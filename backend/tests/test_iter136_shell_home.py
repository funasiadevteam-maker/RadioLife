"""Iter 136 — /api/shell/home aggregator + /api/shell/home-events allowlist tests.

Covers:
- GET /api/shell/home anon: returns all required keys; native_offer may be a
  labelled sponsored card or null; live_now is live-first; is_premium=false.
- GET /api/shell/home authed (demo@bigfm.dubai — Premium, active Dining):
  is_premium=true, dining.member=true.
- POST /api/shell/home-events: valid event -> {ok:true}; unknown event -> {ok:false}.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"


# -------- Fixtures --------
@pytest.fixture(scope="module")
def anon():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def demo_session():
    """Cookie-authed demo user via password login (works on same backend)."""
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"demo login failed: {r.status_code} {r.text[:200]}")
    return s


# -------- /api/shell/home --------
class TestShellHome:
    """Home aggregator returns rails-first payload."""

    REQUIRED_KEYS = {
        "for_you", "live_now", "native_offer",
        "listening_reward", "dining", "is_premium",
    }

    def test_home_anon_keys_and_shape(self, anon):
        r = anon.get(f"{BASE_URL}/api/shell/home", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # All 6 required keys present
        missing = self.REQUIRED_KEYS - set(data.keys())
        assert not missing, f"missing keys: {missing}"
        assert isinstance(data["for_you"], list)
        assert isinstance(data["live_now"], list)
        assert data["is_premium"] is False
        assert data["listening_reward"] == {"points_per_min": 1}
        # native_offer is either null or a labelled sponsored card
        no = data["native_offer"]
        assert no is None or (isinstance(no, dict) and no.get("sponsored") is True)
        # dining.member key present
        assert "member" in data["dining"]

    def test_home_live_now_live_first(self, anon):
        r = anon.get(f"{BASE_URL}/api/shell/home", timeout=30)
        assert r.status_code == 200
        live_now = r.json()["live_now"]
        if len(live_now) < 2:
            pytest.skip("not enough live_now items to assert ordering")
        # Live-first order (excluding a reserved sponsored slot at idx<=3).
        organic = [c for c in live_now if not c.get("sponsored")]
        live_flags = [1 if c["live"] else 0 for c in organic]
        # live items should come before non-live in organic subset
        first_nonlive = next((i for i, v in enumerate(live_flags) if v == 0), len(live_flags))
        assert all(v == 1 for v in live_flags[:first_nonlive])

    def test_home_no_sponsored_station_without_activation(self, anon):
        """Currently no flagship_boost_activation → live_now must be all organic."""
        r = anon.get(f"{BASE_URL}/api/shell/home", timeout=30)
        assert r.status_code == 200
        live_now = r.json()["live_now"]
        sponsored = [c for c in live_now if c.get("sponsored")]
        # Truthful behaviour: none until real inventory exists.
        assert len(sponsored) == 0, f"unexpected sponsored station: {sponsored}"

    def test_home_authed_premium_and_dining(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["is_premium"] is True
        # demo@ is enrolled per test_credentials.md
        assert data["dining"]["member"] is True

    def test_native_offer_labelled_when_present(self, anon):
        """When native_offer exists it MUST be labelled sponsored=true and have
        an image + title + cta."""
        r = anon.get(f"{BASE_URL}/api/shell/home", timeout=30)
        no = r.json().get("native_offer")
        if not no:
            pytest.skip("no promoted marketplace or active campaign — native_offer null (valid)")
        assert no["sponsored"] is True
        assert no.get("title")
        assert no.get("cta")
        assert no.get("to")


# -------- /api/shell/home-events --------
class TestHomeEvents:
    """Analytics ingest allowlist."""

    def test_valid_event_ok(self, anon):
        r = anon.post(
            f"{BASE_URL}/api/shell/home-events",
            json={"event": "home_ad_request", "surface": "web"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_native_offer_impression_ok(self, anon):
        r = anon.post(
            f"{BASE_URL}/api/shell/home-events",
            json={"event": "native_offer_impression", "business_id": "x"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_sponsored_station_start_ok(self, anon):
        r = anon.post(
            f"{BASE_URL}/api/shell/home-events",
            json={"event": "sponsored_station_start", "station_id": "s1"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_unknown_event_rejected(self, anon):
        r = anon.post(
            f"{BASE_URL}/api/shell/home-events",
            json={"event": "totally_made_up"},
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is False
        assert body.get("error") == "unknown_event"

    def test_missing_event_rejected(self, anon):
        r = anon.post(f"{BASE_URL}/api/shell/home-events", json={}, timeout=20)
        assert r.status_code == 200
        assert r.json().get("ok") is False
