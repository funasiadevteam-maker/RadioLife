"""Radio session + segment + share models."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class RadioStartRequest(BaseModel):
    channel: Optional[str] = None


class HostInfo(BaseModel):
    voice_key: str
    name: str


class RadioSegmentOut(BaseModel):
    segment_id: str
    segment_url: str
    duration_sec: float
    track_id: str
    track_title: str
    track_artist: str
    rj_voice_key: str
    rj_voice_name: str
    rj_script: str
    rj_start_sec: float
    rj_format: str
    rj_hosts: List[HostInfo] = []
    channel_slug: Optional[str] = None
    channel_name: Optional[str] = None


class RadioStartResponse(BaseModel):
    session_id: str
    segment: RadioSegmentOut
    skip_state: dict


class RadioNextResponse(BaseModel):
    session_id: str
    segment: RadioSegmentOut
    skip_state: dict


class SwitchChannelRequest(BaseModel):
    session_id: str
    channel: str


class SwitchChannelResponse(BaseModel):
    session_id: str
    channel_slug: str
    channel_name: Optional[str] = None
    transitional: bool = True
    tuning_sfx_url: str
    estimated_ready_sec: int = 15
    skip_state: dict


class RadioReadyResponse(BaseModel):
    ready: bool
    segment: Optional[RadioSegmentOut] = None
    skip_state: dict


class ShareCreateRequest(BaseModel):
    segment_id: str


class AdminTestSegmentReq(BaseModel):
    prev_track_id: Optional[str] = None
    next_track_id: str
    voice_key: str = "veer_dubai"
    format: Optional[str] = None
    channel: Optional[str] = None
