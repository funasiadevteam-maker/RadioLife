"""Phase 42-D2 — Public voucher redemption.

  • POST /api/subscriptions/redeem-voucher  { code }

Validates the voucher, blocks reuse per-user, increments
`redemptions_count`, and stamps the same fields a direct admin grant
would (so the existing premium-gate helpers keep working).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user

log = logging.getLogger("bigfm.subscription_voucher")
router = APIRouter(prefix="/api/subscriptions",
                                    tags=["subscriptions-voucher"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RedeemIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=32)


@router.post("/redeem-voucher")
async def redeem_voucher(payload: RedeemIn, request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    code = payload.code.strip().upper()
    voucher = await db.vouchers.find_one({"code": code})
    if not voucher:
        raise HTTPException(404, {"code": "voucher_not_found"})
    if not voucher.get("active", True):
        raise HTTPException(410, {"code": "voucher_revoked"})
    now = _now()
    expires_at = voucher.get("expires_at")
    if expires_at and expires_at < now:
        raise HTTPException(410, {"code": "voucher_expired"})
    if voucher.get("redemptions_count", 0) >= voucher.get("max_redemptions", 1):
        raise HTTPException(410, {"code": "voucher_exhausted"})

    # Per-user reuse guard (unique index `uniq_voucher_user` enforces).
    already = await db.voucher_redemptions.find_one({
        "voucher_id": voucher["voucher_id"], "user_id": user["user_id"]})
    if already:
        raise HTTPException(409, {"code": "voucher_already_redeemed",
                                                                    "redemption_id": already["redemption_id"]})

    plan = voucher["plan"]
    days = int(voucher["duration_days"])
    expires_at_new = now + timedelta(days=days)
    update_set = {
        "subscription_status": plan,
        "tier": plan,
        "is_premium": True,
        "premium_until": expires_at_new,
        "updated_at": now,
    }
    if plan == "trial":
        update_set.update({"trial_started_at": now,
                                              "trial_ends_at": expires_at_new})
    await db.users.update_one({"user_id": user["user_id"]},
                                                          {"$set": update_set})

    # Record redemption + increment voucher counter.
    rid = f"red_{uuid.uuid4().hex[:14]}"
    try:
        await db.voucher_redemptions.insert_one({
            "_id": rid, "redemption_id": rid,
            "voucher_id": voucher["voucher_id"],
            "voucher_code": code,
            "user_id": user["user_id"],
            "user_email": user.get("email"),
            "plan": plan, "duration_days": days,
            "expires_at": expires_at_new,
            "redeemed_at": now,
        })
    except Exception as e:
        # Unique-index race — somebody else just redeemed it.
        log.info("[voucher-redeem] race for code=%s user=%s: %s",
                          code, user["user_id"], e)
        raise HTTPException(409, {"code": "voucher_already_redeemed"})
    await db.vouchers.update_one(
        {"voucher_id": voucher["voucher_id"]},
        {"$inc": {"redemptions_count": 1},
          "$set": {"updated_at": now}})
    log.info("[voucher-redeem] code=%s plan=%s user=%s days=%s",
                      code, plan, user["user_id"], days)
    return {"ok": True, "redemption_id": rid,
                  "plan": plan, "duration_days": days,
                  "expires_at": expires_at_new.isoformat()}
