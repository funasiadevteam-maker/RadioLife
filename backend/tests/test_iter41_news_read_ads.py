"""iter41 backend tests — News Read reward + regression."""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=30)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    tok = (data.get("session_token") or data.get("token") or data.get("access_token")
           or (data.get("session") or {}).get("token"))
    assert tok, f"no token in demo response: {data}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


# ── /api/news/read reward
class TestNewsReadReward:
    def test_first_read_awards_one(self, auth_headers):
        headline_id = f"TEST_iter41_{uuid.uuid4().hex[:10]}"
        r = requests.post(f"{BASE_URL}/api/news/read",
                          json={"headline_id": headline_id, "title": "T"},
                          headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["awarded"] is True
        assert data["points"] == 1
        assert "balance_after" in data
        assert data["daily_cap"] == 10
        assert data["daily_count"] >= 1

    def test_repeat_same_headline_no_reward(self, auth_headers):
        headline_id = f"TEST_iter41_dup_{uuid.uuid4().hex[:10]}"
        # 1st
        r1 = requests.post(f"{BASE_URL}/api/news/read",
                           json={"headline_id": headline_id},
                           headers=auth_headers, timeout=20)
        assert r1.status_code == 200
        assert r1.json()["awarded"] is True
        # 2nd same id — must NOT award
        r2 = requests.post(f"{BASE_URL}/api/news/read",
                           json={"headline_id": headline_id},
                           headers=auth_headers, timeout=20)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["awarded"] is False
        assert d2["points"] == 0

    def test_daily_cap_ten(self, auth_headers):
        # Fire enough unique reads to reach cap. Use unique ids; will stop at
        # cap regardless of state carried from earlier tests.
        last = None
        for _ in range(15):
            hid = f"TEST_iter41_cap_{uuid.uuid4().hex[:10]}"
            r = requests.post(f"{BASE_URL}/api/news/read",
                              json={"headline_id": hid},
                              headers=auth_headers, timeout=20)
            assert r.status_code == 200
            last = r.json()
        # After 15 unique reads, daily_count should be capped at 10 and
        # further calls must not award.
        assert last["daily_count"] == 10, f"expected cap of 10, got {last}"
        assert last["awarded"] is False
        assert last["points"] == 0


# ── Regression: news endpoints
class TestNewsRegression:
    def test_headlines_live_fallback(self):
        r = requests.get(f"{BASE_URL}/api/news/headlines?limit=10", timeout=25)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        # Live fallback should surface at least some items even with no admin curation
        # If empty, this is not a hard failure but should be logged.
        if data["items"]:
            it = data["items"][0]
            assert "headline_text" in it
            assert "source_name" in it

    def test_local_strip(self):
        r = requests.get(f"{BASE_URL}/api/news/local-strip", timeout=25)
        assert r.status_code == 200
        data = r.json()
        assert "city" in data
        # weather + prayer may be None if upstream fails; just verify keys exist
        assert "weather" in data
        assert "prayer" in data


# ── Regression: /api/promoted/*
class TestPromotedRegression:
    def test_promoted_stations(self):
        r = requests.get(f"{BASE_URL}/api/promoted/stations?limit=6", timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_promoted_leaderboard(self):
        r = requests.get(f"{BASE_URL}/api/promoted/leaderboard?days=7", timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()


# ── Ads: /api/banner/serve for non-premium demo user
class TestBannerServe:
    def test_banner_serve_returns_200_or_null(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/banner/serve?zone=browse_row",
                         headers=auth_headers, timeout=15)
        # Either returns 200 with banner data or 200 with empty/no banner
        assert r.status_code in (200, 204), r.text
