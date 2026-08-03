"""Phase 36c.5 hardening — post-finalize local cleanup tests.

Live tests against the configured Tigris bucket. Validate that:
  1. finalize_session uploads recordings to Tigris, HEAD-verifies, then
        DELETES the local mp3 files and the empty session dir.
  2. The local-recording-orphans hygiene sweep deletes session dirs
        belonging to completed sessions whose Tigris keys are present —
        and KEEPS dirs when any key is missing.
"""
from __future__ import annotations
import asyncio, os, shutil, subprocess, sys, uuid
from pathlib import Path

import pytest

sys.path.insert(0, "/app/backend")

try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

from services import object_storage as obs    # noqa: E402

TIGRIS_LIVE = (os.environ.get("STORAGE_BACKEND") or "").lower() == "tigris"

pytestmark = pytest.mark.skipif(
    not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _make_mp3(path: Path, seconds: float = 1) -> int:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
          "-i", f"sine=frequency=440:duration={seconds}",
          "-codec:a", "libmp3lame", "-b:a", "64k", str(path)],
        check=True, capture_output=True, timeout=15)
    return path.stat().st_size


def test_finalize_deletes_local_files_after_tigris_upload():
    """Stage 1 solo round-trip: stage host.mp3, create the bare minimum
    db rows, call finalize_session, and assert the local session dir is
    EMPTY (or gone) and the Tigris key for mixed.mp3 is present + size-
    verifies."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import podcast_recording as pr
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL") or
                                                  "mongodb://localhost:27017")[
            os.environ.get("DB_NAME") or "bigfm"]
    sid = f"prs_cleanup_{uuid.uuid4().hex[:10]}"
    ch_id = f"ch_cleanup_{uuid.uuid4().hex[:6]}"
    sess_dir = pr.STORAGE_ROOT / sid
    sess_dir.mkdir(parents=True, exist_ok=True)
    host_mp3 = sess_dir / "host.mp3"
    sz = _make_mp3(host_mp3)
    pid = f"prp_cleanup_{uuid.uuid4().hex[:8]}"
    try:
        run(db.podcast_recording_sessions.insert_one({
            "id": sid, "creator_id": "u_test", "channel_id": ch_id,
            "title": "36c.5 cleanup probe",
            "status": "processing",
            "started_at": pr._now(),
            "total_duration_seconds": 1,
            "created_at": pr._now(), "updated_at": pr._now()}))
        run(db.podcast_recording_participants.insert_one({
            "id": pid, "session_id": sid, "user_id": "u_test",
            "role": "host", "display_name": "Host",
            "joined_at": pr._now(),
            "admitted_at": pr._now(),
            "upload_status": "completed",
            "audio_track_url": f"/local/{sid}/host.mp3",
            "created_at": pr._now()}))
        result = run(pr.finalize_session(db, session_id=sid))
        assert result.get("episode_id"), result
        ep_id = result["episode_id"]
        # Local cleanup contract: session dir is gone OR empty.
        leftover = list(sess_dir.rglob("*")) if sess_dir.exists() else []
        leftover_files = [p for p in leftover if p.is_file()]
        assert leftover_files == [], (
            f"local dir not cleaned: {[str(p) for p in leftover_files]}")
        # Tigris contract: mixed.mp3 key is present and ~same size as the
        # ffmpeg-mixed output (we don't know exact size since amix re-
        # encodes, but it must be >0 and HEAD must return).
        s = obs.TigrisStorage()
        key = obs.key_recording_mixed_audio(sid)
        h = s.head(key=key)
        assert h is not None, f"mixed key {key} not on tigris"
        assert int(h.get("size") or 0) > 0
        # Episode row must point at the canonical Tigris key.
        ep = run(db.podcast_episodes.find_one({"id": ep_id}, {"_id": 0}))
        assert ep is not None
        assert ep.get("storage_key_audio") == key
    finally:
        # Cleanup the test artifacts in Tigris + db + disk.
        try:
            obs.TigrisStorage().delete(
                key=obs.key_recording_mixed_audio(sid))
            obs.TigrisStorage().delete(
                key=f"podcasts/recordings/{sid}/host/audio.mp3")
        except Exception: pass
        run(db.podcast_recording_sessions.delete_one({"id": sid}))
        run(db.podcast_recording_participants.delete_one({"id": pid}))
        run(db.podcast_episodes.delete_many({"recording_session_id": sid}))
        run(db.podcast_recordings.delete_many({"session_id": sid}))
        if sess_dir.exists(): shutil.rmtree(sess_dir, ignore_errors=True)


def test_local_recording_orphans_hygiene_sweeps_completed_session_dirs():
    """Plant a leftover session dir + a completed session row + ensure the
    corresponding mixed.mp3 key exists in Tigris → sweep must delete the
    dir. Then plant a second session whose Tigris key is missing → sweep
    must LEAVE that dir in place + log an error."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import hygiene18c
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL") or
                                                  "mongodb://localhost:27017")[
            os.environ.get("DB_NAME") or "bigfm"]
    s = obs.TigrisStorage()

    # Session A: completed, has mixed.mp3 in Tigris → SHOULD sweep.
    sid_a = f"prs_sweepA_{uuid.uuid4().hex[:8]}"
    dir_a = Path("/app/backend/storage/podcasts/recordings") / sid_a
    dir_a.mkdir(parents=True, exist_ok=True)
    mp3_a = dir_a / "mixed.mp3"
    _make_mp3(mp3_a, 0.5)
    key_a = obs.key_recording_mixed_audio(sid_a)
    s.upload(local_path=str(mp3_a), key=key_a, content_type="audio/mpeg")

    # Session B: completed, NO mixed.mp3 in Tigris → MUST NOT sweep.
    sid_b = f"prs_sweepB_{uuid.uuid4().hex[:8]}"
    dir_b = Path("/app/backend/storage/podcasts/recordings") / sid_b
    dir_b.mkdir(parents=True, exist_ok=True)
    mp3_b = dir_b / "mixed.mp3"
    _make_mp3(mp3_b, 0.5)
    # (deliberately NOT uploaded to Tigris)

    try:
        run(db.podcast_recording_sessions.insert_many([
            {"id": sid_a, "status": "completed",
              "channel_id": "ch_x", "creator_id": "u_x",
              "title": "sweepA"},
            {"id": sid_b, "status": "completed",
              "channel_id": "ch_x", "creator_id": "u_x",
              "title": "sweepB"}]))
        # Dry-run first.
        r = run(hygiene18c.tick_local_recording_orphans(db, dry_run=True))
        assert r.get("kind") == "local_recording_orphans"
        assert r.get("dry_run") is True
        assert r.get("scanned", 0) >= 2
        assert r.get("deleted_count", 0) >= 1
        assert dir_a.exists() and dir_b.exists()    # dry-run does not mutate
        # Apply.
        r2 = run(hygiene18c.tick_local_recording_orphans(db, dry_run=False))
        assert r2.get("dry_run") is False
        assert r2.get("deleted_count", 0) >= 1
        # A must be gone, B must remain (with an error log entry).
        assert not dir_a.exists(), "session A dir should be deleted"
        assert dir_b.exists(), "session B dir must be kept (tigris missing)"
        err_text = " ".join(r2.get("errors") or [])
        assert sid_b in err_text or "tigris_keys_missing" in err_text
        # Envelope shape (matches the documented contract).
        for k in ("run_at", "kind", "scanned", "deleted_count",
                          "freed_bytes", "dry_run", "errors"):
            assert k in r2, f"missing field: {k}"
    finally:
        try: s.delete(key=key_a)
        except Exception: pass
        run(db.podcast_recording_sessions.delete_many(
            {"id": {"$in": [sid_a, sid_b]}}))
        if dir_a.exists(): shutil.rmtree(dir_a, ignore_errors=True)
        if dir_b.exists(): shutil.rmtree(dir_b, ignore_errors=True)
