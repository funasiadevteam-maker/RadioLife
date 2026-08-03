"""Phase 42-C — Station claim listener-facing endpoints.

Endpoints (all routed under `/api/radio/claims`):
    POST /api/radio/claims                                — submit
        (Phase CLAIM.1) accepts EITHER JSON body OR multipart form
        with `payload` JSON string + up to 6 `proof_files` (business
        card, business email screenshot, gov ID, station license, etc.).
    GET  /api/radio/claims/my                          — listener's own claims
    GET  /api/radio/claims/{claim_id}              — owner-scoped
    POST /api/radio/claims/verify/{token}        — public, completes email flow
    POST /api/radio/claims/{claim_id}/abandon — claimer-only
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                                              UploadFile)

from auth import current_user, current_user_optional
from services.station_claim_service import (
    auto_verify_or_queue_admin, promote_claim_to_owner,
)
from services.station_upload_service import persist_proof_documents

log = logging.getLogger("bigfm.station_claims.public")

router = APIRouter(prefix="/api/radio/claims",
                                    tags=["station-claims"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _strip(d: dict) -> dict:
    out = {**d}
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ──────────────────── POST /api/radio/claims ────────────────────
async def _submit_claim_core(
    *, db, user: Dict[str, Any], payload: Dict[str, Any],
      proof_files: Optional[List[UploadFile]] = None,
      document_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Shared implementation for the JSON + multipart variants."""
    station_id = (payload or {}).get("station_id", "")
    if not station_id or not station_id.startswith("imp_"):
        raise HTTPException(400, {"code": "invalid_station_id",
                                                                  "message": "Only imported (imp_*) stations can be claimed."})
    organization_name = (payload or {}).get("organization_name", "").strip()
    contact_email = (payload or {}).get("contact_email", "").strip()
    contact_role = (payload or {}).get("contact_role", "").strip()
    contact_name = (payload or {}).get("contact_name", "").strip()
    contact_phone = (payload or {}).get("contact_phone", "").strip()
    business_name = (payload or {}).get("business_name", "").strip()
    business_email_domain = (payload or {}).get("business_email_domain", "").strip()
    agreement_accepted = bool((payload or {}).get("agreement_accepted"))
    if not organization_name:
        raise HTTPException(400, {"code": "organization_name_required"})
    if not contact_email or "@" not in contact_email:
        raise HTTPException(400, {"code": "contact_email_invalid"})
    if not contact_role:
        raise HTTPException(400, {"code": "contact_role_required"})
    if not agreement_accepted:
        raise HTTPException(400, {"code": "agreement_not_accepted",
                                                                  "message": "Partner terms must be accepted."})

    station = await db.imported_radio_stations.find_one({"id": station_id})
    if not station or not station.get("active"):
        raise HTTPException(404, {"code": "station_not_found"})
    if station.get("claim_status") == "claimed":
        raise HTTPException(409, {"code": "already_claimed",
                                                                  "claim_id": station.get("claim_id")})

    dup = await db.radio_station_claims.find_one({
        "station_id": station_id,
        "claimed_by_user_id": user["user_id"],
        "claim_status": {"$in": ["submitted", "verifying", "approved"]},
    })
    if dup:
        raise HTTPException(409, {"code": "active_claim_exists",
                                                                  "claim_id": dup["id"],
                                                                  "claim_status": dup.get("claim_status")})

    now = _now()
    claim_id = _new_id("rsc")
    token = uuid.uuid4().hex

    # Phase CLAIM.1 — proof docs (multipart only).
    accepted_proofs: List[Dict[str, Any]] = []
    if proof_files:
        try:
            accepted_proofs, rejected = await persist_proof_documents(
                claim_id=claim_id, files=proof_files,
                document_types=document_types)
        except ValueError as e:
            raise HTTPException(400, {"code": str(e)})
        if rejected:
            # If ANY doc is rejected, reject the whole submission so the
            # user can fix + retry with clean files.
            raise HTTPException(400, {"code": "proof_docs_rejected",
                                                                    "rejected": rejected})

    doc: Dict[str, Any] = {
        "_id": claim_id, "id": claim_id,
        "station_id": station_id,
        "station_name_snapshot": station.get("name"),
        "station_homepage_snapshot": station.get("homepage"),
        "claimed_by_user_id": user["user_id"],
        "claimed_by_email": user.get("email"),
        "organization_name": organization_name,
        "contact_email": contact_email,
        "contact_role": contact_role,
        # Phase CLAIM.1 richer claimant fields.
        "contact_name": contact_name or None,
        "contact_phone": contact_phone or None,
        "business_name": business_name or None,
        "business_email_domain": business_email_domain or None,
        # Proof docs.
        "proof_documents":       accepted_proofs,
        "has_proof_documents": len(accepted_proofs) > 0,
        "verification_method": None,
        "verification_status": "pending",
        "verification_token": token,
        "verification_attempted_at": None,
        "verification_completed_at": None,
        "agreement_status": "signed",
        "agreement_signed_at": now,
        "agreement_version": "v1.0",
        "admin_review_status": "not_required",
        "admin_reviewer_id": None,
        "admin_reviewed_at": None,
        "admin_rejection_reason": None,
        "claim_status": "submitted",
        "created_at": now, "updated_at": now,
    }
    # Decide path: email_domain auto-verify vs manual_admin.
    # Phase CLAIM.1: presence of proof docs FORCES the admin manual review
    # path even when the email domain matches, so the admin sees the
    # documents.
    if accepted_proofs:
        doc["verification_method"] = "manual_admin"
        doc["verification_status"] = "pending"
        doc["claim_status"] = "submitted"
        doc["admin_review_status"] = "pending"
        doc["verification_attempted_at"] = now
        doc["updated_at"] = now
    else:
        transition = await auto_verify_or_queue_admin(
            db, claim=doc, station=station)
        doc.update(transition)
    await db.radio_station_claims.insert_one(doc)

    # Touch the station to reflect "claim_pending" if not yet claimed.
    if station.get("claim_status") != "claimed":
        await db.imported_radio_stations.update_one(
            {"id": station_id},
            {"$set": {"claim_status": "claim_pending"}})

    return {"ok": True, "claim": _strip(doc)}


@router.post("",
                          description=(
                              "Submit a claim of ownership for an `imp_*` station. "
                              "Accepts JSON body OR multipart form with `payload` "
                              "JSON string + `proof_files[]` + `document_types[]`. "
                              "Auto-verifies via email-domain match when no proof "
                              "docs are attached and the contact email's domain "
                              "matches the station's homepage; otherwise routes "
                              "to the admin queue."))
async def submit_claim(request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload_raw = form.get("payload") or "{}"
        try:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else {}
        except Exception:
            raise HTTPException(400, {"code": "bad_payload_json"})
        proof_files: List[UploadFile] = []
        for k, v in form.multi_items():
            if k == "proof_files" and hasattr(v, "filename"):
                proof_files.append(v)
        document_types = [t for k, t in form.multi_items()
                                                if k == "document_types" and isinstance(t, str)]
        return await _submit_claim_core(
            db=db, user=user, payload=payload,
            proof_files=proof_files, document_types=document_types)
    # JSON body path (unchanged from Phase 42-C).
    payload = await request.json()
    return await _submit_claim_core(db=db, user=user, payload=payload)


# ──────────────────── GET /api/radio/claims/my ────────────────────
@router.get("/my",
                        description=("Caller's own claims, newest first."))
async def list_my_claims(request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    cur = db.radio_station_claims.find(
        {"claimed_by_user_id": user["user_id"]}) \
              .sort("created_at", -1).limit(50)
    items = [_strip(r) async for r in cur]
    return {"items": items, "total": len(items)}


# ──────────────────── GET /api/radio/claims/{id} ────────────────────
@router.get("/{claim_id}",
                        description=("Single claim — owner-scoped (or admin)."))
async def get_claim(claim_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    row = await db.radio_station_claims.find_one({"id": claim_id})
    if not row:
        raise HTTPException(404, {"code": "claim_not_found"})
    if (row["claimed_by_user_id"] != user["user_id"]
                and user.get("role") != "admin"):
        raise HTTPException(403, {"code": "forbidden"})
    return _strip(row)


# ──────────────────── POST /api/radio/claims/verify/{token} ────────────────────
@router.post("/verify/{verification_token}",
                          description=("Public — completes the email-domain "
                                                    "verification flow.  Anonymous-friendly "
                                                    "so the link can be opened from an "
                                                    "email client without a session."))
async def verify_claim(verification_token: str, request: Request,
                                              user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    claim = await db.radio_station_claims.find_one(
        {"verification_token": verification_token})
    if not claim:
        raise HTTPException(404, {"code": "verification_token_not_found"})
    if claim["claim_status"] in {"approved", "rejected", "abandoned"}:
        return {"ok": True, "already_finalized": True,
                      "claim_status": claim["claim_status"],
                      "station_id": claim["station_id"]}
    if claim.get("verification_method") != "email_domain":
        raise HTTPException(400, {"code": "verification_not_email_path",
                                                                    "method": claim.get("verification_method")})
    now = _now()
    patch = {
        "verification_status": "email_verified",
        "verification_completed_at": now,
        "claim_status": "approved",
        "updated_at": now,
    }
    await db.radio_station_claims.update_one(
        {"id": claim["id"]}, {"$set": patch})
    promoted = await promote_claim_to_owner(db,
                                                                                            claim={**claim, **patch})
    return {"ok": True,
                  "claim_id": claim["id"],
                  "claim_status": "approved",
                  "station_id": claim["station_id"],
                  "station_name": claim.get("station_name_snapshot"),
                  "profile_id": promoted["profile_id"]}


# ──────────────────── POST /api/radio/claims/{id}/abandon ────────────────────
@router.post("/{claim_id}/abandon",
                          description=("Claimer abandons their own claim."))
async def abandon_claim(claim_id: str, request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    row = await db.radio_station_claims.find_one({"id": claim_id})
    if not row:
        raise HTTPException(404, {"code": "claim_not_found"})
    if row["claimed_by_user_id"] != user["user_id"]:
        raise HTTPException(403, {"code": "forbidden"})
    if row["claim_status"] in {"approved", "rejected", "abandoned"}:
        raise HTTPException(409, {"code": "claim_already_finalized",
                                                                    "claim_status": row["claim_status"]})
    now = _now()
    await db.radio_station_claims.update_one(
        {"id": claim_id},
        {"$set": {"claim_status": "abandoned", "updated_at": now}})
    # Clear pending flag from station if no other active claims exist.
    other = await db.radio_station_claims.find_one({
        "station_id": row["station_id"],
        "claim_status": {"$in": ["submitted", "verifying"]},
        "id": {"$ne": claim_id},
    })
    if not other:
        await db.imported_radio_stations.update_one(
            {"id": row["station_id"], "claim_status": "claim_pending"},
            {"$set": {"claim_status": "unclaimed"}})
    return {"ok": True, "claim_id": claim_id, "claim_status": "abandoned"}


# ──────────────────── owner profile ────────────────────
profile_router = APIRouter(prefix="/api/owner", tags=["station-owner"])


@profile_router.get("/dashboard",
                                            description=(
                                                "Lists the user's claimed stations + basic stats. "
                                                "Returns `{stations: [...], profile: {...}}`."))
async def owner_dashboard(request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    profile = await db.station_owner_profiles.find_one(
        {"user_id": user["user_id"]})
    stations: list = []
    if profile:
        async for s in db.imported_radio_stations.find(
                {"owner_profile_id": profile["id"], "claim_status": "claimed"}):
            favorites_count = 0
            try:
                favorites_count = await db.user_favorite_stations.count_documents(
                    {"station_id": s["id"]})
            except Exception:
                pass
            stations.append({
                "id": s["id"], "name": s.get("name"),
                "homepage": s.get("homepage"),
                "country": s.get("country"),
                "language": s.get("language"),
                "favicon": s.get("favicon"),
                "click_count": s.get("click_count", 0),
                "votes": s.get("votes", 0),
                "favorites_count": favorites_count,
                "owner_overrides": s.get("owner_overrides") or {},
                "claimed_at": (s.get("claimed_at").isoformat()
                                                if isinstance(s.get("claimed_at"), datetime)
                                                else s.get("claimed_at")),
            })
    return {"profile": _strip(profile) if profile else None,
                  "stations": stations,
                  "station_count": len(stations)}


@profile_router.patch("/stations/{station_id}",
                                              description=(
                                                  "Owner-only patch — overrides Radio Browser "
                                                  "metadata for a claimed station (logo, description, "
                                                  "market, bio).  Returns the updated station card."))
async def patch_owner_station(station_id: str, payload: dict,
                                                                        request: Request,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    profile = await db.station_owner_profiles.find_one(
        {"user_id": user["user_id"]})
    if not profile:
        raise HTTPException(403, {"code": "no_owner_profile"})
    s = await db.imported_radio_stations.find_one({"id": station_id})
    if not s or s.get("owner_profile_id") != profile["id"]:
        raise HTTPException(403, {"code": "not_station_owner"})
    overrides: Dict[str, Any] = s.get("owner_overrides") or {}
    for k in ("logo_url", "description", "market_city",
                          "market_country", "bio"):
        if k in payload:
            overrides[k] = (payload[k] or "").strip() or None
    now = _now()
    await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"owner_overrides": overrides, "updated_at": now}})
    return {"ok": True, "station_id": station_id,
                  "owner_overrides": overrides}
