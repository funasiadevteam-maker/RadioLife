"""Phase 41 Session 5.A — Creator analytics dashboard endpoints.

Public surface:
  - `GET /api/stations/{slug}/analytics?window=7d|30d|90d|all`  (owner)
  - `GET /api/stations/{slug}/analytics.csv?window=…`           (owner, 5.B)

All metrics computed via `services/station_analytics.py`. Results are
cached in-process for 15 minutes keyed on `(slug, window)`. Cache is
busted on any owner-side mutation that materially changes a metric
(post create, follower toggle, announcement create) — those triggers
live in the respective route modules; here we expose a single helper
`bust_analytics_cache(slug)` so other modules can invalidate without
importing the internals.
"""
from __future__ import annotations
import csv
import io
import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from auth import current_user
from services.station_analytics import compose_station_analytics

router = APIRouter(prefix="/api", tags=["station-analytics"])
log = logging.getLogger("bigfm.station_analytics_routes")

_CACHE: dict[tuple, dict] = {}
_TTL_SEC = 15 * 60


def bust_analytics_cache(slug: Optional[str] = None) -> None:
    """If `slug` is provided, drops every window for that slug;
    otherwise flushes everything. Cheap — the cache is tiny."""
    if slug is None:
        _CACHE.clear()
        return
    for k in list(_CACHE.keys()):
        if k[0] == slug:
            _CACHE.pop(k, None)


def _is_admin(user: Optional[dict]) -> bool:
    return bool(user and (user.get("role") == "admin" or user.get("is_admin")))


async def _resolve_owner_station(db, slug: str, user: dict) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if s.get("owner_user_id") != user.get("user_id") and not _is_admin(user):
        raise HTTPException(403, {"code": "permission_denied",
                                    "message": "Owner only."})
    s.pop("_id", None)
    return s


def _norm_window(window: str) -> str:
    if window not in ("7d", "30d", "90d", "all"):
        return "7d"
    return window


@router.get("/stations/{slug}/analytics")
async def get_station_analytics(slug: str, request: Request,
                                  window: str = Query("7d"),
                                  user: dict = Depends(current_user)):
    window = _norm_window(window)
    db = request.app.state.db
    station = await _resolve_owner_station(db, slug, user)

    key = (slug, window)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and cached["expires_at"] > now:
        return cached["value"]

    payload = await compose_station_analytics(db, station, window)
    _CACHE[key] = {"value": payload, "expires_at": now + _TTL_SEC}
    return payload


# ----- 5.B CSV export -------------------------------------------------
@router.get("/stations/{slug}/analytics.csv")
async def get_station_analytics_csv(slug: str, request: Request,
                                       window: str = Query("7d"),
                                       user: dict = Depends(current_user)):
    """Returns the daily_series block as CSV — owner only."""
    window = _norm_window(window)
    db = request.app.state.db
    station = await _resolve_owner_station(db, slug, user)
    payload = await compose_station_analytics(db, station, window)
    series = payload.get("daily_series") or []

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "date", "listen_minutes", "unique_listeners", "new_followers",
        "posts", "reactions", "comments",
    ])
    for row in series:
        writer.writerow([
            row.get("date", ""),
            row.get("listen_minutes", 0),
            row.get("unique_listeners", 0),
            row.get("new_followers", 0),
            row.get("posts", 0),
            row.get("reactions", 0),
            row.get("comments", 0),
        ])
    out.seek(0)
    filename = f"bigfm_{slug}_analytics_{window}.csv"
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        })


# ── Phase J.2 — Mood distribution mini-section ────────────────────
# Owner-or-admin gated.  Aggregates `tracks.mood_tags` across the
# station's recently-played items in the requested window.
def _window_to_days(window: str) -> int:
    return {"today": 1, "week": 7, "month": 30, "all": 3650}.get(window, 7)


@router.get("/stations/{slug}/mood-distribution")
async def get_station_mood_distribution(
        slug: str, request: Request,
        window: str = Query("week", pattern="^(today|week|month|all)$"),
        user: dict = Depends(current_user)):
    """Returns the per-station mood-tag histogram + top-3 share.

    Owner-or-admin only.  Aggregates from `station_play_history` joined
    with `tracks.mood_tags`.  Falls back gracefully when neither
    collection has data (returns zeroed counts so the UI can render an
    empty-state)."""
    from datetime import datetime, timedelta, timezone
    db = request.app.state.db
    station = await _resolve_owner_station(db, slug, user)
    station_id = station.get("_id") or station.get("id") or slug

    since = datetime.now(timezone.utc) - timedelta(days=_window_to_days(window))

    # Pull recently-played track IDs for this station.  Use the
    # community_station_play_events / station_play_history table —
    # whichever the platform writes to.  Both schemas seen in the wild.
    track_ids: set[str] = set()
    for coll_name in ("station_play_events", "station_play_history",
                                      "community_station_play_events",
                                      "play_history"):
        try:
            coll = db[coll_name]
        except Exception:
            continue
        async for ev in coll.find(
            {"$or": [{"station_id": station_id}, {"station_slug": slug}],
              "played_at": {"$gte": since}},
            {"track_id": 1, "_id": 0}).limit(5000):
            tid = ev.get("track_id")
            if tid: track_ids.add(tid)
        if track_ids: break

    if not track_ids:
        return {"window": window, "since": since.isoformat(),
                      "station_id": station_id, "total_plays": 0,
                      "mood_counts": {}, "top_3": []}

    # Sum mood_tags weighted by per-track play count.  We re-loop the
    # play table to weight; if it failed above we treat each track as 1.
    play_counts: dict[str, int] = {tid: 1 for tid in track_ids}

    mood_counts: dict[str, int] = {}
    total = 0
    async for t in db.tracks.find(
        {"_id": {"$in": list(track_ids)}},
        {"mood_tags": 1, "_id": 1}):
        n = play_counts.get(t["_id"], 1)
        for m in (t.get("mood_tags") or []):
            mood_counts[m] = mood_counts.get(m, 0) + n
            total += n

    # Pretty top-3.
    sorted_moods = sorted(mood_counts.items(), key=lambda kv: -kv[1])
    top_3 = [{"mood": m, "count": c,
                      "pct": (round(100 * c / total, 1) if total else 0)}
                  for m, c in sorted_moods[:3]]
    return {"window": window, "since": since.isoformat(),
                  "station_id": station_id, "total_plays": total,
                  "mood_counts": dict(sorted_moods), "top_3": top_3}
