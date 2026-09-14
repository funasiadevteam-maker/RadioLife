"""Iteration 137 — Phase 3 audio ads (hop-cooldown, mid-roll, premium gates)."""
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}
PREMIUM = {"email": "premium@bigfm.dubai", "password": "PremiumTest123!"}
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}

RESOLVABLE_STATION = "imp_fun_beat_978_uae"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE)


@pytest.fixture(scope="module")
def premium_session():
    return _login(PREMIUM)


@pytest.fixture(scope="module")
def demo_session():
    return _login(DEMO)


# ── ADMIN hop-cooldown CRUD ────────────────────────────────────────
class TestHopCooldownAdmin:
    def test_get_default(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/preroll/hop-cooldown", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("effective_seconds", "override_seconds", "env_default", "min", "max"):
            assert k in data, f"missing key {k}: {data}"
        assert data["env_default"] == 90
        assert data["min"] == 0
        assert data["max"] == 600

    def test_patch_and_reflect(self, admin_session):
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/preroll/hop-cooldown",
            json={"seconds": 120}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["effective_seconds"] == 120
        # GET reflects it
        g = admin_session.get(f"{BASE_URL}/api/admin/preroll/hop-cooldown", timeout=10).json()
        assert g["effective_seconds"] == 120
        assert g["override_seconds"] == 120

    def test_patch_out_of_range_high(self, admin_session):
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/preroll/hop-cooldown",
            json={"seconds": 700}, timeout=10)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"

    def test_patch_out_of_range_negative(self, admin_session):
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/preroll/hop-cooldown",
            json={"seconds": -1}, timeout=10)
        assert r.status_code == 422

    def test_anon_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/admin/preroll/hop-cooldown", timeout=10)
        assert r.status_code in (401, 403), f"anon should be blocked, got {r.status_code}"

    def test_free_user_forbidden(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/admin/preroll/hop-cooldown", timeout=10)
        assert r.status_code in (401, 403), f"non-admin should be blocked, got {r.status_code}"

    def test_restore_90(self, admin_session):
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/preroll/hop-cooldown",
            json={"seconds": 90}, timeout=10)
        assert r.status_code == 200
        assert r.json()["effective_seconds"] == 90


# ── HOP COOLDOWN behaviour (anon fresh session) ────────────────────
class TestHopCooldownBehaviour:
    def test_anon_second_preroll_blocked(self):
        session_id = f"TEST_hop_{uuid.uuid4().hex[:10]}"
        # 1st preroll → has_preroll:true
        r1 = requests.post(
            f"{BASE_URL}/api/live-radio/preroll/request",
            json={"station_id": RESOLVABLE_STATION, "session_id": session_id},
            timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("has_preroll") is True, f"expected has_preroll true, got: {d1}"
        assert d1.get("impression_id"), d1

        # 2nd preroll (same session, station or other) → blocked by hop_cooldown
        r2 = requests.post(
            f"{BASE_URL}/api/live-radio/preroll/request",
            json={"station_id": RESOLVABLE_STATION, "session_id": session_id},
            timeout=15)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("has_preroll") is False
        assert d2.get("reason") == "hop_cooldown", f"expected hop_cooldown, got: {d2}"

    def test_free_user_second_preroll_blocked(self, free_session):
        session_id = f"TEST_hop_free_{uuid.uuid4().hex[:10]}"
        r1 = free_session.post(
            f"{BASE_URL}/api/live-radio/preroll/request",
            json={"station_id": RESOLVABLE_STATION, "session_id": session_id},
            timeout=15)
        assert r1.status_code == 200
        d1 = r1.json()
        # if grace/hourly was already tripped previously we may see a different reason
        if d1.get("has_preroll"):
            r2 = free_session.post(
                f"{BASE_URL}/api/live-radio/preroll/request",
                json={"station_id": RESOLVABLE_STATION, "session_id": session_id},
                timeout=15)
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2.get("has_preroll") is False
            assert d2.get("reason") in ("hop_cooldown", "grace_period", "frequency_cap"), d2
        else:
            # user was already ad-recent — treat as skipped
            pytest.skip(f"free user already had recent preroll: {d1}")


# ── MID-ROLL ───────────────────────────────────────────────────────
class TestMidRoll:
    def test_free_mid_roll_with_fresh_session(self):
        session_id = f"TEST_mid_{uuid.uuid4().hex[:10]}"
        r = requests.post(
            f"{BASE_URL}/api/live-radio/midstream-ad/request",
            json={"station_id": RESOLVABLE_STATION,
                  "session_id": session_id,
                  "songs_played_in_session": 4},
            timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("has_ad") is True, f"expected has_ad true, got: {d}"
        assert d.get("impression_id"), f"expected impression_id, got: {d}"

    def test_premium_mid_roll_blocked(self, premium_session):
        session_id = f"TEST_midprem_{uuid.uuid4().hex[:10]}"
        r = premium_session.post(
            f"{BASE_URL}/api/live-radio/midstream-ad/request",
            json={"station_id": RESOLVABLE_STATION,
                  "session_id": session_id,
                  "songs_played_in_session": 4},
            timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("has_ad") is False, f"expected has_ad false, got: {d}"
        assert d.get("reason") == "premium_user", d


# ── PREMIUM BANNER GATE ─────────────────────────────────────────────
class TestBannerGate:
    def _hit(self, sess):
        r = sess.get(
            f"{BASE_URL}/api/ads/banner/decision",
            params={"slot_key": "mid_horizontal", "page_route": "/"},
            timeout=15)
        return r

    def test_premium_gets_none(self, premium_session):
        r = self._hit(premium_session)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("source") == "none", d
        assert d.get("reason") == "premium", d

    def test_demo_premium_via_trial_gets_none(self, demo_session):
        r = self._hit(demo_session)
        assert r.status_code == 200
        d = r.json()
        assert d.get("source") == "none", d
        assert d.get("reason") == "premium", d

    def test_free_gets_real_source(self, free_session):
        r = self._hit(free_session)
        assert r.status_code == 200
        d = r.json()
        assert d.get("source") in ("house", "direct", "adsense"), f"free should get real source, got: {d}"


# ── /api/shell/home is_premium ─────────────────────────────────────
class TestShellHomeIsPremium:
    def test_premium_true(self, premium_session):
        r = premium_session.get(f"{BASE_URL}/api/shell/home", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("is_premium") is True

    def test_demo_true(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("is_premium") is True

    def test_free_false_with_native_offer_and_dining_still(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/shell/home", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("is_premium") is False
        # native_offer + dining should still be surfaced regardless of premium
        assert "native_offer" in d
        assert "dining" in d

    def test_premium_still_has_native_offer_and_dining(self, premium_session):
        r = premium_session.get(f"{BASE_URL}/api/shell/home", timeout=15)
        d = r.json()
        assert "native_offer" in d
        assert "dining" in d
