"""Billing routes: pricing, checkout, status polling, webhook.

Mounted at `/api/billing/*` and `/api/webhook/stripe` (the webhook path is
the canonical one per the Stripe integration playbook).
"""
from __future__ import annotations
from core.origins import resolve_origin

import logging
from typing import Optional

from emergentintegrations.payments.stripe.checkout import (
    CheckoutSessionRequest, StripeCheckout,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user
from core.config import STRIPE_API_KEY, STRIPE_MODE, STRIPE_WEBHOOK_SECRET
from models.billing import (
    CheckoutRequest, CheckoutResponse, CheckoutStatusResponse,
    PricingConfigOut, SubscriptionOut,
)
from services.billing_service import (
    get_transaction, grant_premium, mark_transaction_complete,
    mark_transaction_expired, record_pending_transaction, revoke_premium,
    serialize_subscription,
)
from services.currency import (
    cf_country_header, client_ip, country_from_ip, detect_currency,
)
from services.stripe_setup import (
    DEFAULT_PLAN_ID, get_plan, get_price_for_currency, list_plans_for_currency,
)

logger = logging.getLogger("bigfm.billing.routes")

billing_router = APIRouter(prefix="/api/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/api/webhook", tags=["billing"])

TEST_BANNER_COPY = "Test mode · No real charges"


def _stripe_client(request: Request) -> StripeCheckout:
    """Build a StripeCheckout pointing at our own webhook URL.

    The integration library expects the public origin so it can sign the
    success/cancel URLs and webhook callbacks. We derive it from the request
    headers (set by the ingress / Cloudflare)."""
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url,
                          webhook_secret=STRIPE_WEBHOOK_SECRET or None)


@billing_router.get("/config", response_model=PricingConfigOut)
async def billing_config(
    request: Request,
    currency: Optional[str] = Query(default=None, max_length=8),
):
    """Public — frontend reads this to render the /pricing page.
    Currency is detected from headers unless overridden via `?currency=`."""
    try:
        cur, country = detect_currency(request, override=currency)
    except ValueError as e:
        raise HTTPException(400, str(e))
    plans = list_plans_for_currency(cur)
    return PricingConfigOut(
        mode=STRIPE_MODE,
        currency=cur,
        country_hint=country,
        plans=plans,
        test_banner=TEST_BANNER_COPY if STRIPE_MODE == "test" else None,
    )


# ----------------------------------------------------------------------
# Debug endpoint — region / currency detection introspection.
# No auth (debug only, no sensitive data). Soft rate limit: 6 req/min/IP.
# ----------------------------------------------------------------------
import time as _time

_WHOAMI_HITS: dict[str, list[float]] = {}
_WHOAMI_WINDOW_SEC = 60.0
_WHOAMI_MAX_HITS = 6
# Headers we surface in the debug response — strictly safe / non-secret.
_WHOAMI_SAFE_HEADERS = (
    "host", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-real-ip", "cf-ipcountry", "cf-ray", "cf-connecting-ip",
    "x-country", "x-vercel-ip-country", "x-emergent-country",
    "x-forwarded-country", "x-geo-country", "x-client-country",
    "user-agent", "accept-language",
)


def _whoami_rate_limit_ok(ip: str) -> bool:
    now = _time.monotonic()
    bucket = _WHOAMI_HITS.setdefault(ip, [])
    # Drop hits older than the window
    cutoff = now - _WHOAMI_WINDOW_SEC
    bucket[:] = [t for t in bucket if t >= cutoff]
    if len(bucket) >= _WHOAMI_MAX_HITS:
        return False
    bucket.append(now)
    # Opportunistic GC: every ~20 calls trim the dict so it doesn't grow unbounded
    if len(_WHOAMI_HITS) > 1024:
        for k in [k for k, v in _WHOAMI_HITS.items() if not v or v[-1] < cutoff]:
            _WHOAMI_HITS.pop(k, None)
    return True


@billing_router.get("/_whoami")
async def billing_whoami(request: Request):
    """Debug endpoint — returns the inputs used by detect_currency() for the
    caller's request. Use this to verify region detection from any client.

    Soft rate-limited to 6 requests per IP per minute. No auth required.
    Does NOT return any auth tokens, cookies, or secrets.
    """
    ip = client_ip(request) or "unknown"
    if not _whoami_rate_limit_ok(ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: {_WHOAMI_MAX_HITS} requests per {int(_WHOAMI_WINDOW_SEC)}s per IP",
        )

    cf = cf_country_header(request)
    geo = country_from_ip(ip) if ip and ip != "unknown" else None
    resolved_country = cf or geo
    cur, _ = detect_currency(request, override=None)
    try:
        price = get_price_for_currency(DEFAULT_PLAN_ID, cur)
        # Stripe expects minor units (cents/fils/paise) — 12.00 USD → 1200
        stripe_minor = int(round(float(price["amount"]) * 100))
        major = float(price["amount"])
    except Exception:
        stripe_minor, major = 0, 0.0

    return {
        "ip": ip,
        "cf_country": cf,
        "geoip_country": geo,
        "resolved_country": resolved_country,
        "resolved_currency": cur,
        "stripe_amount": stripe_minor,       # minor units (1200 = $12.00)
        "amount_major": major,                # major units (12.00)
        "plan_id": DEFAULT_PLAN_ID,
        "stripe_mode": STRIPE_MODE,
        "headers_seen": sorted(
            k.lower() for k in request.headers.keys()
            if k.lower() in _WHOAMI_SAFE_HEADERS
        ),
        "rate_limit": {
            "per_ip": _WHOAMI_MAX_HITS,
            "window_sec": int(_WHOAMI_WINDOW_SEC),
            "remaining": max(0, _WHOAMI_MAX_HITS - len(_WHOAMI_HITS.get(ip, []))),
        },
    }


@billing_router.get("/subscription", response_model=SubscriptionOut)
async def my_subscription(user: dict = Depends(current_user)):
    return SubscriptionOut(**serialize_subscription(user))


@billing_router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    user: dict = Depends(current_user),
):
    """Create a Stripe Checkout Session. Backend defines amount + currency —
    NEVER trust the frontend's amount."""
    plan = get_plan(body.plan_id)
    if not plan:
        raise HTTPException(400, f"unknown plan_id {body.plan_id}")
    try:
        cur, _ = detect_currency(request, override=body.currency)
    except ValueError as e:
        raise HTTPException(400, str(e))
    price = get_price_for_currency(body.plan_id, cur)

    # Build URLs from the frontend's origin (the user's window.location.origin)
    origin = resolve_origin(request, body.origin_url)
    if not origin.startswith("http"):
        raise HTTPException(400, "origin_url must be http(s)")
    success_url = f"{origin}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/pricing?cancelled=1"

    stripe = _stripe_client(request)
    checkout_req = CheckoutSessionRequest(
        amount=price["amount"],
        currency=price["currency"].lower(),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "user_id": user["user_id"],
            "user_email": user["email"],
            "plan_id": body.plan_id,
            "tier": plan.get("tier") or "premium",
            "source": "bigfm_pricing_page",
        },
    )
    try:
        session = await stripe.create_checkout_session(checkout_req)
    except Exception as e:
        logger.exception("Stripe checkout creation failed")
        raise HTTPException(502, f"Stripe error: {e}")

    await record_pending_transaction(
        session_id=session.session_id,
        user_id=user["user_id"],
        user_email=user["email"],
        plan_id=body.plan_id,
        amount=price["amount"],
        currency=price["currency"],
        metadata={"checkout_url": session.url},
    )
    return CheckoutResponse(url=session.url, session_id=session.session_id)


@billing_router.get("/status/{session_id}", response_model=CheckoutStatusResponse)
async def checkout_status(
    session_id: str,
    request: Request,
    user: dict = Depends(current_user),
):
    """Polled by the /billing/success page until status is paid/expired.
    Idempotent: only grants premium ONCE per session_id."""
    tx = await get_transaction(session_id)
    if not tx:
        raise HTTPException(404, "session not found")
    if tx.get("user_id") != user["user_id"]:
        raise HTTPException(403, "session does not belong to you")

    stripe = _stripe_client(request)
    try:
        status = await stripe.get_checkout_status(session_id)
    except Exception as e:
        logger.exception("Stripe status check failed")
        raise HTTPException(502, f"Stripe status error: {e}")

    # Stripe returns amount_total in cents — convert to major units
    amount_major = float(status.amount_total) / 100.0 if status.amount_total else 0.0

    is_paid = status.payment_status == "paid" and status.status == "complete"
    if is_paid:
        first_time = await mark_transaction_complete(
            session_id,
            payment_status=status.payment_status,
            amount_total=amount_major,
            currency=(status.currency or tx.get("currency") or "USD").upper(),
        )
        if first_time:
            await grant_premium(
                user["user_id"], tx["plan_id"],
                (status.currency or tx["currency"]).upper(),
                stripe_session_id=session_id,
            )
        # Reload user to surface latest premium flag
        fresh = await request.app.state.db.users.find_one(
            {"user_id": user["user_id"]}, {"_id": 0},
        )
        user = fresh or user
    elif status.status == "expired":
        await mark_transaction_expired(session_id)

    sub = serialize_subscription(user)
    return CheckoutStatusResponse(
        session_id=session_id,
        status=status.status,
        payment_status=status.payment_status,
        amount_total=amount_major,
        currency=(status.currency or tx.get("currency") or "USD").upper(),
        plan_id=tx.get("plan_id") or DEFAULT_PLAN_ID,
        is_premium=sub["is_premium"],
        premium_tier=sub.get("premium_tier"),
    )


@billing_router.post("/cancel")
async def cancel_subscription(user: dict = Depends(current_user)):
    """Soft-cancel: lets user keep premium until period_end."""
    await revoke_premium(user["user_id"], immediate=False)
    return {"ok": True, "cancel_at_period_end": True}


@billing_router.post("/resume")
async def resume_subscription(request: Request, user: dict = Depends(current_user)):
    """Reverses a soft-cancel by clearing cancel_at_period_end."""
    db = request.app.state.db
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"subscription.cancel_at_period_end": False}},
    )
    return {"ok": True, "cancel_at_period_end": False}


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request):
    """Stripe Checkout webhook handler. The Emergent stripe lib verifies
    the signature for us; on a successful event we grant premium idempotently."""
    stripe = _stripe_client(request)
    body = await request.body()
    sig = request.headers.get("Stripe-Signature") or ""
    try:
        evt = await stripe.handle_webhook(body, sig)
    except Exception as e:
        logger.warning(f"Stripe webhook signature/parse failure: {e}")
        raise HTTPException(400, "invalid webhook")

    session_id = evt.session_id
    meta = evt.metadata or {}
    if not session_id:
        return {"received": True, "ignored": True}
    tx = await get_transaction(session_id)
    if not tx:
        logger.info(f"Webhook for unknown session {session_id}; ignoring")
        return {"received": True, "unknown": True}
    if evt.payment_status == "paid":
        first = await mark_transaction_complete(
            session_id, payment_status="paid",
            amount_total=float(tx.get("amount") or 0.0),
            currency=(tx.get("currency") or "USD").upper(),
        )
        if first:
            uid = meta.get("user_id") or tx.get("user_id")
            plan = meta.get("plan_id") or tx.get("plan_id") or DEFAULT_PLAN_ID
            cur = (tx.get("currency") or "USD").upper()
            if uid:
                await grant_premium(uid, plan, cur, stripe_session_id=session_id)
    return {"received": True, "event_type": evt.event_type, "session_id": session_id}
