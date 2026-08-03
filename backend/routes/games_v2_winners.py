"""Phase 23 Session 1.5 — winners + redemptions routes.

Mounted under the existing `/api/games_v2` prefix so callers do NOT have to
learn a new URL space.  Sibling to `routes/games_v2.py` (the main file) and
`routes/games_v2_phase8c.py` (lead forms + webhooks).

All endpoints are net-additive — none of the existing games_v2 endpoints
are modified.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import current_user, require_admin
from services.games_v2_winners_redemptions import (
    admin_void_winner,
    list_admin_redemptions,
    list_admin_winners,
    list_user_winners,
    record_winner,
    save_winner_to_wallet,
    validate_redemption,
)
from scripts.backfill_game_winners_from_sessions import (
    backfill as _backfill_winners,
)
from scripts.backfill_game_redemptions_from_audit_log import (
    backfill as _backfill_redemptions,
)


logger = logging.getLogger("bigfm.games_v2.winners_routes")

games_v2_winners_router = APIRouter(
    prefix="/api/games_v2",
    tags=["games_v2_winners_phase23"],
)


def _db(request: Request):
    return request.app.state.db


def _409(status_code_string: str, message: str | None = None):
    raise HTTPException(status_code=409,
        detail={"status": status_code_string,
                    "message": message or status_code_string})


# =====================================================================
# Listener-side winner flow
# =====================================================================
@games_v2_winners_router.post("/sessions/{session_id}/record_winner")
async def record_winner_endpoint(session_id: str,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    """Internal-ish — called by the existing post-win callback inside
    submit_session(), and also exposed for admin re-triggers / backfill.

    Idempotent on session_id."""
    db = _db(request)
    sess = await db.game_sessions.find_one({"session_id": session_id})
    if not sess:
        raise HTTPException(status_code=404,
            detail={"status": "session_not_found"})
    # Owner check (admin bypass)
    if sess["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403,
            detail={"status": "not_owner"})
    try:
        winner = await record_winner(db, session_id, source="endpoint")
    except ValueError as exc:
        code = str(exc)
        if code in ("inventory_exhausted", "max_per_user_reached"):
            _409(code)
        raise HTTPException(status_code=404, detail={"status": code})
    return {"winner_id": winner["winner_id"],
              "prize_snapshot": winner["prize_snapshot_json"],
              "status": winner["status"],
              "won_at": winner["won_at"]}


@games_v2_winners_router.post("/winners/{winner_id}/save_to_wallet")
async def save_to_wallet_endpoint(winner_id: str,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    db = _db(request)
    try:
        res = await save_winner_to_wallet(db, user, winner_id)
    except PermissionError:
        raise HTTPException(status_code=403,
            detail={"status": "not_owner"})
    except ValueError as exc:
        code = str(exc)
        if code in ("winner_voided",):
            _409(code)
        raise HTTPException(status_code=404, detail={"status": code})
    return res


@games_v2_winners_router.get("/winners")
async def list_my_winners(request: Request,
                                            status: Optional[str] = Query(None),
                                            limit: int = Query(25, ge=1, le=100),
                                            cursor: Optional[str] = Query(None),
                                            user: dict = Depends(current_user)):
    db = _db(request)
    return await list_user_winners(db, user["user_id"],
                                                          status=status, limit=limit, cursor=cursor)


# =====================================================================
# Business / staff redemption flow
# =====================================================================
class RedemptionValidateBody(BaseModel):
    redemption_code: str
    business_id: Optional[str] = None
    staff_user_id: Optional[str] = None
    staff_note: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lng: Optional[float] = None
    client_metadata: Optional[dict] = None


@games_v2_winners_router.post("/redemptions/validate")
async def redemptions_validate_endpoint(body: RedemptionValidateBody,
                                                                            request: Request,
                                                                            user: dict = Depends(current_user)):
    """Staff scan endpoint.  Caller MUST be either an admin or staff/owner
    of a business; we trust the body's business_id on this PoC pass — a
    follow-up phase ties this to formal staff role membership."""
    db = _db(request)
    # Staff identity defaults to caller if not supplied
    staff_user_id = body.staff_user_id or user["user_id"]
    try:
        res = await validate_redemption(
            db,
            redemption_code=body.redemption_code,
            business_id=body.business_id,
            staff_user_id=staff_user_id,
            staff_note=body.staff_note,
            geo_lat=body.geo_lat,
            geo_lng=body.geo_lng,
            client_metadata=body.client_metadata,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "not_found":
            raise HTTPException(status_code=404,
                detail={"status": "not_found"})
        if code == "winner_not_found":
            raise HTTPException(status_code=404,
                detail={"status": "winner_not_found"})
        # all other validation rejections are 409 conflict semantics
        _409(code)
    return res


# =====================================================================
# Admin endpoints
# =====================================================================
@games_v2_winners_router.get("/admin/winners")
async def admin_winners_list(request: Request,
                                                  game_campaign_id: Optional[str] = Query(None),
                                                  status: Optional[str] = Query(None),
                                                  limit: int = Query(50, ge=1, le=200),
                                                  cursor: Optional[str] = Query(None),
                                                  _u: dict = Depends(require_admin)):
    db = _db(request)
    return await list_admin_winners(db,
                                                          game_campaign_id=game_campaign_id,
                                                          status=status,
                                                          limit=limit,
                                                          cursor=cursor)


class WinnerVoidBody(BaseModel):
    voided_reason: str


@games_v2_winners_router.post("/admin/winners/{winner_id}/void")
async def admin_void_winner_endpoint(winner_id: str,
                                                                      body: WinnerVoidBody,
                                                                      request: Request,
                                                                      admin: dict = Depends(require_admin)):
    if not (body.voided_reason or "").strip():
        raise HTTPException(status_code=400,
            detail={"status": "voided_reason_required"})
    db = _db(request)
    try:
        winner = await admin_void_winner(db, winner_id,
                                                                admin_user_id=admin["user_id"],
                                                                voided_reason=body.voided_reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"status": str(exc)})
    return {"winner_id": winner["winner_id"],
              "status": winner["status"],
              "voided_reason": winner.get("voided_reason")}


@games_v2_winners_router.get("/admin/redemptions")
async def admin_redemptions_list(request: Request,
                                                          business_id: Optional[str] = Query(None),
                                                          status: Optional[str] = Query(None),
                                                          limit: int = Query(50, ge=1, le=200),
                                                          cursor: Optional[str] = Query(None),
                                                          _u: dict = Depends(require_admin)):
    db = _db(request)
    return await list_admin_redemptions(db,
                                                                business_id=business_id,
                                                                status=status,
                                                                limit=limit,
                                                                cursor=cursor)


# =====================================================================
# Admin backfill triggers (idempotent — safe to re-run)
# =====================================================================
@games_v2_winners_router.post("/admin/backfill/winners")
async def admin_backfill_winners(request: Request,
                                                          _u: dict = Depends(require_admin)):
    db = _db(request)
    summary = await _backfill_winners(db)
    return summary


@games_v2_winners_router.post("/admin/backfill/redemptions")
async def admin_backfill_redemptions(request: Request,
                                                                  _u: dict = Depends(require_admin)):
    db = _db(request)
    summary = await _backfill_redemptions(db)
    return summary
