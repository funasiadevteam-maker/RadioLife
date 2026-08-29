"""Artwork for imported (Radio Browser) stations.

Mirrors the community-station artwork flow but targets
`imported_radio_stations`, reusing the OpenAI gpt-image-1 generator +
Tigris/disk persistence in ``services.image_gen``.

  POST /api/imported-stations/{sid}/artwork/ensure    — on-demand, public,
        generates ONCE per station on first open (background); placeholder
        until it lands.
  POST /api/imported-stations/{sid}/artwork/generate  — owner/admin regen.
  POST /api/imported-stations/{sid}/artwork/upload    — owner/admin logo upload.
  POST /api/imported-stations/{sid}/artwork/clear      — owner/admin revert.
  GET  /api/imported-stations/{sid}/artwork/status     — poll.

`sid` accepts the raw station id or an ``imp_``-prefixed id.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from auth import current_user
from services import image_gen as image_gen_svc
from services.station_artwork_prompt import BRAND_SUFFIX, GENRE_HINTS

router = APIRouter(prefix="/api/imported-stations", tags=["imported_station_artwork"])
log = logging.getLogger("bigfm.imported_station_artwork")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_UPLOAD_MIMES = {"image/jpeg", "image/png", "image/webp"}
GEN_TIMEOUT_SEC = 120


def _id_candidates(sid: str) -> list:
    """Imported ids may be stored with or without the ``imp_`` prefix."""
    cands = [sid]
    cands.append(sid[4:] if sid.startswith("imp_") else f"imp_{sid}")
    return cands


async def _load(db: Any, sid: str) -> dict:
    s = await db.imported_radio_stations.find_one({"id": {"$in": _id_candidates(sid)}})
    if not s:
        raise HTTPException(404, "station_not_found")
    return s


async def _is_owner_or_admin(db: Any, station: dict, user: dict) -> bool:
    if user.get("role") == "admin":
        return True
    if station.get("owner_user_id") == user.get("user_id"):
        return True
    claim = await db.radio_station_claims.find_one({
        "station_id": station.get("id"),
        "claimed_by_user_id": user.get("user_id"),
        "claim_status": "approved",
    })
    return bool(claim)


def _prompt(station: dict) -> str:
    """Compose an on-brand image prompt from the imported station's
    name + description + genre. Never asks the model to render text."""
    name = (station.get("name") or "Radio").strip()
    hay = " ".join(str(station.get(k) or "") for k in
                   ("music_genre", "tags_raw", "description", "language")).lower()
    genre_hint = next((h for k, h in GENRE_HINTS.items() if k in hay), "")
    desc = (station.get("description") or "").strip()
    parts = [f"Cover artwork capturing the vibe of the radio station '{name}'."]
    if genre_hint:
        parts.append(f"Visual mood: {genre_hint}.")
    elif desc:
        parts.append(f"Theme: {desc[:160]}.")
    parts.append(BRAND_SUFFIX)
    return " ".join(parts)[:1800]


async def _set(db: Any, sid: str, fields: dict) -> None:
    fields = {**fields, "artwork_status_at": datetime.now(timezone.utc)}
    await db.imported_radio_stations.update_one(
        {"id": {"$in": _id_candidates(sid)}}, {"$set": fields})


ART_HISTORY_MAX = 5


async def _archive_current_art(db: Any, sid: str) -> None:
    """Push the station's current AI/owner artwork into `artwork_history`
    (capped, most-recent-last, deduped) so the owner can flip back to it."""
    s = await db.imported_radio_stations.find_one(
        {"id": {"$in": _id_candidates(sid)}},
        {"art_url": 1, "art_source": 1, "artwork_history": 1})
    if not s:
        return
    url = s.get("art_url")
    if not url or s.get("art_source") not in ("ai", "owner"):
        return
    hist = [h for h in (s.get("artwork_history") or []) if h.get("url") != url]
    hist.append({"url": url, "source": s.get("art_source"),
                 "archived_at": datetime.now(timezone.utc).isoformat()})
    await db.imported_radio_stations.update_one(
        {"id": {"$in": _id_candidates(sid)}},
        {"$set": {"artwork_history": hist[-ART_HISTORY_MAX:]}})


async def _run_generation(db: Any, *, sid: str, prompt: str,
                          user_id: str = "", tier: str = "free") -> None:
    try:
        result = await asyncio.wait_for(
            image_gen_svc.generate(db, prompt=prompt, user_id=user_id,
                                   station_slug=sid, tier=tier,
                                   bypass_rate_limit=not user_id),
            timeout=GEN_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        await _set(db, sid, {"artwork_status": "failed", "artwork_error": "timeout",
                             "art_gen_attempted": False})
        return
    if not result.get("ok"):
        await _set(db, sid, {"artwork_status": "failed", "art_gen_attempted": False,
                             "artwork_error": result.get("error") or "unknown"})
        return
    await _archive_current_art(db, sid)
    await _set(db, sid, {
        "art_url": result["url"], "art_source": "ai",
        "artwork_status": "complete", "art_gen_attempted": True,
        "artwork_generated_at": datetime.now(timezone.utc), "artwork_error": None,
    })


@router.post("/{sid}/artwork/ensure")
async def ensure_artwork(sid: str, request: Request):
    """Public, once-per-station on-demand generation. No-op when the station
    already has custom art or a generation was already attempted."""
    db = request.app.state.db
    s = await _load(db, sid)
    has_art = bool(s.get("art_url")) or bool(s.get("flagship_art"))
    if has_art:
        return {"ok": True, "status": "complete", "already": True}
    if s.get("art_gen_attempted") or s.get("artwork_status") in ("running", "queued"):
        return {"ok": True, "status": s.get("artwork_status") or "pending", "already": True}
    await _set(db, sid, {"artwork_status": "queued", "art_gen_attempted": True})
    asyncio.create_task(_run_generation(db, sid=sid, prompt=_prompt(s)))
    return {"ok": True, "status": "queued"}


@router.post("/ensure-flagship-art")
async def ensure_flagship_art(request: Request):
    """Self-heal: queue AI-art generation for flagship stations that only
    have a placeholder (e.g. a fresh deploy with no seeded art). Idempotent."""
    db = request.app.state.db
    queued = 0
    async for s in db.imported_radio_stations.find(
            {"flagship_slug": {"$ne": None}}).limit(12):
        if s.get("flagship_art") or s.get("art_url") or s.get("art_gen_attempted"):
            continue
        if s.get("artwork_status") in ("running", "queued"):
            continue
        await _set(db, s["id"], {"artwork_status": "queued", "art_gen_attempted": True})
        asyncio.create_task(_run_generation(db, sid=s["id"], prompt=_prompt(s)))
        queued += 1
    return {"ok": True, "queued": queued}



@router.post("/{sid}/artwork/generate")
async def generate_artwork(sid: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _load(db, sid)
    if not await _is_owner_or_admin(db, s, user):
        raise HTTPException(403, "not_owner")
    tier = "admin" if user.get("role") == "admin" else (
        "premium" if user.get("subscription_tier") in ("premium", "premium_plus") else "free")
    allowed, used, limit = await image_gen_svc.check_rate_limit(db, user["user_id"], tier)
    if not allowed:
        raise HTTPException(429, detail={"error": "rate_limited", "used": used,
                                         "limit": limit, "tier": tier})
    prompt = _prompt(s)
    await _set(db, sid, {"artwork_status": "running", "artwork_error": None})
    asyncio.create_task(_run_generation(db, sid=sid, prompt=prompt,
                                        user_id=user["user_id"], tier=tier))
    return {"ok": True, "status": "queued", "prompt": prompt}


@router.post("/{sid}/artwork/upload")
async def upload_artwork(sid: str, request: Request, file: UploadFile = File(...),
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _load(db, sid)
    if not await _is_owner_or_admin(db, s, user):
        raise HTTPException(403, "not_owner")
    if (file.content_type or "").lower() not in ALLOWED_UPLOAD_MIMES:
        raise HTTPException(400, detail={"error": "bad_mime", "got": file.content_type})
    raw = await file.read()
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, detail={"error": "bad_size", "got_bytes": len(raw)})
    saved = image_gen_svc.persist_uploaded_bytes(raw, slug=f"imp-{s.get('id')}")
    if not saved:
        raise HTTPException(500, "upload_processing_failed")
    await _archive_current_art(db, sid)
    await _set(db, sid, {
        "art_url": saved["url"], "art_source": "owner",
        "artwork_status": "complete", "art_gen_attempted": True,
        "artwork_generated_at": datetime.now(timezone.utc), "artwork_error": None,
    })
    return {"ok": True, "status": "complete", **saved}


@router.post("/{sid}/artwork/clear")
async def clear_artwork(sid: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _load(db, sid)
    if not await _is_owner_or_admin(db, s, user):
        raise HTTPException(403, "not_owner")
    await _set(db, sid, {"art_url": None, "art_source": None,
                         "artwork_status": "idle", "art_gen_attempted": False})
    return {"ok": True, "status": "idle", "cleared": True}


@router.get("/{sid}/artwork/status")
async def artwork_status(sid: str, request: Request):
    db = request.app.state.db
    s = await db.imported_radio_stations.find_one(
        {"id": {"$in": _id_candidates(sid)}},
        {"art_url": 1, "art_source": 1, "flagship_art": 1,
         "artwork_status": 1, "artwork_error": 1})
    if not s:
        raise HTTPException(404, "station_not_found")
    url = s.get("art_url") or s.get("flagship_art")
    status = s.get("artwork_status") or ("complete" if url else "idle")
    return {"sid": sid, "status": status, "image_url": url,
            "art_source": s.get("art_source"), "error": s.get("artwork_error")}


@router.get("/{sid}/artwork/history")
async def artwork_history(sid: str, request: Request,
                          user: dict = Depends(current_user)):
    """Owner/admin — the last few AI/owner artworks, newest first."""
    db = request.app.state.db
    s = await _load(db, sid)
    if not await _is_owner_or_admin(db, s, user):
        raise HTTPException(403, "not_owner")
    hist = list(reversed(s.get("artwork_history") or []))
    return {"ok": True, "current": s.get("art_url"),
            "current_source": s.get("art_source"), "history": hist}


@router.post("/{sid}/artwork/restore")
async def restore_artwork(sid: str, request: Request,
                          user: dict = Depends(current_user)):
    """Owner/admin — flip the station art back to a previous history entry."""
    db = request.app.state.db
    s = await _load(db, sid)
    if not await _is_owner_or_admin(db, s, user):
        raise HTTPException(403, "not_owner")
    body = await request.json()
    url = (body or {}).get("art_url")
    entries = s.get("artwork_history") or []
    match = next((h for h in entries if h.get("url") == url), None)
    if not match:
        raise HTTPException(400, detail={"error": "unknown_art_url"})
    await _archive_current_art(db, sid)
    await _set(db, sid, {
        "art_url": url, "art_source": match.get("source") or "ai",
        "artwork_status": "complete", "art_gen_attempted": True,
        "artwork_error": None,
    })
    return {"ok": True, "status": "complete", "art_url": url}
