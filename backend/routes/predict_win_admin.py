"""Sub-Phase E1 — Predict & Win admin manual campaign builder.

Compliance guardrails (CRITICAL):
  • Never use gambling terminology (bet, wager, gamble, spread, shares,
    contracts, exchange).  Use "prediction", "pick", "fan pick",
    "community prediction", "points", "confidence", "prize", "reward".
  • `event_type = "live_sports_moment"` is feature-flagged OFF.  Any
    create/update with that value returns HTTP 422.
  • Every campaign MUST have a linked `prediction_compliance_settings`
    row before submit-approval succeeds.
  • Lock-time must be > now + 5 minutes at submit-approval time.
  • ≥ 2 answer options and ≥ 1 prize required before submit-approval.

State machines (two, kept independent):

  approval_status:  draft → pending_review → approved
                                                    → rejected   (terminal after `approved`)

  status:                  draft → scheduled → live → locked → resolved
                                                                            → cancelled

This module owns ONLY the admin (Phase E1) surface.  No consumer / business
/ TV reads here.  Mock external provider (`manual`) is seeded so Phase E5
can flip in Predexon later without schema changes.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from auth import require_admin

logger = logging.getLogger("bigfm.predict_win.admin")

router = APIRouter(prefix="/api/admin/predict-win", tags=["predict-win-admin"])


# ─── Constants ─────────────────────────────────────────────────────────
EVENT_TYPES = [
    "sports_game",
    "live_sports_moment",      # feature-flagged OFF
    "restaurant_bar",
    "club_event",
    "movie_entertainment",
    "business_custom",
    "bigfm_admin",
]

EVENT_TYPES_DISABLED = {"live_sports_moment"}

PRIZE_KINDS = ["points", "merchandise", "experience", "coupon", "bigcoin"]
SCORING_RULES = ["winner_takes_all", "points_per_correct"]
TIEBREAKERS = ["first_to_pick", "random"]
QUESTION_KINDS = ["yes_no", "multiple_choice", "numeric"]

APPROVAL_STATES = {"draft", "pending_review", "approved", "rejected"}
LIFECYCLE_STATES = {"draft", "scheduled", "live", "locked", "resolved", "cancelled"}

# Compliance lexicon guardrail — gambling terminology forbidden in any
# admin-authored text field (title, description, question prompt,
# answer-option label, prize title/description).
FORBIDDEN_LEXICON_RE = re.compile(
    r"\b("
    r"bet|bets|betting|wager|wagers|wagering|gamble|gambling|gambler|"
    r"spread\s*betting|spreads?|odds\b|"
    r"buy\s*shares?|sell\s*shares?|order\s*book|"
    r"contracts?\s+(?:to|for)\s+buy|contracts?\s+(?:to|for)\s+sell|"
    r"exchange"
    r")\b",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _parse_iso(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _strip_mongo(doc: dict) -> dict:
    if not doc:
        return doc
    out = dict(doc)
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = _iso(v)
    return out


def _guard_lexicon(*values: Optional[str]) -> None:
    """Raise 400 if any value contains gambling terminology."""
    for v in values:
        if not v:
            continue
        if FORBIDDEN_LEXICON_RE.search(v):
            raise HTTPException(
                400,
                {
                    "code": "forbidden_terminology",
                    "message": (
                        "Gambling terminology is not allowed. Use "
                        "'prediction', 'pick', 'points', 'prize' instead."
                    ),
                    "matched": FORBIDDEN_LEXICON_RE.search(v).group(0),
                },
            )


def _guard_event_type(event_type: str) -> None:
    if event_type not in EVENT_TYPES:
        raise HTTPException(
            422,
            {
                "code": "invalid_event_type",
                "message": f"event_type must be one of {EVENT_TYPES}",
            },
        )
    if event_type in EVENT_TYPES_DISABLED:
        raise HTTPException(
            422,
            {
                "code": "event_type_disabled",
                "message": (
                    f"event_type '{event_type}' is disabled pending legal "
                    "review and cannot be used in campaigns."
                ),
            },
        )


# ─── Pydantic payloads ─────────────────────────────────────────────────
class AnswerOptionIn(BaseModel):
    option_id: Optional[str] = None
    label: str = Field(min_length=1, max_length=120)
    kind: str = "multiple_choice"

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, v):
        if v not in QUESTION_KINDS:
            raise ValueError(f"kind must be one of {QUESTION_KINDS}")
        return v


class QuestionIn(BaseModel):
    prompt: str = Field(min_length=4, max_length=280)
    answer_options: List[AnswerOptionIn] = Field(default_factory=list)


class WinnerRulesIn(BaseModel):
    scoring: str = "winner_takes_all"
    max_winners: Optional[int] = Field(default=None, ge=1, le=10000)
    tiebreaker: str = "first_to_pick"
    points_per_correct: Optional[int] = Field(default=None, ge=0, le=10000)

    @field_validator("scoring")
    @classmethod
    def _valid_scoring(cls, v):
        if v not in SCORING_RULES:
            raise ValueError(f"scoring must be one of {SCORING_RULES}")
        return v

    @field_validator("tiebreaker")
    @classmethod
    def _valid_tiebreaker(cls, v):
        if v not in TIEBREAKERS:
            raise ValueError(f"tiebreaker must be one of {TIEBREAKERS}")
        return v


class CampaignCreateIn(BaseModel):
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
    data_provider_id: Optional[str] = None
    external_market_id: Optional[str] = Field(default=None, max_length=200)
    compliance_settings_id: Optional[str] = None


class CampaignPatchIn(BaseModel):
    title: Optional[str] = Field(default=None, min_length=4, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    event_type: Optional[str] = None
    event_label: Optional[str] = Field(default=None, max_length=160)
    category: Optional[str] = Field(default=None, max_length=80)
    city: Optional[str] = Field(default=None, max_length=80)
    region: Optional[str] = Field(default=None, max_length=80)
    language: Optional[str] = Field(default=None, max_length=8)
    cover_image_url: Optional[str] = Field(default=None, max_length=600)
    question: Optional[QuestionIn] = None
    start_time: Optional[str] = None
    lock_time: Optional[str] = None
    resolve_by: Optional[str] = None
    winner_rules: Optional[WinnerRulesIn] = None
    data_provider_id: Optional[str] = None
    external_market_id: Optional[str] = Field(default=None, max_length=200)
    compliance_settings_id: Optional[str] = None


class PrizeIn(BaseModel):
    rank: int = Field(ge=1, le=50)
    title: str = Field(min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=600)
    prize_kind: str = "points"
    value_amount: Optional[float] = Field(default=None, ge=0)
    value_currency: Optional[str] = Field(default=None, max_length=8)
    image_url: Optional[str] = Field(default=None, max_length=600)
    inventory_total: int = Field(default=1, ge=1, le=100000)

    @field_validator("prize_kind")
    @classmethod
    def _valid_kind(cls, v):
        if v not in PRIZE_KINDS:
            raise ValueError(f"prize_kind must be one of {PRIZE_KINDS}")
        return v


class ComplianceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    region: Optional[str] = Field(default=None, max_length=80)
    terms_text: str = Field(min_length=10, max_length=20000)
    no_purchase_necessary_text: str = Field(min_length=10, max_length=2000)
    void_where_prohibited: str = Field(min_length=2, max_length=500)
    age_restriction: int = Field(default=18, ge=0, le=99)
    geo_restrictions_json: Dict[str, Any] = Field(default_factory=dict)
    data_handling_url: Optional[str] = Field(default=None, max_length=600)
    is_default: bool = False


class RejectIn(BaseModel):
    reason: str = Field(min_length=4, max_length=600)


class ResolveIn(BaseModel):
    winning_option_id: str = Field(min_length=1, max_length=80)
    audit_notes: Optional[str] = Field(default=None, max_length=2000)
    data_source_url: Optional[str] = Field(default=None, max_length=600)


class CancelIn(BaseModel):
    reason: str = Field(min_length=4, max_length=600)


# ─── Index ensurer ─────────────────────────────────────────────────────
async def ensure_predict_win_indexes(db) -> None:
    """Idempotent index bootstrap.  Covers all 12 collections."""
    # 1. prediction_data_providers
    await db.prediction_data_providers.create_index("provider_name", unique=True)
    # 2. prediction_markets_external
    await db.prediction_markets_external.create_index("external_market_id")
    await db.prediction_markets_external.create_index("provider_id")
    # 3. predict_win_campaigns
    await db.predict_win_campaigns.create_index("campaign_id", unique=True)
    await db.predict_win_campaigns.create_index([("status", 1), ("created_at", -1)])
    await db.predict_win_campaigns.create_index(
        [("approval_status", 1), ("created_at", -1)]
    )
    await db.predict_win_campaigns.create_index([("event_type", 1)])
    # 4. predict_win_prizes
    await db.predict_win_prizes.create_index("prize_id", unique=True)
    await db.predict_win_prizes.create_index([("campaign_id", 1), ("rank", 1)])
    # 5. predict_win_entries
    await db.predict_win_entries.create_index("entry_id", unique=True)
    await db.predict_win_entries.create_index(
        [("campaign_id", 1), ("user_id", 1)], unique=True
    )
    await db.predict_win_entries.create_index([("campaign_id", 1), ("status", 1)])
    # 6. predict_win_resolutions
    await db.predict_win_resolutions.create_index("resolution_id", unique=True)
    await db.predict_win_resolutions.create_index("campaign_id", unique=True)
    # 7. predict_win_awards
    await db.predict_win_awards.create_index("award_id", unique=True)
    await db.predict_win_awards.create_index([("campaign_id", 1), ("winner_user_id", 1)])
    # 8. predict_win_tv_displays
    await db.predict_win_tv_displays.create_index("display_id", unique=True)
    await db.predict_win_tv_displays.create_index([("campaign_id", 1), ("active", 1)])
    # 9. predict_win_analytics_events
    await db.predict_win_analytics_events.create_index(
        [("campaign_id", 1), ("timestamp", -1)]
    )
    await db.predict_win_analytics_events.create_index("event_type")
    # 10. prediction_compliance_settings
    await db.prediction_compliance_settings.create_index("settings_id", unique=True)
    await db.prediction_compliance_settings.create_index(
        [("is_default", 1), ("active", 1)]
    )
    # 11. prediction_api_logs
    await db.prediction_api_logs.create_index([("provider_id", 1), ("called_at", -1)])
    # 12. predict_win_winner_rules (placeholder for E4+ rule reuse; rules
    #      are currently inlined on the campaign doc as `winner_rules_json`)
    await db.predict_win_winner_rules.create_index("rule_id", unique=True)
    logger.info("Sub-Phase E1: predict_win indexes ensured (12 collections)")


async def seed_manual_provider(db) -> None:
    """Idempotent — inserts the `manual` provider so admin campaigns work
    without external data integrations.  Phase E5 will add `predexon`."""
    existing = await db.prediction_data_providers.find_one(
        {"provider_name": "manual"}
    )
    if existing:
        return
    pid = _new_id("pdp")
    await db.prediction_data_providers.insert_one(
        {
            "_id": pid,
            "provider_id": pid,
            "provider_name": "manual",
            "active": True,
            "auth_type": "none",
            "base_url": None,
            "created_at": _now(),
        }
    )
    logger.info("Sub-Phase E1: seeded prediction_data_providers.manual provider")


# ─── Helpers ───────────────────────────────────────────────────────────
async def _resolve_default_provider(db) -> str:
    """Returns the provider_id of the `manual` data source.  Auto-seeds
    if missing (defensive — first user might hit this before startup)."""
    doc = await db.prediction_data_providers.find_one({"provider_name": "manual"})
    if not doc:
        await seed_manual_provider(db)
        doc = await db.prediction_data_providers.find_one({"provider_name": "manual"})
    return doc["provider_id"]


async def _validate_for_submit(db, campaign_id: str) -> None:
    """Pre-submit validation.  Raises HTTPException on failure."""
    c = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    # Live sports moment guard (defence-in-depth — already blocked on
    # create, but a record could exist if a future bug allowed it.)
    if c.get("event_type") in EVENT_TYPES_DISABLED:
        raise HTTPException(
            422,
            {"code": "event_type_disabled",
              "message": f"event_type '{c['event_type']}' is disabled."},
        )
    options = (c.get("question") or {}).get("answer_options") or []
    if len(options) < 2:
        raise HTTPException(
            400,
            {"code": "answer_options_required",
              "message": "Campaign needs at least 2 answer options."},
        )
    prize_count = await db.predict_win_prizes.count_documents(
        {"campaign_id": campaign_id, "active": True}
    )
    if prize_count < 1:
        raise HTTPException(
            400,
            {"code": "prize_required",
              "message": "Campaign needs at least 1 active prize."},
        )
    if not c.get("compliance_settings_id"):
        raise HTTPException(
            400,
            {"code": "compliance_required",
              "message": "Campaign must link a compliance_settings_id."},
        )
    compliance = await db.prediction_compliance_settings.find_one(
        {"settings_id": c["compliance_settings_id"], "active": True}
    )
    if not compliance:
        raise HTTPException(
            400,
            {"code": "compliance_not_found",
              "message": "Linked compliance_settings_id is missing or inactive."},
        )
    lock_time = c.get("lock_time")
    if isinstance(lock_time, datetime) and lock_time.tzinfo is None:
        lock_time = lock_time.replace(tzinfo=timezone.utc)
    if not lock_time or lock_time < _now() + timedelta(minutes=5):
        raise HTTPException(
            400,
            {"code": "lock_time_too_soon",
              "message": "lock_time must be at least 5 minutes in the future."},
        )
    start_time = c.get("start_time")
    if isinstance(start_time, datetime) and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if start_time and lock_time and start_time >= lock_time:
        raise HTTPException(
            400,
            {"code": "lock_must_follow_start",
              "message": "lock_time must be after start_time."},
        )


def _serialize_campaign(c: dict) -> dict:
    """Strip Mongo internals and stringify datetimes."""
    return _strip_mongo(c)


async def _get_campaign_or_404(db, campaign_id: str) -> dict:
    c = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    return c


def _normalize_options(options: List[AnswerOptionIn]) -> List[dict]:
    out: List[dict] = []
    used_ids: set = set()
    for idx, o in enumerate(options):
        opt_id = o.option_id or f"opt_{idx+1}"
        if opt_id in used_ids:
            opt_id = f"opt_{idx+1}_{uuid.uuid4().hex[:4]}"
        used_ids.add(opt_id)
        out.append({"option_id": opt_id, "label": o.label, "kind": o.kind})
    return out


# ─── Metadata routes ───────────────────────────────────────────────────
@router.get("/event-types")
async def list_event_types(_a: dict = Depends(require_admin)):
    """Returns the canonical event-type taxonomy plus a `disabled` flag
    so the UI can grey the `live_sports_moment` option."""
    return {
        "event_types": [
            {
                "value": e,
                "label": e.replace("_", " ").title(),
                "disabled": e in EVENT_TYPES_DISABLED,
                "disabled_reason": (
                    "Disabled pending legal review"
                    if e in EVENT_TYPES_DISABLED
                    else None
                ),
            }
            for e in EVENT_TYPES
        ],
        "prize_kinds": PRIZE_KINDS,
        "scoring_rules": SCORING_RULES,
        "tiebreakers": TIEBREAKERS,
        "question_kinds": QUESTION_KINDS,
    }


@router.get("/providers")
async def list_providers(
    request: Request, _a: dict = Depends(require_admin)
):
    db = request.app.state.db
    cur = db.prediction_data_providers.find({"active": True}).sort("provider_name", 1)
    items = []
    async for d in cur:
        items.append(_strip_mongo(d))
    return {"items": items, "count": len(items)}


# ─── Compliance routes ─────────────────────────────────────────────────
@router.get("/compliance")
async def list_compliance(
    request: Request,
    active_only: bool = Query(True),
    _a: dict = Depends(require_admin),
):
    db = request.app.state.db
    q: Dict[str, Any] = {}
    if active_only:
        q["active"] = True
    cur = db.prediction_compliance_settings.find(q).sort("created_at", -1)
    items = []
    async for d in cur:
        items.append(_strip_mongo(d))
    return {"items": items, "count": len(items)}


@router.post("/compliance")
async def create_compliance(
    body: ComplianceIn, request: Request, admin: dict = Depends(require_admin)
):
    db = request.app.state.db
    _guard_lexicon(body.terms_text, body.no_purchase_necessary_text,
                                body.void_where_prohibited, body.name)
    sid = _new_id("pcs")
    now = _now()
    if body.is_default:
        # Only one default at a time — flip prior defaults to False.
        await db.prediction_compliance_settings.update_many(
            {"is_default": True}, {"$set": {"is_default": False}}
        )
    doc = {
        "_id": sid,
        "settings_id": sid,
        "name": body.name,
        "region": body.region,
        "terms_text": body.terms_text,
        "no_purchase_necessary_text": body.no_purchase_necessary_text,
        "void_where_prohibited": body.void_where_prohibited,
        "age_restriction": body.age_restriction,
        "geo_restrictions_json": body.geo_restrictions_json or {"allowed_countries": ["*"]},
        "data_handling_url": body.data_handling_url,
        "is_default": body.is_default,
        "active": True,
        "created_at": now,
        "updated_at": now,
        "created_by": admin["user_id"],
    }
    await db.prediction_compliance_settings.insert_one(doc)
    return {"ok": True, "settings": _strip_mongo(doc)}


@router.get("/compliance/{settings_id}")
async def get_compliance(
    settings_id: str, request: Request, _a: dict = Depends(require_admin)
):
    db = request.app.state.db
    doc = await db.prediction_compliance_settings.find_one({"settings_id": settings_id})
    if not doc:
        raise HTTPException(404, "compliance_not_found")
    return {"settings": _strip_mongo(doc)}


@router.patch("/compliance/{settings_id}")
async def patch_compliance(
    settings_id: str,
    body: ComplianceIn,
    request: Request,
    _a: dict = Depends(require_admin),
):
    db = request.app.state.db
    existing = await db.prediction_compliance_settings.find_one({"settings_id": settings_id})
    if not existing:
        raise HTTPException(404, "compliance_not_found")
    _guard_lexicon(body.terms_text, body.no_purchase_necessary_text,
                                body.void_where_prohibited, body.name)
    update = body.model_dump()
    update["updated_at"] = _now()
    if body.is_default:
        await db.prediction_compliance_settings.update_many(
            {"is_default": True, "settings_id": {"$ne": settings_id}},
            {"$set": {"is_default": False}},
        )
    await db.prediction_compliance_settings.update_one(
        {"settings_id": settings_id}, {"$set": update}
    )
    fresh = await db.prediction_compliance_settings.find_one({"settings_id": settings_id})
    return {"ok": True, "settings": _strip_mongo(fresh)}


# ─── Campaign routes ───────────────────────────────────────────────────
@router.post(
    "/campaigns",
    description=(
        "Create a Predict & Win campaign in `draft` status.\n\n"
        "**Canonical time ordering** (all in the future at create time):\n"
        "  `start_time` < `lock_time` < `resolution_time` (`resolve_by`)\n\n"
        "  • `start_time`: when picks start being accepted from listeners.\n"
        "  • `lock_time`: when picks are no longer accepted.  Must be > "
        "`start_time` (enforced here) and > `now + 5 min` at "
        "submit-approval time (enforced in `_validate_for_submit`).\n"
        "  • `resolution_time` (`resolve_by`): optional — the latest "
        "moment an admin or the E4 cron sweeper is expected to write a "
        "`predict_win_resolutions` row.  Must be > `lock_time` when "
        "supplied.  An admin can still call `/force-resolve` past this "
        "moment; it is a soft SLA, not a hard cutoff.\n\n"
        "**Compliance guardrails** enforced at creation:\n"
        "  • `event_type` must be one of the 7 canonical values.  "
        "`live_sports_moment` returns HTTP 422 (feature-flagged OFF).\n"
        "  • Gambling terminology in any text field returns HTTP 400."
    ),
)
async def create_campaign(
    body: CampaignCreateIn, request: Request, admin: dict = Depends(require_admin)
):
    db = request.app.state.db
    _guard_event_type(body.event_type)
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
    # Canonical ordering: start_time < lock_time < resolution_time.
    if start_time >= lock_time:
        raise HTTPException(400, "lock_time must be after start_time")
    if resolve_by is not None and resolve_by <= lock_time:
        raise HTTPException(
            400,
            {"code": "resolve_by_too_early",
              "message": "resolve_by (resolution_time) must be after lock_time."},
        )
    provider_id = body.data_provider_id or await _resolve_default_provider(db)
    cid = _new_id("pwc")
    now = _now()
    doc = {
        "_id": cid,
        "campaign_id": cid,
        "title": body.title,
        "description": body.description,
        "event_type": body.event_type,
        "event_label": body.event_label,
        "category": body.category,
        "city": body.city,
        "region": body.region,
        "language": body.language,
        "cover_image_url": body.cover_image_url,
        "question": {
            "prompt": body.question.prompt,
            "answer_options": _normalize_options(body.question.answer_options),
        },
        "start_time": start_time,
        "lock_time": lock_time,
        "resolve_by": resolve_by,
        "winner_rules_json": body.winner_rules.model_dump(),
        "data_provider_id": provider_id,
        "compliance_settings_id": body.compliance_settings_id,
        "external_market_id": body.external_market_id,
        "approval_status": "draft",
        "approval_reason": None,
        "approved_by": None,
        "approved_at": None,
        "rejected_by": None,
        "rejected_at": None,
        "status": "draft",
        "created_by": admin["user_id"],
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    await db.predict_win_campaigns.insert_one(doc)
    return {"ok": True, "campaign": _serialize_campaign(doc)}


@router.get("/campaigns")
async def list_campaigns(
    request: Request,
    status: Optional[str] = Query(None),
    approval_status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _a: dict = Depends(require_admin),
):
    db = request.app.state.db
    q: Dict[str, Any] = {"deleted_at": None}
    if status:
        if status not in LIFECYCLE_STATES:
            raise HTTPException(400, f"status must be one of {sorted(LIFECYCLE_STATES)}")
        q["status"] = status
    if approval_status:
        if approval_status not in APPROVAL_STATES:
            raise HTTPException(
                400, f"approval_status must be one of {sorted(APPROVAL_STATES)}"
            )
        q["approval_status"] = approval_status
    if event_type:
        q["event_type"] = event_type
    cur = db.predict_win_campaigns.find(q).sort("created_at", -1).limit(limit)
    items = []
    async for d in cur:
        prize_count = await db.predict_win_prizes.count_documents(
            {"campaign_id": d["campaign_id"], "active": True}
        )
        entry_count = await db.predict_win_entries.count_documents(
            {"campaign_id": d["campaign_id"]}
        )
        item = _strip_mongo(d)
        item["prize_count"] = prize_count
        item["entry_count"] = entry_count
        items.append(item)
    return {"items": items, "count": len(items)}


@router.get("/approval-queue")
async def approval_queue(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    _a: dict = Depends(require_admin),
):
    """Filter view: campaigns awaiting human review (approval_status =
    pending_review).  No new collection — just a query filter."""
    db = request.app.state.db
    cur = (
        db.predict_win_campaigns.find(
            {"approval_status": "pending_review", "deleted_at": None}
        )
        .sort("updated_at", 1)
        .limit(limit)
    )
    items = []
    async for d in cur:
        prize_count = await db.predict_win_prizes.count_documents(
            {"campaign_id": d["campaign_id"], "active": True}
        )
        item = _strip_mongo(d)
        item["prize_count"] = prize_count
        items.append(item)
    return {"items": items, "count": len(items)}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str, request: Request, _a: dict = Depends(require_admin)
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    prizes_cur = db.predict_win_prizes.find(
        {"campaign_id": campaign_id, "active": True}
    ).sort("rank", 1)
    prizes = [_strip_mongo(p) async for p in prizes_cur]
    compliance = None
    if c.get("compliance_settings_id"):
        cs = await db.prediction_compliance_settings.find_one(
            {"settings_id": c["compliance_settings_id"]}
        )
        if cs:
            compliance = _strip_mongo(cs)
    resolution = await db.predict_win_resolutions.find_one(
        {"campaign_id": campaign_id}
    )
    entry_count = await db.predict_win_entries.count_documents(
        {"campaign_id": campaign_id}
    )
    award_count = await db.predict_win_awards.count_documents(
        {"campaign_id": campaign_id}
    )
    return {
        "campaign": _serialize_campaign(c),
        "prizes": prizes,
        "compliance": compliance,
        "resolution": _strip_mongo(resolution) if resolution else None,
        "entry_count": entry_count,
        "award_count": award_count,
    }


@router.patch("/campaigns/{campaign_id}")
async def patch_campaign(
    campaign_id: str,
    body: CampaignPatchIn,
    request: Request,
    _a: dict = Depends(require_admin),
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["approval_status"] not in {"draft", "rejected"}:
        raise HTTPException(
            409,
            {
                "code": "campaign_locked_for_edit",
                "message": "Campaign can only be edited while approval_status "
                                "is 'draft' or 'rejected'.",
            },
        )
    update: Dict[str, Any] = {}
    if body.event_type is not None:
        _guard_event_type(body.event_type)
        update["event_type"] = body.event_type
    if body.question is not None:
        _guard_lexicon(
            body.question.prompt,
            *[o.label for o in body.question.answer_options],
        )
        update["question"] = {
            "prompt": body.question.prompt,
            "answer_options": _normalize_options(body.question.answer_options),
        }
    text_fields = ("title", "description", "event_label", "category", "city",
                              "region", "language", "cover_image_url")
    text_values = [getattr(body, k) for k in text_fields]
    _guard_lexicon(*[v for v in text_values if isinstance(v, str)])
    for k in text_fields:
        v = getattr(body, k)
        if v is not None:
            update[k] = v
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
    if body.resolve_by:
        update["resolve_by"] = _parse_iso(body.resolve_by)
    if body.winner_rules is not None:
        update["winner_rules_json"] = body.winner_rules.model_dump()
    if body.data_provider_id is not None:
        update["data_provider_id"] = body.data_provider_id
    if body.compliance_settings_id is not None:
        update["compliance_settings_id"] = body.compliance_settings_id
    # Cross-field check
    new_start = update.get("start_time", c.get("start_time"))
    new_lock = update.get("lock_time", c.get("lock_time"))
    if new_start and new_lock and new_start >= new_lock:
        raise HTTPException(400, "lock_time must be after start_time")
    update["updated_at"] = _now()
    # If campaign was rejected, editing should bounce it back to draft
    if c["approval_status"] == "rejected":
        update["approval_status"] = "draft"
        update["rejected_by"] = None
        update["rejected_at"] = None
        update["approval_reason"] = None
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id}, {"$set": update}
    )
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str, request: Request, admin: dict = Depends(require_admin)
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["status"] not in {"draft", "scheduled", "cancelled"}:
        raise HTTPException(
            409,
            {"code": "campaign_active",
              "message": "Cannot delete campaigns in live/locked/resolved state."},
        )
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"deleted_at": _now(), "updated_at": _now()}},
    )
    return {"ok": True, "deleted": True}


# ─── Prize routes ──────────────────────────────────────────────────────
@router.post("/campaigns/{campaign_id}/prizes")
async def add_prize(
    campaign_id: str,
    body: PrizeIn,
    request: Request,
    _a: dict = Depends(require_admin),
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["approval_status"] not in {"draft", "rejected"}:
        raise HTTPException(
            409,
            {"code": "campaign_locked_for_edit",
              "message": "Prizes can only be edited while campaign is in draft/rejected."},
        )
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


@router.get("/campaigns/{campaign_id}/prizes")
async def list_prizes(
    campaign_id: str, request: Request, _a: dict = Depends(require_admin)
):
    db = request.app.state.db
    await _get_campaign_or_404(db, campaign_id)
    cur = db.predict_win_prizes.find(
        {"campaign_id": campaign_id, "active": True}
    ).sort("rank", 1)
    items = [_strip_mongo(p) async for p in cur]
    return {"items": items, "count": len(items)}


@router.patch("/campaigns/{campaign_id}/prizes/{prize_id}")
async def patch_prize(
    campaign_id: str,
    prize_id: str,
    body: PrizeIn,
    request: Request,
    _a: dict = Depends(require_admin),
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["approval_status"] not in {"draft", "rejected"}:
        raise HTTPException(409, "campaign_locked_for_edit")
    _guard_lexicon(body.title, body.description)
    prize = await db.predict_win_prizes.find_one(
        {"prize_id": prize_id, "campaign_id": campaign_id}
    )
    if not prize:
        raise HTTPException(404, "prize_not_found")
    update = body.model_dump()
    new_inv = update["inventory_total"]
    consumed = (prize.get("inventory_total") or 0) - (prize.get("inventory_remaining") or 0)
    update["inventory_remaining"] = max(0, new_inv - consumed)
    update["updated_at"] = _now()
    await db.predict_win_prizes.update_one(
        {"prize_id": prize_id}, {"$set": update}
    )
    fresh = await db.predict_win_prizes.find_one({"prize_id": prize_id})
    return {"ok": True, "prize": _strip_mongo(fresh)}


@router.delete("/campaigns/{campaign_id}/prizes/{prize_id}")
async def delete_prize(
    campaign_id: str,
    prize_id: str,
    request: Request,
    _a: dict = Depends(require_admin),
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["approval_status"] not in {"draft", "rejected"}:
        raise HTTPException(409, "campaign_locked_for_edit")
    res = await db.predict_win_prizes.update_one(
        {"prize_id": prize_id, "campaign_id": campaign_id},
        {"$set": {"active": False, "updated_at": _now()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "prize_not_found")
    return {"ok": True, "deleted": True}


# ─── Approval workflow ─────────────────────────────────────────────────
@router.post("/campaigns/{campaign_id}/submit-approval")
async def submit_for_approval(
    campaign_id: str, request: Request, _a: dict = Depends(require_admin)
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["approval_status"] != "draft":
        raise HTTPException(
            409,
            {"code": "invalid_state",
              "message": f"Cannot submit while approval_status={c['approval_status']}"},
        )
    await _validate_for_submit(db, campaign_id)
    now = _now()
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {
            "$set": {
                "approval_status": "pending_review",
                "updated_at": now,
            }
        },
    )
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}


@router.post("/campaigns/{campaign_id}/approve")
async def approve_campaign(
    campaign_id: str, request: Request, admin: dict = Depends(require_admin)
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["approval_status"] != "pending_review":
        raise HTTPException(
            409,
            {"code": "invalid_state",
              "message": f"Cannot approve from approval_status={c['approval_status']}"},
        )
    now = _now()
    start_time = c.get("start_time")
    if isinstance(start_time, datetime) and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    next_status = "live" if start_time and start_time <= now else "scheduled"
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {
            "$set": {
                "approval_status": "approved",
                "approved_by": admin["user_id"],
                "approved_at": now,
                "status": next_status,
                "rejected_by": None,
                "rejected_at": None,
                "approval_reason": None,
                "updated_at": now,
            }
        },
    )
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}


@router.post("/campaigns/{campaign_id}/reject")
async def reject_campaign(
    campaign_id: str,
    body: RejectIn,
    request: Request,
    admin: dict = Depends(require_admin),
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["approval_status"] != "pending_review":
        raise HTTPException(
            409,
            {"code": "invalid_state",
              "message": f"Cannot reject from approval_status={c['approval_status']}"},
        )
    now = _now()
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {
            "$set": {
                "approval_status": "rejected",
                "rejected_by": admin["user_id"],
                "rejected_at": now,
                "approval_reason": body.reason,
                "status": "draft",
                "updated_at": now,
            }
        },
    )
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}


# ─── Lifecycle: lock / force-resolve / cancel ──────────────────────────
@router.post("/campaigns/{campaign_id}/lock")
async def lock_campaign(
    campaign_id: str, request: Request, _a: dict = Depends(require_admin)
):
    """Manual live → locked transition.  Cron sweeper handles auto-lock
    in Phase E4; this endpoint is the admin override."""
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["status"] != "live":
        raise HTTPException(
            409,
            {"code": "invalid_state",
              "message": f"Can only lock from status=live (current={c['status']})"},
        )
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "locked", "updated_at": _now()}},
    )
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}


@router.post(
    "/campaigns/{campaign_id}/force-resolve",
    description=(
        "Admin override: forcibly resolve a campaign and write a "
        "`predict_win_resolutions` row with `result_source='manual_admin'`. "
        "Allowed from status in (`scheduled`, `live`, `locked`) — the "
        "`scheduled` case bypasses the scheduled→live transition because "
        "Sub-Phase E1 has no cron sweeper yet (that lands in E4) and admins "
        "must be able to drive the full lifecycle for testing, early "
        "cancellations, postponements, or collapsed prediction windows. "
        "Rejected from `draft` (campaign not yet approved) and from "
        "`resolved` / `cancelled` (terminal states) with HTTP 409."
    ),
)
async def force_resolve_campaign(
    campaign_id: str,
    body: ResolveIn,
    request: Request,
    admin: dict = Depends(require_admin),
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    # E1 fix (post-tester): force-resolve is an ADMIN OVERRIDE path.  The
    # name "force-resolve" implies the bypass — we let admins resolve from
    # any post-approval state (scheduled / live / locked), not just live or
    # locked.  Real-world drivers: event cancelled, postponed, or the
    # prediction window collapsed before lock_time elapsed.  Auto-resolution
    # via the cron sweeper still gates on live/locked when it lands in E4.
    ALLOWED_FORCE_RESOLVE_STATUSES = {"scheduled", "live", "locked"}
    if c["status"] not in ALLOWED_FORCE_RESOLVE_STATUSES:
        # Distinguish terminal vs not-yet-approved for a clearer error.
        if c["status"] in {"resolved", "cancelled"}:
            code = "campaign_status_terminal"
            message = (
                f"Cannot force-resolve a {c['status']} campaign — "
                f"this is a terminal state."
            )
        else:
            code = "campaign_not_approved"
            message = (
                f"Cannot force-resolve from status='{c['status']}'. "
                f"Approve the campaign first (allowed: "
                f"{sorted(ALLOWED_FORCE_RESOLVE_STATUSES)})."
            )
        raise HTTPException(409, {"code": code, "message": message})
    # Defence-in-depth: even at status=scheduled, the campaign MUST be
    # approved.  approval_status=approved is what gets us into `scheduled`
    # in the first place, but check explicitly so future state changes
    # don't accidentally open a hole.
    if c["approval_status"] != "approved":
        raise HTTPException(
            409,
            {"code": "campaign_not_approved",
              "message": "Campaign must be approved before force-resolve."},
        )
    options = (c.get("question") or {}).get("answer_options") or []
    valid_ids = {o["option_id"] for o in options}
    if body.winning_option_id not in valid_ids:
        raise HTTPException(
            400,
            {"code": "invalid_winning_option",
              "message": f"winning_option_id must be one of {sorted(valid_ids)}"},
        )
    existing_res = await db.predict_win_resolutions.find_one(
        {"campaign_id": campaign_id}
    )
    if existing_res:
        raise HTTPException(
            409,
            {"code": "campaign_already_resolved",
              "message": "Campaign has already been resolved; idempotent guard."},
        )
    now = _now()
    rid = _new_id("pwr")
    await db.predict_win_resolutions.insert_one(
        {
            "_id": rid,
            "resolution_id": rid,
            "campaign_id": campaign_id,
            "winning_option_id": body.winning_option_id,
            "resolved_by": admin["user_id"],
            "resolved_at": now,
            # `result_source` is the canonical field for who/what produced
            # this resolution.  E1 only supports manual_admin; E4 will add
            # `data_provider_auto` when the cron sweeper consults
            # `prediction_data_providers` (Predexon et al.).
            "result_source": "manual_admin",
            "data_source_url": body.data_source_url,
            "audit_notes": body.audit_notes,
            "audit_json": {
                "actor": admin["user_id"],
                "actor_email": admin.get("email"),
                "prior_status": c["status"],
                "options_at_resolve_time": options,
            },
        }
    )
    # Mark winning/losing entries (does not award prizes — that's Phase E2)
    await db.predict_win_entries.update_many(
        {"campaign_id": campaign_id, "picked_option_id": body.winning_option_id},
        {"$set": {"status": "winner", "evaluated_at": now}},
    )
    await db.predict_win_entries.update_many(
        {"campaign_id": campaign_id,
          "picked_option_id": {"$ne": body.winning_option_id}},
        {"$set": {"status": "loser", "evaluated_at": now}},
    )
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "resolved", "updated_at": now}},
    )
    # Sub-Phase E2 — fan-out awards (prizes + wallet items + bigcoin +
    # badges + notifications + analytics).  Synchronous; cron-driven
    # version lands in E4.
    pipeline_result: dict = {"ok": False, "skipped": True}
    try:
        from services.predict_win_award_pipeline import run_award_pipeline
        pipeline_result = await run_award_pipeline(
            db,
            campaign_id=campaign_id,
            winning_option_id=body.winning_option_id,
            resolution_id=rid,
        )
    except Exception as _e:
        logger.warning("Sub-Phase E2 award pipeline error for %s: %s",
                                  campaign_id, _e)
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    res_fresh = await db.predict_win_resolutions.find_one({"campaign_id": campaign_id})
    return {
        "ok": True,
        "campaign": _serialize_campaign(fresh),
        "resolution": _strip_mongo(res_fresh),
        "award_pipeline": pipeline_result,
    }


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: str,
    body: CancelIn,
    request: Request,
    admin: dict = Depends(require_admin),
):
    db = request.app.state.db
    c = await _get_campaign_or_404(db, campaign_id)
    if c["status"] in {"resolved", "cancelled"}:
        raise HTTPException(409, f"campaign_status_terminal:{c['status']}")
    now = _now()
    await db.predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {
            "$set": {
                "status": "cancelled",
                "updated_at": now,
            },
            "$push": {
                "cancellation_log": {
                    "actor": admin["user_id"],
                    "reason": body.reason,
                    "at": now.isoformat(),
                }
            },
        },
    )
    fresh = await db.predict_win_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True, "campaign": _serialize_campaign(fresh)}
