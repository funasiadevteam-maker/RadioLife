"""Phase 14 prep — one-click demo login tests."""
from __future__ import annotations
import os
import time

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
DB = MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(autouse=True)
def _reset_rate_limit_bucket():
    """Make each test start with a clean in-process rate-limit bucket."""
    try:
        requests.post(f"{API}/auth/_demo_reset_rate_limit", timeout=5)
    except Exception:
        pass
    yield


# ════════════════════════════════════════════════════════════════════
# 1. demo login creates a session
# ════════════════════════════════════════════════════════════════════
def test_demo_login_creates_session():
    r = requests.post(f"{API}/auth/demo", timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["session_token"].startswith("bsess_") \
        or body["session_token"].startswith("sess_")
    assert body["email"] == "demo@bigfm.dubai"
    assert body["auth_provider"] == "demo"
    # Cookie set on the response.
    assert "bigfm_session=" in r.headers.get("set-cookie", "")
    # Token usable for /me.
    me = requests.get(f"{API}/auth/me", headers={
        "Authorization": f"Bearer {body['session_token']}"}, timeout=10)
    assert me.status_code == 200, me.text[:200]
    assert me.json()["email"] == "demo@bigfm.dubai"


# ════════════════════════════════════════════════════════════════════
# 2. demo login reuses the same demo account
# ════════════════════════════════════════════════════════════════════
def test_demo_login_reuses_existing_demo_account():
    r1 = requests.post(f"{API}/auth/demo", timeout=10)
    r2 = requests.post(f"{API}/auth/demo", timeout=10)
    assert r1.status_code == 200 and r2.status_code == 200
    b1, b2 = r1.json(), r2.json()
    # Different session_tokens — each call mints a new session row.
    assert b1["session_token"] != b2["session_token"]
    # Same underlying user.
    assert b1["user_id"] == b2["user_id"]
    assert b1["email"] == b2["email"] == "demo@bigfm.dubai"
    # Exactly one demo user in Mongo.
    cnt = DB.users.count_documents({"email": "demo@bigfm.dubai"})
    assert cnt == 1, f"expected 1 demo user, found {cnt}"


# ════════════════════════════════════════════════════════════════════
# 3. demo login rate-limit fires after 30/min
# ════════════════════════════════════════════════════════════════════
def test_demo_login_rate_limit():
    statuses = []
    with requests.Session() as s:
        for _ in range(35):
            r = s.post(f"{API}/auth/demo", timeout=10)
            statuses.append(r.status_code)
    n200 = sum(1 for s in statuses if s == 200)
    n429 = sum(1 for s in statuses if s == 429)
    assert n429 >= 1, (
        f"expected at least one 429 in 35 rapid calls, got "
        f"{n200}x200, {n429}x429, others={set(statuses)-{200,429}}")
    assert n200 <= 30, (
        f"expected at most 30 successes, got {n200}")


# ════════════════════════════════════════════════════════════════════
# 4. demo session works against /auth/me (basic exercising of seeded UX)
# ════════════════════════════════════════════════════════════════════
def test_demo_login_seeded_session_can_call_passport_endpoints():
    r = requests.post(f"{API}/auth/demo", timeout=10)
    assert r.status_code == 200
    tok = r.json()["session_token"]
    h = {"Authorization": f"Bearer {tok}"}
    # Hit a representative authenticated endpoint that exists in every
    # phase — /auth/me. This proves the bearer flow works end-to-end.
    me = requests.get(f"{API}/auth/me", headers=h, timeout=10)
    assert me.status_code == 200, me.text[:200]
    body = me.json()
    assert body["user_id"] == r.json()["user_id"]
    # Demo user must have onboarding_complete so the post-login UX
    # lands on /radio immediately (not stuck on onboarding).
    assert body["onboarding_complete"] is True
