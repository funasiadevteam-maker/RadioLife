"""Phase AD.7 — Scan-to-Pay HTTP routes.

10 endpoints total (see file docstring for the spec)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services import scan_to_pay_service as _svc

router = APIRouter(tags=["ad7-scan-to-pay"])
logger = logging.getLogger("bigfm.ad7.routes")


# ─── Body models ────────────────────────────────────────────────
class QrGenBody(BaseModel):
    merchant_id:  str
    amount_cents: int = Field(..., ge=1)
    location_id:  Optional[str] = None


class QuoteBody(BaseModel):
    qr_token:            str
    points_to_use:  int = 0
    tip_cents:          int = 0


class AuthorizeBody(BaseModel):
    qr_token:                          str
    points_to_use:                int = 0
    tip_cents:                        int = 0
    payment_method_id:        Optional[str] = None


class CaptureBody(BaseModel):
    transaction_id: str


class RefundBody(BaseModel):
    reason: Optional[str] = None


class MerchantSettingsPatch(BaseModel):
    enabled:                                          Optional[bool] = None
    points_per_dollar:                        Optional[int] = None
    min_scan_to_pay_amount_cents:  Optional[int] = None
    max_points_redemption_pct:        Optional[int] = None


# ─── Merchant RBAC helper ───────────────────────────────────────
async def _assert_merchant_authority(db, merchant_id: str,
                                                                                  user: dict) -> dict:
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    role = user.get("role")
    if role == "admin":
        return user
    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        raise HTTPException(404, {"code": "merchant_not_found"})
    owner = biz.get("owner_user_id")
    staff = [s.get("user_id") for s in (biz.get("staff_users") or [])]
    if user.get("user_id") in ([owner] + staff):
        return user
    raise HTTPException(403, {"code": "merchant_owner_or_staff_required"})


# ─── QR gen + resolve ───────────────────────────────────────────
@router.post("/api/merchant/scan-to-pay/qr/generate")
async def qr_generate(body: QrGenBody, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_merchant_authority(db, body.merchant_id, user)
    try:
        return await _svc.generate_qr(
            db,
            merchant_id=body.merchant_id,
            cashier_user_id=user["user_id"],
            amount_cents=body.amount_cents,
            location_id=body.location_id)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.get("/api/scan-to-pay/qr/{token}")
async def qr_resolve(token: str, request: Request,
                                          user: Optional[dict] = Depends(current_user)):
    db = request.app.state.db
    try:
        return await _svc.resolve_qr(
            db, token=token, user_id=(user or {}).get("user_id"))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


# ─── Quote ──────────────────────────────────────────────────────
@router.post("/api/scan-to-pay/quote")
async def quote_endpoint(body: QuoteBody, request: Request,
                                                  user: Optional[dict] = Depends(current_user)):
    db = request.app.state.db
    try:
        return await _svc.quote(
            db, token=body.qr_token,
            points_to_use=body.points_to_use,
            tip_cents=body.tip_cents,
            user_id=(user or {}).get("user_id"))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


# ─── Authorize + capture + refund ──────────────────────────────
@router.post("/api/scan-to-pay/authorize")
async def authorize_endpoint(body: AuthorizeBody, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    try:
        return await _svc.authorize(
            db, token=body.qr_token, user_id=user["user_id"],
            points_to_use=body.points_to_use,
            tip_cents=body.tip_cents,
            payment_method_id=body.payment_method_id)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/api/scan-to-pay/capture")
async def capture_endpoint(body: CaptureBody, request: Request,
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    try:
        return await _svc.capture(
            db, transaction_id=body.transaction_id,
            user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/api/scan-to-pay/{transaction_id}/refund")
async def refund_endpoint(transaction_id: str, body: RefundBody,
                                                    request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    # Only merchants/admins can trigger refunds.
    tx = await db.scan_to_pay_transactions.find_one(
        {"transaction_id": transaction_id})
    if not tx:
        raise HTTPException(404, {"code": "transaction_not_found"})
    if user.get("role") != "admin":
        await _assert_merchant_authority(db, tx["merchant_id"], user)
    try:
        return await _svc.refund(
            db, transaction_id=transaction_id,
            actor_role=user.get("role") or "merchant",
            reason=body.reason)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


# ─── History + analytics ────────────────────────────────────────
@router.get("/api/user/scan-to-pay/history")
async def user_history(request: Request, limit: int = 20,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    return await _svc.user_history(
        db, user_id=user["user_id"], limit=limit)


@router.get("/api/merchant/{merchant_id}/scan-to-pay/transactions")
async def merchant_txs(merchant_id: str, request: Request, limit: int = 50,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_merchant_authority(db, merchant_id, user)
    return await _svc.merchant_transactions(
        db, merchant_id=merchant_id, limit=limit)


@router.patch("/api/merchant/{merchant_id}/scan-to-pay/settings")
async def merchant_settings(merchant_id: str,
                                                            body: MerchantSettingsPatch,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_merchant_authority(db, merchant_id, user)
    try:
        return await _svc.update_merchant_settings(
            db, merchant_id=merchant_id,
            patch=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.get("/api/merchant/{merchant_id}/scan-to-pay/settings")
async def merchant_settings_get(merchant_id: str, request: Request,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_merchant_authority(db, merchant_id, user)
    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        raise HTTPException(404, {"code": "merchant_not_found"})
    return _svc._merchant_scan_settings(biz)


@router.get("/api/admin/scan-to-pay/analytics")
async def admin_analytics(request: Request,
                                                        user: dict = Depends(current_user)):
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "admin_required"})
    return await _svc.admin_analytics(request.app.state.db)


__all__ = ["router"]
