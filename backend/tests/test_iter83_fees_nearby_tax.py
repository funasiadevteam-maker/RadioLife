"""Iteration 83 backend tests — service fee + delivery + tax, nearby sort,
merchant fulfillment settings round-trip, admin tax CRUD + AI estimate."""
import os
import time
import pytest
import requests

def _read_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except FileNotFoundError:
            pass
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")


BASE_URL = _read_backend_url()

CONSUMER = ("demo@bigfm.dubai", "DemoPass123!")
MERCHANT = ("test@bigfm.dubai", "TestUser123!")
ADMIN = ("admin@bigfm.dubai", "AdminPass123!")

BIZ = "biz_sample_funpizza"
ITEM = "mi_biz_sample_funpizza_0"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def consumer():
    return _login(*CONSUMER)


@pytest.fixture(scope="module")
def merchant():
    return _login(*MERCHANT)


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


# ─────────────────── Fees + Tax on quote/checkout ───────────────────
class TestQuoteFeesTax:
    def _quote(self, s, fulfillment, pickup_time="now"):
        body = {
            "business_id": BIZ,
            "items": [{"item_id": ITEM, "qty": 1, "selected_option_ids": ["opt_size_medium"]}],
            "fulfillment": fulfillment,
            "pickup_time": pickup_time,
        }
        r = s.post(f"{BASE_URL}/api/shop/orders/quote", json=body, timeout=15)
        assert r.status_code == 200, r.text
        return r.json()

    def test_pickup_quote_service_fee_10pct_no_delivery(self, consumer):
        q = self._quote(consumer, "pickup", "+15")
        subtotal = q["subtotal_cents"]
        # 10% service fee (Fun Pizza seeded with service_fee 10%)
        assert q["service_fee_cents"] == round(subtotal * 0.10), q
        assert q["delivery_fee_cents"] == 0
        # UAE VAT 5% on (subtotal - coupon 0 + fees)
        expected_tax = round((subtotal + q["service_fee_cents"]) * 0.05)
        assert q["tax_cents"] == expected_tax, q
        assert q["eta_label"].startswith("Ready in ~15"), q["eta_label"]
        assert q["total_cents"] == q["goods_total_cents"] + q["service_fee_cents"] + q["delivery_fee_cents"] + q["tax_cents"]

    def test_delivery_quote_fee_500_eta_range(self, consumer):
        q = self._quote(consumer, "delivery")
        assert q["delivery_fee_cents"] == 500, q
        assert q["delivery_available"] is True
        # eta looks like 'N–M min'
        assert "–" in q["eta_label"] and q["eta_label"].endswith("min"), q["eta_label"]
        # tax on (subtotal + service_fee + delivery_fee) @ 5%
        subtotal = q["subtotal_cents"]
        base = subtotal + q["service_fee_cents"] + q["delivery_fee_cents"]
        assert q["tax_cents"] == round(base * 0.05), q
        assert q["total_cents"] == q["goods_total_cents"] + q["service_fee_cents"] + q["delivery_fee_cents"] + q["tax_cents"]

    def test_checkout_persists_fee_and_tax_fields(self, consumer):
        body = {
            "business_id": BIZ,
            "items": [{"item_id": ITEM, "qty": 1, "selected_option_ids": ["opt_size_medium"]}],
            "fulfillment": "delivery",
            "pickup_time": "now",
            "origin_url": BASE_URL,
        }
        r = consumer.post(f"{BASE_URL}/api/shop/orders/checkout", json=body, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        oid = j["order_id"]
        # Fetch order document back
        r2 = consumer.get(f"{BASE_URL}/api/shop/orders/{oid}", timeout=15)
        assert r2.status_code == 200
        o = r2.json()["order"]
        assert o["fulfillment"] == "delivery"
        assert o["pickup_time"] == "now"
        assert o["service_fee_cents"] > 0
        assert o["delivery_fee_cents"] == 500
        assert o["tax_cents"] > 0
        assert o["tax_label"]
        assert o["eta_label"]


# ─────────────────── Nearby sort ───────────────────
class TestNearby:
    def test_nearby_sort_dubai(self, consumer):
        r = consumer.get(
            f"{BASE_URL}/api/shop/businesses",
            params={"sort": "nearby", "lat": 25.2048, "lng": 55.2708},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        items = j.get("items") or j.get("businesses") or []
        assert len(items) >= 2, j
        # First one should be Fun Pizza (~0km)
        first = items[0]
        assert first.get("business_id") == "biz_sample_funpizza" or first.get("distance_km", 99) < 0.5, first
        # distance_km ascending
        dists = [it.get("distance_km") for it in items if it.get("distance_km") is not None]
        assert dists == sorted(dists), dists
        # Includes non-food categories (Pulse Fitness, salons, etc.)
        cats = {it.get("category") for it in items}
        assert len(cats) >= 2, cats

    def test_nearby_cards_have_geo_and_delivery(self, consumer):
        r = consumer.get(
            f"{BASE_URL}/api/shop/businesses",
            params={"sort": "nearby", "lat": 25.2048, "lng": 55.2708},
            timeout=15,
        )
        items = r.json().get("items") or []
        # At least one item has full metadata
        got_geo = any(it.get("geo") or (it.get("lat") is not None and it.get("lng") is not None) for it in items)
        got_delivery = any("delivery_enabled" in it for it in items)
        got_prep = any("prep_time_min" in it for it in items)
        assert got_geo, "no geo on nearby cards"
        assert got_delivery, "no delivery_enabled on cards"
        assert got_prep, "no prep_time_min on cards"


# ─────────────────── Merchant fulfillment round-trip ───────────────────
class TestMerchantFulfillment:
    def test_get_settings(self, merchant):
        r = merchant.get(f"{BASE_URL}/api/merchant/marketplace/fulfillment", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "service_fee" in j
        assert "delivery" in j
        assert "prep_time_min" in j
        assert "geo" in j
        assert "tax_jurisdiction" in j

    def test_patch_roundtrip(self, merchant):
        body = {
            "service_fee": {"enabled": True, "percent": 12.5},
            "delivery": {"enabled": True, "fee_cents": 750, "eta_min": 25, "eta_max": 40, "min_order_cents": 1000},
            "prep_time_min": 18,
            "geo": {"lat": 25.21, "lng": 55.27, "address": "Test HQ"},
            "tax_jurisdiction": {"country": "AE", "state": None, "county": None, "city": "Dubai"},
        }
        r = merchant.patch(f"{BASE_URL}/api/merchant/marketplace/fulfillment", json=body, timeout=15)
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["service_fee"]["percent"] == 12.5
        assert saved["delivery"]["fee_cents"] == 750
        assert saved["delivery"]["eta_min"] == 25
        assert saved["prep_time_min"] == 18
        assert saved["geo"]["lat"] == 25.21
        assert saved["tax_jurisdiction"]["country"] == "AE"

        # GET back
        r2 = merchant.get(f"{BASE_URL}/api/merchant/marketplace/fulfillment", timeout=15)
        j2 = r2.json()
        assert j2["service_fee"]["percent"] == 12.5
        assert j2["delivery"]["fee_cents"] == 750
        assert j2["prep_time_min"] == 18


# ─────────────────── Admin tax rules ───────────────────
class TestAdminTax:
    def test_list_seeded(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/tax/rules", timeout=15)
        assert r.status_code == 200
        j = r.json()
        rule_ids = {it.get("rule_id") for it in j.get("items", [])}
        assert {"tax_ae_vat", "tax_us_ca", "tax_us_ca_la"}.issubset(rule_ids), rule_ids

    def test_crud_rule(self, admin):
        body = {"country": "TEST_XX", "state": None, "county": None, "city": None,
                "rate_percent": 3.14, "label": "TEST rule", "active": True}
        r = admin.post(f"{BASE_URL}/api/admin/tax/rules", json=body, timeout=15)
        assert r.status_code == 200, r.text
        rid = r.json()["rule"]["rule_id"]
        # PATCH
        body["rate_percent"] = 6.28
        r2 = admin.patch(f"{BASE_URL}/api/admin/tax/rules/{rid}", json=body, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["rule"]["rate_percent"] == 6.28
        # DELETE
        r3 = admin.delete(f"{BASE_URL}/api/admin/tax/rules/{rid}", timeout=15)
        assert r3.status_code == 200

    def test_ai_estimate_la(self, admin):
        body = {"country": "US", "state": "CA", "county": "Los Angeles", "city": "Los Angeles"}
        r = admin.post(f"{BASE_URL}/api/admin/tax/ai-estimate", json=body, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "rate_percent" in j
        assert isinstance(j["rate_percent"], (int, float))
        assert 0 < j["rate_percent"] < 20, j
        assert "disclaimer" in j
        assert "label" in j or True  # label optional
