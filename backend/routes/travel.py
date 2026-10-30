"""FUUSIC Travel — curated travel-deals vertical under Shop.

Consumers browse / search / book curated deals (flights, hotels, packages,
experiences, cruises). Following the single "travel" topic surfaces recommended
deals in the social wall (see services/social_feed._travel_deals). Checkout
reuses the BigPoints demo flow. Admins manage the catalogue via /admin/deals.
Platform-agnostic (web + mobile)."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin

router = APIRouter(prefix="/api/travel", tags=["travel"])

DEAL_TYPES = ["flight", "hotel", "package", "experience", "cruise"]
TRAVEL_TOPIC = "travel"

# ---- Live "Trending routes" (Travelpayouts Data API) ----------------------
_TP_CITY_DIRECTIONS = "https://api.travelpayouts.com/v1/city-directions"
_WHEREAMI = "https://www.travelpayouts.com/whereami"
_TRENDING_TTL_H = 24
# Curated IATA → city map so the trending row stays recognisable (unknown
# codes are filtered out to keep the row clean).
IATA_NAMES: Dict[str, Dict[str, str]] = {
    "LON": {"city": "London", "country": "UK", "emoji": "🇬🇧"},
    "PAR": {"city": "Paris", "country": "France", "emoji": "🇫🇷"},
    "CDG": {"city": "Paris", "country": "France", "emoji": "🇫🇷"},
    "IST": {"city": "Istanbul", "country": "Türkiye", "emoji": "🇹🇷"},
    "MOW": {"city": "Moscow", "country": "Russia", "emoji": "🇷🇺"},
    "BKK": {"city": "Bangkok", "country": "Thailand", "emoji": "🇹🇭"},
    "SIN": {"city": "Singapore", "country": "Singapore", "emoji": "🇸🇬"},
    "KUL": {"city": "Kuala Lumpur", "country": "Malaysia", "emoji": "🇲🇾"},
    "DEL": {"city": "Delhi", "country": "India", "emoji": "🇮🇳"},
    "BOM": {"city": "Mumbai", "country": "India", "emoji": "🇮🇳"},
    "CMB": {"city": "Colombo", "country": "Sri Lanka", "emoji": "🇱🇰"},
    "MLE": {"city": "Maldives", "country": "Maldives", "emoji": "🏝️"},
    "KWI": {"city": "Kuwait City", "country": "Kuwait", "emoji": "🇰🇼"},
    "DOH": {"city": "Doha", "country": "Qatar", "emoji": "🇶🇦"},
    "RUH": {"city": "Riyadh", "country": "Saudi Arabia", "emoji": "🇸🇦"},
    "JED": {"city": "Jeddah", "country": "Saudi Arabia", "emoji": "🇸🇦"},
    "CAI": {"city": "Cairo", "country": "Egypt", "emoji": "🇪🇬"},
    "BEY": {"city": "Beirut", "country": "Lebanon", "emoji": "🇱🇧"},
    "AMM": {"city": "Amman", "country": "Jordan", "emoji": "🇯🇴"},
    "SLL": {"city": "Salalah", "country": "Oman", "emoji": "🇴🇲"},
    "MCT": {"city": "Muscat", "country": "Oman", "emoji": "🇴🇲"},
    "TAS": {"city": "Tashkent", "country": "Uzbekistan", "emoji": "🇺🇿"},
    "TBS": {"city": "Tbilisi", "country": "Georgia", "emoji": "🇬🇪"},
    "EVN": {"city": "Yerevan", "country": "Armenia", "emoji": "🇦🇲"},
    "BAK": {"city": "Baku", "country": "Azerbaijan", "emoji": "🇦🇿"},
    "AUH": {"city": "Abu Dhabi", "country": "UAE", "emoji": "🇦🇪"},
    "DXB": {"city": "Dubai", "country": "UAE", "emoji": "🇦🇪"},
    "JFK": {"city": "New York", "country": "USA", "emoji": "🇺🇸"},
    "LAX": {"city": "Los Angeles", "country": "USA", "emoji": "🇺🇸"},
    "NYC": {"city": "New York", "country": "USA", "emoji": "🇺🇸"},
    "BCN": {"city": "Barcelona", "country": "Spain", "emoji": "🇪🇸"},
    "MAD": {"city": "Madrid", "country": "Spain", "emoji": "🇪🇸"},
    "ROM": {"city": "Rome", "country": "Italy", "emoji": "🇮🇹"},
    "FCO": {"city": "Rome", "country": "Italy", "emoji": "🇮🇹"},
    "MIL": {"city": "Milan", "country": "Italy", "emoji": "🇮🇹"},
    "AMS": {"city": "Amsterdam", "country": "Netherlands", "emoji": "🇳🇱"},
    "FRA": {"city": "Frankfurt", "country": "Germany", "emoji": "🇩🇪"},
    "BER": {"city": "Berlin", "country": "Germany", "emoji": "🇩🇪"},
    "ATH": {"city": "Athens", "country": "Greece", "emoji": "🇬🇷"},
    "LIS": {"city": "Lisbon", "country": "Portugal", "emoji": "🇵🇹"},
    "HKG": {"city": "Hong Kong", "country": "Hong Kong", "emoji": "🇭🇰"},
    "TYO": {"city": "Tokyo", "country": "Japan", "emoji": "🇯🇵"},
    "NRT": {"city": "Tokyo", "country": "Japan", "emoji": "🇯🇵"},
    "DPS": {"city": "Bali", "country": "Indonesia", "emoji": "🏝️"},
    "ZNZ": {"city": "Zanzibar", "country": "Tanzania", "emoji": "🏝️"},
    "MRU": {"city": "Mauritius", "country": "Mauritius", "emoji": "🏝️"},
    "SEZ": {"city": "Seychelles", "country": "Seychelles", "emoji": "🏝️"},
    "NBO": {"city": "Nairobi", "country": "Kenya", "emoji": "🇰🇪"},
    "JNB": {"city": "Johannesburg", "country": "South Africa", "emoji": "🇿🇦"},
    "KHI": {"city": "Karachi", "country": "Pakistan", "emoji": "🇵🇰"},
    "LHE": {"city": "Lahore", "country": "Pakistan", "emoji": "🇵🇰"},
}


def _trending_deep_link(origin: str, dest: str, dep_at: str, ret_at: str) -> str:
    """Attributed Aviasales search deep link (marker = partner.subid)."""
    marker = os.environ.get("TRAVELPAYOUTS_WL_MARKER", "")
    sub = os.environ.get("TRAVELPAYOUTS_SUBID", "")
    m = f"{marker}.{sub}" if (marker and sub) else marker

    def ddmm(iso: str) -> str:
        try:
            return f"{iso[8:10]}{iso[5:7]}"
        except Exception:
            return ""
    slug = f"{origin}{ddmm(dep_at)}{dest}{ddmm(ret_at)}1"
    base = f"https://www.aviasales.com/search/{slug}"
    return f"{base}?marker={m}" if m else base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _city_name(iata: str) -> str:
    m = IATA_NAMES.get(iata)
    return m["city"] if m else iata


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff.strip():
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


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

@router.get("/trending")
async def trending(request: Request, origin: str = "DXB", limit: int = 8):
    """Live 'trending routes' from an origin with real cheapest prices
    (Travelpayouts Data API), cached 24h. Unknown/obscure destinations are
    filtered out so the row stays recognisable."""
    db = request.app.state.db
    origin = (origin or "DXB").upper()[:3]
    origin_city = _city_name(origin)
    now_ts = _now().timestamp()
    cache = await db.travel_trending_cache.find_one({"_id": origin})
    if cache and isinstance(cache.get("fetched_ts"), (int, float)) \
            and (now_ts - cache["fetched_ts"]) < _TRENDING_TTL_H * 3600:
        return {"origin": origin, "origin_city": origin_city,
                "items": (cache.get("items") or [])[:limit], "cached": True}

    token = os.environ.get("TRAVELPAYOUTS_API_TOKEN")
    items: List[Dict[str, Any]] = []
    if token:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(_TP_CITY_DIRECTIONS,
                                      params={"origin": origin, "currency": "usd", "token": token})
            data = (r.json() or {}).get("data") or {}
            for row in sorted(data.values(), key=lambda x: x.get("price") or 1e9):
                dest = row.get("destination")
                meta = IATA_NAMES.get(dest)
                if not meta or dest == origin:
                    continue
                items.append({
                    "origin": origin, "destination": dest,
                    "city": meta["city"], "country": meta["country"], "emoji": meta["emoji"],
                    "price": int(row.get("price") or 0), "currency": "USD",
                    "airline": row.get("airline"), "transfers": int(row.get("transfers") or 0),
                    "departure_at": row.get("departure_at"), "return_at": row.get("return_at"),
                    "deep_link": _trending_deep_link(origin, dest,
                                                     row.get("departure_at") or "",
                                                     row.get("return_at") or ""),
                })
        except Exception:
            items = []
    if items:
        await db.travel_trending_cache.update_one(
            {"_id": origin}, {"$set": {"items": items, "fetched_ts": now_ts}}, upsert=True)
    elif cache:
        items = cache.get("items") or []  # stale fallback on API failure
    return {"origin": origin, "origin_city": origin_city,
            "items": items[:limit], "cached": False}


@router.get("/nearest-airport")
async def nearest_airport(request: Request):
    """Resolve the caller's nearest city IATA via Travelpayouts /whereami (by IP).
    confident=False for VPN/datacenter IPs so the client can prompt 'set your city'."""
    ip = _client_ip(request)
    origin, city, confident = "DXB", _city_name("DXB"), False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(_WHEREAMI, params={"locale": "en", "ip": ip})
        data = r.json() or {}
        iata = (data.get("iata") or "").upper()[:3]
        accuracy = (data.get("accuracy") or "").lower()
        if iata and accuracy in ("city", "nearest_city"):
            origin, city, confident = iata, (data.get("name") or _city_name(iata)), True
    except Exception:
        pass
    return {"origin": origin, "city": city, "confident": confident}


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


# ---- Trip Price Alerts (watch a route, ping on ≥5% drop) ------------------
_ALERT_DROP_PCT = 5.0


async def _origin_price_map(db, origin: str) -> Dict[str, Dict[str, Any]]:
    """Full {dest: {price,...}} map from city-directions for an origin,
    cached 24h (separate from the recognisable-only trending cache)."""
    origin = (origin or "").upper()[:3]
    now_ts = _now().timestamp()
    cache = await db.travel_prices_cache.find_one({"_id": origin})
    if cache and isinstance(cache.get("fetched_ts"), (int, float)) \
            and (now_ts - cache["fetched_ts"]) < _TRENDING_TTL_H * 3600:
        return cache.get("prices") or {}
    token = os.environ.get("TRAVELPAYOUTS_API_TOKEN")
    prices: Dict[str, Dict[str, Any]] = {}
    if token:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(_TP_CITY_DIRECTIONS,
                                      params={"origin": origin, "currency": "usd", "token": token})
            data = (r.json() or {}).get("data") or {}
            for dest, row in data.items():
                prices[dest] = {
                    "price": int(row.get("price") or 0), "airline": row.get("airline"),
                    "transfers": int(row.get("transfers") or 0),
                    "departure_at": row.get("departure_at"), "return_at": row.get("return_at"),
                }
        except Exception:
            prices = {}
    if prices:
        await db.travel_prices_cache.update_one(
            {"_id": origin}, {"$set": {"prices": prices, "fetched_ts": now_ts}}, upsert=True)
    elif cache:
        prices = cache.get("prices") or {}
    return prices


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _watch_public(w: Dict[str, Any], current: int) -> Dict[str, Any]:
    o, d = w.get("origin"), w.get("destination")
    om, dm = IATA_NAMES.get(o) or {}, IATA_NAMES.get(d) or {}
    base = int(w.get("baseline_price") or 0)
    cur = int(current or base)
    drop_pct = round((base - cur) / base * 100, 1) if base > 0 and cur < base else 0.0
    return {
        "watch_id": w["_id"], "origin": o, "destination": d,
        "origin_city": om.get("city") or o, "city": dm.get("city") or d,
        "country": dm.get("country") or "", "emoji": dm.get("emoji") or "✈️",
        "baseline_price": base, "current_price": cur, "drop_pct": drop_pct,
        "dropped": drop_pct >= _ALERT_DROP_PCT, "currency": "USD",
        "deep_link": w.get("deep_link"), "created_at": _iso(w.get("created_at")),
    }


async def _notify_price_drop(db, uid: str, w: Dict[str, Any], cur: int) -> None:
    o, d = w.get("origin"), w.get("destination")
    om, dm = IATA_NAMES.get(o) or {}, IATA_NAMES.get(d) or {}
    route = f"{om.get('city', o)} → {dm.get('city', d)}"
    base = int(w.get("baseline_price") or 0)
    title = f"Fare drop: {route}"
    msg = (f"{dm.get('emoji', '✈️')} {route} is now ${cur} (was ${base}). "
           "Book before it climbs again.")
    try:
        from routes.notifications import _enqueue
        await _enqueue(db, owner_user_id=uid, station_id="travel",
                       station_slug="travel", type_="travel_price_drop",
                       payload={"title": title, "body": msg, "message": msg,
                                "emoji": dm.get("emoji", "✈️"), "route": route,
                                "old_price": base, "new_price": cur,
                                "cta_url": w.get("deep_link")},
                       dedupe_key=f"tw_drop_{w['_id']}_{cur}")
    except Exception:
        pass
    try:
        u = await db.users.find_one({"user_id": uid})
        email = (u or {}).get("email")
        if email:
            from services.mailgun_client import send_email
            await asyncio.to_thread(send_email, email, title,
                                    f"<p>{msg}</p>", text=msg)
    except Exception:
        pass


class WatchBody(BaseModel):
    origin: str = Field(..., max_length=3)
    destination: str = Field(..., max_length=3)
    price: int = Field(..., ge=0)
    deep_link: Optional[str] = Field(None, max_length=600)


@router.get("/watches")
async def list_watches(request: Request, user: dict = Depends(current_user)):
    """List the user's watched routes with live current price + drop flag.
    Detects ≥5% drops here (fires an in-app + email ping, deduped per price)."""
    db = request.app.state.db
    uid = user["user_id"]
    rows = [w async for w in db.travel_price_watches.find(
        {"user_id": uid}).sort("created_at", -1).limit(50)]
    out: List[Dict[str, Any]] = []
    price_maps: Dict[str, Dict[str, Any]] = {}
    for w in rows:
        o = w.get("origin")
        if o not in price_maps:
            price_maps[o] = await _origin_price_map(db, o)
        cur = (price_maps[o].get(w.get("destination")) or {}).get("price") \
            or int(w.get("last_price") or 0) or int(w.get("baseline_price") or 0)
        cur = int(cur)
        base = int(w.get("baseline_price") or 0)
        upd = {"last_price": cur}
        if base > 0 and cur > 0 and cur <= base * (1 - _ALERT_DROP_PCT / 100) \
                and int(w.get("notified_price") or 0) != cur:
            await _notify_price_drop(db, uid, w, cur)
            upd["notified_price"] = cur
        await db.travel_price_watches.update_one({"_id": w["_id"]}, {"$set": upd})
        out.append(_watch_public(w, cur))
    return {"items": out, "alert_drop_pct": _ALERT_DROP_PCT}


@router.post("/watches")
async def add_watch(body: WatchBody, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    o, d = body.origin.upper()[:3], body.destination.upper()[:3]
    _id = f"tw_{uid[:10]}_{o}_{d}"
    await db.travel_price_watches.update_one(
        {"_id": _id},
        {"$set": {"user_id": uid, "origin": o, "destination": d,
                  "baseline_price": int(body.price), "deep_link": body.deep_link,
                  "last_price": int(body.price), "updated_at": _now()},
         "$setOnInsert": {"created_at": _now(), "notified_price": 0}},
        upsert=True)
    return {"ok": True, "watch_id": _id}


@router.delete("/watches/{watch_id}")
async def remove_watch(watch_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.travel_price_watches.delete_one(
        {"_id": watch_id, "user_id": user["user_id"]})
    return {"ok": True}


# ---- My Trips Sync (save flights/hotels/cars into one place) ---------------
_SAVED_TYPES = ("flight", "hotel", "car")


class SavedTripBody(BaseModel):
    trip_type: str = Field(..., max_length=12)
    title: str = Field(..., max_length=160)
    subtitle: Optional[str] = Field(None, max_length=200)
    deep_link: Optional[str] = Field(None, max_length=600)
    image_url: Optional[str] = Field(None, max_length=600)
    price_label: Optional[str] = Field(None, max_length=60)
    origin: Optional[str] = Field(None, max_length=3)
    destination: Optional[str] = Field(None, max_length=3)


def _saved_public(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "saved_id": s["_id"], "trip_type": s.get("trip_type"),
        "title": s.get("title"), "subtitle": s.get("subtitle"),
        "deep_link": s.get("deep_link"), "image_url": s.get("image_url"),
        "price_label": s.get("price_label"), "origin": s.get("origin"),
        "destination": s.get("destination"), "created_at": _iso(s.get("created_at")),
    }


@router.post("/saved")
async def save_trip(body: SavedTripBody, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    tt = body.trip_type if body.trip_type in _SAVED_TYPES else "flight"
    _id = f"st_{uuid.uuid4().hex[:14]}"
    await db.travel_saved_trips.insert_one({
        "_id": _id, "user_id": user["user_id"], "trip_type": tt,
        "title": body.title[:160], "subtitle": body.subtitle,
        "deep_link": body.deep_link, "image_url": body.image_url,
        "price_label": body.price_label,
        "origin": (body.origin or None), "destination": (body.destination or None),
        "created_at": _now(),
    })
    return {"ok": True, "saved_id": _id}


@router.delete("/saved/{saved_id}")
async def unsave_trip(saved_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.travel_saved_trips.delete_one(
        {"_id": saved_id, "user_id": user["user_id"]})
    return {"ok": True}


@router.get("/saved")
async def list_saved(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    groups: Dict[str, List[Dict[str, Any]]] = {"flight": [], "hotel": [], "car": []}
    async for s in db.travel_saved_trips.find(
            {"user_id": user["user_id"]}).sort("created_at", -1).limit(100):
        groups.setdefault(s.get("trip_type") or "flight", []).append(_saved_public(s))
    return {"flights": groups.get("flight", []),
            "hotels": groups.get("hotel", []),
            "cars": groups.get("car", [])}


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
        await db.travel_price_watches.create_index([("user_id", 1)])
        await db.travel_saved_trips.create_index([("user_id", 1)])
    except Exception:
        pass


__all__ = ["router", "ensure_travel", "TRAVEL_TOPIC", "DEAL_TYPES"]
