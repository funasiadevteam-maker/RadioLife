"""Phase M — M6 Retargeting Audiences routes."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import retargeting_service as svc

log = logging.getLogger("bigfm.m6_retargeting_routes")
router = APIRouter(tags=["m6-retargeting"])


# ── Ownership helper (identical to Phase L) ─────────────────────
async def _assert_business_ownership(request: Request, user: dict,
                                     business_id: str) -> None:
    if user.get("is_admin"):
        return
    db = request.app.state.db
    row = await db.advertisers.find_one(
        {"advertiser_id": business_id,
         "$or": [{"owner_user_id": user["user_id"]},
                 {"created_by_user_id": user["user_id"]}]})
    if row:
        return
    v2 = await db.advertisers_v2.find_one(
        {"$or": [{"advertiser_id": business_id},
                 {"business_id": business_id}],
         "owner_user_id": user["user_id"]})
    if v2:
        return
    raise HTTPException(403, {"code": "not_authorized_for_advertiser"})


def _bad_request(e: Exception) -> HTTPException:
    return HTTPException(
        400, {"code": str(e).split(":", 1)[0] or "bad_request",
              "detail": str(e)})


# ── Bodies ───────────────────────────────────────────────────────
class Rule(BaseModel):
    signal_type:    str
    comparator:     str = ">="
    value:          float
    lookback_days:  int = 30
    target_id:      Optional[str] = None


class AudienceCreate(BaseModel):
    name:         str
    description:  Optional[str] = None
    rules:        List[Rule]
    rule_logic:   str = "AND"


class AudiencePatch(BaseModel):
    name:         Optional[str] = None
    description:  Optional[str] = None
    rules:        Optional[List[Rule]] = None
    rule_logic:   Optional[str] = None


class CampaignCreate(BaseModel):
    audience_id:                 str
    base_ad_type:                str
    base_ad_id:                  str
    boost_multiplier:            float = 2.0
    cost_per_impression_cents:   int   = Field(gt=0)
    plays_target:                int   = 0
    total_budget_cents:          int   = Field(gt=0)
    start_at:                    Optional[str] = None
    end_at:                      Optional[str] = None


class CancelBody(BaseModel):
    reason:  Optional[str] = None


class DecisionBody(BaseModel):
    admin_notes: Optional[str] = None


class ImpressionBody(BaseModel):
    user_id:     Optional[str] = None
    station_id:  Optional[str] = None


class OptOutBody(BaseModel):
    opt_out:  bool


# ── Advertiser — audiences ───────────────────────────────────────
@router.post("/api/advertiser/{business_id}/retargeting-audiences")
async def create_audience(business_id: str,
                          body: AudienceCreate,
                          request: Request,
                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.create_audience(
            request.app.state.db,
            advertiser_business_id=business_id,
            body=body.model_dump())
    except ValueError as e:
        raise _bad_request(e)


@router.get("/api/advertiser/{business_id}/retargeting-audiences")
async def list_audiences(business_id: str, request: Request,
                         status: Optional[str] = None,
                         limit: int = Query(100, ge=1, le=500),
                         user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    rows = await svc.list_audiences(
        request.app.state.db,
        advertiser_business_id=business_id,
        status=status, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.get("/api/advertiser/{business_id}/"
            "retargeting-audiences/{audience_id}")
async def get_audience(business_id: str, audience_id: str,
                       request: Request,
                       user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.get_audience_detail(
            request.app.state.db,
            audience_id=audience_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.patch("/api/advertiser/{business_id}/"
              "retargeting-audiences/{audience_id}")
async def patch_audience(business_id: str, audience_id: str,
                         body: AudiencePatch, request: Request,
                         user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.update_audience(
            request.app.state.db,
            audience_id=audience_id,
            advertiser_business_id=business_id,
            patch=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "retargeting-audiences/{audience_id}/compute")
async def compute_audience(business_id: str, audience_id: str,
                           request: Request,
                           user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.compute_audience(
            request.app.state.db,
            audience_id=audience_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "retargeting-audiences/{audience_id}/activate")
async def activate_audience(business_id: str, audience_id: str,
                            request: Request,
                            user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.activate_audience(
            request.app.state.db,
            audience_id=audience_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "retargeting-audiences/{audience_id}/archive")
async def archive_audience(business_id: str, audience_id: str,
                           request: Request,
                           user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.archive_audience(
            request.app.state.db,
            audience_id=audience_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


# ── Advertiser — campaigns ───────────────────────────────────────
@router.post("/api/advertiser/{business_id}/retargeting-campaigns")
async def create_campaign(business_id: str,
                          body: CampaignCreate,
                          request: Request,
                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.create_campaign(
            request.app.state.db,
            advertiser_business_id=business_id,
            body=body.model_dump())
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "retargeting-campaigns/{campaign_id}/confirm-payment")
async def confirm_payment(business_id: str, campaign_id: str,
                          request: Request,
                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.confirm_campaign_payment(
            request.app.state.db,
            campaign_id=campaign_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "retargeting-campaigns/{campaign_id}/cancel")
async def cancel_campaign(business_id: str, campaign_id: str,
                          body: CancelBody, request: Request,
                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.cancel_campaign(
            request.app.state.db,
            campaign_id=campaign_id,
            advertiser_business_id=business_id,
            reason=(body.reason or "advertiser_cancelled"))
    except ValueError as e:
        raise _bad_request(e)


@router.get("/api/advertiser/{business_id}/retargeting-campaigns")
async def list_campaigns(business_id: str, request: Request,
                         status: Optional[str] = None,
                         limit: int = Query(100, ge=1, le=500),
                         user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    rows = await svc.list_campaigns(
        request.app.state.db,
        advertiser_business_id=business_id,
        status=status, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.get("/api/advertiser/{business_id}/"
            "retargeting-campaigns/{campaign_id}")
async def get_campaign(business_id: str, campaign_id: str,
                       request: Request,
                       user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.get_campaign(
            request.app.state.db,
            campaign_id=campaign_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


# ── Admin ────────────────────────────────────────────────────────
@router.get("/api/admin/retargeting-audiences")
async def admin_list_audiences(request: Request,
                               advertiser_id: Optional[str] = None,
                               status: Optional[str] = None,
                               limit: int = Query(100, ge=1, le=500),
                               user: dict = Depends(require_admin)):
    rows = await svc.list_audiences(
        request.app.state.db,
        advertiser_business_id=advertiser_id,
        status=status, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.get("/api/admin/retargeting-campaigns")
async def admin_list_campaigns(request: Request,
                               status: Optional[str] = None,
                               limit: int = Query(100, ge=1, le=500),
                               user: dict = Depends(require_admin)):
    rows = await svc.list_campaigns(
        request.app.state.db, status=status, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.post(
    "/api/admin/retargeting-campaigns/{campaign_id}/approve")
async def admin_approve(campaign_id: str, body: DecisionBody,
                        request: Request,
                        user: dict = Depends(require_admin)):
    try:
        return await svc.admin_decide_campaign(
            request.app.state.db,
            campaign_id=campaign_id,
            admin_user_id=user["user_id"], approve=True,
            admin_notes=body.admin_notes)
    except ValueError as e:
        raise _bad_request(e)


@router.post(
    "/api/admin/retargeting-campaigns/{campaign_id}/reject")
async def admin_reject(campaign_id: str, body: DecisionBody,
                       request: Request,
                       user: dict = Depends(require_admin)):
    try:
        return await svc.admin_decide_campaign(
            request.app.state.db,
            campaign_id=campaign_id,
            admin_user_id=user["user_id"], approve=False,
            admin_notes=body.admin_notes)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/admin/retargeting-audiences/sweep")
async def admin_sweep(request: Request,
                      user: dict = Depends(require_admin)):
    r = await svc.sweep_stale_audiences(request.app.state.db)
    return {"ok": True, "stats": r}


# ── Selection ────────────────────────────────────────────────────
@router.get("/api/retargeting/candidates")
async def candidates(request: Request,
                     base_ad_type: str = Query(...),
                     user_id: Optional[str] = None,
                     station_id: Optional[str] = None,
                     user: dict = Depends(current_user)):
    # If caller didn't specify user_id, default to the authenticated
    # user.  Admins can pass an arbitrary user_id for debugging.
    uid = user_id or user.get("user_id")
    if user_id and not user.get("is_admin") and \
            user_id != user.get("user_id"):
        raise HTTPException(403, {"code": "user_id_mismatch"})
    picks = await svc.select_candidates(
        request.app.state.db,
        base_ad_type=base_ad_type,
        user_id=uid, station_id=station_id, limit=3)
    return {"user_id": uid, "base_ad_type": base_ad_type,
            "candidates": picks, "total": len(picks)}


@router.post("/api/retargeting-campaigns/{campaign_id}/impression")
async def impression(campaign_id: str, body: ImpressionBody,
                     request: Request,
                     user: dict = Depends(current_user)):
    uid = body.user_id or user.get("user_id")
    if body.user_id and not user.get("is_admin") and \
            body.user_id != user.get("user_id"):
        raise HTTPException(403, {"code": "user_id_mismatch"})
    return await svc.record_impression(
        request.app.state.db,
        campaign_id=campaign_id,
        user_id=uid,
        station_id=body.station_id)


# ── User privacy — retargeting opt-out ───────────────────────────
@router.get("/api/user/retargeting/opt-out")
async def get_opt_out(request: Request,
                      user: dict = Depends(current_user)):
    return await svc.get_retargeting_opt_out(
        request.app.state.db, user_id=user["user_id"])


@router.post("/api/user/retargeting/opt-out")
async def set_opt_out(body: OptOutBody, request: Request,
                      user: dict = Depends(current_user)):
    return await svc.set_retargeting_opt_out(
        request.app.state.db,
        user_id=user["user_id"], opt_out=body.opt_out)


__all__ = ["router"]
