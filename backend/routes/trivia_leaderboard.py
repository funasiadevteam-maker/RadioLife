"""Phase 41 Session 4.5.B — Trivia "Top Brains" leaderboard.

Public endpoint:
    GET /api/stations/{slug}/trivia_leaderboard?window=7d|30d|all&limit=10

Aggregates completed quiz sessions in `game_sessions` filtered by:
  - `source_context.station_slug == slug` OR `source_context_json.station_slug == slug`
  - quiz games (template_id contains "quiz" OR quiz_meta present)
  - status == "completed"
  - completed_at within the requested window

Score = sum of correct answers across all completed sessions of the
player on this station. Falls back to wins (result=="win") count if
no quiz_meta is available so the leaderboard still renders for stations
running non-quiz mini-games.

Public, 60-second in-process cache.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/stations", tags=["trivia-leaderboard"])
log = logging.getLogger("bigfm.trivia_leaderboard")

WINDOW_DAYS = {"7d": 7, "30d": 30, "all": None}
CACHE_TTL_SEC = 60
DEFAULT_LIMIT = 10
MAX_LIMIT     = 50

# (slug, window, limit) -> (timestamp, payload)
_CACHE: dict[tuple[str, str, int], tuple[float, dict]] = {}


def _bust_for_slug(slug: str) -> None:
    for k in list(_CACHE.keys()):
        if k[0] == slug:
            _CACHE.pop(k, None)


def _now() -> datetime: return datetime.now(timezone.utc)


@router.get("/{slug}/trivia_leaderboard")
async def trivia_leaderboard(slug: str, request: Request,
                              window: str = Query(default="7d"),
                              limit: int  = Query(default=DEFAULT_LIMIT,
                                                  ge=1, le=MAX_LIMIT)):
    if window not in WINDOW_DAYS:
        raise HTTPException(400, {
            "code": "validation_error", "field": "window",
            "message": "window must be 7d, 30d or all."})

    cache_key = (slug, window, limit)
    now_ts = time.time()
    cached = _CACHE.get(cache_key)
    if cached and (now_ts - cached[0]) < CACHE_TTL_SEC:
        return cached[1]

    db = request.app.state.db

    # Public, but still confirm the station exists and is published.
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if s.get("status") != "published":
        raise HTTPException(404, {"code": "not_found"})
    if s.get("privacy") and s["privacy"] not in ("public", "unlisted"):
        raise HTTPException(403, {"code": "private_station"})

    days = WINDOW_DAYS.get(window)
    since_iso: Optional[str] = None
    since_dt: Optional[datetime] = None
    if days is not None:
        since_dt  = _now() - timedelta(days=days)
        since_iso = since_dt.isoformat()

    # Match either source_context.station_slug or source_context_json.station_slug.
    match_session: dict = {
        "status": "completed",
        "$or": [
            {"source_context.station_slug":      slug},
            {"source_context_json.station_slug": slug},
        ],
    }
    if since_dt is not None:
        # completed_at can be a datetime OR an ISO string depending on the
        # writer.  Accept both shapes via $or.
        match_session["$and"] = [{"$or": [
            {"completed_at": {"$gte": since_dt}},
            {"completed_at": {"$gte": since_iso}},
        ]}]

    # Player tallies.
    tallies: dict[str, dict] = {}

    async for sess in db.game_sessions.find(match_session):
        uid = sess.get("user_id")
        if not uid:
            continue
        qm  = sess.get("quiz_meta") or {}
        score   = int(qm.get("score") or 0)
        total   = int(qm.get("total") or 0)
        correct = bool(qm.get("correct"))
        is_win  = sess.get("result") == "win"
        # For "dynamic_pool" quizzes each session is a single question
        # so we count "correct=true" as 1 point.  For multi-question
        # quizzes the explicit `score` field carries the count.
        gained_points = 0
        gained_correct = 0
        if total > 0:
            gained_points  = score
            gained_correct = score
        elif correct:
            gained_points  = 1
            gained_correct = 1
        elif is_win:
            # Non-quiz game wins still earn a leaderboard point so the
            # surface isn't empty for stations that only run other games.
            gained_points = 1
        t = tallies.setdefault(uid, {
            "user_id":           uid,
            "score":             0,
            "correct_answers":   0,
            "sessions_played":   0,
            "wins":              0,
            "last_played_at":    None,
        })
        t["score"]           += gained_points
        t["correct_answers"] += gained_correct
        t["sessions_played"] += 1
        if is_win:
            t["wins"] += 1
        # Track the most-recent played-at timestamp for tie-breaking.
        ts = sess.get("completed_at") or sess.get("started_at")
        if ts:
            # Normalize to ISO for comparison.
            try:
                ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            except Exception:
                ts_iso = str(ts)
            if (not t["last_played_at"]) or ts_iso > t["last_played_at"]:
                t["last_played_at"] = ts_iso

    if not tallies:
        payload = {
            "slug":     slug,
            "window":   window,
            "computed_at": _now().isoformat(),
            "top_brains": [],
            "count":    0,
            "note":     "No completed trivia sessions in this window yet."
            if window != "all" else
            "No completed trivia sessions yet.",
        }
        _CACHE[cache_key] = (now_ts, payload)
        return payload

    # Sort: score desc, correct_answers desc, sessions_played desc, last_played_at asc (earliest first wins tie).
    ranked = sorted(tallies.values(),
                     key=lambda r: (
                         -int(r["score"]),
                         -int(r["correct_answers"]),
                         -int(r["sessions_played"]),
                         r["last_played_at"] or "z",
                     ))[:limit]

    uids = [r["user_id"] for r in ranked]
    users_map: dict[str, dict] = {}
    if uids:
        async for u in db.users.find({"user_id": {"$in": uids}},
                                       {"user_id": 1, "name": 1,
                                        "display_name": 1, "avatar_url": 1,
                                        "email": 1, "_id": 0}):
            users_map[u["user_id"]] = u

    top_brains = []
    for idx, r in enumerate(ranked):
        u = users_map.get(r["user_id"]) or {}
        name = (u.get("display_name") or u.get("name")
                 or (u.get("email") or "").split("@")[0]
                 or "Player")
        # Compute accuracy when we have totals.
        accuracy = None
        if r["sessions_played"] > 0:
            denom = r["sessions_played"]
            # If we only have correct_answers and not session-totals,
            # we approximate accuracy = correct / sessions_played.
            accuracy = round(min(1.0, r["correct_answers"] / denom), 3) if denom else None
        top_brains.append({
            "rank":             idx + 1,
            "user_id":          r["user_id"],
            "name":             name,
            "avatar_url":       u.get("avatar_url"),
            "score":            r["score"],
            "correct_answers":  r["correct_answers"],
            "sessions_played":  r["sessions_played"],
            "wins":             r["wins"],
            "last_played_at":   r["last_played_at"],
            "accuracy":         accuracy,
        })

    payload = {
        "slug":         slug,
        "window":       window,
        "computed_at":  _now().isoformat(),
        "top_brains":   top_brains,
        "count":        len(top_brains),
    }
    _CACHE[cache_key] = (now_ts, payload)
    return payload


__all__ = ["router"]
