"""
Phase 15d — geo resolver. Maps an inbound request (anon or logged-in)
to a market label that the rest of the platform can branch on.

Resolution priority (highest wins):
    1. logged-in user's `preferred_market` override
    2. provider lookup (ipapi.co live default / MaxMind / mock), cached 24h
       in `geo_cache`
    3. MOCK default → Dubai (legacy fallback; logs a warning)

The provider is configured via env `BIGFM_GEO_PROVIDER` ∈
{`ipapi.co`, `maxmind`, `mock`}. Missing/empty → `ipapi.co` (live, free tier,
no key required, ~1000 req/day per egress IP, hard-limited via 24h cache).
"""
from __future__ import annotations
import logging
import math
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import httpx

logger = logging.getLogger("bigfm.geo")
PROVIDER = (os.environ.get("BIGFM_GEO_PROVIDER") or "ipapi.co").lower()
CACHE_TTL_SECONDS = 24 * 60 * 60

# Bug B addendum — when ipapi.co is rate-limited (free-tier 429), we fall
# through to a second free provider (ipinfo.io, HTTPS, no key required for
# light usage) and then an optional tertiary (ip-api.com, only enabled if
# IP_GEO_API_KEY env is present — it's HTTPS only on the paid tier).
_IPINFO_TOKEN     = (os.environ.get("IPINFO_TOKEN") or "").strip()
_IP_API_KEY       = (os.environ.get("IP_GEO_API_KEY") or "").strip()

# Bug B dev shim — when BIGFM_DEBUG_GEO=1, a handful of well-known test IPs
# resolve to canned cities WITHOUT any outbound API call.  Lets the e1
# tester run deterministic curl proofs even when ipapi.co is throttled.
# Default OFF in production.  Documented in test_credentials.md.
_DEBUG_GEO_ENABLED = (os.environ.get("BIGFM_DEBUG_GEO") or "").strip() in ("1", "true", "yes")
_DEBUG_IP_FIXTURES = {
    # UAE — Etisalat range
    "5.32.0.1":      {"country": "AE", "city": "Dubai",     "region": "DU", "lat": 25.0734, "lng": 55.2979},
    # India — Mumbai
    "115.240.90.1":  {"country": "IN", "city": "Mumbai",    "region": "MH", "lat": 19.0760, "lng": 72.8777},
    # UK — London
    "212.58.224.1":  {"country": "GB", "city": "London",    "region": "ENG","lat": 51.5074, "lng": -0.1278},
    # US — Dallas (DFW)
    "4.37.34.242":   {"country": "US", "city": "Dallas",    "region": "TX", "lat": 32.7767, "lng": -96.7970},
    # US — New York
    "199.83.131.1":  {"country": "US", "city": "New York",  "region": "NY", "lat": 40.7128, "lng": -74.0060},
    # US — Los Angeles
    "72.229.28.185": {"country": "US", "city": "Los Angeles","region": "CA","lat": 34.0522, "lng": -118.2437},
    # Google DNS — Mountain View (sanity)
    "8.8.8.8":       {"country": "US", "city": "Mountain View","region":"CA","lat":37.4231, "lng": -122.0833},
}

# Phase 15d.1 — country-level default. US is routed by city/lat-lng below; if
# we can't resolve a US city we fall back to the closest-by-lat-lng market.
_COUNTRY_DEFAULT = {
    "AE": "dubai",
    "GB": "london",
    "IN": "mumbai",
    "US": "new_york",   # safe US fallback only if lat/lng absent
}
# Explicit US-city → market table for quick wins on common metros.  Anything
# not in this list falls through to closest-centroid haversine resolution.
_US_CITY_MARKET = {
    "new york":         "new_york",
    "brooklyn":         "new_york",
    "queens":            "new_york",
    "manhattan":        "new_york",
    "bronx":             "new_york",
    "newark":            "new_york",
    "jersey city":      "new_york",
    "los angeles":      "los_angeles",
    "long beach":       "los_angeles",
    "santa monica":     "los_angeles",
    "anaheim":           "los_angeles",
    "san diego":        "los_angeles",
    "san francisco":    "los_angeles",
    # Phase 15d.1 — DFW metroplex
    "dallas":            "dfw",
    "fort worth":       "dfw",
    "arlington":        "dfw",
    "plano":             "dfw",
    "irving":            "dfw",
    "frisco":            "dfw",
    "garland":           "dfw",
    "denton":            "dfw",
    "richardson":        "dfw",
    "mckinney":          "dfw",
    "grand prairie":    "dfw",
    "carrollton":       "dfw",
    "lewisville":       "dfw",
    "mesquite":         "dfw",
}
_COUNTRY_NAMES = {
    "AE": "United Arab Emirates", "GB": "United Kingdom",
    "IN": "India",                 "US": "United States",
}
_TIMEZONES = {
    "dubai":         "Asia/Dubai",
    "new_york":      "America/New_York",
    "london":        "Europe/London",
    "mumbai":        "Asia/Kolkata",
    "los_angeles":   "America/Los_Angeles",
    "dfw":           "America/Chicago",
}


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two coordinates, in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _closest_market(lat: float, lng: float) -> Optional[str]:
    """Walk the lexicon centroids and pick the nearest one. Returns None when
       no centroid is configured (shouldn't happen for the 6 shipping markets)."""
    try:
        from services.market_lexicon import MARKET_LEXICON
    except Exception:
        return None
    if not (lat or lng):
        return None
    best, best_d = None, float("inf")
    for key, entry in MARKET_LEXICON.items():
        c = entry.get("centroid") if isinstance(entry, dict) else None
        if not c or len(c) != 2:
            continue
        d = _haversine_km(lat, lng, c[0], c[1])
        if d < best_d:
            best, best_d = key, d
    return best


def _city_to_market(country: str, city: str | None,
                                lat: float = 0.0, lng: float = 0.0) -> str:
    """Resolve a (country, city, lat/lng) tuple to a market_id."""
    if country == "US" and city:
        m = _US_CITY_MARKET.get(city.lower())
        if m:
            return m
    # Try closest-centroid by lat/lng for any country.
    if lat or lng:
        nearest = _closest_market(lat, lng)
        if nearest:
            return nearest
    # Phase 42-E1.4 — when neither country nor lat/lng resolves to a
    # known market, fall back to `dfw` (Dallas) — the app-wide
    # last-resort default already used by News Local-First and the
    # `Lunch Rush · Dallas` market header.  Previously this leaked
    # `dubai`, which appeared as the wrong city on Maps for IP-routed
    # users in any unsupported country.
    return _COUNTRY_DEFAULT.get(country, "dfw")


def _mock_result(reason: str = "mock") -> dict:
    """Hard-fallback when IP geo, TZ, and provider all fail. Returns a
    neutral 'BigFM Global' shape so we never leak a specific city
    (previously defaulted to Dubai which surfaced as a localised
    BigFM Dubai header even for US/UK listeners — Bug B fix)."""
    return {
        "country":         "",
        "country_name":    "",
        "city":             "Global",
        "region":           "",
        "market":           "global",
        "latitude":         0.0,
        "longitude":        0.0,
        "timezone":         "UTC",
        "source":           reason,
    }


async def _fetch_ipapi(ip: str) -> dict | None:
    """ipapi.co free tier — no key needed for low volume, hard-limited.
       Returns the full resolved geo dict OR None on failure / rate-limit."""
    if not ip or ip in ("127.0.0.1", "0.0.0.0", "::1"):
        return None
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                f"https://ipapi.co/{ip}/json/",
                headers={"User-Agent": "BigFM/1.0 (bigfm.app)"},
            )
        if r.status_code == 429:
            logger.warning("ipapi.co rate-limited (429) for ip=%s; falling through", ip)
            return None
        if r.status_code != 200:
            return None
        d = r.json() or {}
        # ipapi returns {error:true, reason:'...'} on certain quota/abuse blocks.
        if d.get("error"):
            logger.warning("ipapi.co error for ip=%s: %s", ip, d.get("reason"))
            return None
        country = (d.get("country_code") or "").upper()
        city    = d.get("city") or ""
        region  = d.get("region_code") or d.get("region") or ""
        lat     = float(d.get("latitude") or 0.0)
        lng     = float(d.get("longitude") or 0.0)
        if not country:
            return None
        market = _city_to_market(country, city, lat, lng)
        return {
            "country":      country,
            "country_name": _COUNTRY_NAMES.get(country, d.get("country_name") or country),
            "city":         city or "—",
            "region":       region,
            "market":       market,
            "latitude":     lat,
            "longitude":    lng,
            "timezone":     d.get("timezone") or _TIMEZONES.get(market, "UTC"),
            "source":       "ip",
        }
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("ipapi.co fetch failed for ip=%s: %s", ip, e)
        return None


async def _fetch_ipinfo(ip: str) -> dict | None:
    """ipinfo.io HTTPS free tier — small daily quota, no key required for
       light usage.  Returns a normalized dict on success, None otherwise.

       Bug B fallback — kicks in when ipapi.co 429s.
    """
    if not ip or ip in ("127.0.0.1", "0.0.0.0", "::1"):
        return None
    try:
        params = {"token": _IPINFO_TOKEN} if _IPINFO_TOKEN else None
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                f"https://ipinfo.io/{ip}/json",
                headers={"User-Agent": "BigFM/1.0 (bigfm.app)",
                                "Accept":      "application/json"},
                params=params,
            )
        if r.status_code == 429:
            logger.warning("ipinfo.io rate-limited (429) for ip=%s; falling through", ip)
            return None
        if r.status_code != 200:
            return None
        d = r.json() or {}
        country = (d.get("country") or "").upper()
        city    = d.get("city") or ""
        region  = d.get("region") or ""
        # ipinfo returns "lat,lng" packed into a `loc` string.
        loc = d.get("loc") or ""
        lat = lng = 0.0
        if loc and "," in loc:
            try:
                lat_s, lng_s = loc.split(",", 1)
                lat, lng = float(lat_s), float(lng_s)
            except (ValueError, TypeError):
                lat = lng = 0.0
        if not country:
            return None
        market = _city_to_market(country, city, lat, lng)
        return {
            "country":      country,
            "country_name": _COUNTRY_NAMES.get(country, country),
            "city":         city or "—",
            "region":       region,
            "market":       market,
            "latitude":     lat,
            "longitude":    lng,
            "timezone":     d.get("timezone") or _TIMEZONES.get(market, "UTC"),
            "source":       "ip",
        }
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("ipinfo.io fetch failed for ip=%s: %s", ip, e)
        return None


async def _fetch_ip_api(ip: str) -> dict | None:
    """ip-api.com paid HTTPS tier — only enabled when IP_GEO_API_KEY is set.
       Free tier is HTTP-only and we don't speak plain HTTP from the pod
       (TLS-only egress in our infra).  Returns None when key is absent.
    """
    if not _IP_API_KEY:
        return None
    if not ip or ip in ("127.0.0.1", "0.0.0.0", "::1"):
        return None
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                f"https://pro.ip-api.com/json/{ip}",
                params={"key": _IP_API_KEY, "fields": "status,country,countryCode,region,regionName,city,lat,lon,timezone"},
                headers={"User-Agent": "BigFM/1.0 (bigfm.app)"},
            )
        if r.status_code != 200:
            return None
        d = r.json() or {}
        if d.get("status") != "success":
            return None
        country = (d.get("countryCode") or "").upper()
        city    = d.get("city") or ""
        region  = d.get("region") or d.get("regionName") or ""
        lat     = float(d.get("lat") or 0.0)
        lng     = float(d.get("lon") or 0.0)
        if not country:
            return None
        market = _city_to_market(country, city, lat, lng)
        return {
            "country":      country,
            "country_name": _COUNTRY_NAMES.get(country, d.get("country") or country),
            "city":         city or "—",
            "region":       region,
            "market":       market,
            "latitude":     lat,
            "longitude":    lng,
            "timezone":     d.get("timezone") or _TIMEZONES.get(market, "UTC"),
            "source":       "ip",
        }
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("ip-api.com fetch failed for ip=%s: %s", ip, e)
        return None


def _debug_fixture(ip: str) -> dict | None:
    """BIGFM_DEBUG_GEO=1 dev shim — return a deterministic city for known
       test IPs so e1_tester runs aren't subject to ipapi.co quota.
       Returns None when the env flag is off OR the IP isn't fixtured.
    """
    if not _DEBUG_GEO_ENABLED:
        return None
    f = _DEBUG_IP_FIXTURES.get(ip)
    if not f:
        return None
    country = f["country"]
    city    = f["city"]
    lat     = f["lat"]
    lng     = f["lng"]
    market = _city_to_market(country, city, lat, lng)
    return {
        "country":      country,
        "country_name": _COUNTRY_NAMES.get(country, country),
        "city":         city,
        "region":       f.get("region") or "",
        "market":       market,
        "latitude":     lat,
        "longitude":    lng,
        "timezone":     _TIMEZONES.get(market, "UTC"),
        "source":       "debug_fixture",
    }


async def _fetch_maxmind(ip: str) -> dict | None:
    """Placeholder for MaxMind GeoLite2 City local DB. We don't ship the
    binary in this pod; when ops wires the DB path via env we'll switch."""
    db_path = os.environ.get("MAXMIND_DB_PATH")
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        import maxminddb
        reader = maxminddb.open_database(db_path)
        rec = reader.get(ip) or {}
        country = ((rec.get("country") or {}).get("iso_code") or "").upper()
        city    = ((rec.get("city") or {}).get("names") or {}).get("en") or ""
        loc     = rec.get("location") or {}
        lat = float(loc.get("latitude") or 0.0)
        lng = float(loc.get("longitude") or 0.0)
        if not country:
            return None
        market = _city_to_market(country, city, lat, lng)
        return {
            "country":      country,
            "country_name": _COUNTRY_NAMES.get(country, country),
            "city":         city or "—",
            "region":       (rec.get("subdivisions") or [{}])[0].get("iso_code", ""),
            "market":       market,
            "latitude":     lat,
            "longitude":    lng,
            "timezone":     loc.get("time_zone") or _TIMEZONES.get(market, "UTC"),
            "source":       "ip",
        }
    except Exception:
        return None


async def _from_provider(ip: str) -> dict | None:
    """Resolution chain (Bug B fix):
       0. BIGFM_DEBUG_GEO=1 fixture (off in prod).
       1. ipapi.co (HTTPS, free tier — primary).
       2. ipinfo.io (HTTPS, free tier — secondary).
       3. ip-api.com (paid, only when IP_GEO_API_KEY is set — tertiary).
       4. maxmind local DB (only when MAXMIND_DB_PATH is set + db exists).
       Returns the FIRST successful normalized dict, else None.
    """
    fixture = _debug_fixture(ip)
    if fixture:
        logger.info("[geo] debug fixture for ip=%s → %s", ip, fixture["city"])
        return fixture
    if PROVIDER == "maxmind":
        return await _fetch_maxmind(ip)
    if PROVIDER in ("ipapi.co", "ipapi", "live"):
        result = await _fetch_ipapi(ip)
        if result:
            return result
        # ipapi 429 / down — try ipinfo.io next.
        result = await _fetch_ipinfo(ip)
        if result:
            logger.info("[geo] resolved via ipinfo.io fallback ip=%s → %s", ip, result.get("city"))
            return result
        # ipinfo down too — try ip-api.com if env-gated.
        result = await _fetch_ip_api(ip)
        if result:
            logger.info("[geo] resolved via ip-api.com fallback ip=%s → %s", ip, result.get("city"))
            return result
        # All providers exhausted — try maxmind if configured.
        result = await _fetch_maxmind(ip)
        if result:
            return result
        return None
    return None  # mock or unknown


async def _cached_lookup(db: Any, ip: str) -> dict:
    """Cache wrapper. Returns a mock fallback if both provider + cache fail.

    Bug B fix — Mongo strips ``tzinfo`` from naive ``datetime`` writes, so
    the ``expires_at`` comes back naive while we compare against an aware
    ``datetime.now(timezone.utc)``. The original ``try/except: pass`` here
    silently swallowed the ``TypeError`` and forced a fresh provider hit
    (which then 429'd on ipapi.co and bottomed-out at "Global"). We now
    coerce naive datetimes to UTC before the comparison so the cached
    Dubai/NYC/London entries are honoured.
    """
    if not ip:
        return _mock_result("mock_no_ip")
    if db is not None:
        try:
            doc = await db.geo_cache.find_one({"_id": ip})
            if doc:
                expires = doc.get("expires_at")
                if isinstance(expires, datetime):
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if expires > datetime.now(timezone.utc):
                        out = {k: v for k, v in doc.items()
                                  if k not in ("_id", "expires_at")}
                        out["source"] = doc.get("source") or "ip"
                        return out
        except Exception as e:
            logger.warning("[geo] cache lookup failed for ip=%s: %s: %s",
                                  ip, type(e).__name__, e)
    result = await _from_provider(ip)
    if not result:
        return _mock_result("mock_provider_fail" if PROVIDER != "mock" else "mock")
    if db is not None:
        try:
            await db.geo_cache.update_one(
                {"_id": ip},
                {"$set": {**result,
                                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=CACHE_TTL_SECONDS)}},
                upsert=True,
            )
        except Exception as e:
            logger.warning("[geo] cache write failed for ip=%s: %s: %s",
                                  ip, type(e).__name__, e)
    return result


def _ip_from_request(request) -> str:
    """Resolve client IP from common forwarded headers."""
    if request is None:
        return ""
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff: return xff
    real = request.headers.get("x-real-ip")
    if real: return real.strip()
    try:
        return request.client.host or ""
    except Exception:
        return ""


# Phase 15d.1 — timezone → market fallback. Used when ipapi.co is rate-limited
# OR when the client sends `?tz=America/Chicago` (browser-provided via Intl).
# Covers the 6 shipping markets + common neighbouring zones we'd route to them.
_TZ_TO_MARKET = {
    "Asia/Dubai":            "dubai",
    "Asia/Muscat":           "dubai",
    "Asia/Qatar":            "dubai",
    "Asia/Bahrain":          "dubai",
    "Asia/Riyadh":           "dubai",
    "Asia/Kuwait":           "dubai",
    "Europe/London":         "london",
    "Europe/Belfast":        "london",
    "Europe/Dublin":         "london",
    "Asia/Kolkata":          "mumbai",
    "Asia/Calcutta":         "mumbai",
    "Asia/Karachi":          "mumbai",
    "Asia/Colombo":          "mumbai",
    "America/New_York":      "new_york",
    "America/Detroit":       "new_york",
    "America/Toronto":       "new_york",
    "America/Indiana/Indianapolis": "new_york",
    "America/Los_Angeles":   "los_angeles",
    "America/Vancouver":     "los_angeles",
    "America/Phoenix":       "los_angeles",
    "America/Denver":        "los_angeles",
    "America/Tijuana":       "los_angeles",
    "America/Chicago":       "dfw",
    "America/Mexico_City":   "dfw",
    "America/Monterrey":     "dfw",
    "America/Winnipeg":      "dfw",
}


def _resolve_from_tz(tz: str | None) -> dict | None:
    """Map an IANA timezone string to a market when ipapi can't help."""
    if not tz:
        return None
    market = _TZ_TO_MARKET.get(tz)
    if not market:
        return None
    try:
        from services.market_lexicon import get_lexicon
        lex = get_lexicon(market)
    except Exception:
        lex = {}
    return {
        "country":      lex.get("country") or "",
        "country_name": _COUNTRY_NAMES.get(lex.get("country") or "",
                                                              lex.get("country") or ""),
        "city":         lex.get("display_name") or "",
        "region":       lex.get("region") or "",
        "market":       market,
        "latitude":     (lex.get("centroid") or [0.0, 0.0])[0],
        "longitude":    (lex.get("centroid") or [0.0, 0.0])[1],
        "timezone":     tz,
        "source":       "tz",
    }


async def resolve_geo_from_ip(request, db) -> dict:
    """Public entrypoint. Always returns a structured dict; never raises.
       Order of preference:
        1. ipapi/maxmind IP lookup (24h cached in `geo_cache`).
        2. Client-provided timezone (`?tz=…` query OR `x-bigfm-tz` header).
        3. Mock Dubai fallback (logged warning).
    """
    ip = _ip_from_request(request)
    res = await _cached_lookup(db, ip)
    # If the IP path could NOT resolve to a real market, try the tz hint.
    if res.get("source", "").startswith("mock"):
        tz = None
        try:
            tz = (request.query_params.get("tz") if request else None)
            if not tz:
                tz = request.headers.get("x-bigfm-tz") if request else None
        except Exception:
            tz = None
        tz_res = _resolve_from_tz(tz)
        if tz_res:
            return tz_res
    return res


async def resolve_for_user(request, user: dict | None, db) -> dict:
    """Single source of truth for *every* page that wants to know the
    listener's market.  Precedence (highest → lowest):
      1. `user.preferred_city` — Bug B explicit city override (NEW). Free-text
         label; we match it against the lexicon's display_name. If the
         match wins we also set `market` to the matched key so RJ /
         music / channel routing stays in sync.
      2. `user.preferred_market` — explicit CityChip override (legacy).
      3. `user.market`              — home market from onboarding (Phase 18b
                                                  RCA: was previously ignored — a Dubai
                                                  user's home page showed "around Dallas"
                                                  because we fell straight through to
                                                  IP geo).
      4. IP geolocation            — anonymous / cold-start fallback.
      5. Hard fallback              — neutral 'BigFM Global' shape.
    """
    base = await resolve_geo_from_ip(request, db)
    if user and isinstance(user, dict):
        try:
            from services.market_lexicon import (
                get_lexicon, supported_markets, MARKET_LEXICON,
            )
            supported = set(supported_markets())
        except Exception:
            supported = set()
            MARKET_LEXICON = {}  # type: ignore[assignment]
        # Bug B — preferred_city wins over preferred_market when present.
        pref_city = (user.get("preferred_city") or "").strip()
        if pref_city:
            # Match by display_name (case-insensitive) → resolve to market.
            for mkey, mentry in (MARKET_LEXICON or {}).items():
                if (mentry.get("display_name") or "").strip().lower() == pref_city.lower():
                    try:
                        lex = get_lexicon(mkey)
                        return {**base,
                                      "market":   mkey,
                                      "city":     lex.get("display_name") or pref_city,
                                      "country": lex.get("country") or base.get("country"),
                                      "timezone": lex.get("timezone") or base.get("timezone"),
                                      "source":    "user_preferred_city"}
                    except Exception:
                        break
            # No lexicon match → still honour the free-text city in the
            # display label but keep base market/coords (best-effort).
            return {**base, "city": pref_city, "source": "user_preferred_city_unmatched"}
        pref = (user.get("preferred_market") or "").strip().lower()
        home = (user.get("market")                or "").strip().lower()
        chosen = pref if pref in supported else (home if home in supported else None)
        if chosen:
            try:
                lex = get_lexicon(chosen)
                base = {**base,
                              "market":   chosen,
                              "city":        (lex.get("display_name") or lex.get("city")
                                                  or base.get("city")),
                              "timezone": lex.get("timezone") or base.get("timezone"),
                              "source":    "override" if pref == chosen else "user_profile"}
            except Exception:
                base = {**base, "market": chosen,
                              "source": "override" if pref == chosen else "user_profile"}
    return base


def ensure_geo_indexes_sync():
    """Stub — `geo_cache` is keyed on `_id` (the IP) so no extra index needed.
    TTL is enforced by the `expires_at` field at read time."""
    return True
