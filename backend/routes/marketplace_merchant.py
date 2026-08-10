"""Marketplace Merchant API — "Sell on RadioLife" registration, BigPoints
settings + live $ cost preview, and the merchant BigPoints funding account
(prepaid balance via Stripe, or auto-deduct from payout)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.marketplace import now, new_id, resolve_point_cost_cents, resolve_commission

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace", tags=["marketplace-merchant"])


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc.pop("_id", None)
    for k in ("created_at", "updated_at", "approved_at", "effective_date"):
        v = doc.get(k)
        if hasattr(v, "isoformat"):
            doc[k] = v.isoformat()
    return doc


# ───────────── Onboarding ("Sell on RadioLife") ─────────────
class BigPointsConfig(BaseModel):
    mode: str = Field("default", description="default|per_order_value|per_item")
    default_points: int = Field(50, ge=0, le=100000)
    points_per_dollar: float = Field(2.0, ge=0, le=100)
    product_overrides: Dict[str, int] = {}
    service_overrides: Dict[str, int] = {}


class OnboardingBody(BaseModel):
    business_type: str
    legal_name: str = Field(..., min_length=1, max_length=200)
    public_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    category: str
    subcategory: Optional[str] = None
    logo_url: Optional[str] = None
    cover_urls: List[str] = []
    locations: List[Dict[str, Any]] = []
    verification: Dict[str, Any] = {}
    stripe_account_id: Optional[str] = None
    sells: List[str] = []
    bigpoints: BigPointsConfig = BigPointsConfig()
    funding_mode: str = Field("auto_deduct", description="prepaid|auto_deduct")
    commission_agreed: bool = False
    price_parity_certified: bool = False


@router.post("/onboarding")
async def onboarding(body: OnboardingBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    cat = await db.marketplace_categories.find_one({"key": body.category, "active": True})
    if not cat:
        raise HTTPException(400, {"code": "bad_category"})
    if not body.commission_agreed:
        raise HTTPException(400, {"code": "commission_agreement_required"})
    # BigPoints are required for marketplace businesses.
    if body.bigpoints.mode == "default" and body.bigpoints.default_points <= 0:
        raise HTTPException(400, {"code": "bigpoints_required"})
    min_pts = int(cat.get("min_bigpoints", 0))
    if body.bigpoints.mode == "default" and body.bigpoints.default_points < min_pts:
        raise HTTPException(400, {"code": "below_min_bigpoints", "min": min_pts})
    # Restaurant price-parity certification.
    if body.category == "restaurant" and not body.price_parity_certified:
        raise HTTPException(400, {"code": "price_parity_required"})

    existing = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    business_id = existing["business_id"] if existing else new_id("biz")
    market = (body.locations[0].get("city") if body.locations else None) or user.get("market")
    profile = {
        "business_id": business_id, "owner_user_id": user.get("user_id"),
        "business_type": body.business_type, "legal_name": body.legal_name,
        "public_name": body.public_name, "description": body.description,
        "phone": body.phone, "email": body.email or user.get("email"),
        "website": body.website, "category": body.category, "subcategory": body.subcategory,
        "logo_url": body.logo_url, "cover_urls": body.cover_urls,
        "locations": body.locations, "verification": body.verification,
        "stripe_account_id": body.stripe_account_id, "sells": body.sells,
        "bigpoints": body.bigpoints.model_dump(), "funding_mode": body.funding_mode,
        "market": market,
        "commission_agreed": body.commission_agreed,
        "price_parity": {"certified": body.price_parity_certified,
                         "website": body.website, "certified_at": now(),
                         "certified_by": user.get("user_id")} if body.price_parity_certified else None,
        "status": "pending", "rejection_reason": None,
        "updated_at": now(),
    }
    await db.marketplace_profiles.update_one(
        {"business_id": business_id},
        {"$set": profile, "$setOnInsert": {"created_at": now()}}, upsert=True)
    # Mirror into the shared businesses collection (inactive until approved).
    await db.businesses.update_one(
        {"business_id": business_id},
        {"$set": {"business_id": business_id, "owner_user_id": user.get("user_id"),
                  "name": body.public_name, "category": body.category,
                  "city": market, "active": False, "verified": False,
                  "updated_at": now()},
         "$setOnInsert": {"created_at": now()}}, upsert=True)
    # Ensure a BigPoints funding account exists.
    await db.merchant_bigpoint_accounts.update_one(
        {"business_id": business_id},
        {"$setOnInsert": {"business_id": business_id, "funding_mode": body.funding_mode,
                          "balance_points": 0,
                          "auto_reload": {"enabled": False, "threshold": 2000, "amount": 10000},
                          "created_at": now(), "updated_at": now()}},
        upsert=True)
    saved = await db.marketplace_profiles.find_one({"business_id": business_id})
    return {"ok": True, "profile": _clean(saved), "business_id": business_id}


@router.get("/profile")
async def my_profile(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        return {"profile": None}
    return {"profile": _clean(p)}


# ───────────── BigPoints settings + cost preview ─────────────
async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


@router.get("/bigpoints/settings")
async def get_bp_settings(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    cost = await resolve_point_cost_cents(db, market=p.get("market"),
                                          category=p.get("category"),
                                          merchant_id=p.get("business_id"))
    return {"bigpoints": p.get("bigpoints"), "cost_per_point_cents": cost}


@router.patch("/bigpoints/settings")
async def set_bp_settings(body: BigPointsConfig, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    cat = await db.marketplace_categories.find_one({"key": p.get("category")})
    min_pts = int((cat or {}).get("min_bigpoints", 0))
    if body.mode == "default" and body.default_points < min_pts:
        raise HTTPException(400, {"code": "below_min_bigpoints", "min": min_pts})
    await db.marketplace_profiles.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"bigpoints": body.model_dump(), "updated_at": now()}})
    cost = await resolve_point_cost_cents(db, market=p.get("market"),
                                          category=p.get("category"),
                                          merchant_id=p["business_id"])
    return {"ok": True, "cost_per_point_cents": cost}


class PreviewBody(BaseModel):
    points: Optional[int] = None
    order_value_cents: Optional[int] = None


@router.post("/bigpoints/preview")
async def bp_preview(body: PreviewBody, request: Request, user: dict = Depends(current_user)):
    """Show the merchant's $ cost for issuing BigPoints, before publishing."""
    db = request.app.state.db
    p = await _my_business(db, user)
    bp = p.get("bigpoints", {})
    cost = await resolve_point_cost_cents(db, market=p.get("market"),
                                          category=p.get("category"),
                                          merchant_id=p["business_id"])
    if body.points is not None:
        pts = int(body.points)
    elif body.order_value_cents is not None:
        pts = round((body.order_value_cents / 100.0) * float(bp.get("points_per_dollar", 2.0)))
    else:
        pts = int(bp.get("default_points", 0))
    return {"points": pts, "cost_per_point_cents": cost,
            "estimated_cost_cents": round(pts * cost),
            "estimated_cost_display": f"${(pts * cost) / 100.0:.2f}"}


# ───────────── Funding account ─────────────
@router.get("/bigpoints/account")
async def bp_account(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    acct = await db.merchant_bigpoint_accounts.find_one({"business_id": p["business_id"]})
    if not acct:
        acct = {"business_id": p["business_id"], "funding_mode": p.get("funding_mode", "auto_deduct"),
                "balance_points": 0, "auto_reload": {"enabled": False, "threshold": 2000, "amount": 10000}}
        await db.merchant_bigpoint_accounts.insert_one({**acct, "created_at": now(), "updated_at": now()})
    txns = [_clean(t) async for t in db.bigpoint_funding_transactions.find(
        {"business_id": p["business_id"]}).sort("created_at", -1).limit(20)]
    return {"account": _clean(acct), "transactions": txns}


class FundBody(BaseModel):
    points: int = Field(..., gt=0, le=10_000_000)
    origin_url: Optional[str] = None


@router.post("/bigpoints/fund")
async def bp_fund(body: FundBody, request: Request, user: dict = Depends(current_user)):
    """Prepaid top-up via Stripe Checkout — points credited on paid."""
    db = request.app.state.db
    p = await _my_business(db, user)
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    cost = await resolve_point_cost_cents(db, market=p.get("market"),
                                          category=p.get("category"),
                                          merchant_id=p["business_id"])
    amount_cents = round(body.points * cost)
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
                     "product_data": {"name": f"{body.points} BigPoints inventory"},
                     "unit_amount": amount_cents}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "bigpoints_fund", "business_id": p["business_id"],
                  "points": str(body.points)})
    await db.bigpoint_funding_transactions.insert_one({
        "txn_id": new_id("bpf"), "business_id": p["business_id"],
        "session_id": session.id, "points": body.points, "amount_cents": amount_cents,
        "type": "prepaid_topup", "status": "pending", "created_at": now()})
    return {"ok": True, "checkout_url": session.url, "session_id": session.id,
            "amount_cents": amount_cents}


@router.get("/bigpoints/fund/{session_id}/status")
async def bp_fund_status(session_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    txn = await db.bigpoint_funding_transactions.find_one(
        {"session_id": session_id, "business_id": p["business_id"]})
    if not txn:
        raise HTTPException(404, {"code": "txn_not_found"})
    if txn.get("status") == "paid":
        acct = await db.merchant_bigpoint_accounts.find_one({"business_id": p["business_id"]})
        return {"status": "paid", "balance_points": (acct or {}).get("balance_points", 0)}
    if not stripe.api_key:
        return {"status": txn.get("status", "pending")}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": txn.get("status", "pending")}
    if sess.get("payment_status") == "paid":
        await db.merchant_bigpoint_accounts.update_one(
            {"business_id": p["business_id"]},
            {"$inc": {"balance_points": int(txn["points"])},
             "$set": {"updated_at": now()}})
        await db.bigpoint_funding_transactions.update_one(
            {"session_id": session_id}, {"$set": {"status": "paid", "paid_at": now()}})
        acct = await db.merchant_bigpoint_accounts.find_one({"business_id": p["business_id"]})
        return {"status": "paid", "balance_points": (acct or {}).get("balance_points", 0)}
    return {"status": "pending"}


class AutoReloadBody(BaseModel):
    funding_mode: Optional[str] = None
    enabled: bool = False
    threshold: int = Field(2000, ge=0)
    amount: int = Field(10000, gt=0)


@router.patch("/bigpoints/auto-reload")
async def set_auto_reload(body: AutoReloadBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    upd: Dict[str, Any] = {"auto_reload": {"enabled": body.enabled,
                           "threshold": body.threshold, "amount": body.amount},
                           "updated_at": now()}
    if body.funding_mode in ("prepaid", "auto_deduct"):
        upd["funding_mode"] = body.funding_mode
    await db.merchant_bigpoint_accounts.update_one(
        {"business_id": p["business_id"]}, {"$set": upd}, upsert=True)
    return {"ok": True}


__all__ = ["router"]
