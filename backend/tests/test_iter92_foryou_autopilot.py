"""Iteration 92 — For You personalized rail + Bid Autopilot backend verification.
Covers: /api/shop/track (view), /api/shop/home for_you section (positive+negative),
/api/merchant/marketplace/category-bid/autopilot (enable/adjust/disable),
GET /api/merchant/marketplace/category-bid reflects autopilot fields.
"""
import os
import time
import uuid
import pytest
import requests

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return None


BASE_URL = _load_url()
API = f"{BASE_URL}/api"


def _login(email: str, password: str):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json().get("session_token")


@pytest.fixture(scope="module")
def demo_token():
    return _login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="module")
def merchant_token():
    return _login("test@bigfm.dubai", "TestUser123!")


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# --- Personalized "For You" rail ---
class TestForYouRail:
    def test_shop_home_contains_for_you_after_view_and_orders(self, demo_token):
        # First seed a browse view (per-user shop_user_events)
        home = requests.get(f"{API}/shop/home", headers=_h(demo_token), timeout=30).json()
        # pick any business from any section to browse
        biz_id = None
        for sec in home.get("sections", []):
            for it in sec.get("items", []):
                biz_id = it.get("business_id")
                if biz_id:
                    break
            if biz_id:
                break
        assert biz_id, "no business available in shop home to seed browse"
        r = requests.post(f"{API}/shop/track",
                          json={"business_id": biz_id, "kind": "view"},
                          headers=_h(demo_token), timeout=30)
        assert r.status_code == 200
        assert r.json().get("ok") is True

        home2 = requests.get(f"{API}/shop/home", headers=_h(demo_token), timeout=30).json()
        sections = home2.get("sections", [])
        keys = [s.get("key") for s in sections]
        for_you = next((s for s in sections if s.get("key") == "for_you"), None)
        assert for_you is not None, f"expected for_you section, got keys={keys}"
        assert for_you.get("title") == "For You"
        assert isinstance(for_you.get("subtitle"), str) and for_you["subtitle"].startswith("Because")
        assert isinstance(for_you.get("items"), list) and len(for_you["items"]) > 0

    def test_shop_home_no_for_you_for_brand_new_user(self):
        # Sign up an ephemeral fresh user with no history
        email = f"iter92_new_{uuid.uuid4().hex[:8]}@example.com"
        payload = {"email": email, "password": "TestPass123!", "name": "Iter92 New"}
        r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
        if r.status_code not in (200, 201):
            # some backends expose /auth/signup instead
            r = requests.post(f"{API}/auth/signup", json=payload, timeout=30)
        assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text[:200]}"
        tok = r.json().get("session_token") or _login(email, "TestPass123!")
        assert tok
        home = requests.get(f"{API}/shop/home", headers=_h(tok), timeout=30).json()
        keys = [s.get("key") for s in home.get("sections", [])]
        assert "for_you" not in keys, f"brand-new user must NOT get for_you; got {keys}"
        # Must still fall back to generic Recommended
        assert "recommended" in keys


# --- Bid Autopilot ---
class TestBidAutopilot:
    def test_autopilot_enable_adjusts_bid_and_persists(self, merchant_token):
        # Baseline GET
        pre = requests.get(f"{API}/merchant/marketplace/category-bid",
                           headers=_h(merchant_token), timeout=30)
        assert pre.status_code == 200
        pre_body = pre.json()
        assert pre_body.get("bid"), "merchant must have an existing bid"
        # Enable autopilot targeting rank 1 with a cap
        body = {"enabled": True, "target_rank": 1, "max_bid_cents": 15}
        r = requests.post(f"{API}/merchant/marketplace/category-bid/autopilot",
                          json=body, headers=_h(merchant_token), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("autopilot") is True
        assert data.get("bid") is not None
        assert data["bid"].get("autopilot") is True
        assert int(data["bid"].get("autopilot_max_bid_cents")) == 15
        assert int(data["bid"].get("target_rank")) == 1
        # New bid must be within [1, cap]
        assert 1 <= int(data["bid"].get("bid_cents")) <= 15
        assert "standing" in data
        # Persistence via GET
        got = requests.get(f"{API}/merchant/marketplace/category-bid",
                          headers=_h(merchant_token), timeout=30).json()
        assert got.get("bid", {}).get("autopilot") is True
        assert int(got["bid"].get("autopilot_max_bid_cents")) == 15
        assert int(got["bid"].get("target_rank")) == 1

    def test_autopilot_rejects_out_of_range_target_rank(self, merchant_token):
        r = requests.post(f"{API}/merchant/marketplace/category-bid/autopilot",
                          json={"enabled": True, "target_rank": 6, "max_bid_cents": 10},
                          headers=_h(merchant_token), timeout=30)
        assert r.status_code == 422

    def test_autopilot_rejects_out_of_range_max_bid(self, merchant_token):
        r = requests.post(f"{API}/merchant/marketplace/category-bid/autopilot",
                          json={"enabled": True, "target_rank": 1, "max_bid_cents": 5000},
                          headers=_h(merchant_token), timeout=30)
        assert r.status_code == 422

    def test_autopilot_disable_persists(self, merchant_token):
        r = requests.post(f"{API}/merchant/marketplace/category-bid/autopilot",
                          json={"enabled": False, "target_rank": 3, "max_bid_cents": 20},
                          headers=_h(merchant_token), timeout=30)
        assert r.status_code == 200
        assert r.json().get("autopilot") is False
        got = requests.get(f"{API}/merchant/marketplace/category-bid",
                          headers=_h(merchant_token), timeout=30).json()
        assert got.get("bid", {}).get("autopilot") is False
        # target_rank + max_bid still reflected (persisted last values)
        assert int(got["bid"].get("target_rank")) == 3
        assert int(got["bid"].get("autopilot_max_bid_cents")) == 20

    def test_autopilot_reenable_top3_capped(self, merchant_token):
        r = requests.post(f"{API}/merchant/marketplace/category-bid/autopilot",
                          json={"enabled": True, "target_rank": 3, "max_bid_cents": 8},
                          headers=_h(merchant_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["autopilot"] is True
        # bid must be <= cap
        assert int(data["bid"]["bid_cents"]) <= 8
        assert int(data["bid"]["target_rank"]) == 3

    def test_track_view_logs_shop_user_event(self, demo_token):
        """POST /api/shop/track {kind:'view'} returns ok:true and doesn't 500."""
        home = requests.get(f"{API}/shop/home", headers=_h(demo_token), timeout=30).json()
        biz_id = None
        for sec in home.get("sections", []):
            for it in sec.get("items", []):
                biz_id = it.get("business_id")
                if biz_id:
                    break
            if biz_id:
                break
        assert biz_id
        r = requests.post(f"{API}/shop/track",
                          json={"business_id": biz_id, "kind": "view"},
                          headers=_h(demo_token), timeout=30)
        assert r.status_code == 200
        assert r.json().get("ok") is True
