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
from datetime import datetime, timedelta, timezone
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


# ─────────────────────────── History ───────────────────────────────
def _adv_txn_view(p: dict) -> dict:
    return {"id": p.get("booking_id") or str(p.get("_id")),
            "date": _iso(p.get("created_at")),
            "gross_cents": int(p.get("gross_cents", 0)),
            "fee_cents": int(p.get("platform_fee_cents", 0)),
            "net_cents": int(p.get("advisor_share_cents", 0)),
            "status": p.get("status"), "ref": p.get("transfer_id")}


def _mer_txn_view(t: dict) -> dict:
    amt = int(t.get("amount_cents", 0))
    fee = int(t.get("application_fee_cents", 0))
    return {"id": t.get("transaction_id") or str(t.get("_id")),
            "date": _iso(t.get("succeeded_at") or t.get("created_at")),
            "gross_cents": amt, "fee_cents": fee,
            "net_cents": int(t.get("merchant_net_cents", max(0, amt - fee))),
            "status": t.get("status"),
            "ref": t.get("stripe_charge_id") or t.get("transaction_id")}


@router.get("/history")
async def history(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    accounts: list[dict] = []
    a = await _advisor_profile(db, uid)
    if a:
        rows = [_adv_txn_view(p) async for p in
                db.dream_payouts.find({"advisor_id": a["advisor_id"]})
                .sort("created_at", -1).limit(50)]
        accounts.append({"vendor_type": "advisor", "ref_id": a["advisor_id"],
                         "transactions": rows})
    biz = await _owned_business(db, uid)
    if biz:
        mid = biz.get("business_id") or biz.get("_id")
        rows = [_mer_txn_view(t) async for t in
                db.payment_transactions_v2.find({"merchant_id": mid})
                .sort("created_at", -1).limit(50)]
        accounts.append({"vendor_type": "merchant", "ref_id": mid,
                         "transactions": rows})
    return {"accounts": accounts}


# ─────────────────────────── Insights ──────────────────────────────
def _week_starts(n: int) -> list:
    today = _now().date()
    monday = today - timedelta(days=today.weekday())
    return [monday - timedelta(weeks=i) for i in range(n - 1, -1, -1)]


def _empty_weeks(starts: list) -> list:
    return [{"week_start": ws.isoformat(), "label": ws.strftime("%b %d"),
             "sales_cents": 0, "fees_cents": 0, "net_cents": 0} for ws in starts]


def _bucket_idx(dt, starts: list) -> Optional[int]:
    if not isinstance(dt, datetime):
        return None
    d = dt.date()
    for i, ws in enumerate(starts):
        if ws <= d < ws + timedelta(days=7):
            return i
    return None


@router.get("/insights")
async def insights(request: Request, weeks: int = 6,
                   user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    n = max(1, min(12, int(weeks or 6)))
    starts = _week_starts(n)
    cutoff = datetime(starts[0].year, starts[0].month, starts[0].day,
                      tzinfo=timezone.utc)
    accounts: list[dict] = []

    a = await _advisor_profile(db, uid)
    if a:
        buckets = _empty_weeks(starts)
        async for p in db.dream_payouts.find(
                {"advisor_id": a["advisor_id"], "created_at": {"$gte": cutoff}}):
            i = _bucket_idx(p.get("created_at"), starts)
            if i is None:
                continue
            buckets[i]["sales_cents"] += int(p.get("gross_cents", 0))
            buckets[i]["fees_cents"] += int(p.get("platform_fee_cents", 0))
            buckets[i]["net_cents"] += int(p.get("advisor_share_cents", 0))
        accounts.append({"vendor_type": "advisor", "ref_id": a["advisor_id"],
                         "weeks": buckets})

    biz = await _owned_business(db, uid)
    if biz:
        mid = biz.get("business_id") or biz.get("_id")
        buckets = _empty_weeks(starts)
        async for t in db.payment_transactions_v2.find(
                {"merchant_id": mid, "status": "succeeded",
                 "created_at": {"$gte": cutoff}}):
            i = _bucket_idx(t.get("succeeded_at") or t.get("created_at"), starts)
            if i is None:
                continue
            amt = int(t.get("amount_cents", 0))
            fee = int(t.get("application_fee_cents", 0))
            buckets[i]["sales_cents"] += amt
            buckets[i]["fees_cents"] += fee
            buckets[i]["net_cents"] += int(t.get("merchant_net_cents", max(0, amt - fee)))
        accounts.append({"vendor_type": "merchant", "ref_id": mid, "weeks": buckets})

    return {"accounts": accounts, "window_weeks": n}


# ─────────────────────────── Instant cash-out ──────────────────────
DASHBOARD_LOGIN_URL = "https://dashboard.stripe.com/login"


class CashoutBody(BaseModel):
    vendor_type: str = Field(..., pattern="^(advisor|merchant)$")


async def _resolve_cashout_account(db, uid: str, vendor_type: str):
    """→ (stripe_account_id | None, currency, ready)."""
    if vendor_type == "advisor":
        a = await _advisor_profile(db, uid)
        if not a:
            raise HTTPException(404, {"code": "not_an_advisor"})
        return (a.get("stripe_account_id"), "usd",
                bool(a.get("stripe_payouts_enabled") or a.get("stripe_charges_enabled")))
    biz = await _owned_business(db, uid)
    if not biz:
        raise HTTPException(404, {"code": "not_a_merchant"})
    return (biz.get("stripe_account_id"),
            _currency_for_market(biz.get("market") or biz.get("city")),
            merchant_payout_ready(biz))


@router.post("/cashout")
async def cashout(body: CashoutBody, request: Request,
                  user: dict = Depends(current_user)):
    import uuid as _uuid
    db = request.app.state.db
    uid = user["user_id"]
    acct, currency, ready = await _resolve_cashout_account(db, uid, body.vendor_type)
    if not acct or not ready:
        return {"status": "fallback", "reason": "not_onboarded",
                "dashboard_url": DASHBOARD_LOGIN_URL}
    try:
        pre = await scs.instant_payout_precheck(stripe_account_id=acct, currency=currency)
    except Exception as e:
        logger.warning("[cashout] precheck failed: %s", e)
        return {"status": "fallback", "reason": "precheck_failed",
                "dashboard_url": DASHBOARD_LOGIN_URL}
    if not pre.get("ok"):
        return {"status": "fallback", "reason": pre.get("reason"),
                "available_cents": int(pre.get("available", 0)),
                "instant_available_cents": int(pre.get("instant_available", 0)),
                "dashboard_url": DASHBOARD_LOGIN_URL}
    amount = int(pre["instant_available"])
    idem = f"cashout:{body.vendor_type}:{acct}:{amount}:{_uuid.uuid4().hex[:8]}"
    try:
        payout = await scs.create_instant_payout(
            stripe_account_id=acct, amount_cents=amount,
            currency=currency, idempotency_key=idem)
    except Exception as e:
        blob = (getattr(e, "code", "") or "") + " " + str(e)
        if ("not_allowed_on_standard_account" in blob
                or "Cannot create payouts" in blob
                or "payouts_not_allowed" in blob):
            return {"status": "fallback",
                    "reason": "standard_platform_payout_not_allowed",
                    "instant_available_cents": amount,
                    "dashboard_url": DASHBOARD_LOGIN_URL}
        logger.warning("[cashout] payout create failed: %s", e)
        return {"status": "fallback", "reason": "payout_error",
                "dashboard_url": DASHBOARD_LOGIN_URL}
    await db.vendor_instant_payouts.insert_one({
        "_id": payout["payout_id"], "vendor_type": body.vendor_type,
        "stripe_account_id": acct, "amount_cents": amount, "currency": currency,
        "status": payout["status"], "user_id": uid, "created_at": _now()})
    return {"status": payout["status"], "payout_id": payout["payout_id"],
            "amount_cents": amount, "currency": currency}


# ─────────────────────── Weekly earnings digest ────────────────────
WEEKLY_WINDOW_DAYS = 7


def _money_str(c) -> str:
    return f"${(int(c or 0) / 100):.2f}"


def _digest_body(name: str, vendor_type: str, agg: dict) -> tuple[str, str]:
    label = "expert" if vendor_type == "advisor" else "business"
    sales, fees = _money_str(agg["sales"]), _money_str(agg["fees"])
    paid, pending = _money_str(agg["paid"]), _money_str(agg["pending"])
    html = (f"<div style='font-family:system-ui,sans-serif;color:#111'>"
            f"<h2 style='color:#059669'>Your week on FUUSIC</h2>"
            f"<p>Hi {name}, here's your {label} earnings summary for the last 7 days.</p>"
            f"<table cellpadding='8' style='border-collapse:collapse;margin-top:8px'>"
            f"<tr><td style='color:#666'>Sales</td><td><b>{sales}</b></td></tr>"
            f"<tr><td style='color:#666'>Platform fees</td><td>{fees}</td></tr>"
            f"<tr><td style='color:#666'>Paid out</td><td><b style='color:#059669'>{paid}</b></td></tr>"
            f"<tr><td style='color:#666'>Pending</td><td>{pending}</td></tr>"
            f"<tr><td style='color:#666'>Transactions</td><td>{agg['count']}</td></tr>"
            f"</table>"
            f"<p style='color:#666;font-size:12px;margin-top:20px'>— FUUSIC Payouts</p></div>")
    text = (f"Your week on FUUSIC ({label})\nSales {sales}\nFees {fees}\n"
            f"Paid {paid}\nPending {pending}\nTransactions {agg['count']}\n— FUUSIC")
    return html, text


def _send_one_digest(email, name, vendor_type, agg, live) -> dict:
    if not email:
        return {"vendor_type": vendor_type, "name": name, "sent": False,
                "reason": "no_email"}
    html, text = _digest_body(name, vendor_type, agg)
    if not live:
        logger.info("[payout-digest] MOCK (mailgun not live) → %s (%s): %s",
                    email, vendor_type, agg)
        return {"vendor_type": vendor_type, "name": name, "email": email,
                "sent": False, "reason": "provider_not_live", "summary": agg}
    try:
        from services.mailgun_client import send_email
        send_email(to=email, subject="Your weekly FUUSIC earnings",
                   html=html, text=text, tags=["payout_weekly_digest"])
        return {"vendor_type": vendor_type, "name": name, "email": email, "sent": True}
    except Exception as e:
        logger.warning("[payout-digest] send failed %s: %s", email, e)
        return {"vendor_type": vendor_type, "name": name, "email": email,
                "sent": False, "reason": "send_error"}


async def send_weekly_earnings_digests(db, *, only_user_id: Optional[str] = None) -> dict:
    """Email each ACTIVE vendor (advisor/merchant with activity in the last 7
    days) a sales/fees/paid/pending summary via Mailgun. No-op (logged) when
    Mailgun isn't live. `only_user_id` narrows to one vendor (for admin/test)."""
    try:
        from services.mailgun_client import is_live
        live = bool(is_live())
    except Exception:
        live = False
    cutoff = _now() - timedelta(days=WEEKLY_WINDOW_DAYS)

    adv: dict = {}
    async for p in db.dream_payouts.find({"created_at": {"$gte": cutoff}}):
        aid = p.get("advisor_id")
        if not aid:
            continue
        b = adv.setdefault(aid, {"sales": 0, "fees": 0, "paid": 0,
                                 "pending": 0, "count": 0})
        share = int(p.get("advisor_share_cents", 0))
        b["sales"] += int(p.get("gross_cents", 0))
        b["fees"] += int(p.get("platform_fee_cents", 0))
        b["count"] += 1
        if p.get("status") == "paid":
            b["paid"] += share
        else:
            b["pending"] += share

    mer: dict = {}
    async for t in db.payment_transactions_v2.find(
            {"created_at": {"$gte": cutoff}, "status": "succeeded"}):
        mid = t.get("merchant_id")
        if not mid:
            continue
        amt = int(t.get("amount_cents", 0))
        fee = int(t.get("application_fee_cents", 0))
        b = mer.setdefault(mid, {"sales": 0, "fees": 0, "paid": 0,
                                 "pending": 0, "count": 0})
        b["sales"] += amt
        b["fees"] += fee
        b["paid"] += int(t.get("merchant_net_cents", max(0, amt - fee)))
        b["count"] += 1

    results: list[dict] = []
    sent = 0
    for aid, agg in adv.items():
        a = await db.advisor_profiles.find_one({"advisor_id": aid})
        if not a:
            continue
        if only_user_id and a.get("user_id") != only_user_id:
            continue
        u = await db.users.find_one({"user_id": a.get("user_id")}, {"email": 1})
        r = _send_one_digest((u or {}).get("email"),
                             a.get("display_name") or "Advisor", "advisor", agg, live)
        results.append(r)
        sent += 1 if r.get("sent") else 0
    for mid, agg in mer.items():
        biz = await db.businesses.find_one({"$or": [{"business_id": mid}, {"_id": mid}]})
        if not biz:
            continue
        owner = biz.get("owner_user_id")
        owners = biz.get("owner_user_ids") or ([owner] if owner else [])
        if only_user_id and only_user_id not in owners:
            continue
        email = biz.get("owner_email") or biz.get("email")
        if not email:
            uid0 = owner or (owners[0] if owners else None)
            if uid0:
                u = await db.users.find_one({"user_id": uid0}, {"email": 1})
                email = (u or {}).get("email")
        r = _send_one_digest(email, biz.get("name") or "Business", "merchant", agg, live)
        results.append(r)
        sent += 1 if r.get("sent") else 0

    return {"ok": True, "provider_live": live, "sent": sent,
            "advisors": len(adv), "merchants": len(mer), "results": results[:50]}


@admin_router.post("/payouts/send-weekly-digest")
async def admin_send_weekly_digest(request: Request, user_id: Optional[str] = None,
                                   user: dict = Depends(require_admin)):
    db = request.app.state.db
    return await send_weekly_earnings_digests(db, only_user_id=user_id)


async def ensure_payout_hub_defaults(db) -> None:
    """Seed the gate flag once. Fee defaults are managed by the migration +
    admin screen, so we don't overwrite them here."""
    await db.payout_settings.update_one(
        {"_id": SETTINGS_ID},
        {"$setOnInsert": {"_id": SETTINGS_ID, "require_onboarding": True}},
        upsert=True)


__all__ = ["router", "admin_router", "ensure_payout_hub_defaults",
           "gate_on", "advisor_payout_ready", "merchant_payout_ready",
           "advisor_pct", "merchant_pct", "send_weekly_earnings_digests"]
