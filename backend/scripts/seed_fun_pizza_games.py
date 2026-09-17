"""Seed the demo business 'Fun Pizza Kitchen' with a Spin & Win game whose
prizes are real coupon offers (10/20/30/40% off + free small pizza).

Prize probability is set by discount value — lower discounts come up most
often, the free pizza is rarest. Idempotent: safe to re-run.

Run:  cd /app/backend && python3 -m scripts.seed_fun_pizza_games
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

import services.game_service as gs

load_dotenv()

BIZ_ID = "biz_fun_pizza_kitchen"
BIZ_SLUG = "fun-pizza-kitchen"
LOGO_URL = ("https://static.prod-images.emergentagent.com/jobs/"
            "c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/"
            "469e7b6bd839461811b52b0c761c22effb6fd03f06a52e5222485c2557237a63.jpeg")
CAMPAIGN_NAME = "Fun Pizza Kitchen — Spin & Win"


def _now():
    return datetime.now(timezone.utc)


# offer_id, title, offer_type, discount_percent
OFFERS = [
    ("off_fpk_10", "10% off your order", "percent", 10),
    ("off_fpk_20", "20% off your order", "percent", 20),
    ("off_fpk_30", "30% off your order", "percent", 30),
    ("off_fpk_40", "40% off your order", "percent", 40),
    ("off_fpk_free_pizza", "Free small pizza", "freebie", 100),
]

# display_label, coupon_offer_id, weight (lower discount => higher weight),
# display_color
PRIZES = [
    ("10% OFF",          "off_fpk_10",         40, "#10b981"),
    ("20% OFF",          "off_fpk_20",         25, "#0ea5e9"),
    ("30% OFF",          "off_fpk_30",         15, "#a855f7"),
    ("40% OFF",          "off_fpk_40",          8, "#f59e0b"),
    ("Free Small Pizza", "off_fpk_free_pizza",  3, "#ec4899"),
]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # 1) Business
    await db.businesses.update_one(
        {"business_id": BIZ_ID},
        {"$set": {
            "business_id": BIZ_ID,
            "name": "Fun Pizza Kitchen",
            "slug": BIZ_SLUG,
            "status": "active",
            "logo_url": LOGO_URL,
            "category": "Food & Dining",
            "description": "Hand-tossed pizzas, wood-fired flavour. Spin daily "
                           "for tasty discounts and free slices!",
            "city": "Dubai",
            "updated_at": _now(),
        },
         "$setOnInsert": {"created_at": _now()}},
        upsert=True)
    print(f"[seed] business ready: {BIZ_ID}")

    # 2) Coupon offers
    for offer_id, title, otype, pct in OFFERS:
        await db.offers.update_one(
            {"offer_id": offer_id},
            {"$set": {
                "offer_id": offer_id,
                "business_id": BIZ_ID,
                "title": title,
                "description": f"{title} at Fun Pizza Kitchen. Won via Spin & Win.",
                "offer_type": otype,
                "discount_percent": pct,
                "status": "active",
                "max_redemptions": 1000,
                "end_time": _now() + timedelta(days=90),
                "updated_at": _now(),
            },
             "$setOnInsert": {"created_at": _now()}},
            upsert=True)
    print(f"[seed] {len(OFFERS)} coupon offers ready")

    # 3) Spin template (idempotent)
    await gs.seed_templates(db)

    # 4) Spin & Win campaign (skip if already present)
    existing = await db.game_campaigns.find_one(
        {"merchant_id": BIZ_ID, "name": CAMPAIGN_NAME})
    if existing:
        print(f"[seed] campaign already exists: {existing['campaign_id']} — "
              "refreshing prizes/active window")
        prizes = [gs._validate_prize({
            "prize_type": "coupon",
            "coupon_offer_id": off,
            "weight": w,
            "display_label": label,
            "display_color": color,
            "quantity_available": 0,
        }) for (label, off, w, color) in PRIZES]
        await db.game_campaigns.update_one(
            {"campaign_id": existing["campaign_id"]},
            {"$set": {"prizes": prizes, "active": True,
                      "end_at": _now() + timedelta(days=90),
                      "updated_at": _now()}})
        print(f"[seed] done (updated {existing['campaign_id']})")
        return

    campaign = await gs.create_campaign(
        db,
        merchant_id=BIZ_ID,
        actor={"user_id": "system_seed"},
        game_type="spin_win",
        template_id="tpl_spin_default_6",
        name=CAMPAIGN_NAME,
        description="Spin the wheel for a tasty discount — every spin wins!",
        active=True,
        max_plays_per_user=5,
        end_at=_now() + timedelta(days=90),
        hero_color="#e11d48",
        terms="One coupon per spin. Valid at Fun Pizza Kitchen. Up to 5 spins/day.",
        prizes=[{
            "prize_type": "coupon",
            "coupon_offer_id": off,
            "weight": w,
            "display_label": label,
            "display_color": color,
            "quantity_available": 0,
        } for (label, off, w, color) in PRIZES],
    )
    print(f"[seed] campaign created: {campaign['campaign_id']}")


if __name__ == "__main__":
    asyncio.run(main())
