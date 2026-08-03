"""Phase AD.6 — Advertiser App: Staff RBAC + Redemption scanner + live feed.

Endpoints
─────────
  Owner-controlled staff management (advertiser owner or admin):
      POST      /api/advertiser-app/{advertiser_id}/staff/invite
      GET        /api/advertiser-app/{advertiser_id}/staff
      PATCH    /api/advertiser-app/{advertiser_id}/staff/{staff_user_id}/role
      DELETE  /api/advertiser-app/{advertiser_id}/staff/{staff_user_id}
      POST      /api/advertiser-app/{advertiser_id}/staff/invites/{invite_id}/revoke

  Public/authed accept flow (mirrors MER.2):
      GET        /api/advertiser-app/staff/invite/{token}/preview     (public)
      POST      /api/advertiser-app/staff/invite/{token}/accept      (auth)

  Redemption (redemption_staff, manager, owner, admin):
      POST      /api/advertiser-app/{advertiser_id}/scan               → preview
      POST      /api/advertiser-app/{advertiser_id}/redeem            → mark redeemed
      GET        /api/advertiser-app/{advertiser_id}/redemptions/live  → last 50

  Consumer utility (used by the advertiser shell to route to /apply):
      GET        /api/advertiser-app/me/roles → [{advertiser_id, name, role}, …]
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth import current_user
from services.advertiser_rbac_service import (
    STAFF_ROLES,
    resolve_advertiser_with_role,
    get_user_role_for_advertiser,
    list_user_advertisers,
)

router = APIRouter(tags=["advertiser-staff"])
logger = logging.getLogger("bigfm.ad6")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt) -> Optional[datetime]:
    """Coerce a Mongo naive datetime to UTC-aware for safe comparison."""
    if dt is None or not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else dt


def _b62(n: int = 24) -> str:
    alphabet = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                            "abcdefghijklmnopqrstuvwxyz"
                            "0123456789")
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or ""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}…@{domain}"
    return f"{local[:2]}…@{domain}"


# ═══════════════════════════════════════════════════════════════════
# Body models
# ═══════════════════════════════════════════════════════════════════
class InviteBody(BaseModel):
    email:  EmailStr
    role:    str = Field(..., description="One of manager | redemption_staff | analytics_only")


class RoleBody(BaseModel):
    role: str = Field(..., description="New role.")


class ScanBody(BaseModel):
    code: str = Field(min_length=3, max_length=64)


class RedeemBody(BaseModel):
    code:    str = Field(min_length=3, max_length=64)
    notes:  Optional[str] = Field(default=None, max_length=200)


class AcceptBody(BaseModel):
    """Empty on purpose — the auth cookie carries the user context."""
    pass


# ═══════════════════════════════════════════════════════════════════
# Staff — invite / list / role / revoke
# ═══════════════════════════════════════════════════════════════════
@router.post("/api/advertiser-app/{advertiser_id}/staff/invite",
                          description="Advertiser owner or manager invites a new staff member by email.")
async def invite_staff(advertiser_id: str, body: InviteBody, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    adv, actor_role = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user,
        permission="can_invite_staff")

    if body.role not in STAFF_ROLES:
        raise HTTPException(400, {"code": "invalid_role",
                                                          "allowed": sorted(STAFF_ROLES)})
    email = body.email.lower()

    # Do not invite the owner themselves.
    if (adv.get("contact_email") or "").lower() == email:
        raise HTTPException(400, {"code": "cannot_invite_owner"})
    for s in (adv.get("staff_users") or []):
        if (s.get("email") or "").lower() == email and s.get("active", True):
            raise HTTPException(409, {"code": "already_staff",
                                                              "detail": f"{email} is already {s.get('role')}."})

    existing = await db.advertiser_staff_invites.find_one(
        {"advertiser_id": advertiser_id, "email": email, "status": "pending"})
    if existing:
        raise HTTPException(409, {"code": "invite_pending",
                                                          "invite_id": existing.get("invite_id")})

    invite_id = f"adv_inv_{uuid.uuid4().hex[:12]}"
    token = _b62(24)
    now = _now()
    doc = {
        "_id":                          invite_id,
        "invite_id":              invite_id,
        "advertiser_id":      advertiser_id,
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
    await db.advertiser_staff_invites.insert_one(doc)

    origin = os.environ.get("FRONTEND_ORIGIN") or _guess_frontend(request)
    invite_url = f"{origin.rstrip('/')}/advertiser-app/staff/accept/{token}"

    # Best-effort Mailgun send — non-blocking.
    try:
        from services.mailgun_client import send_email, is_live
        if is_live():
            subject = (f"You’ve been invited to {adv.get('name', 'an advertiser')} "
                                  "on BigFM Ads")
            html = (
                "<div style='font-family:system-ui,sans-serif;max-width:520px;'>"
                f"<h2 style='color:#f59e0b'>You’ve got an invite ✨</h2>"
                f"<p><b>{adv.get('name', 'A BigFM advertiser')}</b> invited you to join "
                f"their team as <b>{body.role}</b>.</p>"
                f"<p style='margin:24px 0'>"
                f"<a href='{invite_url}' style='background:#f59e0b;color:#0f172a;"
                f"text-decoration:none;padding:10px 24px;border-radius:999px;"
                f"font-weight:bold;font-size:14px'>Accept invite</a></p>"
                f"<p style='color:#64748b;font-size:12px'>The link expires in 7 days.</p>"
                f"<p style='color:#64748b;font-size:12px'>URL: <code>{invite_url}</code></p>"
                "</div>")
            send_email(to=email, subject=subject, html=html,
                              text=f"Accept invite: {invite_url}",
                              tags=["ad6_advertiser_invite"])
            logger.info("[ad6] invite sent to=%s role=%s adv=%s",
                                    email, body.role, advertiser_id)
    except Exception:
        logger.exception("[ad6] mailgun invite email failed (non-blocking)")

    return {"invite_id": invite_id, "email": email, "role": body.role,
                  "token": token, "expires_at": _iso(doc["expires_at"]),
                  "invite_url": invite_url}


def _guess_frontend(request: Request) -> str:
    """Same trick as MER.2 — derive from Host header if env is unset."""
    host = request.headers.get("origin") or request.headers.get("host")
    if host and not host.startswith("http"):
        proto = request.url.scheme or "https"
        return f"{proto}://{host}"
    return host or ""


@router.get("/api/advertiser-app/{advertiser_id}/staff",
                          description="List active staff + pending invites.")
async def list_staff(advertiser_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    adv, _ = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user,
        permission="can_invite_staff")
    staff = list(adv.get("staff_users") or [])
    # Serialize datetimes.
    for s in staff:
        for k in ("invited_at", "accepted_at", "updated_at"):
            if isinstance(s.get(k), datetime):
                s[k] = s[k].isoformat()
    invites = await db.advertiser_staff_invites.find(
        {"advertiser_id": advertiser_id, "status": "pending"}
    ).sort([("created_at", -1)]).to_list(50)
    for inv in invites:
        inv.pop("_id", None)
        for k in ("created_at", "expires_at", "accepted_at"):
            if isinstance(inv.get(k), datetime):
                inv[k] = inv[k].isoformat()
    # Add owner as a synthetic first row so the UI can display them.
    owner_email = adv.get("contact_email") or ""
    owner_row = {"staff_user_id": adv.get("owner_user_id"),
                              "email":                    owner_email, "role": "owner",
                              "active":                  True,
                              "invited_at":          _iso(adv.get("created_at"))}
    return {"advertiser_id": advertiser_id,
                  "owner_email":      owner_email,
                  "staff":                  [owner_row] + [s for s in staff if s.get("active", True)],
                  "invites":              invites}


@router.patch("/api/advertiser-app/{advertiser_id}/staff/{staff_user_id}/role")
async def update_staff_role(advertiser_id: str, staff_user_id: str,
                                                                    body: RoleBody, request: Request,
                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    adv, _ = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user,
        permission="can_invite_staff")
    if body.role not in STAFF_ROLES:
        raise HTTPException(400, {"code": "invalid_role",
                                                          "allowed": sorted(STAFF_ROLES)})
    if adv.get("owner_user_id") == staff_user_id:
        raise HTTPException(400, {"code": "cannot_change_owner_role"})
    r = await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id,
          "staff_users.staff_user_id": staff_user_id},
        {"$set": {"staff_users.$.role": body.role,
                          "staff_users.$.updated_at": _now()}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "staff_not_found"})
    return {"ok": True, "staff_user_id": staff_user_id, "role": body.role}


@router.delete("/api/advertiser-app/{advertiser_id}/staff/{staff_user_id}",
                              description=("Soft-revoke a staff seat.  Flips `active=false` "
                                                            "so future scans return 403 immediately."))
async def revoke_staff(advertiser_id: str, staff_user_id: str,
                                              request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    adv, _ = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user,
        permission="can_invite_staff")
    if adv.get("owner_user_id") == staff_user_id:
        raise HTTPException(400, {"code": "cannot_revoke_owner"})
    r = await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id,
          "staff_users.staff_user_id": staff_user_id},
        {"$set": {"staff_users.$.active":    False,
                          "staff_users.$.revoked_at": _now(),
                          "staff_users.$.revoked_by": user.get("user_id")}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "staff_not_found"})
    return {"ok": True, "revoked_user_id": staff_user_id}


@router.post("/api/advertiser-app/{advertiser_id}/staff/invites/{invite_id}/revoke")
async def revoke_invite(advertiser_id: str, invite_id: str, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    _adv, _ = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user,
        permission="can_invite_staff")
    r = await db.advertiser_staff_invites.update_one(
        {"invite_id": invite_id, "advertiser_id": advertiser_id,
          "status": "pending"},
        {"$set": {"status": "revoked", "revoked_at": _now(),
                          "revoked_by": user.get("user_id")}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "invite_not_found"})
    return {"ok": True, "invite_id": invite_id}


# ═══════════════════════════════════════════════════════════════════
# Accept flow (public preview + authed accept)
# ═══════════════════════════════════════════════════════════════════
@router.get("/api/advertiser-app/staff/invite/{token}/preview",
                          description="Public — returns advertiser name + role so the accept page can render.")
async def invite_preview(token: str, request: Request):
    db = request.app.state.db
    inv = await db.advertiser_staff_invites.find_one({"token": token})
    if not inv:
        raise HTTPException(404, {"code": "invite_not_found"})
    if inv.get("status") != "pending":
        return {"status": inv.get("status"), "advertiser_name": None}
    exp = _aware(inv.get("expires_at"))
    if exp and exp < _now():
        return {"status": "expired"}
    adv = await db.advertisers_v2.find_one(
        {"advertiser_id": inv.get("advertiser_id")},
        {"name": 1, "logo_url": 1, "contact_email": 1, "_id": 0})
    return {
        "status":                        inv.get("status"),
        "advertiser_id":        inv.get("advertiser_id"),
        "advertiser_name":  (adv or {}).get("name"),
        "advertiser_logo_url": (adv or {}).get("logo_url"),
        "role":                            inv.get("role"),
        "email":                          _mask_email(inv.get("email") or ""),
        "expires_at":                _iso(inv.get("expires_at")),
    }


@router.post("/api/advertiser-app/staff/invite/{token}/accept",
                          description="Auth required — adds the user to the advertiser staff list.")
async def invite_accept(token: str, _body: AcceptBody, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    inv = await db.advertiser_staff_invites.find_one({"token": token})
    if not inv:
        raise HTTPException(404, {"code": "invite_not_found"})
    if inv.get("status") != "pending":
        raise HTTPException(409, {"code": f"invite_{inv.get('status')}"})
    exp = _aware(inv.get("expires_at"))
    if exp and exp < _now():
        raise HTTPException(410, {"code": "expired"})
    advertiser_id = inv.get("advertiser_id")
    role = inv.get("role")
    uid = user.get("user_id")
    email = (user.get("email") or "").lower()

    # Push into staff_users (or reactivate if already there).
    adv = await db.advertisers_v2.find_one({"advertiser_id": advertiser_id})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    existing = [s for s in (adv.get("staff_users") or [])
                              if s.get("staff_user_id") == uid]
    now = _now()
    if existing:
        await db.advertisers_v2.update_one(
            {"advertiser_id": advertiser_id,
              "staff_users.staff_user_id": uid},
            {"$set": {"staff_users.$.role":                  role,
                              "staff_users.$.active":            True,
                              "staff_users.$.accepted_at":  now,
                              "staff_users.$.email":            email,
                              "staff_users.$.updated_at":  now}})
    else:
        await db.advertisers_v2.update_one(
            {"advertiser_id": advertiser_id},
            {"$push": {"staff_users": {
                "staff_user_id":  uid,
                "email":                    email,
                "role":                      role,
                "active":                  True,
                "invited_at":          inv.get("created_at"),
                "invited_by":          inv.get("invited_by"),
                "accepted_at":        now,
                "updated_at":          now,
            }}})
    await db.advertiser_staff_invites.update_one(
        {"token": token},
        {"$set": {"status": "accepted",
                          "accepted_at": now,
                          "accepted_by_user_id": uid}})
    return {"ok": True, "advertiser_id": advertiser_id, "role": role}


# ═══════════════════════════════════════════════════════════════════
# Redemption scanner + live feed
# ═══════════════════════════════════════════════════════════════════
async def _lookup_coupon_by_code_or_qr(db, *, code_or_token: str) -> Optional[dict]:
    """Match a customer scan input against the coupons collection.

    Accepts:
        - `coupon_id` (e.g., `cp_...`, `cpn_...`)
        - `code` / `short_code` (e.g., `ADV-XYZ123`)
        - QR token from `user_wallet_items.qr_token` — resolves to the
          linked coupon via `coupons.source_wallet_item_id`.
    """
    raw = (code_or_token or "").strip()
    if not raw:
        return None
    up = raw.upper()
    # Direct coupon match.
    c = await db.coupons.find_one({"$or": [
        {"coupon_id": raw}, {"coupon_id": up},
        {"code": raw}, {"code": up},
        {"short_code": raw}, {"short_code": up},
    ]})
    if c:
        return c
    # QR-token → wallet_item → coupon.
    wi = await db.user_wallet_items.find_one({"qr_token": raw})
    if wi:
        c = await db.coupons.find_one(
            {"source_wallet_item_id": wi.get("wallet_item_id")})
        if c:
            return c
    return None


def _coupon_belongs_to_advertiser(coupon: dict, advertiser_id: str) -> bool:
    return (coupon or {}).get("advertiser_id") == advertiser_id


def _coupon_expired(coupon: dict) -> bool:
    exp = (coupon or {}).get("expires_at")
    if not exp:
        return False
    if isinstance(exp, str):
        try:
            exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        except Exception:
            return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp < _now()


async def _scan_view(db, *, coupon: dict) -> dict:
    campaign = None
    if coupon.get("ad_campaign_id"):
        campaign = await db.ad_campaigns_v2.find_one(
            {"campaign_id": coupon["ad_campaign_id"]},
            {"name": 1, "creative": 1, "_id": 0})
    customer = await db.users.find_one({"user_id": coupon.get("user_id")},
                                                                                    {"email": 1, "display_name": 1, "_id": 0}) \
                                  if coupon.get("user_id") else None
    return {
        "coupon_id":                          coupon.get("coupon_id"),
        "code":                                    coupon.get("code") or coupon.get("short_code"),
        "advertiser_id":                    coupon.get("advertiser_id"),
        "ad_campaign_id":                  coupon.get("ad_campaign_id"),
        "campaign_name":                    (campaign or {}).get("name"),
        "creative_headline":            (campaign or {}).get("creative", {}).get("headline"),
        "discount_value":                  coupon.get("discount_value"),
        "value_currency":                  coupon.get("value_currency") or "AED",
        "coupon_type":                        coupon.get("coupon_type") or "coupon",
        "customer_masked":                _mask_email((customer or {}).get("email") or ""),
        "customer_display_name":  (customer or {}).get("display_name"),
        "expires_at":                          _iso(coupon.get("expires_at")),
        "status":                                  coupon.get("status"),
    }


@router.post("/api/advertiser-app/{advertiser_id}/scan",
                          description=("Preview a customer scan without redeeming.  "
                                                          "Validates advertiser scope + expiry + status."))
async def advertiser_scan(advertiser_id: str, body: ScanBody, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    adv, _ = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user, permission="can_redeem")
    coupon = await _lookup_coupon_by_code_or_qr(db, code_or_token=body.code)
    if not coupon:
        return {"ok": False, "reason": "not_found"}
    if not _coupon_belongs_to_advertiser(coupon, advertiser_id):
        return {"ok": False, "reason": "wrong_advertiser_scope",
                      "code": coupon.get("code")}
    status = coupon.get("status")
    if status == "redeemed":
        return {"ok": False, "reason": "already_redeemed",
                      "redeemed_at": _iso(coupon.get("redeemed_at"))}
    if status == "revoked":
        return {"ok": False, "reason": "revoked"}
    if _coupon_expired(coupon):
        return {"ok": False, "reason": "expired"}
    if status not in ("saved", "claimed", "in_wallet", "active"):
        return {"ok": False, "reason": f"invalid_status_{status}"}
    return {"ok": True, **await _scan_view(db, coupon=coupon)}


@router.post("/api/advertiser-app/{advertiser_id}/redeem",
                          description=("Mark a coupon redeemed by the calling advertiser.  "
                                                          "Requires `can_redeem`.  Idempotent — a race that "
                                                          "loses the atomic flip returns 409 already_redeemed_race."))
async def advertiser_redeem(advertiser_id: str, body: RedeemBody, request: Request,
                                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    adv, role = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user, permission="can_redeem")
    coupon = await _lookup_coupon_by_code_or_qr(db, code_or_token=body.code)
    if not coupon:
        raise HTTPException(404, {"code": "not_found"})
    if not _coupon_belongs_to_advertiser(coupon, advertiser_id):
        raise HTTPException(403, {"code": "wrong_advertiser_scope"})
    if coupon.get("status") == "redeemed":
        raise HTTPException(409, {"code": "already_redeemed",
                                                          "redeemed_at": _iso(coupon.get("redeemed_at"))})
    if coupon.get("status") == "revoked":
        raise HTTPException(400, {"code": "revoked"})
    if _coupon_expired(coupon):
        raise HTTPException(410, {"code": "expired"})

    now = _now()
    result = await db.coupons.update_one(
        {"coupon_id": coupon["coupon_id"],
          "status": {"$in": ["saved", "claimed", "in_wallet", "active"]}},
        {"$set": {"status":                                              "redeemed",
                          "redeemed_at":                                  now,
                          "redeemed_by_advertiser_id":      advertiser_id,
                          "redeemed_by_staff_user_id":      user.get("user_id"),
                          "redeemed_by_staff_role":            role,
                          "redemption_source_type":            "advertiser_scan"}})
    if result.matched_count == 0:
        raise HTTPException(409, {"code": "already_redeemed_race"})
    # Sync the wallet item too (so /wallet UI reflects redemption).
    if coupon.get("source_wallet_item_id"):
        await db.user_wallet_items.update_one(
            {"wallet_item_id": coupon["source_wallet_item_id"]},
            {"$set": {"status": "redeemed", "redeemed_at": now}})

    redemption_id = f"advr_{uuid.uuid4().hex[:14]}"
    await db.advertiser_redemptions.insert_one({
        "_id":                              redemption_id,
        "redemption_id":            redemption_id,
        "advertiser_id":            advertiser_id,
        "ad_campaign_id":          coupon.get("ad_campaign_id"),
        "coupon_id":                    coupon.get("coupon_id"),
        "wallet_item_id":          coupon.get("source_wallet_item_id"),
        "code":                            coupon.get("code") or coupon.get("short_code"),
        "customer_user_id":      coupon.get("user_id"),
        "staff_user_id":            user.get("user_id"),
        "staff_role":                  role,
        "coupon_type":                coupon.get("coupon_type") or "coupon",
        "notes":                          (body.notes or "")[:200],
        "redeemed_at":                now,
    })
    logger.info("[ad6] REDEEMED coupon=%s adv=%s staff=%s role=%s",
                            coupon.get("coupon_id"), advertiser_id,
                            user.get("user_id"), role)

    # Phase N (M7) — CPA charge on redemption.  Best-effort;
    # never blocks the redemption.
    try:
        from services.coupon_cpa_charge_pipeline import (
            try_charge_after_redemption)
        cpa_result = await try_charge_after_redemption(
            db, coupon_id=coupon["coupon_id"],
            redemption_type="advertiser_staff",
            staff_user_id=user.get("user_id"))
    except Exception as _e:
        logger.warning("[ad6] CPA charge failed: %s", _e)
        cpa_result = None

    view = await _scan_view(db, coupon=coupon)
    return {"ok": True, "redemption_id": redemption_id,
                  "redeemed_at": _iso(now),
                  "cpa_charge": cpa_result, **view}


@router.get("/api/advertiser-app/{advertiser_id}/redemptions/live",
                          description="Return the last 50 redemptions for this advertiser (any staff).")
async def redemptions_live(advertiser_id: str, request: Request,
                                                            limit: int = 50,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    _adv, _ = await resolve_advertiser_with_role(
        db, advertiser_id=advertiser_id, user=user,
        permission="can_view_scan_history")
    rows = await db.advertiser_redemptions.find(
        {"advertiser_id": advertiser_id}
    ).sort([("redeemed_at", -1)]).to_list(min(int(limit or 50), 200))

    # Batch-enrich with staff email + campaign name.
    staff_ids = list({r.get("staff_user_id") for r in rows if r.get("staff_user_id")})
    users = {}
    if staff_ids:
        async for u in db.users.find({"user_id": {"$in": staff_ids}},
                                                                                {"user_id": 1, "email": 1, "display_name": 1, "_id": 0}):
            users[u["user_id"]] = u
    camp_ids = list({r.get("ad_campaign_id") for r in rows if r.get("ad_campaign_id")})
    camps = {}
    if camp_ids:
        async for c in db.ad_campaigns_v2.find({"campaign_id": {"$in": camp_ids}},
                                                                                                {"campaign_id": 1, "name": 1, "_id": 0}):
            camps[c["campaign_id"]] = c

    out = []
    for r in rows:
        row = {k: v for k, v in r.items() if k != "_id"}
        for k, v in list(row.items()):
            if isinstance(v, datetime):
                row[k] = v.isoformat()
        u = users.get(r.get("staff_user_id"))
        row["staff_email"] = (u or {}).get("email")
        row["staff_display_name"] = (u or {}).get("display_name")
        row["campaign_name"] = camps.get(r.get("ad_campaign_id"), {}).get("name")
        out.append(row)
    return {"items": out, "count": len(out)}


# ═══════════════════════════════════════════════════════════════════
# Consumer utility
# ═══════════════════════════════════════════════════════════════════
@router.get("/api/advertiser-app/me/roles",
                          description=("Return every advertiser the caller can access "
                                                          "with their effective role.  Used to gate `/advertiser/*` UI."))
async def my_advertiser_roles(request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    advs = await list_user_advertisers(db, user=user)
    out = []
    for adv in advs:
        role = await get_user_role_for_advertiser(db, user=user, adv=adv)
        out.append({
            "advertiser_id":  adv.get("advertiser_id"),
            "name":                    adv.get("name"),
            "status":                adv.get("status"),
            "logo_url":            adv.get("logo_url"),
            "role":                    role,
        })
    return {"items": out, "count": len(out)}


# ═══════════════════════════════════════════════════════════════════
# Index helper (called from server bootstrap)
# ═══════════════════════════════════════════════════════════════════
async def ensure_ad6_indexes(db) -> None:
    try:
        await db.advertiser_staff_invites.create_index("invite_id", unique=True)
        await db.advertiser_staff_invites.create_index("token",       unique=True)
        await db.advertiser_staff_invites.create_index([
            ("advertiser_id", 1), ("email", 1), ("status", 1)])
        await db.advertisers_v2.create_index("staff_users.staff_user_id",
                                                                                              sparse=True,
                                                                                              name="idx_ad6_staff_uid")
        await db.advertiser_redemptions.create_index("redemption_id", unique=True)
        await db.advertiser_redemptions.create_index([
            ("advertiser_id", 1), ("redeemed_at", -1)])
        await db.advertiser_redemptions.create_index("staff_user_id", sparse=True)
        # Scope isolation on coupons + wallet items (sparse — most legacy
        # rows won't have this field).
        await db.coupons.create_index("advertiser_id",
                                                                        sparse=True, name="idx_ad6_coupons_adv")
        await db.user_wallet_items.create_index("advertiser_id",
                                                                                              sparse=True, name="idx_ad6_wi_adv")
    except Exception as e:
        logger.warning("[ad6] index setup: %s", e)


__all__ = ["router", "ensure_ad6_indexes"]
