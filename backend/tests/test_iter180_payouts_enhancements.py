"""Iter180 — Payouts Hub enhancements: history, insights, cashout, weekly digest."""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ─────────────────── history ───────────────────
class TestPayoutHistory:
    def test_history_shape(self, demo_session):
        r = demo_session.get(f"{BASE}/api/payouts/history")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "accounts" in data
        assert isinstance(data["accounts"], list)
        # demo has a merchant business
        vtypes = [a["vendor_type"] for a in data["accounts"]]
        assert "merchant" in vtypes, f"expected merchant, got {vtypes}"
        for acct in data["accounts"]:
            assert "vendor_type" in acct
            assert "ref_id" in acct
            assert "transactions" in acct
            assert isinstance(acct["transactions"], list)
            for t in acct["transactions"]:
                for k in ("id", "date", "gross_cents", "fee_cents", "net_cents", "status", "ref"):
                    assert k in t, f"missing {k} in tx {t}"

    def test_history_requires_auth(self, anon_session):
        r = anon_session.get(f"{BASE}/api/payouts/history")
        assert r.status_code in (401, 403)


# ─────────────────── insights ───────────────────
class TestPayoutInsights:
    def test_insights_six_weeks(self, demo_session):
        r = demo_session.get(f"{BASE}/api/payouts/insights?weeks=6")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("window_weeks") == 6
        assert "accounts" in data and isinstance(data["accounts"], list)
        merchant_accts = [a for a in data["accounts"] if a["vendor_type"] == "merchant"]
        assert merchant_accts, "expected merchant account bucket"
        for acct in data["accounts"]:
            assert "weeks" in acct
            assert len(acct["weeks"]) == 6, f"expected 6 weeks, got {len(acct['weeks'])}"
            prev_start = None
            for w in acct["weeks"]:
                for k in ("week_start", "label", "sales_cents", "fees_cents", "net_cents"):
                    assert k in w
                # ISO date format YYYY-MM-DD
                assert len(w["week_start"]) == 10 and w["week_start"][4] == "-"
                if prev_start is not None:
                    assert w["week_start"] > prev_start, "weeks must be chronological"
                prev_start = w["week_start"]

    def test_insights_default_weeks(self, demo_session):
        r = demo_session.get(f"{BASE}/api/payouts/insights")
        assert r.status_code == 200
        assert r.json()["window_weeks"] == 6

    def test_insights_requires_auth(self, anon_session):
        r = anon_session.get(f"{BASE}/api/payouts/insights?weeks=6")
        assert r.status_code in (401, 403)


# ─────────────────── cashout ───────────────────
class TestCashout:
    def test_cashout_merchant_fallback(self, demo_session):
        r = demo_session.post(f"{BASE}/api/payouts/cashout",
                              json={"vendor_type": "merchant"})
        assert r.status_code == 200, r.text
        data = r.json()
        # Demo merchant has an account but charges_enabled=false → not ready
        # OR account is ready but standard-account fallback. Either way, must NOT 500.
        assert data.get("status") in ("fallback", "paid", "pending", "in_transit"), data
        if data.get("status") == "fallback":
            assert "dashboard_url" in data
            assert data["dashboard_url"].startswith("http")
            assert "reason" in data
            # Common: not_onboarded, standard_platform_payout_not_allowed, etc.

    def test_cashout_never_500(self, demo_session):
        # Repeat to ensure no error paths return 500
        for _ in range(2):
            r = demo_session.post(f"{BASE}/api/payouts/cashout",
                                  json={"vendor_type": "merchant"})
            assert r.status_code == 200, f"got {r.status_code}: {r.text}"
            body = r.json()
            # If fallback, must always have dashboard_url
            if body.get("status") == "fallback":
                assert body.get("dashboard_url"), body

    def test_cashout_invalid_vendor_type(self, demo_session):
        r = demo_session.post(f"{BASE}/api/payouts/cashout",
                              json={"vendor_type": "junk"})
        assert r.status_code == 422

    def test_cashout_requires_auth(self, anon_session):
        r = anon_session.post(f"{BASE}/api/payouts/cashout",
                              json={"vendor_type": "merchant"})
        assert r.status_code in (401, 403)


# ─────────────────── weekly digest ───────────────────
class TestWeeklyDigest:
    def test_admin_send_weekly_digest(self, admin_session):
        r = admin_session.post(f"{BASE}/api/admin/payouts/send-weekly-digest")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "provider_live" in data and isinstance(data["provider_live"], bool)
        assert "sent" in data and isinstance(data["sent"], int)
        assert "advisors" in data and "merchants" in data
        assert "results" in data and isinstance(data["results"], list)
        # No recent vendor activity in demo env
        # (per problem statement expect sent=0), just assert non-negative.
        assert data["sent"] >= 0

    def test_admin_send_weekly_digest_narrow_user(self, admin_session, demo_session):
        # Get demo user_id from /api/auth/me
        me = demo_session.get(f"{BASE}/api/auth/me").json()
        uid = me.get("user_id") or me.get("id")
        r = admin_session.post(
            f"{BASE}/api/admin/payouts/send-weekly-digest",
            params={"user_id": uid})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True

    def test_weekly_digest_non_admin_rejected(self, demo_session):
        r = demo_session.post(f"{BASE}/api/admin/payouts/send-weekly-digest")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_weekly_digest_anon_rejected(self, anon_session):
        r = anon_session.post(f"{BASE}/api/admin/payouts/send-weekly-digest")
        assert r.status_code in (401, 403)


# ─────────────────── regression ───────────────────
class TestRegression:
    def test_overview_still_works(self, demo_session):
        r = demo_session.get(f"{BASE}/api/payouts/overview")
        assert r.status_code == 200
        data = r.json()
        assert "accounts" in data
        assert "terms_version" in data
        assert "gate_on" in data

    def test_admin_vendor_fees_still_works(self, admin_session):
        r = admin_session.get(f"{BASE}/api/admin/vendor-fees")
        assert r.status_code == 200
        data = r.json()
        assert "advisor_pct" in data
        assert "merchant_pct" in data

    def test_vendor_payments_still_404(self, demo_session):
        r = demo_session.get(f"{BASE}/api/vendor-payments/overview")
        assert r.status_code == 404
