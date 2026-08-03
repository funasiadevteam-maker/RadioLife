"""Phase PW-M.1 — Merchant Predict & Win router.

Two mount points:
    /api/merchant/predict-win/*                — merchant surface, RBAC-gated
    /api/admin/predict-win/*                      — admin surface, admin-only
                                                                                  (parent-campaigns/{id}/merchant-eligible,
                                                                                    merchant-campaigns/{approve|reject|pause},
                                                                                    businesses/{id}/auto-publish-predict-win)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, Body, Depends, HTTPException, Query, Request)
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import (
    merchant_predict_win_analytics_service as analytics_svc,
    merchant_prize_inventory_service as prize_svc,
    predict_win_merchant_service as merchant_svc,
)
from services.merchant_rbac_service import resolve_merchant_with_role

router = APIRouter(tags=["predict-win-merchant"])


# ═════════════════════════════════════════════════════
# Merchant surface  —  /api/merchant/predict-win/*
# ═════════════════════════════════════════════════════
async def _gate(request: Request, merchant_id: str, user: dict,
                              permission: str = "can_manage_predict_win") -> Dict[str, Any]:
    """RBAC gate.  Falls back to `can_create_links` (owner+manager+marketing)
    if the new permission isn't registered on the merchant's role set —
    keeps PW-M.1 rolling without a MER RBAC migration."""
    db = request.app.state.db
    try:
        biz, role = await resolve_merchant_with_role(
            db, merchant_id=merchant_id, user=user, permission=permission)
    except HTTPException as e:
        if e.status_code == 403:
            biz, role = await resolve_merchant_with_role(
                db, merchant_id=merchant_id, user=user,
                permission="can_create_links")
        else:
            raise
    return {"biz": biz, "role": role}


# ─── Preferences ───────────────────────────────────
@router.get("/api/merchant/{merchant_id}/predict-win/preferences")
async def get_merchant_prefs(merchant_id: str, request: Request,
                                                                                user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    return await merchant_svc.get_preferences(request.app.state.db,
                                                                                                              merchant_id=merchant_id)


class PrefsPatchIn(BaseModel):
    preferred_categories:                Optional[List[str]] = None
    preferred_sports:                        Optional[List[str]] = None
    preferred_leagues:                    Optional[List[str]] = None
    preferred_teams:                        Optional[List[str]] = None
    default_prize_inventory_id: Optional[str] = None
    max_campaigns_per_week:      Optional[int] = None
    default_checkin_required:    Optional[bool] = None
    auto_draft_enabled:                Optional[bool] = None
    active:                                          Optional[bool] = None


@router.patch("/api/merchant/{merchant_id}/predict-win/preferences")
async def patch_merchant_prefs(merchant_id: str, body: PrefsPatchIn,
                                                                                    request: Request,
                                                                                    user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    return await merchant_svc.patch_preferences(
        request.app.state.db, merchant_id=merchant_id,
        updates=body.model_dump(exclude_none=True))


# ─── Discovery of eligible parent campaigns ─────
@router.get("/api/merchant/{merchant_id}/predict-win/recommended")
async def recommended(merchant_id: str, request: Request,
                                                    limit: int = Query(10, ge=1, le=50),
                                                    user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    items = await merchant_svc.recommend_for_merchant(
        request.app.state.db, merchant_id=merchant_id, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/merchant/{merchant_id}/predict-win/available-predictions")
async def available_predictions(merchant_id: str, request: Request,
                                                                              category: Optional[str] = Query(None),
                                                                              starting_within_hours: Optional[int] = Query(None, ge=1),
                                                                              limit: int = Query(20, ge=1, le=100),
                                                                              offset: int = Query(0, ge=0),
                                                                              user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    items, total = await merchant_svc.list_eligible_parents(
        request.app.state.db, category=category,
        starting_within_hours=starting_within_hours,
        limit=limit, offset=offset)
    return {"items": items, "total": total,
                        "limit": limit, "offset": offset}


@router.get(
    "/api/merchant/{merchant_id}/predict-win/available-predictions/{parent_id}")
async def parent_detail(merchant_id: str, parent_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    parent = await merchant_svc.get_eligible_parent(
        request.app.state.db, parent_id=parent_id)
    if not parent:
        raise HTTPException(404, {"code": "parent_not_found_or_ineligible"})
    return parent


# ─── Prize inventory CRUD ───────────────────────
@router.get("/api/merchant/{merchant_id}/predict-win/prize-inventory")
async def list_prize_inventory(merchant_id: str, request: Request,
                                                                                include_inactive: bool = Query(False),
                                                                                location_id: Optional[str] = Query(None),
                                                                                user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    items = await prize_svc.list_prize_inventory(
        request.app.state.db, merchant_id=merchant_id,
        include_inactive=include_inactive, location_id=location_id)
    return {"items": items, "count": len(items)}


class PrizeCreateIn(BaseModel):
    prize_type:                  str
    title:                            str
    description:                Optional[str] = None
    retail_value:              float = 0
    currency:                      Optional[str] = "AED"
    quantity_total:          int = Field(ge=1)
    expiration_policy:     Optional[Dict[str, Any]] = None
    redemption_method:     Optional[str] = "cashier_qr"
    terms:                            Optional[str] = None
    location_id:                Optional[str] = None


@router.post("/api/merchant/{merchant_id}/predict-win/prize-inventory")
async def create_prize_inv(merchant_id: str, body: PrizeCreateIn,
                                                                request: Request,
                                                                user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    try:
        return await prize_svc.create_prize(
            request.app.state.db, merchant_id=merchant_id,
            body=body.model_dump())
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


class PrizePatchIn(BaseModel):
    title:                            Optional[str] = None
    description:                Optional[str] = None
    retail_value:              Optional[float] = None
    terms:                            Optional[str] = None
    active:                          Optional[bool] = None
    location_id:                Optional[str] = None
    expiration_policy:     Optional[Dict[str, Any]] = None
    redemption_method:     Optional[str] = None


@router.patch("/api/merchant/{merchant_id}/predict-win/prize-inventory/{prize_id}")
async def patch_prize_inv(merchant_id: str, prize_id: str, body: PrizePatchIn,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    try:
        return await prize_svc.patch_prize(
            request.app.state.db, prize_id=prize_id, merchant_id=merchant_id,
            updates=body.model_dump(exclude_none=True))
    except LookupError:
        raise HTTPException(404, {"code": "prize_not_found"})


# ─── Child campaign CRUD ────────────────────────
class ChildCampaignCreateIn(BaseModel):
    parent_predict_win_campaign_id: str
    campaign_title:                                        Optional[str] = None
    campaign_description:                            Optional[str] = None
    promotional_message:                              Optional[str] = None
    prize_inventory_id:                                str
    prize_quantity_reserved:                    int = 1
    winner_rule:                                            Optional[str] = "first_n_correct"
    max_winners:                                            Optional[int] = 1
    entry_rules:                                            Optional[Dict[str, Any]] = None
    placement_rules:                                    Optional[Dict[str, Any]] = None
    location_id:                                            Optional[str] = None
    start_time:                                              Optional[str] = None
    lock_time:                                                Optional[str] = None
    end_time:                                                  Optional[str] = None


@router.post("/api/merchant/{merchant_id}/predict-win/campaigns/from-existing-prediction")
async def create_child(merchant_id: str, body: ChildCampaignCreateIn,
                                                    request: Request,
                                                    user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    try:
        return await merchant_svc.create_child_campaign(
            request.app.state.db, merchant_id=merchant_id,
            user_id=user["user_id"], body=body.model_dump())
    except LookupError as e:
        raise HTTPException(404, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.get("/api/merchant/{merchant_id}/predict-win/campaigns")
async def list_child(merchant_id: str, request: Request,
                                                status: Optional[str] = Query(None),
                                                limit: int = Query(50, ge=1, le=200),
                                                offset: int = Query(0, ge=0),
                                                user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    items, total = await merchant_svc.list_merchant_campaigns(
        request.app.state.db, merchant_id=merchant_id, status=status,
        limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/api/merchant/{merchant_id}/predict-win/campaigns/{campaign_id}")
async def get_child(merchant_id: str, campaign_id: str, request: Request,
                                                user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    c = await merchant_svc.get_merchant_campaign(
        request.app.state.db, campaign_id=campaign_id, merchant_id=merchant_id)
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return c


class ChildPatchIn(BaseModel):
    campaign_title:              Optional[str] = None
    campaign_description: Optional[str] = None
    promotional_message: Optional[str] = None
    entry_rules:                    Optional[Dict[str, Any]] = None
    placement_rules:            Optional[Dict[str, Any]] = None


@router.patch("/api/merchant/{merchant_id}/predict-win/campaigns/{campaign_id}")
async def patch_child(merchant_id: str, campaign_id: str, body: ChildPatchIn,
                                                    request: Request,
                                                    user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    try:
        return await merchant_svc.patch_merchant_campaign(
            request.app.state.db, campaign_id=campaign_id,
            merchant_id=merchant_id,
            updates=body.model_dump(exclude_none=True))
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@router.post("/api/merchant/{merchant_id}/predict-win/campaigns/{campaign_id}/publish")
async def publish_child(merchant_id: str, campaign_id: str, request: Request,
                                                            user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    try:
        return await merchant_svc.publish_merchant_campaign(
            request.app.state.db, campaign_id=campaign_id,
            merchant_id=merchant_id)
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@router.post("/api/merchant/{merchant_id}/predict-win/campaigns/{campaign_id}/pause")
async def pause_child(merchant_id: str, campaign_id: str, request: Request,
                                                    user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    try:
        return await merchant_svc.pause_merchant_campaign(
            request.app.state.db, campaign_id=campaign_id,
            merchant_id=merchant_id)
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


class AttachEntryIn(BaseModel):
    entry_id: str
    venue_checkin_id: Optional[str] = None


@router.post("/api/merchant/{merchant_id}/predict-win/campaigns/{campaign_id}/attach-entry")
async def attach_entry(merchant_id: str, campaign_id: str,
                                                  body: AttachEntryIn, request: Request,
                                                  user: dict = Depends(current_user)):
    """Called by a customer-side flow (or admin fixture) to link an
    existing `predict_win_entries` row to a merchant child campaign so
    the winner selection scope covers them.  Merchant-authenticated
    (RBAC-gated) — merchants supply their own attach flows via
    landing pages / QR pointers in PW-M.2."""
    await _gate(request, merchant_id, user)
    try:
        row = await merchant_svc.attach_entry(
            request.app.state.db,
            merchant_campaign_id=campaign_id,
            entry_id=body.entry_id,
            user_id=user["user_id"],
            venue_checkin_id=body.venue_checkin_id)
        return {"ok": True, "entry": row}
    except LookupError as e:
        raise HTTPException(404, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.get("/api/merchant/{merchant_id}/predict-win/campaigns/{campaign_id}/analytics")
async def child_analytics(merchant_id: str, campaign_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    await _gate(request, merchant_id, user)
    c = await merchant_svc.get_merchant_campaign(
        request.app.state.db, campaign_id=campaign_id, merchant_id=merchant_id)
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    counts = await analytics_svc.aggregate_campaign(
        request.app.state.db, merchant_campaign_id=campaign_id)
    # Roll up entries + awards from source-of-truth collections too.
    db = request.app.state.db
    entries_n = await db.merchant_predict_win_entries.count_documents(
        {"merchant_campaign_id": campaign_id})
    awards_n = await db.merchant_predict_win_awards.count_documents(
        {"merchant_campaign_id": campaign_id})
    redemptions_n = await db.merchant_predict_win_awards.count_documents(
        {"merchant_campaign_id": campaign_id,
          "award_status": "redeemed"})
    return {
        "campaign": c,
        "events":            counts,
        "totals": {
            "entries":          entries_n,
            "awards":            awards_n,
            "redemptions": redemptions_n,
        },
    }


# ═════════════════════════════════════════════════════
# Admin surface  —  /api/admin/predict-win/*
# ═════════════════════════════════════════════════════
class MerchantEligibleIn(BaseModel):
    merchant_eligible: bool


@router.patch("/api/admin/predict-win/parent-campaigns/{parent_id}/merchant-eligible")
async def admin_toggle_parent_eligible(parent_id: str, body: MerchantEligibleIn,
                                                                                                request: Request,
                                                                                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    pc = await db.predict_win_campaigns.find_one({"campaign_id": parent_id})
    if not pc:
        raise HTTPException(404, {"code": "parent_not_found"})
    from datetime import datetime, timezone
    await db.predict_win_campaigns.update_one(
        {"campaign_id": parent_id},
        {"$set": {"merchant_eligible": bool(body.merchant_eligible),
                              "merchant_eligible_by":     admin["user_id"],
                              "merchant_eligible_at":     datetime.now(timezone.utc).isoformat()}})
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": parent_id})
    return {"ok": True, "campaign_id": parent_id,
                        "merchant_eligible": bool(fresh.get("merchant_eligible"))}


@router.get("/api/admin/predict-win/merchant-campaigns/pending")
async def admin_pending_queue(request: Request,
                                                                            limit: int = Query(50, ge=1, le=200),
                                                                            offset: int = Query(0, ge=0),
                                                                            admin: dict = Depends(require_admin)):
    db = request.app.state.db
    q = {"approval_status": "pending_admin"}
    total = await db.merchant_predict_win_campaigns.count_documents(q)
    items = []
    from services.predict_win_merchant_service import _strip
    async for d in db.merchant_predict_win_campaigns.find(q) \
                                                                                                                  .sort("updated_at", 1) \
                                                                                                                  .skip(offset).limit(limit):
        items.append(_strip(d))
    return {"items": items, "total": total}


@router.post("/api/admin/predict-win/merchant-campaigns/{campaign_id}/approve")
async def admin_approve(campaign_id: str, request: Request,
                                                    admin: dict = Depends(require_admin)):
    try:
        c = await merchant_svc.admin_approve(
            request.app.state.db, campaign_id=campaign_id,
            admin_user_id=admin["user_id"])
        return {"ok": True, "campaign": c}
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/api/admin/predict-win/merchant-campaigns/{campaign_id}/reject")
async def admin_reject(campaign_id: str, body: RejectIn, request: Request,
                                                  admin: dict = Depends(require_admin)):
    try:
        c = await merchant_svc.admin_reject(
            request.app.state.db, campaign_id=campaign_id,
            admin_user_id=admin["user_id"], reason=body.reason)
        return {"ok": True, "campaign": c}
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@router.post("/api/admin/predict-win/merchant-campaigns/{campaign_id}/pause")
async def admin_pause(campaign_id: str, request: Request,
                                                admin: dict = Depends(require_admin)):
    try:
        c = await merchant_svc.pause_merchant_campaign(
            request.app.state.db, campaign_id=campaign_id, by_admin=True)
        return {"ok": True, "campaign": c}
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


class AutoPublishIn(BaseModel):
    auto_publish_predict_win: bool


@router.patch("/api/admin/predict-win/businesses/{merchant_id}/auto-publish-predict-win")
async def admin_toggle_auto_publish(merchant_id: str, body: AutoPublishIn,
                                                                                          request: Request,
                                                                                          admin: dict = Depends(require_admin)):
    db = request.app.state.db
    biz = await db.businesses.find_one(
        {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]})
    if not biz:
        raise HTTPException(404, {"code": "business_not_found"})
    from datetime import datetime, timezone
    await db.businesses.update_one(
        {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]},
        {"$set": {"auto_publish_predict_win": bool(body.auto_publish_predict_win),
                              "auto_publish_predict_win_updated_by": admin["user_id"],
                              "auto_publish_predict_win_updated_at":
                                  datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "merchant_id": merchant_id,
                        "auto_publish_predict_win": bool(body.auto_publish_predict_win)}


# Admin manual cascade trigger — used when a parent resolves via a
# non-sweeper path (`force-resolve`, manual admin action) or as an
# idempotent replay after a sweep error.
@router.post("/api/admin/predict-win/parent-campaigns/{parent_id}/cascade-to-merchants")
async def admin_cascade(parent_id: str, request: Request,
                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    resolution = await db.predict_win_resolutions.find_one(
        {"campaign_id": parent_id})
    if not resolution:
        raise HTTPException(409, {"code": "parent_not_resolved"})
    from services.predict_win_merchant_service import (
        resolve_and_award_children)
    report = await resolve_and_award_children(
        db, parent_campaign_id=parent_id,
        winning_option_id=resolution["winning_option_id"])
    return {"ok": True, "report": report}
