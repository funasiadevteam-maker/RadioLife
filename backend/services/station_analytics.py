"""Phase 41 Session 5.A — composable analytics helpers for community
stations.

Each helper is a pure async function over `db` and returns a single
metric (or a small structured projection). The `compose_station_analytics`
function orchestrates all of them and is the single source of truth
for the dashboard payload.

We intentionally do most of the heavy lifting in Mongo (`$group` /
`$dateToString`) to keep the Python side small. Aggregations are
cached at the *route* layer (`station_analytics.py`), not here — these
helpers are also re-usable for a future email digest / CSV export.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("bigfm.station_analytics")

WINDOW_DAYS = {"7d": 7, "30d": 30, "90d": 90, "all": None}
DEFAULT_WINDOW = "7d"
TOP_POSTS_LIMIT       = 5
TOP_CITIES_LIMIT      = 5
DAILY_SERIES_MAX_DAYS = 90
SAFETY_TRUNCATE_AT    = 1_000_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_window(window: str) -> tuple[Optional[datetime], datetime, str]:
    """Returns `(starts_at, ends_at, normalized_label)`. For `all`
    `starts_at` is None and downstream Mongo filters omit the date
    bound entirely."""
    if window not in WINDOW_DAYS:
        window = DEFAULT_WINDOW
    end = _now()
    days = WINDOW_DAYS[window]
    if days is None:
        return None, end, "all"
    start = end - timedelta(days=days)
    return start, end, window


def _date_bound_clause(field: str, start: Optional[datetime],
                       end: datetime, datetime_field: bool = True):
    """Build a {$gte, $lt} bound for `field`. When the stored field
    is an ISO-8601 string instead of a native datetime we serialize
    bounds as ISO strings too."""
    if datetime_field:
        if start is None:
            return {"$lt": end}
        return {"$gte": start, "$lt": end}
    s_start = start.isoformat() if start else None
    s_end   = end.isoformat()
    if s_start is None:
        return {"$lt": s_end}
    return {"$gte": s_start, "$lt": s_end}


# ----- listen minutes ------------------------------------------------
async def listen_minutes_total(db, slug: str, start, end) -> dict:
    """Sum `duration_sec` from listener_session_archive in the
    window. Returns minutes + unique listener count."""
    match: dict = {"station_slug": slug}
    if start is not None:
        match["joined_at"] = _date_bound_clause("joined_at", start, end)
    else:
        match["joined_at"] = {"$lt": end}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_seconds":    {"$sum": "$duration_sec"},
            "session_count":    {"$sum": 1},
            "unique_listeners": {"$addToSet": "$user_id"},
        }},
        {"$project": {
            "_id": 0,
            "total_seconds": 1,
            "session_count": 1,
            "unique_listener_count": {"$size": "$unique_listeners"},
        }},
    ]
    out = await db.listener_session_archive.aggregate(pipeline).to_list(1)
    if not out:
        return {"total_minutes": 0, "session_count": 0,
                "unique_listeners": 0}
    row = out[0]
    return {
        "total_minutes":  round((row.get("total_seconds") or 0) / 60),
        "session_count":  row.get("session_count", 0),
        "unique_listeners": row.get("unique_listener_count", 0),
    }


async def peak_concurrent_listeners(db, slug: str, start, end) -> int:
    """Sweep-line: max overlap of (joined_at, ended_at) intervals.
    Skipped (returns 0) when no rows exist."""
    match: dict = {"station_slug": slug}
    if start is not None:
        match["joined_at"] = _date_bound_clause("joined_at", start, end)
    cur = db.listener_session_archive.find(
        match, {"joined_at": 1, "ended_at": 1})
    events: list[tuple[datetime, int]] = []
    async for r in cur:
        j, e = r.get("joined_at"), r.get("ended_at") or r.get("joined_at")
        if not j or not e:
            continue
        events.append((j, +1))
        events.append((e, -1))
    if not events:
        return 0
    events.sort()
    cur_n = 0
    peak  = 0
    for _, delta in events:
        cur_n += delta
        if cur_n > peak:
            peak = cur_n
    return peak


# ----- followers -----------------------------------------------------
async def follower_totals(db, station_id: str, start, end) -> dict:
    """Returns total + delta = follows whose `followed_at` falls in
    the window. `followed_at` is stored as an ISO-8601 string."""
    total = await db.station_followers.count_documents(
        {"station_id": station_id})
    delta_q: dict = {"station_id": station_id}
    if start is not None:
        delta_q["followed_at"] = _date_bound_clause(
            "followed_at", start, end, datetime_field=False)
    delta = await db.station_followers.count_documents(delta_q)
    return {"total": total, "delta": delta}


# ----- post / reaction / comment engagement -------------------------
async def post_engagement(db, slug: str, start, end) -> dict:
    """Counts posts created in the window plus their cached reaction
    totals + comment_counts."""
    match: dict = {"station_slug": slug, "deleted_at": None}
    if start is not None:
        match["created_at"] = _date_bound_clause(
            "created_at", start, end, datetime_field=False)
    pipeline = [
        {"$match": match},
        {"$project": {
            "comment_count":     1,
            "reaction_total":    {"$ifNull": [
                {"$sum": [
                    {"$ifNull": ["$reaction_counts.heart", 0]},
                    {"$ifNull": ["$reaction_counts.fire",  0]},
                    {"$ifNull": ["$reaction_counts.clap",  0]},
                    {"$ifNull": ["$reaction_counts.wow",   0]},
                    {"$ifNull": ["$reaction_counts.skull", 0]},
                ]},
                0,
            ]},
        }},
        {"$group": {
            "_id": None,
            "post_count":      {"$sum": 1},
            "reactions_total": {"$sum": "$reaction_total"},
            "comments_total":  {"$sum": "$comment_count"},
        }},
    ]
    out = await db.station_posts.aggregate(pipeline).to_list(1)
    if not out:
        return {"post_count": 0, "reactions_total": 0, "comments_total": 0}
    return {
        "post_count":      out[0].get("post_count", 0),
        "reactions_total": out[0].get("reactions_total", 0),
        "comments_total":  out[0].get("comments_total", 0),
    }


async def top_posts(db, slug: str, start, end,
                      limit: int = TOP_POSTS_LIMIT) -> list[dict]:
    match: dict = {"station_slug": slug, "deleted_at": None}
    if start is not None:
        match["created_at"] = _date_bound_clause(
            "created_at", start, end, datetime_field=False)
    pipeline = [
        {"$match": match},
        {"$project": {
            "_id": 0,
            "post_id":       "$post_id",
            "body":          "$body",
            "comment_count": "$comment_count",
            "created_at":    "$created_at",
            "reaction_total": {"$ifNull": [
                {"$sum": [
                    {"$ifNull": ["$reaction_counts.heart", 0]},
                    {"$ifNull": ["$reaction_counts.fire",  0]},
                    {"$ifNull": ["$reaction_counts.clap",  0]},
                    {"$ifNull": ["$reaction_counts.wow",   0]},
                    {"$ifNull": ["$reaction_counts.skull", 0]},
                ]},
                0,
            ]},
        }},
        {"$addFields": {
            # Weighted engagement: each comment counts ~3 reactions.
            "engagement_score": {"$add": [
                "$reaction_total",
                {"$multiply": ["$comment_count", 3]},
            ]},
        }},
        {"$sort":  {"engagement_score": -1, "created_at": -1}},
        {"$limit": limit},
    ]
    items: list = []
    async for r in db.station_posts.aggregate(pipeline):
        body = r.get("body") or ""
        items.append({
            "post_id":       r.get("post_id"),
            "body_excerpt":  body[:140] + ("…" if len(body) > 140 else ""),
            "reaction_total": r.get("reaction_total", 0),
            "comment_count":  r.get("comment_count", 0),
            "engagement_score": r.get("engagement_score", 0),
            "created_at":    r.get("created_at"),
        })
    return items


async def top_cities(db, slug: str, start, end,
                      limit: int = TOP_CITIES_LIMIT) -> list[dict]:
    match: dict = {"station_slug": slug}
    if start is not None:
        match["joined_at"] = _date_bound_clause("joined_at", start, end)
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"city":    {"$ifNull": ["$city",    "Unknown"]},
                    "country": {"$ifNull": ["$country", "—"]}},
            "count": {"$sum": 1},
        }},
        {"$sort":  {"count": -1}},
        {"$limit": limit},
    ]
    items: list = []
    async for r in db.listener_session_archive.aggregate(pipeline):
        k = r.get("_id") or {}
        items.append({
            "city":    k.get("city")    or "Unknown",
            "country": k.get("country") or "—",
            "count":   r.get("count", 0),
        })
    return items


# ----- daily series -------------------------------------------------
async def daily_series(db, slug: str, station_id: str,
                          start: datetime, end: datetime) -> list[dict]:
    """Per-day aggregation across listener_session_archive,
    station_posts, station_followers, station_comments. Returns a
    list of dicts ordered ascending by date."""
    # 1) listen_minutes + unique listeners per day
    listen_pipe = [
        {"$match": {"station_slug": slug,
                      "joined_at": {"$gte": start, "$lt": end}}},
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m-%d", "date": "$joined_at"}},
            "minutes":  {"$sum": {"$divide": ["$duration_sec", 60]}},
            "uniques":  {"$addToSet": "$user_id"},
        }},
        {"$project": {
            "_id": 1, "minutes": 1,
            "uniques": {"$size": "$uniques"},
        }},
    ]
    listen_by_day: dict[str, dict] = {}
    async for r in db.listener_session_archive.aggregate(listen_pipe):
        listen_by_day[r["_id"]] = {
            "minutes": round(r.get("minutes") or 0),
            "uniques": r.get("uniques") or 0,
        }

    # 2) posts + reactions + comments per day (sum reactions cached
    #    on the post doc; sum comment_count too).
    posts_pipe = [
        {"$match": {"station_slug": slug, "deleted_at": None,
                      "created_at": {"$gte": start.isoformat(),
                                       "$lt":  end.isoformat()}}},
        {"$addFields": {
            "_date": {"$substr": ["$created_at", 0, 10]},
            "_rtotal": {"$sum": [
                {"$ifNull": ["$reaction_counts.heart", 0]},
                {"$ifNull": ["$reaction_counts.fire",  0]},
                {"$ifNull": ["$reaction_counts.clap",  0]},
                {"$ifNull": ["$reaction_counts.wow",   0]},
                {"$ifNull": ["$reaction_counts.skull", 0]},
            ]},
        }},
        {"$group": {
            "_id": "$_date",
            "posts":     {"$sum": 1},
            "reactions": {"$sum": "$_rtotal"},
            "comments":  {"$sum": "$comment_count"},
        }},
    ]
    posts_by_day: dict[str, dict] = {}
    async for r in db.station_posts.aggregate(posts_pipe):
        posts_by_day[r["_id"]] = {
            "posts":     r.get("posts", 0),
            "reactions": r.get("reactions", 0),
            "comments":  r.get("comments", 0),
        }

    # 3) follow events per day
    foll_pipe = [
        {"$match": {"station_id": station_id,
                      "followed_at": {"$gte": start.isoformat(),
                                          "$lt":  end.isoformat()}}},
        {"$addFields": {"_date": {"$substr": ["$followed_at", 0, 10]}}},
        {"$group": {"_id": "$_date", "n": {"$sum": 1}}},
    ]
    foll_by_day: dict[str, int] = {}
    async for r in db.station_followers.aggregate(foll_pipe):
        foll_by_day[r["_id"]] = r.get("n", 0)

    # Build dense day-by-day list so the chart has no gaps.
    out = []
    d = start
    while d < end:
        ds = d.strftime("%Y-%m-%d")
        lst = listen_by_day.get(ds, {})
        pst = posts_by_day.get(ds, {})
        out.append({
            "date":             ds,
            "listen_minutes":   lst.get("minutes", 0),
            "unique_listeners": lst.get("uniques", 0),
            "new_followers":    foll_by_day.get(ds, 0),
            "posts":            pst.get("posts", 0),
            "reactions":        pst.get("reactions", 0),
            "comments":         pst.get("comments", 0),
        })
        d = d + timedelta(days=1)
    # Cap to avoid 1000-day charts on `all`.
    if len(out) > DAILY_SERIES_MAX_DAYS:
        out = out[-DAILY_SERIES_MAX_DAYS:]
    return out


# ----- business-only --------------------------------------------------
async def business_metrics(db, slug: str, start, end) -> dict:
    """Announcement + TV-poll counts. Returns dict for any station;
    callers should null this out for personal_radio."""
    ann_q: dict = {"station_slug": slug}
    if start is not None:
        ann_q["created_at"] = _date_bound_clause(
            "created_at", start, end, datetime_field=False)
    ann_count = await db.station_announcements.count_documents(ann_q)

    tv_q: dict = {"station_slug": slug}
    if start is not None:
        # tv_poll_daily uses date_str = YYYY-MM-DD
        tv_q["date_str"] = {
            "$gte": start.strftime("%Y-%m-%d"),
            "$lt":  end.strftime("%Y-%m-%d"),
        }
    tv_pipeline = [
        {"$match": tv_q},
        {"$group": {"_id": None, "total": {"$sum": "$count"}}},
    ]
    tv_out = await db.tv_poll_daily.aggregate(tv_pipeline).to_list(1)
    tv_polls = tv_out[0].get("total", 0) if tv_out else 0
    return {
        "announcement_count": ann_count,
        "tv_display_polls":   int(tv_polls),
    }


# ----- composition --------------------------------------------------
async def compose_station_analytics(db, station: dict, window: str) -> dict:
    """Build the single composite payload powering the dashboard. The
    caller is responsible for ownership gating."""
    slug = station["slug"]
    station_id = station["station_id"]
    start, end, normalized = resolve_window(window)
    # Previous window of equal length, for delta computation.
    if start is not None:
        span = end - start
        prev_end   = start
        prev_start = start - span
    else:
        prev_end = prev_start = None

    # Safety: if there are >SAFETY_TRUNCATE_AT archive rows in window,
    # only headline metrics are computed.
    archive_count_q: dict = {"station_slug": slug}
    if start is not None:
        archive_count_q["joined_at"] = {"$gte": start, "$lt": end}
    archive_count = await db.listener_session_archive.count_documents(
        archive_count_q)
    truncated = archive_count > SAFETY_TRUNCATE_AT

    headline_lis = await listen_minutes_total(db, slug, start, end)
    peak         = (0 if truncated
                       else await peak_concurrent_listeners(db, slug, start, end))
    follow       = await follower_totals(db, station_id, start, end)
    engage       = await post_engagement(db, slug, start, end)
    biz = (await business_metrics(db, slug, start, end)
            if station.get("is_business") else None)

    prev_lis     = await listen_minutes_total(db, slug, prev_start, prev_end)
    prev_follow  = await follower_totals(db, station_id, prev_start, prev_end)
    prev_engage  = await post_engagement(db, slug, prev_start, prev_end)

    posts        = await top_posts(db, slug, start, end)
    cities       = await top_cities(db, slug, start, end)
    moods        = await mood_top_tracks(db, slug, station_id, start, end)

    series = []
    if start is not None and not truncated:
        series = await daily_series(db, slug, station_id, start, end)

    return {
        "window":           normalized,
        "window_starts_at": (start.isoformat() if start else None),
        "window_ends_at":   end.isoformat(),
        "truncated":        truncated,
        "headline_metrics": {
            "total_listen_minutes":      headline_lis["total_minutes"],
            "unique_listeners":          headline_lis["unique_listeners"],
            "session_count":             headline_lis["session_count"],
            "peak_concurrent_listeners": peak,
            "followers_total":           follow["total"],
            "followers_delta":           follow["delta"],
            "post_count":                engage["post_count"],
            "reactions_total":           engage["reactions_total"],
            "comments_total":            engage["comments_total"],
        },
        "prev_window_metrics": {
            "total_listen_minutes":  prev_lis["total_minutes"],
            "unique_listeners":      prev_lis["unique_listeners"],
            "followers_delta":       prev_follow["delta"],
            "post_count":            prev_engage["post_count"],
            "reactions_total":       prev_engage["reactions_total"],
            "comments_total":        prev_engage["comments_total"],
        },
        "daily_series":         series,
        "top_posts":            posts,
        "top_listeners_by_city": cities,
        # Phase 41M.B — mood vote roll-up per track for the analytics
        # dashboard's new "Track moods" mini-section. Owner-only path
        # via the existing analytics-route auth gate.
        "mood_top_tracks":      moods,
        "business_only":        biz,
    }


# ─── Phase 41M.B — mood roll-up for analytics dashboard ───────────────
VALID_MOODS_FOR_ANALYTICS = ("chill", "hype", "sad", "party", "focus")


async def mood_top_tracks(db, slug: str, station_id: str,
                            start, end, limit: int = 5) -> list[dict]:
    """Top-N most-voted tracks by mood for this station. Joins to
    `tracks` collection for display title + artist. Returns at most
    `limit` entries — auto-hides cold-start noise via the
    sample_count threshold checked client-side."""
    # Match by station_id; fall back to station_slug if the votes used
    # the slug as the station identifier.
    match: dict = {
        "$or": [{"station_id": station_id}, {"station_slug": slug}],
        "track_id": {"$ne": None},
    }
    if start is not None:
        match["voted_at"] = {"$gte": start, "$lte": end}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":   {"track_id": "$track_id", "mood": "$mood"},
            "count": {"$sum": 1}}},
        {"$group": {
            "_id":   "$_id.track_id",
            "moods": {"$push": {"mood":  "$_id.mood",
                                  "count": "$count"}},
            "total": {"$sum":  "$count"}}},
        {"$sort":  {"total": -1}},
        {"$limit": limit},
    ]
    rows: list = []
    async for row in db.mood_votes.aggregate(pipeline):
        distribution = {m: 0 for m in VALID_MOODS_FOR_ANALYTICS}
        for entry in row.get("moods", []):
            mm = entry.get("mood")
            if mm in distribution:
                distribution[mm] = int(entry.get("count") or 0)
        dominant_mood, dominant_count = max(
            distribution.items(), key=lambda kv: kv[1])
        rows.append({
            "track_id":      row["_id"],
            "distribution":  distribution,
            "dominant_mood": dominant_mood if dominant_count > 0 else None,
            "sample_count":  int(row.get("total") or 0),
        })

    # Hydrate display fields from `tracks`.
    if rows:
        tids = [r["track_id"] for r in rows]
        meta: dict = {}
        async for t in db.tracks.find({"_id": {"$in": tids}},
                                        {"_id": 1, "title": 1, "artist": 1}):
            meta[t["_id"]] = {"title":  t.get("title"),
                                "artist": t.get("artist")}
        for r in rows:
            m = meta.get(r["track_id"]) or {}
            r["title"]  = m.get("title")
            r["artist"] = m.get("artist")
    return rows


async def ensure_analytics_indexes(db) -> dict:
    """Idempotent. Called once from server startup."""
    created = []
    try:
        await db.listener_session_archive.create_index(
            [("station_slug", 1), ("joined_at", -1)],
            name="lsa_slug_joined")
        created.append("lsa_slug_joined")
    except Exception as e:
        log.warning("[analytics] index lsa_slug_joined: %s", e)
    try:
        await db.tv_poll_daily.create_index(
            [("station_slug", 1), ("date_str", -1)],
            name="tvp_slug_date", unique=False)
        created.append("tvp_slug_date")
    except Exception as e:
        log.warning("[analytics] index tvp_slug_date: %s", e)
    try:
        await db.station_followers.create_index(
            [("station_id", 1), ("followed_at", -1)],
            name="sfo_station_followed")
        created.append("sfo_station_followed")
    except Exception as e:
        log.warning("[analytics] index sfo_station_followed: %s", e)
    return {"created": created}
