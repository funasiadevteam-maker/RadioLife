"""Migrate local-only tracks to Tigris in batches of 50.

DRY-RUN by default — prints what WOULD be uploaded.  Pass --execute to
actually push to Tigris.  Idempotent: skips tracks already on Tigris.
Retains `local_file_path` as a fallback after upload.

Usage:
  python scripts/migrate_rescued_local_to_tigris.py               # dry-run
  python scripts/migrate_rescued_local_to_tigris.py --execute  # do it
"""
import asyncio
import os
import sys
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

CHUNK = 50


async def main(execute: bool):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    bucket = os.environ.get("TIGRIS_BUCKET", "bigfm-storage")
    prefix = os.environ.get("TRACKS_BUCKET_PREFIX") or "tracks/"
    if not prefix.endswith("/"): prefix += "/"

    # Candidates: storage_provider=local with a real on-disk file.
    candidates = []
    async for t in db.tracks.find(
            {"storage_provider": "local", "status": "active"}):
        path = t.get("local_file_path") or t.get("file_path")
        if path and Path(path).exists():
            candidates.append(t)

    print(f"candidates to migrate: {len(candidates)}")
    print(f"  bucket: {bucket}")
    print(f"  prefix: {prefix}")
    print(f"  mode:    {'EXECUTE' if execute else 'DRY-RUN'}")

    if not execute:
        print("\nFirst 5 candidates (dry-run preview):")
        for t in candidates[:5]:
            tid = t["_id"]
            ext = Path(t.get("local_file_path") or "").suffix or ".mp3"
            target_key = f"{prefix}{tid}{ext}"
            print(f"  {tid} → s3://{bucket}/{target_key}  "
                      f"({Path(t['local_file_path']).stat().st_size:,} bytes)")
        print(f"\nRun with --execute to actually upload {len(candidates)} files.")
        return

    # Execute path.
    from services.object_storage import get_storage
    store = get_storage()
    uploaded = 0
    skipped = 0
    failed = 0
    for i in range(0, len(candidates), CHUNK):
        batch = candidates[i:i+CHUNK]
        print(f"\n--- batch {i//CHUNK + 1}/{(len(candidates)+CHUNK-1)//CHUNK}")
        for t in batch:
            tid = t["_id"]
            local = t.get("local_file_path") or t.get("file_path")
            ext = Path(local).suffix or ".mp3"
            key = f"{prefix}{tid}{ext}"
            try:
                store.upload(local_path=local, key=key,
                                      content_type="audio/mpeg")
                await db.tracks.update_one(
                    {"_id": tid},
                    {"$set": {"storage_provider": "tigris",
                                        "storage_key": key,
                                        "file_path": f"s3://{bucket}/{key}",
                                        "local_file_path": local}})
                uploaded += 1
                print(f"  ✓ {tid}")
            except Exception as e:
                failed += 1
                print(f"  ✗ {tid}: {e}")
    print(f"\nDONE: uploaded={uploaded} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    asyncio.run(main(execute))
