"""FUUSIC Social — Who-to-Follow discovery + suggestion dismissals."""
from __future__ import annotations

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional

from auth import current_user
from services.who_to_follow import suggest, dismiss_suggestion

router = APIRouter(prefix="/api/social", tags=["social-discovery"])


@router.get("/who-to-follow")
async def who_to_follow(request: Request, limit: int = 12,
                        actor_type: Optional[str] = None,
                        user: dict = Depends(current_user)):
    """Interest-based follow suggestions across People / Creators / Stations /
    Businesses / Clubs / Advisors, each with a plain-language reason."""
    limit = max(1, min(limit, 40))
    return await suggest(request.app.state.db, user["user_id"],
                         limit=limit, actor_type=actor_type)


class DismissBody(BaseModel):
    actor_type: str = Field(..., min_length=2, max_length=24)
    actor_id: str = Field(..., min_length=1, max_length=160)
    action: str = "not_interested"  # not_interested | hide


@router.post("/suggestions/dismiss")
async def dismiss(body: DismissBody, request: Request,
                  user: dict = Depends(current_user)):
    """Remember 'Not Interested' / 'Hide' so a suggestion never returns."""
    await dismiss_suggestion(request.app.state.db, user["user_id"],
                             body.actor_type, body.actor_id, body.action)
    return {"ok": True}
