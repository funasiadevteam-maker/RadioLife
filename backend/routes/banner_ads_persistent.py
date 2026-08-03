"""Phase 42-E1 — Persistent banner-ad slots (NEW system).

Distinct from the legacy `/api/ads/banner/*` 12-slot inventory system
(routes/banner_ads.py).  This module powers the spec's `placement`
taxonomy and the new request/impression/click endpoints.

Mounted at `/api/banner-ads/*` (dash-separated — note the difference).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from services.banner_ad_provider import (
    request_banner, log_impression, log_click, VALID_PLACEMENTS,
)

router = APIRouter(prefix="/api/banner-ads", tags=["banner-ads-v2"])
log = logging.getLogger("bigfm.banner_ads.persistent")


class _Geo(BaseModel):
    city:        Optional[str] = None
    country: Optional[str] = None


class BannerRequestBody(BaseModel):
    placement: str
    geo:                Optional[_Geo] = None
    channel:    Optional[str] = None


class BannerImpressionBody(BaseModel):
    impression_token: str
    placement:                Optional[str] = None


class BannerClickBody(BaseModel):
    impression_token: str


async def _current_user_or_none(request: Request) -> Optional[dict]:
    try:
        from auth import current_user
        return await current_user(request)
    except Exception:
        return None


@router.post("/request")
async def request_banner_ad(request: Request, body: BannerRequestBody):
    if body.placement not in VALID_PLACEMENTS:
        return {"has_ad": False, "reason": "bad_placement"}
    user = await _current_user_or_none(request)
    user_id = user.get("user_id") if user else None
    db = request.app.state.db
    geo_dict = body.geo.dict() if body.geo else None
    ad = await request_banner(
        db=db, user_id=user_id, placement=body.placement,
        geo=geo_dict, channel=body.channel,
    )
    if not ad:
        return {"has_ad": False, "source": None}
    return {"has_ad": True, "ad": ad, "source": ad.get("source")}


@router.post("/impression")
async def record_impression(request: Request, body: BannerImpressionBody):
    user = await _current_user_or_none(request)
    user_id = user.get("user_id") if user else None
    db = request.app.state.db
    existing = await db.banner_ad_impressions.find_one(
        {"impression_token": body.impression_token})
    if existing:
        return {"logged": True, "duplicate": True}
    await log_impression(db=db, user_id=user_id,
                                                  ad={"impression_token": body.impression_token},
                                                  placement=body.placement or "unknown")
    return {"logged": True}


@router.post("/click")
async def record_click(request: Request, body: BannerClickBody):
    db = request.app.state.db
    ok = await log_click(db=db, impression_token=body.impression_token)
    return {"logged": ok}
