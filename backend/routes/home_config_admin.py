"""Admin — FUUSIC Home configuration (pillar order + section visibility).

Config-driven so admins can A/B the Home realignment (Social-first default)
without a code change. Cookie admin session (require_admin).
"""
from fastapi import APIRouter, Body, Depends, Request

from auth import require_admin
from core.home_config import get_home_config, save_home_config, pillar_labels

router = APIRouter(prefix="/api/admin", tags=["home_config"])


@router.get("/home-config")
async def admin_get_home_config(request: Request,
                                admin: dict = Depends(require_admin)):
    cfg = await get_home_config(request.app.state.db)
    return {**cfg, "pillars": pillar_labels()}


@router.put("/home-config")
async def admin_put_home_config(request: Request, body: dict = Body(default={}),
                                admin: dict = Depends(require_admin)):
    cfg = await save_home_config(request.app.state.db, body or {})
    return {**cfg, "pillars": pillar_labels()}
