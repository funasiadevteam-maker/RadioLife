"""Phase 42 Session 1 — Banner ad inventory + decision + advertiser CRUD.

This is the v2 (path-based slot) endpoint set. The earlier
`/api/ads/banner/{slot_id}` endpoint (banner_ads.py) is kept for
back-compat; new frontend uses the decision endpoint here.

Collections:
   banner_ad_slots         — canonical slot inventory (seeded at boot)
   banner_ad_campaigns     — advertiser-submitted campaigns
   banner_ad_impressions   — per-impression log w/ click flag
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user

router = APIRouter(prefix="/api/ads", tags=["banner-ads-v2"])
log = logging.getLogger("bigfm.banner_ads_v2")

VALID_STATUS = {"pending_payment", "pending", "approved", "active",
                "paused", "completed", "rejected"}
ADSENSE_CLIENT_ID = os.environ.get("ADSENSE_CLIENT_ID", "").strip()


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str: return _now().isoformat()


SEED_SLOTS = [
    # Phase 42 S2 — 12 canonical slot inventory. `mobile_size: null` means
    # the slot is hidden on small viewports (display:none below 1024px).
    # `mobile_only: true` means hidden on desktop.
    {"slot_key": "top_billboard",         "size": "970x250", "mobile_size": "320x100",
     "position": "top",                   "page_route_pattern": ".*"},
    {"slot_key": "left_skyscraper",       "size": "160x600", "mobile_size": None,
     "position": "left",                  "page_route_pattern": ".*"},
    {"slot_key": "right_skyscraper",      "size": "160x600", "mobile_size": None,
     "position": "right",                 "page_route_pattern": ".*"},
    {"slot_key": "featured_horizontal",   "size": "728x90",  "mobile_size": "300x250",
     "position": "inline_horizontal",     "page_route_pattern": "^/(home|community|news)$"},
    {"slot_key": "inline_mpu_1",          "size": "300x250", "mobile_size": "300x250",
     "position": "inline_block",          "page_route_pattern": ".*"},
    {"slot_key": "inline_mpu_2",          "size": "300x250", "mobile_size": "300x250",
     "position": "inline_block",          "page_route_pattern": ".*"},
    {"slot_key": "mid_horizontal",        "size": "728x90",  "mobile_size": "320x100",
     "position": "inline_horizontal",     "page_route_pattern": ".*"},
    {"slot_key": "half_page_right",       "size": "300x600", "mobile_size": None,
     "position": "right",                 "page_route_pattern": "^/(news)$"},
    {"slot_key": "inline_square",         "size": "250x250", "mobile_size": "250x250",
     "position": "inline_block",          "page_route_pattern": ".*"},
    {"slot_key": "news_inline_rectangle", "size": "336x280", "mobile_size": "300x250",
     "position": "inline_block",          "page_route_pattern": "^/(news)$"},
    {"slot_key": "bottom_horizontal",     "size": "728x90",  "mobile_size": "320x100",
     "position": "footer",                "page_route_pattern": ".*"},
    {"slot_key": "mobile_sticky_bottom",  "size": None,      "mobile_size": "320x50",
     "position": "sticky_bottom",         "mobile_only": True,
     "page_route_pattern": ".*"},
    # Phase 42 S1 legacy slots — kept for back-compat with any pages
    # still wired to them. Will be retired in S3.
    {"slot_key": "top_leaderboard",       "size": "970x90",  "mobile_size": "320x100",
     "position": "top",                   "page_route_pattern": ".*"},
    {"slot_key": "right_rail",            "size": "160x600", "mobile_size": None,
     "position": "right",                 "page_route_pattern": ".*"},
    {"slot_key": "left_rail",             "size": "160x600", "mobile_size": None,
     "position": "left",                  "page_route_pattern": ".*"},
    {"slot_key": "center_mid",            "size": "300x250", "mobile_size": "300x250",
     "position": "center",                "page_route_pattern": ".*"},
]


# Phase 42 S2 — expanded house creative pool (12 variants) for better
# rotation with 12 slots per page.
HOUSE_CREATIVES = [
    {"headline": "Tired of ads?",
     "sub_text": "Go ad-free with RadioLife Premium →",  "click_url": "/premium"},
    {"headline": "Discover community radio",
     "sub_text": "Listener-built stations, on every vibe →",
     "click_url": "/community"},
    {"headline": "Build your own station",
     "sub_text": "Create my radio — free, takes a minute →",
     "click_url": "/radio/create"},
    {"headline": "Listen, earn rewards",
     "sub_text": "BigCoins for every session →",  "click_url": "/wallet"},
    {"headline": "New on RadioLife: News Radio",
     "sub_text": "AI-curated headlines, in your dialect →",
     "click_url": "/radio/news"},
    {"headline": "Win concert tickets weekly",
     "sub_text": "Free entry — drop your dial in →",
     "click_url": "/games"},
    {"headline": "Drive time deals near you",
     "sub_text": "Tap to see today's offers along your route →",
     "click_url": "/commute"},
    {"headline": "Friday Night Bollywood",
     "sub_text": "Live now — non-stop dance floor →",
     "click_url": "/r/friday-night-bollywood"},
    {"headline": "Coffee on your route",
     "sub_text": "30% off Starbucks — tap to claim →",
     "click_url": "/commute"},
    {"headline": "Trivia rewards await",
     "sub_text": "Daily quiz — win BigCoins, free spins →",
     "click_url": "/trivia"},
    {"headline": "Pick your AI radio host",
     "sub_text": "Kishore, Aanya, Charlie — your dial, your DJ →",
     "click_url": "/personas"},
    {"headline": "Premium · 7-day free trial",
     "sub_text": "Ad-free audio, premium stations →",
     "click_url": "/premium"},
]


def _pick_house_creative(slot_key: str, recent_indices: set | None = None) -> tuple[dict, int]:
    """Phase 42 S2 — anti-adjacent rotation. Caller can pass `recent_indices`
    (the set of variant indices already served in the same page-load) so the
    next pick deliberately avoids them. Falls back to plain round-robin when
    the recent set is empty or covers >70% of the pool."""
    pool = HOUSE_CREATIVES
    start = _house_idx.get(slot_key, 0)
    for offset in range(len(pool)):
        idx = (start + offset) % len(pool)
        if recent_indices and idx in recent_indices and \
           len(recent_indices) < int(len(pool) * 0.7):
            continue
        _house_idx[slot_key] = (idx + 1) % len(pool)
        return pool[idx], idx
    # Pool exhausted (shouldn't happen with 12 slots + 12 variants).
    return pool[start], start


_house_idx = {"top_billboard": 0, "left_skyscraper": 1, "right_skyscraper": 2,
               "featured_horizontal": 3, "inline_mpu_1": 4, "inline_mpu_2": 5,
               "mid_horizontal": 6, "half_page_right": 7, "inline_square": 8,
               "news_inline_rectangle": 9, "bottom_horizontal": 10,
               "mobile_sticky_bottom": 11,
               # Legacy.
               "top_leaderboard": 0, "right_rail": 1, "left_rail": 2,
               "center_mid": 3}


async def ensure_banner_v2_indexes(db) -> None:
    try:
        await db.banner_ad_slots.create_index("slot_key", unique=True)
        await db.banner_ad_campaigns.create_index([("status", 1), ("end_date", 1)])
        await db.banner_ad_campaigns.create_index("advertiser_id")
        await db.banner_ad_impressions.create_index(
            [("user_id", 1), ("campaign_id", 1), ("ts", -1)])
        for s in SEED_SLOTS:
            # Phase 42 S2 — also $set mobile_size + mobile_only on existing
            # rows so the 12-slot inventory migrates cleanly. `position`
            # & `size` already insert-only via $setOnInsert.
            await db.banner_ad_slots.update_one(
                {"slot_key": s["slot_key"]},
                {"$setOnInsert": {"active": True, "created_at": _now_iso()},
                 "$set": {k: v for k, v in s.items()
                            if k in ("size", "mobile_size", "mobile_only",
                                     "position", "page_route_pattern")}},
                upsert=True)
    except Exception as e:
        log.warning("[banner_v2] index/seed: %s", e)


def _is_premium(user: dict) -> bool:
    return bool(user.get("is_premium") or user.get("trial_active")
                 or user.get("subscription_status") == "active")


async def _frequency_cap_ok(db, user_id: str, campaign_id: str,
                              cap: int) -> bool:
    if not cap: return True
    today = _now_iso()[:10]
    n = await db.banner_ad_impressions.count_documents({
        "user_id": user_id, "campaign_id": campaign_id,
        "ts": {"$gte": today}})
    return n < cap


# ─── decision endpoint ───────────────────────────────────────────────

@router.get("/banner/decision")
async def banner_decision(request: Request,
                           slot_key: str,
                           page_route: str,
                           user: dict = Depends(current_user)):
    """Waterfall: direct-sold → AdSense backfill (if configured) → house.
    Premium users STILL see banners (only audio is suppressed for them)."""
    db = request.app.state.db
    slot = await db.banner_ad_slots.find_one({"slot_key": slot_key,
                                                "active": True})
    if not slot:
        raise HTTPException(404, {"code": "slot_not_found"})

    # 1. Direct-sold — match active campaigns that include this slot.
    cand = db.banner_ad_campaigns.find({
        "slot_keys": slot_key,
        "status": "active",
        "start_date": {"$lte": _now_iso()},
        "end_date":   {"$gte": _now_iso()},
    }).limit(20)
    chosen: Optional[dict] = None
    async for c in cand:
        if not await _frequency_cap_ok(db, user["user_id"], c["_id"],
                                          c.get("frequency_cap_per_user_per_day", 0)):
            continue
        chosen = c
        break

    if chosen:
        impr_id = "imp_" + uuid.uuid4().hex[:14]
        await db.banner_ad_impressions.insert_one({
            "_id": impr_id, "campaign_id": chosen["_id"],
            "slot_key": slot_key, "user_id": user["user_id"],
            "session_id": request.headers.get("x-session-id"),
            "page_route": page_route, "ts": _now_iso(),
            "was_clicked": False, "click_ts": None})
        return {"source": "direct",
                "campaign_id": chosen["_id"],
                "creative_image_url": chosen["creative_image_url"],
                "click_url": chosen["click_url"],
                "size": slot["size"],
                "impression_pixel": f"/api/ads/banner/_pixel/{impr_id}"}

    # 2. AdSense backfill (only if client_id configured)
    if ADSENSE_CLIENT_ID:
        slot_env = f"ADSENSE_SLOT_ID_{slot_key.upper()}"
        slot_id = os.environ.get(slot_env, "")
        if slot_id:
            return {"source": "adsense",
                    "client_id": ADSENSE_CLIENT_ID,
                    "slot_id":   slot_id,
                    "size":      slot["size"]}

    # 3. House fallback — Phase 42 S2: anti-adjacent rotation. Client
    # passes `recent` (comma-separated variant indices already served
    # on the same page-load) so the next pick deliberately avoids them.
    recent_param = request.query_params.get("recent", "")
    recent_indices: set[int] = set()
    for tok in recent_param.split(","):
        tok = tok.strip()
        if tok.isdigit():
            recent_indices.add(int(tok))
    variant, variant_idx = _pick_house_creative(slot_key, recent_indices)
    # Phase 42 S2 — resolve mobile size if the slot has one. Frontend
    # uses `size` + `mobile_size` together to pick the right asset at
    # render-time based on viewport width.
    return {"source": "house",
            "creative_image_url": None,
            "headline": variant["headline"],
            "sub_text": variant["sub_text"],
            "click_url": variant["click_url"],
            "size": slot.get("size"),
            "mobile_size": slot.get("mobile_size"),
            "mobile_only": bool(slot.get("mobile_only")),
            "variant_idx": variant_idx}


@router.post("/banner/click")
async def banner_click(request: Request, body: dict,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    impr_id = body.get("impression_id")
    if impr_id:
        await db.banner_ad_impressions.update_one(
            {"_id": impr_id},
            {"$set": {"was_clicked": True, "click_ts": _now_iso()}})
    return {"ok": True, "redirect": body.get("click_url") or "/"}


@router.get("/banner/_pixel/{impression_id}")
async def banner_pixel(impression_id: str, request: Request):
    # 1x1 GIF pixel — already-logged impression. Mostly client-side hook.
    from fastapi.responses import Response
    GIF = bytes([0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,0x80,
                  0x00,0x00,0xff,0xff,0xff,0x00,0x00,0x00,0x21,0xf9,0x04,
                  0x01,0x00,0x00,0x00,0x00,0x2c,0x00,0x00,0x00,0x00,0x01,
                  0x00,0x01,0x00,0x00,0x02,0x02,0x44,0x01,0x00,0x3b])
    return Response(content=GIF, media_type="image/gif")


# ─── advertiser CRUD ─────────────────────────────────────────────────

@router.post("/advertiser/banner-campaigns")
async def create_banner_campaign(request: Request, body: dict,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    cid = "bcamp_" + uuid.uuid4().hex[:14]
    slot_keys = body.get("slot_keys") or []
    # Validate slot existence
    for sk in slot_keys:
        if not await db.banner_ad_slots.find_one({"slot_key": sk}):
            raise HTTPException(400, {"code": "unknown_slot", "slot": sk})
    doc = {
        "_id":               cid,
        "campaign_id":       cid,
        "advertiser_id":     user["user_id"],
        "slot_keys":         slot_keys,
        "creative_image_url": body.get("creative_image_url"),
        "click_url":         body.get("click_url"),
        "start_date":        body.get("start_date") or _now_iso(),
        "end_date":          body.get("end_date") or _now_iso(),
        "daily_budget":      float(body.get("daily_budget") or 0),
        "total_budget":      float(body.get("total_budget") or 0),
        "status":            "pending_payment",
        "targeting_json":    body.get("targeting_json") or {},
        "frequency_cap_per_user_per_day":
                              int(body.get("frequency_cap_per_user_per_day") or 5),
        "created_at":        _now_iso(),
        "approved_at":       None,
        "rejected_reason":   None,
        "stripe_session_id": None,
    }
    await db.banner_ad_campaigns.insert_one(doc)
    return {"ok": True, "campaign_id": cid, "status": "pending_payment"}


@router.get("/advertiser/banner-campaigns")
async def list_my_banner_campaigns(request: Request,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    async for c in db.banner_ad_campaigns.find(
            {"advertiser_id": user["user_id"]}).sort("created_at", -1):
        impr = await db.banner_ad_impressions.count_documents({"campaign_id": c["_id"]})
        clicks = await db.banner_ad_impressions.count_documents({"campaign_id": c["_id"], "was_clicked": True})
        c.pop("_id", None)
        c["impressions"] = impr
        c["clicks"] = clicks
        c["ctr"] = (clicks / impr) if impr else 0.0
        out.append(c)
    return {"count": len(out), "items": out}


@router.get("/advertiser/banner-campaigns/{cid}")
async def get_my_banner_campaign(cid: str, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.banner_ad_campaigns.find_one({"_id": cid,
                                                 "advertiser_id": user["user_id"]})
    if not c:
        raise HTTPException(404, {"code": "not_found"})
    c.pop("_id", None)
    return c


@router.patch("/advertiser/banner-campaigns/{cid}")
async def patch_banner_campaign(cid: str, request: Request, body: dict,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    allowed = {"paused", "active"}
    new_status = body.get("status")
    if new_status not in allowed:
        raise HTTPException(400, {"code": "bad_status", "allowed": list(allowed)})
    c = await db.banner_ad_campaigns.find_one({"_id": cid,
                                                 "advertiser_id": user["user_id"]})
    if not c:
        raise HTTPException(404, {"code": "not_found"})
    if c["status"] not in ("active", "paused"):
        raise HTTPException(400, {"code": "cannot_change_state",
                                  "current": c["status"]})
    await db.banner_ad_campaigns.update_one(
        {"_id": cid}, {"$set": {"status": new_status, "updated_at": _now_iso()}})
    return {"ok": True, "status": new_status}


# ─── admin moderation ────────────────────────────────────────────────

def _require_admin(u: dict):
    if not u or not u.get("is_admin"):
        raise HTTPException(403, {"code": "forbidden"})


@router.get("/admin/banner-campaigns")
async def admin_list_banner_campaigns(request: Request,
                                         status: str = "pending",
                                         user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    q: dict = {} if status == "all" else {"status": status}
    out = []
    async for c in db.banner_ad_campaigns.find(q).sort("created_at", -1):
        c.pop("_id", None)
        out.append(c)
    return {"count": len(out), "items": out}


@router.post("/admin/banner-campaigns/{cid}/approve")
async def admin_approve(cid: str, request: Request,
                          user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    r = await db.banner_ad_campaigns.update_one(
        {"_id": cid, "status": "pending"},
        {"$set": {"status": "active", "approved_at": _now_iso(),
                  "approved_by": user["user_id"]}})
    if not r.matched_count:
        raise HTTPException(404, {"code": "not_pending"})
    return {"ok": True, "new_status": "active"}


@router.post("/admin/banner-campaigns/{cid}/reject")
async def admin_reject(cid: str, request: Request, body: dict,
                         user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    r = await db.banner_ad_campaigns.update_one(
        {"_id": cid, "status": "pending"},
        {"$set": {"status": "rejected",
                  "rejected_reason": (body.get("reason") or "")[:300],
                  "rejected_by": user["user_id"]}})
    if not r.matched_count:
        raise HTTPException(404, {"code": "not_pending"})
    return {"ok": True, "new_status": "rejected"}


# ─── Stripe self-serve checkout ──────────────────────────────────────

@router.post("/advertiser/banner-campaigns/{cid}/checkout")
async def create_checkout(cid: str, request: Request,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.banner_ad_campaigns.find_one(
        {"_id": cid, "advertiser_id": user["user_id"]})
    if not c:
        raise HTTPException(404, {"code": "not_found"})
    if c["status"] != "pending_payment":
        raise HTTPException(400, {"code": "wrong_status", "current": c["status"]})
    amount_cents = max(50, int(c["total_budget"] * 100))
    # Use existing stripe wiring if present, else mock.
    session_url = None
    session_id = None
    try:
        from services.stripe_client import create_checkout_session
        session = await create_checkout_session(
            amount_cents=amount_cents,
            currency="usd",
            metadata={"campaign_id": cid, "kind": "banner_campaign"},
            success_url=f"/advertiser/banner/buy/success?cid={cid}",
            cancel_url=f"/advertiser/banner/buy/cancel?cid={cid}")
        session_id  = session.get("id")
        session_url = session.get("url")
    except Exception as e:
        log.info("[banner_v2] stripe mock-mode (%s)", e)
        session_id  = "cs_mock_" + uuid.uuid4().hex[:10]
        session_url = f"/advertiser/banner/buy/success?cid={cid}&mock=true"
        # Mock mode: immediately flip to pending (skip real webhook).
        await db.banner_ad_campaigns.update_one(
            {"_id": cid}, {"$set": {"status": "pending",
                                       "stripe_session_id": session_id,
                                       "paid_at_mock": _now_iso()}})
        return {"ok": True, "checkout_url": session_url,
                "session_id": session_id, "mock": True}
    await db.banner_ad_campaigns.update_one(
        {"_id": cid}, {"$set": {"stripe_session_id": session_id}})
    return {"ok": True, "checkout_url": session_url,
            "session_id": session_id, "mock": False}
