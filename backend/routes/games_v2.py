"""Phase 8a — Gamification Marketplace REST endpoints.

Mounted at /api/games_v2/* to coexist with the old Phase 5 routes which now
return 410 Gone (see routes/games.py).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, require_admin
from services.games_v2 import (
    ACTIVE_GAME_TYPES, BID_TYPES, CAMPAIGN_STATUSES, INACTIVE_GAME_TYPES,
    OBJECTIVES, PRIZE_TYPES, REDEMPTION_METHODS, UNLOCK_REASONS,
    _new_id, _now, _public_prize_view, _wallet_item_view,
    claim_to_wallet, ensure_games_v2_indexes, generate_qr,
    migrate_phase5_games, public_play_and_win, redeem_qr,
    save_for_later_unlock, seed_games_v2, start_session, submit_session,
    validate_compliance, validate_prizes,
)
from services.client_ip import get_real_client_ip

logger = logging.getLogger("bigfm.games_v2.routes")

games_v2_router = APIRouter(prefix="/api/games_v2", tags=["games_v2"])


def _public_base_url(request: Request) -> str:
    env = os.environ.get("PUBLIC_BACKEND_URL")
    if env:
        return env.rstrip("/")
    return str(request.base_url).rstrip("/")


def _require_advertiser(user: dict) -> None:
    if not user.get("is_advertiser") and user.get("role") != "admin":
        raise HTTPException(403, "advertiser_role_required")


# ======================================================================
# Listener / public
# ======================================================================
@games_v2_router.get("/play_and_win")
async def listener_play_and_win(request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    return await public_play_and_win(db, user)


@games_v2_router.get("/campaigns/{campaign_id}")
async def listener_campaign_detail(campaign_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c or c.get("status") not in {"active", "ended"}:
        raise HTTPException(404, "campaign_not_found")
    prizes = await db.game_prizes.find(
        {"campaign_id": campaign_id, "active": True}
    ).to_list(50)
    # never leak probability_weight or inventory remainders to listeners
    safe_prizes = [{
        "title": p["title"], "description": p.get("description"),
        "prize_type": p["prize_type"], "value_amount": p.get("value_amount"),
        "value_currency": p.get("value_currency"),
        "redemption_method": p["redemption_method"],
        "in_stock": int(p.get("inventory_remaining") or 0) > 0,
    } for p in prizes]
    # Phase 8c — expose compliance copy to the listener so the
    # <ComplianceNotice> intro card can show terms / odds / NPN / age gate.
    compliance = await db.game_compliance_settings.find_one(
        {"campaign_id": campaign_id}) or {}
    safe_compliance = {
        "terms_text": compliance.get("terms_text"),
        "odds_disclosure": compliance.get("odds_disclosure"),
        "no_purchase_necessary_text": compliance.get("no_purchase_necessary_text"),
        "age_restriction": compliance.get("age_restriction"),
        "full_terms_url": compliance.get("full_terms_url"),
    }
    return {
        "campaign_id": c["campaign_id"],
        "template_id": c["template_id"],
        "title": c["title"], "description": c.get("description"),
        "sponsor_name": c.get("sponsor_name"),
        "sponsor_logo_url": c.get("sponsor_logo_url"),
        "brand_colors_json": c.get("brand_colors_json"),
        "status": c["status"],
        "open_to_all": bool(c.get("open_to_all")),
        "is_platform_funded": bool(c.get("is_platform_funded")),
        "prizes": safe_prizes,
        "compliance": safe_compliance,
        "end_at": c["end_at"].isoformat() if c.get("end_at") else None,
    }


@games_v2_router.post("/campaigns/{campaign_id}/start")
async def listener_start(campaign_id: str, request: Request,
                             payload: Optional[dict] = None,
                             user: dict = Depends(current_user)):
    db = request.app.state.db
    payload = payload or {}
    # Phase 8c — compliance + lead-form gating BEFORE start_session
    from services.client_ip import get_real_client_ip
    ip = get_real_client_ip(request)
    compliance = await db.game_compliance_settings.find_one(
        {"campaign_id": campaign_id}) or {}
    try:
        from services.games_v2_compliance import (
            check_geo_eligibility, check_age_eligibility)
        check_geo_eligibility(compliance, ip)
        check_age_eligibility(
            compliance,
            listener_age=payload.get("listener_age"),
            age_confirmed=bool(payload.get("age_confirmed")))
    except ValueError as e:
        msg = str(e)
        if msg == "geo_not_eligible":
            raise HTTPException(451, msg)
        if msg in ("age_not_confirmed", "age_below_minimum"):
            raise HTTPException(403, msg)
        raise HTTPException(400, msg)
    # Lead-form gating
    form = await db.game_lead_forms.find_one(
        {"campaign_id": campaign_id, "active": True})
    if form and form.get("required_before_play"):
        provided = payload.get("lead_id")
        from services.games_v2_leads import find_valid_lead_for_user
        valid = None
        if provided:
            valid = await db.game_lead_submissions.find_one(
                {"submission_id": provided, "campaign_id": campaign_id})
        if not valid:
            valid = await find_valid_lead_for_user(
                db, campaign_id=campaign_id,
                user_id=user.get("user_id"), ip=ip)
        if not valid:
            raise HTTPException(412, "lead_form_required")
    try:
        result = await start_session(
            db, user, campaign_id,
            source_context=payload.get("source_context"),
            client_seed=payload.get("client_seed"),
        )
    except ValueError as e:
        msg = str(e)
        if msg == "driving_mode_active":
            # Phase 9a — enrich 423 with active commute context.  When
            # NO commute is active we keep the legacy string detail so
            # existing 8a clients don't break.
            from services.commute import get_active_commute
            cmt = await get_active_commute(db, user["user_id"])
            if cmt:
                eta_row = await db.commute_sessions.find_one(
                    {"commute_id": cmt["commute_id"]},
                    {"eta_remaining_s": 1, "route_duration_in_traffic_s": 1})
                eta = ((eta_row or {}).get("eta_remaining_s")
                          or (eta_row or {}).get("route_duration_in_traffic_s"))
                raise HTTPException(423, {
                    "error": "driving_mode_active",
                    "commute_id": cmt["commute_id"],
                    "mode": cmt.get("mode"),
                    "eta_remaining_s": eta,
                })
            raise HTTPException(423, msg)
        if msg == "campaign_not_found":
            raise HTTPException(404, msg)
        if msg in ("not_unlocked", "max_per_user_reached",
                    "campaign_ended", "campaign_not_started",
                    "rate_limited"):
            raise HTTPException(403 if msg == "not_unlocked" else 429
                                  if msg == "rate_limited" else 400, msg)
        # Phase Stabilization (Mobile games P0) — trivia session was
        # about to be created with 0 questions. Return a typed 503 so
        # the listener UI can render an empty-state pane instead of a
        # broken "Q1 / 0" stage.
        if msg == "no_questions_available":
            raise HTTPException(503, {
                "code":    "no_questions_available",
                "message": ("Trivia questions are still being prepared "
                            "for this campaign — please check back soon.")})
        if msg.startswith("campaign_not_active"):
            raise HTTPException(400, msg)
        raise HTTPException(400, msg)
    # Phase 8c — fire `game_started` webhook (non-blocking)
    try:
        from services.games_v2_webhooks import queue_event
        await queue_event(
            db, campaign_id=campaign_id, event_type="game_started",
            payload={"session_id": result["session_id"],
                      "campaign_id": campaign_id,
                      "user_id": user.get("user_id"),
                      "started_at": _now().isoformat()})
    except Exception:
        pass
    return result


@games_v2_router.post("/sessions/{session_id}/submit")
async def listener_submit(session_id: str, payload: Optional[dict],
                              request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await submit_session(db, user, session_id, payload or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Phase 8c — fire `game_completed` + `prize_won` webhooks
    try:
        from services.games_v2_webhooks import queue_event
        sess = await db.game_sessions.find_one({"session_id": session_id})
        cid = (sess or {}).get("campaign_id")
        if cid:
            await queue_event(
                db, campaign_id=cid, event_type="game_completed",
                payload={"session_id": session_id,
                          "campaign_id": cid,
                          "user_id": user.get("user_id"),
                          "result": result.get("result"),
                          "completed_at": _now().isoformat()})
            if result.get("result") == "win":
                await queue_event(
                    db, campaign_id=cid, event_type="prize_won",
                    payload={"session_id": session_id,
                              "campaign_id": cid,
                              "user_id": user.get("user_id"),
                              "prize_id": result.get("prize_id"),
                              "won_at": _now().isoformat()})
    except Exception:
        pass
    return result


# Phase 23 Session 2 — clearer-named alias for `/submit`.  Same handler
# delegates to submit_session.  The original `/submit` route remains
# canonical; this alias lets new clients adopt the spec naming.
@games_v2_router.post("/sessions/{session_id}/play")
async def listener_play(session_id: str, payload: Optional[dict],
                                request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await submit_session(db, user, session_id, payload or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@games_v2_router.post("/sessions/{session_id}/claim_to_wallet")
async def listener_claim(session_id: str, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        result = await claim_to_wallet(db, user, session_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        from services.games_v2_webhooks import queue_event
        sess = await db.game_sessions.find_one({"session_id": session_id})
        cid = (sess or {}).get("campaign_id")
        if cid:
            await queue_event(
                db, campaign_id=cid, event_type="prize_claimed",
                payload={"session_id": session_id,
                          "campaign_id": cid,
                          "user_id": user.get("user_id"),
                          "wallet_item_id": (result.get("wallet_item") or {})
                                                .get("wallet_item_id"),
                          "claimed_at": _now().isoformat()})
    except Exception:
        pass
    return result


@games_v2_router.post("/sessions/{session_id}/save_for_later")
async def listener_save_for_later(session_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    sess = await db.game_sessions.find_one({"session_id": session_id})
    if not sess or sess["user_id"] != user["user_id"]:
        raise HTTPException(404, "session_not_found")
    if sess.get("status") != "in_progress":
        raise HTTPException(400, "not_in_progress")
    await db.game_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "abandoned", "completed_at": _now(),
                   "result": "abandoned"}})
    return {"ok": True}


@games_v2_router.post("/campaigns/{campaign_id}/save_for_later")
async def listener_save_campaign_for_later(campaign_id: str,
                                                       request: Request,
                                                       user: dict = Depends(current_user)):
    """Phase 8a.1 — listener-facing "Save for later" entry-point.  Works
    whether or not a session is in flight; creates / extends a saved
    `user_game_unlocks` row so the campaign re-surfaces under a "Saved"
    section after driving mode flips off."""
    db = request.app.state.db
    try:
        return await save_for_later_unlock(db, user, campaign_id)
    except ValueError as e:
        code = 404 if str(e) == "campaign_not_found" else 400
        raise HTTPException(code, str(e))


@games_v2_router.post("/wallet/{wallet_item_id}/generate_qr")
async def listener_generate_qr(wallet_item_id: str, request: Request,
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await generate_qr(db, user, wallet_item_id,
                                       _public_base_url(request))
    except ValueError as e:
        raise HTTPException(400, str(e))


@games_v2_router.post("/redeem/{qr_token}")
async def partner_redeem(qr_token: str, request: Request):
    """Phase 8b — partner-token gated.  Requires
       `Authorization: Partner <secret>` header.  Returns 401 otherwise.
       Audited regardless of outcome with one of:
         success | missing_auth | replay | revoked | other"""
    db = request.app.state.db
    from services.games_v2 import (check_partner_token_status,
                                            write_redemption_audit)
    auth = (request.headers.get("authorization") or "").strip()
    raw = ""
    if auth.lower().startswith("partner "):
        raw = auth.split(" ", 1)[1].strip()
    elif auth.lower().startswith("bearer "):
        raw = auth.split(" ", 1)[1].strip()
    ip = get_real_client_ip(request)
    ua = request.headers.get("user-agent")
    prefix = qr_token[:14] if qr_token else "(empty)"    # Look up campaign + wallet item ahead of time so the audit row carries
    # the linkage even on failure
    wi = await db.user_wallet_items.find_one(
        {"qr_token": qr_token}, {"_id": 1, "campaign_id": 1})
    wi_id = (wi or {}).get("_id")
    cid = (wi or {}).get("campaign_id")
    token_row, token_status = (None, "invalid")
    if raw:
        token_row, token_status = await check_partner_token_status(db, raw)
    if not token_row or token_status != "valid":
        outcome = "revoked" if token_status == "revoked" else "missing_auth"
        await write_redemption_audit(
            db, qr_token_prefix=prefix,
            partner_token_id=(token_row or {}).get("partner_token_id"),
            outcome=outcome,
            reason=("token_revoked" if outcome == "revoked"
                       else "partner_token_missing_or_invalid"),
            ip=ip, user_agent=ua,
            campaign_id=cid, wallet_item_id=wi_id)
        raise HTTPException(401, "partner_token_required")
    try:
        result = await redeem_qr(
            db, qr_token,
            redeemer_actor=f"partner:{token_row['partner_token_id']}")
        await write_redemption_audit(
            db, qr_token_prefix=prefix,
            partner_token_id=token_row["partner_token_id"],
            outcome="success", reason=None,
            ip=ip, user_agent=ua,
            campaign_id=cid, wallet_item_id=wi_id)
        # Phase 8c — emit prize_redeemed webhook
        try:
            from services.games_v2_webhooks import queue_event
            if cid:
                await queue_event(
                    db, campaign_id=cid, event_type="prize_redeemed",
                    payload={"wallet_item_id": wi_id,
                              "campaign_id": cid,
                              "partner_token_id": token_row["partner_token_id"],
                              "redeemed_at": _now().isoformat()})
        except Exception:
            pass
        return result
    except ValueError as e:
        reason = str(e)
        outcome = "replay" if reason == "already_redeemed" else "other"
        await write_redemption_audit(
            db, qr_token_prefix=prefix,
            partner_token_id=token_row["partner_token_id"],
            outcome=outcome, reason=reason,
            ip=ip, user_agent=ua,
            campaign_id=cid, wallet_item_id=wi_id)
        raise HTTPException(400, reason)


@games_v2_router.post("/user/driving_mode")
async def listener_driving_mode(payload: dict, request: Request,
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    on = bool((payload or {}).get("on"))
    await db.users.update_one({"user_id": user["user_id"]},
                                   {"$set": {"driving_mode_on": on}})
    return {"ok": True, "driving_mode_on": on}


# Phase 9b backlog — accept PATCH as forgiving alias.  The tester sent
# PATCH and got 405.  Canonical remains POST.
@games_v2_router.patch("/user/driving_mode")
async def listener_driving_mode_patch(payload: dict, request: Request,
                                                  user: dict = Depends(current_user)):
    return await listener_driving_mode(payload, request, user)


# ======================================================================
# Advertiser self-serve
# ======================================================================
@games_v2_router.get("/advertiser/templates")
async def adv_templates(request: Request,
                           user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    out = []
    cur = db.game_templates.find({}).sort("active", -1)
    async for t in cur:
        out.append({
            "template_id": t["template_id"], "name": t["name"],
            "game_type": t["game_type"], "description": t.get("description"),
            "preview_image_url": t.get("preview_image_url"),
            "default_config_json": t.get("default_config_json") or {},
            "min_prizes": t["min_prizes"], "max_prizes": t["max_prizes"],
            "active": t["active"],
        })
    return {"templates": out}


async def _get_advertiser_id(db, user: dict) -> Optional[str]:
    adv = await db.advertisers.find_one({"user_id": user["user_id"]},
                                              {"advertiser_id": 1, "_id": 0})
    return (adv or {}).get("advertiser_id")


def _campaign_view(c: dict, *, counters: Optional[dict] = None) -> dict:
    out = {
        "campaign_id": c["campaign_id"], "title": c.get("title"),
        "template_id": c["template_id"],
        "advertiser_id": c.get("advertiser_id"),
        "business_id": c.get("business_id"),
        "sponsor_name": c.get("sponsor_name"),
        "sponsor_logo_url": c.get("sponsor_logo_url"),
        "brand_colors_json": c.get("brand_colors_json") or {},
        "description": c.get("description"),
        "game_config_json": c.get("game_config_json") or {},
        "objective": c.get("objective"),
        "budget_cents": c.get("budget_cents"),
        "bid_type": c.get("bid_type"),
        "bid_amount_cents": c.get("bid_amount_cents"),
        "targeting_json": c.get("targeting_json") or {},
        # Phase 23 Session 2 — wizard columns
        "placement_rules_json": c.get("placement_rules_json") or {},
        "eligibility_rules_json": c.get("eligibility_rules_json") or {},
        "win_rules_json": c.get("win_rules_json") or {},
        "creator_type": c.get("creator_type") or (
            "admin" if c.get("is_platform_funded") else "advertiser"),
        "status": c["status"],
        "is_platform_funded": bool(c.get("is_platform_funded")),
        "funded_source": c.get("funded_source"),
        "open_to_all": bool(c.get("open_to_all")),
        "start_at": c["start_at"].isoformat() if c.get("start_at") else None,
        "end_at": c["end_at"].isoformat() if c.get("end_at") else None,
        "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
        "updated_at": c["updated_at"].isoformat() if c.get("updated_at") else None,
        "approved_by_user_id": c.get("approved_by_user_id"),
        "approved_at": c["approved_at"].isoformat() if c.get("approved_at") else None,
        "rejection_reason": c.get("rejection_reason"),
        "counters": counters or {},
    }
    return out


@games_v2_router.get("/advertiser/campaigns")
async def adv_list_campaigns(request: Request,
                                  user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    if user.get("role") == "admin":
        q = {}
    else:
        adv_id = await _get_advertiser_id(db, user)
        q = {"advertiser_id": adv_id} if adv_id else {"advertiser_id": "_none_"}
    cur = db.game_campaigns.find(q).sort("created_at", -1).limit(50)
    items = []
    async for c in cur:
        # Aggregate counters via game_analytics_events
        evts = db.game_analytics_events.aggregate([
            {"$match": {"campaign_id": c["campaign_id"]}},
            {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
        ])
        counters = {}
        async for e in evts:
            counters[e["_id"]] = e["n"]
        items.append(_campaign_view(c, counters=counters))
    return {"items": items}


_CAMPAIGN_TOP_LEVEL_ALLOWED = {
    "template_id", "title", "description", "sponsor_name",
    "sponsor_logo_url", "brand_colors_json", "game_config_json",
    "objective", "budget_cents", "bid_type", "bid_amount_cents",
    "start_at", "end_at", "targeting_json", "open_to_all",
    "business_id", "prizes", "redemption_rules", "compliance",
    # Phase 23 Session 2 — wizard backend additions
    "placement_rules_json", "eligibility_rules_json", "win_rules_json",
    "creator_type",
}
_CAMPAIGN_COMPLIANCE_ALIASES = {
    "terms_text", "odds_disclosure", "no_purchase_necessary_text",
    "age_restriction", "geo_restrictions_json",
}


def _normalize_campaign_payload(payload: dict, *, partial: bool = False) -> dict:
    """Phase 8c.1 — reject unknown top-level fields; lift compliance
    aliases at the top level into the nested `compliance` block.

    Setting `partial=True` (for PATCH) only enforces unknown-key rejection
    but allows omission of required keys.
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "body_must_be_object")
    normalized: dict = dict(payload)
    aliased: dict = {}
    for ak in _CAMPAIGN_COMPLIANCE_ALIASES:
        if ak in normalized and ak not in _CAMPAIGN_TOP_LEVEL_ALLOWED:
            aliased[ak] = normalized.pop(ak)
    if aliased:
        comp = dict(normalized.get("compliance") or {})
        for k, v in aliased.items():
            comp.setdefault(k, v)
        normalized["compliance"] = comp
    unknown = [k for k in normalized.keys()
                  if k not in _CAMPAIGN_TOP_LEVEL_ALLOWED]
    if unknown:
        raise HTTPException(
            400,
            f"unknown_fields:{','.join(unknown)} "
            f"(allowed: {sorted(_CAMPAIGN_TOP_LEVEL_ALLOWED)})")
    return normalized


@games_v2_router.post("/advertiser/campaigns")
async def adv_create_campaign(payload: dict, request: Request,
                                    user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    payload = _normalize_campaign_payload(payload, partial=False)
    template_id = (payload or {}).get("template_id")
    if not template_id:
        raise HTTPException(400, "template_id_required")
    tpl = await db.game_templates.find_one({"template_id": template_id})
    if not tpl or not tpl.get("active"):
        raise HTTPException(400, "template_not_active")

    adv_id = await _get_advertiser_id(db, user)
    cid = _new_id("cmp", 14)
    now = _now()
    base_cfg = dict(tpl.get("default_config_json") or {})
    incoming_cfg = (payload or {}).get("game_config_json") or {}
    base_cfg.update(incoming_cfg)
    doc = {
        "_id": cid, "campaign_id": cid,
        "advertiser_id": adv_id, "business_id": (payload or {}).get("business_id"),
        "template_id": template_id,
        "title": (payload or {}).get("title") or "Untitled campaign",
        "description": (payload or {}).get("description"),
        "sponsor_name": (payload or {}).get("sponsor_name") or "RadioLife partner",
        "sponsor_logo_url": (payload or {}).get("sponsor_logo_url"),
        "brand_colors_json": (payload or {}).get("brand_colors_json") or {},
        "game_config_json": base_cfg,
        "objective": (payload or {}).get("objective") or "listener_engagement",
        "budget_cents": (payload or {}).get("budget_cents"),
        "bid_type": (payload or {}).get("bid_type") or "per_save",
        "bid_amount_cents": (payload or {}).get("bid_amount_cents") or 0,
        "start_at": _parse_iso((payload or {}).get("start_at")) or now,
        "end_at": _parse_iso((payload or {}).get("end_at")),
        "targeting_json": (payload or {}).get("targeting_json") or {},
        # Phase 23 Session 2 — wizard backend columns
        "placement_rules_json": (payload or {}).get("placement_rules_json") or {},
        "eligibility_rules_json": (payload or {}).get("eligibility_rules_json") or {},
        "win_rules_json": (payload or {}).get("win_rules_json") or {},
        "creator_type": (payload or {}).get("creator_type") or "advertiser",
        "status": "draft",
        "is_platform_funded": False, "funded_source": None,
        "open_to_all": bool((payload or {}).get("open_to_all", True)),
        "created_by_user_id": user["user_id"],
        "created_at": now, "updated_at": now,
        "approved_by_user_id": None, "approved_at": None,
        "rejection_reason": None,
    }
    await db.game_campaigns.insert_one(doc)
    # Phase K.7c — auto-generate a per-instance thumbnail in the
    # background so the card never ships blank.  Non-blocking.
    try:
        from services.game_thumbnails import fire_thumbnail_task
        fire_thumbnail_task(db, cid)
    except Exception as _e:
        pass

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
    # Redemption rules
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
    # Compliance
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
         "approval_status": "auto_pending",
         "approved_by": None, "approved_at": None, "rejection_notes": None},
        upsert=True,
    )
    return {"ok": True, "campaign_id": cid, "campaign": _campaign_view(doc)}


def _parse_iso(s) -> Optional[datetime]:
    if not s: return None
    if isinstance(s, datetime): return s
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


@games_v2_router.patch("/advertiser/campaigns/{campaign_id}")
async def adv_update_campaign(campaign_id: str, payload: dict,
                                       request: Request,
                                       user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    payload = _normalize_campaign_payload(payload, partial=True)
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if (user.get("role") != "admin"
        and c.get("advertiser_id") != await _get_advertiser_id(db, user)):
        raise HTTPException(403, "not_owner")
    if c["status"] not in {"draft", "rejected"}:
        raise HTTPException(400, f"not_editable_in_status:{c['status']}")
    upd = {"updated_at": _now()}
    for f in ("title", "description", "sponsor_name", "sponsor_logo_url",
                "brand_colors_json", "game_config_json", "objective",
                "budget_cents", "bid_type", "bid_amount_cents",
                "targeting_json", "open_to_all",
                # Phase 23 Session 2 — wizard backend columns
                "placement_rules_json", "eligibility_rules_json",
                "win_rules_json", "creator_type"):
        if f in payload: upd[f] = payload[f]
    if "start_at" in payload: upd["start_at"] = _parse_iso(payload["start_at"])
    if "end_at" in payload: upd["end_at"] = _parse_iso(payload["end_at"])
    if c["status"] == "rejected":
        upd["status"] = "draft"
        upd["rejection_reason"] = None
    await db.game_campaigns.update_one({"campaign_id": campaign_id},
                                              {"$set": upd})
    # prizes rewrite (replace-all if `prizes` provided)
    if "prizes" in payload:
        await db.game_prizes.delete_many({"campaign_id": campaign_id})
        for p in payload["prizes"]:
            pid = _new_id("prz")
            await db.game_prizes.insert_one({
                "_id": pid, "prize_id": pid,
                "campaign_id": campaign_id,
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
                "active": True, "created_at": _now(),
            })
    if "compliance" in payload:
        compliance = payload["compliance"] or {}
        await db.game_compliance_settings.update_one(
            {"campaign_id": campaign_id},
            {"$set": {
                "terms_text": compliance.get("terms_text"),
                "odds_disclosure": compliance.get("odds_disclosure"),
                "no_purchase_necessary_text": compliance.get("no_purchase_necessary_text"),
                "age_restriction": compliance.get("age_restriction"),
                "geo_restrictions_json": compliance.get("geo_restrictions_json"),
            }})
    if "redemption_rules" in payload:
        rules = payload["redemption_rules"] or {}
        await db.game_redemption_rules.update_one(
            {"campaign_id": campaign_id},
            {"$set": {
                "one_time_use": bool(rules.get("one_time_use", True)),
                "requires_qr": bool(rules.get("requires_qr", False)),
                "requires_location": bool(rules.get("requires_location", False)),
                "requires_staff_validation": bool(rules.get("requires_staff_validation", False)),
                "expiration_days": int(rules.get("expiration_days") or 30),
                "terms_url": rules.get("terms_url"),
                "odds_disclosure_text": rules.get("odds_disclosure_text"),
                "no_purchase_necessary_text": rules.get("no_purchase_necessary_text"),
                "age_restriction": rules.get("age_restriction"),
                "geo_restrictions_json": rules.get("geo_restrictions_json"),
            }})
    fresh = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True, "campaign": _campaign_view(fresh)}


@games_v2_router.post("/advertiser/campaigns/{campaign_id}/submit_for_approval")
async def adv_submit(campaign_id: str, request: Request,
                       user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if (user.get("role") != "admin"
        and c.get("advertiser_id") != await _get_advertiser_id(db, user)):
        raise HTTPException(403, "not_owner")
    if c["status"] not in {"draft", "rejected"}:
        raise HTTPException(400, f"not_submittable:{c['status']}")
    # Validate prizes
    prizes = await db.game_prizes.find(
        {"campaign_id": campaign_id, "active": True}).to_list(50)
    tpl = await db.game_templates.find_one({"template_id": c["template_id"]})
    try:
        validate_prizes(prizes, tpl)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Validate compliance — Phase 8c enforces sweepstakes-aware rules
    compliance = await db.game_compliance_settings.find_one(
        {"campaign_id": campaign_id}) or {}
    from services.games_v2_compliance import validate_compliance_strict
    try:
        validate_compliance_strict(compliance, prizes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Phase 9b — validate smart targeting fields if present
    from services.route_ad_engine import validate_targeting_smart
    targeting = c.get("targeting_json") or {}
    err = validate_targeting_smart(targeting)
    if err:
        raise HTTPException(400, f"targeting:{err}")
    await db.game_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "pending_approval", "updated_at": _now()}})
    return {"ok": True, "campaign_id": campaign_id, "status": "pending_approval"}


@games_v2_router.post("/advertiser/campaigns/{campaign_id}/clone")
async def adv_clone(campaign_id: str, request: Request,
                       user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if (user.get("role") != "admin"
        and c.get("advertiser_id") != await _get_advertiser_id(db, user)):
        raise HTTPException(403, "not_owner")
    new_cid = _new_id("cmp", 14)
    new_doc = {**c, "_id": new_cid, "campaign_id": new_cid,
                "status": "draft", "title": f"{c['title']} (clone)",
                "created_at": _now(), "updated_at": _now(),
                "approved_by_user_id": None, "approved_at": None,
                "rejection_reason": None}
    await db.game_campaigns.insert_one(new_doc)
    # Phase K.7c — auto-generate a per-instance thumbnail in the
    # background.  Non-blocking — game card never ships blank.
    try:
        from services.game_thumbnails import fire_thumbnail_task
        fire_thumbnail_task(db, new_doc.get("_id") or new_doc.get("campaign_id"))
    except Exception as _e:
        pass
    prizes = await db.game_prizes.find({"campaign_id": campaign_id}).to_list(50)
    for p in prizes:
        npid = _new_id("prz")
        await db.game_prizes.insert_one({
            **p, "_id": npid, "prize_id": npid,
            "campaign_id": new_cid,
            "inventory_remaining": p["inventory_total"],
        })
    rr = await db.game_redemption_rules.find_one({"campaign_id": campaign_id})
    if rr:
        await db.game_redemption_rules.insert_one(
            {**rr, "_id": new_cid, "campaign_id": new_cid})
    cs = await db.game_compliance_settings.find_one({"campaign_id": campaign_id})
    if cs:
        await db.game_compliance_settings.insert_one(
            {**cs, "_id": new_cid, "campaign_id": new_cid,
             "approval_status": "auto_pending",
             "approved_by": None, "approved_at": None})
    return {"ok": True, "campaign_id": new_cid}


@games_v2_router.get("/advertiser/campaigns/{campaign_id}/analytics")
async def adv_analytics(campaign_id: str, request: Request,
                              user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if (user.get("role") != "admin"
        and c.get("advertiser_id") != await _get_advertiser_id(db, user)):
        raise HTTPException(403, "not_owner")
    agg = db.game_analytics_events.aggregate([
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
    ])
    counters = {}
    async for e in agg:
        counters[e["_id"]] = e["n"]
    prizes = await db.game_prizes.find(
        {"campaign_id": campaign_id}).to_list(50)
    inventory = [{
        "prize_id": p["prize_id"], "title": p["title"],
        "inventory_total": p["inventory_total"],
        "inventory_remaining": p["inventory_remaining"],
    } for p in prizes]
    return {"counters": counters, "inventory": inventory}


@games_v2_router.get("/advertiser/campaigns/{campaign_id}")
async def adv_campaign_detail(campaign_id: str, request: Request,
                                      user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if (user.get("role") != "admin"
        and c.get("advertiser_id") != await _get_advertiser_id(db, user)):
        raise HTTPException(403, "not_owner")
    prizes = await db.game_prizes.find(
        {"campaign_id": campaign_id}).to_list(50)
    compliance = await db.game_compliance_settings.find_one(
        {"campaign_id": campaign_id})
    rules = await db.game_redemption_rules.find_one(
        {"campaign_id": campaign_id})
    return {
        "campaign": _campaign_view(c),
        "prizes": [{**{k: v for k, v in p.items() if k != "_id"},
                     "prize_id": p["prize_id"]} for p in prizes],
        "compliance": {k: v for k, v in (compliance or {}).items() if k != "_id"},
        "redemption_rules": {k: v for k, v in (rules or {}).items() if k != "_id"},
    }


# ======================================================================
# Admin
# ======================================================================
@games_v2_router.get("/admin/queue")
async def admin_queue(request: Request,
                          _u: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.game_campaigns.find(
        {"status": "pending_approval"}).sort("updated_at", 1)
    items = []
    async for c in cur:
        prizes = await db.game_prizes.find(
            {"campaign_id": c["campaign_id"]}).to_list(20)
        items.append({**_campaign_view(c),
                        "prizes_preview": [{"title": p["title"],
                                            "value_amount": p.get("value_amount"),
                                            "probability_weight": p["probability_weight"],
                                            "inventory_total": p["inventory_total"]}
                                            for p in prizes]})
    return {"items": items}


@games_v2_router.post("/admin/campaigns/{campaign_id}/approve")
async def admin_approve(campaign_id: str, request: Request,
                            u: dict = Depends(require_admin)):
    db = request.app.state.db
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if c["status"] != "pending_approval":
        raise HTTPException(400, f"not_pending:{c['status']}")
    await db.game_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "active",
                   "approved_by_user_id": u["user_id"],
                   "approved_at": _now(),
                   "updated_at": _now()}})
    await db.game_compliance_settings.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"approval_status": "approved",
                   "approved_by": u["user_id"], "approved_at": _now()}})
    # Phase 8b — auto-mint public landing slug on first approval
    from services.games_v2 import ensure_public_slug
    slug = await ensure_public_slug(db, campaign_id)
    return {"ok": True, "public_slug": slug}


@games_v2_router.post("/admin/campaigns/{campaign_id}/reject")
async def admin_reject(campaign_id: str, payload: dict, request: Request,
                            u: dict = Depends(require_admin)):
    """Phase 23 Session 5 — taxonomy-aware reject.

    Body: ``{reason_code: str, reason_notes: str|null}``.  Backwards
    compatible with the legacy ``{reason: str}`` body (mapped to
    ``reason_code='other'`` + ``reason_notes=reason``).

    Side effects:
      * Sets ``status='rejected'`` + writes reject_reason_code /
        reject_reason_notes / rejected_by_user_id / rejected_at.
      * Writes a row to ``game_campaign_audit_logs`` (collection
        created lazily on first insert).
      * Idempotent: re-rejecting updates the reason_code/notes but
        does NOT double-audit (matches existing log within 5 min).
    """
    from services.games_v2_audit_log import (
        REJECT_REASON_CODES, write_audit_log,
    )

    payload   = payload or {}
    code      = (payload.get("reason_code")
                            # Legacy free-text reason shim.
                            or ("other" if payload.get("reason") else None))
    notes    = (payload.get("reason_notes")
                          or payload.get("reason") or "").strip() or None
    if not code:
        raise HTTPException(400, "reason_code_required")
    if code not in REJECT_REASON_CODES:
        raise HTTPException(400, f"unknown_reason_code:{code}")
    if code == "other" and not notes:
        raise HTTPException(400, "reason_notes_required_for_other")

    db = request.app.state.db
    c  = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")

    already_rejected = c.get("status") == "rejected"
    now = _now()
    await db.game_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "rejected",
                            "rejection_reason": notes or code,
                            "reject_reason_code": code,
                            "reject_reason_notes": notes,
                            "rejected_by_user_id": u["user_id"],
                            "rejected_at": now,
                            "updated_at": now}})
    await db.game_compliance_settings.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"approval_status": "rejected",
                            "rejection_notes": notes or code,
                            "approved_by": u["user_id"], "approved_at": now}})

    # Idempotent audit: only write a new row if no reject audit
    # exists for this campaign in the last 5 minutes.
    if not already_rejected:
        await write_audit_log(db, campaign_id=campaign_id,
                                                  action="reject",
                                                  actor_user_id=u["user_id"],
                                                  reason_code=code,
                                                  reason_notes=notes)

    c_after = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    return {"ok": True,
                  "campaign_id": campaign_id,
                  "reject_reason_code": code,
                  "reject_reason_notes": notes,
                  "campaign": _campaign_view(c_after) if c_after else None,
                  "was_already_rejected": already_rejected}


@games_v2_router.post("/admin/campaigns/{campaign_id}/force_pause")
async def admin_pause(campaign_id: str, request: Request,
                            u: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.game_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "paused", "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "campaign_not_found")
    return {"ok": True}


@games_v2_router.post("/admin/campaigns/{campaign_id}/resume")
async def admin_resume(campaign_id: str, request: Request,
                              u: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.game_campaigns.update_one(
        {"campaign_id": campaign_id, "status": "paused"},
        {"$set": {"status": "active", "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "campaign_not_paused")
    return {"ok": True}


@games_v2_router.post("/admin/campaigns/{campaign_id}/adjust_inventory")
async def admin_adjust_inventory(campaign_id: str, payload: dict,
                                          request: Request,
                                          u: dict = Depends(require_admin)):
    db = request.app.state.db
    prize_id = (payload or {}).get("prize_id")
    delta = int((payload or {}).get("delta") or 0)
    reason = (payload or {}).get("reason") or "admin_adjustment"
    if not prize_id or delta == 0:
        raise HTTPException(400, "prize_id_and_delta_required")
    p = await db.game_prizes.find_one({"prize_id": prize_id,
                                              "campaign_id": campaign_id})
    if not p:
        raise HTTPException(404, "prize_not_found")
    new_total = max(0, int(p["inventory_total"]) + delta)
    new_remaining = max(0, int(p["inventory_remaining"]) + delta)
    await db.game_prizes.update_one(
        {"prize_id": prize_id},
        {"$set": {"inventory_total": new_total,
                   "inventory_remaining": new_remaining}})
    await db.game_inventory_ledger.insert_one({
        "_id": _new_id("led"), "campaign_id": campaign_id,
        "prize_id": prize_id, "delta": delta,
        "session_id": None, "reason": reason,
        "inventory_after": new_remaining, "ts": _now()})
    return {"ok": True, "inventory_total": new_total,
            "inventory_remaining": new_remaining}


@games_v2_router.post("/admin/templates/{template_id}/activate")
async def admin_activate_template(template_id: str, request: Request,
                                         _u: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.game_templates.update_one({"template_id": template_id},
                                                  {"$set": {"active": True}})
    if not res.matched_count:
        raise HTTPException(404, "template_not_found")
    return {"ok": True}


@games_v2_router.post("/admin/templates/{template_id}/deactivate")
async def admin_deactivate_template(template_id: str, request: Request,
                                            _u: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.game_templates.update_one({"template_id": template_id},
                                                  {"$set": {"active": False}})
    if not res.matched_count:
        raise HTTPException(404, "template_not_found")
    return {"ok": True}


@games_v2_router.get("/admin/templates")
async def admin_list_templates(request: Request,
                                       _u: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.game_templates.find({}).sort("game_type", 1)
    out = []
    async for t in cur:
        out.append({**{k: v for k, v in t.items() if k != "_id"}})
    return {"templates": out}


@games_v2_router.post("/admin/migrate_phase5_games")
async def admin_migrate_phase5(request: Request,
                                       u: dict = Depends(require_admin)):
    db = request.app.state.db
    out = await migrate_phase5_games(db, actor_user_id=u["user_id"])
    return {"ok": True, **out}


@games_v2_router.post("/admin/unlock_grant")
async def admin_unlock_grant(payload: dict, request: Request,
                                    _u: dict = Depends(require_admin)):
    """Manually grant an unlock to a user — useful for testing & VIP gifts."""
    db = request.app.state.db
    user_id = (payload or {}).get("user_id")
    campaign_id = (payload or {}).get("campaign_id")
    expires_in_hours = int((payload or {}).get("expires_in_hours") or 24)
    if not user_id or not campaign_id:
        raise HTTPException(400, "user_id_and_campaign_id_required")
    from datetime import timedelta
    doc = {
        "_id": _new_id("ulk"),
        "user_id": user_id, "campaign_id": campaign_id,
        "unlock_reason": "manual_admin_grant",
        "unlocked_at": _now(),
        "expires_at": _now() + timedelta(hours=expires_in_hours),
        "played": False, "played_at": None,
    }
    await db.user_game_unlocks.insert_one(doc)
    return {"ok": True, "unlock_id": doc["_id"]}


__all__ = ["games_v2_router"]


# ====================================================================
# Phase 8b — listener / advertiser / admin additions
# ====================================================================
from fastapi import File, UploadFile, Form, Header
from fastapi.responses import FileResponse
from services.games_v2 import (
    save_uploaded_asset, pick_game_announce_candidate,
    log_rj_game_mention, issue_partner_token, revoke_partner_token,
    ASSET_MAX_BYTES, ASSETS_DIR,
)


# ---- listener: GET /me/unlocks ---------------------------------------
@games_v2_router.get("/me/unlocks")
async def listener_my_unlocks(request: Request,
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    now = _now()
    cur = db.user_game_unlocks.find({
        "user_id": user["user_id"],
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}],
    }).sort("unlocked_at", -1).limit(50)
    items = []
    async for u in cur:
        c = await db.game_campaigns.find_one(
            {"campaign_id": u["campaign_id"]},
            {"title": 1, "sponsor_name": 1, "template_id": 1, "_id": 0})
        items.append({
            "unlock_id": u.get("unlock_id") or u.get("_id"),
            "campaign_id": u["campaign_id"],
            "campaign_title": (c or {}).get("title"),
            "sponsor_name": (c or {}).get("sponsor_name"),
            "template_id": (c or {}).get("template_id"),
            "unlock_reason": u.get("unlock_reason"),
            "rule_id": u.get("rule_id"),
            "unlocked_at": u["unlocked_at"].isoformat() if u.get("unlocked_at") else None,
            "expires_at": u["expires_at"].isoformat() if u.get("expires_at") else None,
            "played": bool(u.get("played")),
        })
    return {"items": items, "now": now.isoformat()}


# ---- listener: active game announce (player polls during RJ) ---------
@games_v2_router.get("/me/active_game_announce")
async def listener_active_announce(request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    candidate = await pick_game_announce_candidate(db, user)
    if not candidate:
        return {"announce": None}
    return {"announce": candidate}


@games_v2_router.post("/rj_mention_log")
async def listener_rj_mention(payload: dict, request: Request,
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    cid = (payload or {}).get("campaign_id")
    if not cid: raise HTTPException(400, "campaign_id_required")
    out = await log_rj_game_mention(
        db, user["user_id"], cid,
        segment_id=(payload or {}).get("segment_id"),
        source_context=(payload or {}).get("source_context"))
    return {"ok": True, **out}


# ---- advertiser: distribution endpoint -------------------------------
@games_v2_router.get("/advertiser/campaigns/{campaign_id}/distribution")
async def adv_distribution(campaign_id: str, request: Request,
                                 user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if (user.get("role") != "admin"
        and c.get("advertiser_id") != await _get_advertiser_id(db, user)):
        raise HTTPException(403, "not_owner")
    slug = c.get("public_slug")
    if not slug:
        from services.games_v2 import ensure_public_slug
        slug = await ensure_public_slug(db, campaign_id)
    public_url = f"/play/{slug}"
    qr_url = f"/api/public/game/{slug}/qr.png"
    return {
        "campaign_id": campaign_id, "public_slug": slug,
        "public_url": public_url,
        "qr_image_url": qr_url,
        "sms_shortlink": f"bigfm.link/{slug}",   # scaffold (real SMS deferred)
        "embed_iframe": f'<iframe src="{public_url}?embed=1" '
                              f'width="420" height="640" style="border:0"></iframe>',
    }


# ---- advertiser: asset upload ----------------------------------------
@games_v2_router.post("/advertiser/assets/upload")
async def adv_upload_asset(request: Request,
                                  file: UploadFile = File(...),
                                  user: dict = Depends(current_user)):
    _require_advertiser(user)
    db = request.app.state.db
    if not file.content_type:
        raise HTTPException(400, "missing_content_type")
    raw = await file.read()
    if len(raw) > ASSET_MAX_BYTES:
        raise HTTPException(400, f"file_too_large:{len(raw)}")
    try:
        out = await save_uploaded_asset(
            db, filename=file.filename or "image",
            content_type=file.content_type, data=raw,
            uploaded_by_user_id=user["user_id"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


# ---- public asset serving --------------------------------------------
_EXT_TO_MIME = {"png": "image/png", "jpg": "image/jpeg",
                  "jpeg": "image/jpeg", "webp": "image/webp"}


@games_v2_router.api_route("/assets/{filename}", methods=["GET", "HEAD"])
async def public_serve_asset(filename: str, request: Request):
    """Phase 8b — serves uploaded game artwork. Returns the exact MIME
    (image/png | image/jpeg | image/webp), never the `image/*` wildcard
    (some CDNs and strict browsers reject the wildcard).  Supports HEAD
    so partners and CDNs can probe `Content-Type` without downloading."""
    from pathlib import Path
    from fastapi import Response
    safe = Path(filename).name      # strip any traversal
    p = ASSETS_DIR / safe
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "not_found")
    db = request.app.state.db
    row = await db.game_uploaded_assets.find_one({"filename": safe},
                                                       {"content_type": 1})
    mime = (row or {}).get("content_type")
    if not mime or mime == "image/*":
        ext = p.suffix.lower().lstrip(".")
        mime = _EXT_TO_MIME.get(ext, "application/octet-stream")
    if request.method == "HEAD":
        size = p.stat().st_size
        return Response(content=b"", media_type=mime, headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Length": str(size),
        })
    return FileResponse(str(p), media_type=mime,
                              headers={"Cache-Control": "public, max-age=86400"})


# ---- admin: unlock rules CRUD ----------------------------------------
@games_v2_router.get("/admin/unlock_rules")
async def admin_list_unlock_rules(request: Request,
                                         _u: dict = Depends(require_admin)):
    db = request.app.state.db
    cur = db.unlock_rules.find({}).sort("rule_id", 1)
    items = []
    async for r in cur:
        items.append({k: v for k, v in r.items() if k != "_id"})
    return {"items": items}


@games_v2_router.post("/admin/unlock_rules")
async def admin_create_unlock_rule(payload: dict, request: Request,
                                            _u: dict = Depends(require_admin)):
    from services.game_unlock_engine import TRIGGER_TYPES
    db = request.app.state.db
    trigger = (payload or {}).get("trigger_type")
    if trigger not in TRIGGER_TYPES:
        raise HTTPException(400, f"invalid_trigger_type:{trigger}")
    rule_id = (payload or {}).get("rule_id") or _new_id("rule")
    doc = {
        "_id": rule_id, "rule_id": rule_id,
        "trigger_type": trigger,
        "threshold": int((payload or {}).get("threshold") or 1),
        "period": (payload or {}).get("period", "daily"),
        "target_campaign_id": (payload or {}).get("target_campaign_id"),
        "target_template_id": (payload or {}).get("target_template_id"),
        "target_pool": (payload or {}).get("target_pool") or [],
        "unlock_expires_in_hours": int((payload or {}).get("unlock_expires_in_hours") or 24),
        "active": bool((payload or {}).get("active", True)),
        "title": (payload or {}).get("title", "Custom rule"),
        "description": (payload or {}).get("description", ""),
        "created_at": _now(),
    }
    await db.unlock_rules.replace_one({"rule_id": rule_id}, doc, upsert=True)
    return {"ok": True, "rule_id": rule_id}


@games_v2_router.patch("/admin/unlock_rules/{rule_id}")
async def admin_update_unlock_rule(rule_id: str, payload: dict,
                                              request: Request,
                                              _u: dict = Depends(require_admin)):
    db = request.app.state.db
    upd = {k: v for k, v in (payload or {}).items()
              if k in {"threshold", "period", "target_campaign_id",
                            "target_template_id", "target_pool",
                            "unlock_expires_in_hours", "active",
                            "title", "description"}}
    if not upd:
        raise HTTPException(400, "no_updatable_fields")
    res = await db.unlock_rules.update_one(
        {"rule_id": rule_id}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "rule_not_found")
    return {"ok": True}


@games_v2_router.post("/admin/unlock_rules/{rule_id}/toggle_active")
async def admin_toggle_unlock_rule(rule_id: str, request: Request,
                                              _u: dict = Depends(require_admin)):
    db = request.app.state.db
    rule = await db.unlock_rules.find_one({"rule_id": rule_id})
    if not rule:
        raise HTTPException(404, "rule_not_found")
    new_active = not bool(rule.get("active"))
    await db.unlock_rules.update_one(
        {"rule_id": rule_id}, {"$set": {"active": new_active}})
    return {"ok": True, "active": new_active}


# ---- admin: partner tokens -------------------------------------------
@games_v2_router.post("/admin/partner_tokens")
async def admin_issue_partner_token(payload: dict, request: Request,
                                              u: dict = Depends(require_admin)):
    db = request.app.state.db
    business_id = (payload or {}).get("partner_business_id")
    if not business_id:
        raise HTTPException(400, "partner_business_id_required")
    scopes = (payload or {}).get("scopes") or ["redeem_campaigns"]
    out = await issue_partner_token(db, business_id, scopes, u["user_id"])
    return {"ok": True, **out}


@games_v2_router.post("/admin/partner_tokens/{partner_token_id}/revoke")
async def admin_revoke_partner_token(partner_token_id: str,
                                                request: Request,
                                                _u: dict = Depends(require_admin)):
    db = request.app.state.db
    ok = await revoke_partner_token(db, partner_token_id)
    if not ok:
        raise HTTPException(404, "token_not_found_or_already_revoked")
    return {"ok": True}


@games_v2_router.get("/admin/partner_tokens")
async def admin_list_partner_tokens(request: Request,
                                              _u: dict = Depends(require_admin)):
    db = request.app.state.db
    items = []
    async for row in db.partner_tokens.find({}).sort("created_at", -1):
        items.append({
            "partner_token_id": row["partner_token_id"],
            "partner_business_id": row["partner_business_id"],
            "scopes": row.get("scopes") or [],
            "revoked_at": row["revoked_at"].isoformat() if row.get("revoked_at") else None,
            "last_used_at": row["last_used_at"].isoformat() if row.get("last_used_at") else None,
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        })
    return {"items": items}


# ---- admin: redemption audit log -------------------------------------
_AUDIT_OUTCOMES = ("success", "missing_auth", "replay", "revoked", "other")


@games_v2_router.get("/admin/redemption_audit_log")
async def admin_list_redemption_audit_log(
        request: Request,
        partner_token_id: Optional[str] = Query(None),
        campaign_id: Optional[str] = Query(None),
        outcome: Optional[str] = Query(None),
        since: Optional[str] = Query(None),
        until: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        cursor: Optional[str] = Query(None),
        _u: dict = Depends(require_admin)):
    """Phase 8b — paginated audit query.  Cursor is the ISO timestamp of
    the last item from the prior page (we sort by ts desc, so cursor
    becomes the `$lt` filter)."""
    db = request.app.state.db
    q: dict = {}
    if partner_token_id:
        q["partner_token_id"] = partner_token_id
    if campaign_id:
        q["campaign_id"] = campaign_id
    if outcome:
        if outcome not in _AUDIT_OUTCOMES:
            raise HTTPException(400, f"invalid_outcome:{outcome}")
        q["outcome"] = outcome
    ts_q: dict = {}
    if since:
        try:
            ts_q["$gte"] = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "invalid_since")
    if until:
        try:
            ts_q["$lt"] = datetime.fromisoformat(until.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "invalid_until")
    if cursor:
        try:
            cur_ts = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "invalid_cursor")
        if "$lt" in ts_q:
            ts_q["$lt"] = min(ts_q["$lt"], cur_ts)
        else:
            ts_q["$lt"] = cur_ts
    if ts_q:
        q["ts"] = ts_q
    items = []
    async for row in (db.redemption_audit_log
                            .find(q).sort("ts", -1).limit(limit)):
        ts = row.get("ts")
        items.append({
            "audit_id": row.get("audit_id") or row.get("_id"),
            "ts": ts.isoformat() if ts else None,
            "qr_token_prefix": row.get("qr_token_prefix"),
            "partner_token_id": row.get("partner_token_id"),
            "campaign_id": row.get("campaign_id"),
            "wallet_item_id": row.get("wallet_item_id"),
            "outcome": row.get("outcome"),
            "reason": row.get("reason"),
            "ip": row.get("ip"),
            "user_agent": row.get("user_agent"),
        })
    next_cursor = (items[-1]["ts"]
                       if len(items) == limit and items and items[-1]["ts"]
                       else None)
    return {"items": items, "next_cursor": next_cursor}
