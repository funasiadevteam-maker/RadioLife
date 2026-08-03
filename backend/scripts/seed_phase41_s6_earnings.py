"""Phase 41 Session 6.A — synthetic earnings ledger seed.

Idempotent — safe to re-run. Populates `creator_earnings_ledger`,
`payout_requests`, and sets a `stripe_connect_status` flag on the
test owner user, so the Earnings dashboard isn't empty during
screenshots / demos.

Usage:
    cd /app/backend && python -m scripts.seed_phase41_s6_earnings
"""
from __future__ import annotations
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient


STATIONS = ["s3a-smoke-karak", "p41-audit-test"]
SEED_TAG = "phase41_s6_seed_v1"

# Per-source weights for the seed. Higher = more rows of that type.
WEIGHTS_BUSINESS = {
    "banner_impression":   45,
    "audio_ad_completion": 18,
    "premium_listen":      15,
    "tip":                 8,
    "direct_deal":         4,
}
WEIGHTS_PERSONAL = {
    "banner_impression":   25,
    "audio_ad_completion": 22,
    "premium_listen":      30,
    "tip":                 18,
    "direct_deal":         5,
}

# Realistic gross amount ranges in cents per source type.
GROSS_RANGES = {
    "banner_impression":   (1,      4),      # 0.01–0.04 USD per impression
    "audio_ad_completion": (50,     300),    # $0.50–$3.00 per completion
    "premium_listen":      (2,      15),     # $0.02–$0.15 per session
    "tip":                 (300,    5000),   # $3–$50 tips
    "direct_deal":         (10_000, 100_000), # $100–$1000 off-platform
}


async def seed():
    rand = random.Random(20260608)
    db = AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    )[os.environ.get("DB_NAME", "bigfm")]

    rsx = await db.creator_earnings_ledger.delete_many({
        "attribution_metadata.seed_tag": SEED_TAG})
    rsy = await db.payout_requests.delete_many({
        "seed_tag": SEED_TAG})
    print(f"[seed] wiped prior ledger={rsx.deleted_count} "
          f"payouts={rsy.deleted_count}")

    stations: list = []
    for slug in STATIONS:
        s = await db.community_radio_stations.find_one({"slug": slug})
        if not s:
            print(f"[seed] WARN station {slug} missing, skipping")
            continue
        stations.append(s)
    if not stations:
        print("[seed] no stations available")
        return

    share_pct = int(os.environ.get("CREATOR_REV_SHARE_PCT", "70"))

    def _split(gross: int) -> tuple[int, int]:
        creator = (gross * share_pct) // 100
        return creator, gross - creator

    now = datetime.now(timezone.utc)
    insert_rows: list = []
    for s in stations:
        slug = s["slug"]
        owner = s.get("owner_user_id")
        is_biz = (s.get("page_type") == "business_radio"
                    or s.get("is_business"))
        weights = WEIGHTS_BUSINESS if is_biz else WEIGHTS_PERSONAL
        for src, n in weights.items():
            low, high = GROSS_RANGES[src]
            for _ in range(n):
                days_ago = rand.randint(0, 29)
                occurred = (now - timedelta(
                    days=days_ago,
                    hours=rand.randint(0, 23),
                    minutes=rand.randint(0, 59)))
                gross = rand.randint(low, high)
                creator, house = _split(gross)
                source_ref = f"seed_{src}_{uuid.uuid4().hex[:14]}"
                # Mark a few as paid_out to test the lifecycle UI.
                status = "recorded"
                if days_ago > 21 and rand.random() < 0.3:
                    status = "paid_out"
                insert_rows.append({
                    "_id":                 source_ref,
                    "source_ref":          source_ref,
                    "station_id":          s.get("station_id"),
                    "station_slug":        slug,
                    "owner_user_id":       owner,
                    "source_type":         src,
                    "gross_amount_cents":  gross,
                    "creator_amount_cents": creator,
                    "house_cut_cents":     house,
                    "currency":            "USD",
                    "share_pct":           share_pct,
                    "occurred_at":         occurred,
                    "status":              status,
                    "payout_id":           None,
                    "attribution_metadata": {
                        "seed_tag":         SEED_TAG,
                        "mock":             "seeded by phase41_s6 script",
                    },
                    "created_at":          occurred,
                })

    if insert_rows:
        await db.creator_earnings_ledger.insert_many(insert_rows)
    print(f"[seed] inserted {len(insert_rows)} ledger rows "
          f"across {len(stations)} stations")

    # Activate Stripe Connect on the test owner so the "Request payout"
    # CTA is exercisable on the dashboard.
    owners = {s.get("owner_user_id") for s in stations
                if s.get("owner_user_id")}
    for uid in owners:
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {
                "stripe_connect_status":     "active",
                "stripe_connect_account_id": f"acct_MOCK_seed_{uid[-8:]}",
                "stripe_connect_updated_at": now.isoformat(),
            }})
        print(f"[seed] {uid}: stripe_connect_status -> active")

    print("[seed] DONE")


if __name__ == "__main__":
    asyncio.run(seed())
