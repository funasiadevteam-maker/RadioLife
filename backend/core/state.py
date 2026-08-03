"""In-memory state shared across radio routes — locks + prefetch tasks."""
from __future__ import annotations

import asyncio
from typing import Dict

_session_locks: Dict[str, asyncio.Lock] = {}
prefetch_tasks: Dict[str, asyncio.Task] = {}
switch_build_tasks: Dict[str, asyncio.Task] = {}


def lock_for(sid: str) -> asyncio.Lock:
    lk = _session_locks.get(sid)
    if lk is None:
        lk = asyncio.Lock()
        _session_locks[sid] = lk
    return lk
