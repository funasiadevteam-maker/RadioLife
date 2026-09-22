"""Bridge Fun Pizza Kitchen's sponsored games into the `branded_games`
collection so they appear in the MOBILE sponsor-games hub
(GET /api/games/sponsor/discover) and are playable via the 2.5D
/wheel + /scratch engine. FPK's games previously lived only in
`game_campaigns` (the web /play engine), so they never surfaced on mobile.

Idempotent. Run: cd /app/backend && python /app/scripts/seed_fpk_branded_games.py
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

FPK_ID = "biz_fun_pizza_kitchen"
FPK_NAME = "Fun Pizza Kitchen"
FPK_LOGO = ("https://static.prod-images.emergentagent.com/jobs/"
            "c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/"
            "469e7b6bd839461811b52b0c761c22effb6fd03f06a52e5222485c2557237a63.jpeg")

# "Every spin wins" pizza-themed prize wheel. Coupon segments map to FPK's
# real active offers (off_fpk_*); if a claim ever fails the engine falls back
# to points, so there is never a dud win.
SEGMENTS = [
    {"label": "10% OFF", "kind": "coupon", "coupon_offer_id": "off_fpk_10",
     "weight": 22, "color": "#10b981"},
    {"label": "100 pts", "kind": "points", "value": 100, "weight": 18, "color": "#ec4899"},
    {"label": "20% OFF", "kind": "coupon", "coupon_offer_id": "off_fpk_20",
     "weight": 16, "color": "#0ea5e9"},
    {"label": "250 pts", "kind": "points", "value": 250, "weight": 12, "color": "#f59e0b"},
    {"label": "30% OFF", "kind": "coupon", "coupon_offer_id": "off_fpk_30",
     "weight": 10, "color": "#a855f7"},
    {"label": "40% OFF", "kind": "coupon", "coupon_offer_id": "off_fpk_40",
     "weight": 8, "color": "#f43f5e"},
    {"label": "500 pts", "kind": "points", "value": 500, "weight": 8, "color": "#22d3ee"},
    {"label": "FREE PIZZA", "kind": "coupon", "coupon_offer_id": "off_fpk_free_pizza",
     "weight": 6, "color": "#ef4444"},
]


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)

    for gid, gtype, spins in [("wheel_spn_fun_pizza", "wheel", 5),
                              ("scratch_spn_fun_pizza", "scratch", 5)]:
        await db.branded_games.update_one(
            {"_id": gid},
            {"$set": {
                "game_type": gtype, "sponsor_name": FPK_NAME,
                "sponsor_business_id": FPK_ID, "logo_url": FPK_LOGO,
                "bgm_key": "games/bgm/wheel_loop.mp3",
                "segments": SEGMENTS, "daily_spins": spins, "active": True,
                "updated_at": now},
             "$setOnInsert": {"created_at": now}},
            upsert=True)
        print(f"  ✓ {gid} ({gtype}) → sponsor {FPK_NAME}")

    # Make FPK's offers actually claimable by the game engine. They were
    # seeded without `inventory_remaining` (claim_offer's atomic decrement
    # needs > 0) / `max_per_user`, so coupon wins silently fell back to
    # points. Backfill the claimability fields so wins mint the real coupon.
    for oid in ["off_fpk_10", "off_fpk_20", "off_fpk_30", "off_fpk_40",
                "off_fpk_free_pizza"]:
        o = await db.offers.find_one({"offer_id": oid})
        if not o:
            continue
        patch = {"updated_at": now}
        if not isinstance(o.get("inventory_remaining"), int):
            patch["inventory_remaining"] = int(o.get("max_redemptions") or 1000)
        if not o.get("max_per_user"):
            patch["max_per_user"] = 5
        if not o.get("redeem_window_seconds"):
            patch["redeem_window_seconds"] = 86400
        if not o.get("end_at") and o.get("end_time"):
            patch["end_at"] = o["end_time"]
        await db.offers.update_one({"offer_id": oid}, {"$set": patch})
        print(f"  ✓ offer {oid} made claimable")

    # sanity: what mobile sponsor-discover will now return
    n = await db.branded_games.count_documents(
        {"active": True, "sponsor_business_id": {"$exists": True, "$ne": None}})
    print(f"active sponsor branded_games (mobile discover): {n}")
    c.close()


if __name__ == "__main__":
    asyncio.run(main())
