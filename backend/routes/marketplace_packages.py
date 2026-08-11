"""Marketplace Packages (Phase E) — a venue sells a prepaid bundle
(e.g. "5 haircuts", "10 classes"). Buyer pays with Stripe card or BigPoints
and receives N redemption credits, redeemed over time at that venue.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services.marketplace import now, new_id
from services.points_service import PointsService
from services.gift_notify import send_gift_emails

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""
POINTS_PER_DOLLAR = 100

router = APIRouter(prefix="/api/merchant/marketplace/packages", tags=["marketplace-packages"])
consumer_router = APIRouter(prefix="/api/shop", tags=["marketplace-packages-consumer"])


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k in ("created_at", "updated_at", "redeemed_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


class PackageBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=280)
    price_cents: int = Field(..., ge=100, le=1_000_000)
    credits: int = Field(..., ge=1, le=1000)
    allow_points: bool = True
    allow_card: bool = True
    active: bool = True


# ───────────── Merchant CRUD ─────────────
@router.get("")
async def list_packages(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = []
    async for x in db.package_products.find({"business_id": p["business_id"]}).sort("created_at", 1):
        x = _clean(x)
        x["sold_count"] = await db.packages.count_documents(
            {"package_id": x["package_id"], "status": {"$in": ["active", "used_up"]}})
        items.append(x)
    return {"items": items}


@router.post("/items")
async def create_package(body: PackageBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    pid = new_id("pkgprod")
    doc = {"package_id": pid, "business_id": p["business_id"], "sponsor_name": p.get("public_name"),
           "name": body.name.strip(), "description": (body.description or "").strip() or None,
           "price_cents": body.price_cents, "credits": body.credits,
           "allow_points": body.allow_points, "allow_card": body.allow_card,
           "points_per_dollar": POINTS_PER_DOLLAR, "active": body.active,
           "created_at": now(), "updated_at": now()}
    await db.package_products.insert_one(dict(doc))
    return {"ok": True, "package": _clean(doc)}


@router.patch("/items/{package_id}")
async def update_package(package_id: str, body: PackageBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.package_products.update_one(
        {"package_id": package_id, "business_id": p["business_id"]},
        {"$set": {"name": body.name.strip(), "description": (body.description or "").strip() or None,
                  "price_cents": body.price_cents, "credits": body.credits,
                  "allow_points": body.allow_points, "allow_card": body.allow_card,
                  "sponsor_name": p.get("public_name"), "active": body.active, "updated_at": now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "package_not_found"})
    x = await db.package_products.find_one({"package_id": package_id})
    return {"ok": True, "package": _clean(x)}


@router.delete("/items/{package_id}")
async def delete_package(package_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.package_products.delete_one(
        {"package_id": package_id, "business_id": p["business_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, {"code": "package_not_found"})
    return {"ok": True}


# ───────────── Consumer ─────────────
async def _activate(db, product: Dict[str, Any], user_id: str, method: str,
                    session_id: Optional[str] = None, purchase_id: Optional[str] = None,
                    gift_to_email: Optional[str] = None, message: Optional[str] = None) -> Dict[str, Any]:
    pid = purchase_id or new_id("pkg")
    is_gift = bool(gift_to_email)
    owner = user_id
    gto = None
    if is_gift:
        gto = gift_to_email.lower().strip()
        rec = await db.users.find_one({"email": gto}, {"user_id": 1})
        owner = rec["user_id"] if rec else None  # unregistered → surfaces by email
    doc = {"purchase_id": pid, "package_id": product["package_id"],
           "business_id": product["business_id"], "user_id": owner,
           "buyer_user_id": user_id, "is_gift": is_gift, "gifted_to_email": gto,
           "gift_message": (message or None) if is_gift else None,
           "sponsor_name": product.get("sponsor_name"),
           "name": product["name"], "credits_total": product["credits"],
           "credits_remaining": product["credits"], "status": "active",
           "method": method, "session_id": session_id, "created_at": now(), "updated_at": now()}
    await db.packages.insert_one(dict(doc))
    return _clean(doc)


async def _schedule_gift_email(db, bg: Optional[BackgroundTasks], pkg: Dict[str, Any]) -> None:
    if not (bg and pkg.get("is_gift") and pkg.get("gifted_to_email")):
        return
    buyer = await db.users.find_one({"user_id": pkg.get("buyer_user_id")},
                                    {"email": 1, "display_name": 1, "name": 1}) or {}
    bg.add_task(send_gift_emails, kind="package", item_name=pkg.get("name"),
                sponsor_name=pkg.get("sponsor_name"),
                buyer_email=buyer.get("email"),
                buyer_name=buyer.get("display_name") or buyer.get("name") or "A friend",
                recipient_email=pkg.get("gifted_to_email"),
                message=pkg.get("gift_message"))


@consumer_router.get("/businesses/{business_id}/packages")
async def business_packages(business_id: str, request: Request,
                            user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    biz = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1})
    if not biz:
        raise HTTPException(404, {"code": "business_not_found"})
    items = [_clean(x) async for x in db.package_products.find(
        {"business_id": business_id, "active": True}).sort("price_cents", 1)]
    mine = []
    balance = 0
    if user:
        uid = user.get("user_id")
        email = (user.get("email") or "").lower().strip()
        balance = await PointsService(db).get_balance(uid)
        ors: List[Dict[str, Any]] = [{"user_id": uid}]
        if email:
            ors.append({"gifted_to_email": email})
        async for m in db.packages.find(
                {"business_id": business_id, "status": "active", "$or": ors}).sort("created_at", -1):
            mine.append(_clean(dict(m)))
    return {"business_id": business_id, "public_name": biz.get("public_name"),
            "points_per_dollar": POINTS_PER_DOLLAR, "points_balance": balance,
            "items": items, "mine": mine}


class PurchaseBody(BaseModel):
    package_id: str
    method: str = Field(..., description="points | card")
    origin_url: Optional[str] = None
    gift_to_email: Optional[str] = None
    message: Optional[str] = Field(None, max_length=280)


@consumer_router.post("/packages/purchase")
async def purchase_package(body: PurchaseBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    product = await db.package_products.find_one({"package_id": body.package_id, "active": True})
    if not product:
        raise HTTPException(404, {"code": "package_not_found"})

    if body.method == "points":
        if not product.get("allow_points", True):
            raise HTTPException(400, {"code": "points_not_allowed"})
        points_cost = round(product["price_cents"] / 100.0 * POINTS_PER_DOLLAR)
        balance = await PointsService(db).get_balance(uid)
        if balance < points_cost:
            raise HTTPException(400, {"code": "insufficient_points", "needed": points_cost, "have": balance})
        idem = f"package:points:{uid}:{uuid.uuid4().hex[:8]}"
        await PointsService(db).spend(user_id=uid, source="package_purchase", amount=points_cost,
                                      source_id=body.package_id, idempotency_key=idem,
                                      metadata={"package_id": body.package_id})
        pkg = await _activate(db, product, uid, "points",
                              gift_to_email=body.gift_to_email, message=body.message)
        await _schedule_gift_email(db, background_tasks, pkg)
        return {"ok": True, "method": "points", "points_spent": points_cost, "package": pkg}

    if body.method == "card":
        if not stripe.api_key:
            raise HTTPException(503, {"code": "stripe_unconfigured"})
        if not product.get("allow_card", True):
            raise HTTPException(400, {"code": "card_not_allowed"})
        origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
        if not origin:
            raise HTTPException(400, {"code": "origin_required"})
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price_data": {
                "currency": "usd",
                "product_data": {"name": f"{product.get('sponsor_name')} — {product['name']}"},
                "unit_amount": int(product["price_cents"])}, "quantity": 1}],
            success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/payment/cancel",
            metadata={"kind": "marketplace_package", "package_id": body.package_id, "buyer_id": uid,
                      "gift_to_email": body.gift_to_email or ""})
        await db.package_purchases.insert_one({
            "session_id": session.id, "buyer_user_id": uid, "package_id": body.package_id,
            "gift_to_email": body.gift_to_email, "message": body.message,
            "status": "pending", "created_at": now()})
        return {"ok": True, "method": "card", "checkout_url": session.url, "session_id": session.id}

    raise HTTPException(400, {"code": "bad_method"})


@consumer_router.get("/packages/purchase/{session_id}/status")
async def purchase_status(session_id: str, request: Request,
                          background_tasks: BackgroundTasks,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    pur = await db.package_purchases.find_one({"session_id": session_id})
    if not pur:
        raise HTTPException(404, {"code": "purchase_not_found"})
    if pur.get("status") == "paid" and pur.get("purchase_id"):
        pkg = await db.packages.find_one({"purchase_id": pur["purchase_id"]})
        return {"status": "paid", "package": _clean(dict(pkg)) if pkg else None}
    if not stripe.api_key:
        return {"status": pur.get("status", "pending")}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": pur.get("status", "pending")}
    if sess.get("payment_status") == "paid":
        product = await db.package_products.find_one({"package_id": pur["package_id"]})
        if not product:
            return {"status": "paid", "package": None}
        pkg = await _activate(db, product, pur["buyer_user_id"], "card", session_id=session_id,
                              gift_to_email=pur.get("gift_to_email"), message=pur.get("message"))
        await db.package_purchases.update_one(
            {"session_id": session_id},
            {"$set": {"status": "paid", "purchase_id": pkg["purchase_id"], "paid_at": now()}})
        await _schedule_gift_email(db, background_tasks, pkg)
        return {"status": "paid", "package": pkg}
    return {"status": "pending"}


@consumer_router.get("/packages/mine")
async def my_packages(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    email = (user.get("email") or "").lower().strip()
    ors: List[Dict[str, Any]] = [{"user_id": uid}]
    if email:
        ors.append({"gifted_to_email": email})
    out = []
    async for x in db.packages.find(
            {"status": {"$in": ["active", "used_up"]}, "$or": ors}).sort("created_at", -1):
        # Recipient logged in after being gifted → claim ownership so they can redeem.
        if not x.get("user_id") and email and x.get("gifted_to_email") == email:
            await db.packages.update_one(
                {"purchase_id": x["purchase_id"]}, {"$set": {"user_id": uid}})
            x["user_id"] = uid
        c = _clean(dict(x))
        c["received_gift"] = bool(x.get("is_gift") and x.get("buyer_user_id") != uid)
        out.append(c)
    return {"items": out}


@consumer_router.post("/packages/{purchase_id}/redeem")
async def redeem_package(purchase_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    pkg = await db.packages.find_one({"purchase_id": purchase_id, "user_id": user.get("user_id")})
    if not pkg:
        raise HTTPException(404, {"code": "package_not_found"})
    if pkg.get("status") != "active" or pkg.get("credits_remaining", 0) <= 0:
        raise HTTPException(400, {"code": "no_credits"})
    remaining = pkg["credits_remaining"] - 1
    status = "used_up" if remaining <= 0 else "active"
    await db.packages.update_one(
        {"purchase_id": purchase_id},
        {"$set": {"credits_remaining": remaining, "status": status, "updated_at": now()}})
    await db.package_redemptions.insert_one({
        "redemption_id": new_id("pkgr"), "purchase_id": purchase_id,
        "user_id": user.get("user_id"), "business_id": pkg["business_id"], "redeemed_at": now()})
    return {"ok": True, "credits_remaining": remaining, "status": status}


__all__ = ["router", "consumer_router"]
