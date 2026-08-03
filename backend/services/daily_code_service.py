"""Phase AD.8 — Daily Code Claim.

A rotating 6-character code shown inside the Now Playing surface.  User
taps → earns points × streak multiplier.

Streak logic
------------
- If user claimed yesterday → increment streak_days.
- Else reset to 1.
- Multipliers: 1x @ 1d, 1.2x @ 3d, 1.5x @ 7d, 2x @ 14+d (capped 2x).
- One claim per user per code (unique index on user_id+daily_code_id).

Codes rotate every UTC day.  A scheduler generates tomorrow's code at
00:00 UTC if not already seeded by admin.  Claims are FREE (no
advertiser billing — this is a retention lever, not a paid surface),
but the daily_codes.sponsored_by_advertiser_id column allows optional
future paid daily codes without a migration.
"""
from __future__ import annotations

import asyncio
import logging
import random
import secrets
import string
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional

from services.points_service import PointsService

logger = logging.getLogger("bigfm.ad8")


CODE_LEN                    = 6
CODE_ALPHABET          = string.ascii_uppercase + string.digits
DEFAULT_REWARD_PTS = 50
# Streak multiplier ladder — descending scan.
STREAK_LADDER = [
    (14, 2.0),
    (7,    1.5),
    (3,    1.2),
    (1,    1.0),
]
MAX_MULTIPLIER = 2.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_key(dt: Optional[datetime] = None) -> str:
    d = dt or _now()
    return d.strftime("%Y-%m-%d")


def _yesterday_key() -> str:
    return (_now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _random_code() -> str:
    return "".join(random.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


def _multiplier(streak_days: int) -> float:
    for d, m in STREAK_LADDER:
        if streak_days >= d:
            return m
    return 1.0


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ─── Indexes ────────────────────────────────────────────────────
async def ensure_daily_code_indexes(db) -> None:
    try:
        await db.daily_codes.create_index("daily_code_id", unique=True)
        await db.daily_codes.create_index("date_effective", unique=True)
        await db.daily_codes.create_index([
            ("active_from", 1), ("active_until", 1)])
        await db.daily_code_claims.create_index(
            [("user_id", 1), ("daily_code_id", 1)], unique=True)
        await db.daily_code_claims.create_index("user_id")
        await db.daily_code_claims.create_index("claimed_at")
    except Exception as e:
        logger.warning("[ad8] index setup: %s", e)


# ─── CRUD / generation ──────────────────────────────────────────
async def _generate_code_for_date(db, *, date_key: str,
                                                                              points_reward: int = DEFAULT_REWARD_PTS,
                                                                              sponsored_by_advertiser_id:
                                                                                        Optional[str] = None,
                                                                              region_targeting:
                                                                                        Optional[List[str]] = None
                                                                              ) -> Dict[str, Any]:
    now = _now()
    y, m, d = [int(x) for x in date_key.split("-")]
    active_from    = datetime(y, m, d, 0, 0, 0, tzinfo=timezone.utc)
    active_until  = active_from + timedelta(days=1)
    code = _random_code()
    doc = {
        "_id":                                              f"dcd_{secrets.token_hex(7)}",
        "daily_code_id":                          f"dcd_{secrets.token_hex(7)}",
        "code":                                            code,
        "date_effective":                          date_key,
        "points_reward":                            int(points_reward),
        "active_from":                              active_from,
        "active_until":                            active_until,
        "region_targeting":                      list(region_targeting or []),
        "sponsored_by_advertiser_id":  sponsored_by_advertiser_id,
        "total_claims":                            0,
        "created_at":                                now,
    }
    doc["daily_code_id"] = doc["_id"]
    await db.daily_codes.insert_one(doc)
    return _serialize(doc)


async def ensure_today_code(db) -> Dict[str, Any]:
    """Idempotent — creates today's code if it doesn't exist."""
    key = _today_key()
    existing = await db.daily_codes.find_one({"date_effective": key})
    if existing:
        return _serialize(existing)
    try:
        return await _generate_code_for_date(db, date_key=key)
    except Exception:
        # Someone raced us — return whatever landed.
        existing = await db.daily_codes.find_one({"date_effective": key})
        return _serialize(existing) if existing else None


async def admin_create_code(db, *, date_key: str,
                                                            points_reward: int = DEFAULT_REWARD_PTS,
                                                            sponsored_by_advertiser_id:
                                                                      Optional[str] = None,
                                                            region_targeting:
                                                                      Optional[List[str]] = None
                                                            ) -> Dict[str, Any]:
    existing = await db.daily_codes.find_one({"date_effective": date_key})
    if existing:
        raise ValueError("code_already_exists_for_date")
    return await _generate_code_for_date(
        db, date_key=date_key,
        points_reward=points_reward,
        sponsored_by_advertiser_id=sponsored_by_advertiser_id,
        region_targeting=region_targeting)


async def admin_update_code(db, *, daily_code_id: str,
                                                            patch: Dict[str, Any]) -> Dict[str, Any]:
    doc = await db.daily_codes.find_one({"daily_code_id": daily_code_id})
    if not doc:
        raise ValueError("daily_code_not_found")
    # Only allow edit before the code's active window opens.
    if _now() >= doc["active_from"]:
        raise ValueError("code_already_active")
    allow = {"points_reward", "sponsored_by_advertiser_id",
                      "region_targeting"}
    sets = {k: v for k, v in patch.items() if k in allow and v is not None}
    if not sets:
        return _serialize(doc)
    await db.daily_codes.update_one(
        {"daily_code_id": daily_code_id}, {"$set": sets})
    return _serialize(await db.daily_codes.find_one(
        {"daily_code_id": daily_code_id}))


# ─── User-facing ───────────────────────────────────────────────
async def _current_code_row(db) -> Optional[dict]:
    now = _now()
    row = await db.daily_codes.find_one({
        "active_from":  {"$lte": now},
        "active_until": {"$gt":  now},
    })
    if not row:
        # Not seeded yet — create it lazily.
        await ensure_today_code(db)
        row = await db.daily_codes.find_one({
            "active_from":  {"$lte": now},
            "active_until": {"$gt":  now},
        })
    return row


async def current_code_view(db, *, user_id: Optional[str]) -> Dict[str, Any]:
    """Returns the current code MASKED for the user (they can see the
    code plaintext — this isn't a secret, it's a UX gate) + their
    claim status + current streak.  Streak counter reads yesterday's
    claim to preview the multiplier."""
    row = await _current_code_row(db)
    if not row:
        return {"code": None, "already_claimed": False, "streak_days": 0,
                      "next_multiplier": 1.0, "points_reward": DEFAULT_REWARD_PTS}
    result = {
        "daily_code_id":            row["daily_code_id"],
        "code":                              row["code"],
        "points_reward":            int(row.get("points_reward") or DEFAULT_REWARD_PTS),
        "active_until":              row["active_until"].isoformat()
                                                        if isinstance(row["active_until"], datetime)
                                                        else row["active_until"],
        "date_effective":          row.get("date_effective"),
        "sponsored_by_advertiser_id": row.get("sponsored_by_advertiser_id"),
    }
    already_claimed = False
    streak_days      = 0
    if user_id:
        claim = await db.daily_code_claims.find_one(
            {"user_id": user_id, "daily_code_id": row["daily_code_id"]})
        already_claimed = bool(claim)
        # Compute the streak the user would be on if they claim right now.
        streak_days = await _user_current_streak(db, user_id=user_id)
        if not already_claimed:
            # If they haven't claimed today, the NEXT claim will
            # increment (or reset to 1 if yesterday not claimed).
            streak_days = streak_days + 1 if streak_days > 0 else 1
    result["already_claimed"]  = already_claimed
    result["streak_days"]        = streak_days
    result["next_multiplier"]  = _multiplier(streak_days)
    result["estimated_points"] = int(result["points_reward"]
                                                                  * result["next_multiplier"])
    return result


async def _user_current_streak(db, *, user_id: str) -> int:
    """Walk backwards from today's claim (if any) counting consecutive
    daily claims.  Cheap for typical streaks (< 60 days)."""
    today = _now().date()
    yesterday = today - timedelta(days=1)
    # Start from the last claim date.
    latest = await db.daily_code_claims.find_one(
        {"user_id": user_id}, sort=[("claimed_at", -1)])
    if not latest:
        return 0
    last_dt = latest.get("claimed_at")
    if isinstance(last_dt, datetime):
        last_day = last_dt.date()
    else:
        try:    last_day = datetime.fromisoformat(str(last_dt)).date()
        except Exception:  return 0
    # If the last claim was NEITHER today NOR yesterday, the streak is
    # broken (0 — will reset to 1 on next claim).
    if last_day not in (today, yesterday):
        return 0
    streak = 0
    cursor_day = last_day
    while True:
        start = datetime.combine(cursor_day,
                                                              datetime.min.time(),
                                                              tzinfo=timezone.utc)
        end    = start + timedelta(days=1)
        c = await db.daily_code_claims.count_documents(
            {"user_id": user_id,
              "claimed_at": {"$gte": start, "$lt": end}})
        if c == 0:
            break
        streak += 1
        cursor_day = cursor_day - timedelta(days=1)
        if streak > 365:                    # sanity cap
            break
    return streak


async def claim(db, *, user_id: str, code: str) -> Dict[str, Any]:
    if not code or len(code.strip()) != CODE_LEN:
        raise ValueError("invalid_code_format")
    row = await _current_code_row(db)
    if not row:
        raise ValueError("no_active_code")
    if str(row["code"]).upper() != code.strip().upper():
        raise ValueError("wrong_code")
    # Idempotency + rate-limit: one claim per user per code.
    existing = await db.daily_code_claims.find_one(
        {"user_id": user_id, "daily_code_id": row["daily_code_id"]})
    if existing:
        raise ValueError("already_claimed")
    # Compute streak based on YESTERDAY.
    yesterday = (_now().date() - timedelta(days=1))
    y_start = datetime.combine(yesterday, datetime.min.time(),
                                                              tzinfo=timezone.utc)
    y_end    = y_start + timedelta(days=1)
    y_claim = await db.daily_code_claims.count_documents(
        {"user_id": user_id, "claimed_at": {"$gte": y_start, "$lt": y_end}})
    if y_claim > 0:
        # Continue streak — count all consecutive days ending yesterday.
        prev_streak = await _streak_ending(db, user_id=user_id,
                                                                                        end_date=yesterday)
        streak_days = prev_streak + 1
    else:
        streak_days = 1
    multiplier = _multiplier(streak_days)
    base_pts    = int(row.get("points_reward") or DEFAULT_REWARD_PTS)
    awarded    = int(round(base_pts * multiplier))
    now = _now()
    # Insert the claim row FIRST — unique index guards against races.
    claim_id = f"dcl_{secrets.token_hex(7)}"
    try:
        await db.daily_code_claims.insert_one({
            "_id":                          claim_id,
            "claim_id":                claim_id,
            "user_id":                  user_id,
            "daily_code_id":      row["daily_code_id"],
            "date_effective":  row.get("date_effective"),
            "claimed_at":          now,
            "points_awarded":  awarded,
            "streak_days":        streak_days,
            "streak_multiplier": multiplier,
        })
    except Exception:
        raise ValueError("already_claimed")
    # Award points via the F-1 unified ledger.
    try:
        pts = PointsService(db)
        await pts.award(
            user_id=user_id,
            source="daily_code_claim",
            source_id=claim_id,
            delta=awarded,
            metadata={"daily_code_id":  row["daily_code_id"],
                                "streak_days":      streak_days,
                                "streak_multiplier": multiplier},
            idempotency_key=f"daily_code:{claim_id}",
            enforce_caps=False)
    except Exception as e:
        logger.warning("[ad8] points award failed: %s", e)
    # Roll up on the code row.
    await db.daily_codes.update_one(
        {"daily_code_id": row["daily_code_id"]},
        {"$inc": {"total_claims": 1}})
    return {
        "ok":                              True,
        "claim_id":                  claim_id,
        "points_awarded":      awarded,
        "streak_days":            streak_days,
        "streak_multiplier": multiplier,
    }


async def _streak_ending(db, *, user_id: str, end_date: date) -> int:
    """Count consecutive daily claims ending on `end_date`."""
    streak = 0
    cursor_day = end_date
    while True:
        start = datetime.combine(cursor_day, datetime.min.time(),
                                                              tzinfo=timezone.utc)
        end    = start + timedelta(days=1)
        c = await db.daily_code_claims.count_documents(
            {"user_id": user_id,
              "claimed_at": {"$gte": start, "$lt": end}})
        if c == 0:
            break
        streak += 1
        cursor_day = cursor_day - timedelta(days=1)
        if streak > 365:
            break
    return streak


# ─── History ────────────────────────────────────────────────────
async def user_history(db, *, user_id: str, limit: int = 30
                                              ) -> Dict[str, Any]:
    rows = []
    async for c in db.daily_code_claims.find(
                {"user_id": user_id}).sort("claimed_at", -1).limit(limit):
        rows.append({
            "claim_id":                  c["claim_id"],
            "daily_code_id":      c["daily_code_id"],
            "claimed_at":          c["claimed_at"].isoformat()
                                                if isinstance(c["claimed_at"], datetime)
                                                else c["claimed_at"],
            "points_awarded":  int(c.get("points_awarded") or 0),
            "streak_days":        int(c.get("streak_days") or 0),
            "streak_multiplier": float(c.get("streak_multiplier") or 1.0),
        })
    # Aggregate lifetime stats.
    tot_pts = 0
    best_streak = 0
    tot_claims = 0
    async for c in db.daily_code_claims.find({"user_id": user_id}):
        tot_pts += int(c.get("points_awarded") or 0)
        best_streak = max(best_streak, int(c.get("streak_days") or 0))
        tot_claims += 1
    current_streak = await _user_current_streak(db, user_id=user_id)
    return {
        "items":                    rows,
        "count":                    len(rows),
        "totals": {
            "lifetime_points":  tot_pts,
            "total_claims":      tot_claims,
            "best_streak":        best_streak,
            "current_streak":  current_streak,
        },
    }


# ─── Scheduler ──────────────────────────────────────────────────
def start_scheduler(app, db, *, poll_interval_sec: int = 3600) -> None:
    """Every hour, ensures TODAY's code exists.  Effectively midnight-
    granular after ~1h drift from a boot mid-day.  Idempotent."""

    async def _loop():
        await asyncio.sleep(30)
        while True:
            try:
                await ensure_today_code(db)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[ad8] scheduler tick failed: %s", e)
            await asyncio.sleep(poll_interval_sec)

    existing = getattr(app.state, "daily_code_scheduler", None)
    if existing and not existing.done():
        existing.cancel()
    app.state.daily_code_scheduler = asyncio.create_task(_loop())
    logger.info("[ad8] scheduler started (poll=%ds)", poll_interval_sec)


__all__ = [
    "ensure_daily_code_indexes",
    "ensure_today_code",
    "admin_create_code",
    "admin_update_code",
    "current_code_view",
    "claim",
    "user_history",
    "start_scheduler",
    "DEFAULT_REWARD_PTS",
    "CODE_LEN",
    "STREAK_LADDER",
]
