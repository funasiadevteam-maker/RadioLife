"""Phase 19a — defense-in-depth: confirm /admin/podcasts/* require admin role.

Hermetic: hits the live FastAPI via httpx ASGI client. No external network.
"""
from __future__ import annotations
import asyncio
import os
import sys

import pytest

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _client_and_app():
    # Lazy import keeps test collection fast on FE-only runs.
    import importlib
    server = importlib.import_module("server")
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=server.app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login_admin(ac):
    """Return Bearer auth header for the seeded admin.

    httpx ASGIClient doesn't reliably carry the `secure=True; samesite=none`
    session cookie over the in-process `http://test` base URL, so we use
    the Bearer fallback supported by the auth resolver instead.
    """
    r = await ac.post("/api/auth/login",
        json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token")
    assert tok, f"login response missing session_token: {r.text}"
    return {"Authorization": f"Bearer {tok}"}


def test_admin_podcast_applications_blocks_anon():
    """Anonymous fetch of admin podcast routes must NOT return 200.

    Covers BOTH /api/admin/podcasts/creator-applications AND
    /api/admin/podcasts/channels separately so a regression on either
    route is caught independently.
    """
    async def go():
        async with _client_and_app() as ac:
            r1 = await ac.get("/api/admin/podcasts/creator-applications")
            r2 = await ac.get("/api/admin/podcasts/channels")
            # Either auth-required (401) or admin-required (403). Never 200.
            assert r1.status_code in (401, 403), \
                f"applications anon got {r1.status_code}: {r1.text}"
            assert r2.status_code in (401, 403), \
                f"channels anon got {r2.status_code}: {r2.text}"
    run(go())


def test_admin_podcast_applications_allows_admin():
    """Admin login lets BOTH admin podcast routes return 200."""
    async def go():
        async with _client_and_app() as ac:
            hdrs = await _login_admin(ac)
            r1 = await ac.get("/api/admin/podcasts/creator-applications",
                                            headers=hdrs)
            r2 = await ac.get("/api/admin/podcasts/channels",
                                            headers=hdrs)
            assert r1.status_code == 200, \
                f"applications admin got {r1.status_code}: {r1.text}"
            assert r2.status_code == 200, \
                f"channels admin got {r2.status_code}: {r2.text}"
    run(go())
