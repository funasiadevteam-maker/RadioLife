"""Phase AD.1 — Admin approval router for the new advertiser stack.

Mounted at /api/admin/ad1.  Coexists with the legacy Phase-18a admin
queue at /api/admin/advertiser."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_admin
from services.ad1_advertiser_service import (
    approve_advertiser, approve_campaign, list_admin_advertisers,
    list_admin_campaigns, reject_advertiser, reject_campaign,
)

logger = logging.getLogger("bigfm.ad1.admin")
router = APIRouter(prefix="/api/admin/ad1", tags=["ad1-admin"])


class RejectBody(BaseModel):
    reason: str


# ─── Advertiser approval queue ─────────────────────────────
@router.get("/advertisers")
async def admin_list_advertisers(request: Request,
                                                                  status: Optional[str] = None,
                                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    items = await list_admin_advertisers(db, status=status)
    return {"items": items, "count": len(items)}


@router.post("/advertisers/{advertiser_id}/approve")
async def admin_approve_advertiser(advertiser_id: str, request: Request,
                                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await approve_advertiser(
            db, advertiser_id=advertiser_id, admin_user_id=admin["user_id"])
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})


@router.post("/advertisers/{advertiser_id}/reject")
async def admin_reject_advertiser(advertiser_id: str, body: RejectBody,
                                                                              request: Request,
                                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await reject_advertiser(
            db, advertiser_id=advertiser_id, admin_user_id=admin["user_id"],
            reason=body.reason)
    except LookupError:
        raise HTTPException(404, {"code": "advertiser_not_found"})


# ─── Campaign approval queue ────────────────────────────
@router.get("/ad-campaigns")
async def admin_list_campaigns(request: Request,
                                                              status: Optional[str] = None,
                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    items = await list_admin_campaigns(db, status=status)
    return {"items": items, "count": len(items)}


@router.post("/ad-campaigns/{campaign_id}/approve")
async def admin_approve_campaign(campaign_id: str, request: Request,
                                                                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await approve_campaign(
            db, campaign_id=campaign_id, admin_user_id=admin["user_id"])
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})


@router.post("/ad-campaigns/{campaign_id}/reject")
async def admin_reject_campaign(campaign_id: str, body: RejectBody,
                                                                        request: Request,
                                                                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await reject_campaign(
            db, campaign_id=campaign_id, admin_user_id=admin["user_id"],
            reason=body.reason)
    except LookupError:
        raise HTTPException(404, {"code": "campaign_not_found"})
