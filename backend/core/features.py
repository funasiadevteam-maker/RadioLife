"""Personalized portal — the canonical catalog of toggleable FUUSIC features.

Each user picks which features they want; Home + the nav then show only those.
Keys MUST match the "Your FUUSIC World" pillar keys (FuusicWorldGridV2) and the
shell nav keys so filtering lines up on the web client.

Single source of truth for:
  • /api/social/features        (per-user enabled set + first-run onboarding)
  • /api/admin/feature-defaults  (global default set new users start with)
"""
from __future__ import annotations

# key, label, short description, icon (lucide key), route, mandatory
FEATURE_CATALOG = [
    {"key": "listen", "label": "Listen",
     "desc": "Live radio, AI radio & podcasts",
     "icon": "headphones", "to": "/listen", "mandatory": True},
    {"key": "social", "label": "Social",
     "desc": "Friends, Moments, Clubs & live listening rooms",
     "icon": "users", "to": "/social", "mandatory": False},
    {"key": "live", "label": "Live",
     "desc": "Live audio, business video & events happening now",
     "icon": "radio", "to": "/social?tab=live", "mandatory": False},
    {"key": "shop", "label": "Shop",
     "desc": "Local products, services & offers near you",
     "icon": "shopping-bag", "to": "/shop", "mandatory": False},
    {"key": "play", "label": "Play",
     "desc": "Trivia, Predict & Win and challenges",
     "icon": "gamepad-2", "to": "/play-and-win", "mandatory": False},
    {"key": "dining", "label": "Food & Dining",
     "desc": "Restaurants, Dining Club & social dining",
     "icon": "utensils", "to": "/dining", "mandatory": False},
    {"key": "earn", "label": "Earn",
     "desc": "BigPoints as you listen, play & shop",
     "icon": "coins", "to": "/wallet", "mandatory": False},
    {"key": "explore", "label": "Explore",
     "desc": "Moments, Clubs, Local Pulse & Events",
     "icon": "sparkles", "to": "/social", "mandatory": False},
]

FEATURE_KEYS = [f["key"] for f in FEATURE_CATALOG]
MANDATORY_FEATURES = [f["key"] for f in FEATURE_CATALOG if f.get("mandatory")]
# New users start with everything on (opt-out) unless an admin narrows it.
DEFAULT_FEATURES = FEATURE_KEYS[:]


def normalize_features(sel) -> list[str]:
    """Keep only valid keys, in catalog order, with mandatory features forced on."""
    chosen = {k for k in (sel or []) if k in FEATURE_KEYS}
    chosen.update(MANDATORY_FEATURES)
    return [k for k in FEATURE_KEYS if k in chosen]


# Starter per-city default feature sets. Admins can override these via
# app_settings.feature_defaults.by_city; these built-ins are the fallback so a
# brand-new user in a given city gets a sensible, locally-relevant Home order.
CITY_FEATURE_DEFAULTS: dict[str, list[str]] = {
    "dubai":       ["listen", "social", "shop", "dining", "live", "play", "earn", "explore"],
    "mumbai":      ["listen", "social", "play", "live", "shop", "earn", "explore"],
    "london":      ["listen", "social", "live", "shop", "dining", "earn", "explore"],
    "new york":    ["listen", "social", "live", "shop", "dining", "play", "earn", "explore"],
    "dallas":      ["listen", "social", "shop", "play", "live", "earn", "explore"],
    "los angeles": ["listen", "social", "live", "shop", "play", "dining", "earn", "explore"],
}


def normalize_features_ordered(sel) -> list[str]:
    """Keep valid keys in the GIVEN order (de-duped), with mandatory features
    forced on at the front when missing. Preserves the user's chosen order so
    Home + the nav can render features in the sequence they arranged."""
    out: list[str] = []
    seen: set[str] = set()
    for k in (sel or []):
        if k in FEATURE_KEYS and k not in seen:
            seen.add(k)
            out.append(k)
    for k in MANDATORY_FEATURES:
        if k not in seen:
            out.insert(0, k)
            seen.add(k)
    return out


def city_default_features(city) -> list[str] | None:
    """Built-in per-city starter set (ordered), or None when unrecognised."""
    preset = CITY_FEATURE_DEFAULTS.get((city or "").strip().lower())
    return normalize_features_ordered(preset) if preset else None
