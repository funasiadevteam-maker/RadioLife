"""Partner API facade for Marketplace Promotions.

Lets an authenticated partner programmatically buy, on behalf of a listed
business, either:
  * a PROMOTED-RAIL placement (tiered flat fee, Stripe hosted Checkout →
    admin review → active), or
  * a CATEGORY SPOTLIGHT bid + prepaid budget (Stripe hosted Checkout →
    auto-activates on funding, billed per impression by the shop read path).

Reuses the internal engines (single source of truth):
  - routes.marketplace_promotions: PROMO_TIERS / TIERS_BY_ID / _apply_active
  - services.category_bids: bid_standing (auction ranking)

SANDBOX partners get instant comp/funding with NO Stripe (mirrors the ad
top-up sandbox behaviour). Every promotion/bid is tagged with
`purchased_by_partner` for audit and ownership on status polls.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import stripe

from routes.marketplace_promotions import PROMO_TIERS, TIERS_BY_ID, _apply_active
from services.category_bids import bid_standing

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _clean(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return d
    d = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


def _return_urls(success_url: Optional[str], cancel_url: Optional[str]) -> tuple[str, str]:
    base = (os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    s_url = success_url or (f"{base}/payment/success?session_id={{CHECKOUT_SESSION_ID}}" if base else None)
    c_url = cancel_url or (f"{base}/payment/cancel" if base else None)
    if not s_url or not c_url:
        raise ValueError("return_urls_required")
    return s_url, c_url


async def get_profile(db, business_id: str) -> Optional[Dict[str, Any]]:
    return await db.marketplace_profiles.find_one({"business_id": business_id})


def promo_tiers() -> List[Dict[str, Any]]:
    return PROMO_TIERS


async def list_categories(db) -> List[Dict[str, Any]]:
    out = []
    async for c in db.marketplace_categories.find({"active": True}).sort("name", 1):
        out.append({"key": c.get("key"), "name": c.get("name")})
    return out


async def list_promotable_businesses(db, *, q: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if q:
        query["public_name"] = {"$regex": q, "$options": "i"}
    out = []
    now_iso = _iso(_now())
    async for p in db.marketplace_profiles.find(query).limit(min(max(limit, 1), 100)):
        pu = p.get("promoted_until")
        out.append({"business_id": p.get("business_id"),
                    "public_name": p.get("public_name"),
                    "category": p.get("category"),
                    "promoted": bool(pu and str(pu) > now_iso)})
    return out


# ── Promoted-rail placement ──────────────────────────────────────────
async def promotion_checkout(db, *, business_id: str, tier_key: str, partner_id: str,
                             sandbox: bool, environment: str = "LIVE",
                             success_url: Optional[str] = None,
                             cancel_url: Optional[str] = None) -> Dict[str, Any]:
    prof = await get_profile(db, business_id)
    if not prof:
        raise LookupError("business_not_found")
    tier = TIERS_BY_ID.get(tier_key)
    if not tier:
        raise ValueError("bad_tier")
    pid = f"promo_{uuid.uuid4().hex[:10]}"
    if sandbox:
        activated = _now()
        expires_iso = _iso(activated + timedelta(days=tier["days"]))
        await db.marketplace_promotions.insert_one({
            "promotion_id": pid, "business_id": business_id,
            "owner_user_id": prof.get("owner_user_id"), "public_name": prof.get("public_name"),
            "tier": tier["tier"], "name": tier["name"], "days": tier["days"],
            "price_cents": 0, "weight": tier["weight"], "comp": True, "sandbox": True,
            "purchased_by_partner": partner_id, "purchased_by_partner_env": environment,
            "status": "active", "paid": True,
            "created_at": activated, "activated_at": activated, "expires_at": expires_iso})
        await _apply_active(db, business_id, tier["tier"], tier["weight"], expires_iso)
        return {"sandbox": True, "promotion_id": pid, "status": "active",
                "expires_at": expires_iso, "checkout_required": False}
    if not stripe.api_key:
        raise ValueError("stripe_unconfigured")
    s_url, c_url = _return_urls(success_url, cancel_url)
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {
            "currency": "usd", "unit_amount": int(tier["price_cents"]),
            "product_data": {"name": f"RadioLife Promotion — {tier['name']} "
                                     f"({tier['days']}d) · {prof.get('public_name')}"[:120]}},
            "quantity": 1}],
        success_url=s_url, cancel_url=c_url,
        metadata={"kind": "marketplace_promotion", "promotion_id": pid,
                  "business_id": business_id, "tier": tier["tier"],
                  "purchased_by_partner": partner_id})
    await db.marketplace_promotions.insert_one({
        "promotion_id": pid, "business_id": business_id,
        "owner_user_id": prof.get("owner_user_id"), "public_name": prof.get("public_name"),
        "tier": tier["tier"], "name": tier["name"], "days": tier["days"],
        "price_cents": tier["price_cents"], "weight": tier["weight"],
        "purchased_by_partner": partner_id, "purchased_by_partner_env": environment,
        "status": "pending_payment", "paid": False,
        "stripe_session_id": session.id, "expires_at": None, "created_at": _now()})
    return {"checkout_url": session.url, "session_id": session.id, "promotion_id": pid,
            "amount_cents": int(tier["price_cents"]), "currency": "usd",
            "note": "After payment the promotion enters admin review before it goes live."}


async def promotion_status(db, *, promotion_id: str, partner_id: str,
                           environment: str = "LIVE") -> Dict[str, Any]:
    promo = await db.marketplace_promotions.find_one(
        {"promotion_id": promotion_id, "purchased_by_partner": partner_id,
         "purchased_by_partner_env": environment})
    if not promo:
        raise LookupError("promotion_not_found")
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
    return {"status": promo.get("status"), "paid": bool(promo.get("paid")),
            "promotion": _clean(dict(promo))}


# ── Category Spotlight bid + prepaid budget ──────────────────────────
async def spotlight_checkout(db, *, business_id: str, category: str, bid_cents: int,
                             amount_cents: int, partner_id: str, sandbox: bool,
                             environment: str = "LIVE", daily_cap_cents: int = 0,
                             success_url: Optional[str] = None,
                             cancel_url: Optional[str] = None) -> Dict[str, Any]:
    prof = await get_profile(db, business_id)
    if not prof:
        raise LookupError("business_not_found")
    cat = await db.marketplace_categories.find_one({"key": category, "active": True})
    if not cat:
        raise ValueError("bad_category")
    if not (1 <= int(bid_cents) <= 1000):
        raise ValueError("bid_cents_out_of_range")
    if not (500 <= int(amount_cents) <= 1000000):
        raise ValueError("amount_cents_out_of_range")
    ex = await db.category_bids.find_one({"business_id": business_id})
    common = {"category": category, "bid_cents": int(bid_cents),
              "daily_cap_cents": int(daily_cap_cents),
              "owner_user_id": prof.get("owner_user_id"),
              "public_name": prof.get("public_name"),
              "purchased_by_partner": partner_id, "updated_at": _now()}
    if ex:
        bid_id = ex["bid_id"]
        await db.category_bids.update_one({"business_id": business_id}, {"$set": common})
    else:
        bid_id = f"cbid_{uuid.uuid4().hex[:10]}"
        await db.category_bids.insert_one({
            "bid_id": bid_id, "business_id": business_id, "status": "pending_budget",
            "budget_cents": 0, "spent_cents": 0, "impressions": 0,
            "spent_today": 0, "spend_date": None, "created_at": _now(), **common})
    if sandbox:
        b = await db.category_bids.find_one({"bid_id": bid_id})
        new_budget = int((b or {}).get("budget_cents", 0)) + int(amount_cents)
        await db.category_bids.update_one(
            {"bid_id": bid_id},
            {"$set": {"budget_cents": new_budget, "status": "active", "updated_at": _now()}})
        return {"sandbox": True, "bid_id": bid_id, "status": "active",
                "budget_cents": new_budget, "checkout_required": False}
    if not stripe.api_key:
        raise ValueError("stripe_unconfigured")
    s_url, c_url = _return_urls(success_url, cancel_url)
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {
            "currency": "usd", "unit_amount": int(amount_cents),
            "product_data": {"name": f"Category Spotlight budget — {prof.get('public_name')}"[:120]}},
            "quantity": 1}],
        success_url=s_url, cancel_url=c_url,
        metadata={"kind": "category_bid_topup", "business_id": business_id,
                  "bid_id": bid_id, "amount_cents": str(int(amount_cents)),
                  "purchased_by_partner": partner_id})
    await db.category_topups.insert_one({
        "session_id": session.id, "bid_id": bid_id, "business_id": business_id,
        "amount_cents": int(amount_cents), "status": "pending",
        "purchased_by_partner": partner_id, "purchased_by_partner_env": environment,
        "created_at": _now()})
    return {"checkout_url": session.url, "session_id": session.id, "bid_id": bid_id,
            "amount_cents": int(amount_cents), "currency": "usd"}


async def spotlight_status(db, *, session_id: str, partner_id: str,
                           environment: str = "LIVE") -> Dict[str, Any]:
    t = await db.category_topups.find_one(
        {"session_id": session_id, "purchased_by_partner": partner_id,
         "purchased_by_partner_env": environment})
    if not t:
        raise LookupError("topup_not_found")
    if t.get("status") == "credited":
        b = await db.category_bids.find_one({"bid_id": t["bid_id"]})
        return {"status": "credited", "budget_cents": int((b or {}).get("budget_cents", 0))}
    if stripe.api_key:
        try:
            sess = stripe.checkout.Session.retrieve(session_id)
        except Exception:
            sess = None
        if sess and sess.get("payment_status") == "paid":
            b = await db.category_bids.find_one({"bid_id": t["bid_id"]})
            new_budget = int((b or {}).get("budget_cents", 0)) + int(t["amount_cents"])
            await db.category_bids.update_one(
                {"bid_id": t["bid_id"]},
                {"$set": {"budget_cents": new_budget, "status": "active", "updated_at": _now()}})
            await db.category_topups.update_one(
                {"session_id": session_id}, {"$set": {"status": "credited"}})
            return {"status": "credited", "budget_cents": new_budget}
    return {"status": t.get("status")}


async def spotlight_get(db, *, business_id: str) -> Dict[str, Any]:
    b = await db.category_bids.find_one({"business_id": business_id})
    standing = await bid_standing(db, b["category"], business_id) if b and b.get("category") else None
    return {"bid": _clean(dict(b)) if b else None, "standing": standing}


# ── Promotion analytics report ───────────────────────────────────────
async def promotion_report(db, *, promotion_id: str, partner_id: str,
                           environment: str = "LIVE") -> Dict[str, Any]:
    """Impressions/views (promotion_daily) + orders/revenue (marketplace_orders)
    over the promotion's active window, plus total spend (placement fee +
    any Category Spotlight spend for the same business)."""
    promo = await db.marketplace_promotions.find_one(
        {"promotion_id": promotion_id, "purchased_by_partner": partner_id,
         "purchased_by_partner_env": environment})
    if not promo:
        raise LookupError("promotion_not_found")
    bid = promo["business_id"]
    start = promo.get("activated_at") or promo.get("created_at") or _now()
    if getattr(start, "tzinfo", None) is None and hasattr(start, "replace"):
        start = start.replace(tzinfo=timezone.utc)
    exp = promo.get("expires_at")
    if isinstance(exp, str):
        try:
            exp = datetime.fromisoformat(exp)
        except Exception:
            exp = None
    now = _now()
    end = min(now, exp) if exp else now
    imp = views = 0
    async for d in db.promotion_daily.find(
            {"business_id": bid,
             "date": {"$gte": start.date().isoformat(), "$lte": end.date().isoformat()}}):
        imp += int(d.get("impressions", 0))
        views += int(d.get("views", 0))
    orders = revenue = 0
    async for o in db.marketplace_orders.find(
            {"business_id": bid, "payment_status": "paid",
             "created_at": {"$gte": start, "$lt": end}}):
        orders += 1
        revenue += int(o.get("total_cents", 0))
    spotlight = await db.category_bids.find_one({"business_id": bid})
    spotlight_spend = int((spotlight or {}).get("spent_cents", 0))
    spotlight_impr = int((spotlight or {}).get("impressions", 0))
    placement_spend = int(promo.get("price_cents") or 0)
    return {
        "promotion_id": promotion_id, "business_id": bid,
        "public_name": promo.get("public_name"), "tier": promo.get("tier"),
        "status": promo.get("status"),
        "window": {"start": start.isoformat() if hasattr(start, "isoformat") else start,
                   "end": end.isoformat() if hasattr(end, "isoformat") else end},
        "impressions": imp, "views": views,
        "orders": orders, "revenue_cents": revenue,
        "placement_spend_cents": placement_spend,
        "spotlight_spend_cents": spotlight_spend,
        "spotlight_impressions": spotlight_impr,
        "total_spend_cents": placement_spend + spotlight_spend,
    }


__all__ = [
    "promo_tiers", "list_categories", "list_promotable_businesses",
    "promotion_checkout", "promotion_status", "promotion_report",
    "spotlight_checkout", "spotlight_status", "spotlight_get",
    "list_partner_history", "partner_analytics_summary",
]


def _isostr(v):
    return v.isoformat() if hasattr(v, "isoformat") else (v or None)


# ── Console history (everything a partner bought) ────────────────────
async def list_partner_history(db, *, partner_id: str, adv_ids: list,
                               adv_env: dict) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    async for p in db.marketplace_promotions.find(
            {"purchased_by_partner": partner_id}).sort("created_at", -1).limit(100):
        items.append({"kind": "promotion", "id": p.get("promotion_id"),
                      "name": p.get("public_name") or p.get("business_id"),
                      "detail": f"{p.get('name')} · {p.get('days')}d",
                      "status": p.get("status"), "amount_cents": int(p.get("price_cents") or 0),
                      "paid": bool(p.get("paid")), "environment": p.get("purchased_by_partner_env"),
                      "created_at": _isostr(p.get("created_at"))})
    async for b in db.category_bids.find(
            {"purchased_by_partner": partner_id}).sort("updated_at", -1).limit(100):
        items.append({"kind": "spotlight", "id": b.get("bid_id"),
                      "name": b.get("public_name") or b.get("business_id"),
                      "detail": f"{b.get('category')} · bid {b.get('bid_cents')}¢",
                      "status": b.get("status"), "amount_cents": int(b.get("budget_cents") or 0),
                      "paid": b.get("status") == "active", "environment": b.get("purchased_by_partner_env"),
                      "created_at": _isostr(b.get("created_at"))})
    if adv_ids:
        async for t in db.trivia_sponsorships.find(
                {"advertiser_business_id": {"$in": adv_ids}}).sort("created_at", -1).limit(100):
            items.append({"kind": "trivia", "id": t.get("id"),
                          "name": t.get("display_name") or "Trivia sponsorship", "detail": "prize pool",
                          "status": t.get("status"), "amount_cents": int(t.get("cost_cents") or 0),
                          "paid": bool(t.get("paid_at")),
                          "environment": adv_env.get(t.get("advertiser_business_id")),
                          "created_at": _isostr(t.get("created_at"))})
        async for r in db.rj_sponsored_reads.find(
                {"advertiser_business_id": {"$in": adv_ids}}).sort("created_at", -1).limit(100):
            items.append({"kind": "rj_read", "id": r.get("id"),
                          "name": r.get("product_name") or r.get("persona_name") or "AI-RJ read",
                          "detail": f"{r.get('plays_target')} plays",
                          "status": r.get("status"), "amount_cents": int(r.get("total_cost_cents") or 0),
                          "paid": bool(r.get("paid_at")),
                          "environment": adv_env.get(r.get("advertiser_business_id")),
                          "created_at": _isostr(r.get("created_at"))})
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items


# ── Cross-promotion spend/analytics rollup ───────────────────────────
async def partner_analytics_summary(db, *, partner_id: str) -> Dict[str, Any]:
    promos = [p async for p in db.marketplace_promotions.find({"purchased_by_partner": partner_id})]
    biz = {p["business_id"] for p in promos if p.get("business_id")}
    spotlight_spend = 0
    async for b in db.category_bids.find({"purchased_by_partner": partner_id}):
        if b.get("business_id"):
            biz.add(b["business_id"])
        spotlight_spend += int(b.get("spent_cents") or 0)
    biz_ids = list(biz)
    impressions = views = orders = revenue = 0
    if biz_ids:
        async for d in db.promotion_daily.find({"business_id": {"$in": biz_ids}}):
            impressions += int(d.get("impressions", 0))
            views += int(d.get("views", 0))
        async for o in db.marketplace_orders.find(
                {"business_id": {"$in": biz_ids}, "payment_status": "paid"}):
            orders += 1
            revenue += int(o.get("total_cents", 0))
    placement_spend = sum(int(p.get("price_cents") or 0) for p in promos if p.get("paid"))
    return {"businesses": len(biz_ids), "promotions": len(promos),
            "active_promotions": sum(1 for p in promos if p.get("status") == "active"),
            "pending_promotions": sum(1 for p in promos if p.get("status") == "pending_review"),
            "impressions": impressions, "views": views, "orders": orders,
            "revenue_cents": revenue, "placement_spend_cents": placement_spend,
            "spotlight_spend_cents": spotlight_spend,
            "total_spend_cents": placement_spend + spotlight_spend}
