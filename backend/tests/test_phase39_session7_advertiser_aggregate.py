"""Phase 39 Session 7 — Advertiser aggregate dashboard + geo-anchored ads."""
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


async def _seed_visits(db, category="cafe", bucket="morning", n=25):
    """Seed N business visits across N distinct synthetic users."""
    uids = []
    for i in range(n):
        uid = f"u_agg_seed_{i:03d}"
        uids.append(uid)
        await db.UserBusinessVisits.insert_one({
            "_id":              uuid.uuid4().hex,
            "user_id":      uid,
            "trip_id":       "trip_seed_" + str(i),
            "place_id":   "fp_seed_" + str(i),
            "category":   category,
            "label":         "Karak Cafe Branch",
            "visited_at": datetime.now(timezone.utc),
            "time_bucket": bucket,
            "detected_at": datetime.now(timezone.utc),
        })
    return uids


async def _cleanup(db, uids):
    await db.UserBusinessVisits.delete_many({"user_id": {"$in": uids}})


def test_aggregate_too_small_returns_422():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Cleanup any prior seeds with the same uid prefix.
        await db.UserBusinessVisits.delete_many({"category": "rare_cat_test"})
        uids = await _seed_visits(db, category="rare_cat_test", n=5)  # < 20
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r2 = await ac.get(
                "/api/advertiser/audience/aggregate?category=rare_cat_test",
                headers=hdr)
            assert r2.status_code == 422
            assert r2.json()["detail"]["code"] == "segment_too_small"
        await _cleanup(db, uids)
    run(go())


def test_aggregate_safe_returns_counts():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        await db.UserBusinessVisits.delete_many({"category": "agg_safe_test"})
        uids = await _seed_visits(db, category="agg_safe_test",
                                  bucket="morning", n=25)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r2 = await ac.get(
                "/api/advertiser/audience/aggregate?category=agg_safe_test",
                headers=hdr)
            assert r2.status_code == 200, r2.text
            j = r2.json()
            assert j["segment_size"] == 25
            assert j["top_categories"][0]["category"] == "agg_safe_test"
            # Audit row written
            n = await db.AdvertiserAggregateAuditLogs.count_documents({
                "action": "audience_aggregate", "outcome": "ok"})
            assert n >= 1
        await _cleanup(db, uids)
    run(go())


def test_geo_anchored_campaign_create_and_match():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        await db.UserBusinessVisits.delete_many({"category": "match_test_cat"})
        await db.GeoAnchoredCampaigns.delete_many({"target_category": "match_test_cat"})
        uids = await _seed_visits(db, category="match_test_cat",
                                  bucket="evening", n=25)
        async with AsyncClient(transport=ASGITransport(app=server.app),
                               base_url="http://test", timeout=60) as ac:
            r = await ac.post("/api/auth/login",
                              json={"email": "test@bigfm.dubai",
                                    "password": "TestUser123!"})
            hdr = {"Authorization": f"Bearer {r.json()['session_token']}"}
            r2 = await ac.post(
                "/api/advertiser/campaigns/geo_anchored",
                headers=hdr,
                json={"name": "Test Geo",
                      "target_category": "match_test_cat",
                      "target_time_bucket": "evening",
                      "creative_audio_url": "https://example.com/x.mp3",
                      "budget_aed": 100.0})
            assert r2.status_code == 200, r2.text
            cid = r2.json()["campaign_id"]
            assert r2.json()["estimated_segment_size"] == 25

            # Match against a synthetic user with matching pattern.
            test_uid = "u_match_test_" + uuid.uuid4().hex[:6]
            await db.users.insert_one({
                "_id":               test_uid, "user_id": test_uid,
                "email":          test_uid + "@bigfm.dubai",
                "location_consent_level": 3})
            await db.UserFrequentPlaces.insert_one({
                "_id":           uuid.uuid4().hex, "user_id": test_uid,
                "place_id": "fp_demo_match", "lat": 25.2, "lng": 55.3,
                "category": "match_test_cat", "label": "Demo",
                "visit_count": 10, "last_seen": datetime.now(timezone.utc),
                "user_hidden": False})
            await db.UserRoutePatterns.insert_one({
                "_id":          uuid.uuid4().hex, "user_id": test_uid,
                "origin_place_id": "fp_home_demo",
                "destination_place_id": "fp_demo_match",
                "dominant_time_bucket": "evening",
                "repeat_count": 4,
                "last_seen": datetime.now(timezone.utc)})

            from routes.advertiser_aggregate import select_geo_anchored_ad_for_user
            ad = await select_geo_anchored_ad_for_user(db, test_uid)
            assert ad is not None
            assert ad["campaign_id"] == cid

            # Impression count incremented
            camp = await db.GeoAnchoredCampaigns.find_one({"campaign_id": cid})
            assert camp["delivered_impressions"] >= 1

            # Cleanup synthetic match user
            await db.users.delete_one({"user_id": test_uid})
            await db.UserFrequentPlaces.delete_many({"user_id": test_uid})
            await db.UserRoutePatterns.delete_many({"user_id": test_uid})
        await _cleanup(db, uids)
        await db.GeoAnchoredCampaigns.delete_many({"target_category": "match_test_cat"})
    run(go())


def test_geo_anchored_consent_zero_no_match():
    """consent<3 user must NOT match any geo-anchored campaign."""
    async def go():
        from routes.advertiser_aggregate import select_geo_anchored_ad_for_user
        db = _db()
        uid = "u_consent0_" + uuid.uuid4().hex[:6]
        await db.users.insert_one({"_id": uid, "user_id": uid,
                                   "email": uid + "@bigfm.dubai",
                                   "location_consent_level": 0})
        ad = await select_geo_anchored_ad_for_user(db, uid)
        assert ad is None
        await db.users.delete_one({"user_id": uid})
    run(go())
