"""Phase Q — QA Dashboard service.

Aggregates system health, data quality, recent activity, revenue and
open alerts across every phase.  All queries are read-only + cached
in-memory for 30 s per request key.  Alert dismissals are persisted
in `qa_dashboard_dismissals` with a 24 h suppression window.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("bigfm.qa_dashboard")

# ── Module-level constants ─────────────────────────────────────
PROCESS_START_TS = datetime.now(timezone.utc)
_SUMMARY_TTL_SEC = 30
_SUMMARY_CACHE: Dict[str, Any] = {"data": None, "ts": None}

# Campaign-style collections that share the (status, remaining_budget_cents,
# end_at, advertiser_business_id/advertiser_id) shape.  Used by data-quality
# checks + campaign counts.
CAMPAIGN_COLLECTIONS = [
    # (collection, phase_label, advertiser_field, spend_flow)
    ("coupon_campaigns",                    "Phase D · Coupons",        "advertiser_id",         "ad4_coupon_save_split"),
    ("banner_campaigns",                    "Phase AD.11 · Banners",    "advertiser_id",         "ad11_banner_impression"),
    ("notification_campaigns",              "Phase AD.12 · Notifs",     "advertiser_id",         "ad12_notification_delivery"),
    ("retargeting_campaigns",               "Phase M · Retargeting",    "advertiser_business_id","m6_retargeting_prepay"),
    ("location_boost_campaigns",            "Phase J · Location Boost", "advertiser_business_id","m2_location_boost_prepay"),
    ("marketplace_featured_slots",          "Phase K · Marketplace",    "advertiser_business_id","m3_marketplace_slot_prepay"),
    ("rj_sponsored_reads",                  "Phase I · RJ Reads",       "advertiser_business_id","m1_rj_sponsored_read_prepay"),
    ("takeover_hours",                      "Phase L · Takeover Hours", "advertiser_business_id","m5_takeover_hour_prepay"),
    ("trivia_sponsorships",                 "Phase H · Trivia Sponsor", "advertiser_business_id","ad5_trivia_sponsorship_prepay"),
    ("podcast_completion_sponsorships",     "Phase G · Podcast Comp.",  "advertiser_business_id","ad9_pc_prepay"),
]

# Payment `flow` → phase label (for revenue-by-phase bar chart).
FLOW_TO_PHASE = {
    "m4_flagship_boost":              "Phase F · Flagship Boost",
    "m1_rj_sponsored_read_prepay":    "Phase I · RJ Reads",
    "m2_location_boost_prepay":       "Phase J · Location Boost",
    "m3_marketplace_slot_prepay":     "Phase K · Marketplace",
    "m5_takeover_hour_prepay":        "Phase L · Takeover Hours",
    "m6_retargeting_prepay":          "Phase M · Retargeting",
    "m7_cpa_redeem_charge":           "Phase N · CPA Coupons",
    "ad4_coupon_save_split":          "Phase D · Coupons (CPS)",
    "ad5_trivia_sponsorship_prepay":  "Phase H · Trivia Sponsor",
    "ad9_pc_prepay":                  "Phase G · Podcast Comp.",
    "ad3_predict_win_sponsorship":    "Predict & Win",
    "ad11_banner_impression":         "Phase AD.11 · Banners",
    "ad12_notification_delivery":     "Phase AD.12 · Notifs",
    "ad2_sponsored_game_split":       "Sponsored Games",
    "ad7_scan_to_pay":                "Scan-to-Pay",
    "mer3_zero_charge":               "Merchant onboarding",
    "connect_destination":            "Stripe Connect",
}


# ── Helpers ─────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_qa_indexes(db) -> None:
    try:
        await db.qa_dashboard_dismissals.create_index("alert_type", unique=True)
    except Exception as e:
        log.warning("qa_dashboard_dismissals index setup failed: %s", e)


# ── Cache ───────────────────────────────────────────────────────
def _cache_get() -> Optional[Dict[str, Any]]:
    ts = _SUMMARY_CACHE.get("ts")
    if ts and (_now() - ts).total_seconds() < _SUMMARY_TTL_SEC:
        return _SUMMARY_CACHE.get("data")
    return None


def _cache_set(data: Dict[str, Any]) -> None:
    _SUMMARY_CACHE["data"] = data
    _SUMMARY_CACHE["ts"]   = _now()


def clear_cache() -> None:
    _SUMMARY_CACHE["data"] = None
    _SUMMARY_CACHE["ts"]   = None


# ── System health ──────────────────────────────────────────────
async def _system_health(db, app_state) -> Dict[str, Any]:
    # DB ping.
    ping_ms = None
    try:
        t0 = _now()
        await db.command("ping")
        ping_ms = int((_now() - t0).total_seconds() * 1000)
    except Exception as e:  # pragma: no cover
        log.warning("db ping failed: %s", e)

    # Uptime.
    uptime_sec = int((_now() - PROCESS_START_TS).total_seconds())

    # Background task health.
    bg_map = [
        "badge_cron_task", "dunning_cron_task", "unlock_sweep_task",
        "webhook_worker_task", "badge_sweep_task", "predict_win_sweep_task",
        "pdx_curator_task", "radio_import_task", "retention_cron_task",
        "auto_resume_task", "transcript_poll_task", "deferred_boot_task",
    ]
    bg: List[Dict[str, Any]] = []
    for attr in bg_map:
        t = getattr(app_state, attr, None) if app_state else None
        if t is None:
            bg.append({"task_name": attr, "status": "unknown",
                       "last_ran_at": None})
            continue
        done = t.done()
        exc = None
        if done:
            try:
                exc = t.exception()
            except Exception:  # pragma: no cover
                exc = None
        bg.append({
            "task_name":   attr,
            "status":      "healthy" if not done else
                           ("crashed" if exc else "completed"),
            "last_ran_at": None,   # tasks don't self-report timestamps.
        })

    # WS sessions (best-effort — trivia rooms register via SessionSocketRegistry
    # on app.state; return 0 if absent).
    ws = 0
    try:
        reg = getattr(app_state, "trivia_ws_registry", None) if app_state else None
        if reg:
            ws = getattr(reg, "active_count", 0) or 0
    except Exception:
        ws = 0

    return {
        "uptime_seconds":                        uptime_sec,
        "process_started_at":                    PROCESS_START_TS.isoformat(),
        "db_ping_ms":                            ping_ms,
        "active_websocket_sessions":             ws,
        "background_tasks_status":               bg,
        "stripe_mode":                           os.environ.get("STRIPE_MODE", "mock"),
        "emergent_llm_configured":               bool(os.environ.get("EMERGENT_LLM_KEY")),
        "elevenlabs_configured":                 bool(os.environ.get("ELEVENLABS_API_KEY")),
        "tigris_configured":                     bool(os.environ.get("TIGRIS_ACCESS_KEY_ID")),
        "google_maps_configured":                bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
        "openai_configured":                     bool(os.environ.get("OPENAI_API_KEY")),
        "env":                                   os.environ.get("ENV", "unset"),
    }


# ── Data quality ───────────────────────────────────────────────
async def _data_quality(db) -> Dict[str, Any]:
    now = _now()

    # ── Orphaned records ───────────────────────────────────
    orphans: Dict[str, int] = {}
    try:
        # coupons.source="marketplace_save" pointing to a non-existent listing
        # (rare — indicates race between save + delisting).
        pipeline = [
            {"$match": {"source": "marketplace_save"}},
            {"$lookup": {"from": "marketplace_listings",
                         "localField": "listing_id",
                         "foreignField": "id",
                         "as": "l"}},
            {"$match": {"l": {"$size": 0}}},
            {"$count": "n"},
        ]
        c = await db.coupons.aggregate(pipeline).to_list(1)
        orphans["coupons_missing_listing"] = (c[0]["n"] if c else 0)
    except Exception:
        orphans["coupons_missing_listing"] = 0

    try:
        pipeline = [
            {"$match": {"source": "marketplace_save"}},
            {"$lookup": {"from": "coupon_campaigns",
                         "localField": "campaign_id",
                         "foreignField": "id",
                         "as": "c"}},
            {"$match": {"campaign_id": {"$ne": None}, "c": {"$size": 0}}},
            {"$count": "n"},
        ]
        c = await db.coupons.aggregate(pipeline).to_list(1)
        orphans["coupons_missing_campaign"] = (c[0]["n"] if c else 0)
    except Exception:
        orphans["coupons_missing_campaign"] = 0

    try:
        pipeline = [
            {"$lookup": {"from": "marketplace_featured_slots",
                         "localField": "slot_id",
                         "foreignField": "id",
                         "as": "s"}},
            {"$match": {"s": {"$size": 0}}},
            {"$count": "n"},
        ]
        c = await db.marketplace_slot_views.aggregate(pipeline).to_list(1)
        orphans["marketplace_views_missing_slot"] = (c[0]["n"] if c else 0)
    except Exception:
        orphans["marketplace_views_missing_slot"] = 0

    try:
        pipeline = [
            {"$lookup": {"from": "marketplace_listings",
                         "localField": "listing_id",
                         "foreignField": "id",
                         "as": "l"}},
            {"$match": {"l": {"$size": 0}}},
            {"$count": "n"},
        ]
        c = await db.marketplace_saves.aggregate(pipeline).to_list(1)
        orphans["marketplace_saves_missing_listing"] = (c[0]["n"] if c else 0)
    except Exception:
        orphans["marketplace_saves_missing_listing"] = 0

    try:
        pipeline = [
            {"$lookup": {"from": "retargeting_audiences",
                         "localField": "audience_id",
                         "foreignField": "id",
                         "as": "a"}},
            {"$match": {"a": {"$size": 0}}},
            {"$count": "n"},
        ]
        c = await db.retargeting_campaigns.aggregate(pipeline).to_list(1)
        orphans["retargeting_campaigns_missing_audience"] = (c[0]["n"] if c else 0)
    except Exception:
        orphans["retargeting_campaigns_missing_audience"] = 0

    # ── Expired-but-active status ────────────────────────
    expired_active: Dict[str, int] = {}
    for coll, phase, _adv_field, _flow in CAMPAIGN_COLLECTIONS:
        try:
            n = await db[coll].count_documents({
                "status":  {"$in": ["active", "live"]},
                "end_at":  {"$lt": now},
            })
            if n > 0:
                expired_active[coll] = n
        except Exception:
            pass

    # ── Negative budget ──────────────────────────────────
    negative_budget: Dict[str, int] = {}
    for coll, _phase, _adv_field, _flow in CAMPAIGN_COLLECTIONS:
        try:
            n = await db[coll].count_documents({
                "remaining_budget_cents": {"$lt": 0}})
            if n > 0:
                negative_budget[coll] = n
        except Exception:
            pass

    # ── Stale pending_admin (> 48h) ──────────────────────
    stale_pending: Dict[str, int] = {}
    cutoff = now - timedelta(hours=48)
    for coll, _phase, _adv_field, _flow in CAMPAIGN_COLLECTIONS:
        try:
            n = await db[coll].count_documents({
                "status":                   "pending_admin",
                "$or": [{"submitted_at":    {"$lt": cutoff}},
                        {"created_at":      {"$lt": cutoff}}],
            })
            if n > 0:
                stale_pending[coll] = n
        except Exception:
            pass

    # ── Per-collection counts ────────────────────────────
    per_collection: List[Dict[str, Any]] = []
    for coll, phase, _adv_field, _flow in CAMPAIGN_COLLECTIONS:
        try:
            total     = await db[coll].estimated_document_count()
            active    = await db[coll].count_documents(
                {"status": {"$in": ["active", "live"]}})
            completed = await db[coll].count_documents(
                {"status": "completed"})
            paused    = await db[coll].count_documents(
                {"status": "paused"})
            per_collection.append({
                "collection":     coll,
                "phase":          phase,
                "total":          total,
                "active":         active,
                "completed":      completed,
                "paused":         paused,
            })
        except Exception as e:
            log.warning("count failed for %s: %s", coll, e)

    return {
        "orphaned_records":           orphans,
        "expired_but_active_status":  expired_active,
        "budget_negative":            negative_budget,
        "stale_pending_admin":        stale_pending,
        "per_collection":             per_collection,
    }


# ── Recent activity ────────────────────────────────────────────
async def _recent_activity(db) -> Dict[str, Any]:
    now = _now()
    cutoff = now - timedelta(hours=24)
    out: Dict[str, Any] = {}

    async def _count(coll: str, field: str = "created_at") -> int:
        try:
            return await db[coll].count_documents({field: {"$gte": cutoff}})
        except Exception:
            return 0

    out["new_user_signups_24h"]        = await _count("users")
    out["new_advertiser_signups_24h"]  = await _count("advertisers_v2")

    # Payments in the last 24 h.
    try:
        succeeded = await db.payment_transactions_v2.aggregate([
            {"$match": {"status":       "succeeded",
                        "succeeded_at": {"$gte": cutoff}}},
            {"$group": {"_id": None,
                        "count":   {"$sum": 1},
                        "sum":     {"$sum": "$amount_cents"}}},
        ]).to_list(1)
        out["payments_24h"] = {
            "count":       (succeeded[0]["count"] if succeeded else 0),
            "sum_cents":   (succeeded[0]["sum"]   if succeeded else 0),
        }
    except Exception:
        out["payments_24h"] = {"count": 0, "sum_cents": 0}

    # Refunds in the last 24 h.
    try:
        refunded = await db.payment_transactions_v2.aggregate([
            {"$match": {"stripe_refund_id":  {"$ne": None},
                        "refunded_at":       {"$gte": cutoff}}},
            {"$group": {"_id": None,
                        "count": {"$sum": 1},
                        "sum":   {"$sum": "$refunded_amount_cents"}}},
        ]).to_list(1)
        out["refunds_24h"] = {
            "count":     (refunded[0]["count"] if refunded else 0),
            "sum_cents": (refunded[0]["sum"]   if refunded else 0),
        }
    except Exception:
        out["refunds_24h"] = {"count": 0, "sum_cents": 0}

    # New campaigns activated by phase (activated_at within 24h).
    campaigns_activated: List[Dict[str, Any]] = []
    for coll, phase, _adv_field, _flow in CAMPAIGN_COLLECTIONS:
        try:
            n = await db[coll].count_documents({
                "$or": [{"activated_at": {"$gte": cutoff}},
                        {"created_at":   {"$gte": cutoff}}],
                "status": {"$in": ["active", "live", "completed"]},
            })
            if n > 0:
                campaigns_activated.append({"collection": coll,
                                            "phase": phase, "count": n})
        except Exception:
            pass
    campaigns_activated.sort(key=lambda x: -x["count"])
    out["campaigns_activated_24h"] = campaigns_activated

    # Notification recipes fired — top 10.
    try:
        pipeline = [
            {"$match": {"created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$recipe_id", "count": {"$sum": 1}}},
            {"$sort":  {"count": -1}},
            {"$limit": 10},
        ]
        rows = await db.notification_dispatches.aggregate(pipeline).to_list(10)
        out["notifications_top10_24h"] = [
            {"recipe_id": r["_id"], "count": r["count"]} for r in rows]
    except Exception:
        out["notifications_top10_24h"] = []

    out["podcast_completions_24h"]      = await _count("podcast_progress",
                                                       "completed_at")
    out["trivia_rooms_completed_24h"]   = await _count("trivia_sessions",
                                                       "completed_at")
    out["scan_to_pay_txns_24h"] = 0
    try:
        out["scan_to_pay_txns_24h"] = await db.payment_transactions_v2.count_documents({
            "flow":         {"$in": ["ad7_scan_to_pay", "ad7_split_share"]},
            "status":       "succeeded",
            "succeeded_at": {"$gte": cutoff},
        })
    except Exception:
        pass
    out["marketplace_saves_24h"]        = await _count("marketplace_saves",
                                                       "saved_at")
    out["retargeting_impressions_24h"]  = await _count("retargeting_impressions",
                                                       "served_at")
    return out


# ── Revenue summary ────────────────────────────────────────────
async def _revenue_summary(db) -> Dict[str, Any]:
    now = _now()
    cutoff_30d = now - timedelta(days=30)
    out: Dict[str, Any] = {}

    async def _totals(match: Dict[str, Any]) -> Dict[str, int]:
        try:
            rows = await db.payment_transactions_v2.aggregate([
                {"$match": match},
                {"$group": {
                    "_id":              None,
                    "gross_cents":      {"$sum": "$amount_cents"},
                    "platform_cents":   {"$sum": "$application_fee_cents"},
                    "count":            {"$sum": 1},
                }},
            ]).to_list(1)
            if rows:
                return {"gross_cents":    rows[0].get("gross_cents", 0)    or 0,
                        "platform_cents": rows[0].get("platform_cents", 0) or 0,
                        "count":          rows[0].get("count", 0)          or 0}
        except Exception:
            pass
        return {"gross_cents": 0, "platform_cents": 0, "count": 0}

    out["all_time"] = await _totals({"status": "succeeded"})
    out["last_30d"] = await _totals({"status":       "succeeded",
                                     "succeeded_at": {"$gte": cutoff_30d}})

    # Revenue by phase (all time, succeeded only).
    revenue_by_phase: List[Dict[str, Any]] = []
    try:
        pipeline = [
            {"$match": {"status": "succeeded"}},
            {"$group": {"_id": "$flow",
                        "gross":    {"$sum": "$amount_cents"},
                        "platform": {"$sum": "$application_fee_cents"},
                        "count":    {"$sum": 1}}},
            {"$sort": {"gross": -1}},
        ]
        rows = await db.payment_transactions_v2.aggregate(pipeline).to_list(50)
        for r in rows:
            revenue_by_phase.append({
                "flow":            r["_id"],
                "phase":           FLOW_TO_PHASE.get(r["_id"], r["_id"]),
                "gross_cents":     r.get("gross", 0) or 0,
                "platform_cents":  r.get("platform", 0) or 0,
                "count":           r.get("count", 0) or 0,
            })
    except Exception:
        pass
    out["revenue_by_phase"] = revenue_by_phase

    # Top 5 advertisers by 30d spend across the advertiser-facing flows.
    top_advertisers: List[Dict[str, Any]] = []
    try:
        pipeline = [
            {"$match": {"status":            "succeeded",
                        "succeeded_at":      {"$gte": cutoff_30d},
                        "advertiser_id":     {"$ne": None}}},
            {"$group": {"_id":               "$advertiser_id",
                        "spend":              {"$sum": "$amount_cents"},
                        "count":              {"$sum": 1}}},
            {"$sort":  {"spend": -1}},
            {"$limit": 5},
        ]
        rows = await db.payment_transactions_v2.aggregate(pipeline).to_list(5)
        # Attach display name.
        for r in rows:
            adv_id = r["_id"]
            name = None
            try:
                doc = await db.advertisers_v2.find_one(
                    {"advertiser_id": adv_id}, {"name": 1})
                if doc:
                    name = doc.get("name")
            except Exception:
                pass
            top_advertisers.append({
                "advertiser_id":  adv_id,
                "display_name":   name or adv_id,
                "spend_cents":    r.get("spend", 0) or 0,
                "txn_count":      r.get("count", 0) or 0,
            })
    except Exception:
        pass
    out["top_advertisers_30d"] = top_advertisers
    return out


# ── Open alerts ────────────────────────────────────────────────
async def _open_alerts(db, data_quality: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Derive the alert list from data_quality output, filtering out any
    that are within an active dismissal window."""
    now = _now()
    dismissed: Dict[str, datetime] = {}
    try:
        async for row in db.qa_dashboard_dismissals.find({}):
            until = row.get("dismissed_until")
            if until is None:
                continue
            # Mongo returns naive datetimes; normalize to UTC-aware so the
            # comparison against `now` (aware) doesn't throw TypeError.
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > now:
                dismissed[row["alert_type"]] = until
    except Exception as e:
        log.warning("dismissals read failed: %s", e)

    def _include(atype: str) -> bool:
        return atype not in dismissed

    alerts: List[Dict[str, Any]] = []

    for k, n in (data_quality.get("orphaned_records") or {}).items():
        if n <= 0:
            continue
        atype = f"orphaned_{k}"
        if not _include(atype):
            continue
        alerts.append({"alert_type": atype,
                       "severity":   "warn",
                       "count":      n,
                       "message":    f"{n} orphaned rows in {k}",
                       "first_seen_at": now.isoformat()})

    for coll, n in (data_quality.get("expired_but_active_status") or {}).items():
        atype = f"expired_active_{coll}"
        if not _include(atype):
            continue
        alerts.append({"alert_type": atype,
                       "severity":   "warn",
                       "count":      n,
                       "message":    f"{n} rows in {coll} are past end_at but still active/live",
                       "first_seen_at": now.isoformat()})

    for coll, n in (data_quality.get("budget_negative") or {}).items():
        atype = f"budget_negative_{coll}"
        if not _include(atype):
            continue
        alerts.append({"alert_type": atype,
                       "severity":   "critical",
                       "count":      n,
                       "message":    f"{n} rows in {coll} have remaining_budget_cents < 0 (race condition)",
                       "first_seen_at": now.isoformat()})

    for coll, n in (data_quality.get("stale_pending_admin") or {}).items():
        atype = f"stale_pending_{coll}"
        if not _include(atype):
            continue
        alerts.append({"alert_type": atype,
                       "severity":   "info",
                       "count":      n,
                       "message":    f"{n} rows in {coll} have been in pending_admin > 48 h",
                       "first_seen_at": now.isoformat()})

    return alerts


# ── Public API ────────────────────────────────────────────────
async def build_summary(db, app_state=None,
                        force_refresh: bool = False) -> Dict[str, Any]:
    if not force_refresh:
        cached = _cache_get()
        if cached:
            return {**cached, "cached": True}

    system    = await _system_health(db, app_state)
    quality   = await _data_quality(db)
    activity  = await _recent_activity(db)
    revenue   = await _revenue_summary(db)
    alerts    = await _open_alerts(db, quality)

    summary = {
        "generated_at":    _now().isoformat(),
        "system_health":   system,
        "data_quality":    quality,
        "recent_activity": activity,
        "revenue_summary": revenue,
        "open_alerts":     alerts,
        "cached":          False,
    }
    _cache_set(summary)
    return summary


async def alert_details(db, alert_type: str,
                        limit: int = 50) -> List[Dict[str, Any]]:
    """Return the offending rows for a given alert_type."""
    now = _now()
    cutoff = now - timedelta(hours=48)

    # orphaned_coupons_missing_listing
    if alert_type == "orphaned_coupons_missing_listing":
        pipeline = [
            {"$match":  {"source": "marketplace_save"}},
            {"$lookup": {"from": "marketplace_listings",
                         "localField": "listing_id",
                         "foreignField": "id",
                         "as": "l"}},
            {"$match":  {"l": {"$size": 0}}},
            {"$project": {"_id": 0, "coupon_id": 1, "listing_id": 1,
                          "user_id": 1, "saved_at": 1, "status": 1}},
            {"$limit":  limit},
        ]
        return await db.coupons.aggregate(pipeline).to_list(limit)

    if alert_type == "orphaned_coupons_missing_campaign":
        pipeline = [
            {"$match":  {"source": "marketplace_save",
                         "campaign_id": {"$ne": None}}},
            {"$lookup": {"from": "coupon_campaigns",
                         "localField": "campaign_id",
                         "foreignField": "id",
                         "as": "c"}},
            {"$match":  {"c": {"$size": 0}}},
            {"$project": {"_id": 0, "coupon_id": 1, "campaign_id": 1,
                          "user_id": 1, "saved_at": 1, "status": 1}},
            {"$limit":  limit},
        ]
        return await db.coupons.aggregate(pipeline).to_list(limit)

    if alert_type == "orphaned_marketplace_views_missing_slot":
        pipeline = [
            {"$lookup": {"from": "marketplace_featured_slots",
                         "localField": "slot_id",
                         "foreignField": "id",
                         "as": "s"}},
            {"$match":  {"s": {"$size": 0}}},
            {"$project": {"_id": 0, "id": 1, "slot_id": 1,
                          "user_id": 1, "viewed_at": 1}},
            {"$limit":  limit},
        ]
        return await db.marketplace_slot_views.aggregate(pipeline).to_list(limit)

    if alert_type == "orphaned_marketplace_saves_missing_listing":
        pipeline = [
            {"$lookup": {"from": "marketplace_listings",
                         "localField": "listing_id",
                         "foreignField": "id",
                         "as": "l"}},
            {"$match":  {"l": {"$size": 0}}},
            {"$project": {"_id": 0, "id": 1, "listing_id": 1,
                          "user_id": 1, "saved_at": 1}},
            {"$limit":  limit},
        ]
        return await db.marketplace_saves.aggregate(pipeline).to_list(limit)

    if alert_type == "orphaned_retargeting_campaigns_missing_audience":
        pipeline = [
            {"$lookup": {"from": "retargeting_audiences",
                         "localField": "audience_id",
                         "foreignField": "id",
                         "as": "a"}},
            {"$match":  {"a": {"$size": 0}}},
            {"$project": {"_id": 0, "id": 1, "audience_id": 1,
                          "advertiser_business_id": 1, "status": 1}},
            {"$limit":  limit},
        ]
        return await db.retargeting_campaigns.aggregate(pipeline).to_list(limit)

    if alert_type.startswith("expired_active_"):
        coll = alert_type[len("expired_active_"):]
        cursor = db[coll].find(
            {"status": {"$in": ["active", "live"]},
             "end_at": {"$lt": now}},
            {"_id": 0, "id": 1, "status": 1, "end_at": 1,
             "advertiser_id": 1, "advertiser_business_id": 1, "display_name": 1,
             "title": 1, "name": 1}).limit(limit)
        return await cursor.to_list(limit)

    if alert_type.startswith("budget_negative_"):
        coll = alert_type[len("budget_negative_"):]
        cursor = db[coll].find(
            {"remaining_budget_cents": {"$lt": 0}},
            {"_id": 0, "id": 1, "status": 1,
             "remaining_budget_cents": 1,
             "total_budget_cents": 1,
             "advertiser_id": 1, "advertiser_business_id": 1}).limit(limit)
        return await cursor.to_list(limit)

    if alert_type.startswith("stale_pending_"):
        coll = alert_type[len("stale_pending_"):]
        cursor = db[coll].find(
            {"status": "pending_admin",
             "$or": [{"submitted_at": {"$lt": cutoff}},
                     {"created_at":   {"$lt": cutoff}}]},
            {"_id": 0, "id": 1, "status": 1,
             "submitted_at": 1, "created_at": 1,
             "advertiser_id": 1, "advertiser_business_id": 1,
             "display_name": 1, "title": 1}).limit(limit)
        return await cursor.to_list(limit)

    raise ValueError(f"unknown_alert_type:{alert_type}")


async def dismiss_alert(db, alert_type: str, user_id: str,
                        hours: int = 24) -> Dict[str, Any]:
    now = _now()
    until = now + timedelta(hours=hours)
    doc = {
        "alert_type":         alert_type,
        "dismissed_by":       user_id,
        "dismissed_at":       now,
        "dismissed_until":    until,
        "hours":              hours,
    }
    await db.qa_dashboard_dismissals.update_one(
        {"alert_type": alert_type},
        {"$set": doc}, upsert=True)
    clear_cache()
    return {"ok": True, "alert_type": alert_type,
            "dismissed_until": until.isoformat()}


__all__ = ["ensure_qa_indexes", "build_summary", "alert_details",
           "dismiss_alert", "clear_cache", "PROCESS_START_TS"]
