"""Phase 11.3 — Lobby WebSocket Bearer-via-query-param auth tests.

Browser WebSocket API can't set Authorization headers, so the WS handler
must accept the same opaque session token via `?token=<...>` (matches the
auth_testing.md mobile contract).  Legacy `?session=<...>` is kept as an
alias for backwards-compat.
"""
from __future__ import annotations
import asyncio
import json
import os
import uuid

import pytest
import requests
import websockets


HTTP_ROOT = (os.environ.get("BIGFM_API_URL")
                  or os.environ.get("REACT_APP_BACKEND_URL")
                  or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{HTTP_ROOT}/api"
# wss:// (HTTPS preview) → ws if local
WS_ROOT = HTTP_ROOT.replace("https://", "wss://").replace("http://", "ws://")


def _login(email: str, pwd: str) -> tuple[str, str]:
    r = requests.post(f"{API}/auth/login",
                            json={"email": email, "password": pwd}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    return body["session_token"], body["user_id"]


def _create_lobby(token: str) -> str:
    """Get or create a lobby for the test user (1 active host at a time).

    Cleans up the host's stale lobbies first so the Phase 12c
    `lobby_spam` heuristic (>5 in 60min) doesn't 429 us across runs.
    """
    # Resolve user_id once, then prune stale lobbies for that host.
    me = requests.get(f"{API}/auth/me",
                              headers={"Authorization": f"Bearer {token}"},
                              timeout=10)
    if me.status_code == 200:
        uid = me.json().get("user_id")
        if uid:
            try:
                from pymongo import MongoClient
                from datetime import datetime, timedelta, timezone
                cli = MongoClient(
                    os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
                db = cli[os.environ.get("DB_NAME", "bigfm")]
                cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
                db.lobbies.delete_many({
                    "host_user_id": uid,
                    "created_at": {"$gte": cutoff},
                    "status": {"$in": ["closed", "ended"]}})
                cli.close()
            except Exception:
                pass
    r = requests.post(
        f"{API}/lobbies/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"WS Test {uuid.uuid4().hex[:6]}",
                "channel_slug": "bollywood_mehfil",
                "city": "dubai"},
        timeout=10)
    if r.status_code == 200:
        return r.json()["lobby_id"]
    # Reuse the existing lobby if the user is already hosting
    detail = (r.json() or {}).get("detail") or ""
    if isinstance(detail, str) and "already_hosting:" in detail:
        return detail.split(":", 1)[1].strip()
    raise AssertionError(f"create_lobby failed: {r.status_code} {r.text}")


async def _ws_first_frame(url: str, timeout: float = 5.0) -> dict:
    """Connect and pull the first server frame.  Returns the parsed JSON."""
    async with websockets.connect(url, open_timeout=timeout,
                                                close_timeout=2) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        return json.loads(raw)


def test_ws_token_query_param_authenticates():
    """`?token=<bearer>` lets mobile connect (browser can't send headers)."""
    token, _ = _login("test@bigfm.dubai", "TestUser123!")
    lobby_id = _create_lobby(token)
    url = f"{WS_ROOT}/api/lobbies/ws/{lobby_id}?token={token}"
    first = asyncio.run(_ws_first_frame(url))
    # Successful auth → first server frame is `welcome` / `joined`, NOT error
    assert first.get("type") != "error", first
    assert first.get("type") in ("hello", "welcome", "joined",
                                            "presence", "state", "snapshot",
                                            "init"), first


def test_ws_session_query_param_legacy_alias_still_works():
    """Backwards-compat — pre-existing `?session=` callers must keep working."""
    token, _ = _login("test@bigfm.dubai", "TestUser123!")
    lobby_id = _create_lobby(token)
    url = f"{WS_ROOT}/api/lobbies/ws/{lobby_id}?session={token}"
    first = asyncio.run(_ws_first_frame(url))
    assert first.get("type") != "error", first


def test_ws_missing_token_returns_unauthorized_frame():
    """No cookie, no `?token`, no `?session` → first frame is `unauthorized`."""
    token, _ = _login("test@bigfm.dubai", "TestUser123!")
    lobby_id = _create_lobby(token)
    url = f"{WS_ROOT}/api/lobbies/ws/{lobby_id}"
    first = asyncio.run(_ws_first_frame(url))
    assert first.get("type") == "error", first
    assert first.get("code") == "unauthorized", first


def test_ws_bad_token_returns_unauthorized_frame():
    token, _ = _login("test@bigfm.dubai", "TestUser123!")
    lobby_id = _create_lobby(token)
    url = f"{WS_ROOT}/api/lobbies/ws/{lobby_id}?token=this_is_not_a_real_token"
    first = asyncio.run(_ws_first_frame(url))
    assert first.get("type") == "error", first
    assert first.get("code") == "unauthorized", first
