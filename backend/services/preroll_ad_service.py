"""Phase 42-B — Pre-roll ad selection + impression tracking service.

Single source of truth for the "should this user see a pre-roll on this
imported live-radio station, and if so which one?" question.

Design notes:
  • Independent of the legacy ad-decisioning pipeline (campaigns /
        ad_pods / ad_serve_events).  Coupling pre-roll into that engine would
        require touching the radio queue builder; the two systems share the
        `user_wallet_items` write path (for coupon save) and nothing else.
  • Frequency caps live on `live_radio_ad_impressions` only — we never
        read from `ad_impressions` so legacy-channel impression history
        doesn't influence pre-roll selection (and vice versa).
  • Premium gate is delegated to `services.premium_gate.is_premium_or_trial`
        — the SAME predicate every other paid feature uses.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.premium_gate import is_premium_or_trial

log = logging.getLogger("bigfm.preroll_ad")


# Tunables (env-overridable so the tester can tighten/loosen for QA).
# Phase K.9 — defaults raised to support the chain_count=3 default
# (was hourly=1/daily=3 which starved the chain after one play).
DEFAULT_GRACE_SECONDS = int(os.environ.get("PREROLL_GRACE_SECONDS", "60"))
DEFAULT_HOURLY_CAP    = int(os.environ.get("PREROLL_HOURLY_CAP", "12"))
DEFAULT_DAILY_CAP      = int(os.environ.get("PREROLL_DAILY_CAP", "40"))


# ─── Phase PREROLL.EXT — multi-collection station resolver ─────────
# Ordered list — first hit wins.  Each entry:
#   (collection_name, id_field, active_predicate)
_STATION_LOOKUP_CHAIN = (
    ("imported_radio_stations",  "id",                {"active": True}),
    ("imported_radio_stations",  "_id",              {"active": True}),
    ("community_radio_stations", "station_id", {"status": {"$in":
                                                                                                                    ["published", "active", None]}}),
    ("community_radio_stations", "_id",              {"status": {"$in":
                                                                                                                    ["published", "active", None]}}),
    ("channels",                              "_id",              {"active": {"$in": [True, None]}}),
)


async def resolve_station(db, station_id: str) -> Optional[Dict[str, Any]]:
    """Look up a station across all supported station collections.

    Handles the mixed id shapes:
      * imported_radio_stations   — string `id` (imp_*) + string `_id` mirror
      * community_radio_stations  — string `station_id` (stn_*) + ObjectId `_id`
      * channels                  — string `_id` slug (e.g. "bollywood_mehfil")

    Returns the raw doc + injects synthetic fields:
      station_type  : imported|flagship|community|ai_channel
      preroll_enabled: bool (defaults True when missing)
      station_id      : normalized string id
    """
    if not station_id:
        return None
    from bson import ObjectId
    from bson.errors import InvalidId
    for coll_name, id_field, active_pred in _STATION_LOOKUP_CHAIN:
        q: Dict[str, Any] = {id_field: station_id}
        for k, v in (active_pred or {}).items():
            q[k] = v
        try:
            doc = await db[coll_name].find_one(q)
        except Exception:
            doc = None
        # Try ObjectId lookup when a 24-char hex is passed against `_id`.
        if not doc and id_field == "_id" and isinstance(station_id, str) \
                    and len(station_id) == 24:
            try:
                q2 = {"_id": ObjectId(station_id)}
                for k, v in (active_pred or {}).items():
                    q2[k] = v
                doc = await db[coll_name].find_one(q2)
            except InvalidId:
                pass
            except Exception:
                pass
        if not doc:
            continue
        # Derive station_type
        if coll_name == "imported_radio_stations":
            stype = "flagship" if doc.get("is_flagship") else "imported"
        elif coll_name == "community_radio_stations":
            stype = "community"
        elif coll_name == "channels":
            stype = "ai_channel"
        else:
            stype = coll_name
        doc = dict(doc)
        doc["station_type"] = stype
        doc["station_id"] = station_id
        # `id` is used by legacy code (select_ad_for_play etc.) — normalize
        # it so callers don't have to case-split by collection.
        doc["id"] = station_id
        doc["_source_collection"] = coll_name
        doc["_source_id_field"] = id_field
        # Default preroll_enabled True when not set.
        if doc.get("preroll_enabled") is None:
            doc["preroll_enabled"] = True
        return doc
    return None


def _resolved_chain_count() -> int:
    """Phase 42-F.4 / Phase H'.4 — how many sequential pre-roll ads to
    serve on a single station start.  1 keeps legacy single-ad behaviour;
    values > 1 trigger the chain UI in PrerollOverlay.jsx.  Hard-capped
    at 5 to prevent ad-stuffing accidents.

    The async sibling `_resolved_chain_count_async(db)` consults the
    `system_config` override row (Phase H'.4 admin endpoint) before
    falling through to the env var.  This sync version is used in
    legacy code paths that don't have a db handle handy.
    """
    try:
        n = int(os.environ.get("PREROLL_CHAIN_COUNT", "1"))
    except (TypeError, ValueError):
        n = 1
    return max(1, min(n, 5))


async def _resolved_chain_count_async(db) -> int:
    try:
        from routes.admin_preroll import get_effective_chain_count
        return await get_effective_chain_count(db)
    except Exception:
        return _resolved_chain_count()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _strip_mongo(d: dict) -> dict:
    out = {**d}
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ───────────────────────── selection ──────────────────────────
async def _user_is_premium_and_ad_free(db, user: Optional[dict]) -> bool:
    """Returns True only when the user is BOTH premium AND has opted to
    suppress ads.  Free users always see ads (subject to caps); premium
    users with `ad_free_enabled=False` (explicit opt-in to see ads) also
    see ads."""
    if not user:
        return False
    if not is_premium_or_trial(user):
        return False
    # Default to True for premium users (suppress ads by default).
    setting = user.get("ad_settings") or {}
    return bool(setting.get("ad_free_enabled", True))


async def _under_caps(db, user_id: Optional[str], session_id: str,
                                          grace_seconds: int,
                                          hourly_cap: int, daily_cap: int,
                                          *, station_id: Optional[str] = None
                                          ) -> Dict[str, Any]:
    """Returns {"ok": True} or {"ok": False, "reason": "grace_period|frequency_cap"}.
    Anonymous users (no user_id) use the session_id as the dedup key.

    Phase K.9 — grace_period is STATION-AWARE: when the caller passes
    `station_id` we only count impressions on the SAME station against
    the grace window.  This fixes the regression where flipping to a
    new station within 60s was silently swallowed with "grace_period"
    and the user (correctly) thought "ads aren't playing".  Hourly
    and daily caps still apply across all stations as before.
    """
    now = _now()
    key_field = "user_id" if user_id else "session_id"
    key_value = user_id or session_id
    if not key_value:
        return {"ok": True}        # truly anonymous → no cap enforcement
    grace_cutoff = now - timedelta(seconds=grace_seconds)
    grace_q: Dict[str, Any] = {key_field: key_value,
                                                "started_at": {"$gte": grace_cutoff}}
    if station_id:
        grace_q["station_id"] = station_id
    grace = await db.live_radio_ad_impressions.find_one(grace_q)
    if grace:
        return {"ok": False, "reason": "grace_period",
                      "next_eligible_at": (grace["started_at"] +
                                                          timedelta(seconds=grace_seconds)).isoformat()}
    hourly_cutoff = now - timedelta(hours=1)
    hour_n = await db.live_radio_ad_impressions.count_documents(
        {key_field: key_value, "started_at": {"$gte": hourly_cutoff}})
    if hour_n >= hourly_cap:
        return {"ok": False, "reason": "frequency_cap",
                      "scope": "hourly", "limit": hourly_cap, "count": hour_n}
    daily_cutoff = now - timedelta(hours=24)
    day_n = await db.live_radio_ad_impressions.count_documents(
        {key_field: key_value, "started_at": {"$gte": daily_cutoff}})
    if day_n >= daily_cap:
        return {"ok": False, "reason": "frequency_cap",
                      "scope": "daily", "limit": daily_cap, "count": day_n}
    return {"ok": True}


def _ad_matches_targeting(ad: Dict[str, Any],
                                                    country: Optional[str],
                                                    language: Optional[str],
                                                    station_categories: List[str],
                                                    hour: int, weekday: int) -> bool:
    """All-or-nothing AND match.  Empty targeting arrays = wildcard."""
    t = ad.get("targeting") or {}
    if t.get("countries"):
        if (country or "").upper() not in {c.upper() for c in t["countries"]}:
            return False
    if t.get("languages"):
        if (language or "").lower() not in {lang.lower() for lang in t["languages"]}:
            return False
    if t.get("station_categories"):
        if not set(station_categories).intersection({c.lower() for c in t["station_categories"]}):
            return False
    if t.get("dayparts"):
        for dp in t["dayparts"]:
            if (dp.get("day") in (None, weekday)
                    and dp.get("start_hour", 0) <= hour < dp.get("end_hour", 24)):
                break
        else:
            return False
    return True


async def select_ad_for_play(db,
                                                          user: Optional[dict],
                                                          station: Dict[str, Any],
                                                          session_id: str,
                                                          country_code: Optional[str] = None,
                                                          language: Optional[str] = None,
                                                          ) -> Dict[str, Any]:
    """Returns a `{has_preroll: bool, …}` response payload directly
    consumable by the `/preroll/request` endpoint.

    `station` is the full row from `imported_radio_stations` (used to
    derive country/language/category targeting).  AI-curated BigFM
    channels MUST NOT call this — they have their own ad-insertion
    pipeline in the queue builder.
    """
    user_id = user.get("user_id") if user else None
    # 1. Premium short-circuit.
    if await _user_is_premium_and_ad_free(db, user):
        return {"has_preroll": False, "reason": "premium"}

    # 2. Frequency / grace caps.  Grace is station-aware (Phase K.9) so
    #     switching to a new station within 60s triggers a fresh ad.
    cap = await _under_caps(db, user_id, session_id,
                                                          DEFAULT_GRACE_SECONDS,
                                                          DEFAULT_HOURLY_CAP, DEFAULT_DAILY_CAP,
                                                          station_id=station.get("id"))
    if not cap["ok"]:
        return {"has_preroll": False, **cap}

    # 3. Targeting filter.
    country = country_code or station.get("country_code")
    lang = language or station.get("language")
    # Pull station categories from radio_station_categories.
    cats_cur = db.radio_station_categories.find(
        {"station_id": station["id"], "source_provider": "radiobrowser"})
    station_categories = [r["category"] async for r in cats_cur]
    now = _now()
    hour = now.hour
    weekday = now.weekday()

    active_q = {
        "status": "active",
        "start_time": {"$lte": now.isoformat()},
        "$or": [{"end_time": None},
                      {"end_time": {"$exists": False}},
                      {"end_time": {"$gte": now.isoformat()}}],
    }
    eligible: List[Dict[str, Any]] = []
    async for ad in db.preroll_ads.find(active_q):
        if _ad_matches_targeting(ad, country, lang, station_categories,
                                                          hour, weekday):
            eligible.append(ad)

    # Sub-Phase 42-B2 — SSP/VAST waterfall fallback when local has zero fill.
    if not eligible:
        try:
            from services.ssp_ad_provider import request_ssp_ad
            ssp_ad = await request_ssp_ad(
                station_id=station["id"],
                station_meta={"country_code": country, "language": lang,
                                              "categories": station_categories,
                                              "name": station.get("name")},
                user_ctx={"user_id": user_id, "session_id": session_id},
                country_code=country, language=lang)
        except Exception as _e:
            log.warning("[preroll] SSP chain raised: %s", _e)
            ssp_ad = None
        if ssp_ad:
            ssp_impression_id = _new_id("imp")
            await db.live_radio_ad_impressions.insert_one({
                "_id": ssp_impression_id, "id": ssp_impression_id,
                "user_id": user_id, "session_id": session_id,
                "station_id": station["id"],
                "ad_id": ssp_ad.get("ad_id"),
                "placement": "preroll",
                "source": ssp_ad.get("source") or "ssp_unknown",
                "source_provider": ssp_ad.get("source_provider"),
                "started_at": now,
                "completed_at": None, "skipped": False,
                "companion_clicked_at": None, "wallet_saved_at": None,
                "country_code": country, "language": lang,
            })
            # Don't bump preroll_ads.impressions_served — that collection
            # tracks BigFM-managed creatives only.  SSP fill is counted
            # at the impression-row level via `source`.
            return {
                "has_preroll": True,
                "impression_id": ssp_impression_id,
                "ad": {
                    "ad_id": ssp_ad.get("ad_id"),
                    "name": ssp_ad.get("name"),
                    "type": ssp_ad.get("type", "audio"),
                    "audio_url": ssp_ad.get("audio_url"),
                    "duration_sec": ssp_ad.get("duration_sec") or 15,
                    "companion_image_url": ssp_ad.get("companion_image_url"),
                    "companion_cta_text": ssp_ad.get("companion_cta_text"),
                    "companion_cta_url": ssp_ad.get("companion_cta_url"),
                    "attached_offer_id": ssp_ad.get("attached_offer_id"),
                    "advertiser_name": ssp_ad.get("advertiser_name"),
                    "source": ssp_ad.get("source") or "ssp_unknown",
                },
            }
        return {"has_preroll": False, "reason": "no_eligible_ad",
                      "diagnostics": {"country": country, "language": lang,
                                                  "station_categories": station_categories,
                                                  "weekday": weekday, "hour": hour}}

    # 4. Deterministic pick (same user + station + hour-bucket → same ad
    #        so quick replays don't suddenly swap the creative).
    seed_src = f"{user_id or session_id}|{station['id']}|{now.strftime('%Y-%m-%d-%H')}"
    seed = int(hashlib.sha1(seed_src.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    ad = rng.choice(eligible)

    # 5. Record impression row (status=started).
    impression_id = _new_id("imp")
    await db.live_radio_ad_impressions.insert_one({
        "_id": impression_id, "id": impression_id,
        "user_id": user_id, "session_id": session_id,
        "station_id": station["id"], "ad_id": ad["id"],
        "placement": "preroll", "started_at": now,
        # Sub-Phase 42-B2 — source attribution lets admins break down
        # local fill vs SSP fill in analytics.
        "source": "local",
        "completed_at": None, "skipped": False,
        "companion_clicked_at": None, "wallet_saved_at": None,
        "country_code": country, "language": lang,
    })
    # Increment served counter on the ad doc (used by admin analytics).
    await db.preroll_ads.update_one(
        {"id": ad["id"]}, {"$inc": {"impressions_served": 1}})

    return {
        "has_preroll": True,
        "impression_id": impression_id,
        "ad": {
            "ad_id": ad["id"],
            "name": ad.get("name"),
            "type": ad.get("type", "audio"),
            "audio_url": ad.get("audio_url"),
            "duration_sec": ad.get("audio_duration_seconds")
                                          or ad.get("duration_sec") or 15,
            # Sub-Phase 42-B2 — companion creative is ONLY surfaced when
            # the ad has an attached offer (the consumer-facing rule is
            # "popup only if there's a coupon to save").  Ads with no
            # offer become audio-only.
            "companion_image_url": (ad.get("companion_image_url")
                                                              if ad.get("attached_offer_id") else None),
            "companion_cta_text": (ad.get("companion_cta_text")
                                                            if ad.get("attached_offer_id") else None),
            "companion_cta_url": (ad.get("companion_cta_url")
                                                          if ad.get("attached_offer_id") else None),
            "attached_offer_id": ad.get("attached_offer_id"),
            "advertiser_name": ad.get("advertiser_name"),
            "source": "local",
        },
    }


async def select_ad_chain_for_play(db,
                                                                      user: Optional[dict],
                                                                      station: Dict[str, Any],
                                                                      session_id: str,
                                                                      country_code: Optional[str] = None,
                                                                      language: Optional[str] = None,
                                                                      ) -> Dict[str, Any]:
    """Phase 42-F.4 — chain wrapper around `select_ad_for_play`.

    When `PREROLL_CHAIN_COUNT > 1`, requests up to N sequential
    pre-roll ads.  Each subsequent ad reuses the same eligibility +
    targeting check that the first one passed but bypasses the
    grace/frequency cap (the cap is enforced ONCE per chain at the
    start, not per-ad).

    Response shape (always — even when chain_count=1):
      {has_preroll: bool, chain_count: int, ads: [...],
       impression_ids: [...],
       # backward-compat for old PrerollOverlay versions:
       ad: <first ad dict|None>, impression_id: <first impression|None>,
       reason: <optional reason>}
    """
    chain_count = await _resolved_chain_count_async(db)
    # First-pass = same as the legacy function.  Drains cap + grace.
    first = await select_ad_for_play(
        db, user, station, session_id,
        country_code=country_code, language=language)
    if not first.get("has_preroll"):
        first["chain_count"] = chain_count
        first["ads"] = []
        first["impression_ids"] = []
        return first
    ads_list = [first["ad"]]
    imps_list = [first["impression_id"]]
    if chain_count <= 1:
        return {**first, "chain_count": 1,
                          "ads": ads_list, "impression_ids": imps_list}

    # Subsequent picks — same eligibility set, but DON'T re-run
    # grace_period / hourly_cap checks (they would trip after our own
    # first impression).  Re-derive the eligible pool inline.
    user_id = user.get("user_id") if user else None
    country = country_code or station.get("country_code")
    lang = language or station.get("language")
    cats_cur = db.radio_station_categories.find(
        {"station_id": station["id"], "source_provider": "radiobrowser"})
    station_categories = [r["category"] async for r in cats_cur]
    now = _now()
    hour = now.hour
    weekday = now.weekday()
    active_q = {
        "status": "active",
        "start_time": {"$lte": now.isoformat()},
        "$or": [{"end_time": None},
                      {"end_time": {"$exists": False}},
                      {"end_time": {"$gte": now.isoformat()}}],
    }
    eligible: List[Dict[str, Any]] = []
    seen = {first["ad"].get("ad_id")}
    async for ad in db.preroll_ads.find(active_q):
        if ad.get("id") in seen:
            continue
        if _ad_matches_targeting(ad, country, lang, station_categories,
                                                          hour, weekday):
            eligible.append(ad)
    # Deterministic shuffle keyed on session so we don't get the same
    # chain twice for the same listener within an hour.
    seed_src = f"{user_id or session_id}|{station['id']}|chain|{now.strftime('%Y-%m-%d-%H')}"
    seed = int(hashlib.sha1(seed_src.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    rng.shuffle(eligible)

    # Phase K.9 — if the local pool has FEWER distinct ads than the
    # chain count, recycle the available ads with replacement so the
    # chain still fills.  Better to repeat a creative than to short
    # the chain and have the user think "ads not playing".
    need = chain_count - 1
    if need > 0 and len(eligible) > 0 and len(eligible) < need:
        recycled = []
        i = 0
        while len(recycled) < need:
            recycled.append(eligible[i % len(eligible)])
            i += 1
        eligible = recycled
    elif need > 0 and len(eligible) == 0:
        # No additional local inventory — try SSP fallback for the
        # remaining chain slots so the user still hears 3 ads.
        try:
            from services.ssp_ad_provider import request_ssp_ad
            for _ in range(need):
                ssp_ad = await request_ssp_ad(
                    station_id=station["id"],
                    station_meta={"country_code": country, "language": lang,
                                                  "categories": station_categories,
                                                  "name": station.get("name")},
                    user_ctx={"user_id": user_id, "session_id": session_id},
                    country_code=country, language=lang)
                if not ssp_ad:
                    break
                ssp_imp_id = _new_id("imp")
                await db.live_radio_ad_impressions.insert_one({
                    "_id": ssp_imp_id, "id": ssp_imp_id,
                    "user_id": user_id, "session_id": session_id,
                    "station_id": station["id"], "ad_id": ssp_ad.get("ad_id"),
                    "placement": "preroll",
                    "source": ssp_ad.get("source") or "ssp_unknown",
                    "chain_position": len(ads_list) + 1,
                    "chain_count": chain_count,
                    "started_at": now,
                    "completed_at": None, "skipped": False,
                    "country_code": country, "language": lang,
                })
                ads_list.append({
                    "ad_id":              ssp_ad.get("ad_id"),
                    "name":                  ssp_ad.get("name"),
                    "type":                  ssp_ad.get("type", "audio"),
                    "audio_url":      ssp_ad.get("audio_url"),
                    "duration_sec":  ssp_ad.get("duration_sec") or 15,
                    "companion_image_url": ssp_ad.get("companion_image_url"),
                    "companion_cta_text": ssp_ad.get("companion_cta_text"),
                    "companion_cta_url":  ssp_ad.get("companion_cta_url"),
                    "advertiser_name":      ssp_ad.get("advertiser_name"),
                    "source": ssp_ad.get("source") or "ssp_unknown",
                })
                imps_list.append(ssp_imp_id)
        except Exception as _e:
            log.warning("[preroll] SSP chain fill raised: %s", _e)
        eligible = []   # SSP handled; skip the local loop below.

    for ad in eligible[: chain_count - 1]:
        impression_id = _new_id("imp")
        await db.live_radio_ad_impressions.insert_one({
            "_id": impression_id, "id": impression_id,
            "user_id": user_id, "session_id": session_id,
            "station_id": station["id"], "ad_id": ad["id"],
            "placement": "preroll",
            "source": "local",
            "chain_position": len(ads_list) + 1,
            "chain_count": chain_count,
            "started_at": now,
            "completed_at": None, "skipped": False,
            "companion_clicked_at": None, "wallet_saved_at": None,
            "country_code": country, "language": lang,
        })
        await db.preroll_ads.update_one(
            {"id": ad["id"]}, {"$inc": {"impressions_served": 1}})
        ads_list.append({
            "ad_id": ad["id"], "name": ad.get("name"),
            "type": ad.get("type", "audio"),
            "audio_url": ad.get("audio_url"),
            "duration_sec": ad.get("audio_duration_seconds")
                                      or ad.get("duration_sec") or 15,
            "companion_image_url": (ad.get("companion_image_url")
                                                              if ad.get("attached_offer_id") else None),
            "companion_cta_text": (ad.get("companion_cta_text")
                                                            if ad.get("attached_offer_id") else None),
            "companion_cta_url": (ad.get("companion_cta_url")
                                                          if ad.get("attached_offer_id") else None),
            "attached_offer_id": ad.get("attached_offer_id"),
            "advertiser_name": ad.get("advertiser_name"),
            "source": "local",
        })
        imps_list.append(impression_id)
    # The first impression row pre-existed (legacy shape).  Stamp it
    # with chain metadata so analytics can correlate later.
    try:
        await db.live_radio_ad_impressions.update_one(
            {"id": first["impression_id"]},
            {"$set": {"chain_position": 1, "chain_count": chain_count}})
    except Exception:
        pass
    return {"has_preroll": True,
                  "chain_count": chain_count,
                  "ads": ads_list,
                  "impression_ids": imps_list,
                  # Back-compat: keep `ad` + `impression_id` for old clients.
                  "ad": ads_list[0],
                  "impression_id": imps_list[0]}


# ───────────────────────── events ─────────────────────────────
VALID_EVENTS = {"start", "complete", "skip", "companion_click", "wallet_save"}


async def record_impression_event(db, impression_id: str, event_type: str,
                                                                    metadata: Optional[dict] = None) -> Dict[str, Any]:
    if event_type not in VALID_EVENTS:
        return {"ok": False, "code": "invalid_event_type",
                      "allowed": sorted(VALID_EVENTS)}
    row = await db.live_radio_ad_impressions.find_one({"id": impression_id})
    if not row:
        return {"ok": False, "code": "impression_not_found"}
    now = _now()
    set_fields: Dict[str, Any] = {"last_event_at": now,
                                                                  "last_event_type": event_type}
    inc_fields: Dict[str, Any] = {}
    if event_type == "complete":
        set_fields["completed_at"] = now
        inc_fields["completes"] = 1
    elif event_type == "skip":
        set_fields["skipped"] = True
        set_fields["skipped_at"] = now
        inc_fields["skips"] = 1
    elif event_type == "companion_click":
        set_fields["companion_clicked_at"] = now
        inc_fields["companion_clicks"] = 1
    elif event_type == "wallet_save":
        set_fields["wallet_saved_at"] = now
        inc_fields["wallet_saves"] = 1
    if metadata:
        set_fields["last_event_metadata"] = metadata
    await db.live_radio_ad_impressions.update_one(
        {"id": impression_id}, {"$set": set_fields})
    if inc_fields:
        await db.preroll_ads.update_one(
            {"id": row["ad_id"]}, {"$inc": inc_fields})
    return {"ok": True, "impression_id": impression_id,
                  "event_type": event_type, "recorded_at": now.isoformat()}


# ───────────────────────── indexes ────────────────────────────
async def ensure_indexes(db) -> None:
    """Idempotent index creation called from server startup."""
    await db.preroll_ads.create_index([("id", 1)], unique=True)
    await db.preroll_ads.create_index([("status", 1)])
    await db.live_radio_ad_impressions.create_index([("id", 1)], unique=True)
    await db.live_radio_ad_impressions.create_index(
        [("user_id", 1), ("started_at", -1)])
    await db.live_radio_ad_impressions.create_index(
        [("session_id", 1), ("started_at", -1)])
    await db.live_radio_ad_impressions.create_index(
        [("ad_id", 1), ("started_at", -1)])
    await db.live_radio_ad_impressions.create_index(
        [("station_id", 1), ("started_at", -1)])
    # 90-day TTL on impressions (per spec).
    try:
        await db.live_radio_ad_impressions.create_index(
            "started_at", expireAfterSeconds=90 * 86400,
            name="ttl_started_at_90d")
    except Exception:
        pass    # incompatible existing index — skip
