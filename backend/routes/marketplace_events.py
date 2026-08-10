"""Marketplace Events (Phase E) — a venue sells tickets to a local event
with LIMITED CAPACITY that can sell out. Buy with Stripe card or BigPoints.
Capacity is enforced with an atomic guarded increment so an event cannot
oversell.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services.marketplace import now, new_id
from services.points_service import PointsService

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""
POINTS_PER_DOLLAR = 100

router = APIRouter(prefix="/api/merchant/marketplace/events", tags=["marketplace-events"])
consumer_router = APIRouter(prefix="/api/shop", tags=["marketplace-events-consumer"])


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


def _pub(e: Dict[str, Any]) -> Dict[str, Any]:
    e = _clean(dict(e))
    cap = e.get("capacity", 0)
    sold = e.get("tickets_sold", 0)
    e["remaining"] = max(0, cap - sold)
    e["sold_out"] = e["remaining"] <= 0
    return e


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


class EventBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=400)
    location: Optional[str] = Field(None, max_length=160)
    starts_at: str = Field(..., min_length=4, max_length=40)
    price_cents: int = Field(..., ge=0, le=1_000_000)
    capacity: int = Field(..., ge=1, le=100000)
    allow_points: bool = True
    allow_card: bool = True
    active: bool = True


# ───────────── Merchant CRUD ─────────────
@router.get("")
async def list_events(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [_pub(x) async for x in db.events.find(
        {"business_id": p["business_id"]}).sort("starts_at", 1)]
    return {"items": items}


@router.post("/items")
async def create_event(body: EventBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    eid = new_id("evt")
    doc = {"event_id": eid, "business_id": p["business_id"], "sponsor_name": p.get("public_name"),
           "title": body.title.strip(), "description": (body.description or "").strip() or None,
           "location": (body.location or "").strip() or None, "starts_at": body.starts_at,
           "price_cents": body.price_cents, "capacity": body.capacity, "tickets_sold": 0,
           "allow_points": body.allow_points, "allow_card": body.allow_card,
           "points_per_dollar": POINTS_PER_DOLLAR, "active": body.active,
           "created_at": now(), "updated_at": now()}
    await db.events.insert_one(dict(doc))
    return {"ok": True, "event": _pub(doc)}


@router.patch("/items/{event_id}")
async def update_event(event_id: str, body: EventBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    ev = await db.events.find_one({"event_id": event_id, "business_id": p["business_id"]})
    if not ev:
        raise HTTPException(404, {"code": "event_not_found"})
    if body.capacity < ev.get("tickets_sold", 0):
        raise HTTPException(400, {"code": "capacity_below_sold", "sold": ev.get("tickets_sold", 0)})
    await db.events.update_one(
        {"event_id": event_id, "business_id": p["business_id"]},
        {"$set": {"title": body.title.strip(), "description": (body.description or "").strip() or None,
                  "location": (body.location or "").strip() or None, "starts_at": body.starts_at,
                  "price_cents": body.price_cents, "capacity": body.capacity,
                  "allow_points": body.allow_points, "allow_card": body.allow_card,
                  "sponsor_name": p.get("public_name"), "active": body.active, "updated_at": now()}})
    x = await db.events.find_one({"event_id": event_id})
    return {"ok": True, "event": _pub(x)}


@router.delete("/items/{event_id}")
async def delete_event(event_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.events.delete_one({"event_id": event_id, "business_id": p["business_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, {"code": "event_not_found"})
    return {"ok": True}


# ───────────── Consumer ─────────────
async def _reserve(db, event_id: str, qty: int) -> bool:
    """Atomic guarded increment: only succeeds if enough capacity remains."""
    ev = await db.events.find_one({"event_id": event_id})
    if not ev:
        return False
    limit = ev.get("capacity", 0) - qty
    res = await db.events.update_one(
        {"event_id": event_id, "tickets_sold": {"$lte": limit}},
        {"$inc": {"tickets_sold": qty}, "$set": {"updated_at": now()}})
    return res.modified_count == 1


async def _release(db, event_id: str, qty: int) -> None:
    await db.events.update_one({"event_id": event_id}, {"$inc": {"tickets_sold": -qty}})


async def _issue_ticket(db, event: Dict[str, Any], user_id: str, qty: int, method: str,
                        session_id: Optional[str] = None) -> Dict[str, Any]:
    doc = {"ticket_id": new_id("tkt"), "code": uuid.uuid4().hex[:8].upper(),
           "event_id": event["event_id"], "business_id": event["business_id"],
           "event_title": event["title"], "starts_at": event.get("starts_at"),
           "user_id": user_id, "qty": qty, "method": method, "status": "active",
           "session_id": session_id, "created_at": now(), "updated_at": now()}
    await db.event_tickets.insert_one(dict(doc))
    return _clean(doc)


@consumer_router.get("/businesses/{business_id}/events")
async def business_events(business_id: str, request: Request,
                          user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    biz = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1})
    if not biz:
        raise HTTPException(404, {"code": "business_not_found"})
    items = [_pub(x) async for x in db.events.find(
        {"business_id": business_id, "active": True}).sort("starts_at", 1)]
    mine, balance = [], 0
    if user:
        balance = await PointsService(db).get_balance(user.get("user_id"))
        async for t in db.event_tickets.find(
                {"business_id": business_id, "user_id": user.get("user_id"),
                 "status": "active"}).sort("created_at", -1):
            mine.append(_clean(dict(t)))
    return {"business_id": business_id, "public_name": biz.get("public_name"),
            "points_per_dollar": POINTS_PER_DOLLAR, "points_balance": balance,
            "items": items, "mine": mine}


class PurchaseBody(BaseModel):
    event_id: str
    qty: int = Field(1, ge=1, le=20)
    method: str = Field(..., description="points | card")
    origin_url: Optional[str] = None


@consumer_router.post("/events/purchase")
async def purchase_ticket(body: PurchaseBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    event = await db.events.find_one({"event_id": body.event_id, "active": True})
    if not event:
        raise HTTPException(404, {"code": "event_not_found"})

    if body.method == "points":
        if not event.get("allow_points", True):
            raise HTTPException(400, {"code": "points_not_allowed"})
        points_cost = round(event["price_cents"] / 100.0 * POINTS_PER_DOLLAR) * body.qty
        balance = await PointsService(db).get_balance(uid)
        if balance < points_cost:
            raise HTTPException(400, {"code": "insufficient_points", "needed": points_cost, "have": balance})
        if not await _reserve(db, body.event_id, body.qty):
            raise HTTPException(400, {"code": "sold_out"})
        try:
            idem = f"event:points:{uid}:{uuid.uuid4().hex[:8]}"
            if points_cost > 0:
                await PointsService(db).spend(user_id=uid, source="event_ticket", amount=points_cost,
                                              source_id=body.event_id, idempotency_key=idem,
                                              metadata={"event_id": body.event_id, "qty": body.qty})
        except Exception:
            await _release(db, body.event_id, body.qty)
            raise
        ticket = await _issue_ticket(db, event, uid, body.qty, "points")
        return {"ok": True, "method": "points", "points_spent": points_cost, "ticket": ticket}

    if body.method == "card":
        if not stripe.api_key:
            raise HTTPException(503, {"code": "stripe_unconfigured"})
        if not event.get("allow_card", True):
            raise HTTPException(400, {"code": "card_not_allowed"})
        origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
        if not origin:
            raise HTTPException(400, {"code": "origin_required"})
        if not await _reserve(db, body.event_id, body.qty):
            raise HTTPException(400, {"code": "sold_out"})
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price_data": {
                "currency": "usd",
                "product_data": {"name": f"{event.get('sponsor_name')} — {event['title']}"},
                "unit_amount": int(event["price_cents"])}, "quantity": body.qty}],
            success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/payment/cancel",
            metadata={"kind": "marketplace_event", "event_id": body.event_id,
                      "buyer_id": uid, "qty": str(body.qty)})
        await db.event_purchases.insert_one({
            "session_id": session.id, "buyer_user_id": uid, "event_id": body.event_id,
            "qty": body.qty, "status": "pending", "created_at": now()})
        return {"ok": True, "method": "card", "checkout_url": session.url, "session_id": session.id}

    raise HTTPException(400, {"code": "bad_method"})


@consumer_router.get("/events/purchase/{session_id}/status")
async def purchase_status(session_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    pur = await db.event_purchases.find_one({"session_id": session_id})
    if not pur:
        raise HTTPException(404, {"code": "purchase_not_found"})
    if pur.get("status") == "paid" and pur.get("ticket_id"):
        t = await db.event_tickets.find_one({"ticket_id": pur["ticket_id"]})
        return {"status": "paid", "ticket": _clean(dict(t)) if t else None}
    if pur.get("status") == "canceled":
        return {"status": "canceled"}
    if not stripe.api_key:
        return {"status": pur.get("status", "pending")}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": pur.get("status", "pending")}
    if sess.get("payment_status") == "paid":
        event = await db.events.find_one({"event_id": pur["event_id"]})
        ticket = await _issue_ticket(db, event or {"event_id": pur["event_id"], "title": "Event",
                                     "business_id": pur.get("business_id")},
                                     pur["buyer_user_id"], pur["qty"], "card", session_id=session_id)
        await db.event_purchases.update_one(
            {"session_id": session_id},
            {"$set": {"status": "paid", "ticket_id": ticket["ticket_id"], "paid_at": now()}})
        return {"status": "paid", "ticket": ticket}
    return {"status": "pending"}


@consumer_router.get("/events/mine")
async def my_tickets(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    out = [_clean(x) async for x in db.event_tickets.find(
        {"user_id": user.get("user_id"), "status": "active"}).sort("created_at", -1)]
    return {"items": out}


__all__ = ["router", "consumer_router"]
