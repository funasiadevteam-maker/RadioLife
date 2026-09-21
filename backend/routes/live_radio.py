"""Phase 42-A — Live Radio consumer endpoints.

Public, anonymous-friendly surface that backs the new `/live-radio`
React experience.  Reads from the imported_radio_stations + channels
collections; never writes.

Endpoints (no auth required):
    GET  /api/live-radio/categories
    GET  /api/live-radio/stations?category=&language=&country=&q=&page=&limit=
    GET  /api/live-radio/stations/{station_id}
    GET  /api/live-radio/local?country=&city=&limit=
    GET  /api/live-radio/trending?window_hours=24&limit=20
    POST /api/live-radio/click/{station_id}     # fire-and-forget click ping

Ranking rule (per spec):
    1. FUUSIC AI-curated channels matching the category  (source="bigfm_ai")
    2. Claimed partner stations                                            (42-C — empty for now)
    3. Healthy imported stations by (votes desc, click_count desc)
    4. Other imported stations
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from core.content_language import (
    user_content_languages, user_show_all, user_filter_scopes,
    station_language_or_query,
)

from services.radio_browser_import import (
    CATEGORIES, send_click_track,
)
from services.station_art import resolve_art as _resolve_station_art
from auth import current_user_optional

logger = logging.getLogger("bigfm.live_radio.consumer")

router = APIRouter(prefix="/api/live-radio", tags=["live-radio"])

# Phase RELIABILITY.P2 — health filter.  By default the browse feed
# only surfaces stations that are `alive` (probed OK) or `unknown`
# (not yet probed — trusted until proven otherwise).  Admin callers
# can pass `include_dead=true` to see everything, e.g. for a health
# dashboard.
_HEALTH_FILTER_ALIVE_OR_UNKNOWN = {
    "stream_health_status": {"$in": ["alive", "unknown", None, "ok"]}
}


def _health_query(include_dead: bool) -> Dict[str, Any]:
    """Return the health-status portion of a Mongo query.  Empty dict
    when `include_dead=True` so the caller doesn't have to conditionally
    build the query."""
    if include_dead:
        return {}
    return dict(_HEALTH_FILTER_ALIVE_OR_UNKNOWN)


_AI_CHANNEL_TAG_MAP = {
    "bollywood":   {"bollywood", "filmi"},
    "punjabi":       {"punjabi", "punjabi_pop", "bhangra"},
    "hindi":           {"hindi"},
    "news":             {"news"},
    "talk":             {"talk"},
    "sports":         {"sports"},
    "devotional":  {"devotional", "bhajan", "sufi", "ghazal"},
    "pop":             {"pop"},
    "rock":           {"rock", "indie_rock"},
    "edm":             {"edm", "electronic", "house", "techno"},
    "classical":  {"classical"},
    "jazz":           {"jazz", "blues"},
}


def _iso(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v


def _strip_mongo(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {**d}
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def _ai_channel_to_card(ch: Dict[str, Any], category: Optional[str]) -> Dict[str, Any]:
    # Phase 42-D1 — canonical channel id is the slug (`_id`/`slug`), NOT
    # the display name.  Favicon prefers the DB-stamped `thumbnail_url`
    # (real AI artwork written by `services.channel_thumbnails`), then
    # the legacy `cover_image_url`, then a slug-based fallback path.
    slug = (ch.get("slug") or ch.get("_id") or ch.get("channel_id")
                  or ch.get("id") or ch.get("name") or "")
    return {
        "id": slug or ch.get("name"),
        "name": ch.get("name"),
        "source": "bigfm_ai",
        "is_ai_curated": True,
        "music_genre": ch.get("music_genre"),
        "category": category,
        "tags_json": ch.get("allowed_genres") or [],
        "favicon": (ch.get("thumbnail_url")
                              or ch.get("cover_image_url")
                              or (f"/api/static/channel_thumbnails/{slug}.webp"
                                      if slug else None)),
        "logo_url": ch.get("thumbnail_url") or ch.get("cover_image_url"),
        "country": None,
        "country_code": None,
        "language": None,
        "votes": None,
        "click_count": None,
        "stream_url": None,        # AI channels stream via the queue builder, not a raw URL
        "stream_health_status": "ok",
        "provider": "bigfm",
        # Phase FUN.1.1 — shape parity across all sources so downstream
        # UI never sees `undefined` on these fields.
        "is_flagship": False,
        "is_priority": False,
        "flagship_region": None,
        "flagship_priority": None,
    }


def _imported_to_card(s: Dict[str, Any]) -> Dict[str, Any]:
    art_url, art_source = _resolve_station_art(s)
    return {
        "id": s.get("id"),
        "external_station_uuid": s.get("external_station_uuid"),
        "name": s.get("name"),
        "source": "imported",
        "is_ai_curated": False,
        "tags_json": s.get("tags_json") or [],
        "music_genre": s.get("music_genre"),
        "favicon": art_url,
        "logo_url": s.get("logo_url") or art_url,
        "art": art_url,
        "art_source": art_source,
        "has_custom_art": art_source != "placeholder",
        "homepage": s.get("homepage"),
        "country": s.get("country"),
        "country_code": s.get("country_code"),
        "state": s.get("state"),
        "language": s.get("language"),
        "language_codes": s.get("language_codes") or [],
        "codec": s.get("codec"),
        "bitrate": s.get("bitrate"),
        "votes": s.get("votes"),
        "click_count": s.get("click_count"),
        "click_trend": s.get("click_trend"),
        "stream_url": s.get("url_resolved") or s.get("url"),
        "stream_health_status": s.get("stream_health_status", "unknown"),
        "provider": "radiobrowser",
        # Phase 42-C — surface claim metadata so the UI can render a
        # "Claimed by owner" badge and disable the Claim CTA on a
        # station that already has an owner.
        "claim_status": s.get("claim_status") or "unclaimed",
        "claim_badge_visible": bool(s.get("claim_badge_visible")),
        "owner_profile_id": s.get("owner_profile_id"),
        "owner_overrides": s.get("owner_overrides") or {},
        # Phase FUN.1.1 — flagship / priority projection so unified
        # browse + search cards can render the amber ring + PRIO pill.
        "is_flagship": bool(s.get("is_flagship")),
        "is_priority": bool(s.get("is_priority")),
        "flagship_region": s.get("flagship_region"),
        "flagship_priority": s.get("flagship_priority"),
        "needs_stream_review": bool(s.get("needs_stream_review")),
    }


# ─────────────────────── /categories ───────────────────────
@router.get("/categories",
                          description=(
                              "List of supported categories with imported + AI-curated "
                              "station counts.  Drives the Live Radio home page's chip "
                              "rows.  Anonymous."))
async def list_categories(request: Request):
    db = request.app.state.db
    out: List[Dict[str, Any]] = []
    for cat in CATEGORIES:
        slug = cat["slug"]
        # Imported station count via radio_station_categories.
        imp_ids = [r["station_id"] async for r in
                          db.radio_station_categories.find(
                              {"category": slug,
                                "source_provider": "radiobrowser"},
                              projection={"station_id": 1})]
        unique_imp = len(set(imp_ids))
        # FUUSIC AI channel count via genres.
        ai_tags = _AI_CHANNEL_TAG_MAP.get(slug, set())
        ai_count = 0
        if ai_tags:
            ai_count = await db.channels.count_documents({
                "active": True,
                "allowed_genres": {"$in": list(ai_tags)},
            })
        out.append({
            "slug": slug,
            "label": cat["label"],
            "count": unique_imp,
            "ai_curated_count": ai_count,
            "total": unique_imp + ai_count,
        })
    out.sort(key=lambda r: r["total"], reverse=True)
    return {"items": out, "count": len(out)}


# ─────────────────────── /stations  (browse / filter) ─────
@router.get("/stations",
                          description=(
                              "Paginated station list.  Ranking: FUUSIC AI matches first, "
                              "then healthy imported by (votes desc, click_count desc), "
                              "then other imported.  All filters are AND-combined."))
async def list_stations(
    request: Request,
    category: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    country: Optional[str] = Query(None,
                                  description="ISO country code, e.g. AE / US / GB."),
    q: Optional[str] = Query(None, description="Free-text search on station name."),
    show_all: bool = Query(False, description="Bypass the content-language filter."),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
    include_dead: bool = Query(
        False,
        description=("Admin/health-dashboard bypass — when true the "
                      "response includes stations flagged `dead` by "
                      "the probe worker.  Default false hides them.")),
):
    db = request.app.state.db
    cat_slug = (category or "").strip().lower() or None

    # ── FUUSIC AI tier ───────────────────────────────────────
    ai_cards: List[Dict[str, Any]] = []
    if cat_slug:
        ai_tags = _AI_CHANNEL_TAG_MAP.get(cat_slug, set())
        if ai_tags:
            ai_cur = db.channels.find({
                "active": True,
                "allowed_genres": {"$in": list(ai_tags)},
            })
            async for ch in ai_cur:
                ai_cards.append(_ai_channel_to_card(ch, cat_slug))

    # ── Imported tier ───────────────────────────────────────
    imp_query: Dict[str, Any] = {"active": True, **_health_query(include_dead)}
    if country:
        imp_query["country_code"] = country.upper()
    if language:
        imp_query["language"] = language.lower()
    if q:
        # Case-insensitive prefix-friendly match on name.
        imp_query["name"] = {"$regex": re.escape(q), "$options": "i"}
    if cat_slug:
        # Look up the station_ids tagged with this category, then filter.
        sid_cur = db.radio_station_categories.find(
            {"category": cat_slug, "source_provider": "radiobrowser"},
            projection={"station_id": 1})
        sids = list({r["station_id"] async for r in sid_cur})
        imp_query["id"] = {"$in": sids}

    # Content-language HARD filter — hide stations clearly in a non-preferred
    # language (neutral/unknown stay). Skipped when an explicit language filter
    # is supplied, the caller passes show_all, or the user opted into show-all.
    lang_prefs = None
    if not language and not show_all:
        _u = await current_user_optional(request)
        if not user_show_all(_u) and user_filter_scopes(_u).get("music"):
            lang_prefs = user_content_languages(_u)
            imp_query = {"$and": [imp_query, station_language_or_query(lang_prefs)]}

    skip = (page - 1) * limit
    sort_spec = [("stream_health_status", -1),    # "ok" sorts before "unknown" / "down"
                          ("votes", -1),
                          ("click_count", -1)]
    cur = db.imported_radio_stations.find(imp_query).sort(sort_spec)
    total = await db.imported_radio_stations.count_documents(imp_query)
    cur = cur.skip(skip).limit(limit)
    imp_cards = [_imported_to_card(s) async for s in cur]

    return {
        "items": ai_cards + imp_cards,
        "ai_count": len(ai_cards),
        "imported_count": len(imp_cards),
        "total": total + len(ai_cards),
        "page": page, "limit": limit,
        "filters": {"category": cat_slug, "language": language,
                              "country": (country or "").upper() or None, "q": q,
                              "content_languages": lang_prefs, "show_all": show_all},
    }


# ─────────────────────── /stations/{station_id} ────────────
@router.get("/stations/{station_id}",
                          description=(
                              "Station detail with similar-AI-channel suggestion when "
                              "the imported station maps to a category that FUUSIC has "
                              "an AI channel for."))
async def get_station(station_id: str, request: Request):
    db = request.app.state.db
    if station_id.startswith("imp_"):
        s = await db.imported_radio_stations.find_one({"id": station_id})
        if not s or not s.get("active"):
            raise HTTPException(404, {"code": "station_not_found"})
        # Find the strongest category and a matching AI channel.
        cat_row = await db.radio_station_categories.find_one(
            {"station_id": station_id,
              "source_provider": "radiobrowser"},
            sort=[("confidence_score", -1)])
        category = cat_row["category"] if cat_row else None
        ai_suggestion = None
        if category:
            ai_tags = _AI_CHANNEL_TAG_MAP.get(category, set())
            if ai_tags:
                ch = await db.channels.find_one({
                    "active": True,
                    "allowed_genres": {"$in": list(ai_tags)},
                })
                if ch:
                    ai_suggestion = _ai_channel_to_card(ch, category)
        # All categories for the chips on the detail page.
        all_cats = []
        async for r in db.radio_station_categories.find(
                {"station_id": station_id,
                  "source_provider": "radiobrowser"}).sort("confidence_score", -1):
            all_cats.append({"category": r["category"],
                                          "confidence_score": r["confidence_score"],
                                          "source": r["source"]})
        # Does the current viewer own/admin this station? Drives the
        # owner artwork controls on the detail page.
        viewer = await current_user_optional(request)
        viewer_is_owner = False
        if viewer:
            if viewer.get("role") == "admin" or s.get("owner_user_id") == viewer.get("user_id"):
                viewer_is_owner = True
            else:
                claim = await db.radio_station_claims.find_one({
                    "station_id": station_id,
                    "claimed_by_user_id": viewer["user_id"],
                    "claim_status": "approved"})
                viewer_is_owner = bool(claim)
        return {
            "station": _imported_to_card(s),
            "raw": _strip_mongo(s),
            "categories": all_cats,
            "similar_ai_channel": ai_suggestion,
            "claim_url_path": f"/claim/{station_id}",
            "viewer_is_owner": viewer_is_owner,
            "art_source": _imported_to_card(s).get("art_source"),
        }
    # AI-curated channel detail (graceful fallback).
    ch = await db.channels.find_one({"channel_id": station_id})
    if not ch:
        ch = await db.channels.find_one({"name": station_id})
    if not ch:
        raise HTTPException(404, {"code": "station_not_found"})
    return {
        "station": _ai_channel_to_card(ch, None),
        "raw": _strip_mongo(ch),
        "categories": [],
        "similar_ai_channel": None,
        "claim_url_path": None,
    }


# ─────────────────────── /local ────────────────────────────
@router.get("/local",
                          description=(
                              "Stations near the user's resolved location.  Strict "
                              "country match — fallback to country-only when city not "
                              "indexed (RB doesn't surface city)."))
async def local_stations(
    request: Request,
    country: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    include_dead: bool = Query(False),
):
    db = request.app.state.db
    if not country:
        return {"items": [], "count": 0,
                      "resolution_source": "no_country_supplied"}
    q: Dict[str, Any] = {"active": True,
                                          "country_code": country.upper(),
                                          **_health_query(include_dead)}
    cur = db.imported_radio_stations.find(q).sort(
        [("stream_health_status", -1), ("votes", -1)]).limit(limit)
    items = [_imported_to_card(s) async for s in cur]
    return {
        "items": items, "count": len(items),
        "resolution_source": "country" if items else "country_empty",
        "country": country.upper(),
        "city": city or None,
    }


# ─────────────────────── /trending ─────────────────────────
@router.get("/trending",
                          description=(
                              "Top click_trend stations within a recent window.  Uses "
                              "the Radio Browser-reported `click_trend` field as a "
                              "proxy — full session-level analytics is a later phase."))
async def trending_stations(
    request: Request,
    window_hours: int = Query(24, ge=1, le=168),
    limit: int = Query(20, ge=1, le=50),
    include_dead: bool = Query(False),
):
    db = request.app.state.db
    cur = db.imported_radio_stations.find(
        {"active": True, **_health_query(include_dead)}
    ).sort(
        [("click_trend", -1), ("votes", -1)]).limit(limit)
    items = [_imported_to_card(s) async for s in cur]
    return {"items": items, "count": len(items),
                  "window_hours": window_hours}


# ─────────────────────── /click/{station_id} ───────────────
@router.post("/click/{station_id}",
                            description=(
                                "Fire-and-forget click tracker — proxies through to "
                                "Radio Browser's `/json/url/{uuid}` etiquette endpoint "
                                "in a background task.  Always returns 200."))
async def click_station(station_id: str, request: Request,
                                              background_tasks: BackgroundTasks):
    db = request.app.state.db
    if station_id.startswith("imp_"):
        s = await db.imported_radio_stations.find_one({"id": station_id})
        if s and s.get("external_station_uuid"):
            background_tasks.add_task(send_click_track,
                                                              s["external_station_uuid"])
            # Reflect the click locally so our `click_count` mirrors RB.
            await db.imported_radio_stations.update_one(
                {"id": station_id},
                {"$inc": {"click_count": 1}})
    return {"ok": True, "station_id": station_id}
