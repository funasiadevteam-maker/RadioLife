"""Phase 41M.B — Station-scoped fan badge engine.

Separate from `services/badge_engine.py` (global Passport badges) — this
module manages **station-scoped** badges: a fan can be a Loyal Listener
on Station A AND on Station B independently. Collection:
`user_station_badges`.

Grants are fire-and-forget — every call is wrapped in try/except by the
caller and any exception is logged + swallowed so the originating
mutation (listen leave, reaction, comment, follow) never blocks.

Grants are idempotent via the unique compound index
`(user_id, station_id, badge_type)`.

Five badge types (P41M.B spec):
  * loyal_listener  — ≥50 listen-minutes lifetime on this station
                       (aggregated from `listener_session_archive.duration_sec`)
  * top_reactor     — ≥10 reactions on this station's posts/comments
  * comment_champion— ≥5 comments on this station's posts
  * first_follower  — among the first 10 followers (ordered by followed_at)
  * vip             — premium subscriber AND followed station
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.station_badge_engine")

BADGE_TYPES = {
    "loyal_listener", "top_reactor", "comment_champion",
    "first_follower", "vip",
}

BADGE_META = {
    "loyal_listener":   {"label": "Loyal Listener",
                          "icon":  "headphones",
                          "criteria_text": "Listened 50+ minutes on this station"},
    "top_reactor":      {"label": "Top Reactor",
                          "icon":  "flame",
                          "criteria_text": "Reacted 10+ times on this station"},
    "comment_champion": {"label": "Comment Champion",
                          "icon":  "message-circle",
                          "criteria_text": "Commented 5+ times on this station"},
    "first_follower":   {"label": "First 10 Follower",
                          "icon":  "star",
                          "criteria_text": "Among the first 10 followers"},
    "vip":              {"label": "VIP",
                          "icon":  "crown",
                          "criteria_text": "Premium subscriber + station follower"},
}

# Thresholds — single source of truth.
LOYAL_LISTENER_MIN_MINUTES = 50
TOP_REACTOR_MIN_REACTIONS  = 10
COMMENT_CHAMPION_MIN       = 5
FIRST_FOLLOWER_MAX_RANK    = 10


def _now() -> datetime: return datetime.now(timezone.utc)


async def ensure_station_badge_indexes(db) -> None:
    try:
        await db.user_station_badges.create_index(
            [("user_id", 1), ("station_id", 1), ("badge_type", 1)],
            unique=True, name="user_station_badge_unique")
        await db.user_station_badges.create_index(
            [("station_id", 1), ("badge_type", 1)],
            name="badge_by_station_type")
        await db.user_station_badges.create_index(
            [("user_id", 1), ("granted_at", -1)],
            name="badge_by_user_recent")
    except Exception as e:
        logger.warning("[station_badge_engine] index ensure: %s", e)


# ─── Signal counters ──────────────────────────────────────────────────

async def _listen_minutes(db, user_id: str, station_id: str) -> int:
    pipe = [
        {"$match": {"user_id": user_id, "station_id": station_id}},
        {"$group": {"_id": None, "total_sec":
                    {"$sum": {"$ifNull": ["$duration_sec", 0]}}}},
    ]
    async for row in db.listener_session_archive.aggregate(pipe):
        return int((row.get("total_sec") or 0) / 60)
    return 0


async def _reaction_count(db, user_id: str, station_slug: str) -> int:
    """Reactions on station posts + comments. Reactions are stored in
    `station_reactions` and reference `target_type` + `target_id`.
    To scope by station we join via the parent post/comment slug."""
    # Posts belonging to this station:
    post_ids = await db.station_posts.distinct(
        "post_id", {"station_slug": station_slug})
    if post_ids:
        pcount = await db.station_reactions.count_documents({
            "user_id": user_id, "target_type": "post",
            "target_id": {"$in": post_ids}})
    else:
        pcount = 0
    comment_ids = await db.station_comments.distinct(
        "comment_id", {"station_slug": station_slug})
    if comment_ids:
        ccount = await db.station_reactions.count_documents({
            "user_id": user_id, "target_type": "comment",
            "target_id": {"$in": comment_ids}})
    else:
        ccount = 0
    return pcount + ccount


async def _comment_count(db, user_id: str, station_slug: str) -> int:
    return await db.station_comments.count_documents({
        "station_slug": station_slug,
        "author_id":    user_id,
        "deleted_at":   None,
    })


async def _follower_rank(db, user_id: str, station_id: str) -> Optional[int]:
    """1-indexed rank of this user among followers of this station,
    ordered by followed_at ascending. Returns None if not a follower."""
    cursor = db.station_followers.find(
        {"station_id": station_id},
        {"user_id": 1, "followed_at": 1, "_id": 0},
    ).sort("followed_at", 1).limit(FIRST_FOLLOWER_MAX_RANK)
    rank = 0
    async for row in cursor:
        rank += 1
        if row.get("user_id") == user_id:
            return rank
    return None


async def _is_premium(db, user_id: str) -> bool:
    u = await db.users.find_one({"user_id": user_id},
                                {"premium_active": 1, "premium": 1,
                                 "subscription_status": 1, "_id": 0})
    if not u:
        return False
    return bool(u.get("premium_active") or u.get("premium")
                or u.get("subscription_status") in ("active", "trialing"))


async def _is_follower(db, user_id: str, station_id: str) -> bool:
    return bool(await db.station_followers.find_one(
        {"user_id": user_id, "station_id": station_id}))


# ─── Grant ─────────────────────────────────────────────────────────────

async def _grant(db, *, user_id: str, station_id: str, station_slug: str,
                  badge_type: str, payload: dict) -> bool:
    """Idempotent grant. Returns True if a NEW badge was inserted."""
    key = {"user_id": user_id, "station_id": station_id,
           "badge_type": badge_type}
    existing = await db.user_station_badges.find_one(key, {"_id": 1})
    if existing:
        return False
    try:
        await db.user_station_badges.insert_one({
            **key,
            "station_slug": station_slug,
            "granted_at":   _now(),
            "payload":      payload,
        })
        return True
    except Exception as e:
        # Duplicate key — race condition, idempotency holds.
        logger.debug("[station_badge_engine] grant race for %s/%s/%s: %s",
                      user_id, station_id, badge_type, e)
        return False


async def evaluate_and_grant_badges(db, *, user_id: str,
                                     station_id: str,
                                     station_slug: Optional[str] = None,
                                     only_types: Optional[set] = None,
                                     ) -> list[dict]:
    """Re-count the relevant signals and idempotently grant any missing
    badges this user qualifies for on this station. Returns the list of
    newly-granted badge docs (empty if no new grants).

    `only_types` lets the caller scope evaluation (e.g. listen_leave
    only needs to check `loyal_listener`).
    """
    if station_slug is None:
        s = await db.community_radio_stations.find_one(
            {"_id": station_id}, {"slug": 1, "_id": 0})
        station_slug = (s or {}).get("slug") or station_id

    types = only_types or BADGE_TYPES
    newly: list[dict] = []

    if "loyal_listener" in types:
        minutes = await _listen_minutes(db, user_id, station_id)
        if minutes >= LOYAL_LISTENER_MIN_MINUTES:
            if await _grant(db, user_id=user_id, station_id=station_id,
                             station_slug=station_slug,
                             badge_type="loyal_listener",
                             payload={"listen_minutes": minutes,
                                      "threshold": LOYAL_LISTENER_MIN_MINUTES}):
                newly.append({"badge_type": "loyal_listener",
                               "listen_minutes": minutes})

    if "top_reactor" in types:
        reactions = await _reaction_count(db, user_id, station_slug)
        if reactions >= TOP_REACTOR_MIN_REACTIONS:
            if await _grant(db, user_id=user_id, station_id=station_id,
                             station_slug=station_slug,
                             badge_type="top_reactor",
                             payload={"reactions": reactions,
                                      "threshold": TOP_REACTOR_MIN_REACTIONS}):
                newly.append({"badge_type": "top_reactor",
                               "reactions": reactions})

    if "comment_champion" in types:
        comments = await _comment_count(db, user_id, station_slug)
        if comments >= COMMENT_CHAMPION_MIN:
            if await _grant(db, user_id=user_id, station_id=station_id,
                             station_slug=station_slug,
                             badge_type="comment_champion",
                             payload={"comments": comments,
                                      "threshold": COMMENT_CHAMPION_MIN}):
                newly.append({"badge_type": "comment_champion",
                               "comments": comments})

    # first_follower + vip both require follower status — short-circuit
    # before the rank query if the user isn't following.
    is_follower = await _is_follower(db, user_id, station_id) \
        if ("first_follower" in types or "vip" in types) else False

    if "first_follower" in types and is_follower:
        rank = await _follower_rank(db, user_id, station_id)
        if rank is not None and rank <= FIRST_FOLLOWER_MAX_RANK:
            if await _grant(db, user_id=user_id, station_id=station_id,
                             station_slug=station_slug,
                             badge_type="first_follower",
                             payload={"rank": rank,
                                      "max_rank": FIRST_FOLLOWER_MAX_RANK}):
                newly.append({"badge_type": "first_follower", "rank": rank})

    if "vip" in types and is_follower:
        if await _is_premium(db, user_id):
            if await _grant(db, user_id=user_id, station_id=station_id,
                             station_slug=station_slug,
                             badge_type="vip",
                             payload={"premium": True, "follower": True}):
                newly.append({"badge_type": "vip"})

    return newly


async def grant_safe(db, **kwargs) -> None:
    """Fire-and-forget wrapper. Swallows + logs all exceptions so the
    originating mutation (reaction/comment/follow/listen) never blocks."""
    try:
        await evaluate_and_grant_badges(db, **kwargs)
    except Exception as e:
        logger.warning("[station_badge_engine] grant_safe failed for "
                       "user=%s station=%s: %s",
                       kwargs.get("user_id"),
                       kwargs.get("station_id"), e)


def serialize_badge(doc: dict) -> dict:
    """Strip Mongo _id and attach BADGE_META for the frontend."""
    bt = doc.get("badge_type")
    meta = BADGE_META.get(bt) or {}
    granted = doc.get("granted_at")
    if isinstance(granted, datetime):
        granted = granted.isoformat()
    return {
        "badge_type":    bt,
        "label":         meta.get("label", bt),
        "icon":          meta.get("icon"),
        "criteria_text": meta.get("criteria_text"),
        "station_id":    doc.get("station_id"),
        "station_slug":  doc.get("station_slug"),
        "granted_at":    granted,
        "payload":       doc.get("payload") or {},
    }
