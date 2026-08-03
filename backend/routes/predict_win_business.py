"""Sub-Phase E3 — Predict & Win business builder + venue check-in.

Endpoints under `/api/business/predict-win/...` let a verified
business-radio station owner author + manage their own predict-and-win
campaigns end-to-end, with admin approval still gating live deployment.
A separate `POST /api/predict-win/checkin` endpoint (mounted on the
consumer router) lets listeners redeem QR check-in tokens.

Compliance:  reuses the FORBIDDEN_LEXICON_RE + _guard_lexicon helpers
from `routes.predict_win_admin` so business creators are subject to
the exact same forbidden-terminology guard as the admin authoring path.

Surfaces (auth: business-radio station owner unless noted):
    POST   /api/business/predict-win/stations/{slug}/campaigns
    GET    /api/business/predict-win/stations/{slug}/campaigns
    GET    /api/business/predict-win/campaigns/{campaign_id}
    PATCH  /api/business/predict-win/campaigns/{campaign_id}
    POST   /api/business/predict-win/campaigns/{campaign_id}/prizes
    DELETE /api/business/predict-win/campaigns/{campaign_id}/prizes/{prize_id}
    POST   /api/business/predict-win/campaigns/{campaign_id}/submit-approval
    POST   /api/business/predict-win/campaigns/{campaign_id}/resolve
    POST   /api/business/predict-win/campaigns/{campaign_id}/checkin/qr-token
    POST   /api/business/predict-win/campaigns/{campaign_id}/pair-tv
    GET    /api/business/predict-win/campaigns/{campaign_id}/analytics
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from auth import current_user
from routes.predict_win_admin import (
    _guard_lexicon, _guard_event_type, _normalize_options,
    _parse_iso, _iso, _strip_mongo, _now, _new_id,
    EVENT_TYPES_DISABLED,
    AnswerOptionIn, QuestionIn, WinnerRulesIn, PrizeIn, ResolveIn,
)

logger = logging.getLogger("bigfm.predict_win.business")

router = APIRouter(prefix="/api/business/predict-win", tags=["predict-win-business"])


# Business creators may only author these event types.  The admin can
# create any of the 7 admin-only types (see predict_win_admin.EVENT_TYPES).
BUSINESS_EVENT_TYPES = {"restaurant_bar", "club_event", "business_custom"}

# Check-in token TTL.  Matches the venue/staff pairing TTL pattern.
CHECKIN_TTL_SECONDS = 300              # 5 min
CHECKIN_USE_WINDOW_SEC = 1800        # the venue_checkin row stays usable
                                                                # for 30 min after first scan
TV_PAIRING_CODE_TTL_SEC = 900       # 15 min to scan-and-pair


# ─── Pydantic payloads ─────────────────────────────────────────────────
class BusinessCampaignCreateIn(BaseModel):
    """Same shape as admin CampaignCreateIn but with business gates:
    - `event_type` restricted to BUSINESS_EVENT_TYPES (others → 403)
    - `creator_type` auto-set to 'business'
    - `checkin_required` defaults to True
    """
    title: str = Field(min_length=4, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    event_type: str
    event_label: Optional[str] = Field(default=None, max_length=160)
    category: Optional[str] = Field(default=None, max_length=80)
    city: Optional[str] = Field(default=None, max_length=80)
    region: Optional[str] = Field(default=None, max_length=80)
    language: str = Field(default="en", max_length=8)
    cover_image_url: Optional[str] = Field(default=None, max_length=600)
    question: QuestionIn
    start_time: str
    lock_time: str
    resolve_by: Optional[str] = None
    winner_rules: WinnerRulesIn = Field(default_factory=WinnerRulesIn)
    compliance_settings_id: Optional[str] = None
    checkin_required: bool = True


class BusinessCampaignPatchIn(BaseModel):
    title: Optional[str] = Field(default=None, min_length=4, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    event_label: Optional[str] = Field(default=None, max_length=160)
    category: Optional[str] = Field(default=None, max_length=80)
    city: Optional[str] = Field(default=None, max_length=80)
    region: Optional[str] = Field(default=None, max_length=80)
    cover_image_url: Optional[str] = Field(default=None, max_length=600)
    question: Optional[QuestionIn] = None
    start_time: Optional[str] = None
    lock_time: Optional[str] = None
    resolve_by: Optional[str] = None
    winner_rules: Optional[WinnerRulesIn] = None
    compliance_settings_id: Optional[str] = None
    checkin_required: Optional[bool] = None


class PairTVIn(BaseModel):
    label: Optional[str] = Field(default=None, max_length=80)


class CheckinTokenIn(BaseModel):
    ttl_seconds: Optional[int] = Field(
        default=CHECKIN_TTL_SECONDS, ge=60, le=3600,
        description=(
            "Token validity window in seconds. The QR is meant to be "
            "displayed at the venue (on TV / a placard) and rotated "
            "periodically, so the default is short."
        ),
    )


class BusinessResolveIn(BaseModel):
    """Same payload as admin ResolveIn but routed through the business
    path so we tag `result_source: 'manual_business'` on the resolution.
    """
    winning_option_id: str = Field(min_length=1, max_length=80)
    audit_notes: Optional[str] = Field(default=None, max_length=2000)


# ─── Helpers ───────────────────────────────────────────────────────────
async def _resolve_owner_station(db, slug: str, user: dict) -> dict:
    """Find the station, ensure it's a business_radio + the caller owns it."""
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "station_not_found"})
    if s.get("owner_user_id") != user["user_id"]:
        raise HTTPException(403, {"code": "not_station_owner"})
    if s.get("page_type") != "business_radio":
        raise HTTPException(403, {
            "code": "not_a_business_station",
            "message": ("Predict & Win campaigns can only be created from "
                                  "business_radio stations.  Convert the station's "
                                  "page_type from your station settings first."),
        })
    return s


async def _resolve_campaign_for_owner(db, campaign_id: str,
                                                                user: dict) -> dict:
    c = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    if not c or c.get("deleted_at"):
        raise HTTPException(404, {"code": "campaign_not_found"})
    if c.get("creator_type") != "business":
        raise HTTPException(403, {
            "code": "not_a_business_campaign",
            "message": "This campaign was authored on the admin surface.",
        })
    if c.get("business_owner_user_id") != user["user_id"]:
        raise HTTPException(403, {"code": "not_campaign_owner"})
    return c


def _guard_business_event_type(et: str) -> None:
    if et in EVENT_TYPES_DISABLED:
        raise HTTPException(422, {"code": "event_type_disabled"})
    if et not in BUSINESS_EVENT_TYPES:
        raise HTTPException(403, {
            "code": "event_type_not_allowed_for_business",
            "message": (
                f"Business creators may only use event_type in "
                f"{sorted(BUSINESS_EVENT_TYPES)}."),
            "allowed": sorted(BUSINESS_EVENT_TYPES),
            "received": et,
        })


def _serialize_campaign(c: dict) -> dict:
    return _strip_mongo(c)


def _gen_pairing_code() -> str:
    """8-char alphanumeric pairing code, displayed in groups of 4
    (e.g. `AB12-CD34`).  Skips visually-ambiguous chars (I, 1, O, 0)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


# ─── Index ensurer (called from server bootstrap) ──────────────────────
async def ensure_e3_indexes(db) -> dict:
    """E3-specific indexes (venue_checkins, predict_win_tv_displays
    extension fields, business-campaign filters)."""
    # venue_checkins — TTL on expires_at via standard expireAfterSeconds 0.
    await db.venue_checkins.create_index("checkin_id", unique=True)
    await db.venue_checkins.create_index(
        [("user_id", 1), ("campaign_id", 1)])
    await db.venue_checkins.create_index(
        "expires_at", expireAfterSeconds=0)
    # tokens are short-lived rows ("issued tokens") — separate collection.
    await db.predict_win_checkin_tokens.create_index("token", unique=True)
    await db.predict_win_checkin_tokens.create_index(
        "expires_at", expireAfterSeconds=0)
    # predict_win_tv_displays — sparse unique on pairing_code, ttl on
    # pairing_expires_at (only pre-pair rows have it).
    await db.predict_win_tv_displays.create_index(
        "pairing_code",
        unique=True,
        partialFilterExpression={"pairing_code": {"$exists": True, "$type": "string"}},
    )
    # business campaign filter
    await db.predict_win_campaigns.create_index(
        [("creator_type", 1), ("business_station_slug", 1), ("created_at", -1)])
    return {"venue_checkins": True,
                  "predict_win_checkin_tokens": True,
                  "predict_win_tv_displays": True,
                  "predict_win_campaigns": True}


# ─── Campaign CRUD (business-owned) ────────────────────────────────────
@router.post("/stations/{slug}/campaigns",
                            description=(
                                "Create a Predict & Win campaign as the owner of a "
                                "business_radio station.  Owner authentication via the "
                                "standard session cookie; the station must have "
                                "`page_type == 'business_radio'`.  `event_type` is "
                                "restricted to restaurant_bar / club_event / "
                                "business_custom; other values return 403.  Campaign "
                                "still requires admin approval before going live "
                                "(see `/submit-approval`)."))
async def create_business_campaign(
    slug: str, body: BusinessCampaignCreateIn, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    station = await _resolve_owner_station(db, slug, user)
    _guard_business_event_type(body.event_type)
    _guard_lexicon(
        body.title, body.description, body.event_label,
        body.question.prompt,
        *[o.label for o in body.question.answer_options],
    )
    start_time = _parse_iso(body.start_time)
    lock_time = _parse_iso(body.lock_time)
    resolve_by = _parse_iso(body.resolve_by) if body.resolve_by else None
    if not start_time or not lock_time:
        raise HTTPException(400, "start_time and lock_time required (ISO)")
    if start_time >= lock_time:
        raise HTTPException(400, "lock_time must be after start_time")
    if resolve_by is not None and resolve_by <= lock_time:
        raise HTTPException(400, {
            "code": "resolve_by_too_early",
            "message": "resolve_by must be after lock_time."})

    # Default the compliance row if owner didn't pick one explicitly.
    compliance_id = body.compliance_settings_id
    if not compliance_id:
        default = await db.prediction_compliance_settings.find_one(
            {"is_default": True, "active": True})
        compliance_id = default["settings_id"] if default else None

    # Default provider = manual (same as admin path).
    provider = await db.prediction_data_providers.find_one(
        {"provider_name": "manual"})
    provider_id = provider["provider_id"] if provider else None

    cid = _new_id("pwc")
    now = _now()
    bp = (station.get("business_profile") or {})
    doc = {
        "_id": cid,
        "campaign_id": cid,
        "title": body.title,
        "description": body.description,
        "event_type": body.event_type,
        "event_label": body.event_label or bp.get("business_name"),
        "category": body.category,
        "city": body.city or bp.get("city"),
        "region": body.region,
        "language": body.language,
        "cover_image_url": body.cover_image_url or station.get("cover_image_url"),
        "question": {
            "prompt": body.question.prompt,
            "answer_options": _normalize_options(body.question.answer_options),
        },
        "start_time": start_time,
        "lock_time": lock_time,
        "resolve_by": resolve_by,
        "winner_rules_json": body.winner_rules.model_dump(),
        "data_provider_id": provider_id,
        "compliance_settings_id": compliance_id,
        # Business-specific fields.
        "creator_type": "business",
        "business_station_slug": slug,
        "business_owner_user_id": user["user_id"],
        "checkin_required": bool(body.checkin_required),
        # Lifecycle.
        "approval_status": "draft",
        "approval_reason": None,
        "approved_by": None,
        "approved_at": None,
        "rejected_by": None,
        "rejected_at": None,
        "status": "draft",
        "created_by": user["user_id"],
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    await db.predict_win_campaigns.insert_one(doc)
    return {"ok": True, "campaign": _serialize_campaign(doc)}


@router.get("/stations/{slug}/campaigns")
async def list_business_campaigns(
    slug: str, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    station = await _resolve_owner_station(db, slug, user)
    cur = db.predict_win_campaigns.find({
        "business_station_slug": slug,
        "creator_type": "business",
        "deleted_at": None,
    }).sort("created_at", -1).limit(100)
    items: List[dict] = []
    async for c in cur:
        prize_count = await db.predict_win_prizes.count_documents(
            {"campaign_id": c["campaign_id"], "active": True})
        entry_count = await db.predict_win_entries.count_documents(
            {"campaign_id": c["campaign_id"]})
        award_count = await db.predict_win_awards.count_documents(
            {"campaign_id": c["campaign_id"]})
        item = _strip_mongo(c)
        item["prize_count"] = prize_count
        item["entry_count"] = entry_count
        item["award_count"] = award_count
        items.append(item)
    return {"items": items, "count": len(items),
                  "station": {"slug": slug, "name": station.get("name")}}


@router.get("/campaigns/{campaign_id}")
async def get_business_campaign(
    campaign_id: str, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    prizes_cur = db.predict_win_prizes.find(
        {"campaign_id": campaign_id, "active": True}).sort("rank", 1)
    prizes = [_strip_mongo(p) async for p in prizes_cur]
    compliance = None
    if c.get("compliance_settings_id"):
        cs = await db.prediction_compliance_settings.find_one(
            {"settings_id": c["compliance_settings_id"]})
        if cs:
            compliance = _strip_mongo(cs)
    resolution = await db.predict_win_resolutions.find_one(
        {"campaign_id": campaign_id})
    entry_count = await db.predict_win_entries.count_documents(
        {"campaign_id": campaign_id})
    award_count = await db.predict_win_awards.count_documents(
        {"campaign_id": campaign_id})
    tv = await db.predict_win_tv_displays.find_one(
        {"campaign_id": campaign_id, "active": True})
    return {
        "campaign": _serialize_campaign(c),
        "prizes": prizes,
        "compliance": compliance,
        "resolution": _strip_mongo(resolution) if resolution else None,
        "entry_count": entry_count,
        "award_count": award_count,
        "tv_display": _strip_mongo(tv) if tv else None,
    }


@router.patch("/campaigns/{campaign_id}")
async def patch_business_campaign(
    campaign_id: str, body: BusinessCampaignPatchIn, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    if c["approval_status"] not in {"draft", "rejected"}:
        raise HTTPException(409, {
            "code": "campaign_locked_for_edit",
            "message": ("Campaign can only be edited while approval_status "
                                  "is 'draft' or 'rejected'."),
        })
    update: Dict[str, Any] = {}
    text_fields = ("title", "description", "event_label", "category", "city",
                              "region", "cover_image_url")
    text_values = [getattr(body, k) for k in text_fields]
    _guard_lexicon(*[v for v in text_values if isinstance(v, str)])
    for k in text_fields:
        v = getattr(body, k)
        if v is not None:
            update[k] = v
    if body.question is not None:
        _guard_lexicon(body.question.prompt,
                                  *[o.label for o in body.question.answer_options])
        update["question"] = {
            "prompt": body.question.prompt,
            "answer_options": _normalize_options(body.question.answer_options),
        }
    if body.start_time:
        st = _parse_iso(body.start_time)
        if not st:
            raise HTTPException(400, "start_time must be valid ISO")
        update["start_time"] = st
    if body.lock_time:
        lt = _parse_iso(body.lock_time)
        if not lt:
            raise HTTPException(400, "lock_time must be valid ISO")
        update["lock_time"] = lt
    if body.resolve_by is not None:
        update["resolve_by"] = _parse_iso(body.resolve_by) if body.resolve_by else None
    if body.winner_rules is not None:
        update["winner_rules_json"] = body.winner_rules.model_dump()
    if body.compliance_settings_id is not None:
        update["compliance_settings_id"] = body.compliance_settings_id
    if body.checkin_required is not None:
        update["checkin_required"] = bool(body.checkin_required)
    new_start = update.get("start_time", c.get("start_time"))
    new_lock = update.get("lock_time", c.get("lock_time"))
    if new_start and new_lock and new_start >= new_lock:
        raise HTTPException(400, "lock_time must be after start_time")
    update["updated_at"] = _now()
    if c["approval_status"] == "rejected":
        update["approval_status"] = "draft"
        update["rejected_by"] = None
        update["rejected_at"] = None
        update["approval_reason"] = None
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id}, {"$set": update})
    fresh = await db.predict_win_campaigns.find_one(
        {"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}


# ─── Prize management (delegated to admin guard logic) ────────────────
@router.post("/campaigns/{campaign_id}/prizes")
async def add_business_prize(
    campaign_id: str, body: PrizeIn, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    if c["approval_status"] not in {"draft", "rejected"}:
        raise HTTPException(409, {"code": "campaign_locked_for_edit"})
    _guard_lexicon(body.title, body.description)
    pid = _new_id("pwp")
    now = _now()
    doc = {
        "_id": pid,
        "prize_id": pid,
        "campaign_id": campaign_id,
        "rank": body.rank,
        "title": body.title,
        "description": body.description,
        "prize_kind": body.prize_kind,
        "value_amount": body.value_amount,
        "value_currency": body.value_currency,
        "image_url": body.image_url,
        "inventory_total": body.inventory_total,
        "inventory_remaining": body.inventory_total,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.predict_win_prizes.insert_one(doc)
    return {"ok": True, "prize": _strip_mongo(doc)}


@router.delete("/campaigns/{campaign_id}/prizes/{prize_id}")
async def delete_business_prize(
    campaign_id: str, prize_id: str, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    if c["approval_status"] not in {"draft", "rejected"}:
        raise HTTPException(409, {"code": "campaign_locked_for_edit"})
    res = await db.predict_win_prizes.update_one(
        {"prize_id": prize_id, "campaign_id": campaign_id},
        {"$set": {"active": False, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, {"code": "prize_not_found"})
    return {"ok": True, "deleted": True}


# ─── Submit-approval ──────────────────────────────────────────────────
@router.post("/campaigns/{campaign_id}/submit-approval")
async def submit_business_for_approval(
    campaign_id: str, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    if c["approval_status"] != "draft":
        raise HTTPException(409, {
            "code": "invalid_state",
            "message": f"Cannot submit while approval_status={c['approval_status']}"})
    # Reuse the admin validator (≥2 options, ≥1 prize, lock_time > now+5m,
    # compliance row attached).
    from routes.predict_win_admin import _validate_for_submit
    await _validate_for_submit(db, campaign_id)
    now = _now()
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"approval_status": "pending_review", "updated_at": now}})
    fresh = await db.predict_win_campaigns.find_one(
        {"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}


# ─── Business manual resolve ─────────────────────────────────────────
@router.post("/campaigns/{campaign_id}/resolve",
                            description=(
                                "Business owner manual resolve.  Allowed AFTER lock_time "
                                "and only from status='locked' or status='live' "
                                "post-lock.  Sets `result_source='manual_business'` on "
                                "the resolution row and runs the E2 award pipeline."))
async def business_resolve_campaign(
    campaign_id: str, body: BusinessResolveIn, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    if c["approval_status"] != "approved":
        raise HTTPException(409, {"code": "campaign_not_approved"})
    if c["status"] in {"resolved", "cancelled"}:
        raise HTTPException(409, {"code": "campaign_status_terminal",
                                                          "current_status": c["status"]})
    lock_time = c.get("lock_time")
    if isinstance(lock_time, datetime) and lock_time.tzinfo is None:
        lock_time = lock_time.replace(tzinfo=timezone.utc)
    if lock_time and lock_time > _now():
        raise HTTPException(409, {
            "code": "lock_time_not_passed",
            "message": ("Predictions are still open. Wait until after "
                                  "lock_time to resolve the winning pick."),
            "lock_time": _iso(lock_time)})
    options = (c.get("question") or {}).get("answer_options") or []
    valid_ids = {o["option_id"] for o in options}
    if body.winning_option_id not in valid_ids:
        raise HTTPException(400, {
            "code": "invalid_winning_option",
            "message": f"winning_option_id must be one of {sorted(valid_ids)}"})
    existing_res = await db.predict_win_resolutions.find_one(
        {"campaign_id": campaign_id})
    if existing_res:
        raise HTTPException(409, {"code": "campaign_already_resolved"})

    now = _now()
    rid = _new_id("pwr")
    await db.predict_win_resolutions.insert_one({
        "_id": rid,
        "resolution_id": rid,
        "campaign_id": campaign_id,
        "winning_option_id": body.winning_option_id,
        "resolved_by": user["user_id"],
        "resolved_at": now,
        "result_source": "manual_business",
        "data_source_url": None,
        "audit_notes": body.audit_notes,
        "audit_json": {
            "actor": user["user_id"],
            "actor_email": user.get("email"),
            "prior_status": c["status"],
            "options_at_resolve_time": options,
        },
    })
    await db.predict_win_entries.update_many(
        {"campaign_id": campaign_id,
          "picked_option_id": body.winning_option_id},
        {"$set": {"status": "winner", "evaluated_at": now}})
    await db.predict_win_entries.update_many(
        {"campaign_id": campaign_id,
          "picked_option_id": {"$ne": body.winning_option_id}},
        {"$set": {"status": "loser", "evaluated_at": now}})
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "resolved", "updated_at": now}})

    pipeline_result: dict = {"ok": False, "skipped": True}
    try:
        from services.predict_win_award_pipeline import run_award_pipeline
        pipeline_result = await run_award_pipeline(
            db, campaign_id=campaign_id,
            winning_option_id=body.winning_option_id, resolution_id=rid)
    except Exception as _e:
        logger.warning("Sub-Phase E3 award pipeline error for %s: %s",
                                  campaign_id, _e)

    fresh = await db.predict_win_campaigns.find_one(
        {"campaign_id": campaign_id})
    res_fresh = await db.predict_win_resolutions.find_one(
        {"campaign_id": campaign_id})
    return {
        "ok": True,
        "campaign": _serialize_campaign(fresh),
        "resolution": _strip_mongo(res_fresh),
        "award_pipeline": pipeline_result,
    }


# ─── Venue check-in: token issuance (owner) + redemption (listener) ──
def _public_qr_url(host: str, campaign_id: str, token: str) -> str:
    """The URL encoded into the QR rendered on the TV display.  The
    consumer SPA at this path reads campaign + token from the query
    string and calls POST /api/predict-win/checkin internally."""
    # `host` arrives like https://app.bigfm.com (no trailing slash).
    return (f"{host}/predict-win/checkin"
                  f"?campaign={campaign_id}&token={token}")


@router.post("/campaigns/{campaign_id}/checkin/qr-token",
                            description=(
                                "Issue a single-use venue check-in token for this "
                                "campaign.  The token is rendered as a QR code on "
                                "the TV display; customers scan it to prove physical "
                                "presence at the venue.  TTL default is 5 minutes; "
                                "owners rotate the token periodically."))
async def issue_checkin_token(
    campaign_id: str, body: CheckinTokenIn, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    if not c.get("checkin_required"):
        # We still issue, but warn — owners can disable check-in via PATCH.
        pass
    token = "pwk_" + secrets.token_urlsafe(16)
    now = _now()
    expires_at = now + timedelta(seconds=int(body.ttl_seconds or CHECKIN_TTL_SECONDS))
    await db.predict_win_checkin_tokens.insert_one({
        "_id": token,
        "token": token,
        "campaign_id": campaign_id,
        "business_station_slug": c.get("business_station_slug"),
        "business_owner_user_id": user["user_id"],
        "issued_at": now,
        "expires_at": expires_at,
        "ttl_seconds": int(body.ttl_seconds or CHECKIN_TTL_SECONDS),
    })
    host = (str(request.base_url).rstrip("/")
                if request else "https://app.bigfm")
    return {
        "ok": True,
        "token": token,
        "expires_at": _iso(expires_at),
        "ttl_seconds": int(body.ttl_seconds or CHECKIN_TTL_SECONDS),
        "qr_payload_url": _public_qr_url(host, campaign_id, token),
    }


# ─── TV pairing (owner) ───────────────────────────────────────────────
@router.post("/campaigns/{campaign_id}/pair-tv",
                            description=(
                                "Pair a TV display to this campaign.  Returns an 8-char "
                                "alphanumeric pairing code (formatted XXXX-XXXX) that "
                                "matches `/tv/predict-win/{pairing_code}`.  Codes are "
                                "single-display (one paired TV per code).  Re-calling "
                                "deactivates any prior pairing for this campaign."))
async def pair_tv(
    campaign_id: str, body: PairTVIn, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    now = _now()
    # Soft-deactivate any prior active pairing — only one TV per campaign
    # for now (E4 may extend to multiple).
    await db.predict_win_tv_displays.update_many(
        {"campaign_id": campaign_id, "active": True},
        {"$set": {"active": False, "deactivated_at": now}})
    display_id = _new_id("pwt")
    pairing_code = _gen_pairing_code()
    # Belt-and-braces: very small chance of collision on the 8-char
    # alphabet — retry up to 3 times if the index rejects.
    for _attempt in range(3):
        try:
            await db.predict_win_tv_displays.insert_one({
                "_id": display_id,
                "display_id": display_id,
                "campaign_id": campaign_id,
                "business_station_slug": c.get("business_station_slug"),
                "business_owner_user_id": user["user_id"],
                "pairing_code": pairing_code,
                "pairing_issued_at": now,
                "pairing_expires_at": now + timedelta(seconds=TV_PAIRING_CODE_TTL_SEC),
                "label": body.label,
                "active": True,
                "last_seen_at": None,
                "poll_count": 0,
                "created_at": now,
                "updated_at": now,
            })
            break
        except Exception as _e:
            pairing_code = _gen_pairing_code()
    return {
        "ok": True,
        "display_id": display_id,
        "pairing_code": pairing_code,
        "pairing_expires_at": _iso(now + timedelta(seconds=TV_PAIRING_CODE_TTL_SEC)),
        "kiosk_url_path": f"/tv/predict-win/{pairing_code}",
    }


# ─── Analytics ────────────────────────────────────────────────────────
@router.get("/campaigns/{campaign_id}/analytics",
                          description=(
                              "Per-campaign analytics for the owner: entries, unique "
                              "users, community pick distribution, current top pick, "
                              "awards + redemption count."))
async def campaign_analytics(
    campaign_id: str, request: Request,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    c = await _resolve_campaign_for_owner(db, campaign_id, user)
    options = (c.get("question") or {}).get("answer_options") or []
    option_index = {o["option_id"]: o for o in options}

    pipeline = [
        {"$match": {"campaign_id": campaign_id, "status": {"$ne": "void"}}},
        {"$group": {"_id": "$picked_option_id",
                            "count": {"$sum": 1},
                            "users": {"$addToSet": "$user_id"}}},
    ]
    distribution: List[dict] = []
    total_entries = 0
    unique_users: set = set()
    async for r in db.predict_win_entries.aggregate(pipeline):
        opt = option_index.get(r["_id"], {})
        cnt = int(r["count"] or 0)
        total_entries += cnt
        unique_users.update(r.get("users") or [])
        distribution.append({
            "option_id": r["_id"],
            "label": opt.get("label", r["_id"]),
            "count": cnt,
            "user_count": len(r.get("users") or []),
        })
    # Sort by count desc.
    distribution.sort(key=lambda d: d["count"], reverse=True)
    pct_total = float(total_entries) if total_entries > 0 else 0.0
    for d in distribution:
        d["pct"] = round((d["count"] / pct_total) * 100.0, 1) if pct_total else 0.0
    # Ensure every option appears even if 0 picks.
    seen_opts = {d["option_id"] for d in distribution}
    for o in options:
        if o["option_id"] not in seen_opts:
            distribution.append({
                "option_id": o["option_id"],
                "label": o["label"],
                "count": 0, "user_count": 0, "pct": 0.0,
            })

    top_pick = distribution[0] if distribution else None
    award_count = await db.predict_win_awards.count_documents(
        {"campaign_id": campaign_id})
    delivered = await db.predict_win_awards.count_documents(
        {"campaign_id": campaign_id, "delivery_status": "delivered"})

    # Entries-per-minute time-series for the last 60 minutes (or since
    # start_time, whichever is later).  Useful for the dashboard chart.
    now = _now()
    cutoff = now - timedelta(minutes=60)
    start = c.get("start_time")
    if isinstance(start, datetime):
        start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        if start > cutoff:
            cutoff = start
    cutoff_iso = _iso(cutoff)
    ts_pipeline = [
        {"$match": {"campaign_id": campaign_id,
                              "status": {"$ne": "void"},
                              "submitted_at": {"$gte": cutoff_iso}}},
        {"$group": {"_id": {"$substr": ["$submitted_at", 0, 16]},
                            "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    timeseries: List[dict] = []
    async for r in db.predict_win_entries.aggregate(ts_pipeline):
        timeseries.append({"minute": r["_id"], "count": int(r["count"] or 0)})

    return {
        "campaign_id": campaign_id,
        "total_entries": total_entries,
        "unique_users": len(unique_users),
        "distribution": distribution,
        "top_pick": top_pick,
        "award_count": award_count,
        "delivered_count": delivered,
        "timeseries_minute": timeseries,
        "options": [{"option_id": o["option_id"], "label": o["label"]}
                              for o in options],
    }
