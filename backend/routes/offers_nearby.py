"""Phase G1 — Geo-aware Nearby Offers.

Public, anonymous-friendly endpoint that powers the consumer "Nearby
offers" rail on Home.jsx (and any other surface that needs a
city-resolved offer list).

Endpoints:
    GET /api/offers/nearby?market=&city=&country=&lat=&lng=&limit=

Resolution order (first non-empty tier wins):
    1. `market` exact match  (matches useGeoStore.market values:
        dubai / new_york / london / mumbai / los_angeles / dfw)
    2. `country` ISO match    (e.g. AE, US, GB)
    3. globally-popular fallback  →  resolution_source="global"
                                                                      → caller renders a banner
                                                                          "Showing popular offers — none
                                                                            from {city} yet."
    4. empty                              →  resolution_source="empty"
                                                                      → caller renders the
                                                                          "Be the first business" CTA.

The `users.preferred_market` override on the authed user wins over the
query string when present (consistent with `useGeoStore.setMarket`).

Returns a small offer-card shape so the consumer rail doesn't have to
duplicate the venue-side `public_offer` schema.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request

from auth import current_user_optional

logger = logging.getLogger("bigfm.offers.nearby")

router = APIRouter(prefix="/api/offers", tags=["offers-nearby"])


SUPPORTED_MARKETS = {"dubai", "new_york", "london", "mumbai",
                                          "los_angeles", "dfw"}
MARKET_DISPLAY = {
    "dubai":        "Dubai",
    "new_york":     "New York",
    "london":       "London",
    "mumbai":       "Mumbai",
    "los_angeles":  "Los Angeles",
    "dfw":           "Dallas",
}
MARKET_COUNTRY = {
    "dubai":        "AE",
    "new_york":     "US",
    "london":       "GB",
    "mumbai":       "IN",
    "los_angeles":  "US",
    "dfw":           "US",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public_card(o: dict) -> dict:
    """Trimmed offer shape suitable for the consumer rail.  Never leaks
    owner-only fields (margin %, redemption caps, etc.)."""
    return {
        "offer_id":          o.get("offer_id") or o.get("id") or o.get("_id"),
        "title":               o.get("title") or "",
        "description":   o.get("description") or "",
        "offer_type":      o.get("offer_type"),
        "discount_label": _format_discount(o),
        "business_id":   o.get("business_id"),
        "venue_id":        o.get("venue_id"),
        "market":            o.get("market"),
        "city":                o.get("city"),
        "country":          o.get("country"),
        "expires_at":      _iso(o.get("expires_at") or o.get("ends_at")),
        "image_url":      o.get("image_url"),
        "tags":               o.get("tags") or [],
    }


def _format_discount(o: dict) -> Optional[str]:
    """Friendly discount label for the rail card."""
    if o.get("discount_label"):
        return o["discount_label"]
    pct = o.get("discount_percent")
    if isinstance(pct, (int, float)) and pct > 0:
        return f"{int(pct)}% off"
    amt = o.get("discount_amount")
    if isinstance(amt, (int, float)) and amt > 0:
        cur = o.get("discount_currency") or "AED"
        return f"{cur} {int(amt)} off"
    return None


def _iso(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v


def _normalize_market(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    return v if v in SUPPORTED_MARKETS else None


@router.get("/nearby",
                          description=(
                              "Public geo-aware offer rail.  Resolves the user's "
                              "market in order: query-string override → authed user's "
                              "`preferred_market` → IP-derived geo (caller passes it "
                              "via query, since `/api/geo/me` is the canonical IP "
                              "resolver).  Fallback chain: market → country → global "
                              "popular.  Always returns the `resolution_source` field "
                              "so the UI can render banner / empty copy correctly."))
async def offers_nearby(
    request: Request,
    market: Optional[str] = Query(None, description=(
        "useGeoStore market token (e.g. dubai, mumbai).  Wins unless the "
        "authed user has a stored preferred_market.")),
    city: Optional[str] = Query(None, description=(
        "Display city — used purely for response copy (e.g. \"none from "
        "Mumbai yet\").  Does NOT participate in filtering.")),
    country: Optional[str] = Query(None,
        description="ISO country (AE / US / GB / …).  Used as the second-tier fallback."),
    lat: Optional[float] = Query(None,
        description="Reserved for distance-based sort (future)."),
    lng: Optional[float] = Query(None,
        description="Reserved for distance-based sort (future)."),
    limit: int = Query(12, ge=1, le=50),
    user: Optional[dict] = Depends(current_user_optional),
):
    db = request.app.state.db

    # Resolve effective market.
    #
    # Query-string `market` wins because it represents the user's
    # CURRENT geo (either an explicit override from the UI city switcher
    # or the freshly-resolved IP geo from `useGeoStore`).  The authed
    # user's persisted `preferred_market` is only consulted when the
    # query string is empty (e.g. an anonymous request without UI state,
    # or an API caller that wants the user's stored default).
    qs_market = _normalize_market(market)
    pref_market = None
    if user:
        pref_market = (
            _normalize_market(user.get("preferred_market"))
            or _normalize_market(user.get("market")))
    effective_market = qs_market or pref_market or None
    effective_country = (country or "").strip().upper() or None
    if effective_market and not effective_country:
        effective_country = MARKET_COUNTRY.get(effective_market)
    effective_city_label = (
        city
        or (MARKET_DISPLAY.get(effective_market) if effective_market else None)
        or "your area"
    )

    base_query: Dict[str, Any] = {"status": "active"}

    # ── Tier 1 — market match ────────────────────────────────────────
    if effective_market:
        cur = db.offers.find({**base_query, "market": effective_market}) \
                                .sort("created_at", -1).limit(limit)
        items = [_public_card(o) async for o in cur]
        if items:
            return _resp(items, "market", effective_market, effective_city_label,
                              effective_country, requested=market)

    # ── Tier 2 — country match ───────────────────────────────────────
    if effective_country:
        cur = db.offers.find({**base_query, "country": effective_country}) \
                                .sort("created_at", -1).limit(limit)
        items = [_public_card(o) async for o in cur]
        if items:
            return _resp(items, "country", effective_market, effective_city_label,
                              effective_country, requested=market)

    # ── Tier 3 — globally-popular fallback ──────────────────────────
    # Most-recent active offers across all markets, deduplicated by
    # business so the rail isn't a single venue's catalog.
    pipeline = [
        {"$match": {"status": "active"}},
        {"$sort": {"created_at": -1}},
        {"$group": {"_id": "$business_id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"created_at": -1}},
        {"$limit": limit},
    ]
    items: List[dict] = []
    async for o in db.offers.aggregate(pipeline):
        items.append(_public_card(o))
    if items:
        return _resp(items, "global", effective_market, effective_city_label,
                          effective_country, requested=market)

    # ── Tier 4 — empty ───────────────────────────────────────────────
    return _resp([], "empty", effective_market, effective_city_label,
                      effective_country, requested=market)


def _resp(items: List[dict], source: str,
                  effective_market: Optional[str],
                  effective_city_label: str,
                  effective_country: Optional[str],
                  requested: Optional[str]) -> dict:
    return {
        "items": items,
        "count": len(items),
        "resolution_source": source,
        "effective_market": effective_market,
        "effective_country": effective_country,
        "city_label": effective_city_label,
        "requested_market": requested,
        "supported_markets": sorted(SUPPORTED_MARKETS),
        "fallback_banner": (
            None if source in {"market", "country"}
            else (
                f"Showing popular offers — none from {effective_city_label} yet."
                if source == "global"
                else f"We're working on partnerships in {effective_city_label}.")
        ),
    }
