"""FUUSIC — Daily Readings (Horoscope / Tarot / Numerology / Fortune).

PRIVATE by design: a generated reading is only ever shown on the owner's own
feed (`/api/social/my-readings` + a READING card injected only for that user).
All content is AI-generated cultural entertainment + reflection, clearly
labelled, with the approved disclaimer. Cached per (user, type, date) — never
regenerated on refresh. Sensitive prompts never appear in public feed metadata.
"""
from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user

router = APIRouter(prefix="/api/social", tags=["daily-readings"])

TYPES = {"horoscope", "tarot", "numerology", "fortune"}
FREQS = {"daily", "weekly", "off"}
DISCLAIMER = ("AI-generated interpretation for entertainment, cultural tradition "
              "and personal reflection — not a prediction or professional advice.")
TAROT_CARDS = ["The Star", "The Sun", "The Moon", "The Empress", "The Lovers",
               "The World", "Strength", "Wheel of Fortune", "The Magician", "Temperance"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    if isinstance(v, datetime):
        return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).isoformat()
    return v


def _title(rt: str, extra: dict) -> str:
    if rt == "horoscope":
        return f"Your Daily Horoscope{(' — ' + extra['sign']) if extra.get('sign') else ''}"
    if rt == "tarot":
        return "Your Daily Tarot"
    if rt == "numerology":
        return "Your Numerology Number"
    return "Today's Reflection"


def _fallback(rt: str, extra: dict) -> dict:
    if rt == "tarot":
        card = random.choice(TAROT_CARDS)
        return {"headline": f"Today's Card: {card}", "card": card,
                "body": (f"{card} invites you to lead with openness today. Notice where "
                         "a small act of courage or kindness shifts the mood around you.")}
    if rt == "numerology":
        n = random.randint(1, 9)
        return {"headline": f"Your number today is {n}", "number": n,
                "body": (f"The energy of {n} favours steady, intentional steps. Keep one "
                         "promise to yourself and let momentum build.")}
    if rt == "horoscope":
        return {"headline": extra.get("sign") or "Today's reflection",
                "body": ("A good day to listen before you decide. A conversation you've "
                         "been avoiding may open a door — approach it with curiosity.")}
    return {"headline": "A thought for today",
            "body": ("Progress hides in the ordinary. Do the next small thing well and let "
                     "the rest follow.")}


async def _generate(rt: str, extra: dict) -> dict:
    """LLM-generated reading with a graceful templated fallback."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return _fallback(rt, extra)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        sign = extra.get("sign")
        ask = {
            "horoscope": f"Write a short daily horoscope ({'for ' + sign if sign else 'a general sign-neutral reflection'}).",
            "tarot": "Draw ONE tarot card and give a short daily reflection. Start with the card name.",
            "numerology": "Give a single-digit numerology number for today and a short reflection. Start with the number.",
            "fortune": "Write a short uplifting daily fortune / reflection.",
        }[rt]
        chat = LlmChat(
            api_key=key, session_id=f"reading_{rt}_{_now().date().isoformat()}",
            system_message=("You write warm, concise daily readings as cultural "
                            "entertainment and reflection (2-3 sentences). Never promise "
                            "guaranteed outcomes, medical, financial or relationship "
                            "certainty. No markdown."),
        ).with_model("anthropic", "claude-sonnet-4-6")
        raw = await asyncio.wait_for(chat.send_message(UserMessage(text=ask)), timeout=14)
        body = (raw if isinstance(raw, str) else str(raw)).strip()
        if not body:
            return _fallback(rt, extra)
        out = {"body": body[:600]}
        if rt == "tarot":
            out["card"] = next((c for c in TAROT_CARDS if c.lower() in body.lower()), body.split(".")[0][:40])
            out["headline"] = f"Today's Card: {out['card']}"
        elif rt == "numerology":
            nums = [int(ch) for ch in body if ch.isdigit()]
            out["number"] = nums[0] if nums else random.randint(1, 9)
            out["headline"] = f"Your number today is {out['number']}"
        else:
            out["headline"] = extra.get("sign") or "Today's reflection"
        return out
    except Exception:
        return _fallback(rt, extra)


def _due(sub: dict) -> bool:
    freq = sub.get("frequency")
    if freq == "off" or not sub.get("enabled"):
        return False
    last = sub.get("last_generated_at")
    if not last:
        return True
    last_dt = last if isinstance(last, datetime) else _now() - timedelta(days=99)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    gap = (_now() - last_dt).total_seconds()
    return gap >= (6.5 * 86400 if freq == "weekly" else 20 * 3600)


async def _ensure_today(db, uid: str) -> list[dict]:
    """Generate (and cache) readings for every enabled+due subscription."""
    today = _now().date().isoformat()
    made = []
    async for sub in db.daily_reading_subscriptions.find({"user_id": uid, "enabled": True}):
        rt = sub.get("reading_type")
        if rt not in TYPES or not _due(sub):
            continue
        _id = f"dr_{uid}_{rt}_{today}"
        if await db.daily_readings.find_one({"_id": _id}):
            continue
        extra = {"sign": sub.get("sign"), "system": sub.get("system")}
        gen = await _generate(rt, extra)
        doc = {"_id": _id, "user_id": uid, "reading_type": rt, "date": today,
               "title": _title(rt, extra), "headline": gen.get("headline"),
               "body": gen.get("body"), "card": gen.get("card"),
               "number": gen.get("number"), "sign": sub.get("sign"),
               "system": sub.get("system"), "ai_generated": True,
               "disclaimer": DISCLAIMER, "created_at": _now()}
        await db.daily_readings.update_one({"_id": _id}, {"$set": doc}, upsert=True)
        await db.daily_reading_subscriptions.update_one(
            {"_id": sub["_id"]}, {"$set": {"last_generated_at": _now()}})
        made.append(doc)
    return made


def _sub_public(s: dict) -> dict:
    return {"reading_type": s.get("reading_type"), "enabled": bool(s.get("enabled")),
            "frequency": s.get("frequency", "daily"), "sign": s.get("sign"),
            "system": s.get("system"), "timezone": s.get("timezone")}


def _reading_public(r: dict) -> dict:
    return {"id": r["_id"], "reading_type": r.get("reading_type"), "date": r.get("date"),
            "title": r.get("title"), "headline": r.get("headline"), "body": r.get("body"),
            "card": r.get("card"), "number": r.get("number"), "sign": r.get("sign"),
            "disclaimer": r.get("disclaimer"), "created_at": _iso(r.get("created_at"))}


@router.get("/daily-readings")
async def get_daily_readings(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    await _ensure_today(db, uid)
    subs = [_sub_public(s) async for s in
            db.daily_reading_subscriptions.find({"user_id": uid})]
    sub_types = {s["reading_type"] for s in subs}
    for rt in TYPES:
        if rt not in sub_types:
            subs.append({"reading_type": rt, "enabled": False, "frequency": "off",
                         "sign": None, "system": None, "timezone": None})
    today = _now().date().isoformat()
    todays = [_reading_public(r) async for r in
              db.daily_readings.find({"user_id": uid, "date": today})]
    return {"subscriptions": subs, "today": todays, "disclaimer": DISCLAIMER}


class SubBody(BaseModel):
    enabled: bool = True
    frequency: str = Field("daily", max_length=10)
    sign: str | None = Field(None, max_length=20)
    system: str | None = Field(None, max_length=30)
    timezone: str | None = Field(None, max_length=60)


@router.put("/daily-readings/{reading_type}")
async def set_subscription(reading_type: str, body: SubBody, request: Request,
                           user: dict = Depends(current_user)):
    if reading_type not in TYPES:
        raise HTTPException(400, {"code": "bad_type"})
    freq = body.frequency if body.frequency in FREQS else "daily"
    db = request.app.state.db
    uid = user["user_id"]
    await db.daily_reading_subscriptions.update_one(
        {"user_id": uid, "reading_type": reading_type},
        {"$set": {"user_id": uid, "reading_type": reading_type,
                  "enabled": bool(body.enabled) and freq != "off", "frequency": freq,
                  "sign": body.sign, "system": body.system,
                  "timezone": body.timezone, "updated_at": _now()},
         "$setOnInsert": {"created_at": _now()}}, upsert=True)
    # Generate immediately so the card appears right away.
    made = await _ensure_today(db, uid)
    return {"ok": True, "generated": [_reading_public(m) for m in made]}


@router.get("/my-readings")
async def my_readings(request: Request, limit: int = 30,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    await _ensure_today(db, uid)
    out = [_reading_public(r) async for r in
           db.daily_readings.find({"user_id": uid}).sort("created_at", -1).limit(min(limit, 60))]
    return {"count": len(out), "readings": out, "disclaimer": DISCLAIMER}
