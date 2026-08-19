"""Idempotent demo AI-RJ personas so the Sponsored Read flow + voice picker
are usable. Voice render (post-payment/preview) uses the configured
ELEVENLABS_API_KEY.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

PERSONAS = [
    {"id": "persona_demo_rj_ava", "name": "Ava", "tagline": "Bright & upbeat morning voice",
     "voice_id": "riya_dj", "personality": "energetic", "language": "en",
     "persona_prompt": "upbeat, warm, conversational morning-show host"},
    {"id": "persona_demo_rj_leo", "name": "Leo", "tagline": "Smooth late-night baritone",
     "voice_id": "marcus_dj", "personality": "smooth", "language": "en",
     "persona_prompt": "calm, smooth, late-night radio baritone"},
    {"id": "persona_demo_rj_maya", "name": "Maya", "tagline": "Playful drive-time energy",
     "voice_id": "aisha_english", "personality": "playful", "language": "en",
     "persona_prompt": "fun, playful, high-energy drive-time host"},
]


async def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base, ".env"))
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    for p in PERSONAS:
        doc = {"_id": p["id"], "id": p["id"], "name": p["name"], "tagline": p["tagline"],
               "description": p["tagline"], "status": "active", "voice_provider": "openai_tts",
               "voice_id": p["voice_id"], "language": p["language"],
               "personality": p["personality"], "persona_prompt": p["persona_prompt"],
               "demo_seed": True, "updated_at": now}
        await db.rj_personas.update_one(
            {"id": p["id"]}, {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True)
        print("seeded persona:", p["id"], p["name"])


if __name__ == "__main__":
    asyncio.run(main())
