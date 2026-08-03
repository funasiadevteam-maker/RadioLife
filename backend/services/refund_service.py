"""Phase SC.6 — Refund Service.

Full and partial refunds against `payment_transactions_v2` rows.
Refunds are async — we insert the local row status="requested", call
`stripe.Refund.create(...)`, then wait for `charge.refunded` webhook
(or `charge.updated`) to flip the local row to "succeeded" and update
the transaction ledger + write a negative-fee audit row.

Merchant-initiated refunds default to `refund_application_fee=False`
(platform keeps commission).  Admin-initiated refunds default to
`refund_application_fee=True`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe

logger = logging.getLogger("bigfm.refund_sc6")

VALID_REASONS = {"duplicate", "fraudulent", "requested_by_customer",
                                "expired_uncaptured_charge"}

# ─── Errors ──────────────────────────────────────────────────────
class RefundError(Exception):
    def __init__(self, code: str, detail: Optional[str] = None,
                            http_status: int = 400):
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.http_status = http_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _init_stripe() -> None:
    if not stripe.api_key:
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()


# ─── Amount computation ──────────────────────────────────────────
async def _remaining_refundable_cents(db, tx: dict) -> int:
    """Total amount minus already-succeeded refunds on this tx."""
    total = int(tx.get("amount_cents") or 0)
    cursor = db.refunds.find(
        {"transaction_id": tx["transaction_id"],
          "status": {"$in": ["succeeded", "processing", "requested"]}})
    already = 0
    async for r in cursor:
        already += int(r.get("amount_cents") or 0)
    return max(0, total - already)


# ─── Create refund ───────────────────────────────────────────────
async def create_refund(db, *, transaction_id: str,
                                            amount_cents: Optional[int] = None,
                                            reason: str = "requested_by_customer",
                                            refund_application_fee: Optional[bool] = None,
                                            requested_by_user_id: Optional[str] = None,
                                            requested_by_role: str = "admin",
                                            note: Optional[str] = None) -> dict:
    _init_stripe()

    if reason not in VALID_REASONS:
        raise RefundError("invalid_reason",
                                          detail=f"reason must be one of {sorted(VALID_REASONS)}")

    tx = await db.payment_transactions_v2.find_one(
        {"transaction_id": transaction_id})
    if not tx:
        raise RefundError("transaction_not_found", http_status=404)
    if tx.get("status") not in ("succeeded", "refunded"):
        raise RefundError("transaction_not_refundable",
                                          detail=f"status={tx.get('status')}",
                                          http_status=400)
    if not tx.get("stripe_payment_intent_id"):
        raise RefundError("missing_intent", http_status=400)

    remaining = await _remaining_refundable_cents(db, tx)
    if remaining <= 0:
        raise RefundError("already_fully_refunded", http_status=400)

    # Default amount = full remaining
    if amount_cents is None or amount_cents <= 0:
        amount_cents = remaining
    amount_cents = int(amount_cents)
    if amount_cents > remaining:
        raise RefundError("amount_exceeds_remaining",
                                          detail=f"remaining={remaining}", http_status=400)

    # Default refund_application_fee per initiator
    if refund_application_fee is None:
        refund_application_fee = (requested_by_role == "admin")

    refund_id = f"rf_{uuid.uuid4().hex[:16]}"
    idempotency = f"refund_{refund_id}"
    now = _now()

    # Insert local row FIRST — status="requested"
    doc = {
        "_id":                                    refund_id,
        "refund_id":                        refund_id,
        "transaction_id":                transaction_id,
        "merchant_id":                    tx.get("merchant_id"),
        "link_id":                              tx.get("link_id"),
        "stripe_payment_intent_id": tx.get("stripe_payment_intent_id"),
        "stripe_charge_id":              tx.get("stripe_charge_id"),
        "stripe_connected_account_id": tx.get("stripe_connected_account_id"),
        "stripe_refund_id":              None,
        "amount_cents":                    amount_cents,
        "currency":                            tx.get("currency"),
        "refund_application_fee": bool(refund_application_fee),
        "application_fee_refund_cents": None,
        "status":                              "requested",
        "reason":                              reason,
        "note":                                  (note or "")[:500],
        "requested_by_user_id":  requested_by_user_id,
        "requested_by_role":        requested_by_role,
        "failure_reason":                None,
        "idempotency_key":            idempotency,
        "created_at":                      now,
        "succeeded_at":                  None,
        "failed_at":                        None,
    }
    await db.refunds.insert_one(doc)

    # Call Stripe.  If it fails, mark local row failed.
    try:
        # For destination charges, refunding the application fee requires
        # `reverse_transfer=True` so Stripe pulls the money back from the
        # connected account.
        stripe_kwargs = dict(
            payment_intent=tx["stripe_payment_intent_id"],
            amount=amount_cents,
            reason=reason,
            metadata={"bigfm_refund_id":        refund_id,
                                "bigfm_transaction_id": transaction_id,
                                "bigfm_role":                    requested_by_role,
                                "bigfm_note":                    (note or "")[:200]},
            idempotency_key=idempotency,
        )
        if refund_application_fee:
            stripe_kwargs["refund_application_fee"] = True
            stripe_kwargs["reverse_transfer"] = True
        else:
            # Keep the connected-account balance intact — still reverse
            # the transfer proportionally so the connected account doesn't
            # go negative (platform keeps commission on the refunded amount).
            stripe_kwargs["reverse_transfer"] = True
        r = stripe.Refund.create(**stripe_kwargs)
    except stripe.StripeError as e:
        await db.refunds.update_one(
            {"refund_id": refund_id},
            {"$set": {"status": "failed", "failed_at": _now(),
                              "failure_reason": str(e)[:500]}})
        logger.exception("[sc6] stripe.Refund.create failed")
        raise RefundError("stripe_refund_failed", detail=str(e),
                                          http_status=502)

    # Stripe returned — update local row
    stripe_refund_id = getattr(r, "id", None) or r.get("id")
    stripe_status = getattr(r, "status", None) or r.get("status") or "pending"
    # Stripe statuses: pending, succeeded, failed, canceled
    local_status = ("succeeded" if stripe_status == "succeeded"
                                    else ("failed" if stripe_status == "failed"
                                                    else "processing"))
    updates = {
        "stripe_refund_id":                stripe_refund_id,
        "status":                                    local_status,
    }
    if local_status == "succeeded":
        updates["succeeded_at"] = _now()
    await db.refunds.update_one({"refund_id": refund_id},
                                                          {"$set": updates})

    logger.info(f"[sc6] refund created rid={refund_id} sid={stripe_refund_id} "
                          f"tx={transaction_id} amount={amount_cents} status={local_status}")

    # If Stripe returned succeeded synchronously, run the finalize
    if local_status == "succeeded":
        await _finalize_refund(db, refund_id=refund_id)

    return {"refund_id": refund_id,
                  "stripe_refund_id": stripe_refund_id,
                  "amount_cents": amount_cents,
                  "status": local_status,
                  "refund_application_fee": bool(refund_application_fee)}


# ─── Webhook handler: charge.refunded ────────────────────────────
async def handle_charge_refunded(db, charge_dict: dict) -> dict:
    """Fired by Stripe when any refund on this charge succeeds.
    `charge_dict.refunds.data` contains ALL refunds — we look up
    ours by `metadata.bigfm_refund_id` and finalize."""
    charge_id = charge_dict.get("id")
    payment_intent_id = charge_dict.get("payment_intent")
    refunds = ((charge_dict.get("refunds") or {}).get("data")) or []
    if not refunds:
        # Bare event without expanded refunds — look up tx anyway
        return {"handled": False, "reason": "no_refunds_array"}

    handled_any = False
    for r in refunds:
        r_status = r.get("status")
        if r_status != "succeeded":
            continue
        stripe_refund_id = r.get("id")
        bigfm_refund_id = ((r.get("metadata") or {}).get("bigfm_refund_id"))
        # Find local row via idempotency_key OR stripe_refund_id
        local = None
        if bigfm_refund_id:
            local = await db.refunds.find_one({"refund_id": bigfm_refund_id})
        if not local and stripe_refund_id:
            local = await db.refunds.find_one(
                {"stripe_refund_id": stripe_refund_id})
        if not local and charge_id:
            # External refund initiated from Stripe dashboard — auto-create
            tx = await db.payment_transactions_v2.find_one(
                {"stripe_charge_id": charge_id})
            if tx:
                await _create_external_refund_row(
                    db, tx=tx, stripe_refund_obj=r)
                local = await db.refunds.find_one(
                    {"stripe_refund_id": stripe_refund_id})

        if not local:
            logger.warning(f"[sc6] webhook: no local row for refund={stripe_refund_id}")
            continue

        if local.get("status") == "succeeded":
            handled_any = True
            continue

        await db.refunds.update_one(
            {"refund_id": local["refund_id"]},
            {"$set": {"stripe_refund_id": stripe_refund_id,
                              "status": "succeeded",
                              "succeeded_at": _now()}})
        await _finalize_refund(db, refund_id=local["refund_id"])
        handled_any = True

    _ = payment_intent_id  # unused but kept for readability
    return {"handled": handled_any}


async def _create_external_refund_row(db, *, tx: dict,
                                                                            stripe_refund_obj: dict) -> None:
    """Stripe Dashboard refund landed via webhook — mirror it locally."""
    refund_id = f"rf_{uuid.uuid4().hex[:16]}"
    await db.refunds.insert_one({
        "_id":                                    refund_id,
        "refund_id":                        refund_id,
        "transaction_id":                tx["transaction_id"],
        "merchant_id":                    tx.get("merchant_id"),
        "link_id":                              tx.get("link_id"),
        "stripe_payment_intent_id": tx.get("stripe_payment_intent_id"),
        "stripe_charge_id":              tx.get("stripe_charge_id"),
        "stripe_connected_account_id": tx.get("stripe_connected_account_id"),
        "stripe_refund_id":              stripe_refund_obj.get("id"),
        "amount_cents":                    int(stripe_refund_obj.get("amount") or 0),
        "currency":                            (stripe_refund_obj.get("currency") or "usd").upper(),
        "refund_application_fee": False,      # unknown — Stripe dashboard default is False
        "application_fee_refund_cents": None,
        "status":                              "requested",
        "reason":                              stripe_refund_obj.get("reason") or "requested_by_customer",
        "note":                                  "External refund via Stripe dashboard",
        "requested_by_user_id":  None,
        "requested_by_role":        "external",
        "failure_reason":                None,
        "idempotency_key":            f"external_{stripe_refund_obj.get('id')}",
        "created_at":                      _now(),
        "succeeded_at":                  None,
        "failed_at":                        None,
    })


async def _finalize_refund(db, *, refund_id: str) -> None:
    """Idempotent — update tx ledger + write negative audit row."""
    refund = await db.refunds.find_one({"refund_id": refund_id})
    if not refund:
        return
    tx = await db.payment_transactions_v2.find_one(
        {"transaction_id": refund["transaction_id"]})
    if not tx:
        return

    # Sum all succeeded refunds
    total_refunded = 0
    cursor = db.refunds.find(
        {"transaction_id": refund["transaction_id"],
          "status": "succeeded"})
    async for r in cursor:
        total_refunded += int(r.get("amount_cents") or 0)

    # Update tx: if full refund, status="refunded"; if partial, status="succeeded"
    # but track refunded_cents
    is_full = total_refunded >= int(tx.get("amount_cents") or 0)
    updates = {
        "refunded_cents":  total_refunded,
        "last_refund_at": _now(),
    }
    if is_full:
        updates["status"] = "refunded"
    await db.payment_transactions_v2.update_one(
        {"transaction_id": refund["transaction_id"]},
        {"$set": updates})

    # Write NEGATIVE audit-log row so admin ledger reflects the reversal
    try:
        from services.commission_service import _now as _cs_now  # noqa
    except Exception:
        pass
    try:
        # Direct insert — sidestep re-computation
        aid = f"cau_{uuid.uuid4().hex[:16]}"
        # Fee reversed proportionally when refund_application_fee=True
        fee_reversal_cents = 0
        if refund.get("refund_application_fee"):
            total_amt = int(tx.get("amount_cents") or 0)
            total_fee = int(tx.get("application_fee_cents") or 0)
            if total_amt > 0:
                fee_reversal_cents = int(round(
                    total_fee * (int(refund["amount_cents"]) / total_amt)))
                fee_reversal_cents = -fee_reversal_cents   # negative
        await db.commission_audit_log.insert_one({
            "_id":                                aid,
            "audit_id":                        aid,
            "merchant_id":                tx.get("merchant_id"),
            "category":                      tx.get("category_at_charge")
                                                          or "refund",
            "transaction_type":      f"refund_{tx.get('transaction_type') or 'payment'}",
            "market":                          None,
            "campaign_type":              None,
            "amount_cents":              -int(refund["amount_cents"]),
            "resolved_rule_id":      tx.get("commission_rule_id"),
            "resolved_override_id": tx.get("commission_override_id"),
            "computed_commission_cents": fee_reversal_cents,
            "breakdown_json":            {
                "refund_id": refund["refund_id"],
                "stripe_refund_id": refund.get("stripe_refund_id"),
                "refund_application_fee": bool(refund.get("refund_application_fee")),
                "original_tx_id": refund["transaction_id"],
            },
            "computed_at":                _now(),
            "event_kind":                  "refund",
        })
    except Exception:
        logger.exception("[sc6] refund audit-log insert failed (non-blocking)")

    # Application fee refund fields
    if refund.get("refund_application_fee"):
        total_amt = int(tx.get("amount_cents") or 0)
        total_fee = int(tx.get("application_fee_cents") or 0)
        if total_amt > 0:
            fee_ref = int(round(
                total_fee * (int(refund["amount_cents"]) / total_amt)))
            await db.refunds.update_one(
                {"refund_id": refund_id},
                {"$set": {"application_fee_refund_cents": fee_ref}})

    logger.info(f"[sc6] refund FINALIZED rid={refund_id} "
                          f"tx={refund['transaction_id']} amount={refund['amount_cents']} "
                          f"total_refunded={total_refunded} full={is_full}")

    # Phase MER.4 — best-effort reverse-modifiers on FULL refund.
    # Non-blocking: any exception here is logged, refund still finalises.
    try:
        from services.mer4_refund_reversal_service import (
            maybe_reverse_on_refund_finalized as _mer4_reverse)
        await _mer4_reverse(db, refund=await db.refunds.find_one(
            {"refund_id": refund_id}))
    except Exception:
        logger.exception("[sc6→mer4] refund-reversal hook failed (non-blocking)")


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_refund_indexes(db) -> None:
    await db.refunds.create_index("refund_id", unique=True)
    await db.refunds.create_index(
        "stripe_refund_id", unique=True,
        partialFilterExpression={"stripe_refund_id": {"$type": "string"}})
    await db.refunds.create_index([("transaction_id", 1), ("created_at", -1)])
    await db.refunds.create_index([("merchant_id", 1), ("created_at", -1)])
    await db.refunds.create_index([("status", 1), ("created_at", -1)])


__all__ = [
    "create_refund",
    "handle_charge_refunded",
    "ensure_refund_indexes",
    "RefundError",
    "VALID_REASONS",
]
