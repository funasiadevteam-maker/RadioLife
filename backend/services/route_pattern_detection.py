"""Phase 39 Session 6 — Route pattern + business visit detection.

Reads UserTravelEvents (consent_level >= 3 only — caller enforces), groups
them into trips, snaps origin/destination to UserFrequentPlace docs when
within 200m, then clusters repeated origin→destination pairs into
UserRoutePatterns when seen ≥3 times in the last 30 days.

When a trip's destination snaps to a known-category place (cafe / restaurant
/ gym / mall / bar / club / gas_station / salon / dessert / grocery), an
append-only row is written to UserBusinessVisits for the recommender +
advertiser engines to consume.

All detection is idempotent: each trip_id is deterministic on
(user_id, origin_place_id, destination_place_id, started_at) so repeated
sweeps don't dupe rows.
"""
from __future__ import annotations

import hashlib
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("bigfm.routes")

TRIP_GAP_MIN          = 90       # minutes: events farther apart start a new trip
SEPARATION_M          = 100      # minimum displacement between events in same trip
SNAP_M                = 200      # snap distance to a UserFrequentPlace
LOOKBACK_DAYS         = 30
PATTERN_MIN_REPEATS   = 3
BUSINESS_CATEGORIES   = {
    "cafe", "restaurant", "bar", "club", "gym", "mall", "gas_station",
    "salon", "dessert", "grocery", "fast_food", "theater",
}


def _now() -> datetime: return datetime.now(timezone.utc)


def _haversine_m(a_lat: float, a_lng: float,
                 b_lat: float, b_lng: float) -> float:
    R = 6371000.0
    phi1 = math.radians(a_lat); phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlam = math.radians(b_lng - a_lng)
    h = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _trip_id(user_id: str, origin_pid: Optional[str],
             dest_pid: Optional[str], started_at: datetime) -> str:
    seed = f"{user_id}|{origin_pid or '_'}|{dest_pid or '_'}|{started_at.isoformat()}"
    return "trip_" + hashlib.sha1(seed.encode()).hexdigest()[:14]


def _pattern_id(user_id: str, origin_pid: str, dest_pid: str) -> str:
    seed = f"{user_id}|{origin_pid}|{dest_pid}"
    return "pat_" + hashlib.sha1(seed.encode()).hexdigest()[:14]


def _snap_to_place(places: list[dict], lat: float, lng: float) -> Optional[dict]:
    best = None; best_d = SNAP_M + 1
    for p in places:
        d = _haversine_m(lat, lng, p["lat"], p["lng"])
        if d <= SNAP_M and d < best_d:
            best = p; best_d = d
    return best


def _time_bucket(dt: datetime) -> str:
    h = dt.hour
    if 5 <= h < 11:  return "morning"
    if 11 <= h < 15: return "lunch"
    if 15 <= h < 20: return "evening"
    return "night"


def _segment_events_into_trips(events: list[dict]) -> list[list[dict]]:
    """Order events oldest→newest, then split whenever the gap between
    consecutive events exceeds TRIP_GAP_MIN or the user has clearly stopped
    moving (separation < SEPARATION_M for the whole stretch — collapsed)."""
    if not events:
        return []
    events = sorted(events, key=lambda e: e["captured_at"])
    trips: list[list[dict]] = []
    current: list[dict] = [events[0]]
    for e in events[1:]:
        prev = current[-1]
        gap_s = (e["captured_at"] - prev["captured_at"]).total_seconds()
        sep_m = _haversine_m(prev["lat"], prev["lng"], e["lat"], e["lng"])
        if gap_s > TRIP_GAP_MIN * 60:
            if len(current) >= 2:
                trips.append(current)
            current = [e]
        elif sep_m >= SEPARATION_M:
            current.append(e)
        else:
            # tiny jitter — drop point (don't reset trip)
            continue
    if len(current) >= 2:
        trips.append(current)
    return trips


async def detect_for_user(db, user_id: str) -> dict:
    """Idempotent detection sweep for a single user.

    Returns a counts dict.  Caller is responsible for the consent gate."""
    cutoff = _now() - timedelta(days=LOOKBACK_DAYS)
    events: list[dict] = []
    async for e in db.UserTravelEvents.find(
        {"user_id": user_id, "captured_at": {"$gte": cutoff}}
    ):
        events.append(e)
    places: list[dict] = []
    async for p in db.UserFrequentPlaces.find(
        {"user_id": user_id, "user_hidden": {"$ne": True}}
    ):
        places.append(p)

    trips = _segment_events_into_trips(events)

    trips_inserted = visits_inserted = patterns_upserted = 0
    by_pair: dict[tuple, list[dict]] = {}

    for trip_events in trips:
        origin = trip_events[0]; dest = trip_events[-1]
        origin_place = _snap_to_place(places, origin["lat"], origin["lng"])
        dest_place   = _snap_to_place(places, dest["lat"], dest["lng"])
        origin_pid = origin_place["place_id"] if origin_place else None
        dest_pid   = dest_place["place_id"]   if dest_place   else None
        started_at = origin["captured_at"]
        ended_at   = dest["captured_at"]
        tid = _trip_id(user_id, origin_pid, dest_pid, started_at)

        trip_doc = {
            "_id":              tid,
            "user_id":      user_id,
            "started_at": started_at,
            "ended_at":   ended_at,
            "duration_min": int((ended_at - started_at).total_seconds() / 60),
            "origin_place_id":     origin_pid,
            "destination_place_id": dest_pid,
            "origin_lat":   origin["lat"], "origin_lng": origin["lng"],
            "destination_lat": dest["lat"], "destination_lng": dest["lng"],
            "event_count":  len(trip_events),
            "time_bucket": _time_bucket(started_at),
            "detected_at": _now(),
        }
        # upsert
        existed = await db.UserTrips.find_one({"_id": tid})
        if not existed:
            await db.UserTrips.insert_one(trip_doc)
            trips_inserted += 1

        # Business visit on a known-category destination.
        if dest_place and dest_place.get("category") in BUSINESS_CATEGORIES:
            vid = "bv_" + hashlib.sha1(
                f"{tid}|{dest_pid}".encode()).hexdigest()[:14]
            exists_v = await db.UserBusinessVisits.find_one({"_id": vid})
            if not exists_v:
                await db.UserBusinessVisits.insert_one({
                    "_id":              vid,
                    "user_id":      user_id,
                    "trip_id":      tid,
                    "place_id":   dest_pid,
                    "category":   dest_place.get("category"),
                    "label":         dest_place.get("label"),
                    "visited_at": ended_at,
                    "time_bucket": _time_bucket(ended_at),
                    "detected_at": _now(),
                })
                visits_inserted += 1

        if origin_pid and dest_pid and origin_pid != dest_pid:
            by_pair.setdefault((origin_pid, dest_pid), []).append(trip_doc)

    # Route pattern aggregation (≥3 repeats in last 30 days).
    for (op, dp), pair_trips in by_pair.items():
        if len(pair_trips) < PATTERN_MIN_REPEATS:
            continue
        pid = _pattern_id(user_id, op, dp)
        # Most common time bucket for this pattern.
        bucket_counts: dict[str, int] = {}
        for t in pair_trips:
            bucket_counts[t["time_bucket"]] = bucket_counts.get(t["time_bucket"], 0) + 1
        dominant_bucket = max(bucket_counts, key=bucket_counts.get)
        await db.UserRoutePatterns.update_one(
            {"_id": pid},
            {"$set": {
                "_id":              pid,
                "user_id":      user_id,
                "origin_place_id":     op,
                "destination_place_id": dp,
                "repeat_count": len(pair_trips),
                "dominant_time_bucket": dominant_bucket,
                "last_seen":  max(t["started_at"] for t in pair_trips),
                "first_seen": min(t["started_at"] for t in pair_trips),
                "detected_at": _now(),
            }},
            upsert=True)
        patterns_upserted += 1

    return {
        "trips_inserted": trips_inserted,
        "patterns_upserted": patterns_upserted,
        "business_visits_inserted": visits_inserted,
        "events_scanned": len(events),
        "places_known": len(places),
    }


async def ensure_routes_indexes(db) -> None:
    try:
        await db.UserTrips.create_index(
            [("user_id", 1), ("started_at", -1)], name="trips_user_time")
        await db.UserRoutePatterns.create_index(
            [("user_id", 1), ("last_seen", -1)], name="patterns_user_lastseen")
        await db.UserBusinessVisits.create_index(
            [("user_id", 1), ("visited_at", -1)], name="bv_user_time")
        await db.UserBusinessVisits.create_index(
            [("user_id", 1), ("category", 1), ("visited_at", -1)],
            name="bv_user_category_time")
        log.info("[routes] indexes ensured")
    except Exception as e:
        log.warning("[routes] ensure indexes failed: %s", e)


async def get_location_context(db, user_id: str) -> Optional[dict]:
    """Returns a compact dict the RJ prompt can weave into a greeting, or
    None if the user has no detected patterns / visits.

    Shape:
        {
          "morning_commute":  {"label": "Office (JLT)", "category": "office"} | None,
          "recent_business_visit": {"label": "Karak Cafe", "category": "cafe",
                                                              "time_bucket": "evening"} | None,
          "current_time_bucket": "morning|lunch|evening|night",
          "pattern_count": int,
        }
    """
    pattern_count = await db.UserRoutePatterns.count_documents(
        {"user_id": user_id})
    if pattern_count == 0:
        return None
    morning = await db.UserRoutePatterns.find_one(
        {"user_id": user_id, "dominant_time_bucket": "morning"},
        sort=[("repeat_count", -1)])
    morning_destination_label = None
    if morning and morning.get("destination_place_id"):
        d = await db.UserFrequentPlaces.find_one(
            {"user_id": user_id, "place_id": morning["destination_place_id"]})
        if d:
            morning_destination_label = {
                "label":    d.get("label") or "your usual spot",
                "category": d.get("category") or "place"}
    recent_bv = await db.UserBusinessVisits.find_one(
        {"user_id": user_id}, sort=[("visited_at", -1)])
    bv_struct = None
    if recent_bv:
        bv_struct = {
            "label":         recent_bv.get("label") or "a spot",
            "category":   recent_bv.get("category") or "place",
            "time_bucket": recent_bv.get("time_bucket") or "evening",
        }
    return {
        "morning_commute": morning_destination_label,
        "recent_business_visit": bv_struct,
        "current_time_bucket":   _time_bucket(_now()),
        "pattern_count": pattern_count,
    }
