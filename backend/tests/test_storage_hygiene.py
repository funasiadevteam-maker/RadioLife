"""Phase 12c Hotfix #3 — disk hygiene unit tests.

Three cases:
  1. `prune_directory` respects TTL (files older than ttl_seconds gone,
     newer ones kept).
  2. `prune_directory` respects max_bytes via LRU eviction.
  3. `run_hygiene_pass` logs the aggregate `Phase 12c hygiene: pruned`
     summary line.

Pure-disk tests — no Mongo, no HTTP. Uses a temp dir so it never
touches `/app/backend/storage/*`.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path

import pytest

from services import storage_hygiene as sh


def _make_file(p: Path, *, size: int, mtime: float) -> None:
    """Create a file of the requested logical size with a precise mtime.

    Uses a sparse file (`truncate`) so we don't actually write 100 MB
    of bytes — the kernel still reports the logical size via stat.
    """
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        if size > 0:
            f.truncate(size)
    os.utime(p, (mtime, mtime))


# ─── 1. TTL eviction ─────────────────────────────────────────────────
def test_prune_directory_respects_ttl(tmp_path):
    """Files at -10min stay; -40min and -2h get evicted under a 30-min
    TTL."""
    now = time.time()
    _make_file(tmp_path / "fresh.mp3", size=10, mtime=now - 10 * 60)
    _make_file(tmp_path / "stale40.mp3", size=10, mtime=now - 40 * 60)
    _make_file(tmp_path / "stale2h.mp3", size=10, mtime=now - 2 * 3600)

    out = sh.prune_directory(
        tmp_path,
        ttl_seconds=30 * 60,
        max_bytes=10 * 1024 ** 3,  # effectively no cap
        now_ts=now)

    assert out["files_removed"] == 2
    survivors = {p.name for p in tmp_path.iterdir()}
    assert survivors == {"fresh.mp3"}


# ─── 2. LRU eviction under cap ───────────────────────────────────────
def test_prune_directory_respects_max_bytes(tmp_path):
    """10×100MB sparse files with monotonically increasing mtimes;
    max_bytes=500MB should keep the 5 newest only."""
    now = time.time()
    size = 100 * 1024 * 1024  # 100 MB
    for i in range(10):
        # i=0 is OLDEST (mtime far in the past), i=9 is NEWEST
        _make_file(tmp_path / f"f{i:02d}.mp3", size=size,
                       mtime=now - (10 - i) * 60)

    out = sh.prune_directory(
        tmp_path,
        ttl_seconds=24 * 3600,  # TTL won't fire, only LRU
        max_bytes=500 * 1024 * 1024,
        now_ts=now)

    assert out["files_removed"] == 5
    survivors = sorted(p.name for p in tmp_path.iterdir())
    # The 5 NEWEST should survive (f05..f09)
    assert survivors == [f"f{i:02d}.mp3" for i in range(5, 10)]


# ─── 3. run_hygiene_pass logs aggregate summary ──────────────────────
def test_run_hygiene_pass_logs_summary(tmp_path, caplog):
    """Custom targets list + caplog assertion on the summary log line."""
    seg = tmp_path / "segments"
    rj = tmp_path / "rj"
    # Two old files in segments, one old in rj.
    old = time.time() - 7200  # 2 hours
    _make_file(seg / "a.mp3", size=8, mtime=old)
    _make_file(seg / "b.mp3", size=8, mtime=old)
    _make_file(rj / "c.mp3", size=8, mtime=old)

    with caplog.at_level(logging.INFO, logger="bigfm.hygiene"):
        out = sh.run_hygiene_pass(None, targets=(str(seg), str(rj)))

    assert out["files_total"] == 3
    # Summary line must mention both targets
    msgs = [r.message for r in caplog.records
                if r.name == "bigfm.hygiene"]
    summary = next((m for m in msgs if m.startswith(
        "Phase 12c hygiene: pruned")), None)
    assert summary is not None, msgs
    assert "segments" in summary
    assert "rj" in summary
