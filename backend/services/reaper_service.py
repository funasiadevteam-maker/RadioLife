"""Phase SC.6 — Stale intent reaper.

Scans `payment_transactions_v2` for rows stuck in `requires_confirmation`
past a threshold and re-syncs them against real Stripe state.  Runs
every 15 min via `services/reaper_loop.py`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("bigfm.reaper_sc6")


def _now():
    return datetime.now(timezone.utc)


async def run_stale_intent_sweep(db, *,
                                                                    stale_after_minutes: int = 60,
                                                                    abandon_after_hours: int = 24,
                                                                    max_scan: int = 200) -> dict:
    """Return a summary of the sweep.  Idempotent — safe to call
    multiple times per interval."""
    from services.payment_service import poll_intent_and_sync

    stale_cutoff = _now() - timedelta(minutes=stale_after_minutes)
    abandon_cutoff = _now() - timedelta(hours=abandon_after_hours)

    scanned = 0
    updated = 0
    abandoned = 0
    errors = 0

    cursor = db.payment_transactions_v2.find(
        {"status": "requires_confirmation",
          "created_at": {"$lt": stale_cutoff}},
        {"transaction_id": 1, "stripe_payment_intent_id": 1, "created_at": 1},
    ).limit(max_scan)

    async for row in cursor:
        scanned += 1
        intent_id = row.get("stripe_payment_intent_id")
        if not intent_id:
            continue
        stripe_missing = False
        try:
            result = await poll_intent_and_sync(db, intent_id=intent_id)
            _ = result
        except Exception as e:
            # If Stripe says the intent doesn't exist, treat as terminal.
            # `poll_intent_and_sync` wraps stripe errors in `PaymentError`
            # so we check both str(e) and the .detail attribute.
            detail = getattr(e, "detail", None) or ""
            msg = (str(e) + " " + detail).lower()
            if "no such payment_intent" in msg or "resource_missing" in msg:
                stripe_missing = True
            else:
                errors += 1
                logger.exception(f"[reaper] failed intent={intent_id}")
                continue
        fresh = await db.payment_transactions_v2.find_one(
            {"stripe_payment_intent_id": intent_id})
        if not fresh:
            continue
        if fresh.get("status") != "requires_confirmation":
            updated += 1
            continue
        # Still requires_confirmation — check if stale enough to abandon
        created = fresh.get("created_at")
        should_abandon = (stripe_missing
                                              or (created and created < abandon_cutoff))
        if should_abandon:
            reason = ("reaper_intent_missing" if stripe_missing
                              else "reaper_abandoned")
            await db.payment_transactions_v2.update_one(
                {"stripe_payment_intent_id": intent_id},
                {"$set": {"status": "abandoned",
                                  "failed_at": _now(),
                                  "failure_reason": reason}})
            abandoned += 1

    summary = {"scanned":      scanned,
                          "updated":      updated,
                          "abandoned": abandoned,
                          "errors":        errors,
                          "at":                _now().isoformat()}
    logger.info(f"[reaper] sweep {summary}")
    return summary


# ─── Background loop ─────────────────────────────────────────────
async def reaper_loop(app) -> None:
    """Long-running task started by server.py bootstrap."""
    interval = int(os.environ.get("SC6_REAPER_INTERVAL_SEC", "900"))  # 15 min
    stale_min = int(os.environ.get("SC6_REAPER_STALE_MINUTES", "60"))
    abandon_hr = int(os.environ.get("SC6_REAPER_ABANDON_HOURS", "24"))
    logger.info(f"[reaper] starting loop interval={interval}s stale={stale_min}m abandon={abandon_hr}h")
    # Warm-up delay so cold-boot doesn't hammer Stripe
    await asyncio.sleep(30)
    while True:
        try:
            await run_stale_intent_sweep(
                app.state.db,
                stale_after_minutes=stale_min,
                abandon_after_hours=abandon_hr)
        except Exception:
            logger.exception("[reaper] loop iteration failed")
        await asyncio.sleep(interval)


__all__ = ["run_stale_intent_sweep", "reaper_loop"]
