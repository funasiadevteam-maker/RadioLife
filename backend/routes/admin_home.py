"""Phase T — Admin Home dashboard routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import require_admin
from services import admin_home_service as svc

router = APIRouter(tags=["phase-t-admin-home"])


class PinBody(BaseModel):
    route: str
    label: Optional[str] = None


@router.get("/api/admin/home/summary")
async def home_summary(request: Request,
                        force: bool = Query(False),
                        user: dict = Depends(require_admin)):
    return await svc.home_summary(request.app.state.db,
                                    app_state=request.app.state,
                                    force_refresh=force)


@router.get("/api/admin/search")
async def admin_search(q: str = Query(..., min_length=1),
                        limit: int = Query(20, ge=1, le=100),
                        request: Request = None,
                        user: dict = Depends(require_admin)):
    return await svc.global_search(request.app.state.db, q, limit=limit)


@router.get("/api/admin/nav/pins")
async def get_pins(request: Request,
                    user: dict = Depends(require_admin)):
    rows = await svc.list_pins(request.app.state.db, user["user_id"])
    return {"items": rows, "total": len(rows)}


@router.post("/api/admin/nav/pin")
async def add_pin(body: PinBody, request: Request,
                   user: dict = Depends(require_admin)):
    try:
        return await svc.add_pin(request.app.state.db,
                                    user_id=user["user_id"],
                                    route=body.route, label=body.label)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.delete("/api/admin/nav/pin/{route_encoded:path}")
async def remove_pin(route_encoded: str, request: Request,
                       user: dict = Depends(require_admin)):
    route = route_encoded if route_encoded.startswith("/") \
                          else "/" + route_encoded
    return await svc.remove_pin(request.app.state.db,
                                    user_id=user["user_id"], route=route)


__all__ = ["router"]
