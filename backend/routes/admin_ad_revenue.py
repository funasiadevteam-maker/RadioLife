"""Phase COMPANION.1 — Home Audio V2 monetization report (admin).

GET /api/admin/ad-revenue/home-report?days=7

Aggregates REAL signals from existing collections (home_ad_events,
live_radio_ad_impressions, banner_ad_impressions, listening_heartbeat_minutes)
and derives an ESTIMATED revenue proxy from configurable house CPMs. Groups
the native/sponsored/companion funnel by Home `variant` so audio_v2 can be
compared against the (deprecated) legacy Home.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request

from auth import require_admin

router = APIRouter(prefix="/api/admin/ad-revenue", tags=["admin-ad-revenue"])

# House CPM assumptions (cents per 1000 impressions) for the revenue proxy.
CPM_CENTS = {"audio": 2500, "native": 1500, "sponsored_station": 2000,
             "display": 800, "companion": 1200}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/home-report")
async def home_report(request: Request, days: int = 7,
                      _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    days = max(1, min(days, 90))
    since = _now() - timedelta(days=days)
    since_iso = since.isoformat()

    ev_counts: dict = {}
    variants: dict = {}
    cur = db.home_ad_events.aggregate([
        {"$match": {"ts": {"$gte": since_iso}}},
        {"$group": {"_id": {"event": "$event", "variant": "$variant"},
                    "n": {"$sum": 1}}},
    ])
    async for r in cur:
        ev = r["_id"].get("event")
        var = r["_id"].get("variant") or "unknown"
        ev_counts[ev] = ev_counts.get(ev, 0) + r["n"]
        variants.setdefault(var, {})
        variants[var][ev] = variants[var].get(ev, 0) + r["n"]

    audio_total = await db.live_radio_ad_impressions.count_documents(
        {"started_at": {"$gte": since}})
    audio_completed = await db.live_radio_ad_impressions.count_documents(
        {"started_at": {"$gte": since}, "completed_at": {"$ne": None}})

    banner_impr = await db.banner_ad_impressions.count_documents(
        {"ts": {"$gte": since_iso}})
    banner_clicks = await db.banner_ad_impressions.count_documents(
        {"ts": {"$gte": since_iso}, "was_clicked": True})

    listen_minutes = await db.listening_heartbeat_minutes.count_documents(
        {"created_at": {"$gte": since}})

    native_impr = ev_counts.get("native_offer_impression", 0)
    native_clicks = ev_counts.get("native_offer_click", 0)
    sp_impr = ev_counts.get("sponsored_station_impression", 0)
    sp_starts = ev_counts.get("sponsored_station_start", 0)
    comp_impr = ev_counts.get("companion_impression", 0)
    comp_clicks = ev_counts.get("companion_click", 0)
    conversions = ev_counts.get("attributed_conversion", 0)

    def _rev(n: int, k: str) -> int:
        return round((n / 1000.0) * CPM_CENTS[k])

    est_revenue_cents = (
        _rev(audio_total, "audio") + _rev(native_impr, "native")
        + _rev(sp_impr, "sponsored_station") + _rev(banner_impr, "display")
        + _rev(comp_impr, "companion"))

    listen_hours = listen_minutes / 60.0 if listen_minutes else 0.0

    def _rate(a: int, b: int) -> float:
        return round(a / b, 3) if b else 0.0

    return {
        "window_days": days,
        "listening": {
            "minutes": listen_minutes,
            "hours": round(listen_hours, 1),
            "note": ("Listening minutes come from a ~24h-TTL heartbeat "
                     "collection, so this is effectively the last ~24h."),
        },
        "audio_ads": {"impressions": audio_total, "completed": audio_completed,
                      "completion_rate": _rate(audio_completed, audio_total)},
        "native": {"impressions": native_impr, "clicks": native_clicks,
                   "ctr": _rate(native_clicks, native_impr)},
        "sponsored_station": {"impressions": sp_impr, "starts": sp_starts,
                              "start_rate": _rate(sp_starts, sp_impr)},
        "companion": {"impressions": comp_impr, "clicks": comp_clicks,
                      "ctr": _rate(comp_clicks, comp_impr)},
        "display": {"impressions": banner_impr, "clicks": banner_clicks,
                    "ctr": _rate(banner_clicks, banner_impr)},
        "conversions": conversions,
        "estimated_revenue_cents": est_revenue_cents,
        "estimated_revenue_per_listening_hour_cents":
            round(est_revenue_cents / listen_hours) if listen_hours else 0,
        "by_variant": variants,
        "variant_note": ("audio_v2 = the audio-first Home. Legacy Home emits "
                         "no audio-v2 ad events (deprecated), so its funnel "
                         "here is ~0 by design — the cleaner Home monetizes "
                         "listening time, not banner count."),
        "cpm_assumptions_cents": CPM_CENTS,
    }
