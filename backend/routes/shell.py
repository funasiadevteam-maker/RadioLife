"""YouTube-style consumer shell — additive read + user-preference endpoints.

Powers the redesigned AppShell: live nav badges, config-driven filter chips
with LIVE counts, the "Your stations" flagship list, and a per-user theme
preference (dark default). Read-only + a tiny prefs writer — no existing
route, auth, or earn-rate logic is touched.
"""
from fastapi import APIRouter, Request, Body, HTTPException
from auth import current_user, current_user_optional
from services.station_art import resolve_art as _resolve_art
from core.home_config import get_home_config, build_fuusic_world, TOGETHER_ACTIONS
from core.content_language import (
    user_content_languages, user_show_all, user_filter_scopes,
    station_language_or_query, content_allowed,
)
from datetime import datetime, timezone, timedelta
import re

router = APIRouter(prefix="/api/shell")

VALID_THEMES = {"dark", "light", "system"}
VALID_ACCENTS = {"violet", "coral", "teal", "amber", "blue"}
_DEFAULT_SCHEDULE = {"enabled": False, "dark_hour": 19, "light_hour": 7}
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


@router.get("/recommended-genres")
async def recommended_genres(request: Request):
    """Starter genres ranked by what's actually in the catalog (tracks +
    channels) — powers the onboarding "Popular on FUUSIC" picks instead of a
    hardcoded list."""
    db = request.app.state.db
    counts: dict[str, int] = {}

    def _bump(g, n=1):
        if g:
            k = str(g).strip().lower()
            if k:
                counts[k] = counts.get(k, 0) + n

    try:
        async for r in db.tracks.aggregate([
            {"$match": {"genre": {"$nin": [None, ""]}}},
            {"$group": {"_id": "$genre", "n": {"$sum": 1}}},
        ]):
            _bump(r["_id"], int(r["n"]))
    except Exception:
        pass
    try:
        async for ch in db.channels.find(
                {"active": True}, {"allowed_genres": 1, "music_genre": 1}):
            for g in (ch.get("allowed_genres") or []):
                _bump(g, 2)
            _bump(ch.get("music_genre"), 2)
    except Exception:
        pass

    ranked = [g for g, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
    return {"genres": ranked[:8], "source": "catalog", "total": len(counts)}



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


def _clean_schedule(raw) -> dict:
    s = dict(_DEFAULT_SCHEDULE)
    if isinstance(raw, dict):
        s["enabled"] = bool(raw.get("enabled", s["enabled"]))
        for k in ("dark_hour", "light_hour"):
            try:
                v = int(raw.get(k, s[k]))
                if 0 <= v <= 23:
                    s[k] = v
            except (TypeError, ValueError):
                pass
    return s


@router.get("/prefs")
async def get_prefs(request: Request):
    user = await current_user_optional(request)
    if not user:
        return {"theme": "dark", "accent": "violet", "theme_schedule": dict(_DEFAULT_SCHEDULE)}
    db = request.app.state.db
    doc = await db.users.find_one({"user_id": user["user_id"]}, {"prefs": 1})
    prefs = (doc or {}).get("prefs") or {}
    theme = prefs.get("theme", "dark")
    accent = prefs.get("accent", "violet")
    return {
        "theme": theme if theme in VALID_THEMES else "dark",
        "accent": accent if accent in VALID_ACCENTS else "violet",
        "theme_schedule": _clean_schedule(prefs.get("theme_schedule")),
    }


@router.put("/prefs")
async def put_prefs(request: Request, body: dict = Body(default={})):
    user = await current_user(request)
    db = request.app.state.db
    sets = {}
    if "theme" in body:
        theme = body.get("theme")
        sets["prefs.theme"] = theme if theme in VALID_THEMES else "dark"
    if "accent" in body:
        accent = body.get("accent")
        sets["prefs.accent"] = accent if accent in VALID_ACCENTS else "violet"
    if "theme_schedule" in body:
        sets["prefs.theme_schedule"] = _clean_schedule(body.get("theme_schedule"))
    if sets:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": sets})
    doc = await db.users.find_one({"user_id": user["user_id"]}, {"prefs": 1})
    prefs = (doc or {}).get("prefs") or {}
    return {
        "ok": True,
        "theme": prefs.get("theme", "dark"),
        "accent": prefs.get("accent", "violet"),
        "theme_schedule": _clean_schedule(prefs.get("theme_schedule")),
    }


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



# ─────────────────────────────────────────────────────────────────────
# Audio-first Home (Classic-B / Home Audio V2) aggregator + analytics.
# "Value before advertising": one call returns the listening rails first,
# then the native/sponsored placements. Reuses the EXISTING ad / campaign /
# marketplace / flagship-boost engines — no second ad engine.
# ─────────────────────────────────────────────────────────────────────

HOME_EVENT_ALLOWLIST = {
    "home_ad_request", "home_ad_fill", "home_ad_impression", "home_ad_click",
    "sponsored_station_impression", "sponsored_station_start",
    "native_offer_impression", "native_offer_click",
    "companion_impression", "companion_click",
    "audio_ad_start", "audio_ad_complete", "attributed_conversion",
    # FUUSIC Home realignment — ecosystem/social engagement.
    "home_fuusic_world_view", "home_pillar_click",
    "home_social_click", "home_listen_click", "home_live_click",
    "home_shop_click", "home_play_click", "home_dining_click",
    "home_earn_click", "home_explore_click",
    "home_together_action_click", "home_whats_happening_click",
}


def _station_card(s: dict) -> dict:
    art_url, art_source = _resolve_art(s)
    return {
        "id": s.get("id") or s.get("station_id"),
        "slug": s.get("flagship_slug") or s.get("slug"),
        "name": s.get("name"),
        "city": s.get("country"),
        "art": art_url,
        "art_source": art_source,
        "live": bool(s.get("is_live")),
        "listeners": int(s.get("listeners") or 0),
        "language": s.get("language"),
        "sponsored": False,
    }


async def _flagship_stations(db, limit: int = 12, lang_or: dict = None) -> list:
    query = {"flagship_slug": {"$ne": None}}
    if lang_or:
        query = {"$and": [query, lang_or]}
    out = []
    async for s in db.imported_radio_stations.find(query).limit(limit):
        out.append(_station_card(s))
    return out


async def _personalize(db, user, cards):
    """Reorder station cards so the user's recently-played / preferred ones
    surface first. Best-effort; falls back to the input order."""
    if not user or not cards:
        return cards
    recent_ids = set()
    try:
        cur = db.playback_logs.find(
            {"user_id": user["user_id"]},
            {"station_id": 1, "channel_id": 1}).sort("_id", -1).limit(60)
        async for p in cur:
            sid = p.get("station_id") or p.get("channel_id")
            if sid:
                recent_ids.add(sid)
    except Exception:
        recent_ids = set()
    fav_genres = set()
    try:
        pv = (user.get("preference_vector") or {})
        fav_genres = {str(g).lower() for g in (pv.get("favorite_genres") or [])}
    except Exception:
        fav_genres = set()
    if not recent_ids and not fav_genres:
        return cards

    def _score(c):
        s = 0
        if c["id"] in recent_ids:
            s -= 10
        name = (c.get("name") or "").lower()
        if fav_genres and any(g in name for g in fav_genres):
            s -= 3
        if c.get("live"):
            s -= 1
        return s
    return sorted(cards, key=_score)


async def _pick_sponsored_station(db):
    """Return (station_id, advertiser_business_id) for a LIVE flagship-boost
    activation, else (None, None). Truthful — only paid inventory; never
    manipulates organic ranking beyond reserving the labelled slot."""
    try:
        act = await db.flagship_boost_activations.find_one({"status": "live"})
        if act and act.get("station_id"):
            return act.get("station_id"), act.get("advertiser_business_id")
    except Exception:
        pass
    return None, None


async def _native_offer(db, city: str):
    """One labelled native sponsored card. Prefers a promoted marketplace
    business, then an active advertiser campaign. None when no paid/native
    inventory exists (client hides the block)."""
    try:
        promoted_ids = await db.marketplace_promotions.distinct(
            "business_id", {"status": "active"})
    except Exception:
        promoted_ids = []
    if promoted_ids:
        p = await db.marketplace_profiles.find_one(
            {"business_id": {"$in": promoted_ids}, "status": "approved", **_NON_TEST})
        if p:
            bp = p.get("bigpoints") or {}
            cat = p.get("category")
            return {
                "kind": "shop",
                "sponsored": True,
                "business_id": p.get("business_id"),
                "title": p.get("public_name"),
                "subtitle": (f"Earn {bp.get('default_points')} BigPoints"
                             if bp.get("default_points")
                             else _CAT_LABEL.get(cat, "Local offer")),
                "image": (p.get("cover_urls") or [None])[0] or p.get("logo_url"),
                "cta": "View offer",
                "to": f"/shop/{p.get('business_id')}",
            }
    camp = await db.campaigns.find_one(
        {"status": "active", "clip_image_url": {"$nin": [None, ""]}},
        sort=[("created_at", -1)])
    if camp:
        name = camp.get("name") or "Sponsored"
        sponsor, _, offer = name.partition("—")
        return {
            "kind": "offer",
            "sponsored": True,
            "campaign_id": camp.get("campaign_id"),
            "business_id": camp.get("business_id"),
            "title": (offer.strip() or name),
            "subtitle": (sponsor.strip() or "Sponsored offer"),
            "image": camp.get("clip_image_url"),
            "cta": "View offer",
            "to": (f"/shop/{camp.get('business_id')}"
                   if camp.get("business_id") else "/offers"),
        }
    return None


async def _mixed_for_you(db, user, city, station_cards, native_offer):
    """For You beyond audio — interleave stations with a Moment, a live
    room/show, an offer and a game, each tagged with `type` + `badge` so the
    client can render mixed cards. Purely additive; every card carries `to`."""
    stations = []
    for c in (station_cards or [])[:6]:
        sid = c.get("id")
        stations.append({
            "id": sid, "type": "station", "badge": "Station",
            "title": c.get("name"), "subtitle": c.get("city") or "Radio",
            "image": c.get("art"), "live": bool(c.get("live")),
            "language": c.get("language"),
            "to": (f"/radio/station/{sid}?autoplay=1" if sid else "/radio"),
        })
    extras = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        m = await db.social_moments.find_one(
            {"visibility": "public", "media_url": {"$nin": [None, ""]},
             "created_at": {"$gte": cutoff}}, sort=[("created_at", -1)])
        if m:
            extras.append({
                "id": m["_id"], "type": "moment", "badge": "Moment",
                "title": (m.get("caption") or "A new Moment")[:60],
                "subtitle": "From the FUUSIC community",
                "image": m.get("media_url"), "to": "/social?tab=moments",
            })
    except Exception:
        pass
    try:
        _apply_live = not user_show_all(user) and user_filter_scopes(user).get("music")
        _live_prefs = user_content_languages(user) if _apply_live else None

        def _live_ok(txt, explicit=None):
            return (not _apply_live) or content_allowed(txt, _live_prefs, explicit=explicit)

        ls = await db.live_shows.find_one(
            {"status": "live"}, sort=[("started_at", -1)])
        if ls and _live_ok(
                f"{ls.get('title', '')} {ls.get('description', '')} {ls.get('business_name', '')}",
                ls.get("language")):
            extras.append({
                "id": ls["_id"], "type": "live", "badge": "Live", "live": True,
                "title": ls.get("title") or ls.get("business_name") or "Live now",
                "subtitle": ls.get("business_name") or "FUUSIC Live",
                "image": ls.get("cover_url"), "to": "/social?tab=live",
            })
        else:
            rm = await db.listen_rooms.find_one(
                {"active": True}, sort=[("last_active_at", -1)])
            content = (rm or {}).get("content") or {}
            if rm and _live_ok(f"{content.get('name', '')} {rm.get('title', '')}"):
                extras.append({
                    "id": rm["_id"], "type": "live", "badge": "Live", "live": True,
                    "title": content.get("name") or rm.get("title") or "Listening room",
                    "subtitle": "Listen together", "image": content.get("favicon"),
                    "to": f"/social/room/{rm['_id']}",
                })
    except Exception:
        pass
    if native_offer:
        extras.append({
            "id": (native_offer.get("business_id") or native_offer.get("campaign_id") or "offer"),
            "type": "offer", "badge": "Offer", "sponsored": True,
            "title": native_offer.get("title"), "subtitle": native_offer.get("subtitle"),
            "image": native_offer.get("image"), "to": native_offer.get("to") or "/shop",
            "business_id": native_offer.get("business_id"),
            "campaign_id": native_offer.get("campaign_id"), "kind": native_offer.get("kind"),
        })
    try:
        g = await db.game_campaigns.find_one(
            {"status": "active"}, sort=[("created_at", -1)])
        if g:
            extras.append({
                "id": g.get("campaign_id"), "type": "game", "badge": "Play",
                "title": g.get("name") or "Play & Win",
                "subtitle": "Games, trivia & prizes",
                "image": g.get("clip_image_url") or g.get("cover_url"),
                "to": "/play-and-win",
            })
    except Exception:
        pass

    out = []
    ei = 0
    for sc in stations:
        out.append(sc)
        if ei < len(extras):
            out.append(extras[ei])
            ei += 1
    while ei < len(extras):
        out.append(extras[ei])
        ei += 1
    return out[:10]


@router.get("/home")
async def shell_home(request: Request, city: str = ""):
    """Audio-first Home payload (platform-agnostic — web + mobile).
    Rails first (for_you, live_now, listening_reward, dining), then the
    single native sponsored placement + premium flag for display gating."""
    from services.dining_club import get_subscription as _dc_get_subscription
    from services.premium_gate import is_premium_or_trial
    db = request.app.state.db
    user = await current_user_optional(request)
    # Match the banner endpoint's ad-free rule so the Home display banner
    # hides for exactly the users the ad decision blocks (premium + ad_free).
    is_premium = bool(user and is_premium_or_trial(user)
                      and (user.get("ad_settings") or {}).get("ad_free_enabled", True))

    # Content-language HARD filter on Home station rails (music scope) so even
    # curated flagship picks respect the user's languages. Neutral stays.
    _lang_or = None
    if not user_show_all(user) and user_filter_scopes(user).get("music"):
        _lang_or = station_language_or_query(user_content_languages(user))
    cards = await _flagship_stations(db, 12, lang_or=_lang_or)
    if len(cards) < 4 and _lang_or:  # safety: don't leave Home empty
        cards = await _flagship_stations(db, 12)
    for_you = (await _personalize(db, user, [dict(c) for c in cards]))[:6]

    # Live Right Now — live-first; reserve ONE labelled sponsored slot.
    live_sorted = sorted(
        cards, key=lambda c: (0 if c["live"] else 1, -(c["listeners"] or 0)))
    live_now = [dict(c) for c in live_sorted[:6]]
    sp_station_id, sp_biz = await _pick_sponsored_station(db)
    if sp_station_id:
        idx = next((i for i, c in enumerate(live_now)
                    if c["id"] == sp_station_id), None)
        card = None
        if idx is not None:
            card = live_now.pop(idx)
        else:
            s = await db.imported_radio_stations.find_one(
                {"$or": [{"id": sp_station_id}, {"station_id": sp_station_id}]})
            if s:
                card = _station_card(s)
        if card:
            card["sponsored"] = True
            card["sponsor_business_id"] = sp_biz
            live_now.insert(min(3, len(live_now)), card)

    native_offer = await _native_offer(db, city)

    # Live Hero Vibe — the listener's top genre. Onboarding step 2 saves
    # `preference_vector.genres`; fall back to `favorite_genres`. Nullable.
    top_genre = None
    try:
        pv = (user or {}).get("preference_vector") or {}
        src = pv.get("genres") or pv.get("favorite_genres") or []
        if src:
            top_genre = str(src[0]).replace("_", " ").strip().title() or None
    except Exception:
        top_genre = None

    dining = {"member": False}
    if user:
        try:
            sub = await _dc_get_subscription(db, user["user_id"])
            dining = {"member": bool(sub and sub.get("status") == "active")}
        except Exception:
            dining = {"member": False}

    # FUUSIC ecosystem — config-driven pillars + section layout (Social-first
    # default). Backward-compatible: existing fields above are unchanged.
    cfg = await get_home_config(db)
    fuusic_world = build_fuusic_world(cfg["pillar_order"])
    mixed_for_you = await _mixed_for_you(db, user, city, for_you, native_offer)

    return {
        "for_you": for_you,
        "mixed_for_you": mixed_for_you,
        "live_now": live_now,
        "native_offer": native_offer,
        "listening_reward": {"points_per_min": 1},
        "dining": dining,
        "is_premium": is_premium,
        "top_genre": top_genre,
        "fuusic_world": fuusic_world,
        "together_actions": TOGETHER_ACTIONS,
        "pillar_order": cfg["pillar_order"],
        "home_config": cfg["sections"],
    }


@router.post("/home-events")
async def shell_home_events(request: Request, body: dict = Body(default={})):
    """Ingest Home + audio→digital attribution analytics. Fire-and-forget;
    validated against an allowlist; never mutates listener wallets."""
    user = await current_user_optional(request)
    event = (body or {}).get("event")
    if event not in HOME_EVENT_ALLOWLIST:
        return {"ok": False, "error": "unknown_event"}
    db = request.app.state.db
    try:
        await db.home_ad_events.insert_one({
            "event": event,
            "user_id": (user or {}).get("user_id"),
            "campaign_id": (body or {}).get("campaign_id"),
            "station_id": (body or {}).get("station_id"),
            "business_id": (body or {}).get("business_id"),
            "kind": (body or {}).get("kind"),
            "surface": (body or {}).get("surface"),
            "variant": (body or {}).get("variant"),
            "market": (body or {}).get("market"),
            "meta": (body or {}).get("meta"),
            "ts": _now_iso(),
        })
    except Exception:
        return {"ok": False}
    return {"ok": True}


# ─── Public landing analytics (anon capture + admin report) ──────────
_LANDING_EVENTS = {"cta", "section_view", "preview_play"}


@router.post("/landing-event")
async def landing_event(request: Request, body: dict = Body(default={})):
    """Anonymous-friendly capture of public V2 landing CTA clicks + views."""
    ev = str((body or {}).get("event") or "").strip()[:40]
    if ev not in _LANDING_EVENTS:
        return {"ok": False, "error": "unknown_event"}
    db = request.app.state.db
    try:
        user = await current_user_optional(request)
    except Exception:
        user = None
    try:
        await db.landing_events.insert_one({
            "event": ev,
            "cta": (str((body or {}).get("cta") or "")[:60] or None),
            "section": (str((body or {}).get("section") or "")[:60] or None),
            "session_id": (str((body or {}).get("session_id") or "")[:64] or None),
            "user_id": (user or {}).get("user_id"),
            "ts": _now_iso(),
        })
    except Exception:
        return {"ok": False}
    return {"ok": True}


@router.get("/landing-analytics")
async def landing_analytics(request: Request):
    """Admin-only aggregated engagement counts for the public V2 landing."""
    user = await current_user_optional(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(403, {"code": "forbidden"})
    db = request.app.state.db

    async def _top(match_event: str, key: str):
        pipeline = [
            {"$match": {"event": match_event, key: {"$ne": None}}},
            {"$group": {"_id": f"${key}", "count": {"$sum": 1},
                        "sessions": {"$addToSet": "$session_id"}}},
            {"$sort": {"count": -1}},
            {"$limit": 50},
        ]
        rows = []
        async for r in db.landing_events.aggregate(pipeline):
            rows.append({"key": r["_id"], "count": r["count"],
                         "sessions": len([s for s in (r.get("sessions") or []) if s])})
        return rows

    async def _tiles():
        pipeline = [
            {"$match": {"event": "cta", "cta": {"$regex": "^tile_"}}},
            {"$group": {"_id": "$cta", "count": {"$sum": 1},
                        "sessions": {"$addToSet": "$session_id"}}},
            {"$sort": {"count": -1}},
            {"$limit": 50},
        ]
        rows = []
        async for r in db.landing_events.aggregate(pipeline):
            rows.append({"key": str(r["_id"]).replace("tile_", ""), "count": r["count"],
                         "sessions": len([s for s in (r.get("sessions") or []) if s])})
        return rows

    return {
        "total_events": await db.landing_events.count_documents({}),
        "preview_plays": await db.landing_events.count_documents({"event": "preview_play"}),
        "ctas": await _top("cta", "cta"),
        "tiles": await _tiles(),
        "sections": await _top("section_view", "section"),
    }
