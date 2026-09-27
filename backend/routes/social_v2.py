"""FUUSIC Social V2 — Phase 1 (shared backend, design-agnostic).

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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user
from services.points_service import PointsService
from services.social_following import resolve_following, following_summary
from services.social_feed import build_feed, build_rail, WALL_TYPES

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
    await db.social_feed_events.create_index(
        [("user_id", 1), ("created_at", -1)], name="sfe_user_time")
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
    try:
        await seed_social_v2_demo(db)
    except Exception:
        pass


async def seed_social_v2_demo(db) -> None:
    """Idempotent — give the demo account a rich Following graph + wall so the
    combined feed isn't empty in preview: follow the seeded advisors, one
    community station, and seed a public moment + shared tarot + station post
    from a followed advisor."""
    demo = await db.users.find_one({"email": "demo@bigfm.dubai"}, {"user_id": 1})
    if not demo:
        return
    uid = demo["user_id"]

    # Follow every approved advisor (they carry public dreams) — but NOT the
    # sample "suggested" creators seeded below (those stay unfollowed so the
    # Right Rail always has follow suggestions to show).
    advisor_ids: list[str] = []
    async for a in db.advisor_profiles.find(
            {"demo_rail_suggested": {"$ne": True}}, {"user_id": 1}):
        aid = a.get("user_id")
        if aid and aid != uid:
            advisor_ids.append(aid)
            await db.social_follows.update_one(
                {"follower": uid, "target": aid},
                {"$setOnInsert": {"follower": uid, "target": aid, "created_at": _now()}},
                upsert=True)

    # Follow the top public community station.
    st = await db.community_radio_stations.find_one(
        {"status": "published", "privacy": "public"},
        sort=[("follower_count", -1)])
    if st and st.get("station_id"):
        await db.station_followers.update_one(
            {"user_id": uid, "station_id": st["station_id"]},
            {"$setOnInsert": {"followed_at": _now().isoformat()}}, upsert=True)
        # A followed-station post → STATION_ACTIVITY card.
        if not await db.social_posts.find_one({"_id": "post_demo_social_1"}):
            await db.social_posts.insert_one({
                "_id": "post_demo_social_1", "post_id": "post_demo_social_1",
                "page_id": st["station_id"], "author_user_id": st.get("owner_user_id"),
                "post_type": "text", "text": "New mix dropping tonight — tune in! 🎧",
                "media_urls": [], "visibility": "public",
                "approval_status": "approved", "status": "approved",
                "reaction_counts": {}, "comment_count": 0, "share_count": 0,
                "created_at": _now().isoformat()})

    if not advisor_ids:
        return
    a0 = advisor_ids[0]

    # A public moment from a followed advisor → MOMENT card.
    if not await db.social_moments.find_one({"_id": "mom_demo_social_1"}):
        await db.social_moments.insert_one({
            "_id": "mom_demo_social_1", "user_id": a0,
            "media_url": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?crop=entropy&cs=srgb&fm=jpg&q=85&w=1000",
            "media_type": "photo",
            "caption": "Golden hour on the marina 🌇 good energy tonight ✨",
            "context": None, "visibility": "public",
            "city": "Dubai", "like_count": 12, "comment_count": 3,
            "created_at": _now(),
            "expires_at": _now() + timedelta(days=7)})

    # A shared tarot reading from a followed advisor → TAROT_SHARE card.
    if not await db.ai_readings.find_one({"_id": "rd_demo_social_tarot_1"}):
        await db.ai_readings.insert_one({
            "_id": "rd_demo_social_tarot_1", "reading_id": "rd_demo_social_tarot_1",
            "user_id": a0, "type": "tarot", "subject": "What's the energy for this week?",
            "title": "Tarot — 3-card spread",
            "result": "A week of gentle momentum — trust the pull toward something new.",
            "cards": [{"name": "The Star", "orientation": "upright", "position": "Past"},
                      {"name": "The Sun", "orientation": "upright", "position": "Present"},
                      {"name": "The World", "orientation": "upright", "position": "Future"}],
            "public": True, "created_at": _now()})

    # ── Right-Rail sample suggestions (NOT followed by demo) ──────────
    # A small set of creators / stations / a live show so the compact Right
    # Rail always has 5–7 contextual cards to surface in preview.
    _P = ("https://images.unsplash.com/photo-{id}?crop=entropy&cs=srgb"
          "&fm=jpg&q=80&w=400")
    rail_creators = [
        ("usr_rail_c1", "Layla Haddad", "Astrologer & Sound Healer", "Dubai",
         _P.format(id="1506863530036-1efeddceb993")),
        ("usr_rail_c2", "Marco Rossi", "Live DJ · House & Lounge", "Abu Dhabi",
         _P.format(id="1507003211169-0a1dd7228f2d")),
        ("usr_rail_c3", "Daniel Weber", "Podcast Host · Late Nights", "Sharjah",
         _P.format(id="1560250097-0b93528c311a")),
        ("usr_rail_c4", "Omar Nasser", "Dream Interpreter & Guide", "Dubai",
         _P.format(id="1500648767791-00dcc994a43e")),
    ]
    for cid, cname, tagline, city, pic in rail_creators:
        await db.users.update_one(
            {"user_id": cid},
            {"$setOnInsert": {"user_id": cid, "email": f"{cid}@bigfm.dubai",
                              "name": cname, "picture": pic, "city": city,
                              "is_demo_sample": True, "created_at": _now()}},
            upsert=True)
        await db.advisor_profiles.update_one(
            {"user_id": cid},
            {"$setOnInsert": {"user_id": cid, "advisor_id": f"adv_rail_{cid}",
                              "status": "approved",
                              "headline": tagline, "demo_rail_suggested": True,
                              "created_at": _now()}},
            upsert=True)

    rail_stations = [
        ("stn_rail_1", "rail-midnight-fm", "Midnight FM", "Late-night lounge",
         "https://images.unsplash.com/photo-1478737270239-2f02b77fc618?crop=entropy&cs=srgb&fm=jpg&q=80&w=600",
         "usr_rail_c2"),
        ("stn_rail_2", "rail-desert-waves", "Desert Waves Radio", "Chillout & world",
         "https://images.unsplash.com/photo-1531651008558-ed1740375b39?crop=entropy&cs=srgb&fm=jpg&q=80&w=600",
         "usr_rail_c3"),
    ]
    for sid, slug, sname, ptype, cover, owner in rail_stations:
        await db.community_radio_stations.update_one(
            {"station_id": sid},
            {"$setOnInsert": {"station_id": sid, "slug": slug, "name": sname,
                              "page_type": ptype, "cover_image_url": cover,
                              "owner_user_id": owner, "status": "published",
                              "privacy": "unlisted", "follower_count": 0,
                              "is_demo_sample": True, "created_at": _now()}},
            upsert=True)

    # One live-now show hosted by a followed advisor → high-rank LIVE card.
    if not await db.live_shows.find_one({"_id": "lsw_rail_live_1"}):
        await db.live_shows.insert_one({
            "_id": "lsw_rail_live_1", "show_id": "lsw_rail_live_1",
            "host_id": a0, "title": "Sunset Sessions — live now",
            "description": "Deep house & lounge, streaming live from the marina.",
            "cover_url": "https://images.unsplash.com/photo-1563841930606-67e2bce48b78?crop=entropy&cs=srgb&fm=jpg&q=80&w=800",
            "status": "live", "started_at": _now(), "created_at": _now()})


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
    follow_stats = await following_summary(db, uid)

    return {
        "happening_now": {
            "live_experiences": len(suggested),
            "friends_listening": len(friends_now),
            "friends_online": len(friends_now),
            "following": follow_stats["count"],
        },
        "friends_now": friends_now,
        "suggested_rooms": suggested,
        "counts": {"friends": friend_count, "friend_requests": incoming,
                   "following": follow_stats["count"]},
        "do_together": [
            {"key": "listen", "label": "Listen Together"},
            {"key": "play", "label": "Play Together"},
            {"key": "go", "label": "Go Together"},
            {"key": "shop", "label": "Shop Together"},
        ],
    }


# ───────────────────────── Following graph ─────────────────────────
@router.get("/following")
async def get_following(request: Request, user: dict = Depends(current_user)):
    """Unified 'who/what you follow' — people, creators, advisors, businesses,
    stations & clubs, aggregated from the existing follow sources."""
    return await resolve_following(request.app.state.db, user["user_id"])


# ───────────────────────── Combined social wall ────────────────────
FEED_EVENTS = {
    "social_feed_view", "social_feed_mode_following", "social_feed_mode_for_you",
    "feed_item_impression", "feed_item_open", "feed_follow_click",
    "feed_unfollow", "feed_join_room", "feed_watch_live", "feed_comment",
    "feed_share", "feed_dream_similar", "feed_tarot_open",
    "following_page_view", "following_filter", "following_profile_open",
    "following_unfollow",
}


@router.get("/feed-v2")
async def feed_v2(request: Request, background_tasks: BackgroundTasks,
                  mode: str = "following", cursor: Optional[str] = None,
                  limit: int = 20, types: Optional[str] = None,
                  user: dict = Depends(current_user)):
    """The combined Social wall — real DB activity from followed people,
    friends, businesses, stations & clubs, layered-ranked (deterministic +
    cached AI rerank). `mode=following|for_you`."""
    type_list = [t for t in (types or "").split(",") if t.strip()] or None
    return await build_feed(request.app.state.db, user, mode=mode,
                            cursor=cursor, limit=limit, types=type_list,
                            background_tasks=background_tasks)


@router.get("/feed-v2/new-count")
async def feed_v2_new_count(request: Request, since: Optional[str] = None,
                            mode: str = "following",
                            user: dict = Depends(current_user)):
    """How many wall items are newer than `since` — powers the
    'N new posts' banner without disturbing the reader's scroll."""
    db = request.app.state.db
    res = await build_feed(db, user, mode=mode, limit=40)
    items = res.get("items") or []
    if not since:
        return {"new_count": 0, "latest": items[0]["created_at"] if items else None}
    from datetime import datetime as _d, timezone as _tz
    # A '+' in the tz offset is decoded as a space by some clients
    # (e.g. "…T00:00:00+00:00" → "…T00:00:00 00:00"); recover it when a
    # 'T' separator is present so the offset parses correctly.
    raw = (since or "").strip()
    if "T" in raw:
        raw = raw.replace(" ", "+")
    raw = raw.replace("Z", "+00:00")
    try:
        cutoff = _d.fromisoformat(raw)
    except ValueError:
        return {"new_count": 0, "latest": items[0]["created_at"] if items else None}
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=_tz.utc)
    n = 0
    for it in items:
        try:
            ts = _d.fromisoformat((it["created_at"] or "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_tz.utc)
        if ts > cutoff:
            n += 1
    return {"new_count": n, "latest": items[0]["created_at"] if items else None}


@router.get("/rail")
async def social_rail(request: Request, page_route: str = "/home",
                      limit: int = 7, user: dict = Depends(current_user)):
    """Compact Right-Rail: 5–7 contextual cards mixing live shows, upcoming
    events, suggested people to follow and stations to tune into."""
    return await build_rail(request.app.state.db, user,
                            page_route=page_route, limit=limit)


class FeedEventBody(BaseModel):
    event: str
    item_id: Optional[str] = None
    item_type: Optional[str] = None
    mode: Optional[str] = None
    position: Optional[int] = None
    meta: Optional[dict] = None


@router.post("/feed-events")
async def feed_event(body: FeedEventBody, request: Request,
                     user: dict = Depends(current_user)):
    """Allowlisted, fire-and-forget social feed analytics."""
    if body.event not in FEED_EVENTS:
        return {"ok": False, "reason": "event_not_allowed"}
    db = request.app.state.db
    await db.social_feed_events.insert_one({
        "user_id": user["user_id"], "event": body.event,
        "item_id": body.item_id, "item_type": body.item_type,
        "mode": body.mode, "position": body.position,
        "meta": body.meta or {}, "created_at": _now()})
    return {"ok": True}


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
