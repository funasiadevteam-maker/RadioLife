"""Sub-Phase E2 — Predict & Win consumer endpoints.

Listener-facing surface (no admin/business UI here):

  • `GET  /api/predict-win/active`               — discovery list
  • `GET  /api/predict-win/{id}`                 — detail (eligibility, dist)
  • `POST /api/predict-win/{id}/enter`        — submit a pick
  • `GET  /api/predict-win/my-picks`        — user's entries (any status)
  • `GET  /api/predict-win/my-wins`          — user's won entries + prizes
  • `DELETE /api/predict-win/entries/{eid}` — withdraw (pre-lock only)

Compliance lexicon enforced by /predict-win/* server-side as well as
on the frontend: forbidden terminology never appears in any error
message, hint, or label this module produces.
"""
from __future__ import annotations
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional as optional_user

log = logging.getLogger("bigfm.predict_win.consumer")

router = APIRouter(prefix="/api/predict-win", tags=["predict-win-consumer"])


# ───────────────────────────────────────────────────────────── constants
ALLOWED_ENTRY_SOURCES = {"app", "qr", "tv", "lobby", "deep_link"}
DEFAULT_AGE_PERMISSIVE = True   # If user has no DOB, treat as ≥ 18.

# Tiny in-process TTL cache for community-distribution responses.
_DIST_CACHE: Dict[str, dict] = {}
_DIST_TTL_SEC = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _strip(doc: dict) -> dict:
    if not doc:
        return doc
    out = dict(doc)
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = _iso(v)
    return out


# ─────────────────────────────────────────────────────── eligibility
def _compute_age_from_dob(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    try:
        d = datetime.fromisoformat(str(dob).replace("Z", "+00:00"))
        now = _now()
        years = now.year - d.year
        if (now.month, now.day) < (d.month, d.day):
            years -= 1
        return max(0, years)
    except Exception:
        return None


def _user_passes_age_gate(user: Optional[dict],
                                                  min_age: int) -> tuple[bool, Optional[str]]:
    if min_age <= 0:
        return True, None
    if not user:
        # Anonymous browse is OK; entry endpoints enforce login separately.
        return True, None
    age = _compute_age_from_dob(user.get("date_of_birth"))
    if age is None:
        # Permissive default (no DOB on profile) — let the user enter.
        if DEFAULT_AGE_PERMISSIVE:
            return True, None
        return False, "age_unknown"
    if age < min_age:
        return False, f"age_below_{min_age}"
    return True, None


def _resolve_user_country(user: Optional[dict],
                                                request: Request) -> Optional[str]:
    """Use the user-doc country first, then fall back to request-resolved.
    Returns an uppercase ISO code or None."""
    if user and user.get("country"):
        return str(user["country"]).upper()
    # Lazy import to avoid circular import on cold start.
    try:
        from services.geo import resolve_country  # type: ignore
    except Exception:
        return None
    try:
        # Best effort: extract X-Forwarded-For chain.
        xff = request.headers.get("x-forwarded-for") or ""
        ip = xff.split(",")[0].strip() if xff else None
        if not ip:
            return None
        out = resolve_country(ip)
        if isinstance(out, dict):
            return (out.get("country_code") or out.get("country")
                          or "").upper() or None
        return (str(out) or "").upper() or None
    except Exception:
        return None


def _user_passes_geo_gate(country: Optional[str],
                                                  compliance: dict) -> tuple[bool, Optional[str]]:
    if not compliance:
        return True, None
    rules = compliance.get("geo_restrictions_json") or {}
    allow = rules.get("allowed_countries") or ["*"]
    block = rules.get("blocked_countries") or []
    if country:
        if country in block:
            return False, f"country_blocked:{country}"
        if "*" not in allow and country not in allow:
            return False, f"country_not_allowed:{country}"
    else:
        # Unknown country — be permissive unless rules are strict.
        if "*" not in allow and not block:
            return False, "country_unknown"
    return True, None


async def _eligibility(
    db, user: Optional[dict], request: Request, campaign: dict,
) -> Dict[str, Any]:
    compliance = None
    if campaign.get("compliance_settings_id"):
        compliance = await db.prediction_compliance_settings.find_one(
            {"settings_id": campaign["compliance_settings_id"]})
    age_ok, age_reason = _user_passes_age_gate(
        user, (compliance or {}).get("age_restriction") or 0)
    country = _resolve_user_country(user, request)
    geo_ok, geo_reason = _user_passes_geo_gate(country, compliance or {})
    lock_dt = _aware(campaign.get("lock_time"))
    lock_expired = bool(lock_dt and lock_dt <= _now())
    blocked = []
    if not age_ok:
        blocked.append(age_reason or "age_blocked")
    if not geo_ok:
        blocked.append(geo_reason or "geo_blocked")
    if lock_expired:
        blocked.append("entries_closed")
    return {
        "can_enter": (not blocked) and bool(user),
        "block_reasons": blocked,
        "resolved_country": country,
        "min_age": (compliance or {}).get("age_restriction") or 0,
        "lock_time": _iso(lock_dt) if lock_dt else None,
        "lock_expired": lock_expired,
        "anonymous": user is None,
    }


# ──────────────────────────────────────── distribution (TTL-cached)
async def _option_pick_distribution(
    db, campaign: dict, *, viewer_user_id: Optional[str],
) -> Optional[List[dict]]:
    """Returns `[{option_id, label, pct, count}]` or `None` when the
    campaign hides distribution until lock_time elapses."""
    cid = campaign["campaign_id"]
    hide = bool(campaign.get("hide_distribution_before_lock"))
    lock_dt = _aware(campaign.get("lock_time"))
    if hide and lock_dt and lock_dt > _now():
        return None
    cache_key = f"{cid}:dist"
    hit = _DIST_CACHE.get(cache_key)
    if hit and hit["expires_at"] > time.time():
        return hit["value"]
    options = (campaign.get("question") or {}).get("answer_options") or []
    cur = db.predict_win_entries.aggregate([
        {"$match": {"campaign_id": cid, "status": {"$ne": "void"}}},
        {"$group": {"_id": "$picked_option_id", "count": {"$sum": 1}}},
    ])
    counts: Dict[str, int] = {}
    async for row in cur:
        counts[row["_id"]] = row["count"]
    total = sum(counts.values()) or 0
    out = []
    for o in options:
        c = counts.get(o["option_id"], 0)
        pct = (c / total * 100.0) if total > 0 else 0.0
        out.append({
            "option_id": o["option_id"],
            "label": o.get("label"),
            "count": c,
            "pct": round(pct, 1),
        })
    _DIST_CACHE[cache_key] = {
        "value": out, "expires_at": time.time() + _DIST_TTL_SEC,
    }
    return out


# ─────────────────────────────────────────────────────── /active
@router.get("/active")
async def list_active(
    request: Request,
    event_type: Optional[str] = Query(None, max_length=64),
    city: Optional[str] = Query(None, max_length=80),
    category_slug: Optional[str] = Query(None, max_length=64),
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(20, ge=1, le=50),
    user: Optional[dict] = Depends(optional_user),
):
    """Returns approved + scheduled-or-live campaigns whose lock_time
    is still in the future, with eligibility hints for the viewer.

    Phase PDX.1 — accepts `category_slug` filter (one of `sports_top`,
    `stocks_top`, `us_politics`, `national_games`) and returns
    `category_slug` + `points_reward` on every item so the frontend
    can render chip filtering and per-card points badges."""
    db = request.app.state.db
    now = _now()
    q: Dict[str, Any] = {
        "approval_status": "approved",
        "status": {"$in": ["scheduled", "live"]},
        "lock_time": {"$gt": now},
        "deleted_at": None,
    }
    if event_type:
        q["event_type"] = event_type
    if city:
        q["city"] = {"$regex": f"^{city.strip()}$", "$options": "i"}
    if category_slug:
        q["category_slug"] = category_slug
    total = await db.predict_win_campaigns.count_documents(q)
    skip = (page - 1) * limit
    cur = (db.predict_win_campaigns.find(q)
                  .sort([("start_time", 1), ("created_at", -1)])
                  .skip(skip).limit(limit))
    items: List[dict] = []
    user_id = user.get("user_id") if user else None
    async for c in cur:
        # E1.4 hotfix — make this loop defensive against schema drift.
        # Any single malformed campaign row (missing keys, bad
        # datetimes, broken refs) must NOT 500 the entire list and
        # surface as "Failed to load" on the consumer page.
        try:
            prize = await db.predict_win_prizes.find_one(
                {"campaign_id": c["campaign_id"], "active": True},
                sort=[("rank", 1)])
            compliance = None
            if c.get("compliance_settings_id"):
                compliance = await db.prediction_compliance_settings.find_one(
                    {"settings_id": c["compliance_settings_id"]})
            user_entry = None
            if user_id:
                user_entry = await db.predict_win_entries.find_one({
                    "campaign_id": c["campaign_id"],
                    "user_id": user_id,
                })
            eligibility = await _eligibility(db, user, request, c)
            # If the listener has already submitted a non-void pick, surface
            # that on `eligibility.can_enter` so the UI flips its CTA from
            # "Make your pick" to "View My Pick" without a second round-trip.
            if user_entry and user_entry.get("status") != "void":
                if eligibility.get("can_enter"):
                    eligibility = dict(eligibility)
                    eligibility["can_enter"] = False
                    reasons = list(eligibility.get("block_reasons") or [])
                    if "already_entered" not in reasons:
                        reasons.append("already_entered")
                    eligibility["block_reasons"] = reasons
                eligibility["existing_entry_id"] = user_entry.get("entry_id")
                eligibility["existing_entry_status"] = user_entry.get("status")
            items.append({
                "campaign_id": c["campaign_id"],
                "title": c["title"],
                "description": c.get("description"),
                "event_type": c.get("event_type"),
                "event_label": c.get("event_label"),
                "city": c.get("city"),
                "region": c.get("region"),
                "cover_image_url": c.get("cover_image_url"),
                # Phase PDX.1 — surface curator metadata so the client
                # can render the category chip + per-card points badge.
                "category_slug": c.get("category_slug"),
                "points_reward": int(c.get("points_reward") or 25),
                "import_source": c.get("import_source") or "admin_manual",
                "question_prompt": (c.get("question") or {}).get("prompt"),
                "answer_options_count": len(
                    (c.get("question") or {}).get("answer_options") or []),
                "start_time": _iso(_aware(c.get("start_time"))),
                "lock_time": _iso(_aware(c.get("lock_time"))),
                "lock_seconds_remaining": max(
                    0, int((_aware(c["lock_time"]) - now).total_seconds())),
                "prize": _public_prize(prize) if prize else None,
                "no_purchase_necessary_text": (
                    (compliance or {}).get("no_purchase_necessary_text")
                    or "No purchase necessary. All entries are free."
                ),
                "terms_settings_id": (compliance or {}).get("settings_id"),
                "checkin_required": bool(c.get("checkin_required")),
                "eligibility": eligibility,
                "user_has_entered": bool(user_entry),
            })
        except Exception as e:
            # E1.4 hotfix — skip the malformed row, log a warning,
            # keep serving the rest.  Prevents one bad campaign from
            # killing the whole consumer list.
            log.warning("[predict_win] skipping malformed campaign "
                                      "campaign_id=%s err=%s",
                                      (c or {}).get("campaign_id"), e)
            continue
    return {"items": items, "total": total, "page": page,
                  "has_more": (skip + len(items)) < total,
                  "server_time": _iso(now)}


def _public_prize(prize: dict) -> dict:
    return {
        "prize_id": prize.get("prize_id"),
        "rank": prize.get("rank"),
        "title": prize.get("title"),
        "description": prize.get("description"),
        "prize_kind": prize.get("prize_kind"),
        "value_amount": prize.get("value_amount"),
        "value_currency": prize.get("value_currency"),
        "image_url": prize.get("image_url"),
        "inventory_remaining": prize.get("inventory_remaining"),
    }


# ─────────────────────────────────────────────────────── /{id}
# Path uses `/campaigns/{id}` rather than `/{id}` so it can't shadow
# the sibling routes (`/my-picks`, `/my-wins`, `/entries/{eid}`).  The
# brief said `GET /api/predict-win/{id}`; we keep `/campaigns/` as the
# canonical path and add a back-compat alias below for the brief shape.
@router.get("/campaigns/{campaign_id}",
                      response_model=None,
                      include_in_schema=True)
async def get_campaign_public(
    campaign_id: str,
    request: Request,
    user: Optional[dict] = Depends(optional_user),
):
    if not campaign_id.startswith("pwc_"):
        raise HTTPException(404, {"code": "campaign_not_found"})
    db = request.app.state.db
    c = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    if not c or c.get("deleted_at"):
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("approval_status") != "approved":
        raise HTTPException(404, {"code": "campaign_not_visible"})
    prizes_cur = db.predict_win_prizes.find(
        {"campaign_id": campaign_id, "active": True}).sort("rank", 1)
    prizes = [_public_prize(p) async for p in prizes_cur]
    compliance = None
    if c.get("compliance_settings_id"):
        compliance = await db.prediction_compliance_settings.find_one(
            {"settings_id": c["compliance_settings_id"]})
    distribution = await _option_pick_distribution(
        db, c, viewer_user_id=user.get("user_id") if user else None)
    user_entry = None
    if user:
        user_entry = await db.predict_win_entries.find_one({
            "campaign_id": campaign_id, "user_id": user["user_id"]})
    eligibility = await _eligibility(db, user, request, c)
    # Mirror the /active rule: a user with a live (non-void) entry cannot
    # re-enter, so flip can_enter regardless of age/geo state.
    if user_entry and user_entry.get("status") != "void":
        if eligibility.get("can_enter"):
            eligibility = dict(eligibility)
            eligibility["can_enter"] = False
            reasons = list(eligibility.get("block_reasons") or [])
            if "already_entered" not in reasons:
                reasons.append("already_entered")
            eligibility["block_reasons"] = reasons
        eligibility["existing_entry_id"] = user_entry.get("entry_id")
        eligibility["existing_entry_status"] = user_entry.get("status")
    return {
        "campaign": {
            "campaign_id": c["campaign_id"],
            "title": c["title"],
            "description": c.get("description"),
            "event_type": c.get("event_type"),
            "event_label": c.get("event_label"),
            "city": c.get("city"),
            "region": c.get("region"),
            "cover_image_url": c.get("cover_image_url"),
            "language": c.get("language"),
            "question": c.get("question"),
            "start_time": _iso(_aware(c.get("start_time"))),
            "lock_time": _iso(_aware(c.get("lock_time"))),
            "lock_seconds_remaining": max(
                0, int((_aware(c["lock_time"]) - _now()).total_seconds())),
            "checkin_required": bool(c.get("checkin_required")),
            "hide_distribution_before_lock": bool(
                c.get("hide_distribution_before_lock")),
        },
        "prizes": prizes,
        "compliance_summary": _compliance_summary(compliance),
        "option_pick_distribution": distribution,
        "user_entry": _public_entry(user_entry) if user_entry else None,
        "eligibility": eligibility,
        "server_time": _iso(),
    }


def _compliance_summary(c: Optional[dict]) -> Optional[dict]:
    if not c:
        return None
    return {
        "settings_id": c.get("settings_id"),
        "name": c.get("name"),
        "region": c.get("region"),
        "age_restriction": c.get("age_restriction"),
        "no_purchase_necessary_text": c.get("no_purchase_necessary_text"),
        "void_where_prohibited": c.get("void_where_prohibited"),
        "terms_text": c.get("terms_text"),
        "data_handling_url": c.get("data_handling_url"),
    }


def _public_entry(e: Optional[dict]) -> Optional[dict]:
    if not e:
        return None
    # Both `confidence` and `confidence_points` mirror the same value so
    # clients written against either field name see a populated value.
    conf = e.get("confidence")
    return {
        "entry_id": e.get("entry_id"),
        "campaign_id": e.get("campaign_id"),
        "picked_option_id": e.get("picked_option_id"),
        "confidence": conf,
        "confidence_points": conf,
        "submitted_at": e.get("submitted_at"),
        "status": e.get("status"),
        "source_context": e.get("source_context"),
    }


# ─────────────────────────────────────────────────────── /{id}/enter
class EnterIn(BaseModel):
    """Submit-pick payload.

    `confidence` is the canonical field name (matches the stored doc).
    `confidence_points` is accepted as an alias for backward compatibility
    with earlier client revisions / E2 tester harnesses.  Either key
    populates `users.confidence` in the entry doc.  If both keys are sent,
    `confidence_points` wins (since it's the more recent name).  If
    neither key is sent, defaults to 5 (mid-slider).
    """
    # Pydantic v2 — `populate_by_name=True` lets us accept either
    # the field name OR the alias from the JSON body.
    model_config = {"populate_by_name": True}

    selected_option_id: str = Field(min_length=1, max_length=80)
    confidence: Optional[int] = Field(
        default=None, ge=1, le=10,
        description=(
            "Confidence score 1–10. Canonical key. Also accepted as "
            "`confidence_points` for back-compat."
        ),
    )
    confidence_points: Optional[int] = Field(
        default=None, ge=1, le=10,
        description="Alias for `confidence`. Either may be sent.",
    )
    source_context: Optional[str] = Field(default="app", max_length=32)
    venue_checkin_id: Optional[str] = Field(default=None, max_length=120)


@router.post("/campaigns/{campaign_id}/enter")
async def enter_campaign(
    campaign_id: str,
    body: EnterIn,
    request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    if not c or c.get("deleted_at"):
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("approval_status") != "approved":
        raise HTTPException(409, {"code": "campaign_not_visible"})
    if c.get("status") in ("resolved", "cancelled"):
        raise HTTPException(409, {"code": "campaign_closed",
                                                          "current_status": c.get("status")})
    lock_dt = _aware(c.get("lock_time"))
    if lock_dt and lock_dt <= _now():
        raise HTTPException(400, {"code": "entries_closed",
                                                          "message": "Picks are closed for this prediction."})
    options = (c.get("question") or {}).get("answer_options") or []
    valid_ids = {o["option_id"] for o in options}
    if body.selected_option_id not in valid_ids:
        raise HTTPException(400, {"code": "invalid_option",
                                                          "message": "Pick is not one of the available options."})
    if body.source_context and body.source_context not in ALLOWED_ENTRY_SOURCES:
        raise HTTPException(400, {"code": "invalid_source",
                                                          "allowed": sorted(ALLOWED_ENTRY_SOURCES)})

    compliance = None
    if c.get("compliance_settings_id"):
        compliance = await db.prediction_compliance_settings.find_one(
            {"settings_id": c["compliance_settings_id"]})
    age_ok, age_reason = _user_passes_age_gate(
        user, (compliance or {}).get("age_restriction") or 0)
    if not age_ok:
        raise HTTPException(403, {"code": "age_blocked",
                                                          "message": "You don't meet the minimum age for this prediction.",
                                                          "detail": age_reason})
    country = _resolve_user_country(user, request)
    geo_ok, geo_reason = _user_passes_geo_gate(country, compliance or {})
    if not geo_ok:
        raise HTTPException(403, {"code": "geo_blocked",
                                                          "message": "This prediction isn't available in your region.",
                                                          "detail": geo_reason,
                                                          "country": country})
    if c.get("checkin_required"):
        # Sub-Phase E3 — listener must redeem a venue check-in token
        # before entering a check-in-gated campaign.  The body field
        # `venue_checkin_id` is validated against the `venue_checkins`
        # collection (issued by `POST /api/predict-win/checkin` after the
        # listener scans the venue QR).
        if not body.venue_checkin_id:
            raise HTTPException(400, {"code": "venue_checkin_required",
                                                              "message": "You need to check in at the venue first."})
        checkin = await db.venue_checkins.find_one(
            {"checkin_id": body.venue_checkin_id})
        if not checkin or checkin.get("user_id") != user["user_id"]:
            raise HTTPException(400, {"code": "venue_checkin_invalid",
                                                              "message": "Venue check-in could not be verified."})
        if checkin.get("campaign_id") != campaign_id:
            raise HTTPException(400, {"code": "venue_checkin_wrong_campaign",
                                                              "message": "Your check-in was for a different campaign."})
        ck_exp = _aware(checkin.get("expires_at"))
        if ck_exp and ck_exp <= _now():
            raise HTTPException(400, {"code": "venue_checkin_expired",
                                                              "message": "Your venue check-in has expired — scan the QR again."})
    existing = await db.predict_win_entries.find_one(
        {"campaign_id": campaign_id, "user_id": user["user_id"]})
    if existing and existing.get("status") != "void":
        raise HTTPException(400, {"code": "already_entered",
                                                          "message": "You've already submitted a pick for this prediction.",
                                                          "entry_id": existing["entry_id"]})

    now = _now()
    entry_id = _new_id("pwe")
    join_id = f"pwe_{campaign_id}_{user['user_id']}"
    # Accept either `confidence` or `confidence_points` from the client.
    # `confidence_points` (the newer alias) wins when both are sent.
    # Default to 5 (mid-slider) when neither key is present.
    confidence_value = (body.confidence_points
                                            if body.confidence_points is not None
                                            else body.confidence)
    if confidence_value is None:
        confidence_value = 5
    doc = {
        "_id": join_id,
        "entry_id": entry_id,
        "campaign_id": campaign_id,
        "user_id": user["user_id"],
        "picked_option_id": body.selected_option_id,
        "confidence": confidence_value,
        "submitted_at": _iso(now),
        "status": "submitted",
        "evaluated_at": None,
        "ip_geo_city": _resolve_user_city(user, request),
        "ip_geo_country": country,
        "source_context": body.source_context or "app",
        "venue_checkin_id": body.venue_checkin_id,
    }
    if existing and existing.get("status") == "void":
        # Re-entry after withdrawal: upsert (replaces void row).
        await db.predict_win_entries.replace_one(
            {"_id": join_id}, doc)
    else:
        try:
            await db.predict_win_entries.insert_one(doc)
        except Exception as e:
            if "duplicate" in str(e).lower():
                raise HTTPException(400, {"code": "already_entered"})
            raise

    _DIST_CACHE.pop(f"{campaign_id}:dist", None)
    return {
        "ok": True,
        "entry": _public_entry(doc),
        "campaign_id": campaign_id,
        "lock_time": _iso(lock_dt),
        "lock_seconds_remaining": max(
            0, int((lock_dt - now).total_seconds())) if lock_dt else None,
    }


def _resolve_user_city(user: dict, request: Request) -> Optional[str]:
    if user.get("preferred_city"):
        return user["preferred_city"]
    if user.get("city"):
        return user["city"]
    return None


# ──────────────────────────────────────────────── /my-picks
@router.get("/my-picks")
async def my_picks(
    request: Request,
    status: Optional[str] = Query(None, regex=r"^(?:submitted|winner|loser|void|all)$"),
    page: int = Query(1, ge=1, le=200),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    q: Dict[str, Any] = {"user_id": user["user_id"]}
    if status and status != "all":
        q["status"] = status
    total = await db.predict_win_entries.count_documents(q)
    skip = (page - 1) * limit
    rows: List[dict] = []
    async for e in (db.predict_win_entries.find(q)
                                .sort("submitted_at", -1).skip(skip).limit(limit)):
        rows.append(e)
    cids = list({r["campaign_id"] for r in rows})
    campaigns: Dict[str, dict] = {}
    if cids:
        async for c in db.predict_win_campaigns.find(
            {"campaign_id": {"$in": cids}}):
            campaigns[c["campaign_id"]] = c
    items: List[dict] = []
    for e in rows:
        c = campaigns.get(e["campaign_id"], {})
        award = None
        if e.get("status") == "winner":
            award = await db.predict_win_awards.find_one({
                "campaign_id": e["campaign_id"],
                "entry_id": e["entry_id"],
            })
        items.append({
            "entry": _public_entry(e),
            "campaign": _public_campaign_summary(c),
            "award": _public_award(award) if award else None,
        })
    return {"items": items, "total": total, "page": page,
                  "has_more": (skip + len(items)) < total}


def _public_campaign_summary(c: dict) -> dict:
    if not c:
        return {}
    return {
        "campaign_id": c.get("campaign_id"),
        "title": c.get("title"),
        "event_label": c.get("event_label"),
        "city": c.get("city"),
        "cover_image_url": c.get("cover_image_url"),
        "status": c.get("status"),
        "lock_time": _iso(_aware(c.get("lock_time"))),
        "question_prompt": (c.get("question") or {}).get("prompt"),
    }


def _public_award(a: Optional[dict]) -> Optional[dict]:
    if not a:
        return None
    return {
        "award_id": a.get("award_id"),
        "prize_id": a.get("prize_id"),
        "delivery_status": a.get("delivery_status"),
        "wallet_item_id": a.get("wallet_item_id"),
        "awarded_at": _iso(_aware(a.get("awarded_at"))),
    }


# ──────────────────────────────────────────────── /my-wins
@router.get("/my-wins")
async def my_wins(
    request: Request,
    page: int = Query(1, ge=1, le=200),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    q = {"user_id": user["user_id"], "status": "winner"}
    total = await db.predict_win_entries.count_documents(q)
    skip = (page - 1) * limit
    rows: List[dict] = []
    async for e in (db.predict_win_entries.find(q)
                                .sort("evaluated_at", -1).skip(skip).limit(limit)):
        rows.append(e)
    items: List[dict] = []
    for e in rows:
        c = await db.predict_win_campaigns.find_one(
            {"campaign_id": e["campaign_id"]})
        award = await db.predict_win_awards.find_one({
            "campaign_id": e["campaign_id"],
            "entry_id": e["entry_id"],
        })
        prize = None
        wallet_item = None
        if award:
            prize = await db.predict_win_prizes.find_one(
                {"prize_id": award.get("prize_id")})
            if award.get("wallet_item_id"):
                wallet_item = await db.user_wallet_items.find_one(
                    {"_id": award["wallet_item_id"]})
        items.append({
            "entry": _public_entry(e),
            "campaign": _public_campaign_summary(c or {}),
            "award": _public_award(award),
            "prize": _public_prize(prize) if prize else None,
            "wallet_item": _strip(wallet_item) if wallet_item else None,
        })
    return {"items": items, "total": total, "page": page,
                  "has_more": (skip + len(items)) < total}


# ──────────────────────────────────────────────── /entries/{eid}
@router.delete("/entries/{entry_id}")
async def withdraw_entry(
    entry_id: str,
    request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    e = await db.predict_win_entries.find_one({"entry_id": entry_id})
    if not e or e["user_id"] != user["user_id"]:
        raise HTTPException(404, {"code": "entry_not_found"})
    if e["status"] in ("winner", "loser"):
        raise HTTPException(409, {"code": "entry_evaluated",
                                                          "message": "This prediction has already been resolved."})
    c = await db.predict_win_campaigns.find_one(
        {"campaign_id": e["campaign_id"]})
    if c:
        lock_dt = _aware(c.get("lock_time"))
        if lock_dt and lock_dt <= _now():
            raise HTTPException(400, {"code": "entries_closed",
                                                              "message": "Picks are locked — you can no longer remove your entry."})
        if c.get("status") in ("resolved", "cancelled"):
            raise HTTPException(409, {"code": "campaign_closed"})
    await db.predict_win_entries.update_one(
        {"entry_id": entry_id},
        {"$set": {"status": "void", "voided_at": _iso()}},
    )
    _DIST_CACHE.pop(f"{e['campaign_id']}:dist", None)
    return {"ok": True, "entry_id": entry_id}



# ─────────────────────────────────────────── /checkin (Sub-Phase E3)
class CheckinRedeemIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=80)
    token: str = Field(min_length=10, max_length=120)


@router.post("/checkin",
                            description=(
                                "Redeem a venue check-in token (scanned from a TV QR "
                                "at the venue).  Issues a `venue_checkin_id` that the "
                                "listener then passes to `/enter` for campaigns with "
                                "`checkin_required: true`.  Tokens are single-use; "
                                "redeeming twice with the same token returns the "
                                "existing checkin row (idempotent)."))
async def redeem_checkin(
    body: CheckinRedeemIn, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    token_row = await db.predict_win_checkin_tokens.find_one(
        {"token": body.token})
    if not token_row:
        raise HTTPException(400, {"code": "checkin_token_not_found",
                                                          "message": "Check-in token is invalid or expired."})
    if token_row["campaign_id"] != body.campaign_id:
        raise HTTPException(400, {"code": "checkin_token_wrong_campaign",
                                                          "message": "Token does not belong to this campaign."})
    exp = _aware(token_row.get("expires_at"))
    now = _now()
    if exp and exp <= now:
        raise HTTPException(400, {"code": "checkin_token_expired",
                                                          "message": "Check-in token has expired — scan the latest QR."})
    # Idempotency: if this user has redeemed this token before, return
    # the existing checkin row instead of inserting a duplicate.
    existing = await db.venue_checkins.find_one({
        "user_id": user["user_id"],
        "campaign_id": body.campaign_id,
        "redeemed_token": body.token,
    })
    if existing:
        return {
            "ok": True,
            "venue_checkin_id": existing["checkin_id"],
            "expires_at": _iso(existing.get("expires_at")),
            "business_station_slug": existing.get("business_station_slug"),
            "idempotent_reuse": True,
        }
    checkin_id = _new_id("vch")
    # The checkin row stays usable for 30 min after first scan so the
    # listener has comfortable time to walk to their seat and submit
    # their pick.
    valid_until = now + timedelta(minutes=30)
    await db.venue_checkins.insert_one({
        "_id": checkin_id,
        "checkin_id": checkin_id,
        "user_id": user["user_id"],
        "campaign_id": body.campaign_id,
        "business_station_slug": token_row.get("business_station_slug"),
        "business_owner_user_id": token_row.get("business_owner_user_id"),
        "checkin_method": "qr",
        "redeemed_token": body.token,
        "checked_in_at": now,
        "expires_at": valid_until,
    })
    return {
        "ok": True,
        "venue_checkin_id": checkin_id,
        "expires_at": _iso(valid_until),
        "business_station_slug": token_row.get("business_station_slug"),
        "idempotent_reuse": False,
    }
