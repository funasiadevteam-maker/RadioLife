"""Phase 36c.5 (post-repack ads migration) — one-shot migrator.

Walks every `ad_creatives` MongoDB document and:

  1. For each row whose audio file lives on local disk
     (`audio_path` under /app/backend/static/ad_creatives/ or
     /app/backend/storage/ads/) and which has NO
     `storage_key_creative_audio` set (or whose key does not HEAD
     on Tigris), uploads the file to Tigris under the canonical
     `ad_creatives/<creative_id>.mp3` key and persists the key
     back on the row.

  2. Mirrors the same logic for the image counterpart
     (.webp / .png / .jpg) → `ad_creatives/<creative_id>.<ext>`.

  3. After both keys verify on Tigris, optionally unlinks the local
     file when --delete-local is passed. Otherwise leaves the local
     file as a fallback (the serve route is Tigris-first w/ local
     fallback, so leaving the local file in place is safe).

The script is idempotent — running it twice is a no-op for rows
that have already been migrated (their Tigris HEAD succeeds, so the
upload is skipped). Rows that were never on local disk are also
skipped (no source bytes to migrate).

USAGE:
  python -m scripts.migrate_ad_creatives_to_tigris            # dry-run
  python -m scripts.migrate_ad_creatives_to_tigris --apply    # do it
  python -m scripts.migrate_ad_creatives_to_tigris --apply --delete-local
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("bigfm.ads_migrate")
logging.basicConfig(level=logging.INFO,
                                  format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _creative_id(doc: dict) -> str:
    return doc.get("id") or doc.get("creative_id") or ""


def _local_audio_path(doc: dict) -> Path | None:
    ap = doc.get("audio_path")
    if not ap or ap == "x":
        return None
    p = Path(str(ap))
    return p if p.is_file() else None


def _local_image_path(doc: dict) -> Path | None:
    iu = doc.get("image_url")
    if not iu:
        return None
    # image_url is /api/static/ad_creatives/<file>.<ext>
    name = os.path.basename(iu)
    if not name:
        return None
    p = Path("/app/backend/static/ad_creatives") / name
    return p if p.is_file() else None


async def migrate(*, apply: bool, delete_local: bool) -> dict:
    db = AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]
    from services import object_storage as obs
    st = obs.get_storage()
    if st.backend_name != "tigris":
        logger.error("STORAGE_BACKEND must be 'tigris' to run this migration "
                              "(currently %s)", st.backend_name)
        return {"skipped": True, "reason": "STORAGE_BACKEND!=tigris"}
    scanned = audio_uploaded = image_uploaded = 0
    audio_bytes = image_bytes = 0
    local_unlinked = 0
    local_bytes_freed = 0
    errors: list[str] = []
    cursor = db.ad_creatives.find(
        {}, {"id": 1, "creative_id": 1, "audio_path": 1, "image_url": 1,
              "storage_key_creative_audio": 1, "storage_key_creative_image": 1,
              "_id": 1})
    async for doc in cursor:
        scanned += 1
        cid = _creative_id(doc)
        if not cid:
            continue
        local_a = _local_audio_path(doc)
        local_i = _local_image_path(doc)
        if not local_a and not local_i:
            continue
        update = {}
        # Audio leg.
        if local_a:
            key_a = obs.key_ad_creative_audio(cid, local_a.suffix.lstrip(".") or "mp3")
            head = st.head(key=key_a)
            already = bool(head and int(head.get("size") or 0) > 0)
            if already:
                if not doc.get("storage_key_creative_audio"):
                    update["storage_key_creative_audio"] = key_a
            else:
                try:
                    sz = local_a.stat().st_size
                    if apply:
                        st.upload(local_path=str(local_a), key=key_a,
                                          content_type="audio/mpeg")
                    audio_uploaded += 1
                    audio_bytes += sz
                    update["storage_key_creative_audio"] = key_a
                except Exception as e:
                    errors.append(f"audio:{cid}: {e}")
        # Image leg.
        if local_i:
            ext = local_i.suffix.lstrip(".") or "webp"
            key_i = obs.key_ad_creative_image(cid, ext)
            head_i = st.head(key=key_i)
            already_i = bool(head_i and int(head_i.get("size") or 0) > 0)
            if already_i:
                if not doc.get("storage_key_creative_image"):
                    update["storage_key_creative_image"] = key_i
            else:
                try:
                    sz_i = local_i.stat().st_size
                    if apply:
                        st.upload(local_path=str(local_i), key=key_i,
                                          content_type=f"image/{ext}")
                    image_uploaded += 1
                    image_bytes += sz_i
                    update["storage_key_creative_image"] = key_i
                except Exception as e:
                    errors.append(f"image:{cid}: {e}")
        if update and apply:
            await db.ad_creatives.update_one({"_id": doc["_id"]}, {"$set": update})
        # Local-disk cleanup (only after both legs are confirmed on Tigris).
        if apply and delete_local:
            ka = update.get("storage_key_creative_audio") or \
                       doc.get("storage_key_creative_audio")
            if local_a and ka and st.head(key=ka):
                try:
                    sz = local_a.stat().st_size
                    local_a.unlink()
                    local_unlinked += 1
                    local_bytes_freed += sz
                except OSError as e:
                    errors.append(f"unlink:{local_a}: {e}")
            ki = update.get("storage_key_creative_image") or \
                       doc.get("storage_key_creative_image")
            if local_i and ki and st.head(key=ki):
                try:
                    sz_i = local_i.stat().st_size
                    local_i.unlink()
                    local_unlinked += 1
                    local_bytes_freed += sz_i
                except OSError as e:
                    errors.append(f"unlink:{local_i}: {e}")
    summary = {"scanned": scanned, "apply": apply, "delete_local": delete_local,
                          "audio_uploaded": audio_uploaded,
                          "audio_bytes":      audio_bytes,
                          "image_uploaded":  image_uploaded,
                          "image_bytes":      image_bytes,
                          "local_unlinked":   local_unlinked,
                          "local_bytes_freed": local_bytes_freed,
                          "errors_count":     len(errors),
                          "errors":               errors[:25]}
    logger.info("[ads_migrate] %s", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                              help="Actually upload + persist; default is dry-run")
    ap.add_argument("--delete-local", action="store_true",
                              help="After upload, unlink local files (only with --apply)")
    args = ap.parse_args()
    res = asyncio.get_event_loop().run_until_complete(
        migrate(apply=args.apply, delete_local=args.delete_local))
    import json as _json
    print(_json.dumps(res, indent=2, default=str))
    return 0 if res.get("errors_count", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
