"""Phase 18c — Multi-dimension frequency capping.

Replaces the naive 1-per-10-min wall-clock check with per-user × campaign,
per-user × advertiser, and per-user × channel-cadence rules.

Default caps live in DEFAULT_CAPS and can be overridden by
`ad_campaigns.frequency_caps`.  Caps that block emit a stable `reason`
string the admin / pick-debug endpoints surface to operators.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

DEFAULT_CAPS = {
    "min_seconds_between":        600,
    "max_impressions_per_hour":   3,
    "max_impressions_per_day":    10,
    "max_per_advertiser_per_week": 50,
    "max_per_channel_cadence":    4,
}


def effective_caps(campaign: dict) -> dict:
    out = dict(DEFAULT_CAPS)
    out.update(campaign.get("frequency_caps") or {})
    return out


async def check_caps(db, *, user_id: str, campaign: dict, channel_slug: str,
                                  now: Optional[datetime] = None) -> dict:
    """Returns `{blocked: bool, reason: str|None, caps: dict}`.

    `reason` is one of `min_interval`, `hourly`, `daily`, `lifetime_weekly`,
    `channel_cadence`, or None when not blocked.
    """
    now = now or datetime.now(timezone.utc)
    caps = effective_caps(campaign)
    aid  = campaign["advertiser_id"]
    cid  = campaign["id"]

    # 1) min_seconds_between (any prior serve for this user, any campaign).
    win_iso = now - timedelta(seconds=int(caps["min_seconds_between"]))
    prior = await db.ad_serve_events.find_one({"user_id": user_id,
                                                                          "served_at": {"$gte": win_iso}})
    if prior:
        return {"blocked": True, "reason": "min_interval", "caps": caps}

    # 2) hourly per-campaign.
    h_ago = now - timedelta(hours=1)
    hour_n = await db.ad_serve_events.count_documents(
        {"user_id": user_id, "campaign_id": cid, "served_at": {"$gte": h_ago}})
    if hour_n >= int(caps["max_impressions_per_hour"]):
        return {"blocked": True, "reason": "hourly", "caps": caps}

    # 3) daily per-campaign.
    d_ago = now - timedelta(days=1)
    day_n = await db.ad_serve_events.count_documents(
        {"user_id": user_id, "campaign_id": cid, "served_at": {"$gte": d_ago}})
    if day_n >= int(caps["max_impressions_per_day"]):
        return {"blocked": True, "reason": "daily", "caps": caps}

    # 4) lifetime per-advertiser per week.
    w_ago = now - timedelta(days=7)
    wk_n = await db.ad_serve_events.count_documents(
        {"user_id": user_id, "advertiser_id": aid, "served_at": {"$gte": w_ago}})
    if wk_n >= int(caps["max_per_advertiser_per_week"]):
        return {"blocked": True, "reason": "lifetime_weekly", "caps": caps}

    # 5) channel cadence — "max 1 ad per N songs" approximated as
    #     "no more than 1 ad in the last N×30s on this channel".
    cadence_secs = int(caps["max_per_channel_cadence"]) * 30
    cad_ago = now - timedelta(seconds=cadence_secs)
    cad_n = await db.ad_serve_events.count_documents(
        {"user_id": user_id, "channel_slug": channel_slug,
          "served_at": {"$gte": cad_ago}})
    if cad_n >= 1:
        return {"blocked": True, "reason": "channel_cadence", "caps": caps}

    return {"blocked": False, "reason": None, "caps": caps}


async def record_serve_event(db, *, serve_doc: dict) -> None:
    """Mirror an `ad_serves` insert into `ad_serve_events` (the cap-counting
    collection).  Keeping them separate so we can prune `ad_serve_events`
    aggressively without losing financial truth."""
    evt = {k: serve_doc.get(k) for k in
              ("id", "user_id", "campaign_id", "advertiser_id",
                "channel_slug", "served_at", "completed",
                "cost_usd", "was_takeover")}
    evt["serve_id"] = serve_doc.get("id")
    await db.ad_serve_events.insert_one(evt)
