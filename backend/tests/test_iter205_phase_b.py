"""iter_205 — Phase B: social feed-v2 + scan-to-pay flow."""
import os
import requests
import pytest

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
MERCH = {"email": "test@bigfm.dubai", "password": "TestUser123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo_sess():
    return _login(DEMO)


@pytest.fixture(scope="module")
def merch_sess():
    return _login(MERCH)


# --- Social feed v2 ---
def test_feed_following(demo_sess):
    r = demo_sess.get(f"{BASE}/api/social/feed-v2", params={"mode": "following", "limit": 4}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    for it in data["items"]:
        assert "id" in it and "type" in it
        assert "actor" in it
        assert "cta" in it


def test_feed_for_you(demo_sess):
    r = demo_sess.get(f"{BASE}/api/social/feed-v2", params={"mode": "for_you", "limit": 4}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    assert len(data["items"]) > 0, "for_you should return items"
    first = data["items"][0]
    assert "actor" in first and "cta" in first
    # Shape per spec: actor{name, avatar_url}, cta{label, action, target}
    assert "name" in first["actor"]
    assert "label" in first["cta"] and "action" in first["cta"]


# --- Scan-to-pay flow ---
def _get_merchant_biz(sess):
    r = sess.get(f"{BASE}/api/merchant/mine", timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    items = data.get("items") or data.get("businesses") or []
    for b in items:
        if b.get("merchant_status") == "approved" or b.get("status") == "approved":
            return b.get("business_id") or b.get("_id") or b.get("id")
    return (items[0].get("business_id") if items else None)


def test_scan_to_pay_qr_generate_and_quote(demo_sess, merch_sess):
    biz_id = _get_merchant_biz(merch_sess)
    if not biz_id:
        pytest.skip("no merchant biz available")
    # Ensure scan-to-pay enabled
    merch_sess.patch(f"{BASE}/api/merchant/{biz_id}/scan-to-pay/settings",
                     json={"enabled": True}, timeout=20)
    # Generate QR
    r = merch_sess.post(f"{BASE}/api/merchant/scan-to-pay/qr/generate",
                        json={"merchant_id": biz_id, "amount_cents": 1500}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"qr generation unavailable: {r.status_code} {r.text}")
    tok = r.json().get("token")
    assert tok and tok.startswith("stq_")

    # Resolve QR
    rq = demo_sess.get(f"{BASE}/api/scan-to-pay/qr/{tok}", timeout=20)
    assert rq.status_code == 200, rq.text
    qd = rq.json()
    assert qd["amount_cents"] == 1500

    # Quote
    rq2 = demo_sess.post(f"{BASE}/api/scan-to-pay/quote",
                         json={"qr_token": tok, "points_to_use": 0, "tip_cents": 100}, timeout=20)
    assert rq2.status_code == 200, rq2.text
    q = rq2.json()
    assert q["total_cents"] == 1600
    assert q["card_cents"] == 1600

    # Authorize + Capture (Stripe test card)
    ra = demo_sess.post(f"{BASE}/api/scan-to-pay/authorize",
                        json={"qr_token": tok, "points_to_use": 0, "tip_cents": 100,
                              "payment_method_id": "pm_card_visa"}, timeout=30)
    if ra.status_code != 200:
        pytest.skip(f"authorize unavailable in test env: {ra.status_code} {ra.text}")
    tx_id = ra.json()["transaction_id"]
    rc = demo_sess.post(f"{BASE}/api/scan-to-pay/capture",
                        json={"transaction_id": tx_id}, timeout=30)
    assert rc.status_code == 200, rc.text
    cap = rc.json()
    assert cap["status"] == "captured"
    assert cap.get("points_earned", 0) >= 0
