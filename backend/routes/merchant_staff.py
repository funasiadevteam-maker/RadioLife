"""Phase MER.2 — Merchant Staff invite + cashier redemption endpoints.

Endpoints:
    Staff invites (require can_invite_staff):
        POST /api/merchant/{merchant_id}/staff/invite
        GET  /api/merchant/{merchant_id}/staff
        POST /api/merchant/{merchant_id}/staff/{staff_user_id}/role
        POST /api/merchant/{merchant_id}/staff/{staff_user_id}/deactivate
        POST /api/merchant/{merchant_id}/staff/invites/{invite_id}/revoke

    Public invite lookup + accept:
        GET  /api/staff/invite/{token}/preview
        POST /api/staff/invite/{token}/accept

    Cashier redemption (require can_redeem_coupons):
        POST /api/merchant/{merchant_id}/cashier/scan
        POST /api/merchant/{merchant_id}/cashier/redeem
        GET  /api/merchant/{merchant_id}/cashier/redemptions/today
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth import current_user
from services.merchant_rbac_service import (
    resolve_merchant_with_role,
    get_user_role_for_merchant,
    STAFF_ROLES,
    ROLE_PERMISSIONS,
    permissions_for_role,
)

logger = logging.getLogger("bigfm.mer2")
router = APIRouter(prefix="/api", tags=["mer2"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt):
    """Coerce a tz-naive datetime (BSON default) to tz-aware UTC so it
    can be compared to `_now()` without TypeError."""
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _base62_token(n: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or ""
    name, dom = email.split("@", 1)
    if len(name) <= 2:
        return "*" * len(name) + "@" + dom
    return name[0] + "*" * (len(name) - 2) + name[-1] + "@" + dom


# ─── STAFF INVITES ────────────────────────────────────────────────
class InviteBody(BaseModel):
    email:  EmailStr
    role:    str = Field(min_length=1, max_length=32)


@router.post("/merchant/{merchant_id}/staff/invite")
async def staff_invite(merchant_id: str, body: InviteBody, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, actor_role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_invite_staff")
    biz_id = biz.get("business_id") or biz.get("_id")

    if body.role not in STAFF_ROLES:
        raise HTTPException(400, {"code": "invalid_role",
                                                          "allowed": sorted(STAFF_ROLES)})
    email = body.email.lower()

    # Cannot invite the owner themselves
    if biz.get("owner_email", "").lower() == email:
        raise HTTPException(400, {"code": "cannot_invite_owner"})
    # Already-active staff with this email
    for s in (biz.get("staff_users") or []):
        if (s.get("email") or "").lower() == email and s.get("active", True):
            raise HTTPException(409, {"code": "already_staff",
                                                              "detail": f"{email} is already {s.get('role')}."})

    # Existing pending invite
    existing = await db.merchant_staff_invites.find_one(
        {"merchant_id": biz_id, "email": email, "status": "pending"})
    if existing:
        raise HTTPException(409, {"code": "invite_pending",
                                                          "invite_id": existing.get("invite_id"),
                                                          "detail": f"A pending invite to {email} already exists."})

    invite_id = f"inv_{uuid.uuid4().hex[:16]}"
    token = _base62_token(24)
    now = _now()
    doc = {
        "_id":                          invite_id,
        "invite_id":              invite_id,
        "merchant_id":          biz_id,
        "email":                      email,
        "role":                        body.role,
        "invited_by":            user.get("user_id"),
        "invited_by_role":  actor_role,
        "token":                      token,
        "status":                    "pending",
        "created_at":            now,
        "expires_at":            now + timedelta(days=7),
        "accepted_at":          None,
        "accepted_by_user_id": None,
    }
    await db.merchant_staff_invites.insert_one(doc)

    # Fire Mailgun invite (best-effort — do NOT fail the endpoint on email issues)
    origin = os.environ.get("FRONTEND_ORIGIN") \
                        or _guess_frontend_from_env(request)
    invite_url = f"{origin.rstrip('/')}/staff/invite/{token}"
    try:
        from services.mailgun_client import send_email, is_live
        if is_live():
            subject = f"You\u2019ve been invited to BigFM as {body.role} at {biz.get('name','a merchant')}"
            html = (
                f"<div style='font-family:system-ui,sans-serif; max-width:520px;'>"
                f"<h2 style='color:#a855f7'>You\u2019ve got an invite \u2728</h2>"
                f"<p><b>{biz.get('name','A merchant on BigFM')}</b> invited you to join their team on "
                f"<a href='https://bigfm.dubai'>BigFM</a> as a <b>{body.role}</b>.</p>"
                f"<p style='margin:24px 0'>"
                f"<a href='{invite_url}' style='background:linear-gradient(135deg,#a855f7,#ec4899);"
                f"color:#fff;text-decoration:none;padding:10px 24px;border-radius:999px;"
                f"font-weight:bold;font-size:14px'>Accept invite</a></p>"
                f"<p style='color:#64748b;font-size:12px'>The link expires in 7 days.  If it wasn\u2019t you, "
                f"just ignore this email.</p>"
                f"<p style='color:#64748b;font-size:12px'>URL: <code>{invite_url}</code></p>"
                f"</div>")
            send_email(to=email, subject=subject, html=html,
                              text=f"Accept invite: {invite_url}",
                              tags=["mer2_staff_invite"])
            logger.info(f"[mer2] invite sent to={email} role={body.role} mid={biz_id}")
    except Exception:
        logger.exception("[mer2] mailgun invite email failed (non-blocking)")

    return {"invite_id": invite_id, "email": email, "role": body.role,
                  "token": token, "expires_at": _iso(doc["expires_at"]),
                  "invite_url": invite_url}


def _guess_frontend_from_env(request: Request) -> str:
    """Fallback if FRONTEND_ORIGIN env isn't set — derive from Host header."""
    h = request.headers.get("origin") or request.headers.get("referer")
    if h:
        try:
            from urllib.parse import urlparse
            p = urlparse(h)
            return f"{p.scheme}://{p.netloc}"
        except Exception:
            pass
    return "https://bigfm.dubai"


@router.get("/merchant/{merchant_id}/staff")
async def staff_list(merchant_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, actor_role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_invite_staff")
    biz_id = biz.get("business_id") or biz.get("_id")

    # Owner row (synthesized from businesses doc)
    owner_row = None
    if biz.get("owner_user_id"):
        owner_user = await db.users.find_one({"user_id": biz["owner_user_id"]},
                                                                                    {"user_id":1,"email":1,"display_name":1,"name":1})
        owner_row = {
            "staff_user_id":  "owner",
            "user_id":              biz["owner_user_id"],
            "email":                  (owner_user or {}).get("email"),
            "display_name":    (owner_user or {}).get("display_name")
                                                        or (owner_user or {}).get("name"),
            "role":                    "owner",
            "invited_by":        None,
            "invited_at":        biz.get("created_at"),
            "accepted_at":      biz.get("created_at"),
            "active":                True,
            "last_seen_at":    None,
            "is_owner_row":  True,
        }

    staff_rows = list(biz.get("staff_users") or [])
    invites = await db.merchant_staff_invites.find(
        {"merchant_id": biz_id, "status": "pending"}
    ).sort("created_at", -1).to_list(50)

    def _sv(s):
        return {**s,
                        "invited_at":  _iso(s.get("invited_at")),
                        "accepted_at": _iso(s.get("accepted_at")),
                        "last_seen_at": _iso(s.get("last_seen_at"))}
    def _iv(i):
        return {
            "invite_id":      i.get("invite_id"),
            "email":              i.get("email"),
            "role":                i.get("role"),
            "invited_by":    i.get("invited_by"),
            "created_at":    _iso(i.get("created_at")),
            "expires_at":    _iso(i.get("expires_at")),
            "token":              i.get("token"),
        }

    return {
        "owner":                owner_row,
        "staff":                [_sv(s) for s in staff_rows],
        "pending_invites": [_iv(i) for i in invites],
        "actor_role":      actor_role,
    }


class RoleChangeBody(BaseModel):
    role: str


@router.post("/merchant/{merchant_id}/staff/{staff_user_id}/role")
async def staff_change_role(merchant_id: str, staff_user_id: str,
                                                        body: RoleChangeBody, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_invite_staff")
    if staff_user_id == "owner":
        raise HTTPException(400, {"code": "cannot_change_owner"})
    if body.role not in STAFF_ROLES:
        raise HTTPException(400, {"code": "invalid_role",
                                                          "allowed": sorted(STAFF_ROLES)})
    result = await db.businesses.update_one(
        {"_id": biz["_id"], "staff_users.staff_user_id": staff_user_id},
        {"$set": {"staff_users.$.role": body.role,
                            "staff_users.$.updated_at": _now()}})
    if result.matched_count == 0:
        raise HTTPException(404, "staff_not_found")
    return {"staff_user_id": staff_user_id, "role": body.role}


@router.post("/merchant/{merchant_id}/staff/{staff_user_id}/deactivate")
async def staff_deactivate(merchant_id: str, staff_user_id: str,
                                                    request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_invite_staff")
    if staff_user_id == "owner":
        raise HTTPException(400, {"code": "cannot_deactivate_owner"})
    result = await db.businesses.update_one(
        {"_id": biz["_id"], "staff_users.staff_user_id": staff_user_id},
        {"$set": {"staff_users.$.active": False,
                            "staff_users.$.deactivated_at": _now()}})
    if result.matched_count == 0:
        raise HTTPException(404, "staff_not_found")
    return {"staff_user_id": staff_user_id, "active": False}


@router.post("/merchant/{merchant_id}/staff/invites/{invite_id}/revoke")
async def staff_invite_revoke(merchant_id: str, invite_id: str,
                                                              request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_invite_staff")
    biz_id = biz.get("business_id") or biz.get("_id")
    result = await db.merchant_staff_invites.update_one(
        {"invite_id": invite_id, "merchant_id": biz_id, "status": "pending"},
        {"$set": {"status": "revoked", "revoked_at": _now()}})
    if result.matched_count == 0:
        raise HTTPException(404, "invite_not_found_or_not_pending")
    return {"invite_id": invite_id, "status": "revoked"}


# ─── PUBLIC INVITE ACCEPT ─────────────────────────────────────────
@router.get("/staff/invite/{token}/preview")
async def invite_preview(token: str, request: Request):
    db = request.app.state.db
    inv = await db.merchant_staff_invites.find_one({"token": token})
    if not inv:
        raise HTTPException(404, {"code": "not_found"})

    # Expired?
    if inv.get("status") == "pending" and inv.get("expires_at") \
                and _to_utc(inv["expires_at"]) < _now():
        await db.merchant_staff_invites.update_one(
            {"_id": inv["_id"]},
            {"$set": {"status": "expired"}})
        inv["status"] = "expired"

    biz = await db.businesses.find_one(
        {"$or": [{"business_id": inv["merchant_id"]},
                          {"_id": inv["merchant_id"]}]},
        {"name": 1, "logo_url": 1, "category_id": 1}) or {}
    return {
        "merchant_id":  inv.get("merchant_id"),
        "merchant_name": biz.get("name"),
        "merchant_logo_url": biz.get("logo_url"),
        "role":                    inv.get("role"),
        "email_masked":  _mask_email(inv.get("email") or ""),
        "status":                inv.get("status"),
        "expires_at":      _iso(inv.get("expires_at")),
    }


class AcceptBody(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)


@router.post("/staff/invite/{token}/accept")
async def invite_accept(token: str, body: AcceptBody, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    inv = await db.merchant_staff_invites.find_one({"token": token})
    if not inv:
        raise HTTPException(404, {"code": "not_found"})
    if inv.get("status") != "pending":
        raise HTTPException(400, {"code": "invalid_state",
                                                          "current_status": inv.get("status")})
    if inv.get("expires_at") and _to_utc(inv["expires_at"]) < _now():
        await db.merchant_staff_invites.update_one(
            {"_id": inv["_id"]}, {"$set": {"status": "expired"}})
        raise HTTPException(400, {"code": "expired"})

    # Enforce email match unless the current user is an admin
    invite_email = (inv.get("email") or "").lower()
    user_email = (user.get("email") or "").lower()
    if not (user.get("role") == "admin" or user.get("is_admin")):
        if user_email != invite_email:
            raise HTTPException(403, {
                "code": "email_mismatch",
                "detail": f"This invite is for {_mask_email(invite_email)}."
                                    f"  Sign in with that email to accept.",
            })

    biz_id = inv["merchant_id"]
    biz = await db.businesses.find_one(
        {"$or": [{"business_id": biz_id}, {"_id": biz_id}]})
    if not biz:
        raise HTTPException(404, "merchant_not_found")

    # Owner cannot accept a staff invite for their own merchant
    if biz.get("owner_user_id") == user.get("user_id"):
        raise HTTPException(400, {"code": "owner_cannot_accept",
                                                          "detail": "You already own this merchant."})

    # Idempotent — if the user already has an active staff row, just update role
    already = None
    for s in (biz.get("staff_users") or []):
        if s.get("user_id") == user.get("user_id") and s.get("active", True):
            already = s
            break

    now = _now()
    if already:
        await db.businesses.update_one(
            {"_id": biz["_id"],
              "staff_users.staff_user_id": already["staff_user_id"]},
            {"$set": {
                "staff_users.$.role":                    inv["role"],
                "staff_users.$.accepted_at":      now,
                "staff_users.$.active":              True,
                "staff_users.$.updated_at":        now,
            }})
        staff_user_id = already["staff_user_id"]
    else:
        staff_user_id = f"sf_{uuid.uuid4().hex[:16]}"
        staff_row = {
            "staff_user_id":  staff_user_id,
            "user_id":              user.get("user_id"),
            "email":                  invite_email,
            "display_name":    body.display_name or user.get("display_name")
                                                        or user.get("name") or invite_email.split("@")[0],
            "role":                    inv["role"],
            "invited_by":        inv.get("invited_by"),
            "invited_at":        inv.get("created_at"),
            "accepted_at":      now,
            "active":                True,
            "last_seen_at":    now,
        }
        await db.businesses.update_one(
            {"_id": biz["_id"]},
            {"$push": {"staff_users": staff_row}})

    await db.merchant_staff_invites.update_one(
        {"_id": inv["_id"]},
        {"$set": {"status": "accepted", "accepted_at": now,
                            "accepted_by_user_id": user.get("user_id")}})

    logger.info(f"[mer2] invite accepted token={token} mid={biz_id} "
                          f"role={inv['role']} user={user.get('user_id')}")
    return {"merchant_id":    biz.get("business_id") or biz.get("_id"),
                  "role":                    inv["role"],
                  "staff_user_id":  staff_user_id,
                  "redirect_to":      "/merchant/dashboard"}


# ─── CASHIER REDEMPTION ──────────────────────────────────────────
class ScanBody(BaseModel):
    code: str = Field(min_length=3, max_length=64)


class RedeemBody(BaseModel):
    coupon_id: str = Field(min_length=3, max_length=64)
    notes:          Optional[str] = Field(default=None, max_length=200)


async def _lookup_coupon(db, *, code_or_id: str) -> Optional[dict]:
    """Match by coupon_id (`cp_...`) OR by `code` (`BIGFM-XXXXXX`).
    Also try uppercase for the code path since QR/keypad entry may be
    lower-case."""
    code = code_or_id.strip()
    up = code.upper()
    return await db.coupons.find_one({"$or": [
        {"coupon_id": code},
        {"coupon_id": up},
        {"code": code},
        {"code": up},
    ]})


async def _coupon_belongs_to_merchant(db, coupon: dict,
                                                                              merchant_id: str) -> bool:
    # Phase AD.4 — advertiser-minted coupons carry `business_id` directly
    # (no offer_id). Accept them if the sponsoring merchant matches.
    if coupon.get("business_id") == merchant_id:
        return True
    if not coupon.get("offer_id"):
        return False
    offer = await db.offers.find_one({"offer_id": coupon["offer_id"]})
    if not offer:
        return False
    return offer.get("business_id") == merchant_id


async def _coupon_scan_view(db, *, coupon: dict, biz: dict) -> dict:
    offer = None
    if coupon.get("offer_id"):
        offer = await db.offers.find_one({"offer_id": coupon["offer_id"]})
    customer = await db.users.find_one({"user_id": coupon.get("user_id")},
                                                                              {"email": 1}) if coupon.get("user_id") else None
    return {
        "coupon_id":                            coupon.get("coupon_id"),
        "redemption_code":                coupon.get("code"),
        "offer_id":                                (offer or {}).get("offer_id"),
        "offer_title":                        (offer or {}).get("title") or coupon.get("title"),
        "offer_discount_percent":  (offer or {}).get("discount_percent"),
        "offer_type":                          (offer or {}).get("offer_type") or coupon.get("coupon_type"),
        "source_type":                        coupon.get("source_type"),
        "advertiser_id":                    coupon.get("advertiser_id"),
        "ad_coupon_campaign_id":      coupon.get("ad_coupon_campaign_id"),
        "business_id":                        biz.get("business_id") or biz.get("_id"),
        "business_name":                    biz.get("name"),
        "customer_masked":                _mask_email(
                                                                (customer or {}).get("email") or ""),
        "expires_at":                          _iso(coupon.get("expires_at")),
        "status":                                  coupon.get("status"),
    }


@router.post("/merchant/{merchant_id}/cashier/scan")
async def cashier_scan(merchant_id: str, body: ScanBody, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_redeem_coupons")
    biz_id = biz.get("business_id") or biz.get("_id")

    coupon = await _lookup_coupon(db, code_or_id=body.code)
    if not coupon:
        return {"ok": False, "reason": "not_found"}

    if not await _coupon_belongs_to_merchant(db, coupon, biz_id):
        return {"ok": False, "reason": "not_this_merchant"}

    status = coupon.get("status")
    if status == "redeemed":
        return {"ok": False, "reason": "already_redeemed",
                      "redeemed_at": _iso(coupon.get("redeemed_at"))}
    if status == "revoked":
        return {"ok": False, "reason": "revoked"}
    if coupon.get("expires_at") and _to_utc(coupon["expires_at"]) < _now():
        return {"ok": False, "reason": "expired"}
    if status not in ("saved", "claimed"):
        return {"ok": False, "reason": f"invalid_status_{status}"}

    view = await _coupon_scan_view(db, coupon=coupon, biz=biz)
    return {"ok": True, **view}


@router.post("/merchant/{merchant_id}/cashier/redeem")
async def cashier_redeem(merchant_id: str, body: RedeemBody, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_redeem_coupons")
    biz_id = biz.get("business_id") or biz.get("_id")

    coupon = await _lookup_coupon(db, code_or_id=body.coupon_id)
    if not coupon:
        raise HTTPException(404, {"code": "not_found"})
    if not await _coupon_belongs_to_merchant(db, coupon, biz_id):
        raise HTTPException(400, {"code": "not_this_merchant"})
    if coupon.get("status") == "redeemed":
        raise HTTPException(409, {"code": "already_redeemed"})
    if coupon.get("status") == "revoked":
        raise HTTPException(400, {"code": "revoked"})
    if coupon.get("expires_at") and _to_utc(coupon["expires_at"]) < _now():
        raise HTTPException(400, {"code": "expired"})

    now = _now()
    # Atomically flip status
    result = await db.coupons.update_one(
        {"coupon_id": coupon["coupon_id"],
          "status": {"$in": ["saved", "claimed"]}},
        {"$set": {"status": "redeemed",
                            "redeemed_at": now,
                            "redeemed_by_staff_user_id": user.get("user_id"),
                            "redeemed_by_role": role,
                            "redeemed_at_merchant_id": biz_id}})
    if result.matched_count == 0:
        raise HTTPException(409, {"code": "already_redeemed_race"})

    offer = None
    if coupon.get("offer_id"):
        offer = await db.offers.find_one({"offer_id": coupon["offer_id"]})
    offer = offer or {}
    redemption_id = f"rd_{uuid.uuid4().hex[:16]}"
    await db.merchant_redemptions.insert_one({
        "_id":                              redemption_id,
        "redemption_id":            redemption_id,
        "merchant_id":                biz_id,
        "staff_user_id":            user.get("user_id"),
        "staff_role":                  role,
        "coupon_id":                    coupon.get("coupon_id"),
        "redemption_code":        coupon.get("code"),
        "offer_id":                      offer.get("offer_id"),
        "offer_title":                offer.get("title"),
        "offer_type":                  offer.get("offer_type"),
        "offer_discount_percent": offer.get("discount_percent"),
        "customer_user_id":      coupon.get("user_id"),
        "amount_saved_cents":  0,   # unknown here — MER.3 will compute when we have order totals
        "redeemed_at":              now,
        "notes":                          (body.notes or "")[:200],
    })

    logger.info(f"[mer2] coupon REDEEMED cid={coupon['coupon_id']} "
                          f"code={coupon.get('code')} mid={biz_id} "
                          f"staff={user.get('user_id')} role={role}")

    # Phase N (M7) — CPA charge on redemption (best-effort side
    # effect; never blocks or fails the redemption).
    try:
        from services.coupon_cpa_charge_pipeline import (
            try_charge_after_redemption)
        cpa_result = await try_charge_after_redemption(
            db, coupon_id=coupon["coupon_id"],
            redemption_type="merchant_staff",
            staff_user_id=user.get("user_id"))
    except Exception as _e:
        logger.warning("[mer2] CPA charge failed: %s", _e)
        cpa_result = None

    return {"ok":                                    True,
                  "redemption_id":            redemption_id,
                  "coupon_id":                    coupon.get("coupon_id"),
                  "redemption_code":        coupon.get("code"),
                  "offer_title":                offer.get("title"),
                  "offer_discount_percent": offer.get("discount_percent"),
                  "redeemed_at":              _iso(now),
                  "cpa_charge":                cpa_result}


@router.get("/merchant/{merchant_id}/cashier/redemptions/today")
async def cashier_today(merchant_id: str, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_redeem_coupons")
    biz_id = biz.get("business_id") or biz.get("_id")
    start_of_day = _now().replace(hour=0, minute=0, second=0, microsecond=0)

    q = {"merchant_id": biz_id, "redeemed_at": {"$gte": start_of_day}}
    total = await db.merchant_redemptions.count_documents(q)
    rows = await db.merchant_redemptions.find(q).sort("redeemed_at", -1) \
                                          .limit(20).to_list(20)
    def _v(r):
        return {"redemption_id":  r.get("redemption_id"),
                        "coupon_id":            r.get("coupon_id"),
                        "redemption_code": r.get("redemption_code"),
                        "offer_title":        r.get("offer_title"),
                        "offer_discount_percent": r.get("offer_discount_percent"),
                        "redeemed_at":      _iso(r.get("redeemed_at")),
                        "staff_user_id":  r.get("staff_user_id"),
                        "notes":                    r.get("notes")}
    return {"count": total, "list": [_v(r) for r in rows]}


# ─── My role (helper for shell + sidebar) ─────────────────────────
@router.get("/merchant/{merchant_id}/me/role")
async def my_role(merchant_id: str, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await db.businesses.find_one({"$or": [
        {"business_id": merchant_id}, {"_id": merchant_id}]})
    if not biz:
        raise HTTPException(404, "merchant_not_found")
    role = await get_user_role_for_merchant(db, user=user, biz=biz)
    return {"merchant_id": merchant_id,
                  "role":                role,
                  "permissions": sorted(permissions_for_role(role))}


# ─── Merchants where current user is an active staff member ────
@router.get("/merchant/mine/as-staff")
async def mine_as_staff(request: Request,
                                              user: dict = Depends(current_user)):
    """Complements /api/merchant/mine (owner-only) — returns merchants
    where the current user is an active staff member."""
    db = request.app.state.db
    uid = user.get("user_id")
    items = []
    cursor = db.businesses.find(
        {"staff_users": {"$elemMatch": {"user_id": uid, "active": True}}})
    async for biz in cursor:
        # Find the staff row
        my_row = next((s for s in (biz.get("staff_users") or [])
                                      if s.get("user_id") == uid and s.get("active", True)),
                                    None)
        items.append({
            "merchant_id":            biz.get("business_id") or biz.get("_id"),
            "name":                          biz.get("name"),
            "logo_url":                    biz.get("logo_url"),
            "category_id":            biz.get("category_id"),
            "merchant_status":      biz.get("merchant_status"),
            "owner_user_id":        biz.get("owner_user_id"),
            "stripe_charges_enabled": bool(biz.get("stripe_charges_enabled")),
            "stripe_payouts_enabled": bool(biz.get("stripe_payouts_enabled")),
            "role":                          (my_row or {}).get("role"),
            "staff_user_id":        (my_row or {}).get("staff_user_id"),
            "is_staff_member":  True,
        })
    return {"items": items, "count": len(items)}


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_mer2_indexes(db) -> None:
    await db.merchant_staff_invites.create_index("token", unique=True)
    await db.merchant_staff_invites.create_index(
        [("merchant_id", 1), ("email", 1), ("status", 1)])
    await db.merchant_staff_invites.create_index(
        [("merchant_id", 1), ("created_at", -1)])
    await db.merchant_redemptions.create_index(
        [("merchant_id", 1), ("redeemed_at", -1)])
    await db.merchant_redemptions.create_index("coupon_id", unique=True)


__all__ = ["router", "ensure_mer2_indexes"]
