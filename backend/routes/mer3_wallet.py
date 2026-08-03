"""Phase MER.3 — Wallet expansion + checkout modifiers endpoints.

Merchant SKUs (RBAC: can_create_links via merchant_rbac_service):
    POST   /api/merchant/{id}/gift-card-skus
    GET    /api/merchant/{id}/gift-card-skus
    PUT    /api/merchant/{id}/gift-card-skus/{sku_id}
    POST   /api/merchant/{id}/gift-card-skus/{sku_id}/deactivate
    POST   /api/merchant/{id}/prepaid-meal-skus
    GET    /api/merchant/{id}/prepaid-meal-skus
    PUT    /api/merchant/{id}/prepaid-meal-skus/{sku_id}
    POST   /api/merchant/{id}/prepaid-meal-skus/{sku_id}/deactivate

Consumer wallet (auth required):
    GET    /api/wallet/me

Checkout modifier preview + zero-charge (paired with SC.5):
    POST   /api/pay/{token}/modifiers/preview
    POST   /api/pay/{token}/zero-charge

Cashier scan/redeem (extends MER.2, RBAC: can_redeem_coupons):
    POST   /api/merchant/{id}/cashier/redeem-gift-card
    POST   /api/merchant/{id}/cashier/redeem-meal
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services.merchant_rbac_service import resolve_merchant_with_role
from services import gift_card_service as _gc
from services import prepaid_meal_service as _pm
from services import wallet_v2_service as _wv2
from services.payment_link_service import get_link_by_token, is_link_serving

logger = logging.getLogger("bigfm.mer3")
router = APIRouter(prefix="/api", tags=["mer3"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _sku_view(s: dict) -> dict:
    return {
        "sku_id":                                s.get("sku_id"),
        "merchant_id":                    s.get("merchant_id"),
        "name":                                    s.get("name"),
        "description":                    s.get("description"),
        "denominations":                s.get("denominations"),
        "custom_amount_allowed":  s.get("custom_amount_allowed"),
        "min_custom_cents":            s.get("min_custom_cents"),
        "max_custom_cents":            s.get("max_custom_cents"),
        "currency":                            s.get("currency"),
        "terms":                                s.get("terms"),
        "expires_days_after_purchase": s.get("expires_days_after_purchase"),
        "active":                              s.get("active"),
        "created_at":                      _iso(s.get("created_at")),
        "updated_at":                      _iso(s.get("updated_at")),
    }


def _pm_sku_view(s: dict) -> dict:
    return {
        "sku_id":                                s.get("sku_id"),
        "merchant_id":                    s.get("merchant_id"),
        "name":                                    s.get("name"),
        "description":                    s.get("description"),
        "meal_count":                      s.get("meal_count"),
        "total_price_cents":        s.get("total_price_cents"),
        "per_meal_value_cents":  s.get("per_meal_value_cents"),
        "currency":                            s.get("currency"),
        "terms":                                s.get("terms"),
        "expires_days":                  s.get("expires_days"),
        "active":                              s.get("active"),
        "created_at":                      _iso(s.get("created_at")),
        "updated_at":                      _iso(s.get("updated_at")),
    }


# ─── Bodies ──────────────────────────────────────────────────────
class GiftCardSKUCreate(BaseModel):
    name:                                          str = Field(min_length=1, max_length=140)
    description:                            Optional[str] = Field(default=None, max_length=600)
    denominations:                        Optional[list[int]] = None
    custom_amount_allowed:      Optional[bool] = False
    min_custom_cents:                Optional[int] = Field(default=None, ge=0)
    max_custom_cents:                Optional[int] = Field(default=None, ge=0)
    currency:                                  Optional[str] = "AED"
    terms:                                      Optional[str] = Field(default=None, max_length=2000)
    expires_days_after_purchase: Optional[int] = Field(default=365, ge=1, le=3650)


class GiftCardSKUPatch(BaseModel):
    name:                                          Optional[str] = None
    description:                            Optional[str] = None
    denominations:                        Optional[list[int]] = None
    custom_amount_allowed:      Optional[bool] = None
    min_custom_cents:                Optional[int] = None
    max_custom_cents:                Optional[int] = None
    terms:                                      Optional[str] = None
    expires_days_after_purchase: Optional[int] = None
    active:                                    Optional[bool] = None


class PrepaidMealSKUCreate(BaseModel):
    name:                                str = Field(min_length=1, max_length=140)
    description:                  Optional[str] = Field(default=None, max_length=600)
    meal_count:                    int = Field(ge=2, le=1000)
    total_price_cents:      int = Field(ge=1)
    currency:                        Optional[str] = "AED"
    terms:                            Optional[str] = Field(default=None, max_length=2000)
    expires_days:                Optional[int] = Field(default=90, ge=1, le=3650)


class PrepaidMealSKUPatch(BaseModel):
    name:                                Optional[str] = None
    description:                  Optional[str] = None
    meal_count:                    Optional[int] = None
    total_price_cents:      Optional[int] = None
    terms:                            Optional[str] = None
    expires_days:                Optional[int] = None
    active:                          Optional[bool] = None


class ModifierIn(BaseModel):
    type:                        str = Field(min_length=1, max_length=32)
    code_or_id:            Optional[str] = None
    amount_cents:      Optional[int] = None      # only used for `points`


class ModifiersPreviewBody(BaseModel):
    amount_cents:  Optional[int] = None
    modifiers:        list[ModifierIn] = Field(default_factory=list)


class ZeroChargeBody(BaseModel):
    amount_cents:      Optional[int] = None
    modifiers:            list[ModifierIn] = Field(default_factory=list)
    customer_email: Optional[str] = None


class RedeemGiftCardBody(BaseModel):
    code:                              str = Field(min_length=6, max_length=64)
    amount_cents_to_use: int = Field(ge=1)


class RedeemMealBody(BaseModel):
    code:      str = Field(min_length=6, max_length=64)
    count:  int = Field(default=1, ge=1, le=10)


# ─── Gift Card SKU endpoints ─────────────────────────────────────
@router.post("/merchant/{merchant_id}/gift-card-skus")
async def create_gc_sku(merchant_id: str, body: GiftCardSKUCreate,
                                                request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")
    try:
        doc = await _gc.create_sku(db, merchant_id=mid, actor=user,
                                                              **body.model_dump(exclude_none=False))
    except ValueError as ve:
        raise HTTPException(400, {"code": str(ve)})
    return _sku_view(doc)


@router.get("/merchant/{merchant_id}/gift-card-skus")
async def list_gc_skus(merchant_id: str, request: Request,
                                              active: Optional[bool] = Query(None),
                                              limit: int = Query(100, ge=1, le=500),
                                              offset: int = Query(0, ge=0),
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_view_analytics")
    mid = biz.get("business_id") or biz.get("_id")
    res = await _gc.list_skus(db, merchant_id=mid, active=active,
                                                        limit=limit, offset=offset)
    return {"total": res["total"], "limit": res["limit"], "offset": res["offset"],
                  "items": [_sku_view(s) for s in res["items"]]}


@router.put("/merchant/{merchant_id}/gift-card-skus/{sku_id}")
async def update_gc_sku(merchant_id: str, sku_id: str, body: GiftCardSKUPatch,
                                                request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()
                  if v is not None}
    try:
        doc = await _gc.update_sku(db, sku_id=sku_id, merchant_id=mid,
                                                              patch=patch, actor=user)
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return _sku_view(doc)


@router.post("/merchant/{merchant_id}/gift-card-skus/{sku_id}/deactivate")
async def deactivate_gc_sku(merchant_id: str, sku_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")
    try:
        doc = await _gc.update_sku(db, sku_id=sku_id, merchant_id=mid,
                                                              patch={"active": False}, actor=user)
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return _sku_view(doc)


# ─── Prepaid Meal SKU endpoints ──────────────────────────────────
@router.post("/merchant/{merchant_id}/prepaid-meal-skus")
async def create_pm_sku(merchant_id: str, body: PrepaidMealSKUCreate,
                                                request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")
    try:
        doc = await _pm.create_sku(db, merchant_id=mid, actor=user,
                                                              **body.model_dump(exclude_none=False))
    except ValueError as ve:
        raise HTTPException(400, {"code": str(ve)})
    return _pm_sku_view(doc)


@router.get("/merchant/{merchant_id}/prepaid-meal-skus")
async def list_pm_skus(merchant_id: str, request: Request,
                                              active: Optional[bool] = Query(None),
                                              limit: int = Query(100, ge=1, le=500),
                                              offset: int = Query(0, ge=0),
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_view_analytics")
    mid = biz.get("business_id") or biz.get("_id")
    res = await _pm.list_skus(db, merchant_id=mid, active=active,
                                                        limit=limit, offset=offset)
    return {"total": res["total"], "limit": res["limit"], "offset": res["offset"],
                  "items": [_pm_sku_view(s) for s in res["items"]]}


@router.put("/merchant/{merchant_id}/prepaid-meal-skus/{sku_id}")
async def update_pm_sku(merchant_id: str, sku_id: str, body: PrepaidMealSKUPatch,
                                                request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()
                  if v is not None}
    try:
        doc = await _pm.update_sku(db, sku_id=sku_id, merchant_id=mid,
                                                              patch=patch, actor=user)
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return _pm_sku_view(doc)


@router.post("/merchant/{merchant_id}/prepaid-meal-skus/{sku_id}/deactivate")
async def deactivate_pm_sku(merchant_id: str, sku_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")
    try:
        doc = await _pm.update_sku(db, sku_id=sku_id, merchant_id=mid,
                                                              patch={"active": False}, actor=user)
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return _pm_sku_view(doc)


# ─── Consumer wallet ────────────────────────────────────────────
@router.get("/wallet/me")
async def wallet_me(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    return await _wv2.list_user_wallet(db, user=user)


# ─── Checkout modifier preview ──────────────────────────────────
@router.post("/pay/{token}/modifiers/preview")
async def preview_modifiers_endpoint(token: str, body: ModifiersPreviewBody,
                                                                          request: Request,
                                                                          user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    link, biz = await get_link_by_token(db, token)
    if not link or not biz:
        raise HTTPException(404, "link_not_found")

    serving, reason = is_link_serving(link)
    if not serving:
        raise HTTPException(410, {"code": f"link_{reason}"})

    # Resolve amount — fixed link vs customer-enters
    fixed = link.get("amount_cents")
    amt = int(fixed) if fixed is not None else int(body.amount_cents or 0)
    if amt <= 0:
        raise HTTPException(400, {"code": "invalid_amount"})

    mid = biz.get("business_id") or biz.get("_id")
    modifiers_dicts = [m.model_dump() for m in body.modifiers]
    preview = await _wv2.preview_modifiers(
        db, merchant_id=mid, order_amount_cents=amt,
        modifiers=modifiers_dicts, user=user)
    preview["merchant_id"] = mid
    preview["link_id"] = link["link_id"]
    preview["currency"] = (link.get("currency") or "AED").upper()
    return preview


# ─── Zero-charge checkout ───────────────────────────────────────
@router.post("/pay/{token}/zero-charge")
async def zero_charge(token: str, body: ZeroChargeBody, request: Request,
                                        user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    link, biz = await get_link_by_token(db, token)
    if not link or not biz:
        raise HTTPException(404, "link_not_found")

    serving, reason = is_link_serving(link)
    if not serving:
        raise HTTPException(410, {"code": f"link_{reason}"})

    fixed = link.get("amount_cents")
    amt = int(fixed) if fixed is not None else int(body.amount_cents or 0)
    if amt <= 0:
        raise HTTPException(400, {"code": "invalid_amount"})

    mid = biz.get("business_id") or biz.get("_id")
    modifiers_dicts = [m.model_dump() for m in body.modifiers]
    preview = await _wv2.preview_modifiers(
        db, merchant_id=mid, order_amount_cents=amt,
        modifiers=modifiers_dicts, user=user)
    if not preview.get("zero_charge"):
        raise HTTPException(400, {"code": "not_zero_charge",
                                                          "stripe_charge_cents": preview["stripe_charge_cents"]})

    email = body.customer_email or (user or {}).get("email")
    result = await _wv2.zero_charge_transaction(
        db, token=token, link=link, biz=biz,
        amount_cents=amt, modifiers=preview.get("discounts") or [],
        customer_user_id=(user or {}).get("user_id"),
        customer_email=email)
    return {**result, "modifiers": preview.get("discounts")}


# ─── Cashier gift-card + meal redemption ────────────────────────
@router.post("/merchant/{merchant_id}/cashier/redeem-gift-card")
async def cashier_redeem_gc(merchant_id: str, body: RedeemGiftCardBody,
                                                          request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_redeem_coupons")
    mid = biz.get("business_id") or biz.get("_id")

    gc = await _gc.lookup_by_code(db, code=body.code)
    if not gc:
        raise HTTPException(404, {"code": "not_found"})
    if gc.get("merchant_id") != mid:
        raise HTTPException(400, {"code": "not_this_merchant"})
    if gc.get("status") != "active":
        raise HTTPException(400, {"code": gc.get("status")})

    try:
        result = await _gc.decrement_balance(
            db, gift_card_id=gc["gift_card_id"],
            amount_cents=body.amount_cents_to_use)
    except ValueError as ve:
        raise HTTPException(400, {"code": str(ve)})

    # Audit row in `merchant_redemptions` (mirrors MER.2 coupon redemption).
    # MER.2's unique index on `coupon_id` is non-sparse — use the
    # gift_card_id as a stand-in sentinel so unique-null doesn't collide.
    now = _now()
    red_id = f"rdgc_{uuid.uuid4().hex[:16]}"
    await db.merchant_redemptions.insert_one({
        "_id":                              red_id,
        "redemption_id":            red_id,
        "merchant_id":                mid,
        "staff_user_id":            user.get("user_id"),
        "staff_role":                  role,
        "type":                              "gift_card",
        "coupon_id":                    f"gcref_{gc['gift_card_id']}_{red_id}",
        "gift_card_id":              gc.get("gift_card_id"),
        "redemption_code":        gc.get("code"),
        "amount_saved_cents":  int(body.amount_cents_to_use),
        "customer_user_id":      gc.get("owner_user_id"),
        "redeemed_at":                now,
    })
    return {"ok":                                    True,
                  "redemption_id":            red_id,
                  "gift_card_id":              gc.get("gift_card_id"),
                  "code":                              gc.get("code"),
                  "amount_used_cents":  int(body.amount_cents_to_use),
                  "new_balance_cents":  int(result.get("current_balance_cents") or 0),
                  "status":                        result.get("status"),
                  "redeemed_at":                _iso(now)}


@router.post("/merchant/{merchant_id}/cashier/redeem-meal")
async def cashier_redeem_meal(merchant_id: str, body: RedeemMealBody,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_redeem_coupons")
    mid = biz.get("business_id") or biz.get("_id")

    pm = await _pm.lookup_by_code(db, code=body.code)
    if not pm:
        raise HTTPException(404, {"code": "not_found"})
    if pm.get("merchant_id") != mid:
        raise HTTPException(400, {"code": "not_this_merchant"})
    if pm.get("status") != "active":
        raise HTTPException(400, {"code": pm.get("status")})

    try:
        result = await _pm.decrement_meal(
            db, meal_pack_id=pm["meal_pack_id"], count=body.count)
    except ValueError as ve:
        raise HTTPException(400, {"code": str(ve)})

    now = _now()
    red_id = f"rdpm_{uuid.uuid4().hex[:16]}"
    await db.merchant_redemptions.insert_one({
        "_id":                              red_id,
        "redemption_id":            red_id,
        "merchant_id":                mid,
        "staff_user_id":            user.get("user_id"),
        "staff_role":                  role,
        "type":                              "prepaid_meal",
        "coupon_id":                    f"pmref_{pm['meal_pack_id']}_{red_id}",
        "meal_pack_id":              pm.get("meal_pack_id"),
        "redemption_code":        pm.get("code"),
        "meals_redeemed":          body.count,
        "amount_saved_cents":  int(pm.get("per_meal_value_cents") or 0) * body.count,
        "customer_user_id":      pm.get("owner_user_id"),
        "redeemed_at":                now,
    })
    return {"ok":                                    True,
                  "redemption_id":            red_id,
                  "meal_pack_id":              pm.get("meal_pack_id"),
                  "code":                              pm.get("code"),
                  "meals_redeemed":          body.count,
                  "remaining_meals":      int(result.get("remaining_meals") or 0),
                  "status":                        result.get("status"),
                  "redeemed_at":                _iso(now)}


# ─── Extended cashier scan (unified for coupon/GC/PM) ───────────
class UnifiedScanBody(BaseModel):
    code: str = Field(min_length=3, max_length=64)


@router.post("/merchant/{merchant_id}/cashier/scan-any")
async def cashier_scan_any(merchant_id: str, body: UnifiedScanBody,
                                                        request: Request,
                                                        user: dict = Depends(current_user)):
    """Auto-routes based on code prefix:
        BIGFM-GC-... → gift card preview
        BIGFM-PM-... → prepaid meal preview
        Anything else → coupon (uses existing MER.2 endpoint logic inline).
    """
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_redeem_coupons")
    mid = biz.get("business_id") or biz.get("_id")
    up = body.code.strip().upper()

    if up.startswith("BIGFM-GC-"):
        gc = await _gc.lookup_by_code(db, code=up)
        if not gc:
            return {"ok": False, "type": "gift_card", "reason": "not_found"}
        if gc.get("merchant_id") != mid:
            return {"ok": False, "type": "gift_card", "reason": "not_this_merchant"}
        if gc.get("status") != "active":
            return {"ok": False, "type": "gift_card", "reason": gc.get("status")}
        return {"ok": True, "type": "gift_card",
                      "gift_card_id":                gc.get("gift_card_id"),
                      "code":                                gc.get("code"),
                      "current_balance_cents":  int(gc.get("current_balance_cents") or 0),
                      "initial_balance_cents":  int(gc.get("initial_balance_cents") or 0),
                      "currency":                        gc.get("currency"),
                      "expires_at":                    _iso(gc.get("expires_at"))}

    if up.startswith("BIGFM-PM-"):
        pm = await _pm.lookup_by_code(db, code=up)
        if not pm:
            return {"ok": False, "type": "prepaid_meal", "reason": "not_found"}
        if pm.get("merchant_id") != mid:
            return {"ok": False, "type": "prepaid_meal", "reason": "not_this_merchant"}
        if pm.get("status") != "active":
            return {"ok": False, "type": "prepaid_meal", "reason": pm.get("status")}
        sku = None
        if pm.get("sku_id"):
            sku = await db.prepaid_meal_skus.find_one({"sku_id": pm["sku_id"]},
                                                                                                        {"name": 1})
        return {"ok": True, "type": "prepaid_meal",
                      "meal_pack_id":              pm.get("meal_pack_id"),
                      "code":                              pm.get("code"),
                      "sku_name":                    (sku or {}).get("name"),
                      "total_meals":              int(pm.get("total_meals") or 0),
                      "remaining_meals":      int(pm.get("remaining_meals") or 0),
                      "per_meal_value_cents": int(pm.get("per_meal_value_cents") or 0),
                      "expires_at":                _iso(pm.get("expires_at"))}

    # Fall through to coupon path (delegates to existing MER.2 logic)
    coupon = await db.coupons.find_one({"$or": [
        {"coupon_id": body.code.strip()},
        {"coupon_id": up},
        {"code": body.code.strip()},
        {"code": up},
    ]})
    if not coupon:
        return {"ok": False, "type": "coupon", "reason": "not_found"}
    # Phase AD.4 — advertiser-minted coupons carry `business_id` directly.
    ad4_scope = coupon.get("business_id") == mid
    offer = await db.offers.find_one({"offer_id": coupon.get("offer_id")}) if coupon.get("offer_id") else None
    mer2_scope = bool(offer and offer.get("business_id") == mid)
    if not (ad4_scope or mer2_scope):
        return {"ok": False, "type": "coupon", "reason": "not_this_merchant"}
    if coupon.get("status") == "redeemed":
        return {"ok": False, "type": "coupon", "reason": "already_redeemed",
                      "redeemed_at": _iso(coupon.get("redeemed_at"))}
    if coupon.get("status") == "revoked":
        return {"ok": False, "type": "coupon", "reason": "revoked"}
    return {"ok": True, "type": "coupon",
                  "coupon_id":                            coupon.get("coupon_id"),
                  "redemption_code":                coupon.get("code"),
                  "offer_id":                                (offer or {}).get("offer_id"),
                  "offer_title":                        (offer or {}).get("title") or coupon.get("title"),
                  "offer_discount_percent":  (offer or {}).get("discount_percent"),
                  "offer_type":                          (offer or {}).get("offer_type") or coupon.get("coupon_type"),
                  "source_type":                        coupon.get("source_type"),
                  "advertiser_id":                    coupon.get("advertiser_id"),
                  "ad_coupon_campaign_id":      coupon.get("ad_coupon_campaign_id"),
                  "retail_value_cents":            int((coupon.get("discount_value") or 0) * 100)
                                                                        if coupon.get("source_type") == "ad4_coupon_save" else None,
                  "value_currency":                  coupon.get("value_currency"),
                  "expires_at":                          _iso(coupon.get("expires_at"))}


# ─── Bootstrap ───────────────────────────────────────────────────
async def ensure_mer3_indexes(db) -> None:
    await _gc.ensure_gift_card_indexes(db)
    await _pm.ensure_prepaid_meal_indexes(db)
    await _wv2.ensure_wallet_v2_indexes(db)


__all__ = ["router", "ensure_mer3_indexes"]
