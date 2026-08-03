"""
Phase PREROLL.EXT + ADMIN.NAV.1 backend tests.

Covers:
- New OpenAPI routes exist
- Preroll works for flagship / imported / ai_channel / community stations
- Admin per-station preroll toggle
- Top spenders analytics endpoint
- Advertiser priority-adjust endpoint (bump / restrict / clamp)
- Regression smoke: existing preroll endpoint remains intact
"""

import os
import uuid
import requests
import pytest

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Read from frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not configured"
    return url.rstrip("/")


BASE_URL = _load_backend_url()

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
TEST_EMAIL = "test@bigfm.dubai"
TEST_PASS = "TestUser123!"

STATIONS = {
    "flagship": "imp_fun_talk_1003_uae",
    "imported": "imp_780122061aa111e9a8",
    "ai_channel": "bollywood_mehfil",
    "community": "stn_d611ab37d81a",
}

ADVERTISER_ID = "advv2_9fac10b21f5595"


def _login(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def test_user():
    return _login(TEST_EMAIL, TEST_PASS)


# ---------- OpenAPI ----------
def test_openapi_contains_new_routes():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=30)
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    expected = [
        "/api/admin/stations/{station_id}/preroll",
        "/api/ad-review/analytics/top-spenders",
        "/api/ad-review/advertisers/{advertiser_id}/priority-adjust",
    ]
    missing = [p for p in expected if p not in paths]
    assert not missing, f"missing openapi paths: {missing}"


# ---------- Preroll on all station types ----------
@pytest.mark.parametrize("station_type,station_id", list(STATIONS.items()))
def test_preroll_on_all_station_types(test_user, station_type, station_id):
    sess = str(uuid.uuid4())
    r = test_user.post(
        f"{BASE_URL}/api/live-radio/preroll/request",
        json={"station_id": station_id, "session_id": sess, "country_code": "AE"},
        timeout=30,
    )
    assert r.status_code == 200, f"{station_type} {station_id}: {r.status_code} {r.text[:300]}"
    body = r.json()
    # If no eligible creative in inventory, has_preroll may be false. Assert structure.
    assert "has_preroll" in body
    if body.get("has_preroll"):
        assert body.get("station_type") in {"flagship", "imported", "ai_channel", "community"}, body
        ad = body.get("ad") or {}
        assert ad.get("audio_url"), f"missing audio_url in ad for {station_id}: {body}"
    else:
        # Ensure not 'imp_ gate' failure — reason should not be about station-type restriction
        reason = body.get("reason", "")
        assert reason not in {"station_not_eligible", "unsupported_station_type"}, body


# ---------- Admin per-station toggle ----------
def test_admin_station_preroll_toggle(admin, test_user):
    station = "bollywood_mehfil"
    # disable
    r = admin.patch(
        f"{BASE_URL}/api/admin/stations/{station}/preroll",
        json={"enabled": False},
        timeout=30,
    )
    assert r.status_code in (200, 204), f"toggle off failed: {r.status_code} {r.text[:200]}"

    # request preroll -> should be disabled
    sess = str(uuid.uuid4())
    r2 = test_user.post(
        f"{BASE_URL}/api/live-radio/preroll/request",
        json={"station_id": station, "session_id": sess, "country_code": "AE"},
        timeout=30,
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body.get("has_preroll") is False, body
    assert body.get("reason") == "preroll_disabled_for_station", body

    # re-enable
    r3 = admin.patch(
        f"{BASE_URL}/api/admin/stations/{station}/preroll",
        json={"enabled": True},
        timeout=30,
    )
    assert r3.status_code in (200, 204)


# ---------- Top spenders analytics ----------
def test_top_spenders_analytics(admin):
    r = admin.get(
        f"{BASE_URL}/api/ad-review/analytics/top-spenders?window_days=30&limit=10",
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else body
    assert isinstance(items, list), body
    if items:
        row = items[0]
        for key in ("advertiser_id", "advertiser_name", "spend_cents",
                    "reject_rate_pct", "avg_ttr_secs", "priority_score_boost"):
            assert key in row, f"missing field {key} in top-spenders row: {row}"


# ---------- Priority adjust ----------
def test_priority_adjust_bump_and_restrict(admin):
    # bump +5
    r = admin.post(
        f"{BASE_URL}/api/ad-review/advertisers/{ADVERTISER_ID}/priority-adjust",
        json={"delta": 5},
        timeout=30,
    )
    assert r.status_code == 200, f"bump failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("priority_score_boost") == 5, body

    # restore -5
    r2 = admin.post(
        f"{BASE_URL}/api/ad-review/advertisers/{ADVERTISER_ID}/priority-adjust",
        json={"delta": -5},
        timeout=30,
    )
    assert r2.status_code == 200
    assert r2.json().get("priority_score_boost") == 0, r2.json()


def test_priority_adjust_clamp_validation(admin):
    r = admin.post(
        f"{BASE_URL}/api/ad-review/advertisers/{ADVERTISER_ID}/priority-adjust",
        json={"delta": 11},
        timeout=30,
    )
    assert r.status_code == 422, f"expected 422 for delta=11, got {r.status_code} {r.text[:200]}"
