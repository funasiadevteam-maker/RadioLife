"""Phase 9b — Route-based ad/game targeting engine.

When a listener starts a commute we precompute the top-N most relevant
ads + games for that commute by combining:

  - geo proximity to the route polyline (from 9a's MapsClient)
  - weather snapshot at commute start
  - daypart at commute start
  - traffic status
  - destination-arrival proximity (last ~10 min of ETA)

Each opportunity carries a normalised score, a list of human-readable
reason_codes (transparency), and a TTL.  When the radio engine picks
the next ad break, `pick_route_targeted_ad()` is consulted BEFORE the
ordinary Phase 4/4.5/8c waterfall.  If nothing eligible, fall through.

A 15-minute cooldown per listener prevents route-targeted ads from
crowding out other inventory or self-spamming.

All collections + indexes:
  - route_ad_opportunities (one doc per opp; TTL 6h)
  - route_ad_decision_log  (audit; one doc per break)
"""
from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.maps_client import get_maps_client

logger = logging.getLogger("bigfm.route_ads")

# ─── Constants ─────────────────────────────────────────────────────────
DAYPARTS = (
    "morning_drive", "midday", "lunch", "afternoon",
    "evening_drive", "dinner", "night", "late_night",
)
WEATHER_CONDITIONS = (
    "rain", "thunderstorm", "hot", "cold",
    "clear", "cloudy", "haze", "snow",
)
TRAFFIC_STATES = ("light", "moderate", "heavy", "unknown")
KINDS = ("geo_proximity", "weather_triggered", "daypart_triggered",
            "traffic_triggered", "destination_arrival")
COMMUTE_MODES = ("driver", "passenger", "transit")

# Cooldown between route-targeted ads (per listener)
ROUTE_AD_COOLDOWN_MINUTES = 15
# Cap on opportunities persisted per commute
MAX_OPPS_PER_COMMUTE = 25
# How close (km) a campaign's destination must be to fire destination_arrival
DEST_PROX_M = 300
# How many minutes BEFORE arrival to schedule a destination_arrival opp
DEST_ARRIVAL_WINDOW_MIN = 10
# Default radius for geo_proximity if campaign didn't specify
DEFAULT_PROX_RADIUS_M = 3000
DEFAULT_MAX_DETOUR_MIN = 10


def _now():
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════
# Daypart helpers
# ═══════════════════════════════════════════════════════════════════════
def hour_to_daypart(hour: int) -> str:
    """Map a 0-23 hour to a daypart slug."""
    if 6 <= hour < 10:
        return "morning_drive"
    if 10 <= hour < 12:
        return "midday"
    if 12 <= hour < 14:
        return "lunch"
    if 14 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 20:
        return "evening_drive"
    if 20 <= hour < 22:
        return "dinner"
    if 22 <= hour < 24:
        return "night"
    return "late_night"     # 0–5 inclusive


def daypart_for_market(now_utc: datetime, market: str = "dubai") -> str:
    """Resolve daypart in the listener's local TZ.  Dubai = UTC+4, DFW = UTC-6 (DST ignored)."""
    offset = 4 if market == "dubai" else (-6 if market == "dfw" else 0)
    local_hour = (now_utc.hour + offset) % 24
    return hour_to_daypart(local_hour)


# ═══════════════════════════════════════════════════════════════════════
# Targeting validation (used by advertiser submit-for-approval)
# ═══════════════════════════════════════════════════════════════════════
def validate_targeting_smart(t: dict) -> Optional[str]:
    """Return None if the targeting passes, else a short error string.

    Tolerates missing/empty fields (means 'any').
    """
    if not isinstance(t, dict):
        return "targeting_must_be_object"
    for fld in ("weather_triggers", "traffic_triggers", "dayparts",
                  "commute_modes", "route_corridor"):
        v = t.get(fld)
        if v is None:
            continue
        if not isinstance(v, list):
            return f"{fld}_must_be_list"
    for w in (t.get("weather_triggers") or []):
        if w not in WEATHER_CONDITIONS:
            return f"weather_trigger_invalid:{w}"
    for x in (t.get("traffic_triggers") or []):
        if x not in TRAFFIC_STATES:
            return f"traffic_trigger_invalid:{x}"
    for d in (t.get("dayparts") or []):
        if d not in DAYPARTS:
            return f"daypart_invalid:{d}"
    for m in (t.get("commute_modes") or []):
        if m not in COMMUTE_MODES:
            return f"commute_mode_invalid:{m}"
    tb = t.get("temperature_band")
    if tb is not None:
        if not isinstance(tb, dict) or "min_c" not in tb or "max_c" not in tb:
            return "temperature_band_shape"
        try:
            if float(tb["min_c"]) > float(tb["max_c"]):
                return "temperature_band_min_gt_max"
        except (TypeError, ValueError):
            return "temperature_band_numeric"
    prox = t.get("proximity")
    if prox is not None:
        if not isinstance(prox, dict) or "business_id" not in prox:
            return "proximity_business_id_required"
    return None


# ═══════════════════════════════════════════════════════════════════════
# Scoring helpers
# ═══════════════════════════════════════════════════════════════════════
def _distance_score(distance_m: float, radius_m: int) -> float:
    """1.0 at 0m, 0.0 at radius, linear inverse."""
    if radius_m <= 0:
        return 0.0
    d = max(0.0, min(distance_m, radius_m))
    return 1.0 - (d / radius_m)


def _weather_match_score(weather: dict, triggers: list[str],
                              temp_band: Optional[dict]) -> tuple[float, list[str]]:
    """Returns (score, reasons).  Score is 0..1.  Reasons list explains."""
    reasons: list[str] = []
    score = 0.0
    cond = (weather or {}).get("condition")
    temp = (weather or {}).get("temp_c") or 0
    precip = (weather or {}).get("precipitation_mm") or 0
    if triggers:
        if cond in triggers:
            score = 1.0
            reasons.append(f"weather_match:{cond}")
            if "rain" in triggers and precip > 1:
                # Boost for actual rain
                score = min(1.0, score + 0.10)
                reasons.append(f"precipitation:{precip:.1f}mm")
        else:
            return 0.0, []
    if temp_band:
        try:
            mn = float(temp_band["min_c"])
            mx = float(temp_band["max_c"])
            if mn <= float(temp) <= mx:
                if not triggers:
                    score = 0.8
                reasons.append(f"temp_band:{mn}-{mx}°C")
            else:
                return 0.0, []
        except (TypeError, ValueError, KeyError):
            pass
    return score, reasons


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = (math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _decode_polyline_safe(polyline_encoded: str) -> list[tuple[float, float]]:
    """Decode Google-encoded polyline OR the local JSON fallback shape.
    Returns a list of (lat, lng) tuples."""
    if not polyline_encoded:
        return []
    try:
        if polyline_encoded.startswith("JSON:"):
            import json
            pts = json.loads(polyline_encoded[5:])
            return [(float(p[0]), float(p[1])) for p in pts]
        try:
            import polyline as _poly
            return [(float(la), float(ln))
                       for (la, ln) in _poly.decode(polyline_encoded)]
        except Exception:
            return []
    except Exception:
        return []


async def _augment_places_from_db(db, *, polyline: str,
                                            candidate_business_ids: list[str],
                                            radius_m: int,
                                            place_by_bid: dict) -> None:
    """Phase 9c.1 Fix 3 — DB-side polyline proximity fallback.

    Adds entries to `place_by_bid` for any candidate business in the
    local DB whose `loc` falls within `radius_m` of any sampled point
    along the encoded polyline.  This is what surfaces freshly-claimed
    partner businesses when the Maps API is in mock_fallback mode and
    its `places_along_route` only sees the seeded mock_places set.
    """
    if not polyline or not candidate_business_ids:
        return
    pts = _decode_polyline_safe(polyline)
    if not pts:
        return
    # Down-sample the polyline so we don't $geoNear N times for a
    # long route.  ~8 samples covers a typical Dubai/DFW commute.
    step = max(1, len(pts) // 8)
    sampled = pts[::step]
    # Find candidate businesses we haven't already covered via the
    # MapsClient.places_along_route response.
    pending = [bid for bid in candidate_business_ids
                  if bid and bid not in place_by_bid]
    if not pending:
        return
    cur = db.businesses.find(
        {"business_id": {"$in": pending},
          "loc": {"$exists": True},
          "lat": {"$exists": True},
          "lng": {"$exists": True}},
        {"business_id": 1, "lat": 1, "lng": 1, "name": 1})
    async for b in cur:
        b_lat, b_lng = b.get("lat"), b.get("lng")
        if b_lat is None or b_lng is None:
            continue
        best_d = None
        for (lat, lng) in sampled:
            d = _haversine_m(b_lat, b_lng, lat, lng)
            if best_d is None or d < best_d:
                best_d = d
        if best_d is not None and best_d <= radius_m:
            extra_s = int(best_d / (30 * 1000 / 3600))
            place_by_bid[b["business_id"]] = {
                "business_id": b["business_id"],
                "name": b.get("name") or "business",
                "lat": b_lat, "lng": b_lng,
                "distance_from_route_m": float(best_d),
                "extra_drive_time_seconds": extra_s,
                "source": "db_proximity",
            }


# ═══════════════════════════════════════════════════════════════════════
# Opportunity creation
# ═══════════════════════════════════════════════════════════════════════
async def _gather_candidate_campaigns(db) -> list[dict]:
    """Pull active ad + game campaigns with smart-targeting fields.

    Phase 9c — Also fetches active Offer rows and surfaces them as
    pseudo-campaigns with `_origin="offer"` so the existing scoring +
    persistence flow handles them uniformly.  The `targeting_json` is
    synthesized from the offer's host business so geo_proximity fires
    when the route passes near it.
    """
    out: list[dict] = []
    # Ad-engine campaigns
    cur = db.campaigns.find({"status": "active",
                                     "budget_cents": {"$gt": 0}})
    async for c in cur:
        c["_origin"] = "ad"
        out.append(c)
    # Game campaigns
    cur2 = db.game_campaigns.find({"status": "active",
                                            "approval_status": {"$ne": "rejected"}})
    async for g in cur2:
        g["_origin"] = "game"
        out.append(g)
    # Phase 9c — Active offers as pseudo-campaigns
    cur3 = db.offers.find({"status": "active",
                                  "end_at": {"$gte": _now()}})
    async for o in cur3:
        bid_id = o.get("business_id")
        # Synthesize a targeting payload that triggers geo_proximity
        # against the offer's host business.
        pseudo = {
            "_origin": "offer",
            "campaign_id": o["offer_id"],
            "offer_id": o["offer_id"],
            "name": o.get("title") or "Offer",
            "title": o.get("title"),
            "business_id": bid_id,
            "creative_ids": [],
            "budget_cents": 100000,
            "bid_cents_per_impression": 200,
            "targeting_json": {
                "proximity": {"business_id": bid_id,
                                  "radius_m": 3000,
                                  "max_detour_minutes": 10}},
            "sponsor_name": o.get("sponsor_name"),
        }
        out.append(pseudo)
    return out


def _kinds_for_targeting(t: dict) -> set[str]:
    """Which kinds is this campaign opting into?  At least one needed."""
    k: set[str] = set()
    if t.get("proximity") or t.get("route_corridor"):
        k.add("geo_proximity")
        k.add("destination_arrival")
    if t.get("weather_triggers") or t.get("temperature_band"):
        k.add("weather_triggered")
    if t.get("dayparts"):
        k.add("daypart_triggered")
    if t.get("traffic_triggers"):
        k.add("traffic_triggered")
    return k


async def compute_route_opportunities(db, commute_id: str,
                                                 *, market: str = "dubai") -> dict:
    """Background task — populate route_ad_opportunities for a commute.

    Idempotent: re-running for the same commute_id clears prior unspent
    opps first.
    """
    cmt = await db.commute_sessions.find_one({"commute_id": commute_id})
    if not cmt or cmt.get("status") != "active":
        return {"ok": False, "reason": "no_active_commute"}
    polyline = cmt.get("route_polyline") or ""
    weather = cmt.get("weather_snapshot") or {}
    traffic = cmt.get("traffic_status", "unknown")
    started_at = cmt.get("started_at") or _now()
    duration_s = int(cmt.get("route_duration_in_traffic_s") or 0)
    daypart = daypart_for_market(started_at, market=market)
    # Wipe prior unspent opps for this commute (idempotency)
    await db.route_ad_opportunities.delete_many(
        {"commute_id": commute_id, "selected": False})

    candidates = await _gather_candidate_campaigns(db)
    client = get_maps_client(db)
    # Rebind the singleton's db handle to whatever the caller passed.
    # This is a no-op in production (server uses the same motor handle
    # used at boot) but matters in tests / fork tasks that create a
    # fresh AsyncIOMotorClient per call.
    try:
        client.db = db
    except Exception:
        pass

    # Pre-compute places along route (geo_proximity + destination_arrival)
    places_along: list[dict] = []
    if polyline:
        try:
            places_along = await client.places_along_route(
                polyline, DEFAULT_PROX_RADIUS_M,
                ["restaurant", "cafe", "fast_food", "bar", "club",
                  "theater", "mall", "gas_station", "gym", "salon",
                  "dessert", "grocery"], DEFAULT_MAX_DETOUR_MIN)
        except Exception as e:
            logger.warning(f"places_along_route error: {e}")
    place_by_bid = {p.get("business_id"): p for p in places_along
                          if p.get("business_id")}

    # Phase 9c.1 Fix 3 — In mock_fallback Maps mode the synthesised
    # `places_along_route` only knows about the seeded mock_places set,
    # so freshly-claimed partner businesses never appear.  Augment the
    # set with a DB-side proximity scan against businesses.loc using
    # the decoded polyline points so partner offers can still trigger
    # geo_proximity opportunities.
    if polyline:
        try:
            await _augment_places_from_db(
                db, polyline=polyline,
                candidate_business_ids=list({
                    (c.get("targeting_json") or {}).get(
                        "proximity", {}).get("business_id")
                    or c.get("business_id")
                    for c in candidates
                    if (c.get("targeting_json") or {}).get(
                        "proximity", {}).get("business_id")
                    or c.get("business_id")
                }),
                radius_m=DEFAULT_PROX_RADIUS_M,
                place_by_bid=place_by_bid)
        except Exception as e:
            logger.warning(f"_augment_places_from_db error: {e}")

    opportunities: list[dict] = []
    for c in candidates:
        t = c.get("targeting_json") or {}
        # Commute-mode gate
        modes = t.get("commute_modes") or []
        if modes and cmt.get("mode") not in modes:
            continue
        kinds = _kinds_for_targeting(t)
        if not kinds:
            continue
        rating = None
        biz_doc = None
        # Resolve a business (campaign.business_id or proximity.business_id)
        bid_id = (t.get("proximity") or {}).get("business_id") \
                    or c.get("business_id")
        if bid_id:
            biz_doc = await db.businesses.find_one({"business_id": bid_id})
            rating = (biz_doc or {}).get("rating")
        # ── geo_proximity ──────────────────────────────────────────────
        if "geo_proximity" in kinds and bid_id and bid_id in place_by_bid:
            place = place_by_bid[bid_id]
            radius_m = int((t.get("proximity") or {}).get(
                "radius_m", DEFAULT_PROX_RADIUS_M))
            dist = float(place.get("distance_from_route_m") or 0)
            extra_drive = int(place.get("extra_drive_time_seconds") or 0)
            d_score = _distance_score(dist, radius_m)
            reasons = [f"{(biz_doc or {}).get('name','business')} is "
                          f"{int(dist)}m off-route",
                          f"+{int(extra_drive/60)}min detour"]
            if rating:
                reasons.append(f"rating {rating}")
            # Phase 9c — Offers surface with their own kind for clarity
            # in analytics / Why-this-ad reasoning.
            kind = "offer_proximity" if c.get("_origin") == "offer" else "geo_proximity"
            opportunities.append(_make_opp(
                cmt, c, kind, d_score, reasons,
                distance_from_route_m=dist,
                extra_drive_time_seconds=extra_drive,
                weather_snapshot=weather, daypart=daypart,
                business_id=bid_id, business_name=(biz_doc or {}).get("name")))
        # ── destination_arrival ────────────────────────────────────────
        if "destination_arrival" in kinds and biz_doc and cmt.get("destination"):
            dest = cmt["destination"]
            ddist = _haversine_m(biz_doc["lat"], biz_doc["lng"],
                                          dest["lat"], dest["lng"])
            if ddist <= DEST_PROX_M:
                # Schedule for the last 10 min of ETA
                seconds_in = max(0, duration_s - DEST_ARRIVAL_WINDOW_MIN * 60)
                valid_from = started_at + timedelta(seconds=seconds_in)
                opportunities.append(_make_opp(
                    cmt, c, "destination_arrival", 0.9,
                    [f"{biz_doc['name']} is at your destination",
                      f"arrival in ~{int(duration_s/60)}min"],
                    valid_from=valid_from,
                    weather_snapshot=weather, daypart=daypart,
                    business_id=bid_id, business_name=biz_doc["name"]))
        # ── weather_triggered ──────────────────────────────────────────
        if "weather_triggered" in kinds:
            w_score, w_reasons = _weather_match_score(
                weather, t.get("weather_triggers") or [],
                t.get("temperature_band"))
            if w_score > 0:
                opportunities.append(_make_opp(
                    cmt, c, "weather_triggered", w_score,
                    w_reasons + [f"current weather: "
                                      f"{weather.get('condition','-')} "
                                      f"{int(weather.get('temp_c') or 0)}°C"],
                    weather_snapshot=weather, daypart=daypart,
                    business_id=bid_id,
                    business_name=(biz_doc or {}).get("name")))
        # ── daypart_triggered ──────────────────────────────────────────
        if "daypart_triggered" in kinds:
            wanted = t.get("dayparts") or []
            if daypart in wanted:
                opportunities.append(_make_opp(
                    cmt, c, "daypart_triggered", 1.0,
                    [f"it's {daypart.replace('_',' ')}",
                      f"campaign targets {','.join(wanted)}"],
                    weather_snapshot=weather, daypart=daypart,
                    business_id=bid_id,
                    business_name=(biz_doc or {}).get("name")))
        # ── traffic_triggered ──────────────────────────────────────────
        if "traffic_triggered" in kinds:
            wanted = t.get("traffic_triggers") or []
            if traffic in wanted:
                opportunities.append(_make_opp(
                    cmt, c, "traffic_triggered", 0.85,
                    [f"traffic is {traffic}",
                      f"campaign targets {','.join(wanted)}"],
                    weather_snapshot=weather, daypart=daypart,
                    business_id=bid_id,
                    business_name=(biz_doc or {}).get("name")))

        # Compose final blended score: dist 40 / wx 20 / dp 20 / rating 10 / bid 10
        # Done per-opp below.

    # Compose final scores for all opps
    for o in opportunities:
        o["score"] = _blend_score(o, rating_lookup=lambda bid_id:
                                            None)
    opportunities.sort(key=lambda o: o["score"], reverse=True)
    opportunities = opportunities[:MAX_OPPS_PER_COMMUTE]
    if opportunities:
        await db.route_ad_opportunities.insert_many(opportunities)
    return {"ok": True, "commute_id": commute_id,
              "candidates_evaluated": len(candidates),
              "opportunities_created": len(opportunities),
              "daypart": daypart}


def _make_opp(cmt: dict, c: dict, kind: str, sub_score: float,
                  reasons: list[str], *,
                  weather_snapshot: dict, daypart: str,
                  business_id: Optional[str] = None,
                  business_name: Optional[str] = None,
                  distance_from_route_m: Optional[float] = None,
                  extra_drive_time_seconds: Optional[int] = None,
                  valid_from: Optional[datetime] = None) -> dict:
    cid = c.get("campaign_id")
    started = cmt.get("started_at") or _now()
    dur_s = int(cmt.get("route_duration_in_traffic_s") or 0)
    valid_until = started + timedelta(seconds=dur_s + 600)
    opp_id = f"opp_{uuid.uuid4().hex[:14]}"
    origin = c.get("_origin", "ad")
    # Phase 9c — opp_source distinguishes offers from game_campaigns
    # and ad campaigns for analytics / "Why this ad?" reasoning.
    if origin == "offer":
        opp_source = "offer"
    elif origin == "game":
        opp_source = "game_campaign"
    else:
        opp_source = "ad_campaign"
    return {
        "_id": opp_id, "opp_id": opp_id,
        "commute_id": cmt["commute_id"], "user_id": cmt["user_id"],
        "business_id": business_id, "business_name": business_name,
        "campaign_id": cid,
        "campaign_origin": origin,
        "opp_source": opp_source,
        "offer_id": c.get("offer_id"),
        "campaign_title": c.get("title") or c.get("name") or "Campaign",
        "sponsor_name": c.get("sponsor_name") or c.get("advertiser_id"),
        "sponsor_logo_url": c.get("sponsor_logo_url"),
        "kind": kind, "sub_score": float(sub_score),
        "reason_codes": list(reasons),
        "distance_from_route_m": distance_from_route_m,
        "extra_drive_time_seconds": extra_drive_time_seconds,
        "weather_snapshot": weather_snapshot, "daypart": daypart,
        "valid_from": (valid_from or started),
        "valid_until": valid_until,
        "selected": False,
        "shown_at": None, "engaged_at": None, "engagement_type": None,
        "bid_cents": int(c.get("bid_cents_per_impression")
                            or c.get("bid_amount_cents") or 100),
        "business_rating": None,    # filled by blend
        "created_at": _now(),
    }


def _blend_score(opp: dict, *, rating_lookup) -> float:
    """Compose final score.

    Weights:
      40% kind-specific sub-score (distance/weather/daypart/traffic match)
      20% weather context boost (precip if rainy, heat if hot)
      20% daypart bonus for prime drive hours
      10% business rating (0-5 → 0-1)
      10% bid (cents per impression, capped at $5 / 500c)
    """
    sub = float(opp.get("sub_score") or 0.0)
    weather = opp.get("weather_snapshot") or {}
    daypart = opp.get("daypart")
    # Weather context boost (independent of kind):
    wbonus = 0.0
    if (weather.get("precipitation_mm") or 0) > 0.5:
        wbonus = 0.3
    if (weather.get("temp_c") or 25) >= 38:
        wbonus = max(wbonus, 0.4)
    # Daypart bonus for prime-drive
    dbonus = 0.8 if daypart in ("morning_drive", "evening_drive",
                                          "lunch") else 0.4
    # Rating bonus
    rating = opp.get("business_rating")
    rbonus = (float(rating) / 5.0) if rating else 0.4
    # Bid bonus
    bid = float(opp.get("bid_cents") or 0)
    bbonus = min(1.0, bid / 500.0)
    score = (0.40 * sub + 0.20 * wbonus + 0.20 * dbonus
               + 0.10 * rbonus + 0.10 * bbonus)
    return round(min(1.0, max(0.0, score)), 4)


# ═══════════════════════════════════════════════════════════════════════
# Radio engine hook — choose a route-targeted ad if any eligible
# ═══════════════════════════════════════════════════════════════════════
async def pick_route_targeted_ad(db, *, user: dict,
                                          segment_context: dict) -> Optional[dict]:
    """Inspect route_ad_opportunities for the user; return an ad-engine
    decision dict shaped like select_ad's, or None.

    Honors the 15-minute cooldown.  Logs the decision to
    route_ad_decision_log.
    """
    user_id = user.get("user_id")
    if not user_id:
        return None
    # Get the user's active commute
    cmt = await db.commute_sessions.find_one(
        {"user_id": user_id, "status": "active"})
    if not cmt:
        await _log_decision(db, user_id, None,
                                  "no_active_commute", None, 0)
        return None
    commute_id = cmt["commute_id"]
    # Cooldown check
    cutoff = _now() - timedelta(minutes=ROUTE_AD_COOLDOWN_MINUTES)
    recent = await db.route_ad_decision_log.count_documents({
        "user_id": user_id, "decision": "route_targeted_picked",
        "ts": {"$gte": cutoff},
    })
    if recent > 0:
        await _log_decision(db, user_id, commute_id,
                                  "route_targeted_skipped_cooldown",
                                  None, 0)
        return None
    # Find top-scoring eligible opp
    now = _now()
    cur = db.route_ad_opportunities.find({
        "user_id": user_id, "commute_id": commute_id,
        "selected": False,
        "valid_from": {"$lte": now},
        "valid_until": {"$gte": now},
    }).sort([("score", -1)])
    candidates = await cur.to_list(length=10)
    if not candidates:
        await _log_decision(db, user_id, commute_id,
                                  "route_targeted_none_eligible",
                                  None, 0)
        return None
    chosen = candidates[0]
    # Resolve creative + campaign full doc
    cid = chosen["campaign_id"]
    origin = chosen.get("campaign_origin", "ad")
    if origin == "ad":
        campaign = await db.campaigns.find_one({"campaign_id": cid})
    else:
        campaign = await db.game_campaigns.find_one({"campaign_id": cid})
    if not campaign:
        # Stale; mark engaged_at=dismissed so it doesn't re-fire
        await db.route_ad_opportunities.update_one(
            {"opp_id": chosen["opp_id"]},
            {"$set": {"engagement_type": "stale_campaign",
                       "engaged_at": _now()}})
        await _log_decision(db, user_id, commute_id,
                                  "route_targeted_none_eligible",
                                  chosen["opp_id"], len(candidates))
        return None
    # For ad-engine campaigns, find the creative
    creative = None
    actions = []
    business = None
    if origin == "ad":
        cr_id = (campaign.get("creative_ids") or [None])[0]
        if cr_id:
            creative = await db.ad_creatives.find_one(
                # Phase 36c.5 hotfix — see ad_decisioning.py for rationale.
                {"$and": [
                    {"$or": [{"id": cr_id}, {"creative_id": cr_id}]},
                    {"$or": [
                        {"status": {"$in": ["approved", "active"]}},
                        {"$and": [{"approval_status": "approved"},
                                        {"active": True}]},
                    ]},
                ]})
        if creative:
            actions = await db.ad_action_cards.find(
                {"campaign_id": cid, "enabled": True}
            ).sort([("display_order", 1)]).to_list(length=20)
        if campaign.get("business_id"):
            business = await db.businesses.find_one(
                {"business_id": campaign["business_id"]})
    # Mark selected
    await db.route_ad_opportunities.update_one(
        {"opp_id": chosen["opp_id"]},
        {"$set": {"selected": True, "shown_at": _now()}})
    await _log_decision(db, user_id, commute_id,
                              "route_targeted_picked", chosen["opp_id"],
                              len(candidates) - 1)
    if origin == "ad":
        if not creative:
            return None
        return {
            "decision_path": "route_targeted",
            "campaign": campaign, "creative": creative,
            "action_cards": actions, "business": business,
            "route_opp_id": chosen["opp_id"],
            "route_reason_codes": chosen.get("reason_codes", []),
        }
    # Game-campaign origin: surface as a route-targeted recommendation
    # (no creative; consumer caller can choose to surface differently)
    return {
        "decision_path": "route_targeted_game",
        "campaign": campaign, "creative": None,
        "action_cards": [], "business": business,
        "route_opp_id": chosen["opp_id"],
        "route_reason_codes": chosen.get("reason_codes", []),
    }


async def _log_decision(db, user_id: Optional[str], commute_id: Optional[str],
                              decision: str, opp_id: Optional[str],
                              competing_opps_count: int) -> None:
    doc = {
        "_id": str(uuid.uuid4()), "user_id": user_id,
        "commute_id": commute_id, "decision": decision,
        "opp_id": opp_id, "competing_opps_count": int(competing_opps_count),
        "ts": _now(),
    }
    try:
        await db.route_ad_decision_log.insert_one(doc)
    except Exception as e:
        logger.debug(f"decision_log insert: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Engagement helpers (frontend hits these)
# ═══════════════════════════════════════════════════════════════════════
async def mark_opp_engagement(db, *, opp_id: str, user_id: str,
                                       engagement_type: str) -> Optional[dict]:
    """clicked | saved | played | dismissed."""
    if engagement_type not in ("clicked", "saved", "played", "dismissed"):
        raise ValueError("invalid_engagement_type")
    row = await db.route_ad_opportunities.find_one(
        {"opp_id": opp_id, "user_id": user_id})
    if not row:
        return None
    await db.route_ad_opportunities.update_one(
        {"opp_id": opp_id},
        {"$set": {"engagement_type": engagement_type,
                   "engaged_at": _now()}})
    return {"ok": True, "opp_id": opp_id,
              "engagement_type": engagement_type}


async def get_opp_reason_codes(db, *, opp_id: str) -> Optional[dict]:
    """Public-ish (auth-gated) endpoint payload for the "Why this ad?" modal."""
    row = await db.route_ad_opportunities.find_one({"opp_id": opp_id})
    if not row:
        return None
    return {
        "opp_id": row["opp_id"], "kind": row["kind"],
        "commute_id": row.get("commute_id"),
        "reason_codes": row.get("reason_codes", []),
        "score": row.get("score"),
        "campaign_title": row.get("campaign_title"),
        "sponsor_name": row.get("sponsor_name"),
        "business_name": row.get("business_name"),
        "weather_snapshot": row.get("weather_snapshot"),
        "daypart": row.get("daypart"),
        "valid_from": (row["valid_from"].isoformat()
                          if row.get("valid_from") else None),
        "valid_until": (row["valid_until"].isoformat()
                            if row.get("valid_until") else None),
        "shown_at": (row["shown_at"].isoformat()
                        if row.get("shown_at") else None),
    }


async def list_opportunities_for_commute(db, *, commute_id: str,
                                                    user_id: str,
                                                    only_upcoming: bool = True) -> list[dict]:
    q = {"commute_id": commute_id, "user_id": user_id}
    if only_upcoming:
        q["valid_until"] = {"$gte": _now()}
    cur = db.route_ad_opportunities.find(q).sort([("score", -1)])
    out = []
    async for r in cur:
        out.append({
            "opp_id": r["opp_id"], "kind": r["kind"],
            # Phase 9b.1 — per-item commute_id + valid_from so clients can
            # cache opps across commute contexts without re-keying.
            "commute_id": r.get("commute_id"),
            "score": r.get("score"),
            "campaign_id": r["campaign_id"],
            # Phase 9c — distinguish ad campaigns vs game campaigns vs offers
            "opp_source": r.get("opp_source") or "ad_campaign",
            "offer_id": r.get("offer_id"),
            "campaign_title": r.get("campaign_title"),
            "sponsor_name": r.get("sponsor_name"),
            "sponsor_logo_url": r.get("sponsor_logo_url"),
            "business_id": r.get("business_id"),
            "business_name": r.get("business_name"),
            "distance_from_route_m": r.get("distance_from_route_m"),
            "extra_drive_time_seconds": r.get("extra_drive_time_seconds"),
            "weather_snapshot": r.get("weather_snapshot"),
            "daypart": r.get("daypart"),
            "reason_codes": r.get("reason_codes", []),
            "selected": bool(r.get("selected")),
            "engagement_type": r.get("engagement_type"),
            "valid_from": (r["valid_from"].isoformat()
                              if r.get("valid_from") else None),
            "valid_until": (r["valid_until"].isoformat()
                                if r.get("valid_until") else None),
        })
    return out


# ═══════════════════════════════════════════════════════════════════════
# RJ extras consumption — commute_just_completed
# ═══════════════════════════════════════════════════════════════════════
def _humanize_duration(seconds: int) -> str:
    if not seconds or seconds < 0:
        return "a quick"
    m = round(seconds / 60)
    if m < 1:
        return "a quick"
    if m < 60:
        return f"{m}-minute"
    h, rem = divmod(m, 60)
    if rem:
        return f"{h}h {rem}m"
    return f"{h}-hour"


async def enqueue_commute_arrival_rj_extra(db, *, user_id: str,
                                                       cmt: dict) -> dict:
    """Push a `commute_just_completed` extra into `users.pending_rj_extras`.

    TTL'd by `expires_at`.  Cooldown 30 minutes per listener — tracked
    via `users.last_commute_arrival_mention_at` so it survives the pop
    consumer.  (Pre-9b.1 we tried to derive cooldown from the queue
    itself, which crashed on offset-naive vs aware datetime compares
    once an entry survived a server restart.)
    """
    now = _now()
    cutoff = now - timedelta(minutes=30)
    u = await db.users.find_one(
        {"user_id": user_id}, {"last_commute_arrival_mention_at": 1})
    if u:
        last = u.get("last_commute_arrival_mention_at")
        if last:
            # Handle BSON datetimes that came back offset-naive
            if isinstance(last, datetime) and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last > cutoff:
                return {"queued": False, "reason": "cooldown",
                          "last_commute_arrival_mention_at": last.isoformat()}
    dest = cmt.get("destination") or {}
    label = (dest.get("label") or "your destination") if isinstance(dest, dict) else "your destination"
    dur_s = int(cmt.get("route_duration_in_traffic_s") or 0)
    weather = cmt.get("weather_snapshot") or {}
    extra = {
        "extra_id": f"rjx_{uuid.uuid4().hex[:14]}",
        "kind": "commute_just_completed",
        "payload": {
            "destination_label": label,
            "duration_minutes": int(dur_s / 60) if dur_s else 0,
            "duration_human": _humanize_duration(dur_s),
            "weather_condition": weather.get("condition", "clear"),
            "traffic_status": cmt.get("traffic_status", "unknown"),
        },
        "created_at": now,
        "expires_at": now + timedelta(minutes=10),
    }
    await db.users.update_one(
        {"user_id": user_id},
        {"$push": {"pending_rj_extras": extra},
          "$set": {"last_commute_arrival_mention_at": now}})
    return {"queued": True, "extra_id": extra["extra_id"],
              "payload": extra["payload"],
              "last_commute_arrival_mention_at": now.isoformat()}


async def pop_pending_rj_extra(db, *, user_id: str) -> Optional[dict]:
    """Atomic claim of the head pending_rj_extra.  Returns None if none."""
    while True:
        u = await db.users.find_one(
            {"user_id": user_id},
            {"pending_rj_extras": 1})
        items = (u or {}).get("pending_rj_extras") or []
        # Drop expired
        now = _now()
        if items:
            exp = items[0].get("expires_at")
            if exp is not None:
                if isinstance(exp, datetime) and exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now:
                    await db.users.update_one(
                        {"user_id": user_id},
                        {"$pop": {"pending_rj_extras": -1}})
                    continue
        if not items:
            return None
        head = items[0]
        eid = head.get("extra_id")
        r = await db.users.update_one(
            {"user_id": user_id,
              "pending_rj_extras.0.extra_id": eid},
            {"$pop": {"pending_rj_extras": -1}})
        if r.modified_count == 1:
            return head
        # CAS collision, retry once.
        continue


# ═══════════════════════════════════════════════════════════════════════
# Indexes
# ═══════════════════════════════════════════════════════════════════════
async def ensure_route_ad_indexes(db) -> None:
    await db.route_ad_opportunities.create_index(
        [("user_id", 1), ("valid_until", 1)])
    await db.route_ad_opportunities.create_index(
        [("commute_id", 1), ("score", -1)])
    await db.route_ad_opportunities.create_index([("opp_id", 1)],
                                                              unique=True)
    # TTL: 6 hours after valid_until
    await db.route_ad_opportunities.create_index(
        [("valid_until", 1)], expireAfterSeconds=6 * 3600)
    await db.route_ad_decision_log.create_index(
        [("user_id", 1), ("ts", -1)])
    await db.route_ad_decision_log.create_index(
        [("commute_id", 1), ("ts", -1)])
    # 90 day TTL on decision log
    await db.route_ad_decision_log.create_index(
        [("ts", 1)], expireAfterSeconds=90 * 24 * 3600)


__all__ = [
    "compute_route_opportunities", "pick_route_targeted_ad",
    "mark_opp_engagement", "get_opp_reason_codes",
    "list_opportunities_for_commute", "ensure_route_ad_indexes",
    "validate_targeting_smart", "enqueue_commute_arrival_rj_extra",
    "pop_pending_rj_extra", "hour_to_daypart", "daypart_for_market",
    "DAYPARTS", "WEATHER_CONDITIONS", "TRAFFIC_STATES",
    "ROUTE_AD_COOLDOWN_MINUTES",
]
