"""Phase K.2 + K.4 — Routes for City Stamps + new Points-period Leaderboards.

Endpoints
---------
* GET    /api/me/passport/city-stamps                 — auth, own stamps.
* GET    /api/passport/{user_id}/city-stamps      — public view.
* GET    /api/me/passport/ambassador-tier          — own tier + balance.
* GET    /api/leaderboards/points
        ?scope=global|city|friends&period=today|week|month|all&limit=20

The points leaderboards aggregate `points_ledger.delta` per user inside
the period window.  Top-20 is cached in-memory for 5 minutes per
(scope, period, market) tuple to avoid hot aggregations.
"""
from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, current_user_optional
from services.city_stamps_engine import list_user_stamps
from services.passport_engine import (
    compute_ambassador_tier, tier_theme,
)

log = logging.getLogger("bigfm.passport_k_routes")
router = APIRouter(tags=["passport-k"])

# ── In-memory leaderboard cache (5-min TTL per cache key) ──────────
_LB_CACHE: dict[str, tuple[float, dict]] = {}
_LB_TTL_SEC = 300


def _cache_get(key: str) -> Optional[dict]:
    hit = _LB_CACHE.get(key)
    if not hit:
        return None
    ts, val = hit
    if time.monotonic() - ts > _LB_TTL_SEC:
        return None
    return val


def _cache_put(key: str, val: dict) -> None:
    _LB_CACHE[key] = (time.monotonic(), val)


# ── City stamps ────────────────────────────────────────────────────
@router.get("/api/me/passport/city-stamps")
async def my_city_stamps(request: Request,
                                          user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    return await list_user_stamps(db, user_id=user["user_id"],
                                                            include_locked=True)


@router.get("/api/passport/{user_id}/city-stamps")
async def public_city_stamps(user_id: str, request: Request,
                                            current=Depends(current_user_optional)) -> dict:
    db = request.app.state.db
    # Honor privacy: same gate as public_profile_view
    st = await db.social_profile_settings.find_one(
        {"user_id": user_id}) or {}
    if st.get("is_public") is False and (
            not current or current.get("user_id") != user_id):
        raise HTTPException(404, "not_found")
    return await list_user_stamps(db, user_id=user_id, include_locked=True)


# ── Ambassador tier ─────────────────────────────────────────────────
@router.get("/api/me/passport/ambassador-tier")
async def my_ambassador_tier(request: Request,
                                                          user: dict = Depends(current_user)
                                                          ) -> dict:
    db = request.app.state.db
    return await compute_ambassador_tier(db, user["user_id"])


# ── Phase H.5 — Admin manual tier recompute ─────────────────────
@router.post("/api/admin/passport/recompute-tiers")
async def admin_recompute_tiers(request: Request,
                                                                  limit: int = 1000,
                                                                  since_days: int = 7,
                                                                  user: dict = Depends(current_user)
                                                                  ) -> dict:
    """Manual full recompute of ambassador tiers.  Useful after a bulk
    PointsService backfill.  Limited to 5000 users per invocation to
    avoid runaway calls; the periodic scheduler handles the steady
    state."""
    if not (user.get("is_admin") or user.get("is_superadmin")
                  or "admin" in (user.get("roles") or [])):
        raise HTTPException(403, "admin_required")
    from services.passport_tier_scheduler import (
        recompute_ambassador_tier_for_active_users,
    )
    return await recompute_ambassador_tier_for_active_users(
        request.app.state.db,
        limit=min(int(limit), 5000),
        since_days=int(since_days))


# ── Points-period leaderboards ────────────────────────────────────
def _period_since(period: str) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    if period == "all":
        return None
    raise HTTPException(400, "invalid_period")


async def _enrich_rows(db, rows: list[dict], *,
                                            self_user_id: Optional[str]) -> list[dict]:
    """Join user display + city + ambassador tier onto raw aggregate rows."""
    uids = [r["user_id"] for r in rows]
    users = {u["user_id"]: u async for u in
                  db.users.find({"user_id": {"$in": uids}},
                                          {"user_id": 1, "display_name": 1,
                                            "name": 1, "email": 1,
                                            "ambassador_tier": 1,
                                            "ambassador_tier_label": 1})}
    settings = {s["user_id"]: s async for s in
                      db.social_profile_settings.find(
                          {"user_id": {"$in": uids}}) if s.get("user_id")}
    out: list[dict] = []
    for i, r in enumerate(rows, start=1):
        uid = r["user_id"]
        u  = users.get(uid) or {}
        st = settings.get(uid) or {}
        anon = (st.get("show_leaderboard_position_publicly") is False
                      and uid != self_user_id)
        display = ((st.get("display_name") if not anon else None)
                          or (u.get("display_name") if not anon else None)
                          or (u.get("name") if not anon else None)
                          or ("Anonymous Listener" if anon
                                else (u.get("email") or "Listener").split("@")[0]))
        tier = u.get("ambassador_tier") or "bronze"
        theme = tier_theme(tier)
        out.append({
            "rank":                            i,
            "user_id":                      uid if not anon else None,
            "handle":                      st.get("handle") if not anon else None,
            "display_name":            display,
            "avatar_url":                  st.get("avatar_url") if not anon else None,
            "city":                            st.get("city_pin"),
            "ambassador_tier":      tier,
            "ambassador_tier_label": theme.get("label"),
            "ambassador_tier_color": theme.get("hex"),
            "points_in_period":      int(r.get("delta") or 0),
            "is_self":                      uid == self_user_id,
        })
    return out


async def _global_leaderboard(db, *, since: Optional[datetime],
                                              limit: int,
                                              market: Optional[str] = None
                                              ) -> list[dict]:
    match: dict = {"delta": {"$gt": 0}}
    if since is not None:
        match["created_at"] = {"$gte": since}
    pipe: list[dict] = [{"$match": match}]
    if market:
        # Filter by user.market via a $lookup (cheap since uids are small).
        pipe += [
            {"$lookup": {"from": "users", "localField": "user_id",
                              "foreignField": "user_id", "as": "user"}},
            {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
            {"$match": {"user.market": market.lower()}},
        ]
    pipe += [
        {"$group": {"_id": "$user_id", "delta": {"$sum": "$delta"}}},
        {"$sort": {"delta": -1}},
        {"$limit": int(limit)},
        {"$project": {"_id": 0, "user_id": "$_id", "delta": 1}},
    ]
    return await db.points_ledger.aggregate(pipe).to_list(int(limit))


async def _friends_user_ids(db, *, user_id: str) -> list[str]:
    """Friends = users that this person invited (inviter→) OR who
    invited this person (←invitee).  Reads `referral_invites` +
    `referral_attributions` for both directions."""
    out: set[str] = set()
    # I invited them
    async for r in db.referral_invites.find(
            {"inviter_user_id": user_id, "redeemed_user_id": {"$ne": None}},
            {"redeemed_user_id": 1}):
        if r.get("redeemed_user_id"):
            out.add(r["redeemed_user_id"])
    # They invited me — look up by my redeemed referral_attributions row
    async for r in db.referral_attributions.find(
            {"referee_user_id": user_id,
              "attribution_status": {"$in": ["engaged", "completed"]}},
            {"referrer_user_id": 1}):
        if r.get("referrer_user_id"):
            out.add(r["referrer_user_id"])
    out.discard(user_id)
    return list(out)


@router.get("/api/leaderboards/points")
async def points_leaderboard(request: Request,
                                                          scope: str = Query("global"),
                                                          period: str = Query("week"),
                                                          market: Optional[str] = Query(None),
                                                          limit: int = Query(20, ge=1, le=100),
                                                          current=Depends(current_user_optional)
                                                          ) -> dict:
    if scope not in ("global", "city", "friends"):
        raise HTTPException(400, "invalid_scope")
    since = _period_since(period)
    self_uid = current.get("user_id") if current else None

    cache_key = f"{scope}|{period}|{market or ''}|{limit}|{self_uid or ''}"
    cached = _cache_get(cache_key) if scope != "friends" else None
    if cached:
        return cached

    db = request.app.state.db
    if scope == "friends":
        if not self_uid:
            raise HTTPException(401, "auth_required_for_friends")
        friend_ids = await _friends_user_ids(db, user_id=self_uid)
        # Always include self in the friends ranking
        friend_ids = list(set(friend_ids + [self_uid]))
        if not friend_ids:
            return {"scope": scope, "period": period,
                          "rows": [], "your_rank": None}
        match: dict = {"user_id": {"$in": friend_ids}, "delta": {"$gt": 0}}
        if since is not None:
            match["created_at"] = {"$gte": since}
        pipe = [
            {"$match": match},
            {"$group": {"_id": "$user_id", "delta": {"$sum": "$delta"}}},
            {"$sort": {"delta": -1}},
            {"$limit": int(limit)},
            {"$project": {"_id": 0, "user_id": "$_id", "delta": 1}},
        ]
        rows = await db.points_ledger.aggregate(pipe).to_list(int(limit))
    elif scope == "city":
        # market resolves from query OR from caller's profile city_pin.
        if not market and self_uid:
            st = await db.social_profile_settings.find_one(
                {"user_id": self_uid}, {"city_pin": 1}) or {}
            market = (st.get("city_pin") or "").lower() or None
        if not market:
            raise HTTPException(400, "market_required_for_city_scope")
        rows = await _global_leaderboard(db, since=since, limit=limit,
                                                                      market=market)
    else:  # global
        rows = await _global_leaderboard(db, since=since, limit=limit)

    enriched = await _enrich_rows(db, rows, self_user_id=self_uid)
    your_rank = next((r["rank"] for r in enriched if r.get("is_self")), None)
    out = {"scope": scope, "period": period,
                  "market": market,
                  "rows":      enriched,
                  "your_rank": your_rank,
                  "computed_at": datetime.now(timezone.utc).isoformat()}
    if scope != "friends":
        _cache_put(cache_key, out)
    return out
