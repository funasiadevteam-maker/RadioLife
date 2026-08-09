"""Phase RWD.1 — Rewards Earn Loop e2e tests."""
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = "bigfm"

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/demo", timeout=10)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo_user_id(demo_session, db):
    # Try /api/auth/me
    r = demo_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
    if r.status_code == 200:
        j = r.json()
        uid = j.get("user_id") or j.get("id") or (j.get("user") or {}).get("user_id") or (j.get("user") or {}).get("id")
        if uid:
            return uid
    # Fallback: look up demo user by email
    u = db.users.find_one({"email": "demo@bigfm.dubai"})
    assert u, "demo user not found in DB"
    return u.get("user_id") or u.get("id") or str(u.get("_id"))


# ─────────── Auth gating ───────────
class TestAuthGating:
    def test_overview_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/me/earn/overview", timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_ways_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/me/earn/ways-to-earn", timeout=10)
        assert r.status_code in (401, 403)

    def test_claim_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/me/earn/missions/daily_trivia/claim", timeout=10)
        assert r.status_code in (401, 403)

    def test_admin_catalog_requires_admin(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/admin/earn/catalog", timeout=10)
        assert r.status_code in (401, 403)

    def test_admin_config_requires_admin(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/admin/earn/config", timeout=10)
        assert r.status_code in (401, 403)


# ─────────── Overview + ways-to-earn ───────────
class TestOverview:
    def test_overview_shape(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/me/earn/overview", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("balance", "tier", "daily_goal", "streak", "ways_to_earn", "missions"):
            assert k in d, f"missing {k}"
        assert isinstance(d["ways_to_earn"], list) and len(d["ways_to_earn"]) > 0
        assert isinstance(d["missions"], list) and len(d["missions"]) > 0
        # tier shape
        t = d["tier"]
        assert "name" in t and "lifetime_points" in t
        # daily goal shape
        g = d["daily_goal"]
        assert set(["target", "earned", "pct", "complete", "bonus_points"]).issubset(g)

    def test_ways_endpoint(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/me/earn/ways-to-earn", timeout=10)
        assert r.status_code == 200
        items = r.json().get("items")
        assert isinstance(items, list) and len(items) > 0
        keys = {i["key"] for i in items}
        assert "listen" in keys


# ─────────── Admin config tunability ───────────
class TestAdminConfig:
    def test_config_get_and_put(self, admin_session, demo_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/earn/config", timeout=10)
        assert r.status_code == 200
        orig = r.json()
        orig_target = int(orig.get("daily_goal_target", 500))
        new_target = orig_target + 137
        r = admin_session.put(f"{BASE_URL}/api/admin/earn/config",
                              json={"daily_goal_target": new_target}, timeout=10)
        assert r.status_code == 200
        assert r.json()["daily_goal_target"] == new_target

        # reflected in overview
        r = demo_session.get(f"{BASE_URL}/api/me/earn/overview", timeout=10)
        assert r.status_code == 200
        assert r.json()["daily_goal"]["target"] == new_target

        # restore
        r = admin_session.put(f"{BASE_URL}/api/admin/earn/config",
                              json={"daily_goal_target": orig_target}, timeout=10)
        assert r.status_code == 200
        assert r.json()["daily_goal_target"] == orig_target

    def test_catalog_toggle_removes_from_ways(self, admin_session, demo_session):
        # Get initial ways
        r = demo_session.get(f"{BASE_URL}/api/me/earn/ways-to-earn", timeout=10)
        before = {i["key"] for i in r.json()["items"]}
        assert "share" in before

        # Disable "share"
        r = admin_session.put(f"{BASE_URL}/api/admin/earn/catalog",
                              json={"key": "share", "enabled": False}, timeout=10)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        r = demo_session.get(f"{BASE_URL}/api/me/earn/ways-to-earn", timeout=10)
        after = {i["key"] for i in r.json()["items"]}
        assert "share" not in after, "disabled catalog item should be hidden"

        # Restore
        r = admin_session.put(f"{BASE_URL}/api/admin/earn/catalog",
                              json={"key": "share", "enabled": True}, timeout=10)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_mission_reward_points_editable(self, admin_session, demo_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/earn/missions", timeout=10)
        assert r.status_code == 200
        missions = r.json()["items"]
        m = next(x for x in missions if x["mission_id"] == "daily_trivia")
        orig = int(m["reward_points"])
        new_val = orig + 77

        r = admin_session.put(f"{BASE_URL}/api/admin/earn/missions",
                              json={"mission_id": "daily_trivia",
                                    "reward_points": new_val}, timeout=10)
        assert r.status_code == 200
        assert r.json()["reward_points"] == new_val

        r = demo_session.get(f"{BASE_URL}/api/me/earn/overview", timeout=10)
        ov = next(x for x in r.json()["missions"] if x["mission_id"] == "daily_trivia")
        assert ov["reward_points"] == new_val

        # Restore
        r = admin_session.put(f"{BASE_URL}/api/admin/earn/missions",
                              json={"mission_id": "daily_trivia",
                                    "reward_points": orig}, timeout=10)
        assert r.status_code == 200


# ─────────── Mission claim end-to-end ───────────
class TestMissionClaim:
    MISSION = "daily_trivia"  # sources ['game_win','trivia'], target 1, reward 100

    def _clear_state(self, db, uid):
        # Clean previous claim for today's period_key so tests are re-runnable
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.earn_mission_claims.delete_many(
            {"user_id": uid, "mission_id": self.MISSION, "period_key": today})
        # Remove any prior TEST_ ledger rows so we don't accidentally satisfy target already
        db.points_ledger.delete_many(
            {"user_id": uid, "metadata.test_tag": "TEST_earn_loop"})

    def test_incomplete_claim_returns_400(self, demo_session, db, demo_user_id):
        self._clear_state(db, demo_user_id)
        r = demo_session.post(
            f"{BASE_URL}/api/me/earn/missions/{self.MISSION}/claim", timeout=10)
        assert r.status_code == 400, f"expected 400 mission_incomplete, got {r.status_code} {r.text}"
        detail = r.json().get("detail", {})
        assert detail.get("code") == "mission_incomplete"

    def test_complete_and_claim_awards_points(self, demo_session, db, demo_user_id):
        self._clear_state(db, demo_user_id)
        # Balance before
        r = demo_session.get(f"{BASE_URL}/api/me/earn/overview", timeout=10)
        assert r.status_code == 200
        bal_before = int(r.json()["balance"])

        # Seed one positive-delta ledger row so daily_trivia (target=1) completes
        db.points_ledger.insert_one({
            "ledger_id": f"TEST_{uuid.uuid4()}",
            "user_id": demo_user_id,
            "source": "game_win",
            "source_id": f"TEST_{uuid.uuid4()}",
            "delta": 10,
            "balance_after": bal_before + 10,
            "created_at": datetime.now(timezone.utc),
            "metadata": {"test_tag": "TEST_earn_loop"},
        })

        # Overview should now mark mission claimable
        time.sleep(0.3)
        r = demo_session.get(f"{BASE_URL}/api/me/earn/overview", timeout=10)
        ov = next(x for x in r.json()["missions"] if x["mission_id"] == self.MISSION)
        assert ov["complete"] is True, f"mission should be complete: {ov}"
        assert ov["claimable"] is True

        # Claim
        r = demo_session.post(
            f"{BASE_URL}/api/me/earn/missions/{self.MISSION}/claim", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        awarded = int(j["awarded"])
        assert awarded > 0
        assert int(j["balance_after"]) >= bal_before + awarded

        # Second claim → 409 already_claimed (idempotent)
        r2 = demo_session.post(
            f"{BASE_URL}/api/me/earn/missions/{self.MISSION}/claim", timeout=10)
        assert r2.status_code == 409
        assert r2.json().get("detail", {}).get("code") == "already_claimed"

        # Cleanup
        self._clear_state(db, demo_user_id)

    def test_mission_not_found(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/me/earn/missions/bogus_mission_id_xyz/claim", timeout=10)
        assert r.status_code == 404


# ─────────── Regression: favicons ───────────
class TestFavicons:
    def test_favicon_ico(self):
        r = requests.get(f"{BASE_URL}/favicon.ico", timeout=10)
        assert r.status_code == 200

    def test_favicon_512(self):
        r = requests.get(f"{BASE_URL}/favicon-512.png", timeout=10)
        assert r.status_code == 200
