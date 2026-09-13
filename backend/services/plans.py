"""Phase 6 — Plan catalog.

The single source of truth for what's sellable. We persist these into a
`plans` Mongo collection on boot so admin tooling can read/list them,
but the in-code dict is authoritative for pricing math.

Pricing strategy:
- premium_monthly: USD $4.99, AED 18, INR 399 (~$0.99 USD-equivalent values)
- premium_annual:  USD $47.88 (12× $3.99 = ~20% off vs monthly), AED 175, INR 3,999
- premium_family:  USD $9.99/mo, AED 36/mo, INR 799/mo — 5 seats
- venue_business:  scaffolded only — checkout disabled

`tier_rank` is used by /api/billing/change_plan to determine
upgrade-vs-downgrade direction. Higher rank = "better" plan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional


PLAN_CATALOG: Dict[str, Dict] = {
    "free": {
        "slug": "free", "display_name": "Free",
        "interval": "none", "tier_rank": 0, "tier": "free",
        "active": True, "is_premium": False, "trial_days": 0,
        "purchasable": False, "stripe_billable": False,
        "family_seats": 0,
        "prices_by_currency": {
            "USD": {"amount": 0.00, "display": "Free"},
            "AED": {"amount": 0.00, "display": "Free"},
            "INR": {"amount": 0.00, "display": "Free"},
        },
        "features_json": {
            "max_skips_per_hour": 1, "ad_free": False,
            "premium_voices": False, "premium_channels": 0,
            "family_seats": 0, "reward_multiplier": 1.0,
            "bigcoin_2x_weekends": False,
        },
        "description": "Personalized AI radio with ads. 1 skip per hour.",
    },
    "premium_monthly": {
        "slug": "premium_monthly", "display_name": "Premium Monthly",
        "interval": "monthly", "interval_days": 30,
        "tier_rank": 10, "tier": "premium",
        "active": True, "is_premium": True, "trial_days": 7,
        "purchasable": True, "stripe_billable": True,
        "family_seats": 1,
        "prices_by_currency": {
            "USD": {"amount": 4.99,  "display": "$4.99 / mo"},
            "AED": {"amount": 18.00, "display": "AED 18 / mo"},
            "INR": {"amount": 399.00, "display": "₹399 / mo"},
        },
        "features_json": {
            "max_skips_per_hour": 6, "ad_free": True,
            "premium_voices": True, "premium_channels": 2,
            "family_seats": 1, "reward_multiplier": 2.0,
            "bigcoin_2x_weekends": True,
        },
        "description": "6 skips/hour · Ad-free · 2 VIP channels · 2× BigCoin weekends.",
    },
    "premium_annual": {
        "slug": "premium_annual", "display_name": "Premium Annual",
        "interval": "annual", "interval_days": 365,
        "tier_rank": 20, "tier": "premium",
        "active": True, "is_premium": True, "trial_days": 7,
        "purchasable": True, "stripe_billable": True,
        "family_seats": 1,
        "savings_vs_monthly_pct": 20,
        "prices_by_currency": {
            "USD": {"amount": 47.88,   "display": "$47.88 / yr ($3.99/mo)"},
            "AED": {"amount": 175.00,  "display": "AED 175 / yr"},
            "INR": {"amount": 3999.00, "display": "₹3,999 / yr"},
        },
        "features_json": {
            "max_skips_per_hour": 6, "ad_free": True,
            "premium_voices": True, "premium_channels": 2,
            "family_seats": 1, "reward_multiplier": 2.0,
            "bigcoin_2x_weekends": True,
        },
        "description": "Save 20% vs monthly. Same Premium perks for 12 months.",
    },
    "premium_family": {
        "slug": "premium_family", "display_name": "Premium Family",
        "interval": "monthly", "interval_days": 30,
        "tier_rank": 30, "tier": "premium",
        "active": True, "is_premium": True, "trial_days": 7,
        "purchasable": True, "stripe_billable": True,
        "family_seats": 5,
        "prices_by_currency": {
            "USD": {"amount": 9.99,   "display": "$9.99 / mo"},
            "AED": {"amount": 36.00,  "display": "AED 36 / mo"},
            "INR": {"amount": 799.00, "display": "₹799 / mo"},
        },
        "features_json": {
            "max_skips_per_hour": 6, "ad_free": True,
            "premium_voices": True, "premium_channels": 2,
            "family_seats": 5, "reward_multiplier": 2.0,
            "bigcoin_2x_weekends": True,
        },
        "description": "Up to 5 family seats · All Premium perks · One bill.",
    },
    "venue_business": {
        "slug": "venue_business", "display_name": "Venue / Business",
        "interval": "monthly", "interval_days": 30,
        "tier_rank": 100, "tier": "business",
        # B2B is scaffolded — DO NOT enable purchases yet.
        "active": False, "is_premium": True, "trial_days": 14,
        "purchasable": False, "stripe_billable": False,
        "family_seats": 0,
        "prices_by_currency": {
            "USD": {"amount": 99.00, "display": "Contact sales"},
            "AED": {"amount": 365.00, "display": "Contact sales"},
            "INR": {"amount": 8999.00, "display": "Contact sales"},
        },
        "features_json": {
            "max_skips_per_hour": 6, "ad_free": True,
            "premium_voices": True, "premium_channels": 0,
            "family_seats": 0, "reward_multiplier": 2.0,
            "venue_branded_channel": True, "venue_playlist_control": True,
        },
        "description": "For restaurants, salons, and venues. Coming Q3 2026.",
    },
}


def get_plan(slug: str) -> Optional[Dict]:
    return PLAN_CATALOG.get(slug)


def get_price(slug: str, currency: str) -> Dict:
    plan = PLAN_CATALOG.get(slug)
    if not plan:
        raise ValueError(f"unknown plan slug {slug}")
    cur = currency.upper()
    prices = plan.get("prices_by_currency", {})
    if cur not in prices: cur = "USD"
    p = prices[cur]
    return {"amount": float(p["amount"]), "currency": cur,
            "display": p["display"]}


def list_plans_for_currency(currency: str) -> List[Dict]:
    out = []
    for slug, plan in PLAN_CATALOG.items():
        if not plan.get("active"): continue
        price = get_price(slug, currency)
        out.append({
            "slug": slug,
            "display_name": plan["display_name"],
            "description": plan.get("description"),
            "tier": plan.get("tier"),
            "tier_rank": plan["tier_rank"],
            "interval": plan["interval"],
            "interval_days": plan.get("interval_days"),
            "currency": price["currency"],
            "amount": price["amount"],
            "amount_display": price["display"],
            "is_premium": plan["is_premium"],
            "purchasable": plan.get("purchasable", False),
            "stripe_billable": plan.get("stripe_billable", False),
            "trial_days": plan.get("trial_days", 0),
            "family_seats": plan.get("family_seats", 0),
            "features": plan.get("features_json", {}),
            "savings_vs_monthly_pct": plan.get("savings_vs_monthly_pct"),
        })
    out.sort(key=lambda p: p["tier_rank"])
    return out


def compare_tiers(from_slug: str, to_slug: str) -> str:
    """Returns 'upgrade', 'downgrade', or 'same'."""
    a = get_plan(from_slug)
    b = get_plan(to_slug)
    if not a or not b: raise ValueError("unknown plan")
    if b["tier_rank"] > a["tier_rank"]: return "upgrade"
    if b["tier_rank"] < a["tier_rank"]: return "downgrade"
    return "same"


async def seed_plans(db) -> int:
    """Idempotent seed of the `plans` collection. Returns number created."""
    now = datetime.now(timezone.utc)
    created = 0
    for slug, plan in PLAN_CATALOG.items():
        res = await db.plans.update_one(
            {"_id": slug},
            {"$set": {
                "_id": slug,
                **{k: v for k, v in plan.items() if k != "_id"},
                "updated_at": now,
            },
             "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        if res.upserted_id is not None:
            created += 1
    return created
