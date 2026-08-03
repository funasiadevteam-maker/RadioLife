"""Phase 12c — Disk hygiene for audio cache directories.

Prunes `storage/segments/` and `storage/rj/`:

    1. TTL-based: delete files older than the configured TTL.
    2. Max-bytes LRU: if total dir size still exceeds the configured
       cap, evict oldest mtime first until under cap.

Per-target env knobs (defaults shown):
    BIGFM_SEGMENT_TTL_MINUTES = 30
    BIGFM_SEGMENT_MAX_BYTES   = 2 GB
    BIGFM_RJ_TTL_MINUTES      = 60
    BIGFM_RJ_MAX_BYTES        = 1 GB

Phase 12c Hotfix #3 (2026-05-27):
  - Renamed public surface to `prune_directory(...)` and
    `run_hygiene_pass(db)` per the platform handoff spec. The legacy
    names `prune_dir` / `prune_all` are preserved as thin aliases so
    existing callers keep working.
  - Per-target TTL + cap (segments and rj can now diverge).
  - `run_hygiene_pass` returns the same shape as before and emits a
    single summary log line that the boot path can grep on:
        `Phase 12c hygiene: pruned ... files ... from segments, ... from rj`

Idempotent. Safe to call from both lifespan boot and the 12b hourly
scheduler. Errors on individual files do not abort the whole sweep.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("bigfm.hygiene")

# Per-target defaults (read once at import; overridable via env)
SEGMENT_DIR = "/app/backend/storage/segments"
RJ_DIR = "/app/backend/storage/rj"

SEGMENT_TTL_MIN = int(os.environ.get("BIGFM_SEGMENT_TTL_MINUTES", "30"))
SEGMENT_MAX_BYTES = int(
    os.environ.get("BIGFM_SEGMENT_MAX_BYTES", str(2 * 1024 ** 3)))  # 2 GB
RJ_TTL_MIN = int(os.environ.get("BIGFM_RJ_TTL_MINUTES", "60"))
RJ_MAX_BYTES = int(
    os.environ.get("BIGFM_RJ_MAX_BYTES", str(1 * 1024 ** 3)))  # 1 GB


def _policy_for(dir_path: str | Path) -> tuple[int, int]:
    name = Path(dir_path).name
    if name == "rj":
        return RJ_TTL_MIN * 60, RJ_MAX_BYTES
    return SEGMENT_TTL_MIN * 60, SEGMENT_MAX_BYTES


def _safe_unlink(path: Path) -> int:
    try:
        size = path.stat().st_size
        path.unlink(missing_ok=True)
        return size
    except FileNotFoundError:
        return 0
    except Exception as e:
        logger.debug(f"hygiene unlink failed for {path}: {e}")
        return 0


def prune_directory(dir_path: str | Path, *,
                                ttl_seconds: int | None = None,
                                max_bytes: int | None = None,
                                now_ts: float | None = None) -> dict:
    """Run TTL + LRU prune for a single directory.

    If `ttl_seconds` / `max_bytes` are omitted, the per-target policy
    (`segments` vs `rj`, derived from the dir basename) is used.

    `now_ts` lets tests override 'now' to test the TTL path without
    actually sleeping. Defaults to real wall clock.
    """
    p = Path(dir_path)
    if not p.exists() or not p.is_dir():
        return {"dir": str(p), "files_removed": 0, "bytes_freed": 0,
                  "skipped": True}

    pol_ttl, pol_max = _policy_for(p)
    if ttl_seconds is None:
        ttl_seconds = pol_ttl
    if max_bytes is None:
        max_bytes = pol_max

    now = now_ts if now_ts is not None else time.time()
    cutoff = now - ttl_seconds

    files: list[tuple[float, int, Path]] = []  # (mtime, size, path)
    for entry in p.iterdir():
        if not entry.is_file():
            continue
        try:
            st = entry.stat()
            files.append((st.st_mtime, st.st_size, entry))
        except FileNotFoundError:
            continue

    removed = 0
    bytes_freed = 0
    # Phase 1 — TTL
    keep: list[tuple[float, int, Path]] = []
    for mtime, size, path in files:
        if mtime < cutoff:
            bytes_freed += _safe_unlink(path)
            removed += 1
        else:
            keep.append((mtime, size, path))

    # Phase 2 — LRU eviction if still over cap
    total = sum(s for _m, s, _p in keep)
    if total > max_bytes:
        keep.sort(key=lambda t: t[0])  # oldest first
        for mtime, size, path in keep:
            if total <= max_bytes:
                break
            bytes_freed += _safe_unlink(path)
            removed += 1
            total -= size

    return {"dir": str(p),
              "files_removed": removed,
              "bytes_freed": bytes_freed,
              "skipped": False}


# Legacy alias — kept so prior callers (server.py + retention cron)
# keep working without an edit cascade.
def prune_dir(*args, **kwargs) -> dict:
    return prune_directory(*args, **kwargs)


def run_hygiene_pass(_db=None,
                                  targets: Iterable[str] | None = None) -> dict:
    """Prune every target dir; emit a single aggregate summary log.

    The `_db` arg is accepted but currently unused — kept in the
    signature for parity with the rest of the 12b/12c scheduler
    surface and so future versions can persist hygiene-run audits to
    Mongo without breaking callers.
    """
    results = [prune_directory(t) for t in (targets or (SEGMENT_DIR, RJ_DIR))]
    files_total = sum(r["files_removed"] for r in results)
    bytes_total = sum(r["bytes_freed"] for r in results)
    parts = []
    for r in results:
        if r.get("skipped"):
            continue
        mb = r["bytes_freed"] / 1024 / 1024
        parts.append(
            f"{r['files_removed']} files ({mb:.1f} MB) from "
            f"{Path(r['dir']).name}")
    summary = ", ".join(parts) if parts else "nothing to prune"
    logger.info(f"Phase 12c hygiene: pruned {summary}")
    return {"results": results,
              "files_total": files_total,
              "bytes_total": bytes_total,
              "summary": summary}


# Legacy alias
def prune_all(targets: Iterable[str] | None = None) -> dict:
    return run_hygiene_pass(None, targets)


async def ensure_hygiene_indexes(_db) -> None:
    """No collections needed — placeholder for future audit if we want
    to persist hygiene runs. Kept for API parity with the other
    ensure_*_indexes hooks."""
    return None
