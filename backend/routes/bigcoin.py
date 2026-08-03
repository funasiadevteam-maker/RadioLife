"""Phase 5 — BigCoin user-facing routes."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, current_user_optional
from services.bigcoin import (
    award, listening_heartbeat, maybe_award_onboarding,
    compute_tier, tier_color, tier_label, MILESTONES,
)
from services.streaks import touch_streak
from services.badges import recompute_user_badges
from services.redemption import redeem_reward

logger = logging.getLogger("bigfm.bigcoin.routes")

bc_router = APIRouter(prefix="/api/bigcoin", tags=["bigcoin"])


def _strip_id(d: dict) -> dict:
    d.pop("_id", None)
    return d


# ---------------------------------------------------------------
@bc_router.get("/me")
async def bigcoin_me(request: Request, user: dict = Depends(current_user)):
    """Returns balance, lifetime, tier, milestone state, streak.

    Phase F-2 — `balance` is sourced from the unified Points ledger
    (PointsService.get_balance) instead of the legacy
    `users.bigcoin_balance` field.  Lifetime + tier still come off the
    legacy field because they're append-only metrics (no readers ever
    decrement)."""
    db = request.app.state.db
    # Re-read to get fresh fields
    u = await db.users.find_one({"user_id": user["user_id"]},
                                  {"bigcoin_balance": 1, "bigcoin_lifetime_earned": 1,
                                   "bigcoin_tier": 1, "bigcoin_milestone_pending": 1,
                                   "referrer_code": 1, "adfree_until": 1, "_id": 0}) or {}
    # Ensure a referrer_code exists (lazy creation)
    if not u.get("referrer_code"):
        code = _gen_referrer_code(user["user_id"], user.get("email") or "")
        await db.users.update_one({"user_id": user["user_id"]},
                                    {"$set": {"referrer_code": code}})
        u["referrer_code"] = code
    streak = await db.user_streaks.find_one({"user_id": user["user_id"]},
                                              {"_id": 0}) or {}
    # Phase F-2 — read the ledger sum, NOT the legacy field.
    try:
        from services.points_service import PointsService
        balance = int(await PointsService(db).get_balance(user["user_id"]) or 0)
    except Exception:
        balance = int(u.get("bigcoin_balance") or 0)
    lifetime = int(u.get("bigcoin_lifetime_earned") or 0)
    tier = u.get("bigcoin_tier") or compute_tier(lifetime)
    # Next milestone progress
    next_m = next((m for m in MILESTONES if m > lifetime), None)
    return {
        "balance": balance, "lifetime_earned": lifetime,
        "tier": tier, "tier_label": tier_label(tier),
        "tier_color": tier_color(tier),
        "next_milestone": next_m,
        "milestone_progress": (lifetime / next_m * 100) if next_m else 100,
        "milestone_pending": u.get("bigcoin_milestone_pending"),
        "referrer_code": u.get("referrer_code"),
        # Phase 10b — alias for callers that read `referral_code`
        # (matches /api/passport/me + /api/passport/{user_id} naming).
        "referral_code": u.get("referrer_code"),
        "adfree_until": (u.get("adfree_until").isoformat()
                          if u.get("adfree_until") else None),
        "streak_days": int(streak.get("current_streak_days") or 0),
        "longest_streak_days": int(streak.get("longest_streak_days") or 0),
    }


@bc_router.get("/transactions")
async def bigcoin_transactions(request: Request,
                                 user: dict = Depends(current_user),
                                 limit: int = Query(50, ge=1, le=200),
                                 offset: int = Query(0, ge=0)):
    db = request.app.state.db
    cur = db.bigcoin_transactions.find({"user_id": user["user_id"]}) \
                                     .sort("created_at", -1) \
                                     .skip(offset).limit(limit)
    out = []
    async for d in cur:
        out.append({
            "id": str(d.get("_id")),
            "type": d.get("type"), "source": d.get("source"),
            "amount": d.get("amount"), "balance_after": d.get("balance_after"),
            "metadata_json": d.get("metadata_json"), "note": d.get("note"),
            "created_at": d.get("created_at").isoformat() if d.get("created_at") else None,
        })
    total = await db.bigcoin_transactions.count_documents({"user_id": user["user_id"]})
    return {"items": out, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------
# Heartbeat
@bc_router.post("/heartbeat")
async def post_heartbeat(payload: dict, request: Request,
                           user: dict = Depends(current_user)):
    """Client fires this every 60s while audio is playing.
    Server validates and may award 1 BC per valid minute."""
    db = request.app.state.db
    # Premium users still earn (per acceptance #11)
    session_id = (payload or {}).get("session_id")
    track_changed = bool((payload or {}).get("track_changed"))
    # Touch streak on first heartbeat of the day
    streak_res = await touch_streak(db, user["user_id"])
    result = await listening_heartbeat(db, user["user_id"], session_id)
    if streak_res:
        result["streak"] = streak_res
    # Phase 5 — low-skip bonus tracking: client signals when a NEW track starts
    # playing (track_changed=true on the first heartbeat of each track). Server
    # increments the per-session consecutive-no-skip counter and awards 5 BC
    # every 5th consecutive play.
    if track_changed and session_id:
        try:
            from services.streaks import increment_consecutive_play
            from services.bigcoin import maybe_award_low_skip
            cnt = await increment_consecutive_play(db, user["user_id"], session_id)
            bonus = await maybe_award_low_skip(db, user["user_id"], session_id, cnt)
            if bonus:
                result["low_skip_bonus"] = bonus
        except Exception:
            pass
    if result.get("credited"):
        # Check badges every 10 minutes (cheap heuristic: every minute-bucket % 10 == 0)
        now = datetime.now(timezone.utc)
        if now.minute % 10 == 0:
            try:
                await recompute_user_badges(db, user["user_id"])
            except Exception:
                pass
    # Phase 8b — milestone auto-unlock on listening minutes / streak
    try:
        from services.game_unlock_engine import check_listening_unlocks
        awarded = await check_listening_unlocks(db, user["user_id"])
        if awarded:
            result["unlocks_awarded"] = [
                {"unlock_id": u.get("unlock_id"),
                  "campaign_id": u.get("campaign_id"),
                  "rule_id": u.get("rule_id"),
                  "unlock_reason": u.get("unlock_reason")}
                for u in awarded
            ]
    except Exception:
        pass
    return result


# ---------------------------------------------------------------
# Rewards listing
@bc_router.get("/rewards")
async def list_rewards(request: Request,
                         user: Optional[dict] = Depends(current_user_optional),
                         category: Optional[str] = None):
    db = request.app.state.db
    q = {"active": True}
    if category: q["category"] = category
    cur = db.bigcoin_rewards.find(q).sort("cost_bigcoin", 1)
    items = []
    async for r in cur:
        stock_left = None
        if r.get("stock_limit") is not None:
            stock_left = int(r["stock_limit"]) - int(r.get("redeemed_count", 0))
        items.append({
            "reward_id": r["_id"], "name": r.get("name"),
            "description": r.get("description"),
            "cost_bigcoin": r.get("cost_bigcoin"),
            "type": r.get("type"), "payload_json": r.get("payload_json"),
            "image_url": r.get("image_url"), "category": r.get("category"),
            "stock_left": stock_left,
            "partner_business_id": r.get("partner_business_id"),
            "expires_at": (r["expires_at"].isoformat() if r.get("expires_at") else None),
        })
    return {"items": items, "total": len(items)}


@bc_router.post("/redeem/{reward_id}")
async def redeem(reward_id: str, request: Request,
                   user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await redeem_reward(db, user, reward_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Re-run badge check
    try:
        await recompute_user_badges(db, user["user_id"])
    except Exception:
        pass
    return result


@bc_router.get("/redemptions")
async def my_redemptions(request: Request, user: dict = Depends(current_user),
                           limit: int = Query(50, ge=1, le=200)):
    db = request.app.state.db
    cur = db.bigcoin_redemptions.find({"user_id": user["user_id"]}) \
                                    .sort("redeemed_at", -1).limit(limit)
    items = []
    async for d in cur:
        items.append({
            "redemption_id": d["_id"], "reward_id": d.get("reward_id"),
            "reward_name": d.get("reward_name"), "reward_type": d.get("reward_type"),
            "cost_paid": d.get("cost_paid"), "status": d.get("status"),
            "fulfillment_data_json": d.get("fulfillment_data_json"),
            "redeemed_at": d["redeemed_at"].isoformat() if d.get("redeemed_at") else None,
        })
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------
# Badges
@bc_router.get("/badges")
async def list_badges(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    unlocked = set()
    async for d in db.user_badges.find({"user_id": user["user_id"]},
                                          {"badge_id": 1, "unlocked_at": 1, "_id": 0}):
        unlocked.add(d["badge_id"])
    cur = db.badges.find({"active": True}).sort("sort_order", 1)
    items = []
    async for b in cur:
        items.append({
            "badge_id": b["_id"], "slug": b.get("slug"),
            "name": b.get("name"), "description": b.get("description"),
            "icon": b.get("icon"), "tier": b.get("tier"),
            "unlock_rule_json": b.get("unlock_rule_json"),
            "unlocked": b["_id"] in unlocked,
        })
    return {"items": items, "unlocked_count": len(unlocked),
            "total": len(items)}


# ---------------------------------------------------------------
# Referrals
def _gen_referrer_code(user_id: str, email: str) -> str:
    """Stable, friendly: BFM-{6 chars from user_id hash}"""
    import hashlib
    h = hashlib.sha256(f"{user_id}|{email}".encode()).hexdigest()
    return f"BFM-{h[:6].upper()}"


@bc_router.get("/referrals")
async def my_referrals(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    u = await db.users.find_one({"user_id": user["user_id"]},
                                  {"referrer_code": 1, "_id": 0}) or {}
    code = u.get("referrer_code")
    if not code:
        code = _gen_referrer_code(user["user_id"], user.get("email") or "")
        await db.users.update_one({"user_id": user["user_id"]},
                                    {"$set": {"referrer_code": code}})
    cur = db.referrals.find({"referrer_user_id": user["user_id"]}) \
                          .sort("referred_at", -1).limit(50)
    items = []
    completed = 0
    bc_earned = 0
    async for d in cur:
        if d.get("status") == "completed":
            completed += 1
            bc_earned += int(d.get("bigcoin_awarded") or 0)
        items.append({
            "id": str(d["_id"]), "referred_email": d.get("referred_email"),
            "referred_user_id": d.get("referred_user_id"),
            "status": d.get("status"),
            "bigcoin_awarded": d.get("bigcoin_awarded"),
            "referred_at": d["referred_at"].isoformat() if d.get("referred_at") else None,
            "completed_at": (d["completed_at"].isoformat()
                              if d.get("completed_at") else None),
        })
    return {
        "referrer_code": code,
        "share_url": f"/invite/{code}",
        "total_invited": len(items),
        "completed": completed,
        "bigcoin_earned": bc_earned,
        "items": items,
        "monthly_cap": 1000,
    }


@bc_router.post("/referrals/track")
async def track_referral(payload: dict, request: Request,
                           u: Optional[dict] = Depends(current_user_optional)):
    """Called when a NEW user signs up via ?invite=CODE.
    Creates a referral doc with status=pending."""
    db = request.app.state.db
    code = (payload or {}).get("code") or ""
    code = code.strip().upper()
    if not code:
        raise HTTPException(400, "code required")
    referrer = await db.users.find_one({"referrer_code": code},
                                         {"user_id": 1, "email": 1, "_id": 0})
    if not referrer:
        raise HTTPException(404, "invite code not found")
    # Anti-self-referral
    if u and u.get("user_id") == referrer["user_id"]:
        raise HTTPException(400, "cannot refer yourself")
    rid = f"ref_{uuid.uuid4().hex[:14]}"
    ip = (request.client.host if request.client else None)
    # Anti-abuse: same IP already used for this referrer.
    # Phase 5.2 — only treat REAL public IPs as a signal. Localhost, IPv6
    # loopback, RFC1918 / k8s pod (10.x, 192.168.x, 172.16-31.x) and link-local
    # are treated as NEUTRAL because the entire pod / preview environment
    # shares those ranges and would auto-flag every signup from automation
    # or load balancers.
    abuse_flag = False
    abuse_reason = None
    if ip and _is_publicly_routable_ip(ip):
        same_ip = await db.referrals.find_one({
            "referrer_user_id": referrer["user_id"],
            "ip": ip,
        }, {"_id": 1})
        if same_ip:
            abuse_flag = True
            abuse_reason = "same_public_ip"
    await db.referrals.insert_one({
        "_id": rid, "referrer_user_id": referrer["user_id"],
        "referrer_code": code,
        "referred_user_id": (u or {}).get("user_id"),
        "referred_email": (u or {}).get("email") or (payload or {}).get("email"),
        "ip": ip, "ip_is_public": _is_publicly_routable_ip(ip) if ip else False,
        "status": "abuse_flagged" if abuse_flag else "pending",
        "abuse_reason": abuse_reason,
        "bigcoin_awarded": 0,
        "referred_at": datetime.now(timezone.utc),
    })
    return {"ok": True, "referral_id": rid, "flagged": abuse_flag,
            "reason": abuse_reason}


def _is_publicly_routable_ip(ip: Optional[str]) -> bool:
    """True only for genuinely public IPs. Localhost, k8s pod CIDRs
    (10.x, 192.168.x, 172.16-31.x), IPv6 link-local/loopback, and
    Cloudflare's preview-tunnel range are treated as neutral."""
    if not ip: return False
    try:
        import ipaddress
        addr = ipaddress.ip_address(ip)
        if addr.is_loopback: return False
        if addr.is_private: return False        # 10.*, 192.168.*, 172.16-31.*
        if addr.is_link_local: return False
        if addr.is_reserved or addr.is_multicast: return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------
async def complete_referral_after_onboarding(db, user_id: str) -> None:
    """Called from auth.py users_save_prefs after onboarding completes.

    Handles two parallel paths:
      1. Phase 5 `referrals` collection (legacy /api/users/refer POST flow)
      2. Phase 10a `referral_attributions` collection (cookie + claim flow)

    For either path:
      - Award 100 BC to the referrer (subject to monthly cap)
      - Mark the row engaged / completed
      - Emit the badge_engine `referral_completed` evaluation
      - Fire the `referral_engaged` webhook
    Idempotent.
    """
    # ── Path 1: legacy Phase 5 referrals ────────────────────────────────
    pending = await db.referrals.find_one({
        "referred_user_id": user_id, "status": "pending",
    })
    referrer_user_id: Optional[str] = None
    if pending:
        # Check monthly cap (existing logic)
        from datetime import timedelta
        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        pipe = [{"$match": {"referrer_user_id": pending["referrer_user_id"],
                                "status": "completed",
                                "completed_at": {"$gte": month_start}}},
                  {"$group": {"_id": None,
                                "total": {"$sum": "$bigcoin_awarded"}}}]
        doc = await db.referrals.aggregate(pipe).to_list(1)
        earned_this_month = int(doc[0]["total"]) if doc else 0
        if earned_this_month >= 1000:
            await db.referrals.update_one(
                {"_id": pending["_id"]},
                {"$set": {"status": "abuse_flagged",
                            "note": "monthly_cap_reached"}})
        else:
            referrer_user_id = pending["referrer_user_id"]
            await award(db, referrer_user_id, 100, "referral",
                          metadata={"referral_id": pending["_id"],
                                        "referred_user_id": user_id})
            await db.referrals.update_one(
                {"_id": pending["_id"]},
                {"$set": {"status": "completed",
                            "bigcoin_awarded": 100,
                            "completed_at": datetime.now(timezone.utc)}})

    # ── Path 2: Phase 10a referral_attributions (signed_up → engaged) ──
    # Find the attribution row claimed at signup.  If status is already
    # `engaged`, nothing to do.  If `signed_up`, award + flip status.
    att = await db.referral_attributions.find_one_and_update(
        {"referee_user_id": user_id, "attribution_status": "signed_up"},
        {"$set": {"attribution_status": "engaged",
                   "first_engagement_at": datetime.now(timezone.utc)}},
        return_document=True)
    if att:
        att_referrer = att.get("referrer_user_id")
        # Award BC if the legacy path didn't already pay this referrer
        if att_referrer and att_referrer != referrer_user_id:
            # Same monthly cap protection
            from datetime import timedelta
            month_start = datetime.now(timezone.utc).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0)
            pipe = [{"$match": {"referrer_user_id": att_referrer,
                                    "status": "completed",
                                    "completed_at": {"$gte": month_start}}},
                      {"$group": {"_id": None,
                                    "total": {"$sum": "$bigcoin_awarded"}}}]
            doc = await db.referrals.aggregate(pipe).to_list(1)
            earned_this_month = int(doc[0]["total"]) if doc else 0
            if earned_this_month < 1000:
                await award(db, att_referrer, 100, "referral",
                              metadata={
                                  "attribution_id": att.get("attribution_id"),
                                  "referred_user_id": user_id,
                                  "source": "phase10a_attribution"})
                # Mirror into legacy referrals collection for accounting
                import uuid as _u
                await db.referrals.insert_one({
                    "_id": f"ref_{_u.uuid4().hex[:14]}",
                    "referrer_user_id": att_referrer,
                    "referrer_code": att.get("ref_code"),
                    "referred_user_id": user_id,
                    "ip": None, "ip_is_public": False,
                    "status": "completed",
                    "bigcoin_awarded": 100,
                    "referred_at": att.get("landing_at"),
                    "completed_at": datetime.now(timezone.utc),
                    "source": "phase10a_attribution"})
            referrer_user_id = att_referrer
        # Fire the webhook + emit referral_completed for badge engine
        try:
            from services.games_v2_webhooks import queue_system_event
            await queue_system_event(
                db, event_type="referral_engaged",
                payload={
                    "attribution_id": att.get("attribution_id"),
                    "referrer_user_id": att.get("referrer_user_id"),
                    "referee_user_id": user_id,
                    "ref_code": att.get("ref_code"),
                    "landing_path": att.get("landing_path"),
                    "engaged_at": datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass

    # ── Fan-out (badge engine evaluation for the referrer) ──────────────
    if referrer_user_id:
        # Legacy Phase 5 badge recompute
        try:
            await recompute_user_badges(db, referrer_user_id)
        except Exception:
            pass
        # Phase 10a badge engine — fires `referrer` + `super_referrer`
        try:
            from services.badge_engine import evaluate as badge_evaluate
            await badge_evaluate(
                db, referrer_user_id, "referral_completed",
                {"referee_user_id": user_id})
        except Exception:
            pass


# ---------------------------------------------------------------
# Milestone consumption (called by RJ pipeline)
@bc_router.post("/milestone/consume")
async def consume_milestone(request: Request, user: dict = Depends(current_user)):
    """RJ pipeline calls this internally after weaving a milestone into a
    script. Clears the milestone_pending flag so it's only mentioned once."""
    db = request.app.state.db
    res = await db.users.find_one_and_update(
        {"user_id": user["user_id"]},
        {"$unset": {"bigcoin_milestone_pending": ""}},
        return_document=False, projection={"bigcoin_milestone_pending": 1, "_id": 0},
    )
    return {"ok": True, "consumed": (res or {}).get("bigcoin_milestone_pending")}
