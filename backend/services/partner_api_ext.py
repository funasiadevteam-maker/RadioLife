"""Partner API v1 — Phase B write-safety helpers.

Adds three cross-cutting capabilities to the programmatic API without touching
the underlying ad/game engines:

  • Idempotency-Key      — safe retries: same (partner, env, endpoint, key)
                            returns the original response instead of creating a
                            duplicate.
  • external_id de-dup   — an externally-created object carries a partner-owned
                            id; (partner, env, resource_type, external_id) is
                            unique, so re-sending returns the existing object.
  • cursor pagination    — opaque base64 offset cursors for list endpoints.

Everything is stored under the partner's environment so SANDBOX and LIVE never
collide.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.partner_api import Caller

IDEMPOTENCY_TTL_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_ext_indexes(db) -> None:
    await db.partner_idempotency_keys.create_index(
        [("partner_id", 1), ("environment", 1), ("endpoint", 1), ("key", 1)],
        unique=True, name="partner_idem_unique")
    await db.partner_idempotency_keys.create_index(
        "expires_at", expireAfterSeconds=0, name="partner_idem_ttl")
    await db.partner_external_mappings.create_index(
        [("partner_id", 1), ("environment", 1), ("resource_type", 1), ("external_id", 1)],
        unique=True, name="partner_extid_unique")
    await db.api_quotes.create_index("expires_at", expireAfterSeconds=0, name="api_quotes_ttl")


# ── idempotency ─────────────────────────────────────────────────────
async def idem_get(db, caller: Caller, endpoint: str, key: Optional[str]) -> Optional[dict]:
    if not key:
        return None
    doc = await db.partner_idempotency_keys.find_one({
        "partner_id": caller.partner_id, "environment": caller.environment,
        "endpoint": endpoint, "key": key})
    return doc.get("response") if doc else None


async def idem_save(db, caller: Caller, endpoint: str, key: Optional[str],
                    response: dict) -> None:
    if not key:
        return
    now = _now()
    try:
        await db.partner_idempotency_keys.update_one(
            {"partner_id": caller.partner_id, "environment": caller.environment,
             "endpoint": endpoint, "key": key},
            {"$setOnInsert": {"response": response, "created_at": now,
                              "expires_at": now + timedelta(days=IDEMPOTENCY_TTL_DAYS)}},
            upsert=True)
    except Exception:
        pass


# ── external_id de-dup ──────────────────────────────────────────────
async def external_get(db, caller: Caller, resource_type: str,
                       external_id: Optional[str]) -> Optional[dict]:
    if not external_id:
        return None
    doc = await db.partner_external_mappings.find_one({
        "partner_id": caller.partner_id, "environment": caller.environment,
        "resource_type": resource_type, "external_id": external_id})
    return doc.get("response") if doc else None


async def external_save(db, caller: Caller, resource_type: str,
                        external_id: Optional[str], internal_id: str,
                        response: dict) -> None:
    if not external_id:
        return
    try:
        await db.partner_external_mappings.update_one(
            {"partner_id": caller.partner_id, "environment": caller.environment,
             "resource_type": resource_type, "external_id": external_id},
            {"$setOnInsert": {"internal_id": internal_id, "response": response,
                              "created_at": _now()}},
            upsert=True)
    except Exception:
        pass


async def external_lookup_id(db, caller: Caller, resource_type: str,
                             external_id: str) -> Optional[str]:
    doc = await db.partner_external_mappings.find_one({
        "partner_id": caller.partner_id, "environment": caller.environment,
        "resource_type": resource_type, "external_id": external_id})
    return doc.get("internal_id") if doc else None


# ── cursor pagination ───────────────────────────────────────────────
def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()


def decode_cursor(cursor: Optional[str]) -> int:
    if not cursor:
        return 0
    try:
        return int(json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())["o"])
    except Exception:
        raise ValueError("invalid_cursor")


def paginate(items: list, cursor: Optional[str], limit: int) -> dict:
    """Offset-cursor pagination over an in-memory list. Returns the standard
    {data, next_cursor, has_more} envelope."""
    limit = max(1, min(int(limit or 50), 100))
    offset = decode_cursor(cursor)
    page = items[offset:offset + limit]
    has_more = (offset + limit) < len(items)
    return {"data": page, "next_cursor": encode_cursor(offset + limit) if has_more else None,
            "has_more": has_more, "count": len(items)}


__all__ = [
    "ensure_ext_indexes", "idem_get", "idem_save",
    "external_get", "external_save", "external_lookup_id",
    "encode_cursor", "decode_cursor", "paginate", "IDEMPOTENCY_TTL_DAYS",
]
