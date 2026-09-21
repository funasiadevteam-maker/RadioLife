"""Per-user UI preferences (account-level, cross-device).

Currently stores the web player dock position so a user's chosen player
placement (bottom / top / left / right / float) sticks across sessions
and devices.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from auth import current_user

router = APIRouter(prefix="/api/me", tags=["ui_prefs"])

_ALLOWED_DOCK = {"bottom", "top", "left", "right", "float"}


@router.get("/ui-prefs")
async def get_ui_prefs(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    u = await db.users.find_one({"user_id": user["user_id"]}, {"ui_prefs": 1})
    return {"ui_prefs": (u or {}).get("ui_prefs") or {}}


@router.put("/ui-prefs")
async def put_ui_prefs(request: Request, body: dict = Body(...),
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    updates = {}
    dock = (body or {}).get("player_dock")
    if dock is not None:
        if dock not in _ALLOWED_DOCK:
            raise HTTPException(400, {"code": "invalid_player_dock"})
        updates["ui_prefs.player_dock"] = dock
    if updates:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
    return {"ok": True}


__all__ = ["router"]
