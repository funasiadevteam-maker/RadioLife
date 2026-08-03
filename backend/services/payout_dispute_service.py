"""Phase SC.6 — Payout Ledger + Dispute Tracking + account.updated push.

Handlers for Stripe Connect events:
  - `transfer.created` → seed `merchant_payout_ledger` row status=pending
  - `payout.paid`         → flip to status=paid + arrival_date
  - `payout.failed`      → flip to status=failed + failure_code/reason
  - `charge.dispute.created` → insert into `stripe_disputes`, fire Mailgun
  - `charge.dispute.closed`  → update dispute with resolution
  - `charge.updated`          → sync stripe fee actual + balance transaction
  - `account.updated`      → PUSH-model sync of businesses.stripe_* fields
  - `application_fee.created` → informational log
  - `application_fee.refunded` → mirror in audit log
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.payout_dispute_sc6")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _from_ts(ts) -> Optional[datetime]:
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except Exception:
        return None


# ─── Merchant lookup by connected account id ─────────────────────
async def _find_merchant_by_account(db, account_id: str) -> Optional[dict]:
    if not account_id:
        return None
    return await db.businesses.find_one({"stripe_account_id": account_id})


# ─── transfer.created ────────────────────────────────────────────
async def handle_transfer_created(db, obj: dict) -> dict:
    """Platform → connected account transfer.  For destination charges
    with `transfer_data.destination` this fires automatically."""
    transfer_id = obj.get("id")
    dest = obj.get("destination")
    biz = await _find_merchant_by_account(db, dest)
    merchant_id = (biz.get("business_id") or biz.get("_id")) if biz else None

    # Store transfer as a leading record (payout will follow later)
    await db.merchant_transfers.update_one(
        {"stripe_transfer_id": transfer_id},
        {"$setOnInsert": {
            "_id":                                    transfer_id,
            "stripe_transfer_id":            transfer_id,
            "merchant_id":                    merchant_id,
            "stripe_connected_account_id": dest,
            "amount_cents":                    int(obj.get("amount") or 0),
            "currency":                            (obj.get("currency") or "usd").upper(),
            "source_transaction":        obj.get("source_transaction"),
            "created_at":                      _from_ts(obj.get("created")) or _now(),
        }},
        upsert=True,
    )
    logger.info(f"[sc6] transfer.created id={transfer_id} mid={merchant_id}")
    return {"handled": True, "transfer_id": transfer_id,
                  "merchant_id": merchant_id}


# ─── payout.* ───────────────────────────────────────────────────
async def handle_payout_event(db, obj: dict, *,
                                                          event_type: str,
                                                          stripe_account: Optional[str]) -> dict:
    """`payout.created / .paid / .failed` — these fire on the CONNECTED
    account, so the `stripe-account` header identifies the merchant."""
    payout_id = obj.get("id")
    biz = await _find_merchant_by_account(db, stripe_account)
    merchant_id = (biz.get("business_id") or biz.get("_id")) if biz else None

    status_map = {
        "payout.created":  ("pending", "created_at"),
        "payout.paid":        ("paid",      "paid_at"),
        "payout.failed":    ("failed",    "failed_at"),
        "payout.canceled": ("canceled", "failed_at"),
        "payout.updated":  (obj.get("status") or "pending", "updated_at"),
    }
    status, ts_key = status_map.get(event_type, ("pending", "updated_at"))
    if event_type == "payout.paid" and obj.get("status") != "paid":
        status = obj.get("status") or "in_transit"

    now = _now()
    arrival = _from_ts(obj.get("arrival_date"))
    common_set = {
        "merchant_id":                    merchant_id,
        "stripe_payout_id":            payout_id,
        "stripe_connected_account_id": stripe_account,
        "amount_cents":                    int(obj.get("amount") or 0),
        "currency":                            (obj.get("currency") or "usd").upper(),
        "status":                              status,
        "method":                              obj.get("method") or "standard",
        "type":                                  obj.get("type") or "bank_account",
        "description":                    obj.get("description"),
        "failure_code":                  obj.get("failure_code"),
        "failure_reason":                obj.get("failure_message")
                                                          or obj.get("failure_reason"),
        "arrival_date":                  arrival,
        "updated_at":                      now,
        ts_key:                                  now,
    }

    await db.merchant_payout_ledger.update_one(
        {"stripe_payout_id": payout_id},
        {"$set":                common_set,
          "$setOnInsert": {"_id":                    f"po_{uuid.uuid4().hex[:16]}",
                                        "payout_id":          f"po_{uuid.uuid4().hex[:16]}",
                                        "created_at":          _from_ts(obj.get("created")) or now}},
        upsert=True,
    )

    logger.info(f"[sc6] {event_type} sid={payout_id} mid={merchant_id} "
                          f"amount={obj.get('amount')} status={status}")
    return {"handled": True, "payout_id": payout_id,
                  "merchant_id": merchant_id, "status": status}


# ─── charge.dispute.created / closed ─────────────────────────────
async def handle_dispute_created(db, obj: dict) -> dict:
    dispute_id = obj.get("id")
    charge_id = obj.get("charge")
    tx = None
    if charge_id:
        tx = await db.payment_transactions_v2.find_one(
            {"stripe_charge_id": charge_id})

    now = _now()
    doc_id = f"dsp_{uuid.uuid4().hex[:16]}"
    dispute_amount = int(obj.get("amount") or 0)
    await db.stripe_disputes.update_one(
        {"stripe_dispute_id": dispute_id},
        {"$set": {
            "stripe_dispute_id":  dispute_id,
            "transaction_id":        tx.get("transaction_id") if tx else None,
            "merchant_id":            tx.get("merchant_id") if tx else None,
            "stripe_charge_id":  charge_id,
            "amount_cents":            dispute_amount,
            "currency":                    (obj.get("currency") or "usd").upper(),
            "reason":                        obj.get("reason"),
            "status":                        obj.get("status") or "warning_needs_response",
            "evidence_due_by":  _from_ts(obj.get("evidence_details", {}).get("due_by"))
                                                      if isinstance(obj.get("evidence_details"), dict)
                                                      else None,
            "evidence_details_json": obj.get("evidence_details"),
            "updated_at":              now,
        },
          "$setOnInsert": {
            "_id":                            doc_id,
            "dispute_id":                doc_id,
            "created_at":                _from_ts(obj.get("created")) or now,
            "resolved_at":              None,
            "resolution":                None,
        }},
        upsert=True,
    )

    # Mailgun alert to merchant + admin
    await _send_dispute_alert(db, obj, tx=tx)

    logger.warning(f"[sc6] DISPUTE created sid={dispute_id} tx={tx.get('transaction_id') if tx else None} "
                                f"mid={tx.get('merchant_id') if tx else None} amount={dispute_amount} "
                                f"reason={obj.get('reason')}")
    return {"handled": True, "dispute_id": dispute_id,
                  "merchant_id": tx.get("merchant_id") if tx else None}


async def handle_dispute_closed(db, obj: dict) -> dict:
    dispute_id = obj.get("id")
    resolution = obj.get("status")  # won / lost / warning_closed
    await db.stripe_disputes.update_one(
        {"stripe_dispute_id": dispute_id},
        {"$set": {
            "status":                resolution,
            "resolution":        resolution,
            "resolved_at":    _now(),
            "updated_at":      _now(),
        }},
    )
    logger.info(f"[sc6] dispute.closed sid={dispute_id} resolution={resolution}")
    return {"handled": True, "dispute_id": dispute_id,
                  "resolution": resolution}


async def _send_dispute_alert(db, obj: dict, *, tx: Optional[dict]) -> None:
    try:
        from services.mailgun_client import send_email, is_live
        if not is_live():
            return
        merchant_email = None
        merchant_name = "your business"
        if tx:
            biz = await db.businesses.find_one({"$or": [
                {"business_id": tx["merchant_id"]},
                {"_id": tx["merchant_id"]}]})
            if biz:
                merchant_email = biz.get("owner_email")
                merchant_name = biz.get("name") or merchant_name
        admin_email = os.environ.get("MERCHANT_ADMIN_NOTIFY_EMAIL") \
                                    or "admin@bigfm.dubai"
        amount_str = f"{int(obj.get('amount') or 0)/100:.2f} {(obj.get('currency') or 'usd').upper()}"
        subject = f"⚠️ Dispute opened on {merchant_name} — {amount_str}"
        html = (f"<div style='font-family:system-ui,sans-serif'>"
                        f"<h2 style='color:#c026d3'>Payment disputed</h2>"
                        f"<p>A customer opened a dispute on a payment to <b>{merchant_name}</b>.</p>"
                        f"<table cellpadding='6' style='border-collapse:collapse'>"
                        f"<tr><td>Amount</td><td><b>{amount_str}</b></td></tr>"
                        f"<tr><td>Reason</td><td>{obj.get('reason','')}</td></tr>"
                        f"<tr><td>Status</td><td>{obj.get('status','')}</td></tr>"
                        f"<tr><td>Charge</td><td><code>{obj.get('charge','')}</code></td></tr>"
                        f"</table>"
                        f"<p style='margin-top:16px'>Please respond in your Stripe dashboard as soon as possible.</p>"
                        f"</div>")
        recipients = [admin_email]
        if merchant_email and merchant_email not in recipients:
            recipients.append(merchant_email)
        for to in recipients:
            send_email(to=to, subject=subject, html=html,
                              text=f"Dispute opened on {merchant_name} for {amount_str}",
                              tags=["sc6_dispute"])
    except Exception:
        logger.exception("[sc6] dispute alert failed (non-blocking)")


# ─── charge.updated — actual Stripe fee ──────────────────────────
async def handle_charge_updated(db, obj: dict) -> dict:
    charge_id = obj.get("id")
    balance_tx = obj.get("balance_transaction")
    if not charge_id:
        return {"handled": False, "reason": "no_charge_id"}
    updates = {}
    if isinstance(balance_tx, dict):
        fee = balance_tx.get("fee")
        if fee is not None:
            updates["stripe_fee_actual_cents"] = int(fee)
    if updates:
        await db.payment_transactions_v2.update_one(
            {"stripe_charge_id": charge_id}, {"$set": updates})
        logger.info(f"[sc6] charge.updated fee synced charge={charge_id} fee={updates.get('stripe_fee_actual_cents')}")
    return {"handled": bool(updates), "charge_id": charge_id}


# ─── application_fee.created / .refunded ─────────────────────────
async def handle_application_fee_created(db, obj: dict) -> dict:
    logger.info(f"[sc6] application_fee.created fee_id={obj.get('id')} "
                          f"amount={obj.get('amount')} charge={obj.get('charge')}")
    return {"handled": True, "informational": True}


async def handle_application_fee_refunded(db, obj: dict) -> dict:
    """Fired when we (or Stripe) refund a portion of the platform commission."""
    fee_refund = obj.get("id")
    charge_id = obj.get("charge") or obj.get("charge_id")
    amount = int(obj.get("amount") or obj.get("amount_refunded") or 0)
    if charge_id:
        tx = await db.payment_transactions_v2.find_one(
            {"stripe_charge_id": charge_id})
        if tx:
            # Additive — accumulate across partial fee refunds
            existing = int(tx.get("application_fee_refunded_cents") or 0)
            await db.payment_transactions_v2.update_one(
                {"transaction_id": tx["transaction_id"]},
                {"$set": {"application_fee_refunded_cents": existing + amount,
                                    "application_fee_last_refund_at": _now()}})
            logger.info(f"[sc6] application_fee.refunded charge={charge_id} amt={amount} "
                                  f"total_fee_refunded={existing + amount}")
            return {"handled": True, "transaction_id": tx["transaction_id"]}
    logger.info(f"[sc6] application_fee.refunded (no local tx) id={fee_refund}")
    return {"handled": False, "reason": "no_local_tx"}


# ─── account.updated ──────────────────────────────────────────────
async def handle_account_updated(db, obj: dict) -> dict:
    """PUSH-model complement to SC.1's pull-model refresh.  Both use
    the same `derive_onboarding_status` helper for consistent state."""
    account_id = obj.get("id")
    if not account_id:
        return {"handled": False, "reason": "no_account_id"}
    biz = await db.businesses.find_one({"stripe_account_id": account_id})
    if not biz:
        return {"handled": False, "reason": "no_local_business"}

    charges_enabled = bool(obj.get("charges_enabled"))
    payouts_enabled = bool(obj.get("payouts_enabled"))
    details_submitted = bool(obj.get("details_submitted"))
    reqs = obj.get("requirements") or {}
    currently_due = list(reqs.get("currently_due") or [])
    past_due = list(reqs.get("past_due") or [])
    disabled_reason = reqs.get("disabled_reason")
    capabilities = obj.get("capabilities") or None

    # Reuse SC.1's derive
    try:
        from services.stripe_connect_service import derive_onboarding_status
        current = biz.get("stripe_onboarding_status") or "onboarding_incomplete"
        derived = derive_onboarding_status(
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            details_submitted=details_submitted,
            currently_due=currently_due,
            past_due=past_due,
            disabled_reason=disabled_reason,
            current_status=current,
        )
    except Exception:
        derived = biz.get("stripe_onboarding_status") or "onboarding_incomplete"

    now = _now()
    await db.businesses.update_one(
        {"_id": biz["_id"]},
        {"$set": {
            "stripe_charges_enabled":            charges_enabled,
            "stripe_payouts_enabled":            payouts_enabled,
            "stripe_details_submitted":      details_submitted,
            "stripe_requirements_currently_due": currently_due,
            "stripe_requirements_past_due":  past_due,
            "stripe_requirements_disabled_reason": disabled_reason,
            "stripe_capabilities":                capabilities,
            "stripe_onboarding_status":      derived,
            "stripe_status_synced_at":          now,
        }})

    logger.info(f"[sc6] account.updated push mid={biz.get('business_id') or biz['_id']} "
                          f"acct={account_id} status={derived}")
    return {"handled": True, "merchant_id": biz.get("business_id") or biz["_id"],
                  "derived_status": derived}


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_sc6_indexes(db) -> None:
    await db.merchant_payout_ledger.create_index(
        "stripe_payout_id", unique=True)
    await db.merchant_payout_ledger.create_index(
        [("merchant_id", 1), ("created_at", -1)])
    await db.merchant_payout_ledger.create_index(
        [("status", 1), ("created_at", -1)])
    await db.merchant_transfers.create_index(
        "stripe_transfer_id", unique=True)
    await db.stripe_disputes.create_index(
        "stripe_dispute_id", unique=True)
    await db.stripe_disputes.create_index(
        [("merchant_id", 1), ("created_at", -1)])


__all__ = [
    "handle_transfer_created",
    "handle_payout_event",
    "handle_dispute_created",
    "handle_dispute_closed",
    "handle_charge_updated",
    "handle_application_fee_created",
    "handle_application_fee_refunded",
    "handle_account_updated",
    "ensure_sc6_indexes",
]
