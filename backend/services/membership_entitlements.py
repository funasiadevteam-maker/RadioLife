"""Membership Entitlements Engine — schema, enums, and helpers (Phase 1).

Replaces the simple discount-style membership with a true entitlement engine.
A plan grants ENTITLEMENTS bound to concrete menu items / products / a category
/ anything, with:
  - included options (free) vs upgrade options (charged their upcharge delta),
  - a per-period allowance (`quantity`) with a `reset_frequency`,
  - optional rollover of unused allowance,
  - day/time windows and stackability rules.

Menu items & products gain OPTION GROUPS (size / single-select / multi-select),
each option carrying a `price_delta_cents` upcharge relative to the base price.

Every entitlement use is written to the IMMUTABLE `membership_redemption_ledger`
(never mutated; reversals are appended as new rows). This module owns the
schema/normalisers/period math + ledger; checkout wiring lands in Phase 3.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from services.marketplace import now, new_id

# ───────────────────────── Enums ─────────────────────────
RESET_FREQUENCIES = ("daily", "weekly", "monthly", "billing_cycle", "total")
TARGET_TYPES = ("item", "product", "category", "any")
OPTION_GROUP_TYPES = ("size", "single", "multi")

# Legacy period -> new reset_frequency (for the v2 migration).
_LEGACY_PERIOD_MAP = {"day": "daily", "week": "weekly", "month": "monthly"}
# Reverse, for backward-compatible response aliases the old clients read.
_FREQ_TO_LEGACY_PERIOD = {"daily": "day", "weekly": "week", "monthly": "month",
                          "billing_cycle": "month", "total": "month"}


# ───────────────────── Option-group models ─────────────────────
class OptionChoiceModel(BaseModel):
    option_id: Optional[str] = None
    label: str = Field(..., min_length=1, max_length=80)
    price_delta_cents: int = Field(0, ge=-10_000_000, le=10_000_000)
    is_default: bool = False
    available: bool = True
    stock: Optional[int] = Field(None, ge=0, le=1_000_000)


class OptionGroupModel(BaseModel):
    group_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=80)
    type: str = Field("single")  # size | single | multi
    required: bool = False
    min_select: int = Field(0, ge=0, le=50)
    max_select: int = Field(1, ge=1, le=50)
    options: List[OptionChoiceModel] = Field(default_factory=list)


def normalize_option_groups(groups: List[OptionGroupModel]) -> List[Dict[str, Any]]:
    """Assign stable ids + coerce types. Idempotent (keeps existing ids)."""
    out: List[Dict[str, Any]] = []
    for g in groups or []:
        gtype = g.type if g.type in OPTION_GROUP_TYPES else "single"
        opts: List[Dict[str, Any]] = []
        for o in g.options:
            opts.append({
                "option_id": o.option_id or new_id("opt"),
                "label": o.label.strip(),
                "price_delta_cents": int(o.price_delta_cents),
                "is_default": bool(o.is_default),
                "available": bool(o.available),
                "stock": o.stock,
            })
        max_select = 1 if gtype in ("size", "single") else max(1, int(g.max_select))
        out.append({
            "group_id": g.group_id or new_id("grp"),
            "name": g.name.strip(), "type": gtype,
            "required": bool(g.required),
            "min_select": int(g.min_select), "max_select": max_select,
            "options": opts,
        })
    return out


def price_with_options(base_cents: int, option_groups: List[Dict[str, Any]],
                       selected_option_ids: List[str]) -> Tuple[int, List[Dict[str, Any]]]:
    """Base price + the deltas of every selected option. Returns
    (total_cents, selected_detail). Used by the Phase 3 pricing engine."""
    total = int(base_cents or 0)
    ids = set(selected_option_ids or [])
    selected: List[Dict[str, Any]] = []
    for g in option_groups or []:
        for o in g.get("options", []):
            if o.get("option_id") in ids:
                delta = int(o.get("price_delta_cents", 0))
                total += delta
                selected.append({
                    "group_id": g.get("group_id"), "group_name": g.get("name"),
                    "option_id": o.get("option_id"), "label": o.get("label"),
                    "price_delta_cents": delta})
    return max(0, total), selected


def validate_selection(option_groups: List[Dict[str, Any]],
                       selected_option_ids: List[str]) -> Optional[str]:
    """Return an error code if a selection violates required/min/max rules,
    else None. Availability of individual options is checked here too."""
    ids = set(selected_option_ids or [])
    for g in option_groups or []:
        valid = {o["option_id"] for o in g.get("options", [])}
        chosen = ids & valid
        for oid in chosen:
            o = next((x for x in g["options"] if x["option_id"] == oid), None)
            if o and not o.get("available", True):
                return "option_unavailable"
        n = len(chosen)
        if g.get("required") and n < max(1, int(g.get("min_select", 0) or 0)):
            return "option_group_required"
        if n < int(g.get("min_select", 0) or 0):
            return "min_select_not_met"
        if n > int(g.get("max_select", 1) or 1):
            return "max_select_exceeded"
    return None


# ───────────────────── Entitlement models ─────────────────────
class DayTimeRule(BaseModel):
    days: List[int] = Field(default_factory=list)  # 0=Mon .. 6=Sun; empty = all
    start_hour: Optional[int] = Field(None, ge=0, le=23)
    end_hour: Optional[int] = Field(None, ge=0, le=24)


class EntitlementModel(BaseModel):
    entitlement_id: Optional[str] = None
    label: str = Field(..., min_length=1, max_length=100)
    target_type: str = Field("any")  # item | product | category | any
    target_ids: List[str] = Field(default_factory=list)
    category: Optional[str] = Field(None, max_length=80)
    included_option_ids: List[str] = Field(default_factory=list)
    quantity: int = Field(1, ge=1, le=1000)
    reset_frequency: str = Field("monthly")
    rollover: bool = False
    rollover_cap: int = Field(0, ge=0, le=10000)
    day_time: Optional[DayTimeRule] = None
    stackable: bool = False
    max_upcharge_cents: Optional[int] = Field(None, ge=0, le=10_000_000)
    active: bool = True


def normalize_entitlements(ents: List[EntitlementModel]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in ents or []:
        tt = e.target_type if e.target_type in TARGET_TYPES else "any"
        freq = e.reset_frequency if e.reset_frequency in RESET_FREQUENCIES else "monthly"
        dt = None
        if e.day_time and (e.day_time.days or e.day_time.start_hour is not None
                           or e.day_time.end_hour is not None):
            dt = {"days": [d for d in e.day_time.days if 0 <= d <= 6],
                  "start_hour": e.day_time.start_hour, "end_hour": e.day_time.end_hour}
        out.append({
            "entitlement_id": e.entitlement_id or new_id("ent"),
            "label": e.label.strip(),
            "target_type": tt,
            "target_ids": [t.strip() for t in e.target_ids if t and t.strip()],
            "category": (e.category or "").strip() or None,
            "included_option_ids": [o for o in e.included_option_ids if o],
            "quantity": int(e.quantity),
            "reset_frequency": freq,
            "rollover": bool(e.rollover),
            "rollover_cap": int(e.rollover_cap),
            "day_time": dt,
            "stackable": bool(e.stackable),
            "max_upcharge_cents": e.max_upcharge_cents,
            "active": bool(e.active),
        })
    return out


# ───────────────────── Period / reset math ─────────────────────
def period_key(reset_frequency: str, dt: Optional[datetime] = None,
               membership: Optional[Dict[str, Any]] = None) -> str:
    """A bucket key for the current allowance window."""
    dt = dt or datetime.now(timezone.utc)
    if reset_frequency == "daily":
        return dt.strftime("%Y-%m-%d")
    if reset_frequency == "weekly":
        return dt.strftime("%G-W%V")
    if reset_frequency == "total":
        return "all"
    if reset_frequency == "billing_cycle":
        # Anchor to the membership's current period end if we know it, else month.
        cpe = (membership or {}).get("current_period_end")
        if isinstance(cpe, datetime):
            return "bc-" + cpe.strftime("%Y-%m-%d")
        if isinstance(cpe, str) and cpe:
            return "bc-" + cpe[:10]
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m")  # monthly (default)


def day_time_allows(rule: Optional[Dict[str, Any]], dt: Optional[datetime] = None) -> bool:
    if not rule:
        return True
    dt = dt or datetime.now(timezone.utc)
    days = rule.get("days") or []
    if days and dt.weekday() not in days:
        return False
    sh, eh = rule.get("start_hour"), rule.get("end_hour")
    if sh is None or eh is None:
        return True
    h = dt.hour
    if sh == eh:
        return True
    if sh < eh:
        return sh <= h < eh
    return h >= sh or h < eh  # wraps midnight


# ───────────────────── Ledger helpers ─────────────────────
async def entitlement_remaining(db, membership: Dict[str, Any],
                                entitlement: Dict[str, Any]) -> Dict[str, Any]:
    """Used / remaining for the current period (reads the immutable ledger).
    Rollover accrual is computed by the Phase 3 engine; here we report the
    current-period allowance."""
    freq = entitlement.get("reset_frequency", "monthly")
    pk = period_key(freq, membership=membership)
    ent_id = entitlement.get("entitlement_id")
    used = 0
    async for row in db.membership_redemption_ledger.find(
            {"membership_id": membership["membership_id"],
             "entitlement_id": ent_id,
             "period_key": pk, "status": "consumed"}):
        used += int(row.get("qty", 1) or 1)
    qty = int(entitlement.get("quantity", 1))
    return {"used": used, "remaining": max(0, qty - used),
            "period_key": pk, "reset_frequency": freq}


async def record_redemption(db, membership: Dict[str, Any], entitlement: Dict[str, Any], *,
                            order_id: Optional[str] = None, qty: int = 1,
                            base_value_cents: int = 0, upcharge_cents: int = 0,
                            selected_options: Optional[List[Dict[str, Any]]] = None,
                            target_ref: Optional[str] = None,
                            source: str = "claim") -> Dict[str, Any]:
    """Append an immutable ledger row for one entitlement use."""
    freq = entitlement.get("reset_frequency", "monthly")
    pk = period_key(freq, membership=membership)
    row = {
        "ledger_id": new_id("led"),
        "membership_id": membership["membership_id"],
        "plan_id": membership.get("plan_id"),
        "entitlement_id": entitlement["entitlement_id"],
        "user_id": membership.get("user_id"),
        "business_id": membership.get("business_id"),
        "order_id": order_id,
        "label": entitlement.get("label"),
        "target_ref": target_ref,
        "selected_options": selected_options or [],
        "qty": int(qty),
        "base_value_cents": int(base_value_cents),
        "upcharge_cents": int(upcharge_cents),
        "net_savings_cents": max(0, int(base_value_cents) - int(upcharge_cents)),
        "period_key": pk,
        "status": "consumed",
        "source": source,
        "created_at": now(),
    }
    await db.membership_redemption_ledger.insert_one(dict(row))
    return row


async def reverse_redemption(db, ledger_id: str, *, reason: str = "reversed") -> bool:
    """Append a compensating reversal row (never mutate the original)."""
    orig = await db.membership_redemption_ledger.find_one({"ledger_id": ledger_id})
    if not orig or orig.get("status") == "reversed":
        return False
    rev = {**{k: v for k, v in orig.items() if k != "_id"},
           "ledger_id": new_id("led"), "qty": -int(orig.get("qty", 1) or 1),
           "status": "reversal", "reverses_ledger_id": ledger_id,
           "reason": reason, "created_at": now()}
    await db.membership_redemption_ledger.insert_one(dict(rev))
    await db.membership_redemption_ledger.update_one(
        {"ledger_id": ledger_id}, {"$set": {"status": "reversed"}})
    return True


# ───────────────────── Indexes + migration ─────────────────────
async def ensure_membership_indexes(db) -> None:
    await db.membership_plans.create_index("plan_id", unique=True)
    await db.membership_plans.create_index([("business_id", 1), ("created_at", 1)])
    await db.memberships.create_index("membership_id", unique=True)
    await db.memberships.create_index([("user_id", 1), ("status", 1)])
    await db.membership_redemption_ledger.create_index("ledger_id", unique=True)
    await db.membership_redemption_ledger.create_index(
        [("membership_id", 1), ("entitlement_id", 1), ("period_key", 1)])
    await db.membership_redemption_ledger.create_index([("user_id", 1), ("created_at", -1)])
    await db.membership_redemption_ledger.create_index([("business_id", 1), ("created_at", -1)])
    await db.membership_redemption_ledger.create_index("order_id")


def _legacy_entitlement_to_v2(e: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "entitlement_id": e.get("benefit_id") or new_id("ent"),
        "label": e.get("label", "Benefit"),
        "target_type": "any", "target_ids": [], "category": None,
        "included_option_ids": [],
        "choice_labels": [o for o in (e.get("options") or []) if o],
        "quantity": int(e.get("qty", 1) or 1),
        "reset_frequency": _LEGACY_PERIOD_MAP.get(e.get("period", "day"), "daily"),
        "rollover": False, "rollover_cap": 0, "day_time": None,
        "stackable": False, "max_upcharge_cents": None, "active": True,
    }


async def migrate_memberships_v2(db) -> Dict[str, Any]:
    """Idempotently upgrade legacy plans (`schema_version != 2`) to the v2
    entitlement schema and mirror legacy claims into the immutable ledger."""
    await ensure_membership_indexes(db)
    plans_migrated = 0
    async for pl in db.membership_plans.find({"schema_version": {"$ne": 2}}):
        new_ents = [_legacy_entitlement_to_v2(e) for e in (pl.get("entitlements") or [])]
        await db.membership_plans.update_one(
            {"plan_id": pl["plan_id"]},
            {"$set": {"entitlements": new_ents, "schema_version": 2, "updated_at": now()}})
        plans_migrated += 1

    claims_migrated = 0
    async for c in db.membership_claims.find({}):
        if not c.get("claim_id"):
            continue
        lid = f"led_legacy_{c['claim_id']}"
        res = await db.membership_redemption_ledger.update_one(
            {"ledger_id": lid},
            {"$setOnInsert": {
                "ledger_id": lid, "membership_id": c.get("membership_id"),
                "plan_id": c.get("plan_id"), "entitlement_id": c.get("benefit_id"),
                "user_id": c.get("user_id"), "business_id": c.get("business_id"),
                "order_id": None, "label": c.get("label"), "target_ref": None,
                "selected_options": ([{"label": c.get("option")}] if c.get("option") else []),
                "qty": 1, "base_value_cents": 0, "upcharge_cents": 0,
                "net_savings_cents": 0, "period_key": c.get("period_key"),
                "status": "consumed", "source": "legacy_claim",
                "created_at": c.get("claimed_at") or now()}},
            upsert=True)
        if res.upserted_id is not None:
            claims_migrated += 1
    return {"plans_migrated": plans_migrated, "claims_migrated": claims_migrated}


__all__ = [
    "RESET_FREQUENCIES", "TARGET_TYPES", "OPTION_GROUP_TYPES",
    "OptionChoiceModel", "OptionGroupModel", "normalize_option_groups",
    "price_with_options", "validate_selection",
    "DayTimeRule", "EntitlementModel", "normalize_entitlements",
    "period_key", "day_time_allows", "entitlement_remaining",
    "record_redemption", "reverse_redemption",
    "ensure_membership_indexes", "migrate_memberships_v2",
]
