"""QR Scan-to-Pay API — customer presents a QR, the shop scans it to charge.

Consumer endpoints under /api/shop/scanpay (create/poll/cancel token, report a
bypass). Merchant resolve/charge are owner-gated. Admin audit under
/api/admin/scanpay.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import scan_pay_service as svc

router = APIRouter(prefix="/api/shop/scanpay", tags=["scan-pay"])
admin_router = APIRouter(prefix="/api/admin/scanpay", tags=["scan-pay-admin"])


async def _my_business(db, user):
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


class TokenBody(BaseModel):
    method: str  # card | points
    amount_cents: int = Field(..., ge=1)
    payment_method_id: Optional[str] = None


@router.post("/token")
async def create_token(body: TokenBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await svc.create_token(db, user, method=body.method,
                                      amount_cents=body.amount_cents,
                                      payment_method_id=body.payment_method_id)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.get("/token/{token}/status")
async def token_status(token: str, request: Request, user: dict = Depends(current_user)):
    return await svc.token_status(request.app.state.db, user, token)


@router.post("/token/{token}/cancel")
async def cancel_token(token: str, request: Request, user: dict = Depends(current_user)):
    return await svc.cancel_token(request.app.state.db, user, token)


class TokenRef(BaseModel):
    token: str


@router.post("/resolve")
async def resolve(body: TokenRef, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _my_business(db, user)
    return await svc.resolve(db, biz, body.token.strip().upper())


@router.post("/charge")
async def charge(body: TokenRef, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _my_business(db, user)
    return await svc.charge(db, user, biz, body.token.strip().upper())


class BypassBody(BaseModel):
    business_id: Optional[str] = None
    business_name: Optional[str] = Field(None, max_length=120)
    amount_cents: Optional[int] = Field(None, ge=0)
    note: Optional[str] = Field(None, max_length=400)


@router.post("/report-bypass")
async def report_bypass(body: BypassBody, request: Request, user: dict = Depends(current_user)):
    return await svc.report_bypass(request.app.state.db, user,
                                   business_id=body.business_id,
                                   business_name=body.business_name,
                                   amount_cents=body.amount_cents, note=body.note)


@admin_router.get("/fraud-logs")
async def fraud_logs(request: Request, admin: dict = Depends(require_admin)):
    return await svc.admin_fraud_logs(request.app.state.db)


@admin_router.get("/charges")
async def charges(request: Request, admin: dict = Depends(require_admin)):
    return await svc.admin_charges(request.app.state.db)


__all__ = ["router", "admin_router"]
