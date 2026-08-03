"""Phase Π.1 + Π.2 + Π.5 — admin system health + employee tools.

Endpoints:
    GET  /api/admin/system/health                        — kill-switch + key-presence audit
    POST /api/admin/users/{user_id}/flag-employee  — flag employee, auto-seed sample data
    POST /api/feedback/submit                              — employee-or-admin feedback submission
    GET  /api/admin/feedback                                — paginated feedback log
    PATCH /api/admin/feedback/{id}                      — flip resolved status
    GET  /api/admin/revenue/this-month                — Π.6 ad-spend revenue tile
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user

log = logging.getLogger("bigfm.admin_system")

router = APIRouter(tags=["admin-system"])


# ─────────────── Π.4 — ErrorBoundary telemetry sink ────────────
class _TelemetryBody(BaseModel):
    message:                  Optional[str] = Field(None, max_length=2000)
    stack:                      Optional[str] = Field(None, max_length=8000)
    component_stack: Optional[str] = Field(None, max_length=8000)
    url:                          Optional[str] = Field(None, max_length=600)
    user_agent:              Optional[str] = Field(None, max_length=600)


@router.post("/api/telemetry/error")
async def telemetry_error(body: _TelemetryBody, request: Request) -> dict:
    """Public.  React ErrorBoundary posts unhandled render errors here.
    Persisted to `client_errors` for ops review.  Anonymous-friendly —
    if the user is logged in we attach their user_id."""
    db = request.app.state.db
    err_id = f"err_{uuid.uuid4().hex[:14]}"
    uid = None
    # Cheap user-id resolution — try to read the session cookie.
    try:
        from auth import current_user
        u = await current_user(request)
        uid = u.get("user_id") if u else None
    except Exception:
        uid = None
    doc = {
        "_id":                          err_id,
        "user_id":                  uid,
        "message":                  body.message,
        "stack":                      body.stack,
        "component_stack": body.component_stack,
        "url":                          body.url,
        "user_agent":            body.user_agent,
        "ip":                              (request.client.host if request.client else None),
        "created_at":            datetime.now(timezone.utc),
    }
    await db.client_errors.insert_one(doc)
    log.warning("[client_error] %s %s", err_id, (body.message or "")[:120])
    return {"ok": True, "error_id": err_id}


def _is_admin(u: dict) -> bool:
    if not u: return False
    return (u.get("role") == "admin" or u.get("is_admin")
                  or "admin" in (u.get("roles") or []))


def _is_employee_or_admin(u: dict) -> bool:
    if not u: return False
    return _is_admin(u) or bool(u.get("is_employee"))


def _envbool(name: str, default: bool) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


# ─────────────────── Π.1 — kill-switch audit ──────────────────
@router.get("/api/admin/system/health")
async def system_health(request: Request,
                                                  user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db

    # Aggregate key presence (NOT values).
    keys = {
        "openai_text":              bool(os.environ.get("EMERGENT_LLM_KEY")
                                                                      or os.environ.get("OPENAI_API_KEY")),
        "openai_image":            bool(os.environ.get("OPENAI_IMAGE_API_KEY")),
        "elevenlabs":                  bool(os.environ.get("ELEVENLABS_API_KEY")),
        "newsapi":                          bool(os.environ.get("NEWSAPI_API_KEY")),
        "mailgun":                          bool(os.environ.get("MAILGUN_API_KEY")),
        "mailgun_webhook":      bool(os.environ.get("MAILGUN_WEBHOOK_SIGNING_KEY")
                                                                      or os.environ.get("MAILGUN_WEBHOOK_SECRET")),
        "stripe_secret":              bool(os.environ.get("STRIPE_SECRET_KEY")),
        "stripe_publishable": bool(os.environ.get("STRIPE_PUBLISHABLE_KEY")),
        "stripe_webhook":          bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
        "google_maps":                bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
        "google_routes":          bool(os.environ.get("GOOGLE_ROUTES_API_KEY")),
        "google_places":          bool(os.environ.get("GOOGLE_PLACES_API_KEY")),
        "google_weather":          bool(os.environ.get("GOOGLE_WEATHER_API_KEY")),
        "predexon":                      bool(os.environ.get("PREDEXON_API_KEY")),
        "tigris":                          bool(os.environ.get("TIGRIS_ACCESS_KEY_ID")),
        "livekit":                          bool(os.environ.get("LIVEKIT_API_KEY")),
    }

    # Production-safe kill-switch defaults.
    dev_meta = _envbool("BIGFM_DEV_ESCAPE_HATCHES", False)
    switches = {
        "ENV":                                                  os.environ.get("ENV") or "unset",
        "BIGFM_DEV_ESCAPE_HATCHES":      dev_meta,
        "BIGFM_DEBUG_GEO":                              _envbool("BIGFM_DEBUG_GEO", False),
        "BIGCOIN_LEGACY_DUAL_WRITE":  _envbool("BIGCOIN_LEGACY_DUAL_WRITE", False),
        "MAILGUN_WEBHOOK_VERIFY_SIGNATURE":
                                                                              _envbool("MAILGUN_WEBHOOK_VERIFY_SIGNATURE", True),
        "STRIPE_WEBHOOK_VERIFY_SIGNATURE":
                                                                              _envbool("STRIPE_WEBHOOK_VERIFY_SIGNATURE", True),
        "STRIPE_MODE":                                  os.environ.get("STRIPE_MODE", "mock"),
        "INVITE_EMAIL_LIVE":                  _envbool("INVITE_EMAIL_LIVE", False),
        "NEWS_PROVIDER":                          os.environ.get("NEWS_PROVIDER", "newsapi"),
    }

    # Issue list — anything that's misconfigured for prod.
    issues = []
    if os.environ.get("ENV") != "production":
        issues.append({"severity": "info", "code": "env_not_prod",
                                      "msg": "ENV is not 'production'; banner audits assume dev."})
    if not switches["MAILGUN_WEBHOOK_VERIFY_SIGNATURE"]:
        issues.append({"severity": "high",
                                      "code": "mailgun_webhook_signature_disabled",
                                      "msg": "Mailgun webhook signature verification is OFF "
                                                  "— DEV ONLY.  Flip to 1 once signing key is set."})
    if not switches["STRIPE_WEBHOOK_VERIFY_SIGNATURE"]:
        issues.append({"severity": "high",
                                      "code": "stripe_webhook_signature_disabled",
                                      "msg": "Stripe webhook signature verification is OFF "
                                                  "— DEV ONLY.  Flip to 1 once whsec_… is set."})
    if "*" in (os.environ.get("CORS_ORIGINS") or ""):
        issues.append({"severity": "high",
                                      "code": "cors_wildcard",
                                      "msg": "CORS_ORIGINS contains '*' — lock down to prod hosts."})
    if not keys["stripe_webhook"]:
        issues.append({"severity": "high",
                                      "code": "stripe_webhook_secret_missing",
                                      "msg": "STRIPE_WEBHOOK_SECRET is empty."})
    if not keys["mailgun_webhook"]:
        issues.append({"severity": "high",
                                      "code": "mailgun_webhook_signing_key_missing",
                                      "msg": "MAILGUN_WEBHOOK_SIGNING_KEY is empty."})
    if not keys["google_maps"]:
        issues.append({"severity": "info",
                                      "code": "google_maps_missing",
                                      "msg": "Phase H (commute) is BLOCKED — Google keys absent."})

    # Background task status (best-effort).
    bg = {}
    for attr in ("badge_cron_task", "dunning_cron_task", "unlock_sweep_task",
                            "webhook_worker_task", "badge_sweep_task",
                            "predict_win_sweep_task"):
        t = getattr(request.app.state, attr, None)
        bg[attr] = ("running" if t and not t.done()
                              else "done" if t and t.done()
                              else "not_started")

    # Counts (cheap).
    counts = {
        "users":                          await db.users.estimated_document_count(),
        "businesses":              await db.businesses.estimated_document_count(),
        "tips":                              await db.tips.estimated_document_count(),
        "payment_intents_v2": await db.payment_intents_v2.estimated_document_count(),
        "mail_events":              await db.mail_events.estimated_document_count(),
        "points_ledger":          await db.points_ledger.estimated_document_count(),
    }

    # ─── Phase Π+2 — asset migration / Tigris fallback CDN ───
    asset_migration = await _asset_migration_snapshot(db)

    return {
        "ts":                          datetime.now(timezone.utc).isoformat(),
        "keys_present":      keys,
        "kill_switches": switches,
        "issues":                  issues,
        "background_tasks": bg,
        "counts":                  counts,
        "asset_migration": asset_migration,
        "production_ready": not any(i["severity"] == "high" for i in issues),
    }


async def _asset_migration_snapshot(db) -> dict:
    """Surface the Tigris migration state + fallback-CDN runtime stats
    on the admin health page.  Reads the `migration_state` doc written
    by `scripts.migrate_local_to_tigris.py` (if it ever ran) AND
    captures the in-process fallback counters from
    `services.tigris_url_resolver`.

    The block is structured so the UI can render a single traffic-light
    strip:  green when migration has run AND fallback has any hits OR
    no fallback hits but bucket configured, yellow when migration never
    ran, red when Tigris credentials are missing.
    """
    out: dict = {
        "status":                      "unknown",
        "tigris_configured": False,
        "tigris_backend":      None,
        "bucket":                      os.environ.get("TIGRIS_BUCKET"),
        "endpoint":                  os.environ.get("TIGRIS_ENDPOINT_URL"),
        "last_run_at":          None,
        "static_summary":  None,
        "tracks_summary": None,
        "fallback":                  {"today": 0, "lifetime": 0,
                                                  "tracked_days": 0, "cache_entries": 0,
                                                  "cache_ttl_seconds": 0},
        "tigris_url_strategy": "presigned_7day",
        "notes": "Tigris bucket is private; fallback CDN issues 7-day "
                          "presigned URLs.  Migration is one-shot; new uploads "
                          "go directly to Tigris via STORAGE_BACKEND=tigris.",
    }
    # Are Tigris creds present?
    out["tigris_configured"] = bool(
        os.environ.get("TIGRIS_ACCESS_KEY_ID")
        and os.environ.get("TIGRIS_SECRET_ACCESS_KEY")
        and os.environ.get("TIGRIS_BUCKET")
        and os.environ.get("TIGRIS_ENDPOINT_URL"))
    out["tigris_backend"] = (os.environ.get("STORAGE_BACKEND") or "local").lower()

    # Migration state doc (written by scripts.migrate_local_to_tigris).
    try:
        doc = await db.migration_state.find_one({"_id": "tigris_assets"})
    except Exception as e:
        log.warning("[asset_migration] mongo read failed: %s", e)
        doc = None
    if doc:
        ts = doc.get("last_run_at")
        out["last_run_at"] = (ts.isoformat() if isinstance(ts, datetime)
                                              else ts)
        s = doc.get("static_summary") or {}
        if s:
            out["static_summary"] = {
                "uploaded":              int(s.get("uploaded") or 0),
                "skipped":                  int(s.get("skipped") or 0),
                "failed":                    int(s.get("failed") or 0),
                "bytes_uploaded": int(s.get("bytes_uploaded") or 0),
                "per_dir_count":  len(s.get("per_dir") or []),
            }
        t = doc.get("tracks_summary") or {}
        if t:
            out["tracks_summary"] = {
                "migrated":                              int(t.get("migrated") or 0),
                "skipped_already_migrated": int(t.get("skipped_already_migrated") or 0),
                "missing_local_file":          int(t.get("missing_local_file") or 0),
                "failed_count":                      len(t.get("failed") or []),
            }

    # In-process fallback counters.
    try:
        from services.tigris_url_resolver import fallback_hits_summary
        out["fallback"] = fallback_hits_summary()
    except Exception as e:
        log.warning("[asset_migration] fallback summary failed: %s", e)

    # Status classification (drives the traffic-light strip in UI).
    if not out["tigris_configured"]:
        out["status"] = "red"
    elif not doc:
        out["status"] = "yellow"
    else:
        out["status"] = "green"
    return out


# ─────────── Π.5 — employee flag + auto-seed ─────────────────
class _FlagEmployeeBody(BaseModel):
    enable: bool = True


@router.post("/api/admin/users/{user_id}/flag-employee")
async def flag_employee(user_id: str, body: _FlagEmployeeBody,
                                                request: Request,
                                                user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(404, "user_not_found")

    now = datetime.now(timezone.utc)
    update: dict = {"is_employee": bool(body.enable),
                                  "employee_flagged_at": now}
    await db.users.update_one({"user_id": user_id}, {"$set": update})

    seeded = {"pts": 0, "badges": 0, "city_stamps": 0}
    if body.enable and not target.get("employee_seeded"):
        try:
            # Seed 500 pts via PointsService (idempotent on user-id key).
            from services.points_service import PointsService
            res = await PointsService(db).award(
                user_id=user_id, delta=500,
                source="employee_welcome",
                metadata={"flagged_by": user["user_id"]},
                idempotency_key=f"emp_welcome_{user_id}")
            seeded["pts"] = 500 if res.ok else 0
        except Exception as e:
            log.warning("[flag_employee] seed pts failed: %s", e)
        # Seed 3 badges (idempotent inserts).
        for bid in ("first_hour", "first_share", "first_prediction"):
            await db.user_badges.update_one(
                {"user_id": user_id, "badge_id": bid},
                {"$setOnInsert": {"awarded_at": now, "source": "employee_seed"}},
                upsert=True)
            seeded["badges"] += 1
        # Seed Dallas city stamp (idempotent).
        await db.user_city_stamps.update_one(
            {"user_id": user_id, "city_id": "dallas_tx"},
            {"$setOnInsert": {"awarded_at": now, "source": "employee_seed",
                                            "name": "Dallas"}}, upsert=True)
        seeded["city_stamps"] = 1
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"employee_seeded": True,
                              "employee_seeded_at": now}})

    log.info("[flag_employee] %s enable=%s seeded=%s by=%s",
                  user_id, body.enable, seeded, user["user_id"])
    return {"ok": True, "user_id": user_id, "is_employee": bool(body.enable),
                  "seeded": seeded}


# ─────────── Π.5 — feedback widget ────────────────────────────
_FEEDBACK_CATEGORIES = ("bug", "suggestion", "praise", "other")


class _FeedbackBody(BaseModel):
    category: str = Field(..., min_length=1, max_length=24)
    text:          str = Field(..., min_length=4, max_length=2000)
    screenshot_data_url: Optional[str] = Field(None, max_length=2_000_000)
    current_url:                    Optional[str] = Field(None, max_length=600)
    current_user_agent:      Optional[str] = Field(None, max_length=600)


@router.post("/api/feedback/submit")
async def submit_feedback(body: _FeedbackBody, request: Request,
                                                          user: dict = Depends(current_user)) -> dict:
    if not _is_employee_or_admin(user):
        raise HTTPException(403, "employee_or_admin_required")
    if body.category not in _FEEDBACK_CATEGORIES:
        raise HTTPException(400, {"code": "invalid_category",
                                                          "allowed": list(_FEEDBACK_CATEGORIES)})
    db = request.app.state.db
    fid = f"fb_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id":                              fid,
        "user_id":                      user["user_id"],
        "user_email":                user.get("email"),
        "user_name":                  user.get("name"),
        "is_employee":              bool(user.get("is_employee")),
        "is_admin":                      _is_admin(user),
        "category":                  body.category,
        "text":                              body.text.strip(),
        "current_url":              body.current_url,
        "current_user_agent": body.current_user_agent,
        # Screenshot — store inline (data URL) up to ~2MB.  Larger
        # screenshots will need object-storage migration in a follow-up.
        "screenshot_data_url": body.screenshot_data_url,
        "screenshot_size":      (len(body.screenshot_data_url or "") if
                                                  body.screenshot_data_url else 0),
        "status":                          "open",
        "created_at":                datetime.now(timezone.utc),
    }
    await db.employee_feedback.insert_one(doc)
    log.info("[feedback] %s %s %s",
                  user["user_id"], body.category, fid)
    return {"ok": True, "feedback_id": fid}


@router.get("/api/admin/feedback")
async def list_feedback(request: Request,
                                                status: str = Query("open", pattern="^(open|resolved|all)$"),
                                                category: Optional[str] = None,
                                                limit: int = Query(50, ge=1, le=200),
                                                user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    q: dict = {}
    if status != "all": q["status"] = status
    if category: q["category"] = category
    items = []
    async for d in db.employee_feedback.find(q).sort(
            "created_at", -1).limit(int(limit)):
        d["created_at"] = (d["created_at"].isoformat()
                                          if isinstance(d.get("created_at"), datetime)
                                          else d.get("created_at"))
        # Don't echo the full screenshot in the list — only its size.
        d.pop("screenshot_data_url", None)
        items.append(d)
    return {"status": status, "count": len(items), "items": items}


class _ResolveBody(BaseModel):
    status: str = Field("resolved", pattern="^(open|resolved)$")
    note: Optional[str] = Field(None, max_length=1000)


@router.patch("/api/admin/feedback/{fid}")
async def update_feedback(fid: str, body: _ResolveBody, request: Request,
                                                        user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    res = await db.employee_feedback.update_one(
        {"_id": fid},
        {"$set": {"status": body.status,
                          "resolved_by": user["user_id"] if body.status == "resolved" else None,
                          "resolved_at": (datetime.now(timezone.utc)
                                                          if body.status == "resolved" else None),
                          "resolution_note": body.note,
                          "updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(404, "feedback_not_found")
    return {"ok": True, "feedback_id": fid, "status": body.status}


@router.get("/api/admin/feedback/{fid}")
async def get_feedback(fid: str, request: Request,
                                              user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    d = await db.employee_feedback.find_one({"_id": fid})
    if not d: raise HTTPException(404, "feedback_not_found")
    d["created_at"] = (d["created_at"].isoformat()
                                      if isinstance(d.get("created_at"), datetime)
                                      else d.get("created_at"))
    return d


# ─────────── Π.6 — admin revenue tile ─────────────────────────
@router.get("/api/admin/revenue/this-month")
async def revenue_this_month(request: Request,
                                                                  user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)

    async def _sum_paid(since, until=None):
        match: dict = {"status": "paid", "paid_at": {"$gte": since}}
        if until: match["paid_at"]["$lt"] = until
        pipe = [{"$match": match},
                      {"$group": {"_id": "$currency",
                                          "total_cents": {"$sum": "$amount_paid_cents"},
                                          "count": {"$sum": 1}}}]
        out: list[dict] = []
        async for d in db.payment_intents_v2.aggregate(pipe):
            out.append({"currency": d["_id"], "total_cents": int(d["total_cents"]),
                              "count": int(d["count"])})
        return out

    this_month = await _sum_paid(month_start)
    last_month = await _sum_paid(last_month_start, month_start)
    return {
        "ts":                      now.isoformat(),
        "this_month_start": month_start.isoformat(),
        "this_month":      this_month,
        "last_month":      last_month,
    }
