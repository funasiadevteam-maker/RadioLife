"""Phase SC.5 — Payment Service (destination charges via Stripe Connect).

Creates PaymentIntents with `on_behalf_of` + `transfer_data.destination`
+ `application_fee_amount` = SC.3-computed commission cents.  On
success writes:
  * `payment_transactions_v2` row with full breakdown
  * `commission_audit_log` row (SC.3 audit fires HERE on real money)
  * `merchant_payment_links.usage_count` atomic increment
  * `points_ledger` reward for authenticated customers
  * Mailgun receipt email

All external Stripe SDK calls funnel through `services.stripe_client`.
Extends but does NOT replace SC.4 payment_link_service.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe

from services.commission_service import calculate_platform_fee
from services.payment_link_service import get_link_by_token, is_link_serving

logger = logging.getLogger("bigfm.payment_sc5")


# ─── Config ──────────────────────────────────────────────────────
def _init_stripe() -> None:
    if not stripe.api_key:
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _publishable_key() -> str:
    return (os.environ.get("STRIPE_PUBLISHABLE_KEY")
                  or os.environ.get("REACT_APP_STRIPE_PUBLISHABLE_KEY")
                  or "").strip()


# ─── Errors ──────────────────────────────────────────────────────
class PaymentError(Exception):
    def __init__(self, code: str, detail: Optional[str] = None,
                            http_status: int = 400):
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.http_status = http_status


# ─── Create PaymentIntent ────────────────────────────────────────
async def create_payment_intent_for_link(db, *, token: str, amount_cents: int,
                                                                              customer_user_id: Optional[str] = None,
                                                                              customer_email: Optional[str] = None,
                                                                              idempotency_key: Optional[str] = None,
                                                                              modifiers: Optional[list] = None) -> dict:
    _init_stripe()

    link, biz = await get_link_by_token(db, token)
    if not link:
        raise PaymentError("link_not_found", http_status=404)

    serving, reason = is_link_serving(link)
    if not serving:
        raise PaymentError(f"link_{reason}", http_status=410)

    # Amount validation — fixed links override, customer-enter links clamp
    fixed_amt = link.get("amount_cents")
    if fixed_amt is not None:
        amount_cents = int(fixed_amt)
    else:
        amount_cents = int(amount_cents or 0)
        if amount_cents <= 0:
            raise PaymentError("invalid_amount")
        if link.get("min_amount_cents") \
                  and amount_cents < int(link["min_amount_cents"]):
            raise PaymentError("amount_below_min")
        if link.get("max_amount_cents") \
                  and amount_cents > int(link["max_amount_cents"]):
            raise PaymentError("amount_above_max")

    if not biz:
        raise PaymentError("merchant_not_found", http_status=404)

    stripe_acct = biz.get("stripe_account_id")
    if not stripe_acct:
        raise PaymentError("merchant_stripe_missing", http_status=400)
    if not biz.get("stripe_charges_enabled"):
        raise PaymentError("merchant_charges_disabled", http_status=400,
                                              detail="Stripe activation incomplete")

    # Phase MER.3 — resolve modifiers against the original amount before
    # computing Stripe fee.  Modifiers reduce what the customer pays.
    subtotal_cents = amount_cents
    stripe_charge_cents = amount_cents
    applied_modifiers = []
    if modifiers:
        try:
            from services.wallet_v2_service import preview_modifiers as _preview
            mid_for_pre = biz.get("business_id") or biz.get("_id")
            u = {"user_id": customer_user_id, "email": customer_email} \
                        if customer_user_id else None
            preview = await _preview(db, merchant_id=mid_for_pre,
                                                              order_amount_cents=subtotal_cents,
                                                              modifiers=modifiers, user=u)
            stripe_charge_cents = int(preview.get("stripe_charge_cents") or 0)
            applied_modifiers = preview.get("discounts") or []
            if stripe_charge_cents <= 0:
                # Zero-charge is handled by the dedicated endpoint, not here.
                raise PaymentError("use_zero_charge_endpoint",
                                                      detail="Modifiers fully cover this order; "
                                                                    "call /pay/{token}/zero-charge instead.",
                                                      http_status=400)
        except PaymentError:
            raise
        except Exception:
            logger.exception("[mer3] modifier preview failed — proceeding without modifiers")
            applied_modifiers = []
            stripe_charge_cents = amount_cents

    # SC.6 fix — snapshot the REAL category + market at intent creation so
    # the succeeded-audit row can resolve the correct rule rather than
    # using the `_sc5_charge` sentinel.
    real_category = biz.get("category_id") or biz.get("category") or "other"
    real_transaction_type = link.get("transaction_type") or "payment"

    # SC.3 commission — compute BUT do not write audit (audit fires on success).
    # MER.3 note: commission is computed on the ORIGINAL amount, but the
    # `application_fee_amount` we send to Stripe is capped to the ACTUAL
    # amount Stripe is charging (post-modifiers).  This preserves the
    # commission percentage on the merchant-recognised revenue.
    commission = await calculate_platform_fee(
        db,
        merchant_id=biz.get("business_id") or biz.get("_id"),
        category=real_category,
        transaction_type=real_transaction_type,
        amount_cents=amount_cents,
        write_audit=False,
    )
    app_fee_cents = int(commission["commission_cents"])
    # Sanity — never let the platform fee exceed the actual Stripe charge
    if app_fee_cents > stripe_charge_cents:
        app_fee_cents = stripe_charge_cents

    idempotency = idempotency_key or f"pi_link_{token}_{uuid.uuid4().hex[:12]}"
    currency = (link.get("currency") or "usd").lower()

    metadata = {
        "bigfm_flow":                    "connect_destination",
        "bigfm_link_token":        token,
        "bigfm_link_id":              link["link_id"],
        "bigfm_merchant_id":      biz.get("business_id") or biz.get("_id"),
        "bigfm_customer_user_id": customer_user_id or "",
        "bigfm_table_number":  (link.get("table_number") or ""),
        "bigfm_transaction_type": link.get("transaction_type") or "payment",
        "bigfm_commission_rule_id":      str(commission.get("rule_id") or ""),
        "bigfm_commission_override_id": str(commission.get("override_id") or ""),
        "bigfm_computed_percent":  str(commission.get("computed_percent")),
        "bigfm_subtotal_cents":    str(subtotal_cents),
        "bigfm_modifiers_count":  str(len(applied_modifiers)),
    }

    try:
        intent = stripe.PaymentIntent.create(
            amount=stripe_charge_cents,
            currency=currency,
            automatic_payment_methods={"enabled": True,
                                                                "allow_redirects": "never"},
            on_behalf_of=stripe_acct,
            transfer_data={"destination": stripe_acct},
            application_fee_amount=app_fee_cents,
            metadata=metadata,
            receipt_email=customer_email or None,
            idempotency_key=idempotency,
        )
    except stripe.StripeError as e:
        logger.exception("[sc5] stripe.PaymentIntent.create failed")
        raise PaymentError("stripe_error", detail=str(e), http_status=502)

    txn_id = f"tx5_{uuid.uuid4().hex[:16]}"
    now = _now()
    # Rough Stripe fee estimate (~2.9% + 30¢ US) for merchant net display.
    # Real value arrives on the charge.updated event in SC.6.
    stripe_fee_estimate = int(round(stripe_charge_cents * 0.029)) + 30
    merchant_net_est = max(0, stripe_charge_cents - app_fee_cents - stripe_fee_estimate)

    doc = {
        "_id":                                    txn_id,
        "transaction_id":                txn_id,
        "flow":                                  "connect_destination",
        "merchant_id":                    metadata["bigfm_merchant_id"],
        "link_id":                              link["link_id"],
        "link_token":                        token,
        "stripe_payment_intent_id": intent.id,
        "stripe_charge_id":              None,
        "stripe_connected_account_id": stripe_acct,
        "stripe_customer_id":        None,
        "amount_cents":                    stripe_charge_cents,
        "subtotal_cents":                subtotal_cents,
        "currency":                            currency.upper(),
        "application_fee_cents":  app_fee_cents,
        "computed_percent":            commission.get("computed_percent"),
        "commission_rule_id":        commission.get("rule_id"),
        "commission_override_id":  commission.get("override_id"),
        "commission_source":            commission.get("source"),
        "stripe_fee_estimate_cents": stripe_fee_estimate,
        "merchant_net_cents":        merchant_net_est,
        "status":                              "requires_confirmation",
        "failure_reason":                None,
        "payment_method_type":  None,
        "customer_user_id":            customer_user_id,
        "customer_email":                customer_email,
        "table_number":                    link.get("table_number"),
        "transaction_type":            real_transaction_type,
        "category_at_charge":      real_category,
        "idempotency_key":            idempotency,
        "created_at":                      now,
        "confirmed_at":                  None,
        "succeeded_at":                  None,
        "failed_at":                        None,
        "modifiers":                        applied_modifiers,        # MER.3 — persist applied modifiers
    }
    await db.payment_transactions_v2.insert_one(doc)

    logger.info(f"[sc5] intent created intent={intent.id} mid={doc['merchant_id']} "
                          f"subtotal={subtotal_cents} charge={stripe_charge_cents} "
                          f"fee={app_fee_cents} pct={commission.get('computed_percent')} "
                          f"source={commission.get('source')} tx={txn_id} "
                          f"mods={len(applied_modifiers)}")

    return {
        "intent_id":                          intent.id,
        "client_secret":                    intent.client_secret,
        "publishable_key":              _publishable_key(),
        "amount_cents":                      stripe_charge_cents,
        "subtotal_cents":                  subtotal_cents,
        "currency":                              currency.upper(),
        "commission_cents":              app_fee_cents,
        "computed_percent":              commission.get("computed_percent"),
        "commission_source":            commission.get("source"),
        "merchant_net_estimate_cents": merchant_net_est,
        "stripe_fee_estimate_cents":  stripe_fee_estimate,
        "transaction_id":                  txn_id,
        "modifiers":                            applied_modifiers,
        "merchant": {
            "name":          biz.get("name"),
            "logo_url":  biz.get("logo_url"),
        },
        "link": {
            "title":                link.get("title"),
            "description":  link.get("description"),
            "table_number": link.get("table_number"),
        },
    }


# ─── Event handlers ──────────────────────────────────────────────
async def handle_payment_intent_succeeded(db, intent_dict: dict) -> dict:
    """Idempotent — safe to re-run.  Fired from webhook + polling fallback."""
    intent_id = intent_dict.get("id")
    charge_id = None
    latest_charge = intent_dict.get("latest_charge")
    if isinstance(latest_charge, dict):
        charge_id = latest_charge.get("id")
    elif isinstance(latest_charge, str):
        charge_id = latest_charge
    payment_method_type = None
    payment_method = intent_dict.get("payment_method")
    if isinstance(payment_method, dict):
        payment_method_type = payment_method.get("type")
    if not payment_method_type:
        # Try charges.data[0].payment_method_details.type
        charges = intent_dict.get("charges") or {}
        data = charges.get("data") if isinstance(charges, dict) else None
        if data:
            pmd = (data[0] or {}).get("payment_method_details") or {}
            payment_method_type = pmd.get("type")

    tx = await db.payment_transactions_v2.find_one(
        {"stripe_payment_intent_id": intent_id})
    if not tx:
        logger.warning(f"[sc5] webhook: no tx row for intent={intent_id}")
        return {"handled": False, "reason": "no_local_row"}

    # Idempotency guard
    if tx.get("status") == "succeeded":
        return {"handled": True, "reason": "already_succeeded",
                    "transaction_id": tx["transaction_id"]}

    now = _now()
    updates = {
        "status":                        "succeeded",
        "succeeded_at":            now,
        "stripe_charge_id":    charge_id,
        "payment_method_type": payment_method_type,
    }
    await db.payment_transactions_v2.update_one(
        {"stripe_payment_intent_id": intent_id}, {"$set": updates})

    # 1. SC.3 audit — fires HERE on real money.
    # SC.6 fix — use the REAL category snapshotted at intent creation
    # (was `_sc5_charge` sentinel, causing 10% fallback in the audit).
    audit_category = tx.get("category_at_charge") or "_sc5_charge"
    try:
        await calculate_platform_fee(
            db,
            merchant_id=tx["merchant_id"],
            category=audit_category,
            transaction_type=tx["transaction_type"],
            amount_cents=tx["amount_cents"],
            market=None,
            campaign_type=None,
            write_audit=True,
        )
    except Exception:
        logger.exception("[sc5] audit-log write failed (non-blocking)")

    # 2. Increment link usage_count atomically
    try:
        await db.merchant_payment_links.update_one(
            {"link_id": tx["link_id"]},
            {"$inc": {"usage_count": 1},
              "$set": {"last_success_at": now}})
    except Exception:
        logger.exception("[sc5] usage_count bump failed (non-blocking)")

    # 3. Points award — authenticated customers only
    points_earned = 0
    if tx.get("customer_user_id"):
        try:
            from services.points_service import PointsService
            svc = PointsService(db)
            # 1 point per major currency unit (e.g. 1 AED = 1 point)
            delta = max(1, int(tx["amount_cents"] / 100))
            res = await svc.award(
                user_id=tx["customer_user_id"],
                source="payment_transaction",
                source_id=tx["transaction_id"],
                delta=delta,
                metadata={"merchant_id": tx["merchant_id"],
                                    "link_id": tx["link_id"],
                                    "amount_cents": tx["amount_cents"]},
                idempotency_key=f"sc5_pts_{tx['transaction_id']}",
                enforce_caps=False,
            )
            if isinstance(res, dict) and res.get("delta"):
                points_earned = int(res["delta"])
            else:
                points_earned = delta
        except Exception:
            logger.exception("[sc5] points award failed (non-blocking)")

    if points_earned:
        await db.payment_transactions_v2.update_one(
            {"stripe_payment_intent_id": intent_id},
            {"$set": {"points_earned": points_earned}})

    # 4. Mailgun receipt (guests + authenticated) — best-effort
    if tx.get("customer_email"):
        await _send_receipt(db, tx, points_earned=points_earned)

    # 5. Phase MER.3 — mint wallet item on gift_card/prepaid_meal purchase
    # + consume any applied checkout modifiers.  Non-blocking.
    try:
        # Refresh tx to include the fields we just wrote (esp. `modifiers`
        # if the intent was created with them).
        fresh_tx = await db.payment_transactions_v2.find_one(
            {"transaction_id": tx["transaction_id"]})
        if fresh_tx:
            from services.wallet_v2_service import on_payment_succeeded_mer3
            await on_payment_succeeded_mer3(db, tx=fresh_tx)
    except Exception:
        logger.exception("[sc5] MER.3 post-succeeded hook failed (non-blocking)")

    logger.info(f"[sc5] SUCCEEDED intent={intent_id} tx={tx['transaction_id']} "
                          f"mid={tx['merchant_id']} amount={tx['amount_cents']} "
                          f"fee={tx['application_fee_cents']} pts={points_earned}")
    return {"handled": True, "transaction_id": tx["transaction_id"],
              "points_earned": points_earned}


async def handle_payment_intent_failed(db, intent_dict: dict) -> dict:
    intent_id = intent_dict.get("id")
    err_obj = intent_dict.get("last_payment_error") or {}
    reason = err_obj.get("message") or err_obj.get("code") or "unknown"
    tx = await db.payment_transactions_v2.find_one(
        {"stripe_payment_intent_id": intent_id})
    if not tx:
        return {"handled": False, "reason": "no_local_row"}
    if tx.get("status") in ("succeeded", "refunded"):
        return {"handled": True, "reason": "already_terminal"}
    await db.payment_transactions_v2.update_one(
        {"stripe_payment_intent_id": intent_id},
        {"$set": {"status": "failed", "failed_at": _now(),
                        "failure_reason": reason}})
    logger.info(f"[sc5] FAILED intent={intent_id} tx={tx['transaction_id']} reason={reason}")
    return {"handled": True, "transaction_id": tx["transaction_id"],
              "failure_reason": reason}


async def handle_payment_intent_canceled(db, intent_dict: dict) -> dict:
    intent_id = intent_dict.get("id")
    tx = await db.payment_transactions_v2.find_one(
        {"stripe_payment_intent_id": intent_id})
    if not tx:
        return {"handled": False, "reason": "no_local_row"}
    if tx.get("status") in ("succeeded", "refunded"):
        return {"handled": True, "reason": "already_terminal"}
    await db.payment_transactions_v2.update_one(
        {"stripe_payment_intent_id": intent_id},
        {"$set": {"status": "canceled", "failed_at": _now()}})
    logger.info(f"[sc5] CANCELED intent={intent_id} tx={tx['transaction_id']}")
    return {"handled": True, "transaction_id": tx["transaction_id"]}


# ─── Mailgun receipt ─────────────────────────────────────────────
async def _send_receipt(db, tx: dict, *, points_earned: int = 0) -> None:
    try:
        from services.mailgun_client import send_email, is_live
        if not is_live():
            logger.info("[sc5] mailgun not live — receipt skipped for "
                                  f"tx={tx['transaction_id']}")
            return
        biz = await db.businesses.find_one({"$or": [
            {"business_id": tx["merchant_id"]}, {"_id": tx["merchant_id"]}]})
        merchant_name = (biz or {}).get("name") or "the merchant"
        amount_str = f"{tx['amount_cents']/100:.2f} {tx['currency']}"
        subject = f"Your FUUSIC receipt — {merchant_name}"
        pts_line = (f"<p style='color:#059669'><b>+{points_earned} FUUSIC points</b> added to your wallet 🎉</p>"
                          if points_earned else "")
        html = (
            f"<div style='font-family:system-ui,sans-serif;color:#111'>"
            f"<h2 style='color:#7c3aed'>Payment successful</h2>"
            f"<p>Thanks for paying <b>{merchant_name}</b> through FUUSIC.</p>"
            f"<table cellpadding='6' style='margin-top:12px;border-collapse:collapse'>"
            f"<tr><td style='color:#666'>Amount</td><td><b>{amount_str}</b></td></tr>"
            f"<tr><td style='color:#666'>Item</td><td>{tx.get('transaction_type','payment')}</td></tr>"
            f"<tr><td style='color:#666'>Reference</td><td><code>{tx['transaction_id']}</code></td></tr>"
            f"<tr><td style='color:#666'>Date</td><td>{_now().strftime('%Y-%m-%d %H:%M UTC')}</td></tr>"
            f"</table>"
            f"{pts_line}"
            f"<p style='color:#666;font-size:12px;margin-top:20px'>— FUUSIC Team</p>"
            f"</div>"
        )
        text = (f"Payment successful — {amount_str} to {merchant_name}\n"
                    f"Reference: {tx['transaction_id']}\n"
                    + (f"+{points_earned} FUUSIC points added\n" if points_earned else "")
                    + "— FUUSIC Team")
        send_email(to=tx["customer_email"], subject=subject,
                          html=html, text=text, tags=["sc5_receipt"])
        logger.info(f"[sc5] receipt sent to={tx['customer_email']} tx={tx['transaction_id']}")
    except Exception:
        logger.exception("[sc5] receipt send failed (non-blocking)")


# ─── Poll helper (called from /confirm-poll endpoint) ────────────
async def poll_intent_and_sync(db, *, intent_id: str) -> dict:
    """Fetch fresh Stripe intent state, and if it's terminal + our local
    row hasn't caught up yet, run the appropriate handler."""
    _init_stripe()
    try:
        intent = stripe.PaymentIntent.retrieve(
            intent_id,
            expand=["latest_charge", "payment_method"])
    except stripe.StripeError as e:
        raise PaymentError("stripe_retrieve_failed", detail=str(e),
                                              http_status=502)
    intent_dict = intent.to_dict() if hasattr(intent, "to_dict") else dict(intent)
    st = intent_dict.get("status")
    handler_result = {"handled": False}
    if st == "succeeded":
        handler_result = await handle_payment_intent_succeeded(db, intent_dict)
    elif st in ("canceled",):
        handler_result = await handle_payment_intent_canceled(db, intent_dict)
    elif st in ("requires_payment_method",) \
              and intent_dict.get("last_payment_error"):
        handler_result = await handle_payment_intent_failed(db, intent_dict)

    tx = await db.payment_transactions_v2.find_one(
        {"stripe_payment_intent_id": intent_id})
    return {
        "intent_id":        intent_id,
        "stripe_status": st,
        "local_status":  tx.get("status") if tx else None,
        "transaction_id": tx.get("transaction_id") if tx else None,
        "handler_result": handler_result,
    }


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_payment_txn_indexes(db) -> None:
    await db.payment_transactions_v2.create_index(
        "stripe_payment_intent_id", unique=True)
    await db.payment_transactions_v2.create_index(
        [("merchant_id", 1), ("created_at", -1)])
    await db.payment_transactions_v2.create_index(
        [("link_id", 1), ("status", 1)])
    await db.payment_transactions_v2.create_index(
        [("customer_user_id", 1), ("succeeded_at", -1)], sparse=True)


__all__ = [
    "create_payment_intent_for_link",
    "handle_payment_intent_succeeded",
    "handle_payment_intent_failed",
    "handle_payment_intent_canceled",
    "poll_intent_and_sync",
    "ensure_payment_txn_indexes",
    "PaymentError",
]
