"""Marketplace Tax Rules — admin CRUD for jurisdiction-based sales tax + an
AI helper to pre-fill a typical rate. Origin-based (store location) rates are
applied to orders in marketplace_orders."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_admin
from services.tax_service import new_tax_id, norm_key, ai_estimate_rate, _now

router = APIRouter(prefix="/api/admin/tax", tags=["marketplace-tax"])


def _clean(r: Dict[str, Any]) -> Dict[str, Any]:
    r.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = r.get(k)
        if hasattr(v, "isoformat"):
            r[k] = v.isoformat()
    return r


class TaxRuleBody(BaseModel):
    country: str = Field(..., min_length=1, max_length=60)
    state: Optional[str] = Field(None, max_length=60)
    county: Optional[str] = Field(None, max_length=80)
    city: Optional[str] = Field(None, max_length=80)
    rate_percent: float = Field(..., ge=0, le=40)
    label: Optional[str] = Field(None, max_length=100)
    active: bool = True


def _doc(body: TaxRuleBody) -> Dict[str, Any]:
    return {
        "country": body.country.strip(), "state": (body.state or None),
        "county": (body.county or None), "city": (body.city or None),
        "country_key": norm_key(body.country), "state_key": norm_key(body.state),
        "county_key": norm_key(body.county), "city_key": norm_key(body.city),
        "rate_percent": float(body.rate_percent),
        "label": (body.label or "").strip() or None, "active": bool(body.active),
    }


@router.get("/rules")
async def list_rules(request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    rules = [_clean(r) async for r in db.tax_rules.find().sort([("country_key", 1), ("rate_percent", -1)])]
    return {"items": rules, "count": len(rules)}


@router.post("/rules")
async def create_rule(body: TaxRuleBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    rid = new_tax_id()
    doc = {"rule_id": rid, **_doc(body), "created_at": _now(), "updated_at": _now()}
    await db.tax_rules.insert_one(dict(doc))
    return {"ok": True, "rule": _clean(doc)}


@router.patch("/rules/{rule_id}")
async def update_rule(rule_id: str, body: TaxRuleBody, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    r = await db.tax_rules.find_one({"rule_id": rule_id})
    if not r:
        raise HTTPException(404, {"code": "rule_not_found"})
    await db.tax_rules.update_one({"rule_id": rule_id}, {"$set": {**_doc(body), "updated_at": _now()}})
    saved = await db.tax_rules.find_one({"rule_id": rule_id})
    return {"ok": True, "rule": _clean(saved)}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    res = await db.tax_rules.delete_one({"rule_id": rule_id})
    if not res.deleted_count:
        raise HTTPException(404, {"code": "rule_not_found"})
    return {"ok": True}


class AiEstimateBody(BaseModel):
    country: str = Field(..., min_length=1)
    state: Optional[str] = None
    county: Optional[str] = None
    city: Optional[str] = None


@router.post("/ai-estimate")
async def ai_estimate(body: AiEstimateBody, request: Request, _a=Depends(require_admin)):
    """Pre-fill a typical combined rate via AI. The admin reviews & saves it as
    a rule — merchants remain responsible for filing/remitting."""
    try:
        est = await ai_estimate_rate(body.country, body.state, body.county, body.city)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, {"code": "ai_unavailable", "message": str(e)[:200]})
    return {"ok": True, **est,
            "disclaimer": "AI estimate for convenience only. Verify against local law; you must file and remit."}


__all__ = ["router"]
