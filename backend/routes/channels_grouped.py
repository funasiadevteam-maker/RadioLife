"""Phase 41 Session 1.8 — category-grouped channel listing.

Public discovery footer endpoint that merges admin-curated channels
(`channels` collection) and published+public community stations
(`community_radio_stations`), buckets them by genre→category, and
returns a payload ready for a multi-column footer.

In-process cache: 60s. The footer polls infrequently (per-session on
the client side), so 60s smooths burst loads when many tabs open at
once without serving stale category mapping.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/channels", tags=["channels-grouped"])
log = logging.getLogger("bigfm.channels_grouped")

# ----- category derivation ------------------------------------------------
# Stable display labels keyed on a normalized genre slug. Anything not
# in this map falls back to the title-cased raw genre OR "Other".
_GENRE_TO_CATEGORY: dict[str, str] = {
    "bollywood":        "Bollywood",
    "bollywood music":  "Bollywood",
    "hindi":            "Bollywood",
    "pop":              "Pop",
    "retro":            "Retro",
    "indie":            "Indie",
    "electronic":       "Electronic & Dance",
    "edm":              "Electronic & Dance",
    "house":            "Electronic & Dance",
    "dance":            "Electronic & Dance",
    "hip_hop":          "Hip-Hop",
    "hiphop":           "Hip-Hop",
    "rap":              "Hip-Hop",
    "punjabi_pop":      "Punjabi",
    "punjabi":          "Punjabi",
    "bhangra":          "Punjabi",
    "devotional":       "Devotional & Sufi",
    "sufi":             "Devotional & Sufi",
    "ghazal":           "Devotional & Sufi",
    "bhajan":           "Devotional & Sufi",
    "regional":         "Regional",
    "rock":             "Rock",
    "jazz":             "Jazz & Lounge",
    "lounge":           "Jazz & Lounge",
    "classical":        "Classical",
    "news":             "News",
    "talk":             "News",
}


def _normalize_genre(g: str) -> str:
    return (g or "").strip().lower().replace("-", "_")


def _category_for(genres: list, explicit_category: Optional[str]) -> str:
    """Resolve the display category for a single channel/station."""
    if explicit_category:
        cat = explicit_category.strip()
        if cat:
            return _GENRE_TO_CATEGORY.get(cat.lower(), cat.title())
    for g in genres or []:
        ng = _normalize_genre(g)
        if ng in _GENRE_TO_CATEGORY:
            return _GENRE_TO_CATEGORY[ng]
    # fallback: first genre title-cased
    if genres:
        first = (genres[0] or "").strip()
        if first:
            return first.title()
    return "Other"


# ----- cache --------------------------------------------------------------
_CACHE: dict = {"value": None, "expires_at": 0.0}
_CACHE_TTL_SEC = 60.0


@router.get("/by_category")
async def channels_by_category(request: Request):
    """Returns a flat, ready-to-render category list:

      {categories: [{name, channels: [{slug, name, type, listener_count}]}]}

    - Admin channels: `type="admin"`, deep-link `/radio?channel={slug}`
      (frontend uses this; we just return slug + type and let the UI
      decide the route).
    - Community stations: `type="community"`, deep-link `/r/{slug}`.
    - Categories sorted by total channel count desc (ties → alpha).
    - Channels within a category sorted alphabetically by name.
    - Only `active=True` admin channels and `published+public` community
      stations are included.
    """
    now = time.time()
    cached = _CACHE
    if cached["value"] is not None and cached["expires_at"] > now:
        return cached["value"]

    db = request.app.state.db
    buckets: dict[str, list] = {}

    # Admin channels — every market gets the global+market-mixed list;
    # we don't filter by listener market here because the footer is a
    # global discovery surface (deep-links handle the per-channel
    # availability check at click time).
    async for ch in db.channels.find({"active": True}).sort("sort_order", 1):
        slug = ch.get("_id") or ch.get("slug")
        if not slug:
            continue
        cat = _category_for(ch.get("allowed_genres") or [],
                            ch.get("category"))
        buckets.setdefault(cat, []).append({
            "slug":           slug,
            "name":           ch.get("name") or slug,
            "type":           "admin",
            "listener_count": None,  # populated in Session 2.B
        })

    # Community stations — only published+public (the discovery surface).
    async for s in db.community_radio_stations.find(
            {"status": "published", "privacy": "public"}):
        slug = s.get("slug")
        if not slug:
            continue
        cat = _category_for(s.get("allowed_genres") or [], None)
        buckets.setdefault(cat, []).append({
            "slug":           slug,
            "name":           s.get("name") or slug,
            "type":           "community",
            "listener_count": None,  # real live count lands in Session 2.B
        })

    # Sort channels alphabetically inside each bucket; sort categories
    # by channel count desc then alpha.
    categories = []
    for name, channels in buckets.items():
        channels_sorted = sorted(channels, key=lambda c: c["name"].lower())
        categories.append({"name": name, "channels": channels_sorted})
    categories.sort(key=lambda c: (-len(c["channels"]), c["name"].lower()))

    payload = {"categories": categories,
               "total_channels": sum(len(c["channels"]) for c in categories),
               "cached_at": now}
    _CACHE["value"] = payload
    _CACHE["expires_at"] = now + _CACHE_TTL_SEC
    return payload
