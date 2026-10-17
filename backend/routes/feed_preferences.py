"""FUUSIC — My Feed Preferences API (Feature B).

GET  /api/social/feed-preferences                      list followed entities + modes
PUT  /api/social/feed-preferences/{actor_type}/{actor_id}   set an entity's mode

Authorization is server-side; a user may only read/write their own preferences.
Feed-frequency preferences are kept separate from push-notification settings.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_admin
from services.feed_preferences_service import (
    VALID_MODES, VALID_ACTOR_TYPES, set_pref, list_following_entities,
    get_category_defaults, set_category_defaults)

router = APIRouter(prefix="/api/social", tags=["feed-preferences"])


class PrefBody(BaseModel):
    frequency_mode: str


class DefaultsBody(BaseModel):
    defaults: dict


@router.get("/feed-preferences")
async def get_feed_preferences(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    return await list_following_entities(db, user["user_id"])


@router.get("/feed-preferences/defaults")
async def get_feed_defaults(request: Request, admin: dict = Depends(require_admin)):
    """Admin — current per-category default frequency modes for new follows."""
    db = request.app.state.db
    return {"defaults": await get_category_defaults(db),
            "modes": sorted(VALID_MODES),
            "actor_types": sorted(VALID_ACTOR_TYPES)}


@router.put("/feed-preferences/defaults")
async def put_feed_defaults(body: DefaultsBody, request: Request,
                            admin: dict = Depends(require_admin)):
    """Admin — set per-category default frequency modes."""
    db = request.app.state.db
    try:
        merged = await set_category_defaults(db, body.defaults)
    except ValueError:
        raise HTTPException(status_code=400, detail="no_valid_defaults")
    return {"ok": True, "defaults": merged}


@router.put("/feed-preferences/{actor_type}/{actor_id}")
async def put_feed_preference(actor_type: str, actor_id: str, body: PrefBody,
                              request: Request, user: dict = Depends(current_user)):
    if actor_type not in VALID_ACTOR_TYPES:
        raise HTTPException(status_code=400, detail="invalid_actor_type")
    if body.frequency_mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail="invalid_frequency_mode")
    db = request.app.state.db
    res = await set_pref(db, user["user_id"], actor_type, actor_id, body.frequency_mode)
    return {"ok": True, "preference": res}
