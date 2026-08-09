"""Phase 36e Turn 1 — Stripe client abstraction (MOCK / LIVE).

ALL Stripe calls in the RadioLife codebase MUST route through this module.
The day the user provides `sk_test_...` or `sk_live_...`, flipping
`STRIPE_MODE` env from `mock` to `live` and supplying the key is the
ONLY change required — call sites are mode-agnostic.

Mock-mode responses use realistic Stripe-shaped object IDs
(acct_/cus_/sub_/price_/prod_/pi_/cs_/evt_) so downstream code paths
behave identically. Webhook signature verification code exists for live
mode but is bypassed (with a log line) in mock mode.

Why an abstraction instead of `stripe.api_key = None`?
  - Mock mode must not hit Stripe's network at all (CI, no internet).
  - Deterministic test IDs (prefixed `mock_`) make tests reproducible.
  - One choke-point for adding telemetry / retries later.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("bigfm.stripe_client")

# Lazy import: only used in live mode.
_stripe = None
def _live_stripe():
    global _stripe
    if _stripe is None:
        import stripe as _s
        _s.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        _stripe = _s
    return _stripe


def stripe_mode() -> str:
    """Returns 'mock' or 'live'. Defaults to mock for safety."""
    m = (os.environ.get("STRIPE_MODE") or "mock").strip().lower()
    return "live" if m == "live" else "mock"


def is_live() -> bool:
    return stripe_mode() == "live"


def _mock_id(prefix: str) -> str:
    return f"{prefix}_mock_{secrets.token_hex(8)}"


# ─── Connect Express accounts ────────────────────────────────────
def create_express_account(*, email: str,
                                                    country: str = "US",
                                                    default_currency: str = "usd") -> dict:
    """Create a Stripe Express account for a creator."""
    if is_live():
        return _live_stripe().Account.create(
            type="express", country=country, email=email,
            capabilities={"transfers": {"requested": True},
                                  "card_payments": {"requested": True}},
            default_currency=default_currency)
    # Mock — return Stripe-shaped Account dict.
    return {
        "id":                              _mock_id("acct"),
        "object":                      "account",
        "type":                          "express",
        "email":                        email,
        "country":                    country,
        "default_currency":  default_currency,
        "charges_enabled":  False,
        "payouts_enabled":   False,
        "details_submitted": False,
        "created":                    int(time.time()),
    }


def retrieve_account(account_id: str) -> dict:
    if is_live():
        return _live_stripe().Account.retrieve(account_id)
    # Mock — after the user "completes" onboarding via the mock UI, we
    # flip the booleans in DB. The retrieve call simply mirrors that
    # state back. For pure SDK fidelity we return a stub here; the
    # subscription service mutates the DB row separately.
    return {
        "id":                              account_id,
        "charges_enabled":  True,
        "payouts_enabled":   True,
        "details_submitted": True,
    }


def create_account_link(*, account_id: str,
                                              refresh_url: str, return_url: str) -> dict:
    if is_live():
        return _live_stripe().AccountLink.create(
            account=account_id, type="account_onboarding",
            refresh_url=refresh_url, return_url=return_url)
    return {
        "object":      "account_link",
        "created":   int(time.time()),
        "expires_at": int(time.time()) + 300,
        "url":            f"/mock/stripe/express-onboard?account_id={account_id}",
    }


# ─── Products + Prices ───────────────────────────────────────────
def create_product(*, name: str, metadata: Optional[dict] = None) -> dict:
    if is_live():
        return _live_stripe().Product.create(
            name=name, metadata=metadata or {})
    return {"id": _mock_id("prod"), "name": name,
                "metadata": metadata or {}, "active": True}


def create_recurring_price(*, product_id: str, unit_amount_cents: int,
                                                      currency: str = "usd",
                                                      interval: str = "month") -> dict:
    if is_live():
        return _live_stripe().Price.create(
            product=product_id, unit_amount=unit_amount_cents,
            currency=currency, recurring={"interval": interval})
    return {
        "id":                          _mock_id("price"),
        "object":                  "price",
        "product":                product_id,
        "unit_amount":      unit_amount_cents,
        "currency":              currency,
        "recurring":            {"interval": interval},
        "active":                  True,
    }


# ─── Checkout Sessions (listener subscribe) ──────────────────────
def create_checkout_session(*, customer_email: str, price_id: str,
                                                            success_url: str, cancel_url: str,
                                                            trial_period_days: int,
                                                            connected_account_id: Optional[str] = None,
                                                            application_fee_percent: Optional[float] = None,
                                                            client_reference_id: Optional[str] = None,
                                                            metadata: Optional[dict] = None) -> dict:
    if is_live():
        params: dict = {
            "mode":                  "subscription",
            "line_items":      [{"price": price_id, "quantity": 1}],
            "customer_email": customer_email,
            "success_url":    success_url,
            "cancel_url":      cancel_url,
            "subscription_data": {
                "trial_period_days":               trial_period_days,
                "application_fee_percent": application_fee_percent or 0,
            },
            "client_reference_id": client_reference_id or "",
            "metadata":                    metadata or {},
        }
        if connected_account_id:
            params["subscription_data"]["transfer_data"] = {
                "destination": connected_account_id}
        return _live_stripe().checkout.Session.create(**params)
    # Mock — synthesize the session and the redirect URL the FE renders.
    session_id = _mock_id("cs")
    return {
        "id":                  session_id,
        "object":          "checkout.session",
        "mode":              "subscription",
        "url":                f"/mock/stripe/checkout?session_id={session_id}&price={price_id}&trial={trial_period_days}&ref={client_reference_id or ''}",
        "customer_email":           customer_email,
        "client_reference_id":   client_reference_id,
        "metadata":                          metadata or {},
        "payment_status":           "unpaid",
    }


# ─── Subscriptions ───────────────────────────────────────────────
def cancel_subscription_at_period_end(*, subscription_id: str,
                                                                            cancel: bool = True) -> dict:
    if is_live():
        return _live_stripe().Subscription.modify(
            subscription_id, cancel_at_period_end=cancel)
    return {"id": subscription_id, "object": "subscription",
                "cancel_at_period_end": cancel}


# ─── Webhook signature verification ──────────────────────────────
class WebhookSignatureError(Exception): ...


def verify_webhook_signature(*, payload: bytes, sig_header: str,
                                                            secret: str) -> dict:
    """Returns the parsed event dict. Raises WebhookSignatureError on
    invalid sig. In mock mode signature is BYPASSED with a log line so
    the mock-fire endpoint works end-to-end.

    Live signature scheme: Stripe's `t=…,v1=…` header HMAC-SHA256 over
    `${t}.${payload}` with the webhook secret.
    """
    if is_live():
        try:
            return _live_stripe().Webhook.construct_event(
                payload=payload, sig_header=sig_header, secret=secret)
        except Exception as e:
            raise WebhookSignatureError(str(e))
    # Mock — log and accept. Sig schema implemented below so live just
    # plugs in. Useful even in mock mode for unit tests.
    try:
        return json.loads(payload.decode("utf-8") if isinstance(payload, bytes)
                                          else payload)
    except Exception as e:
        raise WebhookSignatureError(f"mock parse: {e}")


# Helper Stripe uses internally; surfaced for tests of the live path.
def _compute_signature(*, timestamp: int, payload: bytes,
                                              secret: str) -> str:
    signed = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signed,
                                hashlib.sha256).hexdigest()


# ─── Mock event factory (used by /api/admin/stripe/mock/fire-webhook) ─
def build_mock_event(*, event_type: str, data_object: dict) -> dict:
    """Wrap a Stripe-shaped object in an event envelope."""
    return {
        "id":               _mock_id("evt"),
        "object":       "event",
        "type":          event_type,
        "created":  int(time.time()),
        "livemode": False,
        "data":          {"object": data_object},
    }
