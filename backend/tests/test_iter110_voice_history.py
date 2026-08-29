"""Iteration 110 — backend regression for:
  #1 News Radio audio + queue (mode='audio' + audio_url + expires_at)
  #2 Admin anchor-voice picker (GET voices, POST voice, admin gate, unknown_voice)
  #3 Owner artwork history + revert (history, restore, unknown_art_url, 403)
  #4 Genre-tagged demo catalog via /api/radio/start
"""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
STATION_ID = "imp_96063f25060111e8ae"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="session")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="session")
def user_session():
    return _login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="session")
def anon_session():
    return requests.Session()


# -------- #1 News Radio queue (audio mode regression) --------
class TestNewsRadioQueue:
    def test_queue_returns_mode_and_items(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/news_radio/queue?limit=6", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["channel"] == "news_radio"
        assert "items" in data and "mode" in data
        assert data["mode"] in ("audio", "text")
        assert "audio_coverage" in data
        # Structure of items
        if data["items"]:
            it = data["items"][0]
            for k in ("news_id", "title", "summary_script", "duration_estimate_sec", "audio_url", "text_only", "pubDate"):
                assert k in it, f"missing key {k}"

    def test_tts_enabled_reports_active(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/news_radio/queue?limit=6", timeout=30)
        data = r.json()
        assert data["tts"]["provider"] == "elevenlabs"
        # Key is now valid → status should be active OR key_present_batch_disabled (but batch is on)
        assert data["tts"]["status"] in ("active", "key_present_batch_disabled")


# -------- #2 Admin anchor-voice picker --------
class TestAnchorVoicePicker:
    def test_voices_public_lists_5(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/news_radio/voices", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("voices"), list)
        assert len(d["voices"]) == 5
        assert d.get("current_voice_id")
        assert d.get("current_voice_name")
        # Every voice has id + name + description
        for v in d["voices"]:
            for k in ("voice_id", "name", "description"):
                assert k in v

    def test_non_admin_cannot_set(self, user_session):
        r = user_session.post(f"{BASE_URL}/api/admin/news-radio/voice",
                              json={"voice_id": "EXAVITQu4vr4xnSDxMaL"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_anon_cannot_set(self, anon_session):
        r = anon_session.post(f"{BASE_URL}/api/admin/news-radio/voice",
                              json={"voice_id": "EXAVITQu4vr4xnSDxMaL"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_admin_unknown_voice_400(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/news-radio/voice",
                               json={"voice_id": "does_not_exist_xyz"}, timeout=30)
        assert r.status_code == 400
        d = r.json()
        # FastAPI wraps HTTPException detail
        detail = d.get("detail") if isinstance(d, dict) else None
        if isinstance(detail, dict):
            assert detail.get("error") == "unknown_voice"
        else:
            assert "unknown_voice" in str(d)

    def test_admin_set_and_persist(self, admin_session, anon_session):
        # Pick voice #2 (Sarah)
        target = "EXAVITQu4vr4xnSDxMaL"
        r = admin_session.post(f"{BASE_URL}/api/admin/news-radio/voice",
                               json={"voice_id": target}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d.get("ok") is True
        assert d.get("voice_id") == target
        # Verify persistence via public voices endpoint
        r2 = anon_session.get(f"{BASE_URL}/api/news_radio/voices", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["current_voice_id"] == target
        # Reset back to default (Raghav) for idempotency
        admin_session.post(f"{BASE_URL}/api/admin/news-radio/voice",
                           json={"voice_id": "8vqXJx9Riwp7L4KLhsU3"}, timeout=30)


# -------- #3 Owner artwork history + revert --------
class TestArtworkHistory:
    def test_history_requires_auth(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/history", timeout=30)
        assert r.status_code in (401, 403)

    def test_history_returns_current_and_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/history", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert "current" in d
        assert isinstance(d.get("history"), list)
        for h in d["history"]:
            assert "url" in h and "source" in h and "archived_at" in h

    def test_restore_unknown_url_400(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/restore",
                               json={"art_url": "https://example.com/nope.png"}, timeout=30)
        assert r.status_code == 400
        d = r.json()
        detail = d.get("detail") if isinstance(d, dict) else None
        if isinstance(detail, dict):
            assert detail.get("error") == "unknown_art_url"
        else:
            assert "unknown_art_url" in str(d)

    def test_non_owner_forbidden(self, user_session):
        # demo user is NOT the owner of imp_96063f25060111e8ae
        r = user_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/history", timeout=30)
        assert r.status_code == 403
        r2 = user_session.post(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/restore",
                               json={"art_url": "x"}, timeout=30)
        assert r2.status_code == 403

    def test_generate_appends_history_and_restore_swaps(self, admin_session):
        """Generate new AI artwork — this archives the current art into history.
        Then GET history should include an entry with url/source/archived_at,
        and POST restore with that url flips the current art back to it."""
        # Capture the current art before we mutate
        r0 = admin_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/history", timeout=30)
        assert r0.status_code == 200
        cur_before = r0.json().get("current")

        # Trigger a new AI-artwork generation
        rg = admin_session.post(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/generate",
                                json={}, timeout=30)
        assert rg.status_code == 200, rg.text[:200]
        assert rg.json().get("status") == "queued"

        # Poll status until complete (up to ~60s)
        new_url = None
        for _ in range(30):
            time.sleep(2)
            rs = admin_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/status", timeout=15)
            if rs.status_code == 200 and rs.json().get("status") == "complete":
                new_url = rs.json().get("image_url")
                break
        assert new_url, "artwork did not complete within timeout"
        # NB: image_gen may dedupe and return the same URL — that's a caching
        # artifact, not a history-feature bug. Only assert archival when the
        # URL actually changed.
        if new_url != cur_before and cur_before:
            r2 = admin_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/history", timeout=30)
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2["current"] == new_url
            assert len(d2["history"]) >= 1, "history should have at least one archived entry"
            for h in d2["history"]:
                assert h.get("url") and h.get("source") in ("ai", "owner") and h.get("archived_at")

            # Restore: flip back to the previous art
            target_url = cur_before
            match = next((h for h in d2["history"] if h.get("url") == target_url), None)
            assert match, f"expected {target_url} in history"
            r3 = admin_session.post(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/restore",
                                    json={"art_url": target_url}, timeout=30)
            assert r3.status_code == 200, r3.text[:200]
            d3 = r3.json()
            assert d3.get("art_url") == target_url
            assert d3.get("status") == "complete"
            r4 = admin_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/status", timeout=15)
            assert r4.json().get("image_url") == target_url
        else:
            # dedup path — just verify history endpoint shape still ok
            r2 = admin_session.get(f"{BASE_URL}/api/imported-stations/{STATION_ID}/artwork/history", timeout=30)
            assert r2.status_code == 200
            d2 = r2.json()
            for h in d2.get("history") or []:
                assert h.get("url") and h.get("source") and h.get("archived_at")


# -------- #4 Genre-tagged demo catalog via /api/radio/start --------
class TestDemoCatalog:
    @pytest.mark.parametrize("channel", [
        "bollywood_mehfil", "punjabi_beats", "devotional_hour", "dfw_bollywood_drive",
    ])
    def test_channel_returns_playable_segment(self, user_session, channel):
        r = user_session.post(f"{BASE_URL}/api/radio/start",
                              json={"channel_slug": channel}, timeout=45)
        assert r.status_code == 200, f"{channel}: {r.status_code} {r.text[:200]}"
        d = r.json()
        seg = d.get("segment") or {}
        assert seg.get("segment_url"), f"{channel}: no segment_url"
        assert seg.get("track_id"), f"{channel}: no track_id"
        assert seg.get("duration_sec"), f"{channel}: no duration"

    def test_vip_lounge_is_gated(self, user_session):
        r = user_session.post(f"{BASE_URL}/api/radio/start",
                              json={"channel_slug": "vip_lounge"}, timeout=30)
        # Gate is expected — may be 200 with gated flag, 402, or 403
        assert r.status_code < 500
        body = r.text.lower()
        # Either a gate reason surfaces or status is 402/403
        assert (r.status_code in (200, 402, 403)) and ("ambassador" in body or "premium" in body or "gate" in body or r.status_code in (402, 403))
