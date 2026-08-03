"""BigFM Dubai Phase 2 — Channels, Voices expansion, Music-clock compliance,
Skip-limit (429), Share-this-break, Channel switcher.

Run: pytest /app/backend/tests/test_phase2.py -v --tb=short
"""
import os
import time
import datetime as dt
import pytest
import requests
import pymongo

# Load backend .env so DB_NAME/MONGO_URL match the live backend (DB_NAME=bigfm)
def _load_backend_env():
    env_path = "/app/backend/.env"
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)
_load_backend_env()

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

TEST_EMAIL = "test@bigfm.dubai"
TEST_PASSWORD = "TestUser123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASSWORD = "AdminPass123!"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

EXPECTED_SLUGS = {
    "bollywood_mehfil", "party_dubai", "late_night_drive", "punjabi_beats",
    "morning_masala", "devotional_hour", "retro_lounge", "workout_wala",
}
EXPECTED_NEW_VOICES = {
    "dj_riya_dubai", "pandit_anand", "gurpreet_bhaji",
    "aarti_morning", "kishore_retro", "simran_punjabi",
}
ORIGINAL_VOICES = {"dj_dubai", "veer_dubai", "monika_dubai"}


# ---------- helpers / fixtures ----------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def user_session():
    return _login(TEST_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def mongo_db():
    client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=4000)
    try:
        yield client[DB_NAME]
    finally:
        client.close()


@pytest.fixture(scope="module")
def test_user_id(mongo_db):
    u = mongo_db.users.find_one({"email": TEST_EMAIL})
    assert u, f"test user {TEST_EMAIL} not seeded"
    return u.get("user_id") or u.get("_id")


# ============ CHANNELS ============
class TestChannels:
    def test_channels_list_public_8_channels(self):
        r = requests.get(f"{BASE_URL}/api/channels", timeout=15)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        chans = body["channels"]
        slugs = {c["slug"] for c in chans}
        assert slugs == EXPECTED_SLUGS, f"got slugs: {slugs}"
        # Default
        assert body.get("default") == "bollywood_mehfil"
        # Each channel has required fields
        for c in chans:
            for k in ("slug", "name", "cover_color", "hosts", "language_mix"):
                assert k in c, f"missing key {k} in {c['slug']}"
            assert isinstance(c["hosts"], list) and len(c["hosts"]) >= 1
            assert isinstance(c["language_mix"], list)

    @pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
    def test_channel_detail_200(self, slug):
        r = requests.get(f"{BASE_URL}/api/channels/{slug}", timeout=15)
        assert r.status_code == 200, f"{slug}: {r.status_code} {r.text[:200]}"
        assert r.json()["slug"] == slug

    def test_channel_detail_invalid_404(self):
        r = requests.get(f"{BASE_URL}/api/channels/no_such_channel_xyz", timeout=15)
        assert r.status_code == 404


# ============ VOICES ============
class TestVoices:
    def test_voices_list_has_9(self):
        r = requests.get(f"{BASE_URL}/api/voices", timeout=15)
        assert r.status_code == 200
        body = r.json()
        # accept list or {voices:[...]}
        voices = body if isinstance(body, list) else body.get("voices") or []
        keys = {v.get("key") or v.get("voice_key") for v in voices}
        missing = (ORIGINAL_VOICES | EXPECTED_NEW_VOICES) - keys
        assert not missing, f"missing voices: {missing}, got: {keys}"
        assert len(voices) >= 9

    @pytest.mark.parametrize("vk", sorted(EXPECTED_NEW_VOICES))
    def test_new_voice_preview_206(self, vk):
        r = requests.get(f"{BASE_URL}/api/voices/preview/{vk}",
                         headers={"Range": "bytes=0-1000"}, timeout=30, stream=True)
        assert r.status_code == 206, f"{vk}: {r.status_code} {r.text[:200]}"
        assert r.headers.get("Content-Range", "").startswith("bytes 0-"), r.headers


# ============ RADIO START w/ CHANNEL ============
@pytest.fixture(scope="module")
def party_session(user_session):
    """Start a fresh session on party_dubai."""
    r = user_session.post(f"{BASE_URL}/api/radio/start",
                          json={"channel": "party_dubai"}, timeout=120)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()


class TestRadioStartChannel:
    def test_party_dubai_voice_is_channel_host(self, party_session):
        seg = party_session["segment"]
        vk = seg.get("rj_voice_key")
        assert vk in {"dj_dubai", "dj_riya_dubai"}, \
            f"party_dubai host should be dj_dubai or dj_riya_dubai, got {vk}"
        # skip_state present
        ss = party_session.get("skip_state") or {}
        assert "used" in ss and "limit" in ss
        assert ss["limit"] == 6

    def test_switch_channel_to_devotional(self, user_session, party_session, mongo_db):
        sid = party_session["session_id"]
        r = user_session.post(f"{BASE_URL}/api/radio/switch_channel",
                              json={"session_id": sid, "channel": "devotional_hour"},
                              timeout=120)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        seg = r.json()["segment"]
        # devotional_hour only host is pandit_anand
        assert seg["rj_voice_key"] == "pandit_anand", \
            f"expected pandit_anand, got {seg.get('rj_voice_key')}"
        # channel_switch event logged in playback_logs
        log = mongo_db.playback_logs.find_one(
            {"session_id": sid, "event": "channel_switch"},
            sort=[("timestamp", pymongo.DESCENDING)],
        )
        assert log, "no channel_switch event in playback_logs"


# ============ SESSION STATE LEAK PROTECTION ============
class TestSessionStateNoLeak:
    def test_session_endpoint_doesnt_leak_upcoming(self, user_session, party_session):
        sid = party_session["session_id"]
        r = user_session.get(f"{BASE_URL}/api/radio/session/{sid}", timeout=20)
        assert r.status_code == 200
        body = r.json()
        forbidden = {"pending_segment_id", "played_track_ids", "last_track_id"}
        leaked = forbidden & set(body.keys())
        assert not leaked, f"leaked keys: {leaked} -- full body: {body}"
        # Required fields present
        for k in ("session_id", "channel_slug", "channel_name",
                  "current_segment_id", "segments_played", "skip_state"):
            assert k in body, f"missing key {k}"


# ============ SKIP LIMIT 429 ============
class TestSkipLimit:
    def test_skip_exhausted_returns_429(self, user_session, party_session,
                                       mongo_db, test_user_id):
        sid = party_session["session_id"]
        now = dt.datetime.now(dt.timezone.utc)
        # Inject 6 skip events directly
        injected_ids = []
        for i in range(6):
            doc = {
                "session_id": sid,
                "user_id": test_user_id,
                "event": "skip",
                "timestamp": now - dt.timedelta(minutes=i * 2),
                "_test_marker": "phase2_skip_test",
            }
            res = mongo_db.playback_logs.insert_one(doc)
            injected_ids.append(res.inserted_id)

        try:
            # skip_state should report exhausted
            ss_r = user_session.get(f"{BASE_URL}/api/radio/skip_state", timeout=15)
            assert ss_r.status_code == 200
            ss = ss_r.json()
            assert ss.get("used", 0) >= 6, ss
            assert ss.get("exhausted") is True, ss

            # POST /api/radio/skip should now 429
            r = user_session.post(f"{BASE_URL}/api/radio/skip",
                                  params={"session_id": sid}, timeout=30)
            assert r.status_code == 429, f"got {r.status_code}: {r.text[:300]}"
            body = r.json()
            # FastAPI HTTPException puts payload under 'detail'
            payload = body.get("detail") if isinstance(body.get("detail"), dict) else body
            for k in ("retry_after_sec", "used", "limit", "window_sec"):
                assert k in payload, f"missing {k} in 429 body: {body}"
            assert payload["limit"] == 6
            assert payload["window_sec"] == 3600
        finally:
            # cleanup injected docs
            mongo_db.playback_logs.delete_many(
                {"_id": {"$in": injected_ids}}
            )


# ============ SHARE-THIS-BREAK ============
@pytest.fixture(scope="module")
def share_session(user_session):
    """Fresh session for share tests."""
    r = user_session.post(f"{BASE_URL}/api/radio/start",
                          json={"channel": "bollywood_mehfil"}, timeout=120)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


class TestShareBreak:
    def test_share_create_meta_audio(self, user_session, share_session):
        seg_id = share_session["segment"]["segment_id"]
        # create share
        r = user_session.post(f"{BASE_URL}/api/share/break",
                              json={"segment_id": seg_id}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        share_id = body["share_id"]
        assert body["share_url"] == f"/r/{share_id}"
        assert body["audio_url"] == f"/api/share/{share_id}/audio"

        # meta public (no auth)
        meta_r = requests.get(f"{BASE_URL}/api/share/{share_id}/meta", timeout=15)
        assert meta_r.status_code == 200
        meta = meta_r.json()
        assert meta["share_id"] == share_id
        # required fields
        assert "track_title" in meta
        assert "host_names" in meta and isinstance(meta["host_names"], list)
        assert "duration_sec" in meta
        assert meta.get("view_count", 0) >= 1

        # audio with Range
        au_r = requests.get(f"{BASE_URL}/api/share/{share_id}/audio",
                            headers={"Range": "bytes=0-2000"}, timeout=30, stream=True)
        assert au_r.status_code == 206
        assert au_r.headers.get("Content-Range", "").startswith("bytes 0-")

    def test_share_fake_segment_404(self, user_session):
        r = user_session.post(f"{BASE_URL}/api/share/break",
                              json={"segment_id": "fake_segment_xyz"}, timeout=20)
        assert r.status_code == 404, f"got {r.status_code}: {r.text[:200]}"

    def test_share_other_user_segment_403(self, user_session, admin_session):
        # Admin starts a session
        r = admin_session.post(f"{BASE_URL}/api/radio/start",
                               json={"channel": "bollywood_mehfil"}, timeout=120)
        assert r.status_code == 200
        admin_seg = r.json()["segment"]["segment_id"]
        # test user tries to share admin's segment
        r2 = user_session.post(f"{BASE_URL}/api/share/break",
                               json={"segment_id": admin_seg}, timeout=30)
        assert r2.status_code == 403, f"got {r2.status_code}: {r2.text[:300]}"


# ============ MUSIC-CLOCK / COMPLIANCE ============
class TestComplianceMusicClock:
    def test_three_sequential_no_repeats_no_3consec_artist(self, user_session, mongo_db):
        # Compliance can only enforce no-repeat when catalog has >= ~4 channel-compatible tracks.
        track_count = mongo_db.tracks.count_documents({})
        if track_count < 6:
            pytest.skip(
                f"catalog too small ({track_count} tracks) to enforce no-repeat over 4 segments; "
                f"compliance logic still functional but test inconclusive"
            )
        r = user_session.post(f"{BASE_URL}/api/radio/start",
                              json={"channel": "bollywood_mehfil"}, timeout=120)
        assert r.status_code == 200
        body = r.json()
        sid = body["session_id"]
        segs = [body["segment"]]
        for _ in range(3):
            nxt = user_session.get(f"{BASE_URL}/api/radio/next",
                                   params={"session_id": sid}, timeout=120)
            assert nxt.status_code == 200, nxt.text[:200]
            segs.append(nxt.json()["segment"])
        # No track repeats
        tids = [s["track_id"] for s in segs]
        assert len(tids) == len(set(tids)), f"track repeats: {tids}"
        # No 3 consecutive artists (best-effort: artist may not be in segment payload)
        artists = [(s.get("track_artist") or s.get("artist") or "").lower() for s in segs]
        if any(artists):
            for i in range(2, len(artists)):
                if artists[i] and artists[i-1] and artists[i-2]:
                    assert not (artists[i] == artists[i-1] == artists[i-2]), \
                        f"3 consec artist at {i}: {artists}"


# ============ ADMIN GATING (regression) ============
class TestAdminGating:
    def test_admin_tracks_user_403(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/admin/tracks", timeout=20)
        assert r.status_code == 403

    def test_admin_tracks_admin_200(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/tracks", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
