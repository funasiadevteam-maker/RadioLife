"""Phase PDX.1 — Category taxonomy for the Predexon auto-curator.

The category slugs, display names, Predexon fetch strategies and default
points-per-event live in one place so the curator, the admin API, the
public categories endpoint and the frontend chip row all agree.

See `/app/memory/PDX_DISCOVERY.md` for the reasoning behind each
strategy — Predexon's `category` filter is a no-op, so we use the
verified `tags=<label>` (single, case-sensitive) and `search=<text>`
(title substring) filters instead.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, TypedDict


class FetchStep(TypedDict, total=False):
    """One Predexon list call.  A category may issue N steps that are
    then deduped by `market_id` client-side."""

    tag:    str                                     # optional — `tags=<label>` filter
    search: str                                     # optional — `search=<text>` filter
    limit:  int                                     # 1-100
    # Post-filter markers.  When present, keep ONLY items whose tag list
    # matches at least one of these strings (case-insensitive, substring).
    require_any_tag: List[str]
    # Or: keep only items whose title matches at least one substring
    # (case-insensitive).  Handy when the `tags` field is thin.
    require_any_title: List[str]
    # Or: drop items whose tag list contains any of these labels.  Used
    # by `sports_top` to exclude league-specific rows already routed to
    # `national_games`.
    exclude_any_tag: List[str]


class CategorySpec(TypedDict):
    slug:             str
    display_name: str
    default_points: int      # base points; log10(volume) bumps toward the 10-100 clamp
    take_top:            int  # after client-side sort by volume desc
    steps:                 List[FetchStep]


# Ordered — matches the frontend chip order.
PDX_CATEGORIES: List[CategorySpec] = [
    {
        "slug":             "sports_top",
        "display_name": "Top Sports",
        "default_points": 25,
        "take_top":         8,
        # Broad Sports tag pull.  Excludes league-specific tags so the
        # national_games slot gets those rows exclusively (dedupe by
        # category is handled in the service).
        "steps": [
            {
                "tag":                        "Sports",
                "limit":                    50,
                "exclude_any_tag": [
                    "NFL", "NBA", "MLB", "NHL", "IPL", "T20", "BBL",
                ],
            },
        ],
    },
    {
        "slug":             "stocks_top",
        "display_name": "Top Stocks",
        "default_points": 50,
        "take_top":         4,
        # Predexon has no `stocks` tag; the closest signal is markets
        # tagged with `Fed`, `Economy`, `Fed Rates`, `fomc`, `CPI Release`.
        # We probe via title search then require one of those tags.
        "steps": [
            {
                "search":                    "Fed rate",
                "limit":                        20,
                "require_any_tag": [
                    "Fed", "Fed Rates", "fomc", "Economy",
                    "Economic Policy", "CPI Release", "Jerome Powell",
                    "Earnings", "Stocks", "SPX", "SP500",
                ],
            },
            {"search": "earnings",   "limit": 10},
            {"search": "SP500",         "limit": 10},
        ],
    },
    {
        "slug":             "us_politics",
        "display_name": "US Politics",
        "default_points": 75,
        "take_top":         4,
        # `US Election` is the densest tag today — 73 hits in the top 100.
        "steps": [
            {"tag": "US Election", "limit": 50},
        ],
    },
    {
        "slug":             "national_games",
        "display_name": "National Games",
        "default_points": 40,
        "take_top":         6,
        # Cricket / American football / baseball / basketball national games.
        # `search=<league>` returns 15-20 markets per league.  We union
        # and dedupe by market_id, then take top 6 by volume.
        "steps": [
            {"search": "NFL",         "limit": 15},
            {"search": "NBA",         "limit": 15},
            {"search": "MLB",         "limit": 15},
            {"search": "cricket", "limit": 15},
        ],
    },
]


CATEGORY_BY_SLUG: Dict[str, CategorySpec] = {c["slug"]: c
                                                                                                      for c in PDX_CATEGORIES}

# Backfill order when `ensure_minimum_active` needs to top up under 20.
# US politics is chosen first because its Predexon pool is by far the
# deepest (~70+ active markets).
BACKFILL_ORDER: List[str] = [
    "us_politics", "sports_top", "stocks_top", "national_games",
]

# ----- Points curve --------------------------------------------------

POINTS_MIN = 10
POINTS_MAX = 100


def derive_points(default_points: int,
                                  volume_usd: float | int | None) -> int:
    """log10(volume)-scaled bump on top of the category default, clamped
    to the user-required [10, 100] window.

    Examples (see PDX_DISCOVERY.md for full worked table):
        sports_top base=25, vol=$8.9M   → 60
        us_politics base=75, vol=$55.8M → 100 (clamped)
        national_games base=40, vol=$4.5M → 73
    """
    if not isinstance(default_points, int):
        default_points = POINTS_MIN
    try:
        v = float(volume_usd or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    v = max(v, 1.0)
    bump = math.log10(v) * 5.0
    raw = round(default_points + bump)
    return max(POINTS_MIN, min(POINTS_MAX, int(raw)))


def polymarket_url_for(market_slug: str | None) -> str | None:
    """Best-effort canonical URL for the admin `Open on Polymarket` link.

    Predexon doesn't return a `market_url`, but every `market_slug`
    resolves 1:1 to the Polymarket UI:
        https://polymarket.com/event/<market_slug>
    """
    if not market_slug or not isinstance(market_slug, str):
        return None
    slug = market_slug.strip().lstrip("/")
    if not slug:
        return None
    return f"https://polymarket.com/event/{slug}"


def public_category_payload() -> List[Dict[str, Any]]:
    """Shape returned by `GET /api/predict-win/categories`.  Kept
    intentionally tiny so the frontend chip row + admin table both
    consume it directly."""
    return [
        {
            "slug":             c["slug"],
            "display_name": c["display_name"],
            "default_points": c["default_points"],
            "target_top":     c["take_top"],
        }
        for c in PDX_CATEGORIES
    ]


__all__ = [
    "PDX_CATEGORIES", "CATEGORY_BY_SLUG", "BACKFILL_ORDER",
    "POINTS_MIN", "POINTS_MAX",
    "derive_points", "polymarket_url_for", "public_category_payload",
]
