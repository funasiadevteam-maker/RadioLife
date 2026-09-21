"""Payouts Hub — a thin orchestration layer over the EXISTING vendor payout
rails so one screen (/payouts) and one admin screen serve BOTH kinds of vendor:

  • Advisors / social professionals  → `advisor_profiles.stripe_account_id`
        + `dream_payouts` ledger (separate charges & transfers on delivery).
  • Business merchants                → `businesses.stripe_account_id`
        + `payment_transactions_v2` (destination charges on payment links /
          marketplace bookings).

This module does NOT create a parallel connected account or a parallel charge
path — it writes to the SAME entity fields the existing charge/settlement code
reads, using the SAME `stripe_connect_service`. It adds: unified onboarding
(with terms acceptance), a unified earnings read, the admin fee knobs
(advisor % + merchant % + the "must onboard before selling" gate), and the gate
helpers other routes call.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import stripe_connect_service as scs
from services.commission_service import FALLBACK_RULE_ID

logger = logging.getLogger("bigfm.payouts_hub")

router = APIRouter(prefix="/api/payouts", tags=["payouts-hub"])
admin_router = APIRouter(prefix="/api/admin", tags=["payouts-hub-admin"])

TERMS_VERSION = "1.0"
SETTINGS_ID = "payout_settings"
DREAM_CONFIG_ID = "dream_payout_config"
COMMISSION_FALLBACK_ID = FALLBACK_RULE_ID  # SC.3 */* fallback rule
DEFAULT_ADVISOR_PCT = 15
DEFAULT_MERCHANT_PCT = 5
UAE_MARKETS = {"dubai", "uae", "abu_dhabi", "abudhabi", "sharjah"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt) -> Optional[str]:
    if not dt:
        return None
    return dt.isoformat() if isinstance(dt, datetime) else str(dt)


def _frontend_url() -> str:
    url = (os.environ.get("FRONTEND_URL")
           or os.environ.get("FRONTEND_BASE_URL") or "").strip()
    return url.rstrip("/") if url else "https://mobile-games-v2.preview.emergentagent.com"


def _origin(request: Request, origin_url: Optional[str]) -> str:
    if origin_url and origin_url.startswith("http"):
        return origin_url.rstrip("/")
    ref = request.headers.get("origin") or request.headers.get("referer")
    if ref and ref.startswith("http"):
        from urllib.parse import urlparse
        p = urlparse(ref)
        return f"{p.scheme}://{p.netloc}"
    return _frontend_url()


def _agreement_text(pct: int) -> str:
    return (f"I agree to pay a {pct}% platform fee on each transaction, and I "
            "accept that I am solely and personally responsible for any "
            "chargebacks, refunds, or disputes. FUUSIC is not liable for "
            "chargebacks.")


def _currency_for_market(market: Optional[str]) -> str:
    return "aed" if (market or "").lower() in UAE_MARKETS else "usd"


# ─────────────────────────── Fee config ────────────────────────────
async def advisor_pct(db) -> int:
    cfg = await db.dream_payout_config.find_one({"_id": DREAM_CONFIG_ID})
    return int((cfg or {}).get("commission_pct", DEFAULT_ADVISOR_PCT))


async def merchant_pct(db) -> int:
    rule = await db.commission_rules.find_one({"_id": COMMISSION_FALLBACK_ID})
    if rule and rule.get("commission_percent") is not None:
        return int(round(float(rule["commission_percent"])))
    return DEFAULT_MERCHANT_PCT


# ─────────────────────────── Gate helpers ──────────────────────────
async def gate_on(db) -> bool:
    s = await db.payout_settings.find_one({"_id": SETTINGS_ID})
    return bool((s or {}).get("require_onboarding", False))


async def advisor_payout_ready(db, advisor_id: str) -> bool:
    a = await db.advisor_profiles.find_one({"advisor_id": advisor_id})
    return bool(a and (a.get("stripe_charges_enabled") or a.get("stripe_payouts_enabled")))


def merchant_payout_ready(biz: dict) -> bool:
    return bool(biz and biz.get("stripe_account_id") and biz.get("stripe_charges_enabled"))


# ─────────────────────────── Eligibility ───────────────────────────
async def _advisor_profile(db, uid: str) -> Optional[dict]:
    return await db.advisor_profiles.find_one(
        {"user_id": uid, "status": "approved"})


async def _owned_business(db, uid: str) -> Optional[dict]:
    return await db.businesses.find_one(
        {"$or": [{"owner_user_id": uid}, {"owner_user_ids": uid}]})


# ─────────────────────────── Earnings ──────────────────────────────
async def _advisor_earnings(db, advisor_id: str) -> dict:
    sales = fees = paid = pending = 0
    async for p in db.dream_payouts.find({"advisor_id": advisor_id}):
        sales += int(p.get("gross_cents", 0))
        fees += int(p.get("platform_fee_cents", 0))
        share = int(p.get("advisor_share_cents", 0))
        if p.get("status") == "paid":
            paid += share
        else:
            pending += share
    return {"sales_cents": sales, "fees_cents": fees,
            "paid_cents": paid, "pending_cents": pending}


async def _merchant_earnings(db, merchant_id: str) -> dict:
    sales = fees = paid = pending = 0
    async for t in db.payment_transactions_v2.find({"merchant_id": merchant_id}):
        amt = int(t.get("amount_cents", 0))
        fee = int(t.get("application_fee_cents", 0))
        net = int(t.get("merchant_net_cents", max(0, amt - fee)))
        if t.get("status") == "succeeded":
            sales += amt
            fees += fee
            paid += net
        elif t.get("status") in ("requires_confirmation", "processing", "requires_action"):
            pending += max(0, amt - fee)
    return {"sales_cents": sales, "fees_cents": fees,
            "paid_cents": paid, "pending_cents": pending}


# ─────────────────────── Account view builders ─────────────────────
async def _advisor_account(db, a: dict) -> dict:
    terms = a.get("payout_terms") or {}
    return {
        "vendor_type": "advisor", "ref_id": a["advisor_id"],
        "display_name": a.get("display_name") or "Advisor profile",
        "onboarding_status": a.get("stripe_onboarding_status") or "not_started",
        "payouts_enabled": bool(a.get("stripe_payouts_enabled")),
        "charges_enabled": bool(a.get("stripe_charges_enabled")),
        "has_account": bool(a.get("stripe_account_id")),
        "ready": bool(a.get("stripe_charges_enabled") or a.get("stripe_payouts_enabled")),
        "fee_pct": await advisor_pct(db),
        "currency": "usd",
        "earnings": await _advisor_earnings(db, a["advisor_id"]),
        "agreement": {"accepted": bool(terms.get("accepted")),
                      "version": terms.get("version")},
    }


async def _merchant_account(db, biz: dict) -> dict:
    mid = biz.get("business_id") or biz.get("_id")
    terms = biz.get("payout_terms") or {}
    return {
        "vendor_type": "merchant", "ref_id": mid,
        "display_name": biz.get("name") or "Business",
        "onboarding_status": biz.get("stripe_onboarding_status") or "not_started",
        "payouts_enabled": bool(biz.get("stripe_payouts_enabled")),
        "charges_enabled": bool(biz.get("stripe_charges_enabled")),
        "has_account": bool(biz.get("stripe_account_id")),
        "ready": merchant_payout_ready(biz),
        "fee_pct": await merchant_pct(db),
        "currency": _currency_for_market(biz.get("market") or biz.get("city")),
        "earnings": await _merchant_earnings(db, mid),
        "agreement": {"accepted": bool(terms.get("accepted")),
                      "version": terms.get("version")},
    }


# ─────────────────────────── Endpoints ─────────────────────────────
@router.get("/overview")
async def overview(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    accounts: list[dict] = []
    a = await _advisor_profile(db, uid)
    if a:
        accounts.append(await _advisor_account(db, a))
    biz = await _owned_business(db, uid)
    if biz:
        accounts.append(await _merchant_account(db, biz))
    return {"eligible": len(accounts) > 0, "accounts": accounts,
            "terms_version": TERMS_VERSION,
            "gate_on": await gate_on(db),
            "agreement_template_advisor": _agreement_text(await advisor_pct(db)),
            "agreement_template_merchant": _agreement_text(await merchant_pct(db))}


class OnboardBody(BaseModel):
    vendor_type: str = Field(..., pattern="^(advisor|merchant)$")
    agreement_accepted: bool = False
    origin_url: Optional[str] = None
    country: Optional[str] = None


async def _record_terms(db, coll, key_field, key_val, pct: int, ip: str):
    await coll.update_one({key_field: key_val}, {"$set": {"payout_terms": {
        "accepted": True, "version": TERMS_VERSION, "fee_pct": pct,
        "accepted_at": _now().isoformat(), "ip": ip,
        "text": _agreement_text(pct)}}})


@router.post("/onboard")
async def onboard(body: OnboardBody, request: Request,
                  user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    ip = (request.client.host if request.client else "") or ""
    origin = _origin(request, body.origin_url)

    if body.vendor_type == "advisor":
        a = await _advisor_profile(db, uid)
        if not a:
            raise HTTPException(404, {"code": "not_an_advisor"})
        acct = a.get("stripe_account_id")
        pct = await advisor_pct(db)
        if not acct and not body.agreement_accepted:
            raise HTTPException(400, {"code": "agreement_required"})
        if body.agreement_accepted:
            await _record_terms(db, db.advisor_profiles, "advisor_id",
                                 a["advisor_id"], pct, ip)
        if not acct:
            created = await scs.create_connected_account(
                merchant_id=a["advisor_id"],
                email=user.get("email") or f"{a['advisor_id']}@advisor.fuusic",
                country=body.country or "US")
            acct = created["stripe_account_id"]
            await db.advisor_profiles.update_one(
                {"advisor_id": a["advisor_id"]},
                {"$set": {"stripe_account_id": acct,
                          "stripe_onboarding_status": "onboarding_in_progress"}})
        url = await scs.create_onboarding_link(
            stripe_account_id=acct,
            return_url=f"{origin}/payouts?connect=done",
            refresh_url=f"{origin}/payouts?connect=refresh")
        return {"ok": True, "onboarding_url": url, "fee_pct": pct, "currency": "usd"}

    # merchant
    biz = await _owned_business(db, uid)
    if not biz:
        raise HTTPException(404, {"code": "not_a_merchant"})
    mid = biz.get("business_id") or biz.get("_id")
    filter_by = "business_id" if biz.get("business_id") else "_id"
    acct = biz.get("stripe_account_id")
    pct = await merchant_pct(db)
    if not acct and not body.agreement_accepted:
        raise HTTPException(400, {"code": "agreement_required"})
    if body.agreement_accepted:
        await _record_terms(db, db.businesses, filter_by, mid, pct, ip)
    country = body.country or ("AE" if _currency_for_market(
        biz.get("market") or biz.get("city")) == "aed" else "US")
    if not acct:
        created = await scs.create_connected_account(
            merchant_id=mid,
            email=(biz.get("owner_email") or biz.get("email")
                   or user.get("email") or f"merchant+{mid}@fuusic.app"),
            country=country)
        acct = created["stripe_account_id"]
        await db.businesses.update_one(
            {filter_by: mid},
            {"$set": {"stripe_account_id": acct,
                      "stripe_onboarding_status": "onboarding_in_progress"}})
    url = await scs.create_onboarding_link(
        stripe_account_id=acct,
        return_url=f"{origin}/payouts?connect=done",
        refresh_url=f"{origin}/payouts?connect=refresh")
    return {"ok": True, "onboarding_url": url, "fee_pct": pct,
            "currency": _currency_for_market(biz.get("market") or biz.get("city"))}


class RefreshBody(BaseModel):
    vendor_type: str = Field(..., pattern="^(advisor|merchant)$")


@router.post("/refresh")
async def refresh(body: RefreshBody, request: Request,
                  user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    if body.vendor_type == "advisor":
        a = await _advisor_profile(db, uid)
        if not a or not a.get("stripe_account_id"):
            raise HTTPException(400, {"code": "no_account"})
        acct, coll, key_field, key_val = (a["stripe_account_id"],
                                           db.advisor_profiles, "advisor_id",
                                           a["advisor_id"])
        cur = a.get("stripe_onboarding_status") or "not_started"
    else:
        biz = await _owned_business(db, uid)
        if not biz or not biz.get("stripe_account_id"):
            raise HTTPException(400, {"code": "no_account"})
        mid = biz.get("business_id") or biz.get("_id")
        acct, coll = biz["stripe_account_id"], db.businesses
        key_field = "business_id" if biz.get("business_id") else "_id"
        key_val = mid
        cur = biz.get("stripe_onboarding_status") or "not_started"
    live = await scs.retrieve_account_status(acct)
    status = scs.derive_onboarding_status(
        charges_enabled=live["charges_enabled"],
        payouts_enabled=live["payouts_enabled"],
        details_submitted=live["details_submitted"],
        requirements_currently_due=live["requirements_currently_due"],
        requirements_past_due=live["requirements_past_due"],
        requirements_disabled_reason=live["requirements_disabled_reason"],
        current_status=cur)
    await coll.update_one({key_field: key_val}, {"$set": {
        "stripe_charges_enabled": live["charges_enabled"],
        "stripe_payouts_enabled": live["payouts_enabled"],
        "stripe_details_submitted": live["details_submitted"],
        "stripe_onboarding_status": status,
        "stripe_status_synced_at": _now()}})
    return {"ok": True, "onboarding_status": status,
            "payouts_enabled": live["payouts_enabled"],
            "charges_enabled": live["charges_enabled"]}


# ─────────────────────────── Admin fees ────────────────────────────
@admin_router.get("/vendor-fees")
async def get_vendor_fees(request: Request, user: dict = Depends(require_admin)):
    db = request.app.state.db
    return {"advisor_pct": await advisor_pct(db),
            "merchant_pct": await merchant_pct(db),
            "require_onboarding": await gate_on(db),
            "terms_version": TERMS_VERSION}


class VendorFeesBody(BaseModel):
    advisor_pct: Optional[int] = Field(None, ge=0, le=90)
    merchant_pct: Optional[int] = Field(None, ge=0, le=90)
    require_onboarding: Optional[bool] = None


@admin_router.put("/vendor-fees")
async def put_vendor_fees(body: VendorFeesBody, request: Request,
                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    if body.advisor_pct is not None:
        await db.dream_payout_config.update_one(
            {"_id": DREAM_CONFIG_ID},
            {"$set": {"commission_pct": body.advisor_pct}}, upsert=True)
    if body.merchant_pct is not None:
        await db.commission_rules.update_one(
            {"_id": COMMISSION_FALLBACK_ID},
            {"$set": {"commission_percent": float(body.merchant_pct),
                      "active": True, "updated_at": _now()},
             "$setOnInsert": {"_id": COMMISSION_FALLBACK_ID,
                              "business_category": "*", "transaction_type": "*",
                              "market": "*", "fixed_fee_cents": 0,
                              "min_fee_cents": 0, "max_fee_cents": None,
                              "priority": 0, "created_at": _now()}},
            upsert=True)
    if body.require_onboarding is not None:
        await db.payout_settings.update_one(
            {"_id": SETTINGS_ID},
            {"$set": {"require_onboarding": bool(body.require_onboarding)}},
            upsert=True)
    return await get_vendor_fees(request, user)


async def ensure_payout_hub_defaults(db) -> None:
    """Seed the gate flag once. Fee defaults are managed by the migration +
    admin screen, so we don't overwrite them here."""
    await db.payout_settings.update_one(
        {"_id": SETTINGS_ID},
        {"$setOnInsert": {"_id": SETTINGS_ID, "require_onboarding": True}},
        upsert=True)


__all__ = ["router", "admin_router", "ensure_payout_hub_defaults",
           "gate_on", "advisor_payout_ready", "merchant_payout_ready",
           "advisor_pct", "merchant_pct"]
