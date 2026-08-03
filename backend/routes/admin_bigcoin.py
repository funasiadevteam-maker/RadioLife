"""Phase 5 — Admin BigCoin routes (transactions, rewards, games, badges, referrals)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin
from services.bigcoin import adjust

logger = logging.getLogger("bigfm.admin.bigcoin")

admin_bc_router = APIRouter(prefix="/api/admin/bigcoin", tags=["admin-bigcoin"])


# ---------------------------------------------------------------
@admin_bc_router.get("/transactions")
async def list_transactions(request: Request, admin: dict = Depends(require_admin),
                              user_id: Optional[str] = None,
                              source: Optional[str] = None,
                              limit: int = Query(50, ge=1, le=500),
                              offset: int = Query(0, ge=0)):
    db = request.app.state.db
    q = {}
    if user_id: q["user_id"] = user_id
    if source: q["source"] = source
    cur = db.bigcoin_transactions.find(q).sort("created_at", -1).skip(offset).limit(limit)
    items = []
    async for d in cur:
        items.append({
            "id": str(d.get("_id")),
            "user_id": d.get("user_id"),
            "type": d.get("type"), "source": d.get("source"),
            "amount": d.get("amount"), "balance_after": d.get("balance_after"),
            "metadata_json": d.get("metadata_json"), "note": d.get("note"),
            "created_at": d["created_at"].isoformat() if d.get("created_at") else None,
        })
    total = await db.bigcoin_transactions.count_documents(q)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@admin_bc_router.get("/summary")
async def bc_summary(request: Request, admin: dict = Depends(require_admin),
                       days: int = Query(7, ge=1, le=90)):
    """Aggregated earn/spend totals + top sources."""
    db = request.app.state.db
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    pipe = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": {"type": "$type", "source": "$source"},
                     "total": {"$sum": "$amount"},
                     "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    breakdown = []
    earn = 0; spend = 0
    async for d in db.bigcoin_transactions.aggregate(pipe):
        breakdown.append({
            "type": d["_id"]["type"], "source": d["_id"]["source"],
            "total": int(d["total"]), "count": int(d["count"]),
        })
        if d["_id"]["type"] == "earn": earn += int(d["total"])
        if d["_id"]["type"] == "spend": spend += abs(int(d["total"]))
    return {"days": days, "earn_total": earn, "spend_total": spend,
            "net_circulation": earn - spend, "breakdown": breakdown}


@admin_bc_router.post("/adjust")
async def adjust_balance(payload: dict, request: Request,
                          admin: dict = Depends(require_admin)):
    """Manual admin adjust: { user_id, delta (signed int), note }."""
    db = request.app.state.db
    uid = (payload or {}).get("user_id")
    delta = int((payload or {}).get("delta", 0))
    note = (payload or {}).get("note") or f"admin adjust by {admin['user_id']}"
    if not uid or delta == 0:
        raise HTTPException(400, "user_id and non-zero delta required")
    try:
        res = await adjust(db, uid, delta, source="admin_adjust",
                            metadata={"admin_user_id": admin["user_id"]},
                            note=note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "balance_after": res["balance_after"]}


# ---------------------------------------------------------------
# Rewards CRUD
@admin_bc_router.get("/rewards")
async def admin_list_rewards(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.bigcoin_rewards.find({}).sort("cost_bigcoin", 1)
    items = []
    async for r in cur:
        items.append({
            "reward_id": r["_id"], "name": r.get("name"),
            "description": r.get("description"),
            "cost_bigcoin": r.get("cost_bigcoin"),
            "type": r.get("type"), "category": r.get("category"),
            "payload_json": r.get("payload_json"),
            "active": r.get("active", True),
            "stock_limit": r.get("stock_limit"),
            "redeemed_count": r.get("redeemed_count", 0),
            "partner_business_id": r.get("partner_business_id"),
        })
    return {"items": items}


@admin_bc_router.post("/rewards/{reward_id}")
async def admin_update_reward(reward_id: str, payload: dict, request: Request,
                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    allowed = {"name", "description", "cost_bigcoin", "active", "stock_limit",
                "category", "image_url", "expires_at", "payload_json"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not update: raise HTTPException(400, "no valid fields to update")
    res = await db.bigcoin_rewards.update_one({"_id": reward_id}, {"$set": update})
    if res.matched_count == 0: raise HTTPException(404, "reward not found")
    return {"ok": True}


# ---------------------------------------------------------------
# Games admin
@admin_bc_router.get("/games")
async def admin_list_games(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.games.find({})
    items = []
    async for g in cur:
        wins = await db.game_sessions.count_documents(
            {"game_id": g["_id"], "result": "won"})
        plays = await db.game_sessions.count_documents({"game_id": g["_id"]})
        items.append({
            "game_id": g["_id"], "slug": g.get("slug"),
            "type": g.get("type"), "title": g.get("title"),
            "active": g.get("active", True),
            "cooldown_sec": g.get("cooldown_sec"),
            "plays_count": plays, "wins_count": wins,
            "win_rate": (wins / plays) if plays else 0,
            "sponsor_business_id": g.get("sponsor_business_id"),
        })
    return {"items": items}


@admin_bc_router.post("/games/{game_id}")
async def admin_update_game(game_id: str, payload: dict, request: Request,
                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    allowed = {"title", "description", "active", "cooldown_sec",
                "sponsor_business_id", "reward_pool_json",
                "rules_json", "daypart_restrictions", "market_restrictions"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not update: raise HTTPException(400, "no valid fields")
    res = await db.games.update_one({"_id": game_id}, {"$set": update})
    if res.matched_count == 0: raise HTTPException(404, "game not found")
    return {"ok": True}


# ---------------------------------------------------------------
# Lyric puzzles CRUD
@admin_bc_router.get("/lyrics")
async def admin_list_lyrics(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.lyric_puzzles.find({}).sort("created_at", -1)
    items = []
    async for lp in cur:
        items.append({
            "puzzle_id": lp["_id"], "song": lp.get("song"),
            "artist": lp.get("artist"), "language": lp.get("language"),
            "first_half": lp.get("first_half"),
            "next_phrase": lp.get("next_phrase"),
            "active": lp.get("active", True),
        })
    return {"items": items}


@admin_bc_router.post("/lyrics")
async def admin_add_lyric(payload: dict, request: Request,
                            admin: dict = Depends(require_admin)):
    import uuid as _uuid
    db = request.app.state.db
    needed = ("song", "first_half", "next_phrase", "language")
    if not all((payload or {}).get(k) for k in needed):
        raise HTTPException(400, f"required: {needed}")
    pid = f"lp_admin_{_uuid.uuid4().hex[:8]}"
    await db.lyric_puzzles.insert_one({
        "_id": pid, "song": payload["song"],
        "artist": payload.get("artist") or "Unknown",
        "language": payload["language"],
        "first_half": payload["first_half"],
        "next_phrase": payload["next_phrase"],
        "active": True, "created_at": datetime.now(timezone.utc),
    })
    return {"ok": True, "puzzle_id": pid}


@admin_bc_router.post("/lyrics/{puzzle_id}")
async def admin_update_lyric(puzzle_id: str, payload: dict, request: Request,
                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    allowed = {"song", "artist", "language", "first_half", "next_phrase", "active"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not update: raise HTTPException(400, "no valid fields")
    res = await db.lyric_puzzles.update_one({"_id": puzzle_id}, {"$set": update})
    if res.matched_count == 0: raise HTTPException(404, "puzzle not found")
    return {"ok": True}


# ---------------------------------------------------------------
# Badges admin
@admin_bc_router.get("/badges")
async def admin_list_badges(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.badges.find({}).sort("sort_order", 1)
    items = []
    async for b in cur:
        unlocked_total = await db.user_badges.count_documents({"badge_id": b["_id"]})
        items.append({
            "badge_id": b["_id"], "slug": b.get("slug"),
            "name": b.get("name"), "description": b.get("description"),
            "icon": b.get("icon"), "tier": b.get("tier"),
            "active": b.get("active", True),
            "unlock_rule_json": b.get("unlock_rule_json"),
            "unlocked_total": unlocked_total,
        })
    return {"items": items}


@admin_bc_router.post("/badges/{badge_id}")
async def admin_update_badge(badge_id: str, payload: dict, request: Request,
                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    allowed = {"name", "description", "tier", "active", "unlock_rule_json",
                "icon", "market", "sort_order"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not update: raise HTTPException(400, "no valid fields")
    res = await db.badges.update_one({"_id": badge_id}, {"$set": update})
    if res.matched_count == 0: raise HTTPException(404, "badge not found")
    return {"ok": True}


# ---------------------------------------------------------------
# Referrals admin
@admin_bc_router.get("/referrals")
async def admin_list_referrals(request: Request, admin: dict = Depends(require_admin),
                                status: Optional[str] = None,
                                limit: int = Query(100, ge=1, le=500)):
    db = request.app.state.db
    q = {}
    if status: q["status"] = status
    cur = db.referrals.find(q).sort("referred_at", -1).limit(limit)
    items = []
    async for d in cur:
        items.append({
            "id": str(d["_id"]),
            "referrer_user_id": d.get("referrer_user_id"),
            "referrer_code": d.get("referrer_code"),
            "referred_user_id": d.get("referred_user_id"),
            "referred_email": d.get("referred_email"),
            "ip": d.get("ip"),
            "status": d.get("status"),
            "bigcoin_awarded": d.get("bigcoin_awarded"),
            "referred_at": d["referred_at"].isoformat() if d.get("referred_at") else None,
            "completed_at": (d["completed_at"].isoformat()
                              if d.get("completed_at") else None),
        })
    return {"items": items, "total": len(items)}


@admin_bc_router.post("/referrals/{ref_id}/approve")
async def admin_approve_referral(ref_id: str, request: Request,
                                   admin: dict = Depends(require_admin)):
    from services.bigcoin import award
    db = request.app.state.db
    ref = await db.referrals.find_one({"_id": ref_id})
    if not ref: raise HTTPException(404, "referral not found")
    if ref.get("status") == "completed":
        return {"ok": True, "already_completed": True}
    await award(db, ref["referrer_user_id"], 100, "referral",
                  metadata={"referral_id": ref_id, "admin_approved": True})
    await db.referrals.update_one(
        {"_id": ref_id},
        {"$set": {"status": "completed", "bigcoin_awarded": 100,
                   "completed_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}


@admin_bc_router.post("/referrals/{ref_id}/reject")
async def admin_reject_referral(ref_id: str, request: Request,
                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.referrals.update_one(
        {"_id": ref_id},
        {"$set": {"status": "abuse_flagged",
                   "rejected_by": admin["user_id"]}},
    )
    if res.matched_count == 0: raise HTTPException(404, "referral not found")
    return {"ok": True}


@admin_bc_router.post("/referrals/{ref_id}/force_complete")
async def admin_force_complete_referral(ref_id: str, request: Request,
                                          admin: dict = Depends(require_admin)):
    """Admin override — clears abuse_flag and credits the referrer +100 BC
    through the SAME completion path used by the normal onboarding flow.
    Idempotent: if already completed, returns the existing payout info
    without double-crediting. Requires the referee to have completed
    onboarding (users.onboarding_complete=true), otherwise 400."""
    from services.bigcoin import award as _award
    db = request.app.state.db
    ref = await db.referrals.find_one({"_id": ref_id})
    if not ref:
        raise HTTPException(404, "referral not found")
    referrer_uid = ref.get("referrer_user_id")
    referee_uid = ref.get("referred_user_id")

    # Idempotency — already completed = return existing payout info
    if ref.get("status") == "completed":
        # Phase F-2 — read balance from the unified ledger.
        try:
            from services.points_service import PointsService
            bal = int(await PointsService(db).get_balance(referrer_uid) or 0)
        except Exception:
            u = await db.users.find_one({"user_id": referrer_uid},
                                           {"bigcoin_balance": 1, "_id": 0}) or {}
            bal = int(u.get("bigcoin_balance") or 0)
        return {
            "ok": True, "idempotent": True,
            "referral_id": ref_id, "status": "completed",
            "referrer_bigcoin_credited": int(ref.get("bigcoin_awarded") or 0),
            "referrer_balance_after": bal,
            "admin_override_by": ref.get("admin_override_by"),
            "completed_at": (ref["completed_at"].isoformat()
                              if ref.get("completed_at") else None),
        }

    # The referee must exist and have finished onboarding
    if not referee_uid:
        raise HTTPException(400, "referral has no referred_user_id yet")
    referee = await db.users.find_one({"user_id": referee_uid},
                                          {"onboarding_complete": 1, "_id": 0})
    if not referee or not referee.get("onboarding_complete"):
        raise HTTPException(400, "referee_onboarding_not_complete")

    now = datetime.now(timezone.utc)
    # Clear flag + audit-log the override
    await db.referrals.update_one(
        {"_id": ref_id},
        {"$set": {"status": "pending",
                   "abuse_reason": None,
                   "admin_override_by": admin["user_id"],
                   "admin_override_at": now}},
    )
    # Credit the referrer through the same award helper used elsewhere.
    res = await _award(db, referrer_uid, 100, "referral",
                         metadata={"referral_id": ref_id,
                                   "referred_user_id": referee_uid,
                                   "admin_override_by": admin["user_id"]})
    await db.referrals.update_one(
        {"_id": ref_id},
        {"$set": {"status": "completed",
                   "bigcoin_awarded": 100,
                   "completed_at": now}},
    )
    # Re-run badge engine for the referrer in case they crossed a refer_N threshold
    try:
        from services.badges import recompute_user_badges
        await recompute_user_badges(db, referrer_uid)
    except Exception:
        pass
    return {
        "ok": True, "idempotent": False,
        "referral_id": ref_id, "status": "completed",
        "referrer_user_id": referrer_uid,
        "referrer_bigcoin_credited": 100,
        "referrer_balance_after": int(res.get("balance_after") or 0),
        "admin_override_by": admin["user_id"],
        "admin_override_at": now.isoformat(),
    }
