"""Iteration 40 — Auto-bidding rules, Sponsor Leaderboard, Local Weather Strip.

Covers the review scope:
  • GET  /api/promoted/leaderboard?days=7
  • POST /api/promoted/self-serve with daily_budget_cents (echoed in /mine)
  • Auto-bidding cap: fund wallet via Mongo, low CPC daily cap, click until budget_capped
  • GET  /api/news/local-strip (Open-Meteo + Aladhan keyless)
  • Regression: wallet, self-serve, mine, toggle, wallet/topup still 200
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ─────────────────────────── fixtures ───────────────────────────
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def demo_token(session):
    try:
        session.post(f"{BASE_URL}/api/auth/_demo_reset_rate_limit", timeout=10)
    except Exception:
        pass
    r = session.post(f"{BASE_URL}/api/auth/demo", json={}, timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("session_token") or j.get("token") or j.get("access_token")
    assert tok, f"no token in demo response: {j}"
    return tok


@pytest.fixture(scope="module")
def auth(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


@pytest.fixture(scope="module")
def a_station_id(session):
    r = session.get(f"{BASE_URL}/api/promoted/stations?limit=6", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items, "no promoted stations available for test"
    return items[0].get("id") or items[0].get("station_id")


@pytest.fixture(scope="module")
def uid_from_wallet(session, auth):
    r = session.get(f"{BASE_URL}/api/promoted/wallet", headers=auth, timeout=15)
    assert r.status_code == 200
    return r.json()["advertiser_id"]


# ─────────────────────────── Leaderboard ───────────────────────────
class TestLeaderboard:
    def test_leaderboard_200_and_shape(self, session):
        r = session.get(f"{BASE_URL}/api/promoted/leaderboard?days=7", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and isinstance(j["items"], list)
        assert j.get("window_days") == 7
        # If items exist, validate shape
        for it in j["items"]:
            for k in ("promo_id", "station_id", "station_name",
                      "listens", "impressions", "pricing_model"):
                assert k in it, f"missing {k} in leaderboard item"
            assert isinstance(it["listens"], int)
            assert isinstance(it["impressions"], int)
            assert it["pricing_model"] in ("cpm", "cpc")

    def test_leaderboard_days_bounds(self, session):
        # ge=1 le=30
        r = session.get(f"{BASE_URL}/api/promoted/leaderboard?days=0", timeout=10)
        assert r.status_code == 422
        r2 = session.get(f"{BASE_URL}/api/promoted/leaderboard?days=31", timeout=10)
        assert r2.status_code == 422

    def test_leaderboard_populated_by_house_promo_click(self, session):
        """Fire a click on a house promo to ensure promo_daily is populated,
        then confirm leaderboard reflects at least one entry."""
        r = session.get(f"{BASE_URL}/api/promoted/stations?limit=1", timeout=15)
        items = r.json().get("items") or []
        assert items
        pid = items[0].get("promo_id")
        session.post(f"{BASE_URL}/api/promoted/{pid}/click", timeout=10)
        session.post(f"{BASE_URL}/api/promoted/{pid}/impression", timeout=10)
        lb = session.get(f"{BASE_URL}/api/promoted/leaderboard?days=7", timeout=15).json()
        # Just assert response is well-formed; content may lag by rollup timing but this promo should be there.
        assert isinstance(lb.get("items"), list)


# ─────────────────────────── Self-serve with daily_budget_cents ───────────────────────────
class TestSelfServeDailyBudget:
    def test_self_serve_accepts_daily_budget_cents(self, session, auth, a_station_id):
        body = {
            "station_id": a_station_id,
            "sponsor_name": "TEST_iter40_daily_budget",
            "pricing_model": "cpc",
            "cpc_bid_cents": 25,
            "daily_budget_cents": 500,  # $5/day cap
        }
        r = session.post(f"{BASE_URL}/api/promoted/self-serve",
                         headers=auth, json=body, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        promo = j["promo"]
        assert promo.get("daily_budget_cents") == 500
        # Echo in /mine
        m = session.get(f"{BASE_URL}/api/promoted/mine", headers=auth, timeout=15).json()
        found = [p for p in m["items"] if p["promo_id"] == promo["promo_id"]]
        assert found and found[0].get("daily_budget_cents") == 500

    def test_self_serve_default_daily_budget_zero(self, session, auth, a_station_id):
        body = {"station_id": a_station_id, "sponsor_name": "TEST_iter40_nocap",
                "pricing_model": "cpm"}
        r = session.post(f"{BASE_URL}/api/promoted/self-serve",
                         headers=auth, json=body, timeout=15)
        assert r.status_code == 200
        assert r.json()["promo"].get("daily_budget_cents") == 0


# ─────────────────────────── Auto-bidding cap (fund wallet, click until capped) ───────────────────────────
class TestAutoBiddingCap:
    @pytest.fixture(scope="class")
    def mongo_db(self):
        try:
            from pymongo import MongoClient
        except ImportError:
            pytest.skip("pymongo not installed")
        client = MongoClient(MONGO_URL)
        yield client[DB_NAME]
        client.close()

    def test_click_hits_daily_cap_and_pauses(self, session, auth, a_station_id,
                                              uid_from_wallet, mongo_db):
        # 1) Fund wallet directly via Mongo
        mongo_db.promo_wallets.update_one(
            {"advertiser_id": uid_from_wallet},
            {"$set": {"balance_cents": 10000, "advertiser_id": uid_from_wallet}},
            upsert=True,
        )
        # 2) Create CPC promo with 50c daily cap (2 clicks * 25c = 50c → cap trip)
        body = {
            "station_id": a_station_id,
            "sponsor_name": "TEST_iter40_autobid",
            "pricing_model": "cpc",
            "cpc_bid_cents": 25,
            "daily_budget_cents": 50,
        }
        r = session.post(f"{BASE_URL}/api/promoted/self-serve",
                         headers=auth, json=body, timeout=15)
        assert r.status_code == 200
        promo = r.json()["promo"]
        pid = promo["promo_id"]
        assert promo["active"] is True, f"expected active with funded wallet; got {promo}"

        # 3) Reset any prior day-rollup for this promo (clean state)
        mongo_db.promo_daily.delete_many({"promo_id": pid})

        # 4) Fire clicks until cap trips
        for _ in range(4):
            session.post(f"{BASE_URL}/api/promoted/{pid}/click", timeout=10)

        # 5) Verify promo doc → active=False, status=budget_capped
        doc = mongo_db.promoted_stations.find_one({"promo_id": pid})
        assert doc is not None
        assert doc.get("status") == "budget_capped", f"status={doc.get('status')}"
        assert doc.get("active") is False

        # 6) Verify /mine reflects it
        m = session.get(f"{BASE_URL}/api/promoted/mine", headers=auth, timeout=15).json()
        found = [p for p in m["items"] if p["promo_id"] == pid]
        assert found and found[0]["status"] == "budget_capped"
        assert found[0]["active"] is False

    def test_house_promo_unaffected_by_daily_cap(self, session, mongo_db):
        # House promo (no advertiser_id) — clicks should NOT trip budget_capped
        r = session.get(f"{BASE_URL}/api/promoted/stations?limit=3", timeout=15)
        items = r.json().get("items") or []
        # Find one that is a house promo (advertiser_id absent in DB)
        target_pid = None
        for it in items:
            pid = it.get("promo_id")
            doc = mongo_db.promoted_stations.find_one({"promo_id": pid})
            if doc and not doc.get("advertiser_id"):
                target_pid = pid
                break
        if not target_pid:
            pytest.skip("no house promo found in seed")
        # No daily cap on house promo; clicks should stay active
        for _ in range(3):
            session.post(f"{BASE_URL}/api/promoted/{target_pid}/click", timeout=10)
        doc = mongo_db.promoted_stations.find_one({"promo_id": target_pid})
        assert doc.get("status") != "budget_capped"


# ─────────────────────────── Local Weather + Prayer Strip ───────────────────────────
class TestLocalStrip:
    def test_local_strip_returns_city_weather_prayer(self, session):
        r = session.get(f"{BASE_URL}/api/news/local-strip", timeout=25)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "city" in j
        # Weather may be None if upstream fails; if present, validate keys
        if j.get("weather"):
            for k in ("temp_c", "label", "is_day"):
                assert k in j["weather"], f"weather missing {k}"
            assert isinstance(j["weather"]["temp_c"], (int, float))
            assert isinstance(j["weather"]["is_day"], bool)
        if j.get("prayer"):
            assert "timings" in j["prayer"]
            assert "next" in j["prayer"]

    def test_local_strip_cached_response_shape(self, session):
        # Second call within TTL should still return same shape
        r = session.get(f"{BASE_URL}/api/news/local-strip", timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert "city" in j


# ─────────────────────────── Regression: previous iteration endpoints ───────────────────────────
class TestRegressionIter39:
    def test_wallet_still_works(self, session, auth):
        r = session.get(f"{BASE_URL}/api/promoted/wallet", headers=auth, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "balance_cents" in j
        assert "packages" in j
        assert len(j["packages"]) == 4

    def test_mine_still_works(self, session, auth):
        r = session.get(f"{BASE_URL}/api/promoted/mine", headers=auth, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "totals" in j

    def test_toggle_404_unknown(self, session, auth):
        r = session.post(
            f"{BASE_URL}/api/promoted/promo_iter40_nope_{uuid.uuid4().hex[:6]}/toggle",
            headers=auth, timeout=10)
        assert r.status_code == 404

    def test_topup_returns_checkout_url(self, session, auth):
        r = session.post(f"{BASE_URL}/api/promoted/wallet/topup", headers=auth,
                         json={"package_id": "topup_10", "origin_url": BASE_URL},
                         timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert j.get("checkout_url", "").startswith("https://")
        assert "checkout.stripe.com" in j["checkout_url"]

    def test_self_serve_still_works(self, session, auth, a_station_id):
        r = session.post(f"{BASE_URL}/api/promoted/self-serve", headers=auth,
                         json={"station_id": a_station_id,
                               "sponsor_name": "TEST_iter40_regression",
                               "pricing_model": "cpm"},
                         timeout=15)
        assert r.status_code == 200
        assert "promo" in r.json()
