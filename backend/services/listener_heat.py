"""Phase B — Listener heat helper.

Aggregates the top cities currently listening on FUUSIC in a rolling
window.  Used by ``/api/personalized/city_tags`` as the anon fallback
("anyone who isn't authed and doesn't have a resolved geo city of their
own gets the heat list so the hero never reads as empty / hardcoded").

Why an in-process TTL cache (and not Redis):
the platform spec is Mongo + in-memory only.  60s is plenty for a hero
tagline that's effectively a marketing label — we do not need millisecond
freshness.  The cache is per-Uvicorn-worker, which is acceptable since
the entries are tiny and the aggregation is cheap.

Data source:
``listener_session_archive`` (where completed sessions land) — every
archived session carries the resolved geo city we capture on
``listener_sessions.join`` (see routes/listener_sessions.py).  Live
sessions are also queried via ``listener_sessions`` for the most
up-to-the-second view, then merged with the archive over the window.

If neither collection has data yet (fresh install / cold pod),
``get_top_cities`` returns ``[]`` and the city_tags route falls back to
the canonical home-market list ("Dubai", "Mumbai", "Dallas") — the
SAME three cities the legacy hardcoded string used, just sourced from a
single config constant.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any

log = logging.getLogger("bigfm.listener_heat")

# Cached as (timestamp_s, payload).  60s TTL per the brief.
_CACHE: dict[tuple[int, int], tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SEC = 60.0

# Static fallback when no listening data exists yet.  Single source of
# truth for the "FUUSIC is live in these places" hero list — replaces
# the previously hardcoded "Dubai · Mumbai · Dallas" string.
LAUNCH_MARKETS: list[dict[str, Any]] = [
    {"city": "Dubai",  "country": "AE", "market": "dubai",   "session_count": 0},
    {"city": "Mumbai", "country": "IN", "market": "mumbai",  "session_count": 0},
    {"city": "Dallas", "country": "US", "market": "dfw",     "session_count": 0},
]


async def get_top_cities(db: Any, window_hours: int = 24,
                          limit: int = 3) -> list[dict[str, Any]]:
    """Return the top ``limit`` distinct cities by session count over the
    last ``window_hours`` hours.  Result shape per item:
    ``{city, country, market, session_count}``.

    Cached for ``_CACHE_TTL_SEC`` seconds per (window_hours, limit) tuple.
    Returns ``LAUNCH_MARKETS`` (truncated to ``limit``) when no data.
    """
    key = (int(window_hours), int(limit))
    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return list(cached[1])  # defensive copy

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    pipeline = [
        {"$match": {
            "resolved_city": {"$nin": [None, "", "Global"]},
            "joined_at":     {"$gte": cutoff},
        }},
        {"$group": {
            "_id":            "$resolved_city",
            "session_count": {"$sum": 1},
            "country":       {"$first": "$resolved_country"},
            "market":         {"$first": "$resolved_market"},
        }},
        {"$sort":  {"session_count": -1}},
        {"$limit": limit},
    ]
    out: list[dict[str, Any]] = []
    try:
        # Union of live + archive — gives the freshest possible view.
        for col in ("listener_sessions", "listener_session_archive"):
            async for row in db[col].aggregate(pipeline):
                out.append({
                    "city":           row.get("_id") or "—",
                    "country":         row.get("country") or "",
                    "market":          row.get("market") or "",
                    "session_count": int(row.get("session_count") or 0),
                })
    except Exception as e:
        log.warning("[heat] aggregation failed: %s: %s", type(e).__name__, e)

    # Merge same-city rows from the two collections; keep order by total.
    merged: dict[str, dict[str, Any]] = {}
    for r in out:
        k = r["city"].lower()
        if k not in merged:
            merged[k] = dict(r)
        else:
            merged[k]["session_count"] += r["session_count"]
    final = sorted(merged.values(),
                    key=lambda r: r["session_count"], reverse=True)[:limit]

    if not final:
        final = list(LAUNCH_MARKETS[:limit])

    _CACHE[key] = (now, list(final))
    return final


def invalidate_cache() -> None:
    """Test hook — clears the TTL cache so tests can assert fresh reads."""
    _CACHE.clear()
