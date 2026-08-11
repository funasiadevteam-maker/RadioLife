"""Saved Cards (Phase 2 Checkout) — shared Stripe helpers.

One Stripe Customer per app user (reusing subscription.stripe_customer_id so
billing + marketplace share the same customer). Cards are collected via a
hosted Stripe Checkout Session in `setup` mode (works on both web + Expo
without native modules) and charged off-session for one-tap checkout.

Services never import routes, so both marketplace_orders and
marketplace_products can import these helpers with no circular dependency.
"""
from __future__ import annotations

import os

import stripe


def _cfg() -> None:
    stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                      or os.environ.get("STRIPE_API_KEY") or "")


def _is_real_customer(cust_id: str | None) -> bool:
    return bool(cust_id and cust_id.startswith("cus_")
                and not cust_id.startswith("cus_test_"))


async def ensure_stripe_customer(db, user: dict) -> str:
    """Return a real Stripe customer id for this user, creating one on demand.
    Reuses subscription.stripe_customer_id (shared with billing)."""
    sub = user.get("subscription") or {}
    cust_id = sub.get("stripe_customer_id")
    if _is_real_customer(cust_id):
        return cust_id
    # user dict may be stale — re-read from DB.
    doc = await db.users.find_one(
        {"user_id": user["user_id"]}, {"subscription.stripe_customer_id": 1})
    cust_id = ((doc or {}).get("subscription") or {}).get("stripe_customer_id")
    if _is_real_customer(cust_id):
        return cust_id
    _cfg()
    customer = stripe.Customer.create(
        email=user.get("email"), name=user.get("name"),
        metadata={"user_id": user["user_id"], "source": "radiolife_wallet"})
    cust_id = customer.id
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"subscription.stripe_customer_id": cust_id}})
    return cust_id


def list_cards(cust_id: str) -> dict:
    """Return saved cards for a customer + the default payment-method id."""
    _cfg()
    cust = stripe.Customer.retrieve(cust_id)
    inv = cust.get("invoice_settings") or {}
    default_pm = inv.get("default_payment_method")
    pms = stripe.PaymentMethod.list(customer=cust_id, type="card")
    cards = []
    for pm in pms.data:
        c = pm.card
        cards.append({
            "id": pm.id, "brand": c.brand, "last4": c.last4,
            "exp_month": c.exp_month, "exp_year": c.exp_year,
            "is_default": pm.id == default_pm,
        })
    # default first, then most-recently-added
    cards.sort(key=lambda x: (not x["is_default"]))
    return {"cards": cards, "default_id": default_pm}


def charge_saved_card(*, amount_cents: int, cust_id: str, pm_id: str,
                      metadata: dict | None = None):
    """Off-session PaymentIntent for one-tap checkout. Raises
    stripe.error.CardError when the card needs authentication / declines."""
    _cfg()
    return stripe.PaymentIntent.create(
        amount=int(amount_cents), currency="usd", customer=cust_id,
        payment_method=pm_id, off_session=True, confirm=True,
        metadata=metadata or {})


def owns_payment_method(cust_id: str, pm_id: str) -> bool:
    _cfg()
    try:
        pm = stripe.PaymentMethod.retrieve(pm_id)
    except stripe.error.StripeError:
        return False
    return pm.get("customer") == cust_id


__all__ = ["ensure_stripe_customer", "list_cards", "charge_saved_card",
           "owns_payment_method"]
