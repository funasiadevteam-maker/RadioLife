"""FUUSIC — My Feed Preferences API (Feature B).

GET  /api/social/feed-preferences                      list followed entities + modes
PUT  /api/social/feed-preferences/{actor_type}/{actor_id}   set an entity's mode

Authorization is server-side; a user may only read/write their own preferences.
Feed-frequency preferences are kept separate from push-notification settings.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user
from services.feed_preferences_service import (
    VALID_MODES, VALID_ACTOR_TYPES, set_pref, list_following_entities)

router = APIRouter(prefix="/api/social", tags=["feed-preferences"])


class PrefBody(BaseModel):
    frequency_mode: str


@router.get("/feed-preferences")
async def get_feed_preferences(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    return await list_following_entities(db, user["user_id"])


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
