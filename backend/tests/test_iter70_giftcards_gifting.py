"""Iteration 70 — Gift Card Gifting (backend).

Covers:
  - POST /api/giftcards/purchase (points path, gift_to_email)
  - POST /api/giftcards/purchase (card path returns Stripe checkout URL)
  - GET /api/giftcards/purchase/{session_id}/status
  - Regression: GET /api/shop/gifts/received still returns items for test@bigfm.dubai
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

TEST_EMAIL = "test@bigfm.dubai"
TEST_PASSWORD = "TestUser123!"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ---------------- Gift Card Catalog ----------------
class TestGiftCardCatalog:
    def test_catalog_returns_products(self, sess):
        r = sess.get(f"{API}/giftcards/catalog", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        assert "points_balance" in data
        assert data.get("points_per_dollar") == 100


# ---------------- Purchase (points path — includes gift) ----------------
class TestGiftCardPurchasePoints:
    def test_purchase_points_gift(self, sess):
        # Get a product
        cat = sess.get(f"{API}/giftcards/catalog").json()
        product = cat["items"][0]
        denom = product["denominations_cents"][0]  # smallest
        balance = cat["points_balance"]

        payload = {
            "product_id": product["product_id"],
            "amount_cents": denom,
            "method": "points",
            "gift_to_email": f"TEST_giftee_{uuid.uuid4().hex[:6]}@example.com",
            "message": "Enjoy your gift! (iter70 test)",
        }
        r = sess.post(f"{API}/giftcards/purchase", json=payload, timeout=20)
        # If insufficient points, skip gracefully (still assert 400 code shape)
        if r.status_code == 400:
            body = r.json()
            code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else None
            if code == "insufficient_points":
                pytest.skip(f"insufficient points to purchase (have {balance})")
        assert r.status_code == 200, f"unexpected {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("method") == "points"
        card = data.get("card")
        assert card is not None
        assert card.get("amount_cents") == denom
        assert card.get("gifted_to_email") == payload["gift_to_email"]
        assert card.get("message") == payload["message"]
        # No _id leak
        assert "_id" not in card


# ---------------- Purchase (card path — Stripe checkout URL) ----------------
class TestGiftCardPurchaseCard:
    def test_purchase_card_returns_stripe_url(self, sess):
        cat = sess.get(f"{API}/giftcards/catalog").json()
        product = cat["items"][0]
        denom = product["denominations_cents"][0]

        payload = {
            "product_id": product["product_id"],
            "amount_cents": denom,
            "method": "card",
            "gift_to_email": "TEST_giftee_card@example.com",
            "message": "Card path gift",
            "origin_url": BASE_URL,
        }
        r = sess.post(f"{API}/giftcards/purchase", json=payload, timeout=30)
        assert r.status_code == 200, f"unexpected {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("method") == "card"
        url = data.get("checkout_url") or ""
        sid = data.get("session_id") or ""
        assert url.startswith("https://checkout.stripe.com"), f"bad checkout url: {url}"
        assert sid.startswith("cs_"), f"bad session_id: {sid}"

        # Status endpoint should return pending (payment not completed in test)
        r2 = sess.get(f"{API}/giftcards/purchase/{sid}/status", timeout=20)
        assert r2.status_code == 200, r2.text
        st = r2.json()
        assert st.get("status") in ("pending", "paid")  # pending expected


# ---------------- Validation ----------------
class TestGiftCardValidation:
    def test_bad_denomination_rejected(self, sess):
        cat = sess.get(f"{API}/giftcards/catalog").json()
        product = cat["items"][0]
        r = sess.post(f"{API}/giftcards/purchase", json={
            "product_id": product["product_id"],
            "amount_cents": 99,  # not in denominations
            "method": "points",
        }, timeout=15)
        assert r.status_code == 400
        detail = r.json().get("detail")
        code = detail.get("code") if isinstance(detail, dict) else detail
        assert code == "bad_denomination"

    def test_unknown_product_404(self, sess):
        r = sess.post(f"{API}/giftcards/purchase", json={
            "product_id": "gc_nope_xxx", "amount_cents": 1000, "method": "points",
        }, timeout=15)
        assert r.status_code == 404


# ---------------- Regression: gift inbox ----------------
class TestGiftInboxRegression:
    def test_gifts_received(self, sess):
        r = sess.get(f"{API}/shop/gifts/received", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        # test@bigfm.dubai has a gifted package from prior iterations
        assert isinstance(data["items"], list)
        for it in data["items"]:
            assert "id" in it
            assert "kind" in it
            assert "from_name" in it
            assert "route" in it


# ---------------- Regression: user's gift cards ----------------
class TestMyGiftCards:
    def test_mine(self, sess):
        r = sess.get(f"{API}/giftcards/mine", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "sent" in data
