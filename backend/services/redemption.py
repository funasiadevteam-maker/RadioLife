"""Phase 5 — Atomic redemption with type-specific fulfillment."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta

from services.bigcoin import spend

logger = logging.getLogger("bigfm.redemption")


async def redeem_reward(db, user: dict, reward_id: str) -> dict:
    """Atomically: validate, deduct BC, decrement stock, write redemption,
    fulfill by type. Returns the redemption doc."""
    now = datetime.now(timezone.utc)
    reward = await db.bigcoin_rewards.find_one({"_id": reward_id})
    if not reward:
        raise ValueError("reward not found")
    if not reward.get("active", True):
        raise ValueError("reward inactive")
    if reward.get("expires_at") and reward["expires_at"] < now:
        raise ValueError("reward expired")
    cost = int(reward["cost_bigcoin"])

    # Atomic stock decrement (if limit set)
    stock_limit = reward.get("stock_limit")
    if stock_limit is not None:
        res = await db.bigcoin_rewards.update_one(
            {"_id": reward_id, "active": True,
             "$expr": {"$lt": ["$redeemed_count", "$stock_limit"]}},
            {"$inc": {"redeemed_count": 1}},
        )
        if res.modified_count == 0:
            raise ValueError("reward sold out")

    # Atomic balance deduct (will rollback stock on failure)
    try:
        spend_res = await spend(db, user["user_id"], cost,
                                  "redemption",
                                  metadata={"reward_id": reward_id,
                                            "reward_name": reward.get("name")})
    except ValueError as e:
        # Roll back the stock decrement
        if stock_limit is not None:
            await db.bigcoin_rewards.update_one(
                {"_id": reward_id}, {"$inc": {"redeemed_count": -1}},
            )
        raise

    redemption_id = f"rdm_{uuid.uuid4().hex[:14]}"
    fulfillment = await _fulfill(db, user, reward, redemption_id, now)
    await db.bigcoin_redemptions.insert_one({
        "_id": redemption_id, "user_id": user["user_id"],
        "reward_id": reward_id, "reward_name": reward.get("name"),
        "reward_type": reward.get("type"),
        "cost_paid": cost,
        "balance_after": spend_res["balance_after"],
        "status": "fulfilled",
        "fulfillment_data_json": fulfillment,
        "redeemed_at": now, "fulfilled_at": now,
    })
    return {
        "redemption_id": redemption_id,
        "reward_id": reward_id,
        "reward_name": reward.get("name"),
        "type": reward.get("type"),
        "cost_paid": cost,
        "balance_after": spend_res["balance_after"],
        "fulfillment": fulfillment,
    }


async def _fulfill(db, user: dict, reward: dict, redemption_id: str,
                     now: datetime) -> dict:
    """Type-specific fulfillment. Returns metadata stored in the redemption."""
    rtype = reward.get("type")
    payload = reward.get("payload_json") or {}
    uid = user["user_id"]

    if rtype == "premium_days":
        days = int(payload.get("days") or 30)
        # Extend premium_until OR set is_premium for free users
        cur_until = user.get("premium_until")
        is_premium = bool(user.get("is_premium"))
        if cur_until and cur_until > now:
            new_until = cur_until + timedelta(days=days)
        else:
            new_until = now + timedelta(days=days)
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {
                "is_premium": True,
                "premium_until": new_until,
                "premium_tier": user.get("premium_tier") or "premium",
                "subscription.complimentary_extension_redemption_id": redemption_id,
            }},
        )
        return {"premium_extended_until": new_until.isoformat(),
                "days_granted": days,
                "was_premium_before": is_premium}

    if rtype == "adfree_hour":
        hours = int(payload.get("hours") or 1)
        cur = user.get("adfree_until")
        base = max(cur, now) if (cur and cur > now) else now
        new_until = base + timedelta(hours=hours)
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {"adfree_until": new_until}},
        )
        return {"adfree_until": new_until.isoformat(), "hours_granted": hours}

    if rtype == "partner_voucher":
        wid = f"wi_{uuid.uuid4().hex[:14]}"
        await db.user_wallet_items.insert_one({
            "_id": wid, "user_id": uid, "item_type": "voucher",
            "source_redemption_id": redemption_id,
            "title": reward.get("name"),
            "partner_business_id": reward.get("partner_business_id"),
            "payload": payload, "code": f"BFM-{uuid.uuid4().hex[:8].upper()}",
            "status": "active", "expires_at": now + timedelta(days=60),
            "created_at": now,
        })
        return {"wallet_item_id": wid, "merchant": payload.get("merchant")}

    if rtype == "raffle":
        rid = f"raffle_entry_{uuid.uuid4().hex[:14]}"
        await db.raffle_entries.insert_one({
            "_id": rid, "user_id": uid, "raffle_id": payload.get("raffle_id"),
            "redemption_id": redemption_id, "entered_at": now,
        })
        return {"raffle_entry_id": rid, "raffle_id": payload.get("raffle_id")}

    if rtype == "coupon":
        wid = f"wi_{uuid.uuid4().hex[:14]}"
        await db.user_wallet_items.insert_one({
            "_id": wid, "user_id": uid, "item_type": "coupon",
            "source_redemption_id": redemption_id,
            "title": reward.get("name"),
            "code": f"BFM-{uuid.uuid4().hex[:8].upper()}",
            "payload": payload, "status": "active",
            "expires_at": now + timedelta(days=90), "created_at": now,
        })
        return {"wallet_item_id": wid}

    if rtype == "badge":
        slug = payload.get("badge_slug")
        if slug:
            badge = await db.badges.find_one({"slug": slug})
            if badge:
                try:
                    await db.user_badges.insert_one({
                        "user_id": uid, "badge_id": badge["_id"],
                        "unlocked_at": now, "displayed_on_profile": True,
                        "source_redemption_id": redemption_id,
                    })
                except Exception:
                    pass
                return {"badge_id": badge["_id"], "badge_slug": slug}
        return {"error": "badge not found"}

    return {"unknown_type": rtype}
