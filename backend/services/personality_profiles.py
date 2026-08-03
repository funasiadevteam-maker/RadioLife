"""Phase 3.7 — RJ Personality Profiles registry.

Seeded into the `rj_personality_profiles` Mongo collection at startup.
Each profile owns:
  - voice_direction_prompt — Stage 1 LLM system prompt
  - voice_settings_overrides — ElevenLabs voice settings overlay
  - tone_tags — for naturalness rewriter
  - recommended_voice_keys — preferred voices for this profile

The "Radio Naturalness Rewrite" Stage 2 prompt lives in `radio_naturalness.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("bigfm.personality")


PROFILES_SEED: List[dict] = [
    {
        "slug": "morning_drive",
        "name": "Morning Drive",
        "description": "Energetic, witty, fast-but-clear, traffic-aware, friendly, local",
        "tone_tags": ["energetic", "witty", "fast", "traffic_aware", "friendly", "local"],
        "voice_direction_prompt": (
            "Sound like a premium international morning radio host for an Indian "
            "diaspora audience. Natural Hinglish, confident, lively, quick rhythm, "
            "not childish. Mention the time of day, the commute, the weather subtly. "
            "Keep things upbeat but not screaming. 18-26 spoken seconds."
        ),
        "recommended_voice_keys": ["aanya_hindi", "aarti_morning", "riya_dj"],
        "voice_settings_overrides": {
            "stability": 0.40, "similarity_boost": 0.82, "style": 0.55, "use_speaker_boost": True,
        },
        "default_dayparts": ["morning_rise", "morning_drive"],
        "default_script_length_sec": 22,
    },
    {
        "slug": "lunch",
        "name": "Lunch Rush",
        "description": "Fun, foodie, social, conversational, offer-friendly",
        "tone_tags": ["fun", "foodie", "social", "conversational", "offer_friendly"],
        "voice_direction_prompt": (
            "Sound like a friendly urban RJ talking to office workers and commuters "
            "during lunch. Make food deals feel exciting but not salesy. Be warm and "
            "playful, like a colleague telling you where to eat. 18-24 spoken seconds."
        ),
        "recommended_voice_keys": ["riya_dj", "monika_dubai", "aisha_english"],
        "voice_settings_overrides": {
            "stability": 0.45, "similarity_boost": 0.80, "style": 0.50, "use_speaker_boost": True,
        },
        "default_dayparts": ["lunch_rush"],
        "default_script_length_sec": 20,
    },
    {
        "slug": "evening_drive",
        "name": "Evening Drive",
        "description": "High-energy, practical, local, entertaining",
        "tone_tags": ["high_energy", "practical", "local", "entertaining"],
        "voice_direction_prompt": (
            "Sound like a polished drive-time RJ with traffic awareness, music "
            "momentum, and local lifestyle energy. Listeners are commuting home — "
            "give them a reason to keep the radio on. Reference traffic and weekend "
            "plans naturally. 22-28 spoken seconds."
        ),
        "recommended_voice_keys": ["veer_dubai", "marcus_dj", "kabir_hindi"],
        "voice_settings_overrides": {
            "stability": 0.35, "similarity_boost": 0.78, "style": 0.65, "use_speaker_boost": True,
        },
        "default_dayparts": ["evening_drive"],
        "default_script_length_sec": 25,
    },
    {
        "slug": "nightlife",
        "name": "Nightlife",
        "description": "Bold, youthful, clubby, premium",
        "tone_tags": ["bold", "youthful", "clubby", "premium"],
        "voice_direction_prompt": (
            "Sound like a late-night international dance radio host with Indian club "
            "energy. Stylish, punchy, confident, not overhyped. The crowd is at the "
            "peak of the night — bring the heat but stay polished. 22-32 spoken seconds."
        ),
        "recommended_voice_keys": ["charlie_dj", "riya_dj", "kabir_hindi", "ishita_hindi"],
        "voice_settings_overrides": {
            "stability": 0.25, "similarity_boost": 0.72, "style": 0.85, "use_speaker_boost": True,
        },
        "default_dayparts": ["prime_social", "nightlife_mode"],
        "default_script_length_sec": 26,
    },
    {
        "slug": "chill_late_night",
        "name": "Chill Late Night",
        "description": "Smooth, intimate, calm, companion-like",
        "tone_tags": ["smooth", "intimate", "calm", "companion"],
        "voice_direction_prompt": (
            "Sound like a late-night FM host: warm, smooth, reflective, minimal "
            "interruptions, soft Hinglish. Listeners are winding down — be the "
            "voice keeping them company. 18-26 spoken seconds, no shouting."
        ),
        "recommended_voice_keys": ["veer_dubai", "monika_dubai", "aisha_english", "marcus_dj"],
        "voice_settings_overrides": {
            "stability": 0.55, "similarity_boost": 0.85, "style": 0.30, "use_speaker_boost": True,
        },
        "default_dayparts": ["overnight_lounge", "afternoon_reset"],
        "default_script_length_sec": 22,
    },
    {
        "slug": "talk_news",
        "name": "Talk / News",
        "description": "Credible, sharp, calm, authoritative",
        "tone_tags": ["credible", "sharp", "calm", "authoritative"],
        "voice_direction_prompt": (
            "Sound like a modern news/talk anchor with warmth. Clear Hinglish/English, "
            "not dramatic, no fake excitement, no unverified claims. State the topic, "
            "give two facts, ask a quick question, lead into the music. 20-26 spoken seconds."
        ),
        "recommended_voice_keys": ["kishore_retro", "pandit_anand", "marcus_dj"],
        "voice_settings_overrides": {
            "stability": 0.65, "similarity_boost": 0.88, "style": 0.25, "use_speaker_boost": True,
        },
        "default_dayparts": ["all_talk_dayparts"],
        "default_script_length_sec": 23,
    },
]


async def ensure_personality_indexes(db) -> None:
    await db.rj_personality_profiles.create_index("slug", unique=True)


async def seed_personality_profiles(db) -> int:
    """Upsert all 6 profiles. Returns count created."""
    created = 0
    now = datetime.now(timezone.utc)
    for p in PROFILES_SEED:
        doc = {**p, "active": True, "updated_at": now}
        res = await db.rj_personality_profiles.update_one(
            {"slug": p["slug"]},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        if res.upserted_id is not None:
            created += 1
    logger.info(f"Personality profiles seeded/refreshed (created {created}, total {len(PROFILES_SEED)})")
    return created


async def get_personality_profile(db, slug: str) -> Optional[dict]:
    return await db.rj_personality_profiles.find_one({"slug": slug, "active": True}, {"_id": 0})


async def list_personality_profiles(db) -> List[dict]:
    cur = db.rj_personality_profiles.find({"active": True}, {"_id": 0}).sort("slug", 1)
    return [d async for d in cur]


def profile_by_slug_sync(slug: str) -> Optional[dict]:
    """In-memory lookup against the seed (no Mongo round-trip)."""
    for p in PROFILES_SEED:
        if p["slug"] == slug:
            return p
    return None


# ---------- Channel / daypart / energy → profile routing ----------

def select_profile_slug(channel_slug: Optional[str], daypart: Optional[str],
                       energy: Optional[str], dubai_hour: Optional[int]) -> str:
    """Choose a personality_profile slug for the upcoming RJ break."""
    if channel_slug == "morning_masala":
        return "morning_drive"
    if channel_slug == "party_dubai" and energy in ("high", "party"):
        return "nightlife"
    if channel_slug == "late_night_drive":
        return "chill_late_night"
    if channel_slug in ("talk_dubai_desi", "talk_dfw_desi"):
        return "talk_news"
    if dubai_hour is not None:
        if 5 <= dubai_hour < 10: return "morning_drive"
        if 11 <= dubai_hour < 14: return "lunch"
        if 16 <= dubai_hour < 20: return "evening_drive"
        if 20 <= dubai_hour < 24 or dubai_hour < 2: return "nightlife"
        if 2 <= dubai_hour < 5: return "chill_late_night"
    if energy in ("party", "high"): return "nightlife"
    if energy == "chill": return "chill_late_night"
    return "evening_drive"
