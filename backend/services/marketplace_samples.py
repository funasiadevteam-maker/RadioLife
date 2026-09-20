"""Sample marketplace customers + sample games seed (idempotent).

Seeds two real-world sample storefronts so memberships / appointments /
products are visible out of the box, plus 3 live sample game campaigns per
active game template.

  • Fun Pizza Kitchen (restaurant) — menu pulled from funpizzakitchen.com,
    a Weekly Pizza Club membership ($60/mo, 1 pizza/week) and a Coffee Club
    membership ($9.99/mo, unlimited coffee).
  • Ambreens Salon (beauty) — bookable services (appointments), a retail
    product, and a membership.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from services.marketplace import now


# ───────────────────────── image assets ─────────────────────────
FPK_COVER = "https://images.unsplash.com/photo-1513104890138-7c749659a591?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"
PIZZA_A = "https://images.unsplash.com/photo-1604382354936-07c5d9983bd3?crop=entropy&cs=srgb&fm=jpg&q=85&w=640"
PIZZA_B = "https://images.unsplash.com/photo-1593560708920-61dd98c46a4e?crop=entropy&cs=srgb&fm=jpg&q=85&w=640"
PIZZA_C = "https://images.unsplash.com/photo-1513104890138-7c749659a591?crop=entropy&cs=srgb&fm=jpg&q=85&w=640"
GARLIC_BREAD = "https://images.unsplash.com/photo-1573140401552-3fab0b24306f?crop=entropy&cs=srgb&fm=jpg&q=85&w=640"
CHEESECAKE = "https://images.unsplash.com/photo-1524351199678-941a58a3df50?crop=entropy&cs=srgb&fm=jpg&q=85&w=640"
SALON_COVER = "https://images.unsplash.com/photo-1600948836101-f9ffda59d250?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"
SALON_HAIRCUT = "https://images.unsplash.com/photo-1647140655214-e4a2d914971f?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
SALON_COLOR = "https://images.unsplash.com/photo-1617391654484-2894196c2cc9?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
SALON_FACIAL = "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
SALON_SERUM = "https://images.unsplash.com/photo-1667242003572-96caaf8ac5c4?crop=entropy&cs=srgb&fm=jpg&q=85&w=800"
COFFEE_IMG = "https://images.unsplash.com/photo-1589985902809-39d25db22101?crop=entropy&cs=srgb&fm=jpg&q=85&w=640"


async def _upsert_profile(db, b: Dict[str, Any], market: str) -> None:
    await db.marketplace_profiles.update_one(
        {"business_id": b["id"]},
        {"$set": {
            "public_name": b["public_name"], "description": b["description"],
            "category": b["category"], "subcategory": b["subcategory"],
            "cover_urls": [b["cover"]], "sells": b["sells"],
            "bigpoints": {"mode": "default", "default_points": b["points"],
                          "points_per_dollar": b["ppd"], "product_overrides": {},
                          "service_overrides": {}},
            "rating": b["rating"], "featured": b["featured"], "sponsored": b.get("sponsored", False),
            "website": b.get("website"), "phone": b.get("phone"),
            "market": market, "subscription_active": True, "updated_at": now()},
         "$setOnInsert": {
            "business_id": b["id"], "owner_user_id": "system_sample",
            "business_type": b["category"], "legal_name": b["public_name"] + " LLC",
            "email": None, "logo_url": None,
            "locations": [{"city": b.get("city", market), "address": b.get("address", "Downtown")}],
            "verification": {}, "stripe_account_id": None, "funding_mode": "auto_deduct",
            "commission_agreed": True, "price_parity": None,
            "status": "approved", "rejection_reason": None,
            "approved_at": now(), "created_at": now()}},
        upsert=True)
    await db.businesses.update_one(
        {"business_id": b["id"]},
        {"$set": {"business_id": b["id"], "owner_user_id": "system_sample",
                  "name": b["public_name"], "category": b["category"],
                  "city": b.get("city", market), "active": True, "verified": True,
                  "updated_at": now()},
         "$setOnInsert": {"created_at": now()}}, upsert=True)
    await db.merchant_subscriptions.update_one(
        {"business_id": b["id"]},
        {"$set": {"business_id": b["id"], "plan_id": "pro", "status": "active",
                  "source": "sample_grant", "current_period_end": None, "updated_at": now()},
         "$setOnInsert": {"created_at": now()}}, upsert=True)


async def _upsert_menu(db, biz_id: str, items: List[Dict[str, Any]]) -> None:
    from services.membership_entitlements import OptionGroupModel, normalize_option_groups
    for i, it in enumerate(items):
        item_id = f"mi_{biz_id}_{i}"
        ogs = normalize_option_groups([OptionGroupModel(**g) for g in it.get("option_groups", [])])
        await db.menu_items.update_one(
            {"item_id": item_id},
            {"$set": {"business_id": biz_id, "section": it["section"], "name": it["name"],
                      "description": it["description"], "price_cents": it["price_cents"],
                      "image_url": it.get("image_url"), "bigpoints": None,
                      "option_groups": ogs,
                      "available": True, "sort": i, "updated_at": now()},
             "$setOnInsert": {"item_id": item_id, "created_at": now()}}, upsert=True)


async def _upsert_membership(db, biz_id: str, sponsor: str, key: str, plan: Dict[str, Any]) -> None:
    plan_id = f"mplan_sample_{biz_id}_{key}"
    from services.membership_entitlements import (
        _legacy_entitlement_to_v2, EntitlementModel, normalize_entitlements)
    ents = []
    for e in plan.get("entitlements", []):
        if "target_type" in e:  # already a v2 entitlement spec
            ents.append(normalize_entitlements([EntitlementModel(**e)])[0])
        else:
            ents.append(_legacy_entitlement_to_v2(e))
    await db.membership_plans.update_one(
        {"plan_id": plan_id},
        {"$set": {"business_id": biz_id, "sponsor_name": sponsor, "name": plan["name"],
                  "description": plan["description"], "price_cents": plan["price_cents"],
                  "interval": plan["interval"], "entitlements": ents, "schema_version": 2,
                  "active": True, "updated_at": now()},
         "$setOnInsert": {"plan_id": plan_id, "created_at": now()}}, upsert=True)


async def _upsert_service(db, biz_id: str, idx: int, svc: Dict[str, Any]) -> None:
    sid = f"svc_sample_{biz_id}_{idx}"
    await db.service_items.update_one(
        {"service_id": sid},
        {"$set": {"business_id": biz_id, "sort": idx, "name": svc["name"],
                  "description": svc["description"], "duration_min": svc["duration_min"],
                  "price_cents": svc["price_cents"], "reservation_fee_cents": svc.get("reservation_fee_cents", 0),
                  "bigpoints": None, "image_url": svc.get("image_url"),
                  "active": True, "updated_at": now()},
         "$setOnInsert": {"service_id": sid, "created_at": now()}}, upsert=True)


async def _upsert_product(db, biz_id: str, key: str, prod: Dict[str, Any], sort: int) -> None:
    pid = f"prod_sample_{biz_id}_{key}"
    await db.products.update_one(
        {"product_id": pid},
        {"$set": {"business_id": biz_id, "name": prod["name"], "description": prod["description"],
                  "category": prod.get("category", "Products"), "price_cents": prod["price_cents"],
                  "stock": prod.get("stock", 100), "variants": prod.get("variants", []),
                  "bigpoints": None, "image_url": prod.get("image_url"), "active": True,
                  "sort": sort, "updated_at": now()},
         "$setOnInsert": {"product_id": pid, "created_at": now()}}, upsert=True)


async def seed_sample_storefronts(db, market: str = "Dubai") -> Dict[str, Any]:
    # ── Fun Pizza Kitchen ──
    fpk = {
        "id": "biz_sample_funpizza", "public_name": "Fun Pizza Kitchen", "category": "restaurant",
        "subcategory": "Pizza", "description": "Fresh fusion pizzas, sides, desserts & coffee. Order for pickup and earn BigPoints.",
        "cover": FPK_COVER, "sells": ["menu", "memberships"], "points": 175, "ppd": 2.0,
        "rating": 4.8, "featured": True, "sponsored": True,
        "website": "https://funpizzakitchen.com", "phone": "+1 469 359 2996",
        "city": "Frisco, TX", "address": "15900 State Hwy 121, Suite 100",
    }
    await _upsert_profile(db, fpk, market)
    PIZZA_OPTS = [
        {"group_id": "grp_pizza_size", "name": "Size", "type": "size", "required": True,
         "min_select": 1, "max_select": 1, "options": [
             {"option_id": "opt_size_medium", "label": "Medium", "price_delta_cents": 0, "is_default": True},
             {"option_id": "opt_size_large", "label": "Large", "price_delta_cents": 400}]},
        {"group_id": "grp_pizza_top", "name": "Extra Toppings", "type": "multi", "required": False,
         "min_select": 0, "max_select": 3, "options": [
             {"option_id": "opt_top_cheese", "label": "Extra Cheese", "price_delta_cents": 200},
             {"option_id": "opt_top_mush", "label": "Mushrooms", "price_delta_cents": 150},
             {"option_id": "opt_top_jala", "label": "Jalapeños", "price_delta_cents": 100}]},
    ]
    await _upsert_menu(db, fpk["id"], [
        {"section": "Pizzas", "name": "Mac & Cheese Pizza", "description": "Creamy mac & cheese on a golden crust.", "price_cents": 1799, "image_url": PIZZA_A, "option_groups": PIZZA_OPTS},
        {"section": "Pizzas", "name": "Tandoori Chicken Pizza", "description": "Spiced tandoori chicken, onions & cilantro.", "price_cents": 1899, "image_url": PIZZA_B, "option_groups": PIZZA_OPTS},
        {"section": "Pizzas", "name": "Fun Chicken Pizza", "description": "House-favourite chicken, peppers & onions.", "price_cents": 1799, "image_url": PIZZA_C, "option_groups": PIZZA_OPTS},
        {"section": "Pizzas", "name": "Achari Paneer Pizza", "description": "Tangy achari paneer, olives & jalapeños.", "price_cents": 1699, "image_url": PIZZA_A, "option_groups": PIZZA_OPTS},
        {"section": "Sides", "name": "Chilli Cheese Bread", "description": "Warm cheese bread with a spicy kick.", "price_cents": 899, "image_url": GARLIC_BREAD},
        {"section": "Dessert", "name": "Cheesecake", "description": "Rich, creamy New York-style cheesecake.", "price_cents": 799, "image_url": CHEESECAKE},
        {"section": "Coffee", "name": "Fresh Brewed Coffee", "description": "Hot, locally roasted drip coffee.", "price_cents": 349, "image_url": COFFEE_IMG},
        {"section": "Coffee", "name": "Iced Latte", "description": "Double-shot espresso over ice with milk.", "price_cents": 449, "image_url": COFFEE_IMG},
    ])
    await _upsert_membership(db, fpk["id"], fpk["public_name"], "pizza", {
        "name": "Pizza Club", "interval": "month", "price_cents": 6000,
        "description": "One free Medium pizza every day — upgrade to Large for $4, add toppings anytime.",
        "entitlements": [{
            "entitlement_id": "ent_free_pizza", "label": "Free Pizza (Medium)",
            "target_type": "category", "category": "Pizzas",
            "included_option_ids": ["opt_size_medium"],
            "quantity": 1, "reset_frequency": "daily",
            "rollover": False, "rollover_cap": 0, "stackable": False,
            "max_upcharge_cents": 1000, "active": True}],
    })
    await _upsert_membership(db, fpk["id"], fpk["public_name"], "coffee", {
        "name": "Coffee Club", "interval": "month", "price_cents": 999,
        "description": "Unlimited coffee, every day, all month. $9.99/mo.",
        "entitlements": [{"benefit_id": "bnf_unlimited_coffee", "label": "Unlimited Coffee", "qty": 99, "period": "day", "options": []}],
    })

    # ── Ambreens Salon ──
    salon = {
        "id": "biz_sample_ambreens", "public_name": "Ambreens Salon", "category": "beauty",
        "subcategory": "Salon", "description": "Cuts, colour, spa facials and premium hair care. Book an appointment and earn on every visit.",
        "cover": SALON_COVER, "sells": ["services", "appointments", "products", "memberships"],
        "points": 200, "ppd": 2.0, "rating": 4.9, "featured": True, "sponsored": False,
        "phone": "+971 4 555 0100", "city": market, "address": "Marina Walk",
    }
    await _upsert_profile(db, salon, market)
    # Weekly availability so appointment slots resolve.
    await db.marketplace_profiles.update_one(
        {"business_id": salon["id"]},
        {"$set": {"service_availability": {
            "slot_minutes": 30,
            "days": {str(d): [{"start": "09:00", "end": "18:00"}] for d in range(0, 6)}},
            "product_delivery": {"pickup": True, "delivery": False, "fee_cents": 0, "free_over_cents": 0},
            "updated_at": now()}})
    for i, svc in enumerate([
        {"name": "Haircut & Style", "description": "Wash, cut and blow-dry with a senior stylist.", "duration_min": 45, "price_cents": 6500, "image_url": SALON_HAIRCUT},
        {"name": "Hair Colour", "description": "Full colour or balayage with premium products.", "duration_min": 120, "price_cents": 18000, "image_url": SALON_COLOR},
        {"name": "Signature Spa Facial", "description": "Deep-cleanse facial with mask & massage.", "duration_min": 60, "price_cents": 12000, "image_url": SALON_FACIAL},
    ]):
        await _upsert_service(db, salon["id"], i, svc)
    await _upsert_product(db, salon["id"], "serum", {
        "name": "Argan Repair Hair Serum", "description": "Lightweight Moroccan argan oil serum for shine & frizz control.",
        "category": "Hair Care", "price_cents": 3200, "stock": 40, "image_url": SALON_SERUM}, 0)
    await _upsert_membership(db, salon["id"], salon["public_name"], "glam", {
        "name": "Unlimited Blowouts", "interval": "month", "price_cents": 4900,
        "description": "Look fresh all month — unlimited blowouts plus 10% off colour.",
        "entitlements": [
            {"benefit_id": "bnf_blowout", "label": "Blowout", "qty": 99, "period": "day", "options": []},
            {"benefit_id": "bnf_colour_off", "label": "10% off colour services", "qty": 1, "period": "month", "options": []},
        ],
    })
    return {"sample_storefronts": ["biz_sample_funpizza", "biz_sample_ambreens"]}


# ───────────────────────── sample games ─────────────────────────
GAME_TITLES = {
    "tpl_spin_wheel": ["Daily Spin Jackpot", "Weekend Spin Fiesta", "Lucky Wheel Rush"],
    "tpl_scratch_card": ["Scratch & Win Gold", "Instant Scratch Frenzy", "Golden Ticket Scratch"],
    "tpl_quiz": ["Pop Culture Quiz", "Music Masters Quiz", "Sports IQ Challenge"],
    "tpl_mystery_box": ["Mystery Box Mania", "Surprise Vault", "Lucky Mystery Drop"],
    "tpl_slot_machine": ["777 Slot Rush", "Jackpot Reels", "Triple Bar Slots"],
    "tpl_memory_match": ["Memory Match Mania", "Flip & Match Rush", "Brain Match Blitz"],
    "tpl_word_puzzle": ["Word Puzzle Challenge", "Daily Word Rush", "Scramble Master"],
    "tpl_pick_a_card": ["Pick a Card Fortune", "Lucky Card Draw", "Card Flip Riches"],
}
GAME_PRIZES = [
    {"title": "50 BigCoin", "value_amount": 50},
    {"title": "150 BigCoin", "value_amount": 150},
    {"title": "500 BigCoin", "value_amount": 500},
]


async def seed_sample_games(db) -> Dict[str, Any]:
    created = 0
    n = now()
    end = n + timedelta(days=90)
    async for tpl in db.game_templates.find({"active": True}):
        tid = tpl["template_id"]
        titles = GAME_TITLES.get(tid, [f"{tpl.get('name', 'Game')} #{i + 1}" for i in range(3)])
        base_cfg = dict(tpl.get("default_config_json") or {})
        for i in range(3):
            cid = f"cmp_smp_{tid}_{i}"
            await db.game_campaigns.update_one(
                {"campaign_id": cid},
                {"$set": {
                    "campaign_id": cid, "advertiser_id": None, "business_id": None,
                    "template_id": tid, "title": titles[i % len(titles)],
                    "description": "A FUUSIC house game — play free and win BigCoin.",
                    "sponsor_name": "FUUSIC", "sponsor_logo_url": None, "brand_colors_json": {},
                    "game_config_json": base_cfg, "objective": "platform_engagement",
                    "budget_cents": 0, "bid_type": "per_save", "bid_amount_cents": 0,
                    "start_at": n, "end_at": end, "targeting_json": {},
                    "placement_rules_json": {}, "eligibility_rules_json": {}, "win_rules_json": {},
                    "creator_type": "admin", "status": "active", "is_platform_funded": True,
                    "funded_source": "bigfm_house", "open_to_all": True,
                    "created_by_user_id": "system_sample", "approved_by_user_id": "system_sample",
                    "approved_at": n, "rejection_reason": None, "updated_at": n},
                 "$setOnInsert": {"_id": cid, "created_at": n}}, upsert=True)
            prize = GAME_PRIZES[i % len(GAME_PRIZES)]
            pid = f"prz_smp_{tid}_{i}"
            await db.game_prizes.update_one(
                {"prize_id": pid},
                {"$set": {
                    "prize_id": pid, "campaign_id": cid, "prize_type": "bigcoin",
                    "title": prize["title"], "description": None,
                    "value_amount": prize["value_amount"], "value_currency": "BC",
                    "probability_weight": 100, "inventory_total": 100000,
                    "inventory_remaining": 100000, "max_per_user": 0,
                    "redemption_method": "in_app_wallet", "requires_location": False,
                    "requires_staff_validation": False,
                    "expiration_policy_json": {"days_after_award": 30, "hard_expiry_at": None},
                    "linked_offer_id": None, "linked_badge_id": None, "active": True},
                 "$setOnInsert": {"_id": pid, "created_at": n}}, upsert=True)
            await db.game_redemption_rules.update_one(
                {"campaign_id": cid},
                {"$set": {"campaign_id": cid, "one_time_use": True, "requires_qr": False,
                          "requires_location": False, "requires_staff_validation": False,
                          "expiration_days": 30, "terms_url": None,
                          "odds_disclosure_text": "Odds vary. No purchase necessary.",
                          "no_purchase_necessary_text": "No purchase necessary to play or win.",
                          "age_restriction": None,
                          "geo_restrictions_json": {"allowed_countries": ["*"]}, "updated_at": n},
                 "$setOnInsert": {"_id": cid, "created_at": n}}, upsert=True)
            await db.game_compliance_settings.update_one(
                {"campaign_id": cid},
                {"$set": {"campaign_id": cid, "terms_text": "Standard FUUSIC game terms apply.",
                          "odds_disclosure": "Odds vary by prize inventory.",
                          "no_purchase_necessary_text": "No purchase necessary.",
                          "age_restriction": None,
                          "geo_restrictions_json": {"allowed_countries": ["*"]}, "updated_at": n},
                 "$setOnInsert": {"_id": cid, "created_at": n}}, upsert=True)
            created += 1
    return {"sample_games_created_or_updated": created}


async def seed_sample_customers_and_games(db, market: str = "Dubai") -> Dict[str, Any]:
    a = await seed_sample_storefronts(db, market)
    b = await seed_sample_games(db)
    c = await seed_demo_user_fixtures(db)
    return {**a, **b, **c}


async def seed_demo_user_fixtures(db) -> Dict[str, Any]:
    """Demo-friendly fixtures so the Membership Wallet + Ticket Scan screens
    show real content without a Stripe round-trip. Seeded for BOTH the mobile
    demo account and the web test account so each surface has data."""
    from datetime import timedelta
    out: List[str] = []
    # (email, code_prefix) — web uses test@ (cookie), mobile uses demo@ (bearer).
    for email, tag in (("demo@bigfm.dubai", "DEMO"), ("test@bigfm.dubai", "TEST")):
        u = await db.users.find_one({"email": email}, {"user_id": 1})
        if not u:
            continue
        uid = u["user_id"]
        for key, plan_id, biz in (
            ("ambreens", "mplan_sample_biz_sample_ambreens_glam", "biz_sample_ambreens"),
            ("coffee", "mplan_sample_biz_sample_funpizza_coffee", "biz_sample_funpizza"),
            ("pizza", "mplan_sample_biz_sample_funpizza_pizza", "biz_sample_funpizza"),
        ):
            mid = f"mbr_{tag.lower()}_{key}"
            await db.memberships.update_one(
                {"membership_id": mid},
                {"$set": {"membership_id": mid, "plan_id": plan_id, "business_id": biz,
                          "user_id": uid, "status": "active",
                          "stripe_subscription_id": f"sub_{mid}",
                          "current_period_end": now() + timedelta(days=30), "updated_at": now()},
                 "$setOnInsert": {"created_at": now()}}, upsert=True)
        # A ticketed event + scannable ticket under the user's own business.
        dp = await db.marketplace_profiles.find_one({"owner_user_id": uid}, {"business_id": 1, "public_name": 1})
        if dp:
            bid = dp["business_id"]
            eid = f"evt_{tag.lower()}_showcase"
            await db.events.update_one(
                {"event_id": eid},
                {"$set": {"event_id": eid, "business_id": bid, "sponsor_name": dp.get("public_name"),
                          "title": "FUUSIC Live Showcase", "description": "Demo event for ticket check-in.",
                          "location": "Main Stage", "starts_at": (now() + timedelta(days=7)).isoformat(),
                          "price_cents": 2500, "capacity": 200, "allow_points": True, "allow_card": True,
                          "points_per_dollar": 100, "active": True, "updated_at": now()},
                 "$setOnInsert": {"tickets_sold": 1, "created_at": now()}}, upsert=True)
            for code in (f"{tag}1234", f"{tag}5678"):
                await db.event_tickets.update_one(
                    {"code": code},
                    {"$set": {"code": code, "event_id": eid, "business_id": bid,
                              "event_title": "FUUSIC Live Showcase",
                              "starts_at": (now() + timedelta(days=7)).isoformat(),
                              "user_id": uid, "qty": 1, "method": "card", "status": "active"},
                     "$setOnInsert": {"ticket_id": f"tkt_{code.lower()}", "created_at": now()},
                     "$unset": {"checked_in_at": ""}}, upsert=True)
            out.append(f"{email}:{tag}1234")
    return {"demo_fixtures": out or "skipped_no_users"}
