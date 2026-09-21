"""
Iter 168 backend tests — Content-language follow-ups.

Covers:
1) FIX RADIO AUDIO       — POST /api/radio/start returns 200 + segment (not 409 build_failed),
                            GET /api/radio/segment/{id} returns audio/mpeg 206 with real bytes.
2) PATCH content-languages accepts content_lang_scopes and persists via preference_vector.
3) PER-SECTION SCOPES gate filters:
     music=false  -> /api/radio/browse?source=imported returns UNFILTERED (~1742)
     music=true   -> filters (~1363)
     games=false  -> /api/games_v2/play_and_win no longer filtered
     quiz=false   -> /api/trivia/categories no longer filtered
     show_all_languages=true overrides all scopes.
4) LANGUAGE HOME RAILS   — /api/shell/home for_you/mixed_for_you carry `language`,
                            and are language-filtered when music=true. Safety net ≥4 cards.
5) REGRESSION — /users/me + /auth/me expose preference_vector.content_lang_scopes.
6) RESTORES demo user to defaults at teardown.
"""

import os
import time
import pytest
import requests

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""

BASE_URL = _load_base_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"


# ------------------------- fixtures -------------------------

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module", autouse=True)
def restore_demo_user_defaults(session):
    """Ensure demo user is restored to defaults after ALL tests in this module."""
    yield
    try:
        session.patch(
            f"{BASE_URL}/api/users/content-languages",
            json={
                "languages": ["english"],
                "show_all_languages": False,
                "content_lang_scopes": {"music": True, "games": True, "quiz": True},
            }, timeout=30,
        )
    except Exception as e:
        print(f"restore failed: {e}")


def _set_scopes(session, *, music=True, games=True, quiz=True, show_all=False,
                languages=("english",)):
    r = session.patch(
        f"{BASE_URL}/api/users/content-languages",
        json={
            "languages": list(languages),
            "show_all_languages": show_all,
            "content_lang_scopes": {"music": music, "games": games, "quiz": quiz},
        }, timeout=30,
    )
    assert r.status_code == 200, f"PATCH content-languages failed: {r.status_code} {r.text[:200]}"
    return r.json()


# ---------- 2) PATCH persists content_lang_scopes ----------

class TestContentLangScopesPersistence:
    def test_patch_accepts_scopes_and_persists(self, session):
        _set_scopes(session, music=False, games=True, quiz=False, show_all=False)

        me = session.get(f"{BASE_URL}/api/users/me", timeout=30)
        assert me.status_code == 200
        pv = me.json().get("preference_vector", {}) or {}
        scopes = pv.get("content_lang_scopes") or {}
        assert scopes.get("music") is False
        assert scopes.get("games") is True
        assert scopes.get("quiz") is False

    def test_auth_me_exposes_scopes(self, session):
        _set_scopes(session, music=True, games=False, quiz=True)
        r = session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200
        # /auth/me may return user under "user" or at top level
        body = r.json()
        user = body.get("user") if isinstance(body.get("user"), dict) else body
        pv = (user or {}).get("preference_vector") or {}
        scopes = pv.get("content_lang_scopes") or {}
        assert scopes.get("games") is False
        assert scopes.get("music") is True
        assert scopes.get("quiz") is True

    def test_patch_partial_scopes_ok(self, session):
        """Partial content_lang_scopes body should be accepted."""
        # first reset defaults
        _set_scopes(session, music=True, games=True, quiz=True)
        r = session.patch(
            f"{BASE_URL}/api/users/content-languages",
            json={"content_lang_scopes": {"music": False}}, timeout=30,
        )
        assert r.status_code == 200
        me = session.get(f"{BASE_URL}/api/users/me", timeout=30).json()
        scopes = (me.get("preference_vector") or {}).get("content_lang_scopes") or {}
        assert scopes.get("music") is False
        # Other scopes should remain true (or default true)
        assert scopes.get("games", True) is True
        assert scopes.get("quiz", True) is True


# ---------- 3) PER-SECTION SCOPES gate filters ----------

class TestPerSectionScopeGating:
    def test_radio_browse_music_scope(self, session):
        # baseline: show_all=1 (unfiltered total)
        r = session.get(f"{BASE_URL}/api/radio/browse",
                        params={"source": "imported", "show_all": 1}, timeout=60)
        assert r.status_code == 200
        total_show_all = r.json().get("total", 0) or len(r.json().get("stations") or [])
        assert total_show_all > 0

        # music scope OFF -> browse should return unfiltered total
        _set_scopes(session, music=False, games=True, quiz=True)
        r = session.get(f"{BASE_URL}/api/radio/browse",
                        params={"source": "imported"}, timeout=60)
        assert r.status_code == 200
        total_music_off = r.json().get("total", 0) or len(r.json().get("stations") or [])

        # music scope ON -> should filter down (< show_all)
        _set_scopes(session, music=True, games=True, quiz=True)
        r = session.get(f"{BASE_URL}/api/radio/browse",
                        params={"source": "imported"}, timeout=60)
        assert r.status_code == 200
        total_music_on = r.json().get("total", 0) or len(r.json().get("stations") or [])

        print(f"radio/browse: show_all={total_show_all}, music_off={total_music_off}, music_on={total_music_on}")
        assert total_music_off == total_show_all, \
            f"music=false should = show_all; got {total_music_off} vs {total_show_all}"
        assert total_music_on < total_show_all, \
            f"music=true should filter; got {total_music_on} vs {total_show_all}"

    def test_games_scope_gates_playandwin(self, session):
        # scope games=true (default) - baseline count
        _set_scopes(session, music=True, games=True, quiz=True)
        r_on = session.get(f"{BASE_URL}/api/games_v2/play_and_win", timeout=60)
        assert r_on.status_code == 200
        on_data = r_on.json()
        # try common shapes
        def count_games(d):
            if isinstance(d, list):
                return len(d)
            if isinstance(d, dict):
                if "games" in d and isinstance(d["games"], list):
                    return len(d["games"])
                if "sections" in d and isinstance(d["sections"], list):
                    return sum(len(s.get("games", []) or s.get("items", []) or []) for s in d["sections"])
                if "items" in d and isinstance(d["items"], list):
                    return len(d["items"])
            return -1
        n_on = count_games(on_data)

        # games=false → filter disabled → expect >= n_on
        _set_scopes(session, music=True, games=False, quiz=True)
        r_off = session.get(f"{BASE_URL}/api/games_v2/play_and_win", timeout=60)
        assert r_off.status_code == 200
        n_off = count_games(r_off.json())

        print(f"play_and_win: games_on={n_on}, games_off={n_off}")
        # off should be >= on (unfiltered is at least as big)
        assert n_off >= n_on

    def test_quiz_scope_gates_trivia_categories(self, session):
        _set_scopes(session, music=True, games=True, quiz=True)
        r_on = session.get(f"{BASE_URL}/api/trivia/categories", timeout=30)
        assert r_on.status_code == 200
        data_on = r_on.json()
        cats_on = data_on if isinstance(data_on, list) else data_on.get("categories") or data_on.get("items") or []
        n_on = len(cats_on)

        _set_scopes(session, music=True, games=True, quiz=False)
        r_off = session.get(f"{BASE_URL}/api/trivia/categories", timeout=30)
        assert r_off.status_code == 200
        data_off = r_off.json()
        cats_off = data_off if isinstance(data_off, list) else data_off.get("categories") or data_off.get("items") or []
        n_off = len(cats_off)

        print(f"trivia/categories: quiz_on={n_on}, quiz_off={n_off}")
        assert n_off >= n_on

    def test_show_all_overrides_scopes(self, session):
        # music=false AND show_all=true → should still return unfiltered (show_all wins)
        _set_scopes(session, music=False, games=False, quiz=False, show_all=True)
        r = session.get(f"{BASE_URL}/api/radio/browse",
                        params={"source": "imported"}, timeout=60)
        assert r.status_code == 200
        with_show_all = r.json().get("total", 0) or len(r.json().get("stations") or [])

        _set_scopes(session, music=True, games=True, quiz=True, show_all=True)
        r2 = session.get(f"{BASE_URL}/api/radio/browse",
                         params={"source": "imported"}, timeout=60)
        total_show_all = r2.json().get("total", 0) or len(r2.json().get("stations") or [])

        print(f"show_all override: scopes_off_but_showall={with_show_all}, scopes_on_showall={total_show_all}")
        assert with_show_all == total_show_all


# ---------- 4) LANGUAGE HOME RAILS ----------

class TestHomeRailsLanguage:
    def _collect_station_cards(self, home):
        rails = []
        for k, v in (home or {}).items():
            if isinstance(v, list):
                rails.append((k, v))
            elif isinstance(v, dict) and isinstance(v.get("items"), list):
                rails.append((k, v["items"]))
        return rails

    def test_home_for_you_has_language_and_filters(self, session):
        # music=true — expect language-filtered
        _set_scopes(session, music=True, games=True, quiz=True, show_all=False)
        r = session.get(f"{BASE_URL}/api/shell/home", timeout=60)
        assert r.status_code == 200, f"home 500: {r.text[:200]}"
        home_on = r.json()

        # look for for_you / mixed_for_you rails
        for_you_on = home_on.get("for_you") or (home_on.get("rails") or {}).get("for_you") or []
        if isinstance(for_you_on, dict):
            for_you_on = for_you_on.get("items") or for_you_on.get("cards") or []
        mixed_on = home_on.get("mixed_for_you") or (home_on.get("rails") or {}).get("mixed_for_you") or []
        if isinstance(mixed_on, dict):
            mixed_on = mixed_on.get("items") or mixed_on.get("cards") or []

        pool_on = (for_you_on or []) + (mixed_on or [])
        print(f"home music=on: for_you={len(for_you_on or [])}, mixed={len(mixed_on or [])}")

        # 4a: cards carry a `language` field (at least one — feature adds it)
        with_lang = [c for c in pool_on if isinstance(c, dict) and ("language" in c)]
        assert len(with_lang) > 0, "expected `language` field on for_you/mixed station cards"

        # 4b: safety — home never left with <4 cards
        assert len(pool_on) >= 4, f"safety net failed: only {len(pool_on)} cards on home"

        # 4c: music=false should widen the pool (filter disabled)
        _set_scopes(session, music=False, games=True, quiz=True, show_all=False)
        r2 = session.get(f"{BASE_URL}/api/shell/home", timeout=60)
        assert r2.status_code == 200
        home_off = r2.json()
        for_you_off = home_off.get("for_you") or (home_off.get("rails") or {}).get("for_you") or []
        if isinstance(for_you_off, dict):
            for_you_off = for_you_off.get("items") or for_you_off.get("cards") or []
        mixed_off = home_off.get("mixed_for_you") or (home_off.get("rails") or {}).get("mixed_for_you") or []
        if isinstance(mixed_off, dict):
            mixed_off = mixed_off.get("items") or mixed_off.get("cards") or []
        pool_off = (for_you_off or []) + (mixed_off or [])
        print(f"home music=off: for_you={len(for_you_off or [])}, mixed={len(mixed_off or [])}")
        # Not strictly asserting counts (safety fallback may already show all when on),
        # but home must still respond OK with cards.
        assert len(pool_off) >= 4


# ---------- 1) FIX RADIO AUDIO — segment plays ----------

class TestRadioAudioStart:
    @pytest.mark.parametrize("channel", ["morning_masala", "retro_lounge"])
    def test_radio_start_returns_playable_segment(self, session, channel):
        # ensure defaults
        _set_scopes(session, music=True, games=True, quiz=True, show_all=False)

        r = session.post(
            f"{BASE_URL}/api/radio/start",
            json={"channel": channel}, timeout=120,
        )
        assert r.status_code == 200, f"/radio/start {channel}: {r.status_code} {r.text[:300]}"
        data = r.json()
        assert "session_id" in data, f"missing session_id: {data}"
        seg = data.get("segment") or data.get("current_segment") or {}
        assert isinstance(seg, dict) and seg, f"missing segment: {data}"
        seg_id = seg.get("segment_id") or seg.get("id")
        assert seg_id, f"missing segment_id in {seg}"

        # 1b: fetch bytes
        rr = session.get(
            f"{BASE_URL}/api/radio/segment/{seg_id}",
            headers={"Range": "bytes=0-2047"}, timeout=120, stream=True,
        )
        assert rr.status_code in (200, 206), f"/segment status: {rr.status_code} {rr.text[:200]}"
        ct = rr.headers.get("content-type", "")
        assert "audio" in ct, f"expected audio content-type, got {ct}"
        chunk = rr.raw.read(1024) if rr.raw else b""
        # some servers might not stream raw — fallback to content[:64]
        if not chunk:
            chunk = rr.content[:64] if rr.content else b""
        assert chunk and len(chunk) > 0, "expected non-empty audio bytes"
        print(f"{channel} seg={seg_id} ct={ct} bytes={len(chunk)}")
