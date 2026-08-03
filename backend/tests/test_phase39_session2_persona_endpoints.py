"""Phase 39 Session 2 — Persona endpoint tests.

Coverage:
  • GET /api/personas/library — 10 personas, listener shape, no internal fields
  • GET /api/personas/me — daypart default when no selection
  • POST /api/personas/select — persists user.selected_persona_id
  • POST /api/personas/select — rejects invalid persona_id with 400
  • GET /api/personas/me after select — returns selected + source=user_selected
  • POST /api/personas/chat — returns text + audio_url
  • POST /api/personas/chat — rejects unsafe persona with 403
  • POST /api/admin/personas/reclassify_all — admin-only, refreshes timestamps
  • Listener cannot call admin reclassify (403)
"""
from __future__ import annotations
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _login(ac, email, password):
    r = await ac.post("/api/auth/login",
                                  json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_library_returns_10_personas_with_listener_shape():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.get("/api/personas/library", headers=hdr)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["count"] == 10
            for p in j["personas"]:
                assert p["persona_id"].startswith("p39_")
                # Listener shape — internal fields must NOT leak.
                assert "safety_classification" not in p
                assert "voice_clone_reference_url" not in p
                assert "evidence" not in p
                # Required listener fields:
                assert "display_name" in p
                assert "description" in p
                assert "language_mix" in p
                assert "daypart_affinity" in p
                assert "signature_phrases_preview" in p
                assert len(p["signature_phrases_preview"]) <= 3
                # sample_clip_url should be populated for live tests; allow
                # None gracefully in case the seed step was skipped.
                assert "sample_clip_url" in p
    run(go())


def test_me_returns_daypart_default_when_unselected():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Clear selection for the test user.
        await db.users.update_one(
            {"email": "test@bigfm.dubai"},
            {"$unset": {"selected_persona_id": "",
                                  "selected_persona_at": ""}})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.get("/api/personas/me", headers=hdr)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["selected_persona_id"] is None
            assert j["source"] == "daypart_default"
            assert j["persona"] is not None
            assert j["persona"]["persona_id"].startswith("p39_")
    run(go())


def test_select_then_me_returns_user_selected():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.post("/api/personas/select", headers=hdr,
                                            json={"persona_id": "p39_friday_night_hype"})
            assert r.status_code == 200, r.text
            assert r.json()["selected_persona_id"] == "p39_friday_night_hype"
            r2 = await ac.get("/api/personas/me", headers=hdr)
            assert r2.status_code == 200
            j = r2.json()
            assert j["selected_persona_id"] == "p39_friday_night_hype"
            assert j["source"] == "user_selected"
            assert j["persona"]["persona_id"] == "p39_friday_night_hype"
    run(go())


def test_select_rejects_unknown_persona_id():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.post("/api/personas/select", headers=hdr,
                                            json={"persona_id": "p39_does_not_exist"})
            assert r.status_code == 400, r.text
    run(go())


def test_select_rejects_unsafe_persona():
    """If an admin manually flips a persona to is_safe=False, select MUST
    refuse it.  We mutate the DB row, hit /select, then restore the row."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        await db.rj_personality_profiles.update_one(
            {"_id": "p39_lunch_cousin"},
            {"$set": {"safety_classification.is_safe": False}})
        try:
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                      base_url="http://test", timeout=60) as ac:
                hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
                r = await ac.post("/api/personas/select", headers=hdr,
                                                json={"persona_id": "p39_lunch_cousin"})
                assert r.status_code == 400
                # And chat should 403:
                r2 = await ac.post("/api/personas/chat", headers=hdr,
                                                  json={"persona_id": "p39_lunch_cousin",
                                                              "listener_input_text": "hi"})
                assert r2.status_code == 403
        finally:
            await db.rj_personality_profiles.update_one(
                {"_id": "p39_lunch_cousin"},
                {"$set": {"safety_classification.is_safe": True}})
    run(go())


def test_chat_returns_text_and_audio():
    """Live LLM + ElevenLabs path.  Asserts the round-trip; tolerates a
    null audio_url if ElevenLabs is rate-limited (audio_error populated)."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=90) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.post("/api/personas/chat", headers=hdr,
                                            json={"persona_id": "p39_dawn_caller",
                                                        "listener_input_text": "What's a good morning routine?"})
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["ok"] is True
            assert j["persona_id"] == "p39_dawn_caller"
            assert isinstance(j["response_text"], str)
            assert len(j["response_text"]) >= 10
            # audio_url may be None if quota was hit; audio_error then populated
            if j["response_audio_url"] is None:
                assert j.get("audio_error"), \
                      "audio_url None must come with an audio_error reason"
    run(go())


def test_admin_reclassify_refreshes_all_personas():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Wipe last_classified_at to confirm it's repopulated.
        await db.rj_personality_profiles.update_many(
            {"is_launch_persona": True},
            {"$unset": {"last_classified_at": ""}})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "admin@bigfm.dubai", "AdminPass123!")
            r = await ac.post("/api/admin/personas/reclassify_all", headers=hdr)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["examined"] >= 10
            assert j["became_unsafe"] == []
            # All 10 launch personas now have last_classified_at populated:
            cnt = await db.rj_personality_profiles.count_documents({
                "is_launch_persona": True,
                "last_classified_at": {"$exists": True}})
            assert cnt == 10
    run(go())


def test_listener_cannot_call_admin_reclassify():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.post("/api/admin/personas/reclassify_all", headers=hdr)
            assert r.status_code in (401, 403), r.text
    run(go())


def test_safety_audit_endpoint_returns_10_launch_personas():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "admin@bigfm.dubai", "AdminPass123!")
            r = await ac.get("/api/admin/personas/safety_audit", headers=hdr)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["total"] >= 10
            launch = [p for p in j["personas"] if p.get("is_launch_persona")]
            assert len(launch) == 10
            for p in launch:
                assert p["safety_classification"]["is_safe"] is True
                assert p["voice_id"]
    run(go())
