"""Phase SC.6 — Refund + Payout + Dispute endpoints (admin + merchant).

Refunds:
    POST  /api/admin/refunds
    POST  /api/merchant/{merchant_id}/refunds
    GET    /api/refunds/{refund_id}
    GET    /api/admin/refunds

Payouts:
    GET    /api/merchant/{merchant_id}/payouts
    GET    /api/admin/payouts

Disputes:
    GET    /api/admin/disputes

Transactions (merchant-side per-link listing for the Transactions tab):
    GET    /api/merchant/{merchant_id}/payment-links/{link_id}/transactions
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services.refund_service import (create_refund, RefundError,
                                                                            VALID_REASONS)

logger = logging.getLogger("bigfm.sc6_routes")
router = APIRouter(prefix="/api", tags=["sc6"])


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


# ─── Owner auth resolver ─────────────────────────────────────────
# Phase MER.2 — extended to accept staff-role users with the right
# permission alongside owners + admins.  Owner/admin path unchanged.
async def _resolve_owner(db, merchant_id: str, user: dict,
                                                *, permission: Optional[str] = None) -> dict:
    from services.merchant_rbac_service import resolve_merchant_with_role
    biz, _role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission=permission)
    return biz


# ─── Serialisers ─────────────────────────────────────────────────
def _refund_view(r: dict) -> dict:
    return {
        "refund_id":                            r.get("refund_id"),
        "transaction_id":                    r.get("transaction_id"),
        "merchant_id":                        r.get("merchant_id"),
        "link_id":                                r.get("link_id"),
        "stripe_refund_id":                r.get("stripe_refund_id"),
        "amount_cents":                        int(r.get("amount_cents") or 0),
        "currency":                                r.get("currency"),
        "refund_application_fee":    bool(r.get("refund_application_fee")),
        "application_fee_refund_cents": r.get("application_fee_refund_cents"),
        "status":                                  r.get("status"),
        "reason":                                  r.get("reason"),
        "note":                                      r.get("note"),
        "failure_reason":                    r.get("failure_reason"),
        "requested_by_user_id":      r.get("requested_by_user_id"),
        "requested_by_role":            r.get("requested_by_role"),
        "created_at":                          _iso(r.get("created_at")),
        "succeeded_at":                      _iso(r.get("succeeded_at")),
        "failed_at":                            _iso(r.get("failed_at")),
    }


def _payout_view(p: dict) -> dict:
    return {
        "payout_id":                                p.get("payout_id") or p.get("_id"),
        "stripe_payout_id":                    p.get("stripe_payout_id"),
        "merchant_id":                            p.get("merchant_id"),
        "stripe_connected_account_id": p.get("stripe_connected_account_id"),
        "amount_cents":                            int(p.get("amount_cents") or 0),
        "currency":                                    p.get("currency"),
        "status":                                      p.get("status"),
        "method":                                      p.get("method"),
        "type":                                          p.get("type"),
        "description":                            p.get("description"),
        "failure_code":                          p.get("failure_code"),
        "failure_reason":                        p.get("failure_reason"),
        "arrival_date":                          _iso(p.get("arrival_date")),
        "created_at":                              _iso(p.get("created_at")),
        "paid_at":                                    _iso(p.get("paid_at")),
        "failed_at":                                _iso(p.get("failed_at")),
    }


def _dispute_view(d: dict) -> dict:
    return {
        "dispute_id":                        d.get("dispute_id") or d.get("_id"),
        "stripe_dispute_id":        d.get("stripe_dispute_id"),
        "transaction_id":              d.get("transaction_id"),
        "merchant_id":                    d.get("merchant_id"),
        "stripe_charge_id":          d.get("stripe_charge_id"),
        "amount_cents":                  int(d.get("amount_cents") or 0),
        "currency":                          d.get("currency"),
        "reason":                              d.get("reason"),
        "status":                              d.get("status"),
        "resolution":                    d.get("resolution"),
        "evidence_due_by":          _iso(d.get("evidence_due_by")),
        "created_at":                    _iso(d.get("created_at")),
        "resolved_at":                  _iso(d.get("resolved_at")),
    }


def _tx_summary_view(tx: dict) -> dict:
    return {
        "transaction_id":                tx.get("transaction_id"),
        "status":                              tx.get("status"),
        "amount_cents":                    int(tx.get("amount_cents") or 0),
        "refunded_cents":                int(tx.get("refunded_cents") or 0),
        "application_fee_cents":  int(tx.get("application_fee_cents") or 0),
        "application_fee_refunded_cents": int(tx.get("application_fee_refunded_cents") or 0),
        "currency":                            tx.get("currency"),
        "payment_method_type":  tx.get("payment_method_type"),
        "customer_email":                tx.get("customer_email"),
        "stripe_payment_intent_id": tx.get("stripe_payment_intent_id"),
        "stripe_charge_id":              tx.get("stripe_charge_id"),
        "succeeded_at":                  _iso(tx.get("succeeded_at")),
        "created_at":                      _iso(tx.get("created_at")),
        "last_refund_at":                _iso(tx.get("last_refund_at")),
    }


# ─── Bodies ──────────────────────────────────────────────────────
class RefundBody(BaseModel):
    transaction_id:                    str = Field(min_length=4, max_length=120)
    amount_cents:                          Optional[int] = Field(default=None, ge=1)
    reason:                                    str = Field(default="requested_by_customer")
    refund_application_fee:      Optional[bool] = Field(default=None)
    note:                                        Optional[str] = Field(default=None, max_length=500)


# ─── Refund endpoints ────────────────────────────────────────────
@router.post("/admin/refunds")
async def sc6_admin_refund(body: RefundBody, request: Request,
                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    if body.reason not in VALID_REASONS:
        raise HTTPException(400, {"code": "invalid_reason",
                                                          "allowed": sorted(VALID_REASONS)})
    try:
        r = await create_refund(
            db,
            transaction_id=body.transaction_id,
            amount_cents=body.amount_cents,
            reason=body.reason,
            refund_application_fee=(True if body.refund_application_fee is None
                                                                else body.refund_application_fee),
            requested_by_user_id=admin.get("user_id"),
            requested_by_role="admin",
            note=body.note)
    except RefundError as e:
        raise HTTPException(e.http_status, {"code": e.code, "detail": e.detail})
    return r


@router.post("/merchant/{merchant_id}/refunds")
async def sc6_merchant_refund(merchant_id: str, body: RefundBody,
                                                            request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_refund")
    # Validate the tx belongs to this merchant
    tx = await db.payment_transactions_v2.find_one(
        {"transaction_id": body.transaction_id})
    if not tx:
        raise HTTPException(404, "transaction_not_found")
    biz_id = biz.get("business_id") or biz.get("_id")
    if tx.get("merchant_id") != biz_id:
        raise HTTPException(403, "transaction_not_owned")

    if body.reason not in VALID_REASONS:
        raise HTTPException(400, {"code": "invalid_reason",
                                                          "allowed": sorted(VALID_REASONS)})

    try:
        r = await create_refund(
            db,
            transaction_id=body.transaction_id,
            amount_cents=body.amount_cents,
            reason=body.reason,
            # Merchants can't refund the application fee; platform keeps commission
            refund_application_fee=False,
            requested_by_user_id=user.get("user_id"),
            requested_by_role="merchant",
            note=body.note)
    except RefundError as e:
        raise HTTPException(e.http_status, {"code": e.code, "detail": e.detail})
    return r


@router.get("/refunds/{refund_id}")
async def sc6_refund_detail(refund_id: str, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.refunds.find_one({"refund_id": refund_id})
    if not r:
        raise HTTPException(404, "refund_not_found")

    is_admin = user.get("role") == "admin" or user.get("is_admin")
    if not is_admin:
        tx = await db.payment_transactions_v2.find_one(
            {"transaction_id": r["transaction_id"]})
        biz = await db.businesses.find_one({"$or": [
            {"business_id": r.get("merchant_id")},
            {"_id": r.get("merchant_id")}]})
        allowed = (biz and biz.get("owner_user_id") == user["user_id"]) \
                          or (tx and tx.get("customer_user_id") == user["user_id"])
        if not allowed:
            raise HTTPException(403, "not_authorized")
    return _refund_view(r)


@router.get("/admin/refunds")
async def sc6_admin_refunds_list(request: Request,
                                                                merchant_id: Optional[str] = Query(None),
                                                                status: Optional[str] = Query(None),
                                                                limit: int = Query(50, ge=1, le=200),
                                                                offset: int = Query(0, ge=0),
                                                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    q = {}
    if merchant_id: q["merchant_id"] = merchant_id
    if status:            q["status"] = status
    total = await db.refunds.count_documents(q)
    rows = await db.refunds.find(q).sort("created_at", -1) \
                                      .skip(offset).limit(limit).to_list(length=limit)
    # Enrich with merchant name
    mids = list({r.get("merchant_id") for r in rows if r.get("merchant_id")})
    biz_map = {}
    if mids:
        async for b in db.businesses.find(
            {"$or": [{"business_id": {"$in": mids}}, {"_id": {"$in": mids}}]},
            {"business_id": 1, "_id": 1, "name": 1}):
            key = b.get("business_id") or b.get("_id")
            biz_map[key] = b.get("name")
    out = []
    for r in rows:
        rv = _refund_view(r)
        rv["merchant_name"] = biz_map.get(r.get("merchant_id"))
        out.append(rv)
    return {"total": total, "limit": limit, "offset": offset, "rows": out}


# ─── Payout endpoints ────────────────────────────────────────────
@router.get("/merchant/{merchant_id}/payouts")
async def sc6_merchant_payouts(merchant_id: str, request: Request,
                                                            status: Optional[str] = Query(None),
                                                            limit: int = Query(50, ge=1, le=200),
                                                            offset: int = Query(0, ge=0),
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_view_payouts")
    biz_id = biz.get("business_id") or biz.get("_id")
    q = {"merchant_id": biz_id}
    if status: q["status"] = status
    total = await db.merchant_payout_ledger.count_documents(q)
    rows = await db.merchant_payout_ledger.find(q) \
                              .sort("created_at", -1).skip(offset).limit(limit) \
                              .to_list(length=limit)

    # Aggregates
    agg_pipeline = [
        {"$match": {"merchant_id": biz_id}},
        {"$group": {"_id": "$status",
                              "count": {"$sum": 1},
                              "sum_amount": {"$sum": "$amount_cents"}}},
    ]
    aggs = await db.merchant_payout_ledger.aggregate(agg_pipeline).to_list(None)
    summary = {
        "total_paid_cents":  sum(a["sum_amount"] for a in aggs if a["_id"] == "paid"),
        "pending_cents":      sum(a["sum_amount"] for a in aggs if a["_id"] in ("pending", "in_transit")),
        "failed_cents":        sum(a["sum_amount"] for a in aggs if a["_id"] == "failed"),
        "count_by_status": {a["_id"]: a["count"] for a in aggs},
    }
    return {"total": total, "limit": limit, "offset": offset,
                  "rows": [_payout_view(p) for p in rows],
                  "summary": summary}


@router.get("/admin/payouts")
async def sc6_admin_payouts(request: Request,
                                                      merchant_id: Optional[str] = Query(None),
                                                      status: Optional[str] = Query(None),
                                                      limit: int = Query(50, ge=1, le=200),
                                                      offset: int = Query(0, ge=0),
                                                      admin: dict = Depends(require_admin)):
    db = request.app.state.db
    q = {}
    if merchant_id: q["merchant_id"] = merchant_id
    if status:            q["status"] = status
    total = await db.merchant_payout_ledger.count_documents(q)
    rows = await db.merchant_payout_ledger.find(q) \
                              .sort("created_at", -1).skip(offset).limit(limit) \
                              .to_list(length=limit)
    mids = list({r.get("merchant_id") for r in rows if r.get("merchant_id")})
    biz_map = {}
    if mids:
        async for b in db.businesses.find(
            {"$or": [{"business_id": {"$in": mids}}, {"_id": {"$in": mids}}]},
            {"business_id": 1, "_id": 1, "name": 1}):
            key = b.get("business_id") or b.get("_id")
            biz_map[key] = b.get("name")
    out = []
    for p in rows:
        pv = _payout_view(p)
        pv["merchant_name"] = biz_map.get(p.get("merchant_id"))
        out.append(pv)
    return {"total": total, "limit": limit, "offset": offset, "rows": out}


# ─── Dispute endpoints ───────────────────────────────────────────
@router.get("/admin/disputes")
async def sc6_admin_disputes(request: Request,
                                                        merchant_id: Optional[str] = Query(None),
                                                        status: Optional[str] = Query(None),
                                                        limit: int = Query(50, ge=1, le=200),
                                                        offset: int = Query(0, ge=0),
                                                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    q = {}
    if merchant_id: q["merchant_id"] = merchant_id
    if status:            q["status"] = status
    total = await db.stripe_disputes.count_documents(q)
    rows = await db.stripe_disputes.find(q) \
                                .sort("created_at", -1).skip(offset).limit(limit) \
                                .to_list(length=limit)
    mids = list({r.get("merchant_id") for r in rows if r.get("merchant_id")})
    biz_map = {}
    if mids:
        async for b in db.businesses.find(
            {"$or": [{"business_id": {"$in": mids}}, {"_id": {"$in": mids}}]},
            {"business_id": 1, "_id": 1, "name": 1}):
            key = b.get("business_id") or b.get("_id")
            biz_map[key] = b.get("name")
    out = []
    for d in rows:
        dv = _dispute_view(d)
        dv["merchant_name"] = biz_map.get(d.get("merchant_id"))
        out.append(dv)
    return {"total": total, "limit": limit, "offset": offset, "rows": out}


# ─── Merchant per-link transactions (drawer Transactions tab) ────
@router.get("/merchant/{merchant_id}/payment-links/{link_id}/transactions")
async def sc6_link_transactions(merchant_id: str, link_id: str,
                                                            request: Request,
                                                            limit: int = Query(20, ge=1, le=100),
                                                            offset: int = Query(0, ge=0),
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_view_transactions")
    biz_id = biz.get("business_id") or biz.get("_id")
    q = {"merchant_id": biz_id, "link_id": link_id,
          "status": {"$in": ["succeeded", "refunded", "failed", "canceled"]}}
    total = await db.payment_transactions_v2.count_documents(q)
    rows = await db.payment_transactions_v2.find(q) \
                                .sort([("succeeded_at", -1), ("created_at", -1)]) \
                                .skip(offset).limit(limit).to_list(length=limit)
    # Enrich with refunds list
    tx_ids = [r["transaction_id"] for r in rows]
    refunds_by_tx = {}
    if tx_ids:
        async for r in db.refunds.find({"transaction_id": {"$in": tx_ids}}) \
                                                    .sort("created_at", -1):
            refunds_by_tx.setdefault(r["transaction_id"], []).append(_refund_view(r))
    out = []
    for tx in rows:
        v = _tx_summary_view(tx)
        v["refunds"] = refunds_by_tx.get(tx["transaction_id"], [])
        out.append(v)
    return {"total": total, "limit": limit, "offset": offset, "rows": out}


__all__ = ["router"]
