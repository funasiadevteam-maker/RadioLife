"""Phase 3.6 — Unified multi-provider voice registry.

Each voice has a `provider` ("openai_tts" or "elevenlabs"), the provider-
specific identifier, an `accent_target` for the script generator, and the
energies/languages it fits.

The synthesis layer reads from this single source of truth.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

# Accent targets influence the OpenAI script generation prompt:
#   "american"      → 90% English, sprinkle yaar/boss/dosto for Dubai authenticity
#   "indian_english"→ 90% English, slight Indian inflection vocabulary
#   "hindi_native"  → 90% Hindi (Roman script), English only for brand names
#   "hinglish"      → free mix (existing behaviour)
#   "punjabi"       → Punjabi-first
#   "devotional"    → Sanskrit-leaning, calm
ACCENT_TARGETS = ("american", "indian_english", "hindi_native", "hinglish", "punjabi", "devotional")

# --- Provider-A: OpenAI TTS (gpt-4o-mini-tts) -----------------------------
# These are SOTA-natural for English party hype.
OPENAI_TTS_VOICES: Dict[str, dict] = {
    "charlie_dj": {
        "provider": "openai_tts",
        "openai_voice": "ash",
        "instructions": (
            "You are an energetic American club DJ broadcasting from Dubai. "
            "Maximum hype, party energy. Shout the lines like a real club MC. "
            "Channel American-Indian DJ vibe. Confident, loud, magnetic."
        ),
        "display_name": "DJ Charlie",
        "persona": "American-Indian club DJ, late 20s, party hype voice, FUUSIC",
        "duo_label": "CHARLIE",
        "duo_blurb": "American-Indian club DJ, late-20s, Dubai-based, hyped party MC. Always shouting boss/yaar.",
        "accent_target": "american",
        "for_languages": ["english", "hinglish"],
        "fits_energies": ("high", "party"),
    },
    "riya_dj": {
        "provider": "openai_tts",
        "openai_voice": "nova",
        "instructions": (
            "You are a bubbly Indian-American female club DJ in her late 20s, "
            "broadcasting from a Dubai nightclub. Bright, peppy, hyped energy. "
            "Sound like you're having the best night of your life."
        ),
        "display_name": "DJ Riya",
        "persona": "Indian-American female DJ, late 20s, bubbly + hyped, Dubai club scene",
        "duo_label": "RIYA",
        "duo_blurb": "Indian-American female DJ, late-20s, bubbly Dubai club energy. The hype-builder.",
        "accent_target": "american",
        "for_languages": ["english", "hinglish"],
        "fits_energies": ("high", "party"),
    },
    "marcus_dj": {
        "provider": "openai_tts",
        "openai_voice": "onyx",
        "instructions": (
            "You are a deep-voiced American male radio host with a late-night "
            "Dubai vibe. Smooth, confident, sometimes hyped. Think a US "
            "broadcaster who moved to Dubai. Warm, magnetic baritone."
        ),
        "display_name": "Marcus",
        "persona": "American male radio host, deep baritone, late-night Dubai vibe",
        "duo_label": "MARCUS",
        "duo_blurb": "American male radio host, 30s, deep baritone, late-night Dubai charm.",
        "accent_target": "american",
        "for_languages": ["english", "hinglish"],
        "fits_energies": ("medium", "high"),
    },
    "aisha_english": {
        "provider": "openai_tts",
        "openai_voice": "coral",
        "instructions": (
            "You are a warm Indian-American female radio host in her mid-20s. "
            "Conversational, friendly, premium hotel-lounge vibe. Speak with "
            "warmth and confidence, never rushed."
        ),
        "display_name": "Aisha",
        "persona": "Indian-American female radio host, mid 20s, warm + premium",
        "duo_label": "AISHA",
        "duo_blurb": "Indian-American female host, mid-20s, warm conversational, VIP lounge vibe.",
        "accent_target": "american",
        "for_languages": ["english", "hinglish"],
        "fits_energies": ("chill", "medium"),
    },
}

# --- Provider-B: ElevenLabs (existing + new native Hindi voices) ----------
ELEVENLABS_VOICES: Dict[str, dict] = {
    # 4 new native Hindi voices (Phase 3.6 picks)
    "raghav_hindi": {
        "provider": "elevenlabs",
        "voice_id": "8vqXJx9Riwp7L4KLhsU3",  # Armaan — Funny & Expressive Vlogger
        "display_name": "Raghav",
        "persona": "young Hindi-native male, expressive, Mumbai-Delhi belt vibe, conversational",
        "duo_label": "RAGHAV",
        "duo_blurb": "young Hindi-native male, late 20s, expressive vlogger energy. Pure Hindi delivery.",
        "accent_target": "hindi_native",
        "for_languages": ["hindi"],
        "fits_energies": ("medium", "high"),
    },
    "aanya_hindi": {
        "provider": "elevenlabs",
        "voice_id": "HS8CUZ9Cpfs4IW3AUJKT",  # Tripti — Natural & Conversational Bot
        "display_name": "Aanya",
        "persona": "young Hindi-native female, natural conversational warmth, Delhi origin",
        "duo_label": "AANYA",
        "duo_blurb": "young Hindi-native female, mid-20s, warm conversational. Pure Hindi.",
        "accent_target": "hindi_native",
        "for_languages": ["hindi"],
        "fits_energies": ("chill", "medium"),
    },
    "kabir_hindi": {
        "provider": "elevenlabs",
        "voice_id": "ORVNcvnT1UwPA7XQ29WD",  # Kuber J — Bold Energetic Hindi Narrator
        "display_name": "Kabir",
        "persona": "young Hindi-native male, bold + energetic, party MC, Delhi-Mumbai DJ vibe",
        "duo_label": "KABIR",
        "duo_blurb": "young Hindi-native male, bold + energetic, party DJ delivery. Hindi-first.",
        "accent_target": "hindi_native",
        "for_languages": ["hindi"],
        "fits_energies": ("high", "party"),
    },
    "ishita_hindi": {
        "provider": "elevenlabs",
        "voice_id": "tA6LGZpsqStKtSaGiXND",  # Tara — Hindi Reels Explainer Style
        "display_name": "Ishita",
        "persona": "young Hindi-native female, peppy reels-style, social-media energy",
        "duo_label": "ISHITA",
        "duo_blurb": "young Hindi-native female, peppy reels-style, party-ready Hindi delivery.",
        "accent_target": "hindi_native",
        "for_languages": ["hindi"],
        "fits_energies": ("high", "party"),
    },

    # ---------- Existing Phase 0/1 hosts — mark for Hinglish ----------
    "veer_dubai": {
        "provider": "elevenlabs",
        "voice_id": "1WrEi9ztXQkVmKgG6j9A",
        "display_name": "Veer",
        "persona": "male, late-night radio voice, intimate and charming, Mumbai-Dubai NRI",
        "duo_label": "VEER",
        "duo_blurb": "smooth late-night charm, late-30s, Mumbai-origin, lives in Bur Dubai.",
        "accent_target": "hinglish",
        "for_languages": ["hinglish"],
        "fits_energies": ("chill", "medium"),
    },
    "monika_dubai": {
        "provider": "elevenlabs",
        "voice_id": "rCmVtv8cYU60uhlsOo1M",
        "display_name": "Monika",
        "persona": "warm British-Indian female, modulated, brunch-and-chai friend energy",
        "duo_label": "MONIKA",
        "duo_blurb": "warm Delhi-origin, mid-20s, lives in JLT. High-energy, bubbly.",
        "accent_target": "hinglish",
        "for_languages": ["hinglish"],
        "fits_energies": ("chill", "medium"),
    },

    # ---------- Existing Phase 2 extended hosts ----------
    "aarti_morning": {
        "provider": "elevenlabs",
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "display_name": "Aarti",
        "persona": "bubbly morning show female, Delhi-origin, fast peppy enthusiastic",
        "duo_label": "AARTI",
        "duo_blurb": "Delhi-origin, mid-20s, peppy morning radio voice.",
        "accent_target": "hinglish",
        "for_languages": ["hinglish"],
        "fits_energies": ("medium", "high"),
    },
    "kishore_retro": {
        "provider": "elevenlabs",
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "display_name": "Kishore Da",
        "persona": "classic broadcaster, smooth drawl, late-80s AIR nostalgia",
        "duo_label": "KISHORE",
        "duo_blurb": "Classic broadcaster, late-80s AIR nostalgia, retro voice.",
        "accent_target": "hinglish",
        "for_languages": ["hinglish"],
        "fits_energies": ("chill", "medium"),
    },
    "pandit_anand": {
        "provider": "elevenlabs",
        "voice_id": "5Q0t7uMcjvnagumLfvZi",
        "display_name": "Pandit Anand",
        "persona": "55+ male, wisdom keeper, devotional broadcaster, slow warm baritone",
        "duo_label": "ANAND",
        "duo_blurb": "55+ devotional voice, slow warm baritone.",
        "accent_target": "devotional",
        "for_languages": ["hindi"],
        "fits_energies": ("chill",),
    },
    "gurpreet_bhaji": {
        "provider": "elevenlabs",
        "voice_id": "TX3LPaxmHKxFdv7VOQHJ",
        "display_name": "Gurpreet Bhaji",
        "persona": "Punjabi specialist male, Karama dhaba energy, hearty and loud",
        "duo_label": "GURPREET",
        "duo_blurb": "Punjabi-speaking male, Karama dhaba vibe, hearty + loud.",
        "accent_target": "punjabi",
        "for_languages": ["punjabi", "hinglish"],
        "fits_energies": ("medium", "high"),
    },
    "simran_punjabi": {
        "provider": "elevenlabs",
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "display_name": "Simran",
        "persona": "Punjabi female co-host, playful warm, teases Gurpreet",
        "duo_label": "SIMRAN",
        "duo_blurb": "Punjabi female, playful warm, teases Gurpreet.",
        "accent_target": "punjabi",
        "for_languages": ["punjabi", "hinglish"],
        "fits_energies": ("medium", "high"),
    },
}

# Master registry — everything the rest of the app reads from.
VOICE_REGISTRY: Dict[str, dict] = {**OPENAI_TTS_VOICES, **ELEVENLABS_VOICES}

# Default voice when nothing else fits.
DEFAULT_VOICE_KEY = "veer_dubai"


def get_voice(key: str) -> Optional[dict]:
    return VOICE_REGISTRY.get(key)


def voice_provider(key: str) -> str:
    v = VOICE_REGISTRY.get(key) or {}
    return v.get("provider", "elevenlabs")


def voices_for_language(lang: str) -> List[str]:
    lang = (lang or "").lower()
    return [k for k, v in VOICE_REGISTRY.items() if lang in v.get("for_languages", [])]


def voices_for_energy(energy: str) -> List[str]:
    return [k for k, v in VOICE_REGISTRY.items() if energy in v.get("fits_energies", ())]


def pick_voice_for_lang_and_energy(lang: str, energy: str) -> str:
    """Best-effort: pick a voice that matches BOTH language and energy. Falls
    back to language-only, then default."""
    by_lang = set(voices_for_language(lang))
    by_energy = set(voices_for_energy(energy))
    common = by_lang & by_energy
    if common:
        return random.choice(sorted(common))
    if by_lang:
        return random.choice(sorted(by_lang))
    return DEFAULT_VOICE_KEY


# ---------- Voice preview scripts (per-language) ----------
PREVIEW_SCRIPTS_BY_ACCENT = {
    "american": "Hands in the air! You're locked into FUUSIC — non-stop hits, all night long. Let's go!",
    "indian_english": "Welcome to FUUSIC. Your home for music, mehfil, and the very best of the night.",
    "hindi_native": "Namaste! Aap sun rahe hain FUUSIC par. Aaj raat ki party shuru ho chuki hai, hands up doston!",
    "hinglish": "[warm] Aap sun rahe ho... [excited] FUUSIC! [warm] Dil se, doston.",
    "punjabi": "Sat sri akal! Tussi sun rahe ho FUUSIC, je kal raat di party shuru ho gayi hai!",
    "devotional": "[warm] Aap sun rahe hain... [soft] FUUSIC par bhakti sangeet. Om shanti.",
}


def preview_script_for(voice_key: str) -> str:
    v = VOICE_REGISTRY.get(voice_key) or {}
    accent = v.get("accent_target", "hinglish")
    # Per-voice override hook for richer demos
    overrides = {
        "charlie_dj":      "HANDS IN THE AIR! You are LOCKED IN to FUUSIC — non-stop party, all night long. Let's GOOO!",
        "riya_dj":         "Hey hey! It's your girl Riya on FUUSIC — the night is JUST getting started, boss!",
        "marcus_dj":       "Late night vibes... this is Marcus on FUUSIC. Smooth ride, all the way home.",
        "aisha_english":   "Welcome to FUUSIC. Your premium soundtrack — handpicked for the moment.",
        "raghav_hindi":    "Namaste! Yeh hai Raghav, FUUSIC par. Aaj ka mood mast hai, gaana sun lo!",
        "aanya_hindi":     "Aap sun rahe hain FUUSIC. Main hoon Aanya, aapki shaam ki saheli.",
        "kabir_hindi":     "Yeh hai Kabir, FUUSIC par! Hands up dosto, aaj raat ki party shuru hai!",
        "ishita_hindi":    "Hello! Main hoon Ishita, FUUSIC par. Mast vibe, full energy — ready ho?",
    }
    if voice_key in overrides:
        return overrides[voice_key]
    return PREVIEW_SCRIPTS_BY_ACCENT.get(accent, PREVIEW_SCRIPTS_BY_ACCENT["hinglish"])
