"""Resolved artwork for imported (Radio Browser) stations.

Priority: owner-set → AI-generated / flagship → real station logo →
deterministic branded placeholder (genre-coloured initials). Every
station therefore ALWAYS has a usable, on-brand image URL — no blanks.

The placeholder is a real PNG URL (ui-avatars) so it renders identically
on web and on mobile (expo-image) with normal caching.
"""
from __future__ import annotations
from urllib.parse import quote
from typing import Any, Tuple

# Genre keyword → hex background for the placeholder.
_GENRE_COLORS = [
    (("bolly", "hindi", "desi", "filmi"), "7c3aed"),
    (("talk", "news", "current"), "0ea5e9"),
    (("pop", "top 40", "hits", "chart"), "ec4899"),
    (("rock", "metal", "alt"), "e11d48"),
    (("classic", "ghazal", "instrumental"), "0d9488"),
    (("devotion", "bhajan", "spiritual", "islam", "quran", "sufi"), "d97706"),
    (("punjab", "bhangra"), "16a34a"),
    (("dance", "edm", "electro", "house", "party", "club"), "8b5cf6"),
    (("jazz", "blues", "soul"), "b45309"),
    (("arab", "khaleeji", "urdu"), "0891b2"),
]
_DEFAULT_COLOR = "6d28d9"


def _genre_color(station: dict) -> str:
    hay = " ".join(str(station.get(k) or "") for k in
                   ("music_genre", "tags_raw", "name", "description", "language")).lower()
    for keys, color in _GENRE_COLORS:
        if any(k in hay for k in keys):
            return color
    return _DEFAULT_COLOR


def placeholder_url(station: dict) -> str:
    name = (station.get("name") or "Radio").strip() or "Radio"
    return (f"https://ui-avatars.com/api/?name={quote(name)}&size=512"
            f"&background={_genre_color(station)}&color=ffffff"
            f"&bold=true&font-size=0.36&format=png")


def _is_real_image(url: Any) -> bool:
    return bool(url) and "ui-avatars.com" not in str(url)


def resolve_art(station: dict) -> Tuple[str, str]:
    """Best-available artwork. Returns (url, source) where source ∈
    {owner, ai, logo, placeholder}."""
    ov = station.get("owner_overrides") or {}
    if station.get("art_source") == "owner" and station.get("art_url"):
        return station["art_url"], "owner"
    if _is_real_image(ov.get("artwork_url")):
        return ov["artwork_url"], "owner"
    if station.get("art_source") == "ai" and station.get("art_url"):
        return station["art_url"], "ai"
    for k in ("flagship_art", "artwork_url", "cover_image_url"):
        if _is_real_image(station.get(k)):
            return station[k], "ai"
    for k in ("logo_url", "favicon"):
        if _is_real_image(station.get(k)):
            return station[k], "logo"
    return placeholder_url(station), "placeholder"
