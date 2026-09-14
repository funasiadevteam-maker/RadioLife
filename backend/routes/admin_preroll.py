"""Phase H'.4 — runtime-tunable admin pre-roll chain count.

PATCH /api/admin/preroll/chain-count  body {count: 1..5}
GET  /api/admin/preroll/chain-count

Backed by `system_config` collection with `_id="preroll_chain_count"`.
Reads from `services.preroll_ad_service._resolved_chain_count()` are
overridden at runtime when this row exists; env var `PREROLL_CHAIN_COUNT`
remains the boot default for un-configured deployments.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_admin

log = logging.getLogger("bigfm.preroll_admin")

router = APIRouter(prefix="/api/admin/preroll", tags=["admin-preroll"])

CONFIG_ID = "preroll_chain_count"
MIN_COUNT = 1
MAX_COUNT = 5


class ChainCountIn(BaseModel):
    count: int = Field(..., ge=MIN_COUNT, le=MAX_COUNT)


def _env_default() -> int:
    try:
        n = int(os.environ.get("PREROLL_CHAIN_COUNT", "1"))
    except (TypeError, ValueError):
        n = 1
    return max(MIN_COUNT, min(n, MAX_COUNT))


async def get_effective_chain_count(db) -> int:
    """Called from preroll_ad_service._resolved_chain_count() when the
    request has a db handle available.  Returns the live override when
    set, else the env default.
    """
    try:
        row = await db.system_config.find_one({"_id": CONFIG_ID})
    except Exception:
        row = None
    if row and isinstance(row.get("value"), int):
        return max(MIN_COUNT, min(row["value"], MAX_COUNT))
    return _env_default()


@router.get("/chain-count")
async def read_chain_count(request: Request,
                                                  _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    row = await db.system_config.find_one({"_id": CONFIG_ID})
    override = row["value"] if row and isinstance(row.get("value"), int) else None
    env_default = _env_default()
    effective = override if override is not None else env_default
    return {"effective_count": effective,
                  "override_count": override,
                  "env_default":      env_default,
                  "min": MIN_COUNT, "max": MAX_COUNT,
                  "updated_at": (row or {}).get("updated_at"),
                  "updated_by": (row or {}).get("updated_by")}


@router.patch("/chain-count")
async def set_chain_count(body: ChainCountIn, request: Request,
                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    now = datetime.now(timezone.utc).isoformat()
    await db.system_config.update_one(
        {"_id": CONFIG_ID},
        {"$set": {"_id": CONFIG_ID,
                            "value": int(body.count),
                            "updated_at": now,
                            "updated_by": admin.get("user_id") or "admin"}},
        upsert=True)
    log.info("[preroll-admin] chain_count set to %d by %s",
                      body.count, admin.get("user_id"))
    return await read_chain_count(request, admin)



# ─────────────────────────────────────────────────────────────────────
# Phase COMPANION.1 — admin-tunable pre-roll HOP COOLDOWN.
# Once a pre-roll has played, no further pre-roll fires for N seconds
# regardless of station, so rapid station-hopping never re-triggers one.
# Backed by `system_config` `_id="preroll_hop_cooldown_seconds"`; env var
# PREROLL_HOP_COOLDOWN_SECONDS is the boot default (90s). 0 disables it.
# ─────────────────────────────────────────────────────────────────────
HOP_CONFIG_ID = "preroll_hop_cooldown_seconds"
HOP_MIN = 0
HOP_MAX = 600


def _hop_env_default() -> int:
    try:
        n = int(os.environ.get("PREROLL_HOP_COOLDOWN_SECONDS", "90"))
    except (TypeError, ValueError):
        n = 90
    return max(HOP_MIN, min(n, HOP_MAX))


async def get_effective_hop_cooldown(db) -> int:
    """Live override when set, else the env default. Called by
    preroll_ad_service._resolved_hop_cooldown_async()."""
    try:
        row = await db.system_config.find_one({"_id": HOP_CONFIG_ID})
    except Exception:
        row = None
    if row and isinstance(row.get("value"), int):
        return max(HOP_MIN, min(row["value"], HOP_MAX))
    return _hop_env_default()


class HopCooldownIn(BaseModel):
    seconds: int = Field(..., ge=HOP_MIN, le=HOP_MAX)


@router.get("/hop-cooldown")
async def read_hop_cooldown(request: Request,
                            _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    row = await db.system_config.find_one({"_id": HOP_CONFIG_ID})
    override = row["value"] if row and isinstance(row.get("value"), int) else None
    env_default = _hop_env_default()
    effective = override if override is not None else env_default
    return {"effective_seconds": effective,
            "override_seconds": override,
            "env_default": env_default,
            "min": HOP_MIN, "max": HOP_MAX,
            "updated_at": (row or {}).get("updated_at"),
            "updated_by": (row or {}).get("updated_by")}


@router.patch("/hop-cooldown")
async def set_hop_cooldown(body: HopCooldownIn, request: Request,
                           admin: dict = Depends(require_admin)):
    db = request.app.state.db
    now = datetime.now(timezone.utc).isoformat()
    await db.system_config.update_one(
        {"_id": HOP_CONFIG_ID},
        {"$set": {"_id": HOP_CONFIG_ID,
                  "value": int(body.seconds),
                  "updated_at": now,
                  "updated_by": admin.get("user_id") or "admin"}},
        upsert=True)
    log.info("[preroll-admin] hop_cooldown set to %ds by %s",
             body.seconds, admin.get("user_id"))
    return await read_hop_cooldown(request, admin)