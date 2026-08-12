"""Marketplace Orders API — Restaurant Pickup (Phase B).

Consumer cart checkout (single-merchant), gift-card auto-apply, Stripe
payment, and the order lifecycle (accepted → preparing → ready → picked_up).
BigPoints are awarded to the buyer when the order is marked picked_up.
"""
from __future__ import annotations

import os
import random
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.marketplace import now, new_id, effective_points
from services.points_service import PointsService
from services.marketplace_coupons import compute_coupon_discount, record_coupon_redemption

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

REDEEM_POINTS_PER_DOLLAR = 100  # 100 BigPoints == $1 when redeeming at checkout


def _points_to_cents(points: int) -> int:
    return int((max(0, int(points or 0)) * 100) // REDEEM_POINTS_PER_DOLLAR)


def _cents_to_max_points(cents: int) -> int:
    return int(max(0, int(cents or 0)) * REDEEM_POINTS_PER_DOLLAR // 100)

router = APIRouter(prefix="/api/shop/orders", tags=["marketplace-orders"])
merchant_router = APIRouter(prefix="/api/merchant/marketplace/orders",
                            tags=["marketplace-merchant-orders"])

LIFECYCLE = ["pending_payment", "accepted", "preparing", "ready", "picked_up", "canceled"]
ADVANCE = {"accepted": "preparing", "preparing": "ready", "ready": "picked_up"}


def _clean(o: Dict[str, Any]) -> Dict[str, Any]:
    o.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = o.get(k)
        if hasattr(v, "isoformat"):
            o[k] = v.isoformat()
    for h in o.get("status_history", []) or []:
        v = h.get("at")
        if hasattr(v, "isoformat"):
            h["at"] = v.isoformat()
    return o


async def _pick_gift_card(db, user, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    uid = user.get("user_id")
    email = (user.get("email") or "").lower()
    owner = [{"owner_user_id": uid}, {"gifted_to_email": email}]
    best = None
    async for c in db.gift_cards.find(
            {"status": "active", "balance_cents": {"$gt": 0}, "$or": owner}):
        cb = c.get("business_id")
        # Venue-scoped cards only apply at their own venue; generic cards apply anywhere.
        if cb and business_id and cb != business_id:
            continue
        exact = bool(cb and business_id and cb == business_id)
        best_exact = bool(best and best.get("business_id") == business_id and business_id)
        if best is None:
            best = c
        elif exact and not best_exact:
            best = c  # prefer a card scoped to this venue
        elif exact == best_exact and c.get("balance_cents", 0) > best.get("balance_cents", 0):
            best = c
    return best


async def _deduct_gift_card(db, card_id: str, amount_cents: int, user) -> None:
    card = await db.gift_cards.find_one({"card_id": card_id})
    if not card:
        return
    bal = int(card.get("balance_cents", 0))
    take = min(bal, amount_cents)
    new_bal = bal - take
    await db.gift_cards.update_one(
        {"card_id": card_id},
        {"$set": {"balance_cents": new_bal,
                  "status": "active" if new_bal > 0 else "spent", "updated_at": now()}})
    await db.gift_card_redemptions.insert_one({
        "redemption_id": new_id("gcr"), "card_id": card_id,
        "user_id": user.get("user_id"), "amount_cents": take,
        "balance_after_cents": new_bal, "source": "marketplace_order",
        "created_at": now()})


class CheckoutItem(BaseModel):
    item_id: str
    qty: int = Field(1, ge=1, le=50)


async def _price_menu(db, user, business_id: str, items: List["CheckoutItem"],
                      use_gift_card: bool, redeem_points: int,
                      coupon_code: Optional[str] = None) -> Dict[str, Any]:
    """Validate + price a single-restaurant basket with optional coupon +
    gift-card + BigPoints redemption. Shared by /quote and /checkout."""
    profile = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True})
    if not profile:
        raise HTTPException(404, {"code": "business_unavailable"})
    line_items: List[Dict[str, Any]] = []
    subtotal = 0
    for ci in items:
        it = await db.menu_items.find_one(
            {"item_id": ci.item_id, "business_id": business_id, "available": True})
        if not it:
            raise HTTPException(400, {"code": "item_unavailable", "item_id": ci.item_id})
        price = int(it.get("price_cents", 0))
        subtotal += price * ci.qty
        line_items.append({"item_id": ci.item_id, "name": it.get("name"),
                           "price_cents": price, "qty": ci.qty})
    if subtotal <= 0:
        raise HTTPException(400, {"code": "zero_total"})

    coupon_discount, coupon_doc, coupon_error = await compute_coupon_discount(
        db, business_id=business_id, code=coupon_code,
        user_id=user.get("user_id"), base_cents=subtotal)
    after_coupon = subtotal - coupon_discount

    gift_card = await _pick_gift_card(db, user, business_id)
    gift_available = int(gift_card.get("balance_cents", 0)) if gift_card else 0
    gift_applied = min(gift_available, after_coupon) if (use_gift_card and gift_card) else 0
    after_gift = after_coupon - gift_applied

    balance = await PointsService(db).get_balance(user.get("user_id"))
    max_redeemable = min(int(balance or 0), _cents_to_max_points(after_gift))
    used_points = max(0, min(int(redeem_points or 0), max_redeemable))
    points_discount = _points_to_cents(used_points)
    total = after_gift - points_discount
    eff = effective_points(profile)
    return {
        "profile": profile, "line_items": line_items, "subtotal_cents": subtotal,
        "gift_card_id": gift_card.get("card_id") if gift_card else None,
        "gift_available_cents": gift_available, "gift_applied_cents": gift_applied,
        "coupon_discount_cents": coupon_discount, "coupon_error": coupon_error,
        "coupon_code": (coupon_doc or {}).get("code") if coupon_discount > 0 else None,
        "coupon_id": (coupon_doc or {}).get("coupon_id") if coupon_discount > 0 else None,
        "points_balance": int(balance or 0), "redeem_points_per_dollar": REDEEM_POINTS_PER_DOLLAR,
        "max_redeemable_points": max_redeemable, "redeemed_points": used_points,
        "points_discount_cents": points_discount, "total_cents": total,
        "points_to_award": int(eff.get("points", 0)), "happy_hour": eff.get("happy_hour", False),
        "points_multiplier": eff.get("multiplier", 1),
    }


class QuoteBody(BaseModel):
    business_id: str
    items: List[CheckoutItem]
    use_gift_card: bool = False
    redeem_points: int = Field(0, ge=0)
    coupon_code: Optional[str] = None


@router.post("/quote")
async def quote(body: QuoteBody, request: Request, user: dict = Depends(current_user)):
    """Live price breakdown for the checkout screen — no order is created."""
    if not body.items:
        raise HTTPException(400, {"code": "empty_cart"})
    db = request.app.state.db
    q = await _price_menu(db, user, body.business_id, body.items,
                          body.use_gift_card, body.redeem_points, body.coupon_code)
    q.pop("profile", None)
    q["public_name"] = None
    return q


class CheckoutBody(BaseModel):
    business_id: str
    items: List[CheckoutItem]
    origin_url: Optional[str] = None
    use_gift_card: bool = False
    redeem_points: int = Field(0, ge=0)
    note: Optional[str] = Field(None, max_length=300)
    payment_method_id: Optional[str] = None  # saved card → one-tap off-session
    coupon_code: Optional[str] = None


@router.post("/checkout")
async def checkout(body: CheckoutBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    if not body.items:
        raise HTTPException(400, {"code": "empty_cart"})
    q = await _price_menu(db, user, body.business_id, body.items,
                          body.use_gift_card, body.redeem_points, body.coupon_code)
    profile = q["profile"]
    line_items = q["line_items"]
    subtotal = q["subtotal_cents"]
    gift_applied = q["gift_applied_cents"]
    gift_card_id = q["gift_card_id"] if gift_applied > 0 else None
    redeemed_points = q["redeemed_points"]
    points_discount = q["points_discount_cents"]
    total = q["total_cents"]

    pickup_code = f"{random.randint(0, 9999):04d}"
    order_id = new_id("ord")
    order = {
        "order_id": order_id, "business_id": body.business_id,
        "business_name": profile.get("public_name"),
        "user_id": user.get("user_id"), "items": line_items,
        "subtotal_cents": subtotal, "gift_card_applied_cents": gift_applied,
        "gift_card_id": gift_card_id,
        "coupon_id": q.get("coupon_id"), "coupon_code": q.get("coupon_code"),
        "coupon_discount_cents": q.get("coupon_discount_cents", 0),
        "coupon_recorded_done": False,
        "redeemed_points": redeemed_points, "points_discount_cents": points_discount,
        "points_redeemed_done": False,
        "total_cents": total,
        "points_to_award": q["points_to_award"], "points_multiplier": q["points_multiplier"],
        "happy_hour": q["happy_hour"], "points_awarded_done": False,
        "note": body.note, "pickup_code": pickup_code,
        "status": "pending_payment", "payment_status": "pending",
        "session_id": None, "status_history": [],
        "created_at": now(), "updated_at": now(),
    }

    if total <= 0:
        # Fully covered by coupon/gift card/points — no Stripe needed.
        if gift_card_id:
            await _deduct_gift_card(db, gift_card_id, gift_applied, user)
        await _redeem_points(db, user, order)
        await _record_order_coupon(db, order)
        order["status"] = "accepted"
        order["payment_status"] = "paid"
        order["status_history"] = [{"status": "accepted", "at": now()}]
        await db.marketplace_orders.insert_one(dict(order))
        await notify_merchant_new_order(
            db, business_id=body.business_id, order_id=order_id, kind="food",
            total_cents=0, code=pickup_code)
        return {"ok": True, "order_id": order_id, "status": "accepted",
                "checkout_url": None, "total_cents": 0,
                "gift_card_applied_cents": gift_applied,
                "coupon_discount_cents": q.get("coupon_discount_cents", 0),
                "points_discount_cents": points_discount, "pickup_code": pickup_code}

    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})

    # One-tap: charge a saved card off-session. On success the order is paid
    # immediately (no redirect); card errors fall through to hosted Checkout.
    if body.payment_method_id:
        from services.saved_cards_service import ensure_stripe_customer, charge_saved_card, owns_payment_method
        cust = await ensure_stripe_customer(db, user)
        if owns_payment_method(cust, body.payment_method_id):
            try:
                pi = charge_saved_card(
                    amount_cents=total, cust_id=cust, pm_id=body.payment_method_id,
                    metadata={"kind": "marketplace_order", "order_id": order_id,
                              "business_id": body.business_id})
                if pi.status == "succeeded":
                    order["payment_intent_id"] = pi.id
                    await db.marketplace_orders.insert_one(dict(order))
                    await _finalize_paid(db, order, user)
                    return {"ok": True, "order_id": order_id, "status": "accepted",
                            "payment_status": "paid", "paid": True, "checkout_url": None,
                            "total_cents": total, "gift_card_applied_cents": gift_applied,
                            "points_discount_cents": points_discount, "pickup_code": pickup_code}
            except stripe.error.CardError:
                pass  # SCA required / declined — fall back to hosted checkout

    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
                     "product_data": {"name": f"{profile.get('public_name')} — Pickup Order"},
                     "unit_amount": total}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "marketplace_order", "order_id": order_id,
                  "business_id": body.business_id})
    order["session_id"] = session.id
    await db.marketplace_orders.insert_one(dict(order))
    return {"ok": True, "order_id": order_id, "status": "pending_payment",
            "checkout_url": session.url, "session_id": session.id,
            "total_cents": total, "gift_card_applied_cents": gift_applied,
            "points_discount_cents": points_discount, "pickup_code": pickup_code}


async def _redeem_points(db, user, order: Dict[str, Any]) -> None:
    """Spend redeemed BigPoints once per order (idempotent)."""
    pts = int(order.get("redeemed_points", 0) or 0)
    if pts <= 0 or order.get("points_redeemed_done"):
        return
    try:
        await PointsService(db).spend(
            user_id=user.get("user_id"), source="marketplace_redeem", amount=pts,
            source_id=order["order_id"], idempotency_key=f"order_redeem:{order['order_id']}",
            metadata={"order_id": order["order_id"], "business_id": order.get("business_id")})
    except Exception:
        pass
    await db.marketplace_orders.update_one(
        {"order_id": order["order_id"]}, {"$set": {"points_redeemed_done": True}})
    order["points_redeemed_done"] = True


async def notify_merchant_new_order(db, *, business_id: str, order_id: str,
                                    kind: str, total_cents: int = 0,
                                    code: Optional[str] = None) -> None:
    """Alert the shop owner in-app when a new paid order arrives (idempotent)."""
    try:
        prof = await db.marketplace_profiles.find_one(
            {"business_id": business_id}, {"owner_user_id": 1, "public_name": 1})
        owner = (prof or {}).get("owner_user_id")
        if not owner:
            return
        from routes.notifications import _enqueue
        name = (prof or {}).get("public_name") or "Your shop"
        label = "pickup order" if kind == "food" else "product order"
        code_txt = f" #{code}" if code else ""
        await _enqueue(
            db, owner_user_id=owner, station_id="marketplace",
            station_slug="marketplace", type_="merchant_new_order",
            payload={"title": "New order! 🛎️",
                     "body": f"{name} · new {label}{code_txt} · ${total_cents / 100:.2f}",
                     "order_id": order_id, "kind": kind},
            dedupe_key=f"merchant_new_order_{order_id}")
    except Exception:
        pass


async def _record_order_coupon(db, order: Dict[str, Any]) -> None:
    """Record the coupon redemption once per order (idempotent)."""
    if not order.get("coupon_id") or order.get("coupon_recorded_done"):
        return
    coupon = await db.marketplace_coupons.find_one({"coupon_id": order["coupon_id"]})
    await record_coupon_redemption(
        db, coupon=coupon, user_id=order.get("user_id"),
        order_id=order["order_id"], discount_cents=int(order.get("coupon_discount_cents", 0) or 0))
    await db.marketplace_orders.update_one(
        {"order_id": order["order_id"]}, {"$set": {"coupon_recorded_done": True}})
    order["coupon_recorded_done"] = True


async def _finalize_paid(db, order: Dict[str, Any], user) -> None:
    """Called once when payment confirmed — deduct gift card + points, record
    the coupon, move to accepted."""
    if order.get("payment_status") == "paid":
        return
    if order.get("gift_card_id") and order.get("gift_card_applied_cents", 0) > 0:
        await _deduct_gift_card(db, order["gift_card_id"],
                                order["gift_card_applied_cents"], user)
    await _redeem_points(db, user, order)
    await _record_order_coupon(db, order)
    await db.marketplace_orders.update_one(
        {"order_id": order["order_id"], "payment_status": {"$ne": "paid"}},
        {"$set": {"payment_status": "paid", "status": "accepted", "updated_at": now()},
         "$push": {"status_history": {"status": "accepted", "at": now()}}})
    await notify_merchant_new_order(
        db, business_id=order.get("business_id"), order_id=order["order_id"],
        kind="food", total_cents=int(order.get("total_cents", 0) or 0),
        code=order.get("pickup_code"))


@router.post("/{order_id}/reorder")
async def reorder(order_id: str, request: Request, user: dict = Depends(current_user)):
    """Return the still-available items from a past order so the client can
    re-fill the cart (prices refreshed from the current menu)."""
    db = request.app.state.db
    o = await db.marketplace_orders.find_one(
        {"order_id": order_id, "user_id": user.get("user_id")})
    if not o:
        raise HTTPException(404, {"code": "order_not_found"})
    profile = await db.marketplace_profiles.find_one(
        {"business_id": o["business_id"], "status": "approved", "subscription_active": True})
    if not profile:
        raise HTTPException(400, {"code": "business_unavailable"})
    items, dropped = [], []
    for li in o.get("items", []):
        it = await db.menu_items.find_one(
            {"item_id": li["item_id"], "business_id": o["business_id"], "available": True})
        if it:
            items.append({"item_id": it["item_id"], "name": it.get("name"),
                          "price_cents": int(it.get("price_cents", 0)), "qty": li.get("qty", 1)})
        else:
            dropped.append(li.get("name"))
    if not items:
        raise HTTPException(400, {"code": "nothing_available"})
    return {"ok": True, "business_id": o["business_id"],
            "business_name": profile.get("public_name"), "items": items, "dropped": dropped}


@router.get("")
async def my_orders(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    items = [_clean(o) async for o in db.marketplace_orders.find(
        {"user_id": user.get("user_id")}).sort("created_at", -1).limit(50)]
    return {"items": items}


@router.get("/{order_id}")
async def order_detail(order_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    o = await db.marketplace_orders.find_one(
        {"order_id": order_id, "user_id": user.get("user_id")})
    if not o:
        raise HTTPException(404, {"code": "order_not_found"})
    return {"order": _clean(o)}


@router.get("/{order_id}/status")
async def order_status(order_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    o = await db.marketplace_orders.find_one(
        {"order_id": order_id, "user_id": user.get("user_id")})
    if not o:
        raise HTTPException(404, {"code": "order_not_found"})
    if o.get("payment_status") != "paid" and o.get("session_id") and stripe.api_key:
        try:
            sess = stripe.checkout.Session.retrieve(o["session_id"])
            if sess.get("payment_status") == "paid" or sess.get("status") == "complete":
                await _finalize_paid(db, o, user)
                o = await db.marketplace_orders.find_one({"order_id": order_id})
        except Exception:
            pass
    return {"status": o.get("status"), "payment_status": o.get("payment_status"),
            "order": _clean(o)}


# ───────────── Merchant order management ─────────────
async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


@merchant_router.get("")
async def merchant_orders(request: Request, status: Optional[str] = None,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    q: Dict[str, Any] = {"business_id": p["business_id"]}
    if status:
        q["status"] = status
    else:
        q["payment_status"] = "paid"  # merchants only see paid orders by default
    items = [_clean(o) async for o in db.marketplace_orders.find(q).sort("created_at", -1).limit(80)]
    return {"items": items}


@merchant_router.get("/new-count")
async def merchant_new_order_count(request: Request, user: dict = Depends(current_user)):
    """Count of orders awaiting the merchant's first action (food: accepted,
    products: paid) — powers the dashboard new-order alert badge."""
    db = request.app.state.db
    p = await _my_business(db, user)
    food = await db.marketplace_orders.count_documents(
        {"business_id": p["business_id"], "payment_status": "paid", "status": "accepted"})
    products = await db.product_orders.count_documents(
        {"business_id": p["business_id"], "status": "paid"})
    return {"food": food, "products": products, "total": food + products}


class StatusBody(BaseModel):
    status: str


@merchant_router.patch("/{order_id}/status")
async def update_order_status(order_id: str, body: StatusBody, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    o = await db.marketplace_orders.find_one(
        {"order_id": order_id, "business_id": p["business_id"]})
    if not o:
        raise HTTPException(404, {"code": "order_not_found"})
    new_status = body.status
    if new_status == "canceled":
        if o.get("status") in ("picked_up", "canceled"):
            raise HTTPException(400, {"code": "cannot_cancel", "status": o.get("status")})
    elif ADVANCE.get(o.get("status")) != new_status:
        raise HTTPException(400, {"code": "invalid_transition",
                                  "from": o.get("status"), "to": new_status})
    if o.get("payment_status") != "paid" and new_status != "canceled":
        raise HTTPException(400, {"code": "order_unpaid"})

    upd: Dict[str, Any] = {"status": new_status, "updated_at": now()}
    await db.marketplace_orders.update_one(
        {"order_id": order_id},
        {"$set": upd, "$push": {"status_history": {"status": new_status, "at": now()}}})

    # Live order alerts — notify the buyer in-app on key transitions.
    if new_status in ("ready", "picked_up"):
        try:
            from routes.notifications import _enqueue
            biz = p.get("public_name") or "Your order"
            if new_status == "ready":
                title, bodytxt = "Order Ready for Pickup! 🎉", f"{biz} · order #{o.get('pickup_code')} is ready. Head over!"
            else:
                title, bodytxt = "Enjoy! 🥡", f"{biz} · order #{o.get('pickup_code')} picked up. BigPoints on the way!"
            await _enqueue(
                db, owner_user_id=o["user_id"], station_id="marketplace",
                station_slug="marketplace", type_=f"order_{new_status}",
                payload={"title": title, "body": bodytxt, "order_id": order_id,
                         "pickup_code": o.get("pickup_code"), "business_name": biz},
                dedupe_key=f"order_{new_status}_{order_id}")
        except Exception:
            pass

    # Award BigPoints to the buyer on pickup (idempotent).
    if new_status == "picked_up" and not o.get("points_awarded_done"):
        pts = int(o.get("points_to_award", 0))
        if pts > 0:
            from services.loyalty import award_with_tier_bonus
            await award_with_tier_bonus(
                db, user_id=o["user_id"], source="marketplace_order",
                source_id=order_id, base_points=pts,
                idempotency_key=f"order_pickup_{order_id}",
                metadata={"business_id": p["business_id"], "note": "Pickup order reward"})
            # Deduct from prepaid BigPoints inventory if that's the funding mode.
            await db.merchant_bigpoint_accounts.update_one(
                {"business_id": p["business_id"], "funding_mode": "prepaid"},
                {"$inc": {"balance_points": -pts}, "$set": {"updated_at": now()}})
        await db.marketplace_orders.update_one(
            {"order_id": order_id}, {"$set": {"points_awarded_done": True}})

    o = await db.marketplace_orders.find_one({"order_id": order_id})
    return {"ok": True, "order": _clean(o)}


__all__ = ["router", "merchant_router"]
