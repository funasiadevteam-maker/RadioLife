"""Phase SC.2 — seed the 16 canonical business categories.

Idempotent — safe to re-run.  The `business_categories` collection is
read by the merchant-onboarding wizard step-1 category grid and by
`/api/admin/merchants` filters.

Fields per category:
    id                   — stable string id (used by wizard + queries)
    name              — display label
    slug              — url-safe identifier
    icon_hint      — lucide-react icon name (frontend renders it)
    sort_order  — 1-based sort key
    active          — allow/hide in the wizard grid
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient


CATEGORIES = [
    ("restaurant",              "Restaurant",              "Utensils",     1),
    ("cafe",                        "Café",                          "Coffee",         2),
    ("grocery",                  "Grocery",                    "ShoppingBasket", 3),
    ("retail",                      "Retail",                        "Store",             4),
    ("salon_spa",              "Salon & Spa",              "Scissors",     5),
    ("medical_dental",      "Medical & Dental",      "Stethoscope", 6),
    ("fitness",                    "Fitness",                    "Dumbbell",     7),
    ("entertainment",        "Entertainment",        "PartyPopper", 8),
    ("movie_theater",        "Movie Theater",        "Film",             9),
    ("event_promoter",    "Event Promoter",      "CalendarDays",10),
    ("concert_promoter","Concert Promoter",  "Music",         11),
    ("club_lounge",          "Club & Lounge",        "Martini",       12),
    ("radio_station",        "Radio Station",        "Radio",         13),
    ("podcast_creator",  "Podcast Creator",    "Mic",              14),
    ("service_business", "Service Business",  "Wrench",       15),
    ("other",                      "Other",                        "Sparkles",     16),
]


async def seed(db) -> dict:
    inserted = 0
    updated  = 0
    now = datetime.now(timezone.utc)
    for cid, name, icon, order in CATEGORIES:
        slug = cid.replace("_", "-")
        doc = {
            "id":              cid,
            "name":          name,
            "slug":          slug,
            "icon_hint":  icon,
            "sort_order": order,
            "active":      True,
            "updated_at": now,
        }
        existing = await db.business_categories.find_one({"id": cid})
        if existing:
            await db.business_categories.update_one(
                {"id": cid}, {"$set": doc})
            updated += 1
        else:
            doc["created_at"] = now
            await db.business_categories.insert_one({**doc, "_id": cid})
            inserted += 1
    # Index for fast lookups + sort
    try:
        await db.business_categories.create_index("id", unique=True)
        await db.business_categories.create_index([("sort_order", 1)])
    except Exception:
        pass
    return {"inserted": inserted, "updated": updated,
              "total": len(CATEGORIES)}


async def _main() -> None:
    url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    dbn = os.environ.get("DB_NAME") or "bigfm"
    client = AsyncIOMotorClient(url)
    db = client[dbn]
    result = await seed(db)
    print(f"[seed_business_categories] {result}")


if __name__ == "__main__":
    asyncio.run(_main())
