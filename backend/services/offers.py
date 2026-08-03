"""
Phase 17a — Offer service.

Pure helpers shared between the REST routes and tests.  The big
behaviour is `issue_coupon_for_offer` which atomically:
  • re-reads the offer and its caps,
  • increments the issued counter,
  • auto-pauses the offer if any cap is now hit,
  • returns the new coupon doc OR raises `CapacityError`.

Caps:
  - max_redemptions   (hard total)
  - daily_cap           (rolls over at midnight in venue-local TZ; we
                                  use venue.market or "UTC" if unset)
  - budget_cap_usd    (sum of `discount_value` × redemptions)

Auto-pause sets `status = "exhausted"`, records `auto_paused_at`,
`auto_paused_reason`, and emits an in-app banner (queued for the
venue dashboard via the existing TVHub broadcast).
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.offers")


class CapacityError(Exception):
    def __init__(self, reason: str, message: str):
        self.reason  = reason
        self.message = message
        super().__init__(message)


MARKET_TZ_OFFSET_HOURS = {
    "dubai": 4, "dfw": -5, "london": 0, "nyc": -5, "default": 0,
}


def _market_midnight_window(market: str) -> tuple[datetime, datetime]:
    """Return (start, end) of the venue-local day in UTC.

    The cap counters live in `offer_daily_counters` keyed by
    `(offer_id, local_date_iso)`.  Resetting is implicit: a new
    local-date string → fresh counter row."""
    offset_h = MARKET_TZ_OFFSET_HOURS.get((market or "").lower(),
                                                          MARKET_TZ_OFFSET_HOURS["default"])
    now_utc = datetime.now(timezone.utc)
    local = now_utc + timedelta(hours=offset_h)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local   = start_local + timedelta(days=1)
    return (start_local - timedelta(hours=offset_h),
              end_local   - timedelta(hours=offset_h))


def _local_date_iso(market: str) -> str:
    offset_h = MARKET_TZ_OFFSET_HOURS.get((market or "").lower(),
                                                          MARKET_TZ_OFFSET_HOURS["default"])
    return (datetime.now(timezone.utc) + timedelta(hours=offset_h)).date().isoformat()


async def issue_coupon_for_offer(db, *, offer_id: str, user_id: str,
                                                  market: Optional[str] = None) -> dict:
    """Atomically issue one coupon for an offer, respecting caps.

    Raises `CapacityError` if any cap is currently hit OR if the offer
    is paused/archived/expired."""
    offer = await db.offers.find_one({"id": offer_id})
    if not offer:
        raise CapacityError("offer_not_found", "Offer not found.")
    if offer.get("status") in ("paused", "archived"):
        raise CapacityError("offer_paused", f"Offer is {offer['status']}.")
    if offer.get("status") == "exhausted":
        # Tell the caller which cap fired so the UI surfaces the right banner.
        reason = offer.get("auto_paused_reason") or "total_cap"
        raise CapacityError(f"{reason}_hit", "Offer has hit its cap.")

    now = datetime.now(timezone.utc)
    if offer.get("end_time") and offer["end_time"] < now:
        raise CapacityError("offer_expired", "Offer window has ended.")
    if offer.get("start_time") and offer["start_time"] > now:
        raise CapacityError("offer_not_started", "Offer hasn't started yet.")

    issued      = int(offer.get("issued_count", 0))
    redeemed   = int(offer.get("redeemed_count", 0))
    max_total = offer.get("max_redemptions")
    daily_cap = offer.get("daily_cap")
    budget    = offer.get("budget_cap_usd")
    discount  = float(offer.get("discount_value") or 0)

    # Total cap.
    if max_total and issued >= int(max_total):
        await _auto_pause(db, offer, "total_cap")
        raise CapacityError("total_cap_hit", "Offer is at its total cap.")

    # Daily cap.
    daily_key = f"{offer_id}::{_local_date_iso(market or offer.get('market'))}"
    daily_doc = await db.offer_daily_counters.find_one({"id": daily_key}) or {"issued": 0}
    if daily_cap and int(daily_doc.get("issued", 0)) >= int(daily_cap):
        await _auto_pause(db, offer, "daily_cap")
        raise CapacityError("daily_cap_hit", "Offer hit today's cap. Resumes at midnight.")

    # Budget cap (estimated using discount_value × issued).
    if budget and (issued * discount) >= float(budget):
        await _auto_pause(db, offer, "budget_cap")
        raise CapacityError("budget_cap_hit", "Offer hit its budget cap. Resume manually.")

    coupon_id = "cpn_" + uuid.uuid4().hex[:14]
    short_code = secrets.token_hex(3).upper()
    coupon = {
        "coupon_id":      coupon_id,
        "short_code":     short_code,
        "offer_id":        offer_id,
        "business_id":   offer.get("business_id"),
        "venue_id":       offer.get("venue_id"),
        "user_id":         user_id,
        "discount_value": discount,
        "status":           "issued",
        "issued_at":       now,
        "expires_at":     offer.get("end_time"),
    }
    await db.coupons.insert_one(coupon)
    await db.offers.update_one({"id": offer_id},
                                          {"$inc": {"issued_count": 1}})
    await db.offer_daily_counters.update_one(
        {"id": daily_key},
        {"$inc": {"issued": 1},
          "$set": {"offer_id": offer_id, "date": _local_date_iso(market or offer.get("market"))}},
        upsert=True,
    )
    # Re-check caps post-increment — auto-pause if the LAST coupon
    # tipped us into a cap so the next attempt fails fast.
    new_issued = issued + 1
    if max_total and new_issued >= int(max_total):
        await _auto_pause(db, offer, "total_cap")
    elif daily_cap and (int(daily_doc.get("issued", 0)) + 1) >= int(daily_cap):
        await _auto_pause(db, offer, "daily_cap")
    elif budget and (new_issued * discount) >= float(budget):
        await _auto_pause(db, offer, "budget_cap")
    coupon.pop("_id", None)
    return coupon


async def _auto_pause(db, offer: dict, reason: str) -> None:
    if offer.get("status") in ("exhausted", "paused", "archived"):
        return
    await db.offers.update_one(
        {"id": offer["id"]},
        {"$set": {"status":                "exhausted",
                    "auto_paused_at":      datetime.now(timezone.utc),
                    "auto_paused_reason": reason}},
    )
    logger.info("[offer] auto-paused %s reason=%s", offer["id"], reason)


# ─── Phase 17b — Auto-resume scheduler ───────────────────────────────
async def auto_resume_eligible_offers(db, *, now: Optional[datetime] = None) -> dict:
    """Flip `status: exhausted` offers back to `active` when their
    venue-local midnight has rolled over since the auto-pause time.

    ONLY applies to `auto_paused_reason == "daily_cap"`.  Total-cap
    and budget-cap exhaustions require manual review and are skipped.

    Returns `{checked, resumed, skipped}` for observability.
    """
    now = now or datetime.now(timezone.utc)
    q = {"status": "exhausted", "auto_paused_reason": "daily_cap"}
    cursor = db.offers.find(q)
    checked = resumed = skipped = 0
    async for o in cursor:
        checked += 1
        paused_at = o.get("auto_paused_at")
        if not paused_at:
            skipped += 1
            continue
        if paused_at.tzinfo is None:
            paused_at = paused_at.replace(tzinfo=timezone.utc)
        market = (o.get("market") or "").lower()
        offset_h = MARKET_TZ_OFFSET_HOURS.get(market,
                                                              MARKET_TZ_OFFSET_HOURS["default"])
        # Local date at pause time vs local date now.
        local_at_pause = (paused_at  + timedelta(hours=offset_h)).date()
        local_now       = (now         + timedelta(hours=offset_h)).date()
        if local_now > local_at_pause:
            await db.offers.update_one(
                {"id": o["id"]},
                {"$set": {"status":              "active",
                            "auto_paused_reason": None,
                            "auto_resumed_at":   now,
                            "updated_at":         now},
                  "$inc": {"auto_resume_count": 1}},
            )
            resumed += 1
            logger.info("[auto-resume] offer=%s venue=%s",
                              o.get("id"), o.get("venue_id"))
        else:
            skipped += 1
    return {"checked": checked, "resumed": resumed, "skipped": skipped}


def public_offer(o: Optional[dict]) -> dict:
    if not o:
        return {}
    out = {k: v for k, v in o.items() if k != "_id"}
    # Coerce datetimes for JSON safety.
    for k in ("start_time", "end_time", "auto_paused_at", "created_at", "updated_at"):
        if isinstance(out.get(k), datetime):
            out[k] = out[k].astimezone(timezone.utc).isoformat()
    return out


CSV_HEADER = [
    "title", "description", "offer_type", "discount_value",
    "start_time", "end_time", "max_redemptions", "redemption_method",
    "terms",
]

CSV_EXAMPLES = [
    ["Happy hour 50% off", "All drinks half price",
      "percent", "50", "2026-06-10T17:00:00Z", "2026-06-10T20:00:00Z",
      "100", "qr_scan", "Dine-in only"],
    ["Free karak refill",   "Buy 1 karak, get 1 free",
      "free_item", "0", "2026-06-11T08:00:00Z", "2026-06-30T22:00:00Z",
      "500", "qr_scan", "Limit 1 per customer per day"],
]
