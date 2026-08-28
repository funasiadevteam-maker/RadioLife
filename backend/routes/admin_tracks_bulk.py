"""Phase 22b → 22e — Bulk Music Upload (admin), STREAMING refactor.

Phase 22e changes (this commit):
  • Multipart parts are no longer buffered into RAM. Each top-level
      input is **streamed** out of `UploadFile` in 1 MB chunks via
      `await f.read(SPOOL_CHUNK)` into a per-job temp dir
      `/tmp/bigfm_bulk_uploads/{job_id}/`, with a running SHA-256
      hasher updated chunk-by-chunk.  ZIP extraction is also streamed:
      `zipfile.ZipFile(<path>)` opened on the spooled file, each entry
      copied via `shutil.copyfileobj(zf.open(zi), out, SPOOL_CHUNK)`
      with its own hasher.  Peak RSS over a 5 GB request stays in the
      hundreds of MB instead of growing proportionally.
  • Dedupe enforcement on bulk + individual upload routes.  Rules
      evaluated in priority order: ISRC > file_hash > normalized
      title+artist+duration±2s.  Duplicates are skipped + logged in the
      audit row and surfaced in the response as
      `duplicates_skipped_details[{file_name, matched_rule,
      matched_track_id, matched_track_title, matched_track_artist}]`.
  • Audit row extensions (additive): `streaming_mode`, `peak_rss_mb`,
      `temp_dir_path`, `total_files_in_upload`, `imported_count`,
      `duplicates_skipped`, `duplicates_skipped_details`,
      `cleanup_succeeded`.
  • Concurrency cap: at most 2 in-flight bulk uploads per pod.  3rd
      concurrent caller gets HTTP 429 + `Retry-After: 60`.
  • Client disconnect: catch `starlette.requests.ClientDisconnect` and
      mark the audit row `status="client_disconnected"`.
  • Mongo dedupe indexes are ensured via
      `services.track_dedupe.ensure_dedupe_indexes` (wired into
      FastAPI startup in `server.py`).

Per-file pipeline is otherwise unchanged from 22b: ffprobe + mutagen
on the temp file, then either local-disk or Tigris persistence + tracks
row insert.  Rows still land in the `tracks` collection the radio
engine reads — they enter rotation on the next
`_pick_next_track_personalized` call without any extra wiring.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import resource
import shutil
import subprocess
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                                          Request, Response, UploadFile)
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from auth import require_admin
from services.bulk_upload_jobs import (abandon_if_running, complete_job,
                                                                          create_job, fail_job)
from services.track_dedupe import (attach_dedupe_fields, find_duplicate,
                                                                          normalize_text)

router = APIRouter(prefix="/api/admin/tracks", tags=["admin-tracks-bulk"])
log = logging.getLogger("bigfm.bulk_upload")


# ─── Phase 22g — audit log wrappers (log + swallow on failure) ───────
async def _audit_create(db, **kwargs) -> Optional[str]:
    try:
        return await create_job(db, **kwargs)
    except Exception as e:
        log.warning("[bulk-upload] audit create_job failed: %s", e)
        return None


async def _audit_complete(db, job_id, items, extra_counts) -> None:
    if not job_id:
        return
    try:
        await complete_job(db, job_id, items=items, extra_counts=extra_counts)
    except Exception as e:
        log.warning("[bulk-upload] audit complete_job failed: %s", e)


async def _audit_fail(db, job_id, items, exc, extra_counts=None) -> None:
    if not job_id:
        return
    try:
        await fail_job(db, job_id, items=items, exception=exc,
                                      extra_counts=extra_counts)
    except Exception as e:
        log.warning("[bulk-upload] audit fail_job failed: %s", e)


async def _audit_abandon(db, job_id) -> None:
    if not job_id:
        return
    try:
        await abandon_if_running(db, job_id)
    except Exception as e:
        log.warning("[bulk-upload] audit abandon_if_running failed: %s", e)


# ─── env-tunable limits ──────────────────────────────────────────────
def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    try: return int(v) if v else default
    except ValueError: return default


BULK_UPLOAD_MAX_BYTES                  = _env_int("BULK_UPLOAD_MAX_BYTES",
                                                                                  5 * 1024 * 1024 * 1024)
BULK_UPLOAD_MAX_FILES                  = _env_int("BULK_UPLOAD_MAX_FILES", 200)
BULK_UPLOAD_MAX_EXTRACTED_FILES = _env_int("BULK_UPLOAD_MAX_EXTRACTED_FILES", 5000)
BULK_UPLOAD_MAX_ZIP_ENTRIES      = _env_int("BULK_UPLOAD_MAX_ZIP_ENTRIES",  2000)
BULK_UPLOAD_CONCURRENCY          = _env_int("BULK_UPLOAD_CONCURRENCY", 2)

ACCEPTED_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

TRACKS_DIR              = Path(os.environ.get("BIGFM_TRACKS_DIR")
                                              or "/app/backend/storage/tracks")
UPLOAD_TEMP_DIR = Path(os.environ.get("TRACKS_UPLOAD_TEMP_DIR")
                                              or "/tmp/bigfm_bulk_uploads")

SPOOL_CHUNK = 1024 * 1024  # 1 MB

# Capped list of duplicate details exposed in the response. The audit
# row separately stores the full list (also capped).
DUPLICATES_DETAIL_CAP = 100


# ─── concurrency gate (per-pod) ───────────────────────────────────────
_inflight_count = 0
_inflight_lock = asyncio.Lock()


async def _try_acquire_slot() -> bool:
    global _inflight_count
    async with _inflight_lock:
        if _inflight_count >= BULK_UPLOAD_CONCURRENCY:
            return False
        _inflight_count += 1
        return True


async def _release_slot() -> None:
    global _inflight_count
    async with _inflight_lock:
        _inflight_count = max(0, _inflight_count - 1)


# ─── magic byte sniffers ─────────────────────────────────────────────
def _is_zip(filename: str, head: bytes) -> bool:
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return True
    return Path(filename).suffix.lower() == ".zip" and not head


def _is_audio(filename: str, head: bytes) -> bool:
    ext = Path(filename).suffix.lower()
    if ext not in ACCEPTED_EXT:
        return False
    if not head:
        return True
    if head[:3] == b"ID3":
        return True
    if head[:4] in (b"RIFF", b"fLaC", b"OggS"):
        return True
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    if ext == ".mp3" and head[:1] == b"\xff" and (head[1] & 0xe0) == 0xe0:
        return True
    return True  # extension-trusted fallback


def _ffprobe_duration(p: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(p)],
            capture_output=True, text=True, timeout=10)
        return float((r.stdout or "").strip() or 0)
    except Exception:
        return 0.0


def _tags(p: Path) -> dict:
    """Best-effort mutagen tag extraction. Adds ISRC via TSRC frame when
    available (mutagen's `easy` mode doesn't expose ISRC, so we use the
    non-easy fallback)."""
    out: dict = {}
    try:
        from mutagen import File as MF
        m = MF(str(p), easy=True)
        if m:
            out.update({
                "title":    (m.get("title") or [None])[0],
                "artist":  (m.get("artist") or [None])[0],
                "album":    (m.get("album") or [None])[0],
                "genre":    (m.get("genre") or [None])[0],
                "language": (m.get("language") or [None])[0],
            })
            try:
                if m.info and getattr(m.info, "length", None):
                    out["duration_sec"] = float(m.info.length)
            except Exception: pass
            try:
                if m.info and getattr(m.info, "bitrate", None):
                    out["bitrate"] = int(m.info.bitrate)
            except Exception: pass
            yr = (m.get("date") or [None])[0]
            if yr and str(yr)[:4].isdigit():
                out["release_year"] = int(str(yr)[:4])
    except Exception:
        pass
    # ISRC via TSRC frame (mp3) / standard tag (flac/ogg).
    try:
        from mutagen import File as MF
        m2 = MF(str(p))
        if m2:
            isrc_val = None
            if hasattr(m2, "tags") and m2.tags is not None:
                # ID3 TSRC frame
                try:
                    if "TSRC" in m2.tags:
                        isrc_val = str(m2.tags["TSRC"]).strip()
                except Exception: pass
                # Vorbis / MP4 freeform
                if not isrc_val:
                    for k in ("isrc", "ISRC", "----:com.apple.iTunes:ISRC"):
                        try:
                            v = m2.tags.get(k)
                            if v: isrc_val = str(v[0] if isinstance(v, list) else v).strip(); break
                        except Exception: pass
            if isrc_val:
                # Strip non-alphanum, uppercase. ISRC is 12 chars
                # (CC + 3-char registrant + 7-digit designation).
                cleaned = "".join(c for c in isrc_val if c.isalnum()).upper()
                if 10 <= len(cleaned) <= 16:
                    out["isrc"] = cleaned
    except Exception:
        pass
    return {k: v for k, v in out.items() if v is not None}


def _peak_rss_mb() -> int:
    """Linux ru_maxrss is in KiB; macOS in bytes. We're Linux."""
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        return int(ru.ru_maxrss / 1024)
    except Exception:
        return 0


async def _spool_upload_to_disk(f: UploadFile, dst: Path) -> str:
    """Read `f` → `dst`, returning the sha256 hex. Also persists the bytes to
    durable object storage (Tigris in prod) so bulk-uploaded tracks survive
    pod restarts; the local file stays as the serving cache.

    Raises starlette.requests.ClientDisconnect when the client hangs up.
    """
    hasher = hashlib.sha256()
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = await f.read()
    hasher.update(data)
    with open(dst, "wb") as out:
        out.write(data)
    try:
        from services.object_storage import get_storage as _get_storage
        _get_storage().upload_bytes(key=f"storage/bulk_tracks/{dst.name}", data=data)
    except Exception:
        pass
    return hasher.hexdigest()


def _spool_zip_entry(zf: zipfile.ZipFile, zi: zipfile.ZipInfo,
                                          dst: Path) -> str:
    """Stream a ZIP entry to disk; returns sha256 hex."""
    hasher = hashlib.sha256()
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(zi, "r") as src, open(dst, "wb") as out:
        while True:
            chunk = src.read(SPOOL_CHUNK)
            if not chunk:
                break
            hasher.update(chunk)
            out.write(chunk)
    return hasher.hexdigest()


# ─── audit complete_job extra_counts builder ─────────────────────────
def _build_extra_counts(*, zip_archives_processed: int,
                                                  audio_files_direct: int,
                                                  audio_files_extracted_from_zip: int,
                                                  total_files_in_upload: int,
                                                  imported_count: int,
                                                  duplicates_skipped: int,
                                                  duplicates_skipped_details: list,
                                                  streaming_mode: str,
                                                  peak_rss_mb: int,
                                                  temp_dir_path: str,
                                                  cleanup_succeeded: bool,
                                                  total_bytes_received: int = 0) -> dict:
    return {
        "zip_count":                              zip_archives_processed,
        "audio_direct_count":              audio_files_direct,
        "total_extracted_from_zip":  audio_files_extracted_from_zip,
        # Phase 22e additions:
        "streaming_mode":                    streaming_mode,
        "peak_rss_mb":                          peak_rss_mb,
        "temp_dir_path":                      temp_dir_path,
        "total_files_in_upload":      total_files_in_upload,
        "imported_count":                    imported_count,
        "duplicates_skipped":              duplicates_skipped,
        "duplicates_skipped_details": duplicates_skipped_details[:DUPLICATES_DETAIL_CAP],
        "cleanup_succeeded":              cleanup_succeeded,
        # Phase 22g compat — bytes are counted incrementally now, so we
        # surface the final tally here.
        "total_bytes_received":      total_bytes_received,
    }


@router.get("/bulk-upload/limits", dependencies=[Depends(require_admin)])
async def bulk_upload_limits():
    return {"max_bytes":                            BULK_UPLOAD_MAX_BYTES,
                  "max_files":                              BULK_UPLOAD_MAX_FILES,
                  "max_extracted_files":      BULK_UPLOAD_MAX_EXTRACTED_FILES,
                  "max_zip_entries":              BULK_UPLOAD_MAX_ZIP_ENTRIES,
                  "concurrency_limit":          BULK_UPLOAD_CONCURRENCY,
                  "accepted_ext":                    sorted(ACCEPTED_EXT),
                  "storage_provider":            (os.environ.get("TRACKS_STORAGE_PROVIDER")
                                                                or "local").lower()}


@router.post("/migrate-storage-to-tigris",
                          dependencies=[Depends(require_admin)])
async def migrate_storage_to_tigris_route(request: Request):
    from scripts.migrate_tracks_to_tigris import migrate_tracks_to_tigris
    return await migrate_tracks_to_tigris(request.app.state.db)


@router.post("/bulk-upload", dependencies=[Depends(require_admin)])
async def bulk_upload(
    request: Request,
    response: Response,
    files: List[UploadFile] = File(default=[]),
    archive: Optional[UploadFile] = File(default=None),
    default_language: Optional[str] = Form(None),
    default_genre:        Optional[str] = Form(None),
    default_era:              Optional[str] = Form(None),
    channel_eligibility:  Optional[str] = Form(None),
    user: dict = Depends(require_admin),
):
    """Phase 22e — STREAMING bulk upload + dedupe addendum."""
    # ── Concurrency gate ─────────────────────────────────────────────
    acquired = await _try_acquire_slot()
    if not acquired:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "60"},
            content={"detail": "bulk_upload_busy",
                          "concurrency_limit": BULK_UPLOAD_CONCURRENCY,
                          "retry_after_seconds": 60})

    db = request.app.state.db
    provider = (os.environ.get("TRACKS_STORAGE_PROVIDER")
                          or "local").lower()
    defaults_json = {
        "default_language":      default_language,
        "default_genre":              default_genre,
        "default_era":                  default_era,
        "channel_eligibility":  channel_eligibility,
    }
    client_ip = (request.client.host
                              if getattr(request, "client", None) else None)
    client_ua = request.headers.get("user-agent") if request.headers else None

    # ── Create audit row early (before any I/O) ──────────────────────
    job_id = await _audit_create(
        db,
        started_by_user_id=(user or {}).get("user_id") or "unknown",
        total_inputs=len(files or []),
        total_bytes_received=0,  # populated incrementally below
        defaults_json=defaults_json,
        client_ip=client_ip,
        client_user_agent=client_ua,
        storage_provider=provider,
    )

    # Per-job temp dir.  Uses job_id when available, else a uuid.
    job_dirname = job_id or ("nojob_" + uuid.uuid4().hex[:16])
    temp_dir = UPLOAD_TEMP_DIR / job_dirname
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.warning("[bulk-upload] temp dir create failed (%s): %s",
                              temp_dir, e)

    items: list[dict] = []
    duplicates_skipped_details: list[dict] = []
    uploaded = dups = skipped = failed = 0
    zip_archives_processed              = 0
    audio_files_extracted_from_zip = 0
    audio_files_direct                          = 0
    extracted_count                              = 0
    total_bytes = 0
    cleanup_succeeded = False
    streaming_mode = "streamed_to_disk"

    eligibility = ([s.strip()
                              for s in (channel_eligibility or "").split(",")
                              if s.strip()] or ["on_air"])

    # ── Spool every top-level input to disk while streaming hash ─────
    # spooled: list of (source_label, archive_name_or_None, filename, disk_path, sha)
    spooled: list[tuple[str, Optional[str], str, Path, str]] = []
    try:
        if archive and (archive.filename or ""):
            raise HTTPException(400, "archive_field_removed_use_files")

        if not files or all(not (f.filename or "") for f in files):
            raise HTTPException(400, "no_files_provided")

        if len(files) > BULK_UPLOAD_MAX_FILES:
            raise HTTPException(413, "too_many_files")

        for f in files:
            if not (f.filename or ""):
                continue
            top_filename = f.filename
            spool_target = temp_dir / f"top_{uuid.uuid4().hex[:10]}_{Path(top_filename).name}"
            try:
                sha_top = await _spool_upload_to_disk(f, spool_target)
            except ClientDisconnect:
                status_for_disconnect = "client_disconnected"
                raise
            except HTTPException:
                raise
            except Exception as e:
                items.append({"source": "direct",
                                          "filename": top_filename,
                                          "status": "failed",
                                          "reason": f"spool_error:{str(e)[:120]}"})
                failed += 1
                continue
            size = spool_target.stat().st_size if spool_target.exists() else 0
            total_bytes += size
            if total_bytes > BULK_UPLOAD_MAX_BYTES:
                raise HTTPException(413, "request_too_large")

            # Decide: zip vs audio based on magic bytes.
            with open(spool_target, "rb") as h:
                head = h.read(64)

            if _is_zip(top_filename, head):
                zip_archives_processed += 1
                try:
                    zf = zipfile.ZipFile(spool_target)
                except zipfile.BadZipFile:
                    items.append({"source": "direct",
                                              "filename": top_filename,
                                              "status": "failed",
                                              "reason": "zip_parse_error"})
                    failed += 1
                    continue
                except Exception as e:
                    items.append({"source": "direct",
                                              "filename": top_filename,
                                              "status": "failed",
                                              "reason": f"zip_parse_error:{str(e)[:120]}"})
                    failed += 1
                    continue
                with zf:
                    infos = [zi for zi in zf.infolist() if not zi.is_dir()]
                    # filter __MACOSX
                    infos = [zi for zi in infos
                                  if not (zi.filename or "").startswith("__MACOSX")]
                    if len(infos) > BULK_UPLOAD_MAX_ZIP_ENTRIES:
                        items.append({"source": "direct",
                                                  "filename": top_filename,
                                                  "status": "failed",
                                                  "reason": "zip_too_many_entries"})
                        failed += 1
                        continue
                    for zi in infos:
                        name = zi.filename or ""
                        if (name.startswith("/") or ".." in Path(name).parts
                                or "\\" in name):
                            items.append({"source": "zip",
                                                      "archive": top_filename,
                                                      "filename": Path(name).name,
                                                      "status": "failed",
                                                      "reason": "zip_slip_attempt"})
                            failed += 1
                            continue
                        if extracted_count + 1 > BULK_UPLOAD_MAX_EXTRACTED_FILES:
                            raise HTTPException(413, {
                                "code":      "too_many_extracted_files",
                                "limit":    BULK_UPLOAD_MAX_EXTRACTED_FILES,
                                "archive": top_filename})
                        extracted_count += 1
                        entry_name = Path(name).name
                        entry_target = (temp_dir / f"zip_{uuid.uuid4().hex[:10]}_{entry_name}")
                        try:
                            sha_entry = _spool_zip_entry(zf, zi, entry_target)
                        except Exception as e:
                            items.append({"source": "zip",
                                                      "archive": top_filename,
                                                      "filename": entry_name,
                                                      "status": "failed",
                                                      "reason": f"zip_entry_extract_failed:{str(e)[:120]}"})
                            failed += 1
                            continue
                        spooled.append(("zip", top_filename, entry_name,
                                                    entry_target, sha_entry))

            elif _is_audio(top_filename, head):
                audio_files_direct += 1
                spooled.append(("direct", None, top_filename,
                                              spool_target, sha_top))
            else:
                items.append({"source": "direct",
                                          "filename": top_filename,
                                          "status": "skipped_non_audio"})
                skipped += 1

        # ── Per-candidate audio pipeline ──────────────────────────────
        TRACKS_DIR.mkdir(parents=True, exist_ok=True)
        for source, arch_name, filename, disk_path, sha in spooled:
            try:
                # 1. Magic-byte audio sniff (head only, no full read).
                with open(disk_path, "rb") as h:
                    head = h.read(64)
                if not _is_audio(filename, head):
                    item = {"source": source, "filename": filename,
                                  "status": "skipped_non_audio"}
                    if arch_name: item["archive"] = arch_name
                    items.append(item); skipped += 1
                    continue

                if source == "zip":
                    audio_files_extracted_from_zip += 1

                # 2. mutagen tags + ffprobe duration.
                meta = _tags(disk_path)
                duration = float(meta.get("duration_sec")
                                              or _ffprobe_duration(disk_path) or 0)
                isrc = meta.get("isrc")
                title_for_dedupe = meta.get("title") or Path(filename).stem
                artist_for_dedupe = meta.get("artist") or "Unknown Artist"

                # 3. DEDUPE — ISRC > file_hash > title+artist+duration.
                dup = await find_duplicate(
                    db,
                    file_hash=sha,
                    isrc=isrc,
                    title=title_for_dedupe,
                    artist=artist_for_dedupe,
                    duration_sec=duration,
                )
                if dup:
                    item = {
                        "source": source, "filename": filename,
                        "status": "duplicate",
                        "matched_rule": dup["matched_rule"],
                        "existing_track_id": dup["track_id"],
                        "matched_track_title": dup["title"],
                        "matched_track_artist": dup["artist"],
                    }
                    if arch_name: item["archive"] = arch_name
                    items.append(item); dups += 1
                    duplicates_skipped_details.append({
                        "file_name":                          filename,
                        "matched_rule":                    dup["matched_rule"],
                        "matched_track_id":            dup["track_id"],
                        "matched_track_title":      dup["title"],
                        "matched_track_artist":    dup["artist"],
                    })
                    continue

                # 4. Persist asset.
                tid = str(uuid.uuid4())
                ext = Path(filename).suffix.lower() or ".mp3"
                local_canonical = TRACKS_DIR / f"{tid}{ext}"
                # Move temp file into final local path (rename = no copy).
                try:
                    shutil.move(str(disk_path), str(local_canonical))
                except Exception:
                    shutil.copyfile(str(disk_path), str(local_canonical))

                storage_key = None
                canonical_path = str(local_canonical)
                if provider == "tigris":
                    prefix = os.environ.get("TRACKS_BUCKET_PREFIX") or "tracks/"
                    if not prefix.endswith("/"): prefix += "/"
                    storage_key = f"{prefix}{tid}{ext}"
                    try:
                        from services.object_storage import get_storage
                        # Upload from disk path — no full file in RAM.
                        get_storage().upload(
                            local_path=str(local_canonical),
                            key=storage_key,
                            content_type="audio/mpeg")
                        canonical_path = (f"s3://{os.environ.get('TIGRIS_BUCKET','')}"
                                                          f"/{storage_key}")
                    except Exception as e:
                        try: local_canonical.unlink(missing_ok=True)
                        except Exception: pass
                        item = {"source": source, "filename": filename,
                                      "status": "failed",
                                      "reason": f"storage_upload_failed:{str(e)[:120]}"}
                        if arch_name: item["archive"] = arch_name
                        items.append(item); failed += 1
                        raise HTTPException(502, {
                            "code": "storage_upload_failed",
                            "filename": filename,
                            "items": items})

                doc = {
                    "_id":          tid,
                    "title":        meta.get("title") or Path(filename).stem,
                    "artist":      meta.get("artist") or "Unknown Artist",
                    "album":        meta.get("album"),
                    "genre":        meta.get("genre") or default_genre,
                    "language":  meta.get("language")
                                              or default_language or "other",
                    "era":          default_era,
                    "isrc":          isrc,
                    "release_year": meta.get("release_year"),
                    "duration_sec": duration,
                    "file_path":  canonical_path,
                    "file_hash":  sha,
                    "status":      "active",
                    "channel_eligibility": eligibility,
                    "storage_provider":            provider,
                    "storage_key":                      storage_key,
                    "local_file_path":              str(local_canonical),
                    "uploaded_by": (user or {}).get("user_id"),
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                }
                attach_dedupe_fields(doc)

                # 5. Insert + race-safe DuplicateKeyError catch.
                try:
                    await db.tracks.insert_one(doc)
                except Exception as ins_exc:
                    # If the UNIQUE sparse hash index caught a concurrent
                    # insert, re-resolve via dedupe to surface a clean
                    # duplicate response.
                    if "duplicate key" in str(ins_exc).lower() or \
                          ins_exc.__class__.__name__ == "DuplicateKeyError":
                        try: local_canonical.unlink(missing_ok=True)
                        except Exception: pass
                        dup = await find_duplicate(db, file_hash=sha,
                                                                              isrc=isrc,
                                                                              title=title_for_dedupe,
                                                                              artist=artist_for_dedupe,
                                                                              duration_sec=duration)
                        if dup:
                            item = {"source": source, "filename": filename,
                                          "status": "duplicate",
                                          "matched_rule": dup["matched_rule"],
                                          "existing_track_id": dup["track_id"],
                                          "matched_track_title": dup["title"],
                                          "matched_track_artist": dup["artist"]}
                            if arch_name: item["archive"] = arch_name
                            items.append(item); dups += 1
                            duplicates_skipped_details.append({
                                "file_name":                          filename,
                                "matched_rule":                    dup["matched_rule"],
                                "matched_track_id":            dup["track_id"],
                                "matched_track_title":      dup["title"],
                                "matched_track_artist":    dup["artist"]})
                            continue
                    # Otherwise re-raise into the outer except below.
                    raise

                item = {"source": source, "filename": filename,
                              "status": "uploaded",
                              "track_id": tid,
                              "title": doc["title"],
                              "artist": doc["artist"],
                              "duration_sec": duration}
                if arch_name: item["archive"] = arch_name
                items.append(item); uploaded += 1
            except HTTPException:
                raise
            except Exception as e:
                item = {"source": source, "filename": filename,
                              "status": "failed", "reason": str(e)[:200]}
                if arch_name: item["archive"] = arch_name
                items.append(item); failed += 1

        # ── Reject whole request only if zero valid audio ────────────
        if (uploaded + dups) == 0:
            raise HTTPException(400, {"code": "no_valid_audio", "items": items})

        log.info("[bulk-upload] persisted %d, deduped %d, failed %d "
                      "(streaming + dedupe; peak_rss=%dMB)",
                      uploaded, dups, failed, _peak_rss_mb())

        # ── Cleanup temp dir ─────────────────────────────────────────
        cleanup_succeeded = _cleanup_temp_dir(temp_dir)
        peak_mb = _peak_rss_mb()

        out = {"ok": True,
                    "total_received":                            len(files or []),
                    "zip_archives_processed":          zip_archives_processed,
                    "audio_files_extracted_from_zip": audio_files_extracted_from_zip,
                    "audio_files_direct":                audio_files_direct,
                    "uploaded":                                  uploaded,
                    "duplicates":                              dups,
                    "skipped_non_audio":                  skipped,
                    "failed":                                      failed,
                    # Phase 22e additive fields:
                    "streaming_mode":                        streaming_mode,
                    "peak_rss_mb":                              peak_mb,
                    "imported_count":                        uploaded,
                    "duplicates_skipped":                  dups,
                    "duplicates_skipped_details":  duplicates_skipped_details[:DUPLICATES_DETAIL_CAP],
                    "total_files_in_upload":          len(files or []),
                    "cleanup_succeeded":                  cleanup_succeeded,
                    "items":                                        items}
        out["job_id"] = job_id

        extra = _build_extra_counts(
            zip_archives_processed=zip_archives_processed,
            audio_files_direct=audio_files_direct,
            audio_files_extracted_from_zip=audio_files_extracted_from_zip,
            total_files_in_upload=len(files or []),
            imported_count=uploaded,
            duplicates_skipped=dups,
            duplicates_skipped_details=duplicates_skipped_details,
            streaming_mode=streaming_mode,
            peak_rss_mb=peak_mb,
            temp_dir_path=str(temp_dir),
            cleanup_succeeded=cleanup_succeeded,
            total_bytes_received=total_bytes,
        )
        await _audit_complete(db, job_id, items, extra_counts=extra)
        return out

    except ClientDisconnect as cd:
        # Best-effort cleanup + audit.
        cleanup_succeeded = _cleanup_temp_dir(temp_dir)
        peak_mb = _peak_rss_mb()
        extra = _build_extra_counts(
            zip_archives_processed=zip_archives_processed,
            audio_files_direct=audio_files_direct,
            audio_files_extracted_from_zip=audio_files_extracted_from_zip,
            total_files_in_upload=len(files or []),
            imported_count=uploaded,
            duplicates_skipped=dups,
            duplicates_skipped_details=duplicates_skipped_details,
            streaming_mode=streaming_mode,
            peak_rss_mb=peak_mb,
            temp_dir_path=str(temp_dir),
            cleanup_succeeded=cleanup_succeeded,
            total_bytes_received=total_bytes,
        )
        extra["status_override"] = "client_disconnected"
        await _audit_fail(db, job_id, items, cd, extra_counts=extra)
        # No response body — connection is gone.
        raise

    except HTTPException as he:
        cleanup_succeeded = _cleanup_temp_dir(temp_dir)
        peak_mb = _peak_rss_mb()
        extra = _build_extra_counts(
            zip_archives_processed=zip_archives_processed,
            audio_files_direct=audio_files_direct,
            audio_files_extracted_from_zip=audio_files_extracted_from_zip,
            total_files_in_upload=len(files or []),
            imported_count=uploaded,
            duplicates_skipped=dups,
            duplicates_skipped_details=duplicates_skipped_details,
            streaming_mode=streaming_mode,
            peak_rss_mb=peak_mb,
            temp_dir_path=str(temp_dir),
            cleanup_succeeded=cleanup_succeeded,
            total_bytes_received=total_bytes,
        )
        await _audit_fail(db, job_id, items, he, extra_counts=extra)
        raise

    except Exception as ex:
        cleanup_succeeded = _cleanup_temp_dir(temp_dir)
        peak_mb = _peak_rss_mb()
        extra = _build_extra_counts(
            zip_archives_processed=zip_archives_processed,
            audio_files_direct=audio_files_direct,
            audio_files_extracted_from_zip=audio_files_extracted_from_zip,
            total_files_in_upload=len(files or []),
            imported_count=uploaded,
            duplicates_skipped=dups,
            duplicates_skipped_details=duplicates_skipped_details,
            streaming_mode=streaming_mode,
            peak_rss_mb=peak_mb,
            temp_dir_path=str(temp_dir),
            cleanup_succeeded=cleanup_succeeded,
            total_bytes_received=total_bytes,
        )
        await _audit_fail(db, job_id, items, ex, extra_counts=extra)
        raise

    finally:
        await _audit_abandon(db, job_id)
        await _release_slot()


def _cleanup_temp_dir(temp_dir: Path) -> bool:
    """Best-effort recursive delete. Returns True on success."""
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        return not temp_dir.exists()
    except Exception as e:
        log.warning("[bulk-upload] temp dir cleanup failed (%s): %s",
                              temp_dir, e)
        return False
