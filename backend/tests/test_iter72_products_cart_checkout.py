"""Iteration 72 — RadioLife products multi-venue cart checkout (Phase 1).

Covers POST /api/shop/cart/quote and /api/shop/cart/checkout with
the Ambreens Salon sample product (Argan Repair Hair Serum $32.00).
Also verifies regression on food /shop/orders/quote + /shop/orders/checkout.
"""
import os
import pytest
import requests

def _load_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    try:
        with open("/app/frontend/.env", "r") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""


BASE_URL = _load_base_url()
assert BASE_URL, "REACT_APP_BACKEND_URL is required"

BIZ_PRODUCTS = "biz_sample_ambreens"
PROD = "prod_sample_biz_sample_ambreens_serum"  # $32.00
SUB_CENTS = 3200

BIZ_FOOD = "biz_sample_funpizza"
FOOD_ITEM = "mi_biz_sample_funpizza_0"  # $17.99
FOOD_CENTS = 1799


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "test@bigfm.dubai", "password": "TestUser123!"},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# ---------- /api/shop/cart/quote ----------
class TestCartQuote:
    def test_quote_basic_no_gift_no_points(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
            "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
            "items": [{"product_id": PROD, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0}]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "groups" in d and len(d["groups"]) == 1
        g = d["groups"][0]
        assert g["business_id"] == BIZ_PRODUCTS
        assert g["subtotal_cents"] == SUB_CENTS
        assert g["gift_applied_cents"] == 0
        assert g["redeemed_points"] == 0
        assert g["points_discount_cents"] == 0
        assert g["total_cents"] == SUB_CENTS
        assert d["grand_total_cents"] == SUB_CENTS
        assert d["points_balance"] >= 0
        assert d.get("redeem_points_per_dollar") in (100, 100.0)

    def test_quote_500_points(self, sess):
        """redeem_points 500 → total = 3200 - 500 = 2700 (per review request)."""
        r = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
            "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
            "items": [{"product_id": PROD, "qty": 1}],
            "use_gift_card": False, "redeem_points": 500}]})
        assert r.status_code == 200, r.text
        d = r.json()
        g = d["groups"][0]
        assert g["subtotal_cents"] == SUB_CENTS
        # Points balance for test@ is 500 per review; but tolerate ≥500 in case
        assert d["points_balance"] >= 500, d
        assert g["redeemed_points"] == 500
        assert g["points_discount_cents"] == 500
        assert g["total_cents"] == 2700
        assert d["grand_total_cents"] == 2700

    def test_quote_points_capped_by_balance(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
            "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
            "items": [{"product_id": PROD, "qty": 1}],
            "use_gift_card": False, "redeem_points": 99999}]})
        assert r.status_code == 200, r.text
        d = r.json()
        g = d["groups"][0]
        assert g["redeemed_points"] <= d["points_balance"]
        assert g["redeemed_points"] <= g["max_redeemable_points"]

    def test_quote_returns_business_name_and_fulfillment(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
            "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
            "items": [{"product_id": PROD, "qty": 2}],
            "use_gift_card": False, "redeem_points": 0}]})
        assert r.status_code == 200, r.text
        g = r.json()["groups"][0]
        assert g.get("business_name")
        assert g["fulfillment"] == "pickup"
        assert g["subtotal_cents"] == SUB_CENTS * 2

    def test_quote_bad_business(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
            "business_id": "does_not_exist", "fulfillment": "pickup",
            "items": [{"product_id": "x", "qty": 1}],
            "use_gift_card": False, "redeem_points": 0}]})
        assert r.status_code in (400, 404)


# ---------- /api/shop/cart/checkout ----------
class TestCartCheckout:
    def test_checkout_creates_stripe_session(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/cart/checkout", json={
            "groups": [{
                "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
                "items": [{"product_id": PROD, "qty": 1}],
                "use_gift_card": False, "redeem_points": 0}],
            "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url"), d
        assert d["checkout_url"].startswith("https://checkout.stripe.com/")
        assert d["grand_total_cents"] == SUB_CENTS
        assert isinstance(d.get("order_ids"), list) and len(d["order_ids"]) == 1

    def test_checkout_with_points_reduces_grand_total(self, sess):
        """redeem_points>0 → grand_total reduced; still returns a checkout_url."""
        r = sess.post(f"{BASE_URL}/api/shop/cart/checkout", json={
            "groups": [{
                "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
                "items": [{"product_id": PROD, "qty": 1}],
                "use_gift_card": False, "redeem_points": 500}],
            "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["grand_total_cents"] == 2700
        assert d.get("checkout_url"), d

    def test_checkout_points_debited_only_after_payment(self, sess):
        """Balance BEFORE and AFTER creating a pending_payment checkout must
        be equal — points debited only on payment confirmation."""
        # Read balance via product-orders isn't ideal; use /api/rewards or
        # infer via the /cart/quote points_balance field.
        r0 = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
            "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
            "items": [{"product_id": PROD, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0}]})
        bal_before = r0.json()["points_balance"]

        r1 = sess.post(f"{BASE_URL}/api/shop/cart/checkout", json={
            "groups": [{
                "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
                "items": [{"product_id": PROD, "qty": 1}],
                "use_gift_card": False, "redeem_points": 500}],
            "origin_url": BASE_URL})
        assert r1.status_code == 200

        r2 = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
            "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
            "items": [{"product_id": PROD, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0}]})
        bal_after = r2.json()["points_balance"]
        assert bal_before == bal_after, (
            f"Points debited BEFORE payment confirmation: {bal_before} -> {bal_after}")

    def test_checkout_lists_order(self, sess):
        """Newly-created pending order should be in /product-orders."""
        r = sess.post(f"{BASE_URL}/api/shop/cart/checkout", json={
            "groups": [{
                "business_id": BIZ_PRODUCTS, "fulfillment": "pickup",
                "items": [{"product_id": PROD, "qty": 1}],
                "use_gift_card": False, "redeem_points": 0}],
            "origin_url": BASE_URL})
        assert r.status_code == 200
        order_id = r.json()["order_ids"][0]

        r2 = sess.get(f"{BASE_URL}/api/shop/product-orders")
        assert r2.status_code == 200
        items = r2.json().get("items", [])
        assert any(o.get("order_id") == order_id for o in items), \
            "Newly created order not surfaced in /product-orders"


# ---------- Regression: food /orders/quote + /orders/checkout ----------
class TestFoodRegression:
    def test_food_quote_still_works(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/orders/quote", json={
            "business_id": BIZ_FOOD, "items": [{"item_id": FOOD_ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subtotal_cents"] == FOOD_CENTS
        assert d["total_cents"] == FOOD_CENTS

    def test_food_checkout_still_works(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/orders/checkout", json={
            "business_id": BIZ_FOOD, "items": [{"item_id": FOOD_ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0,
            "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://checkout.stripe.com/")
        assert d["total_cents"] == FOOD_CENTS
