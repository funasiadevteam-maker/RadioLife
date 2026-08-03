"""Phase K.3 — Points-balance-based Ambassador Tier.

This is a SEPARATE concept from the Phase 10a `ambassador_levels`
collection (which is driven by total badge-points and surfaces as
`user_ambassador_state.level`).  Phase K introduces a parallel,
PointsService-balance-driven tier band purely for visual flair on
the new Passport UI / MiniPlayer.

Tiers
-----
    bronze        0  – 99
    silver      100 – 499
    gold          500 – 2,499
    platinum  2,500 – 9,999
    legend     10,000+

The tier is cached on the user doc under `ambassador_tier` +
`ambassador_tier_updated_at` so the Passport page / MiniPlayer pill
can read it in a single doc fetch without a balance roundtrip.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("bigfm.passport_engine")

TIER_BANDS = [
    ("legend",      10000, None),
    ("platinum",  2500, 10000),
    ("gold",          500,  2500),
    ("silver",      100,  500),
    ("bronze",      0,      100),
]

TIER_THEME = {
    "bronze":      {"hex": "#a86a3e", "label": "Bronze Ambassador"},
    "silver":      {"hex": "#bcc4d6", "label": "Silver Ambassador"},
    "gold":          {"hex": "#f5c84b", "label": "Gold Ambassador"},
    "platinum":  {"hex": "#7ad3ff", "label": "Platinum Ambassador"},
    "legend":      {"hex": "#ff38bb", "label": "Legend"},
}


def tier_for_balance(balance: int) -> str:
    bal = int(balance or 0)
    for name, lo, hi in TIER_BANDS:
        if bal >= lo and (hi is None or bal < hi):
            return name
    return "bronze"


def tier_theme(tier: str) -> dict:
    return TIER_THEME.get(tier or "bronze") or TIER_THEME["bronze"]


def next_tier_threshold(tier: str) -> Optional[int]:
    for i, (name, lo, _hi) in enumerate(TIER_BANDS):
        if name == tier:
            # Walk back through bands to find the next higher one
            if i == 0:
                return None  # already at top
            return TIER_BANDS[i - 1][1]
    return None


async def compute_ambassador_tier(db, user_id: str) -> dict:
    """Reads PointsService balance, returns tier + theme + next threshold.
    Idempotent.  Caches on the user doc."""
    try:
        from services.points_service import PointsService
        svc = PointsService(db)
        bal = await svc.get_balance(user_id)
        balance = int(bal or 0) if isinstance(bal, int) else int(
            (bal or {}).get("balance") or 0)
    except Exception:
        # Fallback to legacy bigcoin_balance if PointsService unavailable.
        u = await db.users.find_one({"user_id": user_id},
                                                  {"bigcoin_balance": 1}) or {}
        balance = int(u.get("bigcoin_balance") or 0)

    tier = tier_for_balance(balance)
    theme = tier_theme(tier)
    next_thr = next_tier_threshold(tier)
    out = {
        "user_id":          user_id,
        "balance":          balance,
        "tier":              tier,
        "label":              theme["label"],
        "color_hex":      theme["hex"],
        "next_threshold": next_thr,
        "progress_to_next_pct": (None if next_thr is None else round(
            min(100.0,
                  100.0 * max(0, balance) / max(1, next_thr)), 1)),
        "updated_at":      datetime.now(timezone.utc).isoformat(),
    }
    # Cache on user doc (best-effort).
    try:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"ambassador_tier": tier,
                          "ambassador_tier_label": theme["label"],
                          "ambassador_tier_updated_at": datetime.now(timezone.utc)}})
    except Exception:
        pass
    return out


__all__ = [
    "TIER_BANDS", "TIER_THEME",
    "tier_for_balance", "tier_theme",
    "next_tier_threshold", "compute_ambassador_tier",
]
