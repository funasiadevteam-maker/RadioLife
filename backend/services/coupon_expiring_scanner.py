"""Phase A Item 3 — Daily coupon-expiring scanner.

Scans `coupons` where:
  * status ∈ {"saved", "claimed"}
  * expires_at within the next 24 hours
  * NOT already notified (idempotency marker `expiring_notified_at`)

Fires the `coupon_expiring_24h` notification trigger and stamps the row
so a subsequent scan run doesn't re-dispatch.

Runs on an in-process hourly loop (mirroring the AD.8 scheduler
pattern) — cheap enough since the window is bounded and the query is
indexed by `expires_at`.  Idempotent + fail-safe: individual dispatch
errors never abort the sweep.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

logger = logging.getLogger("bigfm.coupon_expiring_scanner")

# Poll every hour — a coupon expiring in [now, now+24h) may be picked up
# up to 60 min after crossing the window edge, which is well within the
# "24h heads-up" spirit of the recipe.
POLL_INTERVAL_SEC = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_coupon_expiring_indexes(db) -> None:
    try:
        await db.coupons.create_index(
            [("status", 1), ("expires_at", 1)])
        await db.coupons.create_index("expiring_notified_at", sparse=True)
    except Exception as e:
        logger.warning("[coupon_expiring] index setup: %s", e)


async def run_sweep(db) -> Dict[str, Any]:
    """One scan pass.  Returns a summary dict — used by tests + admin
    manual invocation."""
    from services.notification_trigger_dispatcher import dispatch_event
    now = _now()
    horizon = now + timedelta(hours=24)
    q = {
        "status": {"$in": ["saved", "claimed"]},
        "expires_at": {"$gte": now, "$lte": horizon},
        "expiring_notified_at": {"$exists": False},
        "user_id": {"$exists": True, "$ne": None},
    }
    dispatched = 0
    errors = 0
    scanned = 0
    async for c in db.coupons.find(q).limit(500):        # per-tick cap
        scanned += 1
        try:
            await dispatch_event(
                db,
                event_name="coupon_expiring_24h",
                user_id=c["user_id"],
                payload={"coupon_id":  c.get("coupon_id"),
                                  "title":            c.get("title"),
                                  "expires_at":  (c["expires_at"].isoformat()
                                                              if isinstance(c["expires_at"],
                                                                                          datetime)
                                                              else c["expires_at"]),
                                  "business_id":  c.get("business_id"),
                                  "advertiser_id": c.get("advertiser_id")})
            await db.coupons.update_one(
                {"_id": c["_id"]},
                {"$set": {"expiring_notified_at": now}})
            dispatched += 1
        except Exception as e:
            errors += 1
            logger.warning("[coupon_expiring] dispatch fail cid=%s: %s",
                                          c.get("coupon_id"), e)
    return {"scanned": scanned, "dispatched": dispatched,
                    "errors": errors, "ran_at": now.isoformat()}


def start_scheduler(app, db, *, poll_interval_sec: int = POLL_INTERVAL_SEC) -> None:
    async def _loop():
        # Small grace period so backend boot finishes before first sweep.
        await asyncio.sleep(45)
        while True:
            try:
                res = await run_sweep(db)
                if res["dispatched"] > 0 or res["errors"] > 0:
                    logger.info("[coupon_expiring] sweep %s", res)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[coupon_expiring] tick failed: %s", e)
            await asyncio.sleep(poll_interval_sec)

    existing = getattr(app.state, "coupon_expiring_scheduler", None)
    if existing and not existing.done():
        existing.cancel()
    app.state.coupon_expiring_scheduler = asyncio.create_task(_loop())
    logger.info("[coupon_expiring] scheduler started (poll=%ds)", poll_interval_sec)


__all__ = ["ensure_coupon_expiring_indexes", "run_sweep", "start_scheduler"]
