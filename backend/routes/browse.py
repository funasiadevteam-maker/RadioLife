"""Unified Browse aggregator for the web experience.

One payload -> three skins (Cinematic / Studio / Tube). Pulls existing content
(flagship "Originals", live stations, podcasts, games, deals) plus a light
personalized "Recommended for you" rail from the caller's play history.
Every rail is built defensively so a missing collection never breaks Browse.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request

from services.flagship_station_service import list_flagships

router = APIRouter(prefix="/api/browse", tags=["browse"])
log = logging.getLogger("bigfm.browse")


def _card(cid, ctype, title, subtitle, image, href, badge=None, slug=None):
    return {"id": cid, "type": ctype, "title": title or "Untitled",
            "subtitle": subtitle or "", "image": image or None,
            "href": href, "badge": badge, "slug": slug}


def _img(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


async def _stations(db, n: int) -> list[dict]:
    out = []
    try:
        async for c in db.channels.find({"active": True}).limit(n):
            slug = c.get("slug")
            out.append(_card(
                slug or str(c.get("id") or c.get("_id")), "station",
                c.get("display_name") or c.get("name") or "Station",
                c.get("tagline") or c.get("genre") or "Live radio",
                _img(c, "thumbnail_url", "logo_url", "artwork_url", "cover_image_url"),
                f"/radio?ch={slug}" if slug else "/radio", "LIVE", slug))
    except Exception as e:
        log.warning("browse._stations: %s", e)
    return out


async def _originals(db, n: int) -> list[dict]:
    out = []
    try:
        for f in await list_flagships(db, limit=n):
            slug = f.get("flagship_slug") or f.get("slug")
            cats = f.get("flagship_categories") or []
            out.append(_card(
                f.get("id") or slug, "original",
                f.get("name") or "RadioLife Original",
                (cats[0].title() if cats else "RadioLife Original"),
                _img(f, "favicon", "logo_url", "image", "artwork_url", "image_url"),
                f"/radio?ch={slug}" if slug else "/radio", "ORIGINAL", slug))
    except Exception as e:
        log.warning("browse._originals: %s", e)
    return out


async def _podcasts(db, n: int) -> list[dict]:
    out = []
    try:
        async for p in db.podcast_channels.find({}).limit(n):
            out.append(_card(
                p.get("id"), "podcast",
                p.get("title") or p.get("name") or "Podcast",
                p.get("category") or p.get("author") or "Podcast",
                _img(p, "cover_image_url", "artwork_url", "image_url", "logo_url"),
                "/podcasts", "PODCAST", p.get("slug")))
    except Exception as e:
        log.warning("browse._podcasts: %s", e)
    return out


async def _games(db, n: int) -> list[dict]:
    out = []
    try:
        cur = db.game_campaigns.find({"status": {"$in": ["active", "live", "published"]}}).limit(n)
        async for g in cur:
            out.append(_card(
                g.get("campaign_id") or g.get("id"), "game",
                g.get("title") or g.get("name") or "Play & Win",
                g.get("subtitle") or g.get("tagline") or "Play & Win",
                _img(g, "hero_image_url", "cover_image_url", "image_url", "thumbnail_url"),
                "/play", "GAME", g.get("slug")))
    except Exception as e:
        log.warning("browse._games: %s", e)
    return out


async def _deals(db, n: int) -> list[dict]:
    out = []
    try:
        async for m in db.marketplace_profiles.find({}).limit(n):
            slug = m.get("slug")
            out.append(_card(
                m.get("business_id"), "deal",
                m.get("public_name") or m.get("name") or "Local spot",
                m.get("category") or "Nearby deal",
                _img(m, "logo_url", "cover_url", "cover_image_url", "image_url"),
                f"/business/{slug}" if slug else "/shop", "DEAL", slug))
    except Exception as e:
        log.warning("browse._deals: %s", e)
    return out


async def _recommended(db, user: Optional[dict], n: int) -> list[dict]:
    ids: list[str] = []
    if user:
        seen: list[str] = []
        try:
            async for pl in db.playback_logs.find(
                    {"user_id": user.get("user_id")}).sort("_id", -1).limit(50):
                sid = pl.get("channel_id") or pl.get("station_id") or pl.get("slug")
                if sid and sid not in seen:
                    seen.append(sid)
        except Exception:
            pass
        ids = seen[:n]
    cards: list[dict] = []
    picked = set()
    if ids:
        try:
            q = {"$or": [{"slug": {"$in": ids}}, {"channel_id": {"$in": ids}}, {"id": {"$in": ids}}]}
            async for c in db.channels.find(q).limit(n):
                slug = c.get("slug")
                picked.add(slug)
                cards.append(_card(slug or str(c.get("id")), "station",
                             c.get("display_name") or c.get("name") or "Station",
                             "Because you listened",
                             _img(c, "thumbnail_url", "logo_url", "artwork_url"),
                             f"/radio?ch={slug}" if slug else "/radio", "FOR YOU", slug))
        except Exception:
            pass
    if len(cards) < n:  # fill with popular
        for s in await _stations(db, n * 2):
            if s.get("slug") in picked:
                continue
            s = dict(s)
            s["subtitle"] = "Popular near you"
            s["badge"] = "FOR YOU"
            cards.append(s)
            if len(cards) >= n:
                break
    return cards


@router.get("/home")
async def browse_home(request: Request):
    db = request.app.state.db
    try:
        from auth import current_user_optional
        user = await current_user_optional(request)
    except Exception:
        user = None

    originals = await _originals(db, 12)
    stations = await _stations(db, 18)
    recommended = await _recommended(db, user, 12)
    podcasts = await _podcasts(db, 18)
    games = await _games(db, 12)
    deals = await _deals(db, 12)

    hero_src = originals or stations or recommended
    hero = None
    if hero_src:
        h = hero_src[0]
        hero = {**h, "tagline": "Stream live radio, shows, games and deals — all in one place."}

    rails = [
        {"key": "originals", "title": "RadioLife Originals", "accent": True, "items": originals},
        {"key": "recommended", "title": "Recommended for You", "items": recommended},
        {"key": "stations", "title": "Live Stations", "items": stations},
        {"key": "podcasts", "title": "Podcasts & Shows", "items": podcasts},
        {"key": "games", "title": "Play & Win", "items": games},
        {"key": "deals", "title": "Deals Near You", "items": deals},
    ]
    rails = [r for r in rails if r["items"]]
    return {"hero": hero, "rails": rails,
            "user": {"name": (user or {}).get("display_name") or (user or {}).get("name")} if user else None}


__all__ = ["router"]
