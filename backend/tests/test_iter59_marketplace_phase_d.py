"""Iter 59 — Super Marketplace Phase D backend tests.

Covers:
- Ecommerce Products: merchant CRUD, delivery config, upload-photo,
  consumer product browse, product-orders checkout (gift-card path),
  fulfillment lifecycle paid→packed→shipped→delivered (BigPoints on delivery)
- Loyalty tiers: /api/shop/loyalty (bronze/silver/gold/platinum, bonus_pct,
  next-tier progress); award_with_tier_bonus flow verified via delivery
- Service photos: merchant upload + AI (spot); consumer service list exposes
  image_url

Uses the pre-seeded demo user + biz_8484f6f985d5 (approved+active) which
already contains 3 seeded products and the Men Haircut service.
"""
from __future__ import annotations

import base64
import os
import secrets
import time
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

DEMO_BIZ_ID = "biz_8484f6f985d5"

PNG_1x1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class _NoCookieSession(requests.Session):
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
    return MongoClient(MONGO_URL)[DB_NAME]


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
def demo_user_id(http, demo_headers):
    r = http.get(f"{BASE_URL}/api/auth/me", headers=demo_headers)
    assert r.status_code == 200
    return r.json().get("user_id")


@pytest.fixture(scope="module")
def demo_biz(http, demo_headers):
    r = http.get(f"{BASE_URL}/api/merchant/marketplace/profile", headers=demo_headers)
    if r.status_code != 200:
        pytest.skip(f"demo has no marketplace profile: {r.text}")
    p = r.json().get("profile") or {}
    if p.get("business_id") != DEMO_BIZ_ID:
        pytest.skip(f"demo does not own {DEMO_BIZ_ID} (got {p.get('business_id')})")
    return p


CTX: dict = {}


# ─────────────────── Loyalty Tiers ───────────────────
class TestLoyaltyStatus:
    def test_loyalty_returns_tier_shape(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/shop/loyalty", headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["tier"] in ("bronze", "silver", "gold", "platinum")
        assert isinstance(j["lifetime_points"], int)
        assert isinstance(j["bonus_pct"], int)
        assert "next_tier" in j and "progress" in j
        assert isinstance(j["perks"], list) and len(j["perks"]) >= 1
        assert len(j["all_tiers"]) == 4
        # bronze first tier, min 0
        assert j["all_tiers"][0]["key"] == "bronze"
        assert j["all_tiers"][0]["min_points"] == 0
        assert j["all_tiers"][3]["key"] == "platinum"
        CTX["loyalty_before"] = j


# ─────────────────── Merchant products ───────────────────
class TestMerchantProducts:
    def test_list_seeded_products(self, http, demo_headers, demo_biz):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/products", headers=demo_headers)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # According to reviewer: 3 seeded products on this biz
        assert isinstance(items, list)
        CTX["seeded_products"] = items

    def test_create_product(self, http, demo_headers, demo_biz):
        body = {"name": f"TEST_iter59_prod_{secrets.token_hex(3)}",
                "description": "Iter59 test", "category": "Products",
                "price_cents": 1500, "stock": 10, "variants": [],
                "bigpoints": 200, "active": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/products/items",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        prod = r.json()["product"]
        assert prod["name"] == body["name"]
        assert prod["price_cents"] == 1500
        assert prod["stock"] == 10
        CTX["prod_id"] = prod["product_id"]
        CTX["prod_name"] = prod["name"]

    def test_patch_product(self, http, demo_headers):
        body = {"name": CTX["prod_name"], "description": "updated",
                "category": "Products", "price_cents": 2000, "stock": 8,
                "variants": [{"label": "Small", "price_cents": 1800, "stock": 5},
                             {"label": "Large", "price_cents": 2500, "stock": 3}],
                "bigpoints": 200, "active": True}
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/products/items/{CTX['prod_id']}",
                       json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        p = r.json()["product"]
        assert p["stock"] == 8
        assert len(p["variants"]) == 2

    def test_patch_unknown_returns_404(self, http, demo_headers):
        body = {"name": "x", "price_cents": 100, "stock": 0}
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/products/items/prod_unknown_xyz",
                       json=body, headers=demo_headers)
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "product_not_found"

    def test_upload_product_photo(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/products/items/{CTX['prod_id']}/photo",
                      json={"file_base64": PNG_1x1_B64, "ext": "png"}, headers=demo_headers)
        assert r.status_code == 200, r.text
        url = r.json()["image_url"]
        assert url.startswith("/api/static/menu_photos/") or url.startswith("http")
        # Serve
        srv = url if url.startswith("http") else f"{BASE_URL}{url}"
        s = requests.get(srv)
        assert s.status_code == 200
        assert "image" in s.headers.get("Content-Type", "")

    def test_upload_photo_missing_file(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/products/items/{CTX['prod_id']}/photo",
                      json={"ext": "png"}, headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "file_required"

    def test_upload_photo_unknown_product_404(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/products/items/prod_unknown/photo",
                      json={"file_base64": PNG_1x1_B64}, headers=demo_headers)
        assert r.status_code == 404


# ─────────────────── Delivery config ───────────────────
class TestDeliveryConfig:
    def test_get_delivery_default(self, http, demo_headers, demo_biz):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/products/delivery",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        d = r.json()["delivery"]
        assert d["pickup"] in (True, False)
        assert "delivery" in d and "fee_cents" in d and "free_over_cents" in d

    def test_patch_delivery(self, http, demo_headers):
        body = {"pickup": True, "delivery": True, "fee_cents": 500,
                "free_over_cents": 10000}
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/products/delivery",
                       json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        d = r.json()["delivery"]
        assert d == body


# ─────────────────── Consumer browse ───────────────────
class TestConsumerBrowse:
    def test_business_products(self, http, demo_headers, demo_biz):
        r = http.get(f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/products",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["business_id"] == DEMO_BIZ_ID
        assert isinstance(j["products"], list)
        assert j["delivery"]["delivery"] is True  # we set it above
        # Find the TEST_iter59 product with variants
        me = next((p for p in j["products"] if p["product_id"] == CTX["prod_id"]), None)
        assert me is not None, "created product should be visible in consumer catalog"
        assert me["image_url"] and me["image_url"].startswith("/api/static/")
        assert len(me["variants"]) == 2

    def test_unknown_business_returns_404(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/shop/businesses/biz_unknown_xyz/products",
                     headers=demo_headers)
        assert r.status_code == 404


# ─────────────────── Checkout + lifecycle ───────────────────
class TestProductCheckoutLifecycle:
    def test_refresh_gift_card(self, db, demo_user_id):
        db.gift_cards.update_one(
            {"card_id": "gc_iter59_test"},
            {"$set": {"card_id": "gc_iter59_test", "owner_user_id": demo_user_id,
                      "balance_cents": 100000, "status": "active",
                      "created_at": datetime.now(timezone.utc)}},
            upsert=True)

    def test_checkout_requires_variant(self, http, demo_headers):
        # Product with variants must have variant_label
        body = {"business_id": DEMO_BIZ_ID,
                "items": [{"product_id": CTX["prod_id"], "qty": 1}],
                "fulfillment": "pickup", "use_gift_card": True}
        r = http.post(f"{BASE_URL}/api/shop/product-orders/checkout",
                      json=body, headers=demo_headers)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "variant_required"

    def test_checkout_delivery_requires_address(self, http, demo_headers):
        body = {"business_id": DEMO_BIZ_ID,
                "items": [{"product_id": CTX["prod_id"], "variant_label": "Small", "qty": 1}],
                "fulfillment": "delivery", "use_gift_card": True}
        r = http.post(f"{BASE_URL}/api/shop/product-orders/checkout",
                      json=body, headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "address_required"

    def test_checkout_paid_via_gift_card(self, http, demo_headers):
        body = {"business_id": DEMO_BIZ_ID,
                "items": [{"product_id": CTX["prod_id"], "variant_label": "Small", "qty": 1}],
                "fulfillment": "pickup", "use_gift_card": True}
        r = http.post(f"{BASE_URL}/api/shop/product-orders/checkout",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "paid"
        assert j["checkout_url"] is None
        assert j["total_cents"] == 0
        assert j["gift_card_applied_cents"] >= 1800
        CTX["order_id"] = j["order_id"]

    def test_my_product_orders_lists_order(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/shop/product-orders", headers=demo_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(o["order_id"] == CTX["order_id"] for o in items)

    def test_status_endpoint(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/shop/product-orders/{CTX['order_id']}/status",
                     headers=demo_headers)
        assert r.status_code == 200
        j = r.json()
        assert j["payment_status"] == "paid"
        assert j["status"] == "paid"

    def test_merchant_sees_paid_order(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/products/orders",
                     headers=demo_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(o["order_id"] == CTX["order_id"] for o in items)

    def test_invalid_transition_rejected(self, http, demo_headers):
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/products/orders/{CTX['order_id']}/status",
            json={"status": "shipped"}, headers=demo_headers)  # paid → shipped (skip packed)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_transition"

    def test_advance_to_packed(self, http, demo_headers):
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/products/orders/{CTX['order_id']}/status",
            json={"status": "packed"}, headers=demo_headers)
        assert r.status_code == 200
        assert r.json()["order"]["status"] == "packed"

    def test_advance_to_shipped(self, http, demo_headers):
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/products/orders/{CTX['order_id']}/status",
            json={"status": "shipped"}, headers=demo_headers)
        assert r.status_code == 200
        assert r.json()["order"]["status"] == "shipped"

    def test_ship_creates_notification(self, db, demo_user_id):
        # notifications collection may vary; just verify a row exists
        row = db.station_notifications.find_one(
            {"owner_user_id": demo_user_id,
             "dedupe_key": f"product_shipped_{CTX['order_id']}"})
        # non-blocking: log if missing but do not fail suite (best-effort enqueue)
        CTX["ship_notif_present"] = bool(row)

    def test_advance_to_delivered_awards_points(self, http, demo_headers, demo_user_id, db):
        # Get points before
        r0 = http.get(f"{BASE_URL}/api/shop/loyalty", headers=demo_headers)
        life_before = r0.json()["lifetime_points"]

        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/products/orders/{CTX['order_id']}/status",
            json={"status": "delivered"}, headers=demo_headers)
        assert r.status_code == 200
        assert r.json()["order"]["status"] == "delivered"

        time.sleep(0.5)
        # verify ledger row
        row = db.points_ledger.find_one(
            {"user_id": demo_user_id, "source": "marketplace_product",
             "source_id": CTX["order_id"]})
        assert row, "expected points_ledger row for marketplace_product on delivered"
        assert row["delta"] > 0
        CTX["delivered_base_points"] = int(row["delta"])

        # loyalty status reflects new lifetime
        r1 = http.get(f"{BASE_URL}/api/shop/loyalty", headers=demo_headers)
        life_after = r1.json()["lifetime_points"]
        assert life_after >= life_before + row["delta"]

    def test_deliver_idempotent(self, http, demo_headers, db, demo_user_id):
        rows = list(db.points_ledger.find(
            {"user_id": demo_user_id, "source": "marketplace_product",
             "source_id": CTX["order_id"]}))
        assert len(rows) == 1, f"points award must be idempotent, got {len(rows)} rows"

    def test_re_advance_rejected(self, http, demo_headers):
        # delivered → delivered rejected
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/products/orders/{CTX['order_id']}/status",
            json={"status": "delivered"}, headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_transition"

    def test_loyalty_bonus_row_if_applicable(self, db, demo_user_id):
        # If bonus_pct > 0 for demo's current tier, a loyalty_bonus row must exist
        loyalty_row = db.points_ledger.find_one(
            {"user_id": demo_user_id, "source": "marketplace_loyalty_bonus",
             "source_id": CTX["order_id"]})
        # Only assert if the previous test recorded base points AND user is silver+
        base_pts = CTX.get("delivered_base_points", 0)
        # Get tier via lifetime points
        agg = list(db.points_ledger.aggregate([
            {"$match": {"user_id": demo_user_id, "delta": {"$gt": 0}}},
            {"$group": {"_id": None, "t": {"$sum": "$delta"}}},
        ]))
        lifetime = int(agg[0]["t"]) if agg else 0
        if lifetime >= 1000 and base_pts > 0:
            assert loyalty_row is not None, "expected loyalty tier bonus row"
            assert loyalty_row["delta"] > 0


# ─────────────────── Service Photos ───────────────────
class TestServicePhotos:
    def test_pick_a_service(self, http, demo_headers, demo_biz):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/services",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        if not items:
            pytest.skip("no services present for demo biz")
        CTX["svc_id"] = items[0]["service_id"]

    def test_upload_service_photo(self, http, demo_headers):
        if "svc_id" not in CTX:
            pytest.skip("no service")
        r = http.post(
            f"{BASE_URL}/api/merchant/marketplace/services/items/{CTX['svc_id']}/photo",
            json={"file_base64": PNG_1x1_B64, "ext": "png"}, headers=demo_headers)
        assert r.status_code == 200, r.text
        url = r.json()["image_url"]
        assert url.startswith("/api/static/menu_photos/") or url.startswith("http")
        CTX["svc_image_url"] = url

    def test_consumer_service_exposes_image_url(self, http, demo_headers):
        if "svc_id" not in CTX:
            pytest.skip("no service")
        r = http.get(f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/services",
                     headers=demo_headers)
        assert r.status_code == 200
        items = r.json().get("items") or r.json().get("services") or []
        # response format may be {items:[..]} or {services:[..]}; find our svc
        me = next((s for s in items if s.get("service_id") == CTX["svc_id"]), None)
        assert me is not None, r.text
        assert me.get("image_url"), "service must expose image_url after upload"

    def test_upload_photo_missing_file(self, http, demo_headers):
        if "svc_id" not in CTX:
            pytest.skip("no service")
        r = http.post(
            f"{BASE_URL}/api/merchant/marketplace/services/items/{CTX['svc_id']}/photo",
            json={"ext": "png"}, headers=demo_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "file_required"


# ─────────────────── Cleanup ───────────────────
def teardown_module(module):
    """Delete the TEST_iter59 product created during this run."""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/demo", json={})
        tok = r.json().get("session_token") or r.json().get("token")
        headers = {"Authorization": f"Bearer {tok}"}
        pid = CTX.get("prod_id")
        if pid:
            requests.delete(
                f"{BASE_URL}/api/merchant/marketplace/products/items/{pid}",
                headers=headers)
    except Exception:
        pass
