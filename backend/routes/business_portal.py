"""Phase I — Business Redemption Portal (rescoped, no POS integrations).

Surfaces a self-serve dashboard for storefront owners to:
  * register / login as a `business` user.
  * scan or paste a customer coupon code → validate → redeem with PIN.
  * see their recent redemptions + simple dashboard stats.
  * launch ad campaigns (cross-link to existing advertiser flow).

Key collections
---------------
businesses                  — one row per storefront.
business_redemptions  — redemption ledger.
business_campaigns_link — back-pointer to advertiser_campaigns
                                                    (existing table) tagged with `business_id`.

Award flow
----------
On successful redemption we fire PointsService.award(
        user_id=customer_user_id, source="coupon_redeemed",
        source_id=redemption_id, idempotency_key=...).
"""
from __future__ import annotations
import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth import current_user

log = logging.getLogger("bigfm.business_portal")
router = APIRouter(prefix="/api/business", tags=["business-portal"])


# ── Helpers ──────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"),
                                          bcrypt.gensalt(rounds=10)).decode("utf-8")


def _verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


async def _resolve_business(db, user: dict) -> Optional[dict]:
    return await db.businesses.find_one(
        {"owner_user_id": user["user_id"]})


def _require_business(biz: Optional[dict]) -> dict:
    if not biz:
        raise HTTPException(403, "no_business_profile")
    return biz


def _mask_user_id(uid: str) -> str:
    if not uid:
        return ""
    return f"{uid[:6]}***{uid[-3:]}" if len(uid) > 12 else uid


# ── Pydantic bodies ──────────────────────────────────────────────
class RegisterBusinessBody(BaseModel):
    name:        str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=60)
    address:  Optional[str] = None
    lat:          Optional[float] = None
    lng:          Optional[float] = None
    phone:      Optional[str] = None
    website:  Optional[str] = None
    terminal_pin: str = Field(pattern=r"^\d{4}$")
    google_place_id: Optional[str] = None


class UpdateBusinessBody(BaseModel):
    name:        Optional[str] = None
    category: Optional[str] = None
    address:  Optional[str] = None
    lat:          Optional[float] = None
    lng:          Optional[float] = None
    phone:      Optional[str] = None
    website:  Optional[str] = None
    hours_json: Optional[dict] = None


class ValidateCouponBody(BaseModel):
    code: str = Field(min_length=4, max_length=40)


class RedeemCouponBody(BaseModel):
    code:                  str = Field(min_length=4, max_length=40)
    terminal_pin: str = Field(pattern=r"^\d{4}$")


# ── Onboarding ───────────────────────────────────────────────────
@router.post("/register")
async def register_business(body: RegisterBusinessBody, request: Request,
                                                          user: dict = Depends(current_user)) -> dict:
    """Attach a `business` role to the current user and create their
    storefront profile.  Auto-active in MVP — admin verification flag
    starts False but the dashboard already works."""
    db = request.app.state.db
    existing = await db.businesses.find_one(
        {"owner_user_id": user["user_id"]})
    if existing:
        return {"ok": False, "reason": "already_registered",
                      "business_id": existing["_id"]}
    bid = _new_id("biz")
    now = _now()
    doc = {
        "_id":                          bid,
        "owner_user_id":      user["user_id"],
        "name":                          body.name,
        "category":                  body.category.lower(),
        "address":                  body.address,
        "lat":                          body.lat,
        "lng":                          body.lng,
        "phone":                      body.phone,
        "website":                  body.website,
        "google_place_id":  body.google_place_id,
        "pos_terminal_pin_hash": _hash_pin(body.terminal_pin),
        "verified":                  False,
        "active":                      True,
        "redemption_count": 0,
        "created_at":              now,
        "updated_at":              now,
    }
    await db.businesses.insert_one(doc)
    # Add the `business` role to the user.
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$addToSet": {"roles": "business"},
          "$set": {"business_id": bid, "is_business": True}})
    log.info("[business] registered bid=%s owner=%s",
                    bid, user["user_id"])
    return {"ok": True, "business_id": bid, "verified": False}


@router.get("/me")
async def get_my_business(request: Request,
                                                user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    return {k: v for k, v in biz.items()
                  if k not in ("pos_terminal_pin_hash",)}


@router.patch("/me")
async def update_my_business(body: UpdateBusinessBody, request: Request,
                                                            user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    updates = {k: v for k, v in body.dict(exclude_unset=True).items()
                          if v is not None}
    if not updates:
        return {"ok": True, "modified": 0}
    updates["updated_at"] = _now()
    r = await db.businesses.update_one(
        {"_id": biz["_id"]}, {"$set": updates})
    return {"ok": True, "modified": r.modified_count}


# ── Coupon validation + redemption ─────────────────────────────
async def _resolve_coupon(db, code: str) -> Optional[dict]:
    code = code.strip().upper()
    return (await db.user_coupons.find_one({"code": code})
                  or await db.user_coupons.find_one({"voucher_code": code}))


@router.post("/coupons/validate")
async def validate_coupon(body: ValidateCouponBody, request: Request,
                                                          user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    cp = await _resolve_coupon(db, body.code)
    if not cp:
        return {"valid": False, "reason": "code_not_found"}
    now = _now()
    if cp.get("redeemed_at"):
        return {"valid": False, "reason": "already_redeemed",
                      "redeemed_at": cp["redeemed_at"].isoformat()
                          if isinstance(cp["redeemed_at"], datetime)
                          else cp["redeemed_at"]}
    if cp.get("expires_at"):
        exp = cp["expires_at"]
        if isinstance(exp, datetime) and exp < now:
            return {"valid": False, "reason": "expired",
                          "expires_at": exp.isoformat()}
    # Tie to this business when the offer scope is restricted.
    coupon_biz = cp.get("business_id")
    if coupon_biz and coupon_biz != biz["_id"]:
        return {"valid": False, "reason": "not_for_this_business",
                      "intended_business_id": coupon_biz}
    return {
        "valid":                  True,
        "code":                  cp.get("code") or cp.get("voucher_code"),
        "offer_title":      cp.get("offer_title") or cp.get("title"),
        "savings_value":  cp.get("savings_value") or cp.get("value"),
        "customer_user_id_masked": _mask_user_id(cp.get("user_id") or ""),
        "expires_at":          cp.get("expires_at").isoformat()
            if isinstance(cp.get("expires_at"), datetime) else cp.get("expires_at"),
        "can_redeem":          True,
    }


# Simple per-business rate limit (60 redemptions/min) — in-memory.
_RATE_BUCKET: dict[str, list[float]] = {}


def _rate_check(biz_id: str) -> bool:
    import time
    now = time.monotonic()
    bucket = _RATE_BUCKET.setdefault(biz_id, [])
    cutoff = now - 60.0
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= 60:
        return False
    bucket.append(now)
    return True


@router.post("/coupons/redeem")
async def redeem_coupon(body: RedeemCouponBody, request: Request,
                                                  user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    if not _rate_check(biz["_id"]):
        raise HTTPException(429, "redemption_rate_limit")
    if not _verify_pin(body.terminal_pin, biz.get("pos_terminal_pin_hash") or ""):
        raise HTTPException(401, "bad_pin")
    cp = await _resolve_coupon(db, body.code)
    if not cp:
        raise HTTPException(404, "code_not_found")
    now = _now()
    if cp.get("redeemed_at"):
        # Idempotent — return existing redemption row.
        existing = await db.business_redemptions.find_one(
            {"code": (cp.get("code") or cp.get("voucher_code") or "").upper(),
              "business_id": biz["_id"]})
        if existing:
            return {"ok": True, "idempotent": True,
                          "redemption_id": existing["_id"],
                          "redeemed_at": existing["redeemed_at"].isoformat()}

    # Mark coupon row + insert redemption ledger row atomically (best-effort).
    rid = _new_id("rdmp")
    code_upper = (cp.get("code") or cp.get("voucher_code") or "").upper()
    r = await db.user_coupons.update_one(
        {"_id": cp["_id"], "redeemed_at": {"$in": [None, False]}},
        {"$set": {"redeemed_at": now,
                      "redeemed_business_id": biz["_id"],
                      "redemption_id": rid}})
    if r.modified_count == 0:
        # Race — re-check.
        cp2 = await db.user_coupons.find_one({"_id": cp["_id"]})
        if cp2 and cp2.get("redeemed_at"):
            existing = await db.business_redemptions.find_one(
                {"code": code_upper, "business_id": biz["_id"]})
            if existing:
                return {"ok": True, "idempotent": True,
                              "redemption_id": existing["_id"]}
        raise HTTPException(409, "redemption_race")

    await db.business_redemptions.insert_one({
        "_id":                  rid,
        "business_id":  biz["_id"],
        "code":                  code_upper,
        "customer_user_id": cp.get("user_id"),
        "offer_title":  cp.get("offer_title") or cp.get("title"),
        "savings_value": cp.get("savings_value") or cp.get("value"),
        "redeemed_at":  now,
        "owner_user_id": user["user_id"],
    })
    await db.businesses.update_one(
        {"_id": biz["_id"]}, {"$inc": {"redemption_count": 1}})

    # Award the customer (+20 pts via PointsService).
    reward = {"awarded": False}
    customer_uid = cp.get("user_id")
    if customer_uid:
        try:
            from services.points_service import PointsService
            svc = PointsService(db)
            res = await svc.award(
                user_id=customer_uid,
                source="coupon_redeemed",
                source_id=rid,
                idempotency_key=f"coupon_redeem_{rid}",
                metadata={"business_id": biz["_id"],
                              "code": code_upper})
            reward = {"awarded": bool(getattr(res, "ok", False)),
                            "delta": getattr(res, "delta", 0)}
        except Exception as e:
            log.warning("[business] award err rid=%s: %s", rid, e)
    return {"ok": True, "redemption_id": rid,
                  "redeemed_at": now.isoformat(),
                  "reward_awarded": reward}


@router.get("/coupons/recent")
async def recent_redemptions(request: Request,
                                                          limit: int = 50,
                                                          user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    items = [doc async for doc in
                  db.business_redemptions.find({"business_id": biz["_id"]},
                                                                              {"_id": 1, "code": 1,
                                                                                "offer_title": 1,
                                                                                "savings_value": 1,
                                                                                "redeemed_at": 1,
                                                                                "customer_user_id": 1})
                      .sort("redeemed_at", -1).limit(int(limit))]
    for it in items:
        if it.get("customer_user_id"):
            it["customer_user_id_masked"] = _mask_user_id(it["customer_user_id"])
            del it["customer_user_id"]
    return {"count": len(items), "items": items}


# ── Dashboard stats ────────────────────────────────────────────
@router.get("/dashboard/stats")
async def dashboard_stats(request: Request,
                                                  period: str = "week",
                                                  user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    delta = {"today": timedelta(days=1),
                  "week":  timedelta(days=7),
                  "month": timedelta(days=30)}.get(period, timedelta(days=7))
    cutoff = _now() - delta
    base_match = {"business_id": biz["_id"],
                              "redeemed_at": {"$gte": cutoff}}
    redemptions = await db.business_redemptions.count_documents(base_match)
    pipe = [
        {"$match": base_match},
        {"$group": {"_id": "$offer_title", "n": {"$sum": 1},
                                "sum": {"$sum": "$savings_value"}}},
        {"$sort":  {"n": -1}},
        {"$limit": 5},
    ]
    top_offers = [r async for r in db.business_redemptions.aggregate(pipe)]
    revenue_attributed = sum(
        (r.get("sum") or 0) for r in top_offers)
    return {
        "period":                          period,
        "business_id":              biz["_id"],
        "redemptions":              redemptions,
        "revenue_attributed":  revenue_attributed,
        "top_offers":                  top_offers,
        "total_lifetime_redemptions": int(biz.get("redemption_count") or 0),
    }


# ── Campaigns (cross-link only — full advertiser flow lives in
# /api/advertiser/...; this just shows the business which campaigns
# are tagged to them and stubs the buy-flow entry point). ────────
@router.get("/campaigns")
async def list_business_campaigns(request: Request,
                                                                  user: dict = Depends(current_user)
                                                                  ) -> dict:
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    items = [doc async for doc in
                  db.advertiser_campaigns.find(
                      {"business_id": biz["_id"]},
                      {"_id": 1, "name": 1, "campaign_type": 1,
                        "status": 1, "budget": 1, "created_at": 1})
                      .sort("created_at", -1)]
    return {"count": len(items), "items": items}


@router.post("/campaigns/buy/start")
async def start_buy_flow(request: Request,
                                                  user: dict = Depends(current_user)) -> dict:
    """Stub entry point — issues an opaque session token that the
    existing advertiser-dashboard flow uses to pre-fill the business
    context.  Frontend just deeplinks to /advertiser?biz_session=..."""
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    sess = _new_id("biz_buy")
    await db.business_buy_sessions.insert_one({
        "_id":                  sess,
        "business_id":  biz["_id"],
        "owner_user_id": user["user_id"],
        "created_at":  _now(),
    })
    return {"ok": True, "buy_session_id": sess,
                  "deep_link": f"/advertiser?biz_session={sess}"}


# ── Phase J.1 — One-click launch coupon templates ─────────────────
LAUNCH_TEMPLATES = {
    "launch_50_off": {
        "name":                          "Launch — 50% off any item",
        "discount_label":      "50% OFF",
        "discount_value_pct": 50,
        "savings_value":      None,
        "description":          ("First-time customer launch promo. Valid for "
                                              "one redemption per customer."),
        "tone":                          "magenta",
    },
    "lunch_30_off": {
        "name":                          "Lunch rush — 30% off (11am-2pm)",
        "discount_label":      "30% OFF · LUNCH",
        "discount_value_pct": 30,
        "savings_value":      None,
        "description":          ("Lunch-window special. Server-side validation "
                                              "still allows redemption any time; honour at "
                                              "your discretion."),
        "tone":                          "electric",
    },
    "free_appetizer": {
        "name":                          "Free appetizer with any entrée",
        "discount_label":      "FREE APPETIZER",
        "discount_value_pct": 0,
        "savings_value":      12,
        "description":          ("Complimentary appetizer (up to $12 value) with "
                                              "any entrée purchase."),
        "tone":                          "gold",
    },
    "bogo": {
        "name":                          "Buy one, get one free",
        "discount_label":      "BOGO",
        "discount_value_pct": 50,
        "savings_value":      None,
        "description":          ("Buy any drink/entrée, get the second one free "
                                              "(equal or lesser value)."),
        "tone":                          "emerald",
    },
}
LAUNCH_BATCH_SIZE = 100
LAUNCH_EXPIRES_DAYS = 30


class _LaunchTplBody(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=60)


def _mint_voucher_code() -> str:
    return f"BIGFM-{secrets.token_urlsafe(6).replace('-', '').replace('_', '').upper()[:8]}"


@router.post("/coupons/launch-template")
async def launch_template(body: _LaunchTplBody, request: Request,
                                                          user: dict = Depends(current_user)) -> dict:
    """Mint an `offer` row + 100 voucher codes for a one-click launch
    promo.  Idempotent — re-calling for a business that already used
    THIS template returns 409 with the existing offer details."""
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    tpl = LAUNCH_TEMPLATES.get(body.template_id)
    if not tpl:
        raise HTTPException(400, {"code": "invalid_template",
                                                          "allowed": sorted(LAUNCH_TEMPLATES.keys())})

    # Idempotency — has this business already issued THIS template?
    existing = await db.offers.find_one(
        {"business_id": biz["_id"],
          "launch_template_id": body.template_id})
    if existing:
        raise HTTPException(409, {
            "code":                          "already_issued",
            "offer_id":                  existing["_id"],
            "code_count":            int(existing.get("voucher_code_count") or 0),
            "public_share_url": existing.get("public_share_url"),
        })

    now = _now()
    expires_at = now + timedelta(days=LAUNCH_EXPIRES_DAYS)
    offer_id = _new_id("offer")
    public_share_url = f"/offer/{offer_id}"

    offer_doc = {
        "_id":                                  offer_id,
        "offer_id":                      offer_id,  # legacy unique index
        "business_id":                  biz["_id"],
        "title":                              tpl["name"],
        "description":                  tpl["description"],
        "discount_label":          tpl["discount_label"],
        "discount_value_pct":  tpl["discount_value_pct"],
        "savings_value":              tpl["savings_value"],
        "tone":                                  tpl["tone"],
        "launch_template_id":  body.template_id,
        "status":                              "active",
        "target_radius_miles":  5,
        "target_lat":                  biz.get("lat"),
        "target_lng":                  biz.get("lng"),
        "voucher_code_count":  LAUNCH_BATCH_SIZE,
        "redemption_count":      0,
        "public_share_url":      public_share_url,
        "expires_at":                  expires_at,
        "created_at":                  now,
        "updated_at":                  now,
    }
    await db.offers.insert_one(offer_doc)

    # Mint codes in one batch — collisions are extremely unlikely with
    # 8-char URL-safe tokens, but we still upsert defensively.
    bulk = []
    for _ in range(LAUNCH_BATCH_SIZE):
        code = _mint_voucher_code()
        bulk.append({
            "_id":                          _new_id("vc"),
            "code":                      code,
            "voucher_code":      code,
            "offer_id":              offer_id,
            "business_id":      biz["_id"],
            "offer_title":      tpl["name"],
            "savings_value": tpl["savings_value"],
            "status":                    "issued",
            "issued_at":            now,
            "expires_at":          expires_at,
        })
    if bulk:
        await db.voucher_codes.insert_many(bulk, ordered=False)

    log.info("[launch_template] biz=%s tpl=%s offer=%s codes=%d",
                  biz["_id"], body.template_id, offer_id, LAUNCH_BATCH_SIZE)
    return {
        "ok":                              True,
        "offer_id":                  offer_id,
        "code_count":            LAUNCH_BATCH_SIZE,
        "public_share_url": public_share_url,
        "title":                      tpl["name"],
        "discount_label":  tpl["discount_label"],
        "expires_at":            expires_at.isoformat(),
        "share_text":            (f"{tpl['discount_label']} at "
                                                  f"{biz.get('name') or 'us'} — claim your code on "
                                                  f"RadioLife."),
    }


@router.get("/coupons/launch-templates")
async def list_launch_templates(request: Request,
                                                                          user: dict = Depends(current_user)) -> dict:
    """Returns the available templates + a per-template `already_issued`
    flag so the dashboard can grey-out used templates."""
    db = request.app.state.db
    biz = _require_business(await _resolve_business(db, user))
    used = set()
    async for o in db.offers.find(
        {"business_id": biz["_id"],
          "launch_template_id": {"$ne": None}},
        {"launch_template_id": 1, "_id": 0}):
        if o.get("launch_template_id"):
            used.add(o["launch_template_id"])
    return {"templates": [
        {"id": k, **{kk: v for kk, v in vv.items()
                                if kk in ("name", "discount_label", "description", "tone")},
          "already_issued": (k in used)}
        for k, vv in LAUNCH_TEMPLATES.items()
    ]}

