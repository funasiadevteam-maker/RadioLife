"""Hygiene cron upgrade tests (post-repack 2026-06-04).

Tests the new TTL-gated orphan-no-row sweep + chan_*/pch_* test-fixture
sweep + supervisor log rotation.
"""
from __future__ import annotations
import asyncio, os, sys, time, uuid
from pathlib import Path
import pytest

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
except Exception: pass


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


# ─── 1. Orphan-no-row dir IS swept when mtime > TTL ─────────────
def test_hygiene_a_orphan_no_row_swept_when_older_than_ttl(monkeypatch):
    from services import hygiene18c
    monkeypatch.setenv("HYGIENE_ORPHAN_AGE_HOURS", "1")
    db = _db()
    sid = f"prs_orph_{uuid.uuid4().hex[:8]}"
    d = hygiene18c.LOCAL_RECORDINGS_ROOT / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "host.mp3").write_bytes(b"\x00" * 1000)
    # Backdate mtime to 2 hours ago.
    past = time.time() - 2 * 3600
    os.utime(d, (past, past))
    try:
        r = run(hygiene18c.tick_local_recording_orphans(db, dry_run=False))
        # Was swept (deleted_count ≥ 1).
        assert r.get("deleted_count", 0) >= 1, r
        assert not d.exists(), f"dir {d} should be gone"
    finally:
        if d.exists():
            import shutil; shutil.rmtree(d, ignore_errors=True)


# ─── 2. Orphan-no-row dir is PRESERVED when mtime < TTL ────────
def test_hygiene_b_orphan_no_row_preserved_when_younger_than_ttl(monkeypatch):
    from services import hygiene18c
    monkeypatch.setenv("HYGIENE_ORPHAN_AGE_HOURS", "24")
    db = _db()
    sid = f"prs_young_{uuid.uuid4().hex[:8]}"
    d = hygiene18c.LOCAL_RECORDINGS_ROOT / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "host.mp3").write_bytes(b"\x00" * 500)
    # Backdate by only 1 hour (TTL is 24).
    young = time.time() - 1 * 3600
    os.utime(d, (young, young))
    try:
        run(hygiene18c.tick_local_recording_orphans(db, dry_run=False))
        assert d.exists(), f"young orphan {d} must be preserved"
    finally:
        if d.exists():
            import shutil; shutil.rmtree(d, ignore_errors=True)


# ─── 3. test-fixture chan_*/pch_*/pep_*/ swept when older than TTL ──
def test_hygiene_c_test_fixture_dirs_swept_when_older_than_ttl(monkeypatch):
    from services import hygiene18c
    monkeypatch.setenv("HYGIENE_ORPHAN_AGE_HOURS", "1")
    db = _db()
    # Plant a chan_ + pch_ + pep_ dir with no matching DB row, backdated.
    planted: list[Path] = []
    for prefix in ("chan_", "pch_", "pep_"):
        d = hygiene18c.LOCAL_PODCASTS_ROOT / f"{prefix}t_{uuid.uuid4().hex[:8]}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "audio.mp3").write_bytes(b"\x00" * 2048)
        past = time.time() - 2 * 3600
        os.utime(d, (past, past))
        planted.append(d)
    try:
        r = run(hygiene18c.tick_local_podcast_fixture_orphans(
            db, dry_run=False))
        assert r["kind"] == "local_podcast_fixture_orphans"
        assert r["deleted_count"] >= 3, r
        for d in planted: assert not d.exists(), f"{d} should be swept"
    finally:
        for d in planted:
            if d.exists():
                import shutil; shutil.rmtree(d, ignore_errors=True)


# ─── 4. Supervisor log rotation truncates when oversized ─────────
def test_hygiene_d_supervisor_log_rotation(tmp_path, monkeypatch):
    from services import hygiene18c
    # Redirect the module-level constants to a tmp_path so we don't touch
    # the real /var/log/supervisor.
    fake_log_dir = tmp_path / "supervisor"
    fake_log_dir.mkdir()
    big = fake_log_dir / "backend.err.log"
    # Write 11 MB of synthetic log lines.
    line = (b"2026-06-04 line of log content " * 8 + b"\n")    # ~250 B
    chunk = line * 4096        # ~1 MB
    with open(big, "wb") as f:
        for _ in range(11): f.write(chunk)
    small = fake_log_dir / "backend.out.log"
    small.write_bytes(b"only a tiny log\n" * 10)
    skip = fake_log_dir / "supervisord.log"
    skip.write_bytes(line * 4096 * 11)    # 11 MB but must be SKIPPED
    monkeypatch.setattr(hygiene18c, "SUPERVISOR_LOG_DIR", fake_log_dir)
    sz_before_big = big.stat().st_size
    sz_before_skip = skip.stat().st_size
    r = hygiene18c.tick_supervisor_log_rotation(dry_run=False)
    assert r["kind"] == "supervisor_log_rotate"
    assert r["rotated"] == 1, r    # only backend.err.log crossed threshold
    sz_after_big = big.stat().st_size
    assert sz_after_big < sz_before_big
    # Tail kept is ~2 MB + a small header — must be under 2.5 MB total.
    assert sz_after_big < 2.5 * 1024 * 1024
    # Small log unchanged.
    assert small.stat().st_size < 1024
    # supervisord.log skipped — must be unchanged.
    assert skip.stat().st_size == sz_before_skip
