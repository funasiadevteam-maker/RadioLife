"""Promoted Marketplace (Phase F) — merchants pay to boost their shop higher in
Shop search + a "Promoted near you" rail on the Shop home. Tiered flat fee via
Stripe hosted Checkout, ADMIN-approved before it goes live. Admins can also comp
(grant) a promotion for free. The active promotion writes `promoted_until` +
`promotion_weight` onto the marketplace_profile; shop reads boost + badge it."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace/promotion", tags=["marketplace-promotion"])
admin_router = APIRouter(prefix="/api/admin/marketplace/promotions", tags=["admin-marketplace-promotion"])

# Tier catalogue — flat fee for a fixed window. Higher weight ranks earlier.
PROMO_TIERS = [
    {"tier": "spotlight_7", "name": "Spotlight", "days": 7, "price_cents": 1999, "weight": 1,
     "blurb": "7 days of higher search placement + a Promoted badge."},
    {"tier": "boost_14", "name": "Boost", "days": 14, "price_cents": 3499, "weight": 2,
     "blurb": "14 days boosted, plus the Promoted-near-you rail on the Shop home."},
    {"tier": "premium_30", "name": "Premium", "days": 30, "price_cents": 5999, "weight": 3,
     "blurb": "30 days top placement + Promoted rail + badge."},
]
TIERS_BY_ID = {t["tier"]: t for t in PROMO_TIERS}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k in ("created_at", "activated_at", "paid_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


async def _apply_active(db, business_id: str, tier: str, weight: int, expires_iso: str):
    """Write the active promotion onto the profile so shop reads boost + badge it.
    Never let a weaker/earlier promotion demote a currently-active stronger one."""
    prof = await db.marketplace_profiles.find_one({"business_id": business_id}) or {}
    cur_until = prof.get("promoted_until")
    cur_weight = int(prof.get("promotion_weight") or 0)
    cur_active = bool(cur_until and str(cur_until) > _iso(_now()))
    if cur_active and (cur_weight > weight or (cur_weight == weight and str(cur_until) >= expires_iso)):
        return
    await db.marketplace_profiles.update_one(
        {"business_id": business_id},
        {"$set": {"promoted_until": expires_iso, "promotion_tier": tier, "promotion_weight": weight}})


class CheckoutBody(BaseModel):
    tier: str
    origin_url: Optional[str] = None


@router.get("/tiers")
async def tiers(request: Request, user: dict = Depends(current_user)):
    return {"tiers": PROMO_TIERS}


@router.get("")
async def my_promotion(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await sweep_renewals(db)  # lazily auto-renew anything that just expired
    p = await _my_business(db, user)
    now_iso = _iso(_now())
    active = await db.marketplace_promotions.find_one(
        {"business_id": p["business_id"], "status": "active", "expires_at": {"$gt": now_iso}})
    recent = [_clean(x) async for x in db.marketplace_promotions.find(
        {"business_id": p["business_id"]}).sort("created_at", -1).limit(10)]
    # Saved cards power auto-renew (off-session charge at expiry).
    cards: Dict[str, Any] = {"cards": [], "default_id": None}
    try:
        from services.saved_cards_service import ensure_stripe_customer, list_cards
        cust = await ensure_stripe_customer(db, user)
        if cust:
            cards = list_cards(cust)
    except Exception:
        pass
    return {"business_id": p["business_id"], "public_name": p.get("public_name"),
            "active": _clean(dict(active)) if active else None, "items": recent,
            "auto_renew": bool((active or {}).get("auto_renew")),
            "auto_renew_pm": (active or {}).get("auto_renew_pm"),
            "saved_cards": cards.get("cards", []), "default_pm": cards.get("default_id")}


@router.post("/checkout")
async def checkout(body: CheckoutBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    tier = TIERS_BY_ID.get(body.tier)
    if not tier:
        raise HTTPException(400, {"code": "bad_tier"})
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    pid = f"promo_{uuid.uuid4().hex[:10]}"
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {
            "currency": "usd",
            "product_data": {"name": f"RadioLife Promotion — {tier['name']} "
                                     f"({tier['days']}d) · {p.get('public_name')}"},
            "unit_amount": int(tier["price_cents"])}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "marketplace_promotion", "promotion_id": pid,
                  "business_id": p["business_id"], "tier": tier["tier"]})
    await db.marketplace_promotions.insert_one({
        "promotion_id": pid, "business_id": p["business_id"], "owner_user_id": user.get("user_id"),
        "public_name": p.get("public_name"), "tier": tier["tier"], "name": tier["name"],
        "days": tier["days"], "price_cents": tier["price_cents"], "weight": tier["weight"],
        "status": "pending_payment", "paid": False, "stripe_session_id": session.id,
        "expires_at": None, "created_at": _now()})
    return {"ok": True, "promotion_id": pid, "checkout_url": session.url, "session_id": session.id}


@router.get("/{promotion_id}/status")
async def promotion_status(promotion_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    promo = await db.marketplace_promotions.find_one({"promotion_id": promotion_id})
    if not promo or promo.get("owner_user_id") != user.get("user_id"):
        raise HTTPException(404, {"code": "promotion_not_found"})
    if promo.get("status") == "pending_payment" and stripe.api_key and promo.get("stripe_session_id"):
        try:
            sess = stripe.checkout.Session.retrieve(promo["stripe_session_id"])
        except Exception:
            sess = None
        if sess and sess.get("payment_status") == "paid":
            await db.marketplace_promotions.update_one(
                {"promotion_id": promotion_id},
                {"$set": {"status": "pending_review", "paid": True, "paid_at": _now()}})
            promo = await db.marketplace_promotions.find_one({"promotion_id": promotion_id})
    return {"status": promo.get("status"), "promotion": _clean(dict(promo))}


# ---- Admin review ----
class RejectBody(BaseModel):
    note: Optional[str] = Field(None, max_length=280)


class GrantBody(BaseModel):
    business_id: str
    tier: str = "spotlight_7"


@admin_router.get("")
async def admin_list(request: Request, status: str = "pending_review", _a=Depends(require_admin)):
    db = request.app.state.db
    q: Dict[str, Any] = {} if status == "all" else {"status": status}
    out = [_clean(x) async for x in
           db.marketplace_promotions.find(q).sort("created_at", -1).limit(200)]
    return {"items": out}


@admin_router.post("/{promotion_id}/approve")
async def admin_approve(promotion_id: str, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    promo = await db.marketplace_promotions.find_one({"promotion_id": promotion_id})
    if not promo:
        raise HTTPException(404, {"code": "promotion_not_found"})
    if promo.get("status") != "pending_review":
        # Only paid, in-review requests are approvable; comps use /grant.
        raise HTTPException(400, {"code": "not_reviewable", "status": promo.get("status")})
    days = int(promo.get("days") or 7)
    activated = _now()
    expires_iso = _iso(activated + timedelta(days=days))
    await db.marketplace_promotions.update_one(
        {"promotion_id": promotion_id},
        {"$set": {"status": "active", "activated_at": activated, "expires_at": expires_iso}})
    await _apply_active(db, promo["business_id"], promo["tier"], int(promo.get("weight") or 1), expires_iso)
    saved = await db.marketplace_promotions.find_one({"promotion_id": promotion_id})
    return {"ok": True, "promotion": _clean(dict(saved))}


@admin_router.post("/{promotion_id}/reject")
async def admin_reject(promotion_id: str, body: RejectBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    r = await db.marketplace_promotions.update_one(
        {"promotion_id": promotion_id},
        {"$set": {"status": "rejected", "admin_note": (body.note or "").strip() or None}})
    if not r.matched_count:
        raise HTTPException(404, {"code": "promotion_not_found"})
    return {"ok": True}


@admin_router.post("/grant")
async def admin_grant(body: GrantBody, request: Request, _a=Depends(require_admin)):
    """Comp a promotion (no payment) — the admin-approved free path."""
    db = request.app.state.db
    tier = TIERS_BY_ID.get(body.tier)
    if not tier:
        raise HTTPException(400, {"code": "bad_tier"})
    p = await db.marketplace_profiles.find_one({"business_id": body.business_id})
    if not p:
        raise HTTPException(404, {"code": "business_not_found"})
    pid = f"promo_{uuid.uuid4().hex[:10]}"
    activated = _now()
    expires_iso = _iso(activated + timedelta(days=tier["days"]))
    await db.marketplace_promotions.insert_one({
        "promotion_id": pid, "business_id": body.business_id, "owner_user_id": p.get("owner_user_id"),
        "public_name": p.get("public_name"), "tier": tier["tier"], "name": tier["name"],
        "days": tier["days"], "price_cents": 0, "weight": tier["weight"], "comp": True,
        "status": "active", "paid": True, "created_at": activated,
        "activated_at": activated, "expires_at": expires_iso})
    await _apply_active(db, body.business_id, tier["tier"], tier["weight"], expires_iso)
    return {"ok": True, "promotion_id": pid, "expires_at": expires_iso}


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s) if s else None
    except Exception:
        return None


@router.get("/analytics")
async def analytics(request: Request, user: dict = Depends(current_user)):
    """Views (rail/search impressions + detail opens), orders & revenue for the
    current/most-recent promotion window, plus the uplift vs the equal period
    right before it started."""
    db = request.app.state.db
    p = await _my_business(db, user)
    bid = p["business_id"]
    now = _now()
    promo = await db.marketplace_promotions.find_one(
        {"business_id": bid, "status": "active", "expires_at": {"$gt": _iso(now)}})
    if not promo:
        promo = await db.marketplace_promotions.find_one(
            {"business_id": bid, "status": {"$in": ["active", "expired"]}},
            sort=[("activated_at", -1)])
    if not promo or not promo.get("activated_at"):
        return {"has_data": False}
    start = promo["activated_at"]
    if getattr(start, "tzinfo", None) is None:
        start = start.replace(tzinfo=timezone.utc)
    exp = promo.get("expires_at")
    exp_dt = _parse_iso(exp) if isinstance(exp, str) else exp
    end = min(now, exp_dt) if exp_dt else now
    span = end - start
    prior_start = start - span

    async def _views(s, e):
        agg = {"impressions": 0, "views": 0}
        async for d in db.promotion_daily.find(
                {"business_id": bid,
                 "date": {"$gte": s.date().isoformat(), "$lte": e.date().isoformat()}}):
            agg["impressions"] += int(d.get("impressions", 0))
            agg["views"] += int(d.get("views", 0))
        return agg

    async def _orders(s, e):
        cnt = rev = 0
        async for o in db.marketplace_orders.find(
                {"business_id": bid, "payment_status": "paid", "created_at": {"$gte": s, "$lt": e}}):
            cnt += 1
            rev += int(o.get("total_cents", 0))
        return {"orders": cnt, "revenue_cents": rev}

    win_v = await _views(start, end)
    pri_v = await _views(prior_start, start)
    win_o = await _orders(start, end)
    pri_o = await _orders(prior_start, start)

    def _extra(a, b):
        return max(0, a - b)

    return {
        "has_data": True, "tier": promo.get("name"), "status": promo.get("status"),
        "window": {"start": _iso(start), "end": _iso(end)},
        "impressions": win_v["impressions"], "views": win_v["views"],
        "orders": win_o["orders"], "revenue_cents": win_o["revenue_cents"],
        "extra_impressions": _extra(win_v["impressions"], pri_v["impressions"]),
        "extra_views": _extra(win_v["views"], pri_v["views"]),
        "extra_orders": _extra(win_o["orders"], pri_o["orders"]),
        "extra_revenue_cents": _extra(win_o["revenue_cents"], pri_o["revenue_cents"]),
        "prior": {"impressions": pri_v["impressions"], "views": pri_v["views"],
                  "orders": pri_o["orders"], "revenue_cents": pri_o["revenue_cents"]},
    }


class AutoRenewBody(BaseModel):
    enabled: bool
    payment_method_id: Optional[str] = None


@router.post("/{promotion_id}/auto-renew")
async def set_auto_renew(promotion_id: str, body: AutoRenewBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    promo = await db.marketplace_promotions.find_one({"promotion_id": promotion_id})
    if not promo or promo.get("owner_user_id") != user.get("user_id"):
        raise HTTPException(404, {"code": "promotion_not_found"})
    await db.marketplace_promotions.update_one(
        {"promotion_id": promotion_id},
        {"$set": {"auto_renew": bool(body.enabled),
                  "auto_renew_pm": body.payment_method_id or promo.get("auto_renew_pm")}})
    return {"ok": True, "auto_renew": bool(body.enabled)}


_last_sweep: Dict[str, Any] = {"ts": None}


async def sweep_renewals(db, throttle_seconds: int = 45):
    """Renew promotions that expired with auto_renew on: off-session charge the
    saved card for the same tier; if that isn't possible, free auto-extend
    (opted-in fallback). Throttled so read-path callers stay cheap."""
    now = _now()
    if _last_sweep["ts"] and (now - _last_sweep["ts"]).total_seconds() < throttle_seconds:
        return {"skipped": True}
    _last_sweep["ts"] = now
    due = [p async for p in db.marketplace_promotions.find(
        {"status": "active", "auto_renew": True, "expires_at": {"$lte": _iso(now)}})]
    renewed = 0
    for promo in due:
        tier = TIERS_BY_ID.get(promo.get("tier")) or TIERS_BY_ID["spotlight_7"]
        days = int(tier["days"])
        charged = False
        pm = promo.get("auto_renew_pm")
        if pm:
            try:
                from services.saved_cards_service import (ensure_stripe_customer, list_cards,
                                                          charge_saved_card, owns_payment_method)
                u = await db.users.find_one({"user_id": promo.get("owner_user_id")})
                cust = await ensure_stripe_customer(db, u) if u else None
                if cust and not owns_payment_method(cust, pm):
                    pm = (list_cards(cust) or {}).get("default_id")
                if cust and pm and owns_payment_method(cust, pm):
                    charge_saved_card(amount_cents=tier["price_cents"], cust_id=cust, pm_id=pm,
                                      description=f"RadioLife promotion auto-renew — {tier['name']}",
                                      metadata={"kind": "promotion_renewal", "business_id": promo["business_id"]})
                    charged = True
            except Exception:
                charged = False
        activated = now
        expires_iso = _iso(activated + timedelta(days=days))
        pid = f"promo_{uuid.uuid4().hex[:10]}"
        await db.marketplace_promotions.insert_one({
            "promotion_id": pid, "business_id": promo["business_id"],
            "owner_user_id": promo.get("owner_user_id"), "public_name": promo.get("public_name"),
            "tier": tier["tier"], "name": tier["name"], "days": days,
            "price_cents": tier["price_cents"] if charged else 0, "weight": tier["weight"],
            "status": "active", "paid": charged, "comp": not charged, "renewed": True,
            "auto_renew": True, "auto_renew_pm": pm, "renewed_from": promo["promotion_id"],
            "created_at": activated, "activated_at": activated, "expires_at": expires_iso})
        await _apply_active(db, promo["business_id"], tier["tier"], tier["weight"], expires_iso)
        await db.marketplace_promotions.update_one(
            {"promotion_id": promo["promotion_id"]}, {"$set": {"status": "expired", "auto_renew": False}})
        renewed += 1
    return {"renewed": renewed}



async def ensure_promotions_seed(db):
    """Seed one demo promotion so the Promoted rail + badge show out of the box."""
    biz_id = "biz_sample_ambreens"
    p = await db.marketplace_profiles.find_one({"business_id": biz_id})
    if not p:
        return {"seeded": False}
    expires_iso = _iso(_now() + timedelta(days=3650))
    if not await db.marketplace_promotions.find_one({"promotion_id": "promo_seed_demo"}):
        await db.marketplace_promotions.insert_one({
            "promotion_id": "promo_seed_demo", "business_id": biz_id,
            "owner_user_id": p.get("owner_user_id"), "public_name": p.get("public_name"),
            "tier": "premium_30", "name": "Premium", "days": 30, "price_cents": 0,
            "weight": 3, "comp": True, "status": "active", "paid": True,
            "created_at": _now(), "activated_at": _now(), "expires_at": expires_iso})
    await _apply_active(db, biz_id, "premium_30", 3, expires_iso)
    return {"seeded": True}


__all__ = ["router", "admin_router", "ensure_promotions_seed"]
