"""Marketplace Memberships (Phase E) — a venue sells a recurring membership
that bundles benefit RULES (e.g. "1 free coffee daily", a monthly meal plan,
or a choose-your-item perk). Billed as a recurring Stripe subscription
(same subscription-mode pattern as merchant subscriptions). Members CLAIM
included benefits; each benefit is capped per calendar period (day/week/month).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services.marketplace import now, new_id
from services.gift_notify import send_gift_emails
from services.membership_entitlements import (
    EntitlementModel, normalize_entitlements, period_key, day_time_allows,
    entitlement_remaining, record_redemption, resolve_eligible_items,
    _FREQ_TO_LEGACY_PERIOD)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace/memberships",
                   tags=["marketplace-memberships"])
consumer_router = APIRouter(prefix="/api/shop", tags=["marketplace-memberships-consumer"])


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    for k in ("created_at", "updated_at", "claimed_at", "current_period_end"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


class PlanBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=280)
    price_cents: int = Field(..., ge=100, le=1_000_000)
    interval: str = Field("month")
    entitlements: List[EntitlementModel] = Field(default_factory=list)
    active: bool = True


# ───────────── Merchant CRUD ─────────────
@router.get("")
async def list_plans(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [_clean(x) async for x in db.membership_plans.find(
        {"business_id": p["business_id"]}).sort("created_at", 1)]
    for it in items:
        it["member_count"] = await db.memberships.count_documents(
            {"plan_id": it["plan_id"], "status": "active"})
    return {"items": items}


@router.post("/items")
async def create_plan(body: PlanBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    if body.interval not in ("month", "week"):
        raise HTTPException(400, {"code": "bad_interval"})
    pid = new_id("mplan")
    doc = {"plan_id": pid, "business_id": p["business_id"], "sponsor_name": p.get("public_name"),
           "name": body.name.strip(), "description": (body.description or "").strip() or None,
           "price_cents": body.price_cents, "interval": body.interval,
           "entitlements": normalize_entitlements(body.entitlements),
           "schema_version": 2,
           "active": body.active, "created_at": now(), "updated_at": now()}
    await db.membership_plans.insert_one(dict(doc))
    return {"ok": True, "plan": _clean(doc)}


@router.patch("/items/{plan_id}")
async def update_plan(plan_id: str, body: PlanBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    if body.interval not in ("month", "week"):
        raise HTTPException(400, {"code": "bad_interval"})
    res = await db.membership_plans.update_one(
        {"plan_id": plan_id, "business_id": p["business_id"]},
        {"$set": {"name": body.name.strip(), "description": (body.description or "").strip() or None,
                  "price_cents": body.price_cents, "interval": body.interval,
                  "entitlements": normalize_entitlements(body.entitlements),
                  "schema_version": 2,
                  "active": body.active, "sponsor_name": p.get("public_name"),
                  "updated_at": now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "plan_not_found"})
    x = await db.membership_plans.find_one({"plan_id": plan_id})
    return {"ok": True, "plan": _clean(x)}


@router.delete("/items/{plan_id}")
async def delete_plan(plan_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.membership_plans.delete_one(
        {"plan_id": plan_id, "business_id": p["business_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, {"code": "plan_not_found"})
    return {"ok": True}


# ───────────── Consumer ─────────────
async def _benefit_status(db, membership: Dict[str, Any], plan: Dict[str, Any],
                          with_items: bool = False) -> List[Dict[str, Any]]:
    """Per-entitlement live status. Includes backward-compatible aliases
    (`qty`/`period`/`options`) so pre-v2 clients keep rendering. When
    `with_items`, also resolves the concrete eligible items (for the wallet)."""
    out = []
    for e in plan.get("entitlements", []):
        if not e.get("active", True):
            continue
        rem = await entitlement_remaining(db, membership, e)
        row = {
            **e,
            "used": rem["used"], "remaining": rem["remaining"],
            "period_key": rem["period_key"],
            "qty": int(e.get("quantity", 1)),
            "period": _FREQ_TO_LEGACY_PERIOD.get(e.get("reset_frequency", "monthly"), "month"),
            "options": e.get("choice_labels", []),
            "available_now": day_time_allows(e.get("day_time")),
        }
        if with_items:
            row["eligible_items"] = await resolve_eligible_items(
                db, membership["business_id"], e)
        out.append(row)
    return out


@consumer_router.get("/businesses/{business_id}/memberships")
async def business_memberships(business_id: str, request: Request,
                               user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    biz = await db.marketplace_profiles.find_one(
        {"business_id": business_id, "status": "approved", "subscription_active": True},
        {"public_name": 1, "cover_urls": 1})
    if not biz:
        raise HTTPException(404, {"code": "business_not_found"})
    plans = [_clean(x) async for x in db.membership_plans.find(
        {"business_id": business_id, "active": True}).sort("price_cents", 1)]
    mine = None
    if user:
        uid = user.get("user_id")
        email = (user.get("email") or "").lower().strip()
        ors: List[Dict[str, Any]] = [{"user_id": uid}]
        if email:
            ors.append({"gifted_to_email": email})
        m = await db.memberships.find_one(
            {"business_id": business_id, "status": "active", "$or": ors})
        if m:
            plan = await db.membership_plans.find_one({"plan_id": m["plan_id"]})
            mine = _clean(dict(m))
            mine["benefits"] = await _benefit_status(db, m, plan or {}) if plan else []
            mine["plan_name"] = (plan or {}).get("name")
            mine["received_gift"] = bool(m.get("is_gift") and m.get("buyer_user_id") != uid)
    return {"business_id": business_id, "public_name": biz.get("public_name"),
            "cover_url": (biz.get("cover_urls") or [None])[0], "items": plans, "mine": mine}


class SubscribeBody(BaseModel):
    plan_id: str
    origin_url: Optional[str] = None
    gift_to_email: Optional[str] = None
    message: Optional[str] = Field(None, max_length=280)


@consumer_router.post("/memberships/subscribe")
async def subscribe(body: SubscribeBody, request: Request,
                    background_tasks: BackgroundTasks,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    buyer_id = user.get("user_id")
    plan = await db.membership_plans.find_one({"plan_id": body.plan_id, "active": True})
    if not plan:
        raise HTTPException(404, {"code": "plan_not_found"})

    gto = (body.gift_to_email or "").lower().strip() or None
    is_gift = bool(gto)
    owner = buyer_id
    if is_gift:
        rec = await db.users.find_one({"email": gto}, {"user_id": 1})
        owner = rec["user_id"] if rec else None  # unregistered → surfaces by email

    # "already member" applies to the eventual owner (recipient when gifting).
    if owner:
        existing = await db.memberships.find_one(
            {"plan_id": body.plan_id, "user_id": owner, "status": "active"})
        if existing:
            raise HTTPException(400, {"code": "already_member"})
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price_data": {
            "currency": "usd",
            "product_data": {"name": f"{plan.get('sponsor_name')} — {plan['name']}"},
            "unit_amount": int(plan["price_cents"]),
            "recurring": {"interval": plan.get("interval", "month")}},
            "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "marketplace_membership", "plan_id": body.plan_id,
                  "business_id": plan["business_id"], "user_id": owner or "",
                  "buyer_id": buyer_id, "gift_to_email": gto or ""})
    mid = new_id("mbr")
    await db.memberships.insert_one({
        "membership_id": mid, "plan_id": body.plan_id, "business_id": plan["business_id"],
        "user_id": owner, "buyer_user_id": buyer_id,
        "is_gift": is_gift, "gifted_to_email": gto,
        "gift_message": (body.message or None) if is_gift else None,
        "sponsor_name": plan.get("sponsor_name"), "plan_name": plan.get("name"),
        "status": "pending", "session_id": session.id,
        "created_at": now(), "updated_at": now()})
    return {"ok": True, "checkout_url": session.url, "session_id": session.id, "membership_id": mid}


async def _schedule_membership_gift_email(db, bg: Optional[BackgroundTasks],
                                          m: Dict[str, Any]) -> None:
    if not (bg and m.get("is_gift") and m.get("gifted_to_email")):
        return
    buyer = await db.users.find_one({"user_id": m.get("buyer_user_id")},
                                    {"email": 1, "display_name": 1, "name": 1}) or {}
    bg.add_task(send_gift_emails, kind="membership",
                item_name=m.get("plan_name") or "Membership",
                sponsor_name=m.get("sponsor_name"),
                buyer_email=buyer.get("email"),
                buyer_name=buyer.get("display_name") or buyer.get("name") or "A friend",
                recipient_email=m.get("gifted_to_email"),
                message=m.get("gift_message"))


@consumer_router.get("/memberships/subscribe/{session_id}/status")
async def subscribe_status(session_id: str, request: Request,
                           background_tasks: BackgroundTasks,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    m = await db.memberships.find_one(
        {"session_id": session_id,
         "$or": [{"user_id": uid}, {"buyer_user_id": uid}]})
    if not m:
        raise HTTPException(404, {"code": "membership_not_found"})
    if m.get("status") == "active":
        return {"status": "active", "active": True, "membership_id": m["membership_id"]}
    if not stripe.api_key:
        return {"status": m.get("status", "pending"), "active": False}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": m.get("status", "pending"), "active": False}
    if sess.get("payment_status") == "paid" or sess.get("status") == "complete":
        await db.memberships.update_one(
            {"membership_id": m["membership_id"]},
            {"$set": {"status": "active", "stripe_subscription_id": sess.get("subscription"),
                      "updated_at": now()}})
        await _schedule_membership_gift_email(db, background_tasks, m)
        return {"status": "active", "active": True, "membership_id": m["membership_id"]}
    return {"status": "pending", "active": False}


@consumer_router.get("/memberships/mine")
async def my_memberships(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    email = (user.get("email") or "").lower().strip()
    ors: List[Dict[str, Any]] = [{"user_id": uid}]
    if email:
        ors.append({"gifted_to_email": email})
    out = []
    async for m in db.memberships.find(
            {"status": "active", "$or": ors}).sort("created_at", -1):
        # Recipient logged in after being gifted → claim ownership so they can use benefits.
        if not m.get("user_id") and email and m.get("gifted_to_email") == email:
            await db.memberships.update_one(
                {"membership_id": m["membership_id"]}, {"$set": {"user_id": uid}})
            m["user_id"] = uid
        plan = await db.membership_plans.find_one({"plan_id": m["plan_id"]})
        row = _clean(dict(m))
        row["plan_name"] = (plan or {}).get("name")
        row["sponsor_name"] = (plan or {}).get("sponsor_name")
        row["price_cents"] = (plan or {}).get("price_cents")
        row["interval"] = (plan or {}).get("interval")
        row["benefits"] = await _benefit_status(db, m, plan or {}, with_items=True) if plan else []
        row["received_gift"] = bool(m.get("is_gift") and m.get("buyer_user_id") != uid)
        row["gift_message"] = m.get("gift_message")
        row["business_id"] = m.get("business_id")
        out.append(row)
    return {"items": out}


@consumer_router.get("/businesses/{business_id}/my-entitlements")
async def my_business_entitlements(business_id: str, request: Request,
                                   user: dict = Depends(current_user)):
    """The caller's usable membership entitlements AT this business — powers the
    checkout 'apply your membership' picker."""
    db = request.app.state.db
    uid = user.get("user_id")
    email = (user.get("email") or "").lower().strip()
    ors: List[Dict[str, Any]] = [{"user_id": uid}]
    if email:
        ors.append({"gifted_to_email": email})
    out = []
    async for m in db.memberships.find(
            {"business_id": business_id, "status": "active", "$or": ors}):
        plan = await db.membership_plans.find_one({"plan_id": m["plan_id"]})
        if not plan:
            continue
        for e in await _benefit_status(db, m, plan, with_items=True):
            out.append({
                "membership_id": m["membership_id"], "plan_name": plan.get("name"),
                "entitlement_id": e.get("entitlement_id"), "label": e.get("label"),
                "target_type": e.get("target_type"), "category": e.get("category"),
                "target_ids": e.get("target_ids", []),
                "remaining": e.get("remaining", 0), "available_now": e.get("available_now", True),
                "max_upcharge_cents": e.get("max_upcharge_cents"),
                "included_option_ids": e.get("included_option_ids", []),
                "stackable": e.get("stackable", False),
                "eligible_items": e.get("eligible_items", []),
            })
    return {"business_id": business_id, "items": out}

    return {"items": out}


class ClaimBody(BaseModel):
    entitlement_id: Optional[str] = None
    benefit_id: Optional[str] = None  # legacy alias
    option: Optional[str] = None


@consumer_router.post("/memberships/{membership_id}/claim")
async def claim_benefit(membership_id: str, body: ClaimBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await db.memberships.find_one(
        {"membership_id": membership_id, "user_id": user.get("user_id"), "status": "active"})
    if not m:
        raise HTTPException(404, {"code": "membership_not_found"})
    plan = await db.membership_plans.find_one({"plan_id": m["plan_id"]})
    ent_id = body.entitlement_id or body.benefit_id
    ent = next((e for e in (plan or {}).get("entitlements", [])
                if e.get("entitlement_id") == ent_id), None)
    if not ent:
        raise HTTPException(404, {"code": "benefit_not_found"})
    if not ent.get("active", True):
        raise HTTPException(400, {"code": "benefit_inactive"})
    choices = ent.get("choice_labels", [])
    if choices and body.option not in choices:
        raise HTTPException(400, {"code": "option_required", "options": choices})
    if not day_time_allows(ent.get("day_time")):
        raise HTTPException(400, {"code": "outside_time_window",
                                  "day_time": ent.get("day_time")})
    rem = await entitlement_remaining(db, m, ent)
    if rem["remaining"] <= 0:
        raise HTTPException(400, {"code": "limit_reached",
                                  "reset_frequency": ent.get("reset_frequency"),
                                  "quantity": int(ent.get("quantity", 1))})
    await record_redemption(
        db, m, ent, order_id=None, qty=1,
        selected_options=([{"label": body.option}] if body.option else []),
        source="claim")
    return {"ok": True, "entitlement_id": ent_id, "benefit_id": ent_id,
            "label": ent.get("label"), "option": body.option,
            "remaining": max(0, rem["remaining"] - 1)}


@consumer_router.post("/memberships/{membership_id}/cancel")
async def cancel_membership(membership_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    m = await db.memberships.find_one(
        {"membership_id": membership_id, "user_id": user.get("user_id")})
    if not m:
        raise HTTPException(404, {"code": "membership_not_found"})
    if m.get("stripe_subscription_id") and stripe.api_key:
        try:
            stripe.Subscription.delete(m["stripe_subscription_id"])
        except Exception:
            pass
    await db.memberships.update_one(
        {"membership_id": membership_id},
        {"$set": {"status": "canceled", "updated_at": now()}})
    return {"ok": True}


__all__ = ["router", "consumer_router"]
