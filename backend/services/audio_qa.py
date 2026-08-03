"""Phase 3.7 — Per-segment RJ audio QA storage + admin queries."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from core.db import db

logger = logging.getLogger("bigfm.audio_qa")


async def ensure_audio_qa_indexes() -> None:
    await db.rj_audio_qa.create_index("segment_id", unique=True)
    await db.rj_audio_qa.create_index([("created_at", -1)])
    await db.rj_audio_qa.create_index([("channel_slug", 1), ("created_at", -1)])
    await db.rj_audio_qa.create_index([("personality_profile_slug", 1), ("created_at", -1)])
    await db.rj_audio_qa.create_index("is_winning_take")


async def record_audio_qa(*, segment_id: str, voice_key: str, model_id: str,
                           voice_settings: dict, initial_script: str,
                           rewritten_script: str, final_audio_url: str,
                           final_duration_sec: float, personality_profile_slug: str,
                           daypart_slug: str, channel_slug: str, market: str,
                           takes_generated: int = 1, regen_count: int = 0,
                           banned_phrase_hits: Optional[List[str]] = None,
                           hosts: Optional[list] = None,
                           format: str = "solo") -> None:
    now = datetime.now(timezone.utc)
    doc = {
        "segment_id": segment_id,
        "voice_key": voice_key,
        "model_id": model_id,
        "voice_settings": voice_settings or {},
        "initial_script": initial_script,
        "rewritten_script": rewritten_script,
        "final_audio_url": final_audio_url,
        "final_duration_sec": float(final_duration_sec),
        "personality_profile_slug": personality_profile_slug,
        "daypart_slug": daypart_slug,
        "channel_slug": channel_slug,
        "market": market,
        "takes_generated": int(takes_generated),
        "regen_count": int(regen_count),
        "banned_phrase_hits": banned_phrase_hits or [],
        "format": format,
        "hosts": hosts or [],
        "user_ratings": [],
        "admin_ratings": [],
        "is_winning_take": False,
        "saved_as_template": False,
        "created_at": now,
    }
    try:
        await db.rj_audio_qa.update_one(
            {"segment_id": segment_id},
            {"$setOnInsert": doc},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"record_audio_qa failed for segment {segment_id}: {e}")


async def list_recent_qa(*, limit: int = 50, channel_slug: Optional[str] = None,
                           market: Optional[str] = None,
                           profile_slug: Optional[str] = None) -> List[dict]:
    q: dict = {}
    if channel_slug: q["channel_slug"] = channel_slug
    if market:       q["market"] = market
    if profile_slug: q["personality_profile_slug"] = profile_slug
    cur = db.rj_audio_qa.find(q, {"_id": 0}).sort("created_at", -1).limit(int(limit))
    return [d async for d in cur]


async def add_admin_rating(*, segment_id: str, admin_id: str,
                            naturalness_1_5: int, hinglish_quality_1_5: int,
                            radio_energy_1_5: int, notes: str = "") -> bool:
    res = await db.rj_audio_qa.update_one(
        {"segment_id": segment_id},
        {"$push": {"admin_ratings": {
            "admin_id": admin_id,
            "naturalness_1_5": int(naturalness_1_5),
            "hinglish_quality_1_5": int(hinglish_quality_1_5),
            "radio_energy_1_5": int(radio_energy_1_5),
            "notes": notes,
            "created_at": datetime.now(timezone.utc),
        }}},
    )
    return res.matched_count == 1


async def set_winning_take(segment_id: str, winning: bool) -> bool:
    res = await db.rj_audio_qa.update_one(
        {"segment_id": segment_id},
        {"$set": {"is_winning_take": bool(winning)}},
    )
    return res.matched_count == 1


async def common_issues_summary(*, hours: int = 24) -> List[dict]:
    """Aggregate banned phrase hits in the last N hours."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff},
                    "banned_phrase_hits": {"$ne": []}}},
        {"$unwind": "$banned_phrase_hits"},
        {"$group": {"_id": "$banned_phrase_hits", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    out = []
    async for d in db.rj_audio_qa.aggregate(pipeline):
        out.append({"phrase": d["_id"], "count": d["count"]})
    return out


async def top_rated_voices(*, limit: int = 8) -> List[dict]:
    """Average admin naturalness rating per voice_key."""
    pipeline = [
        {"$match": {"admin_ratings.0": {"$exists": True}}},
        {"$unwind": "$admin_ratings"},
        {"$group": {
            "_id": "$voice_key",
            "avg_naturalness": {"$avg": "$admin_ratings.naturalness_1_5"},
            "avg_hinglish":    {"$avg": "$admin_ratings.hinglish_quality_1_5"},
            "avg_energy":      {"$avg": "$admin_ratings.radio_energy_1_5"},
            "rating_count":    {"$sum": 1},
        }},
        {"$sort": {"avg_naturalness": -1}},
        {"$limit": int(limit)},
    ]
    out = []
    async for d in db.rj_audio_qa.aggregate(pipeline):
        out.append({
            "voice_key": d["_id"],
            "avg_naturalness": round(d["avg_naturalness"], 2),
            "avg_hinglish":    round(d["avg_hinglish"], 2),
            "avg_energy":      round(d["avg_energy"], 2),
            "rating_count":    d["rating_count"],
        })
    return out
