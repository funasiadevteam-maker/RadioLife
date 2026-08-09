"""Phase 17c — "Boost this offer" lever.

Detects offers that are losing the impression→save funnel stage and lets
the venue owner fire a single push fan-out + temporary discount bump in
exchange for one of two allowed boosts per offer per 14 days.

Sweeps every 10 min (sibling task of the 17b auto-resume scheduler) to
revert expired boosts.

Schema (`offer_boosts` collection):
    { id, offer_id, venue_id, started_at, ends_at,
      original_discount_value, boosted_discount_value,
      push_count, status: "active|completed|reverted" }
"""
from __future__ import annotations

import logging
import os
import random
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.boost")

# Eligibility thresholds.
ELIGIBLE_MIN_IMPRESSIONS  = 50
ELIGIBLE_MIN_DROP_PCT      = 30.0
ELIGIBLE_FIRST_STAGE        = "impression"
DEFAULT_DURATION_HOURS    = 24
DEFAULT_DISCOUNT_BUMP_PCT = 5.0
BOOST_LIMIT_PER_14_DAYS  = 2

PUSH_COPY_VARIANTS = [
    "🔥 Boosted: {title} — now {pct}% off for 24h.",
    "Just dropped: {pct}% off {title} at {venue_name}. Tonight only.",
    "{venue_name} fired a deal: {title} bumped to {pct}% off. Tap to save.",
]


def _now() -> datetime: return datetime.now(timezone.utc)


# ─── Eligibility ─────────────────────────────────────────────────────
def compute_boost_eligibility(funnel: dict) -> bool:
    """Receives the same payload `funnel_for_offer` returns and decides
    whether the offer qualifies for a 1-tap boost."""
    if not funnel:
        return False
    if (funnel.get("impressions") or 0) < ELIGIBLE_MIN_IMPRESSIONS:
        return False
    td = funnel.get("top_drop") or {}
    return (td.get("from") == ELIGIBLE_FIRST_STAGE
              and (td.get("drop_pct") or 0) > ELIGIBLE_MIN_DROP_PCT)


# ─── Push fan-out (re-uses 16d push pattern, but tolerant if absent) ──
async def _push_targets_for_venue(db, venue_id: str, market: Optional[str]) -> list[str]:
    cutoff = _now() - timedelta(days=90)
    saver_ids = await db.coupons.distinct("user_id",
                                                                  {"venue_id": venue_id,
                                                                  "issued_at": {"$gte": cutoff}})
    if not saver_ids and market:
        saver_ids = await db.users.distinct("user_id", {"market": market})
    return saver_ids[:5000]  # safety cap


async def _fan_out_push(db, *, offer: dict, venue: dict,
                                  pct: int, user_ids: list[str]) -> int:
    """Drop a notification document per target user.  We never raise here —
    a push outage must not roll back the boost itself."""
    if not user_ids:
        return 0
    copy = random.choice(PUSH_COPY_VARIANTS).format(
        title=offer.get("title") or "your favorite spot",
        pct=pct,
        venue_name=(venue or {}).get("name") or "RadioLife",
    )
    docs = [{
        "id":             f"notif_boost_{secrets.token_hex(6)}_{u}",
        "user_id":      u,
        "offer_id":     offer["id"],
        "venue_id":   venue.get("id"),
        "type":          "offer_boost",
        "title":          "Boosted offer",
        "body":           copy,
        "created_at": _now(),
        "read":          False,
    } for u in user_ids]
    try:
        await db.notifications.insert_many(docs, ordered=False)
    except Exception as e:
        logger.warning("[boost] push fan-out failed: %s", e)
        return 0
    return len(docs)


# ─── Start / list / sweep ────────────────────────────────────────────
async def start_boost(db, *, venue_id: str, offer_id: str,
                                  duration_hours: int = DEFAULT_DURATION_HOURS,
                                  discount_bump_pct: float = DEFAULT_DISCOUNT_BUMP_PCT) -> dict:
    """Atomic-ish: validate caps, mutate offer, write boost, fan out push."""
    offer = await db.offers.find_one({"id": offer_id, "venue_id": venue_id})
    if not offer:
        raise LookupError("offer-not-found")

    # 1️⃣  Cap: only one active boost per offer at a time.
    active = await db.offer_boosts.find_one(
        {"offer_id": offer_id, "status": "active"})
    if active:
        raise PermissionError({"code": "already_active",
                                          "message": "An active boost is already running."})
    # 2️⃣  Cap: at most BOOST_LIMIT_PER_14_DAYS boosts in the last 14 days.
    since = _now() - timedelta(days=14)
    used = await db.offer_boosts.count_documents(
        {"offer_id": offer_id, "started_at": {"$gte": since}})
    if used >= BOOST_LIMIT_PER_14_DAYS:
        raise PermissionError({"code": "boost_limit",
                                          "message": (f"Max {BOOST_LIMIT_PER_14_DAYS} boosts per "
                                                              "offer per 14 days reached."),
                                          "used":     used,
                                          "limit":   BOOST_LIMIT_PER_14_DAYS})

    original   = float(offer.get("discount_value") or 0)
    boosted   = original + float(discount_bump_pct)
    now        = _now()
    ends_at  = now + timedelta(hours=int(duration_hours))
    boost_id = f"bst_{secrets.token_hex(6)}"

    venue = await db.venues.find_one({"id": venue_id}) or {}
    market = venue.get("market") or offer.get("market")
    targets = await _push_targets_for_venue(db, venue_id, market)
    push_count = await _fan_out_push(db, offer=offer, venue=venue,
                                                          pct=int(round(boosted)),
                                                          user_ids=targets)

    boost_doc = {
        "id":                              boost_id,
        "offer_id":                     offer_id,
        "venue_id":                   venue_id,
        "started_at":                 now,
        "ends_at":                      ends_at,
        "original_discount_value": original,
        "boosted_discount_value": boosted,
        "discount_bump_pct":     float(discount_bump_pct),
        "duration_hours":           int(duration_hours),
        "push_count":                  push_count,
        "status":                         "active",
    }
    await db.offer_boosts.insert_one(boost_doc)
    boost_doc.pop("_id", None)   # Motor injects ObjectId — strip before return.
    await db.offers.update_one(
        {"id": offer_id},
        {"$set": {"discount_value":            boosted,
                    "boost_active":              True,
                    "boost_ends_at":           ends_at,
                    "boost_original_value": original,
                    "updated_at":                now}})
    logger.info("[boost] start offer=%s push=%d ends=%s",
                      offer_id, push_count, ends_at.isoformat())
    return {**boost_doc, "push_copy_sample": (PUSH_COPY_VARIANTS[0].format(
        title=offer.get("title") or "", pct=int(round(boosted)),
        venue_name=venue.get("name") or "RadioLife",
    ))}


async def list_boosts(db, *, venue_id: str, offer_id: str,
                                  limit: int = 10) -> list[dict]:
    rows = await db.offer_boosts.find(
        {"offer_id": offer_id, "venue_id": venue_id},
        sort=[("started_at", -1)]).to_list(limit)
    out = []
    for b in rows:
        # Compute lift since boost start vs equal-window baseline before.
        bstart = b["started_at"]
        if bstart.tzinfo is None:
            bstart = bstart.replace(tzinfo=timezone.utc)
        bend   = b["ends_at"] if b["ends_at"].tzinfo else b["ends_at"].replace(tzinfo=timezone.utc)
        window = (bend - bstart)
        base_from = bstart - window
        during = await db.offer_events.count_documents({
            "offer_id": offer_id,
            "stage":     "redeem",
            "timestamp": {"$gte": bstart, "$lt": bend}})
        before = await db.offer_events.count_documents({
            "offer_id": offer_id,
            "stage":     "redeem",
            "timestamp": {"$gte": base_from, "$lt": bstart}})
        out.append({
            "id":          b["id"],
            "started_at": bstart.isoformat(),
            "ends_at":     bend.isoformat(),
            "status":     b["status"],
            "push_count": b.get("push_count", 0),
            "original_discount_value": b["original_discount_value"],
            "boosted_discount_value": b["boosted_discount_value"],
            "redeems_during":  during,
            "redeems_before": before,
            "lift_abs":          during - before,
        })
    return out


async def revert_expired_boosts(db, *, now: Optional[datetime] = None) -> dict:
    """Sweep tick — flips status to 'completed' and reverts offer.discount."""
    now = now or _now()
    cursor = db.offer_boosts.find({"status": "active",
                                                      "ends_at": {"$lte": now}})
    reverted = 0
    async for b in cursor:
        await db.offers.update_one(
            {"id": b["offer_id"]},
            {"$set": {"discount_value":            b["original_discount_value"],
                        "boost_active":              False,
                        "updated_at":                now},
              "$unset": {"boost_ends_at": "", "boost_original_value": ""}})
        await db.offer_boosts.update_one(
            {"id": b["id"]},
            {"$set": {"status": "completed", "completed_at": now}})
        reverted += 1
        logger.info("[boost] revert offer=%s boost=%s",
                          b["offer_id"], b["id"])
    return {"reverted": reverted, "tick_at": now.isoformat()}
