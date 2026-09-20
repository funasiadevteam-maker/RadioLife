"""Phase D — AI RJ Personas.

Owns:
    * `rj_personas` collection — admin-managed voice-branded personas
        with ElevenLabs / OpenAI TTS voice_id, personality tag, LLM
        persona_prompt, cover/sample assets.
    * `rj_station_assignments` — many-to-many station↔persona with a
        priority (fallback chain).  Unique on (station_id, persona_id).
    * `rj_segments` — generated preview + on-demand segment cache.
        Each row has script_text + audio_url + context snapshot.

Coexists with the pre-existing Phase 39 `rj_personality_profiles` +
`ai_rj_segments_cache` — this is NOT a rewrite; it's the admin-managed
catalog + station-binding layer AD.5 (Trivia Sponsorship) needs.

Never leaks `persona_prompt` in public reads — that field is admin-only.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import ELEVENLABS_API_KEY, RJ_DIR
from services.object_storage import get_storage, key_rj

logger = logging.getLogger("bigfm.rj_personas")

PUBLIC_FIELDS = (
    "id", "name", "tagline", "description",
    "voice_id", "voice_provider", "language",
    "personality", "sample_audio_url", "cover_image_url",
    "status", "is_default", "created_at", "updated_at",
)

ADMIN_ONLY_FIELDS = ("persona_prompt", "created_by_user_id")

DEFAULT_PROMPT = (
    "You are an upbeat radio host on FUUSIC. Bridge the previous song "
    "to the next song in 15-25 seconds. Mention the mood or the "
    "listener's daypart. Keep it energetic and conversational.")

PERSONALITY_VALUES = {"energetic", "chill", "news", "party",
                                            "devotional", "custom"}
VOICE_PROVIDERS = {"elevenlabs", "openai_tts"}
STATUSES = {"draft", "active", "archived"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _shape_public(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Strip admin-only fields (persona_prompt, created_by_user_id) for
    public reads.  Never returns None keys."""
    if not doc:
        return {}
    out = {k: doc.get(k) for k in PUBLIC_FIELDS if k in doc}
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def _shape_admin(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Full doc with dates ISO-encoded."""
    if not doc:
        return {}
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ── indexes ──────────────────────────────────────────────────────
async def ensure_rj_persona_indexes(db) -> None:
    try:
        await db.rj_personas.create_index(
            [("status", 1), ("created_at", -1)], name="rjp_status_recent")
        await db.rj_personas.create_index("is_default", sparse=True,
                                                                            name="rjp_default")
        await db.rj_station_assignments.create_index(
            [("station_id", 1), ("persona_id", 1)], unique=True,
            name="rjsa_station_persona_uniq")
        await db.rj_station_assignments.create_index(
            [("station_id", 1), ("priority", 1)], name="rjsa_station_prio")
        await db.rj_station_assignments.create_index(
            "persona_id", name="rjsa_persona")
        await db.rj_segments.create_index(
            [("persona_id", 1), ("generated_at", -1)],
            name="rjs_persona_recent")
        await db.rj_segments.create_index(
            [("station_id", 1), ("generated_at", -1)],
            name="rjs_station_recent")
    except Exception as e:
        logger.warning("[rj_personas] index setup: %s", e)


# ── validation ───────────────────────────────────────────────────
def _validate_body(body: Dict[str, Any], *, partial: bool = False) -> None:
    if not partial:
        if not (body.get("name") or "").strip():
            raise ValueError("name_required")
        if not (body.get("voice_id") or "").strip():
            raise ValueError("voice_id_required")
    if "voice_provider" in body:
        if body["voice_provider"] not in VOICE_PROVIDERS:
            raise ValueError("invalid_voice_provider")
    if "personality" in body:
        if body["personality"] not in PERSONALITY_VALUES:
            raise ValueError("invalid_personality")
    if "status" in body:
        if body["status"] not in STATUSES:
            raise ValueError("invalid_status")


# ── CRUD ─────────────────────────────────────────────────────────
async def create_persona(db, *, body: Dict[str, Any],
                                                  actor_user_id: str) -> Dict[str, Any]:
    _validate_body(body, partial=False)
    now = _now()
    pid = _gen("rjp")
    doc = {
        "_id":                            pid,
        "id":                              pid,
        "name":                          body["name"].strip(),
        "tagline":                    (body.get("tagline") or "").strip() or None,
        "description":            (body.get("description") or "").strip() or None,
        "voice_id":                  body["voice_id"].strip(),
        "voice_provider":        body.get("voice_provider") or "elevenlabs",
        "language":                  (body.get("language") or "en").strip(),
        "personality":            body.get("personality") or "energetic",
        "persona_prompt":        (body.get("persona_prompt") or DEFAULT_PROMPT).strip(),
        "sample_audio_url":  body.get("sample_audio_url"),
        "cover_image_url":    body.get("cover_image_url"),
        "status":                      body.get("status") or "draft",
        "is_default":              bool(body.get("is_default") or False),
        "created_by_user_id": actor_user_id,
        "created_at":              now,
        "updated_at":              now,
    }
    # If this persona is set to default, unflag every other one.
    if doc["is_default"]:
        await db.rj_personas.update_many(
            {"is_default": True}, {"$set": {"is_default": False,
                                                                              "updated_at": now}})
    await db.rj_personas.insert_one(doc)
    return _shape_admin(doc)


async def list_personas(db, *, status: Optional[str] = None,
                                                include_archived: bool = False,
                                                admin: bool = False) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    elif not include_archived:
        q["status"] = {"$ne": "archived"}
    rows = []
    async for d in db.rj_personas.find(q).sort("created_at", -1):
        rows.append(_shape_admin(d) if admin else _shape_public(d))
    return rows


async def get_persona(db, *, persona_id: str,
                                              admin: bool = False) -> Optional[Dict[str, Any]]:
    d = await db.rj_personas.find_one({"id": persona_id})
    if not d:
        return None
    return _shape_admin(d) if admin else _shape_public(d)


async def update_persona(db, *, persona_id: str, patch: Dict[str, Any]
                                                    ) -> Optional[Dict[str, Any]]:
    _validate_body(patch, partial=True)
    updates: Dict[str, Any] = {}
    for k in ("name", "tagline", "description", "voice_id",
                        "voice_provider", "language", "personality",
                        "persona_prompt", "sample_audio_url",
                        "cover_image_url", "status", "is_default"):
        if k in patch:
            v = patch[k]
            if isinstance(v, str):
                v = v.strip()
            updates[k] = v
    if not updates:
        return await get_persona(db, persona_id=persona_id, admin=True)
    now = _now()
    updates["updated_at"] = now
    if updates.get("is_default") is True:
        await db.rj_personas.update_many(
            {"id": {"$ne": persona_id}, "is_default": True},
            {"$set": {"is_default": False, "updated_at": now}})
    r = await db.rj_personas.find_one_and_update(
        {"id": persona_id}, {"$set": updates},
        return_document=True)
    if not r:
        return None
    return _shape_admin(r)


async def archive_persona(db, *, persona_id: str) -> bool:
    r = await db.rj_personas.update_one(
        {"id": persona_id}, {"$set": {"status": "archived",
                                                                    "updated_at": _now()}})
    if r.matched_count:
        # Best-effort: remove from station assignments so the "assigned
        # personas" reads don't surface an archived row.
        await db.rj_station_assignments.delete_many(
            {"persona_id": persona_id})
    return bool(r.matched_count)


# ── station assignments ──────────────────────────────────────────
async def assign_persona(db, *, station_id: str, persona_id: str,
                                                  priority: int, actor_user_id: str
                                                  ) -> Dict[str, Any]:
    # Verify persona exists and is not archived.
    p = await db.rj_personas.find_one({"id": persona_id},
                                                                        {"status": 1, "name": 1})
    if not p:
        raise ValueError("persona_not_found")
    if p.get("status") == "archived":
        raise ValueError("persona_archived")
    now = _now()
    doc = {
        "id":                            _gen("rjsa"),
        "station_id":              station_id,
        "persona_id":              persona_id,
        "priority":                  int(priority),
        "assigned_at":            now,
        "assigned_by_user_id": actor_user_id,
    }
    # Upsert on (station_id, persona_id) — priority is updated in place.
    await db.rj_station_assignments.update_one(
        {"station_id": station_id, "persona_id": persona_id},
        {"$set": {"priority":                doc["priority"],
                          "assigned_at":            doc["assigned_at"],
                          "assigned_by_user_id": doc["assigned_by_user_id"]},
          "$setOnInsert": {"id": doc["id"],
                                            "_id":  doc["id"],
                                            "station_id": station_id,
                                            "persona_id": persona_id}},
        upsert=True)
    row = await db.rj_station_assignments.find_one(
        {"station_id": station_id, "persona_id": persona_id})
    row.pop("_id", None)
    if isinstance(row.get("assigned_at"), datetime):
        row["assigned_at"] = row["assigned_at"].isoformat()
    return row


async def unassign_persona(db, *, station_id: str,
                                                      persona_id: str) -> bool:
    r = await db.rj_station_assignments.delete_one(
        {"station_id": station_id, "persona_id": persona_id})
    return bool(r.deleted_count)


async def list_station_personas(db, *, station_id: str,
                                                                only_active: bool = True
                                                                ) -> List[Dict[str, Any]]:
    """Assigned personas for a station, sorted by priority (asc).
    Public shape — no persona_prompt leaked.  Filters out archived
    personas + status != active when only_active is True."""
    rows: List[Dict[str, Any]] = []
    async for a in db.rj_station_assignments.find(
                {"station_id": station_id}).sort("priority", 1):
        p = await db.rj_personas.find_one({"id": a["persona_id"]})
        if not p:
            continue
        if only_active and p.get("status") != "active":
            continue
        entry = _shape_public(p)
        entry["priority"] = int(a.get("priority") or 100)
        entry["assigned_at"] = (a["assigned_at"].isoformat()
            if isinstance(a.get("assigned_at"), datetime)
            else a.get("assigned_at"))
        rows.append(entry)
    return rows


# ── preview / segment generation ─────────────────────────────────
def _synthesize_audio(script: str, voice_id: str, voice_provider: str,
                                            language: str, personality: str) -> Path:
    """Provider-agnostic synthesis returning a local MP3 path.  Reuses
    the pre-existing helpers so voice-settings + fallback semantics
    match production RJ segments."""
    if voice_provider == "openai_tts":
        # OpenAI TTS uses voice_key from OPENAI_TTS_VOICES; the admin's
        # voice_id IS the key for that provider.
        from services.openai_tts import synthesize_openai
        return synthesize_openai(script, voice_id)
    # Default → ElevenLabs.
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not configured")
    from services.rj import synthesize_elevenlabs_raw
    # personality → energy mapping.
    energy = {
        "energetic":    "high",
        "party":            "high",
        "chill":            "low",
        "devotional":  "low",
        "news":              "medium",
        "custom":          "medium",
    }.get(personality, "medium")
    return synthesize_elevenlabs_raw(script, voice_id, energy)


def _upload_to_storage(local_path: Path, key: str) -> str:
    """Uploads to whichever storage backend is configured (Tigris in
    prod, local disk in dev).  Returns the public signed URL."""
    storage = get_storage()
    storage.upload(local_path=str(local_path), key=key,
                                content_type="audio/mpeg")
    try:
        # 24 h signed URL — plenty for admin preview + listener chip.
        return storage.get_signed_url(key=key, expires_in=86400)
    except Exception:
        # LocalDiskStorage may not implement signing — fall back to a
        # public /storage path.
        return f"/api/storage/{key}"


async def _generate_script(persona: Dict[str, Any],
                                                    context: Dict[str, Any]) -> str:
    """LLM script generator.  Uses `EMERGENT_LLM_KEY` +
    emergentintegrations LlmChat (project-standard).  Falls back to a
    templated stub if the key is missing so the admin flow still works
    in dev environments (the ElevenLabs call is the harder gate)."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    system_prompt = (persona.get("persona_prompt") or DEFAULT_PROMPT).strip()
    ctx_lines = []
    for k in ("time_of_day", "city", "weather_hint",
                        "next_track_mood", "listener_context"):
        v = context.get(k)
        if v:
            ctx_lines.append(f"{k.replace('_', ' ')}: {v}")
    ctx_block = "\n".join(ctx_lines) if ctx_lines else "no additional context"
    user_prompt = (
        f"Produce a 10-25 second radio host segment in "
        f"{persona.get('language') or 'en'}.  Do NOT reveal the exact "
        f"upcoming track name — refer only to mood / vibe.  Do NOT use "
        f"emoji or emoji-like brackets.  Keep it under 500 characters.\n\n"
        f"Context:\n{ctx_block}")
    if not api_key:
        # Deterministic fallback so preview still works — clearly
        # marked so tests can distinguish it.
        return (f"Hey — {persona.get('name')} here on FUUSIC. "
                        f"Hope your {context.get('time_of_day') or 'day'} in "
                        f"{context.get('city') or 'the city'} is going great. "
                        "Stay tuned for more.")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (LlmChat(api_key=api_key,
                                        session_id=f"rj_persona_{persona['id']}_"
                                                              f"{_gen('sess')[:8]}",
                                        system_message=system_prompt)
                        .with_model("openai", "gpt-4o-mini"))
        resp = await chat.send_message(UserMessage(text=user_prompt))
        text = (resp or "").strip()
        return text[:500] if len(text) > 500 else text
    except Exception as e:
        logger.warning("[rj_personas] LLM failed, using fallback: %s", e)
        return (f"Hey — {persona.get('name')} here on FUUSIC. "
                        f"Stay tuned.")


async def generate_preview(db, *, persona_id: str,
                                                      context: Dict[str, Any],
                                                      actor_user_id: Optional[str] = None
                                                      ) -> Dict[str, Any]:
    """Full preview pipeline — LLM script → TTS synth → Tigris upload
    → persist to `rj_segments`.  Raises RuntimeError with a clean code
    if the TTS provider isn't configured."""
    persona = await db.rj_personas.find_one({"id": persona_id})
    if not persona:
        raise ValueError("persona_not_found")

    # 1. LLM script.
    script = await _generate_script(persona, context or {})

    # 2. TTS synth.  Errors are surfaced up to the route so we can 503.
    provider = persona.get("voice_provider") or "elevenlabs"
    if provider == "elevenlabs" and not ELEVENLABS_API_KEY:
        raise RuntimeError("elevenlabs_api_key_missing")
    local_path = _synthesize_audio(
        script=script,
        voice_id=persona["voice_id"],
        voice_provider=provider,
        language=persona.get("language") or "en",
        personality=persona.get("personality") or "energetic")

    # 3. Upload to storage (Tigris in prod).
    seg_id = _gen("rjseg")
    key = key_rj(seg_id)
    audio_url = _upload_to_storage(local_path, key)

    # 4. Duration.
    duration_sec: Optional[float] = None
    try:
        import subprocess
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries",
              "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
              str(local_path)], stderr=subprocess.STDOUT, timeout=8)
        duration_sec = float(out.decode().strip())
    except Exception:
        pass

    # 5. Persist segment row.
    now = _now()
    seg_doc = {
        "_id":                        seg_id,
        "id":                          seg_id,
        "persona_id":          persona_id,
        "station_id":          None,      # preview, not station-bound
        "script_text":        script,
        "audio_url":            audio_url,
        "storage_key":        key,
        "context_json":      context or {},
        "duration_seconds": duration_sec,
        "generated_at":      now,
        "generated_by":      "gpt-4o-mini/eleven_v3"
                                                    if provider == "elevenlabs"
                                                    else "gpt-4o-mini/openai_tts",
        "status":                  "generated",
        "created_by_user_id": actor_user_id,
    }
    await db.rj_segments.insert_one(seg_doc)

    # 6. Best-effort: bump persona's sample_audio_url if the persona
    # doesn't yet have one — first preview becomes the demo clip.
    if not persona.get("sample_audio_url"):
        await db.rj_personas.update_one(
            {"id": persona_id},
            {"$set": {"sample_audio_url": audio_url,
                              "updated_at": now}})

    # 7. Cleanup local temp file so RJ_DIR doesn't grow unbounded when
    # Tigris is the primary backend.
    try:
        if get_storage().backend_name != "local":
            local_path.unlink(missing_ok=True)
    except Exception:
        pass

    return {
        "script_text":          script,
        "audio_url":              audio_url,
        "duration_seconds": duration_sec,
        "segment_id":            seg_id,
        "voice_provider":    provider,
        "persona_id":            persona_id,
    }


__all__ = [
    "ensure_rj_persona_indexes",
    "create_persona", "list_personas", "get_persona",
    "update_persona", "archive_persona",
    "assign_persona", "unassign_persona", "list_station_personas",
    "generate_preview",
    "PERSONALITY_VALUES", "VOICE_PROVIDERS", "STATUSES",
]
