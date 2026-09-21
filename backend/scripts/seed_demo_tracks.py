"""Seed playable demo music tracks for AI radio in the preview.

The preview `tracks` collection had only legacy rows whose local audio files
don't exist on this pod, so the AI-radio segment builder had an empty playable
pool. These rows point `file_path` at public, royalty-free MP3s (SoundHelix,
CC) which ffmpeg fetches directly over HTTPS — no local files needed — so the
pool builds and radio actually plays. Idempotent (upsert by _id).

Run:  python -m scripts.seed_demo_tracks
"""
import asyncio
from datetime import datetime, timezone

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

_URL = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{}.mp3"

# (genre, energy_level, mood, language)
_SPEC = [
    ("pop",         "medium", "uplifting",  "english"),
    ("electronic",  "high",   "energetic",  "english"),
    ("retro",       "chill",  "groove",     "english"),
    ("indie",       "medium", "uplifting",  "english"),
    ("hip_hop",     "high",   "energetic",  "english"),
    ("pop",         "party",  "party",      "english"),
    ("electronic",  "party",  "party",      "english"),
    ("retro",       "chill",  "romantic",   "english"),
    ("indie",       "chill",  "melancholy", "english"),
    ("pop",         "medium", "groove",     "english"),
    ("bollywood",   "high",   "energetic",  "hindi"),
    ("bollywood",   "medium", "romantic",   "hindi"),
    ("ghazal",      "chill",  "melancholy", "hindi"),
    ("devotional",  "chill",  "uplifting",  "hindi"),
    ("punjabi_pop", "party",  "party",      "punjabi"),
    ("bhangra",     "high",   "energetic",  "punjabi"),
]


async def main():
    cfg = dotenv_values("/app/backend/.env")
    db = AsyncIOMotorClient(cfg["MONGO_URL"])[cfg["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for i, (genre, energy, mood, lang) in enumerate(_SPEC, start=1):
        tid = f"demo_track_{i}"
        doc = {
            "_id": tid,
            "title": f"FUUSIC Demo {i} · {genre.replace('_', ' ').title()}",
            "artist": "FUUSIC Studio",
            "album": "FUUSIC Demo Sessions",
            "file_path": _URL.format(((i - 1) % 16) + 1),
            "duration_sec": 300.0,
            "energy_level": energy,
            "mood": mood,
            "genre": genre,
            "language": lang,
            "playable_status": "ok",
            "status": "ok",
            "source": "seed_demo",
            "uploaded_at": now,
        }
        await db.tracks.update_one({"_id": tid}, {"$set": doc}, upsert=True)
        n += 1
    total = await db.tracks.count_documents({})
    playable = await db.tracks.count_documents(
        {"$or": [{"playable_status": {"$exists": False}}, {"playable_status": "ok"}]})
    print(f"seeded {n} demo tracks | tracks total={total} playable={playable}")


if __name__ == "__main__":
    asyncio.run(main())
