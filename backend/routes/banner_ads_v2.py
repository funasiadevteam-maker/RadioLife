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
import asyncio
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)

from auth import current_user
from services.premium_gate import is_premium_or_trial

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
    # New Look V2 right-rail inventory — a stack of buyable 300x250 MPUs
    # advertisers can purchase per-slot. Desktop-only (hidden on mobile).
    {"slot_key": "right_rail_mpu_1",      "size": "300x250", "mobile_size": None,
     "position": "right",                 "page_route_pattern": ".*"},
    {"slot_key": "right_rail_mpu_2",      "size": "300x250", "mobile_size": None,
     "position": "right",                 "page_route_pattern": ".*"},
    {"slot_key": "right_rail_mpu_3",      "size": "300x250", "mobile_size": None,
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
     "sub_text": "Go ad-free with FUUSIC Premium →",  "click_url": "/premium"},
    {"headline": "Discover community radio",
     "sub_text": "Listener-built stations, on every vibe →",
     "click_url": "/community"},
    {"headline": "Build your own station",
     "sub_text": "Create my radio — free, takes a minute →",
     "click_url": "/radio/create"},
    {"headline": "Listen, earn rewards",
     "sub_text": "BigPoints for every session →",  "click_url": "/wallet"},
    {"headline": "New on FUUSIC: News Radio",
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
     "sub_text": "Daily quiz — win BigPoints, free spins →",
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
    Premium (ad-free) users get NO FUUSIC-inserted display banners —
    only opt-in offers/games/Dining remain for them."""
    db = request.app.state.db
    # Premium ad-free short-circuit (Phase COMPANION.1). Mirrors the audio
    # pre/mid-roll suppression so Premium is banner-free across the app.
    if is_premium_or_trial(user) and \
            (user.get("ad_settings") or {}).get("ad_free_enabled", True):
        return {"source": "none", "reason": "premium"}
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
    recent_param = request.query_params.get("recent", "")
    recent_ids = {t.strip() for t in recent_param.split(",") if t.strip()}
    eligible: list[dict] = []
    async for c in cand:
        if not await _frequency_cap_ok(db, user["user_id"], c["_id"],
                                          c.get("frequency_cap_per_user_per_day", 0)):
            continue
        eligible.append(c)
    if eligible:
        # Rotation: drop campaigns already shown on this page-load, then pick
        # weighted-random so the same business isn't always served first.
        pool = [c for c in eligible if c["_id"] not in recent_ids] or eligible
        # Clamp weight defensively (1–10) so a legacy row with an uncapped
        # weight can't monopolise rotation.
        weights = [min(10, max(1, int(c.get("weight") or c.get("priority") or 1)))
                   for c in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]

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
                "mobile_size": slot.get("mobile_size"),
                "mobile_only": bool(slot.get("mobile_only")),
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

RAIL_SLOT_KEYS = ["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3"]
RAIL_CPM = 8.0  # house CPM (USD per 1000 impressions) used for spend estimate


@router.get("/advertiser/rail-analytics")
async def advertiser_rail_analytics(request: Request,
                                       user: dict = Depends(current_user)):
    """Per-slot impressions / clicks / spend for the caller's right-rail campaigns."""
    db = request.app.state.db
    advertiser_id = user["user_id"]
    camp_ids = [c["_id"] async for c in db.banner_ad_campaigns.find(
        {"advertiser_id": advertiser_id, "slot_keys": {"$in": RAIL_SLOT_KEYS}}, {"_id": 1})]
    agg = {k: {"impressions": 0, "clicks": 0} for k in RAIL_SLOT_KEYS}
    if camp_ids:
        pipeline = [
            {"$match": {"campaign_id": {"$in": camp_ids}, "slot_key": {"$in": RAIL_SLOT_KEYS}}},
            {"$group": {"_id": "$slot_key",
                        "impressions": {"$sum": 1},
                        "clicks": {"$sum": {"$cond": [{"$eq": ["$was_clicked", True]}, 1, 0]}}}},
        ]
        async for row in db.banner_ad_impressions.aggregate(pipeline):
            if row["_id"] in agg:
                agg[row["_id"]] = {"impressions": row["impressions"], "clicks": row["clicks"]}
    slots, ti, tc, ts = [], 0, 0, 0.0
    for k in RAIL_SLOT_KEYS:
        i, cl = agg[k]["impressions"], agg[k]["clicks"]
        spend = round(i / 1000.0 * RAIL_CPM, 2)
        slots.append({"slot_key": k, "impressions": i, "clicks": cl,
                      "ctr": round(cl / i, 4) if i else 0.0, "spend": spend})
        ti += i; tc += cl; ts += spend
    return {"cpm": RAIL_CPM, "campaigns": len(camp_ids), "slots": slots,
            "totals": {"impressions": ti, "clicks": tc,
                       "ctr": round(tc / ti, 4) if ti else 0.0, "spend": round(ts, 2)}}


def _require_admin(u: dict):
    if not u or not (u.get("is_admin") or u.get("role") == "admin"):
        raise HTTPException(403, {"code": "forbidden"})


STATIC_ROOT = "/app/backend/static"


def _creative_health(url: str | None) -> Optional[str]:
    """Return an issue string for a broken/degenerate creative, else None.
    Only deep-checks locally-served (/api/static/...) files; external https
    creatives are assumed OK (no network probe)."""
    if not url:
        return "missing_url"
    if url.startswith("/api/static/"):
        path = os.path.join(STATIC_ROOT, url[len("/api/static/"):])
        if not os.path.exists(path):
            return "file_missing"
        try:
            from PIL import Image
            with Image.open(path) as im:
                w, h = im.size
                if w <= 2 or h <= 2:
                    return f"degenerate_{w}x{h}"
                if all(mn == mx for (mn, mx) in im.convert("RGB").getextrema()):
                    return "blank_single_color"
        except Exception as e:
            return f"unreadable:{str(e)[:40]}"
    return None


def _validate_upload_image(data: bytes) -> tuple[int, int]:
    """Reject tiny / blank / unreadable banner uploads BEFORE they can enter
    the rotation. Raises HTTPException(400) with a merchant-friendly message."""
    import io
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise HTTPException(400, {"code": "invalid_image",
            "message": "That file isn't a readable image. Upload a PNG, JPG or WEBP."})
    w, h = im.size
    if w < 200 or h < 50:
        raise HTTPException(400, {"code": "image_too_small",
            "message": f"Banner is too small ({w}×{h}px). Use at least 200×50px.",
            "min": "200x50", "got": f"{w}x{h}"})
    try:
        if all(mn == mx for (mn, mx) in im.convert("RGB").getextrema()):
            raise HTTPException(400, {"code": "image_blank",
                "message": "That image looks blank. Upload your actual banner artwork."})
    except HTTPException:
        raise
    except Exception:
        pass
    return w, h


@router.get("/admin/rotation-health")
async def admin_rotation_health(request: Request,
                                user: dict = Depends(current_user)):
    """List every ACTIVE campaign whose creative is missing, 404s, is a
    degenerate ≤2px placeholder, blank, or unreadable — so bad creatives
    never silently sit in the live rotation."""
    _require_admin(user)
    db = request.app.state.db
    bad, total = [], 0
    async for c in db.banner_ad_campaigns.find({"status": "active"}):
        total += 1
        issue = _creative_health(c.get("creative_image_url"))
        if issue:
            bad.append({
                "campaign_id": c.get("_id"),
                "sponsor_name": c.get("sponsor_name"),
                "business_id": c.get("business_id"),
                "source": c.get("source"),
                "slot_keys": c.get("slot_keys", []),
                "creative_image_url": c.get("creative_image_url"),
                "issue": issue,
            })
    return {"active_total": total, "unhealthy_count": len(bad), "items": bad}


@router.post("/admin/rotation-health/{cid}/pause")
async def admin_pause_unhealthy(cid: str, request: Request,
                                user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    r = await db.banner_ad_campaigns.update_one(
        {"_id": cid},
        {"$set": {"status": "paused", "paused_reason": "unhealthy_creative",
                  "updated_at": _now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, {"code": "not_found"})
    return {"ok": True, "status": "paused"}


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


# ─── Business-portal SELF-SERVE banners ──────────────────────────────
# A store owner uploads a creative + picks slot(s) and either goes live
# instantly (auto-approved house inventory), submits for admin review, or
# pays (reuses the checkout above). Plus per-campaign performance.

PORTAL_SLOT_KEYS = ["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3",
                    "inline_mpu_1", "inline_mpu_2"]


async def _owned_business_or_403(db, merchant_id: str, user: dict) -> dict:
    if not merchant_id:
        raise HTTPException(400, {"code": "merchant_id_required"})
    biz = await db.businesses.find_one({
        "$and": [
            {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]},
            {"$or": [{"owner_user_id": user["user_id"]},
                     {"owner_user_ids": user["user_id"]}]},
        ]})
    if not biz:
        raise HTTPException(403, {"code": "not_your_business"})
    return biz


@router.get("/portal/banner/slots")
async def portal_banner_slots(request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    for sk in PORTAL_SLOT_KEYS:
        s = await db.banner_ad_slots.find_one({"slot_key": sk})
        if s:
            out.append({"slot_key": sk, "label": s.get("label") or sk,
                        "size": s.get("size")})
    return {"slots": out}


@router.post("/portal/banner/upload-creative")
async def portal_upload_creative(request: Request,
                                 merchant_id: str = Form(...),
                                 file: UploadFile = File(...),
                                 user: dict = Depends(current_user)):
    db = request.app.state.db
    await _owned_business_or_403(db, merchant_id, user)
    ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
    if file.content_type not in ext_map:
        raise HTTPException(400, {"code": "unsupported_content_type"})
    data = await file.read()
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(400, {"code": "file_too_large", "limit_mb": 4})
    # Reject tiny / blank / unreadable uploads so a broken creative can never
    # reach the live rotation (Rotation Health guard, upload-side).
    _validate_upload_image(data)
    key_dir = f"portal/{merchant_id}"
    fname = f"{uuid.uuid4().hex[:12]}.{ext_map[file.content_type]}"
    disk_dir = f"/app/backend/static/banners/{key_dir}"
    os.makedirs(disk_dir, exist_ok=True)
    with open(f"{disk_dir}/{fname}", "wb") as fh:
        fh.write(data)
    try:
        from services.object_storage import get_storage
        await asyncio.to_thread(lambda: get_storage().upload_bytes(
            key=f"static/banners/{key_dir}/{fname}", data=data,
            content_type=file.content_type))
    except Exception:
        pass
    return {"ok": True,
            "creative_image_url": f"/api/static/banners/{key_dir}/{fname}"}


@router.post("/portal/banner/publish")
async def portal_banner_publish(body: dict, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    merchant_id = body.get("merchant_id")
    biz = await _owned_business_or_403(db, merchant_id, user)
    creative = body.get("creative_image_url")
    if not creative:
        raise HTTPException(400, {"code": "creative_required"})
    slot_keys = [sk for sk in (body.get("slot_keys") or [])
                 if sk in PORTAL_SLOT_KEYS]
    if not slot_keys:
        raise HTTPException(400, {"code": "slot_required"})
    mode = (body.get("publish_mode") or "instant").lower()
    status = {"instant": "active", "review": "pending",
              "paid": "pending_payment"}.get(mode, "active")
    click_url = (body.get("click_url")
                 or f"/business/{biz.get('slug') or merchant_id}")
    cid = "bcamp_" + uuid.uuid4().hex[:14]
    doc = {
        "_id": cid, "campaign_id": cid,
        "advertiser_id": user["user_id"], "business_id": merchant_id,
        "sponsor_name": biz.get("name"),
        "slot_keys": slot_keys, "creative_image_url": creative,
        "click_url": click_url,
        "start_date": _now_iso(),
        "end_date": (datetime.now(timezone.utc)
                     + timedelta(days=180)).isoformat(),
        "daily_budget": 0.0, "total_budget": 0.0,
        "status": status, "targeting_json": {},
        "frequency_cap_per_user_per_day": int(body.get("frequency_cap") or 8),
        # Server-side clamp (1–10) so a merchant can't pass weight=99999 to
        # permanently dominate the weighted-random rotation.
        "weight": min(10, max(1, int(body.get("weight") or 1))),
        "created_at": _now_iso(),
        "approved_at": _now_iso() if status == "active" else None,
        "approved_by": "self_serve_auto" if status == "active" else None,
        "rejected_reason": None, "stripe_session_id": None,
        "source": "portal_self_serve",
    }
    await db.banner_ad_campaigns.insert_one(doc)
    return {"ok": True, "campaign_id": cid, "status": status,
            "live": status == "active"}


@router.get("/portal/banner/mine")
async def portal_banner_mine(merchant_id: str, request: Request,
                             user: dict = Depends(current_user)):
    db = request.app.state.db
    await _owned_business_or_403(db, merchant_id, user)
    out = []
    async for c in db.banner_ad_campaigns.find(
            {"business_id": merchant_id}).sort("created_at", -1):
        cid = c["_id"]
        impressions = await db.banner_ad_impressions.count_documents(
            {"campaign_id": cid})
        clicks = await db.banner_ad_impressions.count_documents(
            {"campaign_id": cid, "was_clicked": True})
        out.append({
            "campaign_id": cid, "status": c.get("status"),
            "creative_image_url": c.get("creative_image_url"),
            "click_url": c.get("click_url"),
            "slot_keys": c.get("slot_keys", []),
            "created_at": c.get("created_at"),
            "impressions": impressions, "clicks": clicks,
            # CTR is a FRACTION (clicks/impressions) — consumers multiply by
            # 100 for display. Kept consistent with /advertiser/banner-campaigns
            # and /advertiser/rail-analytics.
            "ctr": round(clicks / impressions, 4) if impressions else 0.0,
        })
    return {"items": out, "count": len(out)}


@router.post("/portal/banner/{cid}/toggle")
async def portal_banner_toggle(cid: str, request: Request,
                               user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.banner_ad_campaigns.find_one({"_id": cid})
    if not c:
        raise HTTPException(404, {"code": "not_found"})
    await _owned_business_or_403(db, c.get("business_id"), user)
    new = "paused" if c.get("status") == "active" else "active"
    patch = {"status": new}
    if new == "active" and not c.get("approved_at"):
        patch["approved_at"] = _now_iso()
        patch["approved_by"] = "self_serve_auto"
    await db.banner_ad_campaigns.update_one({"_id": cid}, {"$set": patch})
    return {"ok": True, "status": new}
