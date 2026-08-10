"""Iter 55 — Super Marketplace Phase A1 backend tests.

Covers:
- Consumer public /api/shop/* endpoints
- Merchant /api/merchant/marketplace/* (auth, validations, preview, fund, auto-reload)
- Admin /api/admin/marketplace/* (guarded, CRUD, approve/reject, dashboard)
- Economics resolver specificity: merchant > category > market > global
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

assert BASE_URL, "REACT_APP_BACKEND_URL must be set"


# ─────────────────────────── fixtures ───────────────────────────
class _NoCookieSession(requests.Session):
    """Session that never persists cookies — each test call is stateless.
    Prevents demo cookies leaking into admin bearer calls."""
    def send(self, request, **kwargs):
        resp = super().send(request, **kwargs)
        self.cookies.clear()
        return resp


@pytest.fixture(scope="module")
def http():
    s = _NoCookieSession()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="module")
def demo_token(http):
    r = http.post(f"{BASE_URL}/api/auth/demo", json={})
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token(db):
    """Insert a session row for admin user directly (no email/password admin login)."""
    u = db.users.find_one({"email": "admin@bigfm.dubai"})
    assert u, "admin@bigfm.dubai user missing"
    assert u.get("role") == "admin", f"user role={u.get('role')}"
    token = "sess_iter55_" + secrets.token_hex(12)
    db.sessions.insert_one({
        "user_id": u["user_id"],
        "token": token,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),
    })
    yield token
    db.sessions.delete_one({"token": token})


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ─────────────────────────── consumer /api/shop ───────────────────────────
class TestShopPublic:
    def test_categories_public_no_auth(self, http):
        r = http.get(f"{BASE_URL}/api/shop/categories")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 9, f"expected >=9 categories, got {len(items)}"
        keys = {c["key"] for c in items}
        for k in ["restaurant", "retail", "beauty", "home_services",
                  "professional", "fitness", "automotive", "events", "other"]:
            assert k in keys, f"missing seeded category {k}"

    def test_shop_home_public(self, http):
        r = http.get(f"{BASE_URL}/api/shop/home")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["headline"] == "SHOP LOCAL. EARN BIGPOINTS."
        assert isinstance(data["categories"], list) and len(data["categories"]) >= 1
        section_keys = {s["key"] for s in data["sections"]}
        for k in ["recommended", "earn_more", "food", "services", "featured"]:
            assert k in section_keys

    def test_shop_businesses_public_approved_only(self, http, db):
        r = http.get(f"{BASE_URL}/api/shop/businesses")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # every returned biz must be status=approved in DB
        for it in items:
            p = db.marketplace_profiles.find_one({"business_id": it["business_id"]})
            assert p and p.get("status") == "approved"

    def test_shop_business_detail_404(self, http):
        r = http.get(f"{BASE_URL}/api/shop/businesses/does_not_exist_xxx")
        assert r.status_code == 404


# ─────────────────────────── auth guards ───────────────────────────
class TestAuthGuards:
    def test_merchant_401_without_token(self, http):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/profile")
        assert r.status_code == 401

    def test_admin_403_for_demo_listener(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/dashboard", headers=demo_headers)
        assert r.status_code == 403, r.text

    def test_admin_401_without_token(self, http):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/dashboard")
        assert r.status_code == 401

    def test_admin_200_with_admin_token(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/dashboard", headers=admin_headers)
        assert r.status_code == 200, r.text


# ─────────────────────────── merchant onboarding validations ───────────────────────────
def _base_onboarding_body(**overrides):
    body = {
        "business_type": "sole_proprietor",
        "legal_name": "Iter55 Merchant LLC",
        "public_name": "Iter55 Café",
        "description": "Best coffee in town",
        "phone": "+9715551234",
        "email": "iter55@example.com",
        "website": "https://iter55.example.com",
        "category": "restaurant",
        "subcategory": None,
        "logo_url": None,
        "cover_urls": [],
        "locations": [{"city": "Dubai", "address": "123 Test St"}],
        "verification": {},
        "sells": ["food"],
        "bigpoints": {"mode": "default", "default_points": 100, "points_per_dollar": 2.0},
        "funding_mode": "auto_deduct",
        "commission_agreed": True,
        "price_parity_certified": True,
    }
    body.update(overrides)
    return body


class TestMerchantOnboardingValidations:
    def test_bad_category(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                      json=_base_onboarding_body(category="not_a_real_cat"),
                      headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "bad_category"

    def test_commission_agreement_required(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                      json=_base_onboarding_body(commission_agreed=False),
                      headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "commission_agreement_required"

    def test_bigpoints_required(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                      json=_base_onboarding_body(bigpoints={"mode": "default",
                                                            "default_points": 0,
                                                            "points_per_dollar": 2.0}),
                      headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "bigpoints_required"

    def test_below_min_bigpoints(self, http, demo_headers):
        # restaurant min_bigpoints=50, use 10
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                      json=_base_onboarding_body(bigpoints={"mode": "default",
                                                            "default_points": 10,
                                                            "points_per_dollar": 2.0}),
                      headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "below_min_bigpoints"

    def test_restaurant_price_parity_required(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                      json=_base_onboarding_body(price_parity_certified=False),
                      headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "price_parity_required"


# ─────────────────────────── merchant happy path + bigpoints ───────────────────────────
class TestMerchantHappyPath:
    def test_onboarding_creates_pending_profile(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                      json=_base_onboarding_body(),
                      headers=demo_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["business_id"].startswith("biz_")
        assert data["profile"]["status"] == "pending"
        assert data["profile"]["category"] == "restaurant"

    def test_get_profile(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/profile", headers=demo_headers)
        assert r.status_code == 200
        p = r.json()["profile"]
        assert p is not None
        assert p["status"] in ("pending", "approved")

    def test_get_bp_settings(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/bigpoints/settings",
                     headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["bigpoints"]["mode"] == "default"
        # default cost should be 3.0 cents per point
        assert d["cost_per_point_cents"] == 3.0

    def test_patch_bp_settings_below_min(self, http, demo_headers):
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/bigpoints/settings",
                       json={"mode": "default", "default_points": 10,
                             "points_per_dollar": 2.0},
                       headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "below_min_bigpoints"

    def test_patch_bp_settings_success(self, http, demo_headers):
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/bigpoints/settings",
                       json={"mode": "default", "default_points": 100,
                             "points_per_dollar": 2.0},
                       headers=demo_headers)
        assert r.status_code == 200
        assert r.json()["cost_per_point_cents"] == 3.0

    def test_preview_by_points(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                      json={"points": 100}, headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["points"] == 100
        assert d["cost_per_point_cents"] == 3.0
        assert d["estimated_cost_cents"] == 300  # 100 * 3.0
        assert d["estimated_cost_display"] == "$3.00"

    def test_preview_by_order_value(self, http, demo_headers):
        # $50 order @ 2 pts/$ = 100 pts => $3.00
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                      json={"order_value_cents": 5000}, headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["points"] == 100
        assert d["estimated_cost_cents"] == 300

    def test_account(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/bigpoints/account",
                     headers=demo_headers)
        assert r.status_code == 200
        d = r.json()
        assert "account" in d
        assert d["account"]["business_id"].startswith("biz_")
        assert "balance_points" in d["account"]

    def test_fund_creates_stripe_session(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/fund",
                      json={"points": 10000, "origin_url": "https://example.com"},
                      headers=demo_headers)
        # If stripe unconfigured returns 503, allow-skip; else expect 200
        if r.status_code == 503:
            pytest.skip("Stripe unconfigured in this env")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["amount_cents"] == 30000  # 10000 * 3.0
        assert d["checkout_url"].startswith("http")
        assert d["session_id"].startswith("cs_")

    def test_auto_reload_patch(self, http, demo_headers):
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/bigpoints/auto-reload",
                       json={"funding_mode": "prepaid", "enabled": True,
                             "threshold": 3000, "amount": 20000},
                       headers=demo_headers)
        assert r.status_code == 200
        # confirm persisted
        r2 = http.get(f"{BASE_URL}/api/merchant/marketplace/bigpoints/account",
                      headers=demo_headers)
        acct = r2.json()["account"]
        assert acct["auto_reload"]["enabled"] is True
        assert acct["auto_reload"]["threshold"] == 3000
        assert acct["auto_reload"]["amount"] == 20000
        assert acct["funding_mode"] == "prepaid"


# ─────────────────────────── admin endpoints ───────────────────────────
class TestAdminEndpoints:
    def test_dashboard(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/dashboard", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["categories"] >= 9
        assert d["example_point_cost_cents"] == 3.0
        assert d["example_commission"]["commission_pct"] == 15.0  # restaurant seed

    def test_list_rates(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/bigpoint-rates", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["default_cost_per_point_cents"] == 3.0
        assert any(rate["scope"] == "global" for rate in d["items"])

    def test_list_categories(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/categories", headers=admin_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 9

    def test_list_commission_rules(self, http, admin_headers):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/commission-rules",
                     headers=admin_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        # 9 seeded categories + 1 global fallback = 10+
        assert len(items) >= 10

    def test_list_pending_businesses(self, http, admin_headers, db):
        r = http.get(f"{BASE_URL}/api/admin/marketplace/businesses?status=pending",
                     headers=admin_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        for it in items:
            assert it["status"] == "pending"


# ─────────────────────────── economics resolver ───────────────────────────
class TestEconomicsResolvers:
    """Test resolver specificity: merchant > category > market > global."""

    def test_resolver_priority_merchant_over_category_over_market_over_global(
            self, http, admin_headers, db):
        # Get the demo user's business_id
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/profile",
                     headers={"Authorization": admin_headers["Authorization"]})
        # (admin doesn't have a profile — pull via mongo instead)
        u = db.users.find_one({"email": "demo@bigfm.dubai"})
        p = db.marketplace_profiles.find_one({"owner_user_id": u["user_id"]})
        assert p, "demo merchant profile missing (should exist from earlier tests)"
        biz_id = p["business_id"]
        market = p.get("market") or "Dubai"
        category = p.get("category")

        # Seed 3 rates: market, category, merchant
        rate_ids = []
        for scope, extra, cost in [
            ("market", {"market": market}, 2.5),
            ("category", {"category": category}, 2.0),
            ("merchant", {"merchant_id": biz_id}, 1.5),
        ]:
            body = {"scope": scope, "cost_per_point_cents": cost,
                    "market": None, "category": None, "merchant_id": None,
                    "active": True, **extra}
            rr = http.post(f"{BASE_URL}/api/admin/marketplace/bigpoint-rates",
                           json=body, headers=admin_headers)
            assert rr.status_code == 200, rr.text
            rate_ids.append(rr.json()["rate_id"])

        try:
            # With merchant rate present -> preview should use 1.5
            demo_r = http.post(f"{BASE_URL}/api/auth/demo", json={})
            demo_tok = demo_r.json().get("session_token") or demo_r.json().get("token")
            dh = {"Authorization": f"Bearer {demo_tok}", "Content-Type": "application/json"}
            prv = http.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                            json={"points": 100}, headers=dh)
            assert prv.status_code == 200, prv.text
            assert prv.json()["cost_per_point_cents"] == 1.5, \
                f"merchant scope should win: got {prv.json()}"

            # Deactivate merchant → category (2.0) should win
            db.bigpoint_rates.update_one(
                {"rate_id": rate_ids[2]}, {"$set": {"active": False}})
            prv = http.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                            json={"points": 100}, headers=dh)
            assert prv.json()["cost_per_point_cents"] == 2.0, \
                f"category should now win: got {prv.json()}"

            # Deactivate category → market (2.5) should win
            db.bigpoint_rates.update_one(
                {"rate_id": rate_ids[1]}, {"$set": {"active": False}})
            prv = http.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                            json={"points": 100}, headers=dh)
            assert prv.json()["cost_per_point_cents"] == 2.5, \
                f"market should now win: got {prv.json()}"

            # Deactivate market → global default (3.0)
            db.bigpoint_rates.update_one(
                {"rate_id": rate_ids[0]}, {"$set": {"active": False}})
            prv = http.post(f"{BASE_URL}/api/merchant/marketplace/bigpoints/preview",
                            json={"points": 100}, headers=dh)
            assert prv.json()["cost_per_point_cents"] == 3.0, \
                f"global should now win: got {prv.json()}"
        finally:
            # cleanup
            for rid in rate_ids:
                db.bigpoint_rates.delete_one({"rate_id": rid})


# ─────────────────────────── approval flow ───────────────────────────
class TestApprovalFlow:
    def test_approve_flips_status_and_appears_in_shop(self, http, admin_headers, db, demo_headers):
        # Ensure demo has a pending profile
        prof_r = http.get(f"{BASE_URL}/api/merchant/marketplace/profile", headers=demo_headers)
        prof = prof_r.json().get("profile")
        assert prof is not None
        biz_id = prof["business_id"]

        # Approve
        r = http.post(f"{BASE_URL}/api/admin/marketplace/businesses/{biz_id}/approve",
                      headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

        # Verify profile flipped
        p = db.marketplace_profiles.find_one({"business_id": biz_id})
        assert p["status"] == "approved"
        b = db.businesses.find_one({"business_id": biz_id})
        assert b["active"] is True and b["verified"] is True

        # Should now appear in public shop listings
        r2 = http.get(f"{BASE_URL}/api/shop/businesses")
        ids = {it["business_id"] for it in r2.json()["items"]}
        assert biz_id in ids

        # And accessible via detail endpoint
        r3 = http.get(f"{BASE_URL}/api/shop/businesses/{biz_id}")
        assert r3.status_code == 200
        assert r3.json()["business"]["business_id"] == biz_id

    def test_reject_unknown_business_404(self, http, admin_headers):
        r = http.post(f"{BASE_URL}/api/admin/marketplace/businesses/biz_missing/reject",
                      json={"reason": "test"}, headers=admin_headers)
        assert r.status_code == 404


# ─────────────────────────── admin CRUD ───────────────────────────
class TestAdminCRUD:
    def test_create_and_update_rate(self, http, admin_headers, db):
        body = {"scope": "market", "cost_per_point_cents": 4.5,
                "market": "TEST_market_iter55", "category": None,
                "merchant_id": None, "active": True}
        r = http.post(f"{BASE_URL}/api/admin/marketplace/bigpoint-rates",
                      json=body, headers=admin_headers)
        assert r.status_code == 200
        rid = r.json()["rate_id"]
        try:
            body["cost_per_point_cents"] = 5.5
            r2 = http.patch(f"{BASE_URL}/api/admin/marketplace/bigpoint-rates/{rid}",
                            json=body, headers=admin_headers)
            assert r2.status_code == 200
            got = db.bigpoint_rates.find_one({"rate_id": rid})
            assert got["cost_per_point_cents"] == 5.5
        finally:
            db.bigpoint_rates.delete_one({"rate_id": rid})

    def test_create_and_update_category(self, http, admin_headers, db):
        key = "TEST_cat_iter55"
        db.marketplace_categories.delete_one({"key": key})
        body = {"key": key, "name": "Test Cat", "icon": "storefront",
                "product_enabled": True, "commission_pct": 20.0,
                "min_bigpoints": 25, "requires_approval": True, "active": True}
        try:
            r = http.post(f"{BASE_URL}/api/admin/marketplace/categories",
                          json=body, headers=admin_headers)
            assert r.status_code == 200, r.text
            # duplicate create -> 400
            r2 = http.post(f"{BASE_URL}/api/admin/marketplace/categories",
                           json=body, headers=admin_headers)
            assert r2.status_code == 400
            # patch
            body["name"] = "Test Cat Updated"
            r3 = http.patch(f"{BASE_URL}/api/admin/marketplace/categories/{key}",
                            json=body, headers=admin_headers)
            assert r3.status_code == 200
        finally:
            db.marketplace_categories.delete_one({"key": key})

    def test_create_and_update_commission_rule(self, http, admin_headers, db):
        body = {"scope": "market", "commission_pct": 8.5, "fixed_fee_cents": 0,
                "min_fee_cents": 0, "max_fee_cents": None,
                "market": "TEST_mkt_iter55", "category": None,
                "merchant_id": None, "active": True}
        r = http.post(f"{BASE_URL}/api/admin/marketplace/commission-rules",
                      json=body, headers=admin_headers)
        assert r.status_code == 200
        rid = r.json()["rule_id"]
        try:
            body["commission_pct"] = 9.0
            r2 = http.patch(f"{BASE_URL}/api/admin/marketplace/commission-rules/{rid}",
                            json=body, headers=admin_headers)
            assert r2.status_code == 200
            got = db.marketplace_commission_rules.find_one({"rule_id": rid})
            assert got["commission_pct"] == 9.0
        finally:
            db.marketplace_commission_rules.delete_one({"rule_id": rid})
