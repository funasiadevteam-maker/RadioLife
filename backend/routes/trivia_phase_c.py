"""Phase C — additive trivia endpoints.

Sits on top of the existing Phase 16b `trivia_room_routes.py` +
in-process `RoomHub` — never modifies those.  Adds the endpoints the
Phase C spec requires that were missing:

  * `GET  /api/trivia/question-sets`                  — list pre-baked sets
  * `POST /api/trivia/rooms/{code}/answer`        — REST answer (mirrors WS)
  * `POST /api/trivia/rooms/{code}/advance`      — host-only fast-forward
  * `GET  /api/trivia/rooms/{code}/results`        — final leaderboard
                                                                                                          (post-`done`, reads
                                                                                                            persisted trivia_sessions)

The `answer` and `advance` endpoints re-use hub-owned state so
WebSocket + REST clients stay coherent.  `results` reads persisted
`trivia_sessions` (already written by the room driver on `done`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
# The existing route module exposes _handle_answer + normalize_room_code
# — we import them so the WS + REST paths score identically.
from routes.trivia_room_routes import _handle_answer, normalize_room_code
from services.trivia_rooms import RoomHub

logger = logging.getLogger("bigfm.trivia.phase_c")

router = APIRouter(prefix="/api/trivia", tags=["trivia-phase-c"])


# ── question-sets ────────────────────────────────────────────────
@router.get("/question-sets",
                        description="Public — pre-baked trivia sets seeded by "
                                                "`backend/scripts/seed_trivia_question_sets.py`.  "
                                                "Correct-index fields are stripped from the response.")
async def list_question_sets(request: Request,
                                                          language: Optional[str] = None,
                                                          category: Optional[str] = None):
    db = request.app.state.db
    q = {"active": True}
    if language:
        q["language"] = language
    if category:
        q["category"] = category
    items = []
    async for s in db.trivia_question_sets.find(q).sort("title", 1):
        items.append({
            "id":                        s.get("id"),
            "title":                  s.get("title"),
            "category":            s.get("category"),
            "language":            s.get("language"),
            "difficulty":        s.get("difficulty"),
            "question_count":  int(s.get("question_count")
                                                        or len(s.get("questions") or [])),
        })
    return {"items": items, "count": len(items)}


@router.get("/question-sets/{set_id}",
                        description="Public — question set metadata + prompts + "
                                                "options WITHOUT correct_index (never leak answers).")
async def get_question_set(set_id: str, request: Request):
    s = await request.app.state.db.trivia_question_sets.find_one(
        {"id": set_id, "active": True})
    if not s:
        raise HTTPException(404, {"code": "question_set_not_found"})
    # Strip correct_index from the public payload.
    qs = []
    for q in (s.get("questions") or []):
        qs.append({
            "id":                            q.get("id"),
            "prompt":                    q.get("prompt"),
            "options":                q.get("options") or [],
            "time_limit_seconds": int(q.get("time_limit_seconds") or 15),
            "points":                    int(q.get("points") or 100),
        })
    return {
        "id":                    s.get("id"),
        "title":                s.get("title"),
        "category":          s.get("category"),
        "language":          s.get("language"),
        "difficulty":      s.get("difficulty"),
        "question_count":  len(qs),
        "questions":        qs,
    }


# ── REST answer (WebSocket-equivalent) ────────────────────────────
class AnswerBody(BaseModel):
    question_id:   str
    choice_id:      Optional[str] = None
    selected_index: Optional[int] = Field(None, ge=0, le=3)


@router.post("/rooms/{code}/answer",
                          description="Submit an answer over REST — equivalent to the "
                                                    "WebSocket `answer` message.  Auth-only.")
async def rest_answer(code: str, body: AnswerBody, request: Request,
                                              user: dict = Depends(current_user)):
    hub: RoomHub = request.app.state.trivia_room_hub
    canon = normalize_room_code(code)
    room = hub.get(canon)
    if not room:
        raise HTTPException(404, {"code": "room_not_found"})
    if room.phase != "question":
        raise HTTPException(400, {"code": "not_in_question_phase"})
    q = room.current_question()
    if not q or q["id"] != body.question_id:
        raise HTTPException(400, {"code": "wrong_question_id"})
    if user["user_id"] not in room.players:
        raise HTTPException(403, {"code": "not_in_room"})
    p = room.players[user["user_id"]]
    if q["id"] in p.answers:
        raise HTTPException(400, {"code": "already_answered"})
    # Late guard — mirror _handle_answer's latency check but 400 here so
    # the client gets an explicit signal.
    started_at = room.question_started_at or datetime.now(timezone.utc)
    latency_ms = int(
        (datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    from services.trivia_rooms import QUESTION_DURATION_SEC
    if latency_ms > QUESTION_DURATION_SEC * 1000:
        raise HTTPException(400, {"code": "answer_late",
                                                            "latency_ms": latency_ms})
    # Choice can be supplied either as `choice_id` (WS-shape) or
    # `selected_index` (Phase C spec-shape).  Normalise to choice_id
    # if the caller sent an index — look up `q["choices"]`.
    choice_id = body.choice_id
    if choice_id is None and body.selected_index is not None:
        choices = q.get("choices") or []
        if 0 <= body.selected_index < len(choices):
            _c = choices[body.selected_index]
            # `choices` entries are either strings or dicts {id, text}.
            choice_id = _c.get("id") if isinstance(_c, dict) else str(
                body.selected_index)
    if choice_id is None:
        raise HTTPException(400, {"code": "missing_choice"})
    # Delegate to the WS-side handler so scoring / bonuses / broadcasts
    # stay identical between transports.
    await _handle_answer(hub, room, user,
                                              {"question_id": q["id"], "choice_id": choice_id})
    pa = p.answers.get(q["id"]) or {}
    return {
        "ok":              True,
        "correct":        bool(pa.get("correct")),
        "points_awarded": int(pa.get("points") or 0),
        "response_time_ms": int(pa.get("latency_ms") or latency_ms),
        "your_total":  int(p.score),
    }


# ── host-only advance ────────────────────────────────────────────
@router.post("/rooms/{code}/advance",
                          description="Host-only — fast-forward the current phase.  "
                                                    "Coexists with the server-timed state machine: "
                                                    "shortens `phase_deadline_at` to `now` so the "
                                                    "driver picks up on its next tick (~0.5 s).")
async def advance_room(code: str, request: Request,
                                                user: dict = Depends(current_user)):
    hub: RoomHub = request.app.state.trivia_room_hub
    canon = normalize_room_code(code)
    room = hub.get(canon)
    if not room:
        raise HTTPException(404, {"code": "room_not_found"})
    if room.host_user_id != user["user_id"]:
        raise HTTPException(403, {"code": "host_only"})
    if room.phase in ("lobby", "done"):
        raise HTTPException(400, {"code": "not_advanceable",
                                                            "phase": room.phase})
    # The driver watches phase_deadline_at on 0.5-s ticks; setting it in
    # the past forces the phase to end on the very next tick — no locks
    # needed because it's a single owned coroutine.
    room.phase_deadline_at = datetime.now(timezone.utc)
    return {"ok": True, "phase": room.phase, "advance_at": "now"}


# ── final leaderboard (persisted) ────────────────────────────────
@router.get("/rooms/{code}/results",
                        description="Final leaderboard for a finished room.  Reads "
                                                "the persisted `trivia_sessions` rows written by "
                                                "the room driver on the `done` transition.")
async def room_results(code: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    hub: RoomHub = request.app.state.trivia_room_hub
    canon = normalize_room_code(code)
    # If the room is still in the hub (typical during the 5-min GC TTL),
    # prefer the live view — it has the freshest ranking + player names.
    live = hub.get(canon)
    if live and live.phase == "done":
        ordered = sorted(live.players.values(), key=lambda p: -p.score)
        return {
            "code":        canon,
            "phase":      live.phase,
            "leaderboard": [
                {"user_id": p.user_id, "name": p.name, "avatar": p.avatar,
                  "score":    p.score, "rank": i + 1}
                for i, p in enumerate(ordered)],
            "total_questions": len(live.questions),
            "done_at":  live.done_at.isoformat() if live.done_at else None,
        }
    # Fallback — pull persisted rows.
    rows = []
    async for s in db.trivia_sessions.find(
                {"room_code": canon, "mode": "multiplayer"}
                ).sort("rank", 1):
        rows.append({
            "user_id":              s.get("user_id"),
            "rank":                  s.get("rank"),
            "score":                (s.get("scores") or {}).get(s.get("user_id"))
                                            if isinstance(s.get("scores"), dict)
                                            else None,
            "bigcoin_awarded": s.get("bigcoin_awarded"),
            "ended_at":            (s.get("ended_at").isoformat()
                                                    if isinstance(s.get("ended_at"), datetime)
                                                    else s.get("ended_at")),
        })
    if not rows:
        raise HTTPException(404, {"code": "results_not_found"})
    return {
        "code":              canon,
        "phase":            "done",
        "leaderboard":  rows,
        "total_questions": len({q for r in rows
                                                    for q in (r.get("question_ids") or [])}),
    }


__all__ = ["router"]
