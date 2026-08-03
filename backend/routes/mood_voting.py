"""Phase 41M.A — Mood voting for stations.

Listeners cast a single mood vote per (station, track) pair (track_id
optional → station-overall vote). Switching the mood updates the
existing row (no duplicates). Aggregate is computed on read with a
60-second in-process cache.

Endpoints (all mounted at /api/stations/{slug}/…):
  POST   /mood_vote        body {track_id?, mood}  — upsert vote
  DELETE /mood_vote        ?track_id=…             — clear caller's vote
  GET    /mood_aggregate   ?window=7d|30d|all      — distribution
                                                     (per_track owner-only)

Auth: all three endpoints require auth (anon → 401). Mood voting is a
listener-engagement signal; we explicitly do NOT accept anonymous votes.

Owner mutations bust the analytics cache for the station so the
Analytics dashboard reflects new mood data right away.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user
from routes.community_stations import _visible_to as _station_visible_to


router = APIRouter(prefix="/api/stations", tags=["mood-voting"])
log = logging.getLogger("bigfm.mood_voting")

VALID_MOODS = {"chill", "hype", "sad", "party", "focus"}
WINDOW_DAYS = {"7d": 7, "30d": 30, "all": None}
AGG_CACHE_TTL_SEC = 60
MIN_VOTES_TO_REVEAL_DISTRIBUTION = 5

# (slug, window) -> (ts, payload)
_AGG_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}


def _bust_analytics(slug: str) -> None:
    try:
        from routes.station_analytics import bust_analytics_cache
        bust_analytics_cache(slug)
    except Exception:
        pass


def _bust_mood_cache(slug: str) -> None:
    for k in list(_AGG_CACHE.keys()):
        if k[0] == slug:
            _AGG_CACHE.pop(k, None)


def _now() -> datetime: return datetime.now(timezone.utc)


async def ensure_mood_voting_indexes(db) -> None:
    try:
        # Unique compound — one vote per user per (station, track).
        # track_id can be None for station-overall votes; Mongo treats
        # missing/null as the same value so the constraint still holds.
        await db.mood_votes.create_index(
            [("station_id", 1), ("track_id", 1), ("user_id", 1)],
            unique=True, name="mood_votes_one_per_user")
        await db.mood_votes.create_index(
            [("station_id", 1), ("voted_at", -1)],
            name="mood_votes_by_station_recent")
        await db.mood_votes.create_index(
            [("station_id", 1), ("track_id", 1), ("mood", 1)],
            name="mood_votes_distribution")
    except Exception as e:
        log.warning("[mood_voting] index ensure: %s", e)


async def _resolve_station(db, slug: str, user: Optional[dict]) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if not _station_visible_to(s, user, via_direct_link=True):
        raise HTTPException(404, {"code": "not_found"})
    # Keep `_id` reachable for downstream queries.
    s["_id"] = s.get("_id")
    return s


def _is_owner(station: dict, user: Optional[dict]) -> bool:
    return bool(user and station.get("owner_user_id") == user.get("user_id"))


def _window_bound(window: str) -> Optional[datetime]:
    days = WINDOW_DAYS.get(window)
    if days is None:
        return None
    return _now() - timedelta(days=days)


async def _compute_aggregate(db, *, station_id: str, slug: str,
                              since: Optional[datetime],
                              include_per_track: bool) -> dict:
    """Roll up mood_votes into station_level + per_track distributions.
    Per-track is computed regardless of `include_per_track`, but is
    redacted from the response by the caller when the viewer isn't
    the owner."""
    match: dict = {"station_id": station_id}
    if since is not None:
        match["voted_at"] = {"$gte": since}

    station_pipe = [
        {"$match": match},
        {"$group": {"_id": "$mood", "count": {"$sum": 1}}},
    ]
    station_level = {m: 0 for m in VALID_MOODS}
    async for row in db.mood_votes.aggregate(station_pipe):
        m = row["_id"]
        if m in station_level:
            station_level[m] = int(row.get("count") or 0)
    total = sum(station_level.values())

    per_track: list = []
    if include_per_track:
        pipe = [
            {"$match": {**match, "track_id": {"$ne": None}}},
            {"$group": {
                "_id":   {"track_id": "$track_id", "mood": "$mood"},
                "count": {"$sum": 1}}},
            {"$group": {
                "_id":   "$_id.track_id",
                "moods": {"$push": {"mood": "$_id.mood",
                                     "count": "$count"}},
                "total": {"$sum": "$count"}}},
            {"$sort":  {"total": -1}},
            {"$limit": 25},
        ]
        async for row in db.mood_votes.aggregate(pipe):
            distribution = {m: 0 for m in VALID_MOODS}
            for entry in row.get("moods", []):
                mm = entry.get("mood")
                if mm in distribution:
                    distribution[mm] = int(entry.get("count") or 0)
            dominant_mood, dominant_count = max(
                distribution.items(), key=lambda kv: kv[1])
            per_track.append({
                "track_id":      row["_id"],
                "distribution":  distribution,
                "dominant_mood": dominant_mood if dominant_count > 0 else None,
                "sample_count":  int(row.get("total") or 0),
            })

    return {
        "station_level":   station_level,
        "station_total":   total,
        "reveal_distribution": total >= MIN_VOTES_TO_REVEAL_DISTRIBUTION,
        "per_track":       per_track,
        "computed_at":     _now().isoformat(),
    }


@router.post("/{slug}/mood_vote")
async def cast_mood_vote(slug: str, body: dict, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    mood = (body or {}).get("mood")
    if mood not in VALID_MOODS:
        raise HTTPException(400, {"code": "validation_error",
                                   "field": "mood",
                                   "message": f"mood must be one of {sorted(VALID_MOODS)}"})
    track_id = (body or {}).get("track_id") or None
    station = await _resolve_station(db, slug, user)
    sid = station.get("station_id") or str(station.get("_id") or "")
    now = _now()

    # Upsert: replace existing vote for this (station, track, user).
    key = {"station_id": sid,
           "track_id":   track_id,
           "user_id":    user["user_id"]}
    set_doc = {
        "station_slug": slug,
        "mood":         mood,
        "voted_at":     now,
    }
    insert_doc = {
        "_id":         f"mv_{uuid.uuid4().hex[:14]}",
        "first_voted_at": now,
    }
    await db.mood_votes.update_one(
        key,
        {"$set": set_doc, "$setOnInsert": insert_doc},
        upsert=True,
    )

    _bust_mood_cache(slug)
    _bust_analytics(slug)

    # Return fresh aggregate (no cache).
    agg = await _compute_aggregate(
        db, station_id=sid, slug=slug, since=None,
        include_per_track=_is_owner(station, user))
    return {
        "ok":         True,
        "your_vote":  {"mood": mood, "track_id": track_id,
                       "voted_at": now.isoformat()},
        "aggregate":  agg,
    }


@router.delete("/{slug}/mood_vote")
async def clear_mood_vote(slug: str, request: Request,
                           track_id: Optional[str] = None,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _resolve_station(db, slug, user)
    sid = station.get("station_id") or str(station.get("_id") or "")
    r = await db.mood_votes.delete_one({
        "station_id": sid,
        "track_id":   track_id,
        "user_id":    user["user_id"],
    })
    if r.deleted_count:
        _bust_mood_cache(slug)
        _bust_analytics(slug)
    return {"ok": True, "deleted": bool(r.deleted_count)}


@router.get("/{slug}/mood_aggregate")
async def get_mood_aggregate(slug: str, request: Request,
                              window: str = "7d",
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    if window not in WINDOW_DAYS:
        raise HTTPException(400, {"code": "validation_error",
                                   "field": "window",
                                   "message": f"window must be one of {sorted(WINDOW_DAYS.keys())}"})
    station = await _resolve_station(db, slug, user)
    is_owner = _is_owner(station, user)
    sid = station.get("station_id") or str(station.get("_id") or "")
    cache_key = (slug, window)
    cached = _AGG_CACHE.get(cache_key)
    now_ts = time.time()
    if cached and now_ts - cached[0] < AGG_CACHE_TTL_SEC:
        payload = dict(cached[1])
    else:
        agg = await _compute_aggregate(
            db, station_id=sid, slug=slug,
            since=_window_bound(window),
            include_per_track=True)
        payload = agg
        _AGG_CACHE[cache_key] = (now_ts, agg)

    # Lookup caller's own vote (station-overall) so the UI can highlight.
    own = await db.mood_votes.find_one({
        "station_id": sid,
        "track_id":   None,
        "user_id":    user["user_id"],
    })
    your_vote = ({"mood": own["mood"], "track_id": None,
                   "voted_at": (own.get("voted_at") or _now()).isoformat()}
                  if own else None)

    # Owner sees full per_track; everyone else gets it redacted.
    if not is_owner:
        payload = {**payload, "per_track": []}

    return {
        "slug":        slug,
        "window":      window,
        "your_vote":   your_vote,
        "is_owner":    is_owner,
        **payload,
    }
