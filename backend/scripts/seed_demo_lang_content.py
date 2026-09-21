"""Seed language-specific demo content so the games/quiz language filter is
demonstrable: a Hindi/Bollywood trivia category + a Hindi game campaign.

English users won't see these (hard filter); Hindi users will. The game
campaign is CLONED from an existing active house campaign so its schema
(template + prizes) is guaranteed valid and can't break /play_and_win.
Idempotent. Run:  python -m scripts.seed_demo_lang_content
"""
import asyncio
from datetime import datetime, timezone

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    cfg = dotenv_values("/app/backend/.env")
    db = AsyncIOMotorClient(cfg["MONGO_URL"])[cfg["DB_NAME"]]
    now = datetime.now(timezone.utc)

    # 1) Bollywood trivia category (language=hindi) — hidden for english users.
    await db.trivia_categories.update_one(
        {"id": "global-bollywood"},
        {"$set": {
            "id": "global-bollywood", "slug": "bollywood",
            "name": "Bollywood Music", "tagline": "Filmi hits & Hindi classics",
            "icon": "🎬", "market": "global", "language": "hindi",
            "content_language": "hindi", "active": True, "weight": 0.9,
        }},
        upsert=True)

    # 2) Hindi game campaign — cloned from an active house campaign for schema
    #    safety, retitled Bollywood + tagged content_language=hindi.
    src = (await db.game_campaigns.find_one({"campaign_id": "cmp_house_music_trivia"})
           or await db.game_campaigns.find_one({"status": "active", "is_platform_funded": True})
           or await db.game_campaigns.find_one({"status": "active"}))
    new_id = "cmp_demo_bollywood"
    if src:
        clone = {k: v for k, v in src.items() if k != "_id"}
        clone.update({
            "campaign_id": new_id,
            "title": "Bollywood Beats Quiz",
            "description": "Guess the Bollywood song — Hindi music trivia.",
            "content_language": "hindi",
            "status": "active", "is_platform_funded": True, "open_to_all": True,
            "sponsor_name": "FUUSIC",
            "start_at": now, "end_at": None, "updated_at": now,
        })
        await db.game_campaigns.update_one(
            {"campaign_id": new_id}, {"$set": clone}, upsert=True)
        # Clone prizes from the source campaign.
        await db.game_prizes.delete_many({"campaign_id": new_id})
        src_prizes = await db.game_prizes.find(
            {"campaign_id": src["campaign_id"]}).to_list(20)
        for i, p in enumerate(src_prizes):
            np = {k: v for k, v in p.items() if k != "_id"}
            np["campaign_id"] = new_id
            np["prize_id"] = f"{new_id}_prize_{i}"
            await db.game_prizes.update_one(
                {"prize_id": np["prize_id"]}, {"$set": np}, upsert=True)
        print(f"seeded game campaign {new_id} (cloned {src['campaign_id']}, "
              f"{len(src_prizes)} prizes)")
    else:
        print("no source campaign found — skipped game clone")

    cats = await db.trivia_categories.count_documents({})
    print(f"trivia categories total={cats}; bollywood category seeded")


if __name__ == "__main__":
    asyncio.run(main())
