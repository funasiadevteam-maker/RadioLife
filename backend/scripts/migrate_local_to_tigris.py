"""Phase Π+2 — One-shot Tigris migration for every local static asset.

Walks every directory under /app/backend/static/ and /app/backend/storage/
that the platform serves over /api/static/* (or uses internally for
audio playback) and uploads each file to Tigris under the same relative
key.  Idempotent — uses MD5 ETag comparison to skip already-mirrored
objects.

Also folds in the legacy `migrate_tracks_to_tigris` so a single CLI run
covers BOTH static images AND track mp3s.

Usage:
    python3 -m scripts.migrate_local_to_tigris [--dry-run] [--verbose] [--only-dir <name>]

Outputs a `migration_state` snapshot to MongoDB at the end so the
admin/health endpoint can surface "X% of local assets mirrored".
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bigfm.migrate_local_to_tigris")


# ──────────────────────────── directory catalog ────────────────────────────
# (local_root, tigris_prefix, description).  Order = upload order.
DIR_CATALOG = [
    # /app/backend/static/* — image assets served via /api/static/*
    ("/app/backend/static/channel_thumbnails",          "static/channel_thumbnails",          "Channel thumbnails (Phase 16-prep)"),
    ("/app/backend/static/station_artwork",                "static/station_artwork",                "FUUSIC AI station artwork (Phase C)"),
    ("/app/backend/static/landing_images",                "static/landing_images",                "Marketing landing hero images (K.7)"),
    ("/app/backend/static/city_stamps",                      "static/city_stamps",                      "Passport city stamps (K.2)"),
    ("/app/backend/static/game_thumbnails",                "static/game_thumbnails",                "Game tile thumbnails (K.7c)"),
    ("/app/backend/static/station_logos_scraped",  "static/station_logos_scraped",  "Imported-station logos scraped (K.10)"),
    ("/app/backend/static/shoppable_cards",                "static/shoppable_cards",                "Shoppable cards (Phase 36d)"),
    ("/app/backend/static/ad_creatives",                      "static/ad_creatives",                      "Ad creatives (Phase 18a)"),
    ("/app/backend/static/ads",                                          "static/ads",                                          "Static ad assets"),
    # /app/backend/storage/* — audio + media served via /api/static/* or playback APIs
    ("/app/backend/storage/persona_samples",            "storage/persona_samples",            "Persona TTS voice samples (Phase 42-F.5)"),
    ("/app/backend/storage/news_clips",                      "storage/news_clips",                      "News Radio TTS clips (Phase H'.2)"),
    ("/app/backend/storage/rj_segments",                  "storage/rj_segments",                  "AI-RJ inter-song audio (Phase H'.3)"),
    ("/app/backend/storage/sfx",                                  "storage/sfx",                                  "Game + UI SFX"),
    ("/app/backend/storage/voice_previews",                "storage/voice_previews",                "Voice preview clips"),
    ("/app/backend/storage/podcasts",                          "storage/podcasts",                          "Podcast episodes & covers"),
    ("/app/backend/storage/og_cards",                          "storage/og_cards",                          "OG share cards (Phase 42-E2)"),
    ("/app/backend/storage/feature_tile_images",  "storage/feature_tile_images",  "Feature-tile generated imagery"),
    ("/app/backend/storage/station_logos_scraped", "storage/station_logos_scraped", "Imported-station logos (K.10, alt path)"),
    ("/app/backend/storage/game_assets",                  "storage/game_assets",                  "Game-instance assets"),
    ("/app/backend/storage/rj_segments",                  "storage/rj_segments_v2",            "RJ segments v2 (alt path)"),
    ("/app/backend/storage/ads",                                  "storage/ads",                                  "In-stream ad audio"),
    # Tracks are handled by the legacy `migrate_tracks_to_tigris` because
    # they also need a DB rewrite to `s3://…` + `storage_provider=tigris`.
    # We trigger it below as Step 2.
]


# ────────────────────────────── helpers ──────────────────────────────
def _file_md5(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def _guess_content_type(path: Path) -> str:
    ct, _ = mimetypes.guess_type(str(path))
    return ct or "application/octet-stream"


async def _migrate_dir(storage, local_root: Path, tigris_prefix: str,
                                              *, dry_run: bool, verbose: bool
                                              ) -> dict:
    """Walks `local_root` and uploads every file to Tigris under
    `tigris_prefix/<rel>`.  Skips files whose Tigris ETag matches the
    local MD5 (idempotent).  Returns a counts dict."""
    out = {"uploaded": 0, "skipped": 0, "failed": 0,
                  "bytes_uploaded": 0, "errors": []}
    if not local_root.exists() or not local_root.is_dir():
        return out
    for fp in sorted(local_root.rglob("*")):
        if not fp.is_file():
            continue
        # Skip dotfiles and zero-byte files (typically `.gitkeep`).
        if fp.name.startswith(".") or fp.stat().st_size == 0:
            continue
        rel = fp.relative_to(local_root).as_posix()
        key = f"{tigris_prefix}/{rel}"
        size = fp.stat().st_size
        # Skip if remote ETag matches local MD5.
        try:
            head = storage.head(key=key)
        except Exception:
            head = None
        if head:
            remote_etag = (head.get("etag") or "").lower()
            try:
                local_md5 = _file_md5(fp)
            except Exception:
                local_md5 = ""
            if remote_etag and remote_etag == local_md5:
                if verbose:
                    log.info("  SKIP  %-50s (%.1f KB, ETag match)",
                                  rel[:50], size / 1024)
                out["skipped"] += 1
                continue
        # Upload.
        if dry_run:
            if verbose:
                log.info("  PLAN  %-50s (%.1f KB) → %s",
                              rel[:50], size / 1024, key)
            out["uploaded"] += 1
            out["bytes_uploaded"] += size
            continue
        try:
            ct = _guess_content_type(fp)
            t0 = time.monotonic()
            storage.upload(local_path=str(fp), key=key, content_type=ct)
            dt = (time.monotonic() - t0) * 1000.0
            if verbose:
                log.info("  UPL    %-50s (%.1f KB, %.0fms) → %s",
                              rel[:50], size / 1024, dt, key)
            out["uploaded"] += 1
            out["bytes_uploaded"] += size
        except Exception as e:
            log.warning("  FAIL  %s: %s", key, e)
            out["failed"] += 1
            out["errors"].append({"key": key, "error": str(e)[:200]})
    return out


# ───────────────────────────── main flow ─────────────────────────────
async def main(args) -> None:
    from services.object_storage import get_storage
    storage = get_storage(force_backend="tigris")
    bucket = os.environ.get("TIGRIS_BUCKET") or ""
    log.info("=" * 64)
    log.info("Tigris migration starting · bucket=%s · dry_run=%s",
                  bucket, args.dry_run)
    log.info("=" * 64)

    # Step 1 — static + storage directory walks.
    grand = {"uploaded": 0, "skipped": 0, "failed": 0,
                      "bytes_uploaded": 0, "per_dir": []}
    only = (args.only_dir or "").strip().lower()
    for local_root_s, tigris_prefix, desc in DIR_CATALOG:
        local_root = Path(local_root_s)
        if only and only not in tigris_prefix.lower():
            continue
        log.info("")
        log.info("[%s] %s", tigris_prefix, desc)
        r = await _migrate_dir(storage, local_root, tigris_prefix,
                                                      dry_run=args.dry_run, verbose=args.verbose)
        log.info("  → uploaded=%d skipped=%d failed=%d (%.1f MB)",
                      r["uploaded"], r["skipped"], r["failed"],
                      r["bytes_uploaded"] / 1024 / 1024)
        for k in ("uploaded", "skipped", "failed", "bytes_uploaded"):
            grand[k] += r[k]
        grand["per_dir"].append({"prefix": tigris_prefix, **r})

    # Step 2 — track mp3s (DB rewrite path, reuse legacy migrator).
    track_summary = {"migrated": 0, "skipped_already_migrated": 0,
                                    "missing_local_file": 0, "failed": []}
    if not args.skip_tracks and not only:
        log.info("")
        log.info("[tracks] running migrate_tracks_to_tigris (DB rewrite path)")
        if args.dry_run:
            log.info("  → DRY RUN — track migration skipped (legacy script "
                          "doesn't support dry-run; will run on real pass).")
        else:
            db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            from scripts.migrate_tracks_to_tigris import migrate_tracks_to_tigris
            track_summary = await migrate_tracks_to_tigris(db)
            log.info("  → migrated=%d skipped=%d missing_local=%d failed=%d",
                          track_summary["migrated"],
                          track_summary["skipped_already_migrated"],
                          track_summary["missing_local_file"],
                          len(track_summary.get("failed") or []))

    # Step 3 — persist migration_state in Mongo for the health endpoint.
    if not args.dry_run:
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        now = datetime.now(timezone.utc)
        await db.migration_state.update_one(
            {"_id": "tigris_assets"},
            {"$set": {
                "last_run_at":      now,
                "last_run_dry":    bool(args.dry_run),
                "static_summary": {
                    "uploaded":              grand["uploaded"],
                    "skipped":                  grand["skipped"],
                    "failed":                    grand["failed"],
                    "bytes_uploaded": grand["bytes_uploaded"],
                    "per_dir":                  grand["per_dir"],
                },
                "tracks_summary": track_summary,
            }}, upsert=True)

    log.info("")
    log.info("=" * 64)
    log.info("GRAND TOTAL · uploaded=%d skipped=%d failed=%d (%.1f MB)",
                  grand["uploaded"], grand["skipped"], grand["failed"],
                  grand["bytes_uploaded"] / 1024 / 1024)
    log.info("TRACKS              · migrated=%d skipped=%d missing=%d failed=%d",
                  track_summary["migrated"],
                  track_summary["skipped_already_migrated"],
                  track_summary["missing_local_file"],
                  len(track_summary.get("failed") or []))
    log.info("=" * 64)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                                  help="Plan only — do not upload or write Mongo.")
    ap.add_argument("--verbose", action="store_true",
                                  help="Per-file SKIP/UPL/FAIL log lines.")
    ap.add_argument("--only-dir", type=str, default=None,
                                  help="Limit to one tigris prefix substring "
                                              "(e.g. 'channel_thumbnails').")
    ap.add_argument("--skip-tracks", action="store_true",
                                  help="Skip the legacy track migration step.")
    args = ap.parse_args()
    asyncio.run(main(args))
