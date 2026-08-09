"""Phase 23 Session 7b — Demo campaign seed for new templates.

Creates ONE approved-active demo campaign for each of the 3 templates
that had no live data after Session 7 (slot_machine, mystery_box,
pick_a_card) so the listener flows can be verified end-to-end.

Idempotent: re-running no-ops thanks to deterministic
`cmp_demo_{template}_001` ids and upsert semantics.  Titles
deliberately AVOID the wipe-script regex (no "test/demo/sample/karak
cafe/etc") so future cleanup passes preserve them.
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient


HOUSE_USER_ID = "usr_demo_house"

# (template_id, game_type, title, brand_color, emoji, sponsor_name, prizes[])
SEEDS = [
    (
        "tpl_slot_machine", "slot_machine",
        "RadioLife Lucky Reels",
        "#ef4444",  # red, distinct from mystery's amber
        "🎰", "RadioLife",
        [("Free Coffee", 60, "Espresso on us", 12.0),
          ("Free Pastry", 30, "Pick any pastry",  8.0),
          ("10% Off",        10, "Next purchase",     0.0)],
    ),
    (
        "tpl_mystery_box", "mystery_box",
        "RadioLife Surprise Box",
        "#f59e0b",  # amber per existing TEMPLATE_THEME.mystery_box
        "🎁", "RadioLife",
        [("Mystery Coffee", 60, "Random hot drink",         12.0),
          ("Mystery Snack",   30, "Random pastry / cookie", 10.0),
          ("Mystery Merch",   10, "RadioLife tote / sticker", 25.0)],
    ),
    (
        "tpl_pick_a_card", "pick_a_card",
        "RadioLife Card Pick",
        "#ec4899",  # pink per TEMPLATE_THEME.pick_a_card
        "🃏", "RadioLife",
        [("Iced Latte",        60, "On the house", 18.0),
          ("Bottled Water", 30, "Stay hydrated",  4.0),
          ("Concert Ticket", 10, "Local gig pass", 80.0)],
    ),
]


async def ensure_house_user(db) -> str:
    """Upsert a RadioLife-house advertiser user.  Used as the demo
    campaigns' `advertiser_id` so they show up under the normal
    creator flow."""
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": HOUSE_USER_ID},
        {"$setOnInsert": {
            "_id":  HOUSE_USER_ID, "user_id": HOUSE_USER_ID,
            "email": "house+demo@bigfm.dubai",
            "name":  "RadioLife House",
            "role":  "advertiser",
            "is_advertiser": True,
            "created_at": now,
        }},
        upsert=True)
    return HOUSE_USER_ID


async def seed_one(db, tpl, gtype, title, brand, emoji, sponsor, prizes) -> str:
    cid = f"cmp_demo_{gtype}_001"
    now = datetime.now(timezone.utc)
    placement = {
        "surfaces":                       ["play_and_win_tab"],
        "min_listening_minutes": 0,
        "max_wins_per_user":      3,
        "max_plays_per_day":      5,
        "cooldown_minutes":      30,
    }
    # Build win_rules_json with embedded prize structure (mirrors
    # how the wizard saves it post-Session 3).
    win_rules = {
        "prizes": [
            {"title": p[0], "weight": p[1], "description": p[2],
              "value_amount": p[3]}
            for p in prizes
        ],
        "max_plays_per_user_per_day": 3,
    }
    doc = {
        "_id": cid, "campaign_id": cid,
        "title":              title,
        "description":  f"Spin the reels — quick win on every play! ({emoji})"
                                    if gtype == "slot_machine"
                                    else (f"Open a box. Win a treat. ({emoji})"
                                                if gtype == "mystery_box"
                                                else f"Flip a card. See your prize. ({emoji})"),
        "template_id":  tpl,
        "creator_type": "admin",
        "created_by_user_id": HOUSE_USER_ID,
        "advertiser_id":      HOUSE_USER_ID,
        "business_id":          None,
        "sponsor_name":      sponsor,
        "sponsor_logo_url": None,
        "brand_colors_json": {"primary": brand},
        "game_config_json":  {},
        "win_rules_json":      win_rules,
        "placement_rules_json": placement,
        "targeting_json":      {},
        "eligibility_rules_json": {},
        "objective":  "save_for_later",
        "bid_type":    "house",
        "bid_amount_cents": 0,
        "budget_cents":      0,
        "funded_source":    "platform",
        "is_platform_funded": True,
        "open_to_all":          True,
        "status":                  "active",
        "approved_by_user_id": HOUSE_USER_ID,
        "approved_at":  now,
        "start_at":          now,
        "end_at":              None,
        "public_slug":  cid.replace("cmp_", ""),
        "rejection_reason": None,
        "created_at":  now,
        "updated_at":  now,
        "is_demo_seed": True,
    }
    res = await db.game_campaigns.update_one(
        {"_id": cid}, {"$set": doc}, upsert=True)

    # Mirror prizes into game_prizes collection so the win-flow can
    # pick them.  Wipe-clean any stale rows first to keep weights tidy.
    await db.game_prizes.delete_many({"campaign_id": cid})
    for i, (ptitle, weight, desc, val) in enumerate(prizes):
        pid = f"prz_{cid[-8:]}_{i}"
        await db.game_prizes.insert_one({
            "_id": pid, "prize_id": pid,
            "campaign_id":              cid,
            "title":                          ptitle,
            "description":              desc,
            "prize_type":                "coupon",
            "redemption_method": "qr_local",
            "probability_weight": weight,
            "inventory_total":      500,
            "inventory_remaining": 500,
            "max_per_user":            3,
            "value_amount":            val,
            "value_currency":      "AED",
            "linked_offer_id":      None,
            "linked_badge_id":      None,
            "requires_staff_validation": False,
            "requires_location":  False,
            "expiration_policy_json": {"days": 30},
            "active":                        True,
            "created_at":              datetime.now(timezone.utc),
        })

    # Compliance row (open_to_all approval).
    await db.game_compliance_settings.update_one(
        {"_id": cid},
        {"$set": {"_id": cid, "campaign_id": cid,
                            "terms_text": "Demo campaign — standard RadioLife T&Cs apply.",
                            "approval_status": "approved",
                            "approved_by": HOUSE_USER_ID,
                            "approved_at": now}},
        upsert=True)
    return f"{'created' if res.upserted_id else 'updated'} {cid}"


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await ensure_house_user(db)
    out = []
    for seed in SEEDS:
        out.append(await seed_one(db, *seed))
    for line in out:
        print(line)
    # Audit
    total = await db.game_campaigns.count_documents(
        {"is_demo_seed": True, "status": "active"})
    print(f"-- demo seed active count: {total}")


if __name__ == "__main__":
    asyncio.run(main())
