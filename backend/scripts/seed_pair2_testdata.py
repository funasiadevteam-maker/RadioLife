"""One-off QA seed for Pair 2 (Sold-Out Waitlist + web PiP):
  1. Mark the FPK 'Spin & Save' game SOLD OUT for today so the storefront
     shows the "Remind me" affordance.
  2. Give one podcast episode a public sample video so the web podcast
     detail shows the "Watch → Picture-in-Picture" flow.
Prints the ids/URLs to point QA at.
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

SAMPLE_VIDEO = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1) Sold-out FPK game
    camp_id = "cmp_fpk_spin"
    prizes = await db.game_prizes.find(
        {"campaign_id": camp_id, "active": True, "prize_type": "coupon"}).to_list(50)
    n = 0
    for p in prizes:
        cap = int(p.get("daily_quantity_cap") or 0)
        if cap > 0:
            await db.game_prizes.update_one(
                {"_id": p["_id"]},
                {"$set": {"daily_issued": cap, "daily_issued_date": today}})
            n += 1
    print(f"SOLD-OUT: {camp_id} -> maxed {n} coupon tiers for {today}")

    # 1b) Almost-gone FPK game — leave a small remainder so the storefront
    #     flashes the "Only N left today!" urgency warning.
    ag_id = "cmp_fpk_scratch"
    ag_prizes = await db.game_prizes.find(
        {"campaign_id": ag_id, "active": True, "prize_type": "coupon"}).to_list(50)
    ag_prizes.sort(key=lambda p: int(p.get("daily_quantity_cap") or 0), reverse=True)
    left_total = 0
    for i, p in enumerate(ag_prizes):
        cap = int(p.get("daily_quantity_cap") or 0)
        if cap <= 0:
            continue
        # Leave 12 on the largest tier, exhaust the rest -> total ~12 remaining.
        issued = max(0, cap - 12) if i == 0 else cap
        await db.game_prizes.update_one(
            {"_id": p["_id"]},
            {"$set": {"daily_issued": issued, "daily_issued_date": today}})
        left_total += cap - issued
    print(f"ALMOST-GONE: {ag_id} -> ~{left_total} coupons left today")

    # 2) Podcast episode with a video
    ep = await db.podcast_episodes.find_one(
        {"publish_status": "published"}) or await db.podcast_episodes.find_one({})
    if ep:
        await db.podcast_episodes.update_one(
            {"_id": ep["_id"]},
            {"$set": {"video_url": SAMPLE_VIDEO, "media_type": "video"}})
        # Ensure the parent channel is publicly visible so the web detail loads.
        if ep.get("channel_id"):
            await db.podcast_channels.update_one(
                {"id": ep["channel_id"]},
                {"$set": {"active": True, "approval_status": "approved"}})
        print(f"VIDEO EPISODE: id={ep.get('id')} channel={ep.get('channel_id')} "
              f"title={ep.get('title')!r}")
        print(f"  web detail URL -> /podcasts/{ep.get('channel_id')}")
    else:
        print("VIDEO EPISODE: no podcast_episodes found to seed")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
