"""Phase J.5 — Mid-stream audio-ad selection + admin cadence.

Public + admin endpoints for the "ad between songs" cadence.  Reuses
`services.preroll_ad_service` for selection (the same SSP waterfall +
frequency capping) but returns a SINGLE ad per request rather than a
chain.  Premium gate honours `services.premium_gate`.

Cadence is persisted in `system_config` (key=`midstream_ad_cadence`)
with an env-var fallback `MIDSTREAM_AD_EVERY_N_SONGS` (default 4,
clamped 2-8).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, conint

from auth import current_user, current_user_optional
from services.premium_gate import is_premium_or_trial

log = logging.getLogger("bigfm.midstream_ads")

router = APIRouter(prefix="/api/live-radio/midstream-ad",
                                          tags=["midstream-ads"])
admin_router = APIRouter(prefix="/api/admin/midstream-ad",
                                                          tags=["admin-midstream-ads"])


CADENCE_KEY = "midstream_ad_cadence"
DEFAULT_CADENCE = int(os.environ.get("MIDSTREAM_AD_EVERY_N_SONGS", "4"))
MIN_CADENCE = 2
MAX_CADENCE = 8


def _is_admin(u: dict) -> bool:
    if not u: return False
    return (u.get("role") == "admin" or u.get("is_admin")
                  or "admin" in (u.get("roles") or []))


async def get_cadence(db) -> int:
    doc = await db.system_config.find_one({"_id": CADENCE_KEY})
    raw = (doc or {}).get("every_n_songs")
    try:
        v = int(raw if raw is not None else DEFAULT_CADENCE)
    except (TypeError, ValueError):
        v = DEFAULT_CADENCE
    return max(MIN_CADENCE, min(MAX_CADENCE, v))


@router.post("/request",
                          description=(
                              "Request ONE mid-stream audio ad to play between songs.  "
                              "Premium users always get `has_ad=False`.  Anonymous-friendly."))
async def midstream_ad_request(payload: dict, request: Request,
                                                              user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    station_id = (payload or {}).get("station_id")
    session_id = (payload or {}).get("session_id") or f"anon_{uuid.uuid4().hex[:12]}"
    songs_played = int((payload or {}).get("songs_played_in_session") or 0)
    if not station_id:
        raise HTTPException(400, {"code": "station_id_required"})

    # Premium escape hatch.
    if user and is_premium_or_trial(user):
        return {"has_ad": False, "reason": "premium_user",
                      "station_id": station_id, "session_id": session_id,
                      "cadence": await get_cadence(db)}

    # Resolve station (imported + community both eligible).
    station = (await db.imported_radio_stations.find_one({"id": station_id})
                          or await db.community_stations.find_one({"_id": station_id}))
    if not station or not station.get("active", True):
        return {"has_ad": False, "reason": "station_not_found",
                      "station_id": station_id, "session_id": session_id,
                      "cadence": await get_cadence(db)}

    # Reuse the preroll selector but ask for a 1-ad chain.
    try:
        from services.preroll_ad_service import select_ad_chain_for_play
        res = await select_ad_chain_for_play(
            db, user, station, session_id,
            country_code=(payload or {}).get("country_code"),
            language=(payload or {}).get("language"),
            chain_count_override=1,
            placement_label="midstream")
    except TypeError:
        # Older selector signature — fall back to default chain (slice
        # the first ad ourselves).  Graceful regression-safe.
        from services.preroll_ad_service import select_ad_chain_for_play
        res = await select_ad_chain_for_play(
            db, user, station, session_id,
            country_code=(payload or {}).get("country_code"),
            language=(payload or {}).get("language"))
    chain = res.get("chain") or res.get("ads") or []
    if not chain:
        return {"has_ad": False, "reason": res.get("reason") or "no_fill",
                      "station_id": station_id, "session_id": session_id,
                      "cadence": await get_cadence(db),
                      "songs_played_in_session": songs_played}
    ad = chain[0]
    imp_id = (res.get("impression_id")
                  or (res.get("impression_ids") or [None])[0])
    return {"has_ad": True, "ad": ad, "impression_id": imp_id,
                  "station_id": station_id, "session_id": session_id,
                  "songs_played_in_session": songs_played,
                  "cadence": await get_cadence(db)}


@admin_router.get("/cadence")
async def get_admin_cadence(request: Request,
                                                                    user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    return {"every_n_songs": await get_cadence(db),
                  "min": MIN_CADENCE, "max": MAX_CADENCE,
                  "env_default": DEFAULT_CADENCE}


class _CadenceBody(BaseModel):
    every_n_songs: conint(ge=MIN_CADENCE, le=MAX_CADENCE)  # noqa: F722


@admin_router.patch("/cadence")
async def set_admin_cadence(body: _CadenceBody, request: Request,
                                                                  user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    await db.system_config.update_one(
        {"_id": CADENCE_KEY},
        {"$set": {"every_n_songs": int(body.every_n_songs),
                          "updated_at": now,
                          "updated_by": user["user_id"]}}, upsert=True)
    log.info("[midstream-ads] cadence set to %d by %s",
                  body.every_n_songs, user["user_id"])
    return {"ok": True, "every_n_songs": int(body.every_n_songs),
                  "min": MIN_CADENCE, "max": MAX_CADENCE}
