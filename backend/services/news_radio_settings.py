"""News Radio anchor-voice selection (admin-configurable).

Persists the chosen ElevenLabs anchor voice in the `app_settings`
collection so `synthesize_news_audio` narrates every shared clip in the
selected voice. Changing the voice invalidates cached clips so the next
batch re-renders them in the new voice.
"""
from __future__ import annotations

from typing import Any, Optional

# Curated ElevenLabs anchor voices — all part of the shared default library
# so any account key can synthesize with them.
CURATED_ANCHOR_VOICES = [
    {"voice_id": "8vqXJx9Riwp7L4KLhsU3", "name": "Raghav",
     "description": "Warm South-Asian news anchor (default)"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah",
     "description": "Mature, reassuring, confident"},
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George",
     "description": "Warm, captivating storyteller"},
    {"voice_id": "CwhRBWXzGAHq8TQ4Fs17", "name": "Roger",
     "description": "Laid-back, resonant"},
    {"voice_id": "IKne3meq5aSn9XLyUdCD", "name": "Charlie",
     "description": "Deep, confident, energetic"},
]
DEFAULT_ANCHOR_VOICE_ID = CURATED_ANCHOR_VOICES[0]["voice_id"]
_SETTINGS_ID = "news_radio"
_EPOCH = "1970-01-01T00:00:00+00:00"


def _voice_name(voice_id: str) -> Optional[str]:
    return next((v["name"] for v in CURATED_ANCHOR_VOICES
                 if v["voice_id"] == voice_id), None)


async def get_anchor_voice(db: Any) -> dict:
    doc = await db.app_settings.find_one({"_id": _SETTINGS_ID}) or {}
    vid = doc.get("anchor_voice_id") or DEFAULT_ANCHOR_VOICE_ID
    return {"voice_id": vid, "name": _voice_name(vid) or "Raghav"}


async def set_anchor_voice(db: Any, voice_id: str) -> dict:
    if voice_id not in {v["voice_id"] for v in CURATED_ANCHOR_VOICES}:
        raise ValueError("unknown_voice")
    await db.app_settings.update_one(
        {"_id": _SETTINGS_ID},
        {"$set": {"anchor_voice_id": voice_id,
                  "anchor_voice_name": _voice_name(voice_id)}},
        upsert=True)
    # Invalidate cached clips so the next batch re-renders them in the new
    # voice (expire them retroactively).
    await db.news_articles.update_many(
        {"news_audio_url": {"$nin": [None, ""]}},
        {"$set": {"news_audio_expires_at": _EPOCH}})
    return {"voice_id": voice_id, "name": _voice_name(voice_id)}
