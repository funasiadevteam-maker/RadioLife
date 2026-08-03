"""Phase 10a — Social Passport routes.

Public + listener endpoints for badges, ambassador state, referrals,
landing-page attribution, and private profile settings.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from services.badge_engine import (
    badge_view, recompute_ambassador, evaluate as badge_evaluate,
    admin_grant as badge_admin_grant,
)
from services.referrals_v2 import (
    register_landing, claim_attribution, mark_engaged,
    attribution_stats, fingerprint,
    DEFAULT_ATTRIBUTION_TTL_DAYS,
)
from services.passport_public import (
    public_profile_view, validate_handle,
    list_unclaimed_celebrations, mark_celebrations_seen,
    get_leaderboard, list_leaderboard_cities,
    recompute_leaderboards, migrate_phase5_badges,
    SUPPORTED_LEADERBOARD_METRICS,
    invalid_metric_error_detail,
)

logger = logging.getLogger("bigfm.passport")

passport_router = APIRouter(prefix="/api/passport", tags=["passport"])
referrals_v2_router = APIRouter(prefix="/api/referrals", tags=["referrals_v2"])
admin_passport_router = APIRouter(prefix="/api/admin/passport",
                                                  tags=["admin_passport"])

ATTRIBUTION_COOKIE = "bigfm_ref"


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _require_admin(user: dict) -> None:
    if (user.get("role") or "listener") != "admin":
        raise HTTPException(403, "admin_only")


def _iso(v):
    if isinstance(v, datetime):
        return v.isoformat()
    return v


# ─── Profile settings models ───────────────────────────────────────────
class SocialSettingsIn(BaseModel):
    display_name: Optional[str] = Field(None, max_length=80)
    bio: Optional[str] = Field(None, max_length=280)
    avatar_url: Optional[str] = Field(None, max_length=500)
    city_pin: Optional[str] = Field(None, max_length=80)
    handle: Optional[str] = Field(None, max_length=20)
    is_public: Optional[bool] = None
    show_badges_publicly: Optional[bool] = None
    show_listening_stats_publicly: Optional[bool] = None
    show_leaderboard_position_publicly: Optional[bool] = None
    show_ambassador_level_publicly: Optional[bool] = None


def _settings_view(row: Optional[dict], user: dict) -> dict:
    row = row or {}
    return {
        "user_id": user["user_id"],
        "display_name": (row.get("display_name")
                                or user.get("display_name")
                                or (user.get("email") or "Listener").split("@")[0]),
        "bio": row.get("bio") or "",
        "avatar_url": row.get("avatar_url"),
        "city_pin": row.get("city_pin"),
        "handle": row.get("handle"),
        "is_public": row.get("is_public", True),
        "show_badges_publicly": row.get("show_badges_publicly", True),
        "show_listening_stats_publicly": row.get(
            "show_listening_stats_publicly", False),
        "show_leaderboard_position_publicly": row.get(
            "show_leaderboard_position_publicly", True),
        "show_ambassador_level_publicly": row.get(
            "show_ambassador_level_publicly", True),
    }


# ─── /passport/me ──────────────────────────────────────────────────────
@passport_router.get("/me")
async def passport_me(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    # Settings
    settings = await db.social_profile_settings.find_one({"user_id": uid})
    settings_view = _settings_view(settings, user)
    # Earned badges — Phase 10a UI only renders rows whose catalog entry
    # is `schema_version="10a"`.  Legacy Phase 5 rows (e.g. `badge_10_hours`)
    # silently skipped here; they still exist in `user_badges` and remain
    # consumable by the legacy /api/bigcoin/wallet view.
    earned_cur = db.user_badges.find({"user_id": uid}).sort("earned_at", -1)
    earned_rows = [r async for r in earned_cur]
    badge_ids = [r["badge_id"] for r in earned_rows]
    badge_docs = {b["_id"]: b async for b in
                          db.badges.find({"_id": {"$in": badge_ids}})}
    by_category: dict[str, list[dict]] = {}
    total_points = 0
    earned_10a_rows: list[dict] = []   # used for `recent_feed`
    for r in earned_rows:
        b = badge_docs.get(r["badge_id"])
        # Phase 10a only shows rows whose catalog entry has schema 10a
        if not b or b.get("schema_version") != "10a":
            continue
        cat = b.get("category") or "milestone"
        view = badge_view(b)
        view["earned_at"] = _iso(r.get("earned_at") or r.get("unlocked_at"))
        # Coerce _id (legacy rows can carry BSON ObjectId) → safe string
        view["award_id"] = (r.get("award_id") or str(r.get("_id") or ""))
        view["source"] = r.get("source") or "auto_engine"
        by_category.setdefault(cat, []).append(view)
        earned_10a_rows.append(r)
        total_points += int(b.get("points") or 0)
    # In-progress (top 10 by % complete)
    prog_cur = db.badge_progress.find({"user_id": uid}).limit(50)
    in_progress = []
    async for p in prog_cur:
        b = await db.badges.find_one({"_id": p["badge_id"]})
        if not b or not b.get("active"):
            continue
        in_progress.append({
            **badge_view(b),
            "current_value": int(p.get("current_value") or 0),
            "target_value": int(p.get("target_value") or 1),
            "pct": min(100, round(
                int(p.get("current_value") or 0)
                / max(1, int(p.get("target_value") or 1)) * 100, 1)),
        })
    in_progress.sort(key=lambda x: -x["pct"])
    in_progress = in_progress[:10]
    # Ambassador
    amb = await db.user_ambassador_state.find_one({"user_id": uid})
    if not amb:
        amb = await recompute_ambassador(db, uid)
    amb_view = {
        "level": int(amb.get("level") or 1),
        "level_name": amb.get("level_name") or "Listener",
        "points": int(amb.get("points") or 0),
        "next_level_threshold": amb.get("next_level_threshold"),
        "next_level_name": amb.get("next_level_name"),
        "progress_to_next_pct": amb.get("progress_to_next_pct"),
    }
    # Listening stats summary
    pipe = [{"$match": {"user_id": uid}},
              {"$group": {"_id": None,
                            "total_minutes": {"$sum": "$minutes_credited"}}}]
    doc = await db.listening_heartbeats.aggregate(pipe).to_list(1)
    total_min = int((doc[0] or {}).get("total_minutes") or 0) if doc else 0
    today_pipe = [{"$match": {
        "user_id": uid,
        "ts": {"$gte": _now().replace(hour=0, minute=0, second=0,
                                                  microsecond=0)},
    }}, {"$group": {"_id": None,
                          "m": {"$sum": "$minutes_credited"}}}]
    td = await db.listening_heartbeats.aggregate(today_pipe).to_list(1)
    today_min = int((td[0] or {}).get("m") or 0) if td else 0
    # Referral stats (Phase 5 ref_code from users.referrer_code)
    ref_code = user.get("referrer_code")
    ref_stats = await attribution_stats(db, referrer_user_id=uid)
    # Last 5 earned badges (chronological recent feed) — Phase 10a rows only
    recent_feed = []
    for r in earned_10a_rows[:5]:
        b = badge_docs.get(r["badge_id"])
        if not b:
            continue
        recent_feed.append({
            "badge_id": b.get("badge_id"),
            "name": b.get("name"),
            "tier": b.get("tier"),
            "icon_url": b.get("icon_url"),
            "earned_at": _iso(r.get("earned_at") or r.get("unlocked_at")),
        })
    return {
        "settings": settings_view,
        "ambassador": amb_view,
        "badges_total": len(earned_rows),
        "badges_total_points": total_points,
        "badges_by_category": by_category,
        "badges_in_progress": in_progress,
        "listening_stats": {
            "minutes_total": total_min,
            "minutes_today": today_min,
            "hours_total": round(total_min / 60.0, 1),
        },
        "recent_feed": recent_feed,
        "referral_code": ref_code,
        "referral_stats": ref_stats,
    }


@passport_router.get("/me/badges")
async def my_badges(request: Request,
                            category: Optional[str] = None,
                            earned: Optional[bool] = None,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    q: dict = {"active": True, "schema_version": "10a"}
    if category:
        q["category"] = category
    # Phase 10b.1 — orphan-tolerant: a user_badges row may reference a
    # badge_id no longer present in the catalog (deleted seed entry,
    # mid-migration race).  We silently skip those instead of crashing.
    earned_ids = {r["badge_id"] async for r in
                        db.user_badges.find({"user_id": uid},
                                                  {"badge_id": 1, "_id": 0})
                        if r.get("badge_id")}
    items = []
    skipped_orphans = 0
    async for b in db.badges.find(q).sort([("category", 1), ("points", 1)]):
        bid = b.get("badge_id") or str(b.get("_id") or "")
        if not bid:
            skipped_orphans += 1
            continue
        is_earned = bid in earned_ids
        if b.get("secret") and not is_earned:
            continue
        if earned is True and not is_earned:
            continue
        if earned is False and is_earned:
            continue
        try:
            v = badge_view(b)
        except Exception as ex:
            logger.warning(f"badge_view orphan {bid}: {ex}")
            skipped_orphans += 1
            continue
        if not v.get("badge_id"):
            v["badge_id"] = bid
        v["earned"] = is_earned
        items.append(v)
    return {"items": items, "total": len(items),
              "skipped_orphans": skipped_orphans}


@passport_router.get("/badges/catalog")
async def public_catalog(request: Request,
                                  user: Optional[dict] = Depends(
                                      current_user_optional)):
    db = request.app.state.db
    uid = (user or {}).get("user_id")
    earned_ids = set()
    if uid:
        earned_ids = {r["badge_id"] async for r in
                            db.user_badges.find({"user_id": uid},
                                                      {"badge_id": 1, "_id": 0})}
    items = []
    async for b in db.badges.find(
            {"active": True, "schema_version": "10a"}
            ).sort([("category", 1), ("points", 1)]):
        bid = b.get("badge_id") or str(b.get("_id") or "")
        if not bid:
            continue
        if b.get("secret") and bid not in earned_ids:
            continue
        # Phase 10b — defensive: legacy migrated rows may still have a
        # BSON ObjectId `_id` in rare cases.  badge_view() builds an
        # explicit dict from named fields so ObjectId never leaks.
        v = badge_view(b)
        # Fallback badge_id when the catalog row only has _id (Phase 5 era)
        if not v.get("badge_id"):
            v["badge_id"] = bid
        v["earned"] = bid in earned_ids
        items.append(v)
    return {"items": items, "total": len(items)}


@passport_router.get("/me/badge_progress")
async def my_badge_progress(request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    items = []
    async for p in db.badge_progress.find({"user_id": uid}):
        b = await db.badges.find_one({"_id": p["badge_id"]})
        if not b or not b.get("active"):
            continue
        items.append({
            **badge_view(b),
            "current_value": int(p.get("current_value") or 0),
            "target_value": int(p.get("target_value") or 1),
            "pct": min(100, round(
                int(p.get("current_value") or 0)
                / max(1, int(p.get("target_value") or 1)) * 100, 1)),
            "last_updated_at": _iso(p.get("last_updated_at")),
        })
    items.sort(key=lambda x: -x["pct"])
    return {"items": items[:20]}


@passport_router.get("/me/ambassador")
async def my_ambassador(request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    row = await db.user_ambassador_state.find_one({"user_id": uid})
    if not row:
        row = await recompute_ambassador(db, uid)
    levels = [lvl async for lvl in db.ambassador_levels.find()
                            .sort("level", 1)]
    return {
        "user_id": uid,
        "level": row.get("level"),
        "level_name": row.get("level_name"),
        "points": row.get("points"),
        "badge_count": row.get("badge_count"),
        "next_level_threshold": row.get("next_level_threshold"),
        "next_level_name": row.get("next_level_name"),
        "progress_to_next_pct": row.get("progress_to_next_pct"),
        "all_levels": [{"level": lvl["level"], "name": lvl["name"],
                              "min_points": lvl["min_points"],
                              "perks": lvl.get("perks") or []}
                            for lvl in levels],
    }


@passport_router.patch("/me/settings")
async def update_my_settings(body: SocialSettingsIn,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    # Phase 12c — moderate display_name and bio. Default-deny on
    # contact leaks (phone/email/URL) UNLESS the user is in the
    # verified-partner allowlist (safety_settings.leak_allowlist_partner_ids).
    from services.moderation import moderate, PROFILE_REF, _load_safety_settings
    _settings = await _load_safety_settings(db)
    _partner_id = user.get("partner_business_id") or user.get("business_id")
    _allow_leaks = bool(
        _partner_id and _partner_id in
        (_settings.get("leak_allowlist_partner_ids") or []))
    for field in ("display_name", "bio"):
        if upd.get(field):
            verdict = await moderate(
                db, text=upd[field], user_id=uid,
                ref_type=PROFILE_REF, ref_id=field,
                allow_leaks=_allow_leaks)
            if verdict["verdict"] == "block":
                # Surface a category-aware error code so the UI can
                # show the right banner.
                category = "contact_leak" if any(
                    c.startswith("contact_") for c in verdict["categories"]
                ) else (
                    "profanity" if any(
                        c.startswith("profanity") for c in verdict["categories"])
                    else "other")
                raise HTTPException(422, {
                    "code": "blocked_by_moderation",
                    "category": category,
                    "field": field,
                    "reason": verdict["reason"]})
    # Phase 10b — handle validation + uniqueness
    if "handle" in upd:
        try:
            upd["handle"] = validate_handle(upd["handle"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        # Uniqueness across other users
        existing = await db.social_profile_settings.find_one(
            {"handle": upd["handle"],
              "user_id": {"$ne": uid}})
        if existing:
            raise HTTPException(409, "handle_taken")
    if not upd:
        existing = await db.social_profile_settings.find_one({"user_id": uid})
        return {"settings": _settings_view(existing, user)}
    upd["updated_at"] = _now()
    await db.social_profile_settings.update_one(
        {"user_id": uid},
        {"$set": upd,
          "$setOnInsert": {"user_id": uid, "created_at": _now()}},
        upsert=True)
    fresh = await db.social_profile_settings.find_one({"user_id": uid})
    return {"settings": _settings_view(fresh, user)}


# ─── Phase 10b — PUBLIC profile by user_id / handle ────────────────────
@passport_router.get("/by_handle/{handle}")
async def public_profile_by_handle(handle: str, request: Request,
                                                  user: Optional[dict] = Depends(
                                                      current_user_optional)):
    db = request.app.state.db
    try:
        return await public_profile_view(db, handle=handle)
    except ValueError:
        raise HTTPException(404, "not_found")


@passport_router.get("/{user_id}")
async def public_profile_by_user_id(user_id: str, request: Request,
                                                    user: Optional[dict] = Depends(
                                                        current_user_optional)):
    if user_id in ("me", "by_handle", "badges"):
        raise HTTPException(404, "not_found")
    db = request.app.state.db
    try:
        return await public_profile_view(db, target_user_id=user_id)
    except ValueError:
        raise HTTPException(404, "not_found")


# ─── Phase 10b — level-up celebrations ─────────────────────────────────
@passport_router.get("/me/celebrations")
async def my_celebrations(request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    items = await list_unclaimed_celebrations(
        db, user_id=user["user_id"])
    return {"items": items}


class CelebrationsAckIn(BaseModel):
    levels: list[int]


@passport_router.post("/me/celebrations/ack")
async def ack_celebrations(body: CelebrationsAckIn, request: Request,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await mark_celebrations_seen(
        db, user_id=user["user_id"], levels=body.levels or [])
    return {"ok": True}


# ─── Referral attribution (public + listener) ──────────────────────────
class LandingIn(BaseModel):
    ref_code: str
    landing_path: Optional[str] = "/"
    device_fingerprint: Optional[str] = None


@referrals_v2_router.post("/landing")
async def referral_landing(body: LandingIn, request: Request,
                                      response: Response):
    """Public — sets the bigfm_ref cookie and creates the attribution row."""
    db = request.app.state.db
    ua = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else ""
    fp = (body.device_fingerprint or fingerprint(ua, ip))
    try:
        row = await register_landing(
            db, ref_code=body.ref_code,
            landing_path=body.landing_path or "/",
            device_fingerprint=fp)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Set short-lived ref cookie (path=/)
    cookie_val = f"{row['ref_code']}|{row['attribution_id']}"
    response.set_cookie(
        ATTRIBUTION_COOKIE, cookie_val,
        max_age=int(DEFAULT_ATTRIBUTION_TTL_DAYS * 86400),
        httponly=False, samesite="lax")
    return {
        "attribution_id": row["attribution_id"],
        "ref_code": row["ref_code"],
        "landing_path": row["landing_path"],
        "attribution_status": row["attribution_status"],
        "expires_at": _iso(row["expires_at"]),
    }


class ClaimAttributionIn(BaseModel):
    ref_code: Optional[str] = None


@referrals_v2_router.post("/claim")
async def referral_claim(body: ClaimAttributionIn, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    ua = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else ""
    fp = fingerprint(ua, ip)
    rc = body.ref_code
    if not rc:
        # Try cookie
        ck = request.cookies.get(ATTRIBUTION_COOKIE)
        if ck and "|" in ck:
            rc = ck.split("|", 1)[0]
    row = await claim_attribution(
        db, ref_code=rc, user_id=user["user_id"],
        device_fingerprint=fp)
    if not row:
        return {"claimed": False}
    return {
        "claimed": True,
        "attribution_id": row.get("attribution_id"),
        "ref_code": row.get("ref_code"),
        "status": row.get("attribution_status"),
    }


@referrals_v2_router.get("/me/attribution_stats")
async def my_attribution_stats(request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    return await attribution_stats(
        db, referrer_user_id=user["user_id"])


# ─── Admin grant ───────────────────────────────────────────────────────
class AdminGrantIn(BaseModel):
    user_id: str
    badge_id: str
    reason: Optional[str] = None


@admin_passport_router.post("/grant_badge")
async def admin_grant_badge(body: AdminGrantIn, request: Request,
                                          user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        out = await badge_admin_grant(
            db, user_id=body.user_id, badge_id=body.badge_id,
            admin_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(404, str(e))
    # Cleanup phase — explicit admin audit row.  The webhook fires via
    # `queue_system_event` inside admin_grant but ops also need a
    # queryable trail keyed by target/badge.
    try:
        await db.badge_admin_audit.insert_one({
            "_id": f"baa_{uuid.uuid4().hex[:14]}",
            "actor_user_id": user["user_id"],
            "target_user_id": body.user_id,
            "badge_id": body.badge_id,
            "reason": (body.reason if hasattr(body, "reason") else None),
            "action": ("grant" if (out or {}).get("awarded") else "no_op"),
            "already_owned": bool((out or {}).get("already_owned")),
            "award_id": (out or {}).get("award_id"),
            "ts": datetime.now(timezone.utc),
        })
    except Exception as _e:
        logger.warning(f"badge_admin_audit insert failed: {_e}")
    # Phase 10c.1 — full transition shape so callers don't need a second
    # roundtrip to verify points/level updated.  Backwards-compat keys
    # `awarded` and `award_id` remain at the top level.
    return out or {"awarded": False, "award_id": None}


# ─── Admin activate / deactivate (Phase 10a.1) ─────────────────────────
async def _set_badge_active(db, *, badge_id: str, active: bool,
                                       admin_user_id: str) -> dict:
    badge = await db.badges.find_one({"badge_id": badge_id})
    if not badge:
        raise ValueError("badge_not_found")
    prev = bool(badge.get("active"))
    if prev == active:
        return {"badge_id": badge_id, "active": active,
                  "changed": False, "prev_active": prev}
    await db.badges.update_one(
        {"_id": badge["_id"]},
        {"$set": {"active": active, "updated_at": _now()}})
    # Write audit row
    audit_id = f"bda_{__import__('uuid').uuid4().hex[:14]}"
    await db.badge_admin_audit.insert_one({
        "_id": audit_id, "audit_id": audit_id,
        "actor_user_id": admin_user_id,
        "badge_id": badge_id,
        "action": "activate" if active else "deactivate",
        "prev_active": prev, "new_active": active,
        "ts": _now(),
    })
    return {"badge_id": badge_id, "active": active,
              "changed": True, "prev_active": prev,
              "audit_id": audit_id}


@admin_passport_router.post("/badges/{badge_id}/activate")
async def admin_activate_badge(badge_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _set_badge_active(
            db, badge_id=badge_id, active=True,
            admin_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(404, str(e))


@admin_passport_router.post("/badges/{badge_id}/deactivate")
async def admin_deactivate_badge(badge_id: str, request: Request,
                                                  user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    try:
        return await _set_badge_active(
            db, badge_id=badge_id, active=False,
            admin_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(404, str(e))


@admin_passport_router.get("/badges/audit")
async def admin_badge_audit(request: Request, limit: int = 50,
                                      user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    limit = max(1, min(limit, 200))
    items = []
    async for r in db.badge_admin_audit.find().sort("ts", -1).limit(limit):
        items.append({
            "audit_id": r.get("audit_id"),
            "actor_user_id": r.get("actor_user_id"),
            "badge_id": r.get("badge_id"),
            "action": r.get("action"),
            "prev_active": r.get("prev_active"),
            "new_active": r.get("new_active"),
            "ts": _iso(r.get("ts")),
        })
    return {"items": items}


@admin_passport_router.post("/migrate_phase5_badges")
async def admin_migrate_phase5(request: Request,
                                              user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    return await migrate_phase5_badges(db)


# ─── Phase 10b — City leaderboards ─────────────────────────────────────
leaderboards_router = APIRouter(prefix="/api/leaderboards",
                                                tags=["leaderboards"])
admin_leaderboards_router = APIRouter(prefix="/api/admin/leaderboards",
                                                        tags=["admin_leaderboards"])


@leaderboards_router.get("/cities")
async def leaderboard_cities(request: Request):
    db = request.app.state.db
    items = await list_leaderboard_cities(db)
    return {"items": items}


@leaderboards_router.get("/{city}")
async def leaderboard_city(city: str, request: Request,
                                      metric: str = "ambassador_points_alltime",
                                      user: Optional[dict] = Depends(
                                          current_user_optional)):
    if metric not in SUPPORTED_LEADERBOARD_METRICS:
        raise HTTPException(400, invalid_metric_error_detail())
    db = request.app.state.db
    try:
        return await get_leaderboard(
            db, city=city, metric=metric,
            for_user_id=(user or {}).get("user_id"))
    except ValueError as e:
        raise HTTPException(400, str(e))


class RecomputeIn(BaseModel):
    city: Optional[str] = None
    metric: Optional[str] = None
    min_active_users: Optional[int] = None


@admin_leaderboards_router.post("/recompute")
async def admin_recompute_lb(body: RecomputeIn, request: Request,
                                            user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    kwargs = {"cities": [body.city] if body.city else None,
                  "metrics": [body.metric] if body.metric else None}
    if body.min_active_users is not None:
        kwargs["min_active_users"] = int(body.min_active_users)
    return await recompute_leaderboards(db, **kwargs)


@admin_leaderboards_router.get("/last_runs")
async def admin_last_runs(request: Request,
                                      user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    items = []
    async for s in db.leaderboard_snapshots.find(
            {}, {"city": 1, "metric": 1, "computed_at": 1,
                  "active_user_count": 1, "_id": 0}).sort(
            "computed_at", -1).limit(100):
        items.append({
            "city": s.get("city"), "metric": s.get("metric"),
            "computed_at": _iso(s.get("computed_at")),
            "active_user_count": s.get("active_user_count"),
        })
    return {"items": items}


# ─── Phase 10c.1 — Admin grant / revoke ambassador-channel unlocks ─────
class AdminUnlockGrantIn(BaseModel):
    user_id: str
    unlock_id: str
    expires_at: Optional[datetime] = None
    source: Optional[str] = None


class AdminUnlockRevokeIn(BaseModel):
    user_id: str
    unlock_id: str


@admin_passport_router.post("/grant_unlock")
async def admin_grant_unlock(body: AdminUnlockGrantIn, request: Request,
                                            user: dict = Depends(current_user)):
    """Phase 10c.1 — grant a `user_ambassador_unlocks` row so a user can
    access an `exclusive_unlock` channel (or any channel via a slug-
    matched `exclusive_channel` unlock).  Idempotent: if a row already
    exists, extends `expires_at` to MAX(current, provided).

    NOTE: this is for ambassador-tier / Phase 10c channel unlocks.
    Game-campaign unlocks go through `/api/games_v2/admin/unlock_grant`.
    """
    _require_admin(user)
    db = request.app.state.db
    default_exp = datetime.now(timezone.utc) + timedelta(days=30)
    new_exp = body.expires_at or default_exp
    if new_exp.tzinfo is None:
        new_exp = new_exp.replace(tzinfo=timezone.utc)
    existing = await db.user_ambassador_unlocks.find_one(
        {"user_id": body.user_id, "unlock_id": body.unlock_id})
    if not existing:
        # Try the legacy `ref` field too — Phase 10b wrote unlocks keyed
        # on `ref` rather than `unlock_id`.
        existing = await db.user_ambassador_unlocks.find_one(
            {"user_id": body.user_id, "ref": body.unlock_id})
    idempotent = False
    if existing:
        cur_exp = existing.get("expires_at")
        if cur_exp and cur_exp.tzinfo is None:
            cur_exp = cur_exp.replace(tzinfo=timezone.utc)
        winning = max(cur_exp, new_exp) if cur_exp else new_exp
        await db.user_ambassador_unlocks.update_one(
            {"_id": existing["_id"]},
            {"$set": {"expires_at": winning,
                        "updated_at": datetime.now(timezone.utc),
                        "granted_by": "admin_grant",
                        "unlock_id": body.unlock_id,
                        "ref": existing.get("ref") or body.unlock_id}})
        unlock_id_db = existing["_id"]
        idempotent = True
    else:
        unlock_id_db = f"unl_{uuid.uuid4().hex[:14]}"
        await db.user_ambassador_unlocks.insert_one({
            "_id": unlock_id_db,
            "user_id": body.user_id,
            "unlock_id": body.unlock_id,
            # Phase 10c gate also checks `ref` so populate both.
            "ref": body.unlock_id,
            # Default kind — gate's `_has_named_unlock` matches on
            # `unlock_id`/`ref` regardless of kind.
            "unlock_kind": "exclusive_channel",
            "granted_by": "admin_grant",
            "source": body.source or "admin_grant",
            "granted_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "expires_at": new_exp,
        })
    # Audit
    await db.unlock_admin_audit.insert_one({
        "_id": f"uaa_{uuid.uuid4().hex[:14]}",
        "actor_user_id": user["user_id"],
        "target_user_id": body.user_id,
        "unlock_id": body.unlock_id,
        "action": "grant",
        "expires_at": new_exp,
        "idempotent": idempotent,
        "ts": datetime.now(timezone.utc),
    })
    return {"ok": True, "idempotent": idempotent,
              "unlock_row_id": unlock_id_db,
              "user_id": body.user_id, "unlock_id": body.unlock_id,
              "expires_at": new_exp.isoformat()}


@admin_passport_router.post("/revoke_unlock")
async def admin_revoke_unlock(body: AdminUnlockRevokeIn, request: Request,
                                              user: dict = Depends(current_user)):
    """Revoke a previously granted ambassador-channel unlock.
    Implementation sets `expires_at = now - 1s` so the row stays in the
    audit trail but the gate sees it as expired."""
    _require_admin(user)
    db = request.app.state.db
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    res = await db.user_ambassador_unlocks.update_many(
        {"user_id": body.user_id,
          "$or": [{"unlock_id": body.unlock_id},
                    {"ref": body.unlock_id}]},
        {"$set": {"expires_at": expired_at,
                    "revoked_at": datetime.now(timezone.utc),
                    "revoked_by": user["user_id"]}})
    await db.unlock_admin_audit.insert_one({
        "_id": f"uaa_{uuid.uuid4().hex[:14]}",
        "actor_user_id": user["user_id"],
        "target_user_id": body.user_id,
        "unlock_id": body.unlock_id,
        "action": "revoke",
        "modified": res.modified_count,
        "ts": datetime.now(timezone.utc),
    })
    return {"ok": True, "user_id": body.user_id,
              "unlock_id": body.unlock_id,
              "modified": res.modified_count}


__all__ = ["passport_router", "referrals_v2_router",
              "admin_passport_router", "ATTRIBUTION_COOKIE",
              "leaderboards_router", "admin_leaderboards_router"]
