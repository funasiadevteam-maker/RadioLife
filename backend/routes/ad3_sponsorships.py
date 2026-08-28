"""Phase AD.3 — Advertiser Predict & Win Sponsorship HTTP routes.

8 endpoints: browse available parents, CRUD sponsorships (draft →
publish → ADMOD.1), admin approve/pause, customer-facing
active-sponsor auction + impression billing, and analytics.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import (APIRouter, Depends, HTTPException, Request,
                                          UploadFile, File, Query)
from pydantic import BaseModel, Field

from auth import current_user
from services import ad3_sponsorship_service as _svc
from services import ad_creative_review_service as _ad_review

router = APIRouter(tags=["ad3-predict-win-sponsorship"])
logger = logging.getLogger("bigfm.ad3.routes")


ASSET_STORAGE_ROOT      = "/app/backend/static/pw_sponsorships"
ASSET_PUBLIC_PREFIX    = "/api/static/pw_sponsorships"


class SponsorshipCreateBody(BaseModel):
    parent_campaign_id:      str
    brand_name:                          str = Field(..., min_length=2, max_length=80)
    tagline:                                Optional[str] = None
    brand_asset_url:                Optional[str] = None
    pricing_model:                    str = "per_entry"
    cpe_cents:                              Optional[int] = None
    cpi_cents:                              Optional[int] = None
    budget_cents:                        int = Field(..., ge=100)
    daily_cap_cents:                Optional[int] = None
    targeting_json:                  Optional[Dict[str, Any]] = None
    start_time:                            Optional[str] = None
    end_time:                                Optional[str] = None


class SponsorshipPatchBody(BaseModel):
    brand_name:                          Optional[str] = None
    tagline:                                Optional[str] = None
    brand_asset_url:                Optional[str] = None
    pricing_model:                    Optional[str] = None
    cpe_cents:                              Optional[int] = None
    cpi_cents:                              Optional[int] = None
    budget_cents:                        Optional[int] = None
    daily_cap_cents:                Optional[int] = None
    targeting_json:                  Optional[Dict[str, Any]] = None
    start_time:                            Optional[str] = None
    end_time:                                Optional[str] = None


class ImpressionBody(BaseModel):
    sponsorship_id:              str
    parent_campaign_id:      str
    event_type:                        str


# ─── Advertiser RBAC (same shape as AD.11/AD.12) ─────────────────
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


# ─── Available parents ──────────────────────────────────────────
@router.get("/api/advertiser/predict-win/available-campaigns")
async def available_parents(request: Request,
                                                            limit: int = Query(50, ge=1, le=200)):
    return await _svc.available_parent_campaigns(
        request.app.state.db, limit=limit)


# ─── CRUD ───────────────────────────────────────────────────────
@router.post("/api/advertiser/{advertiser_id}/predict-win/sponsorships")
async def create_sponsorship(advertiser_id: str,
                                                            body: SponsorshipCreateBody,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    if await _ad_review.is_advertiser_blocked(db, advertiser_id):
        raise HTTPException(403, {"code": "advertiser_blocked"})
    try:
        return await _svc.create_sponsorship(
            db, advertiser_id=advertiser_id,
            submitted_by=user["user_id"],
            payload=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.patch("/api/advertiser/predict-win/sponsorships/{sponsorship_id}")
async def patch_sponsorship(sponsorship_id: str,
                                                            body: SponsorshipPatchBody,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    doc = await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id})
    if not doc:
        raise HTTPException(404, {"code": "sponsorship_not_found"})
    await _assert_advertiser_owner(db, doc["advertiser_id"], user)
    try:
        updated = await _svc.update_sponsorship(
            db, sponsorship_id=sponsorship_id,
            patch=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    if not updated:
        raise HTTPException(404, {"code": "sponsorship_not_found"})
    return updated


@router.post("/api/advertiser/predict-win/sponsorships/{sponsorship_id}/brand-asset")
async def upload_brand_asset(sponsorship_id: str, request: Request,
                                                              file: UploadFile = File(...),
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    doc = await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id})
    if not doc:
        raise HTTPException(404, {"code": "sponsorship_not_found"})
    await _assert_advertiser_owner(db, doc["advertiser_id"], user)
    if file.content_type not in ("image/png", "image/jpeg",
                                                                    "image/webp"):
        raise HTTPException(400, {"code": "unsupported_content_type"})
    data = await file.read()
    if len(data) > 1024 * 1024:
        raise HTTPException(400, {"code": "file_too_large"})
    dir_path = os.path.join(ASSET_STORAGE_ROOT, sponsorship_id)
    os.makedirs(dir_path, exist_ok=True)
    ext = "png"
    if file.content_type == "image/jpeg":  ext = "jpg"
    elif file.content_type == "image/webp": ext = "webp"
    fname = f"brand.{ext}"
    fpath = os.path.join(dir_path, fname)
    with open(fpath, "wb") as f:
        f.write(data)
    try:
        from services.object_storage import get_storage as _get_storage
        _get_storage().upload_bytes(
            key=f"static/pw_sponsorships/{sponsorship_id}/{fname}", data=data,
            content_type=file.content_type)
    except Exception:
        pass
    creative_url = f"{ASSET_PUBLIC_PREFIX}/{sponsorship_id}/{fname}"
    await db.predict_win_sponsorships.update_one(
        {"sponsorship_id": sponsorship_id},
        {"$set": {"brand_asset_url": creative_url, "updated_at": _svc._now()}})
    return {"ok": True, "brand_asset_url": creative_url}


@router.post("/api/advertiser/predict-win/sponsorships/{sponsorship_id}/publish")
async def publish_sponsorship(sponsorship_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    doc = await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id})
    if not doc:
        raise HTTPException(404, {"code": "sponsorship_not_found"})
    await _assert_advertiser_owner(db, doc["advertiser_id"], user)
    if await _ad_review.is_advertiser_blocked(db, doc["advertiser_id"]):
        raise HTTPException(403, {"code": "advertiser_blocked"})
    try:
        updated = await _svc.publish_sponsorship(
            db, sponsorship_id=sponsorship_id)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    # Mint ADMOD.1 review row.
    try:
        await _ad_review.create_review(
            db, ad_type="advertiser_pw_sponsorship",
            target_id=sponsorship_id,
            advertiser_id=doc["advertiser_id"],
            submitted_by=user["user_id"])
    except Exception as e:
        logger.warning("[ad3] review-row create failed: %s", e)
    return updated


@router.get("/api/advertiser/{advertiser_id}/predict-win-sponsorships")
async def list_advertiser_sponsorships(advertiser_id: str,
                                                                                          request: Request,
                                                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _svc.list_advertiser_sponsorships(
        db, advertiser_id=advertiser_id)


@router.get("/api/advertiser/{advertiser_id}/predict-win-sponsorships/analytics")
async def analytics(advertiser_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _svc.advertiser_analytics(
        db, advertiser_id=advertiser_id)


# ─── Admin control ─────────────────────────────────────────────
@router.patch("/api/admin/predict-win/sponsorships/{sponsorship_id}/status")
async def admin_set_status(sponsorship_id: str, request: Request,
                                                        new_status: str = Query(...),
                                                        user: dict = Depends(current_user)):
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "admin_required"})
    try:
        return await _svc.admin_set_status(
            request.app.state.db, sponsorship_id=sponsorship_id,
            new_status=new_status)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


# ─── Customer-facing: pick active sponsor + fire impression ────
@router.get("/api/predict-win/{parent_campaign_id}/active-sponsorship")
async def active_sponsor(parent_campaign_id: str, request: Request,
                                                    user: Optional[dict] = Depends(current_user)):
    db = request.app.state.db
    result = await _svc.active_sponsorship_for_parent(
        db, parent_campaign_id=parent_campaign_id, user=user)
    if not result:
        return {"sponsorship": None}
    return {"sponsorship": result}


@router.post("/api/predict-win/sponsorships/impression")
async def fire_impression(body: ImpressionBody, request: Request,
                                                    user: Optional[dict] = Depends(current_user)):
    db = request.app.state.db
    try:
        return await _svc.record_event(
            db, sponsorship_id=body.sponsorship_id,
            event_type=body.event_type,
            parent_campaign_id=body.parent_campaign_id,
            user_id=(user or {}).get("user_id"))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


__all__ = ["router"]
