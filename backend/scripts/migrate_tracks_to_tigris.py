"""Phase 22c — One-shot Tigris migration for `tracks` rows.

Walks every row where `storage_provider != "tigris"` (or missing), reads
the local file, uploads to Tigris under `tracks/<uuid>.<ext>`, writes
back the storage_provider/storage_key/file_path fields. Idempotent —
a second run on already-migrated rows is a no-op.

Returns `{migrated, skipped_already_migrated, missing_local_file, failed}`.
Used by both the CLI entrypoint and `POST /api/admin/tracks/migrate-storage-to-tigris`.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional


async def migrate_tracks_to_tigris(db, *, limit: Optional[int] = None) -> dict:
    from services.object_storage import get_storage
    storage = get_storage()
    bucket = os.environ.get("TIGRIS_BUCKET") or ""
    prefix = os.environ.get("TRACKS_BUCKET_PREFIX") or "tracks/"
    if not prefix.endswith("/"): prefix += "/"

    migrated = 0
    skipped_already_migrated = 0
    missing_local_file = 0
    failed: list[dict] = []

    q = {"$or": [{"storage_provider": {"$exists": False}},
                          {"storage_provider": {"$ne": "tigris"}}]}
    cur = db.tracks.find(q, {"_id": 1, "file_path": 1,
                                                "storage_provider": 1, "storage_key": 1})
    if limit: cur = cur.limit(limit)

    async for t in cur:
        if (t.get("storage_provider") == "tigris"
                and t.get("storage_key")):
            skipped_already_migrated += 1
            continue
        local_fp = t.get("file_path") or ""
        if not local_fp or local_fp.startswith("s3://"):
            # already pointed at Tigris but missing provider flag — fix flag.
            if local_fp.startswith("s3://"):
                # Backfill provider flag from canonical s3 path.
                key = local_fp.split("/", 3)[-1] if "/" in local_fp else None
                if key:
                    await db.tracks.update_one(
                        {"_id": t["_id"]},
                        {"$set": {"storage_provider": "tigris",
                                          "storage_key":          key}})
                    migrated += 1
                    continue
            missing_local_file += 1
            continue
        p = Path(local_fp)
        if not p.exists():
            missing_local_file += 1
            continue
        tid = t["_id"]
        ext = p.suffix.lower() or ".mp3"
        key = f"{prefix}{tid}{ext}"
        try:
            storage.upload(local_path=str(p), key=key,
                                          content_type="audio/mpeg")
        except Exception as e:
            failed.append({"track_id": tid, "reason": str(e)[:160]})
            continue
        canonical = f"s3://{bucket}/{key}"
        await db.tracks.update_one(
            {"_id": tid},
            {"$set": {"storage_provider":  "tigris",
                              "storage_key":          key,
                              "file_path":              canonical,
                              "local_file_path":  str(p)}})
        migrated += 1

    return {"migrated":                                migrated,
                  "skipped_already_migrated": skipped_already_migrated,
                  "missing_local_file":          missing_local_file,
                  "failed":                                  failed}


if __name__ == "__main__":
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    db_ = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    print(asyncio.get_event_loop().run_until_complete(migrate_tracks_to_tigris(db_)))
