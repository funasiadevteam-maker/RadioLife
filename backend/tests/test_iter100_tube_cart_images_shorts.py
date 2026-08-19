"""iter100: Tube skin new features — real product images in feed,
shopping cart checkout (/api/shop/product-orders/checkout), and shorts pool."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_session(session):
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": "test@bigfm.dubai", "password": "TestUser123!"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}: {r.text[:200]}")
    return session  # cookie-based auth


# ── Real product images in shopping feed ────────────────────────────────
class TestShoppingFeedImages:
    def test_shopping_feed_shop_cards_have_image_url(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed",
                        params={"page": 0, "cat": "shopping"}, timeout=30).json()
        grid = next((b for b in r["blocks"] if b.get("kind") == "grid"), None)
        assert grid and grid["items"], "shopping grid missing"
        with_image = [i for i in grid["items"] if i.get("image")]
        assert with_image, f"no shop tiles have image url. sample: {grid['items'][:2]}"

    def test_shopping_feed_has_buyable_products(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed",
                        params={"page": 0, "cat": "shopping"}, timeout=30).json()
        grid = next((b for b in r["blocks"] if b.get("kind") == "grid"), None)
        assert grid
        buyable = [i for i in grid["items"] if i.get("buyable")]
        assert buyable, "no buyable products in shopping grid"
        item = buyable[0]
        # required fields for cart add
        assert item.get("business_id"), f"missing business_id: {item}"
        assert item.get("price_cents", 0) > 0, f"missing price_cents: {item}"
        assert item.get("business_name")

    def test_demo_grill_products_are_buyable(self, session):
        # aggregate across a few pages to be robust
        found = {}
        for p in range(0, 4):
            r = session.get(f"{BASE_URL}/api/browse/feed",
                            params={"page": p, "cat": "shopping"}, timeout=30).json()
            grid = next((b for b in r["blocks"] if b.get("kind") == "grid"), None)
            if not grid:
                continue
            for it in grid["items"]:
                if it.get("business_id") == "biz_demo_grill" and it.get("buyable"):
                    found[it["id"]] = it
        assert found, "no buyable biz_demo_grill products found across pages 0-3"


# ── Checkout endpoint ───────────────────────────────────────────────────
class TestProductCheckout:
    def test_checkout_grill_two_burgers_returns_stripe_url(self, auth_session):
        r = auth_session.post(f"{BASE_URL}/api/shop/product-orders/checkout", json={
            "business_id": "biz_demo_grill",
            "items": [{"product_id": "prod_demo_grill_0", "qty": 2}],
            "fulfillment": "pickup",
            "origin_url": BASE_URL,
        }, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("total_cents") == 2400, f"expected 2400 got {data.get('total_cents')}"
        url = data.get("checkout_url") or ""
        assert "checkout.stripe.com" in url, f"checkout_url not stripe: {url!r}"
        sid = data.get("session_id") or ""
        assert sid.startswith("cs_test_"), f"expected cs_test_ session id, got {sid!r}"

    def test_checkout_two_items_from_same_business(self, auth_session):
        r = auth_session.post(f"{BASE_URL}/api/shop/product-orders/checkout", json={
            "business_id": "biz_demo_grill",
            "items": [
                {"product_id": "prod_demo_grill_0", "qty": 1},
                {"product_id": "prod_demo_grill_1", "qty": 1},
            ],
            "fulfillment": "pickup",
            "origin_url": BASE_URL,
        }, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # 1200 + 750 = 1950
        assert data.get("total_cents") == 1950, f"expected 1950 got {data.get('total_cents')}"
        assert data.get("checkout_url", "").startswith("https://checkout.stripe.com")

    def test_checkout_unavailable_product_returns_400(self, auth_session):
        r = auth_session.post(f"{BASE_URL}/api/shop/product-orders/checkout", json={
            "business_id": "biz_demo_grill",
            "items": [{"product_id": "prod_does_not_exist_zzz", "qty": 1}],
            "fulfillment": "pickup",
            "origin_url": BASE_URL,
        }, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"
        # NOT 500
        detail = r.json().get("detail")
        # detail can be dict or string; check code == product_unavailable
        code = detail.get("code") if isinstance(detail, dict) else str(detail)
        assert "product_unavailable" in code, f"expected product_unavailable, got {detail}"

    def test_checkout_unknown_business_returns_404(self, auth_session):
        r = auth_session.post(f"{BASE_URL}/api/shop/product-orders/checkout", json={
            "business_id": "biz_does_not_exist_zzz",
            "items": [{"product_id": "prod_demo_grill_0", "qty": 1}],
            "fulfillment": "pickup",
            "origin_url": BASE_URL,
        }, timeout=30)
        assert r.status_code == 404, r.text


# ── Shorts pool present in All feed ─────────────────────────────────────
class TestShortsInFeed:
    def test_all_feed_may_include_shorts_shelf(self, session):
        # variant rotates each page, so scan several pages to guarantee we hit shorts
        found_shorts = False
        for p in range(0, 5):
            r = session.get(f"{BASE_URL}/api/browse/feed",
                            params={"page": p, "cat": "all"}, timeout=30).json()
            for b in r.get("blocks", []):
                if b.get("kind") == "shelf" and b.get("variant") == "shorts":
                    found_shorts = True
                    assert b.get("items"), "shorts shelf empty"
                    # each short item should have title + type=short
                    types = {i.get("type") for i in b["items"]}
                    assert types == {"short"}, f"shorts shelf has non-short items: {types}"
                    break
            if found_shorts:
                break
        assert found_shorts, "no shorts shelf found in first 5 pages of 'all' feed"
