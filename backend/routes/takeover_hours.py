"""Phase L — M5 Radio Takeover Hour routes.

Three surfaces:
    * `/api/advertiser/{business_id}/takeover-hours/*` — create,
      submit, confirm-payment, list, detail, cancel.
    * `/api/admin/takeover-hours/*` — moderation queue.
    * `/api/takeovers/*` — listener runtime (current + ping +
      block-played).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import takeover_hour_service as svc

log = logging.getLogger("bigfm.m5_takeover_routes")

router = APIRouter(tags=["m5-takeover-hours"])


# ── Helpers ───────────────────────────────────────────────────────
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


def _conflict(e: Exception) -> HTTPException:
    return HTTPException(
        409, {"code": str(e).split(":", 1)[0] or "conflict",
              "detail": str(e)})


# ── Request bodies ────────────────────────────────────────────────
class ScriptBlock(BaseModel):
    block_index: int = Field(ge=0, le=3)
    script_text: str = ""


class BrandedOverlay(BaseModel):
    logo_url:    Optional[str] = None
    cta_url:     Optional[str] = None
    badge_color: Optional[str] = None


class DealRef(BaseModel):
    source_type: str
    source_id:   str


class BonusGiveaway(BaseModel):
    threshold_listen_seconds: int = 1200
    prize_type:  Optional[str] = None       # "bc" | "usd_voucher"
    prize_amount: int = 0
    max_winners: int = 0                    # 0 = unlimited


class CreateTakeoverBody(BaseModel):
    station_scope:   str                        # single|region|global
    station_id:      Optional[str] = None
    region_code:     Optional[str] = None
    start_at:        str
    end_at:          str
    rj_persona_id:   str
    rj_scripts:      List[ScriptBlock] = Field(default_factory=list)
    advertiser_name: str
    tagline:         Optional[str] = None
    overall_theme:   Optional[str] = None
    branded_overlay: Optional[BrandedOverlay] = None
    featured_deal_refs: List[DealRef] = Field(default_factory=list)
    bonus_giveaway:  Optional[BonusGiveaway] = None
    media_cost_cents: int = Field(ge=1, default=5000)
    listener_reach_estimate: int = 0


class CancelBody(BaseModel):
    reason: Optional[str] = None


class DecisionBody(BaseModel):
    admin_notes: Optional[str] = None


class PingBody(BaseModel):
    session_id:  str
    station_id:  Optional[str] = None
    ping_seconds: int = 30


class BlockPlayedBody(BaseModel):
    session_id:  str
    block_index: int = Field(ge=0, le=3)


# ── Advertiser ────────────────────────────────────────────────────
@router.post("/api/advertiser/{business_id}/takeover-hours")
async def create_takeover(business_id: str,
                          body: CreateTakeoverBody,
                          request: Request,
                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.create_takeover_hour(
            request.app.state.db,
            advertiser_business_id=business_id,
            body=body.model_dump(),
            created_by_user_id=user["user_id"])
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "takeover-hours/{takeover_id}/submit")
async def submit_takeover(business_id: str, takeover_id: str,
                          request: Request,
                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.submit_takeover_hour(
            request.app.state.db,
            takeover_id=takeover_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "takeover-hours/{takeover_id}/confirm-payment")
async def confirm_takeover_payment(business_id: str, takeover_id: str,
                                   request: Request,
                                   user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.confirm_payment(
            request.app.state.db,
            takeover_id=takeover_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.get("/api/advertiser/{business_id}/takeover-hours")
async def list_takeovers(business_id: str, request: Request,
                         status: Optional[str] = None,
                         limit: int = Query(100, ge=1, le=500),
                         user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    rows = await svc.list_takeover_hours(
        request.app.state.db,
        advertiser_business_id=business_id,
        status=status,
        limit=limit)
    return {"items": rows, "total": len(rows)}


@router.get("/api/advertiser/{business_id}/"
            "takeover-hours/{takeover_id}")
async def get_takeover(business_id: str, takeover_id: str,
                       request: Request,
                       user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.get_takeover_hour(
            request.app.state.db,
            takeover_id=takeover_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/"
             "takeover-hours/{takeover_id}/cancel")
async def cancel_takeover(business_id: str, takeover_id: str,
                          body: CancelBody,
                          request: Request,
                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.cancel_takeover_hour(
            request.app.state.db,
            takeover_id=takeover_id,
            advertiser_business_id=business_id,
            reason=(body.reason or "advertiser_cancelled"))
    except ValueError as e:
        if "cannot_cancel_live_takeover" in str(e):
            raise _conflict(e)
        raise _bad_request(e)


# ── Admin ─────────────────────────────────────────────────────────
@router.get("/api/admin/takeover-hours")
async def admin_list_takeovers(request: Request,
                               status: Optional[str] = None,
                               limit: int = Query(100, ge=1, le=500),
                               user: dict = Depends(require_admin)):
    rows = await svc.admin_list(
        request.app.state.db, status=status, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.post("/api/admin/takeover-hours/{takeover_id}/approve")
async def admin_approve_takeover(takeover_id: str,
                                 body: DecisionBody,
                                 request: Request,
                                 user: dict = Depends(require_admin)):
    try:
        return await svc.admin_approve(
            request.app.state.db,
            takeover_id=takeover_id,
            admin_user_id=user["user_id"],
            admin_notes=body.admin_notes)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/admin/takeover-hours/{takeover_id}/reject")
async def admin_reject_takeover(takeover_id: str,
                                body: DecisionBody,
                                request: Request,
                                user: dict = Depends(require_admin)):
    try:
        return await svc.admin_reject(
            request.app.state.db,
            takeover_id=takeover_id,
            admin_user_id=user["user_id"],
            admin_notes=(body.admin_notes or ""))
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/admin/takeover-hours/sweep")
async def admin_sweep_takeovers(request: Request,
                                user: dict = Depends(require_admin)):
    r = await svc.sweep_takeover_hours(request.app.state.db)
    return {"ok": True, "stats": r}


# ── Listener runtime ─────────────────────────────────────────────
@router.get("/api/takeovers/current")
async def takeovers_current(request: Request,
                            station_id: Optional[str] = None,
                            region_code: Optional[str] = None,
                            session_id: Optional[str] = None,
                            user: dict = Depends(current_user)):
    resp = await svc.get_current_takeover_response(
        request.app.state.db,
        station_id=station_id,
        region_code=region_code,
        user_id=user.get("user_id"),
        session_id=session_id)
    return {"takeover": resp}


@router.post("/api/takeovers/{takeover_id}/listener-ping")
async def takeovers_listener_ping(takeover_id: str,
                                  body: PingBody,
                                  request: Request,
                                  user: dict = Depends(current_user)):
    try:
        return await svc.listener_ping(
            request.app.state.db,
            takeover_id=takeover_id,
            user_id=user.get("user_id"),
            session_id=body.session_id,
            station_id=body.station_id,
            ping_seconds=body.ping_seconds)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/takeovers/{takeover_id}/block-played")
async def takeovers_block_played(takeover_id: str,
                                 body: BlockPlayedBody,
                                 request: Request,
                                 user: dict = Depends(current_user)):
    return await svc.record_block_played(
        request.app.state.db,
        takeover_id=takeover_id,
        session_id=body.session_id,
        block_index=body.block_index)


__all__ = ["router"]
