"""Phase 42-D2 — Admin endpoints for direct subscription grants + voucher codes.

  • POST /api/admin/subscriptions/grant  { user_id, plan, duration_days }
  • GET  /api/admin/vouchers
  • POST /api/admin/vouchers/create
  • POST /api/admin/vouchers/{voucher_id}/revoke

`plan ∈ {premium, trial}`.  All grants go through `subscription_gate`
helpers so the same stamps the trial endpoints write are kept.

`vouchers` collection: `{voucher_id, code (unique), plan, duration_days,
max_redemptions, redemptions_count, expires_at, active, created_by,
created_at, revoked_at}`.  Code is case-insensitive (stored uppercased).
"""
from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_admin

log = logging.getLogger("bigfm.admin_subscriptions")
router = APIRouter(prefix="/api/admin", tags=["admin-subscriptions"])

PLAN_PREMIUM = "premium"
PLAN_TRIAL    = "trial"
VALID_PLANS = {PLAN_PREMIUM, PLAN_TRIAL}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_code(prefix: str = "BIGFM") -> str:
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{prefix}-{suffix}"


# ─── direct grant ─────────────────────────────────────────────
class GrantIn(BaseModel):
    user_id: str = Field(..., min_length=3)
    plan: Literal["premium", "trial"] = "premium"
    duration_days: int = Field(30, ge=1, le=3650)


@router.post("/subscriptions/grant")
async def grant_subscription(payload: GrantIn, request: Request,
                                                            admin: dict = Depends(require_admin)):
    db = request.app.state.db
    target = await db.users.find_one({"user_id": payload.user_id})
    if not target:
        raise HTTPException(404, {"code": "user_not_found",
                                                                    "user_id": payload.user_id})
    now = _now()
    expires_at = now + timedelta(days=payload.duration_days)
    # Build the subscription state.  Mirror the same fields the trial
    # endpoints write so the existing premium-gate helpers Just Work.
    update_set = {
        "subscription_status": payload.plan,
        "tier": payload.plan,
        "is_premium": True,
        "premium_until": expires_at,
        "updated_at": now,
    }
    if payload.plan == PLAN_TRIAL:
        update_set.update({
            "trial_started_at": now,
            "trial_ends_at":     expires_at,
            "trial_granted_by_admin": admin["user_id"],
        })
    else:
        update_set.update({
            "premium_granted_by_admin": admin["user_id"],
            "premium_granted_at": now,
        })
    await db.users.update_one({"user_id": payload.user_id},
                                                          {"$set": update_set})
    # Audit row for compliance.
    audit_id = f"sgr_{uuid.uuid4().hex[:14]}"
    await db.subscription_grants.insert_one({
        "_id": audit_id, "grant_id": audit_id,
        "user_id": payload.user_id, "user_email": target.get("email"),
        "plan": payload.plan,
        "duration_days": payload.duration_days,
        "expires_at": expires_at,
        "granted_by_admin": admin["user_id"],
        "granted_by_email": admin.get("email"),
        "created_at": now,
    })
    log.info("[admin-grant] user=%s plan=%s days=%s admin=%s",
                      payload.user_id, payload.plan, payload.duration_days,
                      admin["user_id"])
    return {"ok": True, "grant_id": audit_id,
                  "user_id": payload.user_id,
                  "plan": payload.plan,
                  "expires_at": expires_at.isoformat()}


# ─── voucher CRUD ─────────────────────────────────────────────
class VoucherCreateIn(BaseModel):
    code: Optional[str] = Field(default=None, max_length=32)
    plan: Literal["premium", "trial"] = "premium"
    duration_days: int = Field(30, ge=1, le=3650)
    max_redemptions: int = Field(1, ge=1, le=100000)
    expires_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=400)


@router.post("/vouchers/create")
async def create_voucher(payload: VoucherCreateIn, request: Request,
                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    code = (payload.code or _gen_code()).strip().upper()
    if not code or len(code) < 4:
        raise HTTPException(400, {"code": "code_too_short"})
    existing = await db.vouchers.find_one({"code": code})
    if existing:
        raise HTTPException(409, {"code": "code_already_exists",
                                                                    "voucher_id": existing["voucher_id"]})
    vid = f"vch_{uuid.uuid4().hex[:14]}"
    now = _now()
    doc = {
        "_id": vid, "voucher_id": vid,
        "code": code, "plan": payload.plan,
        "duration_days": payload.duration_days,
        "max_redemptions": payload.max_redemptions,
        "redemptions_count": 0,
        "expires_at": payload.expires_at,
        "active": True, "revoked_at": None,
        "notes": payload.notes,
        "created_by": admin["user_id"],
        "created_at": now, "updated_at": now,
    }
    await db.vouchers.insert_one(doc)
    log.info("[voucher-create] code=%s plan=%s by=%s",
                      code, payload.plan, admin["user_id"])
    return {"ok": True, "voucher_id": vid, "code": code,
                  "plan": payload.plan,
                  "duration_days": payload.duration_days,
                  "max_redemptions": payload.max_redemptions,
                  "expires_at": payload.expires_at.isoformat() if payload.expires_at else None}


@router.get("/vouchers")
async def list_vouchers(request: Request,
                                              status: str = "all",
                                              limit: int = 100,
                                              _a: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {}
    if status == "active":
        q = {"active": True}
    elif status == "revoked":
        q = {"active": False}
    items = []
    async for r in db.vouchers.find(q).sort("created_at", -1).limit(min(limit, 500)):
        r.pop("_id", None)
        items.append({**r,
                              "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                              "expires_at": r["expires_at"].isoformat() if r.get("expires_at") else None,
                              "revoked_at": r["revoked_at"].isoformat() if r.get("revoked_at") else None,
                              "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None})
    return {"ok": True, "items": items, "total": len(items)}


@router.post("/vouchers/{voucher_id}/revoke")
async def revoke_voucher(voucher_id: str, request: Request,
                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    r = await db.vouchers.update_one(
        {"voucher_id": voucher_id, "active": True},
        {"$set": {"active": False, "revoked_at": _now(),
                          "revoked_by_admin": admin["user_id"],
                          "updated_at": _now()}})
    if r.matched_count == 0:
        existing = await db.vouchers.find_one({"voucher_id": voucher_id})
        if not existing:
            raise HTTPException(404, {"code": "voucher_not_found"})
        return {"ok": True, "voucher_id": voucher_id,
                      "already_revoked": True}
    return {"ok": True, "voucher_id": voucher_id, "revoked": True}


async def ensure_indexes(db) -> None:
    """Idempotent indexes for the voucher + grants collections."""
    try:
        await db.vouchers.create_index("code", unique=True, name="uniq_code")
        await db.vouchers.create_index([("active", 1), ("created_at", -1)],
                                                                          name="active_created_at")
        await db.subscription_grants.create_index(
            [("user_id", 1), ("created_at", -1)],
            name="user_created_at")
        await db.voucher_redemptions.create_index(
            [("voucher_id", 1), ("user_id", 1)],
            unique=True, name="uniq_voucher_user")
    except Exception as e:
        log.debug("[admin-subscriptions] index ensure skipped: %s", e)
