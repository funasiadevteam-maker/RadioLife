"""Phase 41M.B — Station-scoped fan badges + Top Fans surface.

Reads from `user_station_badges` (managed by
`services/station_badge_engine.py`).

Endpoints:
  GET /api/me/badges?station_slug=optional
      Returns the caller's badges; filterable by station.

  GET /api/stations/{slug}/top_fans?limit=10
      Public — top fans of a station ranked by:
        1. badge count (desc)
        2. lifetime listen minutes on the station (desc)
        3. earliest followed_at (asc)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, current_user_optional
from routes.community_stations import _visible_to as _station_visible_to
from services.station_badge_engine import serialize_badge, BADGE_META


me_router = APIRouter(prefix="/api/me", tags=["fan-badges"])
station_router = APIRouter(prefix="/api/stations", tags=["fan-badges"])
log = logging.getLogger("bigfm.fan_badges")

TOP_FANS_MAX_LIMIT = 50


@me_router.get("/badges")
async def my_badges(request: Request,
                     station_slug: Optional[str] = None,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    q: dict = {"user_id": user["user_id"]}
    if station_slug:
        q["station_slug"] = station_slug
    cursor = db.user_station_badges.find(q).sort("granted_at", -1)
    rows = [serialize_badge(d) async for d in cursor]
    return {"badges": rows, "count": len(rows)}


async def _resolve_station(db, slug: str, user: Optional[dict]) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if not _station_visible_to(s, user, via_direct_link=True):
        raise HTTPException(404, {"code": "not_found"})
    # Keep `_id` reachable for downstream queries (callers expect it).
    s["_id"] = s.get("_id")
    return s


@station_router.get("/{slug}/top_fans")
async def top_fans(slug: str, request: Request,
                    limit: int = Query(default=10, ge=1, le=TOP_FANS_MAX_LIMIT),
                    user: Optional[dict] = Depends(current_user_optional)):
    """Public — returns top fans of this station, ranked by badge count
    (desc), then listen minutes (desc), then earliest follow (asc)."""
    db = request.app.state.db
    station = await _resolve_station(db, slug, user)
    station_id = station.get("station_id") or str(station.get("_id") or "")

    # ── 1. Aggregate badges per user on this station ──────────────────
    badge_pipe = [
        {"$match": {"station_id": station_id}},
        {"$group": {
            "_id":          "$user_id",
            "badge_count":  {"$sum": 1},
            "badge_types":  {"$addToSet": "$badge_type"},
            "first_grant":  {"$min": "$granted_at"},
        }},
    ]
    badge_map: dict[str, dict] = {}
    async for row in db.user_station_badges.aggregate(badge_pipe):
        badge_map[row["_id"]] = {
            "badge_count": int(row.get("badge_count") or 0),
            "badge_types": list(row.get("badge_types") or []),
            "first_grant": row.get("first_grant"),
        }

    # ── 2. Aggregate listen minutes per user from archive (by slug) ──
    listen_pipe = [
        {"$match": {"station_slug": slug}},
        {"$group": {
            "_id":         "$user_id",
            "total_sec":   {"$sum": {"$ifNull": ["$duration_sec", 0]}},
        }},
    ]
    listen_map: dict[str, int] = {}
    async for row in db.listener_session_archive.aggregate(listen_pipe):
        listen_map[row["_id"]] = int((row.get("total_sec") or 0) / 60)

    # ── 3. Follow time per user (followers store station_id string) ──
    follow_map: dict[str, str] = {}
    async for row in db.station_followers.find(
            {"station_id": station_id},
            {"user_id": 1, "followed_at": 1, "_id": 0}):
        follow_map[row["user_id"]] = row.get("followed_at")

    # ── 4. Merge candidate pool ───────────────────────────────────────
    user_ids = set(badge_map) | set(listen_map) | set(follow_map)
    if not user_ids:
        return {"slug": slug, "top_fans": [], "count": 0}

    # ── 5. Sort + slice top-N ─────────────────────────────────────────
    candidates = []
    for uid in user_ids:
        b = badge_map.get(uid, {})
        candidates.append({
            "user_id":      uid,
            "badge_count":  b.get("badge_count", 0),
            "badge_types":  b.get("badge_types", []),
            "listen_minutes": listen_map.get(uid, 0),
            "followed_at":  follow_map.get(uid),
        })
    candidates.sort(key=lambda c: (
        -c["badge_count"],
        -c["listen_minutes"],
        c["followed_at"] or "z",
    ))
    top = candidates[:limit]

    # ── 6. Attach display name + avatar for the top slice only ────────
    uids = [c["user_id"] for c in top]
    users_map = {}
    async for u in db.users.find({"user_id": {"$in": uids}},
                                   {"user_id": 1, "name": 1, "display_name": 1,
                                    "avatar_url": 1, "email": 1, "_id": 0}):
        users_map[u["user_id"]] = u

    out = []
    for c in top:
        u = users_map.get(c["user_id"]) or {}
        name = u.get("display_name") or u.get("name") \
            or (u.get("email") or "").split("@")[0] or "Listener"
        out.append({
            "user_id":        c["user_id"],
            "name":           name,
            "avatar_url":     u.get("avatar_url"),
            "badge_count":    c["badge_count"],
            "badge_types":    c["badge_types"],
            "listen_minutes": c["listen_minutes"],
            "followed_at":    c["followed_at"],
        })

    return {"slug": slug, "top_fans": out, "count": len(out),
             "badge_meta": BADGE_META}
