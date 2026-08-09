"""Phase 2/3 — AI Reward Engine, Coupon-Fraud Tracking, Merchant Redeem +
Loyalty, and Admin-configurable Game Frequency Limits.

Self-contained module that layers new monetisation behaviours on top of the
existing wallet/merchant primitives without disturbing them.

Admin provisioning:
  GET/PUT /api/rewards/config          — reward engine + merchant loyalty tiers
  GET/PUT /api/games/limits            — per-game play frequency caps

Listener:
  POST /api/rewards/scan-earn          — AI-scaled points per $ + threshold bonuses
  POST /api/coupon-events/show         — log a coupon/scan-to-pay "show" (fraud signal)
  GET  /api/games/play-eligibility/{k} — can this user play game k now?
  POST /api/games/record-play          — enforce + log a play

Merchant:
  POST /api/merchant/redeem            — redeem a shown coupon, reconciles fraud log
  GET  /api/merchant/loyalty           — today's redemptions → loyalty tier + rate

Admin:
  GET  /api/admin/coupon-fraud         — per-merchant show-vs-redeem gap + flags
"""
from __future__ import annotations

import os
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import current_user, require_admin
from services import bigcoin as _bigcoin

router = APIRouter(tags=["rewards-merchant"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

DEFAULT_CONFIG: Dict[str, Any] = {
    "_id": "config",
    "base_points_per_dollar": 1.0,
    "engagement_window_days": 30,
    "min_multiplier": 1.0,
    "max_multiplier": 3.0,
    "use_ai": True,
    # lifetime-points thresholds → one-off bonuses / unlocks
    "thresholds": [
        {"points": 500, "bonus_points": 50, "unlock_bonus_games": True, "concert_pass": False},
        {"points": 2000, "bonus_points": 200, "unlock_bonus_games": True, "concert_pass": True},
    ],
    # merchant loyalty: higher daily redemptions → better rate (their cut %)
    "merchant_tiers": [
        {"min_daily": 0, "rate": 0.10, "name": "Standard"},
        {"min_daily": 10, "rate": 0.12, "name": "Silver"},
        {"min_daily": 25, "rate": 0.15, "name": "Gold"},
    ],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


async def _get_config(db) -> Dict[str, Any]:
    cfg = await db.reward_engine_config.find_one({"_id": "config"})
    if not cfg:
        await db.reward_engine_config.insert_one(dict(DEFAULT_CONFIG))
        cfg = dict(DEFAULT_CONFIG)
    return cfg


# ─────────────────────────── AI reward engine ───────────────────────────

async def _ai_multiplier(stats: Dict[str, Any], lo: float, hi: float) -> Dict[str, Any]:
    """Ask the LLM for a bounded points-per-dollar multiplier + reason.
    Falls back to a deterministic engagement curve on any failure."""
    scans = int(stats.get("scans_in_window", 0))
    # deterministic fallback curve
    fb = min(hi, round(lo + min(scans, 20) * (hi - lo) / 20.0, 2))
    if not EMERGENT_LLM_KEY:
        return {"multiplier": fb, "reason": "Engagement-based reward", "ai": False}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"reward-{stats.get('user_id','x')}",
            system_message=(
                "You are a loyalty reward engine. Given a listener's engagement, "
                "return ONLY compact JSON: {\"multiplier\": <float>, \"reason\": <short string>}. "
                f"multiplier MUST be between {lo} and {hi}. Reward frequent engagement "
                "with a higher multiplier."),
        ).with_model("openai", "gpt-5.4")
        msg = UserMessage(text=json.dumps({
            "scans_last_30d": scans,
            "current_tier": stats.get("tier"),
            "lifetime_points": stats.get("lifetime_points", 0),
        }))
        raw = await chat.send_message(msg)
        txt = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
        s = txt[txt.find("{"): txt.rfind("}") + 1]
        data = json.loads(s)
        mult = float(data.get("multiplier", fb))
        mult = max(lo, min(hi, round(mult, 2)))
        return {"multiplier": mult, "reason": str(data.get("reason", "Personalized reward"))[:120], "ai": True}
    except Exception:
        return {"multiplier": fb, "reason": "Engagement-based reward", "ai": False}


class ScanEarnBody(BaseModel):
    amount_usd: float
    merchant_id: Optional[str] = None
    coupon_id: Optional[str] = None


@router.post("/api/rewards/scan-earn")
async def scan_earn(body: ScanEarnBody, request: Request, user: dict = Depends(current_user)):
    if body.amount_usd <= 0:
        raise HTTPException(400, "amount_usd must be positive")
    db = request.app.state.db
    uid = user.get("user_id")
    cfg = await _get_config(db)
    window = int(cfg.get("engagement_window_days", 30))
    since = _now() - timedelta(days=window)

    scans = await db.scan_earn_events.count_documents({"user_id": uid, "at": {"$gte": since}})
    lifetime = int(user.get("bigcoin_lifetime", 0) or user.get("bigcoin_balance", 0) or 0)
    tier_name = "Bronze" if scans < 5 else "Silver" if scans < 15 else "Gold"

    ai = await _ai_multiplier(
        {"user_id": uid, "scans_in_window": scans, "tier": tier_name, "lifetime_points": lifetime},
        float(cfg.get("min_multiplier", 1.0)), float(cfg.get("max_multiplier", 3.0)))

    base = float(cfg.get("base_points_per_dollar", 1.0))
    points = max(1, round(body.amount_usd * base * ai["multiplier"]))

    # Phase RWD.4 — apply any active Sponsored Bonus window for this venue.
    from routes.merchant_ops import active_bonus_multiplier, maybe_alert
    bonus_mult = await active_bonus_multiplier(db, body.merchant_id)
    if bonus_mult > 1:
        points = max(points, round(points * bonus_mult))

    res = await _bigcoin.award(db, uid, points, source="scan_earn",
        metadata={"amount_usd": body.amount_usd, "merchant_id": body.merchant_id,
                  "multiplier": ai["multiplier"], "bonus_multiplier": bonus_mult})
    balance_after = res.get("balance_after")
    new_lifetime = lifetime + points

    # log the scan-earn (engagement + fraud show event)
    await db.scan_earn_events.insert_one({
        "user_id": uid, "merchant_id": body.merchant_id, "amount_usd": body.amount_usd,
        "points": points, "multiplier": ai["multiplier"], "at": _now()})
    ev_id = None
    if body.merchant_id:
        ev_id = f"cev_{uuid.uuid4().hex[:12]}"
        await db.coupon_show_events.insert_one({
            "event_id": ev_id, "user_id": uid, "merchant_id": body.merchant_id,
            "coupon_id": body.coupon_id, "kind": "scan_to_pay",
            "shown_at": _now(), "redeemed": False, "redeemed_at": None})
        await maybe_alert(db, body.merchant_id)

    # threshold bonuses (idempotent per threshold via user.rewards_thresholds_hit)
    hit = set(user.get("rewards_thresholds_hit", []) or [])
    bonuses = {"bonus_points": 0, "bonus_games_unlocked": False, "concert_pass": False}
    for t in sorted(cfg.get("thresholds", []), key=lambda x: x["points"]):
        tp = int(t["points"])
        if new_lifetime >= tp and tp not in hit:
            hit.add(tp)
            bp = int(t.get("bonus_points", 0))
            if bp:
                await _bigcoin.award(db, uid, bp, source="reward_threshold_bonus",
                                     metadata={"threshold": tp})
                bonuses["bonus_points"] += bp
                new_lifetime += bp
            set_fields: Dict[str, Any] = {}
            if t.get("unlock_bonus_games"):
                bonuses["bonus_games_unlocked"] = True
                set_fields["bonus_games_unlocked"] = True
            if t.get("concert_pass"):
                bonuses["concert_pass"] = True
                set_fields["concert_pass_eligible"] = True
            if set_fields:
                await db.users.update_one({"user_id": uid}, {"$set": set_fields})
    await db.users.update_one({"user_id": uid},
                              {"$set": {"rewards_thresholds_hit": list(hit)}})

    return {
        "points": points, "multiplier": ai["multiplier"], "reason": ai["reason"],
        "ai": ai["ai"], "balance_after": balance_after, "tier": tier_name,
        "scans_in_window": scans, "bonuses": bonuses, "show_event_id": ev_id,
        "bonus_multiplier": bonus_mult,
    }


# ─────────────────────────── Coupon fraud tracking ───────────────────────────

class ShowEventBody(BaseModel):
    merchant_id: str
    coupon_id: Optional[str] = None
    kind: str = "coupon"          # "coupon" | "scan_to_pay"


@router.post("/api/coupon-events/show")
async def coupon_show(body: ShowEventBody, request: Request, user: dict = Depends(current_user)):
    """Customer pulled/showed a coupon or scan-to-pay code. Logged so we can
    detect merchants who never scan (i.e. dodge paying us)."""
    db = request.app.state.db
    ev_id = f"cev_{uuid.uuid4().hex[:12]}"
    await db.coupon_show_events.insert_one({
        "event_id": ev_id, "user_id": user.get("user_id"),
        "merchant_id": body.merchant_id, "coupon_id": body.coupon_id,
        "kind": body.kind if body.kind in ("coupon", "scan_to_pay") else "coupon",
        "shown_at": _now(), "redeemed": False, "redeemed_at": None})
    from routes.merchant_ops import maybe_alert
    await maybe_alert(db, body.merchant_id)
    return {"ok": True, "event_id": ev_id}


class MerchantRedeemBody(BaseModel):
    merchant_id: str
    user_id: Optional[str] = None
    coupon_id: Optional[str] = None
    code: Optional[str] = None
    amount_usd: Optional[float] = None


@router.post("/api/merchant/redeem")
async def merchant_redeem(body: MerchantRedeemBody, request: Request,
                          user: dict = Depends(current_user)):
    """Merchant confirms a redemption. Reconciles the customer's most recent
    unredeemed show event so the fraud gap closes.

    Phase RWD.5 — locked to the logged-in merchant's OWN venue so a business
    can't confirm (and inflate) redemptions belonging to another venue.
    """
    db = request.app.state.db
    from routes.ad4_coupon_campaigns import _assert_merchant_owner
    await _assert_merchant_owner(db, body.merchant_id, user)
    q: Dict[str, Any] = {"merchant_id": body.merchant_id, "redeemed": False}
    if body.user_id:
        q["user_id"] = body.user_id
    if body.coupon_id:
        q["coupon_id"] = body.coupon_id
    ev = await db.coupon_show_events.find_one_and_update(
        q, {"$set": {"redeemed": True, "redeemed_at": _now()}},
        sort=[("shown_at", -1)])
    await db.merchant_redemptions.insert_one({
        "redemption_id": f"red_{uuid.uuid4().hex[:12]}",
        "merchant_id": body.merchant_id, "user_id": body.user_id,
        "coupon_id": body.coupon_id, "amount_usd": body.amount_usd,
        "operator_user_id": user.get("user_id"),
        "matched_event_id": (ev or {}).get("event_id"),
        "redeemed_at": _now(), "date": _today()})
    loyalty = await _merchant_loyalty(db, body.merchant_id)
    return {"ok": True, "matched_show_event": bool(ev), "loyalty": loyalty}


@router.get("/api/admin/coupon-fraud")
async def admin_coupon_fraud(request: Request, _admin=Depends(require_admin),
                             min_shows: int = Query(5, ge=1),
                             flag_rate: float = Query(0.5, ge=0, le=1)):
    """Per-merchant show-vs-redeem gap. Flags merchants who receive lots of
    coupon shows but rarely scan them (possible off-book discounting)."""
    db = request.app.state.db
    agg = db.coupon_show_events.aggregate([
        {"$group": {"_id": "$merchant_id",
                    "shows": {"$sum": 1},
                    "redemptions": {"$sum": {"$cond": ["$redeemed", 1, 0]}}}},
        {"$sort": {"shows": -1}},
    ])
    out: List[Dict[str, Any]] = []
    async for r in agg:
        shows = int(r.get("shows", 0)); reds = int(r.get("redemptions", 0))
        rate = round(reds / shows, 3) if shows else 0.0
        out.append({
            "merchant_id": r["_id"], "shows": shows, "redemptions": reds,
            "unredeemed": shows - reds, "redemption_rate": rate,
            "flagged": shows >= min_shows and rate < flag_rate,
        })
    return {"items": out, "total": len(out),
            "criteria": {"min_shows": min_shows, "flag_rate": flag_rate}}


async def _merchant_loyalty(db, merchant_id: str) -> Dict[str, Any]:
    cfg = await _get_config(db)
    today_count = await db.merchant_redemptions.count_documents(
        {"merchant_id": merchant_id, "date": _today()})
    tiers = sorted(cfg.get("merchant_tiers", []), key=lambda x: x["min_daily"])
    current = tiers[0] if tiers else {"rate": 0.10, "name": "Standard", "min_daily": 0}
    nxt = None
    for t in tiers:
        if today_count >= t["min_daily"]:
            current = t
        elif nxt is None:
            nxt = t
    return {"merchant_id": merchant_id, "redemptions_today": today_count,
            "tier": current.get("name"), "rate": current.get("rate"),
            "next_tier": nxt}


@router.get("/api/merchant/loyalty")
async def merchant_loyalty(merchant_id: str, request: Request,
                           user: dict = Depends(current_user)):
    return await _merchant_loyalty(request.app.state.db, merchant_id)


# ─────────────────────────── Game frequency limits ───────────────────────────

class GameLimitBody(BaseModel):
    game_key: str
    max_plays: int = 3
    period: str = "day"           # "day" | "month" | "days"
    every_n_days: Optional[int] = None   # used when period == "days"
    enabled: bool = True


def _period_start(period: str, every_n_days: Optional[int]) -> datetime:
    now = _now()
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "days" and every_n_days:
        return now - timedelta(days=int(every_n_days))
    return now.replace(hour=0, minute=0, second=0, microsecond=0)  # day


async def _eligibility(db, uid: str, game_key: str) -> Dict[str, Any]:
    lim = await db.game_play_limits.find_one({"game_key": game_key})
    if not lim or not lim.get("enabled", True):
        return {"eligible": True, "unlimited": True, "game_key": game_key}
    start = _period_start(lim.get("period", "day"), lim.get("every_n_days"))
    used = await db.game_plays.count_documents(
        {"user_id": uid, "game_key": game_key, "played_at": {"$gte": start}})
    max_plays = int(lim.get("max_plays", 3))
    return {
        "eligible": used < max_plays, "unlimited": False, "game_key": game_key,
        "plays_used": used, "max_plays": max_plays,
        "period": lim.get("period", "day"), "every_n_days": lim.get("every_n_days"),
        "period_started_at": start.isoformat(),
    }


@router.get("/api/games/play-eligibility/{game_key}")
async def play_eligibility(game_key: str, request: Request, user: dict = Depends(current_user)):
    return await _eligibility(request.app.state.db, user.get("user_id"), game_key)


class RecordPlayBody(BaseModel):
    game_key: str


@router.post("/api/games/record-play")
async def record_play(body: RecordPlayBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    elig = await _eligibility(db, uid, body.game_key)
    if not elig.get("eligible"):
        raise HTTPException(429, {"code": "play_limit_reached", **elig})
    await db.game_plays.insert_one({"user_id": uid, "game_key": body.game_key, "played_at": _now()})
    return await _eligibility(db, uid, body.game_key)


# ─────────────────────────── Admin provisioning ───────────────────────────

@router.get("/api/rewards/config")
async def get_reward_config(request: Request, _admin=Depends(require_admin)):
    cfg = await _get_config(request.app.state.db)
    cfg.pop("_id", None)
    return cfg


class RewardConfigBody(BaseModel):
    base_points_per_dollar: Optional[float] = None
    engagement_window_days: Optional[int] = None
    min_multiplier: Optional[float] = None
    max_multiplier: Optional[float] = None
    use_ai: Optional[bool] = None
    thresholds: Optional[List[Dict[str, Any]]] = None
    merchant_tiers: Optional[List[Dict[str, Any]]] = None


@router.put("/api/rewards/config")
async def put_reward_config(body: RewardConfigBody, request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    await _get_config(db)
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.reward_engine_config.update_one({"_id": "config"}, {"$set": updates})
    cfg = await _get_config(db)
    cfg.pop("_id", None)
    return cfg


@router.get("/api/games/limits")
async def list_game_limits(request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    out: List[Dict[str, Any]] = []
    async for l in db.game_play_limits.find({}):
        l.pop("_id", None)
        out.append(l)
    return {"items": out, "total": len(out)}


@router.put("/api/games/limits")
async def put_game_limit(body: GameLimitBody, request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    doc = body.dict()
    doc["updated_at"] = _now()
    await db.game_play_limits.update_one(
        {"game_key": body.game_key}, {"$set": doc}, upsert=True)
    return {"ok": True, **doc}
