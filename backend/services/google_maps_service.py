"""Phase H v1 — Google Maps Platform service wrapper.

Wraps four Google Maps Platform REST APIs with unified caching:
  * Routes API v2       (`v2:computeRoutes`, `v2:computeRouteMatrix`)
  * Places API (New)    (`places:searchNearby`)
  * Geocoding API       (`maps/api/geocode/json`)
  * Weather API         (`v1/currentConditions:lookup`)

Design notes
------------
* Real network calls only — no mocks.  Errors surface, they don't swallow.
* Independent from the pre-existing Phase 9a `services/maps_client.py`
    (which is mock-first, uses Mongo `maps_cache`, and has its own probe
    flow).  We do NOT touch that module.
* Redis first, in-memory `TTLCache` fallback if Redis unavailable.
    Warns on fallback so ops can see the degrade.
* Cache TTLs (seconds): Routes 60, Places 300, Weather 600, Geocode 86400.
* Cache key: ``gmaps:{method}:{sha256(payload)[:16]}``.
* Retries: httpx transport with max 2 retries on connection errors.  Do
    NOT retry on 4xx — those are permanent per Google's API design.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

import httpx
from cachetools import TTLCache

logger = logging.getLogger("bigfm.gmaps_v1")

# ─── Env + endpoints ────────────────────────────────────────────────────
_API_KEY = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROUTES_MATRIX_ENDPOINT = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
PLACES_NEARBY_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"
GEOCODE_ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
WEATHER_ENDPOINT = "https://weather.googleapis.com/v1/currentConditions:lookup"

# ─── TTLs ───────────────────────────────────────────────────────────────
TTL_ROUTES = 60           # 1 minute — traffic changes fast
TTL_PLACES = 300          # 5 minutes
TTL_WEATHER = 600         # 10 minutes
TTL_GEOCODE = 86_400      # 24 hours

# ─── Cache backend factory ──────────────────────────────────────────────
_redis_client = None
_redis_probed = False
_inmem = TTLCache(maxsize=5000, ttl=TTL_GEOCODE)  # per-entry TTL enforced manually
_inmem_expiries: dict[str, float] = {}
_inmem_warn_at: float = 0.0


def _redis():
    """Lazy-init Redis client.  Returns None if unavailable."""
    global _redis_client, _redis_probed
    if _redis_probed:
        return _redis_client
    _redis_probed = True
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        logger.info("[gmaps_v1] REDIS_URL not set — using in-memory TTLCache")
        return None
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            url, encoding="utf-8", decode_responses=True,
            socket_connect_timeout=1.5, socket_timeout=1.5)
        logger.info(f"[gmaps_v1] Redis client initialised at {url}")
        return _redis_client
    except Exception as e:
        logger.warning(f"[gmaps_v1] Redis init failed: {e} — using in-memory")
        return None


def _cache_key(method: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return f"gmaps:{method}:{hashlib.sha256(raw).hexdigest()[:16]}"


async def _cache_get(key: str) -> Optional[Any]:
    r = _redis()
    if r is not None:
        try:
            v = await r.get(key)
            if v is not None:
                return json.loads(v)
        except Exception as e:
            _inmem_fallback_warn(f"redis get: {e}")
    # in-memory fallback (or Redis miss also checks in-mem in case Redis just came back)
    exp = _inmem_expiries.get(key)
    if exp and exp > time.time():
        return _inmem.get(key)
    return None


async def _cache_set(key: str, value: Any, ttl: int) -> None:
    r = _redis()
    if r is not None:
        try:
            await r.set(key, json.dumps(value), ex=ttl)
            return
        except Exception as e:
            _inmem_fallback_warn(f"redis set: {e}")
    _inmem[key] = value
    _inmem_expiries[key] = time.time() + ttl


def _inmem_fallback_warn(reason: str) -> None:
    """Log once per hour so ops see the degrade without flooding."""
    global _inmem_warn_at
    now = time.time()
    if now - _inmem_warn_at > 3600:
        logger.warning(f"[gmaps_v1] falling back to in-memory cache: {reason}")
        _inmem_warn_at = now


# ─── HTTP client (module-level, reused) ─────────────────────────────────
_http: Optional[httpx.AsyncClient] = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        transport = httpx.AsyncHTTPTransport(retries=2)
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=3.0),
            transport=transport)
    return _http


# ─── Public API ─────────────────────────────────────────────────────────
def api_key_present() -> bool:
    return bool(_API_KEY)


async def compute_route(*, origin: dict, destination: dict,
                              travel_mode: str = "DRIVE") -> dict:
    """Call Routes API v2 computeRoutes.  Returns:
        { encoded_polyline, distance_meters, duration_seconds,
          duration_in_traffic_seconds, traffic_status, raw }
    Raises RuntimeError on API error.
    """
    if not _API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set")
    body = {
        "origin": {"location": {"latLng": {
            "latitude": float(origin["lat"]),
            "longitude": float(origin["lng"])}}},
        "destination": {"location": {"latLng": {
            "latitude": float(destination["lat"]),
            "longitude": float(destination["lng"])}}},
        "travelMode": travel_mode,
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": False,
        "polylineQuality": "OVERVIEW",
    }
    key = _cache_key("routes", body)
    cached = await _cache_get(key)
    if cached is not None:
        return cached
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _API_KEY,
        "X-Goog-FieldMask": (
            "routes.polyline.encodedPolyline,"
            "routes.distanceMeters,"
            "routes.duration,"
            "routes.staticDuration,"
            "routes.travelAdvisory"),
    }
    resp = await _client().post(ROUTES_ENDPOINT, json=body, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"routes_api_error status={resp.status_code} body={resp.text[:400]}")
    data = resp.json() or {}
    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("routes_api_empty_routes")
    r0 = routes[0]
    dur_traffic = _parse_dur(r0.get("duration"))
    dur_static = _parse_dur(r0.get("staticDuration"))
    if dur_static and dur_traffic:
        ratio = dur_traffic / max(dur_static, 1)
        if ratio < 1.10:
            traffic_status = "light"
        elif ratio < 1.30:
            traffic_status = "moderate"
        else:
            traffic_status = "heavy"
    else:
        traffic_status = "unknown"
    out = {
        "encoded_polyline": (r0.get("polyline") or {}).get("encodedPolyline"),
        "distance_meters": int(r0.get("distanceMeters") or 0),
        "duration_seconds": int(dur_traffic or 0),
        "duration_in_traffic_seconds": int(dur_traffic or 0),
        "static_duration_seconds": int(dur_static or 0),
        "traffic_status": traffic_status,
    }
    await _cache_set(key, out, TTL_ROUTES)
    return out


def _parse_dur(s: Any) -> Optional[int]:
    """Google Routes returns durations as `123s` protobuf-style strings."""
    if not s:
        return None
    try:
        return int(str(s).rstrip("s"))
    except (TypeError, ValueError):
        return None


async def geocode(address: str) -> Optional[dict]:
    """Forward geocode.  Returns { lat, lng, formatted_address, place_id } or None."""
    if not _API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set")
    if not address or not address.strip():
        return None
    key = _cache_key("geocode", {"address": address.strip()})
    cached = await _cache_get(key)
    if cached is not None:
        return cached
    params = {"address": address, "key": _API_KEY}
    resp = await _client().get(GEOCODE_ENDPOINT, params=params)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"geocode_api_error status={resp.status_code} body={resp.text[:400]}")
    data = resp.json() or {}
    results = data.get("results") or []
    if not results:
        return None
    r0 = results[0]
    loc = ((r0.get("geometry") or {}).get("location")) or {}
    out = {
        "lat": float(loc.get("lat")),
        "lng": float(loc.get("lng")),
        "formatted_address": r0.get("formatted_address"),
        "place_id": r0.get("place_id"),
    }
    await _cache_set(key, out, TTL_GEOCODE)
    return out


# Places (New) type mapping per activity
ACTIVITY_TO_PLACE_TYPES = {
    "commute":   ["gas_station", "convenience_store", "coffee_shop"],
    "lunch":     ["restaurant", "cafe", "meal_takeaway"],
    "dinner":    ["restaurant", "bar", "meal_takeaway"],
    "nightlife": ["bar", "night_club", "restaurant"],
}


async def nearby_places(*, lat: float, lng: float, radius_m: int = 1500,
                                  place_types: Optional[list[str]] = None,
                                  max_results: int = 10) -> list[dict]:
    """Places API (New) — searchNearby.  Returns a list of place dicts:
        { place_id, name, primary_type, location: {lat, lng}, rating,
          user_rating_count, formatted_address }
    """
    if not _API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set")
    types = place_types or ["restaurant"]
    body = {
        "includedTypes": types,
        "maxResultCount": int(max(1, min(max_results, 20))),
        "locationRestriction": {
            "circle": {
                "center": {"latitude": float(lat), "longitude": float(lng)},
                "radius": float(max(50, min(radius_m, 50_000))),
            }
        },
    }
    key = _cache_key("places_nearby", body)
    cached = await _cache_get(key)
    if cached is not None:
        return cached
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.primaryType,"
            "places.location,places.rating,places.userRatingCount,"
            "places.formattedAddress"),
    }
    resp = await _client().post(PLACES_NEARBY_ENDPOINT, json=body, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"places_api_error status={resp.status_code} body={resp.text[:400]}")
    data = resp.json() or {}
    places = data.get("places") or []
    out: list[dict] = []
    for p in places:
        loc = p.get("location") or {}
        out.append({
            "place_id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text"),
            "primary_type": p.get("primaryType"),
            "location": {
                "lat": loc.get("latitude"),
                "lng": loc.get("longitude"),
            },
            "rating": p.get("rating"),
            "user_rating_count": p.get("userRatingCount"),
            "formatted_address": p.get("formattedAddress"),
        })
    await _cache_set(key, out, TTL_PLACES)
    return out


_weather_disabled_warn_at: float = 0.0


async def current_weather(*, lat: float, lng: float) -> Optional[dict]:
    """Google Weather API — currentConditions:lookup.  Returns:
        { condition, temperature_c, feels_like_c, humidity, is_daytime }
    or None if the Weather API is disabled on the current key.
    """
    global _weather_disabled_warn_at
    if not _API_KEY:
        return None
    key = _cache_key("weather", {"lat": round(float(lat), 3),
                                             "lng": round(float(lng), 3)})
    cached = await _cache_get(key)
    if cached is not None:
        return cached
    params = {
        "key": _API_KEY,
        "location.latitude": str(lat),
        "location.longitude": str(lng),
    }
    try:
        resp = await _client().get(WEATHER_ENDPOINT, params=params)
    except Exception as e:
        logger.warning(f"[gmaps_v1] weather http error: {e}")
        return None
    if resp.status_code in (403, 404):
        # Weather API not enabled on this key — degrade to null (per user answer #4).
        now = time.time()
        if now - _weather_disabled_warn_at > 3600:
            logger.warning(
                f"[gmaps_v1] Weather API disabled/forbidden "
                f"(status={resp.status_code}): {resp.text[:400]}")
            _weather_disabled_warn_at = now
        return None
    if resp.status_code >= 400:
        logger.warning(
            f"[gmaps_v1] weather api error status={resp.status_code} body={resp.text[:200]}")
        return None
    data = resp.json() or {}
    # Weather API preview shape: currentConditions object with weatherCondition.type,
    # temperature.degrees, feelsLikeTemperature.degrees, relativeHumidity, isDaytime.
    cond = ((data.get("weatherCondition") or {}).get("type")
              or (data.get("weatherCondition") or {}).get("description", {}).get("text"))
    temp_c = ((data.get("temperature") or {}).get("degrees"))
    feels = ((data.get("feelsLikeTemperature") or {}).get("degrees"))
    out = {
        "condition": cond,
        "temperature_c": temp_c,
        "feels_like_c": feels,
        "humidity": data.get("relativeHumidity"),
        "is_daytime": data.get("isDaytime"),
    }
    await _cache_set(key, out, TTL_WEATHER)
    return out


# ─── Polyline distance helper (lightweight) ─────────────────────────────
import math
try:
    import polyline as _pl  # v2.0.4 already in requirements
except ImportError:
    _pl = None


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Decode a Google-encoded polyline into a list of (lat, lng) tuples."""
    if not encoded or _pl is None:
        return []
    try:
        return _pl.decode(encoded)
    except Exception:
        return []


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) points, in metres."""
    r = 6_371_000.0
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def min_distance_to_polyline_m(point: tuple[float, float],
                                            polyline_pts: list[tuple[float, float]]) -> float:
    """Cheap approximation — minimum vertex-to-point distance.  Sufficient
    for MVP proximity gating; not a true perpendicular-distance calc."""
    if not polyline_pts:
        return float("inf")
    return min(_haversine_m(point, p) for p in polyline_pts)


def sample_polyline_waypoints(polyline_pts: list[tuple[float, float]],
                                          n: int = 4) -> list[tuple[float, float]]:
    """Return N evenly-spaced waypoints along the polyline for Places lookup.
    Always includes the first and last vertex."""
    if not polyline_pts:
        return []
    if len(polyline_pts) <= n:
        return list(polyline_pts)
    step = (len(polyline_pts) - 1) / (n - 1)
    return [polyline_pts[int(round(i * step))] for i in range(n)]


__all__ = [
    "api_key_present",
    "compute_route", "geocode", "nearby_places", "current_weather",
    "decode_polyline", "min_distance_to_polyline_m",
    "sample_polyline_waypoints",
    "ACTIVITY_TO_PLACE_TYPES",
    "TTL_ROUTES", "TTL_PLACES", "TTL_WEATHER", "TTL_GEOCODE",
]
