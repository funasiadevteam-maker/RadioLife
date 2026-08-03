"""Phase AD.12a — In-app notification ads HTTP routes.

Advertiser CRUD + user inbox + delivery lifecycle + analytics.
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
from services import ad12_notification_service as _svc
from services import ad_creative_review_service as _ad_review
from services.commission_service import calculate_platform_fee

router = APIRouter(tags=["ad12-notifications"])
logger = logging.getLogger("bigfm.ad12.routes")


NOTIF_STORAGE_ROOT      = "/app/backend/static/notifications"
NOTIF_PUBLIC_PREFIX    = "/api/static/notifications"


# ─── Body models ────────────────────────────────────────────────
class TargetingModel(BaseModel):
    region:                Optional[str] = None
    city:                    Optional[str] = None
    country_codes:  Optional[List[str]] = None
    language:            Optional[str] = None
    category_tags:  Optional[List[str]] = None
    min_user_tier:  Optional[str] = None
    exclude_recent_notified_within_hours: Optional[int] = 24


class NotificationDraftBody(BaseModel):
    title:                                              str = Field(..., min_length=3, max_length=120)
    body:                                                str = Field(..., min_length=5, max_length=500)
    cta_text:                                        Optional[str] = Field(default="Learn more", max_length=64)
    target_url:                                    str = Field(..., min_length=4, max_length=1000)
    sponsoring_merchant_id:              Optional[str] = None
    channel:                                        Optional[str] = "in_app"
    delivery_schedule:                    Optional[str] = "immediate"
    scheduled_at:                                Optional[str] = None
    trigger_type:                                Optional[str] = None
    targeting:                                    Optional[TargetingModel] = None
    budget_cents:                                int = Field(..., ge=100)
    cost_per_delivery_cents:            int = Field(..., ge=1, le=100000)
    max_deliveries:                            Optional[int] = None
    start_time:                                    Optional[str] = None
    end_time:                                        Optional[str] = None


class NotificationPatchBody(BaseModel):
    title:                                              Optional[str] = None
    body:                                                Optional[str] = None
    cta_text:                                        Optional[str] = None
    target_url:                                    Optional[str] = None
    sponsoring_merchant_id:              Optional[str] = None
    channel:                                        Optional[str] = None
    delivery_schedule:                    Optional[str] = None
    scheduled_at:                                Optional[str] = None
    trigger_type:                                Optional[str] = None
    targeting:                                    Optional[Dict[str, Any]] = None
    budget_cents:                                Optional[int] = None
    cost_per_delivery_cents:            Optional[int] = None
    max_deliveries:                            Optional[int] = None
    start_time:                                    Optional[str] = None
    end_time:                                        Optional[str] = None


# ─── RBAC helper (mirrors AD.11) ───────────────────────────────
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


# ─── Advertiser CRUD ────────────────────────────────────────────
@router.post("/api/advertiser/{advertiser_id}/notification-campaigns",
                          description="Create a draft notification-ad campaign.")
async def create_campaign(advertiser_id: str,
                                                      body: NotificationDraftBody,
                                                      request: Request,
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    if await _ad_review.is_advertiser_blocked(db, advertiser_id):
        raise HTTPException(403, {"code": "advertiser_blocked"})
    try:
        doc = await _svc.create_notification_campaign(
            db, advertiser_id=advertiser_id,
            user_id=user.get("user_id"),
            payload=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    return doc


@router.patch("/api/advertiser/notification-campaigns/{notification_campaign_id}",
                            description="Edit a draft/rejected/requires_changes campaign.")
async def patch_campaign(notification_campaign_id: str,
                                                      body: NotificationPatchBody,
                                                      request: Request,
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    if not existing:
        raise HTTPException(404, {"code": "notification_campaign_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    try:
        doc = await _svc.update_notification_campaign(
            db, notification_campaign_id=notification_campaign_id,
            patch=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    if not doc:
        raise HTTPException(404, {"code": "notification_campaign_not_found"})
    return doc


@router.post("/api/advertiser/notification-campaigns/{notification_campaign_id}/creative-upload",
                          description=("Upload icon (slot='icon') or image (slot='image') for "
                                                        "the notification.  Accepts PNG/JPG/WEBP, ≤512KB for icon, "
                                                        "≤1MB for image."))
async def creative_upload(notification_campaign_id: str,
                                                      request: Request,
                                                      file: UploadFile = File(...),
                                                      slot: str = Query("icon"),
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    if not existing:
        raise HTTPException(404, {"code": "notification_campaign_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    if slot not in ("icon", "image"):
        raise HTTPException(400, {"code": f"invalid_slot:{slot}"})
    if file.content_type not in ("image/png", "image/jpeg",
                                                                    "image/webp"):
        raise HTTPException(400, {"code": "unsupported_content_type"})
    data = await file.read()
    limit = 512 * 1024 if slot == "icon" else 1024 * 1024
    if len(data) > limit:
        raise HTTPException(400, {"code": "file_too_large"})
    dir_path = os.path.join(NOTIF_STORAGE_ROOT, notification_campaign_id)
    os.makedirs(dir_path, exist_ok=True)
    ext = "png"
    if file.content_type == "image/jpeg":
        ext = "jpg"
    elif file.content_type == "image/webp":
        ext = "webp"
    fname = f"{slot}.{ext}"
    fpath = os.path.join(dir_path, fname)
    with open(fpath, "wb") as f:
        f.write(data)
    creative_url = f"{NOTIF_PUBLIC_PREFIX}/{notification_campaign_id}/{fname}"
    doc = await _svc.attach_creative(
        db,
        notification_campaign_id=notification_campaign_id,
        slot=f"{slot}_url", url=creative_url)
    return {"ok": True, "slot": slot, "creative_url": creative_url,
                  "notification_campaign": doc}


@router.post(
    "/api/advertiser/notification-campaigns/{notification_campaign_id}/publish",
    description="Publish → pending_admin → ADMOD.1 review row minted.")
async def publish_campaign(notification_campaign_id: str,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    if not existing:
        raise HTTPException(404, {"code": "notification_campaign_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    if await _ad_review.is_advertiser_blocked(db, existing["advertiser_id"]):
        raise HTTPException(403, {"code": "advertiser_blocked"})
    try:
        doc = await _svc.publish_notification_campaign(
            db, notification_campaign_id=notification_campaign_id)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    try:
        await _ad_review.create_review(
            db, ad_type="notification",
            target_id=notification_campaign_id,
            advertiser_id=existing["advertiser_id"],
            submitted_by=user.get("user_id"))
    except Exception as e:
        logger.warning("[ad12-publish] review row failed: %s", e)
    return doc


@router.get("/api/advertiser/{advertiser_id}/notification-campaigns")
async def list_campaigns(advertiser_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _svc.list_advertiser_campaigns(
        db, advertiser_id=advertiser_id)


@router.get("/api/advertiser/{advertiser_id}/notification-campaigns/analytics")
async def advertiser_analytics(advertiser_id: str, request: Request,
                                                                    days: int = Query(30, ge=1, le=180),
                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _svc.advertiser_notification_analytics(
        db, advertiser_id=advertiser_id, days=days)


# ─── User inbox + delivery lifecycle ────────────────────────────
async def _fee_calc(db, *, business_category, transaction_type,
                                        gross_cents):
    return await calculate_platform_fee(
        db, business_category=business_category,
        transaction_type=transaction_type, gross_cents=gross_cents)


@router.get("/api/user/notifications/inbox",
                        description="Merged inbox (system + sponsored). Mints new "
                                                    "deliveries + fires billing on first eligible view.")
async def inbox(request: Request,
                            limit: int = Query(20, ge=1, le=50),
                            unread_only: bool = False,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    return await _svc.build_inbox(
        db, user=user, limit=limit, unread_only=unread_only,
        commission_service_calc=_fee_calc)


@router.get("/api/user/notifications/unread_count",
                        description="Fast count of unread items in the merged inbox.")
async def unread_count_endpoint(request: Request,
                                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await _svc.unread_count(db, user_id=user["user_id"])
    return {"count": c}


@router.post("/api/user/notifications/{delivery_id}/open")
async def open_delivery(delivery_id: str, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    return await _svc.mark_opened(
        db, delivery_id=delivery_id, user_id=user["user_id"])


@router.post("/api/user/notifications/{delivery_id}/click")
async def click_delivery(delivery_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    return await _svc.mark_clicked(
        db, delivery_id=delivery_id, user_id=user["user_id"])


@router.post("/api/user/notifications/{delivery_id}/dismiss")
async def dismiss_delivery(delivery_id: str, request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    return await _svc.mark_dismissed(
        db, delivery_id=delivery_id, user_id=user["user_id"])


# ─── Admin controls ─────────────────────────────────────────────
def _require_ad_manager(user: dict) -> None:
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "ad_manager_or_admin_required"})


@router.patch("/api/admin/notification-campaigns/{notification_campaign_id}/pause")
async def admin_pause(notification_campaign_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    _require_ad_manager(user)
    db = request.app.state.db
    r = await db.notification_campaigns.update_one(
        {"notification_campaign_id": notification_campaign_id},
        {"$set": {"status": "paused",
                          "auto_paused_reason": "admin_pause",
                          "updated_at": _svc._now()}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "notification_campaign_not_found"})
    return {"ok": True, "notification_campaign_id": notification_campaign_id,
                  "status": "paused"}


@router.patch("/api/admin/notification-campaigns/{notification_campaign_id}/resume")
async def admin_resume(notification_campaign_id: str, request: Request,
                                                user: dict = Depends(current_user)):
    _require_ad_manager(user)
    db = request.app.state.db
    r = await db.notification_campaigns.update_one(
        {"notification_campaign_id": notification_campaign_id,
          "status": "paused"},
        {"$set": {"status": "live",
                          "auto_paused_reason": None,
                          "updated_at": _svc._now()}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "not_paused_or_missing"})
    return {"ok": True, "notification_campaign_id": notification_campaign_id,
                  "status": "live"}


__all__ = ["router"]
