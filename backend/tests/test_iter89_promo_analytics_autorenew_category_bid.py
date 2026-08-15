"""Iteration 89 — Backend e2e for the 3 new merchant-marketplace features:
- Promo Analytics (impression/view beacons + analytics counters + extra_*)
- Auto-Renew toggle persistence + GET reflects saved_cards + default_pm
- Category Spotlight auction (categories, my bid + standing, set, pause/resume,
  topup checkout returns Stripe url) + ranking/billing on /shop/businesses
  and rail on /shop/home.

Uses the merchant test@bigfm.dubai (owns biz_dc324d800f66 in 'restaurant').
Stripe hosted checkout URL creation is verified; payments are NOT auto-completed.
"""
import os
import time
import pytest
import requests

def _base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # fall back to /app/frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _base_url()
MERCHANT_EMAIL = "test@bigfm.dubai"
MERCHANT_PW = "TestUser123!"
MERCHANT_BIZ_ID = "biz_dc324d800f66"


@pytest.fixture(scope="module")
def merchant_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": MERCHANT_EMAIL, "password": MERCHANT_PW}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"merchant login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ---------- Promo Analytics ----------
class TestPromoAnalytics:
    def test_analytics_shape(self, merchant_session):
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion/analytics", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("has_data") is True, f"expected has_data True (merchant has active promo): {d}"
        for k in ("tier", "views", "impressions", "orders", "revenue_cents",
                  "extra_views", "extra_impressions", "extra_orders",
                  "extra_revenue_cents", "prior"):
            assert k in d, f"missing analytics key {k}: {d}"
        for k in ("views", "impressions", "orders", "revenue_cents"):
            assert isinstance(d[k], int)
        assert isinstance(d["prior"], dict)
        for k in ("impressions", "views", "orders", "revenue_cents"):
            assert k in d["prior"]

    def test_beacon_increments_impressions_and_views(self, merchant_session, anon_session):
        # Read before
        r0 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion/analytics", timeout=15)
        assert r0.status_code == 200
        d0 = r0.json()
        imp0 = int(d0.get("impressions", 0))
        views0 = int(d0.get("views", 0))

        # Beacon x3 impressions + x2 views (no auth needed)
        for _ in range(3):
            rb = anon_session.post(f"{BASE_URL}/api/shop/track",
                                   json={"business_id": MERCHANT_BIZ_ID, "kind": "impression"}, timeout=10)
            assert rb.status_code == 200, rb.text
            assert rb.json().get("ok") is True
        for _ in range(2):
            rb = anon_session.post(f"{BASE_URL}/api/shop/track",
                                   json={"business_id": MERCHANT_BIZ_ID, "kind": "view"}, timeout=10)
            assert rb.status_code == 200, rb.text

        time.sleep(0.5)
        r1 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion/analytics", timeout=15)
        d1 = r1.json()
        assert int(d1["impressions"]) >= imp0 + 3, f"imp did not grow: {imp0}->{d1['impressions']}"
        assert int(d1["views"]) >= views0 + 2, f"views did not grow: {views0}->{d1['views']}"

    def test_analytics_requires_auth(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion/analytics", timeout=10)
        assert r.status_code in (401, 403)


# ---------- Auto-Renew ----------
class TestAutoRenew:
    def test_get_promotion_exposes_autorenew_and_cards(self, merchant_session):
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("business_id") == MERCHANT_BIZ_ID
        assert d.get("active") is not None, "expected an ACTIVE promotion for test@ merchant"
        assert "auto_renew" in d
        assert "saved_cards" in d and isinstance(d["saved_cards"], list)
        assert "default_pm" in d  # can be None but key must exist

    def test_toggle_auto_renew_persists(self, merchant_session):
        # Get current active promotion id
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion", timeout=15)
        assert r.status_code == 200
        active = r.json().get("active")
        assert active and active.get("promotion_id"), "no active promotion to toggle"
        pid = active["promotion_id"]

        # Toggle OFF
        r_off = merchant_session.post(
            f"{BASE_URL}/api/merchant/marketplace/promotion/{pid}/auto-renew",
            json={"enabled": False}, timeout=15)
        assert r_off.status_code == 200, r_off.text
        assert r_off.json().get("auto_renew") is False
        # Verify GET reflects
        gv = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion", timeout=15).json()
        assert gv.get("auto_renew") is False

        # Toggle ON again (with saved pm if any)
        pm = gv.get("default_pm") or (gv.get("saved_cards") or [{}])[0].get("id")
        body = {"enabled": True}
        if pm:
            body["payment_method_id"] = pm
        r_on = merchant_session.post(
            f"{BASE_URL}/api/merchant/marketplace/promotion/{pid}/auto-renew",
            json=body, timeout=15)
        assert r_on.status_code == 200, r_on.text
        assert r_on.json().get("auto_renew") is True
        gv2 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/promotion", timeout=15).json()
        assert gv2.get("auto_renew") is True

    def test_auto_renew_wrong_owner_404(self, merchant_session):
        r = merchant_session.post(
            f"{BASE_URL}/api/merchant/marketplace/promotion/promo_does_not_exist/auto-renew",
            json={"enabled": False}, timeout=10)
        assert r.status_code == 404


# ---------- Category Spotlight Auction ----------
class TestCategoryBid:
    def test_categories_list(self, merchant_session):
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid/categories", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        assert isinstance(items, list) and len(items) > 0
        assert all("key" in c and "name" in c for c in items)
        keys = {c["key"] for c in items}
        assert "restaurant" in keys, f"restaurant category missing: {keys}"

    def test_my_bid_and_standing(self, merchant_session):
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("business_id") == MERCHANT_BIZ_ID
        assert d.get("bid") is not None, "expected active seeded category bid"
        b = d["bid"]
        assert b["category"] == "restaurant"
        assert int(b["bid_cents"]) >= 1
        assert int(b.get("budget_cents", 0)) > 0
        st = d.get("standing")
        assert st is not None
        for k in ("rank", "top_bid_cents", "outbid", "suggested_bid_cents"):
            assert k in st, f"standing missing {k}: {st}"

    def test_set_bid_updates_bid_cents(self, merchant_session):
        r0 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid", timeout=15).json()
        cur_bid = int(r0["bid"]["bid_cents"])
        new_bid = 5 if cur_bid != 5 else 6
        r = merchant_session.post(
            f"{BASE_URL}/api/merchant/marketplace/category-bid/set",
            json={"category": "restaurant", "bid_cents": new_bid}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # Verify persisted
        r2 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid", timeout=15).json()
        assert int(r2["bid"]["bid_cents"]) == new_bid
        # Restore to 5c to keep budget consistent with review contract
        merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/category-bid/set",
                              json={"category": "restaurant", "bid_cents": 5}, timeout=15)

    def test_set_bid_validates_bounds(self, merchant_session):
        r = merchant_session.post(
            f"{BASE_URL}/api/merchant/marketplace/category-bid/set",
            json={"category": "restaurant", "bid_cents": 0}, timeout=10)
        assert r.status_code in (400, 422)
        r2 = merchant_session.post(
            f"{BASE_URL}/api/merchant/marketplace/category-bid/set",
            json={"category": "restaurant", "bid_cents": 1_000_000}, timeout=10)
        assert r2.status_code in (400, 422)

    def test_topup_checkout_returns_stripe_url(self, merchant_session):
        r = merchant_session.post(
            f"{BASE_URL}/api/merchant/marketplace/category-bid/topup/checkout",
            json={"amount_cents": 500, "origin_url": BASE_URL}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("checkout_url", "").startswith("https://checkout.stripe.com/"), d
        assert d.get("session_id", "").startswith("cs_")

    def test_pause_and_resume(self, merchant_session):
        rp = merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/category-bid/pause",
                                   timeout=15)
        assert rp.status_code == 200, rp.text
        rg = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid", timeout=15).json()
        assert rg["bid"]["status"] == "paused"
        rr = merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/category-bid/resume",
                                   timeout=15)
        assert rr.status_code == 200, rr.text
        assert rr.json().get("status") in ("active", "pending_budget")
        rg2 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid", timeout=15).json()
        assert rg2["bid"]["status"] in ("active", "pending_budget")


# ---------- Shop ranking + billing ----------
class TestShopRankingAndBilling:
    def test_category_search_ranks_bidder_first_and_bills(self, merchant_session, anon_session):
        # Ensure bid is active
        merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/category-bid/resume", timeout=15)
        b0 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid", timeout=15).json()
        if b0["bid"]["status"] != "active":
            pytest.skip(f"category bid not active (status={b0['bid']['status']}); can't test ranking/billing")
        budget0 = int(b0["bid"]["budget_cents"])
        bid_cents = int(b0["bid"]["bid_cents"])

        r = anon_session.get(f"{BASE_URL}/api/shop/businesses?category=restaurant&limit=40", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        assert len(items) > 0
        # bidder should be first among items
        first = items[0]
        assert first["business_id"] == MERCHANT_BIZ_ID, (
            f"expected {MERCHANT_BIZ_ID} first, got {first['business_id']}. "
            f"promoted={first.get('promoted')} spotlight={first.get('spotlight')}"
        )
        assert first.get("promoted") is True
        assert first.get("spotlight") is True

        # Budget should have decremented by bid_cents
        time.sleep(0.4)
        b1 = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/category-bid", timeout=15).json()
        budget1 = int(b1["bid"]["budget_cents"])
        assert budget1 == budget0 - bid_cents, f"budget did not drop: {budget0}->{budget1} (bid={bid_cents})"

    def test_shop_home_has_promoted_section(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/shop/home", timeout=20)
        assert r.status_code == 200, r.text
        sections = r.json().get("sections", [])
        promoted = next((s for s in sections if s.get("key") == "promoted"), None)
        assert promoted is not None, f"no 'promoted' section: {[s.get('key') for s in sections]}"
        assert promoted.get("title") == "Promoted near you"
        assert len(promoted.get("items", [])) > 0
        # Merchant biz should appear as it has both active promotion + active bid
        ids = {it["business_id"] for it in promoted["items"]}
        assert MERCHANT_BIZ_ID in ids or "biz_sample_ambreens" in ids
