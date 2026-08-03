"""Phase H.5 — Ambassador-tier recompute scheduler.

Recomputes the cached `ambassador_tier` on the user doc for the top-N
most-recently-active users every cycle.  Without this the tier flair on
the new leaderboards / MiniPlayer pill / Passport hero would only
refresh when the user themselves hit `/api/me/passport/ambassador-tier`
— a long-stale tail.

Public entry points
-------------------
    recompute_ambassador_tier_for_active_users(db, *, limit=1000,
                                                                                            since_days=7) -> dict
    start_scheduler(app, db, *, interval_sec=300)
"""
from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

log = logging.getLogger("bigfm.passport_tier_scheduler")

# Safety budget — abort the cycle if it exceeds this so the event loop
# stays responsive.  30 seconds is well above the typical recompute
# (~50 µs per user × 1000 users ≈ 50 ms gross compute; the heavy bit is
# the per-user PointsService.get_balance round-trip).
_SAFETY_BUDGET_SEC = 30


async def recompute_ambassador_tier_for_active_users(
        db, *, limit: int = 1000, since_days: int = 7) -> dict:
    """Find recently-active users (last login OR last listen in the
    past `since_days`) and refresh their cached tier.  Idempotent.

    Returns a small summary dict for the scheduler / admin endpoint
    so callers can observe progress.
    """
    from services.passport_engine import compute_ambassador_tier

    started = time.monotonic()
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    # The `users` schema across this project uses both `last_login_at`
    # (auth) and `last_listen_at` (bigcoin heartbeat). Match either.
    query = {"$or": [
        {"last_login_at":  {"$gte": cutoff}},
        {"last_listen_at": {"$gte": cutoff}},
    ]}
    # Sort by whichever activity is most recent to bias the cap toward
    # the truly hot tail.
    pipeline = [
        {"$match": query},
        {"$addFields": {"_last_active": {
            "$max": ["$last_login_at", "$last_listen_at"]}}},
        {"$sort":  {"_last_active": -1}},
        {"$limit": int(limit)},
        {"$project": {"_id": 0, "user_id": 1,
                                "ambassador_tier": 1}},
    ]
    bumped = unchanged = errors = scanned = 0
    async for u in db.users.aggregate(pipeline):
        if time.monotonic() - started > _SAFETY_BUDGET_SEC:
            log.warning("[tier-recompute] safety budget exceeded — "
                                    "stopping at scanned=%d", scanned)
            break
        scanned += 1
        uid = u.get("user_id")
        if not uid:
            continue
        old = u.get("ambassador_tier")
        try:
            res = await compute_ambassador_tier(db, uid)
        except Exception as e:
            errors += 1
            log.debug("[tier-recompute] user=%s err=%s", uid, e)
            continue
        new = res.get("tier")
        if new and new != old:
            bumped += 1
        else:
            unchanged += 1
    elapsed_ms = int((time.monotonic() - started) * 1000)
    summary = {"scanned":      scanned,
                          "bumped":      bumped,
                          "unchanged":  unchanged,
                          "errors":      errors,
                          "elapsed_ms": elapsed_ms,
                          "limit":          limit,
                          "since_days": since_days}
    log.info("[tier-recompute] %s", summary)
    return summary


def start_scheduler(app, db, *, interval_sec: int = 300,
                                          limit: int = 1000) -> None:
    """Attaches an asyncio task to `app.state.passport_tier_task`.  Safe
    to call multiple times — old tasks are cancelled first."""
    existing = getattr(app.state, "passport_tier_task", None)
    if existing and not existing.done():
        existing.cancel()

    async def _loop():
        # Stagger the first tick so we don't all-fire alongside other
        # boot-time crons.
        await asyncio.sleep(45)
        while True:
            try:
                await recompute_ambassador_tier_for_active_users(
                    db, limit=limit, since_days=7)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("[tier-recompute] cycle error: %s", e)
            try:
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise

    app.state.passport_tier_task = asyncio.create_task(_loop())
    log.info("Phase H.5 ambassador-tier scheduler started "
                  "(interval=%ds, limit=%d)", interval_sec, limit)


__all__ = [
    "recompute_ambassador_tier_for_active_users",
    "start_scheduler",
]
