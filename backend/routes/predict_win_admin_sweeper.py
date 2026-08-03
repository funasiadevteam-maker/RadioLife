"""Sub-Phase E4 — Predict & Win sweeper diagnostic endpoints (admin).

Surfaces:
    GET    /api/admin/predict-win/sweeper/status
    POST   /api/admin/predict-win/sweeper/run-once
    POST   /api/admin/predict-win/sweeper/pause
    POST   /api/admin/predict-win/sweeper/resume
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from auth import require_admin
from services.predict_win_sweeper import (
    DEFAULT_INTERVAL_SEC,
    NEEDS_MANUAL_ALERT_AFTER_HOURS,
    is_paused,
    run_one_cycle,
    set_paused,
)

router = APIRouter(prefix="/api/admin/predict-win/sweeper",
                                  tags=["predict-win-sweeper"])


def _iso(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return v.isoformat()
    return None


def _strip_mongo(d: dict) -> dict:
    out = {**d}
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@router.get("/status",
                          description=(
                              "Last 10 sweep cycles + current scheduler state + "
                              "next scheduled run estimate (5s clock skew is "
                              "fine — this is a diagnostic).  Admin auth."))
async def sweeper_status(request: Request,
                                              user: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.predict_win_sweep_logs.find().sort("started_at", -1).limit(10)
    cycles = [_strip_mongo(c) async for c in cur]
    paused = await is_paused(db)
    settings = await db.predict_win_settings.find_one({"_id": "sweeper"}) or {}
    last_started = None
    if cycles:
        last_started = cycles[0].get("started_at")
    return {
        "scheduler": {
            "enabled": (not paused),
            "paused": paused,
            "interval_sec": DEFAULT_INTERVAL_SEC,
            "needs_manual_alert_after_hours":
                NEEDS_MANUAL_ALERT_AFTER_HOURS,
            "last_cycle_started_at": last_started,
            "settings_updated_at": _iso(settings.get("updated_at")),
            "settings_updated_by": settings.get("updated_by"),
        },
        "recent_cycles": cycles,
        "recent_cycle_count": len(cycles),
    }


@router.post("/run-once",
                            description=(
                                "Force a single sweep cycle synchronously.  Returns "
                                "the full cycle log including any campaign IDs "
                                "transitioned + any admin alerts fired.  Useful for "
                                "testing the sweep without waiting for the next "
                                "scheduled tick."))
async def sweeper_run_once(request: Request,
                                                  user: dict = Depends(require_admin)):
    db = request.app.state.db
    result = await run_one_cycle(db, trigger="manual")
    return {"ok": True, "cycle": result}


class PauseIn(BaseModel):
    reason: Optional[str] = None


@router.post("/pause",
                            description=(
                                "Pause the scheduled sweeper loop.  Manual run-once "
                                "still works.  Idempotent."))
async def sweeper_pause(body: PauseIn, request: Request,
                                            user: dict = Depends(require_admin)):
    out = await set_paused(request.app.state.db,
                                              paused=True, by_user_id=user["user_id"])
    return {"ok": True, **out, "reason": body.reason}


@router.post("/resume",
                            description=(
                                "Resume the scheduled sweeper loop.  Idempotent."))
async def sweeper_resume(request: Request,
                                              user: dict = Depends(require_admin)):
    out = await set_paused(request.app.state.db,
                                              paused=False, by_user_id=user["user_id"])
    return {"ok": True, **out}
