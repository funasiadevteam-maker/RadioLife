"""Phase 5 — BigCoin core service.

Server-authoritative: every earn/spend goes through one of these helpers
which atomically updates `users.bigcoin_balance`, `users.bigcoin_lifetime_earned`,
writes a `bigcoin_transactions` doc, recomputes `bigcoin_tier`, and stamps
a `milestone_pending` flag for the RJ script pipeline to pick up.

Anti-fraud: callers MUST validate the trigger condition before calling
`award()`. This module trusts the caller — it only enforces idempotency
where applicable (onboarding_awarded flag, daily caps via the heartbeat
collection, etc.).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.bigcoin")

# Tier thresholds (lifetime BC earned)
TIERS = [
    ("platinum", 10000),
    ("gold",     2500),
    ("silver",   500),
    ("bronze",   0),
]

# Milestone thresholds (lifetime BC earned)
MILESTONES = [100, 500, 1000, 5000, 10000, 25000, 50000]


def compute_tier(lifetime: int) -> str:
    for name, threshold in TIERS:
        if lifetime >= threshold:
            return name
    return "bronze"


def crossed_milestone(prev_lifetime: int, new_lifetime: int) -> Optional[int]:
    """Returns the milestone crossed (if any) between prev and new lifetime."""
    for m in MILESTONES:
        if prev_lifetime < m <= new_lifetime:
            return m
    return None


# ---------------------------------------------------------------
async def ensure_bigcoin_indexes(db) -> None:
    await db.bigcoin_transactions.create_index([("user_id", 1), ("created_at", -1)])
    await db.bigcoin_transactions.create_index([("source", 1), ("created_at", -1)])
    await db.bigcoin_rewards.create_index("active")
    await db.bigcoin_redemptions.create_index([("user_id", 1), ("redeemed_at", -1)])
    await db.user_streaks.create_index("user_id", unique=True)
    await db.user_badges.create_index([("user_id", 1), ("badge_id", 1)], unique=True)
    await db.user_badges.create_index([("user_id", 1), ("unlocked_at", -1)])
    await db.badges.create_index("slug", unique=True)
    await db.listening_heartbeats.create_index([("user_id", 1), ("hour_bucket", 1)], unique=True)
    await db.referrals.create_index([("referrer_user_id", 1), ("referred_at", -1)])
    await db.referrals.create_index("referred_user_id", sparse=True)
    await db.referrals.create_index("referrer_code")
    await db.games.create_index("slug", unique=True)
    await db.game_sessions.create_index([("user_id", 1), ("played_at", -1)])
    await db.game_sessions.create_index([("game_id", 1), ("played_at", -1)])
    await db.lyric_puzzles.create_index("active")


# ---------------------------------------------------------------
async def award(
    db, user_id: str, amount: int, source: str,
    metadata: Optional[dict] = None,
    note: Optional[str] = None,
    skip_points_mirror: bool = False,
) -> dict:
    """Credit `amount` BC to user_id. Atomic. Returns {balance_after,
    lifetime_after, tier, milestone_crossed (or None)}. Amount MUST be > 0.

    Phase F-1: pass `skip_points_mirror=True` when the caller is the
    new `PointsService` — it writes its own ledger row and we'd
    otherwise double-count.
    """
    assert amount > 0, "award amount must be positive"
    now = datetime.now(timezone.utc)
    # Atomic increment and read back
    updated = await db.users.find_one_and_update(
        {"user_id": user_id},
        {"$inc": {
            "bigcoin_balance": amount,
            "bigcoin_lifetime_earned": amount,
        }},
        return_document=True,
        projection={"bigcoin_balance": 1, "bigcoin_lifetime_earned": 1,
                     "bigcoin_tier": 1, "_id": 0},
    )
    if not updated:
        raise RuntimeError(f"user not found: {user_id}")
    new_balance = updated["bigcoin_balance"]
    new_lifetime = updated["bigcoin_lifetime_earned"]
    prev_lifetime = new_lifetime - amount
    new_tier = compute_tier(new_lifetime)
    old_tier = updated.get("bigcoin_tier") or "bronze"
    milestone = crossed_milestone(prev_lifetime, new_lifetime)
    update_set = {}
    if new_tier != old_tier:
        update_set["bigcoin_tier"] = new_tier
    if milestone:
        update_set["bigcoin_milestone_pending"] = milestone
    if update_set:
        await db.users.update_one({"user_id": user_id}, {"$set": update_set})
    await db.bigcoin_transactions.insert_one({
        "user_id": user_id, "type": "earn", "source": source,
        "amount": amount, "balance_after": new_balance,
        "metadata_json": metadata or {}, "note": note,
        "created_at": now,
    })
    # Phase F-1 — dual-write to the unified Points ledger.  This block
    # is intentionally non-fatal: if the mirror fails (e.g. during
    # backfill window) the legacy path still succeeds.  TODO Phase F-2:
    # once readers flip to the ledger, the bigcoin_transactions write
    # above can be removed and this becomes the only writer.
    if not skip_points_mirror:
        try:
            from services.points_service import PointsService
            await PointsService(db).award(
                user_id=user_id, source=source,
                source_id=(metadata or {}).get("source_id"),
                delta=int(amount),
                metadata={**(metadata or {}), "note": note,
                                  "legacy_path": "bigcoin.award"},
                mirror_only=True,
                balance_after_override=int(new_balance),
                created_at=now,
            )
        except Exception as e:
            logger.warning("[bigcoin.award] points-ledger mirror failed: %s", e)
    return {
        "balance_after": new_balance,
        "lifetime_after": new_lifetime,
        "tier": new_tier,
        "old_tier": old_tier,
        "tier_upgraded": new_tier != old_tier,
        "milestone_crossed": milestone,
    }


async def spend(
    db, user_id: str, amount: int, source: str,
    metadata: Optional[dict] = None,
    note: Optional[str] = None,
    skip_points_mirror: bool = False,
) -> dict:
    """Debit `amount` BC. Returns {balance_after} or raises ValueError if
    insufficient balance (atomically guarded)."""
    assert amount > 0
    now = datetime.now(timezone.utc)
    # Atomic conditional decrement
    res = await db.users.find_one_and_update(
        {"user_id": user_id, "bigcoin_balance": {"$gte": amount}},
        {"$inc": {"bigcoin_balance": -amount}},
        return_document=True,
        projection={"bigcoin_balance": 1, "_id": 0},
    )
    if not res:
        u = await db.users.find_one({"user_id": user_id}, {"bigcoin_balance": 1})
        cur = (u or {}).get("bigcoin_balance", 0)
        raise ValueError(f"insufficient balance: have {cur}, need {amount}")
    new_balance = res["bigcoin_balance"]
    await db.bigcoin_transactions.insert_one({
        "user_id": user_id, "type": "spend", "source": source,
        "amount": -amount, "balance_after": new_balance,
        "metadata_json": metadata or {}, "note": note,
        "created_at": now,
    })
    # Phase F-1 — mirror the spend into the unified Points ledger.
    # TODO Phase F-2: deprecate the bigcoin_transactions row above
    # once readers flip to points_ledger.
    if not skip_points_mirror:
        try:
            from services.points_service import PointsService
            await PointsService(db).award(
                user_id=user_id, source=source,
                source_id=(metadata or {}).get("source_id"),
                delta=-int(amount),
                metadata={**(metadata or {}), "note": note,
                                  "legacy_path": "bigcoin.spend"},
                mirror_only=True,
                balance_after_override=int(new_balance),
                created_at=now,
            )
        except Exception as e:
            logger.warning("[bigcoin.spend] points-ledger mirror failed: %s", e)
    return {"balance_after": new_balance}


async def adjust(
    db, user_id: str, delta: int, source: str = "admin_adjust",
    metadata: Optional[dict] = None, note: Optional[str] = None,
    skip_points_mirror: bool = False,
) -> dict:
    """Admin manual adjust — can be positive or negative. Doesn't affect
    lifetime_earned (intentional: lifetime is the trust metric)."""
    now = datetime.now(timezone.utc)
    if delta > 0:
        res = await db.users.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"bigcoin_balance": delta}},
            return_document=True, projection={"bigcoin_balance": 1, "_id": 0},
        )
    else:
        # Avoid going negative
        res = await db.users.find_one_and_update(
            {"user_id": user_id, "bigcoin_balance": {"$gte": -delta}},
            {"$inc": {"bigcoin_balance": delta}},
            return_document=True, projection={"bigcoin_balance": 1, "_id": 0},
        )
        if not res:
            raise ValueError("adjustment would go negative")
    new_balance = res["bigcoin_balance"]
    await db.bigcoin_transactions.insert_one({
        "user_id": user_id, "type": "adjust", "source": source,
        "amount": delta, "balance_after": new_balance,
        "metadata_json": metadata or {}, "note": note,
        "created_at": now,
    })
    # Phase F-1 — mirror admin adjust into the unified Points ledger.
    # TODO Phase F-2: deprecate the bigcoin_transactions row above.
    if not skip_points_mirror:
        try:
            from services.points_service import PointsService
            await PointsService(db).award(
                user_id=user_id, source=source,
                source_id=(metadata or {}).get("source_id"),
                delta=int(delta),
                metadata={**(metadata or {}), "note": note,
                                  "legacy_path": "bigcoin.adjust"},
                mirror_only=True,
                balance_after_override=int(new_balance),
                created_at=now,
            )
        except Exception as e:
            logger.warning("[bigcoin.adjust] points-ledger mirror failed: %s", e)
    return {"balance_after": new_balance}


# ---------------------------------------------------------------
# Listening heartbeat earn — server-side validated
DAILY_LISTEN_CAP_BC = 240


async def listening_heartbeat(
    db, user_id: str, session_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Server-side validated +1 BC for the current minute.

    Validation pipeline:
      1. The user must have a play_start log within the last 90 seconds
         (proves audio is actually playing client-side).
      2. The same minute-bucket cannot be credited twice (idempotency).
      3. Daily cap of 240 BC enforced across hour buckets.

    Returns {credited, amount, daily_total, reason}.
    """
    now = now or datetime.now(timezone.utc)
    # Minute bucket as idempotency key
    minute_bucket = now.strftime("%Y%m%d%H%M")
    hour_bucket = now.strftime("%Y%m%d%H")
    # 1. Recent play_start check — guard against AFK
    cutoff = now - timedelta(seconds=90)
    recent = await db.playback_logs.find_one(
        {"user_id": user_id, "event": "play_start", "timestamp": {"$gte": cutoff}},
        {"_id": 1, "timestamp": 1},
    )
    if not recent:
        return {"credited": False, "amount": 0, "reason": "no_recent_play"}
    # 2. Idempotency on minute bucket
    minute_doc = await db.listening_heartbeat_minutes.find_one(
        {"_id": f"{user_id}|{minute_bucket}"}, {"_id": 1},
    )
    if minute_doc:
        return {"credited": False, "amount": 0, "reason": "duplicate_minute"}
    # 3. Daily cap
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {"user_id": user_id,
                     "hour_bucket": {"$gte": day_start.strftime("%Y%m%d00"),
                                     "$lte": now.strftime("%Y%m%d%H")}}},
        {"$group": {"_id": None, "total": {"$sum": "$minutes_credited"}}},
    ]
    daily_doc = await db.listening_heartbeats.aggregate(pipeline).to_list(1)
    daily_total = daily_doc[0]["total"] if daily_doc else 0
    if daily_total >= DAILY_LISTEN_CAP_BC:
        return {"credited": False, "amount": 0, "daily_total": daily_total,
                "reason": "daily_cap_reached"}
    # Write the minute lock first (insert_one will throw on duplicate)
    try:
        await db.listening_heartbeat_minutes.insert_one({
            "_id": f"{user_id}|{minute_bucket}",
            "user_id": user_id, "minute_bucket": minute_bucket,
            "session_id": session_id, "created_at": now,
            # Expire after 24h to keep the collection small
        })
    except Exception:
        return {"credited": False, "amount": 0, "reason": "duplicate_minute"}
    # Increment hour bucket counter
    await db.listening_heartbeats.update_one(
        {"user_id": user_id, "hour_bucket": hour_bucket},
        {"$inc": {"minutes_credited": 1},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    # Award
    result = await award(db, user_id, 1, "listening",
                          metadata={"session_id": session_id,
                                    "minute_bucket": minute_bucket})
    result["credited"] = True
    result["amount"] = 1
    result["daily_total"] = daily_total + 1
    # Phase 10a — Social Passport: emit bigcoin_heartbeat for badge engine.
    # Resolve current channel from the most recent play_start so geo /
    # genre badges can filter (Bollywood, hip-hop, etc).
    try:
        from services.badge_engine import evaluate as badge_evaluate
        ch_slug = (recent or {}).get("channel_slug")
        ch_genre = None
        if ch_slug:
            ch = await db.channels.find_one(
                {"slug": ch_slug}, {"genre": 1, "_id": 0})
            ch_genre = ((ch or {}).get("genre") or "").lower() or None
        # Resolve city via the user's last commute (if active)
        city = None
        cmt = await db.commute_sessions.find_one(
            {"user_id": user_id, "status": "active"},
            sort=[("started_at", -1)])
        if cmt:
            city = cmt.get("origin_city") or cmt.get("destination_city")
        await badge_evaluate(
            db, user_id, "bigcoin_heartbeat",
            {"minute_bucket": minute_bucket,
              "channel_slug": ch_slug,
              "channel_genre": ch_genre,
              "city": city,
              "hour": now.hour})
        # Phase K.2 — City stamps engine listens on the SAME signal.
        # Awards a stamp after STAMP_THRESHOLD_MIN cumulative minutes in
        # a supported city.  Silently skips unknown cities.
        if city:
            try:
                from services.city_stamps_engine import evaluate as cs_eval
                await cs_eval(db, user_id=user_id, city=city,
                                            minutes=1, channel_slug=ch_slug)
            except Exception:
                pass
    except Exception:
        pass
    return result


# ---------------------------------------------------------------
# Onboarding earn (one-time)
async def maybe_award_onboarding(db, user_id: str) -> dict:
    """Idempotent: awards 50 BC the first time a user finishes onboarding."""
    existing = await db.bigcoin_transactions.find_one(
        {"user_id": user_id, "source": "onboarding"}, {"_id": 1},
    )
    if existing:
        return {"awarded": False, "reason": "already_awarded"}
    res = await award(db, user_id, 50, "onboarding", note="Welcome to FUUSIC!")
    res["awarded"] = True
    return res


# ---------------------------------------------------------------
# Low-skip bonus — caller tracks consecutive non-skip in radio_sessions
async def maybe_award_low_skip(db, user_id: str, session_id: str,
                                consecutive: int) -> Optional[dict]:
    """Award 5 BC every 5 consecutive non-skipped songs."""
    if consecutive <= 0 or consecutive % 5 != 0:
        return None
    res = await award(db, user_id, 5, "low_skip_bonus",
                       metadata={"session_id": session_id, "consecutive": consecutive})
    return res


# ---------------------------------------------------------------
# Tier helpers
def tier_color(tier: str) -> str:
    return {
        "platinum": "#e5e4e2", "gold": "#fdb756",
        "silver": "#c0c0c0", "bronze": "#cd7f32",
    }.get(tier, "#cd7f32")


def tier_label(tier: str) -> str:
    return tier.capitalize()
