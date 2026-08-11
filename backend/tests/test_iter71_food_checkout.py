"""Iteration 71 — RadioLife food checkout Phase 1.
Tests /api/shop/orders/quote and /api/shop/orders/checkout with the
Fun Pizza Kitchen sample fixture (biz_sample_funpizza / mi_biz_sample_funpizza_0).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    "https://mobile-games-v2.preview.emergentagent.com"
BIZ = "biz_sample_funpizza"
ITEM = "mi_biz_sample_funpizza_0"  # Mac & Cheese Pizza $17.99
SUBTOTAL_CENTS = 1799


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "test@bigfm.dubai", "password": "TestUser123!"},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# ---- /quote ----
class TestQuote:
    def test_quote_no_gift_no_points(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/orders/quote", json={
            "business_id": BIZ, "items": [{"item_id": ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subtotal_cents"] == SUBTOTAL_CENTS
        assert d["gift_applied_cents"] == 0
        assert d["redeemed_points"] == 0
        assert d["total_cents"] == SUBTOTAL_CENTS

    def test_quote_gift_only(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/orders/quote", json={
            "business_id": BIZ, "items": [{"item_id": ITEM, "qty": 1}],
            "use_gift_card": True, "redeem_points": 0})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gift_available_cents"] >= 1000, d
        # Gift covers subtotal ($10 gift on $17.99 → applies 1000, leaves 799)
        expected_applied = min(d["gift_available_cents"], SUBTOTAL_CENTS)
        assert d["gift_applied_cents"] == expected_applied
        assert d["total_cents"] == SUBTOTAL_CENTS - expected_applied

    def test_quote_points_capped(self, sess):
        # No gift; ask 500 pts but only $17.99 = 1799 max_redeemable = 1799
        r = sess.post(f"{BASE_URL}/api/shop/orders/quote", json={
            "business_id": BIZ, "items": [{"item_id": ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 500})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["points_balance"] >= 500
        # cap is min(balance, subtotal_cents) since 100pts=$1 → 1799 cents allows 1799 pts
        assert d["max_redeemable_points"] >= 500
        assert d["redeemed_points"] == 500  # not over cap → applied as requested
        # 500 pts * 100 // 100 = 500 cents = $5 discount
        assert d["points_discount_cents"] == 500
        assert d["total_cents"] == SUBTOTAL_CENTS - 500

    def test_quote_points_over_balance_capped(self, sess):
        # Ask 999999 pts → capped by balance
        r = sess.post(f"{BASE_URL}/api/shop/orders/quote", json={
            "business_id": BIZ, "items": [{"item_id": ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 999999})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["redeemed_points"] == d["max_redeemable_points"]
        assert d["redeemed_points"] <= d["points_balance"]

    def test_quote_gift_plus_points(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/orders/quote", json={
            "business_id": BIZ, "items": [{"item_id": ITEM, "qty": 1}],
            "use_gift_card": True, "redeem_points": 500})
        assert r.status_code == 200, r.text
        d = r.json()
        after_gift = SUBTOTAL_CENTS - d["gift_applied_cents"]
        # 500 pts = 500 cents; after gift is 799 → discount 500, total 299
        assert d["points_discount_cents"] == min(500, after_gift)
        assert d["total_cents"] == after_gift - d["points_discount_cents"]


# ---- /checkout ----
class TestCheckout:
    def test_checkout_no_gift_reaches_stripe(self, sess):
        """BUG FIX: with use_gift_card=false MUST reach card entry
        (status 'pending_payment' + checkout_url)."""
        r = sess.post(f"{BASE_URL}/api/shop/orders/checkout", json={
            "business_id": BIZ, "items": [{"item_id": ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0,
            "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending_payment", d
        assert d["checkout_url"], "checkout_url missing — bug regression!"
        assert d["checkout_url"].startswith("https://checkout.stripe.com/")
        assert d["total_cents"] == SUBTOTAL_CENTS
        assert d["gift_card_applied_cents"] == 0

    def test_checkout_gift_and_points_partial_still_reaches_stripe(self, sess):
        # $17.99 - $10 gift - $5 pts = $2.99 → still needs Stripe
        r = sess.post(f"{BASE_URL}/api/shop/orders/checkout", json={
            "business_id": BIZ, "items": [{"item_id": ITEM, "qty": 1}],
            "use_gift_card": True, "redeem_points": 500,
            "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending_payment"
        assert d["checkout_url"]
        assert d["total_cents"] > 0
        assert d["total_cents"] < SUBTOTAL_CENTS
