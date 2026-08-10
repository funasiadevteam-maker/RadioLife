"""Creator Studio — video podcast episodes: video upload to Tigris object
storage, chapters, and transcripts.  Self-contained; reuses the existing
`podcast_episodes` collection + `object_storage.get_storage()` (Tigris)."""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from auth import current_user
from services import object_storage as obs

router = APIRouter(prefix="/api/podcasts", tags=["creator-video"])

_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v"}
_MAX_BYTES = 500 * 1024 * 1024  # 500 MB


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _own_episode(db, user, ep_id: str) -> Dict[str, Any]:
    ep = await db.podcast_episodes.find_one({"id": ep_id})
    if not ep:
        raise HTTPException(404, {"code": "episode_not_found"})
    if user.get("role") == "admin":
        return ep
    ch = await db.podcast_channels.find_one({"id": ep.get("channel_id")}, {"creator_id": 1})
    if not ch:
        raise HTTPException(404, {"code": "channel_not_found"})
    cre = await db.podcast_creators.find_one({"user_id": user.get("user_id")}, {"id": 1})
    if not cre or cre.get("id") != ch.get("creator_id"):
        raise HTTPException(403, {"code": "not_your_episode"})
    return ep


def _media_payload(ep: Dict[str, Any]) -> Dict[str, Any]:
    video_url = None
    key = ep.get("video_storage_key")
    if key:
        try:
            video_url = obs.get_storage().get_signed_url(key=key, expires_in=6 * 3600)
        except Exception:
            video_url = None
    if not video_url and ep.get("video_url"):
        video_url = ep.get("video_url")
    return {
        "episode_id": ep.get("id"),
        "media_type": ep.get("media_type") or ("video" if video_url else "audio"),
        "video_url": video_url,
        "chapters": ep.get("chapters") or [],
        "transcript": ep.get("transcript") or "",
        "duration_seconds": ep.get("duration_seconds") or 0,
    }


@router.get("/episodes/{ep_id}/media")
async def get_episode_media(ep_id: str, request: Request):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one({"id": ep_id})
    if not ep:
        raise HTTPException(404, {"code": "episode_not_found"})
    return _media_payload(ep)


@router.post("/episodes/{ep_id}/video")
async def upload_episode_video(ep_id: str, request: Request,
                               video: UploadFile = File(...),
                               user: dict = Depends(current_user)):
    db = request.app.state.db
    ep = await _own_episode(db, user, ep_id)
    if video.content_type and video.content_type not in _VIDEO_TYPES:
        raise HTTPException(400, {"code": "unsupported_video_type", "got": video.content_type})
    suffix = os.path.splitext(video.filename or "")[1] or ".mp4"
    key = f"podcast_video/{ep_id}/{uuid.uuid4().hex}{suffix}"
    size = 0
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_BYTES:
                    raise HTTPException(413, {"code": "video_too_large", "max_mb": 500})
                tmp.write(chunk)
        st = obs.get_storage()
        st.upload(local_path=tmp_path, key=key,
                  content_type=video.content_type or "video/mp4")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
    await db.podcast_episodes.update_one(
        {"id": ep_id},
        {"$set": {"video_storage_key": key, "media_type": "video",
                  "video_size_bytes": size, "updated_at": _now()}})
    ep = await db.podcast_episodes.find_one({"id": ep_id})
    return _media_payload(ep)


class Chapter(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    start_seconds: int = Field(..., ge=0, le=100_000)


class ChaptersBody(BaseModel):
    chapters: List[Chapter]


@router.put("/episodes/{ep_id}/chapters")
async def put_chapters(ep_id: str, body: ChaptersBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_episode(db, user, ep_id)
    chapters = sorted([c.model_dump() for c in body.chapters], key=lambda c: c["start_seconds"])
    await db.podcast_episodes.update_one(
        {"id": ep_id}, {"$set": {"chapters": chapters, "updated_at": _now()}})
    return {"ok": True, "chapters": chapters}


class TranscriptBody(BaseModel):
    transcript: str = Field("", max_length=200_000)


@router.put("/episodes/{ep_id}/transcript")
async def put_transcript(ep_id: str, body: TranscriptBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_episode(db, user, ep_id)
    await db.podcast_episodes.update_one(
        {"id": ep_id}, {"$set": {"transcript": body.transcript, "updated_at": _now()}})
    return {"ok": True, "length": len(body.transcript)}


__all__ = ["router"]
