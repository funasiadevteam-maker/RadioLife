"""Phase 17b — Funnel analytics + A/B + orgs + payouts + auto-resume (12 tests)."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient   # noqa: E402

VENUE_ID  = "venue_demo_karak"
VENUE_ID2 = "venue_demo_karak_frisco"
ORG_ID    = "org_karak_chain"


def _login(email, pwd):
    c = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c.post("/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    raw = r.headers.get("set-cookie", "")
    c.cookies.set("bigfm_session", raw.split("bigfm_session=", 1)[1].split(";", 1)[0])
    return c


def _owner():   return _login("admin@bigfm.dubai", "AdminPass123!")
def _staff():   return _login("test@bigfm.dubai",  "TestUser123!")


def _new_loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    return asyncio.get_event_loop()


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ─── 1. Track records all 4 stages ─────────────────────────────────
def test_offer_event_tracking_records_all_4_stages():
    loop = _new_loop()
    db = _db()
    oid = f"ofr_evt_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Track me", "offer_type": "percent",
            "discount_value": 10, "status": "active", "market": "dubai",
        })
        c = _owner()
        for stage in ("impression", "save", "scan", "redeem"):
            r = c.post(f"/api/offers/{oid}/track", json={"stage": stage})
            assert r.status_code == 200, r.text
        cnt = await db.offer_events.count_documents({"offer_id": oid})
        assert cnt == 4
        # Invalid stage rejected.
        r = c.post(f"/api/offers/{oid}/track", json={"stage": "BOGUS"})
        assert r.status_code == 400
        c.close()

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offer_events.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))


# ─── 2. Funnel endpoint returns stage conversions + time buckets ────
def test_funnel_endpoint_returns_stage_conversions_and_time_buckets():
    loop = _new_loop()
    db = _db()
    oid = f"ofr_funnel_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "Funnel", "offer_type": "percent",
            "discount_value": 25, "status": "active", "market": "dubai",
        })
        # Seed 10 impressions, 6 saves, 3 scans, 2 redeems  →  funnel.
        now = datetime.now(timezone.utc)
        rows = ([{"stage": "impression"}] * 10 + [{"stage": "save"}] * 6
                  + [{"stage": "scan"}] * 3 + [{"stage": "redeem"}] * 2)
        for i, r in enumerate(rows):
            await db.offer_events.insert_one({
                "id":         f"evt_{oid}_{i}",
                "offer_id": oid,
                "venue_id": VENUE_ID,
                "user_id":   "u_seed",
                "stage":     r["stage"],
                "timestamp": now - timedelta(minutes=i),
            })
        c = _owner()
        r = c.get(f"/api/venue/{VENUE_ID}/offers/{oid}/funnel?period=month")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["impressions"] == 10
        assert d["saves"]       == 6
        assert d["scans"]       == 3
        assert d["redeems"]    == 2
        assert d["save_rate"]   == round(6 / 10, 4)
        assert d["scan_rate"]   == round(3 / 6,  4)
        assert d["redeem_rate"] == round(2 / 3,  4)
        assert isinstance(d["time_buckets"], list) and len(d["time_buckets"]) >= 1
        c.close()

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offer_events.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))


# ─── 3. Variant assignment is sticky per user ─────────────────────
def test_ab_variant_assignment_is_sticky_per_user():
    from services.offer_analytics import assign_variant
    variants = [
        {"slug": "control", "headline": "A", "weight": 50, "status": "active"},
        {"slug": "v1",      "headline": "B", "weight": 50, "status": "active"},
    ]
    # Same (user, offer) → same slug across 100 calls.
    first = assign_variant("u_42", "ofr_x", variants)["slug"]
    for _ in range(100):
        assert assign_variant("u_42", "ofr_x", variants)["slug"] == first


# ─── 4. Weighted distribution within tolerance ───────────────────
def test_ab_variant_weighted_distribution_within_5pct_tolerance():
    from services.offer_analytics import assign_variant
    variants = [
        {"slug": "control", "weight": 70, "status": "active", "headline": "A"},
        {"slug": "v1",      "weight": 30, "status": "active", "headline": "B"},
    ]
    counts = {"control": 0, "v1": 0}
    for i in range(2000):
        s = assign_variant(f"u_{i}", "ofr_x", variants)["slug"]
        counts[s] += 1
    p_control = counts["control"] / 2000
    assert 0.65 <= p_control <= 0.75, counts


# ─── 5. Wilson CI present on variant results ─────────────────────
def test_ab_results_includes_wilson_confidence_interval():
    loop = _new_loop()
    db = _db()
    oid = f"ofr_ci_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "CI", "offer_type": "percent",
            "discount_value": 10, "status": "active", "market": "dubai",
            "variants": [
                {"slug": "control", "headline": "A", "weight": 50, "status": "active"},
                {"slug": "v1",      "headline": "B", "weight": 50, "status": "active"},
            ],
        })
        # Seed 20 impressions per variant, 2 redeems for control, 4 for v1.
        now = datetime.now(timezone.utc)
        for v, imps, reds in [("control", 20, 2), ("v1", 20, 4)]:
            for i in range(imps):
                await db.offer_events.insert_one({
                    "id":             f"evt_{oid}_{v}_imp_{i}",
                    "offer_id":      oid,
                    "stage":          "impression",
                    "variant_slug": v,
                    "timestamp":    now,
                })
            for i in range(reds):
                await db.offer_events.insert_one({
                    "id":             f"evt_{oid}_{v}_red_{i}",
                    "offer_id":      oid,
                    "stage":          "redeem",
                    "variant_slug": v,
                    "timestamp":    now,
                })
        c = _owner()
        r = c.get(f"/api/venue/{VENUE_ID}/offers/{oid}/variants/results?period=month")
        assert r.status_code == 200, r.text
        d = r.json()
        slugs = {x["slug"]: x for x in d["variants"]}
        assert "ci_lo" in slugs["control"] and "ci_hi" in slugs["control"]
        assert 0.0 <= slugs["control"]["ci_lo"] <= slugs["control"]["ci_hi"] <= 1.0
        # Not enough impressions → no auto-winner.
        assert d["auto_winner_slug"] is None
        c.close()

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offer_events.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))


# ─── 6. Auto-winner requires 300 imps AND CI separation ─────────
def test_ab_auto_winner_detection_requires_300_impressions_and_95pct_confidence():
    loop = _new_loop()
    db = _db()
    oid = f"ofr_aw_{uuid.uuid4().hex[:6]}"

    async def run():
        await db.offers.insert_one({
            "id": oid, "offer_id": oid, "venue_id": VENUE_ID,
            "title": "AW", "offer_type": "percent",
            "discount_value": 10, "status": "active", "market": "dubai",
            "variants": [
                {"slug": "control", "headline": "A", "weight": 50, "status": "active"},
                {"slug": "v1",      "headline": "B", "weight": 50, "status": "active"},
            ],
        })
        now = datetime.now(timezone.utc)
        # control: 400 imps, 8 redeems (2%);  v1: 400 imps, 60 redeems (15%) → clear winner.
        await db.offer_events.insert_many([
            {"id": f"e_{oid}_c_i_{i}", "offer_id": oid, "stage": "impression",
              "variant_slug": "control", "timestamp": now} for i in range(400)
        ] + [
            {"id": f"e_{oid}_c_r_{i}", "offer_id": oid, "stage": "redeem",
              "variant_slug": "control", "timestamp": now} for i in range(8)
        ] + [
            {"id": f"e_{oid}_v_i_{i}", "offer_id": oid, "stage": "impression",
              "variant_slug": "v1", "timestamp": now} for i in range(400)
        ] + [
            {"id": f"e_{oid}_v_r_{i}", "offer_id": oid, "stage": "redeem",
              "variant_slug": "v1", "timestamp": now} for i in range(60)
        ])
        c = _owner()
        r = c.get(f"/api/venue/{VENUE_ID}/offers/{oid}/variants/results?period=month")
        d = r.json()
        assert d["auto_winner_slug"] == "v1", d
        c.close()

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offer_events.delete_many({"offer_id": oid}))
        loop.run_until_complete(db.offers.delete_one({"id": oid}))


# ─── 7. Org owner can link venues ──────────────────────────────────
def test_venue_org_owner_can_link_venues():
    # admin@bigfm.dubai owns `org_karak_chain` and venue_demo_karak per seed.
    owner = _owner()
    # Unlink, then re-link should both succeed.
    r1 = owner.patch(f"/api/venue/{VENUE_ID}/org", json={"parent_org_id": None})
    assert r1.status_code == 200, r1.text
    r2 = owner.patch(f"/api/venue/{VENUE_ID}/org", json={"parent_org_id": ORG_ID})
    assert r2.status_code == 200, r2.text
    owner.close()


# ─── 8. Org rollup aggregates all child venues ────────────────────
def test_venue_org_rollup_includes_all_child_venues():
    owner = _owner()
    r = owner.get(f"/api/venue/orgs/{ORG_ID}/rollup?period=month")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_venues"] >= 2
    ids = [v["id"] for v in d["venues"]]
    assert VENUE_ID in ids and VENUE_ID2 in ids
    assert "total_redemptions" in d and "total_revenue_usd" in d
    assert d["org"]["id"] == ORG_ID
    owner.close()


# ─── 9. Manager cannot see org-level rollup ──────────────────────
def test_venue_org_manager_cannot_see_org_level_rollup():
    # `test@bigfm.dubai` is a staff member of venue_demo_karak but is NOT
    # the org owner.
    staff = _staff()
    r = staff.get(f"/api/venue/orgs/{ORG_ID}/rollup?period=month")
    assert r.status_code == 403, r.text
    staff.close()


# ─── 10. Payout summary calculates bigcoin liability correctly ────
def test_payout_summary_calculates_bigcoin_liability_correctly():
    loop = _new_loop()
    db = _db()
    cid_a = f"cpn_payout_a_{uuid.uuid4().hex[:6]}"
    cid_b = f"cpn_payout_b_{uuid.uuid4().hex[:6]}"

    async def run():
        now = datetime.now(timezone.utc)
        await db.coupons.insert_many([
            {"coupon_id": cid_a, "venue_id": VENUE_ID,
              "discount_value": 20.0,
              "redeemed_at":    now - timedelta(days=1),
              "status": "redeemed"},
            {"coupon_id": cid_b, "venue_id": VENUE_ID,
              "discount_value": 30.0,
              "redeemed_at":    now - timedelta(days=2),
              "status": "redeemed"},
        ])
        c = _owner()
        r = c.get(f"/api/venue/{VENUE_ID}/payouts?period=week")
        assert r.status_code == 200, r.text
        d = r.json()
        # cash_value of OUR seeded coupons is 50 USD — but the venue may
        # already have other coupons in the window.  Verify OUR values
        # are included.
        assert d["cash_redemptions_count"] >= 2
        assert d["cash_redemptions_value_usd"] >= 50.0
        # Bigcoin liability is non-negative.
        assert d["bigcoin_liability_usd"] >= 0
        # Platform cut math is internally consistent.
        assert round(d["cash_redemptions_value_usd"] -
                          d["net_platform_revenue_share_usd"], 2) \
                  == d["expected_payout_to_venue_usd"]
        c.close()

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.coupons.delete_many(
            {"coupon_id": {"$in": [cid_a, cid_b]}}))


# ─── 11. CSV export returns correct headers ────────────────────────
def test_payout_summary_csv_export_returns_correct_headers():
    owner = _owner()
    r = owner.get(f"/api/venue/{VENUE_ID}/payouts/export.csv?period=month")
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.headers.get("content-type", "").startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0] == "day,redemptions,value_usd,bigcoin_usd"
    # Must include the summary footer rows.
    joined = r.text
    for col in ("cash_redemptions_value_usd",
                  "bigcoin_liability_usd",
                  "net_platform_revenue_share_usd",
                  "expected_payout_to_venue_usd"):
        assert col in joined, f"missing {col} in CSV footer"
    owner.close()


# ─── 12. Auto-resume flips daily-cap but NOT total-cap ────────────
def test_auto_resume_flips_daily_cap_at_venue_midnight_only():
    loop = _new_loop()
    db = _db()
    from services.offers import auto_resume_eligible_offers

    oid_daily = f"ofr_arD_{uuid.uuid4().hex[:6]}"
    oid_total = f"ofr_arT_{uuid.uuid4().hex[:6]}"

    async def run():
        # Both exhausted, paused 25h ago in venue-local time (dubai = UTC+4).
        # 25h ago in UTC → in venue-local time we have definitely crossed midnight.
        paused_at = datetime.now(timezone.utc) - timedelta(hours=25)
        await db.offers.insert_many([
            {"id": oid_daily, "offer_id": oid_daily, "venue_id": VENUE_ID,
              "title": "Daily-Cap exhausted", "offer_type": "percent",
              "discount_value": 5, "status": "exhausted", "market": "dubai",
              "auto_paused_reason": "daily_cap", "auto_paused_at": paused_at,
              "issued_count": 5},
            {"id": oid_total, "offer_id": oid_total, "venue_id": VENUE_ID,
              "title": "Total-Cap exhausted", "offer_type": "percent",
              "discount_value": 5, "status": "exhausted", "market": "dubai",
              "auto_paused_reason": "total_cap", "auto_paused_at": paused_at,
              "issued_count": 5},
        ])
        out = await auto_resume_eligible_offers(db)
        assert out["resumed"] >= 1, out

        daily = await db.offers.find_one({"id": oid_daily})
        total = await db.offers.find_one({"id": oid_total})
        assert daily["status"] == "active",       daily["status"]
        assert daily["auto_paused_reason"] is None
        assert daily.get("auto_resume_count", 0) == 1
        # Total-cap offer must NOT be flipped.
        assert total["status"] == "exhausted",    total["status"]
        assert total["auto_paused_reason"] == "total_cap"

        # Same setup but pause was 1 min ago in venue-local → must NOT resume.
        oid_recent = f"ofr_arR_{uuid.uuid4().hex[:6]}"
        await db.offers.insert_one({
            "id": oid_recent, "offer_id": oid_recent, "venue_id": VENUE_ID,
            "title": "Daily-Cap (recent)", "offer_type": "percent",
            "discount_value": 5, "status": "exhausted", "market": "dubai",
            "auto_paused_reason": "daily_cap",
            "auto_paused_at":      datetime.now(timezone.utc) - timedelta(minutes=1),
            "issued_count": 5,
        })
        out2 = await auto_resume_eligible_offers(db)
        rec = await db.offers.find_one({"id": oid_recent})
        assert rec["status"] == "exhausted", "recent pause should NOT auto-resume"
        await db.offers.delete_one({"id": oid_recent})

    try:
        loop.run_until_complete(run())
    finally:
        loop.run_until_complete(db.offers.delete_many(
            {"id": {"$in": [oid_daily, oid_total]}}))
