"""Phase 8b — Milestone auto-unlock engine.

Listens to existing platform signals and grants `user_game_unlocks`
rows automatically.  Two modes:

  • Real-time hooks — called inline from `routes/bigcoin.py` (heartbeat,
    referrals), `routes/ads_public.py` (ad_save), and
    `services/lobbies.py` (lobby join).
  • Periodic sweep — `sweep_listening_unlocks(db)` runs every 60s from
    the FastAPI lifespan and checks daily / weekly / streak buckets.

Idempotency: a unique compound index on
`user_game_unlocks(user_id, rule_id, period_bucket)` ensures the same
listener cannot earn the same unlock twice in the same window.
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.games_v2.unlock_engine")


# ---------------------------------------------------------------------
TRIGGER_TYPES = {
    "listening_minutes_daily",
    "listening_minutes_weekly",
    "listening_streak_days",
    "lobby_join",
    "ad_save",
    "referral_completed",
    "podcast_completed",        # SCAFFOLD — fires nothing until podcast system lands
    "commute_completed",        # SCAFFOLD — fires nothing until Phase 9 (Maps)
}

PERIODS = {"daily", "weekly", "alltime"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _period_bucket(period: str, ts: datetime) -> str:
    """Deterministic bucket key for idempotency."""
    if period == "daily":
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%d")
    if period == "weekly":
        iso = ts.astimezone(timezone.utc).isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return "alltime"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# ---------------------------------------------------------------------
async def ensure_unlock_engine_indexes(db):
    await db.unlock_rules.create_index([("rule_id", 1)], unique=True)
    await db.unlock_rules.create_index([("active", 1), ("trigger_type", 1)])
    # CRITICAL: idempotency guard
    await db.user_game_unlocks.create_index(
        [("user_id", 1), ("rule_id", 1), ("period_bucket", 1)],
        unique=True, sparse=True,
        name="unique_user_rule_period",
    )


# ---------------------------------------------------------------------
DEFAULT_RULES = [
    {"rule_id": "rule_listen_15m", "trigger_type": "listening_minutes_daily",
      "threshold": 15, "period": "daily",
      "target_pool": ["cmp_house_spin"],
      "unlock_expires_in_hours": 24, "active": True,
      "title": "15-min listen unlock",
      "description": "Listen 15 min in a day → free Daily Spin"},
    {"rule_id": "rule_listen_30m", "trigger_type": "listening_minutes_daily",
      "threshold": 30, "period": "daily",
      "target_pool": ["cmp_house_trivia"],
      "unlock_expires_in_hours": 24, "active": True,
      "title": "30-min listen unlock",
      "description": "Listen 30 min in a day → free Music Trivia"},
    {"rule_id": "rule_listen_60m", "trigger_type": "listening_minutes_daily",
      "threshold": 60, "period": "daily",
      "target_pool": ["cmp_house_lyric"],
      "unlock_expires_in_hours": 24, "active": True,
      "title": "60-min listen unlock",
      "description": "Listen 60 min in a day → free Lyric Hunt"},
    {"rule_id": "rule_listen_3h_week", "trigger_type": "listening_minutes_weekly",
      "threshold": 180, "period": "weekly",
      "target_pool": ["cmp_house_spin", "cmp_house_trivia", "cmp_house_lyric"],
      "unlock_expires_in_hours": 48, "active": True,
      "title": "3-hour weekly listener",
      "description": "Listen 3+ hours a week → bonus play of any house game"},
    {"rule_id": "rule_streak_5", "trigger_type": "listening_streak_days",
      "threshold": 5, "period": "alltime",
      "target_pool": ["cmp_house_spin", "cmp_house_trivia", "cmp_house_lyric"],
      "unlock_expires_in_hours": 72, "active": True,
      "title": "5-day streak",
      "description": "Listen 5 days in a row → loyalty bonus play"},
    {"rule_id": "rule_lobby_join", "trigger_type": "lobby_join",
      "threshold": 1, "period": "daily",
      "target_pool": ["cmp_house_spin"],
      "unlock_expires_in_hours": 24, "active": True,
      "title": "Lobby joiner",
      "description": "Join a lobby → bonus spin"},
    {"rule_id": "rule_ad_save", "trigger_type": "ad_save",
      "threshold": 1, "period": "daily",
      "target_pool": ["cmp_house_trivia"],
      "unlock_expires_in_hours": 24, "active": True,
      "title": "Coupon clipper",
      "description": "Save your first coupon today → bonus trivia"},
    {"rule_id": "rule_referral", "trigger_type": "referral_completed",
      "threshold": 1, "period": "alltime",
      "target_pool": ["cmp_house_lyric", "cmp_house_spin"],
      "unlock_expires_in_hours": 168, "active": True,
      "title": "Referrer reward",
      "description": "Bring a friend → exclusive play"},
    # ---- SCAFFOLDS (don't fire in 8b) ------------------------------
    {"rule_id": "rule_podcast_completed", "trigger_type": "podcast_completed",
      "threshold": 1, "period": "daily",
      "target_pool": ["cmp_house_spin"],
      "unlock_expires_in_hours": 24, "active": False,
      "title": "[Scaffold] Podcast completed",
      "description": "TODO Phase 8+: tied to a future podcast pipeline"},
    {"rule_id": "rule_commute_completed", "trigger_type": "commute_completed",
      "threshold": 1, "period": "daily",
      "target_pool": ["cmp_house_spin"],
      "unlock_expires_in_hours": 24, "active": False,
      "title": "[Scaffold] Commute completed",
      "description": "TODO Phase 9 (Maps): fires when commute session ends"},
]


async def seed_unlock_rules(db) -> dict:
    created = 0
    for r in DEFAULT_RULES:
        res = await db.unlock_rules.update_one(
            {"rule_id": r["rule_id"]},
            {"$setOnInsert": {**r, "created_at": _now()}},
            upsert=True,
        )
        if res.upserted_id:
            created += 1
    return {"unlock_rules_created": created,
            "unlock_rules_total": len(DEFAULT_RULES)}


# ---------------------------------------------------------------------
async def _pick_target_campaign(db, rule: dict, user_id: str) -> Optional[str]:
    """Resolve target_campaign_id / target_template_id / target_pool to a
    single campaign the user hasn't already played to exhaustion."""
    if rule.get("target_campaign_id"):
        return rule["target_campaign_id"]
    pool = rule.get("target_pool") or []
    if not pool and rule.get("target_template_id"):
        # Pick a random active campaign matching the template
        candidates = await db.game_campaigns.find(
            {"template_id": rule["target_template_id"],
             "status": "active"},
            {"campaign_id": 1, "_id": 0},
        ).to_list(50)
        pool = [c["campaign_id"] for c in candidates]
    if not pool:
        return None
    # Prefer campaigns the user hasn't won-yet today
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    played = set()
    async for s in db.game_sessions.find(
            {"user_id": user_id,
             "campaign_id": {"$in": pool},
             "started_at": {"$gte": today_start}},
            {"campaign_id": 1, "_id": 0}):
        played.add(s["campaign_id"])
    fresh = [c for c in pool if c not in played]
    return random.choice(fresh) if fresh else random.choice(pool)


async def _award_unlock(db, *, rule: dict, user_id: str,
                            campaign_id: str, period_bucket: str,
                            metadata: Optional[dict] = None) -> Optional[dict]:
    """Idempotent insert.  Returns the unlock doc if created, None if
    the user already had it for this period_bucket."""
    now = _now()
    unlock_id = _new_id("ulk")
    expires = now + timedelta(hours=int(rule.get("unlock_expires_in_hours") or 24))
    doc = {
        "_id": unlock_id, "unlock_id": unlock_id,
        "user_id": user_id, "campaign_id": campaign_id,
        "rule_id": rule["rule_id"],
        "period_bucket": period_bucket,
        "unlock_reason": rule["trigger_type"],
        "unlocked_at": now, "expires_at": expires,
        "played": False, "played_at": None,
        "metadata": metadata or {},
    }
    try:
        await db.user_game_unlocks.insert_one(doc)
    except Exception as e:
        # DuplicateKeyError → already unlocked this period; that's fine
        if "duplicate" in str(e).lower() or "e11000" in str(e).lower():
            return None
        raise
    await db.game_analytics_events.insert_one({
        "_id": _new_id("evt"), "campaign_id": campaign_id,
        "user_id": user_id, "event_type": "unlock",
        "source_context_json": {"rule_id": rule["rule_id"],
                                  "trigger_type": rule["trigger_type"]},
        "metadata_json": {"period_bucket": period_bucket,
                            "unlock_id": unlock_id},
        "ts": now,
    })
    return doc


# ---------------------------------------------------------------------
# Real-time hooks
# ---------------------------------------------------------------------
async def on_lobby_join(db, user_id: str, lobby_id: str) -> Optional[dict]:
    rules = await db.unlock_rules.find(
        {"trigger_type": "lobby_join", "active": True}).to_list(20)
    awarded = None
    for rule in rules:
        bucket = _period_bucket(rule["period"], _now())
        cid = await _pick_target_campaign(db, rule, user_id)
        if not cid: continue
        awarded = await _award_unlock(
            db, rule=rule, user_id=user_id, campaign_id=cid,
            period_bucket=bucket,
            metadata={"lobby_id": lobby_id}) or awarded
    return awarded


async def on_ad_save(db, user_id: str, ad_id: Optional[str] = None) -> Optional[dict]:
    rules = await db.unlock_rules.find(
        {"trigger_type": "ad_save", "active": True}).to_list(20)
    awarded = None
    for rule in rules:
        bucket = _period_bucket(rule["period"], _now())
        cid = await _pick_target_campaign(db, rule, user_id)
        if not cid: continue
        awarded = await _award_unlock(
            db, rule=rule, user_id=user_id, campaign_id=cid,
            period_bucket=bucket,
            metadata={"ad_id": ad_id}) or awarded
    return awarded


async def on_referral_completed(db, referrer_user_id: str,
                                       invitee_user_id: str) -> Optional[dict]:
    rules = await db.unlock_rules.find(
        {"trigger_type": "referral_completed", "active": True}).to_list(20)
    awarded = None
    for rule in rules:
        bucket = _period_bucket(rule["period"], _now())
        cid = await _pick_target_campaign(db, rule, referrer_user_id)
        if not cid: continue
        awarded = await _award_unlock(
            db, rule=rule, user_id=referrer_user_id,
            campaign_id=cid, period_bucket=bucket,
            metadata={"invitee_user_id": invitee_user_id}) or awarded
    return awarded


# ---------------------------------------------------------------------
# Listening-minute checks (called from heartbeat + sweep)
# ---------------------------------------------------------------------
async def _today_listening_minutes(db, user_id: str) -> int:
    """Approximate: count bigcoin_transactions of type 'heartbeat' today
    × 1 min each.  Mirrors what Phase 5's `listening_heartbeat` does."""
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    n = await db.bigcoin_transactions.count_documents({
        "user_id": user_id, "reason": "heartbeat",
        "created_at": {"$gte": today_start},
    })
    return n


async def _this_week_listening_minutes(db, user_id: str) -> int:
    iso = _now().isocalendar()
    week_start = datetime.fromisocalendar(iso.year, iso.week, 1)
    week_start = week_start.replace(tzinfo=timezone.utc)
    n = await db.bigcoin_transactions.count_documents({
        "user_id": user_id, "reason": "heartbeat",
        "created_at": {"$gte": week_start},
    })
    return n


async def _current_listening_streak_days(db, user_id: str) -> int:
    """Count consecutive UTC days with at least one heartbeat tx, ending
    today (or yesterday if no tx today yet)."""
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    streak = 0
    # Walk back day by day
    cursor = today
    for _ in range(60):
        day_end = cursor + timedelta(days=1)
        n = await db.bigcoin_transactions.count_documents({
            "user_id": user_id, "reason": "heartbeat",
            "created_at": {"$gte": cursor, "$lt": day_end},
        })
        if n > 0:
            streak += 1
            cursor -= timedelta(days=1)
            continue
        # First miss with non-today → break
        if cursor == today:
            cursor -= timedelta(days=1)
            continue
        break
    return streak


async def check_listening_unlocks(db, user_id: str) -> list[dict]:
    """Called on every heartbeat by `routes/bigcoin.post_heartbeat`.
    Re-evaluates daily / weekly / streak rules and awards unlocks
    when thresholds are crossed.  Idempotent."""
    awarded = []
    daily_rules = await db.unlock_rules.find(
        {"trigger_type": "listening_minutes_daily", "active": True}
    ).sort("threshold", 1).to_list(20)
    if daily_rules:
        minutes_today = await _today_listening_minutes(db, user_id)
        bucket = _period_bucket("daily", _now())
        for rule in daily_rules:
            if minutes_today < int(rule["threshold"]):
                break
            cid = await _pick_target_campaign(db, rule, user_id)
            if not cid: continue
            doc = await _award_unlock(
                db, rule=rule, user_id=user_id, campaign_id=cid,
                period_bucket=bucket,
                metadata={"minutes": minutes_today})
            if doc: awarded.append(doc)

    weekly_rules = await db.unlock_rules.find(
        {"trigger_type": "listening_minutes_weekly", "active": True}
    ).sort("threshold", 1).to_list(20)
    if weekly_rules:
        mins_week = await _this_week_listening_minutes(db, user_id)
        bucket = _period_bucket("weekly", _now())
        for rule in weekly_rules:
            if mins_week < int(rule["threshold"]):
                break
            cid = await _pick_target_campaign(db, rule, user_id)
            if not cid: continue
            doc = await _award_unlock(
                db, rule=rule, user_id=user_id, campaign_id=cid,
                period_bucket=bucket,
                metadata={"week_minutes": mins_week})
            if doc: awarded.append(doc)

    streak_rules = await db.unlock_rules.find(
        {"trigger_type": "listening_streak_days", "active": True}
    ).sort("threshold", 1).to_list(20)
    if streak_rules:
        streak = await _current_listening_streak_days(db, user_id)
        for rule in streak_rules:
            if streak < int(rule["threshold"]):
                break
            # Streak unlocks bucket by (streak_length) — once per streak length
            bucket = f"streak-{streak}"
            cid = await _pick_target_campaign(db, rule, user_id)
            if not cid: continue
            doc = await _award_unlock(
                db, rule=rule, user_id=user_id, campaign_id=cid,
                period_bucket=bucket,
                metadata={"streak_days": streak})
            if doc: awarded.append(doc)
    return awarded


# ---------------------------------------------------------------------
# Periodic sweep — runs from the FastAPI lifespan task every 60s.
# Most listening-unlocks fire in real-time via the heartbeat hook, but
# this catches users who hit a threshold via offline accrual.
# ---------------------------------------------------------------------
async def sweep_listening_unlocks(db, *, batch_limit: int = 200) -> dict:
    """Walk recently active users (≥1 heartbeat in the last 2 minutes)
    and re-check listening rules.  Idempotency keeps re-runs cheap."""
    cutoff = _now() - timedelta(minutes=2)
    recent_uids = set()
    async for d in db.bigcoin_transactions.find(
            {"reason": "heartbeat", "created_at": {"$gte": cutoff}},
            {"user_id": 1, "_id": 0}).limit(batch_limit):
        recent_uids.add(d["user_id"])
    awarded = 0
    for uid in recent_uids:
        out = await check_listening_unlocks(db, uid)
        awarded += len(out)
    return {"users_checked": len(recent_uids), "unlocks_awarded": awarded}


async def background_unlock_sweep_task(app):
    """Runs forever from the FastAPI lifespan."""
    db = app.state.db
    while True:
        try:
            await sweep_listening_unlocks(db)
        except Exception as e:
            logger.warning(f"unlock sweep error: {e}")
        await asyncio.sleep(60)


__all__ = [
    "TRIGGER_TYPES", "DEFAULT_RULES",
    "ensure_unlock_engine_indexes", "seed_unlock_rules",
    "on_lobby_join", "on_ad_save", "on_referral_completed",
    "check_listening_unlocks", "sweep_listening_unlocks",
    "background_unlock_sweep_task",
    "_period_bucket", "_pick_target_campaign", "_award_unlock",
]
