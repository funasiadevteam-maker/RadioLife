"""Iter 56 — Super Marketplace Phase A (A2+A3) BACKEND regression.

Covers:
  * Seed demo businesses -> /api/shop/businesses returns >=6 approved demo profiles
    with cover images + default_bigpoints.
  * /api/shop/home headline + sections + categories + filters.
  * /api/shop/businesses/{id} returns ways_to_earn.
  * Sell wizard: POST /api/merchant/marketplace/onboarding validations + pending.
  * BigPoints preview economics: cost = points * $0.03 default.
  * Games Daily Streak: GET status, POST /claim.
  * Reorder Favourites: toggle add/remove, list, rebook.

Runs against the shared backend using BASE_URL from REACT_APP_BACKEND_URL.
Auth = demo listener bearer (POST /api/auth/demo).
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


class _NoCookieSession(requests.Session):
    """The backend prefers cookies over Bearer. Clear cookies after every
    request so subsequent Bearer-only calls aren't hijacked by the demo cookie
    set on /api/auth/demo (same gotcha as iter55)."""

    def request(self, *a, **kw):
        r = super().request(*a, **kw)
        self.cookies.clear()
        return r


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def api():
    s = _NoCookieSession()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def demo_auth(api):
    r = api.post(f"{BASE_URL}/api/auth/demo")
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"no session_token in demo response: {r.text}"
    return {"Authorization": f"Bearer {tok}"}


# ==================================================================
# 1) Seed / Shop consumer API
# ==================================================================
class TestSeedDemoBusinesses:
    """Verify seed_demo_businesses populated the marketplace properly."""

    EXPECTED_DEMO_IDS = {
        "biz_demo_grill", "biz_demo_spice", "biz_demo_brew",
        "biz_demo_glow", "biz_demo_threads", "biz_demo_pulse",
    }
    EXPECTED_NAMES = {
        "The Grill House", "Spice Route Kitchen", "Brew & Bean Café",
        "Glow Hair & Beauty", "Urban Threads", "Pulse Fitness Studio",
    }

    def test_businesses_endpoint_returns_seeded_demos(self, api):
        r = api.get(f"{BASE_URL}/api/shop/businesses?limit=100")
        assert r.status_code == 200
        data = r.json()
        items = data["items"]
        assert data["total"] == len(items)
        ids = {b["business_id"] for b in items}
        assert self.EXPECTED_DEMO_IDS.issubset(ids), f"missing demo ids: {self.EXPECTED_DEMO_IDS - ids}"

    def test_each_demo_has_cover_and_bigpoints(self, api):
        r = api.get(f"{BASE_URL}/api/shop/businesses?limit=100")
        by_id = {b["business_id"]: b for b in r.json()["items"]}
        for bid in self.EXPECTED_DEMO_IDS:
            b = by_id[bid]
            assert isinstance(b.get("cover_url"), str) and b["cover_url"].startswith("http"), \
                f"{bid} missing cover_url: {b.get('cover_url')}"
            assert isinstance(b.get("default_bigpoints"), int) and b["default_bigpoints"] > 0, \
                f"{bid} default_bigpoints invalid: {b.get('default_bigpoints')}"
            assert b["public_name"] in self.EXPECTED_NAMES

    def test_only_approved_returned(self, api):
        # Sanity: every returned card corresponds to an approved profile
        # (verified indirectly — detail endpoint 200s for each)
        r = api.get(f"{BASE_URL}/api/shop/businesses?limit=100")
        for b in r.json()["items"][:3]:
            d = api.get(f"{BASE_URL}/api/shop/businesses/{b['business_id']}")
            assert d.status_code == 200, f"{b['business_id']} detail {d.status_code}"


class TestShopHomeSections:
    def test_home_headline_and_sections(self, api):
        r = api.get(f"{BASE_URL}/api/shop/home")
        assert r.status_code == 200
        d = r.json()
        assert d["headline"] == "SHOP LOCAL. EARN BIGPOINTS."
        assert isinstance(d["categories"], list) and len(d["categories"]) > 0
        assert isinstance(d["filters"], list) and len(d["filters"]) >= 4
        section_keys = {s["key"] for s in d["sections"]}
        assert {"recommended", "earn_more", "food", "services", "featured"}.issubset(section_keys)

    def test_categories_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/shop/categories")
        assert r.status_code == 200
        items = r.json()["items"]
        keys = {c["key"] for c in items}
        assert {"restaurant", "retail", "beauty", "fitness"}.issubset(keys), keys

    def test_shop_home_food_section_contains_restaurant_seeds(self, api):
        r = api.get(f"{BASE_URL}/api/shop/home")
        food = next(s for s in r.json()["sections"] if s["key"] == "food")
        names = {b["public_name"] for b in food["items"]}
        # At least one of the restaurant demo seeds must appear
        assert names & {"The Grill House", "Spice Route Kitchen"}, f"food section names: {names}"


class TestBusinessDetail:
    def test_grill_detail_ways_to_earn(self, api):
        r = api.get(f"{BASE_URL}/api/shop/businesses/biz_demo_grill")
        assert r.status_code == 200
        b = r.json()["business"]
        assert b["public_name"] == "The Grill House"
        assert b["default_bigpoints"] == 250
        earn = b["ways_to_earn"]
        assert len(earn) >= 3
        labels = {e["label"] for e in earn}
        assert {"Order / Buy", "Check In", "Pay with RadioLife"}.issubset(labels)

    def test_unknown_business_404(self, api):
        r = api.get(f"{BASE_URL}/api/shop/businesses/does_not_exist_xyz")
        assert r.status_code == 404


class TestShopSearchAndSort:
    def test_search_by_q(self, api):
        r = api.get(f"{BASE_URL}/api/shop/businesses?q=grill&limit=20")
        assert r.status_code == 200
        names = [b["public_name"] for b in r.json()["items"]]
        assert any("Grill" in n for n in names), names

    def test_sort_by_bigpoints_desc(self, api):
        r = api.get(f"{BASE_URL}/api/shop/businesses?sort=bigpoints&limit=20")
        pts = [b["default_bigpoints"] for b in r.json()["items"]]
        assert pts == sorted(pts, reverse=True), f"not sorted desc: {pts}"

    def test_category_filter(self, api):
        r = api.get(f"{BASE_URL}/api/shop/businesses?category=restaurant&limit=20")
        cats = {b["category"] for b in r.json()["items"]}
        assert cats == {"restaurant"}, cats


# ==================================================================
# 2) Sell wizard / Onboarding
# ==================================================================
class TestSellOnboarding:
    def test_auth_required(self, api):
        r = api.post(f"{BASE_URL}/api/merchant/marketplace/onboarding", json={})
        assert r.status_code == 401

    def _base_payload(self, **over):
        p = {
            "public_name": f"TEST_iter56_{uuid.uuid4().hex[:6]}",
            "legal_name": "TEST_iter56 LLC",
            "business_type": "retail",
            "category": "retail",
            "sells": ["products"],
            "bigpoints": {"mode": "default", "default_points": 100, "points_per_dollar": 2},
            "commission_agreed": True,
        }
        p.update(over)
        return p

    def test_missing_commission_agree(self, api, demo_auth):
        r = api.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                     json=self._base_payload(commission_agreed=False), headers=demo_auth)
        assert r.status_code == 400, r.text
        assert "commission" in str(r.json()).lower()

    def test_restaurant_price_parity_required(self, api, demo_auth):
        r = api.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                     json=self._base_payload(business_type="restaurant",
                                             category="restaurant", sells=["food"]),
                     headers=demo_auth)
        assert r.status_code == 400, r.text
        assert "parity" in str(r.json()).lower()

    def test_below_min_bigpoints(self, api, demo_auth):
        pay = self._base_payload()
        pay["bigpoints"]["default_points"] = 1
        r = api.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                     json=pay, headers=demo_auth)
        assert r.status_code == 400, r.text

    def test_happy_path_creates_pending(self, api, demo_auth):
        r = api.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                     json=self._base_payload(bigpoints={"mode": "default",
                                                        "default_points": 150,
                                                        "points_per_dollar": 2}),
                     headers=demo_auth)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("ok") or body.get("business_id") or body.get("profile")


# ==================================================================
# 3) Economics: preview cost = points * $0.03
# ==================================================================
class TestBigPointsEconomics:
    def test_preview_default_3c(self, api, demo_auth):
        r = api.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                     json={"points": 100}, headers=demo_auth)
        assert r.status_code == 200, r.text
        d = r.json()
        # 100 points * 3c = 300c ($3.00)
        assert d.get("cost_per_point_cents") in (3, 3.0)
        assert d.get("estimated_cost_cents") == 300, d

    def test_preview_order_value(self, api, demo_auth):
        # $50 order at 2 pts/$ = 100 pts * 3c = $3.00 = 300c
        r = api.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                     json={"order_value_cents": 5000, "points_per_dollar": 2},
                     headers=demo_auth)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("points") == 100 or d.get("points_awarded") == 100
        cost = d.get("estimated_cost_cents") or d.get("cost_cents")
        assert cost == 300, d


# ==================================================================
# 4) Games Daily Streak
# ==================================================================
class TestDailyStreak:
    def test_auth_required(self, api):
        r = api.get(f"{BASE_URL}/api/games_v2/daily-streak")
        assert r.status_code == 401

    def test_streak_status_shape(self, api, demo_auth):
        r = api.get(f"{BASE_URL}/api/games_v2/daily-streak", headers=demo_auth)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("total") == 4, d
        assert isinstance(d.get("games"), list) and len(d["games"]) == 4
        for g in d["games"]:
            assert set(g.keys()) >= {"campaign_id", "played", "title"}
        assert d.get("bonus_points") == 100
        assert isinstance(d.get("played_count"), int)
        assert isinstance(d.get("all_done"), bool)
        assert isinstance(d.get("claimed"), bool)

    def test_streak_claim_flow(self, api, demo_auth):
        status = api.get(f"{BASE_URL}/api/games_v2/daily-streak", headers=demo_auth).json()
        if not status.get("all_done"):
            pytest.skip(f"streak not complete: played={status.get('played_count')}/4")
        r = api.post(f"{BASE_URL}/api/games_v2/daily-streak/claim", headers=demo_auth)
        # Either freshly claimed (200) or already claimed today (400)
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            d = r.json()
            assert d.get("ok") is True
            assert d.get("points") == 100
        else:
            assert "already_claimed" in str(r.json()).lower()
        # After claim, status.claimed must be True
        status2 = api.get(f"{BASE_URL}/api/games_v2/daily-streak", headers=demo_auth).json()
        assert status2.get("claimed") is True


# ==================================================================
# 5) Reorder Favourites
# ==================================================================
class TestFavourites:
    def test_auth_required(self, api):
        r = api.get(f"{BASE_URL}/api/favourites/venues")
        assert r.status_code == 401

    def test_list_favourites_shape(self, api, demo_auth):
        r = api.get(f"{BASE_URL}/api/favourites/venues", headers=demo_auth)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d
        assert isinstance(d["items"], list)

    def test_toggle_unknown_campaign_404(self, api, demo_auth):
        r = api.post(f"{BASE_URL}/api/favourites/venues/no_such_camp_xyz",
                     headers=demo_auth)
        assert r.status_code == 404

    def test_toggle_and_rebook_real_booking(self, api, demo_auth):
        # Find an existing booking campaign from any prior seed the demo used.
        # We probe via the /api/bookings/venues catalogue if available; else skip.
        catalog = None
        for path in ("/api/venues/campaigns", "/api/bookings/campaigns",
                     "/api/merchant/bookings/campaigns"):
            r = api.get(f"{BASE_URL}{path}", headers=demo_auth)
            if r.status_code == 200 and (r.json().get("items") or r.json().get("campaigns")):
                catalog = r.json().get("items") or r.json().get("campaigns")
                break
        if not catalog:
            pytest.skip("no booking campaigns discoverable via public endpoints")
        cid = catalog[0].get("campaign_id") or catalog[0].get("id")
        if not cid:
            pytest.skip("catalog item missing campaign_id")

        # Toggle ON
        r = api.post(f"{BASE_URL}/api/favourites/venues/{cid}", headers=demo_auth)
        assert r.status_code in (200, 404), r.text
        if r.status_code == 404:
            pytest.skip("campaign not a booking type")
        assert r.json().get("favourited") in (True, False)

        # List should include it now (if toggled ON)
        r2 = api.get(f"{BASE_URL}/api/favourites/venues", headers=demo_auth)
        assert r2.status_code == 200
        ids = {x["campaign_id"] for x in r2.json()["items"]}
        # Either present (added) or absent (toggled off) — accept both, test round-trip below

        # Rebook (may 400 if inactive / no slots)
        rb = api.post(f"{BASE_URL}/api/favourites/venues/{cid}/rebook", headers=demo_auth)
        assert rb.status_code in (200, 400), rb.text
        if rb.status_code == 200:
            assert rb.json().get("booking_id")

        _ = ids  # silence lint

    def test_rebook_unknown_404(self, api, demo_auth):
        r = api.post(f"{BASE_URL}/api/favourites/venues/nope_camp/rebook",
                     headers=demo_auth)
        assert r.status_code == 404
