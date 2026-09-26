"""Iteration 185 — Testing 3 FUUSIC enhancements:
 1. Daily FREE bar spin (bar-games)
 2. Live Reminders (social liveshows)
 3. Bar Wheel Skins (bar-games)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://mobile-games-v2.preview.emergentagent.com').rstrip('/')
DEMO_BAR_ID = "biz_demo_bar"
DEMO_SHOW_ID = "ls_demo_scheduled_01"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    return _login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="module")
def free_session():
    return _login("freeuser@bigfm.dubai", "FreePass123!")


# ---------------- ENHANCEMENT 1: Free daily bar spin ----------------

class TestBarGameFreeSpin:
    def test_demo_status_has_free_spin_fields(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/bar-games/{DEMO_BAR_ID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("eligible") is True
        assert "free_spin_available" in d
        assert "next_free_reset" in d
        assert "total_playable" in d
        # demo has 1 purchase + 1 free (per problem statement)
        assert d["spins_available"] >= 1, f"demo should have ≥1 purchase spin: {d}"
        expected_total = d["spins_available"] + (1 if d["free_spin_available"] else 0)
        assert d["total_playable"] == expected_total

    def test_free_user_only_has_free_spin(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/bar-games/{DEMO_BAR_ID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("eligible") is True
        # freeuser should have 0 purchase spins
        assert d["spins_available"] == 0, f"freeuser has purchase spins: {d}"
        # Either free is available (fresh) OR total_playable reflects state
        if d["free_spin_available"]:
            assert d["total_playable"] == 1
        else:
            assert d["total_playable"] == 0

    def test_neon_skin_theme_and_segments(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/bar-games/{DEMO_BAR_ID}", timeout=15)
        assert r.status_code == 200
        cfg = r.json().get("config", {})
        theme = cfg.get("theme", {})
        assert theme.get("accent") == "#22d3ee", f"accent: {theme}"
        assert theme.get("accent2") == "#f472b6", f"accent2: {theme}"
        assert theme.get("logo_url"), f"logo_url missing: {theme}"
        labels = [s.get("label") for s in cfg.get("segments", [])]
        expected_prizes = ["Free Neon Mojito", "2-for-1 Cosmo", "25% off your tab",
                           "Free bar bites", "Glow-shot on us"]
        for p in expected_prizes:
            assert p in labels, f"expected segment '{p}' missing from {labels}"


# ---------------- ENHANCEMENT 3: Skin ownership ----------------

class TestBarSkinAuth:
    def test_non_owner_cannot_set_skin(self, free_session):
        r = free_session.put(f"{BASE_URL}/api/bar-games/{DEMO_BAR_ID}/skin",
                             json={"accent": "#000000"}, timeout=15)
        # freeuser isn't the bar owner; demo is
        assert r.status_code == 403, f"expected 403 for non-owner, got {r.status_code} {r.text}"


# ---------------- ENHANCEMENT 2: Live reminders ----------------

class TestLiveReminders:
    def test_scheduled_list_includes_demo_show_with_reminded_flag(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/social/liveshows?status=scheduled", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        show = next((s for s in items if s.get("show_id") == DEMO_SHOW_ID), None)
        assert show is not None, f"demo scheduled show not in list: {[s.get('show_id') for s in items]}"
        assert "reminded" in show

    def test_toggle_remind_on_and_off(self, free_session):
        # Turn ON
        r = free_session.post(f"{BASE_URL}/api/social/liveshows/{DEMO_SHOW_ID}/remind",
                              json={"on": True}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("reminded") is True
        assert d.get("reminder_count", 0) >= 1

        # Verify list reflects reminded=True
        r2 = free_session.get(f"{BASE_URL}/api/social/liveshows?status=scheduled", timeout=15)
        assert r2.status_code == 200
        show = next((s for s in r2.json().get("items", []) if s.get("show_id") == DEMO_SHOW_ID), None)
        assert show is not None
        assert show.get("reminded") is True, f"reminded flag not set in list: {show}"

        # Turn OFF
        r3 = free_session.post(f"{BASE_URL}/api/social/liveshows/{DEMO_SHOW_ID}/remind",
                               json={"on": False}, timeout=15)
        assert r3.status_code == 200
        assert r3.json().get("reminded") is False

    def test_show_detail_returns_reminded_flag(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/social/liveshows/{DEMO_SHOW_ID}", timeout=15)
        assert r.status_code == 200
        assert "reminded" in r.json()
