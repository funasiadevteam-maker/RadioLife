"""
wallet_routes.py — Save-to-Wallet + Wallet listing (FastAPI + MongoDB/Motor)

Backs the "Save to Wallet" action in WinReveal. The coupon was already issued
by record_winner() during /api/play/resolve; this pins it to the listener's
Wallet so it shows up under the Wallet nav.

Reuses the db connection and auth from play_routes.py.

ONE-TIME SETUP (run on startup):
  await db.wallet_items.create_index([("playId", 1), ("listenerId", 1)], unique=True)
  await db.wallet_items.create_index([("listenerId", 1), ("savedAt", -1)])
"""

import secrets
import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from play_routes import db, get_listener_id  # reuse the same client + auth

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


class SaveRequest(BaseModel):
    playId: str
    idempotencyKey: str = Field(..., min_length=8, max_length=64)


class WalletItemOut(BaseModel):
    walletItemId: str
    prizeTitle: str
    code: Optional[str] = None
    redeemUrl: Optional[str] = None
    savedAt: str
    status: str  # "active" | "redeemed" | "expired"


def _shape(doc: dict) -> WalletItemOut:
    return WalletItemOut(
        walletItemId=doc["walletItemId"], prizeTitle=doc["prizeTitle"],
        code=doc.get("code"), redeemUrl=doc.get("redeemUrl"),
        savedAt=doc["savedAt"], status=doc.get("status", "active"),
    )


@router.post("/save", response_model=WalletItemOut)
async def save_to_wallet(req: SaveRequest, listener_id: str = Depends(get_listener_id)):
    # idempotent: already saved -> return existing item
    existing = await db.wallet_items.find_one({"playId": req.playId, "listenerId": listener_id})
    if existing:
        return _shape(existing)

    play = await db.plays.find_one({"_id": req.playId, "listenerId": listener_id})
    if not play:
        raise HTTPException(404, "Play not found")
    if not play.get("won"):
        raise HTTPException(400, "No prize on this play")

    coupon = play.get("coupon") or {}
    item_id = secrets.token_hex(10)
    doc = {
        "_id": item_id, "walletItemId": item_id, "listenerId": listener_id,
        "playId": req.playId, "gameId": play.get("gameId"), "prizeId": play.get("prizeId"),
        "prizeTitle": play["prizeTitle"], "code": coupon.get("code"),
        "redeemUrl": coupon.get("redeemUrl"), "issuanceRef": coupon.get("issuanceRef"),
        "status": "active", "savedAt": datetime.datetime.utcnow().isoformat(),
        "idempotencyKey": req.idempotencyKey,
    }
    try:
        await db.wallet_items.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.wallet_items.find_one({"playId": req.playId, "listenerId": listener_id})
        return _shape(existing)
    return _shape(doc)


@router.get("/items", response_model=List[WalletItemOut])
async def list_wallet(listener_id: str = Depends(get_listener_id)):
    items = await db.wallet_items.find({"listenerId": listener_id}) \
        .sort("savedAt", -1).to_list(200)
    return [_shape(i) for i in items]
