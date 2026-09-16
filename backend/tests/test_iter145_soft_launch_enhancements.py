"""Soft-launch enhancements — iteration 145.

Covers the three follow-ups to iter144:
  1. BUSINESS DIRECTORY: GET /api/launch/businesses
  2. REFERRAL WAITLIST: POST /api/waitlist with ?ref=CODE, GET /api/waitlist/position
  3. LAUNCH COUNTDOWN + launch email: launch_at on status/settings,
     ON->OFF transition triggers _notify_waitlist_launched (idempotent),
     manual POST /api/admin/launch/notify-waitlist.

IMPORTANT: The final restore_mode fixture always leaves mode OFF and does NOT
clobber launch_at so the live preview isn't left gated.  We use
@example.com throwaway emails only (Mailgun is LIVE on radiolife.app).
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
CACHE_WAIT = 11  # launch_guard caches settings ~10s


def _login(session: requests.Session, email: str, password: str) -> bool:
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": password}, timeout=15)
    return r.status_code == 200


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    if not _login(s, *ADMIN):
        pytest.skip("Admin login failed")
    return s


@pytest.fixture(scope="session", autouse=True)
def restore_mode(admin_session):
    """Always leave mode OFF at end so live preview is not gated."""
    yield
    try:
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": False}, timeout=15)
    except Exception:
        pass


# ────────────── 1) BUSINESS DIRECTORY ──────────────
class TestBusinessDirectory:
    def test_public_shape(self):
        r = requests.get(f"{BASE_URL}/api/launch/businesses", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "total" in d and "items" in d
        assert isinstance(d["total"], int)
        assert isinstance(d["items"], list)
        # Each item shape
        for it in d["items"][:5]:
            assert "name" in it
            assert "category_label" in it and isinstance(it["category_label"], str)
            assert "claimed" in it and isinstance(it["claimed"], bool)
            assert "image" in it  # may be None

    def test_excludes_test_qa_names(self):
        r = requests.get(f"{BASE_URL}/api/launch/businesses?limit=60", timeout=20)
        assert r.status_code == 200
        for it in r.json()["items"]:
            name = it.get("name", "")
            assert "TEST_" not in name
            assert "QA Demo" not in name
            assert "Test Shop" not in name

    def test_limit_clamped(self):
        # Above 60 -> clamped to 60
        r = requests.get(f"{BASE_URL}/api/launch/businesses?limit=999", timeout=20)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 60
        # Below 1 -> clamped up to 1 (defensive)
        r2 = requests.get(f"{BASE_URL}/api/launch/businesses?limit=0", timeout=20)
        assert r2.status_code == 200
        # We just need it not to error; server clamps to 1..60
        assert len(r2.json()["items"]) >= 1 or r2.json()["total"] == 0


# ────────────── 2) REFERRAL WAITLIST ──────────────
class TestReferralWaitlist:
    def test_first_signup_returns_ref_and_share_path(self):
        email = f"TEST_ref_owner_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/waitlist",
                          json={"email": email}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d.get("already") is False
        code = d.get("ref_code")
        assert isinstance(code, str) and len(code) >= 4
        assert d.get("share_path") == f"/?ref={code}"
        assert isinstance(d.get("position"), int) and d["position"] > 0
        assert d.get("referrals") == 0
        assert isinstance(d.get("total"), int)

    def test_referral_credits_owner_and_improves_position(self):
        owner_email = f"TEST_ref_o_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/waitlist",
                          json={"email": owner_email}, timeout=15)
        assert r.status_code == 200
        owner = r.json()
        owner_code = owner["ref_code"]
        assert owner["referrals"] == 0
        initial_pos = owner["position"]

        # Two referred signups
        for _ in range(2):
            new_email = f"TEST_ref_f_{uuid.uuid4().hex[:8]}@example.com"
            rr = requests.post(f"{BASE_URL}/api/waitlist",
                               json={"email": new_email, "ref": owner_code}, timeout=15)
            assert rr.status_code == 200

        # Query owner position — referrals should be 2 and position <= initial
        gp = requests.get(f"{BASE_URL}/api/waitlist/position",
                          params={"code": owner_code}, timeout=15)
        assert gp.status_code == 200
        p = gp.json()
        assert p["referrals"] >= 2, p
        assert p["position"] <= initial_pos, (
            f"position should not degrade after referrals; "
            f"before={initial_pos} after={p['position']}")

    def test_resubmit_same_email_no_double_credit(self):
        owner_email = f"TEST_ref_owner2_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/waitlist", json={"email": owner_email}, timeout=15)
        owner_code = r.json()["ref_code"]

        friend_email = f"TEST_ref_friend2_{uuid.uuid4().hex[:8]}@example.com"
        r1 = requests.post(f"{BASE_URL}/api/waitlist",
                           json={"email": friend_email, "ref": owner_code}, timeout=15)
        assert r1.status_code == 200
        assert r1.json().get("already") is False

        # Owner's referrals now:
        p1 = requests.get(f"{BASE_URL}/api/waitlist/position",
                          params={"code": owner_code}, timeout=15).json()
        first_refs = p1["referrals"]

        # Resubmit SAME friend email with the ref — should return already:true and NOT re-credit
        r2 = requests.post(f"{BASE_URL}/api/waitlist",
                           json={"email": friend_email, "ref": owner_code}, timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("already") is True

        p2 = requests.get(f"{BASE_URL}/api/waitlist/position",
                          params={"code": owner_code}, timeout=15).json()
        assert p2["referrals"] == first_refs, (
            f"double-credit detected: {first_refs} -> {p2['referrals']}")

    def test_invalid_email_400(self):
        r = requests.post(f"{BASE_URL}/api/waitlist",
                          json={"email": "not-an-email"}, timeout=15)
        assert r.status_code == 400

    def test_position_missing_code_400(self):
        r = requests.get(f"{BASE_URL}/api/waitlist/position", timeout=15)
        assert r.status_code == 400

    def test_position_unknown_code_fallback(self):
        r = requests.get(f"{BASE_URL}/api/waitlist/position",
                         params={"code": "ZZZZZZ"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["referrals"] == 0
        assert d["position"] == d["total"]


# ────────────── 3) LAUNCH COUNTDOWN + status.launch_at ──────────────
class TestLaunchAt:
    def test_status_includes_launch_at_key(self):
        r = requests.get(f"{BASE_URL}/api/launch/status", timeout=15)
        assert r.status_code == 200
        assert "launch_at" in r.json()  # may be None or ISO string

    def test_patch_launch_at_valid_iso(self, admin_session):
        iso = "2027-01-15T09:00:00+00:00"
        r = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"launch_at": iso}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("launch_at", "").startswith("2027-01-15T09:00:00")
        # Reflected on public status
        s = requests.get(f"{BASE_URL}/api/launch/status", timeout=15).json()
        assert s.get("launch_at", "").startswith("2027-01-15T09:00:00")

    def test_patch_launch_at_clear(self, admin_session):
        r = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"launch_at": ""}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("launch_at") is None

    def test_patch_launch_at_bad_400(self, admin_session):
        r = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"launch_at": "not-a-date"}, timeout=15)
        assert r.status_code == 400
        body = r.json()
        detail = body.get("detail") or body
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "bad_launch_at"

    def test_patch_launch_at_non_admin(self):
        # anon
        r = requests.patch(f"{BASE_URL}/api/admin/launch-settings",
                           json={"launch_at": "2027-01-01T00:00:00Z"}, timeout=15)
        assert r.status_code in (401, 403)


# ────────────── 4) LAUNCH EMAIL on ON->OFF transition ──────────────
class TestLaunchEmailOnTransition:
    def test_notify_endpoint_requires_admin(self):
        r = requests.post(f"{BASE_URL}/api/admin/launch/notify-waitlist", timeout=15)
        assert r.status_code in (401, 403)

    def test_on_to_off_triggers_notify_and_is_idempotent(self, admin_session):
        # 1) Ensure OFF baseline
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": False}, timeout=15)
        time.sleep(2)

        # 2) Add a fresh @example.com waitlist entry (throwaway) so notify has work
        # NOTE: server lowercases email on write, so compare in lowercase.
        marker = f"TEST_launch_notify_{uuid.uuid4().hex[:8]}@example.com".lower()
        wr = requests.post(f"{BASE_URL}/api/waitlist",
                           json={"email": marker}, timeout=15)
        assert wr.status_code == 200

        # 3) Flip ON
        r_on = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                   json={"business_setup_mode_enabled": True}, timeout=15)
        assert r_on.status_code == 200
        assert r_on.json()["business_setup_mode_enabled"] is True

        try:
            time.sleep(2)
            # 4) Flip OFF — triggers _notify_waitlist_launched (background)
            r_off = admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                        json={"business_setup_mode_enabled": False}, timeout=15)
            assert r_off.status_code == 200
            assert r_off.json()["business_setup_mode_enabled"] is False

            # 5) Give the background task a moment to run
            time.sleep(4)

            # 6) Confirm our TEST entry is now launched_notified via admin waitlist
            aw = admin_session.get(f"{BASE_URL}/api/admin/waitlist", timeout=15).json()
            entry = next((x for x in aw["items"] if x.get("email") == marker), None)
            assert entry is not None, "TEST entry missing from admin waitlist"
            # The background task sets launched_notified=True
            assert entry.get("launched_notified") is True, (
                f"launched_notified flag not set on TEST entry: {entry}")

            # 7) Idempotency: hit the manual notify endpoint — since our TEST entry
            #    is already notified, it should be a no-op for that specific entry.
            r_manual = admin_session.post(f"{BASE_URL}/api/admin/launch/notify-waitlist",
                                          timeout=30)
            assert r_manual.status_code == 200
            assert r_manual.json().get("ok") is True
            # The TEST entry must still be flagged (idempotent)
            aw2 = admin_session.get(f"{BASE_URL}/api/admin/waitlist", timeout=15).json()
            entry2 = next((x for x in aw2["items"] if x.get("email") == marker), None)
            assert entry2 and entry2.get("launched_notified") is True
        finally:
            # Ensure OFF regardless of outcome
            admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"business_setup_mode_enabled": False}, timeout=15)


# ────────────── 5) REGRESSION: existing soft-launch still works ──────────────
class TestSoftLaunchRegression:
    def test_shell_home_gated_on_toggle(self, admin_session):
        # Turn ON
        admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                            json={"business_setup_mode_enabled": True}, timeout=15)
        time.sleep(CACHE_WAIT)
        try:
            # Anon
            r = requests.get(f"{BASE_URL}/api/shell/home", timeout=20)
            assert r.status_code == 423, r.status_code

            # Preview-token header
            tr = admin_session.post(f"{BASE_URL}/api/admin/preview-tokens",
                                    json={"label": "TEST_iter145_gate"}, timeout=15)
            tok = tr.json()["token"]
            r2 = requests.get(f"{BASE_URL}/api/shell/home",
                              headers={"X-Preview-Token": tok}, timeout=20)
            assert r2.status_code == 200

            # Admin cookie
            r3 = admin_session.get(f"{BASE_URL}/api/shell/home", timeout=20)
            assert r3.status_code == 200

            admin_session.post(f"{BASE_URL}/api/admin/preview-tokens/{tok}/revoke",
                               timeout=15)
        finally:
            admin_session.patch(f"{BASE_URL}/api/admin/launch-settings",
                                json={"business_setup_mode_enabled": False}, timeout=15)
            time.sleep(CACHE_WAIT)
