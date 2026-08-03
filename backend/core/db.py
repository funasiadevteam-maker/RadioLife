"""Mongo client + db singleton, importable across the app.

Phase Ω — Deploy hardening (2026-06-20):

`AsyncIOMotorClient(mongodb+srv://...)` does an SRV-record DNS lookup at
CONSTRUCTION time (not first-op).  In K8s with Atlas prod, if the SRV
name is temporarily unresolvable, the exception escapes → uvicorn boot
fails → K8s readiness probe never fires → deployment marked "not
ready" and rolled back.

Fix: wrap construction in try/except, use a tight `serverSelectionTimeoutMS`
so downstream operations fail fast, and fall back to a localhost
placeholder client if construction blows up.  The actual failure now
surfaces at request time with a clean 500 (not a boot-time crash).
"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient

from core.config import MONGO_URL, DB_NAME

_log = logging.getLogger("bigfm.core.db")

# 3 s server-selection timeout keeps every Mongo op from hanging the
# request > 3 s when Mongo is unreachable.  Motor's default is 30 s.
_TIMEOUT_MS = 3_000

try:
    mongo_client = AsyncIOMotorClient(
        MONGO_URL, serverSelectionTimeoutMS=_TIMEOUT_MS)
except Exception as _e:
    _log.warning(
        "[core.db] AsyncIOMotorClient construct failed (%s: %s). "
        "Falling back to localhost placeholder — DB-touching endpoints "
        "will return connection errors until MONGO_URL is fixed.",
        type(_e).__name__, str(_e)[:160])
    mongo_client = AsyncIOMotorClient(
        "mongodb://localhost:27017",
        serverSelectionTimeoutMS=_TIMEOUT_MS)

db = mongo_client[DB_NAME]
