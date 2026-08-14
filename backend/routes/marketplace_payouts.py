"""Marketplace Merchant Payouts — Stripe Connect Express.

Funds are collected on the PLATFORM account (subscription Checkout). This module
adds Express onboarding + separate Transfers: a merchant connects a bank via
Stripe's hosted Express flow, then withdraws their tracked net earnings (from the
`merchant_earnings` ledger) as a Transfer to their connected Stripe balance, and
can optionally Instant-Payout that balance to their bank for a fee.

Test mode until the platform goes live (Publish). Onboarding status is read by
polling Stripe (retrieve account) — no Connect webhook secret required.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from auth import current_user
from services.marketplace import now, new_id

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/merchant/marketplace", tags=["marketplace-payouts"])

_DONE_HTML = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RadioLife Payouts</title><style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#FBF5EC;color:#1C1917;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}.c{text-align:center;padding:32px;max-width:420px}
.b{width:64px;height:64px;border-radius:50%;background:#059669;color:#fff;display:flex;align-items:center;justify-content:center;
font-size:34px;margin:0 auto 16px}h1{font-size:22px;margin:0 0 8px}p{color:#57534E;font-size:15px;line-height:1.5}</style></head>
<body><div class="c"><div class="b">✓</div><h1>You're all set</h1>
<p>Your payout details were saved. You can close this window and return to the RadioLife app.</p></div></body></html>"""


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


def _urls(origin: str, platform: str, account_id: str, api_base: str):
    if platform == "mobile":
        ret = f"{api_base}/api/merchant/marketplace/connect/return"
        ref = (f"{api_base}/api/merchant/marketplace/connect/refresh"
               f"?account={account_id}&platform=mobile&origin={origin}")
    else:
        base = origin.rstrip("/")
        ret = f"{base}/shop/merchant/earnings?connect=return"
        ref = f"{base}/shop/merchant/earnings?connect=refresh"
    return ret, ref


def _make_link(account_id: str, return_url: str, refresh_url: str) -> str:
    link = stripe.AccountLink.create(
        account=account_id, refresh_url=refresh_url, return_url=return_url,
        type="account_onboarding")
    return link.url


async def _ensure_account(db, profile: Dict[str, Any]) -> str:
    acct = profile.get("stripe_account_id")
    if acct:
        return acct
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    account = stripe.Account.create(
        type="express", country=(profile.get("payout_country") or "US"),
        email=profile.get("contact_email") or None,
        capabilities={"transfers": {"requested": True}},
        metadata={"business_id": profile["business_id"]})
    await db.marketplace_profiles.update_one(
        {"business_id": profile["business_id"]},
        {"$set": {"stripe_account_id": account.id, "updated_at": now()}})
    return account.id


class OnboardBody(BaseModel):
    origin_url: Optional[str] = None
    platform: str = "web"


@router.post("/connect/account")
async def connect_account(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    acct = await _ensure_account(db, p)
    return {"ok": True, "stripe_account_id": acct}


@router.post("/connect/onboarding-link")
async def onboarding_link(body: OnboardBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    acct = await _ensure_account(db, p)
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    api_base = str(request.base_url).rstrip("/")
    if not origin:
        origin = api_base
    ret, ref = _urls(origin, body.platform, acct, api_base)
    return {"ok": True, "url": _make_link(acct, ret, ref)}


@router.get("/connect/refresh")
async def connect_refresh(account: str, request: Request, platform: str = "mobile", origin: str = ""):
    api_base = str(request.base_url).rstrip("/")
    ret, ref = _urls(origin or api_base, platform, account, api_base)
    return RedirectResponse(_make_link(account, ret, ref))


@router.get("/connect/return", response_class=HTMLResponse)
async def connect_return():
    return HTMLResponse(_DONE_HTML)


def _status_view(a: Any) -> Dict[str, Any]:
    caps = (a.get("capabilities") or {}) if isinstance(a, dict) else (a.capabilities or {})
    transfers = caps.get("transfers")
    req = (a.get("requirements") or {}) if isinstance(a, dict) else (a.requirements or {})
    details = a.get("details_submitted") if isinstance(a, dict) else a.details_submitted
    payouts_enabled = a.get("payouts_enabled") if isinstance(a, dict) else a.payouts_enabled
    charges_enabled = a.get("charges_enabled") if isinstance(a, dict) else a.charges_enabled
    return {
        "connected": bool(details and payouts_enabled and transfers == "active"),
        "details_submitted": bool(details),
        "charges_enabled": bool(charges_enabled),
        "payouts_enabled": bool(payouts_enabled),
        "transfers_capability": transfers,
        "requirements_due": list((req.get("currently_due") or []))[:10],
    }


@router.get("/connect/status")
async def connect_status(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    acct = p.get("stripe_account_id")
    if not acct:
        return {"has_account": False, "connected": False, "payouts_enabled": False}
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    try:
        a = stripe.Account.retrieve(acct)
    except Exception:
        return {"has_account": True, "connected": False, "payouts_enabled": False,
                "stripe_account_id": acct, "error": "account_unavailable"}
    view = _status_view(a)
    await db.marketplace_profiles.update_one(
        {"business_id": p["business_id"]},
        {"$set": {"payouts_connected": view["connected"],
                  "payouts_enabled": view["payouts_enabled"], "updated_at": now()}})
    return {"has_account": True, "stripe_account_id": acct, **view}


async def _available(db, business_id: str):
    rows = [r async for r in db.merchant_earnings.find(
        {"business_id": business_id,
         "$or": [{"payout_status": {"$exists": False}}, {"payout_status": "available"}]})]
    amount = sum(int(r.get("net_cents", 0)) for r in rows)
    return rows, amount


def _friendly_stripe_error(e: Exception) -> str:
    msg = getattr(getattr(e, "error", None), "message", None) or str(e)
    low = msg.lower()
    if "insufficient" in low or "balance" in low:
        return ("Not enough platform balance to transfer yet. In test mode this happens "
                "until there are settled payments to cover it.")
    return msg[:200]


@router.post("/payout/withdraw")
async def payout_withdraw(request: Request, user: dict = Depends(current_user)):
    """Transfer available net earnings → the merchant's connected Stripe balance."""
    db = request.app.state.db
    p = await _my_business(db, user)
    acct = p.get("stripe_account_id")
    if not acct or not stripe.api_key:
        raise HTTPException(400, {"code": "not_connected"})
    a = stripe.Account.retrieve(acct)
    view = _status_view(a)
    if not view["payouts_enabled"] or view["transfers_capability"] != "active":
        raise HTTPException(409, {"code": "not_payout_ready"})

    batch_id = f"{p['business_id']}:{int(time.time())}"
    # Reserve available rows atomically so a double-tap can't double-pay.
    res = await db.merchant_earnings.update_many(
        {"business_id": p["business_id"],
         "$or": [{"payout_status": {"$exists": False}}, {"payout_status": "available"}]},
        {"$set": {"payout_status": "processing", "payout_batch_id": batch_id}})
    if not res.modified_count:
        raise HTTPException(409, {"code": "no_available_earnings"})
    reserved = [r async for r in db.merchant_earnings.find({"payout_batch_id": batch_id})]
    amount = sum(int(r.get("net_cents", 0)) for r in reserved)
    if amount <= 0:
        await db.merchant_earnings.update_many(
            {"payout_batch_id": batch_id},
            {"$set": {"payout_status": "available"}, "$unset": {"payout_batch_id": ""}})
        raise HTTPException(409, {"code": "no_available_earnings"})
    try:
        transfer = stripe.Transfer.create(
            amount=amount, currency="usd", destination=acct, transfer_group=batch_id,
            metadata={"business_id": p["business_id"], "batch_id": batch_id},
            idempotency_key=f"payout-{batch_id}")
    except Exception as e:
        await db.merchant_earnings.update_many(
            {"payout_batch_id": batch_id},
            {"$set": {"payout_status": "available"}, "$unset": {"payout_batch_id": ""}})
        raise HTTPException(402, {"code": "transfer_failed", "message": _friendly_stripe_error(e)})
    await db.merchant_earnings.update_many(
        {"payout_batch_id": batch_id},
        {"$set": {"payout_status": "transferred", "transfer_id": transfer.id, "paid_at": now()}})
    await db.merchant_payouts.insert_one({
        "payout_id": new_id("pout"), "batch_id": batch_id, "business_id": p["business_id"],
        "kind": "transfer", "amount_cents": amount, "currency": "usd",
        "stripe_transfer_id": transfer.id, "count": len(reserved),
        "status": "transferred", "created_at": now()})
    return {"ok": True, "amount_cents": amount, "count": len(reserved), "transfer_id": transfer.id}


@router.post("/payout/instant")
async def payout_instant(request: Request, user: dict = Depends(current_user)):
    """Instant-Payout the connected account's available balance to its bank (fee)."""
    db = request.app.state.db
    p = await _my_business(db, user)
    acct = p.get("stripe_account_id")
    if not acct or not stripe.api_key:
        raise HTTPException(400, {"code": "not_connected"})
    try:
        bal = stripe.Balance.retrieve(stripe_account=acct)
        instant = getattr(bal, "instant_available", None) or []
        avail = getattr(bal, "available", None) or []
        pick = instant or avail
        usd = next((int(b["amount"]) for b in pick if b.get("currency") == "usd"), 0)
        if usd <= 0:
            raise HTTPException(409, {"code": "no_instant_balance",
                                      "message": "No instant-available balance yet. Withdraw first, then try again."})
        payout = stripe.Payout.create(
            amount=usd, currency="usd", method="instant",
            metadata={"business_id": p["business_id"]},
            stripe_account=acct,
            idempotency_key=f"instant-{p['business_id']}-{int(time.time())}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(402, {"code": "instant_failed", "message": _friendly_stripe_error(e)})
    await db.merchant_payouts.insert_one({
        "payout_id": new_id("pout"), "business_id": p["business_id"], "kind": "instant",
        "amount_cents": int(payout.amount), "currency": "usd",
        "stripe_payout_id": payout.id, "status": payout.status, "created_at": now()})
    return {"ok": True, "amount_cents": int(payout.amount), "payout_id": payout.id, "status": payout.status}


__all__ = ["router"]
