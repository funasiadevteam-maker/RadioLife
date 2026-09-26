"""FUUSIC — Gamified Bar Purchase (Phase 5).

After a customer buys at a bar / club-lounge (any paid marketplace order at that
venue), they UNLOCK a drink-themed spin wheel on the bar's page. Each paid order
grants exactly one spin; spinning consumes the unlock and may win a drink perk.

Reuses the existing `marketplace_orders` + `marketplace_profiles` collections and
`secrets.SystemRandom` for a fair weighted draw. No live payment — a "bar
purchase" is any order with payment_status == "paid" at a bar-category business.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user

router = APIRouter(prefix="/api/bar-games", tags=["bar-games"])

_RNG = secrets.SystemRandom()

_BAR_CATEGORIES = {"bar", "club_lounge", "club", "lounge", "pub", "nightclub", "cocktail_bar"}
_PERK_TTL_DAYS = 14  # won drink codes expire after two weeks

# Drink-themed wheel. `win` prizes issue a redemption code; the two consolation
# segments keep it honest (not every spin wins).
SEGMENTS = [
    {"label": "Free house pour", "emoji": "🍺", "win": True, "weight": 6},
    {"label": "2-for-1 cocktail", "emoji": "🍸", "win": True, "weight": 9},
    {"label": "20% off your tab", "emoji": "🏷️", "win": True, "weight": 14},
    {"label": "Free bar snack", "emoji": "🍟", "win": True, "weight": 11},
    {"label": "Mocktail on us", "emoji": "🥂", "win": True, "weight": 10},
    {"label": "So close — sip again", "emoji": "😅", "win": False, "weight": 20},
    {"label": "One more round?", "emoji": "🔄", "win": False, "weight": 20},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def _next_midnight_iso() -> str:
    n = _now()
    nxt = (n.replace(hour=0, minute=0, second=0, microsecond=0)
           + timedelta(days=1))
    return nxt.isoformat()


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _aware(dt):
    """Mongo returns naive UTC datetimes — coerce to aware for safe compares."""
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_bar(profile: dict) -> bool:
    if not profile:
        return False
    cat = (profile.get("category") or "").lower()
    sub = (profile.get("subcategory") or "").lower()
    return cat in _BAR_CATEGORIES or sub in _BAR_CATEGORIES


async def _get_skin(db, business_id: str) -> Optional[dict]:
    return await db.bar_game_skins.find_one({"business_id": business_id})


def _segments_for(skin: Optional[dict]) -> list:
    segs = (skin or {}).get("segments")
    if isinstance(segs, list) and len(segs) >= 3:
        return segs
    return SEGMENTS


async def ensure_bar_game_indexes(db) -> None:
    await db.bar_game_unlocks.create_index(
        [("user_id", 1), ("business_id", 1), ("consumed", 1)], name="bgu_lookup")
    await db.bar_game_unlocks.create_index("order_id", name="bgu_order")
    await db.bar_game_plays.create_index(
        [("user_id", 1), ("created_at", -1)], name="bgp_time")
    await db.bar_game_free_claims.create_index("_id", name="bgfc_id")
    await db.bar_game_skins.create_index("business_id", unique=True, name="bgs_biz")


def _public_config(skin: Optional[dict] = None) -> dict:
    segs = _segments_for(skin)
    theme = {
        "accent": (skin or {}).get("accent") or "#a855f7",
        "accent2": (skin or {}).get("accent2") or "#ec4899",
        "logo_url": (skin or {}).get("logo_url"),
    }
    return {
        "segments": [{"label": s["label"], "emoji": s["emoji"], "win": s["win"]}
                     for s in segs],
        "theme": theme,
        "how_it_works": "Buy a round at this bar to unlock a spin — plus one FREE spin every day. Land a drink perk and we’ll drop a code you can redeem at the bar.",
        "spins_per_purchase": 1,
    }


async def _grant_from_orders(db, user_id: str, business_id: str) -> int:
    """Convert any PAID orders at this bar that haven't yet granted a spin into
    unlocks. Returns how many were newly granted. Idempotent per order."""
    granted = 0
    cursor = db.marketplace_orders.find(
        {"user_id": user_id, "business_id": business_id,
         "payment_status": "paid"}, {"order_id": 1})
    async for o in cursor:
        oid = o.get("order_id")
        if not oid:
            continue
        exists = await db.bar_game_unlocks.find_one({"order_id": oid})
        if exists:
            continue
        await db.bar_game_unlocks.insert_one({
            "_id": f"bgu_{uuid.uuid4().hex[:16]}", "user_id": user_id,
            "business_id": business_id, "order_id": oid,
            "consumed": False, "created_at": _now()})
        granted += 1
    return granted


async def _status(db, user_id: str, business_id: str) -> dict:
    profile = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not _is_bar(profile):
        return {"eligible": False}
    # Auto-convert any paid orders into spin unlocks.
    await _grant_from_orders(db, user_id, business_id)
    available = await db.bar_game_unlocks.count_documents(
        {"user_id": user_id, "business_id": business_id, "consumed": False})
    free_used = await db.bar_game_free_claims.find_one(
        {"_id": f"{user_id}:{business_id}:{_today()}"})
    free_available = not bool(free_used)
    skin = await _get_skin(db, business_id)
    last = await db.bar_game_plays.find_one(
        {"user_id": user_id, "business_id": business_id}, sort=[("created_at", -1)])
    is_owner = profile.get("owner_user_id") == user_id
    return {
        "eligible": True,
        "business_id": business_id,
        "business_name": profile.get("public_name"),
        "is_owner": is_owner,
        "spins_available": available,
        "free_spin_available": free_available,
        "next_free_reset": _next_midnight_iso(),
        "total_playable": available + (1 if free_available else 0),
        "config": _public_config(skin),
        "last_result": {
            "win": bool(last.get("win")), "label": last.get("label"),
            "code": last.get("code"), "created_at": _iso(last.get("created_at")),
        } if last else None,
    }


@router.get("/wallet")
async def bar_game_wallet(request: Request, user: dict = Depends(current_user)):
    """'My drink perks' — every winning code the user has collected."""
    db = request.app.state.db
    now = _now()
    items = []
    remind = []
    async for p in db.bar_game_plays.find(
            {"user_id": user["user_id"], "win": True}).sort("created_at", -1).limit(100):
        created = _aware(p.get("created_at"))
        exp = _aware(p.get("expires_at"))
        if not exp and isinstance(created, datetime):
            exp = created + timedelta(days=_PERK_TTL_DAYS)
        expired = bool(exp and isinstance(exp, datetime) and now > exp)
        redeemed = bool(p.get("redeemed"))
        soon = bool(exp and not expired and not redeemed and (exp - now) <= timedelta(hours=24))
        items.append({
            "play_id": p["_id"], "business_id": p.get("business_id"),
            "business_name": p.get("business_name"), "label": p.get("label"),
            "emoji": p.get("emoji"), "code": p.get("code"),
            "redeemed": redeemed, "expired": expired, "expiring_soon": soon,
            "expires_at": _iso(exp),
            "created_at": _iso(created)})
        if soon and not p.get("expiry_reminded"):
            remind.append(p)
    # Lazy "expires soon" nudge → in-app notification (real push needs a build).
    for p in remind:
        await db.social_notifications.insert_one({
            "_id": "notif_" + uuid.uuid4().hex[:14], "user_id": user["user_id"],
            "notif_type": "perk_expiring", "source_user_id": None,
            "source_post_id": None, "business_id": p.get("business_id"),
            "message": f"⏳ Your ‘{p.get('label')}’ perk ({p.get('code')}) at {p.get('business_name')} expires within 24h — use it soon!"[:240],
            "read": False, "created_at": now})
        await db.bar_game_plays.update_one(
            {"_id": p["_id"]}, {"$set": {"expiry_reminded": True}})
    active = sum(1 for i in items if not i["redeemed"] and not i["expired"])
    return {"items": items, "count": len(items), "active": active}


@router.post("/plays/{play_id}/redeem")
async def bar_game_redeem(play_id: str, request: Request,
                          user: dict = Depends(current_user)):
    """Mark a won perk as redeemed (once used at the bar)."""
    db = request.app.state.db
    now = _now()
    p = await db.bar_game_plays.find_one(
        {"_id": play_id, "user_id": user["user_id"], "win": True})
    if not p:
        raise HTTPException(404, {"code": "perk_not_found"})
    exp = _aware(p.get("expires_at"))
    if not exp and isinstance(_aware(p.get("created_at")), datetime):
        exp = _aware(p["created_at"]) + timedelta(days=_PERK_TTL_DAYS)
    if exp and isinstance(exp, datetime) and now > exp:
        raise HTTPException(400, {"code": "perk_expired",
                                  "message": "This perk has expired."})
    await db.bar_game_plays.update_one(
        {"_id": play_id}, {"$set": {"redeemed": True, "redeemed_at": now}})
    return {"ok": True, "redeemed": True}


@router.get("/{business_id}")
async def bar_game_status(business_id: str, request: Request,
                          user: dict = Depends(current_user)):
    return await _status(request.app.state.db, user["user_id"], business_id)


@router.post("/{business_id}/claim")
async def bar_game_claim(business_id: str, request: Request,
                         user: dict = Depends(current_user)):
    """Re-check paid orders and grant any pending spins (called after a purchase
    returns to the bar page)."""
    db = request.app.state.db
    profile = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not _is_bar(profile):
        raise HTTPException(400, {"code": "not_a_bar"})
    granted = await _grant_from_orders(db, user["user_id"], business_id)
    st = await _status(db, user["user_id"], business_id)
    return {"granted": granted, **st}


def _draw(segments: list) -> dict:
    total = sum(s["weight"] for s in segments)
    r = _RNG.uniform(0, total)
    upto = 0.0
    for i, s in enumerate(segments):
        upto += s["weight"]
        if r <= upto:
            return {"index": i, **s}
    return {"index": len(segments) - 1, **segments[-1]}


@router.post("/{business_id}/spin")
async def bar_game_spin(business_id: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    profile = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not _is_bar(profile):
        raise HTTPException(400, {"code": "not_a_bar"})
    # 1) Prefer a purchase unlock (consume atomically).
    unlock = await db.bar_game_unlocks.find_one_and_update(
        {"user_id": uid, "business_id": business_id, "consumed": False},
        {"$set": {"consumed": True, "consumed_at": _now()}})
    source = "purchase"
    if not unlock:
        # 2) Fall back to the once-a-day FREE spin (atomic claim per UTC day).
        claim_id = f"{uid}:{business_id}:{_today()}"
        try:
            await db.bar_game_free_claims.insert_one(
                {"_id": claim_id, "user_id": uid, "business_id": business_id,
                 "day": _today(), "created_at": _now()})
            source = "daily_free"
        except Exception:
            raise HTTPException(403, {"code": "no_spin_unlocked",
                                      "message": "You’ve used today’s free spin — buy a round to unlock more."})
    skin = await _get_skin(db, business_id)
    seg = _draw(_segments_for(skin))
    win = bool(seg["win"])
    code = ("BAR-" + uuid.uuid4().hex[:8].upper()) if win else None
    play = {
        "_id": f"bgp_{uuid.uuid4().hex[:16]}", "user_id": uid,
        "business_id": business_id, "business_name": profile.get("public_name"),
        "segment_index": seg["index"], "label": seg["label"], "emoji": seg["emoji"],
        "win": win, "code": code, "redeemed": False, "source": source,
        "expires_at": (_now() + timedelta(days=_PERK_TTL_DAYS)) if win else None,
        "created_at": _now()}
    await db.bar_game_plays.insert_one(play)
    available = await db.bar_game_unlocks.count_documents(
        {"user_id": uid, "business_id": business_id, "consumed": False})
    free_used = await db.bar_game_free_claims.find_one(
        {"_id": f"{uid}:{business_id}:{_today()}"})
    return {"win": win, "segment_index": seg["index"], "label": seg["label"],
            "emoji": seg["emoji"], "prize": seg["label"] if win else None,
            "code": code, "spins_available": available, "source": source,
            "free_spin_available": not bool(free_used),
            "next_free_reset": _next_midnight_iso(),
            "segments": _public_config(skin)["segments"]}


class SkinBody(BaseModel):
    accent: Optional[str] = None
    accent2: Optional[str] = None
    logo_url: Optional[str] = None
    segments: Optional[list] = None


@router.put("/{business_id}/skin")
async def set_skin(business_id: str, body: SkinBody, request: Request,
                   user: dict = Depends(current_user)):
    """Bar owner (or admin) themes the wheel — colours, logo & signature-drink
    prizes. Segments require label/emoji/win/weight; win/lose mix recommended."""
    db = request.app.state.db
    profile = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not _is_bar(profile):
        raise HTTPException(400, {"code": "not_a_bar"})
    is_admin = (user.get("role") == "admin") or bool(user.get("is_admin"))
    if not is_admin and profile.get("owner_user_id") != user["user_id"]:
        raise HTTPException(403, {"code": "not_bar_owner"})
    patch: dict = {"business_id": business_id, "updated_at": _now()}
    if body.accent:
        patch["accent"] = body.accent
    if body.accent2:
        patch["accent2"] = body.accent2
    if body.logo_url is not None:
        patch["logo_url"] = body.logo_url
    if body.segments:
        clean = []
        for s in body.segments:
            if not isinstance(s, dict) or not s.get("label"):
                continue
            clean.append({"label": str(s["label"])[:40],
                          "emoji": str(s.get("emoji") or "🍹")[:4],
                          "win": bool(s.get("win", True)),
                          "weight": max(1, int(s.get("weight") or 1))})
        if len(clean) < 3:
            raise HTTPException(400, {"code": "need_min_3_segments"})
        patch["segments"] = clean
    await db.bar_game_skins.update_one({"business_id": business_id},
                                       {"$set": patch}, upsert=True)
    return {"ok": True, "config": _public_config(await _get_skin(db, business_id))}


def _is_owner_or_admin(profile: dict, user: dict) -> bool:
    is_admin = (user.get("role") == "admin") or bool(user.get("is_admin"))
    return is_admin or (profile or {}).get("owner_user_id") == user["user_id"]


async def _perk_status(db, p: dict) -> str:
    if not p or not p.get("win"):
        return "not_found"
    if p.get("redeemed"):
        return "redeemed"
    now = _now()
    exp = _aware(p.get("expires_at"))
    if not exp and isinstance(_aware(p.get("created_at")), datetime):
        exp = _aware(p["created_at"]) + timedelta(days=_PERK_TTL_DAYS)
    if exp and isinstance(exp, datetime) and now > exp:
        return "expired"
    return "valid"


class CodeBody(BaseModel):
    code: str = Field(..., min_length=3, max_length=40)


async def _staff_find(db, business_id: str, code: str) -> Optional[dict]:
    return await db.bar_game_plays.find_one(
        {"business_id": business_id, "code": code.strip().upper(), "win": True})


@router.post("/{business_id}/staff/lookup")
async def staff_lookup(business_id: str, body: CodeBody, request: Request,
                       user: dict = Depends(current_user)):
    """Bar staff/owner validate a customer's drink code before burning it."""
    db = request.app.state.db
    profile = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not _is_bar(profile):
        raise HTTPException(400, {"code": "not_a_bar"})
    if not _is_owner_or_admin(profile, user):
        raise HTTPException(403, {"code": "not_bar_staff"})
    p = await _staff_find(db, business_id, body.code)
    status = await _perk_status(db, p)
    perk = None
    if p:
        cust = await db.users.find_one({"user_id": p.get("user_id")}, {"name": 1, "_id": 0})
        perk = {"label": p.get("label"), "emoji": p.get("emoji"), "code": p.get("code"),
                "customer": (cust or {}).get("name") or "Guest",
                "expires_at": _iso(_aware(p.get("expires_at")))}
    return {"status": status, "perk": perk}


@router.post("/{business_id}/staff/redeem")
async def staff_redeem(business_id: str, body: CodeBody, request: Request,
                       user: dict = Depends(current_user)):
    """Burn (redeem) a valid drink code at the bar."""
    db = request.app.state.db
    profile = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not _is_bar(profile):
        raise HTTPException(400, {"code": "not_a_bar"})
    if not _is_owner_or_admin(profile, user):
        raise HTTPException(403, {"code": "not_bar_staff"})
    p = await _staff_find(db, business_id, body.code)
    status = await _perk_status(db, p)
    if status != "valid":
        return {"ok": False, "status": status}
    await db.bar_game_plays.update_one(
        {"_id": p["_id"]}, {"$set": {"redeemed": True, "redeemed_at": _now(),
                                     "redeemed_by": user["user_id"]}})
    return {"ok": True, "status": "redeemed",
            "perk": {"label": p.get("label"), "emoji": p.get("emoji"), "code": p.get("code")}}


class GiftBody(BaseModel):
    friend_id: str = Field(..., min_length=3, max_length=64)


@router.post("/plays/{play_id}/gift")
async def gift_perk(play_id: str, body: GiftBody, request: Request,
                    user: dict = Depends(current_user)):
    """Transfer a won drink code to an accepted friend — it leaves your
    wallet and lands in theirs."""
    db = request.app.state.db
    uid = user["user_id"]
    p = await db.bar_game_plays.find_one({"_id": play_id, "user_id": uid, "win": True})
    status = await _perk_status(db, p)
    if status != "valid":
        raise HTTPException(400, {"code": f"perk_{status}" if status != "valid" else "invalid",
                                  "message": "This perk can’t be gifted."})
    friend = body.friend_id
    fr = await db.social_friendships.find_one(
        {"status": "accepted",
         "$or": [{"user_a": uid, "user_b": friend}, {"user_a": friend, "user_b": uid}]})
    if not fr:
        raise HTTPException(400, {"code": "not_friends"})
    await db.bar_game_plays.update_one(
        {"_id": play_id}, {"$set": {"user_id": friend, "gifted_by": uid,
                                    "gifted_at": _now(), "expiry_reminded": False}})
    gifter = (user.get("name") or "A friend")
    await db.social_notifications.insert_one({
        "_id": "notif_" + uuid.uuid4().hex[:14], "user_id": friend,
        "notif_type": "perk_gift", "source_user_id": uid, "source_post_id": None,
        "business_id": p.get("business_id"),
        "message": f"🎁 {gifter} gifted you a ‘{p.get('label')}’ perk at {p.get('business_name')}!"[:240],
        "read": False, "created_at": _now()})
    return {"ok": True}


class CoverBody(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=200)


@router.post("/cover-art")
async def cover_art(body: CoverBody, request: Request,
                    user: dict = Depends(current_user)):
    """AI cover art for a Live event (reuses the shared image-gen service)."""
    db = request.app.state.db
    tier = "admin" if user.get("role") == "admin" else ("premium" if user.get("is_premium") else "free")
    prompt = (f"Vibrant nightlife bar event poster background, {body.prompt.strip()}, "
              f"neon cinematic lighting, moody, high detail, no text, no words")
    from services import image_gen
    res = await image_gen.generate(db, prompt=prompt, user_id=user["user_id"], tier=tier)
    if not res.get("ok"):
        code = res.get("error") or "generation_failed"
        raise HTTPException(429 if code == "rate_limited" else 502,
                            {"code": code, "used": res.get("used"), "limit": res.get("limit")})
    # Return the RELATIVE path — each client prepends its own public backend
    # URL so the stored cover_url resolves on both web and mobile.
    return {"ok": True, "url": res["url"], "cached": res.get("cached", False)}


# ─────────────────────────── Demo bar seed ─────────────────────────
_DEMO_BAR_ID = "biz_demo_bar"


async def seed_demo_bar(db) -> None:
    """Idempotent demo bar (approved, subscribed) + one PAID order for the demo
    user, so the drink-themed spin wheel is unlockable/testable in preview."""
    demo = await db.users.find_one({"email": "demo@bigfm.dubai"}, {"user_id": 1})
    now = _now()
    if not await db.marketplace_profiles.find_one({"business_id": _DEMO_BAR_ID}):
        await db.marketplace_profiles.insert_one({
            "business_id": _DEMO_BAR_ID,
            "owner_user_id": (demo or {}).get("user_id") or "system",
            "business_type": "bar", "legal_name": "Neon Nights Bar LLC",
            "public_name": "Neon Nights Bar",
            "description": "Cocktails, craft beer & good vibes on Marina Walk.",
            "category": "bar", "subcategory": "cocktail_bar",
            "logo_url": None,
            "cover_urls": ["https://images.unsplash.com/photo-1514933651103-005eec06c04b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"],
            "locations": [], "sells": ["menu", "products"], "market": "dubai",
            "rating": 4.6, "featured": False, "sponsored": False,
            "status": "approved", "subscription_active": True,
            "shop_plan_status": "active",
            "created_at": now, "updated_at": now})
    # One PAID demo order so the demo user has a spin to try.
    if demo and not await db.marketplace_orders.find_one({"order_id": "ord_demo_bar_1"}):
        await db.marketplace_orders.insert_one({
            "order_id": "ord_demo_bar_1", "business_id": _DEMO_BAR_ID,
            "business_name": "Neon Nights Bar", "user_id": demo["user_id"],
            "items": [{"name": "House Cocktail", "qty": 2}],
            "total_cents": 3600, "payment_status": "paid", "status": "accepted",
            "created_at": now, "updated_at": now})
    # Signature neon skin so the demo bar shows the theming capability.
    if not await db.bar_game_skins.find_one({"business_id": _DEMO_BAR_ID}):
        await db.bar_game_skins.insert_one({
            "business_id": _DEMO_BAR_ID,
            "accent": "#22d3ee", "accent2": "#f472b6",
            "logo_url": "https://images.unsplash.com/photo-1514933651103-005eec06c04b?crop=entropy&cs=srgb&fm=jpg&q=85&w=200",
            "segments": [
                {"label": "Free Neon Mojito", "emoji": "🍹", "win": True, "weight": 6},
                {"label": "2-for-1 Cosmo", "emoji": "🍸", "win": True, "weight": 9},
                {"label": "25% off your tab", "emoji": "🏷️", "win": True, "weight": 13},
                {"label": "Free bar bites", "emoji": "🍤", "win": True, "weight": 11},
                {"label": "Glow-shot on us", "emoji": "🥃", "win": True, "weight": 10},
                {"label": "So close — sip again", "emoji": "😅", "win": False, "weight": 19},
                {"label": "One more round?", "emoji": "🔄", "win": False, "weight": 19},
            ],
            "updated_at": now})
    # Demo bar menu so the Live scheduler's product picker isn't empty.
    if await db.products.count_documents({"business_id": _DEMO_BAR_ID}) == 0:
        menu = [
            ("Neon Martini", 4200, "https://images.unsplash.com/photo-1597075687490-8f673c6c17f6?crop=entropy&cs=srgb&fm=jpg&q=85&w=600"),
            ("Sunset Spritz", 3200, "https://images.unsplash.com/photo-1582106245687-cbb466a9f07f?crop=entropy&cs=srgb&fm=jpg&q=85&w=600"),
            ("Craft Old Fashioned", 3800, "https://images.unsplash.com/photo-1702725365144-6e8584ea54e4?crop=entropy&cs=srgb&fm=jpg&q=85&w=600"),
            ("Bar Snack Platter", 2600, "https://images.unsplash.com/photo-1566417713940-fe7c737a9ef2?crop=entropy&cs=srgb&fm=jpg&q=85&w=600"),
        ]
        for i, (name, price, img) in enumerate(menu):
            await db.products.insert_one({
                "product_id": f"prod_demobar_{i}", "business_id": _DEMO_BAR_ID,
                "sort": i, "name": name, "description": "", "category": "Drinks",
                "price_cents": price, "stock": 100, "variants": [],
                "option_groups": [], "image_url": img, "active": True,
                "created_at": now, "updated_at": now})


__all__ = ["router", "ensure_bar_game_indexes", "seed_demo_bar"]
