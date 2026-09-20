"""Phase SC.2 — Admin merchant approval workflow.

Endpoints (all require admin role):
    GET      /api/admin/merchants                                        — list w/ filters + pagination
    GET      /api/admin/merchants/{merchant_id}              — full profile + locations + photos
    POST    /api/admin/merchants/{merchant_id}/approve      — flip to `approved`, Mailgun notify
    POST    /api/admin/merchants/{merchant_id}/reject        — flip to `rejected`, Mailgun notify
    POST    /api/admin/merchants/{merchant_id}/suspend      — flip to `suspended`, Mailgun notify
    POST    /api/admin/merchants/{merchant_id}/reactivate  — restore approved/active state
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import require_admin
from services.merchant_status_service import (MERCHANT_STATUSES,
                                                                          derive_effective_status)

logger = logging.getLogger("bigfm.admin_merchants")

router = APIRouter(prefix="/api/admin", tags=["admin_merchants"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RejectBody(BaseModel):
    reason: str = Field(min_length=20, max_length=1000)


class SuspendBody(BaseModel):
    reason: str = Field(min_length=20, max_length=1000)


# ─── Helpers ──────────────────────────────────────────────────────
async def _resolve_merchant(db, merchant_id: str) -> dict:
    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        biz = await db.businesses.find_one({"_id": merchant_id})
    if not biz:
        raise HTTPException(404, "merchant_not_found")
    return biz


def _biz_filter(biz: dict) -> dict:
    return {"business_id": biz["business_id"]} if biz.get("business_id") \
                  else {"_id": biz["_id"]}


def _biz_id(biz: dict) -> str:
    return biz.get("business_id") or biz.get("_id") or ""


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


async def _lookup_owner_email(db, owner_user_id: Optional[str]) -> Optional[str]:
    if not owner_user_id:
        return None
    user = await db.users.find_one(
        {"user_id": owner_user_id}, {"email": 1, "name": 1})
    return (user or {}).get("email")


def _merchant_admin_row(biz: dict) -> dict:
    return {
        "merchant_id":                  _biz_id(biz),
        "business_id":                  biz.get("business_id"),
        "name":                              biz.get("name"),
        "slug":                              biz.get("slug"),
        "category_id":                  biz.get("category_id") or biz.get("category"),
        "owner_user_id":              biz.get("owner_user_id"),
        "owner_email":                  biz.get("owner_email"),
        "merchant_status":          biz.get("merchant_status") or "draft",
        "effective_status":          derive_effective_status(biz),
        "stripe_onboarding_status": biz.get("stripe_onboarding_status") or "not_started",
        "stripe_account_id":      biz.get("stripe_account_id"),
        "logo_url":                        biz.get("logo_url"),
        "phone":                            biz.get("phone"),
        "website":                          biz.get("website"),
        "submitted_at":              _iso(biz.get("submitted_at")),
        "approved_at":                _iso(biz.get("approved_at")),
        "rejected_at":                _iso(biz.get("rejected_at")),
        "rejection_reason":        biz.get("rejection_reason"),
        "suspended_at":              _iso(biz.get("suspended_at")),
        "suspension_reason":      biz.get("suspension_reason"),
        "source":                            biz.get("source"),
        "created_at":                  _iso(biz.get("created_at")),
        "updated_at":                  _iso(biz.get("updated_at")),
    }


# ─── Category / status filters ────────────────────────────────────
_STATUS_ALIASES = {
    # Convenience aliases so callers can query with intent
    "pending":            ["submitted"],
    "all_pending":    ["submitted", "verification_pending"],
    "adverse":          ["restricted", "payouts_disabled", "rejected", "suspended"],
}


@router.get("/merchants")
async def admin_list_merchants(request: Request,
                                                _admin: dict = Depends(require_admin),
                                                status: Optional[str] = Query(None),
                                                search: Optional[str] = Query(None,
                                                                                                                        max_length=120),
                                                limit: int = Query(50, ge=1, le=500),
                                                offset: int = Query(0, ge=0)):
    db = request.app.state.db
    q: dict = {}
    if status:
        aliased = _STATUS_ALIASES.get(status)
        if aliased:
            q["merchant_status"] = {"$in": aliased}
        elif status in MERCHANT_STATUSES:
            q["merchant_status"] = status
        elif status == "self_service":
            q["source"] = "self_service"
        else:
            raise HTTPException(400, f"invalid_status:{status}")
    if search:
        rgx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"name": rgx}, {"slug": rgx},
                          {"business_id": rgx}, {"owner_email": rgx}]

    total = await db.businesses.count_documents(q)
    cursor = db.businesses.find(q).sort("submitted_at", -1) \
                                              .sort("created_at", -1) \
                                              .skip(offset).limit(limit)
    items = []
    async for b in cursor:
        row = _merchant_admin_row(b)
        if not row.get("owner_email"):
            row["owner_email"] = await _lookup_owner_email(db, row.get("owner_user_id"))
        items.append(row)
    return {"total": total, "count": len(items),
              "offset": offset, "limit": limit, "items": items}


@router.get("/merchants/{merchant_id}")
async def admin_get_merchant(merchant_id: str, request: Request,
                                                    _admin: dict = Depends(require_admin)):
    db  = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id)
    mid = _biz_id(biz)
    locs = await db.merchant_locations.find(
        {"merchant_id": mid, "active": True}
    ).sort("created_at", 1).to_list(50)

    def _loc_view(l):
        return {
            "location_id":      l.get("location_id"),
            "name":                  l.get("name"),
            "address":            l.get("address"),
            "city":                  l.get("city"),
            "country":            l.get("country"),
            "latitude":          l.get("latitude"),
            "longitude":        l.get("longitude"),
            "google_place_id": l.get("google_place_id"),
            "phone":                l.get("phone"),
            "primary":            bool(l.get("primary")),
        }

    owner_email = biz.get("owner_email") or await _lookup_owner_email(
        db, biz.get("owner_user_id"))
    return {
        **_merchant_admin_row(biz),
        "description":  biz.get("description"),
        "hours":            biz.get("hours"),
        "photos":          biz.get("photos") or [],
        "commission_terms_accepted": bool(biz.get("commission_terms_accepted")),
        "commission_terms_accepted_at": _iso(
            biz.get("commission_terms_accepted_at")),
        "locations":    [_loc_view(l) for l in locs],
        "owner_email": owner_email,
        # Stripe surfaces from SC.1
        "stripe_charges_enabled":  bool(biz.get("stripe_charges_enabled")),
        "stripe_payouts_enabled":  bool(biz.get("stripe_payouts_enabled")),
        "stripe_details_submitted":  bool(biz.get("stripe_details_submitted")),
        "stripe_requirements_currently_due": biz.get(
            "stripe_requirements_currently_due") or [],
        "stripe_requirements_past_due":  biz.get(
            "stripe_requirements_past_due") or [],
        "stripe_status_synced_at":  _iso(biz.get("stripe_status_synced_at")),
    }


# ─── Mailgun ──────────────────────────────────────────────────────
def _frontend_url() -> str:
    url = (os.environ.get("FRONTEND_URL")
              or os.environ.get("FRONTEND_BASE_URL") or "").strip()
    return url.rstrip("/") or "https://mobile-games-v2.preview.emergentagent.com"


async def _notify_merchant(db, biz: dict, subject: str, html: str, text: str,
                                            tags: list[str]) -> dict:
    """Best-effort Mailgun send.  Returns the send result (or a mocked dict
    if mailgun is not configured).  Never raises — an email failure must not
    unwind the approval decision."""
    to = biz.get("owner_email")
    if not to:
        to = await _lookup_owner_email(db, biz.get("owner_user_id"))
    if not to:
        return {"ok": False, "error": "no_owner_email"}
    try:
        from services.mailgun_client import send_email, is_live
        if not is_live():
            logger.info(f"[merchant-notify] mailgun disabled — would send to={to} "
                                  f"subject={subject!r}")
            return {"ok": False, "error": "mailgun_disabled", "to": to}
        return send_email(to=to, subject=subject, html=html, text=text,
                                          tags=tags)
    except Exception as e:
        logger.exception("[merchant-notify] send failed")
        return {"ok": False, "error": str(e)[:200]}


def _mailgun_html_approval(biz: dict) -> tuple[str, str, str]:
    name = biz.get("name") or "your business"
    fe   = _frontend_url()
    dash = f"{fe}/merchant/dashboard"
    subject = f"Welcome to FUUSIC Merchants — {name} is approved"
    html = (
        f"<div style='font-family:system-ui,sans-serif;color:#111;'>"
        f"<h2 style='color:#7c3aed'>Welcome to FUUSIC Merchants</h2>"
        f"<p>Great news — your application for <b>{name}</b> has been "
        f"approved.  You can now set up offers, run campaigns, and take "
        f"payments through FUUSIC.</p>"
        f"<p><a href='{dash}' style='background:linear-gradient(135deg,"
        f"#7c3aed,#ec4899);color:#fff;padding:12px 22px;border-radius:24px;"
        f"text-decoration:none;font-weight:600;'>Open your merchant dashboard</a></p>"
        f"<p style='color:#666;font-size:13px'>Questions? Just reply to this email.<br>"
        f"— FUUSIC Merchant Team</p>"
        f"</div>")
    text = (f"Welcome to FUUSIC Merchants — {name} is approved.\n\n"
                f"Open your merchant dashboard: {dash}\n\n"
                f"— FUUSIC Merchant Team")
    return subject, html, text


def _mailgun_html_rejection(biz: dict, reason: str) -> tuple[str, str, str]:
    name = biz.get("name") or "your business"
    subject = "Your FUUSIC merchant application update"
    html = (
        f"<div style='font-family:system-ui,sans-serif;color:#111;'>"
        f"<h2 style='color:#111'>Application update</h2>"
        f"<p>Thanks for applying to FUUSIC Merchants for <b>{name}</b>.  "
        f"After review we're unable to approve the application at this time.</p>"
        f"<p><b>Reason from our team:</b><br>"
        f"<blockquote style='margin:8px 0 8px 8px;padding-left:14px;"
        f"border-left:3px solid #ec4899;color:#333;'>{reason}</blockquote></p>"
        f"<p>If you have questions or would like to appeal, please "
        f"<a href='mailto:merchants@bigfantv.com'>contact support</a>.</p>"
        f"<p style='color:#666;font-size:13px'>— FUUSIC Merchant Team</p>"
        f"</div>")
    text = (f"Application update for {name}\n\n"
                f"After review we're unable to approve your application at this "
                f"time.\n\nReason: {reason}\n\n"
                f"Contact support: merchants@bigfantv.com\n\n"
                f"— FUUSIC Merchant Team")
    return subject, html, text


def _mailgun_html_suspension(biz: dict, reason: str) -> tuple[str, str, str]:
    name = biz.get("name") or "your business"
    subject = f"Your FUUSIC merchant account has been suspended"
    html = (
        f"<div style='font-family:system-ui,sans-serif;color:#111;'>"
        f"<h2>Account suspended</h2>"
        f"<p>Your merchant account for <b>{name}</b> has been temporarily "
        f"suspended.</p>"
        f"<p><b>Reason:</b><br>"
        f"<blockquote style='margin:8px 0 8px 8px;padding-left:14px;"
        f"border-left:3px solid #f59e0b;color:#333;'>{reason}</blockquote></p>"
        f"<p>To resolve or appeal, please "
        f"<a href='mailto:merchants@bigfantv.com'>contact support</a>.</p>"
        f"<p style='color:#666;font-size:13px'>— FUUSIC Merchant Team</p>"
        f"</div>")
    text = (f"Your merchant account for {name} has been suspended.\n\n"
                f"Reason: {reason}\n\nContact: merchants@bigfantv.com\n\n"
                f"— FUUSIC Merchant Team")
    return subject, html, text


def _mailgun_html_reactivate(biz: dict) -> tuple[str, str, str]:
    name = biz.get("name") or "your business"
    fe   = _frontend_url()
    dash = f"{fe}/merchant/dashboard"
    subject = f"Welcome back to FUUSIC Merchants"
    html = (
        f"<div style='font-family:system-ui,sans-serif;color:#111;'>"
        f"<h2 style='color:#059669'>Welcome back</h2>"
        f"<p>Good news — <b>{name}</b> has been reactivated.  You can pick "
        f"up right where you left off.</p>"
        f"<p><a href='{dash}' style='background:#059669;color:#fff;"
        f"padding:12px 22px;border-radius:24px;text-decoration:none;"
        f"font-weight:600;'>Open your dashboard</a></p>"
        f"<p style='color:#666;font-size:13px'>— FUUSIC Merchant Team</p>"
        f"</div>")
    text = (f"Welcome back — {name} has been reactivated.\n\n"
                f"Open your dashboard: {dash}\n\n— FUUSIC Merchant Team")
    return subject, html, text


# ─── Role elevation on approval ───────────────────────────────────
async def _elevate_owner_role(db, owner_user_id: Optional[str]) -> bool:
    if not owner_user_id:
        return False
    user = await db.users.find_one({"user_id": owner_user_id},
                                                                {"role": 1, "roles": 1})
    if not user:
        return False
    role = user.get("role") or "user"
    roles = list(user.get("roles") or [])
    update: dict = {}
    if role in ("user", "listener"):
        update["role"] = "business"
    if "business" not in roles:
        roles.append("business")
        update["roles"] = roles
    if update:
        await db.users.update_one(
            {"user_id": owner_user_id}, {"$set": update})
        return True
    return False


# ─── Actions ──────────────────────────────────────────────────────
@router.post("/merchants/{merchant_id}/approve")
async def admin_approve_merchant(merchant_id: str, request: Request,
                                                            admin: dict = Depends(require_admin)):
    db  = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id)
    if biz.get("merchant_status") in ("approved", "active"):
        return {"ok": True, "already_approved": True,
                    **_merchant_admin_row(biz)}
    if biz.get("merchant_status") not in ("submitted", "verification_pending",
                                                                        "suspended", "rejected"):
        raise HTTPException(400,
            {"code": "invalid_transition",
              "from": biz.get("merchant_status"),
              "hint": "must be submitted / verification_pending / rejected / suspended"})

    now = _now()
    await db.businesses.update_one(
        _biz_filter(biz),
        {"$set": {"merchant_status": "approved",
                        "approved_at":      now,
                        "approved_by":      admin.get("user_id"),
                        "rejection_reason": None,
                        "rejected_at":      None,
                        "suspended_at":      None,
                        "suspension_reason": None,
                        "updated_at":          now}})

    role_elevated = await _elevate_owner_role(db, biz.get("owner_user_id"))
    biz = await db.businesses.find_one(_biz_filter(biz))
    logger.info(f"[merchant] APPROVED mid={_biz_id(biz)} by={admin.get('user_id')} "
                          f"role_elevated={role_elevated}")

    subject, html, text = _mailgun_html_approval(biz)
    email_res = await _notify_merchant(db, biz, subject, html, text,
                                                                    tags=["merchant_approved"])
    return {"ok": True, "email": email_res,
              "role_elevated": role_elevated,
              **_merchant_admin_row(biz)}


@router.post("/merchants/{merchant_id}/reject")
async def admin_reject_merchant(merchant_id: str, body: RejectBody,
                                                        request: Request,
                                                        admin: dict = Depends(require_admin)):
    db  = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id)
    if biz.get("merchant_status") in ("approved", "active"):
        raise HTTPException(400, "cannot_reject_active_merchant")

    now = _now()
    await db.businesses.update_one(
        _biz_filter(biz),
        {"$set": {"merchant_status": "rejected",
                        "rejected_at":        now,
                        "rejection_reason": body.reason.strip(),
                        "approved_at":        None,
                        "approved_by":        None,
                        "updated_at":            now}})
    biz = await db.businesses.find_one(_biz_filter(biz))
    logger.info(f"[merchant] REJECTED mid={_biz_id(biz)} by={admin.get('user_id')}")

    subject, html, text = _mailgun_html_rejection(biz, body.reason.strip())
    email_res = await _notify_merchant(db, biz, subject, html, text,
                                                                    tags=["merchant_rejected"])
    return {"ok": True, "email": email_res, **_merchant_admin_row(biz)}


@router.post("/merchants/{merchant_id}/suspend")
async def admin_suspend_merchant(merchant_id: str, body: SuspendBody,
                                                          request: Request,
                                                          admin: dict = Depends(require_admin)):
    db  = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id)
    if biz.get("merchant_status") not in ("approved", "active",
                                                                          "payouts_disabled", "restricted"):
        raise HTTPException(400,
            {"code": "invalid_transition",
              "from": biz.get("merchant_status"),
              "hint": "can only suspend an approved/active merchant"})

    now = _now()
    await db.businesses.update_one(
        _biz_filter(biz),
        {"$set": {"merchant_status": "suspended",
                        "suspended_at":      now,
                        "suspension_reason": body.reason.strip(),
                        "updated_at":            now}})
    biz = await db.businesses.find_one(_biz_filter(biz))
    logger.info(f"[merchant] SUSPENDED mid={_biz_id(biz)} by={admin.get('user_id')}")

    subject, html, text = _mailgun_html_suspension(biz, body.reason.strip())
    email_res = await _notify_merchant(db, biz, subject, html, text,
                                                                    tags=["merchant_suspended"])
    return {"ok": True, "email": email_res, **_merchant_admin_row(biz)}


@router.post("/merchants/{merchant_id}/reactivate")
async def admin_reactivate_merchant(merchant_id: str, request: Request,
                                                                admin: dict = Depends(require_admin)):
    db  = request.app.state.db
    biz = await _resolve_merchant(db, merchant_id)
    if biz.get("merchant_status") != "suspended":
        raise HTTPException(400, "only_suspended_can_reactivate")

    now = _now()
    await db.businesses.update_one(
        _biz_filter(biz),
        {"$set": {"merchant_status": "approved",
                        "suspended_at":      None,
                        "suspension_reason": None,
                        "updated_at":            now}})
    biz = await db.businesses.find_one(_biz_filter(biz))
    logger.info(f"[merchant] REACTIVATED mid={_biz_id(biz)} by={admin.get('user_id')}")

    subject, html, text = _mailgun_html_reactivate(biz)
    email_res = await _notify_merchant(db, biz, subject, html, text,
                                                                    tags=["merchant_reactivated"])
    return {"ok": True, "email": email_res, **_merchant_admin_row(biz)}


__all__ = ["router"]
