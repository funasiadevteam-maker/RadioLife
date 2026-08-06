"""Promoted / sponsored radio stations.

Lets a radio station pay to be surfaced first in the Explore + Home rails
with a small "Sponsored" tag.  Supports two pricing models:

    • CPM — billed per 1,000 impressions (cpm_bid_cents / 1000 per view)
    • CPC — billed per click (cpc_bid_cents per click)

Spend accrues on the promo doc (`spend_cents`).  Real wallet settlement is
out of scope for this MVP — the accrual is the source of truth the billing
layer can reconcile against.

Endpoints:
    GET  /api/promoted/stations?limit=          — active promos as station cards
    POST /api/promoted/{promo_id}/impression     — track a view  (CPM accrual)
    POST /api/promoted/{promo_id}/click          — track a click (CPC accrual)
    POST /api/promoted                            — admin: create a promo
    GET  /api/promoted/admin                      — admin: list all promos
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import current_user_optional, require_admin
from routes.radio_unified import (
    _ai_channel_to_card, _community_to_card, _imported_to_card,
)

router = APIRouter(prefix="/api/promoted", tags=["promoted-stations"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PromoCreateBody(BaseModel):
    station_id:      str
    sponsor_name:    Optional[str] = None
    pricing_model:   str = "cpm"            # "cpm" | "cpc"
    cpm_bid_cents:   Optional[int] = 500    # $5 CPM default
    cpc_bid_cents:   Optional[int] = 25     # $0.25 CPC default
    active:          bool = True


async def _resolve_card(db, station_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a promo's station_id to a unified card across all sources."""
    sid = str(station_id or "")
    # Imported live station (Radio Browser tier).
    s = await db.imported_radio_stations.find_one({"id": sid})
    if s:
        return _imported_to_card(s)
    # Community / creator station.
    if sid.startswith("cmn_"):
        c = await db.community_radio_stations.find_one(
            {"station_id": sid.replace("cmn_", "")}) \
            or await db.community_radio_stations.find_one({"station_id": sid})
        if c:
            return _community_to_card(c)
    # BigFM AI channel (matched by slug).
    ch = await db.channels.find_one({"slug": sid}) \
        or await db.channels.find_one({"slug": sid.replace("ai_", "")})
    if ch:
        return _ai_channel_to_card(ch, None)
    return None


async def ensure_promoted_seed(db) -> int:
    """Seed a couple of promos from flagship / top-voted imported stations
    so the Sponsored rail is populated for the demo.  Idempotent — only
    runs when the collection is empty."""
    n = await db.promoted_stations.count_documents({})
    if n > 0:
        return 0
    seeds: List[Dict[str, Any]] = []
    # Prefer flagship stations, then fall back to top-voted imported.
    async for s in db.imported_radio_stations.find(
            {"is_flagship": True}).limit(2):
        seeds.append(s)
    if len(seeds) < 2:
        async for s in db.imported_radio_stations.find(
                {"active": True}).sort([("votes", -1)]).limit(3):
            if all(x.get("id") != s.get("id") for x in seeds):
                seeds.append(s)
            if len(seeds) >= 3:
                break
    created = 0
    for i, s in enumerate(seeds[:3]):
        doc = {
            "promo_id":      f"promo_{uuid.uuid4().hex[:12]}",
            "station_id":    s.get("id"),
            "sponsor_name":  s.get("name") or "Sponsored Station",
            "pricing_model": "cpm" if i % 2 == 0 else "cpc",
            "cpm_bid_cents": 500,
            "cpc_bid_cents": 25,
            "active":        True,
            "impressions":   0,
            "clicks":        0,
            "spend_cents":   0,
            "created_at":    _now(),
            "updated_at":    _now(),
        }
        await db.promoted_stations.insert_one(doc)
        created += 1
    return created


@router.get("/stations")
async def list_promoted_stations(
    request: Request,
    limit: int = Query(6, ge=1, le=20),
    user: Optional[dict] = Depends(current_user_optional),
):
    """Active promoted stations as unified cards, ranked by bid.  Each card
    carries `is_sponsored`, `promo_id`, `pricing_model` and `sponsor_name`."""
    db = request.app.state.db
    await ensure_promoted_seed(db)
    out: List[Dict[str, Any]] = []
    cur = db.promoted_stations.find({"active": True}).sort(
        [("cpm_bid_cents", -1), ("cpc_bid_cents", -1)]).limit(limit * 2)
    async for p in cur:
        card = await _resolve_card(db, p.get("station_id"))
        if not card:
            continue
        card = {**card}
        card["is_sponsored"] = True
        card["promo_id"] = p.get("promo_id")
        card["pricing_model"] = p.get("pricing_model") or "cpm"
        card["sponsor_name"] = p.get("sponsor_name") or card.get("name")
        out.append(card)
        if len(out) >= limit:
            break
    return {"items": out, "total": len(out)}


@router.post("/{promo_id}/impression")
async def track_impression(promo_id: str, request: Request):
    """CPM accrual — one view."""
    db = request.app.state.db
    p = await db.promoted_stations.find_one({"promo_id": promo_id})
    if not p:
        raise HTTPException(404, "promo not found")
    accrue = 0
    if (p.get("pricing_model") or "cpm") == "cpm":
        accrue = max(0, int(p.get("cpm_bid_cents") or 0)) // 1000
    await db.promoted_stations.update_one(
        {"promo_id": promo_id},
        {"$inc": {"impressions": 1, "spend_cents": accrue},
         "$set": {"updated_at": _now()}})
    return {"ok": True, "promo_id": promo_id, "accrued_cents": accrue}


@router.post("/{promo_id}/click")
async def track_click(promo_id: str, request: Request):
    """CPC accrual — one click."""
    db = request.app.state.db
    p = await db.promoted_stations.find_one({"promo_id": promo_id})
    if not p:
        raise HTTPException(404, "promo not found")
    accrue = 0
    if (p.get("pricing_model") or "cpm") == "cpc":
        accrue = max(0, int(p.get("cpc_bid_cents") or 0))
    await db.promoted_stations.update_one(
        {"promo_id": promo_id},
        {"$inc": {"clicks": 1, "spend_cents": accrue},
         "$set": {"updated_at": _now()}})
    return {"ok": True, "promo_id": promo_id, "accrued_cents": accrue}


@router.post("")
async def create_promo(body: PromoCreateBody, request: Request,
                       _admin=Depends(require_admin)):
    db = request.app.state.db
    card = await _resolve_card(db, body.station_id)
    if not card:
        raise HTTPException(400, "station_id does not resolve to a station")
    doc = {
        "promo_id":      f"promo_{uuid.uuid4().hex[:12]}",
        "station_id":    body.station_id,
        "sponsor_name":  body.sponsor_name or card.get("name"),
        "pricing_model": body.pricing_model if body.pricing_model in ("cpm", "cpc") else "cpm",
        "cpm_bid_cents": int(body.cpm_bid_cents or 0),
        "cpc_bid_cents": int(body.cpc_bid_cents or 0),
        "active":        bool(body.active),
        "impressions":   0,
        "clicks":        0,
        "spend_cents":   0,
        "created_at":    _now(),
        "updated_at":    _now(),
    }
    await db.promoted_stations.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/admin")
async def admin_list_promos(request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    out: List[Dict[str, Any]] = []
    async for p in db.promoted_stations.find({}).sort("created_at", -1):
        p.pop("_id", None)
        out.append(p)
    return {"items": out, "total": len(out)}
