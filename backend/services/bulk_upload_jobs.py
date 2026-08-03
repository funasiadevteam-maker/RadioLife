"""Phase 22g — Bulk Upload Job Audit Log service.

Append-only diagnostic record for every `/api/admin/tracks/bulk-upload`
attempt.  Designed around three failure modes that, until this commit,
left no server-side trace:

    1. Backend pod offline / restarted mid-request (graceful or OOM).
    2. Ingress timeout (Emergent's reverse proxy) on multi-GB requests.
    3. Client disconnect (browser closed, network blip).

The route wraps its work in `try / except / finally` around helpers
exposed here.  The `finally` block flips any still-"running" row to
"abandoned" using a conditional update so it can't clobber a terminal
status that was already set.

Indexes are created lazily on first call to `ensure_indexes` so cold
boot doesn't depend on a separate bootstrap hook.

Schema (collection `bulk_upload_jobs`):
    job_id, started_by_user_id, started_at, completed_at, status,
    total_inputs, zip_count, audio_direct_count,
    total_extracted_from_zip, uploaded_count, duplicate_count,
    skipped_non_audio_count, failed_count, total_bytes_received,
    storage_provider, defaults_json, client_ip, client_user_agent,
    duration_ms, failure_reason, per_file_results_json,
    per_file_results_truncated, created_at, updated_at.

`per_file_results_json` is capped at PER_FILE_RESULTS_CAP entries; the
flag `per_file_results_truncated` records whether trimming occurred.
"""
from __future__ import annotations
import logging
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger("bigfm.bulk_upload_audit")

PER_FILE_RESULTS_CAP = 200
STALE_RUNNING_AFTER_MINUTES = 30

# ---- light-row projection used by /jobs list endpoints ----
_LIGHT_PROJECTION = {
    "per_file_results_json": 0,
}


def _duration_ms(started, now: datetime) -> Optional[int]:
    """Motor returns BSON dates as tz-naive UTC.  Normalise both sides to
    aware-UTC before subtracting so we don't throw mid-route."""
    if not hasattr(started, "timestamp"):
        return None
    try:
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return int((now - started).total_seconds() * 1000)
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ════════════════════════════════════════════════════════════════════════
# Indexes (idempotent — safe to call repeatedly).
# ════════════════════════════════════════════════════════════════════════
_INDEXES_READY = False
async def ensure_indexes(db) -> None:
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    coll = db.bulk_upload_jobs
    await coll.create_index([("started_by_user_id", 1), ("started_at", -1)])
    await coll.create_index([("status", 1), ("started_at", -1)])
    await coll.create_index([("started_at", -1)])
    _INDEXES_READY = True


# ════════════════════════════════════════════════════════════════════════
# create / complete / fail / abandon
# ════════════════════════════════════════════════════════════════════════
async def create_job(
    db,
    *,
    started_by_user_id: str,
    total_inputs: int,
    total_bytes_received: int,
    defaults_json: dict,
    client_ip: Optional[str],
    client_user_agent: Optional[str],
    storage_provider: str,
) -> str:
    """Insert a `status="running"` row and return its job_id."""
    await ensure_indexes(db)
    now = _now()
    job_id = "job_" + uuid.uuid4().hex[:20]
    doc = {
        "_id":                              job_id,
        "job_id":                          job_id,
        "started_by_user_id":      started_by_user_id,
        "started_at":                    now,
        "completed_at":                None,
        "status":                          "running",
        "total_inputs":                total_inputs,
        "zip_count":                      0,
        "audio_direct_count":      0,
        "total_extracted_from_zip": 0,
        "uploaded_count":            0,
        "duplicate_count":            0,
        "skipped_non_audio_count": 0,
        "failed_count":                0,
        "total_bytes_received":  total_bytes_received,
        "storage_provider":        storage_provider,
        "defaults_json":              defaults_json,
        "client_ip":                      client_ip,
        "client_user_agent":      client_user_agent,
        "duration_ms":                None,
        "failure_reason":            None,
        "per_file_results_json": [],
        "per_file_results_truncated": False,
        "created_at":                    now,
        "updated_at":                    now,
    }
    await db.bulk_upload_jobs.insert_one(doc)
    return job_id


def _truncate_results(items: list[dict]) -> tuple[list[dict], bool]:
    """Cap per-file results to PER_FILE_RESULTS_CAP. Strip any audio bytes
    that might have leaked in (defense in depth — the route never passes
    them, but we re-shape just in case)."""
    truncated = len(items) > PER_FILE_RESULTS_CAP
    safe = items[:PER_FILE_RESULTS_CAP]
    cleaned = []
    for it in safe:
        # Whitelist the fields we know the route emits.
        cleaned.append({k: it[k] for k in (
            "source", "archive", "filename", "status", "reason",
            "track_id", "existing_track_id", "title", "artist",
            "duration_sec",
            # Phase 22e dedupe fields:
            "matched_rule", "matched_track_title", "matched_track_artist",
        ) if k in it})
    return cleaned, truncated


def _counts_from_items(items: list[dict]) -> dict:
    """Recompute counts from items[] — single source of truth so the row
    can't drift from the response."""
    uploaded = duplicate = skipped = failed = 0
    zip_count = direct_count = extracted = 0
    seen_archives: set[str] = set()
    for it in items:
        s = it.get("status")
        if s == "uploaded":
            uploaded += 1
        elif s == "duplicate":
            duplicate += 1
        elif s == "skipped_non_audio":
            skipped += 1
        elif s == "failed":
            failed += 1
        src = it.get("source")
        if src == "zip":
            extracted += 1
            arch = it.get("archive")
            if arch:
                seen_archives.add(arch)
        elif src == "direct":
            direct_count += 1
    zip_count = len(seen_archives)
    return {
        "uploaded_count":            uploaded,
        "duplicate_count":            duplicate,
        "skipped_non_audio_count": skipped,
        "failed_count":                failed,
        "zip_count":                      zip_count,
        "audio_direct_count":      direct_count,
        "total_extracted_from_zip": extracted,
    }


async def complete_job(db, job_id: str, *, items: list[dict],
                                          extra_counts: Optional[dict] = None) -> None:
    """Mark job completed (or 'partial' if any failed AND any uploaded)."""
    counts = _counts_from_items(items or [])
    status_override: Optional[str] = None
    if extra_counts:
        # Trust the route's authoritative numbers when present (e.g. it
        # already counted zip_archives_processed including failed-parse
        # archives where items[] won't have a source="zip" row).
        # Phase 22e: `status_override` is consumed here, not stored.
        status_override = extra_counts.pop("status_override", None) \
                                          if isinstance(extra_counts, dict) else None
        counts.update({k: v for k, v in extra_counts.items()
                                      if v is not None})

    if status_override:
        status = status_override
    elif counts["failed_count"] > 0 and counts["uploaded_count"] > 0:
        status = "partial"
    elif counts["failed_count"] > 0 and counts["uploaded_count"] == 0:
        # Pure-failure with at least one item — treat as 'failed' so the
        # diagnostic view surfaces it; route still returned 200 because
        # duplicates count toward "valid".
        status = "failed" if counts["duplicate_count"] == 0 else "partial"
    else:
        status = "completed"

    safe_items, truncated = _truncate_results(items or [])
    now = _now()
    row = await db.bulk_upload_jobs.find_one({"_id": job_id},
                                                                                  {"started_at": 1})
    duration_ms = _duration_ms(row.get("started_at") if row else None, now)

    await db.bulk_upload_jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status":                          status,
            "completed_at":                now,
            "updated_at":                    now,
            "duration_ms":                duration_ms,
            "per_file_results_json": safe_items,
            "per_file_results_truncated": truncated,
            # Phase 22e — write BOTH the new `*_count` schema AND the legacy
            # aliases (`uploaded` / `duplicates_skipped` / `skipped` /
            # `failed` / `total`) so older clients + the admin music library
            # UI don't see `None` and report the job as a silent no-op.
            "uploaded":                      counts["uploaded_count"],
            "duplicates_skipped":  counts["duplicate_count"],
            "skipped":                        counts["skipped_non_audio_count"],
            "failed":                          counts["failed_count"],
            "total": (counts["uploaded_count"] + counts["duplicate_count"]
                          + counts["skipped_non_audio_count"] + counts["failed_count"]),
            "items":                          safe_items,
            **counts,
        }})


async def fail_job(db, job_id: str, *, items: list[dict],
                                  exception: Optional[BaseException],
                                  extra_counts: Optional[dict] = None) -> None:
    """Mark job failed; record `str(exception)` + truncated traceback.

    `extra_counts` (Phase 22e additive): same shape as in `complete_job`
    — top-level audit-row fields like `peak_rss_mb`, `temp_dir_path`,
    `duplicates_skipped*`, `streaming_mode`, `cleanup_succeeded`.  A
    `status_override` key, if present, replaces the default
    `"failed"` status (used by the route to record "client_disconnected").
    """
    counts = _counts_from_items(items or [])
    status_override: Optional[str] = None
    if extra_counts and isinstance(extra_counts, dict):
        status_override = extra_counts.pop("status_override", None)
        counts.update({k: v for k, v in extra_counts.items()
                                      if v is not None})
    safe_items, truncated = _truncate_results(items or [])
    now = _now()
    row = await db.bulk_upload_jobs.find_one({"_id": job_id},
                                                                                  {"started_at": 1})
    duration_ms = _duration_ms(row.get("started_at") if row else None, now)

    if exception is None:
        reason = "unknown_failure"
    else:
        tb = "".join(traceback.format_exception_only(type(exception),
                                                                                              exception))[:300]
        reason = tb.strip() or str(exception)[:300] or type(exception).__name__

    await db.bulk_upload_jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status":                          status_override or "failed",
            "completed_at":                now,
            "updated_at":                    now,
            "duration_ms":                duration_ms,
            "failure_reason":            reason,
            "per_file_results_json": safe_items,
            "per_file_results_truncated": truncated,
            **counts,
        }})


async def abandon_if_running(db, job_id: str) -> bool:
    """Best-effort: flip job_id from 'running' → 'abandoned'.  No-op if
    the row was already moved to a terminal status by the success / fail
    path above.  Returns True if it actually wrote."""
    now = _now()
    r = await db.bulk_upload_jobs.update_one(
        {"_id": job_id, "status": "running"},
        {"$set": {"status": "abandoned",
                          "completed_at": now,
                          "updated_at":    now}})
    return r.modified_count > 0


async def sweep_stale(db, *,
                                          cutoff_minutes: int = STALE_RUNNING_AFTER_MINUTES
                                          ) -> int:
    """Find `status="running"` jobs older than the cutoff and flip them
    to `"abandoned"`.  Returns the count swept."""
    await ensure_indexes(db)
    cutoff = _now() - timedelta(minutes=cutoff_minutes)
    r = await db.bulk_upload_jobs.update_many(
        {"status": "running", "started_at": {"$lt": cutoff}},
        {"$set": {"status": "abandoned",
                          "completed_at": _now(),
                          "updated_at":    _now()}})
    return int(r.modified_count or 0)


# ════════════════════════════════════════════════════════════════════════
# read paths used by /jobs endpoints
# ════════════════════════════════════════════════════════════════════════
def _serialize(doc: dict, *, include_results: bool) -> dict:
    out = dict(doc)
    out.pop("_id", None)
    if not include_results:
        out.pop("per_file_results_json", None)
    for k in ("started_at", "completed_at", "created_at", "updated_at"):
        v = out.get(k)
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


async def list_jobs(
    db,
    *,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 25,
    cursor: Optional[str] = None,
) -> dict:
    """Return paginated light rows (no per_file_results_json)."""
    await ensure_indexes(db)
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if user_id:
        q["started_by_user_id"] = user_id
    if cursor:
        # cursor is a job_id; we use its started_at as the boundary.
        last = await db.bulk_upload_jobs.find_one({"_id": cursor},
                                                                                          {"started_at": 1})
        if last and last.get("started_at"):
            q["started_at"] = {"$lt": last["started_at"]}
    limit = max(1, min(limit, 100))
    cursor_q = (db.bulk_upload_jobs.find(q, _LIGHT_PROJECTION)
                              .sort("started_at", -1).limit(limit + 1))
    docs = await cursor_q.to_list(limit + 1)
    has_more = len(docs) > limit
    items = [_serialize(d, include_results=False) for d in docs[:limit]]
    next_cursor = items[-1]["job_id"] if (has_more and items) else None
    return {"items": items, "next_cursor": next_cursor, "limit": limit}


async def get_job(db, job_id: str, *,
                                      restrict_to_user_id: Optional[str] = None
                                      ) -> Optional[dict]:
    """Return a single job row (full doc).  If `restrict_to_user_id` is
    set, returns None when the row belongs to another user — used by the
    `/api/me/bulk-upload/jobs/{job_id}` path."""
    q: dict[str, Any] = {"_id": job_id}
    if restrict_to_user_id:
        q["started_by_user_id"] = restrict_to_user_id
    doc = await db.bulk_upload_jobs.find_one(q)
    if not doc:
        return None
    return _serialize(doc, include_results=True)
