"""Phase 13c — Cohort definitions + DSL resolver.

A cohort = saved audience filter. `filter_dsl` is a JSON tree:

  {"op": "and|or|not",
    "conditions": [
      {"field": "<dotted.path>", "op": "<op>", "value": <any>},
      {"op": "or", "conditions": [...]}   # nested group
    ]}

Supported ops on leaves:
  eq, ne, in, nin, gte, gt, lte, lt, between, contains, exists

Supported fields (whitelist — never let an admin write to arbitrary
collection paths through the DSL):
  - user fields: subscription.status, market, premium_tier, is_premium,
    preference_vector.city, preferences.languages,
    ambassador_level, friend_count
  - virtual (computed): playback_logs.count_7d, playback_logs.count_30d,
    lobby_count_7d, churn_score, churn_band

`resolve_cohort(db, filter_dsl, *, limit=5000)` returns a sorted list of
matching user_ids. Caches resolved size for 1h.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

logger = logging.getLogger("bigfm.cohorts")

ALLOWED_FIELDS = {
    # Plain user-doc fields (passed straight through to the Mongo query)
    "subscription.status": "users",
    "market": "users",
    "premium_tier": "users",
    "is_premium": "users",
    "preference_vector.city": "users",
    "preferences.languages": "users",
    "ambassador_level": "users",
    "friend_count": "users",
    # Phase 13d tidy-up — short aliases for city / country.
    "city": "users_alias_city",
    "country": "users_alias_country",
    # Virtual / derived — handled below in `_apply_virtual`.
    "playback_logs.count_7d": "virtual",
    "playback_logs.count_30d": "virtual",
    "lobby_count_7d": "virtual",
    "churn_score": "virtual",
    "churn_band": "virtual",
}

LEAF_OPS = {"eq", "ne", "in", "nin", "gte", "gt", "lte", "lt",
                  "between", "contains", "exists"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _leaf_to_mongo(field: str, op: str, value: Any) -> dict:
    """Convert one leaf condition to a Mongo predicate {field: <expr>}."""
    if op == "eq":
        return {field: value}
    if op == "ne":
        return {field: {"$ne": value}}
    if op == "in":
        return {field: {"$in": value if isinstance(value, list) else [value]}}
    if op == "nin":
        return {field: {"$nin": value if isinstance(value, list) else [value]}}
    if op == "gte":
        return {field: {"$gte": value}}
    if op == "gt":
        return {field: {"$gt": value}}
    if op == "lte":
        return {field: {"$lte": value}}
    if op == "lt":
        return {field: {"$lt": value}}
    if op == "between":
        lo, hi = (value or [None, None])[:2]
        return {field: {"$gte": lo, "$lte": hi}}
    if op == "contains":
        # array contains a value
        return {field: value}
    if op == "exists":
        return {field: {"$exists": bool(value)}}
    raise ValueError(f"unknown leaf op: {op}")


def _walk_dsl(node: dict) -> tuple[dict, list[dict]]:
    """Walks the DSL tree. Returns (mongo_query, virtual_conditions).
    virtual_conditions are evaluated after the Mongo find().
    """
    if not isinstance(node, dict):
        raise ValueError("dsl node must be a dict")
    op = (node.get("op") or "and").lower()
    if op in ("and", "or", "not"):
        children = node.get("conditions") or []
        if not isinstance(children, list):
            raise ValueError("conditions must be a list")
        sub_mongos: list[dict] = []
        sub_virtuals: list[dict] = []
        for c in children:
            m, v = _walk_dsl(c)
            if m:
                sub_mongos.append(m)
            sub_virtuals.extend(v)
        if op == "and":
            mongo = {"$and": sub_mongos} if sub_mongos else {}
        elif op == "or":
            mongo = {"$or": sub_mongos} if sub_mongos else {}
        else:  # not
            mongo = {"$nor": sub_mongos} if sub_mongos else {}
        return mongo, sub_virtuals
    # Leaf
    field = node.get("field")
    leaf_op = (node.get("op") or "eq").lower()
    value = node.get("value")
    if not field or field not in ALLOWED_FIELDS:
        raise ValueError(f"field not allowed: {field}")
    if leaf_op not in LEAF_OPS:
        raise ValueError(f"op not allowed: {leaf_op}")
    if ALLOWED_FIELDS[field] == "users":
        return _leaf_to_mongo(field, leaf_op, value), []
    if ALLOWED_FIELDS[field] == "users_alias_city":
        # Map short alias `city` → real user doc field `preference_vector.city`.
        return _leaf_to_mongo("preference_vector.city", leaf_op, value), []
    if ALLOWED_FIELDS[field] == "users_alias_country":
        # Map short alias `country` → `market` (BigFM stores ISO-2 there).
        return _leaf_to_mongo("market", leaf_op, value), []
    # Virtual leaf — collect; evaluated after Mongo find.
    return {}, [{"field": field, "op": leaf_op, "value": value}]


async def _apply_virtual(db, user_ids: list[str],
                                    conditions: list[dict]) -> list[str]:
    """Filter user_ids by virtual/derived conditions."""
    if not conditions or not user_ids:
        return user_ids
    keep = set(user_ids)
    for cond in conditions:
        field = cond["field"]
        op = cond["op"]
        value = cond["value"]
        cutoff_7d = _now() - timedelta(days=7)
        cutoff_30d = _now() - timedelta(days=30)
        per_user: dict[str, Any] = {}
        if field in ("playback_logs.count_7d",
                          "playback_logs.count_30d"):
            cutoff = cutoff_7d if field.endswith("7d") else cutoff_30d
            async for doc in db.playback_logs.aggregate([
                    {"$match": {"user_id": {"$in": list(keep)},
                                      "event": "play_start",
                                      "timestamp": {"$gte": cutoff}}},
                    {"$group": {"_id": "$user_id",
                                      "count": {"$sum": 1}}}]):
                per_user[doc["_id"]] = doc["count"]
            # Users without rows count as 0
            for uid in list(keep):
                per_user.setdefault(uid, 0)
        elif field == "lobby_count_7d":
            async for doc in db.lobby_events.aggregate([
                    {"$match": {"user_id": {"$in": list(keep)},
                                      "event_type": "join",
                                      "created_at": {"$gte": cutoff_7d}}},
                    {"$group": {"_id": "$user_id",
                                      "count": {"$sum": 1}}}]):
                per_user[doc["_id"]] = doc["count"]
            for uid in list(keep):
                per_user.setdefault(uid, 0)
        elif field in ("churn_score", "churn_band"):
            key = "score" if field == "churn_score" else "band"
            async for doc in db.churn_scores.find(
                    {"user_id": {"$in": list(keep)}},
                    {"user_id": 1, key: 1, "_id": 0}):
                per_user[doc["user_id"]] = doc.get(key)
            for uid in list(keep):
                per_user.setdefault(uid, None)
        else:
            continue
        # Now apply the leaf op to per_user
        def _match(actual: Any) -> bool:
            if op == "eq": return actual == value
            if op == "ne": return actual != value
            if op == "in": return actual in (value or [])
            if op == "nin": return actual not in (value or [])
            if op == "gte": return actual is not None and actual >= value
            if op == "gt": return actual is not None and actual > value
            if op == "lte": return actual is not None and actual <= value
            if op == "lt": return actual is not None and actual < value
            if op == "between":
                lo, hi = (value or [None, None])[:2]
                return (actual is not None and actual >= lo
                            and actual <= hi)
            if op == "exists":
                return (actual is not None) == bool(value)
            return False
        keep = {uid for uid in keep if _match(per_user.get(uid))}
    return sorted(keep)


async def resolve_cohort(db, filter_dsl: dict, *,
                                  limit: int = 5000) -> list[str]:
    """Returns the list of matching user_ids."""
    if not filter_dsl:
        return []
    mongo_q, virtuals = _walk_dsl(filter_dsl)
    base_ids: list[str] = []
    async for u in db.users.find(
            mongo_q or {}, {"user_id": 1, "_id": 0}).limit(limit):
        if u.get("user_id"):
            base_ids.append(u["user_id"])
    return await _apply_virtual(db, base_ids, virtuals)


# ─── CRUD helpers (used by the admin routes) ──────────────────────────
async def ensure_cohort_indexes(db) -> None:
    await db.audience_cohorts.create_index("id", unique=True)


async def upsert_cohort_size(db, cohort: dict) -> int:
    """Recompute audience size + persist; respects the 1h cache."""
    last = cohort.get("last_computed_at")
    if last and (_now() - _aware(last) < timedelta(hours=1)):
        return int(cohort.get("computed_audience_size") or 0)
    ids = await resolve_cohort(db, cohort.get("filter_dsl") or {},
                                          limit=100_000)
    size = len(ids)
    await db.audience_cohorts.update_one(
        {"id": cohort["id"]},
        {"$set": {"computed_audience_size": size,
                    "last_computed_at": _now()}})
    return size


def _aware(dt):
    if dt is None:
        return _now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
