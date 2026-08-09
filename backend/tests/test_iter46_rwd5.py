"""Iteration 46 — Phase RWD.5 backend tests.

Covers three features:
  1) Redeem ownership lock (rewards_merchant.merchant_redeem + merchant self-
     serve bonus create — both call _assert_merchant_owner).
  2) Weekly streak rewards (_maybe_weekly_streak_bonus, escalating bonus,
     idempotent per week; surfaced in /api/me/earn/overview.streak.weekly).
  3) Merchant self-serve bonus windows (GET my-businesses / CRUD bonus windows
     with ownership enforcement).

Plus regression: /api/me/earn/overview full shape + /api/me/premium/status.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

# ----- session fixtures -----

@pytest.fixture(scope="session")
def demo_session():
    r = requests.post(f"{API}/auth/demo")
    assert r.status_code == 200, r.text
    data = r.json()
    tok = data["session_token"]
    uid = data["user_id"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return {"session": s, "user_id": uid, "email": data["email"]}


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    s.headers.update({"Content-Type": "application/json"})
    return {"session": s, "user_id": r.json()["user_id"]}


# ----- mongo helper for seed / cleanup -----

@pytest.fixture(scope="session")
def db():
    import asyncio
    client = AsyncIOMotorClient(MONGO_URL)
    d = client[DB_NAME]
    yield d
    client.close()


@pytest.fixture(scope="session")
def seeded_business(db, demo_session):
    """Seed a business owned by the DEMO user so merchant self-serve works."""
    import asyncio

    biz_id = f"TEST_iter46_biz_{uuid.uuid4().hex[:8]}"
    uid = demo_session["user_id"]

    async def _seed():
        await db.businesses.insert_one({
            "business_id": biz_id,
            "name": "TEST Iter46 Venue",
            "city": "Dallas",
            "market": "dfw",
            "owner_user_id": uid,
            "staff_user_ids": [],
            "created_at": datetime.now(timezone.utc),
        })

    async def _cleanup():
        await db.businesses.delete_many({"business_id": biz_id})
        await db.bonus_windows.delete_many({"merchant_id": biz_id})

    asyncio.get_event_loop().run_until_complete(_seed())
    yield biz_id
    asyncio.get_event_loop().run_until_complete(_cleanup())


@pytest.fixture(scope="session")
def foreign_business(db):
    """Business owned by someone else (not demo, not admin)."""
    import asyncio
    biz_id = f"TEST_iter46_foreign_{uuid.uuid4().hex[:8]}"

    async def _seed():
        await db.businesses.insert_one({
            "business_id": biz_id,
            "name": "TEST Foreign Venue",
            "city": "Dubai",
            "market": "dxb",
            "owner_user_id": "user_someone_else_iter46",
            "staff_user_ids": [],
            "created_at": datetime.now(timezone.utc),
        })

    async def _cleanup():
        await db.businesses.delete_many({"business_id": biz_id})
        await db.bonus_windows.delete_many({"merchant_id": biz_id})

    asyncio.get_event_loop().run_until_complete(_seed())
    yield biz_id
    asyncio.get_event_loop().run_until_complete(_cleanup())


# ==================== 1) my-businesses ====================

class TestMyBusinesses:
    def test_demo_sees_only_owned(self, demo_session, seeded_business, foreign_business):
        r = demo_session["session"].get(f"{API}/merchant/my-businesses")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        ids = [b["business_id"] for b in data["items"]]
        assert seeded_business in ids, f"demo should see own venue; ids={ids}"
        assert foreign_business not in ids, "demo must NOT see foreign venue"

    def test_admin_sees_all(self, admin_session, seeded_business, foreign_business):
        r = admin_session["session"].get(f"{API}/merchant/my-businesses")
        assert r.status_code == 200, r.text
        ids = [b["business_id"] for b in r.json()["items"]]
        # admin may be capped by limit(50), so just confirm at least one seeded
        # venue we know exists is in there (or that admin gets non-empty list).
        assert isinstance(ids, list)
        assert len(ids) >= 1


# ==================== 2) Merchant bonus windows CRUD + ownership ====================

class TestMerchantBonusWindows:
    def test_create_denied_for_non_owner(self, demo_session, foreign_business):
        r = demo_session["session"].post(f"{API}/merchant/bonus-windows",
            json={"merchant_id": foreign_business, "multiplier": 2, "hours": 2, "budget_usd": 5})
        assert r.status_code == 403, f"expected 403 not_owner, got {r.status_code}: {r.text}"

    def test_create_ok_for_owner(self, demo_session, seeded_business):
        r = demo_session["session"].post(f"{API}/merchant/bonus-windows",
            json={"merchant_id": seeded_business, "multiplier": 3, "hours": 2,
                  "title": "TEST 3× tonight", "budget_usd": 10})
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["merchant_id"] == seeded_business
        assert doc["multiplier"] == 3.0
        assert doc["active"] is True
        assert doc["owner_user_id"] == demo_session["user_id"]
        assert doc["source"] == "merchant"
        # side-effect: pin window_id for later tests
        pytest._iter46_win_id = doc["window_id"]

    def test_multiplier_bounds_rejected(self, demo_session, seeded_business):
        r = demo_session["session"].post(f"{API}/merchant/bonus-windows",
            json={"merchant_id": seeded_business, "multiplier": 20, "hours": 1, "budget_usd": 0})
        assert r.status_code in (400, 422), f"expected validation error, got {r.status_code}"

    def test_hours_bounds_rejected(self, demo_session, seeded_business):
        r = demo_session["session"].post(f"{API}/merchant/bonus-windows",
            json={"merchant_id": seeded_business, "multiplier": 2, "hours": 0, "budget_usd": 0})
        assert r.status_code in (400, 422)
        r2 = demo_session["session"].post(f"{API}/merchant/bonus-windows",
            json={"merchant_id": seeded_business, "multiplier": 2, "hours": 999, "budget_usd": 0})
        assert r2.status_code in (400, 422)

    def test_list_only_own(self, demo_session, seeded_business):
        r = demo_session["session"].get(f"{API}/merchant/bonus-windows")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        for w in items:
            assert w.get("owner_user_id") == demo_session["user_id"]

    def test_deactivate_by_owner(self, demo_session):
        win_id = getattr(pytest, "_iter46_win_id", None)
        if not win_id:
            pytest.skip("no window created")
        r = demo_session["session"].post(f"{API}/merchant/bonus-windows/{win_id}/deactivate")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    def test_deactivate_404(self, demo_session):
        r = demo_session["session"].post(f"{API}/merchant/bonus-windows/bw_doesnotexist/deactivate")
        assert r.status_code == 404, r.text

    def test_deactivate_403_for_non_owner(self, demo_session, admin_session, seeded_business, db):
        """Create a window as ADMIN pretending to be another owner, verify demo cannot deactivate."""
        import asyncio
        win_id = f"bw_TEST_{uuid.uuid4().hex[:8]}"

        async def _seed():
            await db.bonus_windows.insert_one({
                "window_id": win_id,
                "merchant_id": seeded_business,
                "multiplier": 2.0,
                "starts_at": datetime.now(timezone.utc) - timedelta(minutes=1),
                "ends_at": datetime.now(timezone.utc) + timedelta(hours=1),
                "active": True,
                "owner_user_id": "user_someone_else_iter46",
                "source": "merchant",
                "created_at": datetime.now(timezone.utc),
            })

        asyncio.get_event_loop().run_until_complete(_seed())
        try:
            r = demo_session["session"].post(f"{API}/merchant/bonus-windows/{win_id}/deactivate")
            assert r.status_code == 403, f"expected 403 not_owner, got {r.status_code}: {r.text}"
            # admin should be able to
            r2 = admin_session["session"].post(f"{API}/merchant/bonus-windows/{win_id}/deactivate")
            assert r2.status_code == 200, r2.text
        finally:
            async def _cleanup():
                await db.bonus_windows.delete_many({"window_id": win_id})
            asyncio.get_event_loop().run_until_complete(_cleanup())


# ==================== 3) Redeem ownership lock ====================

class TestRedeemOwnershipLock:
    def test_redeem_denied_for_non_owner(self, demo_session, foreign_business):
        r = demo_session["session"].post(f"{API}/merchant/redeem",
            json={"merchant_id": foreign_business, "user_id": "some_user"})
        assert r.status_code == 403, f"expected 403 not_owner, got {r.status_code}: {r.text}"

    def test_redeem_ok_for_owner(self, demo_session, seeded_business):
        r = demo_session["session"].post(f"{API}/merchant/redeem",
            json={"merchant_id": seeded_business, "user_id": "test_user_x"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True

    def test_redeem_404_unknown_merchant(self, demo_session):
        r = demo_session["session"].post(f"{API}/merchant/redeem",
            json={"merchant_id": "no_such_merchant_iter46", "user_id": "x"})
        assert r.status_code == 404, r.text


# ==================== 4) Weekly streak bonus ====================

class TestWeeklyStreak:
    def test_overview_shape(self, demo_session):
        r = demo_session["session"].get(f"{API}/me/earn/overview")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("balance", "tier", "daily_goal", "streak", "active_bonuses",
                  "ways_to_earn", "missions"):
            assert k in d, f"missing key '{k}' in overview"
        # weekly sub-shape
        assert "weekly" in d["streak"], f"streak missing weekly: {d['streak']}"
        w = d["streak"]["weekly"]
        assert "current" in w and "next_reward" in w
        assert isinstance(w["current"], int)
        assert isinstance(w["next_reward"], int) and w["next_reward"] > 0

    def test_weekly_bonus_awarded_after_all_missions(self, demo_session, db):
        """Seed enough ledger progress for the demo user to satisfy ALL weekly
        missions, claim each one, and verify the LAST weekly claim returns
        weekly_bonus in the response (weekly_streak_base × min(streak,cap))."""
        import asyncio
        uid = demo_session["user_id"]
        s = demo_session["session"]

        # Force-clear this week's completions + weekly mission claims for a fresh test
        async def _reset():
            wk_start = _monday_utc()
            wk_key = wk_start.strftime("%Y-W%U")
            await db.earn_weekly_completions.delete_many({"user_id": uid})
            await db.earn_mission_claims.delete_many({"user_id": uid, "period_key": wk_key})
            await db.points_ledger.delete_many({"user_id": uid, "idempotency_key": {"$regex": "^weekstreak:"}})
            # Seed ledger progress for weekly missions:
            #  weekly_explorer  → 5 distinct days of listening_minute
            #  weekly_games     → 3 game_win/trivia events
            #  weekly_local     → 2 venue_checkin events
            now = datetime.now(timezone.utc)
            rows = []
            for i in range(5):
                rows.append({
                    "user_id": uid, "source": "listening_minute", "delta": 1,
                    "created_at": wk_start + timedelta(days=i, hours=10),
                    "idempotency_key": f"TEST_iter46_lm_{i}_{uuid.uuid4().hex[:6]}",
                })
            for i in range(3):
                rows.append({
                    "user_id": uid, "source": "game_win", "delta": 25,
                    "created_at": wk_start + timedelta(days=i, hours=11),
                    "idempotency_key": f"TEST_iter46_gw_{i}_{uuid.uuid4().hex[:6]}",
                })
            for i in range(2):
                rows.append({
                    "user_id": uid, "source": "venue_checkin", "delta": 100,
                    "created_at": wk_start + timedelta(days=i, hours=12),
                    "idempotency_key": f"TEST_iter46_vc_{i}_{uuid.uuid4().hex[:6]}",
                })
            await db.points_ledger.insert_many(rows)

        asyncio.get_event_loop().run_until_complete(_reset())

        # Fetch overview to see current weekly-mission progress
        ov = s.get(f"{API}/me/earn/overview").json()
        weekly = [m for m in ov["missions"] if m["scope"] == "weekly"]
        assert weekly, "no weekly missions found"
        # Not all missions might be complete if base config is different — but
        # if any is not complete, skip with clear reason so main agent knows.
        incomplete = [m for m in weekly if not m["complete"]]
        assert not incomplete, f"seed insufficient for missions: {[m['mission_id'] for m in incomplete]}"

        # Claim each in order; last claim response should include weekly_bonus
        weekly_bonus = None
        last_resp = None
        for m in weekly:
            r = s.post(f"{API}/me/earn/missions/{m['mission_id']}/claim")
            assert r.status_code == 200, f"claim {m['mission_id']} failed: {r.status_code} {r.text}"
            last_resp = r.json()
            if last_resp.get("weekly_bonus"):
                weekly_bonus = last_resp["weekly_bonus"]
        assert weekly_bonus is not None, f"no weekly_bonus returned; last_resp={last_resp}"
        assert weekly_bonus["points"] > 0
        assert weekly_bonus["weekly_streak"] >= 1
        # points formula: base × min(streak, cap) — base default 150, streak≥1
        assert weekly_bonus["points"] == 150 * min(weekly_bonus["weekly_streak"], 5)

    def test_weekly_bonus_idempotent(self, demo_session, db):
        """Re-attempt to claim the same weekly mission — should 409 (already
        claimed), and no new weekstreak ledger row should appear."""
        import asyncio
        uid = demo_session["user_id"]
        s = demo_session["session"]

        # find any weekly mission that was just claimed
        ov = s.get(f"{API}/me/earn/overview").json()
        weekly = [m for m in ov["missions"] if m["scope"] == "weekly" and m["claimed"]]
        if not weekly:
            pytest.skip("previous test did not claim any weekly missions")
        m = weekly[0]
        r = s.post(f"{API}/me/earn/missions/{m['mission_id']}/claim")
        assert r.status_code == 409, r.text

        async def _count():
            wk = _monday_utc().strftime("%Y-%m-%d")
            return await db.points_ledger.count_documents(
                {"user_id": uid, "idempotency_key": f"weekstreak:{wk}:{uid}"})
        n = asyncio.get_event_loop().run_until_complete(_count())
        assert n == 1, f"expected exactly 1 weekly-streak ledger row, got {n}"


def _monday_utc() -> datetime:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=now.weekday())


# ==================== 5) Regression ====================

class TestRegression:
    def test_premium_status(self, demo_session):
        r = demo_session["session"].get(f"{API}/me/premium/status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "is_premium" in d

    def test_overview_full_shape(self, demo_session):
        r = demo_session["session"].get(f"{API}/me/earn/overview")
        assert r.status_code == 200
        d = r.json()
        for k in ("balance", "tier", "daily_goal", "streak", "active_bonuses",
                  "ways_to_earn", "missions"):
            assert k in d
        assert isinstance(d["balance"], int)
        assert isinstance(d["ways_to_earn"], list) and len(d["ways_to_earn"]) > 0
        assert isinstance(d["missions"], list)
