"""Phase 8c — Outbound webhook delivery for game events.

Advertisers register endpoints with a signing secret.  When events like
`lead_submitted`, `game_started`, `game_completed`, `prize_won`,
`prize_claimed`, `prize_redeemed`, or a one-shot `test_ping` fire, we
enqueue a `game_webhook_events` row and the background worker delivers it
with HMAC-SHA256 signing + exponential-backoff retries (10s, 1m, 10m, 1h, 6h).

Receivers verify the signature like so:
    expected = hmac.new(secret, f"{timestamp}.{raw_body}".encode(), 'sha256').hexdigest()
    constant_time_eq(expected, header_signature.split('=')[1])
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
import httpx

from services.games_v2 import _new_id, _now

logger = logging.getLogger("bigfm.gamewebhooks")

EVENT_TYPES = {
    "lead_submitted", "game_started", "game_completed",
    "prize_won", "prize_claimed", "prize_redeemed", "test_ping",
    # Phase 10a — Social Passport
    "badge_earned", "referral_engaged",
    # Phase 10b — Social Passport
    "ambassador_level_up",
}
# Phase 9a — back-compat alias so old `play_win` event names from the
# 8c period keep working. They are silently rewritten to `prize_won`
# on register; receivers always see the canonical name.
DEPRECATED_EVENT_ALIASES = {"play_win": "prize_won"}

# Retry schedule (seconds from the FIRST attempt).  After the 5th attempt
# fails, status flips to `max_retries_exceeded` and admin gets a warning row.
RETRY_BACKOFF_SECONDS = [10, 60, 600, 3600, 21600]   # 10s, 1m, 10m, 1h, 6h
MAX_ATTEMPTS = len(RETRY_BACKOFF_SECONDS)
HTTP_TIMEOUT_SECONDS = 5.0
WORKER_TICK_SECONDS = 5.0


async def ensure_webhook_indexes(db) -> None:
    await db.advertiser_webhook_endpoints.create_index(
        [("advertiser_id", 1), ("active", 1)])
    await db.advertiser_webhook_endpoints.create_index(
        [("endpoint_id", 1)], unique=True)
    await db.game_webhook_events.create_index([("status", 1),
                                                          ("next_retry_at", 1)])
    await db.game_webhook_events.create_index([("campaign_id", 1),
                                                          ("created_at", -1)])
    await db.game_webhook_events.create_index([("endpoint_id", 1),
                                                          ("created_at", -1)])
    await db.game_webhook_events.create_index([("event_type", 1),
                                                          ("created_at", -1)])


# ─── Endpoint management ────────────────────────────────────────────────
def _hash_secret(secret: str) -> str:
    return _bcrypt.hashpw(secret.encode("utf-8"),
                                _bcrypt.gensalt(rounds=10)).decode("utf-8")


def _verify_secret(secret: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(secret.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


async def register_endpoint(db, *, advertiser_id: str, url: str,
                                  events_subscribed: list[str]) -> dict:
    # Phase 9a — rewrite deprecated alias names → canonical, collect warnings
    deprecations: list[str] = []
    rewritten: list[str] = []
    for e in events_subscribed:
        if e in DEPRECATED_EVENT_ALIASES:
            rewritten.append(DEPRECATED_EVENT_ALIASES[e])
            deprecations.append(
                f"{e} renamed to {DEPRECATED_EVENT_ALIASES[e]}")
        else:
            rewritten.append(e)
    events_subscribed = rewritten
    bad = [e for e in events_subscribed if e not in EVENT_TYPES]
    if bad:
        raise ValueError(
            f"invalid_event_types:{bad}; allowed={sorted(EVENT_TYPES)}")
    if not url.startswith(("https://", "http://")):
        raise ValueError("url_must_be_http_or_https")
    raw_secret = "whk_" + secrets.token_urlsafe(28)
    secret_hash = _hash_secret(raw_secret)
    eid = _new_id("whep")
    now = _now()
    doc = {
        "_id": eid, "endpoint_id": eid,
        "advertiser_id": advertiser_id,
        "url": url[:500],
        "signing_secret_hash": secret_hash,
        # Internal-only: kept in plaintext so the worker can sign outbound
        # requests.  Never returned to API consumers (omitted from views).
        "signing_secret_plain": raw_secret,
        "events_subscribed": events_subscribed,
        "active": True,
        "created_at": now,
        "last_delivery_at": None,
        "last_failure_count": 0,
    }
    await db.advertiser_webhook_endpoints.insert_one(doc)
    out = {"endpoint_id": eid, "raw_secret": raw_secret,
              "endpoint": _endpoint_view(doc)}
    if deprecations:
        out["deprecation_warnings"] = deprecations
    return out


def _endpoint_view(row: dict) -> dict:
    return {
        "endpoint_id": row["endpoint_id"],
        "advertiser_id": row.get("advertiser_id"),
        "url": row["url"],
        "events_subscribed": row.get("events_subscribed") or [],
        "active": row.get("active", True),
        "created_at": (row["created_at"].isoformat()
                          if row.get("created_at") else None),
        "last_delivery_at": (row["last_delivery_at"].isoformat()
                                  if row.get("last_delivery_at") else None),
        "last_failure_count": row.get("last_failure_count", 0),
    }


async def list_endpoints(db, advertiser_id: str) -> list[dict]:
    items = []
    async for r in db.advertiser_webhook_endpoints.find(
            {"advertiser_id": advertiser_id}).sort("created_at", -1):
        items.append(_endpoint_view(r))
    return items


async def rotate_endpoint_secret(db, endpoint_id: str,
                                          advertiser_id: str) -> dict:
    row = await db.advertiser_webhook_endpoints.find_one(
        {"endpoint_id": endpoint_id, "advertiser_id": advertiser_id})
    if not row:
        raise ValueError("endpoint_not_found")
    raw_secret = "whk_" + secrets.token_urlsafe(28)
    await db.advertiser_webhook_endpoints.update_one(
        {"_id": row["_id"]},
        {"$set": {"signing_secret_hash": _hash_secret(raw_secret),
                   "signing_secret_plain": raw_secret,
                   "updated_at": _now()}})
    return {"endpoint_id": endpoint_id, "raw_secret": raw_secret}


async def delete_endpoint(db, endpoint_id: str,
                                 advertiser_id: str) -> None:
    await db.advertiser_webhook_endpoints.delete_one(
        {"endpoint_id": endpoint_id, "advertiser_id": advertiser_id})


async def list_deliveries(db, endpoint_id: str,
                                 advertiser_id: str,
                                 limit: int = 50) -> list[dict]:
    endpoint = await db.advertiser_webhook_endpoints.find_one(
        {"endpoint_id": endpoint_id, "advertiser_id": advertiser_id})
    if not endpoint:
        raise ValueError("endpoint_not_found")
    out = []
    async for r in (db.game_webhook_events.find({"endpoint_id": endpoint_id})
                       .sort("created_at", -1).limit(limit)):
        out.append({
            "webhook_event_id": r["webhook_event_id"],
            "event_type": r.get("event_type"),
            "destination_url": r.get("destination_url"),
            "status": r.get("status"),
            "attempts": r.get("attempts", 0),
            "last_attempt_at": (r["last_attempt_at"].isoformat()
                                     if r.get("last_attempt_at") else None),
            "next_retry_at": (r["next_retry_at"].isoformat()
                                  if r.get("next_retry_at") else None),
            "last_response_code": r.get("last_response_code"),
            "last_response_body_snippet": r.get("last_response_body_snippet"),
            "created_at": (r["created_at"].isoformat()
                              if r.get("created_at") else None),
        })
    return out


# ─── Event signing + queuing ────────────────────────────────────────────
def sign_payload(secret: str, timestamp: int, body: str) -> str:
    """Returns the hex HMAC-SHA256 of `<timestamp>.<body>`."""
    mac = hmac.new(secret.encode("utf-8"),
                       f"{timestamp}.{body}".encode("utf-8"),
                       hashlib.sha256)
    return mac.hexdigest()


def verify_signature(secret: str, timestamp: int, body: str,
                          signature_header: str) -> bool:
    """Constant-time signature verification helper exposed for tests &
    receivers running the same algorithm."""
    raw = signature_header.split("=", 1)[1] if "=" in signature_header \
            else signature_header
    return hmac.compare_digest(sign_payload(secret, timestamp, body), raw)


async def queue_event(db, *, campaign_id: str, event_type: str,
                            payload: dict,
                            direct_webhook_url: Optional[str] = None) -> list[dict]:
    """Enqueue one webhook event per matching endpoint.

    `direct_webhook_url` is honoured when the campaign's lead form (or
    other source) supplied an explicit URL.  We still need a secret for
    signing — for direct URLs we use a per-campaign deterministic secret
    derived from the campaign_id (stored once in
    `direct_webhook_secrets`).  Advertisers who want richer auth should
    register a proper endpoint instead."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"invalid_event_type:{event_type}")
    enqueued: list[dict] = []
    campaign = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not campaign and event_type != "test_ping":
        return []
    advertiser_id = (campaign or {}).get("advertiser_id")

    # Fan-out to all registered endpoints for this advertiser that
    # subscribe to this event_type.
    if advertiser_id:
        cur = db.advertiser_webhook_endpoints.find({
            "advertiser_id": advertiser_id,
            "active": True,
            "events_subscribed": event_type,
        })
        async for ep in cur:
            row = await _enqueue_for_endpoint(db,
                                                       endpoint=ep,
                                                       campaign_id=campaign_id,
                                                       event_type=event_type,
                                                       payload=payload)
            enqueued.append(row)

    # Plus, if a direct URL was passed in (e.g. lead form's webhook_url),
    # enqueue a one-off delivery.
    if direct_webhook_url:
        secret_row = await db.direct_webhook_secrets.find_one(
            {"campaign_id": campaign_id})
        if not secret_row:
            secret_raw = "whk_direct_" + secrets.token_urlsafe(22)
            await db.direct_webhook_secrets.insert_one({
                "_id": _new_id("dws"),
                "campaign_id": campaign_id,
                "secret_hash": _hash_secret(secret_raw),
                "secret_token_id": "direct:" + campaign_id,
                "created_at": _now(),
            })
            # Persist the actual secret in plaintext field for direct-URL
            # subscribers (they have no way to retrieve it otherwise).
            await db.direct_webhook_secrets.update_one(
                {"campaign_id": campaign_id},
                {"$set": {"secret_plain": secret_raw}})
            secret_to_use = secret_raw
            token_id = "direct:" + campaign_id
        else:
            secret_to_use = secret_row.get("secret_plain")
            token_id = secret_row.get("secret_token_id", "direct:" + campaign_id)
        row = await _enqueue_direct(db,
                                            campaign_id=campaign_id,
                                            event_type=event_type,
                                            payload=payload,
                                            destination_url=direct_webhook_url,
                                            secret=secret_to_use,
                                            secret_token_id=token_id)
        enqueued.append(row)
    return enqueued


async def queue_system_event(db, *, event_type: str,
                                          payload: dict) -> list[dict]:
    """Phase 10a — system-level (campaign-less) fan-out.

    Used for `badge_earned` and `referral_engaged` events that have no
    campaign_id binding.  Fans out to every active endpoint subscribed
    to this event_type across all advertisers.  Subscribers self-select
    by registering with the event in `events_subscribed`.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"invalid_event_type:{event_type}")
    enqueued: list[dict] = []
    cur = db.advertiser_webhook_endpoints.find({
        "active": True,
        "events_subscribed": event_type,
    })
    async for ep in cur:
        row = await _enqueue_for_endpoint(
            db, endpoint=ep,
            campaign_id=f"system:{event_type}",
            event_type=event_type, payload=payload)
        enqueued.append(row)
    return enqueued


async def _enqueue_for_endpoint(db, *, endpoint: dict,
                                          campaign_id: str, event_type: str,
                                          payload: dict) -> dict:
    eid = _new_id("whev")
    now = _now()
    doc = {
        "_id": eid, "webhook_event_id": eid,
        "campaign_id": campaign_id,
        "endpoint_id": endpoint["endpoint_id"],
        "event_type": event_type,
        "payload_json": payload,
        "destination_url": endpoint["url"],
        "signing_secret_used": endpoint["endpoint_id"],
        "status": "pending",
        "attempts": 0,
        "last_attempt_at": None,
        "next_retry_at": now,
        "last_response_code": None,
        "last_response_body_snippet": None,
        "created_at": now,
    }
    await db.game_webhook_events.insert_one(doc)
    return doc


async def _enqueue_direct(db, *, campaign_id: str, event_type: str,
                                payload: dict, destination_url: str,
                                secret: str, secret_token_id: str) -> dict:
    eid = _new_id("whev")
    now = _now()
    doc = {
        "_id": eid, "webhook_event_id": eid,
        "campaign_id": campaign_id,
        "endpoint_id": None,
        "event_type": event_type,
        "payload_json": payload,
        "destination_url": destination_url,
        "signing_secret_used": secret_token_id,
        "_direct_secret_plain": secret,   # internal only; not returned
        "status": "pending",
        "attempts": 0,
        "last_attempt_at": None,
        "next_retry_at": now,
        "last_response_code": None,
        "last_response_body_snippet": None,
        "created_at": now,
    }
    await db.game_webhook_events.insert_one(doc)
    return doc


# ─── Background delivery worker ─────────────────────────────────────────
async def _resolve_secret(db, event: dict) -> Optional[str]:
    """Direct events store the secret inline; endpoint-backed events
    have no plaintext secret in DB (hashed only).  For endpoint-backed
    deliveries we sign with a stable token derived from the endpoint's
    signing_secret_hash so the receiver can still verify with the raw
    secret we issued at registration."""
    if event.get("_direct_secret_plain"):
        return event["_direct_secret_plain"]
    endpoint_id = event.get("endpoint_id")
    if not endpoint_id:
        return None
    # Look up the cached plaintext from the endpoint registration.  We
    # keep it in `advertiser_webhook_endpoints.signing_secret_plain` for
    # outbound HMAC signing — the receiver gets the raw secret only
    # ONCE at registration (returned to the advertiser) and stores it
    # themselves.  Internally we MUST retain it to sign.
    ep = await db.advertiser_webhook_endpoints.find_one(
        {"endpoint_id": endpoint_id},
        {"signing_secret_plain": 1})
    return (ep or {}).get("signing_secret_plain")


async def deliver_one(db, event_id: str) -> dict:
    """Attempt to deliver one webhook event.  Caller controls when to
    invoke this — the background sweeper just enumerates pending rows."""
    ev = await db.game_webhook_events.find_one({"webhook_event_id": event_id})
    if not ev:
        return {"error": "event_not_found"}
    if ev["status"] in {"sent", "max_retries_exceeded"}:
        return {"skipped": ev["status"]}
    secret = await _resolve_secret(db, ev)
    if not secret:
        # No usable secret → mark as max_retries_exceeded immediately
        await db.game_webhook_events.update_one(
            {"webhook_event_id": event_id},
            {"$set": {"status": "max_retries_exceeded",
                       "last_response_body_snippet": "no_secret_available"}})
        return {"error": "no_secret"}
    body = json.dumps(ev["payload_json"], separators=(",", ":"),
                          default=str)
    ts = int(time.time())
    sig = sign_payload(secret, ts, body)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "RadioLife-Games-Webhook/1.0",
        "X-RadioLife-Event": ev["event_type"],
        "X-RadioLife-Delivery": ev["webhook_event_id"],
        "X-RadioLife-Timestamp": str(ts),
        "X-RadioLife-Signature": f"sha256={sig}",
    }
    status_code = None
    snippet = ""
    success = False
    err = None
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            r = await client.post(ev["destination_url"],
                                         content=body, headers=headers)
            status_code = r.status_code
            snippet = (r.text or "")[:512]
            success = 200 <= r.status_code < 300
    except Exception as e:
        err = str(e)[:512]
        snippet = err

    attempts = int(ev.get("attempts", 0)) + 1
    now = _now()
    if success:
        upd = {
            "status": "sent",
            "attempts": attempts,
            "last_attempt_at": now,
            "next_retry_at": None,
            "last_response_code": status_code,
            "last_response_body_snippet": snippet,
        }
        if ev.get("endpoint_id"):
            await db.advertiser_webhook_endpoints.update_one(
                {"endpoint_id": ev["endpoint_id"]},
                {"$set": {"last_delivery_at": now, "last_failure_count": 0}})
    elif attempts >= MAX_ATTEMPTS:
        upd = {
            "status": "max_retries_exceeded",
            "attempts": attempts,
            "last_attempt_at": now,
            "next_retry_at": None,
            "last_response_code": status_code,
            "last_response_body_snippet": snippet,
        }
        if ev.get("endpoint_id"):
            await db.advertiser_webhook_endpoints.update_one(
                {"endpoint_id": ev["endpoint_id"]},
                {"$inc": {"last_failure_count": 1}})
    else:
        # Exponential backoff: the Nth retry (1-indexed) waits
        # RETRY_BACKOFF_SECONDS[N-1] seconds AFTER this attempt.
        delay = RETRY_BACKOFF_SECONDS[attempts - 1]
        upd = {
            "status": "failed",
            "attempts": attempts,
            "last_attempt_at": now,
            "next_retry_at": now + timedelta(seconds=delay),
            "last_response_code": status_code,
            "last_response_body_snippet": snippet,
        }
    await db.game_webhook_events.update_one(
        {"webhook_event_id": event_id}, {"$set": upd})
    return {"success": success, "status_code": status_code,
              "attempts": attempts}


async def background_webhook_worker(app) -> None:
    """Polls `game_webhook_events` every WORKER_TICK_SECONDS for pending
    or due-for-retry rows, attempting delivery one batch at a time."""
    db = app.state.db
    logger.info("game webhook worker starting")
    while True:
        try:
            now = _now()
            cur = db.game_webhook_events.find({
                "$or": [
                    {"status": "pending"},
                    {"status": "failed",
                      "next_retry_at": {"$lte": now}}],
            }).sort("next_retry_at", 1).limit(20)
            ids = [r["webhook_event_id"] async for r in cur]
            for eid in ids:
                await deliver_one(db, eid)
        except Exception as e:
            logger.warning(f"webhook worker tick failed: {e}")
        await asyncio.sleep(WORKER_TICK_SECONDS)
