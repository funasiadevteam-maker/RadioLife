"""Phase 19a Part 5 — Admin user management.

Admin-only surface for listing, role-changing, activating/deactivating
users, with safety rails (cannot demote self, last admin, etc.) and an
append-only audit log.

Auth: every route requires `require_admin` from auth.py.  Mounted under
/api/admin/users so existing ingress rules apply.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin


logger = logging.getLogger("bigfm.admin_users")

admin_users_router = APIRouter(prefix="/api/admin/users",
                                                tags=["admin_users_phase19a"])


ALLOWED_ROLES = {"user", "listener", "creator", "advertiser",
                          "business_partner", "moderator", "ad_manager",
                          "admin"}
ALLOWED_STATUSES = {"active", "inactive", "suspended"}
ALLOWED_ACTIONS = {"role_change", "activate", "deactivate",
                            "suspend", "unsuspend"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str, n: int = 14) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:n]}"


async def _audit(db, *, user_id: str, changed_by: str, action: str,
                          old_value, new_value, reason: Optional[str] = None):
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"invalid_audit_action:{action}")
    aid = _new_id("uaud", 14)
    await db.user_role_audit_log.insert_one({
        "_id": aid, "audit_id": aid,
        "user_id": user_id, "changed_by_admin_id": changed_by,
        "action": action,
        "old_value": old_value, "new_value": new_value,
        "reason": reason, "created_at": _now(),
    })


def _user_view(u: dict) -> dict:
    if not u:
        return {}
    return {
        "user_id": u.get("user_id"),
        "email": u.get("email"), "name": u.get("name"),
        "role": u.get("role"),
        "status": u.get("status") or "active",
        "creator_status": u.get("creator_status"),
        "creator_id": u.get("creator_id"),
        "is_advertiser": bool(u.get("is_advertiser")),
        "is_premium": bool(u.get("is_premium")),
        "market": u.get("market"),
        "created_at": u.get("created_at"),
        "last_login_at": u.get("last_login_at"),
        "deactivated_at": u.get("deactivated_at"),
        "deactivated_by_admin_id": u.get("deactivated_by_admin_id"),
        "deactivation_reason": u.get("deactivation_reason"),
    }


async def _count_active_admins(db) -> int:
    return await db.users.count_documents(
        {"role": "admin", "status": {"$ne": "inactive"}})


# =====================================================================
# LIST + STATS
# =====================================================================
@admin_users_router.get("")
@admin_users_router.get("/")
async def list_users(request: Request,
                                role: Optional[str] = Query(None),
                                status: Optional[str] = Query(None),
                                search: Optional[str] = Query(None),
                                limit: int = Query(25, ge=1, le=200),
                                cursor: Optional[str] = Query(None),
                                _u: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {}
    if role:
        q["role"] = role
    if status:
        q["status"] = status if status != "active" \
                          else {"$in": ["active", None]}
    if search:
        safe = re.escape(search.strip())
        q["$or"] = [{"email": {"$regex": safe, "$options": "i"}},
                          {"name": {"$regex": safe, "$options": "i"}}]
    if cursor:
        q["user_id"] = {"$lt": cursor}
    rows = await db.users.find(q).sort(
        "user_id", -1).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["user_id"]
        rows = rows[:limit]
    return {"items": [_user_view(u) for u in rows],
              "next_cursor": next_cursor, "limit": limit}


@admin_users_router.get("/stats")
async def users_stats(request: Request,
                                  _u: dict = Depends(require_admin)):
    db = request.app.state.db
    total = await db.users.count_documents({})
    by_role: dict = {}
    async for d in db.users.aggregate(
        [{"$group": {"_id": "$role", "n": {"$sum": 1}}}]):
        by_role[d["_id"] or "unknown"] = d["n"]
    by_status: dict = {}
    async for d in db.users.aggregate(
        [{"$group": {"_id": {"$ifNull": ["$status", "active"]},
                            "n": {"$sum": 1}}}]):
        by_status[d["_id"]] = d["n"]
    week_ago = _now() - timedelta(days=7)
    new_signups_7d = await db.users.count_documents(
        {"created_at": {"$gte": week_ago}})
    deactivations_7d = await db.user_role_audit_log.count_documents(
        {"action": "deactivate", "created_at": {"$gte": week_ago}})
    return {"total": total, "by_role": by_role, "by_status": by_status,
              "new_signups_7d": new_signups_7d,
              "deactivations_7d": deactivations_7d}


# =====================================================================
# GLOBAL AUDIT LOG (must be BEFORE /{user_id} to avoid path collision)
# =====================================================================
@admin_users_router.get("/audit-log")
async def global_audit_log(request: Request,
                                            action: Optional[str] = Query(None),
                                            admin_id: Optional[str] = Query(None),
                                            limit: int = Query(50, ge=1, le=200),
                                            cursor: Optional[str] = Query(None),
                                            _u: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {}
    if action:
        q["action"] = action
    if admin_id:
        q["changed_by_admin_id"] = admin_id
    if cursor:
        q["audit_id"] = {"$lt": cursor}
    rows = await db.user_role_audit_log.find(q).sort(
        "audit_id", -1).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["audit_id"]
        rows = rows[:limit]
    for r in rows:
        r.pop("_id", None)
    return {"items": rows, "next_cursor": next_cursor, "limit": limit}


# =====================================================================
# SINGLE USER
# =====================================================================
@admin_users_router.get("/{user_id}")
async def get_user(user_id: str, request: Request,
                            _u: dict = Depends(require_admin)):
    db = request.app.state.db
    u = await db.users.find_one({"user_id": user_id})
    if not u:
        raise HTTPException(404, {"status": "user_not_found"})
    view = _user_view(u)
    # Last 10 audit rows
    audit = await db.user_role_audit_log.find(
        {"user_id": user_id}).sort("audit_id", -1).limit(10).to_list(10)
    for r in audit:
        r.pop("_id", None)
    view["audit_log"] = audit
    # Associated resources
    if view["creator_id"] or u.get("role") == "creator":
        view["creator_profile"] = await db.podcast_creators.find_one(
            {"user_id": user_id}, {"_id": 0})
    if u.get("role") in ("business_partner", "admin"):
        view["businesses"] = await db.businesses.find(
            {"owner_user_id": user_id}, {"_id": 0}).to_list(20)
    return view


@admin_users_router.get("/{user_id}/audit-log")
async def per_user_audit_log(user_id: str, request: Request,
                                                limit: int = Query(50, ge=1, le=200),
                                                cursor: Optional[str] = Query(None),
                                                _u: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {"user_id": user_id}
    if cursor:
        q["audit_id"] = {"$lt": cursor}
    rows = await db.user_role_audit_log.find(q).sort(
        "audit_id", -1).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["audit_id"]
        rows = rows[:limit]
    for r in rows:
        r.pop("_id", None)
    return {"items": rows, "next_cursor": next_cursor, "limit": limit}


# =====================================================================
# ROLE CHANGE
# =====================================================================
class RoleChangeBody(BaseModel):
    new_role: str
    reason: Optional[str] = Field(None, max_length=500)


@admin_users_router.patch("/{user_id}/role")
async def change_role(user_id: str, body: RoleChangeBody,
                                  request: Request,
                                  admin: dict = Depends(require_admin)):
    if body.new_role not in ALLOWED_ROLES:
        raise HTTPException(400,
            {"status": "invalid_role",
              "allowed": sorted(ALLOWED_ROLES)})
    db = request.app.state.db
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(404, {"status": "user_not_found"})
    old_role = target.get("role")
    if old_role == body.new_role:
        return {"ok": True, "no_op": True,
                  "user": _user_view(target)}

    # Safety rails
    if target["user_id"] == admin["user_id"] and body.new_role != "admin":
        raise HTTPException(400, {"status": "cannot_demote_self"})
    if old_role == "admin" and body.new_role != "admin":
        admin_count = await _count_active_admins(db)
        if admin_count <= 1:
            raise HTTPException(400,
                {"status": "cannot_demote_last_admin"})

    set_fields: dict = {"role": body.new_role, "updated_at": _now()}

    # Side effects for creator transitions
    if body.new_role == "creator":
        cr = await db.podcast_creators.find_one({"user_id": user_id})
        now = _now()
        if not cr:
            cid = _new_id("crt", 14)
            await db.podcast_creators.insert_one({
                "_id": cid, "id": cid, "user_id": user_id,
                "display_name": target.get("name") or "Creator",
                "contact_email": target.get("email"),
                "application_status": "approved",
                "approved_at": now, "applied_at": now, "created_at": now,
            })
            set_fields["creator_id"] = cid
        else:
            if cr.get("application_status") != "approved":
                await db.podcast_creators.update_one(
                    {"user_id": user_id},
                    {"$set": {"application_status": "approved",
                                  "approved_at": now}})
            set_fields["creator_id"] = cr.get("id") or cr.get("_id")
        set_fields["creator_status"] = "approved"
    elif old_role == "creator" and body.new_role != "creator":
        # Demotion from creator — revoke without delete
        await db.podcast_creators.update_one(
            {"user_id": user_id},
            {"$set": {"application_status": "revoked_by_admin",
                          "revoked_at": _now(),
                          "revoked_by_admin_id": admin["user_id"]}})
        set_fields["creator_status"] = "revoked_by_admin"

    await db.users.update_one({"user_id": user_id},
                                              {"$set": set_fields})
    await _audit(db, user_id=user_id, changed_by=admin["user_id"],
                      action="role_change",
                      old_value=old_role, new_value=body.new_role,
                      reason=body.reason)
    fresh = await db.users.find_one({"user_id": user_id})
    return {"ok": True, "user": _user_view(fresh)}


# =====================================================================
# ACTIVATE / DEACTIVATE
# =====================================================================
class StatusBody(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


@admin_users_router.post("/{user_id}/activate")
async def activate_user(user_id: str, body: StatusBody, request: Request,
                                      force: bool = Query(False),
                                      admin: dict = Depends(require_admin)):
    db = request.app.state.db
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(404, {"status": "user_not_found"})
    old_status = target.get("status") or "active"
    if old_status == "active":
        return {"ok": True, "no_op": True, "user": _user_view(target)}
    if old_status == "suspended" and not force:
        raise HTTPException(400,
            {"status": "cannot_reactivate_suspended_without_force",
              "hint": "pass ?force=true with a reason to override"})
    if old_status == "suspended" and not (body.reason or "").strip():
        raise HTTPException(400,
            {"status": "reason_required_for_force_reactivate"})

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"status": "active", "updated_at": _now()},
          "$unset": {"deactivated_at": "", "deactivated_by_admin_id": "",
                          "deactivation_reason": ""}})
    await _audit(db, user_id=user_id, changed_by=admin["user_id"],
                      action="unsuspend" if old_status == "suspended"
                                else "activate",
                      old_value=old_status, new_value="active",
                      reason=body.reason)
    fresh = await db.users.find_one({"user_id": user_id})
    return {"ok": True, "user": _user_view(fresh)}


@admin_users_router.post("/{user_id}/deactivate")
async def deactivate_user(user_id: str, body: StatusBody,
                                          request: Request,
                                          admin: dict = Depends(require_admin)):
    if not (body.reason or "").strip() or len((body.reason or "").strip()) < 5:
        raise HTTPException(400,
            {"status": "reason_required",
              "hint": "Provide at least 5 characters explaining the deactivation."})
    db = request.app.state.db
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(404, {"status": "user_not_found"})

    # Safety rails
    if target["user_id"] == admin["user_id"]:
        raise HTTPException(400, {"status": "cannot_deactivate_self"})
    if target.get("role") == "admin":
        admin_count = await _count_active_admins(db)
        if admin_count <= 1:
            raise HTTPException(400,
                {"status": "cannot_deactivate_last_admin"})

    old_status = target.get("status") or "active"
    now = _now()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"status": "inactive",
                      "deactivated_at": now,
                      "deactivated_by_admin_id": admin["user_id"],
                      "deactivation_reason": body.reason.strip(),
                      "updated_at": now}})
    # Best-effort session invalidation (if sessions collection exists)
    try:
        await db.sessions.delete_many({"user_id": user_id})
    except Exception:
        pass
    await _audit(db, user_id=user_id, changed_by=admin["user_id"],
                      action="deactivate",
                      old_value=old_status, new_value="inactive",
                      reason=body.reason.strip())
    fresh = await db.users.find_one({"user_id": user_id})
    return {"ok": True, "user": _user_view(fresh)}


# =====================================================================
# Index bootstrap (called from server.py startup)
# =====================================================================
async def ensure_phase19a_part5_indexes(db) -> None:
    await db.user_role_audit_log.create_index(
        [("audit_id", 1)], unique=True)
    await db.user_role_audit_log.create_index(
        [("user_id", 1), ("created_at", -1)])
    await db.user_role_audit_log.create_index(
        [("changed_by_admin_id", 1), ("created_at", -1)])
    await db.user_role_audit_log.create_index([("action", 1)])
    # Backfill: ensure every existing user has status="active" set
    await db.users.update_many(
        {"status": {"$exists": False}},
        {"$set": {"status": "active"}})
