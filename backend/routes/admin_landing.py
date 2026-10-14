"""Admin — public social landing configuration (§21).

Read/write the `landing_config` document that drives the public homepage:
enable the new social landing, default public theme, hero copy/CTAs, feature
shortcut order, feed + right-sidebar modules, station-count copy, and the
house/external promo controls (enable/disable + external promo cards).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Body, Depends

from auth import require_admin
from routes.public_landing import DEFAULT_LANDING_CONFIG, STATION_COPY_OPTIONS

router = APIRouter(prefix="/api/admin", tags=["admin-landing"])

_ALLOWED_THEMES = {"light", "dark", "system"}
_EDITABLE_KEYS = {
    "new_landing_enabled", "default_theme", "allow_theme_switch", "station_copy",
    "hero", "shortcut_order", "feed_modules", "right_modules", "promos",
}


@router.get("/landing-config")
async def admin_get_landing_config(request: Request,
                                   admin: dict = Depends(require_admin)):
    db = request.app.state.db
    stored = await db.app_settings.find_one({"_id": "landing_config"}) or {}
    cfg = {**DEFAULT_LANDING_CONFIG, **{k: v for k, v in stored.items() if k != "_id"}}
    cfg["hero"] = {**DEFAULT_LANDING_CONFIG["hero"], **(stored.get("hero") or {})}
    cfg["promos"] = stored.get("promos") or {"disabled": [], "external": []}
    return {"config": cfg,
            "options": {"themes": sorted(_ALLOWED_THEMES),
                        "station_copy": STATION_COPY_OPTIONS}}


@router.put("/landing-config")
async def admin_put_landing_config(request: Request, body: dict = Body(default={}),
                                   admin: dict = Depends(require_admin)):
    db = request.app.state.db
    update: dict = {}
    for k, v in (body or {}).items():
        if k not in _EDITABLE_KEYS:
            continue
        if k == "default_theme" and v not in _ALLOWED_THEMES:
            continue
        if k == "station_copy" and v not in STATION_COPY_OPTIONS:
            continue
        if k == "hero" and isinstance(v, dict):
            update["hero"] = {**DEFAULT_LANDING_CONFIG["hero"], **v}
            continue
        update[k] = v
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.app_settings.update_one(
        {"_id": "landing_config"}, {"$set": update}, upsert=True)
    stored = await db.app_settings.find_one({"_id": "landing_config"}) or {}
    cfg = {**DEFAULT_LANDING_CONFIG, **{k: v for k, v in stored.items() if k != "_id"}}
    cfg["hero"] = {**DEFAULT_LANDING_CONFIG["hero"], **(stored.get("hero") or {})}
    cfg["promos"] = stored.get("promos") or {"disabled": [], "external": []}
    return {"config": cfg}


__all__ = ["router"]
