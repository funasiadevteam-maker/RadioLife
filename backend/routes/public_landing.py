"""FUUSIC public social-first landing — public-safe content endpoints.

Serves the logged-out homepage: a mixed social wall, suggested people, a
Live-Now rail and Sponsored/Discover promos. Blends REAL public-safe data
(launch businesses, radio stations, public Moments) with a few clearly
flagged `illustrative` sample cards so the wall never looks empty. Honours
the public-content policy: nothing private, no fabricated live viewer counts.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends

from auth import current_user_optional

router = APIRouter(prefix="/api/public", tags=["public-landing"])

# ── Imagery (stock, relevant) ────────────────────────────────────────────
IMG = {
    "hero": "https://images.unsplash.com/photo-1768321140311-ed354a0828e3?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzV8MHwxfHNlYXJjaHwxfHx3b21hbiUyMGhlYWRwaG9uZXMlMjBjaXR5JTIwc2t5bGluZSUyMG5pZ2h0JTIwbGlmZXN0eWxlfGVufDB8fHx8MTc5MTk2MTYzNHww&ixlib=rb-4.1.0&q=85",
    "friends": "https://images.unsplash.com/photo-1758272133719-959319bc2364?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzl8MHwxfHNlYXJjaHw0fHxkaXZlcnNlJTIwZnJpZW5kcyUyMGdyb3VwJTIwc2VsZmllJTIwY2l0eSUyMHN1bnNldHxlbnwwfHx8fDE3OTE5NjE2MzR8MA&ixlib=rb-4.1.0&q=85",
    "travel": "https://images.unsplash.com/photo-1758272133786-ee98adcc6837?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzl8MHwxfHNlYXJjaHwzfHxkaXZlcnNlJTIwZnJpZW5kcyUyMGdyb3VwJTIwc2VsZmllJTIwY2l0eSUyMHN1bnNldHxlbnwwfHx8fDE3OTE5NjE2MzR8MA&ixlib=rb-4.1.0&q=85",
    "cooking": "https://images.unsplash.com/photo-1640583342012-4622f31b650d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzB8MHwxfHNlYXJjaHwyfHxjaGVmJTIwY29va2luZyUyMHJlc3RhdXJhbnQlMjBraXRjaGVufGVufDB8fHx8MTc5MTk2MTYzNHww&ixlib=rb-4.1.0&q=85",
    "restaurant": "https://images.unsplash.com/photo-1622021142947-da7dedc7c39a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzB8MHwxfHNlYXJjaHwxfHxjaGVmJTIwY29va2luZyUyMHJlc3RhdXJhbnQlMjBraXRjaGVufGVufDB8fHx8MTc5MTk2MTYzNHww&ixlib=rb-4.1.0&q=85",
    "radio": "https://images.unsplash.com/photo-1589903308904-1010c2294adc?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1NzZ8MHwxfHNlYXJjaHwxfHxyYWRpbyUyMGRqJTIwaGVhZHBob25lcyUyMG1pY3JvcGhvbmUlMjBzdHVkaW98ZW58MHx8fHwxNzkxOTYxNjM0fDA&ixlib=rb-4.1.0&q=85",
    "woman1": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzV8MHwxfHNlYXJjaHwzfHxwcm9mZXNzaW9uYWwlMjBwb3J0cmFpdCUyMHBlcnNvbiUyMHNtaWxpbmd8ZW58MHx8fHwxNzkxOTYxNjM0fDA&ixlib=rb-4.1.0&q=85",
    "woman2": "https://images.unsplash.com/photo-1580489944761-15a19d654956?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzV8MHwxfHNlYXJjaHwxfHxwcm9mZXNzaW9uYWwlMjBwb3J0cmFpdCUyMHBlcnNvbiUyMHNtaWxpbmd8ZW58MHx8fHwxNzkxOTYxNjM0fDA&ixlib=rb-4.1.0&q=85",
    "woman3": "https://images.unsplash.com/photo-1662850886700-4ec19bd30d11?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzV8MHwxfHNlYXJjaHwyfHxwcm9mZXNzaW9uYWwlMjBwb3J0cmFpdCUyMHBlcnNvbiUyMHNtaWxpbmd8ZW58MHx8fHwxNzkxOTYxNjM0fDA&ixlib=rb-4.1.0&q=85",
}

STATION_COPY_OPTIONS = {
    "generic": "Radio stations from around the world",
    "thousands": "Thousands of radio stations. One world of sound.",
}

DEFAULT_LANDING_CONFIG = {
    "new_landing_enabled": True,
    "default_theme": "light",          # light | dark | system
    "allow_theme_switch": True,
    "station_copy": "thousands",       # generic | thousands
    "hero": {
        "headline": "Everything You Love, Together.",
        "subheadline": "Listen. Connect. Play. Shop. Earn.",
        "supporting": "Discover your people, share experiences, explore radio stations worldwide, watch what's live, shop local, play games and earn BigPoints.",
        "primary_cta_label": "Join FUUSIC for Free",
        "secondary_cta_label": "Explore Live Now",
        "chips": ["Radio Stations", "Live Experiences", "Friends & Communities",
                  "Local Businesses", "Games", "BigPoints"],
    },
    "shortcut_order": ["home", "social", "listen", "shop", "play", "dining",
                       "bigpoints", "events", "clubs", "dreams", "tarot", "explore"],
    "feed_modules": ["composer", "together", "tabs", "feed"],
    "right_modules": ["people", "live_now", "promos"],
}


def _now():
    return datetime.now(timezone.utc)


def _iso_ago(minutes: int) -> str:
    return (_now() - timedelta(minutes=minutes)).isoformat()


# ── Illustrative feed cards (clearly flagged) ────────────────────────────
def _illustrative_feed() -> list[dict]:
    return [
        {
            "id": "ill_moment_1", "type": "MOMENT", "illustrative": True,
            "actor": {"id": None, "name": "Priya Sharma", "avatar_url": IMG["woman1"], "kind": "person"},
            "title": None, "text": "Beautiful evening at JBR with the crew! Great music, food and friends.",
            "media_url": IMG["friends"], "media_type": "image", "created_at": _iso_ago(118),
            "ranking_reason": None, "cta": None,
            "meta": {"like_count": 128, "comment_count": 24},
        },
        {
            "id": "ill_radio_1", "type": "LIVE_RADIO", "illustrative": True,
            "actor": {"id": None, "name": "Big FM Dubai", "avatar_url": None, "kind": "business", "verified": True},
            "title": "Evening Drive with RJ Alex", "text": "Join live and drop your requests!",
            "media_url": IMG["radio"], "media_type": "video", "created_at": _iso_ago(10),
            "ranking_reason": "Live radio", "cta": {"label": "Listen Live", "action": "open_station", "target": None},
            "meta": {"like_count": 54, "comment_count": 7},
        },
        {
            "id": "ill_biz_live_1", "type": "BUSINESS_LIVE", "illustrative": True,
            "actor": {"id": None, "name": "Desi District", "avatar_url": None, "kind": "business", "verified": True},
            "title": "Chef's Special Tonight", "text": "Live cooking — watch and order the night's special.",
            "media_url": IMG["cooking"], "media_type": "video", "created_at": _iso_ago(4),
            "ranking_reason": "Live commerce", "cta": {"label": "Watch Live · Shop", "action": "open_live", "target": None},
            "meta": {"like_count": 76, "comment_count": 12, "products": [
                {"product_id": "p1", "title": "Chef's Thali", "offer": "AED 45", "image_url": IMG["restaurant"]},
                {"product_id": "p2", "title": "Mango Lassi", "price_cents": 1800, "image_url": IMG["cooking"]},
            ]},
        },
        {
            "id": "ill_offer_1", "type": "OFFER", "illustrative": True,
            "actor": {"id": None, "name": "SpiceTrail Restaurant", "avatar_url": None, "kind": "business", "verified": True},
            "title": "20% off dinner tonight", "text": "Show your FUUSIC profile at the table to redeem.",
            "media_url": IMG["restaurant"], "media_type": "image", "created_at": _iso_ago(55),
            "ranking_reason": "Popular near you", "cta": {"label": "View Offer", "action": "view_offer", "target": None},
            "meta": {"like_count": 33, "comment_count": 3},
        },
        {
            "id": "ill_game_1", "type": "GAME", "illustrative": True,
            "actor": {"id": None, "name": "Bollywood Trivia", "avatar_url": None, "kind": "business"},
            "title": "Bollywood Trivia — Live Today at 8 PM", "text": "Play with friends and earn eligible BigPoints.",
            "media_url": None, "media_type": None, "created_at": _iso_ago(30),
            "ranking_reason": None, "cta": {"label": "Play Now", "action": "open_game", "target": None},
            "meta": {"like_count": 41, "comment_count": 9},
        },
        {
            "id": "ill_event_1", "type": "EVENT", "illustrative": True,
            "actor": {"id": None, "name": "Travel Club Dubai", "avatar_url": None, "kind": "business"},
            "title": "Weekend meetup — Marina walk", "text": "RSVP to join the weekend meetup with the club.",
            "media_url": IMG["travel"], "media_type": "image", "created_at": _iso_ago(90),
            "ranking_reason": None, "cta": {"label": "View Event", "action": "open_event", "target": None},
            "meta": {"like_count": 58, "comment_count": 14},
        },
        {
            "id": "ill_dream_1", "type": "DREAM", "illustrative": True,
            "actor": {"id": None, "name": "Anonymous Dreamer", "avatar_url": None, "kind": "person"},
            "title": None, "text": "I dreamed I was flying over the ocean at sunrise... felt completely free.",
            "media_url": None, "media_type": None, "created_at": _iso_ago(140),
            "ranking_reason": None, "cta": {"label": "I had a similar dream", "action": "open_dream", "target": None},
            "meta": {"like_count": 22, "comment_count": 6},
        },
        {
            "id": "ill_tarot_1", "type": "TAROT_SHARE", "illustrative": True,
            "actor": {"id": None, "name": "Maya", "avatar_url": IMG["woman3"], "kind": "person"},
            "title": "The Star — a shared reading", "text": "Maya shared a public Tarot card. Explore the meaning.",
            "media_url": None, "media_type": None, "created_at": _iso_ago(200),
            "ranking_reason": None, "cta": {"label": "View Reading", "action": "open_tarot", "target": None},
            "meta": {"like_count": 18, "comment_count": 4},
        },
    ]


async def _real_offer_cards(db, limit: int = 3) -> list[dict]:
    """Real, public launch businesses → OFFER cards (no private data)."""
    out: list[dict] = []
    try:
        cursor = db.businesses.find(
            {"status": {"$ne": "disabled"}},
            {"business_id": 1, "name": 1, "category": 1, "logo_url": 1,
             "cover_url": 1, "city": 1}).limit(limit)
        async for b in cursor:
            name = b.get("name")
            if not name:
                continue
            out.append({
                "id": f"biz_{b.get('business_id')}", "type": "OFFER", "illustrative": False,
                "actor": {"id": None, "name": name, "avatar_url": b.get("logo_url"),
                          "kind": "business", "verified": True},
                "title": f"{name} on FUUSIC",
                "text": f"{(b.get('category') or 'Local business')}"
                        + (f" · {b.get('city')}" if b.get("city") else ""),
                "media_url": b.get("cover_url") or IMG["restaurant"], "media_type": "image",
                "created_at": _iso_ago(random.randint(20, 300)), "ranking_reason": "Local business",
                "cta": {"label": "View Business", "action": "view_offer", "target": b.get("business_id")},
                "meta": {"like_count": 0, "comment_count": 0},
            })
    except Exception:
        pass
    return out


@router.get("/landing-config")
async def public_landing_config(request: Request):
    """Public (read-only) landing configuration that drives the homepage."""
    db = request.app.state.db
    stored = await db.app_settings.find_one({"_id": "landing_config"}) or {}
    cfg = {**DEFAULT_LANDING_CONFIG, **{k: v for k, v in stored.items() if k != "_id"}}
    # Merge nested hero so partial admin edits keep defaults.
    cfg["hero"] = {**DEFAULT_LANDING_CONFIG["hero"], **(stored.get("hero") or {})}
    cfg["station_copy_text"] = STATION_COPY_OPTIONS.get(
        cfg.get("station_copy"), STATION_COPY_OPTIONS["thousands"])
    # Never leak admin-only promo targeting internals to the public config.
    cfg.pop("promos", None)
    return cfg


@router.get("/feed")
async def public_feed(request: Request, limit: int = 8, offset: int = 0,
                      user: Optional[dict] = Depends(current_user_optional)):
    """Public social wall — real public-safe content blended with clearly
    flagged illustrative sample cards. Never exposes private posts."""
    db = request.app.state.db
    real = await _real_offer_cards(db, limit=3)
    items = _illustrative_feed()
    # Interleave real business cards after the first couple of cards.
    for i, r in enumerate(real):
        items.insert(min(2 + i * 2, len(items)), r)
    total = len(items)
    page = items[offset:offset + max(1, min(limit, 20))]
    return {"items": page, "total": total, "has_more": offset + len(page) < total,
            "note": "Public preview — illustrative cards are labelled."}


@router.get("/people")
async def public_people(request: Request):
    """Publicly discoverable suggested profiles (People You May Know)."""
    people = [
        {"id": None, "name": "Arjun Mehta", "descriptor": "Follows same stations",
         "avatar_url": None, "kind": "person", "illustrative": True},
        {"id": None, "name": "Sophie Laurent", "descriptor": "3 mutual friends",
         "avatar_url": IMG["woman2"], "kind": "person", "illustrative": True},
        {"id": None, "name": "CityEats Dubai", "descriptor": "Popular restaurant",
         "avatar_url": IMG["restaurant"], "kind": "business", "verified": True, "illustrative": True},
    ]
    return {"people": people}


@router.get("/live-now")
async def public_live_now(request: Request):
    """Genuinely-live experiences first (none fabricated). When nothing is
    truly live we return an illustrative discover set, clearly flagged and
    WITHOUT fabricated viewer counts, so the module still demonstrates FUUSIC."""
    db = request.app.state.db
    live: list[dict] = []
    try:
        cursor = db.social_live_shows.find(
            {"status": "live"},
            {"show_id": 1, "title": 1, "cover_url": 1, "host_name": 1}).limit(3)
        async for s in cursor:
            live.append({
                "id": s.get("show_id"), "name": s.get("host_name") or s.get("title") or "Live",
                "desc": s.get("title") or "Live now", "thumb": s.get("cover_url") or IMG["radio"],
                "live": True, "illustrative": False,
            })
    except Exception:
        pass
    discover = [
        {"id": "ill_live_1", "name": "Desi District", "desc": "Live cooking tonight",
         "thumb": IMG["cooking"], "live": False, "illustrative": True},
        {"id": "ill_live_2", "name": "Bollywood Vibes", "desc": "Live audio room",
         "thumb": IMG["radio"], "live": False, "illustrative": True},
        {"id": "ill_live_3", "name": "Travel Club Dubai", "desc": "Live from the Marina",
         "thumb": IMG["travel"], "live": False, "illustrative": True},
    ]
    return {"live": live, "discover": discover}


@router.get("/promos")
async def public_promos(request: Request):
    """Sponsored & Discover rail — house promos + admin-configured external
    promos. Paid items are flagged `sponsored` so the UI can label them."""
    db = request.app.state.db
    stored = await db.app_settings.find_one({"_id": "landing_config"}) or {}
    house = [
        {"id": "premium", "name": "FUUSIC Premium", "text": "Go ad-free · 6 skips/hr",
         "cta_label": "Upgrade", "cta_to": "/pricing", "icon": "crown",
         "accent": "#f5c563", "house": True, "sponsored": False},
        {"id": "business", "name": "FUUSIC for Business", "text": "Go live. Run offers. Grow.",
         "cta_label": "Learn More", "cta_to": "/for-business", "icon": "store",
         "accent": "#60a5fa", "house": True, "sponsored": False},
        {"id": "bigpoints", "name": "BigPoints", "text": "Earn rewards everywhere you go",
         "cta_label": "How it works", "cta_to": "/wallet", "icon": "coins",
         "accent": "#a855f7", "house": True, "sponsored": False},
        {"id": "dining", "name": "Dining Club", "text": "Member perks at local spots",
         "cta_label": "Explore", "cta_to": "/dining", "icon": "utensils",
         "accent": "#fb923c", "house": True, "sponsored": False},
        {"id": "invite", "name": "Invite Friends", "text": "Bring your crew, earn together",
         "cta_label": "Invite", "cta_to": "/login", "icon": "users",
         "accent": "#22c55e", "house": True, "sponsored": False},
    ]
    external = [
        {"id": "ext_spicetrail", "name": "SpiceTrail Restaurant", "text": "20% off dinner tonight",
         "cta_label": "View Offer", "cta_to": "/shop", "image_url": IMG["restaurant"],
         "house": False, "sponsored": True, "illustrative": True},
        {"id": "ext_glowfit", "name": "GlowFit Studio", "text": "Join the 7-day challenge",
         "cta_label": "Join Now", "cta_to": "/shop", "image_url": IMG["travel"],
         "house": False, "sponsored": True, "illustrative": True},
        {"id": "ext_citybeat", "name": "CityBeat Events", "text": "Weekend tickets & more",
         "cta_label": "Explore", "cta_to": "/social", "image_url": IMG["friends"],
         "house": False, "sponsored": True, "illustrative": True},
    ]
    # Admin can disable specific house promos / add external ones.
    cfg_promos = stored.get("promos") or {}
    disabled = set(cfg_promos.get("disabled") or [])
    extra = cfg_promos.get("external") or []
    promos = [p for p in house if p["id"] not in disabled] + external + list(extra)
    return {"promos": promos}


__all__ = ["router", "DEFAULT_LANDING_CONFIG", "STATION_COPY_OPTIONS"]
