"""Phase CLAIM.1 — Station edit-request endpoints.

Owner surface (`/api/stations/owner/*`):
    POST      /api/stations/owner/{station_id}/edit-request       (multipart, body JSON + files)
    GET        /api/stations/owner/edit-requests                              (my history)
    POST      /api/stations/owner/edit-requests/{edit_id}/withdraw

Admin surface (`/api/admin/station-edits/*`):
    GET        /api/admin/station-edits?status=&page=&limit=
    GET        /api/admin/station-edits/{edit_id}                              (with diff)
    POST      /api/admin/station-edits/{edit_id}/approve                  { review_notes? }
    POST      /api/admin/station-edits/{edit_id}/reject                    { review_notes  }
    PATCH    /api/admin/stations/{station_id}/owner-edit-mode      { auto_publish_edits }
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                                              Query, Request, UploadFile)
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import station_edit_request_service as svc
from services import station_upload_service as uploads

log = logging.getLogger("bigfm.claim1.edit_requests_router")

owner_router = APIRouter(tags=["station-owner-edits"])
admin_router = APIRouter(tags=["station-edits-admin"])


def _iso_dt(v):
    from datetime import datetime as _dt
    return v.isoformat() if isinstance(v, _dt) else v


async def _resolve_owner_or_403(db, user: dict, station_id: str
                                                                            ) -> Dict[str, Any]:
    """Return the station doc iff caller is a claim-approved owner."""
    station = await db.imported_radio_stations.find_one({"id": station_id})
    if not station:
        raise HTTPException(404, {"code": "station_not_found"})
    profile = await db.station_owner_profiles.find_one(
        {"user_id": user["user_id"]})
    if not profile or station.get("owner_profile_id") != profile["id"]:
        raise HTTPException(403, {"code": "not_station_owner"})
    return station


# ═════════════════════════════════════════════════════
# Owner surface
# ═════════════════════════════════════════════════════
@owner_router.post("/api/stations/owner/{station_id}/edit-request",
                                                  description=("Owner submits an edit request.  Accepts "
                                                                                "multipart with `proposed_changes` (JSON string) "
                                                                                "plus optional `banner_image` + `description_audio` "
                                                                                "file uploads.  Publishes immediately when the "
                                                                                "station has `auto_publish_edits=true`; otherwise "
                                                                                "moves to admin `pending` queue."))
async def owner_submit_edit(station_id: str, request: Request,
                                                                    proposed_changes: str = Form(default="{}"),
                                                                    banner_image: Optional[UploadFile] = File(default=None),
                                                                    description_audio: Optional[UploadFile] = File(default=None),
                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _resolve_owner_or_403(db, user, station_id)
    if not station.get("owner_editable", True):
        raise HTTPException(403, {"code": "owner_edit_disabled"})
    try:
        parsed = json.loads(proposed_changes) if proposed_changes else {}
        if not isinstance(parsed, dict):
            raise ValueError("proposed_changes_must_be_object")
    except Exception as e:
        raise HTTPException(400, {"code": "bad_proposed_changes",
                                                                  "message": str(e)})

    uploaded: List[Dict[str, Any]] = []
    if banner_image is not None:
        try:
            res = await uploads.persist_banner(
                station_id=station_id, file=banner_image)
            parsed["banner_image_url"] = res["banner_image_url"]
            uploaded.append({"field": "banner_image_url",
                                                      "file_url": res["banner_image_url"],
                                                      "bytes": res["bytes"]})
        except ValueError as e:
            raise HTTPException(400, {"code": str(e)})
    if description_audio is not None:
        try:
            res = await uploads.persist_description_audio(
                station_id=station_id, file=description_audio)
            parsed["description_audio_url"]                    = res["description_audio_url"]
            parsed["description_audio_duration_sec"] = res["description_audio_duration_sec"]
            uploaded.append({"field": "description_audio_url",
                                                      "file_url": res["description_audio_url"],
                                                      "duration_sec": res["description_audio_duration_sec"],
                                                      "bytes": res["bytes"]})
        except ValueError as e:
            raise HTTPException(400, {"code": str(e)})

    try:
        row = await svc.submit_edit_request(
            db, station_id=station_id, owner_user_id=user["user_id"],
            proposed_changes=parsed, uploaded_files=uploaded)
        return {"ok": True, "edit_request": row}
    except LookupError as e:
        raise HTTPException(404, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@owner_router.get("/api/stations/owner/edit-requests",
                                              description="List the current owner's edit-request history.")
async def owner_list_edits(request: Request,
                                                                    status: Optional[str] = Query(None),
                                                                    limit: int = Query(50, ge=1, le=200),
                                                                    offset: int = Query(0, ge=0),
                                                                    user: dict = Depends(current_user)):
    items, total = await svc.list_edit_requests_for_owner(
        request.app.state.db, owner_user_id=user["user_id"],
        status=status, limit=limit, offset=offset)
    return {"items": items, "total": total}


@owner_router.post("/api/stations/owner/edit-requests/{edit_id}/withdraw",
                                                  description="Owner withdraws a pending edit request.")
async def owner_withdraw_edit(edit_id: str, request: Request,
                                                                            user: dict = Depends(current_user)):
    try:
        row = await svc.withdraw_edit_request(
            request.app.state.db, edit_id=edit_id,
            owner_user_id=user["user_id"])
        return {"ok": True, "edit_request": row}
    except LookupError:
        raise HTTPException(404, {"code": "edit_request_not_found"})
    except PermissionError:
        raise HTTPException(403, {"code": "not_owner"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@owner_router.get("/api/stations/owner/my-stations",
                                              description=("List the current user's claimed stations. "
                                                                            "Mirrors /api/owner/dashboard.stations but "
                                                                            "with editable-field fingerprints."))
async def owner_list_stations(request: Request,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    profile = await db.station_owner_profiles.find_one(
        {"user_id": user["user_id"]})
    if not profile:
        return {"items": [], "total": 0}
    items = []
    async for s in db.imported_radio_stations.find(
                                                                                                            {"owner_profile_id": profile["id"],
                                                                                                              "claim_status": "claimed"}):
        items.append({
            "id":                                s["id"], "name": s.get("name"),
            "homepage":                    s.get("homepage"),
            "country":                      s.get("country"),
            "language":                    s.get("language"),
            "logo_url":                    s.get("logo_url"),
            "favicon":                      s.get("favicon"),
            "banner_image_url":     s.get("banner_image_url"),
            "description_text":     s.get("description_text"),
            "description_audio_url": s.get("description_audio_url"),
            "owner_edited_at":       _iso_dt(s.get("owner_edited_at")),
            "owner_editable":         bool(s.get("owner_editable", True)),
            "auto_publish_edits": bool(s.get("auto_publish_edits")),
            "claimed_at":                  _iso_dt(s.get("claimed_at")),
        })
    return {"items": items, "total": len(items)}


@owner_router.get("/api/stations/owner/{station_id}",
                                              description="Owner-scoped station detail (all editable fields).")
async def owner_get_station(station_id: str, request: Request,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _resolve_owner_or_403(db, user, station_id)
    editable = {k: station.get(k) for k in svc.OWNER_EDITABLE_FIELDS}
    return {"station_id": station_id,
                        "editable_fields": editable,
                        "auto_publish_edits": bool(station.get("auto_publish_edits")),
                        "owner_editable": bool(station.get("owner_editable", True)),
                        "owner_edited_at": _iso_dt(station.get("owner_edited_at"))}


# ═════════════════════════════════════════════════════
# Admin surface
# ═════════════════════════════════════════════════════
@admin_router.get("/api/admin/station-edits",
                                              description="List station edit requests (default: pending).")
async def admin_list_edits(request: Request,
                                                                    status: Optional[str] = Query("pending"),
                                                                    limit: int = Query(50, ge=1, le=200),
                                                                    offset: int = Query(0, ge=0),
                                                                    admin: dict = Depends(require_admin)):
    items, total = await svc.list_edit_requests_for_admin(
        request.app.state.db, status=status, limit=limit, offset=offset)
    return {"items": items, "total": total,
                        "limit": limit, "offset": offset}


@admin_router.get("/api/admin/station-edits/{edit_id}",
                                              description="Edit request detail + before/after diff.")
async def admin_get_edit(edit_id: str, request: Request,
                                                        admin: dict = Depends(require_admin)):
    row = await svc.get_edit_request(request.app.state.db, edit_id=edit_id)
    if not row:
        raise HTTPException(404, {"code": "edit_request_not_found"})
    return row


class ReviewIn(BaseModel):
    review_notes: Optional[str] = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    review_notes: str = Field(min_length=3, max_length=500)


@admin_router.post("/api/admin/station-edits/{edit_id}/approve",
                                                  description="Approve an edit request → apply changes to station.")
async def admin_approve_edit(edit_id: str, body: ReviewIn, request: Request,
                                                                            admin: dict = Depends(require_admin)):
    try:
        row = await svc.approve_edit_request(
            request.app.state.db, edit_id=edit_id,
            admin_user_id=admin["user_id"],
            review_notes=body.review_notes)
        return {"ok": True, "edit_request": row}
    except LookupError:
        raise HTTPException(404, {"code": "edit_request_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


@admin_router.post("/api/admin/station-edits/{edit_id}/reject",
                                                  description="Reject an edit request (requires review_notes).")
async def admin_reject_edit(edit_id: str, body: RejectIn, request: Request,
                                                                          admin: dict = Depends(require_admin)):
    try:
        row = await svc.reject_edit_request(
            request.app.state.db, edit_id=edit_id,
            admin_user_id=admin["user_id"],
            review_notes=body.review_notes)
        return {"ok": True, "edit_request": row}
    except LookupError:
        raise HTTPException(404, {"code": "edit_request_not_found"})
    except ValueError as e:
        raise HTTPException(409, {"code": str(e)})


class OwnerEditModeIn(BaseModel):
    auto_publish_edits: bool


@admin_router.patch(
    "/api/admin/stations/{station_id}/owner-edit-mode",
    description=("Toggle per-station auto-publish for trusted owners. "
                              "When true, subsequent owner edits skip the admin queue."))
async def admin_set_owner_edit_mode(station_id: str, body: OwnerEditModeIn,
                                                                                        request: Request,
                                                                                        admin: dict = Depends(require_admin)):
    try:
        return await svc.set_auto_publish(
            request.app.state.db, station_id=station_id,
            admin_user_id=admin["user_id"],
            enabled=body.auto_publish_edits)
    except LookupError:
        raise HTTPException(404, {"code": "station_not_found"})
