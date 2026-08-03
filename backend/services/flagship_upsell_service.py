"""Phase O — Flagship Sponsor CTA (upsell funnel).

Contextual banner shown to advertisers who are already spending
across the ad ecosystem and are prime candidates for the priciest
product — a Phase F flagship boost slot.

Eligibility (either passes):
    * `spend_30d_cents >= 50_000`  (i.e. $500 across all ad
      products in the last 30 days), OR
    * `active_campaign_count >= 3` (any active campaign across
      the M4-M7 + legacy AD.* collections owned by them).

Suppression:
    * `upsell_dismissed_until` — 24h soft dismissal.
    * `upsell_lifetime_dismissed` — permanent opt-out.

Recommended slot:
    * Cheapest open Phase F slot (`status="open"`, `end_at > now`)
      in the advertiser's home_region OR in `ae` as fallback that
      the advertiser has NOT already bid on.

In-memory spend cache (15 min TTL per advertiser) — no new
collection, no new indexes on the hot path.
"""
from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("bigfm.m8_upsell")

# ── Config ────────────────────────────────────────────────────────
SPEND_THRESHOLD_CENTS       = 50_000   # $500 in 30d
ACTIVE_CAMPAIGN_THRESHOLD   = 3
DISMISS_HOURS               = 24
SPEND_CACHE_TTL_SECONDS     = 900      # 15 min

# Flow prefixes considered "advertiser spend".
_ADVERTISER_FLOWS = {
    # M4-M7 (Phases F-N).
    "m1_rj_sponsored_read_prepay",
    "m2_location_boost_prepay",
    "m3_marketplace_slot_prepay",
    "m4_flagship_boost",
    "m5_takeover_hour_prepay",
    "m6_retargeting_prepay",
    "m7_cpa_redeem_charge",
    # Legacy AD.* rows that carry `advertiser_id`.
    "ad5_trivia_sponsorship_prepay",
    "ad9_pc_prepay",
    "ad3_predict_win_sponsorship",
    "ad4_coupon_save_split",
    "ad11_banner_impression",
    "ad12_notification_delivery",
    "ad2_sponsored_game_split",
    # Others we own (excluded: connect_destination, mer3_*, ad7_scan_to_pay
    # which are user-payer or platform-fee-only rows).
}

# Collections we count "active campaigns" from + the ownership field name.
_ACTIVE_CAMPAIGN_SOURCES = [
    ("rj_sponsored_reads",       "advertiser_business_id", "active"),
    ("location_boost_campaigns", "advertiser_business_id", "active"),
    ("marketplace_featured_slots","advertiser_business_id", "active"),
    ("takeover_hours",           "advertiser_business_id", "active"),
    ("takeover_hours",           "advertiser_business_id", "live"),
    ("retargeting_campaigns",    "advertiser_business_id", "active"),
    # Legacy AD.*
    ("banner_campaigns",         "advertiser_id",           "live"),
    ("coupon_campaigns",         "advertiser_id",           "live"),
    ("notification_campaigns",   "advertiser_id",           "live"),
    ("trivia_sponsorships",      "advertiser_id",           "active"),
    # Phase G podcast completion sponsorships.
    ("podcast_completion_sponsorships", "advertiser_id",    "active"),
]


# ── Helpers ───────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _shape(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return d
    out = dict(d)
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# In-memory spend cache: {advertiser_id: (spend_cents, cached_at_epoch)}.
_SPEND_CACHE: Dict[str, Tuple[int, float]] = {}


def _cache_get(advertiser_id: str) -> Optional[int]:
    entry = _SPEND_CACHE.get(advertiser_id)
    if not entry:
        return None
    val, ts = entry
    if time.time() - ts > SPEND_CACHE_TTL_SECONDS:
        _SPEND_CACHE.pop(advertiser_id, None)
        return None
    return val


def _cache_put(advertiser_id: str, spend_cents: int) -> None:
    _SPEND_CACHE[advertiser_id] = (spend_cents, time.time())


def invalidate_spend_cache(advertiser_id: Optional[str] = None) -> None:
    if advertiser_id is None:
        _SPEND_CACHE.clear()
    else:
        _SPEND_CACHE.pop(advertiser_id, None)


async def ensure_upsell_indexes(db) -> None:
    try:
        await db.advertiser_upsell_events.create_index(
            "id", unique=True, name="aue_id_uniq")
        await db.advertiser_upsell_events.create_index(
            [("advertiser_business_id", 1), ("event_type", 1),
             ("seen_at", -1)],
            name="aue_adv_type_time")
        await db.advertiser_upsell_events.create_index(
            [("event_type", 1), ("seen_at", -1)],
            name="aue_type_time")
        logger.info("[m8_upsell] indexes ready")
    except Exception as e:
        logger.warning("[m8_upsell] index setup failed: %s", e)


# ── Spend aggregation ────────────────────────────────────────────
async def compute_spend_30d(db, *, advertiser_id: str,
                            force: bool = False) -> int:
    """Sum of `amount_cents` in `payment_transactions_v2` where
    `advertiser_id == X`, flow is an advertiser-buying flow, and
    `created_at > now-30d`.  Refunded rows (`status="refunded"`) are
    excluded."""
    if not force:
        cached = _cache_get(advertiser_id)
        if cached is not None:
            return cached
    cutoff = _now() - timedelta(days=30)
    match = {
        "advertiser_id": advertiser_id,
        "flow":          {"$in": list(_ADVERTISER_FLOWS)},
        "created_at":    {"$gte": cutoff},
        "status":        {"$ne": "refunded"},
    }
    total = 0
    async for r in db.payment_transactions_v2.aggregate([
        {"$match": match},
        {"$group": {"_id": None,
                    "total": {"$sum": "$amount_cents"}}},
    ]):
        total = int(r.get("total") or 0)
    _cache_put(advertiser_id, total)
    return total


async def count_active_campaigns(db, *, advertiser_id: str) -> int:
    """Sum of active/live campaigns across every advertiser-owned
    monetization collection.  Best-effort — collections that don't
    exist yet are ignored."""
    total = 0
    for coll_name, field, status in _ACTIVE_CAMPAIGN_SOURCES:
        try:
            total += await db[coll_name].count_documents(
                {field: advertiser_id, "status": status})
        except Exception:
            pass
    return total


# ── Recommended slot ─────────────────────────────────────────────
async def recommend_slot(db, *, advertiser_id: str,
                         home_region: Optional[str] = None
                         ) -> Optional[Dict[str, Any]]:
    """Cheapest open Phase F flagship boost slot the advertiser
    hasn't already bid on.  Falls back across region → any region."""
    # Slot IDs the advertiser already touched (any bid state).
    bidden_slot_ids: set = set()
    async for b in db.flagship_boost_bids.find(
            {"advertiser_business_id": advertiser_id},
            {"slot_id": 1}):
        bidden_slot_ids.add(b.get("slot_id"))
    now = _now()
    base_q: Dict[str, Any] = {"status": "open",
                              "end_at": {"$gt": now}}
    if bidden_slot_ids:
        base_q["id"] = {"$nin": list(bidden_slot_ids)}

    # Priority 1: home region.  Priority 2: any region.
    for tightener in ([home_region] if home_region else []) + [None]:
        q = dict(base_q)
        if tightener:
            q["region_code"] = tightener.lower()
        row = await db.flagship_boost_slots.find_one(
            q, sort=[("floor_price_cents", 1)])
        if row:
            return {
                "slot_id":              row["id"],
                "region_code":          row.get("region_code"),
                "station_slot":         row.get("station_slot"),
                "floor_price_cents":    int(row.get("floor_price_cents") or 0),
                "end_at":               _iso(row.get("end_at")),
                "current_top_bid_cents":
                    (await _current_top_bid(db, row["id"])) or 0,
            }
    return None


async def _current_top_bid(db, slot_id: str) -> int:
    top = await db.flagship_boost_bids.find_one(
        {"slot_id": slot_id,
         "status": {"$in": ["pending", "winning", "approved"]}},
        sort=[("bid_amount_cents", -1)])
    return int((top or {}).get("bid_amount_cents") or 0)


# ── Eligibility ─────────────────────────────────────────────────
async def check_eligibility(db, *, advertiser_id: str,
                            force_refresh: bool = False
                            ) -> Dict[str, Any]:
    """Runs the eligibility rules and returns the response
    body shape spec'd in the phase brief."""
    now = _now()
    if force_refresh:
        invalidate_spend_cache(advertiser_id)
    # Load the advertiser row for dismissal state + home_region.
    ad = await db.advertisers_v2.find_one(
        {"advertiser_id": advertiser_id})
    if not ad:
        return {"eligible": False, "reason": "advertiser_not_found",
                "spend_30d_cents": 0, "active_campaign_count": 0}

    lifetime_dismissed = bool(ad.get("upsell_lifetime_dismissed"))
    if lifetime_dismissed:
        return {"eligible": False, "reason": "dismissed_permanently",
                "spend_30d_cents": 0, "active_campaign_count": 0,
                "upsell_lifetime_dismissed": True}
    dismissed_until = ad.get("upsell_dismissed_until")
    if isinstance(dismissed_until, datetime):
        if dismissed_until.tzinfo is None:
            dismissed_until = dismissed_until.replace(tzinfo=timezone.utc)
        if dismissed_until > now:
            return {"eligible": False, "reason": "dismissed",
                    "spend_30d_cents": 0, "active_campaign_count": 0,
                    "dismissed_until": _iso(dismissed_until)}

    spend = await compute_spend_30d(db, advertiser_id=advertiser_id)
    count = await count_active_campaigns(db, advertiser_id=advertiser_id)

    spend_ok = spend >= SPEND_THRESHOLD_CENTS
    count_ok = count >= ACTIVE_CAMPAIGN_THRESHOLD
    eligible = spend_ok or count_ok

    reason = "below_thresholds"
    if eligible:
        reasons = []
        if spend_ok: reasons.append(f"spend_ge_{SPEND_THRESHOLD_CENTS}")
        if count_ok: reasons.append(f"active_ge_{ACTIVE_CAMPAIGN_THRESHOLD}")
        reason = "+".join(reasons)

    resp: Dict[str, Any] = {
        "eligible":                eligible,
        "reason":                  reason,
        "spend_30d_cents":         spend,
        "spend_threshold_cents":   SPEND_THRESHOLD_CENTS,
        "active_campaign_count":   count,
        "active_campaign_threshold": ACTIVE_CAMPAIGN_THRESHOLD,
    }
    if eligible:
        resp["recommended_slot"] = await recommend_slot(
            db, advertiser_id=advertiser_id,
            home_region=(ad.get("home_region") or "").lower() or None)
    if dismissed_until:
        resp["dismissed_until"] = _iso(dismissed_until)
    return resp


# ── Event tracking ──────────────────────────────────────────────
async def record_event(db, *, advertiser_id: str,
                       event_type: str,
                       context: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
    if event_type not in {"seen", "clicked", "dismissed",
                          "dismissed_permanently", "converted"}:
        raise ValueError(f"invalid_event_type:{event_type}")
    now = _now()
    ev_id = _gen("aue")
    doc = {
        "_id":                       ev_id,
        "id":                        ev_id,
        "advertiser_business_id":    advertiser_id,
        "event_type":                event_type,
        "context":                   context or {},
        "seen_at":                   now,
    }
    if event_type == "dismissed":
        dismissed_until = now + timedelta(hours=DISMISS_HOURS)
        await db.advertisers_v2.update_one(
            {"advertiser_id": advertiser_id},
            {"$set": {"upsell_dismissed_until": dismissed_until,
                      "updated_at": now}})
        doc["dismissed_until"] = dismissed_until
    elif event_type == "dismissed_permanently":
        await db.advertisers_v2.update_one(
            {"advertiser_id": advertiser_id},
            {"$set": {"upsell_lifetime_dismissed": True,
                      "updated_at": now}})
    await db.advertiser_upsell_events.insert_one(doc)
    return _shape(doc)


# ── Admin analytics ─────────────────────────────────────────────
async def admin_list_events(db, *,
                            advertiser_id: Optional[str] = None,
                            event_type: Optional[str] = None,
                            from_ts: Optional[datetime] = None,
                            to_ts: Optional[datetime] = None,
                            limit: int = 200) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_id:
        q["advertiser_business_id"] = advertiser_id
    if event_type:
        q["event_type"] = event_type
    if from_ts or to_ts:
        q["seen_at"] = {}
        if from_ts: q["seen_at"]["$gte"] = from_ts
        if to_ts:   q["seen_at"]["$lte"] = to_ts
    rows: List[Dict[str, Any]] = []
    async for e in db.advertiser_upsell_events.find(q).sort(
            "seen_at", -1).limit(limit):
        rows.append(_shape(e))
    return rows


async def admin_funnel(db) -> Dict[str, Any]:
    """Aggregate counts of seen → clicked → converted.
    `converted` is inferred: a `clicked` event by advertiser X
    followed by a `flagship_boost` payment (`payment_transactions_v2.
    flow="m4_flagship_boost"`) within 72h of that click.
    """
    counts: Dict[str, int] = {"seen": 0, "clicked": 0,
                              "dismissed": 0,
                              "dismissed_permanently": 0,
                              "converted": 0}
    async for r in db.advertiser_upsell_events.aggregate([
        {"$group": {"_id": "$event_type",
                    "count": {"$sum": 1}}},
    ]):
        counts[r["_id"]] = int(r["count"])

    # Correlate clicks → conversions.
    click_by_adv: Dict[str, List[datetime]] = {}
    async for e in db.advertiser_upsell_events.find(
            {"event_type": "clicked"},
            {"advertiser_business_id": 1, "seen_at": 1}):
        adv = e.get("advertiser_business_id")
        if not adv: continue
        click_by_adv.setdefault(adv, []).append(e["seen_at"])

    inferred_conversions = 0
    conversion_window = timedelta(hours=72)
    for adv, clicks in click_by_adv.items():
        clicks.sort()
        # Find any flagship purchase within 72h of any click.
        async for tx in db.payment_transactions_v2.find({
                "advertiser_id": adv,
                "flow":          "m4_flagship_boost"},
                {"created_at": 1}):
            purchase_ts = tx.get("created_at")
            if not isinstance(purchase_ts, datetime): continue
            for click_ts in clicks:
                if 0 <= (purchase_ts - click_ts).total_seconds() \
                        <= conversion_window.total_seconds():
                    inferred_conversions += 1
                    break

    counts["inferred_conversions_72h"] = inferred_conversions
    return {
        "counts": counts,
        "seen_to_click_rate":
            (counts["clicked"] / counts["seen"])
                if counts["seen"] else 0.0,
        "click_to_conversion_rate":
            (inferred_conversions / counts["clicked"])
                if counts["clicked"] else 0.0,
        "computed_at": _iso(_now()),
    }


__all__ = [
    "ensure_upsell_indexes", "compute_spend_30d",
    "count_active_campaigns", "recommend_slot",
    "check_eligibility", "record_event",
    "admin_list_events", "admin_funnel",
    "invalidate_spend_cache",
    "SPEND_THRESHOLD_CENTS", "ACTIVE_CAMPAIGN_THRESHOLD",
]
