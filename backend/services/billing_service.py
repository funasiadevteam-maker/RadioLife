"""Subscription state mutations + payment_transactions ledger writes."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.db import db
from services.stripe_setup import PRICING_PLANS, get_plan

logger = logging.getLogger("bigfm.billing")

ANNUAL_PERIOD_DAYS = 365


async def ensure_billing_indexes() -> None:
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.payment_transactions.create_index([("user_id", 1), ("created_at", -1)])
    await db.payment_transactions.create_index("payment_status")


async def record_pending_transaction(
    *, session_id: str, user_id: str, user_email: str, plan_id: str,
    amount: float, currency: str, metadata: Optional[dict] = None,
) -> None:
    now = datetime.now(timezone.utc)
    doc = {
        "session_id": session_id,
        "user_id": user_id,
        "user_email": user_email,
        "plan_id": plan_id,
        "amount": amount,
        "currency": currency,
        "status": "pending",
        "payment_status": "pending",
        "metadata": metadata or {},
        "created_at": now,
        "updated_at": now,
    }
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$setOnInsert": doc},
        upsert=True,
    )


async def get_transaction(session_id: str) -> Optional[dict]:
    return await db.payment_transactions.find_one({"session_id": session_id})


async def mark_transaction_complete(
    session_id: str, *, payment_status: str, amount_total: float, currency: str,
) -> bool:
    """Idempotent: returns True if this call flipped the status. Returns
    False if the row was already finalized (prevents double-grant)."""
    now = datetime.now(timezone.utc)
    res = await db.payment_transactions.update_one(
        {"session_id": session_id, "status": {"$ne": "complete"}},
        {"$set": {
            "status": "complete",
            "payment_status": payment_status,
            "amount_total": amount_total,
            "currency": currency,
            "completed_at": now,
            "updated_at": now,
        }},
    )
    return res.modified_count == 1


async def mark_transaction_expired(session_id: str) -> None:
    now = datetime.now(timezone.utc)
    await db.payment_transactions.update_one(
        {"session_id": session_id, "status": {"$ne": "complete"}},
        {"$set": {
            "status": "expired",
            "payment_status": "expired",
            "updated_at": now,
        }},
    )


async def grant_premium(user_id: str, plan_id: str, currency: str, *,
                        stripe_session_id: Optional[str] = None,
                        days: int = ANNUAL_PERIOD_DAYS) -> None:
    """Idempotent: grants premium for `days` from now. If the user is
    already premium, extends the existing period_end by `days`."""
    plan = get_plan(plan_id) or PRICING_PLANS["premium_annual"]
    now = datetime.now(timezone.utc)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        logger.warning(f"grant_premium: user_id {user_id} not found")
        return
    existing = user.get("subscription") or {}
    existing_end = existing.get("current_period_end")
    if isinstance(existing_end, str):
        try:
            existing_end = datetime.fromisoformat(existing_end)
        except Exception:
            existing_end = None
    if existing_end and existing_end > now and existing.get("status") == "active":
        new_end = existing_end + timedelta(days=days)
    else:
        new_end = now + timedelta(days=days)
    sub = {
        "stripe_session_id": stripe_session_id,
        "stripe_subscription_id": existing.get("stripe_subscription_id") or stripe_session_id,
        "stripe_customer_id": existing.get("stripe_customer_id") or f"cus_test_{user_id[:12]}",
        "status": "active",
        "plan": plan_id,
        "currency": currency,
        "current_period_start": now,
        "current_period_end": new_end,
        "trial_end": None,
        "cancel_at_period_end": False,
    }
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "subscription": sub,
            "is_premium": True,
            "premium_tier": plan.get("tier") or "premium",
            "reward_multiplier": 2.0,
        }},
    )
    logger.info(f"Granted premium to {user_id} until {new_end.isoformat()}")


async def revoke_premium(user_id: str, *, immediate: bool = False) -> None:
    """If immediate=True, kills the period right away. Otherwise marks
    cancel_at_period_end=True and lets them keep premium until end date."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return
    if immediate:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "is_premium": False,
                "premium_tier": None,
                "reward_multiplier": 1.0,
                "subscription.status": "canceled",
                "subscription.cancel_at_period_end": True,
            }},
        )
    else:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"subscription.cancel_at_period_end": True}},
        )


async def expire_lapsed_subscriptions() -> int:
    """Sweep job: flip is_premium to False for any user whose period_end is past."""
    now = datetime.now(timezone.utc)
    cur = db.users.find(
        {"is_premium": True, "subscription.current_period_end": {"$lt": now}},
        {"user_id": 1, "_id": 0},
    )
    count = 0
    async for u in cur:
        await db.users.update_one(
            {"user_id": u["user_id"]},
            {"$set": {
                "is_premium": False,
                "premium_tier": None,
                "reward_multiplier": 1.0,
                "subscription.status": "expired",
            }},
        )
        count += 1
    if count:
        logger.info(f"Expired {count} lapsed premium subscriptions")
    return count


def serialize_subscription(user: dict) -> dict:
    sub = user.get("subscription") or {}
    return {
        "is_premium": bool(user.get("is_premium", False)),
        "premium_tier": user.get("premium_tier"),
        "plan": sub.get("plan"),
        "currency": sub.get("currency"),
        "status": sub.get("status"),
        "current_period_start": sub.get("current_period_start"),
        "current_period_end": sub.get("current_period_end"),
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end", False)),
        "reward_multiplier": float(user.get("reward_multiplier", 1.0)),
    }
