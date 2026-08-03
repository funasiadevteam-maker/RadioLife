"""Phase 42-F.3 — NewsAPI.org provider for top headlines.

A second news source layered on top of the existing newsdata.io client.

Activated by env: `NEWS_PROVIDER=newsapi` (or the routes.news layer can
opt-in per request — see `enabled()` / `is_preferred()`).

Cache strategy (per the F.3 spec):
  - In-memory cache per (market, category) with 15-min TTL.
  - Cache miss → live fetch + write-through.
  - Daily request counter `newsapi_requests_today` (per UTC day).  When
    we approach the 100/day plan cap, refuse new live calls and let
    callers fall back to the DB cache.
  - 60-min background sweeper refreshes the active markets so the cache
    stays warm without bursty user-driven fetches.

Market → country mapping (lower-case keys):
  dfw, dallas, new_york, los_angeles, chicago, miami, seattle, sf,
                                              boston → us
  dubai, ae                                                      → ae
  india, mumbai, delhi, bangalore, chennai     → in
  london, uk, gb                                                → gb
  global / unknown                                              → us  (NewsAPI requires a country)
"""
from __future__ import annotations
import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

log = logging.getLogger("bigfm.newsapi")

API_KEY = (os.environ.get("NEWSAPI_API_KEY") or "").strip()
TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"
EVERYTHING_URL    = "https://newsapi.org/v2/everything"
DEFAULT_TIMEOUT = 12.0

# Live plan limit — Developer tier is 100/day.  We back off at 90 to leave
# room for the sweeper.
DAILY_LIMIT = int(os.environ.get("NEWSAPI_DAILY_LIMIT", "100"))
LIVE_BACKOFF_AT = int(os.environ.get("NEWSAPI_LIVE_BACKOFF_AT", "90"))

CACHE_TTL_SEC = 15 * 60  # 15 minutes
ACTIVE_MARKETS = ["us", "ae", "in", "gb"]
ACTIVE_CATEGORIES = ["general", "business", "technology",
                     "entertainment", "sports"]

# Markets where NewsAPI Developer tier returns useful results from
# /v2/top-headlines.  Anywhere else, we route to /v2/everything with a
# country-keyword query.
_HEADLINES_COUNTRIES = {"us"}

# Country keyword fallback for /v2/everything routing.
# Phase 42-F.7 — these are ALSO used as the "city/region" filter when
# building the blended Local+National feed.  Keep them tight enough to
# bias toward the listener's market without dropping below ~15 hits/day.
_COUNTRY_KEYWORD = {
    "ae": "UAE OR Dubai OR Abu Dhabi",
    "in": "India",
    "gb": "United Kingdom OR London",
}

# Phase 42-F.7 — city-level keyword used ONLY for blended-feed local
# weight.  This is the *city-locality* component (paired with national
# headlines from /v2/top-headlines for the same country).  Falls through
# to `_COUNTRY_KEYWORD` when the market alias is country-level (e.g.
# `india`, `ae`).
_MARKET_LOCAL_KEYWORD = {
    # US cities → /v2/everything search query
    "dfw":              "Dallas OR Fort Worth OR \"DFW\"",
    "dallas":          "Dallas OR Fort Worth",
    "new_york":      "\"New York\" OR Manhattan OR Brooklyn",
    "los_angeles": "\"Los Angeles\" OR \"LA\"",
    "chicago":      "Chicago",
    "miami":          "Miami",
    "seattle":      "Seattle",
    "sf":              "\"San Francisco\" OR \"Bay Area\"",
    "boston":          "Boston",
    # India cities (and India alias)
    "india":          "Mumbai OR Delhi OR Bangalore OR Bengaluru OR Chennai OR Kolkata OR Hyderabad",
    "mumbai":          "Mumbai",
    "delhi":          "\"New Delhi\" OR Delhi",
    "bangalore":  "Bangalore OR Bengaluru",
    "chennai":      "Chennai",
    "kolkata":      "Kolkata",
    "hyderabad":  "Hyderabad",
    "pune":              "Pune",
    # UAE cities (and UAE alias)
    "dubai":          "Dubai",
    "ae":              "Dubai OR \"Abu Dhabi\"",
    "uae":              "Dubai OR \"Abu Dhabi\"",
    "abu_dhabi":  "\"Abu Dhabi\"",
    # UK cities (and UK alias)
    "london":          "London",
    "gb":              "London OR Manchester OR Birmingham",
    "uk":              "London OR Manchester",
}

# Market alias → 2-char country code
_MARKET_COUNTRY = {
    # United States hubs
    "us": "us", "dfw": "us", "dallas": "us", "new_york": "us",
    "los_angeles": "us", "chicago": "us", "miami": "us",
    "seattle": "us", "sf": "us", "boston": "us",
    # UAE
    "ae": "ae", "dubai": "ae", "uae": "ae", "abu_dhabi": "ae",
    # India
    "in": "in", "india": "in", "mumbai": "in", "delhi": "in",
    "bangalore": "in", "chennai": "in", "kolkata": "in",
    "hyderabad": "in", "pune": "in",
    # UK
    "gb": "gb", "uk": "gb", "london": "gb",
}

# NewsAPI categories: business, entertainment, general, health, science,
#                    sports, technology
_OUR_TO_NEWSAPI_CATEGORY = {
    "top":            "general",
    "world":          "general",
    "business":       "business",
    "technology":     "technology",
    "entertainment":  "entertainment",
    "sports":         "sports",
    "health":         "health",
    "science":        "science",
}


def enabled() -> bool:
    return bool(API_KEY)


def is_preferred() -> bool:
    return (os.environ.get("NEWS_PROVIDER") or "").strip().lower() == "newsapi"


def market_to_country(market: Optional[str]) -> str:
    m = (market or "").strip().lower()
    return _MARKET_COUNTRY.get(m, "us")


def our_category_to_newsapi(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    return _OUR_TO_NEWSAPI_CATEGORY.get(category.lower())


# ─── Per-process quota + cache state.  Single shared dict guarded by
#      a lock; the route handlers can read concurrently but writes go
#      through `_with_lock` to avoid lost updates.
_lock = threading.Lock()
_cache: dict = {}              # key -> {"at": float, "articles": list}
_daily: dict = {"day": None, "count": 0}


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _quota_check_and_bump() -> bool:
    """Returns True when the live request slot is granted, False when
    the daily quota is exhausted (≥ LIVE_BACKOFF_AT)."""
    today = _today_key()
    with _lock:
        if _daily["day"] != today:
            _daily["day"] = today
            _daily["count"] = 0
        if _daily["count"] >= LIVE_BACKOFF_AT:
            return False
        _daily["count"] += 1
    return True


def _cache_get(key: str) -> Optional[list]:
    with _lock:
        row = _cache.get(key)
        if not row:
            return None
        if time.time() - row["at"] > CACHE_TTL_SEC:
            return None
        return row["articles"]


def _cache_set(key: str, articles: list) -> None:
    with _lock:
        _cache[key] = {"at": time.time(), "articles": articles}


def quota_state() -> dict:
    with _lock:
        return {"day":   _daily.get("day"),
                "count": int(_daily.get("count") or 0),
                "limit": DAILY_LIMIT,
                "backoff_at": LIVE_BACKOFF_AT,
                "cache_keys": list(_cache.keys())}


def _norm_article(a: dict, market: str, our_category: Optional[str]) -> dict:
    """NewsAPI → internal shape (matches what newsdata returns from
    services.newsdata_client._norm)."""
    pub = a.get("publishedAt") or ""
    # Stable derived id — newsapi doesn't expose one.  Use URL hash.
    import hashlib
    seed = (a.get("url") or "") + (a.get("title") or "")
    nid = "newsapi_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]
    cats = [our_category] if our_category else ["top"]
    return {
        "news_id":     nid,
        "title":       (a.get("title") or "").strip(),
        "link":        a.get("url") or "",
        "description": (a.get("description") or "").strip() or None,
        "pubDate":     pub,
        "source_id":   ((a.get("source") or {}).get("id")
                                  or (a.get("source") or {}).get("name") or "newsapi"),
        "source_name": (a.get("source") or {}).get("name") or "NewsAPI",
        "image_url":   a.get("urlToImage") or None,
        "categories":  cats,
        # Phase 42-F.3 — tag the article with the resolved market so the
        # Local-first tab can filter.
        "market":      market,
        "provider":    "newsapi",
    }


# ── Phase K.URGENT — Geo-leak hardening for /v2/everything ──────────
# /v2/everything is unscoped by default, so an Indian Livemint article
# that mentions "Dallas" in its body can leak into the DFW "Around
# Dallas" strip.  We restrict the upstream query via `domains=` AND
# post-filter the response against the same whitelist (NewsAPI
# occasionally returns wire-mirror copies on other-country domains).
_DOMAINS_BY_COUNTRY = {
    "us": ("dallasnews.com,nbcdfw.com,dallasobserver.com,star-telegram.com,"
                "texastribune.org,texasmonthly.com,kera.org,"
                "wfaa.com,fox4news.com,nytimes.com,washingtonpost.com,"
                "cnn.com,foxnews.com,abcnews.go.com,nbcnews.com,reuters.com,"
                "apnews.com,bloomberg.com,usatoday.com,wsj.com,axios.com,"
                "politico.com,latimes.com,sfchronicle.com,chicagotribune.com,"
                "bostonglobe.com,miamiherald.com,seattletimes.com,npr.org,"
                "houstonchronicle.com,nypost.com,thehill.com,vox.com"),
    "ae": ("gulfnews.com,thenationalnews.com,thenational.ae,khaleejtimes.com,"
                "arabianbusiness.com,zawya.com,wam.ae"),
    "gb": ("bbc.co.uk,theguardian.com,guardian.co.uk,telegraph.co.uk,"
                "independent.co.uk,ft.com,thetimes.co.uk,"
                "skynews.com,standard.co.uk,thesun.co.uk,mirror.co.uk"),
    "in": ("ndtv.com,timesofindia.indiatimes.com,thehindu.com,"
                "hindustantimes.com,indianexpress.com,livemint.com,"
                "economictimes.indiatimes.com,news18.com,firstpost.com,"
                "scroll.in,thewire.in,deccanherald.com,deccanchronicle.com,"
                "telegraphindia.com,businesstoday.in,moneycontrol.com,"
                "indiatoday.in,thequint.com,thebetterindia.com"),
}


def _domains_for_country(country: str) -> Optional[str]:
    """Return the NewsAPI `domains=` value (CSV) for a country, or
    None when we don't have a whitelist for it.  Accepts both ISO
    country codes ("us") and BigFM market aliases ("dfw", "dubai") —
    market aliases are normalised to their country first."""
    if not country:
        return None
    cc = country.lower()
    # Phase K.URGENT — market alias → country code coercion.
    _MARKET_TO_CC = {
        "dfw":"us","dallas":"us","new_york":"us","los_angeles":"us",
        "sf":"us","chicago":"us","miami":"us","seattle":"us",
        "boston":"us","houston":"us",
        "dubai":"ae","uae":"ae","abu_dhabi":"ae",
        "london":"gb","uk":"gb",
        "india":"in","mumbai":"in","delhi":"in","bangalore":"in",
        "chennai":"in","hyderabad":"in","kolkata":"in","pune":"in",
    }
    cc = _MARKET_TO_CC.get(cc, cc)
    return _DOMAINS_BY_COUNTRY.get(cc)


def _matches_country_domain(url: str, country: str) -> bool:
    """SAFETY post-filter: only keep articles whose URL host belongs
    to the country's whitelisted source pool.  When no whitelist is
    configured for that country we return True (don't drop).  Accepts
    market aliases (e.g. `dfw`) the same way `_domains_for_country`
    does."""
    csv = _domains_for_country(country)
    if not csv:
        return True
    host = _url_host(url)
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    return any(host == d or host.endswith("." + d)
                          for d in [s.strip() for s in csv.split(",") if s.strip()])


async def _fetch_everything_by_keyword(query: str,
                                                                                              country_hint: str,
                                                                                              page_size: int = 12,
                                                                                              cache_key_suffix: str = "everything",
                                                                                              ) -> list[dict]:
    """Hits /v2/everything for a free-text query.  Used both by the
    `country in {ae,in,gb}` branch of `fetch_top_headlines` and by the
    blended-feed `fetch_blended_headlines` for the city-local leg.

    Phase K.URGENT — Geo-leak fix:
        • Passes `domains=` (whitelist for the country) so /everything
            only returns articles from country-appropriate sources.
        • Post-filters the response against the same whitelist to catch
            anything that slipped through (NewsAPI occasionally returns
            wire-mirror copies on other-country domains).
    """
    if not enabled() or not query:
        return []
    domains_csv = _domains_for_country(country_hint)
    cache_key = (f"{country_hint}|{cache_key_suffix}|{query}|"
                            f"{('d:'+domains_csv) if domains_csv else 'd:any'}")
    cached = _cache_get(cache_key)
    if cached is not None:
        log.info("[newsapi] cache hit %s (n=%d)", cache_key, len(cached))
        return cached
    if not _quota_check_and_bump():
        log.warning("[newsapi] quota cap reached — skip everything query=%r", query)
        return []
    params = {"q": query, "language": "en", "sortBy": "publishedAt",
                      "pageSize": min(max(int(page_size), 1), 30),
                      "apiKey": API_KEY}
    if domains_csv:
        params["domains"] = domains_csv
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(EVERYTHING_URL, params=params)
    except httpx.HTTPError as e:
        log.warning("[newsapi] /everything http err: %s", e)
        return []
    if r.status_code != 200:
        log.warning("[newsapi] /everything HTTP %s body[:200]=%r",
                                r.status_code, r.text[:200])
        return []
    try:
        body = r.json()
    except Exception as e:
        log.warning("[newsapi] /everything decode: %s", e)
        return []
    if body.get("status") != "ok":
        return []
    raw = body.get("articles") or []
    out = [_norm_article(a, country_hint, None) for a in raw
                  if a.get("url") and a.get("title")]
    # Post-filter: drop anything whose URL host isn't in the country
    # whitelist.  This is a belt-and-braces guard on top of `domains=`.
    pre = len(out)
    out = [a for a in out
                if _matches_country_domain(a.get("url") or "", country_hint)]
    dropped = pre - len(out)
    if dropped:
        log.info("[newsapi] geo-filter dropped %d/%d articles for %s",
                        dropped, pre, country_hint)
    _cache_set(cache_key, out)
    log.info("[newsapi] /everything %s → %d (quota=%d/%d)",
                      cache_key, len(out), _daily.get("count"), DAILY_LIMIT)
    return out


async def _fetch_top_headlines_us_only(category: Optional[str],
                                                                                              page_size: int = 12) -> list[dict]:
    """Hits /v2/top-headlines for country=us.  Phase 42-F.7 helper for
    the blended-feed national leg (US listeners get real top-headlines;
    AE/IN/GB listeners use the /everything country-keyword path below)."""
    if not enabled():
        return []
    newsapi_cat = our_category_to_newsapi(category)
    cache_key = f"us|{newsapi_cat or 'general'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        log.info("[newsapi] cache hit %s (n=%d)", cache_key, len(cached))
        return cached
    if not _quota_check_and_bump():
        log.warning("[newsapi] quota cap reached — skip top-headlines us")
        return []
    params = {"country": "us", "pageSize": page_size, "apiKey": API_KEY}
    if newsapi_cat:
        params["category"] = newsapi_cat
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(TOP_HEADLINES_URL, params=params)
    except httpx.HTTPError as e:
        log.warning("[newsapi] /top-headlines http err: %s", e)
        return []
    if r.status_code != 200:
        log.warning("[newsapi] /top-headlines HTTP %s body[:200]=%r",
                                r.status_code, r.text[:200])
        return []
    try:
        body = r.json()
    except Exception as e:
        log.warning("[newsapi] /top-headlines decode: %s", e)
        return []
    if body.get("status") != "ok":
        return []
    raw = body.get("articles") or []
    out = [_norm_article(a, "us", category) for a in raw
                  if a.get("url") and a.get("title")]
    _cache_set(cache_key, out)
    log.info("[newsapi] /top-headlines us → %d (quota=%d/%d)",
                      len(out), _daily.get("count"), DAILY_LIMIT)
    return out


async def fetch_top_headlines(market: Optional[str] = None,
                               category: Optional[str] = None,
                               page_size: int = 20) -> list[dict]:
    """Returns a list of normalised article dicts.  Honours the in-memory
    cache + quota guards.  Returns `[]` on any error so callers can fall
    back to whatever DB cache they hold.

    Phase 42-F.3 — automatic endpoint routing:
      • `country=us`                     → /v2/top-headlines (with optional category)
      • `country in {ae, in, gb}` → /v2/everything (country-keyword search)
    The Developer-tier key cannot fetch top-headlines outside the US.
    """
    if not enabled():
        log.info("[newsapi] key missing — skip")
        return []
    country = market_to_country(market)
    newsapi_cat = our_category_to_newsapi(category)
    cache_key = f"{country}|{newsapi_cat or 'general'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        log.info("[newsapi] cache hit %s (n=%d)", cache_key, len(cached))
        return cached
    if not _quota_check_and_bump():
        log.warning("[newsapi] daily quota cap reached "
                                "(>= %d/%d) — refusing live fetch", LIVE_BACKOFF_AT,
                                DAILY_LIMIT)
        return []
    page_size = min(max(int(page_size), 1), 30)
    # Build the right URL + params for this country.
    if country in _HEADLINES_COUNTRIES:
        url = TOP_HEADLINES_URL
        params = {"country": country, "pageSize": page_size,
                          "apiKey": API_KEY}
        if newsapi_cat:
            params["category"] = newsapi_cat
    else:
        # /v2/everything — country-keyword query.  Falls back to a
        # broader English search when we don't have a mapping (last
        # resort so we never return [] just because of a missing
        # country alias).
        kw = _COUNTRY_KEYWORD.get(country) or country.upper()
        url = EVERYTHING_URL
        params = {"q": kw, "language": "en",
                          "sortBy": "publishedAt",
                          "pageSize": page_size, "apiKey": API_KEY}
        # /v2/everything ignores `category`; we synthesise one in our
        # normalised output via `our_category_to_newsapi` above.
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(url, params=params)
    except httpx.HTTPError as e:
        log.warning("[newsapi] http error: %s", e)
        return []
    if r.status_code != 200:
        log.warning("[newsapi] HTTP %s body[:200]=%r",
                                r.status_code, r.text[:200])
        return []
    try:
        body = r.json()
    except Exception as e:
        log.warning("[newsapi] decode failed: %s", e)
        return []
    if body.get("status") != "ok":
        log.warning("[newsapi] api error: %s", body)
        return []
    raw = body.get("articles") or []
    market_canonical = (market or country).strip().lower()
    out = [_norm_article(a, market_canonical, category) for a in raw
                  if a.get("url") and a.get("title")]
    _cache_set(cache_key, out)
    log.info("[newsapi] live fetch %s url=%s → %d articles (quota=%d/%d)",
                      cache_key, url.rsplit("/", 1)[-1], len(out),
                      _daily.get("count"), DAILY_LIMIT)
    return out


async def fetch_blended_headlines(market: str,
                                                                                              page_size: int = 20,
                                                                                              ) -> dict:
    """Phase 42-F.7 — Local + National blended feed.

    Returns `{items, local_count, national_count, market, country}`.
    Each item carries `news_type ∈ {"local","national"}` so the
    frontend can tag the card.

    Strategy:
      • LOCAL leg → /v2/everything keyword search.  Source keyword comes
        from `_MARKET_LOCAL_KEYWORD[market]` when set, else
        `_COUNTRY_KEYWORD[country]`, else `country.upper()`.
      • NATIONAL leg → `/v2/top-headlines` for the US, or
        `/v2/everything` with the country-level keyword for AE / IN /
        GB (NewsAPI Developer tier doesn't return top-headlines for
        non-US markets).
      • Dedupe by URL across both legs.
      • Interleave 60/40 local : national (or 12/8 of a 20-item feed).
      • Graceful fall-through: if local is empty → all national; if
        national is empty → all local.  Caller (`routes/news.py`) is
        responsible for the further "use DB cache" fallback.

    Char/quota note: this leg costs TWO live calls per cold market.  The
    in-memory cache shares the same 15-min TTL so subsequent listeners
    in the same market reuse the work.
    """
    market = (market or "").strip().lower().replace(" ", "_").replace("-", "_")
    country = market_to_country(market)
    # Targets — local = ~12, national = ~8 for a 20-item feed.
    n_local = max(4, int(round(page_size * 0.6)))
    n_national = max(4, page_size - n_local)

    local_q = _MARKET_LOCAL_KEYWORD.get(market) \
                                  or _COUNTRY_KEYWORD.get(country) \
                                  or country.upper()
    local_arts = await _fetch_everything_by_keyword(
        local_q, country_hint=market or country,
        page_size=n_local + 4, cache_key_suffix="local")
    # Tag the local leg.
    for a in local_arts:
        a["news_type"] = "local"
        a["market"] = market or country

    if country == "us":
        national_arts = await _fetch_top_headlines_us_only(
            category=None, page_size=n_national + 4)
    else:
        nat_q = _COUNTRY_KEYWORD.get(country) or country.upper()
        national_arts = await _fetch_everything_by_keyword(
            nat_q, country_hint=country,
            page_size=n_national + 4, cache_key_suffix="national")
    # Tag the national leg.  Override any earlier market tag — these
    # rows belong to the country pool, not the city.
    for a in national_arts:
        a["news_type"] = "national"
        a["market"] = country

    # Dedupe by URL — local wins on collision (more relevant to listener).
    seen_urls = set()
    local_clean: list[dict] = []
    for a in local_arts:
        url = a.get("link")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        local_clean.append(a)
    national_clean: list[dict] = []
    for a in national_arts:
        url = a.get("link")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        national_clean.append(a)

    # Trim to targets BEFORE interleaving so the ratios hold.
    local_clean = local_clean[:n_local]
    national_clean = national_clean[:n_national]

    # Graceful fall-through.
    if not local_clean and national_clean:
        out = national_clean[:page_size]
        return {"items": out,
                      "local_count": 0,
                      "national_count": len(out),
                      "market": market or country,
                      "country": country,
                      "fallback_reason": "no_local_results"}
    if local_clean and not national_clean:
        out = local_clean[:page_size]
        return {"items": out,
                      "local_count": len(out),
                      "national_count": 0,
                      "market": market or country,
                      "country": country,
                      "fallback_reason": "no_national_results"}
    if not local_clean and not national_clean:
        return {"items": [],
                      "local_count": 0,
                      "national_count": 0,
                      "market": market or country,
                      "country": country,
                      "fallback_reason": "both_empty"}

    # Interleave: target pattern roughly L, N, L, L, N, L, N, L, ...
    # Implemented as ratio-driven: at each step, take from the source
    # that has *the highest fractional remaining quota*.  Produces a
    # nice weave without hard-coding a pattern.
    out: list[dict] = []
    li, ni = 0, 0
    total = len(local_clean) + len(national_clean)
    while li + ni < total:
        # Want overall ratio local/(local+national) ≈ 0.6.
        # If current `out` is undershooting that ratio, take local; else national.
        achieved_local_ratio = li / max(1, len(out)) if out else 0
        want_more_local = (achieved_local_ratio < 0.6) and (li < len(local_clean))
        if (li < len(local_clean)) and (want_more_local or ni >= len(national_clean)):
            out.append(local_clean[li])
            li += 1
        else:
            out.append(national_clean[ni])
            ni += 1
    return {"items": out[:page_size],
                  "local_count":      sum(1 for a in out[:page_size]
                                                                if a.get("news_type") == "local"),
                  "national_count": sum(1 for a in out[:page_size]
                                                                if a.get("news_type") == "national"),
                  "market":      market or country,
                  "country":  country,
                  "fallback_reason": None}


async def warm_cache_for_active_markets() -> dict:
    """Background sweeper: refreshes the active markets.  Designed to be
    invoked once per hour from server.py.

    Phase 42-F.3 — we only sweep one category per market (the implicit
    `general` / market-wide top headlines) to keep the daily quota
    headroom for user-driven requests.  Category-specific cache
    entries warm on-demand via `fetch_top_headlines`.
    """
    summary = {"refreshed": 0, "skipped_cached": 0, "errors": 0,
               "quota_blocked": 0}
    if not enabled():
        summary["skipped"] = "newsapi_not_configured"
        return summary
    for mkt in ACTIVE_MARKETS:
        try:
            country = market_to_country(mkt)
            key = f"{country}|general"
            if _cache_get(key) is not None:
                summary["skipped_cached"] += 1
                continue
            arts = await fetch_top_headlines(market=mkt, category=None,
                                                                              page_size=20)
            if arts:
                summary["refreshed"] += 1
            else:
                # Either empty (no quota left) or genuinely no results;
                # we logged the reason inside fetch_top_headlines.
                summary["errors"] += 1
        except Exception as e:
            log.warning("[newsapi-sweeper] %s: %s", mkt, e)
            summary["errors"] += 1
    summary["quota"] = quota_state()
    return summary
