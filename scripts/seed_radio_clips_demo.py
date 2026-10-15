"""Seed demo radio clips: station daily HIGHLIGHTS + an authorized clip policy
so Clip & Share is demoable. Idempotent. Audio uses stable public samples
(NOT third-party broadcast recordings)."""
import os
import asyncio
from datetime import datetime, timezone

import motor.motor_asyncio as motor
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

SAMPLES = [
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
]
SLOTS = [
    ("morning", "Morning Drive Highlights", "RJ Alex",
     "The funniest Bollywood debate from today's Morning Drive 😂"),
    ("afternoon", "Afternoon Hits Recap", "RJ Priya",
     "Your midday mood-lifter — today's top requests."),
    ("evening", "Evening Drive Moments", "RJ Sana",
     "Wind-down vibes + the question everyone's answering tonight."),
]


async def main():
    c = motor.AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    u = await db.users.find_one({"email": "demo@bigfm.dubai"})
    uid = u["user_id"]
    st_ids = [s["station_id"] async for s in
              db.station_followers.find({"user_id": uid}, {"station_id": 1})
              if s.get("station_id")]
    print("demo follows stations:", st_ids)
    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc)
    made = 0
    for sid in st_ids:
        s = await db.community_radio_stations.find_one({"station_id": sid})
        if s:
            name, slug, logo = s.get("name") or s.get("slug"), s.get("slug"), s.get("cover_image_url")
        else:
            im = await db.imported_radio_stations.find_one({"id": sid})
            if not im:
                continue
            name, slug, logo = im.get("name"), im.get("flagship_slug"), im.get("favicon")
        # Authorized clip policy (buffer the listener can clip from).
        await db.station_clip_policies.update_one(
            {"station_id": sid},
            {"$set": {"station_id": sid, "clip_enabled": True,
                      "buffer_audio_url": SAMPLES[0], "max_clip_seconds": 30,
                      "buffer_seconds": 300, "rights_policy": "authorized_demo",
                      "updated_at": now}}, upsert=True)
        for i, (slot, show, host, caption) in enumerate(SLOTS):
            _id = f"rc_{sid}_{slot}_{today}".replace(":", "_")[:120]
            await db.radio_clips.update_one(
                {"_id": _id},
                {"$set": {"_id": _id, "kind": "station_highlight", "station_id": sid,
                          "station_slug": slug, "station_name": name, "station_logo": logo,
                          "show_name": show, "host_name": host,
                          "title": f"{show} — Today", "caption": caption,
                          "audio_url": SAMPLES[i % len(SAMPLES)], "duration_sec": 45,
                          "slot": slot, "broadcast_date": today, "broadcast_at": now,
                          "rights": "station_provided", "status": "published",
                          "moderation_status": "approved", "created_by": "system",
                          "created_at": now},
                 "$setOnInsert": {"like_count": 0, "comment_count": 0,
                                  "share_count": 0, "play_count": 0}}, upsert=True)
            made += 1
    print(f"seeded {made} highlight clips + clip policies for {len(st_ids)} stations")
    c.close()


if __name__ == "__main__":
    asyncio.run(main())
