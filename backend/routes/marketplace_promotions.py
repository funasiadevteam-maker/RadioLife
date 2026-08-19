"""Promoted Marketplace (Phase F) — merchants pay to boost their shop higher in
Shop search + a "Promoted near you" rail on the Shop home. Tiered flat fee via
Stripe hosted Checkout, ADMIN-approved before it goes live. Admins can also comp
(grant) a promotion for free. The active promotion writes `promoted_until` +
`promotion_weight` onto the marketplace_profile; shop reads boost + badge it."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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
    # Flag + name promotions purchased programmatically via the Partner API.
    pids = {x.get("purchased_by_partner") for x in out if x.get("purchased_by_partner")}
    names: Dict[str, Any] = {}
    if pids:
        async for pa in db.partner_accounts.find({"partner_id": {"$in": list(pids)}}, {"partner_id": 1, "name": 1}):
            names[pa["partner_id"]] = pa.get("name")
    for x in out:
        pp = x.get("purchased_by_partner")
        x["via_partner"] = bool(pp)
        x["partner_name"] = names.get(pp) if pp else None
    return {"items": out}


async def _approve_one(db, promotion_id: str) -> Dict[str, Any]:
    """Approve a single in-review promotion → active. Returns a result dict
    (never raises) so it can be reused by both single + bulk endpoints."""
    promo = await db.marketplace_promotions.find_one({"promotion_id": promotion_id})
    if not promo:
        return {"promotion_id": promotion_id, "ok": False, "code": "promotion_not_found"}
    if promo.get("status") != "pending_review":
        return {"promotion_id": promotion_id, "ok": False,
                "code": "not_reviewable", "status": promo.get("status")}
    days = int(promo.get("days") or 7)
    activated = _now()
    expires_iso = _iso(activated + timedelta(days=days))
    await db.marketplace_promotions.update_one(
        {"promotion_id": promotion_id},
        {"$set": {"status": "active", "activated_at": activated, "expires_at": expires_iso}})
    await _apply_active(db, promo["business_id"], promo["tier"], int(promo.get("weight") or 1), expires_iso)
    return {"promotion_id": promotion_id, "ok": True}


@admin_router.post("/{promotion_id}/approve")
async def admin_approve(promotion_id: str, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    r = await _approve_one(db, promotion_id)
    if not r["ok"]:
        code = r["code"]
        raise HTTPException(404 if code == "promotion_not_found" else 400,
                            {"code": code, **({"status": r["status"]} if r.get("status") else {})})
    saved = await db.marketplace_promotions.find_one({"promotion_id": promotion_id})
    return {"ok": True, "promotion": _clean(dict(saved))}


class BulkApproveBody(BaseModel):
    promotion_ids: List[str]


@admin_router.post("/bulk-approve")
async def admin_bulk_approve(body: BulkApproveBody, request: Request, _a=Depends(require_admin)):
    """Approve many in-review promotions in one call (e.g. clear the partner
    queue). Returns which succeeded and which were skipped + why."""
    db = request.app.state.db
    results = [await _approve_one(db, pid) for pid in (body.promotion_ids or [])[:100]]
    approved = [r["promotion_id"] for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    return {"approved": approved, "approved_count": len(approved),
            "failed": failed, "failed_count": len(failed)}


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

    # Day-by-day trend across the promotion window (capped to 60 points).
    day = start.date()
    days = []
    while day <= end.date() and len(days) < 60:
        days.append(day.isoformat())
        day += timedelta(days=1)
    tmap = {d: {"date": d, "views": 0, "impressions": 0, "orders": 0,
                "revenue_cents": 0, "spend_cents": 0, "capped": False} for d in days}
    if days:
        async for doc in db.promotion_daily.find(
                {"business_id": bid, "date": {"$gte": days[0], "$lte": days[-1]}}):
            t = tmap.get(doc.get("date"))
            if t:
                t["views"] += int(doc.get("views", 0))
                t["impressions"] += int(doc.get("impressions", 0))
        async for o in db.marketplace_orders.find(
                {"business_id": bid, "payment_status": "paid", "created_at": {"$gte": start, "$lt": end}}):
            ca = o.get("created_at")
            dk = ca.date().isoformat() if hasattr(ca, "date") else str(ca)[:10]
            t = tmap.get(dk)
            if t:
                t["orders"] += 1
                t["revenue_cents"] += int(o.get("total_cents", 0))
        # Category Spotlight per-day spend + "cap hit" marker (missed demand).
        async for d in db.category_bid_daily.find(
                {"business_id": bid, "date": {"$gte": days[0], "$lte": days[-1]}}):
            t = tmap.get(d.get("date"))
            if t:
                t["spend_cents"] += int(d.get("spent_cents", 0))
                if d.get("capped"):
                    t["capped"] = True
    trend = [tmap[d] for d in days]

    return {
        "has_data": True, "tier": promo.get("name"), "status": promo.get("status"),
        "trend": trend,
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
        u = None
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
        if charged:
            await _email_renewal_receipt(u, promo.get("public_name"), tier, expires_iso)
        renewed += 1
    return {"renewed": renewed}


async def _email_renewal_receipt(u, shop_name, tier, expires_iso):
    """Best-effort receipt email after an auto-renew charge (never blocks/raises)."""
    try:
        from services.mailgun_client import send_email, is_live
        if not (is_live() and u and u.get("email")):
            return
        amount = f"${tier['price_cents'] / 100:.2f}"
        until = str(expires_iso)[:10]
        html = (
            f"<div style='font-family:sans-serif;max-width:520px'>"
            f"<h2 style='color:#ea580c;margin:0 0 8px'>Promotion renewed 🚀</h2>"
            f"<p>Hi {u.get('name') or 'there'},</p>"
            f"<p>Your <b>{tier['name']}</b> promotion for <b>{shop_name}</b> auto-renewed.</p>"
            f"<table style='border-collapse:collapse;margin:12px 0'>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Plan</td><td style='padding:4px 0'><b>{tier['name']} · {tier['days']} days</b></td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Amount</td><td style='padding:4px 0'><b>{amount}</b></td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Active until</td><td style='padding:4px 0'><b>{until}</b></td></tr>"
            f"</table>"
            f"<p style='color:#64748b;font-size:13px'>You can turn off auto-renew any time from Promote my Shop.</p>"
            f"</div>")
        await asyncio.to_thread(send_email, u["email"],
                                f"Your RadioLife promotion renewed — {tier['name']}",
                                html, tags=["promotion_renewal"])
    except Exception:
        pass



async def _window_numbers(db, business_id, start, end):
    """Views + orders + spotlight spend for a [start, end) window."""
    views = 0
    async for d in db.promotion_daily.find(
            {"business_id": business_id,
             "date": {"$gte": start.date().isoformat(), "$lt": end.date().isoformat()}}):
        views += int(d.get("views", 0))
    orders = rev = 0
    async for o in db.marketplace_orders.find(
            {"business_id": business_id, "payment_status": "paid", "created_at": {"$gte": start, "$lt": end}}):
        orders += 1
        rev += int(o.get("total_cents", 0))
    spend = 0
    async for c in db.category_bid_daily.find(
            {"business_id": business_id,
             "date": {"$gte": start.date().isoformat(), "$lt": end.date().isoformat()}}):
        spend += int(c.get("spent_cents", 0))
    return {"views": views, "orders": orders, "revenue_cents": rev, "spend_cents": spend}


async def _weekly_digest_data(db, business_id):
    now = _now()
    week_start = (now - timedelta(days=7))
    prior_start = week_start - timedelta(days=7)
    cur = await _window_numbers(db, business_id, week_start, now)
    prev = await _window_numbers(db, business_id, prior_start, week_start)

    def _extra(a, b):
        return max(0, a - b)
    return {"week_of": week_start.date().isoformat(),
            "views": cur["views"], "orders": cur["orders"],
            "revenue_cents": cur["revenue_cents"], "spend_cents": cur["spend_cents"],
            "extra_views": _extra(cur["views"], prev["views"]),
            "extra_orders": _extra(cur["orders"], prev["orders"])}


@router.get("/weekly-digest")
async def weekly_digest_preview(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    return {"public_name": p.get("public_name"), **await _weekly_digest_data(db, p["business_id"])}


async def _send_weekly_digest(db, business_id, owner_user_id, shop_name):
    try:
        from services.mailgun_client import send_email, is_live
        if not is_live():
            return False
        u = await db.users.find_one({"user_id": owner_user_id})
        if not u or not u.get("email"):
            return False
        d = await _weekly_digest_data(db, business_id)
        rev = f"${d['revenue_cents'] / 100:.2f}"
        spend = f"${d['spend_cents'] / 100:.2f}"
        html = (
            f"<div style='font-family:sans-serif;max-width:520px'>"
            f"<h2 style='color:#ea580c;margin:0 0 8px'>Your week on RadioLife 📈</h2>"
            f"<p>Hi {u.get('name') or 'there'}, here's how <b>{shop_name}</b> did over the last 7 days:</p>"
            f"<table style='border-collapse:collapse;margin:12px 0'>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Views</td><td style='padding:4px 0'><b>{d['views']}</b> (+{d['extra_views']} vs prior week)</td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Orders</td><td style='padding:4px 0'><b>{d['orders']}</b> (+{d['extra_orders']})</td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Revenue</td><td style='padding:4px 0'><b>{rev}</b></td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>Spotlight spend</td><td style='padding:4px 0'><b>{spend}</b></td></tr>"
            f"</table>"
            f"<p style='color:#64748b;font-size:13px'>Keep your promotion running from Promote my Shop.</p>"
            f"</div>")
        await asyncio.to_thread(send_email, u["email"], f"Your RadioLife week — {shop_name}",
                                html, tags=["weekly_digest"])
        return True
    except Exception:
        return False


_last_digest_check: Dict[str, Any] = {"ts": None}


async def maybe_send_weekly_digests(db, throttle_seconds: int = 3600):
    """On Mondays, email each promoted merchant last week's summary (once/week)."""
    now = _now()
    if now.weekday() != 0:  # Monday only
        return {"skipped": "not_monday"}
    if _last_digest_check["ts"] and (now - _last_digest_check["ts"]).total_seconds() < throttle_seconds:
        return {"skipped": True}
    _last_digest_check["ts"] = now
    iso = now.isocalendar()
    week_key = f"{iso[0]}-W{iso[1]:02d}"
    seen = set()
    sent = 0
    since = now - timedelta(days=14)
    async for promo in db.marketplace_promotions.find(
            {"activated_at": {"$gte": since}}).sort("activated_at", -1):
        biz = promo.get("business_id")
        if not biz or biz in seen:
            continue
        seen.add(biz)
        if await db.promotion_digests.find_one({"business_id": biz, "week": week_key}):
            continue
        ok = await _send_weekly_digest(db, biz, promo.get("owner_user_id"), promo.get("public_name"))
        await db.promotion_digests.insert_one(
            {"business_id": biz, "week": week_key, "sent": ok, "created_at": now})
        if ok:
            sent += 1
    return {"sent": sent, "week": week_key}


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
