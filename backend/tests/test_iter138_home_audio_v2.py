"""Iter 138 — Home Audio V2 follow-ups (companion demo seed, ad-revenue report,
ad pacing, sponsored station in Live Right Now)."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login {creds['email']} → {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE)


@pytest.fixture(scope="module")
def demo_session():
    return _login(DEMO)


# ---------- 1. SEED presence ----------

class TestSeedPresence:
    def test_shell_home_has_sponsored_station(self, demo_session):
        r = demo_session.get(f"{API}/shell/home", timeout=15)
        assert r.status_code == 200
        data = r.json()
        live_now = data.get("live_now") or data.get("liveNow") or []
        sponsored = [s for s in live_now if s.get("sponsored")]
        assert len(sponsored) >= 1, f"Expected >=1 sponsored station, got {sponsored}"
        # Find Beat 97.8
        beat = next((s for s in sponsored if "Beat 97.8" in (s.get("name") or "")), None)
        assert beat is not None, f"Beat 97.8 not in live_now sponsored slots: {[s.get('name') for s in live_now]}"
        assert beat.get("sponsored") is True
        assert beat.get("sponsor_business_id") == "biz_demo_grill", beat

    def test_preroll_returns_grill_house_with_companion(self):
        # Fresh anonymous session (no cookies)
        sid = f"iter138_{uuid.uuid4().hex[:12]}"
        r = requests.post(
            f"{API}/live-radio/preroll/request",
            json={"station_id": "imp_fun_beat_978_uae", "session_id": sid},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data.get("has_preroll") is True, f"Expected has_preroll=true, got {data}"
        ad = data.get("ad") or {}
        name = ad.get("name") or ad.get("advertiser_name") or ""
        assert "Grill House" in name, f"Expected Grill House ad, got {ad}"
        assert ad.get("companion_image_url"), f"No companion_image_url in {ad}"
        assert ad.get("attached_offer_id") == "offer_demo_companion", ad


# ---------- 2. AD REVENUE REPORT ----------

class TestAdRevenueReport:
    REQUIRED_KEYS = {
        "window_days", "listening", "audio_ads", "native", "sponsored_station",
        "companion", "display", "conversions", "estimated_revenue_cents",
        "estimated_revenue_per_listening_hour_cents", "by_variant",
        "variant_note", "cpm_assumptions_cents",
    }

    def test_report_7d(self, admin_session):
        r = admin_session.get(f"{API}/admin/ad-revenue/home-report?days=7", timeout=15)
        assert r.status_code == 200
        data = r.json()
        missing = self.REQUIRED_KEYS - set(data.keys())
        assert not missing, f"Missing keys: {missing}"
        assert data["window_days"] == 7

    def test_report_1d(self, admin_session):
        r = admin_session.get(f"{API}/admin/ad-revenue/home-report?days=1", timeout=15)
        assert r.status_code == 200
        assert r.json()["window_days"] == 1

    def test_report_30d(self, admin_session):
        r = admin_session.get(f"{API}/admin/ad-revenue/home-report?days=30", timeout=15)
        assert r.status_code == 200
        assert r.json()["window_days"] == 30

    def test_report_anon_rejected(self):
        r = requests.get(f"{API}/admin/ad-revenue/home-report?days=7", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_report_nonadmin_rejected(self, free_session):
        r = free_session.get(f"{API}/admin/ad-revenue/home-report?days=7", timeout=15)
        assert r.status_code in (401, 403), r.status_code


# ---------- 3. AD PACING PERSISTENCE (backend endpoints) ----------

class TestAdPacing:
    def test_hop_cooldown_get_and_patch(self, admin_session):
        # GET current
        r = admin_session.get(f"{API}/admin/preroll/hop-cooldown", timeout=15)
        assert r.status_code == 200
        original = r.json().get("effective_seconds", 90)

        # PATCH valid
        r = admin_session.patch(
            f"{API}/admin/preroll/hop-cooldown", json={"seconds": 120}, timeout=15
        )
        assert r.status_code == 200
        assert r.json().get("effective_seconds") == 120

        # PATCH invalid (700)
        r = admin_session.patch(
            f"{API}/admin/preroll/hop-cooldown", json={"seconds": 700}, timeout=15
        )
        assert r.status_code in (400, 422), r.status_code

        # Verify still 120
        r = admin_session.get(f"{API}/admin/preroll/hop-cooldown", timeout=15)
        assert r.json().get("effective_seconds") == 120

        # RESTORE to 90
        r = admin_session.patch(
            f"{API}/admin/preroll/hop-cooldown", json={"seconds": 90}, timeout=15
        )
        assert r.status_code == 200

    def test_cadence_get_and_patch(self, admin_session):
        r = admin_session.get(f"{API}/admin/midstream-ad/cadence", timeout=15)
        assert r.status_code == 200
        # PATCH valid
        r = admin_session.patch(
            f"{API}/admin/midstream-ad/cadence", json={"every_n_songs": 5}, timeout=15
        )
        assert r.status_code == 200, r.text[:200]
        # PATCH invalid — 10 (should be 2-8)
        r = admin_session.patch(
            f"{API}/admin/midstream-ad/cadence", json={"every_n_songs": 10}, timeout=15
        )
        assert r.status_code in (400, 422), r.status_code
        # RESTORE to 4
        r = admin_session.patch(
            f"{API}/admin/midstream-ad/cadence", json={"every_n_songs": 4}, timeout=15
        )
        assert r.status_code == 200

    def test_chain_count_get_and_patch(self, admin_session):
        r = admin_session.get(f"{API}/admin/preroll/chain-count", timeout=15)
        assert r.status_code == 200
        orig = r.json()
        # PATCH valid
        r = admin_session.patch(
            f"{API}/admin/preroll/chain-count", json={"count": 2}, timeout=15
        )
        assert r.status_code == 200, r.text[:200]
        # Invalid — 10
        r = admin_session.patch(
            f"{API}/admin/preroll/chain-count", json={"count": 10}, timeout=15
        )
        assert r.status_code in (400, 422)
        # Restore to original count if present, else 3
        prior = orig.get("count") or orig.get("effective_count") or orig.get("chain_count") or 3
        r = admin_session.patch(
            f"{API}/admin/preroll/chain-count", json={"count": int(prior)}, timeout=15
        )
        assert r.status_code == 200


# ---------- 4. SPONSORED STATION event ----------

class TestSponsoredStationEvent:
    def test_home_events_accepts_sponsored_station_start(self, demo_session):
        payload = {"event": "sponsored_station_start",
                   "station_id": "imp_fun_beat_978_uae",
                   "variant": "audio_v2"}
        r = demo_session.post(f"{API}/shell/home-events", json=payload, timeout=15)
        assert r.status_code in (200, 201, 204), f"{r.status_code} {r.text[:200]}"
