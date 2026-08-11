"""Radio station policy + AI genre backfill.

  • Dubai policy: in Dubai only the BigFM-family flagship stations are shown;
    every other Dubai/UAE station is deactivated (hidden everywhere).
  • Music genre: each branded channel + allowlisted Dubai station gets a
    `music_genre` label, auto-inferred by the LLM from its name/tags.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# The only Dubai/UAE stations allowed to appear (by flagship_slug):
# BigFM, TalkFM, Luv FM, Beat FM, Big Melodies, Chilled Luv, Luv Legends, Urban Beat.
DUBAI_ALLOWLIST_SLUGS = [
    "big-1062-uae", "talk-1003-uae", "luv-1071-uae", "beat-978-uae",
    "big-melodies", "chilled-luv", "luv-legends", "urban-beat",
]

_DUBAI_MATCH = {"$or": [{"city": {"$regex": "dubai", "$options": "i"}}, {"country_code": "AE"}]}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def apply_dubai_station_policy(db) -> Dict[str, Any]:
    """Hide every Dubai/UAE station that is not on the allowlist; keep the 8."""
    hide = await db.imported_radio_stations.update_many(
        {"$and": [_DUBAI_MATCH, {"flagship_slug": {"$nin": DUBAI_ALLOWLIST_SLUGS}}]},
        {"$set": {"active": False, "dubai_hidden": True, "is_flagship": False,
                  "is_priority": False, "updated_at": _now()}})
    keep = await db.imported_radio_stations.update_many(
        {"flagship_slug": {"$in": DUBAI_ALLOWLIST_SLUGS}},
        {"$set": {"active": True, "dubai_hidden": False, "updated_at": _now()}})
    return {"dubai_hidden": hide.modified_count, "dubai_kept": keep.modified_count}


_FALLBACK_MAP = {
    "south_asian": "Bollywood", "bollywood": "Bollywood", "talk": "Talk Radio",
    "news": "News", "pop": "Pop", "hip_hop": "Hip Hop", "dance": "Dance",
    "chill": "Chill", "electronic": "Electronic", "punjabi_pop": "Punjabi",
    "devotional": "Devotional", "retro": "Retro", "sufi": "Sufi",
}


def _fallback_genre(tags: Optional[List[str]]) -> str:
    tags = [t for t in (tags or []) if t not in ("home", "music")]
    for t in tags:
        if t in _FALLBACK_MAP:
            return _FALLBACK_MAP[t]
    return tags[0].replace("_", " ").title() if tags else "Music"


async def _infer_genre(key: Optional[str], name: str, tags: List[str], desc: Optional[str]) -> str:
    fallback = _fallback_genre(tags)
    if not key:
        return fallback
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=key, session_id="radio-genre-backfill",
            system_message=(
                "You are a radio music-genre classifier. Given a station's name, tags and description, "
                "reply with exactly ONE concise music genre label in Title Case (1-3 words) that best "
                "fits the station's music. Examples: Bollywood, Pop, Hip Hop, Electronic, Talk Radio, "
                "Devotional, Retro, Punjabi, Chill. Reply with ONLY the label, no punctuation."),
        ).with_model("openai", "gpt-5.4-mini")
        prompt = f"Station: {name}\nTags: {', '.join(tags) if tags else 'none'}\nDescription: {desc or 'none'}\nGenre:"
        resp = await chat.send_message(UserMessage(text=prompt))
        label = str(resp or "").strip().split("\n")[0].strip().strip('."\'')
        if label and len(label) <= 30:
            return label
    except Exception as e:  # noqa: BLE001
        logger.warning("genre infer failed for %s: %s", name, e)
    return fallback


async def backfill_station_genres(db) -> Dict[str, Any]:
    """Fill `music_genre` (LLM) for branded channels + allowlisted Dubai stations. Idempotent."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    missing = {"$or": [{"music_genre": {"$exists": False}}, {"music_genre": None}, {"music_genre": ""}]}
    filled = 0
    async for ch in db.channels.find(missing):
        g = await _infer_genre(key, ch.get("name", ""), ch.get("allowed_genres") or [],
                               ch.get("tagline") or ch.get("description"))
        await db.channels.update_one({"_id": ch["_id"]}, {"$set": {"music_genre": g, "updated_at": _now()}})
        filled += 1
    async for s in db.imported_radio_stations.find(
            {"$and": [{"flagship_slug": {"$in": DUBAI_ALLOWLIST_SLUGS}}, missing]}):
        g = await _infer_genre(key, s.get("name", ""), s.get("tags_json") or [], s.get("description"))
        await db.imported_radio_stations.update_one({"_id": s["_id"]}, {"$set": {"music_genre": g, "updated_at": _now()}})
        filled += 1
    logger.info("Radio genre backfill: filled %s stations", filled)
    return {"genres_filled": filled}
