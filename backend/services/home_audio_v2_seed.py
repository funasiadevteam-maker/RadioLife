"""Phase COMPANION.1 demo seeds — make the synced companion + the
sponsored-station slot demonstrable in preview / QA.

All idempotent (upsert by fixed _id):
  1. An `offers` row (so pre-roll save-to-wallet snapshots a real title).
  2. An ACTIVE `preroll_ads` row WITH an attached offer + companion, wildcard
     targeting — so a Free listener actually hears a pre-roll AND the synced
     mid-roll companion above the player lights up.
  3. A LIVE `flagship_boost_activations` row → the reserved "Sponsored" slot
     in Live Right Now lights up (only when the station resolves).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger("bigfm.home_audio_v2_seed")

DEMO_OFFER_ID = "offer_demo_companion"
DEMO_PREROLL_ID = "pra_demo_companion"
DEMO_BOOST_ID = "fbact_demo_sponsored"
DEMO_STATION_ID = "imp_fun_beat_978_uae"
DEMO_BUSINESS_ID = "biz_demo_grill"
COMPANION_IMG = ("https://images.unsplash.com/photo-1532550907401-a500c9a57435"
                 "?crop=entropy&cs=srgb&fm=jpg&q=85&w=800")
# Known-playable short MP3 already used by the SSP mock provider in this env.
MOCK_AUDIO = "https://www.kozco.com/tech/piano2-CoolEdit.mp3"


async def seed_home_audio_v2_demo(db) -> dict:
    now = datetime.now(timezone.utc)

    await db.offers.update_one(
        {"offer_id": DEMO_OFFER_ID},
        {"$set": {
            "offer_id": DEMO_OFFER_ID, "id": DEMO_OFFER_ID,
            "business_id": DEMO_BUSINESS_ID,
            "title": "2X BigPoints at The Grill House",
            "description": "Earn double BigPoints on any order today. Show this in-store.",
            "offer_type": "bigpoints_multiplier",
            "discount_label": "2X BigPoints",
            "discount_value_cents": 0,
            "status": "active",
            "updated_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True)

    await db.preroll_ads.update_one(
        {"_id": DEMO_PREROLL_ID},
        {"$set": {
            "_id": DEMO_PREROLL_ID, "id": DEMO_PREROLL_ID,
            "advertiser_id": DEMO_BUSINESS_ID,
            "advertiser_name": "The Grill House",
            "name": "The Grill House — 2X BigPoints",
            "type": "audio",
            "audio_url": MOCK_AUDIO,
            "audio_duration_seconds": 12,
            "companion_image_url": COMPANION_IMG,
            "companion_cta_text": "2X BigPoints at The Grill House · 2.1 mi",
            "companion_cta_url": f"/shop/{DEMO_BUSINESS_ID}",
            "attached_offer_id": DEMO_OFFER_ID,
            "targeting": {},
            "daily_impression_cap_per_user": 50,
            "hourly_impression_cap_per_user": 20,
            "start_time": (now - timedelta(hours=1)).isoformat(),
            "end_time": None,
            "status": "active",
            "updated_at": now,
        }, "$setOnInsert": {
            "impressions_served": 0, "completes": 0, "skips": 0,
            "companion_clicks": 0, "wallet_saves": 0,
            "created_by": "seed", "created_at": now,
        }},
        upsert=True)

    station = await db.imported_radio_stations.find_one({"id": DEMO_STATION_ID})
    if station:
        await db.flagship_boost_activations.update_one(
            {"_id": DEMO_BOOST_ID},
            {"$set": {
                "_id": DEMO_BOOST_ID, "id": DEMO_BOOST_ID,
                "station_id": DEMO_STATION_ID,
                "advertiser_business_id": DEMO_BUSINESS_ID,
                "region_code": station.get("country") or "AE",
                "station_slot": 1,
                "active_from": now - timedelta(hours=1),
                "active_until": now + timedelta(days=30),
                "status": "live",
                "amount_cents": 0,
                "creative": {"station_id_to_promote": DEMO_STATION_ID,
                             "sponsor_name": "The Grill House"},
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True)

    log.info("[home-audio-v2-seed] demo companion + sponsored station seeded "
             "(station_found=%s)", bool(station))
    return {"offer": DEMO_OFFER_ID, "preroll": DEMO_PREROLL_ID,
            "boost": DEMO_BOOST_ID, "station_found": bool(station)}
