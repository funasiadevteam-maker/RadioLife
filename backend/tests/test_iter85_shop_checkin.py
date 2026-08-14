"""Iter85 — Shop check-in loyalty endpoint tests.
POST /api/shop/businesses/{biz_id}/checkin awards 50 points once/day/business.
"""
import os
import pytest
import requests

def _read_env(path, key):
    with open(path) as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    raise KeyError(key)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
BASE_URL = BASE_URL.rstrip("/")
BIZ_ID = "biz_sample_funpizza"


@pytest.fixture(scope="module")
def demo_bearer():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    tok = j.get("session_token") or j.get("token") or j.get("access_token")
    assert tok, j
    return tok


@pytest.fixture(scope="module")
def auth_headers(demo_bearer):
    return {"Authorization": f"Bearer {demo_bearer}", "Content-Type": "application/json"}


# --- Business detail: ways_to_earn structure ---
def test_business_detail_has_ways_to_earn():
    r = requests.get(f"{BASE_URL}/api/shop/businesses/{BIZ_ID}", timeout=15)
    assert r.status_code == 200, r.text
    b = r.json()["business"]
    ways = b.get("ways_to_earn")
    assert isinstance(ways, list) and len(ways) == 3
    labels = [w["label"] for w in ways]
    assert "Order / Buy" in labels
    assert "Check In" in labels
    assert "Pay with RadioLife" in labels
    # basic biz info intact
    assert b["public_name"]
    assert b["business_id"] == BIZ_ID
    assert b.get("has_menu") is True


# --- Check-in requires auth ---
def test_checkin_requires_auth():
    r = requests.post(f"{BASE_URL}/api/shop/businesses/{BIZ_ID}/checkin", timeout=10)
    assert r.status_code in (401, 403), r.text


# --- Check-in unknown business => 404 ---
def test_checkin_unknown_business(auth_headers):
    r = requests.post(f"{BASE_URL}/api/shop/businesses/biz_does_not_exist/checkin",
                      headers=auth_headers, timeout=10)
    assert r.status_code == 404


# --- Check-in awards first call, idempotent second call ---
def test_checkin_awards_then_idempotent(auth_headers):
    r1 = requests.post(f"{BASE_URL}/api/shop/businesses/{BIZ_ID}/checkin",
                       headers=auth_headers, timeout=15)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("ok") is True
    # already awarded from a previous test run today is acceptable — verify shape either way
    assert "already" in d1 and "awarded" in d1 and "points_balance" in d1
    assert isinstance(d1["points_balance"], (int, float))
    if d1["already"] is False:
        assert d1["awarded"] == 50
    else:
        assert d1["awarded"] == 0

    balance_after_first = d1["points_balance"]

    # Second call same day — must be idempotent (already=True, awarded=0, no double credit)
    r2 = requests.post(f"{BASE_URL}/api/shop/businesses/{BIZ_ID}/checkin",
                       headers=auth_headers, timeout=15)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["ok"] is True
    assert d2["already"] is True
    assert d2["awarded"] == 0
    assert d2["points_balance"] == balance_after_first  # no double-award


# --- Menu endpoint sanity for grid ~9 items ---
def test_business_menu_has_items():
    r = requests.get(f"{BASE_URL}/api/shop/businesses/{BIZ_ID}/menu", timeout=15)
    assert r.status_code == 200
    body = r.json()
    total = sum(len(s.get("items", [])) for s in body.get("sections", []))
    assert total >= 6, f"expected multi-row grid content, got {total}"
