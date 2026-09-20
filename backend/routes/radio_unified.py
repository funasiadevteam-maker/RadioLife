"""Phase 42-A2 — Unified Radio consumer endpoints.

Single source of truth for the merged Radio surface: BigFM AI channels +
Community radio stations + imported live stations all served through one
ranking/discovery/search pipeline.  The Phase 42-A `/api/live-radio/*`
routes remain mounted unchanged for backward-compat; the React app reads
exclusively from these new `/api/radio/*` endpoints.

Endpoints (no auth required unless noted):
    GET  /api/radio/discover                                — mega-response: 5+ rails in one call
    GET  /api/radio/browse?q=&category=&language=&country=&source=&page=&limit=
    GET  /api/radio/station/{station_id}            — works for imp_* / cmn_* / ai_*
    POST /api/radio/play/{station_id}                  — returns playback config

Source prefixes:
    imp_*  → imported_radio_stations  (Radio Browser tier)
    cmn_*  → community_radio_stations (user-created stations)
    ai_*   → channels                                          (BigFM AI-curated)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user_optional
from routes.live_radio import (
    _AI_CHANNEL_TAG_MAP, _ai_channel_to_card, _imported_to_card,
    _strip_mongo,
)
from services.radio_browser_import import CATEGORIES, send_click_track

logger = logging.getLogger("bigfm.radio_unified")

router = APIRouter(prefix="/api/radio", tags=["radio-unified"])


TOP_COUNTRIES = ["US", "GB", "DE", "FR", "IN", "RU", "IT", "ES",
                                "MX", "BR", "PL", "TR", "AE", "JP", "AR"]
TOP_LANGUAGES = ["english", "hindi", "spanish", "arabic", "german",
                                  "french", "russian", "italian"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _community_to_card(c: Dict[str, Any]) -> Dict[str, Any]:
    """Map a community_radio_stations row → unified card shape."""
    return {
        "id": (f"cmn_{c['station_id']}" if not str(c.get("station_id", "")).startswith("cmn_")
                      else c["station_id"]),
        "name": c.get("display_name") or c.get("name") or "Community Station",
        "source": "community",
        "is_ai_curated": False,
        "tags_json": c.get("genre_tags") or [],
        "favicon": c.get("cover_image_url") or c.get("artwork_url"),
        "logo_url": c.get("logo_url") or c.get("cover_image_url") or c.get("artwork_url"),
        "country": c.get("home_market") or "Community",
        "country_code": None,
        "language": None,
        "votes": c.get("follower_count") or 0,
        "click_count": c.get("listener_count") or 0,
        "stream_url": None,
        "stream_health_status": "ok",
        "provider": "bigfm_community",
        # Community-specific helpers for the play resolver.
        "share_id": c.get("share_id"),
        "channel_id": c.get("channel_id"),
        "owner_user_id": c.get("owner_user_id"),
        # Phase FUN.1.1 — flagship projection (community stations are
        # never flagship today, but shape parity keeps the browse card
        # renderer branch-free).
        "is_flagship": bool(c.get("is_flagship")),
        "is_priority": bool(c.get("is_priority")),
        "flagship_region": c.get("flagship_region"),
        "flagship_priority": c.get("flagship_priority"),
    }


async def _imported_top_n(db, n: int, *,
                                                          q: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"active": True}
    if q:
        query.update(q)
    out: List[Dict[str, Any]] = []
    cur = db.imported_radio_stations.find(query) \
                  .sort([("votes", -1), ("click_count", -1)]).limit(n)
    async for s in cur:
        out.append(_imported_to_card(s))
    return out


async def _ai_top_n(db, n: int, *,
                                            allowed_genres: Optional[List[str]] = None,
                                            ) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"active": True}
    if allowed_genres:
        query["allowed_genres"] = {"$in": allowed_genres}
    out: List[Dict[str, Any]] = []
    async for ch in db.channels.find(query).limit(n):
        out.append(_ai_channel_to_card(ch, None))
    return out


async def _community_top_n(db, n: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    # Community stations use `status: "published"` (not a boolean
    # `is_published` flag).  Match the canonical field so the rail
    # populates from the 13+ already-published stations.
    async for c in db.community_radio_stations.find(
            {"status": "published"}).sort("follower_count", -1).limit(n):
        out.append(_community_to_card(c))
    return out


async def _trending_imported(db, hours: int, n: int) -> List[Dict[str, Any]]:
    # Lightweight: aggregate recent clicks on imp_ ids from
    # `live_radio_station_clicks` (Phase 42-A) and join.
    cutoff = _now() - timedelta(hours=hours)
    top_ids: List[str] = []
    try:
        cur = db.live_radio_station_clicks.aggregate([
            {"$match": {"clicked_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$station_id", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": n},
        ])
        async for r in cur:
            top_ids.append(r["_id"])
    except Exception:
        pass
    if not top_ids:
        # Cold fallback — just the top voted globally.
        return await _imported_top_n(db, n)
    out: List[Dict[str, Any]] = []
    async for s in db.imported_radio_stations.find(
            {"id": {"$in": top_ids}, "active": True}):
        out.append(_imported_to_card(s))
    # Preserve trending order.
    order = {sid: i for i, sid in enumerate(top_ids)}
    out.sort(key=lambda r: order.get(r["id"], 999))
    return out


# ─────────────────────── /discover ───────────────────────
@router.get("/discover",
                          description=(
                              "Mega-response for the unified Radio home.  One request, "
                              "8+ rails: For You (auth-only), AI-Curated, Community, "
                              "Local, Trending, By-Language / By-Genre / By-Country "
                              "facet chips.  Anonymous-friendly (For You hidden when "
                              "no user)."))
async def discover(request: Request,
                                    country: Optional[str] = Query(None),
                                    city: Optional[str] = Query(None),
                                    user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    rails: List[Dict[str, Any]] = []

    # 1. For You (auth-only, simple v1 = recent stations played).
    if user:
        recent_ids: List[str] = []
        try:
            cur = db.live_radio_station_clicks.find(
                {"user_id": user["user_id"]}).sort("clicked_at", -1).limit(20)
            seen = set()
            async for r in cur:
                sid = r.get("station_id")
                if sid and sid not in seen:
                    seen.add(sid)
                    recent_ids.append(sid)
                if len(recent_ids) >= 12:
                    break
        except Exception:
            pass
        for_you: List[Dict[str, Any]] = []
        if recent_ids:
            order = {sid: i for i, sid in enumerate(recent_ids)}
            async for s in db.imported_radio_stations.find(
                    {"id": {"$in": recent_ids}, "active": True}):
                for_you.append(_imported_to_card(s))
            for_you.sort(key=lambda r: order.get(r["id"], 999))
        # Fill remaining slots with AI suggestions tuned to user's
        # preferred genres.
        if len(for_you) < 12:
            prefs = (user.get("preferences") or {}).get("genres") or []
            fill_ai = await _ai_top_n(db, 12 - len(for_you),
                                                                      allowed_genres=prefs)
            for_you.extend(fill_ai)
        rails.append({"id": "for_you", "title": "For You",
                                  "stations": for_you[:12]})

    # 2. AI-Curated rail.
    ai_cards = await _ai_top_n(db, 12)
    rails.append({"id": "ai_curated", "title": "FUUSIC AI-Curated",
                              "stations": ai_cards})

    # 3. Community.
    comm_cards = await _community_top_n(db, 12)
    rails.append({"id": "community",
                              "title": "Community & Creator Stations",
                              "stations": comm_cards})

    # 4. Local — uses passed country/city or user's resolved geo.
    local_country = (country or "").upper()
    if not local_country and user:
        local_country = (user.get("country") or "").upper()
    local_cards: List[Dict[str, Any]] = []
    local_source = "global_fallback"
    if local_country:
        local_cards = await _imported_top_n(db, 12,
                                                                                          q={"country_code": local_country})
        if local_cards:
            local_source = "country"
    if not local_cards:
        local_cards = await _imported_top_n(db, 12)
    rails.append({"id": "local",
                              "title": f"Local Live Radio · {local_country or 'Global'}",
                              "stations": local_cards,
                              "resolution_source": local_source,
                              "country": local_country})

    # 5. Trending now.
    trending = await _trending_imported(db, hours=24, n=16)
    rails.append({"id": "trending", "title": "Trending Now",
                              "stations": trending})

    # 6. By-Language facet chips (counts).
    lang_chips: List[Dict[str, Any]] = []
    for lang in TOP_LANGUAGES:
        c = await db.imported_radio_stations.count_documents(
            {"active": True, "language": lang})
        if c > 0:
            lang_chips.append({"slug": lang,
                                                          "label": lang.capitalize(),
                                                          "count": c})
    rails.append({"id": "languages", "title": "By Language",
                              "facet_chips": lang_chips})

    # 7. By-Genre facet chips (from CATEGORIES).
    genre_chips: List[Dict[str, Any]] = []
    for cat in CATEGORIES:
        slug = cat["slug"]
        c = len({r["station_id"] async for r in
                          db.radio_station_categories.find(
                              {"category": slug, "source_provider": "radiobrowser"},
                              projection={"station_id": 1})})
        if c > 0:
            genre_chips.append({"slug": slug, "label": cat["label"], "count": c})
    genre_chips.sort(key=lambda r: r["count"], reverse=True)
    rails.append({"id": "genres", "title": "By Genre",
                              "facet_chips": genre_chips[:12]})

    # 8. By-Country facet chips (top 15 by station count).
    country_chips: List[Dict[str, Any]] = []
    cur = db.imported_radio_stations.aggregate([
        {"$match": {"active": True, "country_code": {"$ne": None}}},
        {"$group": {"_id": "$country_code", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 15},
    ])
    async for r in cur:
        country_chips.append({"slug": r["_id"], "label": r["_id"],
                                                      "count": r["n"]})
    rails.append({"id": "countries", "title": "By Country",
                              "facet_chips": country_chips})

    return {"rails": rails,
                  "rail_count": len(rails),
                  "user_authed": bool(user)}


# ─────────────────── Language-group filter ───────────────────
# Chip groups for the Browse language selector (English · Hindi ·
# Indian Languages · News). Robust grouping over the messy free-text
# `language` field + `language_codes` + country / news signals.
_LANG_GROUP_INDIAN_REGEX = (
    "hindi|punjabi|tamil|telugu|bengali|bangla|marathi|gujarati|kannada|"
    "malayalam|urdu|bhojpuri|odia|oriya|assamese|konkani|sindhi|maithili|"
    "kashmiri|dogri|manipuri|santali|nepali|tulu|rajasthani|haryanvi|awadhi|"
    "sanskrit")
_LANG_GROUP_INDIAN_CODES = ["hi", "pa", "ta", "te", "bn", "mr", "gu", "kn",
                            "ml", "ur", "or", "as", "ne", "sd", "ks", "sa",
                            "kok", "mni", "sat", "bho", "asm", "ori"]


def _lang_group_query(group: Optional[str]) -> Optional[Dict[str, Any]]:
    g = (group or "").strip().lower()
    if g in ("", "all"):
        return None
    if g == "english":
        return {"$or": [{"language": {"$regex": "english", "$options": "i"}},
                        {"language_codes": {"$in": ["en", "english"]}}]}
    if g == "hindi":
        return {"$or": [{"language": {"$regex": "hindi", "$options": "i"}},
                        {"language_codes": {"$in": ["hi", "hindi"]}}]}
    if g == "indian":
        return {"$or": [{"language": {"$regex": _LANG_GROUP_INDIAN_REGEX, "$options": "i"}},
                        {"language_codes": {"$in": _LANG_GROUP_INDIAN_CODES}},
                        {"country_code": "IN"}]}
    if g == "news":
        return {"$or": [{"tags_json": "news"},
                        {"name": {"$regex": "news", "$options": "i"}},
                        {"music_genre": {"$regex": "news", "$options": "i"}}]}
    return None


def _merge_lang_group(base: Dict[str, Any], lang_group: Optional[str]) -> None:
    """Fold a lang-group clause into a browse query without clobbering the
    active/flagship `$or` gate."""
    lg = _lang_group_query(lang_group)
    if not lg:
        return
    if "$and" in base:
        base["$and"].append(lg)
    else:
        active_or = base.pop("$or", None)
        base["$and"] = []
        if active_or:
            base["$and"].append({"$or": active_or})
        base["$and"].append(lg)


# ─────────────────────── /browse ───────────────────────
async def _browse_imported_fast(db, request, q, cat_slug, language, country,
                                page: int, limit: int, user, genre=None, sort="popular",
                                lang_group=None):
    """DB-paginated imported-only browse. Flagships first, then votes/clicks."""
    station_ids = None
    if cat_slug:
        ids = [r["station_id"] async for r in
               db.radio_station_categories.find(
                   {"category": cat_slug, "source_provider": "radiobrowser"},
                   projection={"station_id": 1})]
        station_ids = list(set(ids)) or ["__none__"]
    base = {"$or": [{"active": True}, {"is_flagship": True}], "dubai_hidden": {"$ne": True}}
    if station_ids is not None:
        base["id"] = {"$in": station_ids}
    if language:
        base["language"] = language.lower()
    if country:
        base["country_code"] = country.upper()
    if genre:
        base["music_genre"] = {"$regex": f"^{re.escape(genre)}$", "$options": "i"}
    if q:
        search_or = [
            {"name": {"$regex": re.escape(q), "$options": "i"}},
            {"tags_json": q.lower()},
            {"country": {"$regex": re.escape(q), "$options": "i"}},
            {"flagship_categories": {"$in": [q.lower()]}},
            {"flagship_search_terms": {"$in": [q.lower()]}},
        ]
        active_or = base.pop("$or")
        base["$and"] = [{"$or": active_or}, {"$or": search_or}]
    _merge_lang_group(base, lang_group)
    total = await db.imported_radio_stations.count_documents(base)
    skip = (page - 1) * limit
    cards: List[Dict[str, Any]] = []
    sort_map = {
        "popular": [("is_flagship", -1), ("votes", -1), ("click_count", -1)],
        "az": [("name", 1)],
        "newest": [("imported_at", -1), ("is_flagship", -1)],
    }
    sort_spec = sort_map.get((sort or "popular").lower(), sort_map["popular"])
    cur = db.imported_radio_stations.find(base).sort(sort_spec).skip(skip).limit(limit)
    async for s in cur:
        cards.append(_imported_to_card(s))
    return {
        "items": cards, "total": total, "page": page, "limit": limit,
        "counts_by_source": {"bigfm_ai": 0, "community": 0, "imported": total},
        "filters_applied": {"q": q, "category": cat_slug,
                            "language": language, "country": country, "source": "imported"},
    }


@router.get("/genres", description="Distinct music genres available for filtering the browse grid.")
async def list_genres(request: Request):
    db = request.app.state.db
    genres = set()
    for g in await db.channels.distinct("music_genre", {"active": True}):
        if g:
            genres.add(g)
    for g in await db.imported_radio_stations.distinct(
            "music_genre", {"active": True, "dubai_hidden": {"$ne": True}}):
        if g:
            genres.add(g)
    return {"genres": sorted(genres)}


@router.get("/browse",
                          description=(
                              "Unified search/filter grid across AI + community + "
                              "imported sources.  `source` ∈ "
                              "{bigfm_ai, community, imported, all}.  AI tiles "
                              "always rank first when included.  Search `q` matches "
                              "name + tags + country."))
async def browse(
    request: Request,
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    source: str = Query("all"),
    sort: str = Query("popular"),
    lang_group: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
    user: Optional[dict] = Depends(current_user_optional),
):
    db = request.app.state.db
    sources = set()
    if source == "all":
        sources = {"bigfm_ai", "community", "imported"}
    else:
        sources = {s.strip() for s in source.split(",") if s.strip()}
    ai_cards: List[Dict[str, Any]] = []
    comm_cards: List[Dict[str, Any]] = []
    imp_cards: List[Dict[str, Any]] = []
    cat_slug = (category or "").strip().lower() or None

    # Phase MKT.2 — fast DB-level pagination for the imported-only directory
    # (the mobile Stations screen browses `source=imported`).  Avoids the
    # in-memory 2000-doc materialize+merge so the 40K+ directory stays fast
    # and paginates correctly past page ~66.
    if sources == {"imported"}:
        return await _browse_imported_fast(
            db, request, q, cat_slug, language, country, page, limit, user, genre, sort,
            lang_group=lang_group)

    # AI tier.
    if "bigfm_ai" in sources:
        ai_q: Dict[str, Any] = {"active": True}
        if cat_slug:
            tags = _AI_CHANNEL_TAG_MAP.get(cat_slug, set())
            if tags:
                ai_q["allowed_genres"] = {"$in": list(tags)}
        if q:
            ai_q["name"] = {"$regex": re.escape(q), "$options": "i"}
        if genre:
            ai_q["music_genre"] = {"$regex": f"^{re.escape(genre)}$", "$options": "i"}
        async for ch in db.channels.find(ai_q).limit(100):
            ai_cards.append(_ai_channel_to_card(ch, cat_slug))

    # Community tier.
    if "community" in sources:
        cm_q: Dict[str, Any] = {"status": "published"}
        if q:
            cm_q["display_name"] = {"$regex": re.escape(q), "$options": "i"}
        async for c in db.community_radio_stations.find(cm_q) \
                          .sort("follower_count", -1).limit(50):
            comm_cards.append(_community_to_card(c))

    # Imported tier — categorized + filtered.
    if "imported" in sources:
        # Category filter via radio_station_categories.
        station_ids: Optional[List[str]] = None
        if cat_slug:
            ids = [r["station_id"] async for r in
                      db.radio_station_categories.find(
                          {"category": cat_slug,
                            "source_provider": "radiobrowser"},
                          projection={"station_id": 1})]
            station_ids = list(set(ids))
            if not station_ids:
                station_ids = ["__none__"]
        imp_q: Dict[str, Any] = {"dubai_hidden": {"$ne": True}, "$or": [
            {"active": True},
            {"is_flagship": True},   # Phase FUN.1.1 — always surface flagships
        ]}
        if genre:
            imp_q["music_genre"] = {"$regex": f"^{re.escape(genre)}$", "$options": "i"}
        if station_ids is not None:
            imp_q["id"] = {"$in": station_ids}
        if language:
            imp_q["language"] = language.lower()
        if country:
            imp_q["country_code"] = country.upper()
        if q:
            # Phase FUN.1.1 — search `$or` clauses combined via `$and`
            # so the active-or-flagship gate above still applies.
            search_or = [
                {"name": {"$regex": re.escape(q), "$options": "i"}},
                {"tags_json": q.lower()},
                {"country": {"$regex": re.escape(q), "$options": "i"}},
                # Also surface flagships when searching by their curated
                # category / search-term arrays (e.g. "talk", "bollywood").
                {"flagship_categories":      {"$in": [q.lower()]}},
                {"flagship_search_terms":  {"$in": [q.lower()]}},
            ]
            active_or = imp_q.pop("$or")
            imp_q["$and"] = [{"$or": active_or}, {"$or": search_or}]
        _merge_lang_group(imp_q, lang_group)
        async for s in db.imported_radio_stations.find(imp_q) \
                          .sort([("votes", -1), ("click_count", -1)]).limit(2000):
            imp_cards.append(_imported_to_card(s))

        # Phase FUN.1.1 — the initial 2000-doc slice is votes-DESC and
        # excludes flagships (they carry `votes: None`).  Fetch flagship
        # docs separately and merge so the region-aware sort below has
        # them to promote to the top.  Skip when a filter narrows the
        # result set (category / language / country / q) — those queries
        # already include flagship-friendly branches above.
        seen_ids = {c["id"] for c in imp_cards}
        flag_q: Dict[str, Any] = {"is_flagship": True, "dubai_hidden": {"$ne": True}}
        if q:
            flag_q["$or"] = [
                {"name":                                {"$regex": re.escape(q), "$options": "i"}},
                {"flagship_categories":       {"$in": [q.lower()]}},
                {"flagship_search_terms":  {"$in": [q.lower()]}},
                {"language_codes":              {"$in": [q.lower()]}},
            ]
        if language:
            flag_q["language_codes"] = {"$in": [language.lower()]}
        if country:
            # Country filter matches EITHER the station country_code OR
            # the flagship_region (AE flagships have `country_code` set;
            # US flagships likewise).
            flag_q["$or" if "$or" not in flag_q else "$and"] = (
                [{"country_code": country.upper()},
                  {"flagship_region": country.upper()}]
                if "$or" not in flag_q else
                [{"$or": flag_q.pop("$or")},
                  {"$or": [{"country_code": country.upper()},
                                    {"flagship_region": country.upper()}]}])
        async for s in db.imported_radio_stations.find(flag_q).limit(50):
            if s.get("id") in seen_ids:
                continue
            seen_ids.add(s.get("id"))
            imp_cards.append(_imported_to_card(s))

    # Phase FUN.1.1 — region-aware flagship + priority sort applied to
    # the merged result set so browse/search surfaces flagship stations
    # (Talk 100.3 UAE, Big FM 106.2, …) and priority Dubai stations
    # BEFORE the AI + community + generic imported tiers on page 1.
    from services.geo_flagship import (
        get_user_region, sort_with_flagship_priority)
    user_region = await get_user_region(user, request)

    # Merge: flagships/priority rank first (via stable sort), then the
    # remaining ordering preserves upstream: AI → community → imported.
    merged = ai_cards + comm_cards + imp_cards
    merged = sort_with_flagship_priority(merged, user_region)
    total = len(merged)
    skip = (page - 1) * limit
    page_items = merged[skip:skip + limit]
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "limit": limit,
        "counts_by_source": {
            "bigfm_ai": len(ai_cards),
            "community": len(comm_cards),
            "imported": len(imp_cards),
        },
        "filters_applied": {"q": q, "category": cat_slug,
                                                    "language": language, "country": country,
                                                    "source": source},
        "user_region": user_region,
    }


# ─────────────────────── /station/{id} ───────────────────────
@router.get("/station/{station_id}",
                          description=(
                              "Cross-source station detail.  Resolves by id prefix: "
                              "`imp_*` (imported) / `cmn_*` (community) / anything "
                              "else (BigFM AI channel)."))
async def station_detail(station_id: str, request: Request,
                                                user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    if station_id.startswith("imp_"):
        s = await db.imported_radio_stations.find_one({"id": station_id})
        if not s:
            raise HTTPException(404, {"code": "station_not_found"})
        cats: List[Dict[str, Any]] = []
        async for r in db.radio_station_categories.find(
                {"station_id": station_id,
                  "source_provider": "radiobrowser"}):
            cats.append({"category": r["category"],
                                          "confidence_score": r["confidence_score"]})
        return {"station": _imported_to_card(s),
                      "source": "imported",
                      "categories": cats}
    if station_id.startswith("cmn_"):
        raw_id = station_id[4:]
        c = await db.community_radio_stations.find_one(
            {"$or": [{"station_id": raw_id},
                              {"station_id": station_id},
                              {"share_id": raw_id}]})
        if not c:
            raise HTTPException(404, {"code": "station_not_found"})
        return {"station": _community_to_card(c),
                      "source": "community",
                      "owner": c.get("owner_user_id"),
                      "description": c.get("description")}
    # AI channel.
    ch = await db.channels.find_one(
        {"$or": [{"channel_id": station_id}, {"id": station_id},
                          {"slug": station_id}, {"name": station_id}]})
    if not ch:
        raise HTTPException(404, {"code": "station_not_found"})
    return {"station": _ai_channel_to_card(ch, None),
                  "source": "bigfm_ai",
                  "description": ch.get("description")}


# ─────────────────────── /play/{id} ───────────────────────
@router.post("/play/{station_id}",
                          description=(
                              "Returns playback config for ANY source.  Imported → "
                              "`{mode: 'imported', stream_url, ...}`.  AI → "
                              "`{mode: 'ai', channel_slug: ..., ...}` (client invokes "
                              "the existing /api/radio/start flow).  Community → "
                              "`{mode: 'community', share_id, channel_id, ...}`. "
                              "Also fires the per-source click ping."))
async def play(station_id: str, request: Request,
                            user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    now = _now()
    if station_id.startswith("imp_"):
        s = await db.imported_radio_stations.find_one({"id": station_id})
        if not s or not s.get("active"):
            raise HTTPException(404, {"code": "station_not_found"})
        # Click ping (same shape as /api/live-radio/click/{id}).
        try:
            await db.live_radio_station_clicks.insert_one({
                "_id": f"clk_{now.timestamp() * 1000:.0f}",
                "station_id": station_id,
                "user_id": user["user_id"] if user else None,
                "clicked_at": now,
            })
            await db.imported_radio_stations.update_one(
                {"id": station_id}, {"$inc": {"click_count": 1}})
            if s.get("external_station_uuid"):
                import asyncio as _aio
                _aio.create_task(send_click_track(s["external_station_uuid"]))
        except Exception:
            pass
        return {
            "mode": "imported",
            "station_id": station_id,
            "stream_url": s.get("url_resolved") or s.get("url"),
            "name": s.get("name"),
            "favicon": s.get("favicon"),
            "country": s.get("country"),
            "language": s.get("language"),
            "bitrate": s.get("bitrate"),
            "codec": s.get("codec"),
        }
    if station_id.startswith("cmn_"):
        raw_id = station_id[4:]
        c = await db.community_radio_stations.find_one(
            {"$or": [{"station_id": raw_id},
                              {"station_id": station_id},
                              {"share_id": raw_id}]})
        if not c:
            raise HTTPException(404, {"code": "station_not_found"})
        return {
            "mode": "community",
            "station_id": station_id,
            "share_id": c.get("share_id"),
            "channel_id": c.get("channel_id"),
            "name": c.get("display_name"),
            "spa_url": f"/r/{c.get('share_id')}",
        }
    # AI channel — resolve by slug, channel_id, id, OR name (the
    # `_ai_channel_to_card` helper falls back to `name` when no slug
    # is present, so anywhere the discover/browse endpoint surfaced
    # an AI tile, the tile id may be the human name).
    ch = await db.channels.find_one(
        {"$or": [{"channel_id": station_id}, {"id": station_id},
                          {"slug": station_id}, {"name": station_id}]})
    if not ch:
        raise HTTPException(404, {"code": "station_not_found"})
    slug = (ch.get("slug") or ch.get("channel_id")
                  or ch.get("id") or station_id)
    return {
        "mode": "ai",
        "station_id": station_id,
        "channel_slug": slug,
        "name": ch.get("name"),
        "spa_url": f"/radio?ch={slug}&autoplay=1",
    }
