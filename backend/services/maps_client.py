"""Phase 9a — Maps client wrapper.

Three resolution modes for `get_maps_client()`:
  A) `GOOGLE_MAPS_API_KEY` env  → simple-key Google client (`?key=...`)
  B) `GOOGLE_APPLICATION_CREDENTIALS` env → service-account OAuth2 client
  C) Neither present              → MockMapsClient

The factory probes the live integration ONCE at boot (cheap weather lookup
in Dubai) when a Google credential is configured.  If the probe fails
because Maps APIs aren't enabled / unauthorized / quota → the runtime
silently falls back to Mock with a clear log line.  Cache keeps both
modes fast.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

try:
    import polyline as _poly
except ImportError:
    _poly = None

logger = logging.getLogger("bigfm.maps")

CATEGORIES = {"restaurant", "cafe", "fast_food", "bar", "club", "theater",
                  "mall", "gas_station", "gym", "salon", "dessert", "grocery"}

ROUTE_CACHE_TTL = 60
PLACES_CACHE_TTL = 600
WEATHER_CACHE_TTL = 600
GEOCODE_CACHE_TTL = 86400


def _now():
    return datetime.now(timezone.utc)


def _hash_args(method: str, args: dict) -> str:
    s = method + "|" + json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _haversine_m(a_lat: float, a_lng: float,
                     b_lat: float, b_lng: float) -> float:
    R = 6371000.0
    phi1 = math.radians(a_lat)
    phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlam = math.radians(b_lng - a_lng)
    h = (math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2)
          * math.sin(dlam / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


# Category-name mapping for Google Places API
_GOOGLE_CATEGORY_TYPES = {
    "restaurant": "restaurant",
    "cafe":       "cafe",
    "fast_food":  "meal_takeaway",
    "bar":        "bar",
    "club":       "night_club",
    "theater":    "movie_theater",
    "mall":       "shopping_mall",
    "gas_station": "gas_station",
    "gym":        "gym",
    "salon":      "beauty_salon",
    "dessert":    "bakery",
    "grocery":    "supermarket",
}
_GOOGLE_TYPE_TO_CATEGORY = {v: k for k, v in _GOOGLE_CATEGORY_TYPES.items()}


class MapsClient(ABC):
    name = "abstract"
    auth_email: Optional[str] = None
    auth_mode: str = "unknown"     # "api_key" | "service_account" | "mock"

    @abstractmethod
    async def compute_route(self, origin, destination,
                                  departure_time=None) -> dict: ...

    @abstractmethod
    async def geocode(self, address: str) -> dict: ...

    @abstractmethod
    async def reverse_geocode(self, lat: float, lng: float) -> dict: ...

    @abstractmethod
    async def nearby_places(self, center, radius_m: int,
                                  categories: list[str]) -> list[dict]: ...

    @abstractmethod
    async def places_along_route(self, polyline_encoded: str,
                                       radius_m: int, categories: list[str],
                                       max_detour_minutes: int) -> list[dict]: ...

    @abstractmethod
    async def current_weather(self, lat: float, lng: float) -> dict: ...

    @abstractmethod
    async def forecast_weather(self, lat: float, lng: float,
                                     hours_ahead: int) -> list[dict]: ...


# ════════════════════════════════════════════════════════════════════════
# Mock seed data — 60 Dubai + 40 DFW businesses.
# ════════════════════════════════════════════════════════════════════════
_DUBAI_SEED = [
    ("The Dubai Mall", "mall", 25.1972, 55.2790, "Downtown Dubai", 4.6, 2),
    ("Mall of the Emirates", "mall", 25.1181, 55.2003, "Sheikh Zayed Rd", 4.5, 2),
    ("City Walk", "mall", 25.2050, 55.2580, "Al Wasl", 4.4, 2),
    ("Pierchic", "restaurant", 25.1300, 55.1850, "Madinat Jumeirah", 4.7, 3),
    ("Karak House", "cafe", 25.2210, 55.2580, "JLT", 4.4, 1),
    ("Operation: Falafel", "fast_food", 25.2050, 55.2700, "City Walk", 4.3, 1),
    ("Lock, Stock & Barrel", "bar", 25.0750, 55.1380, "JBR", 4.2, 2),
    ("White Dubai", "club", 25.2030, 55.2700, "Meydan", 4.1, 3),
    ("Roxy Cinemas", "theater", 25.2020, 55.2580, "City Walk", 4.5, 2),
    ("Reel Cinemas", "theater", 25.1972, 55.2790, "Dubai Mall", 4.4, 2),
    ("ADNOC Service Station", "gas_station", 25.2300, 55.3000, "Al Rebat St", 4.0, 1),
    ("ENOC", "gas_station", 25.1800, 55.2500, "SZR", 4.1, 1),
    ("Fitness First", "gym", 25.2200, 55.2700, "Trade Centre", 4.2, 2),
    ("GymNation", "gym", 25.1100, 55.1900, "Mall of Emirates", 4.5, 1),
    ("1847", "salon", 25.2100, 55.2700, "DIFC", 4.6, 3),
    ("Project Chaiwala", "cafe", 25.2050, 55.2580, "City Walk", 4.5, 1),
    ("Cassette", "cafe", 25.1900, 55.2600, "Al Wasl", 4.4, 2),
    ("BookMunch", "cafe", 25.0710, 55.1390, "JBR", 4.5, 2),
    ("Tom & Serg", "cafe", 25.1700, 55.2400, "Al Quoz", 4.5, 2),
    ("Salt", "fast_food", 25.1740, 55.2390, "Kite Beach", 4.4, 2),
    ("Burger Hood", "fast_food", 25.1950, 55.2700, "Al Wasl", 4.3, 1),
    ("Pickl", "fast_food", 25.2080, 55.2620, "City Walk", 4.6, 2),
    ("Switch", "restaurant", 25.1100, 55.2000, "MoE", 4.3, 2),
    ("Zuma", "restaurant", 25.2150, 55.2800, "DIFC", 4.6, 3),
    ("Bait Maryam", "restaurant", 25.0820, 55.1430, "JLT", 4.5, 2),
    ("Maiz", "restaurant", 25.1950, 55.2740, "Downtown", 4.4, 3),
    ("Time Out Market", "restaurant", 25.0850, 55.1450, "Souk Al Bahar", 4.4, 2),
    ("Trèsind Studio", "restaurant", 25.1970, 55.2750, "Downtown", 4.8, 3),
    ("Carine", "restaurant", 25.2030, 55.2670, "Emirates Golf Club", 4.5, 3),
    ("Stomping Grounds", "cafe", 25.2300, 55.3050, "Jumeirah", 4.5, 2),
    ("Black Tap", "fast_food", 25.1980, 55.2790, "Souk Al Bahar", 4.3, 2),
    ("Carluccio's", "restaurant", 25.1180, 55.2010, "MoE", 4.2, 2),
    ("Dome Cafe", "cafe", 25.2100, 55.2750, "DIFC", 4.0, 2),
    ("Three", "cafe", 25.2080, 55.2730, "DIFC", 4.4, 2),
    ("L'Eto", "dessert", 25.1980, 55.2790, "Dubai Mall", 4.6, 2),
    ("Cinnabon", "dessert", 25.1980, 55.2790, "Dubai Mall", 4.2, 1),
    ("Crumbl Cookies", "dessert", 25.2070, 55.2700, "City Walk", 4.5, 1),
    ("Magnolia Bakery", "dessert", 25.1980, 55.2790, "Dubai Mall", 4.5, 2),
    ("Cheesecake Factory", "restaurant", 25.1980, 55.2790, "Dubai Mall", 4.3, 2),
    ("McDonald's SZR", "fast_food", 25.2200, 55.2800, "SZR", 3.9, 1),
    ("KFC Marina", "fast_food", 25.0800, 55.1400, "Marina Walk", 4.0, 1),
    ("Five Guys", "fast_food", 25.2080, 55.2620, "City Walk", 4.4, 2),
    ("Carrefour Dubai Mall", "grocery", 25.1972, 55.2790, "Dubai Mall", 4.2, 2),
    ("Spinneys MoE", "grocery", 25.1181, 55.2003, "MoE", 4.3, 2),
    ("Waitrose Dubai Marina", "grocery", 25.0800, 55.1400, "Marina", 4.5, 3),
    ("Choithrams JLT", "grocery", 25.0700, 55.1400, "JLT", 4.0, 2),
    ("Lulu Hypermarket", "grocery", 25.2900, 55.3200, "Al Barsha", 4.1, 1),
    ("Mama'esh", "cafe", 25.0700, 55.1400, "JLT", 4.4, 1),
    ("Atmosphere", "bar", 25.1972, 55.2744, "Burj Khalifa", 4.5, 3),
    ("Cé La Vi", "bar", 25.1900, 55.2810, "Address Sky View", 4.3, 3),
    ("Tribeca", "bar", 25.0770, 55.1400, "JLT", 4.2, 2),
    ("Industrial Avenue", "bar", 25.1900, 55.2750, "DIFC", 4.4, 3),
    ("Vault", "bar", 25.2150, 55.2820, "Trade Centre", 4.3, 3),
    ("BLU Dubai", "club", 25.0780, 55.1400, "JBR", 4.0, 3),
    ("Soho Garden", "club", 25.1900, 55.2700, "Meydan", 4.2, 3),
    ("Akira Back", "restaurant", 25.2080, 55.2630, "Wasl", 4.6, 3),
    ("Hakkasan", "restaurant", 25.1970, 55.2750, "Address", 4.6, 3),
    ("Saadeddin", "dessert", 25.0700, 55.1400, "JLT", 4.5, 1),
    ("Dunkin' Sheikh Zayed", "cafe", 25.2300, 55.2950, "SZR", 4.1, 1),
    ("Costa Coffee", "cafe", 25.1980, 55.2790, "Dubai Mall", 4.2, 2),
    ("Talise Spa Salon", "salon", 25.1300, 55.1850, "Madinat", 4.7, 3),
]

_DFW_SEED = [
    ("Whataburger Forest Lane", "fast_food", 32.9100, -96.8000, "Dallas", 4.4, 1),
    ("In-N-Out Frisco", "fast_food", 33.1500, -96.8200, "Frisco", 4.6, 1),
    ("Chick-fil-A Plano", "fast_food", 33.0200, -96.7000, "Plano", 4.7, 1),
    ("Pecan Lodge", "restaurant", 32.7830, -96.7790, "Deep Ellum", 4.6, 2),
    ("Uchi Dallas", "restaurant", 32.8000, -96.8000, "Uptown", 4.7, 3),
    ("Knife Dallas", "restaurant", 32.8200, -96.7900, "Highland Park", 4.5, 3),
    ("Tei-An", "restaurant", 32.7820, -96.8030, "One Arts Plaza", 4.5, 3),
    ("Mariano's", "restaurant", 32.8500, -96.7700, "North Dallas", 4.3, 2),
    ("Mister Charles", "restaurant", 32.8330, -96.8000, "Uptown", 4.4, 3),
    ("Hillstone Park Cities", "restaurant", 32.8400, -96.8000, "Highland Park", 4.5, 3),
    ("Velvet Taco", "fast_food", 32.7820, -96.8050, "Henderson Ave", 4.5, 1),
    ("Torchy's Tacos", "fast_food", 32.7900, -96.8000, "Greenville Ave", 4.4, 1),
    ("Cane Rosso", "restaurant", 32.7820, -96.7780, "Deep Ellum", 4.5, 2),
    ("Bishop Arts Cafe", "cafe", 32.7500, -96.8290, "Bishop Arts", 4.5, 1),
    ("Ascension Coffee", "cafe", 32.8000, -96.8030, "Design District", 4.5, 2),
    ("La La Land Kind Cafe", "cafe", 32.8170, -96.7800, "Uptown", 4.7, 2),
    ("Drip Coffee", "cafe", 32.7780, -96.8030, "Bishop Arts", 4.4, 2),
    ("AMC NorthPark", "theater", 32.8700, -96.7700, "NorthPark", 4.5, 2),
    ("Alamo Drafthouse Cedars", "theater", 32.7700, -96.7700, "South Side", 4.6, 2),
    ("Lookout Cinema", "theater", 33.0900, -96.7900, "Plano", 4.4, 2),
    ("Galleria Dallas", "mall", 32.9300, -96.8200, "North Dallas", 4.3, 2),
    ("NorthPark Center", "mall", 32.8700, -96.7700, "Park Cities", 4.6, 3),
    ("Stonebriar Centre", "mall", 33.1100, -96.8000, "Frisco", 4.4, 2),
    ("Highland Park Village", "mall", 32.8330, -96.8030, "Highland Park", 4.6, 3),
    ("Texaco Mockingbird", "gas_station", 32.8400, -96.7900, "Mockingbird Ln", 3.9, 1),
    ("Shell Greenville", "gas_station", 32.8000, -96.7700, "Greenville Ave", 4.0, 1),
    ("Costco Plano", "grocery", 33.0200, -96.7000, "Plano", 4.5, 2),
    ("Whole Foods Park Lane", "grocery", 32.8700, -96.7700, "Park Lane", 4.5, 3),
    ("Trader Joe's Plano", "grocery", 33.0500, -96.7800, "Plano", 4.6, 2),
    ("Equinox Highland Park", "gym", 32.8330, -96.7990, "Highland Park", 4.5, 3),
    ("Life Time Plano", "gym", 33.0300, -96.7700, "Plano", 4.5, 3),
    ("Cowboy Salon & Spa", "salon", 32.8700, -96.7700, "NorthPark", 4.7, 3),
    ("Drybar Highland Park", "salon", 32.8330, -96.7990, "HPV", 4.5, 2),
    ("Ferris Wheelers", "bar", 32.7900, -96.8050, "Design District", 4.5, 2),
    ("The Standard Pour", "bar", 32.8020, -96.8000, "Uptown", 4.3, 2),
    ("Lakewood Landing", "bar", 32.8200, -96.7400, "Lakewood", 4.4, 2),
    ("It'll Do Club", "club", 32.8200, -96.7700, "East Dallas", 4.3, 2),
    ("Stereo Live Dallas", "club", 32.7500, -96.7500, "South Side", 4.2, 2),
    ("Trinity Groves Bakery", "dessert", 32.7820, -96.8330, "Trinity Groves", 4.5, 2),
    ("Sweet Daze Dessert Bar", "dessert", 32.9700, -96.7300, "Richardson", 4.6, 2),
    ("Emporium Pies", "dessert", 32.7500, -96.8290, "Bishop Arts", 4.7, 2),
]


# ════════════════════════════════════════════════════════════════════════
# Mock implementation (unchanged shape; full deterministic stub).
# ════════════════════════════════════════════════════════════════════════
class MockMapsClient(MapsClient):
    name = "MockMapsClient"
    auth_mode = "mock"

    def __init__(self, db, *, time_provider=None):
        self.db = db
        self._cache_hits = 0
        self._cache_misses = 0
        self._real_calls = 0
        self._now = time_provider or _now

    async def _cache_get(self, key: str) -> Optional[dict]:
        row = await self.db.maps_cache.find_one({"cache_key": key})
        if row and row.get("expires_at"):
            exp = row["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > self._now():
                self._cache_hits += 1
                return row["response_json"]
        self._cache_misses += 1
        return None

    async def _cache_set(self, key: str, method: str, args: dict,
                              value, ttl_seconds: int) -> None:
        await self.db.maps_cache.update_one(
            {"cache_key": key},
            {"$set": {"cache_key": key, "method": method,
                       "args_json": args, "response_json": value,
                       "expires_at": self._now() + timedelta(seconds=ttl_seconds),
                       "created_at": self._now()}},
            upsert=True)

    async def compute_route(self, origin, destination, departure_time=None):
        args = {"origin": origin, "destination": destination,
                  "departure_time": str(departure_time or "")}
        key = _hash_args("compute_route", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        points = []
        for i in range(7):
            t = i / 6.0
            lat = origin["lat"] + (destination["lat"] - origin["lat"]) * t
            lng = origin["lng"] + (destination["lng"] - origin["lng"]) * t
            jitter = 0.001 * math.sin(i * math.pi / 3)
            points.append((lat + jitter, lng + jitter))
        encoded = (_poly.encode(points) if _poly else _fallback_encode(points))
        dist = _haversine_m(origin["lat"], origin["lng"],
                                  destination["lat"], destination["lng"])
        now = self._now()
        hour = now.hour
        if hour in (7, 8, 9, 17, 18, 19):
            traffic = "heavy";    speed = 25
        elif hour in (6, 10, 16, 20):
            traffic = "moderate"; speed = 40
        elif 23 <= hour or hour < 5:
            traffic = "light";    speed = 70
        else:
            traffic = "moderate"; speed = 50
        dur_s = int(dist / (speed * 1000 / 3600))
        traffic_s = int(dur_s * (1.6 if traffic == "heavy"
                                       else 1.2 if traffic == "moderate"
                                       else 1.0))
        lats = [p[0] for p in points]
        lngs = [p[1] for p in points]
        result = {
            "polyline_encoded": encoded,
            "distance_meters": int(dist),
            "duration_seconds": dur_s,
            "duration_in_traffic_seconds": traffic_s,
            "traffic_status": traffic,
            "steps": [
                {"instruction": "Head toward destination",
                  "distance_m": int(dist * 0.4),
                  "duration_s": int(dur_s * 0.4)},
                {"instruction": "Continue on main road",
                  "distance_m": int(dist * 0.4),
                  "duration_s": int(dur_s * 0.4)},
                {"instruction": "Arrive at destination",
                  "distance_m": int(dist * 0.2),
                  "duration_s": int(dur_s * 0.2)},
            ],
            "bounds": {
                "ne": {"lat": max(lats), "lng": max(lngs)},
                "sw": {"lat": min(lats), "lng": min(lngs)},
            },
            "source": "mock",
        }
        await self._cache_set(key, "compute_route", args, result, ROUTE_CACHE_TTL)
        return result

    _GEOCODE_FIXTURES = {
        "dubai mall": (25.1972, 55.2790, "The Dubai Mall, Downtown Dubai"),
        "dubai marina": (25.0800, 55.1400, "Dubai Marina, Dubai"),
        "burj khalifa": (25.1972, 55.2744, "Burj Khalifa, Downtown Dubai"),
        "mall of the emirates": (25.1181, 55.2003, "Mall of the Emirates, Dubai"),
        "downtown dallas": (32.7830, -96.8060, "Downtown Dallas, TX"),
        "northpark center": (32.8700, -96.7700, "NorthPark Center, Dallas, TX"),
        "frisco": (33.1500, -96.8200, "Frisco, TX"),
        "deep ellum": (32.7830, -96.7790, "Deep Ellum, Dallas, TX"),
        "home": (25.2050, 55.2580, "Home (mock)"),
        "work": (25.0800, 55.1400, "Work (mock)"),
    }

    async def geocode(self, address: str) -> dict:
        args = {"address": address.strip().lower()}
        key = _hash_args("geocode", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        text = address.strip().lower()
        for tok, (lat, lng, formatted) in self._GEOCODE_FIXTURES.items():
            if tok in text:
                out = {"lat": lat, "lng": lng,
                        "formatted_address": formatted,
                        "place_id": f"mock_geo_{abs(hash(formatted)) % 10_000_000}"}
                await self._cache_set(key, "geocode", args, out, GEOCODE_CACHE_TTL)
                return out
        h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        lat = 25.10 + (h % 1000) / 10000.0
        lng = 55.15 + ((h >> 10) % 1000) / 10000.0
        out = {"lat": round(lat, 5), "lng": round(lng, 5),
                "formatted_address": f"{address.strip()} (mock geocoded)",
                "place_id": f"mock_geo_{h % 10_000_000}"}
        await self._cache_set(key, "geocode", args, out, GEOCODE_CACHE_TTL)
        return out

    async def reverse_geocode(self, lat: float, lng: float) -> dict:
        args = {"lat": round(lat, 4), "lng": round(lng, 4)}
        key = _hash_args("reverse_geocode", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        if 24.5 < lat < 26.0 and 54.5 < lng < 56.5:
            country, country_code, city = "United Arab Emirates", "AE", "Dubai"
            addr = f"{round(lat,3)},{round(lng,3)} Dubai, UAE"
        elif 32.0 < lat < 34.0 and -97.5 < lng < -96.0:
            country, country_code, city = "United States", "US", "Dallas"
            addr = f"{round(lat,3)},{round(lng,3)} Dallas, TX"
        else:
            country, country_code, city = "Unknown", "??", "Unknown"
            addr = f"{round(lat,3)},{round(lng,3)}"
        out = {"formatted_address": addr,
                "place_id": f"mock_rg_{abs(hash((round(lat,3), round(lng,3)))) % 10_000_000}",
                "city": city, "country": country, "country_code": country_code}
        await self._cache_set(key, "reverse_geocode", args, out, GEOCODE_CACHE_TTL)
        return out

    async def nearby_places(self, center, radius_m, categories):
        cats = [c for c in (categories or []) if c in CATEGORIES] or list(CATEGORIES)
        args = {"center": center, "radius": radius_m,
                  "categories": sorted(cats)}
        key = _hash_args("nearby_places", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        cur = self.db.businesses.find({
            "active": True, "category": {"$in": cats},
            "loc": {"$near": {"$geometry": {
                "type": "Point", "coordinates": [center["lng"], center["lat"]]},
                            "$maxDistance": radius_m}},
        }).limit(30)
        results = []
        async for b in cur:
            dist = _haversine_m(center["lat"], center["lng"],
                                      b["lat"], b["lng"])
            results.append({
                "place_id": b.get("external_place_id") or b["business_id"],
                "business_id": b["business_id"],
                "name": b["name"], "lat": b["lat"], "lng": b["lng"],
                "categories": b.get("categories", [b["category"]]),
                "category": b["category"],
                "rating": b.get("rating"), "price_level": b.get("price_level"),
                "address": b.get("address"),
                "distance_m": int(dist),
            })
        await self._cache_set(key, "nearby_places", args, results,
                                     PLACES_CACHE_TTL)
        return results

    async def places_along_route(self, polyline_encoded, radius_m,
                                       categories, max_detour_minutes):
        cats = [c for c in (categories or []) if c in CATEGORIES] or list(CATEGORIES)
        args = {"poly": polyline_encoded[:80], "radius": radius_m,
                  "categories": sorted(cats), "max_detour": max_detour_minutes}
        key = _hash_args("places_along_route", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        try:
            points = (_poly.decode(polyline_encoded) if _poly
                         else _fallback_decode(polyline_encoded))
        except Exception:
            points = []
        if not points:
            return []
        seen = set()
        results = []
        sample = points[::max(1, len(points) // 6)]
        for (lat, lng) in sample:
            near = await self.nearby_places(
                {"lat": lat, "lng": lng}, radius_m, cats)
            for n in near:
                if n["business_id"] in seen:
                    continue
                seen.add(n["business_id"])
                detour_m = n["distance_m"]
                extra_s = int(detour_m / (30 * 1000 / 3600))
                if extra_s <= max_detour_minutes * 60:
                    n["distance_from_route_m"] = detour_m
                    n["extra_drive_time_seconds"] = extra_s
                    results.append(n)
        results.sort(key=lambda r: r["extra_drive_time_seconds"])
        await self._cache_set(key, "places_along_route", args, results[:40],
                                     PLACES_CACHE_TTL)
        return results[:40]

    async def current_weather(self, lat, lng):
        args = {"lat": round(lat, 2), "lng": round(lng, 2)}
        key = _hash_args("current_weather", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        out = self._synth_weather(lat, lng, self._now())
        await self._cache_set(key, "current_weather", args, out, WEATHER_CACHE_TTL)
        return out

    async def forecast_weather(self, lat, lng, hours_ahead):
        args = {"lat": round(lat, 2), "lng": round(lng, 2), "h": hours_ahead}
        key = _hash_args("forecast_weather", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        base = self._now()
        out = [self._synth_weather(lat, lng, base + timedelta(hours=h))
                  for h in range(0, hours_ahead, max(1, hours_ahead // 8))]
        await self._cache_set(key, "forecast_weather", args, out, WEATHER_CACHE_TTL)
        return out

    @staticmethod
    def _synth_weather(lat, lng, ts):
        m, h, dow = ts.month, ts.hour, ts.weekday()
        if 24.5 < lat < 26.0 and 54.5 < lng < 56.5:
            if m in (12, 1, 2):
                temp = 20 + (h - 6) % 8
                cond = "cloudy" if dow in (1, 5) else "clear"
                precip = 1.2 if dow == 3 else 0.0
            elif m in (6, 7, 8, 9):
                temp = 36 + (h - 12) % 8
                cond = "hot" if h >= 11 else "haze"
                precip = 0.0
            else:
                temp = 28 + (h - 8) % 8
                cond = "haze" if dow in (1, 4) else "clear"
                precip = 0.0
        elif 32.0 < lat < 34.0 and -97.5 < lng < -96.0:
            if m in (6, 7, 8):
                temp = 32 + (h - 12) % 6
                cond = "clear" if dow in (0, 6) else "cloudy"
                precip = 0.0 if dow in (0, 6) else 0.4
            elif m in (12, 1, 2):
                temp = 8 + (h - 9) % 6
                cond = "cold"
                precip = 0.0
            elif m in (3, 4, 5):
                temp = 22 + (h - 12) % 8
                cond = "thunderstorm" if dow == 2 else "cloudy"
                precip = 5.0 if dow == 2 else 0.0
            else:
                temp = 20 + (h - 10) % 6
                cond = "clear"
                precip = 0.0
        else:
            temp = 20; cond = "clear"; precip = 0.0
        return {
            "temp_c": float(temp), "condition": cond,
            "precipitation_mm": float(precip), "wind_kph": 12.0,
            "humidity_pct": 55, "ts": ts.isoformat(),
        }


def _fallback_encode(points):
    return "JSON:" + json.dumps(points, separators=(",", ":"))


def _fallback_decode(s):
    if s.startswith("JSON:"):
        return [tuple(p) for p in json.loads(s[5:])]
    return []


# ════════════════════════════════════════════════════════════════════════
# Google Maps client (real, with mock fallback per-method on errors)
# ════════════════════════════════════════════════════════════════════════
_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
_PLACES_SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
_WEATHER_CURRENT_URL = "https://weather.googleapis.com/v1/currentConditions:lookup"
_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_OAUTH_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class GoogleMapsClient(MapsClient):
    name = "GoogleMapsClient"

    def __init__(self, db, *, api_key: Optional[str] = None,
                      sa_credentials=None, sa_email: Optional[str] = None):
        self.db = db
        self.api_key = api_key
        self._creds = sa_credentials
        self.auth_email = sa_email
        self.auth_mode = "api_key" if api_key else (
            "service_account" if sa_credentials else "unknown")
        self._mock = MockMapsClient(db)
        self._cache_hits = 0
        self._cache_misses = 0
        self._real_calls = 0
        self._token = None
        self._token_exp = 0
        self.api_health: dict[str, str] = {
            "routes": "unknown", "places": "unknown",
            "weather": "unknown", "geocoding": "unknown",
        }
        logger.info(f"GoogleMapsClient init mode={self.auth_mode} "
                       f"email={self.auth_email or '(api_key)'}")

    def _refresh_token(self) -> Optional[str]:
        if self._creds is None:
            return None
        if self._token and self._token_exp - time.time() > 60:
            return self._token
        from google.auth.transport.requests import Request as GAuthRequest
        try:
            self._creds.refresh(GAuthRequest())
            self._token = self._creds.token
            # Best-effort expiry tracking
            self._token_exp = (self._creds.expiry.timestamp()
                                    if getattr(self._creds, "expiry", None)
                                    else time.time() + 3300)
            return self._token
        except Exception as e:
            logger.warning(f"google-auth token refresh failed: {e}")
            return None

    def _auth_headers(self, field_mask: Optional[str] = None) -> dict:
        h = {"Content-Type": "application/json"}
        if self._creds:
            tok = self._refresh_token()
            if tok:
                h["Authorization"] = f"Bearer {tok}"
            project = getattr(self._creds, "project_id", None)
            if project:
                h["X-Goog-User-Project"] = project
        if field_mask:
            h["X-Goog-FieldMask"] = field_mask
        return h

    def _params_with_key(self, params: dict) -> dict:
        if self.api_key:
            params = dict(params)
            params["key"] = self.api_key
        return params

    async def _cache_get(self, key: str) -> Optional[dict]:
        return await self._mock._cache_get(key)

    async def _cache_set(self, key: str, method: str, args: dict,
                              value, ttl_seconds: int) -> None:
        await self._mock._cache_set(key, method, args, value, ttl_seconds)

    # ─── compute_route ────────────────────────────────────────────────
    async def compute_route(self, origin, destination, departure_time=None):
        args = {"origin": origin, "destination": destination,
                  "departure_time": str(departure_time or "")}
        key = _hash_args("compute_route", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        body = {
            "origin": {"location": {"latLng": {
                "latitude": origin["lat"], "longitude": origin["lng"]}}},
            "destination": {"location": {"latLng": {
                "latitude": destination["lat"], "longitude": destination["lng"]}}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
        }
        field_mask = ("routes.distanceMeters,routes.duration,"
                          "routes.staticDuration,"
                          "routes.polyline.encodedPolyline,"
                          "routes.legs.steps.navigationInstruction,"
                          "routes.legs.steps.distanceMeters,"
                          "routes.legs.steps.staticDuration,"
                          "routes.viewport")
        headers = self._auth_headers(field_mask=field_mask)
        url = _ROUTES_URL
        if self.api_key:
            url = url + f"?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, headers=headers, json=body)
            if r.status_code == 200:
                self.api_health["routes"] = "ok"
                data = r.json()
                out = self._normalize_route(data, origin, destination)
                await self._cache_set(key, "compute_route", args, out,
                                              ROUTE_CACHE_TTL)
                return out
            self._record_api_failure("routes", r)
        except Exception as e:
            logger.warning(f"compute_route http error: {e}")
            self.api_health["routes"] = "error"
        # Fallback to mock for this call
        return await self._mock.compute_route(origin, destination, departure_time)

    def _normalize_route(self, gdata, origin, destination):
        routes = gdata.get("routes") or []
        if not routes:
            return {}
        r0 = routes[0]
        dur_s = int(self._parse_duration(r0.get("duration", "0s")))
        static_s = int(self._parse_duration(r0.get("staticDuration", "0s")))
        if static_s == 0:
            static_s = dur_s
        # Traffic status heuristic: ratio of duration_in_traffic / static
        ratio = (dur_s / static_s) if static_s > 0 else 1.0
        traffic = ("light" if ratio < 1.1
                      else "moderate" if ratio < 1.35
                      else "heavy")
        steps_out = []
        for leg in r0.get("legs") or []:
            for s in leg.get("steps") or []:
                steps_out.append({
                    "instruction": (s.get("navigationInstruction") or {})
                                       .get("instructions") or "",
                    "distance_m": int(s.get("distanceMeters") or 0),
                    "duration_s": int(self._parse_duration(
                        s.get("staticDuration") or "0s")),
                })
        vp = r0.get("viewport") or {}
        ne = (vp.get("high") or {})
        sw = (vp.get("low") or {})
        return {
            "polyline_encoded": (r0.get("polyline") or {})
                                       .get("encodedPolyline", ""),
            "distance_meters": int(r0.get("distanceMeters") or 0),
            "duration_seconds": static_s,
            "duration_in_traffic_seconds": dur_s,
            "traffic_status": traffic,
            "steps": steps_out[:20],
            "bounds": {
                "ne": {"lat": ne.get("latitude"), "lng": ne.get("longitude")},
                "sw": {"lat": sw.get("latitude"), "lng": sw.get("longitude")},
            },
            "source": "google",
        }

    @staticmethod
    def _parse_duration(d: str) -> float:
        # Routes API returns durations like "1234s"
        if not d:
            return 0.0
        d = str(d).strip()
        if d.endswith("s"):
            try:
                return float(d[:-1])
            except ValueError:
                return 0.0
        try:
            return float(d)
        except ValueError:
            return 0.0

    def _record_api_failure(self, api_key: str, response) -> None:
        try:
            err = response.json().get("error", {})
            msg = err.get("message", "")
            status = err.get("status", "")
        except Exception:
            msg = response.text[:300]
            status = ""
        code = response.status_code
        if code in (401, 403):
            if "API has not been used" in msg or "has not been enabled" in msg:
                self.api_health[api_key] = "missing"
            else:
                self.api_health[api_key] = "forbidden"
        elif code == 429:
            self.api_health[api_key] = "quota"
        else:
            self.api_health[api_key] = f"error_{code}"
        logger.warning(f"google_maps.{api_key}.{code} {status} :: {msg[:160]}")

    # ─── geocode / reverse_geocode (delegate to mock for now if fails) ─
    async def geocode(self, address: str) -> dict:
        args = {"address": address.strip().lower()}
        key = _hash_args("geocode", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        # Geocoding API (legacy; usually requires API key, NOT service-account)
        if self.api_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        _GEOCODE_URL,
                        params=self._params_with_key({"address": address}))
                if r.status_code == 200:
                    data = r.json()
                    if data.get("results"):
                        item = data["results"][0]
                        out = {
                            "lat": item["geometry"]["location"]["lat"],
                            "lng": item["geometry"]["location"]["lng"],
                            "formatted_address": item.get("formatted_address"),
                            "place_id": item.get("place_id"),
                        }
                        self.api_health["geocoding"] = "ok"
                        await self._cache_set(key, "geocode", args, out,
                                                      GEOCODE_CACHE_TTL)
                        return out
                self._record_api_failure("geocoding", r)
            except Exception as e:
                logger.warning(f"geocode http error: {e}")
                self.api_health["geocoding"] = "error"
        else:
            # Service-account auth: Geocoding API doesn't accept SA tokens
            # uniformly. Try Places searchText instead.
            try:
                out = await self._places_search_text(address)
                if out:
                    await self._cache_set(key, "geocode", args, out,
                                                  GEOCODE_CACHE_TTL)
                    return out
            except Exception:
                pass
            self.api_health["geocoding"] = "missing_sa_unsupported"
        return await self._mock.geocode(address)

    async def _places_search_text(self, address: str) -> Optional[dict]:
        body = {"textQuery": address}
        headers = self._auth_headers(
            field_mask="places.location,places.formattedAddress,places.id")
        url = _PLACES_SEARCH_TEXT_URL
        if self.api_key:
            url = url + f"?key={self.api_key}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=headers, json=body)
        if r.status_code == 200:
            data = r.json()
            if data.get("places"):
                p = data["places"][0]
                loc = p.get("location") or {}
                return {
                    "lat": loc.get("latitude"),
                    "lng": loc.get("longitude"),
                    "formatted_address": p.get("formattedAddress"),
                    "place_id": p.get("id"),
                }
            return None
        self._record_api_failure("places", r)
        return None

    async def reverse_geocode(self, lat, lng):
        return await self._mock.reverse_geocode(lat, lng)

    # ─── nearby_places ────────────────────────────────────────────────
    async def nearby_places(self, center, radius_m, categories):
        cats = [c for c in (categories or []) if c in CATEGORIES] or list(CATEGORIES)
        args = {"center": center, "radius": radius_m,
                  "categories": sorted(cats)}
        key = _hash_args("nearby_places", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        g_types = [_GOOGLE_CATEGORY_TYPES[c] for c in cats
                       if c in _GOOGLE_CATEGORY_TYPES]
        body = {
            "includedTypes": g_types,
            "maxResultCount": 20,
            "locationRestriction": {"circle": {
                "center": {"latitude": center["lat"],
                              "longitude": center["lng"]},
                "radius": float(min(radius_m, 50000)),
            }},
        }
        headers = self._auth_headers(field_mask=(
            "places.id,places.displayName,places.location,"
            "places.formattedAddress,places.rating,places.priceLevel,"
            "places.types"))
        url = _PLACES_NEARBY_URL
        if self.api_key:
            url = url + f"?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, headers=headers, json=body)
            if r.status_code == 200:
                data = r.json()
                self.api_health["places"] = "ok"
                results = []
                for p in (data.get("places") or []):
                    loc = p.get("location") or {}
                    types = p.get("types") or []
                    canonical = next(
                        (_GOOGLE_TYPE_TO_CATEGORY[t] for t in types
                          if t in _GOOGLE_TYPE_TO_CATEGORY), cats[0])
                    results.append({
                        "place_id": p.get("id"),
                        "business_id": p.get("id"),
                        "name": (p.get("displayName") or {}).get("text", ""),
                        "lat": loc.get("latitude"),
                        "lng": loc.get("longitude"),
                        "categories": [canonical] + types,
                        "category": canonical,
                        "rating": p.get("rating"),
                        "price_level": _price_level_to_int(p.get("priceLevel")),
                        "address": p.get("formattedAddress"),
                        "distance_m": int(_haversine_m(
                            center["lat"], center["lng"],
                            loc.get("latitude") or 0,
                            loc.get("longitude") or 0)),
                    })
                await self._cache_set(key, "nearby_places", args, results,
                                              PLACES_CACHE_TTL)
                return results
            self._record_api_failure("places", r)
        except Exception as e:
            logger.warning(f"places http error: {e}")
            self.api_health["places"] = "error"
        return await self._mock.nearby_places(center, radius_m, categories)

    async def places_along_route(self, polyline_encoded, radius_m,
                                       categories, max_detour_minutes):
        return await self._mock.places_along_route(
            polyline_encoded, radius_m, categories, max_detour_minutes)

    # ─── weather ──────────────────────────────────────────────────────
    async def current_weather(self, lat, lng):
        args = {"lat": round(lat, 2), "lng": round(lng, 2)}
        key = _hash_args("current_weather", args)
        cached = await self._cache_get(key)
        if cached:
            return cached
        self._real_calls += 1
        headers = self._auth_headers()
        params = self._params_with_key({
            "location.latitude": lat, "location.longitude": lng})
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(_WEATHER_CURRENT_URL,
                                            headers=headers, params=params)
            if r.status_code == 200:
                data = r.json()
                self.api_health["weather"] = "ok"
                out = self._normalize_weather(data)
                await self._cache_set(key, "current_weather", args, out,
                                              WEATHER_CACHE_TTL)
                return out
            self._record_api_failure("weather", r)
        except Exception as e:
            logger.warning(f"weather http error: {e}")
            self.api_health["weather"] = "error"
        return await self._mock.current_weather(lat, lng)

    @staticmethod
    def _normalize_weather(data: dict) -> dict:
        temp = ((data.get("temperature") or {}).get("degrees")
                  or data.get("temperatureCelsius") or 0)
        cond_raw = ((data.get("weatherCondition") or {}).get("type")
                       or data.get("condition") or "clear").lower()
        if "rain" in cond_raw or "shower" in cond_raw:
            cond = "rain"
        elif "thunder" in cond_raw:
            cond = "thunderstorm"
        elif "snow" in cond_raw:
            cond = "snow"
        elif "cloud" in cond_raw or "overcast" in cond_raw:
            cond = "cloudy"
        elif "haze" in cond_raw or "mist" in cond_raw or "fog" in cond_raw:
            cond = "haze"
        elif "hot" in cond_raw:
            cond = "hot"
        else:
            cond = "clear"
        precip = ((data.get("precipitation") or {}).get("amount") or {}
                     ).get("quantity") or 0
        wind = ((data.get("wind") or {}).get("speed") or {}).get("value") or 0
        humid = (data.get("relativeHumidity") or 0)
        return {
            "temp_c": float(temp), "condition": cond,
            "precipitation_mm": float(precip),
            "wind_kph": float(wind), "humidity_pct": int(humid),
            "ts": _now().isoformat(),
        }

    async def forecast_weather(self, lat, lng, hours_ahead):
        return await self._mock.forecast_weather(lat, lng, hours_ahead)

    # ─── boot probe ───────────────────────────────────────────────────
    async def probe_apis(self) -> dict:
        """One small call against each API → updates self.api_health.

        Invalidates cache keys for the probe queries so a stale Mock
        response from a previous fallback doesn't mask the true health
        state of the live APIs.
        """
        # Bust cache for our four canonical probe inputs so we always hit
        # the wire on boot.  Methods normalize the args identically.
        try:
            await self.db.maps_cache.delete_many({"method": {"$in": [
                "compute_route", "geocode", "nearby_places",
                "current_weather"]}})
        except Exception:
            pass
        try:
            await self.current_weather(25.276987, 55.296249)
        except Exception:
            pass
        try:
            await self.nearby_places({"lat": 25.197, "lng": 55.279},
                                              500, ["cafe"])
        except Exception:
            pass
        try:
            await self.compute_route({"lat": 25.197, "lng": 55.279},
                                              {"lat": 25.080, "lng": 55.140})
        except Exception:
            pass
        try:
            await self.geocode("Burj Khalifa")
        except Exception:
            pass
        return dict(self.api_health)


def _price_level_to_int(p):
    """Google's Places API returns priceLevel as enum string like
    PRICE_LEVEL_INEXPENSIVE."""
    if not p:
        return None
    if isinstance(p, int):
        return p
    pmap = {"PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1,
              "PRICE_LEVEL_MODERATE": 2, "PRICE_LEVEL_EXPENSIVE": 3,
              "PRICE_LEVEL_VERY_EXPENSIVE": 4}
    return pmap.get(str(p), None)


# ════════════════════════════════════════════════════════════════════════
# Factory + boot
# ════════════════════════════════════════════════════════════════════════
_singleton: Optional[MapsClient] = None


def _load_service_account_creds():
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not sa_path or not os.path.exists(sa_path):
        return None, None
    try:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            sa_path, scopes=[_OAUTH_SCOPE])
        # Surface the client_email (safe-to-log) but NEVER the private_key
        sa_email = creds.service_account_email
        return creds, sa_email
    except Exception as e:
        logger.warning(f"service-account load failed: {e}")
        return None, None


def get_maps_client(db) -> MapsClient:
    global _singleton
    if _singleton is None:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
        sa_creds, sa_email = _load_service_account_creds()
        if api_key:
            _singleton = GoogleMapsClient(db, api_key=api_key)
            logger.info("MapsClient = GoogleMapsClient[api_key]")
        elif sa_creds is not None:
            _singleton = GoogleMapsClient(
                db, sa_credentials=sa_creds, sa_email=sa_email)
            logger.info(f"MapsClient = GoogleMapsClient[service_account:"
                           f"{sa_email}]")
        else:
            _singleton = MockMapsClient(db)
            logger.info("MapsClient = MockMapsClient")
    return _singleton


async def probe_and_decide_client(db, app=None) -> dict:
    """Phase 9a — call once at boot.  If the live client can't probe ANY
    API successfully, fall back to Mock for runtime.  Either way, return
    a status dict admins can read via /api/system/integrations."""
    global _singleton
    cli = get_maps_client(db)
    if isinstance(cli, MockMapsClient):
        if app is not None:
            app.state.maps_mode = "mock"
        return {"client": cli.name, "mode": "mock", "api_health": {}}
    # Live client → probe
    health = await cli.probe_apis()
    healthy = sum(1 for v in health.values() if v == "ok")
    if healthy == 0:
        logger.warning(f"All Maps Platform APIs failed probe: {health}. "
                          f"Falling back to MockMapsClient at runtime.")
        # Replace the singleton with Mock so production traffic stays fast
        _singleton = MockMapsClient(db)
        if app is not None:
            app.state.maps_mode = "mock_fallback"
        return {"client": cli.name, "mode": "mock_fallback",
                  "auth_mode": cli.auth_mode,
                  "auth_email": cli.auth_email,
                  "api_health": health}
    if app is not None:
        app.state.maps_mode = "live"
    return {"client": cli.name, "mode": "live",
              "auth_mode": cli.auth_mode,
              "auth_email": cli.auth_email,
              "api_health": health,
              "healthy_apis": healthy}


async def ensure_maps_indexes(db) -> None:
    await db.maps_cache.create_index([("cache_key", 1)], unique=True)
    await db.maps_cache.create_index([("expires_at", 1)],
                                              expireAfterSeconds=0)
    await db.businesses.create_index([("loc", "2dsphere")])
    await db.businesses.create_index([("business_id", 1)], unique=True)
    await db.businesses.create_index([("category", 1), ("city", 1)])
    await db.businesses.create_index([("country_code", 1), ("city", 1)])
    await db.commute_sessions.create_index(
        [("user_id", 1), ("status", 1), ("started_at", -1)])
    await db.commute_sessions.create_index([("commute_id", 1)], unique=True)
    await db.saved_locations.create_index([("user_id", 1)])
    await db.saved_locations.create_index([("loc_id", 1)], unique=True)


async def seed_mock_places(db, *, force: bool = False) -> dict:
    if not force:
        n = await db.businesses.count_documents({"source": "mock_seed"})
        if n >= 80:
            return {"already_seeded": n}
    inserted = 0
    for batch_data, city, country, cc in (
        (_DUBAI_SEED, "Dubai", "United Arab Emirates", "AE"),
        (_DFW_SEED,   "Dallas", "United States",       "US"),
    ):
        for name, cat, lat, lng, addr, rating, price in batch_data:
            bid = f"biz_{hashlib.sha256(name.encode()).hexdigest()[:14]}"
            await db.businesses.update_one(
                {"business_id": bid},
                {"$setOnInsert": {
                    "_id": bid, "business_id": bid,
                    "external_place_id": None,
                    "name": name, "category": cat,
                    "categories": [cat],
                    "address": addr, "lat": lat, "lng": lng,
                    "loc": {"type": "Point", "coordinates": [lng, lat]},
                    "city": city, "country": country,
                    "country_code": cc,
                    "phone": None, "website": None, "hours_json": None,
                    "rating": rating, "price_level": price,
                    "owner_user_id": None, "verified": True,
                    "source": "mock_seed",
                    "created_at": _now(), "updated_at": _now(),
                    "active": True,
                }},
                upsert=True)
            inserted += 1
    return {"inserted_or_skipped": inserted}
