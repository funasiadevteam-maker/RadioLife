"""Phase 39 Session 3 — premium trial + persona settings tests."""
from __future__ import annotations
import asyncio, os, sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)
def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _login(ac, email, pw):
    r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _reset_user_trial(db):
    """Clear trial fields on test@bigfm.dubai so each test starts clean."""
    await db.users.update_one(
        {"email": "test@bigfm.dubai"},
        {"$unset": {"subscription_status": "", "trial_started_at": "",
                              "trial_ends_at": "", "trial_ended_at": "",
                              "persona_settings": ""}})


def test_start_trial_then_status_and_anti_abuse():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        await _reset_user_trial(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r1 = await ac.post("/api/billing/start_premium_trial", headers=hdr)
            assert r1.status_code == 200, r1.text
            j = r1.json()
            assert j["subscription_status"] == "trial"
            assert j["trial_ends_at"]
            # status endpoint reflects this:
            r2 = await ac.get("/api/billing/trial_status", headers=hdr)
            assert r2.status_code == 200
            sj = r2.json()
            assert sj["is_premium_or_trial"] is True
            assert sj["trial_remaining_seconds"] > 0
            # immediate retry = 403 anti-abuse
            r3 = await ac.post("/api/billing/start_premium_trial", headers=hdr)
            assert r3.status_code == 403
            assert r3.json()["detail"]["code"] in ("trial_already_active",
                                                                                              "trial_within_repeat_window",
                                                                                              "already_premium")
        await _reset_user_trial(db)
    run(go())


def test_end_trial_idempotent_after_expiry():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        await _reset_user_trial(db)
        # Seed an already-expired trial.
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        await db.users.update_one(
            {"email": "test@bigfm.dubai"},
            {"$set": {"subscription_status": "trial",
                              "trial_started_at": past,
                              "trial_ends_at": past}})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r1 = await ac.post("/api/billing/end_trial", headers=hdr)
            assert r1.status_code == 200
            j = r1.json()
            assert j["flipped"] is True
            assert j["subscription_status"] == "free"
            # idempotent re-call: nothing to flip, still 200, free.
            r2 = await ac.post("/api/billing/end_trial", headers=hdr)
            assert r2.status_code == 200
            assert r2.json()["flipped"] is False
            assert r2.json()["subscription_status"] == "free"
        await _reset_user_trial(db)
    run(go())


def test_persona_settings_403_for_free_then_200_during_trial():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        await _reset_user_trial(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            # Free user → 403
            r1 = await ac.post("/api/personas/settings", headers=hdr,
                                            json={"humor": 8, "energy": 6, "slang": 3})
            assert r1.status_code == 403
            assert r1.json()["detail"]["code"] == "premium_required"
            # Start trial → settings now succeed
            await ac.post("/api/billing/start_premium_trial", headers=hdr)
            r2 = await ac.post("/api/personas/settings", headers=hdr,
                                            json={"humor": 8, "energy": 6, "slang": 3})
            assert r2.status_code == 200, r2.text
            assert r2.json()["persona_settings"]["humor"] == 8
            # Validation: out of range → 400/422
            r3 = await ac.post("/api/personas/settings", headers=hdr,
                                            json={"humor": 99, "energy": 5, "slang": 5})
            assert r3.status_code in (400, 422)
        await _reset_user_trial(db)
    run(go())


def test_premium_gate_helper_pure_predicate():
    """Pure unit test for is_premium_or_trial across all states."""
    from services.premium_gate import is_premium_or_trial
    assert is_premium_or_trial({"is_premium": True}) is True
    assert is_premium_or_trial({"subscription": {"status": "active"}}) is True
    assert is_premium_or_trial({"subscription_status": "premium"}) is True
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert is_premium_or_trial({"subscription_status": "trial",
                                                                "trial_ends_at": future}) is True
    assert is_premium_or_trial({"subscription_status": "trial",
                                                                "trial_ends_at": past}) is False
    assert is_premium_or_trial({}) is False
    assert is_premium_or_trial(None) is False


def test_apply_settings_to_prompt_directives():
    from services.premium_gate import apply_settings_to_prompt
    base = "You are a host."
    # midpoint → no directives appended
    assert apply_settings_to_prompt(base, {"humor": 5, "energy": 5,
                                                                                "slang": 5}) == base
    # extremes → directives appended
    out = apply_settings_to_prompt(base, {"humor": 10, "energy": 1,
                                                                                  "slang": 9})
    assert "funnier" in out
    assert "Low-key" in out
    assert "colloquial" in out
