"""YouTube-style consumer shell — additive read + user-preference endpoints.

Powers the redesigned AppShell: live nav badges, config-driven filter chips
with LIVE counts, the "Your stations" flagship list, and a per-user theme
preference (dark default). Read-only + a tiny prefs writer — no existing
route, auth, or earn-rate logic is touched.
"""
from fastapi import APIRouter, Request, Body
from auth import current_user, current_user_optional

router = APIRouter(prefix="/api/shell")

VALID_THEMES = {"dark", "light"}

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
    shop_offers = await db.marketplace_profiles.count_documents({})
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
        n = await db.marketplace_profiles.count_documents({"category": cat})
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
