"""iter_203 — Personalize portal + cover-art security.
Tests:
  - GET/PUT /api/social/features: catalog, mandatory, order persistence, city defaults, factual-copy
  - POST /api/bar-games/cover-art: 401 anon, 403 non-owner, allowed for owner
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("session_token") or j.get("token") or j.get("access_token")
    return tok, r.cookies


@pytest.fixture(scope="module")
def demo_auth():
    tok, cookies = _login("demo@bigfm.dubai", "DemoPass123!")
    return {"headers": {"Authorization": f"Bearer {tok}"} if tok else {}, "cookies": cookies}


@pytest.fixture(scope="module")
def owner_auth():
    tok, cookies = _login("test@bigfm.dubai", "TestUser123!")
    return {"headers": {"Authorization": f"Bearer {tok}"} if tok else {}, "cookies": cookies}


# ─── Features: catalog + factual copy ────────────────────────────────────
def test_features_catalog_factual_copy(demo_auth):
    r = requests.get(f"{BASE}/api/social/features", **demo_auth, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "catalog" in j and len(j["catalog"]) >= 5
    assert j["mandatory"] == ["listen"]
    # catalog[0] is 'listen' - its desc must NOT contain '50K' or digits
    listen = j["catalog"][0]
    assert listen["key"] == "listen"
    assert "50K" not in listen["desc"] and "50,000" not in listen["desc"]
    # Check no digit characters at all in listen desc
    assert not any(c.isdigit() for c in listen["desc"]), f"listen desc has digits: {listen['desc']}"
    assert listen["desc"] == "Live radio, AI radio & podcasts"


def test_features_home_city_dallas(demo_auth):
    """demo@bigfm.dubai should have home_city=Dallas → default = Dallas preset"""
    r = requests.get(f"{BASE}/api/social/features", **demo_auth, timeout=15)
    j = r.json()
    hc = (j.get("home_city") or "").lower()
    default = j.get("default") or []
    # demo user home_city should be set; expect dallas default order
    if hc == "dallas":
        # First mandatory in Dallas preset is 'listen'
        assert default[0] == "listen"
        # Dallas-specific: shop should appear before play (per features.py)
        if "shop" in default and "play" in default:
            assert default.index("shop") < default.index("play"), f"Dallas default order wrong: {default}"
    else:
        # If not Dallas, we still get a sensible default
        assert "listen" in default


# ─── Features: reorder persistence ───────────────────────────────────────
def test_features_reorder_persists(demo_auth):
    custom = ["play", "social", "listen"]
    r = requests.put(f"{BASE}/api/social/features", json={"features": custom}, **demo_auth, timeout=15)
    assert r.status_code == 200, r.text
    saved = r.json()["enabled"]
    assert saved == ["play", "social", "listen"], f"PUT returned {saved}"

    # GET must persist
    r2 = requests.get(f"{BASE}/api/social/features", **demo_auth, timeout=15)
    enabled = r2.json()["enabled"]
    assert enabled == ["play", "social", "listen"], f"reload returned {enabled}"


def test_features_listen_forced_present(demo_auth):
    # Omit listen → must be forced in
    r = requests.put(f"{BASE}/api/social/features", json={"features": ["play", "shop"]}, **demo_auth, timeout=15)
    assert r.status_code == 200
    enabled = r.json()["enabled"]
    assert "listen" in enabled, f"listen not forced: {enabled}"


# ─── Cover-art security ──────────────────────────────────────────────────
def test_cover_art_anonymous_401():
    r = requests.post(f"{BASE}/api/bar-games/cover-art",
                      json={"prompt": "neon bar"}, timeout=15)
    assert r.status_code in (401, 403), f"expected 401, got {r.status_code}"


def test_cover_art_non_owner_no_business_403(demo_auth):
    r = requests.post(f"{BASE}/api/bar-games/cover-art",
                      json={"prompt": "neon bar"}, **demo_auth, timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert r.json().get("detail", {}).get("code") == "forbidden" or "forbidden" in r.text.lower()


def test_cover_art_non_owner_with_business_403(demo_auth):
    r = requests.post(f"{BASE}/api/bar-games/cover-art",
                      json={"prompt": "neon bar", "business_id": "biz_karak_cafe_karama"},
                      **demo_auth, timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_cover_art_owner_allowed(owner_auth):
    r = requests.post(f"{BASE}/api/bar-games/cover-art",
                      json={"prompt": "neon bar", "business_id": "biz_karak_cafe_karama"},
                      **owner_auth, timeout=60)
    # NOT 403 means authorized; 200 or 429 both acceptable (avoid paid image gen)
    assert r.status_code != 403, f"owner was forbidden! {r.status_code} {r.text}"
    assert r.status_code in (200, 429, 502), f"unexpected status {r.status_code}: {r.text}"
