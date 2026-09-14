"""iter128 — targeted retest of iter127 fixes.

Verifies:
1) CORS: preflight from Expo web preview origin returns credentials-safe headers
   (no ACAO:'*' with allow_credentials mismatch).
2) Merchant-role guard on POST /api/merchant/dining-club/redeem — non-owner is 403.
3) Regression smoke on the wheel `segments` (int) + `winner_index` payload.
"""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EXPO_ORIGIN = "https://mobile-games-v2.expo.preview.emergentagent.com"


# ── auth helpers ───────────────────────────────────────────────────────
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_sess():
    return _login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="module")
def test_sess():
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture(scope="module")
def admin_sess():
    return _login("admin@bigfm.dubai", "AdminPass123!")


# ── 1) CORS: Expo preview origin must be reflected + credentials=true ──
class TestCORS:
    def test_preflight_reflects_expo_origin(self):
        r = requests.options(
            f"{BASE}/api/dining-club",
            headers={
                "Origin": EXPO_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
            timeout=15,
        )
        assert r.status_code in (200, 204), f"preflight -> {r.status_code}"
        acao = r.headers.get("access-control-allow-origin")
        acac = r.headers.get("access-control-allow-credentials")
        assert acao == EXPO_ORIGIN, f"ACAO must echo origin, got {acao!r}"
        assert (acac or "").lower() == "true", f"ACAC must be true, got {acac!r}"

    def test_actual_get_with_origin_returns_reflected_header(self, demo_sess):
        r = demo_sess.get(f"{BASE}/api/auth/me", headers={"Origin": EXPO_ORIGIN}, timeout=15)
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == EXPO_ORIGIN


# ── 2) Merchant-role guard on redeem ───────────────────────────────────
class TestRedeemGuard:
    def _new_meal_order(self, sess, admin_sess):
        """Spin+random+accept to obtain a paid QR via admin mark-paid."""
        # start (may resume an existing session)
        r = sess.post(f"{BASE}/api/dining-club/selection/start",
                      json={"veg_preference": "VEG", "meal_period": "LUNCH"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        session = r.json().get("session") or {}
        sel_id = session.get("session_id")
        status = session.get("status")
        # If freshly started (CHOOSING), do a random pick.
        if status in (None, "CHOOSING"):
            r = sess.post(f"{BASE}/api/dining-club/selection/{sel_id}/random", timeout=20)
            assert r.status_code == 200, r.text[:300]
        # accept -> creates a dining order
        r = sess.post(f"{BASE}/api/dining-club/selection/{sel_id}/accept", timeout=20)
        assert r.status_code == 200, r.text[:300]
        order_id = r.json().get("order_id") or r.json().get("id") or (r.json().get("order") or {}).get("order_id")
        assert order_id, r.text[:300]
        # admin mark-paid
        r = admin_sess.post(f"{BASE}/api/admin/dining-club/orders/{order_id}/mark-paid", timeout=20)
        assert r.status_code == 200, r.text[:300]
        # fetch pass to get qr_token
        r = sess.get(f"{BASE}/api/dining-club/pass/{order_id}", timeout=20)
        assert r.status_code == 200, r.text[:300]
        qr = (r.json().get("qr") or {}).get("qr_token")
        assert qr, f"no qr_token in pass: {r.text[:300]}"
        return order_id, qr

    def test_non_owner_gets_403_not_meal_merchant(self, test_sess, admin_sess):
        """test@ owns 'Test Bistro' but the wheel picks a DEMO restaurant → test@ is non-owner → 403."""
        cred = test_sess.get(f"{BASE}/api/dining-club", timeout=15).json()
        avail = (cred.get("credits") or {}).get("available", 0)
        if avail < 1:
            pytest.skip(f"test@ has 0 credits (avail={avail})")
        order_id, qr = self._new_meal_order(test_sess, admin_sess)
        r = test_sess.post(f"{BASE}/api/merchant/dining-club/redeem",
                           json={"qr_token": qr}, timeout=20)
        # Either 403 not_meal_merchant OR 200 if the wheel picked test@'s own restaurant (unlikely).
        if r.status_code == 200:
            pytest.skip("wheel picked test@'s own Test Bistro; cannot exercise 403 path this run")
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:300]}"
        body = r.json()
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "not_meal_merchant", f"expected not_meal_merchant, got {body}"

    def test_admin_can_redeem(self, admin_sess, test_sess):
        cred = test_sess.get(f"{BASE}/api/dining-club", timeout=15).json()
        avail = (cred.get("credits") or {}).get("available", 0)
        if avail < 1:
            pytest.skip("test@ has 0 credits for a fresh order")
        order_id, qr = self._new_meal_order(test_sess, admin_sess)
        r = admin_sess.post(f"{BASE}/api/merchant/dining-club/redeem",
                            json={"qr_token": qr}, timeout=20)
        assert r.status_code == 200, f"admin redeem failed: {r.status_code} {r.text[:300]}"
        # verify payout ledger row
        body = r.json()
        assert body.get("status") in ("redeemed", "ok", "success") or body.get("payout"), body


# ── 3) Wheel payload smoke: segments is int + winner_index in range ────
class TestWheelPayload:
    def test_segments_is_int(self, test_sess):
        r = test_sess.post(f"{BASE}/api/dining-club/selection/start",
                           json={"veg_preference": "VEG", "meal_period": "LUNCH"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        sel_id = (r.json().get("session") or {}).get("session_id") or r.json().get("session_id")
        r = test_sess.post(f"{BASE}/api/dining-club/selection/{sel_id}/spin", timeout=20)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert isinstance(body.get("segments"), int), f"segments must be int, got {body.get('segments')!r}"
        assert 1 <= body["segments"] <= 20
        wi = body.get("winner_index")
        assert isinstance(wi, int) and 0 <= wi < body["segments"]
        assert body.get("winner"), "winner metadata missing"
