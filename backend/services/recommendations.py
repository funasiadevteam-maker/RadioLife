"""Phase 18 UI-cleanup batch — user recommendations + favorites.

Centralises ranking of channels + games for the autoplay suggestion
endpoint, the home-page recommendation cards, and the bottom-bar quick
strip.  Mongo-only, no Redis.  In-memory cache keyed by `user_id` with
24h TTL.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional, List

# ─── In-memory cache: user_id → (computed_at, payload) ─────────────────
_LISTENING_CACHE: dict = {}
_TTL_SEC = 24 * 60 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Helpers ──────────────────────────────────────────────────────────
def _hour_bucket(dt: datetime) -> tuple[int, int]:
    """(day_of_week, hour_of_day) — Mon=0, Sun=6."""
    return (dt.weekday(), dt.hour)


def _bucket_neighbors(b: tuple[int, int]) -> set[tuple[int, int]]:
    """±1 hour wrap-around for the time bucket."""
    dow, hr = b
    return {
        (dow,                    hr),
        (dow,                    (hr - 1) % 24),
        (dow,                    (hr + 1) % 24),
    }


def _safe_dt(d) -> datetime:
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return _now()


async def _market_for_user(db, user_id: str) -> Optional[str]:
    u = await db.users.find_one({"user_id": user_id})
    return (u or {}).get("market")


# ─── Profile (cached) ────────────────────────────────────────────────
async def _user_listening_profile(db, user_id: str, force: bool = False) -> dict:
    """Aggregate the user's last 30d of plays into (dow, hour) → channel → count.
    Caches in-memory for 24h.  Triggers a fresh compute if `force=True`
    or the cache entry is older than the TTL.
    """
    if not force:
        e = _LISTENING_CACHE.get(user_id)
        if e and (_now() - e[0]).total_seconds() < _TTL_SEC:
            return e[1]
    since = _now() - timedelta(days=30)
    by_bucket: dict[tuple[int, int], dict[str, int]] = {}
    overall:    dict[str, int]                              = {}
    minutes:    dict[str, float]                            = {}
    last_seen:  dict[str, datetime]                         = {}
    cursor = db.playback_logs.find(
        {"user_id": user_id, "started_at": {"$gte": since}},
        {"channel_slug": 1, "started_at": 1, "duration_sec": 1},
    )
    async for row in cursor:
        slug = row.get("channel_slug") or row.get("channel_id")
        if not slug:
            continue
        dt = _safe_dt(row.get("started_at"))
        b = _hour_bucket(dt)
        by_bucket.setdefault(b, {})[slug] = by_bucket.get(b, {}).get(slug, 0) + 1
        overall[slug] = overall.get(slug, 0) + 1
        minutes[slug] = minutes.get(slug, 0.0) + (row.get("duration_sec") or 0) / 60.0
        if slug not in last_seen or dt > last_seen[slug]:
            last_seen[slug] = dt
    payload = {
        "by_bucket": {f"{k[0]}-{k[1]}": v for k, v in by_bucket.items()},
        "overall":     overall,
        "minutes":    minutes,
        "last_seen":  {k: v.isoformat() for k, v in last_seen.items()},
        "user_id":     user_id,
        "computed_at": _now().isoformat(),
    }
    _LISTENING_CACHE[user_id] = (_now(), payload)
    # Persist a snapshot for cross-process visibility / debugging.
    try:
        await db.user_listening_profile.update_one(
            {"user_id": user_id},
            {"$set": {**payload, "user_id": user_id}},
            upsert=True,
        )
    except Exception:
        pass
    return payload


def _bust_listening_cache(user_id: str) -> None:
    _LISTENING_CACHE.pop(user_id, None)


# ─── Channel ranking ─────────────────────────────────────────────────
async def _market_top_channel(db, market: Optional[str]) -> Optional[str]:
    """Cheap fallback: scan everyone's last 30d for this market, return the
    most-played channel slug.  No bucket awareness — just popularity."""
    since = _now() - timedelta(days=30)
    match = {"started_at": {"$gte": since}}
    pipe = [{"$match": match},
                {"$group": {"_id": "$channel_slug", "n": {"$sum": 1}}},
                {"$sort":   {"n": -1}}, {"$limit": 50}]
    rows = await db.playback_logs.aggregate(pipe).to_list(50)
    if market:
        users_in_market = await db.users.distinct("user_id", {"market": market})
        if users_in_market:
            pipe2 = [{"$match": {"user_id": {"$in": users_in_market},
                                          "started_at": {"$gte": since}}},
                          {"$group": {"_id": "$channel_slug", "n": {"$sum": 1}}},
                          {"$sort":   {"n": -1}}, {"$limit": 5}]
            rows2 = await db.playback_logs.aggregate(pipe2).to_list(5)
            if rows2: return rows2[0]["_id"]
    if rows:
        return rows[0]["_id"]
    # Static market fallback.
    return _MARKET_DEFAULT_CHANNEL.get((market or "").lower(),
                                                            _MARKET_DEFAULT_CHANNEL["default"])


_MARKET_DEFAULT_CHANNEL = {
    "dubai":   "morning_masala",
    "dfw":      "morning_masala",
    "default": "morning_masala",
}


async def autoplay_suggestion(db, *, user_id: str,
                                              now: Optional[datetime] = None) -> dict:
    """Return the best channel for the user's CURRENT time bucket + a top-5
    list suitable for the bottom-bar quick strip.
    """
    now    = now or _now()
    market = await _market_for_user(db, user_id)
    prof   = await _user_listening_profile(db, user_id)
    bkt    = _hour_bucket(now)
    neigh  = _bucket_neighbors(bkt)
    by_b   = prof.get("by_bucket") or {}
    overall = prof.get("overall") or {}

    # 1️⃣  most-played channel for the user in (dow, hour ±1)
    weighted: dict[str, int] = {}
    for k, m in by_b.items():
        if isinstance(k, tuple):
            kk = k
        elif isinstance(k, str) and "-" in k:
            dow, hr = k.split("-", 1)
            try:    kk = (int(dow), int(hr))
            except: continue
        else:
            continue
        if kk in neigh:
            for slug, n in m.items():
                weighted[slug] = weighted.get(slug, 0) + n
    if not weighted:
        weighted = dict(overall)
    cold = not weighted
    if cold:
        top = await _market_top_channel(db, market)
        top5 = [top] if top else []
    else:
        top5_sorted = sorted(weighted.items(),
                                      key=lambda x: (-x[1],
                                                            -overall.get(x[0], 0), x[0]))
        top5 = [s for s, _ in top5_sorted[:5]]
        top  = top5[0]

    # Resolve full channel docs.
    chans = await db.channels.find({"slug": {"$in": list(set(top5))}}).to_list(20)
    chan_map = {c["slug"]: c for c in chans}
    out_top5 = []
    for s in top5:
        c = chan_map.get(s)
        if not c:
            continue
        out_top5.append({
            "channel_slug":      s,
            "channel_id":         c.get("channel_id") or c.get("id") or s,
            "name":                 c.get("name"),
            "thumbnail_url":     c.get("thumbnail_url"),
            "play_count_in_bucket": weighted.get(s, 0),
            "play_count_total":      overall.get(s, 0),
        })
    return {
        "suggested_channel_slug": top,
        "suggested_channel":         chan_map.get(top, None) and {
            "slug": top, "name": chan_map[top].get("name"),
            "thumbnail_url": chan_map[top].get("thumbnail_url"),
        },
        "top5":         out_top5,
        "is_cold_start": cold,
        "bucket":         {"dow": bkt[0], "hour": bkt[1]},
        "user_market": market,
    }


# ─── Top channel / top game cards (Home hero) ────────────────────────
async def top_channel_for_user(db, *, user_id: str) -> Optional[dict]:
    prof    = await _user_listening_profile(db, user_id)
    overall = prof.get("overall") or {}
    market  = await _market_for_user(db, user_id)
    if not overall:
        slug = await _market_top_channel(db, market)
        cold = True
    else:
        slug = max(overall.items(), key=lambda x: x[1])[0]
        cold = False
    if not slug:
        return None
    c = await db.channels.find_one({"slug": slug})
    if not c:
        return None
    minutes_30d = (prof.get("minutes") or {}).get(slug, 0.0)
    last_seen   = (prof.get("last_seen") or {}).get(slug)
    return {
        "channel_id":        c.get("channel_id") or c.get("id") or slug,
        "slug":               slug,
        "name":                c.get("name"),
        "thumbnail_url":   c.get("thumbnail_url"),
        "minutes_listened_30d": round(minutes_30d, 1),
        "last_played_at":  last_seen,
        "cold_start":         cold,
    }


async def top_game_for_user(db, *, user_id: str) -> Optional[dict]:
    since   = _now() - timedelta(days=30)
    pipe = [{"$match": {"user_id": user_id, "started_at": {"$gte": since},
                                  "status":    "completed"}},
                {"$group": {"_id": "$campaign_id",
                                    "n":    {"$sum": 1},
                                    "last": {"$max": "$started_at"}}},
                {"$sort":  {"n": -1}}, {"$limit": 1}]
    rows = await db.game_sessions.aggregate(pipe).to_list(1)
    cold = False
    if not rows:
        # Cold start: globally most-played game.
        pipe2 = [{"$match": {"started_at": {"$gte": since},
                                          "status":    "completed"}},
                      {"$group": {"_id": "$campaign_id", "n": {"$sum": 1}}},
                      {"$sort":  {"n": -1}}, {"$limit": 1}]
        rows = await db.game_sessions.aggregate(pipe2).to_list(1)
        cold = True
    if not rows:
        # Nothing has ever been played — fall back to any active campaign.
        camp = await db.game_campaigns.find_one(
            {"status": {"$in": ["active", "live"]}})
        if not camp:
            return None
        return {"game_id":   camp.get("campaign_id"),
                  "campaign_id": camp.get("campaign_id"),
                  "template_id": camp.get("template_id"),
                  "name":         camp.get("title") or "BigFM games",
                  "icon_url":    None,
                  "last_played_at": None, "play_count": 0,
                  "cold_start": True}
    row  = rows[0]
    camp = await db.game_campaigns.find_one({"campaign_id": row["_id"]})
    if not camp:
        return None
    return {
        "game_id":         camp.get("campaign_id"),
        "campaign_id":    camp.get("campaign_id"),
        "template_id":   camp.get("template_id"),
        "name":              camp.get("title"),
        "icon_url":         camp.get("sponsor_logo_url"),
        "last_played_at": row.get("last").isoformat() if row.get("last") else None,
        "play_count":     int(row["n"]),
        "cold_start":      cold,
    }


# ─── Favorites ───────────────────────────────────────────────────────
FAVORITES_CAP = 8


async def list_favorites(db, *, user_id: str) -> list[dict]:
    u = await db.users.find_one({"user_id": user_id},
                                              {"favorite_channel_slugs": 1})
    slugs = (u or {}).get("favorite_channel_slugs") or []
    if not slugs:
        return []
    chans = await db.channels.find({"slug": {"$in": slugs}}).to_list(20)
    by = {c["slug"]: c for c in chans}
    out = []
    for s in slugs:
        c = by.get(s)
        if not c:
            continue
        out.append({"channel_slug": s,
                        "channel": {"slug": s, "name": c.get("name"),
                                          "thumbnail_url": c.get("thumbnail_url"),
                                          "channel_id":     c.get("channel_id") or c.get("id") or s}})
    return out


async def add_favorite(db, *, user_id: str, channel_slug: str) -> dict:
    if not channel_slug:
        raise ValueError("channel_slug is required")
    ch = await db.channels.find_one({"slug": channel_slug})
    if not ch:
        raise LookupError("channel not found")
    u = await db.users.find_one({"user_id": user_id},
                                              {"favorite_channel_slugs": 1}) or {}
    cur = list(u.get("favorite_channel_slugs") or [])
    if channel_slug in cur:
        return {"ok": True, "added": False, "favorites": cur}
    if len(cur) >= FAVORITES_CAP:
        raise OverflowError(f"already at {FAVORITES_CAP} favorites")
    cur.append(channel_slug)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"favorite_channel_slugs": cur}},
    )
    return {"ok": True, "added": True, "favorites": cur}


async def remove_favorite(db, *, user_id: str, channel_slug: str) -> dict:
    await db.users.update_one(
        {"user_id": user_id},
        {"$pull": {"favorite_channel_slugs": channel_slug}},
    )
    return {"ok": True, "removed": True, "favorite_slug": channel_slug}
