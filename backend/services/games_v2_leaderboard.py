"""Phase 8c — Top-performing campaigns leaderboard.

Single aggregation over `game_analytics_events` keyed by
(campaign_id, event_type) within a sliding window. Returns the FULL
counter set (plays, wins, saves, redemptions, completion_rate) on every
row — the chosen `metric` value is mirrored in `value` for easy sorting.
Phase 8c.1 made counters always-populated (0 when no data) so dashboards
can render sparklines without null checks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from services.games_v2 import _now


VALID_METRICS = {"plays", "wins", "saves", "redemptions", "completion_rate"}
WINDOW_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

_EVENT_FOR_METRIC = {
    "plays": "start",
    "wins": "win",
    "saves": "save_to_wallet",
    "redemptions": "redeem",
}


async def ensure_leaderboard_indexes(db) -> None:
    await db.game_analytics_events.create_index(
        [("campaign_id", 1), ("event_type", 1), ("ts", -1)])


async def compute_leaderboard(db, *, metric: str, window: str,
                                      advertiser_scope_id: Optional[str] = None,
                                      limit: int = 20) -> list[dict]:
    if metric not in VALID_METRICS:
        raise ValueError(f"invalid_metric:{metric}")
    if window not in WINDOW_DELTAS:
        raise ValueError(f"invalid_window:{window}")
    since = _now() - WINDOW_DELTAS[window]

    match: dict = {"ts": {"$gte": since},
                       "event_type": {"$in": list(_EVENT_FOR_METRIC.values())}}
    if advertiser_scope_id:
        cmp_ids = [c["campaign_id"] async for c in
                       db.game_campaigns.find(
                           {"advertiser_id": advertiser_scope_id})]
        if not cmp_ids:
            return []
        match["campaign_id"] = {"$in": cmp_ids}

    # Single aggregation that produces all 4 raw counters + completion_rate
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"campaign_id": "$campaign_id",
                      "event_type": "$event_type"},
            "n": {"$sum": 1},
        }},
        {"$group": {
            "_id": "$_id.campaign_id",
            "plays":       {"$sum": {"$cond": [
                {"$eq": ["$_id.event_type", "start"]}, "$n", 0]}},
            "wins":        {"$sum": {"$cond": [
                {"$eq": ["$_id.event_type", "win"]}, "$n", 0]}},
            "saves":       {"$sum": {"$cond": [
                {"$eq": ["$_id.event_type", "save_to_wallet"]}, "$n", 0]}},
            "redemptions": {"$sum": {"$cond": [
                {"$eq": ["$_id.event_type", "redeem"]}, "$n", 0]}},
        }},
        {"$project": {
            "plays": 1, "wins": 1, "saves": 1, "redemptions": 1,
            "completion_rate": {"$cond": [
                {"$gt": ["$plays", 0]},
                {"$divide": ["$wins", "$plays"]},
                0]},
        }},
        # Sort by the chosen metric desc
        {"$sort": {metric: -1}},
        {"$limit": limit},
    ]
    rows = await db.game_analytics_events.aggregate(pipeline).to_list(limit)

    items: list[dict] = []
    for r in rows:
        cid = r["_id"]
        c = await db.game_campaigns.find_one(
            {"campaign_id": cid},
            {"title": 1, "advertiser_id": 1, "status": 1,
              "brand_colors_json": 1, "sponsor_name": 1})
        if not c:
            continue
        comp_rate = float(r.get("completion_rate", 0))
        chosen = (round(comp_rate, 4) if metric == "completion_rate"
                     else int(r.get(metric, 0)))
        items.append({
            "rank": len(items) + 1,
            "campaign_id": cid,
            "title": c.get("title"),
            "sponsor_name": c.get("sponsor_name"),
            "status": c.get("status"),
            "metric": metric, "window": window,
            "value": chosen,
            "plays": int(r.get("plays", 0)),
            "wins": int(r.get("wins", 0)),
            "saves": int(r.get("saves", 0)),
            "redemptions": int(r.get("redemptions", 0)),
            "completion_rate": round(comp_rate, 4),
            "brand_color": (c.get("brand_colors_json") or {}).get("primary"),
        })
    return items
