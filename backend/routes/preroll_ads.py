"""Phase 42-B — Pre-roll ads consumer endpoints + user ad-settings.

Public-facing surface invoked by the Live Radio audio player.

Endpoints:
    POST /api/live-radio/preroll/request                        — optional auth
    POST /api/live-radio/preroll/{impression_id}/event   — optional auth
    POST /api/live-radio/preroll/{impression_id}/save-to-wallet — REQUIRES auth
    GET  /api/users/me/ad-settings                                  — REQUIRES auth
    PATCH /api/users/me/ad-settings                                — REQUIRES auth
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user, current_user_optional
from services.premium_gate import is_premium_or_trial
from services.preroll_ad_service import (
    record_impression_event, select_ad_chain_for_play,
)

log = logging.getLogger("bigfm.preroll_ads.public")

preroll_router = APIRouter(prefix="/api/live-radio/preroll",
                                                    tags=["preroll-ads"])
user_router = APIRouter(prefix="/api/users/me",
                                                  tags=["user-ad-settings"])


# ───────────────────────── /request ───────────────────────────
@preroll_router.post("/request",
                                          description=(
                                              "Decide whether a pre-roll should play before the "
                                              "imported live-radio stream.  Anonymous-friendly — "
                                              "anonymous users are tracked by `session_id`."))
async def preroll_request(payload: dict, request: Request,
                                                user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    station_id = (payload or {}).get("station_id")
    session_id = (payload or {}).get("session_id") or f"anon_{uuid.uuid4().hex[:12]}"
    if not station_id:
        raise HTTPException(400, {"code": "station_id_required"})
    # Phase PREROLL.EXT — resolve across ALL station collections (imported,
    # community, AI channels).  No more `imp_*` prefix gating.
    from services.preroll_ad_service import resolve_station
    station = await resolve_station(db, station_id)
    if not station:
        return {"has_preroll": False, "reason": "station_not_found",
                      "station_id": station_id, "session_id": session_id}
    # Per-station opt-out (admin-controlled) — silent skip.
    if station.get("preroll_enabled") is False:
        return {"has_preroll": False, "reason": "preroll_disabled_for_station",
                      "station_id": station_id, "session_id": session_id,
                      "station_type": station.get("station_type")}
    res = await select_ad_chain_for_play(
        db, user, station, session_id,
        country_code=(payload or {}).get("country_code"),
        language=(payload or {}).get("language"))
    res["station_id"] = station_id
    res["session_id"] = session_id
    res["station_type"] = station.get("station_type")
    # Phase A Item 3 — flagship_played_first_time trigger.  Fires the
    # first time an auth'd user tunes into ANY flagship station.  Uses
    # `user_flagship_first_played` marker collection (unique on user_id)
    # for at-most-once semantics.  Silent on error — never blocks preroll.
    if user and user.get("user_id") and station.get("is_flagship"):
        try:
            import asyncio as _aio
            _uid = user["user_id"]
            _marker = await db.user_flagship_first_played.find_one_and_update(
                {"user_id": _uid},
                {"$setOnInsert": {
                    "user_id":            _uid,
                    "station_id":      station_id,
                    "flagship_slug": station.get("flagship_slug"),
                    "first_played_at": datetime.now(timezone.utc),
                }},
                upsert=True, return_document=False)
            if _marker is None:                                # newly inserted
                from services.notification_trigger_dispatcher import dispatch_event
                _aio.create_task(dispatch_event(
                    db, event_name="flagship_played_first_time",
                    user_id=_uid,
                    payload={"station_id": station_id,
                                      "flagship_slug": station.get("flagship_slug")}))
        except Exception as _e:
            log.warning("[trigger] flagship_played_first_time skipped: %s", _e)
    return res


# ───────────────────────── /event ─────────────────────────────
@preroll_router.post("/{impression_id}/event",
                                          description=(
                                              "Record a pre-roll playback event.  "
                                              "event_type ∈ {start, complete, skip, companion_click, "
                                              "wallet_save}.  Anonymous-friendly."))
async def preroll_event(impression_id: str, payload: dict, request: Request,
                                              user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    event_type = (payload or {}).get("event_type")
    metadata = (payload or {}).get("metadata")
    res = await record_impression_event(db, impression_id, event_type,
                                                                                    metadata=metadata)
    if not res["ok"]:
        raise HTTPException(404 if res["code"] == "impression_not_found"
                                            else 400, res)
    return res


# ───────────────────────── /save-to-wallet ────────────────────
@preroll_router.post("/{impression_id}/save-to-wallet",
                                          description=(
                                              "If the impression's ad has an attached_offer_id, "
                                              "drop the matching offer into the user's wallet.  "
                                              "Idempotent — repeated calls return the existing "
                                              "wallet_item_id."))
async def preroll_save_to_wallet(impression_id: str, request: Request,
                                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    row = await db.live_radio_ad_impressions.find_one({"id": impression_id})
    if not row:
        raise HTTPException(404, {"code": "impression_not_found"})
    ad = await db.preroll_ads.find_one({"id": row["ad_id"]})
    if not ad:
        raise HTTPException(404, {"code": "ad_not_found"})
    offer_id = ad.get("attached_offer_id")
    if not offer_id:
        raise HTTPException(400, {"code": "no_offer_attached"})
    # Idempotency check.
    existing = await db.user_wallet_items.find_one({
        "user_id": user["user_id"],
        "source_preroll_impression_id": impression_id,
    })
    if existing:
        return {"ok": True, "wallet_item_id": existing.get("_id") or existing.get("id"),
                      "idempotent": True}
    # Look up the offer for snapshot title/value.
    offer = await db.offers.find_one({"offer_id": offer_id})    \
              or await db.offers.find_one({"id": offer_id}) or {}
    now = datetime.now(timezone.utc)
    wallet_item_id = f"wi_pr_{uuid.uuid4().hex[:12]}"
    await db.user_wallet_items.insert_one({
        "_id": wallet_item_id, "id": wallet_item_id,
        "user_id": user["user_id"], "item_type": "preroll_coupon",
        "offer_id": offer_id,
        "title": offer.get("title") or ad.get("name") or "Saved from pre-roll",
        "description": offer.get("description") or ad.get("companion_cta_text"),
        "value_cents": offer.get("discount_value_cents") or 0,
        "status": "active",
        "expiration": (now + timedelta(days=30)).isoformat(),
        "created_at": now,
        "source_preroll_impression_id": impression_id,
        "source_preroll_ad_id": ad["id"],
    })
    # Record the event + counter.
    await record_impression_event(db, impression_id, "wallet_save",
                                                                            metadata={"wallet_item_id": wallet_item_id})
    return {"ok": True, "wallet_item_id": wallet_item_id, "idempotent": False,
                  "expiration": (now + timedelta(days=30)).isoformat()}


# ───────────────────────── ad-settings ────────────────────────
@user_router.get("/ad-settings",
                                description=(
                                    "Return the user's ad preferences plus their "
                                    "premium-or-trial status.  Free users see "
                                    "`is_premium=false` and `ad_free_enabled=false`."))
async def get_ad_settings(request: Request,
                                                    user: dict = Depends(current_user)):
    settings = user.get("ad_settings") or {}
    is_prem = is_premium_or_trial(user)
    return {
        "is_premium": is_prem,
        "subscription_status": user.get("subscription_status") or "free",
        # Defaults: premium=true, free=false.
        "ad_free_enabled": bool(settings.get("ad_free_enabled", is_prem)),
        "disclosure_acknowledged_at": settings.get("disclosure_acknowledged_at"),
        "disclosure_text": (
            "Premium removes FUUSIC platform ads. Some third-party live "
            "stations may still include ads within their original "
            "broadcast stream."),
    }


@user_router.patch("/ad-settings",
                                  description=(
                                      "Update the user's ad preferences.  Free users get "
                                      "403 with an upgrade pointer if they try to flip the "
                                      "toggle to true."))
async def patch_ad_settings(payload: dict, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    ad_free = bool((payload or {}).get("ad_free_enabled"))
    ack = bool((payload or {}).get("acknowledge_disclosure"))
    is_prem = is_premium_or_trial(user)
    if ad_free and not is_prem:
        raise HTTPException(403, {
            "code": "premium_required",
            "message": "Hide-platform-ads is a Premium-tier setting.",
            "upgrade_url": "/pricing",
        })
    now = datetime.now(timezone.utc)
    updates: Dict[str, Any] = {
        "ad_settings.ad_free_enabled": ad_free,
        "ad_settings.updated_at": now,
    }
    if ack:
        updates["ad_settings.disclosure_acknowledged_at"] = now
    await db.users.update_one({"user_id": user["user_id"]},
                                                                    {"$set": updates})
    return {"ok": True, "is_premium": is_prem,
                  "ad_free_enabled": ad_free,
                  "disclosure_acknowledged_at": now.isoformat() if ack else
                                                                          (user.get("ad_settings") or {}).get("disclosure_acknowledged_at")}
