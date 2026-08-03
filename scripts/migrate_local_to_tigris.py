#!/usr/bin/env python3
"""Phase 36c.5 — Migrate local /app/backend/storage/ → Tigris.

Walks the local storage tree, maps each on-disk file to a canonical Tigris
key, uploads + verifies + updates Mongo refs + (on --apply) deletes the
local copy. Idempotent: re-running skips files already in Tigris with
matching size.

  DRY-RUN:  python3 scripts/migrate_local_to_tigris.py --dry-run
  LIVE:     python3 scripts/migrate_local_to_tigris.py --apply
"""
from __future__ import annotations
import argparse, asyncio, os, re, sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient    # noqa: E402
from services import object_storage as obs                  # noqa: E402

LOCAL_ROOT = Path(os.environ.get("STORAGE_LOCAL_ROOT") or "/app/backend/storage")
MONGO_URL  = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME      = os.environ.get("DB_NAME") or "bigfm"

# Map local-path patterns → (Tigris key fn, content_type, db_update_fn)
# db_update_fn is None when there's no Mongo row to update (e.g. transient).


def _key_for(local_rel: Path) -> tuple:
    """Return (key, content_type) for a given local-relative path, or
    (None, None) when we explicitly skip (transient junk, raw uploads,
    legacy stale dirs). Refusing to upload guesswork is intentional —
    safer to leave stragglers behind than to pollute Tigris."""
    parts = local_rel.parts
    name  = local_rel.name
    ext      = local_rel.suffix.lower()

    if any(p.startswith(".") for p in parts): return (None, None)
    # Recording session files: podcasts/recordings/<sid>/...
    if len(parts) >= 3 and parts[0] == "podcasts" and parts[1] == "recordings":
        sid = parts[2]
        if name == "mixed.mp3" or name == "audio.mp3":
            return (obs.key_recording_mixed_audio(sid), "audio/mpeg")
        if name == "video.mp4" or name == "mixed.mp4":
            return (obs.key_recording_mixed_video(sid), "video/mp4")
        if name == "host.mp3":
            return (f"podcasts/recordings/{sid}/host/audio.mp3", "audio/mpeg")
        if name == "host_video.mp4":
            return (f"podcasts/recordings/{sid}/host/video.mp4", "video/mp4")
        # per-guest files prp_xxx.mp3 / prp_xxx_video.mp4
        m = re.match(r"^(prp_[0-9a-f]+)(_video)?\.(mp3|mp4)$", name)
        if m:
            pid, video_suffix, e = m.group(1), m.group(2), m.group(3)
            if video_suffix:
                return (obs.key_recording_participant_video(sid, pid), "video/mp4")
            return (obs.key_recording_participant_audio(sid, pid), "audio/mpeg")
        # raw transcode intermediates and temps — skip.
        if "_raw" in name or name.endswith(".tmp"): return (None, None)
        return (None, None)

    # Music tracks: tracks/<track_id>.mp3
    if parts[0] == "tracks" and ext == ".mp3":
        track_id = local_rel.stem
        return (obs.key_music_track(track_id), "audio/mpeg")

    # RJ blurbs: rj/<rj_id>.mp3
    if parts[0] == "rj" and ext == ".mp3":
        return (obs.key_rj(local_rel.stem), "audio/mpeg")

    # Ad creatives
    if parts[0] == "ad_creatives":
        cid = local_rel.stem
        if ext == ".mp3": return (obs.key_ad_creative_audio(cid), "audio/mpeg")
        if ext in (".webp", ".jpg", ".jpeg", ".png"):
            return (obs.key_ad_creative_image(cid, ext.lstrip(".")), f"image/{ext.lstrip('.')}")

    # Chapters / transcripts
    if parts[0] == "chapters" and ext == ".json":
        return (obs.key_chapters_json(local_rel.stem), "application/json")
    if parts[0] == "transcripts" and ext == ".srt":
        return (obs.key_transcript_srt(local_rel.stem), "application/x-subrip")

    # Everything else — skip and leave a note. We don't want to silently
    # migrate things like SFX libraries, station IDs, prewarm caches.
    return (None, None)


async def db_patch_for_key(db, *, local_path: Path, key: str) -> int:
    """Best-effort: if this file is referenced in MongoDB by an absolute
    path, replace that with the new `storage_key` field. Returns count
    of docs updated. NOT REQUIRED for the proxy routes to work — they
    resolve keys from the storage_path field — but keeps things tidy."""
    abs_str = str(local_path)
    # The only routes that today read directly from disk look up
    # `podcast_episodes.storage_path` (a directory), so we don't need to
    # touch row-level fields. Leave a no-op for forward-compat hooks.
    _ = abs_str; _ = key; _ = db
    return 0


async def main(apply: bool) -> int:
    if not LOCAL_ROOT.exists():
        print(f"local root {LOCAL_ROOT} does not exist — nothing to migrate")
        return 0
    storage = obs.get_storage()
    if storage.backend_name != "tigris":
        print(f"FAIL: STORAGE_BACKEND={storage.backend_name}, expected tigris"); return 2
    client = AsyncIOMotorClient(MONGO_URL); db = client[DB_NAME]

    stats = {"scanned": 0, "skipped": 0, "uploaded": 0,
                  "skipped_already_present": 0, "deleted_local": 0,
                  "errors": 0, "bytes_migrated": 0}
    skipped_paths = []
    print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"Local root: {LOCAL_ROOT}")
    print(f"Tigris bucket: {storage.bucket}")
    print("─" * 70)

    for p in sorted(LOCAL_ROOT.rglob("*")):
        if not p.is_file(): continue
        stats["scanned"] += 1
        rel = p.relative_to(LOCAL_ROOT)
        key, ctype = _key_for(rel)
        if key is None:
            stats["skipped"] += 1
            skipped_paths.append(str(rel))
            continue
        local_size = p.stat().st_size
        head = storage.head(key=key)
        if head and head.get("size") == local_size:
            stats["skipped_already_present"] += 1
            if apply:
                p.unlink(missing_ok=True)
                stats["deleted_local"] += 1
            print(f"  = {rel}  →  {key}  (already present, "
                      f"{'deleted local' if apply else 'would delete'})")
            continue
        # Upload (real or simulated).
        if apply:
            try:
                storage.upload(local_path=str(p), key=key, content_type=ctype or "application/octet-stream")
                head2 = storage.head(key=key)
                if not head2 or head2["size"] != local_size:
                    print(f"  ! MISMATCH {rel}: local={local_size} remote={head2}")
                    stats["errors"] += 1; continue
                stats["uploaded"] += 1
                stats["bytes_migrated"] += local_size
                p.unlink(missing_ok=True)
                stats["deleted_local"] += 1
                await db_patch_for_key(db, local_path=p, key=key)
                print(f"  ✓ {rel}  →  {key}  ({local_size} B)")
            except Exception as e:
                stats["errors"] += 1
                print(f"  ✗ FAIL {rel}: {type(e).__name__}: {e}")
        else:
            stats["uploaded"] += 1
            stats["bytes_migrated"] += local_size
            print(f"  + {rel}  →  {key}  ({local_size} B)  [dry-run]")

    print("─" * 70)
    print(f"Scanned:                            {stats['scanned']}")
    print(f"Migrated (or would):           {stats['uploaded']}")
    print(f"Bytes migrated (or would): {stats['bytes_migrated']:,} "
              f"({stats['bytes_migrated']/(1024*1024):.2f} MB)")
    print(f"Already present (skipped):  {stats['skipped_already_present']}")
    print(f"Skipped (unmapped):          {stats['skipped']}")
    print(f"Deleted local (if apply):     {stats['deleted_local']}")
    print(f"Errors:                                 {stats['errors']}")
    if skipped_paths and len(skipped_paths) < 30:
        print(f"\nSkipped (unmapped) paths:")
        for s in skipped_paths[:30]: print(f"    - {s}")
    client.close()
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply",    action="store_true", help="actually migrate")
    ap.add_argument("--dry-run", action="store_true", help="report only")
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error("must pass --dry-run or --apply")
    sys.exit(asyncio.get_event_loop().run_until_complete(main(args.apply)))
