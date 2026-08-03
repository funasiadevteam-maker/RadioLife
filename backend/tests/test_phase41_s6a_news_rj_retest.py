"""
Retest for Phase 41 S6.A P1 #1 — news_radio RJ script.
Validates that /api/radio/next no longer 500s on news_anchor and that the
rj_script does NOT contain 'BigFM Dubai' but DOES contain 'BigFM News'.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
CREATOR_EMAIL = "test@bigfm.dubai"
CREATOR_PASS = "TestUser123!"


@pytest.fixture(scope="module")
def creator_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CREATOR_EMAIL, "password": CREATOR_PASS},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json().get("session_token") or r.json().get("token")


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def test_news_radio_start_returns_first_segment(creator_token):
    r = requests.post(
        f"{BASE_URL}/api/radio/start",
        json={"channel": "news_radio"},
        headers=_h(creator_token),
        timeout=30,
    )
    assert r.status_code == 200, f"start failed: {r.status_code} {r.text}"
    body = r.json()
    assert "session_id" in body, body
    assert "segment" in body, body


def test_news_radio_next_returns_news_anchor_no_500(creator_token):
    s = requests.post(
        f"{BASE_URL}/api/radio/start",
        json={"channel": "news_radio"},
        headers=_h(creator_token),
        timeout=30,
    ).json()
    sid = s["session_id"]

    # iterate up to 6 next calls to find a news_anchor (allow OpenAI/TTS time)
    found = None
    for i in range(6):
        r = requests.get(
            f"{BASE_URL}/api/radio/next",
            params={"session_id": sid},
            headers=_h(creator_token),
            timeout=60,
        )
        assert r.status_code == 200, f"/radio/next regressed: {r.status_code} {r.text[:400]}"
        seg = r.json().get("segment") or {}
        if seg.get("kind") == "news_anchor":
            found = seg
            break
        time.sleep(1)

    assert found is not None, "Did not encounter a news_anchor segment in 6 /next calls"
    # track_id must be None for news_anchor
    assert found.get("track_id") in (None, ""), f"track_id should be null for news_anchor, got {found.get('track_id')}"
    rj = found.get("rj_script") or ""
    assert isinstance(rj, str) and len(rj) > 0, f"rj_script empty: {found}"
    assert "BigFM Dubai" not in rj, f"rj_script must not contain 'BigFM Dubai': {rj[:300]}"
    assert "BigFM News" in rj, f"rj_script should contain 'BigFM News': {rj[:300]}"


def test_smoke_earnings_endpoints(creator_token):
    r = requests.get(f"{BASE_URL}/api/me/earnings", headers=_h(creator_token), timeout=20)
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE_URL}/api/stations/p41-audit-test/earnings", headers=_h(creator_token), timeout=20)
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE_URL}/api/me/stripe_connect/status", headers=_h(creator_token), timeout=20)
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE_URL}/api/community/top_listened?limit=10", headers=_h(creator_token), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tier_used" in body, body


def test_non_owner_blocked_on_station_earnings():
    tok = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"},
        timeout=20,
    ).json().get("session_token")
    r = requests.get(f"{BASE_URL}/api/stations/p41-audit-test/earnings", headers=_h(tok), timeout=20)
    assert r.status_code == 403, f"expected 403 for non-owner, got {r.status_code}: {r.text[:200]}"
