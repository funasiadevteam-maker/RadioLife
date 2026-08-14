"""Phase 40 — NewsData.io listener endpoints + cache management.

Public-bearer endpoints serving Home headlines strip + /news page + AI
news radio article detail. Cached in `news_articles` collection,
refreshed hourly by a cron in server.py.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from services.newsdata_client import fetch_latest_headlines, is_live
from services import news_api_provider as newsapi_provider

router = APIRouter(prefix="/api/news", tags=["news"])
log = logging.getLogger("bigfm.news")


def _live_flag() -> bool:
    """News is 'live' when a real source is serving — EITHER the active
    NewsAPI provider (NEWS_PROVIDER=newsapi + key) OR the legacy NewsData.io
    key. Previously this only checked NewsData.io, so prod (served by NewsAPI
    with no NewsData key) wrongly showed the "mock mode" banner."""
    return bool(is_live() or (newsapi_provider.is_preferred() and newsapi_provider.enabled()))

VALID_CATEGORIES = {"top", "world", "business", "technology",
                    "entertainment", "sports", "health", "science",
                    "politics"}


@router.get("/preferences")
async def get_news_preferences(request: Request):
    """Phase 41 P2 — returns the logged-in user's saved news interests.
    No auth requirement here — anonymous returns the default set."""
    from auth import current_user_optional
    user = await current_user_optional(request)
    if not user:
        return {"categories": [], "local_enabled": False, "city": None}
    prefs = (user.get("news_preferences") or {})
    return {"categories":    prefs.get("categories") or [],
            "local_enabled": bool(prefs.get("local_enabled")),
            "city":          user.get("city")}


@router.put("/preferences")
async def put_news_preferences(request: Request, body: dict):
    from auth import current_user
    user = await current_user(request)
    db   = request.app.state.db
    cats = body.get("categories") or []
    if not isinstance(cats, list):
        raise HTTPException(400, {"code": "bad_categories"})
    cats = [c for c in cats if c in VALID_CATEGORIES][:8]
    local = bool(body.get("local_enabled"))
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"news_preferences":
                  {"categories": cats, "local_enabled": local}}})
    return {"ok": True, "categories": cats, "local_enabled": local}


def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()


async def _refresh_cache(db, category: Optional[str] = None,
                         limit: int = 20,
                         market: Optional[str] = None) -> int:
    """Fetches headlines and upserts into `news_articles`. Returns
    number of new rows inserted/updated. Idempotent on news_id.

    Phase 42-F.3 — when `NEWS_PROVIDER=newsapi` and a `market` is
    supplied, hits the NewsAPI provider first (cache+quota-aware) and
    falls through to the legacy newsdata.io source on empty/error.
    Articles from NewsAPI are stamped with their market so the
    Local-first tab on /news can filter them.
    """
    articles: list[dict] = []
    if newsapi_provider.is_preferred() and newsapi_provider.enabled():
        try:
            articles = await newsapi_provider.fetch_top_headlines(
                market=market, category=category, page_size=max(limit, 10))
        except Exception as e:
            log.warning("[news] newsapi fetch failed: %s", e)
            articles = []
    if not articles:
        articles = await fetch_latest_headlines(language="en",
                                                category=category, limit=limit)
    n = 0
    for a in articles:
        try:
            # Phase 42-F.3 — preserve market tag if the provider set one
            # (NewsAPI does; newsdata doesn't).  When we pass a `market`
            # arg explicitly, all rows in this batch get tagged with it.
            tagged = {**a}
            if market and not tagged.get("market"):
                tagged["market"] = market.strip().lower()
            await db.news_articles.update_one(
                {"news_id": tagged["news_id"]},
                {"$set": {**tagged, "cached_at": _now_iso()},
                 "$setOnInsert": {"summary_script":   None,
                                  "summary_built_at": None,
                                  "tts_audio_url":    None}},
                upsert=True)
            n += 1
        except Exception as e:
            log.warning("[news] upsert %s failed: %s", a.get("news_id"), e)
    return n


@router.get("/headlines")
async def get_headlines(request: Request,
                                          limit: int = Query(default=20, ge=1, le=30),
                                          category: Optional[str] = Query(default=None),
                                          market: Optional[str] = Query(default=None)):
    """Listener-facing — returns cached headlines, newest first. Used by the
    Home strip + /news page.

    Phase 42-D follow-up — accepts an optional `?market=<key>` (e.g.
    `dubai`, `dfw`, `new_york`) for the News page's Local-first tab.
    When supplied, we filter `news_articles` where `market` matches.
    If the local pool is empty we fall back to the global feed AND
    set `fallback_global=true` so the UI can surface a soft banner.
    `resolved_market` is always echoed back for the tab label.
    """
    db = request.app.state.db
    q: dict = {}
    if category:
        if category not in VALID_CATEGORIES:
            raise HTTPException(400, {"code": "bad_category",
                                                          "allowed": sorted(VALID_CATEGORIES)})
        q["categories"] = category

    resolved_market = (market or "").strip().lower().replace(" ", "_").replace("-", "_") or None
    fallback_global = False

    # Phase 42-F.7 — Blended Local + National feed.
    # Triggered ONLY when:
    #   • a market is supplied (the Local-first tab)
    #   • no category filter is active (Local tab is category-agnostic)
    #   • NewsAPI provider is configured as the live source
    # Other category tabs (World / Tech / etc.) keep the existing
    # market-filtered DB cache path so we don't double-burn the quota.
    if (resolved_market and resolved_market != "global"
                    and not category
                    and newsapi_provider.is_preferred()
                    and newsapi_provider.enabled()):
        try:
            blend = await newsapi_provider.fetch_blended_headlines(
                resolved_market, page_size=limit)
        except Exception as e:
            log.warning("[news] blended fetch %s failed: %s",
                                      resolved_market, e)
            blend = None
        if blend and blend.get("items"):
            # Upsert into Mongo for next-page reads + News Radio
            # rendering pipeline.  Same shape as `_refresh_cache`.
            for a in blend["items"]:
                try:
                    await db.news_articles.update_one(
                        {"news_id": a["news_id"]},
                        {"$set": {**a, "cached_at": _now_iso()},
                          "$setOnInsert": {"summary_script":      None,
                                                          "summary_built_at":  None,
                                                          "tts_audio_url":      None}},
                        upsert=True)
                except Exception as up_err:
                    log.warning("[news] blended upsert %s failed: %s",
                                              a.get("news_id"), up_err)
            return {"count":              len(blend["items"]),
                          "items":              blend["items"],
                          "live":              _live_flag(),
                          "cached_at":      _now_iso(),
                          "resolved_market": resolved_market,
                          "fallback_global": False,
                          "blended":          True,
                          "local_count":      blend.get("local_count", 0),
                          "national_count": blend.get("national_count", 0),
                          "blend_fallback_reason":
                              blend.get("fallback_reason")}
        # Blended fetch came back empty — fall through to the legacy
        # market-filter path so we can serve DB-cached rows if any.

    # Local-first attempt: filter by market when one is supplied.
    if resolved_market and resolved_market != "global":
        local_q = {**q, "market": resolved_market}
        n_local = await db.news_articles.count_documents(local_q)
        # Phase 42-F.3 — if NewsAPI is enabled and this market has no
        # cached articles yet, prime the cache synchronously so the
        # first request returns local content instead of falling through
        # to the global feed.
        if n_local == 0 and newsapi_provider.is_preferred() \
                and newsapi_provider.enabled():
            try:
                await _refresh_cache(db, category=category,
                                     limit=max(limit, 10),
                                     market=resolved_market)
                n_local = await db.news_articles.count_documents(local_q)
            except Exception as e:
                log.warning("[news] market warm-up failed for %s: %s",
                            resolved_market, e)
        if n_local > 0:
            out: list[dict] = []
            cur = db.news_articles.find(local_q).sort("pubDate", -1).limit(limit)
            async for r in cur:
                r.pop("_id", None)
                out.append(r)
            return {"count": len(out), "items": out,
                              "live": _live_flag(), "cached_at": _now_iso(),
                              "resolved_market": resolved_market,
                              "fallback_global": False}
        # No local hits — fall through to global with the flag set.
        fallback_global = True

    # If cache is cold, do a synchronous warm-up.  Otherwise read.
    n_cached = await db.news_articles.count_documents(q)
    if n_cached == 0:
        await _refresh_cache(db, category=category, limit=max(limit, 10))

    out: list[dict] = []
    cur = db.news_articles.find(q).sort("pubDate", -1).limit(limit)
    async for r in cur:
        r.pop("_id", None)
        out.append(r)
    return {"count": len(out), "items": out,
                      "live": _live_flag(), "cached_at": _now_iso(),
                      "resolved_market": resolved_market,
                      "fallback_global": fallback_global}


@router.get("/article/{news_id}")
async def get_article(news_id: str, request: Request):
    db = request.app.state.db
    a = await db.news_articles.find_one({"news_id": news_id})
    if not a:
        raise HTTPException(404, {"code": "not_found"})
    a.pop("_id", None)
    return a


@router.post("/_refresh")
async def refresh_now(request: Request,
                      category: Optional[str] = Query(default=None),
                      limit: int = Query(default=20, ge=1, le=50)):
    """Manual refresh — used by tests + admin debug. Idempotent."""
    db = request.app.state.db
    n = await _refresh_cache(db, category=category, limit=limit)
    return {"ok": True, "upserted": n, "live": _live_flag()}


async def ensure_news_indexes(db) -> None:
    try:
        await db.news_articles.create_index(
            "news_id", unique=True, name="news_articles_news_id_uniq")
        await db.news_articles.create_index(
            [("pubDate", -1)], name="news_articles_pubdate")
        await db.news_articles.create_index(
            [("categories", 1)], name="news_articles_category")
        # 7-day TTL on cached_at (ISO string stored, but pymongo accepts).
        log.info("[news] indexes ensured")
    except Exception as e:
        log.warning("[news] ensure indexes failed: %s", e)
