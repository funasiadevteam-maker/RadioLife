"""
play_routes.py — server-resolved Play & Win endpoint (Phase 23 Session 9).

A clean parallel surface that sits alongside the legacy games_v2 routes.
The new listener UI calls POST /api/play/resolve and gets back a flat
WinReveal-ready outcome:

    {playId, won, prizeId, prizeTitle, coupon, balance, playedAt}

Reuses the existing games_v2 weighted-prize lottery + atomic inventory
decrement so prize pools stay consistent across both systems.

ONE-TIME SETUP (run on startup):
  await db.plays.create_index(
      [("listenerId", 1), ("idempotencyKey", 1)], unique=True)
"""
import logging
import secrets
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from auth import current_user
from core.db import db  # re-exported for wallet_routes.py to import
from services.games_v2 import _atomic_claim_prize, _weighted_pick

logger = logging.getLogger("bigfm.play")

router = APIRouter(prefix="/api/play", tags=["play"])


async def get_listener_id(user: dict = Depends(current_user)) -> str:
    """Bridge — wallet_routes.py imports this verbatim. Resolves the
    current authenticated user's id from the cookie session."""
    return user["user_id"]


class ResolveRequest(BaseModel):
    gameId: str
    idempotencyKey: str = Field(..., min_length=8, max_length=64)


class CouponOut(BaseModel):
    code: str
    redeemUrl: str
    issuanceRef: Optional[str] = None


class ResolveResponse(BaseModel):
    playId: str
    won: bool
    prizeId: Optional[str] = None
    prizeTitle: Optional[str] = None
    coupon: Optional[CouponOut] = None
    balance: int
    playedAt: str


def _shape(row: dict) -> ResolveResponse:
    return ResolveResponse(
        playId=row["_id"],
        won=bool(row.get("won")),
        prizeId=row.get("prizeId"),
        prizeTitle=row.get("prizeTitle"),
        coupon=CouponOut(**row["coupon"]) if row.get("coupon") else None,
        balance=int(row.get("balance") or 0),
        playedAt=row["playedAt"],
    )


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_play(req: ResolveRequest,
                       user: dict = Depends(current_user)):
    listener_id = user["user_id"]

    # ---- idempotency replay: same key returns the original row. ----
    existing = await db.plays.find_one(
        {"listenerId": listener_id, "idempotencyKey": req.idempotencyKey})
    if existing:
        return _shape(existing)

    # ---- campaign lookup (gameId == campaign_id in our schema). ----
    campaign = await db.game_campaigns.find_one({"campaign_id": req.gameId})
    if not campaign:
        raise HTTPException(404, "Game not found")
    if campaign.get("status") != "active":
        raise HTTPException(
            404, f"Game not active: {campaign.get('status')}")

    play_id = "ply_" + secrets.token_hex(10)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    # ---- weighted prize lottery (reuses games_v2 helpers). ----
    rng = secrets.SystemRandom()
    prize_picked: Optional[dict] = None
    for _ in range(5):
        prizes = await db.game_prizes.find({
            "campaign_id": req.gameId,
            "active": True,
            "inventory_remaining": {"$gt": 0},
        }).to_list(50)
        if not prizes:
            break
        weights = [int(p["probability_weight"]) for p in prizes]
        idx = _weighted_pick(weights, rng)
        if idx < 0:
            break
        if await _atomic_claim_prize(db, prizes[idx], play_id):
            prize_picked = prizes[idx]
            break

    coupon = None
    prize_id = None
    prize_title = None
    if prize_picked:
        prize_id = prize_picked["prize_id"]
        prize_title = prize_picked["title"]
        code = "BIGFM-" + secrets.token_hex(4).upper()
        coupon = {
            "code": code,
            "redeemUrl": f"/redeem/{code}",
            "issuanceRef": f"internal:{play_id}",
        }

    # Snapshot listener BigCoin balance for the WinReveal HUD.
    u = await db.users.find_one(
        {"user_id": listener_id}, {"bigcoin_balance": 1}) or {}
    balance = int(u.get("bigcoin_balance") or 0)

    doc = {
        "_id": play_id,
        "playId": play_id,
        "listenerId": listener_id,
        "gameId": req.gameId,
        "campaignId": req.gameId,
        "won": bool(prize_picked),
        "prizeId": prize_id,
        "prizeTitle": prize_title,
        "coupon": coupon,
        "idempotencyKey": req.idempotencyKey,
        "playedAt": now_iso,
        "balance": balance,
    }
    try:
        await db.plays.insert_one(doc)
    except DuplicateKeyError:
        # Race: concurrent request inserted under the same key.
        existing = await db.plays.find_one({
            "listenerId": listener_id,
            "idempotencyKey": req.idempotencyKey,
        })
        if existing:
            return _shape(existing)
        raise HTTPException(409, "duplicate idempotency key")

    return _shape(doc)


# ---------------------------------------------------------------------
# Startup index hook — called from server.py on app bootstrap.  Safe to
# run repeatedly: create_index is idempotent on a matching spec.
# ---------------------------------------------------------------------
async def ensure_play_wallet_indexes() -> None:
    await db.plays.create_index(
        [("listenerId", 1), ("idempotencyKey", 1)],
        unique=True, name="plays_listener_idem_unique")
    await db.wallet_items.create_index(
        [("playId", 1), ("listenerId", 1)],
        unique=True, name="wallet_items_play_listener_unique")
    await db.wallet_items.create_index(
        [("listenerId", 1), ("savedAt", -1)],
        name="wallet_items_listener_recent")
    logger.info(
        "Phase 23 Session 9 indexes ready: plays.(listenerId,idempotencyKey), "
        "wallet_items.(playId,listenerId), wallet_items.(listenerId,savedAt)")
