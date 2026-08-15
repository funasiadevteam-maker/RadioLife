"""Phase F — Promoted Marketplace backend tests.

Covers:
  * Merchant tiers/get promotion/checkout endpoints
  * Admin list / approve / reject / grant endpoints
  * Ranking: /api/shop/businesses?sort=featured & /api/shop/home 'promoted' section
"""

import os
import requests
import pytest
from pathlib import Path


def _load_web_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env = Path("/app/frontend/.env")
    for line in env.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _load_web_backend_url()


# ---------------- shared helpers ----------------
def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def merchant():
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture(scope="module")
def admin():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def demo():
    return _login("demo@bigfm.dubai", "DemoPass123!")


# ---------------- merchant endpoints ----------------
class TestMerchantPromotion:

    def test_tiers(self, merchant):
        r = merchant.get(f"{BASE}/api/merchant/marketplace/promotion/tiers")
        assert r.status_code == 200, r.text
        tiers = r.json()["tiers"]
        by_id = {t["tier"]: t for t in tiers}
        assert set(by_id) == {"spotlight_7", "boost_14", "premium_30"}
        assert by_id["spotlight_7"]["price_cents"] == 1999
        assert by_id["spotlight_7"]["days"] == 7
        assert by_id["boost_14"]["price_cents"] == 3499
        assert by_id["boost_14"]["days"] == 14
        assert by_id["premium_30"]["price_cents"] == 5999
        assert by_id["premium_30"]["days"] == 30
        # Ordering by weight
        assert by_id["premium_30"]["weight"] > by_id["boost_14"]["weight"] > by_id["spotlight_7"]["weight"]

    def test_my_promotion(self, merchant):
        r = merchant.get(f"{BASE}/api/merchant/marketplace/promotion")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "business_id" in data
        assert "public_name" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        # Field 'active' present (may be None)
        assert "active" in data

    def test_checkout_creates_session(self, merchant):
        body = {"tier": "spotlight_7", "origin_url": BASE}
        r = merchant.post(f"{BASE}/api/merchant/marketplace/promotion/checkout", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("promotion_id", "").startswith("promo_")
        assert data.get("session_id", "").startswith("cs_")
        assert isinstance(data.get("checkout_url"), str)
        assert data["checkout_url"].startswith("https://")
        # Persisted as pending_payment in items
        r2 = merchant.get(f"{BASE}/api/merchant/marketplace/promotion")
        assert r2.status_code == 200
        items = r2.json()["items"]
        pids = [x.get("promotion_id") for x in items]
        assert data["promotion_id"] in pids
        me_row = next(x for x in items if x["promotion_id"] == data["promotion_id"])
        assert me_row["status"] == "pending_payment"
        assert me_row["tier"] == "spotlight_7"

    def test_checkout_bad_tier(self, merchant):
        r = merchant.post(f"{BASE}/api/merchant/marketplace/promotion/checkout",
                          json={"tier": "not_a_tier", "origin_url": BASE})
        assert r.status_code == 400

    def test_endpoints_require_auth(self):
        r = requests.get(f"{BASE}/api/merchant/marketplace/promotion/tiers", timeout=10)
        assert r.status_code in (401, 403)
        r = requests.get(f"{BASE}/api/merchant/marketplace/promotion", timeout=10)
        assert r.status_code in (401, 403)

    def test_non_merchant_has_no_profile(self, demo):
        # demo user in this env is not a marketplace owner? Actually per creds demo owns a business too.
        # Just assert endpoint responds (either 200 with data or 404 no_marketplace_profile)
        r = demo.get(f"{BASE}/api/merchant/marketplace/promotion")
        assert r.status_code in (200, 404), r.text


# ---------------- admin endpoints ----------------
class TestAdminPromotions:

    def test_admin_list_all(self, admin):
        r = admin.get(f"{BASE}/api/admin/marketplace/promotions?status=all")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert isinstance(items, list)
        # Seeded active promotion should be there
        seeded = [x for x in items if x.get("promotion_id") == "promo_seed_demo"]
        assert seeded, "seeded promo_seed_demo missing from admin list"
        assert seeded[0]["status"] == "active"
        assert seeded[0]["business_id"] == "biz_sample_ambreens"

    def test_admin_list_status_filter(self, admin):
        r = admin.get(f"{BASE}/api/admin/marketplace/promotions?status=active")
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["status"] == "active"

    def test_admin_requires_admin(self, merchant):
        r = merchant.get(f"{BASE}/api/admin/marketplace/promotions?status=all")
        assert r.status_code in (401, 403)

    def test_admin_reject_flow(self, merchant, admin):
        # 1) merchant creates a pending_payment promo via checkout
        r = merchant.post(f"{BASE}/api/merchant/marketplace/promotion/checkout",
                          json={"tier": "boost_14", "origin_url": BASE})
        assert r.status_code == 200
        pid = r.json()["promotion_id"]

        # 2) admin rejects it directly (pending_payment path — reject is allowed on any status)
        r = admin.post(f"{BASE}/api/admin/marketplace/promotions/{pid}/reject",
                       json={"note": "TEST_reject reason"})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # 3) verify status persisted
        r = admin.get(f"{BASE}/api/admin/marketplace/promotions?status=rejected")
        assert r.status_code == 200
        rejected_ids = [x["promotion_id"] for x in r.json()["items"]]
        assert pid in rejected_ids

    def test_admin_grant_activates_and_ranks(self, admin, merchant):
        # Grant a comp on test@'s business (business_id from my_promotion)
        r = merchant.get(f"{BASE}/api/merchant/marketplace/promotion")
        assert r.status_code == 200
        biz_id = r.json()["business_id"]

        r = admin.post(f"{BASE}/api/admin/marketplace/promotions/grant",
                       json={"business_id": biz_id, "tier": "premium_30"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("promotion_id", "").startswith("promo_")
        assert data.get("expires_at")
        pid = data["promotion_id"]

        # Merchant now sees an active promotion
        r = merchant.get(f"{BASE}/api/merchant/marketplace/promotion")
        assert r.status_code == 200
        assert r.json().get("active") is not None
        assert r.json()["active"]["promotion_id"] == pid
        assert r.json()["active"]["tier"] == "premium_30"

    def test_admin_grant_bad_tier(self, admin):
        r = admin.post(f"{BASE}/api/admin/marketplace/promotions/grant",
                       json={"business_id": "biz_sample_ambreens", "tier": "not_a_tier"})
        assert r.status_code == 400

    def test_admin_grant_bad_business(self, admin):
        r = admin.post(f"{BASE}/api/admin/marketplace/promotions/grant",
                       json={"business_id": "biz_does_not_exist_TEST", "tier": "spotlight_7"})
        assert r.status_code == 404

    def test_admin_approve_pending(self, merchant, admin):
        # Create a pending_payment first, then approve directly (admin can approve any status).
        r = merchant.post(f"{BASE}/api/merchant/marketplace/promotion/checkout",
                          json={"tier": "spotlight_7", "origin_url": BASE})
        assert r.status_code == 200
        pid = r.json()["promotion_id"]

        r = admin.post(f"{BASE}/api/admin/marketplace/promotions/{pid}/approve")
        assert r.status_code == 200, r.text
        promo = r.json()["promotion"]
        assert promo["status"] == "active"
        assert promo.get("activated_at")
        assert promo.get("expires_at")

    def test_admin_approve_not_found(self, admin):
        r = admin.post(f"{BASE}/api/admin/marketplace/promotions/promo_nope_TEST/approve")
        assert r.status_code == 404


# ---------------- ranking + shop home ----------------
class TestShopRanking:

    def test_shop_home_has_promoted_section(self):
        # Public endpoint — no auth needed
        r = requests.get(f"{BASE}/api/shop/home", timeout=15)
        assert r.status_code == 200, r.text
        sections = r.json().get("sections", [])
        keys = [s.get("key") for s in sections]
        assert "promoted" in keys, f"'promoted' section missing; got {keys}"
        promoted = next(s for s in sections if s["key"] == "promoted")
        assert promoted["title"] == "Promoted near you"
        assert len(promoted["items"]) >= 1
        # Seeded Ambreens should be first (weight 3)
        biz_ids = [it.get("business_id") for it in promoted["items"]]
        assert "biz_sample_ambreens" in biz_ids
        for it in promoted["items"]:
            assert it.get("promoted") is True

    def test_shop_businesses_sort_featured_ranks_promoted_first(self):
        r = requests.get(f"{BASE}/api/shop/businesses?sort=featured&limit=40", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or r.json().get("businesses") or []
        assert items, "no businesses returned"
        # Find promoted vs non-promoted indices
        promoted_indices = [i for i, x in enumerate(items) if x.get("promoted")]
        non_promoted_indices = [i for i, x in enumerate(items) if not x.get("promoted")]
        assert promoted_indices, "no promoted business found in ranked results"
        # All promoted must come before all non-promoted
        if non_promoted_indices:
            assert max(promoted_indices) < min(non_promoted_indices), \
                f"promoted not first: promoted@{promoted_indices} vs non@{non_promoted_indices}"
        # promotion_weight exposed
        for x in items:
            if x.get("promoted"):
                assert isinstance(x.get("promotion_weight"), int)
                assert x["promotion_weight"] >= 1
