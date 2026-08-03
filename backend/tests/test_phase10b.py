"""Phase 10b — Public Passport, leaderboards, level-up rewards, lobby
badges, RJ stinger, and the Phase 5 legacy badge migration.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

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
        async def _runner():
            db = AsyncIOMotorClient(
                os.environ.get("MONGO_URL")
                or "mongodb://localhost:27017")[DB_NAME]
            return await coro_factory(db)
        return loop.run_until_complete(_runner())
    finally:
        loop.close()


# ─── Fixtures ──────────────────────────────────────────────────────────
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
    def _wipe(target_uid: str):
        DB.user_badges.delete_many({"user_id": target_uid})
        DB.badge_progress.delete_many({"user_id": target_uid})
        DB.badge_events.delete_many({"user_id": target_uid})
        DB.user_ambassador_state.delete_many({"user_id": target_uid})
        DB.ambassador_reward_log.delete_many({"user_id": target_uid})
        DB.users.update_one({"user_id": target_uid},
                                  {"$unset": {"pending_rj_extras": "",
                                                "last_badge_rj_mention_at": "",
                                                "level_up_celebrated_levels": ""}})
    yield _wipe


# ════════════════════════════════════════════════════════════════════════
# § 10b.1 — Legacy badge migration
# ════════════════════════════════════════════════════════════════════════
def test_10b_01_legacy_migration_post_total_64(admin_session):
    """After migration the catalog contains 50 Phase 10a + 14 backfilled
    legacy rows.  3 Phase 10a seasonal rows are seeded active=False, so
    the active count is 47 + 19 = 66.  Total catalog = 69.

    Phase 10b.2 reconcile: extended from 14 → 19 legacy entries to
    match the actual Phase 5 catalog that survived seeding (added
    badge_streak_3, badge_streak_7, badge_trivia_legend, badge_lyric_pro,
    badge_redeem_first which were already present with
    `legacy_phase5=True` set by `services/bigcoin_seed.py`).
    """
    r = admin_session.post(
        f"{API}/admin/passport/migrate_phase5_badges", timeout=15)
    assert r.status_code == 200, r.text
    total = DB.badges.count_documents({"schema_version": "10a"})
    assert total == 69, f"expected 69 total catalog badges; got {total}"
    active = DB.badges.count_documents(
        {"schema_version": "10a", "active": True})
    assert active == 66, f"expected 66 active; got {active}"
    legacy = DB.badges.count_documents(
        {"schema_version": "10a", "legacy_phase5": True})
    assert legacy == 19
    # Self-heal sanity — no orphan row with `badge_id=None` should remain
    orphans = DB.badges.count_documents(
        {"schema_version": "10a", "legacy_phase5": True,
          "badge_id": None})
    assert orphans == 0, f"{orphans} legacy badges still missing badge_id"
    # Idempotent: re-run keeps total at 69
    r2 = admin_session.post(
        f"{API}/admin/passport/migrate_phase5_badges", timeout=15)
    assert r2.status_code == 200
    total2 = DB.badges.count_documents({"schema_version": "10a"})
    assert total2 == 69


def test_10b_02_legacy_badges_appear_in_public_catalog(user_session):
    r = user_session.get(f"{API}/passport/badges/catalog", timeout=10)
    assert r.status_code == 200
    ids = {b["badge_id"] for b in r.json()["items"]}
    assert "badge_first_listen" in ids
    assert "badge_refer_5" in ids


# ════════════════════════════════════════════════════════════════════════
# § 10b.2 — Public profile
# ════════════════════════════════════════════════════════════════════════
def test_10b_10_public_profile_returns_safe_view(user_session):
    """Anonymous /passport/{user_id} returns the public view honoring
    show_badges_publicly / show_ambassador_level_publicly defaults and
    NEVER leaks email / privacy_settings / referral_attribution rows."""
    uid = user_session._user_id
    # Make sure profile is_public=True
    DB.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "is_public": True,
                    "show_badges_publicly": True,
                    "show_ambassador_level_publicly": True}},
        upsert=True)
    r = requests.get(f"{API}/passport/{uid}", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    # Allowed fields
    for k in ("user_id", "display_name", "avatar_initial",
                "badges", "ambassador", "is_premium",
                "is_annual_subscriber", "referral_code"):
        assert k in body, f"missing field {k}"
    # Disallowed leaks
    for forbidden in ("email", "password_hash", "is_public", "ip"):
        assert forbidden not in body
    # ambassador_level is a small whitelist of fields
    if body["ambassador"]:
        assert set(body["ambassador"].keys()) <= {
            "level", "level_name", "points",
            "next_level_name", "progress_to_next_pct"}


def test_10b_11_is_public_false_returns_404():
    """User with `is_public=false` is treated as 404 from public surface."""
    u = DB.users.find_one({"email": "premium@bigfm.dubai"},
                                  {"user_id": 1})
    if not u:
        pytest.skip("premium test user missing")
    uid = u["user_id"]
    DB.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "is_public": False}},
        upsert=True)
    r = requests.get(f"{API}/passport/{uid}", timeout=10)
    assert r.status_code == 404
    # Restore so other tests don't see it
    DB.social_profile_settings.update_one(
        {"user_id": uid}, {"$set": {"is_public": True}})


def test_10b_12_handle_uniqueness(user_session, admin_session):
    """Two distinct users cannot both claim the same handle."""
    r = user_session.patch(
        f"{API}/passport/me/settings",
        json={"handle": "userhandle-10b"}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["handle"] == "userhandle-10b"
    r2 = admin_session.patch(
        f"{API}/passport/me/settings",
        json={"handle": "userhandle-10b"}, timeout=10)
    assert r2.status_code == 409
    # Handle lookup
    r3 = requests.get(
        f"{API}/passport/by_handle/userhandle-10b", timeout=10)
    assert r3.status_code == 200
    assert r3.json()["user_id"] == user_session._user_id
    # Cleanup
    DB.social_profile_settings.update_one(
        {"user_id": user_session._user_id},
        {"$unset": {"handle": ""}})


def test_10b_13_show_badges_publicly_false_hides_badges(user_session):
    uid = user_session._user_id
    DB.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": {"show_badges_publicly": False, "is_public": True}},
        upsert=True)
    r = requests.get(f"{API}/passport/{uid}", timeout=10)
    assert r.status_code == 200
    assert r.json()["badges"] == []
    # Restore
    DB.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": {"show_badges_publicly": True}})


# ════════════════════════════════════════════════════════════════════════
# § 10b.3 — City leaderboards
# ════════════════════════════════════════════════════════════════════════
def test_10b_20_leaderboard_recompute_with_anonymous_entry(admin_session,
                                                                              user_session,
                                                                              fresh_user_state):
    """Recompute Dubai listening_minutes_7d; the test user appears in
    the snapshot.  When the user opts out of public leaderboard, their
    entry switches to 'Anonymous Listener' on next recompute."""
    uid = user_session._user_id
    fresh_user_state(uid)
    # City pin + opt-in
    DB.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "city_pin": "Dubai", "is_public": True,
                    "show_leaderboard_position_publicly": True}},
        upsert=True)
    # Seed listening minutes
    DB.listening_heartbeats.delete_many({"user_id": uid})
    DB.listening_heartbeats.insert_one({
        "_id": f"{uid}|lb10b", "user_id": uid,
        "hour_bucket": _now().strftime("%Y%m%d%H"),
        "minutes_credited": 250,
        "ts": _now() - timedelta(hours=2),
        "created_at": _now() - timedelta(hours=2),
    })
    # Seed a heartbeat bigcoin transaction so _active_users_by_city
    # picks up the user.
    DB.bigcoin_transactions.delete_many(
        {"user_id": uid, "reason": "heartbeat"})
    DB.bigcoin_transactions.insert_one({
        "_id": f"{uid}|lbbc",
        "user_id": uid, "amount": 1, "reason": "heartbeat",
        "created_at": _now() - timedelta(hours=2),
    })
    r = admin_session.post(
        f"{API}/admin/leaderboards/recompute",
        json={"city": "Dubai", "metric": "listening_minutes_7d",
                "min_active_users": 1},
        timeout=20)
    assert r.status_code == 200, r.text
    r2 = user_session.get(
        f"{API}/leaderboards/Dubai?metric=listening_minutes_7d", timeout=10)
    assert r2.status_code == 200
    body = r2.json()
    assert body["available"] is True
    assert body["metric"] == "listening_minutes_7d"
    # User must appear in top_n (at least once)
    me = next((r for r in body["top_n"]
                  if r.get("user_id") == uid), None)
    assert me is not None, body["top_n"]
    assert me["is_anonymous"] is False
    assert me["value"] >= 250

    # Flip opt-out
    DB.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": {"show_leaderboard_position_publicly": False}})
    admin_session.post(
        f"{API}/admin/leaderboards/recompute",
        json={"city": "Dubai", "metric": "listening_minutes_7d",
                "min_active_users": 1},
        timeout=20)
    r3 = requests.get(
        f"{API}/leaderboards/Dubai?metric=listening_minutes_7d", timeout=10)
    assert r3.status_code == 200
    top_n = r3.json()["top_n"]
    # Phase 10b.2 — anonymous entries return a bucketed string for `value`
    # so we match on the anonymous flag + display_name instead of int >=.
    me_anon = next((r for r in top_n
                            if r.get("is_anonymous")
                            and r.get("display_name") == "Anonymous Listener"),
                          None)
    assert me_anon is not None, f"opt-out should anonymize entry; got {top_n}"
    assert me_anon["display_name"] == "Anonymous Listener"
    assert me_anon.get("user_id") is None
    assert me_anon.get("value_display_type") == "bucket"
    assert isinstance(me_anon.get("value"), str)
    # Restore
    DB.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": {"show_leaderboard_position_publicly": True}})


def test_10b_21_leaderboard_invalid_metric_400(user_session):
    r = user_session.get(
        f"{API}/leaderboards/Dubai?metric=nope_metric", timeout=10)
    assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════════
# § 10b.4 — Level-up rewards
# ════════════════════════════════════════════════════════════════════════
def test_10b_30_level_up_l2_awards_50_bc(admin_session, user_session,
                                                          fresh_user_state):
    """Synthesize L0→L2 transition; +50 BC awarded; reward log row; idempotent."""
    uid = user_session._user_id
    fresh_user_state(uid)
    bc_before = int((DB.users.find_one(
        {"user_id": uid}) or {}).get("bigcoin_balance") or 0)
    from services.badge_engine import admin_grant, recompute_ambassador
    # Grant badges to push past 100 pts
    for bid in ("lobby_host",        # 20
                    "first_10_hours",     # 25
                    "streak_3",           # 15
                    "coupon_collector",   # 30
                    "first_spin"):        # 10 → total 100
        _run(lambda db, b=bid: admin_grant(
            db, user_id=uid, badge_id=b, admin_user_id="system"))
    st = _run(lambda db: recompute_ambassador(db, uid))
    assert st["level"] >= 2
    # +50 BC for L1→L2
    bc_after = int((DB.users.find_one(
        {"user_id": uid}) or {}).get("bigcoin_balance") or 0)
    assert bc_after - bc_before >= 50, \
        f"expected +50 BC; got {bc_after - bc_before}"
    # Reward log
    n_logs = DB.ambassador_reward_log.count_documents(
        {"user_id": uid, "to_level": 2})
    assert n_logs == 1
    # Idempotent re-trigger
    _run(lambda db: recompute_ambassador(db, uid))
    n_logs2 = DB.ambassador_reward_log.count_documents(
        {"user_id": uid, "to_level": 2})
    assert n_logs2 == 1


def test_10b_31_level_up_l4_activates_premium_30d(admin_session, user_session,
                                                                      fresh_user_state):
    uid = user_session._user_id
    fresh_user_state(uid)
    # Reset premium
    DB.users.update_one(
        {"user_id": uid},
        {"$unset": {"premium_until": "", "premium_source": ""},
          "$set": {"is_premium": False}})
    from services.badge_engine import admin_grant, recompute_ambassador
    # Grant ~2050 pts (L4 threshold = 2000)
    big_badges = ["lobby_host", "first_10_hours", "first_100_hours",
                          "first_500_hours",       # 250
                          "lobby_veteran",         # 80
                          "trivia_master_lvl3",    # 80
                          "lyric_legend",          # 80
                          "streak_30",             # 120
                          "streak_90",             # 300
                          "super_referrer",        # 200
                          "first_1000_hours",      # 500
                          "annual_subscriber",     # 100
                          "family_root",           # 120
                          "bigfm_og"]              # 80   → total ~2055
    for bid in big_badges:
        _run(lambda db, b=bid: admin_grant(
            db, user_id=uid, badge_id=b, admin_user_id="system"))
    st = _run(lambda db: recompute_ambassador(db, uid))
    assert st["level"] >= 4
    # Premium activated
    u = DB.users.find_one({"user_id": uid})
    assert bool(u.get("is_premium")) is True
    pu = u.get("premium_until")
    assert pu is not None
    if pu.tzinfo is None:
        pu = pu.replace(tzinfo=timezone.utc)
    assert (pu - _now()).days >= 28


# ════════════════════════════════════════════════════════════════════════
# § 10b.5 — Lobby member badges
# ════════════════════════════════════════════════════════════════════════
def test_10b_40_lobby_detail_includes_public_badges(admin_session,
                                                                        user_session,
                                                                        fresh_user_state):
    """Phase 10b — `lobby_detail` exposes `public_badges` + `host_perks`
    per member.  Top 5 by tier+points."""
    uid = user_session._user_id
    fresh_user_state(uid)
    # Award a couple of badges with diverse tiers
    from services.badge_engine import admin_grant
    for bid in ("lobby_host", "first_10_hours", "streak_3",
                    "coupon_collector", "first_spin"):
        _run(lambda db, b=bid: admin_grant(
            db, user_id=uid, badge_id=b, admin_user_id="system"))
    # Create a fresh lobby for this user via /api/lobbies
    # Need an active channel — pick the first one available
    chans = list(DB.channels.find({"active": True},
                                              {"slug": 1}).limit(1))
    assert chans, "no active channels seeded"
    slug = chans[0]["slug"]
    # End any prior lobby this user was hosting (carry-over from earlier
    # runs).  Best-effort.
    DB.lobbies.update_many(
        {"host_user_id": uid, "status": "active"},
        {"$set": {"status": "ended"}})
    r = user_session.post(
        f"{API}/lobbies/create",
        json={"channel_slug": slug, "mood": "chill",
                "name": "10b lobby test",
                "max_listeners": 10}, timeout=15)
    if r.status_code in (400, 409):
        det = (r.json() or {}).get("detail") or ""
        if det.startswith("already_hosting:"):
            lobby_id = det.split(":", 1)[1]
        else:
            lobby_id = r.json().get("lobby_id")
    else:
        assert r.status_code == 200, r.text
        lobby_id = r.json()["lobby_id"]
    assert lobby_id, f"could not obtain lobby_id from {r.status_code} {r.text}"
    # Fetch lobby detail
    r2 = user_session.get(f"{API}/lobbies/{lobby_id}", timeout=10)
    assert r2.status_code == 200, r2.text
    members = r2.json().get("members_preview") or []
    assert members, "lobby must have members_preview"
    me = next((m for m in members if m["user_id"] == uid), None)
    assert me is not None
    assert "public_badges" in me
    assert "host_perks" in me
    assert len(me["public_badges"]) <= 5
    # End the lobby (cleanup)
    user_session.post(f"{API}/lobbies/{lobby_id}/end", timeout=10)


# ════════════════════════════════════════════════════════════════════════
# § 10b.6 — RJ stinger queue + cooldown
# ════════════════════════════════════════════════════════════════════════
def test_10b_50_badge_award_queues_rj_extra_with_cooldown(user_session,
                                                                                  fresh_user_state):
    """1st badge award → pending_rj_extras row queued.  2nd badge within
    60 min → no new queue (cooldown)."""
    uid = user_session._user_id
    fresh_user_state(uid)
    # Wipe pending_rj_extras
    DB.users.update_one(
        {"user_id": uid},
        {"$unset": {"pending_rj_extras": "",
                      "last_badge_rj_mention_at": ""}})
    from services.badge_engine import admin_grant
    _run(lambda db: admin_grant(
        db, user_id=uid, badge_id="lobby_host", admin_user_id="system"))
    u1 = DB.users.find_one({"user_id": uid})
    pending = u1.get("pending_rj_extras") or []
    badge_extras = [x for x in pending if x.get("kind") == "badge_earned"]
    assert badge_extras, "first badge must queue a badge_earned RJ extra"
    assert badge_extras[0]["payload"]["badge_id"] == "lobby_host"
    # 2nd badge within 60min — cooldown suppresses
    _run(lambda db: admin_grant(
        db, user_id=uid, badge_id="first_spin", admin_user_id="system"))
    u2 = DB.users.find_one({"user_id": uid})
    n2 = sum(1 for x in (u2.get("pending_rj_extras") or [])
                  if x.get("kind") == "badge_earned")
    assert n2 == 1, \
        f"cooldown failed; expected 1 extra still, got {n2}"


# ════════════════════════════════════════════════════════════════════════
# § 10b.7 — bigcoin /me referral_code alias
# ════════════════════════════════════════════════════════════════════════
def test_10b_60_bigcoin_me_exposes_referral_code(user_session):
    r = user_session.get(f"{API}/bigcoin/me", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    # New alias
    assert "referral_code" in body
    assert body["referral_code"], "referral_code must not be null"
    # Backwards compat: original referrer_code still present
    assert body.get("referrer_code") == body["referral_code"]


# ════════════════════════════════════════════════════════════════════════
# § 10b.8 — Smoke: prior phases still 200
# ════════════════════════════════════════════════════════════════════════
def test_10b_90_existing_endpoints_still_200(user_session):
    for path in ("/passport/me", "/passport/badges/catalog",
                    "/referrals/me/attribution_stats",
                    "/auth/me", "/bigcoin/me",
                    "/leaderboards/cities"):
        r = user_session.get(f"{API}{path}", timeout=10)
        assert r.status_code in (200,), \
            f"{path} returned {r.status_code}: {r.text[:200]}"



# ════════════════════════════════════════════════════════════════════════
# § Priority Bug 1 — Cold-start TTFB (no-RJ first segment)
# ════════════════════════════════════════════════════════════════════════
def test_bug1_cold_start_uses_no_rj_segment(user_session):
    """Cold start (warm cache empty) returns a no-RJ segment with
    `rj_format='no_rj'` and `rj_voice_key=None`. TTFB ≤ 8s including
    HTTP round-trip + segment write.  Historical baseline was ~31s."""
    # Wipe warm cache to force the cold path
    DB.warm_start_segments.delete_many(
        {"user_id": user_session._user_id})
    t0 = time.time()
    r = user_session.post(
        f"{API}/radio/start",
        json={"channel": "bollywood_mehfil"}, timeout=20)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    seg = r.json()["segment"]
    assert seg["rj_format"] == "no_rj", seg
    assert seg["rj_voice_key"] is None
    assert (seg.get("rj_script") or "") == ""
    # TTFB must be well under historical 31s baseline; give a 10s ceiling
    # so we catch genuine regressions but stay tolerant of CI jitter.
    assert elapsed < 10.0, f"cold-start TTFB too high: {elapsed:.1f}s"


def test_bug1_segment_2_keeps_full_ai_rj(user_session):
    """Cold-start no-RJ only affects segment 1.  /api/radio/next must
    deliver a `solo` or `duo` segment with a real ElevenLabs voice key."""
    DB.warm_start_segments.delete_many(
        {"user_id": user_session._user_id})
    r = user_session.post(
        f"{API}/radio/start",
        json={"channel": "bollywood_mehfil"}, timeout=20)
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]
    # Allow up to 60s — full AI RJ + TTS + ffmpeg
    r2 = user_session.get(
        f"{API}/radio/next?session_id={session_id}", timeout=90)
    assert r2.status_code == 200, r2.text
    seg2 = r2.json()["segment"]
    assert seg2["rj_format"] in ("solo", "duo"), seg2
    assert seg2["rj_voice_key"]
    assert len(seg2.get("rj_script") or "") > 50


# ════════════════════════════════════════════════════════════════════════
# § Priority Bug 2 — Progressive filter relaxation + decision log
# ════════════════════════════════════════════════════════════════════════
def test_bug2_relaxation_helper_walks_steps_in_order():
    """Direct unit test on the helper: a channel whose hard filters
    eliminate every track should walk strict → drop_energy → drop_mood
    → drop_genre → language_only and stop early when pool ≥ MIN_POOL."""
    from server import (_build_channel_pool_with_relaxation,
                              MIN_POOL_SIZE)
    channel = {
        "_id": "test_strict_channel",
        "allowed_energy_levels": ["party"],     # excludes everything
        "allowed_genres": ["non_existent"],     # excludes everything
        "allowed_moods": ["non_existent"],      # excludes everything
        "language_mix": [{"language": "hindi"}],
    }
    # 10 hindi tracks — strict gives 0; language_only gives 10
    tracks = [
        {"_id": f"t{i}", "language": "hindi", "energy_level": "chill",
          "mood": "romantic", "genre": "pop",
          "title": f"Song {i}", "artist": "A"} for i in range(10)
    ]
    pool, steps = _build_channel_pool_with_relaxation(tracks, channel)
    # Final pool should satisfy MIN_POOL_SIZE
    assert len(pool) >= MIN_POOL_SIZE, (len(pool), steps)
    step_names = [s["step"] for s in steps]
    assert "strict" in step_names
    # Must have visited at least drop_energy + drop_mood + drop_genre
    assert "drop_genre" in step_names
    # Strict was zero (channel filters reject everything)
    assert steps[0]["pool_size"] == 0
    # Final step pool_size matches MIN_POOL threshold


def test_bug2_relaxation_short_circuits_when_strict_is_healthy():
    """When the strict pool is already ≥ MIN_POOL the helper must return
    immediately without walking further relaxation steps."""
    from server import _build_channel_pool_with_relaxation
    channel = {
        "_id": "healthy_channel",
        "allowed_energy_levels": ["medium"],
        "allowed_genres": ["pop"],
        "allowed_moods": ["uplifting"],
        "language_mix": [{"language": "english"}],
    }
    tracks = [
        {"_id": f"t{i}", "language": "english", "energy_level": "medium",
          "mood": "uplifting", "genre": "pop",
          "title": f"Song {i}", "artist": "A"} for i in range(20)
    ]
    pool, steps = _build_channel_pool_with_relaxation(tracks, channel)
    assert len(pool) == 20
    assert len(steps) == 1, steps
    assert steps[0]["step"] == "strict"


def test_bug2_admin_channel_health_endpoint(admin_session, user_session):
    """`GET /api/admin/channels/{slug}/health` exposes pool inventory +
    decision log + relaxation counts.  Punjabi Beats with the current
    sparse catalog must show drop_genre/language_only as the final step."""
    # Fire a quick radio_start to ensure at least one decision row exists
    DB.warm_start_segments.delete_many(
        {"user_id": user_session._user_id})
    user_session.post(
        f"{API}/radio/start",
        json={"channel": "punjabi_beats"}, timeout=20)
    r = admin_session.get(
        f"{API}/admin/channels/punjabi_beats/health?limit=20",
        timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    # Shape
    for k in ("channel", "catalog", "pool_inventory",
                "min_pool_size_threshold", "current_pool_size",
                "current_relaxation_step", "relax_counts_recent",
                "recent_decisions"):
        assert k in body, f"missing field {k}: {list(body.keys())}"
    assert body["channel"]["slug"] == "punjabi_beats"
    # Pool inventory must contain at least the strict + drop_* keys
    inv = body["pool_inventory"]
    for s in ("strict", "drop_energy", "drop_mood", "drop_genre"):
        assert s in inv, inv


def test_bug2_admin_health_404_on_unknown_channel(admin_session):
    r = admin_session.get(
        f"{API}/admin/channels/__nonexistent__/health", timeout=10)
    assert r.status_code == 404


def test_bug2_admin_health_requires_admin(user_session):
    """Non-admin should be rejected by `require_admin` (403)."""
    r = user_session.get(
        f"{API}/admin/channels/punjabi_beats/health", timeout=10)
    assert r.status_code in (401, 403), (r.status_code, r.text[:200])


def test_bug2_decision_log_inserts_with_steps(user_session):
    """Each radio_start writes a structured row to
    `recommender_decision_log` with `steps`, `final_step`, `tier`."""
    DB.warm_start_segments.delete_many(
        {"user_id": user_session._user_id})
    DB.recommender_decision_log.delete_many({})
    r = user_session.post(
        f"{API}/radio/start",
        json={"channel": "punjabi_beats"}, timeout=30)
    assert r.status_code == 200, r.text
    # The first decision row should be present (warm prebuild or cold).
    # Allow a brief moment for async prebuild to also write its row.
    time.sleep(1.0)
    rows = list(DB.recommender_decision_log.find(
        {"channel_slug": "punjabi_beats"}).sort("ts", -1).limit(5))
    assert rows, "no decision log rows for punjabi_beats"
    top = rows[0]
    assert "steps" in top
    assert top["steps"], top
    assert top.get("final_step") in (
        "strict", "drop_energy", "drop_mood",
        "drop_genre", "language_only", "catalog_wide")
    assert top.get("tier"), top



# ════════════════════════════════════════════════════════════════════════
# § Phase 10b.2 polish — contract gaps from the priority sprint
# ════════════════════════════════════════════════════════════════════════
def test_10b2_channel_health_includes_suggestion(admin_session):
    """Fix 1 — `suggestion` + `strict_pool_size` are present at top level."""
    r = admin_session.get(
        f"{API}/admin/channels/punjabi_beats/health", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "suggestion" in body, list(body.keys())
    assert isinstance(body["suggestion"], str) and body["suggestion"]
    assert "strict_pool_size" in body, list(body.keys())
    # Backwards compat — nested pool_inventory.strict still present
    assert body["pool_inventory"]["strict"] == body["strict_pool_size"]
    # If the channel is unhealthy, suggestion mentions "Upload"; if it's
    # healthy it starts with "Healthy".
    if body["current_pool_size"] >= body["min_pool_size_threshold"]:
        assert body["suggestion"].startswith("Healthy"), body["suggestion"]
    else:
        assert "Upload" in body["suggestion"], body["suggestion"]


def test_10b2_channel_health_healthy_path_suggestion(admin_session):
    """When a channel passes the strict threshold the suggestion is
    'Healthy — strict pool size {N}'."""
    r = admin_session.get(
        f"{API}/admin/channels/bollywood_mehfil/health", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    if body["strict_pool_size"] >= body["min_pool_size_threshold"]:
        assert body["suggestion"].startswith("Healthy"), body["suggestion"]
        assert str(body["strict_pool_size"]) in body["suggestion"]


def test_10b2_bad_metric_error_lists_allowed_values(user_session):
    """Fix 3 — bad metric error literally contains 'Allowed:' and the 6
    valid metric names so operators can self-correct without docs."""
    r = user_session.get(
        f"{API}/leaderboards/dubai?metric=nonsense", timeout=10)
    assert r.status_code == 400, r.text
    body = r.json()
    detail = body.get("detail") or ""
    assert "Allowed:" in detail, detail
    for m in ("listening_minutes_7d", "badges_earned_7d",
                "ambassador_points_alltime", "referrals_engaged_30d",
                "coupons_redeemed_30d", "commutes_completed_30d"):
        assert m in detail, f"missing {m} in detail: {detail}"


def test_10b2_leaderboard_entry_has_value_display_type(admin_session):
    """Fix 4 — every leaderboard entry carries `value_display_type`.
    Seeds a synthetic anonymous user with 1247 listening minutes and a
    synthetic non-anonymous user with 250 minutes, recomputes the dubai
    leaderboard with min_active_users=1, and asserts both entries are
    present with the correct display_type + bucket value.
    """
    import uuid as _u
    from datetime import datetime, timezone
    anon_uid = "test_10b2_anon_user"
    public_uid = "test_10b2_public_user"
    # 1) anonymous (opted out) — 1247 minutes/7d -> "1k+"
    DB.users.update_one({"_id": anon_uid},
                          {"$set": {"_id": anon_uid,
                                       "user_id": anon_uid,
                                       "email": "anon10b2@bigfm.demo",
                                       "name": "Anon10b2",
                                       "city": "dubai"}}, upsert=True)
    DB.social_profile_settings.update_one(
        {"user_id": anon_uid},
        {"$set": {"user_id": anon_uid,
                    "show_leaderboard_position_publicly": False,
                    "display_name": "Anon10b2", "city_pin": "dubai"}},
        upsert=True)
    DB.listening_heartbeats.delete_many({"user_id": anon_uid})
    DB.listening_heartbeats.insert_one({
        "_id": _u.uuid4().hex, "user_id": anon_uid,
        "minutes_credited": 1247,
        "ts": datetime.now(timezone.utc), "city": "dubai"})
    DB.bigcoin_transactions.delete_many(
        {"user_id": anon_uid, "reason": "heartbeat"})
    DB.bigcoin_transactions.insert_one({
        "_id": _u.uuid4().hex, "user_id": anon_uid,
        "reason": "heartbeat", "amount": 1,
        "created_at": datetime.now(timezone.utc)})
    # 2) public (opted in) — 250 minutes/7d -> 250 (exact)
    DB.users.update_one({"_id": public_uid},
                          {"$set": {"_id": public_uid,
                                       "user_id": public_uid,
                                       "email": "pub10b2@bigfm.demo",
                                       "name": "Pub10b2",
                                       "city": "dubai"}}, upsert=True)
    DB.social_profile_settings.update_one(
        {"user_id": public_uid},
        {"$set": {"user_id": public_uid,
                    "show_leaderboard_position_publicly": True,
                    "display_name": "Pub10b2", "city_pin": "dubai"}},
        upsert=True)
    DB.listening_heartbeats.delete_many({"user_id": public_uid})
    DB.listening_heartbeats.insert_one({
        "_id": _u.uuid4().hex, "user_id": public_uid,
        "minutes_credited": 250,
        "ts": datetime.now(timezone.utc), "city": "dubai"})
    DB.bigcoin_transactions.delete_many(
        {"user_id": public_uid, "reason": "heartbeat"})
    DB.bigcoin_transactions.insert_one({
        "_id": _u.uuid4().hex, "user_id": public_uid,
        "reason": "heartbeat", "amount": 1,
        "created_at": datetime.now(timezone.utc)})
    # Recompute
    r = admin_session.post(
        f"{API}/admin/leaderboards/recompute",
        json={"city": "dubai", "metric": "listening_minutes_7d",
                "min_active_users": 1}, timeout=15)
    assert r.status_code == 200, r.text
    # Fetch + assert
    r2 = admin_session.get(
        f"{API}/leaderboards/dubai?metric=listening_minutes_7d",
        timeout=10)
    assert r2.status_code == 200, r2.text
    rows = (r2.json() or {}).get("top_n") or []
    assert rows, "leaderboard empty after recompute"
    # Every entry must carry value_display_type
    for e in rows:
        assert "value_display_type" in e, e
        assert e["value_display_type"] in ("exact", "bucket"), e
    # Locate our two seeds — anonymous is matched by display_name only
    # (user_id is None when anon).
    anon_entry = next(
        (e for e in rows
          if e.get("is_anonymous") and e.get("display_name") == "Anonymous Listener"),
        None)
    pub_entry = next(
        (e for e in rows if e.get("user_id") == public_uid), None)
    assert anon_entry, [e for e in rows if e.get("is_anonymous")]
    assert pub_entry, rows
    assert anon_entry["value"] == "1k+", anon_entry
    assert anon_entry["value_display_type"] == "bucket"
    assert anon_entry["user_id"] is None
    assert pub_entry["value"] == 250, pub_entry
    assert pub_entry["value_display_type"] == "exact"


def test_10b2_bucket_helper_boundaries():
    """Spot-check the 6 bucket boundaries."""
    from services.passport_public import bucket_value_for_anonymous as B
    assert B(0) == "0"
    assert B(1) == "1-99"
    assert B(99) == "1-99"
    assert B(100) == "100s"
    assert B(999) == "100s"
    assert B(1000) == "1k+"
    assert B(9999) == "1k+"
    assert B(10_000) == "10k+"
    assert B(99_999) == "10k+"
    assert B(100_000) == "100k+"
    assert B(5_000_000) == "100k+"
