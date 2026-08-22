"""Attach AI-generated branded clip covers to active advertiser campaigns.
Idempotent — safe to re-run."""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

CLIP_ART = {
    "cmp_dr_mehta_appt": "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/cdfd5d05da0ce75a4a3a0e6cc6797db71e74e1677bc39364bc7b6569f5dc7fcf.jpeg",
    "cmp_funasia_premiere": "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/202e585d94461fe31352a6ed92331683c2e95d863306548c6b1baad0b384f48b.jpeg",
    "cmp_indo_marina_lunch": "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/d671213ffff2f0b327f3c90487c611ce338ae0866e0bb0478ad480e00f28a649.jpeg",
    "cmp_karak_20off": "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/7f224ef4b894318dc1f1a623a80241c04f5f048bd335c02efb3acd149917007e.jpeg",
    "cmp_salam_grocery": "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/978fe6056366369a7564bc97e885b4eff94a9693a6de6ef432339815dacc1eaa.jpeg",
}


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    for cid, url in CLIP_ART.items():
        r = await db.campaigns.update_one(
            {"campaign_id": cid}, {"$set": {"clip_image_url": url}})
        print(f"{cid}: matched={r.matched_count} modified={r.modified_count}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
