"""Marketplace coupons API — merchant self-serve discount codes.

Merchant CRUD under /api/merchant/marketplace/coupons (owner-gated) plus a
consumer validate endpoint under /api/shop/coupons/validate for live preview.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.marketplace import now, new_id
from services.marketplace_coupons import (compute_coupon_discount, norm_code,
                                          serialize_coupon)

router = APIRouter(prefix="/api/merchant/marketplace/coupons", tags=["marketplace-coupons"])
consumer_router = APIRouter(prefix="/api/shop/coupons", tags=["marketplace-coupons-consumer"])


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


def _parse_dt(v: Optional[str]):
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(400, {"code": "bad_date", "value": v})


class CouponBody(BaseModel):
    code: str = Field(..., min_length=2, max_length=24)
    type: str = Field("percent")  # percent | amount
    value: int = Field(..., ge=1)   # percent 1-100, or cents for amount
    min_spend_cents: int = Field(0, ge=0)
    max_discount_cents: Optional[int] = Field(None, ge=0)  # cap for percent
    usage_limit: Optional[int] = Field(None, ge=1)         # total redemptions
    per_user_limit: int = Field(1, ge=0)                   # 0 = unlimited per user
    active: bool = True
    starts_at: Optional[str] = None
    expires_at: Optional[str] = None

    def validated(self) -> Dict[str, Any]:
        if self.type not in ("percent", "amount"):
            raise HTTPException(400, {"code": "bad_type"})
        if self.type == "percent" and not (1 <= self.value <= 100):
            raise HTTPException(400, {"code": "percent_out_of_range"})
        return {
            "code": norm_code(self.code), "type": self.type, "value": int(self.value),
            "min_spend_cents": int(self.min_spend_cents),
            "max_discount_cents": int(self.max_discount_cents) if self.max_discount_cents else None,
            "usage_limit": int(self.usage_limit) if self.usage_limit else None,
            "per_user_limit": int(self.per_user_limit),
            "active": bool(self.active),
            "starts_at": _parse_dt(self.starts_at), "expires_at": _parse_dt(self.expires_at),
        }


@router.get("")
async def list_coupons(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [serialize_coupon(c) async for c in db.marketplace_coupons.find(
        {"business_id": p["business_id"]}).sort("created_at", -1)]
    return {"items": items}


@router.post("")
async def create_coupon(body: CouponBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    data = body.validated()
    existing = await db.marketplace_coupons.find_one(
        {"business_id": p["business_id"], "code": data["code"]})
    if existing:
        raise HTTPException(409, {"code": "code_exists"})
    doc = {"coupon_id": new_id("mc"), "business_id": p["business_id"],
           "used_count": 0, "created_at": now(), "updated_at": now(), **data}
    await db.marketplace_coupons.insert_one(dict(doc))
    return {"ok": True, "coupon": serialize_coupon(doc)}


@router.patch("/{coupon_id}")
async def update_coupon(coupon_id: str, body: CouponBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    c = await db.marketplace_coupons.find_one(
        {"coupon_id": coupon_id, "business_id": p["business_id"]})
    if not c:
        raise HTTPException(404, {"code": "coupon_not_found"})
    data = body.validated()
    # Guard the unique (business, code) index if the code changed.
    if data["code"] != c["code"]:
        dup = await db.marketplace_coupons.find_one(
            {"business_id": p["business_id"], "code": data["code"]})
        if dup:
            raise HTTPException(409, {"code": "code_exists"})
    data["updated_at"] = now()
    await db.marketplace_coupons.update_one({"coupon_id": coupon_id}, {"$set": data})
    c = await db.marketplace_coupons.find_one({"coupon_id": coupon_id})
    return {"ok": True, "coupon": serialize_coupon(c)}


@router.delete("/{coupon_id}")
async def delete_coupon(coupon_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    r = await db.marketplace_coupons.delete_one(
        {"coupon_id": coupon_id, "business_id": p["business_id"]})
    if not r.deleted_count:
        raise HTTPException(404, {"code": "coupon_not_found"})
    return {"ok": True}


class ValidateBody(BaseModel):
    business_id: str
    code: str
    subtotal_cents: int = Field(..., ge=0)


@consumer_router.post("/validate")
async def validate_coupon(body: ValidateBody, request: Request,
                          user: dict = Depends(current_user)):
    """Live preview of a coupon's discount for a given subtotal — no writes."""
    db = request.app.state.db
    disc, coupon, err = await compute_coupon_discount(
        db, business_id=body.business_id, code=body.code,
        user_id=user.get("user_id"), base_cents=body.subtotal_cents)
    if err:
        return {"ok": False, "error": err, "discount_cents": 0}
    return {"ok": True, "discount_cents": disc, "code": norm_code(body.code),
            "type": coupon.get("type"), "value": coupon.get("value")}


__all__ = ["router", "consumer_router"]
