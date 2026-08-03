"""Phase E — AD.7.1 Split-the-bill HTTP routes.

Extends AD.7 scan-to-pay so one merchant bill can be split across 2-8
payers, each paying their own share on their own Stripe payment method.
See services/bill_split_service.py for the underlying mechanics.

Route surface (all under /api/scan-to-pay/splits/*):
- POST /api/scan-to-pay/splits                       — initiator creates split
- GET  /api/scan-to-pay/splits/mine                  — my splits (initiator OR participant)
- GET  /api/scan-to-pay/splits/{split_id}            — auth-gated detail
- POST /api/scan-to-pay/splits/{split_id}/cancel     — initiator-only, refused if any share paid
- GET  /api/scan-to-pay/splits/by-token/{token}      — public read (PII-scrubbed)
- POST /api/scan-to-pay/splits/by-token/{token}/claim — auth'd claim
- POST /api/scan-to-pay/splits/shares/{share_id}/pay — auth'd pay-my-share
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services import bill_split_service as _svc

router = APIRouter(tags=["ad7.1-split-the-bill"])
logger = logging.getLogger("bigfm.ad7.split.routes")


# ─── Body models ────────────────────────────────────────────────
class ShareInput(BaseModel):
    share_amount_cents:  int = Field(..., ge=1)
    display_name:        Optional[str] = None


class SplitCreateBody(BaseModel):
    merchant_id:                str
    total_amount_cents:  int = Field(..., ge=1)
    shares:                          List[ShareInput] = Field(...,
                                                                                                    min_length=_svc.MIN_SHARES,
                                                                                                    max_length=_svc.MAX_SHARES)
    currency:                      Optional[str] = None
    description:                Optional[str] = None
    location_id:                Optional[str] = None
    qr_token:                      Optional[str] = None


class PayShareBody(BaseModel):
    payment_method_id:  Optional[str] = "pm_card_visa"


class CancelSplitBody(BaseModel):
    reason:  Optional[str] = None


# ─── CREATE ─────────────────────────────────────────────────────
@router.post("/api/scan-to-pay/splits")
async def create_split(body: SplitCreateBody, request: Request,
                                                user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    try:
        return await _svc.create_split(
            db,
            initiator_user_id=user["user_id"],
            body=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


# ─── LIST (mine) ────────────────────────────────────────────────
@router.get("/api/scan-to-pay/splits/mine")
async def list_mine(request: Request, status: Optional[str] = None,
                                        limit: int = 50,
                                        user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    items = await _svc.list_mine(
        db, user_id=user["user_id"], status=status, limit=limit)
    return {"items": items, "count": len(items)}


# ─── READ (auth-gated) ──────────────────────────────────────────
@router.get("/api/scan-to-pay/splits/{split_id}")
async def get_split(split_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    row = await _svc.get_split(db, split_id=split_id,
                                                          viewer_user_id=user["user_id"])
    if not row:
        raise HTTPException(404, {"code": "split_not_found"})
    if row.get("forbidden"):
        raise HTTPException(403, {"code": "not_authorized"})
    return row


# ─── CANCEL (initiator-only) ────────────────────────────────────
@router.post("/api/scan-to-pay/splits/{split_id}/cancel")
async def cancel_split(split_id: str, body: CancelSplitBody,
                                              request: Request,
                                              user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    try:
        return await _svc.cancel_split(
            db, split_id=split_id,
            initiator_user_id=user["user_id"],
            reason=body.reason)
    except ValueError as e:
        code = str(e)
        # `has_paid_shares` → 409, `initiator_only` → 403, others 400.
        if code == "has_paid_shares":
            raise HTTPException(409, {"code": code})
        if code == "initiator_only":
            raise HTTPException(403, {"code": code})
        if code == "split_not_found":
            raise HTTPException(404, {"code": code})
        raise HTTPException(400, {"code": code})


# ─── PUBLIC read by invite_token (PII-scrubbed) ─────────────────
@router.get("/api/scan-to-pay/splits/by-token/{invite_token}")
async def get_by_token(invite_token: str, request: Request,
                                              user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    row = await _svc.get_by_token(db, invite_token=invite_token)
    if not row:
        raise HTTPException(404, {"code": "share_not_found"})
    # Never leak initiator PII, other users' user_ids, or other shares'
    # invite tokens.  The service already scopes correctly, but we
    # defensively strip anyway.
    row["auth_required_to_pay"] = not bool(user)
    return row


# ─── CLAIM ──────────────────────────────────────────────────────
@router.post("/api/scan-to-pay/splits/by-token/{invite_token}/claim")
async def claim(invite_token: str, request: Request,
                              user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    try:
        return await _svc.claim_share(
            db, invite_token=invite_token, user_id=user["user_id"])
    except ValueError as e:
        code = str(e)
        if code == "share_taken":
            raise HTTPException(409, {"code": code})
        if code in ("share_not_found", "split_not_found"):
            raise HTTPException(404, {"code": code})
        if code.startswith("split_") or code.startswith("share_"):
            # e.g. split_expired, share_paid, share_cancelled → 410 Gone.
            raise HTTPException(410, {"code": code})
        raise HTTPException(400, {"code": code})


# ─── PAY MY SHARE ───────────────────────────────────────────────
@router.post("/api/scan-to-pay/splits/shares/{share_id}/pay")
async def pay_share(share_id: str, body: PayShareBody, request: Request,
                                        user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    try:
        return await _svc.pay_share(
            db, share_id=share_id, user_id=user["user_id"],
            payment_method_id=body.payment_method_id or "pm_card_visa")
    except ValueError as e:
        code = str(e)
        if code == "not_share_owner":
            raise HTTPException(403, {"code": code})
        if code == "share_not_found":
            raise HTTPException(404, {"code": code})
        if code.startswith("split_") or code.startswith("share_"):
            raise HTTPException(410, {"code": code})
        raise HTTPException(400, {"code": code})


__all__ = ["router"]
