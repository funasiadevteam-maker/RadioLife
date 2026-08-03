"""Phase SC.3 — Commission service.

Two entry points:

    resolve_commission_rule(merchant_id, category, transaction_type, market?,
                                                  campaign_type?, at?)
        Deterministic 5-step resolution:
          1. Active merchant override for (merchant_id, transaction_type)
          2. Active merchant override for (merchant_id, transaction_type=None)
          3. commission_rules matching (category, transaction_type, market=<given>)
          4. commission_rules matching (category, transaction_type, market=null)
          5. FALLBACK rule (category="*", transaction_type="*")

    calculate_platform_fee(...)
        Pure-integer-cents arithmetic (no float rounding drift beyond the
        single `round()` on the percent multiplication).  Applies min-fee
        floor + max-fee cap.  Persists an audit-log row unless
        `write_audit=False`.

Both are read-only against Mongo except for the audit-log insert.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("bigfm.commission")

FALLBACK_RULE_ID = "cr_fallback_global"

VALID_STRIPE_FEE_RESP = {"platform", "merchant"}
OVERRIDE_STATUSES         = {"pending", "active", "expired", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _within_window(row: dict, at: datetime) -> bool:
    start = row.get("effective_start")
    end     = row.get("effective_end")
    if isinstance(start, str):
        try: start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception: start = None
    if isinstance(end, str):
        try: end = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception: end = None
    # BSON strips tz — coerce naive datetimes to UTC for comparison.
    if isinstance(start, datetime) and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if isinstance(end, datetime) and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if start and start > at:
        return False
    if end and end < at:
        return False
    return True


# ─── Resolver ─────────────────────────────────────────────────────
async def resolve_commission_rule(db, *, merchant_id: Optional[str],
                                                              category: str,
                                                              transaction_type: str,
                                                              market: Optional[str] = None,
                                                              campaign_type: Optional[str] = None,
                                                              at: Optional[datetime] = None) -> dict:
    at = at or _now()

    # ─ Step 1: active override for (merchant_id, txn_type) ─
    if merchant_id:
        ov = await db.merchant_commission_overrides.find_one({
            "merchant_id":            merchant_id,
            "transaction_type":  transaction_type,
            "status":                    "active",
        })
        if ov and _within_window(ov, at):
            return _view_from_override(ov, source="override")

        # ─ Step 2: general (txn_type=None) override for merchant ─
        ov2 = await db.merchant_commission_overrides.find_one({
            "merchant_id":            merchant_id,
            "transaction_type":  None,
            "status":                    "active",
        })
        if ov2 and _within_window(ov2, at):
            return _view_from_override(ov2, source="override")

    # ─ Step 3: rules matching (category, txn_type, market=<given>) ─
    if market:
        rule = await _best_rule(db, category=category,
                                                      transaction_type=transaction_type,
                                                      market=market, at=at)
        if rule:
            return _view_from_rule(rule, source="rule")

    # ─ Step 4: rules matching (category, txn_type, market=null) ─
    rule = await _best_rule(db, category=category,
                                                  transaction_type=transaction_type,
                                                  market=None, at=at)
    if rule:
        return _view_from_rule(rule, source="rule")

    # ─ Step 5: FALLBACK ─
    fallback = await db.commission_rules.find_one({
        "business_category": "*", "transaction_type": "*", "active": True})
    if fallback:
        return _view_from_rule(fallback, source="fallback")

    # Emergency default (should never fire because we seed a fallback)
    return {"rule_id": None, "override_id": None, "source": "hardcoded_default",
              "commission_percent": 10.0, "fixed_fee_cents": 0,
              "min_fee_cents": 0, "max_fee_cents": None,
              "stripe_fee_responsibility": "merchant"}


async def _best_rule(db, *, category: str, transaction_type: str,
                                      market: Optional[str], at: datetime) -> Optional[dict]:
    """Highest-priority active rule matching category+txn_type+market.
    Ties broken by latest effective_start."""
    cursor = db.commission_rules.find({
        "business_category":  category,
        "transaction_type":  transaction_type,
        "market":                    market,
        "active":                    True,
    }).sort([("priority", -1), ("effective_start", -1)])
    async for r in cursor:
        if _within_window(r, at):
            return r
    return None


def _view_from_rule(r: dict, *, source: str) -> dict:
    return {
        "rule_id":                              r.get("rule_id") or r.get("_id"),
        "override_id":                      None,
        "source":                              source,
        "commission_percent":          float(r.get("commission_percent") or 0),
        "fixed_fee_cents":              int(r.get("fixed_fee_cents") or 0),
        "min_fee_cents":                    int(r.get("min_fee_cents") or 0),
        "max_fee_cents":                    r.get("max_fee_cents"),
        "stripe_fee_responsibility": r.get("stripe_fee_responsibility") or "merchant",
    }


def _view_from_override(o: dict, *, source: str) -> dict:
    return {
        "rule_id":                              None,
        "override_id":                      o.get("override_id") or o.get("_id"),
        "source":                              source,
        "commission_percent":          float(o.get("custom_percent") or 0),
        "fixed_fee_cents":              int(o.get("custom_fixed_fee_cents") or 0),
        "min_fee_cents":                    int(o.get("min_fee_cents") or 0),
        "max_fee_cents":                    o.get("max_fee_cents"),
        "stripe_fee_responsibility": o.get("stripe_fee_responsibility") or "merchant",
    }


# ─── Calculator ──────────────────────────────────────────────────
async def calculate_platform_fee(db, *, merchant_id: Optional[str],
                                                                category: str,
                                                                transaction_type: str,
                                                                amount_cents: int,
                                                                market: Optional[str] = None,
                                                                campaign_type: Optional[str] = None,
                                                                write_audit: bool = True,
                                                                at: Optional[datetime] = None) -> dict:
    at = at or _now()
    resolved = await resolve_commission_rule(
        db, merchant_id=merchant_id, category=category,
        transaction_type=transaction_type, market=market,
        campaign_type=campaign_type, at=at)

    percent      = float(resolved["commission_percent"])
    fixed          = int(resolved["fixed_fee_cents"])
    min_cents  = int(resolved["min_fee_cents"] or 0)
    max_cents  = resolved["max_fee_cents"]

    # Integer arithmetic — banker's round on the percent multiplication
    percent_part = int(round(amount_cents * percent / 100.0))
    base              = percent_part + fixed
    floor_applied = False
    cap_applied    = False
    if min_cents and base < min_cents:
        base = min_cents; floor_applied = True
    if max_cents is not None and base > int(max_cents):
        base = int(max_cents); cap_applied = True

    breakdown = {
        "amount_cents":  int(amount_cents),
        "percent_part": percent_part,
        "fixed_part":    fixed,
        "min_fee_cents": min_cents,
        "max_fee_cents": max_cents,
        "floor_applied": floor_applied,
        "cap_applied":    cap_applied,
    }
    result = {
        "commission_cents":                base,
        "merchant_net_cents":            max(0, int(amount_cents) - base),
        "rule_id":                                  resolved["rule_id"],
        "override_id":                          resolved["override_id"],
        "source":                                  resolved["source"],
        "computed_percent":                percent,
        "fixed_fee_cents":                  fixed,
        "stripe_fee_responsibility": resolved["stripe_fee_responsibility"],
        "breakdown":                              breakdown,
    }

    if write_audit:
        try:
            aid = f"cau_{uuid.uuid4().hex[:16]}"
            await db.commission_audit_log.insert_one({
                "_id":                                aid,
                "audit_id":                        aid,
                "merchant_id":                merchant_id,
                "category":                      category,
                "transaction_type":      transaction_type,
                "market":                          market,
                "campaign_type":              campaign_type,
                "amount_cents":              int(amount_cents),
                "resolved_rule_id":      resolved["rule_id"],
                "resolved_override_id": resolved["override_id"],
                "computed_commission_cents": base,
                "breakdown_json":            breakdown,
                "computed_at":                at,
            })
        except Exception:
            logger.exception("[commission] audit-log insert failed (non-blocking)")

    return result


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_commission_indexes(db) -> None:
    await db.commission_rules.create_index("rule_id", unique=True)
    await db.commission_rules.create_index([
        ("business_category", 1), ("transaction_type", 1),
        ("market", 1), ("active", 1)])
    await db.commission_rules.create_index([
        ("business_category", 1), ("priority", -1)])
    await db.merchant_commission_overrides.create_index("override_id", unique=True)
    await db.merchant_commission_overrides.create_index([
        ("merchant_id", 1), ("transaction_type", 1), ("status", 1)])
    await db.commission_audit_log.create_index([
        ("merchant_id", 1), ("computed_at", -1)])
    await db.commission_audit_log.create_index([
        ("computed_at", -1)])


__all__ = [
    "resolve_commission_rule",
    "calculate_platform_fee",
    "ensure_commission_indexes",
    "FALLBACK_RULE_ID",
    "VALID_STRIPE_FEE_RESP",
    "OVERRIDE_STATUSES",
]
