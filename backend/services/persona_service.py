"""Phase 39 Session 2 — Persona service helpers.

Thin wrappers around the persona collection that keep route handlers
clean.  Three responsibilities:

  1. `get_safe_persona(db, persona_id)` — single-row lookup with
      classifier guard.  Returns None if missing, not active, or
      `safety_classification.is_safe != True`.  Centralising this means
      every endpoint that accepts a persona_id from the client (select,
      chat, library detail) is guarded by the same predicate.
  2. `resolve_active_persona(db, user, daypart)` — chooses which persona
      the AI RJ should embody right now.  Prefers `user.selected_persona_id`
      when present + safe; otherwise falls back to a daypart-matched
      launch persona; otherwise to the first launch persona by id.
  3. `list_launch_personas_for_listener(db)` — returns the 10 launch
      personas shaped for the GET /api/personas/library endpoint
      (sample_clip_url + signed if Tigris-backed).
"""
from __future__ import annotations
import logging
import os
from typing import Optional

log = logging.getLogger("bigfm.persona_service")

# Public projection — what listeners see.  No raw internal fields like
# `safety_classification.evidence` or `voice_clone_reference_url`.
LISTENER_PROJECTION = {
    "persona_id": 1, "display_name": 1, "archetype": 1,
    "description": 1, "language_mix": 1, "daypart_affinity": 1,
    "signature_phrases": 1, "voice_id": 1, "voice_key": 1,
    "sample_clip_url": 1, "sample_clip_storage_key": 1,
    "sample_clip_script": 1, "is_premium": 1, "is_launch_persona": 1,
    "safety_classification": 1, "active": 1,
}


def _signed_url_for_clip(storage_key: Optional[str],
                                                  fallback_url: Optional[str]) -> Optional[str]:
    """If the clip is Tigris-backed, generate a 1-hour signed URL.  For
    local-disk personas (dev mode) just return whatever URL the seed
    captured."""
    if not storage_key:
        return fallback_url
    try:
        from services.object_storage import get_storage
        return get_storage().get_signed_url(key=storage_key, expires_in=3600)
    except Exception as e:
        log.warning("[persona_service] signed-url failed for %s: %s",
                              storage_key, e)
        return fallback_url


def _shape_listener_row(doc: dict) -> dict:
    return {
        "persona_id":              doc.get("persona_id") or doc.get("_id"),
        "display_name":          doc.get("display_name") or doc.get("name"),
        "archetype":                doc.get("archetype"),
        "description":            doc.get("description"),
        "language_mix":          doc.get("language_mix") or [],
        "daypart_affinity":  doc.get("daypart_affinity") or [],
        "signature_phrases_preview":
            (doc.get("signature_phrases") or [])[:3],
        "sample_clip_url":      _signed_url_for_clip(
                                                  doc.get("sample_clip_storage_key"),
                                                  doc.get("sample_clip_url")),
        "is_premium":              bool(doc.get("is_premium")),
    }


async def get_safe_persona(db, persona_id: Optional[str]) -> Optional[dict]:
    if not persona_id:
        return None
    doc = await db.rj_personality_profiles.find_one({"_id": persona_id})
    if not doc:
        return None
    if not doc.get("active", True):
        return None
    sc = doc.get("safety_classification") or {}
    if sc.get("is_safe") is not True:
        log.warning("[persona_service] blocked unsafe persona request: %s "
                              "flags=%s", persona_id, sc.get("flags"))
        return None
    return doc


async def list_launch_personas_for_listener(db) -> list[dict]:
    """Listener-facing library.  Always filters by `is_safe=True` so a
    persona that fails a later classifier update is invisible."""
    out: list[dict] = []
    async for doc in db.rj_personality_profiles.find(
        {"is_launch_persona": True, "active": True,
          "safety_classification.is_safe": True},
        projection=LISTENER_PROJECTION).sort("persona_id", 1):
        out.append(_shape_listener_row(doc))
    return out


def _daypart_for_hour(hour: int) -> str:
    if 4 <= hour < 7:    return "early_morning"
    if 7 <= hour < 11:  return "morning_drive"
    if 11 <= hour < 14: return "lunch"
    if 14 <= hour < 17: return "afternoon"
    if 17 <= hour < 20: return "evening_drive"
    if 20 <= hour < 23: return "nightlife"
    return "late_night"


async def resolve_active_persona(db, user: dict,
                                                                  daypart: Optional[str] = None) -> Optional[dict]:
    """Pick the persona to embody for this listener.  Priority:
        1. user.selected_persona_id (if safe + active)
        2. first launch persona matching `daypart`
        3. first launch persona by id
    """
    if user and user.get("selected_persona_id"):
        p = await get_safe_persona(db, user["selected_persona_id"])
        if p:
            return p
    # daypart match
    query = {"is_launch_persona": True, "active": True,
                  "safety_classification.is_safe": True}
    if daypart:
        query["daypart_affinity"] = daypart
    doc = await db.rj_personality_profiles.find_one(query,
                                                                                              sort=[("persona_id", 1)])
    if doc:
        return doc
    # final fallback — any safe launch persona
    return await db.rj_personality_profiles.find_one({
        "is_launch_persona": True, "active": True,
        "safety_classification.is_safe": True})


def build_persona_chat_prompt(persona: dict, listener_input: str) -> str:
    """Compose the LLM prompt used by /api/personas/chat.  Persona's
    archetype + language_mix + signature_phrases inform the style,
    while listener_input is the actual question.  Kept deliberately
    short so gpt-4o-mini can fit the response in 25-30 seconds of TTS."""
    name = persona.get("display_name") or persona.get("name") or "the host"
    archetype = persona.get("archetype") or ""
    desc      = persona.get("description") or ""
    phrases  = ", ".join(persona.get("signature_phrases") or [])
    langs    = ", ".join(persona.get("language_mix") or ["English"])
    return (
        f"You are {name}, a RadioLife radio persona.  Archetype: {archetype}.\n"
        f"Style: {desc}\n"
        f"Language mix: {langs}.  Use natural code-switching, not "
        f"forced.  Sprinkle catchphrases occasionally: {phrases}\n\n"
        f"A listener just said: \"{listener_input}\"\n\n"
        f"Respond in 2-4 short sentences (max ~25 seconds when spoken "
        f"aloud).  Stay in character.  Do NOT mention you are an AI "
        f"or a language model.  Do NOT imitate any real public figure."
    )
