"""Phase O — Flagship Sponsor CTA (upsell funnel) routes."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import current_user, require_admin
from services import flagship_upsell_service as svc

log = logging.getLogger("bigfm.m8_upsell_routes")
router = APIRouter(tags=["m8-flagship-upsell"])


async def _assert_ownership(request: Request, user: dict,
                            business_id: str) -> None:
    if user.get("is_admin"):
        return
    db = request.app.state.db
    row = await db.advertisers.find_one(
        {"advertiser_id": business_id,
         "$or": [{"owner_user_id": user["user_id"]},
                 {"created_by_user_id": user["user_id"]}]})
    if row:
        return
    v2 = await db.advertisers_v2.find_one(
        {"$or": [{"advertiser_id": business_id},
                 {"business_id": business_id}],
         "owner_user_id": user["user_id"]})
    if v2:
        return
    raise HTTPException(403, {"code": "not_authorized_for_advertiser"})


def _bad(e: Exception) -> HTTPException:
    return HTTPException(
        400, {"code": str(e).split(":", 1)[0] or "bad_request",
              "detail": str(e)})


# ── Bodies ─────────────────────────────────────────────────────
class EventBody(BaseModel):
    event_type: str          # seen|clicked|dismissed|dismissed_permanently|converted
    context:    Optional[Dict[str, Any]] = None


# ── Advertiser ────────────────────────────────────────────────
@router.get("/api/advertiser/{business_id}/upsell/flagship-sponsor")
async def get_upsell(business_id: str, request: Request,
                     refresh: bool = Query(False),
                     user: dict = Depends(current_user)):
    await _assert_ownership(request, user, business_id)
    return await svc.check_eligibility(
        request.app.state.db, advertiser_id=business_id,
        force_refresh=refresh)


@router.post(
    "/api/advertiser/{business_id}/upsell/flagship-sponsor/event")
async def post_upsell_event(business_id: str, body: EventBody,
                            request: Request,
                            user: dict = Depends(current_user)):
    await _assert_ownership(request, user, business_id)
    try:
        return await svc.record_event(
            request.app.state.db,
            advertiser_id=business_id,
            event_type=body.event_type,
            context=body.context or {})
    except ValueError as e:
        raise _bad(e)


# ── Admin ──────────────────────────────────────────────────────
@router.get("/api/admin/advertiser-upsell-events")
async def admin_events(request: Request,
                       advertiser_id: Optional[str] = None,
                       event_type: Optional[str] = None,
                       from_: Optional[str] = Query(None, alias="from"),
                       to:    Optional[str] = None,
                       limit: int = Query(200, ge=1, le=1000),
                       user: dict = Depends(require_admin)):
    from_ts = None
    to_ts   = None
    try:
        if from_: from_ts = datetime.fromisoformat(
                                from_.replace("Z", "+00:00"))
        if to:    to_ts   = datetime.fromisoformat(
                                to.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400,
            {"code": "invalid_time_range",
             "detail": "from/to must be ISO-8601"})
    rows = await svc.admin_list_events(
        request.app.state.db,
        advertiser_id=advertiser_id,
        event_type=event_type,
        from_ts=from_ts, to_ts=to_ts, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.get("/api/admin/advertiser-upsell-funnel")
async def admin_funnel(request: Request,
                       user: dict = Depends(require_admin)):
    return await svc.admin_funnel(request.app.state.db)


__all__ = ["router"]
