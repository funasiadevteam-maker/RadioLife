"""Partner API v1 — Phase C creative library + multi-format line items.

Creatives are first-class, independent of campaigns:

  POST /creatives            create metadata (optionally with a hosted asset_url)
  POST /creatives/upload-url  short-lived signed PUT → upload straight to storage
  POST /creatives/{id}/finalize  validate the uploaded object → READY
  POST /creatives/import      server-side, SSRF-safe fetch of a remote https asset
  GET/PATCH/DELETE            manage the library

Campaigns then reference creative_ids, and a parent campaign can hold several
line items (multi-format) that each reuse creatives.
"""
from __future__ import annotations

import ipaddress
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from services.object_storage import get_storage

CREATIVE_TYPES = {"audio", "image", "video", "html"}

# Lifecycle: uploading → processing → ready → (pending_review → approved/rejected)
CREATIVE_STATUSES = ["uploading", "processing", "ready", "pending_review",
                     "approved", "rejected", "quarantined", "error"]

# Per-type validation rules used at create + finalize.
RULES = {
    "audio": {"mimes": {"audio/mpeg", "audio/mp3", "audio/aac", "audio/mp4",
                        "audio/wav", "audio/x-wav", "audio/ogg"},
              "exts": {"mp3", "m4a", "aac", "wav", "ogg"},
              "max_bytes": 15 * 1024 * 1024, "max_duration_seconds": 60},
    "image": {"mimes": {"image/png", "image/jpeg", "image/webp", "image/gif"},
              "exts": {"png", "jpg", "jpeg", "webp", "gif"},
              "max_bytes": 5 * 1024 * 1024},
    "video": {"mimes": {"video/mp4", "video/webm", "video/quicktime"},
              "exts": {"mp4", "webm", "mov"},
              "max_bytes": 100 * 1024 * 1024, "max_duration_seconds": 180},
    "html": {"mimes": {"text/html"}, "exts": {"html", "htm"},
             "max_bytes": 512 * 1024},
}

UPLOAD_URL_TTL = 900  # 15 min


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cid() -> str:
    return "crv_" + uuid.uuid4().hex[:18]


def _clean(d: dict) -> dict:
    d = dict(d or {})
    d.pop("_id", None)
    for k in ("created_at", "updated_at", "expires_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    return d


async def ensure_creative_indexes(db) -> None:
    await db.creative_assets.create_index(
        [("partner_id", 1), ("environment", 1), ("status", 1)], name="crv_partner")
    await db.creative_assets.create_index("creative_id", unique=True, name="crv_id")
    await db.campaign_line_items.create_index("parent_id", name="cli_parent")
    await db.campaign_line_items.create_index("line_item_id", unique=True, name="cli_id")
    await db.api_parent_campaigns.create_index("parent_id", unique=True, name="parent_id")


def validate_metadata(ctype: str, *, size_bytes: Optional[int] = None,
                      mime: Optional[str] = None, duration_seconds: Optional[float] = None,
                      filename: Optional[str] = None) -> Optional[dict]:
    """Return an error dict if the declared metadata violates the rules, else None."""
    if ctype not in CREATIVE_TYPES:
        return {"code": "invalid_creative_type", "field": "type",
                "message": f"type must be one of {sorted(CREATIVE_TYPES)}"}
    rule = RULES[ctype]
    if mime and rule.get("mimes") and mime.lower() not in rule["mimes"]:
        return {"code": "invalid_mime", "field": "mime",
                "message": f"{mime} not allowed for {ctype}"}
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if rule.get("exts") and ext not in rule["exts"]:
            return {"code": "invalid_extension", "field": "filename",
                    "message": f".{ext} not allowed for {ctype}"}
    if size_bytes is not None and size_bytes > rule["max_bytes"]:
        return {"code": "file_too_large", "field": "size_bytes",
                "message": f"exceeds {rule['max_bytes']} bytes for {ctype}"}
    md = rule.get("max_duration_seconds")
    if md and duration_seconds and duration_seconds > md:
        return {"code": "duration_exceeds_max", "field": "duration_seconds",
                "message": f"exceeds {md}s for {ctype}"}
    return None


def signed_upload(key: str, content_type: str, expires_in: int = UPLOAD_URL_TTL) -> dict:
    """A short-lived direct-to-storage upload target. Uses an S3 presigned PUT on
    Tigris; falls back to the local proxy route in dev."""
    st = get_storage()
    if getattr(st, "backend_name", "") == "tigris":
        url = st.s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": st.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in)
        return {"upload_url": url, "method": "PUT",
                "headers": {"Content-Type": content_type}}
    return {"upload_url": f"/api/storage/local/{key}", "method": "PUT",
            "headers": {"Content-Type": content_type},
            "note": "local dev backend — direct PUT is not enforced"}


# ── SSRF-safe remote import ─────────────────────────────────────────
def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


def assert_safe_url(url: str) -> None:
    """Raise ValueError if the URL is not a safe, public https target (SSRF guard)."""
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError("import_url_must_be_https")
    if not p.hostname:
        raise ValueError("import_url_invalid_host")
    blocked = {"localhost", "metadata.google.internal", "169.254.169.254"}
    if p.hostname.lower() in blocked:
        raise ValueError("import_url_blocked_host")
    if not _is_public_host(p.hostname):
        raise ValueError("import_url_private_or_unresolvable")


__all__ = [
    "CREATIVE_TYPES", "CREATIVE_STATUSES", "RULES", "UPLOAD_URL_TTL",
    "ensure_creative_indexes", "validate_metadata", "signed_upload",
    "assert_safe_url", "_now", "_cid", "_clean",
]
