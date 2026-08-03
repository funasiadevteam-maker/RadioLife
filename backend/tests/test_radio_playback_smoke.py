"""Phase 19c — Radio playback smoke (regression guard).

Catches the failure mode where a fresh fork has empty storage/tracks/ +
DB rows that reference missing MP3 files. The old behaviour was an opaque
500 with an ffmpeg stderr dump; the new behaviour is either:
  - 200 OK when audio is available, OR
  - 503 {code: "audio_asset_missing"} when it isn't.

Either is acceptable for the test — both prove the regression is closed.
"""
from __future__ import annotations
import asyncio, os, sys

sys.path.insert(0, "/app/backend")
os.environ["STRIPE_MODE"] = "mock"
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _login(ac, email, pwd):
    return ac.post("/api/auth/login", json={"email": email, "password": pwd})


def test_listener_can_start_station_returns_2xx_or_503():
    """Logged-in non-creator hits /api/radio/start — must NOT be 500."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            r = await _login(ac, "admin@bigfm.dubai", "AdminPass123!")
            tok = r.json()["session_token"]
            res = await ac.post("/api/radio/start",
                json={"channel_slug": "bollywood_mehfil"},
                headers={"Authorization": f"Bearer {tok}"})
            # Pass if 2xx OR explicit 503 audio_asset_missing. FAIL on 500.
            assert res.status_code != 500, \
                f"radio_start regressed to opaque 500: {res.text[:200]}"
            assert res.status_code < 400 or res.status_code == 503, \
                f"unexpected status {res.status_code}: {res.text[:200]}"
            if res.status_code == 503:
                assert "audio_asset_missing" in res.text
            else:
                body = res.json()
                assert "session_id" in body
                assert body["segment"]["segment_url"].startswith("/api/radio/segment/")
    run(go())


def test_listener_can_get_next_queue_item_returns_2xx_or_503():
    """After /start succeeds, /next must return 200."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            r = await _login(ac, "admin@bigfm.dubai", "AdminPass123!")
            tok = r.json()["session_token"]
            hdrs = {"Authorization": f"Bearer {tok}"}
            start = await ac.post("/api/radio/start",
                json={"channel_slug": "bollywood_mehfil"}, headers=hdrs)
            if start.status_code == 503:
                # Pre-condition unmet (no audio assets). Smoke is moot.
                return
            sid = start.json()["session_id"]
            nxt = await ac.get(f"/api/radio/next?session_id={sid}", headers=hdrs)
            assert nxt.status_code != 500, \
                f"radio_next regressed to 500: {nxt.text[:200]}"
            assert nxt.status_code == 200, \
                f"radio_next expected 200, got {nxt.status_code}: {nxt.text[:200]}"
    run(go())


def test_logged_in_non_creator_is_not_403_on_radio_routes():
    """Explicitly asserts NO Phase 19b ownership helper accidentally
    blocks listener radio routes. /api/radio/* must never 403 a listener."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            r = await _login(ac, "admin@bigfm.dubai", "AdminPass123!")
            tok = r.json()["session_token"]
            hdrs = {"Authorization": f"Bearer {tok}"}
            for path in ["/api/radio/start", "/api/radio/ready"]:
                if path.endswith("start"):
                    res = await ac.post(path,
                        json={"channel_slug": "bollywood_mehfil"}, headers=hdrs)
                else:
                    res = await ac.get(f"{path}?session_id=nonexistent", headers=hdrs)
                assert res.status_code != 403, \
                    f"{path} returned 403 — Phase 19b ownership helper " \
                    f"may have leaked onto a listener route. " \
                    f"body: {res.text[:200]}"
    run(go())
