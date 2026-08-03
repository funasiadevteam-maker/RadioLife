"""Auction-transparency HTTP routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel

from auth import current_user
from services import auction_insights_service as _svc

router = APIRouter(tags=["auction-insights"])


class BoostBody(BaseModel):
    ad_type:                str
    campaign_id:      str
    new_bid_cents:  int


async def _assert_advertiser_owner(db, advertiser_id: str, user: dict):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    if user.get("role") == "admin":
        return
    adv = await db.advertisers_v2.find_one({"advertiser_id": advertiser_id})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    owner = adv.get("owner_user_id")
    staff = [s.get("user_id") for s in (adv.get("staff_users") or [])]
    if user.get("user_id") in ([owner] + staff):
        return
    raise HTTPException(403, {"code": "advertiser_owner_only"})


@router.get("/api/advertiser/{advertiser_id}/auction-insights",
                        description="Recent auction LOSSES for this advertiser.")
async def insights(advertiser_id: str, request: Request,
                                    hours: int = Query(24, ge=1, le=720),
                                    limit: int = Query(100, ge=1, le=500),
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _svc.advertiser_insights(
        db, advertiser_id=advertiser_id,
        hours=hours, limit=limit)


@router.post("/api/advertiser/{advertiser_id}/auction-insights/boost")
async def boost(advertiser_id: str, body: BoostBody, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    try:
        return await _svc.boost_campaign_bid(
            db, ad_type=body.ad_type,
            campaign_id=body.campaign_id,
            new_bid_cents=body.new_bid_cents,
            advertiser_id=advertiser_id)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


__all__ = ["router"]
