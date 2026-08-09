"""Phase 3.5 — Pre-generated station ID stings for Mirchi-style party rotation.

Generates 10 short (1-2s) RadioLife station-ID stings via ElevenLabs TTS
at first boot, then randomly picks one between songs on party channels.
Idempotent — skips files that already exist.
"""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import List, Optional

from audio_pipeline import ffprobe_duration, truncate_audio
from core.config import (
    ELEVEN_FALLBACK_MODEL, ELEVEN_MODEL_ID, ELEVEN_OUTPUT_FORMAT,
    ELEVENLABS_API_KEY, SFX_DIR,
)

logger = logging.getLogger("bigfm.station_ids")

STATION_ID_DIR = SFX_DIR / "station_id"
STATION_ID_DIR.mkdir(parents=True, exist_ok=True)

# Voice IDs from services/voices.py — replicated here to avoid circular import.
# Each entry: (filename, voice_id, script, max_seconds)
STATION_IDS: List[tuple] = [
    ("sid_01", "IKne3meq5aSn9XLyUdCD", "[hyped] You're listening to RadioLife!", 2.4),                              # DJ Charlie
    ("sid_02", "AZnzlk1XvdvUeBnXmlld", "[excited] RadioLife... [hyped] dil se!", 2.4),                              # DJ Riya
    ("sid_03", "IKne3meq5aSn9XLyUdCD", "[shouts] The number ONE party station — RadioLife!!", 2.6),                 # DJ Charlie
    ("sid_04", "IKne3meq5aSn9XLyUdCD", "[hyped] Non-stop hits, [excited] RadioLife!", 2.4),                         # DJ Charlie
    ("sid_05", "1WrEi9ztXQkVmKgG6j9A", "[playful] RadioLife, [chuckles] aap sun rahe ho!", 2.6),                    # Veer
    ("sid_06", "rCmVtv8cYU60uhlsOo1M", "[warm] RadioLife. [excited] Music chalega NON-stop!", 2.6),                 # Monika
    ("sid_07", "AZnzlk1XvdvUeBnXmlld", "[hyped] Bollywood, beats — RadioLife!", 2.4),                               # DJ Riya
    ("sid_08", "IKne3meq5aSn9XLyUdCD", "[shouts] You. Are. ON. RadioLife!!", 2.4),                                   # DJ Charlie
    ("sid_09", "rCmVtv8cYU60uhlsOo1M", "[whispers] RadioLife... [excited] aur ye gaana sun lo!", 2.8),              # Monika
    ("sid_10", "IKne3meq5aSn9XLyUdCD", "[hyped] Dance. Party. Repeat. [shouts] RadioLife!", 2.6),                    # DJ Charlie
]

# Energetic voice settings — these are radio drops, not radio shows.
STATION_ID_VOICE_SETTINGS = {
    "stability": 0.12,
    "similarity_boost": 0.62,
    "style": 0.95,
    "use_speaker_boost": True,
}

_GENERATION_STARTED = False
_GENERATION_DONE = False


def station_id_path(slug: str) -> Path:
    return STATION_ID_DIR / f"{slug}.mp3"


def _has(slug: str) -> bool:
    p = station_id_path(slug)
    try:
        return p.exists() and p.stat().st_size > 200
    except Exception:
        return False


def existing_station_ids() -> List[Path]:
    return [station_id_path(slug) for slug, *_ in STATION_IDS if _has(slug)]


def pick_random_station_id() -> Optional[Path]:
    paths = existing_station_ids()
    if not paths:
        return None
    return random.choice(paths)


def _generate_one(slug: str, voice_id: str, script: str, max_sec: float) -> Optional[Path]:
    if not ELEVENLABS_API_KEY:
        return None
    try:
        from elevenlabs import ElevenLabs, VoiceSettings
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        voice_settings = VoiceSettings(**STATION_ID_VOICE_SETTINGS)
        out = station_id_path(slug)
        try:
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_id, model_id=ELEVEN_MODEL_ID, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
            )
        except Exception:
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_id, model_id=ELEVEN_FALLBACK_MODEL, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
            )
        with open(out, "wb") as f:
            for chunk in audio_iter:
                if chunk:
                    f.write(chunk)
        try:
            truncate_audio(out, max_sec, fade_out_ms=120)
        except Exception:
            pass
        dur = ffprobe_duration(out) if out.exists() else 0.0
        logger.info(f"Station ID generated: {slug} ({dur:.2f}s) — '{script[:48]}…'")
        return out
    except Exception as e:
        logger.warning(f"Station ID {slug} failed: {e}")
        return None


def ensure_station_ids_blocking() -> int:
    created = 0
    for slug, voice_id, script, max_sec in STATION_IDS:
        if _has(slug):
            continue
        if _generate_one(slug, voice_id, script, max_sec) is not None:
            created += 1
        time.sleep(0.2)
    return created


async def ensure_station_ids_async() -> int:
    import asyncio
    global _GENERATION_STARTED, _GENERATION_DONE
    if _GENERATION_STARTED:
        return 0
    _GENERATION_STARTED = True
    try:
        n = await asyncio.to_thread(ensure_station_ids_blocking)
        _GENERATION_DONE = True
        logger.info(f"Station IDs: created {n} new; total on disk: {len(existing_station_ids())}/{len(STATION_IDS)}")
        return n
    except Exception as e:
        logger.warning(f"ensure_station_ids_async error: {e}")
        return 0


def station_ids_status() -> dict:
    return {
        "total_expected": len(STATION_IDS),
        "on_disk": len(existing_station_ids()),
        "generation_started": _GENERATION_STARTED,
        "generation_done": _GENERATION_DONE,
    }
