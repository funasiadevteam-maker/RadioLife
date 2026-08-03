"""Phase 42-E2.4 — Dynamic OG card endpoint.

`GET /api/og-card/<entity_type>/<entity_id>` resolves the entity,
renders an OG image via og_card_generator, and returns the PNG.

Entity types:
    station                  → live + community radio station (slug).
    news_article          → news article (news_id).
    predict_win_campaign  → Predict & Win campaign (campaign_id).
    persona                  → AI persona (persona_id).
    game                      → Predict & Win / Play & Win campaign (campaign_id).
    passport                  → user passport ref (user_id or `me`).
    wallet                      → user wallet (user_id or `me`).
    feature_tile          → home cinematic tile (tile_id).
    home                      → generic BigFM home (no entity needed).

Anonymous-safe.  Caches PNGs at the disk level via og_card_generator.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

from fastapi import APIRouter, Response, Request

from services.og_card_generator import generate_share_card

log = logging.getLogger("bigfm.og_card_routes")
router = APIRouter(prefix="/api/og-card", tags=["og-card"])


# Resolve { title, subtitle, artwork_url, accent } from an entity.
async def _resolve_entity(db, entity_type: str, entity_id: str
                                      ) -> Optional[dict[str, Any]]:
    et = entity_type.lower()

    if et == "home":
        return {"title": "BigFM",
                      "subtitle": "Personalized radio, news, games and rewards.",
                      "artwork_url": None,
                      "accent": "default"}

    if et == "station":
        # Try BigFM AI channel first, then community/imported station.
        ch = await db.channels.find_one({"slug": entity_id})
        if ch:
            return {"title": ch.get("title") or ch.get("name") or entity_id,
                          "subtitle": ch.get("tagline")
                                              or ch.get("subtitle")
                                              or "Listen live on BigFM",
                          "artwork_url": (ch.get("thumbnail_url")
                                                          or ch.get("cover_image_url")),
                          "accent": ch.get("accent") or "electric"}
        st = await db.community_radio_stations.find_one({"slug": entity_id})
        if st:
            return {"title": st.get("name") or entity_id,
                          "subtitle": st.get("tagline")
                                              or st.get("description")
                                              or "Live on BigFM Community Radio",
                          "artwork_url": st.get("cover_image_url")
                                                          or st.get("artwork_url"),
                          "accent": st.get("accent") or "magenta"}
        return None

    if et == "news_article":
        n = await db.news_articles.find_one({"news_id": entity_id})
        if not n:
            return None
        return {"title": n.get("title") or "Local headline",
                      "subtitle": n.get("source_name") or n.get("source_id") or "BigFM News",
                      "artwork_url": n.get("image_url"),
                      "accent": "cyan"}

    if et in ("predict_win_campaign", "game"):
        c = await db.predict_win_campaigns.find_one({"campaign_id": entity_id})
        if c:
            top = c.get("top_prize_title") or "rewards"
            return {"title": c.get("title") or "Predict & Win",
                          "subtitle": f"Play now and win {top}",
                          "artwork_url": c.get("hero_image_url")
                                                          or c.get("cover_image_url"),
                          "accent": "magenta"}
        # Play & Win games share the same store.
        return None

    if et == "persona":
        p = await db.personas.find_one({"persona_id": entity_id})
        if not p:
            return None
        archetype = (p.get("archetype") or "").replace("_", " ")
        return {"title": p.get("display_name") or "BigFM Persona",
                      "subtitle": f"Chat with {archetype} on BigFM"
                                          if archetype else "Chat on BigFM",
                      "artwork_url": p.get("avatar_url"),
                      "accent": "violet"}

    if et == "feature_tile":
        t = await db.feature_tiles_config.find_one({"tile_id": entity_id})
        if not t:
            return None
        return {"title": t.get("title") or "Explore BigFM",
                      "subtitle": t.get("tagline") or "Tap to explore",
                      "artwork_url": t.get("image_url"),
                      "accent": t.get("accent") or "default"}

    if et == "passport":
        return {"title": "My BigFM Passport",
                      "subtitle": "Collect cities. Earn stamps. Climb the leaderboard.",
                      "artwork_url": None,
                      "accent": "rose"}

    if et == "wallet":
        return {"title": "My BigFM Wallet",
                      "subtitle": "Listen more. Earn more. Cash in rewards.",
                      "artwork_url": None,
                      "accent": "gold"}

    return None


@router.get("/health")
async def og_card_health() -> dict:
    return {"ok": True, "ts": "alive"}


@router.get("/{entity_type}/{entity_id}")
async def og_card(entity_type: str, entity_id: str, request: Request) -> Response:
    db = request.app.state.db
    ctx = await _resolve_entity(db, entity_type, entity_id)
    if ctx is None:
        # Render a graceful generic BigFM card instead of 404 so social
        # crawlers always get a valid preview.
        ctx = {"title": "BigFM",
                  "subtitle": "Personalized radio for the diaspora.",
                  "artwork_url": None,
                  "accent": "default"}
    raw = generate_share_card(
        title=str(ctx["title"])[:80],
        subtitle=str(ctx["subtitle"])[:140],
        artwork_url=ctx.get("artwork_url"),
        accent=str(ctx.get("accent") or "default"))
    return Response(content=raw, media_type="image/png",
                          headers={"Cache-Control": "public, max-age=86400, "
                                                                "stale-while-revalidate=604800"})
