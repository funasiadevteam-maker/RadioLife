"""Partner API v1 — Phase E: Merchant API, reward-events/conversions,
bulk sync + async jobs, analytics and billing.

All of Phase E is a thin, partner-scoped facade over new bookkeeping
collections. It NEVER mutates real listener wallets or the internal ad
engine's billing — it safely INGESTS partner-reported events (idempotent,
de-duped, validated, capped) and READS aggregated numbers back out.

Collections (all keyed by partner_id + environment so LIVE/SANDBOX never
collide):
  • partner_merchants        merchant businesses onboarded by a partner
  • partner_offers           coupons/offers under a merchant business
  • partner_reward_events    safe, de-duped reward events reported by partners
  • partner_conversions      conversions attributed to campaigns/creatives
  • partner_jobs             async bulk-sync jobs (queued → completed/failed)
  • partner_invoices         generated monthly billing statements (cached)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services import partner_api as pa
from services import partner_api_ext as ext
from services.partner_api import Caller

log = logging.getLogger("bigfm.partner_api.phase_e")

# ── validation constants ────────────────────────────────────────────
REWARD_EVENT_TYPES = {
    "listen_minutes", "purchase", "signup", "referral", "coupon_redeemed",
    "survey_completed", "app_open", "share", "custom",
}
CONVERSION_TYPES = {
    "purchase", "signup", "lead", "install", "subscription",
    "add_to_cart", "page_view", "custom",
}
OFFER_TYPES = {"percent", "amount", "bogo", "freebie", "custom"}
BULK_OPERATIONS = {"reward_events", "conversions", "offers"}
# operation → the scope a caller must hold to run it in bulk
BULK_OP_SCOPE = {"reward_events": "rewards:write",
                 "conversions": "conversions:write",
                 "offers": "merchant:write"}

MAX_BULK_ITEMS = 1000
MAX_REWARD_VALUE_CENTS = 1_000_000
MAX_REWARD_POINTS = 1_000_000
MAX_CONVERSION_VALUE_CENTS = 10_000_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:18]}"


def _clean(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return d
    out = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def _parse_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        raise ValueError("invalid_datetime")


# ── index bootstrap ─────────────────────────────────────────────────
async def ensure_phase_e_indexes(db) -> None:
    await db.partner_merchants.create_index("merchant_id", unique=True)
    await db.partner_merchants.create_index([("partner_id", 1), ("environment", 1)])
    await db.partner_offers.create_index("offer_id", unique=True)
    await db.partner_offers.create_index([("partner_id", 1), ("environment", 1), ("merchant_id", 1)])
    await db.partner_reward_events.create_index("event_id", unique=True)
    await db.partner_reward_events.create_index(
        [("partner_id", 1), ("environment", 1), ("created_at", -1)])
    await db.partner_conversions.create_index("conversion_id", unique=True)
    await db.partner_conversions.create_index(
        [("partner_id", 1), ("environment", 1), ("created_at", -1)])
    await db.partner_jobs.create_index("job_id", unique=True)
    await db.partner_jobs.create_index([("partner_id", 1), ("environment", 1), ("created_at", -1)])
    await db.partner_invoices.create_index("invoice_id", unique=True)
    await db.partner_invoices.create_index([("partner_id", 1), ("environment", 1), ("period", -1)])
    log.info("[partner_api.phase_e] indexes ensured")


# ═══════════════════════════ Merchant API ═══════════════════════════
def _merchant_view(d: dict) -> dict:
    return _clean(d)


async def create_merchant(db, caller: Caller, *, name: str, category: Optional[str] = None,
                          contact_email: Optional[str] = None, website: Optional[str] = None,
                          description: Optional[str] = None,
                          external_id: Optional[str] = None) -> dict:
    mid = _gid("mrc")
    now = _now()
    doc = {"_id": mid, "merchant_id": mid, "partner_id": caller.partner_id,
           "environment": caller.environment, "name": (name or "").strip(),
           "category": category, "contact_email": (contact_email or "").strip().lower() or None,
           "website": website, "description": description, "status": "active",
           "external_id": external_id, "created_at": now, "updated_at": now}
    await db.partner_merchants.insert_one(doc)
    return _merchant_view(doc)


async def get_merchant(db, caller: Caller, merchant_id: str) -> Optional[dict]:
    d = await db.partner_merchants.find_one(
        {"merchant_id": merchant_id, "partner_id": caller.partner_id,
         "environment": caller.environment})
    return _merchant_view(d) if d else None


async def list_merchants(db, caller: Caller, *, external_id: Optional[str] = None) -> list[dict]:
    q = {"partner_id": caller.partner_id, "environment": caller.environment}
    if external_id:
        q["external_id"] = external_id
    return [_merchant_view(d) async for d in
            db.partner_merchants.find(q).sort("created_at", -1)]


async def patch_merchant(db, caller: Caller, merchant_id: str, patch: dict) -> Optional[dict]:
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        raise ValueError("empty_patch")
    patch["updated_at"] = _now()
    r = await db.partner_merchants.update_one(
        {"merchant_id": merchant_id, "partner_id": caller.partner_id,
         "environment": caller.environment}, {"$set": patch})
    if r.matched_count == 0:
        return None
    return await get_merchant(db, caller, merchant_id)


async def _assert_merchant(db, caller: Caller, merchant_id: str) -> dict:
    d = await db.partner_merchants.find_one(
        {"merchant_id": merchant_id, "partner_id": caller.partner_id,
         "environment": caller.environment})
    if not d:
        raise LookupError("merchant_not_found")
    return d


async def create_offer(db, caller: Caller, merchant_id: str, *, title: str,
                       offer_type: str = "percent", value: Optional[float] = None,
                       code: Optional[str] = None, description: Optional[str] = None,
                       starts_at: Any = None, ends_at: Any = None,
                       external_id: Optional[str] = None) -> dict:
    await _assert_merchant(db, caller, merchant_id)
    if offer_type not in OFFER_TYPES:
        raise ValueError("invalid_offer_type")
    oid = _gid("off")
    now = _now()
    doc = {"_id": oid, "offer_id": oid, "merchant_id": merchant_id,
           "partner_id": caller.partner_id, "environment": caller.environment,
           "title": (title or "").strip(), "offer_type": offer_type,
           "value": value, "code": (code or "").strip().upper() or None,
           "description": description, "status": "active",
           "starts_at": _parse_dt(starts_at), "ends_at": _parse_dt(ends_at),
           "external_id": external_id, "created_at": now, "updated_at": now}
    await db.partner_offers.insert_one(doc)
    return _clean(doc)


async def list_offers(db, caller: Caller, merchant_id: str,
                      *, external_id: Optional[str] = None) -> list[dict]:
    q = {"partner_id": caller.partner_id, "environment": caller.environment,
         "merchant_id": merchant_id}
    if external_id:
        q["external_id"] = external_id
    return [_clean(d) async for d in db.partner_offers.find(q).sort("created_at", -1)]


async def patch_offer(db, caller: Caller, offer_id: str, patch: dict) -> Optional[dict]:
    patch = {k: v for k, v in patch.items() if v is not None}
    if "offer_type" in patch and patch["offer_type"] not in OFFER_TYPES:
        raise ValueError("invalid_offer_type")
    if not patch:
        raise ValueError("empty_patch")
    for k in ("starts_at", "ends_at"):
        if k in patch:
            patch[k] = _parse_dt(patch[k])
    patch["updated_at"] = _now()
    r = await db.partner_offers.update_one(
        {"offer_id": offer_id, "partner_id": caller.partner_id,
         "environment": caller.environment}, {"$set": patch})
    if r.matched_count == 0:
        return None
    return _clean(await db.partner_offers.find_one({"offer_id": offer_id}))


# ═══════════════════ safe reward events + conversions ═══════════════
async def record_reward_event(db, caller: Caller, *, type: str,
                              value_cents: int = 0, points: int = 0,
                              user_ref: Optional[str] = None,
                              campaign_id: Optional[str] = None,
                              external_id: Optional[str] = None,
                              metadata: Optional[dict] = None,
                              occurred_at: Any = None) -> tuple[dict, bool]:
    """Idempotent, de-duped, validated reward-event ingestion. Returns
    (event, created). A repeated external_id returns the SAME event and
    never double-records. Values are capped to prevent abuse."""
    if type not in REWARD_EVENT_TYPES:
        raise ValueError("invalid_reward_event_type")
    value_cents = max(0, min(int(value_cents or 0), MAX_REWARD_VALUE_CENTS))
    points = max(0, min(int(points or 0), MAX_REWARD_POINTS))
    dup = await ext.external_get(db, caller, "reward_event", external_id)
    if dup is not None:
        return dup, False
    eid = _gid("rev")
    now = _now()
    doc = {"_id": eid, "event_id": eid, "partner_id": caller.partner_id,
           "environment": caller.environment, "type": type,
           "value_cents": value_cents, "points": points, "user_ref": user_ref,
           "campaign_id": campaign_id, "external_id": external_id,
           "metadata": metadata or {}, "status": "recorded", "credited": False,
           "occurred_at": _parse_dt(occurred_at) or now, "created_at": now}
    await db.partner_reward_events.insert_one(doc)
    view = _clean(doc)
    await ext.external_save(db, caller, "reward_event", external_id, eid, view)
    return view, True


async def get_reward_event(db, caller: Caller, event_id: str) -> Optional[dict]:
    d = await db.partner_reward_events.find_one(
        {"event_id": event_id, "partner_id": caller.partner_id,
         "environment": caller.environment})
    return _clean(d) if d else None


async def list_reward_events(db, caller: Caller, *, type: Optional[str] = None,
                             status: Optional[str] = None,
                             external_id: Optional[str] = None) -> list[dict]:
    q = {"partner_id": caller.partner_id, "environment": caller.environment}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    if external_id:
        q["external_id"] = external_id
    return [_clean(d) async for d in
            db.partner_reward_events.find(q).sort("created_at", -1).limit(1000)]


async def record_conversion(db, caller: Caller, *, conversion_type: str,
                           value_cents: int = 0, campaign_id: Optional[str] = None,
                           creative_id: Optional[str] = None,
                           advertiser_id: Optional[str] = None,
                           user_ref: Optional[str] = None,
                           external_id: Optional[str] = None,
                           metadata: Optional[dict] = None,
                           occurred_at: Any = None) -> tuple[dict, bool]:
    """Idempotent conversion ingestion attributed to a campaign/creative.
    Returns (conversion, created). Repeated external_id returns the same row."""
    if conversion_type not in CONVERSION_TYPES:
        raise ValueError("invalid_conversion_type")
    value_cents = max(0, min(int(value_cents or 0), MAX_CONVERSION_VALUE_CENTS))
    dup = await ext.external_get(db, caller, "conversion", external_id)
    if dup is not None:
        return dup, False
    cid = _gid("cnv")
    now = _now()
    doc = {"_id": cid, "conversion_id": cid, "partner_id": caller.partner_id,
           "environment": caller.environment, "conversion_type": conversion_type,
           "value_cents": value_cents, "campaign_id": campaign_id,
           "creative_id": creative_id, "advertiser_id": advertiser_id,
           "user_ref": user_ref, "external_id": external_id,
           "metadata": metadata or {}, "occurred_at": _parse_dt(occurred_at) or now,
           "created_at": now}
    await db.partner_conversions.insert_one(doc)
    view = _clean(doc)
    await ext.external_save(db, caller, "conversion", external_id, cid, view)
    return view, True


async def get_conversion(db, caller: Caller, conversion_id: str) -> Optional[dict]:
    d = await db.partner_conversions.find_one(
        {"conversion_id": conversion_id, "partner_id": caller.partner_id,
         "environment": caller.environment})
    return _clean(d) if d else None


async def list_conversions(db, caller: Caller, *, conversion_type: Optional[str] = None,
                          campaign_id: Optional[str] = None,
                          external_id: Optional[str] = None) -> list[dict]:
    q = {"partner_id": caller.partner_id, "environment": caller.environment}
    if conversion_type:
        q["conversion_type"] = conversion_type
    if campaign_id:
        q["campaign_id"] = campaign_id
    if external_id:
        q["external_id"] = external_id
    return [_clean(d) async for d in
            db.partner_conversions.find(q).sort("created_at", -1).limit(1000)]


# ═══════════════════ bulk sync + async jobs ═════════════════════════
async def create_job(db, caller: Caller, *, operation: str, items: list[dict]) -> dict:
    if operation not in BULK_OPERATIONS:
        raise ValueError("invalid_bulk_operation")
    if not isinstance(items, list) or not items:
        raise ValueError("items_required")
    if len(items) > MAX_BULK_ITEMS:
        raise ValueError("too_many_items")
    jid = _gid("job")
    now = _now()
    doc = {"_id": jid, "job_id": jid, "partner_id": caller.partner_id,
           "environment": caller.environment, "operation": operation,
           "status": "queued", "total": len(items), "succeeded": 0,
           "failed": 0, "duplicates": 0, "items": items, "results": [],
           "error": None, "created_at": now, "updated_at": now,
           "completed_at": None}
    await db.partner_jobs.insert_one(doc)
    return _job_view(doc)


def _job_view(d: dict, *, include_results: bool = True) -> dict:
    out = {k: v for k, v in (d or {}).items() if k not in ("_id", "items")}
    if not include_results:
        out.pop("results", None)
    for k in ("created_at", "updated_at", "completed_at"):
        if isinstance(out.get(k), datetime):
            out[k] = out[k].isoformat()
    return out


async def run_job(db, job_id: str) -> None:
    """Background processor — walks the job's items through the safe
    single-record path so bulk shares the exact same dedup/validation."""
    job = await db.partner_jobs.find_one({"job_id": job_id})
    if not job or job.get("status") != "queued":
        return
    await db.partner_jobs.update_one(
        {"job_id": job_id}, {"$set": {"status": "processing", "updated_at": _now()}})
    caller = Caller(partner_id=job["partner_id"], environment=job["environment"],
                    scopes=set(), credential_type="job", credential_id=job_id)
    op = job["operation"]
    results, succeeded, failed, dups = [], 0, 0, 0
    for i, item in enumerate(job.get("items") or []):
        try:
            if op == "reward_events":
                rec, created = await record_reward_event(db, caller, **_reward_kwargs(item))
                rid = rec.get("event_id")
            elif op == "conversions":
                rec, created = await record_conversion(db, caller, **_conversion_kwargs(item))
                rid = rec.get("conversion_id")
            else:  # offers
                merchant_id = item.get("merchant_id")
                if not merchant_id:
                    raise ValueError("merchant_id_required")
                rec = await create_offer(db, caller, merchant_id, **_offer_kwargs(item))
                rid, created = rec.get("offer_id"), True
            if created:
                succeeded += 1
                results.append({"index": i, "status": "ok", "id": rid})
            else:
                dups += 1
                results.append({"index": i, "status": "duplicate", "id": rid})
        except Exception as e:  # one bad row never sinks the job
            failed += 1
            results.append({"index": i, "status": "error", "error": str(e)})
    await db.partner_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "completed", "succeeded": succeeded, "failed": failed,
                  "duplicates": dups, "results": results,
                  "updated_at": _now(), "completed_at": _now()}})
    try:
        await pa.emit_event(db, partner_id=job["partner_id"], environment=job["environment"],
                            event_type="job.completed",
                            data={"job_id": job_id, "operation": op, "total": job.get("total"),
                                  "succeeded": succeeded, "failed": failed, "duplicates": dups})
    except Exception:
        pass


def _reward_kwargs(item: dict) -> dict:
    return {"type": item.get("type"), "value_cents": item.get("value_cents", 0),
            "points": item.get("points", 0), "user_ref": item.get("user_ref"),
            "campaign_id": item.get("campaign_id"), "external_id": item.get("external_id"),
            "metadata": item.get("metadata"), "occurred_at": item.get("occurred_at")}


def _conversion_kwargs(item: dict) -> dict:
    return {"conversion_type": item.get("conversion_type"), "value_cents": item.get("value_cents", 0),
            "campaign_id": item.get("campaign_id"), "creative_id": item.get("creative_id"),
            "advertiser_id": item.get("advertiser_id"), "user_ref": item.get("user_ref"),
            "external_id": item.get("external_id"), "metadata": item.get("metadata"),
            "occurred_at": item.get("occurred_at")}


def _offer_kwargs(item: dict) -> dict:
    return {"title": item.get("title"), "offer_type": item.get("offer_type", "percent"),
            "value": item.get("value"), "code": item.get("code"),
            "description": item.get("description"), "starts_at": item.get("starts_at"),
            "ends_at": item.get("ends_at"), "external_id": item.get("external_id")}


async def get_job(db, caller: Caller, job_id: str) -> Optional[dict]:
    d = await db.partner_jobs.find_one(
        {"job_id": job_id, "partner_id": caller.partner_id,
         "environment": caller.environment})
    return _job_view(d) if d else None


async def list_jobs(db, caller: Caller) -> list[dict]:
    return [_job_view(d, include_results=False) async for d in
            db.partner_jobs.find({"partner_id": caller.partner_id,
                                  "environment": caller.environment})
            .sort("created_at", -1).limit(500)]


# ═══════════════════════════ analytics ══════════════════════════════
async def _sum_field(db, coll: str, match: dict, field: str) -> tuple[int, int]:
    """Return (count, sum(field)) via aggregation."""
    pipeline = [{"$match": match},
                {"$group": {"_id": None, "count": {"$sum": 1},
                            "total": {"$sum": f"${field}"}}}]
    async for row in db[coll].aggregate(pipeline):
        return int(row.get("count", 0)), int(row.get("total", 0) or 0)
    return 0, 0


async def analytics_summary(db, caller: Caller, *, days: int = 30) -> dict:
    since = _now() - timedelta(days=max(1, min(days, 365)))
    usage = await pa.compute_usage(db, partner_id=caller.partner_id, days=days)
    env_match = {"partner_id": caller.partner_id, "environment": caller.environment,
                 "created_at": {"$gte": since}}
    conv_count, conv_value = await _sum_field(db, "partner_conversions", env_match, "value_cents")
    rew_count, rew_points = await _sum_field(db, "partner_reward_events", env_match, "points")
    _, rew_value = await _sum_field(db, "partner_reward_events", env_match, "value_cents")
    merchants = await db.partner_merchants.count_documents(
        {"partner_id": caller.partner_id, "environment": caller.environment})
    offers = await db.partner_offers.count_documents(
        {"partner_id": caller.partner_id, "environment": caller.environment})
    return {
        "days": days, "environment": caller.environment,
        "campaigns": usage.get("campaigns", 0),
        "active_campaigns": usage.get("active_campaigns", 0),
        "spend_cents": usage.get("spend_cents", 0),
        "impressions": usage.get("impressions", 0),
        "clicks": usage.get("clicks", 0),
        "ctr": usage.get("ctr", 0.0),
        "api_calls": usage.get("total_calls", 0),
        "conversions": conv_count, "conversion_value_cents": conv_value,
        "reward_events": rew_count, "reward_points": rew_points,
        "reward_value_cents": rew_value,
        "merchants": merchants, "offers": offers,
        "cvr": round(conv_count / usage["clicks"], 4) if usage.get("clicks") else 0.0,
    }


_TS_METRICS = {"conversions", "conversion_value", "reward_events", "reward_points", "api_calls"}


async def analytics_timeseries(db, caller: Caller, *, metric: str, days: int = 30) -> dict:
    if metric not in _TS_METRICS:
        raise ValueError("invalid_metric")
    days = max(1, min(days, 365))
    since = _now() - timedelta(days=days)
    buckets: dict[str, float] = {}
    if metric == "api_calls":
        async for c in db.partner_api_calls.find(
                {"partner_id": caller.partner_id, "ts": {"$gte": since}}, {"day": 1}):
            d = c.get("day")
            buckets[d] = buckets.get(d, 0) + 1
    else:
        coll = "partner_conversions" if metric.startswith("conversion") else "partner_reward_events"
        field = {"conversion_value": "value_cents", "reward_points": "points"}.get(metric)
        match = {"partner_id": caller.partner_id, "environment": caller.environment,
                 "created_at": {"$gte": since}}
        async for r in db[coll].find(match, {"created_at": 1, "value_cents": 1, "points": 1}):
            day = r["created_at"].date().isoformat() if isinstance(r.get("created_at"), datetime) else None
            if not day:
                continue
            inc = float(r.get(field, 0) or 0) if field else 1
            buckets[day] = buckets.get(day, 0) + inc
    series = [{"date": d, "value": buckets[d]} for d in sorted(buckets)]
    return {"metric": metric, "days": days, "environment": caller.environment,
            "series": series, "total": sum(buckets.values())}


# ═══════════════════════════ billing ════════════════════════════════
async def _partner_advertisers(db, caller: Caller) -> list[dict]:
    return [a async for a in db.advertisers_v2.find({"owner_user_id": caller.owner_id})]


async def billing_summary(db, caller: Caller, *, days: int = 30) -> dict:
    since = _now() - timedelta(days=max(1, min(days, 365)))
    advs = await _partner_advertisers(db, caller)
    balance = sum(int(a.get("budget_available_cents") or 0) for a in advs)
    adv_ids = [a["advertiser_id"] for a in advs]
    lifetime_spend = 0
    if adv_ids:
        async for c in db.ad_campaigns_v2.find(
                {"advertiser_id": {"$in": adv_ids}}, {"budget_spent_cents": 1}):
            lifetime_spend += int(c.get("budget_spent_cents") or 0)
    _, conv_value = await _sum_field(
        db, "partner_conversions",
        {"partner_id": caller.partner_id, "environment": caller.environment,
         "created_at": {"$gte": since}}, "value_cents")
    invoices = await db.partner_invoices.count_documents(
        {"partner_id": caller.partner_id, "environment": caller.environment})
    now = _now()
    return {
        "environment": caller.environment, "currency": "usd",
        "balance_cents": balance, "lifetime_spend_cents": lifetime_spend,
        "period_conversion_value_cents": conv_value,
        "advertisers": len(advs), "invoices": invoices,
        "current_period": {"start": now.replace(day=1, hour=0, minute=0, second=0,
                                                 microsecond=0).isoformat(),
                           "end": now.isoformat()},
    }


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _aware(dt: Any) -> Optional[datetime]:
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _generate_invoices(db, caller: Caller, *, months: int = 12) -> list[dict]:
    """Build monthly billing statements from real partner activity:
    ad-campaign spend (allocated to the campaign's created month) plus
    marketplace promotion payments purchased via the API. Idempotently
    cached in partner_invoices; the current month stays 'open'."""
    horizon = _now() - timedelta(days=31 * months)
    env_tag = "test" if caller.is_sandbox else "live"
    months_map: dict[str, dict] = {}

    def _bucket(period: str) -> dict:
        return months_map.setdefault(period, {"line_items": [], "subtotal_cents": 0})

    advs = await _partner_advertisers(db, caller)
    adv_ids = [a["advertiser_id"] for a in advs]
    if adv_ids:
        async for c in db.ad_campaigns_v2.find(
                {"advertiser_id": {"$in": adv_ids}},
                {"campaign_id": 1, "name": 1, "budget_spent_cents": 1, "created_at": 1}):
            created = _aware(c.get("created_at"))
            if not created or created < horizon:
                continue
            spent = int(c.get("budget_spent_cents") or 0)
            b = _bucket(_month_key(created))
            b["line_items"].append({
                "type": "ad_delivery", "ref": c.get("campaign_id"),
                "description": f"Ad delivery — {c.get('name') or c.get('campaign_id')} (spend to date)",
                "amount_cents": spent})
            b["subtotal_cents"] += spent

    async for p in db.marketplace_promotions.find(
            {"purchased_by_partner": caller.partner_id,
             "purchased_by_partner_env": caller.environment}):
        created = _aware(p.get("created_at"))
        if not created or created < horizon:
            continue
        amt = int(p.get("price_cents") or 0)
        b = _bucket(_month_key(created))
        b["line_items"].append({
            "type": "marketplace_promotion", "ref": p.get("promotion_id"),
            "description": f"Marketplace promotion — {p.get('tier')} tier",
            "amount_cents": amt})
        b["subtotal_cents"] += amt

    now = _now()
    current = _month_key(now)
    out = []
    for period, data in months_map.items():
        invoice_id = f"inv_{env_tag}_{caller.partner_id}_{period.replace('-', '')}"
        doc = {"_id": invoice_id, "invoice_id": invoice_id,
               "partner_id": caller.partner_id, "environment": caller.environment,
               "period": period, "currency": "usd",
               "status": "open" if period == current else "final",
               "line_items": data["line_items"],
               "subtotal_cents": data["subtotal_cents"],
               "total_cents": data["subtotal_cents"], "updated_at": now}
        await db.partner_invoices.update_one(
            {"invoice_id": invoice_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True)
        stored = await db.partner_invoices.find_one({"invoice_id": invoice_id})
        out.append(_clean(stored))
    out.sort(key=lambda x: x["period"], reverse=True)
    return out


async def list_invoices(db, caller: Caller) -> list[dict]:
    return await _generate_invoices(db, caller)


async def get_invoice(db, caller: Caller, invoice_id: str) -> Optional[dict]:
    await _generate_invoices(db, caller)
    d = await db.partner_invoices.find_one(
        {"invoice_id": invoice_id, "partner_id": caller.partner_id,
         "environment": caller.environment})
    return _clean(d) if d else None


__all__ = [
    "REWARD_EVENT_TYPES", "CONVERSION_TYPES", "OFFER_TYPES", "BULK_OPERATIONS",
    "BULK_OP_SCOPE", "MAX_BULK_ITEMS", "ensure_phase_e_indexes",
    "create_merchant", "get_merchant", "list_merchants", "patch_merchant",
    "create_offer", "list_offers", "patch_offer",
    "record_reward_event", "get_reward_event", "list_reward_events",
    "record_conversion", "get_conversion", "list_conversions",
    "create_job", "run_job", "get_job", "list_jobs",
    "analytics_summary", "analytics_timeseries",
    "billing_summary", "list_invoices", "get_invoice",
]
