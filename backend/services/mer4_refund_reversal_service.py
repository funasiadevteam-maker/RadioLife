"""Phase MER.4 — Reverse-modifiers refund service.

Fixes the SC.6 gap identified in MER.3: when a MER.3 transaction is
refunded, we need to give back the gift-card balance, meal count,
points, and coupon status that were consumed at checkout.

Two entry points:

1. `reverse_transaction_modifiers(tx_id, actor, note=)` — manual reversal
    called from the admin endpoint.  Guards on
    `tx.modifiers_reversed_at` for idempotency.

2. `maybe_reverse_on_refund_finalized(refund)` — invoked from the
    Track-1 `refund_service._finalize_refund` hook (one-liner extension
    at the end of the file, MER.4-authorized).  Only reverses when
    the refund is a FULL refund of the ORIGINAL amount, so partial
    refunds don't disturb consumed modifiers.

3. `refund_zero_charge(tx_id, actor, note=)` — for `mer3_zero_charge`
    synthetic txs which have no Stripe intent to unwind.  Purely
    reverses modifiers + marks tx `status="refunded"`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.mer4.reversal")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


class ReversalError(Exception):
    def __init__(self, code: str, http_status: int = 400,
                              detail: str = None):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.detail = detail or code


# ─── Per-type restorers ────────────────────────────────────────
async def _restore_gift_card(db, mod: dict, tx: dict) -> dict:
    gc_id = mod.get("reference_id")
    amt = int(mod.get("amount_reduced_cents") or 0)
    if not gc_id or amt <= 0:
        return {"ok": False, "reason": "invalid_modifier"}
    gc = await db.user_gift_cards.find_one({"gift_card_id": gc_id})
    if not gc:
        return {"ok": False, "reason": "gift_card_not_found"}
    now = _now()
    # Restore balance + un-deplete
    updates = {
        "$inc": {"current_balance_cents": amt},
        "$set": {"last_restore_at": now},
    }
    if gc.get("status") == "depleted":
        updates["$set"]["status"] = "active"
    await db.user_gift_cards.update_one({"gift_card_id": gc_id}, updates)
    reloaded = await db.user_gift_cards.find_one({"gift_card_id": gc_id})
    return {"ok": True, "gift_card_id": gc_id,
                  "new_balance_cents": int(reloaded.get("current_balance_cents") or 0),
                  "restored_cents": amt}


async def _restore_meal(db, mod: dict, tx: dict) -> dict:
    pack_id = mod.get("reference_id")
    if not pack_id:
        return {"ok": False, "reason": "invalid_modifier"}
    pm = await db.user_prepaid_meals.find_one({"meal_pack_id": pack_id})
    if not pm:
        return {"ok": False, "reason": "meal_pack_not_found"}
    now = _now()
    updates = {
        "$inc": {"remaining_meals": 1},
        "$set": {"last_restore_at": now},
    }
    if pm.get("status") == "depleted":
        updates["$set"]["status"] = "active"
    await db.user_prepaid_meals.update_one({"meal_pack_id": pack_id}, updates)
    reloaded = await db.user_prepaid_meals.find_one({"meal_pack_id": pack_id})
    return {"ok": True, "meal_pack_id": pack_id,
                  "remaining_meals": int(reloaded.get("remaining_meals") or 0),
                  "restored_meals": 1}


async def _restore_points(db, mod: dict, tx: dict) -> dict:
    user_id = tx.get("customer_user_id")
    burned = int(mod.get("points_burned") or 0)
    if not user_id or burned <= 0:
        return {"ok": False, "reason": "no_user_or_zero"}
    try:
        from services.bigcoin import award
        res = await award(
            db, user_id=user_id, amount=burned,
            source="mer4_modifier_reversed",
            metadata={"transaction_id": tx["transaction_id"],
                                "reversal": True,
                                "source_id": tx["transaction_id"]},
            note=f"Reverse-modifiers refund of {tx['transaction_id']}",
        )
        return {"ok": True, "points_credited": burned,
                      "balance_after": (res or {}).get("balance_after")}
    except Exception as e:
        logger.warning(f"[mer4] points award failed: {e}")
        return {"ok": False, "reason": "award_failed"}


async def _restore_coupon(db, mod: dict, tx: dict) -> dict:
    coupon_id = mod.get("reference_id")
    if not coupon_id:
        return {"ok": False, "reason": "invalid_modifier"}
    # Revert only if we (this tx) redeemed it
    c = await db.coupons.find_one({"coupon_id": coupon_id})
    if not c:
        return {"ok": False, "reason": "coupon_not_found"}
    if c.get("redeemed_at_transaction_id") != tx["transaction_id"]:
        return {"ok": False, "reason": "coupon_redeemed_by_other_tx"}
    if c.get("status") != "redeemed":
        return {"ok": False, "reason": f"invalid_status:{c.get('status')}"}
    now = _now()
    await db.coupons.update_one(
        {"coupon_id": coupon_id},
        {"$set": {"status": "saved",
                            "reverted_at": now,
                            "reverted_reason": "modifier_reversed"},
          "$unset": {"redeemed_at": "",
                              "redeemed_at_transaction_id": "",
                              "redeemed_at_merchant_id": ""}})
    return {"ok": True, "coupon_id": coupon_id, "status": "saved"}


# ─── Main reversal ────────────────────────────────────────────
async def reverse_transaction_modifiers(db, *, transaction_id: str,
                                                                              actor: dict,
                                                                              note: str = None,
                                                                              triggered_by: str = "manual") -> dict:
    """Idempotent — no-op on already-reversed tx.  Returns per-modifier
    result list.  Called from admin endpoint AND from the refund
    finalized hook."""
    tx = await db.payment_transactions_v2.find_one(
        {"transaction_id": transaction_id})
    if not tx:
        raise ReversalError("transaction_not_found", 404)

    # Idempotency guard
    if tx.get("modifiers_reversed_at"):
        return {"reversed": False, "reason": "already_reversed",
                      "reversed_at": _iso(tx["modifiers_reversed_at"])}

    mods = tx.get("modifiers") or []
    if not mods:
        return {"reversed": False, "reason": "no_modifiers"}

    results = []
    now = _now()
    reversal_batch_id = f"rev_{uuid.uuid4().hex[:16]}"
    for mod in mods:
        if not mod.get("ok"):
            continue          # skip failed modifiers
        mtype = mod.get("type")
        r = None
        if mtype == "gift_card":
            r = await _restore_gift_card(db, mod, tx)
        elif mtype == "prepaid_meal":
            r = await _restore_meal(db, mod, tx)
        elif mtype == "points":
            r = await _restore_points(db, mod, tx)
        elif mtype == "coupon":
            r = await _restore_coupon(db, mod, tx)
        else:
            r = {"ok": False, "reason": "unknown_type"}

        # Write reversal audit row (piggy-back on checkout_modifiers with
        # `kind:reversal` + `reversal_of:{original_modifier_id}`)
        try:
            aid = f"revmod_{uuid.uuid4().hex[:16]}"
            await db.checkout_modifiers.insert_one({
                "_id":                              aid,
                "modifier_id":              aid,
                "kind":                          "reversal",
                "reversal_of":              mod.get("modifier_id") or mod.get("reference_id"),
                "reversal_batch_id":  reversal_batch_id,
                "transaction_id":        transaction_id,
                "merchant_id":              tx.get("merchant_id"),
                "type":                          mtype,
                "reference_id":            mod.get("reference_id"),
                "code":                          mod.get("code"),
                "amount_restored_cents": int(mod.get("amount_reduced_cents") or 0),
                "applied_at":                now,
                "actor_user_id":          (actor or {}).get("user_id"),
                "actor_role":                (actor or {}).get("role"),
                "note":                          note,
                "triggered_by":            triggered_by,
                "result":                      r,
            })
        except Exception:
            logger.exception("[mer4] reversal audit insert failed (non-blocking)")

        results.append({"type": mtype,
                                      "reference_id": mod.get("reference_id"),
                                      "code": mod.get("code"),
                                      **(r or {})})
        logger.info(f"[mer4] reversed {mtype} ref={mod.get('reference_id')} "
                              f"tx={transaction_id} result={r}")

    # Stamp the tx so re-runs are no-ops
    await db.payment_transactions_v2.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"modifiers_reversed_at": now,
                            "modifiers_reversal_batch_id": reversal_batch_id,
                            "modifiers_reversal_triggered_by": triggered_by,
                            "modifiers_reversal_note": note}})

    return {"reversed": True,
                  "transaction_id": transaction_id,
                  "reversal_batch_id": reversal_batch_id,
                  "reversed_at": _iso(now),
                  "reversed_modifiers": results,
                  "count": len(results)}


# ─── Refund-hook helper ────────────────────────────────────────
async def maybe_reverse_on_refund_finalized(db, *, refund: dict) -> dict:
    """Called from `refund_service._finalize_refund` as a best-effort
    additive hook.  Reverses modifiers only when the refund covers the
    FULL original amount (partial refunds keep modifiers consumed)."""
    tx = await db.payment_transactions_v2.find_one(
        {"transaction_id": refund["transaction_id"]})
    if not tx:
        return {"reversed": False, "reason": "no_tx"}
    if not tx.get("modifiers"):
        return {"reversed": False, "reason": "no_modifiers"}
    if tx.get("modifiers_reversed_at"):
        return {"reversed": False, "reason": "already_reversed"}

    # Full refund only
    total_amt = int(tx.get("amount_cents") or 0)
    total_refunded = int(tx.get("refunded_cents") or 0)
    if total_refunded < total_amt:
        return {"reversed": False, "reason": "partial_refund",
                      "refunded_cents": total_refunded, "amount_cents": total_amt}

    return await reverse_transaction_modifiers(
        db, transaction_id=refund["transaction_id"],
        actor={"user_id": refund.get("requested_by_user_id"),
                    "role": refund.get("requested_by_role")},
        note=f"Auto-reversed by refund {refund['refund_id']}",
        triggered_by="refund_finalized")


# ─── Zero-charge refund ────────────────────────────────────────
async def refund_zero_charge(db, *, transaction_id: str,
                                                    actor: dict,
                                                    note: str = None) -> dict:
    """For `flow=mer3_zero_charge` txs — no Stripe intent to unwind.
    Reverses modifiers + marks tx status=refunded."""
    tx = await db.payment_transactions_v2.find_one(
        {"transaction_id": transaction_id})
    if not tx:
        raise ReversalError("transaction_not_found", 404)
    if tx.get("flow") != "mer3_zero_charge":
        raise ReversalError("not_zero_charge",
                                                detail="Use the standard refund endpoint for Stripe transactions.")
    if tx.get("status") == "refunded":
        return {"refunded": False, "reason": "already_refunded"}

    result = await reverse_transaction_modifiers(
        db, transaction_id=transaction_id, actor=actor, note=note,
        triggered_by="zero_charge_refund")

    now = _now()
    await db.payment_transactions_v2.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"status": "refunded",
                            "refunded_cents": int(tx.get("amount_cents") or 0),
                            "last_refund_at": now,
                            "refund_note": note}})
    logger.info(f"[mer4] zero-charge refund tx={transaction_id} "
                          f"reversed={result.get('count', 0)}")
    return {"refunded": True,
                  "transaction_id": transaction_id,
                  "refunded_at": _iso(now),
                  "reversal": result}


__all__ = [
    "reverse_transaction_modifiers",
    "maybe_reverse_on_refund_finalized",
    "refund_zero_charge",
    "ReversalError",
]
