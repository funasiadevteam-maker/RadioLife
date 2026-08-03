"""Phase D — AI RJ Persona HTTP routes.

Public reads NEVER leak `persona_prompt` (or `created_by_user_id`).
Admin routes are gated via `role == "admin"` on the current user.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from core.config import ELEVENLABS_API_KEY
from services import rj_persona_service as _svc

logger = logging.getLogger("bigfm.rj_personas.routes")

router = APIRouter(tags=["rj-personas"])


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(403, {"code": "admin_required"})


# ── Pydantic bodies ─────────────────────────────────────────────
class PersonaBody(BaseModel):
    name:                    Optional[str]   = None
    tagline:              Optional[str]   = None
    description:      Optional[str]   = None
    voice_id:            Optional[str]   = None
    voice_provider:  Optional[str]   = Field(None,
                                                                                    description="elevenlabs|openai_tts")
    language:            Optional[str]   = None
    personality:      Optional[str]   = Field(None,
                                                                                    description="energetic|chill|news|"
                                                                                                          "party|devotional|custom")
    persona_prompt:  Optional[str]   = None
    sample_audio_url: Optional[str] = None
    cover_image_url:  Optional[str] = None
    status:                Optional[str]   = Field(None,
                                                                                    description="draft|active|archived")
    is_default:        Optional[bool] = None


class AssignBody(BaseModel):
    persona_id: str
    priority:    int = Field(100, ge=0, le=10_000)


class PreviewBody(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)


# ── Admin: personas CRUD ────────────────────────────────────────
@router.post("/api/admin/rj/personas",
                          description="Create a persona (admin-only).")
async def create_persona(body: PersonaBody, request: Request,
                                                    user: dict = Depends(current_user)):
    _require_admin(user)
    payload = body.model_dump(exclude_none=True)
    try:
        row = await _svc.create_persona(request.app.state.db,
                                                                            body=payload,
                                                                            actor_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    return {"persona": row}


@router.get("/api/admin/rj/personas",
                        description="List personas (admin-only, includes "
                                                "persona_prompt).")
async def list_personas_admin(request: Request,
                                                              status: Optional[str] = None,
                                                              include_archived: bool = False,
                                                              user: dict = Depends(current_user)):
    _require_admin(user)
    rows = await _svc.list_personas(request.app.state.db,
                                                                        status=status,
                                                                        include_archived=include_archived,
                                                                        admin=True)
    return {"items": rows, "count": len(rows)}


@router.get("/api/admin/rj/personas/{persona_id}",
                        description="Read one persona (admin-only, full detail).")
async def get_persona_admin(persona_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    _require_admin(user)
    row = await _svc.get_persona(request.app.state.db,
                                                                persona_id=persona_id, admin=True)
    if not row:
        raise HTTPException(404, {"code": "persona_not_found"})
    return {"persona": row}


@router.patch("/api/admin/rj/personas/{persona_id}",
                            description="Edit a persona (admin-only).")
async def patch_persona(persona_id: str, body: PersonaBody,
                                                request: Request,
                                                user: dict = Depends(current_user)):
    _require_admin(user)
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, {"code": "empty_patch"})
    try:
        row = await _svc.update_persona(request.app.state.db,
                                                                        persona_id=persona_id, patch=patch)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    if not row:
        raise HTTPException(404, {"code": "persona_not_found"})
    return {"persona": row}


@router.delete("/api/admin/rj/personas/{persona_id}",
                              description="Soft-delete: status → archived + drops all "
                                                        "station assignments.")
async def delete_persona(persona_id: str, request: Request,
                                                  user: dict = Depends(current_user)):
    _require_admin(user)
    ok = await _svc.archive_persona(request.app.state.db,
                                                                    persona_id=persona_id)
    if not ok:
        raise HTTPException(404, {"code": "persona_not_found"})
    return {"ok": True, "status": "archived"}


# ── Admin: preview generation ───────────────────────────────────
@router.post("/api/admin/rj/personas/{persona_id}/preview",
                          description="Full pipeline: LLM script → TTS synth → "
                                                    "Tigris upload → rj_segments row.  Returns "
                                                    "the playable audio_url.")
async def preview_persona(persona_id: str, body: PreviewBody,
                                                    request: Request,
                                                    user: dict = Depends(current_user)):
    _require_admin(user)
    try:
        res = await _svc.generate_preview(request.app.state.db,
                                                                              persona_id=persona_id,
                                                                              context=body.context or {},
                                                                              actor_user_id=user["user_id"])
    except ValueError as e:
        if str(e) == "persona_not_found":
            raise HTTPException(404, {"code": "persona_not_found"})
        raise HTTPException(400, {"code": str(e)})
    except RuntimeError as e:
        code = str(e)
        # ELEVENLABS_API_KEY missing → 503 per acceptance criterion #6.
        if "elevenlabs_api_key_missing" in code \
                or "ELEVENLABS_API_KEY" in code:
            raise HTTPException(503, {"code": "elevenlabs_not_configured",
                                                                "message": "Set ELEVENLABS_API_KEY "
                                                                                          "on the backend to enable "
                                                                                          "preview."})
        raise HTTPException(502, {"code": "tts_upstream_error",
                                                            "message": code})
    except Exception as e:
        logger.exception("[rj_personas] preview failed")
        raise HTTPException(500, {"code": "preview_failed",
                                                            "message": str(e)})
    return res


# ── Admin: station assignments ──────────────────────────────────
@router.post("/api/admin/rj/stations/{station_id}/assignments",
                          description="Assign a persona to a station.  Idempotent "
                                                    "on (station_id, persona_id).")
async def assign(station_id: str, body: AssignBody, request: Request,
                                  user: dict = Depends(current_user)):
    _require_admin(user)
    try:
        row = await _svc.assign_persona(request.app.state.db,
                                                                        station_id=station_id,
                                                                        persona_id=body.persona_id,
                                                                        priority=body.priority,
                                                                        actor_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(400 if str(e) == "persona_archived" else 404,
                                                {"code": str(e)})
    return {"assignment": row}


@router.delete(
    "/api/admin/rj/stations/{station_id}/assignments/{persona_id}",
    description="Remove a persona from a station (idempotent).")
async def unassign(station_id: str, persona_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    _require_admin(user)
    ok = await _svc.unassign_persona(request.app.state.db,
                                                                        station_id=station_id,
                                                                        persona_id=persona_id)
    return {"ok": True, "removed": ok}


@router.get("/api/admin/rj/stations/{station_id}/assignments",
                        description="Admin — list station assignments with full "
                                                "persona detail.")
async def list_station_assignments_admin(station_id: str,
                                                                                          request: Request,
                                                                                          user: dict = Depends(current_user)):
    _require_admin(user)
    rows = await _svc.list_station_personas(request.app.state.db,
                                                                                        station_id=station_id,
                                                                                        only_active=False)
    return {"items": rows, "count": len(rows), "station_id": station_id}


# ── Public reads ────────────────────────────────────────────────
@router.get("/api/rj/personas/{persona_id}",
                        description="Public read — persona_prompt is stripped.")
async def get_persona_public(persona_id: str, request: Request):
    row = await _svc.get_persona(request.app.state.db,
                                                                persona_id=persona_id, admin=False)
    if not row:
        raise HTTPException(404, {"code": "persona_not_found"})
    return {"persona": row}


@router.get("/api/rj/stations/{station_id}/personas",
                        description="Public — active personas assigned to a station "
                                                "in priority order.  persona_prompt not exposed.")
async def list_station_personas_public(station_id: str,
                                                                                  request: Request):
    rows = await _svc.list_station_personas(request.app.state.db,
                                                                                        station_id=station_id,
                                                                                        only_active=True)
    return {"items": rows, "count": len(rows), "station_id": station_id}

# Phase I — advertiser-facing personas listing (public, active-only, no
# admin_prompt).  Enables the sponsored-read create wizard's persona
# picker without exposing the admin catalog.
@router.get("/api/rj/personas",
                        description="Public — list of active personas (voice catalog).  "
                                                "persona_prompt stripped.")
async def list_personas_public(request: Request):
    rows = await _svc.list_personas(request.app.state.db,
                                                                        status="active", admin=False)
    return {"items": rows, "count": len(rows)}



# ── Admin: health probe ─────────────────────────────────────────
@router.get("/api/admin/rj/health",
                        description="Reports whether ElevenLabs is configured.")
async def rj_health(user: dict = Depends(current_user)):
    _require_admin(user)
    return {"elevenlabs_configured": bool(ELEVENLABS_API_KEY),
                    "emergent_llm_configured":
                        bool(__import__("os").environ.get("EMERGENT_LLM_KEY"))}


__all__ = ["router"]
