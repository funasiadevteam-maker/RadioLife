"""Phase 18d — Programmatic stack routes: GAM + OpenRTB status, VAST XML
serving, attribution-impression tracking, and dynamic ads.txt admin.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel

from auth import require_admin

logger = logging.getLogger("bigfm.phase18d")

phase18d_router = APIRouter(prefix="/api", tags=["phase18d"])


# ────────── GAM status ──────────
@phase18d_router.get("/admin/integrations/gam/status")
async def gam_status(_admin: dict = Depends(require_admin)):
    from services.gam_adapter import status_snapshot
    return status_snapshot()


# ────────── OpenRTB status ──────────
@phase18d_router.get("/admin/integrations/openrtb/status")
async def openrtb_status(_admin: dict = Depends(require_admin)):
    from services.openrtb_adapter import status_snapshot
    return status_snapshot()


# ────────── ads.txt admin (GET + POST) ──────────
class AdsTxtBody(BaseModel):
    content: str


@phase18d_router.get("/admin/integrations/ads-txt")
async def admin_get_ads_txt(_admin: dict = Depends(require_admin)):
    from services.ads_txt_manager import read_content, validate, ADS_TXT_PATH
    content = read_content()
    v = validate(content)
    return {"content": content,
              "path":       str(ADS_TXT_PATH),
              "bytes":     len(content.encode("utf-8")),
              "valid_line_count": v["valid_line_count"],
              "bad_lines":              v["bad_lines"]}


@phase18d_router.post("/admin/integrations/ads-txt")
async def admin_set_ads_txt(body: AdsTxtBody,
                                                _admin: dict = Depends(require_admin)):
    from services.ads_txt_manager import write_content
    try:
        return write_content(body.content)
    except ValueError as e:
        # Flatten the 400 detail shape so clients get a single `detail`
        # wrapper instead of `{detail: {detail: {...}}}`.
        payload = e.args[0] if e.args else {}
        if isinstance(payload, dict):
            payload.setdefault("code", "invalid_ads_txt_lines")
            raise HTTPException(400, payload)
        raise HTTPException(400, {"code": "invalid_ads_txt_lines"})


# ────────── VAST 4.0 wrapper for a stored creative ──────────
@phase18d_router.get("/ads/vast/{creative_id}")
async def serve_vast(creative_id: str, request: Request,
                                  serve_id: Optional[str] = Query(None)):
    """Return VAST 4.0 XML for a stored creative.  Public — used by
    external VAST consumers (in-car OEMs, podcatchers, etc.).  Optionally
    accepts `?serve_id=` so the impression tracking pings tie back to a
    specific `ad_serve_events` row."""
    db = request.app.state.db
    # Phase 18b creatives use `id`; legacy ads_public.py uses `creative_id`.
    cr = await db.ad_creatives.find_one(
        {"$or": [{"id": creative_id}, {"creative_id": creative_id}]})
    if not cr:
        # Empty VAST instead of 404 so external callers don't hard-fail.
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?>\n<VAST version="4.0"/>',
            media_type="application/xml")
    # Try to enrich with advertiser name.
    adv_name = "BigFM Advertiser"
    aid = cr.get("advertiser_id")
    if aid:
        adv = await db.advertisers.find_one({"id": aid}, {"name": 1, "_id": 0})
        if adv:
            adv_name = adv.get("name") or adv_name
    from services.vast_wrapper import build_vast_xml
    xml = build_vast_xml(cr, base_url=str(request.base_url),
                                        serve_id=serve_id or "",
                                        advertiser_name=adv_name)
    return Response(xml, media_type="application/xml",
                          headers={"Cache-Control": "public, max-age=300"})


# ────────── Attribution-impression tracking (idempotent) ──────────
@phase18d_router.get("/ads/tracking/impression")
async def track_impression(request: Request,
                                            serve_id: str = Query(...),
                                            event: str = Query("impression")):
    """Records an event onto the `ad_serve_events` row.  Idempotent:
    the same (serve_id, event) tuple writes a single dedup row and
    returns 200 on subsequent calls."""
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    event = (event or "impression").lower().strip()[:32]
    # Use a deterministic dedup_key so the unique index naturally rejects
    # repeats; we catch DuplicateKeyError to honor idempotency without 4xx.
    dedup_key = f"{serve_id}|{event}"
    try:
        await db.ad_serve_event_pings.update_one(
            {"dedup_key": dedup_key},
            {"$setOnInsert": {"dedup_key": dedup_key,
                                          "serve_id":     serve_id,
                                          "event":         event,
                                          "first_seen": now},
              "$inc": {"hits": 1},
              "$set": {"last_seen": now}},
            upsert=True)
    except Exception as e:
        logger.warning("[phase18d] tracking ping upsert failed: %s", e)
    # Mark the ad_serve_events row when event ∈ {complete, impression}.
    if event in ("complete", "impression"):
        set_fields = {f"event_{event}_at": now}
        if event == "complete":
            set_fields["completed"] = True
        await db.ad_serve_events.update_one(
            {"$or": [{"id": serve_id}, {"serve_id": serve_id}]},
            {"$set": set_fields})
    # Always return 1x1 GIF-ish 204 so callers can use <img> beacons too.
    return Response(status_code=204)
