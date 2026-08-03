"""Phase 39 Session 7 — AI Memory Summary + hard-delete cascade tests."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

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


def test_ai_memory_summary_consent_3_mentions_places():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        u = await db.users.find_one({"email": "test@bigfm.dubai"})
        uid = u["user_id"]
        await db.users.update_one({"user_id": uid},
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
            j = r2.json()
            assert j["summary_text"] and len(j["summary_text"]) > 10
            assert j["frequent_places_count"] >= 0
            assert j["cached"] is False
            # Second call → cached
            r3 = await ac.get("/api/personas/memory_summary", headers=hdr)
            assert r3.json()["cached"] is True
            # Forget invalidates
            r4 = await ac.post("/api/personas/memory_summary/forget", headers=hdr)
            assert r4.status_code == 200
            r5 = await ac.get("/api/personas/memory_summary", headers=hdr)
            assert r5.json()["cached"] is False
    run(go())


def test_ai_memory_summary_consent_0_redacts():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        u = await db.users.find_one({"email": "test@bigfm.dubai"})
        uid = u["user_id"]
        await db.users.update_one({"user_id": uid},
            {"$set": {"location_consent_level": 0},
             "$unset": {"ai_memory_summary": "", "ai_memory_summary_built_at": ""}})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r2 = await ac.get("/api/personas/memory_summary", headers=hdr)
            assert r2.status_code == 200
            j = r2.json()
            # No place/pattern counts surfaced when consent<3
            assert j["frequent_places_count"] == 0
            assert j["route_patterns_count"] == 0
        # Restore for downstream tests
        await db.users.update_one({"user_id": uid},
            {"$set": {"location_consent_level": 3}})
    run(go())


def test_hard_delete_sweep_cascade():
    async def go():
        from services.hard_delete_sweep import sweep_hard_deletes, hard_delete_user, _anon_id
        db = _db()
        # Seed a user soft-deleted >30 days ago + PII rows + audit row
        uid = "u_hd_" + uuid.uuid4().hex[:8]
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        await db.users.insert_one({"_id": uid, "user_id": uid,
                                   "email": uid + "@example.com",
                                   "deleted_at": old})
        await db.UserTravelEvents.insert_one(
            {"_id": uuid.uuid4().hex, "user_id": uid, "lat": 25.2, "lng": 55.3,
             "captured_at": datetime.now(timezone.utc)})
        await db.UserFrequentPlaces.insert_one(
            {"_id": uuid.uuid4().hex, "user_id": uid, "place_id": "p1",
             "lat": 25.2, "lng": 55.3})
        await db.LocationPrivacyAuditLogs.insert_one(
            {"_id": uuid.uuid4().hex, "user_id": uid, "action": "consent_change",
             "timestamp": datetime.now(timezone.utc).isoformat()})

        res = await sweep_hard_deletes(db)
        assert res["users_hard_deleted"] >= 1

        # PII collections empty
        assert await db.UserTravelEvents.count_documents({"user_id": uid}) == 0
        assert await db.UserFrequentPlaces.count_documents({"user_id": uid}) == 0
        # User document hard-deleted
        assert await db.users.find_one({"user_id": uid}) is None
        # Audit log anonymized (row preserved with anon user_id)
        anon = _anon_id(uid)
        assert await db.LocationPrivacyAuditLogs.count_documents(
            {"user_id": anon}) >= 1
        # Tombstone written
        assert await db.users_tombstones.find_one({"_id": anon}) is not None
        # Cleanup the tombstone
        await db.users_tombstones.delete_one({"_id": anon})
        await db.LocationPrivacyAuditLogs.delete_many({"user_id": anon})
    run(go())


def test_export_includes_new_collections():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        u = await db.users.find_one({"email": "test@bigfm.dubai"})
        uid = u["user_id"]
        await db.users.update_one({"user_id": uid},
            {"$set": {"location_consent_level": 3}})
        # Ensure at least one row in each new collection.
        await db.UserTrips.update_one(
            {"_id": "trip_export_test"},
            {"$set": {"_id": "trip_export_test", "user_id": uid,
                      "started_at": datetime.now(timezone.utc),
                      "ended_at":   datetime.now(timezone.utc)}}, upsert=True)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r2 = await ac.get("/api/privacy/export", headers=hdr)
            assert r2.status_code == 200
            j = r2.json()
            assert "trips" in j
            assert "route_patterns" in j
            assert "business_visits" in j
            assert isinstance(j["trips"], list)
        await db.UserTrips.delete_one({"_id": "trip_export_test"})
    run(go())
