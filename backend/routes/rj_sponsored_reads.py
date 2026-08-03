"""Phase I — M1 Sponsored AI-RJ Reads routes.

Three surfaces:
    * `/api/advertiser/{business_id}/rj-sponsored-reads/*` — creation
      + moderation submit + Stripe prepay + cancel.
    * `/api/admin/rj-sponsored-reads/*` — moderation queue for
      over-threshold reads.
    * `/api/rj/sponsored-reads/*` — listener pick + play-impression.
      The FE `GlobalAudio` player calls these between songs.

All routes are additive.  The `/api/ai-rj/segment/generate` endpoint
from Phase H'.3 is untouched — the player just calls the new
`/api/rj/sponsored-reads/next-sponsored` BEFORE the RJ segment fetch
and layers the two audios one after the other.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import rj_sponsored_read_service as svc

log = logging.getLogger("bigfm.m1_rjsr_routes")

router = APIRouter(tags=["m1-rj-sponsored-reads"])


# ── Helpers ───────────────────────────────────────────────────────
async def _assert_business_ownership(request: Request, user: dict,
                                                                          business_id: str) -> None:
    """Advertiser owner OR admin required."""
    if user.get("is_admin"):
        return
    db = request.app.state.db
    # First check advertiser owner_user_id, then Phase 42 v2 model.
    row = await db.advertisers.find_one(
        {"advertiser_id": business_id,
          "$or": [{"owner_user_id":  user["user_id"]},
                          {"created_by_user_id": user["user_id"]}]})
    if row:
        return
    v2 = await db.advertisers_v2.find_one(
        {"$or": [{"advertiser_id": business_id},
                          {"business_id":    business_id}],
          "owner_user_id": user["user_id"]})
    if v2:
        return
    raise HTTPException(403, {"code": "not_authorized_for_advertiser"})


def _bad_request(e: Exception) -> HTTPException:
    return HTTPException(400, {"code": str(e).split(":", 1)[0] or "bad_request",
                                                                "detail": str(e)})


# ── Request bodies ────────────────────────────────────────────────
class CreateReadBody(BaseModel):
    persona_id:                str
    station_ids:              Optional[List[str]] = None
    any_station:              bool = False
    script_body:              str = ""          # "auto" for LLM-drafted
    disclosure_prefix:  str = "Paid sponsorship"
    plays_target:            int = Field(ge=1)
    cost_per_play_cents: int = Field(ge=1)
    start_at:                    Optional[str] = None
    end_at:                        Optional[str] = None
    # Auto-draft inputs (used only when script_body == "auto"):
    product_name:            Optional[str] = None
    key_message:              Optional[str] = None
    cta:                            Optional[str] = None


class SubmitReadBody(BaseModel):
    final_script: str


class CancelReadBody(BaseModel):
    reason: Optional[str] = "advertiser_cancelled"


class AdminDecisionBody(BaseModel):
    admin_notes: Optional[str] = None


class RecordPlayBody(BaseModel):
    station_id: str


# ─────────────────────────────────────────────────────────────────
#  ADVERTISER
# ─────────────────────────────────────────────────────────────────
@router.post("/api/advertiser/{business_id}/rj-sponsored-reads")
async def create_rjsr(business_id: str,
                                            body: CreateReadBody,
                                            request: Request,
                                            user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        row = await svc.create_sponsored_read(
            request.app.state.db,
            advertiser_business_id=business_id,
            body=body.model_dump(),
            user_id=user["user_id"])
    except ValueError as e:
        raise _bad_request(e)
    return row


@router.post("/api/advertiser/{business_id}"
                          "/rj-sponsored-reads/{sponsored_read_id}/submit")
async def submit_rjsr(business_id: str, sponsored_read_id: str,
                                            body: SubmitReadBody, request: Request,
                                            user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        row = await svc.submit_sponsored_read(
            request.app.state.db,
            sponsored_read_id=sponsored_read_id,
            advertiser_business_id=business_id,
            final_script=body.final_script)
    except ValueError as e:
        raise _bad_request(e)
    return row


@router.post("/api/advertiser/{business_id}"
                          "/rj-sponsored-reads/{sponsored_read_id}/confirm-payment")
async def confirm_rjsr(business_id: str, sponsored_read_id: str,
                                              request: Request,
                                              user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.confirm_payment(
            request.app.state.db,
            sponsored_read_id=sponsored_read_id,
            advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.get("/api/advertiser/{business_id}/rj-sponsored-reads")
async def list_rjsr_for_advertiser(business_id: str,
                                                                        request: Request,
                                                                        status: Optional[str] = None,
                                                                        user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    items = await svc.list_reads(request.app.state.db,
                                                              advertiser_business_id=business_id,
                                                              status=status)
    return {"items": items, "count": len(items)}


@router.get("/api/advertiser/{business_id}"
                        "/rj-sponsored-reads/{sponsored_read_id}")
async def get_rjsr(business_id: str, sponsored_read_id: str,
                                    request: Request,
                                    user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    row = await svc.get_read(request.app.state.db,
                                                    sponsored_read_id=sponsored_read_id,
                                                    advertiser_business_id=business_id)
    if not row:
        raise HTTPException(404, {"code": "sponsored_read_not_found"})
    return row


@router.post("/api/advertiser/{business_id}"
                          "/rj-sponsored-reads/{sponsored_read_id}/cancel")
async def cancel_rjsr(business_id: str, sponsored_read_id: str,
                                            body: CancelReadBody, request: Request,
                                            user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.cancel_read(
            request.app.state.db,
            sponsored_read_id=sponsored_read_id,
            advertiser_business_id=business_id,
            reason=(body.reason or "advertiser_cancelled"))
    except ValueError as e:
        raise _bad_request(e)


# ─────────────────────────────────────────────────────────────────
#  ADMIN
# ─────────────────────────────────────────────────────────────────
@router.get("/api/admin/rj-sponsored-reads")
async def admin_list_rjsr(request: Request,
                                                    status: Optional[str] = None,
                                                    _admin: dict = Depends(require_admin)):
    items = await svc.admin_list(request.app.state.db, status=status)
    return {"items": items, "count": len(items)}


@router.get("/api/admin/rj-sponsored-reads/{sponsored_read_id}")
async def admin_get_rjsr(sponsored_read_id: str,
                                                  request: Request,
                                                  _admin: dict = Depends(require_admin)):
    row = await svc.get_read(request.app.state.db,
                                                    sponsored_read_id=sponsored_read_id)
    if not row:
        raise HTTPException(404, {"code": "sponsored_read_not_found"})
    return row


@router.post("/api/admin/rj-sponsored-reads/{sponsored_read_id}/approve")
async def admin_approve_rjsr(sponsored_read_id: str,
                                                            body: AdminDecisionBody,
                                                            request: Request,
                                                            admin: dict = Depends(require_admin)):
    try:
        return await svc.admin_approve(
            request.app.state.db,
            sponsored_read_id=sponsored_read_id,
            admin_user_id=admin["user_id"],
            admin_notes=body.admin_notes)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/admin/rj-sponsored-reads/{sponsored_read_id}/reject")
async def admin_reject_rjsr(sponsored_read_id: str,
                                                          body: AdminDecisionBody,
                                                          request: Request,
                                                          admin: dict = Depends(require_admin)):
    try:
        return await svc.admin_reject(
            request.app.state.db,
            sponsored_read_id=sponsored_read_id,
            admin_user_id=admin["user_id"],
            admin_notes=(body.admin_notes or ""))
    except ValueError as e:
        raise _bad_request(e)


# ─────────────────────────────────────────────────────────────────
#  LISTENER  (called by GlobalAudio.jsx between songs)
# ─────────────────────────────────────────────────────────────────
@router.get("/api/rj/sponsored-reads/next-sponsored")
async def next_sponsored(request: Request,
                                                station_id: str = Query(..., min_length=1),
                                                user: dict = Depends(current_user)):
    """Returns 0 or 1 sponsored read for this station + this listener.
    Response shape:
        `{"sponsored_read": {sponsored_read_id, audio_url, ...} | null}`
    """
    row = await svc.select_next_sponsored(
        request.app.state.db,
        station_id=station_id,
        user_id=user.get("user_id"))
    return {"sponsored_read": row}


@router.post("/api/rj/sponsored-reads/{sponsored_read_id}/played")
async def record_played(sponsored_read_id: str,
                                                body: RecordPlayBody,
                                                request: Request,
                                                user: dict = Depends(current_user)):
    """Impression record.  Atomically decrements budget + increments
    plays_delivered.  Deduped per (read, user, 1-hour bucket)."""
    try:
        return await svc.record_play(
            request.app.state.db,
            sponsored_read_id=sponsored_read_id,
            station_id=body.station_id,
            user_id=user.get("user_id"))
    except ValueError as e:
        raise _bad_request(e)


__all__ = ["router"]
