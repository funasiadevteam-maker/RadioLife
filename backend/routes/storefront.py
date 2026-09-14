"""P1 — Consumer Storefront & Discovery.

A small, platform-agnostic surface (served to BOTH the web and mobile
clients) built on top of the existing games_v2 / FPK sponsored-coupon
engine.  Nothing here mutates state — it reads the live `game_campaigns`
/ `game_prizes` / wallet collections and shapes them for consumers,
admins, and the branded storefront landing page.

Endpoints
  GET  /api/store/{advertiser_id}            → branded storefront (brand + games + scarcity)
  GET  /api/store/{advertiser_id}/scarcity   → per-game "coupons left today" + reset countdown
  GET  /api/me/coupons                        → the signed-in user's owned coupons (unified)
  GET  /api/admin/fpk/coupon-caps            → admin: per-tier daily cap / issued / remaining
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user, require_admin

store_router = APIRouter(prefix="/api/store", tags=["storefront"])
me_coupons_router = APIRouter(prefix="/api/me", tags=["storefront"])
admin_caps_router = APIRouter(prefix="/api/admin/fpk", tags=["storefront-admin"])

FPK_ADVERTISER_ID = "adv_fpk"


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _next_utc_midnight_iso() -> str:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return tomorrow.isoformat()


def _issued_today(prize: dict, today: str) -> int:
    """Daily issuance is only meaningful when the counter's date is today;
    a stale date means the lazy rollover hasn't run, so effectively 0."""
    if prize.get("daily_issued_date") == today:
        return int(prize.get("daily_issued") or 0)
    return 0


def _scarcity_for_game(prizes: list[dict], today: str) -> dict:
    """Aggregate today's coupon scarcity across a game's coupon prizes.

    remaining_today is None when the game has an UNCAPPED coupon prize
    (effectively unlimited supply today); otherwise it's the sum of each
    capped tier's (cap - issued_today)."""
    coupon_prizes = [p for p in prizes
                     if p.get("prize_type") == "coupon" and p.get("active", True)]
    if not coupon_prizes:
        return {"is_coupon_game": False, "remaining_today": None,
                "total_cap_today": None, "issued_today": 0}
    has_uncapped = any(int(p.get("daily_quantity_cap") or 0) <= 0
                       for p in coupon_prizes)
    total_cap = 0
    issued = 0
    for p in coupon_prizes:
        cap = int(p.get("daily_quantity_cap") or 0)
        if cap > 0:
            total_cap += cap
            issued += _issued_today(p, today)
    remaining = None if has_uncapped else max(0, total_cap - issued)
    return {
        "is_coupon_game": True,
        "remaining_today": remaining,
        "total_cap_today": None if has_uncapped else total_cap,
        "issued_today": issued,
    }


async def _game_type_for(db, template_id: str) -> Optional[str]:
    tpl = await db.game_templates.find_one(
        {"template_id": template_id}, {"game_type": 1, "_id": 0})
    return (tpl or {}).get("game_type")


async def _resolve_brand(db, advertiser_id: str, sample_campaign: Optional[dict]) -> dict:
    """Brand identity for the storefront header — prefer the advertiser
    record, fall back to the campaign's sponsor fields."""
    adv = (await db.advertisers_v2.find_one({"advertiser_id": advertiser_id})
           or await db.advertisers.find_one({"advertiser_id": advertiser_id})
           or {})
    colors = (sample_campaign or {}).get("brand_colors_json") or {}
    return {
        "advertiser_id": advertiser_id,
        "name": (adv.get("name")
                 or (sample_campaign or {}).get("sponsor_name")
                 or advertiser_id),
        "logo_url": (adv.get("logo_url")
                     or (sample_campaign or {}).get("sponsor_logo_url")),
        "primary": colors.get("primary") or "#0aa54b",
        "secondary": colors.get("secondary") or "#0a0a0b",
        "tagline": (sample_campaign or {}).get("description")
                   or "Play to win exclusive discount coupons.",
    }


async def _load_store_games(db, advertiser_id: str) -> list[dict]:
    today = _today_str()
    games: list[dict] = []
    cur = db.game_campaigns.find(
        {"advertiser_id": advertiser_id, "status": "active"}
    ).sort("created_at", 1)
    async for c in cur:
        prizes = await db.game_prizes.find(
            {"campaign_id": c["campaign_id"], "active": True}).to_list(50)
        scarcity = _scarcity_for_game(prizes, today)
        games.append({
            "campaign_id": c["campaign_id"],
            "title": c.get("title"),
            "description": c.get("description"),
            "template_id": c.get("template_id"),
            "game_type": await _game_type_for(db, c.get("template_id")),
            "brand_colors": c.get("brand_colors_json") or {},
            "play_route": f"/play/{c['campaign_id']}",
            **scarcity,
        })
    return games


# ======================================================================
# Public — branded storefront
# ======================================================================
@store_router.get("/{advertiser_id}")
async def storefront(advertiser_id: str, request: Request):
    db = request.app.state.db
    games = await _load_store_games(db, advertiser_id)
    if not games:
        # Nothing live for this advertiser — still return brand so the page
        # renders an empty state rather than 404-ing the whole route.
        exists = (await db.advertisers_v2.find_one({"advertiser_id": advertiser_id})
                  or await db.advertisers.find_one({"advertiser_id": advertiser_id}))
        if not exists:
            raise HTTPException(404, "store_not_found")
    sample = await db.game_campaigns.find_one(
        {"advertiser_id": advertiser_id}) if not games else \
        await db.game_campaigns.find_one({"campaign_id": games[0]["campaign_id"]})
    brand = await _resolve_brand(db, advertiser_id, sample)
    total_remaining = 0
    any_unlimited = False
    for g in games:
        if not g.get("is_coupon_game"):
            continue
        if g.get("remaining_today") is None:
            any_unlimited = True
        else:
            total_remaining += int(g["remaining_today"])
    return {
        "brand": brand,
        "games": games,
        "coupons_left_today": None if any_unlimited else total_remaining,
        "resets_at": _next_utc_midnight_iso(),
    }


@store_router.get("/{advertiser_id}/scarcity")
async def storefront_scarcity(advertiser_id: str, request: Request):
    db = request.app.state.db
    games = await _load_store_games(db, advertiser_id)
    total_remaining = 0
    any_unlimited = False
    slim = []
    for g in games:
        if not g.get("is_coupon_game"):
            continue
        rt = g.get("remaining_today")
        if rt is None:
            any_unlimited = True
        else:
            total_remaining += int(rt)
        slim.append({
            "campaign_id": g["campaign_id"], "title": g["title"],
            "game_type": g["game_type"], "remaining_today": rt,
            "total_cap_today": g.get("total_cap_today"),
        })
    return {
        "advertiser_id": advertiser_id,
        "games": slim,
        "coupons_left_today": None if any_unlimited else total_remaining,
        "resets_at": _next_utc_midnight_iso(),
    }


# ======================================================================
# Consumer — my coupons (unified across the three coupon sources)
# ======================================================================
def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


async def _sponsor_name(db, campaign_id: Optional[str], cache: dict) -> Optional[str]:
    if not campaign_id:
        return None
    if campaign_id in cache:
        return cache[campaign_id]
    c = await db.game_campaigns.find_one(
        {"campaign_id": campaign_id}, {"sponsor_name": 1, "_id": 0})
    name = (c or {}).get("sponsor_name")
    cache[campaign_id] = name
    return name


@me_coupons_router.get("/wallet-coupons")
async def my_coupons(request: Request, user: dict = Depends(current_user)):
    """Unifies the user's owned coupons from all three engines:
    games_v2 wallet items, ad-saved coupons, and flat /play resolve wins."""
    db = request.app.state.db
    uid = user["user_id"]
    out: list[dict] = []
    cache: dict = {}

    # 1) games_v2 / ad wallet items with a coupon nature.
    wcur = db.user_wallet_items.find(
        {"user_id": uid,
         "item_type": {"$in": ["coupon", "add_to_wallet"]}}
    ).sort("created_at", -1).to_list(200)
    for wi in await wcur:
        val = wi.get("value_cents")
        label = None
        if isinstance(val, (int, float)) and val:
            label = f"{val/100:.0f} off"
        out.append({
            "id": str(wi.get("_id")),
            "source": "wallet",
            "title": wi.get("title") or "Coupon",
            "description": wi.get("description"),
            "code": wi.get("short_code") or wi.get("coupon_id"),
            "discount_label": label,
            "status": "redeemed" if wi.get("redeemed_at") else (wi.get("status") or "active"),
            "expires_at": _iso(wi.get("expiration") or wi.get("expires_at")),
            "campaign_id": wi.get("campaign_id") or wi.get("source_campaign_id"),
            "wallet_item_id": str(wi.get("_id")),
            "qr_token": wi.get("qr_token"),
            "sponsor_name": await _sponsor_name(
                db, wi.get("campaign_id") or wi.get("source_campaign_id"), cache),
        })

    # 2) ad-saved coupons (db.coupons).
    for cp in await db.coupons.find({"user_id": uid}).sort("saved_at", -1).to_list(200):
        out.append({
            "id": str(cp.get("_id")),
            "source": "saved",
            "title": cp.get("title") or "Saved coupon",
            "description": cp.get("description"),
            "code": cp.get("code"),
            "discount_label": None,
            "status": cp.get("status") or "saved",
            "expires_at": _iso(cp.get("expires_at")),
            "campaign_id": cp.get("attribution_campaign_id"),
            "qr_token": None,
            "sponsor_name": None,
        })

    # 3) flat /play resolve coupon wins (db.plays) — exclude BigPoints
    #    wins (those set bigcoinAwarded > 0 and aren't real coupons).
    pcur = db.plays.find(
        {"listenerId": uid, "coupon": {"$ne": None},
         "$or": [{"bigcoinAwarded": {"$in": [0, None]}},
                 {"bigcoinAwarded": {"$exists": False}}]}
    ).sort("playedAtDt", -1).to_list(200)
    for pl in await pcur:
        coupon = pl.get("coupon") or {}
        out.append({
            "id": pl.get("_id"),
            "source": "game_win",
            "title": pl.get("prizeTitle") or "Discount coupon",
            "description": None,
            "code": coupon.get("code"),
            "discount_label": None,
            "status": "active",
            "expires_at": None,
            "campaign_id": pl.get("gameId"),
            "qr_token": None,
            "sponsor_name": await _sponsor_name(db, pl.get("gameId"), cache),
        })

    active = sum(1 for c in out if c.get("status") in ("active", "saved"))
    return {"items": out, "total": len(out), "active": active}


# ======================================================================
# Admin — FPK coupon cap dashboard
# ======================================================================
@admin_caps_router.get("/coupon-caps")
async def fpk_coupon_caps(request: Request, _u: dict = Depends(require_admin)):
    """Per FPK game, per discount tier: daily cap, issued today, remaining."""
    db = request.app.state.db
    today = _today_str()
    games = []
    total_cap = 0
    total_issued = 0
    cur = db.game_campaigns.find(
        {"advertiser_id": FPK_ADVERTISER_ID}).sort("created_at", 1)
    async for c in cur:
        prizes = await db.game_prizes.find(
            {"campaign_id": c["campaign_id"], "active": True}).to_list(50)
        tiers = []
        g_cap = 0
        g_issued = 0
        for p in sorted(prizes, key=lambda x: int(x.get("value_amount") or 0)):
            if p.get("prize_type") != "coupon":
                continue
            cap = int(p.get("daily_quantity_cap") or 0)
            issued = _issued_today(p, today)
            remaining = max(0, cap - issued) if cap > 0 else None
            tiers.append({
                "prize_id": p.get("prize_id"),
                "title": p.get("title"),
                "percent_off": p.get("value_amount"),
                "daily_cap": cap or None,
                "issued_today": issued,
                "remaining_today": remaining,
                "inventory_remaining": int(p.get("inventory_remaining") or 0),
            })
            if cap > 0:
                g_cap += cap
                g_issued += issued
        total_cap += g_cap
        total_issued += g_issued
        games.append({
            "campaign_id": c["campaign_id"],
            "title": c.get("title"),
            "status": c.get("status"),
            "game_type": await _game_type_for(db, c.get("template_id")),
            "daily_cap": g_cap or None,
            "issued_today": g_issued,
            "remaining_today": max(0, g_cap - g_issued) if g_cap else None,
            "tiers": tiers,
        })
    return {
        "advertiser_id": FPK_ADVERTISER_ID,
        "date": today,
        "resets_at": _next_utc_midnight_iso(),
        "totals": {
            "daily_cap": total_cap or None,
            "issued_today": total_issued,
            "remaining_today": max(0, total_cap - total_issued) if total_cap else None,
        },
        "games": games,
    }


__all__ = ["store_router", "me_coupons_router", "admin_caps_router"]
