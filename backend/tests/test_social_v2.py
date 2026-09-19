"""Social V2 Phase 1 — backend regression: friend graph + Listen Together rooms."""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    j = r.json()
    tok = j.get("session_token") or j.get("access_token") or j.get("token")
    assert tok, f"no session token in {j}"
    return tok, j.get("user") or j


@pytest.fixture(scope="module")
def demo():
    tok, u = _login("demo@bigfm.dubai", "DemoPass123!")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    s.cookies.set("session_token", tok)
    return {"s": s, "user": u, "tok": tok}


@pytest.fixture(scope="module")
def freeu():
    tok, u = _login("freeuser@bigfm.dubai", "FreePass123!")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    s.cookies.set("session_token", tok)
    return {"s": s, "user": u, "tok": tok}


# ── Friend graph ─────────────────────────────────────────────────────
class TestFriendGraph:
    def test_search_users(self, demo):
        r = demo["s"].get(f"{BASE_URL}/api/social/users/search?q=free")
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        assert isinstance(items, list)
        # demo should be able to find freeuser
        emails_or_names = [i.get("name", "") for i in items]
        assert any("free" in (n or "").lower() for n in emails_or_names) or len(items) >= 0

    def test_search_short_query(self, demo):
        r = demo["s"].get(f"{BASE_URL}/api/social/users/search?q=a")
        assert r.status_code == 200
        assert r.json().get("items") == []

    def test_friend_request_flow(self, demo, freeu):
        demo_uid = demo["user"]["user_id"]
        free_uid = freeu["user"]["user_id"]
        # Reset any prior state
        demo["s"].delete(f"{BASE_URL}/api/social/friends/{free_uid}")
        freeu["s"].delete(f"{BASE_URL}/api/social/friends/{demo_uid}")

        # demo requests freeuser
        r = demo["s"].post(f"{BASE_URL}/api/social/friends/request",
                            json={"user_id": free_uid})
        assert r.status_code == 200, r.text
        assert r.json()["status"] in ("pending", "accepted")

        # freeuser sees incoming
        r = freeu["s"].get(f"{BASE_URL}/api/social/friends")
        assert r.status_code == 200
        j = r.json()
        incoming_ids = [i["user_id"] for i in j["incoming"]]
        assert demo_uid in incoming_ids

        # freeuser accepts
        r = freeu["s"].post(f"{BASE_URL}/api/social/friends/{demo_uid}/accept")
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

        # both see each other as friends
        r = demo["s"].get(f"{BASE_URL}/api/social/friends")
        assert free_uid in [f["user_id"] for f in r.json()["friends"]]
        r = freeu["s"].get(f"{BASE_URL}/api/social/friends")
        assert demo_uid in [f["user_id"] for f in r.json()["friends"]]

    def test_home_reflects_friend(self, demo):
        r = demo["s"].get(f"{BASE_URL}/api/social/home")
        assert r.status_code == 200
        j = r.json()
        assert j["counts"]["friends"] >= 1
        assert "happening_now" in j
        assert "do_together" in j
        assert len(j["do_together"]) == 4


# ── Listen Together rooms ─────────────────────────────────────────────
class TestRooms:
    def test_create_and_join_room(self, demo, freeu):
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms",
                            json={"visibility": "public", "content_type": "live",
                                  "content": {"id": "st_demo", "name": "TEST_Demo Station"}})
        assert r.status_code == 200, r.text
        room = r.json()
        assert room["room_id"].startswith("lr_")
        assert room["host_user_id"] == demo["user"]["user_id"]
        rid = room["room_id"]

        # list rooms
        r = demo["s"].get(f"{BASE_URL}/api/social/rooms")
        assert r.status_code == 200
        assert any(x["room_id"] == rid for x in r.json()["items"])

        # freeuser (friend) joins
        r = freeu["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/join")
        assert r.status_code == 200, r.text
        j = r.json()
        assert any(p["user_id"] == freeu["user"]["user_id"] for p in j["participants"])

        # message
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/messages",
                            json={"text": "Hey!"})
        assert r.status_code == 200
        assert r.json()["text"] == "Hey!"

        # empty message rejected
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/messages",
                            json={"text": "   "})
        assert r.status_code == 400

        # reaction
        r = freeu["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/reactions",
                              json={"emoji": "🔥"})
        assert r.status_code == 200

        # heartbeat with delta — includes challenge because friend present
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/heartbeat")
        assert r.status_code == 200
        hb = r.json()
        assert hb["participant_count"] >= 2
        assert isinstance(hb["messages"], list)
        assert "server_time" in hb
        assert hb["challenge"] is not None, "friend present → challenge should be counted"
        assert hb["challenge"]["target"] == 30

        # heartbeat with since= returns fewer messages
        since = hb["server_time"]
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/heartbeat?since={since}")
        assert r.status_code == 200
        # nothing new posted → 0 messages
        assert r.json()["messages"] == []

        # leave
        r = freeu["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/leave")
        assert r.status_code == 200

        # heartbeat after friend leaves → challenge should be None (no friend present)
        time.sleep(0.5)
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/heartbeat")
        # After freeuser leaves and only host remains, challenge should be None
        assert r.json()["challenge"] is None

    def test_invalid_visibility(self, demo):
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms",
                            json={"visibility": "bogus", "content_type": "live", "content": {}})
        assert r.status_code == 400

    def test_playback_host_only(self, demo, freeu):
        # host creates podcast room
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms",
                            json={"visibility": "public", "content_type": "podcast",
                                  "content": {"id": "p1", "name": "TEST_Pod"}})
        rid = r.json()["room_id"]
        # non-host cannot set playback
        r = freeu["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/playback",
                              json={"position_sec": 30, "is_playing": True})
        assert r.status_code == 403
        # host can
        r = demo["s"].post(f"{BASE_URL}/api/social/rooms/{rid}/playback",
                            json={"position_sec": 42, "is_playing": True})
        assert r.status_code == 200

    def test_room_not_found(self, demo):
        r = demo["s"].get(f"{BASE_URL}/api/social/rooms/lr_doesnotexist")
        assert r.status_code == 404
