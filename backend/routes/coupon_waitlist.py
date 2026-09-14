"""P1.3 — Sold-Out Waitlist ("remind me").

When an FPK coupon game is sold out for the day (remaining_today == 0),
a listener can join a per-campaign waitlist. When the daily cap rolls
over (or capacity otherwise returns), we ping every waiter with an
in-app notification (station_notifications feed / bell) AND a best-effort
push (Emergent relay — fires only on a published native build).

No cron is required: delivery is driven by (a) an admin dispatch endpoint
(deterministic) and (b) an opportunistic, rate-limited auto-dispatch that
piggybacks on the public scarcity poll, so the first traffic after the
UTC-midnight reset flushes the queue.

Endpoints
  POST /api/store/{advertiser_id}/waitlist          {campaign_id}  → join
  POST /api/store/{advertiser_id}/waitlist/leave     {campaign_id}  → leave
  GET  /api/me/waitlist                                              → my active entries
  POST /api/admin/waitlist/dispatch                                  → flush due pings (admin)
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user, require_admin
from routes.storefront import _scarcity_for_game, _today_str

logger = logging.getLogger("bigfm.coupon_waitlist")

store_waitlist_router = APIRouter(prefix="/api/store", tags=["coupon-waitlist"])
me_waitlist_router = APIRouter(prefix="/api/me", tags=["coupon-waitlist"])
admin_waitlist_router = APIRouter(prefix="/api/admin/waitlist", tags=["coupon-waitlist"])

# In-process throttle for the opportunistic auto-dispatch.
_LAST_AUTO_DISPATCH = {"at": 0.0}
_AUTO_DISPATCH_MIN_GAP_SEC = 120.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WaitlistBody(BaseModel):
    campaign_id: str


async def _campaign(db, campaign_id: str) -> dict | None:
    return await db.game_campaigns.find_one({"campaign_id": campaign_id})


async def _remaining_today(db, campaign_id: str):
    """(remaining_today, is_coupon_game) for a campaign. None remaining = unlimited."""
    prizes = await db.game_prizes.find(
        {"campaign_id": campaign_id, "active": True}).to_list(50)
    sc = _scarcity_for_game(prizes, _today_str())
    return sc["remaining_today"], sc["is_coupon_game"]


async def _notify_waiter(db, entry: dict) -> None:
    """In-app notification + best-effort push for one restocked waiter."""
    uid = entry["user_id"]
    camp_id = entry["campaign_id"]
    title = entry.get("campaign_title") or "Coupons restocked"
    store_url = f"/store/{entry.get('advertiser_id')}"
    # In-app (station_notifications feed / bell) — dedupe per user+campaign+day.
    try:
        from routes.notifications import _enqueue
        await _enqueue(
            db,
            owner_user_id=uid,
            station_id=f"store:{entry.get('advertiser_id')}",
            station_slug=str(entry.get("advertiser_id") or "store"),
            type_="coupon_restock",
            payload={
                "campaign_id": camp_id,
                "campaign_title": title,
                "advertiser_id": entry.get("advertiser_id"),
                "store_url": store_url,
                "play_url": f"/play/{camp_id}",
                "play_route": f"/game/{camp_id}",
                "message": f"“{title}” just restocked — play now before it sells out again!",
            },
            dedupe_key=f"restock:{uid}:{camp_id}:{_today_str()}",
        )
    except Exception as e:
        logger.warning("[waitlist] in-app enqueue failed: %s", e)
    # Push (best-effort — fires only on a real build with a valid push key).
    try:
        from services.push_service import send_push
        await send_push(
            [uid],
            {"title": "Coupons back in stock 🎟️",
             "message": f"“{title}” just restocked — play now!",
             "action_url": store_url,
             "deeplink": f"/game/{camp_id}"},
            idempotency_key=f"restock:{uid}:{camp_id}:{_today_str()}",
        )
    except Exception as e:
        logger.debug("[waitlist] push skipped/failed (non-blocking): %s", e)


async def dispatch_waitlist(db, campaign_id: str | None = None, force: bool = False) -> dict:
    """Notify waiting entries, then mark them notified. Returns {checked, notified}.

    Normally (auto-dispatch after a reset) a waiter is only pinged once their
    campaign has capacity again. `force=True` (a manual admin flush) pings
    every waiting entry regardless of current stock."""
    q: dict = {"status": "waiting"}
    if campaign_id:
        q["campaign_id"] = campaign_id
    entries = await db.coupon_waitlist.find(q).to_list(2000)
    checked = 0
    notified = 0
    remaining_cache: dict = {}
    for e in entries:
        checked += 1
        cid = e["campaign_id"]
        if not force:
            if cid not in remaining_cache:
                remaining_cache[cid] = await _remaining_today(db, cid)
            remaining, is_coupon = remaining_cache[cid]
            available = (not is_coupon) or (remaining is None) or (remaining > 0)
            if not available:
                continue
        await _notify_waiter(db, e)
        await db.coupon_waitlist.update_one(
            {"_id": e["_id"]},
            {"$set": {"status": "notified", "notified_at": _now()}})
        notified += 1
    return {"checked": checked, "notified": notified}


async def maybe_auto_dispatch(db) -> None:
    """Rate-limited, fire-and-forget flush driven by public scarcity polls."""
    now = time.time()
    if now - _LAST_AUTO_DISPATCH["at"] < _AUTO_DISPATCH_MIN_GAP_SEC:
        return
    _LAST_AUTO_DISPATCH["at"] = now
    try:
        await dispatch_waitlist(db)
    except Exception as e:
        logger.warning("[waitlist] auto-dispatch failed: %s", e)


@store_waitlist_router.post("/{advertiser_id}/waitlist")
async def join_waitlist(advertiser_id: str, body: WaitlistBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    camp = await _campaign(db, body.campaign_id)
    if not camp or camp.get("advertiser_id") != advertiser_id:
        raise HTTPException(404, "campaign_not_found")
    existing = await db.coupon_waitlist.find_one(
        {"user_id": uid, "campaign_id": body.campaign_id, "status": "waiting"})
    if existing:
        return {"ok": True, "on_waitlist": True, "already": True}
    await db.coupon_waitlist.insert_one({
        "_id": "cwl_" + uuid.uuid4().hex[:16],
        "user_id": uid,
        "advertiser_id": advertiser_id,
        "campaign_id": body.campaign_id,
        "campaign_title": camp.get("title"),
        "status": "waiting",
        "created_at": _now(),
        "notified_at": None,
    })
    return {"ok": True, "on_waitlist": True}


@store_waitlist_router.post("/{advertiser_id}/waitlist/leave")
async def leave_waitlist(advertiser_id: str, body: WaitlistBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.coupon_waitlist.update_many(
        {"user_id": user["user_id"], "campaign_id": body.campaign_id,
         "status": "waiting"},
        {"$set": {"status": "left", "left_at": _now()}})
    return {"ok": True, "on_waitlist": False}


@me_waitlist_router.get("/waitlist")
async def my_waitlist(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    rows = await db.coupon_waitlist.find(
        {"user_id": user["user_id"], "status": "waiting"}
    ).sort("created_at", -1).to_list(200)
    return {"items": [{
        "campaign_id": r["campaign_id"],
        "advertiser_id": r.get("advertiser_id"),
        "campaign_title": r.get("campaign_title"),
        "created_at": r["created_at"].isoformat() if hasattr(r.get("created_at"), "isoformat") else r.get("created_at"),
    } for r in rows], "campaign_ids": [r["campaign_id"] for r in rows]}


@admin_waitlist_router.post("/dispatch")
async def admin_dispatch(request: Request, force: bool = True,
                         _u: dict = Depends(require_admin)):
    """Manual admin flush — pings all waiting entries by default (force=True).
    Pass ?force=false to only notify campaigns that currently have stock."""
    db = request.app.state.db
    return await dispatch_waitlist(db, force=force)


async def ensure_waitlist_indexes(db) -> None:
    await db.coupon_waitlist.create_index(
        [("user_id", 1), ("campaign_id", 1), ("status", 1)],
        name="waitlist_owner_campaign")
    await db.coupon_waitlist.create_index([("status", 1), ("campaign_id", 1)])


__all__ = ["store_waitlist_router", "me_waitlist_router", "admin_waitlist_router",
           "dispatch_waitlist", "maybe_auto_dispatch", "ensure_waitlist_indexes"]
