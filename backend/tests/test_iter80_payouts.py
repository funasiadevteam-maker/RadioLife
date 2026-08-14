"""Iteration 80 — Payout Connect + Earnings trends parity tests.

Covers:
  BACKEND Payouts (owner-gated, cookie/Bearer):
    - POST /api/merchant/marketplace/connect/account
    - POST /api/merchant/marketplace/connect/onboarding-link
    - GET  /api/merchant/marketplace/connect/status
    - POST /api/merchant/marketplace/payout/withdraw   (guard: 409 not_payout_ready)
    - POST /api/merchant/marketplace/payout/instant    (guard: 400/402/409 no_instant_balance / not_connected)
    - Unauth → 401 on each
  BACKEND Earnings shape:
    - GET /api/merchant/marketplace/earnings returns daily[] (30 buckets), available_cents,
      paid_out_cents, memberships_sold, gross/fee/net_cents, month{}, transactions[].
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WEB_EMAIL = "test@bigfm.dubai"
WEB_PASS = "TestUser123!"
DEMO_EMAIL = "demo@bigfm.dubai"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def web_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": WEB_EMAIL, "password": WEB_PASS}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"web login failed {r.status_code}: {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def mobile_token():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20)
    if r.status_code != 200:
        pytest.skip(f"mobile demo login failed {r.status_code}: {r.text[:200]}")
    data = r.json()
    tok = data.get("session_token") or data.get("token") or data.get("access_token")
    if not tok:
        pytest.skip(f"no token in demo login: {list(data)}")
    return tok


@pytest.fixture(scope="module")
def mobile_headers(mobile_token):
    return {"Authorization": f"Bearer {mobile_token}"}


# ---------- unauthenticated 401 ----------
class TestUnauth:
    def test_connect_account_unauth(self):
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/connect/account", timeout=20)
        assert r.status_code in (401, 403), f"expected 401, got {r.status_code} {r.text[:200]}"

    def test_connect_onboarding_unauth(self):
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/connect/onboarding-link",
                          json={"platform": "web"}, timeout=20)
        assert r.status_code in (401, 403), r.status_code

    def test_connect_status_unauth(self):
        r = requests.get(f"{BASE_URL}/api/merchant/marketplace/connect/status", timeout=20)
        assert r.status_code in (401, 403), r.status_code

    def test_payout_withdraw_unauth(self):
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/payout/withdraw", timeout=20)
        assert r.status_code in (401, 403), r.status_code

    def test_payout_instant_unauth(self):
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/payout/instant", timeout=20)
        assert r.status_code in (401, 403), r.status_code

    def test_earnings_unauth(self):
        r = requests.get(f"{BASE_URL}/api/merchant/marketplace/earnings", timeout=20)
        assert r.status_code in (401, 403), r.status_code


# ---------- Web merchant (test@) ----------
class TestWebPayouts:
    def test_connect_account_returns_id(self, web_session):
        r = web_session.post(f"{BASE_URL}/api/merchant/marketplace/connect/account", timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("ok") is True
        acct = j.get("stripe_account_id")
        assert isinstance(acct, str) and acct.startswith("acct_"), f"bad acct: {acct}"

    def test_onboarding_link_returns_stripe_url(self, web_session):
        r = web_session.post(f"{BASE_URL}/api/merchant/marketplace/connect/onboarding-link",
                             json={"origin_url": BASE_URL, "platform": "web"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("ok") is True
        url = j.get("url", "")
        assert url.startswith("https://connect.stripe.com"), f"bad url: {url}"

    def test_connect_status_shape(self, web_session):
        r = web_session.get(f"{BASE_URL}/api/merchant/marketplace/connect/status", timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        # test@ already has an account but is NOT onboarded → connected=false
        assert j.get("has_account") is True
        assert j.get("connected") is False
        assert "payouts_enabled" in j
        assert "requirements_due" in j  # list

    def test_withdraw_guard_not_payout_ready(self, web_session):
        r = web_session.post(f"{BASE_URL}/api/merchant/marketplace/payout/withdraw", timeout=30)
        # test@ has an account but is not onboarded → 409 not_payout_ready
        assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text[:300]}"
        detail = r.json().get("detail")
        code = (detail or {}).get("code") if isinstance(detail, dict) else None
        assert code == "not_payout_ready", f"bad code: {detail}"

    def test_instant_guard_graceful(self, web_session):
        r = web_session.post(f"{BASE_URL}/api/merchant/marketplace/payout/instant", timeout=30)
        # No connected balance → graceful 409 no_instant_balance (may be 402 if stripe error)
        assert r.status_code in (409, 402, 400), f"got {r.status_code} {r.text[:300]}"
        # ensure a message/code exists
        detail = r.json().get("detail")
        assert detail, "expected non-empty error detail"


class TestEarningsShape:
    def _assert_shape(self, j):
        for k in ("memberships_sold", "gross_cents", "fee_cents", "net_cents",
                  "available_cents", "paid_out_cents", "month", "daily", "transactions"):
            assert k in j, f"missing {k}: keys={list(j)}"
        assert isinstance(j["daily"], list)
        assert len(j["daily"]) == 30, f"daily buckets = {len(j['daily'])}"
        for b in j["daily"]:
            assert set(b.keys()) >= {"date", "net_cents", "count"}
        # month sub-shape
        m = j["month"]
        for k in ("count", "gross_cents", "fee_cents", "net_cents"):
            assert k in m
        # net = gross - fee (all-time)
        assert j["net_cents"] == j["gross_cents"] - j["fee_cents"]

    def test_web_earnings_shape(self, web_session):
        r = web_session.get(f"{BASE_URL}/api/merchant/marketplace/earnings", timeout=30)
        assert r.status_code == 200, r.text[:300]
        self._assert_shape(r.json())

    def test_mobile_demo_earnings_has_sale(self, mobile_headers):
        r = requests.get(f"{BASE_URL}/api/merchant/marketplace/earnings",
                         headers=mobile_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        self._assert_shape(j)
        # demo@ has 1 real membership sale (net $17.99, fee $2.00, gross $19.99)
        assert j["memberships_sold"] >= 1, f"expected ≥1 sale, got {j['memberships_sold']}"
        assert j["net_cents"] >= 1799, j
        # at least one daily bucket should be non-zero
        assert any(b["net_cents"] > 0 for b in j["daily"]), "no bar in trends"


# ---------- Mobile demo user (demo@) — has NO Stripe account yet ----------
class TestMobilePayouts:
    def test_status_no_account_yet(self, mobile_headers):
        r = requests.get(f"{BASE_URL}/api/merchant/marketplace/connect/status",
                         headers=mobile_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        # If demo already ran through account creation, has_account may be True.
        # Either way connected must be False (can't complete onboarding automatically).
        assert j.get("connected") is False, j

    def test_withdraw_guard_mobile(self, mobile_headers):
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/payout/withdraw",
                          headers=mobile_headers, timeout=30)
        # demo may have no account (400 not_connected) OR account not onboarded (409 not_payout_ready)
        assert r.status_code in (400, 409), f"got {r.status_code} {r.text[:300]}"
        detail = r.json().get("detail")
        code = (detail or {}).get("code") if isinstance(detail, dict) else None
        assert code in ("not_connected", "not_payout_ready"), f"bad code: {detail}"

    def test_onboarding_link_mobile(self, mobile_headers):
        r = requests.post(f"{BASE_URL}/api/merchant/marketplace/connect/onboarding-link",
                          headers=mobile_headers,
                          json={"platform": "mobile"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        url = r.json().get("url", "")
        assert url.startswith("https://connect.stripe.com"), f"bad url: {url}"
