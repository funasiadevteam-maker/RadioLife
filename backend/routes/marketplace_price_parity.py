"""Price Parity Monitor (admin) — flags venues whose in-app prices drift from
the restaurant's own ('direct') price. The direct reference can be set by the
merchant (on the item) OR overridden by an admin here (admin wins)."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from auth import require_admin
from services.marketplace import now

router = APIRouter(prefix="/api/admin/marketplace/price-parity", tags=["admin-price-parity"])

FLAG_TOLERANCE_PCT = 3.0  # drift at/above this is flagged


class OverrideBody(BaseModel):
    ref_type: str = Field(..., pattern="^(menu|product)$")
    ref_id: str
    direct_price_cents: Optional[int] = Field(None, ge=0, le=10_000_000)
    note: Optional[str] = Field(None, max_length=280)


async def _biz_names(db) -> Dict[str, str]:
    names: Dict[str, str] = {}
    async for p in db.marketplace_profiles.find({}, {"business_id": 1, "public_name": 1}):
        names[p["business_id"]] = p.get("public_name") or p["business_id"]
    return names


@router.get("")
async def parity_report(request: Request, only_flagged: bool = False,
                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    names = await _biz_names(db)
    overrides: Dict[str, Dict[str, Any]] = {}
    async for o in db.price_parity_overrides.find({}):
        overrides[o["ref"]] = o

    rows: List[Dict[str, Any]] = []
    async for it in db.menu_items.find({}):
        ov = overrides.get(f"menu:{it['item_id']}")
        direct = ov.get("direct_price_cents") if ov else it.get("direct_price_cents")
        r = {"ref_type": "menu", "ref_id": it["item_id"], "business_id": it.get("business_id"),
             "business_name": names.get(it.get("business_id"), it.get("business_id")),
             "name": it.get("name"), "app_price_cents": int(it.get("price_cents", 0)),
             "direct_price_cents": (int(direct) if direct is not None else None),
             "source": "admin" if (ov and ov.get("direct_price_cents") is not None) else "merchant",
             "note": ov.get("note") if ov else None}
        rows.append(r)
    async for p in db.products.find({}):
        ov = overrides.get(f"product:{p['product_id']}")
        direct = ov.get("direct_price_cents") if ov else p.get("direct_price_cents")
        r = {"ref_type": "product", "ref_id": p["product_id"], "business_id": p.get("business_id"),
             "business_name": names.get(p.get("business_id"), p.get("business_id")),
             "name": p.get("name"), "app_price_cents": int(p.get("price_cents", 0)),
             "direct_price_cents": (int(direct) if direct is not None else None),
             "source": "admin" if (ov and ov.get("direct_price_cents") is not None) else "merchant",
             "note": ov.get("note") if ov else None}
        rows.append(r)

    flagged = 0
    for r in rows:
        d = r["direct_price_cents"]
        if d is None or d == 0:
            r["drift_pct"] = None
            r["flagged"] = False
            continue
        drift = round((r["app_price_cents"] - d) / d * 100, 1)
        r["drift_pct"] = drift
        r["flagged"] = abs(drift) >= FLAG_TOLERANCE_PCT
        if r["flagged"]:
            flagged += 1

    rows.sort(key=lambda x: (x["drift_pct"] is None, -abs(x["drift_pct"] or 0)))
    if only_flagged:
        rows = [r for r in rows if r["flagged"]]
    tracked = sum(1 for r in rows if r["direct_price_cents"] not in (None, 0))
    return {"items": rows, "flagged_count": flagged, "tracked_count": tracked,
            "total": len(rows), "tolerance_pct": FLAG_TOLERANCE_PCT}


@router.post("/override")
async def set_override(body: OverrideBody, request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    ref = f"{body.ref_type}:{body.ref_id}"
    if body.direct_price_cents is None:
        await db.price_parity_overrides.delete_one({"ref": ref})
        return {"ok": True, "cleared": True}
    await db.price_parity_overrides.update_one(
        {"ref": ref},
        {"$set": {"ref": ref, "ref_type": body.ref_type, "ref_id": body.ref_id,
                  "direct_price_cents": int(body.direct_price_cents), "note": body.note,
                  "set_by": admin.get("user_id"), "updated_at": now()}}, upsert=True)
    return {"ok": True}


__all__ = ["router"]
