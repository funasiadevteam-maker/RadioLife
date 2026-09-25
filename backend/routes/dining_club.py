"""FUUSIC Premium Dining Club — HTTP routes (Phase 1).

Consumer flow (Premium-only): browse program → subscribe → get meal credits →
start a selection session → SPIN or SURPRISE ME (equal-probability, server-decided)
→ one optional reroll → accept → pay $9.99 → signed QR → redeem at the restaurant.

Payments reuse the app's Stripe integration (routes/billing.py pattern). In the
preview/mock Stripe mode the meal payment + Premium bundle finalize server-side so
the whole flow is testable without a hosted card page; in live mode a real Stripe
Checkout Session URL is returned and finalized on status poll.
"""
from __future__ import annotations

import logging
import random
import uuid
from typing import Optional
from urllib.parse import urlparse
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from core.config import STRIPE_API_KEY
from services import dining_club as dc
from services import premium_gate
from services.billing_service import grant_premium
from services.stripe_setup import get_price_for_currency
from services.stripe_client import stripe_mode
from services import stripe_connect_service as scs

logger = logging.getLogger("bigfm.dining.routes")

router = APIRouter(prefix="/api/dining-club", tags=["dining-club"])
merchant_router = APIRouter(prefix="/api/merchant/dining-club", tags=["dining-merchant"])
admin_router = APIRouter(prefix="/api/admin/dining-club", tags=["dining-admin"])

PREMIUM_PLAN = "premium_annual"


def _stripe_client(request: Request):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    host_url = str(request.base_url).rstrip("/")
    return StripeCheckout(api_key=STRIPE_API_KEY,
                          webhook_url=f"{host_url}/api/webhook/stripe")


def _premium_price() -> dict:
    try:
        p = get_price_for_currency(PREMIUM_PLAN, "usd")
        return {"amount_cents": int(round(float(p["amount"]) * 100)),
                "currency": (p.get("currency") or "USD").upper()}
    except Exception:
        return {"amount_cents": 0, "currency": "USD"}


from core.origins import resolve_origin as _resolve_origin



async def _charge_id_for_session(session_id: str) -> Optional[str]:
    """Resolve the platform charge id behind a hosted Checkout session, so the
    deferred restaurant transfer can use it as source_transaction."""
    import asyncio as _a
    import stripe as _stripe
    _stripe.api_key = STRIPE_API_KEY

    def _sync():
        s = _stripe.checkout.Session.retrieve(session_id, expand=["payment_intent"])
        pi = s.get("payment_intent")
        if isinstance(pi, str):
            pi = _stripe.PaymentIntent.retrieve(pi, expand=["latest_charge"])
        if not pi:
            return None
        lc = pi.get("latest_charge") if isinstance(pi, dict) else getattr(pi, "latest_charge", None)
        return lc.get("id") if isinstance(lc, dict) else lc

    try:
        return await _a.to_thread(_sync)
    except Exception:
        return None


# ══════════════════════════ CONSUMER ═══════════════════════════════════
class SubscribeBody(BaseModel):
    meals_per_week: int = Field(..., ge=1, le=20)
    veg_default: str = Field("VEG")
    origin_url: Optional[str] = None


class StartBody(BaseModel):
    veg_preference: str = Field(..., description="VEG | NON_VEG")
    meal_period: str = Field("LUNCH", description="LUNCH | DINNER | ANY")
    lat: Optional[float] = None
    lng: Optional[float] = None


class CheckoutBody(BaseModel):
    order_id: str
    origin_url: Optional[str] = None


@router.get("")
async def dining_home(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    program = await dc.get_program(db)
    is_prem = premium_gate.is_premium_or_trial(user)
    sub = await dc.get_subscription(db, user["user_id"])
    credits = await dc.credit_summary(db, user["user_id"], is_prem)
    days_remaining = None
    if sub and sub.get("term_ends_at"):
        end = dc._aware(sub["term_ends_at"])
        if end:
            days_remaining = max(0, (end - dc._now()).days)
    pref_doc = await db.dining_prefs.find_one({"_id": user["user_id"]})
    last_pref = ({"veg_preference": pref_doc.get("veg_preference"),
                  "meal_period": pref_doc.get("meal_period", "LUNCH")}
                 if pref_doc else None)
    return {
        "program": dc.public_program(program),
        "is_premium": is_prem,
        "premium_required": bool(program.get("premium_required")),
        "premium_price": _premium_price(),
        "meal_price_cents": int(program["meal_price_cents"]),
        "access_fee_cents": int(program["access_fee_cents"]),
        "membership": dc._clean(sub) if sub else None,
        "days_remaining": days_remaining,
        "credits": credits,
        "last_pref": last_pref,
    }


@router.post("/subscribe")
async def subscribe(body: SubscribeBody, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    program = await dc.get_program(db)
    lo, hi = int(program["min_meals_week"]), int(program["max_meals_week"])
    if not (lo <= body.meals_per_week <= hi):
        raise HTTPException(400, {"code": "invalid_meals_per_week",
                                  "min": lo, "max": hi})
    if body.veg_default not in ("VEG", "NON_VEG"):
        raise HTTPException(400, {"code": "invalid_veg_default"})
    existing = await dc.get_subscription(db, user["user_id"])
    if existing and existing.get("status") == "active":
        raise HTTPException(400, {"code": "already_subscribed",
                                  "subscription_id": existing["subscription_id"]})

    is_prem = premium_gate.is_premium_or_trial(user)
    access_fee = int(program["access_fee_cents"])
    needs_payment = (not is_prem) or access_fee > 0

    # Live Stripe: bundle Annual Premium (if needed) + access fee into one session.
    if needs_payment and stripe_mode() == "live":
        prem = _premium_price()
        total_cents = (prem["amount_cents"] if not is_prem else 0) + access_fee
        origin = _resolve_origin(request, body.origin_url)
        if not origin:
            raise HTTPException(400, {"code": "origin_url_required"})
        from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest
        stripe = _stripe_client(request)
        session = await stripe.create_checkout_session(CheckoutSessionRequest(
            amount=total_cents / 100.0, currency="usd",
            success_url=f"{origin}/dining/enrolled?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/dining?cancelled=1",
            metadata={"user_id": user["user_id"], "kind": "dining_enroll",
                      "meals_per_week": str(body.meals_per_week),
                      "veg_default": body.veg_default,
                      "bundle_premium": str(not is_prem)}))
        await db.dining_enroll_intents.insert_one({
            "session_id": session.session_id, "user_id": user["user_id"],
            "meals_per_week": body.meals_per_week, "veg_default": body.veg_default,
            "bundle_premium": not is_prem, "status": "pending",
            "created_at": dc._now()})
        return {"requires_payment": True, "checkout_url": session.url,
                "session_id": session.session_id,
                "discloses": {"annual_premium": None if is_prem else prem,
                              "dining_access_fee_cents": access_fee}}

    # Preview/mock (or already-premium + $0 fee): activate immediately.
    if not is_prem:
        await grant_premium(user["user_id"], PREMIUM_PLAN, "USD")
    res = await dc.create_subscription(
        db, customer_id=user["user_id"], meals_per_week=body.meals_per_week,
        veg_default=body.veg_default, program=program)
    return {"requires_payment": False, "activated": True, **res,
            "bundled_premium": (not is_prem)}


@router.get("/subscribe/status/{session_id}")
async def subscribe_status(session_id: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    intent = await db.dining_enroll_intents.find_one(
        {"session_id": session_id, "user_id": user["user_id"]})
    if not intent:
        raise HTTPException(404, {"code": "intent_not_found"})
    if intent.get("status") == "completed":
        sub = await dc.get_subscription(db, user["user_id"])
        return {"status": "completed", "subscription": dc._clean(sub)}
    program = await dc.get_program(db)
    stripe = _stripe_client(request)
    status = await stripe.get_checkout_status(session_id)
    if status.payment_status == "paid" and status.status == "complete":
        if intent.get("bundle_premium"):
            await grant_premium(user["user_id"], PREMIUM_PLAN, "USD",
                                stripe_session_id=session_id)
        res = await dc.create_subscription(
            db, customer_id=user["user_id"],
            meals_per_week=int(intent["meals_per_week"]),
            veg_default=intent["veg_default"], program=program,
            stripe_session_id=session_id)
        await db.dining_enroll_intents.update_one(
            {"session_id": session_id}, {"$set": {"status": "completed"}})
        return {"status": "completed", **res}
    return {"status": status.status, "payment_status": status.payment_status}


@router.get("/credits")
async def credits(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    is_prem = premium_gate.is_premium_or_trial(user)
    return {"summary": await dc.credit_summary(db, user["user_id"], is_prem),
            "credits": await dc.list_credits(db, user["user_id"])}


def _require_active_sub(sub, is_prem):
    if not is_prem:
        raise HTTPException(403, {"code": "premium_required"})
    if not sub or sub.get("status") != "active":
        raise HTTPException(403, {"code": "no_active_membership"})


# ── Roll-a-Dice "free meal for 8" promo game ────────────────────────
# Roll two dice; a double-six (total 12) wins a free meal for 8. The win
# probability is exactly 1/12 (weighted RNG — NOT natural 2-dice odds).
DICE_WIN_CHANCE = 1.0 / 12.0
DICE_PRIZE = "Free meal for 8 people"


def _dice_today_key() -> str:
    return dc._now().strftime("%Y-%m-%d")


def _dice_public(doc):
    if not doc:
        return None
    created = doc.get("created_at")
    return {
        "roll_id": doc["_id"], "die1": doc["die1"], "die2": doc["die2"],
        "total": doc["die1"] + doc["die2"], "win": bool(doc.get("win")),
        "prize": doc.get("prize") if doc.get("win") else None,
        "code": doc.get("code") if doc.get("win") else None,
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
    }


@router.get("/dice")
async def dice_status(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    today = _dice_today_key()
    last = await db.dining_dice_rolls.find_one(
        {"user_id": user["user_id"], "day": today}, sort=[("created_at", -1)])
    wins = await db.dining_dice_rolls.count_documents(
        {"user_id": user["user_id"], "win": True})
    return {
        "config": {
            "prize": DICE_PRIZE, "win_chance": "1 in 12", "party_size": 8,
            "how_it_works": "Roll two dice. Land a double six (a total of 12) and your whole table eats free — a meal for 8, on the house.",
            "rolls_per_day": 1,
        },
        "can_roll": last is None,
        "last_result": _dice_public(last),
        "total_wins": wins,
    }


@router.post("/dice/roll")
async def dice_roll(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    today = _dice_today_key()
    existing = await db.dining_dice_rolls.find_one(
        {"user_id": user["user_id"], "day": today})
    if existing:
        raise HTTPException(429, {"code": "already_rolled_today",
                                  "result": _dice_public(existing)})
    win = random.random() < DICE_WIN_CHANCE
    if win:
        die1 = die2 = 6
    else:
        die1, die2 = 6, 6
        while die1 == 6 and die2 == 6:
            die1 = random.randint(1, 6)
            die2 = random.randint(1, 6)
    code = ("MEAL8-" + uuid.uuid4().hex[:8].upper()) if win else None
    doc = {
        "_id": f"dice_{uuid.uuid4().hex[:16]}", "user_id": user["user_id"],
        "day": today, "die1": die1, "die2": die2, "win": win,
        "prize": DICE_PRIZE if win else None, "code": code,
        "redeemed": False, "created_at": dc._now(),
    }
    await db.dining_dice_rolls.insert_one(doc)
    return _dice_public(doc)


@router.post("/selection/start")
async def selection_start(body: StartBody, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    program = await dc.get_program(db)
    is_prem = premium_gate.is_premium_or_trial(user)
    sub = await dc.get_subscription(db, user["user_id"])
    _require_active_sub(sub, is_prem)
    summary = await dc.credit_summary(db, user["user_id"], is_prem)
    if summary["available"] < 1:
        raise HTTPException(400, {"code": "no_available_credits"})
    # Remember this pick so the next visit can jump straight to the wheel.
    await db.dining_prefs.update_one(
        {"_id": user["user_id"]},
        {"$set": {"veg_preference": body.veg_preference,
                  "meal_period": body.meal_period,
                  "updated_at": dc._now()}},
        upsert=True)
    try:
        return await dc.start_session(
            db, customer_id=user["user_id"], veg=body.veg_preference,
            meal_period=body.meal_period, lat=body.lat, lng=body.lng,
            program=program)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    except PermissionError as e:
        wait = str(e).split(":")[-1]
        raise HTTPException(429, {"code": "cooldown_active", "wait_minutes": wait})
    except LookupError:
        raise HTTPException(409, {"code": "not_enough_options"})


async def _do_spin(db, user, session_id, method):
    program = await dc.get_program(db)
    try:
        return await dc.spin(db, customer_id=user["user_id"],
                             session_id=session_id, method=method, program=program)
    except LookupError as e:
        code = "session_not_found" if str(e) == "session_not_found" else "not_enough_options"
        raise HTTPException(404 if code == "session_not_found" else 409, {"code": code})
    except TimeoutError:
        raise HTTPException(410, {"code": "session_expired"})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/selection/{session_id}/spin")
async def selection_spin(session_id: str, request: Request,
                         user: dict = Depends(current_user)):
    return await _do_spin(request.app.state.db, user, session_id, "wheel")


@router.post("/selection/{session_id}/random")
async def selection_random(session_id: str, request: Request,
                           user: dict = Depends(current_user)):
    return await _do_spin(request.app.state.db, user, session_id, "random")


@router.post("/selection/{session_id}/reroll")
async def selection_reroll(session_id: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await dc.reroll(db, customer_id=user["user_id"], session_id=session_id)
    except LookupError:
        raise HTTPException(404, {"code": "session_not_found"})
    except TimeoutError:
        raise HTTPException(410, {"code": "session_expired"})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.get("/selection/{session_id}")
async def selection_view(session_id: str, request: Request,
                         user: dict = Depends(current_user)):
    v = await dc.get_session_view(request.app.state.db,
                                  customer_id=user["user_id"], session_id=session_id)
    if not v:
        raise HTTPException(404, {"code": "session_not_found"})
    return v


@router.post("/selection/{session_id}/abandon")
async def selection_abandon(session_id: str, request: Request,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await dc.abandon(db, customer_id=user["user_id"], session_id=session_id)
    except LookupError:
        raise HTTPException(404, {"code": "session_not_found"})
    except TimeoutError:
        raise HTTPException(410, {"code": "session_expired"})


@router.post("/selection/{session_id}/accept")
async def selection_accept(session_id: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    program = await dc.get_program(db)
    try:
        return await dc.accept(db, customer_id=user["user_id"],
                               session_id=session_id, program=program)
    except LookupError as e:
        raise HTTPException(404, {"code": str(e)})
    except TimeoutError:
        raise HTTPException(410, {"code": "session_expired"})
    except ConnectionError:
        raise HTTPException(409, {"code": "availability_changed",
                                  "message": "That restaurant just sold out — spin again, free of charge."})
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/checkout")
async def meal_checkout(body: CheckoutBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    program = await dc.get_program(db)
    order = await db.dining_orders.find_one(
        {"order_id": body.order_id, "customer_id": user["user_id"]})
    if not order:
        raise HTTPException(404, {"code": "order_not_found"})
    if order["status"] == "paid":
        return {"status": "paid", **(await dc.get_pass(db, customer_id=user["user_id"], order_id=body.order_id))}

    if stripe_mode() == "live":
        origin = _resolve_origin(request, body.origin_url)
        if not origin:
            raise HTTPException(400, {"code": "origin_url_required"})
        from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest
        stripe = _stripe_client(request)
        session = await stripe.create_checkout_session(CheckoutSessionRequest(
            amount=int(order["amount_cents"]) / 100.0, currency="usd",
            success_url=f"{origin}/dining/pass?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/dining?cancelled=1",
            metadata={"user_id": user["user_id"], "kind": "dining_meal",
                      "order_id": body.order_id}))
        await db.dining_orders.update_one(
            {"order_id": body.order_id},
            {"$set": {"stripe_session_id": session.session_id, "updated_at": dc._now()}})
        return {"requires_payment": True, "checkout_url": session.url,
                "session_id": session.session_id}

    # mock mode → finalize immediately (issue QR)
    res = await dc.finalize_paid_order(db, order=order, program=program,
                                       stripe_session_id="mock")
    return {"requires_payment": False, **res}


@router.get("/checkout/status/{session_id}")
async def meal_checkout_status(session_id: str, request: Request,
                               user: dict = Depends(current_user)):
    db = request.app.state.db
    program = await dc.get_program(db)
    order = await db.dining_orders.find_one(
        {"stripe_session_id": session_id, "customer_id": user["user_id"]})
    if not order:
        raise HTTPException(404, {"code": "order_not_found"})
    if order["status"] == "paid":
        return {"status": "paid", **(await dc.get_pass(db, customer_id=user["user_id"], order_id=order["order_id"]))}
    stripe = _stripe_client(request)
    status = await stripe.get_checkout_status(session_id)
    if status.payment_status == "paid" and status.status == "complete":
        charge_id = await _charge_id_for_session(session_id)
        res = await dc.finalize_paid_order(db, order=order, program=program,
                                           stripe_session_id=session_id,
                                           stripe_charge_id=charge_id)
        return {"status": "paid", **res}
    return {"status": status.status, "payment_status": status.payment_status}


@router.get("/pass/{order_id}")
async def dining_pass(order_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await dc.get_pass(db, customer_id=user["user_id"], order_id=order_id)
    if not p:
        raise HTTPException(404, {"code": "pass_not_found"})
    return p


# ══════════════════════════ MERCHANT ═══════════════════════════════════
class RedeemBody(BaseModel):
    qr_token: str
    location_id: Optional[str] = None


@merchant_router.post("/redeem")
async def merchant_redeem(body: RedeemBody, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    program = await dc.get_program(db)
    # Merchant-role guard: only the restaurant that owns the meal's location
    # (or an admin) may redeem its QR.
    is_admin = (user.get("role") == "admin") or bool(user.get("is_admin"))
    if not is_admin:
        redm = await db.dining_redemptions.find_one({"qr_token": body.qr_token},
                                                    {"location_id": 1})
        if not redm:
            raise HTTPException(404, {"code": "invalid_qr"})
        loc = await db.dining_locations.find_one({"location_id": redm["location_id"]},
                                                 {"merchant_id": 1})
        merch = await db.dining_merchants.find_one(
            {"merchant_id": (loc or {}).get("merchant_id")}, {"owner_user_id": 1})
        if not merch or merch.get("owner_user_id") != user["user_id"]:
            raise HTTPException(403, {"code": "not_meal_merchant"})
    try:
        return await dc.redeem_qr(db, qr_token=body.qr_token, program=program,
                                  merchant_location_id=body.location_id)
    except LookupError:
        raise HTTPException(404, {"code": "invalid_qr"})
    except TimeoutError:
        raise HTTPException(410, {"code": "qr_expired"})
    except PermissionError as e:
        raise HTTPException(403, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


# ── merchant self-serve: enroll + Stripe Connect + catalog + analytics ──
class MerchantEnroll(BaseModel):
    name: str
    cuisine: str = "american"
    restaurant_class: str = "FAST_CASUAL"
    origin_url: Optional[str] = None


class LocationBody(BaseModel):
    name: str
    address: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    veg_available: bool = True
    nonveg_available: bool = True
    hours: str = "11:00–22:00"


class CapacityBody(BaseModel):
    capacity: dict = Field(default_factory=dict, description='{"LUNCH:VEG":20,"DINNER:NON_VEG":30}')


class MealsBody(BaseModel):
    meals: list[dict] = Field(default_factory=list)


class ConnectLinkBody(BaseModel):
    origin_url: str


class DiningWebhookBody(BaseModel):
    url: str
    events: Optional[list[str]] = None


async def _owned(db, user: dict) -> dict:
    m = await dc.get_owned_merchant(db, user["user_id"])
    if not m:
        raise HTTPException(400, {"code": "not_a_dining_merchant"})
    return m


@merchant_router.post("/enroll")
async def merchant_enroll(body: MerchantEnroll, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await dc.create_owned_merchant(
        db, owner_user_id=user["user_id"], name=body.name, cuisine=body.cuisine,
        restaurant_class=body.restaurant_class)
    # Stripe Connect onboarding so the restaurant can receive its $8.99/meal.
    onboarding_url = None
    try:
        if not m.get("stripe_account_id"):
            acct = await scs.create_connected_account(
                merchant_id=m["merchant_id"],
                email=user.get("email") or f"{user['user_id']}@dining.local")
            await dc.set_merchant_connect(db, merchant_id=m["merchant_id"],
                                          stripe_account_id=acct["stripe_account_id"],
                                          status="onboarding_in_progress")
            m["stripe_account_id"] = acct["stripe_account_id"]
        origin = (body.origin_url or str(request.base_url)).rstrip("/")
        onboarding_url = await scs.create_onboarding_link(
            stripe_account_id=m["stripe_account_id"],
            return_url=f"{origin}/dining/merchant?connected=1",
            refresh_url=f"{origin}/dining/merchant?refresh=1")
    except Exception as e:  # noqa: BLE001
        logger.warning("dining connect onboarding failed: %s", e)
    return {"merchant": m, "connect_onboarding_url": onboarding_url}


@merchant_router.get("/me")
async def merchant_me(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    v = await dc.merchant_view(db, user["user_id"])
    if not v:
        return {"enrolled": False}
    return {"enrolled": True, **v}


@merchant_router.post("/connect/link")
async def merchant_connect_link(body: ConnectLinkBody, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    if not m.get("stripe_account_id"):
        acct = await scs.create_connected_account(
            merchant_id=m["merchant_id"],
            email=user.get("email") or f"{user['user_id']}@dining.local")
        await dc.set_merchant_connect(db, merchant_id=m["merchant_id"],
                                      stripe_account_id=acct["stripe_account_id"],
                                      status="onboarding_in_progress")
        m["stripe_account_id"] = acct["stripe_account_id"]
    origin = body.origin_url.rstrip("/")
    url = await scs.create_onboarding_link(
        stripe_account_id=m["stripe_account_id"],
        return_url=f"{origin}/dining/merchant?connected=1",
        refresh_url=f"{origin}/dining/merchant?refresh=1")
    return {"connect_onboarding_url": url}


@merchant_router.post("/locations")
async def merchant_add_location(body: LocationBody, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    return {"location": await dc.add_location(
        db, merchant_id=m["merchant_id"], name=body.name, address=body.address,
        lat=body.lat, lng=body.lng, veg_available=body.veg_available,
        nonveg_available=body.nonveg_available, hours=body.hours)}


@merchant_router.patch("/locations/{location_id}")
async def merchant_patch_location(location_id: str, patch: dict, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    loc = await dc.update_location(db, merchant_id=m["merchant_id"],
                                   location_id=location_id, patch=patch)
    if not loc:
        raise HTTPException(404, {"code": "location_not_found"})
    return {"location": dc._clean(loc)}


@merchant_router.put("/locations/{location_id}/capacity")
async def merchant_set_capacity(location_id: str, body: CapacityBody, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    if not await dc.set_capacity(db, merchant_id=m["merchant_id"],
                                 location_id=location_id, capacity=body.capacity):
        raise HTTPException(404, {"code": "location_not_found"})
    return {"ok": True, "capacity": {k: int(v) for k, v in body.capacity.items()}}


@merchant_router.post("/locations/{location_id}/meals")
async def merchant_set_meals(location_id: str, body: MealsBody, request: Request,
                             user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    return {"meals": await dc.set_meals(db, merchant_id=m["merchant_id"],
                                        location_id=location_id, meals=body.meals)}


@merchant_router.get("/analytics")
async def merchant_analytics(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    return await dc.merchant_analytics(db, m["merchant_id"])


@merchant_router.post("/webhooks")
async def merchant_add_webhook(body: DiningWebhookBody, request: Request,
                               user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    return {"webhook": await dc.register_dining_webhook(
        db, merchant_id=m["merchant_id"], url=body.url, events=body.events)}


@merchant_router.get("/webhooks")
async def merchant_list_webhooks(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    return {"events": dc.DINING_EVENTS,
            "webhooks": await dc.list_dining_webhooks(db, m["merchant_id"])}


@merchant_router.delete("/webhooks/{webhook_id}")
async def merchant_delete_webhook(webhook_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await _owned(db, user)
    if not await dc.delete_dining_webhook(db, m["merchant_id"], webhook_id):
        raise HTTPException(404, {"code": "webhook_not_found"})
    return {"deleted": True}


# ══════════════════════════ ADMIN ══════════════════════════════════════
@admin_router.get("")
async def admin_home(request: Request, _a: dict = Depends(require_admin)):
    db = request.app.state.db
    program = await dc.get_program(db)
    return {
        "program": dc.public_program(program),
        "stats": {
            "merchants": await db.dining_merchants.count_documents({}),
            "locations": await db.dining_locations.count_documents({"status": "ACTIVE"}),
            "subscriptions": await db.dining_subscriptions.count_documents({"status": "active"}),
            "credits_available": await db.dining_meal_credits.count_documents({"status": "AVAILABLE"}),
            "redemptions": await db.dining_redemptions.count_documents({"status": "REDEEMED"}),
        }}


@admin_router.patch("/settings")
async def admin_settings(patch: dict, request: Request,
                         _a: dict = Depends(require_admin)):
    return {"program": dc.public_program(await dc.patch_program(request.app.state.db, patch))}


@admin_router.post("/run-grants")
async def admin_run_grants(request: Request, _a: dict = Depends(require_admin)):
    return {"grants_issued": await dc.issue_due_grants(request.app.state.db)}


@admin_router.get("/fairness")
async def admin_fairness(request: Request, _a: dict = Depends(require_admin)):
    """Distribution monitor — appearances vs wins per restaurant, and the
    per-set expected win rate (1/N) for bias detection (spec §58)."""
    db = request.app.state.db
    appear: dict = {}
    wins: dict = {}
    total_sets = 0
    async for cs in db.dining_candidate_sets.find({}, {"restaurant_ids": 1, "winner_restaurant_id": 1}):
        total_sets += 1
        for rid in cs.get("restaurant_ids") or []:
            appear[rid] = appear.get(rid, 0) + 1
        w = cs.get("winner_restaurant_id")
        if w:
            wins[w] = wins.get(w, 0) + 1
    rows = []
    for rid, ap in sorted(appear.items(), key=lambda x: -x[1]):
        rows.append({"restaurant_id": rid, "appearances": ap,
                     "wins": wins.get(rid, 0),
                     "expected_wins": round(ap * (1.0 / max(1, dc.DEFAULTS["candidate_size"])), 2),
                     "win_rate": round(wins.get(rid, 0) / ap, 3) if ap else 0})
    return {"total_candidate_sets": total_sets, "restaurants": rows}


@admin_router.post("/seed")
async def admin_seed(request: Request, _a: dict = Depends(require_admin)):
    return await seed_demo_restaurants(request.app.state.db)


@admin_router.post("/orders/{order_id}/mark-paid")
async def admin_mark_paid(order_id: str, request: Request,
                          _a: dict = Depends(require_admin)):
    """Admin/QA utility — finalize a pending meal order (issue the QR) without a
    live card charge. In production real payment finalizes via Stripe status poll."""
    db = request.app.state.db
    program = await dc.get_program(db)
    order = await db.dining_orders.find_one({"order_id": order_id})
    if not order:
        raise HTTPException(404, {"code": "order_not_found"})
    return await dc.finalize_paid_order(db, order=order, program=program,
                                        stripe_session_id="admin_marked")


# ── demo seed (12 restaurants around the default market) ────────────────
_DEMO = [
    ("Desi District", "indian", "FAST_CASUAL", True, True),
    ("Cantina Sol", "mexican", "FAST_CASUAL", True, True),
    ("Olive & Vine", "mediterranean", "SIT_DOWN", True, True),
    ("Wok Republic", "asian", "FAST_CASUAL", True, True),
    ("The Grill House", "american", "SIT_DOWN", False, True),
    ("Green Bowl Co", "salads", "FAST_CASUAL", True, False),
    ("Curry Leaf", "indian", "SIT_DOWN", True, True),
    ("Taco Libre", "mexican", "FAST_CASUAL", True, True),
    ("Cedar Kitchen", "mediterranean", "FAST_CASUAL", True, True),
    ("Bamboo Bay", "asian", "SIT_DOWN", True, True),
    ("Smoke & Ember", "american", "SIT_DOWN", False, True),
    ("Falafel Street", "mediterranean", "FAST_CASUAL", True, False),
]


async def seed_demo_restaurants(db) -> dict:
    await dc.get_program(db)
    base = dc.DEFAULT_MARKET
    created = 0
    for i, (name, cuisine, klass, veg, nonveg) in enumerate(_DEMO):
        merchant_id = f"dmerch_demo_{i}"
        location_id = f"dloc_demo_{i}"
        if await db.dining_merchants.find_one({"merchant_id": merchant_id}):
            continue
        await db.dining_merchants.insert_one({
            "merchant_id": merchant_id, "name": name, "cuisine": cuisine,
            "restaurant_class": klass, "status": "ACTIVE",
            "participation_fee_cents": 50000, "billing_frequency": "monthly",
            "logo_url": None, "created_at": dc._now()})
        cap = {}
        for mp in ("LUNCH", "DINNER"):
            if veg:
                cap[f"{mp}:VEG"] = 20
            if nonveg:
                cap[f"{mp}:NON_VEG"] = 30
        await db.dining_locations.insert_one({
            "location_id": location_id, "merchant_id": merchant_id,
            "name": f"{name} — Downtown", "status": "ACTIVE",
            "address": f"{100 + i} Marina Walk, Dubai", "market": base["market"],
            "lat": base["lat"] + (i - 6) * 0.004, "lng": base["lng"] + (i - 6) * 0.004,
            "veg_available": veg, "nonveg_available": nonveg,
            "hours": "11:00–22:00", "blackout_dates": [], "capacity": cap,
            "created_at": dc._now()})
        for mp in ("LUNCH", "DINNER"):
            if veg:
                await db.dining_meal_offers.insert_one({
                    "offer_id": dc._gen("doff"), "location_id": location_id,
                    "merchant_id": merchant_id, "veg_preference": "VEG",
                    "meal_period": mp, "customer_title": f"Today's Veg {cuisine.title()} plate",
                    "customer_description": "Chef's selected vegetarian meal", "active": True})
            if nonveg:
                await db.dining_meal_offers.insert_one({
                    "offer_id": dc._gen("doff"), "location_id": location_id,
                    "merchant_id": merchant_id, "veg_preference": "NON_VEG",
                    "meal_period": mp, "customer_title": f"Today's {cuisine.title()} special",
                    "customer_description": "Chef's selected meal", "active": True})
        created += 1
    return {"seeded": created,
            "total_locations": await db.dining_locations.count_documents({"status": "ACTIVE"})}


__all__ = ["router", "merchant_router", "admin_router", "seed_demo_restaurants"]
