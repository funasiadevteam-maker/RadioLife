"""Phase AD.7 — Scan-to-Pay at Partner Merchants.

Merchants generate ephemeral QR tokens; users scan them, pay with
POINTS + CARD (Stripe Connect destination charge), and earn points on
the card portion.  All settlement runs on the AD.2 split-pay rails
(payment_transactions_v2 shape) + existing SC.3 commission engine +
Points ledger (F-1 unified).

Points math
-----------
- 1 point == 1 cent when redeemed.  points_value_cents == points_to_use.
- points_earned = int(card_cents / 100 * points_per_dollar).
- Redemption cap: `points_value_cents ≤ total_cents * max_pct / 100`.
- Refund reverses BOTH sides: card via Stripe, points via ledger
  reversal, earned points clawed back via ledger reversal.

Idempotency
-----------
- QR token uniquely identifies an authorize request.  Repeated
  authorize on the same token returns the same transaction_id.
- Capture is idempotent by transaction_id.
- Refund is idempotent by transaction_id (records refunded_at once).
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from services.commission_service import calculate_platform_fee
from services.points_service import PointsService
from services.currency_util import currency_for_business

logger = logging.getLogger("bigfm.scan_to_pay")


QR_TTL_SECONDS               = 60
MIN_SCAN_AMOUNT_CENTS = 100
DEFAULT_POINTS_PER_DOLLAR    = 10
DEFAULT_MAX_POINTS_PCT       = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _gen_token() -> str:
    return f"stq_{secrets.token_urlsafe(16)}"


# ─── Indexes ────────────────────────────────────────────────────
async def ensure_scan_to_pay_indexes(db) -> None:
    try:
        await db.scan_to_pay_transactions.create_index("transaction_id",
                                                                                                            unique=True)
        await db.scan_to_pay_transactions.create_index("qr_token")
        await db.scan_to_pay_transactions.create_index([
            ("user_id", 1), ("created_at", -1)])
        await db.scan_to_pay_transactions.create_index("merchant_id")
        await db.scan_to_pay_transactions.create_index(
            "stripe_payment_intent_id", sparse=True)
        await db.scan_to_pay_qr_tokens.create_index("token", unique=True)
        # TTL — Mongo auto-expires the QR row 5 minutes after
        # `expires_at` (keeps history briefly for debugging).
        await db.scan_to_pay_qr_tokens.create_index(
            "expires_at", expireAfterSeconds=300)
    except Exception as e:
        logger.warning("[ad7] index setup: %s", e)


# ─── Settings helpers ───────────────────────────────────────────
def _merchant_scan_settings(biz: dict) -> Dict[str, Any]:
    """Read the scan-to-pay knobs off a `businesses` row with defaults."""
    return {
        "enabled":                                bool(biz.get("scan_to_pay_enabled")),
        "points_per_dollar":              int(biz.get("points_per_dollar")
                                                                              or DEFAULT_POINTS_PER_DOLLAR),
        "min_scan_to_pay_amount_cents": int(biz.get("min_scan_to_pay_amount_cents")
                                                                              or MIN_SCAN_AMOUNT_CENTS),
        "max_points_redemption_pct":  int(biz.get("max_points_redemption_pct")
                                                                              or DEFAULT_MAX_POINTS_PCT),
    }


async def update_merchant_settings(db, *, merchant_id: str,
                                                                              patch: Dict[str, Any]) -> Dict[str, Any]:
    sets: Dict[str, Any] = {}
    if "enabled" in patch:
        sets["scan_to_pay_enabled"] = bool(patch["enabled"])
    if "points_per_dollar" in patch:
        v = int(patch["points_per_dollar"] or 0)
        if v < 0 or v > 1000:
            raise ValueError("invalid_points_per_dollar")
        sets["points_per_dollar"] = v
    if "min_scan_to_pay_amount_cents" in patch:
        v = int(patch["min_scan_to_pay_amount_cents"] or 0)
        if v < 0:
            raise ValueError("invalid_min_amount")
        sets["min_scan_to_pay_amount_cents"] = v
    if "max_points_redemption_pct" in patch:
        v = int(patch["max_points_redemption_pct"] or 0)
        if v < 0 or v > 100:
            raise ValueError("invalid_max_points_pct")
        sets["max_points_redemption_pct"] = v
    if sets:
        r = await db.businesses.update_one(
            {"business_id": merchant_id}, {"$set": sets})
        if r.matched_count == 0:
            raise ValueError("merchant_not_found")
    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        raise ValueError("merchant_not_found")
    return _merchant_scan_settings(biz)


# ─── QR generation ──────────────────────────────────────────────
async def generate_qr(db, *, merchant_id: str, cashier_user_id: str,
                                          amount_cents: int,
                                          location_id: Optional[str] = None
                                          ) -> Dict[str, Any]:
    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        raise ValueError("merchant_not_found")
    settings = _merchant_scan_settings(biz)
    if not settings["enabled"]:
        raise ValueError("scan_to_pay_not_enabled")
    amount_cents = int(amount_cents or 0)
    if amount_cents < settings["min_scan_to_pay_amount_cents"]:
        raise ValueError("amount_below_min")
    if amount_cents > 10_000_00:                    # $10k hard cap for safety
        raise ValueError("amount_above_max")
    token = _gen_token()
    now = _now()
    expires_at = now + timedelta(seconds=QR_TTL_SECONDS)
    await db.scan_to_pay_qr_tokens.insert_one({
        "_id":                          token,
        "token":                      token,
        "merchant_id":            merchant_id,
        "location_id":            location_id,
        "cashier_user_id":    cashier_user_id,
        "amount_cents":          amount_cents,
        "created_at":              now,
        "expires_at":              expires_at,
        "consumed_at":            None,
        "transaction_id":      None,
    })
    return {
        "token":              token,
        "merchant_id":  merchant_id,
        "amount_cents": amount_cents,
        "expires_at":    expires_at.isoformat(),
        "expires_in_s": QR_TTL_SECONDS,
        # Client renders the QR from a shareable deep-link.
        "scan_url":      f"/scan-to-pay/{token}",
    }


async def resolve_qr(db, *, token: str, user_id: Optional[str]
                                          ) -> Dict[str, Any]:
    row = await db.scan_to_pay_qr_tokens.find_one({"token": token})
    if not row:
        raise ValueError("qr_not_found")
    now = _now()
    exp = row["expires_at"]
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        raise ValueError("qr_expired")
    if row.get("consumed_at"):
        raise ValueError("qr_already_used")
    biz = await db.businesses.find_one({"business_id": row["merchant_id"]})
    if not biz:
        raise ValueError("merchant_not_found")
    settings = _merchant_scan_settings(biz)
    # User's balance from the F-1 unified points engine.
    user_points = 0
    if user_id:
        user_points = await PointsService(db).get_balance(user_id)
    return {
        "token":                          token,
        "amount_cents":              int(row["amount_cents"]),
        "currency":                      currency_for_business(biz),
        "expires_at":                  exp.isoformat(),
        "merchant": {
            "merchant_id":            row["merchant_id"],
            "name":                          biz.get("name"),
            "logo_url":                    biz.get("logo_url"),
            "category":                    biz.get("category"),
            "currency":                    currency_for_business(biz),
            "location_id":            row.get("location_id"),
        },
        "settings": {
            "points_per_dollar":          settings["points_per_dollar"],
            "max_points_redemption_pct": settings["max_points_redemption_pct"],
        },
        "user_points_balance":  int(user_points),
    }


# ─── Quote (pure preview) ───────────────────────────────────────
def _compute_quote(*, amount_cents: int, tip_cents: int,
                                        points_to_use: int, points_per_dollar: int,
                                        max_pct: int, user_points_balance: int
                                        ) -> Dict[str, Any]:
    tip_cents = max(0, int(tip_cents or 0))
    total_cents = int(amount_cents) + tip_cents
    points_to_use = max(0, int(points_to_use or 0))
    # Cap by user balance.
    if points_to_use > user_points_balance:
        points_to_use = user_points_balance
    # Cap by merchant % cap.
    max_points_allowed = (total_cents * int(max_pct)) // 100
    if points_to_use > max_points_allowed:
        points_to_use = max_points_allowed
    points_value_cents = points_to_use
    card_cents = total_cents - points_value_cents
    if card_cents < 0:
        card_cents = 0
    # Earning rule: the SUBTOTAL earns only on its card-funded portion
    # (spending points never mints new points), but a TIP ALWAYS earns —
    # we reward the gesture even when BigPoints cover the whole bill.
    # Points are applied to the subtotal first, then the tip.
    points_on_subtotal = min(points_value_cents, int(amount_cents))
    subtotal_card_cents = int(amount_cents) - points_on_subtotal
    ppd = int(points_per_dollar or 0)
    points_earned = int((subtotal_card_cents / 100.0) * ppd) + int((tip_cents / 100.0) * ppd)
    return {
        "subtotal_cents":                int(amount_cents),
        "tip_cents":                        int(tip_cents),
        "total_cents":                    int(total_cents),
        "points_to_use":                int(points_to_use),
        "points_value_cents":      int(points_value_cents),
        "card_cents":                      int(card_cents),
        "points_earned":                int(points_earned),
        "max_points_allowed":      int(max_points_allowed),
    }


async def quote(db, *, token: str, points_to_use: int, tip_cents: int,
                                    user_id: Optional[str]) -> Dict[str, Any]:
    resolved = await resolve_qr(db, token=token, user_id=user_id)
    q = _compute_quote(
        amount_cents=resolved["amount_cents"],
        tip_cents=tip_cents, points_to_use=points_to_use,
        points_per_dollar=resolved["settings"]["points_per_dollar"],
        max_pct=resolved["settings"]["max_points_redemption_pct"],
        user_points_balance=resolved["user_points_balance"])
    q["merchant"]              = resolved["merchant"]
    q["currency"]              = resolved.get("currency")
    q["user_points_balance"] = resolved["user_points_balance"]
    return q


# ─── Authorize + capture ────────────────────────────────────────
async def authorize(db, *, token: str, user_id: str,
                                            points_to_use: int, tip_cents: int,
                                            payment_method_id: Optional[str] = None
                                            ) -> Dict[str, Any]:
    """Locks points, creates Stripe PaymentIntent (auto-confirm off) for
    the card portion.  Returns transaction_id + client_secret."""
    resolved = await resolve_qr(db, token=token, user_id=user_id)
    q = _compute_quote(
        amount_cents=resolved["amount_cents"],
        tip_cents=tip_cents, points_to_use=points_to_use,
        points_per_dollar=resolved["settings"]["points_per_dollar"],
        max_pct=resolved["settings"]["max_points_redemption_pct"],
        user_points_balance=resolved["user_points_balance"])
    if q["card_cents"] == 0 and q["points_value_cents"] == 0:
        raise ValueError("zero_charge")
    merchant_id = resolved["merchant"]["merchant_id"]
    biz = await db.businesses.find_one({"business_id": merchant_id})
    stripe_acct = biz.get("stripe_account_id")

    tx_id = _gen("stx")
    now = _now()

    # 1) Lock points via ledger spend (negative delta).
    points_lock_entry_id = None
    if q["points_to_use"] > 0:
        pts = PointsService(db)
        res = await pts.spend(
            user_id=user_id, source="scan_to_pay",
            amount=q["points_to_use"],
            source_id=tx_id,
            metadata={"merchant_id": merchant_id, "kind": "redeem"},
            idempotency_key=f"scan_redeem:{tx_id}")
        if not res.ok:
            raise ValueError(f"points_lock_failed:{res.reason}")
        points_lock_entry_id = res.entry_id

    # 2) Card portion — Stripe Connect destination charge, if any.
    intent_id = None
    client_secret = None
    app_fee_cents = 0
    real_category = biz.get("category_id") or biz.get("category") or "other"
    if q["card_cents"] > 0:
        # Compute commission on the card portion only (points-portion
        # doesn't touch Stripe).
        commission = await calculate_platform_fee(
            db, merchant_id=merchant_id, category=real_category,
            transaction_type="scan_to_pay",
            amount_cents=q["card_cents"], write_audit=False)
        app_fee_cents = min(int(commission["commission_cents"]),
                                                    int(q["card_cents"]))
        if not stripe_acct or not biz.get("stripe_charges_enabled"):
            # Merchant hasn't finished Stripe activation — degrade to
            # POINTS-ONLY if possible, otherwise refuse.
            if q["points_value_cents"] < q["total_cents"]:
                # Reverse the points lock so the user isn't charged.
                if points_lock_entry_id:
                    await PointsService(db).reverse(
                        entry_id=points_lock_entry_id,
                        reason="merchant_stripe_missing")
                raise ValueError("merchant_stripe_missing")
        else:
            try:
                import stripe as _stripe
                _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
                intent = _stripe.PaymentIntent.create(
                    amount=int(q["card_cents"]),
                    currency=currency_for_business(biz),
                    automatic_payment_methods={
                        "enabled": True, "allow_redirects": "never"},
                    on_behalf_of=stripe_acct,
                    transfer_data={"destination": stripe_acct},
                    application_fee_amount=app_fee_cents,
                    payment_method=payment_method_id,
                    confirm=bool(payment_method_id),
                    capture_method="automatic",
                    metadata={
                        "bigfm_flow":                    "scan_to_pay",
                        "bigfm_merchant_id":      merchant_id,
                        "bigfm_customer_user_id": user_id,
                        "bigfm_scan_to_pay_id": tx_id,
                        "bigfm_qr_token":            token,
                    },
                    idempotency_key=f"stq_{tx_id}")
                intent_id      = intent.id
                client_secret = intent.client_secret
            except Exception as e:
                logger.exception("[ad7] Stripe intent create failed")
                # Rollback the points lock.
                if points_lock_entry_id:
                    await PointsService(db).reverse(
                        entry_id=points_lock_entry_id,
                        reason="stripe_error")
                raise ValueError(f"stripe_error:{e}")

    # 3) Persist the pending transaction.
    doc = {
        "_id":                                            tx_id,
        "transaction_id":                        tx_id,
        "flow":                                          "ad7_scan_to_pay",
        "user_id":                                      user_id,
        "merchant_id":                            merchant_id,
        "location_id":                            resolved["merchant"]["location_id"],
        "cashier_user_id":                    None,   # from qr row, filled below
        "subtotal_cents":                        int(resolved["amount_cents"]),
        "tip_cents":                                int(q["tip_cents"]),
        "tax_cents":                                0,
        "total_cents":                            int(q["total_cents"]),
        "currency":                                  resolved.get("currency") or currency_for_business(biz),
        "points_redeemed":                    int(q["points_to_use"]),
        "points_value_cents":              int(q["points_value_cents"]),
        "points_lock_entry_id":          points_lock_entry_id,
        "card_charged_cents":              int(q["card_cents"]),
        "points_earned_awarded":          int(q["points_earned"]),
        "points_earn_entry_id":          None,          # filled on capture
        "stripe_payment_intent_id":  intent_id,
        "stripe_connected_account_id": stripe_acct,
        "application_fee_cents":          app_fee_cents,
        "merchant_net_cents":              max(0,
                                                                  int(q["card_cents"]) - app_fee_cents),
        "status":                                      "authorized"
                                                              if intent_id or q["points_value_cents"] > 0
                                                              else "pending",
        "qr_token":                                  token,
        "created_at":                              now,
        "authorized_at":                        now,
        "captured_at":                            None,
        "refunded_at":                            None,
        "settings_snapshot": {
            "points_per_dollar":              resolved["settings"]["points_per_dollar"],
            "max_points_redemption_pct":  resolved["settings"]["max_points_redemption_pct"],
        },
    }
    # Pull cashier user id off the QR row.
    qr = await db.scan_to_pay_qr_tokens.find_one({"token": token})
    if qr:
        doc["cashier_user_id"] = qr.get("cashier_user_id")
    await db.scan_to_pay_transactions.insert_one(doc)
    # Mark QR as consumed.
    await db.scan_to_pay_qr_tokens.update_one(
        {"token": token},
        {"$set": {"consumed_at": now, "transaction_id": tx_id}})
    return {
        "transaction_id":                tx_id,
        "status":                                doc["status"],
        "currency":                            doc["currency"],
        "card_cents":                        doc["card_charged_cents"],
        "points_redeemed":              doc["points_redeemed"],
        "points_earned":                doc["points_earned_awarded"],
        "application_fee_cents":  app_fee_cents,
        "merchant_net_cents":        doc["merchant_net_cents"],
        "client_secret":                client_secret,
        "requires_action":            bool(client_secret) and not payment_method_id,
    }


async def capture(db, *, transaction_id: str,
                                    user_id: Optional[str]) -> Dict[str, Any]:
    """Capture points earn + write the AD.2 ledger row.  Idempotent by
    transaction_id — repeated calls are no-ops after the first success."""
    tx = await db.scan_to_pay_transactions.find_one(
        {"transaction_id": transaction_id})
    if not tx:
        raise ValueError("transaction_not_found")
    if user_id and tx["user_id"] != user_id:
        raise ValueError("not_your_transaction")
    if tx["status"] == "captured":
        return {"ok": True, "already_captured": True,
                      "transaction_id": transaction_id}
    if tx["status"] not in ("authorized", "pending"):
        raise ValueError(f"cannot_capture_status:{tx['status']}")

    # Confirm Stripe intent succeeded (if any).
    if tx.get("stripe_payment_intent_id"):
        try:
            import stripe as _stripe
            _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
            intent = _stripe.PaymentIntent.retrieve(
                tx["stripe_payment_intent_id"])
            if intent.status not in ("succeeded",
                                                                "requires_capture",
                                                                "processing"):
                raise ValueError(f"stripe_intent_status:{intent.status}")
            if intent.status == "requires_capture":
                intent = _stripe.PaymentIntent.capture(
                    tx["stripe_payment_intent_id"])
        except ValueError:
            raise
        except Exception as e:
            logger.exception("[ad7] Stripe capture check failed")
            raise ValueError(f"stripe_error:{e}")

    now = _now()
    # Award points earned on the card portion.
    earn_entry_id = None
    if int(tx.get("points_earned_awarded") or 0) > 0:
        pts = PointsService(db)
        res = await pts.award(
            user_id=tx["user_id"],
            source="scan_to_pay_reward",
            source_id=transaction_id,
            delta=int(tx["points_earned_awarded"]),
            metadata={"merchant_id": tx["merchant_id"], "kind": "earn"},
            idempotency_key=f"scan_earn:{transaction_id}",
            enforce_caps=False)
        if res.ok:
            earn_entry_id = res.entry_id

    # Write the AD.2 ledger row.
    await db.payment_transactions_v2.insert_one({
        "_id":                                            _gen("tx_stq"),
        "transaction_id":                        _gen("tx_stq"),
        "stripe_payment_intent_id":  tx.get("stripe_payment_intent_id")
                                                              or f"stq_local:{transaction_id}",
        "flow":                                          "ad7_scan_to_pay",
        "event_source":                            "scan_to_pay_capture",
        "merchant_id":                            tx["merchant_id"],
        "customer_user_id":                    tx["user_id"],
        "scan_to_pay_id":                        transaction_id,
        "amount_cents":                            int(tx["total_cents"]),
        "card_cents":                                int(tx["card_charged_cents"]),
        "points_value_cents":              int(tx["points_value_cents"]),
        "application_fee_cents":          int(tx["application_fee_cents"] or 0),
        "merchant_net_cents":              int(tx["merchant_net_cents"] or 0),
        "status":                                      "posted",
        "created_at":                              now,
    })

    await db.scan_to_pay_transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"status":                        "captured",
                          "captured_at":            now,
                          "points_earn_entry_id": earn_entry_id}})
    return {
        "ok":                                    True,
        "transaction_id":              transaction_id,
        "status":                              "captured",
        "currency":                          tx.get("currency") or "aed",
        "card_cents":                      int(tx["card_charged_cents"]),
        "points_redeemed":            int(tx["points_redeemed"]),
        "points_earned":              int(tx["points_earned_awarded"]),
        # Receipt fields consumed by the web + mobile pay-checkout screens.
        "subtotal_cents":              int(tx["subtotal_cents"]),
        "tip_cents":                        int(tx["tip_cents"]),
        "points_used":                    int(tx["points_redeemed"]),
        "charge_cents":                  int(tx["card_charged_cents"]),
        "bigcoin_earned":              int(tx["points_earned_awarded"]),
    }


async def refund(db, *, transaction_id: str,
                                  actor_role: str,
                                  reason: Optional[str] = None
                                  ) -> Dict[str, Any]:
    """Reverse card + points.  Idempotent per transaction_id."""
    tx = await db.scan_to_pay_transactions.find_one(
        {"transaction_id": transaction_id})
    if not tx:
        raise ValueError("transaction_not_found")
    if tx["status"] == "refunded":
        return {"ok": True, "already_refunded": True,
                      "transaction_id": transaction_id}
    if tx["status"] != "captured":
        raise ValueError(f"cannot_refund_status:{tx['status']}")

    now = _now()
    # 1) Reverse the CARD portion via Stripe.
    if tx.get("stripe_payment_intent_id"):
        try:
            import stripe as _stripe
            _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
            _stripe.Refund.create(
                payment_intent=tx["stripe_payment_intent_id"],
                reason="requested_by_customer",
                # Destination-charge with application_fee → must reverse
                # the transfer AND refund the fee together (Stripe API
                # rule).  See Stripe docs: refunds.reverse_transfer.
                refund_application_fee=True,
                reverse_transfer=True,
                metadata={"bigfm_scan_to_pay_id": transaction_id,
                                    "bigfm_actor_role":        actor_role})
        except Exception as e:
            logger.exception("[ad7] Stripe refund failed")
            raise ValueError(f"stripe_refund_error:{e}")
    # 2) Return redeemed points to the user.
    pts = PointsService(db)
    if tx.get("points_lock_entry_id"):
        await pts.reverse(entry_id=tx["points_lock_entry_id"],
                                            reason=f"scan_refund:{reason or 'refund'}")
    # 3) Claw back earned points.
    if tx.get("points_earn_entry_id"):
        await pts.reverse(entry_id=tx["points_earn_entry_id"],
                                            reason=f"scan_refund_earn:{reason or 'refund'}")
    await db.scan_to_pay_transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"status":              "refunded",
                          "refunded_at":      now,
                          "refund_reason":  reason or "refund"}})
    return {"ok": True, "transaction_id": transaction_id,
                  "status": "refunded"}


# ─── History + analytics ────────────────────────────────────────
def _serialize(doc: dict) -> dict:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def user_history(db, *, user_id: str, limit: int = 20
                                              ) -> Dict[str, Any]:
    rows = []
    async for r in db.scan_to_pay_transactions.find(
                {"user_id": user_id}).sort("created_at", -1).limit(limit):
        biz = await db.businesses.find_one({"business_id": r["merchant_id"]},
                                                                                        {"name": 1, "logo_url": 1})
        rows.append({
            **_serialize(r),
            "merchant_name": (biz or {}).get("name"),
            "merchant_logo": (biz or {}).get("logo_url"),
        })
    return {"items": rows, "count": len(rows)}


async def merchant_transactions(db, *, merchant_id: str,
                                                                        limit: int = 50) -> Dict[str, Any]:
    rows = []
    tot_gross = tot_net = tot_refunds = 0
    async for r in db.scan_to_pay_transactions.find(
                {"merchant_id": merchant_id}).sort("created_at", -1).limit(limit):
        rows.append(_serialize(r))
        if r.get("status") == "captured":
            tot_gross += int(r.get("total_cents") or 0)
            tot_net    += int(r.get("merchant_net_cents") or 0)
        if r.get("status") == "refunded":
            tot_refunds += int(r.get("total_cents") or 0)
    return {
        "items":                    rows,
        "count":                    len(rows),
        "totals": {
            "gross_cents":      tot_gross,
            "net_cents":          tot_net,
            "refunds_cents":  tot_refunds,
        },
    }


async def admin_analytics(db) -> Dict[str, Any]:
    """Platform-wide scan-to-pay stats over the last 30d."""
    since = _now() - timedelta(days=30)
    pipe = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id":                        "$status",
            "count":                    {"$sum": 1},
            "total_cents":        {"$sum": "$total_cents"},
            "app_fee_cents":  {"$sum": "$application_fee_cents"},
            "points_redeemed": {"$sum": "$points_redeemed"},
            "points_earned":    {"$sum": "$points_earned_awarded"},
        }},
    ]
    by_status = {}
    async for r in db.scan_to_pay_transactions.aggregate(pipe):
        by_status[r["_id"] or "unknown"] = {
            "count":                    int(r["count"] or 0),
            "total_cents":        int(r["total_cents"] or 0),
            "app_fee_cents":  int(r["app_fee_cents"] or 0),
            "points_redeemed": int(r["points_redeemed"] or 0),
            "points_earned":    int(r["points_earned"] or 0),
        }
    top_merchants = []
    pipe2 = [
        {"$match": {"created_at": {"$gte": since}, "status": "captured"}},
        {"$group": {"_id": "$merchant_id",
                                "count": {"$sum": 1},
                                "gross": {"$sum": "$total_cents"}}},
        {"$sort":  {"gross": -1}},
        {"$limit": 10},
    ]
    async for r in db.scan_to_pay_transactions.aggregate(pipe2):
        biz = await db.businesses.find_one({"business_id": r["_id"]},
                                                                                        {"name": 1})
        top_merchants.append({
            "merchant_id":  r["_id"],
            "name":                (biz or {}).get("name") or "—",
            "count":              int(r["count"] or 0),
            "gross_cents":  int(r["gross"] or 0),
        })
    return {"by_status": by_status, "top_merchants": top_merchants,
                  "window_days": 30}


__all__ = [
    "ensure_scan_to_pay_indexes",
    "update_merchant_settings",
    "_merchant_scan_settings",
    "generate_qr",
    "resolve_qr",
    "quote",
    "authorize",
    "capture",
    "refund",
    "user_history",
    "merchant_transactions",
    "admin_analytics",
    "MIN_SCAN_AMOUNT_CENTS",
    "DEFAULT_POINTS_PER_DOLLAR",
    "DEFAULT_MAX_POINTS_PCT",
    "QR_TTL_SECONDS",
]
