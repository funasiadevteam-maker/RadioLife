"""Phase H'.1 — Centralised ElevenLabs TTS helper.

A thin wrapper around the existing `services.rj.synthesize_elevenlabs_raw`
that adds the operational glue we need across H' (persona samples, news
clips, AI-RJ segments):

  • Single synthesize entrypoint (text → MP3 bytes OR file path).
  • Built-in retry (3× exponential backoff on 429 / 5xx-ish exceptions).
  • Per-day character quota counter (UTC-bucketed in-memory).
  • Soft circuit-break at `ELEVENLABS_DAILY_CHAR_CAP * 0.9` so heavy news
    batches never spend the whole budget — at that point we degrade to
    text-only mode (callers can branch on `over_quota`).
  • Voice-archetype helper that resolves a persona → voice_id while
    keeping the legacy `8vqXJx9Riwp7L4KLhsU3` (Raghav) as the
    zero-regression fallback when nothing else maps.
  • Never logs the key — only metadata (voice_id, char_count, latency).
"""
from __future__ import annotations
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("bigfm.elevenlabs_tts")

DAILY_CHAR_CAP = int(os.environ.get("ELEVENLABS_DAILY_CHAR_CAP", "100000"))
SOFT_BACKOFF_FRACTION = 0.9
LEGACY_DEFAULT_VOICE_ID = "8vqXJx9Riwp7L4KLhsU3"   # Raghav / Armaan

# Archetype keyword → preferred VOICE_REGISTRY key.  When the persona's
# `archetype` field contains the substring on the left, we override the
# voice_key lookup with the value on the right.  Otherwise we honour the
# explicit `voice_key` on the persona doc (existing behaviour).
#
# These are deliberately *substring* matches against `archetype` so the
# Phase 39 persona schema (where archetype is a free-form descriptor like
# "calm_morning_hinglish" or "high_energy_us_morning") routes naturally:
ARCHETYPE_VOICE_OVERRIDE: dict[str, str] = {
    "news_anchor":              "raghav_hindi",
    "bilingual_news":          "raghav_hindi",
    "calm_morning":              "aarti_morning",
    "dawn_caller":              "aarti_morning",
    "morning_warm":              "aarti_morning",
    "storyteller":              "veer_dubai",
    "afternoon":                  "veer_dubai",
    "slow_narrative":          "veer_dubai",
    "devotional":                  "pandit_anand",
    "drive_time":                  "monika_dubai",
    "energizer":                  "monika_dubai",
    "high_energy_us_morning":  "monika_dubai",
    "us_morning":                  "monika_dubai",
    "friday_hype":              "charlie_dj",
    "party":                          "charlie_dj",
    "high_energy_party":      "charlie_dj",
    "chill":                          "aanya_hindi",
    "lounge":                      "aanya_hindi",
    "vibe_curator":              "aanya_hindi",
    "latin_party":              "ishita_hindi",
    "bilingual_spanish":      "ishita_hindi",
    "late_night":                  "veer_dubai",
    "confidant":                  "veer_dubai",
    "lunch":                          "monika_dubai",
}

# ─── Per-process quota counter ────────────────────────────────────────
_lock = threading.Lock()
_quota: dict = {"day": None, "chars": 0, "calls": 0}


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _bump_quota(chars: int) -> dict:
    today = _today_key()
    with _lock:
        if _quota["day"] != today:
            _quota["day"] = today
            _quota["chars"] = 0
            _quota["calls"] = 0
        _quota["chars"] += int(chars)
        _quota["calls"] += 1
        return dict(_quota)


def quota_state() -> dict:
    today = _today_key()
    with _lock:
        if _quota["day"] != today:
            return {"day": today, "chars": 0, "calls": 0,
                          "cap": DAILY_CHAR_CAP,
                          "soft_backoff_at": int(DAILY_CHAR_CAP * SOFT_BACKOFF_FRACTION),
                          "remaining": DAILY_CHAR_CAP,
                          "over_quota": False}
        cap = DAILY_CHAR_CAP
        soft = int(cap * SOFT_BACKOFF_FRACTION)
        remaining = max(0, cap - _quota["chars"])
        return {"day": _quota["day"], "chars": _quota["chars"],
                      "calls": _quota["calls"], "cap": cap,
                      "soft_backoff_at": soft, "remaining": remaining,
                      "over_quota": _quota["chars"] >= soft}


def reset_quota_for_test() -> None:
    """Test helper — clears the counter. Production code never calls this."""
    with _lock:
        _quota["day"] = None
        _quota["chars"] = 0
        _quota["calls"] = 0


# ─── Voice resolution ──────────────────────────────────────────────────
def resolve_voice_id_for_persona(persona: dict) -> str:
    """Returns an ElevenLabs voice_id, honouring (in priority order):

        1. `persona.elevenlabs_voice_id` — explicit override.
        2. Archetype substring match → VOICE_REGISTRY entry (only if it's
            an `elevenlabs` provider — OpenAI-only voices are skipped).
        3. `persona.voice_key` → VOICE_REGISTRY (elevenlabs only).
        4. Hard-coded legacy default `8vqXJx9Riwp7L4KLhsU3`.

    This is intentionally tolerant — News Radio + AI-RJ both must never
    crash on a missing mapping; they degrade to the legacy voice instead.
    """
    if persona.get("elevenlabs_voice_id"):
        return persona["elevenlabs_voice_id"]

    try:
        from services.voice_config import VOICE_REGISTRY
    except Exception:
        return LEGACY_DEFAULT_VOICE_ID

    archetype = (persona.get("archetype") or "").lower()
    for needle, vkey in ARCHETYPE_VOICE_OVERRIDE.items():
        if needle in archetype:
            row = VOICE_REGISTRY.get(vkey) or {}
            if row.get("provider") == "elevenlabs" and row.get("voice_id"):
                return row["voice_id"]
            # OpenAI-provider override — skip, fall through.

    vk = persona.get("voice_key")
    if vk:
        row = VOICE_REGISTRY.get(vk) or {}
        if row.get("provider") == "elevenlabs" and row.get("voice_id"):
            return row["voice_id"]

    return LEGACY_DEFAULT_VOICE_ID


# ─── Synthesis entrypoint ──────────────────────────────────────────────
def synthesize(
    text: str,
    voice_id: str,
    *,
    energy: str = "medium",
    model_id: Optional[str] = None,
    output_format: Optional[str] = None,
    out_path: Optional[Path] = None,
    max_retries: int = 3,
) -> dict:
    """Renders `text` to MP3 via ElevenLabs.  Returns a metadata dict:

        {
            ok: bool,
            voice_id: str,
            file_path: Path | None,
            audio_bytes: bytes | None,   # only when out_path is None
            char_count: int,
            latency_ms: int,
            over_quota: bool,
            error: str | None,
        }

    When `out_path` is supplied, the MP3 is written there and `audio_bytes`
    is None.  When omitted, the bytes are returned in-memory for callers
    who want to push to object-storage themselves.

    Char quota:  every call increments the per-day counter by `len(text)`.
    When the counter is at or above SOFT_BACKOFF_FRACTION of the cap, we
    skip the live call and return `{ok: False, over_quota: True}` so
    callers can fall back gracefully (text-mode for news, queue-skip for
    RJ segments).
    """
    text = (text or "").strip()
    char_count = len(text)
    if not text:
        return {"ok": False, "voice_id": voice_id, "file_path": None,
                      "audio_bytes": None, "char_count": 0, "latency_ms": 0,
                      "over_quota": False, "error": "empty_text"}
    if not (os.environ.get("ELEVENLABS_API_KEY") or "").strip():
        return {"ok": False, "voice_id": voice_id, "file_path": None,
                      "audio_bytes": None, "char_count": char_count,
                      "latency_ms": 0, "over_quota": False,
                      "error": "elevenlabs_key_missing"}
    # Quota check BEFORE the call — never spend chars we don't have.
    q = quota_state()
    if q["over_quota"]:
        log.warning("[elevenlabs] quota soft-cap hit (%d/%d); skip live call",
                              q["chars"], q["cap"])
        return {"ok": False, "voice_id": voice_id, "file_path": None,
                      "audio_bytes": None, "char_count": char_count,
                      "latency_ms": 0, "over_quota": True,
                      "error": "daily_quota_soft_cap"}

    # Lazy import — the legacy synthesize_elevenlabs_raw already wraps the
    # SDK with eleven_v3 → multilingual_v2 fallback; we reuse it so we
    # don't duplicate the model-fallback ladder.
    from services.rj import synthesize_elevenlabs_raw   # noqa: WPS433
    from core.config import RJ_DIR
    t0 = time.time()
    err: Optional[str] = None
    raw_path: Optional[Path] = None
    for attempt in range(1, max_retries + 1):
        try:
            raw_path = synthesize_elevenlabs_raw(text, voice_id, energy)
            err = None
            break
        except Exception as e:
            err = f"{type(e).__name__}:{str(e)[:120]}"
            if attempt < max_retries:
                wait = 0.6 * (2 ** (attempt - 1))   # 0.6 / 1.2 / 2.4s
                log.warning("[elevenlabs] attempt=%d failed (%s); sleep %.1fs",
                                          attempt, err, wait)
                time.sleep(wait)
            else:
                log.error("[elevenlabs] exhausted retries (%d): %s",
                                          max_retries, err)
    latency_ms = int((time.time() - t0) * 1000)
    if err or not raw_path:
        return {"ok": False, "voice_id": voice_id, "file_path": None,
                      "audio_bytes": None, "char_count": char_count,
                      "latency_ms": latency_ms, "over_quota": False,
                      "error": err or "no_output"}

    # Count chars regardless of retries (we billed even on the failed try
    # would be wrong — only on success).  Counter is post-call to be
    # conservative.
    _bump_quota(char_count)
    log.info("[elevenlabs] ok voice=%s chars=%d ms=%d quota=%d/%d",
                          voice_id, char_count, latency_ms,
                          quota_state()["chars"], DAILY_CHAR_CAP)

    if out_path is not None:
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # raw_path is a fresh file produced by the SDK; move it.
            raw_path.replace(out_path)
        except Exception as e:
            return {"ok": False, "voice_id": voice_id, "file_path": None,
                          "audio_bytes": None, "char_count": char_count,
                          "latency_ms": latency_ms, "over_quota": False,
                          "error": f"move_failed:{e}"}
        return {"ok": True, "voice_id": voice_id, "file_path": out_path,
                      "audio_bytes": None, "char_count": char_count,
                      "latency_ms": latency_ms, "over_quota": False,
                      "error": None}

    # No out_path supplied — return bytes and clean up the temp.
    try:
        audio_bytes = raw_path.read_bytes()
    except Exception as e:
        return {"ok": False, "voice_id": voice_id, "file_path": None,
                      "audio_bytes": None, "char_count": char_count,
                      "latency_ms": latency_ms, "over_quota": False,
                      "error": f"read_failed:{e}"}
    try:
        raw_path.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True, "voice_id": voice_id, "file_path": None,
                  "audio_bytes": audio_bytes, "char_count": char_count,
                  "latency_ms": latency_ms, "over_quota": False,
                  "error": None}
