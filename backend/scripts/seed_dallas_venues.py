"""Seed a few demo Shop & Eat venues in Dallas / DFW so the Home venue
shelf shows local businesses for a Dallas-detected listener. Idempotent."""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

NOW = datetime.now(timezone.utc)
PROMO_UNTIL = (NOW + timedelta(days=14)).isoformat()

VENUES = [
    ("biz_dfw_smokeoak", "Smoke & Oak BBQ", "restaurant", "Barbecue", 4.8, 300, True,
     "https://images.unsplash.com/photo-1545345540-ea5d968030af?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
     "Slow-smoked brisket, ribs & burnt ends — pickup ready in 20."),
    ("biz_dfw_bishop_coffee", "Bishop Arts Coffee", "restaurant", "Cafe", 4.7, 180, True,
     "https://images.unsplash.com/photo-1651449815972-25b31a86af52?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
     "Single-origin pour-overs and fresh pastries in Bishop Arts."),
    ("biz_dfw_lonestar_hair", "Lone Star Hair Lab", "beauty", "Salon", 4.6, 200, False,
     "https://images.unsplash.com/photo-1600948836101-f9ffda59d250?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
     "Cuts, color & blowouts from Dallas' top stylists."),
    ("biz_dfw_pulse_fit", "Pulse DFW Fitness", "fitness", "Gym", 4.5, 150, False,
     "https://images.unsplash.com/photo-1637430308606-86576d8fef3c?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
     "Strength floor, classes and recovery — first class free."),
    ("biz_dfw_trinity_threads", "Trinity Threads", "retail", "Streetwear", 4.4, 120, False,
     "https://images.unsplash.com/photo-1625698311031-f0dd15be5144?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
     "Curated streetwear and local designer drops in Deep Ellum."),
]


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    for bid, name, cat, sub, rating, pts, sponsored, cover, desc in VENUES:
        doc = {
            "business_id": bid, "owner_user_id": "system_demo",
            "business_type": cat, "legal_name": f"{name} LLC",
            "public_name": name, "description": desc, "category": cat,
            "subcategory": sub, "logo_url": None, "cover_urls": [cover],
            "locations": [{"city": "Dallas", "address": "Dallas, TX"}],
            "sells": ["menu"] if cat == "restaurant" else ["products"],
            "bigpoints": {"mode": "default", "default_points": pts,
                          "points_per_dollar": 3.0, "product_overrides": {},
                          "service_overrides": {}},
            "market": "dfw", "commission_agreed": True,
            "rating": rating, "featured": sponsored, "sponsored": sponsored,
            "status": "approved", "approved_at": NOW, "created_at": NOW,
            "updated_at": NOW, "subscription_active": True,
            "shop_plan": "starter", "shop_plan_status": "active",
            "geo": {"lat": 32.7767, "lng": -96.7970, "address": "Dallas, TX"},
            "tax_jurisdiction": {"country": "US", "state": "TX", "city": "Dallas"},
        }
        if sponsored:
            doc["promoted_until"] = PROMO_UNTIL
            doc["promotion_tier"] = "boost_14"
            doc["promotion_weight"] = 2
        r = await db.marketplace_profiles.update_one(
            {"business_id": bid}, {"$set": doc}, upsert=True)
        print(f"{bid}: upserted={r.upserted_id is not None} modified={r.modified_count}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
