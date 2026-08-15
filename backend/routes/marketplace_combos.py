"""Merchant-defined 'make it a meal' combos. A combo bundles category
requirements (e.g. 1 Pizza + 1 Drink) for a fixed price; the discount is
applied automatically in marketplace_orders._price_menu."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user

router = APIRouter(prefix="/api/merchant/marketplace/combos", tags=["marketplace-combos"])


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


def _clean(c: Dict[str, Any]) -> Dict[str, Any]:
    c.pop("_id", None)
    v = c.get("created_at")
    if hasattr(v, "isoformat"):
        c["created_at"] = v.isoformat()
    return c


class ComboReq(BaseModel):
    category: str = Field(..., min_length=1, max_length=60)
    qty: int = Field(1, ge=1, le=10)


class ComboBody(BaseModel):
    combo_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=80)
    price_cents: int = Field(..., ge=0, le=1_000_000)
    requirements: List[ComboReq] = Field(..., min_length=1, max_length=4)
    active: bool = True


@router.get("")
async def list_combos(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    combos = [_clean(c) async for c in
              db.marketplace_combos.find({"business_id": p["business_id"]}).sort("created_at", -1)]
    return {"items": combos}


@router.post("")
async def upsert_combo(body: ComboBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    reqs = [r.model_dump() for r in body.requirements]
    if body.combo_id:
        await db.marketplace_combos.update_one(
            {"combo_id": body.combo_id, "business_id": p["business_id"]},
            {"$set": {"name": body.name, "price_cents": body.price_cents,
                      "requirements": reqs, "active": body.active}})
        cid = body.combo_id
    else:
        cid = f"combo_{uuid.uuid4().hex[:10]}"
        await db.marketplace_combos.insert_one({
            "combo_id": cid, "business_id": p["business_id"], "name": body.name,
            "price_cents": body.price_cents, "requirements": reqs, "active": body.active,
            "created_at": datetime.now(timezone.utc)})
    saved = await db.marketplace_combos.find_one({"combo_id": cid})
    return {"ok": True, "combo": _clean(saved)}


@router.delete("/{combo_id}")
async def delete_combo(combo_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    await db.marketplace_combos.delete_one({"combo_id": combo_id, "business_id": p["business_id"]})
    return {"ok": True}


__all__ = ["router"]
