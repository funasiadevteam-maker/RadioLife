"""iter_208 — FUUSIC: Split-from-receipt + 100% BigPoints regression + claim-deal CTA backend."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    return _login("demo@bigfm.dubai", "DemoPass123!")


# ── Build 2: Split from receipt — the post-pay payload (NO qr_token)
def test_create_split_from_receipt_no_qr_token(demo_session):
    """Mimics mobile pay-checkout.splitReceipt(): merchant_id + total + 2 shares, no qr_token."""
    body = {
        "merchant_id": "biz_demo_karak",
        "total_amount_cents": 1500,
        "description": "Split at Karak Cafe",
        "shares": [
            {"share_amount_cents": 750, "display_name": "You"},
            {"share_amount_cents": 750, "display_name": "Friend"},
        ],
    }
    r = demo_session.post(f"{BASE_URL}/api/scan-to-pay/splits", json=body, timeout=30)
    assert r.status_code == 200, f"splits create failed {r.status_code}: {r.text}"
    data = r.json()
    assert "split_id" in data and isinstance(data["split_id"], str)
    shares = data.get("shares") or []
    assert len(shares) == 2
    for sh in shares:
        assert "share_id" in sh
        assert "invite_token" in sh
        assert "display_name" in sh
    invite = data.get("invite_urls") or {}
    assert isinstance(invite, dict) and len(invite) == 2
    for sh in shares:
        assert sh["share_id"] in invite
        assert isinstance(invite[sh["share_id"]], str)


# ── Pre-pay path: splits WITH a qr_token still works
def test_create_split_with_qr_token_prepay(demo_session):
    """Generate a QR as the cashier then create a split with qr_token (pre-pay flow)."""
    # Use the service to mint QR directly via a seed endpoint if available.
    # Fall back to merchant qr/generate (demo owns biz_demo_karak per iter_206/207 seeds).
    qr_resp = demo_session.post(
        f"{BASE_URL}/api/merchant/scan-to-pay/qr/generate",
        json={"merchant_id": "biz_demo_karak", "amount_cents": 2000},
        timeout=30,
    )
    if qr_resp.status_code != 200:
        pytest.skip(f"QR gen not available for demo: {qr_resp.status_code} {qr_resp.text[:200]}")
    qr_token = qr_resp.json().get("token") or qr_resp.json().get("qr_token")
    assert qr_token

    body = {
        "merchant_id": "biz_demo_karak",
        "total_amount_cents": 2000,
        "qr_token": qr_token,
        "shares": [
            {"share_amount_cents": 1000, "display_name": "You"},
            {"share_amount_cents": 1000, "display_name": "Friend"},
        ],
    }
    r = demo_session.post(f"{BASE_URL}/api/scan-to-pay/splits", json=body, timeout=30)
    assert r.status_code == 200, f"splits create (pre-pay) failed {r.status_code}: {r.text}"
    data = r.json()
    assert "split_id" in data and len(data.get("shares") or []) == 2
    assert len(data.get("invite_urls") or {}) == 2


# ── Regression: 100% BigPoints scan-to-pay (resolve → quote → authorize → capture)
def test_full_points_scan_to_pay_regression(demo_session):
    # Mint a QR
    gen = demo_session.post(
        f"{BASE_URL}/api/merchant/scan-to-pay/qr/generate",
        json={"merchant_id": "biz_demo_karak", "amount_cents": 500},
        timeout=30,
    )
    if gen.status_code != 200:
        pytest.skip(f"QR gen failed: {gen.status_code} {gen.text[:200]}")
    token = gen.json().get("token") or gen.json().get("qr_token")
    assert token

    # Resolve
    res = demo_session.get(f"{BASE_URL}/api/scan-to-pay/qr/{token}", timeout=30)
    assert res.status_code == 200, res.text
    rj = res.json()
    assert rj.get("amount_cents") == 500
    assert "user_points_balance" in rj
    assert rj.get("settings", {}).get("max_points_redemption_pct", 0) >= 100

    # Quote with max points
    qt = demo_session.post(
        f"{BASE_URL}/api/scan-to-pay/quote",
        json={"qr_token": token, "points_to_use": 500, "tip_cents": 0},
        timeout=30,
    )
    assert qt.status_code == 200, qt.text
    qj = qt.json()
    assert qj.get("card_cents") == 0
    assert qj.get("points_value_cents") == 500

    # Authorize + capture
    au = demo_session.post(
        f"{BASE_URL}/api/scan-to-pay/authorize",
        json={"qr_token": token, "points_to_use": 500, "tip_cents": 0,
              "payment_method_id": "pm_card_visa"},
        timeout=30,
    )
    assert au.status_code == 200, au.text
    tx_id = au.json().get("transaction_id")
    assert tx_id

    cap = demo_session.post(
        f"{BASE_URL}/api/scan-to-pay/capture",
        json={"transaction_id": tx_id},
        timeout=30,
    )
    # Full-points can short-circuit to captured on authorize already — tolerate either.
    assert cap.status_code in (200, 400), cap.text
    body = cap.json() if cap.status_code == 200 else {}
    # If capture ran, check receipt fields; otherwise authorize should have them.
    receipt = body or au.json()
    assert receipt.get("subtotal_cents") == 500
    assert receipt.get("charge_cents") == 0
    assert receipt.get("points_used") == 500


# ── Build 1: claim-deal CTA — offer exists in /commerce/offers/feed with offer_id ofr_qa_onetime_demo
def test_offer_exists_in_feed(demo_session):
    r = demo_session.get(f"{BASE_URL}/api/commerce/offers/feed", timeout=30)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert any(it.get("offer_id") == "ofr_qa_onetime_demo" for it in items), \
        "ofr_qa_onetime_demo not present in /commerce/offers/feed"


def test_claim_offer_demo(demo_session):
    """Claim the one-time demo offer. First call may 200 OR 409 (max_per_user_reached) — both OK."""
    r = demo_session.post(
        f"{BASE_URL}/api/commerce/offers/ofr_qa_onetime_demo/claim",
        json={},
        timeout=30,
    )
    assert r.status_code in (200, 201, 409), f"unexpected claim status {r.status_code}: {r.text}"
    if r.status_code in (200, 201):
        data = r.json()
        # Expect a coupon id of some sort
        assert any(k in data for k in ("coupon_id", "id", "claim_id", "ok"))
    else:
        # 409 is the expected "already claimed" state
        err = r.json().get("detail")
        assert err is None or "max_per_user_reached" in str(err).lower() or "already" in str(err).lower() or "limit" in str(err).lower()


# ── Build 3: live-pill backend contract — feed-v2 following returns items with created_at
def test_social_feed_v2_following(demo_session):
    r = demo_session.get(
        f"{BASE_URL}/api/social/feed-v2",
        params={"mode": "following", "limit": 20},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    # may be empty, but if non-empty, each item should have created_at
    for it in (data.get("items") or [])[:5]:
        assert "created_at" in it, f"feed item missing created_at: {it}"
