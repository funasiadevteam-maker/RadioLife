"""P1.1 — Unified Coupon Passes (QR + in-store redeem).

Every coupon a user owns — regardless of which engine minted it
(games_v2 wallet items, ad-saved `db.coupons`, or flat `/play` wins in
`db.plays`) — can be turned into ONE scannable QR pass and settled
in-store through a single redeem path.

A `coupon_passes` record is created idempotently per (user, source,
ref_id) with a stable random token; the QR encodes that token. Staff /
admin scan + POST the token to redeem, which flips the pass to
`redeemed` AND best-effort syncs the underlying source record.

Endpoints
  POST /api/me/coupons/pass            {source,id} → {token, qr_data_uri, ...}
  GET  /api/coupons/pass/{token}       → pass preview (title/sponsor/status)
  POST /api/coupons/redeem/{token}     → settle (admin OR advertiser/merchant)
"""
from __future__ import annotations

import base64
import io
import secrets
from datetime import datetime, timezone

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user

me_pass_router = APIRouter(prefix="/api/me/coupons", tags=["coupon-pass"])
pass_router = APIRouter(prefix="/api/coupons", tags=["coupon-pass"])

VALID_SOURCES = {"wallet", "saved", "game_win"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _qr_data_uri(payload: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def _resolve_coupon(db, uid: str, source: str, ref_id: str) -> dict | None:
    """Return a normalized view of the underlying coupon, or None."""
    if source == "wallet":
        wi = await db.user_wallet_items.find_one({"_id": ref_id, "user_id": uid})
        if not wi:
            return None
        return {
            "title": wi.get("title") or "Coupon",
            "code": wi.get("short_code") or wi.get("coupon_id") or str(wi.get("_id")),
            "campaign_id": wi.get("campaign_id") or wi.get("source_campaign_id"),
            "redeemed": bool(wi.get("redeemed_at")),
        }
    if source == "saved":
        cp = await db.coupons.find_one({"_id": ref_id, "user_id": uid})
        if not cp:
            return None
        return {
            "title": cp.get("title") or "Saved coupon",
            "code": cp.get("code") or str(cp.get("_id")),
            "campaign_id": cp.get("attribution_campaign_id"),
            "redeemed": cp.get("status") in ("redeemed", "used"),
        }
    if source == "game_win":
        pl = await db.plays.find_one({"_id": ref_id, "listenerId": uid})
        if not pl:
            return None
        coupon = pl.get("coupon") or {}
        return {
            "title": pl.get("prizeTitle") or "Discount coupon",
            "code": coupon.get("code") or str(pl.get("_id")),
            "campaign_id": pl.get("gameId"),
            "redeemed": bool(pl.get("coupon_redeemed_at")),
        }
    return None


async def _sponsor_name(db, campaign_id: str | None) -> str | None:
    if not campaign_id:
        return None
    c = await db.game_campaigns.find_one(
        {"campaign_id": campaign_id}, {"sponsor_name": 1, "_id": 0})
    return (c or {}).get("sponsor_name")


class PassBody(BaseModel):
    source: str
    id: str


@me_pass_router.post("/pass")
async def create_or_get_pass(body: PassBody, request: Request,
                             user: dict = Depends(current_user)):
    """Idempotently mint (or fetch) the QR pass for one of the caller's coupons."""
    db = request.app.state.db
    uid = user["user_id"]
    if body.source not in VALID_SOURCES:
        raise HTTPException(400, "invalid_source")
    resolved = await _resolve_coupon(db, uid, body.source, body.id)
    if not resolved:
        raise HTTPException(404, "coupon_not_found")

    existing = await db.coupon_passes.find_one(
        {"user_id": uid, "source": body.source, "ref_id": body.id})
    if existing:
        token = existing["token"]
        status = existing.get("status") or "active"
    else:
        token = "clp_" + secrets.token_urlsafe(16)
        status = "redeemed" if resolved["redeemed"] else "active"
        sponsor = await _sponsor_name(db, resolved.get("campaign_id"))
        await db.coupon_passes.insert_one({
            "_id": token, "token": token, "user_id": uid,
            "source": body.source, "ref_id": body.id,
            "code": resolved["code"], "title": resolved["title"],
            "sponsor_name": sponsor, "campaign_id": resolved.get("campaign_id"),
            "status": status, "created_at": _now(),
            "redeemed_at": _now() if resolved["redeemed"] else None,
            "redeemed_by": None,
        })
    return {
        "token": token,
        "status": status,
        "code": resolved["code"],
        "title": resolved["title"],
        "qr_data_uri": _qr_data_uri(token),
    }


@pass_router.get("/pass/{token}")
async def preview_pass(token: str, request: Request):
    """Merchant-facing preview of a scanned pass (before settling)."""
    db = request.app.state.db
    p = await db.coupon_passes.find_one({"token": token})
    if not p:
        raise HTTPException(404, "pass_not_found")
    return {
        "token": token, "title": p.get("title"),
        "code": p.get("code"), "sponsor_name": p.get("sponsor_name"),
        "status": p.get("status") or "active",
        "redeemed_at": p["redeemed_at"].isoformat() if p.get("redeemed_at") else None,
    }


def _can_redeem(user: dict) -> bool:
    return bool(user.get("role") == "admin"
                or user.get("is_advertiser")
                or user.get("is_merchant")
                or user.get("is_business_owner"))


@pass_router.post("/redeem/{token}")
async def redeem_pass(token: str, request: Request,
                      user: dict = Depends(current_user)):
    """Settle a coupon pass in-store. Gated to staff (admin / advertiser /
    merchant). One-time use — a second scan returns already_redeemed."""
    db = request.app.state.db
    if not _can_redeem(user):
        raise HTTPException(403, "staff_role_required")
    p = await db.coupon_passes.find_one({"token": token})
    if not p:
        raise HTTPException(404, "pass_not_found")
    if (p.get("status") == "redeemed") or p.get("redeemed_at"):
        raise HTTPException(400, "already_redeemed")
    now = _now()
    res = await db.coupon_passes.update_one(
        {"token": token, "redeemed_at": None},
        {"$set": {"status": "redeemed", "redeemed_at": now,
                  "redeemed_by": user["user_id"]}})
    if res.modified_count != 1:
        raise HTTPException(400, "already_redeemed")

    # Best-effort sync of the underlying source record so /me/wallet-coupons
    # reflects the redemption too.
    src, ref = p.get("source"), p.get("ref_id")
    try:
        if src == "wallet":
            await db.user_wallet_items.update_one(
                {"_id": ref}, {"$set": {"redeemed_at": now, "status": "redeemed"}})
        elif src == "saved":
            await db.coupons.update_one(
                {"_id": ref}, {"$set": {"status": "redeemed", "redeemed_at": now}})
        elif src == "game_win":
            await db.plays.update_one(
                {"_id": ref}, {"$set": {"coupon_redeemed_at": now}})
    except Exception:
        pass
    return {"ok": True, "token": token, "status": "redeemed",
            "redeemed_at": now.isoformat(), "title": p.get("title")}


async def ensure_coupon_pass_indexes(db) -> None:
    await db.coupon_passes.create_index(
        [("user_id", 1), ("source", 1), ("ref_id", 1)],
        unique=True, name="coupon_pass_owner_unique")
    await db.coupon_passes.create_index([("token", 1)], unique=True)


__all__ = ["me_pass_router", "pass_router", "ensure_coupon_pass_indexes"]
