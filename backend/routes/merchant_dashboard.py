"""Phase MER.1 — Merchant Desktop Dashboard endpoints.

Track 2 kick-off.  Aggregates Track 1 data (SC.1-SC.6) into a single
dashboard payload for the merchant portal + adds a merchant-wide
transaction list.

Endpoints:
    GET  /api/merchant/{merchant_id}/dashboard/overview
    GET  /api/merchant/{merchant_id}/transactions
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user

logger = logging.getLogger("bigfm.mer1")
router = APIRouter(prefix="/api", tags=["mer1"])


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ─── Auth resolver — merchant-owner OR admin ─────────────────────
# Phase MER.2 — extended to accept staff-role users with the right
# permission alongside owners + admins.
async def _resolve_owner(db, merchant_id: str, user: dict,
                                                *, permission: Optional[str] = None,
                                                allow_any_staff: bool = False) -> dict:
    from services.merchant_rbac_service import resolve_merchant_with_role
    biz, _role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission=permission, allow_any_staff=allow_any_staff)
    return biz


# ─── Overview aggregator ─────────────────────────────────────────
@router.get("/merchant/{merchant_id}/dashboard/overview")
async def merchant_dashboard_overview(merchant_id: str, request: Request,
                                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    # Overview is readable by ANY active member (owner / manager / cashier / marketing / analytics_only).
    biz = await _resolve_owner(db, merchant_id, user, allow_any_staff=True)
    biz_id = biz.get("business_id") or biz.get("_id")

    now = _now()
    month_start = _month_start(now)
    last_month_start = _month_start(month_start - timedelta(days=1))
    last_30_start = now - timedelta(days=30)
    prev_30_start = now - timedelta(days=60)

    # ─── KPIs from payment_transactions_v2 ─────────────────────
    async def _sum_succeeded(from_dt, to_dt=None):
        match = {"merchant_id": biz_id, "status": "succeeded",
                        "succeeded_at": {"$gte": from_dt}}
        if to_dt: match["succeeded_at"]["$lt"] = to_dt
        pipe = [{"$match": match},
                        {"$group": {"_id": None,
                                              "count": {"$sum": 1},
                                              "sum":    {"$sum": "$amount_cents"}}}]
        r = await db.payment_transactions_v2.aggregate(pipe).to_list(1)
        return (r[0]["count"] if r else 0), (r[0]["sum"] if r else 0)

    cnt_month, rev_month = await _sum_succeeded(month_start)
    cnt_last_month, rev_last_month = await _sum_succeeded(
        last_month_start, month_start)
    cnt_30d,      rev_30d      = await _sum_succeeded(last_30_start)
    cnt_prev_30, rev_prev_30 = await _sum_succeeded(prev_30_start, last_30_start)

    avg_month = int(rev_month / cnt_month) if cnt_month else 0
    revenue_delta_pct = None
    if rev_last_month > 0:
        revenue_delta_pct = round(
            ((rev_month - rev_last_month) / rev_last_month) * 100, 1)

    # ─── Active payment links + impressions ──────────────────
    active_links = await db.merchant_payment_links.count_documents(
        {"merchant_id": biz_id, "active": True})
    imp_pipe = [
        {"$match": {"merchant_id": biz_id,
                              "viewed_at": {"$gte": last_30_start}}},
        {"$group": {"_id": None, "n": {"$sum": 1}}},
    ]
    imp_r = await db.payment_link_impressions.aggregate(imp_pipe).to_list(1)
    impressions_30d = imp_r[0]["n"] if imp_r else 0

    # ─── Payouts (from SC.6 ledger) ──────────────────────────
    payout_pipe = [
        {"$match": {"merchant_id": biz_id}},
        {"$group": {"_id": "$status",
                              "count": {"$sum": 1},
                              "sum":    {"$sum": "$amount_cents"}}},
    ]
    payout_agg = await db.merchant_payout_ledger.aggregate(payout_pipe).to_list(None)
    pending_payout_cents = sum(a["sum"] for a in payout_agg
                                                        if a["_id"] in ("pending", "in_transit"))
    last_payout = await db.merchant_payout_ledger.find_one(
        {"merchant_id": biz_id, "status": "paid"},
        sort=[("paid_at", -1)])
    last_payout_view = None
    if last_payout:
        last_payout_view = {
            "payout_id":        last_payout.get("stripe_payout_id"),
            "amount_cents": int(last_payout.get("amount_cents") or 0),
            "currency":        last_payout.get("currency"),
            "status":            last_payout.get("status"),
            "paid_at":          _iso(last_payout.get("paid_at")),
        }

    # ─── Top payment links (by usage) ─────────────────────────
    top_links_cursor = db.merchant_payment_links.find(
        {"merchant_id": biz_id, "active": True}
    ).sort([("usage_count", -1), ("impressions", -1)]).limit(5)
    top_links = []
    async for lk in top_links_cursor:
        # Compute revenue for this link over last 30d
        rev_pipe = [
            {"$match": {"link_id": lk["link_id"], "status": "succeeded",
                                  "succeeded_at": {"$gte": last_30_start}}},
            {"$group": {"_id": None, "sum": {"$sum": "$amount_cents"}}},
        ]
        rev_r = await db.payment_transactions_v2.aggregate(rev_pipe).to_list(1)
        rev_link = rev_r[0]["sum"] if rev_r else 0
        top_links.append({
            "link_id":                          lk.get("link_id"),
            "token":                              lk.get("token"),
            "title":                              lk.get("title") or "Untitled",
            "link_type":                      lk.get("link_type"),
            "usage_count":                  int(lk.get("usage_count") or 0),
            "impressions":                  int(lk.get("impressions") or 0),
            "revenue_cents_last_30d": int(rev_link),
            "currency":                        lk.get("currency") or "USD",
            "hosted_url":                    lk.get("hosted_url"),
        })

    # ─── Recent activity feed (last 10 events) ─────────────
    recent = []
    # Last 8 transactions
    async for tx in db.payment_transactions_v2.find(
        {"merchant_id": biz_id,
          "status": {"$in": ["succeeded", "refunded", "failed"]}}
    ).sort([("succeeded_at", -1), ("created_at", -1)]).limit(8):
        recent.append({
            "type":                              "transaction",
            "id":                                  tx.get("transaction_id"),
            "amount_cents":              int(tx.get("amount_cents") or 0),
            "currency":                      tx.get("currency"),
            "status":                          tx.get("status"),
            "payment_method_type": tx.get("payment_method_type"),
            "customer_email":            tx.get("customer_email"),
            "link_id":                        tx.get("link_id"),
            "at":                                  _iso(tx.get("succeeded_at")
                                                              or tx.get("created_at")),
        })

    # Last 3 refunds
    async for r in db.refunds.find(
        {"merchant_id": biz_id, "status": "succeeded"}
    ).sort("succeeded_at", -1).limit(3):
        recent.append({
            "type":                          "refund",
            "id":                              r.get("refund_id"),
            "transaction_id":        r.get("transaction_id"),
            "amount_cents":          int(r.get("amount_cents") or 0),
            "currency":                  r.get("currency"),
            "at":                              _iso(r.get("succeeded_at")),
        })

    # Last 3 payouts
    async for p in db.merchant_payout_ledger.find(
        {"merchant_id": biz_id}
    ).sort("created_at", -1).limit(3):
        recent.append({
            "type":                          "payout",
            "id":                              p.get("stripe_payout_id"),
            "amount_cents":          int(p.get("amount_cents") or 0),
            "currency":                  p.get("currency"),
            "status":                      p.get("status"),
            "at":                              _iso(p.get("created_at")),
        })

    # Sort merged feed by `at` desc, keep 10
    recent.sort(key=lambda e: (e.get("at") or ""), reverse=True)
    recent = recent[:10]

    # ─── Assemble response ────────────────────────────────────
    return {
        "merchant": {
            "id":                                    biz_id,
            "name":                              biz.get("name"),
            "logo_url":                        biz.get("logo_url"),
            "category":                        biz.get("category_id") or biz.get("category"),
            "merchant_status":            biz.get("merchant_status") or "draft",
            "owner_user_id":              biz.get("owner_user_id"),
        },
        "kpis": {
            "revenue_this_month_cents":  int(rev_month),
            "revenue_last_month_cents":  int(rev_last_month),
            "revenue_delta_pct":              revenue_delta_pct,
            "revenue_last_30d_cents":      int(rev_30d),
            "revenue_prev_30d_cents":      int(rev_prev_30),
            "transactions_this_month":  int(cnt_month),
            "transactions_last_month":  int(cnt_last_month),
            "avg_transaction_cents":      int(avg_month),
            "active_payment_links":        int(active_links),
            "total_impressions_last_30d": int(impressions_30d),
            "pending_payout_cents":        int(pending_payout_cents),
            "last_payout":                        last_payout_view,
        },
        "stripe_status": {
            "charges_enabled":              bool(biz.get("stripe_charges_enabled")),
            "payouts_enabled":              bool(biz.get("stripe_payouts_enabled")),
            "details_submitted":          bool(biz.get("stripe_details_submitted")),
            "onboarding_status":          biz.get("stripe_onboarding_status")
                                                                or "not_started",
            "requirements_currently_due": list(
                biz.get("stripe_requirements_currently_due") or []),
            "requirements_past_due":  list(
                biz.get("stripe_requirements_past_due") or []),
            "disabled_reason":                biz.get(
                "stripe_requirements_disabled_reason"),
        },
        "top_payment_links": top_links,
        "recent_activity":    recent,
        "generated_at":            _iso(now),
    }


# ─── Merchant-wide transactions listing ──────────────────────────
@router.get("/merchant/{merchant_id}/transactions")
async def merchant_transactions(merchant_id: str, request: Request,
                                                              status: Optional[str] = Query(None),
                                                              link_id: Optional[str] = Query(None),
                                                              limit: int = Query(50, ge=1, le=200),
                                                              offset: int = Query(0, ge=0),
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_view_transactions")
    biz_id = biz.get("business_id") or biz.get("_id")

    q = {"merchant_id": biz_id}
    if status:  q["status"]  = status
    if link_id: q["link_id"] = link_id

    total = await db.payment_transactions_v2.count_documents(q)
    rows = await db.payment_transactions_v2.find(q).sort(
        [("succeeded_at", -1), ("created_at", -1)]
    ).skip(offset).limit(limit).to_list(length=limit)

    # Enrich each row with the link title (small denormalization for UI)
    link_ids = list({r.get("link_id") for r in rows if r.get("link_id")})
    link_map = {}
    if link_ids:
        async for lk in db.merchant_payment_links.find(
            {"link_id": {"$in": link_ids}},
            {"link_id": 1, "title": 1, "link_type": 1, "token": 1}):
            link_map[lk["link_id"]] = lk

    out = []
    for tx in rows:
        link = link_map.get(tx.get("link_id")) or {}
        out.append({
            "transaction_id":                tx.get("transaction_id"),
            "status":                              tx.get("status"),
            "amount_cents":                    int(tx.get("amount_cents") or 0),
            "refunded_cents":                int(tx.get("refunded_cents") or 0),
            "application_fee_cents":  int(tx.get("application_fee_cents") or 0),
            "currency":                            tx.get("currency"),
            "payment_method_type":  tx.get("payment_method_type"),
            "customer_email":                tx.get("customer_email"),
            "link_id":                              tx.get("link_id"),
            "link_title":                      link.get("title") or "—",
            "link_type":                        link.get("link_type"),
            "link_token":                      link.get("token") or tx.get("link_token"),
            "created_at":                      _iso(tx.get("created_at")),
            "succeeded_at":                  _iso(tx.get("succeeded_at")),
            "failure_reason":                tx.get("failure_reason"),
        })

    return {"total": total, "limit": limit, "offset": offset, "rows": out}


__all__ = ["router"]
