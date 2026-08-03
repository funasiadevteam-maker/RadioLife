"""Phase 41 Session 4.5.A — Announcement Coupons HTTP routes.

Three surfaces:

  POST /api/stations/{slug}/announcements/{ann_id}/coupon
      Owner attaches or updates the coupon on an announcement.
      Pass `{}` or `{"clear": true}` to remove the coupon.

  POST /api/announcements/{ann_id}/redeem
      ANON-ALLOWED. Body: {device_fingerprint, user_id?}.
      Idempotent: re-redeeming the same device returns the existing
      claim. 410 when cap reached or expired (typed code).

  GET  /api/me/coupons
      Authed listing of the caller's claimed coupons (most recent first).
      Optional `device_fingerprint` query supports anonymous-only flow.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, current_user_optional
from services.coupon_engine import (
    FP_RE,
    coupon_summary_public,
    ensure_coupon_indexes,  # re-exported for server.py wiring
    is_coupon_cap_reached,
    is_coupon_expired,
    new_qr_payload,
    new_red_id,
    validate_coupon_input,
    _now,
    _now_iso,
    _parse_iso_to_dt,
)


station_router = APIRouter(prefix="/api/stations", tags=["announcement-coupons"])
public_router  = APIRouter(prefix="/api/announcements", tags=["announcement-coupons"])
me_router      = APIRouter(prefix="/api/me", tags=["announcement-coupons"])

log = logging.getLogger("bigfm.announcement_coupons")


def _is_admin(u: Optional[dict]) -> bool:
    return bool(u and (u.get("role") == "admin" or u.get("is_admin")))


def _strip_ann_for_owner(ann: dict) -> dict:
    out = {k: v for k, v in ann.items() if k != "_id"}
    return out


# ──────────────────────────────────────────────────────────────────
# Owner: attach / update / clear a coupon on an announcement
# ──────────────────────────────────────────────────────────────────
@station_router.post("/{slug}/announcements/{ann_id}/coupon")
async def attach_or_update_coupon(slug: str, ann_id: str, body: dict,
                                    request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await db.community_radio_stations.find_one({"slug": slug})
    if not station:
        raise HTTPException(404, {"code": "not_found",
                                    "message": "Station not found."})
    if station.get("owner_user_id") != user.get("user_id") \
            and not _is_admin(user):
        raise HTTPException(403, {"code": "permission_denied",
                                    "message": "Not station owner."})

    ann = await db.station_announcements.find_one({"_id": ann_id,
                                                       "station_slug": slug})
    if not ann:
        raise HTTPException(404, {"code": "not_found",
                                    "message": "Announcement not found."})

    if body is None or body.get("clear") is True or body == {}:
        # Remove coupon entirely.
        await db.station_announcements.update_one(
            {"_id": ann_id},
            {"$unset": {"coupon": ""},
             "$set":   {"updated_at": _now_iso()}})
        # Also bust TV cache so listeners stop seeing the QR.
        try:
            from routes.station_tv import _bust_caches
            _bust_caches(slug)
        except Exception:
            pass
        return {"ok": True, "cleared": True, "announcement_id": ann_id}

    cleaned = validate_coupon_input(body)
    existing = (ann.get("coupon") or {})
    # Preserve the running counter if a coupon already existed.
    cleaned["redemptions_count"] = int(existing.get("redemptions_count") or 0)

    await db.station_announcements.update_one(
        {"_id": ann_id},
        {"$set": {"coupon": cleaned,
                  "updated_at": _now_iso()}})
    try:
        from routes.station_tv import _bust_caches
        _bust_caches(slug)
    except Exception:
        pass

    fresh = await db.station_announcements.find_one({"_id": ann_id})
    return {"ok": True,
            "announcement": _strip_ann_for_owner(dict(fresh))}


# ──────────────────────────────────────────────────────────────────
# Public: redeem a coupon (anon-allowed, idempotent)
# ──────────────────────────────────────────────────────────────────
@public_router.post("/{ann_id}/redeem")
async def redeem_announcement_coupon(ann_id: str, body: dict, request: Request,
                                        user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    if not isinstance(body, dict):
        raise HTTPException(400, {"code": "validation_error",
                                    "message": "Body required."})

    device_fp = (body.get("device_fingerprint") or "").strip()
    if not device_fp or not FP_RE.match(device_fp):
        raise HTTPException(400, {
            "code": "validation_error",
            "field": "device_fingerprint",
            "message": "device_fingerprint must be 8-128 chars (A-Z, 0-9, _ or -)."})

    ann = await db.station_announcements.find_one({"_id": ann_id})
    if not ann:
        raise HTTPException(404, {"code": "not_found",
                                    "message": "Announcement not found."})
    coupon = ann.get("coupon")
    if not coupon:
        raise HTTPException(404, {"code": "no_coupon",
                                    "message": "This announcement has no coupon attached."})
    if is_coupon_expired(coupon):
        raise HTTPException(410, {"code": "expired",
                                    "message": "Coupon has expired."})

    # Idempotency check first — if the device already has a redemption
    # for this announcement, return it immediately (no counter bump).
    existing = await db.user_coupons.find_one({
        "announcement_id":    ann_id,
        "device_fingerprint": device_fp,
    })
    if existing:
        out = {k: v for k, v in existing.items() if k != "_id"}
        out["redemption_id"] = existing.get("_id") or existing.get("redemption_id")
        out["already_redeemed"] = True
        return out

    # Cap check before atomic bump.
    if is_coupon_cap_reached(coupon):
        raise HTTPException(410, {
            "code": "redemption_cap_reached",
            "message": "All coupons have been claimed."})

    # Atomic increment, conditional on cap.
    max_red = coupon.get("max_redemptions")
    inc_query: dict = {"_id": ann_id}
    if max_red:
        inc_query["coupon.redemptions_count"] = {"$lt": int(max_red)}
    bump_result = await db.station_announcements.update_one(
        inc_query, {"$inc": {"coupon.redemptions_count": 1}})
    if bump_result.modified_count == 0:
        # The cap was JUST hit by another concurrent redeemer.
        raise HTTPException(410, {
            "code": "redemption_cap_reached",
            "message": "All coupons have been claimed."})

    # Resolve station context for nicer wallet rows.
    slug         = ann.get("station_slug") or ""
    station_name = ""
    try:
        st = await db.community_radio_stations.find_one(
            {"slug": slug},
            {"name": 1, "_id": 0})
        if st:
            station_name = st.get("name") or ""
    except Exception:
        pass

    red_id      = new_red_id()
    code        = coupon.get("code") or ""
    qr_payload  = new_qr_payload(ann_id, code, red_id)
    expires_at  = coupon.get("expires_at")
    expires_dt  = _parse_iso_to_dt(expires_at) if expires_at else None

    user_id = user.get("user_id") if user else None
    if body.get("user_id") and not user_id:
        # The caller may have offered a user_id without auth; we DO NOT
        # trust unauthenticated user_id claims for coupon attribution.
        user_id = None

    now_iso = _now_iso()
    doc = {
        "_id":                  red_id,
        "redemption_id":        red_id,
        "user_id":              user_id,
        "device_fingerprint":   device_fp,
        "announcement_id":      ann_id,
        "station_slug":         slug,
        "station_name":         station_name,
        "coupon_code":          code,
        "discount_pct":         coupon.get("discount_pct"),
        "discount_amount_cents": coupon.get("discount_amount_cents"),
        "terms":                coupon.get("terms"),
        "qr_payload":           qr_payload,
        "redeemed_at":          now_iso,
        # Store as native datetime so the TTL index on `expires_at`
        # actually fires when the coupon lapses.
        "expires_at":           expires_dt,
        "redemption_status":    "claimed",
    }
    try:
        await db.user_coupons.insert_one(doc)
    except Exception as e:
        # Unique-index race: another tab beat us.  Rollback the counter
        # we just bumped and re-fetch the existing row.
        try:
            await db.station_announcements.update_one(
                {"_id": ann_id},
                {"$inc": {"coupon.redemptions_count": -1}})
        except Exception:
            pass
        log.info("[coupons] dedupe race resolved by re-fetch: %s", e)
        existing = await db.user_coupons.find_one({
            "announcement_id":    ann_id,
            "device_fingerprint": device_fp,
        })
        if existing:
            out = {k: v for k, v in existing.items() if k != "_id"}
            out["redemption_id"] = existing.get("_id") or existing.get("redemption_id")
            out["already_redeemed"] = True
            return out
        raise HTTPException(500, {"code": "redemption_failed",
                                    "message": "Could not save redemption."})

    out = {k: v for k, v in doc.items() if k != "_id"}
    # Serialize expires_at back to ISO for JSON output.
    if expires_dt:
        out["expires_at"] = expires_dt.isoformat()
    out["already_redeemed"] = False
    return out


# ──────────────────────────────────────────────────────────────────
# Authed: list my coupons (with optional device fallback for anon merge)
# ──────────────────────────────────────────────────────────────────
@me_router.get("/coupons")
async def my_coupons(request: Request,
                      device_fingerprint: Optional[str] = Query(default=None),
                      limit: int = Query(default=50, ge=1, le=200),
                      user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    if not user and not device_fingerprint:
        raise HTTPException(401, {"code": "auth_required",
                                    "message": "Sign in or pass device_fingerprint."})

    or_clauses = []
    if user:
        or_clauses.append({"user_id": user.get("user_id")})
    if device_fingerprint:
        if not FP_RE.match(device_fingerprint):
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "device_fingerprint"})
        or_clauses.append({"device_fingerprint": device_fingerprint})

    q = {"$or": or_clauses} if len(or_clauses) > 1 else or_clauses[0]

    rows = []
    async for r in db.user_coupons.find(q).sort("redeemed_at", -1).limit(limit):
        # Serialize datetime expires_at back to ISO.
        exp = r.get("expires_at")
        if isinstance(exp, dict) or exp is None:
            exp_iso = None
        else:
            try:
                exp_iso = exp.isoformat() if hasattr(exp, "isoformat") else exp
            except Exception:
                exp_iso = None
        # Surface a `is_expired` flag for UI gating.
        is_expired = False
        if exp:
            try:
                if hasattr(exp, "tzinfo"):
                    is_expired = _now() >= (exp if exp.tzinfo else exp)
                else:
                    dt = _parse_iso_to_dt(exp)
                    is_expired = bool(dt and _now() >= dt)
            except Exception:
                is_expired = False
        rows.append({
            "redemption_id":         r.get("_id"),
            "user_id":               r.get("user_id"),
            "device_fingerprint":    r.get("device_fingerprint"),
            "announcement_id":       r.get("announcement_id"),
            "station_slug":          r.get("station_slug"),
            "station_name":          r.get("station_name"),
            "coupon_code":           r.get("coupon_code"),
            "discount_pct":          r.get("discount_pct"),
            "discount_amount_cents": r.get("discount_amount_cents"),
            "terms":                 r.get("terms"),
            "qr_payload":            r.get("qr_payload"),
            "redeemed_at":           r.get("redeemed_at"),
            "expires_at":            exp_iso,
            "is_expired":            is_expired,
            "redemption_status":     r.get("redemption_status") or "claimed",
        })
    return {"items": rows, "count": len(rows)}


__all__ = [
    "station_router",
    "public_router",
    "me_router",
    "ensure_coupon_indexes",
    "coupon_summary_public",
]
