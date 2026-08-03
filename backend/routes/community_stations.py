"""Phase 41 Session 1 — Create-My-Radio + Personal Radio Page.

Listener-facing endpoints to create, list, follow, discover, and start a
user-owned station.  Extends `podcast_creators` with a `page_type`
discriminator (non-destructive: existing podcast rows get
page_type='podcast' on first startup migration).

Compliance: non-interactive radio rules (skip cap + per-artist cap) are
enforced at queue-build by the existing radio engine — we do NOT override
those.  Per-station only affects candidate-pool filtering, not playback
discipline.
"""
from __future__ import annotations
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user, current_user_optional

router = APIRouter(prefix="/api/stations", tags=["community-stations"])
# Phase 42 S2.3 — "Now playing" strip companion endpoint. Mounted at a
# different prefix to keep the per-station CRUD namespace clean.
community_router = APIRouter(prefix="/api/community", tags=["community"])
log = logging.getLogger("bigfm.stations")

VALID_PAGE_TYPES = {"personal_radio", "business_radio", "influencer_radio",
                    "community_radio", "event_radio"}
PRIVACY_LEVELS = {"public", "unlisted", "private"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,38}[a-z0-9]$")


def _now() -> datetime: return datetime.now(timezone.utc)


async def migrate_phase41_creator_table(db) -> dict:
    """Idempotent — safe to run multiple times. Wired into server.py
    startup. Backfills `page_type='podcast'` on existing rows + creates
    new partial unique slug index. Also backfills the `privacy` field
    on community_radio_stations (legacy rows used `is_public` bool)."""
    r1 = await db.podcast_creators.update_many(
        {"page_type": {"$exists": False}},
        {"$set": {"page_type": "podcast", "follower_count": 0,
                  "verified": False, "stripe_onboarded": False,
                  "social_promotion_opt_in": False}})
    # Phase 41 S1 audit follow-up — backfill privacy on legacy rows.
    r2 = await db.community_radio_stations.update_many(
        {"privacy": {"$exists": False}, "is_public": True},
        {"$set": {"privacy": "public"}})
    r3 = await db.community_radio_stations.update_many(
        {"privacy": {"$exists": False}, "is_public": {"$ne": True}},
        {"$set": {"privacy": "private"}})
    # Phase 41 S3.A — derive `is_business` for query convenience and
    # backfill on all existing rows. Idempotent: matches both rows
    # missing the field AND legacy rows where it's null (from earlier
    # partial migrations).
    r4 = await db.community_radio_stations.update_many(
        {"$or": [{"is_business": {"$exists": False}},
                  {"is_business": None}],
         "page_type": "business_radio"},
        {"$set": {"is_business": True}})
    r5 = await db.community_radio_stations.update_many(
        {"$or": [{"is_business": {"$exists": False}},
                  {"is_business": None}],
         "page_type": {"$ne": "business_radio"}},
        {"$set": {"is_business": False}})
    try:
        await db.podcast_creators.create_index(
            "slug", unique=True, sparse=True, name="creators_slug_unique")
        await db.podcast_creators.create_index(
            [("page_type", 1), ("application_status", 1)],
            name="creators_type_status")
        await db.podcast_creators.create_index(
            "station_id", sparse=True, name="creators_station_id")
        await db.community_radio_stations.create_index(
            "station_id", unique=True, name="stations_id_unique")
        await db.community_radio_stations.create_index(
            "owner_user_id", name="stations_owner")
        await db.community_radio_stations.create_index(
            "slug", unique=True, sparse=True, name="stations_slug_unique")
        await db.community_radio_stations.create_index(
            [("status", 1), ("privacy", 1), ("follower_count", -1)],
            name="stations_discover")
    except Exception as e:
        log.warning("[phase41] index ensure: %s", e)
    return {"backfilled_creators": r1.modified_count,
            "backfilled_privacy_public": r2.modified_count,
            "backfilled_privacy_private": r3.modified_count,
            "backfilled_is_business_true": r4.modified_count,
            "backfilled_is_business_false": r5.modified_count}


def _validate_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not SLUG_RE.match(s):
        raise HTTPException(400, {"code": "bad_slug",
            "message": "Slug must be 4–40 chars, lowercase a-z, 0-9, hyphens "
                        "only. Cannot start/end with hyphen."})
    return s


# Phase 41 S1.7 — auto-derive slug from station name. Wizard no longer
# asks the user for a separate URL field; backend owns this end-to-end.
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9\s-]")
_SLUG_DASH_RE  = re.compile(r"[\s_-]+")

def _slugify(name: str) -> str:
    base = (name or "").lower()
    base = _SLUG_STRIP_RE.sub("", base)
    base = _SLUG_DASH_RE.sub("-", base).strip("-")
    return base[:50]


async def _derive_unique_slug(db, name: str) -> str:
    """Derive a unique slug from `name`. Tries `<base>`, `<base>-2`, ...
    up to `<base>-20`. If still colliding (or base is empty/too short),
    falls back to `<base>-<short-hash>` where short-hash is 6 hex chars
    from a random UUID. Never raises — always returns a usable slug."""
    base = _slugify(name)
    if not base or len(base) < 4:
        # Name is empty / emoji-only / non-Latin — synthesize a stable
        # fallback. `station-<short-hash>` reads cleanly enough as a URL.
        return f"station-{uuid.uuid4().hex[:6]}"
    # First try the bare base.
    if not await db.community_radio_stations.find_one({"slug": base}) \
       and not await db.podcast_creators.find_one({"slug": base}):
        return base
    # Then try -2 .. -20 numeric suffixes.
    for i in range(2, 21):
        cand = f"{base}-{i}"[:50]
        if not await db.community_radio_stations.find_one({"slug": cand}) \
           and not await db.podcast_creators.find_one({"slug": cand}):
            return cand
    # Fall back to short-hash. Truncate base to leave room for `-XXXXXX`.
    return f"{base[:43]}-{uuid.uuid4().hex[:6]}"


def _normalize_privacy(body: dict) -> str:
    """Honor either the new 3-tier `privacy` field or the legacy
    `is_public` bool, defaulting to 'public'."""
    p = (body.get("privacy") or "").strip().lower()
    if p in PRIVACY_LEVELS:
        return p
    if "is_public" in body:
        return "public" if body.get("is_public") else "private"
    return "public"


def _strip(s: dict) -> dict:
    """Drop internal Mongo fields before returning to clients."""
    s.pop("_id", None)
    return s


def _is_owner(station: dict, user: Optional[dict]) -> bool:
    return bool(user and station.get("owner_user_id") == user.get("user_id"))


def _visible_to(station: dict, user: Optional[dict],
                *, via_direct_link: bool = False) -> bool:
    """Visibility rules:
       - owner sees their own station regardless of status/privacy
       - public + published → visible everywhere
       - unlisted + published → visible only via direct slug link
       - private or unpublished → visible only to owner
    """
    if _is_owner(station, user):
        return True
    if station.get("status") != "published":
        return False
    privacy = station.get("privacy") or (
        "public" if station.get("is_public") else "private")
    if privacy == "public":
        return True
    if privacy == "unlisted":
        return via_direct_link
    return False  # private


@router.post("/draft")
async def create_station_draft(request: Request, body: dict,
                                user: dict = Depends(current_user)):
    """5-step wizard saves drafts here.

    Phase 41 S1.7 — `slug`/`handle` is auto-derived from `name` server-side
    with automatic collision suffixing. Wizard no longer collects it.
    For backwards-compat with any direct API caller, an explicit `slug`
    is still accepted but must validate against SLUG_RE and pass
    uniqueness — if it collides, the caller gets 409, NOT auto-suffix.
    """
    db = request.app.state.db
    name = (body.get("name") or "").strip()
    if len(name) < 1:
        raise HTTPException(400, {"code": "bad_name",
            "message": "Station name is required."})
    # Phase 41 S3.A — accept short aliases ("business" / "personal")
    # so the wizard's payload doesn't need to know the canonical enum
    # spelling.
    page_type_raw = (body.get("page_type") or "personal_radio").strip().lower()
    _PAGE_TYPE_ALIAS = {
        "personal":  "personal_radio",
        "business":  "business_radio",
        "podcast":   "podcast",          # legacy passthrough
        "event":     "event_radio",
        "influencer": "influencer_radio",
        "community": "community_radio",
    }
    page_type = _PAGE_TYPE_ALIAS.get(page_type_raw, page_type_raw)
    if page_type not in VALID_PAGE_TYPES:
        raise HTTPException(400, {"code": "bad_page_type",
                                  "allowed": sorted(VALID_PAGE_TYPES)})
    privacy = _normalize_privacy(body)

    # Slug derivation — explicit field for back-compat, auto-derive otherwise.
    explicit_slug = (body.get("slug") or body.get("handle") or "").strip()
    if explicit_slug:
        slug = _validate_slug(explicit_slug)
        if await db.community_radio_stations.find_one({"slug": slug}):
            raise HTTPException(409, {"code": "slug_taken"})
        if await db.podcast_creators.find_one({"slug": slug}):
            raise HTTPException(409, {"code": "slug_taken"})
    else:
        slug = await _derive_unique_slug(db, name)

    station_id = "stn_" + uuid.uuid4().hex[:12]
    doc = {
        "station_id":         station_id,
        "owner_user_id":      user["user_id"],
        "owner_display_name": user.get("name") or user.get("email", "").split("@")[0],
        "slug":               slug,
        "name":               name[:80],
        "tagline":            (body.get("tagline") or "")[:140],
        "bio":                (body.get("bio") or "")[:1000],
        "page_type":          page_type,
        # Music taste (step 2).
        "allowed_genres":     (body.get("genres") or [])[:5],
        "allowed_moods":      (body.get("moods")  or [])[:4],
        "allowed_energy_levels": ["medium", "high"],
        "language_mix":       [{"language": (body.get("language") or "english"),
                                "weight": 1.0}],
        # Phase D — audience defaults to 'general'.  Owners flip via
        # PATCH /api/stations/{slug}/audience.
        "audience":           "general",
        "city":               (body.get("city") or "").strip().lower()[:32] or None,
        # AI RJ persona (step 3).
        "hosts":              [{"voice_key": body.get("persona_key")
                                              or "kishore_retro",
                                "role": "primary"}],
        # Privacy (step 4) — 3-tier (public | unlisted | private).
        "privacy":            privacy,
        "is_public":          privacy == "public",  # legacy alias
        # Cover art (step 4).
        "cover_color":        body.get("cover_color") or "#00d9ff",
        "cover_image_url":    body.get("cover_image_url"),
        # Music clock — uses standard rotation.
        "music_clock":        {"rotation": ["current_hit", "retro",
                                            "mood_match", "wildcard"],
                                "cycle_length": 4},
        "status":             "draft",
        "follower_count":     0,
        "featured":           False,
        "is_business":        page_type == "business_radio",
        "created_at":         _now().isoformat(),
        "updated_at":         _now().isoformat(),
    }
    # Phase 41 S3.A — when the wizard sends a business_profile payload,
    # validate + attach it on the draft. Logo/cover are uploaded
    # separately so they're left empty here.
    if page_type == "business_radio" and body.get("business_profile"):
        from routes.business_stations import validate_business_profile
        doc["business_profile"] = validate_business_profile(
            body.get("business_profile") or {})
    await db.community_radio_stations.insert_one(doc)
    log.info("[stations] draft saved %s slug=%s owner=%s privacy=%s",
             station_id, slug, user["user_id"], privacy)
    return {"ok": True, "station_id": station_id, "slug": slug,
            "status": "draft", "privacy": privacy}


@router.post("/{station_id}/publish")
async def publish_station(station_id: str, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await db.community_radio_stations.find_one({"station_id": station_id})
    if not s or s["owner_user_id"] != user["user_id"]:
        raise HTTPException(404, {"code": "not_found"})
    await db.community_radio_stations.update_one(
        {"station_id": station_id},
        {"$set": {"status": "published", "published_at": _now().isoformat(),
                  "updated_at": _now().isoformat()}})
    return {"ok": True, "station_id": station_id, "status": "published"}


@router.get("/me")
async def my_stations(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    async for s in db.community_radio_stations.find(
            {"owner_user_id": user["user_id"]}).sort("created_at", -1):
        out.append(_strip(s))
    return {"items": out, "count": len(out)}


@router.get("/by-slug/{slug}")
async def get_station_by_slug(slug: str, request: Request,
                               user: Optional[dict] = Depends(current_user_optional)):
    """Phase 41 S1 audit fix — full visibility ladder:
       owner sees draft/private; unlisted only via direct slug; private
       hidden from non-owners; unpublished hidden from non-owners.

    Phase 41 S3.A — when `page_type==business_radio`, the
    `business_profile` is included in the response. Unverified
    profiles get a `pending_verification: true` flag and have
    sensitive fields (currently: phone) redacted for non-owners.
    Server-side `open_now` is computed best-effort from the hours
    grid; the frontend re-evaluates with the viewer's local time.
    """
    db = request.app.state.db
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if not _visible_to(s, user, via_direct_link=True):
        raise HTTPException(404, {"code": "not_found"})
    s = _strip(s)
    if s.get("page_type") == "business_radio":
        from routes.business_stations import (
            _redact_for_unverified, is_open_now)
        bp = s.get("business_profile") or {}
        is_owner_ = _is_owner(s, user)
        # Owners always see the full unredacted profile.
        if not is_owner_:
            bp = _redact_for_unverified(bp)
        s["business_profile"]    = bp
        s["pending_verification"] = not bool(bp.get("verified"))
        s["open_now"]             = is_open_now(bp)
    return s


@router.get("/discover")
async def discover_stations(request: Request,
                             user: Optional[dict] = Depends(current_user_optional),
                             genre: Optional[str] = None,
                             language: Optional[str] = None,
                             city: Optional[str] = None,
                             q: Optional[str] = None,
                             filter: Optional[str] = None,
                             limit: int = 24):
    """Phase 41 S1 audit fix — discovery surface.

    Returns 3 buckets: featured (admin-curated), trending (by 7d-window
    follower growth proxy, fallback to total followers), recent.

    Filters & search apply to ALL buckets in-memory so the surface stays
    a single round-trip for /community page.

    Privacy: only published+public stations are listed. Unlisted and
    private are never surfaced here — they live behind direct slug links.

    Phase 41 S3.A — `?filter=business` narrows to business stations
    only. `?filter=personal` narrows to non-business. No filter →
    both (existing behavior).
    """
    db = request.app.state.db
    q_filter: dict = {"status": "published", "privacy": "public"}
    if genre:
        q_filter["allowed_genres"] = genre.lower()
    if language:
        q_filter["language_mix.language"] = language.lower()
    if city:
        q_filter["city"] = city.lower()
    if q:
        rx = re.escape(q.strip())
        q_filter["$or"] = [
            {"name":    {"$regex": rx, "$options": "i"}},
            {"slug":    {"$regex": rx, "$options": "i"}},
            {"tagline": {"$regex": rx, "$options": "i"}},
        ]
    flt = (filter or "").strip().lower()
    if flt == "business":
        q_filter["is_business"] = True
    elif flt == "personal":
        # `is_business: false` includes legacy rows backfilled in
        # migrate_phase41_creator_table.
        q_filter["is_business"] = False
    cap = min(max(limit, 1), 60)

    featured: list = []
    async for s in db.community_radio_stations.find(
            {**q_filter, "featured": True}).sort("follower_count", -1).limit(cap):
        featured.append(_strip(s))

    # Trending: top followers in last 30d (proxy: created_at within 30d
    # window, sorted by follower_count desc). Falls back gracefully for
    # older stations.
    cutoff = (_now() - timedelta(days=30)).isoformat()
    trending: list = []
    async for s in db.community_radio_stations.find(
            {**q_filter, "created_at": {"$gte": cutoff}}
            ).sort("follower_count", -1).limit(cap):
        trending.append(_strip(s))
    if not trending:  # fallback to all-time top
        async for s in db.community_radio_stations.find(
                q_filter).sort("follower_count", -1).limit(cap):
            trending.append(_strip(s))

    recent: list = []
    async for s in db.community_radio_stations.find(
            q_filter).sort("created_at", -1).limit(cap):
        recent.append(_strip(s))

    total = await db.community_radio_stations.count_documents(q_filter)

    return {"featured": featured,
            "trending": trending,
            "recent":   recent,
            "filters":  {"genre": genre, "language": language,
                          "city": city, "q": q},
            "total":    total}


@router.get("/search")
async def search_stations(request: Request,
                           q: str,
                           user: Optional[dict] = Depends(current_user_optional),
                           limit: int = 20):
    """Lightweight name/slug/tagline search — same privacy rules as
    /discover (public+published only).

    Phase FUN.1.1: Results are region-aware — flagship stations matching
    the caller's region rank first, then other-region flagships, then
    priority Dubai stations, then follower-count-sorted matches."""
    db = request.app.state.db
    rx = re.escape(q.strip())
    cap = min(max(limit, 1), 50)
    out: list = []
    async for s in db.community_radio_stations.find({
            "status":  "published",
            "privacy": "public",
            "$or":     [{"name":    {"$regex": rx, "$options": "i"}},
                          {"slug":    {"$regex": rx, "$options": "i"}},
                          {"tagline": {"$regex": rx, "$options": "i"}}]
            }).sort("follower_count", -1).limit(cap):
        out.append(_strip(s))
    # Also fold in flagship matches from imported_radio_stations so the
    # global search box surfaces the FunAsia flagships when a user types
    # e.g. "talk", "bollywood", "punjabi".
    flag_docs = await db.imported_radio_stations.find({
        "is_flagship": True,
        "$or": [
            {"name":                                {"$regex": rx, "$options": "i"}},
            {"flagship_categories":       {"$in": [q.lower()]}},
            {"flagship_search_terms":  {"$in": [q.lower()]}},
            {"language_codes":              {"$in": [q.lower()]}},
        ]}).limit(cap).to_list(cap)
    for fd in flag_docs:
        out.append({
            "station_id":         fd.get("id"),
            "name":                     fd.get("name"),
            "slug":                     fd.get("flagship_slug"),
            "tagline":                 fd.get("description"),
            "favicon":                fd.get("favicon"),
            "logo_url":              fd.get("logo_url") or fd.get("favicon"),
            "url_resolved":     fd.get("url_resolved"),
            "is_flagship":         True,
            "is_priority":         False,
            "flagship_region": fd.get("flagship_region"),
            "flagship_priority":  fd.get("flagship_priority"),
            "source":                 "imported_flagship",
        })
    # Region-aware priority sort.
    from services.geo_flagship import get_user_region, sort_with_flagship_priority
    user_region = await get_user_region(user, request)
    out = sort_with_flagship_priority(out, user_region)
    return {"items": out, "count": len(out), "q": q,
                    "user_region": user_region}


@router.post("/{station_id}/follow")
async def follow_station(station_id: str, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await db.community_radio_stations.find_one({"station_id": station_id})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if s["owner_user_id"] == user["user_id"]:
        raise HTTPException(400, {"code": "cannot_follow_own"})
    # Idempotent — unique (user_id, station_id)
    r = await db.station_followers.update_one(
        {"user_id": user["user_id"], "station_id": station_id},
        {"$setOnInsert": {"followed_at": _now().isoformat()}},
        upsert=True)
    if r.upserted_id:
        await db.community_radio_stations.update_one(
            {"station_id": station_id}, {"$inc": {"follower_count": 1}})
    # Phase 41M.B — fire-and-forget first_follower + vip badge grant.
    try:
        from services.station_badge_engine import grant_safe
        asyncio.create_task(grant_safe(
            db, user_id=user["user_id"], station_id=station_id,
            station_slug=s.get("slug"),
            only_types={"first_follower", "vip"}))
    except Exception as e:
        log.warning("[community_stations] badge hook (follow) failed: %s", e)
    return {"ok": True, "now_following": True}


@router.post("/{station_id}/unfollow")
async def unfollow_station(station_id: str, request: Request,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.station_followers.delete_one(
        {"user_id": user["user_id"], "station_id": station_id})
    if r.deleted_count:
        await db.community_radio_stations.update_one(
            {"station_id": station_id}, {"$inc": {"follower_count": -1}})
    return {"ok": True, "now_following": False}


@router.get("/{station_id}/follow/status")
async def follow_status(station_id: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.station_followers.find_one(
        {"user_id": user["user_id"], "station_id": station_id})
    return {"following": bool(r)}


# -----------------------------------------------------------------
# Phase 41 S1 audit fix — radio engine queue plumbing.
# Exposed as a helper so server.py:_resolve_channel can fall through
# to community stations after the admin-channel lookup misses.
# -----------------------------------------------------------------

def station_to_channel_dict(station: dict) -> dict:
    """Coerce a community_radio_stations row into the channel-dict shape
    consumed by services.channel_filter / channel_supports_duo / the
    radio engine. Returns a NEW dict — caller can mutate freely.

    Notable mappings:
      slug         -> _id      (engine identifies channels by _id)
      station_id   -> station_id  (preserved for analytics)
      page_type    -> page_type   (preserved; engine ignores)
      music_clock  -> music_clock (preserved; engine consumes verbatim)

    The returned dict is marked `active=True` and `exclusivity_tier='free'`
    so the existing free/premium access gate lets anyone listen.
    """
    return {
        "_id":              station["slug"],
        "station_id":       station.get("station_id"),
        "name":             station.get("name") or station["slug"],
        "tagline":          station.get("tagline"),
        "description":     station.get("bio"),
        "cover_color":     station.get("cover_color"),
        "cover_image_url": station.get("cover_image_url"),
        "active":           True,
        "exclusivity_tier": "free",
        "language_mix":     station.get("language_mix") or [],
        "allowed_genres":   station.get("allowed_genres") or [],
        "allowed_moods":    station.get("allowed_moods") or [],
        "allowed_energy_levels": station.get("allowed_energy_levels") or [],
        "hosts":            station.get("hosts") or [],
        "music_clock":      station.get("music_clock") or {},
        "default_for_time": [],
        "page_type":        station.get("page_type"),
        "owner_user_id":    station.get("owner_user_id"),
        # Marker so engine code can branch if it ever needs to.
        "_source":          "community_station",
    }


async def lookup_community_channel(db, slug: str,
                                    *, user: Optional[dict] = None) -> Optional[dict]:
    """Used by server.py:_resolve_channel as a fallback after the admin
    channels collection lookup misses. Honors the same visibility ladder
    as /api/stations/by-slug — owner can always listen to their own
    drafts/private; unlisted via direct slug; private never to non-owners.
    """
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        return None
    if not _visible_to(s, user, via_direct_link=True):
        return None
    return station_to_channel_dict(s)


# -----------------------------------------------------------------
# Phase 42 S2.3 — "Now playing on community radio" strip backing
# endpoint. Lives under /api/community to keep the /api/stations
# namespace strictly for per-station CRUD.
# -----------------------------------------------------------------

_NOW_PLAYING_CACHE: dict = {"value": None, "expires_at": 0.0}
_NOW_PLAYING_TTL_SEC = 10.0


@community_router.get("/now_playing")
async def community_now_playing(request: Request):
    """Returns the top live community station for the page-top strip.

    Phase 41 S2.B upgrade — **3-tier fallback**:
      1. station with the highest live listener count (last 90s)
      2. station with the highest follower_count
      3. most recently published station

    Bug B addendum — also returns the listener's resolved city
    (``preferred_city`` → IP geo → 'Global') as ``resolved_city`` so
    the frontend strip can keep header + 'Namaste {city}' footer in
    sync without a second round-trip.

    In-process cache: 10s TTL so the strip polling burst doesn't
    hammer the live-count aggregation. Cache key intentionally
    skips the per-listener city — the city is appended post-cache.
    """
    import time
    now = time.time()
    cached = _NOW_PLAYING_CACHE
    if cached["value"] is not None and cached["expires_at"] > now:
        return {**cached["value"],
                  "resolved_city": await _resolve_listener_city(request)}

    db = request.app.state.db
    tier = None
    s = None
    listener_count = 0
    # Tier 1 — live listener count
    try:
        from routes.listener_sessions import top_station_by_live_count
        live = await top_station_by_live_count(db)
        if live and live.get("station"):
            s = live["station"]
            listener_count = int(live.get("live_count") or 0)
            tier = "live"
    except Exception as e:
        log.warning("[now_playing] tier1 live-count failed: %s", e)

    # Tier 2 — most-followed
    if s is None:
        s = await db.community_radio_stations.find_one(
            {"status": "published", "privacy": "public",
             "follower_count": {"$gt": 0}},
            sort=[("follower_count", -1), ("published_at", -1)])
        if s:
            listener_count = max(int(s.get("follower_count") or 0), 1)
            tier = "followers"

    # Tier 3 — most recent published
    if s is None:
        s = await db.community_radio_stations.find_one(
            {"status": "published", "privacy": "public"},
            sort=[("published_at", -1)])
        if s:
            listener_count = 1   # never read "0" — deflating
            tier = "recent"

    if not s:
        payload = {"station": None,
                   "fallback_message": "Start your own community radio →",
                   "tier": None}
    else:
        payload = {"station": {
            "slug":             s["slug"],
            "name":             s.get("name") or s["slug"],
            "listener_count":   listener_count,
            "cover_image_url": s.get("cover_image_url"),
            "cover_color":      s.get("cover_color"),
        }, "fallback_message": None,
           "tier":             tier}

    _NOW_PLAYING_CACHE["value"] = payload
    _NOW_PLAYING_CACHE["expires_at"] = now + _NOW_PLAYING_TTL_SEC
    return {**payload, "resolved_city": await _resolve_listener_city(request)}


async def _resolve_listener_city(request: Request) -> str:
    """Bug B helper — best-effort listener city for the now_playing strip.

    Runs the standard ``services.geo.resolve_geo_from_ip`` chain (ip →
    tz → mock). Anonymous-safe — we don't need a JWT here because the
    strip is public. Returns the resolved display label, falling back
    to ``"Global"`` so the frontend strip never blanks out.
    """
    try:
        from services import geo as geo_svc
        resolved = await geo_svc.resolve_geo_from_ip(
            request, request.app.state.db)
        return resolved.get("city") or "Global"
    except Exception:
        return "Global"


# Phase 41 S2.C.2 — Live Heat ribbon source data.
_LIVE_NOW_CACHE: dict = {"value": None, "expires_at": 0.0}
_LIVE_NOW_TTL_SEC = 10.0


@community_router.get("/live_now")
async def community_live_now(request: Request, limit: int = 3):
    """Top-N public published stations by current live listener count.
    Powers the `LiveHeatRibbon` on `/community`. Returns an empty array
    when no live listeners exist anywhere → frontend hides the ribbon.

    Uses the same 90s live window as `listener_sessions` (90 seconds
    since last_ping_at). In-process 10s cache.
    """
    import time
    cap = max(1, min(int(limit or 3), 10))
    now = time.time()
    cached = _LIVE_NOW_CACHE
    if cached["value"] is not None and cached["expires_at"] > now:
        # Re-slice cached payload to caller's `limit`.
        items = (cached["value"].get("stations") or [])[:cap]
        return {"stations": items}

    db = request.app.state.db
    from routes.listener_sessions import LIVE_WINDOW_SEC
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=LIVE_WINDOW_SEC)
    pipeline = [
        {"$match": {"ended_at": None,
                     "last_ping_at": {"$gt": cutoff}}},
        {"$group": {"_id": "$station_slug", "count": {"$sum": 1}}},
        {"$sort":  {"count": -1}},
        {"$limit": 10},   # cache top 10, slice per-caller
    ]
    out: list = []
    async for row in db.listener_sessions.aggregate(pipeline):
        slug = row["_id"]
        s = await db.community_radio_stations.find_one(
            {"slug": slug, "status": "published", "privacy": "public"})
        if not s:
            continue
        out.append({
            "slug":             s["slug"],
            "name":             s.get("name") or s["slug"],
            "listener_count":   int(row["count"]),
            "cover_image_url": s.get("cover_image_url"),
            "cover_color":      s.get("cover_color") or "#00d9ff",
        })
    payload = {"stations": out[:10]}
    _LIVE_NOW_CACHE["value"] = payload
    _LIVE_NOW_CACHE["expires_at"] = now + _LIVE_NOW_TTL_SEC
    return {"stations": out[:cap]}


# -----------------------------------------------------------------
# Phase 41 P1-interrupt — Radio tab "Community Radio" surface.
# -----------------------------------------------------------------

_TOP_LISTENED_CACHE: dict = {"value": None, "expires_at": 0.0}
_TOP_LISTENED_TTL_SEC = 10.0


def _summarize_for_radio_strip(s: dict, listener_count: int, tier: str) -> dict:
    """Compact per-card payload for the Radio tab Community Radio strip."""
    is_business = bool(s.get("is_business")) \
        or s.get("page_type") == "business_radio"
    bp = s.get("business_profile") or {}
    bps = None
    if is_business:
        bps = {
            "category": bp.get("category"),
            "verified": bool(bp.get("verified")),
        }
    return {
        "slug":              s["slug"],
        "name":              s.get("name") or s["slug"],
        "cover_image_url":  s.get("cover_image_url"),
        "cover_color":       s.get("cover_color") or "#00d9ff",
        # Phase C — artwork_status drives the "Generating cover…" pill on
        # freshly-created stations.  Falls back to "complete" when the
        # station already has a real cover_image_url (back-compat for
        # stations created before Phase C).
        "artwork_status":   (s.get("artwork_status")
                                    or ("complete" if s.get("cover_image_url") else "idle")),
        "artwork_source":   s.get("artwork_source"),
        "page_type":         s.get("page_type") or "personal_radio",
        "follower_count":    int(s.get("follower_count") or 0),
        "listener_count":    int(listener_count),
        "tier":              tier,
        "business_profile_summary": bps,
    }


@community_router.get("/top_listened")
async def community_top_listened(request: Request,
                                    limit: int = 10):
    """Top-N most-listened public published community stations for the
    `/radio` tab's Community Radio strip.

    3-tier fallback (matches the `now_playing` pattern so quiet hours
    still surface real content):
       1. live listener count (90s window, listener_sessions)
       2. follower_count  (most-followed)
       3. published_at    (most-recently-published)

    Results are de-duplicated across tiers and capped at `limit`
    (default 10, max 50). 10-second in-process cache.
    """
    import time
    cap = max(1, min(int(limit or 10), 50))
    now = time.time()
    cached = _TOP_LISTENED_CACHE
    if cached["value"] is not None and cached["expires_at"] > now:
        items = (cached["value"].get("stations") or [])[:cap]
        return {"stations": items,
                "tier_used": cached["value"].get("tier_used")}

    db = request.app.state.db
    seen: set[str] = set()
    out: list[dict] = []
    tier_used: Optional[str] = None

    # Tier 1 — live (last 90s)
    try:
        from routes.listener_sessions import LIVE_WINDOW_SEC
        from datetime import timedelta as _td
        cutoff = datetime.now(timezone.utc) - _td(seconds=LIVE_WINDOW_SEC)
        pipeline = [
            {"$match": {"ended_at": None,
                          "last_ping_at": {"$gt": cutoff}}},
            {"$group": {"_id": "$station_slug", "count": {"$sum": 1}}},
            {"$sort":  {"count": -1}},
            {"$limit": cap},
        ]
        async for row in db.listener_sessions.aggregate(pipeline):
            slug = row["_id"]
            s = await db.community_radio_stations.find_one(
                {"slug": slug, "status": "published",
                 "privacy": "public"})
            if not s or slug in seen:
                continue
            seen.add(slug)
            out.append(_summarize_for_radio_strip(s, int(row["count"]),
                                                       "live"))
            if len(out) >= cap:
                break
        if out:
            tier_used = "live"
    except Exception as e:
        log.warning("[top_listened] tier1 live failed: %s", e)

    # Tier 2 — most-followed
    if len(out) < cap:
        cursor = db.community_radio_stations.find(
            {"status": "published", "privacy": "public",
             "follower_count": {"$gt": 0},
             "slug": {"$nin": list(seen)}},
            sort=[("follower_count", -1), ("published_at", -1)]).limit(cap)
        async for s in cursor:
            slug = s["slug"]
            if slug in seen:
                continue
            seen.add(slug)
            out.append(_summarize_for_radio_strip(
                s, int(s.get("follower_count") or 0), "followers"))
            if len(out) >= cap:
                break
        if out and tier_used is None:
            tier_used = "followers"

    # Tier 3 — most recent published
    if len(out) < cap:
        cursor = db.community_radio_stations.find(
            {"status": "published", "privacy": "public",
             "slug": {"$nin": list(seen)}},
            sort=[("published_at", -1)]).limit(cap)
        async for s in cursor:
            slug = s["slug"]
            if slug in seen:
                continue
            seen.add(slug)
            out.append(_summarize_for_radio_strip(s, 0, "recent"))
            if len(out) >= cap:
                break
        if out and tier_used is None:
            tier_used = "recent"

    payload = {"stations": out, "tier_used": tier_used}
    _TOP_LISTENED_CACHE["value"] = payload
    _TOP_LISTENED_CACHE["expires_at"] = now + _TOP_LISTENED_TTL_SEC
    return payload
