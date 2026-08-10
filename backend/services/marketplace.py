"""RadioLife Super Marketplace — Phase A foundation.

Economics engine (BigPoints issuance cost + category commission), business
categories, and resolver helpers shared by admin, merchant and consumer
routes.  "BigPoints" == the existing BigCoin/points ledger — this module
only governs the *merchant-side cost* of issuing them ($0.03/point default,
admin-configurable) and the platform category commission.

Collections
-----------
- marketplace_config          single doc _id='bigpoints' (kept for future flags)
- bigpoint_rates              issuance-cost rows (global/market/category/merchant)
- marketplace_categories      admin-managed category tree + capability flags
- marketplace_commission_rules commission rows (global/category/market/merchant)
- marketplace_profiles        a business's marketplace listing + onboarding
- merchant_bigpoint_accounts  per-business funding account (prepaid / auto-deduct)
- bigpoint_funding_transactions  audit ledger for prepaid top-ups / deductions
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_POINT_COST_CENTS = 3.0  # $0.03 per BigPoint issued (admin-editable)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Any) -> Optional[datetime]:
    """Coerce a (possibly Mongo-naive) datetime to tz-aware UTC."""
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ───────────────────────── Default seeds ─────────────────────────
DEFAULT_CATEGORIES: List[Dict[str, Any]] = [
    {"key": "restaurant", "name": "Restaurant / Food", "icon": "restaurant",
     "product_enabled": False, "service_enabled": False, "booking_enabled": False,
     "menu_enabled": True, "pickup_enabled": True, "shipping_enabled": False,
     "digital_enabled": False, "commission_pct": 15.0, "min_bigpoints": 50,
     "requires_approval": True},
    {"key": "retail", "name": "Retail / Ecommerce", "icon": "bag-handle",
     "product_enabled": True, "service_enabled": False, "booking_enabled": False,
     "menu_enabled": False, "pickup_enabled": True, "shipping_enabled": True,
     "digital_enabled": False, "commission_pct": 12.0, "min_bigpoints": 25,
     "requires_approval": True},
    {"key": "beauty", "name": "Beauty & Salon", "icon": "cut",
     "product_enabled": True, "service_enabled": True, "booking_enabled": True,
     "menu_enabled": False, "pickup_enabled": False, "shipping_enabled": False,
     "digital_enabled": False, "commission_pct": 15.0, "min_bigpoints": 50,
     "requires_approval": True},
    {"key": "home_services", "name": "Home Services", "icon": "home",
     "product_enabled": False, "service_enabled": True, "booking_enabled": True,
     "menu_enabled": False, "pickup_enabled": False, "shipping_enabled": False,
     "digital_enabled": False, "commission_pct": 12.0, "min_bigpoints": 50,
     "requires_approval": True},
    {"key": "professional", "name": "Professional Services", "icon": "briefcase",
     "product_enabled": False, "service_enabled": True, "booking_enabled": True,
     "menu_enabled": False, "pickup_enabled": False, "shipping_enabled": False,
     "digital_enabled": True, "commission_pct": 10.0, "min_bigpoints": 50,
     "requires_approval": True},
    {"key": "fitness", "name": "Fitness & Wellness", "icon": "barbell",
     "product_enabled": True, "service_enabled": True, "booking_enabled": True,
     "menu_enabled": False, "pickup_enabled": False, "shipping_enabled": False,
     "digital_enabled": True, "commission_pct": 12.0, "min_bigpoints": 50,
     "requires_approval": True},
    {"key": "automotive", "name": "Automotive", "icon": "car-sport",
     "product_enabled": True, "service_enabled": True, "booking_enabled": True,
     "menu_enabled": False, "pickup_enabled": False, "shipping_enabled": False,
     "digital_enabled": False, "commission_pct": 10.0, "min_bigpoints": 50,
     "requires_approval": True},
    {"key": "events", "name": "Events & Experiences", "icon": "ticket",
     "product_enabled": True, "service_enabled": False, "booking_enabled": True,
     "menu_enabled": False, "pickup_enabled": False, "shipping_enabled": False,
     "digital_enabled": True, "commission_pct": 12.0, "min_bigpoints": 50,
     "requires_approval": True},
    {"key": "other", "name": "Other", "icon": "ellipsis-horizontal",
     "product_enabled": True, "service_enabled": True, "booking_enabled": True,
     "menu_enabled": False, "pickup_enabled": True, "shipping_enabled": False,
     "digital_enabled": True, "commission_pct": 15.0, "min_bigpoints": 25,
     "requires_approval": True},
]


async def ensure_marketplace_indexes(db) -> None:
    await db.bigpoint_rates.create_index("rate_id", unique=True)
    await db.marketplace_categories.create_index("key", unique=True)
    await db.marketplace_commission_rules.create_index("rule_id", unique=True)
    await db.marketplace_profiles.create_index("business_id", unique=True)
    await db.marketplace_profiles.create_index("owner_user_id")
    await db.marketplace_profiles.create_index("status")
    await db.merchant_bigpoint_accounts.create_index("business_id", unique=True)
    await db.bigpoint_funding_transactions.create_index([("business_id", 1), ("created_at", -1)])


async def seed_marketplace_foundation(db) -> Dict[str, Any]:
    """Idempotent boot seed: default global BigPoint rate + categories +
    per-category commission rules + a global commission fallback."""
    await ensure_marketplace_indexes(db)
    summary = {"rate": "ok", "categories": 0, "commission_rules": 0}

    # 1) Global BigPoint issuance rate (default $0.03/point).
    if await db.bigpoint_rates.count_documents({"scope": "global"}) == 0:
        await db.bigpoint_rates.insert_one({
            "rate_id": "rate_global_default", "scope": "global",
            "market": None, "category": None, "merchant_id": None,
            "cost_per_point_cents": DEFAULT_POINT_COST_CENTS,
            "effective_date": now(), "active": True,
            "created_at": now(), "updated_at": now()})

    # 2) Categories + a commission rule per category.
    for c in DEFAULT_CATEGORIES:
        res = await db.marketplace_categories.update_one(
            {"key": c["key"]},
            {"$setOnInsert": {**c, "parent": None, "active": True,
                              "created_at": now(), "updated_at": now()}},
            upsert=True)
        if res.upserted_id is not None:
            summary["categories"] += 1
        rid = f"comm_cat_{c['key']}"
        cres = await db.marketplace_commission_rules.update_one(
            {"rule_id": rid},
            {"$setOnInsert": {
                "rule_id": rid, "scope": "category", "category": c["key"],
                "market": None, "merchant_id": None,
                "commission_pct": c["commission_pct"], "fixed_fee_cents": 0,
                "min_fee_cents": 0, "max_fee_cents": None,
                "effective_date": now(), "active": True,
                "created_at": now(), "updated_at": now()}},
            upsert=True)
        if cres.upserted_id is not None:
            summary["commission_rules"] += 1

    # 3) Global commission fallback.
    if await db.marketplace_commission_rules.count_documents({"scope": "global"}) == 0:
        await db.marketplace_commission_rules.insert_one({
            "rule_id": "comm_global_default", "scope": "global",
            "category": None, "market": None, "merchant_id": None,
            "commission_pct": 15.0, "fixed_fee_cents": 0,
            "min_fee_cents": 0, "max_fee_cents": None,
            "effective_date": now(), "active": True,
            "created_at": now(), "updated_at": now()})
    return summary


# ───────────────────────── Resolvers ─────────────────────────
async def resolve_point_cost_cents(db, *, market: Optional[str] = None,
                                   category: Optional[str] = None,
                                   merchant_id: Optional[str] = None) -> float:
    """Most-specific active rate wins: merchant > category > market > global."""
    n = now()
    candidates = []
    async for r in db.bigpoint_rates.find({"active": True}):
        ed = _aware(r.get("effective_date"))
        if ed and ed > n:
            continue
        candidates.append(r)
    def score(r: Dict[str, Any]) -> int:
        if r.get("scope") == "merchant" and r.get("merchant_id") == merchant_id:
            return 4
        if r.get("scope") == "category" and r.get("category") == category:
            return 3
        if r.get("scope") == "market" and r.get("market") == market:
            return 2
        if r.get("scope") == "global":
            return 1
        return 0
    scored = [(score(r), r) for r in candidates]
    scored = [(s, r) for s, r in scored if s > 0]
    if not scored:
        return DEFAULT_POINT_COST_CENTS
    scored.sort(key=lambda x: (x[0], _aware(x[1].get("effective_date")) or n), reverse=True)
    return float(scored[0][1].get("cost_per_point_cents", DEFAULT_POINT_COST_CENTS))


async def resolve_commission(db, *, market: Optional[str] = None,
                             category: Optional[str] = None,
                             merchant_id: Optional[str] = None) -> Dict[str, Any]:
    """Priority: merchant > market_category > category > market > global."""
    n = now()
    rules = []
    async for r in db.marketplace_commission_rules.find({"active": True}):
        ed = _aware(r.get("effective_date"))
        if ed and ed > n:
            continue
        rules.append(r)
    def score(r: Dict[str, Any]) -> int:
        sc = r.get("scope")
        if sc == "merchant" and r.get("merchant_id") == merchant_id:
            return 5
        if sc == "market_category" and r.get("market") == market and r.get("category") == category:
            return 4
        if sc == "category" and r.get("category") == category:
            return 3
        if sc == "market" and r.get("market") == market:
            return 2
        if sc == "global":
            return 1
        return 0
    scored = [(score(r), r) for r in rules]
    scored = [(s, r) for s, r in scored if s > 0]
    if not scored:
        return {"commission_pct": 15.0, "fixed_fee_cents": 0,
                "min_fee_cents": 0, "max_fee_cents": None, "source": "default"}
    scored.sort(key=lambda x: (x[0], _aware(x[1].get("effective_date")) or n), reverse=True)
    r = scored[0][1]
    return {"commission_pct": float(r.get("commission_pct", 15.0)),
            "fixed_fee_cents": int(r.get("fixed_fee_cents", 0)),
            "min_fee_cents": int(r.get("min_fee_cents", 0)),
            "max_fee_cents": r.get("max_fee_cents"),
            "source": r.get("scope"), "rule_id": r.get("rule_id")}


def compute_economics(*, gmv_cents: int, commissionable_cents: int,
                      points_awarded: int, point_cost_cents: float,
                      commission: Dict[str, Any],
                      processing_fee_cents: int = 0) -> Dict[str, Any]:
    """Pure calculator — commission on the commissionable subtotal only
    (not tax/tip unless caller folds them into commissionable_cents)."""
    pct = float(commission.get("commission_pct", 0))
    commission_cents = round(commissionable_cents * pct / 100.0)
    commission_cents += int(commission.get("fixed_fee_cents", 0))
    mn = int(commission.get("min_fee_cents", 0))
    mx = commission.get("max_fee_cents")
    if commission_cents < mn:
        commission_cents = mn
    if mx is not None and commission_cents > int(mx):
        commission_cents = int(mx)
    bigpoints_fee_cents = round(points_awarded * float(point_cost_cents))
    merchant_net_cents = gmv_cents - commission_cents - bigpoints_fee_cents - int(processing_fee_cents)
    return {
        "gmv_cents": gmv_cents,
        "commission_cents": commission_cents,
        "commission_pct": pct,
        "bigpoints_fee_cents": bigpoints_fee_cents,
        "points_awarded": points_awarded,
        "point_cost_cents": point_cost_cents,
        "processing_fee_cents": int(processing_fee_cents),
        "merchant_net_cents": merchant_net_cents,
    }


__all__ = [
    "DEFAULT_POINT_COST_CENTS", "now", "new_id",
    "ensure_marketplace_indexes", "seed_marketplace_foundation",
    "resolve_point_cost_cents", "resolve_commission", "compute_economics",
]
