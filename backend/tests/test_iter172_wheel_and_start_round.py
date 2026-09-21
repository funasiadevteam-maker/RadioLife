"""Iter 172 — Wheel of Fortune + play/start-round member fix (backend regression)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    return _login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="module")
def free_session():
    return _login("freeuser@bigfm.dubai", "FreePass123!")


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


# ─────────────── Wheel of Fortune ───────────────
class TestWheelConfig:
    def test_wheel_list_returns_both(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/games/wheel/list")
        assert r.status_code == 200
        ids = {i["game_id"] for i in r.json().get("items", [])}
        assert "wheel_house" in ids
        assert "wheel_demo_sponsor" in ids

    def test_wheel_config_house(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/games/wheel/config", params={"game_id": "wheel_house"})
        assert r.status_code == 200
        data = r.json()
        assert data["game_id"] == "wheel_house"
        assert "sponsor_name" in data
        assert "bgm_url" in data and data["bgm_url"]
        assert isinstance(data["spins_left"], int)
        assert 0 <= data["spins_left"] <= 3
        segs = data["segments"]
        assert len(segs) == 8
        for s in segs:
            assert "label" in s and "color" in s and "kind" in s
            assert "weight" not in s  # weights must be hidden

    def test_wheel_config_sponsor(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/games/wheel/config", params={"game_id": "wheel_demo_sponsor"})
        assert r.status_code == 200
        d = r.json()
        assert d["sponsor_name"] == "Karak House"
        labels = [s["label"] for s in d["segments"]]
        assert any("KARAK" in l.upper() or "FREE" in l.upper() for l in labels)


class TestWheelSpin:
    def test_spin_awards_points_and_caps_at_3(self, free_session):
        # First get spins_left
        r0 = free_session.get(f"{BASE_URL}/api/games/wheel/config", params={"game_id": "wheel_house"})
        assert r0.status_code == 200
        spins_left = r0.json()["spins_left"]

        # Use up remaining spins
        last_balance = None
        for i in range(spins_left):
            r = free_session.post(f"{BASE_URL}/api/games/wheel/spin", json={"game_id": "wheel_house"})
            assert r.status_code == 200, f"spin {i}: {r.status_code} {r.text[:200]}"
            data = r.json()
            assert "segment_index" in data
            assert 0 <= data["segment_index"] < 8
            assert "prize" in data and "kind" in data["prize"]
            assert data["prize"]["kind"] in ("points", "coupon", "none")
            assert "spins_left" in data
            assert "balance" in data
            last_balance = data["balance"]

        # 4th spin should be 429
        r = free_session.post(f"{BASE_URL}/api/games/wheel/spin", json={"game_id": "wheel_house"})
        assert r.status_code == 429, f"expected 429, got {r.status_code}: {r.text[:200]}"
        body = r.json().get("detail", r.json())
        assert (isinstance(body, dict) and body.get("code") == "no_spins_left") or "no_spins_left" in r.text


class TestWheelBgm:
    def test_bgm_public_audio_mpeg(self):
        # No auth
        r = requests.get(f"{BASE_URL}/api/games/bgm/wheel", timeout=20)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("audio/mpeg")
        assert len(r.content) > 50_000  # ~129KB expected, allow buffer


class TestWheelAdminGuard:
    def test_admin_endpoint_requires_admin(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/games/admin/branded-games")
        assert r.status_code in (401, 403)

    def test_admin_can_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/games/admin/branded-games")
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 2
        # segments carry weights for admin view
        assert any("weight" in (i.get("segments") or [{}])[0] for i in items)


# ─────────────── Play Together start-round bug fix ───────────────
class TestStartRoundMemberFix:
    def test_member_can_start_round(self, demo_session, free_session, admin_session):
        # demo (host) creates session, invites freeuser
        # Get demo user_id and freeuser user_id
        me_free = free_session.get(f"{BASE_URL}/api/auth/me").json()
        free_uid = me_free.get("user_id") or me_free.get("id")
        assert free_uid

        r = demo_session.post(f"{BASE_URL}/api/social/play/sessions",
                              json={"title": "TEST_iter172 startround member",
                                    "game_key": "trivia", "invitees": [free_uid]})
        assert r.status_code in (200, 201), f"create: {r.status_code} {r.text[:200]}"
        sid = r.json().get("session_id") or r.json().get("id") or r.json().get("_id")
        assert sid, r.json()

        # freeuser joins
        rj = free_session.post(f"{BASE_URL}/api/social/play/sessions/{sid}/join")
        assert rj.status_code in (200, 201), f"join: {rj.status_code} {rj.text[:200]}"

        # freeuser (MEMBER, not host) calls start-round -> should succeed
        rs = free_session.post(f"{BASE_URL}/api/social/play/sessions/{sid}/start-round")
        assert rs.status_code == 200, f"member start-round: {rs.status_code} {rs.text[:200]}"
        code = rs.json().get("room_code")
        assert code and code.startswith("BFM-"), rs.json()

        # Non-member (admin) → 403 not_a_member
        rn = admin_session.post(f"{BASE_URL}/api/social/play/sessions/{sid}/start-round")
        assert rn.status_code == 403, f"non-member: {rn.status_code} {rn.text[:200]}"
        body = rn.json()
        assert "not_a_member" in str(body)
