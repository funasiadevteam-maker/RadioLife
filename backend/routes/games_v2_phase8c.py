"""Phase 8c — REST endpoints for lead forms, webhooks, leaderboard,
inventory reconciliation, and CSV exports.  Mounted as a separate router
to keep `routes/games_v2.py` from continuing to balloon."""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from auth import current_user, require_admin, current_user_optional
from services.games_v2 import _now
from services.games_v2_compliance import (
    SWEEPSTAKES_PRIZE_TYPES, CASH_EQUIVALENT_PRIZE_TYPES,
)
from services.games_v2_leads import (
    ensure_lead_indexes, upsert_lead_form, get_lead_form,
    lead_form_view, submit_lead, list_leads, leads_to_csv,
    find_valid_lead_for_user, MAX_LEAD_CSV_ROWS,
)
from services.games_v2_webhooks import (
    EVENT_TYPES, register_endpoint, list_endpoints,
    rotate_endpoint_secret, delete_endpoint, list_deliveries,
    queue_event, deliver_one,
)
from services.games_v2_leaderboard import (
    compute_leaderboard, VALID_METRICS, WINDOW_DELTAS,
)
from services.games_v2_inventory import (
    reconcile_campaign, force_correct, daily_scan_once, list_active_alerts,
)

logger = logging.getLogger("bigfm.games_v2c")

games_v2c_router = APIRouter(prefix="/api/games_v2", tags=["games_v2_phase8c"])


# ─── helpers ────────────────────────────────────────────────────────────
async def _campaign_or_owner_403(db, user: dict, campaign_id: str) -> dict:
    c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise HTTPException(404, "campaign_not_found")
    if user.get("role") == "admin":
        return c
    # advertiser ownership check
    from routes.games_v2 import _get_advertiser_id
    adv_id = await _get_advertiser_id(db, user)
    if c.get("advertiser_id") != adv_id:
        raise HTTPException(403, "not_owner")
    return c


def _csv_response(text: str, filename: str) -> Response:
    return Response(
        content=text, media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        })


async def _require_advertiser_id(db, user: dict) -> str:
    """Return the advertiser_id for this user; raise 403 if neither admin
    nor an active advertiser."""
    from routes.games_v2 import _get_advertiser_id
    adv_id = await _get_advertiser_id(db, user)
    if adv_id:
        return adv_id
    if user.get("role") == "admin":
        # admin without an advertiser row can still see/operate; we treat
        # their user_id as a synthetic scope (matches campaigns directly
        # owned by them, which currently none are — admin sees nothing
        # scoped, which is the safer default)
        return user.get("user_id")
    raise HTTPException(403, "advertiser_only")


# ────────────────────────────────────────────────────────────────────────
# § 1 — Lead capture forms
# ────────────────────────────────────────────────────────────────────────
_LEAD_FORM_ALLOWED_KEYS = {
    "fields_json", "required_before_play", "submit_button_label",
    "consent_text", "consent_required", "crm_sync_enabled",
    "webhook_url", "active",
}
_LEAD_FORM_ALIASES = {"fields": "fields_json"}


def _strict_validate_body(body: dict, allowed: set,
                                  aliases: dict, scope: str) -> dict:
    """Phase 8c.1 — reject unknown top-level fields; rewrite aliases.

    Raises HTTPException(400) listing the unknown keys.  Returns a
    normalized dict with aliased keys remapped to the canonical name.
    """
    if not isinstance(body, dict):
        raise HTTPException(400, "body_must_be_object")
    out: dict = {}
    unknown: list[str] = []
    aliased: list[str] = []
    for k, v in body.items():
        if k in aliases:
            out[aliases[k]] = v
            aliased.append(f"{k}→{aliases[k]}")
        elif k in allowed:
            out[k] = v
        else:
            unknown.append(k)
    if unknown:
        raise HTTPException(
            400,
            f"unknown_fields:{','.join(unknown)} "
            f"(allowed: {sorted(allowed)})")
    return out


@games_v2c_router.post("/advertiser/campaigns/{campaign_id}/lead_form")
async def adv_upsert_lead_form(campaign_id: str, request: Request,
                                        body: dict,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _campaign_or_owner_403(db, user, campaign_id)
    body = _strict_validate_body(body, _LEAD_FORM_ALLOWED_KEYS,
                                          _LEAD_FORM_ALIASES, "lead_form")
    try:
        form = await upsert_lead_form(
            db, campaign_id=campaign_id,
            fields_json=body.get("fields_json") or [],
            required_before_play=body.get("required_before_play", True),
            submit_button_label=body.get("submit_button_label", "Start playing"),
            consent_text=body.get("consent_text", ""),
            consent_required=body.get("consent_required", True),
            crm_sync_enabled=body.get("crm_sync_enabled", False),
            webhook_url=body.get("webhook_url"),
            active=body.get("active", True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "lead_form": await lead_form_view(form)}


@games_v2c_router.get("/advertiser/campaigns/{campaign_id}/lead_form")
async def adv_get_lead_form(campaign_id: str, request: Request,
                                     user: dict = Depends(current_user)):
    db = request.app.state.db
    await _campaign_or_owner_403(db, user, campaign_id)
    form = await get_lead_form(db, campaign_id)
    if not form:
        return {"lead_form": None}
    return {"lead_form": await lead_form_view(form)}


@games_v2c_router.delete("/advertiser/campaigns/{campaign_id}/lead_form")
async def adv_delete_lead_form(campaign_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _campaign_or_owner_403(db, user, campaign_id)
    await db.game_lead_forms.delete_one({"campaign_id": campaign_id})
    return {"ok": True}


@games_v2c_router.get("/advertiser/campaigns/{campaign_id}/leads")
async def adv_list_leads(campaign_id: str, request: Request,
                                  since: Optional[str] = None,
                                  outcome: Optional[str] = None,
                                  limit: int = Query(50, ge=1, le=200),
                                  cursor: Optional[str] = None,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _campaign_or_owner_403(db, user, campaign_id)
    since_dt = None
    cursor_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "invalid_since")
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "invalid_cursor")
    try:
        res = await list_leads(db, campaign_id, since=since_dt,
                                       outcome=outcome, limit=limit,
                                       cursor=cursor_dt)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"items": res["items"],
              "next_cursor": (res["next_cursor"]
                                if isinstance(res["next_cursor"], str)
                                else (res["next_cursor"].isoformat()
                                        if res["next_cursor"] else None))}


@games_v2c_router.get("/advertiser/campaigns/{campaign_id}/leads.csv")
async def adv_leads_csv(campaign_id: str, request: Request,
                                since: Optional[str] = None,
                                outcome: Optional[str] = None,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    await _campaign_or_owner_403(db, user, campaign_id)
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "invalid_since")
    try:
        res = await list_leads(db, campaign_id, since=since_dt,
                                       outcome=outcome,
                                       limit=MAX_LEAD_CSV_ROWS)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if len(res["items"]) >= MAX_LEAD_CSV_ROWS:
        raise HTTPException(
            413, "row_cap_exceeded:use_filtered_windows")
    text = leads_to_csv(res["items"])
    return _csv_response(text, f"{campaign_id}-leads.csv")


@games_v2c_router.get("/campaigns/{campaign_id}/lead_form")
async def listener_get_lead_form(campaign_id: str, request: Request,
                                            user_opt: Optional[dict] = Depends(current_user_optional)):
    """Listener-facing read-only view of the lead form schema (no
    submissions, no secrets).  Anonymous-allowed."""
    db = request.app.state.db
    form = await get_lead_form(db, campaign_id)
    if not form or not form.get("active"):
        return {"lead_form": None}
    public = await lead_form_view(form)
    # Drop the webhook URL & crm flag from the public view
    public.pop("webhook_url", None)
    public.pop("crm_sync_enabled", None)
    return {"lead_form": public}


@games_v2c_router.post("/campaigns/{campaign_id}/submit_lead")
async def listener_submit_lead(campaign_id: str, request: Request,
                                        body: dict,
                                        user_opt: Optional[dict] = Depends(current_user_optional)):
    """Anonymous-allowed.  If the listener is signed in we attach the
    user_id; otherwise we dedupe by IP."""
    db = request.app.state.db
    form = await get_lead_form(db, campaign_id)
    if not form or not form.get("active"):
        raise HTTPException(404, "lead_form_not_found")
    user_id: Optional[str] = (user_opt or {}).get("user_id") if user_opt else None
    from services.client_ip import get_real_client_ip
    ip = get_real_client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        sub = await submit_lead(
            db, campaign_id=campaign_id, form=form,
            user_id=user_id, ip=ip, user_agent=ua,
            form_data=body.get("form_data") or {},
            consent_accepted=bool(body.get("consent_accepted", False)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"lead_id": sub["submission_id"], "ready_to_play": True}


# ────────────────────────────────────────────────────────────────────────
# § 2 — Webhook endpoints
# ────────────────────────────────────────────────────────────────────────
@games_v2c_router.post("/advertiser/webhooks")
async def adv_register_webhook(request: Request, body: dict,
                                        user: dict = Depends(current_user)):
    advertiser_id = await _require_advertiser_id(request.app.state.db, user)
    db = request.app.state.db
    try:
        out = await register_endpoint(
            db, advertiser_id=advertiser_id,
            url=body.get("url") or "",
            events_subscribed=body.get("events_subscribed") or [])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


@games_v2c_router.get("/advertiser/webhooks")
async def adv_list_webhooks(request: Request,
                                     user: dict = Depends(current_user)):
    advertiser_id = await _require_advertiser_id(request.app.state.db, user)
    db = request.app.state.db
    return {"items": await list_endpoints(db, advertiser_id)}


@games_v2c_router.post("/advertiser/webhooks/{endpoint_id}/rotate_secret")
async def adv_rotate_webhook_secret(endpoint_id: str, request: Request,
                                                  user: dict = Depends(current_user)):
    advertiser_id = await _require_advertiser_id(request.app.state.db, user)
    db = request.app.state.db
    try:
        return await rotate_endpoint_secret(db, endpoint_id, advertiser_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@games_v2c_router.post("/advertiser/webhooks/{endpoint_id}/test")
async def adv_webhook_test_ping(endpoint_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    advertiser_id = await _require_advertiser_id(request.app.state.db, user)
    db = request.app.state.db
    ep = await db.advertiser_webhook_endpoints.find_one(
        {"endpoint_id": endpoint_id, "advertiser_id": advertiser_id})
    if not ep:
        raise HTTPException(404, "endpoint_not_found")
    # Manually enqueue the test_ping (campaign-less event)
    from services.games_v2_webhooks import _enqueue_for_endpoint
    payload = {"message": "test_ping", "sent_at": _now().isoformat(),
                  "endpoint_id": endpoint_id}
    ev = await _enqueue_for_endpoint(db, endpoint=ep,
                                                campaign_id="__test__",
                                                event_type="test_ping",
                                                payload=payload)
    # Deliver immediately (single attempt)
    result = await deliver_one(db, ev["webhook_event_id"])
    return {"webhook_event_id": ev["webhook_event_id"],
              "delivery_result": result}


@games_v2c_router.delete("/advertiser/webhooks/{endpoint_id}")
async def adv_delete_webhook(endpoint_id: str, request: Request,
                                       user: dict = Depends(current_user)):
    advertiser_id = await _require_advertiser_id(request.app.state.db, user)
    db = request.app.state.db
    await delete_endpoint(db, endpoint_id, advertiser_id)
    return {"ok": True}


@games_v2c_router.get("/advertiser/webhooks/{endpoint_id}/deliveries")
async def adv_webhook_deliveries(endpoint_id: str, request: Request,
                                              limit: int = Query(50, ge=1, le=200),
                                              user: dict = Depends(current_user)):
    advertiser_id = await _require_advertiser_id(request.app.state.db, user)
    db = request.app.state.db
    try:
        items = await list_deliveries(db, endpoint_id, advertiser_id, limit=limit)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"items": items}


# ────────────────────────────────────────────────────────────────────────
# § 4 — Leaderboard
# ────────────────────────────────────────────────────────────────────────
@games_v2c_router.get("/advertiser/leaderboard")
async def adv_leaderboard(request: Request,
                                  metric: str = Query("plays"),
                                  window: str = Query("7d"),
                                  limit: int = Query(20, ge=1, le=50),
                                  user: dict = Depends(current_user)):
    advertiser_id = await _require_advertiser_id(request.app.state.db, user)
    if metric not in VALID_METRICS:
        raise HTTPException(
            422,
            f"metric must be one of {sorted(VALID_METRICS)}")
    if window not in WINDOW_DELTAS:
        raise HTTPException(
            422,
            f"window must be one of {sorted(WINDOW_DELTAS.keys())}")
    db = request.app.state.db
    items = await compute_leaderboard(
        db, metric=metric, window=window,
        advertiser_scope_id=advertiser_id, limit=limit)
    return {"metric": metric, "window": window, "items": items}


@games_v2c_router.get("/admin/leaderboard")
async def admin_leaderboard(request: Request,
                                     metric: str = Query("plays"),
                                     window: str = Query("7d"),
                                     limit: int = Query(50, ge=1, le=100),
                                     _u: dict = Depends(require_admin)):
    if metric not in VALID_METRICS:
        raise HTTPException(
            422,
            f"metric must be one of {sorted(VALID_METRICS)}")
    if window not in WINDOW_DELTAS:
        raise HTTPException(
            422,
            f"window must be one of {sorted(WINDOW_DELTAS.keys())}")
    db = request.app.state.db
    items = await compute_leaderboard(
        db, metric=metric, window=window,
        advertiser_scope_id=None, limit=limit)
    return {"metric": metric, "window": window, "items": items}


# ────────────────────────────────────────────────────────────────────────
# § 6 — Inventory reconciliation
# ────────────────────────────────────────────────────────────────────────
@games_v2c_router.get("/admin/inventory_reconcile/{campaign_id}")
async def admin_inventory_reconcile(campaign_id: str, request: Request,
                                                   _u: dict = Depends(require_admin)):
    db = request.app.state.db
    return await reconcile_campaign(db, campaign_id)


@games_v2c_router.post("/admin/inventory_reconcile/{campaign_id}/force_correct")
async def admin_inventory_force_correct(campaign_id: str, request: Request,
                                                         u: dict = Depends(require_admin)):
    db = request.app.state.db
    return await force_correct(db, campaign_id, actor_user_id=u["user_id"])


@games_v2c_router.get("/admin/inventory_reconcile_alerts")
async def admin_inventory_alerts(request: Request,
                                              _u: dict = Depends(require_admin)):
    db = request.app.state.db
    return {"items": await list_active_alerts(db)}


@games_v2c_router.post("/admin/inventory_reconcile/run_daily_scan")
async def admin_inventory_run_scan(request: Request,
                                                  _u: dict = Depends(require_admin)):
    db = request.app.state.db
    return await daily_scan_once(db)


# ────────────────────────────────────────────────────────────────────────
# Webhook delivery sweep (admin time-travel)
# ────────────────────────────────────────────────────────────────────────
@games_v2c_router.post("/admin/webhooks/run_delivery_sweep")
async def admin_webhook_delivery_sweep(
        request: Request, body: Optional[dict] = None,
        _u: dict = Depends(require_admin)):
    """Phase 8c.1 — same as_of-parametrized sweep as dunning.

    Body: `{as_of?: ISO}`.  When present, treat that as 'now' for the
    `next_retry_at < as_of` comparison so testers can fast-forward
    through the backoff schedule without waiting 7 hours.
    Returns counts: `{attempted, sent, failed, max_retries_exceeded}`.
    """
    db = request.app.state.db
    body = body or {}
    as_of_str = body.get("as_of")
    if as_of_str:
        try:
            as_of = datetime.fromisoformat(
                str(as_of_str).replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "invalid_as_of")
    else:
        as_of = _now()
    counts = {"attempted": 0, "sent": 0, "failed": 0,
                 "max_retries_exceeded": 0}
    from services.games_v2_webhooks import deliver_one
    # Walk pending + due-for-retry rows under the as_of clock
    cur = db.game_webhook_events.find({
        "$or": [
            {"status": "pending"},
            {"status": "failed", "next_retry_at": {"$lte": as_of}},
        ],
    }).sort("next_retry_at", 1).limit(500)
    ids = [r["webhook_event_id"] async for r in cur]
    for eid in ids:
        res = await deliver_one(db, eid)
        counts["attempted"] += 1
        # Re-fetch to know final status
        ev = await db.game_webhook_events.find_one(
            {"webhook_event_id": eid},
            {"status": 1})
        st = (ev or {}).get("status")
        if st == "sent":
            counts["sent"] += 1
        elif st == "max_retries_exceeded":
            counts["max_retries_exceeded"] += 1
        else:
            counts["failed"] += 1
    return {**counts, "as_of": as_of.isoformat()}


# ────────────────────────────────────────────────────────────────────────
# § 7 — CSV exports (admin audit + advertiser analytics)
# ────────────────────────────────────────────────────────────────────────
_AUDIT_COLS = ["audit_id", "ts", "outcome", "reason", "campaign_id",
                  "wallet_item_id", "partner_token_id",
                  "qr_token_prefix", "ip", "user_agent"]


@games_v2c_router.get("/admin/redemption_audit_log.csv")
async def admin_audit_csv(request: Request,
                                  partner_token_id: Optional[str] = None,
                                  campaign_id: Optional[str] = None,
                                  outcome: Optional[str] = None,
                                  since: Optional[str] = None,
                                  until: Optional[str] = None,
                                  _u: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {}
    if partner_token_id:
        q["partner_token_id"] = partner_token_id
    if campaign_id:
        q["campaign_id"] = campaign_id
    if outcome:
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
    if ts_q:
        q["ts"] = ts_q
    rows = []
    async for r in db.redemption_audit_log.find(q).sort("ts", -1).limit(100_000):
        if len(rows) >= 100_000:
            raise HTTPException(413, "row_cap_exceeded:use_filtered_windows")
        rows.append({
            "audit_id": r.get("audit_id") or r.get("_id"),
            "ts": r["ts"].isoformat() if r.get("ts") else "",
            "outcome": r.get("outcome", ""),
            "reason": r.get("reason", "") or "",
            "campaign_id": r.get("campaign_id", "") or "",
            "wallet_item_id": r.get("wallet_item_id", "") or "",
            "partner_token_id": r.get("partner_token_id", "") or "",
            "qr_token_prefix": r.get("qr_token_prefix", "") or "",
            "ip": r.get("ip", "") or "",
            "user_agent": (r.get("user_agent", "") or "")[:200],
        })
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_AUDIT_COLS)
    w.writeheader()
    for row in rows:
        w.writerow(row)
    return _csv_response(buf.getvalue(), "redemption_audit_log.csv")


_ANALYTICS_COLS = ["event_id", "ts", "event_type", "campaign_id",
                       "user_id", "session_id", "source"]


@games_v2c_router.get("/advertiser/campaigns/{campaign_id}/analytics.csv")
async def adv_analytics_csv(campaign_id: str, request: Request,
                                      since: Optional[str] = None,
                                      until: Optional[str] = None,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await _campaign_or_owner_403(db, user, campaign_id)
    q: dict = {"campaign_id": campaign_id}
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
    if ts_q:
        q["ts"] = ts_q
    rows = []
    async for r in db.game_analytics_events.find(q).sort("ts", -1).limit(100_000):
        if len(rows) >= 100_000:
            raise HTTPException(413, "row_cap_exceeded:use_filtered_windows")
        rows.append({
            "event_id": r.get("_id"),
            "ts": r["ts"].isoformat() if r.get("ts") else "",
            "event_type": r.get("event_type", ""),
            "campaign_id": r.get("campaign_id", ""),
            "user_id": r.get("user_id", "") or "",
            "session_id": ((r.get("metadata_json") or {}).get("session_id")
                              or ""),
            "source": ((r.get("source_context_json") or {}).get("source")
                          or ""),
        })
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_ANALYTICS_COLS)
    w.writeheader()
    for row in rows:
        w.writerow(row)
    return _csv_response(buf.getvalue(), f"{campaign_id}-analytics.csv")


__all__ = ["games_v2c_router"]
