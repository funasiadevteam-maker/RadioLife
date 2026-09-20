"""Phase 12b — Admin Retention + reactivation prompts + tracking router.

Three routers in one module:
    • admin_retention_router  → /api/admin/retention/*
    • me_retention_router       → /api/me/reactivation_prompt
    • tracking_router            → /api/r/{tracking_id}/* (pixel + click)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response

from auth import current_user, require_admin
from services.churn_score import (
    band_for_score, churn_distribution, compute_score,
    ensure_churn_indexes, get_or_recompute,
)
from services.delivery import (
    ensure_delivery_indexes, send_email, send_push,
)
from services.ab import (
    apply_overrides, ensure_ab_indexes, normalize_variants,
    pick_variant, two_proportion_z,
    MIN_SEND_PER_VARIANT, P_VALUE_SIGNIFICANT,
)

logger = logging.getLogger("bigfm.retention")

admin_retention_router = APIRouter(
    prefix="/api/admin/retention", tags=["admin-retention"])
me_retention_router = APIRouter(
    prefix="/api/me", tags=["me-retention"])
tracking_router = APIRouter(prefix="/api/r", tags=["tracking"])


# 1×1 transparent GIF
_PIXEL_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ════════════════════════════════════════════════════════════════════════
# Campaign helpers
# ════════════════════════════════════════════════════════════════════════
# Built-in triggers. Each maps to an audience query.
TRIGGER_DEFS: dict[str, dict] = {
    "inactive_3d":
        {"label": "Inactive 3 days (cooling+)",
          "band_in": ["cooling", "at_risk", "dormant"],
          "min_days_since_play": 3},
    "inactive_7d":
        {"label": "Inactive 7 days",
          "band_in": ["at_risk", "dormant"],
          "min_days_since_play": 7},
    "inactive_14d_winback":
        {"label": "Inactive 14 days (winback with coupon)",
          "band_in": ["at_risk", "dormant"],
          "min_days_since_play": 14},
    "subscription_past_due":
        {"label": "Past-due subscription",
          "subscription_status": "past_due",
          "max_sends_per_user_per_period": 3,
          "throttle_days": 7},
    "subscription_canceled_24h_winback":
        {"label": "Canceled <24h, win back",
          "subscription_status": "canceled",
          "min_days_since_play": 0},
    "coupon_expiring_24h":
        {"label": "Coupon expiring in 24h",
          "coupon_expiring_within_hours": 24},
    "new_badge_eligible":
        {"label": "One play from a badge",
          "near_badge_threshold_min": 60},
    "friend_joined_lobby":
        {"label": "Friend joined a lobby (real-time)"},
    "commute_window_today_offers":
        {"label": "Today's commute window (push only)"},
    "weekly_recap":
        {"label": "Weekly recap (Sundays)"},
}


async def ensure_retention_indexes(db) -> None:
    await ensure_churn_indexes(db)
    await ensure_delivery_indexes(db)
    await db.lifecycle_campaigns.create_index("id", unique=True)
    await db.lifecycle_campaigns.create_index([("trigger", 1), ("active", 1)])
    await db.reactivation_dismiss.create_index(
        [("user_id", 1), ("until", 1)])


def _ser_campaign(d: dict) -> dict:
    out = dict(d)
    out.pop("_id", None)
    for f in ("created_at", "updated_at"):
        v = out.get(f)
        if isinstance(v, datetime):
            out[f] = v.isoformat()
    return out


async def _campaign_audience_query(db, campaign: dict) -> dict:
    """Builds a mongo `users` query from the campaign trigger + filters.
    Caller can `.count_documents()` or `.find()` against `users`."""
    trigger = campaign.get("trigger") or ""
    audience_filter = campaign.get("audience_filter") or {}
    user_q: dict = {}

    if trigger == "subscription_past_due":
        user_q["subscription.status"] = "past_due"
    elif trigger == "subscription_canceled_24h_winback":
        user_q["subscription.status"] = {"$in": [
            "canceled", "incomplete_expired", "unpaid"]}

    # audience_filter overrides
    if audience_filter.get("city"):
        user_q["preference_vector.city"] = audience_filter["city"]
    if audience_filter.get("market"):
        user_q["market"] = audience_filter["market"]
    if audience_filter.get("plan"):
        user_q["premium_tier"] = audience_filter["plan"]
    if audience_filter.get("is_premium") is not None:
        user_q["is_premium"] = bool(audience_filter["is_premium"])
    return user_q


async def _filter_by_churn_band(db, user_ids: list[str],
                                              bands: list[str]) -> list[str]:
    """Keep only users whose cached band matches."""
    if not user_ids or not bands:
        return user_ids
    out = []
    cur = db.churn_scores.find(
        {"user_id": {"$in": user_ids}, "band": {"$in": bands}},
        {"user_id": 1, "_id": 0})
    async for d in cur:
        out.append(d["user_id"])
    return out


async def _audience_user_ids(db, campaign: dict, *,
                                          limit: int = 5000) -> list[str]:
    """Returns the user_ids targeted by a campaign.

    Phase 13c: when `campaign.cohort_id` is set, intersect the trigger
    audience with the cohort audience (AND). When only `cohort_id` is
    set (no trigger), the cohort drives selection.
    """
    trigger = campaign.get("trigger") or ""
    tdef = TRIGGER_DEFS.get(trigger) or {}
    user_q = await _campaign_audience_query(db, campaign)
    candidates: list[str] = []
    cur = db.users.find(user_q, {"user_id": 1, "_id": 0}).limit(limit)
    async for u in cur:
        uid = u.get("user_id")
        if uid:
            candidates.append(uid)

    # Filter by churn band when defined
    bands = tdef.get("band_in") or campaign.get("audience_filter", {}).get(
        "band_in")
    if bands:
        candidates = await _filter_by_churn_band(db, candidates, bands)

    # Filter by min_days_since_play
    min_days = tdef.get("min_days_since_play")
    if min_days and candidates:
        cutoff = _now() - timedelta(days=int(min_days))
        kept = []
        # Users with NO play_start or last < cutoff
        active_set = set()
        cur = db.playback_logs.aggregate([
            {"$match": {"user_id": {"$in": candidates},
                          "event": "play_start",
                          "timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id"}},
        ])
        async for d in cur:
            active_set.add(d["_id"])
        kept = [u for u in candidates if u not in active_set]
        candidates = kept

    # Phase 13c — intersect with cohort audience if cohort_id set.
    cohort_id = campaign.get("cohort_id")
    if cohort_id:
        try:
            from services.cohorts import resolve_cohort
            cohort_doc = await db.audience_cohorts.find_one(
                {"id": cohort_id})
            if cohort_doc and cohort_doc.get("filter_dsl"):
                cohort_uids = set(await resolve_cohort(
                    db, cohort_doc["filter_dsl"], limit=100_000))
                if not candidates:
                    candidates = sorted(cohort_uids)
                else:
                    candidates = [u for u in candidates
                                          if u in cohort_uids]
        except Exception as _e:
            pass
    return candidates


async def _throttle_ok(db, *, campaign: dict, user_id: str) -> bool:
    """Returns True if user can receive another send within the
    campaign's throttle window. Default: 1 send per 72h.

    Accepts BOTH the canonical dict shape
        {"max_sends": int, "period_hours": int}
    AND legacy string shorthand like "7d" / "24h" / "30m" (which older
    campaigns from earlier 12b iterations may still carry).
    """
    raw = campaign.get("throttle_per_user_per_period")
    sends = 1
    period_hours = 72
    if isinstance(raw, dict):
        sends = int(raw.get("max_sends") or 1)
        period_hours = int(raw.get("period_hours") or 72)
    elif isinstance(raw, str) and raw.strip():
        # Legacy string: "7d" / "24h" / "30m"
        s = raw.strip().lower()
        try:
            n = int("".join(c for c in s if c.isdigit()) or 0)
            unit = s[-1]
            if unit == "d": period_hours = n * 24
            elif unit == "h": period_hours = n
            elif unit == "m": period_hours = max(1, n // 60)
        except Exception:
            period_hours = 72
    cutoff = _now() - timedelta(hours=period_hours)
    n = await db.lifecycle_send_log.count_documents(
        {"user_id": user_id, "campaign_id": campaign["id"],
          "sent_at": {"$gte": cutoff}})
    return n < sends


# ════════════════════════════════════════════════════════════════════════
# Admin churn distribution
# ════════════════════════════════════════════════════════════════════════
@admin_retention_router.get("/churn_distribution")
async def get_churn_distribution(request: Request,
                                                  range: str = Query("30d"),
                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    dist = await churn_distribution(db)
    # Enrich top users with name/email/last_play for quick admin context
    uids = [u["user_id"] for u in dist["top_at_risk"]]
    metas: dict[str, dict] = {}
    if uids:
        cur = db.users.find({"user_id": {"$in": uids}},
                                  {"user_id": 1, "email": 1, "name": 1,
                                    "is_premium": 1, "premium_tier": 1,
                                    "_id": 0})
        async for u in cur:
            metas[u["user_id"]] = u
    enriched = []
    for entry in dist["top_at_risk"]:
        m = metas.get(entry["user_id"], {})
        ts = entry.get("computed_at")
        if isinstance(ts, datetime):
            entry["computed_at"] = ts.isoformat()
        if isinstance(entry.get("expires_at"), datetime):
            entry["expires_at"] = entry["expires_at"].isoformat()
        entry["email"] = m.get("email")
        entry["name"] = m.get("name")
        entry["is_premium"] = bool(m.get("is_premium"))
        entry["premium_tier"] = m.get("premium_tier")
        enriched.append(entry)
    return {"range": range,
              "generated_at": _now().isoformat(),
              "data": {"bands": dist["bands"],
                          "total_scored": dist["total_scored"],
                          "top_at_risk": enriched}}


@admin_retention_router.post("/recompute_user/{user_id}")
async def admin_recompute_user(user_id: str, request: Request,
                                              force_band: Optional[str] = Query(
                                                  None,
                                                  description="QA-only override: "
                                                  "'healthy'|'cooling'|'at_risk'|'dormant'"),
                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    # Validate user exists
    if not await db.users.find_one({"user_id": user_id}, {"_id": 1}):
        raise HTTPException(404, f"user not found: {user_id}")
    if force_band:
        # QA helper — bypass real signal calculation
        BAND_MIDPOINTS = {"healthy": 12, "cooling": 38,
                                  "at_risk": 63, "dormant": 90}
        # Days-since-last-play synthetic offset, matched to band so the
        # trigger engine (`inactive_7d`, `inactive_14d_winback`) actually
        # picks the forced user up.
        BAND_DAYS_OFFSET = {"healthy": 0, "cooling": 4,
                                    "at_risk": 10, "dormant": 30}
        if force_band not in BAND_MIDPOINTS:
            raise HTTPException(400,
                                          f"force_band must be one of {list(BAND_MIDPOINTS)}")
        offset_days = BAND_DAYS_OFFSET[force_band]
        synthetic_last_play = _now() - timedelta(days=offset_days)
        # Make playback_logs reflect the synthetic recency:
        # 1. drop any real play_start newer than the synthetic cutoff so
        #    the audience query stops seeing the user as recently-active.
        # 2. seed one synthetic play_start exactly at the offset so
        #    `_days_since_last_play` reads the expected value.
        await db.playback_logs.delete_many(
            {"user_id": user_id, "event": "play_start",
              "timestamp": {"$gt": synthetic_last_play}})
        await db.playback_logs.insert_one({
            "user_id": user_id, "event": "play_start",
            "timestamp": synthetic_last_play,
            "track_id": None, "channel_slug": None,
            "qa_forced": True,
        })
        out = {
            "user_id": user_id,
            "score": BAND_MIDPOINTS[force_band],
            "band": force_band,
            "signals": {"forced": True,
                            "forced_by": admin["user_id"],
                            "forced_at": _now().isoformat(),
                            "forced_last_played_at":
                                synthetic_last_play.isoformat()},
            "computed_at": _now(),
            "expires_at": _now() + timedelta(hours=24),
        }
        await db.churn_scores.update_one(
            {"user_id": user_id}, {"$set": out}, upsert=True)
    else:
        try:
            out = await get_or_recompute(db, user_id, force=True)
        except ValueError as e:
            raise HTTPException(404, str(e))
    if isinstance(out.get("computed_at"), datetime):
        out["computed_at"] = out["computed_at"].isoformat()
    if isinstance(out.get("expires_at"), datetime):
        out["expires_at"] = out["expires_at"].isoformat()
    return out


# ════════════════════════════════════════════════════════════════════════
# Campaign CRUD
# ════════════════════════════════════════════════════════════════════════
@admin_retention_router.get("/triggers")
async def list_triggers(admin: dict = Depends(require_admin)):
    return {"triggers": [{"key": k, **v} for k, v in TRIGGER_DEFS.items()]}


@admin_retention_router.get("/campaigns")
async def list_campaigns(request: Request,
                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    items = []
    async for c in db.lifecycle_campaigns.find({}).sort("created_at", -1):
        items.append(_ser_campaign(c))
    return {"items": items}


@admin_retention_router.post("/campaigns")
async def create_campaign(payload: dict, request: Request,
                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    trigger = (payload or {}).get("trigger")
    if trigger not in TRIGGER_DEFS:
        raise HTTPException(400, f"trigger must be one of {list(TRIGGER_DEFS)}")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    channels = payload.get("channels") or ["email"]
    if not all(c in ("email", "push") for c in channels):
        raise HTTPException(400, "channels must be subset of [email,push]")
    # Phase 13a — A/B variants (optional)
    raw_variants = payload.get("variants") or []
    if raw_variants:
        try:
            variants = normalize_variants(raw_variants)
        except ValueError as e:
            raise HTTPException(400, f"variants invalid: {e}")
        if len(variants) < 2 or len(variants) > 5:
            raise HTTPException(400,
                                          "variants must be 2..5 entries when set")
    else:
        variants = []
    cid = f"cmp_ret_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id": cid, "id": cid, "name": name, "trigger": trigger,
        "audience_filter": payload.get("audience_filter") or {},
        "channels": channels,
        "template": payload.get("template") or {
            "email_subject": "", "email_body": "",
            "push_title": "", "push_body": "",
            "deep_link": "/"},
        "variants": variants,
        "throttle_per_user_per_period": payload.get(
            "throttle_per_user_per_period") or
            {"max_sends": 1, "period_hours": 72},
        "active": bool(payload.get("active", False)),
        "created_at": _now(), "updated_at": _now(),
        "created_by": admin["user_id"],
    }
    await db.lifecycle_campaigns.insert_one(doc)
    return _ser_campaign(doc)


@admin_retention_router.patch("/campaigns/{cid}")
async def patch_campaign(cid: str, payload: dict, request: Request,
                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    allowed = {"name", "audience_filter", "channels", "template",
                  "throttle_per_user_per_period", "active", "variants",
                  "cohort_id"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not update:
        raise HTTPException(400, "no valid fields")
    if "variants" in update:
        raw = update.get("variants") or []
        if raw:
            try:
                update["variants"] = normalize_variants(raw)
            except ValueError as e:
                raise HTTPException(400, f"variants invalid: {e}")
            if not (2 <= len(update["variants"]) <= 5):
                raise HTTPException(400,
                                              "variants must be 2..5 entries when set")
        else:
            update["variants"] = []
    update["updated_at"] = _now()
    res = await db.lifecycle_campaigns.update_one(
        {"id": cid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "campaign not found")
    fresh = await db.lifecycle_campaigns.find_one({"id": cid})
    return _ser_campaign(fresh)


@admin_retention_router.post("/campaigns/{cid}/dry_run")
async def campaign_dry_run(cid: str, request: Request,
                                      admin: dict = Depends(require_admin)):
    db = request.app.state.db
    c = await db.lifecycle_campaigns.find_one({"id": cid})
    if not c:
        raise HTTPException(404, "campaign not found")
    uids = await _audience_user_ids(db, c)
    return {"campaign_id": cid, "audience_size": len(uids),
              "sample_user_ids": uids[:10]}


@admin_retention_router.post("/campaigns/{cid}/run_now")
async def campaign_run_now(cid: str, request: Request,
                                      admin: dict = Depends(require_admin),
                                      max_recipients: int = Query(500,
                                                                                  ge=1, le=5000)):
    db = request.app.state.db
    c = await db.lifecycle_campaigns.find_one({"id": cid})
    if not c:
        raise HTTPException(404, "campaign not found")
    if not c.get("active"):
        raise HTTPException(400, "campaign must be active to run")
    uids = await _audience_user_ids(db, c)
    sent_email = 0; sent_push = 0; skipped = 0
    base_template = c.get("template") or {}
    has_variants = bool(c.get("variants"))
    for uid in uids[:max_recipients]:
        if not await _throttle_ok(db, campaign=c, user_id=uid):
            skipped += 1
            continue
        user = await db.users.find_one({"user_id": uid})
        if not user:
            continue
        vars_ = {"name": user.get("name") or "there",
                    "email": user.get("email") or ""}
        # Phase 13a — pick A/B variant (sticky). None for legacy campaigns.
        variant = None
        variant_slug = None
        if has_variants:
            variant = await pick_variant(db, campaign=c, user_id=uid)
            if variant:
                variant_slug = variant.get("slug")
        effective = (apply_overrides(base_template,
                                                  (variant or {}).get(
                                                      "template_overrides"))
                          if variant else base_template)
        for ch in (c.get("channels") or []):
            if ch == "email":
                await send_email(
                    db, user=user, campaign_id=cid,
                    subject=effective.get("email_subject") or c["name"],
                    body_template=effective.get("email_body") or "",
                    vars=vars_,
                    variant_slug=variant_slug)
                sent_email += 1
            elif ch == "push":
                await send_push(
                    db, user=user, campaign_id=cid,
                    title=effective.get("push_title") or c["name"],
                    body_template=effective.get("push_body") or "",
                    vars=vars_,
                    deep_link=effective.get("deep_link") or "/",
                    variant_slug=variant_slug)
                sent_push += 1
    return {"campaign_id": cid, "audience_size": len(uids),
              "sent_email": sent_email, "sent_push": sent_push,
              "skipped_throttle": skipped}


@admin_retention_router.get("/campaigns/{cid}/stats")
async def campaign_stats(cid: str, request: Request,
                                    admin: dict = Depends(require_admin)):
    db = request.app.state.db
    c = await db.lifecycle_campaigns.find_one({"id": cid})
    if not c:
        raise HTTPException(404, "campaign not found")
    pipe = [{"$match": {"campaign_id": cid}},
              {"$group": {"_id": {"channel": "$channel",
                                       "status": "$status"},
                            "count": {"$sum": 1}}}]
    by_ch: dict[str, dict[str, int]] = {}
    async for r in db.lifecycle_send_log.aggregate(pipe):
        ch = r["_id"]["channel"]; st = r["_id"]["status"]
        by_ch.setdefault(ch, {})[st] = int(r["count"])
    opens = await db.lifecycle_send_log.count_documents(
        {"campaign_id": cid, "opened_at": {"$ne": None}})
    clicks = await db.lifecycle_send_log.count_documents(
        {"campaign_id": cid, "clicked_at": {"$ne": None}})
    converts = await db.lifecycle_send_log.count_documents(
        {"campaign_id": cid, "converted_at": {"$ne": None}})
    return {"campaign_id": cid,
              "by_channel": by_ch,
              "opens": opens, "clicks": clicks,
              "conversions": converts}



# Phase 13a — per-variant funnel + significance.
@admin_retention_router.get("/campaigns/{cid}/variants/stats")
async def campaign_variant_stats(cid: str, request: Request,
                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    c = await db.lifecycle_campaigns.find_one({"id": cid})
    if not c:
        raise HTTPException(404, "campaign not found")
    variants = c.get("variants") or []
    if not variants:
        return {"campaign_id": cid, "has_variants": False,
                  "variants": []}

    # Aggregate per-variant
    rows: list[dict] = []
    for v in variants:
        slug = v["slug"]
        sends = await db.lifecycle_send_log.count_documents(
            {"campaign_id": cid, "variant_slug": slug})
        opens = await db.lifecycle_send_log.count_documents(
            {"campaign_id": cid, "variant_slug": slug,
              "opened_at": {"$ne": None}})
        clicks = await db.lifecycle_send_log.count_documents(
            {"campaign_id": cid, "variant_slug": slug,
              "clicked_at": {"$ne": None}})
        conv = await db.lifecycle_send_log.count_documents(
            {"campaign_id": cid, "variant_slug": slug,
              "converted_at": {"$ne": None}})
        # Phase 13b — sum conversion_value across converted rows.
        cv_cursor = db.lifecycle_send_log.aggregate([
            {"$match": {"campaign_id": cid, "variant_slug": slug,
                              "converted_at": {"$ne": None}}},
            {"$group": {"_id": None,
                              "total": {"$sum": "$conversion_value"}}}])
        cv_total = 0.0
        async for d in cv_cursor:
            cv_total = float(d.get("total") or 0.0)
        rows.append({"slug": slug, "weight": v.get("weight", 1),
                          "sends": sends, "opens": opens,
                          "clicks": clicks, "conversions": conv,
                          "conversion_value_total": cv_total,
                          "open_rate": (opens / sends) if sends else 0.0,
                          "click_rate": (clicks / sends) if sends else 0.0,
                          "conv_rate": (conv / sends) if sends else 0.0})

    # Control = largest-weight variant (stable; ties → first row).
    control = max(rows, key=lambda r: (r["weight"], -rows.index(r)))
    control_slug = control["slug"]
    eligible = all(r["sends"] >= MIN_SEND_PER_VARIANT for r in rows)
    winner_slug: Optional[str] = None
    if eligible and len(rows) >= 2:
        # Find best non-control candidate by conv rate
        cand = sorted([r for r in rows if r["slug"] != control_slug],
                            key=lambda r: -r["conv_rate"])[0]
        z = two_proportion_z(
            n_a=control["sends"], x_a=control["conversions"],
            n_b=cand["sends"], x_b=cand["conversions"])
        for r in rows:
            r["confidence_95"] = False
            r["is_winner"] = False
        if (z["p_value"] < P_VALUE_SIGNIFICANT
                and z["p_b"] > z["p_a"]):
            for r in rows:
                if r["slug"] == cand["slug"]:
                    r["confidence_95"] = True
                    r["is_winner"] = True
                    winner_slug = r["slug"]
                elif r["slug"] == control_slug:
                    r["confidence_95"] = True
        return {"campaign_id": cid, "has_variants": True,
                  "variants": rows, "control_slug": control_slug,
                  "winner_slug": winner_slug,
                  "p_value_vs_control": z["p_value"],
                  "min_sends_per_variant": MIN_SEND_PER_VARIANT}
    for r in rows:
        r["confidence_95"] = False
        r["is_winner"] = False
    return {"campaign_id": cid, "has_variants": True,
              "variants": rows, "control_slug": control_slug,
              "winner_slug": None,
              "p_value_vs_control": None,
              "min_sends_per_variant": MIN_SEND_PER_VARIANT}


# ════════════════════════════════════════════════════════════════════════
# Phase 13b — Conversion funnel + ROI
# ════════════════════════════════════════════════════════════════════════
def _range_to_cutoff(range_: str) -> Optional[datetime]:
    r = (range_ or "30d").lower()
    if r == "all":
        return None
    days = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}.get(r, 30)
    return _now() - timedelta(days=days)


@admin_retention_router.get("/cost_config")
async def cost_config_endpoint(_u: dict = Depends(require_admin)):
    from services.conversion import cost_config
    return cost_config()


async def _funnel_for_campaign(db, cid: str,
                                            cutoff: Optional[datetime]) -> dict:
    base_q = {"campaign_id": cid}
    if cutoff:
        base_q["sent_at"] = {"$gte": cutoff}
    sent = await db.lifecycle_send_log.count_documents(base_q)
    opened = await db.lifecycle_send_log.count_documents(
        {**base_q, "opened_at": {"$ne": None}})
    clicked = await db.lifecycle_send_log.count_documents(
        {**base_q, "clicked_at": {"$ne": None}})
    converted = await db.lifecycle_send_log.count_documents(
        {**base_q, "converted_at": {"$ne": None}})
    cv_total = 0.0
    async for d in db.lifecycle_send_log.aggregate([
            {"$match": {**base_q, "converted_at": {"$ne": None}}},
            {"$group": {"_id": None,
                              "total": {"$sum": "$conversion_value"}}}]):
        cv_total = float(d.get("total") or 0.0)
    # Per-channel counts (for cost estimation)
    sent_email = await db.lifecycle_send_log.count_documents(
        {**base_q, "channel": "email"})
    sent_push = await db.lifecycle_send_log.count_documents(
        {**base_q, "channel": "push"})
    return {"sent": sent, "opened": opened, "clicked": clicked,
              "converted": converted,
              "conversion_value_total": cv_total,
              "sent_email": sent_email, "sent_push": sent_push}


def _rates(totals: dict) -> dict:
    s = totals["sent"] or 0
    o = totals["opened"] or 0
    cl = totals["clicked"] or 0
    cv = totals["converted"] or 0
    return {"open_rate": (o / s) if s else 0.0,
              "click_rate": (cl / s) if s else 0.0,
              "click_to_open_rate": (cl / o) if o else 0.0,
              "conv_rate": (cv / s) if s else 0.0,
              "conv_per_clicked": (cv / cl) if cl else 0.0}


@admin_retention_router.get("/campaigns/{cid}/funnel")
async def campaign_funnel(cid: str, request: Request,
                                    range: str = "30d",
                                    _u: dict = Depends(require_admin)):
    db = request.app.state.db
    c = await db.lifecycle_campaigns.find_one({"id": cid})
    if not c:
        raise HTTPException(404, "campaign not found")
    cutoff = _range_to_cutoff(range)
    totals = await _funnel_for_campaign(db, cid, cutoff)
    rates = _rates(totals)

    from services.conversion import estimate_send_cost
    from services.ab import two_proportion_z, MIN_SEND_PER_VARIANT
    est_cost = estimate_send_cost(
        sent_email=totals["sent_email"], sent_push=totals["sent_push"])

    by_variant: list[dict] = []
    winner_slug: Optional[str] = None
    variants = c.get("variants") or []
    if variants:
        for v in variants:
            slug = v["slug"]
            vq = {"campaign_id": cid, "variant_slug": slug}
            if cutoff:
                vq["sent_at"] = {"$gte": cutoff}
            s = await db.lifecycle_send_log.count_documents(vq)
            o = await db.lifecycle_send_log.count_documents(
                {**vq, "opened_at": {"$ne": None}})
            cl = await db.lifecycle_send_log.count_documents(
                {**vq, "clicked_at": {"$ne": None}})
            cv = await db.lifecycle_send_log.count_documents(
                {**vq, "converted_at": {"$ne": None}})
            cvv = 0.0
            async for d in db.lifecycle_send_log.aggregate([
                    {"$match": {**vq, "converted_at": {"$ne": None}}},
                    {"$group": {"_id": None,
                                      "total": {"$sum": "$conversion_value"}}}]):
                cvv = float(d.get("total") or 0.0)
            by_variant.append({"slug": slug, "weight": v.get("weight", 1),
                                      "sent": s, "opened": o, "clicked": cl,
                                      "converted": cv,
                                      "conversion_value_total": cvv,
                                      "open_rate": (o / s) if s else 0.0,
                                      "click_rate": (cl / s) if s else 0.0,
                                      "conv_rate": (cv / s) if s else 0.0,
                                      "lift_vs_control": None,
                                      "p_value": None})
        # Control = largest-weight; compute lift + p-value for the rest.
        control = max(by_variant, key=lambda r: r["weight"])
        for row in by_variant:
            if row["slug"] == control["slug"]:
                row["lift_vs_control"] = 0.0
                row["p_value"] = None
                continue
            base = control["conv_rate"] or 0.0
            row["lift_vs_control"] = (
                (row["conv_rate"] - base) / base if base else None)
            z = two_proportion_z(
                n_a=control["sent"], x_a=control["converted"],
                n_b=row["sent"], x_b=row["converted"])
            row["p_value"] = z["p_value"]
        eligible = all(r["sent"] >= MIN_SEND_PER_VARIANT
                              for r in by_variant)
        if eligible:
            chal = sorted(
                [r for r in by_variant if r["slug"] != control["slug"]],
                key=lambda r: -r["conv_rate"])
            if (chal and chal[0]["p_value"] is not None
                    and chal[0]["p_value"] < 0.05
                    and chal[0]["conv_rate"] > control["conv_rate"]):
                winner_slug = chal[0]["slug"]

    roi_multiple = (totals["conversion_value_total"] / est_cost
                          if est_cost > 0 else None)
    return {
        "campaign_id": cid, "range": range,
        "totals": {k: totals[k] for k in
                        ("sent", "opened", "clicked", "converted",
                          "conversion_value_total")},
        "rates": rates,
        "by_variant": by_variant,
        "roi": {"estimated_send_cost": est_cost,
                  "conversion_value_total":
                      totals["conversion_value_total"],
                  "roi_multiple": roi_multiple,
                  "winner_variant_slug": winner_slug},
    }


@admin_retention_router.get("/campaigns/top")
async def campaigns_top(request: Request,
                                  range: str = "30d",
                                  metric: str = "roi",
                                  limit: int = 10,
                                  _u: dict = Depends(require_admin)):
    if metric not in ("conv_rate", "roi", "conversions",
                            "conversion_value"):
        raise HTTPException(400, "metric must be one of "
                                  "conv_rate|roi|conversions|conversion_value")
    db = request.app.state.db
    cutoff = _range_to_cutoff(range)
    from services.conversion import estimate_send_cost
    items: list[dict] = []
    async for c in db.lifecycle_campaigns.find({}, projection=None):
        cid = c.get("id") or c.get("_id")
        t = await _funnel_for_campaign(db, cid, cutoff)
        cost = estimate_send_cost(
            sent_email=t["sent_email"], sent_push=t["sent_push"])
        roi = (t["conversion_value_total"] / cost
                  if cost > 0 else 0.0)
        items.append({
            "campaign_id": cid, "name": c.get("name"),
            "trigger": c.get("trigger"),
            "sent": t["sent"], "converted": t["converted"],
            "conv_rate": (t["converted"] / t["sent"])
                              if t["sent"] else 0.0,
            "conversion_value_total": t["conversion_value_total"],
            "estimated_send_cost": cost,
            "roi_multiple": roi,
        })
    key = {"conv_rate": "conv_rate",
              "roi": "roi_multiple",
              "conversions": "converted",
              "conversion_value": "conversion_value_total"}[metric]
    items.sort(key=lambda r: -(r.get(key) or 0.0))
    return {"range": range, "metric": metric,
              "items": items[:max(1, min(limit, 50))]}


# ════════════════════════════════════════════════════════════════════════
# Phase 13c — Cohorts CRUD + behavioral triggers + churn v2
# ════════════════════════════════════════════════════════════════════════
@admin_retention_router.post("/cohorts")
async def cohort_create(request: Request, payload: dict,
                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    dsl = payload.get("filter_dsl") or {}
    # Validate by attempting a walk (raises on bad DSL).
    from services.cohorts import (_walk_dsl, ensure_cohort_indexes,
                                                  resolve_cohort)
    try:
        _walk_dsl(dsl)
    except ValueError as e:
        raise HTTPException(400, f"filter_dsl invalid: {e}")
    await ensure_cohort_indexes(db)
    coh_id = f"coh_{uuid.uuid4().hex[:14]}"
    size = len(await resolve_cohort(db, dsl, limit=100_000))
    doc = {"_id": coh_id, "id": coh_id, "name": name,
              "description": payload.get("description") or "",
              "filter_dsl": dsl,
              "computed_audience_size": size,
              "last_computed_at": _now(),
              "created_by": admin["user_id"],
              "created_at": _now(),
              "deleted": False}
    await db.audience_cohorts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@admin_retention_router.get("/cohorts")
async def cohorts_list(request: Request,
                              _u: dict = Depends(require_admin)):
    db = request.app.state.db
    from services.cohorts import upsert_cohort_size
    out: list[dict] = []
    async for c in db.audience_cohorts.find({"deleted": {"$ne": True}}):
        # Recompute size if cache stale.
        size = await upsert_cohort_size(db, c)
        c["computed_audience_size"] = size
        c.pop("_id", None)
        out.append(c)
    return {"items": out}


@admin_retention_router.get("/cohorts/{cid}/audience")
async def cohort_audience(cid: str, request: Request,
                                    limit: int = 50,
                                    _u: dict = Depends(require_admin)):
    db = request.app.state.db
    coh = await db.audience_cohorts.find_one(
        {"id": cid, "deleted": {"$ne": True}})
    if not coh:
        raise HTTPException(404, "cohort not found")
    from services.cohorts import resolve_cohort
    uids = await resolve_cohort(db, coh.get("filter_dsl") or {},
                                            limit=max(1, min(limit, 500)))
    return {"cohort_id": cid, "audience_size": len(uids),
              "sample_user_ids": uids}


@admin_retention_router.patch("/cohorts/{cid}")
async def cohort_patch(cid: str, request: Request, payload: dict,
                              _u: dict = Depends(require_admin)):
    db = request.app.state.db
    coh = await db.audience_cohorts.find_one(
        {"id": cid, "deleted": {"$ne": True}})
    if not coh:
        raise HTTPException(404, "cohort not found")
    allowed = {"name", "description", "filter_dsl"}
    update = {k: v for k, v in (payload or {}).items() if k in allowed}
    if "filter_dsl" in update:
        from services.cohorts import _walk_dsl, resolve_cohort
        try: _walk_dsl(update["filter_dsl"])
        except ValueError as e:
            raise HTTPException(400, f"filter_dsl invalid: {e}")
        size = len(await resolve_cohort(
            db, update["filter_dsl"], limit=100_000))
        update["computed_audience_size"] = size
        update["last_computed_at"] = _now()
    await db.audience_cohorts.update_one(
        {"id": cid}, {"$set": update})
    return {"updated": True, "cohort_id": cid}


@admin_retention_router.delete("/cohorts/{cid}")
async def cohort_delete(cid: str, request: Request,
                                _u: dict = Depends(require_admin)):
    db = request.app.state.db
    await db.audience_cohorts.update_one(
        {"id": cid},
        {"$set": {"deleted": True, "deleted_at": _now()}})
    return {"deleted": True, "cohort_id": cid}


@admin_retention_router.post("/triggers/dry_run")
async def trigger_dry_run(request: Request, payload: dict,
                                    _u: dict = Depends(require_admin)):
    db = request.app.state.db
    name = (payload.get("trigger") or "").strip()
    params = payload.get("params") or {}
    from services.triggers import run_trigger, TRIGGERS
    if name not in TRIGGERS:
        raise HTTPException(400,
            f"unknown trigger; valid: {sorted(TRIGGERS.keys())}")
    try:
        return await run_trigger(db, name, params)
    except TypeError as e:
        raise HTTPException(400, f"params invalid: {e}")


@admin_retention_router.post("/churn/recompute_all")
async def churn_recompute_all(request: Request,
                                            model: Optional[str] = Query(
                                                None,
                                                description="Override env "
                                                "BIGFM_CHURN_MODEL for this call "
                                                "('v1' or 'v2')."),
                                            _u: dict = Depends(require_admin)):
    db = request.app.state.db
    from services.churn_score import recompute_all
    # Per-call override (UI churn-model toggle uses this).
    prev_env = os.environ.get("BIGFM_CHURN_MODEL")
    if model in ("v1", "v2"):
        os.environ["BIGFM_CHURN_MODEL"] = model
    try:
        out = await recompute_all(db, batch_size=200)
    finally:
        if model in ("v1", "v2"):
            if prev_env is None:
                os.environ.pop("BIGFM_CHURN_MODEL", None)
            else:
                os.environ["BIGFM_CHURN_MODEL"] = prev_env
    out["model_version"] = (model or os.environ.get("BIGFM_CHURN_MODEL")
                                      or "v1").lower()
    return out


@admin_retention_router.get("/churn/model")
async def churn_model_get(_u: dict = Depends(require_admin)):
    """Returns the current churn model setting + last recompute timestamp."""
    return {
        "model": (os.environ.get("BIGFM_CHURN_MODEL") or "v1").lower(),
        "env_var": "BIGFM_CHURN_MODEL",
    }


@admin_retention_router.get("/send_log")
async def get_send_log(request: Request,
                                campaign_id: Optional[str] = None,
                                channel: Optional[str] = None,
                                limit: int = Query(100, ge=1, le=500),
                                admin: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {}
    if campaign_id: q["campaign_id"] = campaign_id
    if channel: q["channel"] = channel
    cur = db.lifecycle_send_log.find(q).sort("sent_at", -1).limit(limit)
    items = []
    async for d in cur:
        d.pop("_id", None)
        for f in ("sent_at", "opened_at", "clicked_at", "converted_at"):
            v = d.get(f)
            if isinstance(v, datetime):
                d[f] = v.isoformat()
        items.append(d)
    return {"items": items}


# ════════════════════════════════════════════════════════════════════════
# /api/me/reactivation_prompt
# ════════════════════════════════════════════════════════════════════════
_PROMPT_TEMPLATES = {
    "dormant": {
        "headline": "We miss you on FUUSIC 👋",
        "body": ("It's been a while.  Tap to grab a 50%-off premium "
                  "trial — back to your favourite channels in seconds."),
        "cta_label": "Resume listening",
        "cta_href": "/?utm_campaign=reactivate_dormant",
    },
    "at_risk": {
        "headline": "Pick up where you left off",
        "body": "Your channels are ready.  One tap to dive back in.",
        "cta_label": "Play now",
        "cta_href": "/?utm_campaign=reactivate_at_risk",
    },
}


@me_retention_router.get("/reactivation_prompt")
async def get_reactivation_prompt(request: Request,
                                                  response: Response,
                                                  user: dict = Depends(current_user)):
    """Returns a 200 with a prompt body when user is at_risk / dormant
    AND the user hasn't dismissed within the dismiss-window.  Returns
    204 (no body) for healthy users."""
    db = request.app.state.db
    payload = await get_or_recompute(db, user["user_id"])
    band = payload.get("band")
    if band not in ("at_risk", "dormant"):
        response.status_code = 204
        return None
    # Honor dismissal
    dismiss = await db.reactivation_dismiss.find_one(
        {"user_id": user["user_id"]})
    if dismiss and dismiss.get("until"):
        until = dismiss["until"]
        if isinstance(until, datetime):
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > _now():
                response.status_code = 204
                return None
    tpl = _PROMPT_TEMPLATES.get(band) or _PROMPT_TEMPLATES["at_risk"]
    return {
        "prompt_type": band,
        "headline": tpl["headline"],
        "body": tpl["body"],
        "cta_label": tpl["cta_label"],
        "cta_href": tpl["cta_href"],
        "score": payload.get("score"),
        "dismissable_until": (_now() + timedelta(days=3)).isoformat(),
    }


@me_retention_router.post("/reactivation_prompt/dismiss")
async def dismiss_reactivation_prompt(request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    until = _now() + timedelta(days=3)
    await db.reactivation_dismiss.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "until": until,
                    "dismissed_at": _now()}},
        upsert=True)
    return {"ok": True, "dismissed_until": until.isoformat()}


# ════════════════════════════════════════════════════════════════════════
# Tracking endpoints (/api/r/{tracking_id}/{pixel.gif|click})
# ════════════════════════════════════════════════════════════════════════
@tracking_router.get("/{tracking_id}/pixel.gif")
async def tracking_pixel(tracking_id: str, request: Request):
    db = request.app.state.db
    await db.lifecycle_send_log.update_one(
        {"tracking_id": tracking_id, "opened_at": None},
        {"$set": {"opened_at": _now()}})
    return Response(content=_PIXEL_GIF, media_type="image/gif",
                          headers={"Cache-Control": "no-store"})


@tracking_router.get("/{tracking_id}/click")
async def tracking_click(tracking_id: str, request: Request,
                                to: str = Query("/")):
    db = request.app.state.db
    await db.lifecycle_send_log.update_one(
        {"tracking_id": tracking_id},
        {"$set": {"clicked_at": _now()}})
    # Only allow same-origin or relative destinations
    dest = to
    if not (dest.startswith("/") or dest.startswith(
            request.app.state.public_backend_url or "")):
        dest = "/"
    return RedirectResponse(url=dest, status_code=302)


# Phase 13b — explicit conversion tracking (open: tracking_id is the secret).
@tracking_router.post("/{tracking_id}/converted")
async def tracking_converted(tracking_id: str, request: Request):
    db = request.app.state.db
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    value = float(body.get("value") or body.get(
        "conversion_value") or 0.0)
    event_type = body.get("event_type") or "explicit"
    conversion_id = body.get("conversion_id")
    # Idempotent: only set converted_at if currently None.
    res = await db.lifecycle_send_log.update_one(
        {"tracking_id": tracking_id, "converted_at": None},
        {"$set": {"converted_at": _now(),
                    "conversion_value": value,
                    "conversion_event_type": event_type,
                    **({"conversion_id": conversion_id}
                          if conversion_id else {})}})
    return {"tracking_id": tracking_id,
              "attributed": bool(res.modified_count),
              "value": value}
