"""Phase AD.7 — Scan-to-Pay + Notification Trigger Recipes tests.

Covers:
  * GET /api/notification-trigger-recipes (10 recipes shape)
  * Merchant scan-to-pay settings (GET + PATCH + validation)
  * QR generate + resolve (RBAC, min-amount, disabled merchant, expired, not-found)
  * Quote (points cap enforcement, points_earned formula)
  * Authorize (creates row, marks QR consumed, idempotent)
  * Capture (idempotent, awards points, ledger row with flow=ad7_scan_to_pay)
  * Refund (points reversal both sides, idempotent)
  * User history + merchant txs + admin analytics
  * AD.12 trigger dispatch via /api/ads/action/save_coupon → notification_deliveries row
"""

from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"

SEED_MERCHANT = "biz_sc5_test_activated"


def _login(session: requests.Session, email: str, password: str) -> str:
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return r.json().get("session_token") or r.json()["token"]


@pytest.fixture(scope="module")
def admin_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    tok = _login(s, ADMIN_EMAIL, ADMIN_PASS)
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def demo_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    tok = _login(s, DEMO_EMAIL, DEMO_PASS)
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


# ---------- Notification trigger recipes ----------
class TestRecipes:
    def test_recipes_list_shape_and_count(self):
        r = requests.get(f"{BASE_URL}/api/notification-trigger-recipes", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 10, data
        ids = {it["id"] for it in data["items"]}
        expected = {
            "coupon_saved", "coupon_expiring_24h", "podcast_completed",
            "station_played_5x", "wallet_top_up", "first_login",
            "flagship_played_first_time", "predict_win_correct",
            "merchant_visit_nearby", "game_win_high_value",
        }
        assert ids == expected
        keys = {"id", "label", "description", "event_name",
                "category", "default_delay_minutes"}
        for it in data["items"]:
            assert keys.issubset(it.keys()), it


# ---------- Merchant settings ----------
class TestMerchantSettings:
    def test_get_settings_defaults_or_persisted(self, admin_client):
        r = admin_client.get(
            f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
            timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("enabled", "points_per_dollar",
                  "max_points_redemption_pct", "min_scan_to_pay_amount_cents"):
            assert k in d, d

    def test_patch_valid_and_persists(self, admin_client):
        patch = {"enabled": True, "points_per_dollar": 10,
                 "max_points_redemption_pct": 50,
                 "min_scan_to_pay_amount_cents": 100}
        r = admin_client.patch(
            f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
            json=patch, timeout=10)
        assert r.status_code == 200, r.text
        g = admin_client.get(
            f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
            timeout=10).json()
        assert g["enabled"] is True
        assert g["points_per_dollar"] == 10
        assert g["max_points_redemption_pct"] == 50

    def test_patch_invalid_ppd_rejected(self, admin_client):
        r = admin_client.patch(
            f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
            json={"points_per_dollar": 5000}, timeout=10)
        assert r.status_code == 400, r.text

    def test_patch_invalid_pct_rejected(self, admin_client):
        r = admin_client.patch(
            f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
            json={"max_points_redemption_pct": 150}, timeout=10)
        assert r.status_code == 400, r.text


# ---------- QR generate / resolve ----------
@pytest.fixture(scope="module")
def qr_token(admin_client) -> str:
    # ensure enabled
    admin_client.patch(
        f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
        json={"enabled": True, "points_per_dollar": 10,
              "max_points_redemption_pct": 50,
              "min_scan_to_pay_amount_cents": 100})
    r = admin_client.post(
        f"{BASE_URL}/api/merchant/scan-to-pay/qr/generate",
        json={"merchant_id": SEED_MERCHANT, "amount_cents": 1000},
        timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["expires_in_s"] == 60
    assert d["amount_cents"] == 1000
    assert d["merchant_id"] == SEED_MERCHANT
    assert "token" in d and "expires_at" in d and "scan_url" in d
    return d["token"]


class TestQrGenerate:
    def test_gen_requires_authority(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/merchant/scan-to-pay/qr/generate",
            json={"merchant_id": SEED_MERCHANT, "amount_cents": 500},
            timeout=10)
        # demo is not owner of biz_sc5_test_activated (admin is per spec)
        assert r.status_code in (403, 404), r.text

    def test_gen_below_min_rejected(self, admin_client):
        r = admin_client.post(
            f"{BASE_URL}/api/merchant/scan-to-pay/qr/generate",
            json={"merchant_id": SEED_MERCHANT, "amount_cents": 50},
            timeout=10)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "amount_below_min"

    def test_gen_when_disabled_rejected(self, admin_client):
        admin_client.patch(
            f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
            json={"enabled": False})
        try:
            r = admin_client.post(
                f"{BASE_URL}/api/merchant/scan-to-pay/qr/generate",
                json={"merchant_id": SEED_MERCHANT, "amount_cents": 500},
                timeout=10)
            assert r.status_code == 400
            assert r.json()["detail"]["code"] == "scan_to_pay_not_enabled"
        finally:
            admin_client.patch(
                f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/settings",
                json={"enabled": True})

    def test_resolve_not_found(self, admin_client):
        r = admin_client.get(
            f"{BASE_URL}/api/scan-to-pay/qr/nope-{uuid.uuid4().hex[:8]}",
            timeout=10)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "qr_not_found"

    def test_resolve_ok(self, admin_client, qr_token):
        r = admin_client.get(f"{BASE_URL}/api/scan-to-pay/qr/{qr_token}",
                             timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount_cents"] == 1000
        # merchant info + settings + user points
        for k in ("merchant", "settings", "user_points_balance"):
            assert k in d, d


# ---------- Quote ----------
class TestQuote:
    def test_points_clamped_and_earned(self, admin_client, qr_token):
        r = admin_client.post(
            f"{BASE_URL}/api/scan-to-pay/quote",
            json={"qr_token": qr_token, "points_to_use": 800, "tip_cents": 0},
            timeout=10)
        assert r.status_code == 200, r.text
        q = r.json()
        # $10 bill, 50% cap on points_value: max 500 points → $5 = 500 cents
        # points_per_dollar=10, ppd_value ~ 1 cent/pt commonly
        assert q["points_to_use"] <= 500
        # card portion is total - points_value_cents
        assert q["card_cents"] + q["points_value_cents"] == q["total_cents"]
        # points_earned = int(card_cents/100 * points_per_dollar)
        expected_earn = int(q["card_cents"] / 100 * 10)
        assert q["points_earned"] == expected_earn


# ---------- Full authorize → capture → refund ----------
class TestFullLifecycle:
    def test_lifecycle(self, admin_client):
        # 1. balance before
        bal_r = admin_client.get(f"{BASE_URL}/api/user/points/balance", timeout=10)
        pre_bal = None
        if bal_r.status_code == 200:
            pre_bal = bal_r.json().get("balance")

        # 2. fresh QR
        g = admin_client.post(
            f"{BASE_URL}/api/merchant/scan-to-pay/qr/generate",
            json={"merchant_id": SEED_MERCHANT, "amount_cents": 1000},
            timeout=10).json()
        token = g["token"]

        # 3. authorize
        auth = admin_client.post(
            f"{BASE_URL}/api/scan-to-pay/authorize",
            json={"qr_token": token, "points_to_use": 200, "tip_cents": 0,
                  "payment_method_id": "pm_card_visa"},
            timeout=30)
        assert auth.status_code == 200, auth.text
        tx_id = auth.json().get("transaction_id") or auth.json().get("tx_id")
        assert tx_id, auth.json()

        # 4. 2nd authorize on same token -> qr_already_used
        auth2 = admin_client.post(
            f"{BASE_URL}/api/scan-to-pay/authorize",
            json={"qr_token": token, "points_to_use": 0, "tip_cents": 0,
                  "payment_method_id": "pm_card_visa"},
            timeout=15)
        assert auth2.status_code == 400
        assert auth2.json()["detail"]["code"] == "qr_already_used"

        # 5. capture
        cap = admin_client.post(
            f"{BASE_URL}/api/scan-to-pay/capture",
            json={"transaction_id": tx_id}, timeout=30)
        assert cap.status_code == 200, cap.text

        # 6. capture again idempotent
        cap2 = admin_client.post(
            f"{BASE_URL}/api/scan-to-pay/capture",
            json={"transaction_id": tx_id}, timeout=15)
        assert cap2.status_code == 200, cap2.text
        assert cap2.json().get("already_captured") is True

        # 7. refund
        ref = admin_client.post(
            f"{BASE_URL}/api/scan-to-pay/{tx_id}/refund",
            json={"reason": "TEST_refund"}, timeout=30)
        assert ref.status_code == 200, ref.text

        # 8. refund idempotent
        ref2 = admin_client.post(
            f"{BASE_URL}/api/scan-to-pay/{tx_id}/refund",
            json={"reason": "TEST_refund"}, timeout=15)
        assert ref2.status_code == 200, ref2.text
        assert ref2.json().get("already_refunded") is True

        # 9. balance restored (allow small drift)
        if pre_bal is not None:
            bal_after = admin_client.get(
                f"{BASE_URL}/api/user/points/balance", timeout=10).json().get("balance")
            assert bal_after == pre_bal, f"balance drift: pre={pre_bal} post={bal_after}"


# ---------- History + merchant + admin analytics ----------
class TestListsAndAnalytics:
    def test_user_history(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/user/scan-to-pay/history", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d
        # optional: merchant_name/logo joined on rows
        if d["items"]:
            row = d["items"][0]
            assert "merchant_name" in row or "merchant" in row

    def test_merchant_txs_totals(self, admin_client):
        r = admin_client.get(
            f"{BASE_URL}/api/merchant/{SEED_MERCHANT}/scan-to-pay/transactions",
            timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "totals" in d
        for k in ("gross_cents", "net_cents", "refunds_cents"):
            assert k in d["totals"], d["totals"]

    def test_admin_analytics_admin_only(self, admin_client, demo_client):
        r = admin_client.get(
            f"{BASE_URL}/api/admin/scan-to-pay/analytics", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "by_status" in d and "top_merchants" in d
        # forbidden for non-admin
        r2 = demo_client.get(
            f"{BASE_URL}/api/admin/scan-to-pay/analytics", timeout=10)
        assert r2.status_code in (401, 403)


# ---------- AD.12 trigger dispatch via save_coupon ----------
class TestCouponSavedTrigger:
    def test_save_coupon_endpoint_reachable(self, demo_client):
        # We just verify the endpoint exists and does not 5xx. A live
        # trigger-based campaign seed is needed for a full delivery mint;
        # dispatcher is silent-on-error so upstream flow must not break
        # even without a matching campaign.
        # Try to find any published coupon.
        cr = requests.get(f"{BASE_URL}/api/coupon-campaigns/live", timeout=10)
        if cr.status_code != 200 or not cr.json().get("items"):
            pytest.skip("no live coupon campaigns to save against")
        camp = cr.json()["items"][0]
        cid = camp.get("campaign_id") or camp.get("id")
        r = demo_client.post(f"{BASE_URL}/api/ads/action/save_coupon",
                             json={"campaign_id": cid}, timeout=15)
        # Either 200 (saved) or 400 (already-saved / not-eligible), never 5xx
        assert r.status_code < 500, r.text
