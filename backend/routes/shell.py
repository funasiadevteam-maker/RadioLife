"""YouTube-style consumer shell — additive read + user-preference endpoints.

Powers the redesigned AppShell: live nav badges, config-driven filter chips
with LIVE counts, the "Your stations" flagship list, and a per-user theme
preference (dark default). Read-only + a tiny prefs writer — no existing
route, auth, or earn-rate logic is touched.
"""
from fastapi import APIRouter, Request, Body
from auth import current_user, current_user_optional
from services.station_art import resolve_art as _resolve_art
from datetime import datetime, timezone
import re

router = APIRouter(prefix="/api/shell")

VALID_THEMES = {"dark", "light"}
_TEST_NAME = re.compile(r"(TEST_|Iter\d|Test Shop|QA Demo)", re.I)

# Excludes QA/seed shops from consumer-facing counts + venue lists.
_NON_TEST = {"public_name": {"$not": {"$regex": r"(TEST_|Iter\d|Test Shop|QA Demo)",
                                      "$options": "i"}}}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Business-category -> friendly Shop & Eat label.
_CAT_LABEL = {
    "restaurant": "Restaurant",
    "beauty": "Salon & Spa",
    "fitness": "Fitness",
    "retail": "Retail",
}

# Marketplace business-category -> chip label (only rendered when count > 0).
_CAT_CHIPS = [
    ("restaurant", "Eat"),
    ("beauty", "Salons"),
    ("fitness", "Fitness"),
    ("retail", "Shops"),
]


@router.get("/summary")
async def shell_summary(request: Request, city: str = ""):
    db = request.app.state.db
    user = await current_user_optional(request)

    world = await db.imported_radio_stations.estimated_document_count()
    ai = await db.channels.count_documents({"active": True})
    station_count = int(world) + int(ai)
    games_live = await db.games.count_documents({})
    shop_offers = await db.marketplace_profiles.count_documents(dict(_NON_TEST))
    podcasts_count = await db.podcasts.count_documents({})

    # Flagship "Your stations" list (live dot + city).
    flagships = []
    cur = db.imported_radio_stations.find({"flagship_slug": {"$ne": None}}).limit(12)
    async for s in cur:
        art_url, art_source = _resolve_art(s)
        flagships.append({
            "id": s.get("id") or s.get("station_id"),
            "slug": s.get("flagship_slug"),
            "name": s.get("name"),
            "city": s.get("country"),
            "art": art_url,
            "art_source": art_source,
            "live": bool(s.get("is_live")),
            "listeners": int(s.get("listeners") or 0),
        })

    # Config-driven filter chips — every count is LIVE; zero-count omitted.
    chips = [{"key": "all", "label": "All"}]
    if user:
        chips.append({"key": "mine", "label": "My stations"})
    if ai:
        chips.append({"key": "radio", "label": "Radio", "count": int(ai)})
    for cat, label in _CAT_CHIPS:
        n = await db.marketplace_profiles.count_documents({"category": cat, **_NON_TEST})
        if n:
            chips.append({"key": f"cat_{cat}", "label": label, "count": int(n)})
    if games_live:
        chips.append({"key": "games", "label": "Games", "count": int(games_live)})
    chips.append({"key": "trivia", "label": "Trivia"})
    if shop_offers:
        chips.append({"key": "offers", "label": "Offers", "count": int(shop_offers)})
    chips.append({"key": "world", "label": "World", "count": int(world)})

    resolved_city = city or (user or {}).get("home_city") or ""

    return {
        "city": resolved_city,
        "station_count": station_count,
        "world_count": int(world),
        "ai_count": int(ai),
        "flagships": flagships,
        "flagship_count": len(flagships),
        "chips": chips,
        "badges": {
            "games": int(games_live),
            "shop": int(shop_offers),
        },
        "podcasts_count": int(podcasts_count),
        "is_premium": bool((user or {}).get("is_premium")),
    }


@router.get("/prefs")
async def get_prefs(request: Request):
    user = await current_user_optional(request)
    if not user:
        return {"theme": "dark"}
    db = request.app.state.db
    doc = await db.users.find_one({"user_id": user["user_id"]}, {"prefs": 1})
    theme = ((doc or {}).get("prefs") or {}).get("theme", "dark")
    return {"theme": theme if theme in VALID_THEMES else "dark"}


@router.put("/prefs")
async def put_prefs(request: Request, body: dict = Body(default={})):
    user = await current_user(request)
    theme = body.get("theme")
    if theme not in VALID_THEMES:
        theme = "dark"
    db = request.app.state.db
    await db.users.update_one(
        {"user_id": user["user_id"]}, {"$set": {"prefs.theme": theme}})
    return {"ok": True, "theme": theme}


def _venue_card(p: dict, promoted_ids: set) -> dict:
    """Consumer venue card sourced from a marketplace profile. Flags a
    business as `sponsored` when it has an active promotion / promoted_until."""
    bid = p.get("business_id")
    pu = p.get("promoted_until")
    promoted_now = bool(pu and str(pu) > _now_iso())
    bp = p.get("bigpoints") or {}
    cat = p.get("category")
    return {
        "business_id": bid,
        "name": p.get("public_name"),
        "category": cat,
        "category_label": _CAT_LABEL.get(cat, (cat or "").replace("_", " ").title()),
        "image": (p.get("cover_urls") or [None])[0] or p.get("logo_url"),
        "rating": p.get("rating"),
        "earn": bp.get("default_points") or None,
        "city": p.get("market"),
        "sponsored": bool(bid in promoted_ids or p.get("sponsored") or promoted_now),
    }


@router.get("/venues")
async def shell_venues(request: Request, category: str = "", city: str = "",
                       market: str = "", limit: int = 24):
    """Real Shop & Eat venues for the Home feed — sponsored-first, and scoped
    to the listener's city/market when we have venues there.

    Sources `marketplace_profiles` directly (the `offers` collection is near-empty
    mock data). Excludes QA/seed shops. `category` accepts a raw business category
    (restaurant/beauty/fitness/retail) or a `cat_<x>` chip key. When `market`/`city`
    match local venues, only those are returned; otherwise falls back to all so the
    shelf is never empty.
    """
    db = request.app.state.db
    promoted_ids = set(await db.marketplace_promotions.distinct(
        "business_id", {"status": "active"}))
    q = {"status": "approved", **_NON_TEST}
    if category:
        q["category"] = category[4:] if category.startswith("cat_") else category
    profiles = [p async for p in db.marketplace_profiles.find(q).limit(200)]

    terms = [t.lower() for t in (market, city) if t]
    if terms:
        def _loc_match(p):
            blob = " ".join(str(x) for x in (
                [p.get("market")] + [loc.get("city") for loc in (p.get("locations") or [])]
            )).lower()
            return any(t in blob or (blob and blob in t) for t in terms)
        local = [p for p in profiles if _loc_match(p)]
        profiles = local or profiles  # never empty the shelf

    cards = [_venue_card(p, promoted_ids) for p in profiles]
    # Sponsored first, then higher-rated.
    cards.sort(key=lambda v: (0 if v["sponsored"] else 1, -(v["rating"] or 0)))
    return {"items": cards[:limit], "count": len(cards)}


@router.get("/clips")
async def shell_clips(request: Request, limit: int = 10):
    """Clips shelf ("RJ moments") for Home. Surfaces ONE real SPONSORED clip
    from an active advertiser campaign first, then station clips from live AI
    channels (real movie-poster art). Empty-safe: [] when no channels."""
    db = request.app.state.db
    clips = []

    # One genuine sponsored clip from an active advertiser campaign — prefer
    # one that already has a branded cover so the clip never renders blank.
    camp = await db.campaigns.find_one(
        {"status": "active", "clip_image_url": {"$nin": [None, ""]}},
        sort=[("created_at", -1)])
    if not camp:
        camp = await db.campaigns.find_one({"status": "active"}, sort=[("created_at", -1)])
    if camp:
        biz = None
        if camp.get("business_id"):
            biz = await db.marketplace_profiles.find_one(
                {"business_id": camp["business_id"]},
                {"public_name": 1, "cover_urls": 1, "logo_url": 1})
        name = camp.get("name") or "Sponsored"
        if "—" in name:
            sponsor, _, offer = name.partition("—")
            sponsor, offer = sponsor.strip(), offer.strip()
        else:
            sponsor = (biz or {}).get("public_name") or "Sponsored"
            offer = name
        clips.append({
            "id": f"camp_{camp.get('campaign_id')}",
            "campaign_id": camp.get("campaign_id"),
            "title": offer,
            "channel": sponsor,
            "offer": offer,
            "sponsor": sponsor,
            "image": (camp.get("clip_image_url")
                      or ((biz or {}).get("cover_urls") or [None])[0]
                      or (biz or {}).get("logo_url")),
            "sponsored": True,
            "business_id": camp.get("business_id"),
        })

    # Station clips from live AI channels (real content + art).
    async for ch in db.channels.find({"active": True}).sort("sort_order", 1).limit(limit):
        clips.append({
            "id": ch.get("_id"),
            "slug": ch.get("_id"),
            "title": ch.get("name"),
            "channel": ch.get("tagline") or "RJ moment",
            "image": ch.get("cover_image_url") or ch.get("thumbnail_url"),
            "sponsored": False,
        })
    return {"items": clips[:limit + 1], "count": len(clips)}


@router.post("/clips/claim")
async def claim_clip_offer(request: Request, body: dict = Body(default={})):
    """Claim a sponsored clip's offer. Idempotent per user+campaign; returns a
    short redemption code the user shows in-store."""
    user = await current_user(request)
    db = request.app.state.db
    campaign_id = (body or {}).get("campaign_id")
    if not campaign_id:
        return {"ok": False, "error": "campaign_id required"}
    camp = await db.campaigns.find_one({"campaign_id": campaign_id})
    if not camp:
        return {"ok": False, "error": "campaign not found"}

    existing = await db.sponsored_clip_claims.find_one(
        {"user_id": user["user_id"], "campaign_id": campaign_id})
    if existing:
        return {"ok": True, "code": existing["code"], "already": True,
                "offer": camp.get("name")}

    import secrets
    code = "RL-" + secrets.token_hex(3).upper()
    await db.sponsored_clip_claims.insert_one({
        "user_id": user["user_id"],
        "campaign_id": campaign_id,
        "business_id": camp.get("business_id"),
        "code": code,
        "claimed_at": _now_iso(),
    })
    return {"ok": True, "code": code, "already": False, "offer": camp.get("name")}
