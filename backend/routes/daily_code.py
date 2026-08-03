"""Phase AD.8 — Daily Code Claim HTTP routes."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services import daily_code_service as _svc

router = APIRouter(tags=["ad8-daily-code"])
logger = logging.getLogger("bigfm.ad8.routes")


class ClaimBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class AdminCreateBody(BaseModel):
    date_effective:                          str
    points_reward:                            int = 50
    sponsored_by_advertiser_id:  Optional[str] = None
    region_targeting:                      Optional[List[str]] = None


class AdminUpdateBody(BaseModel):
    points_reward:                            Optional[int] = None
    sponsored_by_advertiser_id:  Optional[str] = None
    region_targeting:                      Optional[List[str]] = None


def _require_admin(user: Optional[dict]) -> None:
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "admin_required"})


@router.get("/api/daily-code/current",
                        description="Get today's code + user's claim status + preview streak.")
async def get_current(request: Request,
                                              user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    return await _svc.current_code_view(
        db, user_id=(user or {}).get("user_id"))


@router.post("/api/daily-code/claim",
                          description="Claim today's code — awards points × streak multiplier.")
async def claim(body: ClaimBody, request: Request,
                              user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    db = request.app.state.db
    try:
        return await _svc.claim(
            db, user_id=user["user_id"], code=body.code)
    except ValueError as e:
        code = str(e)
        # already_claimed → 409 semantically clearest.
        if code == "already_claimed":
            raise HTTPException(409, {"code": code})
        raise HTTPException(400, {"code": code})


@router.get("/api/user/daily-code/history",
                        description="User's past claims + lifetime + best streak.")
async def history(request: Request,
                                  limit: int = Query(30, ge=1, le=100),
                                  user: dict = Depends(current_user)):
    if not user:
        raise HTTPException(401, {"code": "auth_required"})
    return await _svc.user_history(
        request.app.state.db, user_id=user["user_id"], limit=limit)


@router.post("/api/admin/daily-codes",
                          description="Admin seeds a future code.  Rejects duplicate date.")
async def admin_create(body: AdminCreateBody, request: Request,
                                                  user: dict = Depends(current_user)):
    _require_admin(user)
    try:
        return await _svc.admin_create_code(
            request.app.state.db,
            date_key=body.date_effective,
            points_reward=body.points_reward,
            sponsored_by_advertiser_id=body.sponsored_by_advertiser_id,
            region_targeting=body.region_targeting)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.patch("/api/admin/daily-codes/{daily_code_id}",
                            description="Edit points_reward / sponsor before the window opens.")
async def admin_update(daily_code_id: str, body: AdminUpdateBody,
                                                  request: Request,
                                                  user: dict = Depends(current_user)):
    _require_admin(user)
    try:
        return await _svc.admin_update_code(
            request.app.state.db,
            daily_code_id=daily_code_id,
            patch=body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


__all__ = ["router"]
