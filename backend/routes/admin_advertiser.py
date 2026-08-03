"""Phase 18a — Admin queue for advertiser campaigns + creative safety override."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user, require_admin
from services.advertisers import admin_approve, admin_reject

logger = logging.getLogger("bigfm.admin.advertiser")

admin_advertiser_router = APIRouter(prefix="/api/admin/advertiser",
                                                       tags=["admin-advertiser-18a"])


def _clean(d):
    if not d: return d
    out = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@admin_advertiser_router.get("/campaigns")
async def list_pending(request: Request,
                                  status: Optional[str] = "pending_review",
                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    q  = {"status": status} if status else {}
    docs = await db.ad_campaigns.find(q).sort([("submitted_at", -1)]).to_list(200)
    # Enrich with advertiser name for the queue display.
    out = []
    for d in docs:
        adv = await db.advertisers.find_one({"id": d.get("advertiser_id")})
        item = _clean(d)
        item["advertiser_name"] = adv.get("name") if adv else None
        out.append(item)
    return {"items": out}


@admin_advertiser_router.post("/campaigns/{campaign_id}/approve")
async def approve_campaign(campaign_id: str, request: Request,
                                         admin: dict = Depends(require_admin)):
    db = request.app.state.db
    found = await db.ad_campaigns.find_one({"id": campaign_id})
    if not found:
        raise HTTPException(404, "campaign not found")
    out = await admin_approve(db, campaign_id=campaign_id,
                                       admin_user_id=admin["user_id"])
    await db.admin_audit_log.insert_one({
        "action": "campaign_approve", "actor": admin["user_id"],
        "campaign_id": campaign_id, "ts": datetime.now(timezone.utc),
    })
    return out


class RejectBody(BaseModel):
    reason: str


@admin_advertiser_router.post("/campaigns/{campaign_id}/reject")
async def reject_campaign(campaign_id: str, body: RejectBody, request: Request,
                                       admin: dict = Depends(require_admin)):
    db = request.app.state.db
    found = await db.ad_campaigns.find_one({"id": campaign_id})
    if not found:
        raise HTTPException(404, "campaign not found")
    out = await admin_reject(db, campaign_id=campaign_id,
                                     admin_user_id=admin["user_id"],
                                     reason=body.reason)
    await db.admin_audit_log.insert_one({
        "action": "campaign_reject", "actor": admin["user_id"],
        "campaign_id": campaign_id, "reason": body.reason,
        "ts": datetime.now(timezone.utc),
    })
    return out


class SafetyOverrideBody(BaseModel):
    verdict: str   # approved | rejected | review
    reason:  str


@admin_advertiser_router.post("/creatives/{creative_id}/override_safety")
async def override_safety(creative_id: str, body: SafetyOverrideBody,
                                       request: Request,
                                       admin: dict = Depends(require_admin)):
    if body.verdict not in ("approved", "rejected", "review"):
        raise HTTPException(400, "verdict must be approved|rejected|review")
    db = request.app.state.db
    cr = await db.ad_creatives.find_one({"id": creative_id})
    if not cr:
        raise HTTPException(404, "creative not found")
    prev = cr.get("brand_safety_check") or {}
    new_safety = {
        **prev, "verdict": body.verdict,
        "override_by":       admin["user_id"],
        "override_reason": body.reason,
        "override_at":       datetime.now(timezone.utc).isoformat(),
        "raw_response":     prev.get("raw_response"),
    }
    new_status = ("approved" if body.verdict == "approved"
                       else ("rejected" if body.verdict == "rejected"
                                else "pending_review"))
    await db.ad_creatives.update_one(
        {"id": creative_id},
        {"$set": {"brand_safety_check": new_safety, "status": new_status}})
    await db.admin_audit_log.insert_one({
        "action": "creative_override_safety", "actor": admin["user_id"],
        "creative_id": creative_id, "verdict": body.verdict,
        "reason": body.reason, "ts": datetime.now(timezone.utc),
    })
    return {"ok": True, "verdict": body.verdict, "status": new_status}


# ─── Phase 18b — Advertiser analytics dashboard ────────────────────
@admin_advertiser_router.get("/analytics")
async def advertiser_analytics(request: Request, days: int = 30,
                                                      admin: dict = Depends(require_admin)):
    from services.telemetry import aggregate_advertiser_kpis
    db = request.app.state.db
    return await aggregate_advertiser_kpis(db, days=days)


# ─── Phase 18b polish — admin diagnostic for pick_ad_for_user ────
class PickDebugBody(BaseModel):
    user_id:           str
    channel_slug:  str
    market:             Optional[str] = "dubai"
    now:                  Optional[str] = None  # ISO8601


@admin_advertiser_router.post("/ads/pick-debug")
async def pick_debug(body: PickDebugBody, request: Request,
                                  admin: dict = Depends(require_admin)):
    """Diagnostic-only ad-pick runner.  Returns the same payload that
    `pick_ad_for_user` would emit during the real radio queue + a meta
    block explaining why a particular candidate was selected (or not)."""
    from datetime import datetime as _dt
    from services.advertisers import (pick_ad_for_user,
                                                              _find_exclusive_takeover,
                                                              FREQUENCY_CAP_MIN, _now)
    db   = request.app.state.db
    now = (_dt.fromisoformat(body.now.replace("Z", "+00:00"))
              if body.now else _now())
    iso_now = now.isoformat()

    takeover_camp = await _find_exclusive_takeover(
        db, channel_slug=body.channel_slug, market=body.market, now=now)

    # Freq-cap probe.
    from datetime import timedelta
    recent = await db.ad_serves.find_one({
        "user_id":    body.user_id,
        "served_at": {"$gte": now - timedelta(minutes=FREQUENCY_CAP_MIN)}})
    freq_cap_blocked = recent is not None

    candidates = await db.ad_campaigns.count_documents({
        "status": "active",
        "$or": [{"start_date": None}, {"start_date": {"$lte": iso_now}}],
    })

    # Phase 18c — also surface WHICH cap blocked the pick (when blocked).
    freq_cap_reason = None
    if freq_cap_blocked:
        freq_cap_reason = "min_interval"
    else:
        # Probe per-campaign reasons so operators see the first cap that fires.
        from services.freq_caps import check_caps
        async for c in db.ad_campaigns.find({"status": "active"}, {"id": 1,
                                                                                              "advertiser_id": 1,
                                                                                              "frequency_caps": 1,
                                                                                              "_id": 0}):
            r = await check_caps(db, user_id=body.user_id, campaign=c,
                                          channel_slug=body.channel_slug, now=now)
            if r["blocked"]:
                freq_cap_reason = r["reason"]
                break

    serve = None
    if not freq_cap_blocked:
        serve = await pick_ad_for_user(
            db, user_id=body.user_id, channel_slug=body.channel_slug,
            market=body.market, now=now)

    adv_balance_after = None
    if serve and serve.get("serve"):
        # Phase 18d — programmatic envelopes (GAM/OpenRTB mock backfills)
        # have NO advertiser_id, so guard with .get(...) and skip the
        # balance lookup for them.
        adv_id = (serve["serve"] or {}).get("advertiser_id")
        if adv_id:
            adv = await db.advertisers.find_one(
                {"id": adv_id},
                {"account_balance_usd": 1, "_id": 0})
            adv_balance_after = (adv or {}).get("account_balance_usd")

    return {
        "result": serve,
        "meta":   {
            "was_takeover_window_active": takeover_camp is not None,
            "exclusive": bool((takeover_camp or {})
                                          .get("takeover_config", {}).get("exclusive")),
            "takeover_campaign_id":  (takeover_camp or {}).get("id"),
            "candidate_count_before_freq_cap": candidates,
            "freq_cap_blocked":      freq_cap_blocked,
            "freq_cap_reason":       freq_cap_reason,
            "balance_after_serve":   adv_balance_after,
            "now":                       iso_now,
        }
    }

