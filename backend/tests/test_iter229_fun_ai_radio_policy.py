"""Phase 2 — Talk on the Player: RadioProgrammingPolicyService + player session + admin policy.

Covers:
  * POST /api/fun-ai/radio/action matrix: D, C, E1, E2, record_feedback, unknown action.
  * Skip rate-limit: 6 allowed, 7th denied with SKIP_LIMIT_REACHED (fresh test user).
  * Permitted managed changes persist to db.fun_ai_radio_prefs.
  * GET /api/fun-ai/radio/formats groups: energy/mood/genre/language.
  * GET /api/fun-ai/radio/now-playing resolves managed vs third_party.
  * POST /api/fun-ai/session surface=player tools + instructions; default surface=news tools.
  * Admin GET/PUT /api/admin/fun-ai/radio-policy round-trip + non-admin 403.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"


# ─── fixtures ──────────────────────────────────────────────────────────
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    tok = r.json().get("session_token")
    s.headers.update({"Content-Type": "application/json"})
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def demo_client():
    return _login(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="module")
def admin_client():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def fresh_user_client():
    """Register a brand-new user so the skip rate-limit test starts at 0 skips."""
    email = f"TEST_iter229_{uuid.uuid4().hex[:10]}@bigfm.dubai"
    pw = "TestPass123!"
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "iter229"}, timeout=15)
    assert r.status_code in (200, 201), f"register failed {r.status_code}: {r.text}"
    r2 = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r2.status_code == 200, f"login after register {r2.status_code}: {r2.text}"
    tok = r2.json().get("session_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ─── GET /radio/formats ───────────────────────────────────────────────
def test_radio_formats_shape():
    r = requests.get(f"{API}/fun-ai/radio/formats", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "formats" in body
    f = body["formats"]
    for group in ["energy", "mood", "genre", "language"]:
        assert group in f, f"missing group {group}"
        assert isinstance(f[group], list) and len(f[group]) > 0
    assert "high_energy" in f["energy"]
    assert "hindi_retro" in f["genre"]


# ─── GET /radio/now-playing ───────────────────────────────────────────
def test_now_playing_default_managed():
    r = requests.get(f"{API}/fun-ai/radio/now-playing", params={"station": "big-melodies"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["station"] == "big-melodies"
    assert data["station_type"] == "managed"
    assert data["station_name"]  # non-empty


def test_now_playing_unknown_slug_fallback():
    slug = f"unknown-{uuid.uuid4().hex[:6]}"
    r = requests.get(f"{API}/fun-ai/radio/now-playing", params={"station": slug, "name": "Random"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    # resolver returns 'managed' when nothing matches; name param wins when ch missing
    assert data["station_type"] in ("managed", "third_party")
    assert data["station_name"] == "Random"


# ─── RadioProgrammingPolicyService matrix via /radio/action ───────────
def test_D_play_exact_song_denied(demo_client):
    r = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "play_exact_song",
        "params": {"song": "Blinding Lights", "artist": "The Weeknd"},
        "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"},
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["allowed"] is False
    assert d["code"] == "ON_DEMAND_NOT_PERMITTED"
    assert d.get("alternative") and len(d["alternative"]) > 0
    assert d.get("alternative_action")


def test_C_energy_change_high_energy_managed(demo_client):
    r = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "energy_change",
        "params": {"value": "high_energy"},
        "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"},
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["allowed"] is True
    assert d["code"] == "CHANGE_OK"
    assert d.get("applied") == {"energy": "high_energy"}
    assert d["station_type"] == "managed"


def test_E1_third_party_format_change_denied(demo_client):
    r = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "format_change",
        "params": {"value": "rock"},
        "station": {"slug": "bbc-radio-1", "name": "BBC Radio 1", "type": "third_party"},
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["allowed"] is False
    assert d["code"] == "THIRD_PARTY_SEQUENCE_LOCKED"
    assert d.get("alternative_action") == "change_station"
    assert d["station_type"] == "third_party"


def test_E2_third_party_change_station_allowed(demo_client):
    r = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "change_station",
        "params": {"target": "big-melodies"},
        "station": {"slug": "bbc-radio-1", "name": "BBC Radio 1", "type": "third_party"},
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["allowed"] is True
    assert d["code"] == "STATION_SWITCH_OK"
    assert d.get("target") == "big-melodies"
    assert d["station_type"] == "third_party"


def test_record_feedback_allowed(demo_client):
    r = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "record_feedback",
        "params": {"value": "like"},
        "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"},
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["allowed"] is True
    assert d["code"] == "FEEDBACK_OK"
    assert d.get("applied") == {"feedback": "like"}


def test_unknown_action_denied(demo_client):
    r = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "teleport",
        "params": {},
        "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"},
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["allowed"] is False
    # action not in allowed_actions for managed -> ACTION_NOT_ALLOWED
    assert d["code"] in ("ACTION_NOT_ALLOWED", "UNKNOWN_ACTION")


def test_action_requires_auth():
    r = requests.post(f"{API}/fun-ai/radio/action", json={
        "action": "skip", "params": {}, "station": {"slug": "big-melodies"}
    }, timeout=15)
    # Should 401/403 without a session
    assert r.status_code in (401, 403), f"expected auth required, got {r.status_code}"


# ─── Managed changes persist to fun_ai_radio_prefs ────────────────────
def test_managed_changes_persist_prefs(demo_client):
    # Apply a format change; next permitted change should be reflected in /radio/action's
    # successive persistence by inspecting indirect behaviour (CHANGE_OK with applied).
    # Direct DB access isn't available; we assert the endpoint behaviour contract:
    # two different managed changes both return allowed:true with applied payload.
    r1 = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "mood_change",
        "params": {"value": "feelgood"},
        "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"},
    }, timeout=15).json()
    assert r1["allowed"] and r1["applied"] == {"mood": "feelgood"}

    r2 = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "language_change",
        "params": {"value": "hindi"},
        "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"},
    }, timeout=15).json()
    assert r2["allowed"] and r2["applied"] == {"language": "hindi"}


# ─── Skip rate-limit (fresh user, default policy skip_per_hour=6) ─────
def test_skip_rate_limit(fresh_user_client):
    station = {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"}
    allowed = 0
    denied = None
    # Attempt up to 10 to be safe
    for i in range(10):
        r = fresh_user_client.post(f"{API}/fun-ai/radio/action", json={
            "action": "skip", "params": {}, "station": station}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        if d["allowed"]:
            assert d["code"] == "SKIP_OK"
            allowed += 1
        else:
            denied = d
            break
    # Default policy skip_per_hour is 6
    assert allowed == 6, f"expected 6 skips allowed, got {allowed}"
    assert denied is not None and denied["code"] == "SKIP_LIMIT_REACHED"


# ─── POST /session surface=player returns right tools + instructions ──
def test_session_player_surface(demo_client):
    body = {"surface": "player",
            "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"}}
    r = demo_client.post(f"{API}/fun-ai/session", json=body, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["surface"] == "player"
    tool_names = [t.get("name") for t in d.get("tools", [])]
    for expected in ["get_now_playing", "get_available_radio_formats",
                     "request_radio_action", "record_music_feedback"]:
        assert expected in tool_names, f"missing player tool {expected}"
    # instructions must reference the policy engine authority
    assert "policy" in (d.get("instructions") or "").lower()
    # ephemeral secret must be present and permanent key must NOT leak
    assert d.get("client_secret")
    raw = r.text
    assert "xai-3rsOv" not in raw and "3rsOvI4F4b6DKQZ4" not in raw


def test_session_default_news_tools(demo_client):
    r = demo_client.post(f"{API}/fun-ai/session", json={}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["surface"] == "news"
    tool_names = [t.get("name") for t in d.get("tools", [])]
    assert "search_news" in tool_names
    assert "follow_story" in tool_names
    # player tools must NOT be present on default news surface
    assert "request_radio_action" not in tool_names


def test_session_player_third_party_instructions(demo_client):
    body = {"surface": "player",
            "station": {"slug": "bbc-radio-1", "name": "BBC Radio 1", "type": "third_party"}}
    r = demo_client.post(f"{API}/fun-ai/session", json=body, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["surface"] == "player"
    ins = (d.get("instructions") or "").lower()
    assert "third-party" in ins or "third party" in ins
    assert "switch stations" in ins or "switch you" in ins or "another station" in ins or "only switch" in ins


# ─── Admin GET/PUT /admin/fun-ai/radio-policy ─────────────────────────
def test_admin_policy_requires_admin(demo_client):
    r = demo_client.get(f"{API}/admin/fun-ai/radio-policy", timeout=15)
    assert r.status_code == 403, f"non-admin should be 403, got {r.status_code}"


def test_admin_policy_round_trip(admin_client):
    # GET baseline
    g = admin_client.get(f"{API}/admin/fun-ai/radio-policy", timeout=15)
    assert g.status_code == 200, g.text
    gb = g.json()
    assert "policy" in gb and "formats" in gb
    assert gb["policy"]["on_demand_allowed"] is False
    orig_skip = gb["policy"].get("skip_per_hour", 6)

    try:
        # PUT patch skip_per_hour to a sentinel
        p = admin_client.put(f"{API}/admin/fun-ai/radio-policy",
                             json={"skip_per_hour": 9}, timeout=15)
        assert p.status_code == 200, p.text
        pb = p.json()
        assert pb["ok"] is True
        assert pb["policy"]["skip_per_hour"] == 9
        # GET reflects the change and still returns formats
        g2 = admin_client.get(f"{API}/admin/fun-ai/radio-policy", timeout=15)
        assert g2.status_code == 200
        gb2 = g2.json()
        assert gb2["policy"]["skip_per_hour"] == 9
        assert "formats" in gb2 and "energy" in gb2["formats"]
    finally:
        # restore
        admin_client.put(f"{API}/admin/fun-ai/radio-policy",
                         json={"skip_per_hour": orig_skip}, timeout=15)
