"""Phase 12a — Admin Analytics Dashboard.

Seven read-only aggregation endpoints over real Mongo collections.  All
admin-gated.  When a source collection is empty / a metric depends on an
integration that is not yet live (GAM, programmatic fill, etc.), the
endpoint surfaces a `missing_data_flags` array instead of fabricating a
number.

Response envelope (all endpoints):
    {
        "range": "7d" | "30d" | "90d",
        "generated_at": "<ISO>",
        "data": { ... },
        "missing_data_flags": [ "<field_name>", ... ]
    }
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin

logger = logging.getLogger("bigfm.admin.analytics")

admin_analytics_router = APIRouter(
    prefix="/api/admin/analytics", tags=["admin-analytics"]
)


# ─── In-memory health counters (process-local; cleared on restart) ──────
# ffmpeg concat failures are not persisted, so we keep a rolling counter
# that the radio pipeline can `inc` into via app.state.
def get_health_counters(request: Request) -> dict:
    state = request.app.state
    if not hasattr(state, "health_counters"):
        state.health_counters = {
            "ffmpeg_concat_failures": 0,
            "ffmpeg_concat_total": 0,
            "ai_rj_failures": 0,
            "ai_rj_total": 0,
            "ws_disconnects": 0,
            "ws_connects": 0,
            "process_started_at": datetime.now(timezone.utc).isoformat(),
        }
    return state.health_counters


# ─── Range helpers ──────────────────────────────────────────────────────
_RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def _parse_range(s: str) -> int:
    if s not in _RANGE_DAYS:
        raise HTTPException(400, f"range must be one of {list(_RANGE_DAYS)}")
    return _RANGE_DAYS[s]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cutoff(days: int) -> datetime:
    return _now() - timedelta(days=days)


def _envelope(data: dict, range_s: str, flags: list[str]) -> dict:
    return {
        "range": range_s,
        "generated_at": _now().isoformat(),
        "data": data,
        "missing_data_flags": flags,
    }


async def _has_any(db, collection: str) -> bool:
    """Cheap existence check — returns True if the collection has at least
    one document.  Used to drive `missing_data_flags` instead of returning
    fake zeros for absent telemetry."""
    try:
        return await db[collection].find_one({}, {"_id": 1}) is not None
    except Exception:
        return False


# ────────────────────────────────────────────────────────────────────────
# 1. OVERVIEW
# ────────────────────────────────────────────────────────────────────────
@admin_analytics_router.get("/overview")
async def overview(request: Request,
                   range: str = Query("7d"),
                   _admin=Depends(require_admin)):
    db = request.app.state.db
    days = _parse_range(range)
    since = _cutoff(days)
    flags: list[str] = []
    data: dict = {}

    # DAU/WAU/MAU from playback_logs `play_start` events
    if not await _has_any(db, "playback_logs"):
        flags.append("dau_wau_mau")
        data.update({"dau": None, "wau": None, "mau": None})
    else:
        async def _distinct_users(cutoff: datetime) -> int:
            vals = await db.playback_logs.distinct(
                "user_id", {"event": "play_start", "timestamp": {"$gte": cutoff}})
            return len([v for v in vals if v])
        data["dau"] = await _distinct_users(_now() - timedelta(days=1))
        data["wau"] = await _distinct_users(_now() - timedelta(days=7))
        data["mau"] = await _distinct_users(_now() - timedelta(days=30))

    # Total listening hours from listening_heartbeats
    if await _has_any(db, "listening_heartbeats"):
        pipe = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {"_id": None,
                          "total_min": {"$sum": "$minutes_credited"}}},
        ]
        doc = await db.listening_heartbeats.aggregate(pipe).to_list(1)
        total_min = int(doc[0]["total_min"]) if doc else 0
        data["listening_hours_total"] = round(total_min / 60.0, 2)
    else:
        flags.append("listening_hours_total")
        data["listening_hours_total"] = None

    # Top channels (top 10) by play_start count
    if await _has_any(db, "playback_logs"):
        pipe = [
            {"$match": {"event": "play_start",
                          "timestamp": {"$gte": since},
                          "channel_slug": {"$ne": None}}},
            {"$group": {"_id": "$channel_slug", "plays": {"$sum": 1}}},
            {"$sort": {"plays": -1}},
            {"$limit": 10},
        ]
        chans = []
        async for r in db.playback_logs.aggregate(pipe):
            chans.append({"channel_slug": r["_id"], "plays": int(r["plays"])})
        data["top_channels"] = chans
    else:
        data["top_channels"] = []

    # Skip rate = skips / total play_start in window
    if await _has_any(db, "playback_logs"):
        total = await db.playback_logs.count_documents(
            {"event": "play_start", "timestamp": {"$gte": since}})
        skipped = await db.playback_logs.count_documents(
            {"event": "skip", "timestamp": {"$gte": since}})
        data["skip_rate"] = round(skipped / total, 4) if total else 0.0
        data["plays_total"] = total
        data["skips_total"] = skipped
    else:
        data["skip_rate"] = None

    # AI RJ engagement — share of segments where users did NOT skip the
    # RJ.  Surrogate: rj_quality_votes count vs play_start count.
    if await _has_any(db, "rj_quality_votes"):
        votes = await db.rj_quality_votes.count_documents(
            {"created_at": {"$gte": since}})
        plays_with_rj = await db.playback_logs.count_documents(
            {"event": "play_start", "timestamp": {"$gte": since}})
        rate = (votes / plays_with_rj) if plays_with_rj else 0.0
        data["ai_rj_engagement"] = {"votes": votes,
                                        "plays_with_rj": plays_with_rj,
                                        "rate": round(rate, 4)}
    else:
        flags.append("ai_rj_engagement")
        data["ai_rj_engagement"] = None

    # Premium conversion rate
    total_users = await db.users.count_documents({})
    premium_users = await db.users.count_documents({"is_premium": True})
    data["premium_conversion_rate"] = (
        round(premium_users / total_users, 4) if total_users else 0.0)
    data["premium_users"] = premium_users
    data["total_users"] = total_users

    # Rewards liability — Phase F-2 sources the outstanding balance
    # from the unified `points_ledger` (sum of all deltas, all users).
    pipe = [{"$group": {"_id": None,
                              "total": {"$sum": "$delta"}}}]
    doc = await db.points_ledger.aggregate(pipe).to_list(1)
    data["rewards_liability_bigcoin"] = int(doc[0]["total"]) if doc else 0

    # Revenue by channel / total (cents) from ad_impressions
    if await _has_any(db, "ad_impressions"):
        pipe = [
            {"$match": {"served_at": {"$gte": since}}},
            {"$group": {"_id": "$channel_slug",
                          "rev_cents": {"$sum": "$attributed_revenue_cents"},
                          "imps": {"$sum": 1}}},
            {"$sort": {"rev_cents": -1}},
            {"$limit": 10},
        ]
        by = []
        async for r in db.ad_impressions.aggregate(pipe):
            by.append({"channel_slug": r["_id"],
                          "revenue_cents": int(r["rev_cents"] or 0),
                          "impressions": int(r["imps"])})
        data["revenue_by_channel"] = by
        data["revenue_total_cents"] = sum(b["revenue_cents"] for b in by)
    else:
        flags.append("revenue_by_channel")
        flags.append("revenue_total_cents")
        data["revenue_by_channel"] = []
        data["revenue_total_cents"] = None

    return _envelope(data, range, flags)


# ────────────────────────────────────────────────────────────────────────
# 2. SONGS
# ────────────────────────────────────────────────────────────────────────
@admin_analytics_router.get("/songs")
async def songs(request: Request,
                  range: str = Query("7d"),
                  limit: int = Query(50, ge=1, le=200),
                  _admin=Depends(require_admin)):
    db = request.app.state.db
    days = _parse_range(range)
    since = _cutoff(days)
    flags: list[str] = []

    if not await _has_any(db, "playback_logs"):
        flags.append("songs")
        return _envelope({"top_played": [], "most_skipped": [],
                              "top_liked": []}, range, flags)

    # Per-track aggregates
    pipe = [
        {"$match": {"timestamp": {"$gte": since},
                       "track_id": {"$ne": None},
                       "event": {"$in": ["play_start", "play_complete",
                                              "skip"]}}},
        {"$group": {"_id": {"track_id": "$track_id",
                                "event": "$event"},
                       "count": {"$sum": 1}}},
    ]
    agg: dict[str, dict] = {}
    async for r in db.playback_logs.aggregate(pipe):
        tid = r["_id"]["track_id"]
        ev = r["_id"]["event"]
        agg.setdefault(tid, {"plays": 0, "completes": 0, "skips": 0})
        if ev == "play_start":
            agg[tid]["plays"] = int(r["count"])
        elif ev == "play_complete":
            agg[tid]["completes"] = int(r["count"])
        elif ev == "skip":
            agg[tid]["skips"] = int(r["count"])

    # Resolve titles in one round-trip
    tids = list(agg.keys())
    titles: dict[str, dict] = {}
    if tids:
        cur = db.tracks.find({"_id": {"$in": tids}},
                                  {"title": 1, "artist": 1})
        async for t in cur:
            titles[t["_id"]] = {"title": t.get("title"),
                                  "artist": t.get("artist")}

    items: list[dict] = []
    for tid, c in agg.items():
        plays = c["plays"]
        skip_rate = (c["skips"] / plays) if plays else 0.0
        completion = (c["completes"] / plays) if plays else 0.0
        items.append({
            "track_id": tid,
            "title": titles.get(tid, {}).get("title"),
            "artist": titles.get(tid, {}).get("artist"),
            "plays": plays, "skips": c["skips"],
            "completes": c["completes"],
            "skip_rate": round(skip_rate, 4),
            "completion_rate": round(completion, 4),
        })

    top_played = sorted(items, key=lambda x: x["plays"],
                              reverse=True)[:limit]
    most_skipped = sorted(
        [i for i in items if i["plays"] >= 3],   # min sample
        key=lambda x: x["skip_rate"], reverse=True)[:limit]

    # top_liked — surfaced only if rj_quality_votes carries a track_id
    if await _has_any(db, "rj_quality_votes"):
        pipe = [{"$match": {"created_at": {"$gte": since},
                                  "track_id": {"$ne": None}}},
                  {"$group": {"_id": "$track_id",
                                 "likes": {"$sum": 1}}},
                  {"$sort": {"likes": -1}},
                  {"$limit": limit}]
        liked = []
        async for r in db.rj_quality_votes.aggregate(pipe):
            tid = r["_id"]
            liked.append({"track_id": tid,
                              "title": titles.get(tid, {}).get("title"),
                              "likes": int(r["likes"])})
        top_liked = liked
    else:
        flags.append("top_liked")
        top_liked = []

    return _envelope({"top_played": top_played,
                          "most_skipped": most_skipped,
                          "top_liked": top_liked}, range, flags)


# ────────────────────────────────────────────────────────────────────────
# 3. ADS
# ────────────────────────────────────────────────────────────────────────
@admin_analytics_router.get("/ads")
async def ads(request: Request,
                  range: str = Query("7d"),
                  _admin=Depends(require_admin)):
    db = request.app.state.db
    days = _parse_range(range)
    since = _cutoff(days)
    flags: list[str] = []
    data: dict = {}

    if await _has_any(db, "ad_impressions"):
        imps = await db.ad_impressions.count_documents(
            {"served_at": {"$gte": since}})
        completed = await db.ad_impressions.count_documents(
            {"served_at": {"$gte": since}, "completion_pct": {"$gte": 0.99}})
        data["impressions"] = imps
        data["completed_listens"] = completed
        data["completion_rate"] = round(completed / imps, 4) if imps else 0.0
    else:
        flags += ["impressions", "completed_listens", "completion_rate"]
        data["impressions"] = None
        data["completed_listens"] = None
        data["completion_rate"] = None

    # Click telemetry — coupon_saves, direction_clicks, etc.
    if await _has_any(db, "ad_clicks"):
        pipe = [
            {"$match": {"clicked_at": {"$gte": since}}},
            {"$group": {"_id": "$action_type", "count": {"$sum": 1}}},
        ]
        by_action: dict[str, int] = {}
        async for r in db.ad_clicks.aggregate(pipe):
            by_action[r["_id"] or "unknown"] = int(r["count"])
        data["coupon_saves"] = by_action.get("save_coupon", 0)
        data["direction_clicks"] = by_action.get("get_directions", 0)
        data["share_clicks"] = by_action.get("share", 0)
        data["reserve_clicks"] = by_action.get("reserve_table", 0)
        data["buy_now_clicks"] = by_action.get("buy_now", 0)
        data["all_click_actions"] = by_action
    else:
        flags += ["coupon_saves", "direction_clicks"]
        data["coupon_saves"] = None
        data["direction_clicks"] = None
        data["all_click_actions"] = {}

    # Check-ins
    if await _has_any(db, "offer_redemptions_audit"):
        data["check_ins"] = await db.offer_redemptions_audit.count_documents(
            {"ts": {"$gte": since}, "result": "ok"})
    else:
        flags.append("check_ins")
        data["check_ins"] = None

    # Reward redemptions
    if await _has_any(db, "bigcoin_redemptions"):
        data["redemptions"] = await db.bigcoin_redemptions.count_documents(
            {"created_at": {"$gte": since}})
    else:
        flags.append("redemptions")
        data["redemptions"] = None

    # By advertiser / campaign (impressions, revenue)
    if await _has_any(db, "ad_impressions"):
        pipe = [
            {"$match": {"served_at": {"$gte": since}}},
            {"$group": {"_id": "$campaign_id",
                            "imps": {"$sum": 1},
                            "rev_cents": {"$sum": "$attributed_revenue_cents"},
                            "completed": {"$sum": {"$cond": [
                                {"$gte": ["$completion_pct", 0.99]}, 1, 0]}}}},
            {"$sort": {"imps": -1}},
            {"$limit": 10},
        ]
        by_campaign = []
        camp_ids = []
        async for r in db.ad_impressions.aggregate(pipe):
            camp_ids.append(r["_id"])
            by_campaign.append({
                "campaign_id": r["_id"], "impressions": int(r["imps"]),
                "completed_listens": int(r["completed"]),
                "revenue_cents": int(r["rev_cents"] or 0),
            })
        # Resolve campaign + advertiser names
        camps = {}
        if camp_ids:
            cur = db.campaigns.find({"campaign_id": {"$in": camp_ids}})
            async for c in cur:
                camps[c["campaign_id"]] = {
                    "name": c.get("name"),
                    "advertiser_id": c.get("advertiser_id"),
                    "business_id": c.get("business_id"),
                }
        for row in by_campaign:
            meta = camps.get(row["campaign_id"], {})
            row["campaign_name"] = meta.get("name")
            row["advertiser_id"] = meta.get("advertiser_id")
            row["business_id"] = meta.get("business_id")
        data["by_campaign"] = by_campaign

        # Roll up by advertiser
        adv_agg: dict[str, dict] = {}
        for row in by_campaign:
            aid = row.get("advertiser_id") or "unknown"
            a = adv_agg.setdefault(aid, {
                "advertiser_id": aid,
                "impressions": 0, "completed_listens": 0,
                "revenue_cents": 0})
            a["impressions"] += row["impressions"]
            a["completed_listens"] += row["completed_listens"]
            a["revenue_cents"] += row["revenue_cents"]
        data["by_advertiser"] = sorted(
            adv_agg.values(), key=lambda r: r["revenue_cents"],
            reverse=True)[:10]

        # eCPM and fill_rate require GAM attribution which is not live.
        flags.append("eCPM")
        flags.append("fill_rate")
        data["eCPM"] = None
        data["fill_rate"] = None
    else:
        data["by_campaign"] = []
        data["by_advertiser"] = []
        flags += ["eCPM", "fill_rate"]
        data["eCPM"] = None
        data["fill_rate"] = None

    return _envelope(data, range, flags)


# ────────────────────────────────────────────────────────────────────────
# 4. COMMUTE
# ────────────────────────────────────────────────────────────────────────
@admin_analytics_router.get("/commute")
async def commute(request: Request,
                    range: str = Query("7d"),
                    _admin=Depends(require_admin)):
    db = request.app.state.db
    days = _parse_range(range)
    since = _cutoff(days)
    flags: list[str] = []
    data: dict = {}

    if not await _has_any(db, "route_ad_opportunities"):
        flags.append("route_ad_impressions")
        flags.append("by_trigger")
        return _envelope({"route_ad_impressions": None,
                              "route_ad_conversion_rate": None,
                              "by_trigger": []}, range, flags)

    # Impressions via ad_impressions with route_opp_id set; fall back to
    # decision log otherwise.
    imps = 0
    if await _has_any(db, "ad_pods"):
        imps = await db.ad_pods.count_documents(
            {"served_at": {"$gte": since},
              "route_opp_id": {"$exists": True, "$ne": None}})
    data["route_ad_impressions"] = imps

    # Engagement (any click on route-flagged ad)
    engaged = 0
    if await _has_any(db, "ad_clicks"):
        # Need to join via ad_pod_id but it's expensive; approximate by
        # counting pod_ids that have a route_opp_id and matching clicks.
        pod_ids: list[str] = []
        cur = db.ad_pods.find(
            {"served_at": {"$gte": since},
              "route_opp_id": {"$exists": True, "$ne": None}},
            {"_id": 1})
        async for p in cur:
            pod_ids.append(p["_id"])
        if pod_ids:
            engaged = await db.ad_clicks.count_documents(
                {"ad_pod_id": {"$in": pod_ids},
                  "clicked_at": {"$gte": since}})
    data["route_ad_engagements"] = engaged
    data["route_ad_conversion_rate"] = (
        round(engaged / imps, 4) if imps else 0.0)

    # By trigger from route_ad_decision_log
    if await _has_any(db, "route_ad_decision_log"):
        pipe = [
            {"$match": {"ts": {"$gte": since}}},
            {"$group": {"_id": {"$ifNull": ["$trigger_kind", "unknown"]},
                          "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        rows = []
        async for r in db.route_ad_decision_log.aggregate(pipe):
            rows.append({"trigger": r["_id"], "count": int(r["count"])})
        data["by_trigger"] = rows
    else:
        flags.append("by_trigger")
        data["by_trigger"] = []

    return _envelope(data, range, flags)


# ────────────────────────────────────────────────────────────────────────
# 5. GAMES
# ────────────────────────────────────────────────────────────────────────
@admin_analytics_router.get("/games")
async def games(request: Request,
                  range: str = Query("7d"),
                  _admin=Depends(require_admin)):
    db = request.app.state.db
    days = _parse_range(range)
    since = _cutoff(days)
    flags: list[str] = []
    data: dict = {}

    # Participation by game_type via game_sessions
    if await _has_any(db, "game_sessions"):
        pipe = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {"_id": "$game_type",
                          "plays": {"$sum": 1},
                          "wins": {"$sum": {"$cond": [
                              {"$eq": ["$result", "won"]}, 1, 0]}}}},
            {"$sort": {"plays": -1}},
        ]
        rows = []
        total = 0
        async for r in db.game_sessions.aggregate(pipe):
            plays = int(r["plays"])
            rows.append({
                "game_type": r["_id"] or "unknown",
                "plays": plays, "wins": int(r["wins"]),
                "win_rate": round(r["wins"] / plays, 4) if plays else 0.0,
            })
            total += plays
        data["by_game_type"] = rows
        data["plays_total"] = total
    else:
        flags.append("by_game_type")
        data["by_game_type"] = []
        data["plays_total"] = None

    # Rewards issued via bigcoin_transactions (earn from games)
    if await _has_any(db, "bigcoin_transactions"):
        pipe = [
            {"$match": {"created_at": {"$gte": since},
                          "type": "earn",
                          "source": {"$in": [
                              "game_spin_win", "game_complete_lyric",
                              "game_music_trivia", "games_v2_prize",
                              "game_win", "games_v2"]}}},
            {"$group": {"_id": None,
                          "total": {"$sum": "$amount"},
                          "count": {"$sum": 1}}},
        ]
        doc = await db.bigcoin_transactions.aggregate(pipe).to_list(1)
        data["rewards_issued_bigcoin"] = int(doc[0]["total"]) if doc else 0
        data["rewards_issued_count"] = int(doc[0]["count"]) if doc else 0
    else:
        flags.append("rewards_issued_bigcoin")
        data["rewards_issued_bigcoin"] = None
        data["rewards_issued_count"] = None

    # Claim rate — claimed prizes / wins.  Use games_v2 leaderboard / prizes
    if await _has_any(db, "game_sessions"):
        wins = await db.game_sessions.count_documents(
            {"created_at": {"$gte": since}, "result": "won"})
        claimed = await db.game_sessions.count_documents(
            {"created_at": {"$gte": since}, "result": "won",
              "claimed": True})
        data["wins"] = wins
        data["claimed"] = claimed
        data["claim_rate"] = round(claimed / wins, 4) if wins else 0.0
    else:
        flags.append("claim_rate")
        data["claim_rate"] = None

    # Lead form completion rate
    if await _has_any(db, "game_lead_forms") and await _has_any(
            db, "game_lead_submissions"):
        forms = await db.game_lead_forms.count_documents(
            {"created_at": {"$gte": since}})
        subs = await db.game_lead_submissions.count_documents(
            {"created_at": {"$gte": since}})
        data["lead_forms_active"] = forms
        data["lead_submissions"] = subs
        # Per-form completion: submissions / impressions (best-effort)
        if await _has_any(db, "game_analytics_events"):
            impressions = await db.game_analytics_events.count_documents(
                {"ts": {"$gte": since}, "event_type": "lead_form_view"})
            data["lead_form_completion_rate"] = (
                round(subs / impressions, 4) if impressions else 0.0)
        else:
            flags.append("lead_form_completion_rate")
            data["lead_form_completion_rate"] = None
    else:
        flags.append("lead_form_completion_rate")
        data["lead_form_completion_rate"] = None

    return _envelope(data, range, flags)


# ────────────────────────────────────────────────────────────────────────
# 6. REVENUE
# ────────────────────────────────────────────────────────────────────────
@admin_analytics_router.get("/revenue")
async def revenue(request: Request,
                    range: str = Query("7d"),
                    _admin=Depends(require_admin)):
    db = request.app.state.db
    days = _parse_range(range)
    since = _cutoff(days)
    flags: list[str] = []
    data: dict = {}

    # Subscription MRR — sum of active subscribers' plan prices (cents).
    # We approximate from `users.subscription` snapshot.
    pipe = [
        {"$match": {"is_premium": True,
                       "subscription.status": {"$in": [
                           "active", "trialing", "past_due"]}}},
        {"$group": {"_id": None, "count": {"$sum": 1}}},
    ]
    doc = await db.users.aggregate(pipe).to_list(1)
    active_subs = int(doc[0]["count"]) if doc else 0
    data["active_subscriptions"] = active_subs

    # Pull canonical plan prices to compute MRR
    plan_prices: dict[str, int] = {}
    if await _has_any(db, "plans"):
        async for p in db.plans.find({}):
            cents = int(p.get("monthly_price_cents")
                              or p.get("price_cents") or 0)
            plan_prices[p.get("plan_id") or p.get("_id")] = cents
    # Sum per-user plan price; fall back to $9.99 (999c) if plan missing.
    DEFAULT_MRR_CENTS = 999
    pipe = [
        {"$match": {"is_premium": True,
                       "subscription.status": {"$in": [
                           "active", "trialing", "past_due"]}}},
        {"$group": {"_id": "$premium_tier", "count": {"$sum": 1}}},
    ]
    mrr_total = 0
    tier_breakdown = []
    async for r in db.users.aggregate(pipe):
        tier = r["_id"] or "premium"
        cents = plan_prices.get(tier) or plan_prices.get("premium") \
                  or DEFAULT_MRR_CENTS
        tier_breakdown.append({"tier": tier, "subscribers": int(r["count"]),
                                  "monthly_price_cents": cents})
        mrr_total += cents * int(r["count"])
    data["subscription_mrr_cents"] = mrr_total
    data["mrr_breakdown"] = tier_breakdown

    # Churn — cancellations in window / active at window-start.  Use
    # subscription_lifecycle_log if present.
    if await _has_any(db, "subscription_lifecycle_log"):
        churned = await db.subscription_lifecycle_log.count_documents(
            {"ts": {"$gte": since},
              "to_state": {"$in": ["canceled", "incomplete_expired",
                                          "unpaid"]}})
        baseline = active_subs + churned
        data["subscription_churn"] = {
            "churned_in_window": churned,
            "baseline_active": baseline,
            "churn_rate": round(churned / baseline, 4) if baseline else 0.0,
        }
    else:
        flags.append("subscription_churn")
        data["subscription_churn"] = None

    # Advertiser revenue (cents) — sum of attributed_revenue_cents in window
    if await _has_any(db, "ad_impressions"):
        pipe = [
            {"$match": {"served_at": {"$gte": since}}},
            {"$group": {"_id": None,
                          "rev": {"$sum": "$attributed_revenue_cents"},
                          "imps": {"$sum": 1}}},
        ]
        doc = await db.ad_impressions.aggregate(pipe).to_list(1)
        rev = int(doc[0]["rev"] or 0) if doc else 0
        imps = int(doc[0]["imps"]) if doc else 0
        data["advertiser_revenue_cents"] = rev
        data["ad_impressions"] = imps
    else:
        flags.append("advertiser_revenue_cents")
        data["advertiser_revenue_cents"] = None
        data["ad_impressions"] = None

    # eCPM and programmatic fill rate are NULL until GAM is live (Phase 12d).
    flags.append("eCPM")
    flags.append("programmatic_fill_rate")
    data["eCPM"] = None
    data["programmatic_fill_rate"] = None

    return _envelope(data, range, flags)


# ────────────────────────────────────────────────────────────────────────
# 7. HEALTH
# ────────────────────────────────────────────────────────────────────────
@admin_analytics_router.get("/health")
async def health(request: Request,
                    _admin=Depends(require_admin)):
    db = request.app.state.db
    flags: list[str] = []
    data: dict = {}

    # Cold-start segment latency p50/p95 from playback_logs.prewarm_ms
    if await _has_any(db, "playback_logs"):
        pipe = [
            {"$match": {"prewarm_ms": {"$exists": True, "$ne": None}}},
            {"$sort": {"timestamp": -1}},
            {"$limit": 500},
            {"$group": {"_id": None, "values": {"$push": "$prewarm_ms"}}},
        ]
        doc = await db.playback_logs.aggregate(pipe).to_list(1)
        vals = sorted([int(v) for v in (doc[0]["values"] if doc else [])
                        if v is not None])
        if vals:
            p50 = vals[int(len(vals) * 0.5)]
            p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
            data["cold_start_segment_latency_p50_ms"] = p50
            data["cold_start_segment_latency_p95_ms"] = p95
            data["cold_start_sample_size"] = len(vals)
        else:
            flags.append("cold_start_segment_latency")
            data["cold_start_segment_latency_p50_ms"] = None
            data["cold_start_segment_latency_p95_ms"] = None
            data["cold_start_sample_size"] = 0
    else:
        flags.append("cold_start_segment_latency")
        data["cold_start_segment_latency_p50_ms"] = None
        data["cold_start_segment_latency_p95_ms"] = None

    # AI RJ generation failure rate (in-memory counter)
    hc = get_health_counters(request)
    if hc["ai_rj_total"] > 0:
        data["ai_rj_generation_failure_rate"] = round(
            hc["ai_rj_failures"] / hc["ai_rj_total"], 4)
    else:
        flags.append("ai_rj_generation_failure_rate")
        data["ai_rj_generation_failure_rate"] = None
    data["ai_rj_attempts_since_boot"] = hc["ai_rj_total"]
    data["ai_rj_failures_since_boot"] = hc["ai_rj_failures"]

    if hc["ffmpeg_concat_total"] > 0:
        data["ffmpeg_concat_failure_rate"] = round(
            hc["ffmpeg_concat_failures"] / hc["ffmpeg_concat_total"], 4)
    else:
        flags.append("ffmpeg_concat_failure_rate")
        data["ffmpeg_concat_failure_rate"] = None
    data["ffmpeg_concat_attempts_since_boot"] = hc["ffmpeg_concat_total"]
    data["ffmpeg_concat_failures_since_boot"] = hc["ffmpeg_concat_failures"]

    # Active lobbies (status=live)
    if await _has_any(db, "lobbies"):
        data["active_lobbies"] = await db.lobbies.count_documents(
            {"status": "live"})
    else:
        data["active_lobbies"] = 0

    # WS connect / disconnect (best effort — counters that bump from
    # lobby_hub if instrumented; otherwise NULL)
    if hc["ws_connects"] > 0:
        data["ws_disconnect_rate"] = round(
            hc["ws_disconnects"] / hc["ws_connects"], 4)
    else:
        flags.append("ws_disconnect_rate")
        data["ws_disconnect_rate"] = None
    data["ws_connects_since_boot"] = hc["ws_connects"]
    data["ws_disconnects_since_boot"] = hc["ws_disconnects"]
    data["process_started_at"] = hc["process_started_at"]

    return _envelope(data, "instant", flags)
