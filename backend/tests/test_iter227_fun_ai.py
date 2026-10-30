"""FUUSIC Fun AI Phase 1 — Interactive News voice pilot.

Backend endpoint tests. The permanent XAI key must NEVER appear in responses.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Permanent key substring that must never leak
LEAK_SUBSTR = "3rsOvI4F4b6DKQZ4"
LEAK_PREFIX = "xai-3rsOv"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"


def _login(email: str, password: str):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("session_token") or body.get("token")
    return s, tok, body


@pytest.fixture(scope="module")
def demo():
    s, tok, _ = _login(DEMO_EMAIL, DEMO_PASS)
    return s, tok


@pytest.fixture(scope="module")
def admin():
    s, tok, _ = _login(ADMIN_EMAIL, ADMIN_PASS)
    return s, tok


# ─── 1. config: anonymous OK ──────────────────────────────────────────
def test_config_anonymous():
    r = requests.get(f"{API}/fun-ai/config", timeout=15)
    assert r.status_code == 200
    j = r.json()
    for k in ("enabled", "news_enabled", "sponsorship_enabled",
              "voice_provider", "voice_model", "ws_url", "configured",
              "voice_available", "personalities"):
        assert k in j, f"missing {k}"
    assert j["voice_provider"] == "grok"
    assert j["voice_model"]  # not empty
    assert j["ws_url"].startswith("wss://api.x.ai/v1/realtime")
    assert j["configured"] is True
    assert j["voice_available"] is True
    assert LEAK_SUBSTR not in r.text
    assert LEAK_PREFIX not in r.text


# ─── 2. session: auth required, no key leak, correct shape ──────────
def test_session_requires_auth():
    r = requests.post(f"{API}/fun-ai/session", json={}, timeout=15)
    assert r.status_code in (401, 403), f"got {r.status_code}"


def test_session_success_no_leak(demo):
    s, _ = demo
    r = s.post(f"{API}/fun-ai/session", json={}, timeout=20)
    assert r.status_code == 200, f"session failed: {r.status_code} {r.text[:300]}"
    j = r.json()
    for k in ("client_secret", "expires_at", "ws_url", "model",
              "session_id", "voice", "instructions", "tools"):
        assert k in j, f"missing {k}"
    assert isinstance(j["client_secret"], str) and len(j["client_secret"]) > 10
    assert j["ws_url"].startswith("wss://api.x.ai/v1/realtime")
    assert "model=" in j["ws_url"]
    # CRITICAL: no permanent key leak
    txt = r.text
    assert LEAK_SUBSTR not in txt, "PERMANENT KEY LEAKED in session response"
    assert LEAK_PREFIX not in txt, "PERMANENT xai-3rsOv prefix in response"
    # tools: search_news
    tools = j["tools"]
    assert isinstance(tools, list) and len(tools) >= 1
    assert any(t.get("name") == "search_news" for t in tools)


# ─── 3. session/end: records seconds ────────────────────────────────
def test_session_end_ok(demo):
    s, _ = demo
    r = s.post(f"{API}/fun-ai/session/end",
               json={"voice_seconds": 1}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ─── 4. news/briefing: verified source-grounded articles ────────────
def test_news_briefing_shape():
    r = requests.get(f"{API}/fun-ai/news/briefing?limit=4", timeout=20)
    assert r.status_code == 200
    j = r.json()
    assert "program" in j and "sponsor" in j
    assert "voice_available" in j
    program = j["program"]
    assert isinstance(program, list)
    if program:
        for a in program:
            assert a.get("status") == "verified"
            assert a.get("source_name")
            assert a.get("url")
            assert a.get("retrieved_at")
            assert a.get("title")
    assert LEAK_SUBSTR not in r.text


# ─── 5. news/search tool endpoint (auth) ────────────────────────────
def test_news_search_auth_required():
    r = requests.post(f"{API}/fun-ai/news/search",
                      json={"query": "test"}, timeout=15)
    assert r.status_code in (401, 403)


def test_news_search_returns_sources(demo):
    s, _ = demo
    r = s.post(f"{API}/fun-ai/news/search",
               json={"query": "news"}, timeout=25)
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert "articles" in j and "count" in j and "disclaimer" in j
    for a in j["articles"]:
        assert a.get("source_name")
        assert a.get("url")
        assert a.get("retrieved_at")


# ─── 6. usage: premium demo = 60 min ────────────────────────────────
def test_usage_premium(demo):
    s, _ = demo
    r = s.get(f"{API}/fun-ai/usage", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["allowance_minutes"] == 60
    assert j["max_sessions"] == 20
    assert j["is_premium"] is True
    assert "used_minutes" in j and "sessions_today" in j


# ─── 7. admin sponsor: GET/PUT access control + persistence ─────────
def test_sponsor_non_admin_forbidden(demo):
    s, _ = demo
    r = s.get(f"{API}/admin/fun-ai/news-sponsor", timeout=15)
    assert r.status_code in (401, 403), f"expected 403 got {r.status_code}"
    r2 = s.put(f"{API}/admin/fun-ai/news-sponsor",
               json={"enabled": True, "sponsor_name": "Hack",
                     "opening_line": "x"}, timeout=15)
    assert r2.status_code in (401, 403)


def test_sponsor_admin_put_then_briefing_reflects(admin):
    s, _ = admin
    # PUT enabled sponsor
    payload = {"enabled": True,
               "sponsor_name": "QA Test Sponsor",
               "opening_line": "Brought to you by our QA partner."}
    r = s.put(f"{API}/admin/fun-ai/news-sponsor", json=payload, timeout=15)
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j.get("ok") is True
    sp = j.get("sponsor") or {}
    assert sp.get("enabled") is True
    assert sp.get("sponsor_name") == "QA Test Sponsor"

    # GET back
    g = s.get(f"{API}/admin/fun-ai/news-sponsor", timeout=15)
    assert g.status_code == 200
    gs = g.json().get("sponsor") or {}
    assert gs.get("sponsor_name") == "QA Test Sponsor"
    assert gs.get("enabled") is True

    # Briefing should reflect enabled sponsor
    b = requests.get(f"{API}/fun-ai/news/briefing", timeout=20)
    assert b.status_code == 200
    bs = b.json().get("sponsor") or {}
    assert bs.get("enabled") is True
    assert bs.get("sponsor_name") == "QA Test Sponsor"

    # Teardown — disable sponsor so it doesn't bleed into UI tests later
    s.put(f"{API}/admin/fun-ai/news-sponsor",
          json={"enabled": False, "sponsor_name": "",
                "opening_line": "", "closing_line": ""}, timeout=15)


# ─── 8. quota gating logic (verify path, no brute force) ─────────────
def test_quota_logic_exists():
    """Smoke verify the gating constants / endpoints are present.
    Full 20-session brute force avoided to not exhaust xAI daily quota."""
    from backend.services import fun_ai_service as svc  # type: ignore
    assert svc.max_sessions_per_day() == 20
    assert svc.allowance_minutes({"is_premium": True}) == 60
    assert svc.allowance_minutes({"is_premium": False}) == 10
