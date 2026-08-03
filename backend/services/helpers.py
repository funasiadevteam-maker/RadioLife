"""Generic time-of-day, era, helpers shared across radio modules."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from core.db import db
from models.rj import RJContext


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def era_bucket(year: Optional[int]) -> Optional[str]:
    if not year:
        return None
    if year < 1990:
        return "80s"
    if year < 2000:
        return "90s"
    if year < 2010:
        return "2000s"
    if year < 2020:
        return "2010s"
    return "2020s"


def tod_now_dubai() -> str:
    uae_hour = (datetime.now(timezone.utc) + timedelta(hours=4)).hour
    if 5 <= uae_hour < 12:
        return "morning"
    if 12 <= uae_hour < 17:
        return "afternoon"
    if 17 <= uae_hour < 21:
        return "evening"
    return "late_night"


def activity_guess_now() -> str:
    uae_hour = (datetime.now(timezone.utc) + timedelta(hours=4)).hour
    if 6 <= uae_hour < 10:
        return "morning_commute"
    if 10 <= uae_hour < 13:
        return "workday_focus"
    if 13 <= uae_hour < 15:
        return "lunch_break"
    if 17 <= uae_hour < 20:
        return "evening_commute"
    if 20 <= uae_hour < 23:
        return "dinner"
    if 23 <= uae_hour or uae_hour < 5:
        return "late_night_drive"
    return "workday_focus"


def ctx_for_now() -> RJContext:
    uae_hour = (datetime.now(timezone.utc) + timedelta(hours=4)).hour
    if 5 <= uae_hour < 12:
        tod = "morning"
    elif 12 <= uae_hour < 17:
        tod = "afternoon"
    elif 17 <= uae_hour < 21:
        tod = "evening drive time"
    else:
        tod = "late night"
    return RJContext(time_of_day=tod, city="Dubai")


async def get_track(track_id: str) -> dict:
    doc = await db.tracks.find_one({"_id": track_id})
    if not doc:
        raise HTTPException(404, f"track {track_id} not found")
    return doc


def track_doc_to_out(doc: dict) -> dict:
    """Lightweight serializer that returns a dict suitable for TrackOut model."""
    from core.config import DEFAULT_ENERGY
    uploaded_at = doc["uploaded_at"]
    if isinstance(uploaded_at, str):
        uploaded_at = datetime.fromisoformat(uploaded_at)
    return {
        "id": doc["_id"],
        "title": doc["title"],
        "artist": doc["artist"],
        "duration_sec": doc["duration_sec"],
        "uploaded_at": uploaded_at,
        "energy_level": doc.get("energy_level", DEFAULT_ENERGY),
        "mood": doc.get("mood"),
        "bpm": doc.get("bpm"),
        "album": doc.get("album"),
        "genre": doc.get("genre"),
        "release_year": doc.get("release_year"),
        "language": doc.get("language"),
        "language_confidence": doc.get("language_confidence"),
        "era": doc.get("era"),
        "vibe_tags": doc.get("vibe_tags") or [],
        "recommended_time_of_day": doc.get("recommended_time_of_day") or [],
        "danceability": doc.get("danceability"),
        "explicit": bool(doc.get("explicit", False)),
        "isrc": doc.get("isrc"),
        "fingerprint_match_score": doc.get("fingerprint_match_score"),
        "auto_tagged_at": doc.get("auto_tagged_at"),
        "manual_overrides": doc.get("manual_overrides") or [],
    }
