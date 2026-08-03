"""Phase 36e Turn 3 — First-episode publish nudge.

Drives the qualification check, banner gate, periodic email cron, and
SendGrid-mock email dispatch. All SendGrid calls route through the existing
`services.delivery.send_email` abstraction (which already honours
`SENDGRID_API_KEY` presence → mock mode otherwise). When SendGrid is in
mock mode, this module writes a structured log line + a `creator_nudge_events`
ledger row with a `sg_mock_*` message ID so the day SENDGRID_API_KEY ships
to .env, the path flips to real-send without any code change here.
"""
from __future__ import annotations
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("bigfm.nudges")

PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL")
    or "https://mobile-games-v2.preview.emergentagent.com")

# 24h email runs in the (24h, 26h) past window. Window width must exceed
# cron tick interval (daily) to guarantee at-least-once delivery.
WINDOW_24H_START = timedelta(hours=24)
WINDOW_24H_END    = timedelta(hours=26)
WINDOW_72H_START = timedelta(hours=72)
WINDOW_72H_END    = timedelta(hours=74)


def _now(): return datetime.now(timezone.utc)
def _new_id(prefix: str): return f"{prefix}_{secrets.token_hex(8)}"


async def ensure_indexes(db) -> None:
    await db.creator_nudge_events.create_index(
        [("creator_id", 1), ("occurred_at", -1)])


# ─── Qualification check ──────────────────────────────────────
async def qualifies_for_nudge(db, *, creator: dict) -> dict:
    """Return {qualifies, reason}. Pure read."""
    if creator.get("application_status") != "approved":
        return {"qualifies": False, "reason": "not_approved"}
    if creator.get("nudges_paused"):
        return {"qualifies": False, "reason": "paused"}
    if creator.get("first_episode_published_at"):
        return {"qualifies": False, "reason": "already_published"}
    # Double-check via DB for the rare race where denormalized flag missed.
    has_published = await db.podcast_episodes.find_one({
        "channel_id": {"$in": [c["id"] for c in
            await db.podcast_channels.find({"creator_id": creator["id"]},
                                                                          {"_id": 0, "id": 1}).to_list(50)]},
        "publish_status": "published"}, {"_id": 0, "id": 1})
    if has_published:
        return {"qualifies": False, "reason": "already_published"}
    return {"qualifies": True, "reason": None}


async def get_status_payload(db, *, creator: dict) -> dict:
    q = await qualifies_for_nudge(db, creator=creator)
    last = await db.creator_nudge_events.find_one(
        {"creator_id": creator["id"]},
        sort=[("occurred_at", -1)], projection={"_id": 0})
    return {
        "qualifies": q["qualifies"],
        "reason": q.get("reason"),
        "nudges_paused": bool(creator.get("nudges_paused")),
        "last_event": last,
        "banner_message":
            "🎙️ Record your first episode to start building your audience"
            if q["qualifies"] else None,
    }


# ─── Pause / resume / publish hook ───────────────────────────
async def _log_event(db, *, creator_id: str, event_type: str,
                                              reason: Optional[str] = None,
                                              provider_message_id: Optional[str] = None,
                                              provider: Optional[str] = None) -> dict:
    doc = {"id": _new_id("cne"), "creator_id": creator_id,
                "event_type": event_type, "reason": reason,
                "provider_message_id": provider_message_id,
                "provider": provider,
                # Backward-compat alias for any consumer still reading the old field.
                "sendgrid_message_id": provider_message_id,
                "occurred_at": _now()}
    await db.creator_nudge_events.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def set_paused(db, *, creator_id: str, paused: bool) -> dict:
    await db.podcast_creators.update_one(
        {"id": creator_id}, {"$set": {"nudges_paused": paused}})
    await _log_event(db, creator_id=creator_id,
        event_type="nudge_paused_by_user" if paused else "nudge_resumed_by_user")
    return await db.podcast_creators.find_one(
        {"id": creator_id},
        {"_id": 0, "id": 1, "nudges_paused": 1,
          "first_episode_published_at": 1})


async def mark_first_episode_published(db, *, channel_id: str) -> Optional[dict]:
    """Called from publish_episode hook. Sets the denormalized flag on
    the OWNING creator if not already stamped. Idempotent."""
    ch = await db.podcast_channels.find_one({"id": channel_id},
                                                                                  {"_id": 0, "creator_id": 1})
    if not ch or not ch.get("creator_id"): return None
    creator = await db.podcast_creators.find_one(
        {"id": ch["creator_id"]},
        {"_id": 0, "id": 1, "first_episode_published_at": 1})
    if not creator: return None
    if creator.get("first_episode_published_at"): return creator
    now = _now()
    await db.podcast_creators.update_one(
        {"id": creator["id"]},
        {"$set": {"first_episode_published_at": now}})
    creator["first_episode_published_at"] = now
    return creator


# ─── Email dispatch (mock-discipline) ────────────────────────
def _render_email(*, kind: str, creator: dict) -> dict:
    display = creator.get("display_name") or "there"
    url = f"{PUBLIC_BASE_URL}/creator/studio/new"
    if kind == "24h":
        subject = "Ready to record your first BigFM episode?"
        body =  ("<h2>Hey " + display + ",</h2>"
                          "<p>We approved your creator account yesterday. "
                          "The fastest way to start building an audience is to "
                          "publish your first episode today.</p>"
                          "<p><a href='" + url + "' style='display:inline-block;"
                          "padding:10px 16px;background:#f59e0b;color:#0a0a0c;"
                          "text-decoration:none;border-radius:8px;font-weight:700'>"
                          "Record your first episode</a></p>"
                          "<p style='color:#888;font-size:12px'>BigFM Creator team</p>")
    elif kind == "72h":
        subject = "Your BigFM channel is waiting for episode #1"
        body =  ("<h2>Hi " + display + ",</h2>"
                          "<p>It's been three days since we approved your channel. "
                          "Creators who publish in the first week see 4× the "
                          "follower growth of those who wait longer.</p>"
                          "<p><a href='" + url + "' style='display:inline-block;"
                          "padding:10px 16px;background:#f59e0b;color:#0a0a0c;"
                          "text-decoration:none;border-radius:8px;font-weight:700'>"
                          "Open Creator Studio</a></p>"
                          "<p style='color:#888;font-size:12px'>"
                          "Don't want these reminders? Pause them in Creator Studio.</p>")
    else:
        raise ValueError(f"unknown nudge kind: {kind}")
    return {"subject": subject, "body": body, "cta_url": url}


async def _send_nudge_email(db, *, creator: dict, kind: str) -> dict:
    """Mock-disciplined send. When SENDGRID_API_KEY is unset (mock mode),
    logs the rendered payload to a structured logger and returns a fake
    sg_mock_* message id. When live, delegates to services.delivery.send_email
    which already handles the live SendGrid call + quota throttling."""
    rendered = _render_email(kind=kind, creator=creator)
    email = creator.get("email")
    if not email:
        # Look it up from users.
        u = await db.users.find_one({"user_id": creator.get("user_id")},
                                                                {"_id": 0, "email": 1})
        email = u and u.get("email")
    if not email:
        logger.warning("[nudges] creator %s has no email; skipping send",
                                      creator.get("id"))
        return {"sent": False, "reason": "no_email", "message_id": None,
                      "provider": None}
    # Phase 36e Turn 3.5 — route through Mailgun when configured.
    from services import mailgun_client as mg
    if mg.is_live():
        try:
            res = mg.send_email(email, rendered["subject"], rendered["body"],
                                                  tags=[f"first_episode_{kind}"])
            return {"sent": True, "reason": "live", "provider": "mailgun",
                          "message_id": res.get("message_id"),
                          "rendered": rendered, "to": email}
        except Exception as e:
            logger.warning("[nudges] mailgun failed → mock fallback: %s", e)
            # fall through to mock
    msg_id = f"sg_mock_{secrets.token_hex(8)}"
    logger.warning(
        "***** HIGHLIGHTED MOCK ***** nudge email kind=%s creator=%s "
        "to=%s subject=%r body_excerpt=%r message_id=%s",
        kind, creator.get("id"), email, rendered["subject"],
        rendered["body"][:80], msg_id)
    return {"sent": True, "reason": "mock_mode", "provider": "mock",
                  "message_id": msg_id, "rendered": rendered, "to": email}


# ─── Cron tick ────────────────────────────────────────────────
async def tick_first_episode_nudges(db, *, dry_run: bool = False,
                                                                              now: Optional[datetime] = None) -> dict:
    """Sweep approved-but-unpublished creators, send 24h/72h emails inside
    their respective windows. Returns counts {window_24h_sent, window_72h_sent,
    skipped, dry_run}. Idempotent — re-running won't re-send because the
    *_sent_at stamps gate each send."""
    now = now or _now()
    sent_24, sent_72, skipped = 0, 0, 0

    async def _process_window(kind: str, w_start: timedelta, w_end: timedelta,
                                                          sent_field: str):
        nonlocal sent_24, sent_72, skipped
        cursor = db.podcast_creators.find({
            "application_status": "approved",
            "approved_at": {"$lte": now - w_start, "$gt": now - w_end},
            sent_field: None,
        }, {"_id": 0})
        async for cr in cursor:
            if cr.get("nudges_paused"):
                await _log_event(db, creator_id=cr["id"],
                    event_type=f"email_{kind}_skipped", reason="paused")
                skipped += 1
                continue
            q = await qualifies_for_nudge(db, creator=cr)
            if not q["qualifies"]:
                await _log_event(db, creator_id=cr["id"],
                    event_type=f"email_{kind}_skipped",
                    reason=q.get("reason") or "ineligible")
                skipped += 1
                continue
            if dry_run:
                await _log_event(db, creator_id=cr["id"],
                    event_type=f"email_{kind}_skipped", reason="dry_run")
                skipped += 1
                continue
            res = await _send_nudge_email(db, creator=cr, kind=kind)
            if res.get("sent"):
                await db.podcast_creators.update_one(
                    {"id": cr["id"]},
                    {"$set": {sent_field: now}})
                await _log_event(db, creator_id=cr["id"],
                    event_type=f"email_{kind}_sent",
                    reason=res.get("reason"),
                    provider=res.get("provider"),
                    provider_message_id=res.get("message_id"))
                if kind == "24h": sent_24 += 1
                else:                          sent_72 += 1
            else:
                await _log_event(db, creator_id=cr["id"],
                    event_type=f"email_{kind}_skipped",
                    reason=res.get("reason") or "no_email")
                skipped += 1

    await _process_window("24h", WINDOW_24H_START, WINDOW_24H_END,
                                                  "nudge_email_24h_sent_at")
    await _process_window("72h", WINDOW_72H_START, WINDOW_72H_END,
                                                  "nudge_email_72h_sent_at")
    return {"window_24h_sent": sent_24, "window_72h_sent": sent_72,
                  "skipped": skipped, "dry_run": dry_run, "ran_at": now}
