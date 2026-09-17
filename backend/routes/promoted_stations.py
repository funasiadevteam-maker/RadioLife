"""Promoted / sponsored radio stations.

Lets a radio station pay to be surfaced first in the Explore + Home rails
with a small "Sponsored" tag.  Supports two pricing models:

    • CPM — billed per 1,000 impressions (cpm_bid_cents / 1000 per view)
    • CPC — billed per click (cpc_bid_cents per click)

Spend accrues on the promo doc (`spend_cents`).  Real wallet settlement is
out of scope for this MVP — the accrual is the source of truth the billing
layer can reconcile against.

Endpoints:
    GET  /api/promoted/stations?limit=          — active promos as station cards
    POST /api/promoted/{promo_id}/impression     — track a view  (CPM accrual)
    POST /api/promoted/{promo_id}/click          — track a click (CPC accrual)
    POST /api/promoted                            — admin: create a promo
    GET  /api/promoted/admin                      — admin: list all promos
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth import current_user, current_user_optional, require_admin
from routes.radio_unified import (
    _ai_channel_to_card, _community_to_card, _imported_to_card,
)

router = APIRouter(prefix="/api/promoted", tags=["promoted-stations"])

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""
_TOPUP_PACKAGES = {"topup_10": 1000, "topup_25": 2500, "topup_50": 5000, "topup_100": 10000}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


async def _record_daily_and_cap(db, promo: Dict[str, Any], accrue: int) -> None:
    """Roll up per-day impressions/clicks/spend and auto-pause the promo when
    its `daily_budget_cents` cap is hit for the current UTC day."""
    promo_id = promo.get("promo_id")
    await db.promo_daily.update_one(
        {"promo_id": promo_id, "date": _today()},
        {"$inc": {"spend_cents": accrue}, "$setOnInsert": {"created_at": _now()}},
        upsert=True)
    cap = int(promo.get("daily_budget_cents") or 0)
    if cap <= 0:
        return
    row = await db.promo_daily.find_one({"promo_id": promo_id, "date": _today()})
    if row and int(row.get("spend_cents", 0)) >= cap and promo.get("active"):
        await db.promoted_stations.update_one(
            {"promo_id": promo_id},
            {"$set": {"active": False, "status": "budget_capped", "updated_at": _now()}})


async def _bump_daily_counter(db, promo_id: str, field: str) -> None:
    await db.promo_daily.update_one(
        {"promo_id": promo_id, "date": _today()},
        {"$inc": {field: 1}, "$setOnInsert": {"created_at": _now()}}, upsert=True)


class PromoCreateBody(BaseModel):
    station_id:      str
    sponsor_name:    Optional[str] = None
    pricing_model:   str = "cpm"            # "cpm" | "cpc"
    cpm_bid_cents:   Optional[int] = 500    # $5 CPM default
    cpc_bid_cents:   Optional[int] = 25     # $0.25 CPC default
    active:          bool = True


async def _resolve_card(db, station_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a promo's station_id to a unified card across all sources."""
    sid = str(station_id or "")
    # Imported live station (Radio Browser tier).
    s = await db.imported_radio_stations.find_one({"id": sid})
    if s:
        return _imported_to_card(s)
    # Community / creator station.
    if sid.startswith("cmn_"):
        c = await db.community_radio_stations.find_one(
            {"station_id": sid.replace("cmn_", "")}) \
            or await db.community_radio_stations.find_one({"station_id": sid})
        if c:
            return _community_to_card(c)
    # RadioLife AI channel (matched by slug).
    ch = await db.channels.find_one({"slug": sid}) \
        or await db.channels.find_one({"slug": sid.replace("ai_", "")})
    if ch:
        return _ai_channel_to_card(ch, None)
    return None


async def ensure_promoted_seed(db) -> int:
    """Ensure the Sponsored rail has promos for SEVERAL DISTINCT stations so
    rotation shows real variety.  Idempotent — only tops up distinct
    stations, never duplicates one that's already promoted."""
    TARGET = 5
    existing_sids = set()
    async for p in db.promoted_stations.find({}, {"station_id": 1}):
        existing_sids.add(str(p.get("station_id")))
    if len(existing_sids) >= TARGET:
        return 0

    # Candidate distinct stations: flagship first, then top-voted active.
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    async def _add(s):
        sid = str(s.get("id"))
        if sid and sid not in seen_ids:
            seen_ids.add(sid)
            candidates.append(s)

    async for s in db.imported_radio_stations.find({"is_flagship": True}).limit(8):
        await _add(s)
    async for s in db.imported_radio_stations.find(
            {"active": True}).sort([("votes", -1)]).limit(20):
        await _add(s)
        if len(candidates) >= TARGET + 3:
            break

    created = 0
    for i, s in enumerate(candidates):
        if len(existing_sids) >= TARGET:
            break
        sid = str(s.get("id"))
        if sid in existing_sids:
            continue
        doc = {
            "promo_id":      f"promo_{uuid.uuid4().hex[:12]}",
            "station_id":    s.get("id"),
            "sponsor_name":  s.get("name") or "Sponsored Station",
            "pricing_model": "cpm" if i % 2 == 0 else "cpc",
            "cpm_bid_cents": 500 - i * 20,
            "cpc_bid_cents": 25,
            "active":        True,
            "impressions":   0,
            "clicks":        0,
            "spend_cents":   0,
            "created_at":    _now(),
            "updated_at":    _now(),
        }
        await db.promoted_stations.insert_one(doc)
        existing_sids.add(sid)
        created += 1
    return created


@router.get("/stations")
async def list_promoted_stations(
    request: Request,
    limit: int = Query(6, ge=1, le=20),
    user: Optional[dict] = Depends(current_user_optional),
):
    """Active promoted stations as unified cards, ranked by bid.  Each card
    carries `is_sponsored`, `promo_id`, `pricing_model` and `sponsor_name`."""
    db = request.app.state.db
    await ensure_promoted_seed(db)
    await _resume_capped_promos(db)
    out: List[Dict[str, Any]] = []
    seen_station: set = set()
    cur = db.promoted_stations.find({"active": True}).sort(
        [("cpm_bid_cents", -1), ("cpc_bid_cents", -1)]).limit(limit * 4)
    async for p in cur:
        card = await _resolve_card(db, p.get("station_id"))
        if not card:
            continue
        # De-dupe by station so the rotation cycles distinct advertisers.
        key = str(card.get("id") or card.get("station_id") or p.get("station_id"))
        if key in seen_station:
            continue
        seen_station.add(key)
        card = {**card}
        card["is_sponsored"] = True
        card["promo_id"] = p.get("promo_id")
        card["pricing_model"] = p.get("pricing_model") or "cpm"
        card["sponsor_name"] = p.get("sponsor_name") or card.get("name")
        card["bid_cents"] = (int(p.get("cpm_bid_cents") or 0)
                                                  or int((p.get("cpc_bid_cents") or 0) * 20) or 100)
        out.append(card)
        if len(out) >= limit:
            break
    return {"items": out, "total": len(out)}


async def _uid(user: dict) -> str:
    return user.get("user_id") or str(user.get("_id"))


async def _get_wallet(db, advertiser_id: str) -> Dict[str, Any]:
    w = await db.promo_wallets.find_one({"advertiser_id": advertiser_id})
    if not w:
        w = {"advertiser_id": advertiser_id, "balance_cents": 0,
             "created_at": _now(), "updated_at": _now()}
        await db.promo_wallets.insert_one(dict(w))
    w.pop("_id", None)
    return w


async def _charge_and_maybe_pause(db, promo: Dict[str, Any], cents: int) -> None:
    """Deduct `cents` from the owning advertiser's wallet; pause the promo
    when the balance is exhausted.  House promos (no advertiser) are free."""
    advertiser_id = promo.get("advertiser_id")
    if not advertiser_id or cents <= 0:
        return
    w = await _get_wallet(db, advertiser_id)
    new_balance = int(w.get("balance_cents", 0)) - cents
    updates: Dict[str, Any] = {"balance_cents": new_balance, "updated_at": _now()}
    await db.promo_wallets.update_one({"advertiser_id": advertiser_id}, {"$set": updates})
    if new_balance <= 0:
        await db.promoted_stations.update_one(
            {"promo_id": promo.get("promo_id")},
            {"$set": {"active": False, "status": "depleted", "updated_at": _now()}})


@router.post("/{promo_id}/impression")
async def track_impression(promo_id: str, request: Request):
    """CPM accrual — one view (also debits the advertiser wallet)."""
    db = request.app.state.db
    p = await db.promoted_stations.find_one({"promo_id": promo_id})
    if not p:
        raise HTTPException(404, "promo not found")
    accrue = 0
    if (p.get("pricing_model") or "cpm") == "cpm":
        accrue = max(0, int(p.get("cpm_bid_cents") or 0)) // 1000
    await db.promoted_stations.update_one(
        {"promo_id": promo_id},
        {"$inc": {"impressions": 1, "spend_cents": accrue},
         "$set": {"updated_at": _now()}})
    await _bump_daily_counter(db, promo_id, "impressions")
    await _charge_and_maybe_pause(db, p, accrue)
    await _record_daily_and_cap(db, p, accrue)
    return {"ok": True, "promo_id": promo_id, "accrued_cents": accrue}


@router.post("/{promo_id}/click")
async def track_click(promo_id: str, request: Request):
    """CPC accrual — one click (also debits the advertiser wallet)."""
    db = request.app.state.db
    p = await db.promoted_stations.find_one({"promo_id": promo_id})
    if not p:
        raise HTTPException(404, "promo not found")
    accrue = 0
    if (p.get("pricing_model") or "cpm") == "cpc":
        accrue = max(0, int(p.get("cpc_bid_cents") or 0))
    await db.promoted_stations.update_one(
        {"promo_id": promo_id},
        {"$inc": {"clicks": 1, "spend_cents": accrue},
         "$set": {"updated_at": _now()}})
    await _bump_daily_counter(db, promo_id, "clicks")
    await _charge_and_maybe_pause(db, p, accrue)
    await _record_daily_and_cap(db, p, accrue)
    return {"ok": True, "promo_id": promo_id, "accrued_cents": accrue}


@router.post("")
async def create_promo(body: PromoCreateBody, request: Request,
                       _admin=Depends(require_admin)):
    db = request.app.state.db
    card = await _resolve_card(db, body.station_id)
    if not card:
        raise HTTPException(400, "station_id does not resolve to a station")
    doc = {
        "promo_id":      f"promo_{uuid.uuid4().hex[:12]}",
        "station_id":    body.station_id,
        "sponsor_name":  body.sponsor_name or card.get("name"),
        "pricing_model": body.pricing_model if body.pricing_model in ("cpm", "cpc") else "cpm",
        "cpm_bid_cents": int(body.cpm_bid_cents or 0),
        "cpc_bid_cents": int(body.cpc_bid_cents or 0),
        "active":        bool(body.active),
        "impressions":   0,
        "clicks":        0,
        "spend_cents":   0,
        "created_at":    _now(),
        "updated_at":    _now(),
    }
    await db.promoted_stations.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/admin")
async def admin_list_promos(request: Request, _admin=Depends(require_admin)):
    db = request.app.state.db
    out: List[Dict[str, Any]] = []
    async for p in db.promoted_stations.find({}).sort("created_at", -1):
        p.pop("_id", None)
        out.append(p)
    return {"items": out, "total": len(out)}


# ─────────────────────────── Advertiser self-serve ───────────────────────────

class SelfServeBody(BaseModel):
    station_id:    str
    sponsor_name:  Optional[str] = None
    pricing_model: str = "cpm"              # "cpm" | "cpc"
    cpm_bid_cents: Optional[int] = 500
    cpc_bid_cents: Optional[int] = 25
    daily_budget_cents: Optional[int] = 0   # 0 = no daily cap


def _promo_stats(p: Dict[str, Any]) -> Dict[str, Any]:
    imp = int(p.get("impressions") or 0)
    clk = int(p.get("clicks") or 0)
    ctr = round((clk / imp) * 100, 2) if imp else 0.0
    return {
        "promo_id":      p.get("promo_id"),
        "station_id":    p.get("station_id"),
        "sponsor_name":  p.get("sponsor_name"),
        "pricing_model": p.get("pricing_model") or "cpm",
        "cpm_bid_cents": int(p.get("cpm_bid_cents") or 0),
        "cpc_bid_cents": int(p.get("cpc_bid_cents") or 0),
        "daily_budget_cents": int(p.get("daily_budget_cents") or 0),
        "active":        bool(p.get("active")),
        "status":        p.get("status") or ("active" if p.get("active") else "paused"),
        "impressions":   imp,
        "clicks":        clk,
        "ctr":           ctr,
        "spend_cents":   int(p.get("spend_cents") or 0),
        "created_at":    p.get("created_at"),
    }


@router.get("/wallet")
async def get_wallet(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = await _uid(user)
    w = await _get_wallet(db, uid)
    n_active = await db.promoted_stations.count_documents(
        {"advertiser_id": uid, "active": True})
    return {"advertiser_id": uid, "balance_cents": int(w.get("balance_cents", 0)),
            "active_promos": n_active,
            "packages": [{"id": k, "amount_cents": v} for k, v in _TOPUP_PACKAGES.items()]}


class DemoTopupBody(BaseModel):
    amount_cents: int = 1000


@router.post("/wallet/topup-demo",
                          description="Instant demo wallet credit (no Stripe) so boosted bids "
                                                  "can spend. Reactivates the caller's paused promos once funded.")
async def wallet_topup_demo(body: DemoTopupBody, request: Request,
                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = await _uid(user)
    amt = max(100, min(int(body.amount_cents or 0), 500000))
    w = await _get_wallet(db, uid)
    new_balance = int(w.get("balance_cents", 0)) + amt
    await db.promo_wallets.update_one(
        {"advertiser_id": uid},
        {"$set": {"balance_cents": new_balance, "updated_at": _now()}})
    await db.promoted_stations.update_many(
        {"advertiser_id": uid, "active": False,
          "status": {"$in": ["depleted", "awaiting_funds", "paused", "budget_capped"]}},
        {"$set": {"active": True, "status": "active", "updated_at": _now()}})
    return {"ok": True, "balance_cents": new_balance, "credited_cents": amt}


@router.post("/self-serve")
async def create_self_serve_promo(body: SelfServeBody, request: Request,
                                  user: dict = Depends(current_user)):
    """A logged-in station owner promotes a station.  It auto-activates only
    when the wallet has balance; otherwise it's created paused."""
    db = request.app.state.db
    uid = await _uid(user)
    card = await _resolve_card(db, body.station_id)
    if not card:
        raise HTTPException(400, "station_id does not resolve to a station")
    w = await _get_wallet(db, uid)
    funded = int(w.get("balance_cents", 0)) > 0
    doc = {
        "promo_id":      f"promo_{uuid.uuid4().hex[:12]}",
        "advertiser_id": uid,
        "station_id":    body.station_id,
        "sponsor_name":  body.sponsor_name or card.get("name"),
        "pricing_model": body.pricing_model if body.pricing_model in ("cpm", "cpc") else "cpm",
        "cpm_bid_cents": int(body.cpm_bid_cents or 0),
        "cpc_bid_cents": int(body.cpc_bid_cents or 0),
        "daily_budget_cents": int(body.daily_budget_cents or 0),
        "active":        funded,
        "status":        "active" if funded else "awaiting_funds",
        "impressions":   0, "clicks": 0, "spend_cents": 0,
        "created_at":    _now(), "updated_at": _now(),
    }
    await db.promoted_stations.insert_one(doc)
    doc.pop("_id", None)
    return {"promo": _promo_stats(doc), "wallet_balance_cents": int(w.get("balance_cents", 0))}


@router.get("/mine")
async def my_promos(request: Request, user: dict = Depends(current_user)):
    """Sponsor analytics — the caller's promos with impressions/clicks/CTR/spend."""
    db = request.app.state.db
    uid = await _uid(user)
    promos: List[Dict[str, Any]] = []
    tot_imp = tot_clk = tot_spend = 0
    async for p in db.promoted_stations.find({"advertiser_id": uid}).sort("created_at", -1):
        st = _promo_stats(p)
        card = await _resolve_card(db, p.get("station_id"))
        st["station_name"] = (card or {}).get("name") or p.get("sponsor_name")
        st["logo_url"] = (card or {}).get("logo_url") or (card or {}).get("favicon")
        promos.append(st)
        tot_imp += st["impressions"]; tot_clk += st["clicks"]; tot_spend += st["spend_cents"]
    w = await _get_wallet(db, uid)
    return {
        "items": promos, "total": len(promos),
        "wallet_balance_cents": int(w.get("balance_cents", 0)),
        "totals": {
            "impressions": tot_imp, "clicks": tot_clk,
            "ctr": round((tot_clk / tot_imp) * 100, 2) if tot_imp else 0.0,
            "spend_cents": tot_spend,
        },
    }


@router.post("/{promo_id}/toggle")
async def toggle_promo(promo_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = await _uid(user)
    p = await db.promoted_stations.find_one({"promo_id": promo_id, "advertiser_id": uid})
    if not p:
        raise HTTPException(404, "promo not found")
    new_active = not bool(p.get("active"))
    w = await _get_wallet(db, uid)
    if new_active and int(w.get("balance_cents", 0)) <= 0:
        raise HTTPException(400, "wallet balance is empty — top up to activate")
    await db.promoted_stations.update_one(
        {"promo_id": promo_id},
        {"$set": {"active": new_active,
                  "status": "active" if new_active else "paused",
                  "updated_at": _now()}})
    return {"ok": True, "promo_id": promo_id, "active": new_active}


class BidBody(BaseModel):
    cpm_bid_cents: int


@router.post("/{promo_id}/bid",
                          description="Raise a sponsor's bid to win more home-rotation slots. "
                                                  "Higher bid = more airtime. Any logged-in user can boost a "
                                                  "demo sponsor; a real promo is scoped to its owner.")
async def set_promo_bid(promo_id: str, body: BidBody, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = await _uid(user)
    p = await db.promoted_stations.find_one({"promo_id": promo_id})
    if not p:
        raise HTTPException(404, "promo not found")
    owner = p.get("advertiser_id")
    if owner and owner != uid:
        raise HTTPException(403, "not_your_promo")
    bid = max(100, min(int(body.cpm_bid_cents or 0), 100000))
    patch = {"cpm_bid_cents": bid, "pricing_model": "cpm", "updated_at": _now()}
    if not owner:
        patch["advertiser_id"] = uid          # claim the demo slot on first boost
    await db.promoted_stations.update_one({"promo_id": promo_id}, {"$set": patch})
    return {"ok": True, "promo_id": promo_id, "cpm_bid_cents": bid}


async def _resume_capped_promos(db) -> None:
    """New-day sweep: reactivate promos that were auto-paused by their daily
    budget once the current day's spend is back under the cap and the wallet
    still has balance."""
    async for p in db.promoted_stations.find({"status": "budget_capped"}):
        cap = int(p.get("daily_budget_cents") or 0)
        row = await db.promo_daily.find_one({"promo_id": p.get("promo_id"), "date": _today()})
        spent_today = int((row or {}).get("spend_cents", 0))
        if cap > 0 and spent_today >= cap:
            continue
        if p.get("advertiser_id"):
            w = await db.promo_wallets.find_one({"advertiser_id": p.get("advertiser_id")})
            if int((w or {}).get("balance_cents", 0)) <= 0:
                continue
        await db.promoted_stations.update_one(
            {"promo_id": p.get("promo_id")},
            {"$set": {"active": True, "status": "active", "updated_at": _now()}})


@router.get("/leaderboard")
async def promoted_leaderboard(request: Request,
                               days: int = Query(7, ge=1, le=30),
                               limit: int = Query(10, ge=1, le=50)):
    """Ranks promoted stations by listens (clicks) over the last `days`, to
    nudge sponsors toward higher bids."""
    from datetime import timedelta
    db = request.app.state.db
    await _resume_capped_promos(db)
    since = (_now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    agg = db.promo_daily.aggregate([
        {"$match": {"date": {"$gte": since}}},
        {"$group": {"_id": "$promo_id",
                    "listens": {"$sum": {"$ifNull": ["$clicks", 0]}},
                    "impressions": {"$sum": {"$ifNull": ["$impressions", 0]}}}},
        {"$sort": {"listens": -1, "impressions": -1}},
        {"$limit": limit},
    ])
    out: List[Dict[str, Any]] = []
    async for row in agg:
        promo = await db.promoted_stations.find_one({"promo_id": row["_id"]})
        if not promo:
            continue
        card = await _resolve_card(db, promo.get("station_id"))
        out.append({
            "promo_id": row["_id"],
            "station_id": promo.get("station_id"),
            "station_name": (card or {}).get("name") or promo.get("sponsor_name"),
            "logo_url": (card or {}).get("logo_url") or (card or {}).get("favicon"),
            "listens": int(row.get("listens", 0)),
            "impressions": int(row.get("impressions", 0)),
            "pricing_model": promo.get("pricing_model") or "cpm",
        })
    return {"items": out, "total": len(out), "window_days": days}


# ─────────────────────────── Stripe wallet top-up ───────────────────────────

class TopupBody(BaseModel):
    package_id: str
    origin_url: str


@router.post("/wallet/topup")
async def wallet_topup(body: TopupBody, request: Request,
                       user: dict = Depends(current_user)):
    if body.package_id not in _TOPUP_PACKAGES:
        raise HTTPException(400, "unknown package")
    amount_cents = _TOPUP_PACKAGES[body.package_id]
    db = request.app.state.db
    uid = await _uid(user)
    if not stripe.api_key:
        raise HTTPException(503, "payments not configured")
    origin = body.origin_url.rstrip("/")
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"RadioLife Ad Wallet top-up (${amount_cents/100:.0f})"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "promo_topup", "advertiser_id": uid,
                  "package_id": body.package_id, "amount_cents": str(amount_cents)},
    )
    await db.promo_topups.insert_one({
        "session_id": session.id, "advertiser_id": uid,
        "amount_cents": amount_cents, "status": "initiated",
        "payment_status": "pending", "credited": False,
        "created_at": _now(), "updated_at": _now(),
    })
    return {"checkout_url": session.url, "session_id": session.id}


@router.get("/wallet/topup/status/{session_id}")
async def wallet_topup_status(session_id: str, request: Request):
    db = request.app.state.db
    rec = await db.promo_topups.find_one({"session_id": session_id})
    if not rec:
        raise HTTPException(404, "top-up not found")
    if rec.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                # Idempotent credit: only credit once.
                res = await db.promo_topups.update_one(
                    {"session_id": session_id, "credited": {"$ne": True}},
                    {"$set": {"status": "completed", "payment_status": "paid",
                              "credited": True, "updated_at": _now()}})
                if res.modified_count == 1:
                    await db.promo_wallets.update_one(
                        {"advertiser_id": rec["advertiser_id"]},
                        {"$inc": {"balance_cents": int(rec["amount_cents"])},
                         "$set": {"updated_at": _now()}}, upsert=True)
                    # Re-activate any awaiting-funds promos.
                    await db.promoted_stations.update_many(
                        {"advertiser_id": rec["advertiser_id"], "status": "awaiting_funds"},
                        {"$set": {"active": True, "status": "active", "updated_at": _now()}})
                rec = await db.promo_topups.find_one({"session_id": session_id})
        except stripe.error.StripeError:
            pass
    w = await db.promo_wallets.find_one({"advertiser_id": rec["advertiser_id"]}) or {}
    return {"session_id": session_id, "status": rec.get("status"),
            "payment_status": rec.get("payment_status"),
            "balance_cents": int(w.get("balance_cents", 0))}
