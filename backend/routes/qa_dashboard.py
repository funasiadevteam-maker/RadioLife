"""Phase Q — QA Dashboard routes.  Admin-only.

- GET  /api/admin/qa/summary
- POST /api/admin/qa/refresh
- GET  /api/admin/qa/alert/{alert_type}/details?limit=50
- POST /api/admin/qa/alerts/{alert_type}/dismiss
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import require_admin
from services import qa_dashboard_service as svc

log = logging.getLogger("bigfm.qa_dashboard_routes")
router = APIRouter(tags=["phase-q-qa-dashboard"])


class DismissBody(BaseModel):
    hours: Optional[int] = 24


@router.get("/api/admin/qa/summary")
async def qa_summary(request: Request,
                     force: bool = Query(False),
                     user: dict = Depends(require_admin)):
    return await svc.build_summary(
        request.app.state.db, app_state=request.app.state,
        force_refresh=force)


@router.post("/api/admin/qa/refresh")
async def qa_refresh(request: Request,
                     user: dict = Depends(require_admin)):
    svc.clear_cache()
    return await svc.build_summary(
        request.app.state.db, app_state=request.app.state,
        force_refresh=True)


@router.get("/api/admin/qa/alert/{alert_type}/details")
async def qa_alert_details(alert_type: str, request: Request,
                           limit: int = Query(50, ge=1, le=500),
                           user: dict = Depends(require_admin)):
    try:
        rows = await svc.alert_details(
            request.app.state.db, alert_type=alert_type, limit=limit)
    except ValueError as e:
        raise HTTPException(400,
            {"code": str(e).split(":", 1)[0], "detail": str(e)})
    return {"alert_type": alert_type, "items": rows, "total": len(rows)}


@router.post("/api/admin/qa/alerts/{alert_type}/dismiss")
async def qa_alert_dismiss(alert_type: str, body: DismissBody,
                           request: Request,
                           user: dict = Depends(require_admin)):
    hours = body.hours if (body.hours and body.hours > 0) else 24
    return await svc.dismiss_alert(
        request.app.state.db, alert_type=alert_type,
        user_id=user["user_id"], hours=hours)


__all__ = ["router"]
