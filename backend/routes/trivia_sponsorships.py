"""Phase H — AD.5 Trivia Sponsorship + Giveaway Redemption — HTTP routes.

Advertiser + admin CRUD on sponsorships, plus listener endpoints for
redemption ack.  Room binding happens directly inside the existing
`POST /api/trivia/rooms` (see `routes/trivia_room_routes.py` edits).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services import trivia_sponsorship_service as _svc

router = APIRouter(tags=["ad5-trivia-sponsorships"])
logger = logging.getLogger("bigfm.ad5.routes")


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
    adv = await db.advertisers_v2.find_one({"advertiser_id": business_id})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    owner = adv.get("owner_user_id")
    staff = [s.get("user_id") for s in (adv.get("staff_users") or [])]
    if user.get("user_id") not in ([owner] + staff):
        raise HTTPException(403, {"code": "advertiser_owner_only"})


# ── Body models ─────────────────────────────────────
class PrizeTier(BaseModel):
    rank:                int
    points_reward:  int = Field(..., ge=1)
    currency:          str = Field("bc")
    quantity:          int = Field(1, ge=1)


class CreateSponsorshipBody(BaseModel):
    sponsor_target_type:  str = Field(...)
    target_id:                        Optional[str] = None
    display_name:                str = Field(..., min_length=2, max_length=80)
    tagline:                          Optional[str] = None
    logo_url:                        Optional[str] = None
    prize_pool:                    List[PrizeTier] = Field(..., min_length=1)
    winner_selection:          str = Field("top_n")
    score_threshold:            Optional[int] = None
    start_at:                        datetime
    end_at:                            datetime


class CancelBody(BaseModel):
    reason:  Optional[str] = None


class DecisionBody(BaseModel):
    decision_note:  Optional[str] = None


class ClaimBody(BaseModel):
    pass


# ══════════════════════════════════════════════════════════════
# ADVERTISER routes
# ══════════════════════════════════════════════════════════════
@router.post("/api/advertiser/{business_id}/trivia-sponsorships")
async def adv_create(business_id: str, body: CreateSponsorshipBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.create_sponsorship(
            db,
            advertiser_business_id=business_id,
            body=body.model_dump(exclude_none=True),
            user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/api/advertiser/{business_id}/trivia-sponsorships/{sponsorship_id}/confirm-payment")
async def adv_confirm_payment(business_id: str, sponsorship_id: str,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.confirm_payment(
            db, sponsorship_id=sponsorship_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        code = str(e)
        if code == "sponsorship_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


@router.get("/api/advertiser/{business_id}/trivia-sponsorships")
async def adv_list(business_id: str, request: Request,
                                    status: Optional[str] = None, limit: int = 100,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    items = await _svc.list_sponsorships(
        db, advertiser_business_id=business_id,
        status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/advertiser/{business_id}/trivia-sponsorships/{sponsorship_id}")
async def adv_get(business_id: str, sponsorship_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    row = await _svc.get_sponsorship(
        db, sponsorship_id=sponsorship_id,
        advertiser_business_id=business_id)
    if not row:
        raise HTTPException(404, {"code": "sponsorship_not_found"})
    if row.get("forbidden"):
        raise HTTPException(403, {"code": "not_authorized"})
    return row


@router.get("/api/advertiser/{business_id}/trivia-sponsorships/{sponsorship_id}/awards")
async def adv_awards(business_id: str, sponsorship_id: str, request: Request,
                                          limit: int = 200,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    items = await _svc.list_awards_for_sponsorship(
        db, sponsorship_id=sponsorship_id, limit=limit)
    return {"items": items, "count": len(items)}


@router.post("/api/advertiser/{business_id}/trivia-sponsorships/{sponsorship_id}/cancel")
async def adv_cancel(business_id: str, sponsorship_id: str, body: CancelBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_advertiser_owner(db, business_id, user)
    try:
        return await _svc.cancel_sponsorship(
            db, sponsorship_id=sponsorship_id,
            advertiser_business_id=business_id,
            reason=body.reason)
    except ValueError as e:
        code = str(e)
        if code == "sponsorship_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


# ══════════════════════════════════════════════════════════════
# ADMIN routes
# ══════════════════════════════════════════════════════════════
@router.get("/api/admin/trivia-sponsorships")
async def admin_list(request: Request, status: Optional[str] = None,
                                        limit: int = 100,
                                        user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    items = await _svc.list_sponsorships(db, status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/admin/trivia-sponsorships/{sponsorship_id}")
async def admin_get(sponsorship_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    row = await _svc.get_sponsorship(
        db, sponsorship_id=sponsorship_id, is_admin=True)
    if not row:
        raise HTTPException(404, {"code": "sponsorship_not_found"})
    row["awards"] = await _svc.list_awards_for_sponsorship(
        db, sponsorship_id=sponsorship_id, limit=200)
    return row


@router.post("/api/admin/trivia-sponsorships/{sponsorship_id}/approve")
async def admin_approve(sponsorship_id: str, body: DecisionBody, request: Request,
                                              user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.admin_approve(
            db, sponsorship_id=sponsorship_id,
            admin_user_id=user["user_id"],
            decision_note=body.decision_note)
    except ValueError as e:
        code = str(e)
        if code == "sponsorship_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


@router.post("/api/admin/trivia-sponsorships/{sponsorship_id}/reject")
async def admin_reject(sponsorship_id: str, body: DecisionBody, request: Request,
                                            user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _svc.admin_reject(
            db, sponsorship_id=sponsorship_id,
            admin_user_id=user["user_id"],
            decision_note=body.decision_note)
    except ValueError as e:
        code = str(e)
        if code == "sponsorship_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


# ══════════════════════════════════════════════════════════════
# LISTENER — /api/user/trivia-prize-awards
# ══════════════════════════════════════════════════════════════
@router.get("/api/user/trivia-prize-awards")
async def user_awards(request: Request, limit: int = 50,
                                            user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    items = await _svc.list_awards_for_user(
        db, user_id=user["user_id"], limit=limit)
    return {"items": items, "count": len(items)}


@router.post("/api/user/trivia-prize-awards/{award_id}/claim")
async def user_claim(award_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    try:
        return await _svc.mark_award_claimed(
            db, award_id=award_id, user_id=user["user_id"])
    except ValueError as e:
        code = str(e)
        if code == "award_not_found":
            raise HTTPException(404, {"code": code})
        if code == "not_award_owner":
            raise HTTPException(403, {"code": code})
        raise HTTPException(400, {"code": code})


__all__ = ["router"]
