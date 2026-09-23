"""One-off cleanup: remove BROKEN banner creatives from the active rotation.

Two classes of bad data were surfacing as blank "SPONSORED" boxes:
  1. `portal_self_serve` banners for the demo merchant (biz_8484f6f985d5)
     whose uploaded creative is a 1x1 / 69-byte placeholder PNG.
  2. Campaigns pointing at `/static/banners/samples/biz_placeholder.jpg`,
     which does not exist on disk (404 -> blank box).

Fix: give the demo merchant a real generated creative, and pause the
phantom placeholder campaigns so they leave rotation.
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

# Reuse the sample-banner renderer.
from scripts.seed_sample_banners import render_banner, BUCKET, STATIC_DIR, _slug  # noqa: E402

DEMO_BIZ = "biz_8484f6f985d5"


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # 1) Repoint the demo merchant's broken 1x1 portal banners to a real creative.
    biz = await db.businesses.find_one({"business_id": DEMO_BIZ})
    if biz:
        name = (biz.get("name") or "Featured Business").strip()
        cat = (biz.get("category") or "").strip().lower()
        city = (biz.get("city") or "").strip()
        bucket = BUCKET.get(cat, "retail")
        png = render_banner(name, bucket, city)
        fname = f"{DEMO_BIZ}.jpg"
        (STATIC_DIR / fname).write_bytes(png)
        url = f"/api/static/banners/samples/{fname}"
        try:
            from services.object_storage import get_storage
            get_storage().upload_bytes(key=f"static/banners/samples/{fname}",
                                       data=png, content_type="image/jpeg")
        except Exception:
            pass
        r = await db.banner_ad_campaigns.update_many(
            {"business_id": DEMO_BIZ, "source": "portal_self_serve"},
            {"$set": {"creative_image_url": url, "updated_at": now}})
        print(f"repointed {r.modified_count} portal banners for {name} -> {url}")
    else:
        print(f"WARN: business {DEMO_BIZ} not found")

    # 2) Pause any active campaign whose creative file is the missing placeholder.
    r2 = await db.banner_ad_campaigns.update_many(
        {"status": "active",
         "creative_image_url": {"$regex": "biz_placeholder"}},
        {"$set": {"status": "paused", "paused_reason": "missing_creative",
                  "updated_at": now}})
    print(f"paused {r2.modified_count} phantom placeholder campaigns")

    # Report remaining active portal/placeholder health.
    bad = await db.banner_ad_campaigns.count_documents(
        {"status": "active", "creative_image_url": {"$regex": "biz_placeholder"}})
    print(f"remaining active biz_placeholder campaigns: {bad}")


if __name__ == "__main__":
    asyncio.run(main())
