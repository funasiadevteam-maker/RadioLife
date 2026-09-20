"""Buy More BigCoin — listeners top up their BigCoin balance with a card
(Stripe Checkout).  On paid, credits the unified points ledger via
PointsService (idempotent on the Stripe session id).  100 BigCoin == $1."""
from __future__ import annotations
from core.origins import resolve_origin

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user
from services.points_service import PointsService

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/bigcoin/topup", tags=["bigcoin-topup"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# package_id → (base bigcoin, price cents, bonus bigcoin)
PACKAGES: List[Dict[str, Any]] = [
    {"package_id": "tp_500", "bigcoin": 500, "price_cents": 500, "bonus": 0},
    {"package_id": "tp_1000", "bigcoin": 1000, "price_cents": 1000, "bonus": 50},
    {"package_id": "tp_2500", "bigcoin": 2500, "price_cents": 2500, "bonus": 250},
    {"package_id": "tp_5000", "bigcoin": 5000, "price_cents": 5000, "bonus": 750},
]


def _pkg(package_id: str) -> Optional[Dict[str, Any]]:
    return next((p for p in PACKAGES if p["package_id"] == package_id), None)


@router.get("/packages")
async def packages(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    balance = await PointsService(db).get_balance(user.get("user_id"))
    items = [{**p, "total_bigcoin": p["bigcoin"] + p["bonus"]} for p in PACKAGES]
    return {"items": items, "points_balance": balance}


async def _credit(db, *, session_id: str, uid: str, pkg: Dict[str, Any]) -> Dict[str, Any]:
    total = int(pkg["bigcoin"]) + int(pkg["bonus"])
    res = await PointsService(db).award(
        user_id=uid, source="bigcoin_topup", source_id=pkg["package_id"], delta=total,
        metadata={"package_id": pkg["package_id"], "price_cents": pkg["price_cents"],
                  "bonus": pkg["bonus"]},
        idempotency_key=f"topup:{session_id}", enforce_caps=False)
    return {"credited": total, "balance_after": res.balance_after}


class CheckoutBody(BaseModel):
    package_id: str
    origin_url: Optional[str] = None


@router.post("/checkout")
async def checkout(body: CheckoutBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    pkg = _pkg(body.package_id)
    if not pkg:
        raise HTTPException(404, {"code": "package_not_found"})
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = resolve_origin(request, body.origin_url)
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    total = int(pkg["bigcoin"]) + int(pkg["bonus"])
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"{total} BigCoin"},
                "unit_amount": int(pkg["price_cents"]),
            },
            "quantity": 1,
        }],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "bigcoin_topup", "package_id": pkg["package_id"], "buyer_id": uid},
    )
    await db.bigcoin_topups.insert_one({
        "session_id": session.id, "user_id": uid, "package_id": pkg["package_id"],
        "price_cents": pkg["price_cents"], "total_bigcoin": total,
        "status": "pending", "created_at": _now()})
    return {"ok": True, "checkout_url": session.url, "session_id": session.id}


@router.get("/{session_id}/status")
async def status(session_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    rec = await db.bigcoin_topups.find_one({"session_id": session_id, "user_id": user.get("user_id")})
    if not rec:
        raise HTTPException(404, {"code": "topup_not_found"})
    if rec.get("status") == "paid":
        balance = await PointsService(db).get_balance(user.get("user_id"))
        return {"status": "paid", "credited": rec.get("total_bigcoin"), "balance_after": balance}
    if not stripe.api_key:
        return {"status": rec.get("status", "pending")}
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return {"status": rec.get("status", "pending")}
    if sess.get("payment_status") == "paid":
        pkg = _pkg(rec["package_id"]) or {"package_id": rec["package_id"],
                                          "bigcoin": rec.get("total_bigcoin", 0), "bonus": 0,
                                          "price_cents": rec.get("price_cents", 0)}
        out = await _credit(db, session_id=session_id, uid=rec["user_id"], pkg=pkg)
        await db.bigcoin_topups.update_one(
            {"session_id": session_id},
            {"$set": {"status": "paid", "paid_at": _now(), "credited": out["credited"]}})
        return {"status": "paid", **out}
    return {"status": "pending"}


__all__ = ["router"]
