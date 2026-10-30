"""Phase 19a Part 5 — Admin user management.

Admin-only surface for listing, role-changing, activating/deactivating
users, with safety rails (cannot demote self, last admin, etc.) and an
append-only audit log.

Auth: every route requires `require_admin` from auth.py.  Mounted under
/api/admin/users so existing ingress rules apply.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                                  Request, UploadFile)
from pydantic import BaseModel, Field

from auth import current_user, require_admin, hash_password, PreferenceVector


logger = logging.getLogger("bigfm.admin_users")

admin_users_router = APIRouter(prefix="/api/admin/users",
                                                tags=["admin_users_phase19a"])


ALLOWED_ROLES = {"user", "listener", "creator", "advertiser",
                          "business_partner", "moderator", "ad_manager",
                          "admin"}
ALLOWED_STATUSES = {"active", "inactive", "suspended"}
ALLOWED_ACTIONS = {"role_change", "activate", "deactivate",
                            "suspend", "unsuspend", "create", "update"}


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
        "must_change_password": bool(u.get("must_change_password")),
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
# CREATE USER (admin-provisioned) + BULK IMPORT + EDIT
# =====================================================================
class CreateUserBody(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    role: str = "user"
    status: str = "active"
    is_premium: bool = False
    market: Optional[str] = None
    send_welcome: bool = False


class EditUserBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    email: Optional[str] = None
    is_premium: Optional[bool] = None


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _password_valid(pw: str) -> bool:
    return bool(pw) and len(pw) >= 8 and bool(re.search(r"\d", pw)) \
              and bool(re.search(r"[A-Za-z]", pw))


def _gen_password() -> str:
    """Random password guaranteed to satisfy letter+digit, len >= 11."""
    pool = string.ascii_letters + string.digits
    return (secrets.choice(string.ascii_uppercase)
                  + secrets.choice(string.ascii_lowercase)
                  + "".join(secrets.choice(pool) for _ in range(8))
                  + secrets.choice(string.digits))


async def _create_one(db, admin_id: str, *, email, name, password, role,
                                    status, is_premium, market):
    """Core provisioning used by both single-create and bulk import.
    Returns (ok, result). result is the user view on success, else
    {"error": <code>}."""
    role = (role or "user").strip()
    status = (status or "active").strip()
    if role not in ALLOWED_ROLES:
        return False, {"error": "invalid_role"}
    if status not in ALLOWED_STATUSES:
        return False, {"error": "invalid_status"}
    email = (email or "").lower().strip()
    if not _EMAIL_RE.match(email):
        return False, {"error": "invalid_email"}
    if not name or not name.strip():
        return False, {"error": "missing_name"}
    if not _password_valid(password):
        return False, {"error": "weak_password"}
    if await db.users.find_one({"email": email}, {"_id": 0}):
        return False, {"error": "email_exists"}
    now = _now()
    user_id = _new_id("user", 16)
    doc = {
        "user_id": user_id, "email": email, "name": name.strip(),
        "picture": None, "auth_provider": "email",
        "password_hash": hash_password(password),
        "role": role, "status": status, "is_premium": bool(is_premium),
        "market": market, "onboarding_complete": True,
        "created_by_admin_id": admin_id,
        "preference_vector": PreferenceVector().model_dump(),
        "created_at": now, "last_login_at": None,
    }
    await db.users.insert_one(doc)
    await _audit(db, user_id=user_id, changed_by=admin_id, action="create",
                      old_value=None, new_value=role,
                      reason=f"admin-created ({role})")
    fresh = await db.users.find_one({"user_id": user_id})
    return True, _user_view(fresh)


async def _send_welcome_email(db, request, *, user_id, email, name):
    """Email a single-use 'set your password' link (valid 7 days) plus a
    login link.  Falls back to a visible log line when Mailgun isn't live."""
    try:
        from auth import _ensure_reset_indexes, _frontend_base_url
        await _ensure_reset_indexes(db)
        token = secrets.token_urlsafe(32)
        now = _now()
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": user_id, "email": email,
            "created_at": now, "expires_at": now + timedelta(days=7),
            "used": False, "kind": "welcome",
        })
        base = _frontend_base_url(request)
        set_url = f"{base}/reset-password?token={token}"
        login_url = f"{base}/login"
        sent, err = False, None
        try:
            from services.mailgun_client import send_email, is_live
            if is_live():
                subject = "Welcome to FUUSIC — set your password"
                safe_name = (name or "there").strip() or "there"
                html = (
                    f'<div style="font-family:system-ui,sans-serif;'
                    f'line-height:1.5;color:#0f172a">'
                    f'<h2 style="margin:0 0 8px">Welcome to FUUSIC, '
                    f'{safe_name}!</h2>'
                    f'<p>An account has been created for you. To get '
                    f'started, set your own password — then sign in with '
                    f'<b>{email}</b>.</p>'
                    f'<p><a href="{set_url}" style="display:inline-block;'
                    f'background:#d946ef;color:#fff;padding:12px 22px;'
                    f'border-radius:9999px;text-decoration:none;'
                    f'font-weight:700">Set your password</a></p>'
                    f'<p style="color:#64748b;font-size:12px;margin-top:16px">'
                    f'This link expires in 7 days and can be used once. '
                    f'Already set it? <a href="{login_url}">Sign in</a>.</p>'
                    f'<p style="color:#94a3b8;font-size:11px">Or paste: '
                    f'<span style="word-break:break-all">{set_url}</span>'
                    f'</p></div>'
                )
                text = (f"Welcome to FUUSIC!\nSet your password: {set_url}\n"
                              f"Then sign in at {login_url} with {email}.\n"
                              f"Link expires in 7 days, single use.")
                resp = send_email(email, subject, html, text=text,
                                                      tags=["welcome"])
                sent = bool(resp.get("ok"))
                err = resp.get("error")
        except Exception as e:
            err = f"exception:{type(e).__name__}"
        if not sent:
            logger.warning("[admin_users] MOCKED welcome email to=%s — "
                                      "deliver set-password URL manually: %s",
                                      email, set_url)
        await db.password_reset_tokens.update_one(
            {"token": token},
            {"$set": {"email_sent": sent, "email_error": err,
                              "reset_url_debug": set_url}})
        return {"sent": sent, "error": err, "set_password_url": set_url}
    except Exception as e:
        logger.warning("[admin_users] welcome email failed: %s", e)
        return {"sent": False, "error": str(e), "set_password_url": None}


@admin_users_router.post("")
@admin_users_router.post("/")
async def create_user(body: CreateUserBody, request: Request,
                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    ok, res = await _create_one(
        db, admin["user_id"], email=body.email, name=body.name,
        password=body.password, role=body.role, status=body.status,
        is_premium=body.is_premium, market=body.market)
    if not ok:
        code = res["error"]
        raise HTTPException(409 if code == "email_exists" else 400,
                                            {"status": code})
    out = {"ok": True, "user": res}
    if body.send_welcome:
        out["welcome_email"] = await _send_welcome_email(
            db, request, user_id=res["user_id"], email=res["email"],
            name=res["name"])
    return out


@admin_users_router.post("/bulk")
async def bulk_create_users(request: Request,
                                                file: UploadFile = File(...),
                                                send_welcome: bool = Form(False),
                                                admin: dict = Depends(require_admin)):
    """Create many users from a CSV. Columns (case-insensitive):
    email (required), name (required), role, password (optional — a random
    one is generated if blank), premium/is_premium, market, status."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except Exception:
        text = raw.decode("latin-1", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, {"status": "empty_or_invalid_csv"})
    norm = {(f or "").strip().lower(): f for f in reader.fieldnames}
    if "email" not in norm or "name" not in norm:
        raise HTTPException(400, {"status": "missing_columns",
                                                    "required": ["email", "name"],
                                                    "found": reader.fieldnames})

    def pick(row, key):
        src = norm.get(key)
        return (row.get(src) or "").strip() if src else ""

    db = request.app.state.db
    results, created = [], 0
    for idx, row in enumerate(reader, start=2):   # row 1 = header
        email = pick(row, "email")
        if not email and not any((v or "").strip() for v in row.values()):
            continue    # skip fully blank line
        name = pick(row, "name")
        role = pick(row, "role") or "user"
        status = pick(row, "status") or "active"
        market = pick(row, "market") or None
        prem_raw = (pick(row, "premium") or pick(row, "is_premium")).lower()
        is_premium = prem_raw in ("1", "true", "yes", "y", "premium")
        password = pick(row, "password") or _gen_password()
        ok, res = await _create_one(
            db, admin["user_id"], email=email, name=name, password=password,
            role=role, status=status, is_premium=is_premium, market=market)
        if ok:
            created += 1
            if send_welcome:
                await _send_welcome_email(db, request, user_id=res["user_id"],
                                                              email=res["email"], name=res["name"])
            results.append({"row": idx, "email": email, "status": "created",
                                      "role": res["role"]})
        else:
            results.append({"row": idx, "email": email, "status": "error",
                                      "error": res["error"]})
    return {"ok": True, "created": created,
                  "failed": len(results) - created, "total": len(results),
                  "results": results}


@admin_users_router.patch("/{user_id}")
async def update_user(user_id: str, body: EditUserBody, request: Request,
                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(404, {"status": "user_not_found"})
    updates: dict = {}
    changed = []
    if body.name is not None and body.name.strip() != (user.get("name") or ""):
        updates["name"] = body.name.strip()
        changed.append("name")
    if body.email is not None:
        new_email = body.email.lower().strip()
        if not _EMAIL_RE.match(new_email):
            raise HTTPException(400, {"status": "invalid_email"})
        if new_email != (user.get("email") or ""):
            dupe = await db.users.find_one(
                {"email": new_email, "user_id": {"$ne": user_id}}, {"_id": 0})
            if dupe:
                raise HTTPException(409, {"status": "email_exists"})
            updates["email"] = new_email
            changed.append("email")
    if body.is_premium is not None \
            and bool(body.is_premium) != bool(user.get("is_premium")):
        updates["is_premium"] = bool(body.is_premium)
        changed.append("premium")
    if not updates:
        return {"ok": True, "user": _user_view(user), "changed": []}
    updates["updated_at"] = _now()
    await db.users.update_one({"user_id": user_id}, {"$set": updates})
    await _audit(db, user_id=user_id, changed_by=admin["user_id"],
                      action="update", old_value=None,
                      new_value=", ".join(changed),
                      reason=f"admin-edited: {', '.join(changed)}")
    fresh = await db.users.find_one({"user_id": user_id})
    return {"ok": True, "user": _user_view(fresh), "changed": changed}


@admin_users_router.post("/{user_id}/resend-welcome")
async def resend_welcome(user_id: str, request: Request,
                                          admin: dict = Depends(require_admin)):
    db = request.app.state.db
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(404, {"status": "user_not_found"})
    res = await _send_welcome_email(db, request, user_id=user_id,
                                                          email=user["email"],
                                                          name=user.get("name"))
    await _audit(db, user_id=user_id, changed_by=admin["user_id"],
                      action="update", old_value=None, new_value="resend_welcome",
                      reason="resent welcome / set-password email")
    return {"ok": True, "welcome_email": res}


class ForceResetBody(BaseModel):
    require: bool = True


@admin_users_router.post("/{user_id}/force-password-reset")
async def force_password_reset(user_id: str, request: Request,
                                                    body: ForceResetBody = ForceResetBody(),
                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(404, {"status": "user_not_found"})
    require = bool(body.require)
    await db.users.update_one({"user_id": user_id},
        {"$set": {"must_change_password": require}})
    await _audit(db, user_id=user_id, changed_by=admin["user_id"],
                      action="update", old_value=None,
                      new_value="force_reset_on" if require else "force_reset_off",
                      reason="require password change on next sign-in"
                                  if require else "cleared forced password change")
    fresh = await db.users.find_one({"user_id": user_id})
    return {"ok": True, "user": _user_view(fresh)}


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
