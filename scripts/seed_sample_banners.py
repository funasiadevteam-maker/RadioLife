"""Idempotent seed: sample sponsored banner campaigns for real sample
businesses (Fun Pizza Kitchen + 4 others), served in the New-Look V2 right
rail (right_rail_mpu_1/2/3) and a few general slots. Also retires the old
placeholder campaigns (example.com / picsum) that made the rail look empty.

Run:  cd /app/backend && python /app/scripts/seed_sample_banners.py
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

IMG = "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images"

# (business_id, name, category, city, description, banner_image, slot_keys)
SAMPLES = [
    ("biz_fun_pizza_kitchen", "Fun Pizza Kitchen", "Food & Dining", "Dubai",
     "Wood-fired pizzas, 2-for-1 every Tuesday.",
     f"{IMG}/e0d4fd8e4765a89effe061c31f1eddaa66d78362b2ae91d60bacc35a5d669f01.jpeg",
     ["right_rail_mpu_1", "top_billboard", "inline_mpu_1"]),
    ("biz_camel_beans_coffee", "Camel & Beans Coffee", "Food & Dining", "Dubai",
     "Specialty coffee roasters. 30% off your morning brew.",
     f"{IMG}/e454679ea22a66b210e9acbe720d2e714cc8304cb20d3a5d7d5deeef99e15349.jpeg",
     ["right_rail_mpu_2", "featured_horizontal"]),
    ("biz_iron_oasis_gym", "Iron Oasis Gym", "Fitness", "Dubai",
     "Strength & conditioning studio. First month free.",
     f"{IMG}/809bd51b907e06a3e106741e108b93464833f5c264e8734da048b9d7d4076bf5.jpeg",
     ["right_rail_mpu_3", "inline_mpu_2"]),
    ("biz_dune_spa_salon", "Dune Spa & Salon", "Beauty & Spa", "Dubai",
     "Luxury spa & salon. Pamper package AED 99.",
     f"{IMG}/bd5b0f9359ef30154c6d6d00046f5ef970bba5d42d651239982ad951a6d65bea.jpeg",
     ["mid_horizontal", "inline_square"]),
    ("biz_gadget_souk", "Gadget Souk", "Retail", "Dubai",
     "Consumer electronics superstore. Flash sale up to 50% off.",
     f"{IMG}/a2f219cc85b6bcef9aaf9db1501c4e06fc25a942b52123a73a98d23e98ee5bb2.jpeg",
     ["bottom_horizontal", "top_leaderboard"]),
]


def _iso(dt):
    return dt.isoformat()


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    start_iso = _iso(now - timedelta(days=1))
    end_iso = _iso(now + timedelta(days=180))

    # 1. Retire placeholder campaigns that made the rail look empty.
    r = await db.banner_ad_campaigns.update_many(
        {"status": "active",
         "$or": [{"click_url": {"$regex": "example.com"}},
                 {"creative_image_url": {"$regex": "picsum"}},
                 {"creative_image_url": {"$regex": "1540039155733"}}]},
        {"$set": {"status": "completed", "retired_by": "seed_sample_banners",
                  "retired_at": _iso(now)}})
    print(f"retired placeholder campaigns: {r.modified_count}")

    biz_seeded = camp_seeded = 0
    for bid, name, cat, city, desc, img, slots in SAMPLES:
        slug = bid.replace("biz_", "").replace("_", "-")
        # 2. Ensure the business exists (idempotent, minimal sample doc).
        existing = await db.businesses.find_one({"business_id": bid})
        if not existing:
            await db.businesses.insert_one({
                "_id": bid, "business_id": bid, "name": name, "category": cat,
                "city": city, "country_code": "AE", "description": desc,
                "logo_url": img, "hero_image_url": img, "slug": slug,
                "state": "", "status": "active", "is_sample": True,
                "loc": {"type": "Point", "coordinates": [55.2708, 25.2048]},
                "created_at": _iso(now), "updated_at": _iso(now)})
            biz_seeded += 1
        else:
            slug = existing.get("slug") or slug
            await db.businesses.update_one(
                {"business_id": bid},
                {"$set": {"logo_url": existing.get("logo_url") or img,
                          "updated_at": _iso(now)}})

        # 3. Upsert an active banner campaign (deterministic id → idempotent).
        cid = f"bcamp_sample_{bid.replace('biz_', '')}"
        await db.banner_ad_campaigns.update_one(
            {"_id": cid},
            {"$set": {
                "campaign_id": cid, "advertiser_id": "house_sample_ads",
                "business_id": bid, "advertiser_name": name,
                "slot_keys": slots, "creative_image_url": img,
                "click_url": f"/business/{slug}",
                "start_date": start_iso, "end_date": end_iso,
                "daily_budget": 50.0, "total_budget": 500.0,
                "status": "active", "targeting_json": {},
                "frequency_cap_per_user_per_day": 1000,
                "approved_at": _iso(now), "approved_by": "seed_sample_banners",
                "rejected_reason": None, "stripe_session_id": None,
                "is_sample": True, "updated_at": _iso(now)},
             "$setOnInsert": {"created_at": _iso(now)}},
            upsert=True)
        camp_seeded += 1
        print(f"  ✓ {name:24s} → slots {slots}")

    print(f"businesses created: {biz_seeded} | campaigns upserted: {camp_seeded}")
    total = await db.banner_ad_campaigns.count_documents({"status": "active"})
    print(f"active banner campaigns now: {total}")
    c.close()


if __name__ == "__main__":
    asyncio.run(main())
