"""RadioLife Social V2 — AI READINGS (horoscope · tarot · numerology).

Entertainment / reflection only — clearly labelled AI-GENERATED, never
medical / legal / financial advice, no guaranteed prediction. Deterministic
inputs (zodiac sign, drawn cards, life-path number) are computed server-side;
the Emergent LLM key (Claude Sonnet 4.6) writes the narrative. Birth data is
privacy-first: only the derived value (sign / number) is persisted, never the
raw date of birth.

All routes: /api/social/readings/*
"""
from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user

router = APIRouter(prefix="/api/social/readings", tags=["ai_readings"])

READING_LABEL = "AI-GENERATED · for entertainment & reflection only"
DISCLAIMER = (
    "AI-generated for entertainment and reflection only. Not medical, "
    "mental-health, legal or financial advice, and not a guaranteed prediction.")

TYPES = ["horoscope", "tarot", "numerology"]
TIMEFRAMES = ["today", "week", "month"]
SPREADS = {"one": 1, "three": 3}

ZODIAC = [
    ("Capricorn", (12, 22), (1, 19)), ("Aquarius", (1, 20), (2, 18)),
    ("Pisces", (2, 19), (3, 20)), ("Aries", (3, 21), (4, 19)),
    ("Taurus", (4, 20), (5, 20)), ("Gemini", (5, 21), (6, 20)),
    ("Cancer", (6, 21), (7, 22)), ("Leo", (7, 23), (8, 22)),
    ("Virgo", (8, 23), (9, 22)), ("Libra", (9, 23), (10, 22)),
    ("Scorpio", (10, 23), (11, 21)), ("Sagittarius", (11, 22), (12, 21)),
]
ZODIAC_SIGNS = [z[0] for z in ZODIAC]

MAJOR_ARCANA = [
    "The Fool", "The Magician", "The High Priestess", "The Empress",
    "The Emperor", "The Hierophant", "The Lovers", "The Chariot", "Strength",
    "The Hermit", "Wheel of Fortune", "Justice", "The Hanged Man", "Death",
    "Temperance", "The Devil", "The Tower", "The Star", "The Moon", "The Sun",
    "Judgement", "The World",
]

LIFE_PATH_MEANING = {
    1: "The Leader", 2: "The Peacemaker", 3: "The Communicator",
    4: "The Builder", 5: "The Explorer", 6: "The Nurturer", 7: "The Seeker",
    8: "The Powerhouse", 9: "The Humanitarian", 11: "The Intuitive (Master)",
    22: "The Master Builder", 33: "The Master Teacher",
}

_SYSTEM = (
    "You are a warm, imaginative guide writing SHORT entertainment readings "
    "(horoscope, tarot, numerology) for a social app. Rules you MUST follow: "
    "(1) Keep it uplifting, gentle and non-deterministic — use 'may', 'might', "
    "'one interpretation'. (2) NEVER predict health, death, pregnancy, lawsuits, "
    "money outcomes or exact events. (3) NEVER give medical, legal, financial or "
    "mental-health advice; if the user seems distressed, gently suggest talking "
    "to someone they trust or a licensed professional. (4) Return ONLY compact "
    "JSON, no markdown. Schema: "
    '{"headline": str, "summary": str, "themes": [str,str,str], '
    '"guidance": [str,str], "affirmation": str}')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


def _sign_from_dob(dob: str) -> Optional[str]:
    try:
        parts = [int(x) for x in dob.replace("/", "-").split("-")]
        if len(parts) != 3:
            return None
        # accept YYYY-MM-DD or DD-MM-YYYY
        if parts[0] > 31:
            _, m, day = parts
        else:
            day, m, _ = parts
        for name, (sm, sd), (em, ed) in ZODIAC:
            if (m == sm and day >= sd) or (m == em and day <= ed):
                return name
        return None
    except Exception:
        return None


def _life_path(dob: str) -> Optional[int]:
    digits = [int(c) for c in dob if c.isdigit()]
    if len(digits) < 6:
        return None
    total = sum(digits)
    while total > 9 and total not in (11, 22, 33):
        total = sum(int(c) for c in str(total))
    return total


async def _generate(system: str, prompt: str, session: str) -> Optional[dict]:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=session,
                       system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        raw = await chat.send_message(UserMessage(text=prompt))
        s = raw if isinstance(raw, str) else str(raw)
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1:
            return json.loads(s[a:b + 1])
    except Exception:
        return None
    return None


def _fallback(kind: str, subject: str) -> dict:
    return {
        "headline": f"A gentle {kind} for {subject}",
        "summary": ("One playful interpretation: today invites a small, kind step "
                    "toward something you've been thinking about. Nothing here is "
                    "fixed — you always hold the pen."),
        "themes": ["reflection", "balance", "curiosity"],
        "guidance": ["Notice what gives you energy today.",
                     "Let one worry rest for a moment."],
        "affirmation": "I move at my own pace, with curiosity and care.",
    }


def _reading_public(r: dict) -> dict:
    return {"reading_id": r["_id"], "type": r.get("type"),
            "subject": r.get("subject"), "title": r.get("title"),
            "result": r.get("result"), "cards": r.get("cards"),
            "public": bool(r.get("public")),
            "label": READING_LABEL, "disclaimer": DISCLAIMER,
            "created_at": _iso(r.get("created_at"))}


async def ensure_ai_readings_indexes(db) -> None:
    await db.ai_readings.create_index([("user_id", 1), ("created_at", -1)], name="air_mine")
    await db.ai_readings.create_index("reading_id", unique=True, name="air_id")


# ───────────────────────────── Config ──────────────────────────────
@router.get("/config")
async def config(request: Request, user: dict = Depends(current_user)):
    return {
        "types": TYPES, "timeframes": TIMEFRAMES,
        "zodiac_signs": ZODIAC_SIGNS,
        "spreads": [{"key": k, "cards": v} for k, v in SPREADS.items()],
        "label": READING_LABEL, "disclaimer": DISCLAIMER,
    }


async def _save(db, uid: str, kind: str, subject: str, title: str,
                result: dict, cards=None) -> dict:
    rid = f"air_{uuid.uuid4().hex[:16]}"
    doc = {"_id": rid, "reading_id": rid, "user_id": uid, "type": kind,
           "subject": subject, "title": title, "result": result,
           "cards": cards, "public": False, "created_at": _now()}
    await db.ai_readings.insert_one(doc)
    return _reading_public(doc)


class HoroscopeBody(BaseModel):
    sign: Optional[str] = None
    dob: Optional[str] = None
    timeframe: str = "today"


@router.post("/horoscope")
async def horoscope(body: HoroscopeBody, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    sign = body.sign if body.sign in ZODIAC_SIGNS else (
        _sign_from_dob(body.dob) if body.dob else None)
    if not sign:
        raise HTTPException(400, {"code": "sign_required"})
    tf = body.timeframe if body.timeframe in TIMEFRAMES else "today"
    result = await _generate(
        _SYSTEM,
        f"Write a {tf} horoscope for {sign}. Keep it warm and non-deterministic.",
        f"horo_{user['user_id']}_{uuid.uuid4().hex[:6]}")
    if not result:
        result = _fallback("horoscope", sign)
    title = f"{sign} — {tf.capitalize()} horoscope"
    return await _save(db, user["user_id"], "horoscope", sign, title, result)


class TarotBody(BaseModel):
    question: Optional[str] = Field(None, max_length=300)
    spread: str = "three"


@router.post("/tarot")
async def tarot(body: TarotBody, request: Request,
                user: dict = Depends(current_user)):
    db = request.app.state.db
    n = SPREADS.get(body.spread, 3)
    positions = (["Present"] if n == 1 else ["Past", "Present", "Future"])
    picks = random.sample(MAJOR_ARCANA, n)
    cards = [{"name": name, "orientation": random.choice(["upright", "reversed"]),
              "position": positions[i]} for i, name in enumerate(picks)]
    card_txt = "; ".join(f"{c['position']}: {c['name']} ({c['orientation']})" for c in cards)
    q = (body.question or "").strip()
    result = await _generate(
        _SYSTEM,
        f"Interpret this tarot draw as gentle entertainment. Cards — {card_txt}. "
        + (f"The person asked: '{q}'. " if q else "")
        + "Give one uplifting, non-deterministic reading.",
        f"tarot_{user['user_id']}_{uuid.uuid4().hex[:6]}")
    if not result:
        result = _fallback("tarot", "you")
    title = "Tarot — " + (f"{n}-card spread" if n > 1 else "single card")
    return await _save(db, user["user_id"], "tarot",
                       q or "General reading", title, result, cards=cards)


class NumerologyBody(BaseModel):
    full_name: Optional[str] = Field(None, max_length=120)
    dob: str = Field(..., min_length=6, max_length=20)


@router.post("/numerology")
async def numerology(body: NumerologyBody, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    lp = _life_path(body.dob)
    if lp is None:
        raise HTTPException(400, {"code": "bad_dob"})
    meaning = LIFE_PATH_MEANING.get(lp, "A unique path")
    name = (body.full_name or "").strip()
    result = await _generate(
        _SYSTEM,
        f"Write a numerology reading for Life Path number {lp} ({meaning}). "
        + (f"Name given: {name}. " if name else "")
        + "Explain the number's themes warmly, as entertainment.",
        f"num_{user['user_id']}_{uuid.uuid4().hex[:6]}")
    if not result:
        result = _fallback("numerology", f"Life Path {lp}")
    result["life_path"] = lp
    result["life_path_meaning"] = meaning
    title = f"Life Path {lp} — {meaning}"
    return await _save(db, user["user_id"], "numerology", f"Life Path {lp}", title, result)


# ───────────────────────────── History ─────────────────────────────
@router.get("")
async def my_readings(request: Request, kind: Optional[str] = None,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    q: dict = {"user_id": user["user_id"]}
    if kind in TYPES:
        q["type"] = kind
    items = [_reading_public(r) async for r in
             db.ai_readings.find(q).sort("created_at", -1).limit(50)]
    return {"items": items}


@router.get("/{reading_id}")
async def get_reading(reading_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.ai_readings.find_one({"reading_id": reading_id})
    if not r or (r["user_id"] != user["user_id"] and not r.get("public")):
        raise HTTPException(404, {"code": "reading_not_found"})
    return _reading_public(r)


class ShareBody(BaseModel):
    public: bool = True


@router.post("/{reading_id}/share")
async def share_reading(reading_id: str, body: ShareBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.ai_readings.find_one(
        {"reading_id": reading_id, "user_id": user["user_id"]})
    if not r:
        raise HTTPException(404, {"code": "reading_not_found"})
    await db.ai_readings.update_one({"reading_id": reading_id},
                                    {"$set": {"public": bool(body.public)}})
    return {"ok": True, "public": bool(body.public)}


@router.delete("/{reading_id}")
async def delete_reading(reading_id: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    res = await db.ai_readings.delete_one(
        {"reading_id": reading_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, {"code": "reading_not_found"})
    return {"ok": True}


__all__ = ["router", "ensure_ai_readings_indexes"]
