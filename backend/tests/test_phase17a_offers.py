"""Phase 17a — Offer CRUD + bulk import + caps tests (10 cases)."""
import asyncio
import io
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

VENUE_ID = "venue_demo_karak"


def _login(email, pwd):
    c = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c.post("/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    raw = r.headers.get("set-cookie", "")
    c.cookies.set("bigfm_session", raw.split("bigfm_session=", 1)[1].split(";", 1)[0])
    return c


def _owner(): return _login("admin@bigfm.dubai", "AdminPass123!")
def _staff(): return _login("test@bigfm.dubai",  "TestUser123!")


def _new_loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    return asyncio.get_event_loop()


# ─── 1. CRUD is role-gated ──────────────────────────────────────────
def test_offer_crud_role_gated():
    owner = _owner()
    # Owner can create + patch + delete.
    r = owner.post(f"/api/venue/{VENUE_ID}/offers",
                          json={"title": "Owner test", "offer_type": "percent",
                                  "discount_value": 25, "max_redemptions": 100})
    assert r.status_code == 200, r.text
    oid = r.json()["offer"]["id"]
    assert owner.patch(f"/api/venue/{VENUE_ID}/offers/{oid}",
                              json={"status": "paused"}).status_code == 200
    # Staff CANNOT create (role-gated to owner|manager).
    staff = _staff()
    r = staff.post(f"/api/venue/{VENUE_ID}/offers",
                          json={"title": "Staff test", "offer_type": "percent",
                                  "discount_value": 10})
    assert r.status_code == 403, r.text
    # Staff CAN list (view-only).
    r = staff.get(f"/api/venue/{VENUE_ID}/offers?status=active")
    assert r.status_code == 200, r.text
    # Cleanup.
    owner.delete(f"/api/venue/{VENUE_ID}/offers/{oid}")
    owner.close(); staff.close()


# ─── 2. Bulk import validates rows ─────────────────────────────────
def test_offer_bulk_import_validates_rows():
    csv = "title,offer_type,discount_value\n"\
           "Row OK 1,percent,15\n"\
           ",percent,5\n"\
           "Row OK 2,flat,3\n"\
           "Bad type,SOMETHING,5\n"
    owner = _owner()
    files = {"file": ("offers.csv", io.BytesIO(csv.encode()), "text/csv")}
    r = owner.post(f"/api/venue/{VENUE_ID}/offers/bulk_import?dry_run=true",
                          files=files)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is True
    by_row = {x["row"]: x for x in d["results"]}
    assert by_row[2]["status"] == "created"
    assert by_row[3]["status"] == "failed" and "title" in by_row[3]["error"]
    assert by_row[4]["status"] == "created"
    assert by_row[5]["status"] == "failed" and "offer_type" in by_row[5]["error"]
    owner.close()


# ─── 3. Dry-run doesn't write ──────────────────────────────────────
def test_offer_bulk_import_dry_run_does_not_write():
    owner = _owner()
    before = owner.get(f"/api/venue/{VENUE_ID}/offers?status=active&limit=200").json()["count"]
    csv = "title,offer_type,discount_value\nDry test A,percent,5\nDry test B,percent,5\n"
    files = {"file": ("offers.csv", io.BytesIO(csv.encode()), "text/csv")}
    owner.post(f"/api/venue/{VENUE_ID}/offers/bulk_import?dry_run=true", files=files)
    after = owner.get(f"/api/venue/{VENUE_ID}/offers?status=active&limit=200").json()["count"]
    assert before == after, f"dry_run wrote rows: {before}→{after}"
    owner.close()


# ─── 4. >500 rows rejected ─────────────────────────────────────────
def test_offer_bulk_import_rejects_over_500_rows():
    owner = _owner()
    lines = ["title,offer_type,discount_value"]
    for i in range(501):
        lines.append(f"Row {i},percent,5")
    csv = "\n".join(lines) + "\n"
    files = {"file": ("offers.csv", io.BytesIO(csv.encode()), "text/csv")}
    r = owner.post(f"/api/venue/{VENUE_ID}/offers/bulk_import?dry_run=true",
                          files=files)
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "too_many_rows"
    owner.close()


# ─── 5. Total cap auto-pause ────────────────────────────────────────
def test_offer_auto_pauses_on_total_cap_hit():
    loop = _new_loop()
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.offers import issue_coupon_for_offer, CapacityError
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    oid = f"ofr_test_total_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID, "business_id": "biz_demo_karak",
            "title": "Cap2", "offer_type": "percent", "discount_value": 10,
            "max_redemptions": 2, "status": "active", "issued_count": 0,
            "market": "dubai",
        })
        # First 2 issuances succeed; 3rd raises and offer is exhausted.
        await issue_coupon_for_offer(db, offer_id=oid, user_id="u1")
        await issue_coupon_for_offer(db, offer_id=oid, user_id="u2")
        try:
            await issue_coupon_for_offer(db, offer_id=oid, user_id="u3")
            assert False, "expected total_cap_hit"
        except CapacityError as e:
            assert e.reason == "total_cap_hit"
        o = await db.offers.find_one({"id": oid})
        assert o["status"] == "exhausted"
        assert o["auto_paused_reason"] == "total_cap"

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.coupons.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        client.close()


# ─── 6. Daily cap auto-pause ────────────────────────────────────────
def test_offer_auto_pauses_on_daily_cap_hit():
    loop = _new_loop()
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.offers import issue_coupon_for_offer, CapacityError, _local_date_iso
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    oid = f"ofr_test_daily_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID, "business_id": "biz_demo_karak",
            "title": "DailyCap", "offer_type": "percent", "discount_value": 10,
            "daily_cap": 1, "status": "active", "issued_count": 0, "market": "dubai",
        })
        await issue_coupon_for_offer(db, offer_id=oid, user_id="u1")
        try:
            await issue_coupon_for_offer(db, offer_id=oid, user_id="u2")
            assert False, "expected daily_cap_hit"
        except CapacityError as e:
            assert e.reason == "daily_cap_hit"
        o = await db.offers.find_one({"id": oid})
        assert o["status"] == "exhausted"
        assert o["auto_paused_reason"] == "daily_cap"

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.coupons.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        loop.run_until_complete(db.offer_daily_counters.delete_many({"offer_id": oid}))
        client.close()


# ─── 7. Budget cap auto-pause ──────────────────────────────────────
def test_offer_auto_pauses_on_budget_cap_hit():
    loop = _new_loop()
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.offers import issue_coupon_for_offer, CapacityError
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    oid = f"ofr_test_bud_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID, "business_id": "biz_demo_karak",
            "title": "Budget", "offer_type": "flat", "discount_value": 10,
            "budget_cap_usd": 25, "status": "active", "issued_count": 0,
            "market": "dubai",
        })
        # discount * issued = 10 * 3 = 30 >= 25 → triggers on 3rd issuance
        await issue_coupon_for_offer(db, offer_id=oid, user_id="u1")
        await issue_coupon_for_offer(db, offer_id=oid, user_id="u2")
        # After issuing #3 → would be 30, which exceeds 25 — auto-paused post-issue,
        # so the 4th issuance fails with budget_cap_hit.
        await issue_coupon_for_offer(db, offer_id=oid, user_id="u3")
        try:
            await issue_coupon_for_offer(db, offer_id=oid, user_id="u4")
            assert False, "expected budget_cap_hit"
        except CapacityError as e:
            assert e.reason == "budget_cap_hit", e.reason
        o = await db.offers.find_one({"id": oid})
        assert o["status"] == "exhausted"
        assert o["auto_paused_reason"] == "budget_cap"

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.coupons.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        client.close()


# ─── 8. Resume endpoint idempotent ─────────────────────────────────
def test_offer_resume_endpoint_idempotent():
    owner = _owner()
    r = owner.post(f"/api/venue/{VENUE_ID}/offers",
                          json={"title": "Resume test", "offer_type": "percent",
                                  "discount_value": 5})
    oid = r.json()["offer"]["id"]
    # Pause first.
    owner.patch(f"/api/venue/{VENUE_ID}/offers/{oid}", json={"status": "paused"})
    # Resume twice — both 200, second is no-op.
    r1 = owner.post(f"/api/venue/{VENUE_ID}/offers/{oid}/resume")
    r2 = owner.post(f"/api/venue/{VENUE_ID}/offers/{oid}/resume")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["offer"]["status"] == "active"
    assert r2.json()["offer"]["status"] == "active"
    owner.delete(f"/api/venue/{VENUE_ID}/offers/{oid}")
    owner.close()


# ─── 9. Archived offer rejects new but preserves coupons ───────────
def test_archived_offer_does_not_issue_new_coupons_but_existing_ones_still_valid():
    loop = _new_loop()
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.offers import issue_coupon_for_offer, CapacityError
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    oid = f"ofr_test_arch_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID, "business_id": "biz_demo_karak",
            "title": "Arch", "offer_type": "percent", "discount_value": 10,
            "status": "active", "issued_count": 0, "market": "dubai",
        })
        c = await issue_coupon_for_offer(db, offer_id=oid, user_id="u_existing")
        # Soft-archive.
        await db.offers.update_one({"id": oid}, {"$set": {"status": "archived"}})
        # New issuance blocked.
        try:
            await issue_coupon_for_offer(db, offer_id=oid, user_id="u_new")
            assert False, "expected offer_paused"
        except CapacityError as e:
            assert e.reason == "offer_paused"
        # Existing coupon STILL present + still 'issued'.
        existing = await db.coupons.find_one({"coupon_id": c["coupon_id"]})
        assert existing and existing["status"] == "issued"

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.coupons.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))
        client.close()


# ─── 10. CSV template ──────────────────────────────────────────────
def test_csv_template_returns_correct_headers():
    r = httpx.get("http://localhost:8001/api/venue/offers/csv_template", timeout=10)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers.get("content-disposition", "")
    first_line = r.text.splitlines()[0]
    for col in ("title", "description", "offer_type", "discount_value",
                  "start_time", "end_time", "max_redemptions",
                  "redemption_method", "terms"):
        assert col in first_line, f"missing column {col}"
    # Two example rows + header.
    assert len(r.text.strip().splitlines()) == 3
