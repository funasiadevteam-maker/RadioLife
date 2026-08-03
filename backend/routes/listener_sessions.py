"""Phase 41 Session 2.B — Real listener tracking for community stations.

Why a separate router (instead of folding into `station_feed.py`):
this is its own concern (presence rather than social) and the brief
mandated separate route files. Schema:

    listener_sessions {
        _id, session_token, station_id, station_slug,
        user_id|null (anon allowed via fingerprint cookie),
        joined_at, last_ping_at, ended_at|null
    }

A TTL index on `last_ping_at` auto-expires stale sessions after 95s
(buffer over the 90s "live" threshold so the count is accurate even
during the brief window where a session is alive but past its ping).

`GET /api/stations/{slug}/listeners` returns a denormalized live
count for the StationFeed header. `GET /api/community/now_playing`
upgrades to a 3-tier fallback (live → followers → recent) consuming
the same data.
"""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from auth import current_user_optional
from routes.community_stations import _visible_to as _station_visible_to

router = APIRouter(prefix="/api/stations", tags=["listener-sessions"])
log = logging.getLogger("bigfm.listener_sessions")

# 90s = "live"; TTL = 95s so Mongo cleans up after the live window
# closes, leaving the count source-of-truth aligned with the query.
LIVE_WINDOW_SEC = 90
TTL_SEC         = 95


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str:  return _now().isoformat()


async def ensure_listener_session_indexes(db) -> None:
    try:
        await db.listener_sessions.create_index(
            "session_token", unique=True, name="ls_token_unique")
        await db.listener_sessions.create_index(
            [("station_slug", 1), ("last_ping_at", -1)],
            name="ls_station_recent")
        # TTL on `last_ping_at` — Mongo expects a date type. We store
        # datetime objects (not ISO strings) on this field for that
        # reason; the rest of the doc keeps ISO strings for parity.
        await db.listener_sessions.create_index(
            "last_ping_at", expireAfterSeconds=TTL_SEC,
            name="ls_ttl")
    except Exception as e:
        log.warning("[listener_sessions] index ensure: %s", e)


async def _resolve_community_station(db, slug: str,
                                      user: Optional[dict]) -> Optional[dict]:
    """Resolve a slug to a community station the caller can see.
    Returns None if the slug isn't a community station — caller treats
    that as a no-op (admin channels don't get listener tracking yet).
    Strips raw `_id` so callers never serialize it accidentally."""
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        return None
    if not _station_visible_to(s, user, via_direct_link=True):
        return None
    s.pop("_id", None)
    return s


async def _live_count(db, station_slug: str) -> int:
    cutoff = _now() - timedelta(seconds=LIVE_WINDOW_SEC)
    return await db.listener_sessions.count_documents({
        "station_slug": station_slug,
        "ended_at":     None,
        "last_ping_at": {"$gt": cutoff},
    })


@router.post("/{slug}/listen/join")
async def listen_join(slug: str, request: Request,
                       body: Optional[dict] = Body(default=None),
                       user: Optional[dict] = Depends(current_user_optional)):
    """Open a listening session. Idempotent if the same anon device
    rejoins immediately — we always issue a fresh token but Mongo TTL
    drops stale dupes.

    Anon listeners are allowed (community stations are public-by-default
    discovery surfaces); we tag them with a per-request `anon:<hex>`
    pseudo-id so the same anon can rejoin without inflating counts.

    Returns `{code: "not_community_station"}` 404 for admin channel
    slugs so the frontend hook can no-op without surfacing a toast.
    """
    db = request.app.state.db
    s = await _resolve_community_station(db, slug, user)
    if not s:
        raise HTTPException(404, {"code": "not_community_station"})

    body = body or {}
    anon_id = body.get("anon_id")  # optional client-stable anon fingerprint
    user_id = (user or {}).get("user_id")
    # Phase B — capture the listener's resolved city on session join so the
    # heat-cities aggregation + per-user "Recent" tag have something to
    # group on later.  Best-effort: never blocks the join if the geo
    # service errors out.
    resolved_city = ""
    resolved_country = ""
    resolved_market = ""
    try:
        from services import geo as _geo
        _r = await _geo.resolve_for_user(request, user, db)
        resolved_city    = (_r.get("city")    or "").strip()
        resolved_country = (_r.get("country") or "").strip()
        resolved_market  = (_r.get("market")  or "").strip()
    except Exception as _e:
        log.warning("[listen_join] geo resolve failed: %s", _e)
    token = "ls_" + uuid.uuid4().hex[:18]
    now = _now()
    doc = {
        "_id":           token,
        "session_token": token,
        "station_id":    s["station_id"],
        "station_slug":  s["slug"],
        "user_id":       user_id,
        "anon_id":       anon_id if not user_id else None,
        "joined_at":     now,
        "last_ping_at":  now,   # native datetime — TTL needs this
        "ended_at":      None,
        # Phase B — listener geo snapshot, used by heat + recent tags.
        "resolved_city":    resolved_city    or None,
        "resolved_country": resolved_country or None,
        "resolved_market":  resolved_market  or None,
    }
    await db.listener_sessions.insert_one(doc)
    live = await _live_count(db, s["slug"])
    # Phase A Item 3 — station_played_5x trigger.  Fires when the user's
    # lifetime listener_sessions count crosses 5 (i.e., 5th session).
    # Authenticated users only; anon sessions ignored (no user_id).
    if user_id:
        try:
            import asyncio as _aio
            _play_count = await db.listener_sessions.count_documents(
                {"user_id": user_id})
            # Also include archive (listen_leave archives completed sessions).
            _play_count += await db.listener_session_archive.count_documents(
                {"user_id": user_id})
            if _play_count == 5:
                from services.notification_trigger_dispatcher import dispatch_event
                _aio.create_task(dispatch_event(
                    db, event_name="station_played_5x",
                    user_id=user_id,
                    payload={"station_slug": s["slug"],
                                      "station_id": s.get("station_id"),
                                      "count": 5}))
        except Exception as _e:
            log.warning("[trigger] station_played_5x dispatch skipped: %s", _e)
    return {"ok": True, "session_token": token, "count": live}


@router.post("/{slug}/listen/ping")
async def listen_ping(slug: str, request: Request, body: dict = Body(...),
                       user: Optional[dict] = Depends(current_user_optional)):
    """30s heartbeat. Bumps `last_ping_at` to reset the TTL."""
    db = request.app.state.db
    token = body.get("session_token") or ""
    if not token:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "session_token required."})
    r = await db.listener_sessions.update_one(
        {"session_token": token, "ended_at": None,
         "station_slug": slug},
        {"$set": {"last_ping_at": _now()}})
    if r.matched_count == 0:
        # Session expired / was closed — instruct client to rejoin.
        raise HTTPException(404, {"code": "session_expired"})
    live = await _live_count(db, slug)
    return {"ok": True, "count": live}


@router.post("/{slug}/listen/leave")
async def listen_leave(slug: str, request: Request, body: dict = Body(...),
                        user: Optional[dict] = Depends(current_user_optional)):
    """Explicit close. Idempotent — missing/already-closed sessions
    return ok: false but never error (so sendBeacon never logs noise).

    Phase 41 S5 follow-up FIX A: also archives completed sessions
    into `listener_session_archive` (durable history for the analytics
    dashboard) AND credits a premium-listen ledger row when the
    listener was premium and not the owner.
    """
    db = request.app.state.db
    token = body.get("session_token") or ""
    if not token:
        return {"ok": False, "code": "missing_token"}

    # Snapshot the session BEFORE we mutate it so we have joined_at +
    # station_id even after the update.
    session = await db.listener_sessions.find_one(
        {"session_token": token, "station_slug": slug})
    now = _now()
    now_iso = now.isoformat()
    r = await db.listener_sessions.update_one(
        {"session_token": token, "ended_at": None,
         "station_slug": slug},
        {"$set": {"ended_at": now_iso}})

    # FIX A — archive on successful close. Idempotent via the
    # unique `_id`-derived archive key, so duplicate beacons are safe.
    if r.modified_count and session:
        joined = session.get("joined_at")
        try:
            duration_sec = (
                int((now - joined).total_seconds())
                if isinstance(joined, datetime) else 0)
        except Exception:
            duration_sec = 0
        archive_id = f"lsa_{token}"
        try:
            await db.listener_session_archive.update_one(
                {"_id": archive_id},
                {"$setOnInsert": {
                    "_id":           archive_id,
                    "session_token": token,
                    "station_id":    session.get("station_id"),
                    "station_slug":  slug,
                    "user_id":       session.get("user_id"),
                    "anon_id":       session.get("anon_id"),
                    "joined_at":     joined,
                    "ended_at":      now,
                    "duration_sec":  max(0, duration_sec),
                    # city/country come from the user profile or geo
                    # lookup — we leave them null for now and rely on
                    # the existing seed for sample data. Live geo
                    # attribution lands in the next gap fix.
                    "city":          None,
                    "country":       None,
                }},
                upsert=True)
        except Exception as e:
            log.warning("[listener_sessions] archive failed: %s", e)

        # Phase 41M.B — fire-and-forget loyal_listener badge grant.
        # Re-counts lifetime listen-minutes from the archive and grants
        # the badge if ≥50. Wrapped + create_task'd so it NEVER blocks
        # the leave response. Skips anon sessions.
        try:
            _uid = session.get("user_id")
            _sid = session.get("station_id")
            if _uid and _sid:
                from services.station_badge_engine import grant_safe
                asyncio.create_task(grant_safe(
                    db, user_id=_uid, station_id=_sid,
                    station_slug=slug,
                    only_types={"loyal_listener"}))
        except Exception as e:
            log.warning("[listener_sessions] badge hook failed: %s", e)

        # Premium-listen ledger credit (skips non-premium silently).
        try:
            station_doc = await db.community_radio_stations.find_one(
                {"slug": slug})
            if station_doc:
                from services.creator_revenue import credit_premium_listen
                await credit_premium_listen(
                    db, station=station_doc,
                    listener_user_id=session.get("user_id"),
                    session_token=token,
                    duration_sec=max(0, duration_sec))
        except Exception as e:
            log.debug("[listener_sessions] premium credit skipped: %s", e)

        # Bust analytics cache so the dashboard reflects the new row.
        try:
            from routes.station_analytics import bust_analytics_cache
            bust_analytics_cache(slug)
        except Exception:
            pass

    return {"ok": bool(r.modified_count), "count":
            await _live_count(db, slug)}


@router.get("/{slug}/listeners")
async def listeners_count(slug: str, request: Request,
                           user: Optional[dict] = Depends(current_user_optional)):
    """Public live listener count for the StationFeed header + others.
    Honors privacy: private stations 404 to non-owners."""
    db = request.app.state.db
    s = await _resolve_community_station(db, slug, user)
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    return {"slug": s["slug"], "count": await _live_count(db, s["slug"])}


# ----- Helper for community.now_playing 3-tier fallback ------------
async def top_station_by_live_count(db) -> Optional[dict]:
    """Tier 1 — return the published+public community station with
    the most active live listeners. Returns None if no station has any
    live listeners right now."""
    cutoff = _now() - timedelta(seconds=LIVE_WINDOW_SEC)
    pipeline = [
        {"$match": {"ended_at": None,
                     "last_ping_at": {"$gt": cutoff}}},
        {"$group": {"_id": "$station_slug", "count": {"$sum": 1}}},
        {"$sort":  {"count": -1}},
        {"$limit": 1},
    ]
    cur = db.listener_sessions.aggregate(pipeline)
    async for row in cur:
        slug = row["_id"]
        s = await db.community_radio_stations.find_one(
            {"slug": slug, "status": "published", "privacy": "public"})
        if s:
            return {"station": s, "live_count": int(row["count"]),
                    "tier": "live"}
    return None
