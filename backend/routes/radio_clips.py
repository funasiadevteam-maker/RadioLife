"""FUUSIC — Radio clips: station daily show HIGHLIGHTS + listener 30s CLIP & SHARE.

RIGHTS: FUUSIC never records or redistributes third-party broadcasts. Station
highlights are station-provided / official audio. Listener clips are only
allowed for stations that have opted into authorized clipping
(`station_clip_policies`); community stations opt in by default. For stations
without permission we offer "Share Station" instead — no audio is fabricated.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user

router = APIRouter(prefix="/api", tags=["radio-clips"])

MAX_CLIP_SEC = 30
BUFFER_SEC = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return v


async def _station_meta(db, station_id: str):
    s = await db.community_radio_stations.find_one({"station_id": station_id})
    if s:
        return {"id": station_id, "slug": s.get("slug"),
                "name": s.get("name") or s.get("slug"),
                "logo": s.get("cover_image_url"), "owner": s.get("owner_user_id"),
                "kind": "community"}
    im = await db.imported_radio_stations.find_one({"id": station_id})
    if im:
        return {"id": station_id, "slug": im.get("flagship_slug"),
                "name": im.get("name"), "logo": im.get("favicon"),
                "owner": None, "kind": "imported"}
    return None


async def _clip_allowed(db, station_id: str, meta: dict):
    """Community stations allow clipping by default; imported/third-party only
    when the broadcaster has opted into an authorized clipping arrangement."""
    if meta["kind"] == "community":
        return True, None
    pol = await db.station_clip_policies.find_one({"station_id": station_id})
    if pol and pol.get("clip_enabled"):
        return True, None
    return (False,
            "This station hasn't enabled clip sharing. You can still share the station.")


async def _buffer_url(db, station_id: str) -> str | None:
    pol = await db.station_clip_policies.find_one({"station_id": station_id})
    if pol and pol.get("buffer_audio_url"):
        return pol["buffer_audio_url"]
    return None


def _clip_public(c: dict) -> dict:
    return {
        "clip_id": c["_id"], "kind": c.get("kind"),
        "station_id": c.get("station_id"), "station_slug": c.get("station_slug"),
        "station_name": c.get("station_name"), "station_logo": c.get("station_logo"),
        "show_name": c.get("show_name"), "host_name": c.get("host_name"),
        "title": c.get("title"), "caption": c.get("caption"),
        "audio_url": c.get("audio_url"), "duration_sec": c.get("duration_sec"),
        "slot": c.get("slot"), "broadcast_at": _iso(c.get("broadcast_at")),
        "created_at": _iso(c.get("created_at")),
        "like_count": int(c.get("like_count") or 0),
        "comment_count": int(c.get("comment_count") or 0),
        "share_count": int(c.get("share_count") or 0),
        "status": c.get("status"), "processing_status": c.get("processing_status", "ready"),
    }


# ──────────────────────── Station daily highlights ────────────────────────
class HighlightBody(BaseModel):
    show_name: str = Field(..., max_length=120)
    host_name: str | None = Field(None, max_length=120)
    title: str = Field(..., max_length=160)
    caption: str | None = Field(None, max_length=600)
    audio_url: str = Field(..., max_length=600)
    duration_sec: int = Field(45, ge=5, le=180)
    slot: str = Field("special", max_length=20)   # morning|afternoon|evening|special
    broadcast_date: str | None = None             # YYYY-MM-DD


@router.post("/stations/{station_id}/highlights")
async def publish_highlight(station_id: str, body: HighlightBody, request: Request,
                            user: dict = Depends(current_user)):
    """Station owner (or admin) publishes a daily show-highlight clip.
    Idempotent per (station, slot, broadcast_date) so scheduled jobs never dup."""
    db = request.app.state.db
    meta = await _station_meta(db, station_id)
    if not meta:
        raise HTTPException(404, {"code": "station_not_found"})
    is_admin = user.get("role") == "admin"
    if not is_admin and meta.get("owner") != user["user_id"]:
        raise HTTPException(403, {"code": "not_station_owner"})
    bdate = body.broadcast_date or _now().date().isoformat()
    _id = f"rc_{station_id}_{body.slot}_{bdate}".replace(":", "_")[:120]
    doc = {
        "_id": _id, "kind": "station_highlight", "station_id": station_id,
        "station_slug": meta["slug"], "station_name": meta["name"],
        "station_logo": meta["logo"], "show_name": body.show_name,
        "host_name": body.host_name, "title": body.title, "caption": body.caption,
        "audio_url": body.audio_url, "duration_sec": body.duration_sec,
        "slot": body.slot, "broadcast_date": bdate, "broadcast_at": _now(),
        "rights": "station_provided", "status": "published",
        "moderation_status": "approved", "created_by": user["user_id"],
        "created_at": _now(),
    }
    await db.radio_clips.update_one(
        {"_id": _id},
        {"$set": doc, "$setOnInsert": {"like_count": 0, "comment_count": 0,
                                       "share_count": 0, "play_count": 0}},
        upsert=True)
    return {"ok": True, "clip_id": _id, "status": "published"}


@router.get("/stations/{station_id}/highlights")
async def list_highlights(station_id: str, request: Request, limit: int = 20):
    db = request.app.state.db
    out = []
    async for c in db.radio_clips.find(
            {"station_id": station_id, "kind": "station_highlight",
             "status": "published"}).sort("broadcast_at", -1).limit(min(limit, 50)):
        out.append(_clip_public(c))
    return {"count": len(out), "clips": out}


# ──────────────────────── Listener 30s Clip & Share ───────────────────────
@router.get("/stations/{station_id}/clip-eligibility")
async def clip_eligibility(station_id: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    meta = await _station_meta(db, station_id)
    if not meta:
        raise HTTPException(404, {"code": "station_not_found"})
    allowed, reason = await _clip_allowed(db, station_id, meta)
    return {
        "allowed": allowed, "reason": reason, "max_seconds": MAX_CLIP_SEC,
        "buffer_seconds": BUFFER_SEC,
        "buffer_audio_url": await _buffer_url(db, station_id) if allowed else None,
        "station": {"id": station_id, "name": meta["name"], "logo": meta["logo"],
                    "slug": meta["slug"]},
    }


class ClipShareBody(BaseModel):
    station_id: str = Field(..., max_length=120)
    start_offset: float = Field(0, ge=0, le=BUFFER_SEC)
    duration_seconds: float = Field(30, ge=5, le=MAX_CLIP_SEC)
    comment: str | None = Field(None, max_length=600)
    visibility: str = Field("public", max_length=12)
    tags: list[str] = []
    show_name: str | None = Field(None, max_length=120)
    idempotency_key: str | None = Field(None, max_length=80)


@router.post("/radio/clips/share")
async def share_clip(body: ClipShareBody, request: Request,
                     user: dict = Depends(current_user)):
    """Create a listener's 30s clip (authorized stations only) + share it to
    their wall. Idempotency key guards against duplicate posts on retry."""
    db = request.app.state.db
    uid = user["user_id"]
    meta = await _station_meta(db, body.station_id)
    if not meta:
        raise HTTPException(404, {"code": "station_not_found"})
    allowed, reason = await _clip_allowed(db, body.station_id, meta)
    if not allowed:
        raise HTTPException(403, {"code": "clipping_not_allowed", "message": reason})
    if body.idempotency_key:
        ex = await db.radio_clips.find_one(
            {"idempotency_key": body.idempotency_key, "created_by": uid})
        if ex:
            return {"ok": True, "clip_id": ex["_id"], "duplicate": True,
                    "status": ex.get("status")}
    buf = await _buffer_url(db, body.station_id)
    if not buf:
        raise HTTPException(409, {"code": "no_buffer",
                                  "message": "No authorized audio to clip right now."})
    dur = max(5, min(float(body.duration_seconds or 30), MAX_CLIP_SEC))
    vis = body.visibility if body.visibility in ("public", "friends") else "public"
    _id = f"uc_{uuid.uuid4().hex[:16]}"
    doc = {
        "_id": _id, "kind": "user_clip", "station_id": body.station_id,
        "station_slug": meta["slug"], "station_name": meta["name"],
        "station_logo": meta["logo"], "show_name": body.show_name,
        "title": f"Clip from {meta['name']}", "caption": body.comment,
        "commentary": body.comment, "audio_url": buf,
        "start_offset": float(body.start_offset or 0), "duration_sec": int(dur),
        "tags": (body.tags or [])[:5], "visibility": vis,
        "rights": "authorized_clip", "status": "published",
        "moderation_status": "approved", "processing_status": "ready",
        "created_by": uid, "created_at": _now(), "broadcast_at": _now(),
        "idempotency_key": body.idempotency_key,
        "like_count": 0, "comment_count": 0, "share_count": 0, "play_count": 0,
    }
    await db.radio_clips.insert_one(doc)
    return {"ok": True, "clip_id": _id, "status": "published"}


@router.get("/radio/clips/{clip_id}/status")
async def clip_status(clip_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.radio_clips.find_one({"_id": clip_id})
    if not c:
        raise HTTPException(404, {"code": "not_found"})
    return {"clip_id": clip_id, "status": c.get("status"),
            "processing_status": c.get("processing_status", "ready"),
            "moderation_status": c.get("moderation_status", "approved")}


# ──────────── Followed-station daily highlights digest (grouped) ───────────
@router.get("/social/daily-highlights")
async def daily_highlights(request: Request, user: dict = Depends(current_user)):
    """Grouped station highlights from the stations the user follows — a compact
    digest rather than dozens of consecutive cards."""
    db = request.app.state.db
    uid = user["user_id"]
    st_ids = [s["station_id"] async for s in
              db.station_followers.find({"user_id": uid}, {"station_id": 1})
              if s.get("station_id")]
    groups: dict[str, dict] = {}
    if st_ids:
        async for c in db.radio_clips.find(
                {"station_id": {"$in": st_ids}, "kind": "station_highlight",
                 "status": "published"}).sort("broadcast_at", -1).limit(80):
            g = groups.setdefault(c["station_id"], {
                "station_id": c["station_id"], "station_name": c.get("station_name"),
                "station_logo": c.get("station_logo"), "count": 0, "clips": []})
            g["count"] += 1
            if len(g["clips"]) < 5:
                g["clips"].append(_clip_public(c))
    out = sorted(groups.values(), key=lambda g: g["count"], reverse=True)
    return {"station_count": len(out), "groups": out}


# ──────────── Follow a FUUSIC AI channel (a "show") + clip it ──────────────
# AI channels aren't in community_radio_stations/imported_radio_stations, so we
# track the follow with a display snapshot (surfaced in My Feed Preferences via
# feed_preferences_service.list_following_entities).
def _channel_station_id(slug: str) -> str:
    return f"ch_{slug}"


def _is_owned_audio(url: str, req_hosts: "set[str] | None" = None) -> bool:
    """Rights guard — only FUUSIC's own AI-radio segment audio is clippable.
    Relative /api/radio/... is always allowed; an absolute URL must point at
    our own backend host (blocks e.g. https://evil.com/api/radio/x.mp3)."""
    from urllib.parse import urlparse
    u = (url or "").split("?")[0].strip()
    p = urlparse(u)
    if not p.path.startswith("/api/radio/"):
        return False
    if p.netloc:
        return bool(req_hosts) and p.netloc in req_hosts
    return True


class ChannelFollowBody(BaseModel):
    channel_name: str | None = Field(None, max_length=160)
    channel_logo: str | None = Field(None, max_length=600)


@router.post("/radio/channels/{slug}/follow")
async def follow_channel(slug: str, body: ChannelFollowBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    sid = _channel_station_id(slug)
    snap = {"name": body.channel_name or slug, "logo": body.channel_logo,
            "slug": slug, "kind": "fuusic_channel", "category": "station"}
    await db.station_followers.update_one(
        {"user_id": user["user_id"], "station_id": sid},
        {"$setOnInsert": {"followed_at": _now().isoformat()},
         "$set": {"station_snapshot": snap, "station_kind": "fuusic_channel",
                  "channel_slug": slug}},
        upsert=True)
    return {"ok": True, "now_following": True}


@router.post("/radio/channels/{slug}/unfollow")
async def unfollow_channel(slug: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.station_followers.delete_one(
        {"user_id": user["user_id"], "station_id": _channel_station_id(slug)})
    return {"ok": True, "now_following": False}


@router.get("/radio/channels/{slug}/follow-status")
async def channel_follow_status(slug: str, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.station_followers.find_one(
        {"user_id": user["user_id"], "station_id": _channel_station_id(slug)})
    return {"following": bool(r)}


class SegmentClipBody(BaseModel):
    channel_slug: str = Field(..., max_length=120)
    channel_name: str | None = Field(None, max_length=160)
    channel_logo: str | None = Field(None, max_length=600)
    segment_audio_url: str = Field(..., max_length=600)
    comment: str | None = Field(None, max_length=600)
    visibility: str = Field("public", max_length=12)
    duration_seconds: float = Field(30, ge=5, le=MAX_CLIP_SEC)
    idempotency_key: str | None = Field(None, max_length=80)


@router.post("/radio/clips/share-segment")
async def share_segment_clip(body: SegmentClipBody, request: Request,
                             user: dict = Depends(current_user)):
    """Clip the last 30s of FUUSIC's own AI-radio audio the listener is hearing
    and share it to their wall. Rights-safe: only FUUSIC-owned segment audio."""
    db = request.app.state.db
    uid = user["user_id"]
    req_hosts = {h for h in (request.headers.get("host"),
                             request.headers.get("x-forwarded-host"),
                             request.url.netloc) if h}
    if not _is_owned_audio(body.segment_audio_url, req_hosts):
        raise HTTPException(403, {"code": "not_clippable",
                                  "message": "Only FUUSIC's own audio can be clipped."})
    if body.idempotency_key:
        ex = await db.radio_clips.find_one(
            {"idempotency_key": body.idempotency_key, "created_by": uid})
        if ex:
            return {"ok": True, "clip_id": ex["_id"], "duplicate": True,
                    "status": ex.get("status")}
    dur = max(5, min(float(body.duration_seconds or 30), MAX_CLIP_SEC))
    vis = body.visibility if body.visibility in ("public", "friends") else "public"
    _id = f"uc_{uuid.uuid4().hex[:16]}"
    doc = {
        "_id": _id, "kind": "user_clip",
        "station_id": _channel_station_id(body.channel_slug),
        "station_slug": body.channel_slug,
        "station_name": body.channel_name or body.channel_slug,
        "station_logo": body.channel_logo, "show_name": None,
        "title": f"Clip from {body.channel_name or 'FUUSIC Radio'}",
        "caption": body.comment, "commentary": body.comment,
        "audio_url": body.segment_audio_url, "start_offset": 0,
        "duration_sec": int(dur), "tags": [], "visibility": vis,
        "rights": "fuusic_owned", "status": "published",
        "moderation_status": "approved", "processing_status": "ready",
        "created_by": uid, "created_at": _now(), "broadcast_at": _now(),
        "idempotency_key": body.idempotency_key,
        "like_count": 0, "comment_count": 0, "share_count": 0, "play_count": 0,
    }
    await db.radio_clips.insert_one(doc)
    return {"ok": True, "clip_id": _id, "status": "published"}
