"""Marketplace merchant coupons — self-serve discount codes.

A shop owner creates discount codes (percent-off or fixed amount-off) for
their OWN storefront. Shoppers apply a code at checkout; the discount reduces
the order subtotal and is absorbed by the merchant (their net drops). This is
entirely self-funded and NEVER touches the sponsored-CPA ad engine, so
advertiser revenue splits are unaffected.

Discount stacking order at checkout: coupon → gift card → BigPoints → card.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from services.marketplace import now, new_id


def norm_code(code: Optional[str]) -> str:
    return (code or "").strip().upper()


def _aware(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def ensure_coupon_indexes(db) -> None:
    await db.marketplace_coupons.create_index("coupon_id", unique=True)
    await db.marketplace_coupons.create_index([("business_id", 1), ("code", 1)], unique=True)
    await db.marketplace_coupon_redemptions.create_index([("coupon_id", 1), ("user_id", 1)])
    await db.marketplace_coupon_redemptions.create_index([("order_id", 1), ("coupon_id", 1)], unique=True)


async def compute_coupon_discount(db, *, business_id: str, code: Optional[str],
                                  user_id: str, base_cents: int
                                  ) -> Tuple[int, Optional[Dict[str, Any]], Optional[str]]:
    """Validate a code against a subtotal. Returns
    (discount_cents, coupon_doc_or_None, error_code_or_None). Read-only."""
    code = norm_code(code)
    if not code:
        return 0, None, None
    c = await db.marketplace_coupons.find_one({"business_id": business_id, "code": code})
    if not c or not c.get("active", True):
        return 0, None, "invalid_coupon"
    n = datetime.now(timezone.utc)
    st, ex = _aware(c.get("starts_at")), _aware(c.get("expires_at"))
    if st and n < st:
        return 0, c, "not_started"
    if ex and n > ex:
        return 0, c, "expired"
    if int(base_cents) < int(c.get("min_spend_cents", 0) or 0):
        return 0, c, "min_spend_not_met"
    limit = c.get("usage_limit")
    if limit is not None and int(c.get("used_count", 0)) >= int(limit):
        return 0, c, "usage_exceeded"
    per_user = int(c.get("per_user_limit", 1) or 0)
    if per_user > 0:
        used = await db.marketplace_coupon_redemptions.count_documents(
            {"coupon_id": c["coupon_id"], "user_id": user_id})
        if used >= per_user:
            return 0, c, "already_used"
    if c.get("type") == "percent":
        disc = int(base_cents) * int(c.get("value", 0) or 0) // 100
        maxd = int(c.get("max_discount_cents") or 0)
        if maxd > 0:
            disc = min(disc, maxd)
    else:
        disc = int(c.get("value", 0) or 0)
    disc = max(0, min(disc, int(base_cents)))
    return disc, c, None


async def record_coupon_redemption(db, *, coupon: Optional[Dict[str, Any]], user_id: str,
                                   order_id: str, discount_cents: int) -> None:
    """Idempotent per (order, coupon) — increments used_count exactly once."""
    if not coupon or int(discount_cents or 0) <= 0:
        return
    try:
        await db.marketplace_coupon_redemptions.insert_one({
            "redemption_id": new_id("mcr"), "coupon_id": coupon["coupon_id"],
            "business_id": coupon["business_id"], "code": coupon["code"],
            "user_id": user_id, "order_id": order_id,
            "discount_cents": int(discount_cents), "created_at": now()})
    except Exception:
        return  # duplicate → already recorded
    await db.marketplace_coupons.update_one(
        {"coupon_id": coupon["coupon_id"]}, {"$inc": {"used_count": 1}})


def serialize_coupon(c: Dict[str, Any]) -> Dict[str, Any]:
    c = dict(c)
    c.pop("_id", None)
    for k in ("created_at", "updated_at", "starts_at", "expires_at"):
        v = c.get(k)
        if hasattr(v, "isoformat"):
            c[k] = v.isoformat()
    return c


__all__ = ["norm_code", "ensure_coupon_indexes", "compute_coupon_discount",
           "record_coupon_redemption", "serialize_coupon"]
