"""Phase PREROLL.EXT — Admin per-station preroll toggle.

Unified endpoint that routes to the correct station collection based
on the station ID resolution.  Reuses `resolve_station` so the shape
matches what the /preroll/request endpoint sees.

PATCH /api/admin/stations/{station_id}/preroll body {enabled: bool}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user
from services.preroll_ad_service import resolve_station

router = APIRouter(tags=["preroll-ext-admin"])
logger = logging.getLogger("bigfm.preroll_ext.admin")


class TogglePayload(BaseModel):
    enabled: bool


def _require_admin(user: dict) -> None:
    if not user or user.get("role") != "admin":
        raise HTTPException(403, {"code": "admin_required"})


@router.patch("/api/admin/stations/{station_id}/preroll",
                            description="Toggle per-station preroll gating (works across all station types).")
async def toggle_preroll(station_id: str, payload: TogglePayload,
                                                    request: Request,
                                                    user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    station = await resolve_station(db, station_id)
    if not station:
        raise HTTPException(404, {"code": "station_not_found"})
    coll = station.get("_source_collection")
    if not coll:
        raise HTTPException(500, {"code": "station_collection_missing"})
    id_field = station.get("_source_id_field") or "id"
    # The resolver may have matched via ObjectId when id_field == "_id" and
    # station_id is a 24-char hex. Try string first, then ObjectId fallback.
    from bson import ObjectId
    from bson.errors import InvalidId
    now = datetime.now(timezone.utc)
    update_doc = {"$set": {"preroll_enabled": payload.enabled,
                                                    "preroll_toggled_at": now,
                                                    "preroll_toggled_by": user.get("user_id"),
                                                    "updated_at": now}}
    r = await db[coll].update_one({id_field: station_id}, update_doc)
    if r.matched_count == 0 and id_field == "_id" and isinstance(station_id, str) \
            and len(station_id) == 24:
        try:
            r = await db[coll].update_one({"_id": ObjectId(station_id)}, update_doc)
        except InvalidId:
            pass
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "station_not_found"})
    return {
        "ok":                            True,
        "station_id":              station_id,
        "station_type":          station.get("station_type"),
        "preroll_enabled":    payload.enabled,
    }


__all__ = ["router"]
