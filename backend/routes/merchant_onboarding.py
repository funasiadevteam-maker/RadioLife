"""Phase SC.2 — Merchant self-service onboarding.

Endpoints:
    POST      /api/merchant/apply                                        — begin wizard (login-required)
    GET        /api/merchant/{id}                                            — full profile + Stripe + locations
    PUT        /api/merchant/{id}/profile                              — description, phone, website
    POST      /api/merchant/{id}/locations                        — add a location
    GET        /api/merchant/{id}/locations                        — list locations
    DELETE  /api/merchant/{id}/locations/{loc_id}       — remove a location
    POST      /api/merchant/{id}/logo                                  — multipart upload logo (Tigris)
    POST      /api/merchant/{id}/photos                              — multipart upload photos (max 6)
    DELETE  /api/merchant/{id}/photos/{index}              — remove one photo
    PUT        /api/merchant/{id}/hours                                — 7-day schedule
    POST      /api/merchant/{id}/accept-terms                — commission-terms acknowledgement
    POST      /api/merchant/{id}/submit-for-approval    — flip merchant_status→submitted
    GET        /api/business-categories                                — public: 16 seeded categories
    GET        /api/merchant/mine                                          — current user's merchant docs

All merchant-owner endpoints resolve the actor via `current_user` and require
`biz.owner_user_id == user.user_id` OR admin.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                                UploadFile)
from pydantic import BaseModel, Field, HttpUrl

from auth import current_user
from services.object_storage import get_storage
from services.merchant_status_service import (WIZARD_STEPS,
    derive_effective_status, is_ready_for_submission, next_step, step_index)

logger = logging.getLogger("bigfm.merchant_onboarding")

router = APIRouter(prefix="/api", tags=["merchant_onboarding"])


# ─── Constants ─────────────────────────────────────────────────────
LOGO_MAX_BYTES     = 3 * 1024 * 1024      # 3 MB
PHOTO_MAX_BYTES  = 5 * 1024 * 1024      # 5 MB
MAX_PHOTOS          = 6
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/jpg"}

_SLUG_RX = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    s = _SLUG_RX.sub("-", name.lower()).strip("-")
    return s[:60] or f"merchant-{uuid.uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Auth resolver ─────────────────────────────────────────────────
async def _resolve_merchant(db, merchant_id: str, user: dict,
                                          require_owner: bool = True) -> dict:
    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        biz = await db.businesses.find_one({"_id": merchant_id})
    if not biz:
        raise HTTPException(404, "merchant_not_found")
    is_admin = (user.get("role") == "admin"
                    or bool(user.get("is_admin", False)))
    if require_owner and not is_admin \
              and biz.get("owner_user_id") != user["user_id"]:
        raise HTTPException(403, "not_merchant_owner_or_admin")
    return biz


def _biz_id(biz: dict) -> str:
    return biz.get("business_id") or biz.get("_id") or ""


def _biz_filter(biz: dict) -> dict:
    if biz.get("business_id"):
        return {"business_id": biz["business_id"]}
    return {"_id": biz["_id"]}


# ─── Bodies ────────────────────────────────────────────────────────
class ApplyBody(BaseModel):
    name:          str = Field(min_length=2, max_length=120)
    category_id: str = Field(min_length=2, max_length=40)


class ProfileBody(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    phone:        Optional[str] = Field(default=None, max_length=32)
    website:      Optional[str] = Field(default=None, max_length=200)


class LocationBody(BaseModel):
    name:                  Optional[str] = Field(default=None, max_length=120)
    address:              str = Field(min_length=3, max_length=300)
    city:                    Optional[str] = Field(default=None, max_length=80)
    country:              Optional[str] = Field(default=None, max_length=80)
    latitude:            Optional[float] = None
    longitude:          Optional[float] = None
    google_place_id: Optional[str] = Field(default=None, max_length=120)
    phone:                Optional[str] = Field(default=None, max_length=32)
    primary:              Optional[bool] = None


class DayHours(BaseModel):
    open:      Optional[str] = None       # "09:00" or None if closed
    close:    Optional[str] = None
    closed: bool = False


class HoursBody(BaseModel):
    monday:      DayHours
    tuesday:    DayHours
    wednesday: DayHours
    thursday:  DayHours
    friday:      DayHours
    saturday:  DayHours
    sunday:      DayHours


# ─── Serialisers ───────────────────────────────────────────────────
def _location_view(loc: dict) -> dict:
    return {
        "location_id":       loc.get("location_id"),
        "merchant_id":     loc.get("merchant_id"),
        "name":                  loc.get("name"),
        "address":              loc.get("address"),
        "city":                    loc.get("city"),
        "country":              loc.get("country"),
        "latitude":            loc.get("latitude"),
        "longitude":          loc.get("longitude"),
        "google_place_id": loc.get("google_place_id"),
        "phone":                loc.get("phone"),
        "primary":              bool(loc.get("primary", False)),
        "active":                bool(loc.get("active", True)),
        "created_at":        loc.get("created_at").isoformat()
                                        if hasattr(loc.get("created_at"), "isoformat")
                                        else loc.get("created_at"),
    }


async def _merchant_view(db, biz: dict) -> dict:
    mid = _biz_id(biz)
    locs = await db.merchant_locations.find(
        {"merchant_id": mid, "active": True}
    ).to_list(50)
    # Mark presence of a primary location — used by step helpers
    biz = {**biz, "_has_primary_location":
                    any(l.get("primary") for l in locs) if locs else False}
    ns = next_step(biz)
    ready, missing = is_ready_for_submission(biz)
    submitted_at = biz.get("submitted_at")
    approved_at  = biz.get("approved_at")
    rejected_at  = biz.get("rejected_at")

    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else v

    return {
        "merchant_id":                  mid,
        "business_id":                  biz.get("business_id"),
        "owner_user_id":              biz.get("owner_user_id"),
        "name":                              biz.get("name"),
        "slug":                              biz.get("slug"),
        "category_id":                  biz.get("category_id"),
        "description":                  biz.get("description"),
        "phone":                            biz.get("phone"),
        "website":                          biz.get("website"),
        "logo_url":                        biz.get("logo_url"),
        "photos":                          biz.get("photos") or [],
        "hours":                            biz.get("hours"),
        "commission_terms_accepted": bool(biz.get("commission_terms_accepted")),
        "commission_terms_accepted_at":
            _iso(biz.get("commission_terms_accepted_at")),
        "merchant_status":                  biz.get("merchant_status") or "draft",
        "effective_status":                  derive_effective_status(biz),
        "stripe_account_id":              biz.get("stripe_account_id"),
        "stripe_onboarding_status":  biz.get("stripe_onboarding_status") or "not_started",
        "stripe_charges_enabled":      bool(biz.get("stripe_charges_enabled")),
        "stripe_payouts_enabled":      bool(biz.get("stripe_payouts_enabled")),
        "stripe_details_submitted":  bool(biz.get("stripe_details_submitted")),
        "onboarding_step":                  biz.get("onboarding_step") or step_index(ns),
        "next_step":                          ns,
        "wizard_steps":                      WIZARD_STEPS,
        "ready_for_submission":          ready,
        "missing_fields":                  missing,
        "submitted_at":              _iso(submitted_at),
        "approved_at":                _iso(approved_at),
        "approved_by":                biz.get("approved_by"),
        "rejected_at":                _iso(rejected_at),
        "rejection_reason":        biz.get("rejection_reason"),
        "locations":                    [_location_view(l) for l in locs],
    }


# ─── Public — categories list ─────────────────────────────────────
@router.get("/business-categories")
async def list_business_categories(request: Request):
    db = request.app.state.db
    cats = await db.business_categories.find(
        {"active": True}, {"_id": 0}
    ).sort("sort_order", 1).to_list(50)
    return {"items": cats, "count": len(cats)}


# ─── Merchant — apply / list / get ────────────────────────────────
@router.post("/merchant/apply")
async def merchant_apply(body: ApplyBody, request: Request,
                                            user: dict = Depends(current_user)):
    """Start a merchant application.  Idempotent for the (owner + name)
    combo — re-calling with an existing draft returns that draft."""
    db = request.app.state.db
    # Validate category exists
    cat = await db.business_categories.find_one(
        {"id": body.category_id, "active": True})
    if not cat:
        raise HTTPException(400, "invalid_category")

    # Reuse an existing draft for this owner+name if present
    existing = await db.businesses.find_one({
        "owner_user_id": user["user_id"],
        "name": body.name,
        "merchant_status": {"$in": ["draft", "stripe_onboarding_pending",
                                                        "verification_pending"]},
    })
    if existing:
        return await _merchant_view(db, existing)

    mid   = f"biz_{uuid.uuid4().hex[:14]}"
    slug  = _slugify(body.name)
    # Ensure slug is unique — append short suffix on collision
    if await db.businesses.find_one({"slug": slug}):
        slug = f"{slug}-{uuid.uuid4().hex[:5]}"

    now = _now()
    doc = {
        "_id":                                mid,
        "business_id":                    mid,
        "owner_user_id":              user["user_id"],
        "owner_email":                  user.get("email"),
        "name":                                body.name,
        "slug":                                slug,
        "category_id":                    body.category_id,
        "category":                          body.category_id,        # legacy field kept in sync
        "description":                    None,
        "phone":                              None,
        "website":                            None,
        "logo_url":                          None,
        "photos":                            [],
        "hours":                              None,
        "commission_terms_accepted":        False,
        "commission_terms_accepted_at": None,
        "merchant_status":                "draft",
        "onboarding_step":              1,
        "submitted_at":                  None,
        "approved_at":                    None,
        "approved_by":                    None,
        "rejected_at":                    None,
        "rejection_reason":            None,
        "suspended_at":                  None,
        "suspension_reason":          None,
        # SC.1 defaults (mirrors run_sc1_migration)
        "stripe_account_id":                                    None,
        "stripe_charges_enabled":                        False,
        "stripe_payouts_enabled":                      False,
        "stripe_details_submitted":                    False,
        "stripe_requirements_currently_due":  [],
        "stripe_requirements_past_due":              [],
        "stripe_requirements_disabled_reason": None,
        "stripe_capabilities":                              None,
        "stripe_onboarding_status":                  "not_started",
        "stripe_status_synced_at":                    None,
        "created_at":                                              now,
        "updated_at":                                              now,
        "source":                                                    "self_service",
    }
    await db.businesses.insert_one(doc)
    logger.info(f"[merchant] apply created merchant_id={mid} "
                          f"owner={user['user_id']} name={body.name!r}")
    return await _merchant_view(db, doc)


@router.get("/merchant/mine")
async def merchant_mine(request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    cursor = db.businesses.find(
        {"owner_user_id": user["user_id"]}
    ).sort("created_at", -1).limit(50)
    items = []
    async for b in cursor:
        items.append(await _merchant_view(db, b))
    return {"items": items, "count": len(items)}


@router.get("/merchant/{merchant_id}")
async def merchant_get(merchant_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    return await _merchant_view(db, biz)


# ─── Profile ──────────────────────────────────────────────────────
@router.put("/merchant/{merchant_id}/profile")
async def merchant_profile(merchant_id: str, body: ProfileBody, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    update = {
        "description": body.description.strip(),
        "phone":            (body.phone or "").strip() or None,
        "website":        (body.website or "").strip() or None,
        "updated_at":  _now(),
    }
    # Advance onboarding_step to at least 2 (profile complete)
    biz_step = biz.get("onboarding_step") or 1
    if biz_step < 2:
        update["onboarding_step"] = 2
    await db.businesses.update_one(_biz_filter(biz), {"$set": update})
    biz.update(update)
    return await _merchant_view(db, biz)


# ─── Locations ────────────────────────────────────────────────────
@router.post("/merchant/{merchant_id}/locations")
async def merchant_add_location(merchant_id: str, body: LocationBody,
                                                        request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    mid = _biz_id(biz)

    existing_count = await db.merchant_locations.count_documents(
        {"merchant_id": mid, "active": True})
    if existing_count >= 20:
        raise HTTPException(400, "location_cap_reached")

    # First location is auto-marked primary; otherwise honour body.primary
    make_primary = body.primary if body.primary is not None else (existing_count == 0)
    if make_primary:
        await db.merchant_locations.update_many(
            {"merchant_id": mid}, {"$set": {"primary": False}})

    lid = f"loc_{uuid.uuid4().hex[:14]}"
    now = _now()
    doc = {
        "_id":                    lid,
        "location_id":      lid,
        "merchant_id":    mid,
        "name":                  (body.name or "").strip() or None,
        "address":            body.address.strip(),
        "city":                  (body.city or "").strip() or None,
        "country":            (body.country or "").strip() or None,
        "latitude":          body.latitude,
        "longitude":        body.longitude,
        "google_place_id": (body.google_place_id or "").strip() or None,
        "phone":                (body.phone or "").strip() or None,
        "primary":            bool(make_primary),
        "active":              True,
        "created_at":      now,
        "updated_at":      now,
    }
    await db.merchant_locations.insert_one(doc)
    # Bump step to at least 3 once we have a primary location
    if biz.get("onboarding_step", 0) < 3:
        await db.businesses.update_one(
            _biz_filter(biz),
            {"$set": {"onboarding_step": 3, "updated_at": now}})
    logger.info(f"[merchant] location added mid={mid} loc={lid} "
                          f"primary={make_primary}")
    return _location_view(doc)


@router.get("/merchant/{merchant_id}/locations")
async def merchant_list_locations(merchant_id: str, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    mid = _biz_id(biz)
    locs = await db.merchant_locations.find(
        {"merchant_id": mid, "active": True}
    ).sort("created_at", 1).to_list(50)
    return {"items": [_location_view(l) for l in locs], "count": len(locs)}


@router.delete("/merchant/{merchant_id}/locations/{location_id}")
async def merchant_delete_location(merchant_id: str, location_id: str,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    mid = _biz_id(biz)
    loc = await db.merchant_locations.find_one(
        {"location_id": location_id, "merchant_id": mid})
    if not loc:
        raise HTTPException(404, "location_not_found")
    await db.merchant_locations.update_one(
        {"location_id": location_id},
        {"$set": {"active": False, "deleted_at": _now(),
                    "primary": False}})
    # If this was the primary, promote the oldest remaining active loc
    if loc.get("primary"):
        promote = await db.merchant_locations.find_one(
            {"merchant_id": mid, "active": True},
            sort=[("created_at", 1)])
        if promote:
            await db.merchant_locations.update_one(
                {"location_id": promote["location_id"]},
                {"$set": {"primary": True}})
    return {"ok": True, "location_id": location_id}


# ─── Uploads ──────────────────────────────────────────────────────
def _guess_ext(filename: str, content_type: str) -> str:
    if filename:
        _, dot, ext = filename.rpartition(".")
        if dot and 2 <= len(ext) <= 5:
            return ext.lower()
    guess = mimetypes.guess_extension(content_type or "") or ".bin"
    return guess.lstrip(".").lower()


async def _spool_upload(upload: UploadFile, max_bytes: int) -> str:
    """Stream the upload to a temp file, enforcing the max-size cap.
    Returns the temp path (caller must delete)."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".upload")
    total = 0
    try:
        while True:
            chunk = await upload.read(1 << 15)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(413, "file_too_large")
            tmp.write(chunk)
    finally:
        tmp.close()
    return tmp.name


def _asset_key(mid: str, subpath: str) -> str:
    """Storage key layout — kept under `static/merchant_assets/` so the
    `/api/static/merchant_assets` mount + `TigrisFallbackStaticFiles`
    resolve it via the standard fallback CDN.  See server.py mount block."""
    return f"static/merchant_assets/{mid}/{subpath}"


def _tigris_public_url(key: str) -> str:
    """Return the browser-facing URL for a Tigris object stored under the
    `static/…` prefix.  The route strips the leading `static/` since the
    `/api/static/…` mount already scopes to that prefix."""
    if key.startswith("static/"):
        key = key[len("static/"):]
    return f"/api/static/{key}"


@router.post("/merchant/{merchant_id}/logo")
async def merchant_upload_logo(merchant_id: str, request: Request,
                                                      file: UploadFile = File(...),
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)

    ct = (file.content_type or "").lower()
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"unsupported_content_type:{ct}")

    tmp_path = await _spool_upload(file, LOGO_MAX_BYTES)
    try:
        ext  = _guess_ext(file.filename or "", ct) or "png"
        mid  = _biz_id(biz)
        key  = _asset_key(mid, f"logo.{ext}")
        storage = get_storage()
        storage.upload(local_path=tmp_path, key=key, content_type=ct)
    finally:
        try: os.unlink(tmp_path)
        except Exception: pass

    logo_url = _tigris_public_url(key)
    now = _now()
    update = {"logo_url": logo_url, "updated_at": now}
    if biz.get("onboarding_step", 0) < 4:
        update["onboarding_step"] = 4
    await db.businesses.update_one(_biz_filter(biz), {"$set": update})
    logger.info(f"[merchant] logo uploaded mid={mid} key={key} bytes={file.size or '?'}")
    return {"ok": True, "logo_url": logo_url, "key": key}


@router.post("/merchant/{merchant_id}/photos")
async def merchant_upload_photo(merchant_id: str, request: Request,
                                                        file: UploadFile = File(...),
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    photos = biz.get("photos") or []
    if len(photos) >= MAX_PHOTOS:
        raise HTTPException(400, f"photo_cap_reached:max={MAX_PHOTOS}")

    ct = (file.content_type or "").lower()
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"unsupported_content_type:{ct}")

    tmp_path = await _spool_upload(file, PHOTO_MAX_BYTES)
    try:
        ext  = _guess_ext(file.filename or "", ct) or "jpg"
        mid  = _biz_id(biz)
        pid  = f"ph_{uuid.uuid4().hex[:12]}"
        key  = _asset_key(mid, f"photos/{pid}.{ext}")
        storage = get_storage()
        storage.upload(local_path=tmp_path, key=key, content_type=ct)
    finally:
        try: os.unlink(tmp_path)
        except Exception: pass

    photo_url = _tigris_public_url(key)
    now = _now()
    photos.append({"key": key, "url": photo_url, "uploaded_at": now.isoformat()})
    update = {"photos": photos, "updated_at": now}
    if biz.get("onboarding_step", 0) < 5:
        update["onboarding_step"] = 5
    await db.businesses.update_one(_biz_filter(biz), {"$set": update})
    return {"ok": True, "photo_url": photo_url, "key": key,
              "photo_count": len(photos)}


@router.delete("/merchant/{merchant_id}/photos/{index}")
async def merchant_delete_photo(merchant_id: str, index: int, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    photos = list(biz.get("photos") or [])
    if index < 0 or index >= len(photos):
        raise HTTPException(404, "photo_not_found")
    removed = photos.pop(index)
    await db.businesses.update_one(
        _biz_filter(biz),
        {"$set": {"photos": photos, "updated_at": _now()}})
    # Best-effort object delete
    try:
        get_storage().delete(key=removed.get("key"))
    except Exception:
        pass
    return {"ok": True, "photo_count": len(photos)}


# ─── Hours & terms ────────────────────────────────────────────────
@router.put("/merchant/{merchant_id}/hours")
async def merchant_hours(merchant_id: str, body: HoursBody, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    hours = body.model_dump()
    now = _now()
    update = {"hours": hours, "updated_at": now}
    if biz.get("onboarding_step", 0) < 6:
        update["onboarding_step"] = 6
    await db.businesses.update_one(_biz_filter(biz), {"$set": update})
    return {"ok": True, "hours": hours}


@router.post("/merchant/{merchant_id}/accept-terms")
async def merchant_accept_terms(merchant_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    now = _now()
    update = {
        "commission_terms_accepted":         True,
        "commission_terms_accepted_at": now,
        "commission_terms_version":          "sc2_placeholder_v1",
        "updated_at":                                      now,
    }
    if biz.get("onboarding_step", 0) < 7:
        update["onboarding_step"] = 7
    await db.businesses.update_one(_biz_filter(biz), {"$set": update})
    return {"ok": True, "accepted_at": now.isoformat(),
              "version": "sc2_placeholder_v1"}


# ─── Submit-for-approval ──────────────────────────────────────────
@router.post("/merchant/{merchant_id}/submit-for-approval")
async def merchant_submit(merchant_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id, user)
    mid = _biz_id(biz)

    # Enrich with the has-primary-location flag before validating
    has_primary = await db.merchant_locations.find_one(
        {"merchant_id": mid, "active": True, "primary": True})
    biz["_has_primary_location"] = bool(has_primary)

    ready, missing = is_ready_for_submission(biz)
    if not ready:
        raise HTTPException(400, {"code": "incomplete_application",
                                                    "missing_fields": missing})
    if biz.get("merchant_status") == "submitted":
        # Idempotent — return the current state
        return await _merchant_view(db, biz)
    if biz.get("merchant_status") in ("approved", "active",
                                                            "restricted", "payouts_disabled"):
        raise HTTPException(400, "already_approved_or_activated")

    now = _now()
    await db.businesses.update_one(
        _biz_filter(biz),
        {"$set": {
            "merchant_status": "submitted",
            "submitted_at":      now,
            "onboarding_step": 9,
            "updated_at":          now,
        }})
    biz = await db.businesses.find_one(_biz_filter(biz))
    logger.info(f"[merchant] submitted mid={mid} owner={user['user_id']}")

    # Fire best-effort notification to admins (non-blocking on failure)
    try:
        from services.mailgun_client import send_email, is_live
        if is_live():
            admin_notify = os.environ.get("MERCHANT_ADMIN_NOTIFY_EMAIL",
                                                                  "admin@bigfm.dubai")
            send_email(
                to=admin_notify,
                subject=f"[BigFM] New merchant application: {biz.get('name')}",
                html=(f"<p>Merchant <b>{biz.get('name')}</b> "
                          f"(<code>{mid}</code>) was submitted for approval by "
                          f"<code>{user.get('email')}</code>.</p>"
                          f"<p>Review in the admin panel: /admin/merchants → Pending.</p>"),
                text=(f"Merchant {biz.get('name')} ({mid}) submitted by "
                          f"{user.get('email')}."),
                tags=["merchant_submitted"])
    except Exception:
        logger.exception("[merchant] admin notify failed (non-blocking)")

    return await _merchant_view(db, biz)


__all__ = ["router"]
