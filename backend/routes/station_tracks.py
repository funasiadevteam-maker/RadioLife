"""Phase D — User-station song picker + content moderation.

Adds an explicit per-station track pool (`station_tracks` join
collection) on top of the existing `db.tracks` catalog.  Two upstream
mechanisms for a station owner to populate their pool:

  (a) **Pick from catalog** — full-text + filtered search of
        `db.tracks` with `add` / `remove` / `reorder` endpoints.

  (b) **Upload** — multipart audio file → dedupe via the canonical
        `services.track_dedupe.find_duplicate` (ISRC > file_hash >
        title+artist+duration±2s) → if novel, async moderation pipeline
        (`services.track_moderation_pipeline`) decides one of four
        outcomes: `auto_approved`, `explicit_auto_flagged`,
        `pending_admin_review`, or `rejected`.

Admin moderation: extends the existing Phase 19B unified queue with a
`track_moderation` content_type, plus dedicated approve / reject
action endpoints under `/api/admin/moderation/tracks/...`.

Compliance:
  • Explicit tracks are blocked from `audience="general"` stations
    with HTTP 400 `code="explicit_blocked"`.
  • Upload rate limit: 5/hour (free), 20/hour (premium).  Uses the
    canonical `track_upload_rate_limits` TTL collection (mirrors
    `game_rate_limits` shape from `services/games_v2.py`).
  • Owner gate on every owner-facing route; admin gate on the
    moderation queue + approve/reject.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                                          HTTPException, Query, Request, UploadFile)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services.track_dedupe import find_duplicate
from services.track_moderation_pipeline import (run_moderation_pipeline,
                                                                                              ensure_phase_d_indexes)

log = logging.getLogger("bigfm.station_tracks")

router = APIRouter(prefix="/api/stations", tags=["station-tracks"])
admin_router = APIRouter(prefix="/api/admin/moderation",
                                                    tags=["admin-moderation-tracks"])

# ───────────────────────────────────────────────────────────── constants
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024     # 50 MB

RATE_LIMIT_PER_HOUR = {"free": 5, "premium": 20}

# Upload temp + final dir.  Reuses the same TRACKS_DIR convention so
# admin tracks and user uploads sit alongside each other.
STORAGE_ROOT = Path(os.environ.get("BIGFM_STORAGE_DIR", "/app/backend/storage"))
UPLOAD_TMP = STORAGE_ROOT / "uploads_tmp"
UPLOAD_FINAL = STORAGE_ROOT / "tracks"
UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
UPLOAD_FINAL.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _strip_mongo(doc: dict) -> dict:
    if not doc:
        return doc
    out = dict(doc)
    out.pop("_id", None)
    return out


async def _get_station_or_404(db, slug: str) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "station_not_found"})
    return s


def _require_owner(station: dict, user: dict) -> None:
    if not user or station.get("owner_user_id") != user.get("user_id"):
        # Admin override (so admin moderation flows aren't blocked).
        if not (user and user.get("is_admin")):
            raise HTTPException(403, {"code": "not_station_owner"})


def _station_audience(station: dict) -> str:
    return station.get("audience") or "general"


# ─────────────────────────────────────────────────────── rate limiter
async def _check_rate_limit(db, user: dict) -> None:
    tier = "premium" if user.get("is_premium") else "free"
    limit = RATE_LIMIT_PER_HOUR[tier]
    bucket_hour = int(_now().timestamp() // 3600)
    bucket_key = f"upload:{user['user_id']}:{bucket_hour}"
    bucket = await db.track_upload_rate_limits.find_one({"_id": bucket_key})
    if bucket and (bucket.get("count") or 0) >= limit:
        # Mongo round-trips datetimes without tzinfo — restore aware for the
        # subtraction so we don't trip 'can't subtract naive and aware'.
        ttl = bucket.get("ttl_at") or _now()
        if isinstance(ttl, datetime) and ttl.tzinfo is None:
            ttl = ttl.replace(tzinfo=timezone.utc)
        retry_in = int((ttl - _now()).total_seconds())
        raise HTTPException(
            429,
            {"code": "rate_limited",
              "message": f"Upload rate limit of {limit}/hour reached. Try again in "
                                  f"~{max(60, retry_in)}s.",
              "tier": tier,
              "limit": limit,
              "retry_after_sec": max(60, retry_in)},
        )
    await db.track_upload_rate_limits.update_one(
        {"_id": bucket_key},
        {"$inc": {"count": 1},
          "$setOnInsert": {"user_id": user["user_id"], "tier": tier,
                                          "ttl_at": _now() + timedelta(hours=1, minutes=5)}},
        upsert=True,
    )


# ────────────────────────────────────────────────────────────── search
@router.get("/{slug}/catalog/search")
async def catalog_search(
    slug: str,
    request: Request,
    q: str = Query("", max_length=160),
    genre: Optional[str] = Query(None, max_length=80),
    mood: Optional[str] = Query(None, max_length=80),
    language: Optional[str] = Query(None, max_length=80),
    era: Optional[str] = Query(None, regex=r"^(?:\d{4}(?:-\d{4})?|\d{4}s|all)?$"),
    explicit: bool = Query(False, description="Include explicit tracks"),
    page: int = Query(1, ge=1, le=200),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_user),
):
    """Owner / admin catalog search.  Full-text on title/artist/album
    plus structured filters.  Returns `{tracks, total, page, has_more}`."""
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    # Filters
    mongo_q: Dict[str, Any] = {"status": "active"}
    # Explicit gating — driven by both query flag AND station audience.
    audience = _station_audience(station)
    if not explicit or audience != "adult":
        # By default hide explicit; only adult stations may opt in.
        mongo_q["$or"] = [
            {"explicit_flag": {"$exists": False}},
            {"explicit_flag": False},
        ]
    if q:
        # Cheap regex search; tracks collection is < 100k rows in Phase D.
        # A text index can be introduced later if needed.
        pattern = {"$regex": q.strip(), "$options": "i"}
        mongo_q["$and"] = [{"$or": [
            {"title": pattern},
            {"artist": pattern},
            {"album": pattern},
        ]}]
    if genre:
        mongo_q["genre"] = {"$regex": f"^{genre.strip()}$", "$options": "i"}
    if mood:
        mongo_q["mood"] = {"$regex": f"^{mood.strip()}$", "$options": "i"}
    if language:
        mongo_q["language"] = {"$regex": f"^{language.strip()}$", "$options": "i"}
    if era and era != "all":
        # Era takes `1990s` or `1990-1999` or `1990`.
        if "-" in era:
            lo, hi = era.split("-", 1)
            mongo_q["year"] = {"$gte": int(lo), "$lte": int(hi)}
        elif era.endswith("s"):
            decade = int(era[:-1])
            mongo_q["year"] = {"$gte": decade, "$lte": decade + 9}
        else:
            mongo_q["year"] = int(era)
    total = await db.tracks.count_documents(mongo_q)
    skip = (page - 1) * limit
    cur = db.tracks.find(mongo_q, {
        "_id": 1, "title": 1, "artist": 1, "album": 1, "duration_sec": 1,
        "genre": 1, "mood": 1, "language": 1, "year": 1, "energy_level": 1,
        "explicit_flag": 1, "vibe_tags": 1,
    }).sort([("title", 1)]).skip(skip).limit(limit)
    tracks: List[dict] = []
    async for t in cur:
        tracks.append({
            "track_id": t["_id"],
            "title": t.get("title"),
            "artist": t.get("artist"),
            "album": t.get("album"),
            "duration_sec": t.get("duration_sec"),
            "genre": t.get("genre"),
            "mood": t.get("mood"),
            "language": t.get("language"),
            "energy_level": t.get("energy_level"),
            "year": t.get("year"),
            "explicit_flag": bool(t.get("explicit_flag", False)),
            "vibe_tags": t.get("vibe_tags") or [],
        })
    return {
        "tracks": tracks,
        "total": total,
        "page": page,
        "has_more": (skip + len(tracks)) < total,
        "audience": audience,
    }


# ─────────────────────────────────────────────────────── add / remove
class AddTracksIn(BaseModel):
    track_ids: List[str] = Field(min_length=1, max_length=100)


@router.post("/{slug}/tracks/add")
async def add_tracks(
    slug: str,
    body: AddTracksIn,
    request: Request,
    user: dict = Depends(current_user),
):
    """Append one or more catalog tracks to the station pool.  Explicit
    tracks blocked from general-audience stations with HTTP 400."""
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    audience = _station_audience(station)
    # Validate every track exists + check explicit gating.
    track_docs = []
    async for t in db.tracks.find(
        {"_id": {"$in": body.track_ids}, "status": "active"},
        {"_id": 1, "title": 1, "explicit_flag": 1},
    ):
        track_docs.append(t)
    found_ids = {t["_id"] for t in track_docs}
    missing = [tid for tid in body.track_ids if tid not in found_ids]
    if missing:
        raise HTTPException(
            404,
            {"code": "track_not_found",
              "missing_track_ids": missing,
              "message": f"{len(missing)} track(s) missing or inactive."},
        )
    explicit_violations = [t for t in track_docs
                                                  if t.get("explicit_flag") and audience != "adult"]
    if explicit_violations:
        raise HTTPException(
            400,
            {"code": "explicit_blocked",
              "message": "Explicit tracks can only be added to audience='adult' stations.",
              "blocked_track_ids": [t["_id"] for t in explicit_violations],
              "current_audience": audience},
        )
    # Phase 42-F.6 — enforce pool cap before mutating.  Best-effort import:
    # if the helper file is missing on an older deploy, fall through to
    # the legacy unbounded behaviour.
    try:
        from routes.community_library import assert_under_pool_cap
        await assert_under_pool_cap(
            db, station_id=station["station_id"], user=user,
            incoming=len(track_docs))
    except HTTPException:
        raise
    except Exception:
        pass
    # Compute next sort index.
    sort_doc = await db.station_tracks.find_one(
        {"station_id": station["station_id"]},
        sort=[("sort_index", -1)])
    next_sort = ((sort_doc or {}).get("sort_index") or 0) + 1
    added_ids: List[str] = []
    for t in track_docs:
        join_id = f"stt_{station['station_id']}_{t['_id']}"
        try:
            await db.station_tracks.insert_one({
                "_id": join_id,
                "station_id": station["station_id"],
                "station_slug": station["slug"],
                "track_id": t["_id"],
                "added_at": _iso(),
                "added_by": user["user_id"],
                "sort_index": next_sort,
                "source": "catalog_add",
            })
            added_ids.append(t["_id"])
            next_sort += 1
        except Exception as e:
            if "duplicate key" in str(e).lower():
                continue   # already on station — idempotent
            raise
    pool = await _list_station_tracks(db, station)
    return {"ok": True, "added": added_ids, "skipped_duplicates":
                    [tid for tid in body.track_ids if tid not in added_ids
                      and tid in found_ids],
                  "pool_size": len(pool),
                  "pool": pool}


@router.delete("/{slug}/tracks/{track_id}")
async def remove_track(
    slug: str,
    track_id: str,
    request: Request,
    user: dict = Depends(current_user),
):
    """Owner removes a track from their station pool (does NOT delete
    from the catalog)."""
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    res = await db.station_tracks.delete_one({
        "station_id": station["station_id"],
        "track_id": track_id,
    })
    if not res.deleted_count:
        raise HTTPException(404, {"code": "not_on_station"})
    return {"ok": True, "removed": track_id}


class ReorderIn(BaseModel):
    ordered_track_ids: List[str] = Field(min_length=0, max_length=2000)


@router.patch("/{slug}/tracks/reorder")
async def reorder_tracks(
    slug: str,
    body: ReorderIn,
    request: Request,
    user: dict = Depends(current_user),
):
    """Re-sort the station pool.  Any track NOT in `ordered_track_ids`
    is moved to the bottom in its current relative order (so partial
    re-orders don't accidentally orphan tracks)."""
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    current = []
    async for r in db.station_tracks.find(
        {"station_id": station["station_id"]}).sort("sort_index", 1):
        current.append(r["track_id"])
    seen = set(body.ordered_track_ids)
    tail = [t for t in current if t not in seen]
    final_order = list(body.ordered_track_ids) + tail
    for idx, tid in enumerate(final_order, start=1):
        await db.station_tracks.update_one(
            {"station_id": station["station_id"], "track_id": tid},
            {"$set": {"sort_index": idx, "reordered_at": _iso()}},
        )
    pool = await _list_station_tracks(db, station)
    return {"ok": True, "pool": pool, "pool_size": len(pool)}


# ───────────────────────────────────────────────────────────── list
@router.get("/{slug}/tracks")
async def list_station_tracks(
    slug: str,
    request: Request,
    user: dict = Depends(current_user),
):
    """Owner / admin lists their station pool (with full track details
    joined from `db.tracks`)."""
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    pool = await _list_station_tracks(db, station)
    return {"pool": pool, "pool_size": len(pool),
                  "audience": _station_audience(station)}


async def _list_station_tracks(db, station: dict) -> List[dict]:
    rows = []
    async for r in db.station_tracks.find(
        {"station_id": station["station_id"]}).sort("sort_index", 1):
        rows.append(r)
    ids = [r["track_id"] for r in rows]
    track_map: Dict[str, dict] = {}
    if ids:
        async for t in db.tracks.find(
            {"_id": {"$in": ids}},
            {"_id": 1, "title": 1, "artist": 1, "album": 1,
              "duration_sec": 1, "genre": 1, "mood": 1, "language": 1,
              "year": 1, "energy_level": 1, "explicit_flag": 1,
              "vibe_tags": 1},
        ):
            track_map[t["_id"]] = t
    out: List[dict] = []
    for r in rows:
        t = track_map.get(r["track_id"]) or {}
        out.append({
            "track_id": r["track_id"],
            "title": t.get("title") or "(deleted)",
            "artist": t.get("artist"),
            "album": t.get("album"),
            "duration_sec": t.get("duration_sec"),
            "explicit_flag": bool(t.get("explicit_flag", False)),
            "genre": t.get("genre"),
            "mood": t.get("mood"),
            "language": t.get("language"),
            "year": t.get("year"),
            "sort_index": r["sort_index"],
            "added_at": r.get("added_at"),
            "added_by": r.get("added_by"),
            "source": r.get("source"),
        })
    return out


# ───────────────────────────────────────────────────────────── audience
class AudienceIn(BaseModel):
    audience: str = Field(pattern="^(general|adult)$")


@router.patch("/{slug}/audience")
async def patch_audience(
    slug: str,
    body: AudienceIn,
    request: Request,
    user: dict = Depends(current_user),
):
    """Owner toggles station audience.  Flipping `adult → general` does
    NOT auto-purge explicit tracks already on the station — admins are
    expected to handle that via the moderation queue if needed."""
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    await db.community_radio_stations.update_one(
        {"slug": slug},
        {"$set": {"audience": body.audience,
                          "updated_at": _iso()}},
    )
    return {"ok": True, "slug": slug, "audience": body.audience}


# ───────────────────────────────────────────────────────────── upload
@router.post("/{slug}/tracks/upload")
async def upload_track(
    slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    artist: Optional[str] = Form(None),
    album: Optional[str] = Form(None),
    lyrics: Optional[str] = Form(None),
    confirmed_duplicate: bool = Form(False),
    user: dict = Depends(current_user),
):
    """Multipart upload → stage 1 (hash + ffprobe + ID3) → stage 2
    (dedupe) → if novel, stage 3 (async moderation pipeline) → 202.

    Returns:
      • 200 `{action:"already_in_catalog", track_id, added_to_station}`
            when ISRC / file-hash dedupe matches and the existing track
            is auto-added to the station pool.
      • 409 `{code:"possible_duplicate", candidate_track_id, ...}` when
            fuzzy title+artist+duration dedupe matches.  Client should
            confirm by re-POSTing with `confirmed_duplicate=true` (then
            we add the candidate to the station and skip moderation) or
            `force_new=true` (skip dedupe and run moderation) — for
            simplicity Phase D only honours `confirmed_duplicate`.
      • 202 `{moderation_job_id, status:"pending"}` on the happy path.
    """
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    # Phase 42-F.6 — enforce pool cap *before* writing to disk so we never
    # accept a file we'd reject after ffprobe.  Existing in-flight
    # moderation slots that haven't landed in station_tracks yet are not
    # counted; that's acceptable for the 10/100 caps.
    try:
        from routes.community_library import assert_under_pool_cap
        await assert_under_pool_cap(
            db, station_id=station["station_id"], user=user,
            incoming=1)
    except HTTPException:
        raise
    except Exception:
        pass
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            {"code": "unsupported_format",
              "allowed": sorted(ALLOWED_EXTENSIONS)},
        )
    # Rate-limit BEFORE we touch disk.
    await _check_rate_limit(db, user)

    # Stage 1 — stream to temp + hash chunk-by-chunk.
    tmp_id = uuid.uuid4().hex[:14]
    tmp_path = UPLOAD_TMP / f"{tmp_id}{ext}"
    hasher = hashlib.sha256()
    total_bytes = 0
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    out.close()
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        {"code": "file_too_large",
                          "max_bytes": MAX_UPLOAD_BYTES,
                          "message": "File exceeds 50 MB."},
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        log.warning("[upload] stage1 ingest failed: %s", e)
        raise HTTPException(500, {"code": "ingest_failed", "message": str(e)})
    file_hash = hasher.hexdigest()

    # ffprobe + ID3 — lazy imports to avoid eager-loading the heavy
    # audio_pipeline module on cold-start.
    try:
        from audio_pipeline import ffprobe_info
        info = await asyncio.to_thread(ffprobe_info, str(tmp_path))
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, {"code": "ffprobe_failed",
                                                          "message": str(e)})
    duration_sec = info.get("duration_sec")
    filename_stem = Path(file.filename or "").stem
    title_final = (title or "").strip() or filename_stem or "Untitled"
    # Auto-tag (best-effort: returns empty meta if OpenAI/network down).
    try:
        from auto_tagger import auto_tag as run_auto_tag
        from server import openai_client  # type: ignore
        tag_meta = await asyncio.to_thread(
            run_auto_tag, openai_client, str(tmp_path),
            title_final, (artist or "").strip() or None)
    except Exception as e:
        log.info("[upload] auto-tag skipped (%s): %s", file.filename, e)
        tag_meta = {}

    # Stage 2 — dedupe cascade.
    dup = await find_duplicate(
        db, file_hash=file_hash,
        isrc=tag_meta.get("isrc"),
        title=tag_meta.get("title") or title_final,
        artist=tag_meta.get("artist") or artist,
        duration_sec=duration_sec,
    )
    if dup and dup["matched_rule"] in ("isrc", "file_hash"):
        # Exact match — clean up temp and short-circuit.
        tmp_path.unlink(missing_ok=True)
        added = await _add_to_station_with_explicit_check(
            db, station=station, track_id=dup["track_id"],
            added_by=user["user_id"], source="upload_dedupe")
        return {
            "action": "already_in_catalog",
            "track_id": dup["track_id"],
            "matched_rule": dup["matched_rule"],
            "candidate_title": dup["title"],
            "candidate_artist": dup["artist"],
            "added_to_station": added["ok"],
            "add_blocked_reason": added.get("reason"),
        }
    if dup and dup["matched_rule"] == "title_artist_duration" and not confirmed_duplicate:
        tmp_path.unlink(missing_ok=True)
        return {
            "action": "possible_duplicate",
            "code": "possible_duplicate",
            "candidate_track_id": dup["track_id"],
            "candidate_title": dup["title"],
            "candidate_artist": dup["artist"],
            "matched_rule": dup["matched_rule"],
            "next": ("To use the existing track, re-POST with "
                          "confirmed_duplicate=true.  To upload a different "
                          "song with the same title/artist, change the title "
                          "or contact admin moderation."),
        }
    if dup and dup["matched_rule"] == "title_artist_duration" and confirmed_duplicate:
        tmp_path.unlink(missing_ok=True)
        added = await _add_to_station_with_explicit_check(
            db, station=station, track_id=dup["track_id"],
            added_by=user["user_id"], source="upload_confirmed")
        return {
            "action": "already_in_catalog",
            "track_id": dup["track_id"],
            "matched_rule": dup["matched_rule"],
            "added_to_station": added["ok"],
            "add_blocked_reason": added.get("reason"),
        }

    # Move tmp → final.
    final_path = UPLOAD_FINAL / f"{tmp_id}{ext}"
    try:
        tmp_path.rename(final_path)
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, {"code": "finalize_failed",
                                                          "message": str(e)})

    # Stage 3 — queue moderation job.
    job_id = _new_id("modjob")
    await db.track_moderation_jobs.insert_one({
        "_id": job_id,
        "job_id": job_id,
        "user_id": user["user_id"],
        "station_slug": slug,
        "station_id": station["station_id"],
        "status": "pending",
        "file_hash": file_hash,
        "final_file_path": str(final_path),
        "filename_orig": file.filename,
        "filename_stem": filename_stem,
        "duration_sec": duration_sec,
        "candidate_title": title_final,
        "candidate_artist": (artist or tag_meta.get("artist") or None),
        "candidate_album": (album or tag_meta.get("album") or None),
        "candidate_lyrics": (lyrics or None),
        "candidate_tag_meta": tag_meta or {},
        "created_at": _iso(),
        "decided_at": None,
        "target_track_id": None,
        "rejection_reason": None,
    })

    # Kick the pipeline asynchronously and return 202.
    background_tasks.add_task(_run_pipeline_safely, request.app.state.db, job_id)

    # 202 Accepted — request accepted, processing async.  The synchronous
    # dedupe shortcuts above use the default 200 because they have a
    # final result; this branch enqueues background work so the correct
    # HTTP semantic is 202 and the client should poll `poll_url`.
    return JSONResponse(
        status_code=202,
        content={
            "action": "moderation_queued",
            "moderation_job_id": job_id,
            "status": "pending",
            "poll_url": f"/api/stations/{slug}/moderation-jobs/{job_id}",
            "estimated_seconds": 10,
        },
    )


async def _run_pipeline_safely(db, job_id: str) -> None:
    """Background wrapper — guarantees the job moves out of `pending`
    even on unexpected errors so the client poll doesn't hang."""
    try:
        await run_moderation_pipeline(db, job_id=job_id)
    except Exception as e:
        log.exception("[upload] pipeline error for job=%s: %s", job_id, e)
        await db.track_moderation_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "pending_admin_review",
                              "decision_reason": f"pipeline_error:{e}",
                              "decided_at": _iso()}},
        )


async def _add_to_station_with_explicit_check(
    db, *,
    station: dict,
    track_id: str,
    added_by: str,
    source: str,
) -> dict:
    """Helper for dedupe-path inserts.  Returns
    `{"ok": bool, "reason": Optional[str]}`."""
    t = await db.tracks.find_one(
        {"_id": track_id, "status": "active"},
        {"_id": 1, "explicit_flag": 1})
    if not t:
        return {"ok": False, "reason": "track_not_active"}
    audience = _station_audience(station)
    if t.get("explicit_flag") and audience != "adult":
        return {"ok": False, "reason": "explicit_blocked"}
    sort_doc = await db.station_tracks.find_one(
        {"station_id": station["station_id"]},
        sort=[("sort_index", -1)])
    next_sort = ((sort_doc or {}).get("sort_index") or 0) + 1
    join_id = f"stt_{station['station_id']}_{track_id}"
    try:
        await db.station_tracks.insert_one({
            "_id": join_id,
            "station_id": station["station_id"],
            "station_slug": station["slug"],
            "track_id": track_id,
            "added_at": _iso(),
            "added_by": added_by,
            "sort_index": next_sort,
            "source": source,
        })
        return {"ok": True}
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return {"ok": True, "reason": "already_on_station"}
        return {"ok": False, "reason": str(e)}


# ───────────────────────────────────────────────────── job status poll
@router.get("/{slug}/moderation-jobs/{job_id}")
async def get_moderation_job(
    slug: str,
    job_id: str,
    request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    station = await _get_station_or_404(db, slug)
    _require_owner(station, user)
    job = await db.track_moderation_jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(404, {"code": "job_not_found"})
    if job.get("station_slug") != slug:
        raise HTTPException(403, {"code": "job_belongs_to_other_station"})
    return _public_job_view(job)


def _public_job_view(job: dict) -> dict:
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "decision_reason": job.get("decision_reason"),
        "moderation_verdict": job.get("moderation_verdict"),
        "moderation_categories": job.get("moderation_categories") or [],
        "moderation_score": job.get("moderation_score"),
        "target_track_id": job.get("target_track_id"),
        "candidate_title": job.get("candidate_title"),
        "candidate_artist": job.get("candidate_artist"),
        "duration_sec": job.get("duration_sec"),
        "explicit_flag": bool(job.get("explicit_flag", False)),
        "rejection_reason": job.get("rejection_reason"),
        "created_at": job.get("created_at"),
        "decided_at": job.get("decided_at"),
    }


# ───────────────────────────────────────────────────── admin endpoints
@admin_router.get("/tracks")
async def admin_list_track_moderation(
    request: Request,
    status: str = Query("pending_admin_review",
                                            regex=r"^(?:pending_admin_review|approved|rejected|all)$"),
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(50, ge=1, le=200),
    _a: dict = Depends(require_admin),
):
    """Admin moderation queue — filterable by status."""
    db = request.app.state.db
    q: Dict[str, Any] = {}
    if status != "all":
        q["status"] = status
    total = await db.track_moderation_jobs.count_documents(q)
    skip = (page - 1) * limit
    cur = db.track_moderation_jobs.find(q).sort("created_at", -1).skip(skip).limit(limit)
    items: List[dict] = []
    async for j in cur:
        v = _public_job_view(j)
        v["user_id"] = j.get("user_id")
        v["station_slug"] = j.get("station_slug")
        v["final_file_path"] = j.get("final_file_path")
        items.append(v)
    return {"items": items, "total": total, "page": page,
                  "has_more": (skip + len(items)) < total}


class AdminRejectIn(BaseModel):
    reason: str = Field(min_length=4, max_length=600)


@admin_router.post("/tracks/{job_id}/approve")
async def admin_approve_track(
    job_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Admin approves a flagged track — inserts catalog row with
    `explicit_flag=True` (we conservatively mark all admin-approved
    tracks as explicit since they were flagged by OpenAI), then auto-
    adds to the uploader's station if `audience='adult'`."""
    db = request.app.state.db
    job = await db.track_moderation_jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(404, {"code": "job_not_found"})
    if job["status"] != "pending_admin_review":
        raise HTTPException(
            409,
            {"code": "invalid_state",
              "message": f"Cannot approve from status={job['status']}"},
        )
    # Insert the catalog row.
    from services.track_moderation_pipeline import (_insert_catalog_row,
                                                                                                              _maybe_add_to_station)
    target_id = await _insert_catalog_row(
        db,
        title=job.get("candidate_title") or "Untitled",
        artist=job.get("candidate_artist"),
        album=job.get("candidate_album"),
        duration_sec=job.get("duration_sec"),
        file_path=job.get("final_file_path"),
        file_hash=job.get("file_hash"),
        tag_meta=job.get("candidate_tag_meta") or {},
        explicit_flag=True,
        uploaded_by=job.get("user_id"),
    )
    added = await _maybe_add_to_station(
        db, job.get("station_slug"), target_id, job.get("user_id"),
        source="admin_approved", adult_only=True)
    await db.track_moderation_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "approved",
                          "target_track_id": target_id,
                          "explicit_flag": True,
                          "decision_reason": "admin_approved",
                          "decided_at": _iso(),
                          "decided_by": admin["user_id"],
                          "added_to_station": bool(added)}},
    )
    fresh = await db.track_moderation_jobs.find_one({"job_id": job_id})
    return {"ok": True, "job": _public_job_view(fresh),
                  "target_track_id": target_id,
                  "added_to_station": bool(added)}


@admin_router.post("/tracks/{job_id}/reject")
async def admin_reject_track(
    job_id: str,
    body: AdminRejectIn,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Admin rejects.  Track stays quarantined (NOT in catalog).
    Uploader sees the `rejection_reason` in their job poll."""
    db = request.app.state.db
    job = await db.track_moderation_jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(404, {"code": "job_not_found"})
    if job["status"] != "pending_admin_review":
        raise HTTPException(
            409,
            {"code": "invalid_state",
              "message": f"Cannot reject from status={job['status']}"},
        )
    await db.track_moderation_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "rejected",
                          "rejection_reason": body.reason,
                          "decided_at": _iso(),
                          "decided_by": admin["user_id"]}},
    )
    # Best-effort cleanup of the orphaned media file.
    fp = job.get("final_file_path")
    if fp:
        try:
            Path(fp).unlink(missing_ok=True)
        except Exception:
            pass
    fresh = await db.track_moderation_jobs.find_one({"job_id": job_id})
    return {"ok": True, "job": _public_job_view(fresh)}


# Bootstrap entry point — imported by server.py
async def bootstrap_phase_d(db) -> None:
    await ensure_phase_d_indexes(db)
    # Add `audience` field default on legacy stations (idempotent).
    await db.community_radio_stations.update_many(
        {"audience": {"$exists": False}},
        {"$set": {"audience": "general"}},
    )
    log.info("[station_tracks] Phase D bootstrap complete")
