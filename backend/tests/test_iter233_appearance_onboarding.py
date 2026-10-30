# Iter233 — Light/Dark/System appearance onboarding (web + mobile share /api/shell/prefs)
# Verifies:
#  - GET /api/shell/prefs returns a theme value
#  - PUT /api/shell/prefs accepts light|dark|system and round-trips (persisted)
#  - Invalid theme values are rejected (or at minimum do not corrupt the stored value)
#  - Cross-surface: value set on one session is visible from a fresh session for the SAME user
import os
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")

BASE_URL = _load_backend_url()

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    return _login(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


class TestShellPrefsTheme:
    """GET/PUT /api/shell/prefs theme round-trip (shared by web + mobile)."""

    def test_get_returns_theme_field(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/prefs", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "theme" in data, f"theme missing from prefs response: {data}"
        assert data["theme"] in ("light", "dark", "system")

    @pytest.mark.parametrize("theme", ["light", "dark", "system"])
    def test_put_accepts_valid_theme_and_persists(self, demo_session, theme):
        r = demo_session.put(
            f"{BASE_URL}/api/shell/prefs", json={"theme": theme}, timeout=15
        )
        assert r.status_code == 200, f"PUT {theme} failed: {r.status_code} {r.text[:200]}"
        # response should echo the saved theme
        body = r.json()
        # some impls return {theme: ...}, some return full prefs
        assert body.get("theme") == theme, f"PUT echo mismatch: {body}"

        # verify persistence via GET
        g = demo_session.get(f"{BASE_URL}/api/shell/prefs", timeout=15)
        assert g.status_code == 200
        assert g.json().get("theme") == theme, f"GET after PUT mismatch: {g.json()}"

    def test_invalid_theme_rejected_or_ignored(self, demo_session):
        # set a known-good value first
        demo_session.put(f"{BASE_URL}/api/shell/prefs", json={"theme": "light"}, timeout=15)
        r = demo_session.put(
            f"{BASE_URL}/api/shell/prefs", json={"theme": "neon"}, timeout=15
        )
        # Either reject (4xx) or accept-but-coerce; MUST NOT return "neon" as the saved theme
        g = demo_session.get(f"{BASE_URL}/api/shell/prefs", timeout=15).json()
        assert g.get("theme") in ("light", "dark", "system"), (
            f"invalid theme corrupted store: {g}"
        )


class TestCrossSurfaceSync:
    """A theme set from one session (e.g., web) is visible from a new session (e.g., mobile)."""

    def test_theme_syncs_across_fresh_sessions(self):
        # Session A — set to dark
        a = _login(DEMO_EMAIL, DEMO_PASS)
        rp = a.put(f"{BASE_URL}/api/shell/prefs", json={"theme": "dark"}, timeout=15)
        assert rp.status_code == 200

        # Session B — fresh login, should see dark
        b = _login(DEMO_EMAIL, DEMO_PASS)
        g = b.get(f"{BASE_URL}/api/shell/prefs", timeout=15)
        assert g.status_code == 200
        assert g.json().get("theme") == "dark", f"cross-session sync failed: {g.json()}"

        # Flip back to system from B, verify A sees it too
        b.put(f"{BASE_URL}/api/shell/prefs", json={"theme": "system"}, timeout=15)
        g2 = a.get(f"{BASE_URL}/api/shell/prefs", timeout=15)
        assert g2.json().get("theme") == "system", f"reverse sync failed: {g2.json()}"

        # cleanup — leave as light for other tests
        a.put(f"{BASE_URL}/api/shell/prefs", json={"theme": "light"}, timeout=15)


class TestAnonBehavior:
    """Anon users: GET should work (defaults), PUT may 401 — don't crash."""

    def test_anon_get_returns_default(self):
        r = requests.get(f"{BASE_URL}/api/shell/prefs", timeout=15)
        # Anon may be allowed with a default, or 401 — just assert no 500
        assert r.status_code < 500, r.text
