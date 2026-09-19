"""RadioLife Social V2 — DREAM CLUBS.

Themed communities (Lucid Dreamers, Nightmare Support, Recurring Dreams …)
where people gather around the dreams they share. Reuses the `dreams`
collection + anonymity masking from `routes.dreams_guidance`; a club dream is
a normal dream carrying a `club_slug`. Join/leave is a simple membership row.

All routes: /api/social/clubs/*
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from routes.social_v2 import _user_public
from routes.dreams_guidance import (MOODS, TAGS, _dream_public, _require_flag,
                                    _now as _dg_now)

router = APIRouter(prefix="/api/social/clubs", tags=["dream_clubs"])

DEFAULT_CLUBS = [
    {"_id": "lucid-dreamers", "name": "Lucid Dreamers",
     "description": "Learn to wake up inside your dreams and steer them.",
     "icon": "moon-waning-crescent", "color": "#7c3aed"},
    {"_id": "nightmare-support", "name": "Nightmare Support",
     "description": "A gentle, judgement-free space to share and process nightmares.",
     "icon": "weather-night", "color": "#be123c"},
    {"_id": "recurring-dreams", "name": "Recurring Dreams",
     "description": "For dreams that keep coming back — find patterns together.",
     "icon": "repeat", "color": "#0891b2"},
    {"_id": "astrology-lovers", "name": "Astrology Lovers",
     "description": "Dreams, stars and signs — share and compare cosmic notes.",
     "icon": "zodiac-leo", "color": "#d97706"},
    {"_id": "prophetic-spiritual", "name": "Prophetic & Spiritual",
     "description": "Dreams that feel meaningful, symbolic or spiritual.",
     "icon": "white-balance-sunny", "color": "#ca8a04"},
    {"_id": "sleep-and-science", "name": "Sleep & Science",
     "description": "Curious about why we dream? Talk sleep, REM and the mind.",
     "icon": "brain", "color": "#2563eb"},
]


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


async def ensure_clubs_indexes(db) -> None:
    await db.dream_club_members.create_index([("slug", 1), ("user_id", 1)],
                                             unique=True, name="dcm_uniq")
    await db.dream_club_members.create_index([("user_id", 1)], name="dcm_mine")
    await db.dreams.create_index([("club_slug", 1), ("created_at", -1)], name="dr_club")
    for c in DEFAULT_CLUBS:
        await db.dream_clubs.update_one(
            {"_id": c["_id"]},
            {"$setOnInsert": {**c, "slug": c["_id"], "is_default": True,
                              "created_at": datetime.now(timezone.utc)}},
            upsert=True)


async def _club_or_404(db, slug: str) -> dict:
    c = await db.dream_clubs.find_one({"_id": slug})
    if not c:
        raise HTTPException(404, {"code": "club_not_found"})
    return c


async def _club_public(db, c: dict, uid: str) -> dict:
    member = await db.dream_club_members.find_one({"slug": c["_id"], "user_id": uid})
    member_count = await db.dream_club_members.count_documents({"slug": c["_id"]})
    dream_count = await db.dreams.count_documents({"club_slug": c["_id"], "status": "active"})
    return {"slug": c["_id"], "name": c.get("name"),
            "description": c.get("description"), "icon": c.get("icon"),
            "color": c.get("color"), "is_member": bool(member),
            "member_count": member_count, "dream_count": dream_count}


@router.get("")
async def list_clubs(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    clubs = []
    async for c in db.dream_clubs.find().sort("name", 1):
        clubs.append(await _club_public(db, c, uid))
    return {"items": clubs}


@router.get("/{slug}")
async def club_detail(slug: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    c = await _club_or_404(db, slug)
    info = await _club_public(db, c, uid)
    rows = []
    authors: dict[str, dict] = {}
    async for d in db.dreams.find(
            {"club_slug": slug, "status": "active"}).sort("created_at", -1).limit(40):
        rows.append(d)
    aids = [d["user_id"] for d in rows if not d.get("anonymous")]
    if aids:
        async for u in db.users.find({"user_id": {"$in": aids}}):
            authors[u["user_id"]] = _user_public(u)
    info["dreams"] = [_dream_public(d, uid, authors.get(d["user_id"])) for d in rows]
    return info


@router.post("/{slug}/join")
async def join_club(slug: str, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _club_or_404(db, slug)
    await db.dream_club_members.update_one(
        {"slug": slug, "user_id": user["user_id"]},
        {"$setOnInsert": {"slug": slug, "user_id": user["user_id"],
                          "joined_at": _dg_now()}}, upsert=True)
    return {"ok": True, "is_member": True}


@router.post("/{slug}/leave")
async def leave_club(slug: str, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.dream_club_members.delete_one({"slug": slug, "user_id": user["user_id"]})
    return {"ok": True, "is_member": False}


class ClubDreamBody(BaseModel):
    title: Optional[str] = Field(None, max_length=140)
    description: str = Field(..., min_length=1, max_length=4000)
    mood: Optional[str] = None
    tags: list[str] = []
    anonymous: bool = False


@router.post("/{slug}/dreams")
async def post_club_dream(slug: str, body: ClubDreamBody, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_flag(db, "dream_sharing_enabled")
    c = await _club_or_404(db, slug)
    # Auto-join on first post.
    await db.dream_club_members.update_one(
        {"slug": slug, "user_id": user["user_id"]},
        {"$setOnInsert": {"slug": slug, "user_id": user["user_id"],
                          "joined_at": _dg_now()}}, upsert=True)
    did = f"dm_{uuid.uuid4().hex[:16]}"
    doc = {"_id": did, "user_id": user["user_id"],
           "title": (body.title or "").strip() or None,
           "description": body.description.strip(),
           "mood": body.mood if body.mood in MOODS else None,
           "tags": [t for t in (body.tags or []) if t in TAGS][:8],
           "dream_date": None, "visibility": "public",
           "anonymous": bool(body.anonymous), "club_slug": slug,
           "similar_count": 0, "comment_count": 0, "advisor_response_count": 0,
           "reaction_counts": {}, "ai_reflection": None,
           "status": "active", "report_count": 0,
           "created_at": _dg_now(), "updated_at": _dg_now()}
    await db.dreams.insert_one(doc)
    return _dream_public(doc, user["user_id"], _user_public(user), detail=True)


__all__ = ["router", "ensure_clubs_indexes"]
