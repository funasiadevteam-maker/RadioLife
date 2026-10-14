"""iter_207 Phase D — FUUSIC
Tests:
  1. GET /api/social/friends-nearby returns offer object with offer_id/title/label when
     a followed business has an active offer. For demo@bigfm.dubai (friends with Free Tester,
     follows Karak Cafe Dubai QA Demo), returns 1 item with offer.label='50% off Karak'.
  2. Empty case: freeuser@bigfm.dubai (no friends/follows) still returns 200 and {items: []}.
  3. Regression: scan-to-pay quote/authorize/capture flow at 100% BigPoints on biz_demo_karak
     — card_cents=0 → NO Stripe → receipt renders with subtotal/points_used/charge_cents=0.
"""
import os, time, pytest, requests
from pathlib import Path

def _load_env():
    p = Path("/app/frontend/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

BASE = _load_env()
assert BASE, "REACT_APP_BACKEND_URL not resolved"

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}
MERCH = {"email": "test@bigfm.dubai", "password": "TestUser123!"}
BIZ = "biz_demo_karak"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login {creds['email']} failed: {r.status_code} {r.text[:200]}"
    return s


# ─────────────── Feature 1: friends-nearby offer hook ──────────────
class TestFriendsNearbyOffer:
    def test_demo_sees_nearby_item_with_offer(self):
        s = _login(DEMO)
        r = s.get(f"{BASE}/api/social/friends-nearby", timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "items" in data and isinstance(data["items"], list), data
        assert len(data["items"]) >= 1, f"expected >=1 nearby item for demo, got {data}"
        # Find Karak Cafe item
        karak = next((it for it in data["items"] if it.get("business_id") == BIZ or "Karak" in (it.get("business_name") or "")), None)
        assert karak is not None, f"no Karak nearby item: {data['items']}"
        # Offer object shape
        assert "offer" in karak, karak
        assert karak["offer"] is not None, f"expected offer object, got None: {karak}"
        offer = karak["offer"]
        assert "offer_id" in offer and offer["offer_id"], offer
        assert "title" in offer, offer
        assert "label" in offer, offer
        # Spec label: '50% off Karak'
        assert offer["label"] == "50% off Karak", f"label mismatch: {offer}"

    def test_freeuser_empty_nearby_is_safe(self):
        s = _login(FREE)
        r = s.get(f"{BASE}/api/social/friends-nearby", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data == {"items": []}, f"expected empty items for freeuser, got {data}"


# ───────────── Feature 2: 100% BigPoints scan-to-pay regression ─────────────
class TestScanToPay100PctBigPoints:
    """End-to-end: resolve → quote(points_to_use=amount) → authorize → capture.
    biz_demo_karak has max_points_redemption_pct=100 → card_cents=0 → no Stripe call.
    """

    def test_full_points_receipt_flow(self):
        # Demo owns biz_demo_karak — use demo for both merchant QR gen and consumer flow
        c = _login(DEMO)
        qr = c.post(
            f"{BASE}/api/merchant/scan-to-pay/qr/generate",
            json={"merchant_id": BIZ, "amount_cents": 500},
            timeout=20,
        )
        assert qr.status_code == 200, f"QR gen: {qr.status_code} {qr.text[:300]}"
        token = qr.json().get("token")
        assert token, qr.json()
        rv = c.get(f"{BASE}/api/scan-to-pay/qr/{token}", timeout=20)
        assert rv.status_code == 200, rv.text[:300]
        resolved = rv.json()
        amount = resolved.get("amount_cents")
        assert amount == 500, resolved
        assert resolved.get("settings", {}).get("max_points_redemption_pct") == 100, resolved
        user_pts = resolved.get("user_points_balance") or 0
        assert user_pts >= 500, f"demo needs >=500 BigCoin for 100% test, has {user_pts}"

        # Quote full-points
        q = c.post(f"{BASE}/api/scan-to-pay/quote",
                   json={"qr_token": token, "points_to_use": 500, "tip_cents": 0},
                   timeout=20)
        assert q.status_code == 200, q.text[:300]
        quote = q.json()
        assert quote.get("card_cents") == 0, f"expected card_cents=0 (full points), got {quote}"
        assert quote.get("points_to_use") == 500, quote
        assert quote.get("subtotal_cents") == 500, quote

        # Authorize (no payment_method_id since card_cents=0)
        a = c.post(f"{BASE}/api/scan-to-pay/authorize",
                   json={"qr_token": token, "points_to_use": 500, "tip_cents": 0},
                   timeout=30)
        assert a.status_code == 200, f"authorize failed: {a.status_code} {a.text[:300]}"
        auth = a.json()
        tx_id = auth.get("transaction_id") or auth.get("tx_id")
        assert tx_id, auth
        assert auth.get("status") in ("authorized", "captured"), auth

        # Capture (if not already captured by authorize)
        if auth.get("status") != "captured":
            cap = c.post(f"{BASE}/api/scan-to-pay/capture",
                         json={"transaction_id": tx_id}, timeout=20)
            assert cap.status_code == 200, cap.text[:300]
            receipt = cap.json()
        else:
            receipt = auth

        # Receipt sanity — fields mobile UI reads
        assert receipt.get("subtotal_cents") == 500, receipt
        assert receipt.get("charge_cents") == 0, receipt  # AED 0.00 total paid
        assert receipt.get("points_used") == 500, receipt
        # bigcoin_earned should be 0 because card portion is 0 (points-only bill earns nothing)
        assert receipt.get("bigcoin_earned", 0) == 0, receipt
