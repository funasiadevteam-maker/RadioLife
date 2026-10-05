"""Centralised env vars, paths, and tunable constants."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=False)

# Storage paths
STORAGE_DIR = ROOT_DIR / "storage"
TRACKS_DIR = STORAGE_DIR / "tracks"
RJ_DIR = STORAGE_DIR / "rj"
STREAMS_DIR = STORAGE_DIR / "streams"
SEGMENTS_DIR = STORAGE_DIR / "segments"
VOICE_PREVIEWS_DIR = STORAGE_DIR / "voice_previews"
SHARES_DIR = STORAGE_DIR / "shares"
SFX_DIR = STORAGE_DIR / "sfx"

for d in (TRACKS_DIR, RJ_DIR, STREAMS_DIR, SEGMENTS_DIR,
          VOICE_PREVIEWS_DIR, SHARES_DIR, SFX_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Env
# Phase Ω — Deploy hardening (2026-06-20):  never crash import if these
# env vars are missing.  K8s deploy timeouts trace back to bracket-
# notation env reads that raise KeyError → uvicorn boot fails → readiness
# probe never fires.  Safe defaults + config_check endpoint surface the
# mis-configuration without blocking boot.
MONGO_URL = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME    = os.environ.get("DB_NAME")      or "bigfm"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# Emergent Universal LLM key — routes OpenAI CHAT/TEXT generation through the
# Emergent LiteLLM proxy so RJ / script generation keeps working without a
# BYOK OpenAI balance. (Chat-completions ONLY — not OpenAI TTS/image, which
# are not proxied here.)
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
EMERGENT_LLM_BASE_URL = (os.environ.get("EMERGENT_LLM_BASE_URL")
                         or "https://integrations.emergentagent.com/llm")
LLM_VIA_EMERGENT = bool(EMERGENT_LLM_KEY)
LLM_TEXT_AVAILABLE = bool(EMERGENT_LLM_KEY or OPENAI_API_KEY)


def make_openai_client():
    """OpenAI client for chat/text generation. Prefers the Emergent Universal
    key (via the proxy base_url); falls back to the BYOK OPENAI_API_KEY; else
    None. Chat-completions only."""
    from openai import OpenAI
    if EMERGENT_LLM_KEY:
        return OpenAI(api_key=EMERGENT_LLM_KEY, base_url=EMERGENT_LLM_BASE_URL)
    if OPENAI_API_KEY:
        return OpenAI(api_key=OPENAI_API_KEY)
    return None


ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "sk_test_emergent")
STRIPE_MODE = os.environ.get("STRIPE_MODE", "test").lower()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# ElevenLabs
ELEVEN_MODEL_ID = "eleven_v3"
ELEVEN_FALLBACK_MODEL = "eleven_multilingual_v2"
ELEVEN_OUTPUT_FORMAT = "mp3_44100_192"

# RJ tunables
MAX_RJ_SECONDS = 45.0
RJ_RESHORTEN_THRESHOLD = 42.0
SPEECH_WORDS_PER_SEC = 2.5
DUO_PROBABILITY = 0.30

# Voice settings by energy — Phase 3.5 bumps "party" further for Mirchi-style
# club-DJ delivery: lower stability + max style = highly dynamic shouts.
VOICE_SETTINGS_BY_ENERGY = {
    "chill":  {"stability": 0.50, "similarity_boost": 0.85, "style": 0.40, "use_speaker_boost": True},
    "medium": {"stability": 0.35, "similarity_boost": 0.80, "style": 0.55, "use_speaker_boost": True},
    "high":   {"stability": 0.18, "similarity_boost": 0.72, "style": 0.85, "use_speaker_boost": True},
    "party":  {"stability": 0.10, "similarity_boost": 0.62, "style": 0.97, "use_speaker_boost": True},
}
DEFAULT_ENERGY = "medium"
ENERGY_LEVELS = ("chill", "medium", "high", "party")
MOOD_TAGS = ("romantic", "energetic", "melancholy", "uplifting", "dance", "groove", "intense")
