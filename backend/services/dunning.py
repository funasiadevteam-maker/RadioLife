"""Phase 6 — Dunning / failed-payment lifecycle.

State machine:
  active → past_due (on invoice.payment_failed) → grace 7d → canceled_for_nonpayment
  past_due + invoice.payment_succeeded → active (clear grace)

Notifications are STUBBED to a `billing_notifications` collection — wire
SendGrid / Resend in Phase 7 when transactional email is on the roadmap.
TODO(Phase 7): replace _log_notification(send=True) with real SMTP/Resend.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.dunning")

GRACE_PERIOD_DAYS = 7
# Days within the grace window on which we send reminder notifications.
DUNNING_NOTIFICATION_DAYS = (1, 3, 6)


async def ensure_dunning_indexes(db) -> None:
    await db.users.create_index("billing_status", sparse=True)
    await db.users.create_index([("billing_status", 1), ("grace_period_ends_at", 1)],
                                  sparse=True)
    await db.subscription_lifecycle_log.create_index([("user_id", 1), ("ts", -1)])
    await db.subscription_lifecycle_log.create_index("stripe_event_id", sparse=True)
    await db.stripe_events_processed.create_index("event_id", unique=True)
    # TTL: 90 days on processed events log (Stripe never replays older than that)
    await db.stripe_events_processed.create_index("processed_at",
                                                     expireAfterSeconds=90 * 86400)
    await db.billing_notifications.create_index([("user_id", 1), ("created_at", -1)])


async def log_lifecycle(db, *, user_id: str, event_type: str,
                          from_state: Optional[str], to_state: str,
                          stripe_event_id: Optional[str] = None,
                          metadata: Optional[dict] = None) -> None:
    await db.subscription_lifecycle_log.insert_one({
        "_id": f"slc_{uuid.uuid4().hex[:14]}",
        "user_id": user_id, "event_type": event_type,
        "from_state": from_state, "to_state": to_state,
        "stripe_event_id": stripe_event_id,
        "metadata": metadata or {},
        "ts": datetime.now(timezone.utc),
    })


async def log_notification(db, *, user_id: str, kind: str,
                              subject: str, body: str,
                              metadata: Optional[dict] = None) -> str:
    """STUB: writes to billing_notifications instead of sending email.
    Future: wire SendGrid / Resend transactional email here."""
    nid = f"bn_{uuid.uuid4().hex[:14]}"
    await db.billing_notifications.insert_one({
        "_id": nid, "user_id": user_id, "kind": kind,
        "subject": subject, "body": body,
        "delivery_status": "logged",  # not actually sent yet
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc),
    })
    logger.info(f"[notify-stub] {kind} → user={user_id} subject={subject!r}")
    return nid


# ----------------------------------------------------------------------
async def mark_past_due(db, user_id: str, *,
                          stripe_event_id: Optional[str] = None,
                          metadata: Optional[dict] = None) -> dict:
    """Triggered by invoice.payment_failed webhook. Sets billing_status,
    starts the 7-day grace clock, but keeps premium ACTIVE during grace."""
    now = datetime.now(timezone.utc)
    grace_end = now + timedelta(days=GRACE_PERIOD_DAYS)
    u = await db.users.find_one_and_update(
        {"user_id": user_id},
        {"$set": {
            "billing_status": "past_due",
            "grace_period_ends_at": grace_end,
            "past_due_started_at": now,
            "subscription.status": "past_due",
        }},
        return_document=False,
        projection={"billing_status": 1, "_id": 0},
    )
    prev = (u or {}).get("billing_status") or "active"
    await log_lifecycle(db, user_id=user_id, event_type="invoice.payment_failed",
                          from_state=prev, to_state="past_due",
                          stripe_event_id=stripe_event_id, metadata=metadata)
    # Fire first notification immediately
    await log_notification(db, user_id=user_id, kind="dunning_day_1",
                              subject="Your RadioLife payment failed",
                              body=f"We couldn't process your payment. You have {GRACE_PERIOD_DAYS} days to update your card before losing Premium.",
                              metadata={"grace_period_ends_at": grace_end.isoformat()})
    return {"billing_status": "past_due", "grace_period_ends_at": grace_end}


async def mark_payment_recovered(db, user_id: str, *,
                                    stripe_event_id: Optional[str] = None) -> dict:
    """On invoice.payment_succeeded AFTER a past_due: restore active state."""
    now = datetime.now(timezone.utc)
    u = await db.users.find_one({"user_id": user_id},
                                    {"billing_status": 1, "_id": 0}) or {}
    prev = u.get("billing_status") or "active"
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "billing_status": "active",
            "subscription.status": "active",
            "payment_recovered_at": now,
        },
         "$unset": {"grace_period_ends_at": "", "past_due_started_at": ""}},
    )
    if prev == "past_due":
        await log_lifecycle(db, user_id=user_id,
                              event_type="invoice.payment_succeeded",
                              from_state="past_due", to_state="active",
                              stripe_event_id=stripe_event_id)
        await log_notification(db, user_id=user_id, kind="dunning_recovered",
                                  subject="RadioLife payment recovered",
                                  body="Your card went through. You're all set — thanks for sticking with us.")
    return {"billing_status": "active"}


async def expire_grace_period(db, user_id: str) -> dict:
    """Grace period elapsed without recovery: downgrade to free and cascade
    family seats."""
    from services.family import cascade_family_revoke
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_premium": False,
            "premium_tier": None,
            "premium_source": None,
            "billing_status": "canceled_for_nonpayment",
            # Phase 6.1 — also reset the plan mirror so /billing/status &
            # everywhere else sees a clean `free` baseline post-cancel.
            "subscription.plan": "free",
            "subscription.status": "canceled",
            "subscription.cancel_at_period_end": False,
            "current_plan_slug": "free",
            "reward_multiplier": 1.0,
            "downgraded_at": now,
        },
         "$unset": {"grace_period_ends_at": "", "past_due_started_at": ""}},
    )
    await cascade_family_revoke(db, user_id)
    await log_lifecycle(db, user_id=user_id, event_type="grace_period_expired",
                          from_state="past_due", to_state="canceled_for_nonpayment")
    await log_notification(db, user_id=user_id, kind="dunning_downgraded",
                              subject="RadioLife Premium ended",
                              body="Your Premium grace period ended without payment. You're now on Free. Resubscribe any time at /billing.")
    return {"billing_status": "canceled_for_nonpayment"}


# ----------------------------------------------------------------------
async def sweep_grace_periods(db, as_of: Optional[datetime] = None) -> dict:
    """Background sweep: every minute. Finds users whose grace_period_ends_at
    has elapsed and downgrades them. Also fires day-3 / day-6 reminder
    notifications based on elapsed grace days.

    Optional ``as_of`` lets admin tests force a future timestamp so an expired
    grace window can be evaluated without poking Mongo directly. Defaults to
    ``datetime.now(timezone.utc)``."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None: now = now.replace(tzinfo=timezone.utc)
    downgraded = 0
    notified = 0
    def _aware(dt):
        if dt and dt.tzinfo is None: return dt.replace(tzinfo=timezone.utc)
        return dt
    # 1. Auto-downgrade expired grace
    expired_cur = db.users.find(
        {"billing_status": "past_due",
         "grace_period_ends_at": {"$lte": now}},
        {"user_id": 1, "_id": 0},
    )
    async for u in expired_cur:
        try:
            await expire_grace_period(db, u["user_id"])
            downgraded += 1
        except Exception as e:
            logger.warning(f"[dunning-sweep] expire failed for {u.get('user_id')}: {e}")
    # 2. Day-3 / day-6 reminder notifications (idempotent via kind dedup)
    active_grace = db.users.find(
        {"billing_status": "past_due",
         "grace_period_ends_at": {"$gt": now}},
        {"user_id": 1, "past_due_started_at": 1, "grace_period_ends_at": 1, "_id": 0},
    )
    async for u in active_grace:
        started = _aware(u.get("past_due_started_at"))
        if not started: continue
        days_elapsed = (now - started).days
        if days_elapsed in DUNNING_NOTIFICATION_DAYS and days_elapsed > 1:
            kind = f"dunning_day_{days_elapsed}"
            existing = await db.billing_notifications.find_one(
                {"user_id": u["user_id"], "kind": kind}, {"_id": 1},
            )
            if existing: continue
            grace_end = _aware(u["grace_period_ends_at"])
            days_left = max(0, (grace_end - now).days)
            await log_notification(
                db, user_id=u["user_id"], kind=kind,
                subject=f"Your RadioLife Premium ends in {days_left} days",
                body=f"You're on day {days_elapsed} of a {GRACE_PERIOD_DAYS}-day grace period. Update your card at /billing to keep Premium.",
                metadata={"days_elapsed": days_elapsed, "days_left": days_left},
            )
            notified += 1
    if downgraded or notified:
        logger.info(f"[dunning-sweep] downgraded={downgraded} notified={notified}")
    return {"downgraded": downgraded, "notified": notified}


# ----------------------------------------------------------------------
async def already_processed(db, event_id: str) -> bool:
    """Idempotency check — returns True if this Stripe event_id has already
    been written to stripe_events_processed."""
    if not event_id: return False
    doc = await db.stripe_events_processed.find_one({"event_id": event_id},
                                                        {"_id": 1})
    return bool(doc)


async def mark_processed(db, event_id: str, *,
                            event_type: Optional[str] = None,
                            user_id: Optional[str] = None) -> bool:
    """Inserts a stripe_events_processed row. Returns True if it was a NEW
    insert (we should process this event), False if it was already there."""
    if not event_id:
        return True
    try:
        await db.stripe_events_processed.insert_one({
            "event_id": event_id, "event_type": event_type,
            "user_id": user_id,
            "processed_at": datetime.now(timezone.utc),
        })
        return True
    except Exception:
        return False
