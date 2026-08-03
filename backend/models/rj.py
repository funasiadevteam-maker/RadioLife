"""RJ script + synth + stream-build models."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RJContext(BaseModel):
    time_of_day: Optional[str] = None
    weather_hint: Optional[str] = None
    city: Optional[str] = None


class RJGenerateRequest(BaseModel):
    prev_track_id: str
    next_track_id: str
    context: RJContext = Field(default_factory=RJContext)


class RJGenerateResponse(BaseModel):
    script: str
    voice_id: str


class RJSynthRequest(BaseModel):
    script: str
    voice_id: Optional[str] = None


class RJSynthResponse(BaseModel):
    rj_audio_id: str
    file_path: str
    duration_sec: float


class StreamBuildRequest(BaseModel):
    track_ids: List[str]


class StreamSegment(BaseModel):
    type: str
    index: int
    start_sec: float
    end_sec: float


class StreamBuildResponse(BaseModel):
    stream_id: str
    file_path: str
    duration_sec: float
    segments: List[StreamSegment]
