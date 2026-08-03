"""Phase 12c — Coupon fraud prevention.

Hooks into the coupon redeem flow.  Rules:
    R1. Same QR redeemed > `max_redemptions` → block + flag partner.
    R2. one_time_use coupon redeemed >1 by same user → block + flag.
    R3. Velocity: user redeems >5 coupons in 60s → block.
    R4. Geo mismatch: redemption from a partner >50km from user's
        recent commute / stored location → flag (no block).
    R5. Device fingerprint dupes — same device_id across multiple
        accounts redeeming → flag.

Every flag persisted to `fraud_events`.
"""
from __future__ import annotations
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.strikes import record_strike

logger = logging.getLogger("bigfm.fraud")

VELOCITY_LIMIT = 5
VELOCITY_WINDOW_SEC = 60
GEO_MAX_KM = 50.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_fraud_indexes(db) -> None:
    await db.fraud_events.create_index(
        [("user_id", 1), ("created_at", -1)])
    await db.fraud_events.create_index("status")
    await db.fraud_events.create_index("rule")


def _haversine_km(lat1: float, lon1: float,
                          lat2: float, lon2: float) -> float:
    R = 6371.0
    rad = math.pi / 180
    a = (math.sin((lat2 - lat1) * rad / 2) ** 2
            + math.cos(lat1 * rad) * math.cos(lat2 * rad)
            * math.sin((lon2 - lon1) * rad / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


async def _emit_event(db, *, rule: str, severity: str, user_id: str,
                              coupon_id: str | None, partner_id: str | None,
                              detail: dict) -> dict:
    fid = f"fr_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id": fid, "fraud_id": fid,
        "rule": rule, "severity": severity, "status": "open",
        "user_id": user_id, "coupon_id": coupon_id,
        "partner_id": partner_id, "detail": detail,
        "created_at": _now(),
    }
    await db.fraud_events.insert_one(doc)
    # Pair fraud events with a strike on the user
    try:
        await record_strike(
            db, user_id=user_id, severity=severity, source="fraud",
            reason=rule, ref_type="fraud_event", ref_id=fid)
    except Exception as e:
        logger.warning(f"strike record failed for fraud {fid}: {e}")
    return doc


async def check_redeem(db, *, coupon: dict, user: dict,
                                  partner: Optional[dict] = None,
                                  device_id: Optional[str] = None) -> dict:
    """Run all redeem-time rules.  Returns
        {action: "allow"|"block"|"review", events: [fraud_event,...]}
    Caller must reject the redeem when action == "block"."""
    events: list[dict] = []
    action = "allow"

    # R1 — over-redemption of the same QR
    max_red = int(coupon.get("max_redemptions") or 1)
    used = int(coupon.get("redeemed_count") or 0)
    if used >= max_red:
        ev = await _emit_event(
            db, rule="max_redemptions_exceeded", severity="medium",
            user_id=user["user_id"],
            coupon_id=coupon.get("coupon_id") or coupon.get("_id"),
            partner_id=coupon.get("partner_id") or coupon.get("business_id"),
            detail={"max": max_red, "used": used})
        events.append(ev)
        action = "block"

    # R2 — one_time_use double redeem by same user
    if coupon.get("one_time_use"):
        prior = await db.coupons.find_one({
            "coupon_id": coupon.get("coupon_id"),
            "user_id": user["user_id"],
            "redeemed_at": {"$ne": None},
        })
        if prior:
            ev = await _emit_event(
                db, rule="one_time_use_double_redeem", severity="high",
                user_id=user["user_id"],
                coupon_id=coupon.get("coupon_id"),
                partner_id=coupon.get("partner_id"),
                detail={"prior_redeemed_at": prior.get("redeemed_at")})
            events.append(ev)
            action = "block"

    # R3 — velocity
    velocity_cutoff = _now() - timedelta(seconds=VELOCITY_WINDOW_SEC)
    recent_count = await db.coupons.count_documents({
        "user_id": user["user_id"],
        "redeemed_at": {"$gte": velocity_cutoff},
    })
    if recent_count >= VELOCITY_LIMIT:
        ev = await _emit_event(
            db, rule="redeem_velocity", severity="high",
            user_id=user["user_id"],
            coupon_id=coupon.get("coupon_id"),
            partner_id=coupon.get("partner_id"),
            detail={"recent_count": recent_count,
                      "window_sec": VELOCITY_WINDOW_SEC})
        events.append(ev)
        action = "block"

    # R4 — geo mismatch (flag, never block)
    if partner and partner.get("latitude") is not None:
        last_loc = (user.get("last_known_location") or {})
        u_lat = last_loc.get("lat"); u_lng = last_loc.get("lng")
        if u_lat is not None and u_lng is not None:
            dist = _haversine_km(
                float(u_lat), float(u_lng),
                float(partner["latitude"]), float(partner["longitude"]))
            if dist > GEO_MAX_KM:
                ev = await _emit_event(
                    db, rule="geo_mismatch", severity="low",
                    user_id=user["user_id"],
                    coupon_id=coupon.get("coupon_id"),
                    partner_id=partner.get("business_id"),
                    detail={"distance_km": round(dist, 1),
                              "max_km": GEO_MAX_KM})
                events.append(ev)
                if action == "allow": action = "review"

    # R5 — device fingerprint dupes
    if device_id:
        other_accounts = await db.user_push_tokens.distinct(
            "user_id", {"device_id": device_id})
        other_accounts = [a for a in other_accounts
                                  if a and a != user["user_id"]]
        if len(other_accounts) >= 1:
            ev = await _emit_event(
                db, rule="device_dupe", severity="medium",
                user_id=user["user_id"],
                coupon_id=coupon.get("coupon_id"),
                partner_id=coupon.get("partner_id"),
                detail={"device_id": device_id,
                          "other_account_count": len(other_accounts)})
            events.append(ev)
            if action == "allow": action = "review"

    return {"action": action, "events": events}
