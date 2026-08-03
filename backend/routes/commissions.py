"""Phase SC.3 — Commission rules + overrides + audit endpoints.

Public / merchant endpoints:
    GET  /api/commissions/rates              — snapshot for /legal/commissions
    GET  /api/commissions/preview        — compute a fee (auth any logged-in user)

Admin-only endpoints:
    GET  /api/admin/commission-rules
    POST /api/admin/commission-rules
    PUT  /api/admin/commission-rules/{rule_id}
    POST /api/admin/commission-rules/{rule_id}/deactivate

    GET  /api/admin/commission-overrides
    POST /api/admin/commission-overrides
    PUT  /api/admin/commission-overrides/{override_id}

    GET  /api/admin/commission-audit
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services.commission_service import (FALLBACK_RULE_ID,
                                                                            OVERRIDE_STATUSES,
                                                                            VALID_STRIPE_FEE_RESP,
                                                                            calculate_platform_fee)

logger = logging.getLogger("bigfm.commissions")

router = APIRouter(prefix="/api", tags=["commissions"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _rule_view(r: dict) -> dict:
    return {
        "rule_id":                          r.get("rule_id") or r.get("_id"),
        "name":                              r.get("name"),
        "business_category":      r.get("business_category"),
        "transaction_type":      r.get("transaction_type"),
        "commission_percent":  float(r.get("commission_percent") or 0),
        "fixed_fee_cents":            int(r.get("fixed_fee_cents") or 0),
        "min_fee_cents":                int(r.get("min_fee_cents") or 0),
        "max_fee_cents":                r.get("max_fee_cents"),
        "stripe_fee_responsibility": r.get("stripe_fee_responsibility") or "merchant",
        "market":                          r.get("market"),
        "campaign_type":              r.get("campaign_type"),
        "priority":                      int(r.get("priority") or 0),
        "effective_start":          _iso(r.get("effective_start")),
        "effective_end":                _iso(r.get("effective_end")),
        "active":                          bool(r.get("active")),
        "deletable":                    bool(r.get("deletable", True)),
        "notes":                            r.get("notes"),
        "created_at":                  _iso(r.get("created_at")),
        "updated_at":                  _iso(r.get("updated_at")),
        "created_by":                  r.get("created_by"),
    }


def _override_view(o: dict) -> dict:
    return {
        "override_id":                        o.get("override_id") or o.get("_id"),
        "merchant_id":                      o.get("merchant_id"),
        "transaction_type":            o.get("transaction_type"),
        "custom_percent":                  o.get("custom_percent"),
        "custom_fixed_fee_cents":  o.get("custom_fixed_fee_cents"),
        "min_fee_cents":                      o.get("min_fee_cents"),
        "max_fee_cents":                      o.get("max_fee_cents"),
        "effective_start":                _iso(o.get("effective_start")),
        "effective_end":                    _iso(o.get("effective_end")),
        "status":                                o.get("status"),
        "approval_notes":                  o.get("approval_notes"),
        "approved_by":                      o.get("approved_by"),
        "approved_at":                      _iso(o.get("approved_at")),
        "created_at":                        _iso(o.get("created_at")),
        "updated_at":                        _iso(o.get("updated_at")),
        "created_by":                        o.get("created_by"),
    }


# ─── Public — snapshot for /legal/commissions ────────────────────
@router.get("/commissions/rates")
async def public_rates(request: Request):
    """Grouped snapshot of active default rules (market=null).  Fallback
    row is included but tagged so the UI can display it as "everything
    else"."""
    db = request.app.state.db
    now = _now()
    cursor = db.commission_rules.find({
        "active":  True,
        "market":  None,
    }).sort([("business_category", 1), ("transaction_type", 1)])

    by_category: dict[str, list[dict]] = {}
    fallback = None
    last_updated: Optional[datetime] = None
    total = 0
    async for r in cursor:
        v = _rule_view(r)
        total += 1
        ts = r.get("updated_at") or r.get("created_at")
        if ts and (last_updated is None or ts > last_updated):
            last_updated = ts
        row = {
            "rule_id":                          v["rule_id"],
            "name":                              v["name"],
            "transaction_type":      v["transaction_type"],
            "commission_percent":  v["commission_percent"],
            "fixed_fee_cents":            v["fixed_fee_cents"],
            "min_fee_cents":                v["min_fee_cents"],
            "max_fee_cents":                v["max_fee_cents"],
            "notes":                            v["notes"],
        }
        cat = v["business_category"]
        if cat == "*":
            fallback = row
        else:
            by_category.setdefault(cat, []).append(row)

    return {
        "count":                total,
        "categories":      by_category,
        "fallback":          fallback,
        "last_updated": _iso(last_updated),
    }


# ─── Preview endpoint (any authenticated caller) ─────────────────
@router.get("/commissions/preview")
async def preview_fee(request: Request,
                                      category: str = Query(..., min_length=1),
                                      transaction_type: str = Query(..., min_length=1),
                                      amount_cents: int = Query(..., ge=0),
                                      market: Optional[str] = Query(None),
                                      merchant_id: Optional[str] = Query(None),
                                      campaign_type: Optional[str] = Query(None),
                                      user: dict = Depends(current_user)):
    """Compute the effective fee.  Audit-log write is skipped for previews
    (write_audit=False) so wizard step 7 doesn't pollute the log with
    speculative calls."""
    db = request.app.state.db
    # Only admins can preview against a different merchant_id
    if merchant_id and user.get("role") != "admin" \
              and not user.get("is_admin"):
        biz = await db.businesses.find_one({"business_id": merchant_id},
                                                                        {"owner_user_id": 1})
        if not biz:
            biz = await db.businesses.find_one({"_id": merchant_id},
                                                                            {"owner_user_id": 1})
        if not biz or biz.get("owner_user_id") != user["user_id"]:
            raise HTTPException(403, "cannot_preview_other_merchant")

    result = await calculate_platform_fee(
        db,
        merchant_id=merchant_id,
        category=category,
        transaction_type=transaction_type,
        amount_cents=int(amount_cents),
        market=market,
        campaign_type=campaign_type,
        write_audit=False,
    )
    return result


# ─── Admin: rules CRUD ───────────────────────────────────────────
class RuleBody(BaseModel):
    name:                                        str = Field(min_length=2, max_length=120)
    business_category:              str = Field(min_length=1, max_length=60)
    transaction_type:                  str = Field(min_length=1, max_length=60)
    commission_percent:              float = Field(ge=0, le=100)
    fixed_fee_cents:                    int = Field(default=0, ge=0)
    min_fee_cents:                          int = Field(default=0, ge=0)
    max_fee_cents:                          Optional[int] = Field(default=None, ge=0)
    stripe_fee_responsibility:  str = Field(default="merchant")
    market:                                    Optional[str] = Field(default=None, max_length=8)
    campaign_type:                        Optional[str] = Field(default=None, max_length=60)
    priority:                                  int = Field(default=0)
    effective_start:                    Optional[datetime] = None
    effective_end:                          Optional[datetime] = None
    notes:                                        Optional[str] = Field(default=None, max_length=500)


class RulePatch(BaseModel):
    name:                                        Optional[str] = Field(default=None, max_length=120)
    commission_percent:              Optional[float] = Field(default=None, ge=0, le=100)
    fixed_fee_cents:                    Optional[int] = Field(default=None, ge=0)
    min_fee_cents:                          Optional[int] = Field(default=None, ge=0)
    max_fee_cents:                          Optional[int] = Field(default=None, ge=0)
    stripe_fee_responsibility:  Optional[str] = None
    market:                                    Optional[str] = Field(default=None, max_length=8)
    campaign_type:                        Optional[str] = Field(default=None, max_length=60)
    priority:                                  Optional[int] = None
    effective_start:                    Optional[datetime] = None
    effective_end:                          Optional[datetime] = None
    active:                                    Optional[bool] = None
    notes:                                        Optional[str] = Field(default=None, max_length=500)


@router.get("/admin/commission-rules")
async def admin_list_rules(request: Request,
                                              _admin: dict = Depends(require_admin),
                                              category: Optional[str] = Query(None),
                                              transaction_type: Optional[str] = Query(None),
                                              active: Optional[bool] = Query(None),
                                              limit: int = Query(200, ge=1, le=500),
                                              offset: int = Query(0, ge=0)):
    db = request.app.state.db
    q: dict = {}
    if category:            q["business_category"] = category
    if transaction_type: q["transaction_type"]  = transaction_type
    if active is not None: q["active"]                    = active
    total = await db.commission_rules.count_documents(q)
    cursor = db.commission_rules.find(q).sort([
        ("business_category", 1), ("priority", -1),
        ("transaction_type", 1)]).skip(offset).limit(limit)
    items = []
    async for r in cursor:
        items.append(_rule_view(r))
    return {"total": total, "count": len(items),
              "limit": limit, "offset": offset, "items": items}


@router.post("/admin/commission-rules")
async def admin_create_rule(body: RuleBody, request: Request,
                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    if body.stripe_fee_responsibility not in VALID_STRIPE_FEE_RESP:
        raise HTTPException(400, f"invalid_stripe_fee_responsibility")
    if body.max_fee_cents is not None and body.max_fee_cents < body.min_fee_cents:
        raise HTTPException(400, "max_fee_below_min_fee")

    now = _now()
    rid = f"cr_{uuid.uuid4().hex[:14]}"
    doc = body.model_dump()
    doc.update({
        "_id":                        rid,
        "rule_id":                rid,
        "effective_start":  doc.get("effective_start") or now,
        "active":                  True,
        "created_at":          now,
        "updated_at":          now,
        "created_by":          admin.get("user_id"),
        "deletable":            True,
    })
    await db.commission_rules.insert_one(doc)
    logger.info(f"[commissions] rule created rid={rid} by={admin.get('user_id')} "
                          f"cat={body.business_category} txn={body.transaction_type} pct={body.commission_percent}")
    return _rule_view(doc)


@router.put("/admin/commission-rules/{rule_id}")
async def admin_update_rule(rule_id: str, patch: RulePatch, request: Request,
                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    existing = await db.commission_rules.find_one({"rule_id": rule_id})
    if not existing:
        raise HTTPException(404, "rule_not_found")
    if rule_id == FALLBACK_RULE_ID:
        # Guardrail: allow tweaking the fallback's percent/notes but not
        # deactivating it or changing its wildcard scope.
        if patch.active is False:
            raise HTTPException(400, "cannot_deactivate_fallback")
    updates = {k: v for k, v in patch.model_dump(exclude_unset=True).items()
                    if v is not None or k in ("effective_end", "max_fee_cents",
                                                                    "market", "campaign_type", "notes")}
    if "stripe_fee_responsibility" in updates \
              and updates["stripe_fee_responsibility"] not in VALID_STRIPE_FEE_RESP:
        raise HTTPException(400, "invalid_stripe_fee_responsibility")
    min_c = updates.get("min_fee_cents", existing.get("min_fee_cents", 0))
    max_c = updates.get("max_fee_cents", existing.get("max_fee_cents"))
    if max_c is not None and int(max_c) < int(min_c or 0):
        raise HTTPException(400, "max_fee_below_min_fee")

    updates["updated_at"] = _now()
    await db.commission_rules.update_one(
        {"rule_id": rule_id}, {"$set": updates})
    fresh = await db.commission_rules.find_one({"rule_id": rule_id})
    logger.info(f"[commissions] rule updated rid={rule_id} by={admin.get('user_id')} "
                          f"fields={list(updates.keys())}")
    return _rule_view(fresh)


@router.post("/admin/commission-rules/{rule_id}/deactivate")
async def admin_deactivate_rule(rule_id: str, request: Request,
                                                          admin: dict = Depends(require_admin)):
    db = request.app.state.db
    if rule_id == FALLBACK_RULE_ID:
        raise HTTPException(400, "cannot_deactivate_fallback")
    existing = await db.commission_rules.find_one({"rule_id": rule_id})
    if not existing:
        raise HTTPException(404, "rule_not_found")
    await db.commission_rules.update_one(
        {"rule_id": rule_id},
        {"$set": {"active": False, "updated_at": _now(),
                        "deactivated_by": admin.get("user_id")}})
    fresh = await db.commission_rules.find_one({"rule_id": rule_id})
    logger.info(f"[commissions] rule deactivated rid={rule_id} by={admin.get('user_id')}")
    return _rule_view(fresh)


# ─── Admin: overrides ────────────────────────────────────────────
class OverrideBody(BaseModel):
    merchant_id:                    str = Field(min_length=3, max_length=64)
    transaction_type:          Optional[str] = Field(default=None, max_length=60)
    custom_percent:              Optional[float] = Field(default=None, ge=0, le=100)
    custom_fixed_fee_cents: Optional[int] = Field(default=None, ge=0)
    min_fee_cents:                    Optional[int] = Field(default=None, ge=0)
    max_fee_cents:                    Optional[int] = Field(default=None, ge=0)
    stripe_fee_responsibility: Optional[str] = None
    effective_start:            Optional[datetime] = None
    effective_end:                  Optional[datetime] = None
    approval_notes:              Optional[str] = Field(default=None, max_length=500)


class OverridePatch(BaseModel):
    custom_percent:              Optional[float] = Field(default=None, ge=0, le=100)
    custom_fixed_fee_cents: Optional[int] = Field(default=None, ge=0)
    min_fee_cents:                    Optional[int] = Field(default=None, ge=0)
    max_fee_cents:                    Optional[int] = Field(default=None, ge=0)
    stripe_fee_responsibility: Optional[str] = None
    effective_start:            Optional[datetime] = None
    effective_end:                  Optional[datetime] = None
    status:                              Optional[str] = None
    approval_notes:              Optional[str] = Field(default=None, max_length=500)


@router.get("/admin/commission-overrides")
async def admin_list_overrides(request: Request,
                                                          _admin: dict = Depends(require_admin),
                                                          merchant_id: Optional[str] = Query(None),
                                                          status: Optional[str] = Query(None),
                                                          limit: int = Query(100, ge=1, le=500),
                                                          offset: int = Query(0, ge=0)):
    db = request.app.state.db
    q: dict = {}
    if merchant_id: q["merchant_id"] = merchant_id
    if status:
        if status not in OVERRIDE_STATUSES:
            raise HTTPException(400, f"invalid_status:{status}")
        q["status"] = status
    total = await db.merchant_commission_overrides.count_documents(q)
    cursor = db.merchant_commission_overrides.find(q).sort(
        "created_at", -1).skip(offset).limit(limit)
    items = []
    async for o in cursor:
        v = _override_view(o)
        biz = await db.businesses.find_one(
            {"$or": [{"business_id": v["merchant_id"]},
                          {"_id": v["merchant_id"]}]},
            {"name": 1, "category": 1, "category_id": 1})
        v["merchant_name"]  = (biz or {}).get("name")
        v["merchant_category"] = (biz or {}).get("category_id") \
                                                        or (biz or {}).get("category")
        items.append(v)
    return {"total": total, "count": len(items),
              "limit": limit, "offset": offset, "items": items}


@router.post("/admin/commission-overrides")
async def admin_create_override(body: OverrideBody, request: Request,
                                                            admin: dict = Depends(require_admin)):
    db = request.app.state.db
    # Verify merchant exists
    biz = await db.businesses.find_one({"$or": [
        {"business_id": body.merchant_id}, {"_id": body.merchant_id}]})
    if not biz:
        raise HTTPException(404, "merchant_not_found")
    if (body.stripe_fee_responsibility
              and body.stripe_fee_responsibility not in VALID_STRIPE_FEE_RESP):
        raise HTTPException(400, "invalid_stripe_fee_responsibility")
    if body.max_fee_cents is not None and body.min_fee_cents is not None \
              and body.max_fee_cents < body.min_fee_cents:
        raise HTTPException(400, "max_fee_below_min_fee")
    if body.custom_percent is None and body.custom_fixed_fee_cents is None:
        raise HTTPException(400, "must_provide_custom_percent_or_fixed_fee")

    now = _now()
    oid = f"co_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id":                            oid,
        "override_id":              oid,
        "merchant_id":              body.merchant_id,
        "transaction_type":    body.transaction_type,
        "custom_percent":        body.custom_percent,
        "custom_fixed_fee_cents": body.custom_fixed_fee_cents,
        "min_fee_cents":            body.min_fee_cents,
        "max_fee_cents":            body.max_fee_cents,
        "stripe_fee_responsibility": body.stripe_fee_responsibility,
        "effective_start":      body.effective_start or now,
        "effective_end":            body.effective_end,
        "status":                        "active",
        "approval_notes":        body.approval_notes,
        "approved_by":            admin.get("user_id"),
        "approved_at":            now,
        "created_by":              admin.get("user_id"),
        "created_at":              now,
        "updated_at":              now,
    }
    await db.merchant_commission_overrides.insert_one(doc)
    logger.info(f"[commissions] override created oid={oid} mid={body.merchant_id} "
                          f"pct={body.custom_percent} by={admin.get('user_id')}")
    return _override_view(doc)


@router.put("/admin/commission-overrides/{override_id}")
async def admin_update_override(override_id: str, patch: OverridePatch,
                                                            request: Request,
                                                            admin: dict = Depends(require_admin)):
    db = request.app.state.db
    existing = await db.merchant_commission_overrides.find_one(
        {"override_id": override_id})
    if not existing:
        raise HTTPException(404, "override_not_found")
    updates = {k: v for k, v in patch.model_dump(exclude_unset=True).items()
                    if v is not None or k in ("effective_end", "max_fee_cents",
                                                                    "approval_notes")}
    if "status" in updates and updates["status"] not in OVERRIDE_STATUSES:
        raise HTTPException(400, f"invalid_status:{updates['status']}")
    if ("stripe_fee_responsibility" in updates
              and updates["stripe_fee_responsibility"] not in VALID_STRIPE_FEE_RESP):
        raise HTTPException(400, "invalid_stripe_fee_responsibility")
    updates["updated_at"] = _now()
    await db.merchant_commission_overrides.update_one(
        {"override_id": override_id}, {"$set": updates})
    fresh = await db.merchant_commission_overrides.find_one(
        {"override_id": override_id})
    logger.info(f"[commissions] override updated oid={override_id} by={admin.get('user_id')} "
                          f"fields={list(updates.keys())}")
    return _override_view(fresh)


# ─── Admin: audit-log read ───────────────────────────────────────
@router.get("/admin/commission-audit")
async def admin_audit_log(request: Request,
                                              _admin: dict = Depends(require_admin),
                                              merchant_id: Optional[str] = Query(None),
                                              from_date: Optional[datetime] = Query(None),
                                              to_date:    Optional[datetime] = Query(None),
                                              limit: int = Query(200, ge=1, le=1000),
                                              offset: int = Query(0, ge=0)):
    db = request.app.state.db
    q: dict = {}
    if merchant_id: q["merchant_id"] = merchant_id
    if from_date or to_date:
        window: dict = {}
        if from_date: window["$gte"] = from_date
        if to_date:    window["$lte"] = to_date
        q["computed_at"] = window
    total = await db.commission_audit_log.count_documents(q)
    cursor = db.commission_audit_log.find(q).sort("computed_at", -1) \
                                              .skip(offset).limit(limit)
    items = []
    async for a in cursor:
        items.append({
            "audit_id":                              a.get("audit_id"),
            "merchant_id":                        a.get("merchant_id"),
            "category":                              a.get("category"),
            "transaction_type":              a.get("transaction_type"),
            "market":                                  a.get("market"),
            "campaign_type":                      a.get("campaign_type"),
            "amount_cents":                      a.get("amount_cents"),
            "resolved_rule_id":              a.get("resolved_rule_id"),
            "resolved_override_id":      a.get("resolved_override_id"),
            "computed_commission_cents": a.get("computed_commission_cents"),
            "breakdown_json":                  a.get("breakdown_json"),
            "computed_at":                        _iso(a.get("computed_at")),
        })
    return {"total": total, "count": len(items),
              "limit": limit, "offset": offset, "items": items}


__all__ = ["router"]
