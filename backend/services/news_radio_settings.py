"""Anchor-voice registry + selection for News Radio and station intros.

Persists the chosen ElevenLabs voice(s) in the `app_settings` collection:
  • a global default anchor voice, and
  • optional per-market overrides (e.g. Hindi voice for Dubai, English for
    US markets) so local news auto-narrates in a fitting accent.
Changing a voice invalidates the affected cached clips so the next batch
re-renders them in the new voice.
"""
from __future__ import annotations

from typing import Any, Optional

# Curated ElevenLabs voices — all part of the shared default library so any
# account key can synthesize with them. `language` drives the per-market
# auto-pick and the station-intro default.
CURATED_ANCHOR_VOICES = [
    {"voice_id": "8vqXJx9Riwp7L4KLhsU3", "name": "Raghav",
     "description": "Warm South-Asian news anchor", "language": "hi"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah",
     "description": "Mature, reassuring, confident", "language": "en"},
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George",
     "description": "Warm, captivating storyteller", "language": "en"},
    {"voice_id": "CwhRBWXzGAHq8TQ4Fs17", "name": "Roger",
     "description": "Laid-back, resonant", "language": "en"},
    {"voice_id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie",
     "description": "Deep, confident, energetic", "language": "en"},
]
DEFAULT_ANCHOR_VOICE_ID = CURATED_ANCHOR_VOICES[0]["voice_id"]

# Auto anchor voice per known market (Hindi vs English local news).
MARKET_VOICE_DEFAULTS = {
    "dubai":    "8vqXJx9Riwp7L4KLhsU3",   # Raghav — Hindi/South-Asian
    "dfw":      "EXAVITQu4vr4xnSDxMaL",   # Sarah — US English
    "new_york": "EXAVITQu4vr4xnSDxMaL",   # Sarah — US English
}

VOICE_SAMPLE_PREFIX = "/api/static/voice_samples"
SAMPLE_LINE = ("Hi, I'm your RadioLife anchor. Here's what's happening "
               "around you right now.")

_SETTINGS_ID = "news_radio"
_EPOCH = "1970-01-01T00:00:00+00:00"


def _voice_name(voice_id: str) -> Optional[str]:
    return next((v["name"] for v in CURATED_ANCHOR_VOICES
                 if v["voice_id"] == voice_id), None)


def voice_sample_url(voice_id: str) -> str:
    return f"{VOICE_SAMPLE_PREFIX}/{voice_id}.mp3"


def is_valid_voice(voice_id: Optional[str]) -> bool:
    return voice_id in {v["voice_id"] for v in CURATED_ANCHOR_VOICES}


def list_voices() -> list:
    """Curated voices annotated with a preview sample URL."""
    return [{**v, "sample_url": voice_sample_url(v["voice_id"])}
            for v in CURATED_ANCHOR_VOICES]


async def get_anchor_voice(db: Any, market: Optional[str] = None) -> dict:
    """Resolve the anchor voice: admin per-market override → built-in
    market default → global default → hard default."""
    doc = await db.app_settings.find_one({"_id": _SETTINGS_ID}) or {}
    market_voices = doc.get("market_voices") or {}
    vid = None
    if market:
        vid = market_voices.get(market) or MARKET_VOICE_DEFAULTS.get(market)
    vid = vid or doc.get("anchor_voice_id") or DEFAULT_ANCHOR_VOICE_ID
    return {"voice_id": vid, "name": _voice_name(vid) or "Raghav"}


async def get_voice_config(db: Any) -> dict:
    doc = await db.app_settings.find_one({"_id": _SETTINGS_ID}) or {}
    return {
        "global_voice_id": doc.get("anchor_voice_id") or DEFAULT_ANCHOR_VOICE_ID,
        "market_voices": {**MARKET_VOICE_DEFAULTS,
                          **(doc.get("market_voices") or {})},
    }


async def set_anchor_voice(db: Any, voice_id: str,
                           market: Optional[str] = None) -> dict:
    """Set the global anchor voice, or (when `market` is given) a per-market
    override. Invalidates the affected cached clips for re-render."""
    if not is_valid_voice(voice_id):
        raise ValueError("unknown_voice")
    if market:
        await db.app_settings.update_one(
            {"_id": _SETTINGS_ID},
            {"$set": {f"market_voices.{market}": voice_id}}, upsert=True)
        await db.news_articles.update_many(
            {"market": market, "news_audio_url": {"$nin": [None, ""]}},
            {"$set": {"news_audio_expires_at": _EPOCH}})
    else:
        await db.app_settings.update_one(
            {"_id": _SETTINGS_ID},
            {"$set": {"anchor_voice_id": voice_id,
                      "anchor_voice_name": _voice_name(voice_id)}},
            upsert=True)
        await db.news_articles.update_many(
            {"news_audio_url": {"$nin": [None, ""]}},
            {"$set": {"news_audio_expires_at": _EPOCH}})
    return {"voice_id": voice_id, "name": _voice_name(voice_id), "market": market}
