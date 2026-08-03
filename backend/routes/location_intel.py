"""Phase S — Location Intelligence routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, require_admin
from services import location_intel_service as svc

router = APIRouter(tags=["phase-s-location-intel"])


# ─── admin ─────────────────────────────────
@router.get("/api/admin/location-intel/heatmap")
async def admin_heatmap(request: Request,
                         sw_lat: float = Query(...),
                         sw_lng: float = Query(...),
                         ne_lat: float = Query(...),
                         ne_lng: float = Query(...),
                         days: int = Query(30, ge=1, le=90),
                         refresh: bool = Query(False),
                         user: dict = Depends(require_admin)):
    if sw_lat >= ne_lat or sw_lng >= ne_lng:
        raise HTTPException(400, {"code": "invalid_bounds"})
    return await svc.admin_heatmap(
        request.app.state.db,
        bounds={"sw_lat": sw_lat, "sw_lng": sw_lng,
                "ne_lat": ne_lat, "ne_lng": ne_lng},
        days=days, refresh=refresh)


@router.get("/api/admin/location-intel/regions/rank")
async def admin_regions_rank(request: Request,
                              days: int = Query(30, ge=1, le=90),
                              limit: int = Query(20, ge=1, le=100),
                              refresh: bool = Query(False),
                              user: dict = Depends(require_admin)):
    return await svc.admin_regions_rank(
        request.app.state.db, days=days, limit=limit, refresh=refresh)


@router.get("/api/admin/location-intel/geofence-effectiveness")
async def admin_geofence_effectiveness(request: Request,
                                        days: int = Query(30, ge=1, le=90),
                                        refresh: bool = Query(False),
                                        user: dict = Depends(require_admin)):
    return await svc.admin_geofence_effectiveness(
        request.app.state.db, days=days, refresh=refresh)


@router.get("/api/admin/location-intel/summary")
async def admin_summary(request: Request,
                         days: int = Query(30, ge=1, le=90),
                         refresh: bool = Query(False),
                         user: dict = Depends(require_admin)):
    return await svc.admin_summary(
        request.app.state.db, days=days, refresh=refresh)


# ─── merchant ─────────────────────────
@router.get("/api/merchant/{business_id}/location-intel/foot-traffic")
async def merchant_foot_traffic(business_id: str, request: Request,
                                 days: int = Query(30, ge=1, le=90),
                                 refresh: bool = Query(False),
                                 user: dict = Depends(current_user)):
    ok = await svc.check_business_access(request.app.state.db, business_id, user)
    if not ok:
        raise HTTPException(403, {"code": "forbidden"})
    try:
        return await svc.merchant_foot_traffic(
            request.app.state.db, business_id=business_id,
            days=days, refresh=refresh)
    except ValueError as e:
        code = str(e)
        raise HTTPException(404 if code == "business_not_found" else 400,
                            {"code": code})


# ─── advertiser ─────────────────────
@router.get("/api/advertiser/{business_id}/location-intel/density")
async def advertiser_density(business_id: str, request: Request,
                              center_lat: float = Query(...),
                              center_lng: float = Query(...),
                              radius_meters: int = Query(...,
                                                           ge=100, le=50000),
                              days: int = Query(30, ge=1, le=90),
                              refresh: bool = Query(False),
                              user: dict = Depends(current_user)):
    # For the advertiser preview, ownership check is on the advertiser
    # business id — reuse the merchant/business access helper (works for
    # both `advertisers_v2` and legacy `businesses`).
    ok = (user.get("role") == "admin") or \
         await svc.check_business_access(request.app.state.db,
                                          business_id, user)
    # Also allow if business_id is an advertisers_v2.advertiser_id and
    # that advertiser is owned by the user.
    if not ok:
        adv = await request.app.state.db.advertisers_v2.find_one(
            {"advertiser_id": business_id},
            {"_id": 0, "owner_user_id": 1, "staff_user_ids": 1})
        if adv and (adv.get("owner_user_id") == user.get("user_id") or
                    user.get("user_id") in (adv.get("staff_user_ids") or [])):
            ok = True
    if not ok:
        raise HTTPException(403, {"code": "forbidden"})
    return await svc.advertiser_density(
        request.app.state.db,
        center_lat=center_lat, center_lng=center_lng,
        radius_meters=radius_meters, days=days, refresh=refresh)


__all__ = ["router"]
