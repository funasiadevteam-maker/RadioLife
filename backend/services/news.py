"""
Phase 15d — local news ingestion. RJ scripts and the Home dashboard
mini-widget pull 3-5 headlines per market. We cache results 30min in
`news_cache` so the AI RJ pipeline can splice "today's headlines" without
hammering the upstream provider on every prewarm.

Provider is configured via env `BIGFM_NEWS_PROVIDER` ∈ {`newsapi`,`mock`}.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta
from typing import Any, List
import httpx

PROVIDER = (os.environ.get("BIGFM_NEWS_PROVIDER") or "mock").lower()
NEWSAPI_KEY = os.environ.get("NEWSAPI_API_KEY") or ""
CACHE_TTL_SECONDS = 30 * 60

# market → NewsAPI query string.
_MARKET_QUERY = {
    "dubai":         "Dubai OR UAE",
    "new_york":      "New York City",
    "london":        "London UK",
    "mumbai":        "Mumbai India",
    "los_angeles":   "Los Angeles",
}

_MOCK_STUBS = {
    "dubai": [
        {"title": "Lunch Rush starts 12pm across Dubai Marina",            "source": "BigFM mock"},
        {"title": "RTA announces metro extension feasibility study",        "source": "BigFM mock"},
        {"title": "Dubai Food Festival returns next weekend",                "source": "BigFM mock"},
    ],
    "new_york": [
        {"title": "Bodega coffee prices hold flat for a sixth week",        "source": "BigFM mock"},
        {"title": "MTA: L-train weekend service unchanged",                  "source": "BigFM mock"},
        {"title": "Brooklyn Bridge resurfacing nears completion",           "source": "BigFM mock"},
    ],
    "london": [
        {"title": "TfL: Bakerloo upgrade timetable",                          "source": "BigFM mock"},
        {"title": "Soho restaurants reopen after street works",             "source": "BigFM mock"},
        {"title": "Thames Clipper adds Sunday service",                      "source": "BigFM mock"},
    ],
    "mumbai": [
        {"title": "Monsoon onset confirmed by IMD",                          "source": "BigFM mock"},
        {"title": "Western Railway local frequency boost on Marine Lines", "source": "BigFM mock"},
        {"title": "Bandra Fest dates announced",                              "source": "BigFM mock"},
    ],
    "los_angeles": [
        {"title": "405 northbound reopens overnight",                        "source": "BigFM mock"},
        {"title": "Marine layer lifts by noon citywide",                     "source": "BigFM mock"},
        {"title": "DTLA art walk this Thursday",                              "source": "BigFM mock"},
    ],
}


def _market_key(market: str | None) -> str:
    if not market: return "dubai"
    return market.strip().lower().replace(" ", "_").replace("-", "_")


async def _fetch_newsapi(market: str, limit: int) -> List[dict]:
    if not NEWSAPI_KEY:
        return []
    q = _MARKET_QUERY.get(market, market)
    url = "https://newsapi.org/v2/everything"
    params = {"q": q, "pageSize": limit, "sortBy": "publishedAt",
                  "language": "en", "apiKey": NEWSAPI_KEY}
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(url, params=params)
        if r.status_code != 200:
            return []
        items = (r.json() or {}).get("articles") or []
        return [{"title": (a.get("title") or "").strip(),
                      "source": ((a.get("source") or {}).get("name") or "—").strip(),
                      "url":    a.get("url") or ""} for a in items[:limit] if a.get("title")]
    except (httpx.HTTPError, ValueError):
        return []


def _mock_payload(market: str, limit: int) -> List[dict]:
    return _MOCK_STUBS.get(market, _MOCK_STUBS["dubai"])[:limit]


async def fetch_local_news(market: str | None, db: Any, limit: int = 5) -> dict:
    """Return `{market, items, source, cached_at}`. Items shape:
       {title, source, url?}.  `source` ∈ {`live`,`mock`,`cache`}."""
    mkt = _market_key(market)
    # cache hit?
    if db is not None:
        try:
            doc = await db.news_cache.find_one({"_id": mkt})
            if doc:
                expires = doc.get("expires_at")
                if isinstance(expires, datetime) and expires > datetime.now(timezone.utc):
                    return {"market": mkt, "items": (doc.get("items") or [])[:limit],
                                "source": doc.get("source") or "cache",
                                "cached_at": (doc.get("cached_at") or "").isoformat()
                                                  if isinstance(doc.get("cached_at"), datetime)
                                                  else doc.get("cached_at")}
        except Exception:
            pass
    # fresh fetch
    items: List[dict] = []
    src = "mock"
    if PROVIDER == "newsapi":
        items = await _fetch_newsapi(mkt, limit)
        src = "live" if items else "mock_fallback"
    if not items:
        items = _mock_payload(mkt, limit)
        if src == "mock":
            src = "mock"
    payload = {"market": mkt, "items": items, "source": src,
                    "cached_at": datetime.now(timezone.utc).isoformat()}
    # write through cache
    if db is not None:
        try:
            await db.news_cache.update_one(
                {"_id": mkt},
                {"$set": {"items": items, "source": src,
                                "cached_at": datetime.now(timezone.utc),
                                "expires_at": datetime.now(timezone.utc)
                                                  + timedelta(seconds=CACHE_TTL_SECONDS)}},
                upsert=True,
            )
        except Exception:
            pass
    return payload
