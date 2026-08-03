"""Phase SC.3 — Seed default commission rules.

Creates 21 category-level rules + 1 fallback rule.  Idempotent — safe to
re-run.  Skips rules that already exist (matched by name).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from services.commission_service import (
    FALLBACK_RULE_ID, ensure_commission_indexes,
)


# (name, business_category, transaction_type, commission_percent, notes)
DEFAULT_RULES: list[tuple[str, str, str, float, str]] = [
    ("Restaurant · Standard Payment",              "restaurant",              "payment",                    5.0,
        "Standard in-store or online payment for meals."),
    ("Restaurant · Prepaid Meal",                      "restaurant",              "prepaid_meal",          8.0,
        "Prepaid meal packages redeemed via BigFM."),
    ("Restaurant · Gift Card",                            "restaurant",              "gift_card",              6.0,
        "Digital gift card sold through BigFM."),
    ("Restaurant · Paid Coupon",                        "restaurant",              "paid_coupon",          10.0,
        "Discounted meal coupons purchased upfront."),
    ("Café · Standard Payment",                          "cafe",                        "payment",                    5.0,
        "Standard café transaction."),
    ("Retail · Standard Payment",                      "retail",                      "payment",                    6.0,
        "Retail store purchase."),
    ("Retail · Gift Card",                                    "retail",                      "gift_card",              6.0,
        "Digital gift card for retail."),
    ("Salon & Spa · Appointment Deposit",      "salon_spa",              "appointment_deposit", 10.0,
        "Deposit taken at booking; balance charged in-store."),
    ("Salon & Spa · Payment",                              "salon_spa",              "payment",                    8.0,
        "Standard salon or spa payment."),
    ("Event Promoter · Event Ticket",              "event_promoter",      "event_ticket",          12.0,
        "Event ticket sold via BigFM."),
    ("Concert Promoter · Event Ticket",          "concert_promoter",  "event_ticket",          12.0,
        "Concert ticket sold via BigFM."),
    ("Movie Theater · Event Ticket",                "movie_theater",        "event_ticket",          10.0,
        "Movie ticket sold via BigFM."),
    ("Club & Lounge · Payment",                            "club_lounge",          "payment",                    8.0,
        "Nightlife venue payment."),
    ("Fitness · Appointment Deposit",              "fitness",                  "appointment_deposit", 10.0,
        "Class or PT booking deposit."),
    ("Medical & Dental · Appointment Deposit", "medical_dental",   "appointment_deposit", 10.0,
        "Clinic booking deposit."),
    ("Grocery · Standard Payment",                    "grocery",                  "payment",                    4.0,
        "Grocery purchase — lowest commission tier."),
    ("Radio Station · Station Promotion",      "radio_station",        "station_promotion",  15.0,
        "Paid promotion of a partner radio station."),
    ("Podcast Creator · Podcast Sponsorship", "podcast_creator", "podcast_sponsorship", 20.0,
        "Sponsorship placed inside a partner podcast."),
    ("Service Business · Payment",                    "service_business",  "payment",                    8.0,
        "Generic service (plumber, cleaner, etc.)."),
    ("Entertainment · Event Ticket",                "entertainment",        "event_ticket",          12.0,
        "Entertainment venue ticket."),
    ("Other · Standard Payment",                        "other",                      "payment",                    8.0,
        "Safe fallback for uncategorised businesses."),
]


async def seed(db) -> dict:
    await ensure_commission_indexes(db)
    now = datetime.now(timezone.utc)

    inserted = 0
    kept      = 0

    for name, category, txn, pct, notes in DEFAULT_RULES:
        existing = await db.commission_rules.find_one({"name": name})
        if existing:
            kept += 1
            continue
        rid = f"cr_{uuid.uuid4().hex[:14]}"
        doc = {
            "_id":                                rid,
            "rule_id":                        rid,
            "name":                              name,
            "business_category":      category,
            "transaction_type":      txn,
            "commission_percent":  pct,
            "fixed_fee_cents":            0,
            "min_fee_cents":                0,
            "max_fee_cents":                None,
            "stripe_fee_responsibility": "merchant",
            "market":                          None,
            "campaign_type":              None,
            "priority":                      0,
            "effective_start":          now,
            "effective_end":                None,
            "active":                          True,
            "notes":                            notes,
            "created_at":                  now,
            "updated_at":                  now,
            "created_by":                  "seed_script",
            "deletable":                    True,
        }
        await db.commission_rules.insert_one(doc)
        inserted += 1

    # Fallback rule — stable id, non-deletable in UI
    fb = await db.commission_rules.find_one({"_id": FALLBACK_RULE_ID})
    if not fb:
        await db.commission_rules.insert_one({
            "_id":                                FALLBACK_RULE_ID,
            "rule_id":                        FALLBACK_RULE_ID,
            "name":                              "GLOBAL FALLBACK · Wildcard",
            "business_category":      "*",
            "transaction_type":      "*",
            "commission_percent":  10.0,
            "fixed_fee_cents":            0,
            "min_fee_cents":                0,
            "max_fee_cents":                None,
            "stripe_fee_responsibility": "merchant",
            "market":                          None,
            "campaign_type":              None,
            "priority":                      -100,
            "effective_start":          now,
            "effective_end":                None,
            "active":                          True,
            "notes":                            "Applies only when no other rule matches. Do NOT delete — the resolver falls back to a hard-coded 10% if this row disappears.",
            "created_at":                  now,
            "updated_at":                  now,
            "created_by":                  "seed_script",
            "deletable":                    False,
        })
        fallback_created = True
    else:
        fallback_created = False

    total = await db.commission_rules.count_documents({})
    return {"inserted": inserted, "kept": kept,
              "fallback_created": fallback_created, "total": total}


async def _main() -> None:
    url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    dbn = os.environ.get("DB_NAME") or "bigfm"
    client = AsyncIOMotorClient(url)
    db = client[dbn]
    result = await seed(db)
    print(f"[seed_commission_rules] {result}")


if __name__ == "__main__":
    asyncio.run(_main())
