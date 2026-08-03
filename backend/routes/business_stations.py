"""Phase 41 Session 3.A — Business Radio Page endpoints.

Business stations are `community_radio_stations` rows where
`page_type == "business_radio"` plus a `business_profile` subdoc.
This module owns the business-only routes; the wizard, discovery,
and slug-resolve endpoints stay in `community_stations.py` (with
small extensions for business payloads).

Verification model in this session: **manual only** (admin endpoint).
Google-Place auto-verification lands later.

Privacy / leak protection:
    - Unverified business profiles surface a `pending_verification: true`
      flag in `by-slug` responses and the `business_profile.phone` field
      is REDACTED until verified. All other fields (address, hours,
      website, social_links, logo, cover) remain visible — these are
      already public-by-default on the open web.
"""
from __future__ import annotations
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, HTTPException, Request,
                       UploadFile)

from auth import current_user

router = APIRouter(prefix="/api/stations", tags=["business-stations"])
admin_router = APIRouter(prefix="/api/admin/stations",
                          tags=["business-stations-admin"])
log = logging.getLogger("bigfm.business_stations")

VALID_CATEGORIES = {"restaurant", "cafe", "club", "retail",
                     "salon", "gym", "other"}
VALID_VERIFICATION = {"manual", "google_place", "domain"}

LOGO_MAX_BYTES  = 2 * 1024 * 1024   # 2 MB per spec
COVER_MAX_BYTES = 5 * 1024 * 1024   # 5 MB per spec
IMAGE_MIME_OK   = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
IMAGE_EXT_FROM_MIME = {
    "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/png":  "png", "image/webp": "webp",
}

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HOUR_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str:  return _now().isoformat()


def _is_admin(user: Optional[dict]) -> bool:
    return bool(user and (user.get("role") == "admin"
                          or user.get("is_admin")))


def validate_business_profile(profile: dict) -> dict:
    """Normalize + validate a `business_profile` payload. Raises 400
    on invalid shape. Returns the cleaned dict ready to persist."""
    if not isinstance(profile, dict):
        raise HTTPException(400, {"code": "validation_error",
                                   "field": "business_profile",
                                   "message": "Must be an object."})
    out: dict = {}
    legal = (profile.get("legal_name") or "").strip()
    if not legal:
        raise HTTPException(400, {"code": "validation_error",
                                   "field": "legal_name",
                                   "message": "Required."})
    out["legal_name"] = legal[:120]
    out["display_name"] = (profile.get("display_name") or legal)[:80]

    cat = (profile.get("category") or "other").strip().lower()
    if cat not in VALID_CATEGORIES:
        raise HTTPException(400, {"code": "validation_error",
                                   "field": "category",
                                   "allowed": sorted(VALID_CATEGORIES)})
    out["category"] = cat

    addr_required = ["address", "city", "country"]
    for f in addr_required:
        v = (profile.get(f) or "").strip()
        if not v:
            raise HTTPException(400, {"code": "validation_error",
                                       "field": f,
                                       "message": "Required."})
        out[f] = v[:120]

    for f in ("postal_code", "phone", "website",
               "google_place_id"):
        v = profile.get(f)
        out[f] = (v or "").strip()[:120] if v else None

    # Lat/lng optional but if present must be numeric.
    for f in ("latitude", "longitude"):
        v = profile.get(f)
        if v in (None, "", []):
            out[f] = None
        else:
            try:
                out[f] = float(v)
            except (TypeError, ValueError):
                raise HTTPException(400, {"code": "validation_error",
                                           "field": f,
                                           "message": "Must be numeric."})

    # Hours — 7-day grid. Each row: {open, close, closed:bool}.
    hours_raw = profile.get("hours") or {}
    if not isinstance(hours_raw, dict):
        raise HTTPException(400, {"code": "validation_error",
                                   "field": "hours",
                                   "message": "Must be a mapping of day→row."})
    hours: dict = {}
    for day in DAYS:
        row = hours_raw.get(day) or {}
        closed = bool(row.get("closed"))
        if closed:
            hours[day] = {"open": None, "close": None, "closed": True}
            continue
        o = (row.get("open") or "").strip()
        c = (row.get("close") or "").strip()
        if not (o and c):
            # Day omitted entirely → treat as closed (not invalid).
            hours[day] = {"open": None, "close": None, "closed": True}
            continue
        if not (HOUR_RE.match(o) and HOUR_RE.match(c)):
            raise HTTPException(400, {"code": "validation_error",
                                       "field": f"hours.{day}",
                                       "message": "Time must be HH:MM (24h)."})
        hours[day] = {"open": o, "close": c, "closed": False}
    out["hours"] = hours

    out["logo_url"]  = profile.get("logo_url")  or None
    out["cover_url"] = profile.get("cover_url") or None

    social = profile.get("social_links") or {}
    out["social_links"] = {
        k: (str(social.get(k) or "").strip()[:160] or None)
        for k in ("instagram", "facebook", "tiktok", "twitter")
    }

    # `verified` + `verification_method` are managed by the admin
    # endpoint only — caller can't self-flip.
    out["verified"] = False
    out["verification_method"] = None
    return out


def _redact_for_unverified(profile: dict) -> dict:
    """Return a copy of the business profile with sensitive fields
    masked when `verified=false`. Phone is the only field hidden in
    this session; future iterations may hide more once we have a
    fraud-prevention story."""
    if not profile:
        return profile
    if profile.get("verified"):
        return profile
    out = {**profile}
    if out.get("phone"):
        out["phone"] = None
    return out


def is_open_now(profile: dict,
                 now_utc: Optional[datetime] = None) -> Optional[bool]:
    """Best-effort "open now" computation using the row's hours.
    Returns True / False / None (unknown). We treat the hours grid
    as the business's LOCAL time — but we don't have a tz per row
    yet, so we use UTC plus the user's local time client-side for
    the final badge. Server-side returns a best-effort UTC-based
    answer; the frontend recomputes with the viewer's locale.
    """
    if not profile:
        return None
    now = now_utc or _now()
    day_idx = now.weekday()  # mon=0 … sun=6
    day_key = DAYS[day_idx]
    row = (profile.get("hours") or {}).get(day_key) or {}
    if row.get("closed"):
        return False
    o = row.get("open")
    c = row.get("close")
    if not (o and c):
        return None
    try:
        oh, om = map(int, o.split(":"))
        ch, cm = map(int, c.split(":"))
        open_min  = oh * 60 + om
        close_min = ch * 60 + cm
        cur_min   = now.hour * 60 + now.minute
        if close_min <= open_min:
            # Overnight (e.g. 22:00 → 02:00)
            return cur_min >= open_min or cur_min < close_min
        return open_min <= cur_min < close_min
    except Exception:
        return None


# ----- HTTP -------------------------------------------------------
async def _resolve_owner_station(db, slug: str, user: dict) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if s.get("owner_user_id") != user.get("user_id"):
        raise HTTPException(403, {"code": "permission_denied",
                                   "message": "Not station owner."})
    if s.get("page_type") != "business_radio":
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "Station is not a business."})
    s.pop("_id", None)
    return s


@router.post("/{slug}/business_profile")
async def update_business_profile(slug: str, request: Request, body: dict,
                                    user: dict = Depends(current_user)):
    """Owner-only post-publish update of business_profile fields.
    Preserves `verified` + `verification_method` (admin-managed) AND
    `logo_url` + `cover_url` (managed via separate upload endpoints).
    """
    db = request.app.state.db
    s = await _resolve_owner_station(db, slug, user)
    existing = s.get("business_profile") or {}
    # Carry over admin-managed + asset fields so caller can't tamper.
    merged_input = {**(body or {})}
    merged_input["logo_url"]  = existing.get("logo_url")
    merged_input["cover_url"] = existing.get("cover_url")
    cleaned = validate_business_profile(merged_input)
    cleaned["verified"]            = existing.get("verified", False)
    cleaned["verification_method"] = existing.get("verification_method")
    await db.community_radio_stations.update_one(
        {"slug": slug},
        {"$set": {"business_profile": cleaned,
                  "updated_at":        _now_iso()}})
    return {"ok": True, "business_profile": cleaned}


async def _upload_image(db, slug: str, user: dict,
                          *, file: UploadFile, kind: str,
                          max_bytes: int) -> str:
    s = await _resolve_owner_station(db, slug, user)
    raw = await file.read()
    if len(raw) > max_bytes:
        raise HTTPException(413, {"code": "image_too_large",
                                   "field": kind,
                                   "max_bytes": max_bytes})
    mime = (file.content_type or "").lower()
    if mime not in IMAGE_MIME_OK:
        raise HTTPException(400, {"code": "validation_error",
                                   "field": kind,
                                   "message": "Image must be JPEG/PNG/WebP.",
                                   "received_mime": mime})
    ext = IMAGE_EXT_FROM_MIME[mime]
    real_key = f"station_business/{s['station_id']}/{kind}.{ext}"
    try:
        from services.object_storage import get_storage
        storage = get_storage()
        tmp_path = f"/tmp/{s['station_id']}_{kind}.{ext}"
        with open(tmp_path, "wb") as f:
            f.write(raw)
        storage.upload(local_path=tmp_path, key=real_key, content_type=mime)
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        signed_url = storage.get_signed_url(key=real_key, expires_in=86400 * 7)
    except HTTPException:
        raise
    except Exception as e:
        log.error("[business] %s upload failed: %s", kind, e)
        raise HTTPException(500, {"code": "image_upload_failed"})
    # Persist the storage key (not the signed URL, which expires).
    field = f"business_profile.{kind}_storage_key"
    await db.community_radio_stations.update_one(
        {"slug": slug},
        {"$set": {field: real_key,
                  f"business_profile.{kind}_url": signed_url,
                  "updated_at": _now_iso()}})
    return signed_url


@router.post("/{slug}/business_profile/logo")
async def upload_business_logo(slug: str, request: Request,
                                 image: UploadFile = File(...),
                                 user: dict = Depends(current_user)):
    url = await _upload_image(request.app.state.db, slug, user,
                                file=image, kind="logo",
                                max_bytes=LOGO_MAX_BYTES)
    return {"ok": True, "logo_url": url}


@router.post("/{slug}/business_profile/cover")
async def upload_business_cover(slug: str, request: Request,
                                  image: UploadFile = File(...),
                                  user: dict = Depends(current_user)):
    url = await _upload_image(request.app.state.db, slug, user,
                                file=image, kind="cover",
                                max_bytes=COVER_MAX_BYTES)
    return {"ok": True, "cover_url": url}


# ----- Admin -----------------------------------------------------
@admin_router.post("/{slug}/verify_business")
async def admin_verify_business(slug: str, request: Request,
                                  body: dict,
                                  user: dict = Depends(current_user)):
    """Admin flips a business station's `verified` flag. Manual-only
    in this session. `verification_method` defaults to "manual" if not
    provided."""
    if not _is_admin(user):
        raise HTTPException(403, {"code": "permission_denied",
                                   "message": "Admin only."})
    db = request.app.state.db
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s or s.get("page_type") != "business_radio":
        raise HTTPException(404, {"code": "not_found"})
    method = (body.get("verification_method") or "manual").lower()
    if method not in VALID_VERIFICATION:
        raise HTTPException(400, {"code": "validation_error",
                                   "field": "verification_method",
                                   "allowed": sorted(VALID_VERIFICATION)})
    flag = bool(body.get("verified", True))
    await db.community_radio_stations.update_one(
        {"slug": slug},
        {"$set": {"business_profile.verified":            flag,
                  "business_profile.verification_method": (method if flag else None),
                  "business_profile.verified_at":         (_now_iso() if flag else None),
                  "updated_at":                            _now_iso()}})
    fresh = await db.community_radio_stations.find_one({"slug": slug})
    fresh.pop("_id", None)
    return {"ok": True,
            "verified":            flag,
            "verification_method": method if flag else None,
            "business_profile":   fresh.get("business_profile")}
