"""Phase P0-BAR — Bottom-bar station rail.

`GET /api/user/bottom-bar-rail`

Returns a small set of stations to render as a horizontal icon rail
inside the persistent bottom player.  Composition:

    1. User's favorite imported/community stations (auth'd users only).
    2. Region-matched flagships:
           * US callers → the 5 US flagships (Dallas cluster).
           * AE / OTHER → the 8 AE flagships (Dubai cluster).

De-duplicated by `station_id`, capped to 12 items, favorites-first.
Each item carries `kind = "favorite" | "flagship"` so the frontend can
decorate the caller's #1 favorite with a ring.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request

from auth import current_user_optional
from services.geo_flagship import get_user_region
from services.flagship_station_service import list_flagships

log = logging.getLogger("bigfm.bottom_bar_rail")

router = APIRouter(prefix="/api/user", tags=["bottom-bar-rail"])

RAIL_CAP    = 12
FAV_TAKE = 6              # keep at least half the rail for flagships
FLAG_TAKE = 12


def _to_rail_item(station: Dict[str, Any], *, kind: str) -> Dict[str, Any]:
    """Project a station doc into the rail's compact shape."""
    stream_url = (station.get("stream_url") or station.get("url_resolved")
                              or station.get("url"))
    return {
        "id":                station.get("id") or station.get("_id"),
        "name":            (station.get("name") or "Unnamed")[:80],
        "logo_url":    (station.get("logo_url") or station.get("favicon")
                                    or None),
        "country_code": station.get("country_code")
                                        or station.get("country") or None,
        "language":      station.get("language") or None,
        "is_flagship": bool(station.get("is_flagship")),
        "flagship_slug": station.get("flagship_slug") or None,
        "stream_url": stream_url,
        "kind":              kind,
    }


async def _fetch_user_favorite_stations(
        db, user_id: str, cap: int = FAV_TAKE,
) -> List[Dict[str, Any]]:
    """Read the user's imported-station favorites (bigfm-channel favorites
    are irrelevant to the imported rail).  Sorted newest-first."""
    fav_ids: List[str] = []
    async for r in db.user_favorite_stations.find({
        "user_id": user_id, "station_type": "imported",
    }).sort("added_at", -1).limit(cap):
        sid = r.get("station_id")
        if sid:
            fav_ids.append(sid)
    if not fav_ids:
        return []
    # Batched station lookup.  Preserve the favourites order.
    station_map: Dict[str, Dict[str, Any]] = {}
    async for s in db.imported_radio_stations.find({"id": {"$in": fav_ids}}):
        station_map[s.get("id")] = {k: v for k, v in s.items() if k != "_id"}
    ordered: List[Dict[str, Any]] = []
    for sid in fav_ids:
        s = station_map.get(sid)
        if s:
            ordered.append(s)
    return ordered


@router.get("/bottom-bar-rail",
                        description="Favorites + region-matched flagships for the persistent "
                                              "bottom bar's station rail.")
async def get_bottom_bar_rail(
        request: Request,
        region: Optional[str] = Query(None,
                                                                    description="Override region (US / AE / OTHER)"),
) -> Dict[str, Any]:
    db = request.app.state.db
    user = await current_user_optional(request)
    user_region = (region or await get_user_region(user, request)).upper()

    # ── Favorites (auth only) ─────────────────────────────────
    fav_items: List[Dict[str, Any]] = []
    if user and user.get("user_id"):
        try:
            favs = await _fetch_user_favorite_stations(
                db, user["user_id"], cap=FAV_TAKE)
            fav_items = [_to_rail_item(s, kind="favorite") for s in favs]
        except Exception as e:
            log.warning("[bottom-bar-rail] favorites lookup failed: %s", e)

    # ── Region-matched flagships ─────────────────────────────
    # `list_flagships` returns all; filter by flagship_region.  US-region
    # callers get US flagships; everyone else gets AE flagships.
    target_region = "US" if user_region == "US" else "AE"
    try:
        all_flagships = await list_flagships(db, limit=200)
        flag_items = [
            _to_rail_item(s, kind="flagship")
            for s in all_flagships
            if s.get("flagship_region") == target_region
        ]
    except Exception as e:
        log.warning("[bottom-bar-rail] flagships lookup failed: %s", e)
        flag_items = []

    # ── Merge + dedupe ────────────────────────────────────────
    seen: set = set()
    merged: List[Dict[str, Any]] = []
    # Favorites first (kind preserved).
    for it in fav_items:
        if not it["id"] or it["id"] in seen:
            continue
        seen.add(it["id"])
        merged.append(it)
        if len(merged) >= RAIL_CAP:
            break
    for it in flag_items[:FLAG_TAKE]:
        if not it["id"] or it["id"] in seen:
            continue
        seen.add(it["id"])
        merged.append(it)
        if len(merged) >= RAIL_CAP:
            break

    return {
        "ok":                    True,
        "user_region":  user_region,
        "target_region": target_region,
        "items":              merged,
        "count":              len(merged),
        "favorites_count": len(fav_items),
    }


__all__ = ["router"]
