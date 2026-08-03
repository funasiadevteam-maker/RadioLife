"""Task A — Purge silent pytest-fixture stub tracks from the catalog.

Identification (must satisfy ALL):
  1. status = 'active'
  2. On-disk file size between 1500 and 5000 bytes (1690/2108 byte stubs)
  3. AND any of:
       - rescued_from_orphan_disk == True (the marker from the rescue
         script — covers the 485 rescued from /storage/tracks/)
       - title matches ^(zip_x_|p22[a-z]_ok_|loose_)|^Track [0-9a-f]+
       - file_path doesn't exist on disk (defensive cleanup of stragglers)

Sanity guards:
  - abort if matches > 600 (real uploads are happening)
  - abort if matches < 100 (something else changed)
  - dry-run unless --execute is passed

Cascade cleanup on actual delete:
  queue_items, playback_logs, channel_track_assignments,
  recommender_decision_log delete refs; radio_sessions.last_track_id
  nulled; game_campaigns.eligible_track_ids and playlists.tracks
  scrubbed via $pullAll.
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

STUB_TITLE_RGX = re.compile(
    r"^(zip_x_|p22[a-z]_ok_|loose_)|^Track [0-9a-f]+$", re.IGNORECASE)


async def main(execute: bool):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    candidates = []
    async for t in db.tracks.find({"status": "active"}):
        path = t.get("local_file_path") or t.get("file_path") or ""
        sz = 0
        try:
            if path and not path.startswith("s3://"):
                sz = Path(path).stat().st_size
        except Exception:
            sz = 0
        is_size_stub = (1500 <= sz <= 5000)
        is_title_stub = STUB_TITLE_RGX.search(t.get("title") or "") is not None
        is_marked_rescued = bool(t.get("rescued_from_orphan_disk"))
        is_missing = (not path) or (
            not path.startswith("s3://") and not Path(path).exists())
        if is_size_stub and (is_marked_rescued or is_title_stub or is_missing):
            candidates.append((t["_id"], t.get("title"), sz, path))

    print(f"=== pre-flight ===")
    print(f"  matches: {len(candidates)}")
    for tid, ttl, sz, p in candidates[:10]:
        print(f"    {tid}  size={sz:>5}  title={ttl!r:30}  path={p}")

    if len(candidates) > 600:
        print("ABORT: too many matches (>600). Real uploads may have landed.")
        return
    if len(candidates) < 100:
        print("ABORT: too few matches (<100). Investigate before deleting.")
        return

    if not execute:
        print("\nDRY-RUN — pass --execute to delete.")
        return

    # Log every ID for traceability.
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = f"/app/memory/stub_purge_{ts}.log"
    with open(log_path, "w") as fh:
        fh.write(f"Stub purge {ts}Z — {len(candidates)} rows\n")
        for tid, ttl, sz, p in candidates:
            fh.write(f"{tid}\t{sz}\t{ttl!r}\t{p}\n")
    print(f"\nlog: {log_path}")

    ids = [c[0] for c in candidates]

    # Cascade BEFORE deleting the tracks themselves.
    r1 = await db.queue_items.delete_many({"track_id": {"$in": ids}})
    r2 = await db.playback_logs.delete_many({"track_id": {"$in": ids}})
    r3 = await db.channel_track_assignments.delete_many(
        {"track_id": {"$in": ids}})
    r4 = await db.recommender_decision_log.delete_many(
        {"track_id": {"$in": ids}})
    r5 = await db.radio_sessions.update_many(
        {"last_track_id": {"$in": ids}}, {"$set": {"last_track_id": None}})
    r6 = await db.game_campaigns.update_many(
        {"eligible_track_ids": {"$in": ids}},
        {"$pullAll": {"eligible_track_ids": ids}})
    r7 = await db.playlists.update_many(
        {"tracks": {"$in": ids}}, {"$pullAll": {"tracks": ids}})

    # Now hard-delete the tracks.
    r0 = await db.tracks.delete_many({"_id": {"$in": ids}})

    print(f"\n=== cascade cleanup ===")
    print(f"  tracks                                  deleted={r0.deleted_count}")
    print(f"  queue_items                          deleted={r1.deleted_count}")
    print(f"  playback_logs                      deleted={r2.deleted_count}")
    print(f"  channel_track_assignments deleted={r3.deleted_count}")
    print(f"  recommender_decision_log deleted={r4.deleted_count}")
    print(f"  radio_sessions nulled            updated={r5.modified_count}")
    print(f"  game_campaigns scrubbed     updated={r6.modified_count}")
    print(f"  playlists scrubbed                  updated={r7.modified_count}")

    # Optional: also remove the now-orphan files from disk.
    removed = 0
    for tid, _, _, p in candidates:
        try:
            if p and not p.startswith("s3://") and Path(p).exists():
                Path(p).unlink()
                removed += 1
        except Exception:
            pass
    print(f"  disk files removed:                            {removed}")

    # Final state.
    total = await db.tracks.count_documents({})
    active = await db.tracks.count_documents({"status": "active"})
    print(f"\nFINAL: tracks_total={total} tracks_active={active}")


if __name__ == "__main__":
    asyncio.run(main(execute="--execute" in sys.argv))
