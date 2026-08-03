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
