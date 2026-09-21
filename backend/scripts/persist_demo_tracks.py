"""Persist the demo music library to object storage (Tigris) so AI radio keeps
playing after a fresh fork/redeploy — instead of depending on ffmpeg reaching
external SoundHelix URLs every build.

Downloads each demo track's source MP3 once, uploads it to the Tigris bucket
under `demo_tracks/…`, and repoints the `tracks` row at Tigris
(storage_provider=tigris + storage_key) so `_track_file_path_for_ffmpeg`
serves a signed URL. Idempotent — skips upload if the key already exists.

Run:  python -m scripts.persist_demo_tracks
"""
import asyncio
import os
import tempfile

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from services.object_storage import get_storage

_SRC = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{}.mp3"


async def main():
    load_dotenv("/app/backend/.env")  # populate os.environ so get_storage() sees Tigris
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    storage = get_storage()
    print("storage backend:", storage.backend_name)

    tracks = await db.tracks.find({"source": "seed_demo"}).to_list(100)
    if not tracks:
        print("no seed_demo tracks found — run seed_demo_tracks first")
        return

    done = 0
    for t in tracks:
        tid = t["_id"]
        key = f"demo_tracks/{tid}.mp3"
        try:
            if not storage.exists(key=key):
                # Resolve the source URL (current file_path) and download once.
                src = t.get("file_path") or ""
                if not src.startswith("http"):
                    idx = ((int(str(tid).split("_")[-1]) - 1) % 16) + 1
                    src = _SRC.format(idx)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    r = requests.get(src, timeout=60)
                    r.raise_for_status()
                    tmp.write(r.content)
                    tmp_path = tmp.name
                storage.upload(local_path=tmp_path, key=key, content_type="audio/mpeg")
                os.unlink(tmp_path)
                print(f"uploaded {key} ({len(r.content)} bytes)")
            await db.tracks.update_one(
                {"_id": tid},
                {"$set": {"storage_provider": "tigris", "storage_key": key,
                          "playable_status": "ok", "status": "ok"}})
            done += 1
        except Exception as e:
            print(f"skip {tid}: {e}")
    print(f"persisted {done}/{len(tracks)} demo tracks to Tigris")


if __name__ == "__main__":
    asyncio.run(main())
