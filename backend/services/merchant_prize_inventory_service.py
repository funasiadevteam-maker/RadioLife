"""Phase PW-M.1 — Merchant Prize Inventory service.

Collection: `merchant_prize_inventory`

Row shape:
    prize_id (unique), merchant_id, location_id (nullable),
    prize_type, title, description, retail_value,
    quantity_total, quantity_reserved, quantity_awarded, quantity_redeemed,
    expiration_policy (dict), redemption_method, terms,
    active, created_at, updated_at

The 4 quantity counters MUST satisfy:
    0 <= quantity_reserved + quantity_awarded <= quantity_total
    quantity_redeemed <= quantity_awarded
Atomic operations enforce this via conditional `$inc` updates.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("bigfm.pw_m.prize_inventory")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_prize_id() -> str:
    return f"mpi_{uuid.uuid4().hex[:16]}"


ALLOWED_PRIZE_TYPES = {
    "coupon", "gift_card", "free_item", "prepaid_meal",
    "product_sample", "experience", "merchandise", "custom",
}
ALLOWED_REDEMPTION_METHODS = {"cashier_qr", "cashier_code", "at_pickup",
                                                                                "email_delivery", "in_app_only"}


def _strip(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at"):
        if isinstance(doc.get(k), datetime):
            doc[k] = doc[k].isoformat()
    return doc


# ─────────────────────────── CRUD ───────────────────────────
async def list_prize_inventory(db, *, merchant_id: str,
                                                                            include_inactive: bool = False,
                                                                            location_id: Optional[str] = None
                                                                            ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"merchant_id": merchant_id}
    if not include_inactive:
        q["active"] = True
    if location_id is not None:
        q["location_id"] = location_id
    out = []
    async for d in db.merchant_prize_inventory.find(q).sort("created_at", -1):
        out.append(_strip(d))
    return out


async def get_prize(db, *, prize_id: str,
                                          merchant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    q: Dict[str, Any] = {"prize_id": prize_id}
    if merchant_id:
        q["merchant_id"] = merchant_id
    return _strip(await db.merchant_prize_inventory.find_one(q))


async def create_prize(db, *, merchant_id: str, body: Dict[str, Any]
                                              ) -> Dict[str, Any]:
    prize_type = str(body.get("prize_type") or "").strip().lower()
    if prize_type not in ALLOWED_PRIZE_TYPES:
        raise ValueError(f"invalid_prize_type:{prize_type}")
    redemption_method = str(body.get("redemption_method")
                                                          or "cashier_qr").strip().lower()
    if redemption_method not in ALLOWED_REDEMPTION_METHODS:
        raise ValueError(f"invalid_redemption_method:{redemption_method}")
    title = str(body.get("title") or "").strip()
    if not title:
        raise ValueError("missing_title")
    qty_total = int(body.get("quantity_total") or 0)
    if qty_total < 1:
        raise ValueError("quantity_total_must_be_positive")

    prize_id = _new_prize_id()
    now = _now()
    doc = {
        "_id":                                prize_id,
        "prize_id":                      prize_id,
        "merchant_id":                merchant_id,
        "location_id":                body.get("location_id"),
        "prize_type":                  prize_type,
        "title":                            title,
        "description":                (body.get("description") or "").strip(),
        "retail_value":              float(body.get("retail_value") or 0),
        "currency":                      (body.get("currency") or "AED").upper(),
        "quantity_total":         qty_total,
        "quantity_reserved":     0,
        "quantity_awarded":       0,
        "quantity_redeemed":     0,
        "expiration_policy":     body.get("expiration_policy") or {},
        "redemption_method":     redemption_method,
        "terms":                            (body.get("terms") or "").strip(),
        "active":                          True,
        "created_at":                  now,
        "updated_at":                  now,
    }
    await db.merchant_prize_inventory.insert_one(doc)
    return _strip(doc)


ALLOWED_UPDATE_FIELDS = {"title", "description", "retail_value", "terms",
                                                                          "active", "expiration_policy", "location_id",
                                                                          "redemption_method"}


async def patch_prize(db, *, prize_id: str, merchant_id: str,
                                            updates: Dict[str, Any]) -> Dict[str, Any]:
    p = await db.merchant_prize_inventory.find_one(
        {"prize_id": prize_id, "merchant_id": merchant_id})
    if not p:
        raise LookupError("prize_not_found")
    clean = {k: v for k, v in updates.items() if k in ALLOWED_UPDATE_FIELDS}
    clean["updated_at"] = _now()
    await db.merchant_prize_inventory.update_one(
        {"prize_id": prize_id, "merchant_id": merchant_id},
        {"$set": clean})
    return _strip(await db.merchant_prize_inventory.find_one(
        {"prize_id": prize_id, "merchant_id": merchant_id}))


# ─────────────────────── Quantity ops ───────────────────────
async def reserve(db, *, prize_id: str, merchant_id: str,
                                    qty: int) -> Dict[str, Any]:
    """Atomically increment `quantity_reserved` when `available >= qty`.

    Raises ValueError('insufficient_inventory') on failure."""
    if qty < 1:
        raise ValueError("qty_must_be_positive")
    p = await db.merchant_prize_inventory.find_one(
        {"prize_id": prize_id, "merchant_id": merchant_id, "active": True})
    if not p:
        raise LookupError("prize_not_found")
    available = (int(p["quantity_total"]) - int(p["quantity_reserved"])
                              - int(p["quantity_awarded"]))
    if available < qty:
        raise ValueError("insufficient_inventory")
    # Conditional atomic update — guarantees no over-reservation on race.
    r = await db.merchant_prize_inventory.update_one(
        {"prize_id": prize_id, "merchant_id": merchant_id,
          "$expr": {"$gte": [
              {"$subtract": [{"$subtract": ["$quantity_total", "$quantity_reserved"]},
                                          "$quantity_awarded"]},
              qty]}},
        {"$inc": {"quantity_reserved": qty},
          "$set": {"updated_at": _now()}})
    if r.modified_count == 0:
        raise ValueError("insufficient_inventory")
    return _strip(await db.merchant_prize_inventory.find_one({"prize_id": prize_id}))


async def release(db, *, prize_id: str, qty: int) -> Dict[str, Any]:
    """Decrement `quantity_reserved` — called on pause / cancel."""
    if qty < 1:
        return _strip(await db.merchant_prize_inventory.find_one({"prize_id": prize_id}))
    await db.merchant_prize_inventory.update_one(
        {"prize_id": prize_id,
          "quantity_reserved": {"$gte": qty}},
        {"$inc": {"quantity_reserved": -qty},
          "$set": {"updated_at": _now()}})
    return _strip(await db.merchant_prize_inventory.find_one({"prize_id": prize_id}))


async def award(db, *, prize_id: str, qty: int) -> Dict[str, Any]:
    """Move reserved → awarded when a winner is confirmed."""
    if qty < 1:
        return _strip(await db.merchant_prize_inventory.find_one({"prize_id": prize_id}))
    await db.merchant_prize_inventory.update_one(
        {"prize_id": prize_id,
          "quantity_reserved": {"$gte": qty}},
        {"$inc": {"quantity_reserved": -qty, "quantity_awarded": qty},
          "$set": {"updated_at": _now()}})
    return _strip(await db.merchant_prize_inventory.find_one({"prize_id": prize_id}))


async def redeem(db, *, prize_id: str, qty: int = 1) -> Dict[str, Any]:
    """Increment `quantity_redeemed` — called on cashier scan."""
    await db.merchant_prize_inventory.update_one(
        {"prize_id": prize_id,
          "quantity_awarded": {"$gte": qty}},
        {"$inc": {"quantity_redeemed": qty},
          "$set": {"updated_at": _now()}})
    return _strip(await db.merchant_prize_inventory.find_one({"prize_id": prize_id}))
