"""Phase RWD.4 — Merchant ops: Sponsored Bonus windows + Fraud Alerts.

Platform-agnostic (web + mobile share the contract).

Sponsored Bonuses — a business sponsors a time-boxed "N× points" window at
its venue (e.g. "2× points tonight at The Grill House"). While active, the
multiplier is applied to that merchant's scan-earn awards, and the offer is
surfaced in the consumer Earn loop.

Fraud Alerts — when a merchant's coupon show-vs-scan (redeem) gap crosses a
configurable threshold, an alert is auto-created so admins get notified of
possible off-book discounting. Alerts are (re)computed opportunistically on
show/redeem events and via an admin scan.

Exports (imported by rewards_merchant.scan_earn + rewards_earn.overview):
  active_bonus_windows(db, merchant_id=None)
  active_bonus_multiplier(db, merchant_id)
  maybe_alert(db, merchant_id)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin

router = APIRouter(tags=["merchant-ops"])

FRAUD_DEFAULTS = {"_id": "fraud", "min_shows": 5, "flag_rate": 0.5, "min_unredeemed": 5}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def _parse_dt(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


# ─────────────────────── Sponsored Bonus windows ───────────────────────
async def active_bonus_windows(db, merchant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    now = _now()
    q: Dict[str, Any] = {"active": True, "starts_at": {"$lte": now}, "ends_at": {"$gte": now}}
    if merchant_id:
        q["merchant_id"] = merchant_id
    out: List[Dict[str, Any]] = []
    async for w in db.bonus_windows.find(q).sort("multiplier", -1):
        w.pop("_id", None)
        out.append(w)
    return out


async def active_bonus_multiplier(db, merchant_id: Optional[str]) -> float:
    if not merchant_id:
        return 1.0
    wins = await active_bonus_windows(db, merchant_id)
    return max([float(w.get("multiplier", 1.0)) for w in wins], default=1.0)


class BonusWindowBody(BaseModel):
    merchant_id: str
    multiplier: float = Field(2.0, ge=1.0, le=10.0)
    title: Optional[str] = None
    sponsor_name: Optional[str] = None
    starts_at: str                      # ISO 8601
    ends_at: str                        # ISO 8601
    market: Optional[str] = None


@router.get("/api/admin/bonus-windows")
async def list_bonus_windows(request: Request, _admin=Depends(require_admin),
                             active_only: bool = False):
    db = request.app.state.db
    if active_only:
        return {"items": await active_bonus_windows(db)}
    out = []
    async for w in db.bonus_windows.find({}).sort("starts_at", -1):
        w.pop("_id", None)
        out.append(w)
    return {"items": out, "total": len(out)}


@router.post("/api/admin/bonus-windows")
async def create_bonus_window(body: BonusWindowBody, request: Request,
                              _admin=Depends(require_admin)):
    db = request.app.state.db
    starts, ends = _parse_dt(body.starts_at), _parse_dt(body.ends_at)
    doc = {
        "window_id": f"bw_{uuid.uuid4().hex[:12]}",
        "merchant_id": body.merchant_id,
        "multiplier": float(body.multiplier),
        "title": body.title or f"{body.multiplier:g}× points",
        "sponsor_name": body.sponsor_name,
        "starts_at": starts, "ends_at": ends, "market": body.market,
        "active": True, "created_at": _now(),
    }
    await db.bonus_windows.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.post("/api/admin/bonus-windows/{window_id}/deactivate")
async def deactivate_bonus_window(window_id: str, request: Request,
                                  _admin=Depends(require_admin)):
    await request.app.state.db.bonus_windows.update_one(
        {"window_id": window_id}, {"$set": {"active": False, "updated_at": _now()}})
    return {"ok": True, "window_id": window_id}


@router.get("/api/me/earn/bonus-windows")
async def my_bonus_windows(request: Request, user: dict = Depends(current_user)):
    return {"items": await active_bonus_windows(request.app.state.db)}


# ─────────────────────────── Fraud Alerts ───────────────────────────
async def _fraud_config(db) -> Dict[str, Any]:
    cfg = await db.fraud_config.find_one({"_id": "fraud"})
    if not cfg:
        await db.fraud_config.insert_one(dict(FRAUD_DEFAULTS))
        cfg = dict(FRAUD_DEFAULTS)
    return cfg


async def _merchant_gap(db, merchant_id: str) -> Dict[str, Any]:
    shows = await db.coupon_show_events.count_documents({"merchant_id": merchant_id})
    reds = await db.coupon_show_events.count_documents(
        {"merchant_id": merchant_id, "redeemed": True})
    rate = round(reds / shows, 3) if shows else 0.0
    return {"merchant_id": merchant_id, "shows": shows, "redemptions": reds,
            "unredeemed": shows - reds, "redemption_rate": rate}


def _crosses(gap: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    return (gap["shows"] >= int(cfg["min_shows"])
            and gap["redemption_rate"] < float(cfg["flag_rate"])
            and gap["unredeemed"] >= int(cfg["min_unredeemed"]))


async def maybe_alert(db, merchant_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Auto-create/update a fraud alert if this merchant's gap crosses the
    threshold. Idempotent per merchant per day (keeps one open alert)."""
    if not merchant_id:
        return None
    cfg = await _fraud_config(db)
    gap = await _merchant_gap(db, merchant_id)
    if not _crosses(gap, cfg):
        return None
    existing = await db.fraud_alerts.find_one(
        {"merchant_id": merchant_id, "status": "open"})
    threshold = {"min_shows": cfg["min_shows"], "flag_rate": cfg["flag_rate"],
                 "min_unredeemed": cfg["min_unredeemed"]}
    if existing:
        await db.fraud_alerts.update_one(
            {"_id": existing["_id"]},
            {"$set": {**gap, "threshold": threshold, "updated_at": _now()}})
        existing.update(gap)
        existing.pop("_id", None)
        return existing
    doc = {"alert_id": f"fa_{uuid.uuid4().hex[:12]}", **gap, "threshold": threshold,
           "status": "open", "created_date": _today(),
           "created_at": _now(), "updated_at": _now()}
    await db.fraud_alerts.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/api/admin/fraud-alerts")
async def list_fraud_alerts(request: Request, _admin=Depends(require_admin),
                            status: str = "open"):
    db = request.app.state.db
    q = {} if status == "all" else {"status": status}
    out = []
    async for a in db.fraud_alerts.find(q).sort("updated_at", -1):
        a.pop("_id", None)
        out.append(a)
    return {"items": out, "total": len(out), "status": status}


@router.post("/api/admin/fraud-alerts/scan")
async def scan_fraud_alerts(request: Request, _admin=Depends(require_admin)):
    """Recompute every merchant's gap and open alerts for any that cross."""
    db = request.app.state.db
    created = 0
    async for r in db.coupon_show_events.aggregate(
            [{"$group": {"_id": "$merchant_id"}}]):
        mid = r["_id"]
        if not mid:
            continue
        alert = await maybe_alert(db, mid)
        if alert:
            created += 1
    return {"ok": True, "merchants_flagged": created}


@router.post("/api/admin/fraud-alerts/{alert_id}/resolve")
async def resolve_fraud_alert(alert_id: str, request: Request,
                              _admin=Depends(require_admin)):
    await request.app.state.db.fraud_alerts.update_one(
        {"alert_id": alert_id},
        {"$set": {"status": "resolved", "resolved_at": _now(), "updated_at": _now()}})
    return {"ok": True, "alert_id": alert_id}


class FraudConfigBody(BaseModel):
    min_shows: Optional[int] = None
    flag_rate: Optional[float] = None
    min_unredeemed: Optional[int] = None


@router.get("/api/admin/fraud-config")
async def get_fraud_config(request: Request, _admin=Depends(require_admin)):
    cfg = await _fraud_config(request.app.state.db)
    cfg.pop("_id", None)
    return cfg


@router.put("/api/admin/fraud-config")
async def put_fraud_config(body: FraudConfigBody, request: Request,
                           _admin=Depends(require_admin)):
    db = request.app.state.db
    await _fraud_config(db)
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.fraud_config.update_one({"_id": "fraud"}, {"$set": updates})
    cfg = await _fraud_config(db)
    cfg.pop("_id", None)
    return cfg
