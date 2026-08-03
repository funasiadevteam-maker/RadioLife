"""Phase 7 — Lobby business logic (mongo + radio engine glue).

Pure-function-style helpers — no FastAPI imports. All routes in
`routes/lobbies.py` call into here. Reuses the radio engine via the helpers
exposed on `app.state.radio` (set up at server.py startup).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

logger = logging.getLogger("bigfm.lobby")

# Caps
FREE_HOST_MAX_LISTENERS = 50
PREMIUM_HOST_MAX_LISTENERS = 200
FREE_JOIN_DAILY_CAP = 3
SKIP_CAP_PER_HOUR = 6
INVITE_TTL_HOURS = 24
HOST_TOKEN_TTL_HOURS = 1
CHAT_MAX_LEN = 240
NAME_MAX_LEN = 60
DESC_MAX_LEN = 200
EMOJI_WHITELIST = {
    "❤️", "🔥", "👍", "👏", "🎉", "🎶", "🕺", "💃", "🪩",
    "😍", "😂", "🤩", "😎", "🙏", "💯", "🚀", "✨", "🎵", "🎤", "🎧",
}

AVATAR_COLORS = ["#ff2d95", "#7BD3F7", "#fdb756", "#4ade80",
                  "#a78bfa", "#fb7185", "#f97316", "#06b6d4"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def avatar_color_for(user_id: str) -> str:
    h = hashlib.sha256((user_id or "").encode()).hexdigest()
    return AVATAR_COLORS[int(h[:4], 16) % len(AVATAR_COLORS)]


def host_max_for_user(user: dict) -> int:
    return PREMIUM_HOST_MAX_LISTENERS if user.get("is_premium") else FREE_HOST_MAX_LISTENERS


async def ensure_lobby_indexes(db) -> None:
    await db.lobbies.create_index([("status", 1), ("current_listener_count", -1)])
    await db.lobbies.create_index([("is_public", 1), ("status", 1)])
    await db.lobbies.create_index([("host_user_id", 1), ("status", 1)])
    await db.lobby_members.create_index([("lobby_id", 1), ("user_id", 1)], unique=True)
    await db.lobby_members.create_index([("lobby_id", 1), ("left_at", 1)])
    await db.lobby_messages.create_index([("lobby_id", 1), ("created_at", -1)])
    await db.lobby_skip_votes.create_index([("lobby_id", 1), ("segment_id", 1)], unique=True)
    await db.lobby_events_log.create_index([("lobby_id", 1), ("ts", -1)])
    await db.lobby_invites.create_index("token", unique=True)
    await db.lobby_invites.create_index("expires_at",
                                          expireAfterSeconds=INVITE_TTL_HOURS * 3600 + 600)
    await db.lobby_joins_daily.create_index([("user_id", 1), ("day", 1)], unique=True)


# ----------------------------------------------------------------------
async def log_event(db, *, lobby_id: str, event_type: str,
                       actor_user_id: Optional[str] = None,
                       payload: Optional[dict] = None) -> None:
    await db.lobby_events_log.insert_one({
        "_id": f"evt_{uuid.uuid4().hex[:14]}",
        "lobby_id": lobby_id, "event_type": event_type,
        "actor_user_id": actor_user_id,
        "payload_json": payload or {}, "ts": _now(),
    })


# ----------------------------------------------------------------------
def _validate_name(name: Optional[str]) -> str:
    name = (name or "").strip()
    if not name or len(name) > NAME_MAX_LEN:
        raise ValueError(f"name must be 1..{NAME_MAX_LEN} chars")
    return name


async def create_lobby(db, host: dict, *, name: str, channel_slug: str,
                          mood: Optional[str], activity: Optional[str],
                          description: Optional[str] = None,
                          city: Optional[str] = None,
                          is_public: bool = True,
                          max_listeners: Optional[int] = None) -> dict:
    name = _validate_name(name)
    cap = host_max_for_user(host)
    if max_listeners is None:
        max_listeners = cap
    max_listeners = max(2, min(int(max_listeners), cap))
    desc = (description or "").strip()[:DESC_MAX_LEN] or None

    # Channel must exist
    ch = await db.channels.find_one({"_id": channel_slug, "active": True},
                                        {"_id": 1, "name": 1, "premium_only": 1})
    if not ch:
        raise ValueError(f"channel '{channel_slug}' not found or inactive")
    if ch.get("premium_only") and not host.get("is_premium"):
        raise ValueError("host_must_be_premium_for_this_channel")

    # One live lobby per host
    existing = await db.lobbies.find_one(
        {"host_user_id": host["user_id"], "status": "live"},
        {"lobby_id": 1, "_id": 0})
    if existing:
        raise ValueError(f"already_hosting:{existing['lobby_id']}")

    lobby_id = f"lob_{uuid.uuid4().hex[:14]}"
    now = _now()
    doc = {
        "_id": lobby_id, "lobby_id": lobby_id,
        "name": name, "description": desc,
        "host_user_id": host["user_id"],
        "host_display_name": host.get("name") or (host.get("email") or "").split("@")[0],
        "host_avatar_color": avatar_color_for(host["user_id"]),
        "channel_slug": channel_slug, "channel_name": ch.get("name"),
        "mood": mood, "activity": activity, "city": city,
        "is_public": bool(is_public), "is_event": False,
        "max_listeners": max_listeners,
        "current_listener_count": 1,  # host counts
        "radio_session_id": None,     # set lazily on first WS connect
        "current_segment_id": None,
        "status": "live",
        "created_at": now, "closed_at": None,
        "skips_used_window": [],      # timestamps for the rolling-hour cap
    }
    await db.lobbies.insert_one(doc)
    # Host joins as host-role member
    await db.lobby_members.insert_one({
        "_id": f"{lobby_id}|{host['user_id']}",
        "lobby_id": lobby_id, "user_id": host["user_id"],
        "role": "host",
        "joined_at": now, "left_at": None,
        "display_name": doc["host_display_name"],
        "avatar_color": doc["host_avatar_color"],
    })
    await log_event(db, lobby_id=lobby_id, event_type="created",
                       actor_user_id=host["user_id"],
                       payload={"channel": channel_slug, "mood": mood,
                                 "max_listeners": max_listeners})
    # Phase 10a — Social Passport: emit `lobby_host_start` for badge engine
    try:
        from services.badge_engine import evaluate as badge_evaluate
        await badge_evaluate(
            db, host["user_id"], "lobby_host_start",
            {"lobby_id": lobby_id, "channel_slug": channel_slug,
              "channel_genre": (ch.get("genre") or "").lower() or None,
              "city": city, "mood": mood})
    except Exception as _e:
        logger.warning(f"badge evaluate lobby_host_start: {_e}")
    return doc


# ----------------------------------------------------------------------
def _today_utc_str() -> str:
    return _now().date().isoformat()


async def check_join_daily_cap(db, user: dict) -> None:
    """Free users can join up to FREE_JOIN_DAILY_CAP lobbies per UTC day.
    Raises ValueError when exceeded."""
    if user.get("is_premium"):
        return
    today = _today_utc_str()
    doc = await db.lobby_joins_daily.find_one(
        {"user_id": user["user_id"], "day": today},
        {"count": 1, "_id": 0},
    )
    if doc and int(doc.get("count") or 0) >= FREE_JOIN_DAILY_CAP:
        raise ValueError("free_daily_join_cap_reached")


async def _bump_daily_join(db, user_id: str) -> None:
    await db.lobby_joins_daily.update_one(
        {"user_id": user_id, "day": _today_utc_str()},
        {"$inc": {"count": 1},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )


async def join_lobby(db, user: dict, lobby_id: str, *,
                       invite_token: Optional[str] = None) -> dict:
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby or lobby.get("status") != "live":
        raise ValueError("lobby_not_live")
    if not lobby.get("is_public") and not invite_token:
        raise ValueError("invite_required")
    if invite_token:
        inv = await db.lobby_invites.find_one({"token": invite_token,
                                                  "lobby_id": lobby_id})
        if not inv: raise ValueError("invalid_invite")
        if inv.get("expires_at") and inv["expires_at"].replace(
                tzinfo=timezone.utc if inv["expires_at"].tzinfo is None
                                          else inv["expires_at"].tzinfo) < _now():
            raise ValueError("invite_expired")
    # Already a member?
    existing = await db.lobby_members.find_one(
        {"_id": f"{lobby_id}|{user['user_id']}"})
    if existing and existing.get("left_at") is None:
        return {"already_member": True, "lobby": lobby,
                "role": existing.get("role")}
    # Daily cap for free users (first join only — re-joining a left lobby
    # within the same day doesn't re-charge the cap)
    if not existing:
        await check_join_daily_cap(db, user)
    # Capacity
    if int(lobby.get("current_listener_count") or 0) >= int(lobby.get("max_listeners") or 0):
        raise ValueError("lobby_full")

    now = _now()
    avatar = avatar_color_for(user["user_id"])
    display = user.get("name") or (user.get("email") or "").split("@")[0]
    if existing:
        await db.lobby_members.update_one(
            {"_id": existing["_id"]},
            {"$set": {"left_at": None, "rejoined_at": now,
                       "display_name": display, "avatar_color": avatar}},
        )
    else:
        await db.lobby_members.insert_one({
            "_id": f"{lobby_id}|{user['user_id']}",
            "lobby_id": lobby_id, "user_id": user["user_id"],
            "role": "listener",
            "joined_at": now, "left_at": None,
            "display_name": display, "avatar_color": avatar,
        })
        await _bump_daily_join(db, user["user_id"])

    await db.lobbies.update_one({"lobby_id": lobby_id},
                                   {"$inc": {"current_listener_count": 1}})
    await log_event(db, lobby_id=lobby_id, event_type="join",
                       actor_user_id=user["user_id"])
    fresh = await db.lobbies.find_one({"lobby_id": lobby_id})
    return {"already_member": False, "lobby": fresh,
            "role": "listener",
            "display_name": display, "avatar_color": avatar}


async def leave_lobby(db, user_id: str, lobby_id: str) -> dict:
    member = await db.lobby_members.find_one(
        {"_id": f"{lobby_id}|{user_id}"})
    if not member or member.get("left_at") is not None:
        return {"already_left": True}
    await db.lobby_members.update_one(
        {"_id": member["_id"]},
        {"$set": {"left_at": _now()}},
    )
    await db.lobbies.update_one(
        {"lobby_id": lobby_id, "current_listener_count": {"$gt": 0}},
        {"$inc": {"current_listener_count": -1}},
    )
    await log_event(db, lobby_id=lobby_id, event_type="leave",
                       actor_user_id=user_id)
    return {"already_left": False}


# ----------------------------------------------------------------------
async def list_public_lobbies(db, *, channel_slug: Optional[str] = None,
                                 mood: Optional[str] = None,
                                 city: Optional[str] = None,
                                 limit: int = 30,
                                 offset: int = 0) -> dict:
    q = {"status": "live", "is_public": True}
    if channel_slug: q["channel_slug"] = channel_slug
    if mood: q["mood"] = mood
    if city: q["city"] = city
    cur = db.lobbies.find(q, {
        "_id": 0, "skips_used_window": 0,
    }).sort("current_listener_count", -1).skip(offset).limit(limit)
    items = []
    async for d in cur:
        items.append(_serialize_lobby(d))
    total = await db.lobbies.count_documents(q)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _serialize_lobby(lobby: dict) -> dict:
    return {
        "lobby_id": lobby["lobby_id"], "name": lobby.get("name"),
        "description": lobby.get("description"),
        "host_user_id": lobby.get("host_user_id"),
        "host_display_name": lobby.get("host_display_name"),
        "host_avatar_color": lobby.get("host_avatar_color"),
        "channel_slug": lobby.get("channel_slug"),
        "channel_name": lobby.get("channel_name"),
        "mood": lobby.get("mood"), "activity": lobby.get("activity"),
        "city": lobby.get("city"),
        "is_public": lobby.get("is_public"),
        "max_listeners": lobby.get("max_listeners"),
        "current_listener_count": lobby.get("current_listener_count"),
        "status": lobby.get("status"),
        "created_at": (lobby["created_at"].isoformat()
                          if lobby.get("created_at") else None),
        "closed_at": (lobby["closed_at"].isoformat()
                        if lobby.get("closed_at") else None),
        "current_segment_id": lobby.get("current_segment_id"),
        "radio_session_id": lobby.get("radio_session_id"),
    }


# ----------------------------------------------------------------------
async def lobby_detail(db, lobby_id: str, *,
                          requesting_user_id: Optional[str] = None) -> dict:
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby: raise ValueError("lobby_not_found")
    cur = db.lobby_members.find(
        {"lobby_id": lobby_id, "left_at": None},
        {"_id": 0, "lobby_id": 0},
    ).limit(20)
    raw_members = []
    async for m in cur:
        raw_members.append(m)
    # ── Phase 10b — public badges + host perks per member ──────────────
    member_uids = [m.get("user_id") for m in raw_members if m.get("user_id")]
    public_badges_by_uid = await _public_badges_for_uids(db, member_uids)
    perks_by_uid = await _host_perks_for_uids(db, member_uids)
    members = []
    for m in raw_members:
        uid = m.get("user_id")
        members.append({
            "user_id": uid, "role": m.get("role"),
            "display_name": m.get("display_name"),
            "avatar_color": m.get("avatar_color"),
            "joined_at": m["joined_at"].isoformat() if m.get("joined_at") else None,
            "public_badges": public_badges_by_uid.get(uid) or [],
            "host_perks": perks_by_uid.get(uid) or [],
        })
    recent_msgs = []
    msg_cur = db.lobby_messages.find(
        {"lobby_id": lobby_id}, {"_id": 0, "lobby_id": 0},
    ).sort("created_at", -1).limit(50)
    async for m in msg_cur:
        recent_msgs.append({
            "message_id": m.get("message_id"),
            "kind": m.get("kind"), "user_id": m.get("user_id"),
            "display_name": m.get("display_name"),
            "text": m.get("text"), "emoji": m.get("emoji"),
            "created_at": m["created_at"].isoformat() if m.get("created_at") else None,
        })
    recent_msgs.reverse()
    out = _serialize_lobby(lobby)
    out["members_preview"] = members
    out["recent_messages"] = recent_msgs
    out["i_am_host"] = (requesting_user_id == lobby.get("host_user_id"))
    return out


# ── Phase 10b helpers ──────────────────────────────────────────────────
_TIER_RANK = {"diamond": 5, "platinum": 4, "gold": 3,
                    "silver": 2, "bronze": 1, "unique": 6}


async def _public_badges_for_uids(db, user_ids: list[str]) -> dict[str, list[dict]]:
    """Top 5 earned badges per user, sorted by tier-rank desc then points
    desc.  Honors `show_badges_publicly` (default True) — users opted-out
    return an empty list."""
    if not user_ids:
        return {}
    out: dict[str, list[dict]] = {}
    # Privacy
    settings = {s["user_id"]: s async for s in
                      db.social_profile_settings.find(
                          {"user_id": {"$in": user_ids}})
                      if s.get("user_id")}
    # Earned awards
    awards = [a async for a in
                  db.user_badges.find({"user_id": {"$in": user_ids}})
                  if a.get("user_id") and a.get("badge_id")]
    bids = list({a["badge_id"] for a in awards})
    cat = {b["_id"]: b async for b in
              db.badges.find({"_id": {"$in": bids},
                                      "schema_version": "10a",
                                      "active": True})}
    grouped: dict[str, list[dict]] = {}
    for a in awards:
        b = cat.get(a["badge_id"])
        if not b:
            continue
        grouped.setdefault(a["user_id"], []).append({
            "badge_id": b.get("badge_id"),
            "name": b.get("name"), "tier": b.get("tier"),
            "category": b.get("category"),
            "points": int(b.get("points") or 0),
            "icon_url": b.get("icon_url"),
        })
    for uid in user_ids:
        st = settings.get(uid) or {}
        if st.get("show_badges_publicly") is False:
            out[uid] = []
            continue
        items = grouped.get(uid) or []
        items.sort(key=lambda x: (-_TIER_RANK.get(x.get("tier") or "", 0),
                                            -x.get("points", 0)))
        out[uid] = items[:5]
    return out


async def _host_perks_for_uids(db, user_ids: list[str]) -> dict[str, list[dict]]:
    """Per-user perk indicators: ✨ annual premium, ★ L4+ Ambassador."""
    if not user_ids:
        return {}
    out: dict[str, list[dict]] = {}
    users = {u["user_id"]: u async for u in
                  db.users.find({"user_id": {"$in": user_ids}},
                                        {"user_id": 1, "is_premium": 1,
                                          "premium_plan_period": 1,
                                          "premium_until": 1})
                  if u.get("user_id")}
    states = {s["user_id"]: s async for s in
                    db.user_ambassador_state.find(
                        {"user_id": {"$in": user_ids}})
                    if s.get("user_id")}
    for uid in user_ids:
        perks: list[dict] = []
        u = users.get(uid) or {}
        if (u.get("is_premium") and
                (u.get("premium_plan_period") or "") == "annual"):
            perks.append({"glyph": "✨", "kind": "premium_annual",
                              "label": "ANNUAL"})
        st = states.get(uid)
        if st and int(st.get("level") or 0) >= 4:
            perks.append({"glyph": "★",
                              "kind": "ambassador_l4_plus",
                              "label": st.get("level_name") or "Ambassador"})
        out[uid] = perks
    return out


# ----------------------------------------------------------------------
# Skip-vote logic
async def cast_skip_vote(db, user_id: str, lobby_id: str) -> dict:
    """Records a skip vote for the lobby's current segment. Returns
    {votes, threshold, triggered}. Caller is responsible for executing
    the skip when triggered=True."""
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby or lobby.get("status") != "live":
        raise ValueError("lobby_not_live")
    seg_id = lobby.get("current_segment_id")
    if not seg_id:
        raise ValueError("no_current_segment")
    # Skip cap — 6 in rolling hour
    now = _now()
    window = lobby.get("skips_used_window") or []
    cutoff = now - timedelta(hours=1)
    fresh_window = [t for t in window
                      if (t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t) > cutoff]
    if len(fresh_window) >= SKIP_CAP_PER_HOUR:
        raise ValueError("skip_cap_reached")
    # Voter dedup
    vote_doc = await db.lobby_skip_votes.find_one_and_update(
        {"_id": f"{lobby_id}|{seg_id}"},
        {"$setOnInsert": {
            "_id": f"{lobby_id}|{seg_id}",
            "lobby_id": lobby_id, "segment_id": seg_id,
            "created_at": now,
        },
         "$addToSet": {"voter_user_ids": user_id}},
        upsert=True, return_document=True,
    )
    votes = len(vote_doc.get("voter_user_ids") or [])
    members = int(lobby.get("current_listener_count") or 1)
    threshold = (members // 2) + 1
    triggered = votes >= threshold
    return {"votes": votes, "members": members,
            "threshold": threshold, "triggered": triggered,
            "segment_id": seg_id}


async def record_skip_executed(db, lobby_id: str) -> None:
    """Append the skip timestamp to the rolling-hour window."""
    await db.lobbies.update_one(
        {"lobby_id": lobby_id},
        {"$push": {"skips_used_window": _now()}},
    )


# ----------------------------------------------------------------------
async def kick_member(db, lobby_id: str, actor_user_id: str,
                         target_user_id: str, reason: Optional[str] = None) -> dict:
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id},
                                          {"host_user_id": 1, "_id": 0})
    if not lobby: raise ValueError("lobby_not_found")
    actor_member = await db.lobby_members.find_one(
        {"_id": f"{lobby_id}|{actor_user_id}"})
    if not actor_member or actor_member.get("role") not in ("host", "moderator"):
        raise ValueError("not_authorized")
    if target_user_id == lobby.get("host_user_id"):
        raise ValueError("cannot_kick_host")
    target = await db.lobby_members.find_one(
        {"_id": f"{lobby_id}|{target_user_id}"})
    if not target or target.get("left_at") is not None:
        return {"already_left": True}
    await db.lobby_members.update_one(
        {"_id": target["_id"]},
        {"$set": {"left_at": _now(), "kick_reason": reason}},
    )
    await db.lobbies.update_one(
        {"lobby_id": lobby_id, "current_listener_count": {"$gt": 0}},
        {"$inc": {"current_listener_count": -1}},
    )
    await log_event(db, lobby_id=lobby_id, event_type="kick",
                       actor_user_id=actor_user_id,
                       payload={"target": target_user_id, "reason": reason})
    return {"kicked": True}


async def close_lobby(db, lobby_id: str, actor_user_id: str) -> dict:
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby: raise ValueError("lobby_not_found")
    if lobby.get("status") == "closed":
        return {"already_closed": True}
    if actor_user_id != lobby.get("host_user_id"):
        raise ValueError("not_authorized")
    now = _now()
    await db.lobbies.update_one(
        {"lobby_id": lobby_id},
        {"$set": {"status": "closed", "closed_at": now}},
    )
    await db.lobby_members.update_many(
        {"lobby_id": lobby_id, "left_at": None},
        {"$set": {"left_at": now}},
    )
    await log_event(db, lobby_id=lobby_id, event_type="closed",
                       actor_user_id=actor_user_id)
    return {"closed": True}


# ----------------------------------------------------------------------
async def change_channel(db, lobby_id: str, actor_user_id: str,
                            new_channel_slug: str) -> dict:
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby: raise ValueError("lobby_not_found")
    if actor_user_id != lobby.get("host_user_id"):
        raise ValueError("not_authorized")
    ch = await db.channels.find_one({"_id": new_channel_slug, "active": True})
    if not ch: raise ValueError("channel_not_found")
    if ch.get("premium_only"):
        host = await db.users.find_one({"user_id": actor_user_id},
                                           {"is_premium": 1, "_id": 0})
        if not (host or {}).get("is_premium"):
            raise ValueError("host_must_be_premium_for_this_channel")
    await db.lobbies.update_one(
        {"lobby_id": lobby_id},
        {"$set": {"channel_slug": new_channel_slug,
                   "channel_name": ch.get("name")}},
    )
    await log_event(db, lobby_id=lobby_id, event_type="channel_changed",
                       actor_user_id=actor_user_id,
                       payload={"new_channel": new_channel_slug})
    return {"channel_slug": new_channel_slug, "channel_name": ch.get("name")}


# ----------------------------------------------------------------------
async def issue_invite(db, lobby_id: str, actor_user_id: str) -> dict:
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id},
                                          {"host_user_id": 1, "_id": 0})
    if not lobby: raise ValueError("lobby_not_found")
    if actor_user_id != lobby.get("host_user_id"):
        raise ValueError("not_authorized")
    token = "li_" + secrets.token_urlsafe(20)
    now = _now()
    await db.lobby_invites.insert_one({
        "_id": token, "token": token, "lobby_id": lobby_id,
        "created_by": actor_user_id, "created_at": now,
        "expires_at": now + timedelta(hours=INVITE_TTL_HOURS),
    })
    return {"token": token,
            "expires_at": (now + timedelta(hours=INVITE_TTL_HOURS)).isoformat()}


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
async def transfer_host(db, lobby_id: str, actor_user_id: str,
                            target_user_id: str) -> dict:
    """Host hands over the host role to another active member. The previous
    host downgrades to a 'listener' role; the new host inherits host
    privileges (kick/close/announce_segment)."""
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby: raise ValueError("lobby_not_found")
    if actor_user_id != lobby.get("host_user_id"):
        raise ValueError("not_authorized")
    if target_user_id == actor_user_id:
        return {"already_host": True}
    target = await db.lobby_members.find_one(
        {"_id": f"{lobby_id}|{target_user_id}", "left_at": None})
    if not target:
        raise ValueError("target_not_a_member")
    target_user = await db.users.find_one({"user_id": target_user_id},
                                              {"is_premium": 1, "name": 1, "_id": 0})
    # If host moves to a non-premium user, the lobby is implicitly capped
    # at FREE_HOST_MAX_LISTENERS — keep the existing higher cap (don't shrink
    # below current_listener_count) so nobody is kicked accidentally.
    new_max = lobby.get("max_listeners")
    new_host_premium = bool((target_user or {}).get("is_premium"))
    if not new_host_premium:
        new_max = max(int(lobby.get("current_listener_count") or 0),
                        min(int(new_max or FREE_HOST_MAX_LISTENERS),
                              FREE_HOST_MAX_LISTENERS))
    now = _now()
    await db.lobby_members.update_one(
        {"_id": f"{lobby_id}|{actor_user_id}"},
        {"$set": {"role": "listener", "demoted_at": now}},
    )
    await db.lobby_members.update_one(
        {"_id": f"{lobby_id}|{target_user_id}"},
        {"$set": {"role": "host", "promoted_at": now}},
    )
    new_display = target.get("display_name") or (target_user or {}).get("name") or "host"
    await db.lobbies.update_one(
        {"lobby_id": lobby_id},
        {"$set": {
            "host_user_id": target_user_id,
            "host_display_name": new_display,
            "host_avatar_color": target.get("avatar_color") or avatar_color_for(target_user_id),
            "max_listeners": new_max,
        }},
    )
    await log_event(db, lobby_id=lobby_id, event_type="host_transferred",
                       actor_user_id=actor_user_id,
                       payload={"new_host": target_user_id})
    return {"new_host_user_id": target_user_id,
            "new_host_display_name": new_display,
            "max_listeners": new_max}


async def append_chat_message(db, lobby_id: str, user: dict, text: str) -> dict:
    text = (text or "").strip()
    if not text: raise ValueError("empty_text")
    if len(text) > CHAT_MAX_LEN: raise ValueError("text_too_long")
    member = await db.lobby_members.find_one(
        {"_id": f"{lobby_id}|{user['user_id']}", "left_at": None},
        {"display_name": 1, "_id": 0})
    if not member: raise ValueError("not_a_member")
    msg_id = f"msg_{uuid.uuid4().hex[:14]}"
    now = _now()
    doc = {
        "_id": msg_id, "message_id": msg_id, "lobby_id": lobby_id,
        "user_id": user["user_id"],
        "display_name": member.get("display_name"),
        "avatar_color": avatar_color_for(user["user_id"]),
        "kind": "chat", "text": text,
        "created_at": now,
    }
    await db.lobby_messages.insert_one(doc)
    return {
        "message_id": msg_id, "user_id": user["user_id"],
        "display_name": member.get("display_name"),
        "avatar_color": avatar_color_for(user["user_id"]),
        "text": text, "created_at": now.isoformat(),
    }
