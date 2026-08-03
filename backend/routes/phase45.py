"""Phase 4.5 — Stripe Connect (Express) + AI sponsor-read endpoint + SSP admin.

Mounted at /api/advertiser/stripe and /api/advertiser/creative/ai
plus /api/admin/ssp/* (admin partner mgmt).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Query

from core.config import STRIPE_API_KEY

logger = logging.getLogger("bigfm.phase45")
stripe.api_key = STRIPE_API_KEY

PLATFORM_FEE_PCT = float(os.environ.get("PLATFORM_FEE_PCT", "0.10"))   # 10%

phase45_router = APIRouter(tags=["phase4.5"])
advertiser_p45_router = APIRouter(prefix="/api/advertiser", tags=["advertiser-p45"])
admin_p45_router = APIRouter(prefix="/api/admin", tags=["admin-p45"])


async def _require_user(request: Request):
    from auth import current_user
    return await current_user(request)


async def _require_advertiser(request: Request):
    u = await _require_user(request)
    if not u.get("is_advertiser") and u.get("role") != "admin":
        raise HTTPException(403, "advertiser access required")
    return u


async def _require_admin(request: Request):
    from auth import current_user
    u = await current_user(request)
    if u.get("role") != "admin": raise HTTPException(403, "admin only")
    return u


def _ser(d):
    if not d: return d
    d = dict(d)
    if "_id" in d:
        d["id"] = str(d["_id"]); d.pop("_id", None)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"): d[k] = v.isoformat()
    return d


# ============================================================
# STRIPE CONNECT (Express)
# ============================================================
@advertiser_p45_router.post("/stripe/connect_account")
async def stripe_connect_account(request: Request, u: dict = Depends(_require_advertiser),
                                  payload: Optional[dict] = None):
    """Create or fetch a Stripe Express account for the advertiser's business
    and return an Account Link URL for onboarding."""
    db = request.app.state.db
    payload = payload or {}
    business_id = payload.get("business_id")
    if not business_id:
        raise HTTPException(400, "business_id required")
    biz = await db.businesses.find_one({"business_id": business_id})
    if not biz: raise HTTPException(404, "business not found")
    # Ownership check (skip if admin)
    if u.get("role") != "admin":
        adv = await db.advertisers.find_one({"user_id": u["user_id"]})
        if not adv or biz.get("advertiser_id") != adv.get("advertiser_id"):
            raise HTTPException(403, "not your business")

    # Idempotent: reuse existing acct if present
    acct_id = biz.get("stripe_connect_account_id")
    if not acct_id:
        try:
            country = "AE" if (biz.get("market") or "dubai") == "dubai" else "US"
            acct = stripe.Account.create(
                type="express",
                country=country,
                email=biz.get("contact_email") or u.get("email"),
                business_profile={
                    "name": biz.get("name"),
                    "url": biz.get("website") or "https://bigfm.dubai",
                    "mcc": "5812" if biz.get("category") == "restaurant" else "5999",
                },
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )
            acct_id = acct.id
        except Exception as e:
            logger.warning(f"stripe acct create failed: {e}")
            raise HTTPException(502, f"Stripe Account.create failed: {e}")

    # Generate onboarding link
    base = str(request.base_url).rstrip("/")
    try:
        link = stripe.AccountLink.create(
            account=acct_id, type="account_onboarding",
            refresh_url=f"{base}/advertiser/payouts?refresh=1",
            return_url=f"{base}/advertiser/payouts?return=1",
        )
    except Exception as e:
        raise HTTPException(502, f"Stripe AccountLink failed: {e}")

    await db.businesses.update_one(
        {"business_id": business_id},
        {"$set": {"stripe_connect_account_id": acct_id,
                   "stripe_account_status": "onboarding",
                   "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True, "stripe_account_id": acct_id, "onboarding_url": link.url}


@advertiser_p45_router.get("/stripe/account_status")
async def stripe_account_status(request: Request, u: dict = Depends(_require_advertiser),
                                  business_id: str = Query(...)):
    db = request.app.state.db
    biz = await db.businesses.find_one({"business_id": business_id})
    if not biz: raise HTTPException(404, "business not found")
    acct_id = biz.get("stripe_connect_account_id")
    if not acct_id:
        return {"connected": False, "stripe_account_id": None}
    try:
        acct = stripe.Account.retrieve(acct_id)
        update = {
            "stripe_charges_enabled": bool(acct.charges_enabled),
            "stripe_payouts_enabled": bool(acct.payouts_enabled),
            "stripe_account_status": "active" if acct.charges_enabled else "incomplete",
            "stripe_details_submitted": bool(acct.details_submitted),
            "updated_at": datetime.now(timezone.utc),
        }
        await db.businesses.update_one({"business_id": business_id}, {"$set": update})
        return {
            "connected": True, "stripe_account_id": acct_id,
            "charges_enabled": acct.charges_enabled,
            "payouts_enabled": acct.payouts_enabled,
            "details_submitted": acct.details_submitted,
            "requirements": (acct.requirements.currently_due if acct.requirements else []),
        }
    except Exception as e:
        logger.warning(f"acct retrieve failed: {e}")
        return {"connected": False, "stripe_account_id": acct_id, "error": str(e)}


@advertiser_p45_router.post("/stripe/refresh_account_link")
async def stripe_refresh_link(request: Request, u: dict = Depends(_require_advertiser),
                                business_id: str = Query(...)):
    db = request.app.state.db
    biz = await db.businesses.find_one({"business_id": business_id})
    if not biz or not biz.get("stripe_connect_account_id"):
        raise HTTPException(404, "no Stripe account for this business")
    base = str(request.base_url).rstrip("/")
    link = stripe.AccountLink.create(
        account=biz["stripe_connect_account_id"], type="account_onboarding",
        refresh_url=f"{base}/advertiser/payouts?refresh=1",
        return_url=f"{base}/advertiser/payouts?return=1",
    )
    return {"ok": True, "onboarding_url": link.url}


@advertiser_p45_router.get("/stripe/payouts")
async def stripe_payouts(request: Request, u: dict = Depends(_require_advertiser),
                         business_id: str = Query(...)):
    db = request.app.state.db
    biz = await db.businesses.find_one({"business_id": business_id})
    if not biz or not biz.get("stripe_connect_account_id"):
        return {"available": [], "pending": [], "payouts": [], "balance": None}
    acct_id = biz["stripe_connect_account_id"]
    try:
        balance = stripe.Balance.retrieve(stripe_account=acct_id)
        payouts = stripe.Payout.list(limit=10, stripe_account=acct_id)
        return {
            "available": [{"amount": b.amount, "currency": b.currency} for b in balance.available],
            "pending":   [{"amount": b.amount, "currency": b.currency} for b in balance.pending],
            "payouts": [{"id": p.id, "amount": p.amount, "currency": p.currency,
                          "status": p.status, "arrival_date": p.arrival_date}
                         for p in payouts.data],
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# AI SPONSOR-READ ENDPOINT
# ============================================================
@advertiser_p45_router.post("/creative/ai_sponsor_read")
async def ai_sponsor_read(request: Request, payload: dict, u: dict = Depends(_require_advertiser)):
    from services.sponsor_read import generate_sponsor_read
    if not payload.get("business_id") or not payload.get("brief"):
        raise HTTPException(400, "business_id + brief required")
    db = request.app.state.db
    biz = await db.businesses.find_one({"business_id": payload["business_id"]})
    if not biz: raise HTTPException(404, "business not found")
    adv = await db.advertisers.find_one({"user_id": u["user_id"]}) if u.get("role") != "admin" else None
    advertiser_id = adv["advertiser_id"] if adv else biz.get("advertiser_id", "admin")
    try:
        result = await generate_sponsor_read(
            db,
            advertiser_id=advertiser_id, business_id=payload["business_id"],
            brief=payload["brief"], voice_key=payload.get("voice_key") or "aanya_hindi",
            duration_sec=int(payload.get("duration_sec") or 20),
            tone=payload.get("tone") or "warm-energetic",
            action_labels=payload.get("action_labels") or [],
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"sponsor read gen failed: {e}")
        raise HTTPException(500, f"sponsor read gen failed: {e}")


# ============================================================
# Admin SSP partner management
# ============================================================
@admin_p45_router.get("/ssp/partners")
async def list_ssp_partners(request: Request, _a = Depends(_require_admin)):
    db = request.app.state.db
    docs = await db.ssp_partners.find({}).to_list(length=50)
    # 30-day stats per partner
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=30)
    out = []
    for p in docs:
        pid = p.get("_id")
        wins = await db.openrtb_auctions.count_documents({"winner_partner": pid, "ran_at": {"$gte": since}})
        bids = await db.openrtb_auctions.count_documents({"all_bids.partner": pid, "ran_at": {"$gte": since}})
        avg = await db.openrtb_auctions.aggregate([
            {"$match": {"winner_partner": pid, "ran_at": {"$gte": since}}},
            {"$group": {"_id": None, "avg": {"$avg": "$winner_price_cents"}}},
        ]).to_list(length=1)
        avg_bid = int(avg[0]["avg"]) if avg else 0
        d = _ser(p)
        d["win_count_30d"] = wins; d["bid_count_30d"] = bids; d["avg_bid_cents"] = avg_bid
        out.append(d)
    return {"items": out, "total": len(out)}


@admin_p45_router.post("/ssp/partners/{partner_id}/enable")
async def enable_partner(partner_id: str, request: Request, _a = Depends(_require_admin)):
    db = request.app.state.db
    res = await db.ssp_partners.update_one({"_id": partner_id}, {"$set": {"enabled": True}})
    if res.matched_count != 1: raise HTTPException(404, "partner not found")
    return {"ok": True}


@admin_p45_router.post("/ssp/partners/{partner_id}/disable")
async def disable_partner(partner_id: str, request: Request, _a = Depends(_require_admin)):
    db = request.app.state.db
    res = await db.ssp_partners.update_one({"_id": partner_id}, {"$set": {"enabled": False}})
    if res.matched_count != 1: raise HTTPException(404, "partner not found")
    return {"ok": True}


@admin_p45_router.post("/ssp/partners/{partner_id}")
async def update_partner(partner_id: str, request: Request, _a = Depends(_require_admin),
                          payload: dict = None):
    if not payload: raise HTTPException(400, "missing body")
    db = request.app.state.db
    allowed = {"name", "endpoint_url", "bidder_id", "secret", "timeout_ms", "enabled"}
    upd = {k: payload[k] for k in payload if k in allowed}
    if not upd: raise HTTPException(400, "no allowed fields")
    upd["updated_at"] = datetime.now(timezone.utc)
    res = await db.ssp_partners.update_one({"_id": partner_id}, {"$set": upd})
    if res.matched_count != 1: raise HTTPException(404, "partner not found")
    fresh = await db.ssp_partners.find_one({"_id": partner_id})
    return {"ok": True, "partner": _ser(fresh)}


@admin_p45_router.get("/ssp/auctions/recent")
async def recent_auctions(request: Request, _a = Depends(_require_admin),
                            limit: int = Query(20, ge=1, le=200)):
    db = request.app.state.db
    docs = await db.openrtb_auctions.find({}, {"_id": 0}).sort([("ran_at", -1)]).to_list(length=limit)
    for d in docs:
        if d.get("ran_at") and hasattr(d["ran_at"], "isoformat"):
            d["ran_at"] = d["ran_at"].isoformat()
    return {"items": docs, "total": len(docs)}
