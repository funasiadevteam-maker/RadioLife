"""Category Spotlight bid auction (merchant). Bid per-impression to top ONE
category's search results; higher bid ranks higher. Budget is prepaid via
Stripe hosted Checkout and billed per impression by the shop read path."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.category_bids import bid_standing

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace/category-bid", tags=["marketplace-category-bid"])


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


class SetBidBody(BaseModel):
    category: str
    bid_cents: int = Field(..., ge=1, le=1000)
    daily_cap_cents: int = Field(0, ge=0, le=10000000)


class TopupBody(BaseModel):
    amount_cents: int = Field(..., ge=500, le=1000000)
    origin_url: Optional[str] = None


@router.get("/categories")
async def categories(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    async for c in db.marketplace_categories.find({"active": True}).sort("name", 1):
        out.append({"key": c.get("key"), "name": c.get("name")})
    return {"items": out}


@router.get("")
async def my_bid(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    b = await db.category_bids.find_one({"business_id": p["business_id"]})
    standing = await bid_standing(db, b["category"], p["business_id"]) if b and b.get("category") else None
    # Low-budget warning so the merchant tops up before losing the top spot.
    low = None
    if b:
        bid_c = int(b.get("bid_cents", 0) or 0)
        left = int(b.get("budget_cents", 0)) // bid_c if bid_c else 0
        low = {"impressions_left": left, "low_budget": b.get("status") == "active" and left < 20,
               "depleted": b.get("status") == "depleted"}
    return {"business_id": p["business_id"], "public_name": p.get("public_name"),
            "bid": _clean(dict(b)) if b else None, "standing": standing, "budget": low}


@router.post("/set")
async def set_bid(body: SetBidBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    ex = await db.category_bids.find_one({"business_id": p["business_id"]})
    budget = int(ex.get("budget_cents", 0)) if ex else 0
    status = "active" if budget >= body.bid_cents else "pending_budget"
    base = {"business_id": p["business_id"], "owner_user_id": user.get("user_id"),
            "public_name": p.get("public_name"), "category": body.category,
            "bid_cents": body.bid_cents, "daily_cap_cents": body.daily_cap_cents,
            "status": status, "updated_at": _now()}
    if ex:
        await db.category_bids.update_one({"business_id": p["business_id"]}, {"$set": base})
        bid_id = ex["bid_id"]
    else:
        bid_id = f"cbid_{uuid.uuid4().hex[:10]}"
        base.update({"bid_id": bid_id, "budget_cents": 0, "spent_cents": 0,
                     "impressions": 0, "spent_today": 0, "spend_date": None, "created_at": _now()})
        await db.category_bids.insert_one(base)
    standing = await bid_standing(db, body.category, p["business_id"])
    return {"ok": True, "bid_id": bid_id, "status": status, "standing": standing}


@router.post("/pause")
async def pause(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    await db.category_bids.update_one({"business_id": p["business_id"]},
                                      {"$set": {"status": "paused", "updated_at": _now()}})
    return {"ok": True}


@router.post("/resume")
async def resume(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    b = await db.category_bids.find_one({"business_id": p["business_id"]})
    if not b:
        raise HTTPException(404, {"code": "no_bid"})
    status = "active" if int(b.get("budget_cents", 0)) >= int(b.get("bid_cents", 0)) else "pending_budget"
    await db.category_bids.update_one({"business_id": p["business_id"]},
                                      {"$set": {"status": status, "updated_at": _now()}})
    return {"ok": True, "status": status}


@router.post("/topup/checkout")
async def topup_checkout(body: TopupBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    b = await db.category_bids.find_one({"business_id": p["business_id"]})
    if not b:
        raise HTTPException(400, {"code": "set_bid_first"})
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (body.origin_url or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
            "product_data": {"name": f"Category Spotlight budget — {p.get('public_name')}"},
            "unit_amount": int(body.amount_cents)}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "category_bid_topup", "business_id": p["business_id"],
                  "bid_id": b["bid_id"], "amount_cents": str(body.amount_cents)})
    await db.category_topups.insert_one({"session_id": session.id, "bid_id": b["bid_id"],
        "business_id": p["business_id"], "amount_cents": int(body.amount_cents),
        "status": "pending", "created_at": _now()})
    return {"ok": True, "checkout_url": session.url, "session_id": session.id}


@router.get("/topup/{session_id}/status")
async def topup_status(session_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    t = await db.category_topups.find_one({"session_id": session_id})
    if not t:
        raise HTTPException(404, {"code": "topup_not_found"})
    p = await _my_business(db, user)
    if t.get("business_id") != p["business_id"]:
        raise HTTPException(404, {"code": "topup_not_found"})
    if t.get("status") == "credited":
        return {"status": "credited"}
    if stripe.api_key:
        try:
            sess = stripe.checkout.Session.retrieve(session_id)
        except Exception:
            sess = None
        if sess and sess.get("payment_status") == "paid":
            b = await db.category_bids.find_one({"bid_id": t["bid_id"]})
            new_budget = int((b or {}).get("budget_cents", 0)) + int(t["amount_cents"])
            await db.category_bids.update_one({"bid_id": t["bid_id"]},
                {"$set": {"budget_cents": new_budget, "status": "active", "updated_at": _now()}})
            await db.category_topups.update_one({"session_id": session_id}, {"$set": {"status": "credited"}})
            return {"status": "credited", "budget_cents": new_budget}
    return {"status": t.get("status")}


__all__ = ["router"]
