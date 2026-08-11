"""Phase FUN.1 — Flagship (FunAsia) stations router.

Public endpoints for surfacing + admin CRUD for feature management."""
from __future__ import annotations

import logging
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from auth import require_admin
from services.flagship_station_service import (
    ensure_flagship_indexes, get_flagship_by_slug,
    health_check_all_flagships, list_flagships, set_flagship,
    unset_flagship, seed_funasia_flagships,
    search_flagships_by_query,
)

logger = logging.getLogger("bigfm.flagship.routes")
router = APIRouter(tags=["flagship-stations"])


class FeatureBody(BaseModel):
    priority:      int = 100
    categories: list[str] = []


# ─── Public ───────────────────────────────────────────
@router.get("/api/stations/flagship")
async def list_flagship_stations(request: Request,
                                                                          category: Optional[str] = None,
                                                                          matches_language: Optional[str] = None,
                                                                          matches_city: Optional[str] = None,
                                                                          region: Optional[str] = None,
                                                                          limit: int = 50):
    """Phase FUN.1-v2: When `region` is passed, filter to that region's
    flagships only.  When omitted, resolves the caller's region via
    `get_user_region` and returns region-matched flagships first, then
    other-region flagships (sorted via `sort_with_flagship_priority`)."""
    db = request.app.state.db
    items = await list_flagships(
        db, category=category, matches_language=matches_language,
        matches_city=matches_city, limit=limit)
    # If explicit region filter requested, hard-filter.
    if region:
        region = region.upper()
        items = [s for s in items if s.get("flagship_region") == region]
    else:
        # Resolve caller's region and apply priority sort.
        from services.geo_flagship import get_user_region, sort_with_flagship_priority
        # Try to resolve user via optional auth (public endpoint).
        try:
            from auth import current_user_optional
            user = await current_user_optional(request)
        except Exception:
            user = None
        user_region = await get_user_region(user, request)
        items = sort_with_flagship_priority(items, user_region)
    return {"items": items, "count": len(items)}


@router.get("/api/stations/priority")
async def list_priority_stations(request: Request, limit: int = 30):
    """Phase FUN.1-v2: Non-flagship Dubai stations tagged with is_priority."""
    db = request.app.state.db
    docs = await db.imported_radio_stations.find(
        {"is_priority": True, "is_flagship": {"$ne": True}, "dubai_hidden": {"$ne": True}}
    ).sort([("name", 1)]).to_list(limit)
    items = []
    for d in docs:
        out = {k: v for k, v in d.items() if k != "_id"}
        for k, v in list(out.items()):
            if hasattr(v, "isoformat"):
                out[k] = v.isoformat()
        items.append(out)
    return {"items": items, "count": len(items)}


@router.get("/api/stations/flagship/search")
async def search_flagship_stations(request: Request, q: str,
                                                                          limit: int = 5):
    db = request.app.state.db
    items = await search_flagships_by_query(db, query=q, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/stations/flagship/{slug}")
async def flagship_detail_by_slug(slug: str, request: Request):
    db = request.app.state.db
    d = await get_flagship_by_slug(db, slug)
    if not d:
        raise HTTPException(404, {"code": "flagship_not_found"})
    return d


# ─── Admin ──────────────────────────────────────────
@router.post("/api/admin/stations/{station_id}/feature")
async def admin_feature_station(station_id: str, body: FeatureBody,
                                                                          request: Request,
                                                                          admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await set_flagship(
            db, station_id=station_id, priority=body.priority,
            categories=body.categories, admin_user_id=admin["user_id"])
    except LookupError:
        raise HTTPException(404, {"code": "station_not_found"})


@router.post("/api/admin/stations/{station_id}/unfeature")
async def admin_unfeature_station(station_id: str, request: Request,
                                                                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await unset_flagship(
            db, station_id=station_id, admin_user_id=admin["user_id"])
    except LookupError:
        raise HTTPException(404, {"code": "station_not_found"})


@router.post("/api/admin/stations/flagship/seed")
async def admin_reseed_flagships(request: Request,
                                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    return await seed_funasia_flagships(db)


@router.post("/api/admin/stations/flagship/health-check")
async def admin_run_health_check(request: Request,
                                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    return await health_check_all_flagships(db)


@router.get("/api/admin/stations/flagship")
async def admin_list_flagships(request: Request,
                                                                          admin: dict = Depends(require_admin)):
    """Admin queue — same as public /flagship but returns internal-only
    fields (health status, alerts count)."""
    db = request.app.state.db
    items = await list_flagships(db, limit=100)
    # Enrich with unresolved-alerts count per station.
    for item in items:
        item["_unresolved_alerts"] = await db.flagship_alerts.count_documents({
            "station_id": item.get("id"), "resolved": False,
        })
    return {"items": items, "count": len(items)}


# ─── Phase FUN.1.3 — Admin logo upload ─────────────────
#
# Persists an operator-branded logo under
# `/app/backend/static/flagship_logos/{slug}.{ext}` and updates
# `imported_radio_stations.logo_url` + `.favicon` in one atomic write.
# Accepts PNG, WEBP, JPG/JPEG, SVG.  ≤ 2 MB.

_LOGO_DIR = Path("/app/backend/static/flagship_logos")
_LOGO_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED_LOGO_EXT = {"png": "image/png",
                                                      "webp": "image/webp",
                                                      "jpg": "image/jpeg",
                                                      "jpeg": "image/jpeg",
                                                      "svg": "image/svg+xml"}

_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


def _sanitize_slug(slug: Optional[str]) -> str:
    slug = (slug or "").strip().lower()
    slug = re.sub(r"[^a-z0-9\-]+", "-", slug).strip("-")
    if not slug:
        raise HTTPException(400, {"code": "bad_slug"})
    return slug


@router.post("/api/admin/stations/{station_id}/logo",
                          description=("Upload an operator-branded flagship logo. "
                                                          "Accepts PNG/WEBP/JPG/SVG ≤ 2 MB.  Persists to "
                                                          "`/app/backend/static/flagship_logos/{slug}.{ext}` "
                                                          "and updates the station's `logo_url` + `favicon`."))
async def admin_upload_station_logo(
    station_id: str,
    request: Request,
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin),
):
    db = request.app.state.db
    station = await db.imported_radio_stations.find_one({"id": station_id})
    if not station:
        raise HTTPException(404, {"code": "station_not_found"})

    # Determine extension (trust filename first, then content-type).
    filename = (file.filename or "").lower()
    ext: Optional[str] = None
    for candidate in _ALLOWED_LOGO_EXT:
        if filename.endswith("." + candidate):
            ext = "jpg" if candidate == "jpeg" else candidate
            break
    if ext is None:
        # Fall back to content-type.
        ct = (file.content_type or "").lower()
        for c_ext, c_ct in _ALLOWED_LOGO_EXT.items():
            if ct == c_ct:
                ext = "jpg" if c_ext == "jpeg" else c_ext
                break
    if ext is None:
        raise HTTPException(400, {"code": "unsupported_type",
                                                                  "allowed": sorted(set(_ALLOWED_LOGO_EXT.values()))})

    data = await file.read()
    if not data:
        raise HTTPException(400, {"code": "empty_file"})
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(413, {"code": "file_too_large",
                                                                  "max_bytes": _MAX_LOGO_BYTES})

    # Persist under `{slug}.{ext}`, sweeping any stale extension variants
    # of the same slug (a station going from .webp → .png shouldn't leave
    # a ghost file on disk).
    slug = _sanitize_slug(station.get("flagship_slug") or station_id)
    for other_ext in _ALLOWED_LOGO_EXT:
        candidate = _LOGO_DIR / f"{slug}.{other_ext}"
        if candidate.exists() and other_ext != ext:
            try: candidate.unlink()
            except Exception: pass

    out_path = _LOGO_DIR / f"{slug}.{ext}"
    out_path.write_bytes(data)

    logo_url = f"/api/static/flagship_logos/{slug}.{ext}"
    await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"logo_url": logo_url,
                              "favicon":    logo_url,
                              "logo_uploaded_by":    admin.get("user_id"),
                              "logo_uploaded_at":   __import__("datetime")
                                                                                    .datetime.now(__import__("datetime").timezone.utc)
                                                                                    .isoformat()}},
    )
    logger.info("[flagship-logo] station=%s slug=%s ext=%s bytes=%d",
                                station_id, slug, ext, len(data))
    return {"ok": True, "station_id": station_id, "slug": slug,
                        "logo_url": logo_url, "bytes": len(data), "ext": ext}


# ═══════════════════════════════════════════════════════════════════
# Phase FLAGADMIN.1 — Full Flagship CRUD + Pre-roll Parity
# ═══════════════════════════════════════════════════════════════════
#
# Motivation: prior to this phase, flagship stations could only be
# managed by DB-side seed scripts.  Admins now get a full lifecycle:
# Create · Update · Delete (soft/hard).  Every write is audit-logged
# in `station_admin_audit` for post-hoc traceability.
#
# Pre-roll parity: flagship rows already flow through the same
# `select_ad_chain_for_play` gate as community rows — there is no
# `is_flagship` bypass anywhere in `preroll_ad_service.py`.  The new
# `preroll_enabled` field (default True; enforced in `preroll_ads.py`)
# lets admins toggle preroll per-station if a partnership requires it.


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_station_id() -> str:
    """FLAGADMIN-created flagship IDs share the `imp_` prefix so they
    remain eligible for the pre-roll pipeline (which only fires on
    `imp_*` stations).  The `imp_flg_` sub-prefix distinguishes
    admin-created flagships from seeded ones (`imp_fun_*`)."""
    return f"imp_flg_{secrets.token_hex(6)}"


def _sanitize_flagship_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    slug = re.sub(r"[^a-z0-9\-]+", "-", slug).strip("-")
    if not slug:
        raise HTTPException(400, {"code": "bad_slug"})
    return slug[:64]


def _validate_stream_url(url: str) -> Dict[str, Any]:
    """Run a HEAD-style Range probe via curl (subprocess) against the
    upstream stream URL.  Returns a dict with `ok`, `status_code`,
    and `error`.

    We deliberately use `curl -sI -H "Range: bytes=0-1024"` because
    live-radio endpoints often reject plain HEAD but honor Range GETs
    with a 206.  Both 2xx and 3xx are treated as healthy.  Timeout 5s.

    Non-blocking: a failure never rejects the save — the caller can
    surface a warning and flip `needs_stream_review=true`.
    """
    if not url or not url.strip().lower().startswith(("http://", "https://")):
        return {"ok": False, "status_code": 0, "error": "invalid_url"}
    try:
        # Range GET is more permissive than HEAD — most live-radio
        # endpoints refuse HEAD outright but honor a bytes=0-1024 range
        # with a 206 or a 200.  Use `--max-filesize 4k` as belt-and-braces
        # so we don't accidentally slurp a live broadcast.
        result = subprocess.run(
            ["curl", "-sS", "--max-time", "5", "-A", "BigFM-Admin-Validator/1.0",
              "-H", "Range: bytes=0-1024", "-H", "Icy-MetaData: 1",
              "--max-filesize", "4096",
              "-o", "/dev/null", "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=8,
        )
        status_code = int((result.stdout or "0").strip() or 0)
        ok = 200 <= status_code < 400
        return {"ok": ok, "status_code": status_code,
                      "error": None if ok else f"http_{status_code}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "status_code": 0, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "status_code": 0, "error": str(e)[:120]}


async def _log_admin_audit(db, *, station_id: str, admin_user_id: str,
                                                          action: str, field_changes: Dict[str, Any],
                                                          before: Optional[Dict[str, Any]] = None) -> None:
    """Idempotent audit log write.  Never raises — audit failure MUST
    NOT block admin operations."""
    try:
        await db.station_admin_audit.insert_one({
            "audit_id":              f"aud_{secrets.token_hex(8)}",
            "station_id":          station_id,
            "admin_user_id":  admin_user_id,
            "action":                  action,  # create · update · soft_delete · hard_delete · restore
            "field_changes":  field_changes or {},
            "before_snapshot": {k: v for k, v in (before or {}).items()
                                                          if k != "_id" and not isinstance(v, datetime)},
            "timestamp":          _now(),
        })
    except Exception as e:
        logger.warning("[flagship-audit] insert failed: %s", e)


def _clean_station_doc(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return None
    out = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


class FlagshipCreateBody(BaseModel):
    name:                    str
    homepage:            Optional[str] = None
    frequency:          Optional[str] = None
    stream_url:        str
    logo_url:            Optional[str] = None
    country:              Optional[str] = None
    country_code:    Optional[str] = None
    city:                    Optional[str] = None
    flagship_region: Optional[str] = None   # "AE" · "US" · custom
    flagship_slug:     Optional[str] = None   # auto-derived from name if omitted
    flagship_priority: int = 150
    flagship_categories: List[str] = []
    languages:          List[str] = []
    description:        Optional[str] = None
    preroll_enabled: bool = True


class FlagshipUpdateBody(BaseModel):
    name:                    Optional[str] = None
    homepage:            Optional[str] = None
    frequency:          Optional[str] = None
    stream_url:        Optional[str] = None
    logo_url:            Optional[str] = None
    country:              Optional[str] = None
    country_code:    Optional[str] = None
    city:                    Optional[str] = None
    flagship_region: Optional[str] = None
    flagship_priority: Optional[int] = None
    flagship_categories: Optional[List[str]] = None
    languages:          Optional[List[str]] = None
    description:        Optional[str] = None
    preroll_enabled: Optional[bool] = None
    active:                Optional[bool] = None


class StreamValidateBody(BaseModel):
    stream_url: str


# ─── Stream URL validation ─────────────────────────────
@router.post("/api/admin/stations/flagship/validate-stream",
                          description=("Run a live curl HEAD/Range probe against a "
                                                          "candidate stream URL and return the resolved "
                                                          "status code + ok flag.  Non-destructive — no DB writes."))
async def admin_validate_flagship_stream(body: StreamValidateBody, request: Request,
                                                                                                admin: dict = Depends(require_admin)):
    return _validate_stream_url(body.stream_url)


# ─── CREATE ─────────────────────────────────────────────
@router.post("/api/admin/stations/flagship",
                          description=("Create a new flagship station.  Runs a "
                                                          "non-blocking curl HEAD/Range probe on the stream "
                                                          "URL — failure surfaces as a warning but does NOT "
                                                          "reject the save (row is flagged `needs_stream_review=true`)."))
async def admin_create_flagship(body: FlagshipCreateBody, request: Request,
                                                                            admin: dict = Depends(require_admin)):
    db = request.app.state.db
    slug = _sanitize_flagship_slug(
        body.flagship_slug or re.sub(r"[^a-z0-9]+", "-", body.name.lower()))
    # Collision check on slug.
    dup = await db.imported_radio_stations.find_one({"flagship_slug": slug})
    if dup:
        raise HTTPException(409, {"code": "slug_taken", "slug": slug,
                                                              "existing_station_id": dup.get("id")})
    station_id = _new_station_id()
    warnings: List[str] = []
    probe = _validate_stream_url(body.stream_url)
    needs_review = not probe["ok"]
    if needs_review:
        warnings.append("stream_url_head_check_failed")

    now = _now()
    logo_url = body.logo_url or (
        "https://ui-avatars.com/api/?name={}&size=256&background=8b5cf6"
        "&color=fff&bold=true&font-size=0.4".format(
            __import__("urllib.parse", fromlist=["quote"]).quote(body.name)))
    doc = {
        "id":                                        station_id,
        "provider":                            "flagship_admin_create",
        "name":                                    body.name,
        "homepage":                            body.homepage or "",
        "url":                                      body.stream_url,
        "url_resolved":                    body.stream_url,
        "stream_url":                      body.stream_url,   # convenience
        "favicon":                              logo_url,
        "logo_url":                            logo_url,
        "tags_raw":                            ",".join(body.flagship_categories or []),
        "tags_json":                          list(body.flagship_categories or []),
        "country":                              body.country or "",
        "country_code":                    (body.country_code or "").upper() or None,
        "city":                                      body.city or "",
        "language":                            " ".join(body.languages or []),
        "language_codes":                list(body.languages or []),
        "codec":                                  "mp3",
        "bitrate":                              128,
        "hls":                                      False,
        "active":                                  True,
        "description":                      body.description or "",
        "frequency":                          body.frequency or "",
        # Flagship extension.
        "is_flagship":                      True,
        "flagship_slug":                  slug,
        "flagship_region":              (body.flagship_region or body.country_code or "").upper() or None,
        "flagship_priority":            int(body.flagship_priority or 150),
        "flagship_categories":       list(body.flagship_categories or []),
        "flagship_search_terms":  [],
        "flagship_since":                now,
        "flagship_by":                        admin.get("user_id"),
        # Preroll parity — flagships play preroll like any other station
        # unless the operator explicitly disables it.
        "preroll_enabled":              bool(body.preroll_enabled),
        # Health status.
        "playable_status":              ("pending" if needs_review else "healthy"),
        "needs_stream_review":     needs_review,
        "last_health_check_at":  now,
        "health_error":                    probe.get("error"),
        "imported_at":                      now,
        "updated_at":                        now,
        "external_station_uuid":  f"bigfm-flgadmin-{slug}-{secrets.token_hex(3)}",
    }
    await db.imported_radio_stations.insert_one(doc)
    await _log_admin_audit(db, station_id=station_id,
                                                        admin_user_id=admin.get("user_id"),
                                                        action="create",
                                                        field_changes={"name": body.name, "slug": slug,
                                                                                    "stream_url": body.stream_url,
                                                                                    "preroll_enabled": bool(body.preroll_enabled)})
    logger.info("[flagship-create] id=%s slug=%s stream_ok=%s",
                                station_id, slug, probe["ok"])
    return {
        "ok": True,
        "station": _clean_station_doc(doc),
        "stream_probe": probe,
        "warnings": warnings,
    }


# ─── UPDATE ─────────────────────────────────────────────
@router.patch("/api/admin/stations/flagship/{station_id}",
                            description=("Partial update.  Only fields in the request "
                                                          "body are modified.  Stream URL changes trigger a "
                                                          "curl HEAD/Range probe (warn-only, does not reject)."))
async def admin_update_flagship(station_id: str, body: FlagshipUpdateBody,
                                                                              request: Request,
                                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    existing = await db.imported_radio_stations.find_one({"id": station_id})
    if not existing:
        raise HTTPException(404, {"code": "station_not_found"})
    updates: Dict[str, Any] = {"updated_at": _now()}
    warnings: List[str] = []
    probe: Optional[Dict[str, Any]] = None
    field_changes: Dict[str, Any] = {}
    payload = body.model_dump(exclude_unset=True)

    for f in ("name", "homepage", "frequency", "logo_url", "country",
                        "city", "description", "flagship_priority",
                        "flagship_region", "active"):
        if f in payload:
            updates[f] = payload[f]
            field_changes[f] = {"before": existing.get(f), "after": payload[f]}
    if "country_code" in payload:
        updates["country_code"] = (payload["country_code"] or "").upper() or None
        field_changes["country_code"] = {"before": existing.get("country_code"),
                                                                                  "after": updates["country_code"]}
    if "flagship_categories" in payload:
        cats = list(payload["flagship_categories"] or [])
        updates["flagship_categories"] = cats
        updates["tags_json"] = cats
        updates["tags_raw"] = ",".join(cats)
        field_changes["flagship_categories"] = {"before": existing.get("flagship_categories"),
                                                                                                          "after": cats}
    if "languages" in payload:
        langs = list(payload["languages"] or [])
        updates["language_codes"] = langs
        updates["language"] = " ".join(langs)
        field_changes["languages"] = {"before": existing.get("language_codes"),
                                                                          "after": langs}
    if "preroll_enabled" in payload:
        updates["preroll_enabled"] = bool(payload["preroll_enabled"])
        field_changes["preroll_enabled"] = {"before": existing.get("preroll_enabled"),
                                                                                          "after": bool(payload["preroll_enabled"])}
    if "logo_url" in payload and payload["logo_url"]:
        # Keep `favicon` in sync so existing legacy consumers pick up the change.
        updates["favicon"] = payload["logo_url"]
    if "stream_url" in payload and payload["stream_url"]:
        new_url = payload["stream_url"]
        updates["url"] = new_url
        updates["url_resolved"] = new_url
        updates["stream_url"] = new_url
        probe = _validate_stream_url(new_url)
        updates["needs_stream_review"] = not probe["ok"]
        updates["last_health_check_at"] = _now()
        updates["health_error"] = probe.get("error")
        updates["playable_status"] = "pending" if not probe["ok"] else "healthy"
        if not probe["ok"]:
            warnings.append("stream_url_head_check_failed")
        field_changes["stream_url"] = {"before": existing.get("url_resolved"),
                                                                                "after": new_url,
                                                                                "probe": probe}

    await db.imported_radio_stations.update_one({"id": station_id},
                                                                                                                {"$set": updates})
    await _log_admin_audit(db, station_id=station_id,
                                                        admin_user_id=admin.get("user_id"),
                                                        action="update",
                                                        field_changes=field_changes,
                                                        before=existing)
    fresh = await db.imported_radio_stations.find_one({"id": station_id})
    return {"ok": True, "station": _clean_station_doc(fresh),
                  "stream_probe": probe, "warnings": warnings}


# ─── DELETE ─────────────────────────────────────────────
@router.delete("/api/admin/stations/flagship/{station_id}",
                              description=("Delete a flagship station.  Defaults to soft "
                                                            "delete (`active=false`, `is_flagship=false`) — "
                                                            "pass `hard=true` for permanent removal.  Hard "
                                                            "delete requires the frontend confirmation flow."))
async def admin_delete_flagship(station_id: str, request: Request,
                                                                              hard: bool = Query(False, description="Permanently remove the row."),
                                                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    existing = await db.imported_radio_stations.find_one({"id": station_id})
    if not existing:
        raise HTTPException(404, {"code": "station_not_found"})
    if hard:
        await db.imported_radio_stations.delete_one({"id": station_id})
        await _log_admin_audit(db, station_id=station_id,
                                                            admin_user_id=admin.get("user_id"),
                                                            action="hard_delete",
                                                            field_changes={"deleted_slug": existing.get("flagship_slug")},
                                                            before=existing)
        # Sweep any per-slug logo assets on disk.
        try:
            slug = existing.get("flagship_slug")
            if slug:
                for ext in _ALLOWED_LOGO_EXT:
                    p = _LOGO_DIR / f"{slug}.{ext}"
                    if p.exists():
                        p.unlink()
        except Exception:
            pass
        logger.info("[flagship-hard-delete] station=%s slug=%s admin=%s",
                                station_id, existing.get("flagship_slug"), admin.get("user_id"))
        return {"ok": True, "hard": True, "station_id": station_id}
    # Soft delete: keep the row for auditability + potential restore.
    await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"active": False,
                          "is_flagship": False,
                          "flagship_by":  admin.get("user_id"),
                          "soft_deleted_at": _now(),
                          "updated_at": _now()}})
    await _log_admin_audit(db, station_id=station_id,
                                                        admin_user_id=admin.get("user_id"),
                                                        action="soft_delete",
                                                        field_changes={"active": False, "is_flagship": False},
                                                        before=existing)
    logger.info("[flagship-soft-delete] station=%s slug=%s admin=%s",
                                station_id, existing.get("flagship_slug"), admin.get("user_id"))
    return {"ok": True, "hard": False, "station_id": station_id}


# ─── Audit log query (read-only, admin) ─────────────────
@router.get("/api/admin/stations/flagship/{station_id}/audit",
                          description="Return the audit trail for a flagship station.")
async def admin_flagship_audit(station_id: str, request: Request,
                                                                        limit: int = 50,
                                                                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    rows = await db.station_admin_audit.find(
        {"station_id": station_id}
    ).sort("timestamp", -1).to_list(min(int(limit or 50), 200))
    out = []
    for r in rows:
        d = {k: v for k, v in r.items() if k != "_id"}
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        out.append(d)
    return {"items": out, "count": len(out)}
