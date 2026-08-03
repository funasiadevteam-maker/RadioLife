"""Phase 18d.1 — Programmatic Auction Log panel — backend regression.

Seeds 25 synthetic log entries (split across `ad_impressions` +
`openrtb_auctions`), hits `GET /api/admin/ads/auction-log/recent`,
asserts exactly 20 items are returned newest-first, the merge across
both streams works, and the expected enriched fields are populated.
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _seed_25(db, run_tag: str):
    """15 ad_impressions + 10 openrtb_auctions, ordered timestamps."""
    base = datetime.now(timezone.utc) - timedelta(minutes=120)
    creative_id = f"crt_alog_{run_tag}"
    pod_ids = []
    campaign_id = f"cmp_alog_{run_tag}"
    advertiser_id = f"adv_alog_{run_tag}"
    await db.ad_creatives.insert_one({
        "id": creative_id, "status": "approved",
        "title": "Test Creative ALOG",
        "advertiser_id": advertiser_id})
    await db.campaigns.insert_one({
        "campaign_id": campaign_id, "name": "Test Campaign ALOG",
        "advertiser_id": advertiser_id})
    await db.advertisers.insert_one({
        "advertiser_id": advertiser_id, "company_name": "ALOG Co"})
    impressions = []
    for i in range(15):
        pid = f"pod_alog_{run_tag}_{i}"
        pod_ids.append(pid)
        await db.ad_pods.insert_one(
            {"_id": pid, "decision_path": "direct_sold", "bid_cents": 100 + i})
        impressions.append({
            "_id":                            f"imp_{run_tag}_{i}",
            "ad_pod_id":               pid,
            "ad_creative_id":         creative_id,
            "campaign_id":             campaign_id,
            "user_id":                       f"u_{i}",
            "session_id":                f"s_{run_tag}_{i}",
            "served_at":                  base + timedelta(minutes=i),
            "attributed_revenue_cents": 100 + i,
            "market":                       "dubai",
            "channel_slug":           "bollywood_mehfil",
            "completion_pct":          0.0,
        })
    await db.ad_impressions.insert_many(impressions)
    auctions = []
    for i in range(10):
        auctions.append({
            "_id":                                  f"au_{run_tag}_{i}",
            "bidrequest_id":              f"br_{run_tag}_{i}",
            "user_id":                            f"u_{i}",
            "session_id":                     f"s_{run_tag}_au_{i}",
            "winner_partner":            "mock_ssp",
            "winner_price_cents":      200 + i,
            "clearing_price_cents":  150 + i,
            "ran_at":                            base + timedelta(minutes=20 + i),
            "all_bids":                        [{"partner": "mock_ssp",
                                                                "price_cents": 200 + i}],
        })
    await db.openrtb_auctions.insert_many(auctions)
    return {"creative_id": creative_id, "campaign_id": campaign_id,
                  "advertiser_id": advertiser_id, "pod_ids": pod_ids}


async def _cleanup(db, seeded, run_tag: str):
    await db.ad_impressions.delete_many(
        {"_id": {"$regex": f"^imp_{run_tag}_"}})
    await db.openrtb_auctions.delete_many(
        {"_id": {"$regex": f"^au_{run_tag}_"}})
    await db.ad_pods.delete_many({"_id": {"$in": seeded["pod_ids"]}})
    await db.ad_creatives.delete_one({"id": seeded["creative_id"]})
    await db.campaigns.delete_one({"campaign_id": seeded["campaign_id"]})
    await db.advertisers.delete_one({"advertiser_id": seeded["advertiser_id"]})


@pytest.mark.asyncio
async def test_auction_log_recent_returns_20_sorted_with_enriched_fields():
    from server import app
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]
    run_tag = uuid.uuid4().hex[:8]
    seeded = await _seed_25(db, run_tag)
    try:
        # Authenticate as the seeded admin.
        async with AsyncClient(transport=ASGITransport(app=app),
                                              base_url="http://test") as ac:
            login = await ac.post("/api/auth/login", json={
                "email": "admin@bigfm.dubai", "password": "AdminPass123!"})
            assert login.status_code == 200, login.text
            tok = login.json().get("session_token")
            r = await ac.get(
                "/api/admin/ads/auction-log/recent?limit=20&window_seconds=86400",
                headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 200, r.text
            body = r.json()
        items = body["items"]
        assert len(items) == 20, f"expected 20 items, got {len(items)}"
        # Verify newest-first sort order.
        timestamps = [it["timestamp"] for it in items]
        assert timestamps == sorted(timestamps, reverse=True), \
                  "items must be sorted newest-first"
        # Window-total must include at least our 25 + whatever else lives there.
        assert body["total_in_window"] >= 25
        # Find at least one openrtb row and one impression row.
        openrtb_rows = [i for i in items if i["source"] == "openrtb"]
        direct_rows   = [i for i in items if i["source"] == "direct"]
        assert len(openrtb_rows) > 0, "merge should include openrtb rows"
        assert len(direct_rows)   > 0, "merge should include impression rows"
        # Enriched fields on at least one impression row from our seed:
        my_imp = next((i for i in direct_rows
                                      if i.get("creative_id") == seeded["creative_id"]), None)
        assert my_imp is not None
        assert my_imp["campaign_name"]      == "Test Campaign ALOG"
        assert my_imp["advertiser_id"]         == seeded["advertiser_id"]
        assert my_imp["clear_price_cents"] >= 100
        assert my_imp["bid_price_cents"]      >= 100
        assert my_imp["user_session_hash"], "session_id must be hashed"
        # Openrtb row should carry the synthetic reason.
        if openrtb_rows:
            assert openrtb_rows[0].get("source") == "openrtb"
            assert openrtb_rows[0].get("clear_price_cents") is not None
            assert openrtb_rows[0].get("bid_price_cents") is not None
    finally:
        await _cleanup(db, seeded, run_tag)
