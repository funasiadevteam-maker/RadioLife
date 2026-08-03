"""Phase AD.4 — Coupon Pay-Per-Save · HTTP routes."""
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import ad4_coupon_service as _ad4

router = APIRouter(tags=["ad4-coupon-campaigns"])
logger = logging.getLogger("bigfm.ad4.routes")


# ─── RBAC helpers ────────────────────────────────────────────────
async def _assert_advertiser_owner(db, advertiser_id: str, user: dict):
    if user.get("role") == "admin":
        return
    adv = await db.advertisers_v2.find_one({"advertiser_id": advertiser_id},
                                                                                              {"owner_user_id": 1, "staff_users": 1})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    uid = user.get("user_id")
    if adv.get("owner_user_id") == uid:
        return
    for s in (adv.get("staff_users") or []):
        if s.get("staff_user_id") == uid and s.get("active", True) \
                        and s.get("role") in ("manager", "owner"):
            return
    raise HTTPException(403, {"code": "not_advertiser_owner_or_manager"})


async def _assert_merchant_owner(db, merchant_id: str, user: dict):
    if user.get("role") == "admin":
        return
    biz = await db.businesses.find_one(
        {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]},
        {"owner_user_id": 1, "staff_user_ids": 1})
    if not biz:
        raise HTTPException(404, {"code": "merchant_not_found"})
    uid = user.get("user_id")
    if biz.get("owner_user_id") == uid or uid in (biz.get("staff_user_ids") or []):
        return
    raise HTTPException(403, {"code": "not_merchant_owner_or_staff"})


# ─── Body models ─────────────────────────────────────────────────
class CampaignCreateBody(BaseModel):
    title:                                str
    description:                    Optional[str] = None
    terms:                                Optional[str] = None
    sponsoring_merchant_id: Optional[str] = None
    retail_value_cents:      int = 0
    value_currency:              Optional[str] = "USD"
    cost_per_save_cents:      int = Field(0, ge=0, le=100_000)
    total_inventory:            int = Field(0, ge=0)
    category_tags:                List[str] = []
    targeting:                        Optional[Dict[str, Any]] = None
    logo_url:                          Optional[str] = None
    hero_image_url:              Optional[str] = None
    start_time:                      Optional[str] = None    # ISO
    end_time:                          Optional[str] = None
    # Phase N (M7) — CPA pricing extensions.
    pricing_model:                Optional[str] = "cps"   # cps|cpa|hybrid
    cost_per_action_cents:  int = Field(0, ge=0, le=100_000)
    budget_type:                    Optional[str] = "prepaid"


class CampaignPatchBody(BaseModel):
    title:                                Optional[str] = None
    description:                    Optional[str] = None
    terms:                                Optional[str] = None
    sponsoring_merchant_id: Optional[str] = None
    retail_value_cents:      Optional[int] = None
    value_currency:              Optional[str] = None
    cost_per_save_cents:      Optional[int] = None
    total_inventory:            Optional[int] = None
    category_tags:                Optional[List[str]] = None
    targeting:                        Optional[Dict[str, Any]] = None
    logo_url:                          Optional[str] = None
    hero_image_url:              Optional[str] = None
    start_time:                      Optional[str] = None
    end_time:                          Optional[str] = None
    # Phase N (M7).
    pricing_model:                Optional[str] = None
    cost_per_action_cents:  Optional[int] = None
    budget_type:                    Optional[str] = None


class ReviewBody(BaseModel):
    action:  str = Field(..., description="approve | reject | pause")
    reason:  Optional[str] = None


# ─── Advertiser CRUD ─────────────────────────────────────────────
@router.post("/api/advertiser/{advertiser_id}/coupon-campaigns",
                          description="Advertiser creates a draft coupon campaign.")
async def create_campaign(advertiser_id: str, body: CampaignCreateBody,
                                                          request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    from datetime import datetime
    payload = body.model_dump()
    for k in ("start_time", "end_time"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            try:
                payload[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                payload[k] = None
    try:
        doc = await _ad4.create_coupon_campaign(db, advertiser_id=advertiser_id,
                                                                                              payload=payload)
    except ValueError as e:
        code = str(e)
        raise HTTPException(400, {"code": code.split(":", 1)[0],
                                                          "detail": code})
    return doc


@router.patch("/api/advertiser/coupon-campaigns/{campaign_id}",
                            description="Edit a draft/rejected campaign.")
async def patch_campaign(campaign_id: str, body: CampaignPatchBody,
                                                        request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.coupon_campaigns.find_one({"campaign_id": campaign_id},
                                                                                                                    {"advertiser_id": 1})
    if not existing:
        raise HTTPException(404, {"code": "campaign_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    from datetime import datetime
    payload = {k: v for k, v in body.model_dump(exclude_unset=True).items()
                              if v is not None}
    for k in ("start_time", "end_time"):
        if k in payload and isinstance(payload[k], str):
            try:
                payload[k] = datetime.fromisoformat(
                    payload[k].replace("Z", "+00:00"))
            except Exception:
                payload[k] = None
    try:
        doc = await _ad4.patch_coupon_campaign(db, campaign_id=campaign_id,
                                                                                                      payload=payload)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    if not doc:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return doc


@router.post("/api/advertiser/coupon-campaigns/{campaign_id}/publish",
                          description="Submit for admin review (status → pending_admin).")
async def publish_campaign(campaign_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    existing = await db.coupon_campaigns.find_one({"campaign_id": campaign_id},
                                                                                                                    {"advertiser_id": 1})
    if not existing:
        raise HTTPException(404, {"code": "campaign_not_found"})
    await _assert_advertiser_owner(db, existing["advertiser_id"], user)
    # ADMOD.1 — advertisers marked "blocked" cannot publish new creatives.
    from services import ad_creative_review_service as _ad_review
    if await _ad_review.is_advertiser_blocked(db, existing["advertiser_id"]):
        raise HTTPException(403, {"code": "advertiser_blocked"})
    try:
        doc = await _ad4.publish_coupon_campaign(db, campaign_id=campaign_id)
    except ValueError as e:
        code = str(e)
        raise HTTPException(400, {"code": code.split(":", 1)[0],
                                                          "detail": code})
    # ADMOD.1 — mint a review row (or refresh existing).  Runs OpenAI
    # moderation on title/description/terms behind the scenes.
    try:
        await _ad_review.create_review(
            db, ad_type="coupon_campaign", target_id=campaign_id,
            advertiser_id=existing["advertiser_id"],
            submitted_by=user.get("user_id"))
    except Exception as _e:
        logger.warning("[ad4-publish] review row creation failed: %s", _e)
    return doc


@router.get("/api/advertiser/{advertiser_id}/coupon-campaigns",
                          description="List advertiser coupon campaigns (all statuses).")
async def list_campaigns(advertiser_id: str, request: Request,
                                                        status: Optional[str] = None,
                                                        limit: int = 50,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    items = await _ad4.list_advertiser_coupon_campaigns(
        db, advertiser_id=advertiser_id, status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/advertiser/{advertiser_id}/coupon-transactions",
                          description="Spend history + per-campaign roll-ups for the advertiser.")
async def advertiser_coupon_transactions(
        advertiser_id: str, request: Request,
        limit: int = Query(100, ge=1, le=500),
        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    return await _ad4.list_advertiser_coupon_transactions(
        db, advertiser_id=advertiser_id, limit=limit)


# ─── Admin review ────────────────────────────────────────────────
@router.post("/api/admin/coupon-campaigns/{campaign_id}/review",
                          description="Admin approve/reject/pause a campaign.")
async def admin_review(campaign_id: str, body: ReviewBody, request: Request,
                                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        doc = await _ad4.admin_review_coupon_campaign(
            db, campaign_id=campaign_id, action=body.action,
            admin_user_id=admin.get("user_id"), reason=body.reason)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    if not doc:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return doc


@router.get("/api/admin/coupon-campaigns/pending",
                          description="Admin queue — pending_admin submissions oldest-first.")
async def admin_pending(request: Request, limit: int = 100,
                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    items = await _ad4.list_admin_pending(db, limit=limit)
    return {"items": items, "count": len(items)}


# ─── Customer-facing listing + save ──────────────────────────────
@router.get("/api/coupon-campaigns/live",
                          description=("Public listing of live coupon campaigns filtered by "
                                                          "market + city + category tags."))
async def live_campaigns(request: Request,
                                                      market: Optional[str] = None,
                                                      city: Optional[str] = None,
                                                      category_tag: Optional[str] = None,
                                                      limit: int = 40):
    db = request.app.state.db
    items = await _ad4.list_live_coupon_campaigns(
        db, market=market, city=city, category_tag=category_tag, limit=limit)
    return {"items": items, "count": len(items)}


@router.post("/api/coupon-campaigns/{campaign_id}/save",
                          description=("Customer tap-to-save: mints coupon + wallet_item, "
                                                          "bills advertiser via split-routed ledger.  "
                                                          "Idempotent per (user_id, campaign_id)."))
async def customer_save(campaign_id: str, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    if not uid:
        raise HTTPException(401, {"code": "no_user"})
    res = await _ad4.save_coupon_campaign(db, campaign_id=campaign_id,
                                                                                                user_id=uid)
    # Non-2xx if intrinsically failed (not found / expired / cap).
    if not res.get("ok"):
        reason = res.get("reason")
        if reason == "campaign_not_found":
            raise HTTPException(404, res)
        if reason in ("inventory_exhausted", "expired"):
            raise HTTPException(410, res)
        if reason == "not_started":
            raise HTTPException(425, res)
        if reason == "wallet_exhausted":
            raise HTTPException(402, res)
        if reason and reason.startswith("campaign_"):
            raise HTTPException(409, res)
        raise HTTPException(400, res)
    return res


# ─── Merchant view ───────────────────────────────────────────────
@router.get("/api/merchant/{merchant_id}/coupon-sponsorship-revenue",
                          description="Per-merchant inbound splits from coupon-save events.")
async def merchant_coupon_revenue(merchant_id: str, request: Request,
                                                                              limit: int = Query(100, ge=1, le=500),
                                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_merchant_owner(db, merchant_id, user)
    return await _ad4.list_merchant_coupon_revenue(
        db, merchant_id=merchant_id, limit=limit)


__all__ = ["router"]
