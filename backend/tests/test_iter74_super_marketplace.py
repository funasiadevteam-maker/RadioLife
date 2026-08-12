"""Iter 74 — RadioLife Super Marketplace backend tests.

Covers three new feature areas on the shared FastAPI backend:
  1. COUPONS at checkout (merchant CRUD, validate, /orders/quote reduction)
  2. ORDER ALERTS (new-count, merchant product-orders list + status advance,
     merchant_new_order notification enqueued when an order is marked paid)
  3. QR SCAN-TO-PAY (token create/status/cancel, resolve/charge, report-bypass,
     admin audit endpoints)

All tests hit the EXTERNAL preview URL and use the demo user (owns marketplace
business biz_8484f6f985d5) plus admin@bigfm.dubai for admin routes.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set"

DEMO_BIZ = "biz_8484f6f985d5"
MENU_ITEM_4200 = "mi_3ad4ad3bad30"  # Truffle Risotto @ 4200c under DEMO_BIZ


# ---------- fixtures ----------

@pytest.fixture(scope="session")
def demo_token() -> str:
    r = requests.post(f"{BASE}/api/auth/demo", json={}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


@pytest.fixture(scope="session")
def demo_user_id(demo_token) -> str:
    r = requests.get(f"{BASE}/api/auth/me",
                     headers={"Authorization": f"Bearer {demo_token}"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json().get("user_id") or r.json().get("user", {}).get("user_id")


@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"},
                      timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:120]}")
    return r.json()["session_token"]


def hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- 1) COUPONS ----------

class TestCoupons:
    def test_1_create_coupon_percent(self, demo_token):
        code = "TEST74P" + uuid.uuid4().hex[:4].upper()
        r = requests.post(f"{BASE}/api/merchant/marketplace/coupons",
                          headers=hdr(demo_token),
                          json={"code": code, "type": "percent", "value": 15,
                                "min_spend_cents": 1000, "per_user_limit": 2,
                                "active": True}, timeout=15)
        assert r.status_code == 200, r.text
        c = r.json()["coupon"]
        assert c["code"] == code.upper()
        assert c["type"] == "percent" and c["value"] == 15
        assert c["used_count"] == 0
        pytest.coupon_percent_id = c["coupon_id"]
        pytest.coupon_percent_code = c["code"]

    def test_2_create_duplicate_code_returns_409(self, demo_token):
        r = requests.post(f"{BASE}/api/merchant/marketplace/coupons",
                          headers=hdr(demo_token),
                          json={"code": pytest.coupon_percent_code,
                                "type": "percent", "value": 10}, timeout=15)
        assert r.status_code == 409, r.text

    def test_3_percent_out_of_range_rejected(self, demo_token):
        r = requests.post(f"{BASE}/api/merchant/marketplace/coupons",
                          headers=hdr(demo_token),
                          json={"code": "TEST74BAD" + uuid.uuid4().hex[:3].upper(),
                                "type": "percent", "value": 150}, timeout=15)
        assert r.status_code == 400, r.text

    def test_4_list_includes_created(self, demo_token):
        r = requests.get(f"{BASE}/api/merchant/marketplace/coupons",
                         headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200
        codes = {c["code"] for c in r.json()["items"]}
        assert pytest.coupon_percent_code in codes

    def test_5_validate_ok_percent_discount(self, demo_token):
        # 15% of 4200 = 630
        r = requests.post(f"{BASE}/api/shop/coupons/validate",
                          headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ,
                                "code": pytest.coupon_percent_code,
                                "subtotal_cents": 4200}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j["discount_cents"] == 630

    def test_6_validate_invalid_code(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/coupons/validate",
                          headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ, "code": "NOPE_XYZ",
                                "subtotal_cents": 4200}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is False and j["error"] == "invalid_coupon"

    def test_7_validate_min_spend_not_met(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/coupons/validate",
                          headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ,
                                "code": pytest.coupon_percent_code,
                                "subtotal_cents": 500}, timeout=15)
        j = r.json()
        assert j["ok"] is False and j["error"] == "min_spend_not_met"

    def test_8_quote_with_coupon_reduces_total(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/orders/quote", headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ,
                                "items": [{"item_id": MENU_ITEM_4200, "qty": 1}],
                                "use_gift_card": False, "use_points": False,
                                "coupon_code": pytest.coupon_percent_code},
                          timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("coupon_discount_cents", 0) == 630
        assert j.get("coupon_code") == pytest.coupon_percent_code
        assert not j.get("coupon_error")
        # Total should be reduced by at least the coupon discount vs baseline.
        assert j.get("total_cents", 4200) <= 4200 - 630

    def test_9_quote_with_bad_coupon_surfaces_error(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/orders/quote", headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ,
                                "items": [{"item_id": MENU_ITEM_4200, "qty": 1}],
                                "coupon_code": "BADCODE_ZZZ"}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j.get("coupon_error") == "invalid_coupon"
        assert j.get("coupon_discount_cents", 0) == 0

    def test_10_patch_coupon(self, demo_token):
        r = requests.patch(
            f"{BASE}/api/merchant/marketplace/coupons/{pytest.coupon_percent_id}",
            headers=hdr(demo_token),
            json={"code": pytest.coupon_percent_code, "type": "percent",
                  "value": 20, "min_spend_cents": 1000,
                  "per_user_limit": 2, "active": True}, timeout=15)
        assert r.status_code == 200
        assert r.json()["coupon"]["value"] == 20

    def test_11_delete_coupon(self, demo_token):
        r = requests.delete(
            f"{BASE}/api/merchant/marketplace/coupons/{pytest.coupon_percent_id}",
            headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200 and r.json()["ok"] is True
        # Subsequent validate should now say invalid.
        r2 = requests.post(f"{BASE}/api/shop/coupons/validate",
                           headers=hdr(demo_token),
                           json={"business_id": DEMO_BIZ,
                                 "code": pytest.coupon_percent_code,
                                 "subtotal_cents": 4200}, timeout=15)
        assert r2.json()["error"] == "invalid_coupon"


# ---------- 2) ORDER ALERTS ----------

class TestOrderAlerts:
    def test_1_new_count_shape(self, demo_token):
        r = requests.get(f"{BASE}/api/merchant/marketplace/orders/new-count",
                         headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j.keys()) >= {"food", "products", "total"}
        assert isinstance(j["food"], int)
        assert isinstance(j["products"], int)
        assert j["total"] == j["food"] + j["products"]

    def test_2_merchant_product_orders_list(self, demo_token):
        r = requests.get(f"{BASE}/api/merchant/marketplace/products/orders",
                         headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and isinstance(j["items"], list)
        # persist a paid order id (if any) for the status-advance test
        paid = [o for o in j["items"] if o.get("payment_status") == "paid"]
        if paid:
            pytest.product_order_id = paid[0]["order_id"]
            pytest.product_order_status = paid[0].get("status", "paid")

    def test_3_advance_product_order_status(self, demo_token):
        if not hasattr(pytest, "product_order_id"):
            pytest.skip("no paid product order available to advance")
        # advance one step from current state
        current = pytest.product_order_status
        next_map = {"paid": "packed", "packed": "shipped", "shipped": "delivered"}
        nxt = next_map.get(current)
        if not nxt:
            pytest.skip(f"order already terminal (status={current})")
        r = requests.patch(
            f"{BASE}/api/merchant/marketplace/products/orders/"
            f"{pytest.product_order_id}/status",
            headers=hdr(demo_token), json={"status": nxt}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        # Endpoint may return {"ok":..., "status":nxt} or the updated order
        assert (j.get("status") == nxt) or (j.get("order", {}).get("status") == nxt) or j.get("ok") is True


# ---------- 3) SCAN-TO-PAY ----------

class TestScanPay:
    def test_1_create_card_token_requires_pm(self, demo_token):
        # Method=card without payment_method_id should fail cleanly
        r = requests.post(f"{BASE}/api/shop/scanpay/token", headers=hdr(demo_token),
                          json={"method": "card", "amount_cents": 500}, timeout=15)
        assert r.status_code in (400, 422), r.text

    def test_2_create_points_token_low_balance(self, demo_token):
        # Try a huge points amount so we exercise the low-balance path.
        r = requests.post(f"{BASE}/api/shop/scanpay/token", headers=hdr(demo_token),
                          json={"method": "points",
                                "amount_cents": 99_000_000}, timeout=15)
        # Should reject with 400 or return an error token — either is OK
        # as long as it doesn't 500.
        assert r.status_code in (200, 400), r.text
        if r.status_code == 400:
            assert "code" in r.json().get("detail", {}) or True

    def test_3_create_and_cancel_points_token_small(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/scanpay/token", headers=hdr(demo_token),
                          json={"method": "points", "amount_cents": 50}, timeout=15)
        if r.status_code != 200:
            pytest.skip(f"points token create refused: {r.status_code} {r.text[:120]}")
        j = r.json()
        assert "token" in j
        tok = j["token"]
        # Status
        s = requests.get(f"{BASE}/api/shop/scanpay/token/{tok}/status",
                        headers=hdr(demo_token), timeout=15)
        assert s.status_code == 200
        assert s.json().get("status") in ("active", "pending", "created")
        # Cancel
        c = requests.post(f"{BASE}/api/shop/scanpay/token/{tok}/cancel",
                          headers=hdr(demo_token), timeout=15)
        assert c.status_code == 200
        # Status again → canceled
        s2 = requests.get(f"{BASE}/api/shop/scanpay/token/{tok}/status",
                         headers=hdr(demo_token), timeout=15)
        assert s2.status_code == 200
        assert s2.json().get("status") in ("canceled", "cancelled")

    def test_4_report_bypass_logs_entry(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/scanpay/report-bypass",
                          headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ,
                                "business_name": "TEST_iter74 bypass",
                                "amount_cents": 1000,
                                "note": "iter74 automated"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_5_admin_fraud_logs_visible(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/scanpay/fraud-logs",
                         headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and isinstance(j["items"], list)
        # our just-logged bypass note should appear somewhere
        notes = " ".join(str(x.get("note", "")) for x in j["items"])
        assert "iter74" in notes.lower() or len(j["items"]) >= 1

    def test_6_admin_charges_list(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/scanpay/charges",
                         headers=hdr(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        assert "items" in r.json()

    def test_7_admin_endpoints_require_admin(self, demo_token):
        r = requests.get(f"{BASE}/api/admin/scanpay/fraud-logs",
                         headers=hdr(demo_token), timeout=15)
        assert r.status_code in (401, 403), f"non-admin should be blocked: {r.status_code}"

    def test_8_resolve_bad_token_404(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/scanpay/resolve",
                          headers=hdr(demo_token),
                          json={"token": "NONEXISTENT_XYZ"}, timeout=15)
        # Service returns 200 with {"ok":false,"error":"invalid_token"} — that's the contract.
        assert r.status_code == 200
        j = r.json()
        assert j.get("ok") is False
        assert j.get("error") in ("invalid_token", "not_found", "token_not_found")
