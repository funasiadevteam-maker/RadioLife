"""Phase 3 — RadioLife LIVE (livestream commerce) backend tests.

Tests /api/social/liveshows lifecycle, pinned products with host-only guards,
live chat, viewer heartbeat, and Stripe checkout URL generation.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

HOST_EMAIL = "demo@bigfm.dubai"
HOST_PASS = "DemoPass123!"
VIEWER_EMAIL = "freeuser@bigfm.dubai"
VIEWER_PASS = "FreePass123!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def host():
    return _login(HOST_EMAIL, HOST_PASS)


@pytest.fixture(scope="module")
def viewer():
    return _login(VIEWER_EMAIL, VIEWER_PASS)


@pytest.fixture(scope="module")
def show_ctx(host):
    """Create a show as host and yield the show payload."""
    r = host.post(f"{API}/social/liveshows",
                  json={"title": "TEST_Phase3 Live",
                        "business_name": "TEST_Biz",
                        "description": "phase3 pytest show"}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["show_id"].startswith("ls_")
    assert data["status"] == "live"
    assert "join_token" in data
    assert data["join_token"], "join_token should be present"
    assert "livekit_url" in data
    assert data["mode"] in ("mock", "live")
    yield data
    # cleanup — end show (idempotent-ish; ignore errors if already ended)
    try:
        host.post(f"{API}/social/liveshows/{data['show_id']}/end", timeout=10)
    except Exception:
        pass


# ─── Live listing ───────────────────────────────────────────────
def test_list_live_shows(host, show_ctx):
    r = host.get(f"{API}/social/liveshows?status=live", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "mode" in data
    ids = [x["show_id"] for x in data["items"]]
    assert show_ctx["show_id"] in ids


# ─── Show detail (host + viewer) ────────────────────────────────
def test_show_detail_is_host_true_for_host(host, show_ctx):
    r = host.get(f"{API}/social/liveshows/{show_ctx['show_id']}", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["is_host"] is True
    assert data["join_token"]
    assert data["viewer_count"] >= 1


def test_show_detail_is_host_false_for_viewer(viewer, show_ctx):
    r = viewer.get(f"{API}/social/liveshows/{show_ctx['show_id']}", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["is_host"] is False
    assert data["join_token"]


def test_show_not_found():
    s = _login(HOST_EMAIL, HOST_PASS)
    r = s.get(f"{API}/social/liveshows/ls_doesnotexist_xxxx", timeout=15)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "show_not_found"


# ─── Pin/unpin products (host-only) ─────────────────────────────
def test_pin_product_as_host_success(host, show_ctx):
    r = host.post(f"{API}/social/liveshows/{show_ctx['show_id']}/products",
                  json={"title": "TEST Paid Widget",
                        "price_cents": 1999, "offer": "-20%"}, timeout=15)
    assert r.status_code == 200
    prod = r.json()
    assert prod["product_id"].startswith("prod_")
    assert prod["price_cents"] == 1999
    show_ctx["_paid_product_id"] = prod["product_id"]


def test_pin_free_product_as_host(host, show_ctx):
    r = host.post(f"{API}/social/liveshows/{show_ctx['show_id']}/products",
                  json={"title": "TEST Free Freebie", "price_cents": 0}, timeout=15)
    assert r.status_code == 200
    show_ctx["_free_product_id"] = r.json()["product_id"]


def test_pin_product_403_for_non_host(viewer, show_ctx):
    r = viewer.post(f"{API}/social/liveshows/{show_ctx['show_id']}/products",
                    json={"title": "TEST viewer forbid", "price_cents": 500},
                    timeout=15)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_host"


def test_pinned_products_appear_in_detail(host, show_ctx):
    r = host.get(f"{API}/social/liveshows/{show_ctx['show_id']}", timeout=15)
    ids = [p["product_id"] for p in r.json().get("pinned_products", [])]
    assert show_ctx["_paid_product_id"] in ids
    assert show_ctx["_free_product_id"] in ids


def test_unpin_403_for_non_host(viewer, show_ctx):
    r = viewer.delete(
        f"{API}/social/liveshows/{show_ctx['show_id']}/products/{show_ctx['_free_product_id']}",
        timeout=15)
    assert r.status_code == 403


# ─── Chat ───────────────────────────────────────────────────────
def test_post_and_get_messages(host, viewer, show_ctx):
    r = host.post(f"{API}/social/liveshows/{show_ctx['show_id']}/messages",
                  json={"text": "TEST_host hello"}, timeout=15)
    assert r.status_code == 200
    m1 = r.json()
    assert m1["text"] == "TEST_host hello"
    after = m1["created_at"]
    time.sleep(0.3)
    r2 = viewer.post(f"{API}/social/liveshows/{show_ctx['show_id']}/messages",
                     json={"text": "TEST_viewer hi"}, timeout=15)
    assert r2.status_code == 200

    # GET all messages
    rg = viewer.get(f"{API}/social/liveshows/{show_ctx['show_id']}/messages", timeout=15)
    assert rg.status_code == 200
    texts = [x["text"] for x in rg.json()["items"]]
    assert "TEST_host hello" in texts
    assert "TEST_viewer hi" in texts

    # Incremental ?after=
    ri = viewer.get(f"{API}/social/liveshows/{show_ctx['show_id']}/messages?after={after}",
                    timeout=15)
    assert ri.status_code == 200
    texts_after = [x["text"] for x in ri.json()["items"]]
    assert "TEST_host hello" not in texts_after
    assert "TEST_viewer hi" in texts_after


# ─── Heartbeat / viewer count ───────────────────────────────────
def test_heartbeat_returns_viewer_count(viewer, show_ctx):
    r = viewer.post(f"{API}/social/liveshows/{show_ctx['show_id']}/heartbeat", timeout=15)
    assert r.status_code == 200
    assert "viewer_count" in r.json()
    assert r.json()["viewer_count"] >= 1


# ─── Checkout ───────────────────────────────────────────────────
def test_checkout_paid_returns_stripe_url(viewer, show_ctx):
    r = viewer.post(f"{API}/social/liveshows/{show_ctx['show_id']}/checkout",
                    json={"product_id": show_ctx["_paid_product_id"],
                          "origin_url": BASE_URL}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert data["checkout_url"], "expected Stripe checkout url"
    assert "stripe.com" in data["checkout_url"] or "checkout.stripe" in data["checkout_url"]
    assert data["session_id"]


def test_checkout_free_returns_free_status(viewer, show_ctx):
    r = viewer.post(f"{API}/social/liveshows/{show_ctx['show_id']}/checkout",
                    json={"product_id": show_ctx["_free_product_id"],
                          "origin_url": BASE_URL}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "free"
    assert data["checkout_url"] is None


def test_checkout_product_not_found(viewer, show_ctx):
    r = viewer.post(f"{API}/social/liveshows/{show_ctx['show_id']}/checkout",
                    json={"product_id": "prod_bogus_xxxx",
                          "origin_url": BASE_URL}, timeout=15)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "product_not_found"


# ─── End show (host-only) ───────────────────────────────────────
def test_end_show_403_for_non_host(viewer, show_ctx):
    r = viewer.post(f"{API}/social/liveshows/{show_ctx['show_id']}/end", timeout=15)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_host"


def test_end_show_as_host(host, show_ctx):
    r = host.post(f"{API}/social/liveshows/{show_ctx['show_id']}/end", timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "ended"
    # Detail should now reflect ended status
    rd = host.get(f"{API}/social/liveshows/{show_ctx['show_id']}", timeout=15)
    assert rd.status_code == 200
    assert rd.json()["status"] == "ended"
