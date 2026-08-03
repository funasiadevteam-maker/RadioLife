"""Phase K — M3 Wallet-Deal Marketplace routes."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import marketplace_service as svc

log = logging.getLogger("bigfm.m3_market_routes")

router = APIRouter(tags=["m3-marketplace"])


# ── Helpers ─────────────────────────────────────────────────────
async def _assert_business_ownership(request: Request, user: dict,
                                                                          business_id: str) -> None:
    if user.get("is_admin"):
        return
    db = request.app.state.db
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


# ── Bodies ──────────────────────────────────────────────────────
class SaveBody(BaseModel):
    user_email: Optional[str] = None


class ViewBody(BaseModel):
    region_code: Optional[str] = None


class ListingRef(BaseModel):
    source_type: str
    source_id:    str


class CreateSlotBody(BaseModel):
    listing_ref:                    ListingRef
    region_code:                    str
    slot_position:                int = Field(ge=1, le=3)
    cost_per_day_cents:      int = Field(ge=1)
    days_purchased:              int = Field(ge=1)
    start_at:                        Optional[str] = None
    end_at:                            Optional[str] = None


class CancelBody(BaseModel):
    reason: Optional[str] = "advertiser_cancelled"


class AdminDecisionBody(BaseModel):
    admin_notes: Optional[str] = None


# ────────────────────────────────────────────────────────────────
# PUBLIC — listener browse
# ────────────────────────────────────────────────────────────────
@router.get("/api/marketplace/listings")
async def list_listings(request: Request,
                                              region_code: Optional[str] = None,
                                              category:      Optional[str] = None,
                                              search:          Optional[str] = None,
                                              sort_by:        str = "featured",
                                              limit:            int = Query(30, ge=1, le=100),
                                              offset:          int = Query(0, ge=0)):
    out = await svc.list_listings(
        request.app.state.db,
        region_code=(region_code or "").lower() or None,
        category=category, search=search,
        sort_by=sort_by, limit=limit, offset=offset)
    return out


@router.get("/api/marketplace/listings/{listing_id}")
async def get_listing(listing_id: str, request: Request):
    row = await svc.get_listing(request.app.state.db, listing_id=listing_id)
    if not row:
        raise HTTPException(404, {"code": "listing_not_found"})
    return row


@router.post("/api/marketplace/listings/{listing_id}/view")
async def record_listing_view(listing_id: str, body: ViewBody, request: Request,
                                                            user: dict = Depends(current_user)):
    try:
        return await svc.record_view(
            request.app.state.db,
            listing_id=listing_id,
            user_id=user.get("user_id"),
            region_code=(body.region_code or "").lower() or None)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/marketplace/listings/{listing_id}/save")
async def save_marketplace_listing(listing_id: str, body: SaveBody,
                                                                        request: Request,
                                                                        user: dict = Depends(current_user)):
    try:
        return await svc.save_listing(
            request.app.state.db,
            listing_id=listing_id,
            user_id=user["user_id"],
            user_email=body.user_email or user.get("email"))
    except ValueError as e:
        raise _bad_request(e)


# ────────────────────────────────────────────────────────────────
# ADVERTISER — featured slots
# ────────────────────────────────────────────────────────────────
@router.post("/api/advertiser/{business_id}/marketplace-featured-slots")
async def create_marketplace_slot(business_id: str, body: CreateSlotBody,
                                                                    request: Request,
                                                                    user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.create_slot(
            request.app.state.db,
            advertiser_business_id=business_id,
            body=body.model_dump(), user_id=user["user_id"])
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/advertiser/{business_id}/marketplace-featured-slots/"
                          "{slot_id}/confirm-payment")
async def confirm_marketplace_slot(business_id: str, slot_id: str,
                                                                      request: Request,
                                                                      user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.confirm_payment(
            request.app.state.db,
            slot_id=slot_id, advertiser_business_id=business_id)
    except ValueError as e:
        raise _bad_request(e)


@router.get("/api/advertiser/{business_id}/marketplace-featured-slots")
async def list_marketplace_slots_advertiser(business_id: str,
                                                                                          request: Request,
                                                                                          status: Optional[str] = None,
                                                                                          user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    items = await svc.list_slots(
        request.app.state.db,
        advertiser_business_id=business_id, status=status)
    return {"items": items, "count": len(items)}


@router.get("/api/advertiser/{business_id}/marketplace-featured-slots/"
                        "{slot_id}")
async def get_marketplace_slot(business_id: str, slot_id: str,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    row = await svc.get_slot(request.app.state.db, slot_id=slot_id,
                                                        advertiser_business_id=business_id)
    if not row:
        raise HTTPException(404, {"code": "slot_not_found"})
    return row


@router.post("/api/advertiser/{business_id}/marketplace-featured-slots/"
                          "{slot_id}/cancel")
async def cancel_marketplace_slot(business_id: str, slot_id: str,
                                                                    body: CancelBody, request: Request,
                                                                    user: dict = Depends(current_user)):
    await _assert_business_ownership(request, user, business_id)
    try:
        return await svc.cancel_slot(
            request.app.state.db, slot_id=slot_id,
            advertiser_business_id=business_id,
            reason=(body.reason or "advertiser_cancelled"))
    except ValueError as e:
        raise _bad_request(e)


# ────────────────────────────────────────────────────────────────
# ADMIN
# ────────────────────────────────────────────────────────────────
@router.get("/api/admin/marketplace-featured-slots")
async def admin_list_slots(request: Request,
                                                    status: Optional[str] = None,
                                                    _admin: dict = Depends(require_admin)):
    items = await svc.admin_list(request.app.state.db, status=status)
    return {"items": items, "count": len(items)}


@router.get("/api/admin/marketplace-featured-slots/{slot_id}")
async def admin_get_slot(slot_id: str, request: Request,
                                                  _admin: dict = Depends(require_admin)):
    row = await svc.get_slot(request.app.state.db, slot_id=slot_id)
    if not row:
        raise HTTPException(404, {"code": "slot_not_found"})
    return row


@router.post("/api/admin/marketplace-featured-slots/{slot_id}/approve")
async def admin_approve_slot(slot_id: str, body: AdminDecisionBody,
                                                            request: Request,
                                                            admin: dict = Depends(require_admin)):
    try:
        return await svc.admin_approve(
            request.app.state.db, slot_id=slot_id,
            admin_user_id=admin["user_id"], admin_notes=body.admin_notes)
    except ValueError as e:
        raise _bad_request(e)


@router.post("/api/admin/marketplace-featured-slots/{slot_id}/reject")
async def admin_reject_slot(slot_id: str, body: AdminDecisionBody,
                                                          request: Request,
                                                          admin: dict = Depends(require_admin)):
    try:
        return await svc.admin_reject(
            request.app.state.db, slot_id=slot_id,
            admin_user_id=admin["user_id"], admin_notes=(body.admin_notes or ""))
    except ValueError as e:
        raise _bad_request(e)


# ────────────────────────────────────────────────────────────────
# ADMIN — force indexer run (for E2E)
# ────────────────────────────────────────────────────────────────
@router.post("/api/admin/marketplace/reindex")
async def admin_reindex(request: Request,
                                              _admin: dict = Depends(require_admin)):
    stats = await svc.run_indexer(request.app.state.db)
    return {"ok": True, "stats": stats}


__all__ = ["router"]
