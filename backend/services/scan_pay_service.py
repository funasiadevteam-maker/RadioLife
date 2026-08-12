"""QR Scan-to-Pay — customer presents a QR, the shop scans it to charge.

Flow: a shopper generates a short-lived, single-use pay token (pay by saved
card one-tap, or by BigPoints) encoding the exact amount they approve. The
merchant scans the QR, resolves it, and charges. Every step is audited; a
customer can also report an off-app ("bypass") payment, which is logged for
admin review as an anti-commission-evasion signal.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from services.marketplace import now, new_id
from services.points_service import PointsService

TOKEN_TTL_SEC = 300  # 5 minutes
REDEEM_POINTS_PER_DOLLAR = 100


def _points_for_cents(cents: int) -> int:
    return int(max(0, int(cents or 0)) * REDEEM_POINTS_PER_DOLLAR // 100)


def _gen_token() -> str:
    return "SP" + secrets.token_hex(5).upper()  # e.g. SPA1B2C3D4E5


def _mask_name(name: Optional[str]) -> str:
    n = (name or "Customer").strip()
    return (n[0] + "•••" + n[-1]) if len(n) > 2 else n


async def ensure_scanpay_indexes(db) -> None:
    await db.scanpay_tokens.create_index("token", unique=True)
    await db.scanpay_tokens.create_index("expires_at")
    await db.scanpay_charges.create_index("charge_id", unique=True)
    await db.scanpay_fraud_logs.create_index("created_at")


def _serialize(d: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(d)
    d.pop("_id", None)
    for k in ("created_at", "updated_at", "expires_at", "charged_at"):
        v = d.get(k)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


def _is_expired(tok: Dict[str, Any]) -> bool:
    ex = tok.get("expires_at")
    if isinstance(ex, str):
        ex = datetime.fromisoformat(ex.replace("Z", "+00:00"))
    if ex and ex.tzinfo is None:
        ex = ex.replace(tzinfo=timezone.utc)
    return bool(ex and datetime.now(timezone.utc) > ex)


# ───────────── Customer ─────────────
async def create_token(db, user, *, method: str, amount_cents: int,
                        payment_method_id: Optional[str] = None) -> Dict[str, Any]:
    if method not in ("card", "points"):
        raise ValueError("bad_method")
    if int(amount_cents) <= 0:
        raise ValueError("bad_amount")
    if method == "card":
        from services.saved_cards_service import ensure_stripe_customer, owns_payment_method
        cust = await ensure_stripe_customer(db, user)
        if not payment_method_id or not owns_payment_method(cust, payment_method_id):
            raise ValueError("card_not_found")
    else:
        bal = await PointsService(db).get_balance(user["user_id"])
        if bal < _points_for_cents(amount_cents):
            raise ValueError("insufficient_points")
    doc = {
        "token_id": new_id("spt"), "token": _gen_token(),
        "user_id": user["user_id"], "user_name": user.get("name") or user.get("email"),
        "method": method, "amount_cents": int(amount_cents),
        "payment_method_id": payment_method_id if method == "card" else None,
        "status": "active", "created_at": now(),
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SEC),
    }
    await db.scanpay_tokens.insert_one(dict(doc))
    return _serialize(doc)


async def token_status(db, user, token: str) -> Dict[str, Any]:
    tok = await db.scanpay_tokens.find_one({"token": token, "user_id": user["user_id"]})
    if not tok:
        return {"status": "not_found"}
    if tok["status"] == "active" and _is_expired(tok):
        await db.scanpay_tokens.update_one({"token": token}, {"$set": {"status": "expired"}})
        tok["status"] = "expired"
    out = {"status": tok["status"], "amount_cents": tok["amount_cents"], "method": tok["method"]}
    if tok["status"] == "charged":
        out["charged_at"] = tok.get("charged_at")
        out["business_name"] = tok.get("business_name")
    return out


async def cancel_token(db, user, token: str) -> Dict[str, Any]:
    r = await db.scanpay_tokens.update_one(
        {"token": token, "user_id": user["user_id"], "status": "active"},
        {"$set": {"status": "canceled"}})
    return {"ok": bool(r.modified_count)}


# ───────────── Merchant ─────────────
async def resolve(db, business: Dict[str, Any], token: str) -> Dict[str, Any]:
    tok = await db.scanpay_tokens.find_one({"token": token})
    if not tok:
        return {"ok": False, "error": "invalid_token"}
    if tok["status"] == "active" and _is_expired(tok):
        await db.scanpay_tokens.update_one({"token": token}, {"$set": {"status": "expired"}})
        tok["status"] = "expired"
    if tok["status"] != "active":
        return {"ok": False, "error": tok["status"]}
    await db.scanpay_charges.insert_one({
        "audit_id": new_id("spa"), "event": "resolved", "token": token,
        "business_id": business["business_id"], "created_at": now()})
    return {"ok": True, "token": token, "amount_cents": tok["amount_cents"],
            "method": tok["method"], "customer": _mask_name(tok.get("user_name"))}


async def charge(db, merchant_user, business: Dict[str, Any], token: str) -> Dict[str, Any]:
    tok = await db.scanpay_tokens.find_one({"token": token})
    if not tok:
        return {"ok": False, "error": "invalid_token"}
    if tok["status"] == "active" and _is_expired(tok):
        await db.scanpay_tokens.update_one({"token": token}, {"$set": {"status": "expired"}})
        return {"ok": False, "error": "expired"}
    if tok["status"] != "active":
        return {"ok": False, "error": tok["status"]}

    # Atomically claim the token so it can't be double-charged.
    claim = await db.scanpay_tokens.update_one(
        {"token": token, "status": "active"}, {"$set": {"status": "charging"}})
    if not claim.modified_count:
        return {"ok": False, "error": "already_used"}

    amount = int(tok["amount_cents"])
    customer = await db.users.find_one({"user_id": tok["user_id"]})
    charge_id = new_id("spc")
    try:
        if tok["method"] == "card":
            from services.saved_cards_service import ensure_stripe_customer, charge_saved_card
            import stripe
            cust = await ensure_stripe_customer(db, customer)
            try:
                pi = charge_saved_card(amount_cents=amount, cust_id=cust,
                                       pm_id=tok["payment_method_id"],
                                       metadata={"kind": "scanpay", "token": token,
                                                 "business_id": business["business_id"]})
            except stripe.error.CardError as e:
                await db.scanpay_tokens.update_one({"token": token}, {"$set": {"status": "active"}})
                return {"ok": False, "error": "card_declined", "detail": str(e)}
            if pi.status != "succeeded":
                await db.scanpay_tokens.update_one({"token": token}, {"$set": {"status": "active"}})
                return {"ok": False, "error": "requires_action"}
            ref = pi.id
        else:  # points
            points = _points_for_cents(amount)
            res = await PointsService(db).spend(
                user_id=tok["user_id"], source="scanpay", amount=points,
                source_id=token, idempotency_key=f"scanpay_{token}",
                metadata={"business_id": business["business_id"], "amount_cents": amount})
            if not getattr(res, "ok", False):
                await db.scanpay_tokens.update_one({"token": token}, {"$set": {"status": "active"}})
                return {"ok": False, "error": "points_spend_failed"}
            ref = f"points:{points}"
    except Exception as e:
        await db.scanpay_tokens.update_one({"token": token}, {"$set": {"status": "active"}})
        return {"ok": False, "error": "charge_failed", "detail": str(e)}

    await db.scanpay_tokens.update_one({"token": token}, {"$set": {
        "status": "charged", "charged_at": now(),
        "business_id": business["business_id"],
        "business_name": business.get("public_name")}})
    await db.scanpay_charges.insert_one({
        "charge_id": charge_id, "event": "charged", "token": token,
        "business_id": business["business_id"], "merchant_user_id": merchant_user["user_id"],
        "customer_user_id": tok["user_id"], "amount_cents": amount,
        "method": tok["method"], "reference": ref, "created_at": now()})
    return {"ok": True, "charge_id": charge_id, "amount_cents": amount, "method": tok["method"]}


# ───────────── Anti-fraud ─────────────
async def report_bypass(db, user, *, business_id: Optional[str] = None,
                        business_name: Optional[str] = None,
                        amount_cents: Optional[int] = None,
                        note: Optional[str] = None) -> Dict[str, Any]:
    name = business_name
    if business_id and not name:
        prof = await db.marketplace_profiles.find_one(
            {"business_id": business_id}, {"public_name": 1})
        name = (prof or {}).get("public_name")
    doc = {
        "log_id": new_id("spf"), "type": "customer_bypass_report",
        "business_id": business_id, "business_name": name,
        "reporter_user_id": user["user_id"], "amount_cents": amount_cents,
        "note": (note or "")[:400], "status": "open", "created_at": now(),
    }
    await db.scanpay_fraud_logs.insert_one(dict(doc))
    return {"ok": True, "log_id": doc["log_id"]}


async def admin_fraud_logs(db, limit: int = 100) -> Dict[str, Any]:
    items = [_serialize(d) async for d in
             db.scanpay_fraud_logs.find().sort("created_at", -1).limit(limit)]
    return {"items": items}


async def admin_charges(db, limit: int = 100) -> Dict[str, Any]:
    items = [_serialize(d) async for d in db.scanpay_charges.find(
        {"event": "charged"}).sort("created_at", -1).limit(limit)]
    return {"items": items}


__all__ = ["ensure_scanpay_indexes", "create_token", "token_status", "cancel_token",
           "resolve", "charge", "report_bypass", "admin_fraud_logs", "admin_charges"]
