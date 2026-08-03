"""Phase 36e Turn 2 — Conversion funnel analytics.

Reads from a new `funnel_events` collection (visit / play / cta-click) and
the existing `subscription_events` audit log (trial_started / trial_converted)
for the 5-stage funnel:
    1. channel_visit         → funnel_events
    2. episode_play             → funnel_events
    3. subscribe_cta_click → funnel_events
    4. trial_started            → subscription_events  (Turn 1)
    5. trial_converted        → subscription_events  (Turn 1)

All writes are dedupe-per-(listener, channel, day) — at most one row per
event type per (listener, channel) per UTC calendar day.
"""
from __future__ import annotations
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("bigfm.funnel")

FUNNEL_EVENT_TYPES = ("channel_visit", "episode_play", "subscribe_cta_click")


async def ensure_indexes(db) -> None:
    await db.funnel_events.create_index(
        [("listener_user_id", 1), ("channel_id", 1),
          ("event_type", 1), ("day_bucket", 1)],
        name="ux_funnel_dedupe", unique=True)
    await db.funnel_events.create_index(
        [("channel_id", 1), ("occurred_at", -1)])


def _now():
    return datetime.now(timezone.utc)


def _day_bucket(ts: Optional[datetime] = None) -> str:
    return (ts or _now()).strftime("%Y-%m-%d")


def _new_id(): return f"fne_{secrets.token_hex(8)}"


async def record_event(db, *, event_type: str, listener_user_id: str,
                                                channel_id: str,
                                                episode_id: Optional[str] = None) -> dict:
    """Insert one funnel event with idempotency. Returns {recorded: bool}.
    Anonymous listeners (no user_id) are silently dropped — funnel measures
    LOGGED-IN behaviour only."""
    if event_type not in FUNNEL_EVENT_TYPES:
        return {"recorded": False, "reason": "invalid_event_type"}
    if not listener_user_id or not channel_id:
        return {"recorded": False, "reason": "missing_identity"}
    await ensure_indexes(db)
    now = _now()
    doc = {
        "id":                              _new_id(),
        "event_type":              event_type,
        "listener_user_id":  listener_user_id,
        "channel_id":              channel_id,
        "episode_id":              episode_id,
        "day_bucket":              _day_bucket(now),
        "occurred_at":          now,
    }
    try:
        await db.funnel_events.insert_one(doc)
        return {"recorded": True}
    except Exception as e:
        # Dedupe collision (DuplicateKey) → silent no-op.
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            return {"recorded": False, "reason": "deduped_24h"}
        logger.warning("[funnel] insert failed: %s", e)
        raise


async def _list_creator_channels(db, creator_id: str) -> list[dict]:
    return await db.podcast_channels.find(
        {"creator_id": creator_id},
        {"_id": 0, "id": 1, "title": 1}).to_list(500)


async def _count_funnel(db, channel_ids: list[str], event_type: str,
                                              since: datetime) -> int:
    if not channel_ids: return 0
    return await db.funnel_events.count_documents({
        "channel_id":  {"$in": channel_ids},
        "event_type": event_type,
        "occurred_at": {"$gte": since}})


async def _count_subs_event(db, channel_ids: list[str], event_type: str,
                                                          since: datetime) -> int:
    """subscription_events stores `subscription_id`, not `channel_id`. We
    join via listener_subscriptions.channel_id."""
    if not channel_ids: return 0
    subs = await db.listener_subscriptions.find(
        {"channel_id": {"$in": channel_ids}},
        {"_id": 0, "id": 1}).to_list(10000)
    sub_ids = [s["id"] for s in subs]
    if not sub_ids: return 0
    return await db.subscription_events.count_documents({
        "subscription_id": {"$in": sub_ids},
        "event_type":          event_type,
        "created_at":          {"$gte": since}})


def _ratio(num: int, den: int) -> float:
    if not den: return 0.0
    return round(num / den, 4)


async def summary(db, *, creator_id: str, window_days: int = 7) -> dict:
    channels = await _list_creator_channels(db, creator_id)
    cids = [c["id"] for c in channels]
    since = _now() - timedelta(days=window_days)

    async def stats_for(cids_subset: list[str]) -> dict:
        visits = await _count_funnel(db, cids_subset, "channel_visit", since)
        plays      = await _count_funnel(db, cids_subset, "episode_play", since)
        ctas      = await _count_funnel(db, cids_subset, "subscribe_cta_click", since)
        trials    = await _count_subs_event(db, cids_subset, "trial_started", since)
        convs    = await _count_subs_event(db, cids_subset, "trial_converted", since)
        return {
            "visits": visits, "plays": plays, "cta_clicks": ctas,
            "trials": trials, "conversions": convs,
            "visit_to_play":  _ratio(plays, visits),
            "play_to_cta":      _ratio(ctas,    plays),
            "cta_to_trial":    _ratio(trials, ctas),
            "trial_to_paid":  _ratio(convs,  trials),
        }

    overall = await stats_for(cids)
    per_channel = []
    for c in channels:
        row = await stats_for([c["id"]])
        row["channel_id"]      = c["id"]
        row["channel_name"] = c.get("title") or c["id"]
        per_channel.append(row)
    # Sort by visits desc — most-active channels first.
    per_channel.sort(key=lambda r: r.get("visits", 0), reverse=True)
    return {"window_days": window_days, "overall": overall,
                  "per_channel": per_channel}


async def daily(db, *, creator_id: str, days: int = 7) -> dict:
    days = max(1, min(int(days or 7), 30))
    channels = await _list_creator_channels(db, creator_id)
    cids = [c["id"] for c in channels]
    today = _now().date()
    start = today - timedelta(days=days - 1)
    # Pre-fill zeros so gap-days appear in the output.
    series_map = {(start + timedelta(days=i)).isoformat():
                              {"date": (start + timedelta(days=i)).isoformat(),
                                "visits": 0, "plays": 0, "cta_clicks": 0,
                                "trials": 0, "conversions": 0}
                              for i in range(days)}
    if not cids:
        return {"series": [series_map[k] for k in sorted(series_map)]}

    # funnel_events grouped by day_bucket.
    cursor = db.funnel_events.aggregate([
        {"$match": {"channel_id": {"$in": cids},
                              "occurred_at": {"$gte": datetime(
                                  start.year, start.month, start.day, tzinfo=timezone.utc)}}},
        {"$group": {"_id": {"day": "$day_bucket", "type": "$event_type"},
                              "n": {"$sum": 1}}},
    ])
    async for r in cursor:
        d = r["_id"]["day"]; t = r["_id"]["type"]
        if d not in series_map: continue
        key = {"channel_visit": "visits", "episode_play": "plays",
                    "subscribe_cta_click": "cta_clicks"}.get(t)
        if key: series_map[d][key] = r["n"]

    # subscription_events (trial_started, trial_converted) joined via lsubs.
    subs = await db.listener_subscriptions.find(
        {"channel_id": {"$in": cids}}, {"_id": 0, "id": 1}).to_list(10000)
    sub_ids = [s["id"] for s in subs]
    if sub_ids:
        cur = db.subscription_events.aggregate([
            {"$match": {
                "subscription_id": {"$in": sub_ids},
                "event_type":          {"$in": ["trial_started", "trial_converted"]},
                "created_at":          {"$gte": datetime(
                    start.year, start.month, start.day, tzinfo=timezone.utc)},
            }},
            {"$project": {
                "event_type": 1,
                "day_bucket": {"$dateToString": {
                    "format": "%Y-%m-%d", "date": "$created_at"}}}},
            {"$group": {"_id": {"day": "$day_bucket", "type": "$event_type"},
                                  "n": {"$sum": 1}}},
        ])
        async for r in cur:
            d = r["_id"]["day"]; t = r["_id"]["type"]
            if d not in series_map: continue
            key = {"trial_started": "trials",
                        "trial_converted": "conversions"}.get(t)
            if key: series_map[d][key] = r["n"]

    return {"series": [series_map[k] for k in sorted(series_map)]}
