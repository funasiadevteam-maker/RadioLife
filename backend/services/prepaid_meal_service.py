"""Phase MER.3 — Prepaid Meal SKU management + minting on purchase.

Merchants sell N-meal packs (e.g. "5 lunches for AED 100 · save 20%").
When purchased via `link_type=prepaid_meal`, a `user_prepaid_meals`
row is minted from the SC.5 succeeded handler.  Each cashier scan
decrements `remaining_meals` by 1.

Codes are `BIGFM-PM-XXXXXX` (12 chars total after prefix), unique.
"""
from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("bigfm.mer3.prepaid_meals")

_PM_CODE_ALPHABET = string.ascii_uppercase + "23456789"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pm_code() -> str:
    suffix = "".join(secrets.choice(_PM_CODE_ALPHABET) for _ in range(6))
    return f"BIGFM-PM-{suffix}"


def _coerce_utc(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ─── SKU CRUD ────────────────────────────────────────────────────
async def create_sku(db, *, merchant_id: str, actor: dict, **fields) -> dict:
    name = (fields.get("name") or "").strip()
    if not name:
        raise ValueError("name_required")
    meal_count = int(fields.get("meal_count") or 0)
    total_price_cents = int(fields.get("total_price_cents") or 0)
    if meal_count < 2:
        raise ValueError("meal_count_must_be_at_least_2")
    if total_price_cents <= 0:
        raise ValueError("total_price_required")

    sku_id = f"pms_{uuid.uuid4().hex[:14]}"
    now = _now()
    per_meal = total_price_cents // meal_count if meal_count else 0
    doc = {
        "_id":                                sku_id,
        "sku_id":                        sku_id,
        "merchant_id":              merchant_id,
        "name":                            name,
        "description":              (fields.get("description") or "").strip() or None,
        "meal_count":                meal_count,
        "total_price_cents":  total_price_cents,
        "per_meal_value_cents": per_meal,
        "currency":                    (fields.get("currency") or "AED").upper(),
        "terms":                          (fields.get("terms") or "").strip() or None,
        "expires_days":            int(fields.get("expires_days") or 90),
        "active":                        True,
        "created_at":              now,
        "updated_at":              now,
        "created_by":              (actor or {}).get("user_id"),
    }
    await db.prepaid_meal_skus.insert_one(doc)
    logger.info(f"[mer3.pm] SKU created sku={sku_id} mid={merchant_id} "
                          f"meals={meal_count} price={total_price_cents}")
    return doc


async def update_sku(db, *, sku_id: str, merchant_id: str, patch: dict,
                                          actor: dict) -> dict:
    row = await db.prepaid_meal_skus.find_one({"sku_id": sku_id})
    if not row or row.get("merchant_id") != merchant_id:
        raise ValueError("sku_not_found")

    allowed = {"name", "description", "meal_count", "total_price_cents",
                        "terms", "expires_days", "active"}
    filtered = {k: v for k, v in (patch or {}).items() if k in allowed}
    if "meal_count" in filtered or "total_price_cents" in filtered:
        mc = int(filtered.get("meal_count") or row.get("meal_count") or 1)
        tp = int(filtered.get("total_price_cents") or row.get("total_price_cents") or 0)
        filtered["per_meal_value_cents"] = tp // mc if mc else 0
    filtered["updated_at"] = _now()
    await db.prepaid_meal_skus.update_one({"sku_id": sku_id},
                                                                                {"$set": filtered})
    return await db.prepaid_meal_skus.find_one({"sku_id": sku_id})


async def list_skus(db, *, merchant_id: str, active: Optional[bool] = None,
                                        limit: int = 100, offset: int = 0) -> dict:
    q = {"merchant_id": merchant_id}
    if active is not None:
        q["active"] = active
    total = await db.prepaid_meal_skus.count_documents(q)
    rows = await db.prepaid_meal_skus.find(q).sort("created_at", -1) \
                                    .skip(offset).limit(limit).to_list(length=limit)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


async def get_sku(db, *, sku_id: str, merchant_id: Optional[str] = None) -> Optional[dict]:
    q = {"sku_id": sku_id}
    if merchant_id:
        q["merchant_id"] = merchant_id
    return await db.prepaid_meal_skus.find_one(q)


# ─── Minting on purchase ────────────────────────────────────────
async def mint_prepaid_meal(db, *, sku_id: str, merchant_id: str,
                                                    owner_user_id: Optional[str],
                                                    owner_email: Optional[str],
                                                    purchased_transaction_id: str) -> dict:
    """Called from the SC.5 succeeded handler when a `prepaid_meal`
    link is bought.  Idempotent — returns existing row on duplicate call."""
    existing = await db.user_prepaid_meals.find_one(
        {"purchased_transaction_id": purchased_transaction_id})
    if existing:
        return existing

    sku = await db.prepaid_meal_skus.find_one({"sku_id": sku_id})
    if not sku:
        raise ValueError(f"sku_not_found:{sku_id}")

    now = _now()
    expires_days = int(sku.get("expires_days") or 90)
    total_meals = int(sku.get("meal_count") or 0)
    if total_meals < 1:
        raise ValueError("invalid_sku_meal_count")

    code = _pm_code()
    for _ in range(6):
        if not await db.user_prepaid_meals.find_one({"code": code}):
            break
        code = _pm_code()

    pack_id = f"pm_{uuid.uuid4().hex[:16]}"
    doc = {
        "_id":                                pack_id,
        "meal_pack_id":              pack_id,
        "sku_id":                        sku_id,
        "merchant_id":              merchant_id,
        "owner_user_id":          owner_user_id,
        "owner_email":              (owner_email or "").lower() or None,
        "code":                            code,
        "total_meals":              total_meals,
        "remaining_meals":      total_meals,
        "per_meal_value_cents": int(sku.get("per_meal_value_cents") or 0),
        "expires_at":                now + timedelta(days=expires_days),
        "status":                        "active",
        "purchased_transaction_id": purchased_transaction_id,
        "created_at":                now,
        "last_used_at":            None,
    }
    await db.user_prepaid_meals.insert_one(doc)
    logger.info(f"[mer3.pm] MINTED code={code} meals={total_meals} mid={merchant_id} "
                          f"tx={purchased_transaction_id}")
    return doc


async def lookup_by_code(db, *, code: str) -> Optional[dict]:
    up = code.strip().upper()
    return await db.user_prepaid_meals.find_one({"code": up})


async def apply_at_checkout(db, *, code: str, merchant_id: str) -> dict:
    """Compute meal-redemption preview.  Does NOT decrement — that fires
    on succeeded webhook."""
    pm = await lookup_by_code(db, code=code)
    if not pm:
        return {"ok": False, "reason": "not_found"}
    if pm.get("merchant_id") != merchant_id:
        return {"ok": False, "reason": "not_this_merchant"}
    if pm.get("status") != "active":
        return {"ok": False, "reason": pm.get("status")}
    if _coerce_utc(pm.get("expires_at")) and _coerce_utc(pm["expires_at"]) < _now():
        return {"ok": False, "reason": "expired"}
    remaining = int(pm.get("remaining_meals") or 0)
    if remaining <= 0:
        return {"ok": False, "reason": "depleted"}
    return {"ok": True,
                  "meal_pack_id":              pm["meal_pack_id"],
                  "code":                              pm["code"],
                  "remaining_meals":      remaining,
                  "per_meal_value_cents": int(pm.get("per_meal_value_cents") or 0),
                  "amount_reduced_cents": int(pm.get("per_meal_value_cents") or 0)}


async def decrement_meal(db, *, meal_pack_id: str, count: int = 1) -> dict:
    """Atomically decrement remaining_meals by `count`.  Flips status
    to `depleted` when remaining hits 0."""
    if count <= 0:
        raise ValueError("invalid_count")
    now = _now()
    result = await db.user_prepaid_meals.find_one_and_update(
        {"meal_pack_id": meal_pack_id,
          "status": "active",
          "remaining_meals": {"$gte": count}},
        {"$inc": {"remaining_meals": -count},
          "$set": {"last_used_at": now}},
        return_document=True,
    )
    if not result:
        pm = await db.user_prepaid_meals.find_one({"meal_pack_id": meal_pack_id})
        if not pm:
            raise ValueError("not_found")
        if pm.get("status") != "active":
            raise ValueError(f"invalid_status:{pm.get('status')}")
        raise ValueError("insufficient_meals")

    pm = await db.user_prepaid_meals.find_one({"meal_pack_id": meal_pack_id})
    if pm and int(pm.get("remaining_meals") or 0) <= 0:
        await db.user_prepaid_meals.update_one(
            {"meal_pack_id": meal_pack_id},
            {"$set": {"status": "depleted", "depleted_at": now}})
        pm["status"] = "depleted"
    return pm


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_prepaid_meal_indexes(db) -> None:
    await db.prepaid_meal_skus.create_index([("merchant_id", 1), ("active", 1)])
    await db.prepaid_meal_skus.create_index("sku_id", unique=True)
    await db.user_prepaid_meals.create_index("code", unique=True)
    await db.user_prepaid_meals.create_index([("merchant_id", 1), ("status", 1)])
    await db.user_prepaid_meals.create_index([("owner_user_id", 1), ("created_at", -1)])
    await db.user_prepaid_meals.create_index("purchased_transaction_id", unique=True,
                                                                                    sparse=True)


__all__ = [
    "create_sku", "update_sku", "list_skus", "get_sku",
    "mint_prepaid_meal", "lookup_by_code",
    "apply_at_checkout", "decrement_meal",
    "ensure_prepaid_meal_indexes",
]
