"""Public recipes registry + a lightweight admin trigger test endpoint."""
from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user
from services import notification_trigger_dispatcher as _svc

router = APIRouter(tags=["ad12-triggers"])


@router.get("/api/notification-trigger-recipes",
                        description="Public — used by the AD.12 wizard step 3.")
async def get_recipes():
    return {"items": _svc.recipes_for_api(),
                  "count": len(_svc.RECIPES)}


@router.post("/api/admin/notification-triggers/fire",
                          description="Admin-only — manually fire a trigger event for a "
                                                    "given user, useful for smoke-testing recipes.")
async def fire_trigger(request: Request,
                                            event_name: str,
                                            user_id: str,
                                            user: dict = Depends(current_user)):
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "admin_required"})
    if not _svc.is_valid_recipe(event_name):
        raise HTTPException(400, {"code": "invalid_recipe"})
    return await _svc.dispatch_event(
        request.app.state.db, event_name=event_name, user_id=user_id)


__all__ = ["router"]
