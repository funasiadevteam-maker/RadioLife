"""Iteration 93 — RadioLife Ads Public API (/api/v1) end-to-end tests.

Covers:
  * v1 meta endpoints (root / openapi / docs / /me auth)
  * Admin issuance of partner + sandbox API key
  * Full sandbox lifecycle: whoami, products, advertiser, top-up, campaign, report
  * Guardrails: unbookable product 409, cross-partner 404, garbage bearer 401
  * OAuth2 client-credentials: token issue, scoped call, missing scope 403,
    bad secret 401
  * Self-serve portal endpoints under session auth
"""
import os
import uuid
import requests
import pytest

def _read_env(path, key):
    try:
        for line in open(path):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
            or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
DEV = ("demo@bigfm.dubai", "DemoPass123!")


# ── helpers ────────────────────────────────────────────────────────
def login(session: requests.Session, email: str, password: str) -> str:
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token")
    assert tok
    session.headers["Authorization"] = f"Bearer {tok}"
    return tok


@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    login(s, *ADMIN)
    return s


@pytest.fixture(scope="module")
def dev_sess():
    s = requests.Session()
    login(s, *DEV)
    return s


@pytest.fixture(scope="module")
def sandbox_key(admin_sess):
    """Admin creates a partner + sandbox API key."""
    r = admin_sess.post(f"{BASE_URL}/api/admin/partner-api/partners",
                        json={"name": f"TEST_partner_{uuid.uuid4().hex[:6]}",
                              "contact_email": "test-partner@example.com"},
                        timeout=20)
    assert r.status_code == 200, r.text
    partner_id = r.json()["partner"]["partner_id"]

    r = admin_sess.post(
        f"{BASE_URL}/api/admin/partner-api/partners/{partner_id}/keys",
        json={"environment": "sandbox", "label": "iter93-sandbox"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["api_key"].startswith("rlk_test_")
    assert data["environment"] == "SANDBOX"
    return {"partner_id": partner_id, "api_key": data["api_key"],
            "key_id": data["key_id"], "scopes": data["scopes"]}


@pytest.fixture(scope="module")
def v1(sandbox_key):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {sandbox_key['api_key']}"
    return s


# ── meta ───────────────────────────────────────────────────────────
class TestV1Meta:
    def test_root_public(self):
        r = requests.get(f"{BASE_URL}/api/v1/", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["api"] == "RadioLife Ads API"
        assert j["version"]

    def test_openapi_public(self):
        r = requests.get(f"{BASE_URL}/api/v1/openapi.json", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "paths" in j and "/oauth/token" in j["paths"]

    def test_docs_public(self):
        r = requests.get(f"{BASE_URL}/api/v1/docs", timeout=15)
        assert r.status_code == 200
        assert "swagger" in r.text.lower()

    def test_me_requires_bearer(self):
        r = requests.get(f"{BASE_URL}/api/v1/me", timeout=15)
        assert r.status_code == 401

    def test_garbage_bearer_401(self):
        r = requests.get(f"{BASE_URL}/api/v1/me",
                         headers={"Authorization": "Bearer garbage"}, timeout=15)
        assert r.status_code == 401


# ── auth end-to-end ───────────────────────────────────────────────
class TestSandboxLifecycle:
    _advertiser_id = None
    _campaign_id = None

    def test_whoami(self, v1, sandbox_key):
        r = v1.get(f"{BASE_URL}/api/v1/me", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["partner_id"] == sandbox_key["partner_id"]
        assert j["environment"] == "SANDBOX"
        assert j["credential_type"] == "api_key"

    def test_products_catalog(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/products", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert len(j["items"]) == 9
        bookable = [p for p in j["items"] if p.get("bookable")]
        keys = sorted(p["key"] for p in bookable)
        assert keys == ["audio_preroll", "display_banner", "sponsored_game"]

    def test_create_advertiser_sandbox_autoactive(self, v1):
        r = v1.post(f"{BASE_URL}/api/v1/advertisers",
                    json={"name": "TEST_AdvIter93",
                          "contact_email": "adv@example.com"}, timeout=20)
        assert r.status_code == 201, r.text
        adv = r.json()["advertiser"]
        assert adv["status"] == "active"
        TestSandboxLifecycle._advertiser_id = adv["advertiser_id"]

    def test_topup_sandbox_instant_credit(self, v1):
        aid = TestSandboxLifecycle._advertiser_id
        r = v1.post(f"{BASE_URL}/api/v1/advertisers/{aid}/funding/topup",
                    json={"amount_cents": 50000}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["credited"] is True and j["sandbox"] is True
        assert j["budget_available_cents"] >= 50000

    def test_create_campaign_audio_preroll_active(self, v1):
        aid = TestSandboxLifecycle._advertiser_id
        r = v1.post(f"{BASE_URL}/api/v1/campaigns",
                    json={"advertiser_id": aid, "product": "audio_preroll",
                          "name": "TEST_camp_iter93",
                          "budget_total_cents": 10000, "pricing_model": "cpm",
                          "cpm_bid_cents": 500,
                          "creative": {"audio_url": "https://example.com/a.mp3"}},
                    timeout=20)
        assert r.status_code == 201, r.text
        camp = r.json()["campaign"]
        assert camp["status"] == "active"
        TestSandboxLifecycle._campaign_id = camp["campaign_id"]

    def test_campaign_report(self, v1):
        aid = TestSandboxLifecycle._advertiser_id
        cid = TestSandboxLifecycle._campaign_id
        r = v1.get(f"{BASE_URL}/api/v1/campaigns/{cid}/report",
                   params={"advertiser_id": aid}, timeout=20)
        assert r.status_code == 200, r.text


# ── guardrails ────────────────────────────────────────────────────
class TestGuardrails:
    def test_unbookable_product_409(self, v1):
        # First create an advertiser (sandbox auto-active)
        adv = v1.post(f"{BASE_URL}/api/v1/advertisers",
                      json={"name": "TEST_guard", "contact_email": "g@x.com"},
                      timeout=20).json()["advertiser"]
        aid = adv["advertiser_id"]
        v1.post(f"{BASE_URL}/api/v1/advertisers/{aid}/funding/topup",
                json={"amount_cents": 5000}, timeout=20)
        r = v1.post(f"{BASE_URL}/api/v1/campaigns",
                    json={"advertiser_id": aid,
                          "product": "sponsorship_predict_win",
                          "name": "nope", "budget_total_cents": 5000},
                    timeout=20)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "product_not_bookable_via_api"

    def test_cross_partner_advertiser_404(self, admin_sess, v1):
        # Create a SECOND partner + key, its own advertiser, then try with first key.
        r = admin_sess.post(f"{BASE_URL}/api/admin/partner-api/partners",
                            json={"name": "TEST_p2", "contact_email": "p2@x.com"},
                            timeout=20)
        pid2 = r.json()["partner"]["partner_id"]
        r = admin_sess.post(
            f"{BASE_URL}/api/admin/partner-api/partners/{pid2}/keys",
            json={"environment": "sandbox"}, timeout=20)
        k2 = r.json()["api_key"]
        s2 = requests.Session()
        s2.headers["Authorization"] = f"Bearer {k2}"
        adv = s2.post(f"{BASE_URL}/api/v1/advertisers",
                      json={"name": "TEST_p2adv", "contact_email": "a@p2.com"},
                      timeout=20).json()["advertiser"]
        # First partner's key trying to read partner 2's advertiser → 404
        r = v1.get(f"{BASE_URL}/api/v1/advertisers/{adv['advertiser_id']}", timeout=15)
        assert r.status_code == 404


# ── OAuth2 client credentials ─────────────────────────────────────
class TestOAuth2:
    _client_id = None
    _client_secret = None

    def test_selfserve_create_partner_and_oauth_client(self, dev_sess):
        # any logged-in user can self-serve
        r = dev_sess.post(f"{BASE_URL}/api/partner/account",
                          json={"name": "TEST_selfserve",
                                "contact_email": "self@x.com"}, timeout=20)
        assert r.status_code == 200, r.text
        r = dev_sess.post(f"{BASE_URL}/api/partner/oauth-clients",
                          json={"environment": "sandbox",
                                "scopes": ["catalog:read", "advertisers:read"],
                                "label": "iter93-oauth"},
                          timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["client_id"].startswith("rlc_test_")
        assert "client_secret" in j
        TestOAuth2._client_id = j["client_id"]
        TestOAuth2._client_secret = j["client_secret"]

    def test_token_issue_and_scoped_call(self):
        r = requests.post(f"{BASE_URL}/api/v1/oauth/token",
                          data={"grant_type": "client_credentials",
                                "client_id": TestOAuth2._client_id,
                                "client_secret": TestOAuth2._client_secret},
                          timeout=20)
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        # scoped: catalog:read allowed, campaigns:write NOT
        h = {"Authorization": f"Bearer {tok}"}
        r = requests.get(f"{BASE_URL}/api/v1/products", headers=h, timeout=15)
        assert r.status_code == 200
        r = requests.post(f"{BASE_URL}/api/v1/campaigns", headers=h,
                          json={"advertiser_id": "x", "product": "audio_preroll",
                                "name": "x", "budget_total_cents": 100},
                          timeout=15)
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "insufficient_scope"

    def test_bad_client_secret_401(self):
        r = requests.post(f"{BASE_URL}/api/v1/oauth/token",
                          data={"grant_type": "client_credentials",
                                "client_id": TestOAuth2._client_id,
                                "client_secret": "wrong"}, timeout=15)
        assert r.status_code == 401


# ── self-serve portal ─────────────────────────────────────────────
class TestSelfServePortal:
    def test_account_get_and_keys_lifecycle(self, dev_sess):
        r = dev_sess.get(f"{BASE_URL}/api/partner/account", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["exists"] is True
        assert "api_keys" in j and "oauth_clients" in j
        # Create + revoke key
        r = dev_sess.post(f"{BASE_URL}/api/partner/keys",
                          json={"environment": "sandbox",
                                "label": "iter93-portal"}, timeout=15)
        assert r.status_code == 200
        kid = r.json()["key_id"]
        r = dev_sess.post(f"{BASE_URL}/api/partner/keys/{kid}/revoke", timeout=15)
        assert r.status_code == 200 and r.json()["revoked"] is True
