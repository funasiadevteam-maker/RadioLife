"""Phase G — AD.9 Podcast Completion Points — HTTP routes."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services import podcast_completion_service as _svc

router = APIRouter(tags=["ad9-podcast-completion"])
logger = logging.getLogger("bigfm.ad9.routes")


# ── Guards (reuse Phase F pattern) ──────────────────
def _require_admin(user: Optional[dict]):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    if user.get("role") != "admin":
        raise HTTPException(403, {"code": "admin_only"})


async def _assert_advertiser_owner(db, business_id: str, user: dict):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    if user.get("role") == "admin":
        return
    adv = await db.advertisers_v2.find_one(
        {"advertiser_id": business_id})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    owner = adv.get("owner_user_id")
    staff = [s.get("user_id") for s in (adv.get("staff_users") or [])]
    if user.get("user_id") not in ([owner] + staff):
        raise HTTPException(403, {"code": "advertiser_owner_only"})


# ── Body models ────────────────────────────────────────
class CreateCampaignBody(BaseModel):
    podcast_id:                            Optional[str] = None
    episode_id:                            Optional[str] = None
    points_reward:                      int = Field(..., ge=1)
    currency:                                str = Field("usd")
    sponsor_message:                Optional[str] = None
    max_completions_per_user:  int = Field(1, ge=1)
    max_total_completions:      int = Field(..., ge=1)
    start_at:                                datetime
    end_at:                                    datetime
    cost_per_completion_cents:  int = Field(..., ge=1)


class PatchCampaignBody(BaseModel):
    status:                    Optional[str] = None
    sponsor_message:  Optional[str] = None


class CancelBody(BaseModel):
    reason:  Optional[str] = None


class DecisionBody(BaseModel):
    decision_note:  Optional[str] = None


# ══════════════════════════════════════════════════════════════
# ADVERTISER routes — /api/advertiser/{business_id}/podcast-completion-campaigns/*
# ══════════════════════════════════════════════════════════════
@router.post("/api/advertiser/{business_id}/podcast-completion-campaigns")
async def adv_create(business_id: str, body: CreateCampaignBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.create_campaign(
            db,
            advertiser_business_id=business_id,
            body=body.model_dump(exclude_none=True),
            user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/api/advertiser/{business_id}/podcast-completion-campaigns/{campaign_id}/confirm-payment")
async def adv_confirm_payment(business_id: str, campaign_id: str,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.confirm_payment(
            db, campaign_id=campaign_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        code = str(e)
        if code == "campaign_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


@router.get("/api/advertiser/{business_id}/podcast-completion-campaigns")
async def adv_list(business_id: str, request: Request,
                                    status: Optional[str] = None, limit: int = 100,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    items = await _svc.list_campaigns(
        db, advertiser_business_id=business_id,
        status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/advertiser/{business_id}/podcast-completion-campaigns/{campaign_id}")
async def adv_get(business_id: str, campaign_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    row = await _svc.get_campaign(
        db, campaign_id=campaign_id,
        advertiser_business_id=business_id)
    if not row:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if row.get("forbidden"):
        raise HTTPException(403, {"code": "not_authorized"})
    return row


@router.patch("/api/advertiser/{business_id}/podcast-completion-campaigns/{campaign_id}")
async def adv_patch(business_id: str, campaign_id: str, body: PatchCampaignBody,
                                        request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.patch_campaign(
            db, campaign_id=campaign_id,
            advertiser_business_id=business_id,
            patch=body.model_dump(exclude_none=True))
    except ValueError as e:
        code = str(e)
        if code == "campaign_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


@router.post("/api/advertiser/{business_id}/podcast-completion-campaigns/{campaign_id}/cancel")
async def adv_cancel(business_id: str, campaign_id: str, body: CancelBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.cancel_campaign(
            db, campaign_id=campaign_id,
            advertiser_business_id=business_id,
            reason=body.reason)
    except ValueError as e:
        code = str(e)
        if code == "campaign_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


@router.get("/api/advertiser/{business_id}/podcast-completion-campaigns/{campaign_id}/awards")
async def adv_awards(business_id: str, campaign_id: str, request: Request,
                                          limit: int = 100,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    items = await _svc.list_awards_for_campaign(
        db, campaign_id=campaign_id, limit=limit)
    return {"items": items, "count": len(items)}


# ══════════════════════════════════════════════════════════════
# ADMIN routes — /api/admin/podcast-completion-campaigns/*
# ══════════════════════════════════════════════════════════════
@router.get("/api/admin/podcast-completion-campaigns")
async def admin_list(request: Request, status: Optional[str] = None,
                                        limit: int = 100,
                                        user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    items = await _svc.list_campaigns(db, status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/admin/podcast-completion-campaigns/{campaign_id}")
async def admin_get(campaign_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    row = await _svc.get_campaign(db, campaign_id=campaign_id, is_admin=True)
    if not row:
        raise HTTPException(404, {"code": "campaign_not_found"})
    # Include full award list for admin.
    row["awards"] = await _svc.list_awards_for_campaign(
        db, campaign_id=campaign_id, limit=200)
    return row


@router.post("/api/admin/podcast-completion-campaigns/{campaign_id}/approve")
async def admin_approve(campaign_id: str, body: DecisionBody, request: Request,
                                              user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.admin_approve(
            db, campaign_id=campaign_id,
            admin_user_id=user["user_id"],
            decision_note=body.decision_note)
    except ValueError as e:
        code = str(e)
        if code == "campaign_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


@router.post("/api/admin/podcast-completion-campaigns/{campaign_id}/reject")
async def admin_reject(campaign_id: str, body: DecisionBody, request: Request,
                                            user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.admin_reject(
            db, campaign_id=campaign_id,
            admin_user_id=user["user_id"],
            decision_note=body.decision_note)
    except ValueError as e:
        code = str(e)
        if code == "campaign_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


# ══════════════════════════════════════════════════════════════
# LISTENER — /api/user/podcast-completion-awards
# ══════════════════════════════════════════════════════════════
@router.get("/api/user/podcast-completion-awards")
async def user_awards(request: Request, limit: int = 50,
                                            user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    items = await _svc.list_awards_for_user(
        db, user_id=user["user_id"], limit=limit)
    return {"items": items, "count": len(items)}


__all__ = ["router"]
