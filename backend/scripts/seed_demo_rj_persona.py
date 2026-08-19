"""Idempotent demo RJ persona so the AI-RJ Sponsored Read flow is bookable.
Voice render (post-payment) still needs a real ELEVENLABS_API_KEY.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

PID = "persona_demo_rj_ava"


async def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base, ".env"))
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    doc = {
        "_id": PID, "id": PID, "name": "Ava (Demo RJ)",
        "status": "active", "voice_provider": "elevenlabs",
        "voice_id": "21m00Tcm4TlvDq8ikWAM", "language": "en",
        "personality": "energetic", "persona_prompt": "upbeat, conversational",
        "demo_seed": True, "created_at": now, "updated_at": now,
    }
    await db.rj_personas.update_one({"id": PID}, {"$set": doc}, upsert=True)
    print("seeded persona:", PID)


if __name__ == "__main__":
    asyncio.run(main())
