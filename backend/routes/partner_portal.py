"""Partner API self-serve portal (web dashboard) + admin management.

Lets a logged-in advertiser create their Partner account and mint/revoke
API keys + OAuth2 clients for the public RadioLife Ads API (`/api/v1`).
Raw secrets are shown exactly once, on creation.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import partner_api as pa

router = APIRouter(prefix="/api/partner", tags=["partner-portal"])
admin_router = APIRouter(prefix="/api/admin/partner-api", tags=["admin-partner-api"])


class PartnerCreate(BaseModel):
    name: str
    contact_email: str


class KeyCreate(BaseModel):
    environment: str = "live"          # "live" | "sandbox"
    label: Optional[str] = None
    scopes: Optional[list[str]] = None


async def _my_partner(db, user: dict) -> Optional[dict]:
    return await db.partner_accounts.find_one({"owner_user_id": user.get("user_id")})


# ── self-serve ──────────────────────────────────────────────────────
@router.get("/account")
async def get_account(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        return {"exists": False, "scopes": pa.SCOPES}
    creds = await pa.list_credentials(db, partner_id=p["partner_id"])
    return {"exists": True, "partner": pa._clean(p), "scopes": pa.SCOPES, **creds}


@router.post("/account")
async def create_account(body: PartnerCreate, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await pa.get_or_create_partner(
        db, owner_user_id=user.get("user_id"),
        name=body.name, contact_email=body.contact_email)
    return {"partner": p}


@router.post("/keys")
async def create_key(body: KeyCreate, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    return await pa.issue_api_key(db, partner_id=p["partner_id"],
                                  environment=body.environment,
                                  scopes=body.scopes, label=body.label)


@router.post("/keys/{key_id}/revoke")
async def revoke_key(key_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    ok = await pa.revoke_api_key(db, partner_id=p["partner_id"], key_id=key_id)
    if not ok:
        raise HTTPException(404, {"code": "key_not_found"})
    return {"ok": True, "key_id": key_id, "revoked": True}


@router.post("/oauth-clients")
async def create_oauth_client(body: KeyCreate, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    return await pa.issue_oauth_client(db, partner_id=p["partner_id"],
                                       environment=body.environment,
                                       scopes=body.scopes, label=body.label)


@router.post("/oauth-clients/{client_id}/revoke")
async def revoke_oauth_client(client_id: str, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    ok = await pa.revoke_oauth_client(db, partner_id=p["partner_id"], client_id=client_id)
    if not ok:
        raise HTTPException(404, {"code": "client_not_found"})
    return {"ok": True, "client_id": client_id, "revoked": True}


# ── admin ───────────────────────────────────────────────────────────
@admin_router.get("/partners")
async def admin_list_partners(request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    out = [pa._clean(p) async for p in db.partner_accounts.find({}).sort("created_at", -1).limit(200)]
    return {"items": out, "count": len(out)}


class AdminPartnerCreate(BaseModel):
    name: str
    contact_email: str
    owner_user_id: Optional[str] = None


@admin_router.post("/partners")
async def admin_create_partner(body: AdminPartnerCreate, request: Request,
                               _a=Depends(require_admin)):
    db = request.app.state.db
    p = await pa.get_or_create_partner(
        db, owner_user_id=body.owner_user_id or f"admin:{pa._gen('mgd')}",
        name=body.name, contact_email=body.contact_email)
    return {"partner": p}


@admin_router.post("/partners/{partner_id}/keys")
async def admin_issue_key(partner_id: str, body: KeyCreate, request: Request,
                          _a=Depends(require_admin)):
    db = request.app.state.db
    if not await pa.get_partner(db, partner_id):
        raise HTTPException(404, {"code": "partner_not_found"})
    return await pa.issue_api_key(db, partner_id=partner_id, environment=body.environment,
                                  scopes=body.scopes, label=body.label)


__all__ = ["router", "admin_router"]
