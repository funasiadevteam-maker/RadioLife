"""Phase 36d Turn 1 — Magic Clips routes.

Mounted at /api/podcasts. Auth pattern mirrors routes/podcasts.py:
- creator-only writes go through `require_approved_creator` + an
  ownership check via the episode's channel.
- public reads (`/highlights`, channel carousel) only return
  `status="published"` clips.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query

from auth import current_user, current_user_optional as optional_current_user
from services import podcasts as svc
from services import podcast_magic_clips as mc

magic_clips_router = APIRouter(prefix="/api/podcasts", tags=["magic_clips"])


async def _require_episode_owner(db, user: dict, episode_id: str) -> dict:
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep:
        raise HTTPException(404, "episode_not_found")
    creator = await svc.require_approved_creator(db, user)
    ch = await db.podcast_channels.find_one({"id": ep.get("channel_id"),
                                                                          "creator_id": creator["id"]})
    if not ch and user.get("role") != "admin":
        raise HTTPException(403, "not_your_episode")
    return ep


async def _require_clip_owner(db, user: dict, clip_id: str) -> dict:
    clip = await db.podcast_magic_clips.find_one({"id": clip_id})
    if not clip:
        raise HTTPException(404, "clip_not_found")
    await _require_episode_owner(db, user, clip["episode_id"])
    return clip


# ── Generate / list / publish / patch / delete ─────────────────────
@magic_clips_router.post("/episodes/{episode_id}/magic-clips/generate")
async def generate(episode_id: str, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_episode_owner(db, user, episode_id)
    # Reset status, then schedule.
    await db.podcast_episodes.update_one(
        {"id": episode_id},
        {"$set": {"magic_clips_status": "pending"}})
    mc.schedule_magic_clips(db, episode_id=episode_id)
    return {"scheduled": True, "episode_id": episode_id,
                  "magic_clips_status": "pending"}


@magic_clips_router.get("/episodes/{episode_id}/magic-clips")
async def list_for_episode(episode_id: str, request: Request,
                                                  user: Optional[dict] = Depends(optional_current_user)):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep:
        raise HTTPException(404, "episode_not_found")
    is_owner = False
    if user:
        creator = await db.podcast_creators.find_one({"user_id": user.get("user_id")})
        if creator:
            ch = await db.podcast_channels.find_one(
                {"id": ep.get("channel_id"), "creator_id": creator["id"]})
            is_owner = bool(ch)
        if user.get("role") == "admin":
            is_owner = True
    filt = {"episode_id": episode_id}
    if not is_owner:
        filt["status"] = "published"
    rows = await db.podcast_magic_clips.find(filt, {"_id": 0}).sort(
        "score", -1).to_list(50)
    return {"items": rows,
                  "episode_id": episode_id,
                  "magic_clips_status": ep.get("magic_clips_status"),
                  "magic_clips_error":   ep.get("magic_clips_error")}


@magic_clips_router.post("/magic-clips/{clip_id}/publish")
async def publish_clip(clip_id: str, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_clip_owner(db, user, clip_id)
    now = datetime.now(timezone.utc)
    await db.podcast_magic_clips.update_one(
        {"id": clip_id},
        {"$set": {"status": "published", "published_at": now}})
    r = await db.podcast_magic_clips.find_one({"id": clip_id}, {"_id": 0})
    return r


@magic_clips_router.patch("/magic-clips/{clip_id}")
async def patch_clip(clip_id: str, body: dict, request: Request,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_clip_owner(db, user, clip_id)
    upd = {}
    if "title" in body:
        upd["title"] = str(body["title"])[:120]
    if "summary" in body:
        upd["summary"] = str(body["summary"])[:280]
    if not upd:
        raise HTTPException(400, "no editable fields supplied")
    await db.podcast_magic_clips.update_one({"id": clip_id}, {"$set": upd})
    r = await db.podcast_magic_clips.find_one({"id": clip_id}, {"_id": 0})
    return r


@magic_clips_router.delete("/magic-clips/{clip_id}")
async def delete_clip(clip_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    clip = await _require_clip_owner(db, user, clip_id)
    await db.podcast_magic_clips.delete_one({"id": clip_id})
    # Best-effort Tigris cleanup; local file is left alone.
    try:
        from services import object_storage as obs
        st = obs.get_storage()
        if clip.get("storage_key") and st.backend_name == "tigris":
            st.delete(key=clip["storage_key"])
    except Exception:
        pass
    return {"deleted": True, "id": clip_id}


# ── Highlights feeds ───────────────────────────────────────────
@magic_clips_router.get("/highlights")
async def global_highlights(request: Request,
                                                limit: int = Query(20, ge=1, le=100),
                                                cursor: Optional[str] = None):
    db = request.app.state.db
    filt = {"status": "published"}
    if cursor:
        try:
            filt["published_at"] = {"$lt": datetime.fromisoformat(cursor)}
        except Exception:
            pass
    rows = await db.podcast_magic_clips.find(filt, {"_id": 0}).sort(
        "published_at", -1).limit(limit + 1).to_list(limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (rows[-1]["published_at"].isoformat()
                              if has_more and rows and rows[-1].get("published_at")
                              else None)
    # Serialize timestamps for transport.
    for r in rows:
        for k in ("created_at", "published_at"):
            if hasattr(r.get(k), "isoformat"):
                r[k] = r[k].isoformat()
    return {"items": rows, "next_cursor": next_cursor, "has_more": has_more}


@magic_clips_router.get("/channels/{channel_id}/highlights")
async def channel_highlights(channel_id: str, request: Request,
                                                    limit: int = Query(20, ge=1, le=50)):
    db = request.app.state.db
    rows = await db.podcast_magic_clips.find(
        {"channel_id": channel_id, "status": "published"}, {"_id": 0}
        ).sort("published_at", -1).limit(limit).to_list(limit)
    for r in rows:
        for k in ("created_at", "published_at"):
            if hasattr(r.get(k), "isoformat"):
                r[k] = r[k].isoformat()
    return {"items": rows, "channel_id": channel_id}
