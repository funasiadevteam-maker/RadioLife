"""Phase PG.1 — Play & Win + Scratch & Win game endpoints.

Legacy `routes/games.py` (Phase 5) is preserved untouched — it registers
`/api/games/state` (still powering the Wallet → Games tab) and the
Phase-5 mutation endpoints that return HTTP 410.  Since we use a
distinct set of paths (`/api/games/discover`, `/api/games/{campaign_id}`,
`/api/games/{campaign_id}/play`), no collision.

Merchant/admin (RBAC: can_create_links or admin):
    POST/GET/PUT   /api/merchant/{id}/game-campaigns[/{campaign_id}]
    POST                    /api/merchant/{id}/game-campaigns/{cid}/pause
    POST                    /api/merchant/{id}/game-campaigns/{cid}/end
    GET                      /api/merchant/{id}/game-campaigns/{cid}/analytics

Consumer (auth required):
    GET  /api/games/discover?merchant_id=
    GET  /api/games/{campaign_id}
    POST /api/games/{campaign_id}/play

Admin:
    GET /api/admin/games/campaigns
    GET /api/admin/games/winners
    GET /api/game-templates  (public)
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services.merchant_rbac_service import resolve_merchant_with_role
from services import game_service as _gs

logger = logging.getLogger("bigfm.pg1")
router = APIRouter(prefix="/api", tags=["pg1"])


def _iso(v):
    from datetime import datetime
    return v.isoformat() if isinstance(v, datetime) else v


def _campaign_view(c: dict, *, include_prizes: bool = True) -> dict:
    return {
        "campaign_id":                c.get("campaign_id"),
        "template_id":                c.get("template_id"),
        "game_type":                    c.get("game_type"),
        "merchant_id":                c.get("merchant_id"),
        "name":                              c.get("name"),
        "description":                c.get("description"),
        "active":                          c.get("active"),
        "start_at":                      _iso(c.get("start_at")),
        "end_at":                          _iso(c.get("end_at")),
        "max_plays_per_user":  c.get("max_plays_per_user"),
        "max_total_plays":      c.get("max_total_plays"),
        "current_plays_count": c.get("current_plays_count"),
        "prizes":                          c.get("prizes") if include_prizes else None,
        "terms":                            c.get("terms"),
        "hero_color":                  c.get("hero_color"),
        "created_at":                  _iso(c.get("created_at")),
        "updated_at":                  _iso(c.get("updated_at")),
    }


def _prize_public_view(p: dict) -> dict:
    """Public view — never leak weight or quantity_available to consumers."""
    return {
        "prize_id":                p.get("prize_id"),
        "prize_type":            p.get("prize_type"),
        "display_label":    p.get("display_label"),
        "display_color":    p.get("display_color"),
        "value_cents":        p.get("value_cents"),
        "points_amount":    p.get("points_amount"),
    }


# ─── Bodies ────────────────────────────────────────────────────
class PrizeIn(BaseModel):
    prize_id:                    Optional[str] = None
    prize_type:                str = Field(min_length=1)
    value_cents:              Optional[int] = 0
    sku_id:                        Optional[str] = None
    coupon_offer_id:      Optional[str] = None
    points_amount:          Optional[int] = 0
    badge_slug:                Optional[str] = None
    quantity_available: Optional[int] = 0
    weight:                        Optional[float] = 1.0
    display_label:          Optional[str] = "Prize"
    display_color:          Optional[str] = "#a855f7"


class CampaignCreate(BaseModel):
    template_id:                    str = Field(min_length=3)
    game_type:                        str = Field(min_length=1)
    name:                                str = Field(min_length=1, max_length=140)
    description:                  Optional[str] = None
    active:                          Optional[bool] = True
    start_at:                      Optional[str] = None
    end_at:                          Optional[str] = None
    max_plays_per_user:    Optional[int] = 1
    max_total_plays:          Optional[int] = None
    prizes:                          list[PrizeIn]
    terms:                            Optional[str] = None
    hero_color:                    Optional[str] = None


class CampaignPatch(BaseModel):
    name:                                Optional[str] = None
    description:                  Optional[str] = None
    active:                          Optional[bool] = None
    start_at:                      Optional[str] = None
    end_at:                          Optional[str] = None
    max_plays_per_user:    Optional[int] = None
    max_total_plays:          Optional[int] = None
    prizes:                          Optional[list[PrizeIn]] = None
    terms:                            Optional[str] = None
    hero_color:                    Optional[str] = None


class PlayBody(BaseModel):
    turnstile_token: Optional[str] = None


# ─── Templates (public) ────────────────────────────────────────
@router.get("/game-templates")
async def get_templates(request: Request):
    db = request.app.state.db
    rows = await _gs.list_templates(db)
    return {"items": [{
        "template_id":    t.get("template_id"),
        "game_type":        t.get("game_type"),
        "name":                  t.get("name"),
        "description":    t.get("description"),
        "default_config": t.get("default_config"),
    } for t in rows]}


# ─── Merchant campaign CRUD (RBAC: can_create_links) ──────────
@router.post("/merchant/{merchant_id}/game-campaigns")
async def merchant_create_campaign(merchant_id: str, body: CampaignCreate,
                                                                        request: Request,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_create_links")
    mid = biz.get("business_id") or str(biz.get("_id"))
    try:
        payload = body.model_dump(exclude_none=False)
        # Convert prize items from Pydantic to plain dicts
        doc = await _gs.create_campaign(
            db, merchant_id=mid, actor=user, **payload)
    except ValueError as ve:
        raise HTTPException(400, {"code": str(ve)})
    return _campaign_view(doc)


@router.get("/merchant/{merchant_id}/game-campaigns")
async def merchant_list_campaigns(merchant_id: str, request: Request,
                                                                      active: Optional[bool] = Query(None),
                                                                      limit: int = Query(100, ge=1, le=500),
                                                                      offset: int = Query(0, ge=0),
                                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_view_analytics")
    mid = biz.get("business_id") or str(biz.get("_id"))
    res = await _gs.list_campaigns(db, merchant_id=mid, active=active,
                                                                    limit=limit, offset=offset)
    return {**res, "items": [_campaign_view(c) for c in res["items"]]}


@router.get("/merchant/{merchant_id}/game-campaigns/{campaign_id}")
async def merchant_get_campaign(merchant_id: str, campaign_id: str,
                                                                request: Request,
                                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_view_analytics")
    mid = biz.get("business_id") or str(biz.get("_id"))
    c = await _gs.get_campaign(db, campaign_id=campaign_id)
    if not c or c.get("merchant_id") != mid:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return _campaign_view(c)


@router.put("/merchant/{merchant_id}/game-campaigns/{campaign_id}")
async def merchant_update_campaign(merchant_id: str, campaign_id: str,
                                                                        body: CampaignPatch, request: Request,
                                                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_create_links")
    mid = biz.get("business_id") or str(biz.get("_id"))
    try:
        c = await _gs.update_campaign(
            db, campaign_id=campaign_id, merchant_id=mid,
            patch=body.model_dump(exclude_unset=True), actor=user)
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return _campaign_view(c)


@router.post("/merchant/{merchant_id}/game-campaigns/{campaign_id}/pause")
async def merchant_pause(merchant_id: str, campaign_id: str, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_create_links")
    mid = biz.get("business_id") or str(biz.get("_id"))
    try:
        c = await _gs.update_campaign(
            db, campaign_id=campaign_id, merchant_id=mid,
            patch={"active": False}, actor=user)
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return _campaign_view(c)


@router.post("/merchant/{merchant_id}/game-campaigns/{campaign_id}/end")
async def merchant_end(merchant_id: str, campaign_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    from datetime import datetime, timezone
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_create_links")
    mid = biz.get("business_id") or str(biz.get("_id"))
    try:
        c = await _gs.update_campaign(
            db, campaign_id=campaign_id, merchant_id=mid,
            patch={"active": False,
                        "end_at": datetime.now(timezone.utc).isoformat()},
            actor=user)
    except ValueError as ve:
        raise HTTPException(404, {"code": str(ve)})
    return _campaign_view(c)


@router.get("/merchant/{merchant_id}/game-campaigns/{campaign_id}/analytics")
async def merchant_campaign_analytics(merchant_id: str, campaign_id: str,
                                                                              request: Request,
                                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    biz, _ = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user,
        permission="can_view_analytics")
    mid = biz.get("business_id") or str(biz.get("_id"))
    c = await _gs.get_campaign(db, campaign_id=campaign_id)
    if not c or c.get("merchant_id") != mid:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return await _gs.campaign_analytics(db, campaign_id=campaign_id)


# ─── Consumer ─────────────────────────────────────────────────
def _campaign_public_view(c: dict) -> dict:
    return {
        "campaign_id":  c.get("campaign_id"),
        "template_id":  c.get("template_id"),
        "game_type":    c.get("game_type"),
        "merchant_id":  c.get("merchant_id"),
        "name":                c.get("name"),
        "description":  c.get("description"),
        "hero_color":  c.get("hero_color"),
        "start_at":      _iso(c.get("start_at")),
        "end_at":          _iso(c.get("end_at")),
        "prizes":          [_prize_public_view(p) for p in (c.get("prizes") or [])],
    }


@router.get("/games/discover")
async def discover_games(request: Request,
                                                merchant_id: Optional[str] = Query(None),
                                                limit: int = Query(20, ge=1, le=50)):
    db = request.app.state.db
    rows = await _gs.discover(db, merchant_id=merchant_id, limit=limit)
    return {"items": [{
        **_campaign_public_view(r),
        "merchant_name": r.get("merchant_name"),
        "merchant_logo_url": r.get("merchant_logo_url"),
        "merchant_slug": r.get("merchant_slug"),
    } for r in rows]}


@router.get("/games/{campaign_id}")
async def game_meta(campaign_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await _gs.get_campaign(db, campaign_id=campaign_id)
    if not c:
        raise HTTPException(404, {"code": "campaign_not_found"})
    tpl = await db.game_templates.find_one({"template_id": c.get("template_id")})
    biz = None
    if c.get("merchant_id"):
        biz = await db.businesses.find_one(
            {"$or": [{"business_id": c["merchant_id"]},
                            {"_id": c["merchant_id"]}]},
            {"name": 1, "logo_url": 1, "slug": 1})
    eligibility = await _gs.can_user_play(db, campaign_id=campaign_id,
                                                                                      user_id=user["user_id"])
    # Phase AD.1 — enrich with sponsor branding when the merchant has
    # linked this game to an approved ad campaign of type sponsored_game.
    sponsored_by = None
    sp_ad_id = c.get("sponsored_by_ad_campaign_id")
    if sp_ad_id:
        ad_camp = await db.ad_campaigns_v2.find_one({
            "campaign_id": sp_ad_id, "status": {"$in": ["active", "paused"]}
        }, {"advertiser_id": 1, "creative": 1, "status": 1, "name": 1, "_id": 0})
        if ad_camp:
            adv = await db.advertisers_v2.find_one(
                {"advertiser_id": ad_camp.get("advertiser_id")},
                {"name": 1, "logo_url": 1, "_id": 0})
            cr = ad_camp.get("creative") or {}
            sponsored_by = {
                "ad_campaign_id":  sp_ad_id,
                "advertiser_id":  ad_camp.get("advertiser_id"),
                "advertiser_name": (adv or {}).get("name"),
                "advertiser_logo_url": (adv or {}).get("logo_url"),
                "headline":            cr.get("headline"),
                "body":                  cr.get("body"),
                "image_url":        cr.get("image_url"),
                "click_url":          cr.get("click_url"),
                "ad_status":         ad_camp.get("status"),
            }
    return {
        **_campaign_public_view(c),
        "template_config": (tpl or {}).get("default_config"),
        "merchant_name":    (biz or {}).get("name"),
        "merchant_logo_url": (biz or {}).get("logo_url"),
        "merchant_slug":    (biz or {}).get("slug"),
        "eligibility":        eligibility,
        "sponsored_by":  sponsored_by,
    }


@router.post("/games/{campaign_id}/play")
async def game_play(campaign_id: str, body: PlayBody, request: Request,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    client_ip = request.client.host if request.client else None
    ip_hash = hashlib.sha256((client_ip or "").encode()).hexdigest()[:16] if client_ip else None
    ua = (request.headers.get("user-agent") or "")[:200]
    try:
        result = await _gs.play(db, campaign_id=campaign_id, user=user,
                                                        client_ip_hash=ip_hash, ua=ua)
    except ValueError as ve:
        code = str(ve)
        status = 400
        if code in ("campaign_not_found",):    status = 404
        if code in ("max_plays_reached", "inactive", "sold_out",
                              "not_started", "ended"): status = 409
        raise HTTPException(status, {"code": code})

    prize = result["prize"]
    mint = result["mint"]
    return {
        "session_id":                result["session"]["session_id"],
        "outcome_prize_id":  prize["prize_id"],
        "outcome_type":        prize["prize_type"],
        "outcome_label":      prize.get("display_label"),
        "outcome_color":      prize.get("display_color"),
        "value_cents":          int(prize.get("value_cents") or 0),
        "points_amount":      int(prize.get("points_amount") or 0),
        "won":                          prize["prize_type"] != "nothing",
        "wallet_item_type":  mint.get("wallet_item_type"),
        "wallet_item_id":    mint.get("wallet_item_id"),
        "code":                        mint.get("code"),
        "mint_result":          mint,
    }


# ─── Admin ────────────────────────────────────────────────────
@router.get("/admin/games/campaigns")
async def admin_list_campaigns(request: Request,
                                                              active: Optional[bool] = Query(None),
                                                              merchant_id: Optional[str] = Query(None),
                                                              limit: int = Query(100, ge=1, le=500),
                                                              offset: int = Query(0, ge=0),
                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await _gs.list_campaigns(db, merchant_id=merchant_id, active=active,
                                                                    limit=limit, offset=offset)
    return {**res, "items": [_campaign_view(c) for c in res["items"]]}


@router.get("/admin/games/winners")
async def admin_list_winners(request: Request,
                                                        campaign_id: Optional[str] = Query(None),
                                                        limit: int = Query(100, ge=1, le=500),
                                                        offset: int = Query(0, ge=0),
                                                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    q = {}
    if campaign_id:
        q["campaign_id"] = campaign_id
    total = await db.game_winners.count_documents(q)
    rows = await db.game_winners.find(q).sort("awarded_at", -1) \
                                    .skip(offset).limit(limit).to_list(length=limit)
    return {"total": total, "limit": limit, "offset": offset,
                  "items": [{
                      "winner_id":              w.get("winner_id"),
                      "campaign_id":        w.get("campaign_id"),
                      "merchant_id":        w.get("merchant_id"),
                      "user_id":                w.get("user_id"),
                      "prize_id":              w.get("prize_id"),
                      "prize_type":          w.get("prize_type"),
                      "value_cents":        w.get("value_cents"),
                      "wallet_item_id":  w.get("wallet_item_id"),
                      "wallet_item_type": w.get("wallet_item_type"),
                      "awarded_at":        _iso(w.get("awarded_at")),
                      "redemption_status": w.get("redemption_status"),
                  } for w in rows]}


# ─── Win Wall (public) ────────────────────────────────────────
def _first_name(u: Optional[dict]) -> str:
    if not u:
        return "A RadioLife listener"
    for k in ("first_name", "firstName", "name", "display_name", "full_name"):
        v = (u.get(k) or "").strip()
        if v:
            return v.split()[0]
    email = (u.get("email") or "").strip()
    if email:
        return email.split("@")[0].split(".")[0].title() or "A RadioLife listener"
    return "A RadioLife listener"


@router.get("/games/winners/recent",
                        description="Public live feed of recent winners for a merchant "
                                                "(first name + prize only).")
async def recent_winners(request: Request,
                                                merchant_id: Optional[str] = Query(None),
                                                campaign_id: Optional[str] = Query(None),
                                                limit: int = Query(15, ge=1, le=50)):
    db = request.app.state.db
    q: dict = {"minted": True, "outcome_type": {"$ne": "nothing"}}
    if merchant_id:
        q["merchant_id"] = merchant_id
    if campaign_id:
        q["campaign_id"] = campaign_id
    rows = await db.game_sessions.find(q).sort("played_at", -1) \
                                    .limit(limit).to_list(length=limit)
    uids = list({r.get("user_id") for r in rows if r.get("user_id")})
    users: dict = {}
    if uids:
        async for u in db.users.find(
                {"user_id": {"$in": uids}},
                {"user_id": 1, "first_name": 1, "name": 1,
                  "display_name": 1, "email": 1}):
            users[u.get("user_id")] = u
    items = [{
        "first_name":    _first_name(users.get(r.get("user_id"))),
        "prize_label":  r.get("outcome_label") or "a prize",
        "prize_color":  r.get("outcome_color") or "#f59e0b",
        "prize_type":    r.get("outcome_type"),
        "played_at":      _iso(r.get("played_at")),
    } for r in rows]
    return {"items": items, "total": len(items)}


# ─── Game-coupon redeem (open shop counter screen) ────────────
async def _resolve_game_coupon(db, code: str):
    code = (code or "").strip().upper()
    if not code:
        return None
    return await db.coupons.find_one({"code": code})


async def _game_coupon_view(db, cp: dict) -> dict:
    offer = None
    if cp.get("offer_id"):
        offer = await db.offers.find_one(
            {"$or": [{"offer_id": cp["offer_id"]}, {"id": cp["offer_id"]}]})
    biz = None
    if cp.get("business_id"):
        biz = (await db.businesses.find_one({"business_id": cp["business_id"]})
                      or await db.businesses.find_one({"_id": cp["business_id"]}))
    return {
        "code":                    cp.get("code"),
        "status":                cp.get("status"),
        "prize_title":      (offer or {}).get("title") or "Game reward",
        "discount_percent": (offer or {}).get("discount_percent"),
        "business_id":      cp.get("business_id"),
        "business_name":  (biz or {}).get("name"),
        "source":                cp.get("source"),
        "expires_at":        _iso(cp.get("expires_at")),
        "redeemed_at":      _iso(cp.get("redeemed_at")),
    }


@router.get("/games/coupon/lookup",
                        description="Look up a game-won coupon by code (open shop screen).")
async def game_coupon_lookup(request: Request, code: str = Query(...)):
    db = request.app.state.db
    cp = await _resolve_game_coupon(db, code)
    if not cp:
        return {"found": False, "reason": "code_not_found"}
    return {"found": True, **(await _game_coupon_view(db, cp))}


class GameCouponRedeemBody(BaseModel):
    code: str


@router.post("/games/coupon/redeem",
                          description="Mark a game-won coupon redeemed (open shop screen). "
                                                  "Idempotent.")
async def game_coupon_redeem(body: GameCouponRedeemBody, request: Request):
    from datetime import datetime, timezone
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    cp = await _resolve_game_coupon(db, body.code)
    if not cp:
        raise HTTPException(404, {"code": "code_not_found"})
    if cp.get("status") == "redeemed" or cp.get("redeemed_at"):
        return {"ok": True, "idempotent": True,
                      **(await _game_coupon_view(db, cp))}
    exp = cp.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise HTTPException(409, {"code": "expired"})
    res = await db.coupons.update_one(
        {"_id": cp["_id"], "status": {"$ne": "redeemed"}},
        {"$set": {"status": "redeemed", "redeemed_at": now}})
    if res.modified_count == 0:
        raise HTTPException(409, {"code": "already_redeemed"})
    cp["status"] = "redeemed"
    cp["redeemed_at"] = now
    return {"ok": True, "idempotent": False,
                  **(await _game_coupon_view(db, cp))}



# ─── Bootstrap ─────────────────────────────────────────────────
async def ensure_pg1_indexes(db) -> None:
    await _gs.ensure_game_indexes(db)


__all__ = ["router", "ensure_pg1_indexes"]
