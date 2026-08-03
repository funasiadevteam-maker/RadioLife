"""Phase 39 Session 7 — Hard-delete sweep for soft-deleted users.

When a user has been soft-deleted for >= 30 days, this sweep scrubs
their PII across every collection while anonymizing audit log entries
(legal-required retention).
"""
from __future__ import annotations
import logging
import hashlib
from datetime import datetime, timedelta, timezone

log = logging.getLogger("bigfm.hard_delete")

HARD_DELETE_DAYS = 30

# Collections holding user-tied PII rows that get fully deleted.
PII_DELETE_COLLECTIONS = [
    "UserTravelEvents",
    "UserFrequentPlaces",
    "UserTrips",
    "UserRoutePatterns",
    "UserBusinessVisits",
    "plays",
    "wallet_items",
    "game_winners",
    "game_redemptions",
    "radio_sessions",
    "persona_chat_log",
]

# Audit-trail collections — user_id anonymized but row preserved.
AUDIT_ANONYMIZE_COLLECTIONS = [
    "LocationPrivacyAuditLogs",
    "AdvertiserAggregateAuditLogs",
]


def _anon_id(user_id: str) -> str:
    return "deleted_" + hashlib.sha1(user_id.encode()).hexdigest()[:12]


async def hard_delete_user(db, user_id: str) -> dict:
    """Cascade scrub for one user.  Returns row counts per collection."""
    counts: dict[str, int] = {}
    for coll in PII_DELETE_COLLECTIONS:
        try:
            r = await db[coll].delete_many({"user_id": user_id})
            counts[coll] = r.deleted_count
        except Exception as e:
            log.warning("[hard-delete] %s failed: %s", coll, e)
            counts[coll] = -1
    anon = _anon_id(user_id)
    for coll in AUDIT_ANONYMIZE_COLLECTIONS:
        try:
            r = await db[coll].update_many(
                {"user_id": user_id},
                {"$set": {"user_id": anon,
                          "anonymized_at": datetime.now(timezone.utc).isoformat()}})
            counts[coll + "_anonymized"] = r.modified_count
        except Exception as e:
            log.warning("[hard-delete] %s anonymize failed: %s", coll, e)
            counts[coll + "_anonymized"] = -1
    # Also anonymize the advertiser_user_id field on AdvertiserAggregateAuditLogs.
    try:
        r = await db.AdvertiserAggregateAuditLogs.update_many(
            {"advertiser_user_id": user_id},
            {"$set": {"advertiser_user_id": anon}})
        counts["AdvertiserAggregateAuditLogs_advertiser_anon"] = r.modified_count
    except Exception as e:
        log.warning("[hard-delete] adv_audit failed: %s", e)

    # Finally — wipe the user document itself, preserving the audit
    # trail by writing a tombstone with the anonymized id.
    try:
        await db.users.delete_one({"user_id": user_id})
        await db.users_tombstones.insert_one({
            "_id":                       anon,
            "original_anon_id":   anon,
            "hard_deleted_at":  datetime.now(timezone.utc).isoformat()})
        counts["users_deleted"] = 1
    except Exception as e:
        log.warning("[hard-delete] user delete failed: %s", e)
        counts["users_deleted"] = -1
    log.info("[hard-delete] user=%s anon=%s counts=%s", user_id, anon, counts)
    return counts


async def sweep_hard_deletes(db) -> dict:
    """Find soft-deleted users past the 30-day recovery window and scrub."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=HARD_DELETE_DAYS)).isoformat()
    n_swept = 0
    per_user: list[dict] = []
    cur = db.users.find({
        "deleted_at": {"$exists": True, "$ne": None, "$lt": cutoff},
        "hard_deleted_at": {"$exists": False}})
    async for u in cur:
        res = await hard_delete_user(db, u["user_id"])
        per_user.append({"user_id": u["user_id"], "counts": res})
        n_swept += 1
    return {"users_hard_deleted": n_swept, "per_user": per_user}
