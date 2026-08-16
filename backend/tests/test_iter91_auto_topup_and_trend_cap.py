"""Iteration 91 backend verification:
- POST /api/merchant/marketplace/category-bid/auto-topup toggles auto_topup + persists
  amount_cents + payment_method_id (returns {ok:true, auto_topup:<bool>})
- GET /api/merchant/marketplace/category-bid returns bid (with auto_topup after save),
  saved_cards + default_pm
- GET /api/merchant/marketplace/promotion/analytics returns trend[] where each point
  has a 'capped' boolean field (marker used by UI)
"""
from __future__ import annotations

import os

import pytest
import requests

def _load_backend_url() -> str:
    if os.environ.get("REACT_APP_BACKEND_URL"):
        return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
    env_path = "/app/frontend/.env"
    with open(env_path) as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
MERCHANT_EMAIL = "test@bigfm.dubai"
MERCHANT_PASSWORD = "TestUser123!"


@pytest.fixture(scope="module")
def merchant_token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": MERCHANT_EMAIL, "password": MERCHANT_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    tok = r.json().get("session_token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="module")
def auth(merchant_token):
    return {"Authorization": f"Bearer {merchant_token}"}


# ---- category-bid GET (used by UI to gate the toggle vs add-a-card hint) ----
class TestCategoryBidRead:
    def test_get_bid_shape(self, auth):
        r = requests.get(f"{BASE_URL}/api/merchant/marketplace/category-bid",
                         headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "bid" in data
        assert "saved_cards" in data and isinstance(data["saved_cards"], list)
        assert "default_pm" in data  # may be None
        # There should be at least one saved card (seeded by iter73 for QA)
        assert len(data["saved_cards"]) >= 1, "expected at least one saved card for merchant"
        assert data["bid"] is not None, "merchant should have an existing category bid"
        assert data["bid"].get("category")
        assert isinstance(data["bid"].get("bid_cents"), int)


# ---- auto-topup endpoint round-trip ----
class TestAutoTopupToggle:
    def test_enable_auto_topup(self, auth):
        # Fetch current default_pm to send with the toggle
        cb = requests.get(f"{BASE_URL}/api/merchant/marketplace/category-bid",
                          headers=auth, timeout=15).json()
        pm = cb.get("default_pm") or (cb.get("saved_cards") or [{}])[0].get("id")
        assert pm, "no saved payment method to attach for auto-topup"
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/category-bid/auto-topup",
                          headers=auth,
                          json={"enabled": True, "amount_cents": 1500,
                                "payment_method_id": pm}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j == {"ok": True, "auto_topup": True} or (j.get("ok") is True and j.get("auto_topup") is True), j

        # Verify persistence via GET
        cb2 = requests.get(f"{BASE_URL}/api/merchant/marketplace/category-bid",
                           headers=auth, timeout=15).json()
        assert cb2["bid"].get("auto_topup") is True
        assert int(cb2["bid"].get("auto_topup_amount_cents", 0)) == 1500
        assert cb2["bid"].get("auto_topup_pm") == pm

    def test_disable_auto_topup(self, auth):
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/category-bid/auto-topup",
                          headers=auth,
                          json={"enabled": False, "amount_cents": 1500}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("auto_topup") is False

        cb = requests.get(f"{BASE_URL}/api/merchant/marketplace/category-bid",
                          headers=auth, timeout=15).json()
        assert cb["bid"].get("auto_topup") is False

    def test_re_enable_for_ui_verification(self, auth):
        """Leave auto_topup=True so the UI flow can be verified visually."""
        cb = requests.get(f"{BASE_URL}/api/merchant/marketplace/category-bid",
                          headers=auth, timeout=15).json()
        pm = cb.get("default_pm") or (cb.get("saved_cards") or [{}])[0].get("id")
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/category-bid/auto-topup",
                          headers=auth,
                          json={"enabled": True, "amount_cents": 1000,
                                "payment_method_id": pm}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("auto_topup") is True


# ---- promotion analytics trend[].capped for the daily-cap marker ----
class TestAnalyticsCappedFlag:
    def test_trend_points_have_capped_flag(self, auth):
        r = requests.get(f"{BASE_URL}/api/merchant/marketplace/promotion/analytics",
                         headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "trend" in data and isinstance(data["trend"], list), data
        assert len(data["trend"]) >= 1, "trend should have at least one data point"
        for pt in data["trend"]:
            assert "date" in pt and isinstance(pt["date"], str)
            assert "views" in pt
            assert "capped" in pt, f"missing 'capped' flag on trend point: {pt}"
            assert isinstance(pt["capped"], bool), f"'capped' must be bool: {pt}"
