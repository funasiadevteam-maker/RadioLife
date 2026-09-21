"""Iteration 179 — Payouts Hub consolidation tests.

Covers:
 - GET/PUT /api/admin/vendor-fees (admin)
 - GET /api/payouts/overview (user)
 - POST /api/payouts/onboard (merchant)  agreement_required + real Stripe link
 - POST /api/payouts/refresh (merchant)  no_account path
 - Retired module: /api/vendor-payments/* must be 404
 - Onboarding gate on advisor booking checkout returns 409 advisor_payout_not_ready
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}


def _login(session, creds):
    r = session.post(f"{API}/auth/login", json=creds, timeout=15)
    return r


@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    r = _login(s, ADMIN)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text}")
    return s


@pytest.fixture(scope="module")
def demo_sess():
    s = requests.Session()
    r = _login(s, DEMO)
    if r.status_code != 200:
        pytest.skip(f"demo login failed: {r.status_code} {r.text}")
    return s


# ─── Admin vendor-fees ─────────────────────────────────────────────
class TestAdminVendorFees:
    def test_get_vendor_fees(self, admin_sess):
        r = admin_sess.get(f"{API}/admin/vendor-fees", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("advisor_pct", "merchant_pct", "require_onboarding", "terms_version"):
            assert k in d
        assert isinstance(d["advisor_pct"], int)
        assert isinstance(d["merchant_pct"], int)
        assert isinstance(d["require_onboarding"], bool)

    def test_put_vendor_fees_persists(self, admin_sess):
        body = {"advisor_pct": 15, "merchant_pct": 5, "require_onboarding": True}
        r = admin_sess.put(f"{API}/admin/vendor-fees", json=body, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["advisor_pct"] == 15
        assert d["merchant_pct"] == 5
        assert d["require_onboarding"] is True
        # Verify persistence via GET
        r2 = admin_sess.get(f"{API}/admin/vendor-fees", timeout=15)
        d2 = r2.json()
        assert d2["advisor_pct"] == 15
        assert d2["merchant_pct"] == 5
        assert d2["require_onboarding"] is True

    def test_non_admin_denied(self, demo_sess):
        r = demo_sess.get(f"{API}/admin/vendor-fees", timeout=15)
        assert r.status_code in (401, 403), r.text


# ─── Payouts overview ──────────────────────────────────────────────
class TestPayoutsOverview:
    def test_overview_demo_has_merchant(self, demo_sess):
        r = demo_sess.get(f"{API}/payouts/overview", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["eligible"] is True
        assert isinstance(d["accounts"], list)
        assert "gate_on" in d
        assert "terms_version" in d
        merchant = next((a for a in d["accounts"] if a["vendor_type"] == "merchant"), None)
        assert merchant is not None, f"no merchant account in {d}"
        assert merchant["fee_pct"] == 5
        assert "earnings" in merchant
        for k in ("sales_cents", "fees_cents", "paid_cents", "pending_cents"):
            assert k in merchant["earnings"]
        assert "agreement" in merchant

    def test_overview_requires_auth(self):
        r = requests.get(f"{API}/payouts/overview", timeout=15)
        assert r.status_code in (401, 403)


# ─── Retirement: vendor_payments must be 404 ───────────────────────
class TestVendorPaymentsRetired:
    def test_status_404(self, demo_sess):
        r = demo_sess.get(f"{API}/vendor-payments/status", timeout=15)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"

    def test_onboard_404(self, demo_sess):
        r = demo_sess.post(f"{API}/vendor-payments/onboard", json={}, timeout=15)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"


# ─── Onboard merchant flow ─────────────────────────────────────────
class TestOnboardMerchant:
    def test_refresh_no_account_when_never_onboarded(self, demo_sess):
        # Only meaningful when demo has NEVER onboarded; if seeded from
        # a prior test, we skip the strict assertion.
        overview = demo_sess.get(f"{API}/payouts/overview", timeout=15).json()
        m = next((a for a in overview["accounts"] if a["vendor_type"] == "merchant"), None)
        if m and m.get("has_account"):
            pytest.skip("merchant already has stripe_account_id; no_account path not applicable")
        r = demo_sess.post(f"{API}/payouts/refresh",
                           json={"vendor_type": "merchant"}, timeout=15)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail") or {}
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "no_account", r.text

    def test_onboard_agreement_required_first(self, demo_sess):
        overview = demo_sess.get(f"{API}/payouts/overview", timeout=15).json()
        m = next((a for a in overview["accounts"] if a["vendor_type"] == "merchant"), None)
        if m and m.get("has_account"):
            pytest.skip("merchant already has stripe account; agreement_required only fires on fresh accounts")
        r = demo_sess.post(f"{API}/payouts/onboard", json={
            "vendor_type": "merchant",
            "agreement_accepted": False,
            "origin_url": BASE_URL,
        }, timeout=20)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail") or {}
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "agreement_required", r.text

    def test_onboard_with_agreement_returns_link(self, demo_sess):
        r = demo_sess.post(f"{API}/payouts/onboard", json={
            "vendor_type": "merchant",
            "agreement_accepted": True,
            "origin_url": BASE_URL,
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d.get("onboarding_url", "").startswith("http")
        assert d["fee_pct"] == 5
        assert d.get("currency") in ("aed", "usd")


# ─── Advisor booking checkout gate ─────────────────────────────────
class TestAdvisorBookingGate:
    """When require_onboarding=true and the target advisor is NOT payout-ready,
    booking a paid reading must return 409 advisor_payout_not_ready. We only
    verify the gate — no Stripe checkout completion."""

    def test_gate_returns_409(self, demo_sess, admin_sess):
        # Ensure gate is ON.
        admin_sess.put(f"{API}/admin/vendor-fees",
                       json={"require_onboarding": True}, timeout=15)
        # Find an advisor with an active service.
        adv_list = demo_sess.get(f"{API}/social/dreams/advisors", timeout=15)
        if adv_list.status_code != 200:
            pytest.skip(f"advisor list unavailable: {adv_list.status_code}")
        data = adv_list.json()
        advisors = data.get("items") if isinstance(data, dict) else data
        if not isinstance(advisors, list) or not advisors:
            pytest.skip("no advisors seeded")
        # Pick first advisor with a service
        target = None
        for a in advisors:
            aid = a.get("advisor_id") or a.get("id")
            if not aid:
                continue
            det = demo_sess.get(f"{API}/social/dreams/advisors/{aid}", timeout=15)
            if det.status_code != 200:
                continue
            services = det.json().get("services") or []
            active_svcs = [s for s in services if s.get("active", True)
                           and int(s.get("price_cents", 0)) > 0]
            if active_svcs:
                target = (aid, active_svcs[0])
                break
        if not target:
            pytest.skip("no advisor with paid services")
        aid, svc = target
        sid = svc.get("service_id") or svc.get("id")
        body = {
            "advisor_id": aid,
            "service_id": sid,
            "origin_url": BASE_URL,
        }
        r = demo_sess.post(f"{API}/social/dreams/bookings/checkout",
                           json=body, timeout=25)
        # Gate expected — 409 with advisor_payout_not_ready. Accept
        # alternate payloads (some builds wrap under detail.code).
        if r.status_code == 409:
            body_j = r.json()
            code = (body_j.get("detail") or {}).get("code") \
                if isinstance(body_j.get("detail"), dict) \
                else body_j.get("code")
            assert code == "advisor_payout_not_ready", body_j
        else:
            # Not 409 — surface for debugging but do not silently pass.
            pytest.fail(f"expected 409 advisor_payout_not_ready, got {r.status_code}: {r.text[:400]}")
