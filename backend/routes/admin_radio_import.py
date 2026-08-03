"""Phase 42-A — Radio Browser import admin endpoints.

Admin-only diagnostics + manual triggers for the live-radio import
pipeline.  Mirrors the predict_win_admin_sweeper pattern.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_admin
from services.radio_browser_import import (
    DEFAULT_IMPORT_INTERVAL_HOURS,
    DEFAULT_HEALTH_INTERVAL_HOURS,
    HEALTH_CHECK_TOP_N,
    health_check_station,
    import_daily_full_sync,
)
import httpx


router = APIRouter(prefix="/api/admin/radio-import",
                                  tags=["radio-import-admin"])


def _iso(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _strip_mongo(d: dict) -> dict:
    out = {**d}
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@router.post("/run-now",
                            description=(
                                "Force-fire an immediate Radio Browser sync.  Pass "
                                "`?full_catalog=true` to paginate the entire RB "
                                "catalog (~50K stations, 30-60 min runtime); the "
                                "default is the legacy top-N sync."))
async def admin_run_now(request: Request,
                                              full_catalog: bool = False,
                                              background: bool = False,
                                              user: dict = Depends(require_admin)):
    db = request.app.state.db
    if background:
        import asyncio as _asyncio
        _asyncio.create_task(
            import_daily_full_sync(db, trigger="manual",
                                                                full_catalog=full_catalog))
        return {"ok": True, "started_in_background": True,
                      "full_catalog": full_catalog,
                      "note": "Poll GET /api/admin/radio-import/status for chunk progress."}
    log_doc = await import_daily_full_sync(db, trigger="manual",
                                                                                        full_catalog=full_catalog)
    return {"ok": True, "run": _strip_mongo(log_doc)}


@router.post("/cancel",
                          description=(
                              "Set the cancel flag on the active full-sync run. "
                              "The paginated walker checks this flag between "
                              "chunks and exits cleanly."))
async def admin_cancel(request: Request,
                                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    state = await db.radio_import_state.find_one({"_id": "last_full_sync"})
    if not state or not state.get("active_run_id"):
        return {"ok": False, "code": "no_active_run"}
    await db.radio_import_state.update_one(
        {"_id": "last_full_sync"},
        {"$set": {"cancel_requested": True,
                              "cancel_requested_at": datetime.utcnow()}})
    return {"ok": True, "active_run_id": state.get("active_run_id"),
                  "note": "Run will halt at the next chunk boundary."}


@router.get("/status",
                          description=(
                              "Last 10 import run logs + scheduler config + live "
                              "chunk progress (if a paginated full sync is in "
                              "flight).  Admin auth."))
async def admin_status(request: Request,
                                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.radio_import_logs.find().sort("started_at", -1).limit(10)
    runs = [_strip_mongo(r) async for r in cur]
    state = await db.radio_import_state.find_one({"_id": "last_full_sync"}) or {}
    stations_total = await db.imported_radio_stations.count_documents({})
    stations_active = await db.imported_radio_stations.count_documents(
        {"active": True})
    by_health = {}
    async for r in db.imported_radio_stations.aggregate([
            {"$group": {"_id": "$stream_health_status",
                                  "count": {"$sum": 1}}}]):
        by_health[r["_id"] or "unknown"] = r["count"]
    # Live chunk progress.
    chunk_progress = state.get("chunk_progress") or {}
    if chunk_progress:
        for k in ("started_at", "updated_at", "finished_at"):
            if isinstance(chunk_progress.get(k), datetime):
                chunk_progress[k] = chunk_progress[k].isoformat()
    return {
        "scheduler": {
            "full_sync_interval_hours": DEFAULT_IMPORT_INTERVAL_HOURS,
            "health_check_interval_hours": DEFAULT_HEALTH_INTERVAL_HOURS,
            "health_check_top_n": HEALTH_CHECK_TOP_N,
            "last_full_sync_completed_at": _iso(state.get("completed_at")),
            "last_full_sync_ok": state.get("ok"),
            "last_full_sync_fetched": state.get("fetched"),
            "active_run_id": state.get("active_run_id"),
            "cancel_requested": state.get("cancel_requested", False),
        },
        "stations": {
            "total": stations_total,
            "active": stations_active,
            "by_health_status": by_health,
        },
        "chunk_progress": chunk_progress,
        "recent_runs": runs,
        "recent_run_count": len(runs),
    }


@router.post("/health-check/{station_id}",
                            description=(
                                "Force re-probe a single station's stream URL.  Returns "
                                "the new health status."))
async def admin_health_check(station_id: str, request: Request,
                                                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    s = await db.imported_radio_stations.find_one({"id": station_id})
    if not s:
        raise HTTPException(404, {"code": "station_not_found"})
    async with httpx.AsyncClient() as client:
        status = await health_check_station(
            client, s.get("url_resolved") or s.get("url"))
    await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"stream_health_status": status,
                          "last_health_check_at": datetime.utcnow()}})
    return {"ok": True, "station_id": station_id, "status": status}
