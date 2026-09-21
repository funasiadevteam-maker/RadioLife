"""
Phase 16a — Trivia REST endpoints (single-player solo mode).

All routes mounted under /api/trivia/*.  Server is the authority on
correctness, latency, scoring, and the answer key (never exposed in the
session-start response).

Wired up in server.py via `from routes.trivia_routes import build_router`.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from services.market_context import get_user_market
from services.trivia_ai import pick_for_user, generate_questions
from services import bigcoin

logger = logging.getLogger("bigfm.trivia_routes")

# Scoring constants live here so tests can import them.
BASE_POINTS         = 100
FAST_BONUS_UNDER_3S = 50
FAST_BONUS_UNDER_6S = 25
QUESTIONS_PER_SESSION = 10
PER_QUESTION_TIMEOUT_SEC = 30
BIGCOIN_DIVISOR     = 10   # score / 10 = BC awarded at session finish


class StartReq(BaseModel):
    category_id: str
    difficulty:  int = Field(default=2, ge=1, le=5)


class AnswerReq(BaseModel):
    question_id:        str
    choice_id:          str
    client_answered_at: Optional[str] = None  # advisory only


def _public_question(q: dict, *, served_at: datetime) -> dict:
    """Strip the correct_choice_id before exposing to the client."""
    return {
        "id":         q["id"],
        "prompt":     q["prompt"],
        "choices":    q["choices"],
        "category":   q.get("category"),
        "difficulty": q.get("difficulty"),
        "served_at":  served_at.isoformat(),
    }


def _score_for(correct: bool, latency_ms: int) -> int:
    if not correct:
        return 0
    pts = BASE_POINTS
    if latency_ms < 3000:
        pts += FAST_BONUS_UNDER_3S
    elif latency_ms < 6000:
        pts += FAST_BONUS_UNDER_6S
    return pts


def build_router(db, get_current_user) -> APIRouter:
    router = APIRouter(prefix="/api/trivia", tags=["trivia"])

    # ─── Categories ─────────────────────────────────────────────────────
    @router.get("/categories")
    async def list_categories(request: Request, user: dict = Depends(get_current_user)):
        # Lazy-seed on first request — startup hooks fire before this
        # router is mounted, so we initialise here once.
        seeded_flag = await db.migration_flags.find_one(
            {"_id": "_phase16a_categories_seeded"})
        if not (seeded_flag and seeded_flag.get("done")):
            from services.trivia_ai import (
                ensure_trivia_indexes, seed_default_categories,
            )
            await ensure_trivia_indexes(db)
            await seed_default_categories(db)
        market = await get_user_market(request, user, db)
        out: list[dict] = []
        async for c in db.trivia_categories.find(
            {"active": True, "market": {"$in": ["global", market]}},
            projection={"_id": 0},
        ).sort([("weight", -1), ("name", 1)]):
            out.append(c)
        # Content-language HARD filter — hide language-specific categories
        # (e.g. Bollywood) for users who didn't opt into that language.
        try:
            from core.content_language import (
                user_content_languages as _ucl, user_show_all as _usa,
                content_allowed as _ca, user_filter_scopes as _ufs,
            )
            if not _usa(user) and _ufs(user).get("quiz"):
                _prefs = _ucl(user)
                out = [c for c in out if _ca(
                    f"{c.get('name', '')} {c.get('slug', '')} {c.get('description', '')}",
                    _prefs, explicit=c.get("content_language"))]
        except Exception:
            pass
        return {"market": market, "categories": out}

    # ─── Start a solo session ───────────────────────────────────────────
    @router.post("/sessions/start")
    async def start_session(req: StartReq, request: Request, user: dict = Depends(get_current_user)):
        market = await get_user_market(request, user, db)
        cat = await db.trivia_categories.find_one({"id": req.category_id, "active": True})
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        category_slug = cat["slug"]

        questions = await pick_for_user(
            db, user["user_id"], market, category_slug,
            count=QUESTIONS_PER_SESSION, difficulty=req.difficulty,
        )
        if len(questions) < 1:
            raise HTTPException(
                status_code=503,
                detail="Trivia bank empty for this market/category — try again in a minute.",
            )

        now = datetime.now(timezone.utc)
        session_id = f"ts_{uuid.uuid4().hex[:14]}"
        session_doc = {
            "id":             session_id,
            "user_id":        user["user_id"],
            "mode":           "solo",
            "category_id":    req.category_id,
            "category_slug":  category_slug,
            "market":         market,
            "started_at":     now,
            "ended_at":       None,
            "question_ids":   [q["id"] for q in questions],
            "current_index": 0,
            "scores":         {user["user_id"]: 0},
            "served_at":      {questions[0]["id"]: now},
            "status":         "active",
            "difficulty":     req.difficulty,
        }
        await db.trivia_sessions.insert_one(session_doc)
        return {
            "session_id": session_id,
            "started_at": now.isoformat(),
            "category":   {"id": cat["id"], "name": cat["name"], "slug": category_slug},
            "questions":  [_public_question(q, served_at=now) for q in questions],
            "per_question_timeout_sec": PER_QUESTION_TIMEOUT_SEC,
        }

    # ─── Answer ─────────────────────────────────────────────────────────
    @router.post("/sessions/{session_id}/answer")
    async def answer(session_id: str, req: AnswerReq,
                      user: dict = Depends(get_current_user)):
        session = await db.trivia_sessions.find_one({"id": session_id})
        if not session or session["user_id"] != user["user_id"]:
            raise HTTPException(status_code=404, detail="Session not found")
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail="Session already finished")
        if req.question_id not in session["question_ids"]:
            raise HTTPException(status_code=400, detail="Question not in session")
        # No replay: refuse if the user already answered this question in
        # this session.
        already = await db.trivia_answers.find_one(
            {"session_id": session_id, "question_id": req.question_id},
        )
        if already:
            raise HTTPException(status_code=400, detail="Question already answered")

        served_at = session.get("served_at", {}).get(req.question_id) or session["started_at"]
        if isinstance(served_at, str):
            served_at = datetime.fromisoformat(served_at)
        # Mongo strips tzinfo on read — coerce back to UTC.
        if served_at.tzinfo is None:
            served_at = served_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        latency_ms = max(0, int((now - served_at).total_seconds() * 1000))

        # Anti-cheat: reject answers after the 30s server-authoritative timeout.
        if latency_ms > PER_QUESTION_TIMEOUT_SEC * 1000:
            await db.trivia_answers.insert_one({
                "id":              f"ta_{uuid.uuid4().hex[:14]}",
                "session_id":      session_id,
                "user_id":         user["user_id"],
                "question_id":     req.question_id,
                "choice_id":       None,
                "answered_at":     now,
                "latency_ms":      latency_ms,
                "correct":         False,
                "points_awarded":  0,
                "timed_out":       True,
            })
            raise HTTPException(
                status_code=408,
                detail={
                    "error":      "timeout",
                    "latency_ms": latency_ms,
                    "message":    f"Answer arrived after {PER_QUESTION_TIMEOUT_SEC}s window.",
                },
            )

        q = await db.trivia_questions.find_one({"id": req.question_id})
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")
        correct = (req.choice_id == q["correct_choice_id"])
        points  = _score_for(correct, latency_ms)

        await db.trivia_answers.insert_one({
            "id":              f"ta_{uuid.uuid4().hex[:14]}",
            "session_id":      session_id,
            "user_id":         user["user_id"],
            "question_id":     req.question_id,
            "choice_id":       req.choice_id,
            "answered_at":     now,
            "latency_ms":      latency_ms,
            "correct":         correct,
            "points_awarded":  points,
            "timed_out":       False,
        })

        # Update running score + advance index + stamp the NEXT question's served_at.
        next_idx = session["current_index"] + 1
        next_qid = session["question_ids"][next_idx] if next_idx < len(session["question_ids"]) else None
        update_doc = {
            f"scores.{user['user_id']}": session["scores"].get(user["user_id"], 0) + points,
            "current_index":            next_idx,
        }
        if next_qid:
            update_doc[f"served_at.{next_qid}"] = now
        await db.trivia_sessions.update_one({"id": session_id}, {"$set": update_doc})

        return {
            "correct":            correct,
            "correct_choice_id": q["correct_choice_id"],
            "points_awarded":    points,
            "latency_ms":        latency_ms,
            "running_score":     update_doc[f"scores.{user['user_id']}"],
            "next_question_id": next_qid,
        }

    # ─── Finish ─────────────────────────────────────────────────────────
    @router.post("/sessions/{session_id}/finish")
    async def finish_session(session_id: str, user: dict = Depends(get_current_user)):
        session = await db.trivia_sessions.find_one({"id": session_id})
        if not session or session["user_id"] != user["user_id"]:
            raise HTTPException(status_code=404, detail="Session not found")
        if session["status"] == "done":
            # Idempotent: return the prior result.
            return {
                "session_id":      session_id,
                "final_score":     session["scores"].get(user["user_id"], 0),
                "bigcoin_awarded": session.get("bigcoin_awarded", 0),
                "already_finished": True,
            }
        score = session["scores"].get(user["user_id"], 0)
        bc = max(0, math.floor(score / BIGCOIN_DIVISOR))

        if bc > 0:
            try:
                await bigcoin.award(
                    db, user["user_id"], bc,
                    source="trivia_session_complete",
                    metadata={"session_id": session_id, "score": score},
                )
            except Exception as e:
                logger.warning("[trivia] BC award failed for %s: %s", user["user_id"], e)

        now = datetime.now(timezone.utc)
        await db.trivia_sessions.update_one(
            {"id": session_id},
            {"$set": {
                "status":          "done",
                "ended_at":        now,
                "bigcoin_awarded": bc,
            }},
        )
        # Count correct/incorrect for the result screen.
        n_correct = await db.trivia_answers.count_documents(
            {"session_id": session_id, "correct": True})
        n_total = len(session["question_ids"])
        return {
            "session_id":      session_id,
            "final_score":     score,
            "bigcoin_awarded": bc,
            "correct":         n_correct,
            "total":           n_total,
            "already_finished": False,
        }

    # ─── Resume an active session ───────────────────────────────────────
    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str, user: dict = Depends(get_current_user)):
        s = await db.trivia_sessions.find_one({"id": session_id}, projection={"_id": 0})
        if not s or s["user_id"] != user["user_id"]:
            raise HTTPException(status_code=404, detail="Session not found")
        qs: list[dict] = []
        async for q in db.trivia_questions.find(
            {"id": {"$in": s["question_ids"]}}, projection={"_id": 0},
        ):
            qs.append(q)
        qmap = {q["id"]: q for q in qs}
        ordered = [qmap[qid] for qid in s["question_ids"] if qid in qmap]
        return {
            "id":             s["id"],
            "status":         s["status"],
            "category_id":    s["category_id"],
            "current_index": s["current_index"],
            "started_at":     s["started_at"].isoformat() if s.get("started_at") else None,
            "running_score": s["scores"].get(user["user_id"], 0),
            "questions":      [_public_question(q, served_at=s.get("started_at", datetime.now(timezone.utc)))
                                  for q in ordered],
        }

    # ─── History ────────────────────────────────────────────────────────
    @router.get("/me/history")
    async def history(limit: int = 20, user: dict = Depends(get_current_user)):
        limit = max(1, min(100, limit))
        items: list[dict] = []
        async for s in db.trivia_sessions.find(
            {"user_id": user["user_id"], "status": "done"},
            projection={"_id": 0},
        ).sort("ended_at", -1).limit(limit):
            items.append({
                "session_id":      s["id"],
                "category_slug":  s.get("category_slug"),
                "category_id":    s.get("category_id"),
                "started_at":     s["started_at"].isoformat() if s.get("started_at") else None,
                "ended_at":       s["ended_at"].isoformat() if s.get("ended_at") else None,
                "final_score":    s["scores"].get(user["user_id"], 0),
                "bigcoin_awarded": s.get("bigcoin_awarded", 0),
                "difficulty":     s.get("difficulty", 2),
                "market":         s.get("market"),
            })
        return {"items": items}

    # ─── Admin pre-seed (lazy is default) ───────────────────────────────
    @router.post("/admin/seed")
    async def admin_seed(market: str, category: str, count: int = 30,
                            difficulty: int = 2,
                            user: dict = Depends(get_current_user)):
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin only")
        docs = await generate_questions(db, market, category, difficulty, count)
        return {"generated": len(docs), "market": market,
                  "category": category, "difficulty": difficulty}

    return router
