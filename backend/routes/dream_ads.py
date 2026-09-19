"""RadioLife Social V2 — ADVISOR ADVERTISING (Featured placement).

Approved advisors buy a Featured slot (Stripe hosted checkout, env-driven
test keys in preview). While active, the advisor is pinned + badged at the
top of the Advisors marketplace and/or the Live tab. Admin can edit tier
prices and stop any promotion.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user, require_admin

router = APIRouter(prefix="/api/social/ads", tags=["dream_ads"])
admin_router = APIRouter(prefix="/api/admin/dreams/ads", tags=["dream_ads_admin"])

DEFAULT_TIERS = [
    {"key": "day", "days": 1, "price_cents": 2999, "label": "1 day"},
    {"key": "week", "days": 7, "price_cents": 4999, "label": "7 days"},
    {"key": "month", "days": 30, "price_cents": 9999, "label": "30 days"},
]
SURFACES = ["advisors", "live", "both"]
SURFACE_LABELS = {"advisors": "Advisors tab", "live": "Live tab",
                  "both": "Advisors + Live"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _stripe():
    import stripe
    stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                      or os.environ.get("STRIPE_API_KEY") or "")
    return stripe


async def _tiers(db) -> list:
    cfg = await db.dream_ads_config.find_one({"_id": "config"})
    if cfg and cfg.get("tiers"):
        return cfg["tiers"]
    return DEFAULT_TIERS


async def _approved_advisor(db, uid: str) -> dict:
    a = await db.advisor_profiles.find_one({"user_id": uid, "status": "approved"})
    if not a:
        raise HTTPException(403, {"code": "not_an_advisor"})
    return a


async def _active_promo_for(db, advisor_id: str) -> Optional[dict]:
    return await db.advisor_promotions.find_one(
        {"advisor_id": advisor_id, "status": "active", "ends_at": {"$gt": _now()}})


async def active_featured_advisor_ids(db, surface: str) -> set:
    """Advisor ids with a live Featured promotion for `surface` (or 'both')."""
    ids: set = set()
    async for p in db.advisor_promotions.find(
            {"status": "active", "ends_at": {"$gt": _now()},
             "surface": {"$in": [surface, "both"]}}):
        ids.add(p["advisor_id"])
    return ids


def _promo_public(p: dict) -> dict:
    return {"promo_id": p["promo_id"], "advisor_id": p.get("advisor_id"),
            "advisor_name": p.get("advisor_name"), "tier": p.get("tier"),
            "days": p.get("days"), "surface": p.get("surface"),
            "surface_label": SURFACE_LABELS.get(p.get("surface")),
            "price_cents": p.get("price_cents"), "status": p.get("status"),
            "starts_at": _iso(p.get("starts_at")), "ends_at": _iso(p.get("ends_at")),
            "created_at": _iso(p.get("created_at"))}


async def ensure_ads_indexes(db) -> None:
    await db.advisor_promotions.create_index("promo_id", unique=True, name="promo_id")
    await db.advisor_promotions.create_index([("advisor_id", 1)], name="promo_adv")
    await db.advisor_promotions.create_index(
        [("status", 1), ("ends_at", 1)], name="promo_active")


# ───────────────────────────── Advisor ─────────────────────────────
@router.get("/config")
async def ads_config(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    tiers = await _tiers(db)
    adv = await db.advisor_profiles.find_one(
        {"user_id": user["user_id"], "status": "approved"})
    active = None
    if adv:
        p = await _active_promo_for(db, adv["advisor_id"])
        active = _promo_public(p) if p else None
    return {"tiers": tiers,
            "surfaces": [{"key": s, "label": SURFACE_LABELS[s]} for s in SURFACES],
            "is_advisor": bool(adv), "active_promotion": active,
            "note": "Featured placement pins you to the top with a badge. "
                    "It does not change reviews, ranking fairness or search results."}


class AdCheckoutBody(BaseModel):
    tier: str
    surface: str = "advisors"
    origin_url: Optional[str] = None


@router.post("/checkout")
async def ad_checkout(body: AdCheckoutBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    adv = await _approved_advisor(db, user["user_id"])
    tier = next((t for t in await _tiers(db) if t["key"] == body.tier), None)
    if not tier:
        raise HTTPException(400, {"code": "bad_tier"})
    surface = body.surface if body.surface in SURFACES else "advisors"
    pid = f"promo_{uuid.uuid4().hex[:16]}"
    price = int(tier["price_cents"])
    promo = {"_id": pid, "promo_id": pid, "advisor_id": adv["advisor_id"],
             "advisor_user_id": user["user_id"],
             "advisor_name": adv.get("display_name"),
             "tier": tier["key"], "days": int(tier["days"]), "surface": surface,
             "price_cents": price, "status": "pending_payment",
             "session_id": None, "starts_at": None, "ends_at": None,
             "created_at": _now()}
    stripe = _stripe()
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = (body.origin_url or os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd", "product_data": {
            "name": f"Featured placement — {tier['label']} ({SURFACE_LABELS[surface]})"},
            "unit_amount": price}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "dream_ad", "promo_id": pid,
                  "advisor_id": adv["advisor_id"]})
    promo["session_id"] = session.id
    await db.advisor_promotions.insert_one(promo)
    return {"ok": True, "promo_id": pid, "status": "pending_payment",
            "checkout_url": session.url}


@router.get("/status/{promo_id}")
async def ad_status(promo_id: str, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await db.advisor_promotions.find_one(
        {"promo_id": promo_id, "advisor_user_id": user["user_id"]})
    if not p:
        raise HTTPException(404, {"code": "promo_not_found"})
    if p["status"] == "pending_payment" and p.get("session_id"):
        try:
            sess = _stripe().checkout.Session.retrieve(p["session_id"])
            if sess.get("payment_status") == "paid" or sess.get("status") == "complete":
                starts = _now()
                ends = starts + timedelta(days=int(p.get("days", 7)))
                await db.advisor_promotions.update_one(
                    {"promo_id": promo_id},
                    {"$set": {"status": "active", "starts_at": starts,
                              "ends_at": ends}})
                p = await db.advisor_promotions.find_one({"promo_id": promo_id})
        except Exception:
            pass
    return _promo_public(p)


@router.get("/mine")
async def my_ads(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    items = [_promo_public(p) async for p in db.advisor_promotions.find(
        {"advisor_user_id": user["user_id"]}).sort("created_at", -1).limit(40)]
    return {"items": items}


# ═══════════════════════════ ADMIN ═════════════════════════════════
@admin_router.get("/config")
async def admin_ads_config(request: Request, user: dict = Depends(require_admin)):
    return {"tiers": await _tiers(request.app.state.db)}


class AdminTiersBody(BaseModel):
    tiers: list


@admin_router.patch("/config")
async def admin_set_tiers(body: AdminTiersBody, request: Request,
                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    clean = []
    for t in body.tiers:
        if not all(k in t for k in ("key", "days", "price_cents", "label")):
            raise HTTPException(400, {"code": "bad_tier"})
        clean.append({"key": str(t["key"]), "days": int(t["days"]),
                      "price_cents": int(t["price_cents"]), "label": str(t["label"])})
    await db.dream_ads_config.update_one(
        {"_id": "config"}, {"$set": {"tiers": clean, "updated_at": _now()}}, upsert=True)
    return {"ok": True, "tiers": clean}


@admin_router.get("/promotions")
async def admin_promotions(request: Request, status: Optional[str] = None,
                           user: dict = Depends(require_admin)):
    db = request.app.state.db
    q = {"status": status} if status else {}
    items = [_promo_public(p) async for p in
             db.advisor_promotions.find(q).sort("created_at", -1).limit(100)]
    return {"items": items}


@admin_router.post("/promotions/{promo_id}/stop")
async def admin_stop_promo(promo_id: str, request: Request,
                           user: dict = Depends(require_admin)):
    db = request.app.state.db
    r = await db.advisor_promotions.update_one(
        {"promo_id": promo_id}, {"$set": {"status": "stopped", "ends_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, {"code": "promo_not_found"})
    return {"ok": True}


__all__ = ["router", "admin_router", "ensure_ads_indexes",
           "active_featured_advisor_ids"]
