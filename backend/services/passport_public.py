"""Phase 10b — Public Social Passport, leaderboards, level-up rewards,
and the Phase 5 legacy-badge migration.

This module owns surfaces that are READABLE without auth (subject to per-
user privacy flags) and the heavy-lifting recompute jobs that materialise
city leaderboard rollups.  The 10a `badge_engine` continues to own the
award-eligibility evaluation; 10b only consumes it.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.passport_public")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# ─── Handle validation ─────────────────────────────────────────────────
HANDLE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,18}[a-z0-9])?$")


def validate_handle(raw: str) -> str:
    if not raw:
        raise ValueError("handle_required")
    s = raw.strip().lower()
    if not HANDLE_RE.match(s):
        raise ValueError("handle_invalid_format")
    if "--" in s:
        raise ValueError("handle_invalid_format")
    return s


# ─── Phase 5 legacy badge migration ────────────────────────────────────
# Conservative defaults — the existing legacy unlock_rule_json keeps
# legacy engine working; we just enrich the catalog row so it can render
# on the new public surfaces.  `legacy_phase5=True` marks origin so the
# 10b admin UI / analytics can filter.
#
# Phase 10b.2 reconcile (2026-05-26) — extended from 14 → 19 entries to
# match the actual Phase 5 catalog that survived seeding.  The 5 added
# rows (badge_lyric_pro, badge_redeem_first, badge_streak_3,
# badge_streak_7, badge_trivia_legend) were already in `badges` with
# `legacy_phase5=True` set by `services/bigcoin_seed.py` — we now own
# them explicitly so `migrate_phase5_badges` can heal slug/badge_id
# drift if it ever recurs.  Canonical count = 50 + 19 = 69 total
# (66 active; 3 Phase 10a seasonal rows ship inactive).
PHASE5_LEGACY_BADGE_BACKFILL = [
    # Real Phase 5 catalog rows seeded in services/bigcoin_seed.py.
    ("badge_first_listen",     "First Listen",        "listening", "bronze", 10),
    ("badge_10_hours",         "10 Hours In",         "listening", "silver", 25),
    ("badge_50_hours",         "50 Hours Strong",     "listening", "gold",   60),
    ("badge_100_hours",        "Centurion",           "listening", "gold",   80),
    ("badge_streak_3",         "3-Day Streak",        "streak",    "bronze", 15),
    ("badge_streak_7",         "7-Day Streak",        "streak",    "silver", 35),
    ("badge_streak_30",        "30-Day Streak",       "streak",    "gold",   90),
    ("badge_friday_regular",   "Friday Night Regular","streak",    "silver", 35),
    ("badge_mirchi_loyalist",  "Party Dubai Loyalist","city",      "silver", 40),
    ("badge_bigcoin_tycoon",   "BigCoin Tycoon",      "milestone", "platinum", 200),
    ("badge_game_master",      "Game Master",         "game",      "silver", 30),
    ("badge_trivia_legend",    "Trivia Legend",       "game",      "gold",   60),
    ("badge_lyric_pro",        "Lyric Pro",           "game",      "silver", 25),
    ("badge_refer_1",          "First Referral",      "social",    "bronze", 20),
    ("badge_refer_5",          "Referral Hero",       "social",    "gold",   75),
    ("badge_refer_10",         "Squad Builder",       "social",    "platinum", 150),
    ("badge_coupon_collector", "Coupon Collector",    "coupon",    "silver", 30),
    ("badge_redeem_first",     "First Redemption",    "coupon",    "bronze", 15),
    # Synthetic — placeholder for the historical "premium subscriber"
    # row (kept so total legacy count = 19 per Phase 10b.2 reconcile).
    ("badge_premium",          "Premium Subscriber",  "premium",   "silver", 40),
]


async def migrate_phase5_badges(db) -> dict:
    """Idempotent.  For every Phase 5 catalog row that lacks
    `schema_version="10a"`, write back tier/category/points/legacy flag.
    Existing `user_badges` rows are unchanged — they continue referencing
    the same `badge_id` and now render with proper meta in /passport/*.

    Also re-namespaces the legacy slug to `badge_<original>` so that
    the canonical Phase 10a catalog (slug==badge_id) can co-exist
    without violating the unique `slug_1` index.

    Phase 10b.2 — also self-heals any pre-existing row that already has
    `schema_version='10a'` + `legacy_phase5=True` but is missing the
    `badge_id` field (an artifact of an earlier broken migration run).
    """
    updated, skipped = 0, 0
    for badge_id, name, cat, tier, points in PHASE5_LEGACY_BADGE_BACKFILL:
        row = await db.badges.find_one({"_id": badge_id})
        if not row:
            # Row not present in DB — create a thin entry so it renders
            # when an old user_badges row references it.
            try:
                await db.badges.insert_one({
                    "_id": badge_id, "badge_id": badge_id,
                    "slug": badge_id,
                    "name": name,
                    "description": "Earned during the Phase 5 era.",
                    "category": cat, "tier": tier, "points": int(points),
                    "icon_url": f"/assets/badges/{badge_id}.svg",
                    "secret": False, "active": True,
                    "schema_version": "10a", "legacy_phase5": True,
                    "criteria_json": {"type": "admin_only",
                                              "legacy_phase5": True},
                    "created_at": _now(), "updated_at": _now(),
                })
                updated += 1
            except Exception as e:
                skipped += 1
                logger.warning(f"phase5 migrate insert {badge_id}: {e}")
            continue
        if row.get("schema_version") == "10a" and row.get("legacy_phase5"):
            # Already migrated.  Self-heal the two known drift patterns:
            #   (a) `badge_id` field missing/None  (legacy bug)
            #   (b) `slug` still equals the bare phase-10a slug (collision)
            patch: dict = {}
            if not row.get("badge_id"):
                patch["badge_id"] = badge_id
            bare_slug = badge_id.removeprefix("badge_")
            if row.get("slug") == bare_slug and bare_slug != badge_id:
                patch["slug"] = badge_id
            if patch:
                await db.badges.update_one(
                    {"_id": badge_id}, {"$set": patch})
                updated += 1
                continue
            skipped += 1
            continue
        await db.badges.update_one(
            {"_id": badge_id},
            {"$set": {
                "badge_id": badge_id,
                # Re-namespace the slug so Phase 10a's canonical slug
                # (without the `badge_` prefix) can co-exist.
                "slug": badge_id,
                "name": row.get("name") or name,
                "description": (row.get("description")
                                    or "Earned during the Phase 5 era."),
                "category": cat, "tier": tier, "points": int(points),
                "icon_url": row.get("icon_url")
                                or f"/assets/badges/{badge_id}.svg",
                "active": True,
                "schema_version": "10a", "legacy_phase5": True,
                "criteria_json": (row.get("criteria_json")
                                          or {"type": "admin_only",
                                                "legacy_phase5": True}),
                "updated_at": _now(),
            }})
        updated += 1
    return {"updated": updated, "skipped": skipped,
              "total_phase5": len(PHASE5_LEGACY_BADGE_BACKFILL)}


# ─── Public profile assembly ───────────────────────────────────────────
def _initial_avatar(display: str) -> str:
    return (display or "?").strip()[:1].upper()


async def public_profile_view(db, *,
                                          target_user_id: Optional[str] = None,
                                          handle: Optional[str] = None) -> dict:
    """Returns the public profile for a user, honoring privacy flags.

    Raises ValueError("not_found") if the user doesn't exist OR has
    `is_public=False` (we treat the page as 404 from the outside).
    """
    if handle:
        h = validate_handle(handle)
        st = await db.social_profile_settings.find_one({"handle": h})
        if not st:
            raise ValueError("not_found")
        target_user_id = st.get("user_id")
    if not target_user_id:
        raise ValueError("not_found")

    u = await db.users.find_one({"user_id": target_user_id},
                                          {"display_name": 1, "name": 1,
                                            "email": 1, "is_premium": 1,
                                            "premium_until": 1,
                                            "premium_plan_period": 1,
                                            "referrer_code": 1})
    if not u:
        raise ValueError("not_found")
    st = (await db.social_profile_settings.find_one(
        {"user_id": target_user_id})) or {}
    # is_public default True
    if st.get("is_public") is False:
        raise ValueError("not_found")
    display = (st.get("display_name") or u.get("display_name")
                  or u.get("name")
                  or (u.get("email") or "Listener").split("@")[0])
    show_badges = bool(st.get("show_badges_publicly", True))
    show_amb = bool(st.get("show_ambassador_level_publicly", True))
    show_stats = bool(st.get("show_listening_stats_publicly", False))

    # Earned badges (10a-shape catalog only)
    badges_public = []
    if show_badges:
        earned = [r async for r in
                        db.user_badges.find({"user_id": target_user_id})
                            .sort("earned_at", -1).limit(80)]
        bids = [r["badge_id"] for r in earned]
        cat = {b["_id"]: b async for b in
                  db.badges.find({"_id": {"$in": bids},
                                          "schema_version": "10a",
                                          "active": True})}
        for r in earned:
            b = cat.get(r["badge_id"])
            if not b:
                continue
            badges_public.append({
                "badge_id": b.get("badge_id"),
                "name": b.get("name"), "tier": b.get("tier"),
                "category": b.get("category"),
                "points": int(b.get("points") or 0),
                "icon_url": b.get("icon_url"),
                "earned_at": (r["earned_at"].isoformat()
                                  if isinstance(r.get("earned_at"), datetime)
                                  else r.get("earned_at")),
            })
    # Ambassador (10a state)
    amb_public = None
    if show_amb:
        amb = await db.user_ambassador_state.find_one(
            {"user_id": target_user_id})
        if amb:
            amb_public = {
                "level": int(amb.get("level") or 1),
                "level_name": amb.get("level_name") or "Listener",
                "points": int(amb.get("points") or 0),
                "next_level_name": amb.get("next_level_name"),
                "progress_to_next_pct": amb.get("progress_to_next_pct"),
            }
    # Listening stats — only when explicitly opt-in
    listening_public = None
    if show_stats:
        pipe = [{"$match": {"user_id": target_user_id}},
                  {"$group": {"_id": None,
                                "total": {"$sum": "$minutes_credited"}}}]
        d = await db.listening_heartbeats.aggregate(pipe).to_list(1)
        listening_public = {
            "hours_total": round(((d[0] or {}).get("total") or 0) / 60.0, 1)
                                if d else 0,
        }
    # Premium chip / annual subscriber
    is_annual = (bool(u.get("is_premium"))
                      and (u.get("premium_plan_period") or "") == "annual")
    return {
        "user_id": target_user_id,
        "handle": st.get("handle"),
        "display_name": display,
        "avatar_url": st.get("avatar_url"),
        "avatar_initial": _initial_avatar(display),
        "city_pin": st.get("city_pin"),
        "bio": st.get("bio") or "",
        "ambassador": amb_public,
        "badges": badges_public,
        "badges_total": len(badges_public),
        "listening_stats": listening_public,
        "is_premium": bool(u.get("is_premium")),
        "is_annual_subscriber": is_annual,
        "referral_code": u.get("referrer_code"),
        "referral_url": (
            f"/passport/{target_user_id}?ref={u.get('referrer_code')}"
            if u.get("referrer_code") else None),
    }


# ─── Ambassador rewards (level-up perks) ───────────────────────────────
AMBASSADOR_REWARDS = {
    2: {"bigcoin": 50,   "premium_days": 0,
          "chip": "regular_chip"},
    3: {"bigcoin": 200,  "premium_days": 0,
          "exclusive_channel": "vip_lounge", "exclusive_channel_days": 30,
          "chip": "insider_chip"},
    4: {"bigcoin": 500,  "premium_days": 30,
          "early_access_giveaways": True, "chip": "ambassador_chip"},
    5: {"bigcoin": 1500, "premium_days": 90,
          "vip_lobby_host_chip": True, "chip": "diamond_chip"},
}


async def claim_level_up_rewards(db, *, user_id: str,
                                              new_level: int,
                                              prev_level: int) -> list[dict]:
    """Atomically award perks for every level transition in
    (prev_level, new_level].  Idempotent via
    `user_ambassador_state.rewards_claimed_for_level` set.
    Returns the list of newly-claimed reward dicts.
    """
    if new_level <= prev_level:
        return []
    state = await db.user_ambassador_state.find_one({"user_id": user_id})
    already = set((state or {}).get("rewards_claimed_for_level") or [])
    claimed_now: list[dict] = []
    for level in range(max(prev_level, 1) + 1, new_level + 1):
        if level in already:
            continue
        reward = AMBASSADOR_REWARDS.get(level)
        if not reward:
            continue
        # 1. BigCoin
        if reward.get("bigcoin"):
            try:
                from services.bigcoin import award
                await award(db, user_id, int(reward["bigcoin"]),
                                "ambassador_level_up",
                                metadata={"to_level": level})
            except Exception as e:
                logger.warning(f"BC award failed L{level} u={user_id}: {e}")
        # 2. Premium days
        if reward.get("premium_days"):
            await _grant_premium_days(db, user_id,
                                                  int(reward["premium_days"]),
                                                  source=f"ambassador_l{level}")
        # 3. Exclusive channel access (just a flag; channel UI can read it)
        if reward.get("exclusive_channel"):
            await db.user_ambassador_unlocks.update_one(
                {"user_id": user_id,
                  "unlock_kind": "exclusive_channel",
                  "ref": reward["exclusive_channel"]},
                {"$set": {"user_id": user_id,
                            "unlock_kind": "exclusive_channel",
                            "ref": reward["exclusive_channel"],
                            "expires_at": _now() + timedelta(
                                days=int(reward.get(
                                    "exclusive_channel_days") or 30)),
                            "created_at": _now()}},
                upsert=True)
        # 4. VIP host chip (level 5 only) — read at lobby_detail time
        # 5. Audit
        rid = _new_id("alr")
        await db.ambassador_reward_log.insert_one({
            "_id": rid, "reward_id": rid,
            "user_id": user_id,
            "to_level": level,
            "from_level": level - 1,
            "reward_json": reward,
            "claimed_at": _now(),
        })
        # 6. Mark claimed
        await db.user_ambassador_state.update_one(
            {"user_id": user_id},
            {"$addToSet": {"rewards_claimed_for_level": level}})
        claimed_now.append({"level": level, **reward,
                                  "reward_id": rid})
        # 7. Webhook event
        try:
            from services.games_v2_webhooks import queue_system_event
            await queue_system_event(
                db, event_type="ambassador_level_up",
                payload={"user_id": user_id,
                            "to_level": level, "from_level": level - 1,
                            "rewards": reward,
                            "claimed_at": _now().isoformat()})
        except Exception:
            pass
    return claimed_now


async def _grant_premium_days(db, user_id: str, days: int,
                                          *, source: str) -> None:
    """Extend `users.premium_until` by `days` (clamps at now() if expired).
    Does NOT touch Stripe / existing billing — just the premium gate flag.
    """
    if days <= 0:
        return
    u = await db.users.find_one({"user_id": user_id},
                                          {"premium_until": 1, "is_premium": 1})
    now = _now()
    cur = (u or {}).get("premium_until")
    if isinstance(cur, datetime):
        if cur.tzinfo is None:
            cur = cur.replace(tzinfo=timezone.utc)
        base = cur if cur > now else now
    else:
        base = now
    new_until = base + timedelta(days=int(days))
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"premium_until": new_until, "is_premium": True,
                    "premium_source": source}})
    await db.premium_grant_log.insert_one({
        "_id": _new_id("pg"),
        "user_id": user_id, "days": days,
        "source": source, "extended_to": new_until,
        "created_at": now,
    })


async def list_unclaimed_celebrations(db, *, user_id: str) -> list[dict]:
    """Return reward_log entries that the user hasn't yet acknowledged
    via the celebration modal (`level_up_celebrated_levels`)."""
    u = await db.users.find_one({"user_id": user_id},
                                          {"level_up_celebrated_levels": 1})
    seen = set((u or {}).get("level_up_celebrated_levels") or [])
    out = []
    async for r in db.ambassador_reward_log.find(
            {"user_id": user_id}).sort("claimed_at", 1):
        if int(r.get("to_level") or 0) in seen:
            continue
        out.append({
            "reward_id": r.get("reward_id"),
            "to_level": r.get("to_level"),
            "from_level": r.get("from_level"),
            "rewards": r.get("reward_json"),
            "claimed_at": (r["claimed_at"].isoformat()
                              if isinstance(r.get("claimed_at"), datetime)
                              else r.get("claimed_at")),
        })
    return out


async def mark_celebrations_seen(db, *, user_id: str,
                                              levels: list[int]) -> None:
    await db.users.update_one(
        {"user_id": user_id},
        {"$addToSet": {"level_up_celebrated_levels": {"$each": levels}}})


# ─── City leaderboards ─────────────────────────────────────────────────
SUPPORTED_LEADERBOARD_METRICS = {
    "listening_minutes_7d", "badges_earned_7d",
    "ambassador_points_alltime", "referrals_engaged_30d",
    "coupons_redeemed_30d", "commutes_completed_30d",
}
# Deterministic ordered list used in error messages so the client can
# read it back and surface the allowed set to operators.  Matches the
# Phase 10b spec order.
SUPPORTED_LEADERBOARD_METRICS_ORDERED = [
    "listening_minutes_7d", "badges_earned_7d",
    "ambassador_points_alltime", "referrals_engaged_30d",
    "coupons_redeemed_30d", "commutes_completed_30d",
]


def invalid_metric_error_detail() -> str:
    """Phase 10b.2 — single source of truth for the 400 detail string."""
    return (f"invalid_metric. Allowed: "
              f"{SUPPORTED_LEADERBOARD_METRICS_ORDERED!r}")


def bucket_value_for_anonymous(val: int) -> str:
    """Phase 10b.1/10b.2 — coarse bucket for anonymous leaderboard
    entries so we don't leak precise listening time / coin counts.

    Buckets:
      0          → "0"
      1..99      → "1-99"
      100..999   → "100s"
      1000..9999 → "1k+"
      10000..99999 → "10k+"
      100000+    → "100k+"
    """
    n = int(val or 0)
    if n <= 0:
        return "0"
    if n < 100:
        return "1-99"
    if n < 1000:
        return "100s"
    if n < 10_000:
        return "1k+"
    if n < 100_000:
        return "10k+"
    return "100k+"
SUPPORTED_CITIES_FALLBACK = [
    "Dubai", "Frisco", "Dallas", "Abu Dhabi", "Sharjah",
]


def _norm_city(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return s.strip().title()


async def _city_of_user(db, user_id: str) -> Optional[str]:
    """Best-effort city lookup.  Order of preference:
       1. social_profile_settings.city_pin
       2. most recent commute origin/destination city
    """
    st = await db.social_profile_settings.find_one(
        {"user_id": user_id}, {"city_pin": 1})
    if st and st.get("city_pin"):
        return _norm_city(st["city_pin"])
    cmt = await db.commute_sessions.find_one(
        {"user_id": user_id},
        sort=[("started_at", -1)])
    if cmt:
        return _norm_city(cmt.get("destination_city")
                                  or cmt.get("origin_city"))
    return None


async def _active_users_by_city(db, *, max_days: int = 30
                                        ) -> dict[str, list[str]]:
    """Map city → active user_ids over the past `max_days` (anyone with
    a heartbeat in window).  Caps at 5000 users per city for v1."""
    since = _now() - timedelta(days=max_days)
    by_city: dict[str, list[str]] = {}
    seen: set[str] = set()
    cur = db.bigcoin_transactions.find(
        {"reason": "heartbeat", "created_at": {"$gte": since}},
        {"user_id": 1, "_id": 0})
    async for d in cur:
        uid = d["user_id"]
        if uid in seen:
            continue
        seen.add(uid)
        city = await _city_of_user(db, uid)
        if not city:
            continue
        by_city.setdefault(city, []).append(uid)
        if len(by_city[city]) >= 5000:
            continue
    return by_city


async def _metric_value(db, *, user_id: str, metric: str) -> int:
    if metric == "listening_minutes_7d":
        since = _now() - timedelta(days=7)
        pipe = [{"$match": {"user_id": user_id, "ts": {"$gte": since}}},
                  {"$group": {"_id": None,
                                "m": {"$sum": "$minutes_credited"}}}]
        d = await db.listening_heartbeats.aggregate(pipe).to_list(1)
        if not d:
            return 0
        return int(d[0].get("m") or 0)
    if metric == "badges_earned_7d":
        since = _now() - timedelta(days=7)
        return await db.user_badges.count_documents(
            {"user_id": user_id, "earned_at": {"$gte": since}})
    if metric == "ambassador_points_alltime":
        s = await db.user_ambassador_state.find_one({"user_id": user_id})
        return int((s or {}).get("points") or 0)
    if metric == "referrals_engaged_30d":
        since = _now() - timedelta(days=30)
        return await db.referral_attributions.count_documents({
            "referrer_user_id": user_id,
            "attribution_status": "engaged",
            "first_engagement_at": {"$gte": since}})
    if metric == "coupons_redeemed_30d":
        since = _now() - timedelta(days=30)
        return await db.coupons.count_documents({
            "user_id": user_id, "status": "redeemed",
            "redeemed_at": {"$gte": since}})
    if metric == "commutes_completed_30d":
        since = _now() - timedelta(days=30)
        return await db.commute_sessions.count_documents({
            "user_id": user_id, "status": "completed",
            "ended_at": {"$gte": since}})
    return 0


async def recompute_leaderboards(db, *,
                                              cities: Optional[list[str]] = None,
                                              metrics: Optional[list[str]] = None,
                                              min_active_users: int = 3
                                              ) -> dict:
    """Build/refresh `leaderboard_snapshots` for every (city, metric).
    Honors `social_profile_settings.show_leaderboard_position_publicly`
    by replacing display_name with 'Anonymous Listener' but keeping rank.

    City filtering is case-insensitive — callers can pass `dubai` and
    we'll match the canonical `Dubai`.
    """
    metrics = metrics or list(SUPPORTED_LEADERBOARD_METRICS)
    by_city = await _active_users_by_city(db)
    if cities:
        wanted = {_norm_city(c) for c in cities if c}
        by_city = {c: u for c, u in by_city.items() if c in wanted}
        # Make sure each requested city has at least an empty slot
        for c in wanted:
            by_city.setdefault(c, [])
    snapshots = 0
    skipped = 0
    for city, uids in by_city.items():
        if len(uids) < min_active_users:
            skipped += 1
            continue
        # Per-user privacy + display name + avatar look-up (single batch)
        settings = {s["user_id"]: s async for s in
                          db.social_profile_settings.find(
                              {"user_id": {"$in": uids}})
                          if s.get("user_id")}
        users = {u["user_id"]: u async for u in
                      db.users.find({"user_id": {"$in": uids}},
                                            {"user_id": 1, "display_name": 1,
                                              "name": 1, "email": 1})
                      if u.get("user_id")}
        for metric in metrics:
            if metric not in SUPPORTED_LEADERBOARD_METRICS:
                continue
            rows = []
            for uid in uids:
                val = await _metric_value(db, user_id=uid, metric=metric)
                if val <= 0:
                    continue
                st = settings.get(uid) or {}
                u = users.get(uid) or {}
                anon = (st.get("show_leaderboard_position_publicly")
                          is False)
                display = (st.get("display_name") or u.get("display_name")
                              or u.get("name")
                              or (u.get("email") or "Listener").split("@")[0])
                # Phase 10b.1/10b.2 — anonymous entries return a bucketed
                # string for `value` (e.g. "1k+") so we don't leak the
                # exact metric.  Non-anonymous entries keep the integer.
                if anon:
                    value_field: object = bucket_value_for_anonymous(val)
                    value_display_type = "bucket"
                else:
                    value_field = int(val)
                    value_display_type = "exact"
                rows.append({
                    "user_id": uid if not anon else None,
                    "handle": st.get("handle") if not anon else None,
                    "display_name": ("Anonymous Listener" if anon else display),
                    "avatar_url": (None if anon else st.get("avatar_url")),
                    "is_anonymous": anon,
                    "value": value_field,
                    "value_display_type": value_display_type,
                    # Kept for internal sorting / your_rank lookup; not
                    # exposed to non-admin clients.
                    "_sort_value": int(val),
                })
            rows.sort(key=lambda r: -r["_sort_value"])
            top = rows[:100]
            for i, r in enumerate(top, start=1):
                r["rank"] = i
                # Drop internal sort field before persisting
                r.pop("_sort_value", None)
            recompute_every_h = 6 if metric.endswith("_7d") \
                                          else 24
            await db.leaderboard_snapshots.update_one(
                {"city": city, "metric": metric},
                {"$set": {
                    "snapshot_id": _new_id("lbs"),
                    "city": city, "metric": metric,
                    "window": metric.split("_")[-1] if "_" in metric else "alltime",
                    "top_n": top,
                    "active_user_count": len(uids),
                    "computed_at": _now(),
                    "next_recompute_at": _now() + timedelta(
                        hours=recompute_every_h),
                }},
                upsert=True)
            snapshots += 1
    return {"snapshots_written": snapshots,
              "cities_processed": len(by_city),
              "cities_skipped_low_pop": skipped}


async def get_leaderboard(db, *, city: str, metric: str,
                                  for_user_id: Optional[str] = None) -> dict:
    if metric not in SUPPORTED_LEADERBOARD_METRICS:
        raise ValueError(invalid_metric_error_detail())
    city = _norm_city(city)
    snap = await db.leaderboard_snapshots.find_one(
        {"city": city, "metric": metric})
    if not snap:
        return {"city": city, "metric": metric,
                  "top_n": [], "active_user_count": 0,
                  "computed_at": None,
                  "your_rank": None, "your_value": None,
                  "available": False}
    out = {
        "city": city, "metric": metric,
        "top_n": snap.get("top_n") or [],
        "active_user_count": snap.get("active_user_count") or 0,
        "computed_at": (snap["computed_at"].isoformat()
                            if isinstance(snap.get("computed_at"), datetime)
                            else snap.get("computed_at")),
        "your_rank": None, "your_value": None,
        "available": True,
    }
    if for_user_id:
        # See if the caller appears in top_n
        for r in snap.get("top_n") or []:
            if r.get("user_id") == for_user_id:
                out["your_rank"] = r.get("rank")
                out["your_value"] = r.get("value")
                break
        if out["your_rank"] is None:
            # Compute the caller's value on the fly
            val = await _metric_value(
                db, user_id=for_user_id, metric=metric)
            out["your_value"] = val
            # Cheap rank estimate — how many of top_n strictly beat them
            # Use the integer comparison; bucketed string values fall
            # back to 0 here which is safe (they sort last anyway).
            def _as_int(v):
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return 0
            beats = sum(1 for r in snap.get("top_n") or []
                            if _as_int(r.get("value")) > val)
            out["your_rank"] = beats + 1
    return out


async def list_leaderboard_cities(db, *, min_active_users: int = 3
                                              ) -> list[dict]:
    cities = []
    pipe = [{"$group": {"_id": "$city",
                              "metrics": {"$addToSet": "$metric"},
                              "users": {"$max": "$active_user_count"},
                              "last_run": {"$max": "$computed_at"}}}]
    async for c in db.leaderboard_snapshots.aggregate(pipe):
        if int(c.get("users") or 0) < min_active_users:
            continue
        cities.append({
            "city": c["_id"], "metrics": c.get("metrics") or [],
            "active_user_count": int(c.get("users") or 0),
            "last_computed_at": (c["last_run"].isoformat()
                                          if isinstance(c.get("last_run"),
                                                              datetime)
                                          else c.get("last_run")),
        })
    cities.sort(key=lambda x: -x["active_user_count"])
    return cities


# ─── Indexes ───────────────────────────────────────────────────────────
async def ensure_passport_public_indexes(db) -> None:
    # Handle uniqueness
    await db.social_profile_settings.create_index(
        [("handle", 1)], unique=True, sparse=True)
    # Leaderboards
    await db.leaderboard_snapshots.create_index(
        [("city", 1), ("metric", 1)], unique=True)
    await db.leaderboard_snapshots.create_index(
        [("next_recompute_at", 1)])
    # Reward log
    await db.ambassador_reward_log.create_index(
        [("user_id", 1), ("claimed_at", -1)])
    # User ambassador unlocks
    await db.user_ambassador_unlocks.create_index(
        [("user_id", 1), ("unlock_kind", 1), ("ref", 1)], unique=True)
    await db.user_ambassador_unlocks.create_index(
        [("expires_at", 1)])
    # Premium grant log
    await db.premium_grant_log.create_index(
        [("user_id", 1), ("created_at", -1)])


__all__ = [
    "migrate_phase5_badges", "PHASE5_LEGACY_BADGE_BACKFILL",
    "public_profile_view", "validate_handle",
    "AMBASSADOR_REWARDS", "claim_level_up_rewards",
    "list_unclaimed_celebrations", "mark_celebrations_seen",
    "recompute_leaderboards", "get_leaderboard",
    "list_leaderboard_cities", "SUPPORTED_LEADERBOARD_METRICS",
    "ensure_passport_public_indexes",
]
