"""FUUSIC Social V2 — Phase 2: "Do things together".

Four surfaces on the shared /api/social contract:
  • Moments      — photo / video / voice posts with rich context (what you're
                   listening to / eating / playing / where), a friends+public
                   feed, likes and comments.
  • Go Together  — plan a real-world meetup (activity, place, time), invite
                   friends, and RSVP.
  • Play Together— spin up a shared game session and invite friends to join.
  • Local Pulse  — a city feed aggregating recent moments, upcoming plans,
                   live listening rooms and open play sessions near you.

Media is uploaded to the shared object storage and served back through a
range-capable proxy so both web and mobile use identical URLs.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                     Request, Response, UploadFile)
from pydantic import BaseModel, Field

from auth import current_user
from routes.social_v2 import _friend_ids, _user_public, _users_map
from services.object_storage import get_storage
from services.points_service import PointsService

router = APIRouter(prefix="/api/social", tags=["social_together"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB cap (photos + short clips/voice)
MOMENT_TTL_DAYS = 7                  # moments fade from the feed after a week
REFERRAL_POINTS = 500               # awarded to BOTH joiner + referrer

MIME_EXT = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "image/gif": "gif", "image/heic": "heic",
    "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
    "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/aac": "aac",
    "audio/wav": "wav", "audio/webm": "weba", "audio/ogg": "ogg",
}

GAMES = [
    {"key": "trivia", "label": "Trivia Live", "icon": "help-circle"},
    {"key": "predict", "label": "Predict & Win", "icon": "trending-up"},
    {"key": "beatguess", "label": "Guess the Beat", "icon": "musical-notes"},
    {"key": "quiz", "label": "Bollywood Quiz", "icon": "film"},
]
GAME_LABELS = {g["key"]: g["label"] for g in GAMES}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or request.url.netloc)
    return f"{proto}://{host}"


def _media_kind(content_type: str) -> Optional[str]:
    if content_type.startswith("image/"):
        return "photo"
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("audio/"):
        return "voice"
    return None


async def _user_city(db, uid: str) -> Optional[str]:
    u = await db.users.find_one({"user_id": uid}, {"city": 1, "market": 1, "_id": 0})
    return (u or {}).get("city") or (u or {}).get("market")


# ───────────────────────────── Bootstrap ───────────────────────────
async def ensure_social_together(db) -> None:
    await db.social_moments.create_index([("created_at", -1)], name="mom_time")
    await db.social_moments.create_index([("user_id", 1), ("created_at", -1)],
                                         name="mom_user_time")
    await db.social_moments.create_index([("city", 1), ("created_at", -1)],
                                         name="mom_city_time")
    await db.social_moment_likes.create_index(
        [("moment_id", 1), ("user_id", 1)], unique=True, name="ml_uniq")
    await db.social_moment_comments.create_index(
        [("moment_id", 1), ("created_at", 1)], name="mc_time")
    await db.social_outings.create_index([("created_at", -1)], name="out_time")
    await db.social_outings.create_index([("city", 1), ("when_at", 1)],
                                         name="out_city_when")
    await db.social_media_files.create_index("storage_key", name="smf_key")
    await db.play_sessions.create_index([("status", 1), ("created_at", -1)],
                                        name="ps_status_time")
    # One referral reward per (session, joiner) — prevents re-join farming.
    await db.play_referrals.create_index(
        [("session_id", 1), ("joiner_id", 1)], unique=True, name="pref_uniq")


# ═══════════════════════════ Media upload ══════════════════════════
@router.post("/media/upload")
async def media_upload(request: Request, file: UploadFile = File(...),
                       user: dict = Depends(current_user)):
    ct = (file.content_type or "").lower().split(";")[0].strip()
    kind = _media_kind(ct)
    if not kind:
        raise HTTPException(400, {"code": "unsupported_media", "content_type": ct})
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, {"code": "file_too_large", "max_mb": 25})
    if not data:
        raise HTTPException(400, {"code": "empty_file"})
    ext = MIME_EXT.get(ct, "bin")
    key = f"social/moments/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
    try:
        get_storage().upload_bytes(key=key, data=data, content_type=ct)
    except Exception:
        raise HTTPException(502, {"code": "storage_failed"})
    await db_files_insert(request.app.state.db, key, ct, len(data), user["user_id"])
    return {"key": key, "media_type": kind, "content_type": ct,
            "size": len(data),
            "url": f"{_base_url(request)}/api/social/media/file/{key}"}


async def db_files_insert(db, key, ct, size, uid) -> None:
    await db.social_media_files.update_one(
        {"storage_key": key},
        {"$set": {"storage_key": key, "content_type": ct, "size": size,
                  "user_id": uid, "created_at": _now()}}, upsert=True)


@router.get("/media/file/{key:path}")
async def media_file(key: str, request: Request):
    db = request.app.state.db
    rec = await db.social_media_files.find_one({"storage_key": key})
    if not rec:
        raise HTTPException(404, {"code": "media_not_found"})
    ct = rec.get("content_type") or "application/octet-stream"
    st = get_storage()
    head = st.head(key=key)
    if not head:
        raise HTTPException(404, {"code": "media_missing"})
    size = int(head.get("size") or rec.get("size") or 0)
    range_header = request.headers.get("range")
    if range_header and size > 0:
        try:
            units, rng = range_header.split("=")
            start_s, end_s = rng.split("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
            chunk = st.open_range(key=key, start=start, end=end)
            return Response(content=chunk, status_code=206, media_type=ct,
                            headers={"Content-Range": f"bytes {start}-{end}/{size}",
                                     "Accept-Ranges": "bytes",
                                     "Content-Length": str(len(chunk)),
                                     "Cache-Control": "public, max-age=86400"})
        except Exception:
            pass
    data = st.open_range(key=key, start=0, end=max(0, size - 1))
    return Response(content=data, media_type=ct,
                    headers={"Accept-Ranges": "bytes",
                             "Cache-Control": "public, max-age=86400"})


# ═══════════════════════════ Moments ═══════════════════════════════
class ContextTag(BaseModel):
    kind: str = "custom"          # listening | eating | playing | place | custom
    label: str = Field("", max_length=80)
    sub: Optional[str] = Field(None, max_length=80)


class MomentBody(BaseModel):
    media_url: Optional[str] = None
    media_key: Optional[str] = None
    media_type: Optional[str] = None      # photo | video | voice
    caption: str = Field("", max_length=500)
    context: Optional[ContextTag] = None
    visibility: str = "friends"           # friends | public


def _moment_public(m: dict, viewer: str, author: Optional[dict],
                   liked: bool) -> dict:
    return {
        "moment_id": m["_id"], "user_id": m.get("user_id"),
        "author": author, "is_mine": m.get("user_id") == viewer,
        "media_url": m.get("media_url"), "media_type": m.get("media_type"),
        "caption": m.get("caption"), "context": m.get("context"),
        "visibility": m.get("visibility"), "city": m.get("city"),
        "like_count": int(m.get("like_count") or 0),
        "comment_count": int(m.get("comment_count") or 0),
        "liked_by_me": liked, "created_at": _iso(m.get("created_at")),
    }


@router.post("/moments")
async def create_moment(body: MomentBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    if not body.media_url and not body.caption.strip():
        raise HTTPException(400, {"code": "empty_moment"})
    vis = body.visibility if body.visibility in ("friends", "public") else "friends"
    mid = f"mom_{uuid.uuid4().hex[:16]}"
    doc = {"_id": mid, "user_id": user["user_id"],
           "media_url": body.media_url, "media_key": body.media_key,
           "media_type": body.media_type,
           "caption": body.caption.strip(),
           "context": body.context.model_dump() if body.context else None,
           "visibility": vis, "city": await _user_city(db, user["user_id"]),
           "like_count": 0, "comment_count": 0,
           "created_at": _now(),
           "expires_at": _now() + timedelta(days=MOMENT_TTL_DAYS)}
    await db.social_moments.insert_one(doc)
    pts = 0
    try:
        from routes.dreams_guidance import award_social_share
        pts = await award_social_share(db, user["user_id"], f"moment:{mid}")
    except Exception:
        pts = 0
    author = _user_public(await db.users.find_one({"user_id": user["user_id"]}))
    return {**_moment_public(doc, user["user_id"], author, False),
            "points_awarded": pts}


@router.get("/moments")
async def moments_feed(request: Request, scope: str = "feed",
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    cutoff = _now() - timedelta(days=MOMENT_TTL_DAYS)
    if scope == "mine":
        q: dict = {"user_id": uid}
    else:
        q = {"created_at": {"$gte": cutoff},
             "$or": [{"visibility": "public"},
                     {"user_id": {"$in": list(friends) + [uid]}}]}
    rows: list[dict] = []
    author_ids: set[str] = set()
    async for m in db.social_moments.find(q).sort("created_at", -1).limit(60):
        rows.append(m)
        author_ids.add(m["user_id"])
    authors = await _users_map(db, list(author_ids))
    liked: set[str] = set()
    if rows:
        ids = [m["_id"] for m in rows]
        async for l in db.social_moment_likes.find(
                {"moment_id": {"$in": ids}, "user_id": uid}):
            liked.add(l["moment_id"])
    return {"items": [_moment_public(m, uid, authors.get(m["user_id"]),
                                     m["_id"] in liked) for m in rows]}


async def _moment_or_404(db, mid: str) -> dict:
    m = await db.social_moments.find_one({"_id": mid})
    if not m:
        raise HTTPException(404, {"code": "moment_not_found"})
    return m


@router.post("/moments/{mid}/like")
async def like_moment(mid: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await _moment_or_404(db, mid)
    uid = user["user_id"]
    existing = await db.social_moment_likes.find_one(
        {"moment_id": mid, "user_id": uid})
    if existing:
        await db.social_moment_likes.delete_one({"_id": existing["_id"]})
        await db.social_moments.update_one({"_id": mid}, {"$inc": {"like_count": -1}})
        liked = False
    else:
        await db.social_moment_likes.insert_one(
            {"_id": f"ml_{uuid.uuid4().hex[:16]}", "moment_id": mid,
             "user_id": uid, "created_at": _now()})
        await db.social_moments.update_one({"_id": mid}, {"$inc": {"like_count": 1}})
        liked = True
    m = await db.social_moments.find_one({"_id": mid})
    return {"liked_by_me": liked, "like_count": int(m.get("like_count") or 0)}


class CommentBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)


@router.get("/moments/{mid}/comments")
async def moment_comments(mid: str, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    rows: list[dict] = []
    author_ids: set[str] = set()
    async for c in db.social_moment_comments.find(
            {"moment_id": mid}).sort("created_at", 1).limit(200):
        rows.append(c)
        author_ids.add(c["user_id"])
    authors = await _users_map(db, list(author_ids))
    return {"items": [{"id": c["_id"], "text": c.get("text"),
                       "author": authors.get(c["user_id"]),
                       "created_at": _iso(c.get("created_at"))} for c in rows]}


@router.post("/moments/{mid}/comments")
async def add_moment_comment(mid: str, body: CommentBody, request: Request,
                             user: dict = Depends(current_user)):
    db = request.app.state.db
    await _moment_or_404(db, mid)
    cid = f"mc_{uuid.uuid4().hex[:16]}"
    await db.social_moment_comments.insert_one(
        {"_id": cid, "moment_id": mid, "user_id": user["user_id"],
         "text": body.text.strip(), "created_at": _now()})
    await db.social_moments.update_one({"_id": mid}, {"$inc": {"comment_count": 1}})
    author = _user_public(await db.users.find_one({"user_id": user["user_id"]}))
    return {"id": cid, "text": body.text.strip(), "author": author,
            "created_at": _iso(_now())}


@router.delete("/moments/{mid}")
async def delete_moment(mid: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _moment_or_404(db, mid)
    if m["user_id"] != user["user_id"]:
        raise HTTPException(403, {"code": "not_owner"})
    await db.social_moments.delete_one({"_id": mid})
    await db.social_moment_likes.delete_many({"moment_id": mid})
    await db.social_moment_comments.delete_many({"moment_id": mid})
    return {"ok": True}


# ═══════════════════════════ Go Together ═══════════════════════════
class OutingBody(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    activity: str = Field("hangout", max_length=40)
    place: str = Field("", max_length=160)
    when_text: str = Field("", max_length=80)
    note: str = Field("", max_length=400)
    invitees: list[str] = Field(default_factory=list)
    visibility: str = "friends"       # friends | public


def _outing_public(o: dict, viewer: str, host: Optional[dict],
                   invitees: list[dict]) -> dict:
    rsvps = o.get("rsvps") or {}
    going = [uid for uid, s in rsvps.items() if s == "going"]
    return {
        "outing_id": o["_id"], "host": host,
        "is_host": o.get("host_id") == viewer,
        "title": o.get("title"), "activity": o.get("activity"),
        "place": o.get("place"), "when_text": o.get("when_text"),
        "note": o.get("note"), "visibility": o.get("visibility"),
        "city": o.get("city"), "invitees": invitees,
        "going_count": len(going), "my_rsvp": rsvps.get(viewer),
        "created_at": _iso(o.get("created_at")),
    }


@router.post("/outings")
async def create_outing(body: OutingBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    invitees = [i for i in body.invitees if i in friends][:50]
    vis = body.visibility if body.visibility in ("friends", "public") else "friends"
    oid = f"out_{uuid.uuid4().hex[:16]}"
    doc = {"_id": oid, "host_id": uid, "title": body.title.strip(),
           "activity": body.activity, "place": body.place.strip(),
           "when_text": body.when_text.strip(), "note": body.note.strip(),
           "invitees": invitees, "visibility": vis,
           "city": await _user_city(db, uid),
           "rsvps": {uid: "going"}, "when_at": None, "created_at": _now()}
    await db.social_outings.insert_one(doc)
    for iid in invitees:
        await db.social_notifications.insert_one({
            "_id": f"sn_{uuid.uuid4().hex[:14]}", "user_id": iid, "type": "outing_invite",
            "outing_id": oid, "from": uid, "title": body.title.strip(),
            "read": False, "created_at": _now()})
    host = _user_public(await db.users.find_one({"user_id": uid}))
    inv = list((await _users_map(db, invitees)).values())
    return _outing_public(doc, uid, host, inv)


@router.get("/outings")
async def list_outings(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    city = await _user_city(db, uid)
    q = {"$or": [{"host_id": uid}, {"invitees": uid},
                 {"visibility": "public", "city": city} if city else {"visibility": "public"}]}
    rows: list[dict] = []
    ids: set[str] = set()
    async for o in db.social_outings.find(q).sort("created_at", -1).limit(50):
        rows.append(o)
        ids.add(o["host_id"])
        ids.update(o.get("invitees") or [])
    umap = await _users_map(db, list(ids))
    out = []
    for o in rows:
        inv = [umap[i] for i in (o.get("invitees") or []) if i in umap]
        out.append(_outing_public(o, uid, umap.get(o["host_id"]), inv))
    return {"items": out}


class RsvpBody(BaseModel):
    status: str = Field(..., pattern="^(going|maybe|no)$")


@router.post("/outings/{oid}/rsvp")
async def rsvp_outing(oid: str, body: RsvpBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    o = await db.social_outings.find_one({"_id": oid})
    if not o:
        raise HTTPException(404, {"code": "outing_not_found"})
    await db.social_outings.update_one(
        {"_id": oid}, {"$set": {f"rsvps.{user['user_id']}": body.status}})
    o = await db.social_outings.find_one({"_id": oid})
    rsvps = o.get("rsvps") or {}
    going = [uid for uid, s in rsvps.items() if s == "going"]
    return {"my_rsvp": body.status, "going_count": len(going)}


# ═══════════════════════════ Play Together ═════════════════════════
class PlayBody(BaseModel):
    game_key: str
    title: str = Field("", max_length=120)
    invitees: list[str] = Field(default_factory=list)


def _play_public(p: dict, viewer: str, host: Optional[dict],
                 players: list[dict]) -> dict:
    parts = p.get("participants") or []
    return {"session_id": p["_id"], "game_key": p.get("game_key"),
            "game_label": p.get("game_label"), "title": p.get("title"),
            "host": host, "is_host": p.get("host_id") == viewer,
            "status": p.get("status"), "players": players,
            "player_count": len(parts), "joined": viewer in parts,
            "invited": viewer in (p.get("invitees") or []),
            "created_at": _iso(p.get("created_at"))}


@router.get("/play/games")
async def play_games(user: dict = Depends(current_user)):
    return {"games": GAMES}


@router.post("/play/sessions")
async def create_play_session(body: PlayBody, request: Request,
                              user: dict = Depends(current_user)):
    if body.game_key not in GAME_LABELS:
        raise HTTPException(400, {"code": "unknown_game"})
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    invitees = [i for i in body.invitees if i in friends][:50]
    sid = f"ps_{uuid.uuid4().hex[:16]}"
    doc = {"_id": sid, "host_id": uid, "game_key": body.game_key,
           "game_label": GAME_LABELS[body.game_key],
           "title": body.title.strip() or GAME_LABELS[body.game_key],
           "invitees": invitees, "participants": [uid], "status": "active",
           "created_at": _now()}
    await db.play_sessions.insert_one(doc)
    for iid in invitees:
        await db.social_notifications.insert_one({
            "_id": f"sn_{uuid.uuid4().hex[:14]}", "user_id": iid,
            "type": "play_invite", "session_id": sid, "from": uid,
            "title": doc["title"], "read": False, "created_at": _now()})
    host = _user_public(await db.users.find_one({"user_id": uid}))
    return _play_public(doc, uid, host, [host])


@router.get("/play/sessions")
async def list_play_sessions(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    rows: list[dict] = []
    ids: set[str] = set()
    async for p in db.play_sessions.find(
            {"status": "active"}).sort("created_at", -1).limit(40):
        rows.append(p)
        ids.add(p["host_id"])
        ids.update(p.get("participants") or [])
    umap = await _users_map(db, list(ids))
    out = []
    for p in rows:
        players = [umap[i] for i in (p.get("participants") or []) if i in umap]
        out.append(_play_public(p, uid, umap.get(p["host_id"]), players))
    return {"items": out}


class JoinBody(BaseModel):
    ref: Optional[str] = None       # referrer user_id from a shared invite link


async def _award_play_referral(db, sid: str, joiner: str, ref: Optional[str],
                               host_id: Optional[str],
                               invitees: list[str]) -> Optional[dict]:
    """Reward a viral Play Together join. Both the joining friend AND the
    referrer earn REFERRAL_POINTS. Rewarded once per (session, joiner);
    self-referral is ignored; the points engine's daily cap prevents
    farming. Falls back to the host as referrer when the joiner was in the
    session's explicit invitee list but no ?ref was supplied."""
    referrer: Optional[str] = None
    if ref and ref != joiner:
        if await db.users.find_one({"user_id": ref}, {"_id": 1}):
            referrer = ref
    if not referrer and joiner in (invitees or []) and host_id and host_id != joiner:
        referrer = host_id
    if not referrer:
        return None
    try:
        await db.play_referrals.insert_one(
            {"_id": f"pref_{uuid.uuid4().hex[:16]}", "session_id": sid,
             "joiner_id": joiner, "referrer_id": referrer, "created_at": _now()})
    except Exception:
        return None  # duplicate (already rewarded for this session+joiner)
    svc = PointsService(db)
    jr = await svc.award(
        user_id=joiner, source="game_referral", source_id=sid,
        idempotency_key=f"game_referral:join:{sid}:{joiner}",
        metadata={"role": "joiner", "session_id": sid, "referrer_id": referrer})
    rr = await svc.award(
        user_id=referrer, source="game_referral", source_id=sid,
        idempotency_key=f"game_referral:invite:{sid}:{joiner}",
        metadata={"role": "referrer", "session_id": sid, "joiner_id": joiner})
    return {
        "points": REFERRAL_POINTS,
        "joiner_points": jr.delta if jr.ok else 0,
        "referrer_id": referrer,
        "referrer_points": rr.delta if rr.ok else 0,
    }


@router.post("/play/sessions/{sid}/join")
async def join_play_session(sid: str, request: Request,
                            body: Optional[JoinBody] = Body(default=None),
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    p = await db.play_sessions.find_one({"_id": sid})
    if not p or p.get("status") != "active":
        raise HTTPException(404, {"code": "session_not_found"})
    already = uid in (p.get("participants") or [])
    await db.play_sessions.update_one(
        {"_id": sid}, {"$addToSet": {"participants": uid}})
    reward = None
    if not already:
        reward = await _award_play_referral(
            db, sid, joiner=uid, ref=(body.ref if body else None),
            host_id=p.get("host_id"), invitees=p.get("invitees") or [])
    p = await db.play_sessions.find_one({"_id": sid})
    return {"joined": True, "player_count": len(p.get("participants") or []),
            "reward": reward}


@router.post("/play/sessions/{sid}/leave")
async def leave_play_session(sid: str, request: Request,
                             user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    p = await db.play_sessions.find_one({"_id": sid})
    if not p:
        raise HTTPException(404, {"code": "session_not_found"})
    await db.play_sessions.update_one({"_id": sid}, {"$pull": {"participants": uid}})
    p = await db.play_sessions.find_one({"_id": sid})
    remaining = p.get("participants") or []
    if p.get("host_id") == uid and not remaining:
        await db.play_sessions.update_one({"_id": sid}, {"$set": {"status": "ended"}})
    return {"left": True, "player_count": len(remaining)}


# ═══════════════════════════ Local Pulse ═══════════════════════════
@router.get("/pulse")
async def local_pulse(request: Request, city: Optional[str] = None,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    city = city or await _user_city(db, uid)
    cutoff = _now() - timedelta(days=MOMENT_TTL_DAYS)

    # Public moments near you (fall back to global recent if no city).
    mq: dict = {"visibility": "public", "created_at": {"$gte": cutoff}}
    if city:
        mq["city"] = city
    moments, mids, aids = [], [], set()
    async for m in db.social_moments.find(mq).sort("created_at", -1).limit(20):
        moments.append(m)
        aids.add(m["user_id"])

    # Upcoming public plans near you.
    oq: dict = {"visibility": "public"}
    if city:
        oq["city"] = city
    outings, oaids = [], set()
    async for o in db.social_outings.find(oq).sort("created_at", -1).limit(15):
        outings.append(o)
        oaids.add(o["host_id"])

    # Open play sessions.
    plays, paids = [], set()
    async for p in db.play_sessions.find(
            {"status": "active"}).sort("created_at", -1).limit(10):
        plays.append(p)
        paids.add(p["host_id"])

    umap = await _users_map(db, list(aids | oaids | paids))
    return {
        "city": city,
        "moments": [_moment_public(m, uid, umap.get(m["user_id"]), False)
                    for m in moments],
        "outings": [_outing_public(o, uid, umap.get(o["host_id"]), [])
                    for o in outings],
        "play_sessions": [_play_public(p, uid, umap.get(p["host_id"]), [])
                          for p in plays],
    }


__all__ = ["router", "ensure_social_together"]
