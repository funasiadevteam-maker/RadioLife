"""Phase 42-B — Seed sample pre-roll ads for testing.

Idempotent: drops + re-inserts the 3 fixtures so the tester always has
the same `ad_id` values to point at.

Run:
    python3 backend/scripts/seed_preroll_ads.py
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

# Use Pixabay's CDN — guaranteed open MP3 hosting.  These three URLs are
# short royalty-free clips.  If the URLs ever 404, swap them for any
# 200-OK MP3.
SAMPLE_ADS = [
    {
        "id": "pra_seed_karak_promo",
        "name": "Karak Cafe — Pre-roll promo",
        "advertiser_id": "adv_karak_cafe",
        "advertiser_name": "Karak Cafe Karama",
        "type": "audio_with_companion",
        "audio_url": "https://cdn.pixabay.com/audio/2022/03/15/audio_25738dc742.mp3",
        "audio_duration_seconds": 15,
        "companion_image_url": "https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=600&q=80",
        "companion_cta_text": "Get 20% off your first karak chai",
        "companion_cta_url": "https://example.com/karak-promo",
        "attached_offer_id": "off_karak_20",
        "targeting": {
            "countries": ["AE", "IN", "US", "GB"],
            "languages": ["english", "hindi", "arabic"],
            "station_categories": ["bollywood", "punjabi", "hindi", "pop"],
            "dayparts": [],          # all day
        },
        "hourly_impression_cap_per_user": 1,
        "daily_impression_cap_per_user": 3,
    },
    {
        "id": "pra_seed_pixel_phone",
        "name": "Pixel Phone — Audio teaser",
        "advertiser_id": "adv_pixel",
        "advertiser_name": "Pixel by Google",
        "type": "audio_with_companion",
        "audio_url": "https://www.kozco.com/tech/piano2-CoolEdit.mp3",
        "audio_duration_seconds": 12,
        "companion_image_url": "https://images.unsplash.com/photo-1606220588913-b3aacb4d2f46?w=600&q=80",
        "companion_cta_text": "See the new Pixel — free trade-in",
        "companion_cta_url": "https://example.com/pixel-trade",
        "attached_offer_id": None,
        "targeting": {
            "countries": [],          # global
            "languages": [],
            "station_categories": ["pop", "rock", "edm", "news", "talk"],
            "dayparts": [],
        },
        "hourly_impression_cap_per_user": 1,
        "daily_impression_cap_per_user": 3,
    },
    {
        "id": "pra_seed_radio_app",
        "name": "FUUSIC house spot",
        "advertiser_id": "adv_bigfm_inhouse",
        "advertiser_name": "FUUSIC",
        "type": "audio",
        "audio_url": "https://www.kozco.com/tech/piano2-CoolEdit.mp3",
        "audio_duration_seconds": 10,
        # Sub-Phase 42-B2 — house spot ships as AUDIO ONLY.  The
        # previous "Go ad-free with FUUSIC Premium" companion was a
        # consumer-facing upsell masquerading as an ad — moved to the
        # dedicated <PremiumUpsellBanner /> component.  Ads without an
        # attached offer must not render companion creative.
        "companion_image_url": None,
        "companion_cta_text": None,
        "companion_cta_url": None,
        "attached_offer_id": None,
        "targeting": {
            "countries": [], "languages": [],
            "station_categories": [],          # any
            "dayparts": [],
        },
        "hourly_impression_cap_per_user": 1,
        "daily_impression_cap_per_user": 3,
    },
]


async def seed():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    inserted, replaced = 0, 0
    for fix in SAMPLE_ADS:
        doc = {
            **fix,
            "_id": fix["id"],
            "status": "active",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(days=365)).isoformat(),
            "impressions_served": 0, "completes": 0,
            "skips": 0, "companion_clicks": 0, "wallet_saves": 0,
            "created_by": "seed_script",
            "created_at": now, "updated_at": now,
            "activated_at": now,
        }
        existing = await db.preroll_ads.find_one({"id": fix["id"]})
        if existing:
            await db.preroll_ads.replace_one({"id": fix["id"]}, doc)
            replaced += 1
        else:
            await db.preroll_ads.insert_one(doc)
            inserted += 1

    # Indexes (idempotent).
    await db.preroll_ads.create_index([("id", 1)], unique=True)
    await db.preroll_ads.create_index([("status", 1)])

    total_active = await db.preroll_ads.count_documents({"status": "active"})
    print(f"seed_preroll_ads: inserted={inserted} replaced={replaced} "
                f"active_total={total_active}")
    for fix in SAMPLE_ADS:
        print(f"  ✓ {fix['id']:30s} {fix['name']}")


if __name__ == "__main__":
    asyncio.run(seed())
