"""Marketplace Consumer API — Shop Home, categories, and business listings.
Reads APPROVED marketplace profiles.  Platform-agnostic (mobile + web)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request

from auth import current_user_optional
from services.marketplace import resolve_point_cost_cents

router = APIRouter(prefix="/api/shop", tags=["shop"])


def _card(p: Dict[str, Any]) -> Dict[str, Any]:
    bp = p.get("bigpoints", {}) or {}
    return {
        "business_id": p.get("business_id"),
        "public_name": p.get("public_name"),
        "category": p.get("category"),
        "subcategory": p.get("subcategory"),
        "description": p.get("description"),
        "logo_url": p.get("logo_url"),
        "cover_url": (p.get("cover_urls") or [None])[0],
        "city": p.get("market"),
        "sells": p.get("sells", []),
        "default_bigpoints": bp.get("default_points", 0),
        "points_per_dollar": bp.get("points_per_dollar"),
        "rating": p.get("rating"),
        "featured": bool(p.get("featured")),
        "sponsored": bool(p.get("sponsored")),
    }


@router.get("/categories")
async def categories(request: Request):
    db = request.app.state.db
    out = []
    async for c in db.marketplace_categories.find({"active": True}).sort("name", 1):
        c.pop("_id", None)
        for k in ("created_at", "updated_at"):
            c.pop(k, None)
        out.append(c)
    return {"items": out}


@router.get("/businesses")
async def businesses(request: Request, category: Optional[str] = None,
                     market: Optional[str] = None, q: Optional[str] = None,
                     sort: str = "featured", limit: int = 40,
                     user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    query: Dict[str, Any] = {"status": "approved", "subscription_active": True}
    if category:
        query["category"] = category
    if market:
        query["market"] = market
    if q:
        query["public_name"] = {"$regex": q, "$options": "i"}
    items = [_card(p) async for p in db.marketplace_profiles.find(query).limit(max(1, min(limit, 100)))]
    if sort == "bigpoints":
        items.sort(key=lambda x: x.get("default_bigpoints", 0), reverse=True)
    elif sort == "rating":
        items.sort(key=lambda x: (x.get("rating") or 0), reverse=True)
    else:  # featured — sponsored/featured first
        items.sort(key=lambda x: (x.get("sponsored", False), x.get("featured", False),
                                  x.get("default_bigpoints", 0)), reverse=True)
    return {"items": items, "total": len(items)}


@router.get("/businesses/{business_id}")
async def business_detail(business_id: str, request: Request,
                          user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one({"business_id": business_id, "status": "approved",
                                                "subscription_active": True})
    if not p:
        from fastapi import HTTPException
        raise HTTPException(404, {"code": "business_not_found"})
    card = _card(p)
    card["locations"] = p.get("locations", [])
    card["phone"] = p.get("phone")
    card["website"] = p.get("website")
    card["cover_urls"] = p.get("cover_urls", [])
    card["has_menu"] = "menu" in (p.get("sells") or []) or bool(
        await db.menu_items.find_one({"business_id": business_id, "available": True}))
    card["has_giftcards"] = bool(
        await db.gift_card_products.find_one({"business_id": business_id, "active": True}))
    card["has_memberships"] = bool(
        await db.membership_plans.find_one({"business_id": business_id, "active": True}))
    card["has_packages"] = bool(
        await db.package_products.find_one({"business_id": business_id, "active": True}))
    card["has_events"] = bool(
        await db.events.find_one({"business_id": business_id, "active": True}))
    # Happy Hour live state for consumer.
    from services.marketplace import effective_points
    eff = effective_points(p)
    card["happy_hour"] = eff.get("happy_hour", False)
    card["points_multiplier"] = eff.get("multiplier", 1)
    # Ways to earn here
    bp = p.get("bigpoints", {}) or {}
    card["ways_to_earn"] = [
        {"label": "Order / Buy", "points": bp.get("default_points", 0), "icon": "bag-check"},
        {"label": "Check In", "points": 50, "icon": "location"},
        {"label": "Pay with RadioLife", "points": 50, "icon": "wallet"},
    ]
    return {"business": card}


@router.get("/home")
async def shop_home(request: Request, market: Optional[str] = None,
                    user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    mk = market or (user or {}).get("market")
    cats = []
    async for c in db.marketplace_categories.find({"active": True}).sort("name", 1).limit(12):
        cats.append({"key": c["key"], "name": c["name"], "icon": c.get("icon")})

    base: Dict[str, Any] = {"status": "approved", "subscription_active": True}
    if mk:
        base_market = {**base, "market": mk}
    else:
        base_market = base

    async def _list(q, sortfn=None, limit=10):
        out = [_card(p) async for p in db.marketplace_profiles.find(q).limit(limit)]
        if sortfn:
            out.sort(key=sortfn, reverse=True)
        return out

    recommended = await _list(base_market, lambda x: x.get("default_bigpoints", 0), 10)
    most_points = await _list(base, lambda x: x.get("default_bigpoints", 0), 10)
    food = await _list({**base, "category": "restaurant"}, None, 10)
    services = await _list({**base, "sells": "services"}, None, 10)
    featured = await _list({**base, "featured": True}, None, 10)

    return {
        "headline": "SHOP LOCAL. EARN BIGPOINTS.",
        "market": mk,
        "categories": cats,
        "filters": ["Nearby", "Open Now", "Top Rated", "Most BigPoints",
                    "Special Offers", "Available Today", "Book Now", "Pickup Today"],
        "sections": [
            {"key": "recommended", "title": "Recommended for You", "items": recommended},
            {"key": "earn_more", "title": "Earn More BigPoints", "items": most_points},
            {"key": "food", "title": "Food Ready for Pickup", "items": food},
            {"key": "services", "title": "Popular Services", "items": services},
            {"key": "featured", "title": "Featured Businesses", "items": featured},
        ],
    }


@router.get("/businesses/{business_id}/menu")
async def business_menu(business_id: str, request: Request,
                        user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1, "cover_urls": 1, "bigpoints": 1, "happy_hour": 1})
    if not p:
        from fastapi import HTTPException
        raise HTTPException(404, {"code": "business_not_found"})
    from services.marketplace import effective_points
    eff = effective_points(p)
    sections: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    async for it in db.menu_items.find(
            {"business_id": business_id, "available": True}).sort("sort", 1):
        sec = it.get("section") or "Menu"
        if sec not in sections:
            sections[sec] = []
            order.append(sec)
        sections[sec].append({
            "item_id": it["item_id"], "name": it.get("name"),
            "description": it.get("description"), "price_cents": it.get("price_cents", 0),
            "image_url": it.get("image_url"), "bigpoints": it.get("bigpoints"),
        })
    return {
        "business_id": business_id,
        "public_name": p.get("public_name"),
        "cover_url": (p.get("cover_urls") or [None])[0],
        "default_bigpoints": (p.get("bigpoints") or {}).get("default_points", 0),
        "happy_hour": eff.get("happy_hour", False),
        "points_multiplier": eff.get("multiplier", 1),
        "sections": [{"title": s, "items": sections[s]} for s in order],
    }


__all__ = ["router"]
