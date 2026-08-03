"""Phase PDX.1 — Admin + public routes for the Predexon auto-curator.

Endpoints:
    GET   /api/admin/pdx-curator/status        — enabled + last/next run + counts
    POST  /api/admin/pdx-curator/run-now       — force one tick, returns summary
    PATCH /api/admin/pdx-curator/settings      — enabled / interval_min / target_min|max
    PATCH /api/admin/predict-win/campaigns/{id}/points  — override points [10, 100]
    GET   /api/predict-win/categories          — PUBLIC — chip data for frontend

All admin routes require `require_admin`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_admin
from config.pdx_categories import (
    POINTS_MAX, POINTS_MIN, public_category_payload,
)
from services import pdx_curator_service as curator

log = logging.getLogger("bigfm.pdx_curator.routes")

admin_router = APIRouter(prefix="/api/admin/pdx-curator",
                                                  tags=["pdx-curator-admin"])
admin_pw_points_router = APIRouter(
    prefix="/api/admin/predict-win",
    tags=["predict-win-admin-points"])
public_router = APIRouter(prefix="/api/predict-win",
                                                    tags=["predict-win-public-categories"])


# ─── /admin/pdx-curator/status ────────────────────────────────────
@admin_router.get("/status",
                                    description="Curator health + last-run + active-auto counts.")
async def curator_status(request: Request,
                                                  _a: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = request.app.state.db
    settings = await curator.get_settings(db)
    active_total = await db.predict_win_campaigns.count_documents({
        "creator_type": "admin_auto",
        "status": {"$in": ["scheduled", "live"]},
        "approval_status": "approved",
        "lock_time": {"$gt": datetime.now(timezone.utc)},
        "deleted_at": None,
    })
    # Per-category counts.
    from config.pdx_categories import PDX_CATEGORIES
    per_cat: Dict[str, int] = {}
    for spec in PDX_CATEGORIES:
        per_cat[spec["slug"]] = await db.predict_win_campaigns.count_documents({
            "creator_type": "admin_auto",
            "category_slug": spec["slug"],
            "status": {"$in": ["scheduled", "live"]},
            "approval_status": "approved",
            "lock_time": {"$gt": datetime.now(timezone.utc)},
            "deleted_at": None,
        })
    last_run_at = settings.get("last_run_at")
    next_run_at: Optional[str] = None
    if isinstance(last_run_at, datetime) and settings.get("interval_min"):
        nxt = last_run_at + timedelta(minutes=int(settings["interval_min"]))
        next_run_at = nxt.isoformat()
    return {
        "enabled":         bool(settings.get("enabled", True)),
        "interval_min": int(settings.get("interval_min", 60)),
        "target_min":     int(settings.get("target_min", 20)),
        "target_max":     int(settings.get("target_max", 40)),
        "last_run_at":   (last_run_at.isoformat()
                                              if isinstance(last_run_at, datetime) else None),
        "next_run_at":  next_run_at,
        "active_total":  active_total,
        "active_by_category": per_cat,
        "last_run_summary":     settings.get("last_run_summary"),
    }


# ─── /admin/pdx-curator/run-now ───────────────────────────────────
@admin_router.post("/run-now",
                                      description="Force one curator tick synchronously (blocks ~40s).")
async def curator_run_now(request: Request,
                                                    _a: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = request.app.state.db
    # A single forced-run tick — shorten sleep_between to be responsive
    # for the admin (still >=2s to stay under Predexon's rate limit).
    return await curator.run_curator_tick(db, sleep_between=3.0,
                                                                            run_retire=False)


# ─── /admin/pdx-curator/settings ──────────────────────────────────
class CuratorSettingsPatch(BaseModel):
    enabled:            Optional[bool] = None
    interval_min:  Optional[int] = Field(None, ge=5, le=1440)
    target_min:      Optional[int] = Field(None, ge=1, le=60)
    target_max:      Optional[int] = Field(None, ge=1, le=200)


@admin_router.patch("/settings",
                                        description="Update curator flags without a redeploy.")
async def curator_settings_patch(request: Request,
                                                                        body: CuratorSettingsPatch,
                                                                        _a: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = request.app.state.db
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, {"code": "no_fields_to_update"})
    if ("target_max" in patch and "target_min" in patch
            and patch["target_max"] < patch["target_min"]):
        raise HTTPException(400, {"code": "target_max_lt_target_min"})
    updated = await curator.update_settings(db, patch)
    return {"ok": True, "settings": {
        "enabled":         bool(updated.get("enabled", True)),
        "interval_min": int(updated.get("interval_min", 60)),
        "target_min":     int(updated.get("target_min", 20)),
        "target_max":     int(updated.get("target_max", 40)),
    }}


# ─── /admin/predict-win/campaigns/{id}/points ─────────────────────
class PointsPatch(BaseModel):
    points_reward: int = Field(..., ge=POINTS_MIN, le=POINTS_MAX)


@admin_pw_points_router.patch("/campaigns/{campaign_id}/points",
                                                              description="Admin override for an event's points reward "
                                                                                  "(bounded 10-100 per user directive).")
async def update_campaign_points(campaign_id: str,
                                                                  request: Request,
                                                                  body: PointsPatch,
                                                                  _a: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    res = await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id, "deleted_at": None},
        {"$set": {"points_reward": int(body.points_reward),
                          "updated_at": now}})
    if not res.matched_count:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return {"ok": True, "campaign_id": campaign_id,
                  "points_reward": int(body.points_reward)}


# ─── /predict-win/categories (public) ─────────────────────────────
@public_router.get("/categories",
                                      description="Public chip data — 4 category slugs + display names.")
async def list_public_categories() -> Dict[str, Any]:
    return {"items": public_category_payload(),
                  "count": len(public_category_payload())}


# ─── /admin/pdx-curator/active-events (list for the admin table) ──
@admin_router.get("/active-events",
                                    description="Currently active auto-imported campaigns with per-row detail.")
async def curator_active_events(request: Request,
                                                                category_slug: Optional[str] = None,
                                                                limit: int = 100,
                                                                _a: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = request.app.state.db
    q: Dict[str, Any] = {
        "creator_type": "admin_auto",
        "status": {"$in": ["scheduled", "live"]},
        "approval_status": "approved",
        "lock_time": {"$gt": datetime.now(timezone.utc)},
        "deleted_at": None,
    }
    if category_slug:
        q["category_slug"] = category_slug
    total = await db.predict_win_campaigns.count_documents(q)
    cur = (db.predict_win_campaigns
                  .find(q, {"campaign_id": 1, "title": 1,
                                      "category_slug": 1, "points_reward": 1,
                                      "start_time": 1, "lock_time": 1,
                                      "external_market_id": 1,
                                      "external_market_url": 1,
                                      "external_provider_snapshot.total_volume_usd": 1,
                                      "imported_at": 1, "status": 1})
                  .sort([("lock_time", 1)])
                  .limit(min(200, max(1, int(limit)))))
    items = []
    async for d in cur:
        vol = (((d.get("external_provider_snapshot") or {})
                        .get("total_volume_usd")) or None)
        items.append({
            "campaign_id":        d.get("campaign_id"),
            "title":                       d.get("title"),
            "category_slug":    d.get("category_slug"),
            "points_reward":   int(d.get("points_reward") or 25),
            "start_time":            (d.get("start_time").isoformat()
                                                          if isinstance(d.get("start_time"), datetime) else None),
            "lock_time":              (d.get("lock_time").isoformat()
                                                        if isinstance(d.get("lock_time"), datetime) else None),
            "external_market_id":     d.get("external_market_id"),
            "external_market_url":  d.get("external_market_url"),
            "total_volume_usd":         vol,
            "status":                                  d.get("status"),
        })
    return {"items": items, "total": total}


__all__ = ["admin_router", "admin_pw_points_router", "public_router"]
