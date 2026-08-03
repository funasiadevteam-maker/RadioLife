"""Phase 39 Session 7 — AI Memory Summary dedicated checks."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass
from motor.motor_asyncio import AsyncIOMotorClient


def run(c): return asyncio.get_event_loop().run_until_complete(c)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_summary_returns_string_and_uses_gpt4o_mini_module():
    """Verifies the module imports OpenAI client and targets gpt-4o-mini."""
    import importlib
    mod = importlib.import_module("routes.ai_memory")
    src = open(mod.__file__).read()
    assert "gpt-4o-mini" in src
    assert "from openai import OpenAI" in src


def test_summary_no_clock_time_phrase():
    """Sanity check — system prompt forbids clock times. The cached summary
    text must not contain explicit AM/PM/o'clock markers."""
    import re
    import importlib
    from httpx import ASGITransport, AsyncClient

    async def go():
        server = importlib.import_module("server")
        db = _db()
        u = await db.users.find_one({"email": "test@bigfm.dubai"})
        await db.users.update_one(
            {"user_id": u["user_id"]},
            {"$set": {"location_consent_level": 3},
             "$unset": {"ai_memory_summary": "", "ai_memory_summary_built_at": ""}})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r2 = await ac.get("/api/personas/memory_summary", headers=hdr)
            assert r2.status_code == 200, r2.text
            text = r2.json()["summary_text"]
            assert not re.search(
                r"\b(\d{1,2})\s*(AM|PM|am|pm|:00|o'?clock)\b", text), \
                f"summary leaked clock time: {text}"
    run(go())


def test_summary_consent_change_invalidates_via_forget():
    import importlib
    from httpx import ASGITransport, AsyncClient

    async def go():
        server = importlib.import_module("server")
        db = _db()
        u = await db.users.find_one({"email": "test@bigfm.dubai"})
        uid = u["user_id"]
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            # Prime cache at consent=3
            await db.users.update_one({"user_id": uid},
                {"$set": {"location_consent_level": 3},
                 "$unset": {"ai_memory_summary": "", "ai_memory_summary_built_at": ""}})
            r2 = await ac.get("/api/personas/memory_summary", headers=hdr)
            assert r2.json()["cached"] is False
            r3 = await ac.get("/api/personas/memory_summary", headers=hdr)
            assert r3.json()["cached"] is True
            # Forget then re-fetch → fresh build
            rf = await ac.post("/api/personas/memory_summary/forget", headers=hdr)
            assert rf.status_code == 200 and rf.json()["ok"] is True
            r4 = await ac.get("/api/personas/memory_summary", headers=hdr)
            assert r4.json()["cached"] is False
    run(go())
