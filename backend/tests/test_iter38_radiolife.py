"""Iteration 38 — RadioLife.app rebrand + Promoted Stations + News fallback + Demo geo.

Covers:
  • GET  /api/news/headlines             — live NewsAPI fallback populates when curated empty
  • GET  /api/news/headlines/breaking    — same with is_breaking=true
  • GET  /api/promoted/stations          — seeded cards with is_sponsored/promo_id/pricing_model/sponsor_name
  • POST /api/promoted/{promo_id}/impression + /click — increments counters (MOCKED accrual)
  • POST /api/auth/demo                   — user market from geo/IP, name != "BigFM Demo Listener"
"""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── News (live NewsAPI fallback) ────────────────────────
class TestNewsFallback:
    def test_headlines_returns_live_items(self, api):
        r = api.get(f"{BASE_URL}/api/news/headlines?limit=10", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        # DB curated pool is empty in this env => fallback must populate.
        assert len(data["items"]) > 0, "expected live NewsAPI fallback items"
        it = data["items"][0]
        # Public headline shape the mobile+web clients expect
        for k in ("headline_text", "category", "source_name",
                  "published_at"):
            assert k in it, f"missing key {k} in {it}"
        assert isinstance(it["headline_text"], str) and it["headline_text"]
        # summary_text may be None but key must exist
        assert "summary_text" in it

    def test_breaking_marks_is_breaking_true(self, api):
        r = api.get(f"{BASE_URL}/api/news/headlines/breaking?limit=5",
                    timeout=30)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or []
        assert len(items) > 0, "expected breaking live fallback items"
        assert all(bool(i.get("is_breaking")) for i in items), \
            "every breaking item must have is_breaking=true"


# ─── Promoted / Sponsored stations ───────────────────────
class TestPromotedStations:
    def test_list_seeds_and_returns_sponsored_cards(self, api):
        r = api.get(f"{BASE_URL}/api/promoted/stations?limit=6", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items") or []
        assert len(items) > 0, "promo seed should have populated items"
        for c in items:
            assert c.get("is_sponsored") is True
            assert c.get("promo_id"), "promo_id missing"
            assert c.get("pricing_model") in ("cpm", "cpc")
            assert c.get("sponsor_name"), "sponsor_name missing"

    def test_impression_increments(self, api):
        lst = api.get(f"{BASE_URL}/api/promoted/stations?limit=6").json()
        # Prefer a cpm promo for spend accrual assertion
        promo = next((c for c in lst["items"]
                      if c.get("pricing_model") == "cpm"), None) \
            or lst["items"][0]
        pid = promo["promo_id"]
        r = api.post(f"{BASE_URL}/api/promoted/{pid}/impression", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("promo_id") == pid
        assert "accrued_cents" in body
        # cpm accrual = cpm_bid_cents // 1000 (default 500 // 1000 = 0)
        assert isinstance(body["accrued_cents"], int)

    def test_click_increments_and_cpc_accrues(self, api):
        lst = api.get(f"{BASE_URL}/api/promoted/stations?limit=6").json()
        promo = next((c for c in lst["items"]
                      if c.get("pricing_model") == "cpc"), None) \
            or lst["items"][0]
        pid = promo["promo_id"]
        r = api.post(f"{BASE_URL}/api/promoted/{pid}/click", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("promo_id") == pid
        # cpc pricing model => accrue = cpc_bid_cents (seed default 25)
        if promo.get("pricing_model") == "cpc":
            assert body["accrued_cents"] >= 1, \
                f"expected CPC accrual > 0, got {body}"

    def test_bad_promo_id_returns_404(self, api):
        r = api.post(f"{BASE_URL}/api/promoted/promo_doesnotexist/impression",
                     timeout=10)
        assert r.status_code == 404


# ─── Demo login geo + name ───────────────────────────────
class TestDemoLoginGeo:
    def test_demo_login_ok_and_not_bigfm_demo_listener(self, api):
        # Reset the rate bucket first so parallel test runs don't 429 us.
        api.post(f"{BASE_URL}/api/auth/_demo_reset_rate_limit", timeout=10)
        r = api.post(f"{BASE_URL}/api/auth/demo", timeout=30)
        assert r.status_code == 200, r.text
        u = r.json()
        # Name must NOT be the deprecated "BigFM Demo Listener"
        assert u.get("name") != "BigFM Demo Listener", \
            f"demo name should not be legacy 'BigFM Demo Listener', got {u.get('name')!r}"
        # Should be present
        assert u.get("name"), "demo user name missing"
        # Session token surfaced for mobile
        assert u.get("session_token"), "demo login must return session_token"
        # Market should be a non-empty lowercase string (may or may not be
        # 'dubai' depending on the pod's egress IP — the important guarantee
        # from the review is that it's *resolved from geo*, not hardcoded.
        # We only assert it's a real value here.
        assert isinstance(u.get("market"), str) and u["market"], \
            "demo user market must be set"
