"""iter143 — Landing analytics + preserve-intent regression.

Verifies:
- POST /api/shell/landing-event accepts anonymous CTA/section/preview events
- Unknown events rejected
- Anonymous cannot GET /api/shell/landing-analytics (403)
- Admin can GET aggregated report with expected shape
- Regression: /api/live-radio/stations returns items and the landing preferred https ones exist
"""
import os
import uuid
import requests
import pytest
from pathlib import Path


def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "")
    if url:
        return url.rstrip("/")
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    return ""


BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PW = "AdminPass123!"
PREMIUM_EMAIL = "premium@bigfm.dubai"
PREMIUM_PW = "PremiumTest123!"


@pytest.fixture
def anon():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:120]}")
    return s


@pytest.fixture
def premium():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": PREMIUM_EMAIL, "password": PREMIUM_PW})
    if r.status_code != 200:
        pytest.skip(f"premium login failed: {r.status_code} {r.text[:120]}")
    return s


# ─── Landing analytics: anonymous capture ───────────────────────────
class TestLandingEventCapture:
    def test_cta_event_ok(self, anon):
        sid = f"test_{uuid.uuid4().hex[:10]}"
        r = anon.post(f"{BASE_URL}/api/shell/landing-event",
                      json={"event": "cta", "cta": "TEST_hero_start", "session_id": sid})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

    def test_section_view_event_ok(self, anon):
        sid = f"test_{uuid.uuid4().hex[:10]}"
        r = anon.post(f"{BASE_URL}/api/shell/landing-event",
                      json={"event": "section_view", "section": "TEST_public-airadio",
                            "session_id": sid})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_preview_play_event_ok(self, anon):
        sid = f"test_{uuid.uuid4().hex[:10]}"
        r = anon.post(f"{BASE_URL}/api/shell/landing-event",
                      json={"event": "preview_play", "cta": "TEST_Dance Wave",
                            "session_id": sid})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_unknown_event_rejected(self, anon):
        r = anon.post(f"{BASE_URL}/api/shell/landing-event",
                      json={"event": "nope", "session_id": "TEST_x"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is False
        assert body.get("error") == "unknown_event"


# ─── Landing analytics: admin-only report ───────────────────────────
class TestLandingAnalyticsReport:
    def test_anon_forbidden(self, anon):
        r = anon.get(f"{BASE_URL}/api/shell/landing-analytics")
        assert r.status_code == 403

    def test_non_admin_forbidden(self, premium):
        r = premium.get(f"{BASE_URL}/api/shell/landing-analytics")
        assert r.status_code == 403

    def test_admin_ok_shape(self, admin, anon):
        # Seed a couple of events so aggregates are non-zero.
        sid = f"seed_{uuid.uuid4().hex[:10]}"
        anon.post(f"{BASE_URL}/api/shell/landing-event",
                  json={"event": "cta", "cta": "iter143_seed", "session_id": sid})
        anon.post(f"{BASE_URL}/api/shell/landing-event",
                  json={"event": "section_view", "section": "iter143_section",
                        "session_id": sid})
        anon.post(f"{BASE_URL}/api/shell/landing-event",
                  json={"event": "preview_play", "cta": "iter143_preview",
                        "session_id": sid})

        r = admin.get(f"{BASE_URL}/api/shell/landing-analytics")
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("total_events", "preview_plays", "ctas", "sections"):
            assert key in data, f"missing key {key}"
        assert isinstance(data["ctas"], list)
        assert isinstance(data["sections"], list)
        assert data["total_events"] >= 3
        assert data["preview_plays"] >= 1
        # confirm our seed CTA is aggregated somewhere in top 50
        cta_keys = [c["key"] for c in data["ctas"]]
        assert "iter143_seed" in cta_keys
        # sections aggregation likewise
        sec_keys = [s["key"] for s in data["sections"]]
        assert "iter143_section" in sec_keys


# ─── Regression: live-radio stations still power the landing ────────
class TestStationsRegression:
    def test_stations_endpoint(self, anon):
        r = anon.get(f"{BASE_URL}/api/live-radio/stations?limit=40")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        # Landing prefers https streams — at least one should exist.
        has_https = any(str(s.get("stream_url", "")).startswith("https://")
                        for s in data["items"])
        assert has_https, "no https streams available — preview will not work"
