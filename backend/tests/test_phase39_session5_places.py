"""Phase 39 Session 5 — DBSCAN + places endpoints tests."""
import asyncio, os, sys, uuid
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
except Exception: pass
from motor.motor_asyncio import AsyncIOMotorClient

def run(c): return asyncio.get_event_loop().run_until_complete(c)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_dbscan_cluster_minimum_threshold():
    from routes.places import _cluster_grid
    now = datetime.now(timezone.utc)
    # Cluster A: 8 visits at (25.2,55.3); Cluster B: 4 visits at (25.5,55.6) — should be skipped (<5)
    events = []
    for _ in range(8):
        events.append({"lat": 25.2, "lng": 55.3, "captured_at": now})
    for _ in range(4):
        events.append({"lat": 25.5, "lng": 55.6, "captured_at": now})
    clusters = _cluster_grid(events)
    assert len(clusters) == 1
    assert clusters[0]["visit_count"] == 8


def test_dbscan_two_distinct_clusters():
    from routes.places import _cluster_grid
    now = datetime.now(timezone.utc)
    events = []
    for _ in range(10): events.append({"lat": 25.20, "lng": 55.30, "captured_at": now})
    for _ in range(7):  events.append({"lat": 24.50, "lng": 54.60, "captured_at": now})
    clusters = _cluster_grid(events)
    assert len(clusters) == 2


def test_frequent_endpoint_403_without_consent():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Reset consent.
        await db.users.update_one({"email": "test@bigfm.dubai"},
                                                          {"$set": {"location_consent_level": 0}})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                                            json={"email": "test@bigfm.dubai",
                                                        "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r2 = await ac.get("/api/places/frequent", headers=hdr)
            assert r2.status_code == 403
            assert r2.json()["detail"]["required_level"] == 3
    run(go())


def test_refresh_clusters_and_endpoints_e2e():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Seed: 12 events at one location for the test user.
        u = await db.users.find_one({"email": "test@bigfm.dubai"})
        await db.users.update_one({"_id": u["_id"]},
                                                          {"$set": {"location_consent_level": 3}})
        await db.UserTravelEvents.delete_many({"user_id": u["user_id"]})
        await db.UserFrequentPlaces.delete_many({"user_id": u["user_id"]})
        now = datetime.now(timezone.utc)
        for i in range(12):
            await db.UserTravelEvents.insert_one({
                "_id": uuid.uuid4().hex,
                "user_id": u["user_id"],
                "lat": 25.20 + (i % 3) * 0.00001,  # all within same grid cell
                "lng": 55.30,
                "captured_at": now - timedelta(hours=i),
                "app_state": "foreground"})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                                            json={"email": "test@bigfm.dubai",
                                                        "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r1 = await ac.post("/api/places/frequent/refresh", headers=hdr)
            assert r1.status_code == 200, r1.text
            j = r1.json()
            assert j["clusters_found"] >= 1
            assert j["inserted"] >= 1
            # Idempotent re-run.
            r2 = await ac.post("/api/places/frequent/refresh", headers=hdr)
            assert r2.json()["updated"] >= 1
            assert r2.json()["inserted"] == 0
            # List
            r3 = await ac.get("/api/places/frequent", headers=hdr)
            assert r3.status_code == 200
            places = r3.json()["places"]
            assert len(places) >= 1
            pid = places[0]["place_id"]
            # Confirm
            r4 = await ac.post(f"/api/places/frequent/{pid}/confirm",
                                              headers=hdr, json={"confirmed": True})
            assert r4.status_code == 200
            # Hide
            r5 = await ac.post(f"/api/places/frequent/{pid}/hide", headers=hdr)
            assert r5.status_code == 200
            # After hide, the place is filtered out
            r6 = await ac.get("/api/places/frequent", headers=hdr)
            assert all(p["place_id"] != pid for p in r6.json()["places"])
        # Cleanup
        await db.UserTravelEvents.delete_many({"user_id": u["user_id"]})
        await db.UserFrequentPlaces.delete_many({"user_id": u["user_id"]})
    run(go())
