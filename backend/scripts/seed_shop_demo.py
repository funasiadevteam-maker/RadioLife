"""Idempotent demo seed — make the new variant + option screens shine.
- Adds size variants to Ambreen's serum + inserts a variant apparel product.
- Adds option groups (Cook + Add-ons) to a Grill House main.
Run: python -m scripts.seed_shop_demo
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


def now():
    return datetime.now(timezone.utc)


def oid(pfx):
    return f"{pfx}_{uuid.uuid4().hex[:12]}"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    AMB = "biz_sample_ambreens"
    GRILL = "biz_demo_grill"

    # 1) Serum → size variants
    serum = await db.products.find_one({"business_id": AMB})
    if serum:
        await db.products.update_one({"product_id": serum["product_id"]}, {"$set": {
            "variants": [
                {"label": "30 ml", "price_cents": 3200, "stock": 20},
                {"label": "50 ml", "price_cents": 4800, "stock": 15},
                {"label": "100 ml", "price_cents": 7900, "stock": 8},
            ], "updated_at": now(),
        }})
        print("serum variants set:", serum["product_id"])

    # 2) Apparel product with size + colour variants (insert once)
    tee_id = "prod_demo_radiolife_tee"
    if not await db.products.find_one({"product_id": tee_id}):
        n = await db.products.count_documents({"business_id": AMB})
        await db.products.insert_one({
            "product_id": tee_id, "business_id": AMB, "sort": n,
            "name": "RadioLife Signature Tee",
            "description": "Soft 100% combed-cotton crew tee with the RadioLife mark. Unisex fit.",
            "category": "Apparel", "price_cents": 4500, "stock": 0, "bigpoints": 45,
            "image_url": "https://images.unsplash.com/photo-1581655353564-df123a1eb820?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
            "variants": [
                {"label": "S · Black", "price_cents": 4500, "stock": 12},
                {"label": "M · Black", "price_cents": 4500, "stock": 18},
                {"label": "L · Navy", "price_cents": 4500, "stock": 9},
                {"label": "XL · White", "price_cents": 4900, "stock": 6},
            ],
            "option_groups": [], "active": True,
            "created_at": now(), "updated_at": now(),
        })
        print("tee inserted:", tee_id)

    # 3) Grill main → option groups (Cook required + Add-ons multi)
    main_item = await db.menu_items.find_one({"business_id": GRILL, "section": {"$regex": "main", "$options": "i"}}) \
        or await db.menu_items.find_one({"business_id": GRILL})
    if main_item and not main_item.get("option_groups"):
        await db.menu_items.update_one({"item_id": main_item["item_id"]}, {"$set": {
            "option_groups": [
                {"group_id": oid("grp"), "name": "Cook", "type": "single", "required": True,
                 "min_select": 1, "max_select": 1, "options": [
                     {"option_id": oid("opt"), "label": "Medium rare", "price_delta_cents": 0, "is_default": True, "available": True},
                     {"option_id": oid("opt"), "label": "Medium", "price_delta_cents": 0, "available": True},
                     {"option_id": oid("opt"), "label": "Well done", "price_delta_cents": 0, "available": True},
                 ]},
                {"group_id": oid("grp"), "name": "Add-ons", "type": "multi", "required": False,
                 "min_select": 0, "max_select": 3, "options": [
                     {"option_id": oid("opt"), "label": "Extra cheese", "price_delta_cents": 250, "available": True},
                     {"option_id": oid("opt"), "label": "Smoked bacon", "price_delta_cents": 350, "available": True},
                     {"option_id": oid("opt"), "label": "Truffle fries", "price_delta_cents": 500, "available": True},
                 ]},
            ], "updated_at": now(),
        }})
        print("option groups set on menu item:", main_item["item_id"], main_item.get("name"))
    else:
        print("menu item options: skipped (none found or already set)")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
