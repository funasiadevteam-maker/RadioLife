"""Phase 4 — Advertising seed data + ad creative generation.

Seeds on boot:
- 3 demo advertisers (owners are the existing admin/test users, so we don't need
  separate auth setup)
- 5 campaigns spanning the major campaign types (coupon, appointment, prepaid_meal,
  event_ticket, ecommerce)
- 1 ad creative per campaign (~18-22 second audio ad, lazy-generated via ElevenLabs
  on first boot if not on disk)
- Default action cards per campaign type

Collections written: advertisers, businesses, campaigns, ad_creatives,
ad_action_cards, offers, products, giveaways.

Files: /app/backend/storage/ads/<creative_id>.mp3
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from core.config import STORAGE_DIR, ELEVENLABS_API_KEY

logger = logging.getLogger("bigfm.ads.seed")

ADS_DIR = STORAGE_DIR / "ads"
ADS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Demo advertisers ----------
DEMO_ADVERTISERS: List[dict] = [
    {
        "advertiser_id": "adv_karak_cafe",
        "name": "Karak Cafe Dubai",
        "category": "restaurant",
        "market": "dubai",
        "contact_email": "owner@karakcafe.test",
        "owner_email": "admin@bigfm.dubai",
    },
    {
        "advertiser_id": "adv_dr_mehta_dental",
        "name": "Dr. Mehta Family Dental",
        "category": "dentist",
        "market": "dubai",
        "contact_email": "frontdesk@drmehta.test",
        "owner_email": "admin@bigfm.dubai",
    },
    {
        "advertiser_id": "adv_funasia_cinemas",
        "name": "FunAsia Cinemas",
        "category": "movie",
        "market": "dfw",
        "contact_email": "ops@funasiacinemas.test",
        "owner_email": "admin@bigfm.dubai",
    },
    {
        "advertiser_id": "adv_salam_mart",
        "name": "Salam Mart",
        "category": "retail",
        "market": "dubai",
        "contact_email": "ecom@salammart.test",
        "owner_email": "admin@bigfm.dubai",
    },
    {
        "advertiser_id": "adv_indo_marina",
        "name": "Indo Marina JBR",
        "category": "restaurant",
        "market": "dubai",
        "contact_email": "reservations@indomarina.test",
        "owner_email": "admin@bigfm.dubai",
    },
]


# ---------- Demo businesses (one per advertiser) ----------
DEMO_BUSINESSES: List[dict] = [
    {
        "business_id": "biz_karak_cafe_karama", "advertiser_id": "adv_karak_cafe",
        "name": "Karak Cafe — Karama Branch", "category": "restaurant",
        "address": "Shop 4, Karama Centre, Dubai", "city": "Dubai", "market": "dubai",
        "latitude": 25.2522, "longitude": 55.3026,
        "phone": "+971-4-555-1010", "website": "https://karakcafe.test",
        "brand_colors_json": {"primary": "#C8102E", "secondary": "#F5C518"},
        "verified": True, "active": True,
    },
    {
        "business_id": "biz_dr_mehta_jlt", "advertiser_id": "adv_dr_mehta_dental",
        "name": "Dr. Mehta Family Dental — JLT Clinic", "category": "dentist",
        "address": "Cluster X, JLT, Dubai", "city": "Dubai", "market": "dubai",
        "latitude": 25.0668, "longitude": 55.1416,
        "phone": "+971-4-555-2020", "website": "https://drmehta.test",
        "brand_colors_json": {"primary": "#0A66C2", "secondary": "#7BD3F7"},
        "verified": True, "active": True,
    },
    {
        "business_id": "biz_funasia_cinemas_irving", "advertiser_id": "adv_funasia_cinemas",
        "name": "FunAsia Cinemas — Irving 8", "category": "movie",
        "address": "3535 W Walnut Hill Ln, Irving, TX 75038", "city": "Irving", "market": "dfw",
        "latitude": 32.8758, "longitude": -96.9869,
        "phone": "+1-972-555-3030", "website": "https://funasiacinemas.test",
        "brand_colors_json": {"primary": "#FF2D95", "secondary": "#FFD93D"},
        "verified": True, "active": True,
    },
    {
        "business_id": "biz_salam_mart_busn_bay", "advertiser_id": "adv_salam_mart",
        "name": "Salam Mart Express — Business Bay", "category": "retail",
        "address": "Bay Square Bldg 12, Business Bay, Dubai", "city": "Dubai", "market": "dubai",
        "latitude": 25.1881, "longitude": 55.2630,
        "phone": "+971-4-555-4040", "website": "https://salammart.test",
        "brand_colors_json": {"primary": "#22C55E", "secondary": "#FACC15"},
        "verified": True, "active": True,
    },
    {
        "business_id": "biz_indo_marina_jbr", "advertiser_id": "adv_indo_marina",
        "name": "Indo Marina JBR — The Walk", "category": "restaurant",
        "address": "Murjan 4, JBR The Walk, Dubai", "city": "Dubai", "market": "dubai",
        "latitude": 25.0786, "longitude": 55.1342,
        "phone": "+971-4-555-5050", "website": "https://indomarina.test",
        "brand_colors_json": {"primary": "#8B5CF6", "secondary": "#F472B6"},
        "verified": True, "active": True,
    },
]


# ---------- Demo campaigns + creatives ----------
DEMO_CAMPAIGNS: List[dict] = [
    {
        "campaign_id": "cmp_karak_20off",
        "advertiser_id": "adv_karak_cafe", "business_id": "biz_karak_cafe_karama",
        "name": "Karak Cafe — 20% off karak chai",
        "campaign_type": "coupon", "objective": "redemptions",
        "status": "active",
        "budget_cents": 50_000, "daily_budget_cents": 5_000,
        "bid_cents_per_impression": 200,   # $2 CPM
        "pacing": "even",
        "targeting": {
            "markets": ["dubai"], "cities": ["Dubai"],
            "languages": ["Hindi", "English"], "genres": ["bollywood", "oldies"],
            "moods": ["happy", "chill", "energetic"],
            "activities": ["commute", "morning", "afternoon"],
            "dayparts": ["morning_drive", "lunch_rush", "evening_drive"],
            "premium_only": False, "free_only": True,
        },
        "frequency_cap": {"per_hour": 1, "per_day": 3, "per_week": 8, "per_user_lifetime": 30},
        "action_card_buttons": ["save_coupon", "get_directions", "share"],
        "creative_script": "[warm] Karama mein Karak chai chahiye? [excited] Karak Cafe is celebrating with 20 percent off ALL chai today. [hyped] Save the code KARAK20 on RadioLife right now — show it at the counter, sip happy. [warm] Karak Cafe — Karama. Dil se.",
        "creative_voice_key": "raghav_hindi",
        "creative_duration_sec": 18.0,
        "offer": {
            "offer_id": "off_karak_20",
            "title": "20% off any karak chai", "description": "Show this coupon at Karak Cafe Karama.",
            "offer_type": "percent", "discount_percent": 20,
            "max_redemptions": 200,
        },
    },
    {
        "campaign_id": "cmp_dr_mehta_appt",
        "advertiser_id": "adv_dr_mehta_dental", "business_id": "biz_dr_mehta_jlt",
        "name": "Dr. Mehta — Free dental check-up",
        "campaign_type": "appointment", "objective": "bookings",
        "status": "active",
        "budget_cents": 75_000, "daily_budget_cents": 6_000,
        "bid_cents_per_impression": 300,
        "pacing": "smart",
        "targeting": {
            "markets": ["dubai"], "cities": ["Dubai"],
            "languages": ["Hindi", "English"],
            "moods": ["chill", "uplifting"],
            "activities": ["evening", "weekend"],
            "dayparts": ["evening_drive", "overnight_lounge"],
            "premium_only": False, "free_only": True,
        },
        "frequency_cap": {"per_hour": 1, "per_day": 2, "per_week": 5, "per_user_lifetime": 12},
        "action_card_buttons": ["book_appointment", "request_callback", "get_directions"],
        "creative_script": "[warm] Family ka dental check-up due hai? [crisp] Dr. Mehta Family Dental in JLT is offering a free first visit this month. [warm] Book in two taps — right here on RadioLife. [excited] Dr. Mehta Dental. Healthy smiles, family-first.",
        "creative_voice_key": "aanya_hindi",
        "creative_duration_sec": 20.0,
        "offer": None,
    },
    {
        "campaign_id": "cmp_funasia_premiere",
        "advertiser_id": "adv_funasia_cinemas", "business_id": "biz_funasia_cinemas_irving",
        "name": "FunAsia Cinemas — Friday Bollywood Premiere",
        "campaign_type": "event_ticket", "objective": "purchases",
        "status": "active",
        "budget_cents": 120_000, "daily_budget_cents": 12_000,
        "bid_cents_per_impression": 250,
        "pacing": "even",
        "targeting": {
            "markets": ["dfw"], "cities": ["Irving", "Plano", "Frisco", "Dallas"],
            "languages": ["Hindi", "English"], "genres": ["bollywood", "pop"],
            "moods": ["happy", "energetic"],
            "activities": ["evening", "weekend"],
            "dayparts": ["evening_drive", "nightlife_mode"],
            "premium_only": False, "free_only": True,
        },
        "frequency_cap": {"per_hour": 1, "per_day": 3, "per_week": 9, "per_user_lifetime": 24},
        "action_card_buttons": ["buy_tickets", "join_giveaway", "share", "remind_me_later"],
        "creative_script": "[hyped] DFW! Friday night Bollywood premiere is HERE. [excited] FunAsia Cinemas Irving — biggest Bollywood release of the year, [warm] dolby surround, samosa-popcorn combos, the works. [hyped] Buy tickets right now — or join the giveaway for a free family pass. FunAsia AI Radio.",
        "creative_voice_key": "charlie_dj",
        "creative_duration_sec": 22.0,
        "offer": None,
        "giveaway": {
            "giveaway_id": "gw_funasia_family_pass",
            "title": "Free Family Pass — Friday Bollywood Premiere",
            "prize_value_cents": 6500, "max_winners": 3,
            "draw_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        },
    },
    {
        "campaign_id": "cmp_salam_grocery",
        "advertiser_id": "adv_salam_mart", "business_id": "biz_salam_mart_busn_bay",
        "name": "Salam Mart — 1-hour grocery delivery",
        "campaign_type": "ecommerce", "objective": "purchases",
        "status": "active",
        "budget_cents": 90_000, "daily_budget_cents": 8_000,
        "bid_cents_per_impression": 180,
        "pacing": "asap",
        "targeting": {
            "markets": ["dubai"],
            "languages": ["Hindi", "English"],
            "moods": ["chill", "happy"],
            "activities": ["commute", "evening", "weekend"],
            "dayparts": ["lunch_rush", "evening_drive"],
            "premium_only": False, "free_only": False,
        },
        "frequency_cap": {"per_hour": 1, "per_day": 4, "per_week": 12, "per_user_lifetime": 40},
        "action_card_buttons": ["buy_now", "add_to_wallet", "share"],
        "creative_script": "[upbeat] Grocery khatam? [warm] Salam Mart Express delivers in one hour — Business Bay, Marina, Downtown. [excited] Tap Buy Now for ten percent off your first order. [warm] Salam Mart. Ghar tak, fast.",
        "creative_voice_key": "raghav_hindi",
        "creative_duration_sec": 19.0,
        "product": {
            "product_id": "prd_salam_first_order_15aed",
            "title": "AED 75 grocery starter pack (with 10% off)",
            "price_cents": 6800,                 # AED 68 after discount
            "currency": "AED",
            "stripe_price_id": None,             # Phase 4 stub — Phase 4.5 wires Stripe Connect
        },
    },
    {
        "campaign_id": "cmp_indo_marina_lunch",
        "advertiser_id": "adv_indo_marina", "business_id": "biz_indo_marina_jbr",
        "name": "Indo Marina JBR — Prepaid Lunch",
        "campaign_type": "prepaid_meal", "objective": "purchases",
        "status": "active",
        "budget_cents": 60_000, "daily_budget_cents": 5_500,
        "bid_cents_per_impression": 220,
        "pacing": "even",
        "targeting": {
            "markets": ["dubai"], "cities": ["Dubai"],
            "languages": ["Hindi", "English"],
            "moods": ["happy", "uplifting"],
            "activities": ["lunch", "afternoon"],
            "dayparts": ["lunch_rush"],
            "premium_only": False, "free_only": True,
        },
        "frequency_cap": {"per_hour": 1, "per_day": 2, "per_week": 6, "per_user_lifetime": 15},
        "action_card_buttons": ["buy_prepaid_lunch", "reserve_table", "save_coupon"],
        "creative_script": "[warm] JBR lunch plans? [excited] Indo Marina is doing a prepaid lunch deal — AED 49 for the full thali, [hyped] no waiting, no surprise bills. [warm] Pre-pay on RadioLife, walk in, sit down. [excited] Indo Marina, JBR The Walk.",
        "creative_voice_key": "aanya_hindi",
        "creative_duration_sec": 20.0,
        "product": {
            "product_id": "prd_indo_marina_lunch_49aed",
            "title": "Prepaid Lunch Thali — Indo Marina JBR",
            "price_cents": 4900, "currency": "AED",
            "stripe_price_id": None,
        },
    },
]


# ---------- Mongo bootstrap ----------
async def ensure_ads_indexes(db) -> None:
    await db.advertisers.create_index([("advertiser_id", 1)], unique=True)
    await db.businesses.create_index([("business_id", 1)], unique=True)
    await db.businesses.create_index([("advertiser_id", 1), ("market", 1)])
    await db.campaigns.create_index([("campaign_id", 1)], unique=True)
    await db.campaigns.create_index([("status", 1), ("advertiser_id", 1)])
    await db.ad_creatives.create_index([("campaign_id", 1)])
    await db.ad_creatives.create_index([("creative_id", 1)], unique=True)
    await db.ad_action_cards.create_index([("campaign_id", 1), ("display_order", 1)])
    await db.offers.create_index([("offer_id", 1)], unique=True)
    await db.products.create_index([("product_id", 1)], unique=True)
    await db.giveaways.create_index([("giveaway_id", 1)], unique=True)
    await db.giveaway_entries.create_index([("giveaway_id", 1), ("user_id", 1)])
    await db.ad_pods.create_index([("session_id", 1), ("served_at", -1)])
    await db.ad_pods.create_index([("user_id", 1), ("campaign_id", 1), ("served_at", -1)])
    await db.ad_impressions.create_index([("user_id", 1), ("campaign_id", 1), ("served_at", -1)])
    await db.ad_impressions.create_index([("served_at", -1)])
    await db.ad_clicks.create_index([("user_id", 1), ("clicked_at", -1)])
    await db.coupons.create_index([("user_id", 1), ("status", 1)])
    await db.user_wallet_items.create_index([("user_id", 1), ("status", 1)])
    await db.reservations.create_index([("user_id", 1), ("created_at", -1)])
    await db.openrtb_bid_logs.create_index([("received_at", -1)])


# ---------- Audio ad generation ----------
def _ad_audio_path(creative_id: str) -> Path:
    return ADS_DIR / f"{creative_id}.mp3"


def _generate_ad_audio(creative_id: str, script: str, voice_key: str, max_sec: float) -> bool:
    """Synchronous ElevenLabs TTS for ad creatives. Reuses the imaging-asset
    pipeline (eleven_v3 + truncate + loudnorm-light)."""
    out_path = _ad_audio_path(creative_id)
    if out_path.exists() and out_path.stat().st_size > 4_000:
        return True   # already on disk
    if not ELEVENLABS_API_KEY:
        return False
    try:
        from services.imaging_assets import _voice_id_for, IMAGING_VOICE_SETTINGS
        from services.loudness import normalize_to_lufs
        from elevenlabs import ElevenLabs, VoiceSettings
        from audio_pipeline import truncate_audio
        from core.config import ELEVEN_MODEL_ID, ELEVEN_FALLBACK_MODEL, ELEVEN_OUTPUT_FORMAT
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        vs = VoiceSettings(stability=0.32, similarity_boost=0.7, style=0.55, use_speaker_boost=True)
        raw_path = out_path.with_name(out_path.stem + ".raw.mp3")
        try:
            audio_iter = client.text_to_speech.convert(
                voice_id=_voice_id_for(voice_key), model_id=ELEVEN_MODEL_ID, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs,
            )
        except Exception:
            audio_iter = client.text_to_speech.convert(
                voice_id=_voice_id_for(voice_key), model_id=ELEVEN_FALLBACK_MODEL, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs,
            )
        with open(raw_path, "wb") as f:
            for chunk in audio_iter:
                if chunk:
                    f.write(chunk)
        try:
            truncate_audio(raw_path, max_sec + 0.4, fade_out_ms=160)
        except Exception:
            pass
        normalize_to_lufs(raw_path, out_path, target_i=-14.0, target_tp=-1.0)
        try: raw_path.unlink(missing_ok=True)  # type: ignore
        except Exception: pass
        return out_path.exists() and out_path.stat().st_size > 4_000
    except Exception as e:
        logger.warning(f"ad gen failed for {creative_id}: {e}")
        return False


# ---------- Seed driver ----------
async def seed_demo_ads(db) -> dict:
    """Idempotent. Returns counts."""
    now = datetime.now(timezone.utc)
    stats = {"advertisers": 0, "businesses": 0, "campaigns": 0,
             "creatives_seeded": 0, "creatives_generated": 0,
             "offers": 0, "products": 0, "giveaways": 0}

    # 1. Advertisers — link to existing users by owner_email
    for adv in DEMO_ADVERTISERS:
        owner = await db.users.find_one({"email": adv["owner_email"]}, {"user_id": 1})
        owner_user_id = owner["user_id"] if owner else None
        await db.advertisers.update_one(
            {"advertiser_id": adv["advertiser_id"]},
            {"$set": {
                "advertiser_id": adv["advertiser_id"],
                "user_id": owner_user_id,
                "name": adv["name"], "category": adv["category"],
                "market": adv["market"],
                "contact_email": adv["contact_email"],
                "billing_status": "active", "total_spent_cents": 0,
                "approval_status": "approved",
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        stats["advertisers"] += 1

    for biz in DEMO_BUSINESSES:
        await db.businesses.update_one(
            {"business_id": biz["business_id"]},
            {"$set": {**biz, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        stats["businesses"] += 1

    # 2. Campaigns + creatives + offers
    for cmp in DEMO_CAMPAIGNS:
        creative_id = f"crv_{cmp['campaign_id']}"
        # Generate ad audio synchronously (idempotent, ~5s per missing audio)
        ok = _generate_ad_audio(creative_id, cmp["creative_script"],
                                  cmp["creative_voice_key"], cmp["creative_duration_sec"])
        if ok and not _ad_audio_path(creative_id).exists():
            ok = False
        if ok:
            try:
                from audio_pipeline import ffprobe_duration
                duration_actual = float(ffprobe_duration(_ad_audio_path(creative_id)) or cmp["creative_duration_sec"])
            except Exception:
                duration_actual = cmp["creative_duration_sec"]
        else:
            duration_actual = 0.0

        # Campaign upsert
        await db.campaigns.update_one(
            {"campaign_id": cmp["campaign_id"]},
            {"$set": {
                "campaign_id": cmp["campaign_id"],
                "advertiser_id": cmp["advertiser_id"], "business_id": cmp["business_id"],
                "name": cmp["name"], "campaign_type": cmp["campaign_type"],
                "objective": cmp["objective"], "status": cmp["status"],
                "budget_cents": cmp["budget_cents"], "daily_budget_cents": cmp["daily_budget_cents"],
                "bid_cents_per_impression": cmp["bid_cents_per_impression"],
                "pacing": cmp["pacing"],
                "start_date": now.isoformat(),
                "end_date": (now + timedelta(days=30)).isoformat(),
                "targeting_json": cmp["targeting"],
                "creative_ids": [creative_id],
                "frequency_cap": cmp["frequency_cap"],
                "approved_by": "system_seed",
                "approved_at": now,
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        stats["campaigns"] += 1

        # Creative upsert
        await db.ad_creatives.update_one(
            {"creative_id": creative_id},
            {"$set": {
                "creative_id": creative_id,
                "campaign_id": cmp["campaign_id"],
                "advertiser_id": cmp["advertiser_id"],
                "creative_type": "audio_ad",
                "duration_sec": duration_actual,
                "audio_path": str(_ad_audio_path(creative_id)),
                "audio_url": f"/api/ads/creative/{creative_id}/audio",
                "transcript": cmp["creative_script"],
                "voice_key": cmp["creative_voice_key"],
                "voice_provider": "elevenlabs",
                "is_ai_generated": True,
                "approval_status": "approved",
                "active": True,
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        stats["creatives_seeded"] += 1
        if ok and duration_actual > 1:
            stats["creatives_generated"] += 1

        # Action cards
        for idx, btn_type in enumerate(cmp["action_card_buttons"]):
            await db.ad_action_cards.update_one(
                {"campaign_id": cmp["campaign_id"], "action_type": btn_type},
                {"$set": {
                    "campaign_id": cmp["campaign_id"], "ad_creative_id": creative_id,
                    "action_type": btn_type,
                    "label": _default_label(btn_type),
                    "display_order": idx,
                    "enabled": True,
                    "destination_url": cmp.get("targeting", {}).get("dest_url"),
                }},
                upsert=True,
            )

        # Offers (coupons)
        if cmp.get("offer"):
            o = cmp["offer"]
            await db.offers.update_one(
                {"offer_id": o["offer_id"]},
                {"$set": {**o, "business_id": cmp["business_id"], "campaign_id": cmp["campaign_id"],
                          "status": "active", "updated_at": now},
                 "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            stats["offers"] += 1

        # Products
        if cmp.get("product"):
            p = cmp["product"]
            await db.products.update_one(
                {"product_id": p["product_id"]},
                {"$set": {**p, "business_id": cmp["business_id"], "campaign_id": cmp["campaign_id"],
                          "active": True, "updated_at": now},
                 "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            stats["products"] += 1

        # Giveaways
        if cmp.get("giveaway"):
            g = cmp["giveaway"]
            await db.giveaways.update_one(
                {"giveaway_id": g["giveaway_id"]},
                {"$set": {**g, "business_id": cmp["business_id"], "campaign_id": cmp["campaign_id"],
                          "status": "open", "updated_at": now},
                 "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            stats["giveaways"] += 1

    return stats


def _default_label(action_type: str) -> str:
    return {
        "save_coupon":         "Save coupon",
        "clip_ad":             "Clip this",
        "add_to_wallet":       "Save to wallet",
        "book_appointment":    "Book appointment",
        "reserve_table":       "Reserve table",
        "order_now":           "Order now",
        "buy_now":             "Buy now",
        "buy_gift_card":       "Buy gift card",
        "buy_product":         "Buy product",
        "buy_prepaid_lunch":   "Pre-pay lunch",
        "buy_prepaid_dinner":  "Pre-pay dinner",
        "buy_tickets":         "Buy tickets",
        "get_directions":      "Get directions",
        "request_callback":    "Request callback",
        "join_giveaway":       "Join giveaway",
        "share":               "Share",
        "remind_me_later":     "Remind me later",
    }.get(action_type, action_type.replace("_", " ").title())
