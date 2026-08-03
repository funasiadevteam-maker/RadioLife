"""Phase AD.2 — Sponsored Games Revenue Split · HTTP routes.

Four endpoints:
    POST /api/games/{game_campaign_id}/impression
    GET  /api/advertiser/{advertiser_id}/game-transactions
    GET  /api/merchant/{merchant_id}/game-revenue
    PATCH /api/admin/commission-rules/sponsored-game
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import ad2_sponsored_game_service as _ad2

router = APIRouter(tags=["ad2-sponsored-games"])
logger = logging.getLogger("bigfm.ad2.routes")


# ─── Consumer-side impression / entry ─────────────────────────
class GameEventBody(BaseModel):
    event_type: str = Field(..., description="`impression` (view) or `entry` (play/click)")
    event_id:      Optional[str] = Field(None, description="Client UUID for at-most-once billing.")
    placement:  Optional[str] = None
    user_id:      Optional[str] = None    # server prefers current_user; kept for future service-to-service.


def _normalize_event_type(raw: str) -> str:
    r = (raw or "").strip().lower()
    if r in ("impression", "view", "game_impression"):
        return _ad2.EVENT_GAME_IMPRESSION
    if r in ("entry", "click", "play", "game_entry"):
        return _ad2.EVENT_GAME_ENTRY
    raise HTTPException(400, {"code": "bad_event_type",
                                                        "hint": "impression | entry"})


@router.post("/api/games/{game_campaign_id}/impression",
                          description=(
                              "Record a sponsored-game impression or entry.  "
                              "Deducts the CPM/CPC fee from the advertiser wallet "
                              "and writes a split-routed `payment_transactions_v2` "
                              "row (`flow=ad2_sponsored_game_split`).  Idempotent "
                              "per `event_id`.  Per-user-per-game daily cap enforced."))
async def game_impression(game_campaign_id: str, body: GameEventBody,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    event_type = _normalize_event_type(body.event_type)
    uid = user.get("user_id")
    if not uid:
        raise HTTPException(401, {"code": "no_user"})
    res = await _ad2.record_game_event(
        db,
        game_campaign_id=game_campaign_id,
        user_id=uid,
        event_type=event_type,
        event_id=body.event_id,
        placement=body.placement,
    )
    return res


# ─── Advertiser view ──────────────────────────────────────────
async def _assert_can_view_advertiser(db, advertiser_id: str, user: dict):
    """Advertiser owner OR admin only."""
    if user.get("role") == "admin":
        return
    adv = await db.advertisers_v2.find_one({"advertiser_id": advertiser_id},
                                                                                              {"owner_user_id": 1})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    if adv.get("owner_user_id") != user.get("user_id"):
        raise HTTPException(403, {"code": "not_advertiser_owner"})


@router.get("/api/advertiser/{advertiser_id}/game-transactions",
                          description=("Per-advertiser sponsored-game spend history + "
                                                          "per-campaign roll-ups.  Advertiser owner or admin only."))
async def advertiser_game_transactions(advertiser_id: str, request: Request,
                                                                                                limit: int = Query(100, ge=1, le=500),
                                                                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_can_view_advertiser(db, advertiser_id, user)
    return await _ad2.list_advertiser_game_transactions(
        db, advertiser_id=advertiser_id, limit=limit)


# ─── Merchant view ────────────────────────────────────────────
async def _assert_can_view_merchant(db, merchant_id: str, user: dict):
    """Merchant owner/staff OR admin only.  Reuses the same
    resolver pattern as MER.1/MER.2 (`can_create_links` fallback)."""
    if user.get("role") == "admin":
        return
    biz = await db.businesses.find_one(
        {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]},
        {"owner_user_id": 1, "staff_user_ids": 1})
    if not biz:
        raise HTTPException(404, {"code": "merchant_not_found"})
    uid = user.get("user_id")
    if biz.get("owner_user_id") == uid:
        return
    if uid in (biz.get("staff_user_ids") or []):
        return
    raise HTTPException(403, {"code": "not_merchant_owner_or_staff"})


@router.get("/api/merchant/{merchant_id}/game-revenue",
                          description=("Per-merchant inbound game-sponsorship revenue.  "
                                                          "Merchant owner/staff or admin only."))
async def merchant_game_revenue(merchant_id: str, request: Request,
                                                                          limit: int = Query(100, ge=1, le=500),
                                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _assert_can_view_merchant(db, merchant_id, user)
    return await _ad2.list_merchant_game_revenue(
        db, merchant_id=merchant_id, limit=limit)


# ─── Admin: adjust merchant share ─────────────────────────────
class CommissionOverrideBody(BaseModel):
    merchant_share_pct: int = Field(..., ge=0, le=100,
                                                                        description="Percentage the sponsoring merchant retains (0-100).")


@router.patch("/api/admin/commission-rules/sponsored-game",
                            description=("Override the platform/merchant split on sponsored-game "
                                                        "events.  Sets `commission_percent = 100 - merchant_share_pct` "
                                                        "on the singleton `sponsored_game` fallback rule.  "
                                                        "Admin only.  Effective immediately for subsequent events."))
async def admin_update_sponsored_game_split(body: CommissionOverrideBody,
                                                                                                              request: Request,
                                                                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    from datetime import datetime, timezone
    platform_pct = 100 - int(body.merchant_share_pct)
    r = await db.commission_rules.find_one_and_update(
        {"business_category": "*", "transaction_type": _ad2.COMMISSION_TXN_TYPE,
          "market": None},
        {"$set": {"commission_percent":    float(platform_pct),
                          "fixed_fee_cents":            0,
                          "min_fee_cents":                0,
                          "max_fee_cents":                None,
                          "priority":                          100,
                          "active":                            True,
                          "effective_start":            datetime.now(timezone.utc),
                          "effective_end":                None,
                          "stripe_fee_responsibility": "platform",
                          "updated_at":                      datetime.now(timezone.utc),
                          "updated_by":                      admin.get("user_id")},
          "$setOnInsert": {
              "rule_id":         "cr_sponsored_game_default",
              "created_at":  datetime.now(timezone.utc),
              "note":              "AD.2 sponsored-game default split (managed by admin)."}},
        upsert=True, return_document=True)
    rule = {k: v for k, v in (r or {}).items() if k != "_id"}
    # datetime serialization
    for k, v in list(rule.items()):
        if hasattr(v, "isoformat"):
            rule[k] = v.isoformat()
    return {"ok": True,
                  "merchant_share_pct": int(body.merchant_share_pct),
                  "platform_percent":  float(platform_pct),
                  "rule": rule}


__all__ = ["router"]
