"""Phase 13b — Conversion attribution + ROI cost config.

`attribute_conversion(db, user_id, event_type, value, conversion_id=None,
                                  window_days=7)`
  Finds the most recent `lifecycle_send_log` row for the user where
  `clicked_at >= now - window_days` AND `converted_at is None`, then
  marks it converted with `conversion_value` + metadata. Idempotent —
  if a row with the same `conversion_id` (e.g. coupon_id) has already
  been attributed, it's a no-op.

Callable from coupon-claim, billing webhook, and reward-win paths.
Best-effort: never raises, never blocks the caller.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.conversion")

DEFAULT_WINDOW_DAYS = int(
    os.environ.get("BIGFM_CONVERSION_WINDOW_DAYS", "7"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def attribute_conversion(
        db, *, user_id: str, event_type: str,
        value: float = 0.0,
        currency: Optional[str] = None,
        conversion_id: Optional[str] = None,
        window_days: int = DEFAULT_WINDOW_DAYS) -> Optional[dict]:
    """Best-effort attribution. Returns the updated send_log row dict
    on success, None on no-op.

    `currency` (Phase 13b hotfix): persists `conversion_currency` onto
    the send_log row so funnel/ROI reporting can show the right unit
    when offers are priced in AED/USD/etc.
    """
    try:
        # Idempotency check: if this conversion_id is already on a
        # send_log row, skip.
        if conversion_id:
            already = await db.lifecycle_send_log.find_one(
                {"user_id": user_id, "conversion_id": conversion_id})
            if already:
                return None
        cutoff = _now() - timedelta(days=window_days)
        # Newest clicked-not-yet-converted row in the window.
        candidate = await db.lifecycle_send_log.find_one(
            {"user_id": user_id,
              "clicked_at": {"$gte": cutoff},
              "converted_at": None},
            sort=[("clicked_at", -1)])
        if not candidate:
            return None
        update = {
            "converted_at": _now(),
            "conversion_value": float(value or 0.0),
            "conversion_event_type": event_type,
        }
        if currency:
            update["conversion_currency"] = currency
        if conversion_id:
            update["conversion_id"] = conversion_id
        await db.lifecycle_send_log.update_one(
            {"_id": candidate["_id"]},
            {"$set": update})
        candidate.update(update)
        logger.info(
            "Phase 13b conversion attributed: user=%s event=%s "
            "value=%.2f %s send_log=%s campaign=%s variant=%s",
            user_id, event_type, value, currency or "",
            candidate["_id"],
            candidate.get("campaign_id"),
            candidate.get("variant_slug"))
        return candidate
    except Exception as e:
        logger.debug(f"attribute_conversion noop: {e}")
        return None


# ─── ROI cost config ──────────────────────────────────────────────────
def cost_config() -> dict:
    return {
        "email_usd": float(
            os.environ.get("BIGFM_COST_EMAIL_USD", "0.001")),
        "push_usd": float(
            os.environ.get("BIGFM_COST_PUSH_USD", "0.0")),
        "sms_usd": float(
            os.environ.get("BIGFM_COST_SMS_USD", "0.01")),
        "window_days": DEFAULT_WINDOW_DAYS,
    }


def estimate_send_cost(*, sent_email: int = 0, sent_push: int = 0,
                                sent_sms: int = 0) -> float:
    c = cost_config()
    return (sent_email * c["email_usd"]
              + sent_push * c["push_usd"]
              + sent_sms * c["sms_usd"])
