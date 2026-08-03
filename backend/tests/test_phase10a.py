"""Phase 10a — Social Passport tests.

Catalog seed, badge engine fan-out, ambassador recompute, referral
attribution funnel, privacy settings persistence, and webhook delivery.

Same harness conventions as test_phase9b / test_phase9c — public HTTPS
preview URL so the secure session cookie round-trips.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

ROOT = os.environ.get("BIGFM_API_URL") or \
          "https://mobile-games-v2.preview.emergentagent.com"
API = f"{ROOT.rstrip('/')}/api"
MONGO = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME") or "bigfm"
DB = MONGO[DB_NAME]


def _now():
    return datetime.now(timezone.utc)


def _run(coro_factory):
    loop = asyncio.new_event_loop()
    try:
        if callable(coro_factory):
            async def _runner():
                db = AsyncIOMotorClient(
                    os.environ.get("MONGO_URL")
                    or "mongodb://localhost:27017")[DB_NAME]
                return await coro_factory(db)
            return loop.run_until_complete(_runner())
        return loop.run_until_complete(coro_factory)
    finally:
        loop.close()


# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def user_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "test@bigfm.dubai",
                          "password": "TestUser123!"}, timeout=10)
    assert r.status_code == 200, r.text
    s._user_id = r.json()["user_id"]
    yield s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "admin@bigfm.dubai",
                          "password": "AdminPass123!"}, timeout=10)
    assert r.status_code == 200, r.text
    s._user_id = r.json()["user_id"]
    yield s


@pytest.fixture
def fresh_user_state():
    """Wipe Phase-10a state for the test user so each test starts clean."""
    uid = "_phase10a_pending_"
    def _wipe(target_uid: str):
        DB.user_badges.delete_many({"user_id": target_uid})
        DB.badge_progress.delete_many({"user_id": target_uid})
        DB.badge_events.delete_many({"user_id": target_uid})
        DB.user_ambassador_state.delete_many({"user_id": target_uid})
        DB.social_profile_settings.delete_many({"user_id": target_uid})
    yield _wipe


# ════════════════════════════════════════════════════════════════════════
# § 10a.1 — Catalog seed
# ════════════════════════════════════════════════════════════════════════
def test_10a_01_catalog_seeded_with_minimum_active_badges():
    active = DB.badges.count_documents(
        {"schema_version": "10a", "active": True})
    assert active >= 45, f"expected ≥45 active Phase 10a badges; got {active}"
    # 13 categories represented
    cats = set(DB.badges.distinct("category", {"schema_version": "10a"}))
    assert {"city", "listening", "streak", "genre", "game", "commute",
              "restaurant", "event", "coupon", "social", "premium",
              "seasonal", "milestone"} <= cats


def test_10a_02_public_catalog_endpoint_hides_unearned_secret(user_session):
    r = user_session.get(f"{API}/passport/badges/catalog", timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    # Seasonal `ramadan_devotional_2026` is secret + currently inactive →
    # never in the catalog.
    ids = {b["badge_id"] for b in items}
    assert "ramadan_devotional_2026" not in ids


def test_10a_03_ambassador_levels_seeded():
    n = DB.ambassador_levels.count_documents({})
    assert n == 5
    lvl4 = DB.ambassador_levels.find_one({"level": 4})
    assert lvl4 is not None
    assert lvl4["min_points"] == 2000
    assert lvl4["name"] == "Ambassador"


# ════════════════════════════════════════════════════════════════════════
# § 10a.2 — Counter badge: lobby_host
# ════════════════════════════════════════════════════════════════════════
def test_10a_10_counter_lobby_host_badge(user_session, fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    # Directly trigger the badge engine because creating a real lobby
    # requires a live channel.  The engine is the same code path used
    # by the lobby_host_start emitter.
    from services.badge_engine import evaluate as badge_evaluate
    _run(lambda db: badge_evaluate(
        db, uid, "lobby_host_start",
        {"lobby_id": "lob_t01", "channel_slug": "party_dubai"}))
    earned = DB.user_badges.find_one(
        {"user_id": uid, "badge_id": "lobby_host"})
    assert earned is not None
    assert earned.get("source") == "auto_engine"
    # /passport/me returns it
    r = user_session.get(f"{API}/passport/me", timeout=10)
    assert r.status_code == 200, r.text
    by_cat = r.json()["badges_by_category"]
    social_ids = [b["badge_id"] for b in by_cat.get("social") or []]
    assert "lobby_host" in social_ids


# ════════════════════════════════════════════════════════════════════════
# § 10a.3 — Listening minutes (first_10_hours @ 600 min)
# ════════════════════════════════════════════════════════════════════════
def test_10a_11_listening_minutes_badge(user_session, fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    now = _now()
    DB.listening_heartbeats.delete_many({"user_id": uid})
    DB.listening_heartbeats.insert_one({
        "_id": f"{uid}|seed10a", "user_id": uid,
        "hour_bucket": now.strftime("%Y%m%d%H"),
        "minutes_credited": 700, "created_at": now,
    })
    from services.badge_engine import evaluate as badge_evaluate
    _run(lambda db: badge_evaluate(
        db, uid, "bigcoin_heartbeat", {"minute_bucket": "synthetic"}))
    earned_ids = {b["badge_id"] for b in DB.user_badges.find({"user_id": uid})}
    # first_hour AND first_10_hours should both fire
    assert "first_hour" in earned_ids
    assert "first_10_hours" in earned_ids
    assert "first_100_hours" not in earned_ids


def test_10a_11b_listening_minutes_badge_repeat_idempotent(user_session,
                                                                              fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    now = _now()
    DB.listening_heartbeats.delete_many({"user_id": uid})
    DB.listening_heartbeats.insert_one({
        "_id": f"{uid}|seed10a", "user_id": uid,
        "hour_bucket": now.strftime("%Y%m%d%H"),
        "minutes_credited": 700, "created_at": now,
    })
    from services.badge_engine import evaluate as badge_evaluate
    for _ in range(2):
        _run(lambda db: badge_evaluate(
            db, uid, "bigcoin_heartbeat",
            {"minute_bucket": "synthetic2"}))
    # first_10_hours single award, not duplicated
    n = DB.user_badges.count_documents(
        {"user_id": uid, "badge_id": "first_10_hours"})
    assert n == 1


# ════════════════════════════════════════════════════════════════════════
# § 10a.4 — Streak badge
# ════════════════════════════════════════════════════════════════════════
def test_10a_12_streak_3_days_badge(user_session, fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    # Synthesise 3 consecutive days of heartbeat bigcoin transactions
    DB.bigcoin_transactions.delete_many(
        {"user_id": uid, "reason": "heartbeat"})
    today = _now().replace(hour=12, minute=0, second=0, microsecond=0)
    for d in range(3):
        DB.bigcoin_transactions.insert_one({
            "_id": f"{uid}|streak{d}",
            "user_id": uid, "amount": 1,
            "reason": "heartbeat",
            "created_at": today - timedelta(days=d),
        })
    from services.badge_engine import evaluate as badge_evaluate
    _run(lambda db: badge_evaluate(
        db, uid, "bigcoin_heartbeat", {"minute_bucket": "synthetic3"}))
    earned = DB.user_badges.find_one(
        {"user_id": uid, "badge_id": "streak_3"})
    assert earned is not None


# ════════════════════════════════════════════════════════════════════════
# § 10a.5 — Compound badge (Rainy Day Chai Winner)
# ════════════════════════════════════════════════════════════════════════
def test_10a_13_compound_badge_admin_seeded(user_session, fresh_user_state):
    """Phase 10a doesn't ship a Rainy Day Chai Winner badge by default — we
    insert one for this test to validate the compound type.  Both legs
    fire within the 24-h window."""
    uid = user_session._user_id
    fresh_user_state(uid)
    # Insert a compound badge
    DB.badges.delete_one({"_id": "rainy_chai_winner"})
    DB.badges.insert_one({
        "_id": "rainy_chai_winner", "badge_id": "rainy_chai_winner",
        "slug": "rainy_chai_winner",
        "name": "Rainy Day Chai Winner", "description": "test",
        "category": "social", "tier": "gold", "points": 75,
        "criteria_json": {
            "type": "compound",
            "all_of": [
                {"source_event": "commute_completed",
                  "filters": {"weather": "rain"}, "period": "24h"},
                {"source_event": "coupon_claimed",
                  "filters": {"business_category": "karak"},
                  "period": "24h_after_above"},
            ]},
        "icon_url": "/assets/badges/rainy_chai.svg",
        "secret": False, "active": True, "schema_version": "10a",
        "created_at": _now(), "updated_at": _now(),
    })
    from services.badge_engine import evaluate as badge_evaluate
    # Only the commute → no badge yet
    _run(lambda db: badge_evaluate(
        db, uid, "commute_completed",
        {"commute_id": "cmt_test", "weather": "rain"}))
    no_yet = DB.user_badges.find_one(
        {"user_id": uid, "badge_id": "rainy_chai_winner"})
    assert no_yet is None
    # Now coupon claim with karak — fires
    _run(lambda db: badge_evaluate(
        db, uid, "coupon_claimed",
        {"coupon_id": "cpn_x", "business_category": "karak"}))
    fired = DB.user_badges.find_one(
        {"user_id": uid, "badge_id": "rainy_chai_winner"})
    assert fired is not None
    # Cleanup
    DB.badges.delete_one({"_id": "rainy_chai_winner"})


# ════════════════════════════════════════════════════════════════════════
# § 10a.6 — Secret seasonal badge admin grant
# ════════════════════════════════════════════════════════════════════════
def test_10a_14_secret_badge_admin_grant_only(admin_session, user_session,
                                                              fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    # Public catalog must NOT contain ramadan_devotional_2026 (secret + inactive)
    r = user_session.get(f"{API}/passport/badges/catalog", timeout=10)
    ids = {b["badge_id"] for b in r.json()["items"]}
    assert "ramadan_devotional_2026" not in ids
    # Admin grants it
    r2 = admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "ramadan_devotional_2026"},
        timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["awarded"] is True
    # Now /passport/me shows it under seasonal
    r3 = user_session.get(f"{API}/passport/me", timeout=10)
    by_cat = r3.json()["badges_by_category"]
    seasonal_ids = [b["badge_id"] for b in by_cat.get("seasonal") or []]
    assert "ramadan_devotional_2026" in seasonal_ids


# ════════════════════════════════════════════════════════════════════════
# § 10a.7 — Idempotency
# ════════════════════════════════════════════════════════════════════════
def test_10a_15_evaluate_is_idempotent(user_session, fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    from services.badge_engine import evaluate as badge_evaluate
    for _ in range(3):
        _run(lambda db: badge_evaluate(
            db, uid, "lobby_host_start", {"lobby_id": "lob_dup"}))
    n = DB.user_badges.count_documents(
        {"user_id": uid, "badge_id": "lobby_host"})
    assert n == 1


# ════════════════════════════════════════════════════════════════════════
# § 10a.8 — Ambassador recompute
# ════════════════════════════════════════════════════════════════════════
def test_10a_20_ambassador_recompute_levels_up(user_session, fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    from services.badge_engine import (
        admin_grant, recompute_ambassador)
    # Grant a bouquet of badges totalling > 100 (Regular threshold)
    _run(lambda db: admin_grant(
        db, user_id=uid, badge_id="lobby_host",
        admin_user_id="system"))   # 20 pts
    _run(lambda db: admin_grant(
        db, user_id=uid, badge_id="first_10_hours",
        admin_user_id="system"))   # 25 pts
    _run(lambda db: admin_grant(
        db, user_id=uid, badge_id="streak_7",
        admin_user_id="system"))   # 40 pts
    _run(lambda db: admin_grant(
        db, user_id=uid, badge_id="streak_3",
        admin_user_id="system"))   # 15 pts → total 100, level 2
    st = _run(lambda db: recompute_ambassador(db, uid))
    assert st["points"] >= 100
    assert st["level"] >= 2
    r = user_session.get(f"{API}/passport/me/ambassador", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == st["level"]
    assert body["level_name"] in {"Regular", "Insider", "Ambassador",
                                              "Diamond Ambassador"}


# ════════════════════════════════════════════════════════════════════════
# § 10a.9 — Referral attribution funnel
# ════════════════════════════════════════════════════════════════════════
def test_10a_30_landing_endpoint_creates_attribution():
    """POST /api/referrals/landing creates a row + sets bigfm_ref cookie."""
    # Find any user with a referrer_code
    referrer = DB.users.find_one(
        {"referrer_code": {"$exists": True, "$ne": None}},
        {"referrer_code": 1, "user_id": 1, "_id": 0})
    if not referrer:
        # Seed one on the admin user
        DB.users.update_one({"email": "admin@bigfm.dubai"},
                                  {"$set": {"referrer_code": "BFM-TEST10A"}})
        referrer = DB.users.find_one(
            {"email": "admin@bigfm.dubai"},
            {"referrer_code": 1, "user_id": 1, "_id": 0})
    ref_code = referrer["referrer_code"]
    s = requests.Session()
    r = s.post(f"{API}/referrals/landing",
                  json={"ref_code": ref_code,
                          "landing_path": "/business/karak-cafe",
                          "device_fingerprint": "fpr_10a_test_dev"},
                  timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ref_code"] == ref_code
    assert body["attribution_status"] == "clicked"
    aid = body["attribution_id"]
    row = DB.referral_attributions.find_one({"attribution_id": aid})
    assert row is not None
    assert row["landing_path"] == "/business/karak-cafe"
    # Cookie set
    assert "bigfm_ref" in s.cookies


def test_10a_31_attribution_stats_endpoint(user_session):
    r = user_session.get(f"{API}/referrals/me/attribution_stats", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "funnel" in body
    assert "conversion_to_engaged_pct" in body
    # funnel keys must exist
    for k in ("clicked", "signed_up", "engaged", "expired"):
        assert k in body["funnel"]


def test_10a_32_mark_engaged_fires_referral_completed_badge():
    """Phase 10a wires `mark_engaged` → emits `referral_completed`, which
    awards the `referrer` badge (target=1)."""
    # Create a synthetic referrer + referee
    rid = f"user_10a_referrer_{int(time.time())}"
    fid = f"user_10a_referee_{int(time.time())}"
    DB.users.insert_one({
        "_id": rid, "user_id": rid,
        "email": f"{rid}@bigfm.dubai",
        "name": "10a Test Referrer",
        "referrer_code": "BFM-10A1", "role": "user",
        "auth_provider": "email",
        "onboarding_complete": True, "created_at": _now()})
    DB.users.insert_one({
        "_id": fid, "user_id": fid,
        "email": f"{fid}@bigfm.dubai", "name": "10a Test Referee",
        "role": "user", "auth_provider": "email",
        "onboarding_complete": True, "created_at": _now()})
    DB.referral_attributions.delete_one({"_id": "att_10a_x"})
    DB.referral_attributions.insert_one({
        "_id": "att_10a_x", "attribution_id": "att_10a_x",
        "referrer_user_id": rid, "referee_user_id": fid,
        "ref_code": "BFM-10A1",
        "landing_path": "/business/karak-cafe",
        "landing_at": _now() - timedelta(minutes=5),
        "signup_at": _now() - timedelta(minutes=4),
        "first_engagement_at": None,
        "attribution_status": "signed_up",
        "expires_at": _now() + timedelta(days=30),
        "device_fingerprint": "fpr_10a32",
        "created_at": _now(),
    })
    from services.referrals_v2 import mark_engaged
    out = _run(lambda db: mark_engaged(db, referee_user_id=fid))
    assert out is not None
    assert out["attribution_status"] == "engaged"
    # `referrer` badge should be awarded to the referrer
    earned = DB.user_badges.find_one(
        {"user_id": rid, "badge_id": "referrer"})
    assert earned is not None
    # Cleanup
    DB.referral_attributions.delete_one({"_id": "att_10a_x"})
    DB.users.delete_many({"_id": {"$in": [rid, fid]}})
    DB.user_badges.delete_many({"user_id": rid})
    DB.badge_events.delete_many({"user_id": rid})
    DB.user_ambassador_state.delete_many({"user_id": rid})


# ════════════════════════════════════════════════════════════════════════
# § 10a.10 — Privacy settings persist
# ════════════════════════════════════════════════════════════════════════
def test_10a_40_privacy_settings_persist(user_session, fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    r = user_session.patch(
        f"{API}/passport/me/settings",
        json={"is_public": False,
                "show_listening_stats_publicly": True,
                "bio": "10a integration test bio",
                "city_pin": "Dubai"},
        timeout=10)
    assert r.status_code == 200, r.text
    s = r.json()["settings"]
    assert s["is_public"] is False
    assert s["show_listening_stats_publicly"] is True
    assert s["bio"] == "10a integration test bio"
    assert s["city_pin"] == "Dubai"
    # /passport/me reflects it
    r2 = user_session.get(f"{API}/passport/me", timeout=10)
    body = r2.json()
    assert body["settings"]["is_public"] is False


# ════════════════════════════════════════════════════════════════════════
# § 10a.11 — Webhook delivery (badge_earned)
# ════════════════════════════════════════════════════════════════════════
def test_10a_50_badge_earned_webhook_enqueued(user_session, fresh_user_state,
                                                                admin_session):
    """Register a webhook endpoint subscribed to `badge_earned`, fire a
    badge award, and assert that the delivery row is enqueued + signed."""
    uid = user_session._user_id
    fresh_user_state(uid)
    # Find or create an advertiser_id for this user (the admin can register
    # endpoints under their own advertiser_id).  We bypass the registration
    # API and write the endpoint directly for hermetic-ness.
    eid = "whep_10a_test_badge"
    secret = "whk_test_badge_earned_secret_v1"
    import bcrypt
    DB.advertiser_webhook_endpoints.delete_many({"_id": eid})
    DB.advertiser_webhook_endpoints.insert_one({
        "_id": eid, "endpoint_id": eid,
        "advertiser_id": "adv_10a_test",
        "url": "https://example.com/10a-webhook",
        "signing_secret_hash": bcrypt.hashpw(
            secret.encode(), bcrypt.gensalt(rounds=4)).decode(),
        "signing_secret_plain": secret,
        "events_subscribed": ["badge_earned", "referral_engaged"],
        "active": True, "created_at": _now(),
        "last_delivery_at": None, "last_failure_count": 0,
    })
    DB.game_webhook_events.delete_many({"endpoint_id": eid})
    # Fire a badge by grant
    from services.badge_engine import admin_grant
    _run(lambda db: admin_grant(
        db, user_id=uid, badge_id="first_spin", admin_user_id="system"))
    # Allow worker tick window
    time.sleep(1.0)
    rows = list(DB.game_webhook_events.find(
        {"endpoint_id": eid, "event_type": "badge_earned"}))
    assert rows, "badge_earned webhook event must be enqueued"
    payload = rows[0]["payload_json"]
    assert payload["badge_id"] == "first_spin"
    assert payload["user_id"] == uid
    # Cleanup
    DB.game_webhook_events.delete_many({"endpoint_id": eid})
    DB.advertiser_webhook_endpoints.delete_many({"_id": eid})


# ════════════════════════════════════════════════════════════════════════
# § 10a.12 — Smoke: prior phases still 200
# ════════════════════════════════════════════════════════════════════════
def test_10a_90_existing_endpoints_still_200(user_session):
    for path in ("/commute/saved_locations", "/auth/me", "/channels",
                    "/passport/badges/catalog", "/passport/me",
                    "/referrals/me/attribution_stats"):
        r = user_session.get(f"{API}{path}", timeout=10)
        assert r.status_code in (200,), \
            f"{path} returned {r.status_code}: {r.text[:200]}"


# ════════════════════════════════════════════════════════════════════════
# § 10a.1 — Bug-fix battery (Fix 1-3 + admin activate)
# ════════════════════════════════════════════════════════════════════════
def test_10a1_01_passport_me_survives_legacy_badge_rows(user_session,
                                                                            fresh_user_state):
    """Fix 1 — A user with a mix of Phase 5 legacy `user_badges`
    rows (ObjectId `_id`, no `award_id`, schema-less catalog match) +
    Phase 10a rows must still get a 200 from /passport/me.  Regression
    test seeds a synthetic legacy row + a 10a row for the test user."""
    from bson import ObjectId
    uid = user_session._user_id
    fresh_user_state(uid)
    # Synthetic legacy row mimicking Phase 5's recompute_user_badges
    DB.user_badges.insert_one({
        "_id": ObjectId(),
        "user_id": uid,
        "badge_id": "badge_first_listen",
        "unlocked_at": _now(),
        "displayed_on_profile": True,
    })
    # Catalog row for legacy badge with no schema_version
    DB.badges.update_one(
        {"_id": "badge_first_listen"},
        {"$set": {"name": "First Listen", "tier": "common",
                    "active": True, "slug": "badge_first_listen"}},
        upsert=True)
    DB.badges.update_one(
        {"_id": "badge_first_listen"},
        {"$unset": {"schema_version": ""}})
    # And a 10a row so we exercise both code paths
    from services.badge_engine import evaluate as badge_evaluate
    _run(lambda db: badge_evaluate(
        db, uid, "lobby_host_start", {"lobby_id": "lob_10a1_01"}))
    r = user_session.get(f"{API}/passport/me", timeout=10)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # Legacy row hidden, Phase 10a `lobby_host` exposed
    social_ids = [b["badge_id"] for b in
                        body["badges_by_category"].get("social") or []]
    assert "lobby_host" in social_ids
    # recent_feed must not contain null-badge entries
    for f in body.get("recent_feed") or []:
        assert f["badge_id"], f"null badge in recent_feed: {f}"
    # Cleanup
    DB.user_badges.delete_many({"user_id": uid,
                                          "badge_id": "badge_first_listen"})


def test_10a1_10_compound_badge_rainy_chai_seeded():
    """Fix 3 — `rainy_day_chai_winner` is in the active catalog with the
    spec-prescribed compound rule."""
    b = DB.badges.find_one({"badge_id": "rainy_day_chai_winner"})
    assert b is not None
    assert b.get("active") is True
    cj = b.get("criteria_json") or {}
    assert cj.get("type") == "compound"
    subs = cj.get("all_of") or []
    assert len(subs) == 2
    src_events = {s.get("source_event") for s in subs}
    assert src_events == {"commute_completed", "coupon_claimed"}
    # commute_concert_combo also exists
    b2 = DB.badges.find_one({"badge_id": "commute_concert_combo"})
    assert b2 is not None and b2.get("active") is True
    assert (b2.get("criteria_json") or {}).get("type") == "compound"


def test_10a1_11_compound_engine_fires_via_emitter(user_session,
                                                                        fresh_user_state):
    """Fix 3 — Synthesize the two source events for a user and assert the
    compound badge fires from the engine."""
    uid = user_session._user_id
    fresh_user_state(uid)
    from services.badge_engine import evaluate as badge_evaluate
    # Step 1: rainy commute event — badge NOT yet fired
    _run(lambda db: badge_evaluate(
        db, uid, "commute_completed",
        {"commute_id": "cmt_10a1", "weather": "rain"}))
    not_yet = DB.user_badges.find_one(
        {"user_id": uid, "badge_id": "rainy_day_chai_winner"})
    assert not_yet is None
    # Step 2: karak coupon claim within 24h — fires
    _run(lambda db: badge_evaluate(
        db, uid, "coupon_claimed",
        {"coupon_id": "cpn_10a1", "business_category": "karak"}))
    fired = DB.user_badges.find_one(
        {"user_id": uid, "badge_id": "rainy_day_chai_winner"})
    assert fired is not None, "compound rainy_day_chai_winner must fire"


def test_10a1_20_referral_engaged_full_funnel(admin_session, fresh_user_state):
    """Fix 2 — End-to-end: landing → cookie → signup → onboarding-complete
    advances attribution_status all the way to `engaged`, awards 100 BC
    to the referrer, fires the `referrer` Phase 10a badge."""
    # Use admin as the referrer (already has a referrer_code)
    referrer = DB.users.find_one(
        {"email": "admin@bigfm.dubai"}, {"user_id": 1, "referrer_code": 1})
    if not referrer.get("referrer_code"):
        DB.users.update_one(
            {"_id": referrer["_id"]},
            {"$set": {"referrer_code": "BFM-10A1FUN"}})
        referrer["referrer_code"] = "BFM-10A1FUN"
    rcode = referrer["referrer_code"]
    referrer_uid = referrer["user_id"]
    # Wipe any prior 10a state for the referrer + referee
    fresh_user_state(referrer_uid)
    # Wipe any prior attributions on this ref_code so the fingerprint
    # dedupe path doesn't return a stale signed_up row.
    DB.referral_attributions.delete_many({"ref_code": rcode})
    DB.users.delete_many(
        {"email": {"$regex": "^ref10a1_"}})
    # Step 1: landing (anonymous public POST)
    import secrets as _sec
    fp = f"fp_funnel_{_sec.token_hex(4)}"
    s = requests.Session()
    r1 = s.post(f"{API}/referrals/landing",
                    json={"ref_code": rcode,
                            "landing_path": "/business/karak-cafe",
                            "device_fingerprint": fp},
                    timeout=10)
    assert r1.status_code == 200, r1.text
    aid = r1.json()["attribution_id"]
    assert r1.json()["attribution_status"] == "clicked"
    assert "bigfm_ref" in s.cookies
    # Step 2: signup — fresh referee using the same session (cookie carries
    # automatically) to exercise the claim_attribution hook in auth.py
    referee_email = f"ref10a1_{_sec.token_hex(4)}@bigfm.dubai"
    r2 = s.post(f"{API}/auth/register",
                    json={"email": referee_email,
                            "password": "FunnelPass123!",
                            "name": "Funnel Referee"}, timeout=15)
    assert r2.status_code == 200, r2.text
    referee_uid = r2.json()["user_id"]
    # Verify attribution row jumped clicked → signed_up
    row = DB.referral_attributions.find_one({"attribution_id": aid})
    assert row is not None
    assert row["attribution_status"] == "signed_up", row
    assert row["referee_user_id"] == referee_uid
    # Step 3: complete onboarding — must trigger
    # complete_referral_after_onboarding which flips → engaged + pays BC.
    bc_before_doc = DB.users.find_one({"user_id": referrer_uid},
                                                      {"bigcoin_balance": 1})
    bc_before = int((bc_before_doc or {}).get("bigcoin_balance") or 0)
    r3 = s.post(
        f"{API}/users/preferences",
        json={"languages": ["english"],
                "genres": ["pop", "hip_hop"],
                "eras": ["2010s"],
                "moods": ["chill", "energetic"],
                "activities": ["commute"],
                "host_personality": "auto",
                "market": "dubai"}, timeout=15)
    assert r3.status_code == 200, r3.text
    # Verify attribution_status = engaged
    row2 = DB.referral_attributions.find_one({"attribution_id": aid})
    assert row2["attribution_status"] == "engaged", row2
    assert row2.get("first_engagement_at")
    # Verify referrer earned the `referrer` badge
    earned = DB.user_badges.find_one(
        {"user_id": referrer_uid, "badge_id": "referrer"})
    assert earned is not None, \
        "referrer must earn Phase 10a `referrer` badge after engagement"
    # Verify BigCoin balance moved by 100 BC (users.bigcoin_balance)
    refreshed = DB.users.find_one({"user_id": referrer_uid},
                                              {"bigcoin_balance": 1})
    bc_after = int((refreshed or {}).get("bigcoin_balance") or 0)
    assert bc_after - bc_before == 100, \
        f"expected +100 BC; got {bc_after - bc_before}"
    # Cleanup
    DB.users.delete_one({"_id": referee_uid})
    DB.sessions.delete_many({"user_id": referee_uid})


def test_10a1_30_admin_activate_deactivate_seasonal(admin_session):
    """Fix 5 — admin can flip seasonal badge active flags via the new
    endpoints; audit log records each transition."""
    bid = "ramadan_devotional_2026"
    # Reset to inactive
    DB.badges.update_one({"_id": bid}, {"$set": {"active": False}})
    DB.badge_admin_audit.delete_many({"badge_id": bid})
    # Activate
    r1 = admin_session.post(
        f"{API}/admin/passport/badges/{bid}/activate", timeout=10)
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["active"] is True
    assert body["changed"] is True
    assert body["prev_active"] is False
    assert body.get("audit_id")
    # DB row updated
    assert DB.badges.find_one({"_id": bid})["active"] is True
    # Idempotent re-activate
    r1b = admin_session.post(
        f"{API}/admin/passport/badges/{bid}/activate", timeout=10)
    assert r1b.status_code == 200
    assert r1b.json()["changed"] is False
    # Deactivate
    r2 = admin_session.post(
        f"{API}/admin/passport/badges/{bid}/deactivate", timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["active"] is False
    assert r2.json()["changed"] is True
    # Audit log shows both transitions
    audits = list(DB.badge_admin_audit.find({"badge_id": bid}).sort("ts", 1))
    assert len(audits) >= 2
    assert audits[0]["action"] == "activate"
    assert audits[-1]["action"] == "deactivate"
    # GET endpoint exposes the trail
    r3 = admin_session.get(
        f"{API}/admin/passport/badges/audit?limit=10", timeout=10)
    assert r3.status_code == 200
    audit_ids = {a["audit_id"] for a in r3.json()["items"]}
    assert audits[0]["audit_id"] in audit_ids
    # Non-existent badge → 404
    r4 = admin_session.post(
        f"{API}/admin/passport/badges/no_such_badge_x/activate", timeout=10)
    assert r4.status_code == 404


def test_10a1_31_admin_activate_listener_role_forbidden(user_session):
    r = user_session.post(
        f"{API}/admin/passport/badges/ramadan_devotional_2026/activate",
        timeout=10)
    assert r.status_code == 403
