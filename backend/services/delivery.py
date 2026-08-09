"""Phase 12b — Delivery layer for retention campaigns.

Two channels:
    • Email — uses SendGrid v3 if `SENDGRID_API_KEY` is set, otherwise
      falls back to a queue-and-log stub (HIGHLIGHTED MOCK).
    • Push — uses Expo's public push endpoint
      `https://exp.host/--/api/v2/push/send` (no SDK / no key required;
      individual tokens may carry their own access secret via
      `expo_push_token` from `user_push_tokens`).

Every send call:
    1. Writes a `lifecycle_send_log` row with status sent / queued / failed.
    2. For email: optional tracking pixel + click-through redirector via
       `tracking_id` (handled by `routes/admin_retention.py`).

Public API:
    send_email(db, *, user, campaign_id, template, vars) → dict
    send_push(db, *, user, campaign_id, title, body, deep_link) → dict
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("bigfm.delivery")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
DEFAULT_FROM_EMAIL = os.environ.get(
    "RETENTION_FROM_EMAIL", "hello@bigfm.dubai")
DEFAULT_FROM_NAME = os.environ.get(
    "RETENTION_FROM_NAME", "RadioLife")
PUBLIC_BACKEND = os.environ.get(
    "PUBLIC_BACKEND_URL",
    "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


# ─── Phase 12d — SendGrid plan-aware quota ────────────────────────────
SENDGRID_PLAN_CAPS = {
    "free":       {"hourly_soft": 25,     "daily_hard": 100},
    "essentials": {"hourly_soft": 5_000,  "daily_hard": 50_000},
    "pro":        {"hourly_soft": 100_000, "daily_hard": 1_500_000},
    "premier":    {"hourly_soft": 250_000, "daily_hard": 5_000_000},
}
SENDGRID_PLAN_TIER = (os.environ.get("SENDGRID_PLAN_TIER")
                                  or "free").lower()
THROTTLE_DELAY_SEC = float(
    os.environ.get("SENDGRID_THROTTLE_DELAY_SEC", "5"))


def _plan_caps() -> dict:
    return SENDGRID_PLAN_CAPS.get(
        SENDGRID_PLAN_TIER, SENDGRID_PLAN_CAPS["free"])


def _date_hour_keys(now: Optional[datetime] = None) -> tuple:
    n = now or datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%d"), n.hour


async def _read_or_init_quota(db) -> dict:
    date, _hour = _date_hour_keys()
    doc = await db.sendgrid_quota.find_one({"_id": date})
    if not doc:
        doc = {"_id": date, "date": date,
                  "plan_tier": SENDGRID_PLAN_TIER,
                  "daily_sent": 0,
                  "hourly_sent": {str(h): 0 for h in range(24)},
                  "throttled_count": 0,
                  "quota_blocked_count": 0,
                  "created_at": datetime.now(timezone.utc)}
        await db.sendgrid_quota.update_one(
            {"_id": date}, {"$setOnInsert": doc}, upsert=True)
    return doc


async def get_sendgrid_quota_snapshot(db) -> dict:
    import datetime as _dt
    doc = await _read_or_init_quota(db)
    date, hour = _date_hour_keys()
    caps = _plan_caps()
    hsent_map = doc.get("hourly_sent") or {}
    if isinstance(hsent_map, dict):
        hourly_sent = int(hsent_map.get(str(hour), 0))
    else:
        hourly_sent = 0
    daily_sent = int(doc.get("daily_sent", 0))
    now = datetime.now(timezone.utc)
    next_midnight = (now.replace(hour=0, minute=0, second=0,
                                                microsecond=0)
                              + _dt.timedelta(days=1))
    next_hour = (now.replace(minute=0, second=0, microsecond=0)
                       + _dt.timedelta(hours=1))
    return {
        "plan_tier": SENDGRID_PLAN_TIER,
        "caps": caps,
        "date": date, "hour": hour,
        "daily_sent": daily_sent,
        "hourly_sent": hourly_sent,
        "throttled_count": int(doc.get("throttled_count", 0)),
        "quota_blocked_count": int(doc.get("quota_blocked_count", 0)),
        "daily_remaining": max(0, caps["daily_hard"] - daily_sent),
        "hourly_remaining": max(0, caps["hourly_soft"] - hourly_sent),
        "soft_limit_hit": hourly_sent >= caps["hourly_soft"],
        "hard_limit_hit": daily_sent >= caps["daily_hard"],
        "seconds_to_daily_reset": int(
            (next_midnight - now).total_seconds()),
        "seconds_to_hourly_roll": int((next_hour - now).total_seconds()),
    }


async def _check_quota_and_increment(db) -> dict:
    """Returns `{action: 'send'|'throttle'|'block', snapshot}`."""
    snap = await get_sendgrid_quota_snapshot(db)
    if snap["hard_limit_hit"]:
        await db.sendgrid_quota.update_one(
            {"_id": snap["date"]},
            {"$inc": {"quota_blocked_count": 1}})
        return {"action": "block", "snapshot": snap}
    date, hour = _date_hour_keys()
    upd = {"$inc": {"daily_sent": 1,
                          f"hourly_sent.{hour}": 1}}
    if snap["soft_limit_hit"]:
        upd["$inc"]["throttled_count"] = 1
    await db.sendgrid_quota.update_one(
        {"_id": date}, upd, upsert=True)
    action = "throttle" if snap["soft_limit_hit"] else "send"
    return {"action": action, "snapshot": snap}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _payload_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


def render_template(template: str, vars: dict) -> str:
    """Minimal `{var}` token substitution. Missing keys render as empty."""
    if not template:
        return ""
    out = template
    for k, v in (vars or {}).items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out


# ─── Indexes ────────────────────────────────────────────────────────────
async def ensure_delivery_indexes(db) -> None:
    await db.lifecycle_send_log.create_index(
        [("user_id", 1), ("campaign_id", 1), ("sent_at", -1)])
    await db.lifecycle_send_log.create_index("tracking_id", sparse=True)
    await db.lifecycle_send_log.create_index([("campaign_id", 1),
                                                                ("status", 1)])
    await db.delivery_queue.create_index([("status", 1), ("created_at", 1)])


# ─── Email ──────────────────────────────────────────────────────────────
async def _sendgrid_send(*, to_email: str, to_name: str,
                                    subject: str, body_md: str) -> dict:
    """SendGrid v3 send.  Returns {status: 'sent'} on 2xx; raises on
    network error (caller will log + write failed status)."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY not set")
    payload = {
        "personalizations": [{"to": [{"email": to_email,
                                                  "name": to_name}]}],
        "from": {"email": DEFAULT_FROM_EMAIL, "name": DEFAULT_FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": body_md}],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            SENDGRID_URL, json=payload,
            headers={"Authorization": f"Bearer {api_key}"})
    if r.status_code >= 300:
        raise RuntimeError(f"sendgrid {r.status_code}: {r.text[:200]}")
    return {"status": "sent",
              "provider_message_id": r.headers.get("x-message-id")}


async def send_email(db, *, user: dict, campaign_id: str,
                              subject: str, body_template: str,
                              vars: Optional[dict] = None,
                              variant_slug: Optional[str] = None) -> dict:
    """Render + dispatch.  Returns the lifecycle_send_log row that was
    inserted.  When SENDGRID_API_KEY is absent, writes to the
    `delivery_queue` collection and logs a HIGHLIGHTED MOCK warning so
    operators can see the gap immediately.

    `variant_slug` (Phase 13a) is persisted on every send row + queued
    item when the caller already resolved the A/B variant. Callers that
    don't use variants pass None.
    """
    vars = vars or {}
    tracking_id = f"trk_{uuid.uuid4().hex[:18]}"
    # Append tracking pixel + click-wrap CTA in vars for templates
    pixel = (f"<img src=\"{PUBLIC_BACKEND}/api/r/{tracking_id}/pixel.gif\""
              " width=\"1\" height=\"1\" alt=\"\" />")
    full_vars = dict(vars)
    full_vars["__pixel__"] = pixel
    full_vars["__cta_wrap__"] = (
        f"{PUBLIC_BACKEND}/api/r/{tracking_id}/click?to=")
    rendered_body = render_template(body_template, full_vars)
    rendered_subject = render_template(subject, full_vars)
    body_with_pixel = rendered_body + "\n" + pixel
    log = {
        "_id": f"sl_{uuid.uuid4().hex[:18]}",
        "user_id": user["user_id"],
        "email": user.get("email"),
        "campaign_id": campaign_id,
        "channel": "email",
        "subject": rendered_subject,
        "tracking_id": tracking_id,
        "payload_hash": _payload_hash(rendered_subject + rendered_body),
        "sent_at": _now(),
        "status": "stubbed",
    }
    if variant_slug:
        log["variant_slug"] = variant_slug
    if not os.environ.get("SENDGRID_API_KEY"):
        # *** HIGHLIGHTED MOCK ***
        logger.warning(
            "***** HIGHLIGHTED MOCK ***** email send to %s (campaign=%s) "
            "queued to delivery_queue (SENDGRID_API_KEY unset)",
            user.get("email"), campaign_id)
        await db.delivery_queue.insert_one({
            "_id": f"dq_{uuid.uuid4().hex[:18]}",
            "user_id": user["user_id"], "email": user.get("email"),
            "campaign_id": campaign_id,
            "variant_slug": variant_slug,
            "subject": rendered_subject, "body": body_with_pixel,
            "tracking_id": tracking_id,
            "status": "stubbed",
            "created_at": _now(),
        })
        await db.lifecycle_send_log.insert_one(log)
        return log
    # Phase 12d — plan-aware throttle/block BEFORE the real send.
    quota = await _check_quota_and_increment(db)
    if quota["action"] == "block":
        log["status"] = "throttled_quota"
        log["quota_snapshot"] = quota["snapshot"]
        logger.warning(
            "SendGrid hard-limit hit (plan=%s daily=%d/%d); "
            "queueing email user=%s campaign=%s",
            quota["snapshot"]["plan_tier"],
            quota["snapshot"]["daily_sent"],
            quota["snapshot"]["caps"]["daily_hard"],
            user["user_id"], campaign_id)
        await db.delivery_queue.insert_one({
            "_id": f"dq_{uuid.uuid4().hex[:18]}",
            "user_id": user["user_id"], "email": user.get("email"),
            "campaign_id": campaign_id,
            "variant_slug": variant_slug,
            "subject": rendered_subject, "body": body_with_pixel,
            "tracking_id": tracking_id,
            "status": "throttled_quota",
            "reason": "sendgrid_daily_hard_limit",
            "created_at": _now(),
        })
        await db.lifecycle_send_log.insert_one(log)
        return log
    if quota["action"] == "throttle":
        logger.warning(
            "SendGrid soft-limit hit (plan=%s hourly=%d/%d); "
            "delaying %.1fs before send user=%s",
            quota["snapshot"]["plan_tier"],
            quota["snapshot"]["hourly_sent"],
            quota["snapshot"]["caps"]["hourly_soft"],
            THROTTLE_DELAY_SEC, user["user_id"])
        import asyncio
        await asyncio.sleep(THROTTLE_DELAY_SEC)
    try:
        result = await _sendgrid_send(
            to_email=user["email"],
            to_name=user.get("name") or user["email"],
            subject=rendered_subject, body_md=body_with_pixel)
        log["status"] = "sent"
        log["provider_message_id"] = result.get("provider_message_id")
    except Exception as e:
        log["status"] = "failed"
        log["error"] = str(e)[:300]
        logger.warning(f"email send failed user={user['user_id']}: {e}")
    await db.lifecycle_send_log.insert_one(log)
    return log


# ─── Push ───────────────────────────────────────────────────────────────
async def _expo_send(messages: list[dict],
                          client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    """POST messages to Expo's public push API. `messages` follows the
    Expo schema: `{to, title, body, data?, sound?}`. Returns the
    receipts array from Expo (one entry per message)."""
    headers = {"Accept": "application/json",
                  "Accept-encoding": "gzip, deflate",
                  "Content-Type": "application/json"}
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=15)
    try:
        r = await client.post(EXPO_PUSH_URL, json=messages,
                                       headers=headers)
        if r.status_code >= 300:
            raise RuntimeError(f"expo {r.status_code}: {r.text[:200]}")
        data = r.json()
        return data.get("data") or []
    finally:
        if own:
            await client.aclose()


async def send_push(db, *, user: dict, campaign_id: str,
                              title: str, body_template: str,
                              vars: Optional[dict] = None,
                              deep_link: Optional[str] = None,
                              variant_slug: Optional[str] = None) -> dict:
    """Sends to every active expo_push_token registered for the user.
    Records one lifecycle_send_log entry that aggregates per-device
    statuses into `receipts`."""
    vars = vars or {}
    rendered_title = render_template(title, vars)
    rendered_body = render_template(body_template, vars)
    tokens = []
    cur = db.user_push_tokens.find({"user_id": user["user_id"],
                                                    "active": True},
                                                  {"expo_push_token": 1,
                                                    "platform": 1,
                                                    "device_type": 1,
                                                    "apns_environment": 1})
    async for t in cur:
        if t.get("expo_push_token"):
            tokens.append(t)
    log = {
        "_id": f"sl_{uuid.uuid4().hex[:18]}",
        "user_id": user["user_id"],
        "campaign_id": campaign_id,
        "channel": "push",
        "title": rendered_title, "body": rendered_body,
        "payload_hash": _payload_hash(rendered_title + rendered_body),
        "sent_at": _now(),
        "device_count": len(tokens),
        "status": "no_devices" if not tokens else "pending",
    }
    if variant_slug:
        log["variant_slug"] = variant_slug
    if not tokens:
        await db.lifecycle_send_log.insert_one(log)
        return log

    # Phase 13e — split tokens by delivery path.
    from services import apns as apns_svc
    apns_live = apns_svc.is_configured()
    apns_tokens = []
    expo_tokens = []
    for t in tokens:
        is_apns_native = (t.get("device_type") == "apns_native"
                                and not str(t["expo_push_token"]).startswith(
                                    "ExponentPushToken"))
        if apns_live and is_apns_native:
            apns_tokens.append(t)
        else:
            expo_tokens.append(t)

    # ---- APNs direct path -------------------------------------------------
    apns_receipts = []
    for t in apns_tokens:
        r = await apns_svc.send_push(
            device_token=t["expo_push_token"],
            title=rendered_title, body=rendered_body,
            deep_link=deep_link or "/",
            campaign_id=campaign_id, variant_slug=variant_slug)
        apns_receipts.append({"token": t["expo_push_token"], **r})
        await db.push_deliveries.insert_one({
            "_id": f"pd_{uuid.uuid4().hex[:16]}",
            "user_id": user["user_id"],
            "expo_push_token": t["expo_push_token"],
            "campaign_id": campaign_id,
            "delivery_provider": "apns_direct",
            "status": "ok" if r.get("ok") else "failed",
            "apns_id": r.get("apns_id"),
            "apns_env": r.get("env"),
            "details": r,
            "sent_at": _now(),
        })

    # ---- Expo fallback / default path ------------------------------------
    expo_receipts = []
    try:
        if expo_tokens:
            messages = [{
                "to": t["expo_push_token"], "title": rendered_title,
                "body": rendered_body, "sound": "default",
                "data": {"campaign_id": campaign_id,
                            "deep_link": deep_link or "/",
                            "variant_slug": variant_slug},
            } for t in expo_tokens]
            expo_receipts = await _expo_send(messages)
            for t, rcpt in zip(expo_tokens, expo_receipts):
                await db.push_deliveries.insert_one({
                    "_id": f"pd_{uuid.uuid4().hex[:16]}",
                    "user_id": user["user_id"],
                    "expo_push_token": t["expo_push_token"],
                    "campaign_id": campaign_id,
                    "delivery_provider": "expo_proxy",
                    "status": rcpt.get("status") or "unknown",
                    "expo_receipt_id": rcpt.get("id"),
                    "details": rcpt.get("details"),
                    "sent_at": _now(),
                })
        log["status"] = "sent"
        log["receipts"] = (apns_receipts + expo_receipts)[:10]
        log["delivery_provider_counts"] = {
            "apns_direct": len(apns_tokens),
            "expo_proxy":  len(expo_tokens),
        }
    except Exception as e:
        log["status"] = "failed"
        log["error"] = str(e)[:300]
        logger.warning(f"push send failed user={user['user_id']}: {e}")
    await db.lifecycle_send_log.insert_one(log)
    return log
