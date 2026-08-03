"""Phase 39 Session 3 — Premium trial lifecycle endpoints.

  • POST /api/billing/start_premium_trial — start a 7-day trial.
      Anti-abuse: at most one trial per 365 days (server-clock checked).
  • POST /api/billing/end_trial — idempotent.  Flips subscription_status
      from 'trial' to 'free' iff trial_ends_at is in the past.
  • GET  /api/billing/trial_status — returns the current trial state +
      seconds remaining (for the UI countdown badge).

Anti-abuse is enforced via `services.premium_gate.can_start_trial`
which checks the `trial_started_at` field — never trusts client clock.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user
from services.premium_gate import (TRIAL_DURATION_DAYS, TRIAL_REPEAT_DAYS,
                                                                          can_start_trial, flip_expired_trial,
                                                                          is_premium_or_trial, start_trial,
                                                                          trial_remaining_seconds)

router = APIRouter(prefix="/api/billing", tags=["billing-trial"])
log = logging.getLogger("bigfm.billing_trial")


@router.post("/start_premium_trial")
async def billing_start_trial(request: Request,
                                                          user: dict = Depends(current_user)):
    """Phase 42-D2 — structured response instead of 403 noise.

    Always returns 200.  `state ∈ {started, already_active, already_consumed,
    upgrade_required}` lets the UI render the correct button without
    swallowing-then-recovering from an error.
    """
    db = request.app.state.db
    fresh = await db.users.find_one({"user_id": user["user_id"]})
    if not fresh:
        raise HTTPException(404, "user_not_found")
    # Active trial branch — current trial_ends_at in future.
    from services.premium_gate import trial_remaining_seconds as _rem
    remaining = _rem(fresh)
    if remaining > 0:
        return {
            "ok": True, "state": "already_active",
            "trial_ends_at": fresh.get("trial_ends_at"),
            "trial_remaining_seconds": remaining,
            "subscription_status": fresh.get("subscription_status") or "free",
            "is_premium_or_trial": True,
            "trial_duration_days": TRIAL_DURATION_DAYS,
        }
    # Already on a paid premium plan branch.
    sub_status = (fresh.get("subscription_status") or "free").lower()
    if sub_status == "premium" and fresh.get("premium_until"):
        return {
            "ok": True, "state": "already_active",
            "subscription_status": "premium",
            "is_premium_or_trial": True,
            "premium_until": fresh.get("premium_until"),
            "trial_duration_days": TRIAL_DURATION_DAYS,
        }
    allowed, reason = await can_start_trial(db, fresh)
    if not allowed:
        # Map the eligibility reason to one of the structured states.
        consumed = (reason in ("trial_already_used",
                                                  "trial_repeat_window"))
        return {
            "ok": True,
            "state": "already_consumed" if consumed else "upgrade_required",
            "reason": reason or "trial_blocked",
            "trial_repeat_days": TRIAL_REPEAT_DAYS,
            "subscription_status": sub_status,
            "is_premium_or_trial": False,
            "trial_duration_days": TRIAL_DURATION_DAYS,
        }
    state = await start_trial(db, fresh["user_id"])
    log.info("[billing-trial] start user=%s ends_at=%s",
                      fresh["user_id"], state["trial_ends_at"])
    return {"ok": True, "state": "started", **state,
                  "is_premium_or_trial": True,
                  "trial_duration_days": TRIAL_DURATION_DAYS}


@router.post("/end_trial")
async def billing_end_trial(request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    flipped = await flip_expired_trial(db, user["user_id"])
    fresh = await db.users.find_one({"user_id": user["user_id"]},
                                                                  {"subscription_status": 1,
                                                                    "trial_ended_at": 1,
                                                                    "trial_ends_at":  1})
    return {"ok": True, "flipped": flipped,
                  "subscription_status": (fresh or {}).get("subscription_status",
                                                                                                  "free"),
                  "trial_ends_at":  (fresh or {}).get("trial_ends_at"),
                  "trial_ended_at": (fresh or {}).get("trial_ended_at")}


@router.get("/trial_status")
async def billing_trial_status(request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    return {
        "subscription_status": fresh.get("subscription_status") or "free",
        "is_premium_or_trial": is_premium_or_trial(fresh),
        "trial_started_at":      fresh.get("trial_started_at"),
        "trial_ends_at":          fresh.get("trial_ends_at"),
        "trial_remaining_seconds": trial_remaining_seconds(fresh),
    }
