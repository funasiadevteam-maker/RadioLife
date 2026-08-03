"""Phase 10a — Referral attribution + landing tracking.

Extends Phase 5's `referrals` collection with a parallel
`referral_attributions` ledger that captures the public landing page
+ device fingerprint at click time and walks the attribution through
the funnel: clicked → signed_up → engaged.

Reuses Phase 5's anti-abuse primitives (`_is_publicly_routable_ip`,
admin force_complete, monthly cap) — does NOT replace them.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.referrals_v2")

DEFAULT_ATTRIBUTION_TTL_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def fingerprint(ua: str, ip: str) -> str:
    """Cheap device fingerprint = sha256(ua + '|' + ip)[:24].  Used to
    dedupe same-device repeat clicks on the same ref_code."""
    raw = f"{ua or ''}|{ip or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


# ─── Public landing ────────────────────────────────────────────────────
async def register_landing(db, *, ref_code: str, landing_path: str,
                                     device_fingerprint: Optional[str] = None,
                                     ttl_days: int = DEFAULT_ATTRIBUTION_TTL_DAYS
                                     ) -> dict:
    """Idempotent per (ref_code, device_fingerprint) within the TTL.
    Returns the canonical attribution row."""
    code = (ref_code or "").strip().upper()
    if not code:
        raise ValueError("ref_code_required")
    # Validate the referrer exists
    referrer = await db.users.find_one(
        {"referrer_code": code}, {"user_id": 1, "_id": 0})
    if not referrer:
        raise ValueError("ref_code_not_found")
    # Idempotency on (ref_code, device_fingerprint) within window
    if device_fingerprint:
        existing = await db.referral_attributions.find_one({
            "ref_code": code,
            "device_fingerprint": device_fingerprint,
            "attribution_status": {"$in": ["clicked", "signed_up", "engaged"]},
            "landing_at": {"$gte": _now() - timedelta(days=ttl_days)},
        })
        if existing:
            return existing
    aid = _new_id("att")
    doc = {
        "_id": aid, "attribution_id": aid,
        "referrer_user_id": referrer["user_id"],
        "referee_user_id": None,
        "ref_code": code,
        "landing_path": (landing_path or "/")[:240],
        "landing_at": _now(),
        "signup_at": None,
        "first_engagement_at": None,
        "attribution_status": "clicked",
        "expires_at": _now() + timedelta(days=ttl_days),
        "device_fingerprint": device_fingerprint,
        "created_at": _now(),
    }
    await db.referral_attributions.insert_one(doc)
    return doc


async def claim_attribution(db, *, ref_code: Optional[str],
                                       user_id: str,
                                       device_fingerprint: Optional[str] = None
                                       ) -> Optional[dict]:
    """Called immediately after a fresh signup completes.  Looks up the
    latest still-valid attribution for (ref_code OR fingerprint) and
    links the referee.  Idempotent — re-claiming returns the row."""
    if not (ref_code or device_fingerprint):
        return None
    q: dict = {
        "attribution_status": {"$in": ["clicked"]},
        "expires_at": {"$gte": _now()},
        "referee_user_id": None,
    }
    if ref_code:
        q["ref_code"] = ref_code.strip().upper()
    elif device_fingerprint:
        q["device_fingerprint"] = device_fingerprint
    # Pick the most recent landing
    row = await db.referral_attributions.find_one(
        q, sort=[("landing_at", -1)])
    if not row:
        # Already-claimed lookup so caller gets idempotent response
        return await db.referral_attributions.find_one(
            {"referee_user_id": user_id})
    # Anti-self-attribution
    if row.get("referrer_user_id") == user_id:
        return None
    await db.referral_attributions.update_one(
        {"_id": row["_id"]},
        {"$set": {"referee_user_id": user_id,
                   "signup_at": _now(),
                   "attribution_status": "signed_up"}})
    return await db.referral_attributions.find_one({"_id": row["_id"]})


async def mark_engaged(db, *, referee_user_id: str) -> Optional[dict]:
    """Called when the referee completes onboarding / earns first BC.
    Fires `referral_engaged` webhook."""
    row = await db.referral_attributions.find_one_and_update(
        {"referee_user_id": referee_user_id,
          "attribution_status": "signed_up"},
        {"$set": {"attribution_status": "engaged",
                   "first_engagement_at": _now()}},
        return_document=True)
    if not row:
        return None
    try:
        from services.games_v2_webhooks import queue_system_event
        await queue_system_event(
            db, event_type="referral_engaged",
            payload={
                "attribution_id": row.get("attribution_id"),
                "referrer_user_id": row.get("referrer_user_id"),
                "referee_user_id": referee_user_id,
                "ref_code": row.get("ref_code"),
                "landing_path": row.get("landing_path"),
                "engaged_at": (row.get("first_engagement_at") or _now()
                                  ).isoformat(),
            })
    except Exception as e:
        logger.warning(f"referral_engaged webhook enqueue: {e}")
    # Bookkeeping for badge engine — record the source event
    try:
        from services.badge_engine import evaluate as badge_evaluate
        await badge_evaluate(
            db, row["referrer_user_id"], "referral_completed",
            {"referee_user_id": referee_user_id,
              "ref_code": row.get("ref_code")})
    except Exception as e:
        logger.warning(f"referral_completed badge eval: {e}")
    return row


async def attribution_stats(db, *, referrer_user_id: str) -> dict:
    """Conversion funnel + recent rows."""
    pipe = [
        {"$match": {"referrer_user_id": referrer_user_id}},
        {"$group": {"_id": "$attribution_status", "n": {"$sum": 1}}},
    ]
    funnel = {"clicked": 0, "signed_up": 0, "engaged": 0, "expired": 0}
    async for r in db.referral_attributions.aggregate(pipe):
        funnel[r["_id"]] = int(r["n"])
    # Force expired transition (lazy)
    cutoff = _now()
    await db.referral_attributions.update_many(
        {"referrer_user_id": referrer_user_id,
          "attribution_status": "clicked",
          "expires_at": {"$lt": cutoff}},
        {"$set": {"attribution_status": "expired"}})
    # Recompute after lazy expiry
    funnel = {"clicked": 0, "signed_up": 0, "engaged": 0, "expired": 0}
    async for r in db.referral_attributions.aggregate(pipe):
        funnel[r["_id"]] = int(r["n"])
    total = sum(funnel.values()) or 1
    cur = db.referral_attributions.find(
        {"referrer_user_id": referrer_user_id}).sort("landing_at", -1).limit(20)
    recent = []
    async for r in cur:
        recent.append({
            "attribution_id": r.get("attribution_id"),
            "ref_code": r.get("ref_code"),
            "landing_path": r.get("landing_path"),
            "landing_at": _iso(r.get("landing_at")),
            "signup_at": _iso(r.get("signup_at")),
            "first_engagement_at": _iso(r.get("first_engagement_at")),
            "status": r.get("attribution_status"),
        })
    return {
        "funnel": funnel,
        "total_clicks": funnel["clicked"] + funnel["signed_up"] + funnel["engaged"] + funnel["expired"],
        "conversion_to_signup_pct": round(
            (funnel["signed_up"] + funnel["engaged"]) / total * 100, 2),
        "conversion_to_engaged_pct": round(
            funnel["engaged"] / total * 100, 2),
        "recent": recent,
    }


def _iso(d):
    if isinstance(d, datetime):
        return d.isoformat()
    return d


__all__ = [
    "register_landing", "claim_attribution", "mark_engaged",
    "attribution_stats", "fingerprint",
    "DEFAULT_ATTRIBUTION_TTL_DAYS",
]
