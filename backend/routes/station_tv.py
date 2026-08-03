"""Phase 41 Session 4.A — In-Store Business TV Display routes.

Endpoints in this module:

  - `GET    /api/tv/{slug}`                                  (public)
      Compact kiosk state: station + business_profile snapshot +
      now_playing (best-effort, sampled from station's musical taste
      using a 3-minute global slot index) + top 3 active announcements
      + qr_target_url. 8-second in-process cache to keep TV pages cheap.

  - `POST   /api/stations/{slug}/announcements`              (owner)
  - `GET    /api/stations/{slug}/announcements`              (public list, owner sees expired)
  - `PATCH  /api/stations/{slug}/announcements/{ann_id}`     (owner)
  - `DELETE /api/stations/{slug}/announcements/{ann_id}`     (owner)
  - `POST   /api/stations/{slug}/announcements/{ann_id}/image` (owner, ≤2 MB)

Rules:

  - Private/unlisted stations 403 the public TV endpoint.
  - Active-cap of 10 announcements per station. Beyond that the create
    endpoint returns 429 `{code: "active_cap", ...}`.
  - `now_playing` is a best-effort projection — the radio engine is
    per-listener so there isn't a single "broadcast" track. We sample
    a track that matches the station's allowed_genres + allowed_moods
    and rotate it deterministically on a 3-minute slot so every TV
    viewer sees the same value. When no matching track exists,
    `now_playing: null` and the kiosk shows a placeholder.
"""
from __future__ import annotations
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, HTTPException, Query,
                       Request, UploadFile)

from auth import current_user, current_user_optional

router = APIRouter(prefix="/api", tags=["station-tv"])
log = logging.getLogger("bigfm.station_tv")

# In-process cache keyed by slug. 8s per spec.
_TV_CACHE: dict[str, dict] = {}
_TV_TTL_SEC = 8.0

MAX_ACTIVE_ANNOUNCEMENTS = 10
ANNOUNCEMENT_MAX_CHARS   = 280
ANNOUNCEMENT_IMG_MAX_BYTES = 2 * 1024 * 1024

IMAGE_MIME_OK   = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
IMAGE_EXT_FROM_MIME = {
    "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/png":  "png", "image/webp": "webp",
}

ID_RE = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")

PUBLIC_FRONTEND_URL = (os.environ.get("PUBLIC_FRONTEND_URL")
                         or os.environ.get("PUBLIC_BACKEND_URL")
                         or os.environ.get("REACT_APP_BACKEND_URL")
                         or "").rstrip("/")


def _bust_caches(slug: str) -> None:
    """TV state cache + Phase 41 S5 analytics cache. Best-effort."""
    _TV_CACHE.pop(slug, None)
    try:
        from routes.station_analytics import bust_analytics_cache
        bust_analytics_cache(slug)
    except Exception:
        pass


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str:  return _now().isoformat()


def _is_admin(user: Optional[dict]) -> bool:
    return bool(user and (user.get("role") == "admin" or user.get("is_admin")))


def _strip_id(d: dict) -> dict:
    d.pop("_id", None)
    return d


def _is_active(a: dict, now_iso: str) -> bool:
    s = a.get("starts_at")
    e = a.get("ends_at")
    if s and s > now_iso:
        return False
    if e and e <= now_iso:
        return False
    return True


def _strip_announcement(a: dict, now_iso: str,
                          *, owner_view: bool = False) -> dict:
    """Strip a station_announcements doc for outbound JSON.

    `owner_view=True` includes the FULL coupon sub-document
    (including `redemptions_count` and `max_redemptions`).
    Public callers receive a reduced `coupon_summary` projection via
    `services.coupon_engine.coupon_summary_public` so we don't leak
    raw counter math beyond what's needed for "X claimed of Y" copy.
    """
    a = {k: v for k, v in a.items() if k != "_id"}
    a["active"] = _is_active(a, now_iso)
    coupon = a.get("coupon")
    if coupon:
        if owner_view:
            # Pass the full sub-doc through — owners see counts/max etc.
            pass
        else:
            # Project a safe, listener-friendly summary.
            try:
                from services.coupon_engine import coupon_summary_public
                a["coupon"] = coupon_summary_public(coupon)
            except Exception:
                # Belt and braces — never let a coupon serialization
                # bug break announcement listing.
                a.pop("coupon", None)
    return a


# ----- announcement validation ------------------------------------
def _parse_iso(v, field: str) -> Optional[str]:
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise HTTPException(400, {"code": "validation_error", "field": field,
                                    "message": "Must be ISO-8601 string."})
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, {"code": "validation_error", "field": field,
                                    "message": "Must be ISO-8601 string."})
    return v


def _validate_announcement_body(body: dict, *, allow_partial: bool = False):
    out: dict = {}
    if "message" in body or not allow_partial:
        msg = (body.get("message") or "").strip()
        if not msg:
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "message",
                                        "message": "Message required."})
        if len(msg) > ANNOUNCEMENT_MAX_CHARS:
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "message",
                                        "max_chars": ANNOUNCEMENT_MAX_CHARS,
                                        "message": "Message too long."})
        out["message"] = msg

    if "priority" in body or not allow_partial:
        p = body.get("priority", 5)
        try:
            p = int(p)
        except Exception:
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "priority",
                                        "message": "Priority must be 1–10."})
        if p < 1 or p > 10:
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "priority",
                                        "message": "Priority must be 1–10."})
        out["priority"] = p

    if "starts_at" in body or not allow_partial:
        out["starts_at"] = _parse_iso(body.get("starts_at"), "starts_at")
    if "ends_at" in body or not allow_partial:
        out["ends_at"]   = _parse_iso(body.get("ends_at"),   "ends_at")

    if (out.get("starts_at") and out.get("ends_at")
            and out["starts_at"] >= out["ends_at"]):
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "ends_at",
                                    "message": "ends_at must be after starts_at."})

    if "image_url" in body:
        u = body.get("image_url")
        if u is not None and not isinstance(u, str):
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "image_url",
                                        "message": "image_url must be a string or null."})
        out["image_url"] = u or None

    return out


async def _resolve_owner_station(db, slug: str, user: dict) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if s.get("owner_user_id") != user.get("user_id") and not _is_admin(user):
        raise HTTPException(403, {"code": "permission_denied",
                                    "message": "Not station owner."})
    return _strip_id(s)


# ----- announcement HTTP -----------------------------------------
@router.post("/stations/{slug}/announcements")
async def create_announcement(slug: str, request: Request, body: dict,
                                 user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _resolve_owner_station(db, slug, user)
    cleaned = _validate_announcement_body(body, allow_partial=False)

    now_iso = _now_iso()
    # Count currently-active rows (active === now is between starts/ends).
    active_count = 0
    async for a in db.station_announcements.find({"station_slug": slug}):
        if _is_active(a, now_iso):
            active_count += 1
    if active_count >= MAX_ACTIVE_ANNOUNCEMENTS:
        raise HTTPException(429, {"code": "active_cap",
                                    "max_active": MAX_ACTIVE_ANNOUNCEMENTS,
                                    "message": f"Maximum {MAX_ACTIVE_ANNOUNCEMENTS} active announcements at a time."})

    import uuid
    ann_id = f"ann_{uuid.uuid4().hex[:12]}"
    doc = {
        "_id":          ann_id,
        "id":           ann_id,
        "station_id":   s["station_id"],
        "station_slug": slug,
        "message":      cleaned["message"],
        "image_url":    cleaned.get("image_url"),
        "priority":     cleaned.get("priority", 5),
        "starts_at":    cleaned.get("starts_at"),
        "ends_at":      cleaned.get("ends_at"),
        "created_at":   now_iso,
        "created_by":   user.get("user_id"),
    }
    await db.station_announcements.insert_one(doc)
    _bust_caches(slug)
    return _strip_announcement(dict(doc), now_iso, owner_view=True)


@router.get("/stations/{slug}/announcements")
async def list_announcements(slug: str, request: Request,
                                include_expired: bool = Query(False),
                                user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})

    is_owner = bool(user and user.get("user_id") == s.get("owner_user_id"))
    now_iso = _now_iso()
    q = {"station_slug": slug}
    owner_or_admin = bool(is_owner or _is_admin(user))
    items: list = []
    async for a in db.station_announcements.find(q).sort([("priority", -1),
                                                              ("created_at", -1)]):
        a_strip = _strip_announcement(dict(a), now_iso,
                                          owner_view=owner_or_admin)
        if not owner_or_admin:
            if not a_strip["active"]:
                continue
        elif not include_expired and not a_strip["active"]:
            continue
        items.append(a_strip)
    return {"items": items, "count": len(items)}


@router.patch("/stations/{slug}/announcements/{ann_id}")
async def patch_announcement(slug: str, ann_id: str, request: Request,
                                body: dict, user: dict = Depends(current_user)):
    if not ID_RE.match(ann_id):
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "ann_id"})
    db = request.app.state.db
    await _resolve_owner_station(db, slug, user)
    a = await db.station_announcements.find_one({"_id": ann_id,
                                                     "station_slug": slug})
    if not a:
        raise HTTPException(404, {"code": "not_found"})
    cleaned = _validate_announcement_body(body, allow_partial=True)
    cleaned["updated_at"] = _now_iso()
    await db.station_announcements.update_one(
        {"_id": ann_id}, {"$set": cleaned})
    _bust_caches(slug)
    fresh = await db.station_announcements.find_one({"_id": ann_id})
    return _strip_announcement(dict(fresh), _now_iso(), owner_view=True)


@router.delete("/stations/{slug}/announcements/{ann_id}")
async def delete_announcement(slug: str, ann_id: str, request: Request,
                                 user: dict = Depends(current_user)):
    if not ID_RE.match(ann_id):
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "ann_id"})
    db = request.app.state.db
    await _resolve_owner_station(db, slug, user)
    r = await db.station_announcements.delete_one(
        {"_id": ann_id, "station_slug": slug})
    if r.deleted_count == 0:
        raise HTTPException(404, {"code": "not_found"})
    _bust_caches(slug)
    return {"ok": True, "deleted": ann_id}


@router.post("/stations/{slug}/announcements/{ann_id}/image")
async def upload_announcement_image(slug: str, ann_id: str, request: Request,
                                        file: UploadFile = File(...),
                                        user: dict = Depends(current_user)):
    if not ID_RE.match(ann_id):
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "ann_id"})
    db = request.app.state.db
    s = await _resolve_owner_station(db, slug, user)
    a = await db.station_announcements.find_one({"_id": ann_id,
                                                     "station_slug": slug})
    if not a:
        raise HTTPException(404, {"code": "not_found"})

    raw = await file.read()
    if len(raw) > ANNOUNCEMENT_IMG_MAX_BYTES:
        raise HTTPException(413, {"code": "image_too_large",
                                    "max_bytes": ANNOUNCEMENT_IMG_MAX_BYTES})
    mime = (file.content_type or "").lower()
    if mime not in IMAGE_MIME_OK:
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "image",
                                    "message": "Image must be JPEG/PNG/WebP.",
                                    "received_mime": mime})

    ext = IMAGE_EXT_FROM_MIME[mime]
    real_key = f"station_announcements/{s['station_id']}/{ann_id}.{ext}"
    try:
        from services.object_storage import get_storage
        storage = get_storage()
        tmp_path = f"/tmp/{ann_id}.{ext}"
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
        log.error("[tv] announcement image upload failed: %s", e)
        raise HTTPException(500, {"code": "image_upload_failed"})

    await db.station_announcements.update_one(
        {"_id": ann_id},
        {"$set": {"image_url": signed_url,
                  "image_storage_key": real_key,
                  "updated_at": _now_iso()}})
    _bust_caches(slug)
    return {"ok": True, "image_url": signed_url}


# ----- best-effort now_playing -----------------------------------
def _slot_index(slot_seconds: int = 180) -> int:
    return int(time.time() // slot_seconds)


async def _pick_now_playing_track(db, station: dict) -> Optional[dict]:
    """Pick a deterministic-but-rotating track that fits the station's
    musical taste. Returns a normalized dict suitable for the TV
    payload, or None when nothing matches.
    """
    genres = station.get("allowed_genres") or []
    moods  = station.get("allowed_moods")  or []
    langs  = [lm.get("language") for lm in (station.get("language_mix") or [])
                if isinstance(lm, dict) and lm.get("language")]

    q: dict = {"playable_status": "ok"}
    or_filters = []
    if genres:
        or_filters.append({"vibe_tags": {"$in": genres}})
    if moods:
        or_filters.append({"mood": {"$in": moods}})
    if langs:
        or_filters.append({"language": {"$in": langs}})
    if or_filters:
        q["$or"] = or_filters
    cursor = db.tracks.find(q, {"title": 1, "artist": 1,
                                  "duration_sec": 1, "mood": 1,
                                  "vibe_tags": 1, "language": 1})
    tracks = await cursor.to_list(500)
    if not tracks:
        # Fall back to ANY playable track so the kiosk isn't blank.
        cursor = db.tracks.find({"playable_status": "ok"},
                                  {"title": 1, "artist": 1,
                                   "duration_sec": 1, "mood": 1,
                                   "language": 1})
        tracks = await cursor.to_list(500)
    if not tracks:
        return None

    slot_secs = 180
    slot = _slot_index(slot_secs)
    t = tracks[slot % len(tracks)]
    started_at = int(slot * slot_secs)
    return {
        "track_id":   t.get("_id"),
        "title":      t.get("title"),
        "artist":     t.get("artist"),
        "duration_sec": float(t.get("duration_sec") or 0),
        "mood":       t.get("mood"),
        "language":   t.get("language"),
        "started_at": started_at,
        "slot_seconds": slot_secs,
        "cover_color":  station.get("cover_color"),
        "cover_image_url": station.get("cover_image_url"),
    }


def _redact_business_profile_for_public(bp: dict, verified: bool) -> dict:
    """For the TV kiosk, mirror the by-slug redaction rules: hide
    `phone` until verified. (TV is unauth so we always treat the
    viewer as a listener.)"""
    if not bp:
        return {}
    if verified:
        return dict(bp)
    out = dict(bp)
    out["phone"] = None
    return out


# ----- TV public endpoint ----------------------------------------
@router.get("/tv/{slug}")
async def get_tv_state(slug: str, request: Request):
    """Compact kiosk-display state. Public. 403 on private/unlisted.

    Cache window: 8s. On cache hit we still recompute `now_playing`
    when the 3-minute slot has advanced so we don't serve a stale
    track for up to 10s after a slot boundary.
    """
    db = request.app.state.db
    now_ts = time.time()
    now_iso = _now_iso()
    cached = _TV_CACHE.get(slug)
    if cached and cached["expires_at"] > now_ts \
            and cached["slot"] == _slot_index():
        return cached["value"]

    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if s.get("status") != "published":
        raise HTTPException(404, {"code": "not_found"})
    if s.get("privacy") and s["privacy"] != "public":
        raise HTTPException(403, {"code": "private_station",
                                    "message": "Station is private."})

    page_type = s.get("page_type") or "personal_radio"
    is_business = page_type == "business_radio"
    bp = s.get("business_profile") or {}
    verified = bool(bp.get("verified")) if is_business else True
    public_bp = (_redact_business_profile_for_public(bp, verified)
                  if is_business else None)

    # Top-3 active announcements (highest priority then newest).
    anns: list = []
    async for a in db.station_announcements.find(
            {"station_slug": slug}).sort([("priority", -1),
                                            ("created_at", -1)]):
        if _is_active(a, now_iso):
            anns.append(_strip_announcement(dict(a), now_iso))
        if len(anns) >= 3:
            break

    now_playing = await _pick_now_playing_track(db, s)

    qr_target = (f"{PUBLIC_FRONTEND_URL}/r/{slug}"
                  if PUBLIC_FRONTEND_URL else f"/r/{slug}")

    payload = {
        "station": {
            "slug":             s["slug"],
            "name":             s.get("name") or s["slug"],
            "tagline":          s.get("tagline"),
            "page_type":        page_type,
            "is_business":      is_business,
            "cover_color":      s.get("cover_color"),
            "cover_image_url":  s.get("cover_image_url"),
            "business_profile": public_bp,
            "pending_verification": (is_business and not verified),
        },
        "now_playing":     now_playing,
        "announcements":   anns,
        "qr_target_url":   qr_target,
        "refresh_after_sec": 10,
        "server_time":     now_iso,
    }
    _TV_CACHE[slug] = {"value": payload,
                       "expires_at": now_ts + _TV_TTL_SEC,
                       "slot": _slot_index()}
    # Phase 41 S5.A — fire-and-forget bump of the daily TV-poll counter
    # so analytics can show the kiosk's reach over time.
    try:
        date_str = _now().strftime("%Y-%m-%d")
        await db.tv_poll_daily.update_one(
            {"_id": f"tvp_{slug}_{date_str}"},
            {"$inc": {"count": 1},
             "$setOnInsert": {"station_slug": slug,
                                "station_id":   s.get("station_id"),
                                "date_str":     date_str}},
            upsert=True)
    except Exception as e:
        log.debug("[tv] tv_poll_daily bump failed: %s", e)
    return payload


# ----- index bootstrap -------------------------------------------
async def ensure_announcement_indexes(db) -> dict:
    """Idempotent. Called from server boot."""
    created = []
    try:
        await db.station_announcements.create_index(
            [("station_slug", 1), ("priority", -1), ("created_at", -1)],
            name="ann_station_priority_created")
        created.append("ann_station_priority_created")
    except Exception as e:
        log.warning("[tv] ensure_announcement_indexes failed: %s", e)
    return {"created": created}
