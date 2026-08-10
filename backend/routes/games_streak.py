"""Games Daily Streak — play all the house games in a day to earn a bonus.
Encourages daily return.  Reuses game_sessions (completed/claimed) to detect
which house games were played today; awards a one-per-day BigCoin bonus."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user
from services.points_service import PointsService
from services.games_v2 import EXTRA_HOUSE_GAMES

router = APIRouter(prefix="/api/games_v2/daily-streak", tags=["games-streak"])

STREAK_GAME_IDS = [g["id"] for g in EXTRA_HOUSE_GAMES]  # scratch, mystery, memory, word
STREAK_BONUS_POINTS = 100


def _day_start() -> datetime:
    n = datetime.now(timezone.utc)
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _played_today(db, uid: str) -> list:
    start = _day_start()
    played = set()
    async for s in db.game_sessions.find({
        "user_id": uid, "campaign_id": {"$in": STREAK_GAME_IDS},
        "status": {"$in": ["completed", "claimed"]},
        "started_at": {"$gte": start},
    }, {"campaign_id": 1}):
        played.add(s.get("campaign_id"))
    return [g for g in STREAK_GAME_IDS if g in played]


async def _titles(db) -> dict:
    out = {}
    async for c in db.game_campaigns.find(
            {"campaign_id": {"$in": STREAK_GAME_IDS}}, {"campaign_id": 1, "title": 1}):
        out[c["campaign_id"]] = c.get("title")
    return out


@router.get("")
async def streak_status(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    played = await _played_today(db, uid)
    titles = await _titles(db)
    claim = await db.daily_streak_claims.find_one({"user_id": uid, "day": _day_key()})
    all_done = len(played) >= len(STREAK_GAME_IDS)
    return {
        "games": [{"campaign_id": g, "title": titles.get(g, g), "played": g in played}
                  for g in STREAK_GAME_IDS],
        "played_count": len(played), "total": len(STREAK_GAME_IDS),
        "all_done": all_done, "bonus_points": STREAK_BONUS_POINTS,
        "claimed": bool(claim),
    }


@router.post("/claim")
async def claim_streak(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    day = _day_key()
    if await db.daily_streak_claims.find_one({"user_id": uid, "day": day}):
        raise HTTPException(400, {"code": "already_claimed"})
    played = await _played_today(db, uid)
    if len(played) < len(STREAK_GAME_IDS):
        raise HTTPException(400, {"code": "streak_incomplete",
                                  "played": len(played), "total": len(STREAK_GAME_IDS)})
    res = await PointsService(db).award(
        user_id=uid, source="daily_game_streak", source_id=day,
        delta=STREAK_BONUS_POINTS, metadata={"day": day},
        idempotency_key=f"streak:{uid}:{day}", enforce_caps=False)
    await db.daily_streak_claims.insert_one({
        "user_id": uid, "day": day, "points": STREAK_BONUS_POINTS,
        "created_at": datetime.now(timezone.utc)})
    return {"ok": True, "points": STREAK_BONUS_POINTS, "balance_after": res.balance_after}


__all__ = ["router"]
