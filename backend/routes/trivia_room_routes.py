"""
Phase 16b — Multiplayer trivia room routes.

REST:
    POST   /api/trivia/rooms                              create + auto-join host
    POST   /api/trivia/rooms/{code}/join                  join an existing room
    GET    /api/trivia/rooms/{code}                       public room snapshot
    DELETE /api/trivia/rooms/{code}/players/{user_id}    host-only kick
    POST   /api/trivia/rooms/{code}/start                 host-only start

WebSocket:
    /api/trivia/ws/{code}?token=<session>

Message contract (see trivia_rooms.py for the state machine):
    C→S: {type: "answer", question_id, choice_id}
    C→S: {type: "ping"}
    C→S: {type: "leave"}
    S→C: {type: "hello", server_now, room: <public_room>}
    S→C: {type: "player_joined" | "player_left", ...}
    S→C: {type: "phase_change", phase, deadline_ms, question?, leaderboard?, final_scores?}
    S→C: {type: "answer_received", user_id}
    S→C: {type: "error", code, message}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Request, WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from services.market_context import get_user_market
from services.trivia_ai import pick_for_user
from services.trivia_rooms import (
    Room, RoomHub, PlayerState, FIRST_CORRECT_BONUSES,
    QUESTION_DURATION_SEC, REVEAL_DURATION_SEC, LEADERBOARD_DURATION_SEC,
)
from services import bigcoin
from auth import SESSION_COOKIE
import uuid

logger = logging.getLogger("bigfm.trivia.room_routes")

# Multiplayer-finish BC multipliers (extends 16a).
BIGCOIN_DIVISOR = 10
RANK_MULTIPLIERS = {1: 1.20, 2: 1.10, 3: 1.05}


class CreateRoomReq(BaseModel):
    category_id: str
    is_private:  bool = False
    max_players: int = Field(default=20, ge=2, le=50)
    # Phase H — AD.5 optional sponsorship binding.
    sponsorship_id: Optional[str] = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def normalize_room_code(raw: str) -> str:
    """Accept any of `BFM-XJG979`, `bfm-xjg979`, `BFMXJG979`, `xjg979`,
    `  bfm xjg-979  ` → canonical `BFM-XJG979`.

    Trim → upper → strip whitespace + non-[A-Z0-9-] noise → drop any
    leading `BFM-?` prefix → re-attach the canonical `BFM-` prefix to
    the 6-char body.  Returns the raw input upper-cased if it doesn't
    look like a room code so the 404 path still reports it cleanly."""
    s = (raw or "").strip().upper()
    # Strip whitespace inside the code (handle accidental spaces) +
    # anything that isn't part of our alphabet.
    s = "".join(ch for ch in s if ch.isalnum() or ch == "-")
    # Drop the prefix in any form (BFM-, BFM) so we re-add cleanly.
    if s.startswith("BFM-"):
        body = s[4:]
    elif s.startswith("BFM"):
        body = s[3:]
    else:
        body = s
    # Strip any leftover hyphens inside the body — only the prefix hyphen survives.
    body = body.replace("-", "")
    if not body:
        return s
    return f"BFM-{body}"


def _score_for(correct: bool, latency_ms: int) -> int:
    if not correct:
        return 0
    pts = 100
    if latency_ms < 3000:
        pts += 50
    elif latency_ms < 6000:
        pts += 25
    return pts


async def notify_room_followers(db, room, host_user: dict,
                                venue_name: Optional[str] = None) -> int:
    """Send Expo push notifications about a new trivia room to users in the
    same market who have active push tokens.  Proxy for 'followers' until a
    follower / venue-favorite model exists."""
    canon = room.code
    market = getattr(room, "market", "global") or "global"
    host_name = host_user.get("name") or "Someone"
    title_source = venue_name or host_name
    push_title = f"Trivia starting at {title_source}"
    push_body = f"Tap to join room {canon}"
    deep_link = f"/trivia/rooms/{canon}"

    target_uids: set[str] = set()
    async for tok in db.user_push_tokens.find(
        {"active": True}, {"user_id": 1}
    ).limit(200):
        uid = tok.get("user_id")
        if uid and uid != room.host_user_id:
            target_uids.add(uid)

    if not target_uids:
        return 0

    market_users: list[dict] = []
    async for u in db.users.find(
        {"user_id": {"$in": list(target_uids)}, "market": market},
        {"user_id": 1, "name": 1, "email": 1},
    ).limit(50):
        market_users.append(u)

    sent = 0
    from services.delivery import send_push as delivery_send
    for target in market_users:
        try:
            await delivery_send(
                db, user=target, campaign_id=f"trivia_room_{canon}",
                title=push_title, body_template=push_body,
                deep_link=deep_link,
            )
            sent += 1
        except Exception as e:
            logger.warning("trivia push user=%s: %s", target.get("user_id"), e)
    return sent


def build_router(db, get_current_user) -> APIRouter:
    router = APIRouter(prefix="/api/trivia", tags=["trivia-rooms"])

    # ─── Auth on the WS (mirrors lobbies.py `_resolve_ws_user`) ────────
    async def _resolve_ws_user(websocket: WebSocket) -> Optional[dict]:
        token = websocket.cookies.get(SESSION_COOKIE)
        if not token:
            token = (websocket.query_params.get("token")
                        or websocket.query_params.get("session"))
        if not token:
            return None
        sess = await db.sessions.find_one({"token": token}, {"_id": 0})
        if not sess:
            return None
        exp = sess.get("expires_at")
        if exp and getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp < datetime.now(timezone.utc):
            return None
        return await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})

    # ───────── REST: create ─────────────────────────────────────────────
    @router.post("/rooms")
    async def create_room(req: CreateRoomReq, request: Request,
                              user: dict = Depends(get_current_user)):
        market = await get_user_market(request, user, db)
        cat = await db.trivia_categories.find_one({"id": req.category_id, "active": True})
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        # Phase H — resolve + validate sponsorship if provided.  The
        # service raises ValueError on any binding mismatch (wrong
        # category, expired, cancelled, not active).
        sponsorship_meta = None
        if req.sponsorship_id:
            try:
                from services.trivia_sponsorship_service import (
                    resolve_and_validate_sponsorship)
                sponsorship_meta = await resolve_and_validate_sponsorship(
                    db, sponsorship_id=req.sponsorship_id,
                    category_id=req.category_id)
            except ValueError as e:
                raise HTTPException(status_code=400,
                                                          detail={"code": str(e)})
        hub: RoomHub = request.app.state.trivia_room_hub
        room = await hub.create(
            host_user={
                "user_id": user["user_id"],
                "name":     user.get("name") or "Host",
                "avatar":   user.get("avatar_url"),
            },
            category_id=req.category_id,
            category_slug=cat["slug"],
            market=market,
            is_private=req.is_private,
            max_players=req.max_players,
            sponsorship=sponsorship_meta,
        )
        host = request.url.scheme + "://" + (request.headers.get("host") or "")
        invite_url = f"{host}/trivia/join?code={room.code}"
        # Auto-notify followers for public rooms (fire-and-forget)
        if not req.is_private:
            asyncio.create_task(notify_room_followers(db, room, user))
        return {
            "room_code": room.code,
            "invite_url": invite_url,
            "room":       room.to_public(),
        }

    # ───────── REST: join ───────────────────────────────────────────────
    @router.post("/rooms/{code}/join")
    async def join_room(code: str, request: Request,
                          user: dict = Depends(get_current_user)):
        hub: RoomHub = request.app.state.trivia_room_hub
        canon = normalize_room_code(code)
        try:
            room = await hub.add_player(canon, {
                "user_id": user["user_id"],
                "name":     user.get("name") or "Player",
                "avatar":   user.get("avatar_url"),
            })
        except KeyError:
            raise HTTPException(status_code=404, detail={
                "code": "room_not_found",
                "message": f"No room with code {canon} — double-check the code or ask the host.",
                "code_typed": code,
                "code_normalized": canon,
            })
        except PermissionError as e:
            if str(e) == "room_in_progress":
                raise HTTPException(status_code=409,
                                            detail={"code": "room_in_progress",
                                                      "message": "Room is mid-game; wait for next round."})
            raise HTTPException(status_code=409,
                                        detail={"code": str(e), "message": str(e)})
        # Broadcast.
        await hub.broadcast(canon, {
            "type": "player_joined",
            "user": {"id": user["user_id"], "name": user.get("name"),
                       "avatar": user.get("avatar_url")},
        })
        return {"room": room.to_public(), "your_player_id": user["user_id"]}

    # ───────── REST: snapshot ───────────────────────────────────────────
    @router.get("/rooms/{code}")
    async def get_room(code: str, request: Request,
                          user: dict = Depends(get_current_user)):
        hub: RoomHub = request.app.state.trivia_room_hub
        canon = normalize_room_code(code)
        room = hub.get(canon)
        if not room:
            raise HTTPException(status_code=404, detail={
                "code": "room_not_found",
                "message": f"No room with code {canon}.",
                "code_typed": code,
                "code_normalized": canon,
            })
        return {"room": room.to_public()}

    # ───────── REST: kick ───────────────────────────────────────────────
    @router.delete("/rooms/{code}/players/{user_id}")
    async def kick_player(code: str, user_id: str, request: Request,
                              user: dict = Depends(get_current_user)):
        hub: RoomHub = request.app.state.trivia_room_hub
        canon = normalize_room_code(code)
        room = hub.get(canon)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if room.host_user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="Host only")
        # `hub.kick` does the targeted-notify + WS close (4001) + remove
        # + broadcast `player_left`.  Returns False for an idempotent
        # kick on a non-member (test_host_can_kick_player covers this).
        await hub.kick(canon, user_id)
        return {"ok": True}

    # ───────── REST: start ──────────────────────────────────────────────
    @router.post("/rooms/{code}/start")
    async def start_room(code: str, request: Request,
                            user: dict = Depends(get_current_user)):
        hub: RoomHub = request.app.state.trivia_room_hub
        canon = normalize_room_code(code)
        room = hub.get(canon)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if room.host_user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="Host only")
        if room.phase != "lobby":
            raise HTTPException(status_code=409, detail="Room already started")
        # Multiplayer rooms need at least 2 humans — practice solo lives
        # at /trivia/play (Phase 16a).
        MIN_PLAYERS = 2
        if len(room.players) < MIN_PLAYERS:
            raise HTTPException(status_code=400, detail={
                "code":     "need_more_players",
                "message":  f"Need at least {MIN_PLAYERS} players to start.  Share the code or play solo at /trivia/play.",
                "current":  len(room.players),
                "required": MIN_PLAYERS,
            })
        # Generate the 10 questions for this room.
        qs = await pick_for_user(
            db, room.host_user_id, room.market, room.category_slug,
            count=10, difficulty=2,
        )
        if len(qs) < 1:
            raise HTTPException(status_code=503, detail="Trivia bank empty")
        room.questions = qs
        # Kick off the state-machine driver.
        room.advance_task = asyncio.create_task(_run_room(db, hub, room))
        return {"ok": True}

    # ───────── REST: notify followers ────────────────────────────────────
    @router.post("/rooms/{code}/notify_followers")
    async def notify_followers_endpoint(code: str, request: Request,
                                        user: dict = Depends(get_current_user)):
        """Send Expo push to users in the same market about this room.
        Automatically called from room creation (public) and venue trivia start.
        Also callable manually by the host."""
        hub: RoomHub = request.app.state.trivia_room_hub
        canon = normalize_room_code(code)
        room = hub.get(canon)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if room.host_user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="Host only")

        venue_name = None
        venue_id = getattr(room, "venue_id", None)
        if venue_id:
            venue = await db.venues.find_one({"venue_id": venue_id}, {"name": 1})
            venue_name = venue.get("name") if venue else None

        sent = await notify_room_followers(db, room, user, venue_name=venue_name)
        return {"notified": sent, "room_code": canon}

    # ───────── WebSocket ────────────────────────────────────────────────
    @router.websocket("/ws/{code}")
    async def trivia_ws(websocket: WebSocket, code: str):
        await websocket.accept()
        user = await _resolve_ws_user(websocket)
        if not user:
            await websocket.send_text(json.dumps({"type": "error", "code": "unauthorized"}))
            await websocket.close(code=4401)
            return
        hub: RoomHub = websocket.app.state.trivia_room_hub
        # Accept any of the join-page code variants — REST + WS must
        # agree on the canonical form or a typo'd URL gets stuck on the
        # spinner instead of redirecting.
        canon = normalize_room_code(code)
        code = canon
        room = hub.get(canon)
        if not room:
            await websocket.send_text(json.dumps({"type": "error",
                                                      "code": "room_not_found"}))
            await websocket.close(code=4404)
            return
        if user["user_id"] not in room.players:
            # Auto-join lobby on WS connect IF in lobby (else reject).
            # Window B's /trivia/join → /trivia/rooms/:code flow only
            # opens a socket and never calls REST /join, so treat "open
            # ws while in lobby" as the join itself.
            try:
                room = await hub.add_player(canon, {
                    "user_id": user["user_id"],
                    "name":     user.get("name") or "Player",
                    "avatar":   user.get("avatar_url"),
                })
                await hub.broadcast(canon, {
                    "type": "player_joined",
                    "user": {"id": user["user_id"], "name": user.get("name"),
                               "avatar": user.get("avatar_url")},
                })
            except PermissionError:
                await websocket.send_text(json.dumps({"type": "error",
                                                          "code": "room_in_progress"}))
                await websocket.close(code=4409)
                return

        hub.attach_socket(canon, user["user_id"], websocket)

        # Send hello + skew baseline.
        await websocket.send_text(json.dumps({
            "type":       "hello",
            "server_now": _now_ms(),
            "you":         {"user_id": user["user_id"], "name": user.get("name")},
            "room":        room.to_public(),
        }, default=str))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    await websocket.send_text(json.dumps({"type": "error",
                                                              "code": "bad_json"}))
                    continue
                t = msg.get("type")
                if t == "ping":
                    await websocket.send_text(json.dumps({"type": "pong",
                                                              "server_now": _now_ms()}))
                    continue
                if t == "answer":
                    await _handle_answer(hub, room, user, msg)
                    continue
                if t == "leave":
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("[trivia_ws] %s socket error: %s", code, e)
        finally:
            # Just detach the socket — the player STAYS in the room
            # marked as `connected: false`.  Phase 0 of 16b auto-removed
            # the player on disconnect, but that destroyed the room
            # whenever React 18 dev-mode double-mounted the component
            # (cleanup ran before the WS handshake settled).  The store
            # auto-reconnects within 2 s; the host is still the host.
            # A truly-departed player gets garbage-collected when the
            # room transitions to "done" (driver tears it down).
            hub.detach_socket(code, user["user_id"], websocket)

    return router


# ─── Server-authoritative answer handling ─────────────────────────────
async def _handle_answer(hub: RoomHub, room: Room, user: dict, msg: dict) -> None:
    if room.phase != "question":
        await hub.send_to(room.code, user["user_id"], {
            "type": "error", "code": "not_in_question_phase",
            "message": "Answers are only accepted during the question phase.",
        })
        return
    q = room.current_question()
    if not q or q["id"] != msg.get("question_id"):
        await hub.send_to(room.code, user["user_id"], {
            "type": "error", "code": "wrong_question_id",
            "message": "Answer is for a different question.",
        })
        return
    p = room.players.get(user["user_id"])
    if not p:
        return
    if q["id"] in p.answers:
        # Replay attempt — silently ignore.
        return

    server_now = datetime.now(timezone.utc)
    started_at = room.question_started_at or server_now
    latency_ms = max(0, int((server_now - started_at).total_seconds() * 1000))
    # Beyond the phase deadline?  Reject.
    if latency_ms > QUESTION_DURATION_SEC * 1000:
        return
    correct = (msg.get("choice_id") == q["correct_choice_id"])
    pts = _score_for(correct, latency_ms)
    # Multiplayer first-correct bonus.
    bonus = 0
    if correct:
        room.correct_order.append(user["user_id"])
        rank = len(room.correct_order)
        if 1 <= rank <= len(FIRST_CORRECT_BONUSES):
            bonus = FIRST_CORRECT_BONUSES[rank - 1]
    total_award = pts + bonus
    p.answers[q["id"]] = {
        "choice_id":  msg.get("choice_id"),
        "latency_ms": latency_ms,
        "correct":    correct,
        "points":     total_award,
        "bonus":      bonus,
        "answered_at": server_now,
    }
    p.score += total_award
    # Suspicious sub-50ms answer — flag but accept.
    if latency_ms < 50:
        try:
            db = hub  # not the db; flag elsewhere
        except Exception:
            pass

    await hub.broadcast(room.code, {
        "type":     "answer_received",
        "user_id":  user["user_id"],
        "answers_in": sum(1 for pp in room.players.values() if q["id"] in pp.answers),
        "total":    len(room.players),
    })
    # If everyone answered, fast-forward to reveal.
    if all(q["id"] in pp.answers for pp in room.players.values()):
        # Wake the advance loop by shortening the deadline.
        room.phase_deadline_at = server_now


# ─── State-machine driver task (one per live room) ─────────────────────
async def _run_room(db, hub: RoomHub, room: Room) -> None:
    """Drives the room from `lobby` → `question` → `reveal` → `leaderboard`
    → … → `done`.  Cancelled when the room is GC'd or the host leaves
    in-lobby."""
    try:
        for i, q in enumerate(room.questions):
            room.current_index = i
            room.phase = "question"
            now = datetime.now(timezone.utc)
            room.question_started_at = now
            room.phase_deadline_at  = now + timedelta(seconds=QUESTION_DURATION_SEC)
            room.correct_order      = []
            await hub.broadcast(room.code, {
                "type":         "phase_change",
                "phase":        "question",
                "current_index": i,
                "total":        len(room.questions),
                "deadline_ms":  int(room.phase_deadline_at.timestamp() * 1000),
                "question":     room.public_question(),
                "server_now":   _now_ms(),
            })
            # Wait until deadline OR everyone answered (the answer handler
            # shortens phase_deadline_at to "now" when all are in).
            while True:
                remaining = (room.phase_deadline_at - datetime.now(timezone.utc)).total_seconds()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(remaining, 0.5))

            # ── REVEAL ────────────────────────────────────────────────
            room.phase = "reveal"
            reveal_deadline = datetime.now(timezone.utc) + timedelta(seconds=REVEAL_DURATION_SEC)
            room.phase_deadline_at = reveal_deadline
            await hub.broadcast(room.code, {
                "type":               "phase_change",
                "phase":               "reveal",
                "current_index":      i,
                "deadline_ms":        int(reveal_deadline.timestamp() * 1000),
                "correct_choice_id": q["correct_choice_id"],
                "per_player": {
                    p.user_id: {
                        "choice_id":  p.answers.get(q["id"], {}).get("choice_id"),
                        "correct":    p.answers.get(q["id"], {}).get("correct", False),
                        "points":     p.answers.get(q["id"], {}).get("points", 0),
                        "bonus":      p.answers.get(q["id"], {}).get("bonus", 0),
                        "total":      p.score,
                    } for p in room.players.values()
                },
                "leaderboard":        room.leaderboard(top=5),
                "server_now":         _now_ms(),
            })
            await asyncio.sleep(REVEAL_DURATION_SEC)

            # ── LEADERBOARD (skip on last question) ───────────────────
            if i < len(room.questions) - 1:
                room.phase = "leaderboard"
                lb_deadline = datetime.now(timezone.utc) + timedelta(seconds=LEADERBOARD_DURATION_SEC)
                room.phase_deadline_at = lb_deadline
                await hub.broadcast(room.code, {
                    "type":         "phase_change",
                    "phase":        "leaderboard",
                    "deadline_ms":  int(lb_deadline.timestamp() * 1000),
                    "leaderboard": room.leaderboard(top=5),
                    "server_now":   _now_ms(),
                })
                await asyncio.sleep(LEADERBOARD_DURATION_SEC)

        # ── DONE — finalise + award BigCoin ───────────────────────────
        room.phase = "done"
        room.done_at = datetime.now(timezone.utc)
        ordered = sorted(room.players.values(), key=lambda p: -p.score)
        final_scores = []
        for rank, p in enumerate(ordered, start=1):
            p.rank = rank
            base_bc = max(0, p.score // BIGCOIN_DIVISOR)
            mult = RANK_MULTIPLIERS.get(rank, 1.0)
            bc = int(round(base_bc * mult))
            # Persist a per-player trivia_sessions row.
            session_id = f"ts_mp_{uuid.uuid4().hex[:14]}"
            try:
                await db.trivia_sessions.insert_one({
                    "id":             session_id,
                    "user_id":        p.user_id,
                    "mode":            "multiplayer",
                    "room_code":      room.code,
                    "category_id":    room.category_id,
                    "category_slug": room.category_slug,
                    "market":         room.market,
                    "started_at":     room.created_at,
                    "ended_at":       room.done_at,
                    "question_ids":  [q["id"] for q in room.questions],
                    "current_index": len(room.questions),
                    "scores":         {p.user_id: p.score},
                    "status":         "done",
                    "difficulty":    2,
                    "bigcoin_awarded": bc,
                    "rank":            rank,
                    "rank_multiplier": mult,
                })
            except Exception as e:
                logger.warning("[room.done] persist failed %s: %s", p.user_id, e)
            if bc > 0:
                try:
                    await bigcoin.award(
                        db, p.user_id, bc,
                        source="trivia_multiplayer_finish",
                        metadata={"room_code": room.code, "rank": rank,
                                    "score": p.score, "multiplier": mult},
                    )
                except Exception as e:
                    logger.warning("[room.done] BC award failed %s: %s", p.user_id, e)
            final_scores.append({
                "user_id":         p.user_id,
                "name":            p.name,
                "rank":            rank,
                "score":           p.score,
                "bigcoin_awarded": bc,
            })
        # Phase H — AD.5 trivia sponsorship prize pipeline.  Runs INLINE
        # after the base BigCoin payouts so the phase_change broadcast
        # can include the per-player sponsor prizes.
        sponsor_prizes: list = []
        try:
            from services.trivia_sponsor_award_pipeline import (
                on_trivia_room_done as _sponsor_award)
            sp_result = await _sponsor_award(
                db,
                room_code=room.code,
                category_id=room.category_id,
                sponsorship_id=room.sponsorship_id,
                final_scores=final_scores)
            sponsor_prizes = sp_result.get("awards") or []
        except Exception as e:
            logger.warning("[room.done] AD.5 sponsor pipeline failed: %s", e)
        await hub.broadcast(room.code, {
            "type":                        "phase_change",
            "phase":                      "done",
            "final_scores":          final_scores,
            "sponsor_prizes":      sponsor_prizes,
            "sponsorship_bound":  room.sponsorship_id,
            "server_now":            _now_ms(),
        })
    except asyncio.CancelledError:
        logger.info("[room.driver] %s cancelled", room.code)
        raise
    except Exception as e:
        logger.exception("[room.driver] %s crashed: %s", room.code, e)
        await hub.broadcast(room.code, {"type": "error", "code": "room_crashed",
                                            "message": str(e)})
