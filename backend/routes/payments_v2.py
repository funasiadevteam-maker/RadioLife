"""Phase J.3 — Real Stripe Checkout for advertiser self-serve.

Replaces the mocked `payment_intent_id` ack with a real Stripe Checkout
Session.  Mirrors the existing `services/stripe_client.py` mock/live
toggle (STRIPE_MODE env), and reuses its webhook signature verification
helper.

Endpoints:
    POST /api/payments/create-checkout                                  (auth)
    POST /api/webhooks/stripe/events                                          (public)
    GET  /api/payments/{checkout_session_id}/status            (auth)

Webhook handler flips campaign rows from `pending_payment` →
`pending_approval` (P&W) or `live` (banner ads, direct-sold) on
`checkout.session.completed`, then awards the advertiser a small loyalty
bonus via PointsService.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, conint
from starlette.responses import JSONResponse

from auth import current_user
from services.stripe_client import (
    is_live, stripe_mode,
    _live_stripe, _mock_id,
    verify_webhook_signature, WebhookSignatureError,
)

log = logging.getLogger("bigfm.payments_v2")
router = APIRouter(tags=["payments"])


# ────────────────────── helpers ──────────────────────────────────
PURPOSES = {"predict_win_campaign", "banner_ad_campaign",
                      "sponsored_game", "business_ad_buy",
                      "advertiser_topup_v2"}   # Phase AD.1

# Default currency by market — falls back to USD.
MARKET_CURRENCY = {
    "dfw": "usd", "us": "usd",
    "dubai": "aed", "uae": "aed",
    "india": "inr", "mumbai": "inr", "delhi": "inr",
    "london": "gbp", "uk": "gbp",
}


def _resolve_currency(market: Optional[str],
                                              currency_hint: Optional[str]) -> str:
    if currency_hint:
        c = currency_hint.lower()
        if c in ("usd", "aed", "inr", "gbp", "eur"):
            return c
    if market:
        return MARKET_CURRENCY.get(market.lower(), "usd")
    return "usd"


class _CreateBody(BaseModel):
    purpose: str = Field(..., min_length=1, max_length=60)
    entity_id: str = Field(..., min_length=1, max_length=120)
    amount_cents: conint(ge=50, le=5_000_00)  # 50¢ floor, $5k ceiling
    currency: Optional[str] = None
    market: Optional[str] = None
    success_url: str = Field(..., min_length=8)
    cancel_url: str = Field(..., min_length=8)
    description: Optional[str] = None


def _create_payment_checkout(*, amount_cents: int, currency: str,
                                                            success_url: str, cancel_url: str,
                                                            metadata: dict,
                                                            description: str) -> dict:
    """Payment-mode Checkout Session (one-time charge).  Mirrors the
    subscription-mode helper in stripe_client.py but for
    purpose="predict_win_campaign" et al."""
    if is_live():
        params: dict = {
            "mode":                              "payment",
            "payment_method_types": ["card"],
            "line_items":                  [{
                "price_data": {
                    "currency":      currency,
                    "unit_amount": amount_cents,
                    "product_data": {"name": description[:120] or "RadioLife",
                                                      "description": description[:300] or ""},
                },
                "quantity": 1,
            }],
            "success_url":  success_url,
            "cancel_url":    cancel_url,
            "metadata":        metadata,
        }
        sess = _live_stripe().checkout.Session.create(**params)
        return {"id": sess["id"], "url": sess["url"],
                      "payment_status": sess.get("payment_status") or "unpaid",
                      "amount_total": sess.get("amount_total") or amount_cents,
                      "currency":        sess.get("currency") or currency}
    # Mock — caller flows can complete via /api/admin/stripe/mock/fire-webhook.
    session_id = _mock_id("cs")
    return {"id": session_id,
                  "url": f"/mock/stripe/checkout?session_id={session_id}",
                  "payment_status": "unpaid",
                  "amount_total": amount_cents,
                  "currency":        currency}


@router.post("/api/payments/create-checkout")
async def create_checkout(body: _CreateBody, request: Request,
                                                  user: dict = Depends(current_user)) -> dict:
    if body.purpose not in PURPOSES:
        raise HTTPException(400, {"code": "invalid_purpose",
                                                          "allowed": sorted(PURPOSES)})
    db = request.app.state.db
    currency = _resolve_currency(body.market, body.currency)
    metadata = {
        "purpose":        body.purpose,
        "entity_id":  body.entity_id,
        "user_id":      user["user_id"],
        "market":        body.market or "",
    }
    description = (body.description
                                  or f"RadioLife · {body.purpose} · {body.entity_id}")[:300]
    try:
        sess = _create_payment_checkout(
            amount_cents=int(body.amount_cents),
            currency=currency,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata=metadata,
            description=description)
    except Exception as e:
        log.exception("[payments] create-checkout failed: %s", e)
        raise HTTPException(502, {"code": "stripe_error", "detail": str(e)})

    # Persist the intent for status polling + reconcile.
    now = datetime.now(timezone.utc)
    await db.payment_intents_v2.insert_one({
        "_id":                          sess["id"],
        "user_id":                  user["user_id"],
        "purpose":                  body.purpose,
        "entity_id":              body.entity_id,
        "amount_cents":      int(body.amount_cents),
        "currency":                currency,
        "status":                    "pending",
        "stripe_mode":        stripe_mode(),
        "created_at":            now,
    })

    # If this checkout is bound to an existing entity (P&W campaign,
    # banner campaign, business buy session), stamp the session id on it
    # so the webhook can reverse-map.
    if body.purpose == "predict_win_campaign":
        await db.predict_win_campaigns.update_one(
            {"_id": body.entity_id},
            {"$set": {"checkout_session_id": sess["id"],
                              "approval_status": "pending_payment",
                              "updated_at": now}})
    elif body.purpose == "business_ad_buy":
        await db.business_buy_sessions.update_one(
            {"_id": body.entity_id},
            {"$set": {"checkout_session_id": sess["id"],
                              "status": "pending_payment", "updated_at": now}})
    elif body.purpose == "banner_ad_campaign":
        await db.campaigns.update_one(
            {"_id": body.entity_id},
            {"$set": {"checkout_session_id": sess["id"],
                              "status": "pending_payment", "updated_at": now}})

    return {"ok": True, "checkout_session_id": sess["id"],
                  "checkout_url": sess["url"],
                  "amount_total": sess["amount_total"],
                  "currency": sess["currency"],
                  "mode": stripe_mode()}


@router.get("/api/payments/{checkout_session_id}/status")
async def get_payment_status(checkout_session_id: str, request: Request,
                                                          user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    doc = await db.payment_intents_v2.find_one(
        {"_id": checkout_session_id})
    if not doc:
        raise HTTPException(404, "session_not_found")
    if doc.get("user_id") != user["user_id"]:
        raise HTTPException(403, "not_owner")
    return {
        "checkout_session_id": checkout_session_id,
        "status":                          doc.get("status"),
        "purpose":                      doc.get("purpose"),
        "entity_id":                  doc.get("entity_id"),
        "amount_cents":          int(doc.get("amount_cents") or 0),
        "currency":                    doc.get("currency"),
        "paid_at":                      (doc["paid_at"].isoformat()
                                                          if isinstance(doc.get("paid_at"), datetime)
                                                          else None),
    }


# ────────────────────── webhook handler ──────────────────────────
@router.post("/api/webhooks/stripe/events")
async def stripe_webhook(request: Request) -> JSONResponse:
    """Public endpoint.  Verifies the HMAC-SHA256 signature against
    `STRIPE_WEBHOOK_SECRET` (env).  SC.6 verify-mode:
      - `STRIPE_WEBHOOK_VERIFY_ENFORCE=1` + secret set → construct_event (verified)
      - `STRIPE_WEBHOOK_VERIFY_SIGNATURE=0` OR enforce=0 → construct_from (unverified)
    Backward-compat: existing `STRIPE_WEBHOOK_VERIFY_SIGNATURE` still honoured
    when the new enforce flag is unset."""
    enforce = (os.environ.get("STRIPE_WEBHOOK_VERIFY_ENFORCE", "").strip() == "1")
    legacy_verify = (os.environ.get("STRIPE_WEBHOOK_VERIFY_SIGNATURE", "1")
                                        .strip() == "1")
    secret = (os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip()
    verify = enforce or (legacy_verify and bool(secret))

    body = await request.body()
    if verify and secret:
        sig = request.headers.get("stripe-signature") or ""
        try:
            event = verify_webhook_signature(
                payload=body, sig_header=sig, secret=secret)
        except WebhookSignatureError as e:
            log.warning("[stripe_webhook] mode=verified BAD_SIG %s", e)
            raise HTTPException(400, {"code": "bad_signature"})
        log.info("[webhook] mode=verified event=%s",
                        event.get("type") if isinstance(event, dict) else "?")
    else:
        if enforce:
            # Enforce requested but secret missing — hard fail to surface config bug
            log.error("[stripe_webhook] enforce=1 but STRIPE_WEBHOOK_SECRET missing")
            raise HTTPException(500, {"code": "webhook_secret_missing"})
        log.warning("[stripe_webhook] mode=unverified (enforce=0) — DEV ONLY")
        try:
            event = json.loads(body.decode("utf-8"))
        except Exception as e:
            raise HTTPException(400, {"code": "bad_payload", "detail": str(e)})
        log.info("[webhook] mode=unverified event=%s",
                        event.get("type") if isinstance(event, dict) else "?")

    event_id = event.get("id") or _mock_id("evt")
    event_type = event.get("type") or "unknown"
    stripe_account_hdr = (request.headers.get("stripe-account")
                                                or event.get("account"))
    db = request.app.state.db

    # Persist raw event.
    await db.payment_events.update_one(
        {"_id": event_id},
        {"$setOnInsert": {
            "_id":                  event_id,
            "event_type":      event_type,
            "received_at":  datetime.now(timezone.utc),
            "stripe_mode": stripe_mode(),
            "stripe_account": stripe_account_hdr,
            "raw":                    event,
        }}, upsert=True)

    handler_result = {"ok": True, "handled": False}
    obj = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        handler_result = await _handle_checkout_completed(db, event)
    elif event_type in ("payment_intent.succeeded",
                                              "payment_intent.payment_failed",
                                              "payment_intent.canceled"):
        # SC.5 — destination-charge lifecycle
        try:
            from services.payment_service import (
                handle_payment_intent_succeeded as _sc5_succ,
                handle_payment_intent_failed        as _sc5_fail,
                handle_payment_intent_canceled  as _sc5_canc,
            )
            if event_type == "payment_intent.succeeded":
                res = await _sc5_succ(db, obj)
            elif event_type == "payment_intent.payment_failed":
                res = await _sc5_fail(db, obj)
            else:
                res = await _sc5_canc(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc5": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.5 handler failed")
            handler_result = {"ok": True, "handled": False,
                                              "event_type": event_type, "error": str(_e)[:200]}
    elif event_type == "charge.refunded":
        # SC.6 — refund lifecycle
        try:
            from services.refund_service import handle_charge_refunded
            res = await handle_charge_refunded(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 refund handler failed")
            handler_result = {"ok": True, "handled": False,
                                              "event_type": event_type, "error": str(_e)[:200]}
    elif event_type == "charge.updated":
        try:
            from services.payout_dispute_service import handle_charge_updated
            res = await handle_charge_updated(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 charge.updated failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}
    elif event_type == "transfer.created":
        try:
            from services.payout_dispute_service import handle_transfer_created
            res = await handle_transfer_created(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 transfer.created failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}
    elif event_type in ("payout.created", "payout.paid",
                                              "payout.failed", "payout.canceled",
                                              "payout.updated"):
        try:
            from services.payout_dispute_service import handle_payout_event
            res = await handle_payout_event(
                db, obj, event_type=event_type,
                stripe_account=stripe_account_hdr)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 payout handler failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}
    elif event_type == "charge.dispute.created":
        try:
            from services.payout_dispute_service import handle_dispute_created
            res = await handle_dispute_created(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 dispute.created failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}
    elif event_type == "charge.dispute.closed":
        try:
            from services.payout_dispute_service import handle_dispute_closed
            res = await handle_dispute_closed(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 dispute.closed failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}
    elif event_type == "application_fee.created":
        try:
            from services.payout_dispute_service import handle_application_fee_created
            res = await handle_application_fee_created(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 app_fee.created failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}
    elif event_type == "application_fee.refunded":
        try:
            from services.payout_dispute_service import handle_application_fee_refunded
            res = await handle_application_fee_refunded(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 app_fee.refunded failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}
    elif event_type == "account.updated":
        try:
            from services.payout_dispute_service import handle_account_updated
            res = await handle_account_updated(db, obj)
            handler_result = {"ok": True, "handled": True,
                                              "event_type": event_type, "sc6": res}
        except Exception as _e:
            log.exception("[stripe_webhook] SC.6 account.updated failed")
            handler_result = {"ok": True, "handled": False, "error": str(_e)[:200]}

    return JSONResponse({"ok": True, "event_id": event_id,
                                              "event_type": event_type,
                                              **handler_result})


async def _handle_checkout_completed(db, event: dict) -> dict:
    """Flip the bound entity to its post-payment state."""
    obj = (event.get("data") or {}).get("object") or {}
    session_id = obj.get("id")
    metadata = obj.get("metadata") or {}
    purpose = metadata.get("purpose")
    entity_id = metadata.get("entity_id")
    user_id = metadata.get("user_id")
    amount_total = int(obj.get("amount_total") or 0)
    currency = obj.get("currency") or "usd"
    now = datetime.now(timezone.utc)

    if not (purpose and entity_id):
        log.warning("[stripe_webhook] checkout.session.completed missing "
                              "metadata.purpose/entity_id: %s", session_id)
        return {"ok": True, "handled": False,
                      "reason": "missing_metadata"}

    # Mark payment_intents_v2 as paid.
    await db.payment_intents_v2.update_one(
        {"_id": session_id},
        {"$set": {"status": "paid",
                          "paid_at": now,
                          "amount_paid_cents": amount_total,
                          "currency": currency,
                          "updated_at": now}})

    # Flip the bound entity.
    if purpose == "predict_win_campaign":
        await db.predict_win_campaigns.update_one(
            {"_id": entity_id},
            {"$set": {"approval_status": "pending",
                              "payment_intent_id": session_id,
                              "submitted_at": now, "updated_at": now}})
    elif purpose == "banner_ad_campaign":
        await db.campaigns.update_one(
            {"_id": entity_id},
            {"$set": {"status": "live",
                              "payment_intent_id": session_id,
                              "updated_at": now}})
    elif purpose == "business_ad_buy":
        await db.business_buy_sessions.update_one(
            {"_id": entity_id},
            {"$set": {"status": "paid",
                              "payment_intent_id": session_id,
                              "updated_at": now}})
    elif purpose == "advertiser_topup_v2":
        # Phase AD.1 — credit the advertiser budget via a dedicated helper.
        try:
            from services.ad1_advertiser_service import credit_topup_on_webhook
            await credit_topup_on_webhook(
                db, session_id=session_id, advertiser_id=entity_id,
                amount_cents=amount_total)
        except Exception as e:
            log.warning("[stripe_webhook] AD.1 topup credit failed: %s", e)

    # Loyalty bonus: 10 pts per $100 spent (currency-agnostic — uses
    # the literal cents value as a proxy).  Idempotent via session id.
    if user_id and amount_total > 0:
        try:
            from services.points_service import PointsService
            pts = int(amount_total / 1000)  # $1 = 100c → 10 pts per $100
            if pts > 0:
                await PointsService(db).award(
                    user_id=user_id, delta=pts,
                    source="ad_spend_bonus",
                    metadata={"session_id": session_id, "purpose": purpose,
                                          "amount_cents": amount_total,
                                          "currency": currency},
                    idempotency_key=f"ad_spend_{session_id}")
        except Exception as e:
            log.warning("[stripe_webhook] ad_spend_bonus award failed: %s", e)

    log.info("[stripe_webhook] checkout.completed %s purpose=%s entity=%s",
                  session_id, purpose, entity_id)
    return {"ok": True, "handled": True,
                  "purpose": purpose, "entity_id": entity_id,
                  "amount_total": amount_total}
