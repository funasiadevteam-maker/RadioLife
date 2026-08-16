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
from services.category_bids import bid_standing, active_bids_for

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
    await sweep_topups(db)  # refill low budgets before showing status
    await sweep_autopilot(db)  # keep autopilot bid current before showing status
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
    cards: Dict[str, Any] = {"cards": [], "default_id": None}
    try:
        from services.saved_cards_service import ensure_stripe_customer, list_cards
        cust = await ensure_stripe_customer(db, user)
        if cust:
            cards = list_cards(cust)
    except Exception:
        pass
    return {"business_id": p["business_id"], "public_name": p.get("public_name"),
            "bid": _clean(dict(b)) if b else None, "standing": standing, "budget": low,
            "saved_cards": cards.get("cards", []), "default_pm": cards.get("default_id")}


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



class AutoTopupBody(BaseModel):
    enabled: bool
    amount_cents: int = Field(1000, ge=500, le=1000000)
    payment_method_id: Optional[str] = None


@router.post("/auto-topup")
async def set_auto_topup(body: AutoTopupBody, request: Request, user: dict = Depends(current_user)):
    """Auto-refill the prepaid spotlight budget from a saved card when it runs low."""
    db = request.app.state.db
    p = await _my_business(db, user)
    b = await db.category_bids.find_one({"business_id": p["business_id"]})
    if not b:
        raise HTTPException(400, {"code": "set_bid_first"})
    await db.category_bids.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"auto_topup": bool(body.enabled),
                  "auto_topup_amount_cents": int(body.amount_cents),
                  "auto_topup_pm": body.payment_method_id or b.get("auto_topup_pm"),
                  "updated_at": _now()}})
    return {"ok": True, "auto_topup": bool(body.enabled)}


_last_topup_sweep: Dict[str, Any] = {"ts": None}


async def sweep_topups(db, throttle_seconds: int = 45):
    """Off-session refill low/depleted spotlight budgets that have auto-topup on.
    Throttled so read-path callers stay cheap."""
    now = _now()
    if _last_topup_sweep["ts"] and (now - _last_topup_sweep["ts"]).total_seconds() < throttle_seconds:
        return {"skipped": True}
    _last_topup_sweep["ts"] = now
    refilled = 0
    async for b in db.category_bids.find({"auto_topup": True}):
        bid = int(b.get("bid_cents", 0) or 0)
        amt = int(b.get("auto_topup_amount_cents", 0) or 0)
        if bid <= 0 or amt <= 0:
            continue
        if int(b.get("budget_cents", 0)) >= 20 * bid:  # only when < ~20 impressions left
            continue
        pm = b.get("auto_topup_pm")
        try:
            from services.saved_cards_service import (ensure_stripe_customer, list_cards,
                                                      charge_saved_card, owns_payment_method)
            u = await db.users.find_one({"user_id": b.get("owner_user_id")})
            cust = await ensure_stripe_customer(db, u) if u else None
            if cust and not owns_payment_method(cust, pm):
                pm = (list_cards(cust) or {}).get("default_id")
            if not (cust and pm and owns_payment_method(cust, pm)):
                continue
            charge_saved_card(amount_cents=amt, cust_id=cust, pm_id=pm,
                              description=f"Category Spotlight auto top-up — {b.get('public_name')}",
                              metadata={"kind": "category_topup_auto", "business_id": b.get("business_id")})
            await db.category_bids.update_one(
                {"bid_id": b["bid_id"]},
                {"$inc": {"budget_cents": amt}, "$set": {"status": "active", "updated_at": now}})
            await db.category_topups.insert_one({
                "session_id": f"auto_{uuid.uuid4().hex[:10]}", "bid_id": b["bid_id"],
                "business_id": b.get("business_id"), "amount_cents": amt,
                "status": "credited", "auto": True, "created_at": now})
            refilled += 1
        except Exception:
            continue
    return {"refilled": refilled}


class AutopilotBody(BaseModel):
    enabled: bool
    target_rank: int = Field(1, ge=1, le=5)
    max_bid_cents: int = Field(20, ge=1, le=1000)


@router.post("/autopilot")
async def set_autopilot(body: AutopilotBody, request: Request, user: dict = Depends(current_user)):
    """Auto-adjust the per-impression bid to hold a target category rank, capped at max_bid."""
    db = request.app.state.db
    p = await _my_business(db, user)
    b = await db.category_bids.find_one({"business_id": p["business_id"]})
    if not b:
        raise HTTPException(400, {"code": "set_bid_first"})
    await db.category_bids.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"autopilot": bool(body.enabled), "target_rank": int(body.target_rank),
                  "autopilot_max_bid_cents": int(body.max_bid_cents), "updated_at": _now()}})
    if body.enabled:
        await sweep_autopilot(db, throttle_seconds=0)  # apply immediately
    b = await db.category_bids.find_one({"business_id": p["business_id"]})
    standing = await bid_standing(db, b["category"], p["business_id"]) if b and b.get("category") else None
    return {"ok": True, "autopilot": bool(body.enabled),
            "bid": _clean(dict(b)) if b else None, "standing": standing}


_last_autopilot_sweep: Dict[str, Any] = {"ts": None}


async def sweep_autopilot(db, throttle_seconds: int = 30):
    """Nudge each autopilot bid to the minimum ¢ needed to hold its target rank,
    never exceeding the merchant's max-bid cap (auto-raises AND auto-lowers to save budget)."""
    now = _now()
    if throttle_seconds and _last_autopilot_sweep["ts"] and \
            (now - _last_autopilot_sweep["ts"]).total_seconds() < throttle_seconds:
        return {"skipped": True}
    _last_autopilot_sweep["ts"] = now
    adjusted = 0
    async for b in db.category_bids.find(
            {"autopilot": True, "status": {"$in": ["active", "pending_budget", "depleted"]}}):
        cat = b.get("category")
        maxbid = int(b.get("autopilot_max_bid_cents", 0) or 0)
        if not cat or maxbid <= 0:
            continue
        target = max(1, min(5, int(b.get("target_rank", 1) or 1)))
        comps = sorted(
            [int(x.get("bid_cents", 0)) for x in await active_bids_for(db, cat)
             if x.get("business_id") != b.get("business_id")], reverse=True)
        needed = (comps[target - 1] + 1) if len(comps) >= target else 1
        new_bid = max(1, min(needed, maxbid))
        if new_bid == int(b.get("bid_cents", 0)):
            continue
        budget = int(b.get("budget_cents", 0))
        status = "active" if budget >= new_bid else "pending_budget"
        await db.category_bids.update_one(
            {"bid_id": b["bid_id"]},
            {"$set": {"bid_cents": new_bid, "autopilot_last_bid_cents": new_bid,
                      "autopilot_adjusted_at": now, "status": status, "updated_at": now}})
        adjusted += 1
    return {"adjusted": adjusted}


__all__ = ["router"]