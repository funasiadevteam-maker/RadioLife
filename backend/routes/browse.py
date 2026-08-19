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


def _price(cents, currency) -> Optional[str]:
    if not cents:
        return None
    sym = {"usd": "$", "aed": "AED ", "inr": "₹", "eur": "€", "gbp": "£"}.get(
        (currency or "usd").lower(), (currency or "").upper() + " ")
    return f"{sym}{int(cents) / 100:.2f}"


async def _shop_products(db, n: int) -> list[dict]:
    out = []
    try:
        prods = [p async for p in db.products.find({"active": True}).limit(n * 2)]
        if not prods:
            prods = [p async for p in db.products.find({}).limit(n * 2)]
        biz_ids = list({p.get("business_id") for p in prods if p.get("business_id")})
        binfo: dict = {}
        if biz_ids:
            async for b in db.marketplace_profiles.find({"business_id": {"$in": biz_ids}}):
                cov = b.get("cover_urls") or []
                img = ((cov[0] if isinstance(cov, list) and cov else None)
                       or b.get("logo_url") or b.get("cover_url") or b.get("cover_image_url"))
                binfo[b.get("business_id")] = {"img": img, "slug": b.get("slug"),
                                               "name": b.get("public_name") or b.get("name")}
        for p in prods[:n]:
            bi = binfo.get(p.get("business_id"), {})
            slug = bi.get("slug")
            card = _card(p.get("product_id") or p.get("id"), "shop",
                         p.get("title") or "Product", bi.get("name") or "RadioLife Shop",
                         bi.get("img"), f"/business/{slug}" if slug else "/shop", "SHOP", slug)
            card["price"] = _price(p.get("price_cents"), p.get("currency"))
            out.append(card)
    except Exception as e:
        log.warning("browse._shop_products: %s", e)
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
    shop = await _shop_products(db, 12)

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
        {"key": "shop", "title": "Shop on RadioLife", "items": shop},
        {"key": "deals", "title": "Deals Near You", "items": deals},
    ]
    rails = [r for r in rails if r["items"]]
    return {"hero": hero, "rails": rails,
            "user": {"name": (user or {}).get("display_name") or (user or {}).get("name")} if user else None}


def _dedup(cards: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for c in cards:
        k = (c.get("type"), c.get("id") or c.get("title"))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def _rot(lst: list, offset: int, count: int) -> list:
    if not lst:
        return []
    return [lst[(offset + i) % len(lst)] for i in range(count)]


async def _feed_pools(db, user: Optional[dict]) -> dict:
    originals = await _originals(db, 12)
    stations = await _stations(db, 24)
    recommended = await _recommended(db, user, 12)
    podcasts = await _podcasts(db, 24)
    games = await _games(db, 16)
    shop = await _shop_products(db, 20)
    deals = await _deals(db, 16)
    shoppool = list(shop)
    for d in deals:  # top up the shop pool with local businesses as shop cards
        d = dict(d)
        d["type"] = "shop"
        d["badge"] = "SHOP"
        shoppool.append(d)
    videos = _dedup(originals + recommended + stations + podcasts)
    shorts = [{**v, "type": "short", "badge": None}
              for v in _dedup(recommended + stations + originals + podcasts)][:18]
    return {"videos": videos, "games": games, "shop": _dedup(shoppool), "shorts": shorts}


@router.get("/feed")
async def browse_feed(request: Request, page: int = 0, cat: str = "all"):
    """Endless YouTube-style feed: mixed grid + rotating shelves (shorts,
    playables/games, shop) with shop products sprinkled through the grid.
    Recycles a finite catalog so it never ends (has_more stays true)."""
    db = request.app.state.db
    try:
        from auth import current_user_optional
        user = await current_user_optional(request)
    except Exception:
        user = None
    pools = await _feed_pools(db, user)
    videos, games = pools["videos"], pools["games"]
    shop, shorts = pools["shop"], pools["shorts"]
    blocks: list[dict] = []

    if cat == "shopping":
        blocks.append({"kind": "grid", "items": _rot(shop, page * 12, 12)})
        if page % 2 == 0 and shop:
            blocks.append({"kind": "shelf", "variant": "shop",
                           "title": "Trending in Shop", "items": _rot(shop, page * 6 + 3, 10)})
        has_more = bool(shop)
    elif cat == "games":
        blocks.append({"kind": "shelf", "variant": "playables",
                       "title": "Play & Win — instant games", "items": _rot(games, page * 8, min(10, max(1, len(games))))})
        blocks.append({"kind": "grid", "items": _rot(games, page * 8, 8)})
        has_more = bool(games)
    elif cat != "all":
        typ = {"originals": "original", "stations": "station",
               "podcasts": "podcast"}.get(cat)
        pool = [v for v in videos if (typ is None or v.get("type") == typ)] or videos
        blocks.append({"kind": "grid", "items": _rot(pool, page * 12, 12)})
        has_more = bool(pool)
    else:
        grid = _rot(videos, page * 10, 10)
        mixed = []
        si = page * 3
        for i, v in enumerate(grid):
            mixed.append(v)
            if shop and (i + 1) % 6 == 0:
                mixed.append(shop[si % len(shop)])
                si += 1
        blocks.append({"kind": "grid", "items": mixed})
        variant = page % 4
        if variant == 0 and shorts:
            blocks.append({"kind": "shelf", "variant": "shorts", "title": "Shorts",
                           "items": _rot(shorts, page * 5, min(14, len(shorts)))})
        elif variant == 1 and games:
            blocks.append({"kind": "shelf", "variant": "playables",
                           "title": "Play & Win — instant games", "items": _rot(games, page * 6, min(10, len(games)))})
        elif variant == 2 and shop:
            blocks.append({"kind": "shelf", "variant": "shop", "title": "Shop on RadioLife",
                           "items": _rot(shop, page * 6, min(10, len(shop)))})
        else:
            feat = (shop[page % len(shop)] if shop else (videos[page % len(videos)] if videos else None))
            if feat:
                blocks.append({"kind": "featured", "item": feat,
                               "cta": "Shop now" if feat.get("type") == "shop" else "Watch now"})
        has_more = bool(videos)

    resp: dict[str, Any] = {"page": page, "has_more": has_more, "blocks": blocks}
    if page == 0:
        chips = [{"key": "all", "title": "All"}, {"key": "shopping", "title": "Shopping"}]
        for key, title in [("originals", "Originals"), ("stations", "Live Stations"),
                           ("podcasts", "Podcasts"), ("games", "Play & Win")]:
            chips.append({"key": key, "title": title})
        resp["chips"] = chips
        resp["subs"] = _rot(pools["videos"], 0, min(8, len(pools["videos"])))
        resp["user"] = {"name": (user or {}).get("display_name") or (user or {}).get("name")} if user else None
    return resp


__all__ = ["router"]
