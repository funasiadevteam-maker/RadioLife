"""Sub-Phase E4 — Predict & Win lifecycle sweeper.

Runs three idempotent sweeps every `PREDICT_WIN_SWEEP_INTERVAL_SEC`
(default 60) inside an asyncio background task started from
`server.py` (matches the existing `badge_cron_task` / `dunning_cron_task`
pattern — no external scheduler library).

Sweeps:
    sweep_scheduled_to_live()   approved + scheduled + start_time<=now → live
    sweep_live_to_locked()         live + lock_time<=now → locked
    sweep_locked_to_resolved() locked + resolve_by<=now → either kick the
                                                      auto-resolution provider (E5) or
                                                      surface a `needs_manual_resolution`
                                                      admin alert (after >24h locked).

E4 deliberately does NOT auto-resolve any campaign — that's E5 once a
real data provider (Predexon) is wired.  E4 only logs which campaigns
WANT resolution and fires an alert when a locked campaign sits > 24h.

Cycle metrics are persisted to `predict_win_sweep_logs` (TTL 7 days).
Pause/resume toggle lives in `predict_win_settings.sweeper.enabled`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.predict_win.sweeper")
log = logger  # alias for E5 predexon block compatibility

DEFAULT_INTERVAL_SEC = int(os.environ.get(
    "PREDICT_WIN_SWEEP_INTERVAL_SEC", "60"))
NEEDS_MANUAL_ALERT_AFTER_HOURS = int(os.environ.get(
    "PREDICT_WIN_NEEDS_MANUAL_ALERT_AFTER_HOURS", "24"))


# ─── Helpers ───────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _aware(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


async def _emit_analytics(db, event_type: str, campaign_id: str,
                                                payload: Optional[dict] = None) -> None:
    """Append a row to `predict_win_analytics_events` so admins can audit
    every auto-transition.  Fire-and-forget — never raise."""
    try:
        await db.predict_win_analytics_events.insert_one({
            "_id": _new_id("pwa_evt"),
            "event_id": _new_id("pwa_evt"),
            "campaign_id": campaign_id,
            "event_type": event_type,
            "user_id": None,
            "created_at": _now(),
            "payload": payload or {},
        })
    except Exception as e:
        logger.warning("[sweeper] analytics emit failed: %s", e)


async def _emit_admin_alert(db, campaign_id: str, reason: str,
                                                  payload: Optional[dict] = None) -> None:
    """Drop a row in `predict_win_admin_alerts` so the admin queue can
    surface manual-resolution backlogs.  Idempotent on
    (campaign_id, reason)."""
    try:
        await db.predict_win_admin_alerts.update_one(
            {"campaign_id": campaign_id, "reason": reason},
            {"$setOnInsert": {
                "alert_id": _new_id("pwa_alrt"),
                "campaign_id": campaign_id,
                "reason": reason,
                "created_at": _now(),
                "payload": payload or {},
                "acked_at": None,
            }}, upsert=True)
    except Exception as e:
        logger.warning("[sweeper] admin alert emit failed: %s", e)


# ─── Sweep functions ──────────────────────────────────────────────────
async def sweep_scheduled_to_live(db) -> Dict[str, Any]:
    """Find approved+scheduled campaigns whose start_time has arrived
    and flip them to status='live'.  Atomic per row — uses Mongo's
    matched conditional update so a concurrent manual action wins if
    it landed first."""
    now = _now()
    affected_ids: List[str] = []
    # Use find_one_and_update in a loop so each transition is atomic.
    while True:
        c = await db.predict_win_campaigns.find_one_and_update(
            {
                "approval_status": "approved",
                "status": "scheduled",
                "start_time": {"$lte": now},
                "deleted_at": None,
            },
            {"$set": {"status": "live", "updated_at": now}},
            return_document=True,   # i.e. the doc AFTER update
        )
        if not c:
            break
        affected_ids.append(c["campaign_id"])
        await _emit_analytics(db, "auto_transition_to_live",
                                              c["campaign_id"],
                                              {"start_time": c.get("start_time").isoformat()
                                                if isinstance(c.get("start_time"), datetime) else None})
    return {"count": len(affected_ids), "campaign_ids": affected_ids}


async def sweep_live_to_locked(db) -> Dict[str, Any]:
    """Find live campaigns whose lock_time has passed and flip them to
    status='locked'.  Entry-level state machine stays at `submitted` —
    the campaign-level `status='locked'` is the lock signal (consumer
    `/enter` already rejects via the `lock_expired` eligibility guard
    so no entry-row rewrite is needed)."""
    now = _now()
    affected_ids: List[str] = []
    while True:
        c = await db.predict_win_campaigns.find_one_and_update(
            {
                "approval_status": "approved",
                "status": "live",
                "lock_time": {"$lte": now},
                "deleted_at": None,
            },
            {"$set": {"status": "locked", "updated_at": now}},
            return_document=True,
        )
        if not c:
            break
        affected_ids.append(c["campaign_id"])
        # Notify entrants — fire-and-forget (skip on any error).
        entry_user_ids = set()
        try:
            async for e in db.predict_win_entries.find(
                {"campaign_id": c["campaign_id"],
                  "status": {"$nin": ["void"]}},
                projection={"user_id": 1},
            ):
                entry_user_ids.add(e["user_id"])
        except Exception as _le:
            logger.warning("[sweeper] entrant lookup failed: %s", _le)

        if entry_user_ids:
            await _drop_entrant_notifications(
                db, list(entry_user_ids), c["campaign_id"], c.get("title", ""))

        await _emit_analytics(db, "auto_locked", c["campaign_id"], {
            "lock_time": c["lock_time"].isoformat()
                if isinstance(c.get("lock_time"), datetime) else None,
            "entrant_count": len(entry_user_ids),
        })
    return {"count": len(affected_ids), "campaign_ids": affected_ids}


async def _drop_entrant_notifications(db, user_ids: List[str],
                                                                          campaign_id: str,
                                                                          campaign_title: str) -> None:
    """Insert an in-app notification per entrant when the campaign locks.
    Idempotent via a composite dedupe key per (campaign, user)."""
    now = _now()
    docs = []
    for uid in user_ids:
        dedupe = f"predict_win_locked:{campaign_id}:{uid}"
        docs.append({
            "_id": dedupe,
            "notification_id": _new_id("ntf"),
            "user_id": uid,
            "kind": "predict_win_locked",
            "title": "Your prediction is locked in",
            "body": f"Results coming soon for \"{campaign_title}\".",
            "data": {"campaign_id": campaign_id, "campaign_title": campaign_title},
            "created_at": now,
            "read_at": None,
            "dedupe_key": dedupe,
        })
    if docs:
        try:
            # insertMany with ordered=False so duplicate _id collisions
            # (re-locked twice) silently skip rather than failing the lot.
            await db.notifications.insert_many(docs, ordered=False)
        except Exception as e:
            # Most expected errors are dup _id collisions; log and move on.
            logger.debug("[sweeper] notifications insert returned: %s", e)


async def _increment_predexon_failure(db, campaign_id: str,
                                                                                      err_msg: Optional[str]) -> None:
    """Track consecutive Predexon failures per campaign; fire an admin
    alert at 3 strikes.  Idempotent on (campaign_id, reason)."""
    now = _now()
    try:
        doc = await db.predict_win_admin_alerts.find_one(
            {"campaign_id": campaign_id,
              "reason": "predexon_consecutive_failures",
              "status": "pending"})
        if doc:
            new_count = ((doc.get("metadata") or {}).get("count", 0)) + 1
            await db.predict_win_admin_alerts.update_one(
                {"_id": doc["_id"]},
                {"$set": {"metadata.count": new_count,
                                  "metadata.last_error": (err_msg or "")[:200],
                                  "updated_at": now}})
        else:
            aid = _new_id("pwal")
            await db.predict_win_admin_alerts.insert_one({
                "_id": aid, "alert_id": aid,
                "campaign_id": campaign_id,
                "reason": "predexon_consecutive_failures",
                "status": "pending",
                "metadata": {"count": 1,
                                          "last_error": (err_msg or "")[:200]},
                "created_at": now, "updated_at": now,
            })
    except Exception as _e:
        logger.debug("[predexon] failure-streak tracker skipped: %s", _e)


async def sweep_locked_to_resolved(db) -> Dict[str, Any]:
    """Inspect locked campaigns whose `resolve_by` has arrived.

    E4 does NOT auto-resolve any campaign — Predexon (E5) and a future
    trivia-engine path will plug in here.  For now we only:
      • check which campaigns are candidates for auto-resolution (today
          this is always 0 — no auto-provider wired).
      • check which locked campaigns have sat >24h without resolution
          and fire a `needs_manual_resolution` admin alert.
    """
    now = _now()
    needs_resolution: List[dict] = []
    auto_resolved: List[str] = []
    skipped_no_provider: List[str] = []
    alerts_fired: List[str] = []

    cur = db.predict_win_campaigns.find({
        "approval_status": "approved",
        "status": "locked",
        "deleted_at": None,
    })
    async for c in cur:
        resolve_by = _aware(c.get("resolve_by"))
        if resolve_by is None or resolve_by > now:
            continue
        existing = await db.predict_win_resolutions.find_one(
            {"campaign_id": c["campaign_id"]})
        if existing:
            continue
        # Lookup the data provider attached to this campaign to decide.
        provider_name = "manual"
        if c.get("data_provider_id"):
            prov = await db.prediction_data_providers.find_one(
                {"provider_id": c["data_provider_id"]})
            if prov:
                provider_name = prov.get("provider_name") or "manual"
        if provider_name == "predexon":
            # Sub-Phase E5 — fully wired Predexon auto-resolve.  Calls
            # the read-only resolution endpoint; if the upstream market
            # is resolved + we can map its outcome to a campaign option,
            # we mint a `predict_win_resolutions` row (`result_source=
            # "predexon"`) and fan out the award pipeline.  Any failure
            # leaves the campaign in `locked` for the next sweep.
            try:
                from services import predexon_client
                ext_id = c.get("external_market_id")
                if not ext_id:
                    skipped_no_provider.append(c["campaign_id"])
                    await _emit_analytics(
                        db, "auto_resolve_skipped_no_external_market_id",
                        c["campaign_id"], {"provider": "predexon"})
                    continue
                res = await predexon_client.get_market_resolution(db, ext_id)
                if not res.get("ok"):
                    # Upstream error — leave locked, track consecutive
                    # failures, alert at 3.
                    await _increment_predexon_failure(
                        db, c["campaign_id"], res.get("error_message"))
                    continue
                body = res.get("body")
                if not body:
                    # 404 → market not yet resolved.  Quietly retry later.
                    skipped_no_provider.append(c["campaign_id"])
                    continue
                options = (c.get("question") or {}).get("answer_options") or []
                winning_option_id = predexon_client.map_resolution_to_option_id(
                    resolution_body=body, answer_options=options)
                if not winning_option_id:
                    log.warning(
                        "[predexon] no option match for campaign=%s "
                        "external_market_id=%s payload_keys=%s — "
                        "leaving locked for manual resolve",
                        c["campaign_id"], ext_id, list(body.keys())[:8])
                    needs_resolution.append({
                        "campaign_id": c["campaign_id"],
                        "title": c.get("title"),
                        "locked_since": _iso_or_none(c.get("updated_at")),
                        "resolve_by": _iso_or_none(c.get("resolve_by")),
                        "data_provider": "predexon",
                        "predexon_unmappable": True,
                    })
                    continue
                # Mint resolution + fan out awards (mirrors the manual
                # admin path so the rest of E2 is unchanged).
                rid = f"pwr_{uuid.uuid4().hex[:14]}"
                external_resolution_id = (
                    body.get("resolution_id") or body.get("id")
                    or body.get("market_id") or ext_id)
                try:
                    await db.predict_win_resolutions.insert_one({
                        "_id": rid, "resolution_id": rid,
                        "campaign_id": c["campaign_id"],
                        "winning_option_id": winning_option_id,
                        "resolved_by": None,
                        "resolved_at": now,
                        "result_source": "predexon",
                        "external_resolution_id": str(external_resolution_id),
                        "data_source_url": (
                            f"https://api.predexon.com/v2/polymarket/"
                            f"markets/{ext_id}/resolution"),
                        "audit_notes": "Auto-resolved by E5 sweeper.",
                        "audit_json": {
                            "predexon_payload_keys": list(body.keys())[:20],
                            "options_at_resolve_time": options,
                            "external_market_id": ext_id,
                        },
                    })
                except Exception as _ie:
                    # Unique index on (campaign_id) — already resolved
                    # by a concurrent sweep / manual admin.  Move on.
                    log.info("[predexon] resolution insert race for %s: %s",
                                      c["campaign_id"], _ie)
                    continue
                await db.predict_win_entries.update_many(
                    {"campaign_id": c["campaign_id"],
                      "picked_option_id": winning_option_id},
                    {"$set": {"status": "winner", "evaluated_at": now}})
                await db.predict_win_entries.update_many(
                    {"campaign_id": c["campaign_id"],
                      "picked_option_id": {"$ne": winning_option_id}},
                    {"$set": {"status": "loser", "evaluated_at": now}})
                await db.predict_win_campaigns.update_one(
                    {"campaign_id": c["campaign_id"]},
                    {"$set": {"status": "resolved", "updated_at": now}})
                try:
                    from services.predict_win_award_pipeline import (
                        run_award_pipeline)
                    await run_award_pipeline(
                        db,
                        campaign_id=c["campaign_id"],
                        winning_option_id=winning_option_id,
                        resolution_id=rid)
                except Exception as _ae:
                    log.warning("[predexon] award pipeline error for %s: %s",
                                          c["campaign_id"], _ae)
                # Phase PW-M.1 — cascade to any merchant child campaigns.
                try:
                    from services.predict_win_merchant_service import (
                        resolve_and_award_children)
                    _child_rep = await resolve_and_award_children(
                        db, parent_campaign_id=c["campaign_id"],
                        winning_option_id=winning_option_id)
                    if _child_rep.get("children_awarded"):
                        log.info("[pw-m] cascade parent=%s report=%s",
                                            c["campaign_id"], _child_rep)
                except Exception as _me:
                    log.warning("[pw-m] merchant cascade error for %s: %s",
                                              c["campaign_id"], _me)
                # Clear any prior failure-streak counters.
                await db.predict_win_admin_alerts.delete_many({
                    "campaign_id": c["campaign_id"],
                    "reason": "predexon_consecutive_failures",
                    "status": "pending",
                })
                auto_resolved.append(c["campaign_id"])
                await _emit_analytics(
                    db, "auto_resolve_succeeded",
                    c["campaign_id"],
                    {"provider": "predexon",
                      "external_market_id": ext_id,
                      "winning_option_id": winning_option_id})
            except Exception as _e:
                log.exception("[predexon] sweep error for %s: %s",
                                          c["campaign_id"], _e)
                await _increment_predexon_failure(
                    db, c["campaign_id"], str(_e)[:200])
        else:
            # Manual or unknown — needs human resolve.
            needs_resolution.append({
                "campaign_id": c["campaign_id"],
                "title": c.get("title"),
                "locked_since": _iso_or_none(c.get("updated_at")),
                "resolve_by": _iso_or_none(c.get("resolve_by")),
                "data_provider": provider_name,
            })
            # If the campaign has been locked > NEEDS_MANUAL_ALERT_AFTER_HOURS
            # hours, raise an alert (idempotent on campaign_id+reason).
            locked_since = _aware(c.get("updated_at"))
            if locked_since:
                age_h = (now - locked_since).total_seconds() / 3600.0
                if age_h >= NEEDS_MANUAL_ALERT_AFTER_HOURS:
                    await _emit_admin_alert(
                        db, c["campaign_id"],
                        "needs_manual_resolution",
                        {"locked_hours": round(age_h, 2),
                          "campaign_title": c.get("title"),
                          "creator_type": c.get("creator_type"),
                          "business_station_slug": c.get("business_station_slug")})
                    alerts_fired.append(c["campaign_id"])

    return {
        "needs_resolution_count": len(needs_resolution),
        "needs_resolution": needs_resolution,
        "auto_resolved_count": len(auto_resolved),
        "skipped_provider_not_configured_count": len(skipped_no_provider),
        "skipped_provider_campaign_ids": skipped_no_provider,
        "admin_alerts_fired_count": len(alerts_fired),
        "admin_alerts_fired_campaign_ids": alerts_fired,
    }


def _iso_or_none(v: Any) -> Optional[str]:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return None


# ─── Orchestration ────────────────────────────────────────────────────
async def is_paused(db) -> bool:
    s = await db.predict_win_settings.find_one({"_id": "sweeper"})
    if not s:
        return False
    return not bool(s.get("enabled", True))


async def set_paused(db, paused: bool, by_user_id: str) -> dict:
    now = _now()
    await db.predict_win_settings.update_one(
        {"_id": "sweeper"},
        {"$set": {
            "enabled": (not paused),
            "updated_at": now,
            "updated_by": by_user_id,
        }, "$setOnInsert": {"_id": "sweeper", "created_at": now}},
        upsert=True)
    return {"enabled": (not paused), "paused": paused, "updated_at": now}


async def run_one_cycle(db, *,
                                        trigger: str = "scheduled") -> Dict[str, Any]:
    """Run all three sweeps once and persist a cycle log.

    `trigger` distinguishes 'scheduled' (the asyncio loop) from
    'manual' (admin run-once)."""
    cycle_id = _new_id("pwsc")
    started_at = _now()
    paused = await is_paused(db)
    if paused and trigger == "scheduled":
        return {"cycle_id": cycle_id, "skipped_paused": True,
                      "trigger": trigger,
                      "started_at": started_at.isoformat()}
    errors: List[str] = []
    s2l: Dict[str, Any] = {"count": 0, "campaign_ids": []}
    l2k: Dict[str, Any] = {"count": 0, "campaign_ids": []}
    res: Dict[str, Any] = {"needs_resolution_count": 0,
                                          "needs_resolution": [],
                                          "auto_resolved_count": 0,
                                          "skipped_provider_not_configured_count": 0,
                                          "skipped_provider_campaign_ids": [],
                                          "admin_alerts_fired_count": 0,
                                          "admin_alerts_fired_campaign_ids": []}
    try:
        s2l = await sweep_scheduled_to_live(db)
    except Exception as e:
        errors.append(f"scheduled_to_live: {e}")
        logger.exception("[sweeper] scheduled_to_live error")
    try:
        l2k = await sweep_live_to_locked(db)
    except Exception as e:
        errors.append(f"live_to_locked: {e}")
        logger.exception("[sweeper] live_to_locked error")
    try:
        res = await sweep_locked_to_resolved(db)
    except Exception as e:
        errors.append(f"locked_to_resolved: {e}")
        logger.exception("[sweeper] locked_to_resolved error")
    completed_at = _now()

    log_doc = {
        "_id": cycle_id,
        "cycle_id": cycle_id,
        "trigger": trigger,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": int((completed_at - started_at).total_seconds() * 1000),
        "scheduled_to_live_count": s2l["count"],
        "scheduled_to_live_ids": s2l["campaign_ids"],
        "live_to_locked_count": l2k["count"],
        "live_to_locked_ids": l2k["campaign_ids"],
        "locked_pending_resolution_count": res["needs_resolution_count"],
        "auto_resolved_count": res["auto_resolved_count"],
        "skipped_provider_count": res["skipped_provider_not_configured_count"],
        "admin_alerts_fired_count": res["admin_alerts_fired_count"],
        "errors": errors,
        "ok": (len(errors) == 0),
    }
    try:
        await db.predict_win_sweep_logs.insert_one(log_doc)
    except Exception as e:
        logger.warning("[sweeper] cycle log insert failed: %s", e)
    if not errors:
        log_msg = (f"[sweeper] cycle={cycle_id[:18]} trigger={trigger} "
                            f"s2l={s2l['count']} l2k={l2k['count']} "
                            f"needs_res={res['needs_resolution_count']} "
                            f"alerts={res['admin_alerts_fired_count']}")
        if (s2l["count"] or l2k["count"] or
                res["needs_resolution_count"] or
                res["admin_alerts_fired_count"]):
            logger.info(log_msg)
        else:
            logger.debug(log_msg)
    # Detailed listings are useful for the manual run-once response.
    out = {
        **log_doc,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "needs_resolution": res["needs_resolution"],
        "skipped_provider_campaign_ids": res["skipped_provider_campaign_ids"],
        "admin_alerts_fired_campaign_ids": res["admin_alerts_fired_campaign_ids"],
    }
    return out


async def ensure_e4_indexes(db) -> dict:
    """Create the collections + indexes the sweeper relies on.  TTL on
    sweep logs is 7 days (set via expireAfterSeconds)."""
    # Drop any pre-existing non-TTL index on started_at so the TTL one
    # can be created without conflicting (Mongo refuses to redefine the
    # same key with different options).
    try:
        existing = await db.predict_win_sweep_logs.index_information()
        if "started_at_1" in existing and "ttl_started_at_7d" not in existing:
            await db.predict_win_sweep_logs.drop_index("started_at_1")
    except Exception:
        pass
    await db.predict_win_sweep_logs.create_index(
        "started_at", expireAfterSeconds=7 * 24 * 3600,
        name="ttl_started_at_7d")
    await db.predict_win_admin_alerts.create_index(
        [("campaign_id", 1), ("reason", 1)], unique=True)
    await db.predict_win_admin_alerts.create_index("acked_at")
    return {"predict_win_sweep_logs": True,
                  "predict_win_admin_alerts": True,
                  "predict_win_settings": True}


# ─── Background task entry point ──────────────────────────────────────
async def sweeper_loop(app) -> None:
    """Long-running asyncio coroutine started from server.py startup.

    Matches the codebase pattern (badge_cron, dunning_cron, etc.):
    infinite `while True`, sleep + try/except so a single bad cycle
    doesn't kill the loop.
    """
    interval = DEFAULT_INTERVAL_SEC
    logger.info(f"[predict_win_sweeper] loop starting (interval={interval}s, "
                          f"alert_after_hours={NEEDS_MANUAL_ALERT_AFTER_HOURS}h)")
    # 5-second initial delay so we don't fire mid-bootstrap.
    await asyncio.sleep(5)
    while True:
        try:
            db = app.state.db
            await run_one_cycle(db, trigger="scheduled")
        except Exception as e:
            logger.warning("[predict_win_sweeper] cycle error: %s", e)
        await asyncio.sleep(interval)
