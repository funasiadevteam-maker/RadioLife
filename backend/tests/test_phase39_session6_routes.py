"""Phase 39 Session 6 — Route patterns + trips + business visits tests."""
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


def _seed_places(uid):
    """Two anchor places: Home + Office (Cafe category for business-visit gate)."""
    return [
        {"_id": uuid.uuid4().hex, "user_id": uid, "place_id": "fp_home_abc",
         "lat": 25.20, "lng": 55.30, "label": "Home", "category": "home",
         "visit_count": 40, "confidence": "high",
         "first_seen": datetime.now(timezone.utc) - timedelta(days=30),
         "last_seen":  datetime.now(timezone.utc),
         "user_hidden": False, "user_confirmed": True,
         "detected_at": datetime.now(timezone.utc),
         "last_refreshed_at": datetime.now(timezone.utc)},
        {"_id": uuid.uuid4().hex, "user_id": uid, "place_id": "fp_cafe_xyz",
         "lat": 25.21, "lng": 55.31, "label": "Karak Cafe", "category": "cafe",
         "visit_count": 20, "confidence": "high",
         "first_seen": datetime.now(timezone.utc) - timedelta(days=30),
         "last_seen":  datetime.now(timezone.utc),
         "user_hidden": False, "user_confirmed": None,
         "detected_at": datetime.now(timezone.utc),
         "last_refreshed_at": datetime.now(timezone.utc)},
    ]


def _seed_trip_events(uid, base_dt, n_events=4):
    """One trip: 4 events drifting from Home → Cafe, separated by ~25 minutes,
    each >100m from previous."""
    pts = [
        (25.200, 55.300),   # home
        (25.204, 55.304),
        (25.207, 55.307),
        (25.210, 55.310),   # cafe-ish
    ]
    out = []
    for i, (lat, lng) in enumerate(pts[:n_events]):
        out.append({
            "_id": uuid.uuid4().hex,
            "user_id": uid,
            "lat": lat, "lng": lng,
            "captured_at": base_dt + timedelta(minutes=25 * i),
            "app_state": "foreground",
            "accuracy_m": 5,
            "source": "user_post",
        })
    return out


async def _reset(db, uid):
    await db.UserTravelEvents.delete_many({"user_id": uid})
    await db.UserFrequentPlaces.delete_many({"user_id": uid})
    await db.UserTrips.delete_many({"user_id": uid})
    await db.UserRoutePatterns.delete_many({"user_id": uid})
    await db.UserBusinessVisits.delete_many({"user_id": uid})


def test_segment_events_into_one_trip():
    """4 chronologically close events at >100m separation → 1 trip."""
    from services.route_pattern_detection import _segment_events_into_trips
    now = datetime.now(timezone.utc)
    events = _seed_trip_events("u_test", now)
    trips = _segment_events_into_trips(events)
    assert len(trips) == 1
    assert len(trips[0]) == 4


def test_pattern_detection_3_repeats():
    """3 repeated Home→Cafe trips → 1 UserRoutePatterns row."""
    async def go():
        from services.route_pattern_detection import detect_for_user
        db = _db()
        uid = "u_test_pattern_" + uuid.uuid4().hex[:6]
        await _reset(db, uid)
        await db.UserFrequentPlaces.insert_many(_seed_places(uid))
        now = datetime.now(timezone.utc)
        # 3 trip repeats spread across last 7 days, all at morning bucket.
        for d in range(3):
            morning = now.replace(hour=8, minute=0, second=0,
                                  microsecond=0) - timedelta(days=d)
            await db.UserTravelEvents.insert_many(
                _seed_trip_events(uid, morning))
        res = await detect_for_user(db, uid)
        assert res["trips_inserted"] >= 3
        assert res["patterns_upserted"] >= 1
        pat = await db.UserRoutePatterns.find_one({"user_id": uid})
        assert pat is not None
        assert pat["origin_place_id"] == "fp_home_abc"
        assert pat["destination_place_id"] == "fp_cafe_xyz"
        assert pat["repeat_count"] >= 3
        assert pat["dominant_time_bucket"] == "morning"
        # Cafe destination → business_visit captured
        bv_count = await db.UserBusinessVisits.count_documents(
            {"user_id": uid, "category": "cafe"})
        assert bv_count >= 1
        # Idempotent re-run.
        res2 = await detect_for_user(db, uid)
        assert res2["trips_inserted"] == 0
        await _reset(db, uid)
    run(go())


def test_endpoints_403_at_consent_low():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        await db.users.update_one(
            {"email": "test@bigfm.dubai"},
            {"$set": {"location_consent_level": 0}})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            for path in ("/api/routes/patterns",
                         "/api/routes/trips",
                         "/api/routes/business_visits"):
                rr = await ac.get(path, headers=hdr)
                assert rr.status_code == 403, f"{path} → {rr.status_code}"
                assert rr.json()["detail"]["required_level"] == 3
    run(go())


def test_endpoints_e2e_consent_3():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        u = await db.users.find_one({"email": "test@bigfm.dubai"})
        uid = u["user_id"]
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {"location_consent_level": 3}})
        await _reset(db, uid)
        await db.UserFrequentPlaces.insert_many(_seed_places(uid))
        now = datetime.now(timezone.utc)
        for d in range(3):
            morning = now.replace(hour=8, minute=0, second=0,
                                  microsecond=0) - timedelta(days=d)
            await db.UserTravelEvents.insert_many(
                _seed_trip_events(uid, morning))
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            # Manual detect sweep.
            r0 = await ac.post("/api/routes/detect", headers=hdr)
            assert r0.status_code == 200, r0.text
            assert r0.json()["patterns_upserted"] >= 1
            # Patterns
            r1 = await ac.get("/api/routes/patterns", headers=hdr)
            assert r1.status_code == 200
            assert r1.json()["count"] >= 1
            # Trips
            r2 = await ac.get("/api/routes/trips", headers=hdr)
            assert r2.status_code == 200
            assert r2.json()["count"] >= 3
            # business visits — category filter
            r3 = await ac.get("/api/routes/business_visits?category=cafe",
                              headers=hdr)
            assert r3.status_code == 200
            assert r3.json()["count"] >= 1
        await _reset(db, uid)
    run(go())
