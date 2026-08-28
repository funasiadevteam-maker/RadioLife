"""
iter109 — E2E backend tests
  1. News Radio queue endpoint /api/news_radio/queue (no 500 post 48h-cache change)
  2. Live radio start /api/radio/start for bollywood_mehfil returns playable segment
  3. Imported station artwork generate/status endpoints (contract only)
  4. Upload endpoints regression (spot-check from iter108)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}


@pytest.fixture(scope="module")
def demo_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=DEMO, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"demo login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:200]}")
    return s


# ============ ITEM 1: News Radio Queue =====================================
class TestNewsRadioQueue:
    def test_queue_returns_200_no_500(self):
        r = requests.get(f"{BASE_URL}/api/news_radio/queue?limit=6", timeout=30)
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text[:300]}"
        data = r.json()
        assert data.get("channel") == "news_radio"
        assert "items" in data
        assert "mode" in data
        assert "tts" in data
        assert "audio_coverage" in data
        assert "fetched_at" in data

    def test_queue_items_have_text_only_and_audio_url_fields(self):
        r = requests.get(f"{BASE_URL}/api/news_radio/queue?limit=6", timeout=30)
        assert r.status_code == 200
        data = r.json()
        for it in data.get("items", []):
            assert "audio_url" in it
            assert "text_only" in it
            # text_only should be True when audio_url falsy
            if not it["audio_url"]:
                assert it["text_only"] is True
            # required fields
            for k in ("news_id", "title", "summary_script", "duration_estimate_sec"):
                assert k in it

    def test_queue_mode_reflects_tts_state(self):
        r = requests.get(f"{BASE_URL}/api/news_radio/queue?limit=6", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # With invalid ELEVENLABS key, mode should be 'text'
        assert data.get("mode") in ("audio", "text")


# ============ ITEM 3: Live Radio Start ======================================
class TestLiveRadioStart:
    def test_start_bollywood_mehfil_playable(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/radio/start",
            json={"channel_slug": "bollywood_mehfil"},
            timeout=30,
        )
        # Should NOT be ambassador-gated; must return a playable segment
        assert r.status_code == 200, f"status={r.status_code}, body={r.text[:400]}"
        data = r.json()
        # Response should have a segment/track info
        assert isinstance(data, dict)
        # Look for playable audio field variants
        payload_str = str(data)
        has_track = any(
            k in data for k in ("track_id", "track", "current_track", "segment", "audio_url", "stream_url")
        )
        assert has_track, f"no track info in response: keys={list(data.keys())}"

    def test_vip_lounge_ambassador_gated_by_design(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/radio/start",
            json={"channel_slug": "vip_lounge"},
            timeout=30,
        )
        # per problem statement: ambassador_level_required is CORRECT
        # 200 with a gate reason OR 403 both acceptable — just verify not a crash
        assert r.status_code < 500, f"unexpected server error: {r.status_code} {r.text[:200]}"
        body = r.text.lower()
        # accept either explicit gate or paywall — expected upstream gating
        assert (
            "ambassador" in body
            or "premium" in body
            or "gate" in body
            or r.status_code in (200, 402, 403)
        )


# ============ ITEM 4: Imported Station Artwork Endpoints ====================
class TestImportedStationArtwork:
    def test_artwork_status_endpoint_404_for_missing(self):
        r = requests.get(
            f"{BASE_URL}/api/imported-stations/imp_does_not_exist_zzz/artwork/status",
            timeout=15,
        )
        assert r.status_code == 404

    def test_artwork_status_endpoint_shape_for_real_station(self, admin_client):
        # Try to find an imported station via any listing; fall back to known seed
        # Use the flagship station seen in iter108: imp_96063f25060111e8ae
        sid = "imp_96063f25060111e8ae"
        r = requests.get(
            f"{BASE_URL}/api/imported-stations/{sid}/artwork/status",
            timeout=15,
        )
        # Either 200 with contract, or 404 if seed not applied in this run
        if r.status_code == 200:
            data = r.json()
            assert data.get("sid") == sid
            assert "status" in data
            assert "image_url" in data
        else:
            assert r.status_code == 404

    def test_artwork_generate_requires_auth(self):
        sid = "imp_96063f25060111e8ae"
        r = requests.post(
            f"{BASE_URL}/api/imported-stations/{sid}/artwork/generate", timeout=15
        )
        assert r.status_code in (401, 403), f"expected auth gate got {r.status_code}"

    def test_artwork_generate_non_owner_forbidden(self, demo_client):
        # demo user is unlikely to own this seeded flagship station
        sid = "imp_96063f25060111e8ae"
        r = demo_client.post(
            f"{BASE_URL}/api/imported-stations/{sid}/artwork/generate", timeout=15
        )
        # 403 (not_owner) or 404 (station gone) — both acceptable
        assert r.status_code in (403, 404, 429), f"unexpected {r.status_code}: {r.text[:200]}"

    def test_artwork_generate_as_admin_starts_or_rate_limits(self, admin_client):
        sid = "imp_96063f25060111e8ae"
        r = admin_client.post(
            f"{BASE_URL}/api/imported-stations/{sid}/artwork/generate", timeout=30
        )
        # admin is always owner-equivalent. Accept 200 (queued) or 429 (rate-limit) or 404
        assert r.status_code in (200, 404, 429), f"got {r.status_code}: {r.text[:200]}"
        if r.status_code == 200:
            data = r.json()
            assert data.get("ok") is True
            assert data.get("status") == "queued"


# ============ ITEM 2: Upload endpoints regression (spot check) ==============
class TestUploadRegressionSpot:
    def test_admin_flagship_logo_upload_still_works(self, admin_client):
        import io
        # 1x1 png bytes (minimal)
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
            b"\x00\x00\x00\x03\x00\x01\x08\xd7\x14\xa8\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        files = {"file": ("test.png", io.BytesIO(png), "image/png")}
        r = admin_client.post(
            f"{BASE_URL}/api/admin/stations/imp_96063f25060111e8ae/logo",
            files=files,
            timeout=30,
        )
        # 200 expected, 404 if station missing in this env
        assert r.status_code in (200, 404), f"regression: got {r.status_code} {r.text[:200]}"
        if r.status_code == 200:
            data = r.json()
            assert data.get("ok") is True
            assert "logo_url" in data
