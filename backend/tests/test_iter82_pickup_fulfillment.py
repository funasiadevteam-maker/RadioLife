"""Iteration 82 — Pickup/Delivery fulfillment persistence on marketplace orders.

Covers:
  * POST /api/shop/orders/quote — regression: option upcharges price correctly
    (Grill House 'Signature Ribeye': Cook required + Add-ons +$2.50/+$3.50/+$5.00)
  * POST /api/shop/orders/checkout — persists fulfillment + pickup_time on the
    created order (fully-covered $0 membership path AND Stripe-hosted path).
  * GET /api/merchant/marketplace/orders — merchant sees fulfillment + pickup_time.
  * Membership entitlement pricing on Fun Pizza (demo@ + test@ own Pizza Club).
"""
from __future__ import annotations

import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
FUNPIZZA = "biz_sample_funpizza"
GRILL = "biz_demo_grill"
RIBEYE = "mi_biz_demo_grill_2"
MAC_PIZZA = "mi_biz_sample_funpizza_0"


def _login_cookie(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def test_user():
    return _login_cookie("test@bigfm.dubai", "TestUser123!")


@pytest.fixture(scope="module")
def demo_user():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin_user():
    return _login_cookie("admin@bigfm.dubai", "AdminPass123!")


# ── Menu discovery helpers ────────────────────────────────────────────────
def _get_menu_item(sess, business_id, item_id):
    r = sess.get(f"{BASE}/api/shop/businesses/{business_id}/menu", timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    items = []
    for sec in data.get("sections", []) or []:
        items.extend(sec.get("items", []) or [])
    if not items:
        items = data.get("items", []) or []
    for it in items:
        if it.get("item_id") == item_id:
            return it
    return None


# ── 1. Regression: option upcharges (Grill House Ribeye) ──────────────────
class TestOptionUpcharges:
    def test_ribeye_addons_price_delta(self, test_user):
        it = _get_menu_item(test_user, GRILL, RIBEYE)
        assert it, "Ribeye not found in Grill House menu"
        base = int(it.get("price_cents", 0))
        # find option IDs
        cook_group = next((g for g in it.get("option_groups", []) if g.get("required")), None)
        addons_group = next((g for g in it.get("option_groups", []) if g.get("type") == "multi"), None)
        assert cook_group and addons_group, f"missing option groups: {it.get('option_groups')}"
        cook_opt = cook_group["options"][0]["option_id"]
        # pick all three add-ons
        addons = {o["label"].lower(): o for o in addons_group["options"]}
        assert "extra cheese" in addons and "smoked bacon" in addons and "truffle fries" in addons
        expected_addons = 250 + 350 + 500
        r = test_user.post(f"{BASE}/api/shop/orders/quote", json={
            "business_id": GRILL,
            "items": [{
                "item_id": RIBEYE, "qty": 1,
                "selected_option_ids": [cook_opt,
                                        addons["extra cheese"]["option_id"],
                                        addons["smoked bacon"]["option_id"],
                                        addons["truffle fries"]["option_id"]],
            }],
        }, timeout=15)
        assert r.status_code == 200, r.text[:200]
        q = r.json()
        line = q["line_items"][0]
        # Price should be base + $2.50 + $3.50 + $5.00 (cook required delta = 0)
        assert line["price_cents"] == base + expected_addons, (
            f"expected {base + expected_addons}, got {line['price_cents']} (base={base})")
        # And option deltas must be positive on the multi-select group
        assert all(o.get("price_delta_cents", 0) >= 0 for o in addons_group["options"])


# ── 2. Membership entitlement (Pizza Club → base free on Fun Pizza) ───────
class TestMembershipEntitlement:
    def _find_entitlement_and_item(self, sess):
        # Get any owned membership for this business
        r = sess.get(f"{BASE}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200, r.text[:200]
        for m in r.json().get("items", []) or r.json().get("memberships", []) or []:
            if m.get("business_id") == FUNPIZZA and m.get("status") in (None, "active"):
                for ent in (m.get("benefits") or []):
                    if ent.get("remaining", 1) > 0:
                        return m, ent
        return None, None

    def test_pizza_club_waives_base(self, test_user):
        mem, ent = self._find_entitlement_and_item(test_user)
        if not ent:
            pytest.skip("No Pizza Club entitlement seeded for test@")
        it = _get_menu_item(test_user, FUNPIZZA, MAC_PIZZA)
        assert it, "Mac & Cheese pizza not found"
        size_group = next((g for g in it.get("option_groups", []) if g.get("required")), None)
        assert size_group
        size_opt = size_group["options"][0]["option_id"]
        r = test_user.post(f"{BASE}/api/shop/orders/quote", json={
            "business_id": FUNPIZZA,
            "items": [{"item_id": MAC_PIZZA, "qty": 1,
                       "selected_option_ids": [size_opt],
                       "apply_entitlement_id": ent["entitlement_id"]}],
        }, timeout=15)
        assert r.status_code == 200, r.text[:200]
        q = r.json()
        assert q["entitlement_discount_cents"] > 0, f"expected base waived: {q}"


# ── 3. Fulfillment + pickup_time persistence on $0 order ──────────────────
class TestFulfillmentPersistenceFreeOrder:
    def _place_free_order(self, sess, fulfillment, pickup_time):
        mem_r = sess.get(f"{BASE}/api/shop/memberships/mine", timeout=15).json()
        ent = None
        for m in (mem_r.get("items") or mem_r.get("memberships") or []):
            if m.get("business_id") == FUNPIZZA:
                for e in m.get("benefits") or []:
                    if e.get("remaining", 1) > 0:
                        ent = e; break
            if ent: break
        if not ent:
            pytest.skip("No entitlement available to zero-out order total")
        it = _get_menu_item(sess, FUNPIZZA, MAC_PIZZA)
        size_group = next((g for g in it.get("option_groups", []) if g.get("required")), None)
        size_opt = size_group["options"][0]["option_id"]
        body = {
            "business_id": FUNPIZZA,
            "items": [{"item_id": MAC_PIZZA, "qty": 1,
                       "selected_option_ids": [size_opt],
                       "apply_entitlement_id": ent["entitlement_id"]}],
            "fulfillment": fulfillment, "pickup_time": pickup_time,
            "origin_url": BASE,
        }
        r = sess.post(f"{BASE}/api/shop/orders/checkout", json=body, timeout=20)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    @pytest.mark.parametrize("fulfillment,pickup_time", [
        ("pickup", "now"), ("pickup", "+15"), ("delivery", "+30"), ("pickup", "+45"),
    ])
    def test_fulfillment_persists_free_path(self, test_user, fulfillment, pickup_time):
        resp = self._place_free_order(test_user, fulfillment, pickup_time)
        order_id = resp["order_id"]
        # verify persisted via GET
        r = test_user.get(f"{BASE}/api/shop/orders/{order_id}", timeout=15)
        assert r.status_code == 200, r.text[:200]
        o = r.json()["order"]
        assert o.get("fulfillment") == fulfillment, f"expected {fulfillment}, got {o.get('fulfillment')}"
        assert o.get("pickup_time") == pickup_time, f"expected {pickup_time}, got {o.get('pickup_time')}"

    def test_defaults_pickup_now_when_omitted(self, test_user):
        mem_r = test_user.get(f"{BASE}/api/shop/memberships/mine", timeout=15).json()
        ent = None
        for m in (mem_r.get("items") or mem_r.get("memberships") or []):
            if m.get("business_id") == FUNPIZZA:
                for e in m.get("benefits") or []:
                    if e.get("remaining", 1) > 0:
                        ent = e; break
            if ent: break
        if not ent:
            pytest.skip("no entitlement")
        it = _get_menu_item(test_user, FUNPIZZA, MAC_PIZZA)
        size_group = next((g for g in it.get("option_groups", []) if g.get("required")), None)
        size_opt = size_group["options"][0]["option_id"]
        r = test_user.post(f"{BASE}/api/shop/orders/checkout", json={
            "business_id": FUNPIZZA,
            "items": [{"item_id": MAC_PIZZA, "qty": 1,
                       "selected_option_ids": [size_opt],
                       "apply_entitlement_id": ent["entitlement_id"]}],
            "origin_url": BASE,
        }, timeout=20)
        assert r.status_code == 200, r.text[:300]
        order_id = r.json()["order_id"]
        o = test_user.get(f"{BASE}/api/shop/orders/{order_id}", timeout=15).json()["order"]
        assert o.get("fulfillment") == "pickup", f"default fulfillment expected pickup, got {o.get('fulfillment')}"
        assert o.get("pickup_time") == "now", f"default pickup_time expected 'now', got {o.get('pickup_time')}"


# ── 4. Stripe-hosted checkout path: fulfillment fields persist ────────────
class TestFulfillmentPersistenceStripePath:
    def test_stripe_path_persists_fields(self, test_user):
        # No entitlement -> total > 0 -> Stripe-hosted flow
        it = _get_menu_item(test_user, GRILL, RIBEYE)
        cook_opt = next((g["options"][0]["option_id"] for g in it["option_groups"] if g["required"]), None)
        r = test_user.post(f"{BASE}/api/shop/orders/checkout", json={
            "business_id": GRILL,
            "items": [{"item_id": RIBEYE, "qty": 1, "selected_option_ids": [cook_opt]}],
            "fulfillment": "delivery", "pickup_time": "+45",
            "origin_url": BASE,
        }, timeout=20)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("status") == "pending_payment"
        assert j.get("checkout_url"), "expected Stripe hosted checkout url"
        order_id = j["order_id"]
        o = test_user.get(f"{BASE}/api/shop/orders/{order_id}", timeout=15).json()["order"]
        assert o.get("fulfillment") == "delivery"
        assert o.get("pickup_time") == "+45"
        assert o.get("status") == "pending_payment"


# ── 5. Merchant orders endpoint surfaces fulfillment + pickup_time ────────
class TestMerchantOrdersSurface:
    def test_merchant_sees_fulfillment_fields(self, test_user):
        # test@bigfm.dubai owns business biz_dc324d800f66. Place a Stripe-hosted
        # order against own business (pending_payment) then query merchant view
        # filtered by status=pending_payment (bypasses the paid-only default).
        OWN_BIZ = "biz_dc324d800f66"
        menu = test_user.get(f"{BASE}/api/shop/businesses/{OWN_BIZ}/menu", timeout=15).json()
        item = None
        for sec in menu.get("sections", []) or []:
            for it in sec.get("items", []) or []:
                if int(it.get("price_cents", 0)) > 0:
                    item = it; break
            if item: break
        if not item:
            pytest.skip("no priced item on test@'s own business menu")
        r = test_user.post(f"{BASE}/api/shop/orders/checkout", json={
            "business_id": OWN_BIZ,
            "items": [{"item_id": item["item_id"], "qty": 1, "selected_option_ids": []}],
            "fulfillment": "delivery", "pickup_time": "+30",
            "origin_url": BASE,
        }, timeout=20)
        assert r.status_code == 200, r.text[:300]
        placed = r.json()["order_id"]
        r = test_user.get(f"{BASE}/api/merchant/marketplace/orders?status=pending_payment", timeout=15)
        assert r.status_code == 200, r.text[:200]
        items = r.json().get("items", [])
        target = next((o for o in items if o.get("order_id") == placed), None)
        assert target, f"placed order {placed} not visible to merchant"
        assert target.get("fulfillment") == "delivery"
        assert target.get("pickup_time") == "+30"


# ── 6. Admin routes reachable (for layout page) ───────────────────────────
class TestAdminReachable:
    def test_admin_merchants_api(self, admin_user):
        r = admin_user.get(f"{BASE}/api/admin/stripe-connect/merchants", timeout=15)
        assert r.status_code in (200, 404), f"unexpected admin route status {r.status_code}"
