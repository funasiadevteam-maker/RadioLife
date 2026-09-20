"""FUUSIC Advertising Product Registry — Phase A of the programmatic API.

Single source of truth for what the Partner API (`/api/v1`) can offer,
reconciled with the ad / game / sponsorship engines that ACTUALLY exist so
external clients never hardcode assumptions. The discovery endpoints
(`/capabilities`, `/inventory`, `/rate-card`, `/targeting/options`,
`/markets`) all read from here.

status:        available | beta | coming_soon | unavailable
api_bookable:  True  -> can be created/booked through the Partner API today
approval:      sandbox auto-approves; LIVE requires human review unless a
               partner has explicit trusted auto-approval.
"""
from __future__ import annotations

from typing import Optional

from services.market_lexicon import MARKET_LEXICON

API_VERSION = "1"

# country -> ISO currency (best-effort; rate card is USD-normalized).
_CCY = {"AE": "AED", "US": "USD", "GB": "GBP", "IN": "INR"}

_LIVE_APPROVAL = "sandbox_auto_live_human_review"


# ─────────────────────────── product registry ──────────────────────────
REGISTRY: list[dict] = [
    {
        "key": "audio_preroll", "name": "Audio Pre-roll", "category": "audio",
        "status": "available", "api_bookable": True,
        "campaign_type": "audio_preroll_stub",
        "pricing_models": ["cpm", "flat"],
        "creative_requirements": {"types": ["audio/mp3", "audio/aac"],
                                  "max_duration_seconds": 30},
        "targeting_capabilities": ["market", "station", "genre", "language",
                                   "daypart", "device", "frequency_cap"],
        "internal_service": "ad_decisioning",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["spend", "impressions", "audio_starts",
                              "completions", "completion_rate"],
        "consumer_placement": "Before a live-radio stream starts",
    },
    {
        "key": "display_banner", "name": "Display Banner", "category": "display",
        "status": "available", "api_bookable": True,
        "campaign_type": "display_banner",
        "pricing_models": ["cpm", "cpc", "flat"],
        "creative_requirements": {"types": ["image/png", "image/jpeg"],
                                  "placements": ["home_rail", "player", "shop"]},
        "targeting_capabilities": ["market", "genre", "device", "daypart",
                                   "content_category"],
        "internal_service": "ad11_banner_service",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["spend", "impressions", "clicks", "ctr",
                              "conversions"],
        "consumer_placement": "In-app banner across web + mobile",
    },
    {
        "key": "sponsored_game", "name": "Sponsored Game", "category": "games",
        "status": "available", "api_bookable": True,
        "campaign_type": "sponsored_game",
        "pricing_models": ["cpm", "flat"],
        "creative_requirements": {"types": ["image/png"],
                                  "requires": ["sponsored_game_campaign_id"]},
        "targeting_capabilities": ["market", "game_type"],
        "internal_service": "games_v2",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["entries", "unique_players", "completions",
                              "winners", "coupon_saves", "redemptions"],
        "consumer_placement": "FUUSIC Play & Win",
    },
    {
        "key": "trivia_sponsorship", "name": "Trivia Sponsorship",
        "category": "trivia", "status": "available", "api_bookable": True,
        "campaign_type": None, "pricing_models": ["prize_pool"],
        "creative_requirements": {"types": ["image/png"]},
        "targeting_capabilities": ["market", "category"],
        "internal_service": "trivia_sponsorship_service",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["entries", "engagement", "winners"],
        "consumer_placement": "FUUSIC Trivia rooms",
        "endpoints": {"inventory": "/api/v1/sponsorships/inventory?type=trivia",
                      "create": "/api/v1/sponsorships",
                      "checkout": "/api/v1/sponsorships/{id}/checkout"},
    },
    {
        "key": "predict_win_sponsorship", "name": "Predict & Win Sponsorship",
        "category": "predict_win", "status": "available", "api_bookable": True,
        "campaign_type": None, "pricing_models": ["per_entry", "per_impression"],
        "creative_requirements": {"types": ["image/png"]},
        "targeting_capabilities": ["market"],
        "internal_service": "ad3_sponsorship_service",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["entries", "engagement"],
        "consumer_placement": "FUUSIC Predict & Win",
        "endpoints": {"create": "/api/v1/sponsorships",
                      "checkout": "/api/v1/sponsorships/{id}/checkout"},
    },
    {
        "key": "ai_rj_read", "name": "AI-RJ Sponsored Read", "category": "audio",
        "status": "available", "api_bookable": True,
        "campaign_type": None, "pricing_models": ["cost_per_play"],
        "creative_requirements": {"script_required": True,
                                  "approved_persona_required": True},
        "targeting_capabilities": ["market", "station", "language"],
        "internal_service": "rj_sponsored_read_service",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["plays", "spend"],
        "consumer_placement": "Host-read mention between songs",
        "endpoints": {"create": "/api/v1/sponsorships",
                      "submit": "/api/v1/sponsorships/{id}/submit",
                      "checkout": "/api/v1/sponsorships/{id}/checkout"},
    },
    {
        "key": "marketplace_promotion", "name": "Marketplace Promotion",
        "category": "commerce", "status": "available", "api_bookable": True,
        "campaign_type": None, "pricing_models": ["flat", "cpm"],
        "creative_requirements": {"types": ["image/png", "image/jpeg"]},
        "targeting_capabilities": ["market", "category"],
        "internal_service": "partner_marketplace",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["impressions", "clicks", "views"],
        "consumer_placement": "Shop promoted rail + category spotlight",
        "endpoints": {"tiers": "/api/v1/marketplace/promotion/tiers",
                      "businesses": "/api/v1/marketplace/businesses",
                      "checkout": "/api/v1/marketplace/promotion/checkout"},
    },
    {
        "key": "programmatic_openrtb", "name": "Programmatic (OpenRTB)",
        "category": "programmatic", "status": "beta", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["cpm"],
        "creative_requirements": {"vast": True},
        "targeting_capabilities": ["market", "device"],
        "internal_service": "openrtb",
        "approval": "programmatic",
        "reporting_metrics": ["bids", "wins", "impressions", "spend"],
        "consumer_placement": "Audio + display via RTB",
        "endpoints": {"bid": "/api/openrtb", "vast": "/api/vast"},
    },
    {
        "key": "audio_midroll", "name": "Audio Mid-stream", "category": "audio",
        "status": "available", "api_bookable": False,  # booking wired in Phase D
        "campaign_type": None, "pricing_models": ["cpm"],
        "creative_requirements": {"types": ["audio/mp3", "audio/aac"],
                                  "max_duration_seconds": 30},
        "targeting_capabilities": ["market", "station", "daypart"],
        "internal_service": "midstream",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["impressions", "audio_starts", "completions"],
        "consumer_placement": "Mid-stream during live radio",
    },
    {
        "key": "push_notification", "name": "Push / Notification Campaign",
        "category": "push", "status": "available", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["flat", "cpm"],
        "creative_requirements": {"title": True, "body": True,
                                  "image_optional": True, "deep_link": True},
        "targeting_capabilities": ["market", "audience", "frequency_cap"],
        "internal_service": "ad12_notifications",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["sends", "opens", "clicks"],
        "consumer_placement": "Push + in-app notification",
    },
    {
        "key": "coupon_promotion", "name": "Coupon / Offer Campaign",
        "category": "local_business", "status": "available", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["flat", "cpa"],
        "creative_requirements": {"offer_terms": True},
        "targeting_capabilities": ["market", "merchant_category"],
        "internal_service": "ad4_coupon_campaigns",
        "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["saves", "redemptions"],
        "consumer_placement": "Coupons in wallet + shop",
    },
    {
        "key": "location_boost", "name": "Location Boost", "category": "local_business",
        "status": "coming_soon", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["cpm", "flat"],
        "creative_requirements": {}, "targeting_capabilities": ["market", "radius"],
        "internal_service": "listener_heat", "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["impressions", "visits"],
        "consumer_placement": "Proximity-based placements",
    },
    {
        "key": "retargeting", "name": "Audience Retargeting", "category": "audience",
        "status": "coming_soon", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["cpm"],
        "creative_requirements": {}, "targeting_capabilities": ["audience_segment"],
        "internal_service": "ad_decisioning", "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["impressions", "conversions"],
        "consumer_placement": "Across enabled placements",
    },
    {
        "key": "takeover_hour", "name": "Sponsored Hour / Takeover",
        "category": "sponsorship", "status": "coming_soon", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["flat"],
        "creative_requirements": {}, "targeting_capabilities": ["station", "market"],
        "internal_service": "ad3_sponsorships", "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["impressions", "listens"],
        "consumer_placement": "Station takeover window",
    },
    {
        "key": "podcast_sponsorship", "name": "Podcast Sponsorship",
        "category": "podcast", "status": "coming_soon", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["cpm", "flat"],
        "creative_requirements": {"types": ["audio/mp3"]},
        "targeting_capabilities": ["market", "show"],
        "internal_service": "podcasts", "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["impressions", "completions"],
        "consumer_placement": "Audio + video podcasts",
    },
    {
        "key": "station_promotion", "name": "Promoted Station",
        "category": "stations", "status": "available", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["flat", "cpm"],
        "creative_requirements": {}, "targeting_capabilities": ["market", "genre"],
        "internal_service": "promoted_stations", "approval": _LIVE_APPROVAL,
        "reporting_metrics": ["impressions", "clicks", "new_listeners"],
        "consumer_placement": "Featured / search-boosted stations",
    },
    {
        "key": "video_ads", "name": "Video Ads", "category": "video",
        "status": "coming_soon", "api_bookable": False,
        "campaign_type": None, "pricing_models": ["cpm"],
        "creative_requirements": {"types": ["video/mp4"]},
        "targeting_capabilities": ["market"], "internal_service": None,
        "approval": _LIVE_APPROVAL, "reporting_metrics": ["impressions", "views"],
        "consumer_placement": "Video pre/mid + podcast video",
    },
]


def registry_list() -> list[dict]:
    return REGISTRY


def by_key(key: str) -> Optional[dict]:
    return next((p for p in REGISTRY if p["key"] == key), None)


def bookable() -> list[dict]:
    return [p for p in REGISTRY if p.get("api_bookable")]


# ─────────────────────────── markets ───────────────────────────────────
def markets() -> list[dict]:
    out = []
    for key, m in MARKET_LEXICON.items():
        country = m.get("country")
        out.append({
            "market_id": key,
            "city": m.get("display_name"),
            "metro": m.get("display_name"),
            "region": m.get("region"),
            "country": country,
            "timezone": m.get("timezone"),
            "currency": _CCY.get(country, "USD"),
            "primary_language": m.get("language"),
            "status": "active",
        })
    return out


def market_ids() -> list[str]:
    return list(MARKET_LEXICON.keys())


# ─────────────────────────── targeting ─────────────────────────────────
TARGETING_OPTIONS: list[dict] = [
    {"key": "market", "label": "Market", "type": "enum", "values_endpoint": "/api/v1/markets"},
    {"key": "city", "label": "City", "type": "string"},
    {"key": "radius", "label": "ZIP / radius", "type": "geo_radius", "status": "where_supported"},
    {"key": "language", "label": "Language", "type": "enum",
     "values": ["english", "hindi", "hinglish", "arabic"]},
    {"key": "genre", "label": "Genre", "type": "string"},
    {"key": "station", "label": "Station", "type": "id", "values_endpoint": "/api/v1/stations"},
    {"key": "daypart", "label": "Daypart", "type": "enum",
     "values": ["morning_drive", "midday", "afternoon_drive", "evening", "overnight"]},
    {"key": "device", "label": "Device", "type": "enum", "values": ["ios", "android", "web"]},
    {"key": "listener_interest", "label": "Listener interest", "type": "enum"},
    {"key": "merchant_category", "label": "Merchant category", "type": "enum",
     "values_endpoint": "/api/v1/marketplace/categories"},
    {"key": "content_category", "label": "Content category", "type": "enum"},
    {"key": "frequency_cap", "label": "Frequency cap", "type": "int"},
]


# ─────────────────────────── rate card ─────────────────────────────────
# Server rate-card rules are authoritative; POST /quotes (Phase B) returns a
# binding estimate. Rates are illustrative floors in USD cents.
RATE_CARD: dict = {
    "currency": "USD",
    "pricing_models": {
        "cpm": "Cost per 1,000 impressions",
        "cpc": "Cost per click",
        "cpa": "Cost per action / acquisition",
        "cpl": "Cost per lead",
        "flat": "Flat fee for the flight",
        "prize_pool": "Fund a sponsorship prize pool",
        "cost_per_play": "Cost per audio play",
        "per_entry": "Cost per game/prediction entry",
        "per_impression": "Cost per sponsorship impression",
        "revenue_share": "Share of attributed revenue",
    },
    "base_rates": [
        {"product": "audio_preroll", "model": "cpm", "amount_cents": 2500},
        {"product": "audio_midroll", "model": "cpm", "amount_cents": 3000},
        {"product": "display_banner", "model": "cpm", "amount_cents": 900},
        {"product": "display_banner", "model": "cpc", "amount_cents": 60},
        {"product": "sponsored_game", "model": "flat", "amount_cents": 150000},
        {"product": "trivia_sponsorship", "model": "prize_pool", "amount_cents": 50000},
        {"product": "ai_rj_read", "model": "cost_per_play", "amount_cents": 120},
        {"product": "marketplace_promotion", "model": "flat", "amount_cents": 30000},
    ],
    "multipliers": [
        {"key": "market", "description": "Premium metros cost more",
         "examples": {"dubai": 1.2, "new_york": 1.3, "london": 1.25,
                      "los_angeles": 1.2, "mumbai": 1.0, "dfw": 1.0}},
        {"key": "daypart", "description": "Drive-time premium",
         "examples": {"morning_drive": 1.3, "afternoon_drive": 1.25,
                      "midday": 1.0, "evening": 1.1, "overnight": 0.7}},
        {"key": "premium_station", "description": "Flagship / premium stations",
         "factor": 1.25},
        {"key": "scarcity", "description": "Applied when inventory is tight",
         "max_factor": 1.5},
        {"key": "targeting", "description": "Per extra targeting dimension",
         "per_dimension": 0.1},
    ],
    "notes": ("Server rate-card rules are authoritative. Submit "
              "POST /api/v1/quotes for a binding estimate before creating a campaign."),
}


# ─────────────────────────── inventory ─────────────────────────────────
_INVENTORY_CATEGORIES = [
    ("audio", "AUDIO"), ("display", "DISPLAY"), ("video", "VIDEO"),
    ("podcast", "PODCAST"), ("games", "GAMES"), ("predict_win", "PREDICT & WIN"),
    ("trivia", "TRIVIA"), ("push", "PUSH"),
    ("commerce", "MARKETPLACE"), ("local_business", "LOCAL BUSINESS"),
    ("stations", "STATIONS"), ("audience", "AUDIENCE"),
    ("sponsorship", "SPONSORSHIPS"), ("programmatic", "PROGRAMMATIC"),
]


def inventory() -> list[dict]:
    """Inventory grouped by category, listing the products under each and
    whether any are available today."""
    seen = set()
    out = []
    for cat, label in _INVENTORY_CATEGORIES:
        if label in seen:
            continue
        seen.add(label)
        prods = [p for p in REGISTRY if p["category"] == cat]
        if not prods:
            continue
        out.append({
            "category": cat, "label": label,
            "available": any(p["status"] in ("available", "beta") for p in prods),
            "products": [{"key": p["key"], "name": p["name"],
                          "status": p["status"], "api_bookable": p["api_bookable"],
                          "pricing_models": p["pricing_models"]} for p in prods],
        })
    return out


# ─────────────────────────── capabilities ──────────────────────────────
FEATURE_FLAGS = {
    "multi_format_campaigns": True,     # Phase C
    "creative_library": True,          # Phase C
    "idempotency_keys": True,          # Phase B
    "external_id": True,               # Phase B
    "quotes": True,                    # Phase B
    "merchant_api": True,              # Phase E
    "reward_events": True,             # Phase E
    "conversions": True,               # Phase E
    "bulk_jobs": True,                 # Phase E
    "analytics": True,                 # Phase E
    "billing": True,                   # Phase E
    "webhooks": True,
    "sandbox": True,
    "openrtb": True,
}


def compute_quote(*, product: str, pricing_model: str,
                  market: Optional[str] = None, budget_cents: int = 0,
                  targeting_dimensions: int = 0, daypart: Optional[str] = None,
                  premium: bool = False) -> dict:
    """Server-authoritative pricing estimate from the rate card. External
    clients cannot submit arbitrary low prices — this is the source of truth."""
    p = by_key(product)
    if not p:
        raise ValueError("unknown_product")
    if pricing_model not in p["pricing_models"]:
        raise ValueError("invalid_pricing_model_for_product")
    base = next((r["amount_cents"] for r in RATE_CARD["base_rates"]
                 if r["product"] == product and r["model"] == pricing_model), None)
    if base is None:
        base = next((r["amount_cents"] for r in RATE_CARD["base_rates"]
                     if r["product"] == product), 1000)
    mkt_mult = dp_mult = 1.0
    for m in RATE_CARD["multipliers"]:
        if m["key"] == "market" and market:
            mkt_mult = float(m["examples"].get(market, 1.0))
        elif m["key"] == "daypart" and daypart:
            dp_mult = float(m["examples"].get(daypart, 1.0))
    prem_mult = 1.25 if premium else 1.0
    tgt_mult = 1.0 + 0.1 * max(0, int(targeting_dimensions or 0))
    effective = base * mkt_mult * dp_mult * prem_mult * tgt_mult
    eff_int = int(round(effective))
    est: dict = {}
    b = int(budget_cents or 0)
    if effective > 0 and b > 0:
        if pricing_model in ("cpm", "per_impression"):
            est["impressions"] = int(b / effective * 1000)
        elif pricing_model == "cpc":
            est["clicks"] = int(b / effective)
        elif pricing_model in ("cpa", "cpl"):
            est["actions"] = int(b / effective)
        elif pricing_model == "cost_per_play":
            est["plays"] = int(b / effective)
        elif pricing_model == "per_entry":
            est["entries"] = int(b / effective)
        else:  # flat / prize_pool / revenue_share
            est["flights"] = 1
    return {
        "product": product, "pricing_model": pricing_model, "market": market,
        "currency": RATE_CARD["currency"], "base_rate_cents": base,
        "effective_rate_cents": eff_int,
        "multipliers_applied": {"market": mkt_mult, "daypart": dp_mult,
                                "premium": prem_mult, "targeting": round(tgt_mult, 2)},
        "estimated_volume": est,
        "minimum_spend_cents": max(eff_int, 5000),
        "estimated_total_cents": b,
    }


async def supported_game_types(db) -> list[dict]:
    out = []
    try:
        async for t in db.game_templates.find(
                {"active": True}, {"template_id": 1, "game_type": 1, "name": 1}):
            out.append({"template_id": t.get("template_id"),
                        "game_type": t.get("game_type"), "name": t.get("name")})
    except Exception:
        pass
    return out


async def capabilities(db, environment: str = "LIVE") -> dict:
    return {
        "api_versions": [API_VERSION],
        "environment": environment,
        "feature_flags": FEATURE_FLAGS,
        "pricing_models": RATE_CARD["pricing_models"],
        "campaign_types": [
            {"key": p["key"], "name": p["name"], "category": p["category"],
             "status": p["status"], "api_bookable": p["api_bookable"],
             "pricing_models": p["pricing_models"],
             "creative_types": (p.get("creative_requirements") or {}).get("types", []),
             "approval": p["approval"]}
            for p in REGISTRY
        ],
        "inventory_types": [i["label"] for i in inventory()],
        "supported_markets": market_ids(),
        "supported_targeting": [t["key"] for t in TARGETING_OPTIONS],
        "supported_game_types": await supported_game_types(db),
        "scopes": None,  # filled by the route from services.partner_api.SCOPES
    }


__all__ = [
    "API_VERSION", "REGISTRY", "registry_list", "by_key", "bookable",
    "markets", "market_ids", "TARGETING_OPTIONS", "RATE_CARD", "inventory",
    "FEATURE_FLAGS", "capabilities", "supported_game_types", "compute_quote",
]
