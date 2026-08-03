"""Phase G1 — Backfill `market` + `country` on existing offers.

This is a one-time metadata fix (NOT new seed data) — it tags every
existing offer with the implicit market its business represents so the
new `/api/offers/nearby` endpoint can filter by market without
returning Dubai-themed content to non-Dubai users.

Heuristic (in priority order):
    1. Offer already has `market` set     → leave alone.
    2. Lookup parent venue / venue_org      → use its `market`.
    3. Heuristic on `business_id` string  → contains "karak" / "demo_"
        / "dxb" → `dubai`; otherwise leave NULL (so it falls out of
        market-scoped queries until properly tagged).
    4. Tag `country` from the `MARKET_COUNTRY` map alongside `market`
        when a market is set.

Idempotent: re-running it is a no-op for rows already tagged.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

MARKET_COUNTRY = {
    "dubai":        "AE",
    "new_york":     "US",
    "london":       "GB",
    "mumbai":       "IN",
    "los_angeles":  "US",
    "dfw":           "US",
}

DUBAI_HINTS = re.compile(
    r"(karak|demo_|dxb|dubai|attr_test)", re.IGNORECASE)


async def main() -> None:
    client = AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "bigfm")]

    stats = {"total": 0, "already_tagged": 0,
                  "tagged_from_venue": 0, "tagged_from_heuristic": 0,
                  "untagged": 0}
    now = datetime.now(timezone.utc)

    async for o in db.offers.find({}):
        stats["total"] += 1
        if o.get("market"):
            stats["already_tagged"] += 1
            continue

        market = None
        country = None

        # Try venue lookup (works when offer.venue_id is set).
        if o.get("venue_id"):
            v = await db.venues.find_one({"id": o["venue_id"]})
            if v and v.get("market"):
                market = v["market"]
                country = (MARKET_COUNTRY.get(market) or
                                  (v.get("country") or "").upper() or None)

        # Heuristic on business_id (Dubai-themed brand names).
        if not market and o.get("business_id"):
            if DUBAI_HINTS.search(o["business_id"]):
                market = "dubai"
                country = MARKET_COUNTRY[market]

        if market:
            update = {"market": market, "updated_at": now}
            if country:
                update["country"] = country
            await db.offers.update_one(
                {"_id": o["_id"]}, {"$set": update})
            if o.get("venue_id"):
                stats["tagged_from_venue"] += 1
            else:
                stats["tagged_from_heuristic"] += 1
        else:
            stats["untagged"] += 1

    # Add a regular index for the new market field — supports the
    # /api/offers/nearby filter without a collection scan.
    try:
        await db.offers.create_index([("status", 1), ("market", 1)])
        await db.offers.create_index([("status", 1), ("country", 1)])
    except Exception as e:
        print(f"index already present: {e}", file=sys.stderr)

    print(f"offers backfill: {stats}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
