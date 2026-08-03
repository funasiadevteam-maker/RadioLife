"""Phase 18a — idempotent seeder for the demo `adv_demo_karak` advertiser.

Boots on startup.  Skips if migration_flag `_phase18a_seed_done` is true.
Drops a 1-second placeholder MP3 if the audio file is missing so the audio
URL works for the demo.
"""
from __future__ import annotations
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("bigfm.advertiser.seed")

DEMO_AID    = "adv_demo_karak"
DEMO_CMP    = "cmp_demo_karak_lunch"
DEMO_CRT    = "crt_demo_karak_lunch_15s"
LINKED_BIZ  = "biz_demo_karak"
SAFETY_FLAG = "_phase18a_seed_done"

STATIC_DIR = Path("/app/backend/static/ad_creatives")
AUDIO_PATH = STATIC_DIR / f"{DEMO_CRT}.mp3"
IMAGE_PATH = STATIC_DIR / f"{DEMO_CRT}.webp"


def _ensure_placeholder_audio() -> None:
    """Create a 1-second silent MP3 if missing — keeps URLs honest for demo."""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if AUDIO_PATH.exists() and AUDIO_PATH.stat().st_size > 200:
        return
    if shutil.which("ffmpeg"):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                  "-t", "1", "-q:a", "9", str(AUDIO_PATH)],
                check=True, capture_output=True, timeout=15)
            logger.info("[adv_seed] placeholder audio minted: %s", AUDIO_PATH)
            return
        except Exception as e:
            logger.warning("[adv_seed] ffmpeg placeholder failed: %s", e)
    # Last-resort: bytes header so file exists.
    AUDIO_PATH.write_bytes(b"ID3" + b"\x00" * 256)


def _ensure_placeholder_image() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    if IMAGE_PATH.exists() and IMAGE_PATH.stat().st_size > 100:
        return
    # 32-byte minimal "webp" stub — browsers will fail to render but URL works.
    # Most demos fall through to the click_url anyway.
    IMAGE_PATH.write_bytes(b"RIFF" + b"\x20\x00\x00\x00" + b"WEBPVP8 " + b"\x00" * 16)


async def seed_phase18a(db) -> dict:
    flag = await db.migration_flags.find_one({"_id": SAFETY_FLAG})
    if flag and flag.get("done"):
        return {"skipped": True}

    admin_user = await db.users.find_one({"email": "admin@bigfm.dubai"},
                                                            {"user_id": 1, "_id": 0})
    admin_uid  = admin_user.get("user_id") if admin_user else "user_admin_seed"
    now    = datetime.now(timezone.utc)

    _ensure_placeholder_audio()
    _ensure_placeholder_image()

    # 1) Advertiser ─────────────────────────────────────────────────
    await db.advertisers.update_one(
        {"id": DEMO_AID},
        {"$setOnInsert": {
            "id":                          DEMO_AID,
            "name":                      "Karak Cafe (Demo)",
            "contact_email":         "ads@karakcafe.demo",
            "contact_phone":         "+971-50-000-0001",
            "billing_user_id":      admin_uid,
            "stripe_customer_id": "cus_test_demo_karak",
            "account_balance_usd": 50.00,
            "plan_tier":                "self_serve",
            "market":                    "dubai",
            "status":                    "active",
            "linked_business_slug": LINKED_BIZ,
            "created_at":             now,
        }},
        upsert=True)

    # 2) Staff (admin = owner) ──────────────────────────────────────
    await db.advertiser_staff.update_one(
        {"advertiser_id": DEMO_AID, "user_id": admin_uid},
        {"$setOnInsert": {
            "id":              "astaff_demo_karak_owner",
            "advertiser_id": DEMO_AID,
            "user_id":     admin_uid,
            "role":           "owner",
            "created_at": now,
        }},
        upsert=True)

    # 3) Creative ──────────────────────────────────────────────────
    audio_url = f"/api/static/ad_creatives/{DEMO_CRT}.mp3"
    image_url = f"/api/static/ad_creatives/{DEMO_CRT}.webp"
    await db.ad_creatives.update_one(
        {"id": DEMO_CRT},
        {"$setOnInsert": {
            "id":                  DEMO_CRT,
            "advertiser_id":  DEMO_AID,
            "campaign_id":    DEMO_CMP,
            "kind":               "audio_15s",
            "title":              "Karak Cafe — Free dessert with any lunch",
            "audio_url":      audio_url,
            "audio_path":     str(AUDIO_PATH),
            "image_url":     image_url,
            "click_url":       "https://karakcafe.demo/lunch",
            "transcript":     "Lunch rush at Karak Cafe — free dessert with any lunch combo today.",
            "duration_sec": 15,
            "status":           "approved",
            "brand_safety_check": {"verdict": "approved", "issues": [], "confidence": 0.98},
            "created_at":   now,
        }},
        upsert=True)

    # 4) Campaign ──────────────────────────────────────────────────
    end_d = (now + timedelta(days=30)).date().isoformat()
    start = now.date().isoformat()
    await db.ad_campaigns.update_one(
        {"id": DEMO_CMP},
        {"$setOnInsert": {
            "id":                  DEMO_CMP,
            "advertiser_id":  DEMO_AID,
            "name":              "Lunch Rush — Karak Cafe",
            "objective":        "coupon_save",
            "budget_total_usd": 80.00,
            "budget_daily_usd": 20.00,
            "spend_usd":      0.0,
            "start_date":       start,
            "end_date":         end_d,
            "targeting":         {
                "market":            "dubai",
                "time_of_day":  ["afternoon"],
                "days_of_week": [0, 1, 2, 3, 4],
                "channel_slugs": ["morning_masala", "bollywood_mehfil"],
            },
            "status":             "active",
            "creative_ids":   [DEMO_CRT],
            "created_at":      now,
            "updated_at":     now,
            "approved_at":   now,
            "approved_by_user_id": admin_uid,
        }},
        upsert=True)

    await db.migration_flags.update_one(
        {"_id": SAFETY_FLAG},
        {"$set": {"done": True, "ts": now}}, upsert=True)
    logger.info("[adv_seed] Phase 18a demo seed complete")
    return {"skipped": False,
              "advertiser_id": DEMO_AID, "campaign_id": DEMO_CMP,
              "creative_id":    DEMO_CRT}


async def ensure_advertiser_indexes(db) -> None:
    """Indexes for the 5 Phase 18a collections."""
    try:
        await db.advertisers.create_index("id", unique=True)
        await db.advertiser_staff.create_index([("advertiser_id", 1),
                                                                ("user_id", 1)],
                                                                unique=True)
        await db.advertiser_staff.create_index("user_id")
        await db.ad_campaigns.create_index("id", unique=True)
        await db.ad_campaigns.create_index([("advertiser_id", 1), ("status", 1)])
        await db.ad_campaigns.create_index("status")
        await db.ad_creatives.create_index("id", unique=True)
        await db.ad_creatives.create_index([("advertiser_id", 1), ("status", 1)])
        await db.ad_serves.create_index([("user_id", 1), ("served_at", -1)])
        await db.ad_serves.create_index([("campaign_id", 1), ("served_at", -1)])
    except Exception as e:
        logger.warning("[adv_seed] index creation: %s", e)
