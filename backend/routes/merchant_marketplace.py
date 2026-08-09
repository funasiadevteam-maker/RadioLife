"""Phase MKT.1 — Merchant Marketplace ("Get More Customers" goal-first flow).

Platform-agnostic contract (mobile merchant screens + web admin share it).

A merchant picks a GOAL (e.g. "Get More Customers"), the marketplace recommends
campaign types, and the merchant launches one of:
  * coupon_bid  — bids for a Featured Coupon slot; pays a CPA per consumer claim.
  * trivia      — a branded trivia round; pays per correct answer, rewards listeners.

Admin owns a tunable Rate Card (CPM/CPA/CPL per ad inventory type) that seeds
the pricing hints shown during campaign creation.

Collections: rate_card (single doc _id='rate_card'), merchant_campaigns,
brand_trivia_answers, brand_coupon_claims.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional, require_admin
from services.points_service import PointsService

router = APIRouter(tags=["merchant-marketplace"])
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────── Rate Card ───────────────────────────
RATE_CARD_DEFAULTS: List[Dict[str, Any]] = [
    {"key": "display_banner", "label": "Display Banner", "pricing_model": "CPM",
     "base_cents": 800, "min_cents": 300, "max_cents": 3000,
     "multipliers": {"premium_placement": 1.5, "peak_hours": 1.3}, "enabled": True},
    {"key": "audio_preroll", "label": "Audio Pre-Roll", "pricing_model": "CPM",
     "base_cents": 1500, "min_cents": 800, "max_cents": 5000,
     "multipliers": {"flagship_station": 1.4}, "enabled": True},
    {"key": "sponsored_rj", "label": "Sponsored AI RJ Read", "pricing_model": "CPM",
     "base_cents": 2500, "min_cents": 1500, "max_cents": 8000,
     "multipliers": {"drive_time": 1.5}, "enabled": True},
    {"key": "push_notification", "label": "Push Notification", "pricing_model": "CPA",
     "base_cents": 10, "min_cents": 5, "max_cents": 100,
     "multipliers": {"geo_targeted": 1.4}, "enabled": True},
    {"key": "coupon_featured", "label": "Featured Coupon", "pricing_model": "CPA",
     "base_cents": 25, "min_cents": 10, "max_cents": 300,
     "multipliers": {"category_exclusive": 1.6}, "enabled": True},
    {"key": "trivia_sponsored", "label": "Sponsored Trivia", "pricing_model": "CPA",
     "base_cents": 8, "min_cents": 3, "max_cents": 50,
     "multipliers": {"exclusive_round": 1.5}, "enabled": True},
    {"key": "video_ad", "label": "Video Ad", "pricing_model": "CPM",
     "base_cents": 2000, "min_cents": 1000, "max_cents": 6000,
     "multipliers": {"skippable": 0.7, "non_skippable": 1.3}, "enabled": True},
    {"key": "instant_win_game", "label": "Instant-Win Game", "pricing_model": "CPA",
     "base_cents": 12, "min_cents": 5, "max_cents": 100,
     "multipliers": {"high_value_prize": 1.5}, "enabled": True},
    {"key": "giveaway_entry", "label": "Giveaway Entry", "pricing_model": "CPL",
     "base_cents": 3, "min_cents": 1, "max_cents": 50,
     "multipliers": {}, "enabled": True},
    {"key": "featured_listing", "label": "Featured Listing", "pricing_model": "CPA",
     "base_cents": 20, "min_cents": 5, "max_cents": 500,
     "multipliers": {"category_exclusive": 1.6}, "enabled": True},
]


async def _rate_card(db) -> Dict[str, Any]:
    doc = await db.rate_card.find_one({"_id": "rate_card"})
    if not doc:
        doc = {"_id": "rate_card", "items": RATE_CARD_DEFAULTS, "updated_at": _now()}
        await db.rate_card.insert_one(dict(doc))
    else:
        # Backfill any newly-added default keys so admins can tune them.
        have = {it.get("key") for it in doc.get("items", [])}
        missing = [d for d in RATE_CARD_DEFAULTS if d["key"] not in have]
        if missing:
            doc["items"] = doc.get("items", []) + missing
            await db.rate_card.update_one(
                {"_id": "rate_card"}, {"$set": {"items": doc["items"]}})
    doc.pop("_id", None)
    return doc


async def _rate_for(db, key: str) -> Dict[str, Any]:
    rc = await _rate_card(db)
    for it in rc.get("items", []):
        if it.get("key") == key:
            return it
    return {}


async def seed_marketplace(db) -> Dict[str, Any]:
    """Idempotent boot bootstrap: rate card + a demo-owned venue."""
    await _rate_card(db)  # seeds rate card if missing
    # Indexes (idempotent).
    try:
        await db.merchant_campaigns.create_index("campaign_id", unique=True)
        await db.merchant_campaigns.create_index("owner_user_id")
        await db.brand_trivia_answers.create_index(
            [("user_id", 1), ("campaign_id", 1), ("question_index", 1)], unique=True)
        await db.brand_coupon_claims.create_index(
            [("user_id", 1), ("campaign_id", 1)], unique=True)
        await db.brand_game_plays.create_index(
            [("user_id", 1), ("campaign_id", 1)], unique=True)
        await db.brand_giveaway_entries.create_index(
            [("user_id", 1), ("campaign_id", 1)], unique=True)
        await db.featured_clicks.create_index(
            [("user_id", 1), ("campaign_id", 1), ("day", 1)], unique=True)
    except Exception:
        pass
    # Demo venue so the demo account sees the merchant flows populated.
    created_demo = False
    demo = await db.users.find_one({"email": "demo@bigfm.dubai"}, {"user_id": 1})
    if demo:
        biz_id = "biz_demo_marketplace"
        exists = await db.businesses.find_one({"business_id": biz_id}, {"_id": 1})
        await db.businesses.update_one(
            {"business_id": biz_id},
            {"$set": {"business_id": biz_id, "owner_user_id": demo["user_id"],
                      "name": "The Grind Coffee (Demo)", "category": "cafe",
                      "city": demo.get("market") or "Dallas", "active": True,
                      "verified": True, "updated_at": _now()},
             "$setOnInsert": {"created_at": _now()}},
            upsert=True)
        created_demo = not exists
    return {"rate_card": "ok", "demo_venue_created": created_demo}


@router.get("/api/admin/rate-card")
async def get_rate_card(request: Request, _admin=Depends(require_admin)):
    return await _rate_card(request.app.state.db)


class RateCardItem(BaseModel):
    key: str
    label: str
    pricing_model: str = Field(..., description="CPM | CPA | CPL")
    base_cents: int = Field(..., ge=0, le=1_000_000)
    min_cents: int = Field(0, ge=0, le=1_000_000)
    max_cents: int = Field(1_000_000, ge=0, le=1_000_000)
    multipliers: Dict[str, float] = {}
    enabled: bool = True


class RateCardBody(BaseModel):
    items: List[RateCardItem]


@router.put("/api/admin/rate-card")
async def put_rate_card(body: RateCardBody, request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    items = [i.model_dump() for i in body.items]
    for it in items:
        if it["pricing_model"] not in ("CPM", "CPA", "CPL"):
            raise HTTPException(400, {"code": "bad_pricing_model", "key": it["key"]})
        if it["min_cents"] > it["max_cents"]:
            raise HTTPException(400, {"code": "min_gt_max", "key": it["key"]})
    await db.rate_card.update_one(
        {"_id": "rate_card"},
        {"$set": {"items": items, "updated_at": _now()}}, upsert=True)
    return {"ok": True, "items": items}


# ─────────────────────── Goal-first catalog ───────────────────────
GOALS: List[Dict[str, Any]] = [
    {"key": "more_customers", "title": "Get More Customers",
     "subtitle": "Attract new listeners to your venue", "icon": "people",
     "recommended": ["coupon_bid", "featured", "spin", "trivia"]},
    {"key": "foot_traffic", "title": "Drive Foot Traffic",
     "subtitle": "Fill quiet hours with a compelling offer", "icon": "walk",
     "recommended": ["coupon_bid", "featured", "scratch"]},
    {"key": "engagement", "title": "Boost Engagement",
     "subtitle": "Get listeners playing with your brand", "icon": "game-controller",
     "recommended": ["trivia", "spin", "scratch"]},
    {"key": "awareness", "title": "Grow Brand Awareness",
     "subtitle": "Put your name in front of the audience", "icon": "megaphone",
     "recommended": ["giveaway", "trivia", "coupon_bid"]},
]

CAMPAIGN_TYPES: Dict[str, Dict[str, Any]] = {
    "coupon_bid": {
        "type": "coupon_bid", "label": "Featured Coupon (Bid)",
        "desc": "Bid for the top coupon slot. You pay only when a listener claims it.",
        "icon": "pricetag", "rate_key": "coupon_featured"},
    "trivia": {
        "type": "trivia", "label": "Branded Trivia",
        "desc": "Run a trivia round. You pay per correct answer; listeners earn points.",
        "icon": "help-circle", "rate_key": "trivia_sponsored"},
    "spin": {
        "type": "spin", "label": "Spin the Wheel",
        "desc": "An instant-win spin. Listeners try their luck to win points.",
        "icon": "sync-circle", "rate_key": "instant_win_game"},
    "scratch": {
        "type": "scratch", "label": "Scratch Card",
        "desc": "A scratch-to-reveal instant win. Great for driving quick visits.",
        "icon": "sparkles", "rate_key": "instant_win_game"},
    "giveaway": {
        "type": "giveaway", "label": "Prize Giveaway",
        "desc": "Listeners enter to win a prize. You draw the winners.",
        "icon": "gift", "rate_key": "giveaway_entry"},
    "featured": {
        "type": "featured", "label": "Featured Listing",
        "desc": "Pin your venue to the top of local discovery. Pay per tap.",
        "icon": "star", "rate_key": "featured_listing"},
}

# Ad formats (advertiser Campaign Format Selector) → rate card keys.
AD_FORMATS = [
    {"format": "banner", "label": "Display Banner", "icon": "image", "rate_key": "display_banner"},
    {"format": "audio", "label": "Audio Pre-Roll", "icon": "mic", "rate_key": "audio_preroll"},
    {"format": "push", "label": "Push Notification", "icon": "notifications", "rate_key": "push_notification"},
    {"format": "video", "label": "Video Ad", "icon": "videocam", "rate_key": "video_ad"},
]


@router.get("/api/rate-card/formats")
async def rate_card_formats(request: Request, user: dict = Depends(current_user)):
    """Advertiser-facing: ad formats + their current rate-card pricing."""
    db = request.app.state.db
    out = []
    for f in AD_FORMATS:
        r = await _rate_for(db, f["rate_key"])
        if r and not r.get("enabled", True):
            continue
        out.append({**f, "pricing_model": r.get("pricing_model"),
                    "base_cents": r.get("base_cents"),
                    "min_cents": r.get("min_cents"), "max_cents": r.get("max_cents")})
    return {"items": out}


@router.get("/api/merchant/marketplace/goals")
async def marketplace_goals(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    hints = {}
    for ct in CAMPAIGN_TYPES.values():
        r = await _rate_for(db, ct["rate_key"])
        hints[ct["type"]] = {"pricing_model": r.get("pricing_model"),
                             "base_cents": r.get("base_cents"),
                             "min_cents": r.get("min_cents"),
                             "max_cents": r.get("max_cents")}
    return {"goals": GOALS, "campaign_types": CAMPAIGN_TYPES, "rate_card_hints": hints}


# ───────────────────── Merchant campaign CRUD ─────────────────────
class TriviaQuestion(BaseModel):
    q: str
    choices: List[str] = Field(..., min_length=2, max_length=4)
    answer_index: int = Field(..., ge=0, le=3)


class CampaignBody(BaseModel):
    merchant_id: str
    type: str = Field(..., description="coupon_bid | trivia | spin | scratch | giveaway")
    goal: str
    title: str
    budget_usd: float = Field(..., gt=0, le=100_000)
    market: Optional[str] = None
    # coupon_bid
    bid_cents: int = Field(0, ge=0, le=100_000)
    coupon_title: Optional[str] = None
    coupon_value_cents: int = Field(0, ge=0)
    reward_points_on_claim: int = Field(5, ge=0, le=10_000)
    # trivia
    reward_points: int = Field(10, ge=0, le=10_000)
    questions: List[TriviaQuestion] = []
    # spin / scratch (instant-win)
    win_points: int = Field(20, ge=0, le=100_000)
    win_probability: float = Field(0.3, gt=0, le=1.0)
    prize_label: Optional[str] = None
    # giveaway
    prize_desc: Optional[str] = None
    num_winners: int = Field(1, ge=1, le=1000)
    # featured listing
    tagline: Optional[str] = None
    hero_image_url: Optional[str] = None


@router.post("/api/merchant/marketplace/campaigns")
async def create_campaign(body: CampaignBody, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    from routes.ad4_coupon_campaigns import _assert_merchant_owner
    await _assert_merchant_owner(db, body.merchant_id, user)
    if body.type not in CAMPAIGN_TYPES:
        raise HTTPException(400, {"code": "bad_campaign_type"})
    if body.type == "coupon_bid" and body.bid_cents <= 0:
        raise HTTPException(400, {"code": "bid_required"})
    if body.type == "featured" and body.bid_cents <= 0:
        raise HTTPException(400, {"code": "bid_required"})
    if body.type == "trivia" and not body.questions:
        raise HTTPException(400, {"code": "questions_required"})
    if body.type == "giveaway" and not body.prize_desc:
        raise HTTPException(400, {"code": "prize_required"})
    biz = await db.businesses.find_one(
        {"$or": [{"business_id": body.merchant_id}, {"_id": body.merchant_id}]},
        {"name": 1})
    doc: Dict[str, Any] = {
        "campaign_id": f"mc_{uuid.uuid4().hex[:12]}",
        "merchant_id": body.merchant_id, "owner_user_id": user.get("user_id"),
        "sponsor_name": (biz or {}).get("name"),
        "type": body.type, "goal": body.goal, "title": body.title,
        "budget_usd": float(body.budget_usd), "spent_usd": 0.0,
        "market": body.market, "status": "active",
        "created_at": _now(), "updated_at": _now(),
    }
    if body.type == "coupon_bid":
        doc.update({"bid_cents": body.bid_cents, "coupon_title": body.coupon_title or body.title,
                    "coupon_value_cents": body.coupon_value_cents,
                    "reward_points_on_claim": body.reward_points_on_claim,
                    "claims": 0})
    elif body.type == "trivia":
        doc.update({"reward_points": body.reward_points,
                    "questions": [q.model_dump() for q in body.questions],
                    "answers_count": 0, "correct_count": 0})
    elif body.type in ("spin", "scratch"):
        doc.update({"win_points": body.win_points, "win_probability": body.win_probability,
                    "prize_label": body.prize_label or f"{body.win_points} points",
                    "plays": 0, "wins": 0})
    elif body.type == "featured":
        doc.update({"bid_cents": body.bid_cents, "tagline": body.tagline,
                    "hero_image_url": body.hero_image_url,
                    "impressions": 0, "clicks": 0})
    else:  # giveaway
        doc.update({"prize_desc": body.prize_desc, "num_winners": body.num_winners,
                    "entries_count": 0, "reward_points_on_entry": body.reward_points_on_claim,
                    "drawn": False, "winners": []})
    await db.merchant_campaigns.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/api/merchant/marketplace/campaigns")
async def list_campaigns(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    async for c in db.merchant_campaigns.find(
            {"owner_user_id": user.get("user_id")}).sort("created_at", -1):
        c.pop("_id", None)
        out.append(c)
    return {"items": out, "total": len(out)}


async def _owned_campaign(db, campaign_id: str, user: dict) -> Dict[str, Any]:
    c = await db.merchant_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if user.get("role") != "admin" and c.get("owner_user_id") != user.get("user_id"):
        raise HTTPException(403, {"code": "not_owner"})
    return c


@router.post("/api/merchant/marketplace/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _owned_campaign(db, campaign_id, user)
    await db.merchant_campaigns.update_one(
        {"campaign_id": campaign_id}, {"$set": {"status": "paused", "updated_at": _now()}})
    return {"ok": True, "status": "paused"}


@router.post("/api/merchant/marketplace/campaigns/{campaign_id}/activate")
async def activate_campaign(campaign_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await _owned_campaign(db, campaign_id, user)
    if c.get("spent_usd", 0) >= c.get("budget_usd", 0):
        raise HTTPException(400, {"code": "budget_exhausted"})
    await db.merchant_campaigns.update_one(
        {"campaign_id": campaign_id}, {"$set": {"status": "active", "updated_at": _now()}})
    return {"ok": True, "status": "active"}


def _live_q(campaign_id: str, base: Dict[str, Any]) -> Dict[str, Any]:
    return base


# ─────────────────────── Consumer: Brand Trivia ───────────────────────
@router.get("/api/brand-trivia/active")
async def brand_trivia_active(request: Request, market: Optional[str] = None,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    q: Dict[str, Any] = {"type": "trivia", "status": "active"}
    out = []
    async for c in db.merchant_campaigns.find(q).sort("created_at", -1):
        if c.get("spent_usd", 0) >= c.get("budget_usd", 0):
            continue
        answered = set()
        async for a in db.brand_trivia_answers.find(
                {"user_id": uid, "campaign_id": c["campaign_id"]}, {"question_index": 1}):
            answered.add(a["question_index"])
        qs = []
        for i, question in enumerate(c.get("questions", [])):
            qs.append({"index": i, "q": question["q"], "choices": question["choices"],
                       "answered": i in answered})
        out.append({"campaign_id": c["campaign_id"], "sponsor_name": c.get("sponsor_name"),
                    "title": c.get("title"), "reward_points": c.get("reward_points", 0),
                    "questions": qs})
    return {"items": out, "total": len(out)}


class TriviaAnswerBody(BaseModel):
    question_index: int = Field(..., ge=0)
    choice_index: int = Field(..., ge=0)


@router.post("/api/brand-trivia/{campaign_id}/answer")
async def brand_trivia_answer(campaign_id: str, body: TriviaAnswerBody, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    c = await db.merchant_campaigns.find_one({"campaign_id": campaign_id, "type": "trivia"})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("status") != "active" or c.get("spent_usd", 0) >= c.get("budget_usd", 0):
        raise HTTPException(400, {"code": "campaign_inactive"})
    questions = c.get("questions", [])
    if body.question_index >= len(questions):
        raise HTTPException(400, {"code": "bad_question"})
    # Idempotency — one answer per user per question.
    try:
        await db.brand_trivia_answers.insert_one({
            "user_id": uid, "campaign_id": campaign_id,
            "question_index": body.question_index, "created_at": _now()})
    except Exception:
        raise HTTPException(409, {"code": "already_answered"})
    correct = body.choice_index == questions[body.question_index]["answer_index"]
    awarded, balance_after = 0, None
    if correct:
        reward = int(c.get("reward_points", 0))
        rate = await _rate_for(db, "trivia_sponsored")
        cost_usd = int(rate.get("base_cents", 8)) / 100.0
        res = await PointsService(db).award(
            user_id=uid, source="brand_trivia", source_id=campaign_id, delta=reward,
            metadata={"campaign_id": campaign_id, "question_index": body.question_index},
            idempotency_key=f"brandtrivia:{campaign_id}:{body.question_index}:{uid}",
            enforce_caps=False)
        awarded, balance_after = reward, res.balance_after
        new_spent = round(c.get("spent_usd", 0.0) + cost_usd, 4)
        upd = {"$inc": {"correct_count": 1, "answers_count": 1}, "$set": {"spent_usd": new_spent}}
        if new_spent >= c.get("budget_usd", 0):
            upd["$set"]["status"] = "paused"
        await db.merchant_campaigns.update_one({"campaign_id": campaign_id}, upd)
    else:
        await db.merchant_campaigns.update_one(
            {"campaign_id": campaign_id}, {"$inc": {"answers_count": 1}})
    return {"correct": correct, "awarded": awarded, "balance_after": balance_after,
            "answer_index": questions[body.question_index]["answer_index"]}


# ─────────────────────── Consumer: Featured Coupons (bidding) ───────────────────────
@router.get("/api/brand-coupons/featured")
async def featured_coupons(request: Request, market: Optional[str] = None,
                           user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    uid = (user or {}).get("user_id")
    claimed = set()
    if uid:
        async for cl in db.brand_coupon_claims.find({"user_id": uid}, {"campaign_id": 1}):
            claimed.add(cl["campaign_id"])
    out = []
    async for c in db.merchant_campaigns.find(
            {"type": "coupon_bid", "status": "active"}).sort("bid_cents", -1):
        if c.get("spent_usd", 0) >= c.get("budget_usd", 0):
            continue
        out.append({"campaign_id": c["campaign_id"], "sponsor_name": c.get("sponsor_name"),
                    "coupon_title": c.get("coupon_title") or c.get("title"),
                    "coupon_value_cents": c.get("coupon_value_cents", 0),
                    "reward_points_on_claim": c.get("reward_points_on_claim", 0),
                    "bid_cents": c.get("bid_cents", 0),
                    "claimed": c["campaign_id"] in claimed})
    return {"items": out, "total": len(out)}


@router.post("/api/brand-coupons/{campaign_id}/claim")
async def claim_featured_coupon(campaign_id: str, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    c = await db.merchant_campaigns.find_one({"campaign_id": campaign_id, "type": "coupon_bid"})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("status") != "active" or c.get("spent_usd", 0) >= c.get("budget_usd", 0):
        raise HTTPException(400, {"code": "campaign_inactive"})
    try:
        await db.brand_coupon_claims.insert_one({
            "user_id": uid, "campaign_id": campaign_id, "created_at": _now()})
    except Exception:
        raise HTTPException(409, {"code": "already_claimed"})
    # Charge the merchant's bid; award the listener a small point bonus.
    cost_usd = int(c.get("bid_cents", 0)) / 100.0
    reward = int(c.get("reward_points_on_claim", 0))
    balance_after = None
    if reward > 0:
        res = await PointsService(db).award(
            user_id=uid, source="brand_coupon_claim", source_id=campaign_id, delta=reward,
            metadata={"campaign_id": campaign_id},
            idempotency_key=f"brandcoupon:{campaign_id}:{uid}", enforce_caps=False)
        balance_after = res.balance_after
    new_spent = round(c.get("spent_usd", 0.0) + cost_usd, 4)
    upd = {"$inc": {"claims": 1}, "$set": {"spent_usd": new_spent}}
    if new_spent >= c.get("budget_usd", 0):
        upd["$set"]["status"] = "paused"
    await db.merchant_campaigns.update_one({"campaign_id": campaign_id}, upd)
    return {"ok": True, "awarded": reward, "balance_after": balance_after,
            "coupon_title": c.get("coupon_title") or c.get("title")}


# ─────────────────────── Consumer: Instant-Win Games (spin/scratch) ───────────────────────
@router.get("/api/brand-games/active")
async def brand_games_active(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    played = {}
    async for p in db.brand_game_plays.find({"user_id": uid}):
        played[p["campaign_id"]] = {"won": p.get("won", False), "awarded": p.get("awarded", 0)}
    out = []
    async for c in db.merchant_campaigns.find(
            {"type": {"$in": ["spin", "scratch"]}, "status": "active"}).sort("created_at", -1):
        if c.get("spent_usd", 0) >= c.get("budget_usd", 0):
            continue
        out.append({"campaign_id": c["campaign_id"], "type": c["type"],
                    "sponsor_name": c.get("sponsor_name"), "title": c.get("title"),
                    "prize_label": c.get("prize_label"), "win_points": c.get("win_points", 0),
                    "played": played.get(c["campaign_id"])})
    return {"items": out, "total": len(out)}


@router.post("/api/brand-games/{campaign_id}/play")
async def brand_game_play(campaign_id: str, request: Request, user: dict = Depends(current_user)):
    import random
    db = request.app.state.db
    uid = user.get("user_id")
    c = await db.merchant_campaigns.find_one(
        {"campaign_id": campaign_id, "type": {"$in": ["spin", "scratch"]}})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("status") != "active" or c.get("spent_usd", 0) >= c.get("budget_usd", 0):
        raise HTTPException(400, {"code": "campaign_inactive"})
    won = random.random() < float(c.get("win_probability", 0.3))
    try:
        await db.brand_game_plays.insert_one({
            "user_id": uid, "campaign_id": campaign_id, "won": won,
            "awarded": 0, "created_at": _now()})
    except Exception:
        raise HTTPException(409, {"code": "already_played"})
    awarded, balance_after = 0, None
    if won:
        awarded = int(c.get("win_points", 0))
        res = await PointsService(db).award(
            user_id=uid, source="brand_game_win", source_id=campaign_id, delta=awarded,
            metadata={"campaign_id": campaign_id, "game": c["type"]},
            idempotency_key=f"brandgame:{campaign_id}:{uid}", enforce_caps=False)
        balance_after = res.balance_after
        await db.brand_game_plays.update_one(
            {"user_id": uid, "campaign_id": campaign_id}, {"$set": {"awarded": awarded}})
    rate = await _rate_for(db, "instant_win_game")
    cost_usd = int(rate.get("base_cents", 12)) / 100.0
    new_spent = round(c.get("spent_usd", 0.0) + cost_usd, 4)
    upd = {"$inc": {"plays": 1, "wins": 1 if won else 0}, "$set": {"spent_usd": new_spent}}
    if new_spent >= c.get("budget_usd", 0):
        upd["$set"]["status"] = "paused"
    await db.merchant_campaigns.update_one({"campaign_id": campaign_id}, upd)
    return {"won": won, "awarded": awarded, "balance_after": balance_after,
            "prize_label": c.get("prize_label")}


# ─────────────────────── Consumer: Giveaways ───────────────────────
@router.get("/api/brand-giveaways/active")
async def brand_giveaways_active(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    entered = set()
    async for e in db.brand_giveaway_entries.find({"user_id": uid}, {"campaign_id": 1}):
        entered.add(e["campaign_id"])
    out = []
    async for c in db.merchant_campaigns.find(
            {"type": "giveaway", "status": "active", "drawn": {"$ne": True}}).sort("created_at", -1):
        out.append({"campaign_id": c["campaign_id"], "sponsor_name": c.get("sponsor_name"),
                    "title": c.get("title"), "prize_desc": c.get("prize_desc"),
                    "num_winners": c.get("num_winners", 1),
                    "entries_count": c.get("entries_count", 0),
                    "entered": c["campaign_id"] in entered})
    return {"items": out, "total": len(out)}


@router.post("/api/brand-giveaways/{campaign_id}/enter")
async def brand_giveaway_enter(campaign_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    c = await db.merchant_campaigns.find_one({"campaign_id": campaign_id, "type": "giveaway"})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("status") != "active" or c.get("drawn"):
        raise HTTPException(400, {"code": "campaign_inactive"})
    try:
        await db.brand_giveaway_entries.insert_one({
            "user_id": uid, "campaign_id": campaign_id, "created_at": _now()})
    except Exception:
        raise HTTPException(409, {"code": "already_entered"})
    reward = int(c.get("reward_points_on_entry", 0))
    balance_after = None
    if reward > 0:
        res = await PointsService(db).award(
            user_id=uid, source="brand_giveaway_entry", source_id=campaign_id, delta=reward,
            metadata={"campaign_id": campaign_id},
            idempotency_key=f"brandgiveaway:{campaign_id}:{uid}", enforce_caps=False)
        balance_after = res.balance_after
    rate = await _rate_for(db, "giveaway_entry")
    cost_usd = int(rate.get("base_cents", 3)) / 100.0
    new_spent = round(c.get("spent_usd", 0.0) + cost_usd, 4)
    upd = {"$inc": {"entries_count": 1}, "$set": {"spent_usd": new_spent}}
    if new_spent >= c.get("budget_usd", 0):
        upd["$set"]["status"] = "paused"
    await db.merchant_campaigns.update_one({"campaign_id": campaign_id}, upd)
    return {"ok": True, "awarded": reward, "balance_after": balance_after}


@router.post("/api/merchant/marketplace/campaigns/{campaign_id}/draw")
async def draw_giveaway(campaign_id: str, request: Request, user: dict = Depends(current_user)):
    import random
    db = request.app.state.db
    c = await _owned_campaign(db, campaign_id, user)
    if c.get("type") != "giveaway":
        raise HTTPException(400, {"code": "not_a_giveaway"})
    if c.get("drawn"):
        raise HTTPException(400, {"code": "already_drawn"})
    entrants = [e["user_id"] async for e in
                db.brand_giveaway_entries.find({"campaign_id": campaign_id}, {"user_id": 1})]
    n = min(int(c.get("num_winners", 1)), len(entrants))
    winners = random.sample(entrants, n) if n > 0 else []
    await db.merchant_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"drawn": True, "winners": winners, "status": "paused", "updated_at": _now()}})
    # Winner Notifications — drop an in-app notification into each winner's inbox.
    try:
        from routes.notifications import _enqueue
        for uid in winners:
            await _enqueue(
                db, owner_user_id=uid, station_id="marketplace",
                station_slug="marketplace", type_="giveaway_winner",
                payload={"campaign_id": campaign_id, "title": c.get("title"),
                         "sponsor_name": c.get("sponsor_name"),
                         "prize_desc": c.get("prize_desc")},
                dedupe_key=f"giveaway_win:{campaign_id}:{uid}")
    except Exception as _e:
        logger.warning("giveaway winner notif enqueue failed for %s: %s", campaign_id, _e)
    return {"ok": True, "winners": winners, "total_entries": len(entrants)}


# ─────────────────────── Consumer: Featured Listings (local discovery) ───────────────────────
@router.get("/api/discovery/featured")
async def discovery_featured(request: Request, market: Optional[str] = None,
                             limit: int = 10, user: dict = Depends(current_user_optional)):
    db = request.app.state.db
    q: Dict[str, Any] = {"type": "featured", "status": "active"}
    if market:
        q["market"] = market
    out = []
    async for c in db.merchant_campaigns.find(q).sort("bid_cents", -1).limit(max(1, min(limit, 50))):
        if c.get("spent_usd", 0) >= c.get("budget_usd", 0):
            continue
        out.append({"campaign_id": c["campaign_id"], "sponsor_name": c.get("sponsor_name"),
                    "title": c.get("title"), "tagline": c.get("tagline"),
                    "hero_image_url": c.get("hero_image_url"),
                    "merchant_id": c.get("merchant_id"), "featured": True})
    # Fire-and-forget impression accounting.
    for item in out:
        await db.merchant_campaigns.update_one(
            {"campaign_id": item["campaign_id"]}, {"$inc": {"impressions": 1}})
    return {"items": out, "total": len(out)}


@router.post("/api/discovery/featured/{campaign_id}/click")
async def discovery_featured_click(campaign_id: str, request: Request,
                                   user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.merchant_campaigns.find_one({"campaign_id": campaign_id, "type": "featured"})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("status") != "active":
        return {"ok": True, "merchant_id": c.get("merchant_id"), "charged": False}
    # Anti-fraud: bill at most once per user per campaign per day.
    day = _now().strftime("%Y-%m-%d")
    try:
        await db.featured_clicks.insert_one({
            "user_id": user.get("user_id"), "campaign_id": campaign_id,
            "day": day, "created_at": _now()})
        billable = True
    except Exception:
        billable = False
    if not billable:
        return {"ok": True, "merchant_id": c.get("merchant_id"), "charged": False}
    cost_usd = int(c.get("bid_cents", 0)) / 100.0
    new_spent = round(c.get("spent_usd", 0.0) + cost_usd, 4)
    upd = {"$inc": {"clicks": 1}, "$set": {"spent_usd": new_spent}}
    if new_spent >= c.get("budget_usd", 0):
        upd["$set"]["status"] = "paused"
    await db.merchant_campaigns.update_one({"campaign_id": campaign_id}, upd)
    return {"ok": True, "merchant_id": c.get("merchant_id"), "charged": True}


__all__ = ["router", "seed_marketplace"]