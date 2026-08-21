"""YouTube-style consumer shell — additive read + user-preference endpoints.

Powers the redesigned AppShell: live nav badges, config-driven filter chips
with LIVE counts, the "Your stations" flagship list, and a per-user theme
preference (dark default). Read-only + a tiny prefs writer — no existing
route, auth, or earn-rate logic is touched.
"""
from fastapi import APIRouter, Request, Body
from auth import current_user, current_user_optional
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
        flagships.append({
            "id": s.get("id") or s.get("station_id"),
            "slug": s.get("flagship_slug"),
            "name": s.get("name"),
            "city": s.get("country"),
            "art": s.get("flagship_art") or s.get("favicon"),
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
async def shell_venues(request: Request, category: str = "", limit: int = 24):
    """Real Shop & Eat venues for the Home feed — grouped-ready + sponsored-first.

    Sources `marketplace_profiles` directly (the `offers` collection is near-empty
    mock data). Excludes QA/seed shops. `category` accepts a raw business category
    (restaurant/beauty/fitness/retail) or a `cat_<x>` chip key.
    """
    db = request.app.state.db
    promoted_ids = set(await db.marketplace_promotions.distinct(
        "business_id", {"status": "active"}))
    q = {"status": "approved", **_NON_TEST}
    if category:
        q["category"] = category[4:] if category.startswith("cat_") else category
    cards = [_venue_card(p, promoted_ids)
             async for p in db.marketplace_profiles.find(q).limit(200)]
    # Sponsored first, then higher-rated.
    cards.sort(key=lambda v: (0 if v["sponsored"] else 1, -(v["rating"] or 0)))
    return {"items": cards[:limit], "count": len(cards)}
