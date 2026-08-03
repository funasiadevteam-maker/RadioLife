"""Phase 41 Session 6.A — Creator revenue dashboard + payout endpoints.

Public surface:

  - `GET  /api/me/earnings?window=7d|30d|90d|all&station_slug=optional`
        Owner-side composite payload (totals + per-source + per-station +
        recent 50 ledger rows).

  - `GET  /api/stations/{slug}/earnings?window=7d|30d|90d|all`
        Station-scoped — owner only.

  - `POST /api/me/stripe_connect/onboard`
        MOCKED Stripe Connect onboarding kick-off. Flips the user's
        `stripe_connect_status` to `pending` and returns a mock URL.
        Repeated calls just return the existing mock URL.

  - `POST /api/me/stripe_connect/activate`        (dev shim)
        MOCKED — flips status to `active`. In real life this is a
        webhook callback from Stripe Connect.

  - `GET  /api/me/stripe_connect/status`
        Returns the user's current connect status.

  - `POST /api/me/payout/request`
        MOCKED payout request. Validates that connect is active +
        there is pending creator_cents to pay out. Writes a
        `payout_requests` row in `pending` state.

  - `GET  /api/me/payouts`
        List the user's payout requests + status.

  - `POST /api/admin/earnings/direct_deal`
        Admin-only manual ledger insert for off-platform deals.

  - `GET  /api/admin/earnings/ledger?status=&from=&to=&owner_user_id=`
        Admin reconciliation view.

All Stripe Connect logic is MOCKED — no real Stripe API calls. Marked
with MOCKED comments inline + via the response payload.
"""
from __future__ import annotations
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user
from services.creator_revenue import (
    compute_earnings,
    write_ledger_row,
    VALID_SOURCE_TYPES,
    LEDGER_STATUSES,
    CREATOR_REV_SHARE_PCT,
)

router = APIRouter(prefix="/api", tags=["creator-revenue"])
admin_router = APIRouter(prefix="/api/admin", tags=["creator-revenue-admin"])
log = logging.getLogger("bigfm.creator_revenue_routes")

WINDOW_DAYS = {"7d": 7, "30d": 30, "90d": 90, "all": None}
DEFAULT_WINDOW = "7d"

# MOCKED — placeholder Stripe Connect base. Never hits real Stripe.
MOCK_STRIPE_CONNECT_BASE = (
    "https://connect.stripe.com/express/onboarding/MOCKED")


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str:  return _now().isoformat()


def _is_admin(user: Optional[dict]) -> bool:
    return bool(user and (user.get("role") == "admin" or user.get("is_admin")))


def _norm_window(window: str) -> tuple[Optional[datetime], datetime, str]:
    if window not in WINDOW_DAYS:
        window = DEFAULT_WINDOW
    end = _now()
    days = WINDOW_DAYS[window]
    if days is None:
        return None, end, "all"
    return end - timedelta(days=days), end, window


async def _resolve_owner_station(db, slug: str, user: dict) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if s.get("owner_user_id") != user.get("user_id") and not _is_admin(user):
        raise HTTPException(403, {"code": "permission_denied",
                                    "message": "Owner only."})
    s.pop("_id", None)
    return s


# ----- earnings reads ------------------------------------------------
@router.get("/me/earnings")
async def my_earnings(request: Request,
                        window: str = Query("7d"),
                        station_slug: Optional[str] = Query(None),
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    start, end, normalized = _norm_window(window)
    payload = await compute_earnings(
        db, owner_user_id=user["user_id"],
        station_slug=station_slug, start=start, end=end)
    payload["window"] = normalized
    return payload


@router.get("/stations/{slug}/earnings")
async def station_earnings(slug: str, request: Request,
                              window: str = Query("7d"),
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _resolve_owner_station(db, slug, user)
    start, end, normalized = _norm_window(window)
    payload = await compute_earnings(
        db, owner_user_id=station["owner_user_id"],
        station_slug=slug, start=start, end=end)
    payload["window"] = normalized
    return payload


# ----- Stripe Connect (MOCKED) --------------------------------------
@router.post("/me/stripe_connect/onboard")
async def stripe_connect_onboard(request: Request,
                                    user: dict = Depends(current_user)):
    """MOCKED — does NOT call real Stripe. Flips connect status to
    `pending` and returns a mock onboarding URL the frontend can
    open."""
    db = request.app.state.db
    uid = user["user_id"]
    now_iso = _now_iso()
    rec = await db.users.find_one({"user_id": uid}) or {}
    current = (rec.get("stripe_connect_status") or "none")
    mock_account_id = (rec.get("stripe_connect_account_id")
                         or f"acct_MOCK_{uuid.uuid4().hex[:14]}")
    onboarding_url = (
        f"{MOCK_STRIPE_CONNECT_BASE}?account={mock_account_id}"
        f"&user={uid}&ts={int(_now().timestamp())}")
    new_status = "pending" if current != "active" else "active"
    await db.users.update_one(
        {"user_id": uid},
        {"$set": {
            "stripe_connect_status":     new_status,
            "stripe_connect_account_id": mock_account_id,
            "stripe_connect_updated_at": now_iso,
        }})
    return {
        "mock":                       True,
        "stripe_connect_status":      new_status,
        "stripe_connect_account_id":  mock_account_id,
        "onboarding_url":             onboarding_url,
        "note":                       "MOCKED — does not call real Stripe.",
    }


@router.post("/me/stripe_connect/activate")
async def stripe_connect_activate(request: Request,
                                     user: dict = Depends(current_user)):
    """MOCKED dev shim — flips a pending connect to `active`. In
    production this would land via a Stripe webhook
    (`account.updated` with `details_submitted=true`)."""
    db = request.app.state.db
    uid = user["user_id"]
    await db.users.update_one(
        {"user_id": uid},
        {"$set": {"stripe_connect_status":     "active",
                  "stripe_connect_updated_at": _now_iso()}})
    rec = await db.users.find_one({"user_id": uid}) or {}
    return {
        "mock":                  True,
        "stripe_connect_status": rec.get("stripe_connect_status"),
        "stripe_connect_account_id": rec.get("stripe_connect_account_id"),
        "note":                  "MOCKED activation.",
    }


@router.get("/me/stripe_connect/status")
async def stripe_connect_status(request: Request,
                                   user: dict = Depends(current_user)):
    db = request.app.state.db
    rec = await db.users.find_one({"user_id": user["user_id"]}) or {}
    return {
        "stripe_connect_status":     rec.get("stripe_connect_status") or "none",
        "stripe_connect_account_id": rec.get("stripe_connect_account_id"),
        "stripe_connect_updated_at": rec.get("stripe_connect_updated_at"),
    }


# ----- payouts (MOCKED) ----------------------------------------------
@router.post("/me/payout/request")
async def request_payout(request: Request,
                            user: dict = Depends(current_user)):
    """MOCKED — does NOT initiate a real Stripe transfer. Validates
    eligibility, writes a `payout_requests` row in `pending` state."""
    db = request.app.state.db
    uid = user["user_id"]
    rec = await db.users.find_one({"user_id": uid}) or {}
    if (rec.get("stripe_connect_status") or "") != "active":
        raise HTTPException(409, {"code": "stripe_connect_not_active",
                                    "message": "Connect Stripe to receive payouts."})

    pending = await db.creator_earnings_ledger.aggregate([
        {"$match": {"owner_user_id": uid, "status": "recorded"}},
        {"$group": {"_id": None,
                    "creator": {"$sum": "$creator_amount_cents"},
                    "count":   {"$sum": 1}}},
    ]).to_list(1)
    pending_cents = pending[0].get("creator", 0) if pending else 0
    pending_count = pending[0].get("count",   0) if pending else 0
    if pending_cents <= 0:
        raise HTTPException(409, {"code": "no_pending_balance",
                                    "message": "Nothing to pay out yet."})

    payout_id = f"po_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id":               payout_id,
        "payout_id":         payout_id,
        "user_id":           uid,
        "amount_cents":      pending_cents,
        "currency":          "USD",
        "ledger_row_count":  pending_count,
        "status":            "pending",
        "stripe_transfer_id": None,
        "stripe_connect_account_id": rec.get("stripe_connect_account_id"),
        "requested_at":      _now_iso(),
        "mock":              True,
    }
    await db.payout_requests.insert_one(doc)
    log.info("[creator_revenue] MOCKED payout requested user=%s "
                "amount=%s rows=%s", uid, pending_cents, pending_count)
    return {
        "ok":         True,
        "payout_id":  payout_id,
        "amount_cents": pending_cents,
        "status":     "pending",
        "mock":       True,
        "note":       "MOCKED — no real Stripe transfer initiated.",
    }


@router.get("/me/payouts")
async def my_payouts(request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    cur = db.payout_requests.find(
        {"user_id": user["user_id"]}).sort("requested_at", -1).limit(50)
    items: list = []
    async for r in cur:
        r.pop("_id", None)
        items.append(r)
    return {"items": items, "count": len(items)}


# ----- admin reconciliation -----------------------------------------
@admin_router.get("/earnings/ledger")
async def admin_ledger(request: Request,
                          status: Optional[str] = Query(None),
                          source_type: Optional[str] = Query(None),
                          owner_user_id: Optional[str] = Query(None),
                          station_slug: Optional[str] = Query(None),
                          limit: int = Query(200, ge=1, le=1000),
                          user: dict = Depends(current_user)):
    if not _is_admin(user):
        raise HTTPException(403, {"code": "permission_denied",
                                    "message": "Admin only."})
    db = request.app.state.db
    q: dict = {}
    if status:
        if status not in LEDGER_STATUSES:
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "status"})
        q["status"] = status
    if source_type:
        if source_type not in VALID_SOURCE_TYPES:
            raise HTTPException(400, {"code": "validation_error",
                                        "field": "source_type"})
        q["source_type"] = source_type
    if owner_user_id:
        q["owner_user_id"] = owner_user_id
    if station_slug:
        q["station_slug"] = station_slug

    totals = await db.creator_earnings_ledger.aggregate([
        {"$match": q},
        {"$group": {"_id": None,
                    "gross":   {"$sum": "$gross_amount_cents"},
                    "creator": {"$sum": "$creator_amount_cents"},
                    "house":   {"$sum": "$house_cut_cents"},
                    "count":   {"$sum": 1}}},
    ]).to_list(1)
    headline = totals[0] if totals else {
        "gross": 0, "creator": 0, "house": 0, "count": 0}

    cur = db.creator_earnings_ledger.find(q).sort(
        [("occurred_at", -1)]).limit(limit)
    items: list = []
    async for r in cur:
        r.pop("_id", None)
        oc = r.get("occurred_at")
        ca = r.get("created_at")
        items.append({
            "source_ref":           r.get("source_ref"),
            "station_slug":         r.get("station_slug"),
            "station_id":           r.get("station_id"),
            "owner_user_id":        r.get("owner_user_id"),
            "source_type":          r.get("source_type"),
            "gross_amount_cents":   r.get("gross_amount_cents", 0),
            "house_cut_cents":      r.get("house_cut_cents", 0),
            "creator_amount_cents": r.get("creator_amount_cents", 0),
            "currency":             r.get("currency", "USD"),
            "status":               r.get("status", "recorded"),
            "occurred_at":          (oc.isoformat()
                                       if isinstance(oc, datetime) else oc),
            "created_at":           (ca.isoformat()
                                       if isinstance(ca, datetime) else ca),
        })
    return {
        "filters": {"status": status, "source_type": source_type,
                     "owner_user_id": owner_user_id,
                     "station_slug": station_slug, "limit": limit},
        "headline": {
            "total_gross_cents":   headline.get("gross", 0),
            "total_creator_cents": headline.get("creator", 0),
            "total_house_cents":   headline.get("house", 0),
            "ledger_row_count":    headline.get("count", 0),
            "currency":            "USD",
        },
        "items": items,
        "count": len(items),
        "config": {"share_pct": CREATOR_REV_SHARE_PCT},
    }


@admin_router.post("/earnings/direct_deal")
async def admin_direct_deal(request: Request, body: dict,
                               user: dict = Depends(current_user)):
    """Admin-only manual ledger insert for off-platform deals."""
    if not _is_admin(user):
        raise HTTPException(403, {"code": "permission_denied",
                                    "message": "Admin only."})
    db = request.app.state.db
    slug = (body.get("station_slug") or "").strip()
    if not slug:
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "station_slug"})
    gross = body.get("gross_amount_cents")
    try:
        gross = int(gross)
    except Exception:
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "gross_amount_cents"})
    if gross <= 0:
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "gross_amount_cents",
                                    "message": "Must be > 0."})
    note = (body.get("note") or "").strip()[:280]

    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    owner = s.get("owner_user_id")
    if not owner:
        raise HTTPException(400, {"code": "validation_error",
                                    "field": "station_slug",
                                    "message": "Station has no owner."})

    source_ref = f"dd_{uuid.uuid4().hex[:14]}"
    doc = await write_ledger_row(
        db, station=s, owner_user_id=owner,
        source_type="direct_deal",
        source_ref=source_ref,
        gross_amount_cents=gross,
        attribution_metadata={"note": note,
                                "admin_user_id": user.get("user_id")})
    # Bust analytics cache so the dashboard reflects this row immediately.
    try:
        from routes.station_analytics import bust_analytics_cache
        bust_analytics_cache(slug)
    except Exception:
        pass
    if not doc:
        raise HTTPException(500, {"code": "ledger_write_failed"})
    return {"ok": True, "source_ref": source_ref,
              "creator_amount_cents": doc.get("creator_amount_cents")}
