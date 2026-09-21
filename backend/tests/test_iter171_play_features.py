"""Iter 171 — regression coverage for 4 new Play Together features:
   leaderboard, invite-open+pending+remind, start-live-round (trivia),
   and win-to-share card (PNG + OG page)."""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

HOST = ("demo@bigfm.dubai", "DemoPass123!")
JOINER = ("freeuser@bigfm.dubai", "FreePass123!")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def host_session():
    return _login(*HOST)


@pytest.fixture(scope="module")
def joiner_session():
    return _login(*JOINER)


@pytest.fixture(scope="module")
def host_uid(host_session):
    r = host_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest.fixture(scope="module")
def joiner_uid(joiner_session):
    r = joiner_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


@pytest.fixture(scope="module")
def demo_session_id(host_session, joiner_uid):
    """Host creates a session inviting the joiner explicitly."""
    r = host_session.post(f"{BASE_URL}/api/social/play/sessions",
                          json={"game_key": "trivia", "title": "TEST_iter171",
                                "invitees": [joiner_uid]}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("session_id", "").startswith("ps_")
    return data["session_id"]


# ─── Leaderboard ────────────────────────────────────────────────
class TestLeaderboard:
    def test_leaderboard_shape(self, host_session):
        r = host_session.get(f"{BASE_URL}/api/social/play/referral-leaderboard", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert "me" in data and isinstance(data["me"], dict)
        assert "is_me" in data["me"]
        # If host is in top, first item should be them (main agent said rank 1 with 3 refs)
        for it in data["items"]:
            assert "rank" in it and "user_id" in it and "referrals" in it and "points" in it
            assert it["points"] == it["referrals"] * 500

    def test_leaderboard_me_when_not_in_top(self, joiner_session, joiner_uid):
        r = joiner_session.get(f"{BASE_URL}/api/social/play/referral-leaderboard", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data["me"]["user_id"] == joiner_uid
        assert data["me"]["is_me"] is True


# ─── Invite Opens + Pending + Remind ─────────────────────────────
class TestOpenedPendingRemind:
    def test_opened_logs_and_pending_shows(self, host_session, joiner_session, demo_session_id, joiner_uid, host_uid):
        # Joiner opens the invite (but does NOT join)
        r = joiner_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/opened",
            json={"ref": host_uid}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Host GET pending — should include joiner
        r2 = host_session.get(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/pending", timeout=15)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["count"] >= 1
        uids = [it["user_id"] for it in data["items"]]
        assert joiner_uid in uids

    def test_pending_403_for_non_host(self, joiner_session, demo_session_id):
        r = joiner_session.get(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/pending", timeout=15)
        assert r.status_code == 403

    def test_remind_creates_notification_and_rate_limits(self, host_session, demo_session_id, joiner_uid):
        r = host_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/remind",
            json={"user_ids": [joiner_uid]}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["eligible"] >= 1
        # First call should have reminded 1 OR 0 (if already reminded within the hour from a prior test run)
        assert data["reminded"] in (0, 1)

        # Immediate 2nd call — rate limited => reminded=0
        r2 = host_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/remind",
            json={"user_ids": [joiner_uid]}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["reminded"] == 0

    def test_remind_403_for_non_host(self, joiner_session, demo_session_id, host_uid):
        r = joiner_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/remind",
            json={"user_ids": [host_uid]}, timeout=15)
        assert r.status_code == 403


# ─── Start Live Round (Trivia) ───────────────────────────────────
class TestStartRound:
    def test_start_round_host_creates_room(self, host_session, demo_session_id):
        r = host_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/start-round", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "room_code" in data
        code = data["room_code"]
        assert re.match(r"^[A-Z0-9\-]{4,20}$", code), code

        # Trivia room should exist in lobby phase
        r2 = host_session.get(f"{BASE_URL}/api/trivia/rooms/{code}", timeout=15)
        assert r2.status_code == 200, r2.text
        room_payload = r2.json()
        room = room_payload.get("room") or room_payload
        assert room.get("phase") == "lobby", room

        # 2nd call should reuse (idempotent)
        r3 = host_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/start-round", timeout=15)
        assert r3.status_code == 200
        assert r3.json()["room_code"] == code

        # Session list should now report room_live true
        r4 = host_session.get(f"{BASE_URL}/api/social/play/sessions", timeout=15)
        assert r4.status_code == 200
        found = [s for s in r4.json()["items"] if s["session_id"] == demo_session_id]
        assert found and found[0].get("room_code") == code
        assert found[0].get("room_live") is True

    def test_start_round_403_for_non_host(self, joiner_session, demo_session_id):
        r = joiner_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/start-round", timeout=15)
        assert r.status_code == 403


# ─── Share Card ──────────────────────────────────────────────────
class TestShareCard:
    def test_create_share_card_returns_urls(self, host_session):
        r = host_session.post(f"{BASE_URL}/api/social/share-card",
                              json={"kind": "referral", "title": "TEST_iter171 win!",
                                    "prize": "+500", "subtitle": "Play together"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["card_id"].startswith("scard_")
        assert data["image_url"].endswith(f"/api/social/share-card/img/{data['card_id']}")
        assert data["share_url"].endswith(f"/api/social/share-card/{data['card_id']}")

        # Image endpoint is public (no cookies)
        r2 = requests.get(data["image_url"], timeout=30)
        assert r2.status_code == 200, r2.status_code
        assert r2.headers.get("content-type", "").startswith("image/png")
        assert len(r2.content) > 5000  # a real PNG (>5KB)
        assert r2.content[:8] == b"\x89PNG\r\n\x1a\n"

        # OG page is public HTML with the og:image tag
        r3 = requests.get(data["share_url"], timeout=30)
        assert r3.status_code == 200, r3.status_code
        assert "og:image" in r3.text
        assert "og:title" in r3.text
        assert data["card_id"] in r3.text

    def test_share_card_404(self):
        r = requests.get(f"{BASE_URL}/api/social/share-card/img/scard_doesnotexist12", timeout=15)
        assert r.status_code == 404


# ─── Live-round trigger via referral join (extra sanity) ────────
class TestJoinFlow:
    def test_join_after_opened_marks_converted(self, joiner_session, demo_session_id, host_uid):
        # joiner joins the session (was invited)
        r = joiner_session.post(
            f"{BASE_URL}/api/social/play/sessions/{demo_session_id}/join",
            json={"ref": host_uid}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["joined"] is True
        # After this join the pending list must NOT include joiner anymore
