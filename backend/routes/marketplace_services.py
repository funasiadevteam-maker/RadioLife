"""Marketplace Service Bookings (Phase C) — non-food merchants.

Salons / home-service pros publish services (name, duration, price, BigPoints)
and weekly availability. Customers book a slot and pay a merchant-set
RESERVATION FEE (credited toward the service). BigPoints are awarded on
booking completion. Reservation fee via Stripe (or free if fee is 0).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services.marketplace import now, new_id, effective_points

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace/services", tags=["marketplace-services"])
consumer_router = APIRouter(prefix="/api/shop", tags=["marketplace-services-consumer"])

BOOKING_ADVANCE = {"confirmed": ("completed", "no_show"), "pending_payment": ("confirmed", "canceled")}


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    for h in d.get("status_history", []) or []:
        v = h.get("at")
        if hasattr(v, "isoformat"):
            h["at"] = v.isoformat()
    return d


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


# ───────────── Merchant: service catalogue ─────────────
class ServiceBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=400)
    duration_min: int = Field(30, ge=5, le=600)
    price_cents: int = Field(..., ge=0, le=10_000_000)
    reservation_fee_cents: int = Field(0, ge=0, le=10_000_000)
    bigpoints: Optional[int] = Field(None, ge=0, le=100000)
    image_url: Optional[str] = None
    active: bool = True


@router.get("")
async def list_services(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [_clean(s) async for s in db.service_items.find(
        {"business_id": p["business_id"]}).sort("sort", 1)]
    return {"items": items}


@router.post("/items")
async def create_service(body: ServiceBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    if body.reservation_fee_cents > body.price_cents:
        raise HTTPException(400, {"code": "fee_exceeds_price"})
    n = await db.service_items.count_documents({"business_id": p["business_id"]})
    sid = new_id("svc")
    doc = {"service_id": sid, "business_id": p["business_id"], "sort": n,
           **body.model_dump(), "created_at": now(), "updated_at": now()}
    await db.service_items.insert_one(dict(doc))
    return {"ok": True, "service": _clean(doc)}


@router.patch("/items/{service_id}")
async def update_service(service_id: str, body: ServiceBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    if body.reservation_fee_cents > body.price_cents:
        raise HTTPException(400, {"code": "fee_exceeds_price"})
    res = await db.service_items.update_one(
        {"service_id": service_id, "business_id": p["business_id"]},
        {"$set": {**body.model_dump(), "updated_at": now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "service_not_found"})
    s = await db.service_items.find_one({"service_id": service_id})
    return {"ok": True, "service": _clean(s)}


@router.delete("/items/{service_id}")
async def delete_service(service_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.service_items.delete_one(
        {"service_id": service_id, "business_id": p["business_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, {"code": "service_not_found"})
    return {"ok": True}


@router.post("/items/{service_id}/photo")
async def service_photo(service_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    s = await db.service_items.find_one({"service_id": service_id, "business_id": p["business_id"]})
    if not s:
        raise HTTPException(404, {"code": "service_not_found"})
    body = await request.json()
    b64 = body.get("file_base64")
    if not b64:
        raise HTTPException(400, {"code": "file_required"})
    from services import menu_photos as mp
    try:
        url = mp.save_base64(service_id, b64, body.get("ext", "png"))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    await db.service_items.update_one({"service_id": service_id},
                                      {"$set": {"image_url": url, "updated_at": now()}})
    return {"ok": True, "image_url": url}


@router.post("/items/{service_id}/photo/ai")
async def service_photo_ai(service_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    s = await db.service_items.find_one({"service_id": service_id, "business_id": p["business_id"]})
    if not s:
        raise HTTPException(404, {"code": "service_not_found"})
    from services import menu_photos as mp
    try:
        url = await mp.generate_service_ai(service_id, name=s.get("name", ""),
                                            description=s.get("description") or "")
    except Exception as e:
        raise HTTPException(502, {"code": "ai_photo_failed", "detail": str(e)[:200]})
    await db.service_items.update_one({"service_id": service_id},
                                      {"$set": {"image_url": url, "updated_at": now()}})
    return {"ok": True, "image_url": url}


# ───────────── Merchant: weekly availability ─────────────
class AvailabilityBody(BaseModel):
    slot_minutes: int = Field(30, ge=5, le=240)
    # day index "0"=Mon .. "6"=Sun -> list of {start:"HH:MM", end:"HH:MM"}
    days: Dict[str, List[Dict[str, str]]] = {}


DEFAULT_AVAIL = {"slot_minutes": 30,
                 "days": {str(d): [{"start": "09:00", "end": "17:00"}] for d in range(0, 6)}}


@router.get("/availability")
async def get_availability(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    return {"availability": p.get("service_availability") or DEFAULT_AVAIL}


@router.patch("/availability")
async def set_availability(body: AvailabilityBody, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    await db.marketplace_profiles.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"service_availability": body.model_dump(), "updated_at": now()}})
    return {"ok": True, "availability": body.model_dump()}


# ───────────── Merchant: booking management ─────────────
@router.get("/bookings")
async def merchant_bookings(request: Request, status: Optional[str] = None,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    q: Dict[str, Any] = {"business_id": p["business_id"]}
    if status:
        q["status"] = status
    else:
        q["payment_status"] = "paid"
    items = [_clean(b) async for b in db.service_bookings.find(q).sort("created_at", -1).limit(80)]
    return {"items": items}


class BookingStatusBody(BaseModel):
    status: str


@router.patch("/bookings/{booking_id}/status")
async def update_booking_status(booking_id: str, body: BookingStatusBody, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    b = await db.service_bookings.find_one(
        {"booking_id": booking_id, "business_id": p["business_id"]})
    if not b:
        raise HTTPException(404, {"code": "booking_not_found"})
    allowed = BOOKING_ADVANCE.get(b.get("status"), ())
    if body.status not in allowed:
        raise HTTPException(400, {"code": "invalid_transition",
                                  "from": b.get("status"), "to": body.status})
    await db.service_bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {"status": body.status, "updated_at": now()},
         "$push": {"status_history": {"status": body.status, "at": now()}}})
    if body.status == "completed" and not b.get("points_awarded_done"):
        pts = int(b.get("points_to_award", 0))
        if pts > 0:
            from services.loyalty import award_with_tier_bonus
            await award_with_tier_bonus(
                db, user_id=b["user_id"], source="marketplace_service",
                source_id=booking_id, base_points=pts,
                idempotency_key=f"booking_complete_{booking_id}",
                metadata={"business_id": p["business_id"], "note": "Service booking reward"})
            await db.merchant_bigpoint_accounts.update_one(
                {"business_id": p["business_id"], "funding_mode": "prepaid"},
                {"$inc": {"balance_points": -pts}, "$set": {"updated_at": now()}})
        await db.service_bookings.update_one(
            {"booking_id": booking_id}, {"$set": {"points_awarded_done": True}})
    b = await db.service_bookings.find_one({"booking_id": booking_id})
    return {"ok": True, "booking": _clean(b)}


# ───────────── Consumer: browse + slots + book ─────────────
def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


@consumer_router.get("/businesses/{business_id}/services")
async def business_services(business_id: str, request: Request,
                            user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1, "cover_urls": 1, "bigpoints": 1, "happy_hour": 1})
    if not p:
        raise HTTPException(404, {"code": "business_not_found"})
    eff = effective_points(p)
    items = []
    async for s in db.service_items.find(
            {"business_id": business_id, "active": True}).sort("sort", 1):
        items.append({"service_id": s["service_id"], "name": s.get("name"),
                      "description": s.get("description"), "duration_min": s.get("duration_min"),
                      "price_cents": s.get("price_cents"),
                      "reservation_fee_cents": s.get("reservation_fee_cents", 0),
                      "bigpoints": s.get("bigpoints"), "image_url": s.get("image_url")})
    return {"business_id": business_id, "public_name": p.get("public_name"),
            "cover_url": (p.get("cover_urls") or [None])[0],
            "default_bigpoints": (p.get("bigpoints") or {}).get("default_points", 0),
            "happy_hour": eff.get("happy_hour", False), "points_multiplier": eff.get("multiplier", 1),
            "services": items}


@consumer_router.get("/businesses/{business_id}/services/{service_id}/slots")
async def service_slots(business_id: str, service_id: str, date: str, request: Request,
                        user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    svc = await db.service_items.find_one(
        {"service_id": service_id, "business_id": business_id, "active": True})
    if not svc:
        raise HTTPException(404, {"code": "service_not_found"})
    profile = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "subscription_active": True}, {"service_availability": 1})
    avail = (profile or {}).get("service_availability") or DEFAULT_AVAIL
    try:
        d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, {"code": "bad_date"})
    weekday = str(d.weekday())
    windows = avail.get("days", {}).get(weekday, [])
    step = int(svc.get("duration_min") or avail.get("slot_minutes", 30))
    # Booked start times for this business+date (exclude canceled).
    booked = set()
    async for b in db.service_bookings.find(
            {"business_id": business_id, "date": date,
             "status": {"$nin": ["canceled"]}}, {"start_time": 1}):
        booked.add(b.get("start_time"))
    # Filter past slots if the date is today.
    today = datetime.now(timezone.utc)
    is_today = d.date() == today.date()
    now_min = today.hour * 60 + today.minute
    slots = []
    for w in windows:
        start, end = _to_min(w.get("start", "09:00")), _to_min(w.get("end", "17:00"))
        t = start
        while t + step <= end:
            hhmm = _to_hhmm(t)
            if hhmm not in booked and not (is_today and t <= now_min):
                slots.append(hhmm)
            t += step
    return {"date": date, "duration_min": step, "slots": slots}


class ServiceCheckoutBody(BaseModel):
    business_id: str
    service_id: str
    date: str
    start_time: str
    origin_url: Optional[str] = None
    note: Optional[str] = Field(None, max_length=300)


@consumer_router.post("/service-bookings/checkout")
async def service_checkout(body: ServiceCheckoutBody, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    profile = await db.marketplace_profiles.find_one(
        {"business_id": body.business_id, "status": "approved", "subscription_active": True})
    if not profile:
        raise HTTPException(404, {"code": "business_unavailable"})
    svc = await db.service_items.find_one(
        {"service_id": body.service_id, "business_id": body.business_id, "active": True})
    if not svc:
        raise HTTPException(404, {"code": "service_not_found"})
    # Slot must still be free.
    clash = await db.service_bookings.find_one(
        {"business_id": body.business_id, "date": body.date,
         "start_time": body.start_time, "status": {"$nin": ["canceled"]}})
    if clash:
        raise HTTPException(409, {"code": "slot_taken"})

    eff = effective_points(profile)
    base_pts = svc.get("bigpoints")
    points = int(base_pts if base_pts is not None else eff.get("points", 0))
    if base_pts is not None and eff.get("happy_hour"):
        points = int(round(points * eff.get("multiplier", 1)))
    fee = int(svc.get("reservation_fee_cents", 0))
    booking_id = new_id("bk")
    booking = {
        "booking_id": booking_id, "business_id": body.business_id,
        "business_name": profile.get("public_name"), "user_id": user.get("user_id"),
        "service_id": body.service_id, "service_name": svc.get("name"),
        "price_cents": int(svc.get("price_cents", 0)), "reservation_fee_cents": fee,
        "date": body.date, "start_time": body.start_time,
        "duration_min": svc.get("duration_min"), "note": body.note,
        "points_to_award": points, "points_awarded_done": False,
        "status": "pending_payment", "payment_status": "pending",
        "session_id": None, "status_history": [], "created_at": now(), "updated_at": now(),
    }
    if fee <= 0:
        booking["status"] = "confirmed"
        booking["payment_status"] = "paid"
        booking["status_history"] = [{"status": "confirmed", "at": now()}]
        await db.service_bookings.insert_one(dict(booking))
        return {"ok": True, "booking_id": booking_id, "status": "confirmed",
                "checkout_url": None, "reservation_fee_cents": 0}
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
                     "product_data": {"name": f"{profile.get('public_name')} — {svc.get('name')} reservation"},
                     "unit_amount": fee}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "service_booking", "booking_id": booking_id,
                  "business_id": body.business_id})
    booking["session_id"] = session.id
    await db.service_bookings.insert_one(dict(booking))
    return {"ok": True, "booking_id": booking_id, "status": "pending_payment",
            "checkout_url": session.url, "session_id": session.id,
            "reservation_fee_cents": fee}


@consumer_router.get("/service-bookings")
async def my_bookings(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    items = [_clean(b) async for b in db.service_bookings.find(
        {"user_id": user.get("user_id")}).sort("created_at", -1).limit(50)]
    return {"items": items}


@consumer_router.get("/service-bookings/{booking_id}/status")
async def booking_status(booking_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    b = await db.service_bookings.find_one(
        {"booking_id": booking_id, "user_id": user.get("user_id")})
    if not b:
        raise HTTPException(404, {"code": "booking_not_found"})
    if b.get("payment_status") != "paid" and b.get("session_id") and stripe.api_key:
        try:
            sess = stripe.checkout.Session.retrieve(b["session_id"])
            if sess.get("payment_status") == "paid" or sess.get("status") == "complete":
                await db.service_bookings.update_one(
                    {"booking_id": booking_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"payment_status": "paid", "status": "confirmed", "updated_at": now()},
                     "$push": {"status_history": {"status": "confirmed", "at": now()}}})
                b = await db.service_bookings.find_one({"booking_id": booking_id})
        except Exception:
            pass
    return {"status": b.get("status"), "payment_status": b.get("payment_status"),
            "booking": _clean(b)}


async def ensure_services_indexes(db) -> None:
    await db.service_items.create_index("service_id", unique=True)
    await db.service_items.create_index([("business_id", 1), ("sort", 1)])
    await db.service_bookings.create_index("booking_id", unique=True)
    await db.service_bookings.create_index([("user_id", 1), ("created_at", -1)])
    await db.service_bookings.create_index([("business_id", 1), ("date", 1)])


__all__ = ["router", "consumer_router", "ensure_services_indexes"]
