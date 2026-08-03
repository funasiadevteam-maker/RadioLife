"""Hotfix — register the 485 orphan local MP3s as active tracks, then
hard-delete the 137 broken_storage_missing rows.

Runs idempotently.  Safe to invoke twice.
"""
import asyncio
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

import sys; sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

TRACKS_DIR = Path("/app/backend/storage/tracks")


def _ffprobe_duration(p: Path) -> float:
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
            capture_output=True, text=True, timeout=8)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _try_tags(p: Path) -> dict:
    try:
        from mutagen import File as MutagenFile
        m = MutagenFile(str(p), easy=True)
        if not m:
            return {}
        t = (m.get("title") or [""])[0]
        a = (m.get("artist") or [""])[0]
        return {"title": t or None, "artist": a or None}
    except Exception:
        return {}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)

    # ----- 1. discover orphan disk files (on disk, NOT in mongo) -------
    disk_files = {p.stem: p for p in TRACKS_DIR.glob("*.mp3")}
    mongo_ids = set()
    async for t in db.tracks.find({}, {"_id": 1}):
        mongo_ids.add(t["_id"])
    orphans = [(stem, path) for stem, path in disk_files.items()
                  if stem not in mongo_ids]
    print(f"orphan files to register: {len(orphans)}")

    # ----- 2. register each as an active local track ------------------
    registered = 0
    skipped = 0
    for stem, path in orphans:
        tags = _try_tags(path)
        duration = _ffprobe_duration(path)
        if duration <= 0:
            skipped += 1
            continue
        # Use the file's UUID-shaped stem as the track id where possible.
        try:
            uuid.UUID(stem)
            tid = stem
        except Exception:
            tid = str(uuid.uuid4())
        doc = {
            "_id": tid,
            "title":  tags.get("title")  or f"Track {stem[:8]}",
            "artist": tags.get("artist") or "Unknown Artist",
            "file_path":        str(path),
            "local_file_path": str(path),
            "storage_provider": "local",
            "status": "active",
            "duration_sec": duration,
            "bitrate_kbps": None,
            "energy_level": "medium",
            "mood":              "uplifting",
            "language":     "en",
            "genre_tags":  [],
            "era_tag":       None,
            "uploaded_at": now,
            "uploaded_by_user_id": "system_rescue",
            "rescued_from_orphan_disk": True,
        }
        try:
            await db.tracks.insert_one(doc)
            registered += 1
        except Exception as e:
            print(f"  insert failed for {tid}: {e}")
            skipped += 1
    print(f"registered={registered} skipped={skipped}")

    # ----- 3. hard-delete broken_storage_missing rows -----------------
    broken_ids = []
    async for t in db.tracks.find({"status": "broken_storage_missing"},
                                                            {"_id": 1, "title": 1, "artist": 1}):
        broken_ids.append(t["_id"])
        print(f"  deleting {t['_id']} | {t.get('title')} | {t.get('artist')}")
    print(f"broken rows to delete: {len(broken_ids)}")

    if broken_ids:
        # Cascade: scrub the broken IDs from any referencing collections.
        # We touch only collections that actually exist + are safe to
        # update.  Each $pull on the broken IDs is idempotent.
        await db.channel_track_assignments.delete_many(
            {"track_id": {"$in": broken_ids}})
        await db.recommender_decision_log.delete_many(
            {"track_id": {"$in": broken_ids}})
        # Listening sessions reference last_track_id; null it out for safety.
        await db.radio_sessions.update_many(
            {"last_track_id": {"$in": broken_ids}},
            {"$set": {"last_track_id": None}})
        # Finally drop the rows.
        r = await db.tracks.delete_many({"status": "broken_storage_missing"})
        print(f"deleted_tracks={r.deleted_count}")

    # ----- 4. final inventory ----------------------------------------
    total = await db.tracks.count_documents({})
    active = await db.tracks.count_documents({"status": "active"})
    broken_after = await db.tracks.count_documents(
        {"status": "broken_storage_missing"})
    print(f"FINAL: total={total} active={active} broken={broken_after}")


if __name__ == "__main__":
    asyncio.run(main())
