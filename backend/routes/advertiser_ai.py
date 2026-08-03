"""Phase 18b — AI Ad Creator routes.

Endpoints (mounted at /api/advertiser):
  GET  /{aid}/ai/voices              public voice catalog
  POST /{aid}/ai/generate            run full pipeline → preview payload
  POST /{aid}/ai/save                persist preview as ad_creatives doc
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from routes.advertiser import _require_staff
from services.ai_ad_creator import AI_VOICE_CATALOG, run_pipeline
from services.telemetry import emit_event

ai_router = APIRouter(prefix="/api/advertiser", tags=["advertiser-18b-ai"])


class GenerateBody(BaseModel):
    business:           str
    description:        str
    tone:                  str = "friendly"
    audio_length_sec: int  = 15
    voice_id:            str = "maya"
    brand_color:        Optional[str] = None
    market:              Optional[str] = None
    click_url:           Optional[str] = None
    keywords:           Optional[list[str]] = None
    include_image:    bool = True


@ai_router.get("/{advertiser_id}/ai/voices")
async def list_voices(advertiser_id: str, request: Request):
    await _require_staff(request, advertiser_id, "analyst")
    return {"items": [{"id": v["id"], "label": v["label"],
                                  "persona": v["persona"]} for v in AI_VOICE_CATALOG]}


@ai_router.post("/{advertiser_id}/ai/generate")
async def ai_generate(advertiser_id: str, body: GenerateBody, request: Request):
    await _require_staff(request, advertiser_id, "manager")
    db = request.app.state.db
    adv = await db.advertisers.find_one({"id": advertiser_id})
    if not adv:
        raise HTTPException(404, "advertiser not found")
    if body.tone not in ("friendly", "energetic", "luxurious", "chill", "urgent"):
        raise HTTPException(400, "invalid tone")
    if body.audio_length_sec not in (15, 30):
        raise HTTPException(400, "audio_length_sec must be 15 or 30")
    try:
        preview = await run_pipeline(
            db=db, advertiser=adv, business=body.business,
            description=body.description, tone=body.tone,
            audio_length_sec=body.audio_length_sec,
            voice_id=body.voice_id, brand_color=body.brand_color,
            market=body.market, click_url=body.click_url,
            keywords=body.keywords, include_image=body.include_image)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return preview


class SaveBody(BaseModel):
    creative_id:        str
    title:                  str
    script:                str
    audio_url:           str
    audio_path:         str
    duration_sec:      float
    image_url:           Optional[str] = None
    brand_safety_check: dict
    vast_xml:            str
    voice_id:             str
    tone:                    str
    audio_length_sec: int
    audio_source:      str
    click_url:             Optional[str] = None


@ai_router.post("/{advertiser_id}/ai/save")
async def ai_save(advertiser_id: str, body: SaveBody, request: Request):
    await _require_staff(request, advertiser_id, "manager")
    db = request.app.state.db
    verdict = (body.brand_safety_check or {}).get("verdict", "review")
    status  = "approved" if verdict == "approved" else (
                  "rejected" if verdict == "rejected" else "pending_review")
    # Phase 36c.5 (post-repack ads migration) — when Tigris is configured,
    # push the local audio + image artefacts to S3 and persist the keys on
    # the creative doc. Local files remain as a fallback (serve route
    # prefers Tigris key, then local).
    storage_key_creative_audio = None
    storage_key_creative_image = None
    try:
        import os as _os
        from pathlib import Path as _P
        from services import object_storage as obs
        st = obs.get_storage()
        if st.backend_name == "tigris":
            if body.audio_path and _P(body.audio_path).is_file():
                k_a = obs.key_ad_creative_audio(body.creative_id, "mp3")
                st.upload(local_path=body.audio_path, key=k_a,
                                  content_type="audio/mpeg")
                storage_key_creative_audio = k_a
            if body.image_url:
                # image_url is /api/static/ad_creatives/<file>.<ext>
                local_img = _P("/app/backend/static/ad_creatives") / \
                                      _os.path.basename(body.image_url)
                if local_img.is_file():
                    ext = local_img.suffix.lstrip(".") or "webp"
                    k_i = obs.key_ad_creative_image(body.creative_id, ext)
                    st.upload(local_path=str(local_img), key=k_i,
                                      content_type=f"image/{ext}")
                    storage_key_creative_image = k_i
    except Exception as _e:
        import logging as _lg
        _lg.getLogger("bigfm.advertiser_ai").warning(
            "[ai_save] tigris upload failed (local kept): %s", _e)
    doc = {
        "id":                body.creative_id,
        "advertiser_id":  advertiser_id,
        "campaign_id":   None,
        "kind":              f"audio_{body.audio_length_sec}s",
        "title":              body.title,
        "audio_url":      body.audio_url,
        "audio_path":     body.audio_path,
        "audio_source": body.audio_source,
        "image_url":     body.image_url,
        "storage_key_creative_audio": storage_key_creative_audio,
        "storage_key_creative_image": storage_key_creative_image,
        "click_url":       body.click_url,
        "transcript":     body.script,
        "duration_sec": body.duration_sec,
        "status":           status,
        "brand_safety_check": body.brand_safety_check,
        "vast_xml":      body.vast_xml,
        "ai_voice":       body.voice_id,
        "ai_tone":        body.tone,
        "source":          "ai_generated",
        "created_at":   datetime.now(timezone.utc),
    }
    await db.ad_creatives.update_one(
        {"id": body.creative_id}, {"$set": doc}, upsert=True)
    await emit_event(db, name="advertiser_creative_uploaded",
                              props={"source": "ai_generated",
                                        "verdict": verdict, "was_blocked": status == "rejected",
                                        "audio_length_sec": body.audio_length_sec,
                                        "ai_voice": body.voice_id,
                                        "ai_tone":  body.tone,
                                        "audio_source": body.audio_source,
                                        "issues":  (body.brand_safety_check or {}).get("issues") or []},
                              advertiser_id=advertiser_id,
                              creative_id=body.creative_id)
    return {"creative_id": body.creative_id, "status": status,
              "brand_safety_check": body.brand_safety_check}
