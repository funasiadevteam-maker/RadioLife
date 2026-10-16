"""Game rewards — daily-play streaks + a live "just won" winners ticker.

Both are strictly server-authoritative, mirroring the rest of Play & Win:
- Streak bonus points are credited via PointsService with a per-day
  idempotency key, so replays never double-credit.
- A 7-day (multiple-of-7) streak grants ONE bonus house spin for the day,
  tracked in `game_bonus_spins` and read back by instant_games `_spins_left`.
- Winners are recorded on real wins only; the ticker pads with a few
  realistic samples so it never looks empty on a quiet day.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request, Depends

from auth import current_user
from services.points_service import PointsService

router = APIRouter(prefix="/api/games", tags=["game_rewards"])

STREAK_CAP_DAY = 7          # bonus grows until day 7, then plateaus
STREAK_PTS_PER_DAY = 10     # day N bonus = min(N, 7) * 10  (max 70)
TICKER_MIN_ITEMS = 8        # pad with samples below this many real wins

GAME_LABELS = {
    "spin_win": "Spin & Win",
    "scratch_win": "Daily Scratch",
    "lucky_dice": "Lucky Dice",
    "wheel": "Spin & Win",
    "scratch": "Daily Scratch",
    "dice": "Lucky Dice",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).strftime("%Y-%m-%d")


def _display_name(user: Optional[dict]) -> str:
    if not user:
        return "A FUUSIC fan"
    raw = (user.get("name") or "").strip()
    if not raw:
        raw = (user.get("email") or "").split("@")[0]
    if not raw:
        return "A FUUSIC fan"
    parts = raw.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0].upper()}."
    return parts[0]


# ───────────────────────────── indexes ─────────────────────────────
async def seed_game_rewards(db) -> None:
    await db.game_streaks.create_index("user_id", name="gs_user")
    await db.game_bonus_spins.create_index("user_id", name="gbs_user")
    await db.game_wins.create_index([("created_at", -1)], name="gw_time")


# ─────────────────────── bonus house spins ─────────────────────────
async def bonus_spins_today(db, user_id: str) -> int:
    """Extra house spins granted today by a 7-day streak milestone."""
    doc = await db.game_bonus_spins.find_one({"_id": f"{user_id}:{_day()}"})
    return int((doc or {}).get("count") or 0) if doc else 0


# ─────────────────────────── streak core ───────────────────────────
async def touch_streak(db, user_id: str) -> dict:
    """Call on EVERY game play. Advances the daily-play streak and credits a
    growing bonus once per UTC day. Returns the streak + any bonus awarded."""
    today = _day()
    yesterday = _day(_now() - timedelta(days=1))
    doc = await db.game_streaks.find_one({"_id": user_id}) or {}
    last = doc.get("last_play_day")
    cur = int(doc.get("current") or 0)

    bonus = {"awarded": False, "points": 0, "bonus_spin": False, "streak_day": cur}

    if last == today:
        new_cur = cur                      # already counted + rewarded today
    else:
        new_cur = cur + 1 if last == yesterday else 1
        cap_day = min(new_cur, STREAK_CAP_DAY)
        pts = cap_day * STREAK_PTS_PER_DAY
        res = await PointsService(db).award(
            user_id=user_id, source="streak_bonus", delta=pts,
            idempotency_key=f"streak:{user_id}:{today}", enforce_caps=False,
            metadata={"streak_day": new_cur})
        bonus_spin = (new_cur % STREAK_CAP_DAY == 0)
        if bonus_spin and not res.idempotency_hit:
            await db.game_bonus_spins.update_one(
                {"_id": f"{user_id}:{today}"},
                {"$inc": {"count": 1},
                 "$set": {"user_id": user_id, "day": today, "updated_at": _now()}},
                upsert=True)
        bonus = {"awarded": not res.idempotency_hit, "points": pts,
                 "bonus_spin": bonus_spin, "streak_day": new_cur}

    longest = max(int(doc.get("longest") or 0), new_cur)
    await db.game_streaks.update_one(
        {"_id": user_id},
        {"$set": {"user_id": user_id, "current": new_cur, "longest": longest,
                  "last_play_day": today, "updated_at": _now()}},
        upsert=True)
    return {"current": new_cur, "longest": longest, "played_today": True,
            "bonus": bonus}


@router.get("/streak")
async def get_streak(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    today = _day()
    yesterday = _day(_now() - timedelta(days=1))
    doc = await db.game_streaks.find_one({"_id": uid}) or {}
    cur = int(doc.get("current") or 0)
    last = doc.get("last_play_day")
    played_today = (last == today)
    if played_today:
        prospective = cur
    else:
        prospective = cur + 1 if last == yesterday else 1
    pending = min(prospective, STREAK_CAP_DAY) * STREAK_PTS_PER_DAY
    return {
        "current_streak": cur if played_today else (cur if last == yesterday else 0),
        "longest_streak": int(doc.get("longest") or 0),
        "played_today": played_today,
        "claim_available": not played_today,
        "pending_bonus_points": 0 if played_today else pending,
        "pending_bonus_spin": (not played_today) and (prospective % STREAK_CAP_DAY == 0),
        "cap_day": STREAK_CAP_DAY,
    }


# ─────────────────────────── winners ticker ────────────────────────
async def record_game_win(db, user: dict, game_type: str, prize: dict) -> None:
    """Record a real win (points>0 or coupon) for the live ticker."""
    kind = (prize or {}).get("kind")
    pts = int((prize or {}).get("points") or 0)
    if kind not in ("points", "coupon"):
        return
    if kind == "points" and pts <= 0:
        return
    try:
        await db.game_wins.insert_one({
            "user_id": user.get("user_id"),
            "display_name": _display_name(user),
            "game": game_type,
            "prize_label": (prize or {}).get("label") or "a prize",
            "prize_points": pts,
            "created_at": _now(),
        })
    except Exception:
        pass


_SAMPLE_NAMES = ["Sara A.", "Omar K.", "Layla M.", "Yousef R.", "Aisha B.",
                 "Khalid T.", "Mariam S.", "Hassan D.", "Noor F.", "Zayd N."]
_SAMPLE_WINS = [
    ("spin_win", "250 pts", 250), ("scratch_win", "500 pts", 500),
    ("lucky_dice", "Free meal for 8", 0), ("spin_win", "100 pts", 100),
    ("scratch_win", "1000 pts", 1000), ("spin_win", "JACKPOT", 5000),
    ("scratch_win", "FREE KARAK", 0), ("spin_win", "500 pts", 500),
]


def _win_view(w: dict, sample: bool = False) -> dict:
    return {"display_name": w["display_name"], "game": w["game"],
            "game_label": GAME_LABELS.get(w["game"], "Play & Win"),
            "prize_label": w["prize_label"],
            "prize_points": int(w.get("prize_points") or 0),
            "created_at": (w["created_at"].isoformat()
                           if isinstance(w.get("created_at"), datetime)
                           else w.get("created_at")),
            "sample": sample}


@router.get("/recent-wins")
async def recent_wins(request: Request, limit: int = 20,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    limit = max(1, min(40, int(limit)))
    items: list[dict] = []
    async for w in db.game_wins.find({}).sort("created_at", -1).limit(limit):
        items.append(_win_view(w))
    if len(items) < TICKER_MIN_ITEMS:
        rnd = random.Random(_day())          # stable within the day
        pool = list(zip(_SAMPLE_NAMES, _SAMPLE_WINS))
        rnd.shuffle(pool)
        need = TICKER_MIN_ITEMS - len(items)
        base = _now()
        for i in range(need):
            name, (game, label, pts) = pool[i % len(pool)]
            items.append(_win_view({
                "display_name": name, "game": game, "prize_label": label,
                "prize_points": pts,
                "created_at": base - timedelta(minutes=7 * (i + 1) + rnd.randint(0, 5)),
            }, sample=True))
    return {"items": items}


__all__ = ["router", "seed_game_rewards", "touch_streak",
           "record_game_win", "bonus_spins_today"]
