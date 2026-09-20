"""Phase RWD.1 — Rewards "Earn Loop".

A platform-agnostic layer (web + mobile consume the same contract) that
turns the existing Points engine (services/points_service.py) into a
visible, gamified earn loop:

Listener:
  GET  /api/me/earn/overview            — one call powers the whole UX
  GET  /api/me/earn/ways-to-earn        — ordered earn opportunities
  POST /api/me/earn/missions/{id}/claim — claim a completed mission reward

Admin (tunable — nothing hardcoded in the client):
  GET/PUT /api/admin/earn/catalog       — earn-opportunity presentation
  GET/PUT /api/admin/earn/missions      — daily/weekly missions
  GET/PUT /api/admin/earn/config        — listener tiers + daily goal

Design notes
------------
- Economic truth stays in `points_earn_rules` (base points + caps).
- This module adds presentation + progress on top; each item exposes a
  semantic `action` key (e.g. "listen", "trivia") that each client maps
  to its own route — so no web/mobile route assumptions leak into the API.
- All seeds are idempotent ($setOnInsert) so admin edits survive reboots.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user, require_admin
from services.points_service import PointsService

router = APIRouter(tags=["rewards-earn"])


# ─────────────────────────── Seed defaults ───────────────────────────
DEFAULT_CATALOG: List[Dict[str, Any]] = [
    {"key": "listen", "title": "Listen to radio", "subtitle": "Earn points every minute you tune in",
     "icon": "radio", "points": 1, "unit": "per min", "rule_id": "listening_minute",
     "action": "listen", "category": "available", "sort": 10},
    {"key": "daily_code", "title": "Enter today's code", "subtitle": "Grab the on-air daily code",
     "icon": "key", "points": 500, "rule_id": None,
     "action": "daily_code", "category": "daily", "sort": 20},
    {"key": "trivia", "title": "Play daily trivia", "subtitle": "10 questions, big points",
     "icon": "brain", "points": 100, "rule_id": None,
     "action": "trivia", "category": "daily", "sort": 30},
    {"key": "predict", "title": "Make a prediction", "subtitle": "Predict & Win today",
     "icon": "target", "points": 50, "rule_id": "predict_win_participate",
     "action": "predict", "category": "daily", "sort": 40},
    {"key": "game", "title": "Play & Win", "subtitle": "Spin, scratch and win points",
     "icon": "gamepad", "points": 100, "rule_id": "game_win",
     "action": "game", "category": "available", "sort": 50},
    {"key": "checkin", "title": "Visit a business", "subtitle": "Check in at a partner venue",
     "icon": "map-pin", "points": 100, "rule_id": "venue_checkin",
     "action": "discover", "category": "available", "sort": 60},
    {"key": "pay", "title": "Pay with FUUSIC", "subtitle": "Earn on every purchase",
     "icon": "credit-card", "points": 25, "rule_id": None,
     "action": "discover", "category": "available", "sort": 70},
    {"key": "share", "title": "Share FUUSIC", "subtitle": "Spread the word",
     "icon": "share", "points": 5, "rule_id": "social_share",
     "action": "share", "category": "available", "sort": 80},
    {"key": "refer", "title": "Invite a friend", "subtitle": "Earn when a friend joins",
     "icon": "user-plus", "points": 100, "rule_id": "referral_signup",
     "action": "refer", "category": "available", "sort": 90},
]

DEFAULT_MISSIONS: List[Dict[str, Any]] = [
    {"mission_id": "daily_trivia", "title": "Play daily trivia", "scope": "daily",
     "target": 1, "metric": "count", "sources": ["game_win", "trivia"],
     "reward_points": 100, "icon": "brain", "sort": 10, "enabled": True},
    {"mission_id": "daily_listen", "title": "Listen for 10 minutes", "scope": "daily",
     "target": 10, "metric": "count", "sources": ["listening_minute"],
     "reward_points": 50, "icon": "radio", "sort": 20, "enabled": True},
    {"mission_id": "daily_code", "title": "Enter the daily code", "scope": "daily",
     "target": 1, "metric": "count", "sources": ["daily_code_claim"],
     "reward_points": 25, "icon": "key", "sort": 30, "enabled": True},
    {"mission_id": "weekly_explorer", "title": "Listen on 5 different days", "scope": "weekly",
     "target": 5, "metric": "days", "sources": ["listening_minute"],
     "reward_points": 500, "icon": "compass", "sort": 40, "enabled": True},
    {"mission_id": "weekly_games", "title": "Complete 3 games", "scope": "weekly",
     "target": 3, "metric": "count", "sources": ["game_win", "trivia"],
     "reward_points": 300, "icon": "gamepad", "sort": 50, "enabled": True},
    {"mission_id": "weekly_local", "title": "Visit 2 participating businesses", "scope": "weekly",
     "target": 2, "metric": "count", "sources": ["venue_checkin"],
     "reward_points": 750, "icon": "map-pin", "sort": 60, "enabled": True},
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "_id": "config",
    "listener_tiers": [
        {"name": "Bronze", "min_points": 0},
        {"name": "Silver", "min_points": 1000},
        {"name": "Gold", "min_points": 5000},
        {"name": "Platinum", "min_points": 15000},
    ],
    "daily_goal_target": 500,
    "daily_goal_bonus": 100,
    "streak_bonuses": [
        {"days": 3, "points": 50},
        {"days": 7, "points": 200},
        {"days": 14, "points": 500},
        {"days": 30, "points": 1000},
    ],
    "weekly_streak_base": 150,      # escalating weekly-challenge bonus = base × streak
    "weekly_streak_cap": 5,         # streak multiplier capped at this many weeks
}


# ─────────────────────────── Helpers ───────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_start() -> datetime:
    return _now().replace(hour=0, minute=0, second=0, microsecond=0)


def _today_key() -> str:
    return _now().strftime("%Y-%m-%d")


def _week_start() -> datetime:
    now = _today_start()
    return now - timedelta(days=now.weekday())  # Monday 00:00 UTC


def _week_key() -> str:
    return _week_start().strftime("%Y-W%U")


async def _seed(db) -> None:
    now = _now()
    for c in DEFAULT_CATALOG:
        await db.earn_actions_catalog.update_one(
            {"key": c["key"]},
            {"$setOnInsert": {**c, "enabled": c.get("enabled", True),
                              "created_at": now, "updated_at": now}},
            upsert=True)
    for m in DEFAULT_MISSIONS:
        await db.earn_missions.update_one(
            {"mission_id": m["mission_id"]},
            {"$setOnInsert": {**m, "created_at": now, "updated_at": now}},
            upsert=True)
    if not await db.earn_config.find_one({"_id": "config"}):
        await db.earn_config.insert_one(dict(DEFAULT_CONFIG))
    await db.earn_mission_claims.create_index(
        [("user_id", 1), ("mission_id", 1), ("period_key", 1)], unique=True)


async def _get_config(db) -> Dict[str, Any]:
    cfg = await db.earn_config.find_one({"_id": "config"})
    if not cfg:
        await db.earn_config.insert_one(dict(DEFAULT_CONFIG))
        return dict(DEFAULT_CONFIG)
    # Backfill any keys added after this doc was first seeded (e.g. streak_bonuses).
    missing = {k: v for k, v in DEFAULT_CONFIG.items()
               if k != "_id" and k not in cfg}
    if missing:
        await db.earn_config.update_one({"_id": "config"}, {"$set": missing})
        cfg.update(missing)
    return cfg


async def _sum_positive(db, uid: str, sources: List[str], since: datetime) -> int:
    pipe = [{"$match": {"user_id": uid, "source": {"$in": sources},
                        "created_at": {"$gte": since}, "delta": {"$gt": 0}}},
            {"$group": {"_id": None, "n": {"$sum": 1}}}]
    async for d in db.points_ledger.aggregate(pipe):
        return int(d.get("n") or 0)
    return 0


async def _distinct_days(db, uid: str, sources: List[str], since: datetime) -> int:
    pipe = [{"$match": {"user_id": uid, "source": {"$in": sources},
                        "created_at": {"$gte": since}, "delta": {"$gt": 0}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d",
                                                   "date": "$created_at"}}}},
            {"$count": "days"}]
    async for d in db.points_ledger.aggregate(pipe):
        return int(d.get("days") or 0)
    return 0


async def _lifetime_earned(db, uid: str) -> int:
    pipe = [{"$match": {"user_id": uid, "delta": {"$gt": 0}}},
            {"$group": {"_id": None, "t": {"$sum": "$delta"}}}]
    async for d in db.points_ledger.aggregate(pipe):
        return int(d.get("t") or 0)
    return 0


async def _today_earned(db, uid: str) -> int:
    pipe = [{"$match": {"user_id": uid, "delta": {"$gt": 0},
                        "created_at": {"$gte": _today_start()}}},
            {"$group": {"_id": None, "t": {"$sum": "$delta"}}}]
    async for d in db.points_ledger.aggregate(pipe):
        return int(d.get("t") or 0)
    return 0


async def _cap_progress(db, uid: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    """Today's usage vs daily cap for a rule; returns eligibility."""
    cap = rule.get("daily_cap_per_user")
    if not cap:
        return {"eligible": rule.get("enabled", True), "used": 0, "cap": None}
    pipe = [{"$match": {"user_id": uid, "source": rule["rule_id"], "delta": {"$gt": 0},
                        "created_at": {"$gte": _today_start()}}},
            {"$group": {"_id": None, "t": {"$sum": "$delta"}}}]
    used = 0
    async for d in db.points_ledger.aggregate(pipe):
        used = int(d.get("t") or 0)
    return {"eligible": rule.get("enabled", True) and used < cap,
            "used": used, "cap": int(cap)}


async def _daily_code_eligible(db, uid: str) -> Dict[str, Any]:
    code = await db.daily_codes.find_one({"date_effective": _today_key()})
    if not code:
        return {"eligible": True, "points": None}
    claimed = await db.daily_code_claims.find_one(
        {"user_id": uid, "daily_code_id": code.get("daily_code_id")})
    return {"eligible": not bool(claimed),
            "points": int(code.get("points_reward") or 0)}


async def _current_streak(db, uid: str) -> int:
    """Consecutive UTC days (ending today or yesterday) with earn activity."""
    since = _today_start() - timedelta(days=30)
    pipe = [{"$match": {"user_id": uid, "delta": {"$gt": 0},
                        "created_at": {"$gte": since}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d",
                                                   "date": "$created_at"}}}}]
    days = set()
    async for d in db.points_ledger.aggregate(pipe):
        days.add(d["_id"])
    if not days:
        return 0
    streak = 0
    cursor = _today_start()
    # allow the streak to still count if today has no activity yet but yesterday did
    if cursor.strftime("%Y-%m-%d") not in days:
        cursor = cursor - timedelta(days=1)
    while cursor.strftime("%Y-%m-%d") in days:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


async def _streak_details(db, uid: str) -> Dict[str, Any]:
    """Current streak length + the anchor (first day) of the current run,
    used to make milestone-bonus awards idempotent per run."""
    since = _today_start() - timedelta(days=45)
    pipe = [{"$match": {"user_id": uid, "delta": {"$gt": 0},
                        "created_at": {"$gte": since}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d",
                                                   "date": "$created_at"}}}}]
    days = set()
    async for d in db.points_ledger.aggregate(pipe):
        days.add(d["_id"])
    if not days:
        return {"current": 0, "anchor": None}
    cursor = _today_start()
    if cursor.strftime("%Y-%m-%d") not in days:
        cursor = cursor - timedelta(days=1)
    streak = 0
    anchor = None
    while cursor.strftime("%Y-%m-%d") in days:
        streak += 1
        anchor = cursor.strftime("%Y-%m-%d")
        cursor = cursor - timedelta(days=1)
    return {"current": streak, "anchor": anchor}


async def _streak_state(db, uid: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    det = await _streak_details(db, uid)
    current, anchor = det["current"], det["anchor"]
    milestones = sorted(cfg.get("streak_bonuses", []), key=lambda m: m["days"])

    # best-streak tracking
    state = await db.earn_streak_state.find_one({"user_id": uid}) or {}
    best = max(int(state.get("best_streak", 0)), current)
    if best != int(state.get("best_streak", 0)):
        await db.earn_streak_state.update_one(
            {"user_id": uid}, {"$set": {"best_streak": best, "updated_at": _now()}},
            upsert=True)

    # award the highest milestone reached in THIS run (idempotent per anchor)
    awarded = None
    reached = [m for m in milestones if current >= m["days"]]
    if reached and anchor:
        m = reached[-1]
        key = f"streak:{m['days']}:{uid}:{anchor}"
        already = await db.points_ledger.find_one({"idempotency_key": key})
        if not already:
            await PointsService(db).award(
                user_id=uid, source="streak_bonus", source_id=str(m["days"]),
                delta=int(m["points"]),
                metadata={"streak_days": m["days"], "anchor": anchor},
                idempotency_key=key, enforce_caps=False)
            awarded = {"days": m["days"], "points": int(m["points"])}

    nxt = next((m for m in milestones if m["days"] > current), None)
    weekly = await _weekly_streak(db, uid)
    base = int(cfg.get("weekly_streak_base", 150))
    cap = int(cfg.get("weekly_streak_cap", 5))
    return {"current": current, "best": best, "next": nxt,
            "awarded_bonus": awarded,
            "weekly": {"current": weekly,
                       "next_reward": base * min(weekly + 1, cap)}}


async def _build_ways(db, uid: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    dc = None
    async for c in db.earn_actions_catalog.find({"enabled": True}).sort("sort", 1):
        pts = c.get("points")
        eligible = True
        used = cap = None
        rid = c.get("rule_id")
        if rid:
            rule = await db.points_earn_rules.find_one({"rule_id": rid})
            if rule:
                if pts is None:
                    pts = int(rule.get("base_points") or 0)
                prog = await _cap_progress(db, uid, rule)
                eligible, used, cap = prog["eligible"], prog["used"], prog["cap"]
        if c.get("action") == "daily_code":
            if dc is None:
                dc = await _daily_code_eligible(db, uid)
            eligible = dc["eligible"]
            if dc["points"]:
                pts = dc["points"]
        items.append({
            "key": c["key"], "title": c["title"], "subtitle": c.get("subtitle"),
            "icon": c.get("icon"), "points": int(pts or 0), "unit": c.get("unit"),
            "action": c.get("action"), "category": c.get("category", "available"),
            "eligible": bool(eligible), "used_today": used, "daily_cap": cap,
        })
    # eligible first, then configured sort
    items.sort(key=lambda x: (not x["eligible"],))
    return items


async def _mission_state(db, uid: str, m: Dict[str, Any]) -> Dict[str, Any]:
    scope = m.get("scope", "daily")
    since = _today_start() if scope == "daily" else _week_start()
    period_key = _today_key() if scope == "daily" else _week_key()
    sources = m.get("sources") or []
    metric = m.get("metric", "count")
    if metric == "days":
        progress = await _distinct_days(db, uid, sources, since)
    else:
        progress = await _sum_positive(db, uid, sources, since)
    target = int(m.get("target", 1))
    claimed = await db.earn_mission_claims.find_one(
        {"user_id": uid, "mission_id": m["mission_id"], "period_key": period_key})
    complete = progress >= target
    return {
        "mission_id": m["mission_id"], "title": m["title"], "scope": scope,
        "icon": m.get("icon"), "target": target, "progress": min(progress, target),
        "reward_points": int(m.get("reward_points", 0)),
        "complete": complete, "claimed": bool(claimed),
        "claimable": complete and not bool(claimed),
        "period_key": period_key,
    }


async def _tier_state(cfg: Dict[str, Any], lifetime: int) -> Dict[str, Any]:
    tiers = sorted(cfg.get("listener_tiers", []), key=lambda t: t["min_points"])
    current = tiers[0] if tiers else {"name": "Bronze", "min_points": 0}
    nxt = None
    for t in tiers:
        if lifetime >= t["min_points"]:
            current = t
        elif nxt is None:
            nxt = t
    to_next = (nxt["min_points"] - lifetime) if nxt else 0
    return {"name": current.get("name"), "min_points": current.get("min_points"),
            "next": nxt, "points_to_next": max(0, to_next), "lifetime_points": lifetime}


# ─────────────────────────── Listener endpoints ───────────────────────────
@router.get("/api/me/earn/overview")
async def earn_overview(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _seed(db)
    uid = user["user_id"]
    svc = PointsService(db)
    cfg = await _get_config(db)
    # streak first — may award a milestone bonus that affects balance/lifetime.
    streak = await _streak_state(db, uid, cfg)
    balance = await svc.get_balance(uid)
    lifetime = await _lifetime_earned(db, uid)
    today = await _today_earned(db, uid)
    tier = await _tier_state(cfg, lifetime)
    ways = await _build_ways(db, uid)
    # Phase RWD.4 — active Sponsored Bonus windows surfaced in the earn loop.
    active_bonuses: List[Dict[str, Any]] = []
    try:
        from routes.merchant_ops import active_bonus_windows
        active_bonuses = await active_bonus_windows(db)
    except Exception:
        active_bonuses = []
    missions: List[Dict[str, Any]] = []
    async for m in db.earn_missions.find({"enabled": True}).sort("sort", 1):
        missions.append(await _mission_state(db, uid, m))
    target = int(cfg.get("daily_goal_target", 500))
    return {
        "balance": balance,
        "tier": tier,
        "daily_goal": {
            "target": target, "earned": today,
            "bonus_points": int(cfg.get("daily_goal_bonus", 0)),
            "pct": min(100, round((today / target) * 100)) if target else 0,
            "complete": today >= target,
        },
        "streak": streak,
        "active_bonuses": active_bonuses,
        "ways_to_earn": ways,
        "missions": missions,
    }


@router.get("/api/me/earn/ways-to-earn")
async def ways_to_earn(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _seed(db)
    return {"items": await _build_ways(db, user["user_id"])}


@router.post("/api/me/earn/missions/{mission_id}/claim")
async def claim_mission(mission_id: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    m = await db.earn_missions.find_one({"mission_id": mission_id, "enabled": True})
    if not m:
        raise HTTPException(404, {"code": "mission_not_found"})
    st = await _mission_state(db, uid, m)
    if not st["complete"]:
        raise HTTPException(400, {"code": "mission_incomplete", **st})
    if st["claimed"]:
        raise HTTPException(409, {"code": "already_claimed", **st})
    period_key = st["period_key"]
    try:
        await db.earn_mission_claims.insert_one({
            "user_id": uid, "mission_id": mission_id, "period_key": period_key,
            "claimed_at": _now()})
    except Exception:
        raise HTTPException(409, {"code": "already_claimed", **st})
    res = await PointsService(db).award(
        user_id=uid, source="mission_reward",
        source_id=mission_id, delta=int(m.get("reward_points", 0)),
        metadata={"mission_id": mission_id, "period_key": period_key},
        idempotency_key=f"mission:{mission_id}:{uid}:{period_key}",
        enforce_caps=False)
    balance_after = res.balance_after
    # Phase RWD.5 — escalating weekly-challenge streak bonus when the user
    # completes ALL weekly missions for the week.
    weekly = None
    if m.get("scope") == "weekly":
        weekly = await _maybe_weekly_streak_bonus(db, uid)
        if weekly:
            balance_after = weekly["balance_after"]
    return {"ok": True, "awarded": int(m.get("reward_points", 0)),
            "weekly_bonus": weekly,
            "balance_after": balance_after,
            "mission": {**st, "claimed": True, "claimable": False}}


async def _maybe_weekly_streak_bonus(db, uid: str) -> Optional[Dict[str, Any]]:
    """If every enabled weekly mission is now claimed for this week, record the
    completion, compute the consecutive-week streak, and award an escalating
    bonus (base × min(streak, cap)), idempotent per week."""
    week_key = _week_key()
    weekly_missions = [m async for m in db.earn_missions.find(
        {"enabled": True, "scope": "weekly"})]
    if not weekly_missions:
        return None
    for m in weekly_missions:
        claimed = await db.earn_mission_claims.find_one(
            {"user_id": uid, "mission_id": m["mission_id"], "period_key": week_key})
        if not claimed:
            return None  # not all weekly missions done yet
    wk = _week_start().strftime("%Y-%m-%d")
    try:
        await db.earn_weekly_completions.insert_one(
            {"user_id": uid, "week_start": wk, "created_at": _now()})
    except Exception:
        return None  # already recorded this week
    streak = await _weekly_streak(db, uid)
    cfg = await _get_config(db)
    base = int(cfg.get("weekly_streak_base", 150))
    cap = int(cfg.get("weekly_streak_cap", 5))
    points = base * min(streak, cap)
    res = await PointsService(db).award(
        user_id=uid, source="weekly_streak_bonus", source_id=wk, delta=points,
        metadata={"week_start": wk, "weekly_streak": streak},
        idempotency_key=f"weekstreak:{wk}:{uid}", enforce_caps=False)
    return {"points": points, "weekly_streak": streak, "balance_after": res.balance_after}


async def _weekly_streak(db, uid: str) -> int:
    """Consecutive completed weeks ending this or last week."""
    from datetime import timedelta
    weeks = set()
    async for d in db.earn_weekly_completions.find(
            {"user_id": uid}, {"week_start": 1}):
        weeks.add(d["week_start"])
    if not weeks:
        return 0
    cursor = _week_start()
    if cursor.strftime("%Y-%m-%d") not in weeks:
        cursor = cursor - timedelta(days=7)
    streak = 0
    while cursor.strftime("%Y-%m-%d") in weeks:
        streak += 1
        cursor = cursor - timedelta(days=7)
    return streak


# ─────────────────────────── Admin endpoints ───────────────────────────
@router.get("/api/admin/earn/catalog")
async def admin_get_catalog(request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    await _seed(db)
    out = []
    async for c in db.earn_actions_catalog.find({}).sort("sort", 1):
        c.pop("_id", None)
        out.append(c)
    return {"items": out, "total": len(out)}


class CatalogItemBody(BaseModel):
    key: str
    title: Optional[str] = None
    subtitle: Optional[str] = None
    icon: Optional[str] = None
    points: Optional[int] = None
    unit: Optional[str] = None
    rule_id: Optional[str] = None
    action: Optional[str] = None
    category: Optional[str] = None
    sort: Optional[int] = None
    enabled: Optional[bool] = None


@router.put("/api/admin/earn/catalog")
async def admin_put_catalog(body: CatalogItemBody, request: Request,
                            _admin=Depends(require_admin)):
    db = request.app.state.db
    updates = {k: v for k, v in body.dict().items() if v is not None and k != "key"}
    updates["updated_at"] = _now()
    await db.earn_actions_catalog.update_one(
        {"key": body.key}, {"$set": updates}, upsert=True)
    doc = await db.earn_actions_catalog.find_one({"key": body.key})
    doc.pop("_id", None)
    return doc


@router.get("/api/admin/earn/missions")
async def admin_get_missions(request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    await _seed(db)
    out = []
    async for m in db.earn_missions.find({}).sort("sort", 1):
        m.pop("_id", None)
        out.append(m)
    return {"items": out, "total": len(out)}


class MissionBody(BaseModel):
    mission_id: str
    title: Optional[str] = None
    scope: Optional[str] = None
    target: Optional[int] = None
    metric: Optional[str] = None
    sources: Optional[List[str]] = None
    reward_points: Optional[int] = None
    icon: Optional[str] = None
    sort: Optional[int] = None
    enabled: Optional[bool] = None


@router.put("/api/admin/earn/missions")
async def admin_put_mission(body: MissionBody, request: Request,
                            _admin=Depends(require_admin)):
    db = request.app.state.db
    updates = {k: v for k, v in body.dict().items()
               if v is not None and k != "mission_id"}
    updates["updated_at"] = _now()
    await db.earn_missions.update_one(
        {"mission_id": body.mission_id}, {"$set": updates}, upsert=True)
    doc = await db.earn_missions.find_one({"mission_id": body.mission_id})
    doc.pop("_id", None)
    return doc


@router.get("/api/admin/earn/config")
async def admin_get_config(request: Request, _admin=Depends(require_admin)):
    cfg = await _get_config(request.app.state.db)
    cfg.pop("_id", None)
    return cfg


class EarnConfigBody(BaseModel):
    listener_tiers: Optional[List[Dict[str, Any]]] = None
    daily_goal_target: Optional[int] = None
    daily_goal_bonus: Optional[int] = None
    streak_bonuses: Optional[List[Dict[str, Any]]] = None
    weekly_streak_base: Optional[int] = None
    weekly_streak_cap: Optional[int] = None


@router.put("/api/admin/earn/config")
async def admin_put_config(body: EarnConfigBody, request: Request,
                           _admin=Depends(require_admin)):
    db = request.app.state.db
    await _get_config(db)
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.earn_config.update_one({"_id": "config"}, {"$set": updates})
    cfg = await _get_config(db)
    cfg.pop("_id", None)
    return cfg
