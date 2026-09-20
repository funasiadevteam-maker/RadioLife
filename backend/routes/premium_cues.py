"""Phase RWD.3 — Premium Cues (admin-configurable benefits + value calc).

Platform-agnostic. Premium entitlement is read from the existing
`users.is_premium` flag (granted by billing_service). This module only
adds the CONFIG + CUE + VALUE surface; it does NOT handle billing.

Listener:
  GET /api/me/premium/status   — is_premium + enabled benefits + honest
                                  personalized value (this-month numbers)
  GET /api/premium/benefits    — enabled benefits + pricing (comparison)

Admin (tunable — nothing hardcoded in clients):
  GET/PUT /api/admin/premium/config
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from auth import current_user, require_admin

router = APIRouter(tags=["premium-cues"])

DEFAULT_CONFIG: Dict[str, Any] = {
    "_id": "config",
    "points_multiplier": 1.5,       # 1.0 == disabled
    "trial_days": 7,                # 0 == no trial
    "monthly_price": 4.99,
    "annual_price": 39.99,
    "currency": "USD",
    "benefits": [
        {"key": "ad_free_audio", "title": "No FUUSIC platform audio ads",
         "category": "core", "enabled": True},
        {"key": "ad_free_display", "title": "No FUUSIC platform display ads",
         "category": "core", "enabled": True},
        {"key": "premium_badge", "title": "Premium profile badge",
         "category": "core", "enabled": True},
        {"key": "points_multiplier", "title": "Boosted reward multiplier",
         "category": "rewards", "enabled": True},
        {"key": "monthly_bonus_points", "title": "Monthly bonus points",
         "category": "rewards", "enabled": True},
        {"key": "exclusive_rewards", "title": "Premium-only rewards",
         "category": "rewards", "enabled": True},
        {"key": "premium_ai_personas", "title": "Premium AI RJ personas",
         "category": "ai", "enabled": True},
        {"key": "more_ai_presets", "title": "More AI station personalization",
         "category": "ai", "enabled": True},
        {"key": "extra_game_entries", "title": "Extra daily game entries",
         "category": "games", "enabled": True},
        {"key": "premium_podcasts", "title": "Exclusive & early podcasts",
         "category": "podcasts", "enabled": True},
    ],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start() -> datetime:
    return _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _get_config(db) -> Dict[str, Any]:
    cfg = await db.premium_config.find_one({"_id": "config"})
    if not cfg:
        await db.premium_config.insert_one(dict(DEFAULT_CONFIG))
        cfg = dict(DEFAULT_CONFIG)
    return cfg


async def _month_points_earned(db, uid: str, exclude_sources: Optional[List[str]] = None) -> int:
    match = {"user_id": uid, "delta": {"$gt": 0},
             "created_at": {"$gte": _month_start()}}
    if exclude_sources:
        match["source"] = {"$nin": exclude_sources}
    pipe = [{"$match": match},
            {"$group": {"_id": None, "t": {"$sum": "$delta"}}}]
    async for d in db.points_ledger.aggregate(pipe):
        return int(d.get("t") or 0)
    return 0


@router.get("/api/premium/benefits")
async def premium_benefits(request: Request):
    cfg = await _get_config(request.app.state.db)
    benefits = [b for b in cfg.get("benefits", []) if b.get("enabled", True)]
    return {
        "benefits": benefits,
        "points_multiplier": cfg.get("points_multiplier", 1.0),
        "trial_days": cfg.get("trial_days", 0),
        "monthly_price": cfg.get("monthly_price"),
        "annual_price": cfg.get("annual_price"),
        "currency": cfg.get("currency", "USD"),
    }


@router.get("/api/me/premium/status")
async def premium_status(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    cfg = await _get_config(db)
    is_premium = bool(user.get("is_premium"))
    mult = float(cfg.get("points_multiplier", 1.0))
    month_earned = await _month_points_earned(db, user["user_id"])
    # HONEST value: the multiplier realistically applies to base earning, NOT
    # to reward payouts (mission/premium bonuses) — exclude those from the base
    # so the estimate doesn't compound on itself.
    base_earned = await _month_points_earned(
        db, user["user_id"], exclude_sources=["mission_reward", "premium_bonus"])
    bonus_estimate = int(round(base_earned * (mult - 1))) if mult > 1 else 0
    benefits = [b for b in cfg.get("benefits", []) if b.get("enabled", True)]
    return {
        "is_premium": is_premium,
        "points_multiplier": mult,
        "trial_days": cfg.get("trial_days", 0),
        "monthly_price": cfg.get("monthly_price"),
        "annual_price": cfg.get("annual_price"),
        "currency": cfg.get("currency", "USD"),
        "benefits": benefits,
        "value": {
            "month_points_earned": month_earned,
            "premium_bonus_points_estimate": bonus_estimate,
            "multiplier_active": mult > 1,
        },
    }


@router.get("/api/admin/premium/config")
async def admin_get_premium(request: Request, _admin=Depends(require_admin)):
    cfg = await _get_config(request.app.state.db)
    cfg.pop("_id", None)
    return cfg


class PremiumConfigBody(BaseModel):
    points_multiplier: Optional[float] = None
    trial_days: Optional[int] = None
    monthly_price: Optional[float] = None
    annual_price: Optional[float] = None
    currency: Optional[str] = None
    benefits: Optional[List[Dict[str, Any]]] = None


@router.put("/api/admin/premium/config")
async def admin_put_premium(body: PremiumConfigBody, request: Request,
                            _admin=Depends(require_admin)):
    db = request.app.state.db
    await _get_config(db)
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.premium_config.update_one({"_id": "config"}, {"$set": updates})
    cfg = await _get_config(db)
    cfg.pop("_id", None)
    return cfg
