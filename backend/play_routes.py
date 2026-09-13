"""
play_routes.py — server-resolved Play & Win endpoint (Phase 23 Session 9).

A clean parallel surface that sits alongside the legacy games_v2 routes.
The new listener UI calls POST /api/play/resolve and gets back a flat
WinReveal-ready outcome:

    {playId, won, prizeId, prizeTitle, coupon, balance, playedAt}

Reuses the existing games_v2 weighted-prize lottery + atomic inventory
decrement so prize pools stay consistent across both systems.

ONE-TIME SETUP (run on startup):
  await db.plays.create_index(
      [("listenerId", 1), ("idempotencyKey", 1)], unique=True)
"""
import logging
import secrets
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from auth import current_user
from core.db import db  # re-exported for wallet_routes.py to import
from services import bigcoin
from services.games_v2 import (
    _atomic_claim_prize, _weighted_pick,
    _rollover_daily_caps, _eligible_prize_query,
)

logger = logging.getLogger("bigfm.play")

router = APIRouter(prefix="/api/play", tags=["play"])

STREAK_STEP = 10   # BigPoints earned per consecutive day
STREAK_CAP = 70    # maximum daily streak bonus


async def _award_daily_streak(db, uid: str, now: dt.datetime) -> dict:
    """Credit a consecutive-day play-streak bonus (+10/day, capped at +70),
    at most once per UTC day. Atomic via a per-user daily slot so concurrent
    first-plays can't double-award. Returns {awarded, bonus, streak, balance_after}."""
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    prev = await db.daily_play_streaks.find_one({"user_id": uid})
    if prev and prev.get("last_play_day") == today:
        return {"awarded": False, "bonus": 0,
                "streak": int(prev.get("current_streak") or 0)}
    new_streak = (int(prev.get("current_streak") or 0) + 1
                  if prev and prev.get("last_play_day") == yesterday else 1)
    bonus = min(new_streak * STREAK_STEP, STREAK_CAP)
    try:
        await db.daily_play_streaks.find_one_and_update(
            {"user_id": uid, "last_play_day": {"$ne": today}},
            {"$set": {"last_play_day": today, "current_streak": new_streak,
                      "last_bonus": bonus, "updated_at": now}},
            upsert=True)
    except DuplicateKeyError:
        # Another concurrent first-play already claimed today's slot.
        return {"awarded": False, "bonus": 0, "streak": new_streak}
    res = await bigcoin.award(db, uid, bonus, "daily_play_streak",
                              metadata={"day": today, "streak": new_streak})
    return {"awarded": True, "bonus": bonus, "streak": new_streak,
            "balance_after": int(res["balance_after"])}


async def get_listener_id(user: dict = Depends(current_user)) -> str:
    """Bridge — wallet_routes.py imports this verbatim. Resolves the
    current authenticated user's id from the cookie session."""
    return user["user_id"]


class ResolveRequest(BaseModel):
    gameId: str
    idempotencyKey: str = Field(..., min_length=8, max_length=64)


class CouponOut(BaseModel):
    code: str
    redeemUrl: str
    issuanceRef: Optional[str] = None


class ResolveResponse(BaseModel):
    playId: str
    won: bool
    prizeId: Optional[str] = None
    prizeTitle: Optional[str] = None
    coupon: Optional[CouponOut] = None
    balance: int
    playedAt: str
    bigcoinAwarded: int = 0
    streakBonus: int = 0
    streakCount: int = 0


def _shape(row: dict) -> ResolveResponse:
    return ResolveResponse(
        playId=row["_id"],
        won=bool(row.get("won")),
        prizeId=row.get("prizeId"),
        prizeTitle=row.get("prizeTitle"),
        coupon=CouponOut(**row["coupon"]) if row.get("coupon") else None,
        balance=int(row.get("balance") or 0),
        playedAt=row["playedAt"],
        bigcoinAwarded=int(row.get("bigcoinAwarded") or 0),
        streakBonus=int(row.get("streakBonus") or 0),
        streakCount=int(row.get("streakCount") or 0),
    )


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_play(req: ResolveRequest,
                       user: dict = Depends(current_user)):
    listener_id = user["user_id"]

    # ---- idempotency replay: same key returns the original row. ----
    existing = await db.plays.find_one(
        {"listenerId": listener_id, "idempotencyKey": req.idempotencyKey})
    if existing:
        return _shape(existing)

    # ---- campaign lookup (gameId == campaign_id in our schema). ----
    campaign = await db.game_campaigns.find_one({"campaign_id": req.gameId})
    if not campaign:
        raise HTTPException(404, "Game not found")
    if campaign.get("status") != "active":
        raise HTTPException(
            404, f"Game not active: {campaign.get('status')}")

    now = dt.datetime.now(dt.timezone.utc)
    tpl = await db.game_templates.find_one(
        {"template_id": campaign.get("template_id")}, {"game_type": 1})
    game_type = (tpl or {}).get("game_type")
    is_sponsored = not bool(campaign.get("is_platform_funded"))

    # ---- Daily play policy ----
    # FREE (platform-funded) games: one play per game TYPE per UTC day.
    # SPONSORED (advertiser-funded) games: UNLIMITED plays.
    if not is_sponsored and game_type:
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        played_today = await db.plays.count_documents({
            "listenerId": listener_id,
            "gameType": game_type,
            "isPlatformFunded": True,
            "playedAtDt": {"$gte": start_of_day},
        })
        if played_today >= 1:
            raise HTTPException(429, {
                "code": "daily_type_limit_reached",
                "message": ("You've already played a free game of this type "
                            "today — come back tomorrow, or play a sponsored "
                            "game for unlimited plays.")})

    play_id = "ply_" + secrets.token_hex(10)
    now_iso = now.isoformat()

    # ---- weighted prize lottery (reuses games_v2 helpers). ----
    # Roll over per-day coupon caps at the UTC boundary before drawing so
    # daily-capped prizes (e.g. FPK discount tiers) are awardable today.
    await _rollover_daily_caps(db, req.gameId, now.strftime("%Y-%m-%d"))
    rng = secrets.SystemRandom()
    prize_picked: Optional[dict] = None
    for _ in range(5):
        prizes = await db.game_prizes.find(
            _eligible_prize_query(req.gameId)).to_list(50)
        if not prizes:
            break
        weights = [int(p["probability_weight"]) for p in prizes]
        idx = _weighted_pick(weights, rng)
        if idx < 0:
            break
        if await _atomic_claim_prize(db, prizes[idx], play_id):
            prize_picked = prizes[idx]
            break

    coupon = None
    prize_id = None
    prize_title = None
    if prize_picked:
        prize_id = prize_picked["prize_id"]
        prize_title = prize_picked["title"]
        code = "BIGFM-" + secrets.token_hex(4).upper()
        coupon = {
            "code": code,
            "redeemUrl": f"/redeem/{code}",
            "issuanceRef": f"internal:{play_id}",
        }

    # Snapshot listener BigCoin balance for the WinReveal HUD.
    u = await db.users.find_one(
        {"user_id": listener_id}, {"bigcoin_balance": 1}) or {}
    balance = int(u.get("bigcoin_balance") or 0)

    doc = {
        "_id": play_id,
        "playId": play_id,
        "listenerId": listener_id,
        "gameId": req.gameId,
        "campaignId": req.gameId,
        "gameType": game_type,
        "isPlatformFunded": bool(campaign.get("is_platform_funded")),
        "won": bool(prize_picked),
        "prizeId": prize_id,
        "prizeTitle": prize_title,
        "coupon": coupon,
        "idempotencyKey": req.idempotencyKey,
        "playedAt": now_iso,
        "playedAtDt": now,
        "balance": balance,
    }
    try:
        await db.plays.insert_one(doc)
    except DuplicateKeyError:
        # Race: concurrent request inserted under the same key.
        existing = await db.plays.find_one({
            "listenerId": listener_id,
            "idempotencyKey": req.idempotencyKey,
        })
        if existing:
            return _shape(existing)
        raise HTTPException(409, "duplicate idempotency key")

    # ---- Credit the wallet (runs once, only on a fresh insert). ----
    # A won BigPoints prize actually mutates the listener's balance now;
    # previously the prize was resolved but never credited.
    bigcoin_awarded = 0
    if prize_picked and prize_picked.get("prize_type") == "bigcoin":
        amt = int(prize_picked.get("value_amount") or 0)
        if amt > 0:
            res = await bigcoin.award(
                db, listener_id, amt, "game_win",
                metadata={"playId": play_id, "gameId": req.gameId,
                          "prizeId": prize_id})
            balance = int(res["balance_after"])
            bigcoin_awarded = amt

    # ---- Daily play-streak bonus (+10/day, capped +70; once per UTC day). ----
    streak = await _award_daily_streak(db, listener_id, now)
    if streak.get("awarded"):
        balance = int(streak.get("balance_after") or balance)

    doc["balance"] = balance
    doc["bigcoinAwarded"] = bigcoin_awarded
    doc["streakBonus"] = int(streak.get("bonus") or 0)
    doc["streakCount"] = int(streak.get("streak") or 0)
    await db.plays.update_one(
        {"_id": play_id},
        {"$set": {"balance": balance, "bigcoinAwarded": bigcoin_awarded,
                  "streakBonus": doc["streakBonus"], "streakCount": doc["streakCount"]}})

    return _shape(doc)


# ---------------------------------------------------------------------
# Startup index hook — called from server.py on app bootstrap.  Safe to
# run repeatedly: create_index is idempotent on a matching spec.
# ---------------------------------------------------------------------
async def ensure_play_wallet_indexes() -> None:
    await db.plays.create_index(
        [("listenerId", 1), ("idempotencyKey", 1)],
        unique=True, name="plays_listener_idem_unique")
    await db.daily_play_streaks.create_index(
        [("user_id", 1)], unique=True, name="daily_play_streaks_user_unique")
    await db.wallet_items.create_index(
        [("playId", 1), ("listenerId", 1)],
        unique=True, name="wallet_items_play_listener_unique")
    await db.wallet_items.create_index(
        [("listenerId", 1), ("savedAt", -1)],
        name="wallet_items_listener_recent")
    logger.info(
        "Phase 23 Session 9 indexes ready: plays.(listenerId,idempotencyKey), "
        "daily_play_streaks.user_id, "
        "wallet_items.(playId,listenerId), wallet_items.(listenerId,savedAt)")


@router.get("/streak")
async def play_streak_status(user: dict = Depends(current_user)):
    """Current consecutive-day play streak + next-day bonus preview."""
    now = dt.datetime.now(dt.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    doc = await db.daily_play_streaks.find_one({"user_id": user["user_id"]})
    last_day = (doc or {}).get("last_play_day")
    streak = int((doc or {}).get("current_streak") or 0)
    # Streak is broken if the last play wasn't today or yesterday.
    active = last_day in (today, yesterday)
    current = streak if active else 0
    claimed_today = last_day == today
    # Bonus you'd earn on your next qualifying play-day (today or tomorrow).
    next_bonus = min((current + 1) * STREAK_STEP, STREAK_CAP)
    return {
        "streak": current,
        "claimedToday": claimed_today,
        "todayBonus": int((doc or {}).get("last_bonus") or 0) if claimed_today else 0,
        "nextBonus": next_bonus,
        "step": STREAK_STEP,
        "cap": STREAK_CAP,
    }
