"""Phase 23 Session 2 — admin-creator campaign endpoint + submit validator.

The admin creator path is distinct from the advertiser path:
  • No advertiser_id required (admin acts on behalf of the platform)
  • Sets is_platform_funded=True + funded_source="bigfm_house"
  • Sets creator_type="admin"
  • Skips pending_approval — campaigns go straight to active when payload
    is complete (terms + prizes + valid dates), otherwise stay in draft
    so admin can complete via the existing PATCH flow.

Keeps existing routes/games_v2.py untouched per the "DO NOT touch core
listener-play path" rule.  Lives in a sibling file mounted under the same
prefix.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_admin


logger = logging.getLogger("bigfm.games_v2.admin_campaigns")

games_v2_admin_campaigns_router = APIRouter(
    prefix="/api/games_v2",
    tags=["games_v2_admin_campaigns_phase23"],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str, length: int = 14) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:length]}"


def _parse_iso(s) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


async def validate_for_submit(db, campaign_id: str) -> None:
    """Phase 23 S2 submit-validation harness.  Augments the existing
    games_v2 prize + compliance + targeting validators with date-sanity
    and minimum-completeness checks.  Raises ValueError on failure."""
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    # Date sanity
    start_at = c.get("start_at")
    end_at = c.get("end_at")
    if not end_at:
        raise ValueError("end_at_required")
    if start_at and end_at and start_at >= end_at:
        raise ValueError("start_must_precede_end")
    now = _now()
    end_norm = end_at
    if isinstance(end_norm, datetime) and end_norm.tzinfo is None:
        end_norm = end_norm.replace(tzinfo=timezone.utc)
    if isinstance(end_norm, datetime) and end_norm < now:
        raise ValueError("end_at_in_past")
    # At least 1 active prize
    prize_count = await db.game_prizes.count_documents(
        {"campaign_id": campaign_id, "active": True})
    if prize_count < 1:
        raise ValueError("at_least_one_prize_required")
    # Terms must be present in compliance_settings
    compliance = await db.game_compliance_settings.find_one(
        {"campaign_id": campaign_id}) or {}
    if not (compliance.get("terms_text") or "").strip():
        raise ValueError("terms_text_required")


@games_v2_admin_campaigns_router.post("/admin/campaigns")
async def admin_create_campaign(payload: dict, request: Request,
                                                        admin: dict = Depends(require_admin)):
    """Admin-creator path.  Platform-funded, auto-approved when complete.

    Required: template_id, title, end_at, prizes (≥1), compliance.terms_text.
    Sets creator_type=admin, is_platform_funded=True, funded_source=
    `bigfm_house`, and status="active" when validation passes (else
    "draft" so admin can complete via PATCH /advertiser/campaigns/{id} —
    that path's admin-bypass already allows it).
    """
    db = request.app.state.db
    if not isinstance(payload, dict):
        raise HTTPException(400, "body_must_be_object")
    template_id = (payload or {}).get("template_id")
    if not template_id:
        raise HTTPException(400, "template_id_required")
    tpl = await db.game_templates.find_one({"template_id": template_id})
    if not tpl or not tpl.get("active"):
        raise HTTPException(400, "template_not_active")

    cid = _new_id("cmp", 14)
    now = _now()
    base_cfg = dict(tpl.get("default_config_json") or {})
    incoming_cfg = (payload or {}).get("game_config_json") or {}
    base_cfg.update(incoming_cfg)
    doc = {
        "_id": cid, "campaign_id": cid,
        "advertiser_id": None,
        "business_id": (payload or {}).get("business_id"),
        "template_id": template_id,
        "title": (payload or {}).get("title") or "Untitled platform campaign",
        "description": (payload or {}).get("description"),
        "sponsor_name": (payload or {}).get("sponsor_name") or "RadioLife",
        "sponsor_logo_url": (payload or {}).get("sponsor_logo_url"),
        "brand_colors_json": (payload or {}).get("brand_colors_json") or {},
        "game_config_json": base_cfg,
        "objective": (payload or {}).get("objective") or "platform_engagement",
        "budget_cents": (payload or {}).get("budget_cents") or 0,
        "bid_type": (payload or {}).get("bid_type") or "per_save",
        "bid_amount_cents": (payload or {}).get("bid_amount_cents") or 0,
        "start_at": _parse_iso((payload or {}).get("start_at")) or now,
        "end_at": _parse_iso((payload or {}).get("end_at")),
        "targeting_json": (payload or {}).get("targeting_json") or {},
        # Phase 23 Session 2 — wizard columns
        "placement_rules_json": (payload or {}).get("placement_rules_json") or {},
        "eligibility_rules_json": (payload or {}).get("eligibility_rules_json") or {},
        "win_rules_json": (payload or {}).get("win_rules_json") or {},
        "creator_type": "admin",
        "status": "draft",
        "is_platform_funded": True,
        "funded_source": (payload or {}).get("funded_source") or "bigfm_house",
        "open_to_all": True,
        "created_by_user_id": admin["user_id"],
        "created_at": now, "updated_at": now,
        "approved_by_user_id": admin["user_id"],
        "approved_at": now,
        "rejection_reason": None,
    }
    await db.game_campaigns.insert_one(doc)

    # Prizes
    prizes = (payload or {}).get("prizes") or []
    for p in prizes:
        pid = _new_id("prz")
        await db.game_prizes.insert_one({
            "_id": pid, "prize_id": pid,
            "campaign_id": cid,
            "prize_type": p.get("prize_type") or "bigcoin",
            "title": p.get("title") or "Prize",
            "description": p.get("description"),
            "value_amount": p.get("value_amount"),
            "value_currency": p.get("value_currency"),
            "probability_weight": int(p.get("probability_weight") or 0),
            "inventory_total": int(p.get("inventory_total") or 0),
            "inventory_remaining": int(p.get("inventory_total") or 0),
            "max_per_user": int(p.get("max_per_user") or 0),
            "redemption_method": p.get("redemption_method") or "in_app_wallet",
            "requires_location": bool(p.get("requires_location")),
            "requires_staff_validation": bool(p.get("requires_staff_validation")),
            "expiration_policy_json": p.get("expiration_policy_json") or
                {"days_after_award": 30, "hard_expiry_at": None},
            "linked_offer_id": p.get("linked_offer_id"),
            "linked_badge_id": p.get("linked_badge_id"),
            "active": True, "created_at": now,
        })

    # Redemption rules + compliance (admin path mirrors advertiser path)
    rules = (payload or {}).get("redemption_rules") or {}
    await db.game_redemption_rules.replace_one(
        {"campaign_id": cid},
        {"_id": cid, "campaign_id": cid,
          "one_time_use": bool(rules.get("one_time_use", True)),
          "requires_qr": bool(rules.get("requires_qr", False)),
          "requires_location": bool(rules.get("requires_location", False)),
          "requires_staff_validation": bool(rules.get("requires_staff_validation", False)),
          "expiration_days": int(rules.get("expiration_days") or 30),
          "terms_url": rules.get("terms_url"),
          "odds_disclosure_text": rules.get("odds_disclosure_text"),
          "no_purchase_necessary_text": rules.get("no_purchase_necessary_text"),
          "age_restriction": rules.get("age_restriction"),
          "geo_restrictions_json": rules.get("geo_restrictions_json") or {"allowed_countries": ["*"]},
          "created_at": now, "updated_at": now},
        upsert=True,
    )
    compliance = (payload or {}).get("compliance") or {}
    await db.game_compliance_settings.replace_one(
        {"campaign_id": cid},
        {"_id": cid, "campaign_id": cid,
          "terms_text": compliance.get("terms_text"),
          "odds_disclosure": compliance.get("odds_disclosure"),
          "no_purchase_necessary_text": compliance.get("no_purchase_necessary_text"),
          "age_restriction": compliance.get("age_restriction"),
          "geo_restrictions_json": compliance.get("geo_restrictions_json") or
              {"allowed_countries": ["*"]},
          "approval_status": "approved",
          "approved_by": admin["user_id"],
          "approved_at": now, "rejection_notes": None},
        upsert=True,
    )

    # Auto-activate if validate_for_submit passes; otherwise leave as draft
    auto_activated = False
    try:
        await validate_for_submit(db, cid)
        await db.game_campaigns.update_one(
            {"campaign_id": cid},
            {"$set": {"status": "active", "updated_at": _now()}})
        auto_activated = True
    except ValueError as e:
        # Stays as draft; admin can complete + auto-activate via PATCH or
        # via the existing submit_for_approval flow's admin-bypass.
        logger.info("admin_create_campaign draft-only "
                       "campaign=%s reason=%s", cid, e)

    return {"ok": True, "campaign_id": cid,
              "creator_type": "admin",
              "auto_activated": auto_activated,
              "status": "active" if auto_activated else "draft"}


# =====================================================================
# Phase 23 Session 5 — moderation workspace
# =====================================================================
from services.games_v2_audit_log import (
    REJECT_REASON_CODES,
    write_audit_log,
    stats_cache_get, stats_cache_set, stats_cache_bust,
)


@games_v2_admin_campaigns_router.get("/admin/campaigns/queue-stats")
async def admin_queue_stats(request: Request,
                                                  _u: dict = Depends(require_admin)):
    """4-metric strip for the admin moderation page.  60s TTL cache."""
    cached = stats_cache_get()
    if cached is not None:
        return {**cached, "cached": True}

    db = request.app.state.db
    today_midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    pending = await db.game_campaigns.count_documents(
        {"status": "pending_approval"})
    approved_today = await db.game_campaigns.count_documents(
        {"status": "active",
          "approved_at": {"$gte": today_midnight}})
    rejected_today = await db.game_campaigns.count_documents(
        {"status": "rejected",
          "rejected_at": {"$gte": today_midnight}})

    # Median minutes between created_at and approved_at/rejected_at,
    # last 7 days.
    decision_minutes: list[float] = []
    async for c in db.game_campaigns.find({
            "$or": [{"approved_at": {"$gte": week_ago}},
                          {"rejected_at": {"$gte": week_ago}}],
        }, {"created_at": 1, "approved_at": 1, "rejected_at": 1}):
        decided_at = c.get("approved_at") or c.get("rejected_at")
        created_at = c.get("created_at")
        if not (decided_at and created_at):
            continue
        # Normalize to aware datetimes (motor sometimes returns naive).
        if decided_at.tzinfo is None:
            decided_at = decided_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        delta_s = (decided_at - created_at).total_seconds()
        if delta_s >= 0:
            decision_minutes.append(delta_s / 60.0)
    if decision_minutes:
        decision_minutes.sort()
        n = len(decision_minutes)
        avg_decision_minutes = (decision_minutes[n // 2] if n % 2 == 1
                                                else (decision_minutes[n//2 - 1]
                                                          + decision_minutes[n//2]) / 2.0)
        avg_decision_minutes = round(avg_decision_minutes, 1)
    else:
        avg_decision_minutes = None

    out = {
        "pending":                          pending,
        "approved_today":          approved_today,
        "rejected_today":          rejected_today,
        "avg_decision_minutes": avg_decision_minutes,
        "cached":                            False,
    }
    stats_cache_set({k: v for k, v in out.items() if k != "cached"})
    return out


@games_v2_admin_campaigns_router.get("/admin/campaigns/reject-reasons")
async def admin_reject_reasons(_u: dict = Depends(require_admin)):
    """Canonical reason taxonomy for the reject modal dropdown."""
    return {"reasons": [{"code": k, "label": v}
                                          for k, v in REJECT_REASON_CODES.items()]}


@games_v2_admin_campaigns_router.get(
    "/admin/campaigns/{campaign_id}/detail")
async def admin_campaign_detail(campaign_id: str, request: Request,
                                                    _u: dict = Depends(require_admin)):
    """Drawer-mode detail: campaign + prizes + targeting +
    placement_rules + win-rate math strip."""
    db = request.app.state.db
    c  = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    prizes = await db.game_prizes.find(
        {"campaign_id": campaign_id}).to_list(50)
    rules = await db.game_redemption_rules.find_one(
        {"campaign_id": campaign_id}) or {}
    compliance = await db.game_compliance_settings.find_one(
        {"campaign_id": campaign_id}) or {}
    # Win-rate math
    total_weight = sum(int(p.get("probability_weight") or 0) for p in prizes) or 1
    expected_payout_per_play = sum(
        (float(p.get("value_amount") or 0)
          * int(p.get("probability_weight") or 0) / total_weight)
        for p in prizes)
    max_total_redemptions = sum(int(p.get("inventory_total") or 0) for p in prizes)
    expected_redemption_cost = round(
        expected_payout_per_play * max_total_redemptions, 2)
    max_budget_cents = c.get("budget_cents") or 0
    max_budget = round(max_budget_cents / 100.0, 2)
    over_budget_pct = None
    if max_budget > 0 and expected_redemption_cost > 1.2 * max_budget:
        over_budget_pct = round(
            (expected_redemption_cost / max_budget - 1) * 100, 1)

    # Advertiser name
    adv_name = None
    if c.get("advertiser_id"):
        adv = await db.users.find_one(
            {"_id": c["advertiser_id"]}, {"name": 1, "email": 1})
        if adv:
            adv_name = adv.get("name") or adv.get("email")

    return {
        "campaign": {
            "campaign_id":         c["campaign_id"],
            "title":                          c.get("title"),
            "advertiser_name":     adv_name,
            "advertiser_id":         c.get("advertiser_id"),
            "sponsor_name":         c.get("sponsor_name"),
            "template_id":             c.get("template_id"),
            "brand_colors_json": c.get("brand_colors_json") or {},
            "status":                        c.get("status"),
            "creator_type":            c.get("creator_type"),
            "created_at":              c["created_at"].isoformat()
                                                  if c.get("created_at") else None,
            "approved_at":            c["approved_at"].isoformat()
                                                  if c.get("approved_at") else None,
            "rejected_at":            c.get("rejected_at").isoformat()
                                                  if c.get("rejected_at") else None,
            "reject_reason_code":  c.get("reject_reason_code"),
            "reject_reason_notes": c.get("reject_reason_notes"),
        },
        "prizes": [{
            "prize_id":                  p.get("prize_id"),
            "title":                          p.get("title"),
            "value_amount":          p.get("value_amount"),
            "value_currency":      p.get("value_currency"),
            "probability_weight": int(p.get("probability_weight") or 0),
            "inventory_total":      int(p.get("inventory_total") or 0),
        } for p in prizes],
        "targeting":              c.get("targeting_json") or {},
        "placement_rules":  c.get("placement_rules_json") or {},
        "win_rules":              c.get("win_rules_json") or {},
        "compliance": {
            "terms_text": (compliance.get("terms_text") or "")[:280],
            "odds_disclosure": compliance.get("odds_disclosure"),
            "approval_status": compliance.get("approval_status"),
        },
        "math": {
            "total_weight":                          total_weight,
            "expected_payout_per_play":  round(expected_payout_per_play, 4),
            "max_total_redemptions":      max_total_redemptions,
            "expected_redemption_cost": expected_redemption_cost,
            "max_budget":                              max_budget,
            "over_budget_pct":                  over_budget_pct,
        },
    }


@games_v2_admin_campaigns_router.post(
    "/admin/campaigns/bulk-approve")
async def admin_bulk_approve(payload: dict, request: Request,
                                                      u: dict = Depends(require_admin)):
    """Multi-row approve.  Body: ``{campaign_ids: [str]}``.

    Returns ``{approved: [id], failed: [{id, reason}]}`` — partial
    success is reportable.  Each successful approval writes its own
    ``action='approve_bulk'`` audit row.  Sub-routine mirrors the
    single-approve path in games_v2.py to preserve side effects
    (compliance row, public slug minting).
    """
    db = request.app.state.db
    ids = (payload or {}).get("campaign_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "campaign_ids_required")
    if len(ids) > 100:
        raise HTTPException(400, "max_100_campaigns_per_batch")

    from services.games_v2 import ensure_public_slug

    approved: list[str] = []
    failed:      list[dict] = []
    now = _now()
    for cid in ids:
        try:
            c = await db.game_campaigns.find_one({"campaign_id": cid})
            if not c:
                failed.append({"id": cid, "reason": "not_found"})
                continue
            if c["status"] != "pending_approval":
                failed.append({"id": cid,
                                          "reason": f"not_pending:{c['status']}"})
                continue
            await db.game_campaigns.update_one(
                {"campaign_id": cid},
                {"$set": {"status": "active",
                                    "approved_by_user_id": u["user_id"],
                                    "approved_at": now,
                                    "updated_at": now}})
            await db.game_compliance_settings.update_one(
                {"campaign_id": cid},
                {"$set": {"approval_status": "approved",
                                    "approved_by": u["user_id"],
                                    "approved_at": now}})
            await ensure_public_slug(db, cid)
            await write_audit_log(db, campaign_id=cid,
                                                          action="approve_bulk",
                                                          actor_user_id=u["user_id"])
            approved.append(cid)
        except Exception as e:  # pragma: no cover (defensive)
            logger.exception("bulk_approve failed cid=%s", cid)
            failed.append({"id": cid, "reason": str(e)[:120]})

    # Bust the queue-stats cache so admins see fresh counters.
    stats_cache_bust()
    return {"approved": approved, "failed": failed,
                  "approved_count": len(approved),
                  "failed_count": len(failed)}
