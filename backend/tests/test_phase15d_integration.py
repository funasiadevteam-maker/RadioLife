"""
Phase 15d integration tests against the live preview backend.

Covers acceptance criteria:
- /api/geo/me anon (mock dubai)
- /api/auth/login admin
- PATCH /api/users/me/market (new_york, london, atlantis=400, null)
- /api/geo/me with override
- /api/news/local (override & dubai)
- regression: /api/channels, /api/auth/me, /api/bigcoin/me
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# Fallback to reading from frontend/.env if env var is not set in shell.
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

assert BASE_URL, "REACT_APP_BACKEND_URL missing"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(session):
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("session_token") or data.get("token") or data.get("access_token")
    assert token, f"no session_token in login response: {data}"
    return token


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ─── 1. /api/geo/me anonymous returns mock Dubai ─────────────────────────────
def test_geo_me_anon_returns_mock_dubai(session):
    r = session.get(f"{BASE_URL}/api/geo/me", timeout=10)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("country") == "AE"
    assert data.get("market") == "dubai"
    assert "mock" in (data.get("source") or "").lower()


# ─── 2. PATCH market → new_york persists ─────────────────────────────────────
def test_patch_market_new_york(session, auth_headers):
    r = session.patch(
        f"{BASE_URL}/api/users/me/market",
        json={"market": "new_york"},
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("ok") is True
    assert data.get("preferred_market") == "new_york"
    supported = data.get("supported") or []
    assert len(supported) >= 5, f"expected ≥5 markets, got {supported}"
    assert "dfw" in supported, "Phase 15d.1 must register DFW as a market"


# ─── 3. /api/geo/me with override = new_york ────────────────────────────────
def test_geo_me_after_ny_override(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/geo/me", headers=auth_headers, timeout=10)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("market") == "new_york"
    assert data.get("city") == "New York"
    assert data.get("timezone") == "America/New_York"
    assert data.get("source") == "override"


# ─── 4. /api/news/local for NY ───────────────────────────────────────────────
def test_news_local_new_york(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/news/local?limit=3", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("market") == "new_york"
    items = data.get("items") or []
    assert 3 <= len(items) <= 5 or len(items) == 3
    blob = " ".join(i.get("title", "") + " " + i.get("summary", "") for i in items)
    assert any(k in blob for k in ("Brooklyn", "MTA", "bodega", "New York")), (
        f"NY headlines missing local keywords: {blob[:300]}"
    )
    assert "Dubai" not in blob


# ─── 5. PATCH market → london ────────────────────────────────────────────────
def test_patch_market_london_and_verify(session, auth_headers):
    r = session.patch(
        f"{BASE_URL}/api/users/me/market",
        json={"market": "london"},
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("preferred_market") == "london"

    r2 = session.get(f"{BASE_URL}/api/geo/me", headers=auth_headers, timeout=10)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("market") == "london"
    assert d2.get("city") == "London"


# ─── 6. PATCH market → atlantis (400) ────────────────────────────────────────
def test_patch_market_unsupported(session, auth_headers):
    r = session.patch(
        f"{BASE_URL}/api/users/me/market",
        json={"market": "atlantis"},
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:200]}"


# ─── 7. PATCH market → null reverts to mock dubai ────────────────────────────
def test_patch_market_null_clears_override(session, auth_headers):
    r = session.patch(
        f"{BASE_URL}/api/users/me/market",
        json={"market": None},
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("ok") is True
    assert data.get("preferred_market") is None

    r2 = session.get(f"{BASE_URL}/api/geo/me", headers=auth_headers, timeout=10)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("market") == "dubai"


# ─── 8. /api/news/local dubai (mock) mentions Dubai content ─────────────────
def test_news_local_dubai_market(session, auth_headers):
    # Set market = dubai explicitly
    session.patch(
        f"{BASE_URL}/api/users/me/market",
        json={"market": "dubai"},
        headers=auth_headers,
        timeout=15,
    )
    r = session.get(f"{BASE_URL}/api/news/local?limit=3", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("market") == "dubai"
    blob = " ".join(i.get("title", "") + " " + i.get("summary", "") for i in data.get("items", []))
    assert any(k in blob for k in ("Dubai Marina", "RTA", "Dubai")), (
        f"Dubai headlines missing landmark keywords: {blob[:300]}"
    )


# ─── 9. Regression: /api/auth/me, /api/channels, /api/bigcoin/me ────────────
def test_regression_auth_me(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=10)
    assert r.status_code == 200, r.text[:200]


def test_regression_channels(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/channels", headers=auth_headers, timeout=10)
    assert r.status_code == 200, r.text[:200]


def test_regression_bigcoin_me(session, auth_headers):
    r = session.get(f"{BASE_URL}/api/bigcoin/me", headers=auth_headers, timeout=10)
    assert r.status_code == 200, r.text[:200]


# ─── 10. Cleanup ─────────────────────────────────────────────────────────────
def test_zz_cleanup_market_override(session, auth_headers):
    """Reset preferred_market to null so this account doesn't leave override on."""
    r = session.patch(
        f"{BASE_URL}/api/users/me/market",
        json={"market": None},
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 200
