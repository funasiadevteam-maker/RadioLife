"""Demo music library — shared seed + object-storage persistence.

Single source of truth for the 16 royalty-free demo tracks that power AI radio
in preview. Used by the seed scripts and the admin "Rebuild track library"
button so the library can be restored in one tap if it ever goes missing.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import requests

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

STATUS_DOC_ID = "status"


def track_specs() -> list[dict]:
    out = []
    for i, (genre, energy, mood, lang) in enumerate(_SPEC, start=1):
        tid = f"demo_track_{i}"
        out.append({
            "id": tid,
            "title": f"FUUSIC Demo {i} · {genre.replace('_', ' ').title()}",
            "genre": genre, "energy_level": energy, "mood": mood, "language": lang,
            "src_url": _URL.format(((i - 1) % 16) + 1),
            "key": f"demo_tracks/{tid}.mp3",
        })
    return out


def _fetch_and_store(storage, src_url: str, key: str) -> None:
    r = requests.get(src_url, timeout=90)
    r.raise_for_status()
    storage.upload_bytes(key=key, data=r.content, content_type="audio/mpeg")


async def rebuild_demo_track_library(db, storage, force: bool = False) -> dict:
    """Ensure the 16 demo track rows exist AND their audio lives in object
    storage. Uploads only what's missing (unless force). Updates a status doc
    the admin UI polls. Blocking download/upload runs off the event loop."""
    specs = track_specs()
    now = datetime.now(timezone.utc).isoformat()
    await db.admin_track_rebuild.update_one(
        {"_id": STATUS_DOC_ID},
        {"$set": {"running": True, "total": len(specs), "done": 0, "uploaded": 0,
                  "skipped": 0, "error": None, "started_at": now, "finished_at": None}},
        upsert=True)
    uploaded = skipped = 0
    try:
        for n, sp in enumerate(specs, start=1):
            await db.tracks.update_one({"_id": sp["id"]}, {"$set": {
                "_id": sp["id"], "title": sp["title"], "artist": "FUUSIC Studio",
                "album": "FUUSIC Demo Sessions", "duration_sec": 300.0,
                "energy_level": sp["energy_level"], "mood": sp["mood"],
                "genre": sp["genre"], "language": sp["language"],
                "playable_status": "ok", "status": "ok", "source": "seed_demo",
                "uploaded_at": now,
            }}, upsert=True)
            try:
                present = bool(storage.exists(key=sp["key"]))
            except Exception:
                present = False
            if force or not present:
                await asyncio.to_thread(_fetch_and_store, storage, sp["src_url"], sp["key"])
                uploaded += 1
            else:
                skipped += 1
            await db.tracks.update_one({"_id": sp["id"]}, {"$set": {
                "storage_provider": "tigris", "storage_key": sp["key"],
                "file_path": f"s3://{sp['key']}", "playable_status": "ok"}})
            await db.admin_track_rebuild.update_one(
                {"_id": STATUS_DOC_ID},
                {"$set": {"done": n, "uploaded": uploaded, "skipped": skipped}})
        playable = await db.tracks.count_documents(
            {"$or": [{"playable_status": {"$exists": False}}, {"playable_status": "ok"}]})
        await db.admin_track_rebuild.update_one(
            {"_id": STATUS_DOC_ID},
            {"$set": {"running": False, "playable_total": playable,
                      "finished_at": datetime.now(timezone.utc).isoformat()}})
        return {"uploaded": uploaded, "skipped": skipped, "playable_total": playable}
    except Exception as e:
        await db.admin_track_rebuild.update_one(
            {"_id": STATUS_DOC_ID},
            {"$set": {"running": False, "error": str(e)[:300],
                      "finished_at": datetime.now(timezone.utc).isoformat()}})
        raise
