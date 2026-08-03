"""Phase C — Station artwork routes.

  POST   /api/stations/{slug}/artwork/generate    — kick off OpenAI gen
  GET    /api/stations/{slug}/artwork/status      — poll job state
  POST   /api/stations/{slug}/artwork/upload      — owner uploads JPG/PNG/WebP
  POST   /api/stations/{slug}/artwork/clear        — revert to gradient

Auth: owner-or-admin gate identical to other station-edit routes.

Generation is fire-and-forget — the POST returns immediately with a
``status: "queued"`` payload; a background task does the OpenAI call,
encodes the WebP, updates the station doc.  Frontend polls
``/artwork/status`` every 3s for up to 60s.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from auth import current_user
from services import image_gen as image_gen_svc
from services.station_artwork_prompt import build_prompt

router = APIRouter(prefix="/api/stations", tags=["station_artwork"])
log = logging.getLogger("bigfm.station_artwork")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024     # 5 MB per the brief
ALLOWED_UPLOAD_MIMES = {"image/jpeg", "image/png", "image/webp"}
GEN_TIMEOUT_SEC = 120                       # OpenAI image gen can take up to ~60s


# ─── Helpers ─────────────────────────────────────────────────────
async def _load_station(db: Any, slug: str) -> dict[str, Any]:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, "station_not_found")
    return s


def _is_owner_or_admin(station: dict, user: dict) -> bool:
    if user.get("role") == "admin":
        return True
    return station.get("owner_user_id") == user.get("user_id")


async def _set_status(db: Any, slug: str, status: str,
                          extras: Optional[dict] = None) -> None:
    """Mongo helper — keeps status writes consistent + audit-trailable."""
    update = {"artwork_status": status,
                  "artwork_status_at": datetime.now(timezone.utc)}
    if extras:
        update.update(extras)
    await db.community_radio_stations.update_one(
        {"slug": slug}, {"$set": update})


def _user_tier(user: dict) -> str:
    """Free vs premium vs admin — quota table lives in image_gen.py."""
    if user.get("role") == "admin":
        return "admin"
    if user.get("subscription_tier") in ("premium", "premium_plus"):
        return "premium"
    return "free"


# ─── Background gen task ─────────────────────────────────────────
async def _run_generation(db: Any, *, slug: str, prompt: str,
                          user_id: str, tier: str) -> None:
    """Background coroutine kicked off by /generate.  Updates the station
       doc with the final URL on success, or leaves status=failed on a
       provider error.  Either way the frontend's /status poller sees a
       terminal state within at most ``GEN_TIMEOUT_SEC`` seconds."""
    try:
        result = await asyncio.wait_for(
            image_gen_svc.generate(db, prompt=prompt, user_id=user_id,
                                                    station_slug=slug, tier=tier),
            timeout=GEN_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        log.warning("[station_artwork] generation timed out slug=%s", slug)
        await _set_status(db, slug, "failed",
                            {"artwork_error": "timeout"})
        return
    if not result.get("ok"):
        await _set_status(db, slug, "failed",
                            {"artwork_error": result.get("error") or "unknown"})
        return
    await _set_status(db, slug, "complete", {
        "artwork_url":            result["url"],
        "cover_image_url":       result["url"],   # legacy field consumed by UI
        "artwork_source":        "ai_generated",
        "artwork_generated_at": datetime.now(timezone.utc),
        "artwork_prompt":        prompt,
        "artwork_key":             result.get("key"),
        "artwork_error":          None,
    })


# ─── POST /generate ─────────────────────────────────────────────
@router.post("/{slug}/artwork/generate")
async def generate_artwork(slug: str, request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _load_station(db, slug)
    if not _is_owner_or_admin(station, user):
        raise HTTPException(403, "not_owner")

    # Rate-limit gate is enforced inside image_gen.generate, but we
    # check up-front so we can return a clean 429 BEFORE marking the
    # station as "running" (avoids confusing the UI poller).
    tier = _user_tier(user)
    allowed, used, limit = await image_gen_svc.check_rate_limit(
        db, user["user_id"], tier)
    if not allowed:
        raise HTTPException(429, detail={
            "error": "rate_limited",
            "message": f"You've generated {used}/{limit} images in the last hour. Try again later or upgrade for higher limits.",
            "used": used, "limit": limit, "tier": tier,
        })

    prompt = build_prompt(station)
    # Mark running before scheduling so a fast cache-hit doesn't race
    # with the poller's first read.
    await _set_status(db, slug, "running",
                            {"artwork_prompt": prompt, "artwork_error": None})
    # Fire and forget — the route returns immediately.
    asyncio.create_task(_run_generation(db, slug=slug, prompt=prompt,
                                                                    user_id=user["user_id"], tier=tier))
    return {
        "ok": True, "status": "queued", "slug": slug,
        "prompt": prompt,    # surface for debugging / display
        "rate_limit": {"used": used + 1, "limit": limit, "tier": tier},
    }


# ─── GET /status ─────────────────────────────────────────────────
@router.get("/{slug}/artwork/status")
async def artwork_status(slug: str, request: Request):
    """Public poll endpoint — no auth required (artwork is public anyway
       once the station is published)."""
    db = request.app.state.db
    s = await db.community_radio_stations.find_one(
        {"slug": slug},
        {"artwork_status": 1, "artwork_url": 1, "cover_image_url": 1,
          "artwork_source": 1, "artwork_generated_at": 1,
          "artwork_error": 1, "artwork_prompt": 1})
    if not s:
        raise HTTPException(404, "station_not_found")
    url = s.get("artwork_url") or s.get("cover_image_url")
    status = s.get("artwork_status") or ("complete" if url else "idle")
    return {
        "slug":                  slug,
        "status":                status,                                # queued|running|complete|failed|idle
        "image_url":            url,
        "artwork_source":     s.get("artwork_source"),
        "generated_at":        s.get("artwork_generated_at"),
        "prompt":                s.get("artwork_prompt"),
        "error":                  s.get("artwork_error"),
    }


# ─── POST /upload ───────────────────────────────────────────────
@router.post("/{slug}/artwork/upload")
async def artwork_upload(slug: str, request: Request,
                                              file: UploadFile = File(...),
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _load_station(db, slug)
    if not _is_owner_or_admin(station, user):
        raise HTTPException(403, "not_owner")

    if (file.content_type or "").lower() not in ALLOWED_UPLOAD_MIMES:
        raise HTTPException(400, detail={
            "error": "bad_mime",
            "message": "Only JPEG, PNG and WebP files are accepted.",
            "got": file.content_type})

    raw = await file.read()
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, detail={
            "error": "bad_size",
            "message": f"File must be ≤ {MAX_UPLOAD_BYTES // 1024 // 1024} MB.",
            "got_bytes": len(raw)})

    saved = image_gen_svc.persist_uploaded_bytes(raw, slug=slug)
    if not saved:
        raise HTTPException(500, "upload_processing_failed")
    await _set_status(db, slug, "complete", {
        "artwork_url":            saved["url"],
        "cover_image_url":       saved["url"],
        "artwork_source":        "uploaded",
        "artwork_generated_at": datetime.now(timezone.utc),
        "artwork_key":             saved["key"],
        "artwork_prompt":        None,
        "artwork_error":          None,
    })
    return {"ok": True, "status": "complete", **saved}


# ─── POST /clear ────────────────────────────────────────────────
@router.post("/{slug}/artwork/clear")
async def artwork_clear(slug: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _load_station(db, slug)
    if not _is_owner_or_admin(station, user):
        raise HTTPException(403, "not_owner")
    await _set_status(db, slug, "idle", {
        "artwork_url":            None,
        "cover_image_url":       None,
        "artwork_source":        "gradient_fallback",
        "artwork_generated_at": None,
        "artwork_key":             None,
        "artwork_prompt":        None,
        "artwork_error":          None,
    })
    return {"ok": True, "status": "idle", "cleared": True}
