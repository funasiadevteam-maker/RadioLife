"""Phase 5 — streak tracking + low-skip bonus tracking."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from services.bigcoin import award

logger = logging.getLogger("bigfm.streaks")

# Day-streak BC rewards
STREAK_DAILY_BC = 10
STREAK_MILESTONES = {7: 50, 14: 100, 30: 250, 60: 500, 100: 1000}


def _today_str(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


async def touch_streak(db, user_id: str,
                        now: Optional[datetime] = None) -> Optional[dict]:
    """Idempotent. Called on any authed API hit. If today is a new day vs
    last_login_date, increment streak (or reset if gap > 1) and award BC.

    Returns the new streak state or None if same-day (no-op)."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    today_str = today.isoformat()
    state = await db.user_streaks.find_one({"user_id": user_id}) or {}
    last_str = state.get("last_login_date")
    if last_str == today_str:
        return None  # already touched today
    cur_streak = int(state.get("current_streak_days") or 0)
    longest = int(state.get("longest_streak_days") or 0)
    if last_str:
        try:
            last_date = date.fromisoformat(last_str)
            gap = (today - last_date).days
        except Exception:
            gap = 99
        new_streak = cur_streak + 1 if gap == 1 else 1
    else:
        new_streak = 1
    longest = max(longest, new_streak)
    await db.user_streaks.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id, "current_streak_days": new_streak,
            "longest_streak_days": longest, "last_login_date": today_str,
            "updated_at": now,
        }},
        upsert=True,
    )
    # Always award the daily BC
    await award(db, user_id, STREAK_DAILY_BC, "streak",
                  metadata={"streak_days": new_streak})
    # Milestone bonus?
    milestone_award = None
    if new_streak in STREAK_MILESTONES:
        already = state.get("last_milestone_awarded") or 0
        if already < new_streak:
            bonus = STREAK_MILESTONES[new_streak]
            await award(db, user_id, bonus, "streak_milestone",
                          metadata={"streak_days": new_streak})
            await db.user_streaks.update_one(
                {"user_id": user_id},
                {"$set": {"last_milestone_awarded": new_streak}},
            )
            milestone_award = {"days": new_streak, "bonus": bonus}
    return {
        "streak_days": new_streak, "longest_streak_days": longest,
        "milestone_award": milestone_award,
    }


# ---------------------------------------------------------------
# Low-skip bonus: track consecutive non-skip in a tiny per-session counter
async def increment_consecutive_play(db, user_id: str, session_id: str) -> int:
    """Called on play_start. Returns the new consecutive count."""
    res = await db.radio_sessions.find_one_and_update(
        {"_id": session_id},
        {"$inc": {"consecutive_no_skip": 1}},
        return_document=True,
        projection={"consecutive_no_skip": 1, "_id": 0},
    )
    return int((res or {}).get("consecutive_no_skip") or 0)


async def reset_consecutive_play(db, session_id: str) -> None:
    """Called on skip — wipes the counter."""
    await db.radio_sessions.update_one(
        {"_id": session_id},
        {"$set": {"consecutive_no_skip": 0}},
    )
