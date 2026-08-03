"""Phase MER.3 — Gift Card SKU management + minting on purchase.

SKUs are merchant-defined templates (name, denominations, terms, expiry).
`user_gift_cards` are the actual instances issued when a customer buys
a `link_type=gift_card` payment link — minted from the SC.5 succeeded
handler via `wallet_v2_service.on_payment_succeeded_mer3`.

Codes are `BIGFM-GC-XXXXXX` (12 chars total after prefix), unique.
"""
from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("bigfm.mer3.giftcards")

_GC_CODE_ALPHABET = string.ascii_uppercase + "23456789"      # skip 0/O/1/I


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gc_code() -> str:
    """`BIGFM-GC-XXXXXX` (6 base32-ish suffix, ~30 bits)."""
    suffix = "".join(secrets.choice(_GC_CODE_ALPHABET) for _ in range(6))
    return f"BIGFM-GC-{suffix}"


# ─── SKU CRUD ────────────────────────────────────────────────────
async def create_sku(db, *, merchant_id: str, actor: dict, **fields) -> dict:
    name = (fields.get("name") or "").strip()
    if not name:
        raise ValueError("name_required")

    denoms = fields.get("denominations") or []
    if not isinstance(denoms, list):
        raise ValueError("denominations_must_be_list")
    denoms = [int(d) for d in denoms if int(d) > 0]
    custom_allowed = bool(fields.get("custom_amount_allowed"))
    if not denoms and not custom_allowed:
        raise ValueError("must_provide_denominations_or_allow_custom")

    sku_id = f"gcs_{uuid.uuid4().hex[:14]}"
    now = _now()
    doc = {
        "_id":                                sku_id,
        "sku_id":                        sku_id,
        "merchant_id":              merchant_id,
        "name":                            name,
        "description":              (fields.get("description") or "").strip() or None,
        "denominations":          sorted(set(denoms)),
        "custom_amount_allowed": custom_allowed,
        "min_custom_cents":      int(fields.get("min_custom_cents") or 0) or None,
        "max_custom_cents":      int(fields.get("max_custom_cents") or 0) or None,
        "currency":                    (fields.get("currency") or "AED").upper(),
        "terms":                          (fields.get("terms") or "").strip() or None,
        "expires_days_after_purchase": int(fields.get("expires_days_after_purchase") or 365),
        "active":                        True,
        "created_at":              now,
        "updated_at":              now,
        "created_by":              (actor or {}).get("user_id"),
    }
    await db.gift_card_skus.insert_one(doc)
    logger.info(f"[mer3.gc] SKU created sku={sku_id} mid={merchant_id} name={name!r}")
    return doc


async def update_sku(db, *, sku_id: str, merchant_id: str, patch: dict,
                                          actor: dict) -> dict:
    row = await db.gift_card_skus.find_one({"sku_id": sku_id})
    if not row or row.get("merchant_id") != merchant_id:
        raise ValueError("sku_not_found")

    allowed_fields = {"name", "description", "denominations",
                                      "custom_amount_allowed", "min_custom_cents",
                                      "max_custom_cents", "terms",
                                      "expires_days_after_purchase", "active"}
    filtered = {k: v for k, v in (patch or {}).items() if k in allowed_fields}
    if "denominations" in filtered:
        filtered["denominations"] = sorted(set(int(d) for d in filtered["denominations"]
                                                                          if int(d) > 0))
    filtered["updated_at"] = _now()
    await db.gift_card_skus.update_one({"sku_id": sku_id},
                                                                          {"$set": filtered})
    return await db.gift_card_skus.find_one({"sku_id": sku_id})


async def list_skus(db, *, merchant_id: str, active: Optional[bool] = None,
                                        limit: int = 100, offset: int = 0) -> dict:
    q = {"merchant_id": merchant_id}
    if active is not None:
        q["active"] = active
    total = await db.gift_card_skus.count_documents(q)
    rows = await db.gift_card_skus.find(q).sort("created_at", -1) \
                                    .skip(offset).limit(limit).to_list(length=limit)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


async def get_sku(db, *, sku_id: str, merchant_id: Optional[str] = None) -> Optional[dict]:
    q = {"sku_id": sku_id}
    if merchant_id:
        q["merchant_id"] = merchant_id
    return await db.gift_card_skus.find_one(q)


# ─── Minting on purchase ────────────────────────────────────────
async def mint_gift_card(db, *, sku_id: Optional[str], merchant_id: str,
                                              amount_cents: int,
                                              owner_user_id: Optional[str],
                                              owner_email: Optional[str],
                                              purchased_transaction_id: str) -> dict:
    """Called from the SC.5 succeeded handler when a `gift_card` link
    is bought.  Idempotent — a second call for the same transaction
    returns the existing card row."""
    if amount_cents <= 0:
        raise ValueError("invalid_amount")

    # Idempotency guard — one card per transaction
    existing = await db.user_gift_cards.find_one(
        {"purchased_transaction_id": purchased_transaction_id})
    if existing:
        return existing

    # Resolve expiry from SKU (or default 365 days)
    expires_days = 365
    if sku_id:
        sku = await db.gift_card_skus.find_one({"sku_id": sku_id})
        if sku:
            expires_days = int(sku.get("expires_days_after_purchase") or 365)

    # Retry code generation on collision
    code = _gc_code()
    for _ in range(6):
        if not await db.user_gift_cards.find_one({"code": code}):
            break
        code = _gc_code()

    now = _now()
    gc_id = f"gc_{uuid.uuid4().hex[:16]}"
    doc = {
        "_id":                                gc_id,
        "gift_card_id":              gc_id,
        "sku_id":                        sku_id,
        "merchant_id":              merchant_id,
        "owner_user_id":          owner_user_id,
        "owner_email":              (owner_email or "").lower() or None,
        "code":                            code,
        "initial_balance_cents": int(amount_cents),
        "current_balance_cents": int(amount_cents),
        "currency":                    "AED",         # source-of-truth from tx.currency in caller
        "expires_at":                now + timedelta(days=expires_days),
        "status":                        "active",
        "purchased_transaction_id": purchased_transaction_id,
        "created_at":                now,
        "last_used_at":            None,
    }
    await db.user_gift_cards.insert_one(doc)
    logger.info(f"[mer3.gc] MINTED code={code} amt={amount_cents} mid={merchant_id} "
                          f"tx={purchased_transaction_id} owner={owner_email}")
    return doc


async def lookup_by_code(db, *, code: str) -> Optional[dict]:
    up = code.strip().upper()
    return await db.user_gift_cards.find_one({"code": up})


async def apply_at_checkout(db, *, code: str, merchant_id: str,
                                                order_amount_cents: int) -> dict:
    """Compute how much this gift card would reduce the order.  Does
    NOT decrement the balance — that happens on succeeded webhook."""
    gc = await lookup_by_code(db, code=code)
    if not gc:
        return {"ok": False, "reason": "not_found"}
    if gc.get("merchant_id") != merchant_id:
        return {"ok": False, "reason": "not_this_merchant"}
    if gc.get("status") != "active":
        return {"ok": False, "reason": gc.get("status")}
    expires = gc.get("expires_at")
    if expires and _coerce_utc(expires) < _now():
        return {"ok": False, "reason": "expired"}
    balance = int(gc.get("current_balance_cents") or 0)
    if balance <= 0:
        return {"ok": False, "reason": "depleted"}
    reduction = min(balance, int(order_amount_cents))
    return {"ok": True,
                  "gift_card_id":                gc["gift_card_id"],
                  "code":                                gc["code"],
                  "current_balance_cents":  balance,
                  "amount_reduced_cents":  reduction}


async def decrement_balance(db, *, gift_card_id: str,
                                                        amount_cents: int) -> dict:
    """Atomically decrement — used both by cashier redeem and by the
    modifier-applied-on-checkout hook."""
    if amount_cents <= 0:
        raise ValueError("invalid_amount")

    now = _now()
    result = await db.user_gift_cards.find_one_and_update(
        {"gift_card_id": gift_card_id,
          "status": "active",
          "current_balance_cents": {"$gte": amount_cents}},
        {"$inc": {"current_balance_cents": -amount_cents},
          "$set": {"last_used_at": now}},
        return_document=True,        # motor default is `BEFORE` which is unsafe here
    )
    if not result:
        # Reload to figure out why
        gc = await db.user_gift_cards.find_one({"gift_card_id": gift_card_id})
        if not gc:
            raise ValueError("not_found")
        if gc.get("status") != "active":
            raise ValueError(f"invalid_status:{gc.get('status')}")
        raise ValueError("insufficient_balance")

    # Reload to get the up-to-date balance for `depleted` flip check
    gc = await db.user_gift_cards.find_one({"gift_card_id": gift_card_id})
    if gc and int(gc.get("current_balance_cents") or 0) <= 0:
        await db.user_gift_cards.update_one(
            {"gift_card_id": gift_card_id},
            {"$set": {"status": "depleted", "depleted_at": now}})
        gc["status"] = "depleted"
    return gc


def _coerce_utc(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_gift_card_indexes(db) -> None:
    await db.gift_card_skus.create_index([("merchant_id", 1), ("active", 1)])
    await db.gift_card_skus.create_index("sku_id", unique=True)
    await db.user_gift_cards.create_index("code", unique=True)
    await db.user_gift_cards.create_index([("merchant_id", 1), ("status", 1)])
    await db.user_gift_cards.create_index([("owner_user_id", 1), ("created_at", -1)])
    await db.user_gift_cards.create_index("purchased_transaction_id", unique=True,
                                                                                sparse=True)


__all__ = [
    "create_sku", "update_sku", "list_skus", "get_sku",
    "mint_gift_card", "lookup_by_code",
    "apply_at_checkout", "decrement_balance",
    "ensure_gift_card_indexes",
]
