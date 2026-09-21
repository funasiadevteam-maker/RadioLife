"""Instant single-player games — Wheel of Fortune (spin-to-win).

Rich, instant, solo play so there's never a "waiting for players"
dead-end.  Prizes are FUUSIC points (via PointsService) or a sponsor
coupon (via local_commerce.claim_offer).  Sponsors attach a logo + a
coupon prize; a looping BGM track is streamed from object storage.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services.object_storage import get_storage
from services.points_service import PointsService

router = APIRouter(prefix="/api/games", tags=["instant_games"])

BGM_KEY = "games/bgm/wheel_loop.mp3"          # shared looping track
DEFAULT_DAILY_SPINS = 3

# Default "house" wheel — always available, points-only.
_HOUSE_SEGMENTS = [
    {"label": "50 pts",    "kind": "points", "value": 50,   "weight": 24, "color": "#a855f7"},
    {"label": "100 pts",   "kind": "points", "value": 100,  "weight": 20, "color": "#ec4899"},
    {"label": "Try again", "kind": "none",   "value": 0,    "weight": 16, "color": "#334155"},
    {"label": "250 pts",   "kind": "points", "value": 250,  "weight": 14, "color": "#f59e0b"},
    {"label": "500 pts",   "kind": "points", "value": 500,  "weight": 10, "color": "#22d3ee"},
    {"label": "Try again", "kind": "none",   "value": 0,    "weight": 8,  "color": "#475569"},
    {"label": "1000 pts",  "kind": "points", "value": 1000, "weight": 5,  "color": "#10b981"},
    {"label": "JACKPOT",   "kind": "points", "value": 5000, "weight": 3,  "color": "#fbbf24"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or request.url.netloc)
    return f"{proto}://{host}"


async def seed_instant_games(db) -> None:
    await db.branded_games.create_index([("active", 1)], name="bg_active")
    await db.wheel_spins.create_index(
        [("user_id", 1), ("game_id", 1), ("day", 1)], name="ws_user_game_day")
    if not await db.branded_games.find_one({"_id": "wheel_house"}):
        await db.branded_games.insert_one({
            "_id": "wheel_house", "game_type": "wheel",
            "sponsor_name": "FUUSIC", "logo_url": None, "bgm_key": BGM_KEY,
            "segments": _HOUSE_SEGMENTS, "daily_spins": DEFAULT_DAILY_SPINS,
            "active": True, "created_at": _now()})
    if not await db.branded_games.find_one({"_id": "wheel_demo_sponsor"}):
        segs = [dict(s) for s in _HOUSE_SEGMENTS]
        segs[6] = {"label": "FREE KARAK", "kind": "coupon",
                   "coupon_offer_id": "ofr_qa_onetime_demo",
                   "weight": 5, "color": "#ef4444"}
        await db.branded_games.insert_one({
            "_id": "wheel_demo_sponsor", "game_type": "wheel",
            "sponsor_name": "Karak House", "logo_url": None, "bgm_key": BGM_KEY,
            "segments": segs, "daily_spins": DEFAULT_DAILY_SPINS,
            "active": True, "created_at": _now()})


def _public_segments(game: dict) -> list[dict]:
    return [{"label": s["label"], "color": s.get("color", "#334155"),
             "kind": s.get("kind", "none")} for s in (game.get("segments") or [])]


async def _spins_left(db, user_id: str, game: dict) -> int:
    used = await db.wheel_spins.count_documents(
        {"user_id": user_id, "game_id": game["_id"], "day": _today()})
    return max(0, int(game.get("daily_spins") or DEFAULT_DAILY_SPINS) - used)


def _bgm_url(request: Request, game: dict) -> Optional[str]:
    return f"{_base_url(request)}/api/games/bgm/wheel" if game.get("bgm_key") else None


def _config_payload(request: Request, game: dict, spins_left: int) -> dict:
    return {"game_id": game["_id"], "game_type": game.get("game_type", "wheel"),
            "sponsor_name": game.get("sponsor_name"),
            "logo_url": game.get("logo_url"),
            "bgm_url": _bgm_url(request, game),
            "daily_spins": int(game.get("daily_spins") or DEFAULT_DAILY_SPINS),
            "spins_left": spins_left, "segments": _public_segments(game)}


async def _ensure_seeded(db) -> None:
    if not await db.branded_games.find_one({}):
        await seed_instant_games(db)


async def _load_game(db, game_id: Optional[str]) -> dict:
    await _ensure_seeded(db)
    gid = game_id or "wheel_house"
    game = await db.branded_games.find_one({"_id": gid, "active": True})
    if not game:
        game = await db.branded_games.find_one({"_id": "wheel_house"})
    if not game:
        raise HTTPException(503, {"code": "no_wheel_configured"})
    return game


@router.get("/wheel/list")
async def list_wheels(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _ensure_seeded(db)
    out = []
    async for g in db.branded_games.find({"game_type": "wheel", "active": True}):
        out.append({"game_id": g["_id"], "sponsor_name": g.get("sponsor_name"),
                    "logo_url": g.get("logo_url")})
    return {"items": out}


@router.get("/wheel/config")
async def wheel_config(request: Request, game_id: Optional[str] = None,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    game = await _load_game(db, game_id)
    left = await _spins_left(db, user["user_id"], game)
    return _config_payload(request, game, left)


class SpinBody(BaseModel):
    game_id: Optional[str] = None


async def _award_segment(db, user_id: str, game: dict, seg: dict,
                         spin_id: str) -> dict:
    kind = seg.get("kind")
    if kind == "points" and int(seg.get("value") or 0) > 0:
        svc = PointsService(db)
        await svc.award(user_id=user_id, source="wheel_prize",
                        delta=int(seg["value"]), source_id=game["_id"],
                        idempotency_key=f"wheel:{spin_id}",
                        metadata={"label": seg["label"], "game_id": game["_id"]},
                        enforce_caps=False)
        return {"kind": "points", "label": seg["label"], "points": int(seg["value"])}
    if kind == "coupon" and seg.get("coupon_offer_id"):
        try:
            from services.local_commerce import claim_offer
            coupon = await claim_offer(
                db, offer_id=seg["coupon_offer_id"], user_id=user_id,
                claim_source="game_prize_redemption",
                claim_context={"game_id": game["_id"], "spin_id": spin_id})
            return {"kind": "coupon", "label": seg["label"],
                    "coupon_id": coupon.get("coupon_id"),
                    "sponsor": game.get("sponsor_name")}
        except Exception:
            svc = PointsService(db)   # never a dud win
            await svc.award(user_id=user_id, source="wheel_prize", delta=200,
                            source_id=game["_id"],
                            idempotency_key=f"wheel:{spin_id}", enforce_caps=False)
            return {"kind": "points", "label": "200 pts", "points": 200}
    return {"kind": "none", "label": seg.get("label", "Try again"), "points": 0}


@router.post("/wheel/spin")
async def wheel_spin(request: Request, body: SpinBody = Body(default=SpinBody()),
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    game = await _load_game(db, body.game_id)
    if await _spins_left(db, uid, game) <= 0:
        raise HTTPException(429, {"code": "no_spins_left",
                                  "message": "You’re out of spins for today."})
    segments = game.get("segments") or []
    weights = [max(0, int(s.get("weight") or 0)) for s in segments]
    if not segments or sum(weights) <= 0:
        raise HTTPException(503, {"code": "wheel_misconfigured"})
    idx = random.choices(range(len(segments)), weights=weights, k=1)[0]
    seg = segments[idx]
    spin_id = uuid.uuid4().hex[:16]
    prize = await _award_segment(db, uid, game, seg, spin_id)
    await db.wheel_spins.insert_one(
        {"_id": f"ws_{spin_id}", "user_id": uid, "game_id": game["_id"],
         "day": _today(), "segment_index": idx, "prize": prize,
         "created_at": _now()})
    left = await _spins_left(db, uid, game)
    bal = await PointsService(db).get_balance(uid)
    return {"segment_index": idx, "prize": prize, "spins_left": left,
            "balance": bal}


@router.get("/bgm/wheel")
async def wheel_bgm(request: Request):
    """Public streaming loop for the wheel BGM (no auth so <audio> can load)."""
    st = get_storage()
    head = st.head(key=BGM_KEY)
    if not head:
        raise HTTPException(404, {"code": "bgm_missing"})
    size = int(head.get("size") or 0)
    data = st.open_range(key=BGM_KEY, start=0, end=max(0, size - 1))
    return Response(content=data, media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=86400",
                             "Accept-Ranges": "bytes"})


# ─────────────────────── Admin / sponsor config ────────────────────
class SegmentIn(BaseModel):
    label: str
    kind: str = "points"                   # points | coupon | none
    value: int = 0
    weight: int = 1
    color: str = "#334155"
    coupon_offer_id: Optional[str] = None


class BrandedGameIn(BaseModel):
    game_id: Optional[str] = None
    game_type: str = "wheel"
    sponsor_name: str = Field(..., max_length=60)
    logo_url: Optional[str] = None
    sponsor_business_id: Optional[str] = None
    daily_spins: int = DEFAULT_DAILY_SPINS
    segments: list[SegmentIn] = Field(default_factory=list)
    active: bool = True


@router.post("/admin/branded-games")
async def admin_upsert_branded_game(body: BrandedGameIn, request: Request,
                                    _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    gid = body.game_id or f"wheel_{uuid.uuid4().hex[:10]}"
    segs = [s.model_dump() for s in body.segments] or _HOUSE_SEGMENTS
    doc = {"_id": gid, "game_type": body.game_type,
           "sponsor_name": body.sponsor_name, "logo_url": body.logo_url,
           "sponsor_business_id": body.sponsor_business_id,
           "bgm_key": BGM_KEY, "segments": segs,
           "daily_spins": int(body.daily_spins), "active": body.active,
           "created_at": _now()}
    await db.branded_games.update_one({"_id": gid}, {"$set": doc}, upsert=True)
    return {"game_id": gid, "ok": True}


@router.get("/admin/branded-games")
async def admin_list_branded_games(request: Request,
                                   _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    out = []
    async for g in db.branded_games.find({}):
        out.append({"game_id": g["_id"], "game_type": g.get("game_type"),
                    "sponsor_name": g.get("sponsor_name"),
                    "logo_url": g.get("logo_url"), "active": g.get("active"),
                    "daily_spins": g.get("daily_spins"),
                    "segments": g.get("segments")})
    return {"items": out}


__all__ = ["router", "seed_instant_games"]
