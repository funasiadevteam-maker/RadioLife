"""Phase 18 UI-cleanup — `/api/me/*` recommendation + favorites endpoints.

Plus a safe `/api/commute/offers_along_route` fallback that never 500s.
"""
from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import current_user
from services.recommendations import (
    autoplay_suggestion, top_channel_for_user, top_game_for_user,
    list_favorites,     add_favorite,           remove_favorite,
    _bust_listening_cache, _user_listening_profile,
    FAVORITES_CAP,
)
# Phase Ω — Deploy hardening: share the global Motor client from
# `core.db` (wrapped with a safe localhost fallback) so a bad
# `mongodb+srv://` URL can't crash uvicorn's import chain.
from core.db import db as _db

logger = logging.getLogger("bigfm.me_recs")
me_recs_router = APIRouter(tags=["me-recs"])


# ─── Autoplay suggestion ─────────────────────────────────────────────
@me_recs_router.get("/api/me/autoplay/suggestion")
async def me_autoplay_suggestion(now: Optional[str] = None,
                                                      fresh: bool = Query(False),
                                                      user: dict = Depends(current_user)):
    dt = None
    if now:
        try:
            dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "now must be ISO-8601")
    if fresh:
        _bust_listening_cache(user["user_id"])
    out = await autoplay_suggestion(_db, user_id=user["user_id"], now=dt)
    return out


# ─── Home recommendation cards ───────────────────────────────────────
@me_recs_router.get("/api/me/recommendations/top-channel")
async def me_top_channel(fresh: bool = Query(False),
                                          user: dict = Depends(current_user)):
    if fresh:
        _bust_listening_cache(user["user_id"])
    out = await top_channel_for_user(_db, user_id=user["user_id"])
    if not out:
        return {"channel": None}
    return out


@me_recs_router.get("/api/me/recommendations/top-game")
async def me_top_game(user: dict = Depends(current_user)):
    out = await top_game_for_user(_db, user_id=user["user_id"])
    if not out:
        return {"game": None}
    return out


# ─── Favorites ───────────────────────────────────────────────────────
class FavoriteAddReq(BaseModel):
    channel_slug: str


@me_recs_router.get("/api/me/favorites")
async def me_favorites_list(user: dict = Depends(current_user)):
    items = await list_favorites(_db, user_id=user["user_id"])
    return {"favorites": items, "cap": FAVORITES_CAP}


@me_recs_router.post("/api/me/favorites")
async def me_favorites_add(req: FavoriteAddReq,
                                              user: dict = Depends(current_user)):
    try:
        out = await add_favorite(_db, user_id=user["user_id"],
                                              channel_slug=req.channel_slug)
    except OverflowError as e:
        raise HTTPException(409, {"code": "favorites_cap",
                                              "message": str(e),
                                              "cap":      FAVORITES_CAP})
    except LookupError:
        raise HTTPException(404, "channel not found")
    return out


@me_recs_router.delete("/api/me/favorites/{channel_slug}")
async def me_favorites_remove(channel_slug: str,
                                                    user: dict = Depends(current_user)):
    return await remove_favorite(_db, user_id=user["user_id"],
                                              channel_slug=channel_slug)


# ─── Listening-profile inspector (debug-only, gated to owner) ──────
@me_recs_router.get("/api/me/listening_profile")
async def me_listening_profile(force: bool = Query(False),
                                                    user: dict = Depends(current_user)):
    if force:
        _bust_listening_cache(user["user_id"])
    return await _user_listening_profile(_db, user_id=user["user_id"], force=force)


# ─── Commute — friendly-empty offers fallback ────────────────────
@me_recs_router.get("/api/commute/offers_along_route")
async def commute_offers_safe(origin: Optional[str] = None,
                                                  destination: Optional[str] = None,
                                                  mood:           Optional[str] = None,
                                                  user: dict = Depends(current_user)):
    """Returns up to 3 offers near the route.  Never 500s — if no partners
    are seeded, returns `{offers: [], note: "..."}`.
    """
    try:
        # Use the venue offers active list as a stand-in for now.
        rows = await _db.offers.find({"status": "active"},
                                                    sort=[("created_at", -1)]).to_list(20)
        out = []
        for o in rows[:3]:
            out.append({
                "offer_id":          o.get("id"),
                "title":               o.get("title"),
                "discount_value": o.get("discount_value"),
                "offer_type":       o.get("offer_type"),
                "venue_id":         o.get("venue_id"),
                "distance_off_route_mi": 0.4,
            })
        return {"offers": out,
                  "total":  len(out),
                  "mock":   True,
                  "note":    "Commute-route partner network seeds arrive in Phase 18.",
                  "echo":    {"origin": origin, "destination": destination, "mood": mood}}
    except Exception as e:
        logger.warning("commute_offers fallback: %s", e)
        return {"offers": [], "total": 0, "mock": True,
                  "note": "No partners seeded yet — check back soon."}
