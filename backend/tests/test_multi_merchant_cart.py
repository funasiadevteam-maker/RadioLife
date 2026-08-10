"""Multi-merchant cart split-checkout (Marketplace Phase E, item 5).

Tests the new POST /api/shop/cart/checkout endpoint that:
  - Splits into ONE product_order per venue with a shared cart_id
  - Returns a single Stripe checkout_url + session_id
  - Rejects duplicate business_id (400 duplicate_business)
  - Rejects delivery without address (400 address_required)
  - Returns 404 business_unavailable for non-approved businesses
"""
import os
import uuid
import requests
import pytest

def _load_web_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE_URL = _load_web_env().rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

# Demo credentials (bearer via /api/auth/demo). Same shared backend as web.
DEMO_EMAIL = "demo@bigfm.dubai"


# ── Session fixtures ──────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def demo_token():
    r = requests.post(f"{API}/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def approved_product_businesses(demo_headers):
    """Find approved, subscription_active businesses that have >=1 in-stock product.
    Returns list of dicts: [{business_id, product_id, price_cents, delivery}, ...] (up to 3)."""
    # Try shop/businesses (public). Fall back to any listing.
    r = requests.get(f"{API}/shop/businesses", headers=demo_headers, timeout=15)
    assert r.status_code == 200, r.text
    bizes = r.json().get("items") or []
    out = []
    for b in bizes:
        bid = b.get("business_id")
        if not bid:
            continue
        rp = requests.get(f"{API}/shop/businesses/{bid}/products",
                          headers=demo_headers, timeout=15)
        if rp.status_code != 200:
            continue
        data = rp.json()
        products = data.get("products") or []
        picked = None
        for p in products:
            if int(p.get("stock", 0)) > 0 and not p.get("variants") \
                    and int(p.get("price_cents", 0)) > 0:
                picked = p
                break
        if not picked:
            continue
        out.append({
            "business_id": bid,
            "product_id": picked["product_id"],
            "price_cents": picked.get("price_cents", 0),
            "delivery": data.get("delivery") or {},
        })
        if len(out) >= 3:
            break
    return out


# ── Cart split-checkout tests ────────────────────────────────────────────
class TestCartCheckoutSplit:
    def test_two_business_split_returns_order_per_venue(
            self, demo_headers, approved_product_businesses):
        if len(approved_product_businesses) < 2:
            pytest.skip(f"Need >=2 approved product businesses with in-stock items; "
                        f"found {len(approved_product_businesses)} "
                        f"(seed data currently ships only 1 product-selling venue)")
        biz = approved_product_businesses[:2]
        groups = [{
            "business_id": b["business_id"], "fulfillment": "pickup",
            "items": [{"product_id": b["product_id"], "qty": 1}],
        } for b in biz]
        r = requests.post(f"{API}/shop/cart/checkout",
                          json={"groups": groups, "use_gift_card": False,
                                "origin_url": BASE_URL},
                          headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Shape assertions
        assert data.get("ok") is True
        assert "cart_id" in data and data["cart_id"].startswith("cart_")
        assert isinstance(data.get("order_ids"), list)
        assert len(data["order_ids"]) == 2, "one order per venue expected"
        assert data.get("checkout_url", "").startswith("https://checkout.stripe.com/") or \
               data.get("checkout_url", "").startswith("https://") or \
               data.get("total_cents", 1) == 0  # covered-by-gift edge
        assert data.get("session_id"), "expected a single Stripe session"
        assert isinstance(data.get("grand_total_cents"), int)

        # Persistence: each order_id resolvable + shares cart_id
        cart_id = data["cart_id"]
        for oid in data["order_ids"]:
            rs = requests.get(f"{API}/shop/product-orders/{oid}/status",
                              headers=demo_headers, timeout=15)
            assert rs.status_code == 200, rs.text
            od = rs.json().get("order") or {}
            assert od.get("cart_id") == cart_id
            assert od.get("session_id") == data["session_id"]
            assert od.get("payment_status") == "pending"

    def test_single_venue_cart_still_works(
            self, demo_headers, approved_product_businesses):
        """Even with 1 venue, cart/checkout endpoint should return proper split payload
        (cart_id, order_ids list, session_id, checkout_url, grand_total_cents)."""
        if not approved_product_businesses:
            pytest.skip("No approved product businesses found")
        b = approved_product_businesses[0]
        r = requests.post(f"{API}/shop/cart/checkout",
                          json={"groups": [{
                              "business_id": b["business_id"], "fulfillment": "pickup",
                              "items": [{"product_id": b["product_id"], "qty": 1}],
                          }], "use_gift_card": False, "origin_url": BASE_URL},
                          headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("cart_id", "").startswith("cart_")
        assert len(data.get("order_ids") or []) == 1
        assert data.get("session_id"), "Stripe session expected for paid cart"
        assert "checkout.stripe.com" in (data.get("checkout_url") or ""), \
            f"expected Stripe checkout URL, got {data.get('checkout_url')!r}"
        assert isinstance(data.get("grand_total_cents"), int)
        assert data["grand_total_cents"] > 0
        # Verify order persistence carries cart_id + shared session
        oid = data["order_ids"][0]
        rs = requests.get(f"{API}/shop/product-orders/{oid}/status",
                          headers=demo_headers, timeout=15)
        assert rs.status_code == 200
        od = rs.json().get("order") or {}
        assert od.get("cart_id") == data["cart_id"]
        assert od.get("session_id") == data["session_id"]
        assert od.get("business_id") == b["business_id"]

    def test_duplicate_business_returns_400(
            self, demo_headers, approved_product_businesses):
        if not approved_product_businesses:
            pytest.skip("No approved product businesses available")
        b = approved_product_businesses[0]
        groups = [{
            "business_id": b["business_id"], "fulfillment": "pickup",
            "items": [{"product_id": b["product_id"], "qty": 1}],
        }, {
            "business_id": b["business_id"], "fulfillment": "pickup",
            "items": [{"product_id": b["product_id"], "qty": 1}],
        }]
        r = requests.post(f"{API}/shop/cart/checkout",
                          json={"groups": groups, "origin_url": BASE_URL},
                          headers=demo_headers, timeout=15)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail") or {}
        assert detail.get("code") == "duplicate_business", detail

    def test_delivery_without_address_returns_400(
            self, demo_headers, approved_product_businesses):
        # Find one with delivery=True
        cand = next((b for b in approved_product_businesses
                     if (b.get("delivery") or {}).get("delivery")), None)
        if not cand:
            pytest.skip("No approved product business with delivery enabled")
        groups = [{
            "business_id": cand["business_id"], "fulfillment": "delivery",
            "items": [{"product_id": cand["product_id"], "qty": 1}],
        }]
        r = requests.post(f"{API}/shop/cart/checkout",
                          json={"groups": groups, "origin_url": BASE_URL},
                          headers=demo_headers, timeout=15)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail") or {}
        assert detail.get("code") == "address_required", detail

    def test_unknown_business_returns_404(self, demo_headers,
                                          approved_product_businesses):
        if not approved_product_businesses:
            pytest.skip("Need at least one product to hold a valid product_id")
        p = approved_product_businesses[0]
        fake_biz = f"biz_{uuid.uuid4().hex[:12]}"
        groups = [{
            "business_id": fake_biz, "fulfillment": "pickup",
            "items": [{"product_id": p["product_id"], "qty": 1}],
        }]
        r = requests.post(f"{API}/shop/cart/checkout",
                          json={"groups": groups, "origin_url": BASE_URL},
                          headers=demo_headers, timeout=15)
        assert r.status_code == 404, r.text
        detail = r.json().get("detail") or {}
        assert detail.get("code") == "business_unavailable", detail

    def test_empty_groups_rejected(self, demo_headers):
        r = requests.post(f"{API}/shop/cart/checkout",
                          json={"groups": [], "origin_url": BASE_URL},
                          headers=demo_headers, timeout=15)
        # Pydantic min_length=1 → 422
        assert r.status_code in (400, 422), r.text

    def test_unauth_rejected(self):
        r = requests.post(f"{API}/shop/cart/checkout",
                          json={"groups": [{"business_id": "x",
                                            "items": [{"product_id": "y", "qty": 1}]}]},
                          timeout=15)
        assert r.status_code in (401, 403), r.text
