"""Idempotent demo marketplace products (with photos + stock) on eligible
(approved + subscribed) businesses, so the Tube feed shows real product images
and the in-feed cart + checkout work end to end.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.marketplace import now  # noqa: E402

BURGER1 = "https://images.unsplash.com/photo-1610440042657-612c34d95e9f?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
BURGER2 = "https://images.unsplash.com/photo-1561758033-d89a9ad46330?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
COFFEE1 = "https://images.unsplash.com/photo-1671759545218-831c32bfe92d?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
COFFEE2 = "https://images.pexels.com/photos/35229818/pexels-photo-35229818.jpeg?auto=compress&cs=tinysrgb&w=800"
BIRYANI = "https://images.pexels.com/photos/9609869/pexels-photo-9609869.jpeg?auto=compress&cs=tinysrgb&w=800"
CURRY = "https://images.unsplash.com/photo-1589302168068-964664d93dc0?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
BEAUTY1 = "https://images.unsplash.com/photo-1597931752949-98c74b5b159f?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
BEAUTY2 = "https://images.pexels.com/photos/13573920/pexels-photo-13573920.jpeg?auto=compress&cs=tinysrgb&w=800"

CATALOG = {
    "biz_demo_grill": [
        ("Signature Angus Burger", 1200, "Food", BURGER1),
        ("Loaded Fries Combo", 750, "Food", BURGER2),
    ],
    "biz_demo_brew": [
        ("Iced Caramel Latte", 500, "Drinks", COFFEE1),
        ("Cold Brew + Croissant", 800, "Drinks", COFFEE2),
    ],
    "biz_demo_spice": [
        ("Chicken Biryani", 1000, "Food", BIRYANI),
        ("Butter Chicken Curry", 1100, "Food", CURRY),
    ],
    "biz_demo_glow": [
        ("Repair Shampoo & Conditioner", 2400, "Beauty", BEAUTY1),
        ("Signature Styling Kit", 3200, "Beauty", BEAUTY2),
    ],
}


async def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base, ".env"))
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for biz, prods in CATALOG.items():
        prof = await db.marketplace_profiles.find_one({"business_id": biz})
        if not prof:
            print("skip (no business):", biz)
            continue
        # make sure it's checkout-eligible
        await db.marketplace_profiles.update_one(
            {"business_id": biz},
            {"$set": {"status": "approved", "subscription_active": True}})
        for i, (name, cents, cat, img) in enumerate(prods):
            pid = f"prod_demo_{biz.split('_')[-1]}_{i}"
            doc = {"product_id": pid, "business_id": biz, "name": name,
                   "description": f"{name} — freshly prepared.", "category": cat,
                   "price_cents": cents, "currency": "usd", "stock": 500,
                   "variants": [], "option_groups": [], "image_url": img,
                   "active": True, "sort": i, "demo_seed": True, "updated_at": now()}
            await db.products.update_one(
                {"product_id": pid}, {"$set": doc, "$setOnInsert": {"created_at": now()}}, upsert=True)
        print("seeded", len(prods), "products on", biz, f"({prof.get('public_name')})")


if __name__ == "__main__":
    asyncio.run(main())
