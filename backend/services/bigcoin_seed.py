"""Phase 5 — Seed data for BigCoin rewards, badges, lyric puzzles, games."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("bigfm.bigcoin.seed")


# ---------------------------------------------------------------
LAUNCH_REWARDS = [
    {"_id": "rwd_1mo_premium", "name": "1 Month Premium",
     "description": "Unlock all Premium perks for 30 days: 6 skips/hour, 2 VIP channels, ad-free.",
     "cost_bigcoin": 500, "type": "premium_days",
     "payload_json": {"days": 30},
     "stock_limit": None, "image_url": "/assets/rewards/premium_1mo.svg",
     "category": "premium"},
    {"_id": "rwd_adfree_hour", "name": "1 Hour Ad-Free",
     "description": "Block ad breaks for 60 minutes. Listen uninterrupted.",
     "cost_bigcoin": 200, "type": "adfree_hour",
     "payload_json": {"hours": 1},
     "stock_limit": None, "image_url": "/assets/rewards/adfree.svg",
     "category": "premium"},
    {"_id": "rwd_karak_voucher", "name": "Karak Cafe — 10% off",
     "description": "Use at any Karak Cafe in Dubai. Valid 30 days.",
     "cost_bigcoin": 100, "type": "partner_voucher",
     "payload_json": {"discount_pct": 10, "merchant": "Karak Cafe"},
     "partner_business_id": "biz_karak_cafe_karama",
     "stock_limit": 500, "image_url": "/assets/rewards/karak.svg",
     "category": "partner"},
    {"_id": "rwd_raffle_iphone", "name": "Monthly Raffle — iPhone 17",
     "description": "Entry into the monthly grand prize draw. Drawn end of month.",
     "cost_bigcoin": 50, "type": "raffle",
     "payload_json": {"raffle_id": "iphone17_monthly"},
     "stock_limit": None, "image_url": "/assets/rewards/raffle.svg",
     "category": "raffle"},
    {"_id": "rwd_sticker_pack", "name": "FUUSIC Sticker Pack",
     "description": "Limited-edition holographic stickers. Shipped free.",
     "cost_bigcoin": 250, "type": "coupon",
     "payload_json": {"sku": "BIGFM-STICKER-V1"},
     "stock_limit": 100, "image_url": "/assets/rewards/stickers.svg",
     "category": "merch"},
    {"_id": "rwd_mehfil_badge", "name": "Mehfil VIP Badge",
     "description": "Profile badge — exclusive to listeners who've put in serious hours.",
     "cost_bigcoin": 1000, "type": "badge",
     "payload_json": {"badge_slug": "mehfil_vip"},
     "stock_limit": None, "image_url": "/assets/rewards/vip_badge.svg",
     "category": "badge"},
    {"_id": "rwd_funasia_ticket", "name": "Funasia Cinemas — 1 Free Ticket",
     "description": "Any movie, any showing. Redeem at the box office.",
     "cost_bigcoin": 800, "type": "partner_voucher",
     "payload_json": {"merchant": "Funasia Cinemas DFW"},
     "partner_business_id": "biz_funasia_cinema",
     "stock_limit": 50, "image_url": "/assets/rewards/funasia.svg",
     "category": "partner"},
    {"_id": "rwd_spotify_50", "name": "Spotify Gift Card — ₹50",
     "description": "Add ₹50 to any Spotify account. Code emailed after redemption.",
     "cost_bigcoin": 400, "type": "coupon",
     "payload_json": {"vendor": "spotify", "value_cents": 5000, "currency": "INR"},
     "stock_limit": 200, "image_url": "/assets/rewards/spotify.svg",
     "category": "gift_card"},
]

LAUNCH_BADGES = [
    {"_id": "badge_first_listen", "slug": "first_listen", "name": "First Listen",
     "description": "Played your first song on FUUSIC.",
     "icon": "🎧", "tier": "common",
     "unlock_rule_json": {"type": "first_listen"}, "sort_order": 1},
    {"_id": "badge_10_hours", "slug": "10_hours", "name": "10 Hours In",
     "description": "10 hours of total listening.",
     "icon": "⏱️", "tier": "common",
     "unlock_rule_json": {"type": "listening_hours", "value": 10}, "sort_order": 2},
    {"_id": "badge_50_hours", "slug": "50_hours", "name": "50 Hours Strong",
     "description": "50 hours of total listening.",
     "icon": "🔥", "tier": "rare",
     "unlock_rule_json": {"type": "listening_hours", "value": 50}, "sort_order": 3},
    {"_id": "badge_100_hours", "slug": "100_hours", "name": "Centurion",
     "description": "100 hours of total listening.",
     "icon": "💯", "tier": "epic",
     "unlock_rule_json": {"type": "listening_hours", "value": 100}, "sort_order": 4},
    {"_id": "badge_streak_30", "slug": "streak_30", "name": "30-Day Streak",
     "description": "Logged in 30 days in a row.",
     "icon": "🗓️", "tier": "epic",
     "unlock_rule_json": {"type": "streak_days", "value": 30}, "sort_order": 5},
    {"_id": "badge_friday_regular", "slug": "friday_regular",
     "name": "Friday Night Regular",
     "description": "Listened on 4 Fridays.",
     "icon": "🌃", "tier": "rare",
     "unlock_rule_json": {"type": "consecutive_friday_nightlife", "value": 4},
     "sort_order": 6},
    {"_id": "badge_mirchi_loyalist", "slug": "mirchi_loyalist",
     "name": "Party Dubai Loyalist",
     "description": "10+ hours on Party Dubai channel.",
     "icon": "🪩", "tier": "rare",
     "unlock_rule_json": {"type": "channel_listening_hours",
                            "channel": "party_dubai", "value": 10},
     "sort_order": 7},
    {"_id": "badge_bigcoin_tycoon", "slug": "bigcoin_tycoon",
     "name": "BigCoin Tycoon",
     "description": "Earned 10,000 lifetime BigCoin.",
     "icon": "💰", "tier": "legendary",
     "unlock_rule_json": {"type": "lifetime_bigcoin", "value": 10000},
     "sort_order": 8},
    {"_id": "badge_game_master", "slug": "game_master", "name": "Game Master",
     "description": "Played 50 games.",
     "icon": "🎮", "tier": "epic",
     "unlock_rule_json": {"type": "game_plays", "value": 50}, "sort_order": 9},
    {"_id": "badge_refer_1", "slug": "refer_1", "name": "First Referral",
     "description": "Brought 1 friend to FUUSIC.",
     "icon": "✉️", "tier": "common",
     "unlock_rule_json": {"type": "successful_referrals", "value": 1},
     "sort_order": 10},
    {"_id": "badge_refer_5", "slug": "refer_5", "name": "Referral Hero",
     "description": "Brought 5 friends to FUUSIC.",
     "icon": "🤝", "tier": "rare",
     "unlock_rule_json": {"type": "successful_referrals", "value": 5},
     "sort_order": 11},
    {"_id": "badge_refer_10", "slug": "refer_10", "name": "Squad Builder",
     "description": "Brought 10 friends to FUUSIC.",
     "icon": "👥", "tier": "epic",
     "unlock_rule_json": {"type": "successful_referrals", "value": 10},
     "sort_order": 12},
    {"_id": "badge_coupon_collector", "slug": "coupon_collector",
     "name": "Coupon Collector",
     "description": "Saved 10+ coupons.",
     "icon": "🎟️", "tier": "common",
     "unlock_rule_json": {"type": "coupon_saves", "value": 10},
     "sort_order": 13},
]

# ---------------------------------------------------------------
LYRIC_PUZZLES = [
    {"_id": "lp_tum_hi_ho", "song": "Tum Hi Ho", "artist": "Arijit Singh",
     "language": "hindi", "first_half": "Hum tere bin ab reh nahi sakte",
     "next_phrase": "Tere bina kya wajood mera"},
    {"_id": "lp_kuch_kuch", "song": "Kuch Kuch Hota Hai", "artist": "Udit Narayan",
     "language": "hindi", "first_half": "Kuch kuch hota hai",
     "next_phrase": "Tum nahi samjhoge"},
    {"_id": "lp_tujh_mein", "song": "Tujh Mein Rab Dikhta Hai",
     "artist": "Roop Kumar Rathod", "language": "hindi",
     "first_half": "Tujh mein rab dikhta hai", "next_phrase": "Yaara main kya karoon"},
    {"_id": "lp_shape_of_you", "song": "Shape of You", "artist": "Ed Sheeran",
     "language": "english", "first_half": "I'm in love with the shape of you",
     "next_phrase": "We push and pull like a magnet do"},
    {"_id": "lp_blinding_lights", "song": "Blinding Lights", "artist": "The Weeknd",
     "language": "english", "first_half": "I've been tryna call",
     "next_phrase": "I've been on my own for long enough"},
    {"_id": "lp_levitating", "song": "Levitating", "artist": "Dua Lipa",
     "language": "english", "first_half": "If you wanna run away with me",
     "next_phrase": "I know a galaxy and I can take you for a ride"},
    {"_id": "lp_kesariya", "song": "Kesariya", "artist": "Arijit Singh",
     "language": "hindi", "first_half": "Kesariya tera ishq hai piya",
     "next_phrase": "Rang jaaun jo main haath laga"},
    {"_id": "lp_galliyan", "song": "Galliyan", "artist": "Ankit Tiwari",
     "language": "hindi", "first_half": "Teri galliyan, gali galliyan",
     "next_phrase": "Teri galliyan, mujhko bhaavein galliyan teri"},
    {"_id": "lp_perfect", "song": "Perfect", "artist": "Ed Sheeran",
     "language": "english", "first_half": "I found a love for me",
     "next_phrase": "Darling, just dive right in and follow my lead"},
    {"_id": "lp_chaiyya", "song": "Chaiyya Chaiyya", "artist": "Sukhwinder Singh",
     "language": "hindi", "first_half": "Chal chaiyya chaiyya",
     "next_phrase": "Chaiyya chaiyya chaiyya chaiyya"},
    {"_id": "lp_jai_ho", "song": "Jai Ho", "artist": "A.R. Rahman",
     "language": "hindi", "first_half": "Aaja aaja jind shamiyaane ke tale",
     "next_phrase": "Aaja zariwaale neele aasmaan ke tale"},
    {"_id": "lp_tera_ban_jaunga", "song": "Tera Ban Jaunga", "artist": "Akhil Sachdeva",
     "language": "hindi", "first_half": "Mujhe ishq se inkaar nahin",
     "next_phrase": "Tera ban jaunga"},
    {"_id": "lp_uptown_funk", "song": "Uptown Funk", "artist": "Bruno Mars",
     "language": "english", "first_half": "Don't believe me, just watch",
     "next_phrase": "Hot damn"},
    {"_id": "lp_thinking_out_loud", "song": "Thinking Out Loud", "artist": "Ed Sheeran",
     "language": "english", "first_half": "Take me into your loving arms",
     "next_phrase": "Kiss me under the light of a thousand stars"},
    {"_id": "lp_someone_like_you", "song": "Someone Like You", "artist": "Adele",
     "language": "english", "first_half": "Never mind I'll find someone like you",
     "next_phrase": "I wish nothing but the best for you"},
    {"_id": "lp_rolling_deep", "song": "Rolling in the Deep", "artist": "Adele",
     "language": "english", "first_half": "We could have had it all",
     "next_phrase": "Rolling in the deep"},
    {"_id": "lp_pasoori", "song": "Pasoori", "artist": "Ali Sethi & Shae Gill",
     "language": "punjabi", "first_half": "Aag laavaan teriyan majbooriyan nu",
     "next_phrase": "Door reh ke vi tu nede aaja sajna"},
    {"_id": "lp_butta_bomma", "song": "Butta Bomma", "artist": "Armaan Malik",
     "language": "telugu", "first_half": "Butta Bomma Butta Bomma",
     "next_phrase": "Yekkadunnave"},
    {"_id": "lp_rockstar", "song": "Rockstar", "artist": "Post Malone",
     "language": "english", "first_half": "I've been fuckin' hoes and poppin' pillies",
     "next_phrase": "Man, I feel just like a rockstar"},
    {"_id": "lp_apna_time_aayega", "song": "Apna Time Aayega", "artist": "DIVINE",
     "language": "hindi", "first_half": "Tu nanga hi toh aaya hai",
     "next_phrase": "Kya ghanta lekar jayega"},
]


GAMES = [
    {"_id": "spin_win", "slug": "spin_win", "type": "spin_wheel",
     "title": "Spin & Win", "icon": "🎡",
     "description": "Spin once every 4 hours. Win BigCoin or coupons.",
     "rules_json": {"cooldown_sec": 14400},
     "reward_pool_json": None,  # uses DEFAULT_SPIN_POOL
     "cooldown_sec": 14400, "min_bigcoin_to_play": 0,
     "daypart_restrictions": None, "market_restrictions": None,
     "sponsor_business_id": None, "active": True, "plays_count": 0},
    {"_id": "game_trivia", "slug": "music_trivia", "type": "trivia",
     "title": "Music Trivia", "icon": "🎶",
     "description": "3 questions a day. Get them right, earn BigCoin.",
     "rules_json": {"daily_limit": 3, "timer_sec": 10},
     "reward_pool_json": None,
     "cooldown_sec": 0, "min_bigcoin_to_play": 0,
     "active": True, "plays_count": 0},
    {"_id": "game_lyric", "slug": "complete_lyric", "type": "complete_lyric",
     "title": "Complete the Lyric", "icon": "🎤",
     "description": "Fill in the missing line. Bollywood, English, Punjabi, Telugu.",
     "rules_json": {"daily_limit": 3},
     "reward_pool_json": None,
     "cooldown_sec": 0, "min_bigcoin_to_play": 0,
     "active": True, "plays_count": 0},
]


# ---------------------------------------------------------------
async def seed_phase5(db) -> dict:
    """Idempotent — upsert all launch data."""
    now = datetime.now(timezone.utc)
    rewards_created = 0
    for r in LAUNCH_REWARDS:
        res = await db.bigcoin_rewards.update_one(
            {"_id": r["_id"]},
            {"$setOnInsert": {**r, "active": True, "redeemed_count": 0,
                                "expires_at": None, "created_at": now}},
            upsert=True,
        )
        if res.upserted_id is not None:
            rewards_created += 1
    badges_created = 0
    for b in LAUNCH_BADGES:
        res = await db.badges.update_one(
            {"_id": b["_id"]},
            {"$setOnInsert": {**b, "active": True,
                                "market": None, "created_at": now}},
            upsert=True,
        )
        if res.upserted_id is not None:
            badges_created += 1
    lyrics_created = 0
    for lp in LYRIC_PUZZLES:
        res = await db.lyric_puzzles.update_one(
            {"_id": lp["_id"]},
            {"$setOnInsert": {**lp, "active": True, "created_at": now}},
            upsert=True,
        )
        if res.upserted_id is not None:
            lyrics_created += 1
    games_created = 0
    for g in GAMES:
        res = await db.games.update_one(
            {"_id": g["_id"]},
            {"$setOnInsert": {**g, "created_at": now}},
            upsert=True,
        )
        if res.upserted_id is not None:
            games_created += 1
    return {
        "rewards_created": rewards_created,
        "badges_created": badges_created,
        "lyrics_created": lyrics_created,
        "games_created": games_created,
    }
