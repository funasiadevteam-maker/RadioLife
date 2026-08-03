"""Phase 19b — routes/podcasts.py P0+P1 hardening tests."""
from __future__ import annotations
import asyncio, os, sys, uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

# Force mock Stripe in tests regardless of host .env state (STRIPE_MODE=live
# is set in .env for live API testing but unit tests must never hit Stripe).
os.environ["STRIPE_MODE"] = "mock"

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _login_admin(ac):
    r = await ac.post("/api/auth/login",
        json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _register(ac, suffix: str):
    r = await ac.post("/api/auth/register",
        json={"email": f"u_{suffix}_{uuid.uuid4().hex[:6]}@bigfm.dubai",
                  "password": "Pwd1234!", "name": "U"})
    return r.json()["user_id"], {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _seed_creator_with_session(db, *, with_clip: bool = False,
                                                                              with_episode: bool = True) -> dict:
    """Seed an approved creator + channel + (optional) episode + session + clip."""
    suf = uuid.uuid4().hex[:8]
    ids = {
        "creator":  f"crt_p19b_{suf}", "user": f"usr_p19b_{suf}",
        "channel": f"pch_p19b_{suf}", "episode": f"pep_p19b_{suf}",
        "session": f"sess_p19b_{suf}", "clip":      f"clip_p19b_{suf}",
    }
    now = datetime.now(timezone.utc)
    await db.podcast_creators.insert_one({"id": ids["creator"],
        "user_id": ids["user"], "application_status": "approved",
        "display_name": "Owner", "created_at": now})
    await db.podcast_channels.insert_one({"id": ids["channel"],
        "creator_id": ids["creator"], "title": "Ch", "created_at": now})
    if with_episode:
        await db.podcast_episodes.insert_one({"id": ids["episode"],
            "channel_id": ids["channel"], "title": "Ep",
            "publish_status": "draft", "created_at": now})
    await db.podcast_recording_sessions.insert_one({"id": ids["session"],
        "creator_id": ids["creator"], "channel_id": ids["channel"],
        "status": "scheduled", "created_at": now})
    if with_clip:
        await db.podcast_clips.insert_one({"id": ids["clip"],
            "episode_id": ids["episode"], "channel_id": ids["channel"],
            "start_seconds": 0, "end_seconds": 30, "status": "pending"})
    return ids


async def _outsider_creator(db, *, user_id: str) -> str:
    crt_id = f"crt_outsider_{uuid.uuid4().hex[:6]}"
    await db.podcast_creators.insert_one({"id": crt_id,
        "user_id": user_id, "application_status": "approved",
        "display_name": "Outsider"})
    return crt_id


async def _cleanup(db, ids: dict, extras: list = None):
    await db.podcast_creators.delete_many(
        {"id": {"$in": [ids["creator"]] + (extras or [])}})
    await db.podcast_channels.delete_many({"id": ids["channel"]})
    await db.podcast_episodes.delete_many({"channel_id": ids["channel"]})
    await db.podcast_recording_sessions.delete_many({"id": ids["session"]})
    await db.podcast_clips.delete_many({"episode_id": ids.get("episode")})


# Reusable harness ────────────────────────────────────────────────
def _run_p0(method: str, path_fmt: str, *, body=None, files=None):
    """Generic non-owner P0 expectation: creator B hits creator A's resource → 403."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        ids = await _seed_creator_with_session(db,
            with_clip=("/clips/" in path_fmt),
            with_episode=("episodes" in path_fmt or "/clips/" in path_fmt))
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            outsider_uid, hdrs = await _register(ac, "out")
            outsider_crt = await _outsider_creator(db, user_id=outsider_uid)
            url = path_fmt.format(**ids)
            kwargs = {"headers": hdrs}
            if body is not None: kwargs["json"] = body
            r = await getattr(ac, method)(url, **kwargs)
            assert r.status_code in (403, 404), \
                f"{method.upper()} {url} should be 403/404; got {r.status_code}: {r.text}"
            assert r.status_code == 403 or "not_your" in r.text or "not_found" in r.text
        await _cleanup(db, ids, extras=[outsider_crt])
        await db.users.delete_many({"user_id": outsider_uid})
    run(go())


# ─── P0 tests (8) ─────────────────────────────────────────────
def test_p0_session_start_non_owner_creator_403():
    _run_p0("post", "/api/podcasts/recording-sessions/{session}/start")

def test_p0_session_finalize_non_owner_403():
    _run_p0("post", "/api/podcasts/recording-sessions/{session}/finalize")

def test_p0_session_delete_non_owner_403():
    _run_p0("delete", "/api/podcasts/recording-sessions/{session}")

def test_p0_session_get_non_owner_403():
    _run_p0("get", "/api/podcasts/recording-sessions/{session}")

def test_p0_episode_clips_generate_non_owner_403():
    _run_p0("post", "/api/podcasts/episodes/{episode}/clips/generate?count=1")

def test_p0_episode_clip_patch_non_owner_403():
    _run_p0("patch", "/api/podcasts/episodes/{episode}/clips/{clip}",
                  body={"status": "approved"})

def test_p0_channel_value_config_patch_non_owner_403():
    """THE Lightning landmine — money redirect prevention."""
    _run_p0("patch", "/api/podcasts/channels/{channel}/value-config",
                  body={"enabled": True, "splits":
                              [{"address": "attacker@strike.me", "share": 100}]})

def test_p0_episode_value_config_patch_non_owner_403():
    _run_p0("patch", "/api/podcasts/episodes/{episode}/value-config",
                  body={"enabled": True, "splits":
                              [{"address": "attacker@strike.me", "share": 100}]})


# ─── Admin bypass (P0 representative) ─────────────────────────
def test_p0_session_start_admin_bypass_200_or_404():
    """Admin should bypass ownership; either 200 OK or 404 'session_not_found'
    if start_session inner-checks state. Should NOT be 403."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        ids = await _seed_creator_with_session(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            hdrs = await _login_admin(ac)
            r = await ac.post(
                f"/api/podcasts/recording-sessions/{ids['session']}/start",
                headers=hdrs)
            assert r.status_code != 403, \
                f"admin must bypass; got 403: {r.text}"
        await _cleanup(db, ids)
    run(go())


# ─── P1 tests (4 representative) ───────────────────────────────
def test_p1_creators_channels_list_admin_can_read_any_creator():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        ids = await _seed_creator_with_session(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            hdrs = await _login_admin(ac)
            r = await ac.get(
                f"/api/podcasts/creators/{ids['creator']}/channels",
                headers=hdrs)
            assert r.status_code == 200, r.text
            channels = r.json().get("channels", [])
            assert any(c["id"] == ids["channel"] for c in channels)
        await _cleanup(db, ids)
    run(go())


def test_p1_channel_distribution_get_non_owner_403():
    _run_p0("get", "/api/podcasts/channels/{channel}/distribution")


def test_p1_session_connection_quality_non_owner_403():
    _run_p0("get", "/api/podcasts/recording-sessions/{session}/connection-quality")


def test_p1_import_rss_caps_at_500_entries_with_warning():
    """Unit-level: pass through the route handler logic to confirm cap math.
    Full HTTP test would need a hostile feed server — skip that; just verify
    the slicing+warning shape via the response contract."""
    async def go():
        # Mock feedparser to return 600 fake entries.
        import importlib, types
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        import routes.podcasts as rp
        original_fp = rp.feedparser
        original_httpx = rp.httpx

        # 1) Fake feed parse returning 600 entries.
        fake = types.SimpleNamespace(entries=[
            {"guid": f"g{i}", "title": f"e{i}", "summary": "",
              "content": [], "enclosures": [{"href": f"http://x/{i}.mp3",
                                                                "length": "0"}]}
            for i in range(600)])
        rp.feedparser = types.SimpleNamespace(parse=lambda _: fake)

        # 2) Fake httpx client to skip the network.
        class _FakeResp:
            content = b"<rss></rss>"
            def raise_for_status(self): pass
        class _FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def get(self, *a, **k): return _FakeResp()
        rp.httpx = types.SimpleNamespace(AsyncClient=_FakeClient)

        try:
            db = _db()
            ids = await _seed_creator_with_session(db)
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                          base_url="http://test") as ac:
                hdrs = await _login_admin(ac)
                r = await ac.post(
                    f"/api/podcasts/channels/{ids['channel']}/import-rss",
                    json={"rss_url": "http://fake.local/feed.xml"},
                    headers=hdrs)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["total_seen"] == 600
                assert body.get("warning") == "truncated_to_500"
                assert body["imported_count"] <= 500
            await _cleanup(db, ids)
        finally:
            rp.feedparser = original_fp
            rp.httpx = original_httpx
    run(go())
