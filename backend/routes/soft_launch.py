"""Soft-launch — Business Setup Mode.

Central launch config, consumer waitlist, admin preview-token management, and
the merchant "6 months free" soft-launch claim. Pairs with
`services/launch_guard.py` (the server-side enforcement middleware).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from auth import current_user, current_user_optional, require_admin
from services.launch_guard import (
    LAUNCH_KEY, bust_launch_cache, get_launch_settings, resolve_bypass,
    valid_preview_token,
)

router = APIRouter(prefix="/api", tags=["soft-launch"])
logger = logging.getLogger("bigfm.soft_launch")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

# Paid featured-placement pricing (US cents per day).
_FEATURED_PRICING = {"deal": 2500, "pin": 1500}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TEST_NAME = re.compile(r"(TEST_|Iter\d|Test Shop|QA Demo)", re.I)
_CAT_LABEL = {"restaurant": "Restaurant", "beauty": "Salon & Spa",
              "fitness": "Fitness", "retail": "Retail", "cafe": "Cafe",
              "bar": "Bar", "grocery": "Grocery", "service": "Services"}
_BIZ_CACHE = {"ts": 0.0, "val": None}

# Referral reward tiers (pre-launch promises, unlocked at launch).
_REFERRAL_TIERS = [
    {"min": 0, "name": "Waitlisted", "perk": "You're on the list"},
    {"min": 1, "name": "Insider", "perk": "Early access when we open"},
    {"min": 3, "name": "VIP", "perk": "Early access + 500 bonus BigPoints"},
    {"min": 5, "name": "Founding Fan", "perk": "VIP perks + 1 month Premium free"},
    {"min": 10, "name": "Legend", "perk": "Founding perks + a lifetime Legend badge"},
]


def _tier_for(n: int) -> dict:
    t = _REFERRAL_TIERS[0]
    for x in _REFERRAL_TIERS:
        if n >= x["min"]:
            t = x
    return t


def _mask_email(e: str) -> str:
    e = str(e or "")
    if "@" not in e:
        return "someone"
    local, dom = e.split("@", 1)
    lm = (local[:2] + "\u2022\u2022\u2022") if len(local) > 2 else (local[:1] + "\u2022")
    return f"{lm}@{dom[:1]}\u2026"


def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _ends_at_iso() -> str:
    """Next UTC midnight — when the Deal of the Day rolls over."""
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc).isoformat()


def _mask_name(user: dict) -> str:
    if not user:
        return "A listener"
    name = (user.get("name") or user.get("display_name") or "").strip()
    if name:
        parts = name.split()
        first = parts[0]
        if len(parts) > 1:
            return f"{first} {parts[-1][:1].upper()}."
        return first
    email = user.get("email") or ""
    if "@" in email:
        return email.split("@", 1)[0][:2].title() + "\u2022\u2022\u2022"
    return "A listener"


async def _paid_booking(db, kind: str, date_str: str):
    return await db.featured_bookings.find_one(
        {"type": kind, "date": date_str, "status": "paid"})


@router.get("/launch/winners")
async def launch_winners(request: Request, limit: int = 10):
    """Public — recent real prize winners (masked) for the Winners Wall."""
    db = request.app.state.db
    limit = max(1, min(30, int(limit or 10)))
    items = []
    cursor = db.game_winners.find({"status": {"$nin": ["voided", "cancelled"]}}) \
        .sort([("won_at", -1), ("created_at", -1)]).limit(limit * 3)
    async for w in cursor:
        snap = w.get("prize_snapshot_json") or {}
        prize = snap.get("title") or "a prize"
        uid = w.get("user_id")
        user = await db.users.find_one({"user_id": uid}, {"name": 1, "display_name": 1, "email": 1}) if uid else None
        when = w.get("won_at") or w.get("created_at")
        try:
            when_iso = when.isoformat() if hasattr(when, "isoformat") else str(when)
        except Exception:
            when_iso = None
        items.append({"name": _mask_name(user), "prize": prize,
                      "prize_type": snap.get("prize_type"), "when": when_iso})
        if len(items) >= limit:
            break
    return {"items": items, "total": await db.game_winners.count_documents({"status": {"$nin": ["voided", "cancelled"]}})}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _clean(d: dict) -> dict:
    if not d:
        return d
    d.pop("_id", None)
    return d


# ─────────────────────────── PUBLIC ────────────────────────────────
@router.get("/launch/status")
async def launch_status(request: Request):
    """Public — the frontend guard reads this to decide Coming-Soon vs app."""
    db = request.app.state.db
    s = await get_launch_settings(db)
    if not s.get("business_setup_mode_enabled"):
        return {"business_setup_mode": False,
                "waitlist_enabled": bool(s.get("waitlist_enabled")),
                "offer_months": int(s.get("offer_months", 6)),
                "launch_at": s.get("launch_at"),
                "has_bypass": True, "bypass_reason": None}
    has_bypass, reason = await resolve_bypass(request, db)
    return {"business_setup_mode": True,
            "waitlist_enabled": bool(s.get("waitlist_enabled")),
            "offer_months": int(s.get("offer_months", 6)),
            "launch_at": s.get("launch_at"),
            "has_bypass": bool(has_bypass), "bypass_reason": reason}


@router.get("/launch/businesses")
async def launch_businesses(request: Request, limit: int = 24, offset: int = 0):
    """Public — the 'Businesses joining now' wall for the Coming-Soon page.
    Real approved storefronts (newest first), soft-launch claimers flagged.
    Paginated via limit/offset; the full list is cached ~20s so the public
    poll + 'See all' browsing don't re-scan two collections each hit.
    """
    db = request.app.state.db
    limit = max(1, min(60, int(limit or 24)))
    offset = max(0, int(offset or 0))
    import time as _t
    now = _t.time()
    if _BIZ_CACHE["val"] is None or (now - _BIZ_CACHE["ts"]) >= 20.0:
        items, seen = [], set()
        q = {"status": "approved",
             "public_name": {"$not": {"$regex": r"(TEST_|Iter\d|Test Shop|QA Demo)",
                                      "$options": "i"}}}
        async for p in db.marketplace_profiles.find(q).sort("updated_at", -1).limit(300):
            name = p.get("public_name")
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            cat = p.get("category")
            items.append({
                "name": name,
                "category": cat,
                "category_label": _CAT_LABEL.get(cat, (cat or "Business").title()),
                "image": (p.get("cover_urls") or [None])[0] or p.get("logo_url"),
                "claimed": bool((p.get("soft_launch_offer") or {}).get("status") == "active"),
            })
        async for b in db.businesses.find({"active": True}).sort("created_at", -1).limit(200):
            name = b.get("name")
            if not name or name.lower() in seen or _TEST_NAME.search(name):
                continue
            seen.add(name.lower())
            cat = (b.get("category") or "").lower()
            items.append({
                "name": name, "category": cat,
                "category_label": _CAT_LABEL.get(cat, (cat or "Business").title()),
                "image": None, "claimed": False,
            })
        claimed_total = await db.soft_launch_claims.count_documents({})
        total = max(len(items), claimed_total)
        _BIZ_CACHE["val"] = {"total": total, "items": items}
        _BIZ_CACHE["ts"] = now
    cached = _BIZ_CACHE["val"]
    window = cached["items"][offset:offset + limit]
    return {"total": cached["total"], "items": window,
            "loaded": len(cached["items"]),
            "has_more": (offset + limit) < len(cached["items"])}


@router.get("/launch/leaderboard")
async def launch_leaderboard(request: Request, limit: int = 10):
    """Public — top waitlist referrers + the reward-tier ladder."""
    db = request.app.state.db
    limit = max(1, min(50, int(limit or 10)))
    top, rank = [], 0
    cursor = db.consumer_waitlist.find({"referrals": {"$gt": 0}}) \
        .sort([("referrals", -1), ("created_at", 1)]).limit(limit)
    async for w in cursor:
        rank += 1
        n = int(w.get("referrals", 0) or 0)
        top.append({"rank": rank, "name": _mask_email(w.get("email")),
                    "referrals": n, "tier": _tier_for(n)["name"]})
    return {"tiers": _REFERRAL_TIERS, "top": top}


@router.get("/launch/shop-tiles")
async def launch_shop_tiles(request: Request, city: str = ""):
    """Public — real business cover images for the Shop tiles (a LIST per
    category so the landing can auto-rotate). City-aware (nearby first) and a
    paid 'pin' booking is prepended to Featured Businesses. Falls back to art."""
    db = request.app.state.db
    city = (city or "").strip().lower()[:60]
    q = {"status": "approved",
         "public_name": {"$not": {"$regex": r"(TEST_|Iter\d|Test Shop|QA Demo)",
                                  "$options": "i"}}}
    profs = []
    async for p in db.marketplace_profiles.find(q).sort("updated_at", -1).limit(120):
        img = (p.get("cover_urls") or [None])[0] or p.get("logo_url")
        if not img:
            continue
        addr = ((p.get("geo") or {}).get("address") or "").lower()
        profs.append({"name": p.get("public_name"), "cat": (p.get("category") or "").lower(),
                      "img": img, "near": bool(city and city in addr),
                      "bid": p.get("business_id"),
                      "claimed": bool((p.get("soft_launch_offer") or {}).get("status") == "active")})
    if city:  # nearby businesses first, stable otherwise
        profs.sort(key=lambda p: (0 if p["near"] else 1))

    def ser(lst, n=4, pin=None):
        out, seen = [], set()
        if pin:
            out.append(pin)
            seen.add(pin["name"])
        for pr in lst:
            if pr["name"] in seen:
                continue
            seen.add(pr["name"])
            out.append({"image": pr["img"], "name": pr["name"], "near": pr.get("near")})
            if len(out) >= n:
                break
        return out

    food = [p for p in profs if p["cat"] in ("restaurant", "cafe", "bar", "grocery")]
    serv = [p for p in profs if p["cat"] in ("service", "beauty", "fitness")]
    retail = [p for p in profs if p["cat"] in ("retail", "grocery")]
    claimed = [p for p in profs if p["claimed"]]

    # Paid 'pin' booking → first Featured Businesses tile today.
    pin = None
    booking = await _paid_booking(db, "pin", _today_str())
    if booking:
        bp = await db.marketplace_profiles.find_one({"business_id": booking.get("business_id")})
        if bp:
            img = (bp.get("cover_urls") or [None])[0] or bp.get("logo_url")
            if img:
                pin = {"image": img, "name": bp.get("public_name"), "pinned": True}

    mapping = {}
    if food:
        mapping["Restaurant Pickup"] = ser(food)
    if serv:
        mapping["Services"] = ser(serv)
    feat = claimed + [p for p in profs if not p["claimed"]]
    if feat or pin:
        mapping["Featured Businesses"] = ser(feat, pin=pin)
    if retail or profs:
        mapping["Local Deals"] = ser(retail or profs)
    if profs:
        mapping["Memberships"] = ser(profs)
    return {"items": mapping, "city": city or None}


_DEAL_CACHE = {"key": None, "val": None}


@router.get("/launch/deal-of-day")
async def launch_deal_of_day(request: Request, city: str = ""):
    """Public — one real business deal. A paid 'deal' booking for today wins;
    otherwise a city-aware deterministic daily pick. Includes ends_at (next
    UTC midnight) for the countdown timer."""
    db = request.app.state.db
    city = (city or "").strip().lower()[:60]
    day = datetime.now(timezone.utc).toordinal()
    today = _today_str()
    ends_at = _ends_at_iso()

    def _prof_deal(prof, headline, subtext, featured=False):
        img = ((prof or {}).get("cover_urls") or [None])[0] or (prof or {}).get("logo_url")
        return {"business_name": prof.get("public_name"),
                "category_label": _CAT_LABEL.get((prof.get("category") or "").lower(), "Local"),
                "image": img, "headline": headline, "subtext": subtext,
                "featured": featured, "to": "/shop/near-me"}

    # 1) Paid booking overrides everything for its day.
    booking = await _paid_booking(db, "deal", today)
    if booking:
        bp = await db.marketplace_profiles.find_one({"business_id": booking.get("business_id")})
        img = ((bp or {}).get("cover_urls") or [None])[0] or (bp or {}).get("logo_url")
        if bp and img:
            return {"available": True, "ends_at": ends_at,
                    "deal": _prof_deal(bp, booking.get("headline") or f"Featured: {bp.get('public_name')}",
                                       booking.get("subtext") or f"Today's spotlight on RadioLife", featured=True)}

    ckey = f"{day}:{city}"
    if _DEAL_CACHE["key"] == ckey and _DEAL_CACHE["val"] is not None:
        return _DEAL_CACHE["val"]

    async def _prof(bid):
        if not bid:
            return None
        return await db.marketplace_profiles.find_one({"business_id": bid, "status": "approved"})

    def _ok(prof):
        name = (prof or {}).get("public_name")
        img = ((prof or {}).get("cover_urls") or [None])[0] or (prof or {}).get("logo_url")
        if not name or not img or _TEST_NAME.search(name):
            return None
        return name, img

    def _near(prof):
        return bool(city and city in (((prof or {}).get("geo") or {}).get("address") or "").lower())

    cands = []
    async for o in db.offers.find({"status": "active"}).limit(50):
        prof = await _prof(o.get("business_id"))
        if not _ok(prof):
            continue
        name = prof.get("public_name")
        dp = o.get("discount_percent")
        headline = f"{int(dp)}% off" if dp else (o.get("title") or "Special offer")
        d = _prof_deal(prof, headline, o.get("description") or f"Exclusive offer at {name}")
        d["_near"] = _near(prof)
        cands.append(d)
    async for sp in db.marketplace_specials.find({"active": True}).limit(50):
        prof = await _prof(sp.get("business_id"))
        if not _ok(prof):
            continue
        name = prof.get("public_name")
        d = _prof_deal(prof, sp.get("blurb") or "Today's special", f"Limited-time special at {name}")
        d["_near"] = _near(prof)
        cands.append(d)
    if not cands:
        async for p in db.marketplace_profiles.find({"status": "approved"}).sort("updated_at", -1).limit(40):
            if not _ok(p):
                continue
            d = _prof_deal(p, "Featured this week", f"Discover {p.get('public_name')} on RadioLife")
            d["_near"] = _near(p)
            cands.append(d)
    if city:
        cands.sort(key=lambda d: (0 if d.get("_near") else 1))
    for d in cands:
        d.pop("_near", None)
    out = {"available": bool(cands), "ends_at": ends_at,
           "deal": (cands[day % len(cands)] if cands else None)}
    _DEAL_CACHE["key"] = ckey
    _DEAL_CACHE["val"] = out
    return out


async def _new_ref_code(db) -> str:
    for _ in range(8):
        code = secrets.token_urlsafe(4).replace("-", "").replace("_", "")[:6].upper()
        if code and not await db.consumer_waitlist.find_one({"ref_code": code}):
            return code
    return secrets.token_urlsafe(6)[:8].upper()


async def _waitlist_position(db, code: str) -> dict:
    me = await db.consumer_waitlist.find_one({"ref_code": code})
    total = await db.consumer_waitlist.count_documents({})
    if not me:
        return {"position": total, "referrals": 0, "total": total, "tier": _tier_for(0)["name"]}
    my_ref = int(me.get("referrals", 0) or 0)
    my_created = me.get("created_at") or ""
    # Rank = 1 + (#entries with more referrals, or same referrals but earlier).
    ahead = await db.consumer_waitlist.count_documents({"$or": [
        {"referrals": {"$gt": my_ref}},
        {"referrals": my_ref, "created_at": {"$lt": my_created}},
    ]})
    return {"position": ahead + 1, "referrals": my_ref, "total": total,
            "tier": _tier_for(my_ref)["name"]}


@router.post("/waitlist")
async def join_waitlist(request: Request, body: dict = Body(default={})):
    db = request.app.state.db
    s = await get_launch_settings(db)
    if not s.get("waitlist_enabled"):
        raise HTTPException(403, {"code": "waitlist_closed"})
    email = str((body or {}).get("email") or "").strip().lower()[:120]
    if not _EMAIL.match(email):
        raise HTTPException(400, {"code": "invalid_email"})
    interests = [str(x)[:40] for x in ((body or {}).get("interests") or [])][:12]
    city = str((body or {}).get("city") or "").strip()[:80] or None
    ref_in = (str((body or {}).get("ref") or "").strip()[:24] or None)
    if ref_in:
        ref_in = ref_in.upper()
    try:
        user = await current_user_optional(request)
    except Exception:
        user = None
    existing = await db.consumer_waitlist.find_one({"email": email})
    is_new = existing is None
    my_code = (existing or {}).get("ref_code") or await _new_ref_code(db)
    on_insert = {"created_at": _now_iso(), "ref_code": my_code, "referrals": 0}
    credit_ref = bool(is_new and ref_in and ref_in != my_code)
    if credit_ref:
        on_insert["referred_by"] = ref_in
    await db.consumer_waitlist.update_one(
        {"email": email},
        {"$set": {"email": email, "interests": interests, "city": city,
                  "user_id": (user or {}).get("user_id"), "updated_at": _now_iso()},
         "$setOnInsert": on_insert},
        upsert=True)
    if credit_ref:
        # Credit the referrer only if their code belongs to a different entry.
        await db.consumer_waitlist.update_one(
            {"ref_code": ref_in, "email": {"$ne": email}},
            {"$inc": {"referrals": 1}})
    pos = await _waitlist_position(db, my_code)
    return {"ok": True, "ref_code": my_code, "share_path": f"/?ref={my_code}",
            **pos, "already": (not is_new)}


@router.get("/waitlist/position")
async def waitlist_position(request: Request, code: str = ""):
    db = request.app.state.db
    code = (code or "").strip().upper()[:24]
    if not code:
        raise HTTPException(400, {"code": "code_required"})
    return await _waitlist_position(db, code)


@router.post("/launch/preview/redeem")
async def redeem_preview(request: Request, response: Response, body: dict = Body(default={})):
    db = request.app.state.db
    token = str((body or {}).get("token") or "").strip()[:80]
    if not token or not await valid_preview_token(db, token):
        raise HTTPException(400, {"code": "invalid_token"})
    await db.preview_tokens.update_one(
        {"token": token},
        {"$inc": {"uses": 1}, "$set": {"last_used_at": _now_iso()}})
    response.set_cookie("rl_preview_token", token, max_age=60 * 60 * 24 * 30,
                        httponly=False, samesite="lax", path="/")
    return {"ok": True, "valid": True}


# ─────────────────────────── ADMIN ─────────────────────────────────
@router.get("/admin/launch-settings")
async def admin_get_settings(request: Request, admin: dict = Depends(require_admin)):
    return await get_launch_settings(request.app.state.db)


@router.patch("/admin/launch-settings")
async def admin_patch_settings(request: Request, body: dict = Body(default={}),
                               admin: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = await db.platform_settings.find_one({"key": LAUNCH_KEY}) or {}
    prior_mode = bool(cur.get("business_setup_mode_enabled", False))
    updates: dict = {}
    if "business_setup_mode_enabled" in (body or {}):
        updates["business_setup_mode_enabled"] = bool(body["business_setup_mode_enabled"])
    if "waitlist_enabled" in (body or {}):
        updates["waitlist_enabled"] = bool(body["waitlist_enabled"])
    if "offer_months" in (body or {}):
        try:
            updates["offer_months"] = max(1, min(24, int(body["offer_months"])))
        except Exception:
            pass
    if "launch_at" in (body or {}):
        raw = body.get("launch_at")
        if raw in (None, "", "null"):
            updates["launch_at"] = None
        else:
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                updates["launch_at"] = dt.isoformat()
            except Exception:
                raise HTTPException(400, {"code": "bad_launch_at"})
    if not updates:
        raise HTTPException(400, {"code": "no_updates"})
    updates["updated_at"] = _now_iso()
    updates["updated_by"] = admin.get("user_id")
    await db.platform_settings.update_one(
        {"key": LAUNCH_KEY}, {"$set": {"key": LAUNCH_KEY, **updates}}, upsert=True)
    bust_launch_cache()
    # Launching = flipping Business Setup Mode OFF. Email the whole waitlist once.
    new_mode = updates.get("business_setup_mode_enabled", prior_mode)
    if prior_mode and not new_mode:
        try:
            asyncio.create_task(_notify_waitlist_launched(db))
        except Exception as _e:
            logger.warning("launch notify not scheduled: %s", _e)
    return await get_launch_settings(db)


@router.get("/admin/waitlist")
async def admin_waitlist(request: Request, admin: dict = Depends(require_admin),
                         limit: int = 300):
    db = request.app.state.db
    total = await db.consumer_waitlist.count_documents({})
    items = []
    async for w in db.consumer_waitlist.find({}, {"_id": 0}).sort("created_at", -1).limit(min(limit, 1000)):
        items.append(w)
    return {"total": total, "items": items}


def _new_token() -> str:
    return "pv_" + secrets.token_urlsafe(18)


@router.post("/admin/preview-tokens")
async def admin_create_token(request: Request, body: dict = Body(default={}),
                             admin: dict = Depends(require_admin)):
    db = request.app.state.db
    label = str((body or {}).get("label") or "").strip()[:80] or "Preview access"
    try:
        max_uses = max(0, int((body or {}).get("max_uses") or 0))
    except Exception:
        max_uses = 0
    try:
        expires_days = max(0, int((body or {}).get("expires_days") or 0))
    except Exception:
        expires_days = 0
    token = _new_token()
    doc = {
        "token": token, "label": label, "max_uses": max_uses, "uses": 0,
        "revoked": False, "created_by": admin.get("user_id"),
        "created_at": _now_iso(),
        "expires_at": ((_now() + timedelta(days=expires_days)).isoformat()
                       if expires_days > 0 else None),
    }
    await db.preview_tokens.insert_one(dict(doc))
    return {"ok": True, "token": token, "record": _clean(doc)}


@router.get("/admin/preview-tokens")
async def admin_list_tokens(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    items = []
    async for t in db.preview_tokens.find({}, {"_id": 0}).sort("created_at", -1).limit(200):
        items.append(t)
    return {"items": items}


@router.post("/admin/preview-tokens/{token}/revoke")
async def admin_revoke_token(token: str, request: Request,
                             admin: dict = Depends(require_admin)):
    db = request.app.state.db
    r = await db.preview_tokens.update_one(
        {"token": token}, {"$set": {"revoked": True, "revoked_at": _now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, {"code": "not_found"})
    bust_launch_cache()
    return {"ok": True}


# ────────────────────── MERCHANT SOFT-LAUNCH ───────────────────────
_COMMISSION_NOTE = ("Your monthly subscription fee is waived for the soft-launch "
                    "period. Standard per-sale commission still applies on the "
                    "products you sell.")


@router.get("/merchant/soft-launch/offer")
async def merchant_offer(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await get_launch_settings(db)
    months = int(s.get("offer_months", 6))
    uid = user.get("user_id")
    claim = await db.soft_launch_claims.find_one({"user_id": uid}, {"_id": 0})
    prof = await db.marketplace_profiles.find_one({"owner_user_id": uid})
    biz = await db.businesses.find_one({"owner_user_id": uid})
    return {
        "offer_months": months,
        "has_business": bool(prof or biz or user.get("is_business")),
        "has_storefront": bool(prof),
        "claimed": bool(claim),
        "claim": claim,
        "commission_note": _COMMISSION_NOTE,
    }


@router.post("/merchant/soft-launch/claim")
async def merchant_claim(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await get_launch_settings(db)
    months = int(s.get("offer_months", 6))
    uid = user.get("user_id")
    existing = await db.soft_launch_claims.find_one({"user_id": uid})
    if existing:
        return {"ok": True, "already": True, "claim": _clean(dict(existing))}
    free_until = (_now() + timedelta(days=30 * months)).isoformat()
    claim = {"user_id": uid, "months": months, "free_until": free_until,
             "status": "active", "claimed_at": _now_iso()}
    await db.soft_launch_claims.insert_one(dict(claim))
    # Grant the business role so the merchant gets preview bypass immediately.
    await db.users.update_one(
        {"user_id": uid},
        {"$addToSet": {"roles": "business"},
         "$set": {"is_business": True, "soft_launch_offer": claim}})
    # If they already have a storefront, waive its monthly subscription fee.
    prof = await db.marketplace_profiles.find_one({"owner_user_id": uid})
    if prof:
        await db.marketplace_profiles.update_one(
            {"owner_user_id": uid},
            {"$set": {"subscription_active": True, "status": "approved",
                      "soft_launch_offer": claim, "updated_at": _now_iso()}})
        await db.merchant_subscriptions.update_one(
            {"business_id": prof["business_id"]},
            {"$set": {"business_id": prof["business_id"], "plan_id": "soft_launch_free",
                      "status": "active", "soft_launch": True, "free_until": free_until,
                      "updated_at": _now_iso()},
             "$setOnInsert": {"created_at": _now_iso()}}, upsert=True)
    bust_launch_cache()
    return {"ok": True, "claim": claim, "commission_note": _COMMISSION_NOTE}


# ─────────────────────── LAUNCH NOTIFICATION ───────────────────────
_LAUNCH_EMAIL_HTML = """\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;
  background:#0b0f24;color:#fff;border-radius:16px;overflow:hidden">
  <div style="padding:32px 28px;background:linear-gradient(135deg,#a855f7,#ec4899)">
    <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;opacity:.9">
      RadioLife</div>
    <div style="font-size:28px;font-weight:900;margin-top:8px;line-height:1.1">
      We&rsquo;re live. 🎉</div>
  </div>
  <div style="padding:28px">
    <p style="font-size:15px;line-height:1.6;color:#d7dcf0">
      Thanks for waiting! RadioLife is now open to listeners. Live radio, AI radio,
      and rewards for every minute you listen &mdash; dive in.</p>
    <a href="{base}" style="display:inline-block;margin-top:14px;background:#fff;
      color:#0b0f24;font-weight:800;text-decoration:none;padding:13px 26px;
      border-radius:999px;font-size:14px">Start listening &rarr;</a>
    <p style="font-size:12px;color:#8b96b8;margin-top:24px">
      You&rsquo;re receiving this because you joined the RadioLife waitlist.</p>
  </div>
</div>"""


async def _notify_waitlist_launched(db) -> int:
    """Email the whole waitlist once when the app opens (mode flipped OFF).
    Best-effort + idempotent (per-entry `launched_notified` flag)."""
    try:
        from services.mailgun_client import send_email, is_live
    except Exception as _e:
        logger.warning("mailgun client unavailable: %s", _e)
        return 0
    base = (os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    html = _LAUNCH_EMAIL_HTML.format(base=base or "https://radiolife.app")
    live = False
    try:
        live = bool(is_live())
    except Exception:
        live = False
    sent = 0
    cursor = db.consumer_waitlist.find({"launched_notified": {"$ne": True}})
    async for w in cursor:
        email = w.get("email")
        if not email:
            continue
        try:
            if live:
                await asyncio.to_thread(
                    send_email, email, "RadioLife is live \U0001F389", html,
                    tags=["launch", "waitlist"])
            await db.consumer_waitlist.update_one(
                {"email": email},
                {"$set": {"launched_notified": True, "notified_at": _now_iso()}})
            sent += 1
        except Exception as _e:  # never fail the whole batch on one bad address
            logger.warning("launch email failed for one recipient: %s", _e)
    logger.info("[soft-launch] launch emails processed=%d (live=%s)", sent, live)
    return sent


@router.post("/admin/launch/notify-waitlist")
async def admin_notify_waitlist(request: Request, admin: dict = Depends(require_admin)):
    """Manually (re)send the launch email to any not-yet-notified waitlisters."""
    db = request.app.state.db
    sent = await _notify_waitlist_launched(db)
    return {"ok": True, "processed": sent}


# ─────────────────────── MERCHANT CHECKLIST ────────────────────────
@router.get("/merchant/soft-launch/checklist")
async def merchant_checklist(request: Request, user: dict = Depends(current_user)):
    """Guides a business to 'Launch Ready': claim, profile, logo, catalog."""
    db = request.app.state.db
    uid = user.get("user_id")
    prof = await db.marketplace_profiles.find_one({"owner_user_id": uid})
    claim = await db.soft_launch_claims.find_one({"user_id": uid})
    bid = (prof or {}).get("business_id")
    n_catalog = 0
    if bid:
        n_catalog = (await db.products.count_documents({"business_id": bid})
                     + await db.menu_items.count_documents({"business_id": bid}))
    has_logo = bool((prof or {}).get("logo_url"))
    has_cover = bool((prof or {}).get("cover_urls"))
    has_details = bool((prof or {}).get("public_name") and (prof or {}).get("category")
                       and (prof or {}).get("description"))
    items = [
        {"key": "claim", "label": "Claim your free-months offer", "done": bool(claim),
         "cta_route": "/merchant/soft-launch", "cta_label": "Claim offer"},
        {"key": "profile", "label": "Complete your business profile", "done": has_details,
         "cta_route": "/shop/merchant", "cta_label": "Edit profile"},
        {"key": "logo", "label": "Upload your logo", "done": has_logo,
         "cta_route": "/shop/merchant", "cta_label": "Add logo"},
        {"key": "catalog", "label": "Add your first product or menu item", "done": n_catalog > 0,
         "cta_route": "/shop/merchant/products", "cta_label": "Add products"},
        {"key": "cover", "label": "Add a cover photo", "done": has_cover, "optional": True,
         "cta_route": "/shop/merchant", "cta_label": "Add cover"},
    ]
    required = [i for i in items if not i.get("optional")]
    done_req = sum(1 for i in required if i["done"])
    launch_ready = done_req == len(required)
    if launch_ready and prof and not prof.get("launch_ready"):
        await db.marketplace_profiles.update_one(
            {"owner_user_id": uid},
            {"$set": {"launch_ready": True, "launch_ready_at": _now_iso()}})
    return {"items": items, "progress": {"done": done_req, "total": len(required)},
            "launch_ready": launch_ready, "has_storefront": bool(prof), "catalog_count": n_catalog}


# ─────────────────── FEATURED BUSINESS BOOKING (PAID) ──────────────
async def _my_profile(db, uid: str):
    return await db.marketplace_profiles.find_one({"owner_user_id": uid})


def _valid_future_date(s: str) -> str:
    try:
        d = date.fromisoformat(str(s))
    except Exception:
        raise HTTPException(400, {"code": "bad_date"})
    today = datetime.now(timezone.utc).date()
    if d < today:
        raise HTTPException(400, {"code": "date_in_past"})
    if (d - today).days > 60:
        raise HTTPException(400, {"code": "date_too_far"})
    return d.isoformat()


@router.get("/merchant/featured/availability")
async def featured_availability(request: Request, date: str = "", type: str = "deal",
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    kind = type if type in _FEATURED_PRICING else "deal"
    date_str = _valid_future_date(date) if date else _today_str()
    taken = await _paid_booking(db, kind, date_str)
    return {"date": date_str, "type": kind, "available": not bool(taken),
            "price_cents": _FEATURED_PRICING[kind]}


@router.post("/merchant/featured/checkout")
async def featured_checkout(request: Request, body: dict = Body(default={}),
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    prof = await _my_profile(db, uid)
    if not prof:
        raise HTTPException(400, {"code": "no_storefront",
                                  "message": "Set up your storefront before booking a featured slot."})
    kind = str((body or {}).get("type") or "deal")
    if kind not in _FEATURED_PRICING:
        raise HTTPException(400, {"code": "bad_type"})
    date_str = _valid_future_date((body or {}).get("date") or _today_str())
    if await _paid_booking(db, kind, date_str):
        raise HTTPException(409, {"code": "slot_taken",
                                  "message": "That day is already booked — pick another date."})
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (str((body or {}).get("origin_url") or "").rstrip("/")
              or (os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/"))
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    price = _FEATURED_PRICING[kind]
    headline = str((body or {}).get("headline") or "").strip()[:80] or None
    label = ("Deal of the Day" if kind == "deal" else "Pinned Shop tile")
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"RadioLife {label} — {date_str}"},
                "unit_amount": price,
            },
            "quantity": 1,
        }],
        success_url=f"{origin}/merchant/soft-launch?featured_session={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/merchant/soft-launch?featured_cancel=1",
        metadata={"kind": "featured_booking", "type": kind, "date": date_str,
                  "business_id": prof.get("business_id"), "buyer_id": uid},
    )
    booking = {"booking_id": "fb_" + secrets.token_urlsafe(10), "session_id": session.id,
               "type": kind, "date": date_str, "business_id": prof.get("business_id"),
               "owner_user_id": uid, "business_name": prof.get("public_name"),
               "headline": headline, "price_cents": price, "status": "pending",
               "created_at": _now_iso()}
    await db.featured_bookings.insert_one(dict(booking))
    return {"ok": True, "checkout_url": session.url, "session_id": session.id,
            "price_cents": price, "date": date_str, "type": kind}


@router.get("/merchant/featured/mine")
async def featured_mine(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    items = []
    async for b in db.featured_bookings.find(
            {"owner_user_id": user.get("user_id")}, {"_id": 0}).sort("date", -1).limit(50):
        items.append(b)
    return {"items": items, "pricing": _FEATURED_PRICING}


@router.get("/merchant/featured/{session_id}/status")
async def featured_status(session_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    rec = await db.featured_bookings.find_one(
        {"session_id": session_id, "owner_user_id": user.get("user_id")})
    if not rec:
        raise HTTPException(404, {"code": "booking_not_found"})
    if rec.get("status") == "paid":
        return {"status": "paid", "type": rec.get("type"), "date": rec.get("date")}
    if not stripe.api_key:
        return {"status": rec.get("status", "pending")}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": rec.get("status", "pending")}
    if sess.get("payment_status") == "paid":
        # Double-booking guard: if someone else already paid this slot, refundable
        # edge — mark this one 'superseded' rather than active.
        other = await db.featured_bookings.find_one(
            {"type": rec["type"], "date": rec["date"], "status": "paid",
             "session_id": {"$ne": session_id}})
        new_status = "superseded" if other else "paid"
        await db.featured_bookings.update_one(
            {"session_id": session_id},
            {"$set": {"status": new_status, "paid_at": _now_iso()}})
        if new_status == "paid":
            _DEAL_CACHE["key"] = None  # bust so today's deal reflects the booking
        return {"status": new_status, "type": rec.get("type"), "date": rec.get("date")}
    return {"status": "pending"}


# ─────────────────────── TEASER (SNEAK PEEK) EMAIL ─────────────────
_TEASER_EMAIL_HTML = """\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;
  background:#0b0f24;color:#fff;border-radius:16px;overflow:hidden">
  <div style="padding:30px 28px;background:linear-gradient(135deg,#3b82f6,#8b5cf6)">
    <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;opacity:.9">
      RadioLife &middot; sneak peek</div>
    <div style="font-size:26px;font-weight:900;margin-top:8px;line-height:1.15">
      Something good is coming \U0001F440</div>
  </div>
  <div style="padding:28px">
    <p style="font-size:15px;line-height:1.6;color:#d7dcf0">
      {days} Live radio, AI radio built around you, local deals, games and rewards for
      every minute you listen &mdash; all in one app. Great local businesses are setting
      up their storefronts right now.</p>
    <p style="font-size:15px;line-height:1.6;color:#d7dcf0">
      Want to skip the line? Invite friends with your waitlist link to move up the queue.</p>
    <a href="{base}" style="display:inline-block;margin-top:14px;background:#fff;
      color:#0b0f24;font-weight:800;text-decoration:none;padding:13px 26px;
      border-radius:999px;font-size:14px">See what's coming &rarr;</a>
    <p style="font-size:12px;color:#8b96b8;margin-top:24px">
      You&rsquo;re receiving this because you joined the RadioLife waitlist.</p>
  </div>
</div>"""


async def _send_teaser(db, min_hours_between: int = 48) -> int:
    """Best-effort 'sneak peek' email to waitlisters not yet launch-notified,
    throttled so nobody gets one more than once per `min_hours_between`."""
    try:
        from services.mailgun_client import send_email, is_live
    except Exception as _e:
        logger.warning("mailgun client unavailable: %s", _e)
        return 0
    s = await get_launch_settings(db)
    days_txt = "Launching soon."
    la = s.get("launch_at")
    if la:
        try:
            dt = datetime.fromisoformat(str(la).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = max(0, (dt - _now()).days)
            days_txt = f"Just {days} day{'s' if days != 1 else ''} to go."
        except Exception:
            pass
    base = (os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/") or "https://radiolife.app"
    html = _TEASER_EMAIL_HTML.format(days=days_txt, base=base)
    live = False
    try:
        live = bool(is_live())
    except Exception:
        live = False
    cutoff = (_now() - timedelta(hours=min_hours_between)).isoformat()
    sent = 0
    cursor = db.consumer_waitlist.find({
        "launched_notified": {"$ne": True},
        "$or": [{"teaser_sent_at": {"$exists": False}},
                {"teaser_sent_at": {"$lt": cutoff}}],
    })
    async for w in cursor:
        email = w.get("email")
        if not email:
            continue
        try:
            if live:
                await asyncio.to_thread(
                    send_email, email, "A sneak peek at RadioLife \U0001F440", html,
                    tags=["teaser", "waitlist"])
            await db.consumer_waitlist.update_one(
                {"email": email},
                {"$set": {"teaser_sent_at": _now_iso()}, "$inc": {"teaser_count": 1}})
            sent += 1
        except Exception as _e:
            logger.warning("teaser email failed for one recipient: %s", _e)
    logger.info("[soft-launch] teaser emails processed=%d (live=%s)", sent, live)
    return sent


@router.get("/admin/launch/teaser-stats")
async def admin_teaser_stats(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    total = await db.consumer_waitlist.count_documents({})
    teased = await db.consumer_waitlist.count_documents({"teaser_count": {"$gt": 0}})
    cutoff = (_now() - timedelta(hours=48)).isoformat()
    eligible = await db.consumer_waitlist.count_documents({
        "launched_notified": {"$ne": True},
        "$or": [{"teaser_sent_at": {"$exists": False}},
                {"teaser_sent_at": {"$lt": cutoff}}],
    })
    return {"total": total, "teased": teased, "eligible_now": eligible}


@router.post("/admin/launch/teaser")
async def admin_send_teaser(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    sent = await _send_teaser(db)
    return {"ok": True, "processed": sent}
