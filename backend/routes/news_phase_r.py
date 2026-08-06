"""Phase R — News Radio Expansion routes.

Admin-curated news layer.  Uses `require_admin` for /api/admin/news/*
and `current_user`-less public access for /api/news/*.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import require_admin
from services import news_phase_r_service as svc
from services import news_api_provider as _newsapi
from services import geo as _geo_svc

router = APIRouter(tags=["phase-r-news"])


def _live_article_to_public(a: Dict[str, Any], is_breaking: bool = False) -> Dict[str, Any]:
    """Map a NewsAPI-normalised article → the public headline shape the
    web + mobile clients expect (headline_text / summary_text / etc.)."""
    cats = a.get("categories") or []
    category = (cats[0] if cats else None) or "features"
    return {
        "headline_id":  a.get("news_id"),
        "id":           a.get("news_id"),
        "headline_text": (a.get("title") or "").strip(),
        "summary_text": (a.get("description") or None),
        "category":     category,
        "source_name":  a.get("source_name") or "NewsAPI",
        "source_url":   a.get("link") or None,
        "image_url":    a.get("image_url") or None,
        "published_at": a.get("pubDate") or None,
        "is_breaking":  is_breaking,
        "market":       a.get("market"),
        "provider":     "newsapi",
    }


async def _fetch_live_headlines(request: Request, category: Optional[str],
                                limit: int,
                                market_override: Optional[str] = None,
                                scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fallback source when the admin-curated pool is empty.  Resolves the
    requester's location from geo/IP and pulls the live NewsAPI feed.
      • scope=local (default) → the resolved city-level market
      • scope=national        → the resolved country code
      • market_override       → explicit market, wins over scope"""
    if not (_newsapi.is_preferred() and _newsapi.enabled()):
        return []
    market = market_override
    if not market:
        try:
            resolved = await _geo_svc.resolve_for_user(request, None,
                                                       request.app.state.db)
            if scope == "national":
                market = resolved.get("country") or resolved.get("market")
            else:
                market = resolved.get("market") or resolved.get("country")
        except Exception:
            market = None
    try:
        arts = await _newsapi.fetch_top_headlines(
            market=market, category=category, page_size=max(limit, 10))
        if not arts and market:
            arts = await _newsapi.fetch_top_headlines(
                market=None, category=category, page_size=max(limit, 10))
        return arts or []
    except Exception:
        return []


# ─── request models ──────────────────────────────────────
class HeadlineCreateBody(BaseModel):
    headline_text:    str
    summary_text:     Optional[str] = None
    category:         Optional[str] = "features"
    region_code:      Optional[str] = None
    channel_id:       Optional[str] = None
    source_name:      Optional[str] = None
    source_url:       Optional[str] = None
    image_url:        Optional[str] = None
    priority:         Optional[int] = 5
    auto_summarize:   Optional[bool] = True


class BulkHeadlineRow(BaseModel):
    headline_text:    str
    summary_text:     Optional[str] = None
    category:         Optional[str] = "features"
    region_code:      Optional[str] = None
    channel_id:       Optional[str] = None
    source_name:      Optional[str] = None
    source_url:       Optional[str] = None
    image_url:        Optional[str] = None
    priority:         Optional[int] = 5


class BulkHeadlineBody(BaseModel):
    rows:           List[BulkHeadlineRow] = Field(default_factory=list)
    auto_summarize: bool = True


class HeadlinePatchBody(BaseModel):
    headline_text:  Optional[str] = None
    summary_text:   Optional[str] = None
    category:       Optional[str] = None
    region_code:    Optional[str] = None
    channel_id:     Optional[str] = None
    source_name:    Optional[str] = None
    source_url:     Optional[str] = None
    image_url:      Optional[str] = None
    priority:       Optional[int] = None
    status:         Optional[str] = None
    is_breaking:    Optional[bool] = None


class ChannelCreateBody(BaseModel):
    name:             str
    region_code:      Optional[str] = None
    city:             Optional[str] = None
    language:         Optional[str] = "en"
    tagline:          Optional[str] = None
    cover_image_url:  Optional[str] = None
    station_id:       Optional[str] = None
    program_schedule: Optional[List[Dict[str, Any]]] = None


class ChannelPatchBody(BaseModel):
    name:             Optional[str] = None
    region_code:      Optional[str] = None
    city:             Optional[str] = None
    language:         Optional[str] = None
    tagline:          Optional[str] = None
    cover_image_url:  Optional[str] = None
    station_id:       Optional[str] = None
    program_schedule: Optional[List[Dict[str, Any]]] = None
    live:             Optional[bool] = None
    status:           Optional[str] = None


class BulletinGenBody(BaseModel):
    top_n: Optional[int] = 5


# ─── admin: headlines ──────────────────────────────────
@router.post("/api/admin/news/headlines")
async def admin_create_headline(body: HeadlineCreateBody, request: Request,
                                 user: dict = Depends(require_admin)):
    try:
        return await svc.create_headline(
            request.app.state.db,
            headline_text=body.headline_text,
            summary_text=body.summary_text,
            category=body.category or "features",
            region_code=body.region_code,
            channel_id=body.channel_id,
            source_name=body.source_name,
            source_url=body.source_url,
            image_url=body.image_url,
            priority=body.priority or 5,
            created_by_user_id=user["user_id"],
            auto_summarize=bool(body.auto_summarize),
        )
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})


@router.post("/api/admin/news/headlines/bulk")
async def admin_bulk_headlines(body: BulkHeadlineBody, request: Request,
                                user: dict = Depends(require_admin)):
    return await svc.bulk_create_headlines(
        request.app.state.db,
        rows=[r.model_dump() for r in body.rows],
        auto_summarize=body.auto_summarize,
        created_by_user_id=user["user_id"])


@router.get("/api/admin/news/headlines")
async def admin_list_headlines(request: Request,
                                region_code: Optional[str] = None,
                                category:    Optional[str] = None,
                                status:      Optional[str] = None,
                                limit: int = Query(100, ge=1, le=500),
                                user: dict = Depends(require_admin)):
    rows = await svc.list_headlines(request.app.state.db,
                                     region_code=region_code,
                                     category=category, status=status,
                                     limit=limit)
    return {"items": rows, "total": len(rows)}


@router.patch("/api/admin/news/headlines/{headline_id}")
async def admin_patch_headline(headline_id: str, body: HeadlinePatchBody,
                                request: Request,
                                user: dict = Depends(require_admin)):
    try:
        return await svc.update_headline(
            request.app.state.db, headline_id,
            body.model_dump(exclude_none=True))
    except ValueError as e:
        code = str(e)
        raise HTTPException(404 if code == "headline_not_found" else 400,
                            {"code": code})


@router.post("/api/admin/news/headlines/{headline_id}/promote-breaking")
async def admin_promote_breaking(headline_id: str, request: Request,
                                  user: dict = Depends(require_admin)):
    try:
        return await svc.promote_breaking(request.app.state.db, headline_id)
    except ValueError as e:
        raise HTTPException(404, {"code": str(e)})


@router.delete("/api/admin/news/headlines/{headline_id}")
async def admin_delete_headline(headline_id: str, request: Request,
                                 user: dict = Depends(require_admin)):
    try:
        return await svc.soft_delete_headline(request.app.state.db,
                                               headline_id)
    except ValueError as e:
        raise HTTPException(404, {"code": str(e)})


# ─── admin: channels ──────────────────────────────────
@router.post("/api/admin/news/channels")
async def admin_create_channel(body: ChannelCreateBody, request: Request,
                                user: dict = Depends(require_admin)):
    return await svc.create_channel(
        request.app.state.db,
        name=body.name,
        region_code=body.region_code, city=body.city,
        language=body.language or "en",
        tagline=body.tagline, cover_image_url=body.cover_image_url,
        station_id=body.station_id,
        program_schedule=body.program_schedule,
        created_by_user_id=user["user_id"])


@router.patch("/api/admin/news/channels/{channel_id}")
async def admin_patch_channel(channel_id: str, body: ChannelPatchBody,
                                request: Request,
                                user: dict = Depends(require_admin)):
    try:
        return await svc.update_channel(request.app.state.db, channel_id,
                                         body.model_dump(exclude_none=True))
    except ValueError as e:
        code = str(e)
        raise HTTPException(404 if code == "channel_not_found" else 400,
                            {"code": code})


@router.get("/api/admin/news/channels")
async def admin_list_channels(request: Request,
                               user: dict = Depends(require_admin)):
    # Simple pass-through; admin sees all statuses.
    db = request.app.state.db
    rows = [d async for d in db.news_channels.find({}, {"_id": 0}).limit(200)]
    return {"items": rows, "total": len(rows)}


# ─── admin: bulletins ────────────────────────────────
@router.post("/api/admin/news/channels/{channel_id}/bulletins/generate")
async def admin_generate_bulletin(channel_id: str, body: BulletinGenBody,
                                   request: Request,
                                   user: dict = Depends(require_admin)):
    try:
        return await svc.generate_bulletin(
            request.app.state.db, channel_id=channel_id,
            top_n=int(body.top_n or 5),
            generated_by_user_id=user["user_id"])
    except ValueError as e:
        code = str(e)
        status = 404 if code == "channel_not_found" else 400
        raise HTTPException(status, {"code": code})


@router.post("/api/admin/news/bulletins/{bulletin_id}/publish")
async def admin_publish_bulletin(bulletin_id: str, request: Request,
                                  user: dict = Depends(require_admin)):
    try:
        return await svc.publish_bulletin(request.app.state.db, bulletin_id)
    except ValueError as e:
        raise HTTPException(404, {"code": str(e)})


@router.get("/api/admin/news/bulletins")
async def admin_list_bulletins(request: Request,
                                channel_id: Optional[str] = None,
                                status:     Optional[str] = None,
                                limit: int = Query(50, ge=1, le=200),
                                user: dict = Depends(require_admin)):
    rows = await svc.list_bulletins_admin(
        request.app.state.db, channel_id=channel_id,
        status=status, limit=limit)
    return {"items": rows, "total": len(rows)}


# ─── public listener routes ─────────────────────────
@router.get("/api/news/channels")
async def public_list_channels(request: Request,
                                region_code: Optional[str] = None,
                                language:    Optional[str] = None,
                                limit: int = Query(50, ge=1, le=200)):
    rows = await svc.list_channels_public(
        request.app.state.db, region_code=region_code,
        language=language, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.get("/api/news/channels/{channel_id}")
async def public_channel_detail(channel_id: str, request: Request):
    try:
        return await svc.get_channel_public(request.app.state.db, channel_id)
    except ValueError as e:
        raise HTTPException(404, {"code": str(e)})


@router.get("/api/news/headlines")
async def public_headlines(request: Request,
                            region_code: Optional[str] = None,
                            category:    Optional[str] = None,
                            scope:       Optional[str] = None,
                            market:      Optional[str] = None,
                            limit: int = Query(50, ge=1, le=200)):
    rows = await svc.list_public_headlines(
        request.app.state.db, region_code=region_code,
        category=category, limit=limit)
    # Fallback to the live NewsAPI feed when no admin-curated headlines
    # exist for this filter, so the app always shows fresh news.
    #   scope=local    → use the caller's resolved geo market
    #   scope=national → drop the market for broad national/world coverage
    if not rows:
        override = market
        live = await _fetch_live_headlines(request, category, limit,
                                           market_override=override, scope=scope)
        rows = [_live_article_to_public(a) for a in live][:limit]
    return {"items": rows, "total": len(rows)}


@router.get("/api/news/headlines/breaking")
async def public_breaking(request: Request,
                           region_code: Optional[str] = None,
                           limit: int = Query(5, ge=1, le=20)):
    rows = await svc.get_breaking_headlines(
        request.app.state.db, region_code=region_code, limit=limit)
    # Fallback: surface the freshest live headlines as "breaking" when the
    # curated breaking pool is empty.
    if not rows:
        live = await _fetch_live_headlines(request, None, limit)
        rows = [_live_article_to_public(a, is_breaking=True)
                for a in live][:limit]
    return {"items": rows, "total": len(rows)}


@router.get("/api/news/bulletins/next")
async def public_next_bulletin(channel_id: str, request: Request):
    r = await svc.get_next_bulletin(request.app.state.db, channel_id)
    return {"bulletin": r}


__all__ = ["router"]
