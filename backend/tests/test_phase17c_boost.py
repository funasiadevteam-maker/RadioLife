"""Phase 17c — "Boost this offer" lever (6 backend tests)."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import httpx
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient   # noqa: E402

VENUE_ID = "venue_demo_karak"


def _login(email, pwd):
    c = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c.post("/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    raw = r.headers.get("set-cookie", "")
    c.cookies.set("bigfm_session", raw.split("bigfm_session=", 1)[1].split(";", 1)[0])
    return c


def _owner(): return _login("admin@bigfm.dubai", "AdminPass123!")
def _loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    return asyncio.get_event_loop()
def _db():    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ─── 1. Eligibility from top-drop > 30% on first stage ──────────
def test_offer_is_boost_eligible_when_first_stage_drop_above_30pct():
    loop = _loop(); db = _db()
    oid = f"ofr_bel_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Boost-eligible", "offer_type": "percent",
            "discount_value": 20, "status": "active", "market": "dubai",
        })
        now = datetime.now(timezone.utc)
        # 100 impressions, 30 saves → 70% drop on first stage.
        for i in range(100):
            await db.offer_events.insert_one({
                "id": f"e_imp_{oid}_{i}", "offer_id": oid,
                "stage": "impression", "timestamp": now})
        for i in range(30):
            await db.offer_events.insert_one({
                "id": f"e_save_{oid}_{i}", "offer_id": oid,
                "stage": "save", "timestamp": now})
        c = _owner()
        r = c.get(f"/api/venue/{VENUE_ID}/offers/{oid}/funnel?period=month")
        d = r.json()
        assert d["boost_eligible"] is True, d
        c.close()

    try: loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offer_events.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))


# ─── 2. Boost endpoint mutates discount + persists original ────
def test_boost_endpoint_increases_discount_and_persists_original():
    loop = _loop(); db = _db()
    oid = f"ofr_bst_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Boost target", "offer_type": "percent",
            "discount_value": 10, "status": "active", "market": "dubai"})
        c = _owner()
        r = c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        b = d["boost"]
        assert b["original_discount_value"] == 10
        assert b["boosted_discount_value"] == 15      # +5% default
        assert b["status"] == "active"
        # Offer document mutated.
        offer = await db.offers.find_one({"id": oid})
        assert offer["discount_value"]            == 15
        assert offer["boost_active"]              is True
        assert offer["boost_original_value"] == 10
        c.close()

    try: loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        loop.run_until_complete(db.offer_boosts.delete_many({"offer_id": oid}))


# ─── 3. Auto-revert after duration expires ──────────────────────
def test_boost_auto_reverts_discount_after_duration_expires():
    loop = _loop(); db = _db()
    from services.offer_boost import revert_expired_boosts

    oid = f"ofr_brv_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Revert me", "offer_type": "percent",
            "discount_value": 25, "status": "active", "market": "dubai"})
        c = _owner()
        c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost",
                  json={"duration_hours": 24, "discount_bump_pct": 5})
        # Force-expire by rewinding ends_at into the past.
        await db.offer_boosts.update_one(
            {"offer_id": oid, "status": "active"},
            {"$set": {"ends_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
        # Trigger sweep.
        out = await revert_expired_boosts(db)
        assert out["reverted"] >= 1
        offer = await db.offers.find_one({"id": oid})
        assert offer["discount_value"] == 25, offer
        assert offer["boost_active"]    is False
        b = await db.offer_boosts.find_one({"offer_id": oid})
        assert b["status"] == "completed"
        c.close()

    try: loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        loop.run_until_complete(db.offer_boosts.delete_many({"offer_id": oid}))


# ─── 4. 2-per-14-days limit ──────────────────────────────────────
def test_boost_limit_enforced_2_per_offer_per_14_days():
    loop = _loop(); db = _db()
    oid = f"ofr_blim_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Limit me", "offer_type": "percent",
            "discount_value": 10, "status": "active", "market": "dubai"})
        c = _owner()
        # Boost 1 — succeeds, then immediately complete it so it doesn't block
        # the next attempt on the active-boost rule.
        c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost", json={})
        await db.offer_boosts.update_many(
            {"offer_id": oid, "status": "active"},
            {"$set": {"status": "completed"}})
        # Boost 2 — succeeds.
        r2 = c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost", json={})
        assert r2.status_code == 200, r2.text
        await db.offer_boosts.update_many(
            {"offer_id": oid, "status": "active"},
            {"$set": {"status": "completed"}})
        # Boost 3 — should hit 2-per-14-day cap.
        r3 = c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost", json={})
        assert r3.status_code == 409, r3.text
        assert r3.json()["detail"]["code"] == "boost_limit"
        c.close()

    try: loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        loop.run_until_complete(db.offer_boosts.delete_many({"offer_id": oid}))


# ─── 5. Only one active boost per offer ─────────────────────────
def test_boost_only_one_active_per_offer():
    loop = _loop(); db = _db()
    oid = f"ofr_b1_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Solo boost", "offer_type": "percent",
            "discount_value": 8, "status": "active", "market": "dubai"})
        c = _owner()
        r1 = c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost", json={})
        assert r1.status_code == 200
        # Second boost while first is still active.
        r2 = c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost", json={})
        assert r2.status_code == 409
        assert r2.json()["detail"]["code"] == "already_active"
        c.close()

    try: loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        loop.run_until_complete(db.offer_boosts.delete_many({"offer_id": oid}))


# ─── 6. Push fan-out targets market + savers ────────────────────
def test_boost_notification_fanout_targets_market_and_savers():
    loop = _loop(); db = _db()
    oid = f"ofr_bnf_{uuid.uuid4().hex[:6]}"
    saver_uid = f"u_saver_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Push me", "offer_type": "percent",
            "discount_value": 12, "status": "active", "market": "dubai"})
        # Seed a saver who issued a coupon for this venue in last 90d.
        now = datetime.now(timezone.utc)
        await db.coupons.insert_one({
            "coupon_id":  f"cpn_seed_{uuid.uuid4().hex[:6]}",
            "venue_id":  VENUE_ID,
            "user_id":   saver_uid,
            "issued_at": now - timedelta(days=10),
            "status":     "issued",
        })
        c = _owner()
        r = c.post(f"/api/venue/{VENUE_ID}/offers/{oid}/boost", json={})
        assert r.status_code == 200, r.text
        b = r.json()["boost"]
        assert b["push_count"] >= 1
        # Verify a notification doc lives for our saver.
        notif = await db.notifications.find_one({"offer_id": oid,
                                                                            "user_id": saver_uid})
        assert notif, "saver did not receive a push notification"
        assert "% off" in (notif.get("body") or "")
        c.close()

    try: loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        loop.run_until_complete(db.offer_boosts.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.notifications.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.coupons.delete_many({"user_id": saver_uid}))
