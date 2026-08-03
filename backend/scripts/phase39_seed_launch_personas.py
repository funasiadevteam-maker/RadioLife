"""Phase 39 Session 1 — seed the 10 launch personas idempotently.

Each persona MUST pass `PersonaSafetyClassifier.classify(...).is_safe`
or the seed aborts for that row (and reports which).

Voices are mapped to existing `VOICE_REGISTRY` entries (the ElevenLabs
voice_ids already provisioned in earlier phases).  This avoids spending
voice slots on new clones for the POC — Session 2 may upgrade specific
personas with cloned voices once persona-selection UX is validated.

Run:
    python -m scripts.phase39_seed_launch_personas
or programmatically via `seed_launch_personas(db)`.
"""
from __future__ import annotations
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Path setup for direct script invocation.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.persona_safety import PersonaSafetyClassifier  # noqa: E402
from services.voice_config import VOICE_REGISTRY                              # noqa: E402

log = logging.getLogger("bigfm.phase39_seed")
COLLECTION = "rj_personality_profiles"


# Voice mapping uses existing ElevenLabs voice_keys from VOICE_REGISTRY.
# Each launch persona gets a distinct voice; no two share a voice_key.
LAUNCH_PERSONAS: list[dict] = [
    {
        "persona_id":  "p39_dawn_caller",
        "display_name":  "Dawn Caller",
        "archetype":      "calm_morning_hinglish",
        "description":  "A calm Hinglish morning host who gently nudges you out of sleep. Warm, unhurried, never preachy.",
        "signature_phrases": ["soft start, big day", "chai chal raha hai?",
                                                      "let's ease in"],
        "language_mix":  ["hinglish", "english"],
        "daypart_affinity": ["morning_drive"],
        "voice_key":      "aarti_morning",
    },
    {
        "persona_id":  "p39_drive_time_energizer",
        "display_name":  "Drive Time Energizer",
        "archetype":      "high_energy_us_morning",
        "description":  "High-octane US-style morning commute voice. Quick wit, sports references, weather snaps.",
        "signature_phrases": ["wheels up", "let's roll", "morning crew, you ready?"],
        "language_mix":  ["english"],
        "daypart_affinity": ["morning_drive"],
        "voice_key":      "monika_dubai",
    },
    {
        "persona_id":  "p39_lunch_cousin",
        "display_name":  "Lunch Cousin",
        "archetype":      "friendly_hinglish_lunch",
        "description":  "Friendly Hinglish lunchtime host — the cousin who shares meme links and asks about your day.",
        "signature_phrases": ["lunch ho gaya?", "thoda hass lete hain",
                                                      "good vibes only"],
        "language_mix":  ["hinglish", "hindi"],
        "daypart_affinity": ["lunch"],
        "voice_key":      "veer_dubai",
    },
    {
        "persona_id":  "p39_afternoon_storyteller",
        "display_name":  "Afternoon Storyteller",
        "archetype":      "slow_narrative_anchor",
        "description":  "A slow narrative anchor blending English and Arabic for the deep afternoon hours.",
        "signature_phrases": ["here's a small story",
                                                      "ek baat batayein",
                                                      "settle in"],
        "language_mix":  ["english", "arabic"],
        "daypart_affinity": ["afternoon"],
        "voice_key":      "kabir_hindi",
    },
    {
        "persona_id":  "p39_sunset_reflector",
        "display_name":  "Sunset Reflector",
        "archetype":      "mellow_evening_transition",
        "description":  "Mellow Hinglish evening voice for the sunset transition. Reflective, kind, never gloomy.",
        "signature_phrases": ["day done, slow down",
                                                      "thoda saans le lo",
                                                      "good evening, friend"],
        "language_mix":  ["hinglish", "english"],
        "daypart_affinity": ["evening_drive"],
        "voice_key":      "ishita_hindi",
    },
    {
        "persona_id":  "p39_friday_night_hype",
        "display_name":  "Friday Night Hype",
        "archetype":      "high_energy_party_host",
        "description":  "High-energy English party/club host for Friday night going-out hours.",
        "signature_phrases": ["the weekend starts now", "city's on tonight",
                                                      "turn it up"],
        "language_mix":  ["english"],
        "daypart_affinity": ["nightlife"],
        "voice_key":      "raghav_hindi",
    },
    {
        "persona_id":  "p39_late_night_confidant",
        "display_name":  "Late Night Confidant",
        "archetype":      "intimate_late_night",
        "description":  "Soft English/Hindi intimate voice for the late hours when listeners want company, not noise.",
        "signature_phrases": ["still up?", "raat ki chuppi", "you're not alone"],
        "language_mix":  ["english", "hindi"],
        "daypart_affinity": ["late_night"],
        "voice_key":      "aanya_hindi",
    },
    {
        "persona_id":  "p39_devotional_murmur",
        "display_name":  "Devotional Murmur",
        "archetype":      "calm_devotional_anchor",
        "description":  "Calm devotional anchor — slow warm baritone, sliding between Hindi, Tamil, and Punjabi devotional touches.",
        "signature_phrases": ["om shanti", "sab thik hoga",
                                                      "rab kare changa"],
        "language_mix":  ["hindi", "tamil", "punjabi"],
        "daypart_affinity": ["early_morning", "evening"],
        "voice_key":      "pandit_anand",
    },
    {
        "persona_id":  "p39_bilingual_news_anchor",
        "display_name":  "Bilingual News Anchor",
        "archetype":      "neutral_news_cadence",
        "description":  "Neutral Hinglish news cadence. Credible, brisk, no opinion injection.",
        "signature_phrases": ["here is what you need to know",
                                                      "the headline this hour"],
        "language_mix":  ["hinglish", "english"],
        "daypart_affinity": ["all_day"],
        "voice_key":      "kishore_retro",
    },
    {
        "persona_id":  "p39_weekend_vibe_curator",
        "display_name":  "Weekend Vibe Curator",
        "archetype":      "laid_back_weekend",
        "description":  "Laid-back English/Hindi weekend host curating mood-based blocks. Lots of breathing room.",
        "signature_phrases": ["weekend mood, locked in",
                                                      "no rush today",
                                                      "let it flow"],
        "language_mix":  ["english", "hindi"],
        "daypart_affinity": ["weekend"],
        "voice_key":      "gurpreet_bhaji",
    },
]


def _persona_to_doc(p: dict, classification: dict) -> dict:
    voice_meta = VOICE_REGISTRY.get(p["voice_key"]) or {}
    voice_id = voice_meta.get("voice_id") or voice_meta.get("id") or None
    now = datetime.now(timezone.utc).isoformat()
    return {
        "_id":                          p["persona_id"],
        "persona_id":            p["persona_id"],
        "slug":                          p["persona_id"],  # 22e index compat
        "display_name":      p["display_name"],
        "name":                        p["display_name"],  # legacy column
        "archetype":              p["archetype"],
        "description":          p["description"],
        "signature_phrases": p["signature_phrases"],
        "language_mix":      p["language_mix"],
        "daypart_affinity": p["daypart_affinity"],
        "voice_key":              p["voice_key"],
        "voice_id":                p["voice_key"] and voice_id,
        "voice_clone_reference_url": None,
        "is_launch_persona": True,
        "is_premium":              False,
        "active":                    True,
        "safety_classification": {
            **classification,
            "classified_at": now,
            "classifier_version": "p39s1.1",
        },
        "created_at":            now,
        "updated_at":            now,
        "created_by":            "phase39_seed",
    }


async def seed_launch_personas(db) -> dict:
    """Idempotent. Returns {classified, seeded, blocked, blocked_details}."""
    classifier = PersonaSafetyClassifier()
    seeded = 0
    blocked: list[dict] = []
    classified = 0
    for p in LAUNCH_PERSONAS:
        result = classifier.classify(p)
        classified += 1
        if not result["is_safe"]:
            blocked.append({"persona_id":  p["persona_id"],
                                          "display_name":  p["display_name"],
                                          "flags":              result["flags"],
                                          "evidence":          result["evidence"]})
            log.error("[phase39_seed] BLOCKED %s — flags=%s evidence=%s",
                              p["persona_id"], result["flags"], result["evidence"])
            continue
        doc = _persona_to_doc(p, result)
        await db[COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": doc,
              "$setOnInsert": {"inserted_at": doc["created_at"]}},
            upsert=True,
        )
        seeded += 1
    return {"classified":            classified,
                  "seeded":                  seeded,
                  "blocked":                len(blocked),
                  "blocked_details": blocked}


async def _main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    result = await seed_launch_personas(db)
    print("[phase39_seed]", result)


if __name__ == "__main__":
    asyncio.run(_main())
