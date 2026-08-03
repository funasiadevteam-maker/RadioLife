"""Phase F — Monetization M4: Boosted Flagship Slots — HTTP routes.

Admin creates auction slots + approves winners; advertisers bid;
listener runtime consumes live activations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services import flagship_boost_service as _svc

router = APIRouter(tags=["m4-flagship-boosts"])
logger = logging.getLogger("bigfm.flagship_boost.routes")


# ── Guards ─────────────────────────────────────────────────────
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


# ── Body models ────────────────────────────────────────────────
class CreateSlotBody(BaseModel):
    region_code:                str = Field(..., min_length=1)
    station_slot:            str
    start_at:                    datetime
    end_at:                        datetime
    floor_price_cents:  int = Field(..., ge=1)
    currency:                    Optional[str] = "usd"
    notes:                          Optional[str] = None


class PatchSlotBody(BaseModel):
    region_code:                Optional[str] = None
    station_slot:            Optional[str] = None
    start_at:                    Optional[datetime] = None
    end_at:                        Optional[datetime] = None
    floor_price_cents:  Optional[int] = None
    currency:                    Optional[str] = None
    notes:                          Optional[str] = None


class ApproveBidBody(BaseModel):
    decision_note:  Optional[str] = None


class RejectBidBody(BaseModel):
    decision_note:  Optional[str] = None


class CreativeBody(BaseModel):
    station_id_to_promote:  str
    display_headline:            str = Field(..., min_length=2, max_length=120)
    subtext:                              Optional[str] = None
    badge_color:                      Optional[str] = "orange"


class SubmitBidBody(BaseModel):
    bid_amount_cents:  int = Field(..., ge=1)
    creative:                    CreativeBody


class ImpressionBody(BaseModel):
    pass  # activation_id is in the path


# ═══════════════════════════════════════════════════════════════
# ADMIN routes — /api/admin/flagship-boosts/*
# ═══════════════════════════════════════════════════════════════
@router.post("/api/admin/flagship-boosts/slots")
async def admin_create_slot(body: CreateSlotBody, request: Request,
                                                        user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.create_slot(
            db,
            region_code=body.region_code,
            station_slot=body.station_slot,
            start_at=body.start_at,
            end_at=body.end_at,
            floor_price_cents=body.floor_price_cents,
            currency=body.currency or "usd",
            notes=body.notes,
            admin_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.get("/api/admin/flagship-boosts/slots")
async def admin_list_slots(request: Request,
                                                      region_code: Optional[str] = None,
                                                      status: Optional[str] = None,
                                                      limit: int = 100,
                                                      user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    items = await _svc.list_slots(db, region_code=region_code,
                                                                    status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/admin/flagship-boosts/slots/{slot_id}")
async def admin_get_slot(slot_id: str, request: Request,
                                                  user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    row = await _svc.get_slot(db, slot_id=slot_id, viewer_admin=True)
    if not row:
        raise HTTPException(404, {"code": "slot_not_found"})
    return row


@router.patch("/api/admin/flagship-boosts/slots/{slot_id}")
async def admin_patch_slot(slot_id: str, body: PatchSlotBody,
                                                      request: Request,
                                                      user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.edit_slot(
            db, slot_id=slot_id,
            patch=body.model_dump(exclude_none=True),
            admin_user_id=user["user_id"])
    except ValueError as e:
        code = str(e)
        if code == "slot_not_found":
            raise HTTPException(404, {"code": code})
        if code == "slot_has_decisions":
            raise HTTPException(409, {"code": code})
        raise HTTPException(400, {"code": code})


@router.post("/api/admin/flagship-boosts/slots/{slot_id}/close")
async def admin_close_slot(slot_id: str, request: Request,
                                                      user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.close_slot(db, slot_id=slot_id,
                                                                  admin_user_id=user["user_id"])
    except ValueError as e:
        code = str(e)
        if code == "slot_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


@router.post("/api/admin/flagship-boosts/bids/{bid_id}/approve")
async def admin_approve_bid(bid_id: str, body: ApproveBidBody,
                                                        request: Request,
                                                        force: bool = Query(False),
                                                        user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.approve_bid(
            db, bid_id=bid_id,
            admin_user_id=user["user_id"],
            decision_note=body.decision_note,
            force=force)
    except ValueError as e:
        code = str(e)
        if code == "bid_not_found" or code == "slot_not_found":
            raise HTTPException(404, {"code": code})
        if code == "higher_pending_bid_exists":
            raise HTTPException(409, {"code": code})
        raise HTTPException(400, {"code": code})


@router.post("/api/admin/flagship-boosts/bids/{bid_id}/reject")
async def admin_reject_bid(bid_id: str, body: RejectBidBody,
                                                      request: Request,
                                                      user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.reject_bid(
            db, bid_id=bid_id,
            admin_user_id=user["user_id"],
            decision_note=body.decision_note)
    except ValueError as e:
        code = str(e)
        if code == "bid_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


# ═══════════════════════════════════════════════════════════════
# ADVERTISER routes — /api/advertiser/{business_id}/flagship-boosts/*
# ═══════════════════════════════════════════════════════════════
@router.get("/api/advertiser/{business_id}/flagship-boosts/available")
async def advertiser_list_available(business_id: str, request: Request,
                                                                        region_code: Optional[str] = None,
                                                                        limit: int = 100,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    items = await _svc.get_available_slots(
        db, advertiser_business_id=business_id,
        region_code=region_code, limit=limit)
    return {"items": items, "count": len(items)}


@router.post("/api/advertiser/{business_id}/flagship-boosts/slots/{slot_id}/bid")
async def advertiser_submit_bid(business_id: str, slot_id: str,
                                                                body: SubmitBidBody, request: Request,
                                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.submit_bid(
            db, slot_id=slot_id,
            advertiser_business_id=business_id,
            bid_amount_cents=body.bid_amount_cents,
            creative=body.creative.model_dump(),
            user_id=user["user_id"])
    except ValueError as e:
        code = str(e)
        if code == "slot_not_found":
            raise HTTPException(404, {"code": code})
        if code == "duplicate_active_bid":
            raise HTTPException(409, {"code": code})
        if code == "bid_below_floor":
            raise HTTPException(400, {"code": code})
        raise HTTPException(400, {"code": code})


@router.get("/api/advertiser/{business_id}/flagship-boosts/my-bids")
async def advertiser_list_bids(business_id: str, request: Request,
                                                              status: Optional[str] = None,
                                                              limit: int = 100,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    items = await _svc.list_my_bids(
        db, advertiser_business_id=business_id,
        status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.delete("/api/advertiser/{business_id}/flagship-boosts/bids/{bid_id}")
async def advertiser_withdraw_bid(business_id: str, bid_id: str,
                                                                  request: Request,
                                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.withdraw_bid(
            db, bid_id=bid_id, advertiser_business_id=business_id)
    except ValueError as e:
        code = str(e)
        if code == "bid_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_bid_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


@router.get("/api/advertiser/{business_id}/flagship-boosts/bids/{bid_id}/transparency")
async def advertiser_bid_transparency(business_id: str, bid_id: str,
                                                                            request: Request,
                                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.bid_transparency(
            db, bid_id=bid_id, advertiser_business_id=business_id)
    except ValueError as e:
        code = str(e)
        if code == "bid_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_bid_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


@router.get("/api/advertiser/{business_id}/flagship-boosts/activations")
async def advertiser_list_activations(business_id: str, request: Request,
                                                                              status: Optional[str] = None,
                                                                              limit: int = 100,
                                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    items = await _svc.list_activations(
        db, advertiser_business_id=business_id,
        status=status, limit=limit)
    return {"items": items, "count": len(items)}


# ═══════════════════════════════════════════════════════════════
# PUBLIC / LISTENER — /api/flagship/boosts/*
# ═══════════════════════════════════════════════════════════════
@router.get("/api/flagship/boosts/active")
async def public_active_boosts(request: Request,
                                                              region_code: str = Query(..., min_length=1)):
    db = request.app.state.db
    items = await _svc.get_live_boosts_for_region(
        db, region_code=region_code)
    return {"region_code": (region_code or "").strip().lower(),
                    "items": items, "count": len(items)}


@router.post("/api/flagship/boosts/{activation_id}/impression")
async def public_record_impression(activation_id: str, request: Request,
                                                                        user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    try:
        return await _svc.record_impression(
            db, activation_id=activation_id,
            user_id=(user or {}).get("user_id"))
    except ValueError as e:
        code = str(e)
        if code == "activation_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


__all__ = ["router"]
