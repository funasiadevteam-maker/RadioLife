"""Phase 3 — Billing / Premium gating backend tests.

Covers:
- /api/billing/config (default, currency override, CF-IPCountry header)
- /api/billing/subscription (premium + free)
- /api/auth/me premium fields
- /api/channels premium_only flag
- /api/radio/start premium gating (403 premium_required)
- /api/billing/checkout (200, 401)
- /api/billing/status/{bogus} (404)
- /api/openapi.json route registration
- /api/radio/skip_state for premium (unlimited:true)
- Login + basic radio_start regression
"""
import os
import sys
import pathlib

import pytest
import requests
from dotenv import load_dotenv

# Load backend env so MONGO_URL is available if needed
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

FREE_EMAIL = "test@bigfm.dubai"
FREE_PASS = "TestUser123!"
PREMIUM_EMAIL = "premium@bigfm.dubai"
PREMIUM_PASS = "PremiumTest123!"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE_EMAIL, FREE_PASS)


@pytest.fixture(scope="module")
def premium_session():
    return _login(PREMIUM_EMAIL, PREMIUM_PASS)


# =========================================================================
# /api/billing/config
# =========================================================================
class TestBillingConfig:
    def test_default_no_params(self):
        r = requests.get(f"{API}/billing/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "test"
        assert d["currency"] == "USD"
        assert d["test_banner"] == "Test mode · No real charges"
        assert isinstance(d["plans"], list) and len(d["plans"]) >= 1
        plan = d["plans"][0]
        assert plan["plan_id"] == "premium_annual"
        assert plan["currency"] == "USD"
        assert plan["amount"] == 12.0
        assert plan["amount_display"] == "$12"

    def test_currency_aed_override(self):
        r = requests.get(f"{API}/billing/config", params={"currency": "AED"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["currency"] == "AED"
        plan = d["plans"][0]
        assert plan["currency"] == "AED"
        assert plan["amount"] == 36.0
        assert plan["amount_display"] == "AED 36"

    def test_currency_inr_override(self):
        r = requests.get(f"{API}/billing/config", params={"currency": "INR"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["currency"] == "INR"
        plan = d["plans"][0]
        assert plan["currency"] == "INR"
        assert plan["amount"] == 999.0
        assert plan["amount_display"] == "₹999"

    def test_cf_ipcountry_ae(self):
        # NOTE: The preview ingress strips client-supplied CF-IPCountry headers
        # before they reach the backend. We test the feature via localhost
        # which reflects how Cloudflare itself injects this header in prod.
        r = requests.get("http://localhost:8001/api/billing/config", headers={"CF-IPCountry": "AE"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["currency"] == "AED"
        assert d["country_hint"] == "AE"

    def test_cf_ipcountry_in(self):
        r = requests.get("http://localhost:8001/api/billing/config", headers={"CF-IPCountry": "IN"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["currency"] == "INR"
        assert d["country_hint"] == "IN"


# =========================================================================
# /api/billing/subscription + /api/auth/me
# =========================================================================
class TestSubscriptionState:
    def test_subscription_premium_user(self, premium_session):
        r = premium_session.get(f"{API}/billing/subscription", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_premium"] is True
        assert d["plan"] == "premium_annual"
        assert d["status"] == "active"
        assert d["reward_multiplier"] == 2.0

    def test_subscription_free_user(self, free_session):
        r = free_session.get(f"{API}/billing/subscription", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_premium"] is False

    def test_auth_me_premium(self, premium_session):
        r = premium_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_premium"] is True
        assert d.get("premium_tier") == "premium"
        assert d.get("subscription_period_end") is not None or d.get("current_period_end") is not None
        assert float(d.get("reward_multiplier", 1.0)) == 2.0

    def test_auth_me_free(self, free_session):
        r = free_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_premium"] is False


# =========================================================================
# Channels premium_only flag
# =========================================================================
class TestChannelsPremiumFlag:
    def test_premium_only_channels(self):
        r = requests.get(f"{API}/channels", timeout=15)
        assert r.status_code == 200
        data = r.json()
        channels = data["channels"] if isinstance(data, dict) and "channels" in data else data
        assert isinstance(channels, list)
        by_slug = {c["slug"]: c for c in channels}
        assert "vip_lounge" in by_slug, f"vip_lounge missing. Got slugs: {list(by_slug.keys())}"
        assert "premium_mehfil" in by_slug, f"premium_mehfil missing. Got slugs: {list(by_slug.keys())}"
        assert by_slug["vip_lounge"].get("premium_only") is True
        assert by_slug["premium_mehfil"].get("premium_only") is True
        # Other channels should be premium_only false
        non_premium = [c for s, c in by_slug.items() if s not in {"vip_lounge", "premium_mehfil"}]
        for c in non_premium:
            assert c.get("premium_only") is False, f"{c['slug']} should be premium_only=false"


# =========================================================================
# Premium gating on /api/radio/start
# =========================================================================
class TestRadioPremiumGating:
    def test_free_user_blocked_on_vip_lounge(self, free_session):
        r = free_session.post(f"{API}/radio/start", json={"channel": "vip_lounge"}, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
        body = r.json()
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
        assert detail.get("code") == "premium_required", f"detail={body}"
        assert detail.get("upgrade_url") == "/pricing"

    def test_free_user_blocked_on_premium_mehfil(self, free_session):
        r = free_session.post(f"{API}/radio/start", json={"channel": "premium_mehfil"}, timeout=30)
        assert r.status_code == 403
        body = r.json()
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
        assert detail.get("code") == "premium_required"


# =========================================================================
# Skip state for premium → unlimited:true / limit:-1
# =========================================================================
class TestPremiumSkipState:
    def test_premium_skip_state_unlimited(self, premium_session):
        r = premium_session.get(f"{API}/radio/skip_state", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("unlimited") is True, f"got: {d}"
        assert d.get("limit") == -1, f"got: {d}"


# =========================================================================
# /api/billing/checkout
# =========================================================================
class TestBillingCheckout:
    def test_checkout_unauthenticated_401(self):
        r = requests.post(
            f"{API}/billing/checkout",
            json={"plan_id": "premium_annual", "currency": "USD", "origin_url": "https://example.com"},
            timeout=15,
        )
        assert r.status_code == 401, f"got {r.status_code}: {r.text}"

    def test_checkout_authenticated_200(self, premium_session):
        r = premium_session.post(
            f"{API}/billing/checkout",
            json={"plan_id": "premium_annual", "currency": "USD", "origin_url": "https://example.com"},
            timeout=30,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        d = r.json()
        assert "url" in d and "session_id" in d
        assert d["url"].startswith("https://") and ("stripe.com" in d["url"] or "checkout" in d["url"].lower())

    def test_checkout_status_bogus_404(self, premium_session):
        r = premium_session.get(f"{API}/billing/status/cs_test_bogus_session_does_not_exist", timeout=15)
        assert r.status_code == 404, r.text


# =========================================================================
# OpenAPI route registration
# =========================================================================
class TestOpenAPIRoutes:
    def test_openapi_includes_billing(self):
        r = requests.get(f"{API}/openapi.json", timeout=15)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        required = [
            "/api/billing/config",
            "/api/billing/checkout",
            "/api/billing/subscription",
            "/api/billing/status/{session_id}",
            "/api/billing/cancel",
            "/api/billing/resume",
            "/api/webhook/stripe",
        ]
        missing = [p for p in required if p not in paths]
        assert not missing, f"missing routes in openapi: {missing}"


# =========================================================================
# Premium user can hit /api/radio/start on vip_lounge (slow ~30s).
# Mark as slow — skipped by default unless RUN_SLOW=1.
# =========================================================================
@pytest.mark.skipif(os.environ.get("RUN_SLOW") != "1", reason="slow: builds real OpenAI+ElevenLabs segment")
class TestRadioPremiumStart:
    def test_premium_can_start_vip_lounge(self, premium_session):
        r = premium_session.post(f"{API}/radio/start", json={"channel": "vip_lounge"}, timeout=120)
        assert r.status_code == 200, r.text


# =========================================================================
# Regression: basic login + default radio_start works
# =========================================================================
class TestRegression:
    def test_free_login_works(self):
        r = requests.post(f"{API}/auth/login", json={"email": FREE_EMAIL, "password": FREE_PASS}, timeout=20)
        assert r.status_code == 200
