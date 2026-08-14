"""Iteration 86 — Delivery address, destination/origin tax, order status
push relay + merchant AI tax estimate.

- Backend: POST /api/shop/orders/quote and /checkout with delivery_address
  drives destination tax; pickup uses origin.
- Backend: POST /api/merchant/marketplace/tax/ai-estimate (owner-gated) via
  Emergent LLM Gemini.
- Backend: GET/PATCH /api/merchant/marketplace/fulfillment round-trips tax_override.
- Backend: POST /api/register-push returns 500 with placeholder key (expected).
- Backend: Order status transitions still succeed & 'preparing' resets ready_at
  even though push send is a no-op.
"""
import os
import time
import pytest
import requests
from pathlib import Path


def _load_base_url():
    envp = Path("/app/frontend/.env")
    for line in envp.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or _load_base_url()
BIZ = "biz_sample_funpizza"
ITEM_NO_OPTS = "mi_biz_sample_funpizza_6"


# ── auth fixtures ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def buyer():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"},
               timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def merchant():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "test@bigfm.dubai", "password": "TestUser123!"},
               timeout=15)
    assert r.status_code == 200, r.text
    return s


# ── (1) quote / checkout: destination vs origin tax ─────────────────────────
class TestDeliveryAddressTax:
    def test_pickup_uses_origin_uae_vat_5pct(self, buyer):
        r = buyer.post(f"{BASE}/api/shop/orders/quote", json={
            "business_id": BIZ, "fulfillment": "pickup",
            "items": [{"item_id": ITEM_NO_OPTS, "qty": 1}]})
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["fulfillment"] == "pickup"
        assert q["tax_basis"] == "origin"
        assert abs(float(q["tax_rate_percent"]) - 5.0) < 0.01, q
        assert q["tax_cents"] > 0

    def test_delivery_to_ca_uses_destination_7_25pct(self, buyer):
        r = buyer.post(f"{BASE}/api/shop/orders/quote", json={
            "business_id": BIZ, "fulfillment": "delivery",
            "items": [{"item_id": ITEM_NO_OPTS, "qty": 1}],
            "delivery_address": {"country": "US", "state": "CA",
                                 "city": "Los Angeles",
                                 "lat": 34.05, "lng": -118.24}})
        assert r.status_code == 200, r.text
        q = r.json()
        # If delivery isn't enabled the backend coerces to pickup — verify
        # this store has delivery on.
        assert q["delivery_available"] is True, q
        assert q["fulfillment"] == "delivery"
        assert q["tax_basis"] == "destination"
        assert abs(float(q["tax_rate_percent"]) - 7.25) < 0.5, q

    def test_checkout_persists_delivery_fields(self, buyer):
        # Place a delivery order and verify persistence via GET.
        r = buyer.post(f"{BASE}/api/shop/orders/checkout", json={
            "business_id": BIZ, "fulfillment": "delivery",
            "items": [{"item_id": ITEM_NO_OPTS, "qty": 1}],
            "origin_url": BASE,
            "delivery_address": {"country": "US", "state": "CA",
                                 "city": "Los Angeles", "line1": "1 Main St",
                                 "lat": 34.05, "lng": -118.24}})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        order_id = j["order_id"]

        # GET back
        rr = buyer.get(f"{BASE}/api/shop/orders/{order_id}")
        assert rr.status_code == 200
        o = rr.json()["order"]
        assert o["fulfillment"] == "delivery"
        assert o["tax_basis"] == "destination"
        assert o.get("ready_at")  # persisted timestamp
        assert o.get("eta_label")
        assert (o.get("delivery_address") or {}).get("state") == "CA"


# ── (2) merchant fulfillment tax_override round-trip + ai-estimate ──────────
class TestMerchantTaxOverrideAndAi:
    def test_fulfillment_get_returns_tax_override_shape(self, merchant):
        r = merchant.get(f"{BASE}/api/merchant/marketplace/fulfillment")
        assert r.status_code == 200, r.text
        j = r.json()
        assert "tax_override" in j
        assert set(j["tax_override"].keys()) >= {"enabled", "rate_percent", "label"}

    def test_fulfillment_patch_roundtrips_tax_override(self, merchant):
        r = merchant.patch(f"{BASE}/api/merchant/marketplace/fulfillment", json={
            "tax_override": {"enabled": True, "rate_percent": 8.75,
                             "label": "TEST_iter86_override"}})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["tax_override"]["enabled"] is True
        assert abs(float(j["tax_override"]["rate_percent"]) - 8.75) < 0.01
        assert j["tax_override"]["label"] == "TEST_iter86_override"

        # Verify persisted via GET
        r2 = merchant.get(f"{BASE}/api/merchant/marketplace/fulfillment")
        assert r2.json()["tax_override"]["label"] == "TEST_iter86_override"

        # Cleanup: disable
        merchant.patch(f"{BASE}/api/merchant/marketplace/fulfillment", json={
            "tax_override": {"enabled": False, "rate_percent": 0, "label": None}})

    def test_ai_estimate_returns_rate_and_disclaimer(self, merchant):
        r = merchant.post(f"{BASE}/api/merchant/marketplace/tax/ai-estimate",
                          json={"country": "US", "state": "CA",
                                "city": "Los Angeles"}, timeout=45)
        # LLM can occasionally 502; retry once
        if r.status_code == 502:
            time.sleep(2)
            r = merchant.post(f"{BASE}/api/merchant/marketplace/tax/ai-estimate",
                              json={"country": "US", "state": "CA",
                                    "city": "Los Angeles"}, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert "rate_percent" in j and isinstance(j["rate_percent"], (int, float))
        assert 0 <= float(j["rate_percent"]) <= 40
        assert j.get("label")
        assert "disclaimer" in j

    def test_ai_estimate_requires_owner(self):
        s = requests.Session()  # anonymous
        r = s.post(f"{BASE}/api/merchant/marketplace/tax/ai-estimate",
                   json={"country": "US"}, timeout=10)
        assert r.status_code in (401, 403), r.text


# ── (3) register-push placeholder-key wiring ────────────────────────────────
class TestRegisterPush:
    def test_register_push_returns_500_with_placeholder_key(self):
        # Endpoint exists and surfaces placeholder-key error as 500.
        r = requests.post(f"{BASE}/api/register-push", json={
            "user_id": "TEST_iter86_user", "platform": "android",
            "device_token": "TEST_iter86_token_abc"}, timeout=15)
        # Route accepts anonymous & 500s with the placeholder key — expected wiring.
        assert r.status_code in (500, 502), r.text
        # Message should mention key config
        body = r.text.lower()
        assert "push" in body or "emergent" in body or "key" in body


# ── (4) status transitions still succeed with placeholder push key ──────────
class TestOrderStatusTransitions:
    def test_transitions_do_not_break_and_preparing_resets_ready_at(self, buyer, merchant):
        # Buyer creates a delivery order (goes straight to accepted only if
        # total==0; with stripe live we get pending_payment). To reach the
        # merchant transition path we need a paid order — the sample store
        # doesn't guarantee that here.
        #
        # Instead, iterate merchant's existing paid+accepted orders and
        # transition ONE through preparing→ready→picked_up.
        r = merchant.get(f"{BASE}/api/merchant/marketplace/orders?status=accepted")
        assert r.status_code == 200, r.text
        accepted = r.json().get("items", [])
        if not accepted:
            pytest.skip("No accepted+paid order available to test transitions")

        order = accepted[0]
        oid = order["order_id"]

        # accepted -> preparing (must succeed even with placeholder push key)
        r1 = merchant.patch(
            f"{BASE}/api/merchant/marketplace/orders/{oid}/status",
            json={"status": "preparing"})
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert j1["ok"] is True
        assert j1["order"]["status"] == "preparing"
        assert j1["order"].get("ready_at")  # reset by preparing transition

        # preparing -> ready
        r2 = merchant.patch(
            f"{BASE}/api/merchant/marketplace/orders/{oid}/status",
            json={"status": "ready"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["order"]["status"] == "ready"

        # ready -> picked_up
        r3 = merchant.patch(
            f"{BASE}/api/merchant/marketplace/orders/{oid}/status",
            json={"status": "picked_up"})
        assert r3.status_code == 200, r3.text
        assert r3.json()["order"]["status"] == "picked_up"
