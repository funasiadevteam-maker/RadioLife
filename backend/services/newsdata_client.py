"""Phase 40 — NewsData.io client.

Provides `fetch_latest_headlines()`.  Mock mode kicks in when
`NEWSDATA_API_KEY` is unset or equal to 'mock' so dev environments stay
functional without quota.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

log = logging.getLogger("bigfm.newsdata")

API_KEY  = os.environ.get("NEWSDATA_API_KEY", "").strip()
_BASE_RAW = os.environ.get("NEWSDATA_BASE_URL",
                           "https://newsdata.io/api/1").rstrip("/")
# Tolerate both `.../api/1` and `.../api/1/news` in env — we always
# call the /news endpoint.
BASE_URL = _BASE_RAW if _BASE_RAW.endswith("/news") else f"{_BASE_RAW}/news"
TIMEOUT  = 12.0


_MOCK_HEADLINES = [
    {"news_id": "mock_n1", "title": "FUUSIC expands AI Radio to three new markets",
     "link": "https://example.com/bigfm-expands",
     "description": ("FUUSIC today announced AI-personalized radio is now live "
                     "in three new metropolitan markets, doubling its reach."),
     "pubDate": "2026-06-07 10:00:00", "source_id": "bigfm",
     "image_url": None, "categories": ["technology", "business"]},
    {"news_id": "mock_n2", "title": "RTA's metro extension feasibility study advances",
     "link": "https://example.com/rta-metro",
     "description": ("Dubai's Roads and Transport Authority confirmed the next "
                     "phase of the metro extension feasibility study."),
     "pubDate": "2026-06-07 09:30:00", "source_id": "khaleej_times",
     "image_url": None, "categories": ["top", "world"]},
    {"news_id": "mock_n3", "title": "Markets edge higher on tech rally",
     "link": "https://example.com/markets",
     "description": "Equity markets gained 0.8% led by megacap technology shares.",
     "pubDate": "2026-06-07 09:00:00", "source_id": "reuters",
     "image_url": None, "categories": ["business"]},
    {"news_id": "mock_n4", "title": "Premier League weekend wrap-up",
     "link": "https://example.com/epl",
     "description": "A surprise win at the top of the Premier League table.",
     "pubDate": "2026-06-07 08:30:00", "source_id": "bbc",
     "image_url": None, "categories": ["sports"]},
    {"news_id": "mock_n5", "title": "New blockbuster opens to packed cinemas",
     "link": "https://example.com/movies",
     "description": "Opening-weekend numbers exceeded analyst forecasts.",
     "pubDate": "2026-06-07 08:00:00", "source_id": "variety",
     "image_url": None, "categories": ["entertainment"]},
]


def _is_mock() -> bool:
    return (not API_KEY) or API_KEY.lower() == "mock"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(article: dict) -> dict:
    """Normalize NewsData.io article → our internal shape."""
    cats = article.get("category") or []
    if isinstance(cats, str):
        cats = [cats]
    return {
        "news_id":     article.get("article_id") or article.get("link") or "",
        "title":       (article.get("title") or "").strip(),
        "link":        article.get("link") or "",
        "description": (article.get("description") or "").strip() or None,
        "pubDate":     article.get("pubDate") or "",
        "source_id":   article.get("source_id") or "",
        "source_name": article.get("source_name") or article.get("source_id") or "",
        "image_url":   article.get("image_url") or None,
        "categories":  cats,
    }


async def fetch_latest_headlines(
        country: Optional[str] = None,
        category: Optional[str] = None,
        language: str = "en",
        limit: int = 20) -> list[dict]:
    """Returns a list of normalized article dicts (newest first). Caps `limit`
    to 50.  On any error or mock-mode → returns the local stub set."""
    limit = max(1, min(int(limit), 50))
    if _is_mock():
        log.info("[newsdata] mock-mode (no key)")
        return _MOCK_HEADLINES[:limit]

    params = {"apikey": API_KEY, "language": language, "size": min(limit, 10)}
    if country:  params["country"]  = country
    if category: params["category"] = category

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(BASE_URL, params=params)
    except httpx.HTTPError as e:
        log.warning("[newsdata] http error: %s — mock fallback", e)
        return _MOCK_HEADLINES[:limit]

    if r.status_code >= 500:
        log.warning("[newsdata] 5xx %s — mock fallback", r.status_code)
        return _MOCK_HEADLINES[:limit]
    if r.status_code >= 400:
        log.warning("[newsdata] %s — refusing fallback (likely bad key); "
                    "returning empty", r.status_code)
        return []

    body = {}
    try:
        body = r.json()
    except Exception as e:
        log.warning("[newsdata] json decode failed: %s", e)
        return []
    if body.get("status") != "success":
        log.warning("[newsdata] api error: %s", body.get("results"))
        return []
    results = body.get("results") or []
    out = [_norm(a) for a in results if a.get("article_id") and a.get("title")]
    return out[:limit]


def is_live() -> bool:
    return not _is_mock()
