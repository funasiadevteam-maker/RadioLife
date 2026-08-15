"""Marketplace Consumer API — Shop Home, categories, and business listings.
Reads APPROVED marketplace profiles.  Platform-agnostic (mobile + web)."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user, current_user_optional
from services.marketplace import resolve_point_cost_cents, ranking_score

router = APIRouter(prefix="/api/shop", tags=["shop"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(r * 2 * math.asin(math.sqrt(a)), 2)


def _card(p: Dict[str, Any]) -> Dict[str, Any]:
    bp = p.get("bigpoints", {}) or {}
    geo = p.get("geo") or {}
    pu = p.get("promoted_until")
    promoted = bool(pu and str(pu) > _now_iso())
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
        "promoted": promoted,
        "promotion_weight": int(p.get("promotion_weight") or 0) if promoted else 0,
        "geo": {"lat": geo.get("lat"), "lng": geo.get("lng"),
                "address": geo.get("address")} if (geo.get("lat") is not None) else None,
        "delivery_enabled": bool((p.get("delivery") or {}).get("enabled")),
        "prep_time_min": int(p.get("prep_time_min", 20) or 20),
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
                     lat: Optional[float] = None, lng: Optional[float] = None,
                     user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    query: Dict[str, Any] = {"status": "approved", "subscription_active": True}
    if category:
        query["category"] = category
    if market:
        query["market"] = market
    if q:
        query["public_name"] = {"$regex": q, "$options": "i"}
    want = max(1, min(limit, 100))
    # Fetch a wide pool first so post-sort truncation (nearby / bigpoints / rating)
    # doesn't drop the best matches before ranking.
    items = [_card(p) async for p in db.marketplace_profiles.find(query).limit(200)]
    # Attach distance when the caller shares a location.
    if lat is not None and lng is not None:
        for it in items:
            g = it.get("geo")
            it["distance_km"] = _haversine_km(lat, lng, g["lat"], g["lng"]) if g else None
    if sort == "nearby" and lat is not None and lng is not None:
        items.sort(key=lambda x: (x.get("distance_km") is None,
                                  x["distance_km"] if x.get("distance_km") is not None else 1e9))
    elif sort == "bigpoints":
        items.sort(key=lambda x: x.get("default_bigpoints", 0), reverse=True)
    elif sort == "rating":
        items.sort(key=lambda x: (x.get("rating") or 0), reverse=True)
    else:  # featured — sponsored/featured/points-per-dollar boost first
        items.sort(key=ranking_score, reverse=True)
    items = items[:want]
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
    card["service_fee"] = p.get("service_fee") or {"enabled": False, "percent": 0}
    card["delivery"] = p.get("delivery") or {"enabled": False, "fee_cents": 0,
                                             "eta_min": 30, "eta_max": 45, "min_order_cents": 0}
    card["has_menu"] = "menu" in (p.get("sells") or []) or bool(
        await db.menu_items.find_one({"business_id": business_id, "available": True}))
    card["has_giftcards"] = bool(
        await db.gift_card_products.find_one({"business_id": business_id, "active": True}))
    card["has_memberships"] = bool(
        await db.membership_plans.find_one({"business_id": business_id, "active": True}))
    card["has_packages"] = bool(
        await db.package_products.find_one({"business_id": business_id, "active": True}))
    card["has_products"] = "products" in (p.get("sells") or []) or bool(
        await db.products.find_one({"business_id": business_id, "active": True}))
    card["has_events"] = bool(
        await db.events.find_one({"business_id": business_id, "active": True}))
    card["note_presets"] = p.get("note_presets") or []
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

    recommended = await _list(base_market, ranking_score, 10)
    most_points = await _list(base, lambda x: x.get("default_bigpoints", 0), 10)
    food = await _list({**base, "category": "restaurant"}, None, 10)
    services = await _list({**base, "sells": "services"}, None, 10)
    featured = await _list({**base, "featured": True}, None, 10)

    # Promoted near you — active paid/comped promotions, highest tier first.
    promoted = await _list({**base_market, "promoted_until": {"$gt": _now_iso()}},
                           lambda x: x.get("promotion_weight", 0) * 1e6 + ranking_score(x), 12)

    from routes.marketplace_specials import get_active_specials
    specials = await get_active_specials(db, mk, 12)

    sections = []
    if promoted:
        sections.append({"key": "promoted", "title": "Promoted near you", "items": promoted})
    sections += [
        {"key": "recommended", "title": "Recommended for You", "items": recommended},
        {"key": "earn_more", "title": "Earn More BigPoints", "items": most_points},
        {"key": "food", "title": "Food Ready for Pickup", "items": food},
        {"key": "services", "title": "Popular Services", "items": services},
        {"key": "featured", "title": "Featured Businesses", "items": featured},
    ]

    return {
        "headline": "SHOP LOCAL. EARN BIGPOINTS.",
        "market": mk,
        "categories": cats,
        "filters": ["Nearby", "Open Now", "Top Rated", "Most BigPoints",
                    "Special Offers", "Available Today", "Book Now", "Pickup Today"],
        "specials": specials,
        "sections": sections,
    }


@router.get("/businesses/{business_id}/menu")
async def business_menu(business_id: str, request: Request,
                        user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1, "cover_urls": 1, "bigpoints": 1, "happy_hour": 1,
         "service_fee": 1, "delivery": 1, "prep_time_min": 1, "geo": 1})
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
            "option_groups": it.get("option_groups", []),
        })
    geo = p.get("geo") or {}
    return {
        "business_id": business_id,
        "public_name": p.get("public_name"),
        "cover_url": (p.get("cover_urls") or [None])[0],
        "default_bigpoints": (p.get("bigpoints") or {}).get("default_points", 0),
        "happy_hour": eff.get("happy_hour", False),
        "points_multiplier": eff.get("multiplier", 1),
        "service_fee": p.get("service_fee") or {"enabled": False, "percent": 0},
        "delivery": p.get("delivery") or {"enabled": False, "fee_cents": 0,
                                          "eta_min": 30, "eta_max": 45, "min_order_cents": 0},
        "prep_time_min": int(p.get("prep_time_min", 20) or 20),
        "geo": {"lat": geo.get("lat"), "lng": geo.get("lng"),
                "address": geo.get("address")} if (geo.get("lat") is not None) else None,
        "sections": [{"title": s, "items": sections[s]} for s in order],
    }


CHECKIN_POINTS = 50


@router.get("/businesses/{business_id}/combos")
async def business_combos(business_id: str, request: Request,
                          user: dict = Depends(current_user_optional)):
    """Active merchant-defined meal combos — powers the store-page combo nudge
    and badges. Honours happy-hour schedules via active_now."""
    from services.combos import combo_active_now
    db = request.app.state.db
    combos = []
    async for c in db.marketplace_combos.find({"business_id": business_id, "active": True}):
        combos.append({"combo_id": c.get("combo_id"), "name": c.get("name"),
                       "price_cents": c.get("price_cents", 0),
                       "requirements": c.get("requirements", []),
                       "schedule": c.get("schedule"),
                       "active_now": combo_active_now(c)})
    return {"combos": combos}


async def _usual_items(db, uid: str, business_id: str, limit: int = 4):
    agg: Dict[str, Dict[str, Any]] = {}
    async for o in db.marketplace_orders.find(
            {"user_id": uid, "business_id": business_id, "payment_status": "paid"}).sort("created_at", -1).limit(40):
        for li in (o.get("items") or []):
            iid = li.get("item_id")
            if not iid:
                continue
            e = agg.setdefault(iid, {"item_id": iid, "name": li.get("name"),
                                     "price_cents": li.get("price_cents"), "count": 0,
                                     "selected_options": li.get("selected_options") or [],
                                     "note": li.get("note")})
            e["count"] += int(li.get("qty", 1) or 1)
    ranked = sorted(agg.values(), key=lambda x: x["count"], reverse=True)[:limit]
    out = []
    for e in ranked:
        mi = await db.menu_items.find_one({"item_id": e["item_id"], "business_id": business_id, "available": True})
        if not mi:
            continue
        opts = e.get("selected_options") or []
        out.append({
            "item_id": e["item_id"], "name": e["name"], "price_cents": e["price_cents"],
            "image_url": mi.get("image_url"), "times_ordered": e["count"],
            "selected_option_ids": [op.get("option_id") for op in opts if op.get("option_id")],
            "option_summary": ", ".join([op.get("label") for op in opts if op.get("label")]) or None,
            "note": e.get("note"),
        })
    return out


@router.get("/usual")
async def my_usual_home(request: Request, user: dict = Depends(current_user)):
    """The shopper's go-to store + usual items — powers the Shop-home shortcut."""
    db = request.app.state.db
    uid = user.get("user_id")
    counts: Dict[str, int] = {}
    async for o in db.marketplace_orders.find(
            {"user_id": uid, "payment_status": "paid"}).sort("created_at", -1).limit(60):
        bid = o.get("business_id")
        if bid:
            counts[bid] = counts.get(bid, 0) + 1
    if not counts:
        return {"has_usual": False}
    top_biz = max(counts, key=counts.get)
    p = await db.marketplace_profiles.find_one({"business_id": top_biz})
    if not p or "menu" not in (p.get("sells") or []):
        # only menu stores support quick reorder
        menu_biz = [b for b in sorted(counts, key=counts.get, reverse=True)]
        p = None
        for b in menu_biz:
            cand = await db.marketplace_profiles.find_one({"business_id": b})
            if cand and ("menu" in (cand.get("sells") or []) or await db.menu_items.find_one({"business_id": b})):
                p = cand
                top_biz = b
                break
        if not p:
            return {"has_usual": False}
    items = await _usual_items(db, uid, top_biz)
    if not items:
        return {"has_usual": False}
    return {"has_usual": True, "business_id": top_biz,
            "business_name": p.get("public_name"), "items": items}


@router.get("/businesses/{business_id}/usual")
async def my_usual(business_id: str, request: Request, user: dict = Depends(current_user)):
    """Most-ordered items across the shopper's paid orders here — 'Get your usual?'."""
    db = request.app.state.db
    items = await _usual_items(db, user.get("user_id"), business_id)
    return {"has_usual": len(items) > 0, "items": items}


@router.post("/businesses/{business_id}/checkin")
async def checkin(business_id: str, request: Request, user: dict = Depends(current_user)):
    """Loyalty check-in — awards points once per day per business."""
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1})
    if not p:
        raise HTTPException(404, {"code": "business_not_found"})
    from datetime import datetime, timezone
    from services.points_service import PointsService
    uid = user.get("user_id")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    idem = f"checkin:{uid}:{business_id}:{day}"
    svc = PointsService(db)
    if await db.points_ledger.find_one({"idempotency_key": idem}):
        return {"ok": True, "already": True, "awarded": 0,
                "points_balance": await svc.get_balance(uid)}
    await svc.award(user_id=uid, source="venue_checkin", source_id=business_id,
                    delta=CHECKIN_POINTS, idempotency_key=idem, enforce_caps=False,
                    metadata={"business_id": business_id, "business_name": p.get("public_name")})
    return {"ok": True, "already": False, "awarded": CHECKIN_POINTS,
            "points_balance": await svc.get_balance(uid)}


__all__ = ["router"]
