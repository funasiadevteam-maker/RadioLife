"""Stripe pricing plan registry + checkout session builder.

Phase 3 uses Stripe Checkout (one-time annual passes) via the
`emergentintegrations` library — not native Stripe subscription mode.
We still call them "annual subscriptions" in product copy, but on the
Stripe side they are single payments. Subscription state is tracked in
Mongo (`users.subscription`) — when the payment succeeds we set
`current_period_end = now + 365 days`. This is intentional for Phase 3
to stay compatible with the platform's managed Stripe key.

At server start `stripe_setup_bootstrap()` is called. With the managed
key, no real Products/Prices need to be created in Stripe — we expose
in-code "plans" and create per-request Checkout Sessions with the
correct amount + currency. The structure is identical to a real
Stripe Products/Prices model so a future flip is trivial.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from core.config import STRIPE_API_KEY, STRIPE_MODE

logger = logging.getLogger("bigfm.stripe_setup")


# In-code "products + prices" registry. The plan_id is what the frontend
# passes to /api/billing/checkout. Currency-specific amount.
PRICING_PLANS: Dict[str, Dict] = {
    "premium_annual": {
        "name": "FUUSIC Premium",
        "description": "6 skips/hour · 2 VIP channels · Ad-free · VIP badge · 2× rewards",
        "interval": "annual",
        "tier": "premium",
        "is_premium": True,
        "features": [
            "6 skips every hour (vs 1 on Free)",
            "2 exclusive VIP channels: VIP Lounge + Premium Mehfil",
            "Ad-free listening (no breaks for promos)",
            "VIP Badge on your avatar + profile",
            "2× Rewards Multiplier (Phase 4+)",
        ],
        "prices_by_currency": {
            # Amounts are MAJOR units (dollars / dirhams / rupees) as floats.
            "USD": {"amount": 12.00, "display": "$12"},
            "AED": {"amount": 36.00, "display": "AED 36"},
            "INR": {"amount": 999.00, "display": "₹999"},
        },
    },
}

DEFAULT_PLAN_ID = "premium_annual"


def get_plan(plan_id: str) -> Optional[Dict]:
    return PRICING_PLANS.get(plan_id)


def get_price_for_currency(plan_id: str, currency: str) -> Dict:
    """Returns {amount: float, currency: str, display: str} or raises ValueError."""
    plan = PRICING_PLANS.get(plan_id)
    if not plan:
        raise ValueError(f"unknown plan_id {plan_id}")
    cur = currency.upper()
    prices = plan.get("prices_by_currency", {})
    if cur not in prices:
        cur = "USD"
    p = prices[cur]
    return {"amount": float(p["amount"]), "currency": cur, "display": p["display"]}


def list_plans_for_currency(currency: str) -> List[Dict]:
    """Render the catalog for the /api/billing/pricing endpoint."""
    out: List[Dict] = []
    for plan_id, plan in PRICING_PLANS.items():
        price = get_price_for_currency(plan_id, currency)
        out.append({
            "plan_id": plan_id,
            "name": plan["name"],
            "description": plan["description"],
            "currency": price["currency"],
            "amount": price["amount"],
            "amount_display": price["display"],
            "interval": plan["interval"],
            "features": plan["features"],
            "is_premium": plan["is_premium"],
        })
    return out


def stripe_setup_bootstrap() -> None:
    """Called once at server startup. With Emergent-managed Stripe key,
    products/prices are NOT created in the Stripe account — they live in
    this module's PRICING_PLANS dict and are referenced per-checkout.

    If you flip to a self-managed Stripe account later, this is the place
    to call `stripe.Product.create` and `stripe.Price.create` idempotently.
    """
    plan_count = len(PRICING_PLANS)
    cur_count = sum(len(p["prices_by_currency"]) for p in PRICING_PLANS.values())
    logger.info(
        "Stripe pricing plans bootstrapped: %d plans × %d currencies (mode=%s, key=%s)",
        plan_count, cur_count // max(plan_count, 1), STRIPE_MODE,
        STRIPE_API_KEY[:18] + "…" if STRIPE_API_KEY else "unset",
    )
