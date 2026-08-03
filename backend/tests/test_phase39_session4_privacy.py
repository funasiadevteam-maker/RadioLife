"""Phase 39 Session 4 — privacy / consent / travel-event tests."""
from __future__ import annotations
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _login(ac, email, pw):
    r = await ac.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _reset(db):
    await db.users.update_one(
        {"email": "test@bigfm.dubai"},
        {"$unset": {"location_consent_level": "",
                              "location_consent_updated_at": "",
                              "deleted_at": "", "hard_delete_at": ""}})
    await db.LocationPrivacyAuditLogs.delete_many({"user_id": {"$exists": True}})
    await db.UserTravelEvents.delete_many({})


def test_consent_default_is_0_and_can_be_raised():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db(); await _reset(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.get("/api/privacy/consent", headers=hdr)
            assert r.json()["level"] == 0
            r2 = await ac.post("/api/privacy/consent", headers=hdr, json={"level": 3})
            assert r2.status_code == 200
            assert r2.json()["level"] == 3
            r3 = await ac.get("/api/privacy/consent", headers=hdr)
            assert r3.json()["level"] == 3
            # audit log records it
            r4 = await ac.get("/api/privacy/audit_log", headers=hdr)
            assert r4.status_code == 200
            entries = r4.json()["entries"]
            assert any(e["action"] == "consent_change" and e["new_level"] == 3
                                  for e in entries)
        await _reset(db)
    run(go())


def test_travel_event_403_below_required_level():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db(); await _reset(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            # Default level=0 → 403, required=2
            r = await ac.post("/api/privacy/travel_event", headers=hdr,
                                            json={"lat": 25.2, "lng": 55.3, "app_state": "foreground"})
            assert r.status_code == 403
            assert r.json()["detail"]["required_level"] == 2
            # Bump to level=1 (city only) → still 403
            await ac.post("/api/privacy/consent", headers=hdr, json={"level": 1})
            r2 = await ac.post("/api/privacy/travel_event", headers=hdr,
                                              json={"lat": 25.2, "lng": 55.3, "app_state": "foreground"})
            assert r2.status_code == 403
            # Bump to level=2 → 200
            await ac.post("/api/privacy/consent", headers=hdr, json={"level": 2})
            r3 = await ac.post("/api/privacy/travel_event", headers=hdr,
                                              json={"lat": 25.2, "lng": 55.3, "app_state": "foreground"})
            assert r3.status_code == 200, r3.text
            # background requires level 3 → 403 at level 2
            r4 = await ac.post("/api/privacy/travel_event", headers=hdr,
                                              json={"lat": 25.2, "lng": 55.3, "app_state": "background"})
            assert r4.status_code == 403
            assert r4.json()["detail"]["required_level"] == 3
            # Bump to 3 → background ok
            await ac.post("/api/privacy/consent", headers=hdr, json={"level": 3})
            r5 = await ac.post("/api/privacy/travel_event", headers=hdr,
                                              json={"lat": 25.2, "lng": 55.3, "app_state": "background"})
            assert r5.status_code == 200
        await _reset(db)
    run(go())


def test_export_returns_full_data_dump():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db(); await _reset(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            await ac.post("/api/privacy/consent", headers=hdr, json={"level": 3})
            await ac.post("/api/privacy/travel_event", headers=hdr,
                                      json={"lat": 25.1, "lng": 55.2, "app_state": "foreground"})
            r = await ac.get("/api/privacy/export", headers=hdr)
            assert r.status_code == 200
            j = r.json()
            assert "user_profile" in j
            assert "audit_log" in j and len(j["audit_log"]) >= 1
            assert "travel_events" in j and len(j["travel_events"]) == 1
            assert "wallet" in j
            assert "password_hash" not in j["user_profile"]
        await _reset(db)
    run(go())


def test_soft_delete_requires_exact_confirm_string():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db(); await _reset(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            r = await ac.post("/api/privacy/delete", headers=hdr,
                                          json={"confirm": "yes please"})
            assert r.status_code == 400
            r2 = await ac.post("/api/privacy/delete", headers=hdr,
                                            json={"confirm": "DELETE_MY_DATA"})
            assert r2.status_code == 200
            j = r2.json()
            assert j["recovery_window_days"] == 30
            assert j["hard_delete_at"]
            # User now has deleted_at + hard_delete_at
            u = await db.users.find_one({"email": "test@bigfm.dubai"})
            assert u.get("deleted_at")
            assert u.get("hard_delete_at")
        # Restore user
        await db.users.update_one(
            {"email": "test@bigfm.dubai"},
            {"$unset": {"deleted_at": "", "hard_delete_at": ""}})
        await _reset(db)
    run(go())


def test_consent_rate_limit_blocks_11th_change_in_24h():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db(); await _reset(db)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login(ac, "test@bigfm.dubai", "TestUser123!")
            # 10 alternating changes succeed; 11th blocks.
            for i in range(10):
                r = await ac.post("/api/privacy/consent", headers=hdr,
                                              json={"level": (i % 4)})
                assert r.status_code == 200, f"change #{i+1}: {r.text}"
            r11 = await ac.post("/api/privacy/consent", headers=hdr,
                                              json={"level": 1})
            assert r11.status_code == 429
            assert r11.json()["detail"]["code"] == "consent_rate_limit"
        await _reset(db)
    run(go())


def test_advertiser_safe_aggregation_guard():
    from routes.privacy import is_advertiser_safe_aggregation, MIN_SEGMENT_SIZE
    assert MIN_SEGMENT_SIZE == 20
    assert is_advertiser_safe_aggregation(19) is False
    assert is_advertiser_safe_aggregation(20) is True
    assert is_advertiser_safe_aggregation(5000) is True
