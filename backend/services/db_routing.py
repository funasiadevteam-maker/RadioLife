"""RadioLife Phase 13d — Mongo read-preference + multi-cluster routing.

Single-region preview keeps using ``MONGO_URL``. When operators provide
``BIGFM_MONGO_PRIMARY_URI`` and ``BIGFM_MONGO_REPLICA_URIS`` (csv) we
construct an additional motor client per replica that the circuit-breaker
can flip to.

Public helpers:
    primary_client()          – Motor client for the primary cluster.
    replica_clients()         – list of Motor clients (one per replica URI).
    get_collection(name, read_preference="primary"|"secondary"|"nearest")
                                                     – returns a coll on the appropriate cluster /
                                                       read-preference.
"""
from __future__ import annotations
import logging
import os
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.read_preferences import (
    Primary, Secondary, SecondaryPreferred, Nearest,
)

log = logging.getLogger("bigfm.db_routing")

_DB_NAME = os.environ.get("DB_NAME", "bigfm")

# Routes that benefit from `secondaryPreferred` reads. Anything not in this
# allow-list keeps the default `primary` read-preference for strong
# consistency.
SECONDARY_PREFERRED_COLLECTIONS = {
    # Read-heavy analytics & public surfaces.
    "admin_analytics_overview",
    "admin_analytics_songs",
    "admin_analytics_ads",
    "admin_analytics_games",
    "leaderboards",
    "leaderboard_snapshots",
    "channels",
    "public_passport_profiles",
}

_RP_MAP = {
    "primary":              Primary(),
    "secondary":            Secondary(),
    "secondary_preferred":  SecondaryPreferred(),
    "secondaryPreferred":   SecondaryPreferred(),
    "nearest":              Nearest(),
}

_state: Dict[str, object] = {
    "primary": None,
    "replicas": [],
    "active": "primary",   # circuit-breaker flips this to 'replica'.
}


# ─── connection bootstrap ────────────────────────────────────────────────
def _build_clients() -> None:
    """Build motor clients from env. Idempotent."""
    if _state["primary"] is not None:
        return
    primary_uri = (os.environ.get("BIGFM_MONGO_PRIMARY_URI")
                              or os.environ.get("MONGO_URL"))
    if not primary_uri:
        raise RuntimeError("MONGO_URL (or BIGFM_MONGO_PRIMARY_URI) not set")
    _state["primary"] = AsyncIOMotorClient(primary_uri,
                                                            uuidRepresentation="standard")

    rep_csv = os.environ.get("BIGFM_MONGO_REPLICA_URIS", "").strip()
    replicas: List[AsyncIOMotorClient] = []
    if rep_csv:
        for u in rep_csv.split(","):
            u = u.strip()
            if not u:
                continue
            try:
                replicas.append(AsyncIOMotorClient(
                    u, uuidRepresentation="standard"))
            except Exception as e:
                log.warning("replica URI %s rejected: %s", u, e)
    _state["replicas"] = replicas
    log.info("Phase 13d db_routing: primary=ok replicas=%d", len(replicas))


def primary_client() -> AsyncIOMotorClient:
    _build_clients()
    return _state["primary"]   # type: ignore[return-value]


def replica_clients() -> List[AsyncIOMotorClient]:
    _build_clients()
    return list(_state["replicas"])  # type: ignore[arg-type]


# ─── circuit breaker state ───────────────────────────────────────────────
def set_active_cluster(which: str) -> None:
    """Flip which cluster the helpers route to: 'primary' or 'replica'."""
    if which not in ("primary", "replica"):
        raise ValueError(f"unknown_cluster:{which}")
    if which == "replica" and not replica_clients():
        # No replicas configured → no-op (keep primary).
        log.warning("db_routing: cannot flip to replica — none configured")
        return
    _state["active"] = which


def active_cluster() -> str:
    return _state.get("active", "primary")  # type: ignore[return-value]


def _active_client() -> AsyncIOMotorClient:
    if _state.get("active") == "replica":
        reps = replica_clients()
        if reps:
            return reps[0]
    return primary_client()


# ─── collection helper ───────────────────────────────────────────────────
def get_collection(name: str,
                          read_preference: Optional[str] = None,
                          db_name: Optional[str] = None):
    """Returns a collection handle on the currently-active cluster.

    If `read_preference` is omitted, we auto-pick `secondaryPreferred` for
    well-known read-heavy collections and `primary` for everything else.
    Operators can always force a specific RP from the call site.
    """
    if read_preference is None:
        read_preference = ("secondary_preferred"
                                  if name in SECONDARY_PREFERRED_COLLECTIONS
                                  else "primary")
    rp = _RP_MAP.get(read_preference, Primary())
    client = _active_client()
    db = client.get_database(db_name or _DB_NAME, read_preference=rp)
    return db[name]


__all__ = [
    "SECONDARY_PREFERRED_COLLECTIONS",
    "primary_client", "replica_clients",
    "set_active_cluster", "active_cluster",
    "get_collection",
]
