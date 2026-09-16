"""Soft-launch / Business Setup Mode — backend E2E test suite (iteration 144).

Covers:
  - GET /api/launch/status (mode OFF/ON, bypass reason)
  - PATCH/GET /api/admin/launch-settings (admin gating + validation)
  - POST /api/waitlist (email validation + dedupe + position)
  - GET /api/admin/waitlist
  - POST/GET/revoke /api/admin/preview-tokens
  - POST /api/launch/preview/redeem (invalid + valid → cookie)
  - Server-side gate on /api/shell/home: 423 for anon, 200 with token header,
    200 for admin cookie, open paths (auth, admin, merchant, waitlist, launch)
    never 423.
  - GET /api/merchant/soft-launch/offer + POST claim (idempotent)

IMPORTANT: The suite ALWAYS resets business_setup_mode_enabled=False in the
final `restore_mode` fixture so the live preview isn't left gated.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")
DEMO = ("demo@bigfm.dubai", "DemoPass123!")

CACHE_WAIT = 11  # launch_guard caches settings for ~10s


# ─────────────────────────── fixtures ──────────────────────────────
def _login(session: requests.Session, email: str, password: str) -> bool:
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": password}, timeout=15)
    return r.status_code == 200


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    if not _login(s, *ADMIN):
        pytest.skip("Admin login failed — cannot run soft-launch suite")
    return s


@pytest.fixture(scope="session")
def free_session():
    s = requests.Session()
    if not _login(s, *FREE):
        pytest.skip("Free user login failed")
    return s


@pytest.fixture(scope="session", autouse=True)
def restore_mode(admin_session):
    """Guarantee mode is OFF at the end of the run (even on failure)."""
    yield
    try:
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": False,
                                  "waitlist_enabled": True,
                                  "offer_months": 6}, timeout=15)
    except Exception:
        pass


# ─────────────────────────── public status ─────────────────────────
class TestLaunchStatusPublic:
    def test_status_mode_off_default(self, admin_session):
        # Ensure OFF first
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": False}, timeout=15)
        time.sleep(CACHE_WAIT)
        r = requests.get(f"{BASE_URL}/api/launch/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["business_setup_mode"] is False
        assert d["has_bypass"] is True
        assert isinstance(d.get("offer_months"), int)
        assert isinstance(d.get("waitlist_enabled"), bool)


# ─────────────────────────── admin gating ──────────────────────────
class TestAdminGating:
    def test_admin_settings_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/launch-settings", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_patch_admin_settings_requires_auth(self):
        r = requests.patch(f"{BASE_URL}/api/admin/launch-settings",
                           json={"business_setup_mode_enabled": True}, timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_non_admin_forbidden(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/admin/launch-settings", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_admin_get_settings(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/launch-settings", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("business_setup_mode_enabled", "waitlist_enabled", "offer_months"):
            assert k in d

    def test_patch_offer_months_clamped(self, admin_session):
        r = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"offer_months": 99}, timeout=15)
        assert r.status_code == 200
        assert r.json()["offer_months"] == 24
        r = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"offer_months": 0}, timeout=15)
        assert r.status_code == 200
        assert r.json()["offer_months"] == 1
        # restore
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"offer_months": 6}, timeout=15)

    def test_patch_empty_400(self, admin_session):
        r = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={}, timeout=15)
        assert r.status_code == 400


# ─────────────────────────── waitlist ──────────────────────────────
class TestWaitlist:
    def test_invalid_email(self):
        r = requests.post(f"{BASE_URL}/api/waitlist", json={"email": "not-an-email"}, timeout=15)
        assert r.status_code == 400

    def test_valid_email_and_dedupe(self):
        email = f"TEST_wl_{uuid.uuid4().hex[:8]}@example.com"
        r1 = requests.post(f"{BASE_URL}/api/waitlist",
                           json={"email": email, "city": "Dubai",
                                 "interests": ["music"]}, timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["ok"] is True
        assert isinstance(d1.get("position"), int) and d1["position"] > 0
        # Dedup — same email should not raise and total unchanged
        r2 = requests.post(f"{BASE_URL}/api/waitlist",
                           json={"email": email}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["position"] == d1["position"]

    def test_admin_waitlist_lists_entries(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/waitlist", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "total" in d and "items" in d
        assert isinstance(d["items"], list)


# ─────────────────────────── preview tokens ────────────────────────
class TestPreviewTokens:
    def test_create_list_revoke(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/preview-tokens",
                               json={"label": "TEST_pv", "max_uses": 3,
                                     "expires_days": 7}, timeout=15)
        assert r.status_code == 200, r.text
        tok = r.json()["token"]
        assert tok.startswith("pv_")

        lr = admin_session.get(f"{BASE_URL}/api/admin/preview-tokens", timeout=15)
        assert lr.status_code == 200
        assert any(x["token"] == tok for x in lr.json()["items"])

        rv = admin_session.post(
            f"{BASE_URL}/api/admin/preview-tokens/{tok}/revoke", timeout=15)
        assert rv.status_code == 200

        # revoked token can't be redeemed
        rd = requests.post(f"{BASE_URL}/api/launch/preview/redeem",
                           json={"token": tok}, timeout=15)
        assert rd.status_code == 400

    def test_redeem_invalid(self):
        r = requests.post(f"{BASE_URL}/api/launch/preview/redeem",
                          json={"token": "pv_does_not_exist"}, timeout=15)
        assert r.status_code == 400

    def test_redeem_valid_sets_cookie(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/preview-tokens",
                               json={"label": "TEST_pv_ok"}, timeout=15)
        tok = r.json()["token"]
        s = requests.Session()
        rr = s.post(f"{BASE_URL}/api/launch/preview/redeem",
                    json={"token": tok}, timeout=15)
        assert rr.status_code == 200
        assert rr.json().get("valid") is True
        assert s.cookies.get("rl_preview_token") == tok
        # cleanup
        admin_session.post(f"{BASE_URL}/api/admin/preview-tokens/{tok}/revoke", timeout=15)


# ─────────────────────────── SERVER-SIDE GATE ──────────────────────
class TestServerSideGate:
    """Core: 423 for anon on consumer paths; 200 for admin/token; open paths free."""

    @pytest.fixture(scope="class", autouse=True)
    def gate_on(self, admin_session):
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": True}, timeout=15)
        time.sleep(CACHE_WAIT)
        yield
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": False}, timeout=15)
        time.sleep(CACHE_WAIT)

    def test_status_shows_mode_on_no_bypass_anon(self):
        r = requests.get(f"{BASE_URL}/api/launch/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["business_setup_mode"] is True
        assert d["has_bypass"] is False

    def test_consumer_endpoint_423_anon(self):
        r = requests.get(f"{BASE_URL}/api/shell/home", timeout=15)
        assert r.status_code == 423, r.status_code
        body = r.json()
        # Detail may be a dict {code, message}
        detail = body.get("detail") or body
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "business_setup_mode"

    def test_consumer_endpoint_200_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/shell/home", timeout=20)
        assert r.status_code == 200

    def test_consumer_endpoint_200_with_token_header(self, admin_session):
        # Create a fresh token
        tr = admin_session.post(f"{BASE_URL}/api/admin/preview-tokens",
                                json={"label": "TEST_gate_hdr"}, timeout=15)
        tok = tr.json()["token"]
        r = requests.get(f"{BASE_URL}/api/shell/home",
                         headers={"X-Preview-Token": tok}, timeout=20)
        assert r.status_code == 200, r.status_code
        admin_session.post(f"{BASE_URL}/api/admin/preview-tokens/{tok}/revoke", timeout=15)

    def test_open_paths_never_423(self):
        # /api/auth/me → 401 (not authed) but NOT 423
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code != 423

        # /api/launch/status → 200
        assert requests.get(f"{BASE_URL}/api/launch/status", timeout=15).status_code == 200

        # /api/admin/launch-settings → 401/403 for anon (never 423)
        r = requests.get(f"{BASE_URL}/api/admin/launch-settings", timeout=15)
        assert r.status_code != 423
        assert r.status_code in (401, 403)

        # /api/waitlist → 400 invalid email (never 423)
        r = requests.post(f"{BASE_URL}/api/waitlist", json={"email": "x"}, timeout=15)
        assert r.status_code != 423

    def test_status_bypass_reason_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/launch/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["has_bypass"] is True
        assert d.get("bypass_reason") == "admin"


# ─────────────────────────── merchant offer ────────────────────────
class TestMerchantSoftLaunch:
    def test_offer_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/merchant/soft-launch/offer", timeout=15)
        assert r.status_code in (401, 403)

    def test_offer_shape(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/merchant/soft-launch/offer", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("offer_months", "has_business", "has_storefront",
                  "claimed", "commission_note"):
            assert k in d
        assert isinstance(d["offer_months"], int)

    def test_claim_idempotent(self, free_session):
        r1 = free_session.post(f"{BASE_URL}/api/merchant/soft-launch/claim", timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["ok"] is True
        assert "claim" in d1
        # Second call
        r2 = free_session.post(f"{BASE_URL}/api/merchant/soft-launch/claim", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("already") is True

        # After claim — offer.claimed True and free_until present
        of = free_session.get(f"{BASE_URL}/api/merchant/soft-launch/offer", timeout=15).json()
        assert of["claimed"] is True
        assert of["claim"] and of["claim"].get("free_until")

    def test_after_claim_free_user_has_business_bypass(self, admin_session, free_session):
        # Turn mode on briefly and confirm free_session (now business role) gets bypass
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": True}, timeout=15)
        try:
            time.sleep(CACHE_WAIT)
            r = free_session.get(f"{BASE_URL}/api/launch/status", timeout=15)
            assert r.status_code == 200
            d = r.json()
            assert d["business_setup_mode"] is True
            assert d["has_bypass"] is True
            assert d.get("bypass_reason") == "business"
        finally:
            admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"business_setup_mode_enabled": False}, timeout=15)
            time.sleep(CACHE_WAIT)
