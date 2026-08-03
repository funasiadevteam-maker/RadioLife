"""Phase MER.3 — Wallet v2 aggregator + checkout modifier engine.

Two duties:

1. `list_user_wallet(user)` — one call to render `/wallet` (coupons +
    gift cards + prepaid meals + points balance).

2. Modifier engine — validates a batch of modifiers against a payment
    link/order, computes the reduced Stripe charge, and (on the succeeded
    handler) idempotently applies them (redeem coupon, decrement GC,
    decrement PM, burn points).

Modifier types: `coupon`, `gift_card`, `prepaid_meal`, `points`.

Points redemption ratio: 100 points → 1 AED (configurable via env
`POINTS_REDEMPTION_RATE_CENTS_PER_100`).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from services import gift_card_service as _gc
from services import prepaid_meal_service as _pm

logger = logging.getLogger("bigfm.mer3.wallet_v2")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _coerce_utc(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _points_cents_per_100() -> int:
    try:
        return int(os.environ.get("POINTS_REDEMPTION_RATE_CENTS_PER_100", "100"))
    except Exception:
        return 100


def _mask_email(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return email or ""
    name, dom = email.split("@", 1)
    if len(name) <= 2:
        return "*" * len(name) + "@" + dom
    return name[0] + "*" * (len(name) - 2) + name[-1] + "@" + dom


# ─── Wallet aggregator ─────────────────────────────────────────
async def list_user_wallet(db, *, user: dict) -> dict:
    """Return coupons + gift cards + prepaid meals + points_balance
    for the authenticated user.  Email match acts as a fallback for
    guest-purchased items (owner_user_id set on next login)."""
    uid = user.get("user_id")
    email = (user.get("email") or "").lower()

    # ── Coupons (legacy `coupons` collection) ─────────────────
    coupons_q = {"status": {"$in": ["saved", "claimed"]}}
    if uid:
        coupons_q["user_id"] = uid
    else:
        coupons_q["user_id"] = "___never_matches___"        # anonymous → empty
    coupons = []
    async for c in db.coupons.find(coupons_q).sort("created_at", -1).limit(50):
        offer = None
        if c.get("offer_id"):
            offer = await db.offers.find_one({"offer_id": c["offer_id"]},
                                                                              {"title": 1, "discount_percent": 1,
                                                                                "offer_type": 1, "business_id": 1})
        biz = None
        if offer and offer.get("business_id"):
            biz = await db.businesses.find_one(
                {"$or": [{"business_id": offer["business_id"]},
                                {"_id": offer["business_id"]}]},
                {"name": 1, "logo_url": 1})
        coupons.append({
            "coupon_id":                c.get("coupon_id"),
            "code":                            c.get("code"),
            "offer_id":                    c.get("offer_id"),
            "offer_title":              (offer or {}).get("title"),
            "offer_discount_percent": (offer or {}).get("discount_percent"),
            "offer_type":                (offer or {}).get("offer_type"),
            "business_id":              (offer or {}).get("business_id"),
            "business_name":            (biz or {}).get("name"),
            "expires_at":                _iso(c.get("expires_at")),
            "status":                        c.get("status"),
            "wallet_pass_url":      c.get("wallet_pass_url"),
        })

    # ── Gift cards (own + email-matched guest buys) ───────────
    gc_q = {"status": {"$in": ["active", "depleted"]}}
    ors = []
    if uid: ors.append({"owner_user_id": uid})
    if email: ors.append({"owner_email": email})
    if ors:
        gc_q["$or"] = ors
    else:
        gc_q["_id"] = "___never_matches___"
    gift_cards = []
    async for g in db.user_gift_cards.find(gc_q).sort("created_at", -1).limit(50):
        biz = await db.businesses.find_one(
            {"$or": [{"business_id": g.get("merchant_id")},
                            {"_id": g.get("merchant_id")}]},
            {"name": 1, "logo_url": 1}) if g.get("merchant_id") else None
        gift_cards.append({
            "gift_card_id":              g.get("gift_card_id"),
            "code":                            g.get("code"),
            "merchant_id":              g.get("merchant_id"),
            "merchant_name":            (biz or {}).get("name"),
            "merchant_logo_url":  (biz or {}).get("logo_url"),
            "initial_balance_cents": int(g.get("initial_balance_cents") or 0),
            "current_balance_cents": int(g.get("current_balance_cents") or 0),
            "currency":                    g.get("currency") or "AED",
            "expires_at":                _iso(g.get("expires_at")),
            "status":                        g.get("status"),
            "last_used_at":            _iso(g.get("last_used_at")),
        })

    # ── Prepaid meals ─────────────────────────────────────────
    pm_q = {"status": {"$in": ["active", "depleted"]}}
    if ors:
        pm_q["$or"] = ors
    else:
        pm_q["_id"] = "___never_matches___"
    meals = []
    async for m in db.user_prepaid_meals.find(pm_q).sort("created_at", -1).limit(50):
        biz = await db.businesses.find_one(
            {"$or": [{"business_id": m.get("merchant_id")},
                            {"_id": m.get("merchant_id")}]},
            {"name": 1, "logo_url": 1}) if m.get("merchant_id") else None
        sku = None
        if m.get("sku_id"):
            sku = await db.prepaid_meal_skus.find_one({"sku_id": m["sku_id"]},
                                                                                                        {"name": 1})
        meals.append({
            "meal_pack_id":              m.get("meal_pack_id"),
            "code":                            m.get("code"),
            "merchant_id":              m.get("merchant_id"),
            "merchant_name":            (biz or {}).get("name"),
            "merchant_logo_url":  (biz or {}).get("logo_url"),
            "sku_name":                    (sku or {}).get("name"),
            "total_meals":              int(m.get("total_meals") or 0),
            "remaining_meals":      int(m.get("remaining_meals") or 0),
            "per_meal_value_cents": int(m.get("per_meal_value_cents") or 0),
            "expires_at":                _iso(m.get("expires_at")),
            "status":                        m.get("status"),
            "last_used_at":            _iso(m.get("last_used_at")),
        })

    # ── Points balance ────────────────────────────────────────
    # Phase F-2 ledger flip: source-of-truth is points_ledger; the legacy
    # users.bigcoin_balance mirror is no longer dual-written on all earn
    # paths (e.g. AD.8 daily_code_claim), so we compute from the ledger.
    points_balance = 0
    if uid:
        try:
            from services.points_service import PointsService
            points_balance = await PointsService(db).get_balance(uid)
        except Exception:
            logger.exception("[mer3] wallet points lookup failed (non-blocking)")
            try:
                u = await db.users.find_one({"user_id": uid}, {"bigcoin_balance": 1})
                points_balance = int((u or {}).get("bigcoin_balance") or 0)
            except Exception:
                logger.exception("[mer3] legacy bigcoin_balance fallback failed")

    return {
        "coupons":                    coupons,
        "gift_cards":              gift_cards,
        "prepaid_meals":        meals,
        "points_balance":      points_balance,
        "points_rate_cents_per_100": _points_cents_per_100(),
        "counts": {
            "coupons":                len(coupons),
            "gift_cards":          len(gift_cards),
            "prepaid_meals":    len(meals),
        },
    }


# ─── Modifier validation + preview ─────────────────────────────
async def _validate_coupon_modifier(db, *, code_or_id: str, merchant_id: str,
                                                                          order_amount_cents: int, user: dict) -> dict:
    up = code_or_id.strip().upper()
    c = await db.coupons.find_one({"$or": [
        {"coupon_id": code_or_id.strip()}, {"coupon_id": up},
        {"code": code_or_id.strip()}, {"code": up}]})
    if not c:
        return {"ok": False, "reason": "not_found"}
    if c.get("status") not in ("saved", "claimed"):
        return {"ok": False, "reason": c.get("status") or "invalid"}
    if c.get("expires_at") and _coerce_utc(c["expires_at"]) < _now():
        return {"ok": False, "reason": "expired"}
    offer = await db.offers.find_one({"offer_id": c.get("offer_id")})
    if not offer:
        return {"ok": False, "reason": "offer_missing"}
    if offer.get("business_id") != merchant_id:
        return {"ok": False, "reason": "not_this_merchant"}
    disc_pct = int(offer.get("discount_percent") or 0)
    if disc_pct <= 0:
        return {"ok": False, "reason": "no_discount"}
    reduction = int(order_amount_cents * disc_pct / 100)
    return {"ok": True,
                  "reference_id":              c["coupon_id"],
                  "code":                              c.get("code"),
                  "amount_reduced_cents":  reduction,
                  "discount_percent":        disc_pct,
                  "offer_title":                offer.get("title")}


async def _validate_points_modifier(db, *, requested_cents: int,
                                                                          user: dict) -> dict:
    if not user or not user.get("user_id"):
        return {"ok": False, "reason": "auth_required"}
    u = await db.users.find_one({"user_id": user["user_id"]},
                                                          {"bigcoin_balance": 1})
    balance = int((u or {}).get("bigcoin_balance") or 0)
    rate = _points_cents_per_100()
    max_cents_available = int(balance / 100 * rate)      # 100 pts → rate cents
    cap = min(int(requested_cents), max_cents_available)
    if cap <= 0:
        return {"ok": False, "reason": "insufficient_points",
                      "points_balance": balance}
    points_burn = int(cap * 100 / rate)
    return {"ok": True,
                  "reference_id":              None,
                  "amount_reduced_cents":  cap,
                  "points_burned":            points_burn,
                  "points_balance":          balance,
                  "rate_cents_per_100":  rate}


async def preview_modifiers(db, *, merchant_id: str, order_amount_cents: int,
                                                      modifiers: list, user: Optional[dict]) -> dict:
    """Compute reduced Stripe charge given a batch of applied modifiers.

    Applied in list order, each reducing the running subtotal.  If a
    modifier would over-reduce (bring charge below 0), it is capped
    at the remaining subtotal — no rejection.

    Returns:  {subtotal_cents, discounts:[{type, ...}], stripe_charge_cents}
    """
    subtotal = int(order_amount_cents)
    remaining = subtotal
    discounts = []
    for m in (modifiers or []):
        mtype = (m or {}).get("type")
        cid_or_code = (m or {}).get("code_or_id") or (m or {}).get("code") \
                                          or (m or {}).get("reference_id") or ""
        if remaining <= 0:
            discounts.append({"type": mtype, "ok": False,
                                              "reason": "already_covered",
                                              "amount_reduced_cents": 0})
            continue

        if mtype == "coupon":
            r = await _validate_coupon_modifier(
                db, code_or_id=cid_or_code, merchant_id=merchant_id,
                order_amount_cents=subtotal, user=user or {})
            if r.get("ok"):
                reduction = min(int(r["amount_reduced_cents"]), remaining)
                remaining -= reduction
                discounts.append({"type": "coupon", "ok": True,
                                                  "reference_id": r["reference_id"],
                                                  "code": r.get("code"),
                                                  "amount_reduced_cents": reduction,
                                                  "offer_title": r.get("offer_title"),
                                                  "discount_percent": r.get("discount_percent")})
            else:
                discounts.append({"type": "coupon", "ok": False,
                                                  "reason": r.get("reason"),
                                                  "amount_reduced_cents": 0})

        elif mtype == "gift_card":
            r = await _gc.apply_at_checkout(
                db, code=cid_or_code, merchant_id=merchant_id,
                order_amount_cents=remaining)
            if r.get("ok"):
                reduction = min(int(r["amount_reduced_cents"]), remaining)
                remaining -= reduction
                discounts.append({"type": "gift_card", "ok": True,
                                                  "reference_id": r["gift_card_id"],
                                                  "code": r.get("code"),
                                                  "amount_reduced_cents": reduction,
                                                  "current_balance_cents": r.get("current_balance_cents")})
            else:
                discounts.append({"type": "gift_card", "ok": False,
                                                  "reason": r.get("reason"),
                                                  "amount_reduced_cents": 0})

        elif mtype == "prepaid_meal":
            r = await _pm.apply_at_checkout(
                db, code=cid_or_code, merchant_id=merchant_id)
            if r.get("ok"):
                reduction = min(int(r["amount_reduced_cents"]), remaining)
                remaining -= reduction
                discounts.append({"type": "prepaid_meal", "ok": True,
                                                  "reference_id": r["meal_pack_id"],
                                                  "code": r.get("code"),
                                                  "amount_reduced_cents": reduction,
                                                  "remaining_meals": r.get("remaining_meals")})
            else:
                discounts.append({"type": "prepaid_meal", "ok": False,
                                                  "reason": r.get("reason"),
                                                  "amount_reduced_cents": 0})

        elif mtype == "points":
            requested = int((m or {}).get("amount_cents") or remaining)
            requested = min(requested, remaining)
            r = await _validate_points_modifier(
                db, requested_cents=requested, user=user or {})
            if r.get("ok"):
                reduction = min(int(r["amount_reduced_cents"]), remaining)
                remaining -= reduction
                discounts.append({"type": "points", "ok": True,
                                                  "reference_id": None,
                                                  "amount_reduced_cents": reduction,
                                                  "points_burned": r.get("points_burned"),
                                                  "points_balance": r.get("points_balance"),
                                                  "rate_cents_per_100": r.get("rate_cents_per_100")})
            else:
                discounts.append({"type": "points", "ok": False,
                                                  "reason": r.get("reason"),
                                                  "amount_reduced_cents": 0,
                                                  "points_balance": r.get("points_balance")})

        else:
            discounts.append({"type": mtype, "ok": False,
                                              "reason": "unknown_type",
                                              "amount_reduced_cents": 0})

    total_discount = sum(int(d.get("amount_reduced_cents") or 0) for d in discounts)
    stripe_charge = max(0, subtotal - total_discount)
    return {
        "subtotal_cents":        subtotal,
        "discounts":                discounts,
        "total_discount_cents": total_discount,
        "stripe_charge_cents": stripe_charge,
        "zero_charge":            (stripe_charge == 0),
    }


# ─── Applied-modifier consumption on succeeded webhook ─────────
async def _consume_coupon(db, tx: dict, mod: dict) -> Optional[dict]:
    coupon_id = mod.get("reference_id")
    if not coupon_id:
        return None
    now = _now()
    result = await db.coupons.update_one(
        {"coupon_id": coupon_id, "status": {"$in": ["saved", "claimed"]}},
        {"$set": {"status": "redeemed",
                            "redeemed_at": now,
                            "redeemed_at_transaction_id": tx["transaction_id"],
                            "redeemed_at_merchant_id": tx["merchant_id"]}})
    return {"matched": result.matched_count > 0,
                  "modified": result.modified_count > 0,
                  "coupon_id": coupon_id}


async def _consume_gift_card(db, tx: dict, mod: dict) -> Optional[dict]:
    gc_id = mod.get("reference_id")
    amt = int(mod.get("amount_reduced_cents") or 0)
    if not gc_id or amt <= 0:
        return None
    try:
        result = await _gc.decrement_balance(
            db, gift_card_id=gc_id, amount_cents=amt)
        return {"ok": True, "gift_card_id": gc_id,
                      "new_balance_cents": int(result.get("current_balance_cents") or 0)}
    except ValueError as ve:
        return {"ok": False, "reason": str(ve), "gift_card_id": gc_id}


async def _consume_prepaid_meal(db, tx: dict, mod: dict) -> Optional[dict]:
    pack_id = mod.get("reference_id")
    if not pack_id:
        return None
    try:
        result = await _pm.decrement_meal(db, meal_pack_id=pack_id, count=1)
        return {"ok": True, "meal_pack_id": pack_id,
                      "remaining_meals": int(result.get("remaining_meals") or 0)}
    except ValueError as ve:
        return {"ok": False, "reason": str(ve), "meal_pack_id": pack_id}


async def _consume_points(db, tx: dict, mod: dict) -> Optional[dict]:
    user_id = tx.get("customer_user_id")
    burn = int(mod.get("points_burned") or 0)
    if not user_id or burn <= 0:
        return None
    try:
        from services.bigcoin import spend
        res = await spend(
            db, user_id=user_id, amount=burn,
            source="mer3_checkout_burn",
            metadata={"transaction_id": tx["transaction_id"],
                                "merchant_id": tx["merchant_id"],
                                "amount_reduced_cents": int(mod.get("amount_reduced_cents") or 0),
                                "source_id": tx["transaction_id"]},
            note=f"Checkout modifier applied on {tx['transaction_id']}",
        )
        return {"ok": True, "points_burned": burn,
                      "balance_after": (res or {}).get("balance_after")}
    except Exception as e:
        logger.warning(f"[mer3] points burn failed: {e}")
        return {"ok": False, "reason": "spend_failed"}


async def apply_modifiers_at_succeeded(db, *, tx: dict) -> dict:
    """Called from the SC.5 succeeded handler.  Idempotent — guarded by
    `checkout_modifiers.transaction_id + type + reference_id` unique
    combo (write once per tx+modifier).  Safe to re-run on webhook replay."""
    mods = tx.get("modifiers") or []
    if not mods:
        return {"applied": 0}

    already = await db.checkout_modifiers.count_documents(
        {"transaction_id": tx["transaction_id"]})
    if already > 0:
        return {"applied": already, "reason": "already_processed"}

    applied = []
    now = _now()
    for mod in mods:
        mtype = mod.get("type")
        # Only ok=true modifiers made it to the tx row — but be defensive
        if not mod.get("ok"):
            continue
        result = None
        if mtype == "coupon":
            result = await _consume_coupon(db, tx, mod)
        elif mtype == "gift_card":
            result = await _consume_gift_card(db, tx, mod)
        elif mtype == "prepaid_meal":
            result = await _consume_prepaid_meal(db, tx, mod)
        elif mtype == "points":
            result = await _consume_points(db, tx, mod)

        entry = {
            "_id":                              f"mm_{uuid.uuid4().hex[:16]}",
            "modifier_id":              f"mm_{uuid.uuid4().hex[:16]}",
            "transaction_id":        tx["transaction_id"],
            "merchant_id":              tx["merchant_id"],
            "type":                            mtype,
            "reference_id":            mod.get("reference_id"),
            "code":                            mod.get("code"),
            "amount_reduced_cents": int(mod.get("amount_reduced_cents") or 0),
            "applied_at":                now,
            "result":                        result,
        }
        entry["modifier_id"] = entry["_id"]
        try:
            await db.checkout_modifiers.insert_one(entry)
        except Exception:
            logger.exception("[mer3] checkout_modifiers insert failed (non-blocking)")
        applied.append(entry)
        logger.info(f"[mer3] modifier applied type={mtype} amt={entry['amount_reduced_cents']} "
                              f"ref={entry['reference_id']} tx={tx['transaction_id']}")

    return {"applied": len(applied)}


# ─── Post-succeeded hook (called from payment_service) ─────────
async def on_payment_succeeded_mer3(db, *, tx: dict) -> dict:
    """Called from `handle_payment_intent_succeeded` in payment_service.py
    (SC.5) after all standard side-effects.  Two duties:

    1. If `link.link_type` is `gift_card` or `prepaid_meal`, mint the
        purchased wallet item.
    2. Consume any modifiers stored on the tx row (`tx.modifiers`).
    """
    out = {"minted": None, "modifiers": None}

    # 1. Mint wallet item on purchase
    link = None
    if tx.get("link_id"):
        link = await db.merchant_payment_links.find_one({"link_id": tx["link_id"]})
    if link:
        lt = link.get("link_type")
        if lt == "gift_card":
            try:
                gc = await _gc.mint_gift_card(
                    db, sku_id=link.get("gift_card_id"),
                    merchant_id=tx["merchant_id"],
                    amount_cents=int(tx.get("amount_cents") or 0),
                    owner_user_id=tx.get("customer_user_id"),
                    owner_email=tx.get("customer_email"),
                    purchased_transaction_id=tx["transaction_id"],
                )
                # Stamp code on tx row so receipt page can render it
                await db.payment_transactions_v2.update_one(
                    {"transaction_id": tx["transaction_id"]},
                    {"$set": {"minted_gift_card_id": gc.get("gift_card_id"),
                                        "minted_gift_card_code": gc.get("code")}})
                out["minted"] = {"type": "gift_card",
                                                "gift_card_id": gc.get("gift_card_id"),
                                                "code": gc.get("code")}
            except Exception:
                logger.exception("[mer3] gift card mint failed (non-blocking)")

        elif lt == "prepaid_meal":
            try:
                pm = await _pm.mint_prepaid_meal(
                    db, sku_id=link.get("prepaid_meal_id"),
                    merchant_id=tx["merchant_id"],
                    owner_user_id=tx.get("customer_user_id"),
                    owner_email=tx.get("customer_email"),
                    purchased_transaction_id=tx["transaction_id"],
                )
                await db.payment_transactions_v2.update_one(
                    {"transaction_id": tx["transaction_id"]},
                    {"$set": {"minted_meal_pack_id": pm.get("meal_pack_id"),
                                        "minted_meal_pack_code": pm.get("code")}})
                out["minted"] = {"type": "prepaid_meal",
                                                "meal_pack_id": pm.get("meal_pack_id"),
                                                "code": pm.get("code")}
            except Exception:
                logger.exception("[mer3] prepaid meal mint failed (non-blocking)")

    # 2. Consume applied modifiers
    if tx.get("modifiers"):
        try:
            out["modifiers"] = await apply_modifiers_at_succeeded(db, tx=tx)
        except Exception:
            logger.exception("[mer3] apply_modifiers_at_succeeded failed (non-blocking)")

    return out


# ─── Zero-charge helper ─────────────────────────────────────────
async def zero_charge_transaction(db, *, token: str, link: dict, biz: dict,
                                                                  amount_cents: int, modifiers: list,
                                                                  customer_user_id: Optional[str],
                                                                  customer_email: Optional[str]) -> dict:
    """When modifiers fully cover the order (0¢ Stripe charge), create
    a synthetic `payment_transactions_v2` row with `status=succeeded`
    (no Stripe intent) and fire the MER.3 post-succeeded hook."""
    now = _now()
    txn_id = f"tx3z_{uuid.uuid4().hex[:16]}"
    doc = {
        "_id":                                    txn_id,
        "transaction_id":                txn_id,
        "flow":                                    "mer3_zero_charge",
        "merchant_id":                    biz.get("business_id") or biz.get("_id"),
        "link_id":                              link["link_id"],
        "link_token":                        token,
        # SC.5 unique index on stripe_payment_intent_id is non-sparse — use a
        # synthetic per-row sentinel to satisfy uniqueness on zero-charge txs.
        "stripe_payment_intent_id": f"zero_{txn_id}",
        "stripe_charge_id":              None,
        "stripe_connected_account_id": biz.get("stripe_account_id"),
        "amount_cents":                    int(amount_cents),
        "currency":                            (link.get("currency") or "AED").upper(),
        "application_fee_cents":  0,
        "computed_percent":            0,
        "stripe_fee_estimate_cents": 0,
        "merchant_net_cents":        0,
        "status":                              "succeeded",
        "payment_method_type":  "modifiers_only",
        "customer_user_id":            customer_user_id,
        "customer_email":                customer_email,
        "table_number":                    link.get("table_number"),
        "transaction_type":            link.get("transaction_type") or "payment",
        "category_at_charge":      biz.get("category_id") or biz.get("category"),
        "created_at":                      now,
        "confirmed_at":                  now,
        "succeeded_at":                  now,
        "failed_at":                        None,
        "modifiers":                        modifiers,
        "modifiers_only":                True,
    }
    await db.payment_transactions_v2.insert_one(doc)

    # Bump link usage_count (mirrors SC.5 behaviour)
    try:
        await db.merchant_payment_links.update_one(
            {"link_id": link["link_id"]},
            {"$inc": {"usage_count": 1},
              "$set": {"last_success_at": now}})
    except Exception:
        logger.exception("[mer3] zero-charge usage_count bump failed (non-blocking)")

    # Fire MER.3 post-succeeded hook — mint items + consume modifiers
    hook = await on_payment_succeeded_mer3(db, tx=doc)

    logger.info(f"[mer3] ZERO-CHARGE tx={txn_id} link={link['link_id']} "
                          f"amt={amount_cents} mods={len(modifiers)}")

    return {"transaction_id": txn_id, "status": "succeeded",
                  "amount_cents": amount_cents, "hook": hook}


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_wallet_v2_indexes(db) -> None:
    await db.checkout_modifiers.create_index(
        [("transaction_id", 1), ("type", 1), ("reference_id", 1)])
    await db.checkout_modifiers.create_index("applied_at")


__all__ = [
    "list_user_wallet",
    "preview_modifiers",
    "apply_modifiers_at_succeeded",
    "on_payment_succeeded_mer3",
    "zero_charge_transaction",
    "ensure_wallet_v2_indexes",
]
