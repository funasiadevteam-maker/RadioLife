"""Phase 3.7 — Admin RJ Quality Dashboard backend routes.

All routes require admin role. Surfaces the data the dashboard renders:
recent QA records, common banned-phrase issues, top-rated voices,
rating submission, winning-take flagging, and audition trigger.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import current_user
from core.db import db
from services.audio_qa import (
    add_admin_rating, common_issues_summary, list_recent_qa,
    set_winning_take, top_rated_voices,
)
from services.personality_profiles import list_personality_profiles

logger = logging.getLogger("bigfm.rj_quality")


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user


rj_quality_router = APIRouter(prefix="/api/admin/rj-quality", tags=["rj-quality"])


@rj_quality_router.get("/recent")
async def get_recent_qa(
    limit: int = Query(default=50, ge=1, le=200),
    channel: Optional[str] = None,
    market: Optional[str] = None,
    profile: Optional[str] = None,
    user: dict = Depends(require_admin),
):
    """Recent RJ breaks with full QA metadata for side-by-side comparison."""
    rows = await list_recent_qa(
        limit=limit, channel_slug=channel, market=market, profile_slug=profile,
    )
    return {"total": len(rows), "items": rows}


@rj_quality_router.get("/dashboard")
async def dashboard_summary(user: dict = Depends(require_admin)):
    """Aggregate stats for the dashboard hero strip."""
    total_qa = await db.rj_audio_qa.count_documents({})
    winners = await db.rj_audio_qa.count_documents({"is_winning_take": True})
    issues = await common_issues_summary(hours=24)
    voices = await top_rated_voices(limit=8)
    profiles = await list_personality_profiles(db)
    return {
        "total_segments": total_qa,
        "winning_takes": winners,
        "common_issues_24h": issues,
        "top_rated_voices": voices,
        "personality_profiles": profiles,
    }


@rj_quality_router.post("/{segment_id}/rate")
async def rate_segment(
    segment_id: str,
    naturalness_1_5: int = Query(..., ge=1, le=5),
    hinglish_quality_1_5: int = Query(..., ge=1, le=5),
    radio_energy_1_5: int = Query(..., ge=1, le=5),
    notes: str = Query(default=""),
    user: dict = Depends(require_admin),
):
    ok = await add_admin_rating(
        segment_id=segment_id, admin_id=user["user_id"],
        naturalness_1_5=naturalness_1_5,
        hinglish_quality_1_5=hinglish_quality_1_5,
        radio_energy_1_5=radio_energy_1_5,
        notes=notes,
    )
    if not ok:
        raise HTTPException(404, "segment not found in QA store")
    return {"ok": True, "segment_id": segment_id}


@rj_quality_router.post("/{segment_id}/winning")
async def mark_winning(
    segment_id: str,
    winning: bool = Query(default=True),
    user: dict = Depends(require_admin),
):
    ok = await set_winning_take(segment_id, winning)
    if not ok:
        raise HTTPException(404, "segment not found")
    return {"ok": True, "segment_id": segment_id, "is_winning_take": winning}


@rj_quality_router.get("/personality_profiles")
async def get_personality_profiles(user: dict = Depends(require_admin)):
    return {"profiles": await list_personality_profiles(db)}
