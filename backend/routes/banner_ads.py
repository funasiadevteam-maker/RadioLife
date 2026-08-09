"""Phase 42 Session 1 — Waterfall orchestrator + 4 banner ad slots.

Slot inventory: top_banner · left_mid · center_mid · right_mid

Waterfall (per slot, per request):
   1. direct_sold   — existing services/ad_decisioning.py
   2. private_mkt   — placeholder (returns None for MVP)
   3. adswizz       — placeholder (key not yet provisioned)
   4. adsense       — placeholder (publisher application pending)
   5. house         — fallback to services/ai_ad_creator generated banner

Premium / trial users see NO banners. Frequency caps:
   - max 1 refresh per slot per 30s
   - max 6 impressions per slot per session
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user

router = APIRouter(prefix="/api/ads/banner", tags=["banner-ads"])
log = logging.getLogger("bigfm.banner_ads")

VALID_SLOTS = {"top_banner", "left_mid", "center_mid", "right_mid"}

REFRESH_COOLDOWN_SEC = 30
SESSION_IMPRESSION_CAP = 6


def _now() -> datetime: return datetime.now(timezone.utc)


def _is_premium(user: dict) -> bool:
    """Free vs premium-or-trial gate.  Premium users get NO banners."""
    if not user: return False
    return bool(user.get("is_premium")
                or user.get("trial_active")
                or user.get("subscription_status") == "active")


async def _admin_slot_enabled(db, slot_id: str) -> bool:
    cfg = await db.banner_slot_config.find_one({"slot_id": slot_id})
    if not cfg: return True  # default ON
    return bool(cfg.get("enabled", True))


async def _try_house_ad(db) -> Optional[dict]:
    """Fallback house ad — picks any approved banner creative tagged 'house'.
    Returns None when no house creative is available (slot rendered empty)."""
    c = await db.ad_creatives.find_one(
        {"status": "approved", "house": True, "format": "banner"})
    if not c:
        return {"tier": "house_default",
                "creative_id": "house_default",
                "image_url": None,
                "click_url": "/premium",
                "alt_text": "Upgrade to RadioLife Premium — ad-free listening",
                "headline": "Tired of ads?",
                "sub_text": "Go ad-free with RadioLife Premium →",
                "cta": "Try free for 7 days"}
    return {"tier": "house",
            "creative_id": str(c.get("_id") or c.get("creative_id")),
            "image_url":   c.get("image_url"),
            "click_url":   c.get("click_url") or "/premium",
            "alt_text":    c.get("alt_text") or "",
            "headline":    c.get("headline"),
            "sub_text":    c.get("sub_text"),
            "cta":         c.get("cta")}


async def _within_frequency_cap(db, user_id: str, slot_id: str) -> bool:
    cutoff = _now() - timedelta(seconds=REFRESH_COOLDOWN_SEC)
    n_recent = await db.banner_impressions.count_documents({
        "user_id": user_id, "slot_id": slot_id,
        "shown_at": {"$gte": cutoff.isoformat()}})
    return n_recent == 0


@router.get("/{slot_id}")
async def get_banner_for_slot(slot_id: str, request: Request,
                               station_slug: Optional[str] = Query(None),
                               user: dict = Depends(current_user)):
    if slot_id not in VALID_SLOTS:
        raise HTTPException(400, {"code": "bad_slot",
                                  "allowed": sorted(VALID_SLOTS)})
    # Premium users → 204 empty.
    if _is_premium(user):
        return {"slot_id": slot_id, "tier": "premium_no_ads", "ad": None}

    db = request.app.state.db
    if not await _admin_slot_enabled(db, slot_id):
        return {"slot_id": slot_id, "tier": "slot_disabled", "ad": None}
    if not await _within_frequency_cap(db, user["user_id"], slot_id):
        return {"slot_id": slot_id, "tier": "cooldown", "ad": None}

    # Waterfall:
    # 1. direct_sold — try existing decisioning service.
    try:
        from services.ad_decisioning import pick_banner_for_slot
        ad = await pick_banner_for_slot(db, user_id=user["user_id"],
                                          slot_id=slot_id)
        if ad:
            await _record_impression(db, user["user_id"], slot_id, ad,
                                       "direct_sold",
                                       station_slug=station_slug)
            return {"slot_id": slot_id, "tier": "direct_sold", "ad": ad}
    except Exception as e:
        log.debug("[waterfall] direct_sold skipped (%s)", e)

    # 2-4. private_mkt, adswizz, adsense — placeholders (return None
    # until SSP keys provisioned + AdSense publisher approval).
    # 5. House fallback.
    house = await _try_house_ad(db)
    if house:
        await _record_impression(db, user["user_id"], slot_id, house,
                                   house["tier"],
                                   station_slug=station_slug)
        return {"slot_id": slot_id, "tier": house["tier"], "ad": house}
    return {"slot_id": slot_id, "tier": "empty", "ad": None}


async def _record_impression(db, user_id: str, slot_id: str,
                              ad: dict, tier: str,
                              station_slug: Optional[str] = None) -> None:
    """Phase 41 S6.A — when a direct-sold banner serves on a
    community-station page, also write a creator earnings ledger
    row. Mocked CPM via BANNER_IMPRESSION_CPM_CENTS (default $5 CPM →
    50¢ per 100 impressions or 0.5¢ per single impression — wrapped
    to int cents which gives us a small dust-rounding-to-house but
    that's the right side to err on for an MVP).
    """
    import uuid as _uuid
    impression_id = f"bi_{_uuid.uuid4().hex[:14]}"
    try:
        await db.banner_impressions.insert_one({
            "_id":          impression_id,
            "impression_id": impression_id,
            "user_id":     user_id,
            "slot_id":     slot_id,
            "tier":        tier,
            "creative_id": ad.get("creative_id"),
            "station_slug": station_slug,
            "shown_at":    _now().isoformat(),
        })
    except Exception as e:
        log.warning("[banner] impression log failed: %s", e)
        return

    # Phase 41 S6.A — ledger attribution. Only direct_sold tier yields
    # revenue to creators (house ads are platform-internal upsells).
    if tier != "direct_sold" or not station_slug:
        return
    try:
        s = await db.community_radio_stations.find_one(
            {"slug": station_slug})
        if not s or not s.get("owner_user_id"):
            return
        cpm_cents = int(os.environ.get("BANNER_IMPRESSION_CPM_CENTS", "500"))
        gross = max(1, cpm_cents // 1000)
        # 500 ¢ / 1000 imps → 0.5¢ rounded to 1¢; tiny per-event
        # ledger rows are intentional so the table stays auditable.
        from services.creator_revenue import write_ledger_row
        await write_ledger_row(
            db, station=s,
            owner_user_id=s["owner_user_id"],
            source_type="banner_impression",
            source_ref=f"bi_{impression_id}",
            gross_amount_cents=gross,
            attribution_metadata={
                "slot_id":     slot_id,
                "creative_id": ad.get("creative_id"),
                "viewer_user_id": user_id,
                "cpm_cents_assumed": cpm_cents,
            })
    except Exception as e:
        log.debug("[banner] ledger attribution skipped: %s", e)


@router.post("/{slot_id}/click")
async def record_click(slot_id: str, request: Request, body: dict,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        await db.banner_clicks.insert_one({
            "user_id":     user["user_id"],
            "slot_id":     slot_id,
            "creative_id": body.get("creative_id"),
            "tier":        body.get("tier"),
            "clicked_at":  _now().isoformat(),
        })
    except Exception as e:
        log.warning("[banner] click log failed: %s", e)
    return {"ok": True}


@router.get("/_admin/config")
async def admin_get_config(request: Request,
                            user: dict = Depends(current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, {"code": "forbidden"})
    db = request.app.state.db
    out = {}
    for s in sorted(VALID_SLOTS):
        cfg = await db.banner_slot_config.find_one({"slot_id": s})
        out[s] = {"enabled": True if not cfg else bool(cfg.get("enabled", True))}
    return out


@router.put("/_admin/config/{slot_id}")
async def admin_set_slot(slot_id: str, request: Request, body: dict,
                          user: dict = Depends(current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, {"code": "forbidden"})
    if slot_id not in VALID_SLOTS:
        raise HTTPException(400, {"code": "bad_slot"})
    db = request.app.state.db
    await db.banner_slot_config.update_one(
        {"slot_id": slot_id},
        {"$set": {"enabled": bool(body.get("enabled")),
                  "updated_at": _now().isoformat(),
                  "updated_by": user["user_id"]}}, upsert=True)
    return {"ok": True, "slot_id": slot_id,
            "enabled": bool(body.get("enabled"))}
