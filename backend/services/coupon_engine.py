"""Phase 41 Session 4.5.A — Announcement Coupon engine.

Coupons live as an optional sub-document on `station_announcements`.

  station_announcements.coupon = {
      "code":                str,    # owner-defined or auto-generated
      "discount_pct":        int?,   # XOR with discount_amount_cents
      "discount_amount_cents": int?,
      "max_redemptions":     int?,   # null → unlimited
      "redemptions_count":   int,    # atomic counter
      "expires_at":          iso?,   # null → no expiry
      "terms":               str?,   # short legal text
  }

Redemptions live in their own collection so we can:
  - enforce one-per-device idempotently via unique compound index
  - cleanly support anonymous (device_fingerprint only) redemptions
  - TTL expire on `expires_at` (best-effort housekeeping)

  user_coupons = {
      "_id":                 str (red_id),
      "user_id":             str | null,
      "device_fingerprint":  str,
      "announcement_id":     str,
      "station_slug":        str,
      "station_name":        str,
      "coupon_code":         str,
      "discount_pct":        int | null,
      "discount_amount_cents": int | null,
      "terms":               str | null,
      "qr_payload":          str,           # opaque token shown in QR
      "redeemed_at":         iso,           # claimed_at, really
      "expires_at":          datetime|None, # TTL-friendly datetime
      "redemption_status":   "claimed"|"used"|"expired",
  }
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

log = logging.getLogger("bigfm.coupon_engine")

CODE_RE   = re.compile(r"^[A-Z0-9][A-Z0-9_\-]{2,23}$")
FP_RE     = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")
TERMS_MAX = 240


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str:  return _now().isoformat()


def _parse_iso_to_dt(v) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _gen_code() -> str:
    return f"BIGFM{secrets.token_hex(3).upper()}"


def validate_coupon_input(body: dict) -> dict:
    """Validate + normalize a coupon body coming from the owner.
    Returns a dict ready to embed under announcement.coupon (with a
    `redemptions_count=0` initialized when called for first-time create
    — the caller decides whether to overwrite or preserve that on update).
    """
    if body is None:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "Coupon body required."})

    code = (body.get("code") or "").strip().upper()
    if code:
        if not CODE_RE.match(code):
            raise HTTPException(400, {
                "code": "validation_error",
                "field": "code",
                "message": "Code must be 3-24 chars (A-Z, 0-9, _ or -)."})
    else:
        code = _gen_code()

    discount_pct          = body.get("discount_pct")
    discount_amount_cents = body.get("discount_amount_cents")
    if discount_pct is not None:
        try:
            discount_pct = int(discount_pct)
        except Exception:
            raise HTTPException(400, {"code": "validation_error",
                                       "field": "discount_pct"})
        if not (1 <= discount_pct <= 100):
            raise HTTPException(400, {
                "code": "validation_error", "field": "discount_pct",
                "message": "discount_pct must be 1-100."})
    if discount_amount_cents is not None:
        try:
            discount_amount_cents = int(discount_amount_cents)
        except Exception:
            raise HTTPException(400, {"code": "validation_error",
                                       "field": "discount_amount_cents"})
        if discount_amount_cents <= 0 or discount_amount_cents > 1_000_000:
            raise HTTPException(400, {
                "code": "validation_error", "field": "discount_amount_cents",
                "message": "Amount must be 1-1,000,000 cents."})
    if discount_pct is None and discount_amount_cents is None:
        raise HTTPException(400, {
            "code": "validation_error",
            "message": "Provide discount_pct OR discount_amount_cents."})
    if discount_pct is not None and discount_amount_cents is not None:
        raise HTTPException(400, {
            "code": "validation_error",
            "message": "Provide ONE of discount_pct or discount_amount_cents, not both."})

    max_redemptions = body.get("max_redemptions")
    if max_redemptions is not None and max_redemptions != "":
        try:
            max_redemptions = int(max_redemptions)
        except Exception:
            raise HTTPException(400, {"code": "validation_error",
                                       "field": "max_redemptions"})
        if max_redemptions < 1 or max_redemptions > 1_000_000:
            raise HTTPException(400, {
                "code": "validation_error", "field": "max_redemptions",
                "message": "max_redemptions must be 1-1,000,000."})
    else:
        max_redemptions = None

    expires_at_raw = body.get("expires_at")
    expires_at_dt  = _parse_iso_to_dt(expires_at_raw) if expires_at_raw else None
    if expires_at_raw and expires_at_dt is None:
        raise HTTPException(400, {
            "code": "validation_error", "field": "expires_at",
            "message": "expires_at must be ISO-8601."})

    terms = (body.get("terms") or "").strip() or None
    if terms and len(terms) > TERMS_MAX:
        raise HTTPException(400, {
            "code": "validation_error", "field": "terms",
            "max_chars": TERMS_MAX})

    return {
        "code":                  code,
        "discount_pct":          discount_pct,
        "discount_amount_cents": discount_amount_cents,
        "max_redemptions":       max_redemptions,
        "expires_at":            expires_at_dt.isoformat() if expires_at_dt else None,
        "terms":                 terms,
    }


def coupon_summary_public(coupon: dict) -> dict:
    """Public-facing projection of a coupon (TV display / station feed).
    Hides `redemptions_count` if it's unbounded; reveals scarcity counter
    when max_redemptions is set."""
    if not coupon:
        return None
    out = {
        "code":                  coupon.get("code"),
        "discount_pct":          coupon.get("discount_pct"),
        "discount_amount_cents": coupon.get("discount_amount_cents"),
        "expires_at":            coupon.get("expires_at"),
        "terms":                 coupon.get("terms"),
    }
    mx = coupon.get("max_redemptions")
    if mx:
        used = int(coupon.get("redemptions_count") or 0)
        out["max_redemptions"]    = int(mx)
        out["redemptions_count"]  = used
        out["remaining"]          = max(0, int(mx) - used)
    return out


def is_coupon_expired(coupon: dict) -> bool:
    exp = coupon.get("expires_at") if isinstance(coupon, dict) else None
    dt = _parse_iso_to_dt(exp)
    if not dt:
        return False
    return _now() >= dt


def is_coupon_cap_reached(coupon: dict) -> bool:
    mx = coupon.get("max_redemptions") if isinstance(coupon, dict) else None
    if not mx:
        return False
    return int(coupon.get("redemptions_count") or 0) >= int(mx)


async def ensure_coupon_indexes(db) -> dict:
    """Idempotent. Called on startup."""
    created = []
    # one-per-device idempotency for redemptions
    try:
        await db.user_coupons.create_index(
            [("announcement_id", 1), ("device_fingerprint", 1)],
            unique=True,
            name="user_coupons_dedupe_unique")
        created.append("user_coupons_dedupe_unique")
    except Exception as e:
        log.warning("[coupons] dedupe index create failed: %s", e)
    # user lookup index
    try:
        await db.user_coupons.create_index(
            [("user_id", 1), ("redeemed_at", -1)],
            name="user_coupons_user_recent")
        created.append("user_coupons_user_recent")
    except Exception as e:
        log.warning("[coupons] user index create failed: %s", e)
    # device lookup index for anonymous listing
    try:
        await db.user_coupons.create_index(
            [("device_fingerprint", 1), ("redeemed_at", -1)],
            name="user_coupons_device_recent")
        created.append("user_coupons_device_recent")
    except Exception as e:
        log.warning("[coupons] device index create failed: %s", e)
    # TTL on expires_at (best-effort; documents with null are ignored)
    try:
        await db.user_coupons.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
            name="user_coupons_ttl",
            sparse=True)
        created.append("user_coupons_ttl")
    except Exception as e:
        log.warning("[coupons] ttl index create failed: %s", e)
    return {"created": created}


def new_red_id() -> str:
    return f"rd_{uuid.uuid4().hex[:14]}"


def new_qr_payload(announcement_id: str, code: str, red_id: str) -> str:
    """Opaque token for the QR code printed on the user's wallet item.
    The redeeming venue can scan this to verify against the user's wallet.
    """
    return f"bigfm:c:{announcement_id}:{code}:{red_id}"
