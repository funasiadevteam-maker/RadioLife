"""Phase 42-D3 — Station favorites (BigFM AI channels + imported live
radio).

This is a separate surface from the channel-slug-only
`/api/me/favorites` (channels), which `Phase18Home.FavoritesStrip` uses.
The new collection models the broader user-facing "heart any station
anywhere" behaviour:

    user_favorite_stations {
        favorite_id (unique),
        user_id (indexed),
        station_id (indexed),         # e.g. "imp_…", "vip_lounge", "ai_*"
        station_type: "bigfm" | "imported",
        added_at,
    }

Compound unique index on (user_id, station_id) makes POST idempotent.

Routes (auth required):
    POST    /api/me/favorite-stations    { station_id, station_type }
    GET     /api/me/favorite-stations    → joined station objects
    DELETE  /api/me/favorite-stations/{station_id}
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user

log = logging.getLogger("bigfm.station_favorites")
router = APIRouter(prefix="/api/me/favorite-stations",
                                    tags=["station-favorites"])

MAX_FAVORITES = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ToggleIn(BaseModel):
    station_id: str = Field(..., min_length=2, max_length=200)
    station_type: Literal["bigfm", "imported"]


@router.post("")
async def add_favorite_station(payload: ToggleIn, request: Request,
                                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    now = _now()
    # Cap check (cheap).
    count = await db.user_favorite_stations.count_documents(
        {"user_id": user["user_id"]})
    existing = await db.user_favorite_stations.find_one({
        "user_id": user["user_id"], "station_id": payload.station_id})
    if existing:
        return {"ok": True, "favorite_id": existing["favorite_id"],
                      "already_favorited": True}
    if count >= MAX_FAVORITES:
        raise HTTPException(409, {"code": "favorites_cap",
                                                                    "cap": MAX_FAVORITES,
                                                                    "current": count})
    fid = f"fav_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id": fid, "favorite_id": fid,
        "user_id": user["user_id"],
        "station_id": payload.station_id,
        "station_type": payload.station_type,
        "added_at": now,
    }
    try:
        await db.user_favorite_stations.insert_one(doc)
    except Exception as e:
        # Compound-unique race — return idempotent OK.
        log.debug("[station-favorites] insert race: %s", e)
        existing = await db.user_favorite_stations.find_one({
            "user_id": user["user_id"], "station_id": payload.station_id})
        if existing:
            return {"ok": True, "favorite_id": existing["favorite_id"],
                          "already_favorited": True}
        raise
    return {"ok": True, "favorite_id": fid, "added": True}


@router.delete("/{station_id}")
async def remove_favorite_station(station_id: str, request: Request,
                                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.user_favorite_stations.delete_one(
        {"user_id": user["user_id"], "station_id": station_id})
    return {"ok": True, "removed": r.deleted_count > 0,
                  "station_id": station_id}


@router.get("")
async def list_favorite_stations(request: Request,
                                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    favs: List[dict] = []
    async for r in db.user_favorite_stations.find(
            {"user_id": user["user_id"]}).sort("added_at", -1):
        r.pop("_id", None)
        favs.append({**r,
                              "added_at": r["added_at"].isoformat()
                                                    if r.get("added_at") else None})
    if not favs:
        return {"ok": True, "items": [], "total": 0}
    # Join station objects in two batched lookups.
    bigfm_ids   = [f["station_id"] for f in favs
                          if f["station_type"] == "bigfm"]
    imported_ids = [f["station_id"] for f in favs
                              if f["station_type"] == "imported"]
    bigfm_map: dict = {}
    imp_map: dict = {}
    if bigfm_ids:
        async for c in db.channels.find({"_id": {"$in": bigfm_ids}}):
            bigfm_map[c["_id"]] = {
                "id": c["_id"], "name": c.get("name"),
                "tagline": c.get("tagline"),
                "thumbnail_url": c.get("thumbnail_url"),
                "type": "bigfm",
            }
    if imported_ids:
        async for s in db.imported_radio_stations.find(
                {"id": {"$in": imported_ids}}):
            imp_map[s["id"]] = {
                "id": s["id"], "name": s.get("name"),
                "favicon": s.get("favicon"),
                "country": s.get("country"),
                "language": s.get("language"),
                "stream_url": s.get("url_resolved") or s.get("url"),
                "type": "imported",
            }
    items = []
    for f in favs:
        st = (bigfm_map.get(f["station_id"]) if f["station_type"] == "bigfm"
                  else imp_map.get(f["station_id"]))
        if st is None:
            # Orphaned favourite — station was deleted / deactivated.
            # We still return the favorite-stub so the UI can offer
            # a one-tap remove.
            st = {"id": f["station_id"], "name": "(unavailable)",
                      "type": f["station_type"]}
        items.append({"favorite_id": f["favorite_id"],
                                  "station_id": f["station_id"],
                                  "station_type": f["station_type"],
                                  "added_at": f["added_at"],
                                  "station": st})
    return {"ok": True, "items": items, "total": len(items),
                  "cap": MAX_FAVORITES}


async def ensure_indexes(db) -> None:
    try:
        await db.user_favorite_stations.create_index(
            [("user_id", 1), ("station_id", 1)],
            unique=True, name="uniq_user_station")
        await db.user_favorite_stations.create_index(
            [("user_id", 1), ("added_at", -1)],
            name="user_added_at")
    except Exception as e:
        log.debug("[station-favorites] index ensure skipped: %s", e)
