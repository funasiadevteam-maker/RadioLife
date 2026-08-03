"""Phase 36a — Podcast routes (creator + listener + public RSS)."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Optional

import feedparser
import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from auth import current_user, current_user_optional, require_admin
from services import podcasts as svc
from services import podcast_rss as rss_svc

logger = logging.getLogger("bigfm.routes.podcasts")

# All under /api so kubernetes ingress routes them correctly.
podcasts_router         = APIRouter(prefix="/api/podcasts",      tags=["podcasts"])
admin_podcasts_router = APIRouter(prefix="/api/admin/podcasts",
                                                                tags=["admin_podcasts"])
# Public RSS at site root (the proxy in src/setupProxy.js forwards /podcasts/*).
podcasts_public_router = APIRouter(tags=["podcasts_public"])


# ─── Creator applications ─────────────────────────────────────────
class ApplyBody(BaseModel):
    display_name:   str
    bio:                      str = ""
    contact_email: str
    market:                str = "dubai"


@podcasts_router.post("/creators/apply")
async def creator_apply(body: ApplyBody, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    doc = await svc.submit_creator_application(
        db, user_id=user["user_id"],
        display_name=body.display_name, bio=body.bio,
        contact_email=body.contact_email, market=body.market)
    doc.pop("_id", None)
    return doc


@podcasts_router.get("/creators/me")
async def creator_me(request: Request,
                                  user: dict = Depends(current_user)):
    c = await svc.get_creator_by_user(request.app.state.db, user["user_id"])
    if not c: return {"creator": None}
    c.pop("_id", None)
    return {"creator": c}


# ─── Channels (creator-side) ────────────────────────────────────
@podcasts_router.post("/creators/{creator_id}/channels")
async def create_channel(creator_id: str, body: dict, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    creator = await svc.require_approved_creator(db, user)
    if creator["id"] != creator_id:
        raise HTTPException(403, "creator_mismatch")
    ch = await svc.create_channel(db, creator_id=creator_id, body=body)
    ch.pop("_id", None)
    return ch


@podcasts_router.get("/me")
async def get_my_creator(request: Request,
                                                user: dict = Depends(current_user)):
    """Phase 36c Stage 1 fix — resolve the current user's creator profile +
    their approved/active channels in one shot. Used by the Studio New
    page to populate the channel picker. Returns 404 with a route hint
    when the user has no approved creator profile."""
    db = request.app.state.db
    uid = user.get("user_id")
    cre = await db.podcast_creators.find_one(
        {"user_id": uid}, {"_id": 0})
    if not cre or cre.get("application_status") != "approved":
        raise HTTPException(404, {"code": "creator_not_approved",
            "message": "You don't have an approved creator profile.",
            "next_route": "/creator/apply"})
    channels = await db.podcast_channels.find(
        {"creator_id": cre["id"]}, {"_id": 0}).to_list(100)
    # Stage 1 picker shows only approved + active channels.
    active = [c for c in channels
                  if c.get("approval_status") == "approved" and c.get("active")]
    return {"creator": cre, "channels": active,
              "next_route": "/creator/podcasts/new" if not active else None}


@podcasts_router.get("/creators/{creator_id}/channels")
async def list_creator_channels(creator_id: str, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    if user.get("role") != "admin":
        creator = await svc.require_approved_creator(db, user)
        if creator["id"] != creator_id:
            raise HTTPException(403, "creator_mismatch")
    rows = await db.podcast_channels.find(
        {"creator_id": creator_id}, {"_id": 0}).to_list(100)
    return {"channels": rows}


@podcasts_router.patch("/channels/{channel_id}")
async def patch_channel(channel_id: str, body: dict, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    ch = await _own_channel_or_403(db, user, channel_id)
    # Reuse the service-layer update; pass the channel's existing creator_id
    # so admin updates don't break the filter shape.
    r = await svc.update_channel(db, channel_id=channel_id,
                                                        creator_id=ch.get("creator_id"), body=body)
    if not r: raise HTTPException(404, "channel_not_found")
    r.pop("_id", None)
    await svc.invalidate_feed_cache(db, channel_id=channel_id)
    return r


# ── Phase 36d — Canonical Channel Settings (creator-only) ────────
# Read/write subset for the new /creator/channels/:id/settings page.
# Later phases (Lightning Splits in Turn 3, etc.) add sections to the
# same page; this endpoint will grow the field whitelist accordingly.
_SETTINGS_FIELDS = ("magic_clips_enabled", "magic_clips_per_episode")


async def _own_channel_or_403(db, user, channel_id: str) -> dict:
    # Admin role bypass FIRST — admins manage any channel without needing a
    # `podcast_creators` row. (Previously `require_approved_creator` raised
    # 403 before this branch was reachable.)
    ch = await db.podcast_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "channel_not_found")
    if user.get("role") == "admin":
        return ch
    creator = await svc.require_approved_creator(db, user)
    if ch.get("creator_id") != creator["id"]:
        raise HTTPException(403, "not_your_channel")
    return ch


# Phase 19b — security sweep helpers (admin-first, ownership-enforcing).
async def _own_session_or_403(db, user, sid: str) -> dict:
    sess = await db.podcast_recording_sessions.find_one({"id": sid})
    if not sess: raise HTTPException(404, "session_not_found")
    if user.get("role") == "admin": return sess
    creator = await svc.require_approved_creator(db, user)
    if sess.get("creator_id") != creator["id"]:
        raise HTTPException(403, "not_your_session")
    return sess


async def _own_episode_or_403(db, user, eid: str) -> dict:
    ep = await db.podcast_episodes.find_one({"id": eid})
    if not ep: raise HTTPException(404, "episode_not_found")
    ch = await db.podcast_channels.find_one({"id": ep.get("channel_id")})
    if not ch: raise HTTPException(404, "channel_not_found")
    if user.get("role") == "admin": return ep
    creator = await svc.require_approved_creator(db, user)
    if ch.get("creator_id") != creator["id"]:
        raise HTTPException(403, "not_your_episode")
    return ep


def _settings_subset(ch: dict) -> dict:
    out = {"id": ch["id"], "title": ch.get("title"),
              "creator_id": ch.get("creator_id")}
    for k in _SETTINGS_FIELDS:
        if k == "magic_clips_enabled":
            out[k] = ch.get(k, True) is not False
        elif k == "magic_clips_per_episode":
            v = ch.get(k)
            try:
                out[k] = int(v) if v is not None else 5
            except Exception:
                out[k] = 5
        else:
            out[k] = ch.get(k)
    return out


@podcasts_router.get("/channels/{channel_id}/settings")
async def get_channel_settings(channel_id: str, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    ch = await _own_channel_or_403(db, user, channel_id)
    return _settings_subset(ch)


@podcasts_router.patch("/channels/{channel_id}/settings")
async def patch_channel_settings(channel_id: str, body: dict, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    upd: dict = {}
    if "magic_clips_enabled" in body:
        upd["magic_clips_enabled"] = bool(body["magic_clips_enabled"])
    if "magic_clips_per_episode" in body:
        try:
            n = int(body["magic_clips_per_episode"])
        except Exception:
            raise HTTPException(400, "magic_clips_per_episode must be an integer")
        if not (1 <= n <= 15):
            raise HTTPException(400, "magic_clips_per_episode must be between 1 and 15")
        upd["magic_clips_per_episode"] = n
    if not upd:
        raise HTTPException(400, "no editable fields supplied")
    upd["updated_at"] = datetime.now(timezone.utc)
    await db.podcast_channels.update_one({"id": channel_id}, {"$set": upd})
    ch = await db.podcast_channels.find_one({"id": channel_id})
    return _settings_subset(ch)


# ─── Channel (public read) ───────────────────────────────────────
@podcasts_router.get("/channels/{channel_id}")
async def get_channel_public(channel_id: str, request: Request,
                                                          user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    ch = await db.podcast_channels.find_one({"id": channel_id}, {"_id": 0})
    if not ch: raise HTTPException(404, "channel_not_found")
    if not ch.get("active") or ch.get("approval_status") != "approved":
        raise HTTPException(404, "channel_not_published")
    eps = await db.podcast_episodes.find(
        {"channel_id": channel_id, "publish_status": "published"},
        {"_id": 0}).sort("published_at", -1).to_list(100)
    # Phase 36e Turn 2 — funnel: channel_visit event for logged-in non-creator
    # listeners. Anon visits not counted. Best-effort (never block the request).
    if user and user.get("user_id") and ch.get("creator_id"):
        try:
            from services import funnel as _fn
            creator_doc = await db.podcast_creators.find_one(
                {"id": ch["creator_id"]}, {"_id": 0, "user_id": 1})
            if not creator_doc or creator_doc.get("user_id") != user.get("user_id"):
                await _fn.record_event(db, event_type="channel_visit",
                    listener_user_id=user["user_id"], channel_id=channel_id)
        except Exception as e:
            logger.warning("[36e/turn2] channel_visit emit failed: %s", e)
    return {"channel": ch, "episodes": eps,
              "followers": await svc.get_followers_count(db, channel_id=channel_id)}


@podcasts_router.get("/discover")
async def discover(request: Request,
                              category: Optional[str] = None,
                              market: Optional[str] = None,
                              q: Optional[str] = None,
                              limit: int = 24):
    db = request.app.state.db
    f: dict = {"active": True, "approval_status": "approved"}
    if category: f["category"] = category
    if q:
        f["$or"] = [{"title":          {"$regex": q, "$options": "i"}},
                          {"description": {"$regex": q, "$options": "i"}}]
    rows = await db.podcast_channels.find(f, {"_id": 0}) \
        .sort("follower_count", -1).limit(min(int(limit), 100)).to_list(100)
    return {"channels": rows}


# ─── Episodes ────────────────────────────────────────────────────
@podcasts_router.post("/channels/{channel_id}/episodes")
async def upload_episode(channel_id: str, request: Request,
                                              title: str = Form(...),
                                              description: str = Form(""),
                                              show_notes: str = Form(""),
                                              season: int = Form(1),
                                              episode_number: int = Form(0),
                                              episode_type: str = Form("full"),
                                              explicit_flag: bool = Form(False),
                                              audio_url_external: Optional[str] = Form(None),
                                              audio: Optional[UploadFile] = File(None),
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    ch = await _own_channel_or_403(db, user, channel_id)
    audio_bytes = None; filename = "audio.mp3"
    if audio is not None:
        audio_bytes = await audio.read()
        filename     = audio.filename or filename
        if len(audio_bytes) > 500 * 1024 * 1024:
            raise HTTPException(413, "audio_too_large_500MB")
    # Phase 36a hardening: reject zero-content episodes EARLY (was 200+zombie row).
    # Accept only when a non-empty uploaded audio file is present OR an
    # external audio_url_external is provided (for the RSS-import re-publish
    # path).  Wrong form field name (e.g. `audio_file=` instead of `audio=`)
    # → `audio` is None → 422 here.
    has_upload = bool(audio_bytes)
    has_external = bool((audio_url_external or "").startswith("http"))
    if not has_upload and not has_external:
        raise HTTPException(422, {
            "code":        "audio_required",
            "message": "Audio file is required and must be non-empty. "
                              "Use form field name 'audio' (mp3/m4a/wav) "
                              "or pass `audio_url_external` for RSS re-publish."})
    ep = await svc.ingest_episode_upload(
        db, channel_id=channel_id,
        body={"title": title, "description": description, "show_notes": show_notes,
                "season": season, "episode_number": episode_number,
                "episode_type": episode_type, "explicit_flag": explicit_flag,
                "audio_url_external": audio_url_external},
        audio_bytes=audio_bytes, audio_filename=filename)
    # Defense in depth: if ingestion produced a duration-less, zero-byte
    # local row (corrupted upload, ffmpeg failure, transcode skipped),
    # roll it back and 422 — never persist a zombie episode.
    if has_upload and (not ep.get("file_size_bytes") or not ep.get("duration_seconds")):
        await db.podcast_episodes.delete_one({"id": ep["id"]})
        raise HTTPException(422, {
            "code":        "audio_unreadable",
            "message": "Audio file could not be transcoded or has zero duration."})
    ep.pop("_id", None)
    return ep


# Phase P2 — pagination envelope helper. Returns (limit, offset). 400s on
# out-of-range. Default 50, max 200.
def _paginate(limit: Optional[int], cursor: Optional[str]) -> tuple[int, int]:
    lim = 50 if limit is None else int(limit)
    if lim < 1 or lim > 200:
        raise HTTPException(400, "limit_out_of_range")
    off = 0
    if cursor:
        try: off = max(0, int(cursor))
        except Exception: raise HTTPException(400, "limit_out_of_range")
    return lim, off


@podcasts_router.get("/channels/{channel_id}/episodes")
async def list_episodes(channel_id: str, request: Request,
                                          include_drafts: bool = False,
                                          limit: Optional[int] = Query(None),
                                          cursor: Optional[str] = Query(None),
                                          user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    lim, off = _paginate(limit, cursor)
    q = {"channel_id": channel_id}
    if not include_drafts: q["publish_status"] = "published"
    total_seen = await db.podcast_episodes.count_documents(q)
    rows = await db.podcast_episodes.find(q, {"_id": 0}) \
        .sort("published_at", -1).skip(off).limit(lim).to_list(lim)
    next_cursor = str(off + lim) if (off + lim) < total_seen else None
    # Phase 19: legacy `episodes` alias removed (Phase 22b cleanup).
    return {"items": rows, "next_cursor": next_cursor,
                  "total_seen": total_seen}


@podcasts_router.patch("/channels/{channel_id}/episodes/{ep_id}")
async def patch_episode(channel_id: str, ep_id: str, body: dict,
                                          request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    allowed = {"title", "description", "show_notes", "tags", "explicit_flag",
                  "season", "episode_number", "episode_type",
                  "subscriber_only", "scheduled_publish_time", "cover_image_url",
                  "is_bonus", "release_for_subscribers_at"}
    upd = {k: v for k, v in (body or {}).items() if k in allowed}
    # Phase 36e Turn 1 — coerce/validate paywall-surface fields.
    if "is_bonus" in upd:
        if not isinstance(upd["is_bonus"], bool):
            raise HTTPException(400, "is_bonus_must_be_bool")
    if "release_for_subscribers_at" in upd:
        v = upd["release_for_subscribers_at"]
        if v is None:
            upd["release_for_subscribers_at"] = None
        elif isinstance(v, str):
            try:
                upd["release_for_subscribers_at"] = datetime.fromisoformat(
                    v.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(400, "release_for_subscribers_at_invalid_iso8601")
        else:
            raise HTTPException(400, "release_for_subscribers_at_invalid_iso8601")
    upd["updated_at"] = datetime.now(timezone.utc)
    r = await db.podcast_episodes.find_one_and_update(
        {"id": ep_id, "channel_id": channel_id}, {"$set": upd},
        return_document=True)
    if not r: raise HTTPException(404, "episode_not_found")
    r.pop("_id", None)
    await svc.invalidate_feed_cache(db, channel_id=channel_id)
    return r


@podcasts_router.post("/channels/{channel_id}/episodes/{ep_id}/publish")
async def publish_ep(channel_id: str, ep_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    r = await svc.publish_episode(db, ep_id=ep_id)
    if not r: raise HTTPException(404, "episode_not_found")
    r.pop("_id", None)
    # Phase 36e Turn 3 — first-episode nudge gate. Best-effort.
    try:
        from services import nudges as _nudges
        await _nudges.mark_first_episode_published(db, channel_id=channel_id)
    except Exception as e:
        logger.warning("[36e/turn3] first-episode hook failed: %s", e)
    # Phase 36b — auto-fire transcription on publish. Best-effort.
    try:
        from services import podcast_transcription as tx
        await tx.kick_transcription(db, episode_id=ep_id)
    except Exception as e:
        logger.warning("[36b] auto-transcribe on publish failed: %s", e)
    # Phase 36d — auto-fire magic-clip generation on publish. Best-effort.
    try:
        from services import podcast_clips as pc
        import asyncio as _aio
        _aio.create_task(pc.generate_clips(db, episode_id=ep_id, count=3))
    except Exception as e:
        logger.warning("[36d] auto-clip on publish failed: %s", e)
    return r


@podcasts_router.delete("/channels/{channel_id}/episodes/{ep_id}")
async def delete_ep(channel_id: str, ep_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    r = await svc.archive_episode(db, ep_id=ep_id)
    if not r: raise HTTPException(404, "episode_not_found")
    return {"ok": True}


@podcasts_router.get("/episodes/{ep_id}")
async def get_episode_public(ep_id: str, request: Request):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one(
        {"id": ep_id, "publish_status": "published"}, {"_id": 0})
    if not ep: raise HTTPException(404, "episode_not_found")
    return ep


@podcasts_router.api_route(
    "/episodes/{ep_id}/audio.mp3", methods=["GET", "HEAD"])
async def stream_episode_audio(ep_id: str, request: Request):
    """Phase 36a — Apple Podcasts / Overcast / Pocket Casts send HEAD
    before downloading enclosures, and most clients use byte-range
    requests for seek/resume.  We support BOTH on the same route:
      - HEAD → 200 with Content-Length + Accept-Ranges; no body.
      - GET no Range → 200 full body, Accept-Ranges: bytes.
      - GET with Range: bytes=A-B → 206 Partial Content + Content-Range.
    For externally-hosted (RSS-imported) episodes we 302 to the source
    URL; HEAD on a 302 is acceptable to Apple and Overcast."""
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one({"id": ep_id})
    if not ep: raise HTTPException(404, "episode_not_found")
    storage = ep.get("storage_path")
    audio_path: Optional[str] = None
    if storage:
        cand = f"{storage}/audio.mp3"
        if Path(cand).is_file():
            audio_path = cand
    # Phase 36c.5 — Tigris fallback. When the local file is gone (migrated),
    # resolve the canonical key + stream via the ObjectStorage backend's
    # range API. Preserves HEAD/Range/Content-Length contract.
    if audio_path is None:
        from services import object_storage as obs
        key = ep.get("storage_key_audio") or obs.key_episode_audio(
            ep.get("channel_id") or "_", ep_id)
        # If the recording came from a session, also try the mixed key.
        sid_key = (obs.key_recording_mixed_audio(ep.get("recording_session_id"))
                          if ep.get("recording_session_id") else None)
        st = obs.get_storage()
        head = st.head(key=key) or (st.head(key=sid_key) if sid_key else None)
        if head:
            resolved_key = key if st.head(key=key) else sid_key
            size = int(head.get("size") or 0)
            media_type = "audio/mpeg"
            headers = {"Accept-Ranges": "bytes",
                              "Content-Length": str(size),
                              "Content-Type":     media_type,
                              "Cache-Control":   "public, max-age=300"}
            if request.method == "HEAD":
                return Response(status_code=200, headers=headers, media_type=media_type)
            rng = request.headers.get("range") or request.headers.get("Range")
            a, b = 0, size - 1
            status = 200
            if rng and rng.startswith("bytes="):
                try:
                    spec = rng[len("bytes="):].split(",")[0].strip()
                    aS, bS = (spec.split("-") + [""])[:2]
                    a = int(aS) if aS else 0
                    b = int(bS) if bS else size - 1
                    if a < 0 or b >= size or a > b:
                        return Response(status_code=416,
                                                      headers={"Content-Range": f"bytes */{size}"})
                    status = 206
                except (ValueError, IndexError): a, b = 0, size - 1
            buf = st.open_range(key=resolved_key, start=a, end=b)
            hdrs = dict(headers); hdrs["Content-Length"] = str(len(buf))
            if status == 206: hdrs["Content-Range"] = f"bytes {a}-{b}/{size}"
            return Response(content=buf, status_code=status, headers=hdrs,
                                          media_type=media_type)
        if ep.get("audio_url_external"):
            return Response(status_code=302,
                                  headers={"Location": ep["audio_url_external"]})
        raise HTTPException(404, "audio_not_available")
    import os as _os
    size = _os.path.getsize(audio_path)
    media_type = "audio/mpeg"
    headers = {"Accept-Ranges":   "bytes",
                      "Content-Length": str(size),
                      "Content-Type":     media_type,
                      "Cache-Control":   "public, max-age=300"}
    if request.method == "HEAD":
        return Response(status_code=200, headers=headers,
                              media_type=media_type)
    # GET — handle Range if present.
    rng = request.headers.get("range") or request.headers.get("Range")
    if rng and rng.startswith("bytes="):
        try:
            spec = rng[len("bytes="):].split(",")[0].strip()
            a_s, b_s = (spec.split("-") + [""])[:2]
            a = int(a_s) if a_s else 0
            b = int(b_s) if b_s else size - 1
            if a < 0 or b >= size or a > b:
                return Response(status_code=416, headers={
                    "Content-Range": f"bytes */{size}"})
            length = b - a + 1
            with open(audio_path, "rb") as f:
                f.seek(a); buf = f.read(length)
            hdrs = dict(headers)
            hdrs["Content-Length"] = str(length)
            hdrs["Content-Range"]  = f"bytes {a}-{b}/{size}"
            return Response(content=buf, status_code=206, headers=hdrs,
                                  media_type=media_type)
        except (ValueError, IndexError):
            pass    # malformed range → fall through to full body
    return FileResponse(audio_path, media_type=media_type, headers=headers)


# ─── Phase 36c Stage 3 — Episode video.mp4 HEAD + Range (Tigris-only) ─
@podcasts_router.api_route(
    "/episodes/{ep_id}/video.mp4", methods=["GET", "HEAD"])
async def stream_episode_video(ep_id: str, request: Request):
    """Mirror of audio.mp3 for the video grid output. Backed exclusively
    by Tigris (no local-disk fallback because Stage 3 video files are
    big and always offloaded post-finalize). Returns 404 if the
    episode has no video_url or the Tigris key is missing."""
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one({"id": ep_id})
    if not ep: raise HTTPException(404, "episode_not_found")
    if not ep.get("video_url"):
        raise HTTPException(404, "video_not_available")
    from services import object_storage as obs
    keys: list = []
    if ep.get("storage_key_video"): keys.append(ep["storage_key_video"])
    keys.append(obs.key_episode_video(ep.get("channel_id") or "_", ep_id))
    if ep.get("recording_session_id"):
        keys.append(obs.key_recording_mixed_video(
            ep["recording_session_id"]))
    st = obs.get_storage()
    resolved_key: Optional[str] = None
    head: Optional[dict] = None
    for k in keys:
        h = st.head(key=k)
        if h: resolved_key, head = k, h; break
    if not head:
        raise HTTPException(404, "video_not_available")
    size = int(head.get("size") or 0)
    media_type = "video/mp4"
    headers = {"Accept-Ranges": "bytes",
                      "Content-Length": str(size),
                      "Content-Type":     media_type,
                      "Cache-Control":   "public, max-age=300"}
    if request.method == "HEAD":
        return Response(status_code=200, headers=headers,
                              media_type=media_type)
    rng = request.headers.get("range") or request.headers.get("Range")
    a, b, status = 0, size - 1, 200
    if rng and rng.startswith("bytes="):
        try:
            spec = rng[len("bytes="):].split(",")[0].strip()
            aS, bS = (spec.split("-") + [""])[:2]
            a = int(aS) if aS else 0
            b = int(bS) if bS else size - 1
            if a < 0 or b >= size or a > b:
                return Response(status_code=416,
                                              headers={"Content-Range": f"bytes */{size}"})
            status = 206
        except (ValueError, IndexError): a, b = 0, size - 1
    buf = st.open_range(key=resolved_key, start=a, end=b)
    hdrs = dict(headers); hdrs["Content-Length"] = str(len(buf))
    if status == 206: hdrs["Content-Range"] = f"bytes {a}-{b}/{size}"
    return Response(content=buf, status_code=status, headers=hdrs,
                                  media_type=media_type)



# ─── Distribution ──────────────────────────────────────────────
@podcasts_router.get("/channels/{channel_id}/distribution")
async def get_distrib(channel_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    return {"checklist": await svc.get_distribution(db, channel_id=channel_id)}


@podcasts_router.post("/channels/{channel_id}/distribution/submit")
async def post_distrib(channel_id: str, body: dict, request: Request,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    r = await svc.submit_distribution(
        db, channel_id=channel_id,
        platform=(body.get("platform") or "").lower(),
        submission_url=body.get("submission_url"),
        platform_show_url=body.get("platform_show_url"))
    r.pop("_id", None)
    return r


# ─── Feed (admin/creator-side validate + RSS XML) ────────────────
@podcasts_router.get("/channels/{channel_id}/rss")
async def channel_rss(channel_id: str, request: Request):
    db = request.app.state.db
    xml = await rss_svc.get_or_build_xml(db, channel_id=channel_id)
    return Response(xml, media_type="application/rss+xml",
                          headers={"Cache-Control": "public, max-age=300"})


@podcasts_router.post("/channels/{channel_id}/feeds/validate")
async def validate_feed(channel_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    xml = await rss_svc.get_or_build_xml(db, channel_id=channel_id)
    return rss_svc.validate_feed(xml)


# ─── RSS import (migration from other host) ─────────────────────
@podcasts_router.post("/channels/{channel_id}/import-rss")
async def import_rss(channel_id: str, body: dict, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    url = (body or {}).get("rss_url") or ""
    if not url.startswith("http"):
        raise HTTPException(400, "rss_url_required")
    try:
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.get(url, follow_redirects=True)
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
    except Exception as e:
        raise HTTPException(400, f"fetch_failed:{e}")
    imported, skipped, errors = 0, 0, []
    # Phase 19b — cap entries to prevent DoS via hostile RSS feed.
    all_entries = parsed.entries or []
    total_seen = len(all_entries)
    entries = all_entries[:500]
    truncated = total_seen > 500
    for e in entries:
        guid = e.get("guid") or e.get("id") or e.get("link")
        if not guid:
            errors.append({"title": e.get("title"), "reason": "no_guid"})
            continue
        if await db.podcast_episodes.find_one(
                {"channel_id": channel_id, "guid": guid}):
            skipped += 1; continue
        enc = (e.get("enclosures") or [{}])[0].get("href")
        await db.podcast_episodes.insert_one({
            "id":                    svc._gen("pep"),
            "channel_id":     channel_id,
            "guid":                guid,
            "title":                e.get("title") or "Imported episode",
            "description":  e.get("summary") or "",
            "show_notes":  e.get("content", [{}])[0].get("value", "") if e.get("content") else "",
            "tags":                [],
            "audio_url":      None,
            "audio_url_external": enc,
            "duration_seconds":  None,
            "file_size_bytes":    int((e.get("enclosures") or [{}])[0].get("length") or 0),
            "season":              1,
            "episode_number":  0,
            "episode_type":     "full",
            "explicit_flag":     False,
            "publish_status":   "imported_draft",
            "published_at":      datetime(*e.get("published_parsed")[:6], tzinfo=timezone.utc)
                                                if e.get("published_parsed") else None,
            "source":                "rss_import",
            "storage_path":     None,
            "created_at":           datetime.now(timezone.utc),
            "updated_at":          datetime.now(timezone.utc),
        })
        imported += 1
    out = {"imported_count": imported, "skipped_duplicates": skipped,
                "errors": errors, "total_seen": total_seen}
    if truncated:
        out["warning"] = "truncated_to_500"
    return out


@podcasts_router.post("/channels/{channel_id}/redirect")
async def channel_redirect(channel_id: str, body: dict, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    new_url = (body or {}).get("new_feed_url")
    if not new_url: raise HTTPException(400, "new_feed_url_required")
    await db.podcast_channels.update_one(
        {"id": channel_id}, {"$set": {"new_feed_url": new_url}})
    await svc.invalidate_feed_cache(db, channel_id=channel_id)
    return {"ok": True}


# ─── Follow ────────────────────────────────────────────────────
@podcasts_router.post("/channels/{channel_id}/follow")
async def follow_channel(channel_id: str, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.podcast_followers.update_one(
        {"user_id": user["user_id"], "channel_id": channel_id},
        {"$setOnInsert": {"user_id": user["user_id"],
                                      "channel_id": channel_id,
                                      "followed_at": datetime.now(timezone.utc)}},
        upsert=True)
    if r.upserted_id is not None:
        await db.podcast_channels.update_one(
            {"id": channel_id}, {"$inc": {"follower_count": 1}})
    return {"ok": True}


# ─── Admin moderation queue ───────────────────────────────────
@admin_podcasts_router.get("/creator-applications")
async def admin_list_applications(request: Request,
                                                          status: str = Query("pending"),
                                                          _: dict = Depends(require_admin)):
    rows = await request.app.state.db.podcast_creators.find(
        {"application_status": status}, {"_id": 0}) \
        .sort("applied_at", -1).to_list(200)
    return {"applications": rows}


@admin_podcasts_router.post("/creator-applications/{cid}/approve")
async def admin_approve(cid: str, request: Request,
                                          admin: dict = Depends(require_admin)):
    r = await svc.approve_creator(request.app.state.db,
                                                        creator_id=cid,
                                                        admin_user_id=admin["user_id"])
    if not r: raise HTTPException(404, "application_not_found")
    r.pop("_id", None)
    return r


@admin_podcasts_router.post("/creator-applications/{cid}/reject")
async def admin_reject(cid: str, body: dict, request: Request,
                                        admin: dict = Depends(require_admin)):
    r = await svc.reject_creator(request.app.state.db,
                                                      creator_id=cid,
                                                      admin_user_id=admin["user_id"],
                                                      reason=(body or {}).get("reason") or "")
    if not r: raise HTTPException(404, "application_not_found")
    r.pop("_id", None)
    return r


@admin_podcasts_router.get("/channels")
async def admin_list_channels(request: Request,
                                                    approval_status: Optional[str] = None,
                                                    limit: Optional[int] = Query(None),
                                                    cursor: Optional[str] = Query(None),
                                                    _: dict = Depends(require_admin)):
    lim, off = _paginate(limit, cursor)
    q: dict = {}
    if approval_status: q["approval_status"] = approval_status
    db = request.app.state.db
    total_seen = await db.podcast_channels.count_documents(q)
    rows = await db.podcast_channels.find(q, {"_id": 0}) \
        .sort("created_at", -1).skip(off).limit(lim).to_list(lim)
    next_cursor = str(off + lim) if (off + lim) < total_seen else None
    # Legacy `channels` key retained one release cycle.
    return {"items": rows, "next_cursor": next_cursor,
                  "total_seen": total_seen, "channels": rows}


@admin_podcasts_router.post("/channels/{ch_id}/approve")
async def admin_channel_approve(ch_id: str, request: Request,
                                                            _: dict = Depends(require_admin)):
    r = await request.app.state.db.podcast_channels.find_one_and_update(
        {"id": ch_id},
        {"$set": {"approval_status": "approved", "active": True,
                      "approved_at": datetime.now(timezone.utc)}},
        return_document=True)
    if not r: raise HTTPException(404, "channel_not_found")
    r.pop("_id", None)
    return r


@admin_podcasts_router.post("/channels/{ch_id}/reject")
async def admin_channel_reject(ch_id: str, body: dict, request: Request,
                                                        _: dict = Depends(require_admin)):
    r = await request.app.state.db.podcast_channels.find_one_and_update(
        {"id": ch_id},
        {"$set": {"approval_status": "rejected", "active": False,
                      "rejection_reason": (body or {}).get("reason") or ""}},
        return_document=True)
    if not r: raise HTTPException(404, "channel_not_found")
    r.pop("_id", None)
    return r


# ─── Public root paths: /podcasts/{slug}/rss.xml ────────────────
@podcasts_public_router.get("/podcasts/{slug}/rss.xml")
async def public_rss(slug: str, request: Request):
    db = request.app.state.db
    ch = await db.podcast_channels.find_one({"slug": slug}, {"id": 1, "_id": 0})
    if not ch:
        return Response('<?xml version="1.0"?><rss version="2.0"><channel/></rss>',
                              media_type="application/rss+xml", status_code=404)
    xml = await rss_svc.get_or_build_xml(db, channel_id=ch["id"])
    return Response(xml, media_type="application/rss+xml",
                          headers={"Cache-Control": "public, max-age=300"})


# ═══════════════════════════════════════════════════════════════════
# Phase 36b — Transcription + AI metadata + chapters.json + transcript.srt
# ═══════════════════════════════════════════════════════════════════

@podcasts_router.post("/episodes/{ep_id}/transcribe")
async def post_transcribe(ep_id: str, request: Request,
                                            user: dict = Depends(current_user)):
    """Creator force-transcribe (e.g. for an imported episode)."""
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    from services import podcast_transcription as tx
    r = await tx.kick_transcription(db, episode_id=ep_id)
    if isinstance(r, dict):
        r.pop("_id", None)
    return r


@podcasts_router.get("/episodes/{ep_id}/transcript")
async def get_transcript_route(ep_id: str, request: Request):
    """Returns the latest transcript row for the episode (public read).
    Returns 404 if no transcript has been kicked yet.

    Phase 36b round-2: expose `utterances` alongside the legacy
    `utterances_json` key. `utterances_json` is kept for one release cycle
    as a deprecation buffer for the mobile + creator UI."""
    db = request.app.state.db
    from services import podcast_transcription as tx
    r = await tx.get_transcript(db, episode_id=ep_id)
    if not r:
        raise HTTPException(404, "transcript_not_found")
    # Alias the DB column name to a cleaner API key.
    r["utterances"] = r.get("utterances_json") or []
    return r


@podcasts_router.patch("/episodes/{ep_id}/transcript")
async def patch_transcript_route(ep_id: str, body: dict, request: Request,
                                                            user: dict = Depends(current_user)):
    """Creator edits the transcript text. Collapses utterances into a
    single 'edited' block and flips manual_edit=True."""
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    from services import podcast_transcription as tx
    try:
        r = await tx.patch_transcript_text(
            db, episode_id=ep_id, text=(body or {}).get("text") or "")
    except ValueError as e:
        raise HTTPException(404, str(e))
    r.pop("_id", None)
    return r


@podcasts_router.post("/episodes/{ep_id}/ai/generate-metadata")
async def post_generate_metadata(ep_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    from services import podcast_ai_metadata as ai_md
    out = await ai_md.generate_metadata(db, episode_id=ep_id)
    return {"metadata": out}


@podcasts_router.get("/episodes/{ep_id}/ai/history")
async def get_ai_history(ep_id: str, request: Request,
                                          user: dict = Depends(current_user),
                                          limit: int = Query(20, ge=1, le=100)):
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    from services import podcast_ai_metadata as ai_md
    rows = await ai_md.list_history(db, episode_id=ep_id, limit=limit)
    return {"history": rows}


@podcasts_router.post("/episodes/{ep_id}/apply-metadata")
async def post_apply_metadata(ep_id: str, body: dict, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    from services import podcast_ai_metadata as ai_md
    try:
        r = await ai_md.apply_metadata(db, episode_id=ep_id, body=body or {})
    except ValueError as e:
        raise HTTPException(404, str(e))
    if r: r.pop("_id", None)
    return r


@admin_podcasts_router.post("/episodes/{ep_id}/retranscribe")
async def admin_retranscribe(ep_id: str, request: Request,
                                                      _: dict = Depends(require_admin)):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one({"id": ep_id}, {"_id": 0})
    if not ep: raise HTTPException(404, "episode_not_found")
    # Soft-archive prior rows so a new run kicks fresh.
    await db.podcast_transcripts.update_many(
        {"episode_id": ep_id, "status": {"$in": ["pending", "processing"]}},
        {"$set": {"status": "error",
                      "error_message": "superseded_by_admin_retranscribe"}})
    from services import podcast_transcription as tx
    r = await tx.kick_transcription(db, episode_id=ep_id)
    if isinstance(r, dict): r.pop("_id", None)
    return r


# ─── Public chapters.json + transcript.srt ────────────────────────
@podcasts_router.get("/episodes/{ep_id}/chapters.json")
async def get_chapters_json(ep_id: str, request: Request):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one({"id": ep_id}, {"_id": 0})
    if not ep: raise HTTPException(404, "episode_not_found")
    chapters = ep.get("chapters") or []
    payload = {
        "version":   "1.2.0",     # Podcasting 2.0 chapters spec
        "title":       ep.get("title") or "",
        "podcastName": "",
        "chapters":  [
            {"startTime": float(c.get("start_time_seconds") or 0),
              "endTime":     float(c.get("end_time_seconds") or 0),
              "title":           c.get("title") or "",
              "img":             ep.get("cover_image_url") or ""}
            for c in chapters
        ],
    }
    return payload


@podcasts_router.get("/episodes/{ep_id}/transcript.srt")
async def get_transcript_srt(ep_id: str, request: Request):
    db = request.app.state.db
    from services import podcast_transcription as tx
    r = await tx.get_transcript(db, episode_id=ep_id)
    if not r or r.get("status") != "completed":
        raise HTTPException(404, "transcript_not_completed")
    srt = tx.utterances_to_srt(r.get("utterances_json") or [])
    return PlainTextResponse(srt, media_type="application/x-subrip",
                                            headers={"Cache-Control": "public, max-age=300"})


# ─── Admin: AssemblyAI integration status ─────────────────────────
@admin_podcasts_router.get("/integrations/assemblyai/status")
async def admin_assemblyai_status(request: Request,
                                                            _: dict = Depends(require_admin)):
    from services import assemblyai_client as aai
    return {
        "is_live":             aai.is_live(),
        "api_key_present": aai.is_live(),
        "last_check_at": datetime.now(timezone.utc).isoformat(),
        "provider":         "assemblyai",
        "mode":                  "live" if aai.is_live() else "mock",
    }


# ═══════════════════════════════════════════════════════════════════
# Phase 36c Stage 1 — Solo Audio Recording Studio
# ═══════════════════════════════════════════════════════════════════

@podcasts_router.post("/creators/{cid}/recording-sessions")
async def post_create_recording_session(cid: str, body: dict, request: Request,
                                                                                user: dict = Depends(current_user),
                                                                                force_mock: int = Query(0)):
    db = request.app.state.db
    creator = await svc.require_approved_creator(db, user)
    if creator["id"] != cid:
        raise HTTPException(403, "creator_mismatch")
    await _own_channel_or_403(db, user, body.get("channel_id") or "")
    # Phase 36c Stage 2 — `?force_mock=1` is an admin-only canary flag. For
    # non-admins it's a silent no-op (we still create the session, just on
    # the normal live-or-mock path).
    fm = bool(force_mock) and user.get("role") == "admin"
    from services import podcast_recording as rec
    return await rec.create_session(
        db,
        creator_id=cid,
        channel_id=body["channel_id"],
        title=(body.get("title") or "Untitled Recording")[:200],
        recording_mode=(body.get("recording_mode") or "solo"),
        user_id=user.get("user_id"),
        force_mock=fm,
        video_enabled=bool(body.get("video_enabled")),
        grid_layout=(body.get("grid_layout") or "auto"))


@podcasts_router.post("/recording-sessions/{sid}/start")
async def post_start_recording_session(sid: str, request: Request,
                                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_recording as rec
    return await rec.start_session(db, session_id=sid)


@podcasts_router.post("/recording-sessions/{sid}/stop")
async def post_stop_recording_session(sid: str, body: dict, request: Request,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_recording as rec
    return await rec.stop_session(db, session_id=sid,
        client_duration_seconds=float((body or {}).get("client_duration_seconds") or 0))


@podcasts_router.post("/recording-sessions/{sid}/upload-track")
async def post_upload_track(sid: str, request: Request,
                                                  user: dict = Depends(current_user),
                                                  audio: UploadFile = File(...),
                                                  video: Optional[UploadFile] = File(None),
                                                  screen: Optional[UploadFile] = File(None),
                                                  participant_role: str = Form("host"),
                                                  client_duration_seconds: float = Form(0),
                                                  participant_id: Optional[str] = Form(None)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_recording as rec
    role = participant_role if participant_role in ("host", "guest") else "host"
    return await rec.upload_track(db, session_id=sid, role=role,
                                                              upload=audio, user_id=user.get("user_id"),
                                                              client_duration_seconds=float(
                                                                  client_duration_seconds or 0),
                                                              participant_id=participant_id,
                                                              video_upload=video,
                                                              screen_upload=screen)


# Phase 36c Stage 2 — Public guest upload (no auth, uses ws_token). The
# studio guest landing-page uploads through this endpoint after the host
# ends the session.
@podcasts_router.post("/studio/{sid}/upload-track")
async def post_public_guest_upload_track(sid: str, request: Request,
                                                                              audio: UploadFile = File(...),
                                                                              video: Optional[UploadFile] = File(None),
                                                                              screen: Optional[UploadFile] = File(None),
                                                                              ws_token: str = Form(...),
                                                                              participant_id: str = Form(...),
                                                                              client_duration_seconds: float = Form(0)):
    db = request.app.state.db
    p = await db.podcast_recording_participants.find_one(
        {"id": participant_id, "session_id": sid, "ws_token": ws_token})
    if not p: raise HTTPException(401, "invalid_ws_token")
    if p.get("role") != "guest":
        raise HTTPException(403, "only_guests_use_this_endpoint")
    from services import podcast_recording as rec
    return await rec.upload_track(db, session_id=sid, role="guest",
                                                              upload=audio,
                                                              client_duration_seconds=float(
                                                                  client_duration_seconds or 0),
                                                              participant_id=participant_id,
                                                              video_upload=video,
                                                              screen_upload=screen)


# ─── Phase 36d — Magic clips, action cards, Lightning splits ───────


@podcasts_router.post("/episodes/{ep_id}/clips/generate")
async def post_clips_generate(ep_id: str, request: Request,
                                                            user: dict = Depends(current_user),
                                                            count: int = 3):
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    from services import podcast_clips as pc
    return await pc.generate_clips(db, episode_id=ep_id, count=int(count))


@podcasts_router.get("/episodes/{ep_id}/clips")
async def get_clips(ep_id: str, request: Request):
    db = request.app.state.db
    rows = await db.podcast_clips.find(
        {"episode_id": ep_id},
        {"_id": 0}).sort("start_seconds", 1).to_list(50)
    return {"episode_id": ep_id, "clips": rows}


@podcasts_router.patch("/episodes/{ep_id}/clips/{clip_id}")
async def patch_clip(ep_id: str, clip_id: str, request: Request,
                                          user: dict = Depends(current_user),
                                          body: dict = Body(...)):
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    # Verify clip actually belongs to this episode (path consistency).
    existing = await db.podcast_clips.find_one(
        {"id": clip_id, "episode_id": ep_id}, {"_id": 0, "id": 1})
    if not existing: raise HTTPException(404, "clip_not_found")
    upd = {k: body[k] for k in ("start_seconds", "end_seconds", "why",
                                                                "status", "video_url") if k in body}
    if upd:
        from datetime import datetime, timezone
        upd["updated_at"] = datetime.now(timezone.utc)
        await db.podcast_clips.update_one(
            {"id": clip_id, "episode_id": ep_id}, {"$set": upd})
    return await db.podcast_clips.find_one(
        {"id": clip_id, "episode_id": ep_id}, {"_id": 0})


@podcasts_router.api_route("/clips/{clip_id}/audio.mp3", methods=["GET", "HEAD"])
async def stream_clip_audio(clip_id: str, request: Request):
    db = request.app.state.db
    clip = await db.podcast_clips.find_one({"id": clip_id})
    if not clip: raise HTTPException(404, "clip_not_found")
    from services import object_storage as obs
    st = obs.get_storage()
    key = clip.get("storage_key")
    head = st.head(key=key) if key else None
    if not head: raise HTTPException(404, "clip_audio_missing")
    size = int(head.get("size") or 0)
    headers = {"Accept-Ranges": "bytes",
                      "Content-Length": str(size),
                      "Content-Type":     "audio/mpeg",
                      "Cache-Control":   "public, max-age=300"}
    if request.method == "HEAD":
        return Response(status_code=200, headers=headers,
                              media_type="audio/mpeg")
    rng = request.headers.get("range") or request.headers.get("Range")
    a, b, status = 0, size - 1, 200
    if rng and rng.startswith("bytes="):
        try:
            spec = rng[len("bytes="):].split(",")[0].strip()
            aS, bS = (spec.split("-") + [""])[:2]
            a = int(aS) if aS else 0
            b = int(bS) if bS else size - 1
            if a < 0 or b >= size or a > b:
                return Response(status_code=416,
                                              headers={"Content-Range": f"bytes */{size}"})
            status = 206
        except (ValueError, IndexError): a, b = 0, size - 1
    buf = st.open_range(key=key, start=a, end=b)
    hdrs = dict(headers); hdrs["Content-Length"] = str(len(buf))
    if status == 206: hdrs["Content-Range"] = f"bytes {a}-{b}/{size}"
    return Response(content=buf, status_code=status, headers=hdrs,
                                  media_type="audio/mpeg")


@podcasts_router.post("/episodes/{ep_id}/action-cards")
async def post_action_card(ep_id: str, request: Request,
                                                  user: dict = Depends(current_user),
                                                  body: dict = Body(...)):
    db = request.app.state.db
    await svc.require_approved_creator(db, user)
    from services import podcast_action_cards as ac
    try:
        return await ac.create_card(db, episode_id=ep_id,
                                                              owner_user_id=user["user_id"],
                                                              body=body)
    except (ValueError, LookupError) as e:
        raise HTTPException(400, str(e))


@podcasts_router.get("/episodes/{ep_id}/action-cards")
async def get_action_cards(ep_id: str, request: Request,
                                                      current_seconds: Optional[float] = None):
    db = request.app.state.db
    from services import podcast_action_cards as ac
    if current_seconds is not None:
        return {"cards": await ac.list_active_cards_at_time(
            db, episode_id=ep_id, current_seconds=float(current_seconds))}
    return {"cards": await ac.list_cards_for_creator(db, episode_id=ep_id)}


@podcasts_router.patch("/episodes/{ep_id}/action-cards/{card_id}")
async def patch_action_card(ep_id: str, card_id: str, request: Request,
                                                          user: dict = Depends(current_user),
                                                          body: dict = Body(...)):
    db = request.app.state.db
    await svc.require_approved_creator(db, user)
    from services import podcast_action_cards as ac
    try:
        return await ac.patch_card(db, card_id=card_id, episode_id=ep_id,
                                                          owner_user_id=user["user_id"], body=body)
    except LookupError as e: raise HTTPException(404, str(e))
    except PermissionError as e: raise HTTPException(403, str(e))
    except ValueError as e: raise HTTPException(400, str(e))


@podcasts_router.post("/action-cards/{card_id}/save-offer")
async def post_action_card_save_offer(card_id: str, request: Request,
                                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    from services import podcast_action_cards as ac
    try:
        return await ac.save_offer_via_card(
            db, card_id=card_id, user_id=user["user_id"])
    except LookupError as e: raise HTTPException(404, str(e))


@podcasts_router.patch("/channels/{ch_id}/value-config")
async def patch_channel_value_config(ch_id: str, request: Request,
                                                                              user: dict = Depends(current_user),
                                                                              body: dict = Body(...)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, ch_id)
    from datetime import datetime, timezone
    # Phase P2 hygiene — `podcast_lightning_splits` is the canonical SoT for
    # splits. When the client patches `splits`/`default_splits` inline on the
    # channel value-config, route it through the write-through helper so the
    # SoT and the channel.value_config.splits read-cache stay coherent.
    raw_splits = body.get("splits") or body.get("default_splits")
    if raw_splits is not None:
        await _pl.write_channel_splits(
            db, channel_id=ch_id, recipients=raw_splits)
    vc_set = {"enabled":   bool(body.get("enabled", True)),
                      "method":     body.get("method", "keysend"),
                      "suggested": body.get("suggested")}
    # Only overwrite splits inline if the helper above didn't (preserve
    # mirror written by write_channel_splits).
    update: dict = {"value_config_updated_at": datetime.now(timezone.utc)}
    for k, v in vc_set.items():
        update[f"value_config.{k}"] = v
    await db.podcast_channels.update_one({"id": ch_id}, {"$set": update})
    return await db.podcast_channels.find_one(
        {"id": ch_id}, {"_id": 0, "value_config": 1, "id": 1})


@podcasts_router.patch("/episodes/{ep_id}/value-config")
async def patch_episode_value_config(ep_id: str, request: Request,
                                                                              user: dict = Depends(current_user),
                                                                              body: dict = Body(...)):
    db = request.app.state.db
    await _own_episode_or_403(db, user, ep_id)
    vc = {"enabled":   bool(body.get("enabled", True)),
              "method":     body.get("method", "keysend"),
              "suggested": body.get("suggested"),
              "splits":     body.get("splits") or []}
    await db.podcast_episodes.update_one(
        {"id": ep_id}, {"$set": {"value_config": vc}})
    return await db.podcast_episodes.find_one(
        {"id": ep_id}, {"_id": 0, "value_config": 1, "id": 1})


# ─── Phase 36d Turn 3 — Lightning splits (placeholder schema) ────
# Stores per-channel & per-episode <podcast:value> recipient configs.
# NO real Lightning payment processing — RSS emission only.
from services import podcast_lightning as _pl  # noqa: E402

# ─── Phase 36e Turn 1 — Subscription paywall gate on episode read ──
from services import subscriptions as _subs  # noqa: E402
from auth import current_user_optional as _current_user_optional  # noqa: E402


@podcasts_router.get("/episodes/{eid}/access-check")
async def check_episode_access(eid: str, request: Request,
                                                            user: Optional[dict] = Depends(_current_user_optional)):
    """Returns 200 with `{accessible: true}` if reachable; otherwise 402
    with `{paywall: {...}}`. Frontend hits this BEFORE attempting to
    play. The actual audio endpoint also enforces this gate."""
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one(
        {"id": eid}, {"_id": 0})
    if not ep: raise HTTPException(404, "episode_not_found")
    ok = await _subs.is_episode_accessible(db, episode=ep, user=user)
    if ok: return {"accessible": True, "episode_id": eid}
    plan = await _subs.get_active_plan(db, channel_id=ep["channel_id"])
    payload = _subs.paywall_payload(channel_id=ep["channel_id"], plan=plan)
    payload["accessible"] = False
    raise HTTPException(status_code=402, detail=payload)


@podcasts_router.get("/channels/{channel_id}/lightning-splits")
async def get_channel_lightning_splits(channel_id: str, request: Request,
                                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    doc = await _pl.get_channel_default(db, channel_id)
    return doc or {"channel_id": channel_id, "episode_id": None,
                                "recipients": []}


@podcasts_router.put("/channels/{channel_id}/lightning-splits")
async def put_channel_lightning_splits(channel_id: str, request: Request,
                                                                                    body: dict = Body(...),
                                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_channel_or_403(db, user, channel_id)
    # Phase P2 — write-through SoT helper. Persists to
    # `podcast_lightning_splits` AND mirrors into `channel.value_config.splits`.
    return await _pl.write_channel_splits(
        db, channel_id=channel_id,
        recipients=body.get("recipients") or [])


@podcasts_router.get("/episodes/{episode_id}/lightning-splits")
async def get_episode_lightning_splits(episode_id: str, request: Request):
    """Public — readable by RSS aggregators / podcast clients."""
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one(
        {"id": episode_id}, {"channel_id": 1, "_id": 0})
    if not ep: raise HTTPException(404, "episode_not_found")
    resolved = await _pl.get_episode_resolved(
        db, channel_id=ep["channel_id"], episode_id=episode_id)
    return resolved or {"channel_id": ep["channel_id"],
                                          "episode_id": episode_id,
                                          "recipients": [],
                                          "inherited_from_channel": False}


@podcasts_router.put("/episodes/{episode_id}/lightning-splits")
async def put_episode_lightning_splits(episode_id: str, request: Request,
                                                                                    body: dict = Body(...),
                                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one(
        {"id": episode_id}, {"channel_id": 1, "_id": 0})
    if not ep: raise HTTPException(404, "episode_not_found")
    await _own_channel_or_403(db, user, ep["channel_id"])
    return await _pl.upsert_episode_override(
        db, channel_id=ep["channel_id"], episode_id=episode_id,
        recipients=body.get("recipients") or [])


@podcasts_router.delete("/episodes/{episode_id}/lightning-splits")
async def delete_episode_lightning_splits(episode_id: str, request: Request,
                                                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one(
        {"id": episode_id}, {"channel_id": 1, "_id": 0})
    if not ep: raise HTTPException(404, "episode_not_found")
    await _own_channel_or_403(db, user, ep["channel_id"])
    deleted = await _pl.delete_episode_override(db, episode_id=episode_id)
    return {"deleted": deleted}


# ─── Phase P2 — Admin reconcile endpoint ───────────────────────────
# One-shot backfill, exposed for ops. Idempotent: a second call with no
# inflight changes returns reconciled=0.
@admin_podcasts_router.post("/lightning-splits/reconcile")
async def admin_reconcile_lightning_splits(request: Request,
                                                                                      _: dict = Depends(require_admin)):
    return await _pl.reconcile_all_channel_splits(request.app.state.db)


@podcasts_router.post(
    "/recording-sessions/{sid}/participants/{pid}/connection-quality")
async def post_connection_quality(sid: str, pid: str, request: Request,
                                                                  payload: dict = Body(...)):
    """Append a single connection-quality sample to the participant's log.
    Auth: open with ws_token OR signed-in creator. Capped at 200 entries
    per participant (FIFO drop) to keep doc sizes sane."""
    db = request.app.state.db
    ws_token = payload.get("ws_token") or request.headers.get("x-ws-token")
    p = await db.podcast_recording_participants.find_one(
        {"id": pid, "session_id": sid}, {"id": 1, "ws_token": 1, "_id": 0})
    if not p: raise HTTPException(404, "participant_not_found")
    if p.get("ws_token") and ws_token and p["ws_token"] != ws_token:
        raise HTTPException(401, "invalid_ws_token")
    entry = {
        "ts":                                __import__("datetime").datetime.now(
                                                  __import__("datetime").timezone.utc).isoformat(),
        "score":                          float(max(0.0, min(1.0,
                                                  payload.get("score") or 0))),
        "rtt_ms":                       int(payload.get("rtt_ms") or 0),
        "jitter_ms":                  int(payload.get("jitter_ms") or 0),
        "packet_loss_pct":     float(payload.get("packet_loss_pct") or 0),
    }
    # $push with $slice to cap at 200 (keep the most recent).
    await db.podcast_recording_participants.update_one(
        {"id": pid, "session_id": sid},
        {"$push": {"connection_quality_log":
                          {"$each": [entry], "$slice": -200}},
          "$set": {"last_connection_quality": entry}})
    return {"ok": True, "entry": entry}


@podcasts_router.get(
    "/recording-sessions/{sid}/connection-quality")
async def get_connection_quality(sid: str, request: Request,
                                                              user: dict = Depends(current_user)):
    """Aggregated quality view per participant (admin/creator only)."""
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    rows = await db.podcast_recording_participants.find(
        {"session_id": sid},
        {"id": 1, "role": 1, "display_name": 1,
          "last_connection_quality": 1,
          "connection_quality_log": 1, "_id": 0}).to_list(20)
    out = []
    for r in rows:
        log = r.get("connection_quality_log") or []
        avg = (sum(e.get("score") or 0 for e in log) / len(log)) if log else None
        out.append({
            "participant_id":    r["id"],
            "role":                          r.get("role"),
            "display_name":     r.get("display_name"),
            "samples":                  len(log),
            "avg_score":                 round(avg, 3) if avg is not None else None,
            "last":                          r.get("last_connection_quality")})
    return {"session_id": sid, "participants": out}


@podcasts_router.post("/recording-sessions/{sid}/finalize")
async def post_finalize_recording_session(sid: str, request: Request,
                                                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_recording as rec
    return await rec.finalize_session(db, session_id=sid)


@podcasts_router.get("/recording-sessions/{sid}")
async def get_recording_session(sid: str, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_recording as rec
    r = await rec.get_session(db, session_id=sid)
    if not r: raise HTTPException(404, "session_not_found")
    return r


@podcasts_router.delete("/recording-sessions/{sid}")
async def delete_recording_session(sid: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_recording as rec
    return await rec.cancel_session(db, session_id=sid)


@podcasts_router.get("/recording-sessions/{sid}/audio/{name}")
async def get_recording_audio(sid: str, name: str, request: Request):
    """Public-read access to the recording's host.mp3 or mixed.mp3 file."""
    from pathlib import Path as _P
    if name not in ("host.mp3", "mixed.mp3", "guest.mp3"):
        raise HTTPException(404, "not_found")
    p = _P("/app/backend/storage/podcasts/recordings") / sid / name
    if not p.exists(): raise HTTPException(404, "audio_not_found")
    return FileResponse(str(p), media_type="audio/mpeg",
                                          headers={"Accept-Ranges": "bytes",
                                                          "Cache-Control": "private, max-age=60"})


# ─── Admin: LiveKit integration status + disk-events audit ────────
@admin_podcasts_router.get("/integrations/livekit/status")
async def admin_livekit_status(request: Request,
                                                        _: dict = Depends(require_admin)):
    from services import livekit_client as lk
    return lk.status()


@admin_podcasts_router.get("/recording-disk-events")
async def admin_disk_events(request: Request,
                                                  _: dict = Depends(require_admin),
                                                  limit: int = Query(50, ge=1, le=200)):
    db = request.app.state.db
    from services import podcast_recording as rec
    return {"events": await rec.list_disk_events(db, limit=limit)}


# Phase 36c Stage 1 path parity — old `/api/podcasts/admin/recording-disk-events`
# is preserved as a permanent 308 redirect to the canonical admin path. 308
# preserves method + body, so curl/HTTP clients keep working. No auth here —
# the redirect target enforces require_admin.
@podcasts_router.get("/admin/recording-disk-events")
async def admin_disk_events_legacy_redirect(request: Request):
    from fastapi.responses import RedirectResponse
    new_path = "/api/admin/podcasts/recording-disk-events"
    qs = request.url.query
    if qs: new_path = f"{new_path}?{qs}"
    return RedirectResponse(new_path, status_code=308)



# Phase 36c.5 — Tigris object-storage status pill (mirrors LiveKit/AAI/GAM).
@admin_podcasts_router.get("/integrations/tigris/status")
async def admin_tigris_status(_: dict = Depends(require_admin)):
    from services import object_storage as obs
    st = obs.get_storage()
    out = {"backend":  st.backend_name,
              "is_live": st.backend_name == "tigris",
              "endpoint": getattr(st, "endpoint", None),
              "bucket":     getattr(st, "bucket", None),
              "total_objects": 0,
              "total_size_bytes": 0,
              "last_check_at": datetime.now(timezone.utc).isoformat()}
    try:
        cnt = sz = 0
        for it in st.list_keys(prefix=""):
            cnt += 1; sz += int(it.get("size") or 0)
            if cnt > 5000: break    # safety guard
        out["total_objects"] = cnt
        out["total_size_bytes"] = sz
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


# ═══════════════════════════════════════════════════════════════════
# Phase 36c Stage 2 — Guest invites, lobby, WS, funnel analytics
# ═══════════════════════════════════════════════════════════════════
from fastapi import WebSocket, WebSocketDisconnect


class InviteBody(BaseModel):
    guest_name:                str
    guest_email:              str
    guest_phone:              Optional[str] = None
    consent_required:    bool = True


@podcasts_router.post("/recording-sessions/{sid}/invite-guest")
async def post_invite_guest(sid: str, body: InviteBody, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_guests as pg
    inv = await pg.create_invite(db, session_id=sid,
        guest_name=body.guest_name, guest_email=body.guest_email,
        guest_phone=body.guest_phone, consent_required=body.consent_required,
        invited_by_user_id=user["user_id"])
    # Build full join URL for the "Copy link" UI.
    public_origin = (request.headers.get("origin")
                                    or os.environ.get("PUBLIC_FRONTEND_ORIGIN")
                                    or "")
    invite_url = f"{public_origin}/studio/join/{inv['invite_token']}"
    return {"invite_id":          inv["id"],
              "invite_token":     inv["invite_token"],
              "invite_url":         invite_url,
              "expires_at":        inv["expires_at"],
              "mocked_email_sent": True}


@podcasts_router.get("/recording-sessions/{sid}/invites")
async def get_session_invites(sid: str, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_guests as pg
    return {"invites": await pg.list_invites(db, session_id=sid)}


@podcasts_router.post("/recording-sessions/{sid}/invites/{invite_id}/cancel")
async def post_cancel_invite(sid: str, invite_id: str, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_guests as pg
    return await pg.cancel_invite(db, session_id=sid, invite_id=invite_id,
                                                              revoked_by_user_id=user["user_id"])


@podcasts_router.post("/recording-sessions/{sid}/lobby/admit/{participant_id}")
async def post_admit_participant(sid: str, participant_id: str,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_guests as pg
    return await pg.admit_participant(db, session_id=sid,
                                                                participant_id=participant_id,
                                                                admitted_by_user_id=user["user_id"])


@podcasts_router.post("/recording-sessions/{sid}/lobby/kick/{participant_id}")
async def post_kick_participant(sid: str, participant_id: str,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_session_or_403(db, user, sid)
    from services import podcast_guests as pg
    return await pg.kick_participant(db, session_id=sid,
                                                                participant_id=participant_id,
                                                                kicked_by_user_id=user["user_id"])


# ─── Public guest landing endpoints (no auth) ────────────────────
@podcasts_router.get("/studio/invites/{invite_token}")
async def get_public_invite_route(invite_token: str, request: Request):
    db = request.app.state.db
    from services import podcast_guests as pg
    return await pg.get_public_invite(db, invite_token=invite_token)


class AcceptInviteBody(BaseModel):
    display_name:           str
    email:                          Optional[str] = None
    consent_accepted: bool = False
    device_info:              Optional[dict] = None


@podcasts_router.post("/studio/invites/{invite_token}/accept")
async def post_accept_invite(invite_token: str, body: AcceptInviteBody,
                                                        request: Request):
    db = request.app.state.db
    ip = (request.headers.get("x-forwarded-for")
              or (request.client.host if request.client else ""))
    from services import podcast_guests as pg
    return await pg.accept_invite(db, invite_token=invite_token,
                                                              display_name=body.display_name,
                                                              email=body.email or "",
                                                              consent_accepted=body.consent_accepted,
                                                              device_info=body.device_info or {},
                                                              ip_address=ip)


@podcasts_router.get("/studio/invites/{invite_token}/state")
async def get_invite_state_route(invite_token: str, request: Request):
    db = request.app.state.db
    from services import podcast_guests as pg
    return await pg.get_invite_state(db, invite_token=invite_token)


# ─── WebSocket: studio lobby presence ───────────────────────────
@podcasts_router.websocket("/studio/{sid}/ws")
async def studio_lobby_ws(websocket: WebSocket, sid: str):
    """Host and guest WS endpoint. Auth via `?token=<X>`:
      - host: session cookie value (auth.SESSION_COOKIE)
      - guest: participant.ws_token (UUID4 issued at accept time)"""
    await websocket.accept()
    db    = websocket.app.state.db
    from services import podcast_guests as pg
    qp = websocket.query_params
    token = qp.get("token") or qp.get("session") or ""
    sess = await db.podcast_recording_sessions.find_one({"id": sid})
    if not sess:
        await websocket.send_text(__import__("json").dumps(
            {"type": "error", "code": "session_not_found"}))
        await websocket.close(code=4404); return
    key:    Optional[str] = None
    role: str = "guest"
    you: dict = {}
    # Try host (session token) first.
    if token:
        s = await db.sessions.find_one({"token": token})
        if s:
            creator = await db.podcast_creators.find_one(
                {"user_id": s["user_id"]})
            if creator and creator["id"] == sess.get("creator_id"):
                key  = f"host:{s['user_id']}"
                role = "host"
                you  = {"role": "host", "user_id": s["user_id"]}
    # Fall back: guest with ws_token.
    if key is None and token:
        p = await db.podcast_recording_participants.find_one(
            {"session_id": sid, "ws_token": token})
        if p:
            key  = p["id"]
            role = "guest"
            you  = {"role": "guest", "participant_id": p["id"],
                       "lobby_status": p.get("lobby_status"),
                       "display_name": p.get("display_name")}
    if key is None:
        await websocket.send_text(__import__("json").dumps(
            {"type": "error", "code": "unauthorized"}))
        await websocket.close(code=4401); return
    pg.lobby_hub.attach(sid, key, websocket)
    await websocket.send_text(__import__("json").dumps(
        {"type": "hello", "role": role, "you": you,
          "session_status": sess.get("status")}, default=str))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = __import__("json").loads(raw)
            except Exception:
                continue
            if msg.get("type") == "ping":
                await websocket.send_text(__import__("json").dumps(
                    {"type": "pong"}))
            if msg.get("type") == "leave":
                break
    except WebSocketDisconnect:
        pass
    finally:
        pg.lobby_hub.detach(sid, key)


# ─── Admin: creator-studio funnel ────────────────────────────────
@admin_podcasts_router.get("/creator-studio-funnel")
async def admin_creator_studio_funnel(request: Request,
                                                                      _: dict = Depends(require_admin),
                                                                      from_iso: Optional[str] = Query(None, alias="from"),
                                                                      to_iso:    Optional[str] = Query(None, alias="to"),
                                                                      session_id: Optional[str] = None):
    db = request.app.state.db
    q: dict = {}
    if session_id: q["session_id"] = session_id
    if from_iso or to_iso:
        rng: dict = {}
        if from_iso: rng["$gte"] = datetime.fromisoformat(from_iso.replace("Z","+00:00"))
        if to_iso:    rng["$lte"] = datetime.fromisoformat(to_iso.replace("Z","+00:00"))
        q["timestamp"] = rng
    pipeline = [{"$match": q},
                          {"$group": {"_id": "$event", "count": {"$sum": 1}}},
                          {"$sort":   {"_id": 1}}]
    counts = await db.creator_studio_funnel.aggregate(pipeline).to_list(50)
    rows = await db.creator_studio_funnel.find(q, {"_id": 0}) \
        .sort("timestamp", -1).limit(200).to_list(200)
    return {"counts": {c["_id"]: c["count"] for c in counts}, "events": rows}


# ─── Admin: release-forms introspection (Stage 2 audit closeout) ─
# Read-only surface for the consent audit trail. The persisted snapshot
# (full text + version-at-signing) is what these endpoints expose; they
# do NOT touch the way release_forms are written (that contract is held
# by services/podcast_guests.py::accept_invite).
@admin_podcasts_router.get("/sessions/{sid}/release-forms")
async def admin_session_release_forms(sid: str, request: Request,
                                                                            _: dict = Depends(require_admin)):
    db = request.app.state.db
    rows = await db.podcast_release_forms.find(
        {"session_id": sid}, {"_id": 0}).sort("signed_at", 1).to_list(50)
    return {"session_id": sid, "release_forms": rows,
              "count": len(rows)}


@admin_podcasts_router.get("/release-forms/{form_id}")
async def admin_release_form_detail(form_id: str, request: Request,
                                                                          _: dict = Depends(require_admin)):
    db = request.app.state.db
    row = await db.podcast_release_forms.find_one({"id": form_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, {"code": "release_form_not_found"})
    return row


# Public funnel event drop (no auth — fire-and-forget from FE).
class FunnelPing(BaseModel):
    event:           str
    session_id: Optional[str] = None
    channel_id: Optional[str] = None
    meta:             Optional[dict] = None


@podcasts_router.post("/studio/funnel-event")
async def post_funnel_event(body: FunnelPing, request: Request,
                                                  user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    from services import podcast_guests as pg
    await pg.log_funnel(db, event=body.event,
                                          user_id=user["user_id"] if user else None,
                                          session_id=body.session_id,
                                          channel_id=body.channel_id,
                                          meta=body.meta or {})
    return {"ok": True}



# ──────────────────────────────────────────────────────────
# Phase 36e Turn 2 — Conversion funnel dashboard endpoints.
# ──────────────────────────────────────────────────────────

@podcasts_router.post("/channels/{channel_id}/funnel/cta-clicked")
async def funnel_cta_clicked(channel_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    """Logged-in listener clicked a Subscribe / Start-trial CTA. Fired
    BEFORE the actual subscribe call. Dedupe per (listener, channel, day)."""
    db = request.app.state.db
    ch = await db.podcast_channels.find_one({"id": channel_id})
    if not ch: raise HTTPException(404, "channel_not_found")
    from services import funnel as _fn
    res = await _fn.record_event(db, event_type="subscribe_cta_click",
        listener_user_id=user["user_id"], channel_id=channel_id)
    return res


@podcasts_router.post("/episodes/{ep_id}/play-start")
async def funnel_episode_play_start(ep_id: str, request: Request,
                                                                              user: dict = Depends(current_user)):
    """Fired when audio playback actually begins (not page load). Dedupe per
    (listener, channel, day) — counts unique daily play sessions."""
    db = request.app.state.db
    ep = await db.podcast_episodes.find_one({"id": ep_id},
                                                                                  {"_id": 0, "id": 1, "channel_id": 1})
    if not ep: raise HTTPException(404, "episode_not_found")
    from services import funnel as _fn
    res = await _fn.record_event(db, event_type="episode_play",
        listener_user_id=user["user_id"], channel_id=ep["channel_id"],
        episode_id=ep_id)
    return res


async def _creator_or_admin(db, user, creator_id: str) -> dict:
    """Gate helper for creator-owned dashboards. Admin sees any creator; a
    creator only sees their own. Mirrors the Turn 1 ordering fix."""
    crt = await db.podcast_creators.find_one({"id": creator_id})
    if not crt: raise HTTPException(404, "creator_not_found")
    if user.get("role") == "admin": return crt
    if crt.get("user_id") != user.get("user_id"):
        raise HTTPException(403, "not_your_creator_profile")
    return crt


@podcasts_router.get("/creators/{creator_id}/funnel/summary")
async def funnel_summary(creator_id: str, request: Request,
                                                  window_days: int = 7,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _creator_or_admin(db, user, creator_id)
    window_days = max(1, min(int(window_days or 7), 30))
    from services import funnel as _fn
    return await _fn.summary(db, creator_id=creator_id,
                                                      window_days=window_days)


@podcasts_router.get("/creators/{creator_id}/funnel/daily")
async def funnel_daily(creator_id: str, request: Request, days: int = 7,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _creator_or_admin(db, user, creator_id)
    from services import funnel as _fn
    return await _fn.daily(db, creator_id=creator_id, days=days)



# ──────────────────────────────────────────────────────────
# Phase 36e Turn 3 — First-episode publish nudge endpoints.
# ──────────────────────────────────────────────────────────

@podcasts_router.get("/creators/{creator_id}/nudge-status")
async def nudge_status(creator_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    crt = await _creator_or_admin(db, user, creator_id)
    from services import nudges as _nudges
    return await _nudges.get_status_payload(db, creator=crt)


@podcasts_router.post("/creators/{creator_id}/nudge-status/pause")
async def nudge_pause(creator_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    crt = await db.podcast_creators.find_one({"id": creator_id})
    if not crt: raise HTTPException(404, "creator_not_found")
    if crt.get("user_id") != user.get("user_id"):
        raise HTTPException(403, "not_your_creator_profile")
    from services import nudges as _nudges
    return await _nudges.set_paused(db, creator_id=creator_id, paused=True)


@podcasts_router.post("/creators/{creator_id}/nudge-status/resume")
async def nudge_resume(creator_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    crt = await db.podcast_creators.find_one({"id": creator_id})
    if not crt: raise HTTPException(404, "creator_not_found")
    if crt.get("user_id") != user.get("user_id"):
        raise HTTPException(403, "not_your_creator_profile")
    from services import nudges as _nudges
    return await _nudges.set_paused(db, creator_id=creator_id, paused=False)


@podcasts_router.post("/admin/nudges/dispatch")
async def admin_nudges_dispatch(request: Request, dry_run: bool = True,
                                                                  user: dict = Depends(require_admin)):
    db = request.app.state.db
    from services import nudges as _nudges
    from services import mailgun_client as _mg
    res = await _nudges.tick_first_episode_nudges(db, dry_run=dry_run)
    res["provider"] = "mailgun" if _mg.is_live() else "mock"
    return res


@podcasts_router.get("/admin/integrations/mailgun/status")
async def admin_mailgun_status(request: Request,
                                                              user: dict = Depends(require_admin)):
    from services import mailgun_client as _mg
    import os
    return {"configured": bool(os.environ.get("MAILGUN_API_KEY")),
                  "domain":     os.environ.get("MAILGUN_DOMAIN"),
                  "from":         os.environ.get("MAILGUN_FROM"),
                  "live":         _mg.is_live(),
                  "provider": os.environ.get("EMAIL_PROVIDER")}

