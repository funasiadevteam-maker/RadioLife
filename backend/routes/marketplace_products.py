"""Marketplace Ecommerce (Phase D) — physical products with stock, variants,
delivery, and a fulfillment lifecycle (paid → packed → shipped → delivered).

BigPoints (with loyalty tier bonus) awarded to the buyer on delivery.
Also exposes the consumer loyalty-status endpoint.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services.marketplace import now, new_id, effective_points
from services.loyalty import award_with_tier_bonus, get_status as loyalty_status

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace/products", tags=["marketplace-products"])
consumer_router = APIRouter(prefix="/api/shop", tags=["marketplace-products-consumer"])

FULFILL_ADVANCE = {"paid": "packed", "packed": "shipped", "shipped": "delivered"}
FULFILL_LABEL = {"paid": "Mark Packed", "packed": "Mark Shipped", "shipped": "Mark Delivered"}


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


# ───────────── Merchant: product catalogue ─────────────
class Variant(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    price_cents: int = Field(0, ge=0, le=10_000_000)  # 0 => use product price
    stock: int = Field(0, ge=0, le=1_000_000)


class ProductBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=600)
    category: str = Field("Products", max_length=60)
    price_cents: int = Field(..., ge=0, le=10_000_000)
    stock: int = Field(0, ge=0, le=1_000_000)  # used when no variants
    variants: List[Variant] = []
    bigpoints: Optional[int] = Field(None, ge=0, le=100000)
    image_url: Optional[str] = None
    active: bool = True


@router.get("")
async def list_products(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [_clean(x) async for x in db.products.find(
        {"business_id": p["business_id"]}).sort("sort", 1)]
    return {"items": items}


@router.post("/items")
async def create_product(body: ProductBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    n = await db.products.count_documents({"business_id": p["business_id"]})
    pid = new_id("prod")
    doc = {"product_id": pid, "business_id": p["business_id"], "sort": n,
           **body.model_dump(), "created_at": now(), "updated_at": now()}
    await db.products.insert_one(dict(doc))
    return {"ok": True, "product": _clean(doc)}


@router.patch("/items/{product_id}")
async def update_product(product_id: str, body: ProductBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.products.update_one(
        {"product_id": product_id, "business_id": p["business_id"]},
        {"$set": {**body.model_dump(), "updated_at": now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "product_not_found"})
    x = await db.products.find_one({"product_id": product_id})
    return {"ok": True, "product": _clean(x)}


@router.delete("/items/{product_id}")
async def delete_product(product_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.products.delete_one(
        {"product_id": product_id, "business_id": p["business_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, {"code": "product_not_found"})
    return {"ok": True}


@router.post("/items/{product_id}/photo")
async def product_photo(product_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    x = await db.products.find_one({"product_id": product_id, "business_id": p["business_id"]})
    if not x:
        raise HTTPException(404, {"code": "product_not_found"})
    body = await request.json()
    if not body.get("file_base64"):
        raise HTTPException(400, {"code": "file_required"})
    from services import menu_photos as mp
    try:
        url = mp.save_base64(product_id, body["file_base64"], body.get("ext", "png"))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    await db.products.update_one({"product_id": product_id},
                                 {"$set": {"image_url": url, "updated_at": now()}})
    return {"ok": True, "image_url": url}


@router.post("/items/{product_id}/photo/ai")
async def product_photo_ai(product_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    x = await db.products.find_one({"product_id": product_id, "business_id": p["business_id"]})
    if not x:
        raise HTTPException(404, {"code": "product_not_found"})
    from services import menu_photos as mp
    try:
        url = await mp.generate_product_ai(product_id, name=x.get("name", ""),
                                           description=x.get("description") or "")
    except Exception as e:
        raise HTTPException(502, {"code": "ai_photo_failed", "detail": str(e)[:200]})
    await db.products.update_one({"product_id": product_id},
                                 {"$set": {"image_url": url, "updated_at": now()}})
    return {"ok": True, "image_url": url}


# ───────────── Merchant: delivery config ─────────────
class DeliveryBody(BaseModel):
    pickup: bool = True
    delivery: bool = False
    fee_cents: int = Field(0, ge=0, le=1_000_000)
    free_over_cents: int = Field(0, ge=0, le=100_000_000)  # 0 => no free threshold


DEFAULT_DELIVERY = {"pickup": True, "delivery": False, "fee_cents": 0, "free_over_cents": 0}


@router.get("/delivery")
async def get_delivery(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    return {"delivery": p.get("product_delivery") or DEFAULT_DELIVERY}


@router.patch("/delivery")
async def set_delivery(body: DeliveryBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    await db.marketplace_profiles.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"product_delivery": body.model_dump(), "updated_at": now()}})
    return {"ok": True, "delivery": body.model_dump()}


# ───────────── Merchant: order fulfillment ─────────────
@router.get("/orders")
async def merchant_product_orders(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [_clean(o) async for o in db.product_orders.find(
        {"business_id": p["business_id"], "payment_status": "paid"}).sort("created_at", -1).limit(80)]
    return {"items": items}


class FulfillBody(BaseModel):
    status: str


async def _restock(db, order: Dict[str, Any]) -> None:
    for li in order.get("items", []):
        if li.get("variant_label"):
            await db.products.update_one(
                {"product_id": li["product_id"], "variants.label": li["variant_label"]},
                {"$inc": {"variants.$.stock": li["qty"]}})
        else:
            await db.products.update_one({"product_id": li["product_id"]},
                                         {"$inc": {"stock": li["qty"]}})


@router.patch("/orders/{order_id}/status")
async def update_fulfillment(order_id: str, body: FulfillBody, request: Request,
                             user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    o = await db.product_orders.find_one(
        {"order_id": order_id, "business_id": p["business_id"]})
    if not o:
        raise HTTPException(404, {"code": "order_not_found"})
    new_status = body.status
    if new_status == "canceled":
        if o.get("status") in ("delivered", "canceled", "shipped"):
            raise HTTPException(400, {"code": "cannot_cancel", "status": o.get("status")})
        await _restock(db, o)
    elif FULFILL_ADVANCE.get(o.get("status")) != new_status:
        raise HTTPException(400, {"code": "invalid_transition",
                                  "from": o.get("status"), "to": new_status})
    await db.product_orders.update_one(
        {"order_id": order_id},
        {"$set": {"status": new_status, "updated_at": now()},
         "$push": {"status_history": {"status": new_status, "at": now()}}})

    if new_status == "shipped":
        try:
            from routes.notifications import _enqueue
            await _enqueue(db, owner_user_id=o["user_id"], station_id="marketplace",
                           station_slug="marketplace", type_="product_shipped",
                           payload={"title": "Your order shipped! 📦",
                                    "body": f"{p.get('public_name')} · order is on the way.",
                                    "order_id": order_id},
                           dedupe_key=f"product_shipped_{order_id}")
        except Exception:
            pass
    if new_status == "delivered" and not o.get("points_awarded_done"):
        pts = int(o.get("points_to_award", 0))
        if pts > 0:
            await award_with_tier_bonus(
                db, user_id=o["user_id"], source="marketplace_product",
                source_id=order_id, base_points=pts,
                idempotency_key=f"product_delivered_{order_id}",
                metadata={"business_id": p["business_id"], "note": "Product order reward"})
            await db.merchant_bigpoint_accounts.update_one(
                {"business_id": p["business_id"], "funding_mode": "prepaid"},
                {"$inc": {"balance_points": -pts}, "$set": {"updated_at": now()}})
        await db.product_orders.update_one(
            {"order_id": order_id}, {"$set": {"points_awarded_done": True}})
    o = await db.product_orders.find_one({"order_id": order_id})
    return {"ok": True, "order": _clean(o)}


# ───────────── Consumer: browse + checkout ─────────────
@consumer_router.get("/businesses/{business_id}/products")
async def business_products(business_id: str, request: Request,
                            user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1, "cover_urls": 1, "bigpoints": 1, "happy_hour": 1, "product_delivery": 1})
    if not p:
        raise HTTPException(404, {"code": "business_not_found"})
    eff = effective_points(p)
    items = []
    async for x in db.products.find(
            {"business_id": business_id, "active": True}).sort("sort", 1):
        items.append({"product_id": x["product_id"], "name": x.get("name"),
                      "description": x.get("description"), "category": x.get("category"),
                      "price_cents": x.get("price_cents", 0), "stock": x.get("stock", 0),
                      "variants": x.get("variants", []), "bigpoints": x.get("bigpoints"),
                      "image_url": x.get("image_url")})
    return {"business_id": business_id, "public_name": p.get("public_name"),
            "cover_url": (p.get("cover_urls") or [None])[0],
            "default_bigpoints": (p.get("bigpoints") or {}).get("default_points", 0),
            "happy_hour": eff.get("happy_hour", False), "points_multiplier": eff.get("multiplier", 1),
            "delivery": p.get("product_delivery") or DEFAULT_DELIVERY, "products": items}


class ProductCheckoutItem(BaseModel):
    product_id: str
    variant_label: Optional[str] = None
    qty: int = Field(1, ge=1, le=100)


class ProductCheckoutBody(BaseModel):
    business_id: str
    items: List[ProductCheckoutItem]
    fulfillment: str = "pickup"  # pickup | delivery
    address: Optional[str] = Field(None, max_length=400)
    origin_url: Optional[str] = None
    use_gift_card: bool = True


async def _pick_gift_card(db, user):
    uid = user.get("user_id")
    email = (user.get("email") or "").lower()
    best = None
    async for c in db.gift_cards.find(
            {"status": "active", "balance_cents": {"$gt": 0},
             "$or": [{"owner_user_id": uid}, {"gifted_to_email": email}]}):
        if best is None or c.get("balance_cents", 0) > best.get("balance_cents", 0):
            best = c
    return best


@consumer_router.post("/product-orders/checkout")
async def product_checkout(body: ProductCheckoutBody, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    if not body.items:
        raise HTTPException(400, {"code": "empty_cart"})
    profile = await db.marketplace_profiles.find_one(
        {"business_id": body.business_id, "status": "approved", "subscription_active": True})
    if not profile:
        raise HTTPException(404, {"code": "business_unavailable"})
    delivery_cfg = profile.get("product_delivery") or DEFAULT_DELIVERY
    if body.fulfillment == "delivery":
        if not delivery_cfg.get("delivery"):
            raise HTTPException(400, {"code": "delivery_unavailable"})
        if not body.address:
            raise HTTPException(400, {"code": "address_required"})
    elif not delivery_cfg.get("pickup", True):
        raise HTTPException(400, {"code": "pickup_unavailable"})

    line_items, subtotal = [], 0
    for ci in body.items:
        prod = await db.products.find_one(
            {"product_id": ci.product_id, "business_id": body.business_id, "active": True})
        if not prod:
            raise HTTPException(400, {"code": "product_unavailable", "product_id": ci.product_id})
        price = int(prod.get("price_cents", 0))
        avail = int(prod.get("stock", 0))
        if ci.variant_label:
            v = next((vv for vv in prod.get("variants", []) if vv["label"] == ci.variant_label), None)
            if not v:
                raise HTTPException(400, {"code": "variant_unavailable", "product_id": ci.product_id})
            if int(v.get("price_cents") or 0) > 0:
                price = int(v["price_cents"])
            avail = int(v.get("stock", 0))
        elif prod.get("variants"):
            raise HTTPException(400, {"code": "variant_required", "product_id": ci.product_id})
        if avail < ci.qty:
            raise HTTPException(409, {"code": "out_of_stock", "product_id": ci.product_id})
        subtotal += price * ci.qty
        line_items.append({"product_id": ci.product_id, "variant_label": ci.variant_label,
                           "name": prod.get("name"), "price_cents": price, "qty": ci.qty})
    if subtotal <= 0:
        raise HTTPException(400, {"code": "zero_total"})

    # Delivery fee.
    delivery_fee = 0
    if body.fulfillment == "delivery":
        fee = int(delivery_cfg.get("fee_cents", 0))
        free_over = int(delivery_cfg.get("free_over_cents", 0))
        delivery_fee = 0 if (free_over > 0 and subtotal >= free_over) else fee

    # Gift-card auto-apply against (subtotal + delivery).
    gross = subtotal + delivery_fee
    gift_applied, gift_card_id = 0, None
    if body.use_gift_card:
        gc = await _pick_gift_card(db, user)
        if gc:
            gift_applied = min(int(gc.get("balance_cents", 0)), gross)
            gift_card_id = gc.get("card_id")
    total = gross - gift_applied

    eff = effective_points(profile)
    points = int(eff.get("points", 0))
    order_id = new_id("po")
    order = {
        "order_id": order_id, "business_id": body.business_id,
        "business_name": profile.get("public_name"), "user_id": user.get("user_id"),
        "items": line_items, "subtotal_cents": subtotal, "delivery_fee_cents": delivery_fee,
        "fulfillment": body.fulfillment, "address": body.address,
        "gift_card_applied_cents": gift_applied, "gift_card_id": gift_card_id,
        "total_cents": total, "points_to_award": points, "points_awarded_done": False,
        "status": "pending_payment", "payment_status": "pending", "session_id": None,
        "status_history": [], "created_at": now(), "updated_at": now(),
    }

    async def _decrement_stock():
        for li in line_items:
            if li.get("variant_label"):
                await db.products.update_one(
                    {"product_id": li["product_id"], "variants.label": li["variant_label"]},
                    {"$inc": {"variants.$.stock": -li["qty"]}})
            else:
                await db.products.update_one({"product_id": li["product_id"]},
                                             {"$inc": {"stock": -li["qty"]}})

    async def _deduct_gift():
        if not gift_card_id or gift_applied <= 0:
            return
        card = await db.gift_cards.find_one({"card_id": gift_card_id})
        bal = int((card or {}).get("balance_cents", 0))
        take = min(bal, gift_applied)
        newb = bal - take
        await db.gift_cards.update_one({"card_id": gift_card_id},
            {"$set": {"balance_cents": newb, "status": "active" if newb > 0 else "spent",
                      "updated_at": now()}})
        await db.gift_card_redemptions.insert_one({
            "redemption_id": new_id("gcr"), "card_id": gift_card_id,
            "user_id": user.get("user_id"), "amount_cents": take, "balance_after_cents": newb,
            "source": "marketplace_product", "created_at": now()})

    if total <= 0:
        await _deduct_gift()
        await _decrement_stock()
        order["status"] = "paid"
        order["payment_status"] = "paid"
        order["status_history"] = [{"status": "paid", "at": now()}]
        await db.product_orders.insert_one(dict(order))
        return {"ok": True, "order_id": order_id, "status": "paid", "checkout_url": None,
                "total_cents": 0, "delivery_fee_cents": delivery_fee,
                "gift_card_applied_cents": gift_applied}

    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
                     "product_data": {"name": f"{profile.get('public_name')} — Order"},
                     "unit_amount": total}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "product_order", "order_id": order_id, "business_id": body.business_id})
    order["session_id"] = session.id
    await db.product_orders.insert_one(dict(order))
    return {"ok": True, "order_id": order_id, "status": "pending_payment",
            "checkout_url": session.url, "session_id": session.id, "total_cents": total,
            "delivery_fee_cents": delivery_fee, "gift_card_applied_cents": gift_applied}


@consumer_router.get("/product-orders")
async def my_product_orders(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    items = [_clean(o) async for o in db.product_orders.find(
        {"user_id": user.get("user_id")}).sort("created_at", -1).limit(50)]
    return {"items": items}


@consumer_router.get("/product-orders/{order_id}/status")
async def product_order_status(order_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    o = await db.product_orders.find_one(
        {"order_id": order_id, "user_id": user.get("user_id")})
    if not o:
        raise HTTPException(404, {"code": "order_not_found"})
    if o.get("payment_status") != "paid" and o.get("session_id") and stripe.api_key:
        try:
            sess = stripe.checkout.Session.retrieve(o["session_id"])
            if sess.get("payment_status") == "paid" or sess.get("status") == "complete":
                if o.get("payment_status") != "paid":
                    # Deduct gift card + decrement stock on first confirmation.
                    if o.get("gift_card_id") and o.get("gift_card_applied_cents", 0) > 0:
                        card = await db.gift_cards.find_one({"card_id": o["gift_card_id"]})
                        bal = int((card or {}).get("balance_cents", 0))
                        take = min(bal, o["gift_card_applied_cents"])
                        newb = bal - take
                        await db.gift_cards.update_one({"card_id": o["gift_card_id"]},
                            {"$set": {"balance_cents": newb, "status": "active" if newb > 0 else "spent",
                                      "updated_at": now()}})
                    for li in o.get("items", []):
                        if li.get("variant_label"):
                            await db.products.update_one(
                                {"product_id": li["product_id"], "variants.label": li["variant_label"]},
                                {"$inc": {"variants.$.stock": -li["qty"]}})
                        else:
                            await db.products.update_one({"product_id": li["product_id"]},
                                                         {"$inc": {"stock": -li["qty"]}})
                    await db.product_orders.update_one(
                        {"order_id": order_id, "payment_status": {"$ne": "paid"}},
                        {"$set": {"payment_status": "paid", "status": "paid", "updated_at": now()},
                         "$push": {"status_history": {"status": "paid", "at": now()}}})
                    o = await db.product_orders.find_one({"order_id": order_id})
        except Exception:
            pass
    return {"status": o.get("status"), "payment_status": o.get("payment_status"),
            "order": _clean(o)}


# ───────────── Consumer: loyalty status ─────────────
@consumer_router.get("/loyalty")
async def loyalty(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    return await loyalty_status(db, user.get("user_id"))


async def ensure_products_indexes(db) -> None:
    await db.products.create_index("product_id", unique=True)
    await db.products.create_index([("business_id", 1), ("sort", 1)])
    await db.product_orders.create_index("order_id", unique=True)
    await db.product_orders.create_index([("user_id", 1), ("created_at", -1)])
    await db.product_orders.create_index([("business_id", 1), ("created_at", -1)])


__all__ = ["router", "consumer_router", "ensure_products_indexes"]
