"""Iteration 73 — Saved Cards (Phase 2 Checkout).

Covers /api/shop/wallet/cards + one-tap /api/shop/orders/checkout and
/api/shop/cart/checkout paths with `payment_method_id`, the no-PM fallback
(returns Stripe hosted checkout_url), plus a gift-toggle regression:
/api/shop/orders/quote and /api/shop/cart/quote must ALWAYS emit
gift_available_cents regardless of use_gift_card.
"""
import os
import time
import pytest
import requests
import stripe


def _load_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    with open("/app/frontend/.env", "r") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip().rstrip("/")
    return ""


def _load_stripe_key() -> str:
    for line in open("/app/backend/.env"):
        if line.startswith("STRIPE_SECRET_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


BASE_URL = _load_base_url()
STRIPE_KEY = _load_stripe_key()
assert BASE_URL
assert STRIPE_KEY
stripe.api_key = STRIPE_KEY

BIZ_FOOD = "biz_sample_funpizza"
FOOD_ITEM = "mi_biz_sample_funpizza_0"  # $17.99
BIZ_PROD = "biz_sample_ambreens"
PROD = "prod_sample_biz_sample_ambreens_serum"  # $32.00


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "test@bigfm.dubai", "password": "TestUser123!"},
               timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def customer_id(sess):
    """First GET creates the customer; returns customer id from Stripe search."""
    r = sess.get(f"{BASE_URL}/api/shop/wallet/cards", timeout=20)
    assert r.status_code == 200, r.text
    # Look up customer via the /wallet/cards call — the customer id is stored
    # server-side. We fetch it by matching Stripe customers by email.
    customers = stripe.Customer.list(email="test@bigfm.dubai", limit=5)
    assert customers.data, "Stripe customer should have been created"
    return customers.data[0].id


@pytest.fixture(scope="module")
def attached_pm(customer_id):
    """Attach pm_card_visa to the user's Stripe customer for one-tap tests."""
    pm = stripe.PaymentMethod.attach("pm_card_visa", customer=customer_id)
    stripe.Customer.modify(
        customer_id, invoice_settings={"default_payment_method": pm.id})
    yield pm.id
    try:
        stripe.PaymentMethod.detach(pm.id)
    except Exception:
        pass


# ─────────────────── Wallet: /api/shop/wallet/cards ───────────────────
class TestWalletCards:
    def test_list_cards_shape(self, sess):
        r = sess.get(f"{BASE_URL}/api/shop/wallet/cards")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "cards" in d and isinstance(d["cards"], list)
        assert "default_id" in d

    def test_setup_session_returns_stripe_url(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/wallet/cards/setup-session",
                      json={"origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["checkout_url"].startswith("https://checkout.stripe.com/")
        assert d["session_id"].startswith("cs_")

    def test_setup_session_requires_origin(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/wallet/cards/setup-session",
                      json={"origin_url": ""})
        assert r.status_code == 400

    def test_list_cards_after_attach(self, sess, attached_pm):
        r = sess.get(f"{BASE_URL}/api/shop/wallet/cards")
        assert r.status_code == 200
        d = r.json()
        ids = [c["id"] for c in d["cards"]]
        assert attached_pm in ids
        pm = next(c for c in d["cards"] if c["id"] == attached_pm)
        assert pm["brand"] == "visa"
        assert pm["last4"] == "4242"
        assert pm["is_default"] is True
        assert d["default_id"] == attached_pm

    def test_set_default_unowned_returns_404(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/wallet/cards/pm_does_not_exist/default")
        assert r.status_code == 404

    def test_delete_unowned_returns_404(self, sess):
        r = sess.delete(f"{BASE_URL}/api/shop/wallet/cards/pm_does_not_exist")
        assert r.status_code == 404

    def test_set_default_owned(self, sess, attached_pm):
        r = sess.post(f"{BASE_URL}/api/shop/wallet/cards/{attached_pm}/default")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["default_id"] == attached_pm


# ─────────────────── One-tap food: /api/shop/orders/checkout ───────────────────
class TestOneTapFoodCheckout:
    def test_one_tap_with_pm_returns_paid_true(self, sess, attached_pm):
        r = sess.post(f"{BASE_URL}/api/shop/orders/checkout", json={
            "business_id": BIZ_FOOD,
            "items": [{"item_id": FOOD_ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0,
            "payment_method_id": attached_pm,
            "origin_url": BASE_URL,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("paid") is True, d
        assert d["payment_status"] == "paid"
        assert d["status"] == "accepted"
        assert d["checkout_url"] is None
        assert d["total_cents"] == 1799

    def test_no_pm_falls_back_to_hosted_checkout(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/orders/checkout", json={
            "business_id": BIZ_FOOD,
            "items": [{"item_id": FOOD_ITEM, "qty": 1}],
            "use_gift_card": False, "redeem_points": 0,
            "origin_url": BASE_URL,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://checkout.stripe.com/")
        assert d["status"] == "pending_payment"


# ─────────────── One-tap products cart: /api/shop/cart/checkout ───────────────
class TestOneTapProductsCart:
    def test_one_tap_cart_returns_paid_true(self, sess, attached_pm):
        r = sess.post(f"{BASE_URL}/api/shop/cart/checkout", json={
            "groups": [{
                "business_id": BIZ_PROD, "fulfillment": "pickup",
                "items": [{"product_id": PROD, "qty": 1}],
                "use_gift_card": False, "redeem_points": 0}],
            "payment_method_id": attached_pm,
            "origin_url": BASE_URL,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("paid") is True, d
        assert d["checkout_url"] is None
        assert d["grand_total_cents"] == 3200
        assert isinstance(d["order_ids"], list) and len(d["order_ids"]) == 1

        # Verify order is marked paid via /product-orders/{id}/status
        oid = d["order_ids"][0]
        r2 = sess.get(f"{BASE_URL}/api/shop/product-orders/{oid}/status")
        assert r2.status_code == 200, r2.text
        assert r2.json()["payment_status"] == "paid"

    def test_cart_no_pm_falls_back_to_hosted(self, sess):
        r = sess.post(f"{BASE_URL}/api/shop/cart/checkout", json={
            "groups": [{
                "business_id": BIZ_PROD, "fulfillment": "pickup",
                "items": [{"product_id": PROD, "qty": 1}],
                "use_gift_card": False, "redeem_points": 0}],
            "origin_url": BASE_URL,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("paid") is False
        assert d.get("checkout_url", "").startswith("https://checkout.stripe.com/")


# ─────────────── Gift-toggle regression ───────────────
class TestGiftToggleRegression:
    def test_orders_quote_always_emits_gift_available(self, sess):
        """/api/shop/orders/quote must return gift_available_cents whether or
        not use_gift_card is true — test@ has a $10 Fun Pizza gift card."""
        for flag in (True, False):
            r = sess.post(f"{BASE_URL}/api/shop/orders/quote", json={
                "business_id": BIZ_FOOD,
                "items": [{"item_id": FOOD_ITEM, "qty": 1}],
                "use_gift_card": flag, "redeem_points": 0})
            assert r.status_code == 200, r.text
            d = r.json()
            assert "gift_available_cents" in d
            assert d["gift_available_cents"] > 0, (
                f"gift_available_cents dropped to 0 when use_gift_card={flag}. "
                f"UX bug: toggle vanishes after user turns it off.")

    def test_cart_quote_always_emits_gift_available(self, sess):
        """/api/shop/cart/quote — Ambreens has no gift; use a hypothetical
        biz with a gift instead. test@ has a Fun Pizza gift only, and there
        is no products fixture at biz_sample_funpizza, so we can only assert
        the field is present (may be 0 if no gift exists for that biz)."""
        for flag in (True, False):
            r = sess.post(f"{BASE_URL}/api/shop/cart/quote", json={"groups": [{
                "business_id": BIZ_PROD, "fulfillment": "pickup",
                "items": [{"product_id": PROD, "qty": 1}],
                "use_gift_card": flag, "redeem_points": 0}]})
            assert r.status_code == 200, r.text
            g = r.json()["groups"][0]
            assert "gift_available_cents" in g
