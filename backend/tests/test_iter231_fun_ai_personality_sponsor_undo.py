"""Iter 231 — Fun AI follow-ups backend tests.

Covers:
  * RJ personalities: GET /fun-ai/preferences (returns personality + personalities[5]),
    PUT /fun-ai/preferences {personality} persists; GET /fun-ai/config exposes
    personalities[] objects + default_personality='friendly'.
  * Personality feeds session: POST /fun-ai/session (news default) and
    {surface:'player',station} both return personality + personality_label and
    instructions START with 'PERSONALITY — <Label>:'.
  * Sponsor admin: GET/PUT /admin/fun-ai/news-sponsor (admin only; non-admin 403).
    PUT {enabled:true, ...} persists; GET round-trips; and
    /fun-ai/news/briefing returns sponsor.enabled=true with the chosen name.
    Teardown PUT it back to enabled:false.
  * Radio undo: POST /fun-ai/radio/action energy_change (managed) returns
    applied={energy:...}; POST /fun-ai/radio/undo {fields:['energy']} returns
    ok + undone=['prefs.energy'].
"""
import os
import uuid
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"


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
def fresh_client():
    """Register a brand-new user so session-limit quota is fresh."""
    email = f"TEST_iter231_{uuid.uuid4().hex[:10]}@bigfm.dubai"
    pw = "TestPass123!"
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "iter231"}, timeout=15)
    assert r.status_code in (200, 201), f"register failed {r.status_code}: {r.text}"
    r2 = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r2.status_code == 200, f"login after register {r2.status_code}: {r2.text}"
    tok = r2.json().get("session_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ─── Config endpoint exposes personalities[] + default_personality ─────
def test_config_personalities_and_default():
    r = requests.get(f"{API}/fun-ai/config", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "personalities" in d and isinstance(d["personalities"], list)
    assert len(d["personalities"]) == 5
    for p in d["personalities"]:
        assert "id" in p and "label" in p
    assert d.get("default_personality") == "friendly"


# ─── Preferences GET + PUT round-trip ─────────────────────────────────
def test_preferences_get_initial_shape(demo_client):
    r = demo_client.get(f"{API}/fun-ai/preferences", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "personality" in d
    assert isinstance(d.get("personalities"), list) and len(d["personalities"]) == 5


def test_preferences_put_calm_persists(demo_client):
    # Set to 'calm'
    r = demo_client.put(f"{API}/fun-ai/preferences", json={"personality": "calm"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("personality") == "calm"

    # GET reflects it
    g = demo_client.get(f"{API}/fun-ai/preferences", timeout=15)
    assert g.status_code == 200
    assert g.json().get("personality") == "calm"


# ─── Personality feeds POST /session (news default) ───────────────────
def test_session_news_injects_personality(fresh_client):
    # Set saved preference to 'calm' for determinism
    fresh_client.put(f"{API}/fun-ai/preferences", json={"personality": "calm"}, timeout=15)
    r = fresh_client.post(f"{API}/fun-ai/session", json={}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("surface") == "news"
    assert d.get("personality") == "calm"
    assert d.get("personality_label")
    ins = d.get("instructions") or ""
    assert ins.startswith(f"PERSONALITY — {d['personality_label']}:"), f"instructions did not start with personality header: {ins[:120]!r}"


# ─── Personality feeds POST /session surface=player ───────────────────
def test_session_player_injects_personality(fresh_client):
    fresh_client.put(f"{API}/fun-ai/preferences", json={"personality": "friendly"}, timeout=15)
    body = {"surface": "player",
            "station": {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"}}
    r = fresh_client.post(f"{API}/fun-ai/session", json=body, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("surface") == "player"
    assert d.get("personality") == "friendly"
    assert d.get("personality_label")
    ins = d.get("instructions") or ""
    assert ins.startswith(f"PERSONALITY — {d['personality_label']}:"), f"player instructions did not start with personality header: {ins[:140]!r}"


# ─── Sponsor admin: non-admin forbidden ───────────────────────────────
def test_sponsor_non_admin_forbidden(demo_client):
    g = demo_client.get(f"{API}/admin/fun-ai/news-sponsor", timeout=15)
    assert g.status_code == 403, f"expected 403, got {g.status_code}: {g.text}"
    p = demo_client.put(f"{API}/admin/fun-ai/news-sponsor",
                        json={"enabled": True, "sponsor_name": "Hack", "opening_line": "x"}, timeout=15)
    assert p.status_code == 403, f"expected 403, got {p.status_code}: {p.text}"


# ─── Sponsor admin: round-trip + briefing surfaces it; disabled at end ─
def test_sponsor_round_trip_and_briefing(admin_client):
    # Enable
    payload = {
        "enabled": True,
        "sponsor_name": "TEST_SponsorCo",
        "opening_line": "Brought to you by TEST_SponsorCo — enjoy today's briefing.",
        "closing_line": "Thanks again to TEST_SponsorCo.",
    }
    p = admin_client.put(f"{API}/admin/fun-ai/news-sponsor", json=payload, timeout=15)
    assert p.status_code == 200, p.text
    pb = p.json()
    assert pb.get("ok") is True
    sp = pb.get("sponsor") or {}
    assert sp.get("enabled") is True
    assert sp.get("sponsor_name") == "TEST_SponsorCo"
    assert sp.get("opening_line") == payload["opening_line"]

    # GET reflects
    g = admin_client.get(f"{API}/admin/fun-ai/news-sponsor", timeout=15)
    assert g.status_code == 200
    gs = (g.json() or {}).get("sponsor") or {}
    assert gs.get("enabled") is True
    assert gs.get("sponsor_name") == "TEST_SponsorCo"

    try:
        # Briefing exposes sponsor.enabled=true + name
        b = admin_client.get(f"{API}/fun-ai/news/briefing", timeout=20)
        assert b.status_code == 200, b.text
        body = b.json() or {}
        s = body.get("sponsor") or {}
        assert s.get("enabled") is True, f"briefing sponsor not enabled: {s}"
        assert s.get("sponsor_name") == "TEST_SponsorCo"
    finally:
        # Teardown — disable sponsor to leave no sponsor showing
        d = admin_client.put(f"{API}/admin/fun-ai/news-sponsor",
                             json={"enabled": False, "sponsor_name": "",
                                   "opening_line": "", "closing_line": ""}, timeout=15)
        assert d.status_code == 200, d.text
        assert d.json().get("sponsor", {}).get("enabled") is False
        # Confirm briefing no longer flags sponsor enabled
        b2 = admin_client.get(f"{API}/fun-ai/news/briefing", timeout=20)
        assert b2.status_code == 200
        assert ((b2.json() or {}).get("sponsor") or {}).get("enabled") is False


# ─── Radio action apply + undo round-trip ─────────────────────────────
def test_radio_action_energy_change_apply_and_undo(demo_client):
    station = {"slug": "big-melodies", "name": "Big Melodies", "type": "managed"}
    # Apply energy change
    r = demo_client.post(f"{API}/fun-ai/radio/action", json={
        "action": "energy_change",
        "params": {"value": "chill"},
        "station": station,
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("allowed") is True
    assert d.get("code") == "CHANGE_OK"
    assert d.get("applied") == {"energy": "chill"}

    # Undo it
    u = demo_client.post(f"{API}/fun-ai/radio/undo", json={"fields": ["energy"]}, timeout=15)
    assert u.status_code == 200, u.text
    ub = u.json()
    assert ub.get("ok") is True
    assert ub.get("undone") == ["prefs.energy"], f"unexpected undone: {ub}"


def test_radio_undo_ignores_invalid_fields(demo_client):
    # Only valid identifier fields should be unset
    u = demo_client.post(f"{API}/fun-ai/radio/undo",
                         json={"fields": ["energy; DROP TABLE", "", "mood"]}, timeout=15)
    assert u.status_code == 200
    ub = u.json()
    assert ub.get("ok") is True
    # 'energy; DROP TABLE' is not a Python identifier -> filtered out
    assert ub.get("undone") == ["prefs.mood"]
