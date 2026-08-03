"""
Phase 15d — geo + market endpoints.

  GET  /api/geo/me                    anon or authed — resolve current market
  POST /api/geo/gps                    authed — write GPS into user doc
  PATCH /api/users/me/market         authed — set/clear preferred_market
  GET  /api/news/local                anon or authed — 3-5 headlines for market
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from services import geo as geo_svc
from services import news as news_svc
from services.market_lexicon import supported_markets, MARKET_LEXICON

# Body models at module level so tests can import them.
class GpsBody(BaseModel):
    latitude:        float
    longitude:        float
    accuracy_meters: Optional[float] = None


class MarketBody(BaseModel):
    market: Optional[str] = None  # null/empty clears


class PreferredCityBody(BaseModel):
    """Bug B — free-text city override.  Empty/None clears."""
    city: Optional[str] = None


def _make_router(db, get_current_user_optional, get_current_user_required):
    """Factory — server.py calls this with its DI hooks so we don't have to
       re-implement auth.  `_optional` returns None for anon.
       A fresh APIRouter is created on every call so tests can build
       isolated routers without polluting a module-level singleton."""
    router = APIRouter()

    @router.get("/api/geo/me")
    async def geo_me(request: Request,
                              user: Optional[dict] = Depends(get_current_user_optional)):
        resolved = await geo_svc.resolve_for_user(request, user, db)
        # Phase 15d.1 — persist `last_resolved_market` on the user doc so the
        # RJ pipeline (which reads users.find_one in a different code path)
        # can honour the resolved market even when the user hasn't pinned a
        # `preferred_market` override yet.  Cheap idempotent write.
        if user and isinstance(user, dict):
            try:
                uid = user.get("user_id") or user.get("id")
                if uid and resolved.get("market"):
                    await db.users.update_one(
                        {"user_id": uid},
                        {"$set": {"last_resolved_market": resolved["market"]}},
                    )
            except Exception:
                pass
        return resolved

    @router.get("/api/geo/resolve_city")
    async def geo_resolve_city(
        request: Request,
        user: Optional[dict] = Depends(get_current_user_optional),
    ):
        """Bug B — resolve current listener city via the standard chain.

        Returns ``{city, country, lat, lng, source}`` for the requester.
        Resolution priority:

          1. ``user.preferred_city`` (explicit override).
          2. ``user.preferred_market`` / ``user.market``.
          3. Server-side IP geolocation (24 h cached, ipapi.co provider).
          4. Hard fallback → ``{city: "Global", country: "", source: "mock"}``.

        Use this from the frontend when you specifically want a single
        compact `{city, country, lat, lng, source}` payload — the older
        ``/api/geo/me`` returns the richer market shape.
        """
        resolved = await geo_svc.resolve_for_user(request, user, db)
        return {
            "city":     resolved.get("city") or "Global",
            "country": resolved.get("country") or "",
            "lat":      float(resolved.get("latitude") or 0.0),
            "lng":      float(resolved.get("longitude") or 0.0),
            "source":   resolved.get("source") or "mock",
            # Bonus context the frontend can use to keep header/footer in sync.
            "market":   resolved.get("market") or "global",
            "timezone": resolved.get("timezone") or "UTC",
        }

    @router.patch("/api/users/me/preferred_city")
    async def patch_preferred_city(body: PreferredCityBody,
                                                          user: dict = Depends(get_current_user_required)):
        """Bug B — explicit city override.

        Free-text city label (we don't constrain to the lexicon's six
        markets). Empty/None clears the override and falls back to IP /
        market resolution. When the label matches a lexicon
        ``display_name`` we also keep ``preferred_market`` in sync so RJ
        scripts and music routing pick up the same hint.
        """
        from services.market_lexicon import MARKET_LEXICON
        uid = user.get("user_id") or user.get("id")
        city = (body.city or "").strip()
        update: dict = {"preferred_city": city or None}
        if city:
            for mkey, mentry in MARKET_LEXICON.items():
                if (mentry.get("display_name") or "").strip().lower() == city.lower():
                    update["preferred_market"] = mkey
                    break
        else:
            # Clearing the city → also clear the derived market override so
            # we fall back to the user's home market / IP resolver.
            update["preferred_market"] = None
        await db.users.update_one({"user_id": uid}, {"$set": update})
        return {"ok": True,
                  "preferred_city":    update.get("preferred_city"),
                  "preferred_market": update.get("preferred_market")}

    @router.post("/api/geo/gps")
    async def geo_gps(body: GpsBody,
                              user: dict = Depends(get_current_user_required)):
        # Best-effort reverse geocode via maps_client (already wired); we
        # just persist the coords + last_known_location stamp here. The
        # market itself stays driven by the user override or IP resolver.
        from datetime import datetime, timezone
        uid = user.get("user_id") or user.get("id")
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {
                "last_known_location": {
                    "lat": body.latitude, "lng": body.longitude,
                    "accuracy_m": body.accuracy_meters,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                },
            }},
        )
        return {"ok": True, "lat": body.latitude, "lng": body.longitude}

    @router.patch("/api/users/me/market")
    async def patch_market(body: MarketBody,
                                          user: dict = Depends(get_current_user_required)):
        m = (body.market or "").strip().lower().replace(" ", "_").replace("-", "_")
        if m and m not in MARKET_LEXICON:
            raise HTTPException(400, f"unsupported market: {m}")
        uid = user.get("user_id") or user.get("id")
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {"preferred_market": m or None}},
        )
        return {"ok": True, "preferred_market": m or None,
                  "supported": supported_markets()}

    @router.get("/api/news/local")
    async def news_local(request: Request,
                                      user: Optional[dict] = Depends(get_current_user_optional),
                                      limit: int = 5):
        resolved = await geo_svc.resolve_for_user(request, user, db)
        market = resolved.get("market") or "dubai"
        payload = await news_svc.fetch_local_news(market, db, limit=limit)
        return payload

    return router
