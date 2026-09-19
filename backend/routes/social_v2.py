"""RadioLife Social V2 — Phase 1 (shared backend, design-agnostic).

"Do things together": the social layer that connects PEOPLE + AUDIO +
activity.  Phase 1 ships the shared services the web + mobile clients both
consume:

  • Friend graph      — request / accept / decline / remove / follow / block
  • Social home       — "what's happening now" + friends-right-now
  • Listen Together   — create/join a room around the currently-playing
                        station or podcast, with live text chat + emoji
                        reactions + participant presence (poll-based sync;
                        live = shared station context, podcast = timestamp
                        sync from the host)
  • BigPoints challenge — "listen with a friend for 30 min" awards via the
                        EXISTING points ledger (economics live in the
                        admin-editable points_earn_rules table, not here)

No new auth, no new ledger, no per-design logic.  All routes are /api/social/*.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user
from services.points_service import PointsService

router = APIRouter(prefix="/api/social", tags=["social_v2"])

ROOM_ACTIVE_SEC = 40          # a participant is "present" if seen within this
CHALLENGE_TARGET_MIN = 30     # listen-with-a-friend minutes to earn the reward
LISTEN_TOGETHER_SOURCE = "social_listen_together"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else dt


def _pair_key(a: str, b: str) -> str:
    return ":".join(sorted([a, b]))


# ───────────────────────── Bootstrap ───────────────────────────────
async def ensure_social_v2(db) -> None:
    """Idempotent — indexes + the Listen-Together earn rule."""
    await db.social_friendships.create_index("pair_key", unique=True,
                                                                                        name="sf_pair_uniq")
    await db.social_friendships.create_index("user_a", name="sf_a")
    await db.social_friendships.create_index("user_b", name="sf_b")
    await db.social_follows.create_index([("follower", 1), ("target", 1)],
                                                                              unique=True, name="sfl_uniq")
    await db.social_blocks.create_index([("blocker", 1), ("blocked", 1)],
                                                                            unique=True, name="sb_uniq")
    await db.listen_rooms.create_index([("active", 1), ("last_active_at", -1)],
                                                                          name="lr_active")
    await db.listen_room_participants.create_index(
        [("room_id", 1), ("user_id", 1)], unique=True, name="lrp_uniq")
    await db.listen_room_participants.create_index("user_id", name="lrp_user")
    await db.listen_room_messages.create_index([("room_id", 1), ("created_at", 1)],
                                                                                        name="lrm_room_time")
    await db.listen_room_reactions.create_index([("room_id", 1), ("created_at", 1)],
                                                                                          name="lrr_room_time")
    await db.social_listen_progress.create_index("user_id", name="slp_user")
    # Economics live in the admin-editable rules table (not hardcoded here).
    await db.points_earn_rules.update_one(
        {"rule_id": LISTEN_TOGETHER_SOURCE},
        {"$setOnInsert": {
            "rule_id": LISTEN_TOGETHER_SOURCE,
            "label": "Listen Together (30 min with a friend)",
            "base_points": 50, "daily_cap_per_user": 100,
            "weekly_cap_per_user": None, "monthly_cap_per_user": None,
            "enabled": True, "created_at": _now(), "updated_at": _now(),
        }},
        upsert=True,
    )


# ───────────────────────── Serialization ───────────────────────────
def _user_public(u: dict) -> dict:
    return {
        "user_id": u.get("user_id"),
        "name": u.get("name") or (u.get("email") or "").split("@")[0] or "Listener",
        "avatar_url": u.get("picture") or u.get("avatar_url"),
        "city": u.get("city") or u.get("market"),
    }


async def _users_map(db, ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not ids:
        return out
    async for u in db.users.find({"user_id": {"$in": list(set(ids))}}):
        out[u["user_id"]] = _user_public(u)
    return out


# ───────────────────────── Friend graph helpers ────────────────────
async def _friend_ids(db, uid: str) -> set[str]:
    ids: set[str] = set()
    async for f in db.social_friendships.find(
            {"status": "accepted",
              "$or": [{"user_a": uid}, {"user_b": uid}]}):
        ids.add(f["user_b"] if f["user_a"] == uid else f["user_a"])
    return ids


async def _blocked_pair(db, a: str, b: str) -> bool:
    doc = await db.social_blocks.find_one(
        {"$or": [{"blocker": a, "blocked": b}, {"blocker": b, "blocked": a}]})
    return doc is not None


# ───────────────────────── Friend graph API ────────────────────────
class UserIdBody(BaseModel):
    user_id: str


@router.get("/users/search")
async def search_users(q: str = "", request: Request = None,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    q = (q or "").strip()
    if len(q) < 2:
        return {"items": []}
    blocked = set()
    async for b in db.social_blocks.find(
            {"$or": [{"blocker": uid}, {"blocked": uid}]}):
        blocked.add(b["blocked"] if b["blocker"] == uid else b["blocker"])
    rx = {"$regex": q, "$options": "i"}
    rows: list[dict] = []
    async for u in db.users.find(
            {"$or": [{"name": rx}, {"email": rx}],
              "user_id": {"$ne": uid}}).limit(20):
        if u["user_id"] in blocked:
            continue
        rows.append(_user_public(u))
    # annotate relationship
    friends = await _friend_ids(db, uid)
    pend = set()
    async for f in db.social_friendships.find(
            {"status": "pending", "$or": [{"user_a": uid}, {"user_b": uid}]}):
        pend.add(f["user_b"] if f["user_a"] == uid else f["user_a"])
    for r in rows:
        r["relationship"] = ("friend" if r["user_id"] in friends
                                              else "pending" if r["user_id"] in pend else "none")
    return {"items": rows}


@router.get("/friends")
async def list_friends(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends, incoming, outgoing = [], [], []
    ids: list[str] = []
    rows: list[dict] = []
    async for f in db.social_friendships.find(
            {"$or": [{"user_a": uid}, {"user_b": uid}]}):
        other = f["user_b"] if f["user_a"] == uid else f["user_a"]
        ids.append(other)
        rows.append((f, other))
    umap = await _users_map(db, ids)
    for f, other in rows:
        pub = umap.get(other) or {"user_id": other, "name": "Listener"}
        if f["status"] == "accepted":
            friends.append(pub)
        elif f["status"] == "pending":
            if f["requested_by"] == uid:
                outgoing.append(pub)
            else:
                incoming.append(pub)
    return {"friends": friends, "incoming": incoming, "outgoing": outgoing,
                    "counts": {"friends": len(friends), "incoming": len(incoming),
                                        "outgoing": len(outgoing)}}


@router.post("/friends/request")
async def friend_request(body: UserIdBody, request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    other = body.user_id
    if other == uid:
        raise HTTPException(400, "cannot_friend_self")
    if not await db.users.find_one({"user_id": other}, {"_id": 1}):
        raise HTTPException(404, "user_not_found")
    if await _blocked_pair(db, uid, other):
        raise HTTPException(403, "blocked")
    pk = _pair_key(uid, other)
    existing = await db.social_friendships.find_one({"pair_key": pk})
    if existing:
        if existing["status"] == "accepted":
            return {"status": "accepted"}
        # if the OTHER person already requested → accept it
        if existing["status"] == "pending" and existing["requested_by"] == other:
            await db.social_friendships.update_one(
                {"pair_key": pk}, {"$set": {"status": "accepted",
                                                                      "updated_at": _now()}})
            return {"status": "accepted"}
        return {"status": "pending"}
    a, b = sorted([uid, other])
    await db.social_friendships.insert_one({
        "_id": f"fr_{uuid.uuid4().hex[:16]}", "pair_key": pk,
        "user_a": a, "user_b": b, "status": "pending",
        "requested_by": uid, "created_at": _now(), "updated_at": _now()})
    return {"status": "pending"}


@router.post("/friends/{other}/accept")
async def friend_accept(other: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    pk = _pair_key(uid, other)
    f = await db.social_friendships.find_one({"pair_key": pk})
    if not f or f["status"] != "pending":
        raise HTTPException(404, "no_pending_request")
    if f["requested_by"] == uid:
        raise HTTPException(400, "cannot_accept_own_request")
    await db.social_friendships.update_one(
        {"pair_key": pk}, {"$set": {"status": "accepted", "updated_at": _now()}})
    return {"status": "accepted"}


@router.post("/friends/{other}/decline")
async def friend_decline(other: str, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    await db.social_friendships.delete_one({"pair_key": _pair_key(uid, other)})
    return {"status": "removed"}


@router.delete("/friends/{other}")
async def friend_remove(other: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    await db.social_friendships.delete_one({"pair_key": _pair_key(uid, other)})
    return {"status": "removed"}


@router.post("/friends/{other}/block")
async def block_user(other: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    if other == uid:
        raise HTTPException(400, "cannot_block_self")
    await db.social_friendships.delete_one({"pair_key": _pair_key(uid, other)})
    await db.social_follows.delete_many(
        {"$or": [{"follower": uid, "target": other},
                          {"follower": other, "target": uid}]})
    await db.social_blocks.update_one(
        {"blocker": uid, "blocked": other},
        {"$setOnInsert": {"blocker": uid, "blocked": other, "created_at": _now()}},
        upsert=True)
    return {"status": "blocked"}


@router.post("/friends/{other}/unblock")
async def unblock_user(other: str, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.social_blocks.delete_one(
        {"blocker": user["user_id"], "blocked": other})
    return {"status": "unblocked"}


@router.post("/follow/{other}")
async def follow_user(other: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    if other == uid:
        raise HTTPException(400, "cannot_follow_self")
    if await _blocked_pair(db, uid, other):
        raise HTTPException(403, "blocked")
    await db.social_follows.update_one(
        {"follower": uid, "target": other},
        {"$setOnInsert": {"follower": uid, "target": other, "created_at": _now()}},
        upsert=True)
    return {"status": "following"}


@router.delete("/follow/{other}")
async def unfollow_user(other: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.social_follows.delete_one(
        {"follower": user["user_id"], "target": other})
    return {"status": "unfollowed"}


# ───────────────────────── Listen Together rooms ───────────────────
class CreateRoomBody(BaseModel):
    title: Optional[str] = None
    visibility: str = "public"          # public | friends | private
    content_type: str = "live"          # live | podcast
    content: dict = {}                  # station/podcast snapshot from the player
    playback: Optional[dict] = None     # {position_sec, is_playing} for podcast


class MessageBody(BaseModel):
    text: str


class ReactionBody(BaseModel):
    emoji: str


class PlaybackBody(BaseModel):
    position_sec: float = 0
    is_playing: bool = True


def _room_public(r: dict, participants: int = 0) -> dict:
    return {
        "room_id": r["_id"], "title": r.get("title"),
        "visibility": r.get("visibility"), "content_type": r.get("content_type"),
        "content": r.get("content") or {}, "host_user_id": r.get("host_user_id"),
        "host_name": r.get("host_name"),
        "participant_count": participants or r.get("participant_count", 0),
        "playback": r.get("playback"),
        "created_at": _iso(r.get("created_at")),
        "last_active_at": _iso(r.get("last_active_at")),
    }


async def _active_participants(db, room_id: str) -> list[dict]:
    cutoff = _now() - timedelta(seconds=ROOM_ACTIVE_SEC)
    rows: list[dict] = []
    async for p in db.listen_room_participants.find(
            {"room_id": room_id, "active": True, "last_seen_at": {"$gte": cutoff}}):
        rows.append({"user_id": p["user_id"], "name": p.get("name"),
                                "avatar_url": p.get("avatar_url"),
                                "role": p.get("role", "guest")})
    return rows


async def _touch_participant(db, room_id: str, user: dict, role: str = "guest"):
    pub = _user_public(user)
    await db.listen_room_participants.update_one(
        {"room_id": room_id, "user_id": user["user_id"]},
        {"$set": {"active": True, "last_seen_at": _now(),
                          "name": pub["name"], "avatar_url": pub["avatar_url"]},
          "$setOnInsert": {"joined_at": _now(), "role": role}},
        upsert=True)
    await db.listen_rooms.update_one(
        {"_id": room_id}, {"$set": {"last_active_at": _now(), "active": True}})


@router.post("/rooms")
async def create_room(body: CreateRoomBody, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    if body.visibility not in ("public", "friends", "private"):
        raise HTTPException(400, "bad_visibility")
    if body.content_type not in ("live", "podcast"):
        raise HTTPException(400, "bad_content_type")
    pub = _user_public(user)
    rid = f"lr_{uuid.uuid4().hex[:16]}"
    title = (body.title or "").strip() or (
        (body.content or {}).get("name") or "Listening Room")
    doc = {
        "_id": rid, "host_user_id": user["user_id"], "host_name": pub["name"],
        "title": title, "visibility": body.visibility,
        "content_type": body.content_type, "content": body.content or {},
        "playback": ({"position_sec": float((body.playback or {}).get("position_sec", 0)),
                                  "is_playing": bool((body.playback or {}).get("is_playing", True)),
                                  "updated_at": _now().isoformat()}
                                if body.content_type == "podcast" else None),
        "active": True, "participant_count": 1,
        "created_at": _now(), "last_active_at": _now()}
    await db.listen_rooms.insert_one(doc)
    await _touch_participant(db, rid, user, role="host")
    return _room_public(doc, participants=1)


@router.get("/rooms")
async def list_rooms(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    cutoff = _now() - timedelta(seconds=ROOM_ACTIVE_SEC * 3)
    out: list[dict] = []
    async for r in db.listen_rooms.find(
            {"active": True, "last_active_at": {"$gte": cutoff}}
            ).sort("last_active_at", -1).limit(50):
        vis = r.get("visibility")
        if vis == "private" and r.get("host_user_id") != uid:
            continue
        if vis == "friends" and r.get("host_user_id") != uid \
                and r.get("host_user_id") not in friends:
            continue
        parts = await _active_participants(db, r["_id"])
        if not parts and r.get("host_user_id") != uid:
            continue
        rp = _room_public(r, participants=len(parts))
        rp["participants_preview"] = parts[:5]
        rp["has_friend"] = any(p["user_id"] in friends for p in parts)
        out.append(rp)
    out.sort(key=lambda x: (not x["has_friend"], -x["participant_count"]))
    return {"items": out}


async def _room_or_404(db, room_id: str) -> dict:
    r = await db.listen_rooms.find_one({"_id": room_id})
    if not r or not r.get("active"):
        raise HTTPException(404, "room_not_found")
    return r


@router.get("/rooms/{room_id}")
async def get_room(room_id: str, request: Request,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await _room_or_404(db, room_id)
    parts = await _active_participants(db, room_id)
    msgs: list[dict] = []
    async for m in db.listen_room_messages.find({"room_id": room_id}
                                                                                      ).sort("created_at", -1).limit(50):
        msgs.append({"id": m["_id"], "user_id": m["user_id"], "name": m.get("name"),
                                  "avatar_url": m.get("avatar_url"), "text": m.get("text"),
                                  "created_at": _iso(m.get("created_at"))})
    msgs.reverse()
    rp = _room_public(r, participants=len(parts))
    rp["participants"] = parts
    rp["messages"] = msgs
    return rp


@router.post("/rooms/{room_id}/join")
async def join_room(room_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await _room_or_404(db, room_id)
    uid = user["user_id"]
    if r.get("visibility") == "friends" and r.get("host_user_id") != uid:
        friends = await _friend_ids(db, uid)
        if r.get("host_user_id") not in friends:
            raise HTTPException(403, "friends_only")
    await _touch_participant(db, room_id, user,
                                                    role="host" if r.get("host_user_id") == uid else "guest")
    return await get_room(room_id, request, user)


@router.post("/rooms/{room_id}/leave")
async def leave_room(room_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.listen_room_participants.update_one(
        {"room_id": room_id, "user_id": user["user_id"]},
        {"$set": {"active": False, "last_seen_at": _now()}})
    # If the host left and nobody remains, close the room.
    r = await db.listen_rooms.find_one({"_id": room_id})
    if r:
        parts = await _active_participants(db, room_id)
        if not parts:
            await db.listen_rooms.update_one({"_id": room_id},
                                                                              {"$set": {"active": False}})
    return {"status": "left"}


@router.post("/rooms/{room_id}/messages")
async def post_message(room_id: str, body: MessageBody, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _room_or_404(db, room_id)
    text = (body.text or "").strip()[:500]
    if not text:
        raise HTTPException(400, "empty")
    pub = _user_public(user)
    mid = f"msg_{uuid.uuid4().hex[:16]}"
    await db.listen_room_messages.insert_one({
        "_id": mid, "room_id": room_id, "user_id": user["user_id"],
        "name": pub["name"], "avatar_url": pub["avatar_url"],
        "text": text, "created_at": _now()})
    await _touch_participant(db, room_id, user)
    return {"id": mid, "text": text, "created_at": _now().isoformat(),
                    "user_id": user["user_id"], "name": pub["name"]}


@router.post("/rooms/{room_id}/reactions")
async def post_reaction(room_id: str, body: ReactionBody, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    await _room_or_404(db, room_id)
    emoji = (body.emoji or "").strip()[:8] or "❤️"
    await db.listen_room_reactions.insert_one({
        "_id": f"rx_{uuid.uuid4().hex[:14]}", "room_id": room_id,
        "user_id": user["user_id"], "emoji": emoji, "created_at": _now()})
    await _touch_participant(db, room_id, user)
    return {"ok": True, "emoji": emoji}


@router.post("/rooms/{room_id}/playback")
async def set_playback(room_id: str, body: PlaybackBody, request: Request,
                                              user: dict = Depends(current_user)):
    """Host-only timestamp sync for on-demand/podcast rooms."""
    db = request.app.state.db
    r = await _room_or_404(db, room_id)
    if r.get("host_user_id") != user["user_id"]:
        raise HTTPException(403, "host_only")
    if r.get("content_type") != "podcast":
        raise HTTPException(400, "not_podcast_room")
    await db.listen_rooms.update_one({"_id": room_id}, {"$set": {
        "playback": {"position_sec": float(body.position_sec),
                                  "is_playing": bool(body.is_playing),
                                  "updated_at": _now().isoformat()},
        "last_active_at": _now()}})
    return {"ok": True}


async def _award_listen_challenge(db, uid: str) -> dict:
    """Increment listen-with-a-friend minutes and award once/day at target."""
    today = _now().strftime("%Y-%m-%d")
    doc_id = f"{uid}:{today}"
    doc = await db.social_listen_progress.find_one({"_id": doc_id})
    now = _now()
    if not doc:
        doc = {"_id": doc_id, "user_id": uid, "date": today,
                      "minutes": 0, "awarded": False, "last_credit_at": None}
        await db.social_listen_progress.insert_one(doc)
    last = doc.get("last_credit_at")
    if last and getattr(last, "tzinfo", None) is None:
        last = last.replace(tzinfo=timezone.utc)  # Motor returns naive UTC
    # Credit at most ~1 minute per real minute (abuse-resistant).
    if not last or (now - last) >= timedelta(seconds=55):
        doc["minutes"] = int(doc.get("minutes", 0)) + 1
        await db.social_listen_progress.update_one(
            {"_id": doc_id}, {"$set": {"minutes": doc["minutes"],
                                                              "last_credit_at": now}})
    awarded = bool(doc.get("awarded"))
    if not awarded and doc["minutes"] >= CHALLENGE_TARGET_MIN:
        res = await PointsService(db).award(
            user_id=uid, source=LISTEN_TOGETHER_SOURCE,
            metadata={"challenge": "listen_together_30min", "date": today},
            idempotency_key=f"slt:{uid}:{today}")
        awarded = res.ok or res.idempotency_hit
        await db.social_listen_progress.update_one(
            {"_id": doc_id}, {"$set": {"awarded": awarded}})
    return {"minutes": doc["minutes"], "target": CHALLENGE_TARGET_MIN,
                    "awarded": awarded, "reward_points": 50}


@router.post("/rooms/{room_id}/heartbeat")
async def room_heartbeat(room_id: str, request: Request,
                                                  since: Optional[str] = None,
                                                  user: dict = Depends(current_user)):
    """Presence + poll delta + BigPoints challenge progress."""
    db = request.app.state.db
    r = await _room_or_404(db, room_id)
    uid = user["user_id"]
    await _touch_participant(db, room_id, user,
                                                    role="host" if r.get("host_user_id") == uid else "guest")
    parts = await _active_participants(db, room_id)
    # Challenge: only counts while a FRIEND is present in the room.
    friends = await _friend_ids(db, uid)
    friend_present = any(p["user_id"] in friends for p in parts)
    challenge = (await _award_listen_challenge(db, uid)
                              if friend_present else None)

    # Poll delta since the client's last cursor.
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            since_dt = None
    mq: dict = {"room_id": room_id}
    if since_dt:
        mq["created_at"] = {"$gt": since_dt}
    new_msgs: list[dict] = []
    async for m in db.listen_room_messages.find(mq).sort("created_at", 1).limit(60):
        new_msgs.append({"id": m["_id"], "user_id": m["user_id"],
                                          "name": m.get("name"), "avatar_url": m.get("avatar_url"),
                                          "text": m.get("text"), "created_at": _iso(m.get("created_at"))})
    rx_cut = since_dt or (_now() - timedelta(seconds=6))
    new_rx: list[dict] = []
    async for x in db.listen_room_reactions.find(
            {"room_id": room_id, "created_at": {"$gt": rx_cut}}
            ).sort("created_at", 1).limit(40):
        new_rx.append({"emoji": x["emoji"], "user_id": x["user_id"],
                                    "created_at": _iso(x["created_at"])})
    return {
        "server_time": _now().isoformat(),
        "participants": parts, "participant_count": len(parts),
        "messages": new_msgs, "reactions": new_rx,
        "playback": r.get("playback"),
        "content": r.get("content") or {},
        "content_type": r.get("content_type"),
        "challenge": challenge,
        "active": r.get("active", True),
    }


# ───────────────────────── Social home + activity ──────────────────
@router.get("/home")
async def social_home(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    cutoff = _now() - timedelta(seconds=ROOM_ACTIVE_SEC)

    # Friends right now — active in a listen room.
    friends_now: list[dict] = []
    seen: set[str] = set()
    live_rooms = 0
    async for r in db.listen_rooms.find(
            {"active": True, "last_active_at": {"$gte": _now() - timedelta(minutes=5)}}
            ).sort("last_active_at", -1).limit(60):
        parts = await _active_participants(db, r["_id"])
        if parts:
            live_rooms += 1
        for p in parts:
            if p["user_id"] in friends and p["user_id"] not in seen:
                seen.add(p["user_id"])
                friends_now.append({**p, "activity": "listening",
                                                        "context": (r.get("content") or {}).get("name")
                                                                          or r.get("title"),
                                                        "room_id": r["_id"]})

    # Suggested rooms (public + friends', currently active).
    suggested = (await list_rooms(request, user))["items"][:8]

    friend_count = len(friends)
    incoming = await db.social_friendships.count_documents(
        {"status": "pending", "requested_by": {"$ne": uid},
          "$or": [{"user_a": uid}, {"user_b": uid}]})

    return {
        "happening_now": {
            "live_experiences": len(suggested),
            "friends_listening": len(friends_now),
            "friends_online": len(friends_now),
        },
        "friends_now": friends_now,
        "suggested_rooms": suggested,
        "counts": {"friends": friend_count, "friend_requests": incoming},
        "do_together": [
            {"key": "listen", "label": "Listen Together"},
            {"key": "play", "label": "Play Together"},
            {"key": "go", "label": "Go Together"},
            {"key": "shop", "label": "Shop Together"},
        ],
    }


@router.get("/activity")
async def social_activity(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    items: list[dict] = []
    seen: set[str] = set()
    async for r in db.listen_rooms.find(
            {"active": True, "last_active_at": {"$gte": _now() - timedelta(minutes=10)}}
            ).sort("last_active_at", -1).limit(60):
        parts = await _active_participants(db, r["_id"])
        for p in parts:
            if p["user_id"] in friends and p["user_id"] not in seen:
                seen.add(p["user_id"])
                items.append({
                    "user_id": p["user_id"], "name": p["name"],
                    "avatar_url": p["avatar_url"], "verb": "is listening to",
                    "target": (r.get("content") or {}).get("name") or r.get("title"),
                    "room_id": r["_id"], "at": _iso(r.get("last_active_at"))})
    return {"items": items}


__all__ = ["router", "ensure_social_v2"]
