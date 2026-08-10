"""Marketplace Merchant Gift Cards (Phase E) — a venue sells its own branded
gift card. Reuses the shared `gift_card_products` + `gift_cards` collections
and the existing `/api/giftcards/purchase` flow (points or Stripe). The only
new surface is merchant CRUD of their own products + a consumer listing per
business. Cards minted carry the venue's `business_id`, so redemption is
venue-scoped (see `_pick_gift_card` in the order routers)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional

POINTS_PER_DOLLAR = 100  # 100 points == $1 (mirror of routes.gift_cards)

router = APIRouter(prefix="/api/merchant/marketplace/giftcards",
                   tags=["marketplace-giftcards"])
consumer_router = APIRouter(prefix="/api/shop", tags=["marketplace-giftcards-consumer"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


class GiftCardProductBody(BaseModel):
    denominations_cents: List[int] = Field(..., min_length=1, max_length=8)
    allow_points: bool = True
    allow_card: bool = True
    active: bool = True


def _validate_denoms(denoms: List[int]) -> List[int]:
    cleaned = sorted({int(d) for d in denoms if 100 <= int(d) <= 1_000_000})
    if not cleaned:
        raise HTTPException(400, {"code": "bad_denominations"})
    return cleaned


@router.get("")
async def list_products(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [_clean(x) async for x in db.gift_card_products.find(
        {"business_id": p["business_id"]}).sort("created_at", 1)]
    return {"items": items}


@router.post("/items")
async def create_product(body: GiftCardProductBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    denoms = _validate_denoms(body.denominations_cents)
    from services.marketplace import new_id
    pid = new_id("gcprod")
    doc = {"product_id": pid, "business_id": p["business_id"],
           "sponsor_name": p.get("public_name"), "category": p.get("category", "shop"),
           "denominations_cents": denoms, "points_per_dollar": POINTS_PER_DOLLAR,
           "allow_points": body.allow_points, "allow_card": body.allow_card,
           "active": body.active, "created_at": _now(), "updated_at": _now()}
    await db.gift_card_products.insert_one(dict(doc))
    return {"ok": True, "product": _clean(doc)}


@router.patch("/items/{product_id}")
async def update_product(product_id: str, body: GiftCardProductBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    denoms = _validate_denoms(body.denominations_cents)
    res = await db.gift_card_products.update_one(
        {"product_id": product_id, "business_id": p["business_id"]},
        {"$set": {"denominations_cents": denoms, "allow_points": body.allow_points,
                  "allow_card": body.allow_card, "active": body.active,
                  "sponsor_name": p.get("public_name"), "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "product_not_found"})
    x = await db.gift_card_products.find_one({"product_id": product_id})
    return {"ok": True, "product": _clean(x)}


@router.delete("/items/{product_id}")
async def delete_product(product_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.gift_card_products.delete_one(
        {"product_id": product_id, "business_id": p["business_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, {"code": "product_not_found"})
    return {"ok": True}


@consumer_router.get("/businesses/{business_id}/giftcards")
async def business_giftcards(business_id: str, request: Request,
                             user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1, "cover_urls": 1})
    if not p:
        raise HTTPException(404, {"code": "business_not_found"})
    items = [_clean(x) async for x in db.gift_card_products.find(
        {"business_id": business_id, "active": True}).sort("created_at", 1)]
    balance = 0
    if user:
        from services.points_service import PointsService
        balance = await PointsService(db).get_balance(user.get("user_id"))
    return {"business_id": business_id, "public_name": p.get("public_name"),
            "cover_url": (p.get("cover_urls") or [None])[0],
            "points_per_dollar": POINTS_PER_DOLLAR, "points_balance": balance,
            "items": items}


__all__ = ["router", "consumer_router"]
