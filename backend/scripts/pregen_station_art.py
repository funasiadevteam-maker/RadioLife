"""Pre-generate AI covers for a curated set of top imported stations that
lack real art. On-demand ensure covers the rest as users browse.

Usage: python3 scripts/pregen_station_art.py [N]
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import image_gen as image_gen_svc  # noqa: E402
from services.station_artwork_prompt import BRAND_SUFFIX, GENRE_HINTS  # noqa: E402


def _prompt(s):
    name = (s.get("name") or "Radio").strip()
    hay = " ".join(str(s.get(k) or "") for k in
                   ("music_genre", "tags_raw", "description", "language")).lower()
    hint = next((h for k, h in GENRE_HINTS.items() if k in hay), "")
    desc = (s.get("description") or "").strip()
    parts = [f"Cover artwork capturing the vibe of the radio station '{name}'."]
    if hint:
        parts.append(f"Visual mood: {hint}.")
    elif desc:
        parts.append(f"Theme: {desc[:160]}.")
    parts.append(BRAND_SUFFIX)
    return " ".join(parts)[:1800]


async def main(n=6):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    q = {"active": True,
         "flagship_art": {"$in": [None, ""]},
         "art_url": {"$in": [None, ""]},
         "art_gen_attempted": {"$ne": True}}
    cur = db.imported_radio_stations.find(q).sort("click_count", -1).limit(n)
    stations = [s async for s in cur]
    print(f"pre-generating {len(stations)} covers…")
    for s in stations:
        sid = s.get("id")
        await db.imported_radio_stations.update_one(
            {"id": sid}, {"$set": {"art_gen_attempted": True}})
        res = await image_gen_svc.generate(db, prompt=_prompt(s), user_id="",
                                            station_slug=sid, bypass_rate_limit=True)
        if res.get("ok"):
            await db.imported_radio_stations.update_one(
                {"id": sid}, {"$set": {"art_url": res["url"], "art_source": "ai",
                                       "artwork_status": "complete"}})
            print(f"  ✓ {s.get('name')} → {res['url']}")
        else:
            print(f"  ✗ {s.get('name')} → {res.get('error')}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 6))
