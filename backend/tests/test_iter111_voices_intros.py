"""Iteration 111 — Voice picker + market voices, per-station intro, art style-note.

Covers:
  #1 Per-station AI intro (owner/admin) — GET/POST intro endpoints
  #2 Voice preview — sample_url + 200 mp3
  #3 Art style-note — persists + shows up in prompt
  #4 Per-market anchor voice — global/dubai/dfw/new_york defaults + admin override
"""
import os
import requests
import pytest

def _read_env(key: str) -> str:
    v = os.environ.get(key)
    if v:
        return v
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    raise RuntimeError(f"{key} not set")


BASE_URL = _read_env("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SID = "imp_96063f25060111e8ae"
UNKNOWN_VOICE = "voice_does_not_exist_zzz"

DUBAI_DEFAULT = "8vqXJx9Riwp7L4KLhsU3"   # Raghav
SARAH = "EXAVITQu4vr4xnSDxMaL"
GEORGE = "JBFqnCBsd6RMkjVDRZzb"
CHARLIE = "IKne3meq5aSn9XLyUdCD"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def demo_sess():
    return _login(DEMO)


@pytest.fixture(scope="module")
def anon_sess():
    return requests.Session()


# ── #2 + #4: /api/news_radio/voices ─────────────────────────────────────
class TestNewsRadioVoices:
    def test_voices_list_shape(self, anon_sess):
        r = anon_sess.get(f"{API}/news_radio/voices", timeout=15)
        assert r.status_code == 200
        data = r.json()
        voices = data.get("voices") or []
        assert len(voices) == 5, f"expected 5 voices, got {len(voices)}"
        # Each voice must have voice_id, name, description, sample_url
        for v in voices:
            assert "voice_id" in v and v["voice_id"]
            assert "name" in v
            assert "sample_url" in v and v["sample_url"].startswith("/api/static/voice_samples/")
            assert v["sample_url"].endswith(f"{v['voice_id']}.mp3")
        assert "global_voice_id" in data
        # market_voices defaults
        mv = data.get("market_voices") or {}
        # Server-side defaults must always be present when unset
        assert mv.get("dubai") == DUBAI_DEFAULT
        assert mv.get("dfw") == SARAH
        assert mv.get("new_york") == SARAH

    def test_voice_sample_mp3_served(self, anon_sess):
        # Test at least one voice sample mp3 serves 200 with audio content-type
        url = f"{API}/static/voice_samples/{DUBAI_DEFAULT}.mp3"
        r = anon_sess.get(url, timeout=20)
        assert r.status_code == 200, f"sample not served: {url}"
        ct = r.headers.get("content-type", "")
        assert "audio" in ct or "mpeg" in ct or "octet" in ct, f"bad content-type: {ct}"
        assert len(r.content) > 500, "sample too small"


# ── #4: admin POST /api/admin/news-radio/voice (per-market) ─────────────
class TestAdminVoiceGate:
    def test_anon_denied(self, anon_sess):
        r = anon_sess.post(f"{API}/admin/news-radio/voice",
                           json={"voice_id": SARAH}, timeout=15)
        assert r.status_code in (401, 403)

    def test_non_admin_denied(self, demo_sess):
        r = demo_sess.post(f"{API}/admin/news-radio/voice",
                           json={"voice_id": SARAH}, timeout=15)
        assert r.status_code in (401, 403)

    def test_unknown_voice_rejected(self, admin_sess):
        r = admin_sess.post(f"{API}/admin/news-radio/voice",
                            json={"voice_id": UNKNOWN_VOICE}, timeout=15)
        assert r.status_code == 400
        body = r.json()
        # detail may wrap error
        err = body.get("detail", body)
        if isinstance(err, dict):
            assert err.get("error") == "unknown_voice"

    def test_set_market_voice_persists(self, admin_sess):
        # Change Dubai to Sarah
        r = admin_sess.post(f"{API}/admin/news-radio/voice",
                            json={"voice_id": SARAH, "market": "dubai"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # Verify GET reflects
        r2 = admin_sess.get(f"{API}/news_radio/voices", timeout=15)
        mv = r2.json().get("market_voices") or {}
        assert mv.get("dubai") == SARAH

        # Restore back to Raghav (Dubai default)
        r3 = admin_sess.post(f"{API}/admin/news-radio/voice",
                             json={"voice_id": DUBAI_DEFAULT, "market": "dubai"}, timeout=15)
        assert r3.status_code == 200

    def test_set_global_voice_persists(self, admin_sess):
        # Get current global
        cur = admin_sess.get(f"{API}/news_radio/voices", timeout=15).json()
        original = cur.get("global_voice_id") or DUBAI_DEFAULT
        # Flip to George
        r = admin_sess.post(f"{API}/admin/news-radio/voice",
                            json={"voice_id": GEORGE}, timeout=15)
        assert r.status_code == 200
        r2 = admin_sess.get(f"{API}/news_radio/voices", timeout=15)
        assert r2.json().get("global_voice_id") == GEORGE
        # Restore
        admin_sess.post(f"{API}/admin/news-radio/voice",
                        json={"voice_id": original}, timeout=15)


# ── #1: Per-station intro (owner/admin) ─────────────────────────────────
class TestStationIntro:
    def test_anon_denied(self, anon_sess):
        r = anon_sess.get(f"{API}/imported-stations/{SID}/intro", timeout=15)
        assert r.status_code in (401, 403)

    def test_non_owner_denied(self, demo_sess):
        r = demo_sess.get(f"{API}/imported-stations/{SID}/intro", timeout=15)
        # demo user is not owner and not admin
        assert r.status_code in (401, 403)

    def test_admin_get_intro_shape(self, admin_sess):
        r = admin_sess.get(f"{API}/imported-stations/{SID}/intro", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data.get("voices"), list)
        assert len(data["voices"]) == 5
        assert "voice_id" in data  # default anchor voice
        # each voice has sample_url
        for v in data["voices"]:
            assert v.get("sample_url", "").startswith("/api/static/voice_samples/")

    def test_admin_generate_intro(self, admin_sess):
        # Use Charlie (short and different from default)
        r = admin_sess.post(f"{API}/imported-stations/{SID}/intro/generate",
                            json={"voice_id": CHARLIE}, timeout=60)
        assert r.status_code == 200, f"intro gen failed: {r.status_code} {r.text[:250]}"
        data = r.json()
        assert data.get("ok") is True
        intro_url = data.get("intro_url")
        assert intro_url and intro_url.startswith("/api/static/station_intros/")
        assert data.get("voice_id") == CHARLIE

        # Fetch the mp3
        mp3 = requests.get(f"{BASE_URL}{intro_url}", timeout=20)
        assert mp3.status_code == 200
        ct = mp3.headers.get("content-type", "")
        assert "audio" in ct or "mpeg" in ct or "octet" in ct
        assert len(mp3.content) > 1000

    def test_admin_generate_unknown_voice_rejected(self, admin_sess):
        r = admin_sess.post(f"{API}/imported-stations/{SID}/intro/generate",
                            json={"voice_id": UNKNOWN_VOICE}, timeout=15)
        assert r.status_code == 400

    def test_non_owner_generate_denied(self, demo_sess):
        r = demo_sess.post(f"{API}/imported-stations/{SID}/intro/generate",
                           json={"voice_id": CHARLIE}, timeout=15)
        assert r.status_code in (401, 403)


# ── #3: Art style-note ──────────────────────────────────────────────────
class TestArtStyleNote:
    def test_style_note_included_in_prompt_and_persisted(self, admin_sess):
        note = "TEST_neon_cyberpunk_moody_purple"
        r = admin_sess.post(
            f"{API}/imported-stations/{SID}/artwork/generate",
            json={"style_note": note}, timeout=30)
        assert r.status_code == 200, f"gen failed: {r.status_code} {r.text[:250]}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("style_note") == note
        prompt = data.get("prompt") or ""
        assert "Style direction" in prompt, f"prompt missing style direction: {prompt[:200]}"
        assert note in prompt, "style_note text not in prompt"

    def test_non_owner_denied(self, demo_sess):
        r = demo_sess.post(
            f"{API}/imported-stations/{SID}/artwork/generate",
            json={"style_note": "hax"}, timeout=15)
        assert r.status_code in (401, 403)
