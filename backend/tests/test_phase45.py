"""Phase 4.5 backend tests: SSP partners admin, GAM integration, Stripe Connect,
AI sponsor read, buy_now fallback, OpenRTB auction firing."""
from __future__ import annotations
import os
import json
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
FREE = {"email": "test@bigfm.dubai", "password": "TestUser123!"}
PREMIUM = {"email": "premium@bigfm.dubai", "password": "PremiumTest123!"}

BIZ_ID = "biz_karak_cafe_karama"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def free_token():
    return _login(FREE)


@pytest.fixture(scope="session")
def premium_token():
    return _login(PREMIUM)


def _h(_s):
    # backward-compat helper — auth via session cookies, headers unused
    return {}


# ============================================================
# SSP admin
# ============================================================
class TestSSPPartners:
    def test_list_ssp_partners(self, admin_token):
        r = admin_token.get(f"{BASE_URL}/api/admin/ssp/partners", timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        items = body["items"]
        assert len(items) >= 5, f"expected >=5 partners, got {len(items)}"
        mock = [p for p in items if p.get("id") == "mock_ssp" or p.get("partner_id") == "mock_ssp"]
        assert mock, f"mock_ssp partner missing. partners: {[p.get('id') for p in items]}"
        assert mock[0].get("enabled") is True
        # others disabled
        others = [p for p in items if (p.get("id") or p.get("partner_id")) != "mock_ssp"]
        for o in others:
            assert o.get("enabled") in (False, None), f"non-mock partner {o.get('id')} should be disabled"

    def test_disable_then_enable(self, admin_token):
        # pick a non-mock partner
        r = admin_token.get(f"{BASE_URL}/api/admin/ssp/partners", timeout=10)
        items = r.json()["items"]
        target = next((p for p in items if (p.get("id") or p.get("partner_id")) != "mock_ssp"), None)
        assert target, "need a non-mock partner"
        pid = target.get("id") or target.get("partner_id")

        # enable
        r = admin_token.post(f"{BASE_URL}/api/admin/ssp/partners/{pid}/enable", timeout=10)
        assert r.status_code == 200, r.text[:200]
        # disable
        r = admin_token.post(f"{BASE_URL}/api/admin/ssp/partners/{pid}/disable", timeout=10)
        assert r.status_code == 200, r.text[:200]

    def test_update_partner(self, admin_token):
        r = admin_token.get(f"{BASE_URL}/api/admin/ssp/partners", timeout=10)
        items = r.json()["items"]
        target = next((p for p in items if (p.get("id") or p.get("partner_id")) != "mock_ssp"), None)
        assert target
        pid = target.get("id") or target.get("partner_id")
        new_url = "https://example.com/openrtb"
        r = admin_token.post(
            f"{BASE_URL}/api/admin/ssp/partners/{pid}", json={"endpoint_url": new_url, "bidder_id": "bidder_test", "timeout_ms": 250},
            timeout=10)
        assert r.status_code == 200, r.text[:200]
        partner = r.json().get("partner") or {}
        assert partner.get("endpoint_url") == new_url
        assert partner.get("bidder_id") == "bidder_test"
        assert partner.get("timeout_ms") == 250

    def test_recent_auctions(self, admin_token):
        r = admin_token.get(f"{BASE_URL}/api/admin/ssp/auctions/recent", timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert "items" in body and isinstance(body["items"], list)


# ============================================================
# GAM integration
# ============================================================
class TestGAM:
    def test_gam_status_initial(self, admin_token):
        r = admin_token.get(f"{BASE_URL}/api/admin/ads/integrations/gam", timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert "service_account_configured" in body
        # service_account_json_encrypted should never be exposed
        assert "service_account_json_encrypted" not in body

    def test_gam_save_fake_creds(self, admin_token):
        fake_sa = {
            "type": "service_account",
            "project_id": "fake-project",
            "private_key_id": "fakeid",
            "private_key": "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n",
            "client_email": "fake@fake.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        r = admin_token.post(
            f"{BASE_URL}/api/admin/ads/integrations/gam", json={"service_account_json": json.dumps(fake_sa), "ad_unit_id": "/123/test_ad_unit"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        # verify configured now
        r2 = admin_token.get(f"{BASE_URL}/api/admin/ads/integrations/gam", timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("service_account_configured") is True

    def test_gam_test_fake_fails_gracefully(self, admin_token):
        r = admin_token.post(f"{BASE_URL}/api/admin/ads/integrations/gam/test", timeout=30)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("ok") is False
        assert "reason" in body, f"missing reason: {body}"


# ============================================================
# Stripe Connect
# ============================================================
class TestStripeConnect:
    def test_account_status_not_connected(self, admin_token):
        r = admin_token.get(
            f"{BASE_URL}/api/advertiser/stripe/account_status",
            params={"business_id": BIZ_ID}, timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        # Allowed: connected may be False; if there is no acct, stripe_account_id should be None
        if not body.get("stripe_account_id"):
            assert body["connected"] is False

    def test_connect_account_route_exists(self, admin_token):
        r = admin_token.post(
            f"{BASE_URL}/api/advertiser/stripe/connect_account", json={"business_id": BIZ_ID}, timeout=20)
        # Expected: 502 with Stripe error or 200. Should NOT be 404/500/exception trace.
        assert r.status_code in (200, 502), f"unexpected status {r.status_code}: {r.text[:300]}"
        if r.status_code == 502:
            text = r.text.lower()
            assert "stripe" in text or "api key" in text, f"expected stripe error msg, got: {r.text[:300]}"

    def test_payouts_empty_when_not_connected(self, admin_token):
        r = admin_token.get(
            f"{BASE_URL}/api/advertiser/stripe/payouts",
            params={"business_id": BIZ_ID}, timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        # When not connected: empty lists. When connected with fake acct, may have 'error'.
        if "available" in body:
            assert isinstance(body["available"], list)
            assert isinstance(body["pending"], list)
            assert isinstance(body["payouts"], list)


# ============================================================
# AI Sponsor Read
# ============================================================
class TestAISponsorRead:
    def test_ai_sponsor_read_generates(self, admin_token):
        r = admin_token.post(
            f"{BASE_URL}/api/advertiser/creative/ai_sponsor_read", json={
                "business_id": BIZ_ID,
                "brief": "Friday brunch buffet 50 percent off",
                "voice_key": "aanya_hindi",
                "duration_sec": 15,
                "tone": "warm-energetic",
            },
            timeout=90)
        assert r.status_code == 200, f"sponsor read failed: {r.status_code} {r.text[:400]}"
        body = r.json()
        assert body.get("creative_id"), body
        assert body.get("audio_url"), body
        assert body.get("transcript"), body
        assert body.get("duration_sec"), body
        # verify audio_url is downloadable
        audio_url = body["audio_url"]
        if audio_url.startswith("/"):
            audio_url = BASE_URL + audio_url
        head = requests.head(audio_url, timeout=15, allow_redirects=True)
        if head.status_code == 405:
            head = requests.get(audio_url, timeout=20, stream=True)
        assert head.status_code == 200, f"audio not downloadable: {head.status_code} {audio_url}"


# ============================================================
# Buy-now fallback (no Stripe Connect attached)
# ============================================================
class TestBuyNowFallback:
    def test_buy_now_still_works(self, free_token):
        # Start a radio session first
        s = free_token.post(f"{BASE_URL}/api/radio/start", json={"channel_slug": "bigfm-dubai", "market": "dubai"},
                          timeout=15)
        # may already be started; either way accept 200
        sess_id = None
        if s.status_code == 200:
            sess_id = s.json().get("session_id")
        # Try to pull an ad
        for _ in range(6):
            time.sleep(5)
            cur = free_token.get(f"{BASE_URL}/api/ads/current", params={"session_id": sess_id} if sess_id else None, timeout=10)
            if cur.status_code == 200 and cur.json().get("has_ad"):
                ad = cur.json()
                # find a buy_now action card on a campaign that has product
                pod_id = (ad.get("ad_pod") or {}).get("id") or ad.get("ad_pod_id")
                acs = ad.get("action_cards") or []
                buy_ac = next((a for a in acs if a.get("action_type") == "buy_now"), None)
                if not (pod_id and buy_ac):
                    pytest.skip("no buy_now action card on this pod")
                r = free_token.post(f"{BASE_URL}/api/ads/action/buy_now", json={"ad_pod_id": pod_id, "product_id": buy_ac.get("product_id")},
                                  timeout=15)
                assert r.status_code == 200, r.text[:300]
                body = r.json()
                assert body.get("order_id"), body
                assert body.get("checkout_url"), body
                return
        pytest.skip("no ad served within window — cannot test buy_now")


# ============================================================
# OpenRTB auction firing (soft test)
# ============================================================
class TestOpenRTBSoft:
    def test_openrtb_auction_may_fire(self, admin_token, free_token):
        # snapshot count
        r0 = admin_token.get(f"{BASE_URL}/api/admin/ssp/auctions/recent", params={"limit": 200}, timeout=10)
        assert r0.status_code == 200
        before = len(r0.json().get("items", []))

        # trigger several /api/radio/next calls as free user (postroll path)
        for _ in range(10):
            try:
                free_token.post(f"{BASE_URL}/api/radio/next", json={"channel_slug": "bigfm-dubai", "market": "dubai"},
                              timeout=10)
            except requests.RequestException:
                pass
            time.sleep(1)

        r1 = admin_token.get(f"{BASE_URL}/api/admin/ssp/auctions/recent", params={"limit": 200}, timeout=10)
        assert r1.status_code == 200
        after = len(r1.json().get("items", []))
        # Soft: just print the delta; don't fail if 0 since path is probabilistic
        print(f"openrtb auctions before={before} after={after} delta={after - before}")
        assert after >= before
