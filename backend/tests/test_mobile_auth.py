"""Phase 11 (Mobile) — Bearer-token / session_token contract tests."""
from __future__ import annotations
import os
import requests

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"


def test_login_returns_session_token_in_body():
    """Mobile clients need the opaque token in the JSON body so they can
    store it in `expo-secure-store`.  Web still gets the Set-Cookie
    header so it keeps working unchanged."""
    r = requests.post(f"{API}/auth/login",
                            json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "session_token" in body, body
    assert isinstance(body["session_token"], str)
    assert len(body["session_token"]) >= 32, body["session_token"]
    assert "session_expires_at" in body, body
    assert body["session_expires_at"]  # non-null ISO timestamp
    # Set-Cookie must still be present so web is unaffected
    set_cookie = r.headers.get("set-cookie") or ""
    assert "bigfm_session=" in set_cookie, set_cookie


def test_bearer_token_authorizes_protected_route():
    """Login → take the returned session_token → use it as Authorization:
    Bearer header (no cookie jar) → call a protected route → expect 200
    and the same user back."""
    # Step 1 — login WITHOUT carrying a cookie jar across (simulate mobile)
    login = requests.post(
        f"{API}/auth/login",
        json={"email": "test@bigfm.dubai",
                "password": "TestUser123!"}, timeout=10)
    assert login.status_code == 200, login.text
    token = login.json()["session_token"]
    user_id = login.json()["user_id"]
    # Step 2 — fresh session, NO cookie, Bearer only.  `/passport/me`
    # returns a nested payload; auth success = 200 + non-empty body.
    bearer = requests.Session()
    r = bearer.get(f"{API}/passport/me",
                          headers={"Authorization": f"Bearer {token}"},
                          timeout=10)
    assert r.status_code == 200, r.text
    assert r.json(), "empty body on authenticated passport/me"
    # Step 3 — `/api/auth/me` returns the canonical user shape with user_id
    r2 = bearer.get(f"{API}/auth/me",
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("user_id") == user_id, r2.json()


def test_bearer_logout_revokes_token():
    """Logout with a Bearer-supplied token must invalidate it so a
    subsequent call with the same token returns 401."""
    login = requests.post(
        f"{API}/auth/login",
        json={"email": "test@bigfm.dubai",
                "password": "TestUser123!"}, timeout=10)
    assert login.status_code == 200, login.text
    token = login.json()["session_token"]
    # Logout via Bearer (no cookie)
    r = requests.post(f"{API}/auth/logout",
                              headers={"Authorization": f"Bearer {token}"},
                              timeout=10)
    assert r.status_code == 200, r.text
    # Next call with the SAME token must now be unauthorized
    r2 = requests.get(f"{API}/auth/me",
                              headers={"Authorization": f"Bearer {token}"},
                              timeout=10)
    assert r2.status_code in (401, 403), (r2.status_code, r2.text[:200])


def test_openapi_json_reflects_session_token_field():
    """The new fields must surface in the OpenAPI schema so generated
    mobile clients pick them up."""
    r = requests.get(f"{API}/openapi.json", timeout=10)
    assert r.status_code == 200, r.text[:200]
    spec = r.json()
    user_out = (spec.get("components") or {}).get("schemas", {}).get("UserOut")
    assert user_out, "UserOut schema missing"
    props = user_out.get("properties") or {}
    assert "session_token" in props, list(props.keys())
    assert "session_expires_at" in props, list(props.keys())
