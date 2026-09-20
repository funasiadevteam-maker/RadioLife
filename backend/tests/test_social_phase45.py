"""Phase 4 + Phase 5 backend tests — co-host, AI clips, shoppable clips,
group carts, discover, translation. Uses shared /api/social contract.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests


def _load_backend_url() -> str:
    if os.environ.get("REACT_APP_BACKEND_URL"):
        return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
    env = Path("/app/frontend/.env")
    if env.exists():
        for ln in env.read_text().splitlines():
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL is required")


BASE = _load_backend_url()
HOST_CREDS = ("demo@bigfm.dubai", "DemoPass123!")
FREE_CREDS = ("freeuser@bigfm.dubai", "FreePass123!")


def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def host_session() -> requests.Session:
    return _login(*HOST_CREDS)


@pytest.fixture(scope="session")
def free_session() -> requests.Session:
    return _login(*FREE_CREDS)


@pytest.fixture(scope="session")
def host_uid(host_session: requests.Session) -> str:
    r = host_session.get(f"{BASE}/api/auth/me", timeout=15)
    assert r.status_code == 200
    return r.json()["user_id"]


@pytest.fixture(scope="session")
def free_uid(free_session: requests.Session) -> str:
    r = free_session.get(f"{BASE}/api/auth/me", timeout=15)
    assert r.status_code == 200
    return r.json()["user_id"]


@pytest.fixture(scope="session")
def live_show(host_session):
    r = host_session.post(f"{BASE}/api/social/liveshows",
                          json={"title": "TEST_P45 Live",
                                "description": "phase 4/5 tests",
                                "business_name": "TEST_P45 Biz"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    try:
        host_session.post(f"{BASE}/api/social/liveshows/{data['show_id']}/end",
                          timeout=15)
    except Exception:
        pass


# ═════════════════════════ Co-hosting ═════════════════════════
class TestCohost:
    def test_non_host_cannot_add_cohost(self, free_session, live_show, host_uid):
        r = free_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/cohosts",
            json={"user_id": host_uid}, timeout=15)
        assert r.status_code == 403

    def test_host_adds_cohost(self, host_session, live_show, free_uid):
        r = host_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/cohosts",
            json={"user_id": free_uid}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert any(c.get("user_id") == free_uid for c in j["cohosts"]), j

    def test_cohost_can_pin_product(self, free_session, live_show):
        r = free_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/products",
            json={"title": "TEST_P45 Cohost Product",
                  "price_cents": 999}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("product_id", "").startswith("prod_")

    def test_cohost_cannot_end_show(self, free_session, live_show):
        r = free_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/end",
            timeout=15)
        assert r.status_code == 403

    def test_host_remove_cohost(self, host_session, live_show, free_uid):
        r = host_session.delete(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/cohosts/{free_uid}",
            timeout=15)
        assert r.status_code == 200

    def test_removed_cohost_cannot_pin(self, free_session, live_show):
        r = free_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/products",
            json={"title": "TEST_P45 blocked", "price_cents": 100},
            timeout=15)
        assert r.status_code == 403

    def test_re_add_cohost_for_clip_test(self, host_session, live_show, free_uid):
        r = host_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/cohosts",
            json={"user_id": free_uid}, timeout=15)
        assert r.status_code == 200


# ═════════════════════════ AI Clips ═════════════════════════
class TestClips:
    @pytest.fixture(scope="class")
    def pinned(self, host_session, live_show):
        r = host_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/products",
            json={"title": "TEST_P45 Saffron Box",
                  "price_cents": 1999, "offer": "20% OFF"}, timeout=15)
        assert r.status_code == 200
        return r.json()

    def test_host_creates_clip(self, host_session, live_show, pinned):
        r = host_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/clips",
            json={"note": "amazing reveal"}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["clip_id"].startswith("clip_")
        assert isinstance(j["title"], str) and len(j["title"]) > 0
        assert isinstance(j["caption"], str) and len(j["caption"]) > 0
        # Snapshot of pinned products at that moment.
        assert any(p.get("product_id") == pinned["product_id"]
                   for p in j["products"])
        return j

    def test_non_host_cannot_clip(self, live_show):
        anon = requests.Session()
        r = anon.post(f"{BASE}/api/social/liveshows/{live_show['show_id']}/clips",
                      json={"note": "no"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_list_clips_for_show(self, host_session, live_show):
        r = host_session.get(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/clips",
            timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)
        assert len(r.json()["items"]) >= 1

    def test_global_clip_feed(self, free_session):
        r = free_session.get(f"{BASE}/api/social/liveshows/clips/feed",
                             timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)


# ═════════════════════════ Shoppable Clip Checkout ═════════════════════════
class TestClipCheckout:
    @pytest.fixture(scope="class")
    def clip_with_prod(self, host_session, live_show):
        p = host_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/products",
            json={"title": "TEST_P45 Buyable Item",
                  "price_cents": 2500}, timeout=15).json()
        c = host_session.post(
            f"{BASE}/api/social/liveshows/{live_show['show_id']}/clips",
            json={"note": "buy this"}, timeout=60).json()
        return c, p

    def test_buy_from_clip_stripe(self, free_session, clip_with_prod):
        clip, prod = clip_with_prod
        r = free_session.post(
            f"{BASE}/api/social/liveshows/clips/{clip['clip_id']}/checkout",
            json={"product_id": prod["product_id"],
                  "origin_url": BASE}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending"
        assert j["checkout_url"].startswith("https://checkout.stripe.com/")
        assert j["order_id"].startswith("lo_")

    def test_product_not_found(self, free_session, clip_with_prod):
        clip, _ = clip_with_prod
        r = free_session.post(
            f"{BASE}/api/social/liveshows/clips/{clip['clip_id']}/checkout",
            json={"product_id": "nope", "origin_url": BASE}, timeout=15)
        assert r.status_code == 404
        assert r.json().get("detail", {}).get("code") == "product_not_found"


# ═════════════════════════ Group Carts ═════════════════════════
class TestGroupCarts:
    @pytest.fixture(scope="class")
    def cart(self, host_session, free_uid):
        r = host_session.post(f"{BASE}/api/social/carts",
                              json={"name": "TEST_P45 Party Cart",
                                    "members": [free_uid]}, timeout=15)
        assert r.status_code == 200, r.text
        return r.json()

    def test_create_cart_has_owner_and_member(self, cart, host_uid, free_uid):
        assert cart["owner_id"] == host_uid
        member_ids = [m.get("user_id") for m in cart["members"]]
        assert host_uid in member_ids
        assert free_uid in member_ids

    def test_list_carts(self, host_session, cart):
        r = host_session.get(f"{BASE}/api/social/carts", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(c["cart_id"] == cart["cart_id"] for c in items)

    def test_get_cart_by_id(self, free_session, cart):
        r = free_session.get(f"{BASE}/api/social/carts/{cart['cart_id']}",
                             timeout=15)
        assert r.status_code == 200
        assert r.json()["cart_id"] == cart["cart_id"]

    def test_add_items_to_cart(self, host_session, free_session, cart):
        r1 = host_session.post(
            f"{BASE}/api/social/carts/{cart['cart_id']}/items",
            json={"title": "TEST_P45 Item A",
                  "price_cents": 1500, "qty": 2}, timeout=15)
        assert r1.status_code == 200, r1.text
        r2 = free_session.post(
            f"{BASE}/api/social/carts/{cart['cart_id']}/items",
            json={"title": "TEST_P45 Item B",
                  "price_cents": 800, "qty": 1}, timeout=15)
        assert r2.status_code == 200, r2.text
        j = r2.json()
        assert j["item_count"] == 2
        assert j["total_cents"] == 1500 * 2 + 800

    def test_non_member_forbidden(self, cart):
        anon = requests.Session()
        r = anon.get(f"{BASE}/api/social/carts/{cart['cart_id']}", timeout=15)
        assert r.status_code in (401, 403)

    def test_remove_item(self, host_session, cart):
        c = host_session.get(f"{BASE}/api/social/carts/{cart['cart_id']}").json()
        item = c["items"][0]
        r = host_session.delete(
            f"{BASE}/api/social/carts/{cart['cart_id']}/items/{item['item_id']}",
            timeout=15)
        assert r.status_code == 200
        assert len(r.json()["items"]) == len(c["items"]) - 1

    def test_checkout_group_cart(self, host_session, cart):
        r = host_session.post(
            f"{BASE}/api/social/carts/{cart['cart_id']}/checkout",
            json={"origin_url": BASE}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["checkout_url"].startswith("https://checkout.stripe.com/")
        assert j["total_cents"] > 0

    def test_empty_cart_checkout_400(self, host_session, free_uid):
        # Brand new cart with no items.
        c = host_session.post(f"{BASE}/api/social/carts",
                              json={"name": "TEST_P45 Empty",
                                    "members": []}, timeout=15).json()
        r = host_session.post(
            f"{BASE}/api/social/carts/{c['cart_id']}/checkout",
            json={"origin_url": BASE}, timeout=15)
        assert r.status_code == 400
        assert r.json().get("detail", {}).get("code") == "empty_cart"


# ═════════════════════════ Discover ═════════════════════════
class TestDiscover:
    def test_discover_shape(self, host_session):
        r = host_session.get(f"{BASE}/api/social/discover", timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("headline", "people", "shows", "moments", "clips"):
            assert k in j, f"missing key {k}"
        assert isinstance(j["headline"], str) and len(j["headline"]) > 0
        assert isinstance(j["people"], list)
        assert isinstance(j["shows"], list)
        assert isinstance(j["moments"], list)
        assert isinstance(j["clips"], list)


# ═════════════════════════ Translation ═════════════════════════
class TestTranslate:
    def test_langs(self, host_session):
        r = host_session.get(f"{BASE}/api/social/translate/langs", timeout=15)
        assert r.status_code == 200
        langs = r.json()["langs"]
        codes = {l["code"] for l in langs}
        for c in ("en", "hi", "ar", "es", "fr"):
            assert c in codes

    def test_translate_and_cache(self, host_session):
        text = "Good morning, welcome to RadioLife!"
        r1 = host_session.post(f"{BASE}/api/social/translate",
                               json={"text": text, "target_lang": "hi"},
                               timeout=60)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert j1["target_lang"] == "hi"
        assert isinstance(j1["translated"], str) and len(j1["translated"]) > 0
        assert j1["label"] == "हिन्दी"
        assert j1["cached"] in (True, False)  # first call MAY be cached if run before

        # Second identical call MUST be cached.
        r2 = host_session.post(f"{BASE}/api/social/translate",
                               json={"text": text, "target_lang": "hi"},
                               timeout=30)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["cached"] is True
        assert j2["translated"] == j1["translated"]

    def test_invalid_lang_falls_back_to_en(self, host_session):
        r = host_session.post(f"{BASE}/api/social/translate",
                              json={"text": "Hello world",
                                    "target_lang": "zz"}, timeout=60)
        assert r.status_code == 200
        assert r.json()["target_lang"] == "en"
