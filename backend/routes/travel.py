"""FUUSIC Travel — curated travel-deals vertical under Shop.

Consumers browse / search / book curated deals (flights, hotels, packages,
experiences, cruises). Following the single "travel" topic surfaces recommended
deals in the social wall (see services/social_feed._travel_deals). Checkout
reuses the BigPoints demo flow. Admins manage the catalogue via /admin/deals.
Platform-agnostic (web + mobile)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user, require_admin

router = APIRouter(prefix="/api/travel", tags=["travel"])

DEAL_TYPES = ["flight", "hotel", "package", "experience", "cruise"]
TRAVEL_TOPIC = "travel"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _card(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "deal_id": d.get("deal_id"),
        "title": d.get("title"),
        "deal_type": d.get("deal_type"),
        "destination": d.get("destination"),
        "origin": d.get("origin"),
        "price_cents": int(d.get("price_cents") or 0),
        "strike_cents": d.get("strike_cents"),
        "bigpoints": int(d.get("bigpoints") or 0),
        "image_url": d.get("image_url"),
        "blurb": d.get("blurb"),
        "duration": d.get("duration"),
        "rating": d.get("rating"),
        "tags": d.get("tags") or [],
        "promoted": bool(d.get("promoted")),
    }


def _admin_doc(d: Dict[str, Any]) -> Dict[str, Any]:
    c = _card(d)
    c["active"] = bool(d.get("active", True))
    return c


# ----------------------------------------------------------------------------- consumer

@router.get("/deals")
async def list_deals(request: Request, q: Optional[str] = None,
                     type: Optional[str] = None, sort: str = "featured",
                     limit: int = 40):
    db = request.app.state.db
    query: Dict[str, Any] = {"active": True}
    if type and type in DEAL_TYPES:
        query["deal_type"] = type
    if q and q.strip():
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"title": rx}, {"destination": rx}, {"tags": rx}]
    rows = [_card(d) async for d in db.travel_deals.find(query).limit(200)]
    if sort == "price_low":
        rows.sort(key=lambda x: x["price_cents"])
    elif sort == "price_high":
        rows.sort(key=lambda x: x["price_cents"], reverse=True)
    elif sort == "rating":
        rows.sort(key=lambda x: (x.get("rating") or 0), reverse=True)
    else:  # featured — promoted first, then rating
        rows.sort(key=lambda x: (x["promoted"], x.get("rating") or 0), reverse=True)
    return {"items": rows[:max(1, min(limit, 100))], "types": DEAL_TYPES}


@router.get("/follow")
async def follow_status(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    doc = await db.category_follows.find_one(
        {"user_id": user["user_id"], "topic": TRAVEL_TOPIC})
    return {"following": bool(doc)}


@router.post("/follow")
async def follow(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.category_follows.update_one(
        {"user_id": user["user_id"], "topic": TRAVEL_TOPIC},
        {"$setOnInsert": {"user_id": user["user_id"], "topic": TRAVEL_TOPIC,
                          "created_at": _now()}}, upsert=True)
    return {"ok": True, "following": True}


@router.delete("/follow")
async def unfollow(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.category_follows.delete_one(
        {"user_id": user["user_id"], "topic": TRAVEL_TOPIC})
    return {"ok": True, "following": False}


@router.get("/orders")
async def my_orders(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    async for o in db.travel_orders.find(
            {"user_id": user["user_id"]}).sort("created_at", -1).limit(50):
        o.pop("_id", None)
        if isinstance(o.get("created_at"), datetime):
            o["created_at"] = o["created_at"].isoformat()
        out.append(o)
    return {"items": out}


@router.get("/deals/{deal_id}")
async def deal_detail(deal_id: str, request: Request):
    db = request.app.state.db
    d = await db.travel_deals.find_one({"deal_id": deal_id, "active": True})
    if not d:
        raise HTTPException(404, {"code": "deal_not_found"})
    return {"deal": _card(d)}


class BookBody(BaseModel):
    travelers: int = 1
    date: Optional[str] = None


@router.post("/deals/{deal_id}/book")
async def book_deal(deal_id: str, body: BookBody, request: Request,
                    user: dict = Depends(current_user)):
    """Demo BigPoints booking — records a confirmed order and rewards points."""
    db = request.app.state.db
    d = await db.travel_deals.find_one({"deal_id": deal_id, "active": True})
    if not d:
        raise HTTPException(404, {"code": "deal_not_found"})
    uid = user["user_id"]
    travelers = max(1, min(int(body.travelers or 1), 9))
    total_cents = int(d.get("price_cents") or 0) * travelers
    order_id = f"trip_{uuid.uuid4().hex[:12]}"
    confirmation = f"FU{uuid.uuid4().hex[:6].upper()}"
    await db.travel_orders.insert_one({
        "order_id": order_id, "user_id": uid, "deal_id": deal_id,
        "title": d.get("title"), "deal_type": d.get("deal_type"),
        "destination": d.get("destination"), "image_url": d.get("image_url"),
        "travelers": travelers, "total_cents": total_cents,
        "status": "confirmed", "payment": "bigpoints_demo",
        "confirmation": confirmation, "created_at": _now()})
    try:
        from services.points_service import PointsService
        svc = PointsService(db)
        await svc.award(user_id=uid, source="travel_booking", source_id=order_id,
                        delta=int(d.get("bigpoints") or 0),
                        idempotency_key=f"travel:{order_id}", enforce_caps=False,
                        metadata={"deal_id": deal_id, "title": d.get("title")})
    except Exception:
        pass
    return {"ok": True, "order_id": order_id, "confirmation": confirmation,
            "total_cents": total_cents, "status": "confirmed"}


# ------------------------------------------------------------------------------- admin

class DealBody(BaseModel):
    title: str
    deal_type: str
    destination: str
    origin: Optional[str] = None
    price_cents: int
    strike_cents: Optional[int] = None
    bigpoints: int = 0
    image_url: Optional[str] = None
    blurb: Optional[str] = None
    duration: Optional[str] = None
    rating: Optional[float] = None
    tags: List[str] = []
    promoted: bool = False
    active: bool = True


@router.get("/admin/deals")
async def admin_list(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    out = []
    async for d in db.travel_deals.find({}).sort("created_at", -1):
        out.append(_admin_doc(d))
    return {"items": out, "types": DEAL_TYPES}


@router.post("/admin/deals")
async def admin_create(body: DealBody, request: Request,
                       admin: dict = Depends(require_admin)):
    if body.deal_type not in DEAL_TYPES:
        raise HTTPException(400, {"code": "bad_type"})
    db = request.app.state.db
    doc = body.dict()
    doc.update({"deal_id": f"deal_{uuid.uuid4().hex[:12]}", "created_at": _now()})
    await db.travel_deals.insert_one(doc)
    return {"ok": True, "deal": _admin_doc(doc)}


@router.put("/admin/deals/{deal_id}")
async def admin_update(deal_id: str, body: DealBody, request: Request,
                       admin: dict = Depends(require_admin)):
    if body.deal_type not in DEAL_TYPES:
        raise HTTPException(400, {"code": "bad_type"})
    db = request.app.state.db
    r = await db.travel_deals.update_one({"deal_id": deal_id}, {"$set": body.dict()})
    if not r.matched_count:
        raise HTTPException(404, {"code": "deal_not_found"})
    d = await db.travel_deals.find_one({"deal_id": deal_id})
    return {"ok": True, "deal": _admin_doc(d)}


@router.delete("/admin/deals/{deal_id}")
async def admin_delete(deal_id: str, request: Request,
                       admin: dict = Depends(require_admin)):
    db = request.app.state.db
    await db.travel_deals.delete_one({"deal_id": deal_id})
    return {"ok": True}


# -------------------------------------------------------------------------------- seed

_IMG = {
    "bali": "https://images.unsplash.com/photo-1504814532849-cff240bbc503?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "maldives": "https://images.unsplash.com/photo-1691849233457-837d8e2f9da3?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "dubai": "https://images.pexels.com/photos/7974839/pexels-photo-7974839.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "santorini": "https://images.unsplash.com/photo-1561501900-3701fa6a0864?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "paris_sunset": "https://images.unsplash.com/photo-1583265266785-aab9e443ee68?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "airplane": "https://images.unsplash.com/photo-1543797414-a0c3ad076f7c?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "cruise_day": "https://images.unsplash.com/photo-1599640842225-85d111c60e6b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "cruise_sunset": "https://images.unsplash.com/photo-1554254648-2d58a1bc3fd5?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "safari": "https://images.unsplash.com/photo-1577971132997-c10be9372519?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "safari_sunset": "https://images.unsplash.com/photo-1516426122078-c23e76319801?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "paris_day": "https://images.unsplash.com/photo-1609971757431-439cf7b4141b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "beach_hotel": "https://images.unsplash.com/photo-1549294413-26f195200c16?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
}

_SEED: List[Dict[str, Any]] = [
    {"deal_id": "deal_bali_pkg", "title": "Bali Beach Escape — 5 Nights", "deal_type": "package",
     "destination": "Bali, Indonesia", "price_cents": 69900, "strike_cents": 99900, "bigpoints": 1200,
     "image_url": _IMG["bali"], "duration": "5 nights", "rating": 4.8, "promoted": True,
     "blurb": "Private pool villa, daily breakfast & airport transfers included.",
     "tags": ["beach", "villa", "all-inclusive"]},
    {"deal_id": "deal_maldives_pkg", "title": "Maldives Overwater Villa — 4 Nights", "deal_type": "package",
     "destination": "Maldives", "price_cents": 189900, "strike_cents": 249900, "bigpoints": 3000,
     "image_url": _IMG["maldives"], "duration": "4 nights", "rating": 4.9, "promoted": True,
     "blurb": "Overwater villa on a private island with half-board dining.",
     "tags": ["luxury", "overwater", "honeymoon"]},
    {"deal_id": "deal_dubai_hotel", "title": "5★ Dubai Marina Resort", "deal_type": "hotel",
     "destination": "Dubai, UAE", "price_cents": 24900, "strike_cents": 34900, "bigpoints": 600,
     "image_url": _IMG["dubai"], "duration": "per night", "rating": 4.7,
     "blurb": "Infinity pool, marina views and a world-class spa.",
     "tags": ["city", "pool", "spa"]},
    {"deal_id": "deal_santorini_hotel", "title": "Santorini Cliffside Suite", "deal_type": "hotel",
     "destination": "Santorini, Greece", "price_cents": 31900, "bigpoints": 700,
     "image_url": _IMG["santorini"], "duration": "per night", "rating": 4.8,
     "blurb": "Caldera-view suite with a private plunge pool.",
     "tags": ["sunset", "romantic"]},
    {"deal_id": "deal_paris_flight", "title": "Return Flights to Paris", "deal_type": "flight",
     "destination": "Paris, France", "origin": "Dubai", "price_cents": 42900, "strike_cents": 55900,
     "bigpoints": 800, "image_url": _IMG["paris_sunset"], "duration": "Round trip", "rating": 4.5,
     "promoted": True, "blurb": "Nonstop return fares with 23kg checked baggage.",
     "tags": ["city break", "nonstop"]},
    {"deal_id": "deal_tokyo_flight", "title": "Return Flights to Tokyo", "deal_type": "flight",
     "destination": "Tokyo, Japan", "origin": "Dubai", "price_cents": 58900, "bigpoints": 900,
     "image_url": _IMG["airplane"], "duration": "Round trip", "rating": 4.6,
     "blurb": "Great-value return fares to Haneda.", "tags": ["asia", "adventure"]},
    {"deal_id": "deal_med_cruise", "title": "7-Night Mediterranean Cruise", "deal_type": "cruise",
     "destination": "Mediterranean", "price_cents": 109900, "strike_cents": 139900, "bigpoints": 2000,
     "image_url": _IMG["cruise_day"], "duration": "7 nights", "rating": 4.7, "promoted": True,
     "blurb": "Rome, Barcelona & more — all meals and entertainment included.",
     "tags": ["cruise", "all-inclusive"]},
    {"deal_id": "deal_carib_cruise", "title": "Caribbean Island Cruise — 5 Nights", "deal_type": "cruise",
     "destination": "Caribbean", "price_cents": 89900, "bigpoints": 1600,
     "image_url": _IMG["cruise_sunset"], "duration": "5 nights", "rating": 4.6,
     "blurb": "Island-hop the Caribbean with a family-friendly ship.",
     "tags": ["islands", "family"]},
    {"deal_id": "deal_safari_exp", "title": "Serengeti Safari Adventure", "deal_type": "experience",
     "destination": "Tanzania", "price_cents": 149900, "bigpoints": 2600,
     "image_url": _IMG["safari"], "duration": "3 days", "rating": 4.9,
     "blurb": "Guided game drives with lodge stays in the Serengeti.",
     "tags": ["wildlife", "guided"]},
    {"deal_id": "deal_safari_sunset_exp", "title": "Sunset Game Drive & Lodge", "deal_type": "experience",
     "destination": "Masai Mara, Kenya", "price_cents": 79900, "bigpoints": 1400,
     "image_url": _IMG["safari_sunset"], "duration": "2 days", "rating": 4.7,
     "blurb": "Evening game drive, sundowners and an overnight lodge.",
     "tags": ["safari", "lodge"]},
    {"deal_id": "deal_paris_city_pkg", "title": "Paris City Break — 3 Nights", "deal_type": "package",
     "destination": "Paris, France", "price_cents": 54900, "bigpoints": 1000,
     "image_url": _IMG["paris_day"], "duration": "3 nights", "rating": 4.6,
     "blurb": "Central hotel, Seine cruise and a museum pass.",
     "tags": ["city", "museums"]},
    {"deal_id": "deal_zanzibar_hotel", "title": "Zanzibar Beachfront Hotel", "deal_type": "hotel",
     "destination": "Zanzibar, Tanzania", "price_cents": 18900, "bigpoints": 500,
     "image_url": _IMG["beach_hotel"], "duration": "per night", "rating": 4.5,
     "blurb": "Beachfront room steps from the turquoise shore.",
     "tags": ["beach", "value"]},
]


async def ensure_travel(db):
    """Idempotently seed curated demo deals + indexes on startup."""
    try:
        for s in _SEED:
            await db.travel_deals.update_one(
                {"deal_id": s["deal_id"]},
                {"$set": {**s, "active": True},
                 "$setOnInsert": {"created_at": _now()}},
                upsert=True)
        await db.category_follows.create_index([("user_id", 1), ("topic", 1)], unique=True)
        await db.travel_deals.create_index([("deal_type", 1)])
    except Exception:
        pass


__all__ = ["router", "ensure_travel", "TRAVEL_TOPIC", "DEAL_TYPES"]
