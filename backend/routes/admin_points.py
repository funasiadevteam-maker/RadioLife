"""Phase F-1 — Admin points endpoints.

All routes require admin role.  Mounted under `/api/admin/points/*`.

Operations:
    GET    /api/admin/points/ledger          — paginated ledger browser
    POST   /api/admin/points/grant             — direct grant (caps bypassed)
    POST   /api/admin/points/reverse         — compensating row for an entry
    POST   /api/admin/points/reconcile      — ledger ↔ legacy diff per user
    GET    /api/admin/points/earn-rules    — rules list
    PATCH /api/admin/points/earn-rules/{rule_id} — tweak caps/base/enabled
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.points_service import (
    PointsService, _serialize, DEFAULT_RULES,
)

router = APIRouter(prefix="/api/admin/points", tags=["admin-points"])
log = logging.getLogger("bigfm.points.admin_routes")


async def _require_admin(request: Request) -> dict:
    from auth import current_user
    user = await current_user(request)
    if (user.get("role") or "").lower() != "admin":
        raise HTTPException(403, {"code": "admin_required"})
    return user


# ─── Schemas ──────────────────────────────────────────────────────
class GrantBody(BaseModel):
    user_id: str
    delta: int
    reason: Optional[str] = None
    source: str = "admin_grant"


class ReverseBody(BaseModel):
    entry_id: str
    reason: str


class EarnRulePatch(BaseModel):
    base_points:                    Optional[int]  = None
    daily_cap_per_user:        Optional[int]  = None
    weekly_cap_per_user:       Optional[int]  = None
    monthly_cap_per_user: Optional[int] = None
    enabled:                              Optional[bool] = None
    label:                                  Optional[str]  = None


# ─── Routes ───────────────────────────────────────────────────────
@router.get("/ledger")
async def get_ledger(request: Request,
                                          user_id: Optional[str] = Query(None),
                                          source: Optional[str] = Query(None),
                                          from_iso: Optional[str] = Query(None, alias="from"),
                                          to_iso:   Optional[str] = Query(None, alias="to"),
                                          limit:     int = Query(100, ge=1, le=500),
                                          cursor:   Optional[str] = Query(None)):
    await _require_admin(request)
    db = request.app.state.db
    q: dict = {}
    if user_id: q["user_id"] = user_id
    if source:  q["source"]  = source
    time_q: dict = {}
    for label, iso in (("$gte", from_iso), ("$lte", to_iso)):
        if iso:
            try:
                time_q[label] = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(400, {"code": "bad_iso", "field": label})
    if time_q:
        q["created_at"] = time_q
    if cursor:
        try:
            cur_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            q.setdefault("created_at", {})["$lt"] = cur_dt
        except ValueError:
            pass
    rows = []
    async for r in db.points_ledger.find(q).sort(
                              "created_at", -1).limit(limit + 1):
        rows.append(_serialize(r))
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["created_at"]
        rows = rows[:limit]
    return {"items": rows, "next_cursor": next_cursor, "count": len(rows)}


@router.post("/grant")
async def admin_grant(request: Request, body: GrantBody):
    admin = await _require_admin(request)
    db = request.app.state.db
    if body.delta == 0:
        raise HTTPException(400, {"code": "zero_delta"})
    target = await db.users.find_one({"user_id": body.user_id},
                                                                      {"user_id": 1, "_id": 0})
    if not target:
        raise HTTPException(404, {"code": "user_not_found"})
    svc = PointsService(db)
    res = await svc.award(
        user_id=body.user_id,
        source=body.source or "admin_grant",
        source_id=None,
        delta=int(body.delta),
        metadata={"reason": body.reason,
                          "granted_by": admin.get("user_id"),
                          "via": "admin_grant_endpoint"},
        enforce_caps=False,
    )
    if not res.ok:
        raise HTTPException(409, {"code": res.reason})
    return res.to_dict()


@router.post("/reverse")
async def admin_reverse(request: Request, body: ReverseBody):
    admin = await _require_admin(request)
    db = request.app.state.db
    res = await PointsService(db).reverse(
        entry_id=body.entry_id, reason=body.reason,
        admin_user_id=admin.get("user_id"))
    if not res.ok:
        raise HTTPException(404 if res.reason == "not_found" else 409,
                                                  {"code": res.reason})
    return res.to_dict()


@router.post("/reconcile")
async def admin_reconcile(request: Request,
                                                      user_id: str = Query(...)):
    await _require_admin(request)
    db = request.app.state.db
    return await PointsService(db).reconcile(user_id)


@router.get("/earn-rules")
async def list_earn_rules(request: Request):
    await _require_admin(request)
    db = request.app.state.db
    rows = []
    async for r in db.points_earn_rules.find({}).sort("rule_id", 1):
        r["_id"] = str(r.get("_id"))
        for k in ("updated_at", "created_at"):
            v = r.get(k)
            if isinstance(v, datetime):
                r[k] = v.isoformat()
        rows.append(r)
    return {"items": rows, "count": len(rows),
                      "default_seed": [r["rule_id"] for r in DEFAULT_RULES]}


@router.patch("/earn-rules/{rule_id}")
async def patch_earn_rule(rule_id: str, request: Request,
                                                          body: EarnRulePatch):
    await _require_admin(request)
    db = request.app.state.db
    rule = await db.points_earn_rules.find_one({"rule_id": rule_id})
    if not rule:
        raise HTTPException(404, {"code": "rule_not_found"})
    update = {k: v for k, v in body.dict().items() if v is not None}
    if not update:
        raise HTTPException(400, {"code": "empty_patch"})
    update["updated_at"] = datetime.now(timezone.utc)
    await db.points_earn_rules.update_one(
        {"rule_id": rule_id}, {"$set": update})
    r = await db.points_earn_rules.find_one({"rule_id": rule_id})
    r["_id"] = str(r.get("_id"))
    for k in ("updated_at", "created_at"):
        v = r.get(k)
        if isinstance(v, datetime):
            r[k] = v.isoformat()
    return r
