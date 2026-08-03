"""Phase 3.6 — OpenAI TTS synthesis (gpt-4o-mini-tts).

Wraps `client.audio.speech.create` with the project's OPENAI_API_KEY and the
voice's `instructions` parameter for delivery style. Returns a Path to an
MP3 on disk.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from openai import OpenAI

from audio_pipeline import new_uuid_filename, truncate_audio
from core.config import OPENAI_API_KEY, MAX_RJ_SECONDS, RJ_DIR
from services.voice_config import OPENAI_TTS_VOICES

logger = logging.getLogger("bigfm.openai_tts")

_OPENAI_CLIENT: Optional[OpenAI] = None
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"


def _client() -> OpenAI:
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
    return _OPENAI_CLIENT


def synthesize_openai(
    text: str,
    voice_key: str,
    *,
    out_dir: Optional[Path] = None,
    max_seconds: Optional[float] = None,
    extra_instructions: Optional[str] = None,
) -> Path:
    """Render `text` through OpenAI TTS for the given voice_key.
    Returns the path to a fresh MP3. Raises on error.
    """
    cfg = OPENAI_TTS_VOICES.get(voice_key)
    if not cfg:
        raise ValueError(f"unknown OpenAI TTS voice_key '{voice_key}'")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")
    voice = cfg["openai_voice"]
    instructions = cfg.get("instructions") or ""
    if extra_instructions:
        instructions = f"{instructions} {extra_instructions}".strip()
    target_dir = out_dir or RJ_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / new_uuid_filename("mp3")

    resp = _client().audio.speech.create(
        model=OPENAI_TTS_MODEL,
        voice=voice,
        input=text,
        instructions=instructions,
        response_format="mp3",
    )
    out_path.write_bytes(resp.content)
    # Soft cap on duration (OpenAI usually obeys, but truncate as a safety net)
    cap = max_seconds if max_seconds is not None else MAX_RJ_SECONDS
    try:
        truncate_audio(out_path, cap, fade_out_ms=200)
    except Exception as e:
        logger.debug(f"OpenAI TTS truncate failed (non-fatal): {e}")
    return out_path
