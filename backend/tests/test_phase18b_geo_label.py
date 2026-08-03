"""Phase 18b polish — geo-label single-source-of-truth tests."""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN   = os.environ.get("DB_NAME",   "bigfm")

def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _fake_request():
    r = MagicMock()
    r.client = None
    r.headers = {}
    return r


# ─── 1) user.market wins over IP geo when no preferred_market is set ─
def test_geo_resolve_for_user_uses_user_market_when_no_preferred_market():
    from services.geo import resolve_for_user
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(MONGO)[DBN]
    user = {"user_id": "test_p18b_geo", "market": "dubai"}
    out = run(resolve_for_user(_fake_request(), user, db))
    assert out["market"] == "dubai"
    assert out["city"]      == "Dubai"
    assert out["source"]    == "user_profile"


# ─── 2) preferred_market overrides user.market when both are set ─────
def test_geo_resolve_for_user_preferred_market_overrides_home_market():
    from services.geo import resolve_for_user
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(MONGO)[DBN]
    user = {"user_id": "x", "market": "dubai", "preferred_market": "new_york"}
    out = run(resolve_for_user(_fake_request(), user, db))
    assert out["market"] == "new_york"
    assert out["source"] == "override"


# ─── 3) demo user fresh-login lands on Dubai (no Dallas leak) ────────
def test_demo_login_clears_stale_preferred_market_and_returns_dubai():
    """Confirms the canonical demo flow: /api/auth/demo + /api/geo/me
    returns market=dubai, not Dallas — even if the demo user had a stale
    preferred_market override from a previous QA session."""
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(MONGO)[DBN]
    # Seed the demo user with a stale Dallas override.
    run(db.users.update_one({"email": "demo@bigfm.dubai"},
                                              {"$set": {"market": "dubai",
                                                              "preferred_market": "dfw"}},
                                              upsert=False))
    # The demo_login route should clear it.
    import requests
    BASE = "http://localhost:8001/api"
    s = requests.Session()
    s.post(f"{BASE}/auth/_demo_reset_rate_limit")  # avoid 429 in CI
    r = s.post(f"{BASE}/auth/demo")
    assert r.status_code == 200, r.text
    # Session cookie is Secure; SameSite=none — requests.Session() won't send
    # it on plain http://localhost.  Pull it out and pass explicitly.
    sess_cookie = r.cookies.get("bigfm_session")
    assert sess_cookie, "demo_login did not set session cookie"
    cookies = {"bigfm_session": sess_cookie}
    # /api/geo/me must now reflect Dubai, not Dallas.
    g = requests.get(f"{BASE}/geo/me",
                                params={"tz": "America/Chicago"}, cookies=cookies)
    assert g.status_code == 200
    body = g.json()
    assert body["market"] == "dubai", body
    assert body["city"]      == "Dubai", body
    assert body["source"]    == "user_profile", body
    # And the persisted user record no longer has the stale override.
    u = run(db.users.find_one({"email": "demo@bigfm.dubai"}))
    assert not u.get("preferred_market")
