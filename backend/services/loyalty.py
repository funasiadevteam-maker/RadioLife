"""Loyalty tiers — reward marketplace regulars with bonus BigPoints.

Tier is derived from LIFETIME BigPoints earned (sum of positive ledger
deltas). Higher tiers earn a bonus % on marketplace rewards (pickup orders,
service bookings, product deliveries).

Tiers + perks are ADMIN-CONFIGURABLE, stored in `marketplace_loyalty_config`
(single doc, config_id="global"), seeded idempotently from DEFAULT_TIERS on
first read. Admin edits survive reboots.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.points_service import PointsService

DEFAULT_TIERS: List[Dict[str, Any]] = [
    {"key": "bronze", "name": "Bronze", "min_points": 0, "bonus_pct": 0, "color": "#b08d57",
     "perks": ["Earn BigPoints on every order & booking"]},
    {"key": "silver", "name": "Silver", "min_points": 1000, "bonus_pct": 5, "color": "#9aa5b1",
     "perks": ["+5% bonus BigPoints on the marketplace", "Priority support"]},
    {"key": "gold", "name": "Gold", "min_points": 5000, "bonus_pct": 10, "color": "#e6b800",
     "perks": ["+10% bonus BigPoints on the marketplace", "Early access to Happy Hours"]},
    {"key": "platinum", "name": "Platinum", "min_points": 15000, "bonus_pct": 15, "color": "#6c5ce7",
     "perks": ["+15% bonus BigPoints on the marketplace", "Exclusive partner perks",
               "Free delivery events"]},
]

# Backwards-compat alias (older imports referenced TIERS).
TIERS = DEFAULT_TIERS


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_tiers(db) -> List[Dict[str, Any]]:
    """Load the admin-configurable tier ladder, seeding defaults on first use.
    Always returned sorted ascending by min_points."""
    doc = await db.marketplace_loyalty_config.find_one({"config_id": "global"})
    if not doc or not doc.get("tiers"):
        await db.marketplace_loyalty_config.update_one(
            {"config_id": "global"},
            {"$setOnInsert": {"config_id": "global",
                              "tiers": [dict(t) for t in DEFAULT_TIERS],
                              "created_at": _now()}},
            upsert=True)
        return [dict(t) for t in DEFAULT_TIERS]
    return sorted(doc["tiers"], key=lambda t: t.get("min_points", 0))


def _tier_index(lifetime: int, tiers: List[Dict[str, Any]]) -> int:
    idx = 0
    for i, t in enumerate(tiers):
        if lifetime >= t.get("min_points", 0):
            idx = i
    return idx


async def lifetime_points(db, user_id: str) -> int:
    cur = db.points_ledger.aggregate([
        {"$match": {"user_id": user_id, "delta": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$delta"}}},
    ])
    async for row in cur:
        return int(row.get("total") or 0)
    return 0


async def get_status(db, user_id: str) -> Dict[str, Any]:
    tiers = await get_tiers(db)
    lifetime = await lifetime_points(db, user_id)
    idx = _tier_index(lifetime, tiers)
    tier = tiers[idx]
    nxt = tiers[idx + 1] if idx + 1 < len(tiers) else None
    if nxt:
        span = nxt["min_points"] - tier["min_points"]
        progress = 0.0 if span <= 0 else min(1.0, (lifetime - tier["min_points"]) / span)
        to_next = max(0, nxt["min_points"] - lifetime)
    else:
        progress, to_next = 1.0, 0
    return {
        "tier": tier["key"], "tier_name": tier["name"], "bonus_pct": tier["bonus_pct"],
        "color": tier.get("color", "#b08d57"), "lifetime_points": lifetime,
        "perks": tier.get("perks", []),
        "next_tier": nxt["name"] if nxt else None,
        "next_tier_points": nxt["min_points"] if nxt else None,
        "points_to_next": to_next, "progress": round(progress, 3),
        "all_tiers": [{"key": t["key"], "name": t["name"], "min_points": t["min_points"],
                       "bonus_pct": t["bonus_pct"], "color": t.get("color", "#b08d57")}
                      for t in tiers],
    }


async def award_with_tier_bonus(db, *, user_id: str, source: str, source_id: str,
                                base_points: int, idempotency_key: str,
                                metadata: Optional[dict] = None) -> Dict[str, Any]:
    """Award the base points, then a loyalty bonus based on the user's tier.
    Both awards are idempotent. Returns {base, bonus, tier}."""
    svc = PointsService(db)
    if base_points > 0:
        await svc.award(user_id=user_id, source=source, source_id=source_id,
                        delta=base_points, enforce_caps=False,
                        idempotency_key=idempotency_key, metadata=metadata or {})
    # Tier computed AFTER base award so it reflects the fresh lifetime total.
    status = await get_status(db, user_id)
    pct = status["bonus_pct"]
    bonus = int(round(base_points * pct / 100)) if (pct and base_points > 0) else 0
    if bonus > 0:
        await svc.award(user_id=user_id, source="marketplace_loyalty_bonus",
                        source_id=source_id, delta=bonus, enforce_caps=False,
                        idempotency_key=f"loyalty_{idempotency_key}",
                        metadata={"tier": status["tier"], "base_source": source,
                                  "bonus_pct": pct})
    return {"base": base_points, "bonus": bonus, "tier": status["tier"]}


__all__ = ["TIERS", "DEFAULT_TIERS", "get_tiers", "get_status",
           "lifetime_points", "award_with_tier_bonus"]
