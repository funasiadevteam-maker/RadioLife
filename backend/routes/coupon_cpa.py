"""Phase N — M7 CPA routes.

Companion routes for the CPA charge pipeline that sits on top of
AD.4 coupon campaigns.  Ownership uses the same helper pattern as
Phase L / M.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import current_user, require_admin
from services import coupon_cpa_charge_pipeline as pipe

log = logging.getLogger("bigfm.m7_cpa_routes")
router = APIRouter(tags=["m7-coupon-cpa"])


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


def _bad(e: Exception) -> HTTPException:
    return HTTPException(
        400, {"code": str(e).split(":", 1)[0] or "bad_request",
              "detail": str(e)})


# ── Bodies ─────────────────────────────────────────────────────
class DisputeBody(BaseModel):
    reason: str


class AdminRefundBody(BaseModel):
    reason: str


# ── Advertiser ────────────────────────────────────────────────
@router.get("/api/advertiser/{business_id}/"
            "coupon-campaigns/{campaign_id}/charges-metric")
async def get_metric(business_id: str, campaign_id: str,
                     request: Request,
                     user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        m = await pipe.campaign_charges_metric(
            request.app.state.db, campaign_id=campaign_id)
    except ValueError as e:
        raise _bad(e)
    return m


@router.get("/api/advertiser/{business_id}/"
            "coupon-campaigns/{campaign_id}/charges")
async def list_campaign_charges(business_id: str, campaign_id: str,
                                request: Request,
                                refunded: Optional[bool] = None,
                                limit: int = Query(100, ge=1, le=500),
                                skip:  int = Query(0, ge=0),
                                user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    rows = await pipe.list_charges(
        request.app.state.db,
        advertiser_business_id=business_id,
        campaign_id=campaign_id,
        refunded=refunded, limit=limit, skip=skip)
    return {"items": rows, "total": len(rows)}


@router.post("/api/advertiser/{business_id}/coupon-campaigns/"
             "{campaign_id}/charges/{charge_id}/dispute")
async def dispute_charge(business_id: str, campaign_id: str,
                         charge_id: str, body: DisputeBody,
                         request: Request,
                         user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await pipe.advertiser_dispute_charge(
            request.app.state.db,
            campaign_id=campaign_id,
            charge_id=charge_id,
            advertiser_business_id=business_id,
            reason=body.reason,
            advertiser_user_id=user["user_id"])
    except ValueError as e:
        raise _bad(e)


# ── Admin ──────────────────────────────────────────────────────
@router.get("/api/admin/coupon-action-charges")
async def admin_list_charges(request: Request,
                             advertiser_business_id: Optional[str] = None,
                             campaign_id: Optional[str] = None,
                             refunded: Optional[bool] = None,
                             limit: int = Query(100, ge=1, le=500),
                             skip: int = Query(0, ge=0),
                             user: dict = Depends(require_admin)):
    rows = await pipe.list_charges(
        request.app.state.db,
        advertiser_business_id=advertiser_business_id,
        campaign_id=campaign_id,
        refunded=refunded, limit=limit, skip=skip)
    return {"items": rows, "total": len(rows)}


@router.post("/api/admin/coupon-action-charges/{charge_id}/refund")
async def admin_refund(charge_id: str, body: AdminRefundBody,
                       request: Request,
                       user: dict = Depends(require_admin)):
    try:
        return await pipe.admin_refund_charge(
            request.app.state.db,
            charge_id=charge_id,
            reason=body.reason,
            admin_user_id=user["user_id"])
    except ValueError as e:
        raise _bad(e)


__all__ = ["router"]
