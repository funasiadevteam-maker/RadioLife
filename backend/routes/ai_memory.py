"""Phase 39 Session 7 — AI Memory Summary.

A natural-language paragraph the listener can read to understand what the
system has learned about them. Builds trust + drives consent uptake.

Cached in `users.ai_memory_summary` with `ai_memory_summary_built_at` —
24h TTL.  Privacy guard: when consent<3, summary omits place/pattern
details (only persona + city).
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import OpenAI

from auth import current_user

router = APIRouter(prefix="/api/personas", tags=["personas-memory"])
log = logging.getLogger("bigfm.ai_memory")

CACHE_TTL_HOURS = 24
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
_openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def _now(): return datetime.now(timezone.utc)


async def _build_summary_text(db, user: dict) -> str:
    consent = int(user.get("location_consent_level", 0))
    persona_id = user.get("selected_persona_id")
    persona_name = "FUUSIC's default RJ"
    if persona_id:
        p = await db.rj_personality_profiles.find_one({"_id": persona_id})
        if p:
            persona_name = p.get("display_name") or p.get("name") or persona_name

    facts: list[str] = [f"User's chosen AI RJ: {persona_name}."]
    facts.append(f"User's market: {user.get('city') or 'Dubai'}.")
    place_count = pattern_count = 0
    morning_dest: Optional[str] = None
    recent_bv: Optional[dict] = None
    if consent >= 3:
        place_count = await db.UserFrequentPlaces.count_documents(
            {"user_id": user["user_id"], "user_hidden": {"$ne": True}})
        pattern_count = await db.UserRoutePatterns.count_documents(
            {"user_id": user["user_id"]})
        pat = await db.UserRoutePatterns.find_one(
            {"user_id": user["user_id"], "dominant_time_bucket": "morning"},
            sort=[("repeat_count", -1)])
        if pat and pat.get("destination_place_id"):
            d = await db.UserFrequentPlaces.find_one(
                {"user_id": user["user_id"],
                 "place_id": pat["destination_place_id"]})
            if d:
                morning_dest = d.get("label")
        bv = await db.UserBusinessVisits.find_one(
            {"user_id": user["user_id"]},
            sort=[("visited_at", -1)])
        if bv:
            recent_bv = {"label": bv.get("label"),
                         "category": bv.get("category"),
                         "bucket": bv.get("time_bucket")}
        facts.append(f"Detected frequent places (with consent): {place_count}.")
        facts.append(f"Detected route patterns: {pattern_count}.")
        if morning_dest:
            facts.append(f"Typical morning destination: {morning_dest}.")
        if recent_bv:
            facts.append(f"Most recent place visit: {recent_bv['label']} "
                         f"({recent_bv['category']}) in the {recent_bv['bucket']} bucket.")
    else:
        facts.append("Location intelligence is OFF for this user (consent<3) — "
                     "summary mentions only persona and city.")

    if not _openai:
        # Deterministic fallback when OpenAI key missing.
        return ("Your AI RJ — " + persona_name + " — is set. " +
                ("We have not learned your places or routes." if consent < 3
                 else f"You have {place_count} detected places "
                      f"and {pattern_count} repeating route(s)."))

    system_prompt = (
        "You write SHORT, warm, second-person summaries (2-4 sentences) of "
        "what a personalized radio platform has learned about a listener. "
        "Speak to them directly ('You usually...'). NEVER name a clock time — "
        "use only buckets (morning/lunch/evening/night). NEVER list raw "
        "coordinates. If location intelligence is off, only mention persona "
        "and city. Keep it friendly, not creepy.")
    user_prompt = "Facts about this listener:\n- " + "\n- ".join(facts)
    try:
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.7, max_tokens=180,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or "Your AI RJ is ready. Tune in to FUUSIC."
    except Exception as e:
        log.warning("[ai-memory] OpenAI fallback: %s", e)
        return ("Your AI RJ — " + persona_name + " — is set. " +
                ("We have not learned your places or routes." if consent < 3
                 else f"You have {place_count} detected place(s) and "
                      f"{pattern_count} route pattern(s)."))


@router.get("/memory_summary")
async def get_memory_summary(request: Request,
                             user: dict = Depends(current_user)):
    db = request.app.state.db
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    cached_at = fresh.get("ai_memory_summary_built_at")
    cached_text = fresh.get("ai_memory_summary")
    if cached_at and cached_text:
        try:
            built = datetime.fromisoformat(cached_at) if isinstance(
                cached_at, str) else cached_at
            if built.tzinfo is None:
                built = built.replace(tzinfo=timezone.utc)
            if _now() - built < timedelta(hours=CACHE_TTL_HOURS):
                return {
                    "summary_text":    cached_text,
                    "selected_persona": fresh.get("selected_persona_id"),
                    "frequent_places_count": fresh.get(
                        "ai_memory_places_count", 0),
                    "route_patterns_count":  fresh.get(
                        "ai_memory_patterns_count", 0),
                    "cached": True,
                    "built_at": cached_at,
                }
        except Exception:
            pass

    consent = int(fresh.get("location_consent_level", 0))
    place_count = pattern_count = 0
    if consent >= 3:
        place_count = await db.UserFrequentPlaces.count_documents(
            {"user_id": user["user_id"], "user_hidden": {"$ne": True}})
        pattern_count = await db.UserRoutePatterns.count_documents(
            {"user_id": user["user_id"]})

    summary_text = await _build_summary_text(db, fresh)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "ai_memory_summary":              summary_text,
            "ai_memory_summary_built_at": _now().isoformat(),
            "ai_memory_places_count":     place_count,
            "ai_memory_patterns_count":  pattern_count,
        }})
    return {
        "summary_text":             summary_text,
        "selected_persona":      fresh.get("selected_persona_id"),
        "frequent_places_count": place_count,
        "route_patterns_count":  pattern_count,
        "cached":                       False,
        "built_at":                  _now().isoformat(),
    }


@router.post("/memory_summary/forget")
async def forget_summary(request: Request,
                         user: dict = Depends(current_user)):
    """Invalidates the cached AI memory summary.  Use after consent changes."""
    db = request.app.state.db
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$unset": {"ai_memory_summary": "",
                    "ai_memory_summary_built_at": ""}})
    return {"ok": True}
