"""Phase MER.4 — Shoppable Business Profile + Follow/Save + Reverse-modifiers refund endpoints.

Public endpoints:
    GET   /api/business/{slug_or_id}/profile

Consumer endpoints (auth required):
    POST  /api/business/{merchant_id}/follow
    POST  /api/business/{merchant_id}/unfollow
    POST  /api/business/{merchant_id}/save
    POST  /api/business/{merchant_id}/unsave
    GET   /api/me/followed-businesses
    GET   /api/me/saved-businesses

Admin/manager endpoints:
    POST  /api/admin/transactions/{tx_id}/reverse-modifiers
    POST  /api/admin/transactions/{tx_id}/refund-zero-charge
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional, require_admin
from services.business_profile_service import (
    build_profile, follow_merchant, unfollow_merchant, list_relations,
    ensure_mer4_profile_indexes,
)
from services.mer4_refund_reversal_service import (
    reverse_transaction_modifiers, refund_zero_charge, ReversalError,
)

logger = logging.getLogger("bigfm.mer4")
router = APIRouter(prefix="/api", tags=["mer4"])


# ─── Public business profile ────────────────────────────────────
@router.get("/business/{slug_or_id}/profile")
async def get_business_profile(slug_or_id: str, request: Request,
                                                              user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    profile = await build_profile(db, slug_or_id=slug_or_id, user=user)
    if not profile:
        raise HTTPException(404, {"code": "merchant_not_found"})
    return profile


# ─── Public purchase-link resolvers (used by /business/{slug} buy CTAs) ──
@router.get("/business/{merchant_id}/gift-card-purchase-link")
async def gc_purchase_link(merchant_id: str, request: Request,
                                                        sku_id: str = Query(...),
                                                        amount_cents: int = Query(..., ge=1)):
    """Find an ACTIVE `link_type=gift_card` payment link for this SKU
    at the requested amount.  Fallback: any link_type=gift_card link
    tied to this SKU (customer may see a different amount than they
    clicked, that's OK)."""
    db = request.app.state.db
    from services.business_profile_service import resolve_merchant
    biz = await resolve_merchant(db, merchant_id)
    if not biz:
        raise HTTPException(404, {"code": "merchant_not_found"})
    mid = biz.get("business_id") or str(biz.get("_id"))

    l = await db.merchant_payment_links.find_one({
        "merchant_id": mid,
        "link_type": "gift_card",
        "active": True,
        "gift_card_id": sku_id,
        "amount_cents": amount_cents})
    if not l:
        l = await db.merchant_payment_links.find_one({
            "merchant_id": mid, "link_type": "gift_card",
            "active": True, "gift_card_id": sku_id})
    if not l:
        raise HTTPException(404, {"code": "no_link_for_sku"})
    return {"link_id": l["link_id"], "token": l["token"],
                  "amount_cents": l.get("amount_cents"),
                  "currency": l.get("currency")}


@router.get("/business/{merchant_id}/meal-pack-purchase-link")
async def meal_purchase_link(merchant_id: str, request: Request,
                                                            sku_id: str = Query(...)):
    db = request.app.state.db
    from services.business_profile_service import resolve_merchant
    biz = await resolve_merchant(db, merchant_id)
    if not biz:
        raise HTTPException(404, {"code": "merchant_not_found"})
    mid = biz.get("business_id") or str(biz.get("_id"))
    l = await db.merchant_payment_links.find_one({
        "merchant_id": mid, "link_type": "prepaid_meal",
        "active": True, "prepaid_meal_id": sku_id})
    if not l:
        raise HTTPException(404, {"code": "no_link_for_sku"})
    return {"link_id": l["link_id"], "token": l["token"],
                  "amount_cents": l.get("amount_cents"),
                  "currency": l.get("currency")}


# ─── Follow / save ──────────────────────────────────────────────
@router.post("/business/{merchant_id}/follow")
async def follow(merchant_id: str, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await follow_merchant(db, user=user, merchant_id=merchant_id,
                                                                        kind="follow")
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return {"followed": True, **result}


@router.post("/business/{merchant_id}/unfollow")
async def unfollow(merchant_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await unfollow_merchant(db, user=user, merchant_id=merchant_id,
                                                                          kind="follow")
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return {"followed": False, **result}


@router.post("/business/{merchant_id}/save")
async def save(merchant_id: str, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await follow_merchant(db, user=user, merchant_id=merchant_id,
                                                                        kind="save")
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return {"saved": True, **result}


@router.post("/business/{merchant_id}/unsave")
async def unsave(merchant_id: str, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await unfollow_merchant(db, user=user, merchant_id=merchant_id,
                                                                          kind="save")
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return {"saved": False, **result}


@router.get("/me/followed-businesses")
async def my_follows(request: Request,
                                        limit: int = Query(100, ge=1, le=500),
                                        offset: int = Query(0, ge=0),
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    return await list_relations(db, user=user, kind="follow",
                                                          limit=limit, offset=offset)


@router.get("/me/saved-businesses")
async def my_saves(request: Request,
                                    limit: int = Query(100, ge=1, le=500),
                                    offset: int = Query(0, ge=0),
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    return await list_relations(db, user=user, kind="save",
                                                          limit=limit, offset=offset)


# ─── Admin: reverse-modifiers ──────────────────────────────────
class ReverseBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=600)


@router.post("/admin/transactions/{transaction_id}/reverse-modifiers")
async def admin_reverse_modifiers(transaction_id: str, body: ReverseBody,
                                                                    request: Request,
                                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        result = await reverse_transaction_modifiers(
            db, transaction_id=transaction_id,
            actor={"user_id": admin.get("user_id"), "role": "admin"},
            note=body.note, triggered_by="manual_admin")
    except ReversalError as re:
        raise HTTPException(re.http_status, {"code": re.code,
                                                                                  "detail": re.detail})
    return result


@router.post("/admin/transactions/{transaction_id}/refund-zero-charge")
async def admin_refund_zero_charge(transaction_id: str, body: ReverseBody,
                                                                        request: Request,
                                                                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        result = await refund_zero_charge(
            db, transaction_id=transaction_id,
            actor={"user_id": admin.get("user_id"), "role": "admin"},
            note=body.note or "Zero-charge refund")
    except ReversalError as re:
        raise HTTPException(re.http_status, {"code": re.code,
                                                                                  "detail": re.detail})
    return result


# ─── Bootstrap ───────────────────────────────────────────────────
async def ensure_mer4_indexes(db) -> None:
    await ensure_mer4_profile_indexes(db)


__all__ = ["router", "ensure_mer4_indexes"]
