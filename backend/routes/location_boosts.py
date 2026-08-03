"""Phase J — M2 Location-Boost Ads routes.

Endpoint surface:
  * `/api/user/location/*`                              — listener location ping + opt-out.
  * `/api/advertiser/{business_id}/location-boosts/*` — advertiser CRUD + Stripe prepay.
  * `/api/admin/location-boosts/*`                    — admin moderation queue.
  * `/api/location-boosts/*`                              — auction hook + impression.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import location_boost_service as svc

log = logging.getLogger("bigfm.m2_lb_routes")

router = APIRouter(tags=["m2-location-boosts"])


# ── Helpers ──────────────────────────────────────────────────────
async def _assert_business_ownership(request: Request, user: dict,
                                                                          business_id: str) -> None:
    if user.get("is_admin"):
        return
    db = request.app.state.db
    row = await db.advertisers.find_one(
        {"advertiser_id": business_id,
          "$or": [{"owner_user_id":  user["user_id"]},
                          {"created_by_user_id": user["user_id"]}]})
    if row:
        return
    v2 = await db.advertisers_v2.find_one(
        {"$or": [{"advertiser_id": business_id},
                          {"business_id":    business_id}],
          "owner_user_id": user["user_id"]})
    if v2:
        return
    raise HTTPException(403, {"code": "not_authorized_for_advertiser"})


def _bad_request(e: Exception) -> HTTPException:
    return HTTPException(400, {"code": str(e).split(":", 1)[0] or "bad_request",
                                                                "detail": str(e)})


# ── Request bodies ───────────────────────────────────────────────
class LocationPingBody(BaseModel):
    lat: float
    lng: float
    accuracy_meters: Optional[float] = None
    source: Optional[str] = "browser"


class GeofenceSpec(BaseModel):
    type:                  str
    center_lat:      Optional[float] = None
    center_lng:      Optional[float] = None
    radius_meters: Optional[float] = None
    vertices:          Optional[List[List[float]]] = None


class TimeWindowSpec(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_hour:  int = Field(ge=0, le=23)
    end_hour:      int = Field(ge=0, le=23)


class CreateCampaignBody(BaseModel):
    display_name:                          str
    base_ad_type:                          str    # banner|coupon|notification|game_sponsorship
    base_ad_id:                            Optional[str] = None
    inline_creative:                    Optional[dict] = None
    geofences:                              List[GeofenceSpec]
    time_windows:                        List[TimeWindowSpec] = []
    boost_multiplier:                  float = 1.5
    cost_per_impression_cents:  int = Field(ge=1)
    plays_target:                          int = Field(ge=1)
    start_at:                                Optional[str] = None
    end_at:                                    Optional[str] = None


class CancelBody(BaseModel):
    reason: Optional[str] = "advertiser_cancelled"


class AdminDecisionBody(BaseModel):
    admin_notes: Optional[str] = None


class RecordImpressionBody(BaseModel):
    lat:                    float
    lng:                    float
    session_id:      Optional[str] = None
    base_ad_type:  str
    base_ad_id:      Optional[str] = None


# ────────────────────────────────────────────────────────────────
#  USER  LOCATION
# ────────────────────────────────────────────────────────────────
@router.post("/api/user/location/ping")
async def location_ping(body: LocationPingBody, request: Request,
                                                user: dict = Depends(current_user)):
    try:
        return await svc.record_user_location(
            request.app.state.db,
            user_id=user["user_id"],
            lat=body.lat, lng=body.lng,
            accuracy_meters=body.accuracy_meters,
            source=(body.source or "browser"))
    except ValueError as e:
        raise _bad_request(e)


@router.delete("/api/user/location")
async def location_delete(request: Request,
                                                    user: dict = Depends(current_user)):
    return await svc.clear_user_location(
        request.app.state.db, user_id=user["user_id"])


@router.get("/api/user/location")
async def location_get(request: Request,
                                              user: dict = Depends(current_user)):
    pair = await svc.get_user_location(
        request.app.state.db, user_id=user["user_id"])
    return {"has_location": bool(pair),
                    "lat": pair[0] if pair else None,
                    "lng": pair[1] if pair else None}


# ────────────────────────────────────────────────────────────────
#  ADVERTISER
# ────────────────────────────────────────────────────────────────
@router.post("/api/advertiser/{business_id}/location-boosts")
async def create_lb(business_id: str, body: CreateCampaignBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.create_campaign(
            request.app.state.db,
            advertiser_business_id=business_id,
            body=body.model_dump(),
            user_id=user["user_id"])
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/location-boosts/"
                          "{campaign_id}/confirm-payment")
async def confirm_lb(business_id: str, campaign_id: str,
                                            request: Request,
                                            user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.confirm_payment(
            request.app.state.db,
            campaign_id=campaign_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.get("/api/advertiser/{business_id}/location-boosts")
async def list_lb_for_advertiser(business_id: str, request: Request,
                                                                        status: Optional[str] = None,
                                                                        user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    items = await svc.list_campaigns(
        request.app.state.db,
        advertiser_business_id=business_id,
        status=status)
    return {"items": items, "count": len(items)}


@router.get("/api/advertiser/{business_id}/location-boosts/{campaign_id}")
async def get_lb(business_id: str, campaign_id: str, request: Request,
                                user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    row = await svc.get_campaign(
        request.app.state.db,
        campaign_id=campaign_id,
        advertiser_business_id=business_id)
    if not row:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return row


@router.post("/api/advertiser/{business_id}/location-boosts/"
                          "{campaign_id}/cancel")
async def cancel_lb(business_id: str, campaign_id: str,
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


# ────────────────────────────────────────────────────────────────
#  ADMIN
# ────────────────────────────────────────────────────────────────
@router.get("/api/admin/location-boosts")
async def admin_list_lb(request: Request,
                                              status: Optional[str] = None,
                                              _admin: dict = Depends(require_admin)):
    items = await svc.admin_list(request.app.state.db, status=status)
    return {"items": items, "count": len(items)}


@router.get("/api/admin/location-boosts/{campaign_id}")
async def admin_get_lb(campaign_id: str, request: Request,
                                              _admin: dict = Depends(require_admin)):
    row = await svc.get_campaign(request.app.state.db,
                                                              campaign_id=campaign_id)
    if not row:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return row


@router.post("/api/admin/location-boosts/{campaign_id}/approve")
async def admin_approve_lb(campaign_id: str, body: AdminDecisionBody,
                                                    request: Request,
                                                    admin: dict = Depends(require_admin)):
    try:
        return await svc.admin_approve(
            request.app.state.db, campaign_id=campaign_id,
            admin_user_id=admin["user_id"],
            admin_notes=body.admin_notes)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/admin/location-boosts/{campaign_id}/reject")
async def admin_reject_lb(campaign_id: str, body: AdminDecisionBody,
                                                  request: Request,
                                                  admin: dict = Depends(require_admin)):
    try:
        return await svc.admin_reject(
            request.app.state.db, campaign_id=campaign_id,
            admin_user_id=admin["user_id"],
            admin_notes=(body.admin_notes or ""))
    except ValueError as e:
        raise _bad_request(e)


# ────────────────────────────────────────────────────────────────
#  AUCTION HOOK  (called by AD.11 / AD.4 / AD.12 servers OR the FE)
# ────────────────────────────────────────────────────────────────
@router.get("/api/location-boosts/candidates")
async def candidates(request: Request,
                                          base_ad_type: str = Query(...),
                                          lat: Optional[float] = None,
                                          lng: Optional[float] = None,
                                          user: dict = Depends(current_user)):
    items = await svc.select_candidates(
        request.app.state.db,
        base_ad_type=base_ad_type,
        user_id=user.get("user_id"),
        lat=lat, lng=lng)
    return {"items": items, "count": len(items)}


@router.post("/api/location-boosts/{campaign_id}/impression")
async def impression(campaign_id: str, body: RecordImpressionBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    try:
        return await svc.record_impression(
            request.app.state.db, campaign_id=campaign_id,
            user_id=user.get("user_id"),
            session_id=body.session_id,
            lat=body.lat, lng=body.lng,
            base_ad_type=body.base_ad_type,
            base_ad_id=body.base_ad_id)
    except ValueError as e:
        raise _bad_request(e)


__all__ = ["router"]
