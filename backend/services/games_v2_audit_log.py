"""Phase 23 Session 5 — admin moderation taxonomy + audit log helper.

A lightweight audit-trail collection lives at `game_campaign_audit_logs`
and is written by the admin reject/approve/bulk-approve endpoints.  No
schema enforcement on Mongo; the collection is created lazily on first
insert.  Idempotency is enforced at write time (skip if an audit row
for the same campaign + action exists within the last 5 minutes).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


# Canonical reject reason taxonomy (frontend mirrors this list).
REJECT_REASON_CODES: dict[str, str] = {
    "prize_value_too_low":      "Prize value below minimum threshold",
    "prize_value_too_high":    "Prize value above category cap",
    "inventory_misallocated": "Inventory mismatch vs win-rate math",
    "targeting_too_narrow":  "Targeting filters too restrictive",
    "targeting_too_broad":    "Targeting too broad / not relevant",
    "unsafe_content":              "Creative copy / imagery flags safety review",
    "missing_assets":              "Required creative assets missing or low-res",
    "duplicate_campaign":      "Duplicate of an active campaign",
    "compliance_violation":  "Violates regulatory / promo rules",
    "other":                              "Other (free-text required)",
}


async def write_audit_log(db, *, campaign_id: str, action: str,
                                              actor_user_id: str,
                                              reason_code: Optional[str] = None,
                                              reason_notes: Optional[str] = None,
                                              extra: Optional[dict] = None) -> str:
    """Insert an audit row.  Idempotent within a 5-min window: a recent
    row for the same (campaign_id, action) tuple short-circuits.

    Returns the audit row id (or the existing row id when skipped).
    """
    coll = db.game_campaign_audit_logs
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=5)
    existing = await coll.find_one({
        "campaign_id": campaign_id,
        "action":          action,
        "timestamp":  {"$gte": cutoff},
    })
    if existing:
        return existing["audit_id"]

    import uuid
    audit_id = f"aud_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id":                  audit_id,
        "audit_id":          audit_id,
        "campaign_id": campaign_id,
        "action":              action,
        "actor_user_id": actor_user_id,
        "reason_code":  reason_code,
        "reason_notes": reason_notes,
        "extra":                  extra or {},
        "timestamp":      now,
    }
    await coll.insert_one(doc)
    return audit_id


# ----- queue-stats in-memory TTL cache --------------------------------
# Project is Mongo-only (no Redis), per `bigfm-no-postgres-no-redis`
# constraint.  In-memory cache is sufficient because the admin queue
# page is hit by a small number of admins (single-digit concurrent).
_STATS_CACHE: dict = {"value": None, "expires_at": None}
_STATS_TTL_SEC = 60


def stats_cache_get() -> Optional[dict]:
    now = datetime.now(timezone.utc)
    if (_STATS_CACHE["value"] is not None
                  and _STATS_CACHE["expires_at"]
                  and _STATS_CACHE["expires_at"] > now):
        return _STATS_CACHE["value"]
    return None


def stats_cache_set(value: dict) -> None:
    _STATS_CACHE["value"]          = value
    _STATS_CACHE["expires_at"] = (datetime.now(timezone.utc)
                                                    + timedelta(seconds=_STATS_TTL_SEC))


def stats_cache_bust() -> None:
    _STATS_CACHE["value"]          = None
    _STATS_CACHE["expires_at"] = None
