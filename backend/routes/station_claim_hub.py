"""Phase CLAIM.1 — Claim Radio Hub browse endpoints.

Public discovery + per-user status:
    GET  /api/stations/claimable
    GET  /api/stations/{station_id}/claim-status
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, current_user_optional

router = APIRouter(tags=["claim-hub"])


def _project(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id":                                    s.get("id"),
        "name":                              s.get("name"),
        "homepage":                      s.get("homepage"),
        "country":                        s.get("country"),
        "country_code":              s.get("country_code"),
        "state":                            s.get("state"),
        "language":                      s.get("language"),
        "language_codes":         s.get("language_codes"),
        "favicon":                        s.get("favicon"),
        "logo_url":                      s.get("logo_url"),
        "banner_image_url":     s.get("banner_image_url"),
        "tags_json":                    s.get("tags_json") or [],
        "votes":                            s.get("votes"),
        "click_count":                s.get("click_count"),
        "claim_status":              s.get("claim_status") or "unclaimed",
        "claim_badge_visible":  bool(s.get("claim_badge_visible")),
        "is_flagship":                bool(s.get("is_flagship")),
        "flagship_region":         s.get("flagship_region"),
    }


@router.get("/api/stations/claimable",
                          description=("Paginated list of imported stations available "
                                                    "to claim.  Excludes already-claimed rows.  "
                                                    "Filters: q (name substring), country, language, "
                                                    "region (flagship_region), page, limit."))
async def list_claimable(request: Request,
                                                        q: Optional[str] = Query(None),
                                                        country: Optional[str] = Query(None),
                                                        language: Optional[str] = Query(None),
                                                        region: Optional[str] = Query(None),
                                                        page: int = Query(1, ge=1),
                                                        limit: int = Query(24, ge=1, le=100)):
    db = request.app.state.db
    query: Dict[str, Any] = {
        "$or": [{"active": True}, {"is_flagship": True}],
        "claim_status": {"$ne": "claimed"},
    }
    if q:
        query.setdefault("$and", []).append(
            {"name": {"$regex": re.escape(q), "$options": "i"}})
    if country:
        query["country_code"] = country.upper()
    if language:
        query["language"] = language.lower()
    if region:
        query["flagship_region"] = region.upper()

    total = await db.imported_radio_stations.count_documents(query)
    items = []
    cur = db.imported_radio_stations.find(query) \
                                                                                  .sort([("is_flagship", -1),
                                                                                              ("votes", -1),
                                                                                              ("click_count", -1)]) \
                                                                                  .skip((page - 1) * limit).limit(limit)
    async for s in cur:
        items.append(_project(s))
    return {"items": items, "total": total,
                        "page": page, "limit": limit,
                        "filters": {"q": q, "country": country,
                                                          "language": language, "region": region}}


@router.get("/api/stations/{station_id}/claim-status",
                          description=("Return the current user's claim status for a "
                                                    "specific station.  Anonymous callers get "
                                                    "`{status: 'anonymous'}`."))
async def my_claim_status(station_id: str, request: Request,
                                                        user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    station = await db.imported_radio_stations.find_one(
        {"id": station_id}, projection={"claim_status": 1, "owner_profile_id": 1,
                                                                              "name": 1})
    if not station:
        raise HTTPException(404, {"code": "station_not_found"})
    payload = {"station_id": station_id,
                              "station_name": station.get("name"),
                              "station_claim_status": station.get("claim_status") or "unclaimed",
                              "already_claimed_by_someone_else": False}
    if not user:
        payload["status"] = "anonymous"
        return payload
    # Is this station claimed BY this user?
    profile = await db.station_owner_profiles.find_one(
        {"user_id": user["user_id"]})
    if profile and station.get("owner_profile_id") == profile["id"]:
        payload["status"] = "owned_by_me"
        payload["owner_profile_id"] = profile["id"]
        return payload
    # Otherwise — is there an active claim by the user?
    my_claim = await db.radio_station_claims.find_one({
        "station_id": station_id,
        "claimed_by_user_id": user["user_id"]},
        sort=[("created_at", -1)])
    if my_claim:
        payload["status"] = my_claim.get("claim_status")
        payload["my_claim_id"] = my_claim["id"]
        return payload
    # If station is claimed by someone else, flag it.
    if station.get("claim_status") == "claimed":
        payload["already_claimed_by_someone_else"] = True
    payload["status"] = "none"
    return payload


# ─────────────────────── Proof download (admin-only) ──────────
proof_router = APIRouter(tags=["claim-proof-admin"])


@proof_router.get(
    "/api/admin/radio/claims/{claim_id}/proof/{filename}",
    description=("Admin-only download of a claim proof document.  "
                              "Files live under `static/claim_proofs/{claim_id}/` "
                              "and are NOT publicly indexed."))
async def download_claim_proof(claim_id: str, filename: str, request: Request,
                                                                            admin: dict = Depends(current_user)):
    if not admin.get("is_admin") and admin.get("role") not in ("admin", "super_admin"):
        raise HTTPException(403, {"code": "forbidden"})
    from fastapi.responses import FileResponse
    from services.station_upload_service import open_proof_file
    fp = open_proof_file(claim_id=claim_id, filename=filename)
    if not fp:
        raise HTTPException(404, {"code": "proof_not_found"})
    return FileResponse(str(fp))
