"""Marketplace Orders API — Restaurant Pickup (Phase B).

Consumer cart checkout (single-merchant), gift-card auto-apply, Stripe
payment, and the order lifecycle (accepted → preparing → ready → picked_up).
BigPoints are awarded to the buyer when the order is marked picked_up.
"""
from __future__ import annotations

import logging
import os
import random
from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from auth import current_user
from services.marketplace import now, new_id, effective_points, points_for_order
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
    for k in ("created_at", "updated_at", "ready_at"):
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
    selected_option_ids: List[str] = Field(default_factory=list)
    apply_entitlement_id: Optional[str] = None
    note: Optional[str] = Field(None, max_length=140)


def _compute_fees(profile: Dict[str, Any], base_cents: int, fulfillment: str) -> tuple:
    """Merchant-configurable owner.com-style fees added ON TOP of the goods
    (never discounted by gift card / points). Returns (service_fee, delivery_fee)."""
    sf = profile.get("service_fee") or {}
    service_fee = int(round(base_cents * float(sf.get("percent", 0) or 0) / 100.0)) if sf.get("enabled") else 0
    dl = profile.get("delivery") or {}
    delivery_fee = int(dl.get("fee_cents", 0) or 0) if (fulfillment == "delivery" and dl.get("enabled")) else 0
    return service_fee, delivery_fee


def _eta_label(profile: Dict[str, Any], fulfillment: str, pickup_time: Optional[str]) -> str:
    prep = int(profile.get("prep_time_min", 20) or 20)
    if fulfillment == "delivery":
        dl = profile.get("delivery") or {}
        lo, hi = int(dl.get("eta_min", prep + 20) or 0), int(dl.get("eta_max", prep + 35) or 0)
        return f"{lo}–{hi} min"
    offset = {"now": 0, "+15": 15, "+30": 30, "+45": 45}.get(pickup_time or "now", 0)
    return f"Ready in ~{offset} min" if offset else f"Ready in ~{prep} min"


def _eta_minutes(profile: Dict[str, Any], fulfillment: str, pickup_time: Optional[str]) -> int:
    """Estimated minutes until the order is ready (pickup) / arrives (delivery).
    Powers the live countdown timer on the order tracker."""
    prep = int(profile.get("prep_time_min", 20) or 20)
    if fulfillment == "delivery":
        dl = profile.get("delivery") or {}
        return int(dl.get("eta_max", prep + 35) or (prep + 35))
    return {"now": prep, "+15": 15, "+30": 30, "+45": 45}.get(pickup_time or "now", prep)


def _ready_at(profile: Dict[str, Any], fulfillment: str, pickup_time: Optional[str]):
    """Absolute timestamp the order is expected ready/arrived (for the timer)."""
    return now() + timedelta(minutes=_eta_minutes(profile, fulfillment, pickup_time))


_DRINK_KW = ("coffee", "drink", "beverage", "tea", "juice", "soda", "shake",
             "latte", "smoothie", "cola", "water", "mocktail")
_ADDON_KW = _DRINK_KW + ("dessert", "side", "extra", "sauce", "topping", "add-on", "addon")


def _auto_combo(line_meta: List[Dict[str, Any]]):
    """Default combo when a merchant hasn't defined any: 30% off one drink when
    the basket has a main + a drink."""
    drink_units = [m["unit"] for m in line_meta
                   if any(k in (m["section"] or "").lower() for k in _DRINK_KW)]
    has_main = any(not any(k in (m["section"] or "").lower() for k in _ADDON_KW) for m in line_meta)
    if has_main and drink_units:
        return int(round(min(drink_units) * 0.30)), ["Meal combo"]
    return 0, []


def _apply_combos(combos: List[Dict[str, Any]], line_meta: List[Dict[str, Any]]):
    """Merchant-defined combos. Each combo = {name, price_cents, requirements:
    [{category, qty}]}. A combo fires whenever the basket contains enough
    units matching every requirement (cheapest units chosen); it applies
    repeatedly while it keeps matching. Discount = regular total − combo price."""
    units: List[Dict[str, Any]] = []
    for m in line_meta:
        for _ in range(int(m.get("qty", 1) or 1)):
            units.append({"section": (m["section"] or "").lower(), "unit": m["unit"], "used": False})
    total, names = 0, []
    for c in combos:
        reqs = c.get("requirements") or []
        price = int(c.get("price_cents", 0) or 0)
        if not reqs:
            continue
        guard = 0
        while guard < 20:
            guard += 1
            chosen, picked, ok = [], set(), True
            for req in reqs:
                cat = (req.get("category") or "").lower().strip()
                need = int(req.get("qty", 1) or 1)
                cands = sorted([u for u in units if not u["used"] and id(u) not in picked and cat and cat in u["section"]],
                               key=lambda x: x["unit"])
                if len(cands) < need:
                    ok = False
                    break
                for u in cands[:need]:
                    picked.add(id(u))
                    chosen.append(u)
            if not ok:
                break
            disc = sum(u["unit"] for u in chosen) - price
            if disc <= 0:
                break
            for u in chosen:
                u["used"] = True
            total += disc
            names.append(c.get("name") or "Combo")
    return total, list(dict.fromkeys(names))


async def _price_menu(db, user, business_id: str, items: List["CheckoutItem"],
                      use_gift_card: bool, redeem_points: int,
                      coupon_code: Optional[str] = None,
                      fulfillment: str = "pickup",
                      pickup_time: Optional[str] = "now",
                      delivery_address: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate + price a single-restaurant basket with option upcharges, an
    optional membership entitlement (base free + included-option waivers),
    coupon, gift-card and BigPoints redemption. Shared by /quote and /checkout."""
    from services.membership_entitlements import (
        validate_selection, price_with_options, evaluate_line_entitlement, find_join_nudge)
    profile = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True})
    if not profile:
        raise HTTPException(404, {"code": "business_unavailable"})
    # Coerce to pickup if the shop doesn't deliver, so fees + ETA stay consistent.
    if fulfillment == "delivery" and not (profile.get("delivery") or {}).get("enabled"):
        fulfillment = "pickup"
    line_items: List[Dict[str, Any]] = []
    line_meta: List[Dict[str, Any]] = []
    subtotal = 0
    entitlement_discount = 0
    applied_entitlements: List[Dict[str, Any]] = []
    nudge_items: List[Dict[str, Any]] = []
    has_coupon = bool(coupon_code)
    for ci in items:
        it = await db.menu_items.find_one(
            {"item_id": ci.item_id, "business_id": business_id, "available": True})
        if not it:
            raise HTTPException(400, {"code": "item_unavailable", "item_id": ci.item_id})
        base = int(it.get("price_cents", 0))
        nudge_items.append({"item_id": ci.item_id, "category": it.get("section"),
                            "base_cents": base, "name": it.get("name")})
        ogs = it.get("option_groups", []) or []
        sel = ci.selected_option_ids or []
        sel_err = validate_selection(ogs, sel)
        if sel_err:
            raise HTTPException(400, {"code": sel_err, "item_id": ci.item_id})
        unit_price, selected_detail = price_with_options(base, ogs, sel)
        line = {"item_id": ci.item_id, "name": it.get("name"), "price_cents": unit_price,
                "qty": ci.qty, "selected_options": selected_detail}
        if ci.note:
            line["note"] = ci.note.strip()[:140]
        if ci.apply_entitlement_id:
            ev = await evaluate_line_entitlement(
                db, user, business_id, item_id=ci.item_id, category=it.get("section"),
                base_cents=base, option_groups=ogs, selected_option_ids=sel,
                apply_entitlement_id=ci.apply_entitlement_id, has_coupon=has_coupon)
            if not ev.get("applicable"):
                detail = {"code": ev.get("error", "entitlement_not_applicable"), "item_id": ci.item_id}
                if ev.get("max_upcharge_cents") is not None:
                    detail["max_upcharge_cents"] = ev["max_upcharge_cents"]
                raise HTTPException(400, detail)
            ent, mem = ev["entitlement"], ev["membership"]
            entitlement_discount += int(ev["discount_cents"])
            line["entitlement_id"] = ci.apply_entitlement_id
            line["entitlement_discount_cents"] = int(ev["discount_cents"])
            applied_entitlements.append({
                "entitlement_id": ci.apply_entitlement_id, "membership_id": mem["membership_id"],
                "item_id": ci.item_id, "base_value_cents": int(ev["discount_cents"]),
                "upcharge_cents": int(ev.get("charged_upcharge_cents", 0)),
                "reset_frequency": ent.get("reset_frequency", "monthly"), "label": ent.get("label")})
        subtotal += unit_price * ci.qty
        line_meta.append({"section": it.get("section") or "", "unit": unit_price, "qty": ci.qty})
        line_items.append(line)
    if subtotal <= 0:
        raise HTTPException(400, {"code": "zero_total"})

    after_entitlement = max(0, subtotal - entitlement_discount)
    coupon_discount, coupon_doc, coupon_error = await compute_coupon_discount(
        db, business_id=business_id, code=coupon_code,
        user_id=user.get("user_id"), base_cents=after_entitlement)
    after_coupon = after_entitlement - coupon_discount

    # "Make it a meal" combos — merchant-defined if any, else the default
    # 30%-off-a-drink. Server-enforced so /quote and /checkout stay in sync.
    combos = [c async for c in db.marketplace_combos.find({"business_id": business_id, "active": True})]
    from services.combos import combo_active_now
    combos = [c for c in combos if combo_active_now(c)]
    combo_raw, combo_names = _apply_combos(combos, line_meta) if combos else _auto_combo(line_meta)
    combo_discount = min(combo_raw, max(0, after_coupon))
    combo_applied = combo_discount > 0
    combo_names = combo_names if combo_applied else []
    after_combo = after_coupon - combo_discount

    gift_card = await _pick_gift_card(db, user, business_id)
    gift_available = int(gift_card.get("balance_cents", 0)) if gift_card else 0
    gift_applied = min(gift_available, after_combo) if (use_gift_card and gift_card) else 0
    after_gift = after_combo - gift_applied

    balance = await PointsService(db).get_balance(user.get("user_id"))
    max_redeemable = min(int(balance or 0), _cents_to_max_points(after_gift))
    used_points = max(0, min(int(redeem_points or 0), max_redeemable))
    points_discount = _points_to_cents(used_points)
    goods_total = after_gift - points_discount
    service_fee_cents, delivery_fee_cents = _compute_fees(profile, subtotal, fulfillment)
    fees_total = service_fee_cents + delivery_fee_cents
    # Sales tax. Delivery → charge at the CUSTOMER's jurisdiction (destination);
    # pickup → the store's local rate (origin), honouring a merchant override.
    from services.tax_service import resolve_tax_rate, calculate_tax
    if (fulfillment == "delivery" and delivery_address
            and (delivery_address.get("country") or delivery_address.get("state")
                 or delivery_address.get("city"))):
        tax_info = await resolve_tax_rate(db, {
            "country": delivery_address.get("country"),
            "state": delivery_address.get("state"),
            "county": delivery_address.get("county"),
            "city": delivery_address.get("city")})
        tax_basis = "destination"
    else:
        override = profile.get("tax_override") or {}
        if override.get("enabled") and override.get("rate_percent") is not None:
            tax_info = {"rate_percent": float(override.get("rate_percent") or 0),
                        "label": override.get("label") or "Local tax", "rule_id": None}
        else:
            tax_info = await resolve_tax_rate(db, profile.get("tax_jurisdiction") or {})
        tax_basis = "origin"
    taxable_base = max(0, after_combo) + service_fee_cents + delivery_fee_cents
    tax_cents = calculate_tax(taxable_base, tax_info["rate_percent"])
    total = goods_total + fees_total + tax_cents
    eff = points_for_order(profile, after_entitlement)
    join_nudge = None
    if entitlement_discount <= 0:
        join_nudge = await find_join_nudge(db, user, business_id, nudge_items)
    return {
        "profile": profile, "line_items": line_items, "subtotal_cents": subtotal,
        "entitlement_discount_cents": entitlement_discount,
        "applied_entitlements": applied_entitlements,
        "join_nudge": join_nudge,
        "gift_card_id": gift_card.get("card_id") if gift_card else None,
        "gift_available_cents": gift_available, "gift_applied_cents": gift_applied,
        "coupon_discount_cents": coupon_discount, "coupon_error": coupon_error,
        "coupon_code": (coupon_doc or {}).get("code") if coupon_discount > 0 else None,
        "coupon_id": (coupon_doc or {}).get("coupon_id") if coupon_discount > 0 else None,
        "combo_discount_cents": combo_discount, "combo_applied": combo_applied,
        "combo_label": ", ".join(combo_names) if combo_applied else None,
        "points_balance": int(balance or 0), "redeem_points_per_dollar": REDEEM_POINTS_PER_DOLLAR,
        "max_redeemable_points": max_redeemable, "redeemed_points": used_points,
        "points_discount_cents": points_discount,
        "goods_total_cents": goods_total,
        "service_fee_cents": service_fee_cents, "delivery_fee_cents": delivery_fee_cents,
        "fees_total_cents": fees_total, "eta_label": _eta_label(profile, fulfillment, pickup_time),
        "tax_cents": tax_cents, "tax_rate_percent": tax_info["rate_percent"],
        "tax_label": tax_info["label"], "tax_basis": tax_basis,
        "prep_time_min": int(profile.get("prep_time_min", 20) or 20),
        "delivery_available": bool((profile.get("delivery") or {}).get("enabled")),
        "fulfillment": fulfillment, "pickup_time": pickup_time,
        "total_cents": total,
        "points_to_award": int(eff.get("points", 0)), "happy_hour": eff.get("happy_hour", False),
        "points_multiplier": eff.get("multiplier", 1),
    }


class DeliveryAddress(BaseModel):
    label: Optional[str] = Field(None, max_length=300)
    line1: Optional[str] = Field(None, max_length=300)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    country: Optional[str] = Field(None, max_length=80)
    state: Optional[str] = Field(None, max_length=80)
    county: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)


class QuoteBody(BaseModel):
    business_id: str
    items: List[CheckoutItem]
    use_gift_card: bool = False
    redeem_points: int = Field(0, ge=0)
    coupon_code: Optional[str] = None
    fulfillment: Optional[Literal["pickup", "delivery"]] = "pickup"
    pickup_time: Optional[Literal["now", "+15", "+30", "+45"]] = "now"
    delivery_address: Optional[DeliveryAddress] = None


@router.post("/quote")
async def quote(body: QuoteBody, request: Request, user: dict = Depends(current_user)):
    """Live price breakdown for the checkout screen — no order is created."""
    if not body.items:
        raise HTTPException(400, {"code": "empty_cart"})
    db = request.app.state.db
    q = await _price_menu(db, user, body.business_id, body.items,
                          body.use_gift_card, body.redeem_points, body.coupon_code,
                          fulfillment=(body.fulfillment or "pickup"),
                          pickup_time=(body.pickup_time or "now"),
                          delivery_address=(body.delivery_address.model_dump()
                                            if body.delivery_address else None))
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
    fulfillment: Optional[Literal["pickup", "delivery"]] = "pickup"
    pickup_time: Optional[Literal["now", "+15", "+30", "+45"]] = "now"
    delivery_address: Optional[DeliveryAddress] = None


@router.post("/checkout")
async def checkout(body: CheckoutBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    if not body.items:
        raise HTTPException(400, {"code": "empty_cart"})
    q = await _price_menu(db, user, body.business_id, body.items,
                          body.use_gift_card, body.redeem_points, body.coupon_code,
                          fulfillment=(body.fulfillment or "pickup"),
                          pickup_time=(body.pickup_time or "now"),
                          delivery_address=(body.delivery_address.model_dump()
                                            if body.delivery_address else None))
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
        "entitlement_discount_cents": q.get("entitlement_discount_cents", 0),
        "applied_entitlements": q.get("applied_entitlements", []),
        "entitlements_recorded_done": False,
        "coupon_id": q.get("coupon_id"), "coupon_code": q.get("coupon_code"),
        "coupon_discount_cents": q.get("coupon_discount_cents", 0),
        "coupon_recorded_done": False,
        "combo_discount_cents": q.get("combo_discount_cents", 0),
        "combo_applied": q.get("combo_applied", False),
        "redeemed_points": redeemed_points, "points_discount_cents": points_discount,
        "points_redeemed_done": False,
        "total_cents": total,
        "points_to_award": q["points_to_award"], "points_multiplier": q["points_multiplier"],
        "happy_hour": q["happy_hour"], "points_awarded_done": False,
        "note": body.note, "pickup_code": pickup_code,
        "fulfillment": q.get("fulfillment") or "pickup",
        "pickup_time": q.get("pickup_time") or "now",
        "service_fee_cents": q.get("service_fee_cents", 0),
        "delivery_fee_cents": q.get("delivery_fee_cents", 0),
        "fees_total_cents": q.get("fees_total_cents", 0),
        "tax_cents": q.get("tax_cents", 0),
        "tax_rate_percent": q.get("tax_rate_percent", 0),
        "tax_label": q.get("tax_label"),
        "tax_basis": q.get("tax_basis"),
        "delivery_address": (body.delivery_address.model_dump()
                             if body.delivery_address else None),
        "eta_label": q.get("eta_label"),
        "ready_at": _ready_at(profile, q.get("fulfillment") or "pickup",
                              q.get("pickup_time") or "now"),
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
        from services.membership_entitlements import record_order_entitlements
        await record_order_entitlements(db, order, "marketplace_orders")
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
    from services.membership_entitlements import record_order_entitlements
    await record_order_entitlements(db, order, "marketplace_orders")
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


@router.get("/last/{business_id}")
async def last_order(business_id: str, request: Request, user: dict = Depends(current_user)):
    """Most recent paid order at this business, as a reorderable basket (only
    items that still exist & are available). Powers 'Reorder my last order'."""
    db = request.app.state.db
    o = await db.marketplace_orders.find_one(
        {"user_id": user.get("user_id"), "business_id": business_id,
         "payment_status": "paid"},
        sort=[("created_at", -1)])
    if not o:
        return {"has_order": False, "items": [], "dropped": 0}
    items, dropped = [], 0
    for li in (o.get("items") or []):
        mi = await db.menu_items.find_one(
            {"item_id": li.get("item_id"), "business_id": business_id, "available": True})
        if not mi:
            dropped += 1
            continue
        opts = li.get("selected_options") or []
        items.append({
            "item_id": li.get("item_id"), "name": li.get("name"),
            "price_cents": li.get("price_cents"), "qty": li.get("qty", 1),
            "selected_option_ids": [op.get("option_id") for op in opts if op.get("option_id")],
            "option_summary": ", ".join([op.get("label") for op in opts if op.get("label")]) or None,
            "note": li.get("note"),
        })
    return {"has_order": True, "order_id": o.get("order_id"),
            "created_at": o.get("created_at").isoformat() if hasattr(o.get("created_at"), "isoformat") else o.get("created_at"),
            "items": items, "dropped": dropped}


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
    # Restart the live prep clock the moment the kitchen actually starts.
    if new_status == "preparing":
        upd["ready_at"] = now() + timedelta(minutes=int(p.get("prep_time_min", 20) or 20))
    await db.marketplace_orders.update_one(
        {"order_id": order_id},
        {"$set": upd, "$push": {"status_history": {"status": new_status, "at": now()}}})

    # Live order alerts — notify the buyer in-app + real push on key transitions.
    if new_status in ("preparing", "ready", "picked_up"):
        biz = p.get("public_name") or "Your order"
        code = o.get("pickup_code")
        is_delivery = (o.get("fulfillment") == "delivery")
        if new_status == "ready":
            title = "Order Ready — head over! 🎉" if not is_delivery else "Out for delivery! 🛵"
            bodytxt = (f"{biz} · order #{code} is ready for pickup." if not is_delivery
                       else f"{biz} · order #{code} is on its way to you.")
        elif new_status == "preparing":
            title, bodytxt = "In the kitchen 👩‍🍳", f"{biz} is preparing order #{code}."
        else:
            title, bodytxt = "Enjoy! 🥡", f"{biz} · order #{code} complete. BigPoints on the way!"
        try:
            from routes.notifications import _enqueue
            await _enqueue(
                db, owner_user_id=o["user_id"], station_id="marketplace",
                station_slug="marketplace", type_=f"order_{new_status}",
                payload={"title": title, "body": bodytxt, "order_id": order_id,
                         "pickup_code": code, "business_name": biz},
                dedupe_key=f"order_{new_status}_{order_id}")
        except Exception:
            pass
        try:
            from services.push_service import send_push
            await send_push(
                recipients=[o["user_id"]],
                data={"title": title, "message": bodytxt,
                      "action_url": f"/shop/order/{order_id}"},
                idempotency_key=f"push_order_{new_status}_{order_id}")
        except Exception as e:  # noqa: BLE001 — push failure never blocks the update
            logger.warning("order status push failed (non-blocking): %s", e)

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
