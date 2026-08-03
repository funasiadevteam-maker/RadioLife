"""Phase 5 — Badge engine.

Two paths:
  1. `recompute_user_badges(user_id)` — on-demand check after any event that
      could unlock a badge (heartbeat, redemption, referral, game play).
  2. `cron_recompute_all()` — sweep all active users every 5min (background
      task scheduled in server.py lifespan).

Each badge has an `unlock_rule_json` like:
    {"type": "listening_hours", "value": 10}
    {"type": "streak_days", "value": 30}
    {"type": "channel_listening_hours", "channel": "party_dubai", "value": 10}
    {"type": "lifetime_bigcoin", "value": 10000}
    {"type": "successful_referrals", "value": 5}
    {"type": "coupon_saves", "value": 10}
    {"type": "game_plays", "value": 50}
    {"type": "first_listen"}
    {"type": "consecutive_friday_nightlife", "value": 4}
    {"type": "home_area_login", "area": "Karama"}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("bigfm.badges")


async def _user_listening_minutes(db, user_id: str) -> int:
    """Total credited listening minutes from listening_heartbeats."""
    pipe = [{"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$minutes_credited"}}}]
    doc = await db.listening_heartbeats.aggregate(pipe).to_list(1)
    return int(doc[0]["total"]) if doc else 0


async def _channel_listening_minutes(db, user_id: str, channel: str) -> int:
    """Sum of play_start events scoped to a channel."""
    cnt = await db.playback_logs.count_documents(
        {"user_id": user_id, "event": "play_start", "channel_slug": channel},
    )
    # Each play_start is ~3 min on average — rough estimate
    return cnt * 3


async def _successful_referrals(db, user_id: str) -> int:
    return await db.referrals.count_documents(
        {"referrer_user_id": user_id, "status": "completed"},
    )


async def _coupon_saves(db, user_id: str) -> int:
    return await db.user_wallet_items.count_documents(
        {"user_id": user_id, "item_type": "coupon"},
    )


async def _game_plays(db, user_id: str) -> int:
    return await db.game_sessions.count_documents({"user_id": user_id})


async def _ratings(db, user_id: str) -> int:
    return await db.rj_quality_votes.count_documents({"user_id": user_id})


async def _is_first_listen(db, user_id: str) -> bool:
    doc = await db.playback_logs.find_one(
        {"user_id": user_id, "event": "play_start"}, {"_id": 1},
    )
    return bool(doc)


async def _consecutive_friday_nightlife(db, user_id: str) -> int:
    """Approximate via play_start docs in friday_nightlife daypart. Returns
    the count of distinct Friday dates with at least one play_start."""
    pipe = [
        {"$match": {"user_id": user_id, "event": "play_start"}},
        {"$project": {"day": {"$dayOfWeek": "$timestamp"},
                       "date": {"$dateToString": {"format": "%Y-%m-%d",
                                                   "date": "$timestamp"}}}},
        # MongoDB $dayOfWeek: 1=Sunday ... 6=Friday
        {"$match": {"day": 6}},
        {"$group": {"_id": "$date"}},
        {"$count": "fridays"},
    ]
    doc = await db.playback_logs.aggregate(pipe).to_list(1)
    return int(doc[0]["fridays"]) if doc else 0


async def _evaluate(db, user: dict, rule: dict) -> bool:
    """Returns True if the user satisfies the badge unlock rule."""
    uid = user["user_id"]
    t = rule.get("type")
    val = rule.get("value", 0)
    if t == "first_listen":
        return await _is_first_listen(db, uid)
    if t == "listening_hours":
        m = await _user_listening_minutes(db, uid)
        return m >= val * 60
    if t == "streak_days":
        s = await db.user_streaks.find_one({"user_id": uid},
                                             {"longest_streak_days": 1, "_id": 0})
        return int((s or {}).get("longest_streak_days") or 0) >= val
    if t == "channel_listening_hours":
        m = await _channel_listening_minutes(db, uid, rule.get("channel") or "")
        return m >= val * 60
    if t == "lifetime_bigcoin":
        return int(user.get("bigcoin_lifetime_earned") or 0) >= val
    if t == "successful_referrals":
        return await _successful_referrals(db, uid) >= val
    if t == "coupon_saves":
        return await _coupon_saves(db, uid) >= val
    if t == "game_plays":
        return await _game_plays(db, uid) >= val
    if t == "ratings_count":
        return await _ratings(db, uid) >= val
    if t == "consecutive_friday_nightlife":
        return await _consecutive_friday_nightlife(db, uid) >= val
    if t == "home_area_login":
        return (user.get("home_area") or "").lower() == (rule.get("area") or "").lower()
    return False


async def recompute_user_badges(db, user_id: str) -> dict:
    """Returns {newly_unlocked: [badge_slug, ...]}. Idempotent."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return {"newly_unlocked": []}
    # Get already-unlocked
    cur = db.user_badges.find({"user_id": user_id}, {"badge_id": 1, "_id": 0})
    unlocked = set()
    async for d in cur: unlocked.add(d["badge_id"])
    # Iterate active badges
    new_badges = []
    cur = db.badges.find({"active": True})
    async for badge in cur:
        if badge["_id"] in unlocked: continue
        rule = badge.get("unlock_rule_json") or {}
        if await _evaluate(db, user, rule):
            try:
                await db.user_badges.insert_one({
                    "user_id": user_id, "badge_id": badge["_id"],
                    "unlocked_at": datetime.now(timezone.utc),
                    "displayed_on_profile": True,
                })
                new_badges.append(badge.get("slug") or badge["_id"])
            except Exception:
                pass  # duplicate
    return {"newly_unlocked": new_badges}


async def cron_recompute_all(db, limit: int = 500) -> dict:
    """Background sweep — limited to active users to keep cost bounded."""
    # Pick users who have had activity in the last 7 days (had a play_start)
    cutoff_ts = datetime.now(timezone.utc).timestamp() - 7 * 86400
    # Use a simpler heuristic: users with bigcoin transactions in last 7d
    from datetime import timedelta as _td
    cutoff = datetime.now(timezone.utc) - _td(days=7)
    pipe = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$user_id"}}, {"$limit": limit},
    ]
    cur = db.bigcoin_transactions.aggregate(pipe)
    users_processed = 0
    total_new = 0
    async for doc in cur:
        uid = doc["_id"]
        out = await recompute_user_badges(db, uid)
        users_processed += 1
        total_new += len(out["newly_unlocked"])
    return {"users_processed": users_processed, "new_badges": total_new}
