"""Iteration 160 — Social V2 Phase 2 "Do things together" backend tests.

Coverage:
- Media upload + serve (image + audio range 206)
- Moments create/feed/like/comments/delete + points award
- Outings create/list/rsvp
- Play games/session create/list/join/leave
- Local Pulse aggregation
"""
import io
import os
import pytest
import requests

def _load_url():
    env = os.environ.get("REACT_APP_BACKEND_URL")
    if env:
        return env.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""

BASE_URL = _load_url()

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PW = "DemoPass123!"
FREE_EMAIL = "freeuser@bigfm.dubai"
FREE_PW = "FreePass123!"

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\xa1\xa1\x9d\x01\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": DEMO_EMAIL, "password": DEMO_PW}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"demo login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": FREE_EMAIL, "password": FREE_PW}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"free login failed: {r.status_code} {r.text[:200]}")
    return s


# ================= Media Upload / Serve =================
class TestMedia:
    def test_upload_image_and_serve(self, demo_session):
        files = {"file": ("t.png", io.BytesIO(TINY_PNG), "image/png")}
        r = demo_session.post(f"{BASE_URL}/api/social/media/upload",
                              files=files, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["media_type"] == "photo"
        assert data["content_type"] == "image/png"
        assert data["key"].startswith("social/moments/")
        assert data["url"].endswith(data["key"])
        # Serve
        r2 = demo_session.get(data["url"], timeout=15)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("image/png")
        assert r2.content == TINY_PNG

    def test_upload_rejects_unsupported(self, demo_session):
        files = {"file": ("t.txt", io.BytesIO(b"hi"), "text/plain")}
        r = demo_session.post(f"{BASE_URL}/api/social/media/upload",
                              files=files, timeout=15)
        assert r.status_code == 400

    def test_range_request_206(self, demo_session):
        # upload an audio-ish file
        buf = os.urandom(2048)
        files = {"file": ("t.mp3", io.BytesIO(buf), "audio/mpeg")}
        r = demo_session.post(f"{BASE_URL}/api/social/media/upload",
                              files=files, timeout=30)
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        r2 = demo_session.get(url, headers={"Range": "bytes=0-99"}, timeout=15)
        assert r2.status_code == 206
        assert "Content-Range" in r2.headers
        assert r2.headers["Content-Range"].startswith("bytes 0-99/")
        assert len(r2.content) == 100


# ================= Moments =================
class TestMoments:
    def test_create_moment_awards_points(self, demo_session):
        payload = {
            "caption": "TEST_iter160 moment caption",
            "context": {"kind": "listening", "label": "Test Vibes"},
            "visibility": "public",
        }
        r = demo_session.post(f"{BASE_URL}/api/social/moments", json=payload,
                              timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["caption"] == payload["caption"]
        assert data["context"]["kind"] == "listening"
        assert data["visibility"] == "public"
        assert "moment_id" in data
        assert "points_awarded" in data
        assert data["like_count"] == 0
        assert data["comment_count"] == 0
        # Save moment id for later tests
        pytest.moment_id = data["moment_id"]

    def test_moments_feed_contains_new(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/social/moments", timeout=15)
        assert r.status_code == 200
        ids = [m["moment_id"] for m in r.json()["items"]]
        assert pytest.moment_id in ids

    def test_like_toggle(self, free_session):
        mid = pytest.moment_id
        r = free_session.post(f"{BASE_URL}/api/social/moments/{mid}/like",
                              timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["liked_by_me"] is True
        assert d["like_count"] >= 1
        r2 = free_session.post(f"{BASE_URL}/api/social/moments/{mid}/like",
                               timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["liked_by_me"] is False

    def test_comments_post_and_list(self, free_session):
        mid = pytest.moment_id
        r = free_session.post(
            f"{BASE_URL}/api/social/moments/{mid}/comments",
            json={"text": "TEST_iter160 nice one"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["text"] == "TEST_iter160 nice one"
        r2 = free_session.get(
            f"{BASE_URL}/api/social/moments/{mid}/comments", timeout=15)
        assert r2.status_code == 200
        assert any(c["text"] == "TEST_iter160 nice one"
                   for c in r2.json()["items"])

    def test_delete_moment_requires_owner(self, free_session, demo_session):
        mid = pytest.moment_id
        # Non-owner
        r = free_session.delete(f"{BASE_URL}/api/social/moments/{mid}",
                                timeout=15)
        assert r.status_code == 403
        # Owner
        r2 = demo_session.delete(f"{BASE_URL}/api/social/moments/{mid}",
                                 timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("ok") is True

    def test_empty_moment_rejected(self, demo_session):
        r = demo_session.post(f"{BASE_URL}/api/social/moments",
                              json={"caption": "  "}, timeout=15)
        assert r.status_code == 400


# ================= Outings =================
class TestOutings:
    def test_create_outing(self, demo_session):
        payload = {
            "title": "TEST_iter160 Coffee",
            "activity": "coffee",
            "place": "Downtown",
            "when_text": "Tomorrow 5pm",
            "note": "bring friends",
            "visibility": "friends",
        }
        r = demo_session.post(f"{BASE_URL}/api/social/outings", json=payload,
                              timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == payload["title"]
        assert d["is_host"] is True
        assert d["my_rsvp"] == "going"
        pytest.outing_id = d["outing_id"]

    def test_list_outings_contains(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/social/outings", timeout=15)
        assert r.status_code == 200
        ids = [o["outing_id"] for o in r.json()["items"]]
        assert pytest.outing_id in ids

    def test_rsvp(self, free_session):
        oid = pytest.outing_id
        r = free_session.post(
            f"{BASE_URL}/api/social/outings/{oid}/rsvp",
            json={"status": "maybe"}, timeout=15)
        # freeuser must be invitee or the outing must be public/city.
        # Endpoint updates rsvp regardless — should be 200.
        assert r.status_code == 200
        assert r.json()["my_rsvp"] == "maybe"

    def test_rsvp_invalid_status(self, demo_session):
        oid = pytest.outing_id
        r = demo_session.post(
            f"{BASE_URL}/api/social/outings/{oid}/rsvp",
            json={"status": "bogus"}, timeout=15)
        assert r.status_code in (400, 422)


# ================= Play Together =================
class TestPlay:
    def test_list_games(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/social/play/games", timeout=15)
        assert r.status_code == 200
        keys = [g["key"] for g in r.json()["games"]]
        assert "trivia" in keys and "predict" in keys

    def test_create_session(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/social/play/sessions",
            json={"game_key": "trivia", "title": "TEST_iter160 room"},
            timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["game_key"] == "trivia"
        assert d["is_host"] is True
        assert d["status"] == "active"
        pytest.session_id = d["session_id"]

    def test_create_session_bad_game(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/social/play/sessions",
            json={"game_key": "nope"}, timeout=15)
        assert r.status_code == 400

    def test_list_sessions_contains(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/social/play/sessions",
                             timeout=15)
        assert r.status_code == 200
        ids = [p["session_id"] for p in r.json()["items"]]
        assert pytest.session_id in ids

    def test_join_and_leave(self, free_session):
        sid = pytest.session_id
        r = free_session.post(
            f"{BASE_URL}/api/social/play/sessions/{sid}/join", timeout=15)
        assert r.status_code == 200
        assert r.json()["joined"] is True
        r2 = free_session.post(
            f"{BASE_URL}/api/social/play/sessions/{sid}/leave", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["left"] is True


# ================= Local Pulse =================
class TestPulse:
    def test_pulse_shape(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/social/pulse", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "city" in d
        assert isinstance(d.get("moments"), list)
        assert isinstance(d.get("outings"), list)
        assert isinstance(d.get("play_sessions"), list)

    def test_pulse_city_query(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/social/pulse?city=Dubai", timeout=15)
        assert r.status_code == 200
        assert r.json()["city"] == "Dubai"
