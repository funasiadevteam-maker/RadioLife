"""Phase 10a — Social Passport badge engine.

Catalog-driven rule evaluation that listens to existing platform signals
(bigcoin heartbeat, game wins, lobby host start, coupon claim/redeem,
commute completion, referral completion, premium activation) and awards
badges + recomputes ambassador level state.

Design choices:

* MongoDB only — `badges`, `user_badges`, `badge_progress`,
  `ambassador_levels`, `user_ambassador_state`.  No Redis, no queues
  beyond the existing Phase 8c webhook system which we reuse for the
  `badge_earned` + `referral_engaged` fan-out.

* Real-time hooks are invoked inline from existing routes (cheap counter
  bumps); a 5-min periodic sweep catches streak / rolling-window badges
  that can't be done in a single counter increment.

* Idempotency: unique compound index `(user_id, badge_id)` on
  `user_badges` keeps double-awards impossible.

* The Phase 5 `services/badges.py` legacy engine and its
  `unlock_rule_json` schema continue to function untouched — Phase 10a
  badges use the new `criteria_json` schema (see CRITERIA_SCHEMA below).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.badge_engine")

# ─── Constants ─────────────────────────────────────────────────────────
BADGE_CATEGORIES = {
    "city", "listening", "streak", "genre", "game", "commute",
    "restaurant", "event", "coupon", "social", "premium", "seasonal",
    "milestone",
}
BADGE_TIERS = {"bronze", "silver", "gold", "platinum", "diamond", "unique"}
SOURCE_EVENTS = {
    "bigcoin_heartbeat", "game_win", "lobby_host_start",
    "coupon_claimed", "coupon_redeemed", "commute_completed",
    "ad_saved", "referral_completed", "premium_activated",
}
PERIODS = {"lifetime", "rolling_7d", "rolling_30d", "daily_streak", "24h"}

CRITERIA_SCHEMA = {
    # type: "counter" — count source_event occurrences (filtered) until target
    "counter": {"required": {"source_event", "target"},
                  "optional": {"filters", "period"}},
    # type: "listening_minutes" — sum bigcoin heartbeat-derived minutes
    "listening_minutes": {"required": {"target"},
                            "optional": {"filters", "period"}},
    # type: "geo_listening" — listening_minutes scoped by city
    "geo_listening": {"required": {"target", "filters"},
                        "optional": {"period"}},
    # type: "streak_days" — consecutive daily heartbeats
    "streak_days": {"required": {"target"}, "optional": {}},
    # type: "compound" — all_of an array of sub-criteria within optional window
    "compound": {"required": {"all_of"}, "optional": {}},
    # type: "admin_only" — never auto-awarded
    "admin_only": {"required": set(), "optional": set()},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# ─── Indexes ───────────────────────────────────────────────────────────
async def ensure_passport_indexes(db) -> None:
    # `badges` — Phase 5 already exists, we just add category/tier indexes
    await db.badges.create_index([("category", 1), ("active", 1)])
    await db.badges.create_index([("tier", 1)])
    await db.badges.create_index([("secret", 1), ("active", 1)])
    # user_badges — index already exists from Phase 5 with the default name.
    # Ensure it's present idempotently using the same auto-generated name
    # to avoid IndexOptionsConflict.
    await db.user_badges.create_index(
        [("user_id", 1), ("badge_id", 1)], unique=True)
    await db.user_badges.create_index([("user_id", 1), ("earned_at", -1)])
    await db.user_badges.create_index([("badge_id", 1), ("earned_at", -1)])
    # badge_progress
    await db.badge_progress.create_index(
        [("user_id", 1), ("badge_id", 1)], unique=True)
    await db.badge_progress.create_index([("user_id", 1)])
    # referral_attributions
    await db.referral_attributions.create_index(
        [("ref_code", 1), ("landing_at", -1)])
    await db.referral_attributions.create_index(
        [("referee_user_id", 1)], sparse=True)
    await db.referral_attributions.create_index(
        [("attribution_status", 1), ("landing_at", -1)])
    await db.referral_attributions.create_index(
        [("device_fingerprint", 1), ("ref_code", 1)], sparse=True)
    # social_profile_settings
    await db.social_profile_settings.create_index(
        [("user_id", 1)], unique=True)
    # ambassador_levels + state
    await db.ambassador_levels.create_index(
        [("level", 1)], unique=True)
    await db.user_ambassador_state.create_index(
        [("user_id", 1)], unique=True)
    await db.user_ambassador_state.create_index(
        [("points", -1)])


# ─── Catalog seed ──────────────────────────────────────────────────────
def _b(badge_id, *, name, description, category, tier, points,
        criteria_json, icon_url=None, secret=False, active=True,
        partner_seeded=False):
    return {
        "_id": badge_id, "badge_id": badge_id,
        # `slug` is the Phase 5 legacy unique index — keep distinct per row
        "slug": badge_id,
        "name": name, "description": description,
        "category": category, "tier": tier, "points": int(points),
        "criteria_json": criteria_json,
        "icon_url": icon_url or f"/assets/badges/{badge_id}.svg",
        "secret": bool(secret), "active": bool(active),
        "partner_seeded": bool(partner_seeded),
        "schema_version": "10a",
    }


PHASE_10A_BADGE_CATALOG = [
    # ── City — 5 ──────────────────────────────────────────────────────
    _b("dubai_regular", name="Dubai Regular",
        description="30+ hours of listening while in Dubai.",
        category="city", tier="silver", points=50,
        criteria_json={"type": "geo_listening", "target": 1800,
                          "filters": {"city": "Dubai"}, "period": "lifetime"}),
    _b("frisco_regular", name="Frisco Regular",
        description="30+ hours of listening while in Frisco TX.",
        category="city", tier="silver", points=50,
        criteria_json={"type": "geo_listening", "target": 1800,
                          "filters": {"city": "Frisco"}, "period": "lifetime"}),
    _b("dallas_regular", name="Dallas Regular",
        description="30+ hours of listening while in Dallas.",
        category="city", tier="silver", points=50,
        criteria_json={"type": "geo_listening", "target": 1800,
                          "filters": {"city": "Dallas"}, "period": "lifetime"}),
    _b("abu_dhabi_regular", name="Abu Dhabi Regular",
        description="30+ hours of listening while in Abu Dhabi.",
        category="city", tier="silver", points=50,
        criteria_json={"type": "geo_listening", "target": 1800,
                          "filters": {"city": "Abu Dhabi"},
                          "period": "lifetime"}),
    _b("sharjah_regular", name="Sharjah Regular",
        description="30+ hours of listening while in Sharjah.",
        category="city", tier="silver", points=50,
        criteria_json={"type": "geo_listening", "target": 1800,
                          "filters": {"city": "Sharjah"},
                          "period": "lifetime"}),
    # ── Listening hours — 5 tiers ─────────────────────────────────────
    _b("first_hour", name="First Hour",
        description="Listened for 60 minutes lifetime.",
        category="listening", tier="bronze", points=10,
        criteria_json={"type": "listening_minutes", "target": 60,
                          "period": "lifetime"}),
    _b("first_10_hours", name="10 Hours In",
        description="10 hours of total listening.",
        category="listening", tier="silver", points=25,
        criteria_json={"type": "listening_minutes", "target": 600,
                          "period": "lifetime"}),
    _b("first_100_hours", name="Centurion",
        description="100 hours of total listening.",
        category="listening", tier="gold", points=100,
        criteria_json={"type": "listening_minutes", "target": 6000,
                          "period": "lifetime"}),
    _b("first_500_hours", name="500 Hour Veteran",
        description="500 hours of total listening.",
        category="listening", tier="platinum", points=250,
        criteria_json={"type": "listening_minutes", "target": 30000,
                          "period": "lifetime"}),
    _b("first_1000_hours", name="Thousand Hour Lifer",
        description="1000 hours of total listening.",
        category="listening", tier="diamond", points=500,
        criteria_json={"type": "listening_minutes", "target": 60000,
                          "period": "lifetime"}),
    # ── Streak — 4 tiers ──────────────────────────────────────────────
    _b("streak_3", name="3-Day Streak",
        description="Listened 3 days in a row.",
        category="streak", tier="bronze", points=15,
        criteria_json={"type": "streak_days", "target": 3}),
    _b("streak_7", name="7-Day Streak",
        description="Listened 7 days in a row.",
        category="streak", tier="silver", points=40,
        criteria_json={"type": "streak_days", "target": 7}),
    _b("streak_30", name="30-Day Streak",
        description="Logged in 30 days in a row.",
        category="streak", tier="gold", points=120,
        criteria_json={"type": "streak_days", "target": 30}),
    _b("streak_90", name="90-Day Streak",
        description="90 consecutive days listening.",
        category="streak", tier="platinum", points=300,
        criteria_json={"type": "streak_days", "target": 90}),
    # ── Genre — 5 ─────────────────────────────────────────────────────
    _b("bollywood_connoisseur", name="Bollywood Connoisseur",
        description="20+ hours on a Bollywood channel.",
        category="genre", tier="gold", points=60,
        criteria_json={"type": "listening_minutes", "target": 1200,
                          "filters": {"channel_genre": "bollywood"},
                          "period": "lifetime"}),
    _b("hip_hop_head", name="Hip-Hop Head",
        description="20+ hours of hip-hop listening.",
        category="genre", tier="gold", points=60,
        criteria_json={"type": "listening_minutes", "target": 1200,
                          "filters": {"channel_genre": "hip_hop"},
                          "period": "lifetime"}),
    _b("english_pop_lover", name="English Pop Lover",
        description="20+ hours of English pop listening.",
        category="genre", tier="gold", points=60,
        criteria_json={"type": "listening_minutes", "target": 1200,
                          "filters": {"channel_genre": "english_pop"},
                          "period": "lifetime"}),
    _b("devotional_morning_streak", name="Morning Devotional",
        description="Devotional channel before 9am — 5 days in a row.",
        category="genre", tier="silver", points=45,
        criteria_json={"type": "counter", "target": 5,
                          "source_event": "bigcoin_heartbeat",
                          "filters": {"channel_genre": "devotional",
                                          "hour_lt": 9},
                          "period": "daily_streak"}),
    _b("punjabi_party_regular", name="Punjabi Party Regular",
        description="10+ hours on Punjabi channels.",
        category="genre", tier="silver", points=40,
        criteria_json={"type": "listening_minutes", "target": 600,
                          "filters": {"channel_genre": "punjabi"},
                          "period": "lifetime"}),
    # ── Game — 5 ──────────────────────────────────────────────────────
    _b("first_spin", name="First Spin",
        description="Played your first game.",
        category="game", tier="bronze", points=10,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "game_win",
                          "period": "lifetime"}),
    _b("trivia_master_lvl3", name="Trivia Master Lv.3",
        description="Won 10 trivia rounds.",
        category="game", tier="gold", points=80,
        criteria_json={"type": "counter", "target": 10,
                          "source_event": "game_win",
                          "filters": {"game_type": "trivia_master"},
                          "period": "lifetime"}),
    _b("lyric_legend", name="Lyric Legend",
        description="Solved 10 lyric-completion puzzles.",
        category="game", tier="gold", points=80,
        criteria_json={"type": "counter", "target": 10,
                          "source_event": "game_win",
                          "filters": {"game_type": "lyric_completion"},
                          "period": "lifetime"}),
    _b("mystery_box_explorer", name="Mystery Box Explorer",
        description="Opened 5 mystery boxes.",
        category="game", tier="silver", points=40,
        criteria_json={"type": "counter", "target": 5,
                          "source_event": "game_win",
                          "filters": {"game_type": "mystery_box"},
                          "period": "lifetime"}),
    _b("wheel_of_fortune_solver", name="Wheel Solver",
        description="Solved 5 Wheel of Fortune puzzles.",
        category="game", tier="silver", points=40,
        criteria_json={"type": "counter", "target": 5,
                          "source_event": "game_win",
                          "filters": {"game_type": "wheel_of_fortune"},
                          "period": "lifetime"}),
    # ── Commute — 3 ───────────────────────────────────────────────────
    _b("daily_commuter", name="Daily Commuter",
        description="Completed 10 commutes.",
        category="commute", tier="silver", points=40,
        criteria_json={"type": "counter", "target": 10,
                          "source_event": "commute_completed",
                          "period": "lifetime"}),
    _b("morning_drive_veteran", name="Morning Drive Veteran",
        description="5 morning-drive commutes.",
        category="commute", tier="bronze", points=20,
        criteria_json={"type": "counter", "target": 5,
                          "source_event": "commute_completed",
                          "filters": {"daypart": "morning_drive"},
                          "period": "lifetime"}),
    _b("rainy_day_navigator", name="Rainy Day Navigator",
        description="Drove through 3 rainy commutes.",
        category="commute", tier="silver", points=35,
        criteria_json={"type": "counter", "target": 3,
                          "source_event": "commute_completed",
                          "filters": {"weather": "rain"},
                          "period": "lifetime"}),
    # ── Restaurant — 3 (partner-seeded generic) ───────────────────────
    _b("karak_cafe_regular", name="Karak Cafe Regular",
        description="Redeemed 3 offers at any karak business.",
        category="restaurant", tier="silver", points=40,
        partner_seeded=True,
        criteria_json={"type": "counter", "target": 3,
                          "source_event": "coupon_redeemed",
                          "filters": {"business_category": "karak"},
                          "period": "lifetime"}),
    _b("lunch_explorer", name="Lunch Explorer",
        description="Claimed 5 lunch-window offers.",
        category="restaurant", tier="bronze", points=25,
        partner_seeded=True,
        criteria_json={"type": "counter", "target": 5,
                          "source_event": "coupon_claimed",
                          "filters": {"daypart": "lunch"},
                          "period": "lifetime"}),
    _b("dinner_critic", name="Dinner Critic",
        description="Claimed 5 dinner-window offers.",
        category="restaurant", tier="bronze", points=25,
        partner_seeded=True,
        criteria_json={"type": "counter", "target": 5,
                          "source_event": "coupon_claimed",
                          "filters": {"daypart": "dinner"},
                          "period": "lifetime"}),
    # ── Event — 3 ─────────────────────────────────────────────────────
    _b("concert_hunter", name="Concert Hunter",
        description="Claimed 1 concert ticket coupon.",
        category="event", tier="silver", points=40,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "coupon_claimed",
                          "filters": {"business_category": "concert"},
                          "period": "lifetime"}),
    _b("movie_night_vip", name="Movie Night VIP",
        description="Claimed 3 movie tickets.",
        category="event", tier="silver", points=45,
        criteria_json={"type": "counter", "target": 3,
                          "source_event": "coupon_claimed",
                          "filters": {"business_category": "cinema"},
                          "period": "lifetime"}),
    _b("club_passport", name="Club Passport",
        description="Claimed a club-night offer.",
        category="event", tier="gold", points=60,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "coupon_claimed",
                          "filters": {"business_category": "club"},
                          "period": "lifetime"}),
    # ── Coupon — 3 ────────────────────────────────────────────────────
    _b("coupon_collector", name="Coupon Collector",
        description="Claimed 10 coupons.",
        category="coupon", tier="silver", points=40,
        criteria_json={"type": "counter", "target": 10,
                          "source_event": "coupon_claimed",
                          "period": "lifetime"}),
    _b("big_saver", name="Big Saver",
        description="Redeemed 5 coupons.",
        category="coupon", tier="gold", points=70,
        criteria_json={"type": "counter", "target": 5,
                          "source_event": "coupon_redeemed",
                          "period": "lifetime"}),
    _b("karak_winner", name="Karak Winner",
        description="Won a karak offer via game prize.",
        category="coupon", tier="gold", points=60,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "game_win",
                          "filters": {"prize_business_category": "karak"},
                          "period": "lifetime"}),
    # ── Social — 4 ────────────────────────────────────────────────────
    _b("lobby_host", name="Lobby Host",
        description="Hosted your first lobby.",
        category="social", tier="bronze", points=20,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "lobby_host_start",
                          "period": "lifetime"}),
    _b("lobby_veteran", name="Lobby Veteran",
        description="Hosted 10 lobbies.",
        category="social", tier="gold", points=80,
        criteria_json={"type": "counter", "target": 10,
                          "source_event": "lobby_host_start",
                          "period": "lifetime"}),
    _b("referrer", name="Referrer",
        description="One successful referral.",
        category="social", tier="bronze", points=25,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "referral_completed",
                          "period": "lifetime"}),
    _b("super_referrer", name="Super Referrer",
        description="10 successful referrals.",
        category="social", tier="platinum", points=200,
        criteria_json={"type": "counter", "target": 10,
                          "source_event": "referral_completed",
                          "period": "lifetime"}),
    # ── Premium — 3 ───────────────────────────────────────────────────
    _b("premium_subscriber", name="Premium Subscriber",
        description="Subscribed to FUUSIC Premium.",
        category="premium", tier="silver", points=50,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "premium_activated",
                          "period": "lifetime"}),
    _b("annual_subscriber", name="Annual Subscriber",
        description="Active annual subscription.",
        category="premium", tier="gold", points=100,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "premium_activated",
                          "filters": {"plan_period": "annual"},
                          "period": "lifetime"}),
    _b("family_root", name="Family Root",
        description="Paying head of a family plan.",
        category="premium", tier="platinum", points=120,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "premium_activated",
                          "filters": {"plan_type": "family"},
                          "period": "lifetime"}),
    # ── Seasonal — 3 scaffold (active=False, secret=True) ─────────────
    _b("ramadan_devotional_2026", name="Ramadan Devotional 2026",
        description="Listened daily during Ramadan 2026.",
        category="seasonal", tier="unique", points=150,
        secret=True, active=False,
        criteria_json={"type": "streak_days", "target": 30}),
    _b("garba_season_2026", name="Garba Season 2026",
        description="Hosted a Navratri Garba lobby.",
        category="seasonal", tier="unique", points=150,
        secret=True, active=False,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "lobby_host_start",
                          "filters": {"channel_genre": "garba"},
                          "period": "lifetime"}),
    _b("diwali_hunter_2026", name="Diwali Hunter 2026",
        description="Claimed a Diwali festive offer.",
        category="seasonal", tier="unique", points=150,
        secret=True, active=False,
        criteria_json={"type": "counter", "target": 1,
                          "source_event": "coupon_claimed",
                          "filters": {"campaign_tag": "diwali_2026"},
                          "period": "lifetime"}),
    # ── Milestone — 2 ─────────────────────────────────────────────────
    _b("bigfm_og", name="FUUSIC OG",
        description="Account older than 90 days.",
        category="milestone", tier="gold", points=80,
        criteria_json={"type": "admin_only"}),
    _b("early_adopter", name="Early Adopter",
        description="One of the first 1000 FUUSIC listeners.",
        category="milestone", tier="diamond", points=400,
        criteria_json={"type": "admin_only"}),
    # ── Compound — 2 (Phase 10a.1) ───────────────────────────────────
    _b("rainy_day_chai_winner", name="Rainy Day Chai Winner",
        description="Drove through a rainy commute and claimed a karak "
                       "offer within 24 hours.",
        category="restaurant", tier="gold", points=50,
        partner_seeded=True,
        criteria_json={
            "type": "compound",
            "all_of": [
                {"source_event": "commute_completed",
                  "filters": {"weather": "rain"},
                  "period": "24h"},
                {"source_event": "coupon_claimed",
                  "filters": {"business_category": "karak"},
                  "period": "24h_after_above"},
            ]}),
    _b("commute_concert_combo", name="Commute · Concert Combo",
        description="Completed a commute and claimed a concert-ticket "
                       "coupon within 24 hours.",
        category="event", tier="gold", points=60,
        criteria_json={
            "type": "compound",
            "all_of": [
                {"source_event": "commute_completed",
                  "filters": {},
                  "period": "24h"},
                {"source_event": "coupon_claimed",
                  "filters": {"business_category": "concert"},
                  "period": "24h_after_above"},
            ]}),
]


AMBASSADOR_LEVELS = [
    {"level": 1, "name": "Listener",            "min_points": 0,
      "perks": []},
    {"level": 2, "name": "Regular",             "min_points": 100,
      "perks": ["custom_avatar"]},
    {"level": 3, "name": "Insider",             "min_points": 500,
      "perks": ["custom_avatar", "city_pin"]},
    {"level": 4, "name": "Ambassador",          "min_points": 2000,
      "perks": ["custom_avatar", "city_pin", "ambassador_chip"]},
    {"level": 5, "name": "Diamond Ambassador",  "min_points": 10000,
      "perks": ["custom_avatar", "city_pin", "ambassador_chip",
                  "exclusive_channels"]},
]


async def seed_badge_catalog(db) -> dict:
    """Idempotent seed.  Inserts missing badges, refreshes catalog fields
    (name/description/criteria) on existing rows.  Never deletes.

    Note on Phase 5 ↔ Phase 10a slug collisions
    ────────────────────────────────────────────
    Phase 5 used `_id="badge_streak_30"` with `slug="streak_30"`.  Phase 10a
    seeded the canonical `_id="streak_30", slug="streak_30"` row.  We
    keep them as DISTINCT rows in the catalog; the Phase 10b migration
    namespaces legacy slugs to `slug="badge_streak_30"` so the Phase 10a
    canonical row can insert cleanly without violating the `slug_1`
    unique index.
    """
    created, updated, skipped = 0, 0, 0
    for b in PHASE_10A_BADGE_CATALOG:
        try:
            existing = await db.badges.find_one({"_id": b["_id"]})
            if existing is None:
                doc = dict(b)
                doc["created_at"] = _now()
                doc["updated_at"] = _now()
                try:
                    await db.badges.insert_one(doc)
                    created += 1
                except Exception as ins_err:
                    # Slug collision against a Phase 5 row that hasn't
                    # been migrated yet — defer to the Phase 10b
                    # migration which namespaces the legacy slug.
                    skipped += 1
                    logger.info(f"badge seed defer {b['_id']}: {ins_err}")
                continue
            keep = {"created_at": existing.get("created_at") or _now()}
            if existing.get("schema_version") == "10a" \
                    and existing.get("active") != b["active"]:
                keep["active"] = existing["active"]
            await db.badges.update_one(
                {"_id": b["_id"]},
                {"$set": {**b, **keep, "updated_at": _now()}})
            updated += 1
        except Exception as e:
            skipped += 1
            logger.warning(f"badge seed skip {b.get('_id')}: {e}")
    return {"created": created, "updated": updated, "skipped": skipped,
              "catalog_size": len(PHASE_10A_BADGE_CATALOG)}


async def seed_ambassador_levels(db) -> dict:
    created = 0
    for lvl in AMBASSADOR_LEVELS:
        res = await db.ambassador_levels.update_one(
            {"level": lvl["level"]},
            {"$set": lvl, "$setOnInsert": {"created_at": _now()}},
            upsert=True)
        if res.upserted_id:
            created += 1
    return {"created": created, "total": len(AMBASSADOR_LEVELS)}


# ─── Counter helpers ───────────────────────────────────────────────────
def _filter_match(event_filters: dict, payload: dict) -> bool:
    """Check that every filter key in `event_filters` is satisfied by
    the payload.  Special operators: `<key>_lt`, `<key>_gte` map to
    numeric comparison against payload[<key>]."""
    if not event_filters:
        return True
    for k, v in event_filters.items():
        if k.endswith("_lt"):
            real = k[:-3]
            try:
                if not (float(payload.get(real, 0)) < float(v)):
                    return False
            except (TypeError, ValueError):
                return False
            continue
        if k.endswith("_gte"):
            real = k[:-4]
            try:
                if not (float(payload.get(real, 0)) >= float(v)):
                    return False
            except (TypeError, ValueError):
                return False
            continue
        if payload.get(k) != v:
            return False
    return True


async def _count_source_events(db, *, user_id: str, source_event: str,
                                       filters: dict, period: str) -> int:
    """Count matching rows in `badge_events` for a counter-type rule."""
    q: dict = {"user_id": user_id, "source_event": source_event}
    if period == "rolling_7d":
        q["ts"] = {"$gte": _now() - timedelta(days=7)}
    elif period == "rolling_30d":
        q["ts"] = {"$gte": _now() - timedelta(days=30)}
    elif period == "24h":
        q["ts"] = {"$gte": _now() - timedelta(hours=24)}
    # `filters` are stored verbatim in payload — Mongo lets us address
    # nested keys.  For simple equality we can run as a dotted key.
    for k, v in (filters or {}).items():
        if k.endswith("_lt") or k.endswith("_gte"):
            # Numeric — skip server side, evaluate in Python below.
            continue
        q[f"payload.{k}"] = v
    rows = await db.badge_events.find(q).to_list(2000)
    # Numeric filter check (small per-user)
    out = [r for r in rows if _filter_match(filters or {}, r.get("payload") or {})]
    return len(out)


async def _listening_minutes_lifetime(db, *, user_id: str,
                                                  filters: dict) -> int:
    """Sum minutes_credited from listening_heartbeats with optional
    city / channel filters via payload."""
    q: dict = {"user_id": user_id}
    pipe = [{"$match": q},
              {"$group": {"_id": None, "total": {"$sum": "$minutes_credited"}}}]
    doc = await db.listening_heartbeats.aggregate(pipe).to_list(1)
    base = int(doc[0]["total"]) if doc else 0
    if not filters:
        return base
    # filtered branch — count badge_events of type bigcoin_heartbeat
    # whose payload matches the filter.
    cnt = await _count_source_events(
        db, user_id=user_id, source_event="bigcoin_heartbeat",
        filters=filters, period="lifetime")
    return cnt


async def _streak_days(db, *, user_id: str) -> int:
    """Reuses Phase 8b's heartbeat-bucket logic for parity."""
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    streak = 0
    cursor = today
    for _ in range(120):
        day_end = cursor + timedelta(days=1)
        n = await db.bigcoin_transactions.count_documents({
            "user_id": user_id, "reason": "heartbeat",
            "created_at": {"$gte": cursor, "$lt": day_end},
        })
        if n > 0:
            streak += 1
            cursor -= timedelta(days=1)
            continue
        if cursor == today:
            cursor -= timedelta(days=1)
            continue
        break
    return streak


# ─── Eval entry point ──────────────────────────────────────────────────
async def evaluate(db, user_id: str, source_event: str,
                        payload: Optional[dict] = None) -> list[dict]:
    """Called inline from any source-event hook.  Persists the event
    row into `badge_events` for later counter queries, then re-evaluates
    every active badge for this user that subscribes to this source.

    Returns the list of newly-awarded badge views.
    """
    if source_event not in SOURCE_EVENTS:
        logger.warning(f"evaluate: unknown source_event={source_event}")
        return []
    payload = payload or {}
    # 1. Persist event (cheap, append-only)
    try:
        await db.badge_events.insert_one({
            "_id": _new_id("bev"),
            "user_id": user_id, "source_event": source_event,
            "payload": payload, "ts": _now(),
        })
    except Exception as e:
        logger.warning(f"badge_event insert: {e}")
    # 2. Evaluate badges subscribed to this source.  Read user_id's
    # already-earned set once.
    earned = {r["badge_id"] async for r in
                  db.user_badges.find({"user_id": user_id},
                                            {"badge_id": 1, "_id": 0})}
    newly_awarded: list[dict] = []
    cur = db.badges.find({"active": True,
                                  "schema_version": "10a"})
    async for badge in cur:
        bid = badge.get("badge_id") or str(badge.get("_id") or "")
        if not bid:
            continue
        if not badge.get("badge_id"):
            badge["badge_id"] = bid   # local-only repair
        if bid in earned:
            continue
        cj = badge.get("criteria_json") or {}
        if not await _criteria_subscribes_to(cj, source_event):
            continue
        progress = await _compute_progress(db, user_id, cj, payload)
        target = int(cj.get("target") or 0) if cj.get("type") != "compound" else 1
        if progress["current"] >= max(target, 1) and progress["satisfied"]:
            awarded = await _award_badge(
                db, user_id=user_id, badge=badge,
                progress_snapshot=progress)
            if awarded:
                newly_awarded.append(awarded)
        elif target > 1:
            # bump progress row
            await db.badge_progress.update_one(
                {"user_id": user_id, "badge_id": badge["badge_id"]},
                {"$set": {"current_value": int(progress["current"]),
                            "target_value": target,
                            "last_updated_at": _now()}},
                upsert=True)
    if newly_awarded:
        await recompute_ambassador(db, user_id)
    return newly_awarded


async def _criteria_subscribes_to(criteria: dict, source_event: str) -> bool:
    t = criteria.get("type")
    if t == "counter":
        return criteria.get("source_event") == source_event
    if t in ("listening_minutes", "geo_listening"):
        return source_event == "bigcoin_heartbeat"
    if t == "streak_days":
        return source_event == "bigcoin_heartbeat"
    if t == "compound":
        for sub in criteria.get("all_of") or []:
            if sub.get("source_event") == source_event:
                return True
        return False
    return False


async def _compute_progress(db, user_id: str, criteria: dict,
                                      payload: dict) -> dict:
    """Compute (current_value, satisfied_bool) for any criteria type.
    `satisfied` is True iff the threshold is met."""
    t = criteria.get("type")
    if t == "counter":
        cur = await _count_source_events(
            db, user_id=user_id,
            source_event=criteria["source_event"],
            filters=criteria.get("filters") or {},
            period=criteria.get("period") or "lifetime")
        return {"current": cur, "satisfied": cur >= int(criteria.get("target") or 1)}
    if t == "listening_minutes":
        m = await _listening_minutes_lifetime(
            db, user_id=user_id,
            filters=criteria.get("filters") or {})
        return {"current": m, "satisfied": m >= int(criteria.get("target") or 1)}
    if t == "geo_listening":
        m = await _count_source_events(
            db, user_id=user_id, source_event="bigcoin_heartbeat",
            filters=criteria.get("filters") or {}, period="lifetime")
        return {"current": m, "satisfied": m >= int(criteria.get("target") or 1)}
    if t == "streak_days":
        s = await _streak_days(db, user_id=user_id)
        return {"current": s, "satisfied": s >= int(criteria.get("target") or 1)}
    if t == "compound":
        return await _compound_satisfied(db, user_id, criteria)
    if t == "admin_only":
        return {"current": 0, "satisfied": False}
    return {"current": 0, "satisfied": False}


async def _compound_satisfied(db, user_id: str, criteria: dict) -> dict:
    """All-of compound: every sub-criterion must have at least one
    matching event within its window.  Phase 10a only supports
    `period="24h"` and `period="24h_after_above"` sub-criteria."""
    subs = criteria.get("all_of") or []
    if not subs:
        return {"current": 0, "satisfied": False}
    cursor_floor = None
    for sub in subs:
        src = sub.get("source_event")
        flt = sub.get("filters") or {}
        per = sub.get("period") or "24h"
        # Compute the time floor for this sub
        if per == "24h":
            floor = _now() - timedelta(hours=24)
        elif per == "24h_after_above":
            if cursor_floor is None:
                floor = _now() - timedelta(hours=24)
            else:
                floor = cursor_floor
        else:
            floor = _now() - timedelta(days=30)  # generous fallback
        q: dict = {"user_id": user_id, "source_event": src,
                     "ts": {"$gte": floor}}
        for k, v in flt.items():
            if not (k.endswith("_lt") or k.endswith("_gte")):
                q[f"payload.{k}"] = v
        rows = await db.badge_events.find(q).sort("ts", 1).to_list(50)
        rows = [r for r in rows if _filter_match(flt, r.get("payload") or {})]
        if not rows:
            return {"current": 0, "satisfied": False, "missing_sub": src}
        cursor_floor = rows[0]["ts"]
    return {"current": len(subs), "satisfied": True}


# ─── Award + ambassador recompute ──────────────────────────────────────
async def _award_badge(db, *, user_id: str, badge: dict,
                              progress_snapshot: dict) -> Optional[dict]:
    """Atomic, idempotent award.  Returns the award doc if newly
    created, else None.  Fires the `badge_earned` webhook + queues a
    Phase 10b RJ stinger (60-min cooldown per listener)."""
    award_id = _new_id("bdg")
    doc = {
        "_id": award_id, "award_id": award_id,
        "user_id": user_id, "badge_id": badge["badge_id"],
        "earned_at": _now(),
        "source": "auto_engine",
        "progress_snapshot_json": {
            "current": progress_snapshot.get("current"),
            "target": badge.get("criteria_json", {}).get("target"),
            "criteria_type": badge.get("criteria_json", {}).get("type"),
        },
    }
    try:
        await db.user_badges.insert_one(doc)
    except Exception:
        # duplicate — idempotent
        return None
    # Drop any progress row
    await db.badge_progress.delete_one(
        {"user_id": user_id, "badge_id": badge["badge_id"]})
    # Fire webhook
    try:
        from services.games_v2_webhooks import queue_system_event
        await queue_system_event(
            db, event_type="badge_earned",
            payload={
                "user_id": user_id,
                "badge_id": badge["badge_id"],
                "badge_name": badge.get("name"),
                "category": badge.get("category"),
                "tier": badge.get("tier"),
                "points": int(badge.get("points") or 0),
                "earned_at": doc["earned_at"].isoformat(),
            })
    except Exception as e:
        logger.warning(f"badge_earned webhook enqueue failed: {e}")
    # Phase 10b — RJ stinger ("Big congrats to {display_name}…").
    # 60-min cooldown per listener.
    try:
        await enqueue_badge_earned_rj_extra(
            db, user_id=user_id, badge=badge)
    except Exception as e:
        logger.warning(f"badge_earned rj extra: {e}")
    logger.info(f"badge_award user={user_id} badge={badge['badge_id']}")
    return doc


async def enqueue_badge_earned_rj_extra(db, *, user_id: str,
                                                      badge: dict) -> dict:
    """Phase 10b — push a `badge_earned` extra into `users.pending_rj_extras`
    so the next RJ break weaves in a 1-sentence congratulations.
    60-min cooldown per listener tracked via
    `users.last_badge_rj_mention_at`."""
    now = _now()
    cutoff = now - timedelta(minutes=60)
    u = await db.users.find_one(
        {"user_id": user_id},
        {"last_badge_rj_mention_at": 1, "display_name": 1, "name": 1,
          "email": 1})
    if u:
        last = u.get("last_badge_rj_mention_at")
        if isinstance(last, datetime):
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last > cutoff:
                return {"queued": False, "reason": "cooldown",
                          "last_badge_rj_mention_at": last.isoformat()}
    display = ((u or {}).get("display_name")
                  or (u or {}).get("name")
                  or ((u or {}).get("email") or "Listener").split("@")[0])
    # Total badge count for the stinger payload
    total_badges = await db.user_badges.count_documents(
        {"user_id": user_id})
    extra = {
        "extra_id": _new_id("rjx"),
        "kind": "badge_earned",
        "payload": {
            "display_name": display,
            "badge_id": badge.get("badge_id"),
            "badge_name": badge.get("name"),
            "badge_tier": badge.get("tier"),
            "badge_category": badge.get("category"),
            "points": int(badge.get("points") or 0),
            "total_badges_count": int(total_badges),
        },
        "created_at": now,
        "expires_at": now + timedelta(minutes=15),
    }
    await db.users.update_one(
        {"user_id": user_id},
        {"$push": {"pending_rj_extras": extra},
          "$set": {"last_badge_rj_mention_at": now}})
    return {"queued": True, "extra_id": extra["extra_id"],
              "payload": extra["payload"]}


async def admin_grant(db, *, user_id: str, badge_id: str,
                              admin_user_id: str) -> Optional[dict]:
    """Admin-only path — bypasses criteria evaluation.  Idempotent.

    Phase 10c.1 — explicit idempotency: detects an existing earned row
    BEFORE insert so the caller gets `{awarded: false, already_owned:
    True}` instead of a silent insert-failure.  Also returns the
    pre/post ambassador state so the caller can verify the points/level
    transition without a second roundtrip.
    """
    # Look up by either `_id` or `badge_id` field — Phase 5 rows have
    # only `_id` set whereas Phase 10a rows set both to the slug.
    badge = await db.badges.find_one(
        {"$or": [{"_id": badge_id}, {"badge_id": badge_id}]})
    if not badge:
        raise ValueError("badge_not_found")
    canonical_bid = badge.get("badge_id") or badge.get("_id")
    # Idempotency: already earned?
    existing = await db.user_badges.find_one(
        {"user_id": user_id, "badge_id": canonical_bid})
    if existing:
        prev_state = await db.user_ambassador_state.find_one(
            {"user_id": user_id}) or {}
        return {
            "awarded": False,
            "already_owned": True,
            "award_id": existing.get("award_id") or existing.get("_id"),
            "badge_id": canonical_bid,
            "user_id": user_id,
            "state": {
                "level": prev_state.get("level"),
                "points": prev_state.get("points"),
                "badge_count": prev_state.get("badge_count"),
            },
        }
    # Pre-state for delta reporting
    prev_state = await db.user_ambassador_state.find_one(
        {"user_id": user_id}) or {}
    prev_level = int(prev_state.get("level") or 1)
    prev_points = int(prev_state.get("points") or 0)
    award_id = _new_id("bdg")
    doc = {
        "_id": award_id, "award_id": award_id,
        "user_id": user_id, "badge_id": canonical_bid,
        "earned_at": _now(),
        "source": "admin_grant",
        "granted_by_user_id": admin_user_id,
        "progress_snapshot_json": {"source": "admin"},
    }
    try:
        await db.user_badges.insert_one(doc)
    except Exception as _e:
        # Race — another grant beat us to it.  Treat as idempotent.
        logger.warning(f"admin_grant insert race u={user_id} b={badge_id}: {_e}")
        return {
            "awarded": False, "already_owned": True,
            "award_id": None, "badge_id": canonical_bid,
            "user_id": user_id, "state": {
                "level": prev_state.get("level"),
                "points": prev_state.get("points"),
                "badge_count": prev_state.get("badge_count"),
            },
        }
    try:
        from services.games_v2_webhooks import queue_system_event
        await queue_system_event(
            db, event_type="badge_earned",
            payload={"user_id": user_id, "badge_id": canonical_bid,
                       "badge_name": badge.get("name"),
                       "category": badge.get("category"),
                       "tier": badge.get("tier"),
                       "points": int(badge.get("points") or 0),
                       "earned_at": doc["earned_at"].isoformat(),
                       "source": "admin_grant"})
    except Exception:
        pass
    new_state = await recompute_ambassador(db, user_id)
    # Phase 10b — RJ stinger (60-min cooldown)
    try:
        await enqueue_badge_earned_rj_extra(db, user_id=user_id, badge=badge)
    except Exception as e:
        logger.warning(f"admin_grant rj extra: {e}")
    return {
        "awarded": True,
        "already_owned": False,
        "award_id": award_id,
        "badge_id": canonical_bid,
        "user_id": user_id,
        "badge": {
            "name": badge.get("name"),
            "category": badge.get("category"),
            "tier": badge.get("tier"),
            "points": int(badge.get("points") or 0),
        },
        "state": {
            "level": new_state.get("level"),
            "points": new_state.get("points"),
            "badge_count": new_state.get("badge_count"),
        },
        "delta": {
            "points_delta": int(new_state.get("points") or 0) - prev_points,
            "level_delta": int(new_state.get("level") or 1) - prev_level,
            "level_changed_from": prev_level,
            "level_changed_to": int(new_state.get("level") or 1),
        },
    }


async def recompute_ambassador(db, user_id: str) -> dict:
    """Sum points across earned Phase-10a badges, set level + state."""
    pipe = [
        {"$match": {"user_id": user_id}},
        {"$lookup": {
            "from": "badges", "localField": "badge_id",
            "foreignField": "badge_id", "as": "badge"}},
        {"$unwind": {"path": "$badge", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": None,
            "total_points": {"$sum": "$badge.points"},
            "badges": {"$sum": 1},
            "by_category": {"$push": "$badge.category"},
        }},
    ]
    out = await db.user_badges.aggregate(pipe).to_list(1)
    points = int((out[0] or {}).get("total_points") or 0) if out else 0
    badge_count = int((out[0] or {}).get("badges") or 0) if out else 0
    # Determine level from ambassador_levels
    levels = [lvl async for lvl in db.ambassador_levels.find()
                          .sort("level", -1)]
    chosen = next((lvl for lvl in levels if points >= int(lvl["min_points"])),
                       levels[-1] if levels else {"level": 1, "min_points": 0,
                                                          "name": "Listener"})
    # Find next threshold
    next_thr = None
    next_name = None
    for lvl in sorted(levels, key=lambda x: x["level"]):
        if lvl["level"] > chosen["level"]:
            next_thr = int(lvl["min_points"])
            next_name = lvl["name"]
            break
    progress_to_next = None
    if next_thr is not None and next_thr > chosen["min_points"]:
        progress_to_next = round(
            (points - chosen["min_points"])
            / max(1, next_thr - chosen["min_points"]) * 100, 1)
    upd = {
        "user_id": user_id,
        "level": chosen["level"],
        "level_name": chosen["name"],
        "points": points,
        "badge_count": badge_count,
        "next_level_threshold": next_thr,
        "next_level_name": next_name,
        "progress_to_next_pct": progress_to_next,
        "updated_at": _now(),
    }
    # Phase 10b — capture pre-transition level so we can claim perks
    prev_state = await db.user_ambassador_state.find_one({"user_id": user_id})
    prev_level = int((prev_state or {}).get("level") or 0)
    await db.user_ambassador_state.update_one(
        {"user_id": user_id},
        {"$set": upd,
          "$setOnInsert": {"created_at": _now(),
                              "level_achieved_at": _now(),
                              "rewards_claimed_for_level": []}},
        upsert=True)
    # Phase 10b — atomic level-up reward claim (idempotent via the
    # rewards_claimed_for_level set on the state doc).
    if chosen["level"] > prev_level:
        try:
            from services.passport_public import claim_level_up_rewards
            claimed = await claim_level_up_rewards(
                db, user_id=user_id,
                new_level=int(chosen["level"]),
                prev_level=int(prev_level))
            if claimed:
                upd["just_claimed_rewards"] = claimed
                # bump level_achieved_at
                await db.user_ambassador_state.update_one(
                    {"user_id": user_id},
                    {"$set": {"level_achieved_at": _now()}})
        except Exception as e:
            logger.warning(f"level-up reward claim u={user_id}: {e}")
    return upd


# ─── Periodic sweep ────────────────────────────────────────────────────
async def sweep(db, *, batch_limit: int = 200) -> dict:
    """Re-evaluate streak / rolling-window badges for recently active
    users.  Run every 5 min from the FastAPI lifespan."""
    cutoff = _now() - timedelta(minutes=10)
    recent_uids: set[str] = set()
    async for d in db.bigcoin_transactions.find(
            {"reason": "heartbeat", "created_at": {"$gte": cutoff}},
            {"user_id": 1, "_id": 0}).limit(batch_limit):
        recent_uids.add(d["user_id"])
    awarded = 0
    for uid in recent_uids:
        out = await evaluate(db, uid, "bigcoin_heartbeat", {})
        awarded += len(out)
    return {"users_checked": len(recent_uids),
              "badges_awarded": awarded}


async def background_sweep_task(app) -> None:
    db = app.state.db
    while True:
        try:
            await asyncio.sleep(300)
            out = await sweep(db)
            if out.get("badges_awarded"):
                logger.info(f"badge sweep: {out}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"badge sweep error: {e}")


# ─── Views ─────────────────────────────────────────────────────────────
def badge_view(b: dict) -> dict:
    return {
        "badge_id": b.get("badge_id"),
        "name": b.get("name"),
        "description": b.get("description"),
        "category": b.get("category"),
        "tier": b.get("tier"),
        "points": int(b.get("points") or 0),
        "icon_url": b.get("icon_url"),
        "secret": bool(b.get("secret")),
        "active": bool(b.get("active")),
        "criteria_summary": _criteria_human_summary(
            b.get("criteria_json") or {}),
    }


def _criteria_human_summary(c: dict) -> str:
    t = c.get("type")
    if t == "counter":
        what = (c.get("source_event") or "").replace("_", " ")
        return f"{what} ×{c.get('target')}"
    if t == "listening_minutes":
        return f"Listen {int(c.get('target', 0)) // 60} hour(s)"
    if t == "geo_listening":
        city = (c.get("filters") or {}).get("city") or "city"
        return f"Listen {int(c.get('target', 0)) // 60}h in {city}"
    if t == "streak_days":
        return f"Listen {c.get('target')} days in a row"
    if t == "compound":
        return "Complete a multi-step challenge"
    if t == "admin_only":
        return "Awarded by the FUUSIC team"
    return "—"


__all__ = [
    "ensure_passport_indexes",
    "seed_badge_catalog", "seed_ambassador_levels",
    "evaluate", "admin_grant", "recompute_ambassador",
    "sweep", "background_sweep_task",
    "PHASE_10A_BADGE_CATALOG", "AMBASSADOR_LEVELS",
    "BADGE_CATEGORIES", "BADGE_TIERS", "SOURCE_EVENTS",
    "badge_view",
]
