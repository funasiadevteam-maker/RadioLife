"""Phase RWD.4 backend tests: Streaks, Sponsored Bonuses, Fraud Alerts."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")


def _mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/demo")
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def demo_user_id(demo_session):
    r = demo_session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200, r.text
    data = r.json()
    return data.get("user_id") or data.get("user", {}).get("user_id")


# ─────────────────────────── STREAKS ───────────────────────────
class TestStreaks:
    def _seed_consecutive_days(self, db, uid: str, n_days: int):
        """Insert positive-delta points_ledger rows on n consecutive UTC days ending today."""
        # Wipe ALL recent positive-delta ledger for uid so streak is exactly what we seed.
        since = datetime.now(timezone.utc) - timedelta(days=60)
        db.points_ledger.delete_many({"user_id": uid, "delta": {"$gt": 0},
                                      "created_at": {"$gte": since}})
        db.earn_streak_state.delete_many({"user_id": uid})

        today0 = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        docs = []
        for i in range(n_days):
            docs.append({
                "ledger_id": f"test_{uuid.uuid4().hex[:12]}",
                "user_id": uid,
                "source": "listening_minute",
                "source_id": None,
                "delta": 1,
                "balance_after": 1,
                "metadata": {"test": True},
                "idempotency_key": f"testseed:{uid}:{i}:{uuid.uuid4().hex[:6]}",
                "created_at": today0 - timedelta(days=i),
            })
        db.points_ledger.insert_many(docs)

    def test_streak_awards_milestone_and_is_idempotent(self, demo_session, demo_user_id):
        db = _mongo()
        self._seed_consecutive_days(db, demo_user_id, 3)

        # first overview call → should award bonus for days=3
        r1 = demo_session.get(f"{BASE_URL}/api/me/earn/overview")
        assert r1.status_code == 200, r1.text
        data1 = r1.json()
        streak = data1["streak"]
        assert streak["current"] == 3, f"expected current=3, got {streak}"
        assert streak["awarded_bonus"] is not None
        assert streak["awarded_bonus"]["days"] == 3
        assert streak["awarded_bonus"]["points"] == 50
        assert streak["best"] >= 3

        # idempotency_key streak:3:<uid>:<anchor> must exist exactly once
        anchor = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                  - timedelta(days=2)).strftime("%Y-%m-%d")
        key = f"streak:3:{demo_user_id}:{anchor}"
        n = db.points_ledger.count_documents({"idempotency_key": key})
        assert n == 1, f"expected 1 streak ledger row for key {key}, got {n}"

        balance_after_first = data1["balance"]

        # second overview call same day → NO re-award
        r2 = demo_session.get(f"{BASE_URL}/api/me/earn/overview")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["streak"]["awarded_bonus"] is None
        assert data2["balance"] == balance_after_first
        assert data2["streak"]["current"] == 3
        assert data2["streak"]["best"] >= 3

        # next milestone shown
        assert data2["streak"]["next"] is not None
        assert data2["streak"]["next"]["days"] == 7

    def test_best_streak_persists(self, demo_session, demo_user_id):
        db = _mongo()
        state = db.earn_streak_state.find_one({"user_id": demo_user_id})
        assert state is not None
        assert int(state.get("best_streak", 0)) >= 3


# ─────────────────────────── SPONSORED BONUS ───────────────────────────
class TestBonusWindows:
    MERCHANT_WITH = "TEST_merchant_bonus_A"
    MERCHANT_WITHOUT = "TEST_merchant_bonus_B"

    def test_non_admin_forbidden(self, demo_session):
        r = demo_session.post(f"{BASE_URL}/api/admin/bonus-windows",
                              json={"merchant_id": "x", "multiplier": 2,
                                    "starts_at": datetime.now(timezone.utc).isoformat(),
                                    "ends_at": (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()})
        assert r.status_code in (401, 403)

    def test_create_and_list_bonus_window(self, admin_session):
        # clean any previous test windows
        _mongo().bonus_windows.delete_many({"merchant_id": {"$in": [self.MERCHANT_WITH, self.MERCHANT_WITHOUT]}})
        now = datetime.now(timezone.utc)
        payload = {
            "merchant_id": self.MERCHANT_WITH,
            "multiplier": 2.0,
            "sponsor_name": "TEST Sponsor",
            "starts_at": (now - timedelta(minutes=5)).isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
        }
        r = admin_session.post(f"{BASE_URL}/api/admin/bonus-windows", json=payload)
        assert r.status_code == 200, r.text
        w = r.json()
        assert w["merchant_id"] == self.MERCHANT_WITH
        assert w["multiplier"] == 2.0
        assert w["active"] is True
        wid = w["window_id"]

        # GET list
        r = admin_session.get(f"{BASE_URL}/api/admin/bonus-windows")
        assert r.status_code == 200
        ids = [i["window_id"] for i in r.json()["items"]]
        assert wid in ids

        pytest.bonus_window_id = wid  # stash for later

    def test_active_bonus_surfaced_in_overview(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/me/earn/overview")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("active_bonuses"), list)
        wids = [b["window_id"] for b in data["active_bonuses"]]
        assert pytest.bonus_window_id in wids

        # dedicated bonus-windows endpoint
        r2 = demo_session.get(f"{BASE_URL}/api/me/earn/bonus-windows")
        assert r2.status_code == 200
        wids2 = [b["window_id"] for b in r2.json()["items"]]
        assert pytest.bonus_window_id in wids2

    def test_scan_earn_multiplier_applied(self, demo_session):
        # Call WITHOUT window first, then WITH window (so AI multiplier trend does not
        # inflate the without-baseline vs the with-window call).
        r_without = demo_session.post(f"{BASE_URL}/api/rewards/scan-earn",
                                      json={"amount_usd": 10.0, "merchant_id": self.MERCHANT_WITHOUT})
        assert r_without.status_code == 200
        wo_data = r_without.json()
        assert wo_data.get("bonus_multiplier") == 1.0
        points_without = wo_data["points"]
        base_mult_without = wo_data.get("multiplier", 1.0)

        r_with = demo_session.post(f"{BASE_URL}/api/rewards/scan-earn",
                                   json={"amount_usd": 10.0, "merchant_id": self.MERCHANT_WITH})
        assert r_with.status_code == 200, r_with.text
        with_data = r_with.json()
        assert with_data.get("bonus_multiplier") == 2.0
        points_with = with_data["points"]
        base_mult_with = with_data.get("multiplier", 1.0)

        # Compare against WITH-call's own base multiplier (removes AI drift noise):
        # expected_without_bonus = round(10 * 1 * base_mult_with)
        # points_with = max(that, round(that * 2)) → ~2x
        expected_no_bonus = max(1, round(10.0 * base_mult_with))
        assert points_with >= 2 * expected_no_bonus - 1, \
            f"points_with={points_with} vs expected_no_bonus={expected_no_bonus} (base_mult_with={base_mult_with})"
        # Sanity: baseline call did NOT get doubled
        assert points_without <= round(10.0 * base_mult_without) + 1

    def test_deactivate_bonus_window(self, admin_session, demo_session):
        wid = pytest.bonus_window_id
        r = admin_session.post(f"{BASE_URL}/api/admin/bonus-windows/{wid}/deactivate")
        assert r.status_code == 200

        # verify it no longer appears in active bonuses
        r2 = demo_session.get(f"{BASE_URL}/api/me/earn/bonus-windows")
        assert r2.status_code == 200
        wids = [b["window_id"] for b in r2.json()["items"]]
        assert wid not in wids


# ─────────────────────────── FRAUD ALERTS ───────────────────────────
class TestFraudAlerts:
    MERCHANT = "TEST_merchant_fraud_X"

    def test_non_admin_forbidden(self, demo_session):
        r1 = demo_session.get(f"{BASE_URL}/api/admin/fraud-alerts")
        assert r1.status_code in (401, 403)
        r2 = demo_session.post(f"{BASE_URL}/api/admin/fraud-alerts/scan")
        assert r2.status_code in (401, 403)
        r3 = demo_session.get(f"{BASE_URL}/api/admin/fraud-config")
        assert r3.status_code in (401, 403)

    def test_fraud_config_get_and_put(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/fraud-config")
        assert r.status_code == 200
        cfg = r.json()
        assert cfg["min_shows"] >= 1
        assert 0 <= cfg["flag_rate"] <= 1
        # PUT with same values - roundtrip
        r2 = admin_session.put(f"{BASE_URL}/api/admin/fraud-config",
                               json={"min_shows": 5, "flag_rate": 0.5, "min_unredeemed": 5})
        assert r2.status_code == 200
        assert r2.json()["min_shows"] == 5

    def test_auto_create_fraud_alert_via_coupon_shows(self, demo_session, admin_session):
        db = _mongo()
        # Clean test merchant state
        db.coupon_show_events.delete_many({"merchant_id": self.MERCHANT})
        db.fraud_alerts.delete_many({"merchant_id": self.MERCHANT})

        # Trigger 6 coupon show events (>= 5, none redeemed, low rate)
        for _ in range(6):
            r = demo_session.post(f"{BASE_URL}/api/coupon-events/show",
                                  json={"merchant_id": self.MERCHANT, "kind": "coupon"})
            assert r.status_code == 200, r.text

        # Alert should have been auto-created via maybe_alert
        r = admin_session.get(f"{BASE_URL}/api/admin/fraud-alerts?status=open")
        assert r.status_code == 200
        items = r.json()["items"]
        matching = [a for a in items if a["merchant_id"] == self.MERCHANT]
        assert len(matching) >= 1, f"no open alert for {self.MERCHANT}: got {items}"
        alert = matching[0]
        assert alert["shows"] >= 5
        assert alert["status"] == "open"
        pytest.fraud_alert_id = alert["alert_id"]

    def test_scan_fraud_alerts(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/fraud-alerts/scan")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "merchants_flagged" in data

    def test_resolve_fraud_alert(self, admin_session):
        aid = pytest.fraud_alert_id
        r = admin_session.post(f"{BASE_URL}/api/admin/fraud-alerts/{aid}/resolve")
        assert r.status_code == 200

        # Verify alert no longer in open list
        r2 = admin_session.get(f"{BASE_URL}/api/admin/fraud-alerts?status=open")
        assert r2.status_code == 200
        ids = [a["alert_id"] for a in r2.json()["items"]]
        assert aid not in ids

        # But visible in resolved list
        r3 = admin_session.get(f"{BASE_URL}/api/admin/fraud-alerts?status=resolved")
        assert r3.status_code == 200
        ids3 = [a["alert_id"] for a in r3.json()["items"]]
        assert aid in ids3


# ─────────────────────────── REGRESSION ───────────────────────────
class TestRegression:
    def test_earn_overview_shape(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/me/earn/overview")
        assert r.status_code == 200
        d = r.json()
        for k in ("balance", "tier", "daily_goal", "streak", "active_bonuses",
                  "ways_to_earn", "missions"):
            assert k in d, f"missing {k} in overview"

    def test_premium_status(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/me/premium/status")
        assert r.status_code == 200
        assert "is_premium" in r.json()
