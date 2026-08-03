"""Phase H'.3 — AI-RJ inter-song voice segment shim.

A thin HTTP wrapper around the existing solo RJ pipeline
(`services.rj.generate_rj_script_solo` + `services.elevenlabs_tts.synthesize`)
that adds:

  • A cache collection `ai_rj_segments_cache` keyed on
    `(persona_id, prev_track_id, next_mood, hour_bucket)` so identical
    contexts reuse audio across listeners — saves both OpenAI tokens
    and ElevenLabs characters.
  • A `cadence_due(songs_played)` helper so the orchestrator can ask
    "is it time for an RJ break?" before generating.
  • The endpoint `POST /api/ai-rj/segment/generate` for orchestrator
    callers.  Returns `{audio_url, duration_seconds, transcript,
    expires_at, voice_id, cache_hit}`.

This module deliberately does NOT touch the legacy prewarm pipeline in
`services/rj.py` — that path stays exactly as-is.  Phase H'.3 adds a
cadence-aware layer above it for the upcoming player work.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin

log = logging.getLogger("bigfm.ai_rj_segments")

router = APIRouter(prefix="/api/ai-rj", tags=["ai-rj-segments"])

CACHE_TTL_HOURS = 24
SEGMENT_DIR = Path("/app/backend/storage/rj_segments")
SEGMENT_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_utc_key() -> str:
    """Phase H'.5b — UTC day-bucket key for the `ai_rj_daily_stats`
    rollup collection (one row per UTC date)."""
    return _now().strftime("%Y-%m-%d")


def _hour_bucket(dt: Optional[datetime] = None) -> str:
    """8 broad buckets so the cache key has high reuse without losing
    daypart flavour."""
    dt = dt or _now()
    h = dt.hour
    if 0 <= h < 4:
        return "late_night"
    if 4 <= h < 7:
        return "dawn"
    if 7 <= h < 11:
        return "morning"
    if 11 <= h < 14:
        return "lunch"
    if 14 <= h < 17:
        return "afternoon"
    if 17 <= h < 20:
        return "evening_drive"
    if 20 <= h < 23:
        return "night"
    return "late"


def _cache_key(persona_id: str, prev_track_id: Optional[str],
                                  next_mood: Optional[str], hour_bucket: str) -> str:
    raw = "|".join([persona_id or "default",
                                  prev_track_id or "—",
                                  (next_mood or "").lower(),
                                  hour_bucket])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


# ─── Public helper used by the orchestrator ───────────────────────────
def cadence_due(songs_played_since_last_segment: int) -> bool:
    """Returns True when it's time to insert an RJ segment between songs.

    The cadence is the count `AI_RJ_SEGMENT_EVERY_N` (env), bounded
    [2, 6] so the orchestrator can never starve or spam the listener.
    """
    try:
        n = int(os.environ.get("AI_RJ_SEGMENT_EVERY_N", "3"))
    except (TypeError, ValueError):
        n = 3
    n = max(2, min(n, 6))
    return songs_played_since_last_segment >= n


# ─── Request / response shapes ─────────────────────────────────────────
class _Track(BaseModel):
    track_id: Optional[str] = None
    title: str = ""
    artist: str = ""
    energy_level: str = "medium"
    mood: Optional[str] = None


class GenerateIn(BaseModel):
    persona_id: Optional[str] = Field(
        None, description="Override the resolved persona.  When omitted, "
                                          "resolve_active_persona() picks based on user "
                                          "selection + daypart.")
    previous_track: Optional[_Track] = None
    next_track: _Track
    city:              Optional[str] = "Dubai"
    weather_hint:  Optional[str] = None
    channel_name: Optional[str] = None
    force_refresh: bool = False


# ─── Endpoint ─────────────────────────────────────────────────────────
@router.post("/segment/generate",
                          description="Phase H'.3 — generate (or fetch) an AI-RJ "
                                                "voice segment for the upcoming song.")
async def generate_segment(body: GenerateIn, request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db

    # ─── Resolve persona ─────────────────────────────────────────────
    persona: Optional[dict] = None
    if body.persona_id:
        persona = await db.rj_personality_profiles.find_one({
            "_id": body.persona_id})
    if not persona:
        from services.persona_service import resolve_active_persona
        persona = await resolve_active_persona(db, user)
    if not persona:
        raise HTTPException(404, {"code": "persona_unavailable",
                                                                "message": "No safe persona could be resolved."})

    persona_id = persona.get("_id") or persona.get("persona_id") or "default"
    hour_bucket = _hour_bucket()
    cache_key = _cache_key(persona_id, body.previous_track.track_id
                                                  if body.previous_track else None,
                                                  body.next_track.mood or body.next_track.energy_level,
                                                  hour_bucket)

    # ─── Cache lookup ────────────────────────────────────────────────
    if not body.force_refresh:
        cached = await db.ai_rj_segments_cache.find_one({"_id": cache_key})
        if cached:
            expires_at = cached.get("expires_at")
            # Mongo returns naive UTC datetimes — normalise before
            # comparing to our tz-aware `_now()`.
            if expires_at and isinstance(expires_at, datetime):
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at > _now():
                    log.info("[ai-rj] cache hit key=%s persona=%s",
                                              cache_key, persona_id)
                    # Phase H'.5b — bump access counter on hit.
                    now = _now()
                    await db.ai_rj_segments_cache.update_one(
                        {"_id": cache_key},
                        {"$set": {"last_accessed_at": now},
                          "$inc": {"access_count": 1}})
                    # Tally daily hit for the cache-stats endpoint.
                    await db.ai_rj_daily_stats.update_one(
                        {"_id": _today_utc_key()},
                        {"$inc": {"hits": 1},
                          "$set": {"updated_at": now}},
                        upsert=True)
                    return {
                        "cache_hit": True,
                        "audio_url": cached["audio_url"],
                        "duration_seconds": cached.get("duration_seconds"),
                        "transcript":      cached["transcript"],
                        "voice_id":          cached["voice_id"],
                        "expires_at":      expires_at.isoformat(),
                        "cache_key":      cache_key,
                    }

    # ─── Generate script ─────────────────────────────────────────────
    try:
        from services.rj import generate_rj_script_solo
        # Build a minimal Context object the legacy code expects.
        class _Ctx:
            time_of_day = hour_bucket
            weather_hint = body.weather_hint
            city = body.city or "Dubai"
        prev = None
        if body.previous_track:
            prev = {"title": body.previous_track.title,
                          "artist": body.previous_track.artist,
                          "energy_level": body.previous_track.energy_level,
                          "mood": body.previous_track.mood}
        nxt = {"title": body.next_track.title,
                      "artist": body.next_track.artist,
                      "energy_level": body.next_track.energy_level,
                      "mood": body.next_track.mood}
        voice_key = persona.get("voice_key") or "veer_dubai"
        transcript = await asyncio.to_thread(
            generate_rj_script_solo, prev, nxt, _Ctx(), voice_key,
            body.channel_name)
    except Exception as e:
        log.error("[ai-rj] script generation failed: %s", e)
        raise HTTPException(502, {"code": "script_generation_failed",
                                                                "error": str(e)[:140]})

    # ─── Synthesize via shared ElevenLabs helper ─────────────────────
    from services.elevenlabs_tts import (
        synthesize as eleven_synthesize,
        resolve_voice_id_for_persona,
    )
    voice_id = resolve_voice_id_for_persona(persona)
    out_path = SEGMENT_DIR / f"{cache_key}.mp3"
    res = await asyncio.to_thread(
        eleven_synthesize, transcript, voice_id,
        energy=body.next_track.energy_level or "medium",
        out_path=out_path)
    if not res["ok"]:
        # Soft degrade — return the transcript without audio so the
        # orchestrator can either skip the segment or render text only.
        return {
            "cache_hit": False,
            "audio_url": None,
            "duration_seconds": None,
            "transcript": transcript,
            "voice_id":    voice_id,
            "expires_at": None,
            "over_quota": res.get("over_quota", False),
            "error":          res.get("error"),
            "cache_key":  cache_key,
        }

    # Try ffprobe for duration (best-effort).
    duration_sec = None
    try:
        import subprocess as _subprocess
        import json as _json
        probe = _subprocess.run(
            ["ffprobe", "-v", "quiet", "-of", "json",
              "-show_format", str(out_path)],
            capture_output=True, text=True, timeout=4)
        info = _json.loads(probe.stdout)
        duration_sec = float(info["format"]["duration"])
    except Exception:
        pass

    expires_at = _now() + timedelta(hours=CACHE_TTL_HOURS)
    audio_url = f"/api/static/rj_segments/{cache_key}.mp3"
    doc = {
        "_id":              cache_key,
        "persona_id":  persona_id,
        "voice_id":      voice_id,
        "voice_key":  voice_key,
        "audio_url":  audio_url,
        "transcript": transcript,
        "duration_seconds": duration_sec,
        "char_count": res["char_count"],
        "prev_track_id": body.previous_track.track_id if body.previous_track else None,
        "next_mood":      body.next_track.mood or body.next_track.energy_level,
        "hour_bucket": hour_bucket,
        "created_at":  _now(),
        "expires_at":  expires_at,
    }
    await db.ai_rj_segments_cache.update_one(
        {"_id": cache_key}, {"$set": doc}, upsert=True)
    # Phase H'.5b — tally daily miss (live generation) + char spend.
    await db.ai_rj_daily_stats.update_one(
        {"_id": _today_utc_key()},
        {"$inc": {"misses": 1,
                            "chars_spent": int(res["char_count"])},
          "$set": {"updated_at": _now()}},
        upsert=True)
    log.info("[ai-rj] generated key=%s voice=%s chars=%d dur=%s",
                          cache_key, voice_id, res["char_count"], duration_sec)
    return {
        "cache_hit": False,
        "audio_url": audio_url,
        "duration_seconds": duration_sec,
        "transcript":       transcript,
        "voice_id":          voice_id,
        "expires_at":      expires_at.isoformat(),
        "char_count":      res["char_count"],
        "cache_key":      cache_key,
    }


# ─── Admin/listener: peek at cadence config ───────────────────────────
@router.get("/segment/cadence")
async def get_cadence(user: dict = Depends(current_user)):
    try:
        n = int(os.environ.get("AI_RJ_SEGMENT_EVERY_N", "3"))
    except (TypeError, ValueError):
        n = 3
    n = max(2, min(n, 6))
    return {"every_n_songs": n, "min": 2, "max": 6}


# ─── Phase H'.5b — Admin AI-RJ cache stats ────────────────────────────
admin_router = APIRouter(prefix="/api/admin/ai-rj",
                                                tags=["admin-ai-rj"])


@admin_router.get("/cache-stats",
                                          description="Cache hit-rate + char-spend rollup for today (UTC).")
async def cache_stats(request: Request,
                                                _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    today = _today_utc_key()
    rollup = (await db.ai_rj_daily_stats.find_one({"_id": today})) or {}
    hits = int(rollup.get("hits") or 0)
    misses = int(rollup.get("misses") or 0)
    chars_today = int(rollup.get("chars_spent") or 0)
    total_today = hits + misses
    hit_rate = (hits / total_today) if total_today else 0.0

    total_segments = await db.ai_rj_segments_cache.count_documents({})
    # Aggregate avg char + duration across the live cache (not just today).
    avg_chars = 0.0
    avg_dur = 0.0
    try:
        agg = await db.ai_rj_segments_cache.aggregate([
            {"$group": {"_id": None,
                                    "avg_chars": {"$avg": "$char_count"},
                                    "avg_dur":      {"$avg": "$duration_seconds"}}}
        ]).to_list(length=1)
        if agg:
            avg_chars = float(agg[0].get("avg_chars") or 0.0)
            avg_dur = float(agg[0].get("avg_dur") or 0.0)
    except Exception as e:
        log.warning("[ai-rj] cache-stats agg failed: %s", e)

    # Top personas by segment volume (uses the live cache, not rollups).
    top = []
    try:
        cur = db.ai_rj_segments_cache.aggregate([
            {"$group": {"_id": "$persona_id",
                                    "segment_count": {"$sum": 1}}},
            {"$sort":  {"segment_count": -1}},
            {"$limit": 5},
        ])
        async for r in cur:
            top.append({"persona_id":      r["_id"],
                                      "segment_count": int(r["segment_count"])})
    except Exception as e:
        log.warning("[ai-rj] cache-stats top agg failed: %s", e)

    # Reach for the live cadence + ElevenLabs quota cap for context.
    try:
        cadence = int(os.environ.get("AI_RJ_SEGMENT_EVERY_N", "3"))
    except (TypeError, ValueError):
        cadence = 3
    cadence = max(2, min(cadence, 6))
    elevenlabs_quota = None
    try:
        from services.elevenlabs_tts import quota_state
        elevenlabs_quota = quota_state()
    except Exception:
        pass

    return {
        "total_segments":          total_segments,
        "cache_hits_today":      hits,
        "cache_misses_today":  misses,
        "hit_rate_today":          round(hit_rate, 4),
        "chars_spent_today":      chars_today,
        "avg_chars_per_segment": round(avg_chars, 2),
        "avg_duration_seconds": round(avg_dur, 2),
        "top_personas_by_volume": top,
        "current_cadence":      cadence,
        "elevenlabs_quota":      elevenlabs_quota,
        "today":                          today,
    }
