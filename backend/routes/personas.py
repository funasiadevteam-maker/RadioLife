"""Phase 39 Session 2 — Persona library, selection, chat, admin re-classify.

All persona-related listener + admin HTTP routes live here.  Routes:

  • GET  /api/personas/library             — listener: 10 launch personas
  • GET  /api/personas/me                    — listener: currently-selected persona (or daypart suggestion)
  • POST /api/personas/select                — listener: persist selection
  • POST /api/personas/chat                  — listener: push-to-talk (text in → text+audio out)
  • POST /api/admin/personas/reclassify_all — admin: re-run classifier on all personas

Every persona_id received from the client is validated via
`services.persona_service.get_safe_persona` BEFORE use — single guard
point, can't be bypassed.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services.persona_service import (LISTENER_PROJECTION,
                                                                          _signed_url_for_clip,
                                                                          _shape_listener_row,
                                                                          build_persona_chat_prompt,
                                                                          get_safe_persona,
                                                                          list_launch_personas_for_listener,
                                                                          resolve_active_persona)

router = APIRouter(prefix="/api", tags=["personas"])
log = logging.getLogger("bigfm.personas")

RJ_STORAGE_DIR = Path(os.environ.get("BIGFM_RJ_STORAGE_DIR")
                                          or "/app/backend/storage/rj")


# ─── request bodies ──────────────────────────────────────────────────
class SelectPersonaIn(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=128)


class ChatPersonaIn(BaseModel):
    persona_id:                str = Field(..., min_length=1, max_length=128)
    listener_input_text: str = Field(..., min_length=1, max_length=2000)


class PersonaSettingsIn(BaseModel):
    humor:  int = Field(..., ge=0, le=10)
    energy: int = Field(..., ge=0, le=10)
    slang:  int = Field(..., ge=0, le=10)


# Phase 39 Session 3 — premium-gated persona settings sliders.
@router.post("/personas/settings")
async def personas_settings(body: PersonaSettingsIn, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    from services.premium_gate import is_premium_or_trial
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    if not is_premium_or_trial(fresh):
        raise HTTPException(403, {"code": "premium_required",
                                                      "message": "Persona sliders require Premium or an active 7-day trial."})
    now_iso = datetime.now(timezone.utc).isoformat()
    settings = {"humor":  body.humor,
                          "energy": body.energy,
                          "slang":  body.slang,
                          "updated_at": now_iso}
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"persona_settings": settings}})
    return {"ok": True, "persona_settings": settings}


# ─── library ────────────────────────────────────────────────────────
@router.get("/personas/library")
async def get_personas_library(request: Request,
                                                              user: dict = Depends(current_user)):
    rows = await list_launch_personas_for_listener(request.app.state.db)
    return {"personas": rows, "count": len(rows)}


@router.get("/personas/me")
async def get_my_persona(request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    persona = await resolve_active_persona(db, user)
    if not persona:
        return {"persona": None,
                      "selected_persona_id": None,
                      "source": "no_personas_available"}
    source = ("user_selected"
                      if user.get("selected_persona_id") == persona.get("_id")
                      else "daypart_default")
    return {"persona": _shape_listener_row(persona),
                  "selected_persona_id": user.get("selected_persona_id"),
                  "source": source}


@router.post("/personas/select")
async def select_persona(body: SelectPersonaIn, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    persona = await get_safe_persona(db, body.persona_id)
    if not persona:
        raise HTTPException(400, {"code": "persona_unavailable",
                                                      "persona_id": body.persona_id})
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"selected_persona_id": persona["_id"],
                            "selected_persona_at":
                                datetime.now(timezone.utc).isoformat()}})
    return {"ok": True,
                  "selected_persona_id": persona["_id"],
                  "persona": _shape_listener_row(persona)}


# ─── chat ───────────────────────────────────────────────────────────
async def _llm_chat_reply(persona: dict, listener_input: str,
                                                    user: Optional[dict] = None) -> str:
    """Call gpt-4o-mini with the persona-styled prompt + (optionally) the
    user's persona-settings sliders applied as style directives."""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return _fallback_reply(persona)
    try:
        from openai import OpenAI
        from services.premium_gate import (apply_settings_to_prompt,
                                                                                  is_premium_or_trial)
        client = OpenAI(api_key=api_key)
        prompt = build_persona_chat_prompt(persona, listener_input)
        # Slider directives only apply when user is premium-or-trial.
        if user and is_premium_or_trial(user):
            prompt = apply_settings_to_prompt(prompt,
                                                                                  user.get("persona_settings"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system",
                                  "content": "You are a BigFM radio host. Stay in character. "
                                                      "Reply in 2-4 short sentences. Never break character."},
                                  {"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=180,
            timeout=20,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or _fallback_reply(persona)
    except Exception as e:
        log.warning("[personas.chat] llm_failed=%s persona=%s", e,
                              persona.get("_id"))
        return _fallback_reply(persona)


def _fallback_reply(persona: dict) -> str:
    name = persona.get("display_name") or "your host"
    return (f"This is {name}. The studio mic is acting up — give me a "
                  f"second and I'll be right back with you.")


def _persona_voice_id(persona: dict) -> Optional[str]:
    """Resolve the ElevenLabs voice_id for this persona.  Prefer the
    column on the persona doc; else look up via voice_key in VOICE_REGISTRY."""
    if persona.get("voice_id"):
        return persona["voice_id"]
    vk = persona.get("voice_key")
    if not vk:
        return None
    try:
        from services.voice_config import VOICE_REGISTRY
        return (VOICE_REGISTRY.get(vk) or {}).get("voice_id")
    except Exception:
        return None


async def _synthesize_persona_audio(persona: dict, text: str) -> dict:
    """Render `text` in the persona's voice. Returns {audio_url,
    storage_key, error?}.  Audio is persisted under
    /app/backend/storage/rj/p39_chat_<uuid>.mp3, then uploaded to Tigris
    if STORAGE_BACKEND=tigris. Local mode returns a /api/admin/rj-audio
    style URL via the local static endpoint."""
    voice_id = _persona_voice_id(persona)
    if not voice_id:
        return {"audio_url": None,
                      "storage_key": None,
                      "error": "voice_id_missing"}
    try:
        from services.rj import synthesize_solo
        from core.config import DEFAULT_ENERGY
        # synthesize_solo is sync (writes to disk); run in thread.
        out_path = await asyncio.to_thread(
            synthesize_solo, text, voice_id, DEFAULT_ENERGY)
    except Exception as e:
        log.warning("[personas.chat] tts_failed=%s persona=%s",
                              e, persona.get("_id"))
        return {"audio_url": None, "storage_key": None,
                      "error": f"tts_failed: {type(e).__name__}"}

    # Push to Tigris if configured; else return local file URL.
    storage_key = f"persona_chat/{persona['_id']}/{Path(out_path).name}"
    audio_url: Optional[str] = None
    try:
        from services.object_storage import get_storage
        backend = (os.environ.get("STORAGE_BACKEND") or "local").lower()
        if backend == "tigris":
            get_storage().upload(local_path=str(out_path), key=storage_key,
                                                  content_type="audio/mpeg")
            audio_url = get_storage().get_signed_url(key=storage_key,
                                                                                              expires_in=3600)
            # Clean up local copy.
            try: out_path.unlink(missing_ok=True)
            except Exception: pass
        else:
            audio_url = f"/storage/rj/{Path(out_path).name}"
    except Exception as e:
        log.warning("[personas.chat] storage_failed=%s — falling back to "
                              "local path", e)
        audio_url = f"/storage/rj/{Path(out_path).name}"
    return {"audio_url": audio_url, "storage_key": storage_key, "error": None}


@router.post("/personas/chat")
async def persona_chat(body: ChatPersonaIn, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    persona = await get_safe_persona(db, body.persona_id)
    if not persona:
        raise HTTPException(403, {"code": "persona_unavailable",
                                                      "persona_id": body.persona_id})

    reply_text = await _llm_chat_reply(persona, body.listener_input_text,
                                                                          user=user)
    audio = await _synthesize_persona_audio(persona, reply_text)

    # Log the turn for analytics (best-effort, non-blocking).
    try:
        await db.persona_chat_log.insert_one({
            "_id":                  uuid.uuid4().hex,
            "user_id":            user.get("user_id"),
            "persona_id":      persona["_id"],
            "listener_input": body.listener_input_text[:500],
            "response_text":  reply_text[:1000],
            "audio_url":          audio.get("audio_url"),
            "audio_error":      audio.get("error"),
            "created_at":      datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        log.warning("[personas.chat] log insert failed: %s", e)

    return {
        "ok": True,
        "persona_id":          persona["_id"],
        "persona_display_name": persona.get("display_name"),
        "response_text":      reply_text,
        "response_audio_url": audio.get("audio_url"),
        "audio_error":          audio.get("error"),
    }


# ─── admin re-classify ──────────────────────────────────────────────
@router.post("/admin/personas/reclassify_all",
                          dependencies=[Depends(require_admin)])
async def admin_reclassify_all_personas(request: Request):
    """Re-runs `PersonaSafetyClassifier.classify()` over every persona
    row.  Useful after a blocklist edit — admins don't need to redeploy
    or restart the backend.  Returns a per-persona before/after diff
    so any newly-blocked rows are immediately visible."""
    from services.persona_safety import (PersonaSafetyClassifier,
                                                                              reload_blocklists)
    reload_blocklists()
    classifier = PersonaSafetyClassifier()
    db = request.app.state.db
    now = datetime.now(timezone.utc).isoformat()
    examined = 0
    became_unsafe: list[dict] = []
    became_safe:    list[dict] = []
    unchanged = 0
    async for doc in db.rj_personality_profiles.find({}):
        examined += 1
        # Skip legacy rows with non-string _id (ObjectId) — they aren't
        # personas in the Phase 39 sense.
        if not isinstance(doc.get("_id"), str):
            continue
        was_safe = bool((doc.get("safety_classification") or {})
                                      .get("is_safe"))
        # Reconstruct the classifier input from the stored row.
        result = classifier.classify({
            "display_name":  doc.get("display_name") or doc.get("name"),
            "description":  doc.get("description"),
            "signature_phrases": doc.get("signature_phrases") or [],
            "voice_clone_reference_url":
                doc.get("voice_clone_reference_url"),
        })
        new_safe = bool(result["is_safe"])
        update_fields = {
            "safety_classification": {
                **result,
                "classified_at": now,
                "classifier_version": "p39s2.1",
            },
            "last_classified_at": now,
        }
        await db.rj_personality_profiles.update_one(
            {"_id": doc["_id"]}, {"$set": update_fields})
        if was_safe and not new_safe:
            became_unsafe.append({"persona_id": doc["_id"],
                                                      "flags": result["flags"]})
        elif (not was_safe) and new_safe:
            became_safe.append({"persona_id": doc["_id"]})
        else:
            unchanged += 1
    return {"ok": True,
                  "examined": examined,
                  "became_unsafe": became_unsafe,
                  "became_safe":    became_safe,
                  "unchanged":        unchanged,
                  "classified_at": now}
