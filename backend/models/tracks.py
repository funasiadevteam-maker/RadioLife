"""Track-related Pydantic models."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from core.config import DEFAULT_ENERGY


class TrackOut(BaseModel):
    id: str
    title: str
    artist: str
    duration_sec: float
    uploaded_at: datetime
    energy_level: str = DEFAULT_ENERGY
    mood: Optional[str] = None
    bpm: Optional[float] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    release_year: Optional[int] = None
    language: Optional[str] = None
    language_confidence: Optional[str] = None
    era: Optional[str] = None
    vibe_tags: list[str] = []
    recommended_time_of_day: list[str] = []
    danceability: Optional[float] = None
    explicit: bool = False
    isrc: Optional[str] = None
    fingerprint_match_score: Optional[float] = None
    auto_tagged_at: Optional[str] = None
    manual_overrides: list[str] = []


class BulkUploadResult(BaseModel):
    succeeded: List[TrackOut]
    failed: List[dict]
