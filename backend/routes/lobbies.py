"""Phase 7 — Social Lobbies: REST + WebSocket endpoints.

Endpoints (all mounted under /api/lobbies):
  GET    /list                         → list active public lobbies (filterable)
  POST   /create                       → host creates a lobby
  GET    /{lobby_id}                   → lobby snapshot (members + recent msgs)
  POST   /{lobby_id}/join              → join (consumes daily quota for free)
  POST   /{lobby_id}/leave             → leave
  POST   /{lobby_id}/skip_vote         → cast majority skip-vote
  POST   /{lobby_id}/kick              → host kicks a listener
  POST   /{lobby_id}/close             → host ends the lobby
  POST   /{lobby_id}/invite            → host issues an invite token
  POST   /{lobby_id}/transfer_host     → host hands over host role
  POST   /{lobby_id}/change_channel    → host swaps channel mid-stream
  POST   /{lobby_id}/announce_segment  → host pushes the new segment metadata
                                          (also broadcast over WS)

WS:
  WS /api/lobbies/ws/{lobby_id}        → main socket. Auth via the bigfm_session
                                          cookie (or ?session=<token> query for
                                          environments where cookies are tricky).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Request, WebSocket,
    WebSocketDisconnect, status,
)

from auth import SESSION_COOKIE, current_user
from services.lobbies import (
    EMOJI_WHITELIST, FREE_HOST_MAX_LISTENERS, PREMIUM_HOST_MAX_LISTENERS,
    append_chat_message, avatar_color_for, cast_skip_vote, change_channel,
    close_lobby, create_lobby, ensure_lobby_indexes, issue_invite,
    join_lobby, kick_member, leave_lobby, list_public_lobbies, lobby_detail,
    log_event, record_skip_executed, transfer_host,
)
from services.lobby_hub import TokenBucket

logger = logging.getLogger("bigfm.lobbies.routes")

lobbies_router = APIRouter(prefix="/api/lobbies", tags=["lobbies"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# WebSocket auth — resolves the user from any of:
#   • the `bigfm_session` cookie (browsers — primary)
#   • `?token=<opaque>` (mobile — matches the Bearer string from
#     POST /api/auth/login)
#   • `?session=<opaque>` (legacy alias kept for backwards-compat)
# All three paths validate against the same `sessions` collection that
# `auth.py:_resolve_user_from_request` uses; same TTL semantics.
async def _resolve_ws_user(websocket: WebSocket) -> Optional[dict]:
    token = websocket.cookies.get(SESSION_COOKIE)
    if not token:
        token = (websocket.query_params.get("token")
                    or websocket.query_params.get("session"))
    if not token:
        return None
    db = websocket.app.state.db
    sess = await db.sessions.find_one({"token": token}, {"_id": 0})
    if not sess:
        return None
    exp = sess.get("expires_at")
    if exp and getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < _now():
        return None
    return await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})


# ----------------------------------------------------------------------
# REST
@lobbies_router.get("/list")
async def list_lobbies(request: Request,
                          channel: Optional[str] = Query(None),
                          mood: Optional[str] = Query(None),
                          city: Optional[str] = Query(None),
                          limit: int = Query(30, ge=1, le=100),
                          offset: int = Query(0, ge=0)):
    db = request.app.state.db
    return await list_public_lobbies(db, channel_slug=channel, mood=mood,
                                          city=city, limit=limit, offset=offset)


@lobbies_router.post("/create")
async def post_create_lobby(payload: dict, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    # Phase 12c — lobby_spam abuse heuristic
    from services.abuse import check_lobby_spam
    spam = await check_lobby_spam(db, user_id=user["user_id"])
    if spam:
        raise HTTPException(
            status_code=429,
            detail={"code": "abuse_blocked",
                      "reason": "lobby_spam",
                      "abuse_id": spam.get("abuse_id")})
    channel_slug = (payload or {}).get("channel_slug") or ""
    # Phase 10c.2 — channel exclusivity gate.  Reuse the same helper that
    # `/api/radio/start` uses so the gating UX is identical.  Lookup
    # happens here (not inside create_lobby) because we need to return a
    # 403 with the structured `access` detail body, not a 400.
    if channel_slug:
        ch = await db.channels.find_one({"_id": channel_slug,
                                                    "active": True})
        if ch:
            from services.channel_access import (
                check_channel_access, access_to_403_detail)
            access = await check_channel_access(db, user, ch)
            if not access.get("allowed"):
                raise HTTPException(
                    status_code=403,
                    detail=access_to_403_detail(access, ch))
    try:
        lobby = await create_lobby(
            db, user,
            name=(payload or {}).get("name") or "",
            channel_slug=channel_slug,
            mood=(payload or {}).get("mood"),
            activity=(payload or {}).get("activity"),
            description=(payload or {}).get("description"),
            city=(payload or {}).get("city") or (user.get("preference_vector") or {}).get("city"),
            is_public=bool((payload or {}).get("is_public", True)),
            max_listeners=(payload or {}).get("max_listeners"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "ok": True,
        "lobby_id": lobby["lobby_id"],
        "name": lobby["name"],
        "channel_slug": lobby["channel_slug"],
        "channel_name": lobby.get("channel_name"),
        "max_listeners": lobby["max_listeners"],
        "is_public": lobby["is_public"],
        "host_user_id": lobby["host_user_id"],
        "created_at": lobby["created_at"].isoformat(),
    }


@lobbies_router.get("/host_caps")
async def get_host_caps(user: dict = Depends(current_user)):
    return {
        "is_premium": bool(user.get("is_premium")),
        "free_host_max_listeners": FREE_HOST_MAX_LISTENERS,
        "premium_host_max_listeners": PREMIUM_HOST_MAX_LISTENERS,
        "max_listeners": (PREMIUM_HOST_MAX_LISTENERS if user.get("is_premium")
                              else FREE_HOST_MAX_LISTENERS),
        "free_join_daily_cap": 3,
    }


@lobbies_router.get("/{lobby_id}")
async def get_lobby(lobby_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await lobby_detail(db, lobby_id, requesting_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(404, str(e))


@lobbies_router.post("/{lobby_id}/join")
async def post_join(lobby_id: str, request: Request,
                     payload: Optional[dict] = None,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    invite_token = (payload or {}).get("invite_token") if isinstance(payload, dict) else None
    try:
        out = await join_lobby(db, user, lobby_id, invite_token=invite_token)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Phase 8b — milestone unlock on lobby join
    try:
        from services.game_unlock_engine import on_lobby_join
        await on_lobby_join(db, user["user_id"], lobby_id)
    except Exception:
        pass
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub and not out.get("already_member"):
        await hub.broadcast(lobby_id, {
            "type": "presence_update",
            "action": "join",
            "user": {
                "user_id": user["user_id"],
                "display_name": out.get("display_name"),
                "avatar_color": out.get("avatar_color"),
                "role": out.get("role"),
            },
            "current_listener_count": out["lobby"].get("current_listener_count"),
        })
    return {
        "ok": True,
        "lobby_id": lobby_id,
        "already_member": out.get("already_member", False),
        "role": out.get("role", "listener"),
        "display_name": out.get("display_name"),
        "avatar_color": out.get("avatar_color") or avatar_color_for(user["user_id"]),
        "current_listener_count": out["lobby"].get("current_listener_count"),
    }


@lobbies_router.post("/{lobby_id}/leave")
async def post_leave(lobby_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    out = await leave_lobby(db, user["user_id"], lobby_id)
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub and not out.get("already_left"):
        lobby = await db.lobbies.find_one({"lobby_id": lobby_id},
                                              {"current_listener_count": 1, "_id": 0})
        await hub.broadcast(lobby_id, {
            "type": "presence_update",
            "action": "leave",
            "user": {"user_id": user["user_id"]},
            "current_listener_count": (lobby or {}).get("current_listener_count", 0),
        })
    return {"ok": True}


@lobbies_router.post("/{lobby_id}/skip_vote")
async def post_skip_vote(lobby_id: str, request: Request,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        out = await cast_skip_vote(db, user["user_id"], lobby_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub:
        await hub.broadcast(lobby_id, {
            "type": "skip_vote_update",
            "votes": out["votes"], "threshold": out["threshold"],
            "members": out["members"], "triggered": out["triggered"],
            "segment_id": out["segment_id"],
        })
        if out["triggered"]:
            lobby = await db.lobbies.find_one({"lobby_id": lobby_id},
                                                 {"host_user_id": 1, "_id": 0})
            host_id = (lobby or {}).get("host_user_id")
            if host_id:
                await hub.send_to_user(lobby_id, host_id, {
                    "type": "host_skip_now",
                    "segment_id": out["segment_id"],
                })
            await record_skip_executed(db, lobby_id)
            await log_event(db, lobby_id=lobby_id, event_type="skip_triggered",
                              actor_user_id=user["user_id"],
                              payload={"votes": out["votes"],
                                        "members": out["members"]})
    return out


@lobbies_router.post("/{lobby_id}/kick")
async def post_kick(lobby_id: str, payload: dict, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    target = (payload or {}).get("user_id") or ""
    reason = (payload or {}).get("reason")
    if not target:
        raise HTTPException(400, "user_id required")
    try:
        out = await kick_member(db, lobby_id, user["user_id"], target, reason)
    except ValueError as e:
        raise HTTPException(403 if str(e) == "not_authorized" else 400, str(e))
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub and out.get("kicked"):
        await hub.send_to_user(lobby_id, target, {
            "type": "kicked", "reason": reason or "by_host",
        })
        await hub.broadcast(lobby_id, {
            "type": "presence_update", "action": "kicked",
            "user": {"user_id": target},
            "current_listener_count": (await db.lobbies.find_one(
                {"lobby_id": lobby_id}, {"current_listener_count": 1, "_id": 0}
            ) or {}).get("current_listener_count", 0),
        })
        # Close the victim's socket if still open
        sock = hub.user_socket(lobby_id, target)
        if sock:
            try: await sock.close(code=4003)
            except Exception: pass
    return {"ok": True, **out}


@lobbies_router.post("/{lobby_id}/close")
async def post_close(lobby_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        out = await close_lobby(db, lobby_id, user["user_id"])
    except ValueError as e:
        raise HTTPException(403 if str(e) == "not_authorized" else 400, str(e))
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub and out.get("closed"):
        await hub.broadcast(lobby_id, {"type": "lobby_closed"})
        # Drop all sockets shortly after
        await asyncio.sleep(0.2)
        sockets = list(hub._conns.get(lobby_id, set()))
        for s in sockets:
            try: await s.close(code=4002)
            except Exception: pass
    return {"ok": True, **out}


@lobbies_router.post("/{lobby_id}/invite")
async def post_invite(lobby_id: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        out = await issue_invite(db, lobby_id, user["user_id"])
    except ValueError as e:
        raise HTTPException(403 if str(e) == "not_authorized" else 400, str(e))
    return {"ok": True, **out}


@lobbies_router.post("/{lobby_id}/transfer_host")
async def post_transfer_host(lobby_id: str, payload: dict, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    target = (payload or {}).get("user_id") or ""
    if not target:
        raise HTTPException(400, "user_id required")
    try:
        out = await transfer_host(db, lobby_id, user["user_id"], target)
    except ValueError as e:
        code = {"not_authorized": 403,
                "target_not_a_member": 400,
                "target_not_premium": 400,
                "lobby_not_found": 404}.get(str(e), 400)
        raise HTTPException(code, str(e))
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub:
        await hub.broadcast(lobby_id, {
            "type": "host_changed",
            "new_host_user_id": target,
            "new_host_display_name": out.get("new_host_display_name"),
        })
    return {"ok": True, **out}


@lobbies_router.post("/{lobby_id}/change_channel")
async def post_change_channel(lobby_id: str, payload: dict, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    new_slug = (payload or {}).get("channel_slug") or ""
    if not new_slug:
        raise HTTPException(400, "channel_slug required")
    try:
        out = await change_channel(db, lobby_id, user["user_id"], new_slug)
    except ValueError as e:
        code = 403 if str(e) == "not_authorized" else 400
        raise HTTPException(code, str(e))
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub:
        await hub.broadcast(lobby_id, {"type": "channel_changed", **out})
    return {"ok": True, **out}


@lobbies_router.post("/{lobby_id}/announce_segment")
async def post_announce_segment(lobby_id: str, payload: dict, request: Request,
                                    user: dict = Depends(current_user)):
    """Host's frontend calls this each time their `<audio>` swaps in a fresh
    segment. We persist `current_segment_id` + broadcast `segment_changed`
    so every listener can sync."""
    db = request.app.state.db
    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby:
        raise HTTPException(404, "lobby_not_found")
    if user["user_id"] != lobby.get("host_user_id"):
        raise HTTPException(403, "not_authorized")
    if lobby.get("status") != "live":
        raise HTTPException(400, "lobby_not_live")
    seg = payload or {}
    started_at = _now()
    started_at_iso = started_at.isoformat()
    update = {
        "current_segment_id": seg.get("segment_id"),
        "current_segment_url": seg.get("segment_url"),
        "current_segment_duration_sec": seg.get("duration_sec"),
        "current_segment_started_at": started_at,
        "current_segment_metadata": {
            "track_title": seg.get("track_title"),
            "track_artist": seg.get("track_artist"),
            "rj_voice_name": seg.get("rj_voice_name"),
            "rj_start_sec": seg.get("rj_start_sec"),
            "rj_script": seg.get("rj_script"),
            "channel_slug": seg.get("channel_slug"),
            "channel_name": seg.get("channel_name"),
        },
    }
    await db.lobbies.update_one({"lobby_id": lobby_id}, {"$set": update})
    # New segment → wipe stale skip vote
    await db.lobby_skip_votes.delete_many({"lobby_id": lobby_id})
    hub = getattr(request.app.state, "lobby_hub", None)
    if hub:
        await hub.broadcast(lobby_id, {
            "type": "segment_changed",
            "segment_id": seg.get("segment_id"),
            "segment_url": seg.get("segment_url"),
            "duration_sec": seg.get("duration_sec"),
            "started_at": started_at_iso,
            "track_title": seg.get("track_title"),
            "track_artist": seg.get("track_artist"),
            "rj_voice_name": seg.get("rj_voice_name"),
            "rj_start_sec": seg.get("rj_start_sec"),
            "rj_script": seg.get("rj_script"),
            "channel_slug": seg.get("channel_slug"),
            "channel_name": seg.get("channel_name"),
        })
    return {"ok": True, "started_at": started_at_iso}


# ----------------------------------------------------------------------
# WebSocket
@lobbies_router.websocket("/ws/{lobby_id}")
async def lobby_ws(websocket: WebSocket, lobby_id: str):
    await websocket.accept()
    user = await _resolve_ws_user(websocket)
    if not user:
        await websocket.send_text(json.dumps({"type": "error", "code": "unauthorized"}))
        await websocket.close(code=4401)
        return
    db = websocket.app.state.db
    hub = websocket.app.state.lobby_hub

    # Must be a current member
    member = await db.lobby_members.find_one(
        {"_id": f"{lobby_id}|{user['user_id']}", "left_at": None})
    if not member:
        await websocket.send_text(json.dumps({"type": "error",
                                                  "code": "not_a_member"}))
        await websocket.close(code=4403)
        return

    lobby = await db.lobbies.find_one({"lobby_id": lobby_id})
    if not lobby or lobby.get("status") != "live":
        await websocket.send_text(json.dumps({"type": "error",
                                                  "code": "lobby_not_live"}))
        await websocket.close(code=4404)
        return

    await hub.register(lobby_id, user["user_id"], websocket)
    chat_bucket = TokenBucket(capacity=5, refill_per_sec=1.0)        # ~5 msgs burst, 1/s sustained
    reaction_bucket = TokenBucket(capacity=10, refill_per_sec=3.0)   # 3/s reactions

    # Send hello snapshot
    try:
        snap = await lobby_detail(db, lobby_id, requesting_user_id=user["user_id"])
    except Exception:
        snap = None
    # Current segment sync — include started_at so listener seeks correctly
    seg_started_at = lobby.get("current_segment_started_at")
    seg_meta = lobby.get("current_segment_metadata") or {}
    hello = {
        "type": "hello",
        "you": {
            "user_id": user["user_id"],
            "role": member.get("role"),
            "display_name": member.get("display_name"),
            "avatar_color": member.get("avatar_color"),
            "is_premium": bool(user.get("is_premium")),
        },
        "lobby": snap,
        "current_segment": {
            "segment_id": lobby.get("current_segment_id"),
            "segment_url": lobby.get("current_segment_url"),
            "duration_sec": lobby.get("current_segment_duration_sec"),
            "started_at": (seg_started_at.isoformat()
                            if isinstance(seg_started_at, datetime) else None),
            **seg_meta,
        } if lobby.get("current_segment_id") else None,
    }
    await websocket.send_text(json.dumps(hello, default=str))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error",
                                                          "code": "bad_json"}))
                continue
            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
            if mtype == "chat":
                if not chat_bucket.take():
                    await websocket.send_text(json.dumps({"type": "error",
                                                              "code": "rate_limited"}))
                    continue
                # Phase 12c — moderate chat (fail-closed: any error
                # blocks the message and logs loudly)
                text_in = msg.get("text") or ""
                try:
                    from services.moderation import moderate, CHAT_REF
                    verdict = await moderate(
                        db, text=text_in, user_id=user["user_id"],
                        ref_type=CHAT_REF, ref_id=lobby_id)
                except Exception as me:
                    logger.error(
                        f"chat moderation HARD-FAIL (fail-closed); "
                        f"blocking message. user={user['user_id']} "
                        f"lobby={lobby_id}: {me}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "moderation_unavailable",
                        "reason": "moderation_error_blocked"}))
                    continue
                if verdict["verdict"] == "block":
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "blocked_by_moderation",
                        "reason": verdict["reason"]}))
                    continue
                try:
                    saved = await append_chat_message(
                        db, lobby_id, user, text_in)
                except ValueError as e:
                    await websocket.send_text(json.dumps({"type": "error",
                                                              "code": str(e)}))
                    continue
                await hub.broadcast(lobby_id, {
                    "type": "chat_message",
                    "message_id": saved["message_id"],
                    "user_id": user["user_id"],
                    "display_name": saved["display_name"],
                    "avatar_color": saved["avatar_color"],
                    "text": saved["text"],
                    "created_at": saved["created_at"],
                })
                continue
            if mtype == "reaction":
                if not reaction_bucket.take():
                    continue   # silently drop excess reactions
                emoji = (msg.get("emoji") or "").strip()
                if emoji not in EMOJI_WHITELIST:
                    await websocket.send_text(json.dumps({"type": "error",
                                                              "code": "emoji_not_allowed"}))
                    continue
                await hub.broadcast(lobby_id, {
                    "type": "reaction",
                    "user_id": user["user_id"],
                    "display_name": member.get("display_name"),
                    "avatar_color": member.get("avatar_color"),
                    "emoji": emoji,
                    "ts": _now().isoformat(),
                })
                continue
            if mtype == "request_resync":
                # Re-send current segment to this socket only
                lob = await db.lobbies.find_one({"lobby_id": lobby_id})
                if lob and lob.get("current_segment_id"):
                    sa = lob.get("current_segment_started_at")
                    sm = lob.get("current_segment_metadata") or {}
                    await websocket.send_text(json.dumps({
                        "type": "segment_changed",
                        "segment_id": lob.get("current_segment_id"),
                        "segment_url": lob.get("current_segment_url"),
                        "duration_sec": lob.get("current_segment_duration_sec"),
                        "started_at": (sa.isoformat()
                                        if isinstance(sa, datetime) else None),
                        **sm,
                    }, default=str))
                continue
            await websocket.send_text(json.dumps({"type": "error",
                                                      "code": "unknown_type",
                                                      "got": mtype}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[lobby-ws] {lobby_id} user={user['user_id']} error: {e}")
    finally:
        await hub.unregister(lobby_id, user["user_id"], websocket)
        # Best-effort presence broadcast
        try:
            await hub.broadcast(lobby_id, {
                "type": "presence_update",
                "action": "ws_disconnect",
                "user": {"user_id": user["user_id"]},
                "current_listener_count": (await db.lobbies.find_one(
                    {"lobby_id": lobby_id},
                    {"current_listener_count": 1, "_id": 0}
                ) or {}).get("current_listener_count"),
            })
        except Exception:
            pass


__all__ = ["lobbies_router", "ensure_lobby_indexes"]
