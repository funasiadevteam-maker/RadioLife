"""Phase 42-E1 — Banner-ad provider for persistent placements.

This is the persistent-banner sibling of `services/ssp_ad_provider.py`
(pre-roll audio).  It implements the same waterfall pattern:

    direct-sold `banner_persistent` campaign matching targeting
    → SSP banner backfill (mocked for now, TODO real OpenRTB)
    → null

Selection rules
---------------
1. Premium users → always null (banner ads are free-tier only).
2. Match active `advertiser_campaigns` where:
       campaign_type == "banner_persistent"
       AND status == "live"
       AND placements ∋ <placement>
       AND targeting matches (city / weather / time-of-day / channel)
3. Honor `frequency_cap_per_user_per_day` (default 20) — track impressions
     in `banner_ad_impressions` collection.
4. If multiple match, prefer highest `bid_cpm_cents` (or `priority`),
     ties broken random.

Endpoints (mounted by `routes/banner_ads.py`)
---------------------------------------------
    POST /api/banner-ads/request           — returns {has_ad, ad?, source}
    POST /api/banner-ads/impression       — logs that the slot rendered
    POST /api/banner-ads/click                  — logs a click for attribution
"""
from __future__ import annotations

import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("bigfm.banner_ads")


VALID_PLACEMENTS = {
    "miniplayer", "commute_map", "predict_win_list", "news_local", "generic",
}
DEFAULT_FREQ_CAP = 20


# ─── Bootstrap ─────────────────────────────────────────────────────
async def ensure_banner_ad_indexes(db) -> None:
    """Idempotent — safe to call on every boot."""
    await db.banner_ad_impressions.create_index(
        [("user_id", 1), ("created_at", -1)], name="bai_user_time")
    await db.banner_ad_impressions.create_index(
        [("user_id", 1), ("campaign_id", 1), ("created_at", -1)],
        name="bai_user_camp_time")
    await db.banner_ad_impressions.create_index(
        "impression_token", unique=True,
        partialFilterExpression={"impression_token": {"$type": "string"}},
        name="bai_token_uniq")
    # Existing advertiser_campaigns gets a placement index used during select.
    await db.advertiser_campaigns.create_index(
        [("campaign_type", 1), ("status", 1), ("placements", 1)],
        name="ac_type_status_place")
    log.info("[banner_ads] indexes ensured")


# ─── Helpers ──────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _is_premium(db, user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    u = await db.users.find_one({"user_id": user_id},
                                                                  {"is_premium": 1, "subscription_status": 1,
                                                                    "premium_until": 1, "_id": 0})
    if not u:
        return False
    if u.get("is_premium"):
        return True
    status = (u.get("subscription_status") or "").lower()
    if status in ("active", "premium", "trial", "trialing"):
        return True
    pu = u.get("premium_until")
    if isinstance(pu, datetime) and pu > _now():
        return True
    return False


async def _freq_capped(db, user_id: str, campaign_id: str,
                                              freq_cap: int) -> bool:
    if not user_id or not campaign_id:
        return False
    since = _now() - timedelta(days=1)
    n = await db.banner_ad_impressions.count_documents({
        "user_id": user_id, "campaign_id": campaign_id,
        "created_at": {"$gte": since},
    })
    return n >= max(1, int(freq_cap or DEFAULT_FREQ_CAP))


def _matches_targeting(camp: dict, geo: Optional[dict],
                                                channel: Optional[str]) -> bool:
    """Light targeting — city + channel.  Time-of-day and weather can be
    added without changing the API surface."""
    t = camp.get("targeting") or {}
    # City: case-insensitive, "all" / empty / missing = always match.
    cities = [c.lower() for c in (t.get("cities") or []) if c]
    user_city = ((geo or {}).get("city") or "").lower()
    if cities and "all" not in cities:
        if user_city and user_city not in cities:
            return False
    # Channel: empty = match any.
    chs = [c.lower() for c in (t.get("channels") or []) if c]
    if chs and channel:
        if channel.lower() not in chs:
            return False
    return True


# ─── Direct-sold pool ─────────────────────────────────────────────
async def _select_direct(db, user_id: Optional[str], placement: str,
                                                  geo: Optional[dict],
                                                  channel: Optional[str]) -> Optional[dict]:
    cur = db.advertiser_campaigns.find({
        "campaign_type": "banner_persistent",
        "status": "live",
        "placements": placement,
    })
    candidates: List[dict] = []
    async for c in cur:
        if not _matches_targeting(c, geo, channel):
            continue
        if user_id and await _freq_capped(
                                  db, user_id, str(c.get("_id") or c.get("campaign_id")),
                                  c.get("frequency_cap_per_user_per_day") or DEFAULT_FREQ_CAP):
            continue
        candidates.append(c)
    if not candidates:
        return None
    # Highest bid_cpm_cents wins.  Tie → random.
    candidates.sort(key=lambda c: -int(c.get("bid_cpm_cents") or 0))
    top_bid = int(candidates[0].get("bid_cpm_cents") or 0)
    top = [c for c in candidates if int(c.get("bid_cpm_cents") or 0) == top_bid]
    return random.choice(top) if top else candidates[0]


# ─── Mocked SSP banner backfill ───────────────────────────────────
def _ssp_mock_fill() -> Optional[dict]:
    """TODO Phase 42 v2 — replace with real OpenRTB banner provider chain
    (AdsWizz banner, Triton display, GAM, etc.).  Reads SSP_BANNER_FILL
    env knob to simulate no-fill scenarios for the tester."""
    if os.environ.get("SSP_BANNER_MOCK_ENABLED", "true").lower() != "true":
        return None
    try:
        fill = float(os.environ.get("SSP_BANNER_FILL_RATE", "0.6"))
    except ValueError:
        fill = 0.6
    if random.random() > fill:
        return None
    # Random house creative.
    creatives = [
        {"image_url": "/api/static/ad_creatives/house_premium_320x60.png",
          "click_url": "/billing", "cta_text": "Go Premium · skip ads"},
        {"image_url": "/api/static/ad_creatives/house_predict_win_320x60.png",
          "click_url": "/predict-win", "cta_text": "Predict to win BigPoints"},
        {"image_url": "/api/static/ad_creatives/house_referral_320x60.png",
          "click_url": "/wallet", "cta_text": "Earn 100 BigPoints per friend"},
    ]
    pick = random.choice(creatives)
    return {
        "id": f"house_{uuid.uuid4().hex[:10]}",
        "image_url": pick["image_url"],
        "click_url": pick["click_url"],
        "cta_text": pick["cta_text"],
        "advertiser_id": None,
        "campaign_id": None,
        "source": "ssp_mocked_banner",
    }


# ─── Public selector ─────────────────────────────────────────────
async def request_banner(*, db, user_id: Optional[str], placement: str,
                                                  geo: Optional[dict] = None,
                                                  channel: Optional[str] = None,
                                                  weather_ctx: Optional[dict] = None) -> Optional[dict]:
    """Returns a normalised banner ad payload or None.

    Returned shape:
        {
            "id": str,
            "image_url": str,
            "click_url": str,
            "cta_text": str | None,
            "advertiser_id": str | None,
            "campaign_id": str | None,
            "impression_token": str,
            "source": "direct" | "ssp_mocked_banner",
        }
    """
    if placement not in VALID_PLACEMENTS:
        return None
    if await _is_premium(db, user_id):
        return None

    # 1) Direct-sold.
    direct = await _select_direct(db, user_id, placement, geo, channel)
    if direct:
        token = f"impt_{uuid.uuid4().hex}"
        cid = str(direct.get("_id") or direct.get("campaign_id"))
        return {
            "id": cid,
            "image_url": direct.get("creative_image_url") or direct.get("image_url"),
            "click_url": direct.get("click_url"),
            "cta_text":  direct.get("cta_text"),
            "advertiser_id": direct.get("advertiser_id"),
            "campaign_id":      cid,
            "impression_token": token,
            "source": "direct",
        }

    # 2) SSP / house backfill.
    backfill = _ssp_mock_fill()
    if backfill:
        backfill["impression_token"] = f"impt_{uuid.uuid4().hex}"
        return backfill

    return None


async def log_impression(*, db, user_id: Optional[str],
                                                  ad: dict, placement: str) -> None:
    """Record the impression once the client confirms render."""
    if not ad or not ad.get("impression_token"):
        return
    doc = {
        "_id": ad["impression_token"],
        "impression_token": ad["impression_token"],
        "user_id":          user_id,
        "campaign_id":  ad.get("campaign_id"),
        "advertiser_id": ad.get("advertiser_id"),
        "placement":        placement,
        "source":              ad.get("source"),
        "click_url":          ad.get("click_url"),
        "created_at":      _now(),
        "clicked":              False,
    }
    try:
        await db.banner_ad_impressions.insert_one(doc)
    except Exception as e:
        # Duplicate token (client retry) — fine to ignore.
        if "duplicate" not in str(e).lower():
            log.warning("[banner_ads] impression insert: %s", e)


async def log_click(*, db, impression_token: str) -> bool:
    res = await db.banner_ad_impressions.update_one(
        {"impression_token": impression_token},
        {"$set": {"clicked": True, "clicked_at": _now()}},
    )
    return res.modified_count > 0
