"""RadioLife Social V2 — LIVE DREAM Q&A.

Approved advisors host live audio/video sessions where the community asks
about dreams in real time. Reuses `services.livekit_client` for room tokens
(mock-safe when LiveKit env is unset) — live VIDEO validates only on a native
build after Publish; the text Q&A queue works everywhere.

Routes: /api/social/live/*
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from routes.social_v2 import _user_public
from routes.dreams_guidance import CATEGORY_LABELS
from services import livekit_client

router = APIRouter(prefix="/api/social/live", tags=["dream_live"])

MODES = ["audio", "video"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


async def ensure_live_indexes(db) -> None:
    await db.dream_live_sessions.create_index([("status", 1), ("created_at", -1)], name="dls_q")
    await db.dream_live_sessions.create_index("session_id", unique=True, name="dls_id")
    await db.dream_live_sessions.create_index([("advisor_id", 1)], name="dls_adv")
    await db.dream_live_questions.create_index([("session_id", 1), ("created_at", 1)], name="dlq_room")


def _safe_token(room: str, identity: str, role: str, perms: dict) -> Optional[str]:
    """Mint a LiveKit token; never 500 if the SDK/creds misbehave — the text
    Q&A queue works with or without an A/V token."""
    try:
        return livekit_client.mint_room_token(
            room_name=room, identity=identity, role=role, permissions=perms)
    except Exception:
        return None


def _live_mode() -> str:
    try:
        return livekit_client.status()["mode"]
    except Exception:
        return "mock"


async def _advisor_for(db, uid: str) -> dict:
    a = await db.advisor_profiles.find_one({"user_id": uid, "status": "approved"})
    if not a:
        raise HTTPException(403, {"code": "not_an_advisor"})
    return a



def _session_public(s: dict, question_count: int = 0) -> dict:
    return {"session_id": s["session_id"], "advisor_id": s.get("advisor_id"),
            "advisor_name": s.get("advisor_name"),
            "advisor_category": s.get("advisor_category"),
            "advisor_category_label": CATEGORY_LABELS.get(s.get("advisor_category")),
            "advisor_photo_url": s.get("advisor_photo_url"),
            "title": s.get("title"), "description": s.get("description"),
            "mode": s.get("mode"), "status": s.get("status"),
            "scheduled_at": _iso(s.get("scheduled_at")),
            "started_at": _iso(s.get("started_at")),
            "ended_at": _iso(s.get("ended_at")),
            "viewer_count": int(s.get("viewer_count", 0)),
            "question_count": question_count,
            "created_at": _iso(s.get("created_at"))}


@router.get("/sessions")
async def list_sessions(request: Request, status: str = "live",
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    if status == "past":
        q = {"status": "ended"}
    elif status == "upcoming":
        q = {"status": "scheduled"}
    else:
        q = {"status": "live"}
    featured_ids: set = set()
    try:
        from routes.dream_ads import active_featured_advisor_ids
        featured_ids = await active_featured_advisor_ids(db, "live")
    except Exception:
        pass
    items = []
    async for s in db.dream_live_sessions.find(q).sort("created_at", -1).limit(40):
        qc = await db.dream_live_questions.count_documents({"session_id": s["session_id"]})
        pub = _session_public(s, qc)
        pub["featured"] = s.get("advisor_id") in featured_ids
        items.append(pub)
    items.sort(key=lambda x: 0 if x.get("featured") else 1)  # featured first, stable
    return {"items": items, "live_mode": _live_mode()}


class SessionBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    description: Optional[str] = Field(None, max_length=600)
    mode: str = "audio"
    scheduled_at: Optional[str] = None


@router.post("/sessions")
async def create_session(body: SessionBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _advisor_for(db, user["user_id"])
    mode = body.mode if body.mode in MODES else "audio"
    sid = f"dl_{uuid.uuid4().hex[:16]}"
    room = f"dreamlive_{sid}"
    go_live = not body.scheduled_at
    doc = {"_id": sid, "session_id": sid, "advisor_id": a["advisor_id"],
           "advisor_name": a.get("display_name"), "advisor_category": a.get("category"),
           "advisor_photo_url": a.get("photo_url"),
           "host_user_id": user["user_id"],
           "title": body.title.strip(), "description": (body.description or "").strip() or None,
           "mode": mode, "room_name": room,
           "status": "live" if go_live else "scheduled",
           "scheduled_at": body.scheduled_at,
           "started_at": _now() if go_live else None, "ended_at": None,
           "viewer_count": 0, "created_at": _now()}
    await db.dream_live_sessions.insert_one(doc)
    return _session_public(doc, 0)


async def _session_or_404(db, session_id: str) -> dict:
    s = await db.dream_live_sessions.find_one({"session_id": session_id})
    if not s:
        raise HTTPException(404, {"code": "session_not_found"})
    return s


@router.get("/sessions/{session_id}")
async def session_detail(session_id: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _session_or_404(db, session_id)
    is_host = s.get("host_user_id") == user["user_id"]
    token = None
    if s.get("status") == "live":
        token = _safe_token(
            s["room_name"], user["user_id"],
            "host" if is_host else "guest",
            {"can_publish": is_host,
             "can_publish_video": is_host and s.get("mode") == "video",
             "can_subscribe": True})
    questions = []
    async for qd in db.dream_live_questions.find(
            {"session_id": session_id}).sort("created_at", 1).limit(200):
        questions.append({"id": qd["_id"], "user_id": qd.get("user_id"),
                          "name": qd.get("name"), "text": qd.get("text"),
                          "answered": bool(qd.get("answered")),
                          "created_at": _iso(qd.get("created_at"))})
    out = _session_public(s, len(questions))
    out.update({"is_host": is_host, "join_token": token,
                "livekit_url": livekit_client.livekit_url(),
                "live_mode": _live_mode(),
                "questions": questions})
    return out


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _session_or_404(db, session_id)
    if s.get("host_user_id") != user["user_id"]:
        raise HTTPException(403, {"code": "not_host"})
    livekit_client.delete_room(s["room_name"])
    await db.dream_live_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "ended", "ended_at": _now()}})
    return {"ok": True}


@router.post("/sessions/{session_id}/start")
async def start_session(session_id: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _session_or_404(db, session_id)
    if s.get("host_user_id") != user["user_id"]:
        raise HTTPException(403, {"code": "not_host"})
    await db.dream_live_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "live", "started_at": _now()}})
    return {"ok": True}


@router.post("/sessions/{session_id}/join")
async def join_session(session_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _session_or_404(db, session_id)
    await db.dream_live_sessions.update_one(
        {"session_id": session_id}, {"$inc": {"viewer_count": 1}})
    return {"ok": True}


class QuestionBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


@router.post("/sessions/{session_id}/questions")
async def ask_question(session_id: str, body: QuestionBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _session_or_404(db, session_id)
    pub = _user_public(user)
    qid = f"dlq_{uuid.uuid4().hex[:14]}"
    await db.dream_live_questions.insert_one({
        "_id": qid, "session_id": session_id, "user_id": user["user_id"],
        "name": pub.get("name"), "text": body.text.strip(),
        "answered": False, "created_at": _now()})
    return {"ok": True, "id": qid}


@router.post("/questions/{question_id}/answer")
async def answer_question(question_id: str, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    q = await db.dream_live_questions.find_one({"_id": question_id})
    if not q:
        raise HTTPException(404, {"code": "question_not_found"})
    s = await db.dream_live_sessions.find_one({"session_id": q["session_id"]})
    if not s or s.get("host_user_id") != user["user_id"]:
        raise HTTPException(403, {"code": "not_host"})
    await db.dream_live_questions.update_one(
        {"_id": question_id}, {"$set": {"answered": True}})
    return {"ok": True}


__all__ = ["router", "ensure_live_indexes"]
