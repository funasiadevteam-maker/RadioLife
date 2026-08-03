"""Phase SC.4 — Merchant Payment Links + QR Codes.

Creation, retrieval, deactivation, and impression tracking for
merchant-owned persistent payment URLs.  Actual charging comes in
SC.5 — for now the `/pay/{token}` frontend page just shows a
"Payment coming in SC.5" preview.

Public functions:
    create_payment_link(db, *, merchant_id, link_type, actor, **fields)
    get_link_by_token(db, token)                    → (link, merchant) or (None, None)
    deactivate_link(db, link_id, actor_user_id)
    record_link_impression(db, link, viewer_ip, headers)
    generate_qr_png(link_token, size=512)      → bytes (in-memory PNG)
    hosted_url_for(token) / qr_url_for(token)
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

import qrcode
from qrcode.constants import ERROR_CORRECT_M

logger = logging.getLogger("bigfm.payment_links")

# ─── URL helpers ─────────────────────────────────────────────────
def _frontend_base() -> str:
    url = (os.environ.get("FRONTEND_URL")
              or os.environ.get("FRONTEND_BASE_URL")
              or os.environ.get("PUBLIC_BACKEND_URL")
              or "https://mobile-games-v2.preview.emergentagent.com")
    return url.rstrip("/")


def _backend_base() -> str:
    url = (os.environ.get("PUBLIC_BACKEND_URL")
              or os.environ.get("FRONTEND_URL")
              or "https://mobile-games-v2.preview.emergentagent.com")
    return url.rstrip("/")


def hosted_url_for(token: str) -> str:
    return f"{_frontend_base()}/pay/{token}"


def qr_url_for(token: str) -> str:
    return f"{_backend_base()}/api/pay/qr/{token}.png"


# ─── Constants ───────────────────────────────────────────────────
VALID_LINK_TYPES = {
    "general_payment", "location_payment", "table_qr", "offer_payment",
    "prepaid_meal", "gift_card", "product_checkout", "event_ticket",
    "appointment_deposit", "campaign_payment",
}

# Default transaction_type per link_type when merchant doesn't override
_DEFAULT_TXN_FOR_LINK_TYPE = {
    "general_payment":        "payment",
    "location_payment":      "payment",
    "table_qr":                    "payment",
    "offer_payment":            "paid_coupon",
    "prepaid_meal":              "prepaid_meal",
    "gift_card":                    "gift_card",
    "product_checkout":      "payment",
    "event_ticket":              "event_ticket",
    "appointment_deposit": "appointment_deposit",
    "campaign_payment":      "payment",
}

# base62 alphabet — the token is short + URL-safe + QR-friendly
_B62 = string.ascii_letters + string.digits


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_token() -> str:
    """12-char base62 token via `secrets`.  ~71 bits of entropy — plenty
    for the collision-resistance requirement."""
    return "".join(secrets.choice(_B62) for _ in range(12))


def _ip_hash(ip: Optional[str]) -> str:
    salt = os.environ.get("PAYMENT_LINK_IP_SALT", "bigfm.sc4.default_salt")
    return hashlib.sha256(f"{salt}|{ip or ''}".encode("utf-8")).hexdigest()[:32]


def default_txn_type(link_type: str) -> str:
    return _DEFAULT_TXN_FOR_LINK_TYPE.get(link_type, "payment")


# ─── Merchant status guard ───────────────────────────────────────
async def is_merchant_approved(db, merchant_id: str) -> tuple[bool, Optional[dict]]:
    biz = await db.businesses.find_one({"$or": [
        {"business_id": merchant_id}, {"_id": merchant_id}]})
    if not biz:
        return False, None
    status = biz.get("merchant_status")
    return (status in ("approved", "active")), biz


# ─── CRUD ────────────────────────────────────────────────────────
async def create_payment_link(db, *, merchant_id: str, link_type: str,
                                                          actor: dict, **fields) -> dict:
    if link_type not in VALID_LINK_TYPES:
        raise ValueError(f"invalid_link_type:{link_type}")

    approved, biz = await is_merchant_approved(db, merchant_id)
    if not biz:
        raise ValueError("merchant_not_found")
    if not approved:
        raise ValueError(f"merchant_not_approved:{biz.get('merchant_status')}")

    # Ensure token uniqueness — retry on collision (~vanishingly rare)
    token = _gen_token()
    for _ in range(6):
        if not await db.merchant_payment_links.find_one({"token": token}):
            break
        token = _gen_token()

    lid = f"pl_{uuid.uuid4().hex[:14]}"
    now = _now()
    doc = {
        "_id":                        lid,
        "link_id":                lid,
        "token":                    token,
        "merchant_id":        merchant_id,
        "location_id":        fields.get("location_id"),
        "link_type":            link_type,
        "title":                    (fields.get("title") or "").strip() or None,
        "description":        (fields.get("description") or "").strip() or None,
        "amount_cents":      fields.get("amount_cents"),
        "currency":                (fields.get("currency") or "AED").upper(),
        "transaction_type":  fields.get("transaction_type") or default_txn_type(link_type),
        "min_amount_cents":  fields.get("min_amount_cents"),
        "max_amount_cents":  fields.get("max_amount_cents"),
        "table_number":        fields.get("table_number"),
        "offer_id":                fields.get("offer_id"),
        "product_id":            fields.get("product_id"),
        "event_id":                fields.get("event_id"),
        "service_id":            fields.get("service_id"),
        "campaign_id":        fields.get("campaign_id"),
        "gift_card_id":        fields.get("gift_card_id"),
        "prepaid_meal_id":  fields.get("prepaid_meal_id"),
        "expires_at":            fields.get("expires_at"),
        "max_uses":                fields.get("max_uses"),
        "usage_count":        0,
        "impressions":        0,
        "last_impression_at": None,
        "active":                    True,
        "qr_style":                (fields.get("qr_style") or "default"),
        "created_at":            now,
        "updated_at":            now,
        "created_by":            (actor or {}).get("user_id"),
    }
    await db.merchant_payment_links.insert_one(doc)
    logger.info(f"[payment_links] created lid={lid} token={token} mid={merchant_id} "
                          f"type={link_type} amt={doc['amount_cents']}")
    return doc


async def update_payment_link(db, *, link_id: str, merchant_id: str,
                                                          patch: dict, actor: dict) -> dict:
    existing = await db.merchant_payment_links.find_one({"link_id": link_id})
    if not existing:
        raise ValueError("link_not_found")
    if existing["merchant_id"] != merchant_id:
        raise ValueError("not_link_owner")

    # Fields the merchant is allowed to update — token/link_type/merchant_id
    # are immutable per SC.4 constraint.
    ALLOWED = {"title", "description", "amount_cents", "currency",
                        "min_amount_cents", "max_amount_cents", "table_number",
                        "expires_at", "max_uses", "active", "location_id",
                        "transaction_type"}
    updates = {k: v for k, v in patch.items() if k in ALLOWED}
    if not updates:
        return existing
    updates["updated_at"] = _now()
    await db.merchant_payment_links.update_one(
        {"link_id": link_id}, {"$set": updates})
    fresh = await db.merchant_payment_links.find_one({"link_id": link_id})
    logger.info(f"[payment_links] updated lid={link_id} fields={list(updates.keys())} "
                          f"by={(actor or {}).get('user_id')}")
    return fresh


async def deactivate_link(db, *, link_id: str, merchant_id: str,
                                              actor: dict) -> dict:
    existing = await db.merchant_payment_links.find_one({"link_id": link_id})
    if not existing:
        raise ValueError("link_not_found")
    if existing["merchant_id"] != merchant_id:
        raise ValueError("not_link_owner")
    await db.merchant_payment_links.update_one(
        {"link_id": link_id},
        {"$set": {"active": False, "deactivated_at": _now(),
                        "deactivated_by": (actor or {}).get("user_id"),
                        "updated_at": _now()}})
    fresh = await db.merchant_payment_links.find_one({"link_id": link_id})
    return fresh


# ─── Public token resolution ─────────────────────────────────────
async def get_link_by_token(db, token: str) -> tuple[Optional[dict], Optional[dict]]:
    link = await db.merchant_payment_links.find_one({"token": token})
    if not link:
        return None, None
    biz = await db.businesses.find_one({"$or": [
        {"business_id": link["merchant_id"]},
        {"_id": link["merchant_id"]},
    ]})
    return link, biz


def is_link_serving(link: dict) -> tuple[bool, Optional[str]]:
    """Return (ok, reason_if_not).  Reason values mirror the frontend
    "no longer active" states."""
    if not link:
        return False, "not_found"
    if not link.get("active"):
        return False, "deactivated"
    exp = link.get("expires_at")
    if exp:
        if isinstance(exp, datetime):
            e = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
            if e < _now():
                return False, "expired"
    mu = link.get("max_uses")
    if mu is not None and link.get("usage_count", 0) >= int(mu):
        return False, "max_uses_reached"
    return True, None


# ─── Impressions ─────────────────────────────────────────────────
async def record_link_impression(db, *, link: dict, viewer_ip: Optional[str],
                                                                headers: Optional[dict] = None) -> None:
    """Fire-and-forget.  Insert a small doc + bump the link's aggregate
    counters."""
    try:
        headers = headers or {}
        ua = (headers.get("user-agent") or headers.get("User-Agent") or "")[:200]
        ref = (headers.get("referer") or headers.get("Referer") or "")[:200]
        # Extract UA family for cheap analytics (no expensive parser)
        ua_family = "other"
        ua_low = ua.lower()
        if "iphone" in ua_low or "ipad" in ua_low: ua_family = "ios"
        elif "android" in ua_low: ua_family = "android"
        elif "windows" in ua_low: ua_family = "windows"
        elif "mac os" in ua_low: ua_family = "macos"
        elif "linux" in ua_low: ua_family = "linux"

        now = _now()
        await db.payment_link_impressions.insert_one({
            "_id":                        f"pli_{uuid.uuid4().hex[:16]}",
            "link_id":                link["link_id"],
            "merchant_id":        link.get("merchant_id"),
            "token":                    link["token"],
            "viewer_ip_hash":  _ip_hash(viewer_ip),
            "referer":                ref or None,
            "ua_family":            ua_family,
            "ua_raw":                  ua[:120] or None,
            "viewed_at":            now,
        })
        await db.merchant_payment_links.update_one(
            {"link_id": link["link_id"]},
            {"$inc": {"impressions": 1},
              "$set": {"last_impression_at": now}})
    except Exception:
        logger.exception("[payment_links] impression insert failed (non-blocking)")


# ─── Analytics ───────────────────────────────────────────────────
async def link_analytics(db, *, link: dict) -> dict:
    total = link.get("impressions") or 0
    unique = len(await db.payment_link_impressions.distinct(
        "viewer_ip_hash", {"link_id": link["link_id"]}))
    # Placeholder — SC.5 will start populating a payments/transactions
    # collection.  For now these are zero.
    return {
        "link_id":              link["link_id"],
        "impressions":      int(total),
        "unique_visitors": int(unique),
        "transactions":    0,
        "revenue_cents":    0,
        "avg_amount_cents": 0,
        "last_impression_at": link.get("last_impression_at").isoformat()
                                            if hasattr(link.get("last_impression_at"), "isoformat")
                                            else link.get("last_impression_at"),
    }


# ─── QR code generation ─────────────────────────────────────────
def generate_qr_png(token: str, *, size: int = 512) -> bytes:
    """Return PNG bytes for a QR encoding the hosted URL.  Uses standard
    ERROR_CORRECT_M + quiet-zone padding (border=4)."""
    url = hosted_url_for(token)
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    # Resize to requested size with nearest-neighbour so modules stay sharp
    img = img.resize((int(size), int(size)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_payment_link_indexes(db) -> None:
    await db.merchant_payment_links.create_index("link_id", unique=True)
    await db.merchant_payment_links.create_index("token", unique=True)
    await db.merchant_payment_links.create_index([
        ("merchant_id", 1), ("active", 1), ("created_at", -1)])
    await db.merchant_payment_links.create_index([("link_type", 1), ("active", 1)])
    await db.payment_link_impressions.create_index([
        ("link_id", 1), ("viewed_at", -1)])
    await db.payment_link_impressions.create_index([("viewed_at", -1)])


__all__ = [
    "VALID_LINK_TYPES", "default_txn_type",
    "create_payment_link", "update_payment_link", "deactivate_link",
    "get_link_by_token", "is_link_serving",
    "record_link_impression", "link_analytics",
    "generate_qr_png", "hosted_url_for", "qr_url_for",
    "ensure_payment_link_indexes", "is_merchant_approved",
]
