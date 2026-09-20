"""FUUSIC Phase 13d — admin region observability endpoints."""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin
from services import region_health
from services.region import current_region, current_role
from services import db_routing

log = logging.getLogger("bigfm.admin_region")

admin_region_router = APIRouter(prefix="/api/admin/region", tags=["admin-region"])


@admin_region_router.get("/status")
async def get_region_status(request: Request,
                                          _u: dict = Depends(require_admin)):
    db = request.app.state.db
    return await region_health.get_status(db)


@admin_region_router.post("/probe")
async def run_region_probe(request: Request,
                                          _u: dict = Depends(require_admin)):
    """Force-run a probe right now (does not wait for the 60s cadence)."""
    db = request.app.state.db
    return await region_health.probe_once(db)


@admin_region_router.post("/promote")
async def promote_region(request: Request,
                                      to: Optional[str] = Query(
                                          None,
                                          description="Target role to switch THIS "
                                          "region to: 'primary' or 'replica'. "
                                          "No-op in single-region preview but "
                                          "documents the contract for future use."),
                                      _u: dict = Depends(require_admin)):
    target = (to or "").lower()
    if target and target not in ("primary", "replica"):
        raise HTTPException(400, "to must be 'primary' or 'replica'")
    return {
        "region": current_region(),
        "current_role": current_role(),
        "requested_role": target or None,
        "active_cluster": db_routing.active_cluster(),
        "applied": False,
        "note": (
            "Single-region preview — promote is a documented no-op. In "
            "production this would update the orchestrator's region "
            "registry and trigger DNS / read-pref flips."
        ),
    }
