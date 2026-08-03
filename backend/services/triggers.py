"""Phase 13c — Behavioral & contextual triggers.

Each trigger is `async def <name>(db, **params) -> list[str]` returning
matching user_ids. The admin `/triggers/dry_run` route + the campaign
scheduler both call into this registry. Caches not used here — the
caller decides batch cadence.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.triggers")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def played_artist_x_times(db, *, artist_id: str,
                                              count: Optional[int] = None,
                                              x: Optional[int] = None,
                                              days: int = 14,
                                              **_ignored) -> list[str]:
    # 13c tidy-up: accept either `count` (preferred) or alias `x`.
    n = int(count if count is not None else (x if x is not None else 3))
    cutoff = _now() - timedelta(days=days)
    out: list[str] = []
    async for d in db.playback_logs.aggregate([
            {"$match": {"event": "play_start", "artist_id": artist_id,
                              "timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gte": n}}}]):
        if d["_id"]:
            out.append(d["_id"])
    return out


async def skipped_genre_recently(db, *, genre: str,
                                              skip_rate_pct: float = 50.0,
                                              days: int = 7) -> list[str]:
    cutoff = _now() - timedelta(days=days)
    out: list[str] = []
    async for d in db.playback_logs.aggregate([
            {"$match": {"genre": genre,
                              "timestamp": {"$gte": cutoff},
                              "event": {"$in": ["play_start", "skip"]}}},
            {"$group": {"_id": "$user_id",
                              "starts": {"$sum": {"$cond": [
                                  {"$eq": ["$event", "play_start"]},
                                  1, 0]}},
                              "skips": {"$sum": {"$cond": [
                                  {"$eq": ["$event", "skip"]},
                                  1, 0]}}}}]):
        starts = max(1, d.get("starts", 0))
        rate = (d.get("skips", 0) / starts) * 100.0
        if rate >= skip_rate_pct:
            out.append(d["_id"])
    return out


async def joined_lobby_no_chat(db, *, days: int = 14) -> list[str]:
    cutoff = _now() - timedelta(days=days)
    joiners: dict[str, int] = {}
    async for d in db.lobby_events.aggregate([
            {"$match": {"event_type": "join",
                              "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}}]):
        joiners[d["_id"]] = d["n"]
    if not joiners:
        return []
    chatters: set[str] = set()
    async for d in db.lobby_events.aggregate([
            {"$match": {"event_type": "chat",
                              "user_id": {"$in": list(joiners.keys())},
                              "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id"}}]):
        chatters.add(d["_id"])
    return [uid for uid in joiners if uid not in chatters]


async def claimed_coupon_no_redeem(db, *, days: int = 14) -> list[str]:
    cutoff = _now() - timedelta(days=days)
    out: list[str] = []
    async for c in db.coupons.find(
            {"claimed_at": {"$gte": cutoff},
              "status": "claimed"},
            {"user_id": 1, "_id": 0}):
        if c.get("user_id"):
            out.append(c["user_id"])
    return sorted(set(out))


async def commute_window_active(db, *, city: str = None,
                                            radius_hours: float = 2.0) -> list[str]:
    """Users whose saved commute window starts or ends within ±radius_hours
    of *current local hour*. Simplistic — UTC for now; future versions
    can localize per-user.
    """
    now = _now()
    cur_hour = now.hour
    out: list[str] = []
    q: dict = {"saved_commute": {"$exists": True}}
    if city:
        q["preference_vector.city"] = city
    async for u in db.users.find(q, {"user_id": 1, "saved_commute": 1}):
        sc = u.get("saved_commute") or {}
        start_h = sc.get("start_hour")
        end_h = sc.get("end_hour")
        hit = False
        for h in (start_h, end_h):
            if h is None: continue
            diff = abs((int(h) - cur_hour + 12) % 24 - 12)
            if diff <= radius_hours:
                hit = True; break
        if hit:
            out.append(u["user_id"])
    return out


async def friends_in_lobby(db) -> list[str]:
    """Users with ≥1 referred friend currently in an `active` lobby."""
    # Active lobby participants right now.
    active_uids: set[str] = set()
    async for l in db.lobbies.find(
            {"status": "active"}, {"participants": 1, "host_user_id": 1}):
        if l.get("host_user_id"):
            active_uids.add(l["host_user_id"])
        for p in (l.get("participants") or []):
            if isinstance(p, dict) and p.get("user_id"):
                active_uids.add(p["user_id"])
            elif isinstance(p, str):
                active_uids.add(p)
    if not active_uids:
        return []
    # For each user, do they have a friend in `active_uids`?
    out: list[str] = []
    async for u in db.users.find(
            {"friend_ids": {"$elemMatch": {"$in": list(active_uids)}}},
            {"user_id": 1, "_id": 0}):
        out.append(u["user_id"])
    return out


# ─── registry consumed by the admin dry-run endpoint ──────────────────
TRIGGERS = {
    "played_artist_x_times": played_artist_x_times,
    "skipped_genre_recently": skipped_genre_recently,
    "joined_lobby_no_chat": joined_lobby_no_chat,
    "claimed_coupon_no_redeem": claimed_coupon_no_redeem,
    "commute_window_active": commute_window_active,
    "friends_in_lobby": friends_in_lobby,
}


REASONING_TEMPLATES = {
    "played_artist_x_times":
        "Users who played artist `{artist_id}` ≥{count} times "
        "in last {days}d",
    "skipped_genre_recently":
        "Users with skip rate ≥{skip_rate_pct}% on genre `{genre}` "
        "in last {days}d",
    "joined_lobby_no_chat":
        "Users who joined a lobby in last {days}d but sent zero chat "
        "messages",
    "claimed_coupon_no_redeem":
        "Users who claimed a coupon in last {days}d but it was never "
        "redeemed by the partner",
    "commute_window_active":
        "Users with a saved commute window starting/ending within "
        "±{radius_hours}h of now (city={city})",
    "friends_in_lobby":
        "Users with ≥1 friend currently in an active lobby",
}


async def run_trigger(db, name: str, params: dict) -> dict:
    fn = TRIGGERS.get(name)
    if not fn:
        raise ValueError(f"unknown_trigger:{name}")
    uids = await fn(db, **(params or {}))
    # 13c tidy-up: normalize `x` alias → `count` for the reasoning text.
    p_for_text = dict(params or {})
    if name == "played_artist_x_times":
        if "count" not in p_for_text and "x" in p_for_text:
            p_for_text["count"] = p_for_text["x"]
    reasoning = REASONING_TEMPLATES.get(name, name).format(
        **({"artist_id": "?", "count": "?", "days": "?",
              "skip_rate_pct": "?", "genre": "?", "city": "?",
              "radius_hours": "?"} | p_for_text))
    return {"audience_size": len(uids),
              "sample_user_ids": uids[:10],
              "reasoning": reasoning}
