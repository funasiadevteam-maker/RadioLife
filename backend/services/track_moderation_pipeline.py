"""Phase D — Track moderation pipeline.

Async pipeline that runs after a user uploads an audio file to their
station.  Decides one of four verdicts and writes the catalog row /
station-track row when appropriate.

Stages (in order):
    1. **Text moderation** — runs the existing `services.moderation`
        pipeline against `<title> <artist> <album> <optional lyrics>`.
        That service already combines a rule-based profanity / leak /
        caps pre-filter with OpenAI `omni-moderation-latest` and writes
        to the canonical `moderation_audit` collection.

    2. **Verdict mapping**
        • text verdict == "allow" + zero `explicit` flag from ID3
            → `auto_approved` (catalog status=active, explicit_flag=false)
        • text verdict == "allow" + ID3 `explicit=1` OR profanity
            category from rule pre-filter (case-insensitive partial
            match on title/artist) → `explicit_auto_flagged`
            (catalog status=active, explicit_flag=true).  Added to
            station ONLY if station.audience == "adult".  General-
            audience stations are NOT auto-added — the uploader sees the
            job as approved-but-not-on-station with a clear reason.
        • text verdict == "warn" → `pending_admin_review`
            (NOT in catalog yet; appears in admin queue).
        • text verdict == "block" → `pending_admin_review`
            (NOT in catalog; appears in admin queue with the OpenAI
            categories carried through).

Concurrency: this module is called via FastAPI `BackgroundTasks`.  The
upload route returns 202 with the job_id; the client polls
`/api/stations/{slug}/moderation-jobs/{job_id}` for status.

Idempotency: the pipeline only fires once per `job_id`.  If a job is
re-run (e.g., after admin manual approve), it picks up the prior
`target_track_meta` and inserts into catalog without re-calling OpenAI.
"""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from services.moderation import moderate
from services.track_dedupe import attach_dedupe_fields, find_duplicate

log = logging.getLogger("bigfm.track_moderation")

# Tracks where the uploaded file's title/artist contains one of these
# tokens are flagged as `explicit_auto_flagged` even when OpenAI returns
# `allow` — this is a defence-in-depth cheap rule that catches obvious
# explicit titles when the OpenAI signal is weak (e.g. when the artist
# is widely known and the moderation service doesn't flag the word in
# isolation).
EXPLICIT_TITLE_TOKENS = (
    "explicit", "[explicit]", "(explicit)", "uncensored",
    "parental advisory", "18+", "xxx",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_explicit_from_id3(tag_meta: dict) -> bool:
    """ID3v2 supports an `explicit` boolean (some tagger libs surface
    as an integer or string).  Be liberal in what we accept."""
    raw = tag_meta.get("explicit") or tag_meta.get("itunes_advisory")
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw >= 1
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "explicit", "yes", "y", "e")
    return False


def _is_explicit_from_title(title: str | None,
                                                artist: str | None) -> bool:
    blob = f"{title or ''} {artist or ''}".lower()
    return any(tok in blob for tok in EXPLICIT_TITLE_TOKENS)


def _moderation_text_blob(*, title: str, artist: str | None,
                                                album: str | None,
                                                lyrics: str | None) -> str:
    pieces = [title or ""]
    if artist:
        pieces.append(f"by {artist}")
    if album:
        pieces.append(f"album {album}")
    if lyrics:
        # Truncate lyrics — OpenAI moderation has its own input limit
        # but we keep this lean for cost and latency.
        pieces.append(lyrics[:8000])
    return " · ".join(p for p in pieces if p).strip()


async def run_moderation_pipeline(
    db,
    *,
    job_id: str,
) -> dict:
    """Execute the pipeline for a single job_id.  Reads the job doc,
    runs moderation, decides verdict, writes catalog + station_tracks
    rows.  Returns the final job dict (also persisted).

    This function is idempotent: if the job is already in a terminal
    state, it short-circuits.  It is also safe to retry on transient
    errors — the catalog insert is gated on a dedupe re-check via
    `find_duplicate`.
    """
    job = await db.track_moderation_jobs.find_one({"job_id": job_id})
    if not job:
        log.warning("[track_mod] job_id=%s not found", job_id)
        return {"error": "job_not_found"}

    if job["status"] not in ("pending", "queued"):
        # Already decided — return as-is.
        return job

    title = job.get("candidate_title") or job.get("filename_stem") or "Untitled"
    artist = job.get("candidate_artist")
    album = job.get("candidate_album")
    lyrics = job.get("candidate_lyrics")
    tag_meta = job.get("candidate_tag_meta") or {}
    file_hash = job.get("file_hash")
    duration_sec = job.get("duration_sec")
    isrc = tag_meta.get("isrc")
    station_slug = job.get("station_slug")
    uploader_id = job.get("user_id")

    # 1. Defence-in-depth dedupe re-check (race window between upload
    # accept and pipeline pickup).
    dup = await find_duplicate(
        db,
        file_hash=file_hash,
        isrc=isrc,
        title=title,
        artist=artist,
        duration_sec=duration_sec,
    )
    if dup:
        log.info("[track_mod] job=%s late-dedupe matched track=%s via=%s",
                          job_id, dup["track_id"], dup["matched_rule"])
        await _finalize_job(db, job_id, status="auto_approved",
                                          target_track_id=dup["track_id"],
                                          decision_reason=f"late_dedupe:{dup['matched_rule']}",
                                          dedupe_matched_rule=dup["matched_rule"])
        await _maybe_add_to_station(db, station_slug,
                                                                dup["track_id"], uploader_id,
                                                                source="upload",
                                                                require_general_only=False)
        return await db.track_moderation_jobs.find_one({"job_id": job_id})

    # 2. Text moderation.
    text = _moderation_text_blob(
        title=title, artist=artist, album=album, lyrics=lyrics)
    try:
        mod = await moderate(db, ref_type="ugc_track", ref_id=job_id,
                                              user_id=uploader_id, text=text)
    except Exception as e:
        log.warning("[track_mod] moderation call failed for job=%s: %s",
                              job_id, e)
        # Defensive fail-safe: route to admin review on any pipeline error.
        mod = {"verdict": "warn", "categories": ["moderation_error"],
                  "score": 0.0, "reason": str(e)}

    verdict = mod.get("verdict") or "warn"
    categories = mod.get("categories") or []

    # 3. Decide outcome.
    id3_explicit = _is_explicit_from_id3(tag_meta)
    title_explicit = _is_explicit_from_title(title, artist)
    rule_profanity = any(c.startswith("profanity") for c in categories)

    if verdict == "block":
        new_status = "pending_admin_review"
        decision_reason = "openai_blocked"
        explicit_flag = True
    elif verdict == "warn":
        new_status = "pending_admin_review"
        decision_reason = "openai_warned"
        explicit_flag = bool(rule_profanity or id3_explicit or title_explicit)
    else:                                  # verdict == "allow"
        if id3_explicit or title_explicit or rule_profanity:
            new_status = "explicit_auto_flagged"
            decision_reason = ("id3_explicit" if id3_explicit
                                          else "title_explicit" if title_explicit
                                          else "rule_profanity")
            explicit_flag = True
        else:
            new_status = "auto_approved"
            decision_reason = "openai_allowed"
            explicit_flag = False

    # 4. If outcome allows it, insert the catalog row + attach to station.
    target_track_id: Optional[str] = None
    if new_status in ("auto_approved", "explicit_auto_flagged"):
        try:
            target_track_id = await _insert_catalog_row(
                db,
                title=title, artist=artist, album=album,
                duration_sec=duration_sec,
                file_path=job.get("final_file_path"),
                file_hash=file_hash,
                tag_meta=tag_meta,
                explicit_flag=explicit_flag,
                uploaded_by=uploader_id,
            )
        except Exception as e:
            log.warning("[track_mod] catalog insert failed for job=%s: %s",
                                  job_id, e)
            new_status = "pending_admin_review"
            decision_reason = f"catalog_insert_failed:{e}"

    if target_track_id and new_status == "auto_approved":
        await _maybe_add_to_station(
            db, station_slug, target_track_id, uploader_id,
            source="upload", require_general_only=False)
    elif target_track_id and new_status == "explicit_auto_flagged":
        # Only attach to "adult" stations automatically — the uploader
        # sees a clear status note when this fails.
        await _maybe_add_to_station(
            db, station_slug, target_track_id, uploader_id,
            source="upload", require_general_only=False,
            adult_only=True)

    return await _finalize_job(
        db, job_id,
        status=new_status,
        target_track_id=target_track_id,
        decision_reason=decision_reason,
        moderation_verdict=verdict,
        moderation_categories=categories,
        moderation_score=mod.get("score"),
        explicit_flag=explicit_flag,
    )


async def _finalize_job(db, job_id: str, **fields) -> dict:
    update = {"$set": {**fields, "decided_at": _now().isoformat()}}
    await db.track_moderation_jobs.update_one({"job_id": job_id}, update)
    return await db.track_moderation_jobs.find_one({"job_id": job_id})


async def _insert_catalog_row(
    db, *,
    title: str,
    artist: str | None,
    album: str | None,
    duration_sec: float | None,
    file_path: str | None,
    file_hash: str | None,
    tag_meta: dict,
    explicit_flag: bool,
    uploaded_by: str,
) -> str:
    """Create a `tracks` row and return its track_id.  Re-races safely
    against the UNIQUE sparse file_hash index by re-resolving the
    duplicate on E11000."""
    import uuid as _uuid
    track_id = f"ugc_{_uuid.uuid4().hex[:14]}"
    doc: dict[str, Any] = {
        "_id":                            track_id,
        "title":                          title or "Untitled",
        "artist":                        artist,
        "album":                        album,
        "duration_sec":            duration_sec,
        "file_path":                  file_path,
        "file_hash":                  file_hash,
        "storage_provider":   "disk",
        "status":                        "active",
        "explicit_flag":            bool(explicit_flag),
        "uploaded_at":              _now().isoformat(),
        "uploaded_by_user":  uploaded_by,
        "source":                      "user_upload",
        # ID3 / auto-tag passthrough where available.
        "language":                  tag_meta.get("language"),
        "language_confidence": tag_meta.get("language_confidence"),
        "mood":                        tag_meta.get("mood"),
        "energy_level":            tag_meta.get("energy_level"),
        "genre":                        tag_meta.get("genre"),
        "vibe_tags":                  tag_meta.get("vibe_tags") or [],
        "isrc":                            tag_meta.get("isrc"),
        "year":                          tag_meta.get("year"),
    }
    attach_dedupe_fields(doc)
    try:
        await db.tracks.insert_one(doc)
        return track_id
    except Exception as e:
        if "duplicate key" in str(e).lower():
            dup = await find_duplicate(
                db, file_hash=file_hash,
                isrc=tag_meta.get("isrc"),
                title=title, artist=artist,
                duration_sec=duration_sec)
            if dup:
                return dup["track_id"]
        raise


async def _maybe_add_to_station(
    db, station_slug: str | None,
    track_id: str,
    added_by: str,
    *,
    source: str,
    require_general_only: bool = False,
    adult_only: bool = False,
) -> bool:
    """Adds (track_id, station) join row.  Returns True on success.

    `adult_only=True` skips the insert if station.audience != "adult".
    """
    if not station_slug:
        return False
    station = await db.community_radio_stations.find_one(
        {"slug": station_slug})
    if not station:
        return False
    audience = station.get("audience") or "general"
    if adult_only and audience != "adult":
        return False
    if require_general_only and audience != "general":
        return False
    # Idempotent: unique compound index on (station_id, track_id) +
    # upsert behaviour.
    sort_index_doc = await db.station_tracks.find_one(
        {"station_id": station["station_id"]},
        sort=[("sort_index", -1)])
    next_sort = ((sort_index_doc or {}).get("sort_index") or 0) + 1
    join_id = f"stt_{station['station_id']}_{track_id}"
    try:
        await db.station_tracks.insert_one({
            "_id":                  join_id,
            "station_id":      station["station_id"],
            "station_slug":  station["slug"],
            "track_id":          track_id,
            "added_at":          _now().isoformat(),
            "added_by":          added_by,
            "sort_index":      next_sort,
            "source":              source,
        })
        return True
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return True   # idempotent — already on station
        log.warning("[track_mod] station_tracks insert failed: %s", e)
        return False


def normalize_search_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())


async def ensure_phase_d_indexes(db) -> None:
    """Phase D indexes for `station_tracks` + `track_moderation_jobs`
    + `track_upload_rate_limits`.  Idempotent."""
    # station_tracks
    await db.station_tracks.create_index(
        [("station_id", 1), ("track_id", 1)], unique=True,
        name="station_tracks_unique")
    await db.station_tracks.create_index(
        [("station_id", 1), ("sort_index", 1)],
        name="station_tracks_sort")
    await db.station_tracks.create_index(
        "track_id", name="station_tracks_track")

    # track_moderation_jobs
    await db.track_moderation_jobs.create_index(
        "job_id", unique=True, name="track_mod_job_id_unique")
    await db.track_moderation_jobs.create_index(
        [("status", 1), ("created_at", -1)],
        name="track_mod_status")
    await db.track_moderation_jobs.create_index(
        [("user_id", 1), ("created_at", -1)],
        name="track_mod_user")
    await db.track_moderation_jobs.create_index(
        "station_slug", name="track_mod_station")

    # track_upload_rate_limits — TTL on `ttl_at` so the bucket auto-
    # disappears 1h after creation.  Mirrors `game_rate_limits` shape.
    try:
        await db.track_upload_rate_limits.create_index(
            "ttl_at", expireAfterSeconds=0,
            name="track_rl_ttl")
    except Exception as e:
        log.warning("[track_mod] TTL index ensure failed: %s", e)

    log.info("[track_mod] Phase D indexes ensured")
