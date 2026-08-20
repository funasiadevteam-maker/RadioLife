"""Backend tests for the redesigned consumer shell (Phase A/B).

Covers GET /api/shell/summary, GET/PUT /api/shell/prefs. Uses real backend via
REACT_APP_BACKEND_URL so we exercise the same endpoint the frontend calls.
"""
import os
import pytest
import requests

BASE_URL = "https://mobile-games-v2.preview.emergentagent.com"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"


@pytest.fixture
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def demo_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": DEMO_EMAIL, "password": DEMO_PASS})
    assert r.status_code == 200, f"demo login failed: {r.text}"
    return s


@pytest.fixture
def admin_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return s


# --- /api/shell/summary ---
class TestShellSummary:
    def test_summary_anon_returns_expected_shape(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/shell/summary")
        assert r.status_code == 200
        d = r.json()
        for k in ("city", "station_count", "world_count", "ai_count",
                  "flagships", "flagship_count", "chips", "badges",
                  "podcasts_count", "is_premium"):
            assert k in d, f"missing key: {k}"

    def test_summary_station_count_matches_world_plus_ai(self, anon_client):
        d = anon_client.get(f"{BASE_URL}/api/shell/summary").json()
        assert d["station_count"] == d["world_count"] + d["ai_count"]
        # PRD promises ~5,035 "world+AI" stations.
        assert d["station_count"] >= 5000

    def test_summary_flagships_capped_at_12(self, anon_client):
        d = anon_client.get(f"{BASE_URL}/api/shell/summary").json()
        assert isinstance(d["flagships"], list)
        assert len(d["flagships"]) <= 12
        # Sanity — flagship items should carry slug + name.
        if d["flagships"]:
            f0 = d["flagships"][0]
            assert "slug" in f0 and "name" in f0 and "live" in f0

    def test_summary_chips_include_required_keys(self, anon_client):
        d = anon_client.get(f"{BASE_URL}/api/shell/summary").json()
        keys = {c["key"] for c in d["chips"]}
        # Must-have chips per PRD (podcasts hidden when count=0 → not in chips list).
        for k in ("all", "world"):
            assert k in keys, f"missing chip: {k}"
        # Live-count chips only appear when their source > 0. Verify shape.
        for c in d["chips"]:
            assert "key" in c and "label" in c

    def test_summary_badges_shape(self, anon_client):
        d = anon_client.get(f"{BASE_URL}/api/shell/summary").json()
        assert "games" in d["badges"] and "shop" in d["badges"]
        assert isinstance(d["badges"]["games"], int)
        assert isinstance(d["badges"]["shop"], int)

    def test_summary_demo_shows_home_city_and_mine_chip(self, demo_client):
        d = demo_client.get(f"{BASE_URL}/api/shell/summary").json()
        # demo user seeded with home city Dallas / market dfw.
        assert d["city"], "expected non-empty city for logged in demo"
        keys = [c["key"] for c in d["chips"]]
        assert "mine" in keys, "logged-in users should get 'mine' chip"


# --- /api/shell/prefs ---
class TestShellPrefs:
    def test_prefs_anon_defaults_dark(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/shell/prefs")
        assert r.status_code == 200
        assert r.json()["theme"] == "dark"

    def test_prefs_put_requires_auth(self, anon_client):
        r = anon_client.put(f"{BASE_URL}/api/shell/prefs",
                            json={"theme": "light"})
        assert r.status_code in (401, 403)

    def test_prefs_put_light_then_get_persists(self, demo_client):
        # Set light
        r = demo_client.put(f"{BASE_URL}/api/shell/prefs",
                            json={"theme": "light"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "theme": "light"}
        # Read back
        r2 = demo_client.get(f"{BASE_URL}/api/shell/prefs")
        assert r2.status_code == 200
        assert r2.json()["theme"] == "light"

    def test_prefs_put_dark_persists(self, demo_client):
        demo_client.put(f"{BASE_URL}/api/shell/prefs",
                        json={"theme": "dark"})
        r = demo_client.get(f"{BASE_URL}/api/shell/prefs")
        assert r.json()["theme"] == "dark"

    def test_prefs_invalid_theme_falls_back_to_dark(self, demo_client):
        r = demo_client.put(f"{BASE_URL}/api/shell/prefs",
                            json={"theme": "neon"})
        assert r.status_code == 200
        assert r.json()["theme"] == "dark"
