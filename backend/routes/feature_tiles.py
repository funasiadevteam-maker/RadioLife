"""Phase 42-E2.1 — Public read endpoint for home feature tiles."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Request

log = logging.getLogger("bigfm.feature_tiles")

router = APIRouter(prefix="/api/home", tags=["home"])


@router.get("/feature-tiles",
                          description="Phase 42-E2.1 — Six home-page feature tiles + their "
                                                "AI-generated hero images.")
async def list_feature_tiles(request: Request):
    db = request.app.state.db
    out: list[dict] = []
    cur = db.feature_tiles_config.find({}).sort("sort_order", 1)
    async for r in cur:
        out.append({
            "tile_id":      r.get("tile_id"),
            "title":          r.get("title"),
            "tagline":      r.get("tagline"),
            "route":          r.get("route"),
            "cta_text":  r.get("cta_text"),
            "lucide_icon": r.get("lucide_icon"),
            "accent":      r.get("accent"),
            "sort_order": r.get("sort_order"),
            "image_url":  r.get("image_url"),
        })
    return {"count": len(out), "tiles": out}


@router.get("/local-highlights",
                          description="Phase 42-E2.1 — Three to five city-localized highlights "
                                                "for the Local strip on the home page.")
async def local_highlights(request: Request, market: str = "global",
                                                            limit: int = 5):
    """Light aggregator that combines (a) top news article for the
    market, (b) one active local offer, (c) one active Predict-&-Win
    campaign.  Best-effort — each leg degrades silently if its source
    is unavailable."""
    db = request.app.state.db
    market = (market or "").strip().lower() or "global"
    out: list[dict] = []

    # Leg 1 — top local news.
    try:
        cur = db.news_articles.find(
            {"market": market} if market != "global" else {}
        ).sort("pubDate", -1).limit(2)
        async for r in cur:
            out.append({
                "kind":          "news",
                "id":              r.get("news_id"),
                "title":          r.get("title"),
                "subtitle": r.get("source_name") or r.get("source_id"),
                "image_url": r.get("image_url"),
                "route":          f"/news/{r.get('news_id')}",
                "badge":          "LOCAL NEWS",
            })
    except Exception as e:
        log.warning("[local_highlights] news leg: %s", e)

    # Leg 2 — top active offer for the market.
    try:
        cur = db.offers.find({
            "status": "active",
            "$or": [{"market": market}, {"city": market}],
        }).sort("created_at", -1).limit(2)
        async for r in cur:
            out.append({
                "kind":          "offer",
                "id":              r.get("offer_id"),
                "title":          r.get("title"),
                "subtitle": r.get("discount_label") or "Limited time",
                "image_url": None,
                "route":          "/map",
                "badge":          "NEARBY OFFER",
            })
    except Exception as e:
        log.warning("[local_highlights] offers leg: %s", e)

    # Leg 3 — one active Predict-&-Win campaign.
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        c = await db.predict_win_campaigns.find_one({
            "status":            "active",
            "starts_at":  {"$lte": now},
            "ends_at":      {"$gte": now},
        }, sort=[("ends_at", 1)])
        if c:
            out.append({
                "kind":          "predict_win",
                "id":              c.get("campaign_id"),
                "title":          c.get("title") or "Predict & Win",
                "subtitle": c.get("question") or "Make your prediction",
                "image_url": c.get("hero_image_url"),
                "route":          "/predict-win",
                "badge":          "PREDICT & WIN",
            })
    except Exception as e:
        log.warning("[local_highlights] predict-win leg: %s", e)

    return {"market": market, "count": len(out[:limit]),
                  "items": out[:limit]}
