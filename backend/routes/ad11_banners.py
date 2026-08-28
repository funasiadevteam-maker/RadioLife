"""Phase AD.11 — Banner ads HTTP routes.

Advertiser-facing:
  POST   /api/advertiser/{advertiser_id}/banner-campaigns   (draft)
  PATCH  /api/advertiser/banner-campaigns/{banner_id}
  POST   /api/advertiser/banner-campaigns/{banner_id}/creative-upload
  POST   /api/advertiser/banner-campaigns/{banner_id}/publish
  GET    /api/advertiser/{advertiser_id}/banner-campaigns
  GET    /api/advertiser/{advertiser_id}/banner-analytics

Customer-facing (public):
  GET    /api/banner/serve?zone=<zone>
  POST   /api/banner/impression
  POST   /api/banner/click

Admin:
  GET    /api/admin/banner-campaigns/analytics
  PATCH  /api/admin/banner-campaigns/{banner_id}/pause
  PATCH  /api/admin/banner-campaigns/{banner_id}/resume
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, Depends, HTTPException, Request,
                                          UploadFile, File, Query)
from pydantic import BaseModel, Field

from auth import current_user
from services import ad11_banner_service as _svc
from services.commission_service import calculate_platform_fee
from services import ad_creative_review_service as _ad_review
from config.ad_pricing_hints import (
    BANNER_ZONES, BANNER_ZONE_CPM_CENTS, BANNER_ZONE_DIMENSIONS,
)

router = APIRouter(tags=["ad11-banner-ads"])
logger = logging.getLogger("bigfm.ad11.routes")

BANNER_STORAGE_ROOT = "/app/backend/static/banners"
BANNER_PUBLIC_PREFIX = "/api/static/banners"


# ─── RBAC helper ───────────────────────────────────────────────
async def _assert_advertiser_owner(db, advertiser_id: str, user: dict) -> dict:
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    if user.get("role") == "admin":
        return user
    adv = await db.advertisers_v2.find_one({"advertiser_id": advertiser_id})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    owner = adv.get("owner_user_id")
    staff = [s.get("user_id") for s in (adv.get("staff_users") or [])]
    if user.get("user_id") in ([owner] + staff):
        return user
    raise HTTPException(403, {"code": "advertiser_owner_only"})


# ─── Body models ────────────────────────────────────────────────
class BannerDraftBody(BaseModel):
    title:  str = Field(..., min_length=3, max_length=120)
    description: Optional[str] = Field(default="", max_length=500)
    target_url:  str = Field(..., min_length=4, max_length=1000)
    cta_text:      Optional[str] = Field(default="Learn more", max_length=64)
    sponsoring_merchant_id: Optional[str] = None
    placement_zones:            List[str]
    per_zone_cpm_cents:        Optional[Dict[str, int]] = None
    total_budget_cents:        int = Field(..., ge=100)
    daily_cap_cents:              Optional[int] = None
    country_codes:                Optional[List[str]] = None
    region:                              Optional[str] = None
    city:                                  Optional[str] = None
    language:                          Optional[str] = None
    category_tags:                Optional[List[str]] = None
    min_user_tier:                Optional[str] = None
    age_range:                          Optional[str] = None
    gender:                              Optional[str] = None


class BannerPatchBody(BaseModel):
    title:  Optional[str] = None
    description: Optional[str] = None
    target_url:  Optional[str] = None
    cta_text:      Optional[str] = None
    sponsoring_merchant_id: Optional[str] = None
    total_budget_cents:  Optional[int] = None
    daily_cap_cents:        Optional[int] = None
    placement_zones:        Optional[List[str]] = None
    per_zone_cpm_cents:  Optional[Dict[str, int]] = None
    targeting:                    Optional[Dict[str, Any]] = None


class ImpressionBody(BaseModel):
    banner_id:  str
    zone:        str
    session_id:  Optional[str] = None


class ClickBody(BaseModel):
    banner_id:  str
    zone:        str
    session_id:  Optional[str] = None


# ─── Advertiser CRUD ────────────────────────────────────────────
@router.post("/api/advertiser/{advertiser_id}/banner-campaigns",
                          description="Create a draft banner campaign.")
async def create_campaign(advertiser_id: str, body: BannerDraftBody,
                                                          request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    if await _ad_review.is_advertiser_blocked(db, advertiser_id):
        raise HTTPException(403, {"code": "advertiser_blocked"})
    try:
        doc = await _svc.create_banner_campaign(
            db, advertiser_id=advertiser_id,
            user_id=user.get("user_id"),
            payload=body.model_dump())
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    return doc


@router.patch("/api/advertiser/banner-campaigns/{banner_id}",
                            description="Edit a draft/rejected banner campaign.")
async def patch_campaign(banner_id: str, body: BannerPatchBody,
                                                        request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not existing:
        raise HTTPException(404, {"code": "banner_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    try:
        doc = await _svc.update_banner_campaign(
            db, banner_id=banner_id, patch=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    if not doc:
        raise HTTPException(404, {"code": "banner_not_found"})
    return doc


@router.post("/api/advertiser/banner-campaigns/{banner_id}/creative-upload",
                          description=("Upload a creative image for a specific zone.  "
                                                        "Multipart form: `file` (image) + `zone` (form field).  "
                                                        "Accepts PNG/JPG/WEBP up to 3MB."))
async def creative_upload(banner_id: str,
                                                        request: Request,
                                                        file: UploadFile = File(...),
                                                        zone: str = Query(...),
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not existing:
        raise HTTPException(404, {"code": "banner_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    if zone not in BANNER_ZONES:
        raise HTTPException(400, {"code": f"invalid_zone:{zone}"})
    if zone not in (existing.get("placement_zones") or []):
        raise HTTPException(400, {"code": "zone_not_in_placement"})
    if file.content_type not in ("image/png", "image/jpeg",
                                                                    "image/webp"):
        raise HTTPException(400, {"code": "unsupported_content_type"})
    data = await file.read()
    if len(data) > 3 * 1024 * 1024:
        raise HTTPException(400, {"code": "file_too_large"})
    # Persist to /app/backend/static/banners/{banner_id}/{zone}.<ext>
    dir_path = os.path.join(BANNER_STORAGE_ROOT, banner_id)
    os.makedirs(dir_path, exist_ok=True)
    ext = "png"
    if file.content_type == "image/jpeg":
        ext = "jpg"
    elif file.content_type == "image/webp":
        ext = "webp"
    fname = f"{zone}.{ext}"
    fpath = os.path.join(dir_path, fname)
    with open(fpath, "wb") as f:
        f.write(data)
    try:
        from services.object_storage import get_storage as _get_storage
        _get_storage().upload_bytes(
            key=f"banners/{banner_id}/{fname}", data=data,
            content_type=file.content_type)
    except Exception:
        pass
    creative_url = f"{BANNER_PUBLIC_PREFIX}/{banner_id}/{fname}"
    try:
        doc = await _svc.attach_creative(
            db, banner_id=banner_id, zone=zone, creative_url=creative_url)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    return {"ok": True, "zone": zone, "creative_url": creative_url,
                  "banner": doc}


@router.post("/api/advertiser/banner-campaigns/{banner_id}/publish")
async def publish_campaign(banner_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not existing:
        raise HTTPException(404, {"code": "banner_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    if await _ad_review.is_advertiser_blocked(db, existing["advertiser_id"]):
        raise HTTPException(403, {"code": "advertiser_blocked"})
    try:
        doc = await _svc.publish_banner_campaign(db, banner_id=banner_id)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    # Mint an ADMOD.1 review row.
    try:
        await _ad_review.create_review(
            db, ad_type="banner", target_id=banner_id,
            advertiser_id=existing["advertiser_id"],
            submitted_by=user.get("user_id"))
    except Exception as e:
        logger.warning("[ad11-publish] review row failed: %s", e)
    return doc


@router.get("/api/advertiser/{advertiser_id}/banner-campaigns")
async def list_campaigns(advertiser_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _svc.list_banner_campaigns(db, advertiser_id=advertiser_id)


@router.get("/api/advertiser/{advertiser_id}/banner-analytics")
async def advertiser_banner_rollup(advertiser_id: str, request: Request,
                                                                                        days: int = Query(30, ge=1, le=180),
                                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _svc.advertiser_rollup(db, advertiser_id=advertiser_id,
                                                                                    days=days)


# ─── Customer-facing (public) ──────────────────────────────────
@router.get("/api/banner/serve",
                        description="Auction one live banner for the requested zone.")
async def serve(request: Request,
                            zone: str = Query(...),
                            country: Optional[str] = None,
                            language: Optional[str] = None,
                            category_tag: Optional[str] = None,
                            session_id: Optional[str] = None):
    db = request.app.state.db
    if zone not in BANNER_ZONES:
        raise HTTPException(400, {"code": f"invalid_zone:{zone}"})
    out = await _svc.serve_banner(
        db, zone=zone, country=country, language=language,
        category_tags=[category_tag] if category_tag else None,
        session_id=session_id)
    if not out:
        return {"banner": None, "zone": zone}
    return {"banner": out, "zone": zone}


async def _fee_calc(db, *, business_category, transaction_type, gross_cents):
    return await calculate_platform_fee(
        db, business_category=business_category,
        transaction_type=transaction_type, gross_cents=gross_cents)


@router.post("/api/banner/impression",
                          description="Called from IntersectionObserver on visible banner slots.")
async def impression(body: ImpressionBody, request: Request):
    db = request.app.state.db
    sid = body.session_id or f"anon_{uuid.uuid4().hex[:12]}"
    # Try to attach user_id if logged in (best-effort — no hard auth).
    user_id: Optional[str] = None
    try:
        cookie = request.cookies.get("session")
        if cookie:
            from auth import current_user_optional
            u = await current_user_optional(request)   # type: ignore
            if u:
                user_id = u.get("user_id")
    except Exception:
        pass
    res = await _svc.record_impression(
        db, banner_id=body.banner_id, zone=body.zone,
        user_id=user_id, session_id=sid,
        commission_service_calc=_fee_calc)
    return res


@router.post("/api/banner/click")
async def click(body: ClickBody, request: Request):
    db = request.app.state.db
    sid = body.session_id or f"anon_{uuid.uuid4().hex[:12]}"
    return await _svc.record_click(
        db, banner_id=body.banner_id, zone=body.zone,
        user_id=None, session_id=sid)


# ─── Admin ──────────────────────────────────────────────────────
def _require_ad_manager(user: dict) -> None:
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "ad_manager_or_admin_required"})


@router.get("/api/admin/banner-campaigns/analytics")
async def admin_banner_analytics(request: Request,
                                                                            days: int = Query(30, ge=1, le=180),
                                                                            user: dict = Depends(current_user)):
    _require_ad_manager(user)
    return await _svc.platform_analytics(request.app.state.db, days=days)


@router.patch("/api/admin/banner-campaigns/{banner_id}/pause")
async def admin_pause(banner_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    _require_ad_manager(user)
    db = request.app.state.db
    r = await db.banner_campaigns.update_one(
        {"banner_id": banner_id},
        {"$set": {"status": "paused",
                          "auto_paused_reason": "admin_pause",
                          "auto_paused_at": _svc._now(),
                          "updated_at": _svc._now()}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "banner_not_found"})
    return {"ok": True, "banner_id": banner_id, "status": "paused"}


@router.patch("/api/admin/banner-campaigns/{banner_id}/resume")
async def admin_resume(banner_id: str, request: Request,
                                                user: dict = Depends(current_user)):
    _require_ad_manager(user)
    db = request.app.state.db
    r = await db.banner_campaigns.update_one(
        {"banner_id": banner_id, "status": "paused"},
        {"$set": {"status": "live",
                          "auto_paused_reason": None,
                          "auto_paused_at": None,
                          "updated_at": _svc._now()}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "banner_not_paused_or_missing"})
    return {"ok": True, "banner_id": banner_id, "status": "live"}


__all__ = ["router"]
