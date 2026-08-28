"""Phase CLAIM.1 — File upload helpers for claim proofs + station media.

Two namespaces:
    /app/backend/static/claim_proofs/{claim_id}/{filename}
                → sensitive; served ONLY through an authed admin endpoint,
                    NOT via the public static mount.
    /app/backend/static/station_media/{station_id}/{filename}
                → public banner / description-audio; served via the existing
                    `/api/static/...` static mount.

Validation:
    Docs   (business card, email screenshot, gov ID, station license) →
               PNG / JPG / WEBP / PDF, ≤ 5 MB each, ≤ 6 files per claim.
    Banner (station hero) → PNG / JPG / WEBP, ≤ 5 MB.
    Audio  (station intro clip) → MP3 / WAV, ≤ 3 MB, ≤ 30 seconds
               (duration probed via ffprobe when available).
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile

log = logging.getLogger("bigfm.claim1.uploads")

PROOFS_ROOT   = Path("/app/backend/static/claim_proofs")
STATION_ROOT  = Path("/app/backend/static/station_media")

# Ensure both roots exist on import — cheap, no-op if present.
PROOFS_ROOT.mkdir(parents=True, exist_ok=True)
STATION_ROOT.mkdir(parents=True, exist_ok=True)

DOC_EXTS      = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                                  "webp": "image/webp", "pdf": "application/pdf"}
IMAGE_EXTS  = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                                  "webp": "image/webp"}
AUDIO_EXTS  = {"mp3": "audio/mpeg", "wav": "audio/wav",
                                  "mpeg": "audio/mpeg"}

MAX_DOC_BYTES         = 5 * 1024 * 1024
MAX_IMAGE_BYTES      = 5 * 1024 * 1024
MAX_AUDIO_BYTES      = 3 * 1024 * 1024
MAX_AUDIO_SECONDS = 30.0
MAX_PROOF_FILES      = 6

DOC_TYPES = {"business_card", "business_email_screenshot",
                                  "government_id", "station_license", "other"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_slug(v: str) -> str:
    v = re.sub(r"[^a-zA-Z0-9._-]+", "-", v).strip("-.")
    return v[:80] or "file"


def _pick_ext(filename: str, content_type: str,
                              allowed: Dict[str, str]) -> Optional[str]:
    fn = (filename or "").lower()
    for ext in allowed:
        if fn.endswith("." + ext):
            return "jpg" if ext == "jpeg" else ("mp3" if ext == "mpeg" else ext)
    ct = (content_type or "").lower()
    for ext, mime in allowed.items():
        if ct == mime:
            return "jpg" if ext == "jpeg" else ("mp3" if ext == "mpeg" else ext)
    return None


# ─────────────────────────── Proof docs ───────────────────────────
async def persist_proof_documents(
    *, claim_id: str, files: List[UploadFile],
      document_types: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Persist proof docs for a claim.  Returns
       (accepted_docs[], rejected_docs[]) — the caller decides how to
       respond (usually: raise if ANY rejected)."""
    if not files:
        return [], []
    if len(files) > MAX_PROOF_FILES:
        raise ValueError(f"too_many_files:max_{MAX_PROOF_FILES}")

    proof_dir = PROOFS_ROOT / _sanitize_slug(claim_id)
    proof_dir.mkdir(parents=True, exist_ok=True)

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    types = document_types or []

    for idx, f in enumerate(files):
        doc_type = (types[idx] if idx < len(types) else "other").lower().strip()
        if doc_type not in DOC_TYPES:
            doc_type = "other"
        ext = _pick_ext(f.filename, f.content_type, DOC_EXTS)
        if not ext:
            rejected.append({"filename": f.filename,
                                                  "reason": "unsupported_type",
                                                  "allowed_mimes": sorted(set(DOC_EXTS.values()))})
            continue
        data = await f.read()
        if not data:
            rejected.append({"filename": f.filename, "reason": "empty"})
            continue
        if len(data) > MAX_DOC_BYTES:
            rejected.append({"filename": f.filename,
                                                  "reason": "file_too_large",
                                                  "max_bytes": MAX_DOC_BYTES})
            continue
        # Persist under {claim_id}/{docType}_{ts}_{hex}.{ext}
        ts = int(datetime.now(timezone.utc).timestamp())
        h = uuid.uuid4().hex[:8]
        out_name = f"{doc_type}_{ts}_{h}.{ext}"
        out_path = proof_dir / out_name
        out_path.write_bytes(data)
        try:
            from services.object_storage import get_storage as _get_storage
            _get_storage().upload_bytes(
                key=f"claim_proofs/{_sanitize_slug(claim_id)}/{out_name}",
                data=data)
        except Exception:
            pass
        accepted.append({
            "type":                doc_type,
            "filename":        _sanitize_slug(f.filename or out_name),
            "storage_path": str(out_path),
            "download_url": f"/api/admin/radio/claims/{claim_id}/proof/{out_name}",
            "mime":                DOC_EXTS[ext] if ext in DOC_EXTS
                                              else (DOC_EXTS.get("jpeg") if ext == "jpg" else "application/octet-stream"),
            "bytes":              len(data),
            "uploaded_at": _now_iso(),
        })
    return accepted, rejected


def open_proof_file(*, claim_id: str, filename: str) -> Optional[Path]:
    """Path-safe resolver — refuses `../`, returns None if missing."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    fp = PROOFS_ROOT / _sanitize_slug(claim_id) / filename
    if not fp.exists() or not fp.is_file():
        return None
    return fp


# ─────────────────────────── Station media ───────────────────────────
def _station_dir(station_id: str) -> Path:
    d = STATION_ROOT / _sanitize_slug(station_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def persist_banner(*, station_id: str, file: UploadFile) -> Dict[str, Any]:
    ext = _pick_ext(file.filename, file.content_type, IMAGE_EXTS)
    if not ext:
        raise ValueError("unsupported_banner_type")
    data = await file.read()
    if not data:
        raise ValueError("empty_file")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"file_too_large:max_{MAX_IMAGE_BYTES}")
    d = _station_dir(station_id)
    # Sweep older banners with alternate extensions to save disk.
    for other in IMAGE_EXTS:
        candidate = d / f"banner.{other}"
        if candidate.exists() and other != ext:
            try: candidate.unlink()
            except Exception: pass
    out_path = d / f"banner.{ext}"
    out_path.write_bytes(data)
    try:
        from services.object_storage import get_storage as _get_storage
        _get_storage().upload_bytes(
            key=f"station_media/{_sanitize_slug(station_id)}/banner.{ext}",
            data=data)
    except Exception:
        pass
    return {"banner_image_url": (f"/api/static/station_media/"
                                                                        f"{_sanitize_slug(station_id)}/banner.{ext}"),
                        "bytes": len(data)}


def _probe_audio_duration(path: Path) -> Optional[float]:
    """Return audio duration in seconds via ffprobe, or None if the tool
    isn't installed / the file is un-probable."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.check_output(
            [ffprobe, "-v", "error", "-show_entries",
              "format=duration", "-of",
              "default=noprint_wrappers=1:nokey=1", str(path)],
            timeout=10, stderr=subprocess.STDOUT).decode().strip()
        return float(out)
    except Exception:
        return None


async def persist_description_audio(*, station_id: str, file: UploadFile
                                                                                    ) -> Dict[str, Any]:
    ext = _pick_ext(file.filename, file.content_type, AUDIO_EXTS)
    if not ext:
        raise ValueError("unsupported_audio_type")
    data = await file.read()
    if not data:
        raise ValueError("empty_file")
    if len(data) > MAX_AUDIO_BYTES:
        raise ValueError(f"file_too_large:max_{MAX_AUDIO_BYTES}")
    d = _station_dir(station_id)
    for other in AUDIO_EXTS:
        candidate = d / f"description_audio.{other}"
        if candidate.exists() and other != ext:
            try: candidate.unlink()
            except Exception: pass
    out_path = d / f"description_audio.{ext}"
    out_path.write_bytes(data)
    try:
        from services.object_storage import get_storage as _get_storage
        _get_storage().upload_bytes(
            key=f"station_media/{_sanitize_slug(station_id)}/description_audio.{ext}",
            data=data)
    except Exception:
        pass
    # Probe duration; if over the cap, delete + raise.
    duration = _probe_audio_duration(out_path)
    if duration is not None and duration > MAX_AUDIO_SECONDS:
        try: out_path.unlink()
        except Exception: pass
        raise ValueError(f"audio_too_long:max_{MAX_AUDIO_SECONDS}s:"
                                                            f"got_{duration:.1f}s")
    return {"description_audio_url": (f"/api/static/station_media/"
                                                                                        f"{_sanitize_slug(station_id)}/"
                                                                                        f"description_audio.{ext}"),
                        "description_audio_duration_sec": duration,
                        "bytes": len(data)}
