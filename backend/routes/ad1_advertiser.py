"""Phase AD.1 — Advertiser self-service router (prefix /api/ad1).

Namespaced /ad1 to coexist with the legacy Phase-18a advertiser routes
(prefix /api/advertiser).  Both systems share nothing but the auth layer
and the Stripe webhook."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user

from services.ad1_advertiser_service import (
    approve_advertiser, approve_campaign, campaign_analytics,
    create_advertiser, create_campaign, create_topup_checkout,
    end_campaign, ensure_ad1_indexes, get_advertiser, get_campaign,
    list_campaigns_for_advertiser, list_mine, pause_campaign,
    reject_advertiser, reject_campaign, submit_advertiser_for_approval,
    submit_campaign_for_approval, update_advertiser, update_campaign,
    advertiser_overview, assert_owner,
)

logger = logging.getLogger("bigfm.ad1.routes")
router = APIRouter(prefix="/api/ad1", tags=["ad1-advertiser"])


# ─── Body models ─────────────────────────────────────────────
class RegisterBody(BaseModel):
    name:                    str
    contact_email:  str
    contact_name:   Optional[str] = None
    phone:                  Optional[str] = None
    website:              Optional[str] = None
    industry:            Optional[str] = None
    logo_url:            Optional[str] = None


class TopUpBody(BaseModel):
    amount_cents:  int
    success_url:      Optional[str] = None
    cancel_url:      Optional[str] = None


class CampaignCreateBody(BaseModel):
    name:                              str
    campaign_type:                str
    start_at:                         Optional[str] = None
    end_at:                            Optional[str] = None
    budget_total_cents:      int
    daily_cap_cents:              Optional[int] = None
    pricing_model:                str = "cpm"
    cpm_bid_cents:                Optional[int] = None
    cpc_bid_cents:                Optional[int] = None
    targeting:                        Optional[dict] = None
    creative:                          Optional[dict] = None


# ─── Advertiser CRUD ─────────────────────────────────────────
@router.post("/advertiser/register")
async def register_advertiser(body: RegisterBody, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        adv = await create_advertiser(
            db,
            owner_user_id=user["user_id"],
            name=body.name,
            contact_email=body.contact_email,
            contact_name=body.contact_name,
            phone=body.phone,
            website=body.website,
            industry=body.industry,
            logo_url=body.logo_url,
        )
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    logger.info("[ad1] advertiser %s registered by %s",
                          adv["advertiser_id"], user["user_id"])
    return adv


@router.get("/advertiser/mine")
async def my_advertisers(request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    items = await list_mine(db, owner_user_id=user["user_id"])
    return {"items": items, "count": len(items)}


@router.get("/advertiser/{advertiser_id}")
async def advertiser_detail(advertiser_id: str, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        adv = await assert_owner(db, advertiser_id=advertiser_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                    for k, v in adv.items() if k != "_id"}


@router.put("/advertiser/{advertiser_id}")
async def advertiser_update(advertiser_id: str, body: dict, request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        adv = await update_advertiser(db, advertiser_id=advertiser_id,
                                                                  patch=body, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    return adv


@router.get("/advertiser/{advertiser_id}/overview")
async def overview(advertiser_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        await assert_owner(db, advertiser_id=advertiser_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    return await advertiser_overview(db, advertiser_id=advertiser_id)


@router.post("/advertiser/{advertiser_id}/submit-for-approval")
async def submit_advertiser(advertiser_id: str, request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await submit_advertiser_for_approval(
            db, advertiser_id=advertiser_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


# ─── Campaign CRUD ─────────────────────────────────────────
@router.post("/advertiser/{advertiser_id}/campaigns")
async def campaign_create(advertiser_id: str, body: CampaignCreateBody,
                                                        request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        camp = await create_campaign(db, advertiser_id=advertiser_id,
                                                                    payload=body.model_dump(),
                                                                    user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    return camp


@router.get("/advertiser/{advertiser_id}/campaigns")
async def campaigns_list(advertiser_id: str, request: Request,
                                                      status: Optional[str] = None,
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        await assert_owner(db, advertiser_id=advertiser_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    items = await list_campaigns_for_advertiser(
        db, advertiser_id=advertiser_id, status=status)
    return {"items": items, "count": len(items)}


@router.get("/advertiser/{advertiser_id}/campaigns/{campaign_id}")
async def campaign_detail(advertiser_id: str, campaign_id: str,
                                                        request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        await assert_owner(db, advertiser_id=advertiser_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    camp = await get_campaign(db, advertiser_id=advertiser_id,
                                                        campaign_id=campaign_id)
    if not camp:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return camp


@router.put("/advertiser/{advertiser_id}/campaigns/{campaign_id}")
async def campaign_update(advertiser_id: str, campaign_id: str,
                                                            body: dict, request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await update_campaign(db, advertiser_id=advertiser_id,
                                                                  campaign_id=campaign_id,
                                                                  patch=body, user=user)
    except LookupError as e:
        raise HTTPException(404, {"code": str(e) or "not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/advertiser/{advertiser_id}/campaigns/{campaign_id}/submit-for-approval")
async def campaign_submit(advertiser_id: str, campaign_id: str,
                                                          request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await submit_campaign_for_approval(
            db, advertiser_id=advertiser_id, campaign_id=campaign_id, user=user)
    except LookupError as e:
        raise HTTPException(404, {"code": str(e) or "not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/advertiser/{advertiser_id}/campaigns/{campaign_id}/pause")
async def campaign_pause(advertiser_id: str, campaign_id: str,
                                                      request: Request,
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await pause_campaign(db, advertiser_id=advertiser_id,
                                                              campaign_id=campaign_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@router.post("/advertiser/{advertiser_id}/campaigns/{campaign_id}/end")
async def campaign_end(advertiser_id: str, campaign_id: str,
                                                    request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await end_campaign(db, advertiser_id=advertiser_id,
                                                          campaign_id=campaign_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@router.get("/advertiser/{advertiser_id}/campaigns/{campaign_id}/analytics")
async def campaign_analytics_route(advertiser_id: str, campaign_id: str,
                                                                              request: Request,
                                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        await assert_owner(db, advertiser_id=advertiser_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    try:
        return await campaign_analytics(db, campaign_id=campaign_id)
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})


# ─── Top-up ───────────────────────────────────────────────
@router.post("/advertiser/{advertiser_id}/top-up")
async def topup(advertiser_id: str, body: TopUpBody, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await create_topup_checkout(
            db, advertiser_id=advertiser_id,
            amount_cents=body.amount_cents, user=user,
            success_url=body.success_url, cancel_url=body.cancel_url)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


# ─── Payments history (helper for /budget tab) ────────────
@router.get("/advertiser/{advertiser_id}/payments")
async def list_payments(advertiser_id: str, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        await assert_owner(db, advertiser_id=advertiser_id, user=user)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    docs = await db.ad_payments.find(
        {"advertiser_id": advertiser_id}
    ).sort([("created_at", -1)]).to_list(50)
    items = []
    for d in docs:
        item = {k: v for k, v in d.items() if k != "_id"}
        for k, v in list(item.items()):
            if hasattr(v, "isoformat"):
                item[k] = v.isoformat()
        items.append(item)
    return {"items": items, "count": len(items)}
