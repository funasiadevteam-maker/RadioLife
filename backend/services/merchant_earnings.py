"""Merchant earnings ledger (auto-deduct model).

When a consumer membership activates, the platform collects the full payment and
we record one ledger row: gross, the platform fee (from the category commission
engine, admin-overridable), and the merchant's net. The merchant Earnings
dashboard reads these rows. Real bank payouts happen out-of-band (no Stripe
Connect split until a merchant connects an account)."""
from typing import Any, Dict

from services.marketplace import now, new_id
from services.commission_service import calculate_platform_fee


def _period(dt=None) -> str:
    return (dt or now()).strftime("%Y-%m")


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    v = d.get("created_at")
    if hasattr(v, "isoformat"):
        d["created_at"] = v.isoformat()
    return d


async def record_membership_earning(db, m: Dict[str, Any]) -> None:
    """Idempotent per membership — records gross/fee/net for one membership sale."""
    mid = m.get("membership_id")
    if not mid or await db.merchant_earnings.find_one({"membership_id": mid}):
        return
    bid = m.get("business_id")
    price = m.get("price_cents")
    if price is None:
        plan = await db.membership_plans.find_one({"plan_id": m.get("plan_id")})
        price = int((plan or {}).get("price_cents") or 0)
    prof = await db.marketplace_profiles.find_one({"business_id": bid}, {"category": 1})
    category = (prof or {}).get("category") or "other"
    fee = await calculate_platform_fee(
        db, merchant_id=bid, category=category,
        transaction_type="membership", amount_cents=int(price), write_audit=False)
    await db.merchant_earnings.insert_one({
        "earning_id": new_id("earn"), "business_id": bid, "membership_id": mid,
        "plan_id": m.get("plan_id"), "plan_name": m.get("plan_name"),
        "buyer_user_id": m.get("buyer_user_id") or m.get("user_id"),
        "transaction_type": "membership",
        "gross_cents": int(price),
        "fee_pct": float(fee["computed_percent"]),
        "fee_cents": int(fee["commission_cents"]),
        "net_cents": int(fee["merchant_net_cents"]),
        "period": _period(), "created_at": now(),
    })


async def earnings_summary(db, business_id: str) -> Dict[str, Any]:
    rows = [r async for r in db.merchant_earnings.find(
        {"business_id": business_id}).sort("created_at", -1)]
    month = _period()
    m_rows = [r for r in rows if r.get("period") == month]

    def _sum(items, key):
        return sum(int(r.get(key, 0)) for r in items)

    return {
        "memberships_sold": len(rows),
        "gross_cents": _sum(rows, "gross_cents"),
        "fee_cents": _sum(rows, "fee_cents"),
        "net_cents": _sum(rows, "net_cents"),
        "month": {
            "count": len(m_rows),
            "gross_cents": _sum(m_rows, "gross_cents"),
            "fee_cents": _sum(m_rows, "fee_cents"),
            "net_cents": _sum(m_rows, "net_cents"),
        },
        "transactions": [_clean(dict(r)) for r in rows[:25]],
    }
