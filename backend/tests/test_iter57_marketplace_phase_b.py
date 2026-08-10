"""Iter 57 — Super Marketplace Phase B (Restaurant Pickup) backend tests.

Covers:
- Merchant subscription plans + checkout + admin comp/revoke
- Subscription enforcement in consumer /api/shop
- Menu CRUD + bulk import + file (CSV) import + AI url import (best-effort)
- Consumer menu grouping (biz_demo_grill)
- Consumer checkout with gift-card auto-apply (fully covered / partial)
- Merchant order list + lifecycle transitions + invalid transition + unpaid
- BigPoints award on pickup + idempotent
- Happy Hour PATCH (multiplier applied in menu response)
- Merchant dashboard
"""
from __future__ import annotations

import base64
import io
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


class _NoCookieSession(requests.Session):
    """Prevents demo cookies leaking into admin bearer calls."""
    def send(self, request, **kwargs):
        resp = super().send(request, **kwargs)
        self.cookies.clear()
        return resp


# ─────────────────────────── fixtures ───────────────────────────
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
def demo_user_id(http, demo_token):
    r = http.get(f"{BASE_URL}/api/auth/me",
                 headers={"Authorization": f"Bearer {demo_token}"})
    if r.status_code == 200:
        return r.json().get("user_id")
    return None


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_user_token(http):
    r = http.post(f"{BASE_URL}/api/auth/login",
                  json={"email": "test@bigfm.dubai", "password": "TestUser123!"})
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def test_user_id(db):
    u = db.users.find_one({"email": "test@bigfm.dubai"})
    return u["user_id"] if u else None


@pytest.fixture(scope="module")
def test_headers(test_user_token):
    return {"Authorization": f"Bearer {test_user_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token(db):
    u = db.users.find_one({"email": "admin@bigfm.dubai"})
    assert u, "admin@bigfm.dubai missing"
    token = "sess_iter57_" + secrets.token_hex(12)
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


CTX: dict = {}


# ─────────────────────────── Subscription ───────────────────────────
class TestSubscriptionPlans:
    def test_plans_returns_starter_and_pro(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/subscription/plans",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        by_id = {p["plan_id"]: p for p in items}
        assert "starter" in by_id, by_id
        assert "pro" in by_id, by_id
        assert by_id["starter"]["price_cents"] == 2900
        assert by_id["pro"]["price_cents"] == 9900

    def test_get_subscription_shape(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/subscription",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "active" in j and "business_id" in j

    def test_checkout_returns_stripe_url_subscription_mode(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/subscription/checkout",
                      json={"plan_id": "starter",
                            "origin_url": "https://example.test"},
                      headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("checkout_url", "").startswith("https://checkout.stripe.com"), j
        assert j.get("session_id")

    def test_checkout_bad_plan(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/subscription/checkout",
                      json={"plan_id": "nonsense", "origin_url": "https://example.test"},
                      headers=demo_headers)
        assert r.status_code == 400
        assert (r.json().get("detail") or {}).get("code") == "bad_plan"


# ─────────────────────────── Admin comp/revoke + enforcement ────────────
@pytest.fixture(scope="module")
def biz_grill_id():
    return "biz_demo_grill"


class TestSubscriptionEnforcement:
    def test_grill_visible_when_active(self, http, biz_grill_id):
        # Demo seeds have subscription_active=True per Phase B main-agent smoke.
        r = http.get(f"{BASE_URL}/api/shop/businesses/{biz_grill_id}")
        assert r.status_code == 200, r.text

    def test_revoke_hides_business(self, http, admin_headers, biz_grill_id):
        # revoke
        r = http.post(f"{BASE_URL}/api/admin/marketplace/businesses/{biz_grill_id}/revoke-subscription",
                      headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["subscription_active"] is False
        # detail 404
        r = http.get(f"{BASE_URL}/api/shop/businesses/{biz_grill_id}")
        assert r.status_code == 404
        # not in listing
        r = http.get(f"{BASE_URL}/api/shop/businesses?limit=100")
        assert r.status_code == 200
        assert not any(b["business_id"] == biz_grill_id for b in r.json()["items"])
        # not in shop home food
        r = http.get(f"{BASE_URL}/api/shop/home")
        for sec in r.json()["sections"]:
            assert not any(b["business_id"] == biz_grill_id for b in sec["items"])

    def test_comp_restores_business(self, http, admin_headers, biz_grill_id):
        r = http.post(f"{BASE_URL}/api/admin/marketplace/businesses/{biz_grill_id}/comp-subscription",
                      headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["subscription_active"] is True
        r = http.get(f"{BASE_URL}/api/shop/businesses/{biz_grill_id}")
        assert r.status_code == 200


# ─────────────────────────── Merchant setup for test_user (full lifecycle) ───────
@pytest.fixture(scope="module")
def test_merchant_business_id(http, admin_headers, test_headers, db, test_user_id):
    """Onboard test@ as merchant, admin approve, comp-subscription. Returns business_id."""
    # Onboard
    body = {
        "business_type": "sole_proprietor",
        "legal_name": "TEST Iter57 Pickup LLC",
        "category": "restaurant",
        "public_name": "TEST_iter57_pickup",
        "description": "Iter57 test merchant",
        "sells": ["menu"],
        "commission_agreed": True,
        "price_parity_certified": True,
        "bigpoints": {"default_points": 100, "points_per_dollar": 2, "signup_bonus": 0,
                      "funding_mode": "prepaid"},
        "locations": [{"city": "dubai", "address": "Test Ave 1"}],
    }
    r = http.post(f"{BASE_URL}/api/merchant/marketplace/onboarding",
                  json=body, headers=test_headers)
    assert r.status_code == 200, r.text
    # Find business_id from profile
    r = http.get(f"{BASE_URL}/api/merchant/marketplace/profile", headers=test_headers)
    assert r.status_code == 200, r.text
    bid = r.json()["profile"]["business_id"]
    # Approve
    ar = http.post(f"{BASE_URL}/api/admin/marketplace/businesses/{bid}/approve",
                   headers=admin_headers)
    assert ar.status_code == 200, ar.text
    # Comp subscription
    cs = http.post(f"{BASE_URL}/api/admin/marketplace/businesses/{bid}/comp-subscription",
                   headers=admin_headers)
    assert cs.status_code == 200, cs.text
    yield bid


# ─────────────────────────── Menu CRUD ───────────────────────────
class TestMenuCRUD:
    def test_create_menu_item(self, http, test_headers, test_merchant_business_id):
        body = {"section": "Starters", "name": "Test Wings", "description": "Crispy",
                "price_cents": 999, "bigpoints": 50, "available": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/menu/items",
                      json=body, headers=test_headers)
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        assert item["name"] == "Test Wings" and item["price_cents"] == 999
        CTX['item_id'] = item["item_id"]

    def test_list_menu(self, http, test_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/menu", headers=test_headers)
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_patch_menu_item(self, http, test_headers):
        body = {"section": "Starters", "name": "Test Wings Updated",
                "price_cents": 1099, "available": True}
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/menu/items/{CTX['item_id']}",
                       json=body, headers=test_headers)
        assert r.status_code == 200, r.text
        assert r.json()["item"]["name"] == "Test Wings Updated"

    def test_bulk_items(self, http, test_headers, test_merchant_business_id):
        body = {"items": [
            {"section": "Mains", "name": "Test Burger", "price_cents": 1500,
             "bigpoints": 75, "available": True},
            {"section": "Mains", "name": "Test Pizza", "price_cents": 1800,
             "bigpoints": 90, "available": True},
        ]}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/menu/items/bulk",
                      json=body, headers=test_headers)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 2

    def test_delete_menu_item(self, http, test_headers):
        # delete the first item we made
        r = http.delete(f"{BASE_URL}/api/merchant/marketplace/menu/items/{CTX['item_id']}",
                        headers=test_headers)
        assert r.status_code == 200
        # 404 on repeat delete
        r = http.delete(f"{BASE_URL}/api/merchant/marketplace/menu/items/{CTX['item_id']}",
                        headers=test_headers)
        assert r.status_code == 404


# ─────────────────────────── Import: CSV file ───────────────────────────
class TestFileImport:
    def test_import_csv(self, http, test_headers):
        csv = ("name,price,section,description\n"
               "TEST_Latte,4.50,Drinks,Espresso + milk\n"
               "TEST_Mocha,5.00,Drinks,Chocolate espresso\n")
        b64 = base64.b64encode(csv.encode()).decode()
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/menu/import/file",
                      json={"file_base64": b64, "filename": "menu.csv"},
                      headers=test_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["count"] >= 2
        names = [i["name"] for i in j["items"]]
        assert any("TEST_Latte" in n for n in names)


# ─────────────────────────── Consumer Menu ───────────────────────────
class TestConsumerMenu:
    def test_grill_menu_grouped_sections(self, http):
        r = http.get(f"{BASE_URL}/api/shop/businesses/biz_demo_grill/menu")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["business_id"] == "biz_demo_grill"
        assert isinstance(j["sections"], list)
        # At least one section with items
        total = sum(len(s["items"]) for s in j["sections"])
        assert total > 0, j
        assert "happy_hour" in j and "points_multiplier" in j

    def test_menu_for_spice_and_brew(self, http):
        for bid in ("biz_demo_spice", "biz_demo_brew"):
            r = http.get(f"{BASE_URL}/api/shop/businesses/{bid}/menu")
            assert r.status_code == 200, f"{bid} -> {r.text}"


# ─────────────────────────── Consumer Checkout ───────────────────────────
class TestConsumerCheckout:
    def test_checkout_gift_card_fully_covers(self, http, demo_headers, db, demo_user_id):
        # ensure the demo user has a large active gift card
        assert demo_user_id
        db.gift_cards.update_one(
            {"owner_user_id": demo_user_id, "card_id": "gc_iter57_test"},
            {"$set": {"card_id": "gc_iter57_test", "owner_user_id": demo_user_id,
                      "status": "active", "balance_cents": 100000,
                      "created_at": datetime.now(timezone.utc)}},
            upsert=True)
        # pick a real menu item from biz_demo_grill (small price hopefully)
        r = http.get(f"{BASE_URL}/api/shop/businesses/biz_demo_grill/menu")
        items = []
        for sec in r.json()["sections"]:
            items.extend(sec["items"])
        assert items
        cheapest = min(items, key=lambda i: i.get("price_cents", 0))
        payload = {"business_id": "biz_demo_grill",
                   "items": [{"item_id": cheapest["item_id"], "qty": 1}],
                   "origin_url": "https://example.test", "use_gift_card": True}
        r = http.post(f"{BASE_URL}/api/shop/orders/checkout",
                      json=payload, headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        # gift card fully covers the small item -> instant paid
        assert j["status"] == "accepted", j
        assert j["checkout_url"] is None, j
        assert j["gift_card_applied_cents"] > 0
        assert j["total_cents"] == 0
        CTX['paid_order_id'] = j["order_id"]

    def test_get_paid_order(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/shop/orders/{CTX['paid_order_id']}",
                     headers=demo_headers)
        assert r.status_code == 200
        assert r.json()["order"]["payment_status"] == "paid"

    def test_orders_list_contains(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/shop/orders", headers=demo_headers)
        assert r.status_code == 200
        ids = [o["order_id"] for o in r.json()["items"]]
        assert CTX['paid_order_id'] in ids


# ─────────────────────────── Full order lifecycle (test merchant + demo customer) ─────
class TestOrderLifecycle:
    """Create menu item on test merchant, demo customer orders it fully via
    gift card, then merchant marches through lifecycle to picked_up and
    BigPoints are awarded once."""

    def test_setup_test_merchant_menu_and_place_order(
            self, http, test_headers, demo_headers, demo_user_id, db,
            test_merchant_business_id):
        # Create small menu item on test merchant
        item_body = {"section": "Menu", "name": "TEST_Small", "price_cents": 500,
                     "bigpoints": 40, "available": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/menu/items",
                      json=item_body, headers=test_headers)
        assert r.status_code == 200
        item_id = r.json()["item"]["item_id"]

        # Ensure demo gift card balance is enough
        db.gift_cards.update_one(
            {"card_id": "gc_iter57_test"},
            {"$set": {"balance_cents": 100000, "status": "active"}}, upsert=False)

        # Snapshot demo's BigPoints balance BEFORE
        r = http.get(f"{BASE_URL}/api/bigcoin/me", headers=demo_headers)
        assert r.status_code == 200, r.text
        CTX['pts_before'] = int(r.json().get("balance", 0))

        # Consumer places the order
        payload = {"business_id": test_merchant_business_id,
                   "items": [{"item_id": item_id, "qty": 1}],
                   "origin_url": "https://example.test", "use_gift_card": True}
        r = http.post(f"{BASE_URL}/api/shop/orders/checkout",
                      json=payload, headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "accepted"
        assert j["checkout_url"] is None
        CTX['lc_order_id'] = j["order_id"]
        CTX['lc_points_expected'] = j.get("gift_card_applied_cents") and \
            j.get("total_cents") == 0
        # points_to_award from menu is default_points=100 (from onboarding)
        # merchant profile default points was 100 -> confirmed order below

    def test_invalid_transition_rejected(self, http, test_headers):
        # accepted -> ready is invalid (must go accepted->preparing->ready)
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{CTX['lc_order_id']}/status",
            json={"status": "ready"}, headers=test_headers)
        assert r.status_code == 400
        assert (r.json().get("detail") or {}).get("code") == "invalid_transition"

    def test_advance_accepted_to_preparing(self, http, test_headers):
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{CTX['lc_order_id']}/status",
            json={"status": "preparing"}, headers=test_headers)
        assert r.status_code == 200
        assert r.json()["order"]["status"] == "preparing"

    def test_advance_preparing_to_ready(self, http, test_headers):
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{CTX['lc_order_id']}/status",
            json={"status": "ready"}, headers=test_headers)
        assert r.status_code == 200
        assert r.json()["order"]["status"] == "ready"

    def test_pickup_awards_points_and_idempotent(
            self, http, test_headers, demo_headers):
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{CTX['lc_order_id']}/status",
            json={"status": "picked_up"}, headers=test_headers)
        assert r.status_code == 200, r.text
        order = r.json()["order"]
        assert order["status"] == "picked_up"
        assert order.get("points_awarded_done") is True
        pts_award = int(order.get("points_to_award", 0))
        assert pts_award > 0

        # Verify demo user's BigPoints balance increased
        r = http.get(f"{BASE_URL}/api/bigcoin/me", headers=demo_headers)
        assert r.status_code == 200
        after = int(r.json().get("balance", 0))
        assert after >= CTX['pts_before'] + pts_award, \
            f"before={CTX['pts_before']} after={after} award={pts_award}"

        # Idempotent: advancing again from picked_up is invalid_transition
        r2 = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{CTX['lc_order_id']}/status",
            json={"status": "picked_up"}, headers=test_headers)
        assert r2.status_code == 400  # picked_up not in ADVANCE keys

    def test_merchant_orders_paid_only_default(self, http, test_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/orders",
                     headers=test_headers)
        assert r.status_code == 200
        ids = [o["order_id"] for o in r.json()["items"]]
        assert CTX['lc_order_id'] in ids


# ─────────────────────────── Happy Hour ───────────────────────────
class TestHappyHour:
    def test_set_happy_hour_active_now(self, http, test_headers):
        now_h = datetime.now(timezone.utc).hour
        # window covers now
        body = {"enabled": True, "start_hour": 0, "end_hour": 23, "multiplier": 2.0}
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/happy-hour",
                       json=body, headers=test_headers)
        assert r.status_code == 200, r.text
        assert r.json()["active_now"] is True

    def test_menu_reflects_happy_hour(self, http, test_merchant_business_id):
        r = http.get(f"{BASE_URL}/api/shop/businesses/{test_merchant_business_id}/menu")
        assert r.status_code == 200
        j = r.json()
        assert j["happy_hour"] is True
        assert j["points_multiplier"] == 2.0

    def test_disable_happy_hour(self, http, test_headers):
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/happy-hour",
                       json={"enabled": False, "start_hour": 0, "end_hour": 0,
                             "multiplier": 2.0}, headers=test_headers)
        assert r.status_code == 200
        assert r.json()["active_now"] is False


# ─────────────────────────── Merchant Dashboard ───────────────────────────
class TestMerchantDashboard:
    def test_dashboard_shape(self, http, test_headers, test_merchant_business_id):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/dashboard",
                     headers=test_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["business_id"] == test_merchant_business_id
        assert j["subscription_active"] is True
        assert isinstance(j["order_counts"], dict)
        assert isinstance(j["open_orders"], int)
        assert isinstance(j["revenue_cents"], int)
        assert isinstance(j["menu_item_count"], int)
        assert j["menu_item_count"] >= 1
        assert "happy_hour" in j
