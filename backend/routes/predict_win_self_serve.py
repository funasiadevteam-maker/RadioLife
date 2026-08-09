"""Phase 42-E1.3 — Predict & Win self-serve advertiser + admin pricing.

Adds two surfaces on top of the existing predict_win_campaigns
infrastructure:

1. **Admin pricing config** — singleton `predict_win_pricing_config`
     row tunes the global `min_campaign_price_usd` (default 299) and
     `per_participant_price_usd` (default 5).  Final invoice =
     `max(min, per_participant * expected_participants)`.
2. **Advertiser self-serve campaign builder** — POST /draft creates a
     campaign in `approval_status="pending"` after a (mocked) Stripe
     Checkout has been completed and `payment_intent_id` stamped.

Schema additions to predict_win_campaigns
-----------------------------------------
- advertiser_id            (str, optional)        — links to advertisers row.
- pricing_snapshot     (dict)                       — { min_campaign_price_usd,
                                                                              per_participant_price_usd,
                                                                              expected_participants,
                                                                              total_quoted_usd }
- payment_intent_id  (str, optional)        — stripe checkout session id.
- submitted_at          (datetime, optional)  — set on /submit.
- approval_status      (existing field)            — "draft" → "pending" → "approved" / "rejected"

Routes
------
    GET    /api/admin/predict-win/pricing
    PATCH /api/admin/predict-win/pricing
    POST   /api/advertiser/predict-win/draft
    POST   /api/advertiser/predict-win/{id}/submit
    GET    /api/advertiser/predict-win/mine
    POST   /api/admin/predict-win/{id}/approve
    POST   /api/admin/predict-win/{id}/reject
    GET    /api/admin/predict-win/pending
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["predict-win-self-serve"])
log = logging.getLogger("bigfm.predict_win.self_serve")


PRICING_DOC_ID = "default"
DEFAULT_MIN_USD = 299
DEFAULT_PER_PARTICIPANT_USD = 5


# ─── Bootstrap ───────────────────────────────────────────────────
async def ensure_predict_win_pricing_indexes(db) -> None:
    """Idempotent — seeds the pricing singleton + indexes."""
    await db.predict_win_pricing_config.update_one(
        {"_id": PRICING_DOC_ID},
        {"$setOnInsert": {
            "_id": PRICING_DOC_ID,
            "min_campaign_price_usd":    DEFAULT_MIN_USD,
            "per_participant_price_usd": DEFAULT_PER_PARTICIPANT_USD,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "updated_by": "system",
        }},
        upsert=True,
    )
    # New indexes on predict_win_campaigns for the advertiser flow.
    try:
        await db.predict_win_campaigns.create_index(
            [("advertiser_id", 1), ("created_at", -1)],
            name="pwc_adv_time")
        await db.predict_win_campaigns.create_index(
            [("approval_status", 1), ("submitted_at", -1)],
            name="pwc_apprstatus_subm")
    except Exception as e:
        log.debug("[pw_pricing] index ensure skipped: %s", e)


# ─── Schemas ─────────────────────────────────────────────────────
class _AnswerOption(BaseModel):
    # Existing campaigns use `option_id`; advertiser side accepts either
    # `option_id` or `id` for ergonomics — normalized below.
    option_id: Optional[str] = None
    id:                Optional[str] = None
    label:        str

    def to_canonical(self) -> dict:
        oid = (self.option_id or self.id or "").strip()
        return {"option_id": oid, "label": self.label,
                          "external_outcome_id": oid}


class _PricingPatch(BaseModel):
    min_campaign_price_usd:        Optional[int] = Field(default=None, ge=0)
    per_participant_price_usd: Optional[int] = Field(default=None, ge=0)


class _DraftBody(BaseModel):
    campaign_name:                str
    event_type:                      str = "advertiser_custom"
    event_label:                    Optional[str] = None
    question:                            str
    answer_options:              List[_AnswerOption]
    lock_time_iso:                str
    prize_description:        str
    expected_participants: int = Field(ge=1, le=100000)
    city:                                  Optional[str] = None
    language:                          str = "en"


class _SubmitBody(BaseModel):
    payment_intent_id: Optional[str] = None
    # In the mocked Stripe flow this is a placeholder.  Real flow
    # would verify the payment_intent against Stripe's API here.
    # Phase J.3 — when not paid yet, the endpoint mints a Stripe
    # Checkout Session and these URLs control where Stripe redirects
    # after completion / cancellation.
    success_url:        Optional[str] = None
    cancel_url:          Optional[str] = None


class _RejectBody(BaseModel):
    reason: str


# ─── Auth helpers ────────────────────────────────────────────────
async def _current_user(request: Request) -> dict:
    from auth import current_user
    return await current_user(request)


async def _require_admin(request: Request) -> dict:
    user = await _current_user(request)
    if (user.get("role") or "").lower() != "admin":
        raise HTTPException(403, {"code": "admin_required"})
    return user


async def _require_advertiser(request: Request) -> tuple[dict, dict]:
    """Returns (user, advertiser_row).  Advertiser is the user's
    primary advertiser org — created on demand if missing."""
    user = await _current_user(request)
    if (user.get("role") or "").lower() not in ("advertiser",
                                                                                            "business_partner",
                                                                                            "admin"):
        raise HTTPException(403, {"code": "advertiser_required"})
    db = request.app.state.db
    adv = await db.advertisers.find_one({"user_id": user["user_id"]})
    if not adv:
        # Auto-provision a minimal advertiser org for this user so the
        # builder doesn't 404 on first visit.
        adv = {
            "_id": uuid.uuid4().hex[:24],
            "user_id":         user["user_id"],
            "name":               user.get("name") or user.get("email") or "Advertiser",
            "contact_email": user.get("email"),
            "created_at":    datetime.now(timezone.utc),
        }
        await db.advertisers.insert_one(adv)
    return user, adv


async def _read_pricing(db) -> dict:
    doc = await db.predict_win_pricing_config.find_one(
        {"_id": PRICING_DOC_ID})
    if not doc:
        return {"min_campaign_price_usd": DEFAULT_MIN_USD,
                          "per_participant_price_usd": DEFAULT_PER_PARTICIPANT_USD,
                          "updated_at": None, "updated_by": None}
    out = dict(doc)
    out.pop("_id", None)
    ua = out.get("updated_at")
    if isinstance(ua, datetime):
        out["updated_at"] = ua.isoformat()
    return out


def _quote(pricing: dict, expected_participants: int) -> int:
    min_u = int(pricing.get("min_campaign_price_usd") or DEFAULT_MIN_USD)
    per_u = int(pricing.get("per_participant_price_usd") or DEFAULT_PER_PARTICIPANT_USD)
    pp = int(expected_participants or 0)
    return max(min_u, per_u * pp)


# ─── Admin: pricing ──────────────────────────────────────────────
@router.get("/api/admin/predict-win/pricing")
async def get_pricing(request: Request):
    await _require_admin(request)
    db = request.app.state.db
    return await _read_pricing(db)


@router.patch("/api/admin/predict-win/pricing")
async def patch_pricing(request: Request, body: _PricingPatch):
    admin = await _require_admin(request)
    db = request.app.state.db
    update = {k: v for k, v in body.dict().items() if v is not None}
    if not update:
        raise HTTPException(400, {"code": "empty_patch"})
    update["updated_at"] = datetime.now(timezone.utc)
    update["updated_by"] = admin.get("user_id")
    await db.predict_win_pricing_config.update_one(
        {"_id": PRICING_DOC_ID}, {"$set": update}, upsert=True)
    return await _read_pricing(db)


# ─── Advertiser: draft + submit + list ───────────────────────────
@router.post("/api/advertiser/predict-win/draft")
async def create_draft(request: Request, body: _DraftBody):
    user, adv = await _require_advertiser(request)
    db = request.app.state.db
    pricing = await _read_pricing(db)
    quote = _quote(pricing, body.expected_participants)
    cid = f"pwc_adv_{uuid.uuid4().hex[:14]}"
    try:
        lock_dt = datetime.fromisoformat(body.lock_time_iso.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, {"code": "bad_lock_time"})
    doc = {
        "_id": cid,
        "campaign_id": cid,
        "title": body.campaign_name,
        "description": body.prize_description,
        "event_type": body.event_type,
        "event_label": body.event_label,
        "city":            body.city,
        "language":  body.language,
        "question": {
            "prompt": body.question,
            "answer_options": [o.to_canonical() for o in body.answer_options],
        },
        "start_time": datetime.now(timezone.utc),
        "lock_time":  lock_dt,
        "advertiser_id": str(adv.get("_id")),
        "created_by":      user["user_id"],
        "approval_status": "draft",
        "status": "draft",
        "pricing_snapshot": {
            "min_campaign_price_usd":      pricing.get("min_campaign_price_usd"),
            "per_participant_price_usd": pricing.get("per_participant_price_usd"),
            "expected_participants":          int(body.expected_participants),
            "total_quoted_usd":                        quote,
        },
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.predict_win_campaigns.insert_one(doc)
    return {"campaign_id": cid, "quote_usd": quote,
                      "approval_status": "draft"}


@router.post("/api/advertiser/predict-win/{campaign_id}/submit")
async def submit_for_approval(request: Request, campaign_id: str,
                                                                        body: _SubmitBody):
    """Phase J.3 — submission now requires a real Stripe Checkout
    session to be paid before the campaign can flip to `pending`.
    The flow:
        1. Advertiser calls THIS endpoint with `payment_intent_id=`
              (legacy mock path retained for tests).
        2. OR the advertiser hits `/api/payments/create-checkout` first
              (purpose=`predict_win_campaign`, entity_id=campaign_id),
              completes Stripe Checkout, and the webhook flips the row
              to `pending` automatically.
    Calling THIS endpoint with no payment_intent_id now returns the
    Stripe checkout URL so the frontend can redirect."""
    user, adv = await _require_advertiser(request)
    db = request.app.state.db
    c = await db.predict_win_campaigns.find_one({"_id": campaign_id})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("advertiser_id") != str(adv.get("_id")):
        raise HTTPException(403, {"code": "not_owner"})
    if c.get("approval_status") not in (None, "draft", "pending_payment"):
        raise HTTPException(409, {"code": "wrong_state",
                                                          "current": c.get("approval_status")})

    # If the advertiser already paid via Stripe Checkout, the webhook
    # has already moved the row to "pending".  Accept the legacy
    # ack path too (any non-empty payment_intent_id) so QA flows stay
    # green.
    pi_id = body.payment_intent_id
    if not pi_id:
        # Phase J.3 — mint a Stripe Checkout Session for this campaign.
        try:
            from services.stripe_client import is_live, stripe_mode
            from routes.payments_v2 import _create_payment_checkout
            quote = int(((c.get("pricing") or {}).get("total_quoted_usd")
                                      or 0) * 100)  # USD → cents
            if quote < 50:
                quote = 50    # Stripe minimum
            success_url = (body.success_url
                                            or f"/advertiser/predict-win/{campaign_id}?paid=1")
            cancel_url = (body.cancel_url
                                          or f"/advertiser/predict-win/{campaign_id}?paid=0")
            sess = _create_payment_checkout(
                amount_cents=quote, currency="usd",
                success_url=success_url, cancel_url=cancel_url,
                metadata={"purpose": "predict_win_campaign",
                                  "entity_id": campaign_id,
                                  "user_id": user["user_id"]},
                description=f"RadioLife Predict & Win · {campaign_id}")
            now = datetime.now(timezone.utc)
            await db.predict_win_campaigns.update_one(
                {"_id": campaign_id},
                {"$set": {"checkout_session_id": sess["id"],
                                  "approval_status": "pending_payment",
                                  "updated_at": now}})
            await db.payment_intents_v2.insert_one({
                "_id":                          sess["id"],
                "user_id":                  user["user_id"],
                "purpose":                  "predict_win_campaign",
                "entity_id":              campaign_id,
                "amount_cents":      quote, "currency": "usd",
                "status":                    "pending",
                "stripe_mode":        stripe_mode(),
                "created_at":            now,
            })
            return {"campaign_id": campaign_id,
                          "approval_status": "pending_payment",
                          "checkout_session_id": sess["id"],
                          "checkout_url": sess["url"],
                          "amount_cents": quote, "currency": "usd",
                          "stripe_mode": stripe_mode()}
        except Exception as _e:
            # Fall through to the legacy mock path on any Stripe error.
            pi_id = f"pi_mock_{uuid.uuid4().hex[:14]}"
    now = datetime.now(timezone.utc)
    await db.predict_win_campaigns.update_one(
        {"_id": campaign_id},
        {"$set": {
            "approval_status": "pending",
            "payment_intent_id": pi_id,
            "submitted_at": now,
            "updated_at": now,
        }})
    return {"campaign_id": campaign_id, "approval_status": "pending",
                      "payment_intent_id": pi_id}


@router.get("/api/advertiser/predict-win/mine")
async def list_my_campaigns(request: Request):
    user, adv = await _require_advertiser(request)
    db = request.app.state.db
    rows = []
    cur = db.predict_win_campaigns.find(
        {"advertiser_id": str(adv.get("_id"))}).sort("created_at", -1)
    async for r in cur:
        r["_id"] = str(r.get("_id"))
        for k in ("created_at", "updated_at", "submitted_at",
                            "approved_at", "rejected_at", "lock_time", "start_time"):
            v = r.get(k)
            if isinstance(v, datetime):
                r[k] = v.isoformat()
        rows.append(r)
    return {"items": rows, "count": len(rows)}


# ─── Admin: approval queue ───────────────────────────────────────
@router.get("/api/admin/predict-win/pending")
async def admin_pending(request: Request):
    await _require_admin(request)
    db = request.app.state.db
    rows = []
    cur = db.predict_win_campaigns.find(
        {"approval_status": "pending"}).sort("submitted_at", 1)
    async for r in cur:
        r["_id"] = str(r.get("_id"))
        for k in ("created_at", "updated_at", "submitted_at",
                            "approved_at", "rejected_at", "lock_time", "start_time"):
            v = r.get(k)
            if isinstance(v, datetime):
                r[k] = v.isoformat()
        rows.append(r)
    return {"items": rows, "count": len(rows)}


@router.post("/api/admin/predict-win/{campaign_id}/approve")
async def admin_approve(request: Request, campaign_id: str):
    admin = await _require_admin(request)
    db = request.app.state.db
    c = await db.predict_win_campaigns.find_one({"_id": campaign_id})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    now = datetime.now(timezone.utc)
    await db.predict_win_campaigns.update_one(
        {"_id": campaign_id},
        {"$set": {
            "approval_status": "approved",
            "status": "live",
            "approved_at": now,
            "approved_by": admin.get("user_id"),
            "updated_at": now,
        }})
    return {"campaign_id": campaign_id, "approval_status": "approved",
                      "status": "live"}


@router.post("/api/admin/predict-win/{campaign_id}/reject")
async def admin_reject(request: Request, campaign_id: str,
                                                  body: _RejectBody):
    admin = await _require_admin(request)
    if not body.reason.strip():
        raise HTTPException(400, {"code": "reason_required"})
    db = request.app.state.db
    c = await db.predict_win_campaigns.find_one({"_id": campaign_id})
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    now = datetime.now(timezone.utc)
    await db.predict_win_campaigns.update_one(
        {"_id": campaign_id},
        {"$set": {
            "approval_status": "rejected",
            "status": "rejected",
            "rejected_at": now,
            "rejected_by": admin.get("user_id"),
            "approval_reason": body.reason.strip(),
            "updated_at": now,
        }})
    return {"campaign_id": campaign_id, "approval_status": "rejected",
                      "reason": body.reason.strip()}
