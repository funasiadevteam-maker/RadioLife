"""Admin — FUUSIC Home configuration (pillar order + section visibility) and
the demo track-library rebuild.

Config-driven so admins can A/B the Home realignment (Social-first default)
without a code change. Cookie admin session (require_admin).
"""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Request

from auth import require_admin
from core.features import (
    FEATURE_CATALOG, MANDATORY_FEATURES, DEFAULT_FEATURES,
    normalize_features, normalize_features_ordered,
)
from core.home_config import get_home_config, save_home_config, pillar_labels
from services.demo_library import (
    rebuild_demo_track_library, track_specs, STATUS_DOC_ID,
)
from services.object_storage import get_storage

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


@router.get("/feature-defaults")
async def admin_get_feature_defaults(request: Request,
                                     admin: dict = Depends(require_admin)):
    """Global + per-city default feature sets new users start with."""
    db = request.app.state.db
    doc = await db.app_settings.find_one({"_id": "feature_defaults"}) or {}
    base = doc.get("features")
    feats = normalize_features(base if base is not None else DEFAULT_FEATURES)
    by_city = {c: normalize_features_ordered(v)
               for c, v in (doc.get("by_city") or {}).items()}
    return {"catalog": FEATURE_CATALOG, "mandatory": MANDATORY_FEATURES,
            "features": feats, "by_city": by_city}


@router.put("/feature-defaults")
async def admin_put_feature_defaults(request: Request, body: dict = Body(default={}),
                                     admin: dict = Depends(require_admin)):
    db = request.app.state.db
    feats = normalize_features((body or {}).get("features"))
    update = {"features": feats,
              "updated_at": datetime.now(timezone.utc).isoformat()}
    raw_by_city = (body or {}).get("by_city")
    if isinstance(raw_by_city, dict):
        update["by_city"] = {str(c).strip().lower(): normalize_features_ordered(v)
                             for c, v in raw_by_city.items() if str(c).strip()}
    await db.app_settings.update_one(
        {"_id": "feature_defaults"}, {"$set": update}, upsert=True)
    doc = await db.app_settings.find_one({"_id": "feature_defaults"}) or {}
    by_city = {c: normalize_features_ordered(v)
               for c, v in (doc.get("by_city") or {}).items()}
    return {"catalog": FEATURE_CATALOG, "mandatory": MANDATORY_FEATURES,
            "features": feats, "by_city": by_city}


def _rebuild_status_public(doc: dict) -> dict:
    doc = dict(doc or {})
    doc.pop("_id", None)
    return doc


def _is_stale(doc: dict) -> bool:
    """A rebuild started >15 min ago (e.g. lost to a restart) is treated as
    not-running so the admin can retry."""
    if not doc or not doc.get("running"):
        return False
    started = doc.get("started_at")
    try:
        dt = datetime.fromisoformat(started)
        return (datetime.now(timezone.utc) - dt).total_seconds() > 900
    except Exception:
        return True


@router.get("/rebuild-track-library/status")
async def admin_rebuild_track_status(request: Request,
                                     admin: dict = Depends(require_admin)):
    db = request.app.state.db
    doc = await db.admin_track_rebuild.find_one({"_id": STATUS_DOC_ID}) or {}
    playable = await db.tracks.count_documents(
        {"source": "seed_demo",
         "storage_provider": "tigris", "playable_status": "ok"})
    return {**_rebuild_status_public(doc),
            "library_size": len(track_specs()),
            "persisted_ok": playable}


@router.post("/rebuild-track-library")
async def admin_rebuild_track_library(request: Request, force: bool = False,
                                      admin: dict = Depends(require_admin)):
    """One-tap: re-seed the demo track rows and re-upload any missing audio to
    object storage. Runs in the background; poll the status endpoint."""
    db = request.app.state.db
    cur = await db.admin_track_rebuild.find_one({"_id": STATUS_DOC_ID})
    if cur and cur.get("running") and not _is_stale(cur):
        return {"status": "already_running", **_rebuild_status_public(cur)}
    storage = get_storage()
    asyncio.create_task(rebuild_demo_track_library(db, storage, force=force))
    return {"status": "started", "total": len(track_specs()), "force": force}
