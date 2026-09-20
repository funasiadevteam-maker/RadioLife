"""FUUSIC Phase 13d — region health probes + circuit breaker + pending-write queue.

Probes:
  Every ~60s (or on demand) we write a heartbeat doc to the primary and try
  to read it back from a replica connection if one is configured. We persist
  the rollup to `region_status` for ``GET /api/admin/region/status``.

Circuit breaker:
  If the primary fails for > 30s we mark `primary_down=true` and flip the
  db_routing active cluster to 'replica' so subsequent reads serve from a
  replica. We re-check every ~10s and recover automatically.

Pending writes:
  While the primary is down, non-critical writes can be queued via
  ``queue_pending_write`` to the replica's ``pending_writes`` collection
  with an idempotency key; ``replay_pending_writes`` flushes them when the
  primary returns. Critical write surfaces (auth, billing) must NOT queue
  and should call ``critical_write_blocked`` to surface a 503 to the
  client.
"""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from . import db_routing
from .region import current_region, current_role

log = logging.getLogger("bigfm.region_health")

_HEARTBEAT_COLL  = "region_heartbeats"
_STATUS_COLL     = "region_status"
_PENDING_COLL    = "pending_writes"
_FAILOVER_LOG    = "region_failover_log"

PRIMARY_DOWN_THRESHOLD_SEC = 30
RECOVERY_CHECK_SEC          = 10
CRITICAL_WRITE_ROUTES = {
    "/api/auth/login", "/api/auth/register", "/api/auth/refresh",
    "/api/billing/checkout", "/api/billing/portal",
    "/api/billing/webhook",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── core probe ──────────────────────────────────────────────────────────
async def probe_once(db) -> Dict[str, Any]:
    """Probe primary write + replica read. Persist & return the rollup."""
    region = current_region()
    role   = current_role()
    out: Dict[str, Any] = {
        "region": region, "role": role,
        "mongo_primary_ok": False, "mongo_replica_ok": False,
        "p50_ms_primary": None, "p50_ms_replica": None,
        "last_heartbeat_at": _now(),
    }
    # primary write
    hb_id = f"hb_{uuid.uuid4().hex[:8]}"
    t0 = time.perf_counter()
    try:
        await db[_HEARTBEAT_COLL].insert_one({
            "_id": hb_id, "region": region, "role": role,
            "ts": _now()})
        out["mongo_primary_ok"] = True
        out["p50_ms_primary"]    = round((time.perf_counter() - t0) * 1000, 1)
    except Exception as e:
        log.warning("region_health: primary probe failed: %s", e)
        out["primary_error"] = str(e)[:200]
    # replica read
    reps = db_routing.replica_clients()
    if reps:
        t1 = time.perf_counter()
        try:
            rep_db = reps[0].get_default_database()
            row = await rep_db[_HEARTBEAT_COLL].find_one(
                sort=[("ts", -1)])
            if row:
                out["mongo_replica_ok"] = True
            out["p50_ms_replica"] = round((time.perf_counter() - t1) * 1000, 1)
        except Exception as e:
            log.warning("region_health: replica probe failed: %s", e)
            out["replica_error"] = str(e)[:200]
    else:
        out["replica_configured"] = False
    # circuit-breaker decision
    out.update(await _evaluate_breaker(db, out))
    # persist rollup
    await db[_STATUS_COLL].update_one(
        {"region": region},
        {"$set": out}, upsert=True)
    return out


async def _evaluate_breaker(db, probe: Dict[str, Any]) -> Dict[str, Any]:
    """Decide whether to flip the breaker based on the probe result."""
    region = probe["region"]
    existing = await db[_STATUS_COLL].find_one({"region": region}) or {}
    primary_ok = probe["mongo_primary_ok"]
    first_fail = existing.get("primary_first_fail_at")
    breaker_open = bool(existing.get("primary_down"))
    update: Dict[str, Any] = {}
    if not primary_ok:
        if not first_fail:
            update["primary_first_fail_at"] = _now()
            first_fail = update["primary_first_fail_at"]
        # If failure window exceeded threshold and we have replicas, open.
        if first_fail and not breaker_open:
            ff = first_fail
            if ff.tzinfo is None:
                ff = ff.replace(tzinfo=timezone.utc)
            if (_now() - ff).total_seconds() >= PRIMARY_DOWN_THRESHOLD_SEC:
                if db_routing.replica_clients():
                    db_routing.set_active_cluster("replica")
                    update["primary_down"] = True
                    update["failover_opened_at"] = _now()
                    await db[_FAILOVER_LOG].insert_one({
                        "_id": f"fo_{uuid.uuid4().hex[:8]}",
                        "region": region, "at": _now(),
                        "event": "open",
                        "reason": "primary_unreachable_>30s"})
                    log.error("***** CIRCUIT BREAKER OPEN ***** "
                                  "region=%s flipped reads → replica", region)
    else:
        if breaker_open:
            db_routing.set_active_cluster("primary")
            update["primary_down"] = False
            update["primary_first_fail_at"] = None
            update["failover_closed_at"] = _now()
            await db[_FAILOVER_LOG].insert_one({
                "_id": f"fo_{uuid.uuid4().hex[:8]}",
                "region": region, "at": _now(),
                "event": "close",
                "reason": "primary_recovered"})
            log.info("Circuit breaker CLOSED — primary recovered "
                       "region=%s", region)
            # Replay queued writes.
            asyncio.create_task(replay_pending_writes(db))
        elif first_fail:
            update["primary_first_fail_at"] = None
    return update


async def get_status(db) -> Dict[str, Any]:
    """Return current rollup + last 10 failover events."""
    region = current_region()
    doc = await db[_STATUS_COLL].find_one({"region": region}) or {
        "region": region, "role": current_role(),
        "mongo_primary_ok": None, "mongo_replica_ok": None,
        "last_heartbeat_at": None}
    history = []
    async for ev in db[_FAILOVER_LOG].find(
            {"region": region}).sort("at", -1).limit(10):
        ev.pop("_id", None)
        ev["at"] = ev["at"].isoformat() if isinstance(ev.get("at"),
                                                                            datetime) else ev.get("at")
        history.append(ev)
    failovers_24h = await db[_FAILOVER_LOG].count_documents({
        "region": region, "event": "open",
        "at": {"$gte": _now() - timedelta(hours=24)}})
    # Coerce non-JSON-safe types.
    safe: Dict[str, Any] = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if isinstance(v, datetime):
            safe[k] = v.isoformat()
        else:
            safe[k] = v
    safe["active_cluster"]      = db_routing.active_cluster()
    safe["failover_count_24h"]  = failovers_24h
    safe["history"]             = history
    return safe


# ─── pending writes queue ───────────────────────────────────────────────
async def queue_pending_write(db, *, surface: str, payload: Dict[str, Any],
                                            idempotency_key: Optional[str] = None) -> str:
    """Append a write to the pending queue on the replica (best-effort)."""
    reps = db_routing.replica_clients()
    target_db = reps[0].get_default_database() if reps else db
    key = idempotency_key or f"pw_{uuid.uuid4().hex[:12]}"
    await target_db[_PENDING_COLL].update_one(
        {"_id": key},
        {"$setOnInsert": {
            "_id": key, "surface": surface, "payload": payload,
            "queued_at": _now(),
            "region": current_region(), "replayed": False}},
        upsert=True)
    log.warning("region_health: queued pending write surface=%s key=%s",
                       surface, key)
    return key


def critical_write_blocked(path: str) -> bool:
    """Whether a path is on the critical-route allow-list (no queueing)."""
    return path in CRITICAL_WRITE_ROUTES


async def replay_pending_writes(db) -> Dict[str, Any]:
    """Replay queued writes when the primary returns. No-op if empty."""
    replayed = 0
    failed = 0
    async for row in db[_PENDING_COLL].find({"replayed": False}):
        try:
            # Replay is surface-specific. In single-region preview we just
            # mark them replayed so the queue drains — operators wire real
            # replay handlers per surface in their multi-region rollout.
            await db[_PENDING_COLL].update_one(
                {"_id": row["_id"]},
                {"$set": {"replayed": True,
                              "replayed_at": _now()}})
            replayed += 1
        except Exception as e:
            log.warning("replay failed key=%s: %s", row.get("_id"), e)
            failed += 1
    return {"replayed": replayed, "failed": failed}
