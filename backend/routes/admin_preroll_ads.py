"""Phase 42-B — Pre-roll ads admin CRUD + analytics.

Mirrors the predict_win_admin / admin_radio_import pattern.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin

router = APIRouter(prefix="/api/admin/preroll-ads",
                                    tags=["preroll-ads-admin"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_mongo(d: dict) -> dict:
    out = {**d}
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def _validate_status(s: str) -> str:
    if s not in {"draft", "active", "paused", "ended"}:
        raise HTTPException(400, {"code": "invalid_status",
                                                                    "allowed": ["draft", "active", "paused", "ended"]})
    return s


# ───────────────────────── list ───────────────────────────────
@router.get("",
                        description=("List pre-roll ads.  Filter by status. "
                                                  "Newest first."))
async def list_preroll_ads(request: Request,
                                                          status: Optional[str] = Query(None),
                                                          limit: int = Query(50, ge=1, le=200),
                                                          page: int = Query(1, ge=1),
                                                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    q: Dict[str, Any] = {}
    if status:
        q["status"] = _validate_status(status)
    skip = (page - 1) * limit
    total = await db.preroll_ads.count_documents(q)
    cur = db.preroll_ads.find(q).sort([("created_at", -1)]).skip(skip).limit(limit)
    rows = [_strip_mongo(r) async for r in cur]
    return {"items": rows, "total": total, "page": page, "limit": limit}


# ───────────────────────── create ─────────────────────────────
@router.post("",
                          description=("Create a new pre-roll ad.  Defaults to "
                                                    "status=draft so the admin can review before "
                                                    "activating."))
async def create_preroll_ad(payload: dict, request: Request,
                                                            user: dict = Depends(require_admin)):
    db = request.app.state.db
    if not (payload or {}).get("audio_url"):
        raise HTTPException(400, {"code": "audio_url_required"})
    now_iso = _now_iso()
    ad_id = f"pra_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id": ad_id, "id": ad_id,
        "advertiser_id": payload.get("advertiser_id"),
        "name": payload.get("name") or "Untitled pre-roll",
        "type": payload.get("type") or "audio",
        "audio_url": payload["audio_url"],
        "audio_duration_seconds": min(30,
                                                                              int(payload.get("audio_duration_seconds") or 15)),
        "companion_image_url": payload.get("companion_image_url"),
        "companion_cta_text": payload.get("companion_cta_text"),
        "companion_cta_url": payload.get("companion_cta_url"),
        "attached_offer_id": payload.get("attached_offer_id"),
        "advertiser_name": payload.get("advertiser_name"),
        "targeting": payload.get("targeting") or {},
        "daily_impression_cap_per_user":
            int(payload.get("daily_impression_cap_per_user") or 3),
        "hourly_impression_cap_per_user":
            int(payload.get("hourly_impression_cap_per_user") or 1),
        "start_time": payload.get("start_time") or now_iso,
        "end_time": payload.get("end_time"),
        "status": _validate_status(payload.get("status") or "draft"),
        "impressions_served": 0, "completes": 0, "skips": 0,
        "companion_clicks": 0, "wallet_saves": 0,
        "created_by": user.get("user_id"),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.preroll_ads.insert_one(doc)
    return {"ok": True, "ad": _strip_mongo(doc)}


# ───────────────────────── update ─────────────────────────────
_PATCHABLE_FIELDS = {
    "name", "type", "audio_url", "audio_duration_seconds",
    "companion_image_url", "companion_cta_text", "companion_cta_url",
    "attached_offer_id", "advertiser_name", "targeting",
    "daily_impression_cap_per_user", "hourly_impression_cap_per_user",
    "start_time", "end_time",
}


@router.patch("/{ad_id}",
                            description=("Partial update.  Status changes go through "
                                                      "/activate or /pause."))
async def patch_preroll_ad(ad_id: str, payload: dict, request: Request,
                                                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    set_fields: Dict[str, Any] = {}
    for k in _PATCHABLE_FIELDS:
        if k in payload:
            set_fields[k] = payload[k]
    if "audio_duration_seconds" in set_fields:
        set_fields["audio_duration_seconds"] = min(30,
                                                                                                              int(set_fields["audio_duration_seconds"] or 15))
    if not set_fields:
        raise HTTPException(400, {"code": "no_patchable_fields"})
    set_fields["updated_at"] = datetime.now(timezone.utc)
    r = await db.preroll_ads.find_one_and_update(
        {"id": ad_id}, {"$set": set_fields},
        return_document=True)
    if not r:
        raise HTTPException(404, {"code": "ad_not_found"})
    return {"ok": True, "ad": _strip_mongo(r)}


# ───────────────────────── status toggles ────────────────────
@router.post("/{ad_id}/activate")
async def activate_preroll_ad(ad_id: str, request: Request,
                                                                  user: dict = Depends(require_admin)):
    db = request.app.state.db
    r = await db.preroll_ads.find_one_and_update(
        {"id": ad_id},
        {"$set": {"status": "active",
                              "activated_at": datetime.now(timezone.utc),
                              "updated_at": datetime.now(timezone.utc)}},
        return_document=True)
    if not r:
        raise HTTPException(404, {"code": "ad_not_found"})
    return {"ok": True, "status": "active", "ad": _strip_mongo(r)}


@router.post("/{ad_id}/pause")
async def pause_preroll_ad(ad_id: str, request: Request,
                                                            user: dict = Depends(require_admin)):
    db = request.app.state.db
    r = await db.preroll_ads.find_one_and_update(
        {"id": ad_id},
        {"$set": {"status": "paused",
                              "paused_at": datetime.now(timezone.utc),
                              "updated_at": datetime.now(timezone.utc)}},
        return_document=True)
    if not r:
        raise HTTPException(404, {"code": "ad_not_found"})
    return {"ok": True, "status": "paused", "ad": _strip_mongo(r)}


@router.get("/analytics/by-source",
                          description=("Sub-Phase 42-B2 — pre-roll impression "
                                                    "breakdown by ad source (local vs SSP). "
                                                    "Used by the admin dashboard to track "
                                                    "fill-rate distribution after the "
                                                    "waterfall went live."))
async def preroll_analytics_by_source(
        request: Request,
        _a: dict = Depends(require_admin)):
    db = request.app.state.db
    pipe = [
        {"$group": {"_id": {"$ifNull": ["$source", "local"]},
                              "count": {"$sum": 1},
                              "completes": {"$sum": {"$cond": [
                                  {"$ne": ["$completed_at", None]}, 1, 0]}},
                              "skips": {"$sum": {"$cond": ["$skipped", 1, 0]}}}},
        {"$sort": {"count": -1}},
    ]
    total = 0
    breakdown: List[Dict[str, Any]] = []
    async for r in db.live_radio_ad_impressions.aggregate(pipe):
        src = r["_id"] or "local"
        total += r["count"]
        breakdown.append({"source": src,
                                              "impressions": r["count"],
                                              "completes": r["completes"],
                                              "skips": r["skips"]})
    return {"total_impressions": total,
                  "by_source": breakdown,
                  "ssp_provider_chain": (
                      os.environ.get("SSP_PROVIDER_CHAIN", "mocked")),
                  "ssp_mock_enabled": (
                      os.environ.get("SSP_MOCK_ENABLED", "true").lower() == "true"),
                  "ssp_mock_fill_rate": float(
                      os.environ.get("SSP_MOCK_FILL_RATE", "1.0"))}


# ───────────────────────── analytics ─────────────────────────
@router.get("/{ad_id}/analytics",
                        description=("Performance metrics for a single pre-roll. "
                                                  "Completion rate, companion CTR, wallet-save "
                                                  "rate, top stations."))
async def preroll_analytics(ad_id: str, request: Request,
                                                              user: dict = Depends(require_admin)):
    db = request.app.state.db
    ad = await db.preroll_ads.find_one({"id": ad_id})
    if not ad:
        raise HTTPException(404, {"code": "ad_not_found"})
    impressions = ad.get("impressions_served", 0) or 0
    completes = ad.get("completes", 0) or 0
    skips = ad.get("skips", 0) or 0
    companion_clicks = ad.get("companion_clicks", 0) or 0
    wallet_saves = ad.get("wallet_saves", 0) or 0
    def pct(num: int, den: int) -> float:
        return round((num / den) * 100, 2) if den else 0.0
    # Top stations.
    top_stations: List[Dict[str, Any]] = []
    cur = db.live_radio_ad_impressions.aggregate([
        {"$match": {"ad_id": ad_id}},
        {"$group": {"_id": "$station_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ])
    async for r in cur:
        top_stations.append({"station_id": r["_id"], "count": r["count"]})
    return {
        "ad_id": ad_id,
        "name": ad.get("name"),
        "status": ad.get("status"),
        "metrics": {
            "impressions_served": impressions,
            "completes": completes, "skips": skips,
            "companion_clicks": companion_clicks,
            "wallet_saves": wallet_saves,
            "completion_rate_pct": pct(completes, impressions),
            "skip_rate_pct": pct(skips, impressions),
            "companion_ctr_pct": pct(companion_clicks, impressions),
            "wallet_save_rate_pct": pct(wallet_saves, impressions),
        },
        "top_stations": top_stations,
    }
