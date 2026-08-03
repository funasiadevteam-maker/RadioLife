"""Phase 42-C — Admin station-claim queue.

Mirrors the AdminTrackModeration UX:
    GET    /api/admin/radio/claims?status=&page=&limit=
    POST /api/admin/radio/claims/{id}/approve
    POST /api/admin/radio/claims/{id}/reject  { reason }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin
from services.station_claim_service import promote_claim_to_owner

router = APIRouter(prefix="/api/admin/radio/claims",
                                    tags=["station-claims-admin"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _strip(d: dict) -> dict:
    out = {**d}
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@router.get("",
                          description=("List station claims for admin review. "
                                                    "Default filter: status=submitted (the queue)."))
async def list_claims(request: Request,
                                            status: Optional[str] = Query(None),
                                            page: int = Query(1, ge=1),
                                            limit: int = Query(50, ge=1, le=200),
                                            user: dict = Depends(require_admin)):
    db = request.app.state.db
    q: Dict[str, Any] = {}
    if status and status != "all":
        q["claim_status"] = status
    total = await db.radio_station_claims.count_documents(q)
    cur = db.radio_station_claims.find(q) \
                  .sort("created_at", -1).skip((page - 1) * limit).limit(limit)
    items = [_strip(r) async for r in cur]
    # Counts by status (for the filter chips).
    counts: Dict[str, int] = {}
    async for r in db.radio_station_claims.aggregate([
            {"$group": {"_id": "$claim_status", "n": {"$sum": 1}}}]):
        counts[r["_id"] or "unknown"] = r["n"]
    return {"items": items, "total": total,
                  "page": page, "limit": limit,
                  "counts_by_status": counts}


@router.post("/{claim_id}/approve",
                          description=("Admin approval.  Skips the email-domain "
                                                    "path and directly promotes the claim to "
                                                    "approved + creates/links the owner profile."))
async def approve_claim(claim_id: str, request: Request,
                                                  user: dict = Depends(require_admin)):
    db = request.app.state.db
    claim = await db.radio_station_claims.find_one({"id": claim_id})
    if not claim:
        raise HTTPException(404, {"code": "claim_not_found"})
    if claim["claim_status"] in {"approved", "rejected", "abandoned"}:
        raise HTTPException(409, {"code": "claim_already_finalized",
                                                                    "claim_status": claim["claim_status"]})
    now = _now()
    patch = {
        "claim_status": "approved",
        "admin_review_status": "approved",
        "admin_reviewer_id": user["user_id"],
        "admin_reviewed_at": now,
        "verification_completed_at": now,
        "updated_at": now,
    }
    await db.radio_station_claims.update_one(
        {"id": claim_id}, {"$set": patch})
    promoted = await promote_claim_to_owner(
        db, claim={**claim, **patch})
    return {"ok": True, "claim_id": claim_id,
                  "claim_status": "approved",
                  "station_id": claim["station_id"],
                  "profile_id": promoted["profile_id"]}


@router.post("/{claim_id}/reject",
                          description=("Admin rejection.  Requires a `reason` field "
                                                    "(stored on the claim for audit)."))
async def reject_claim(claim_id: str, payload: dict, request: Request,
                                                user: dict = Depends(require_admin)):
    db = request.app.state.db
    reason = (payload or {}).get("reason", "").strip()
    if not reason:
        raise HTTPException(400, {"code": "reason_required"})
    claim = await db.radio_station_claims.find_one({"id": claim_id})
    if not claim:
        raise HTTPException(404, {"code": "claim_not_found"})
    if claim["claim_status"] in {"approved", "rejected", "abandoned"}:
        raise HTTPException(409, {"code": "claim_already_finalized",
                                                                    "claim_status": claim["claim_status"]})
    now = _now()
    patch = {
        "claim_status": "rejected",
        "admin_review_status": "rejected",
        "admin_reviewer_id": user["user_id"],
        "admin_reviewed_at": now,
        "admin_rejection_reason": reason,
        "updated_at": now,
    }
    await db.radio_station_claims.update_one(
        {"id": claim_id}, {"$set": patch})
    # Clear station claim_pending if no other active claims.
    other = await db.radio_station_claims.find_one({
        "station_id": claim["station_id"],
        "claim_status": {"$in": ["submitted", "verifying"]},
        "id": {"$ne": claim_id},
    })
    if not other:
        await db.imported_radio_stations.update_one(
            {"id": claim["station_id"], "claim_status": "claim_pending"},
            {"$set": {"claim_status": "unclaimed"}})
    return {"ok": True, "claim_id": claim_id,
                  "claim_status": "rejected",
                  "reason": reason}
