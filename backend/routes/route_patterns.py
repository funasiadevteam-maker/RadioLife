"""Phase 39 Session 6 — Route patterns + trips + business visits API.

3 endpoints, all gated on `users.location_consent_level >= 3`.
Also exposes a manual `/api/routes/detect` sweep used by tests + admin.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user
from services.route_pattern_detection import detect_for_user

router = APIRouter(prefix="/api/routes", tags=["routes"])
log = logging.getLogger("bigfm.routes_api")


async def _check_consent(db, user, required: int = 3):
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    cl = int(fresh.get("location_consent_level", 0))
    if cl < required:
        raise HTTPException(403, {"code": "consent_required",
                                  "required_level": required,
                                  "current_level": cl})
    return fresh


@router.get("/patterns")
async def get_patterns(request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_consent(db, user)
    out = []
    async for r in db.UserRoutePatterns.find(
        {"user_id": user["user_id"]}
    ).sort("last_seen", -1):
        r.pop("_id", None); out.append(r)
    return {"count": len(out), "patterns": out}


@router.get("/trips")
async def get_trips(request: Request,
                    since: Optional[str] = Query(None),
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_consent(db, user)
    q: dict = {"user_id": user["user_id"]}
    if since:
        try:
            dt = datetime.fromisoformat(since)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            q["started_at"] = {"$gte": dt}
        except ValueError:
            raise HTTPException(400, {"code": "bad_since",
                                      "message": "use ISO-8601"})
    out = []
    async for r in db.UserTrips.find(q).sort("started_at", -1).limit(200):
        r.pop("_id", None); out.append(r)
    return {"count": len(out), "trips": out}


@router.get("/business_visits")
async def get_business_visits(request: Request,
                              category: Optional[str] = Query(None),
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_consent(db, user)
    q: dict = {"user_id": user["user_id"]}
    if category:
        q["category"] = category
    out = []
    async for r in db.UserBusinessVisits.find(q).sort("visited_at", -1).limit(200):
        r.pop("_id", None); out.append(r)
    return {"count": len(out), "visits": out}


@router.post("/detect")
async def manual_detect(request: Request,
                        user: dict = Depends(current_user)):
    """Manual sweep — used by tests and the /places UI refresh."""
    db = request.app.state.db
    await _check_consent(db, user)
    return await detect_for_user(db, user["user_id"])
