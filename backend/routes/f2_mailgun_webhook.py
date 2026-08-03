"""Phase F-2 — Admin parity check + Mailgun webhook + admin event log.

Endpoints
---------
GET  /api/admin/points/parity-check
    Returns the count of users whose legacy `bigcoin_balance` mirror
    disagrees with the ledger sum from PointsService.  Should be 0
    immediately after `scripts/reconcile_legacy_balance_field.py`
    runs.  Drift > 0 means something is still dual-writing or a row
    was modified directly.

POST /api/webhooks/mailgun/events
    Public endpoint Mailgun pushes events to.  Verifies signature via
    `MAILGUN_WEBHOOK_SIGNING_KEY` (HMAC-SHA256 of `timestamp + token`).
    Persists every event to `mail_events` and cross-links the
    matching `referral_invites` row by `message_id`.

GET  /api/admin/mail/events
    Paginated event log (admin-only).

GET  /api/admin/mail/funnel
    Aggregated funnel metrics: sent, delivered, opened, clicked,
    open_rate, click_rate, bounce_rate, complaint_rate.
"""
from __future__ import annotations
import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query, Depends

from auth import current_user

log = logging.getLogger("bigfm.f2_mailgun_webhook")
router = APIRouter(tags=["f2-mailgun"])


# ─── F-2 parity endpoint ────────────────────────────────────────
def _is_admin(user: dict) -> bool:
    """Match the codebase convention: auth.require_admin checks
    `user.get("role") == "admin"`.  Mirror that here so the parity
    + funnel + event log endpoints stay consistent with /api/admin/*."""
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    if user.get("is_admin") or user.get("is_superadmin"):
        return True
    if "admin" in (user.get("roles") or []):
        return True
    return False


@router.get("/api/admin/points/parity-check")
async def points_parity_check(request: Request,
                                                              limit: int = 50,
                                                              user: dict = Depends(current_user)
                                                              ) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    from services.points_service import PointsService
    svc = PointsService(db)

    scanned = drift = matched = 0
    drift_sample: list[dict] = []
    async for u in db.users.find({}, {"_id": 0, "user_id": 1,
                                                                    "email": 1, "bigcoin_balance": 1}):
        scanned += 1
        uid = u.get("user_id")
        if not uid:
            continue
        try:
            # PointsService.get_balance returns an int directly.
            ledger = int(await svc.get_balance(uid) or 0)
        except Exception:
            continue
        legacy = int(u.get("bigcoin_balance") or 0)
        if ledger == legacy:
            matched += 1
        else:
            drift += 1
            if len(drift_sample) < int(limit):
                drift_sample.append({"user_id": uid,
                                                            "email": u.get("email"),
                                                            "legacy": legacy,
                                                            "ledger": ledger,
                                                            "diff": ledger - legacy})
    return {"scanned": scanned, "matched": matched,
                  "drift_count": drift, "drift_sample": drift_sample,
                  "ledger_authoritative": True,
                  "ts": datetime.now(timezone.utc).isoformat()}


# ─── Mailgun webhook ────────────────────────────────────────────
def _verify_mailgun_signature(timestamp: str, token: str,
                                                              signature: str) -> bool:
    """HMAC-SHA256(signing_key, timestamp + token) → hex digest must
    equal `signature`.  See Mailgun docs → Webhooks → Webhook payload."""
    key = os.environ.get("MAILGUN_WEBHOOK_SIGNING_KEY", "")
    if not key:
        # DEV-mode escape hatch — allow unverified posts but log loudly
        # so we never accidentally ship this to prod.
        if os.environ.get("MAILGUN_WEBHOOK_VERIFY_SIGNATURE", "1") == "0":
            log.warning("[mg_webhook] signature verification DISABLED "
                                    "(MAILGUN_WEBHOOK_VERIFY_SIGNATURE=0) — DEV ONLY")
            return True
        return False
    payload = (timestamp + token).encode("utf-8")
    expected = hmac.new(key.encode("utf-8"), payload,
                                            hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").lower())


def _mask_email(e: str) -> str:
    if not e or "@" not in e:
        return (e or "")[:8]
    local, _, domain = e.partition("@")
    return f"{local[:3]}***@{domain}"


@router.post("/api/webhooks/mailgun/events")
async def mailgun_event(request: Request) -> dict:
    """Mailgun → BigFM event ingest.  Always 200s so Mailgun stops
    retrying once we've persisted; bad sig still gets 200 + logged."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid_json")

    sig = (body.get("signature") or {})
    timestamp = str(sig.get("timestamp", ""))
    token        = str(sig.get("token", ""))
    signature = str(sig.get("signature", ""))

    if not _verify_mailgun_signature(timestamp, token, signature):
        log.warning("[mg_webhook] signature mismatch — dropping event")
        return {"ok": False, "reason": "bad_signature"}

    event_data = body.get("event-data") or {}
    et = event_data.get("event", "").lower()
    # Mailgun events: accepted, delivered, opened, clicked, unsubscribed,
    # complained, permanent_failure, temporary_failure.
    canon = {
        "accepted":                    "accepted",
        "delivered":                "delivered",
        "opened":                        "opened",
        "clicked":                    "clicked",
        "unsubscribed":          "unsubscribed",
        "complained":              "complained",
        "permanent_failure": "permanent_failed",
        "temporary_failure": "temporary_failed",
        "failed":                        "permanent_failed",
    }.get(et, et or "unknown")

    msg = event_data.get("message") or {}
    msg_hdrs = msg.get("headers") or {}
    message_id = msg_hdrs.get("message-id") or event_data.get("message-id")
    # Mailgun puts message-id without angle brackets sometimes; ours store with.
    if message_id and not message_id.startswith("<"):
        message_id = f"<{message_id}>"

    recipient = event_data.get("recipient") or ""
    tags = event_data.get("tags") or []
    geo = event_data.get("geolocation") or {}
    ua = event_data.get("client-info") or {}

    db = request.app.state.db
    evt_id = f"mevt_{uuid.uuid4().hex[:14]}"
    ts = datetime.now(timezone.utc)
    try:
        ev_ts = event_data.get("timestamp")
        if ev_ts:
            ts = datetime.fromtimestamp(float(ev_ts), tz=timezone.utc)
    except Exception:
        pass

    await db.mail_events.insert_one({
        "_id":              evt_id,
        "event_type":  canon,
        "message_id":  message_id,
        "recipient":    recipient,
        "recipient_masked": _mask_email(recipient),
        "tags":              tags,
        "click_url":    event_data.get("url"),
        "geolocation": geo,
        "user_agent": ua.get("user-agent"),
        "ip":                  event_data.get("ip"),
        "timestamp":  ts,
        "raw":              event_data,
    })

    # Cross-link to referral_invites row when present.
    if message_id:
        upd: dict = {}
        if canon in ("accepted", "delivered"):
            upd = {"$set": {"email_status": "delivered",
                                          "email_delivered_at": ts}}
        elif canon == "opened":
            upd = {"$set": {"email_opened_at": ts},
                        "$inc": {"email_open_count": 1}}
        elif canon == "clicked":
            upd = {"$set": {"email_clicked_at": ts,
                                          "email_last_click_url": event_data.get("url")},
                        "$inc": {"email_click_count": 1}}
        elif canon in ("permanent_failed", "complained", "unsubscribed"):
            upd = {"$set": {"email_status": "failed",
                                          "email_failed_at": ts,
                                          "email_failure_reason": canon}}
            # Add to suppression list so we don't email this address again.
            await db.email_suppressions.update_one(
                {"email": recipient.lower()},
                {"$set": {"email": recipient.lower(),
                              "reason": canon, "added_at": ts}},
                upsert=True)
        if upd:
            await db.referral_invites.update_one(
                {"email_message_id": message_id}, upd)

    return {"ok": True, "event_id": evt_id, "event_type": canon}


# ─── Admin event log + funnel ────────────────────────────────
@router.get("/api/admin/mail/events")
async def admin_mail_events(request: Request,
                                                          recipient: Optional[str] = None,
                                                          event_type: Optional[str] = None,
                                                          since_hours: int = 24,
                                                          limit: int = 100,
                                                          user: dict = Depends(current_user)
                                                          ) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    q: dict = {"timestamp": {"$gte": datetime.now(timezone.utc)
                                                                  - timedelta(hours=int(since_hours))}}
    if recipient:
        q["recipient"] = recipient.lower()
    if event_type:
        q["event_type"] = event_type.lower()
    items = [doc async for doc in
                  db.mail_events.find(q, {"_id": 0, "raw": 0})
                      .sort("timestamp", -1).limit(int(limit))]
    return {"count": len(items), "items": items}


@router.get("/api/admin/mail/funnel")
async def admin_mail_funnel(request: Request,
                                                          period: str = Query("week"),
                                                          user: dict = Depends(current_user)
                                                          ) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    delta = {"today": timedelta(days=1),
                  "week":  timedelta(days=7),
                  "month": timedelta(days=30)}.get(period, timedelta(days=7))
    cutoff = datetime.now(timezone.utc) - delta
    pipe = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
    ]
    rows = {r["_id"]: int(r["n"]) async for r in
                  db.mail_events.aggregate(pipe)}
    sent      = rows.get("accepted", 0) + rows.get("delivered", 0)
    delivered = rows.get("delivered", 0)
    opened    = rows.get("opened", 0)
    clicked    = rows.get("clicked", 0)
    bounced    = rows.get("permanent_failed", 0)
    complained = rows.get("complained", 0)
    rate = lambda n, d: round(100.0 * n / d, 2) if d else 0.0
    return {"period": period,
                  "sent": sent, "delivered": delivered,
                  "opened": opened, "clicked": clicked,
                  "bounced": bounced, "complained": complained,
                  "open_rate":            rate(opened, delivered),
                  "click_rate":          rate(clicked, delivered),
                  "bounce_rate":      rate(bounced, sent),
                  "complaint_rate": rate(complained, delivered),
                  "raw_counts":          rows,
                  "computed_at": datetime.now(timezone.utc).isoformat()}
