"""Phase SC.1 — Stripe Connect endpoints.

Routes:
    POST /api/stripe/connect/onboarding/start        merchant-owner OR admin
    POST /api/stripe/connect/status/refresh          merchant-owner OR admin
    GET  /api/stripe/connect/status/{merchant_id}    merchant-owner OR admin
    POST /api/stripe/connect/dashboard-link          merchant-owner OR admin
    GET  /api/admin/stripe/connect/all-merchants     admin only
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field

from auth import current_user, require_admin
from services import stripe_connect_service as connect

logger = logging.getLogger("bigfm.stripe_connect_routes")

router = APIRouter(prefix="/api/stripe/connect", tags=["stripe_connect"])
admin_router = APIRouter(prefix="/api/admin/stripe/connect",
                                        tags=["stripe_connect_admin"])


# ─── Auth helpers ─────────────────────────────────────────────────
async def _resolve_merchant_for_actor(db, merchant_id: str, user: dict) -> dict:
    """Load the merchant + verify the actor is either the owner or an admin.

    The `businesses` collection is a mixed pool — some rows carry a
    `business_id` (public listing pool), others only carry `_id` as their
    identifier (owner-managed QA fixtures).  Try both keys so admins can
    operate on any merchant regardless of provenance."""
    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        biz = await db.businesses.find_one({"_id": merchant_id})
    if not biz:
        raise HTTPException(404, "merchant_not_found")
    is_admin = (user.get("role") == "admin"
                    or bool(user.get("is_admin", False)))
    if biz.get("owner_user_id") != user["user_id"] and not is_admin:
        raise HTTPException(403, "not_merchant_owner_or_admin")
    return biz


def _biz_key(biz: dict) -> str:
    """The identifier we use for update queries — prefer `business_id`,
    fall back to `_id` for rows that lack it."""
    return biz.get("business_id") or biz.get("_id") or ""


def _frontend_url() -> str:
    """Return the browser-facing base URL.  Prefer FRONTEND_URL, then the
    marketing-style FRONTEND_BASE_URL, then the preview default."""
    url = (os.environ.get("FRONTEND_URL")
              or os.environ.get("FRONTEND_BASE_URL") or "").strip()
    if url:
        return url.rstrip("/")
    return "https://mobile-games-v2.preview.emergentagent.com"


# ─── Bodies ───────────────────────────────────────────────────────
class StartOnboardingBody(BaseModel):
    merchant_id: str = Field(min_length=3, max_length=64)
    email: Optional[EmailStr] = None
    country: str = Field(default="US", min_length=2, max_length=2)


class MerchantIdBody(BaseModel):
    merchant_id: str = Field(min_length=3, max_length=64)


# ─── Endpoints ────────────────────────────────────────────────────
@router.post("/onboarding/start")
async def onboarding_start(body: StartOnboardingBody, request: Request,
                                        user: dict = Depends(current_user)):
    """Create (or reuse) a connected account and mint a fresh Account Link.
    Marks the merchant as onboarding-in-progress."""
    db = request.app.state.db
    biz = await _resolve_merchant_for_actor(db, body.merchant_id, user)
    biz_key = _biz_key(biz)
    filter_by = "business_id" if biz.get("business_id") else "_id"

    email = (body.email or biz.get("owner_email") or biz.get("email")
                or f"merchant+{biz_key}@bigfm.app")

    acct_id = biz.get("stripe_account_id")
    if not acct_id:
        try:
            created = await connect.create_connected_account(
                merchant_id=biz_key, email=email, country=body.country)
            acct_id = created["stripe_account_id"]
        except Exception as e:
            logger.exception("[connect] create_connected_account failed")
            raise HTTPException(502, f"stripe_connect_create_failed: {str(e)[:200]}")
        await db.businesses.update_one(
            {filter_by: biz_key},
            {"$set": {"stripe_account_id": acct_id,
                          "stripe_onboarding_status": "onboarding_in_progress"}})
    else:
        await db.businesses.update_one(
            {filter_by: biz_key},
            {"$set": {"stripe_onboarding_status": "onboarding_in_progress"}})

    fe = _frontend_url()
    try:
        onboarding_url = await connect.create_onboarding_link(
            stripe_account_id=acct_id,
            return_url=f"{fe}/merchant/onboarding/complete?merchant_id={biz_key}",
            refresh_url=f"{fe}/merchant/onboarding/refresh?merchant_id={biz_key}")
    except Exception as e:
        logger.exception("[connect] create_onboarding_link failed")
        raise HTTPException(502, f"stripe_connect_link_failed: {str(e)[:200]}")

    return {
        "ok": True,
        "onboarding_url": onboarding_url,
        "stripe_account_id": acct_id,
        "merchant_id": biz_key,
    }


@router.post("/status/refresh")
async def status_refresh(body: MerchantIdBody, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant_for_actor(db, body.merchant_id, user)
    acct_id = biz.get("stripe_account_id")
    if not acct_id:
        raise HTTPException(400, "merchant_has_no_connected_account")
    biz_key = _biz_key(biz)
    filter_by = "business_id" if biz.get("business_id") else "_id"
    try:
        return await connect.refresh_account_status(
            stripe_account_id=acct_id, merchant_id=biz_key,
            db=db, filter_by=filter_by)
    except Exception as e:
        logger.exception("[connect] refresh_account_status failed")
        raise HTTPException(502, f"stripe_connect_refresh_failed: {str(e)[:200]}")


@router.get("/status/{merchant_id}")
async def status_cached(merchant_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    """Last-known status from Mongo (no live Stripe call)."""
    db = request.app.state.db
    biz = await _resolve_merchant_for_actor(db, merchant_id, user)
    return _merchant_status_view(biz)


@router.post("/dashboard-link")
async def dashboard_link(body: MerchantIdBody, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_merchant_for_actor(db, body.merchant_id, user)
    acct_id = biz.get("stripe_account_id")
    if not acct_id:
        raise HTTPException(400, "merchant_has_no_connected_account")
    if not biz.get("stripe_details_submitted"):
        # Stripe rejects login-link creation until onboarding is complete.
        raise HTTPException(400, "onboarding_incomplete")
    try:
        url = await connect.create_login_link(acct_id)
    except Exception as e:
        logger.exception("[connect] create_login_link failed")
        raise HTTPException(502, f"stripe_connect_login_link_failed: {str(e)[:200]}")
    return {"ok": True, "login_url": url, "merchant_id": body.merchant_id}


# ─── Admin — list-all ─────────────────────────────────────────────
@admin_router.get("/all-merchants")
async def admin_all_merchants(request: Request,
                                          _admin: dict = Depends(require_admin),
                                          limit: int = Query(50, ge=1, le=500),
                                          offset: int = Query(0, ge=0),
                                          status: Optional[str] = Query(None)):
    """Paginated list of every merchant with their Connect status snapshot."""
    db = request.app.state.db
    q: dict = {}
    if status:
        if status not in connect.VALID_STATUSES:
            raise HTTPException(400, f"invalid_status:{status}")
        q["stripe_onboarding_status"] = status
    total = await db.businesses.count_documents(q)
    cur = (db.businesses.find(q).sort("created_at", -1).skip(offset).limit(limit))
    items: list[dict] = []
    async for b in cur:
        items.append(_merchant_status_view(b))
    return {"total": total, "count": len(items),
              "offset": offset, "limit": limit, "items": items}


# ─── Serialisation ─────────────────────────────────────────────────
def _merchant_status_view(b: dict) -> dict:
    synced = b.get("stripe_status_synced_at")
    return {
        # `merchant_id` is what admin actions POST back with.  Prefer the
        # canonical `business_id`; fall back to `_id` for legacy fixture
        # rows that lack it.
        "merchant_id": b.get("business_id") or b.get("_id"),
        "business_id": b.get("business_id"),
        "name": b.get("name"),
        "slug": b.get("slug"),
        "category": b.get("category"),
        "owner_user_id": b.get("owner_user_id"),
        "stripe_account_id": b.get("stripe_account_id"),
        "stripe_onboarding_status": b.get("stripe_onboarding_status") or "not_started",
        "charges_enabled": bool(b.get("stripe_charges_enabled")),
        "payouts_enabled": bool(b.get("stripe_payouts_enabled")),
        "details_submitted": bool(b.get("stripe_details_submitted")),
        "requirements_currently_due": b.get("stripe_requirements_currently_due") or [],
        "requirements_past_due": b.get("stripe_requirements_past_due") or [],
        "requirements_disabled_reason": b.get("stripe_requirements_disabled_reason"),
        "capabilities": b.get("stripe_capabilities") or {},
        "status_synced_at": (synced.isoformat() if hasattr(synced, "isoformat")
                                    else synced),
    }


__all__ = ["router", "admin_router"]
