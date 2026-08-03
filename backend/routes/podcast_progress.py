"""Phase B — Podcast progress tracking HTTP routes."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user
from services import podcast_progress_service as _pp

router = APIRouter(tags=["podcast-progress"])
logger = logging.getLogger("bigfm.podcast_progress.routes")


class ProgressBody(BaseModel):
    position_seconds:  float = Field(..., ge=0)
    duration_seconds: Optional[float] = Field(None, ge=0)


@router.post("/api/podcasts/episodes/{episode_id}/progress",
                          description="Save the caller's resume position + fire "
                                                  "podcast_completed on 90% crossing (idempotent).")
async def post_progress(episode_id: str, body: ProgressBody,
                                                request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await _pp.record_progress(
            db, user_id=user["user_id"],
            episode_id=episode_id,
            position_seconds=body.position_seconds,
            duration_seconds=body.duration_seconds)
    except ValueError as e:
        raise HTTPException(404 if str(e) == "episode_not_found" else 400,
                                                {"code": str(e)})


@router.get("/api/podcasts/episodes/{episode_id}/progress",
                        description="Caller's saved progress for this episode "
                                                "(null if never started).")
async def get_progress(episode_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    row = await _pp.get_progress(
        request.app.state.db,
        user_id=user["user_id"], episode_id=episode_id)
    return {"progress": row}


@router.get("/api/podcasts/me/continue-listening",
                        description="Recent-first list of episodes the caller has "
                                                "started but not yet completed.")
async def continue_listening(request: Request,
                                                          limit: int = Query(20, ge=1, le=100),
                                                          user: dict = Depends(current_user)):
    return await _pp.continue_listening(
        request.app.state.db, user_id=user["user_id"], limit=limit)


@router.get("/api/podcasts/me/subscriptions",
                        description="List of podcast channels the caller follows.")
async def my_subscriptions(request: Request,
                                                    user: dict = Depends(current_user)):
    return await _pp.list_user_subscriptions(
        request.app.state.db, user_id=user["user_id"])


@router.post("/api/podcasts/channels/{channel_id}/unfollow",
                          description="Unsubscribe from a podcast channel.  Idempotent.")
async def unfollow(channel_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    return await _pp.unfollow_channel(
        request.app.state.db,
        user_id=user["user_id"], channel_id=channel_id)


@router.get("/api/podcasts/episodes/{episode_id}/analytics",
                        description="Creator-only per-episode analytics stub — "
                                                "plays / completions / avg completion %.")
async def analytics(episode_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one(
        {"id": episode_id}, {"channel_id": 1, "_id": 0})
    if not ep:
        raise HTTPException(404, {"code": "episode_not_found"})
    # Owner-or-admin gate.
    if user.get("role") != "admin":
        ch = await db.podcast_channels.find_one(
            {"id": ep.get("channel_id")}, {"creator_id": 1, "_id": 0})
        creator = await db.podcast_creators.find_one(
            {"id": (ch or {}).get("creator_id")}, {"user_id": 1, "_id": 0})
        if not creator or creator.get("user_id") != user["user_id"]:
            raise HTTPException(403, {"code": "not_episode_owner"})
    try:
        return await _pp.episode_analytics(db, episode_id=episode_id)
    except ValueError as e:
        raise HTTPException(404, {"code": str(e)})


__all__ = ["router"]
