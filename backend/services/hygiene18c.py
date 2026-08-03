"""Phase 18c — Disk hygiene cron + admin trigger.

Prunes stale files in storage/static directories that aren't whitelisted by
an active `ad_creatives` row or a scheduled `news_radio_segments` row.

Idempotent.  Logs every run to `hygiene_runs` collection.
"""
from __future__ import annotations
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigfm.hygiene18c")

PRUNE_DIRS = [
    "/app/backend/storage/streams",
    "/app/backend/storage/segments",
    "/app/backend/storage/tracks",
    "/app/backend/static/ad_creatives",
]
TTL_HOURS = int(os.environ.get("HYGIENE_TTL_HOURS", "24"))


async def _whitelist(db) -> set[str]:
    keep: set[str] = set()
    async for c in db.ad_creatives.find({"status": {"$in": ["active", "approved",
                                                                                "pending_review"]}},
                                                              {"audio_path": 1, "audio_url": 1,
                                                                "image_url": 1, "_id": 0}):
        for k in ("audio_path", "audio_url", "image_url"):
            v = c.get(k)
            if v:
                keep.add(Path(str(v)).name)
    # Forward-compat: news radio segments scheduled within next 7 days.
    try:
        in_7d = datetime.now(timezone.utc) + timedelta(days=7)
        async for r in db.news_radio_segments.find(
            {"scheduled_for": {"$lte": in_7d}},
            {"audio_path": 1, "_id": 0}):
            v = r.get("audio_path")
            if v:
                keep.add(Path(str(v)).name)
    except Exception:
        pass
    return keep


async def tick_daily(db, *, ttl_hours: Optional[int] = None,
                                  dry_run: bool = False) -> dict:
    ttl = int(ttl_hours if ttl_hours is not None else TTL_HOURS)
    cutoff = time.time() - ttl * 3600
    keep = await _whitelist(db)
    deleted, freed, errs = 0, 0, []
    for d in PRUNE_DIRS:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.glob("**/*"):
            if not f.is_file():
                continue
            try:
                if f.name in keep:
                    continue
                if f.stat().st_mtime > cutoff:
                    continue
                sz = f.stat().st_size
                if not dry_run:
                    f.unlink()
                deleted += 1
                freed += sz
            except Exception as e:
                errs.append(f"{f}: {e}")
    run_at = datetime.now(timezone.utc)
    rec = {"run_at": run_at, "ttl_hours": ttl, "deleted_count": deleted,
              "freed_bytes": freed, "dry_run": dry_run,
              "errors": errs[:25]}
    try:
        await db.hygiene_runs.insert_one(rec)
    except Exception as e:
        logger.warning("[hygiene18c] could not log run: %s", e)
    rec.pop("_id", None)
    # Phase 36c.5 hardening — fold the local-recording-orphan safety sweep
    # into every daily tick so disk pressure is auto-self-healing. Best
    # effort — failures here MUST NOT break the primary tick contract.
    try:
        sub = await tick_local_recording_orphans(db, dry_run=dry_run)
        rec["local_recording_orphans"] = sub
    except Exception as e:
        logger.warning("[hygiene18c] local-recording-orphan sub-tick failed: %s", e)
    # Post-repack hygiene upgrade (2026-06-04): also fold the test-fixture
    # sweep + supervisor log rotation into the daily tick.
    try:
        rec["local_podcast_fixture_orphans"] = \
            await tick_local_podcast_fixture_orphans(db, dry_run=dry_run)
    except Exception as e:
        logger.warning("[hygiene18c] fixture sub-tick failed: %s", e)
    try:
        rec["supervisor_log_rotate"] = \
            tick_supervisor_log_rotation(dry_run=dry_run)
    except Exception as e:
        logger.warning("[hygiene18c] log rotate sub-tick failed: %s", e)
    logger.info("[hygiene18c] pruned %d files (%.1f MB), errors=%d",
                      deleted, freed / 1_048_576, len(errs))
    return rec


async def last_run(db) -> Optional[dict]:
    doc = await db.hygiene_runs.find_one({}, sort=[("run_at", -1)])
    if doc:
        doc.pop("_id", None)
    return doc


# ─── Phase 36c.5: Tigris orphan pruning ────────────────────────
TIGRIS_TRANSIENT_PREFIXES = ("_test/", "_list_", "_probe/")
TIGRIS_ORPHAN_TTL_HOURS = int(
    os.environ.get("TIGRIS_ORPHAN_TTL_HOURS", "168"))    # 7 days


async def _tigris_referenced_keys(db) -> set[str]:
    """Collect every Tigris key referenced by an active DB row. Anything
    NOT in this set + older than TTL is considered orphaned."""
    keep: set[str] = set()
    try:
        async for ep in db.podcast_episodes.find(
            {}, {"id": 1, "channel_id": 1, "storage_key_audio": 1,
                      "storage_key_video": 1, "storage_key_cover": 1,
                      "recording_session_id": 1, "_id": 0}):
            ch = ep.get("channel_id") or "_"
            ep_id = ep.get("id") or ""
            keep.add(f"podcasts/channels/{ch}/{ep_id}/audio.mp3")
            keep.add(f"podcasts/channels/{ch}/{ep_id}/video.mp4")
            keep.add(f"podcasts/channels/{ch}/{ep_id}/cover.jpg")
            keep.add(f"podcasts/channels/{ch}/{ep_id}/cover.webp")
            keep.add(f"podcasts/channels/{ch}/{ep_id}/cover.png")
            for k in ("storage_key_audio", "storage_key_video",
                          "storage_key_cover"):
                if ep.get(k): keep.add(ep[k])
            sid = ep.get("recording_session_id")
            if sid:
                keep.add(f"podcasts/recordings/{sid}/mixed.mp3")
                keep.add(f"podcasts/recordings/{sid}/mixed.mp4")
        async for s in db.podcast_recording_sessions.find(
            {}, {"id": 1, "_id": 0}):
            sid = s.get("id") or ""
            keep.add(f"podcasts/recordings/{sid}/mixed.mp3")
            keep.add(f"podcasts/recordings/{sid}/mixed.mp4")
            keep.add(f"podcasts/recordings/{sid}/host/audio.mp3")
            keep.add(f"podcasts/recordings/{sid}/host/video.mp4")
        async for p in db.podcast_recording_participants.find(
            {}, {"id": 1, "session_id": 1, "_id": 0}):
            sid = p.get("session_id") or ""; pid = p.get("id") or ""
            if sid and pid:
                keep.add(f"podcasts/recordings/{sid}/{pid}/audio.mp3")
                keep.add(f"podcasts/recordings/{sid}/{pid}/video.mp4")
        async for t in db.tracks.find({}, {"_id": 1}):
            keep.add(f"music/tracks/{t.get('_id')}.mp3")
        async for r in db.rj_audio.find({}, {"_id": 1}):
            keep.add(f"rj/{r.get('_id')}.mp3")
        async for c in db.ad_creatives.find(
            {}, {"_id": 1, "id": 1}):
            cid = c.get("id") or c.get("_id")
            if cid:
                keep.add(f"ad_creatives/{cid}.mp3")
                keep.add(f"ad_creatives/{cid}.webp")
                keep.add(f"ad_creatives/{cid}.jpg")
                keep.add(f"ad_creatives/{cid}.png")
    except Exception as e:
        logger.warning("[hygiene36c5] _tigris_referenced_keys failed: %s", e)
    return keep


async def tick_tigris_orphans(db, *, ttl_hours: Optional[int] = None,
                                                dry_run: bool = False,
                                                max_scan: int = 10000) -> dict:
    """Phase 36c.5 — prune Tigris objects older than TTL and not referenced
    by any active DB row (and not under a known transient prefix is kept
    for shorter TTL via this same pass)."""
    from services import object_storage as obs    # local import: optional dep
    st = obs.get_storage()
    if st.backend_name != "tigris":
        return {"skipped": True, "reason": "STORAGE_BACKEND!=tigris"}
    ttl = int(ttl_hours if ttl_hours is not None else TIGRIS_ORPHAN_TTL_HOURS)
    cutoff_ts = time.time() - ttl * 3600
    keep = await _tigris_referenced_keys(db)
    scanned = deleted = freed = errs_n = 0
    errors: list[str] = []
    # boto3 client lives on TigrisStorage
    s3 = getattr(st, "s3", None); bucket = getattr(st, "bucket", None)
    if not s3 or not bucket:
        return {"skipped": True, "reason": "tigris_client_unavailable"}
    token = None
    while True:
        kw = {"Bucket": bucket}
        if token: kw["ContinuationToken"] = token
        try:
            r = s3.list_objects_v2(**kw)
        except Exception as e:
            return {"skipped": False, "error": f"list_objects: {e}",
                      "deleted": 0, "freed_bytes": 0}
        for it in (r.get("Contents") or []):
            scanned += 1
            if scanned > max_scan: break
            k = it["Key"]
            sz = int(it.get("Size") or 0)
            ts = it.get("LastModified")
            mtime = ts.timestamp() if ts else 0
            # Always preserve referenced keys
            if k in keep: continue
            # Test prefixes — short TTL of 1 hour
            transient = any(k.startswith(p) for p in TIGRIS_TRANSIENT_PREFIXES)
            cutoff = (time.time() - 3600) if transient else cutoff_ts
            if mtime > cutoff: continue
            if dry_run:
                deleted += 1; freed += sz; continue
            try:
                s3.delete_object(Bucket=bucket, Key=k)
                deleted += 1; freed += sz
            except Exception as e:
                errs_n += 1; errors.append(f"{k}: {e}")
        if not r.get("IsTruncated") or scanned > max_scan: break
        token = r.get("NextContinuationToken")
    rec = {"run_at": datetime.now(timezone.utc), "kind": "tigris_orphans",
              "ttl_hours": ttl, "scanned": scanned,
              "deleted_count": deleted, "freed_bytes": freed,
              "dry_run": dry_run, "errors": errors[:25]}
    try: await db.hygiene_runs.insert_one(rec)
    except Exception as e: logger.warning("[hygiene36c5] insert_one: %s", e)
    rec.pop("_id", None)
    logger.info("[hygiene36c5] Tigris: scanned=%d deleted=%d freed=%d MB",
                      scanned, deleted, freed // 1_048_576)
    return rec


# ─── Phase 36c.5 hardening: Local recording-dir orphan sweep ──
LOCAL_RECORDINGS_ROOT = Path("/app/backend/storage/podcasts/recordings")


async def tick_local_recording_orphans(db, *, dry_run: bool = False,
                                                                ) -> dict:
    """Delete on-disk recording session dirs when:
        - the session row status ∈ {completed, cancelled, failed} AND
        - every referenced Tigris key for that session HEAD-verifies up.
    Belt-and-suspenders to the inline post-finalize delete (which is the
    primary mechanism). Safe to run on a cron; idempotent. Returns the
    same envelope shape as `tick_daily` (deleted_count + freed_bytes)."""
    from services import object_storage as obs
    st = obs.get_storage()
    scanned = deleted = freed = errs_n = 0
    errors: list[str] = []
    if not LOCAL_RECORDINGS_ROOT.is_dir():
        rec = {"run_at": datetime.now(timezone.utc),
                  "kind": "local_recording_orphans", "scanned": 0,
                  "deleted_count": 0, "freed_bytes": 0,
                  "dry_run": dry_run, "errors": []}
        try: await db.hygiene_runs.insert_one(rec)
        except Exception: pass
        rec.pop("_id", None); return rec

    for sess_dir in sorted(LOCAL_RECORDINGS_ROOT.iterdir()):
        if not sess_dir.is_dir(): continue
        sid = sess_dir.name
        scanned += 1
        sess = await db.podcast_recording_sessions.find_one(
            {"id": sid}, {"status": 1, "_id": 0})
        # Phase 36c.5+ (post-repack hygiene upgrade): orphan-no-row dirs
        # older than HYGIENE_ORPHAN_AGE_HOURS are now swept. Younger dirs
        # are still preserved (could be a session still being created).
        if not sess:
            try: age_h = (time.time() - sess_dir.stat().st_mtime) / 3600
            except OSError: age_h = 0
            ttl_h = int(os.environ.get("HYGIENE_ORPHAN_AGE_HOURS", "168"))
            if age_h < ttl_h:
                continue    # too young to sweep
            sz = sum(f.stat().st_size for f in sess_dir.rglob("*")
                          if f.is_file())
            if not dry_run:
                try:
                    import shutil as _sh
                    _sh.rmtree(sess_dir)
                    deleted += 1; freed += sz
                except OSError as e:
                    errs_n += 1; errors.append(f"{sid}: rmtree {e}")
            else:
                deleted += 1; freed += sz
            continue
        if sess.get("status") not in ("completed", "cancelled", "failed"):
            continue
        # Tigris verification only meaningful when Tigris is the backend.
        # Otherwise the local files ARE the canonical store and we must
        # NOT delete them.
        if st.backend_name != "tigris":
            continue
        mixed_key = f"podcasts/recordings/{sid}/mixed.mp3"
        keys_required: list[str] = []
        local_files = list(sess_dir.rglob("*"))
        for f in local_files:
            if not f.is_file(): continue
            rel = f.relative_to(sess_dir)
            name = rel.name
            if name in ("mixed.mp3", "audio.mp3"):
                keys_required.append(mixed_key)
            elif name == "host.mp3":
                keys_required.append(
                    f"podcasts/recordings/{sid}/host/audio.mp3")
            elif name.startswith("prp_") and name.endswith(".mp3"):
                keys_required.append(
                    f"podcasts/recordings/{sid}/{name[:-4]}/audio.mp3")
        all_present = True
        for k in keys_required:
            h = st.head(key=k)
            if not h or int(h.get("size") or 0) <= 0:
                all_present = False; break
        if not all_present:
            errors.append(f"{sid}: tigris_keys_missing — leaving dir in place")
            continue
        # All verified. Compute size, then delete on apply.
        sz = sum(f.stat().st_size for f in local_files if f.is_file())
        if not dry_run:
            try:
                import shutil as _sh
                _sh.rmtree(sess_dir)
                deleted += 1; freed += sz
            except OSError as e:
                errs_n += 1; errors.append(f"{sid}: rmtree {e}")
        else:
            deleted += 1; freed += sz
    rec = {"run_at": datetime.now(timezone.utc),
              "kind": "local_recording_orphans",
              "scanned": scanned, "deleted_count": deleted,
              "freed_bytes": freed, "dry_run": dry_run,
              "errors": errors[:25]}
    try: await db.hygiene_runs.insert_one(rec)
    except Exception as e: logger.warning("[hygiene36c5] insert: %s", e)
    rec.pop("_id", None)
    logger.info("[hygiene36c5] local recordings: scanned=%d deleted=%d "
                      "freed=%d B", scanned, deleted, freed)
    return rec


# ─── Post-repack hygiene upgrade (2026-06-04): test-fixture sweep + logs ──
LOCAL_PODCASTS_ROOT = Path("/app/backend/storage/podcasts")
SUPERVISOR_LOG_DIR = Path("/var/log/supervisor")
SUPERVISOR_LOG_ROTATE_THRESHOLD = 10 * 1024 * 1024    # 10 MB
SUPERVISOR_LOG_KEEP_TAIL              = 2 * 1024 * 1024      # last 2 MB


async def tick_local_podcast_fixture_orphans(db, *, dry_run: bool = False
                                                                                              ) -> dict:
    """Sweep CI test-fixture episode dirs under
    `/app/backend/storage/podcasts/{chan_*,pch_*}/` that no longer have a
    matching `podcast_episodes` row AND are older than
    HYGIENE_ORPHAN_AGE_HOURS (default 168). Distinct from
    `tick_local_recording_orphans` because these dirs are NOT recording
    sessions — they're per-channel/per-episode test artifacts left behind
    when CI tests fail to teardown cleanly."""
    ttl_h = int(os.environ.get("HYGIENE_ORPHAN_AGE_HOURS", "168"))
    cutoff = time.time() - ttl_h * 3600
    scanned = deleted = freed = 0
    errors: list[str] = []
    if not LOCAL_PODCASTS_ROOT.is_dir():
        return {"run_at": datetime.now(timezone.utc),
                  "kind": "local_podcast_fixture_orphans",
                  "scanned": 0, "deleted_count": 0, "freed_bytes": 0,
                  "dry_run": dry_run, "errors": []}
    # Gather all known episode ids + channel ids in one pass to avoid N+1 queries.
    known_ep = set()
    known_ch = set()
    async for ep in db.podcast_episodes.find({}, {"id": 1, "_id": 0}):
        if ep.get("id"): known_ep.add(ep["id"])
    async for ch in db.podcast_channels.find({}, {"id": 1, "_id": 0}):
        if ch.get("id"): known_ch.add(ch["id"])
    for d in sorted(LOCAL_PODCASTS_ROOT.iterdir()):
        if not d.is_dir(): continue
        name = d.name
        # Skip the recordings/ sub-root (separate sweep covers that).
        if name == "recordings": continue
        is_fixture = (name.startswith("chan_") or name.startswith("pch_")
                                  or name.startswith("pep_"))
        if not is_fixture: continue
        scanned += 1
        try: mtime = d.stat().st_mtime
        except OSError: continue
        if mtime > cutoff: continue    # too young
        # Has a matching row? Channel dirs are named after channel ids; episode
        # dirs after episode ids. If either matches a live row, skip.
        if name.startswith("pep_") and name in known_ep: continue
        if (name.startswith("chan_") or name.startswith("pch_")) and \
              name in known_ch: continue
        sz = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        if not dry_run:
            try:
                import shutil as _sh
                _sh.rmtree(d)
                deleted += 1; freed += sz
            except OSError as e:
                errors.append(f"{name}: rmtree {e}")
        else:
            deleted += 1; freed += sz
    rec = {"run_at": datetime.now(timezone.utc),
              "kind": "local_podcast_fixture_orphans",
              "ttl_hours": ttl_h, "scanned": scanned,
              "deleted_count": deleted, "freed_bytes": freed,
              "dry_run": dry_run, "errors": errors[:25]}
    try: await db.hygiene_runs.insert_one(rec)
    except Exception: pass
    rec.pop("_id", None)
    logger.info("[hygiene-fixture] scanned=%d deleted=%d freed=%d B",
                          scanned, deleted, freed)
    return rec


def tick_supervisor_log_rotation(*, dry_run: bool = False) -> dict:
    """Truncate backend.err.log and backend.out.log to the last
    SUPERVISOR_LOG_KEEP_TAIL bytes when they cross
    SUPERVISOR_LOG_ROTATE_THRESHOLD. supervisord.log is skipped (its
    operational events matter for incident debug across restarts).
    Synchronous on purpose (single read + truncate per file)."""
    if not SUPERVISOR_LOG_DIR.is_dir():
        return {"kind": "supervisor_log_rotate", "rotated": 0, "freed_bytes": 0,
                  "files": []}
    rotated = 0; freed = 0; files: list[dict] = []
    targets = ["backend.err.log", "backend.out.log"]
    for name in targets:
        p = SUPERVISOR_LOG_DIR / name
        if not p.is_file(): continue
        sz_before = p.stat().st_size
        if sz_before <= SUPERVISOR_LOG_ROTATE_THRESHOLD: continue
        if dry_run:
            files.append({"file": name, "size_before": sz_before,
                                  "would_truncate": True})
            rotated += 1; freed += sz_before - SUPERVISOR_LOG_KEEP_TAIL
            continue
        try:
            # Read the last KEEP_TAIL bytes — boundary-safe to next newline.
            with open(p, "rb") as f:
                f.seek(max(0, sz_before - SUPERVISOR_LOG_KEEP_TAIL))
                tail = f.read()
            # Trim leading partial line so log starts at a record boundary.
            nl = tail.find(b"\n")
            if 0 <= nl < 2048: tail = tail[nl + 1:]
            with open(p, "wb") as f:
                f.write(b"# [rotated " + datetime.now(timezone.utc)
                              .isoformat().encode() + b" - earlier "
                              + str(sz_before).encode() + b" bytes truncated]\n")
                f.write(tail)
            sz_after = p.stat().st_size
            rotated += 1; freed += sz_before - sz_after
            files.append({"file": name, "size_before": sz_before,
                                  "size_after": sz_after,
                                  "bytes_freed": sz_before - sz_after})
        except OSError as e:
            files.append({"file": name, "error": str(e)})
    return {"kind": "supervisor_log_rotate", "rotated": rotated,
              "freed_bytes": freed, "dry_run": dry_run, "files": files}
