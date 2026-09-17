"""Seed the demo business 'Fun Pizza Kitchen' with a Spin & Win AND a
Scratch & Win game.

Prizes are real coupon offers (10/20/30/40% off + free small pizza).  The
Scratch card additionally carries a $10 store gift card that ~10% of plays
win.  Probability is weighted by value — lower discounts come up most often,
the gift card / free pizza are rarest.

Idempotent: safe to re-run (creates or refreshes both games).

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
GC_SKU_ID = "gcs_fun_pizza_10"

SPIN_NAME = "Fun Pizza Kitchen — Spin & Win"
SCRATCH_NAME = "Fun Pizza Kitchen — Scratch & Win"


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

# Coupon prizes — lower discount => higher weight.
SPIN_PRIZES = [
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_10",
     "weight": 40, "display_label": "10% OFF", "display_color": "#10b981"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_20",
     "weight": 25, "display_label": "20% OFF", "display_color": "#0ea5e9"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_30",
     "weight": 15, "display_label": "30% OFF", "display_color": "#a855f7"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_40",
     "weight": 8, "display_label": "40% OFF", "display_color": "#f59e0b"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_free_pizza",
     "weight": 3, "display_label": "Free Small Pizza", "display_color": "#ec4899"},
]

# Scratch card — same discounts + a rare $10 gift card (~10% of plays).
# Weights sum to 100 so the gift card is exactly 1-in-10.
SCRATCH_PRIZES = [
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_10",
     "weight": 36, "display_label": "10% OFF", "display_color": "#10b981"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_20",
     "weight": 24, "display_label": "20% OFF", "display_color": "#0ea5e9"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_30",
     "weight": 15, "display_label": "30% OFF", "display_color": "#a855f7"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_40",
     "weight": 8, "display_label": "40% OFF", "display_color": "#f59e0b"},
    {"prize_type": "coupon", "coupon_offer_id": "off_fpk_free_pizza",
     "weight": 7, "display_label": "Free Small Pizza", "display_color": "#ec4899"},
    {"prize_type": "gift_card", "sku_id": GC_SKU_ID, "value_cents": 1000,
     "weight": 10, "display_label": "$10 Gift Card", "display_color": "#facc15"},
]


async def _ensure_campaign(db, *, name, game_type, template_id, prizes,
                            description, terms):
    existing = await db.game_campaigns.find_one(
        {"merchant_id": BIZ_ID, "name": name})
    validated = [gs._validate_prize({**p, "quantity_available": 0}) for p in prizes]
    if existing:
        await db.game_campaigns.update_one(
            {"campaign_id": existing["campaign_id"]},
            {"$set": {"prizes": validated, "active": True,
                      "end_at": _now() + timedelta(days=90),
                      "updated_at": _now()}})
        print(f"[seed] refreshed {game_type}: {existing['campaign_id']}")
        return existing["campaign_id"]
    campaign = await gs.create_campaign(
        db, merchant_id=BIZ_ID, actor={"user_id": "system_seed"},
        game_type=game_type, template_id=template_id, name=name,
        description=description, active=True, max_plays_per_user=5,
        end_at=_now() + timedelta(days=90), hero_color="#e11d48",
        terms=terms,
        prizes=[{**p, "quantity_available": 0} for p in prizes])
    print(f"[seed] created {game_type}: {campaign['campaign_id']}")
    return campaign["campaign_id"]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # 1) Business
    await db.businesses.update_one(
        {"business_id": BIZ_ID},
        {"$set": {
            "business_id": BIZ_ID, "name": "Fun Pizza Kitchen", "slug": BIZ_SLUG,
            "status": "active", "logo_url": LOGO_URL, "category": "Food & Dining",
            "description": "Hand-tossed pizzas, wood-fired flavour. Play daily "
                           "for tasty discounts, free slices and gift cards!",
            "city": "Dubai", "updated_at": _now()},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True)
    print(f"[seed] business ready: {BIZ_ID}")

    # 2) Coupon offers
    for offer_id, title, otype, pct in OFFERS:
        await db.offers.update_one(
            {"offer_id": offer_id},
            {"$set": {
                "offer_id": offer_id, "business_id": BIZ_ID, "title": title,
                "description": f"{title} at Fun Pizza Kitchen. Won via a game.",
                "offer_type": otype, "discount_percent": pct, "status": "active",
                "max_redemptions": 1000,
                "end_time": _now() + timedelta(days=90), "updated_at": _now()},
             "$setOnInsert": {"created_at": _now()}},
            upsert=True)
    print(f"[seed] {len(OFFERS)} coupon offers ready")

    # 3) $10 gift-card SKU
    await db.gift_card_skus.update_one(
        {"sku_id": GC_SKU_ID},
        {"$set": {
            "sku_id": GC_SKU_ID, "merchant_id": BIZ_ID,
            "name": "Fun Pizza $10 Gift Card",
            "description": "A $10 store gift card, won on the Scratch & Win card.",
            "denominations": [1000], "custom_amount_allowed": False,
            "currency": "USD", "active": True,
            "expires_days_after_purchase": 365, "updated_at": _now()},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True)
    print(f"[seed] gift-card SKU ready: {GC_SKU_ID}")

    # 4) Templates + both games
    await gs.seed_templates(db)
    await _ensure_campaign(
        db, name=SPIN_NAME, game_type="spin_win",
        template_id="tpl_spin_default_6", prizes=SPIN_PRIZES,
        description="Spin the wheel for a tasty discount — every spin wins!",
        terms="One coupon per spin. Valid at Fun Pizza Kitchen. Up to 5 spins/day.")
    await _ensure_campaign(
        db, name=SCRATCH_NAME, game_type="scratch_win",
        template_id="tpl_scratch_default_3x3", prizes=SCRATCH_PRIZES,
        description="Scratch to reveal your prize — discounts, free pizza, or a "
                    "rare $10 gift card!",
        terms="One reward per card. $10 gift card on ~1 in 10 cards. "
              "Valid at Fun Pizza Kitchen. Up to 5 cards/day.")
    print("[seed] done")


if __name__ == "__main__":
    asyncio.run(main())
