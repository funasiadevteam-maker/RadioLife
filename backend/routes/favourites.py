"""Reorder Favourites — save a favourite venue and rebook the usual slot in
one tap.  'Usual slot' = the listener's most recent booking at that venue."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user

router = APIRouter(prefix="/api/favourites", tags=["favourites"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _last_booking(db, uid: str, campaign_id: str) -> Optional[Dict[str, Any]]:
    return await db.venue_bookings.find_one(
        {"user_id": uid, "campaign_id": campaign_id},
        sort=[("created_at", -1)])


@router.post("/venues/{campaign_id}")
async def toggle_favourite(campaign_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    existing = await db.venue_favourites.find_one({"user_id": uid, "campaign_id": campaign_id})
    if existing:
        await db.venue_favourites.delete_one({"user_id": uid, "campaign_id": campaign_id})
        return {"ok": True, "favourited": False}
    c = await db.merchant_campaigns.find_one({"campaign_id": campaign_id, "type": "booking"})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    await db.venue_favourites.insert_one({
        "user_id": uid, "campaign_id": campaign_id,
        "sponsor_name": c.get("sponsor_name"), "venue_title": c.get("title"),
        "created_at": _now()})
    return {"ok": True, "favourited": True}


@router.get("/venues")
async def list_favourites(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    out = []
    async for f in db.venue_favourites.find({"user_id": uid}).sort("created_at", -1):
        c = await db.merchant_campaigns.find_one(
            {"campaign_id": f["campaign_id"]},
            {"sponsor_name": 1, "title": 1, "slots": 1, "status": 1})
        last = await _last_booking(db, uid, f["campaign_id"])
        out.append({
            "campaign_id": f["campaign_id"],
            "sponsor_name": (c or {}).get("sponsor_name") or f.get("sponsor_name"),
            "venue_title": (c or {}).get("title") or f.get("venue_title"),
            "available_slots": (c or {}).get("slots", []),
            "active": (c or {}).get("status") == "active",
            "usual_slot": (last or {}).get("slot"),
            "usual_party": (last or {}).get("party_size"),
        })
    return {"items": out, "total": len(out)}


@router.post("/venues/{campaign_id}/rebook")
async def rebook(campaign_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    c = await db.merchant_campaigns.find_one({"campaign_id": campaign_id, "type": "booking"})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("status") != "active":
        raise HTTPException(400, {"code": "campaign_inactive"})
    slots = c.get("slots") or []
    last = await _last_booking(db, uid, campaign_id)
    slot = (last or {}).get("slot")
    if slot not in slots:
        slot = slots[0] if slots else None
    if not slot:
        raise HTTPException(400, {"code": "no_slots"})
    booking = {
        "booking_id": f"bk_{uuid.uuid4().hex[:12]}", "campaign_id": campaign_id,
        "merchant_id": c.get("merchant_id"), "user_id": uid,
        "booking_type": c.get("booking_type", "table"), "slot": slot,
        "party_size": (last or {}).get("party_size", 2),
        "name": (last or {}).get("name"), "phone": (last or {}).get("phone"),
        "status": "confirmed", "created_at": _now(),
    }
    await db.venue_bookings.insert_one(dict(booking))
    try:
        from routes.notifications import _enqueue
        await _enqueue(db, owner_user_id=uid, station_id="bookings",
                       station_slug="bookings", type_="booking_reminder",
                       payload={"campaign_id": campaign_id, "booking_id": booking["booking_id"],
                                "sponsor_name": c.get("sponsor_name"), "title": c.get("title"),
                                "slot": slot, "rebooked": True},
                       dedupe_key=f"rebook:{booking['booking_id']}")
    except Exception:
        pass
    return {"ok": True, "booking_id": booking["booking_id"], "slot": slot,
            "sponsor_name": c.get("sponsor_name"), "venue_title": c.get("title")}


__all__ = ["router"]
