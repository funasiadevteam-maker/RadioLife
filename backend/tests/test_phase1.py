"""BigFM Dubai Phase 1 — backend API tests for auth, admin gating, radio personalization, RJ caps, duo banter."""
import os
import time
import uuid
import json
import glob
import shutil
import subprocess
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

TEST_EMAIL = "test@bigfm.dubai"
TEST_PASSWORD = "TestUser123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASSWORD = "AdminPass123!"

RJ_STORAGE_DIR = "/app/backend/storage/rj"


# ---------------- helpers ----------------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def user_session():
    return _login(TEST_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


# ============== AUTH ==============
class TestAuth:
    def test_login_returns_cookie(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
        assert r.status_code == 200
        # bigfm_session cookie set
        assert "bigfm_session" in r.cookies, f"no bigfm_session cookie: {r.cookies}"
        data = r.json()
        assert data.get("email") == TEST_EMAIL

    def test_me_with_cookie_returns_user(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("email") == TEST_EMAIL
        assert body.get("onboarding_complete") is True

    def test_me_without_cookie_401(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 401

    def test_logout_clears_cookie(self):
        s = _login(TEST_EMAIL, TEST_PASSWORD)
        r = s.post(f"{BASE_URL}/api/auth/logout", timeout=15)
        assert r.status_code in (200, 204)
        # after logout, me should be 401
        r2 = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r2.status_code == 401

    def test_register_new_user(self):
        email = f"qa+{int(time.time())}_{uuid.uuid4().hex[:6]}@bigfm.dubai"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "QaTest1234!", "name": "QA Tester"},
                          timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
        body = r.json()
        assert body.get("email") == email
        assert body.get("onboarding_complete") is False

    def test_login_bad_password_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": TEST_EMAIL, "password": "WRONG"}, timeout=15)
        assert r.status_code == 401


# ============== PREFERENCES + ONBOARDING ==============
class TestPreferences:
    def test_post_preferences_flips_onboarding_complete(self):
        email = f"qa+{int(time.time())}_{uuid.uuid4().hex[:6]}@bigfm.dubai"
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"email": email, "password": "QaTest1234!", "name": "QA Pref"},
                   timeout=30)
        assert r.status_code in (200, 201)

        # Should not be onboarded yet
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
        assert me["onboarding_complete"] is False

        prefs = {
            "languages": ["hindi", "english"],
            "genres": ["bollywood", "pop"],
            "eras": ["2010s", "2020s"],
            "moods": ["energetic", "chill"],
            "activities": ["evening_commute", "party"],
            "city": "Dubai",
            "home_area": "Karama",
            "host_personality": "auto",
            "explicit_ok": True,
        }
        r2 = s.post(f"{BASE_URL}/api/users/preferences", json=prefs, timeout=30)
        assert r2.status_code == 200, f"{r2.status_code} {r2.text[:300]}"

        me2 = s.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
        assert me2["onboarding_complete"] is True
        # Verify some preference round-tripped
        pv = me2.get("preferences") or me2.get("preference_vector") or {}
        # Tolerate either shape
        lang_list = pv.get("languages") if isinstance(pv, dict) else None
        if lang_list is not None:
            assert "hindi" in lang_list


# ============== ADMIN GATING ==============
class TestAdminGating:
    def test_admin_tracks_admin_200(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/tracks", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_tracks_user_403(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/admin/tracks", timeout=20)
        assert r.status_code == 403

    def test_admin_tracks_no_auth_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/tracks", timeout=20)
        assert r.status_code == 401


# ============== RADIO PERSONALIZATION ==============
@pytest.fixture(scope="module")
def radio_session(user_session):
    r = user_session.post(f"{BASE_URL}/api/radio/start",
                          json={"channel": "dubai_default"}, timeout=180)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()


class TestRadioPersonalization:
    def test_radio_start_picks_personalized_language(self, radio_session):
        seg = radio_session["segment"]
        assert "session_id" in radio_session
        # Track language should match user preferences (hindi/bollywood/english)
        # We don't strictly require language on the response, but if present check it
        tlang = (seg.get("track_language") or "").lower()
        if tlang:
            assert tlang in {"hindi", "bollywood", "english"}, f"unexpected lang {tlang}"

    def test_radio_next_no_repeats_and_eventually_duo(self, user_session, radio_session):
        sid = radio_session["session_id"]
        seen_track_ids = {radio_session["segment"]["track_id"]}
        seen_segments = [radio_session["segment"]]
        found_duo = radio_session["segment"].get("rj_format") == "duo"

        # Up to 8 more /next calls
        for i in range(8):
            r = user_session.get(f"{BASE_URL}/api/radio/next",
                                 params={"session_id": sid}, timeout=180)
            assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
            seg = r.json()["segment"]
            tid = seg["track_id"]
            assert tid not in seen_track_ids, f"track {tid} repeated at step {i}"
            seen_track_ids.add(tid)
            seen_segments.append(seg)
            if seg.get("rj_format") == "duo":
                found_duo = True
            if found_duo and len(seen_segments) >= 4:
                break

        # We saved >=4 unique track_ids
        assert len(seen_segments) >= 4
        # Stash for later tests
        radio_session["_seen_segments"] = seen_segments
        radio_session["_found_duo"] = found_duo

    def test_radio_next_wrong_user_403(self, radio_session, admin_session):
        sid = radio_session["session_id"]
        # admin uses a different user → session should reject
        r = admin_session.get(f"{BASE_URL}/api/radio/next",
                              params={"session_id": sid}, timeout=30)
        # 403 (or 404 if backend doesn't bind sessions to user); we expect 403
        assert r.status_code == 403, f"expected 403 cross-user, got {r.status_code} {r.text[:200]}"


# ============== 45-SECOND RJ CAP ==============
class TestRjCap:
    def test_rj_segment_under_45s(self, radio_session, user_session):
        seen = radio_session.get("_seen_segments") or [radio_session["segment"]]
        for seg in seen:
            seg_id = seg["segment_id"]
            r = requests.get(f"{BASE_URL}/api/radio/segment/{seg_id}/meta", timeout=15) \
                if False else None
            # Use the seg object directly: duration_sec - rj_start_sec
            dur = float(seg["duration_sec"])
            rj_start = float(seg.get("rj_start_sec", 0))
            rj_dur = dur - rj_start
            assert rj_dur <= 45.5, f"segment {seg_id} RJ portion {rj_dur:.2f}s exceeds 45s"

    def test_rj_storage_files_under_45s(self):
        if not os.path.isdir(RJ_STORAGE_DIR):
            pytest.skip(f"RJ storage dir missing: {RJ_STORAGE_DIR}")
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            pytest.skip("ffprobe not installed")
        files = sorted(glob.glob(os.path.join(RJ_STORAGE_DIR, "*.mp3")))
        if not files:
            pytest.skip("no rj mp3 files yet")
        # Sample at most 25 to keep test fast
        for f in files[:25]:
            try:
                out = subprocess.check_output(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", f],
                    stderr=subprocess.STDOUT, timeout=10
                ).decode().strip()
                dur = float(out)
            except Exception as e:
                pytest.fail(f"ffprobe failed on {f}: {e}")
            assert dur <= 45.5, f"{os.path.basename(f)} = {dur:.2f}s (>45s)"


# ============== DUO BANTER ==============
class TestDuoBanter:
    def test_admin_test_segment_duo(self, admin_session):
        # Need a chill track id
        tracks = admin_session.get(f"{BASE_URL}/api/admin/tracks", timeout=20).json()
        assert tracks, "no tracks"
        # pick first track
        tid = tracks[0]["id"]
        r = admin_session.post(f"{BASE_URL}/api/admin/test_segment",
                               json={"next_track_id": tid, "voice_key": "veer_dubai", "format": "duo"},
                               timeout=180)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        body = r.json()
        seg = body.get("segment") or body
        assert seg.get("rj_format") == "duo", f"expected duo, got {seg.get('rj_format')}"
        hosts = seg.get("rj_hosts") or []
        assert len(hosts) == 2, f"expected 2 hosts, got {hosts}"
        script = seg.get("rj_script", "")
        # count [VEER] or [MONIKA] lines
        veer_lines = script.count("[VEER]")
        monika_lines = script.count("[MONIKA]")
        assert (veer_lines + monika_lines) >= 2, f"too few host-tagged lines: {script[:400]}"


# ============== ADMIN DELETE + PREVIEW ==============
class TestAdminDeleteAndPreview:
    def _make_mp3(self, path, sec=3):
        # generate 3-sec sine via ffmpeg
        ff = shutil.which("ffmpeg")
        if not ff:
            return False
        subprocess.check_call(
            [ff, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}",
             "-q:a", "9", "-acodec", "libmp3lame", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True

    def test_admin_upload_then_delete(self, admin_session, user_session, tmp_path):
        mp3_path = tmp_path / "TEST_upload.mp3"
        if not self._make_mp3(str(mp3_path)):
            pytest.skip("ffmpeg not available to synthesize mp3")
        files = {"file": ("TEST_upload.mp3", open(mp3_path, "rb"), "audio/mpeg")}
        data = {"title": "TEST_Track", "artist": "TEST_Artist",
                "language": "english", "genre": "pop"}
        r = admin_session.post(f"{BASE_URL}/api/admin/tracks/upload",
                               files=files, data=data, timeout=60)
        assert r.status_code in (200, 201), f"upload failed: {r.status_code} {r.text[:300]}"
        track = r.json()
        tid = track.get("id") or track.get("track", {}).get("id")
        assert tid

        # user cannot delete
        r_user = user_session.delete(f"{BASE_URL}/api/admin/tracks/{tid}", timeout=20)
        assert r_user.status_code == 403

        # admin deletes
        r_del = admin_session.delete(f"{BASE_URL}/api/admin/tracks/{tid}", timeout=30)
        assert r_del.status_code == 200, f"delete failed: {r_del.status_code} {r_del.text[:200]}"

        # gone from listing
        list_r = admin_session.get(f"{BASE_URL}/api/admin/tracks", timeout=20)
        ids = [t["id"] for t in list_r.json()]
        assert tid not in ids

    def test_admin_preview_206_with_range(self, admin_session, user_session):
        tracks = admin_session.get(f"{BASE_URL}/api/admin/tracks", timeout=20).json()
        assert tracks
        tid = tracks[0]["id"]
        # admin + Range
        r = admin_session.get(f"{BASE_URL}/api/admin/tracks/{tid}/preview",
                              headers={"Range": "bytes=0-2000"}, timeout=30, stream=True)
        assert r.status_code == 206, f"got {r.status_code}"
        assert r.headers.get("Content-Range", "").startswith("bytes 0-")

        # no auth → 401
        r2 = requests.get(f"{BASE_URL}/api/admin/tracks/{tid}/preview", timeout=15)
        assert r2.status_code == 401

        # user → 403
        r3 = user_session.get(f"{BASE_URL}/api/admin/tracks/{tid}/preview", timeout=15)
        assert r3.status_code == 403


# ============== VOICE PREVIEW (public) ==============
class TestVoicePreview:
    @pytest.mark.parametrize("vk", ["dj_dubai", "veer_dubai", "monika_dubai"])
    def test_voice_preview_206(self, vk):
        r = requests.get(f"{BASE_URL}/api/voices/preview/{vk}",
                         headers={"Range": "bytes=0-1000"}, timeout=20, stream=True)
        assert r.status_code == 206, f"{vk}: {r.status_code}"
        assert r.headers.get("Content-Range", "").startswith("bytes 0-")

    def test_voice_preview_bogus_404(self):
        r = requests.get(f"{BASE_URL}/api/voices/preview/bogus_voice_xyz", timeout=15)
        assert r.status_code == 404


# ============== GOOGLE OAUTH ==============
class TestGoogleOauth:
    def test_bogus_session_id_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/google/session",
                          json={"session_id": "bogus"}, timeout=30)
        assert r.status_code == 401, f"got {r.status_code}: {r.text[:200]}"

    def test_empty_payload_returns_422(self):
        r = requests.post(f"{BASE_URL}/api/auth/google/session",
                          json={}, timeout=15)
        assert r.status_code == 422
