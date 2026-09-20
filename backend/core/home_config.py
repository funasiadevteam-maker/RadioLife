"""FUUSIC Home — config-driven pillar order + section visibility (A/B ready).

Single source of truth for the New Look V2 Home realignment. The consumer
brand is FUUSIC (see core/brand.py). The Home page leads with the WHOLE
ecosystem — Social first — instead of an audio-only surface. Admins can
reorder pillars / toggle sections without a code change (A/B ready).
"""
from __future__ import annotations

from typing import Any

# Ordered ecosystem pillars shown in "Your FUUSIC World". Social-first default.
# `icon` is a lucide name resolved on the web client.
PILLARS: dict[str, dict] = {
    "social": {
        "label": "Social", "icon": "users",
        "headline": "Do things together",
        "sub": "Friends, Moments, Clubs, rooms and shared experiences.",
        "cta": "Explore Social", "to": "/social", "featured": True,
        "grad": ["#14b8a6", "#22c55e"],
    },
    "listen": {
        "label": "Listen", "icon": "headphones",
        "headline": "Your sound. Your way.",
        "sub": "Live radio, AI radio, podcasts and more.",
        "cta": "Start Listening", "to": "/listen", "featured": False,
        "grad": ["#a855f7", "#ec4899"],
    },
    "live": {
        "label": "Live", "icon": "radio",
        "headline": "Happening right now",
        "sub": "Live audio, business video, creators and events.",
        "cta": "See What's Live", "to": "/social?tab=live", "featured": False,
        "grad": ["#f43f5e", "#a855f7"],
    },
    "shop": {
        "label": "Shop", "icon": "shopping-bag",
        "headline": "Discover local favorites",
        "sub": "Products, services, offers and businesses around you.",
        "cta": "Shop Now", "to": "/shop", "featured": False,
        "grad": ["#ec4899", "#f59e0b"],
    },
    "play": {
        "label": "Play", "icon": "gamepad-2",
        "headline": "Play. Compete. Win.",
        "sub": "Trivia, Predict & Win, games and challenges.",
        "cta": "Start Playing", "to": "/play-and-win", "featured": False,
        "grad": ["#8b5cf6", "#6366f1"],
    },
    "dining": {
        "label": "Dining", "icon": "utensils",
        "headline": "Your next favorite meal",
        "sub": "Restaurants, Dining Club and social dining.",
        "cta": "Explore Dining", "to": "/dining", "featured": False,
        "grad": ["#fb923c", "#ec4899"],
    },
    "earn": {
        "label": "Earn", "icon": "coins",
        "headline": "Everything counts",
        "sub": "Earn BigPoints when you listen, play, shop and engage.",
        "cta": "View BigPoints", "to": "/wallet", "featured": False,
        "grad": ["#f59e0b", "#f5c563"],
    },
    "explore": {
        "label": "Explore", "icon": "sparkles",
        "headline": "More to discover",
        "sub": "Moments, Clubs, Local Pulse, Events and more.",
        "cta": "Explore FUUSIC", "to": "/social", "featured": False,
        "grad": ["#06b6d4", "#3b82f6"],
    },
}

DEFAULT_PILLAR_ORDER = [
    "social", "listen", "live", "shop", "play", "dining", "earn", "explore",
]

# Home section visibility + titles. Order is fixed on the client; this drives
# what shows + the copy. Admin-editable.
DEFAULT_SECTIONS: dict[str, dict] = {
    "fuusic_world": {"visible": True, "title": "Your FUUSIC World"},
    "whats_happening": {"visible": True, "title": "What's Happening Now"},
    "continue": {"visible": True, "title": "Continue Listening"},
    "for_you": {"visible": True, "title": "For You"},
    "live_now": {"visible": True, "title": "Live Right Now"},
    "together": {"visible": True, "title": "Do Something Together"},
    "premium": {"visible": True, "title": ""},
}

# "Do something together" — one of FUUSIC's clearest differentiators.
TOGETHER_ACTIONS = [
    {"key": "listen", "label": "Listen Together",
     "sub": "Sync a station with friends", "to": "/social", "icon": "headphones"},
    {"key": "play", "label": "Play Together",
     "sub": "Team up on games & trivia", "to": "/social", "icon": "gamepad-2"},
    {"key": "shop", "label": "Shop Together",
     "sub": "Share a group cart", "to": "/social", "icon": "shopping-bag"},
    {"key": "go", "label": "Go Together",
     "sub": "Plan a night out", "to": "/social", "icon": "map-pin"},
]

_DOC_ID = "home_config_v2"


def _valid_order(order: Any) -> list[str]:
    """Keep only known pillars, de-dup, then append any missing so the set
    is always complete regardless of stored input."""
    seen: set[str] = set()
    out: list[str] = []
    if isinstance(order, list):
        for k in order:
            if k in PILLARS and k not in seen:
                seen.add(k)
                out.append(k)
    for k in DEFAULT_PILLAR_ORDER:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out


def build_fuusic_world(order: list[str]) -> list[dict]:
    return [{"key": k, **PILLARS[k]} for k in order if k in PILLARS]


async def get_home_config(db) -> dict:
    try:
        doc = await db.home_config.find_one({"_id": _DOC_ID})
    except Exception:
        doc = None
    order = _valid_order((doc or {}).get("pillar_order"))
    sections: dict[str, dict] = {}
    stored = (doc or {}).get("sections") or {}
    for key, base in DEFAULT_SECTIONS.items():
        s = stored.get(key) or {}
        sections[key] = {
            "visible": bool(s.get("visible", base["visible"])),
            "title": str(s.get("title") or base["title"]),
        }
    return {"pillar_order": order, "sections": sections}


async def save_home_config(db, patch: dict) -> dict:
    cur = await get_home_config(db)
    order = _valid_order(patch.get("pillar_order", cur["pillar_order"]))
    sections = dict(cur["sections"])
    for key, val in (patch.get("sections") or {}).items():
        if key in DEFAULT_SECTIONS and isinstance(val, dict):
            sections[key] = {
                "visible": bool(val.get("visible", sections[key]["visible"])),
                "title": str(val.get("title") or DEFAULT_SECTIONS[key]["title"]),
            }
    await db.home_config.update_one(
        {"_id": _DOC_ID},
        {"$set": {"pillar_order": order, "sections": sections}},
        upsert=True,
    )
    return {"pillar_order": order, "sections": sections}


def pillar_labels() -> dict:
    return {k: {"label": v["label"], "featured": v.get("featured", False)}
            for k, v in PILLARS.items()}
