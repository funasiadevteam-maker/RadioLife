"""Gift Card Market — listeners buy & gift local venue gift cards using
points or a card (Stripe Checkout).  Self-contained; reuses PointsService
for the points path and the standard stripe.checkout.Session pattern."""
from __future__ import annotations
from core.origins import resolve_origin

import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.points_service import PointsService
from services.gift_notify import send_gift_emails

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/giftcards", tags=["gift-cards"])

POINTS_PER_DOLLAR = 100  # 100 points == $1


def _now() -> datetime:
    return datetime.now(timezone.utc)


GIFT_CARD_DEFAULTS: List[Dict[str, Any]] = [
    {"product_id": "gc_grind_coffee", "business_id": "biz_demo_marketplace",
     "sponsor_name": "The Grind Coffee (Demo)", "category": "cafe",
     "denominations_cents": [1000, 2500, 5000], "points_per_dollar": POINTS_PER_DOLLAR,
     "allow_points": True, "allow_card": True, "active": True},
    {"product_id": "gc_frisco_eats", "business_id": "biz_platform_eats",
     "sponsor_name": "Frisco Eats", "category": "restaurant",
     "denominations_cents": [2500, 5000, 10000], "points_per_dollar": POINTS_PER_DOLLAR,
     "allow_points": True, "allow_card": True, "active": True},
    {"product_id": "gc_spa_bliss", "business_id": "biz_platform_spa",
     "sponsor_name": "Bliss Day Spa", "category": "wellness",
     "denominations_cents": [5000, 10000], "points_per_dollar": POINTS_PER_DOLLAR,
     "allow_points": True, "allow_card": True, "active": True},
]


async def _seed_products(db):
    if await db.gift_card_products.count_documents({}) == 0:
        for p in GIFT_CARD_DEFAULTS:
            await db.gift_card_products.update_one(
                {"product_id": p["product_id"]},
                {"$set": {**p, "updated_at": _now()},
                 "$setOnInsert": {"created_at": _now()}}, upsert=True)


def _new_code() -> str:
    raw = secrets.token_hex(6).upper()
    return f"RL-{raw[:4]}-{raw[4:8]}-{raw[8:12]}"


async def _issue_card(db, *, product: Dict[str, Any], amount_cents: int, buyer_id: str,
                      method: str, gift_to_email: Optional[str], message: Optional[str],
                      idempotency_key: str) -> Dict[str, Any]:
    existing = await db.gift_cards.find_one({"idempotency_key": idempotency_key})
    if existing:
        existing.pop("_id", None)
        return existing
    owner_id = buyer_id
    if gift_to_email:
        rec = await db.users.find_one({"email": gift_to_email.lower().strip()}, {"user_id": 1})
        if rec:
            owner_id = rec["user_id"]
    card = {
        "card_id": f"gc_{uuid.uuid4().hex[:12]}", "code": _new_code(),
        "product_id": product["product_id"], "business_id": product.get("business_id"),
        "sponsor_name": product.get("sponsor_name"), "amount_cents": amount_cents,
        "balance_cents": amount_cents, "owner_user_id": owner_id, "buyer_user_id": buyer_id,
        "gifted_to_email": (gift_to_email or None), "message": message,
        "method": method, "status": "active", "idempotency_key": idempotency_key,
        "revealed": gift_to_email is None, "thanks_sent": False,
        "created_at": _now(),
    }
    await db.gift_cards.insert_one(dict(card))
    card.pop("_id", None)
    return card


async def _schedule_gc_gift_email(db, bg: Optional[BackgroundTasks], card: Dict[str, Any]) -> None:
    if not (bg and card.get("gifted_to_email")):
        return
    buyer = await db.users.find_one({"user_id": card.get("buyer_user_id")},
                                    {"email": 1, "display_name": 1, "name": 1}) or {}
    bg.add_task(send_gift_emails, kind="giftcard",
                item_name=f"${int(card.get('amount_cents', 0) / 100)} gift card",
                sponsor_name=card.get("sponsor_name"),
                buyer_email=buyer.get("email"),
                buyer_name=buyer.get("display_name") or buyer.get("name") or "A friend",
                recipient_email=card.get("gifted_to_email"),
                message=card.get("message"))


@router.get("/catalog")
async def catalog(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _seed_products(db)
    out = []
    async for p in db.gift_card_products.find({"active": True}):
        p.pop("_id", None)
        out.append(p)
    balance = await PointsService(db).get_balance(user.get("user_id"))
    return {"items": out, "points_balance": balance, "points_per_dollar": POINTS_PER_DOLLAR}


class PurchaseBody(BaseModel):
    product_id: str
    amount_cents: int = Field(..., gt=0, le=1_000_000)
    method: str = Field(..., description="points | card")
    gift_to_email: Optional[str] = None
    message: Optional[str] = Field(None, max_length=280)
    origin_url: Optional[str] = None


@router.post("/purchase")
async def purchase(body: PurchaseBody, request: Request,
                   background_tasks: BackgroundTasks,
                   user: dict = Depends(current_user)):
    db = request.app.state.db
    await _seed_products(db)
    uid = user.get("user_id")
    product = await db.gift_card_products.find_one({"product_id": body.product_id, "active": True})
    if not product:
        raise HTTPException(404, {"code": "product_not_found"})
    if body.amount_cents not in (product.get("denominations_cents") or []):
        raise HTTPException(400, {"code": "bad_denomination"})

    if body.method == "points":
        if not product.get("allow_points", True):
            raise HTTPException(400, {"code": "points_not_allowed"})
        ppd = int(product.get("points_per_dollar", POINTS_PER_DOLLAR))
        points_cost = round(body.amount_cents / 100.0 * ppd)
        balance = await PointsService(db).get_balance(uid)
        if balance < points_cost:
            raise HTTPException(400, {"code": "insufficient_points",
                                      "needed": points_cost, "have": balance})
        idem = f"giftcard:points:{uid}:{uuid.uuid4().hex[:8]}"
        await PointsService(db).spend(
            user_id=uid, source="giftcard_purchase", amount=points_cost,
            source_id=body.product_id, idempotency_key=idem,
            metadata={"product_id": body.product_id, "amount_cents": body.amount_cents})
        card = await _issue_card(db, product=product, amount_cents=body.amount_cents,
                                 buyer_id=uid, method="points",
                                 gift_to_email=body.gift_to_email, message=body.message,
                                 idempotency_key=idem)
        await _schedule_gc_gift_email(db, background_tasks, card)
        return {"ok": True, "method": "points", "points_spent": points_cost, "card": card}

    if body.method == "card":
        if not stripe.api_key:
            raise HTTPException(503, {"code": "stripe_unconfigured"})
        if not product.get("allow_card", True):
            raise HTTPException(400, {"code": "card_not_allowed"})
        origin = resolve_origin(request, body.origin_url)
        if not origin:
            raise HTTPException(400, {"code": "origin_required"})
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"{product.get('sponsor_name')} Gift Card"},
                    "unit_amount": body.amount_cents,
                },
                "quantity": 1,
            }],
            success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/payment/cancel",
            metadata={"kind": "giftcard", "product_id": body.product_id, "buyer_id": uid,
                      "amount_cents": str(body.amount_cents),
                      "gift_to_email": body.gift_to_email or "",
                      "message": (body.message or "")[:200]},
        )
        await db.gift_card_purchases.insert_one({
            "session_id": session.id, "buyer_user_id": uid, "product_id": body.product_id,
            "amount_cents": body.amount_cents, "gift_to_email": body.gift_to_email,
            "message": body.message, "status": "pending", "created_at": _now()})
        return {"ok": True, "method": "card", "checkout_url": session.url,
                "session_id": session.id}

    raise HTTPException(400, {"code": "bad_method"})


@router.get("/purchase/{session_id}/status")
async def purchase_status(session_id: str, request: Request,
                          background_tasks: BackgroundTasks,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    pur = await db.gift_card_purchases.find_one({"session_id": session_id})
    if not pur:
        raise HTTPException(404, {"code": "purchase_not_found"})
    if pur.get("status") == "paid" and pur.get("card_id"):
        card = await db.gift_cards.find_one({"card_id": pur["card_id"]})
        if card:
            card.pop("_id", None)
        return {"status": "paid", "card": card}
    if not stripe.api_key:
        return {"status": pur.get("status", "pending")}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": pur.get("status", "pending")}
    if sess.get("payment_status") == "paid":
        product = await db.gift_card_products.find_one({"product_id": pur["product_id"]})
        card = await _issue_card(
            db, product=product or {"product_id": pur["product_id"]},
            amount_cents=int(pur["amount_cents"]), buyer_id=pur["buyer_user_id"],
            method="card", gift_to_email=pur.get("gift_to_email"),
            message=pur.get("message"), idempotency_key=f"giftcard:card:{session_id}")
        await db.gift_card_purchases.update_one(
            {"session_id": session_id},
            {"$set": {"status": "paid", "card_id": card["card_id"], "paid_at": _now()}})
        await _schedule_gc_gift_email(db, background_tasks, card)
        return {"status": "paid", "card": card}
    return {"status": "pending"}


@router.get("/mine")
async def my_cards(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    email = (user.get("email") or "").lower()
    owned, sent = [], []
    async for c in db.gift_cards.find(
            {"$or": [{"owner_user_id": uid}, {"gifted_to_email": email}]}).sort("created_at", -1):
        c.pop("_id", None)
        c["received_gift"] = bool(c.get("buyer_user_id") and c.get("buyer_user_id") != uid)
        c.setdefault("revealed", not c["received_gift"])
        c.setdefault("thanks_sent", False)
        owned.append(c)
    async for c in db.gift_cards.find(
            {"buyer_user_id": uid, "gifted_to_email": {"$nin": [None, ""]}}).sort("created_at", -1):
        c.pop("_id", None)
        sent.append(c)
    return {"items": owned, "sent": sent, "total": len(owned)}


async def _my_card(db, card_id: str, user: dict) -> Dict[str, Any]:
    uid = user.get("user_id")
    email = (user.get("email") or "").lower()
    card = await db.gift_cards.find_one(
        {"card_id": card_id,
         "$or": [{"owner_user_id": uid}, {"gifted_to_email": email}]})
    if not card:
        raise HTTPException(404, {"code": "card_not_found"})
    return card


@router.post("/{card_id}/reveal")
async def reveal_card(card_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _my_card(db, card_id, user)
    await db.gift_cards.update_one(
        {"card_id": card_id}, {"$set": {"revealed": True, "revealed_at": _now()}})
    card = await db.gift_cards.find_one({"card_id": card_id})
    card.pop("_id", None)
    return {"ok": True, "card": card}


class ThanksBody(BaseModel):
    message: Optional[str] = Field(None, max_length=280)


@router.post("/{card_id}/thanks")
async def thank_gifter(card_id: str, body: ThanksBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    card = await _my_card(db, card_id, user)
    buyer_id = card.get("buyer_user_id")
    if not buyer_id or buyer_id == user.get("user_id"):
        raise HTTPException(400, {"code": "no_gifter"})
    try:
        from routes.notifications import _enqueue
        await _enqueue(
            db, owner_user_id=buyer_id, station_id="giftcards",
            station_slug="giftcards", type_="giftcard_thanks",
            payload={"card_id": card_id, "sponsor_name": card.get("sponsor_name"),
                     "from_name": user.get("name") or user.get("email"),
                     "message": (body.message or "Thank you for the gift card!")[:200]},
            dedupe_key=f"giftcard_thanks:{card_id}")
    except Exception:
        pass
    await db.gift_cards.update_one(
        {"card_id": card_id}, {"$set": {"thanks_sent": True, "thanks_at": _now()}})
    return {"ok": True}


class RedeemBody(BaseModel):
    amount_cents: int = Field(..., gt=0, le=1_000_000)


@router.post("/{card_id}/redeem")
async def redeem_card(card_id: str, body: RedeemBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    card = await _my_card(db, card_id, user)
    if card.get("status") != "active":
        raise HTTPException(400, {"code": "card_inactive"})
    balance = int(card.get("balance_cents", 0))
    if body.amount_cents > balance:
        raise HTTPException(400, {"code": "insufficient_balance", "have": balance})
    new_balance = balance - body.amount_cents
    await db.gift_cards.update_one(
        {"card_id": card_id},
        {"$set": {"balance_cents": new_balance,
                  "status": "active" if new_balance > 0 else "spent",
                  "updated_at": _now()}})
    await db.gift_card_redemptions.insert_one({
        "redemption_id": f"gcr_{uuid.uuid4().hex[:12]}", "card_id": card_id,
        "user_id": user.get("user_id"), "amount_cents": body.amount_cents,
        "balance_after_cents": new_balance, "created_at": _now()})
    return {"ok": True, "amount_cents": body.amount_cents,
            "balance_cents": new_balance,
            "status": "active" if new_balance > 0 else "spent"}


__all__ = ["router"]
