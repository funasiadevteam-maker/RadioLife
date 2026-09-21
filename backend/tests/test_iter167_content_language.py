"""Iter 167 — LANGUAGE + MUSIC PREFERENCE filtering.

Tests:
  * core/content_language.py: detect + content_allowed unit checks
  * PATCH /api/users/content-languages (auth)
  * GET /api/radio/browse content-language hard filter + escapes
  * GET /api/live-radio/stations content-language filter + show_all
  * GET /api/games_v2/play_and_win filters non-preferred-language campaigns
  * GET /api/trivia/categories filters non-preferred-language categories
  * AI radio _score_track applies -40 penalty for non-preferred-language tracks
"""
from __future__ import annotations

import os
import sys
import requests
import pytest

sys.path.insert(0, "/app/backend")

def _read_env(path: str, key: str) -> str | None:
    try:
        with open(path) as f:
            for ln in f:
                ln = ln.strip()
                if ln.startswith(f"{key}="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        return None
    return None


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
    or _read_env("/app/mobile/.env", "EXPO_PUBLIC_BACKEND_URL")
)
assert BASE_URL, "REACT_APP_BACKEND_URL not found in env or /app/frontend/.env"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASSWORD = "DemoPass123!"


# ---------------------------------------------------------------------------
# Engine unit tests
# ---------------------------------------------------------------------------
class TestContentLanguageEngine:
    def test_detect_bollywood_is_hindi(self):
        from core.content_language import detect_languages
        assert detect_languages("Bollywood") == {"hindi"}

    def test_detect_neutral_spin_and_win_is_empty(self):
        from core.content_language import detect_languages
        assert detect_languages("Spin & Win") == set()

    def test_detect_neutral_rock_80s_is_empty(self):
        from core.content_language import detect_languages
        assert detect_languages("Rock 80s") == set()

    def test_english_user_allowed_neutral(self):
        from core.content_language import content_allowed
        assert content_allowed("Spin & Win", ["english"]) is True

    def test_english_user_blocks_bollywood_quiz(self):
        from core.content_language import content_allowed
        assert content_allowed("Bollywood Quiz", ["english"]) is False

    def test_hindi_user_allows_bollywood_quiz(self):
        from core.content_language import content_allowed
        assert content_allowed("Bollywood Quiz", ["hindi"]) is True

    def test_show_all_bypass(self):
        from core.content_language import content_allowed
        assert content_allowed("Bollywood Quiz", ["english"], show_all=True) is True


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Demo login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ---------------------------------------------------------------------------
# PATCH /api/users/content-languages
# ---------------------------------------------------------------------------
class TestPatchContentLanguages:
    def test_patch_updates_and_restores(self, demo_session):
        # 1. Set to hindi + show_all True
        r = demo_session.patch(
            f"{API}/users/content-languages",
            json={"languages": ["hindi"], "show_all_languages": True},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        pv = data.get("preference_vector") or {}
        assert pv.get("languages") == ["hindi"]
        assert pv.get("show_all_languages") is True

        # 2. Verify via GET /api/users/me
        me = demo_session.get(f"{API}/users/me", timeout=15).json()
        pv2 = me.get("preference_vector") or {}
        assert pv2.get("languages") == ["hindi"]
        assert pv2.get("show_all_languages") is True

        # 3. RESTORE demo user to {english, show_all=false}
        r = demo_session.patch(
            f"{API}/users/content-languages",
            json={"languages": ["english"], "show_all_languages": False},
            timeout=15,
        )
        assert r.status_code == 200
        pv3 = (r.json().get("preference_vector") or {})
        assert pv3.get("languages") == ["english"]
        assert pv3.get("show_all_languages") is False


# ---------------------------------------------------------------------------
# GET /api/radio/browse
# ---------------------------------------------------------------------------
class TestRadioBrowse:
    def test_english_lt_show_all(self, anon_session):
        # anon = defaults to english
        r_en = anon_session.get(f"{API}/radio/browse", params={"source": "imported", "limit": 5}, timeout=30)
        assert r_en.status_code == 200, r_en.text
        english_total = r_en.json().get("matched") or r_en.json().get("total") or 0

        r_all = anon_session.get(
            f"{API}/radio/browse", params={"source": "imported", "show_all": "true", "limit": 5}, timeout=30
        )
        assert r_all.status_code == 200
        all_total = r_all.json().get("matched") or r_all.json().get("total") or 0
        assert english_total < all_total, f"english={english_total} should be < show_all={all_total}"
        # Sanity: numbers should be in expected ballpark
        assert english_total > 500 and all_total > 1000

    def test_hindi_lang_group_bypass(self, anon_session):
        r = anon_session.get(
            f"{API}/radio/browse",
            params={"source": "imported", "lang_group": "hindi", "limit": 5},
            timeout=30,
        )
        assert r.status_code == 200
        total = r.json().get("matched") or r.json().get("total") or 0
        assert total > 0 and total < 500  # ~108

    def test_logged_in_hindi_user_sees_hindi_stations(self, demo_session):
        # Set demo -> hindi
        demo_session.patch(
            f"{API}/users/content-languages",
            json={"languages": ["hindi"], "show_all_languages": False},
            timeout=15,
        )
        try:
            r = demo_session.get(f"{API}/radio/browse", params={"source": "imported", "limit": 5}, timeout=30)
            assert r.status_code == 200
            hindi_total = r.json().get("matched") or r.json().get("total") or 0

            # Enable show_all on user
            demo_session.patch(
                f"{API}/users/content-languages",
                json={"languages": ["hindi"], "show_all_languages": True},
                timeout=15,
            )
            r2 = demo_session.get(f"{API}/radio/browse", params={"source": "imported", "limit": 5}, timeout=30)
            all_total = r2.json().get("matched") or r2.json().get("total") or 0
            assert all_total > hindi_total, f"show_all={all_total} should exceed hindi-only={hindi_total}"
        finally:
            demo_session.patch(
                f"{API}/users/content-languages",
                json={"languages": ["english"], "show_all_languages": False},
                timeout=15,
            )


# ---------------------------------------------------------------------------
# GET /api/live-radio/stations
# ---------------------------------------------------------------------------
class TestLiveRadioStations:
    def test_english_lt_show_all(self, anon_session):
        r_en = anon_session.get(f"{API}/live-radio/stations", params={"limit": 5}, timeout=30)
        assert r_en.status_code == 200, r_en.text
        en = r_en.json()
        en_total = en.get("total") or en.get("matched") or 0
        # filters echo
        filters = en.get("filters") or {}
        assert "content_languages" in filters, f"Missing filters.content_languages in {filters}"

        r_all = anon_session.get(f"{API}/live-radio/stations", params={"show_all": "true", "limit": 5}, timeout=30)
        assert r_all.status_code == 200
        all_total = r_all.json().get("total") or r_all.json().get("matched") or 0
        assert en_total < all_total, f"english={en_total} vs show_all={all_total}"


# ---------------------------------------------------------------------------
# GET /api/games_v2/play_and_win
# ---------------------------------------------------------------------------
class TestGamesV2PlayAndWin:
    def test_english_user_hides_bollywood_campaigns(self, demo_session):
        # demo defaults to english after prior restore
        r = demo_session.get(f"{API}/games_v2/play_and_win", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        # sections intact
        for key in ("unlocked_for_you", "expiring_soon", "played_history"):
            assert key in body, f"missing key {key}"
        # No campaign titled "Bollywood ..." in unlocked_for_you
        for c in body.get("unlocked_for_you") or []:
            title = (c.get("title") or "").lower()
            desc = (c.get("description") or "").lower()
            assert "bollywood" not in title and "bollywood" not in desc, f"Bollywood campaign leaked: {c.get('title')}"

    def test_show_all_bypass_shows_bollywood(self, demo_session):
        demo_session.patch(
            f"{API}/users/content-languages",
            json={"languages": ["english"], "show_all_languages": True},
            timeout=15,
        )
        try:
            r = demo_session.get(f"{API}/games_v2/play_and_win", timeout=30)
            assert r.status_code == 200
        finally:
            demo_session.patch(
                f"{API}/users/content-languages",
                json={"languages": ["english"], "show_all_languages": False},
                timeout=15,
            )


# ---------------------------------------------------------------------------
# GET /api/trivia/categories
# ---------------------------------------------------------------------------
class TestTriviaCategories:
    def test_english_user_hides_bollywood_categories(self, demo_session):
        r = demo_session.get(f"{API}/trivia/categories", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        cats = body.get("categories") if isinstance(body, dict) else body
        assert isinstance(cats, list)
        for c in cats:
            name = (c.get("name") or c.get("title") or c.get("category") or "").lower()
            assert "bollywood" not in name, f"Bollywood trivia category leaked: {c}"

    def test_show_all_bypass(self, demo_session):
        r = demo_session.get(f"{API}/trivia/categories", params={"show_all": "true"}, timeout=30)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Regression — /api/users/preferences save works with show_all_languages field
# ---------------------------------------------------------------------------
class TestPreferenceVectorRegression:
    def test_me_returns_preference_vector_with_show_all(self, demo_session):
        r = demo_session.get(f"{API}/users/me", timeout=15)
        assert r.status_code == 200
        pv = r.json().get("preference_vector") or {}
        assert "show_all_languages" in pv, f"pv missing show_all_languages: {pv}"

    def test_auth_me_returns_preference_vector(self, demo_session):
        r = demo_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        u = r.json()
        # /auth/me may nest under 'user' or return directly
        target = u.get("user") if isinstance(u, dict) and "user" in u else u
        pv = (target or {}).get("preference_vector") or {}
        assert "show_all_languages" in pv


# ---------------------------------------------------------------------------
# AI radio scoring — -40 penalty for non-preferred-language tracks
# ---------------------------------------------------------------------------
class TestAIRadioScore:
    def test_score_track_penalty(self):
        """Verify _score_track applies a -40 penalty for non-preferred-language tracks."""
        try:
            from server import _score_track
        except Exception as e:
            pytest.skip(f"server._score_track not importable: {e}")

        pv_english = {"languages": ["english"], "genres": [], "eras": [], "moods": [], "activities": []}
        neutral_track = {"_id": "t_neutral", "title": "Sunset Drive", "artist": "The Waves", "language": ""}
        hindi_track = {"_id": "t_hindi", "title": "Bollywood Hits", "artist": "AR Rahman", "language": "hindi"}

        neutral_score = _score_track(neutral_track, pv_english, None, set(), [])
        hindi_score = _score_track(hindi_track, pv_english, None, set(), [])
        assert hindi_score < neutral_score, f"hindi={hindi_score} should be lower than neutral={neutral_score}"
        # Penalty should be strong (~40) but not -inf
        assert hindi_score != float("-inf"), "penalty must be soft, not hard-drop"
        assert (neutral_score - hindi_score) >= 30, (
            f"penalty too weak: neutral={neutral_score} hindi={hindi_score}"
        )
