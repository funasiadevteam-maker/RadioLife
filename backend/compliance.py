"""RadioLife Phase 2 — Compliance + Playback Logs + Rolling Windows.

Non-interactive radio compliance (CRTC/FCC-style) rules applied server-side:

1. 4 tracks per artist per rolling 3 hours per user
2. 3 tracks per album per rolling 3 hours per user
3. Never 3 consecutive same-artist tracks (last 2 are hard-banned)
4. 6 skips per rolling 1 hour per user

Also exposes a thin event logger that other modules use to write to the
`playback_logs` collection. Indexes are ensured at startup.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


SKIP_LIMIT = 6
SKIP_WINDOW_SEC = 3600
ARTIST_LIMIT_3H = 4
ALBUM_LIMIT_3H = 3
ROLLING_WINDOW_SEC = 3 * 3600
CONSECUTIVE_ARTIST_BAN = 2  # never 3-in-a-row → last 2 are banned

# Premium tier bypasses the 1-hour skip limit. We still LOG every skip event
# so analytics + abuse detection can see the activity.
PREMIUM_UNLIMITED_SKIPS = True


def is_premium_user(user_or_id) -> bool:
    """Accepts either the full user doc or just the is_premium flag."""
    if isinstance(user_or_id, dict):
        return bool(user_or_id.get("is_premium", False))
    return bool(user_or_id)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_compliance_indexes(db) -> None:
    await db.playback_logs.create_index([("user_id", 1), ("timestamp", -1)])
    await db.playback_logs.create_index([("user_id", 1), ("event", 1), ("timestamp", -1)])
    await db.shares.create_index("share_id", unique=True)
    await db.shares.create_index([("user_id", 1), ("created_at", -1)])


async def log_event(
    db,
    *,
    user_id: str,
    session_id: Optional[str],
    segment_id: Optional[str],
    track_id: Optional[str],
    channel_slug: Optional[str],
    event: str,
    played_for_sec: float = 0.0,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    await db.playback_logs.insert_one({
        "user_id": user_id,
        "session_id": session_id,
        "segment_id": segment_id,
        "track_id": track_id,
        "channel_slug": channel_slug,
        "event": event,
        "played_for_sec": float(played_for_sec or 0.0),
        "metadata": metadata or {},
        "timestamp": _now(),
    })


async def recent_played_track_ids(db, user_id: str, since_sec: int) -> List[str]:
    cutoff = _now() - timedelta(seconds=since_sec)
    cur = db.playback_logs.find(
        {"user_id": user_id, "event": "play_start", "timestamp": {"$gte": cutoff}},
        {"track_id": 1, "_id": 0},
    )
    out: List[str] = []
    async for d in cur:
        if d.get("track_id"):
            out.append(d["track_id"])
    return out


async def banned_artists_albums(
    db, user_id: str, all_tracks: List[dict]
) -> tuple[set[str], set[str]]:
    """Return (artists_at_cap, albums_at_cap) within the rolling 3-hour window."""
    cutoff = _now() - timedelta(seconds=ROLLING_WINDOW_SEC)
    cur = db.playback_logs.find(
        {"user_id": user_id, "event": "play_start", "timestamp": {"$gte": cutoff}},
        {"track_id": 1, "_id": 0},
    )
    played_ids: List[str] = []
    async for d in cur:
        if d.get("track_id"):
            played_ids.append(d["track_id"])
    if not played_ids:
        return set(), set()
    id_to_track = {t["_id"]: t for t in all_tracks}
    artist_counts: Dict[str, int] = {}
    album_counts: Dict[str, int] = {}
    for tid in played_ids:
        t = id_to_track.get(tid)
        if not t:
            continue
        a = t.get("artist")
        al = t.get("album")
        if a:
            artist_counts[a] = artist_counts.get(a, 0) + 1
        if al:
            album_counts[al] = album_counts.get(al, 0) + 1
    artists_at_cap = {a for a, n in artist_counts.items() if n >= ARTIST_LIMIT_3H}
    albums_at_cap = {a for a, n in album_counts.items() if n >= ALBUM_LIMIT_3H}
    return artists_at_cap, albums_at_cap


async def consecutive_artists_to_block(db, user_id: str) -> List[str]:
    """Return the last `CONSECUTIVE_ARTIST_BAN` artists' names (most-recent first).
    These will be hard-banned for the next pick."""
    cur = db.playback_logs.find(
        {"user_id": user_id, "event": "play_start"}
    ).sort("timestamp", -1).limit(CONSECUTIVE_ARTIST_BAN + 1)
    artists: List[str] = []
    async for d in cur:
        artists.append(d.get("metadata", {}).get("artist", ""))
    # Only ban consecutive same-artist if the last N are the SAME artist
    # The spec is "never 3 consecutive same-artist" so if last 2 == same, ban that artist
    if len(artists) >= 2 and artists[0] and artists[0] == artists[1]:
        return [artists[0]]
    if artists and artists[0]:
        return []  # last 1 is not enough to risk a 3-streak
    return []


async def skip_state(db, user_id: str, *, is_premium: bool = False) -> Dict[str, Any]:
    """Return {used, limit, window_sec, oldest_skip_at, reset_in_sec}.

    Premium users get unlimited=True and never have `exhausted=True`. The
    `used` field is still populated for analytics.
    """
    cutoff = _now() - timedelta(seconds=SKIP_WINDOW_SEC)
    cur = db.playback_logs.find(
        {"user_id": user_id, "event": "skip", "timestamp": {"$gte": cutoff}},
        {"timestamp": 1, "_id": 0},
    ).sort("timestamp", 1)
    times: List[datetime] = []
    async for d in cur:
        ts = d.get("timestamp")
        if isinstance(ts, str):
            try: ts = datetime.fromisoformat(ts)
            except Exception: ts = None
        if ts is not None:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            times.append(ts)
    used = len(times)
    if is_premium and PREMIUM_UNLIMITED_SKIPS:
        return {
            "used": used,
            "limit": -1,
            "window_sec": SKIP_WINDOW_SEC,
            "reset_in_sec": 0,
            "remaining": -1,
            "exhausted": False,
            "unlimited": True,
        }
    reset_in = 0
    if used >= SKIP_LIMIT and times:
        reset_at = times[0] + timedelta(seconds=SKIP_WINDOW_SEC)
        reset_in = int(max(0, (reset_at - _now()).total_seconds()))
    return {
        "used": used,
        "limit": SKIP_LIMIT,
        "window_sec": SKIP_WINDOW_SEC,
        "reset_in_sec": reset_in,
        "remaining": max(0, SKIP_LIMIT - used),
        "exhausted": used >= SKIP_LIMIT,
        "unlimited": False,
    }


async def shares_count_today(db, user_id: str) -> int:
    cutoff = _now() - timedelta(hours=24)
    return await db.shares.count_documents({"user_id": user_id, "created_at": {"$gte": cutoff}})
