"""
Phase 15d.2 — backend verification for:
  - GET /api/channels returns >= 10 channels with thumbnail_url, market in (global|dubai|dfw)
  - GET /api/static/channel_thumbnails/bollywood_mehfil.webp returns 200 image/webp
  - GET /api/news/local?limit=3 returns 200 (items may be empty), never 500
  - GET /api/auth/me for demo user returns name == 'Demo Listener'
  - GET /api/geo/me?tz=Asia/Dubai returns a market field
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
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
def demo_auth(session):
    """One-click demo login → returns (token, user dict)."""
    r = session.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    token = data.get("session_token") or data.get("token") or data.get("access_token")
    # /api/auth/demo returns user fields flat (name, email, user_id) at top level
    user = data.get("user") if isinstance(data.get("user"), dict) else data
    assert token, f"no session_token in /api/auth/demo response: {data}"
    return token, user


@pytest.fixture
def headers(demo_auth):
    token, _ = demo_auth
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── 1. /api/channels: >=10 channels, thumbnail_url, market in (global|dubai|dfw)
def test_channels_returns_at_least_10_with_thumbnails(session, headers):
    r = session.get(f"{BASE_URL}/api/channels", headers=headers, timeout=15)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # Normalize: some APIs return list, some return {channels:[...]}
    channels = body if isinstance(body, list) else (body.get("channels") or body.get("data") or [])
    assert isinstance(channels, list), f"channels not a list: {type(body)}"
    assert len(channels) >= 10, f"expected >=10 channels (Phase 15d.2 regression fix), got {len(channels)}"

    allowed_markets = {"global", "dubai", "dfw"}
    missing_thumb = []
    bad_market = []
    for ch in channels:
        if not ch.get("thumbnail_url"):
            missing_thumb.append(ch.get("slug") or ch.get("id") or ch.get("name"))
        market = ch.get("market")
        if market not in allowed_markets:
            bad_market.append((ch.get("slug") or ch.get("name"), market))
    assert not missing_thumb, f"channels missing thumbnail_url: {missing_thumb}"
    assert not bad_market, f"channels with unexpected market value: {bad_market}"


# ─── 2. Channel thumbnail static asset
def test_channel_thumbnail_webp_static_asset(session):
    r = session.get(
        f"{BASE_URL}/api/static/channel_thumbnails/bollywood_mehfil.webp",
        timeout=15,
    )
    assert r.status_code == 200, f"thumbnail GET status={r.status_code} body[:120]={r.text[:120]}"
    ctype = r.headers.get("content-type", "").lower()
    assert "image/webp" in ctype, f"unexpected content-type: {ctype}"
    assert len(r.content) > 200, f"thumbnail content suspiciously small: {len(r.content)} bytes"


# ─── 3. /api/news/local must never 500 for valid user
def test_news_local_no_500(session, headers):
    r = session.get(f"{BASE_URL}/api/news/local?limit=3", headers=headers, timeout=15)
    assert r.status_code == 200, f"/api/news/local returned {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert "items" in data, f"missing items field: {data}"
    assert isinstance(data["items"], list)


# ─── 4. demo user name fix: 'Demo Listener'
def test_auth_me_demo_user_name(session, headers, demo_auth):
    _, user_from_login = demo_auth
    # First validate on /api/auth/demo body
    assert user_from_login.get("name") == "Demo Listener", (
        f"demo login user.name should be 'Demo Listener', got {user_from_login.get('name')!r}"
    )
    r = session.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    user = body.get("user") if isinstance(body, dict) and "user" in body else body
    assert user.get("name") == "Demo Listener", (
        f"/api/auth/me user.name should be 'Demo Listener', got {user.get('name')!r}"
    )
    # Email sanity
    assert (user.get("email") or "").lower() == "demo@bigfm.dubai"


# ─── 5. /api/geo/me?tz=Asia/Dubai returns market field, no error
def test_geo_me_with_tz_param(session, headers):
    r = session.get(f"{BASE_URL}/api/geo/me?tz=Asia/Dubai", headers=headers, timeout=10)
    assert r.status_code == 200, f"/api/geo/me?tz=Asia/Dubai returned {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert "market" in data, f"missing market field: {data}"
    assert data["market"] in {"dubai", "dfw", "global", "new_york", "london", "mumbai", "los_angeles"}
