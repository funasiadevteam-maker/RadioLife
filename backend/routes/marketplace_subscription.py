"""Marketplace Merchant Subscriptions + Happy Hour + Dashboard.

Only merchants with an active paid subscription (Starter $29 / Pro $99) may
list & sell. Subscription is billed via Stripe Checkout (subscription mode).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.marketplace import now, effective_points

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace", tags=["marketplace-subscription"])


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k in ("created_at", "updated_at", "current_period_end"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


@router.get("/subscription/plans")
async def plans(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    async for p in db.subscription_plans.find({"active": True}).sort("price_cents", 1):
        out.append({"plan_id": p["plan_id"], "name": p["name"],
                    "price_cents": p["price_cents"], "interval": p.get("interval", "month"),
                    "features": p.get("features", [])})
    return {"items": out}


@router.get("/subscription")
async def my_subscription(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    sub = await db.merchant_subscriptions.find_one({"business_id": p["business_id"]})
    active = bool(p.get("subscription_active"))
    return {"active": active,
            "subscription": _clean(sub) if sub else None,
            "business_id": p["business_id"]}


class SubCheckoutBody(BaseModel):
    plan_id: str
    origin_url: Optional[str] = None


@router.post("/subscription/checkout")
async def subscription_checkout(body: SubCheckoutBody, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    plan = await db.subscription_plans.find_one({"plan_id": body.plan_id, "active": True})
    if not plan:
        raise HTTPException(400, {"code": "bad_plan"})
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price_data": {
            "currency": "usd",
            "product_data": {"name": f"RadioLife {plan['name']} — Merchant Plan"},
            "unit_amount": int(plan["price_cents"]),
            "recurring": {"interval": plan.get("interval", "month")}},
            "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "merchant_subscription", "business_id": p["business_id"],
                  "plan_id": body.plan_id})
    await db.merchant_subscriptions.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"business_id": p["business_id"], "plan_id": body.plan_id,
                  "status": "pending", "session_id": session.id, "updated_at": now()},
         "$setOnInsert": {"created_at": now()}}, upsert=True)
    return {"ok": True, "checkout_url": session.url, "session_id": session.id}


@router.get("/subscription/status/{session_id}")
async def subscription_status(session_id: str, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    sub = await db.merchant_subscriptions.find_one(
        {"business_id": p["business_id"], "session_id": session_id})
    if not sub:
        raise HTTPException(404, {"code": "sub_not_found"})
    if sub.get("status") == "active":
        return {"status": "active", "active": True}
    if not stripe.api_key:
        return {"status": sub.get("status", "pending"), "active": False}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": sub.get("status", "pending"), "active": False}
    if sess.get("payment_status") == "paid" or sess.get("status") == "complete":
        await db.merchant_subscriptions.update_one(
            {"business_id": p["business_id"]},
            {"$set": {"status": "active",
                      "stripe_subscription_id": sess.get("subscription"),
                      "updated_at": now()}})
        await db.marketplace_profiles.update_one(
            {"business_id": p["business_id"]},
            {"$set": {"subscription_active": True, "updated_at": now()}})
        return {"status": "active", "active": True}
    return {"status": "pending", "active": False}


# ───────────── Happy Hour (2X BigPoints boost) ─────────────
class HappyHourBody(BaseModel):
    enabled: bool = False
    start_hour: int = Field(0, ge=0, le=23)
    end_hour: int = Field(0, ge=0, le=23)
    multiplier: float = Field(2.0, ge=1.0, le=5.0)


@router.get("/happy-hour")
async def get_happy_hour(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    hh = p.get("happy_hour") or {"enabled": False, "start_hour": 0, "end_hour": 0, "multiplier": 2.0}
    return {"happy_hour": hh, "active_now": effective_points(p).get("happy_hour", False)}


@router.patch("/happy-hour")
async def set_happy_hour(body: HappyHourBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    await db.marketplace_profiles.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"happy_hour": body.model_dump(), "updated_at": now()}})
    updated = await db.marketplace_profiles.find_one({"business_id": p["business_id"]})
    return {"ok": True, "active_now": effective_points(updated).get("happy_hour", False)}


# ───────────── Merchant Dashboard summary ─────────────
@router.get("/dashboard")
async def dashboard(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    bid = p["business_id"]
    sub = await db.merchant_subscriptions.find_one({"business_id": bid})
    acct = await db.merchant_bigpoint_accounts.find_one({"business_id": bid})
    menu_count = await db.menu_items.count_documents({"business_id": bid})
    counts: Dict[str, int] = {}
    async for o in db.marketplace_orders.find({"business_id": bid}, {"status": 1}):
        counts[o.get("status", "?")] = counts.get(o.get("status", "?"), 0) + 1
    points_spent = 0
    async for o in db.marketplace_orders.find(
            {"business_id": bid, "points_awarded_done": True}, {"points_to_award": 1}):
        points_spent += int(o.get("points_to_award", 0))
    revenue_cents = 0
    async for o in db.marketplace_orders.find(
            {"business_id": bid, "payment_status": "paid"}, {"subtotal_cents": 1}):
        revenue_cents += int(o.get("subtotal_cents", 0))
    return {
        "business_id": bid,
        "public_name": p.get("public_name"),
        "status": p.get("status"),
        "subscription_active": bool(p.get("subscription_active")),
        "subscription": _clean(sub) if sub else None,
        "happy_hour": p.get("happy_hour") or {"enabled": False},
        "happy_hour_active_now": effective_points(p).get("happy_hour", False),
        "menu_item_count": menu_count,
        "order_counts": counts,
        "open_orders": counts.get("accepted", 0) + counts.get("preparing", 0) + counts.get("ready", 0),
        "bigpoints_spent": points_spent,
        "bigpoints_balance": (acct or {}).get("balance_points", 0),
        "revenue_cents": revenue_cents,
    }


__all__ = ["router"]
