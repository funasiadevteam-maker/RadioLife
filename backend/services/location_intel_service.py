"""Phase S — Location Intelligence.

Read-only geospatial analytics over data already collected:
  • `commute_sessions`             — origin + destination lat/lng, per user (bulk source).
  • `location_boost_impressions`   — Phase J impression lat/lng.
  • `location_boost_campaigns`     — Phase J geofenced campaigns.
  • `businesses`                   — lat/lng per merchant.
  • `payment_transactions_v2`      — scan-to-pay conversion linkage.

`user_location_pings` is DEFINED for future ping-based analytics but is
empty in demo — the service unions the two commute lat/lng points +
location_boost_impressions to produce a "ping stream" for aggregation.

Cache: `location_intel_cache` collection.  15-min TTL, keyed by a
hash of the endpoint parameters.  `?refresh=true` busts the cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger("bigfm.location_intel")

CACHE_TTL_SEC = 15 * 60
BUCKET_RESOLUTION_DEG = 0.01      # ≈ 1.1 km cells.
NEARBY_METERS = 500
CONVERSION_WINDOW_MIN = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes(db) -> None:
    try:
        await db.location_intel_cache.create_index("query_key", unique=True)
        await db.location_intel_cache.create_index("computed_at")
    except Exception as e:
        log.warning("location_intel index setup failed: %s", e)


# ─── auth helper ─────────────────────────────────────
async def check_business_access(db, business_id: str,
                                 user: Dict[str, Any]) -> bool:
    if user.get("role") == "admin":
        return True
    uid = user.get("user_id")
    if not uid:
        return False
    biz = await db.businesses.find_one({"business_id": business_id},
                                         {"_id": 0, "staff_users": 1,
                                          "advertiser_id": 1,
                                          "owner_user_id": 1})
    if not biz:
        return False
    if uid in (biz.get("staff_users") or []):
        return True
    if biz.get("owner_user_id") == uid:
        return True
    adv_id = biz.get("advertiser_id")
    if adv_id:
        adv = await db.advertisers_v2.find_one(
            {"$or": [{"id": adv_id}, {"advertiser_id": adv_id}]},
            {"_id": 0, "owner_user_id": 1, "staff_user_ids": 1})
        if adv:
            if adv.get("owner_user_id") == uid:
                return True
            if uid in (adv.get("staff_user_ids") or []):
                return True
        # Legacy advertisers table.
        adv = await db.advertisers.find_one(
            {"advertiser_id": adv_id},
            {"_id": 0, "user_id": 1})
        if adv and adv.get("user_id") == uid:
            return True
    return False


# ─── cache ───────────────────────────────────────────
def _cache_key(endpoint: str, params: Dict[str, Any]) -> str:
    raw = json.dumps({"e": endpoint, "p": params}, sort_keys=True,
                     default=str).encode()
    return hashlib.sha1(raw).hexdigest()


async def _cache_get(db, key: str) -> Optional[Dict[str, Any]]:
    row = await db.location_intel_cache.find_one({"query_key": key},
                                                     {"_id": 0})
    if not row:
        return None
    computed = row.get("computed_at")
    if computed and computed.tzinfo is None:
        computed = computed.replace(tzinfo=timezone.utc)
    ttl = row.get("ttl_seconds", CACHE_TTL_SEC)
    if computed and (_now() - computed).total_seconds() > ttl:
        return None
    return row.get("payload_json")


async def _cache_set(db, key: str, payload: Dict[str, Any]) -> None:
    await db.location_intel_cache.update_one(
        {"query_key": key},
        {"$set": {"query_key":     key,
                  "payload_json":  payload,
                  "computed_at":   _now(),
                  "ttl_seconds":   CACHE_TTL_SEC}},
        upsert=True)


# ─── geo utils ────────────────────────────────────
_EARTH_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_M * math.asin(math.sqrt(a))


def _bucket(lat: float, lng: float) -> Tuple[float, float]:
    r = BUCKET_RESOLUTION_DEG
    return (round(round(lat / r) * r, 4), round(round(lng / r) * r, 4))


def _in_bounds(lat: float, lng: float,
               bounds: Optional[Dict[str, float]]) -> bool:
    if not bounds:
        return True
    return (bounds["sw_lat"] <= lat <= bounds["ne_lat"] and
            bounds["sw_lng"] <= lng <= bounds["ne_lng"])


# ─── unified ping stream ─────────────────────────
async def _iter_pings(db, cutoff: datetime,
                      bounds: Optional[Dict[str, float]] = None
                      ) -> List[Dict[str, Any]]:
    """Return a list of pseudo-pings unioning:
    (a) commute_sessions origin  (b) commute_sessions destination
    (c) location_boost_impressions (Phase J)
    (d) user_location_pings (empty in demo — future-proof)."""
    pings: List[Dict[str, Any]] = []

    # (a) + (b) commute origin/destination.
    q = {"started_at": {"$gte": cutoff}}
    async for c in db.commute_sessions.find(q,
            {"_id": 0, "user_id": 1, "origin": 1, "destination": 1,
             "started_at": 1}):
        ts = c.get("started_at")
        uid = c.get("user_id")
        for kind in ("origin", "destination"):
            p = c.get(kind) or {}
            lat = p.get("lat"); lng = p.get("lng")
            if lat is None or lng is None:
                continue
            if not _in_bounds(lat, lng, bounds):
                continue
            pings.append({"lat": lat, "lng": lng,
                          "user_id": uid, "ts": ts,
                          "source": f"commute_{kind}"})

    # (c) location_boost_impressions.
    async for r in db.location_boost_impressions.find(
            {"served_at": {"$gte": cutoff}},
            {"_id": 0, "user_id": 1, "lat": 1, "lng": 1,
             "served_at": 1, "campaign_id": 1,
             "advertiser_business_id": 1}):
        lat = r.get("lat"); lng = r.get("lng")
        if lat is None or lng is None:
            continue
        if not _in_bounds(lat, lng, bounds):
            continue
        pings.append({"lat": lat, "lng": lng,
                      "user_id": r.get("user_id"),
                      "ts": r.get("served_at"),
                      "source": "location_boost_impression",
                      "campaign_id": r.get("campaign_id")})

    # (d) native user_location_pings (empty today, future-proofed).
    try:
        async for r in db.user_location_pings.find(
                {"pinged_at": {"$gte": cutoff}},
                {"_id": 0, "user_id": 1, "lat": 1, "lng": 1,
                 "pinged_at": 1}):
            lat = r.get("lat"); lng = r.get("lng")
            if lat is None or lng is None:
                continue
            if not _in_bounds(lat, lng, bounds):
                continue
            pings.append({"lat": lat, "lng": lng,
                          "user_id": r.get("user_id"),
                          "ts": r.get("pinged_at"),
                          "source": "user_location_ping"})
    except Exception:
        pass
    return pings


# ─── admin endpoints ─────────────────────────────
async def admin_heatmap(db, *, bounds: Dict[str, float], days: int,
                         refresh: bool = False) -> Dict[str, Any]:
    key = _cache_key("heatmap", {"b": bounds, "d": days})
    if not refresh:
        c = await _cache_get(db, key)
        if c is not None:
            return {**c, "cached": True}

    cutoff = _now() - timedelta(days=days)
    pings = await _iter_pings(db, cutoff, bounds)
    cells: Dict[Tuple[float, float], int] = {}
    for p in pings:
        b = _bucket(p["lat"], p["lng"])
        cells[b] = cells.get(b, 0) + 1

    ordered = sorted(cells.items(), key=lambda x: -x[1])
    payload = {
        "bounds":               bounds,
        "days":                 days,
        "total_pings":          len(pings),
        "unique_cells":         len(cells),
        "resolution_deg":       BUCKET_RESOLUTION_DEG,
        "cells": [{"lat": lat, "lng": lng, "count": n}
                  for (lat, lng), n in ordered[:2000]],
        "sources": {
            "commute_origin":                sum(1 for p in pings if p["source"] == "commute_origin"),
            "commute_destination":            sum(1 for p in pings if p["source"] == "commute_destination"),
            "location_boost_impression":  sum(1 for p in pings if p["source"] == "location_boost_impression"),
            "user_location_ping":              sum(1 for p in pings if p["source"] == "user_location_ping"),
        },
        "cached":               False,
    }
    await _cache_set(db, key, payload)
    return payload


async def admin_regions_rank(db, *, days: int, limit: int,
                              refresh: bool = False) -> Dict[str, Any]:
    key = _cache_key("regions_rank", {"d": days, "l": limit})
    if not refresh:
        c = await _cache_get(db, key)
        if c is not None:
            return {**c, "cached": True}

    cutoff = _now() - timedelta(days=days)
    pings = await _iter_pings(db, cutoff)

    # Bucket at 0.1° (~ 11 km) for region-level grouping.  We then attempt
    # to attach a city name by matching to the nearest business.
    coarse: Dict[Tuple[float, float], Dict[str, Any]] = {}
    for p in pings:
        b = (round(p["lat"], 1), round(p["lng"], 1))
        e = coarse.setdefault(b,
                              {"ping_count": 0, "users": set(),
                               "lat_sum": 0.0, "lng_sum": 0.0})
        e["ping_count"] += 1
        if p.get("user_id"):
            e["users"].add(p["user_id"])
        e["lat_sum"] += p["lat"]; e["lng_sum"] += p["lng"]

    # Fetch all businesses with lat/lng for city labelling.
    biz_index: List[Dict[str, Any]] = []
    async for b in db.businesses.find(
            {"latitude": {"$ne": None}, "longitude": {"$ne": None}},
            {"_id": 0, "business_id": 1, "city": 1,
             "latitude": 1, "longitude": 1, "market": 1}):
        biz_index.append(b)

    # Active geofences per region — count Phase J campaigns whose
    # geofence center is within 15 km of the bucket centroid.
    async def _active_gf_count(centroid_lat: float, centroid_lng: float) -> int:
        n = 0
        async for c in db.location_boost_campaigns.find(
                {"status": {"$in": ["active", "live"]}},
                {"_id": 0, "geofences": 1}):
            for g in c.get("geofences", []) or []:
                if g.get("type") == "radius":
                    d = haversine_m(centroid_lat, centroid_lng,
                                    g.get("center_lat", 0),
                                    g.get("center_lng", 0))
                    if d < 15_000:
                        n += 1
                        break
        return n

    items: List[Dict[str, Any]] = []
    for _bucket, e in coarse.items():
        n = e["ping_count"]
        clat = e["lat_sum"] / n
        clng = e["lng_sum"] / n
        # Nearest business for city label.
        city = None; region_code = None; market = None
        best = None; best_d = 1e18
        for b in biz_index:
            d = haversine_m(clat, clng, b["latitude"], b["longitude"])
            if d < best_d:
                best_d = d; best = b
        if best and best_d < 25_000:
            city = best.get("city"); market = best.get("market")
            region_code = market or city
        items.append({
            "region_code":     region_code,
            "city":            city,
            "market":          market,
            "centroid":        {"lat": round(clat, 4), "lng": round(clng, 4)},
            "ping_count":      n,
            "unique_users":    len(e["users"]),
            "active_geofences": await _active_gf_count(clat, clng),
        })
    items.sort(key=lambda x: -x["ping_count"])
    payload = {"days": days, "total_regions": len(items),
               "items": items[:limit], "cached": False}
    await _cache_set(db, key, payload)
    return payload


async def admin_geofence_effectiveness(db, *, days: int,
                                        refresh: bool = False
                                        ) -> Dict[str, Any]:
    key = _cache_key("gfx_effectiveness", {"d": days})
    if not refresh:
        c = await _cache_get(db, key)
        if c is not None:
            return {**c, "cached": True}

    cutoff = _now() - timedelta(days=days)
    campaigns: List[Dict[str, Any]] = []

    async for c in db.location_boost_campaigns.find(
            {}, {"_id": 0, "id": 1, "advertiser_business_id": 1,
                 "display_name": 1, "geofences": 1, "status": 1,
                 "base_ad_type": 1, "base_ad_id": 1,
                 "plays_delivered": 1, "media_cost_cents": 1}):
        cid = c["id"]
        # Impressions.
        n_imp = await db.location_boost_impressions.count_documents({
            "campaign_id": cid, "served_at": {"$gte": cutoff}})
        # Unique users.
        u_users = 0
        try:
            u_users = len(await db.location_boost_impressions.distinct(
                "user_id", {"campaign_id": cid,
                            "served_at": {"$gte": cutoff}}))
        except Exception:
            pass
        # Geofence area (sum radius circles + polygon bbox approx).
        area_km2 = 0.0
        for g in c.get("geofences", []) or []:
            if g.get("type") == "radius":
                r_km = (g.get("radius_meters") or 0) / 1000.0
                area_km2 += math.pi * r_km * r_km
            elif g.get("type") == "polygon":
                pts = g.get("polygon") or []
                if len(pts) >= 3:
                    # Shoelace approx.
                    lat0 = sum(p.get("lat", 0) for p in pts) / len(pts)
                    lng0 = sum(p.get("lng", 0) for p in pts) / len(pts)
                    a = 0.0
                    for i, p in enumerate(pts):
                        q = pts[(i + 1) % len(pts)]
                        dx = (q.get("lng", 0) - p.get("lng", 0)) * 111.32 * math.cos(math.radians(lat0))
                        dy = (q.get("lat", 0) - p.get("lat", 0)) * 110.57
                        a += (p.get("lng", 0) * dy - q.get("lng", 0) * dy) * 0.5
                    area_km2 += abs(a) or 1.0
        # CTR estimate = banner_clicks (matching base_ad_id) / impressions.
        ctr = None
        base_ad_id = c.get("base_ad_id")
        if n_imp > 0 and base_ad_id:
            try:
                clicks = await db.banner_clicks.count_documents(
                    {"banner_id": base_ad_id,
                     "created_at": {"$gte": cutoff}})
                ctr = round(clicks / n_imp, 4)
            except Exception:
                ctr = None
        campaigns.append({
            "campaign_id":            cid,
            "advertiser_business_id": c.get("advertiser_business_id"),
            "display_name":           c.get("display_name"),
            "status":                 c.get("status"),
            "base_ad_type":           c.get("base_ad_type"),
            "base_ad_id":             base_ad_id,
            "geofence_area_sq_km":    round(area_km2, 3),
            "impressions_delivered": n_imp,
            "unique_users_reached":  u_users,
            "ctr_estimate":           ctr,
            "media_cost_cents":       c.get("media_cost_cents", 0),
        })
    campaigns.sort(key=lambda x: -x["impressions_delivered"])
    payload = {"days": days, "total": len(campaigns),
               "items": campaigns, "cached": False}
    await _cache_set(db, key, payload)
    return payload


async def admin_summary(db, *, days: int,
                        refresh: bool = False) -> Dict[str, Any]:
    key = _cache_key("summary", {"d": days})
    if not refresh:
        c = await _cache_get(db, key)
        if c is not None:
            return {**c, "cached": True}

    cutoff = _now() - timedelta(days=days)
    pings = await _iter_pings(db, cutoff)

    unique_users = {p["user_id"] for p in pings if p.get("user_id")}
    n_boost_matches = sum(1 for p in pings
                          if p["source"] == "location_boost_impression")

    # Top city — take the biggest 0.1° bucket → nearest business city.
    coarse: Dict[Tuple[float, float], int] = {}
    for p in pings:
        b = (round(p["lat"], 1), round(p["lng"], 1))
        coarse[b] = coarse.get(b, 0) + 1
    top_bucket = None
    if coarse:
        top_bucket = max(coarse.items(), key=lambda x: x[1])[0]
    top_city = None
    if top_bucket:
        best = None; best_d = 1e18
        async for b in db.businesses.find(
                {"latitude": {"$ne": None}},
                {"_id": 0, "city": 1, "latitude": 1, "longitude": 1}):
            d = haversine_m(top_bucket[0], top_bucket[1],
                            b["latitude"], b["longitude"])
            if d < best_d:
                best_d = d; best = b
        if best and best_d < 25_000:
            top_city = best.get("city")

    # Hour-of-day histogram.
    hod: List[int] = [0] * 24
    for p in pings:
        ts = p.get("ts")
        if isinstance(ts, datetime):
            hod[ts.hour] += 1
    most_active_hour = int(hod.index(max(hod))) if any(hod) else None

    # Average distance from ping to nearest merchant.
    biz_pts: List[Tuple[float, float]] = []
    async for b in db.businesses.find(
            {"latitude": {"$ne": None}},
            {"_id": 0, "latitude": 1, "longitude": 1}):
        biz_pts.append((b["latitude"], b["longitude"]))
    dists: List[float] = []
    for p in pings[:2000]:   # cap for perf.
        best_d = 1e18
        for (bl, bg) in biz_pts:
            d = haversine_m(p["lat"], p["lng"], bl, bg)
            if d < best_d:
                best_d = d
        if best_d < 1e17:
            dists.append(best_d)
    avg_dist_m = round(sum(dists) / len(dists), 1) if dists else None

    payload = {
        "days":                                days,
        "total_pings":                      len(pings),
        "unique_users_pinged":         len(unique_users),
        "geofence_matches":              n_boost_matches,
        "top_city":                            top_city,
        "hour_of_day_histogram":     hod,
        "most_active_hour":            most_active_hour,
        "avg_distance_to_merchant_m": avg_dist_m,
        "cached":                                False,
    }
    await _cache_set(db, key, payload)
    return payload


# ─── merchant endpoint ─────────────────────────
async def merchant_foot_traffic(db, *, business_id: str, days: int,
                                 refresh: bool = False) -> Dict[str, Any]:
    key = _cache_key("merchant_ft", {"b": business_id, "d": days})
    if not refresh:
        c = await _cache_get(db, key)
        if c is not None:
            return {**c, "cached": True}

    biz = await db.businesses.find_one(
        {"business_id": business_id},
        {"_id": 0, "business_id": 1, "name": 1,
         "latitude": 1, "longitude": 1, "city": 1})
    if not biz:
        raise ValueError("business_not_found")
    if biz.get("latitude") is None or biz.get("longitude") is None:
        raise ValueError("business_has_no_location")

    cutoff = _now() - timedelta(days=days)
    pings = await _iter_pings(db, cutoff)
    lat0 = biz["latitude"]; lng0 = biz["longitude"]
    nearby = [p for p in pings
              if haversine_m(p["lat"], p["lng"], lat0, lng0) <= NEARBY_METERS]

    unique_users = {p["user_id"] for p in nearby if p.get("user_id")}

    hod: List[int] = [0] * 24
    dow: List[int] = [0] * 7
    for p in nearby:
        ts = p.get("ts")
        if isinstance(ts, datetime):
            hod[ts.hour] += 1
            dow[ts.weekday()] += 1

    # Top dwelling clusters (bucket 0.001° ≈ 110 m).
    clusters: Dict[Tuple[float, float], int] = {}
    for p in nearby:
        b = (round(p["lat"], 3), round(p["lng"], 3))
        clusters[b] = clusters.get(b, 0) + 1
    top_clusters = sorted(clusters.items(), key=lambda x: -x[1])[:5]

    # Scan-to-pay conversions: for each scan-to-pay txn at this merchant,
    # was there a nearby ping in the 60 min prior?
    scan_txns: List[Dict[str, Any]] = []
    async for t in db.payment_transactions_v2.find(
            {"merchant_id": business_id,
             "flow": {"$in": ["ad7_scan_to_pay", "ad7_split_share"]},
             "status": "succeeded",
             "succeeded_at": {"$gte": cutoff}},
            {"_id": 0, "transaction_id": 1, "user_id": 1,
             "succeeded_at": 1, "amount_cents": 1}):
        scan_txns.append(t)

    linked = 0
    for t in scan_txns:
        ts = t.get("succeeded_at")
        uid = t.get("user_id")
        if not isinstance(ts, datetime):
            continue
        win_start = ts - timedelta(minutes=CONVERSION_WINDOW_MIN)
        for p in nearby:
            pts = p.get("ts")
            if not isinstance(pts, datetime):
                continue
            if pts < win_start or pts > ts:
                continue
            if uid and p.get("user_id") == uid:
                linked += 1
                break

    payload = {
        "business_id":                      business_id,
        "business_name":                  biz.get("name"),
        "business_city":                    biz.get("city"),
        "days":                                    days,
        "nearby_radius_meters":      NEARBY_METERS,
        "nearby_pings_count":         len(nearby),
        "unique_nearby_users":         len(unique_users),
        "hour_of_day_histogram":     hod,
        "day_of_week_histogram":     dow,
        "top_dwelling_locations": [
            {"lat": lat, "lng": lng, "count": n}
            for (lat, lng), n in top_clusters],
        "scan_to_pay_txns_count":    len(scan_txns),
        "scan_to_pay_conversions_from_nearby_pings": linked,
        "conversion_window_minutes": CONVERSION_WINDOW_MIN,
        "cached":                                False,
    }
    await _cache_set(db, key, payload)
    return payload


# ─── advertiser density preview ───────────────
async def advertiser_density(db, *, center_lat: float, center_lng: float,
                              radius_meters: int, days: int,
                              refresh: bool = False) -> Dict[str, Any]:
    key = _cache_key("adv_density", {
        "lat": round(center_lat, 4), "lng": round(center_lng, 4),
        "r":   radius_meters, "d": days})
    if not refresh:
        c = await _cache_get(db, key)
        if c is not None:
            return {**c, "cached": True}

    cutoff = _now() - timedelta(days=days)
    pings = await _iter_pings(db, cutoff)
    hits = [p for p in pings
            if haversine_m(p["lat"], p["lng"], center_lat, center_lng)
            <= radius_meters]
    unique_users = {p["user_id"] for p in hits if p.get("user_id")}

    hod: List[int] = [0] * 24
    for p in hits:
        ts = p.get("ts")
        if isinstance(ts, datetime):
            hod[ts.hour] += 1

    # Competing campaigns — active Phase J boosts whose fence overlaps.
    competing = 0
    async for c in db.location_boost_campaigns.find(
            {"status": {"$in": ["active", "live"]}},
            {"_id": 0, "geofences": 1}):
        for g in c.get("geofences", []) or []:
            if g.get("type") == "radius":
                d = haversine_m(center_lat, center_lng,
                                g.get("center_lat", 0),
                                g.get("center_lng", 0))
                if d < (radius_meters + (g.get("radius_meters") or 0)):
                    competing += 1
                    break

    payload = {
        "center":                {"lat": center_lat, "lng": center_lng},
        "radius_meters":     radius_meters,
        "days":                    days,
        "ping_count":         len(hits),
        "estimated_reach": len(unique_users),
        "active_hours":       hod,
        "competing_campaigns_count": competing,
        "cached":                False,
    }
    await _cache_set(db, key, payload)
    return payload


__all__ = [
    "ensure_indexes", "check_business_access",
    "admin_heatmap", "admin_regions_rank",
    "admin_geofence_effectiveness", "admin_summary",
    "merchant_foot_traffic", "advertiser_density",
]
