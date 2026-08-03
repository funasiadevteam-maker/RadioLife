"""Phase K.2 — Seed City Stamps definitions.

Creates 18 supported cities globally with AI-generated artwork
(hero + stamp images) via `OPENAI_IMAGE_API_KEY` (gpt-image-1).

The script is idempotent: existing city_id rows get their metadata
refreshed via $set on every run; missing artwork is regenerated.

Usage:
    python3 backend/scripts/seed_city_stamps.py [--force]
    python3 backend/scripts/seed_city_stamps.py --skip-images
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bigfm.seed_city_stamps")

ART_DIR = BASE / "static" / "city_stamps"
ART_DIR.mkdir(parents=True, exist_ok=True)


# Phase K — supported city universe.  Order = `sort_order` on the doc.
CITIES = [
    {"city_id": "dubai",        "name": "Dubai",          "country": "United Arab Emirates",
      "market": "dubai",        "lat": 25.2048, "lng": 55.2708},
    {"city_id": "abu_dhabi",  "name": "Abu Dhabi",  "country": "United Arab Emirates",
      "market": "dubai",        "lat": 24.4539, "lng": 54.3773},
    {"city_id": "dallas",        "name": "Dallas",          "country": "USA",
      "market": "dfw",            "lat": 32.7767, "lng": -96.7970},
    {"city_id": "frisco",        "name": "Frisco",          "country": "USA",
      "market": "dfw",            "lat": 33.1507, "lng": -96.8236},
    {"city_id": "new_york",  "name": "New York",      "country": "USA",
      "market": "nyc",            "lat": 40.7128, "lng": -74.0060},
    {"city_id": "los_angeles","name": "Los Angeles","country": "USA",
      "market": "la",              "lat": 34.0522, "lng": -118.2437},
    {"city_id": "mumbai",      "name": "Mumbai",          "country": "India",
      "market": "mumbai",      "lat": 19.0760, "lng": 72.8777},
    {"city_id": "delhi",        "name": "Delhi",          "country": "India",
      "market": "delhi",        "lat": 28.6139, "lng": 77.2090},
    {"city_id": "bangalore", "name": "Bangalore",  "country": "India",
      "market": "bangalore", "lat": 12.9716, "lng": 77.5946},
    {"city_id": "london",      "name": "London",          "country": "United Kingdom",
      "market": "london",      "lat": 51.5074, "lng": -0.1278},
    {"city_id": "paris",        "name": "Paris",          "country": "France",
      "market": "paris",        "lat": 48.8566, "lng": 2.3522},
    {"city_id": "tokyo",        "name": "Tokyo",          "country": "Japan",
      "market": "tokyo",        "lat": 35.6762, "lng": 139.6503},
    {"city_id": "sydney",      "name": "Sydney",          "country": "Australia",
      "market": "sydney",      "lat": -33.8688, "lng": 151.2093},
    {"city_id": "singapore", "name": "Singapore",  "country": "Singapore",
      "market": "singapore", "lat": 1.3521, "lng": 103.8198},
    {"city_id": "bangkok",    "name": "Bangkok",        "country": "Thailand",
      "market": "bangkok",    "lat": 13.7563, "lng": 100.5018},
    {"city_id": "berlin",      "name": "Berlin",          "country": "Germany",
      "market": "berlin",      "lat": 52.5200, "lng": 13.4050},
    {"city_id": "toronto",    "name": "Toronto",        "country": "Canada",
      "market": "toronto",    "lat": 43.6532, "lng": -79.3832},
    {"city_id": "lagos",        "name": "Lagos",          "country": "Nigeria",
      "market": "lagos",        "lat": 6.5244, "lng": 3.3792},
]


def _hero_prompt(name: str, country: str) -> str:
    return (f"Cinematic dark-mode skyline of {name}, {country} at golden "
                  "hour. Vibrant neon accents, ultrawide composition, soft "
                  "depth-of-field, premium editorial photography. No text "
                  "or watermarks. Square 1:1 frame.")


def _stamp_prompt(name: str, country: str) -> str:
    return (f"A vintage passport stamp design featuring the iconic skyline "
                  f"of {name}, {country}. Circular emblem, embossed look, "
                  f"navy + neon-magenta + gold ink, with the city's name "
                  f"'{name}' arched across the top in serif lettering and "
                  f"the country '{country}' along the bottom. Detailed "
                  f"geometric inner border. Aged paper background. No "
                  f"extra text. Square 1:1 frame, centered.")


async def _gen_image(prompt: str, *, slug: str, kind: str,
                                  skip: bool) -> str | None:
    """Generate one image via OPENAI_IMAGE_API_KEY → save under
    static/city_stamps/<slug>_<kind>.png.  Returns the API path."""
    fname = f"{slug}_{kind}.png"
    disk = ART_DIR / fname
    api_path = f"/api/static/city_stamps/{fname}"
    if disk.exists() and disk.stat().st_size > 1024:
        return api_path   # already generated
    if skip:
        return None
    try:
        from services.openai_image_provider import generate_image
        raw = await generate_image(prompt, size="1024x1024",
                                                            quality="standard")
        disk.write_bytes(raw)
        log.info("[city_stamps] image generated %s (%d KB)", fname,
                        len(raw) // 1024)
        return api_path
    except Exception as e:
        log.error("[city_stamps] image gen failed %s: %s", slug, e)
        return None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-images", action="store_true",
                              help="Insert/refresh rows without generating images.")
    ap.add_argument("--force", action="store_true",
                              help="Re-generate even if image already exists on disk.")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    inserted = updated = images = 0

    for idx, c in enumerate(CITIES, start=1):
        cid = c["city_id"]
        hero = await _gen_image(_hero_prompt(c["name"], c["country"]),
                                                          slug=cid, kind="hero",
                                                          skip=args.skip_images) \
                          if (args.force or not (ART_DIR / f"{cid}_hero.png").exists()) \
                          else f"/api/static/city_stamps/{cid}_hero.png"
        stamp = await _gen_image(_stamp_prompt(c["name"], c["country"]),
                                                            slug=cid, kind="stamp",
                                                            skip=args.skip_images) \
                            if (args.force or not (ART_DIR / f"{cid}_stamp.png").exists()) \
                            else f"/api/static/city_stamps/{cid}_stamp.png"
        if hero:   images += 1
        if stamp: images += 1
        spec = {**c,
                      "sort_order": idx,
                      "hero_image_url":  hero,
                      "stamp_image_url": stamp,
                      "updated_at": now}
        res = await db.city_stamps_definitions.update_one(
            {"city_id": cid},
            {"$set": spec,
              "$setOnInsert": {"_id": f"cdef_{cid}",
                                              "created_at": now}},
            upsert=True)
        if res.upserted_id is not None:
            inserted += 1
        else:
            updated += 1
    print(f"[city_stamps] inserted={inserted} updated={updated} "
                f"images_present={images} cities_total={len(CITIES)}")


if __name__ == "__main__":
    asyncio.run(main())
