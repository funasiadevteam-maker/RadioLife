"""Phase 12c — Admin Trust & Safety routes."""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin
from services.moderation import ensure_moderation_indexes
from services.fraud import ensure_fraud_indexes
from services.abuse import ensure_abuse_indexes
from services.strikes import ensure_strike_indexes

logger = logging.getLogger("bigfm.admin.safety")

admin_safety_router = APIRouter(
    prefix="/api/admin/safety", tags=["admin-safety"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    if isinstance(v, datetime):
        return v.isoformat()
    return v


async def ensure_safety_indexes(db) -> None:
    await ensure_moderation_indexes(db)
    await ensure_fraud_indexes(db)
    await ensure_abuse_indexes(db)
    await ensure_strike_indexes(db)


def _ser(d: dict) -> dict:
    out = dict(d); out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ─── Moderation queue ──────────────────────────────────────────────────
@admin_safety_router.get("/moderation_queue")
async def moderation_queue(request: Request,
                                          status: str = Query("warn"),
                                          limit: int = Query(100, ge=1, le=500),
                                          admin: dict = Depends(require_admin)):
    """Items needing human review: any moderation_audit row where
    `verdict in {warn, block}` (default: warn) ordered by recency."""
    db = request.app.state.db
    verdict_in = ["warn", "block"] if status == "all" else [status]
    cur = db.moderation_audit.find(
        {"verdict": {"$in": verdict_in}}
    ).sort("created_at", -1).limit(limit)
    items = []
    async for d in cur:
        items.append(_ser(d))
    return {"items": items, "count": len(items)}


# ─── Fraud events ──────────────────────────────────────────────────────
@admin_safety_router.get("/fraud_events")
async def fraud_events(request: Request,
                                range: str = Query("30d"),
                                status: Optional[str] = Query(None),
                                limit: int = Query(100, ge=1, le=500),
                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    days = {"7d": 7, "30d": 30, "90d": 90}.get(range, 30)
    q: dict = {"created_at": {"$gte": _now() - timedelta(days=days)}}
    if status:
        q["status"] = status
    cur = db.fraud_events.find(q).sort("created_at", -1).limit(limit)
    items = []
    async for d in cur:
        items.append(_ser(d))
    return {"range": range, "items": items, "count": len(items)}


@admin_safety_router.patch("/fraud_events/{fraud_id}")
async def patch_fraud_event(fraud_id: str, payload: dict,
                                          request: Request,
                                          admin: dict = Depends(require_admin)):
    db = request.app.state.db
    allowed = {"status", "notes"}
    upd = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not upd:
        raise HTTPException(400, "no valid fields")
    if upd.get("status") not in (None, "open", "reviewed", "dismissed"):
        raise HTTPException(400, "status must be open|reviewed|dismissed")
    upd["reviewed_by"] = admin["user_id"]
    upd["reviewed_at"] = _now()
    res = await db.fraud_events.update_one(
        {"fraud_id": fraud_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "fraud event not found")
    fresh = await db.fraud_events.find_one({"fraud_id": fraud_id})
    return _ser(fresh)


# ─── Abuse events ──────────────────────────────────────────────────────
@admin_safety_router.get("/abuse_events")
async def abuse_events(request: Request,
                                range: str = Query("30d"),
                                status: Optional[str] = Query(None),
                                rule: Optional[str] = Query(None),
                                limit: int = Query(100, ge=1, le=500),
                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    days = {"7d": 7, "30d": 30, "90d": 90}.get(range, 30)
    q: dict = {"created_at": {"$gte": _now() - timedelta(days=days)}}
    if status: q["status"] = status
    if rule: q["rule"] = rule
    cur = db.abuse_events.find(q).sort("created_at", -1).limit(limit)
    items = []
    async for d in cur:
        items.append(_ser(d))
    return {"range": range, "items": items, "count": len(items)}


@admin_safety_router.patch("/abuse_events/{abuse_id}/triage")
async def triage_abuse_event(abuse_id: str, payload: dict,
                                              request: Request,
                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    status = (payload or {}).get("status")
    if status not in ("reviewed", "dismissed"):
        raise HTTPException(400, "status must be reviewed|dismissed")
    res = await db.abuse_events.update_one(
        {"abuse_id": abuse_id},
        {"$set": {"status": status,
                    "reviewed_by": admin["user_id"],
                    "reviewed_at": _now(),
                    "notes": (payload or {}).get("notes")}})
    if res.matched_count == 0:
        raise HTTPException(404, "abuse event not found")
    fresh = await db.abuse_events.find_one({"abuse_id": abuse_id})
    return _ser(fresh)


# ─── User actions (suspend / unsuspend / lookup) ───────────────────────
@admin_safety_router.get("/users/{user_id}")
async def user_safety_card(user_id: str, request: Request,
                                          admin: dict = Depends(require_admin)):
    db = request.app.state.db
    user = await db.users.find_one(
        {"user_id": user_id},
        {"user_id": 1, "email": 1, "name": 1, "is_premium": 1,
          "premium_tier": 1, "strikes_summary": 1,
          "suspended_until": 1, "suspended_reason": 1, "mute_until": 1,
          "_id": 0})
    if not user:
        raise HTTPException(404, "user not found")
    # Recent flag context (limit 25 each)
    async def _recent(coll, status_field=None):
        cur = db[coll].find({"user_id": user_id}).sort(
            "created_at", -1).limit(25)
        return [_ser(d) async for d in cur]
    return {
        "user": _ser(user),
        "moderation_recent": await _recent("moderation_audit"),
        "fraud_recent": await _recent("fraud_events"),
        "abuse_recent": await _recent("abuse_events"),
        "strikes_recent": await _recent("strike_events"),
    }


@admin_safety_router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: str, payload: dict, request: Request,
                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    days = int((payload or {}).get("duration_days") or 7)
    reason = ((payload or {}).get("reason") or "admin_action").strip()
    notes = (payload or {}).get("notes")
    if days <= 0 or days > 3650:
        raise HTTPException(400, "duration_days must be 1..3650")
    until = _now() + timedelta(days=days)
    res = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"suspended_until": until,
                    "suspended_reason": reason}})
    if res.matched_count == 0:
        raise HTTPException(404, "user not found")
    # Terminate active sessions
    purged = await db.sessions.delete_many({"user_id": user_id})
    # Audit
    aid = f"safe_{uuid.uuid4().hex[:14]}"
    await db.safety_admin_audit.insert_one({
        "_id": aid, "audit_id": aid, "action": "suspend",
        "target_user_id": user_id, "admin_user_id": admin["user_id"],
        "reason": reason, "notes": notes,
        "duration_days": days, "until": until,
        "sessions_terminated": purged.deleted_count,
        "created_at": _now(),
    })
    return {"user_id": user_id, "suspended_until": until.isoformat(),
              "reason": reason,
              "sessions_terminated": purged.deleted_count}


@admin_safety_router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(user_id: str, request: Request,
                                      payload: Optional[dict] = None,
                                      admin: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.users.update_one(
        {"user_id": user_id},
        {"$unset": {"suspended_until": "", "suspended_reason": ""}})
    if res.matched_count == 0:
        raise HTTPException(404, "user not found")
    aid = f"safe_{uuid.uuid4().hex[:14]}"
    await db.safety_admin_audit.insert_one({
        "_id": aid, "audit_id": aid, "action": "unsuspend",
        "target_user_id": user_id, "admin_user_id": admin["user_id"],
        "notes": (payload or {}).get("notes"),
        "created_at": _now(),
    })
    return {"user_id": user_id, "suspended": False}


# ─── Safety settings (profanity_extra, allowlists, thresholds) ─────────
@admin_safety_router.get("/settings")
async def get_safety_settings(request: Request,
                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    doc = await db.safety_settings.find_one({"_id": "global"}) or {}
    doc.pop("_id", None)
    return {"settings": doc}


@admin_safety_router.patch("/settings")
async def patch_safety_settings(payload: dict, request: Request,
                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    allowed = {"profanity_extra", "leak_allowlist_partner_ids",
                  "strike_thresholds"}
    upd = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not upd:
        raise HTTPException(400, "no valid fields")
    # Phase 12c hotfix — strict shape validation so a bad save can't
    # crash the moderation pipeline later (issue: `profanity_extra: []`
    # was crashing _rule_check with "'list' object is not a mapping").
    if "profanity_extra" in upd:
        v = upd["profanity_extra"]
        if not isinstance(v, dict):
            raise HTTPException(
                400, "profanity_extra must be an object mapping "
                       "lang_code → [word, ...]")
        for lang, words in v.items():
            if not isinstance(words, list) or not all(
                    isinstance(w, str) for w in words):
                raise HTTPException(
                    400, f"profanity_extra['{lang}'] must be a list "
                           "of strings")
    if "leak_allowlist_partner_ids" in upd:
        v = upd["leak_allowlist_partner_ids"]
        if not isinstance(v, list) or not all(
                isinstance(p, str) for p in v):
            raise HTTPException(
                400, "leak_allowlist_partner_ids must be a list of strings")
    if "strike_thresholds" in upd and not isinstance(
            upd["strike_thresholds"], dict):
        raise HTTPException(400, "strike_thresholds must be an object")
    upd["updated_at"] = _now()
    upd["updated_by"] = admin["user_id"]
    await db.safety_settings.update_one(
        {"_id": "global"}, {"$set": upd}, upsert=True)
    fresh = await db.safety_settings.find_one({"_id": "global"})
    fresh.pop("_id", None)
    return {"settings": fresh}
