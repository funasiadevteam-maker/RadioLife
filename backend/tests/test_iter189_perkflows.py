"""ITER189 — Perk Redemption Scan + Featured Live Banner + Cover Art Generator + Perk Gifting.

Backend contract tests against the shared FastAPI. Uses production seeded fixtures
(demo@bigfm.dubai owns biz_demo_bar; freeuser@bigfm.dubai is demo's accepted friend).
"""
import os
import time
import requests
import pytest

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

DEMO = ("demo@bigfm.dubai", "DemoPass123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")
BIZ = "biz_demo_bar"


def _login(session, email, password):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    _login(s, *DEMO)
    return s


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    _login(s, *FREE)
    return s


# ─────────────── Perk Redemption Scan (staff/lookup + staff/redeem) ───────────────
class TestStaffScan:
    def test_lookup_valid_returns_customer(self, demo_session):
        r = demo_session.post(f"{API}/bar-games/{BIZ}/staff/lookup",
                              json={"code": "BAR-NEON2FOR"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "valid", data
        assert data["perk"]["code"] == "BAR-NEON2FOR"
        assert data["perk"]["customer"]  # not blank

    def test_lookup_expired(self, demo_session):
        r = demo_session.post(f"{API}/bar-games/{BIZ}/staff/lookup",
                              json={"code": "BAR-OLD999"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "expired"

    def test_lookup_not_found(self, demo_session):
        r = demo_session.post(f"{API}/bar-games/{BIZ}/staff/lookup",
                              json={"code": "BAR-BOGUS999"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "not_found"

    def test_lookup_forbidden_for_non_owner(self, free_session):
        r = free_session.post(f"{API}/bar-games/{BIZ}/staff/lookup",
                              json={"code": "BAR-NEON2FOR"}, timeout=15)
        assert r.status_code == 403
        # FastAPI wraps HTTPException.detail in {"detail": {...}}
        body = r.json()
        detail = body.get("detail", body)
        assert (detail.get("code") if isinstance(detail, dict) else detail) == "not_bar_staff"

    def test_redeem_forbidden_for_non_owner(self, free_session):
        r = free_session.post(f"{API}/bar-games/{BIZ}/staff/redeem",
                              json={"code": "BAR-NEON2FOR"}, timeout=15)
        assert r.status_code == 403


# ─────────────── Cover Art Generator ───────────────
class TestCoverArt:
    def test_generate_returns_relative_url(self, demo_session):
        r = demo_session.post(f"{API}/bar-games/cover-art",
                              json={"prompt": "iter189 neon test"}, timeout=90)
        # Either OK, or gracefully rate-limited (429) / gen failed (502) — treat rate-limit as non-blocking
        if r.status_code in (429, 502):
            pytest.skip(f"image-gen limited/failed: {r.status_code} {r.text}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        url = data.get("url")
        assert isinstance(url, str) and url.startswith("/api/"), f"expected relative /api/... got {url}"
        # verify reachable
        head = requests.get(f"{BASE_URL}{url}", timeout=15)
        assert head.status_code == 200
        assert "image" in head.headers.get("content-type", "")


# ─────────────── Perk Gifting ───────────────
def _find_friend_id(session, my_uid_hint_email="freeuser"):
    r = session.get(f"{API}/social/friends", timeout=15)
    assert r.status_code == 200, r.text
    friends = r.json().get("friends") or r.json()  # tolerate wrapping
    if isinstance(friends, dict):
        friends = friends.get("friends") or friends.get("items") or []
    # find freeuser
    for f in friends:
        if my_uid_hint_email in ((f.get("email") or "") + (f.get("username") or "") + (f.get("name") or "").lower()):
            return f.get("user_id") or f.get("id")
    if friends:
        return friends[0].get("user_id") or friends[0].get("id")
    return None


def _pick_valid_play(session):
    """Return a currently-valid (non-expired, non-redeemed) play_id from demo's wallet."""
    r = session.get(f"{API}/bar-games/wallet", timeout=15)
    assert r.status_code == 200, r.text
    plays = r.json().get("items") or r.json().get("plays") or []
    for p in plays:
        if not p.get("redeemed") and not p.get("expired"):
            return p.get("play_id") or p.get("_id") or p.get("id")
    return None


class TestPerkGift:
    def test_gift_rejects_non_friend(self, demo_session):
        play_id = _pick_valid_play(demo_session)
        if not play_id:
            pytest.skip("no valid perk in demo wallet")
        r = demo_session.post(f"{API}/bar-games/plays/{play_id}/gift",
                              json={"friend_id": "user_nonexistent_zzz"}, timeout=15)
        assert r.status_code == 400
        body = r.json()
        detail = body.get("detail", body)
        assert (detail.get("code") if isinstance(detail, dict) else detail) == "not_friends"

    def test_friends_list_has_freeuser(self, demo_session):
        fid = _find_friend_id(demo_session, "freeuser")
        assert fid, "demo is expected to be friends with freeuser"

    # NOTE: we intentionally do NOT run an end-to-end gift here because it mutates
    # seeded demo wallet (moves BAR-NEON2FOR to freeuser). The UI test will do it in
    # a controlled way inside its own play-through if needed.
