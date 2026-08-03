"""Phase 18 UI-cleanup batch — A+B+C+D backend tests (12 total)."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import httpx

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient   # noqa: E402

USER_EMAIL = "test@bigfm.dubai"
USER_PWD   = "TestUser123!"


def _login(email=USER_EMAIL, pwd=USER_PWD):
    c = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c.post("/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    raw = r.headers.get("set-cookie", "")
    c.cookies.set("bigfm_session", raw.split("bigfm_session=", 1)[1].split(";", 1)[0])
    me = c.get("/api/users/me")
    c.user_id = me.json().get("user_id")
    return c


def _loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    return asyncio.get_event_loop()


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ─── ISSUE B (1 test) ──────────────────────────────────────────────
def test_games_endpoint_returns_empty_array_when_no_games_seeded():
    """Empty DB → /api/games/state returns {items: [], total: 0}, NOT 500/410."""
    loop = _loop()
    db = _db()

    async def run():
        # Move ALL active/live campaigns to draft, hit endpoint, restore.
        await db.game_campaigns.update_many(
            {"status": {"$in": ["active", "live"]}},
            {"$set": {"status": "draft", "_phase18_test_paused": True}})
        try:
            c = _login()
            r = c.get("/api/games/state")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["items"] == [], f"expected empty, got {len(d['items'])} items"
            assert d["total"] == 0
            c.close()
        finally:
            await db.game_campaigns.update_many(
                {"_phase18_test_paused": True},
                {"$set":    {"status": "active"},
                  "$unset": {"_phase18_test_paused": ""}})

    loop.run_until_complete(run())


# ─── ISSUE A (5 tests) ──────────────────────────────────────────────
def test_autoplay_suggestion_picks_most_played_for_current_time_bucket():
    """Seed user history so a non-default channel beats the global default."""
    loop = _loop()
    db = _db()
    c = _login()
    uid = c.user_id

    async def run():
        # Clean slate then seed 10 plays of `bollywood_mehfil`.
        await db.playback_logs.delete_many({"user_id": uid})
        now = datetime.now(timezone.utc)
        for i in range(10):
            await db.playback_logs.insert_one({
                "id":             f"pb_test_a_{uid}_{i}",
                "user_id":      uid,
                "channel_slug": "bollywood_mehfil",
                "started_at":  now - timedelta(minutes=i),
                "duration_sec": 90,
            })
        # Bust cache, hit endpoint.
        from services.recommendations import _bust_listening_cache
        _bust_listening_cache(uid)
        r = c.get("/api/me/autoplay/suggestion?fresh=true")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["suggested_channel_slug"] == "bollywood_mehfil", d
        assert d["is_cold_start"] is False
        assert any(t["channel_slug"] == "bollywood_mehfil" for t in d["top5"])
        await db.playback_logs.delete_many({"id": {"$regex": f"^pb_test_a_{uid}_"}})

    try: loop.run_until_complete(run())
    finally: c.close()


def test_autoplay_suggestion_falls_back_to_global_for_cold_start_user():
    """User with NO history → cold-start fallback hits a non-None channel."""
    loop = _loop()
    db = _db()
    c = _login()
    uid = c.user_id

    async def run():
        await db.playback_logs.delete_many({"user_id": uid})
        from services.recommendations import _bust_listening_cache
        _bust_listening_cache(uid)
        r = c.get("/api/me/autoplay/suggestion?fresh=true")
        d = r.json()
        assert d["is_cold_start"] is True
        assert d["suggested_channel_slug"]   # not None
        # Must be a real channel.
        ch = await db.channels.find_one({"slug": d["suggested_channel_slug"]})
        assert ch, f"suggested {d['suggested_channel_slug']!r} not in channels"

    try: loop.run_until_complete(run())
    finally: c.close()


def test_autoplay_suggestion_respects_user_market():
    """User in dubai → cold-start fallback returns dubai's default (morning_masala)."""
    loop = _loop()
    c = _login()
    db = _db()
    uid = c.user_id

    async def run():
        await db.users.update_one({"user_id": uid}, {"$set": {"market": "dubai"}})
        await db.playback_logs.delete_many({"user_id": uid})
        from services.recommendations import _bust_listening_cache
        _bust_listening_cache(uid)
        r = c.get("/api/me/autoplay/suggestion")
        d = r.json()
        assert d["user_market"] == "dubai"
        assert d["suggested_channel_slug"] is not None

    try: loop.run_until_complete(run())
    finally: c.close()


def test_autoplay_top5_returns_distinct_channels():
    loop = _loop()
    db = _db()
    c = _login()
    uid = c.user_id

    async def run():
        await db.playback_logs.delete_many({"user_id": uid})
        now = datetime.now(timezone.utc)
        for slug, n in [("bollywood_mehfil", 5), ("morning_masala", 3), ("party_dubai", 1)]:
            for i in range(n):
                await db.playback_logs.insert_one({
                    "id":             f"pb_test_top5_{uid}_{slug}_{i}",
                    "user_id":      uid,
                    "channel_slug": slug,
                    "started_at":  now - timedelta(minutes=i),
                    "duration_sec": 60,
                })
        from services.recommendations import _bust_listening_cache
        _bust_listening_cache(uid)
        r = c.get("/api/me/autoplay/suggestion")
        d = r.json()
        slugs = [t["channel_slug"] for t in d["top5"]]
        assert len(slugs) == len(set(slugs)), f"duplicates: {slugs}"
        assert slugs[0] == "bollywood_mehfil"
        await db.playback_logs.delete_many({"id": {"$regex": f"^pb_test_top5_{uid}_"}})

    try: loop.run_until_complete(run())
    finally: c.close()


def test_user_listening_profile_caches_with_24h_ttl():
    """Two calls within TTL → cached payload (same computed_at)."""
    loop = _loop()
    c = _login()
    uid = c.user_id

    async def run():
        from services.recommendations import _bust_listening_cache, _LISTENING_CACHE
        _bust_listening_cache(uid)
        r1 = c.get("/api/me/listening_profile").json()
        r2 = c.get("/api/me/listening_profile").json()
        assert r1["computed_at"] == r2["computed_at"], "cache miss between calls"
        # Force recompute → must produce a strictly newer computed_at.
        # (Sleep a hair to avoid clock-tie.)
        import time; time.sleep(0.01)
        r3 = c.get("/api/me/listening_profile?force=true").json()
        assert r3["computed_at"] >= r1["computed_at"]

    loop.run_until_complete(run())
    c.close()


# ─── ISSUE D (4 tests) ──────────────────────────────────────────────
def test_top_game_recommendation_picks_most_played_30d():
    loop = _loop()
    db = _db()
    c = _login()
    uid = c.user_id

    async def run():
        # Ensure clean game history.
        await db.game_sessions.delete_many({"user_id": uid})
        now = datetime.now(timezone.utc)
        # Pick existing campaign.
        camp = await db.game_campaigns.find_one({"status": {"$in": ["active", "live"]}})
        assert camp, "no seeded campaign"
        cid = camp["campaign_id"]
        for i in range(4):
            await db.game_sessions.insert_one({
                "session_id": f"gs_test_{uid}_{i}",
                "user_id":    uid,
                "campaign_id": cid,
                "status":     "completed",
                "result":     "win",
                "started_at": now - timedelta(hours=i),
            })
        r = c.get("/api/me/recommendations/top-game")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["campaign_id"] == cid
        assert d["play_count"] == 4
        assert d["cold_start"] is False
        await db.game_sessions.delete_many({"user_id": uid})

    try: loop.run_until_complete(run())
    finally: c.close()


def test_top_channel_recommendation_picks_most_played_30d():
    loop = _loop()
    db = _db()
    c = _login()
    uid = c.user_id

    async def run():
        await db.playback_logs.delete_many({"user_id": uid})
        now = datetime.now(timezone.utc)
        for i in range(6):
            await db.playback_logs.insert_one({
                "id":             f"pb_topch_{uid}_{i}",
                "user_id":      uid,
                "channel_slug": "late_night_drive",
                "started_at":  now - timedelta(minutes=i*3),
                "duration_sec": 120,
            })
        from services.recommendations import _bust_listening_cache
        _bust_listening_cache(uid)
        r = c.get("/api/me/recommendations/top-channel?fresh=true")
        d = r.json()
        assert d["slug"] == "late_night_drive"
        assert d["cold_start"] is False
        assert d["minutes_listened_30d"] > 10
        await db.playback_logs.delete_many({"id": {"$regex": f"^pb_topch_{uid}_"}})

    try: loop.run_until_complete(run())
    finally: c.close()


def test_recommendations_fall_back_to_market_popular_for_cold_start_user():
    loop = _loop()
    db = _db()
    c = _login()
    uid = c.user_id

    async def run():
        await db.playback_logs.delete_many({"user_id": uid})
        await db.game_sessions.delete_many({"user_id": uid})
        await db.users.update_one({"user_id": uid},
                                              {"$set": {"market": "dubai"}})
        from services.recommendations import _bust_listening_cache
        _bust_listening_cache(uid)
        r_ch = c.get("/api/me/recommendations/top-channel?fresh=true").json()
        r_gm = c.get("/api/me/recommendations/top-game").json()
        assert r_ch.get("slug"),    f"cold-start channel must not be None: {r_ch}"
        assert r_ch["cold_start"] is True
        assert r_gm.get("game_id"), f"cold-start game must not be None: {r_gm}"

    loop.run_until_complete(run())
    c.close()


def test_favorites_capped_at_8_returns_4xx_on_9th():
    loop = _loop()
    c = _login()
    db = _db()
    uid = c.user_id

    async def run():
        # Reset favorites.
        await db.users.update_one({"user_id": uid},
                                              {"$set": {"favorite_channel_slugs": []}})
        all_chans = await db.channels.find({}, {"slug": 1}).to_list(20)
        slugs = [c["slug"] for c in all_chans][:9]
        assert len(slugs) >= 9, "need at least 9 channels seeded to run this test"
        added_ok = 0
        for s in slugs[:8]:
            r = c.post("/api/me/favorites", json={"channel_slug": s})
            if r.status_code == 200: added_ok += 1
        assert added_ok == 8, f"only added {added_ok} of 8"
        r = c.post("/api/me/favorites", json={"channel_slug": slugs[8]})
        assert 400 <= r.status_code < 500, r.status_code
        assert r.status_code == 409
        # List confirms 8 entries.
        lst = c.get("/api/me/favorites").json()
        assert len(lst["favorites"]) == 8
        # Cleanup.
        await db.users.update_one({"user_id": uid},
                                              {"$set": {"favorite_channel_slugs": []}})

    try: loop.run_until_complete(run())
    finally: c.close()


# ─── ISSUE C (1 test) ──────────────────────────────────────────────
def test_commute_offers_returns_friendly_empty_when_no_partners():
    """Endpoint must NOT 500 even with no partner network seeded."""
    c = _login()
    r = c.get("/api/commute/offers_along_route?origin=Dubai&destination=Karak")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "offers" in d
    assert isinstance(d["offers"], list)
    assert d.get("mock") is True
    c.close()
