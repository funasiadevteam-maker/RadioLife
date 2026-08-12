"""Promoted Specials — merchant-curated "Today's Specials".

A shop owner flags their own products / menu items as a special (optional
blurb + optional sale price). Active specials from approved, subscribed shops
surface in a "Today's Specials" row on the Shop home and via
GET /api/shop/specials. Self-serve merchandising — no ad spend required.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.marketplace import now, new_id

router = APIRouter(prefix="/api/merchant/marketplace/specials", tags=["marketplace-specials"])
consumer_router = APIRouter(prefix="/api/shop", tags=["marketplace-specials-consumer"])


async def ensure_specials_indexes(db) -> None:
    await db.marketplace_specials.create_index("special_id", unique=True)
    await db.marketplace_specials.create_index(
        [("business_id", 1), ("kind", 1), ("item_id", 1)], unique=True)
    await db.marketplace_specials.create_index([("active", 1)])


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(d)
    d.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


async def _item(db, kind: str, item_id: str, business_id: str) -> Optional[Dict[str, Any]]:
    if kind == "product":
        return await db.products.find_one({"product_id": item_id, "business_id": business_id})
    if kind == "menu":
        return await db.menu_items.find_one({"item_id": item_id, "business_id": business_id})
    return None


async def get_active_specials(db, market: Optional[str] = None, limit: int = 12) -> List[Dict[str, Any]]:
    """Enriched special cards for the Shop home / consumer feed."""
    out: List[Dict[str, Any]] = []
    async for sp in db.marketplace_specials.find({"active": True}).sort("updated_at", -1).limit(limit * 3):
        prof = await db.marketplace_profiles.find_one(
            {"business_id": sp["business_id"], "status": "approved", "subscription_active": True},
            {"public_name": 1, "market": 1, "sponsored": 1, "cover_urls": 1})
        if not prof:
            continue
        if market and prof.get("market") and prof.get("market") != market:
            continue
        it = await _item(db, sp["kind"], sp["item_id"], sp["business_id"])
        if not it or (sp["kind"] == "product" and not it.get("active", True)):
            continue
        price = int(it.get("price_cents", 0))
        out.append({
            "special_id": sp["special_id"], "business_id": sp["business_id"],
            "business_name": prof.get("public_name"), "kind": sp["kind"],
            "item_id": sp["item_id"], "name": it.get("name"),
            "blurb": sp.get("blurb"), "price_cents": price,
            "sale_price_cents": sp.get("sale_price_cents"),
            "image_url": it.get("image_url"), "sponsored": bool(prof.get("sponsored")),
        })
        if len(out) >= limit:
            break
    return out


# ───────────── Merchant ─────────────
@router.get("")
async def list_specials(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    biz = p["business_id"]
    specials = {s["item_id"]: _clean(s) async for s in
                db.marketplace_specials.find({"business_id": biz})}
    products = [{"kind": "product", "item_id": x["product_id"], "name": x.get("name"),
                 "price_cents": x.get("price_cents"), "image_url": x.get("image_url")}
                async for x in db.products.find({"business_id": biz, "active": True})]
    menu = [{"kind": "menu", "item_id": x["item_id"], "name": x.get("name"),
             "price_cents": x.get("price_cents"), "image_url": x.get("image_url")}
            async for x in db.menu_items.find({"business_id": biz})]
    return {"specials": list(specials.values()), "products": products, "menu": menu}


class SpecialBody(BaseModel):
    kind: str  # product | menu
    item_id: str
    blurb: Optional[str] = Field(None, max_length=120)
    sale_price_cents: Optional[int] = Field(None, ge=0)
    active: bool = True


@router.put("")
async def upsert_special(body: SpecialBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    if body.kind not in ("product", "menu"):
        raise HTTPException(400, {"code": "bad_kind"})
    it = await _item(db, body.kind, body.item_id, p["business_id"])
    if not it:
        raise HTTPException(404, {"code": "item_not_found"})
    existing = await db.marketplace_specials.find_one(
        {"business_id": p["business_id"], "kind": body.kind, "item_id": body.item_id})
    doc = {"business_id": p["business_id"], "kind": body.kind, "item_id": body.item_id,
           "blurb": body.blurb, "sale_price_cents": body.sale_price_cents,
           "active": body.active, "updated_at": now()}
    if existing:
        await db.marketplace_specials.update_one(
            {"special_id": existing["special_id"]}, {"$set": doc})
        sid = existing["special_id"]
    else:
        sid = new_id("sp")
        await db.marketplace_specials.insert_one(
            {"special_id": sid, "created_at": now(), **doc})
    s = await db.marketplace_specials.find_one({"special_id": sid})
    return {"ok": True, "special": _clean(s)}


@router.delete("/{special_id}")
async def delete_special(special_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    r = await db.marketplace_specials.delete_one(
        {"special_id": special_id, "business_id": p["business_id"]})
    if not r.deleted_count:
        raise HTTPException(404, {"code": "special_not_found"})
    return {"ok": True}


# ───────────── Consumer ─────────────
@consumer_router.get("/specials")
async def shop_specials(request: Request, market: Optional[str] = None, limit: int = 20):
    db = request.app.state.db
    return {"items": await get_active_specials(db, market, min(max(1, limit), 40))}


__all__ = ["router", "consumer_router", "ensure_specials_indexes", "get_active_specials"]
