"""Phase 18c — admin + advertiser routes for pacing, freq-cap, attribution,
hygiene, and engagement-push diagnostics."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel

from auth import require_admin, current_user

phase18c_router = APIRouter(prefix="/api", tags=["phase18c"])


# ────────── Pacing status per campaign ──────────
@phase18c_router.get("/advertiser/{advertiser_id}/campaigns/{campaign_id}/pacing")
async def get_pacing(advertiser_id: str, campaign_id: str, request: Request):
    db = request.app.state.db
    c = await db.ad_campaigns.find_one(
        {"id": campaign_id, "advertiser_id": advertiser_id})
    if not c:
        raise HTTPException(404, "campaign not found")
    from services.pacing import pacing_status
    return pacing_status(c)


# ────────── Attribution funnel per campaign ──────────
@phase18c_router.get("/advertiser/{advertiser_id}/campaigns/{campaign_id}/attribution")
async def attribution(advertiser_id: str, campaign_id: str, request: Request):
    db = request.app.state.db
    # Phase 18d — `attribution_window_hours` per-campaign cap.  Defaults to
    # 24h. Filters coupon saves/redemptions to only those whose `saved_at`
    # (or `claimed_at`) fell within `window_hours` of the matched serve.
    c = await db.ad_campaigns.find_one(
        {"id": campaign_id},
        {"spend_usd": 1, "attribution_window_hours": 1, "_id": 0}) or {}
    spend = float(c.get("spend_usd") or 0.0)
    window_h = int(c.get("attribution_window_hours") or 24)

    impressions = await db.ad_serve_events.count_documents(
        {"campaign_id": campaign_id})

    async def _within_window(coupons_query):
        """Count coupons matching `coupons_query` whose tied serve fired
        within `window_h` hours of save/claim time."""
        n = 0
        async for cp in db.coupons.find(coupons_query,
                                                                  {"attribution_serve_id": 1,
                                                                    "saved_at": 1, "claimed_at": 1, "_id": 0}):
            sid = cp.get("attribution_serve_id")
            ts  = cp.get("saved_at") or cp.get("claimed_at")
            if not sid or not ts:
                # Pre-window-cap coupon: count it (legacy data).
                n += 1
                continue
            evt = await db.ad_serve_events.find_one(
                {"$or": [{"id": sid}, {"serve_id": sid}]},
                {"served_at": 1, "_id": 0})
            if not evt or not evt.get("served_at"):
                n += 1
                continue
            try:
                delta = (ts - evt["served_at"]).total_seconds() / 3600.0
            except Exception:
                n += 1
                continue
            if delta <= window_h:
                n += 1
        return n

    saves         = await _within_window(
        {"attribution_campaign_id": campaign_id})
    redemptions = await _within_window(
        {"attribution_campaign_id": campaign_id, "status": "redeemed"})
    checkins      = (await db.checkins.count_documents(
        {"attribution_campaign_id": campaign_id})
        if "checkins" in await db.list_collection_names() else 0)

    def _r(n, d): return round(n / d, 3) if d else 0.0
    return {
        "impressions":     impressions,
        "coupon_saves":  saves,
        "redemptions":    redemptions,
        "checkins":          checkins,
        "save_rate":        _r(saves, impressions),
        "redeem_rate":   _r(redemptions, saves),
        "cpc_estimate":  _r(spend, saves) if saves else 0.0,
        "cost_per_save":  _r(spend, saves),
        "cost_per_redeem": _r(spend, redemptions),
        "attribution_window_hours": window_h,
    }


# ────────── Frequency cap report ──────────
@phase18c_router.get("/admin/advertiser/freq-cap-report")
async def freq_cap_report(request: Request, user_id: str,
                                                channel_slug: str = "morning_masala",
                                                market: str = "dubai",
                                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    from services.freq_caps import check_caps
    out = []
    cur = db.ad_campaigns.find({"status": "active"})
    async for c in cur:
        r = await check_caps(db, user_id=user_id, campaign=c,
                                      channel_slug=channel_slug)
        out.append({"campaign_id": c["id"], "name": c.get("name"),
                          "advertiser_id": c["advertiser_id"],
                          "status": "blocked_" + r["reason"] if r["blocked"]
                                      else "ok",
                          "caps": r["caps"]})
    return {"user_id": user_id, "channel_slug": channel_slug,
              "items": out}


# ────────── Pacing health panel ──────────
@phase18c_router.get("/admin/advertiser/pacing-health")
async def pacing_health(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    from services.pacing import pacing_status
    ahead, behind = [], []
    cur = db.ad_campaigns.find({"status": "active"})
    async for c in cur:
        p = pacing_status(c)
        row = {"campaign_id": c["id"], "name": c.get("name"),
                  "advertiser_id": c["advertiser_id"],
                  "spend_progress": p["spend_progress"],
                  "time_progress":   p["time_progress"],
                  "projected_eob": p["projected_eob"],
                  "status": p["status"]}
        if p["status"] == "ahead":  ahead.append(row)
        if p["status"] == "behind": behind.append(row)
    return {"ahead": ahead, "behind": behind}


# ────────── Hygiene admin endpoints ──────────
@phase18c_router.get("/admin/hygiene/last-run")
async def hygiene_last_run(request: Request,
                                              admin: dict = Depends(require_admin)):
    from services.hygiene18c import last_run
    return await last_run(request.app.state.db) or {}


@phase18c_router.post("/admin/hygiene/run-now")
async def hygiene_run_now(request: Request,
                                                admin: dict = Depends(require_admin),
                                                ttl_hours: int = 24,
                                                dry_run: bool = False):
    from services.hygiene18c import tick_daily
    return await tick_daily(request.app.state.db,
                                          ttl_hours=ttl_hours, dry_run=dry_run)


# Phase 36c.5 — Tigris orphan pruner (admin trigger).
@phase18c_router.post("/admin/hygiene/tigris-orphans")
async def hygiene_tigris_orphans(request: Request,
                                                admin: dict = Depends(require_admin),
                                                ttl_hours: int = 168,
                                                dry_run: bool = True):
    from services.hygiene18c import tick_tigris_orphans
    return await tick_tigris_orphans(request.app.state.db,
                                                          ttl_hours=ttl_hours, dry_run=dry_run)


# Phase 36c.5 hardening — local recording-dir orphan sweep (admin trigger).
@phase18c_router.post("/admin/hygiene/local-recording-orphans")
async def hygiene_local_recording_orphans(request: Request,
                                                admin: dict = Depends(require_admin),
                                                dry_run: bool = True):
    from services.hygiene18c import tick_local_recording_orphans
    return await tick_local_recording_orphans(
        request.app.state.db, dry_run=dry_run)


# ────────── Engagement push (tick + subscribe) ──────────
class PushSubscribe(BaseModel):
    endpoint: str
    keys:        dict


@phase18c_router.post("/me/push/subscribe")
async def push_subscribe(body: PushSubscribe, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"push_enabled": True,
                      "push_subscription": {"endpoint": body.endpoint,
                                                          "keys": body.keys}}})
    return {"ok": True}


@phase18c_router.post("/admin/push/tick-now")
async def push_tick_now(request: Request,
                                            admin: dict = Depends(require_admin)):
    from services.engagement_push import tick
    return await tick(request.app.state.db)
