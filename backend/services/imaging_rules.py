"""Phase 3.8 — Imaging rules engine.

Picks the right imaging asset (station ID / daypart opener / sweeper / music
bed / sponsor / game) for the current segment, while enforcing rotation
(no repeat of the same asset within a 4-hour window per user).

Public surface:
- pick_station_id(db, station_slug, user_id, length="short") → asset dict or None
- pick_daypart_opener(db, station_slug, daypart, user_id) → asset dict or None
- pick_top_of_hour(db, station_slug, user_id) → asset dict or None
- pick_sponsor_bumper(db, station_slug, user_id) → asset dict or None
- pick_game_stinger(db, station_slug, user_id, kind="game") → asset dict or None
- pick_sweeper(db, station_slug, user_id, energy="medium") → asset dict or None
- pick_music_bed(db, station_slug, energy="medium") → asset dict or None
- log_imaging_play(db, user_id, session_id, asset, transition_type) → write station_flow_logs row
- should_play_station_id_now(db, session_id, listening_seconds) → bool (15-20min cadence)
- station_slug_for_market(market) → str

Picks the LEAST-RECENTLY-PLAYED active asset that has a generated file, with
random tiebreaker. Rotation tracking uses `station_flow_logs`.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigfm.imaging_rules")

# 4-hour anti-repeat window per user
ROTATION_WINDOW = timedelta(hours=4)

# Station ID cadence: between 15 and 20 minutes of listening
STATION_ID_CADENCE_MIN_SEC = 15 * 60
STATION_ID_CADENCE_MAX_SEC = 20 * 60


def station_slug_for_market(market: Optional[str]) -> str:
    m = (market or "dubai").lower()
    if m == "dfw":
        return "funasia_dfw"
    return "bigfm_dubai"


async def _recent_played_ids(db, user_id: Optional[str], asset_type: str) -> set:
    """Return set of imaging_asset_ids the user has heard in the last 4h."""
    if not user_id:
        return set()
    since = datetime.now(timezone.utc) - ROTATION_WINDOW
    cursor = db.station_flow_logs.find(
        {"user_id": user_id, "asset_type": asset_type, "played_at": {"$gte": since}},
        {"asset_id": 1, "_id": 0},
    )
    return {d["asset_id"] async for d in cursor}


async def _pick_one(db, *, station_slug: str, asset_type: str,
                    user_id: Optional[str], extra: Optional[dict] = None) -> Optional[dict]:
    """Pick one active asset of the given type that has a generated file and
    hasn't been heard by this user in the last 4h. Random tiebreaker."""
    q = {"station_slug": station_slug, "asset_type": asset_type,
         "active": True, "generation_status": "ready"}
    if extra:
        q.update(extra)
    candidates = await db.imaging_assets.find(q).to_list(length=200)
    if not candidates:
        return None
    recent = await _recent_played_ids(db, user_id, asset_type)
    fresh = [c for c in candidates if str(c.get("_id")) not in recent]
    pool = fresh or candidates  # fall back to repeat if everything's been played
    # weight-based pick
    weights = [max(0.1, float(c.get("weight", 1.0))) for c in pool]
    return random.choices(pool, weights=weights, k=1)[0]


async def pick_station_id(db, *, station_slug: str, user_id: Optional[str],
                          length: str = "short") -> Optional[dict]:
    asset_type = "brand_id_short" if length == "short" else "brand_id_long"
    return await _pick_one(db, station_slug=station_slug, asset_type=asset_type, user_id=user_id)


async def pick_daypart_opener(db, *, station_slug: str, daypart: str,
                              user_id: Optional[str]) -> Optional[dict]:
    return await _pick_one(db, station_slug=station_slug, asset_type="daypart_opener",
                            user_id=user_id, extra={"daypart": daypart})


async def pick_top_of_hour(db, *, station_slug: str, user_id: Optional[str]) -> Optional[dict]:
    return await _pick_one(db, station_slug=station_slug, asset_type="top_of_hour", user_id=user_id)


async def pick_sponsor_bumper(db, *, station_slug: str, user_id: Optional[str]) -> Optional[dict]:
    return await _pick_one(db, station_slug=station_slug, asset_type="sponsor_bumper", user_id=user_id)


async def pick_game_stinger(db, *, station_slug: str, user_id: Optional[str],
                            kind: str = "game") -> Optional[dict]:
    asset_type = "winner_stinger" if kind == "winner" else "game_stinger"
    return await _pick_one(db, station_slug=station_slug, asset_type=asset_type, user_id=user_id)


async def pick_sweeper(db, *, station_slug: str, user_id: Optional[str],
                       energy: str = "medium") -> Optional[dict]:
    return await _pick_one(db, station_slug=station_slug, asset_type="sweeper_short", user_id=user_id)


async def pick_music_bed(db, *, station_slug: str, energy: str = "medium") -> Optional[dict]:
    """Music bed picked by energy, NOT user-rotation-aware (beds repeat naturally)."""
    # map session energy to bed energy
    energy_map = {"chill": "chill", "low": "chill", "medium": "medium",
                  "uplifting": "uplifting", "high": "uplifting", "party": "energetic"}
    bed_energy = energy_map.get(energy or "medium", "medium")
    docs = await db.imaging_assets.find(
        {"station_slug": station_slug, "asset_type": "music_bed",
         "active": True, "generation_status": "ready",
         "energy": bed_energy},
    ).to_list(length=10)
    if not docs:
        # fall back to ANY ready bed for that station
        docs = await db.imaging_assets.find(
            {"station_slug": station_slug, "asset_type": "music_bed",
             "active": True, "generation_status": "ready"},
        ).to_list(length=10)
    if not docs:
        return None
    return random.choice(docs)


async def log_imaging_play(db, *, user_id: Optional[str], session_id: Optional[str],
                            asset: dict, transition_type: str) -> None:
    """Insert a station_flow_logs row recording one imaging insertion."""
    try:
        await db.station_flow_logs.insert_one({
            "user_id": user_id,
            "session_id": session_id,
            "asset_id": str(asset.get("_id")),
            "asset_type": asset.get("asset_type"),
            "asset_slug": asset.get("slug"),
            "station_slug": asset.get("station_slug"),
            "transition_type": transition_type,
            "loudness_lufs": asset.get("loudness_lufs"),
            "duration_sec": float(asset.get("duration_sec") or 0.0),
            "played_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.warning(f"log_imaging_play error: {e}")


def should_play_station_id_now(*, last_station_id_at: Optional[datetime],
                                listening_seconds: float = 0.0) -> bool:
    """True if it's time to insert a station ID into the next break."""
    if last_station_id_at is None:
        # first ID after ~15 min of listening
        return listening_seconds >= STATION_ID_CADENCE_MIN_SEC
    elapsed = (datetime.now(timezone.utc) - last_station_id_at).total_seconds()
    target = random.uniform(STATION_ID_CADENCE_MIN_SEC, STATION_ID_CADENCE_MAX_SEC)
    return elapsed >= target


async def last_station_id_played_at(db, *, session_id: str) -> Optional[datetime]:
    """When was the last station ID played in this session?"""
    if not session_id:
        return None
    doc = await db.station_flow_logs.find_one(
        {"session_id": session_id,
         "asset_type": {"$in": ["brand_id_short", "brand_id_long", "top_of_hour"]}},
        sort=[("played_at", -1)],
    )
    return doc.get("played_at") if doc else None


async def should_play_top_of_hour(db, *, session_id: str, now: Optional[datetime] = None) -> bool:
    """True if the wall-clock minute is < 2 AND we haven't fired a TOH for this hour yet."""
    now = now or datetime.now(timezone.utc)
    if now.minute >= 2:
        return False
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    if not session_id:
        return True
    fired = await db.station_flow_logs.find_one({
        "session_id": session_id,
        "asset_type": "top_of_hour",
        "played_at": {"$gte": hour_start},
    })
    return fired is None
