"""Soft-launch — Business Setup Mode.

Central launch config, consumer waitlist, admin preview-token management, and
the merchant "6 months free" soft-launch claim. Pairs with
`services/launch_guard.py` (the server-side enforcement middleware).
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from auth import current_user, current_user_optional, require_admin
from services.launch_guard import (
    LAUNCH_KEY, bust_launch_cache, get_launch_settings, resolve_bypass,
    valid_preview_token,
)

router = APIRouter(prefix="/api", tags=["soft-launch"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _clean(d: dict) -> dict:
    if not d:
        return d
    d.pop("_id", None)
    return d


# ─────────────────────────── PUBLIC ────────────────────────────────
@router.get("/launch/status")
async def launch_status(request: Request):
    """Public — the frontend guard reads this to decide Coming-Soon vs app."""
    db = request.app.state.db
    s = await get_launch_settings(db)
    if not s.get("business_setup_mode_enabled"):
        return {"business_setup_mode": False,
                "waitlist_enabled": bool(s.get("waitlist_enabled")),
                "offer_months": int(s.get("offer_months", 6)),
                "has_bypass": True, "bypass_reason": None}
    has_bypass, reason = await resolve_bypass(request, db)
    return {"business_setup_mode": True,
            "waitlist_enabled": bool(s.get("waitlist_enabled")),
            "offer_months": int(s.get("offer_months", 6)),
            "has_bypass": bool(has_bypass), "bypass_reason": reason}


@router.post("/waitlist")
async def join_waitlist(request: Request, body: dict = Body(default={})):
    db = request.app.state.db
    s = await get_launch_settings(db)
    if not s.get("waitlist_enabled"):
        raise HTTPException(403, {"code": "waitlist_closed"})
    email = str((body or {}).get("email") or "").strip().lower()[:120]
    if not _EMAIL.match(email):
        raise HTTPException(400, {"code": "invalid_email"})
    interests = [str(x)[:40] for x in ((body or {}).get("interests") or [])][:12]
    city = str((body or {}).get("city") or "").strip()[:80] or None
    try:
        user = await current_user_optional(request)
    except Exception:
        user = None
    await db.consumer_waitlist.update_one(
        {"email": email},
        {"$set": {"email": email, "interests": interests, "city": city,
                  "user_id": (user or {}).get("user_id"), "updated_at": _now_iso()},
         "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True)
    total = await db.consumer_waitlist.count_documents({})
    return {"ok": True, "position": total}


@router.post("/launch/preview/redeem")
async def redeem_preview(request: Request, response: Response, body: dict = Body(default={})):
    db = request.app.state.db
    token = str((body or {}).get("token") or "").strip()[:80]
    if not token or not await valid_preview_token(db, token):
        raise HTTPException(400, {"code": "invalid_token"})
    await db.preview_tokens.update_one(
        {"token": token},
        {"$inc": {"uses": 1}, "$set": {"last_used_at": _now_iso()}})
    response.set_cookie("rl_preview_token", token, max_age=60 * 60 * 24 * 30,
                        httponly=False, samesite="lax", path="/")
    return {"ok": True, "valid": True}


# ─────────────────────────── ADMIN ─────────────────────────────────
@router.get("/admin/launch-settings")
async def admin_get_settings(request: Request, admin: dict = Depends(require_admin)):
    return await get_launch_settings(request.app.state.db)


@router.patch("/admin/launch-settings")
async def admin_patch_settings(request: Request, body: dict = Body(default={}),
                               admin: dict = Depends(require_admin)):
    db = request.app.state.db
    updates: dict = {}
    if "business_setup_mode_enabled" in (body or {}):
        updates["business_setup_mode_enabled"] = bool(body["business_setup_mode_enabled"])
    if "waitlist_enabled" in (body or {}):
        updates["waitlist_enabled"] = bool(body["waitlist_enabled"])
    if "offer_months" in (body or {}):
        try:
            updates["offer_months"] = max(1, min(24, int(body["offer_months"])))
        except Exception:
            pass
    if not updates:
        raise HTTPException(400, {"code": "no_updates"})
    updates["updated_at"] = _now_iso()
    updates["updated_by"] = admin.get("user_id")
    await db.platform_settings.update_one(
        {"key": LAUNCH_KEY}, {"$set": {"key": LAUNCH_KEY, **updates}}, upsert=True)
    bust_launch_cache()
    return await get_launch_settings(db)


@router.get("/admin/waitlist")
async def admin_waitlist(request: Request, admin: dict = Depends(require_admin),
                         limit: int = 300):
    db = request.app.state.db
    total = await db.consumer_waitlist.count_documents({})
    items = []
    async for w in db.consumer_waitlist.find({}, {"_id": 0}).sort("created_at", -1).limit(min(limit, 1000)):
        items.append(w)
    return {"total": total, "items": items}


def _new_token() -> str:
    return "pv_" + secrets.token_urlsafe(18)


@router.post("/admin/preview-tokens")
async def admin_create_token(request: Request, body: dict = Body(default={}),
                             admin: dict = Depends(require_admin)):
    db = request.app.state.db
    label = str((body or {}).get("label") or "").strip()[:80] or "Preview access"
    try:
        max_uses = max(0, int((body or {}).get("max_uses") or 0))
    except Exception:
        max_uses = 0
    try:
        expires_days = max(0, int((body or {}).get("expires_days") or 0))
    except Exception:
        expires_days = 0
    token = _new_token()
    doc = {
        "token": token, "label": label, "max_uses": max_uses, "uses": 0,
        "revoked": False, "created_by": admin.get("user_id"),
        "created_at": _now_iso(),
        "expires_at": ((_now() + timedelta(days=expires_days)).isoformat()
                       if expires_days > 0 else None),
    }
    await db.preview_tokens.insert_one(dict(doc))
    return {"ok": True, "token": token, "record": _clean(doc)}


@router.get("/admin/preview-tokens")
async def admin_list_tokens(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    items = []
    async for t in db.preview_tokens.find({}, {"_id": 0}).sort("created_at", -1).limit(200):
        items.append(t)
    return {"items": items}


@router.post("/admin/preview-tokens/{token}/revoke")
async def admin_revoke_token(token: str, request: Request,
                             admin: dict = Depends(require_admin)):
    db = request.app.state.db
    r = await db.preview_tokens.update_one(
        {"token": token}, {"$set": {"revoked": True, "revoked_at": _now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, {"code": "not_found"})
    bust_launch_cache()
    return {"ok": True}


# ────────────────────── MERCHANT SOFT-LAUNCH ───────────────────────
_COMMISSION_NOTE = ("Your monthly subscription fee is waived for the soft-launch "
                    "period. Standard per-sale commission still applies on the "
                    "products you sell.")


@router.get("/merchant/soft-launch/offer")
async def merchant_offer(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await get_launch_settings(db)
    months = int(s.get("offer_months", 6))
    uid = user.get("user_id")
    claim = await db.soft_launch_claims.find_one({"user_id": uid}, {"_id": 0})
    prof = await db.marketplace_profiles.find_one({"owner_user_id": uid})
    biz = await db.businesses.find_one({"owner_user_id": uid})
    return {
        "offer_months": months,
        "has_business": bool(prof or biz or user.get("is_business")),
        "has_storefront": bool(prof),
        "claimed": bool(claim),
        "claim": claim,
        "commission_note": _COMMISSION_NOTE,
    }


@router.post("/merchant/soft-launch/claim")
async def merchant_claim(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await get_launch_settings(db)
    months = int(s.get("offer_months", 6))
    uid = user.get("user_id")
    existing = await db.soft_launch_claims.find_one({"user_id": uid})
    if existing:
        return {"ok": True, "already": True, "claim": _clean(dict(existing))}
    free_until = (_now() + timedelta(days=30 * months)).isoformat()
    claim = {"user_id": uid, "months": months, "free_until": free_until,
             "status": "active", "claimed_at": _now_iso()}
    await db.soft_launch_claims.insert_one(dict(claim))
    # Grant the business role so the merchant gets preview bypass immediately.
    await db.users.update_one(
        {"user_id": uid},
        {"$addToSet": {"roles": "business"},
         "$set": {"is_business": True, "soft_launch_offer": claim}})
    # If they already have a storefront, waive its monthly subscription fee.
    prof = await db.marketplace_profiles.find_one({"owner_user_id": uid})
    if prof:
        await db.marketplace_profiles.update_one(
            {"owner_user_id": uid},
            {"$set": {"subscription_active": True, "status": "approved",
                      "soft_launch_offer": claim, "updated_at": _now_iso()}})
        await db.merchant_subscriptions.update_one(
            {"business_id": prof["business_id"]},
            {"$set": {"business_id": prof["business_id"], "plan_id": "soft_launch_free",
                      "status": "active", "soft_launch": True, "free_until": free_until,
                      "updated_at": _now_iso()},
             "$setOnInsert": {"created_at": _now_iso()}}, upsert=True)
    bust_launch_cache()
    return {"ok": True, "claim": claim, "commission_note": _COMMISSION_NOTE}
