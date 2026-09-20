"""Phase 3.7 — Brand phrase bank for natural-Hinglish RJ inspiration.

Seeded into the `rj_phrase_bank` Mongo collection. Categorised by
(market, daypart, category). The Naturalness Rewriter samples 2-4
underused phrases as inspiration; the LLM then writes its own line
in the same voice without verbatim copying.

Each phrase tracks `used_count` so we can prefer fresh material.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger("bigfm.phrase_bank")


# (market, daypart, category, phrase, language, voice_tone)
PHRASE_SEED: List[tuple] = [
    # ===== DFW market =====
    ("dfw", "morning_drive", "opener",      "DFW, good morning! Chaliye din ki shuruaat thodi energy ke saath.", "hinglish", "morning_drive"),
    ("dfw", "morning_drive", "traffic",     "Traffic slow ho sakta hai, but mood slow nahi hone denge.", "hinglish", "morning_drive"),
    ("dfw", "morning_drive", "lifestyle",   "Coffee ready? Playlist bhi ready hai.", "hinglish", "morning_drive"),
    ("dfw", "morning_drive", "weather",     "Texas ki subah crisp hai, AC chalao ya khidki khol do — your call.", "hinglish", "morning_drive"),
    ("dfw", "morning_drive", "opener",      "Frisco se Plano tak, hum hain saath aapke.", "hinglish", "morning_drive"),

    ("dfw", "lunch_rush", "opener",         "Lunch ka time ho gaya hai, aur deals bhi garam hain.", "hinglish", "lunch"),
    ("dfw", "lunch_rush", "sponsor_lead",   "Aap route pe ho, aur ek solid food stop nearby hai.", "hinglish", "lunch"),
    ("dfw", "lunch_rush", "playful",        "Spin karo, shayad dessert free mil jaaye.", "hinglish", "lunch"),
    ("dfw", "lunch_rush", "opener",         "Office se nikalne se pehle, ek quick break — DFW lunch energy.", "hinglish", "lunch"),
    ("dfw", "lunch_rush", "sponsor_lead",   "Biryani ka craving? Jay Bhavani, Tarka, ya humble Irving stop — your call.", "hinglish", "lunch"),

    ("dfw", "evening_drive", "opener",      "Workday almost done, ab drive ko thoda filmy banate hain.", "hinglish", "evening_drive"),
    ("dfw", "evening_drive", "traffic",     "Traffic ka tension side pe, music ka volume thoda up.", "hinglish", "evening_drive"),
    ("dfw", "evening_drive", "lifestyle",   "Dinner plans pending hain? Mere paas kuch options hain.", "hinglish", "evening_drive"),
    ("dfw", "evening_drive", "opener",      "DFW drive-time — let's make it cinematic.", "hinglish", "evening_drive"),

    ("dfw", "nightlife_mode", "opener",     "Friday night ka scene set hai.", "hinglish", "nightlife"),
    ("dfw", "nightlife_mode", "hype",       "Party mode on, DFW.", "hinglish", "nightlife"),
    ("dfw", "nightlife_mode", "music_intro","Club energy, Bollywood flavor, aur thoda surprise coming up.", "hinglish", "nightlife"),
    ("dfw", "nightlife_mode", "hype",       "Frisco, Plano, Irving — sab ki energy chahiye yahan.", "hinglish", "nightlife"),

    ("dfw", "overnight_lounge", "opener",   "Late night crew, this one is for you.", "hinglish", "chill_late_night"),
    ("dfw", "overnight_lounge", "lifestyle","Drive safe, mood soft, aur music smooth.", "hinglish", "chill_late_night"),
    ("dfw", "overnight_lounge", "companion","Raat lambi hai, company hum denge.", "hinglish", "chill_late_night"),

    ("dfw", "talk_dayparts", "news_lead",   "DFW desi community ke liye aaj ki key story.", "hinglish", "talk_news"),
    ("dfw", "talk_dayparts", "transition",  "Ek baat soch ke dekhiye, aur phir music wapas aata hai.", "hinglish", "talk_news"),

    # ===== Dubai market =====
    ("dubai", "morning_drive", "opener",    "Dubai, good morning — Sheikh Zayed pe traffic light hai, vibe heavy.", "hinglish", "morning_drive"),
    ("dubai", "morning_drive", "weather",   "Gulf ki subah aaj soft hai, AC thoda kam karo.", "hinglish", "morning_drive"),
    ("dubai", "morning_drive", "lifestyle", "Karak chai ready? Hum playlist sambhal lete hain.", "hinglish", "morning_drive"),

    ("dubai", "lunch_rush", "opener",       "Lunch break time, Business Bay se Karama tak.", "hinglish", "lunch"),
    ("dubai", "lunch_rush", "sponsor_lead", "Aap route pe ho aur Ravi's biryani bus 10 minute door hai.", "hinglish", "lunch"),

    ("dubai", "evening_drive", "opener",    "Workday khatam, ab Marina ki taraf chalte hain.", "hinglish", "evening_drive"),
    ("dubai", "evening_drive", "traffic",   "Sheikh Zayed pe traffic build up — music ka volume up.", "hinglish", "evening_drive"),

    ("dubai", "nightlife_mode", "opener",   "Friday night Dubai mein. Scene ready hai.", "hinglish", "nightlife"),
    ("dubai", "nightlife_mode", "hype",     "JBR ki energy, Karama ka heart, sab yahan FUUSIC par.", "hinglish", "nightlife"),
    ("dubai", "nightlife_mode", "music_intro","Bollywood beats, Punjabi flavor, coming up.", "hinglish", "nightlife"),

    ("dubai", "overnight_lounge", "opener", "Dubai ki raat, FUUSIC par, dheere se.", "hinglish", "chill_late_night"),
    ("dubai", "overnight_lounge", "companion","Drive safe, music smooth — late-night company.", "hinglish", "chill_late_night"),
]


async def ensure_phrase_bank_indexes(db) -> None:
    await db.rj_phrase_bank.create_index([("market", 1), ("daypart_slug", 1), ("category", 1)])
    await db.rj_phrase_bank.create_index([("market", 1), ("voice_tone", 1)])


async def seed_phrase_bank(db) -> int:
    """Idempotently seed phrases. Skips entries that already exist verbatim."""
    created = 0
    now = datetime.now(timezone.utc)
    for market, daypart, category, phrase, language, voice_tone in PHRASE_SEED:
        existing = await db.rj_phrase_bank.find_one(
            {"market": market, "daypart_slug": daypart, "phrase": phrase},
            {"_id": 1},
        )
        if existing:
            continue
        await db.rj_phrase_bank.insert_one({
            "market": market,
            "daypart_slug": daypart,
            "category": category,
            "phrase": phrase,
            "language": language,
            "voice_tone": voice_tone,
            "used_count": 0,
            "active": True,
            "created_at": now,
        })
        created += 1
    logger.info(f"Phrase bank seeded (created {created}, total entries {len(PHRASE_SEED)})")
    return created


async def sample_phrases(db, *, market: str, daypart: str, n: int = 4) -> List[dict]:
    """Pick the N least-used phrases for the given market+daypart. The
    Naturalness Rewriter passes these as inspiration; the LLM does NOT copy
    them verbatim but uses them to seed style + cadence."""
    cur = db.rj_phrase_bank.find(
        {"market": market, "daypart_slug": daypart, "active": True},
        {"_id": 1, "phrase": 1, "category": 1, "used_count": 1},
    ).sort("used_count", 1).limit(n * 2)  # buffer for some randomness
    rows = [d async for d in cur]
    if len(rows) <= n:
        return rows
    import random
    return random.sample(rows, n)


async def mark_phrases_used(db, ids: List) -> None:
    if not ids:
        return
    await db.rj_phrase_bank.update_many(
        {"_id": {"$in": ids}},
        {"$inc": {"used_count": 1}},
    )
