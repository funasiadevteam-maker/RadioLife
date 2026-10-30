"""FUUSIC Arena — Play-With-Friends competitive layer.

Head-to-head and group CHALLENGES on skill games (Trivia, Quiz): a host
invites friends to the SAME fixed question set; each participant plays
async; the highest score wins and earns BigPoints.  Every submission also
feeds a weekly SCORE LEADERBOARD (global + friends, overall + per-game).

Shared /api/arena contract — identical for web and mobile.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from routes.social_v2 import _friend_ids, _user_public, _users_map
from services.points_service import PointsService

router = APIRouter(prefix="/api/arena", tags=["arena"])

# ── Challengeable skill games ────────────────────────────────────────
GAMES = [
    {"key": "trivia", "label": "Trivia Clash", "icon": "help-circle",
     "blurb": "5 general-knowledge questions — fastest correct wins."},
    {"key": "quiz", "label": "Movie Quiz", "icon": "film",
     "blurb": "5 Bollywood & cinema questions, head-to-head."},
]
GAME_LABELS = {g["key"]: g["label"] for g in GAMES}
GAME_ICONS = {g["key"]: g["icon"] for g in GAMES}

CHALLENGE_TTL_HOURS = 48
DEFAULT_PRIZE = 100
MIN_PRIZE, MAX_PRIZE = 10, 500
QUESTIONS_PER_ROUND = 5

# ── Static question bank (seeded into challenge_questions) ────────────
QUIZ_BANK: dict[str, list[dict]] = {
    "trivia": [
        {"prompt": "Which planet is the largest in our solar system?",
         "choices": ["Earth", "Jupiter", "Saturn", "Neptune"], "correct": 1},
        {"prompt": "How many continents are there on Earth?",
         "choices": ["5", "6", "7", "8"], "correct": 2},
        {"prompt": "What is the chemical symbol for gold?",
         "choices": ["Gd", "Au", "Ag", "Go"], "correct": 1},
        {"prompt": "Which ocean is the largest?",
         "choices": ["Atlantic", "Indian", "Arctic", "Pacific"], "correct": 3},
        {"prompt": "In which year did humans first land on the Moon?",
         "choices": ["1965", "1969", "1972", "1958"], "correct": 1},
        {"prompt": "What is the tallest mountain above sea level?",
         "choices": ["K2", "Kangchenjunga", "Everest", "Makalu"], "correct": 2},
        {"prompt": "Which gas do plants mainly absorb for photosynthesis?",
         "choices": ["Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen"], "correct": 2},
        {"prompt": "How many sides does a hexagon have?",
         "choices": ["5", "6", "7", "8"], "correct": 1},
        {"prompt": "What is the capital of Japan?",
         "choices": ["Osaka", "Kyoto", "Tokyo", "Nagoya"], "correct": 2},
        {"prompt": "Which is the smallest prime number?",
         "choices": ["0", "1", "2", "3"], "correct": 2},
        {"prompt": "The Great Barrier Reef is off the coast of which country?",
         "choices": ["Brazil", "Australia", "Mexico", "Thailand"], "correct": 1},
        {"prompt": "Which metal is liquid at room temperature?",
         "choices": ["Mercury", "Lead", "Iron", "Zinc"], "correct": 0},
        {"prompt": "How many strings does a standard guitar have?",
         "choices": ["4", "5", "6", "7"], "correct": 2},
        {"prompt": "What is the fastest land animal?",
         "choices": ["Lion", "Cheetah", "Horse", "Greyhound"], "correct": 1},
    ],
    "quiz": [
        {"prompt": "Who directed the film '3 Idiots'?",
         "choices": ["Rajkumar Hirani", "Karan Johar", "Rohit Shetty", "Zoya Akhtar"], "correct": 0},
        {"prompt": "Which actor is known as the 'King of Bollywood'?",
         "choices": ["Salman Khan", "Aamir Khan", "Shah Rukh Khan", "Akshay Kumar"], "correct": 2},
        {"prompt": "'Lagaan' was set during the rule of which empire?",
         "choices": ["Mughal", "British", "Maratha", "Portuguese"], "correct": 1},
        {"prompt": "Who composed the music for 'Slumdog Millionaire'?",
         "choices": ["Pritam", "A. R. Rahman", "Shankar-Ehsaan-Loy", "Vishal-Shekhar"], "correct": 1},
        {"prompt": "Which movie features the song 'Chaiyya Chaiyya'?",
         "choices": ["Dil Se", "Dil Chahta Hai", "Devdas", "Veer-Zaara"], "correct": 0},
        {"prompt": "Deepika Padukone made her Bollywood debut opposite whom?",
         "choices": ["Ranbir Kapoor", "Shah Rukh Khan", "Saif Ali Khan", "Hrithik Roshan"], "correct": 1},
        {"prompt": "Which film won India's first Academy Award nomination for Best Foreign Film?",
         "choices": ["Mother India", "Salaam Bombay", "Lagaan", "Devdas"], "correct": 0},
        {"prompt": "Who played the title role in 'Bajirao Mastani'?",
         "choices": ["Ranveer Singh", "Ranbir Kapoor", "Hrithik Roshan", "Ajay Devgn"], "correct": 0},
        {"prompt": "'Sholay' was released in which year?",
         "choices": ["1971", "1975", "1980", "1983"], "correct": 1},
        {"prompt": "Which actress starred in 'Queen' (2014)?",
         "choices": ["Alia Bhatt", "Kangana Ranaut", "Anushka Sharma", "Vidya Balan"], "correct": 1},
        {"prompt": "Who is the lead actor of the 'Dhoom' franchise villains across films?",
         "choices": ["Abhishek Bachchan", "John Abraham", "Uday Chopra", "Various"], "correct": 3},
        {"prompt": "Which movie popularised the dialogue 'Mere paas maa hai'?",
         "choices": ["Deewaar", "Zanjeer", "Don", "Trishul"], "correct": 0},
    ],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Any) -> Optional[str]:
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return dt


def _week_key(dt: Optional[datetime] = None) -> str:
    dt = dt or _now()
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ───────────────────────── bootstrap ─────────────────────────────────
async def ensure_challenge_bank(db) -> None:
    """Seed the static question bank (idempotent) + indexes."""
    for game_key, rows in QUIZ_BANK.items():
        for i, q in enumerate(rows):
            qid = f"qc_{game_key}_{i}"
            await db.challenge_questions.update_one(
                {"_id": qid},
                {"$set": {"game_key": game_key, "prompt": q["prompt"],
                          "choices": q["choices"], "correct": q["correct"]}},
                upsert=True)
    try:
        await db.game_scores.create_index([("week", 1), ("game_key", 1), ("user_id", 1)])
        await db.game_scores.create_index([("user_id", 1), ("created_at", -1)])
        await db.game_challenges.create_index([("participants", 1), ("status", 1)])
        await db.game_challenges.create_index([("invitees", 1), ("status", 1)])
        await db.game_challenges.create_index([("expires_at", 1)])
    except Exception:
        pass


async def _questions_for(db, game_key: str, ids: list[str]) -> list[dict]:
    rows = {r["_id"]: r async for r in db.challenge_questions.find({"_id": {"$in": ids}})}
    return [rows[i] for i in ids if i in rows]


# ───────────────────────── serializers ───────────────────────────────
def _challenge_public(doc: dict, uid: str, umap: dict) -> dict:
    parts = doc.get("participants") or []
    invitees = doc.get("invitees") or []
    scores = doc.get("scores") or {}
    submitted = doc.get("submitted") or []
    done = doc.get("status") == "completed"
    out = {
        "id": doc["_id"],
        "game_key": doc["game_key"],
        "game_label": doc.get("game_label") or GAME_LABELS.get(doc["game_key"], "Game"),
        "game_icon": GAME_ICONS.get(doc["game_key"], "help-circle"),
        "mode": doc.get("mode", "h2h"),
        "title": doc.get("title") or GAME_LABELS.get(doc["game_key"], "Challenge"),
        "status": doc.get("status", "active"),
        "prize_points": doc.get("prize_points", DEFAULT_PRIZE),
        "host": umap.get(doc["host_id"]),
        "is_host": doc["host_id"] == uid,
        "created_at": _iso(doc.get("created_at")),
        "expires_at": _iso(doc.get("expires_at")),
        "question_count": len(doc.get("question_ids") or []),
        "participants": [umap[i] for i in parts if i in umap],
        "invitees": [umap[i] for i in invitees if i in umap],
        "submitted_ids": submitted,
        "i_joined": uid in parts,
        "i_invited": uid in invitees and uid not in parts,
        "i_submitted": uid in submitted,
        "winner_id": doc.get("winner_id"),
        "winner": umap.get(doc.get("winner_id")) if doc.get("winner_id") else None,
        "i_won": done and doc.get("winner_id") == uid,
    }
    # Reveal scoreboard only once the challenge is completed.
    if done:
        board = []
        for pid in parts:
            s = scores.get(pid)
            board.append({"user": umap.get(pid), "score": (s or {}).get("score", 0),
                          "correct": (s or {}).get("correct", 0),
                          "submitted": pid in submitted})
        board.sort(key=lambda b: b["score"], reverse=True)
        out["scoreboard"] = board
        out["my_score"] = (scores.get(uid) or {}).get("score", 0)
    return out


async def _load_umap(db, doc: dict) -> dict:
    ids = set(doc.get("participants") or []) | set(doc.get("invitees") or [])
    ids.add(doc["host_id"])
    if doc.get("winner_id"):
        ids.add(doc["winner_id"])
    return await _users_map(db, list(ids))


# ───────────────────────── finalize ──────────────────────────────────
async def _finalize(db, doc: dict) -> dict:
    scores = doc.get("scores") or {}
    ranked = sorted(
        ((uid, s) for uid, s in scores.items()),
        key=lambda kv: (kv[1].get("score", 0), -(kv[1].get("at_ts") or 0)),
        reverse=True)
    winner_id = ranked[0][0] if ranked else None
    await db.game_challenges.update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": "completed", "winner_id": winner_id,
                  "completed_at": _now()}})
    doc = {**doc, "status": "completed", "winner_id": winner_id}
    if winner_id:
        try:
            await PointsService(db).award(
                user_id=winner_id, source="game_challenge",
                source_id=doc["_id"], delta=doc.get("prize_points", DEFAULT_PRIZE),
                idempotency_key=f"challenge_win:{doc['_id']}",
                metadata={"game_key": doc["game_key"], "mode": doc.get("mode")})
        except Exception:
            pass
        for pid in (doc.get("participants") or []):
            try:
                await db.social_notifications.insert_one({
                    "_id": f"sn_{uuid.uuid4().hex[:14]}", "user_id": pid,
                    "type": "arena_result", "challenge_id": doc["_id"],
                    "won": pid == winner_id, "title": doc.get("title"),
                    "read": False, "created_at": _now()})
            except Exception:
                pass
    return doc


# ───────────────────────── models ────────────────────────────────────
class CreateBody(BaseModel):
    game_key: str
    mode: str = "h2h"                       # h2h | group
    invitees: list[str] = Field(default_factory=list)
    title: Optional[str] = None
    prize: Optional[int] = None


class SubmitBody(BaseModel):
    answers: list[int] = Field(default_factory=list)
    time_ms: int = 0


class ScoreBody(BaseModel):
    game_key: str
    score: int


# ───────────────────────── endpoints ─────────────────────────────────
@router.get("/games")
async def arena_games(user: dict = Depends(current_user)):
    return {"games": GAMES}


@router.post("/challenges")
async def create_challenge(body: CreateBody, request: Request,
                           user: dict = Depends(current_user)):
    if body.game_key not in GAME_LABELS:
        raise HTTPException(400, {"code": "unknown_game"})
    mode = body.mode if body.mode in ("h2h", "group") else "h2h"
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    invitees = [i for i in dict.fromkeys(body.invitees) if i in friends and i != uid][:20]
    if mode == "h2h" and len(invitees) != 1:
        raise HTTPException(400, {"code": "h2h_needs_one"})
    if mode == "group" and len(invitees) < 2:
        raise HTTPException(400, {"code": "group_needs_two"})
    prize = body.prize if body.prize is not None else DEFAULT_PRIZE
    prize = max(MIN_PRIZE, min(MAX_PRIZE, int(prize)))
    pool = [f"qc_{body.game_key}_{i}" for i in range(len(QUIZ_BANK[body.game_key]))]
    random.shuffle(pool)
    question_ids = pool[:QUESTIONS_PER_ROUND]
    cid = f"ch_{uuid.uuid4().hex[:16]}"
    doc = {
        "_id": cid, "host_id": uid, "game_key": body.game_key,
        "game_label": GAME_LABELS[body.game_key], "mode": mode,
        "title": (body.title or "").strip() or f"{GAME_LABELS[body.game_key]} Challenge",
        "invitees": invitees, "participants": [uid], "question_ids": question_ids,
        "scores": {}, "submitted": [], "status": "active", "winner_id": None,
        "prize_points": prize, "created_at": _now(),
        "expires_at": _now() + timedelta(hours=CHALLENGE_TTL_HOURS)}
    await db.game_challenges.insert_one(doc)
    for iid in invitees:
        try:
            await db.social_notifications.insert_one({
                "_id": f"sn_{uuid.uuid4().hex[:14]}", "user_id": iid,
                "type": "arena_invite", "challenge_id": cid, "from": uid,
                "title": doc["title"], "read": False, "created_at": _now()})
        except Exception:
            pass
    umap = await _load_umap(db, doc)
    return _challenge_public(doc, uid, umap)


@router.get("/challenges")
async def list_challenges(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    invites, active, completed = [], [], []
    seen: set[str] = set()
    cursor = db.game_challenges.find(
        {"$or": [{"participants": uid}, {"invitees": uid}]}
    ).sort("created_at", -1).limit(60)
    docs = [d async for d in cursor]
    ids: set[str] = set()
    for d in docs:
        ids |= set(d.get("participants") or []) | set(d.get("invitees") or [])
        ids.add(d["host_id"])
        if d.get("winner_id"):
            ids.add(d["winner_id"])
    umap = await _users_map(db, list(ids))
    for d in docs:
        if d["_id"] in seen:
            continue
        seen.add(d["_id"])
        pub = _challenge_public(d, uid, umap)
        if d.get("status") == "completed":
            completed.append(pub)
        elif uid in (d.get("invitees") or []) and uid not in (d.get("participants") or []):
            invites.append(pub)
        else:
            active.append(pub)
    return {"invites": invites, "active": active, "completed": completed}


@router.get("/challenges/{cid}")
async def get_challenge(cid: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    doc = await db.game_challenges.find_one({"_id": cid})
    if not doc:
        raise HTTPException(404, {"code": "not_found"})
    umap = await _load_umap(db, doc)
    return _challenge_public(doc, uid, umap)


@router.post("/challenges/{cid}/accept")
async def accept_challenge(cid: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    doc = await db.game_challenges.find_one({"_id": cid})
    if not doc or doc.get("status") != "active":
        raise HTTPException(404, {"code": "not_found"})
    if uid not in (doc.get("invitees") or []) and uid not in (doc.get("participants") or []):
        raise HTTPException(403, {"code": "not_invited"})
    await db.game_challenges.update_one(
        {"_id": cid},
        {"$addToSet": {"participants": uid}, "$pull": {"invitees": uid}})
    doc = await db.game_challenges.find_one({"_id": cid})
    umap = await _load_umap(db, doc)
    return _challenge_public(doc, uid, umap)


@router.post("/challenges/{cid}/decline")
async def decline_challenge(cid: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    await db.game_challenges.update_one({"_id": cid}, {"$pull": {"invitees": uid}})
    return {"ok": True}


@router.get("/challenges/{cid}/quiz")
async def challenge_quiz(cid: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    doc = await db.game_challenges.find_one({"_id": cid})
    if not doc or doc.get("status") != "active":
        raise HTTPException(404, {"code": "not_found"})
    if uid not in (doc.get("participants") or []):
        raise HTTPException(403, {"code": "join_first"})
    if uid in (doc.get("submitted") or []):
        raise HTTPException(409, {"code": "already_submitted"})
    qs = await _questions_for(db, doc["game_key"], doc.get("question_ids") or [])
    return {"challenge_id": cid, "game_key": doc["game_key"],
            "game_label": doc.get("game_label"),
            "questions": [{"id": q["_id"], "prompt": q["prompt"],
                           "choices": q["choices"]} for q in qs]}


@router.post("/challenges/{cid}/submit")
async def submit_challenge(cid: str, body: SubmitBody, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    doc = await db.game_challenges.find_one({"_id": cid})
    if not doc or doc.get("status") != "active":
        raise HTTPException(404, {"code": "not_found"})
    if uid not in (doc.get("participants") or []):
        raise HTTPException(403, {"code": "join_first"})
    if uid in (doc.get("submitted") or []):
        raise HTTPException(409, {"code": "already_submitted"})
    qs = await _questions_for(db, doc["game_key"], doc.get("question_ids") or [])
    correct = 0
    for i, q in enumerate(qs):
        if i < len(body.answers) and body.answers[i] == q["correct"]:
            correct += 1
    secs = max(0, int(body.time_ms) // 1000)
    speed_bonus = max(0, 100 - secs) if correct else 0
    score = correct * 100 + speed_bonus
    entry = {"score": score, "correct": correct, "time_ms": int(body.time_ms),
             "at": _now(), "at_ts": _now().timestamp()}
    await db.game_challenges.update_one(
        {"_id": cid},
        {"$set": {f"scores.{uid}": entry}, "$addToSet": {"submitted": uid}})
    # Feed the leaderboard.
    await _record_score(db, uid, doc["game_key"], score, source="challenge", ref=cid)
    doc = await db.game_challenges.find_one({"_id": cid})
    finalized = False
    parts = set(doc.get("participants") or [])
    sub = set(doc.get("submitted") or [])
    pending_invites = doc.get("invitees") or []
    if not pending_invites and len(parts) >= 2 and sub >= parts:
        doc = await _finalize(db, doc)
        finalized = True
    umap = await _load_umap(db, doc)
    return {"score": score, "correct": correct, "total": len(qs),
            "finalized": finalized, "challenge": _challenge_public(doc, uid, umap)}


@router.post("/challenges/{cid}/complete")
async def complete_challenge(cid: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    doc = await db.game_challenges.find_one({"_id": cid})
    if not doc:
        raise HTTPException(404, {"code": "not_found"})
    if doc["host_id"] != uid:
        raise HTTPException(403, {"code": "host_only"})
    if doc.get("status") != "active":
        raise HTTPException(409, {"code": "already_done"})
    if not (doc.get("scores") or {}):
        raise HTTPException(400, {"code": "no_scores_yet"})
    doc = await _finalize(db, doc)
    umap = await _load_umap(db, doc)
    return _challenge_public(doc, uid, umap)


# ───────────────────────── leaderboard ───────────────────────────────
async def _record_score(db, uid: str, game_key: str, score: int,
                         *, source: str = "play", ref: Optional[str] = None) -> None:
    await db.game_scores.insert_one({
        "_id": f"gs_{uuid.uuid4().hex[:16]}", "user_id": uid,
        "game_key": game_key, "score": int(score), "week": _week_key(),
        "source": source, "ref": ref, "created_at": _now()})


@router.post("/score")
async def submit_score(body: ScoreBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    score = max(0, int(body.score))
    await _record_score(db, user["user_id"], (body.game_key or "misc").strip(), score)
    return {"ok": True}


@router.get("/leaderboard")
async def leaderboard(request: Request, scope: str = "global",
                      game_key: str = "all", period: Optional[str] = None,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    week = period or _week_key()
    match: dict = {"week": week}
    if game_key and game_key != "all":
        match["game_key"] = game_key
    if scope == "friends":
        friends = await _friend_ids(db, uid)
        match["user_id"] = {"$in": list(friends) + [uid]}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$user_id", "score": {"$sum": "$score"},
                    "plays": {"$sum": 1}}},
        {"$sort": {"score": -1, "plays": -1}},
    ]
    rows = [r async for r in db.game_scores.aggregate(pipeline)]
    umap = await _users_map(db, [r["_id"] for r in rows])
    items = []
    me = None
    for rank, r in enumerate(rows, start=1):
        row = {"rank": rank, "user": umap.get(r["_id"]),
               "score": r["score"], "plays": r["plays"],
               "is_me": r["_id"] == uid}
        if r["_id"] == uid:
            me = row
        if rank <= 50:
            items.append(row)
    return {"items": items, "me": me, "week": week,
            "scope": scope, "game_key": game_key}
