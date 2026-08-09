"""Phase B — Personalized city tags.

Endpoint:
    GET  /api/personalized/city_tags    — optional auth
    PATCH /api/users/me/home_city        — auth required

Why a dedicated router (and not folding into geo_routes):
the geo router is about IP-resolution semantics; this router is about
user-personalization semantics that *uses* the geo result.  Splitting
them keeps the geo unit-tests focused on resolution correctness and
makes the personalization layer easy to swap out (eg. with a Redis-
backed heat table later) without touching geo.
"""
from __future__ import annotations
import logging
from typing import Any, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services import geo as geo_svc
from services.listener_heat import get_top_cities, LAUNCH_MARKETS

router = APIRouter(prefix="/api", tags=["personalized"])
log = logging.getLogger("bigfm.personalized")


# Coarse market → primary city.  Mirrors the labelling in
# frontend/src/store/useGeoStore.js so the two layers stay aligned.
_MARKET_TO_CITY = {
    "dubai":        "Dubai",
    "dfw":          "Dallas",
    "mumbai":       "Mumbai",
    "london":       "London",
    "new_york":     "New York",
    "los_angeles":  "Los Angeles",
}


# ─── Schemas ────────────────────────────────────────────────────────────
class CityTag(BaseModel):
    city:    str        = Field(..., description="Display name, eg. 'Dubai'.")
    label:   str        = Field(..., description="Short relationship label, eg. 'Home', 'Visiting', 'Live', 'Recent'.")
    source:  str        = Field(..., description="Origin signal: user_home_city, geo_ip, listener_history, heat, market_default.")
    market:  Optional[str] = None


class CityTagsResponse(BaseModel):
    primary_city:  str         = Field(..., description="Hero label — the city that should headline the home page.")
    tags:           list[CityTag]
    fallback_used: bool        = Field(..., description="True when no personal signal was available and the response is just the heat list.")


class HomeCityBody(BaseModel):
    home_city:    Optional[str] = Field(None, max_length=80,
        description="Free-text home city (any string).  Null clears the override.")


# ─── Helpers ─────────────────────────────────────────────────────────────
def _norm(c: Optional[str]) -> str:
    """Lowercased, trimmed comparison key — case-insensitive de-dupe."""
    return (c or "").strip().lower()


async def _recent_cities_for_user(db: Any, user_id: str,
                                  exclude: set[str],
                                  limit: int = 3) -> list[dict[str, Any]]:
    """Cities the user has previously listened from, last 7 days, ordered
    by session count desc.  Reads ``listener_session_archive`` (closed
    sessions) since live sessions are usually still rendering the user's
    current geo (which is already in the 'Visiting' tag)."""
    if not user_id:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    pipeline = [
        {"$match": {
            "user_id":         user_id,
            "resolved_city":  {"$nin": [None, "", "Global"]},
            "joined_at":       {"$gte": cutoff},
        }},
        {"$group": {
            "_id":             "$resolved_city",
            "session_count": {"$sum": 1},
        }},
        {"$sort": {"session_count": -1}},
        {"$limit": limit + len(exclude)},  # over-fetch so we can skip excludes
    ]
    out: list[dict[str, Any]] = []
    try:
        async for row in db.listener_session_archive.aggregate(pipeline):
            city = row.get("_id") or ""
            if _norm(city) in exclude:
                continue
            out.append({"city": city,
                          "session_count": int(row.get("session_count") or 0)})
            if len(out) >= limit:
                break
    except Exception as e:
        log.warning("[city_tags] recent agg failed: %s: %s", type(e).__name__, e)
    return out


# ─── Route: GET /api/personalized/city_tags ────────────────────────────
@router.get("/personalized/city_tags", response_model=CityTagsResponse)
async def get_city_tags(
    request: Request,
    user: Optional[dict] = Depends(current_user_optional),
) -> CityTagsResponse:
    """Returns 1-3 personalized city tags for the hero / station chrome.

    Ordering (per Phase B brief):
      1. ``user.home_city`` if set                   → label ``Home``
      2. Current resolved geo city                      → label ``Live`` (==home) or ``Visiting`` (!=home)
      3. One recent city from listener_session_archive → label ``Recent``
      4. Fill remaining slots from heat / launch markets — sets ``fallback_used=true``.

    Anonymous callers see the resolved geo city (if any) + heat fill.
    The first tag's city becomes ``primary_city``.
    """
    db = request.app.state.db
    tags: list[CityTag] = []
    seen: set[str] = set()

    def _push(city: str, label: str, source: str, market: str = "") -> None:
        c = (city or "").strip()
        if not c or _norm(c) in seen:
            return
        seen.add(_norm(c))
        tags.append(CityTag(city=c, label=label, source=source,
                                market=market or None))

    # (1) home_city — only when authed
    home_city = (user or {}).get("home_city") or ""
    home_city = home_city.strip() if isinstance(home_city, str) else ""
    if home_city:
        _push(home_city, "Home", "user_home_city")

    # (2) resolved geo for the *Visiting* signal.  Per user feedback
    # ("dynamic name of my city AND home town in preference AND city
    # I am visiting"), the Visiting tag must reflect the listener's
    # *current* IP location independent of any preferred_market /
    # home_market override they set during onboarding.  We deliberately
    # bypass `resolve_for_user` here (which prefers the home market)
    # and read the raw IP geolocation instead.  This lets a Dubai-home
    # user travelling to NY see ``[Home: Dubai, Visiting: New York]``
    # in the hero strip.
    try:
        resolved = await geo_svc.resolve_geo_from_ip(request, db)
    except Exception as e:
        log.warning("[city_tags] raw IP resolve failed: %s", e)
        resolved = {}
    resolved_city = (resolved.get("city") or "").strip()
    resolved_market = (resolved.get("market") or "").strip()
    if resolved_city and resolved_city != "Global":
        if home_city and _norm(resolved_city) == _norm(home_city):
            # Re-label the Home tag → "Live" since the user IS home now.
            # We mutate the previously-pushed tag rather than emit a dupe.
            if tags and _norm(tags[0].city) == _norm(home_city):
                tags[0] = tags[0].model_copy(update={"label": "Live"})
        else:
            _push(resolved_city, "Visiting", "geo_ip", resolved_market)

    # (3) one recent city from archive (authed only)
    if user:
        recent = await _recent_cities_for_user(db, user["user_id"], seen, limit=1)
        for r in recent:
            _push(r["city"], "Recent", "listener_history")

    # (4) heat / launch-market fill until we have 3 (or there's nothing left)
    fallback_used = False
    if len(tags) < 3:
        try:
            heat = await get_top_cities(db, window_hours=24, limit=6)
        except Exception as e:
            log.warning("[city_tags] heat failed: %s", e)
            heat = list(LAUNCH_MARKETS)
        for h in heat:
            if len(tags) >= 3:
                break
            if _norm(h["city"]) in seen:
                continue
            fallback_used = True
            _push(h["city"], "Live in", "heat" if h.get("session_count") else "market_default",
                       h.get("market") or "")

    primary = tags[0].city if tags else "RadioLife Global"
    return CityTagsResponse(primary_city=primary,
                                              tags=tags[:3],
                                              fallback_used=fallback_used)


# ─── Route: PATCH /api/users/me/home_city ──────────────────────────────
@router.patch("/users/me/home_city")
async def patch_home_city(body: HomeCityBody, request: Request,
                            user: dict = Depends(current_user)):
    """Set / clear the caller's home city.  Free-text (so users can pick
    'Karachi' or 'Lagos' even though they aren't in our launch markets).
    Empty / null clears the field.  Derived from market on first
    onboarding save (auth.py::users_save_prefs); this endpoint is the
    explicit-override path."""
    db = request.app.state.db
    new_city = (body.home_city or "").strip()[:80] if body.home_city else ""
    update: dict[str, Any] = {"home_city": new_city or None}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    return {"ok": True, "home_city": update["home_city"]}
