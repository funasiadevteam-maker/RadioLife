"""Iter234 — Appearance Phase B: accent + theme_schedule on /api/shell/prefs.
Tests GET/PUT round-trip, validation, fallbacks, and cross-session sync.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
FREE_EMAIL = "freeuser@bigfm.dubai"
FREE_PASS = "FreePass123!"


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": FREE_EMAIL, "password": FREE_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module", autouse=True)
def _reset_demo(demo_session):
    yield
    # restore demo to a sane default
    demo_session.put(f"{API}/shell/prefs", json={
        "theme": "light",
        "accent": "violet",
        "theme_schedule": {"enabled": False, "dark_hour": 19, "light_hour": 7},
    }, timeout=15)


class TestAnonPrefs:
    def test_anon_get_returns_defaults(self):
        r = requests.get(f"{API}/shell/prefs", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["theme"] == "dark"
        assert d["accent"] == "violet"
        assert d["theme_schedule"] == {"enabled": False, "dark_hour": 19, "light_hour": 7}


class TestPrefsSchema:
    def test_get_shape(self, demo_session):
        r = demo_session.get(f"{API}/shell/prefs", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) >= {"theme", "accent", "theme_schedule"}
        ts = d["theme_schedule"]
        assert set(ts.keys()) == {"enabled", "dark_hour", "light_hour"}
        assert isinstance(ts["enabled"], bool)
        assert isinstance(ts["dark_hour"], int)
        assert isinstance(ts["light_hour"], int)


class TestAccentRoundTrip:
    @pytest.mark.parametrize("accent", ["violet", "coral", "teal", "amber", "blue"])
    def test_valid_accents_persist(self, demo_session, accent):
        r = demo_session.put(f"{API}/shell/prefs", json={"accent": accent}, timeout=15)
        assert r.status_code == 200
        assert r.json()["accent"] == accent
        r2 = demo_session.get(f"{API}/shell/prefs", timeout=15)
        assert r2.json()["accent"] == accent

    def test_invalid_accent_falls_back_to_violet(self, demo_session):
        # pre-set to teal so we can detect the overwrite
        demo_session.put(f"{API}/shell/prefs", json={"accent": "teal"}, timeout=15)
        r = demo_session.put(f"{API}/shell/prefs", json={"accent": "neon-pink"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["accent"] == "violet"
        r2 = demo_session.get(f"{API}/shell/prefs", timeout=15)
        assert r2.json()["accent"] == "violet"


class TestThemeValidation:
    @pytest.mark.parametrize("theme", ["light", "dark", "system"])
    def test_valid_themes(self, demo_session, theme):
        r = demo_session.put(f"{API}/shell/prefs", json={"theme": theme}, timeout=15)
        assert r.status_code == 200
        assert r.json()["theme"] == theme

    def test_invalid_theme_falls_back_to_dark(self, demo_session):
        demo_session.put(f"{API}/shell/prefs", json={"theme": "light"}, timeout=15)
        r = demo_session.put(f"{API}/shell/prefs", json={"theme": "midnight"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["theme"] == "dark"


class TestScheduleRoundTrip:
    def test_schedule_full_round_trip(self, demo_session):
        payload = {"theme_schedule": {"enabled": True, "dark_hour": 20, "light_hour": 6}}
        r = demo_session.put(f"{API}/shell/prefs", json=payload, timeout=15)
        assert r.status_code == 200
        ts = r.json()["theme_schedule"]
        assert ts == {"enabled": True, "dark_hour": 20, "light_hour": 6}
        r2 = demo_session.get(f"{API}/shell/prefs", timeout=15)
        assert r2.json()["theme_schedule"] == ts

    def test_schedule_partial_update_preserves_others(self, demo_session):
        demo_session.put(f"{API}/shell/prefs", json={
            "theme_schedule": {"enabled": True, "dark_hour": 20, "light_hour": 6}
        }, timeout=15)
        # Only toggle enabled off — but note the PUT replaces whole theme_schedule
        # So we must send full object
        r = demo_session.put(f"{API}/shell/prefs", json={
            "theme_schedule": {"enabled": False, "dark_hour": 20, "light_hour": 6}
        }, timeout=15)
        ts = r.json()["theme_schedule"]
        assert ts["enabled"] is False
        assert ts["dark_hour"] == 20
        assert ts["light_hour"] == 6

    def test_schedule_out_of_range_hours_ignored_defaulted(self, demo_session):
        # Reset to known values first
        demo_session.put(f"{API}/shell/prefs", json={
            "theme_schedule": {"enabled": True, "dark_hour": 19, "light_hour": 7}
        }, timeout=15)
        # Now send out-of-range; backend _clean_schedule starts from DEFAULT, then applies valid
        r = demo_session.put(f"{API}/shell/prefs", json={
            "theme_schedule": {"enabled": True, "dark_hour": 99, "light_hour": -3}
        }, timeout=15)
        ts = r.json()["theme_schedule"]
        # out of range → fall back to default 19/7 (per implementation)
        assert ts["enabled"] is True
        assert ts["dark_hour"] == 19
        assert ts["light_hour"] == 7

    def test_schedule_boundary_hours_0_and_23(self, demo_session):
        r = demo_session.put(f"{API}/shell/prefs", json={
            "theme_schedule": {"enabled": True, "dark_hour": 0, "light_hour": 23}
        }, timeout=15)
        ts = r.json()["theme_schedule"]
        assert ts["dark_hour"] == 0
        assert ts["light_hour"] == 23

    def test_schedule_non_int_strings_still_parse(self, demo_session):
        r = demo_session.put(f"{API}/shell/prefs", json={
            "theme_schedule": {"enabled": True, "dark_hour": "21", "light_hour": "8"}
        }, timeout=15)
        ts = r.json()["theme_schedule"]
        assert ts["dark_hour"] == 21
        assert ts["light_hour"] == 8

    def test_schedule_non_dict_falls_to_default(self, demo_session):
        r = demo_session.put(f"{API}/shell/prefs", json={
            "theme_schedule": "nope"
        }, timeout=15)
        assert r.status_code == 200
        ts = r.json()["theme_schedule"]
        assert ts == {"enabled": False, "dark_hour": 19, "light_hour": 7}


class TestPartialPUT:
    def test_only_accent_doesnt_wipe_theme_or_schedule(self, demo_session):
        demo_session.put(f"{API}/shell/prefs", json={
            "theme": "dark",
            "accent": "violet",
            "theme_schedule": {"enabled": True, "dark_hour": 22, "light_hour": 5}
        }, timeout=15)
        r = demo_session.put(f"{API}/shell/prefs", json={"accent": "coral"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["accent"] == "coral"
        assert d["theme"] == "dark"
        assert d["theme_schedule"] == {"enabled": True, "dark_hour": 22, "light_hour": 5}

    def test_empty_put_body_is_ok(self, demo_session):
        r = demo_session.put(f"{API}/shell/prefs", json={}, timeout=15)
        assert r.status_code == 200
        assert "theme" in r.json() and "accent" in r.json()


class TestCrossSurfaceSync:
    """Same user, different sessions (web cookie vs. 'mobile' bearer-like) — verify sync."""

    def test_set_on_one_session_visible_on_another(self):
        s1 = requests.Session()
        r1 = s1.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
        assert r1.status_code == 200

        s2 = requests.Session()
        r2 = s2.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
        assert r2.status_code == 200

        s1.put(f"{API}/shell/prefs", json={"accent": "amber", "theme": "light"}, timeout=15)
        d = s2.get(f"{API}/shell/prefs", timeout=15).json()
        assert d["accent"] == "amber"
        assert d["theme"] == "light"

    def test_different_users_isolated(self, demo_session, free_session):
        demo_session.put(f"{API}/shell/prefs", json={"accent": "blue"}, timeout=15)
        free_session.put(f"{API}/shell/prefs", json={"accent": "teal"}, timeout=15)
        assert demo_session.get(f"{API}/shell/prefs", timeout=15).json()["accent"] == "blue"
        assert free_session.get(f"{API}/shell/prefs", timeout=15).json()["accent"] == "teal"


class TestAuthRequiredForPUT:
    def test_anon_put_rejected(self):
        r = requests.put(f"{API}/shell/prefs", json={"accent": "teal"}, timeout=15)
        assert r.status_code in (401, 403)
