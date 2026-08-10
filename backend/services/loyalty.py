"""Loyalty tiers — reward marketplace regulars with bonus BigPoints.

Tier is derived from LIFETIME BigPoints earned (sum of positive ledger
deltas). Higher tiers earn a bonus % on marketplace rewards (pickup orders,
service bookings, product deliveries).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.points_service import PointsService

TIERS = [
    {"key": "bronze", "name": "Bronze", "min_points": 0, "bonus_pct": 0, "color": "#b08d57"},
    {"key": "silver", "name": "Silver", "min_points": 1000, "bonus_pct": 5, "color": "#9aa5b1"},
    {"key": "gold", "name": "Gold", "min_points": 5000, "bonus_pct": 10, "color": "#e6b800"},
    {"key": "platinum", "name": "Platinum", "min_points": 15000, "bonus_pct": 15, "color": "#6c5ce7"},
]

PERKS = {
    "bronze": ["Earn BigPoints on every order & booking"],
    "silver": ["+5% bonus BigPoints on the marketplace", "Priority support"],
    "gold": ["+10% bonus BigPoints on the marketplace", "Early access to Happy Hours"],
    "platinum": ["+15% bonus BigPoints on the marketplace", "Exclusive partner perks", "Free delivery events"],
}


def _tier_index(lifetime: int) -> int:
    idx = 0
    for i, t in enumerate(TIERS):
        if lifetime >= t["min_points"]:
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
    lifetime = await lifetime_points(db, user_id)
    idx = _tier_index(lifetime)
    tier = TIERS[idx]
    nxt = TIERS[idx + 1] if idx + 1 < len(TIERS) else None
    if nxt:
        span = nxt["min_points"] - tier["min_points"]
        progress = 0.0 if span <= 0 else min(1.0, (lifetime - tier["min_points"]) / span)
        to_next = max(0, nxt["min_points"] - lifetime)
    else:
        progress, to_next = 1.0, 0
    return {
        "tier": tier["key"], "tier_name": tier["name"], "bonus_pct": tier["bonus_pct"],
        "color": tier["color"], "lifetime_points": lifetime,
        "perks": PERKS.get(tier["key"], []),
        "next_tier": nxt["name"] if nxt else None,
        "next_tier_points": nxt["min_points"] if nxt else None,
        "points_to_next": to_next, "progress": round(progress, 3),
        "all_tiers": [{"key": t["key"], "name": t["name"], "min_points": t["min_points"],
                       "bonus_pct": t["bonus_pct"], "color": t["color"]} for t in TIERS],
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


__all__ = ["TIERS", "get_status", "lifetime_points", "award_with_tier_bonus"]
