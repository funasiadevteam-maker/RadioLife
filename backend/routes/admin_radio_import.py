"""Phase 42-A — Radio Browser import admin endpoints.

Admin-only diagnostics + manual triggers for the live-radio import
pipeline.  Mirrors the predict_win_admin_sweeper pattern.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

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



# ─────────────── Language-policy restore controls ───────────────
# Stations hidden by the Hindi/English/Indian/news/US-UAE-UK language
# policy carry `lang_hidden: True`. These admin endpoints let an admin
# see what's hidden and re-enable a single station or a whole
# language / country group.

@router.get("/hidden-summary",
            description="Counts of stations hidden by the language policy, "
                        "broken down by country and language.")
async def hidden_summary(request: Request, _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    coll = db.imported_radio_stations
    total_hidden = await coll.count_documents({"lang_hidden": True})
    total_active = await coll.count_documents({"active": True})

    async def _top(field: str, limit: int = 40):
        cur = coll.aggregate([
            {"$match": {"lang_hidden": True}},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": limit},
        ])
        return [{"value": r["_id"], "count": r["count"]}
                async for r in cur if r["_id"]]

    return {
        "total_hidden": total_hidden,
        "total_active": total_active,
        "by_country": await _top("country_code"),
        "by_language": await _top("language"),
    }


@router.get("/hidden-stations",
            description="Paginated list of stations hidden by the language policy.")
async def hidden_stations(request: Request, _admin: dict = Depends(require_admin),
                          q: Optional[str] = None,
                          country: Optional[str] = None,
                          language: Optional[str] = None,
                          page: int = 1, limit: int = 30):
    db = request.app.state.db
    coll = db.imported_radio_stations
    query: dict = {"lang_hidden": True}
    if country:
        query["country_code"] = country.upper()
    if language:
        query["language"] = language.lower()
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    total = await coll.count_documents(query)
    skip = max(0, (page - 1)) * limit
    items = []
    cur = coll.find(query, {"id": 1, "name": 1, "country_code": 1,
                            "language": 1, "favicon": 1}).sort(
        [("name", 1)]).skip(skip).limit(limit)
    async for s in cur:
        items.append({"id": s.get("id"), "name": s.get("name"),
                      "country_code": s.get("country_code"),
                      "language": s.get("language"), "favicon": s.get("favicon")})
    return {"items": items, "total": total, "page": page, "limit": limit}


class RestoreBody(BaseModel):
    scope: str                       # "station" | "country" | "language" | "all"
    value: Optional[str] = None


@router.post("/restore",
             description="Re-enable stations hidden by the language policy. "
                         "scope=station|country|language|all.")
async def restore_hidden(body: RestoreBody, request: Request,
                         _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    coll = db.imported_radio_stations
    scope = (body.scope or "").strip().lower()
    query: dict = {"lang_hidden": True}
    if scope == "station":
        if not body.value:
            raise HTTPException(400, {"code": "value_required"})
        query["id"] = body.value
    elif scope == "country":
        if not body.value:
            raise HTTPException(400, {"code": "value_required"})
        query["country_code"] = body.value.upper()
    elif scope == "language":
        if not body.value:
            raise HTTPException(400, {"code": "value_required"})
        query["language"] = body.value.lower()
    elif scope == "all":
        pass
    else:
        raise HTTPException(400, {"code": "invalid_scope"})
    res = await coll.update_many(
        query, {"$set": {"active": True, "updated_at": datetime.utcnow()},
                "$unset": {"lang_hidden": ""}})
    return {"ok": True, "restored": res.modified_count, "scope": scope,
            "value": body.value}


class SetActiveBody(BaseModel):
    active: bool


@router.post("/station/{station_id}/set-active",
             description="Toggle a single imported station on/off. Turning it "
                         "off marks it lang_hidden so it stays reversible.")
async def set_station_active(station_id: str, body: SetActiveBody,
                             request: Request,
                             _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    coll = db.imported_radio_stations
    s = await coll.find_one({"id": station_id})
    if not s:
        raise HTTPException(404, {"code": "station_not_found"})
    if body.active:
        update = {"$set": {"active": True, "updated_at": datetime.utcnow()},
                  "$unset": {"lang_hidden": ""}}
    else:
        update = {"$set": {"active": False, "lang_hidden": True,
                           "updated_at": datetime.utcnow()}}
    await coll.update_one({"id": station_id}, update)
    return {"ok": True, "station_id": station_id, "active": body.active}
