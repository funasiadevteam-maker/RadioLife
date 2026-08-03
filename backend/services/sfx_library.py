"""Phase 3.5 — Sound design library for Mirchi-style party transitions.

Generates a small library of party SFX (crowd cheers, whooshes, airhorns,
drum rolls, record scratches, bass drops, vocal shouts) ONCE at first boot,
then reuses the files forever. Lazy + cached: if generation fails, the
party transition pipeline gracefully degrades to no-SFX.

Generation uses:
- ElevenLabs Sound Generation API for the instrumental SFX
  (`POST /v1/sound-generation`, model `eleven_text_to_sound_v2`)
- ElevenLabs TTS (eleven_v3) for vocal shouts (DJ Charlie + DJ Riya)

All files land under `/app/backend/storage/sfx/library/<name>.mp3`.
"""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from audio_pipeline import ffprobe_duration, truncate_audio
from core.config import (
    ELEVEN_FALLBACK_MODEL, ELEVEN_MODEL_ID, ELEVEN_OUTPUT_FORMAT,
    ELEVENLABS_API_KEY, SFX_DIR,
)

logger = logging.getLogger("bigfm.sfx_library")

LIBRARY_DIR = SFX_DIR / "library"
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

# Each entry: name → (prompt, duration_sec, kind). kind: "sound" or "tts".
SFX_SPECS: Dict[str, Tuple[str, float, str]] = {
    # Instrumental SFX (via Sound Generation API)
    "crowd_cheer_1":    ("short crowd cheering, party, 1.5 seconds, energetic, no music", 1.6, "sound"),
    "crowd_cheer_2":    ("club crowd hyped, whoops and screams, 1.5 seconds, dense", 1.6, "sound"),
    "crowd_cheer_3":    ("festival crowd roar, 1.5 seconds, peak energy, no music", 1.6, "sound"),
    "whoosh_1":         ("fast whoosh sweep effect 0.5 seconds, transition", 0.6, "sound"),
    "whoosh_2":         ("riser whoosh transition 0.5 seconds, sharp", 0.6, "sound"),
    "whoosh_3":         ("downsweep whoosh transition 0.5 seconds, deep", 0.6, "sound"),
    "airhorn_1":        ("DJ air horn party callout 1 second, single blast, classic reggae siren", 1.0, "sound"),
    "airhorn_2":        ("double air horn dancehall, 1 second, party hype", 1.0, "sound"),
    "drumroll_short":   ("snare drum roll buildup 1.2 seconds, accelerating, no cymbals", 1.3, "sound"),
    "drumroll_long":    ("snare drum roll buildup 2 seconds, accelerating to climax, no cymbals", 2.1, "sound"),
    "record_scratch":   ("vinyl record scratch transition, 0.6 seconds, sharp DJ effect, no music", 0.7, "sound"),
    "bass_drop":        ("bass drop sub kick 0.5 seconds, deep punchy lead-in, EDM", 0.6, "sound"),

    # Vocal shouts (via TTS with extreme party settings)
    "vocal_shout_DUBAI": ("[hyped] DUBAI!!! [shouts] LET'S GOOO!!", 0.9, "tts"),
    "vocal_shout_WAH":   ("[hyped] WAH!! [excited] WAH WAH WAH!!", 0.7, "tts"),
}

# Voice id for vocal shouts (DJ Charlie persona — Australian club MC). We use
# eleven_v3 with extreme party voice settings.
VOCAL_SHOUT_VOICE_ID = "IKne3meq5aSn9XLyUdCD"  # DJ Charlie

# Extreme party voice settings — max expressiveness, low stability for shouts.
SHOUT_VOICE_SETTINGS = {
    "stability": 0.08,
    "similarity_boost": 0.55,
    "style": 0.99,
    "use_speaker_boost": True,
}

# Sound generation API endpoint + model
_SOUND_GEN_URL = "https://api.elevenlabs.io/v1/sound-generation"
_SOUND_GEN_MODEL = "eleven_text_to_sound_v2"  # also acceptable: omit for default

# In-process flag: have we kicked off the generation yet?
_GENERATION_STARTED = False
_GENERATION_DONE = False


def library_path(name: str) -> Path:
    return LIBRARY_DIR / f"{name}.mp3"


def has(name: str) -> bool:
    p = library_path(name)
    try:
        return p.exists() and p.stat().st_size > 200
    except Exception:
        return False


def existing_files() -> Dict[str, Path]:
    """Return {name: path} for every SFX file currently on disk."""
    return {name: library_path(name) for name in SFX_SPECS if has(name)}


def pick_random(*names: str) -> Optional[Path]:
    """Pick a random existing file from the listed names. None if none exist."""
    candidates = [library_path(n) for n in names if has(n)]
    if not candidates:
        return None
    return random.choice(candidates)


def _generate_sound_effect(name: str, prompt: str, duration_sec: float) -> Optional[Path]:
    if not ELEVENLABS_API_KEY:
        return None
    out = library_path(name)
    try:
        r = requests.post(
            _SOUND_GEN_URL,
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "accept": "audio/mpeg",
            },
            json={
                "text": prompt,
                "duration_seconds": min(max(duration_sec, 0.5), 22.0),
                "prompt_influence": 0.6,
            },
            timeout=60,
        )
        if r.status_code != 200:
            logger.warning(f"Sound-gen {name} HTTP {r.status_code}: {r.text[:200]}")
            return None
        with open(out, "wb") as f:
            f.write(r.content)
        # Cap exact duration with a quick fade-out (ElevenLabs sometimes overshoots)
        try:
            truncate_audio(out, duration_sec, fade_out_ms=80)
        except Exception:
            pass
        logger.info(f"SFX generated: {name} ({duration_sec:.2f}s)")
        return out
    except Exception as e:
        logger.warning(f"Sound-gen {name} failed: {e}")
        return None


def _generate_tts_shout(name: str, script: str, duration_sec: float) -> Optional[Path]:
    if not ELEVENLABS_API_KEY:
        return None
    try:
        from elevenlabs import ElevenLabs, VoiceSettings
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        voice_settings = VoiceSettings(**SHOUT_VOICE_SETTINGS)
        out = library_path(name)
        try:
            audio_iter = client.text_to_speech.convert(
                voice_id=VOCAL_SHOUT_VOICE_ID, model_id=ELEVEN_MODEL_ID, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
            )
        except Exception:
            audio_iter = client.text_to_speech.convert(
                voice_id=VOCAL_SHOUT_VOICE_ID, model_id=ELEVEN_FALLBACK_MODEL, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
            )
        with open(out, "wb") as f:
            for chunk in audio_iter:
                if chunk:
                    f.write(chunk)
        # Trim long tails so the shout is punchy
        try:
            truncate_audio(out, duration_sec + 0.3, fade_out_ms=80)
        except Exception:
            pass
        logger.info(f"SFX vocal shout generated: {name}")
        return out
    except Exception as e:
        logger.warning(f"Vocal shout {name} failed: {e}")
        return None


def ensure_library_blocking() -> int:
    """Generate any missing SFX files. Returns the count created.

    Runs synchronously — call from a background task at startup, not at request
    time. Safe to call multiple times (skips files that already exist).
    """
    created = 0
    for name, (prompt, dur, kind) in SFX_SPECS.items():
        if has(name):
            continue
        if kind == "tts":
            p = _generate_tts_shout(name, prompt, dur)
        else:
            p = _generate_sound_effect(name, prompt, dur)
        if p is not None:
            created += 1
        # gentle pacing so we don't hammer the API
        time.sleep(0.2)
    return created


async def ensure_library_async() -> int:
    """Async wrapper that offloads ensure_library_blocking to a thread."""
    import asyncio
    global _GENERATION_STARTED, _GENERATION_DONE
    if _GENERATION_STARTED:
        return 0
    _GENERATION_STARTED = True
    try:
        n = await asyncio.to_thread(ensure_library_blocking)
        _GENERATION_DONE = True
        logger.info(f"SFX library: created {n} new files; total on disk: {len(existing_files())}/{len(SFX_SPECS)}")
        return n
    except Exception as e:
        logger.warning(f"ensure_library_async error: {e}")
        return 0


def library_status() -> dict:
    on_disk = existing_files()
    return {
        "total_expected": len(SFX_SPECS),
        "on_disk": len(on_disk),
        "missing": sorted(set(SFX_SPECS) - set(on_disk)),
        "generation_started": _GENERATION_STARTED,
        "generation_done": _GENERATION_DONE,
    }
