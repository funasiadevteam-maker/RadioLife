"""Phase 3.8 — Admin Imaging endpoints + per-asset audio streaming.

Routes (mounted at /api/admin/imaging):
- GET  /stations                                       → list stations + counts
- GET  /{station_slug}                                 → sonic_branding + summary counts per asset_type
- POST /{station_slug}/sonic-branding                  → upsert sonic branding (name/tagline/voices/brand_words)
- GET  /{station_slug}/assets                          → list all assets for a station (grouped by type)
- POST /{station_slug}/asset/{asset_id}                → update weight/active/script/voice_key/daypart
- POST /{station_slug}/asset/{asset_id}/regenerate     → re-run generation on a single asset
- POST /{station_slug}/regenerate                      → kick a background pass over pending+failed (optional ?force=true)
- GET  /{station_slug}/asset/{asset_id}/audio          → stream MP3 (supports Range / 206)
- GET  /flow-logs?session_id=...&limit=N               → recent station_flow_logs (admin debug)

All routes require an admin user (HTTPException(403) otherwise).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, Response

from services.imaging_assets import (
    STATIONS, seed_imaging_assets, ensure_imaging_audio_async, _gen_one_asset,
)

logger = logging.getLogger("bigfm.admin.imaging")
imaging_router = APIRouter(prefix="/api/admin/imaging", tags=["admin-imaging"])


# Local copy of admin dep to avoid a circular import
async def _require_admin(request: Request):
    from auth import current_user
    user = await current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(403, "admin only")
    return user


def _serialize(doc: dict) -> dict:
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d["_id"])
        d.pop("_id", None)
    for k in ("generated_at", "created_at", "updated_at"):
        if d.get(k) and hasattr(d[k], "isoformat"):
            d[k] = d[k].isoformat()
    # Don't leak file_path
    d.pop("file_path", None)
    return d


# ---------- stations + branding ----------
@imaging_router.get("/stations")
async def list_stations(request: Request, _admin = Depends(_require_admin)):
    db = request.app.state.db
    out = []
    for slug, st in STATIONS.items():
        branding = await db.sonic_branding.find_one({"station_slug": slug}) or {}
        total = await db.imaging_assets.count_documents({"station_slug": slug})
        ready = await db.imaging_assets.count_documents({"station_slug": slug, "generation_status": "ready"})
        pending = await db.imaging_assets.count_documents({"station_slug": slug, "generation_status": "pending"})
        failed = await db.imaging_assets.count_documents({"station_slug": slug, "generation_status": "failed"})
        out.append({
            "station_slug": slug,
            "station_name": st["station_name"],
            "market": st["market"],
            "tagline": branding.get("tagline", st["tagline"]),
            "primary_voice_key":   branding.get("primary_voice_key",   st["primary_voice_key"]),
            "secondary_voice_key": branding.get("secondary_voice_key", st["secondary_voice_key"]),
            "brand_words": branding.get("brand_words", st["brand_words"]),
            "imaging_style_preset": branding.get("imaging_style_preset", st["imaging_style_preset"]),
            "asset_counts": {"total": total, "ready": ready, "pending": pending, "failed": failed},
        })
    return {"stations": out}


@imaging_router.get("/{station_slug}")
async def station_detail(station_slug: str, request: Request, _admin = Depends(_require_admin)):
    if station_slug not in STATIONS:
        raise HTTPException(404, "station not found")
    db = request.app.state.db
    branding = await db.sonic_branding.find_one({"station_slug": station_slug}) or {}
    # Count by asset_type
    pipeline = [
        {"$match": {"station_slug": station_slug}},
        {"$group": {
            "_id": "$asset_type",
            "total": {"$sum": 1},
            "ready": {"$sum": {"$cond": [{"$eq": ["$generation_status", "ready"]}, 1, 0]}},
        }},
    ]
    counts = await db.imaging_assets.aggregate(pipeline).to_list(length=100)
    return {
        "station_slug": station_slug,
        "branding": _serialize(branding),
        "asset_type_counts": [{"asset_type": c["_id"], "total": c["total"], "ready": c["ready"]} for c in counts],
    }


@imaging_router.post("/{station_slug}/sonic-branding")
async def update_sonic_branding(
    station_slug: str, request: Request, _admin = Depends(_require_admin),
    payload: dict = None,
):
    if station_slug not in STATIONS:
        raise HTTPException(404, "station not found")
    if not payload:
        raise HTTPException(400, "missing body")
    db = request.app.state.db
    allowed = {"tagline", "primary_voice_key", "secondary_voice_key",
               "brand_words", "imaging_style_preset"}
    update = {k: payload[k] for k in payload if k in allowed}
    if not update:
        raise HTTPException(400, "no allowed fields in body")
    from datetime import datetime, timezone
    update["updated_at"] = datetime.now(timezone.utc)
    await db.sonic_branding.update_one({"station_slug": station_slug}, {"$set": update}, upsert=True)
    fresh = await db.sonic_branding.find_one({"station_slug": station_slug})
    return {"ok": True, "branding": _serialize(fresh)}


# ---------- assets ----------
@imaging_router.get("/{station_slug}/assets")
async def list_assets(station_slug: str, request: Request,
                      asset_type: Optional[str] = Query(None),
                      _admin = Depends(_require_admin)):
    if station_slug not in STATIONS:
        raise HTTPException(404, "station not found")
    db = request.app.state.db
    q = {"station_slug": station_slug}
    if asset_type:
        q["asset_type"] = asset_type
    docs = await db.imaging_assets.find(q).sort([("asset_type", 1), ("slug", 1)]).to_list(length=500)
    out = [_serialize(d) for d in docs]
    # Build audio URLs (frontend will prefix with REACT_APP_BACKEND_URL)
    for o in out:
        o["audio_url"] = f"/api/admin/imaging/{station_slug}/asset/{o['id']}/audio"
    return {"items": out, "total": len(out)}


def _parse_object_id(s: str) -> ObjectId:
    try:
        return ObjectId(s)
    except Exception:
        raise HTTPException(400, "bad asset id")


@imaging_router.post("/{station_slug}/asset/{asset_id}")
async def update_asset(station_slug: str, asset_id: str, request: Request,
                       _admin = Depends(_require_admin),
                       payload: dict = None):
    if not payload:
        raise HTTPException(400, "missing body")
    db = request.app.state.db
    oid = _parse_object_id(asset_id)
    allowed = {"weight", "active", "script", "voice_key", "daypart", "energy"}
    update = {k: payload[k] for k in payload if k in allowed}
    if not update:
        raise HTTPException(400, "no allowed fields")
    res = await db.imaging_assets.update_one({"_id": oid, "station_slug": station_slug}, {"$set": update})
    if res.matched_count != 1:
        raise HTTPException(404, "asset not found")
    fresh = await db.imaging_assets.find_one({"_id": oid})
    return {"ok": True, "asset": _serialize(fresh)}


@imaging_router.post("/{station_slug}/asset/{asset_id}/regenerate")
async def regenerate_one(station_slug: str, asset_id: str, request: Request,
                          _admin = Depends(_require_admin)):
    db = request.app.state.db
    oid = _parse_object_id(asset_id)
    doc = await db.imaging_assets.find_one({"_id": oid, "station_slug": station_slug})
    if not doc:
        raise HTTPException(404, "asset not found")
    upd = await asyncio.to_thread(_gen_one_asset, doc)
    await db.imaging_assets.update_one({"_id": oid}, {"$set": upd})
    fresh = await db.imaging_assets.find_one({"_id": oid})
    return {"ok": True, "asset": _serialize(fresh)}


@imaging_router.post("/{station_slug}/regenerate")
async def regenerate_all(station_slug: str, request: Request,
                          _admin = Depends(_require_admin),
                          force: bool = Query(False),
                          limit: int = Query(60, ge=1, le=200)):
    if station_slug not in STATIONS:
        raise HTTPException(404, "station not found")
    db = request.app.state.db
    # Launch background task and return immediately
    asyncio.create_task(ensure_imaging_audio_async(db, station_slug=station_slug,
                                                     limit=limit, force=force))
    return {"ok": True, "kicked_off": True, "station_slug": station_slug,
            "force": force, "limit": limit}


# ---------- audio streaming (Range support) ----------
_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


def _serve_file_with_range(file_path: Path, request: Request) -> Response:
    if not file_path.exists() or file_path.stat().st_size < 200:
        raise HTTPException(404, "asset audio not generated yet")
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range") or request.headers.get("Range")
    if not range_header:
        def _full():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
        return StreamingResponse(_full(), media_type="audio/mpeg", headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400",
        })
    m = _RANGE_RE.match(range_header)
    if not m:
        raise HTTPException(416, "bad Range header")
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else file_size - 1
    end = min(end, file_size - 1)
    length = end - start + 1
    def _range_iter():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    return StreamingResponse(_range_iter(), status_code=206, media_type="audio/mpeg", headers={
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "public, max-age=86400",
    })


@imaging_router.get("/{station_slug}/asset/{asset_id}/audio")
async def stream_asset_audio(station_slug: str, asset_id: str, request: Request,
                              _admin = Depends(_require_admin)):
    db = request.app.state.db
    oid = _parse_object_id(asset_id)
    doc = await db.imaging_assets.find_one({"_id": oid, "station_slug": station_slug},
                                            {"file_path": 1, "_id": 0})
    if not doc:
        raise HTTPException(404, "asset not found")
    fp = doc.get("file_path")
    if not fp:
        raise HTTPException(404, "no audio yet")
    return _serve_file_with_range(Path(fp), request)


@imaging_router.get("/flow-logs/recent")
async def flow_logs_recent(request: Request, _admin = Depends(_require_admin),
                            session_id: Optional[str] = Query(None),
                            user_id: Optional[str] = Query(None),
                            limit: int = Query(50, ge=1, le=500)):
    db = request.app.state.db
    q = {}
    if session_id: q["session_id"] = session_id
    if user_id: q["user_id"] = user_id
    docs = await db.station_flow_logs.find(q, {"_id": 0}).sort([("played_at", -1)]).to_list(length=limit)
    for d in docs:
        if d.get("played_at") and hasattr(d["played_at"], "isoformat"):
            d["played_at"] = d["played_at"].isoformat()
    return {"items": docs, "total": len(docs)}


# ---------- Phase 3.8 v2 debug: inject sponsor bumper into next segment ----------
@imaging_router.post("/debug/inject-sponsor")
async def debug_inject_sponsor(request: Request, _admin = Depends(_require_admin),
                                session_id: str = Query(...),
                                sponsor_id: str = Query("test-sponsor-001")):
    """Admin debug: arm the next segment build to fire a sponsor_bumper pre-roll
    by writing `next_segment_sponsor_id` onto the session. Used to prove the
    sponsor-bumper wiring without real Phase 4 inventory."""
    db = request.app.state.db
    res = await db.radio_sessions.update_one(
        {"_id": session_id},
        {"$set": {"next_segment_sponsor_id": sponsor_id}},
    )
    if res.matched_count != 1:
        raise HTTPException(404, "session not found")
    return {"ok": True, "session_id": session_id, "next_segment_sponsor_id": sponsor_id,
            "note": "Next segment build will fire a sponsor_bumper pre-roll and clear this flag."}


@imaging_router.get("/flow-logs/live-summary")
async def flow_logs_live_summary(request: Request, _admin = Depends(_require_admin),
                                  minutes: int = Query(60, ge=1, le=1440)):
    """Aggregate item_type counts in the last N minutes — quick admin pulse on
    how often each imaging element is firing across all listeners."""
    from datetime import datetime, timedelta, timezone
    db = request.app.state.db
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    pipeline = [
        {"$match": {"played_at": {"$gte": since}}},
        {"$group": {"_id": "$item_type", "count": {"$sum": 1},
                     "last": {"$max": "$played_at"}}},
        {"$sort": {"count": -1}},
    ]
    rows = await db.station_flow_logs.aggregate(pipeline).to_list(length=50)
    total = await db.station_flow_logs.count_documents({"played_at": {"$gte": since}})
    for r in rows:
        if r.get("last") and hasattr(r["last"], "isoformat"):
            r["last"] = r["last"].isoformat()
    return {"minutes": minutes, "total_inserts": total, "by_item_type": rows}
