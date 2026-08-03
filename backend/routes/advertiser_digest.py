"""Weekly-digest admin + advertiser opt-out routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user
from services import advertiser_digest_service as _svc

router = APIRouter(tags=["advertiser-digest"])
logger = logging.getLogger("bigfm.digest.routes")


class DigestPrefsBody(BaseModel):
    email_weekly_digest: bool


def _require_admin(user: dict) -> None:
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "admin_required"})


@router.post("/api/admin/advertiser/{advertiser_id}/send-digest-now",
                          description="Admin: fire this advertiser's weekly digest "
                                                    "immediately (bypasses schedule + opt-out).")
async def send_now(advertiser_id: str, request: Request,
                                        force: bool = True,
                                        user: dict = Depends(current_user)):
    _require_admin(user)
    return await _svc.send_digest_for_advertiser(
        request.app.state.db, advertiser_id=advertiser_id, force=force)


@router.post("/api/admin/advertiser-digest/run-batch-now",
                          description="Admin: fire the weekly batch immediately.")
async def batch_now(request: Request,
                                        user: dict = Depends(current_user)):
    _require_admin(user)
    return await _svc.run_weekly_batch(request.app.state.db)


@router.get("/api/advertiser/{advertiser_id}/digest/preferences")
async def get_prefs(advertiser_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    from routes.ad12_notifications import _assert_advertiser_owner
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    adv = await db.advertisers_v2.find_one(
        {"advertiser_id": advertiser_id},
        {"email_weekly_digest": 1})
    # Default: ON when the field is absent.
    v = (adv or {}).get("email_weekly_digest")
    return {"email_weekly_digest": True if v is None else bool(v)}


@router.patch("/api/advertiser/{advertiser_id}/digest/preferences")
async def set_prefs(advertiser_id: str, body: DigestPrefsBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    from routes.ad12_notifications import _assert_advertiser_owner
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id},
        {"$set": {"email_weekly_digest": bool(body.email_weekly_digest)}})
    return {"ok": True,
                  "email_weekly_digest": bool(body.email_weekly_digest)}


@router.get("/api/advertiser/{advertiser_id}/digest/preview",
                        description="Advertiser: preview the current week's digest.")
async def preview(advertiser_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    from routes.ad12_notifications import _assert_advertiser_owner
    db = request.app.state.db
    await _assert_advertiser_owner(db, advertiser_id, user)
    payload = await _svc.build_digest_payload(
        db, advertiser_id=advertiser_id, days=7)
    return payload


__all__ = ["router"]
