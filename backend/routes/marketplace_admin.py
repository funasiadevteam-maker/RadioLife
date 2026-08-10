"""Marketplace Admin API — BigPoints economics, categories, commission
rules, and business approvals.  Admin-only."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_admin
from services.marketplace import now, new_id, resolve_point_cost_cents, resolve_commission

router = APIRouter(prefix="/api/admin/marketplace", tags=["marketplace-admin"])


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc.pop("_id", None)
    for k in ("effective_date", "created_at", "updated_at"):
        v = doc.get(k)
        if hasattr(v, "isoformat"):
            doc[k] = v.isoformat()
    return doc


# ───────────── BigPoints Economics ─────────────
@router.get("/bigpoint-rates")
async def list_rates(request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    out = [_clean(r) async for r in db.bigpoint_rates.find().sort("created_at", -1)]
    return {"items": out, "default_cost_per_point_cents": 3.0}


class RateBody(BaseModel):
    scope: str = Field(..., description="global|market|category|merchant")
    cost_per_point_cents: float = Field(..., gt=0, le=100)
    market: Optional[str] = None
    category: Optional[str] = None
    merchant_id: Optional[str] = None
    active: bool = True


@router.post("/bigpoint-rates")
async def create_rate(body: RateBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    rid = new_id("rate")
    doc = {"rate_id": rid, **body.model_dump(), "effective_date": now(),
           "created_at": now(), "updated_at": now()}
    await db.bigpoint_rates.insert_one(dict(doc))
    return _clean(doc)


@router.patch("/bigpoint-rates/{rate_id}")
async def update_rate(rate_id: str, body: RateBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    r = await db.bigpoint_rates.find_one({"rate_id": rate_id})
    if not r:
        raise HTTPException(404, {"code": "rate_not_found"})
    await db.bigpoint_rates.update_one(
        {"rate_id": rate_id}, {"$set": {**body.model_dump(), "updated_at": now()}})
    return {"ok": True}


# ───────────── Categories ─────────────
@router.get("/categories")
async def list_categories(request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    out = [_clean(c) async for c in db.marketplace_categories.find().sort("name", 1)]
    return {"items": out}


class CategoryBody(BaseModel):
    key: str
    name: str
    icon: str = "storefront"
    parent: Optional[str] = None
    product_enabled: bool = False
    service_enabled: bool = False
    booking_enabled: bool = False
    menu_enabled: bool = False
    pickup_enabled: bool = False
    shipping_enabled: bool = False
    digital_enabled: bool = False
    commission_pct: float = Field(15.0, ge=0, le=100)
    min_bigpoints: int = Field(0, ge=0)
    requires_approval: bool = True
    active: bool = True


@router.post("/categories")
async def create_category(body: CategoryBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    if await db.marketplace_categories.find_one({"key": body.key}):
        raise HTTPException(400, {"code": "category_exists"})
    doc = {**body.model_dump(), "created_at": now(), "updated_at": now()}
    await db.marketplace_categories.insert_one(dict(doc))
    return _clean(doc)


@router.patch("/categories/{key}")
async def update_category(key: str, body: CategoryBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    if not await db.marketplace_categories.find_one({"key": key}):
        raise HTTPException(404, {"code": "category_not_found"})
    await db.marketplace_categories.update_one(
        {"key": key}, {"$set": {**body.model_dump(), "updated_at": now()}})
    return {"ok": True}


# ───────────── Commission Rules ─────────────
@router.get("/commission-rules")
async def list_commission(request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    out = [_clean(r) async for r in db.marketplace_commission_rules.find().sort("created_at", -1)]
    return {"items": out}


class CommissionBody(BaseModel):
    scope: str = Field(..., description="global|category|market|market_category|merchant")
    commission_pct: float = Field(..., ge=0, le=100)
    fixed_fee_cents: int = Field(0, ge=0)
    min_fee_cents: int = Field(0, ge=0)
    max_fee_cents: Optional[int] = None
    category: Optional[str] = None
    market: Optional[str] = None
    merchant_id: Optional[str] = None
    active: bool = True


@router.post("/commission-rules")
async def create_commission(body: CommissionBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    rid = new_id("comm")
    doc = {"rule_id": rid, **body.model_dump(), "effective_date": now(),
           "created_at": now(), "updated_at": now()}
    await db.marketplace_commission_rules.insert_one(dict(doc))
    return _clean(doc)


@router.patch("/commission-rules/{rule_id}")
async def update_commission(rule_id: str, body: CommissionBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    if not await db.marketplace_commission_rules.find_one({"rule_id": rule_id}):
        raise HTTPException(404, {"code": "rule_not_found"})
    await db.marketplace_commission_rules.update_one(
        {"rule_id": rule_id}, {"$set": {**body.model_dump(), "updated_at": now()}})
    return {"ok": True}


# ───────────── Business Approvals ─────────────
@router.get("/businesses")
async def list_businesses(request: Request, status: Optional[str] = None, _a=Depends(require_admin)):
    db = request.app.state.db
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    out = [_clean(p) async for p in db.marketplace_profiles.find(q).sort("created_at", -1).limit(200)]
    return {"items": out, "total": len(out)}


class ApprovalBody(BaseModel):
    reason: Optional[str] = None


@router.post("/businesses/{business_id}/approve")
async def approve_business(business_id: str, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not p:
        raise HTTPException(404, {"code": "business_not_found"})
    await db.marketplace_profiles.update_one(
        {"business_id": business_id},
        {"$set": {"status": "approved", "approved_at": now(), "updated_at": now()}})
    await db.businesses.update_one(
        {"business_id": business_id}, {"$set": {"active": True, "verified": True}})
    return {"ok": True, "status": "approved"}


@router.post("/businesses/{business_id}/reject")
async def reject_business(business_id: str, body: ApprovalBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    p = await db.marketplace_profiles.find_one({"business_id": business_id})
    if not p:
        raise HTTPException(404, {"code": "business_not_found"})
    await db.marketplace_profiles.update_one(
        {"business_id": business_id},
        {"$set": {"status": "rejected", "rejection_reason": body.reason,
                  "updated_at": now()}})
    return {"ok": True, "status": "rejected"}


@router.get("/dashboard")
async def dashboard(request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    prof = db.marketplace_profiles
    return {
        "businesses_total": await prof.count_documents({}),
        "pending": await prof.count_documents({"status": "pending"}),
        "approved": await prof.count_documents({"status": "approved"}),
        "rejected": await prof.count_documents({"status": "rejected"}),
        "categories": await db.marketplace_categories.count_documents({"active": True}),
        "example_point_cost_cents": await resolve_point_cost_cents(db),
        "example_commission": await resolve_commission(db, category="restaurant"),
    }


__all__ = ["router"]
