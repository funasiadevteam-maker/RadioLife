"""Phase F-1 — Listener-facing points endpoints.

All routes require auth (current_user).  See /api/admin/points/* in
`routes/admin_points.py` for the admin surface.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from services.points_service import PointsService

router = APIRouter(prefix="/api/me/points", tags=["points"])
log = logging.getLogger("bigfm.points.routes")


# ─── /api/me/points (summary) ──────────────────────────────────────
@router.get("")
async def get_points_summary(request: Request):
    from auth import current_user
    user = await current_user(request)
    db = request.app.state.db
    svc = PointsService(db)
    uid = user["user_id"]

    balance = await svc.get_balance(uid)
    today_b = await svc.get_breakdown(uid, period="today")
    week_b   = await svc.get_breakdown(uid, period="week")
    today_earned = sum(int(i["total"]) for i in (today_b["items"] or []))
    week_earned  = sum(int(i["total"]) for i in (week_b["items"] or []))
    # Top 5 sources lifetime.
    all_b = await svc.get_breakdown(uid, period="all")
    top_sources = (all_b["items"] or [])[:5]
    # Last 10 entries.
    hist = await svc.get_history(uid, limit=10)
    return {
        "balance": balance,
        "today_earned": today_earned,
        "this_week_earned": week_earned,
        "top_sources": top_sources,
        "recent": hist["items"],
    }


# ─── /api/me/points/history (paginated) ────────────────────────────
@router.get("/history")
async def get_points_history(request: Request,
                                                          limit: int = Query(50, ge=1, le=200),
                                                          cursor: Optional[str] = Query(None),
                                                          source: Optional[str] = Query(None)):
    from auth import current_user
    user = await current_user(request)
    db = request.app.state.db
    out = await PointsService(db).get_history(
        user["user_id"], limit=limit, cursor=cursor, source=source)
    return out


# ─── /api/me/points/breakdown (group-by source) ────────────────────
@router.get("/breakdown")
async def get_points_breakdown(request: Request,
                                                              period: str = Query("today")):
    if period not in ("today", "week", "month", "all"):
        raise HTTPException(400, {"code": "bad_period",
                                                          "allowed": ["today", "week", "month", "all"]})
    from auth import current_user
    user = await current_user(request)
    db = request.app.state.db
    return await PointsService(db).get_breakdown(
        user["user_id"], period=period)
