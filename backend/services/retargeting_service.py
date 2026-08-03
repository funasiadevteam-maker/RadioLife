"""Phase M — M6 Retargeting Audiences.

Layer sits ON TOP of the existing ad system.  Advertisers define
audiences by behavioral signals (users who did X in the past N
days), then attach a *retargeting campaign* that boosts one of
their EXISTING ads (banner / coupon / notification / marketplace
slot / sponsored read / takeover / location boost) when that ad
is served to a user who is in the audience.

Reuses:
    * `advertisers_v2` for ownership checks (same pattern as
      Phase K + Phase L).
    * `payment_transactions_v2` for the Stripe prepay row.
    * Phase J's `location_boost_service.select_candidates` return
      shape — we return the same shape so the AD.11 banner auction
      can compare us against location-boost candidates trivially.
    * Phase J opt-out pattern for privacy — extends users doc with
      `retargeting_opt_out: bool`.
    * All 11 signal collections listed in M.2 (already have
      user_id available except `payment_transactions_v2` which uses
      `customer_user_id` — we handle that below).

Money model:
    total_budget_cents = advertiser-provided
    platform_fee_cents = 25% of total_budget_cents
    grand_total_cents  = budget + fee
    Admin gate         = grand_total_cents >= $500 (50000 cents)
    Refund on cancel   = remaining_budget_cents + unspent fee pro-rata
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("bigfm.m6_retargeting")

# ── Constants ─────────────────────────────────────────────────────
PLATFORM_FEE_PCT           = 25
ADMIN_APPROVAL_THRESHOLD   = 50_000
MAX_RULES                  = 5
MAX_LOOKBACK_DAYS          = 90
MAX_AUDIENCE_SIZE          = 50_000
IMPRESSION_DEDUP_MIN       = 15
BASE_AD_TYPES = {
    "banner", "coupon", "notification", "marketplace_slot",
    "sponsored_read", "takeover", "location_boost",
}

SIGNAL_TYPES: Set[str] = {
    "listen_minutes_total",
    "podcast_completions",
    "trivia_games_played",
    "coupons_saved",
    "marketplace_saves",
    "scan_to_pay_txns",
    "location_matched_geofence",
    "takeover_listened",
    "predict_win_participated",
    "station_played_specific",
    "merchant_visited_specific",
}
_STATUSES_AUDIENCE = {"draft", "active", "paused", "archived"}
_STATUSES_CAMPAIGN = {"draft", "pending_moderation", "pending_admin",
                      "active", "paused", "completed", "cancelled"}


# ── Helpers ───────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _shape(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return d
    out = dict(d)
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def ensure_retargeting_indexes(db) -> None:
    try:
        await db.retargeting_audiences.create_index(
            "id", unique=True, name="rta_id_uniq")
        await db.retargeting_audiences.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="rta_adv_status")

        await db.retargeting_audience_members.create_index(
            "id", unique=True, name="rtam_id_uniq")
        await db.retargeting_audience_members.create_index(
            [("audience_id", 1), ("user_id", 1)],
            unique=True, name="rtam_aud_user_uniq")
        await db.retargeting_audience_members.create_index(
            [("user_id", 1)], name="rtam_user")

        await db.retargeting_campaigns.create_index(
            "id", unique=True, name="rtc_id_uniq")
        await db.retargeting_campaigns.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="rtc_adv_status")
        await db.retargeting_campaigns.create_index(
            [("audience_id", 1), ("status", 1)],
            name="rtc_aud_status")
        await db.retargeting_campaigns.create_index(
            [("base_ad_type", 1), ("status", 1)],
            name="rtc_type_status")

        await db.retargeting_impressions.create_index(
            "id", unique=True, name="rtimp_id_uniq")
        await db.retargeting_impressions.create_index(
            [("campaign_id", 1), ("user_id", 1), ("dedup_bucket", 1)],
            unique=True, name="rtimp_dedup_uniq")
        await db.retargeting_impressions.create_index(
            [("campaign_id", 1), ("served_at", -1)],
            name="rtimp_camp_served")
        logger.info("[m6_retargeting] indexes ready")
    except Exception as e:
        logger.warning("[m6_retargeting] index setup failed: %s", e)


# ── Rule validation ──────────────────────────────────────────────
def _validate_rules(rules: List[Dict[str, Any]],
                    rule_logic: str) -> List[Dict[str, Any]]:
    if not isinstance(rules, list) or not rules:
        raise ValueError("at_least_one_rule_required")
    if len(rules) > MAX_RULES:
        raise ValueError(f"max_rules_exceeded:limit={MAX_RULES}")
    if rule_logic not in ("AND", "OR"):
        raise ValueError("invalid_rule_logic")
    out = []
    for i, r in enumerate(rules):
        sig = (r.get("signal_type") or "").strip()
        if sig not in SIGNAL_TYPES:
            raise ValueError(f"unknown_signal_type:{sig}")
        cmp_ = (r.get("comparator") or ">=").strip()
        if cmp_ not in (">=", ">", "=="):
            raise ValueError(f"invalid_comparator:{cmp_}")
        try:
            val = float(r.get("value"))
        except Exception:
            raise ValueError(f"invalid_value:rule_{i}")
        lb = int(r.get("lookback_days") or 30)
        if lb <= 0 or lb > MAX_LOOKBACK_DAYS:
            raise ValueError(
                f"lookback_out_of_range:1..{MAX_LOOKBACK_DAYS}")
        rule = {
            "signal_type":     sig,
            "comparator":      cmp_,
            "value":           val,
            "lookback_days":   lb,
        }
        # Specific-target signal types accept a `target_id` param.
        if sig in ("station_played_specific", "merchant_visited_specific"):
            tid = (r.get("target_id") or "").strip()
            if not tid:
                raise ValueError(f"target_id_required:rule_{i}:{sig}")
            rule["target_id"] = tid
        out.append(rule)
    return out


# ── Signal computation ───────────────────────────────────────────
def _cmp(count: float, comparator: str, value: float) -> bool:
    if comparator == ">=": return count >= value
    if comparator == ">":  return count >  value
    if comparator == "==": return count == value
    return False


async def _users_for_rule(db, rule: Dict[str, Any]) -> Set[str]:
    """Return the set of user_ids that satisfy `rule` in the lookback
    window.  Excludes users with retargeting_opt_out=True."""
    now = _now()
    cutoff = now - timedelta(days=int(rule["lookback_days"]))
    sig = rule["signal_type"]
    cmp_ = rule["comparator"]
    val = float(rule["value"])
    target = rule.get("target_id")

    match: List[Dict[str, Any]] = [{
        "$match": {"user_id": {"$exists": True, "$ne": None}},
    }]

    if sig == "listen_minutes_total":
        # Aggregate `takeover_hour_listener_sessions.cumulative_listen_seconds`
        # (the only listen collection with per-user seconds in current DB).
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "last_ping_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": {"$divide": [
                            {"$ifNull":
                             ["$cumulative_listen_seconds", 0]},
                            60]}}}},
        ]
        return await _collect_users(
            db.takeover_hour_listener_sessions, pipeline, cmp_, val)

    if sig == "podcast_completions":
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "completed": True,
                        "completed_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(
            db.podcast_progress, pipeline, cmp_, val)

    if sig == "trivia_games_played":
        # Use trivia_sessions (has user_id + started_at).
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "started_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(
            db.trivia_sessions, pipeline, cmp_, val)

    if sig == "coupons_saved":
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "saved_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(db.coupons, pipeline, cmp_, val)

    if sig == "marketplace_saves":
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "saved_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(
            db.marketplace_saves, pipeline, cmp_, val)

    if sig == "scan_to_pay_txns":
        # payment_transactions_v2 uses `customer_user_id`, not user_id.
        q_flow = {"$in": ["ad7_scan_to_pay", "ad7_split_share"]}
        pipeline = [
            {"$match": {"customer_user_id": {"$exists": True, "$ne": None},
                        "flow": q_flow,
                        "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$customer_user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(
            db.payment_transactions_v2, pipeline, cmp_, val)

    if sig == "location_matched_geofence":
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "served_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(
            db.location_boost_impressions, pipeline, cmp_, val)

    if sig == "takeover_listened":
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "last_ping_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(
            db.takeover_hour_listener_sessions, pipeline, cmp_, val)

    if sig == "predict_win_participated":
        users: Set[str] = set()
        for coll in (db.predict_win_participants,
                     db.merchant_predict_win_participants):
            pipeline = [
                {"$match": {"user_id": {"$exists": True, "$ne": None},
                            "created_at": {"$gte": cutoff}}},
                {"$group": {"_id": "$user_id",
                            "count": {"$sum": 1}}},
            ]
            users |= await _collect_users(coll, pipeline, cmp_, val)
        return users

    if sig == "station_played_specific":
        pipeline = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "station_id": target,
                        "listen_started_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        # takeover sessions carry station_id; else fall back to
        # listener_sessions if populated in future.
        users_a = await _collect_users(
            db.takeover_hour_listener_sessions, pipeline, cmp_, val)
        pipeline_b = [
            {"$match": {"user_id": {"$exists": True, "$ne": None},
                        "station_id": target,
                        "started_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$user_id",
                        "count": {"$sum": 1}}},
        ]
        users_b = await _collect_users(
            db.listener_sessions, pipeline_b, cmp_, val)
        return users_a | users_b

    if sig == "merchant_visited_specific":
        pipeline = [
            {"$match": {"customer_user_id":
                            {"$exists": True, "$ne": None},
                        "merchant_id": target,
                        "flow": {"$in":
                                    ["ad7_scan_to_pay", "ad7_split_share"]},
                        "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$customer_user_id",
                        "count": {"$sum": 1}}},
        ]
        return await _collect_users(
            db.payment_transactions_v2, pipeline, cmp_, val)

    return set()


async def _collect_users(coll, pipeline: List[Dict[str, Any]],
                         comparator: str, value: float) -> Set[str]:
    users: Set[str] = set()
    async for row in coll.aggregate(pipeline):
        if _cmp(float(row.get("count") or 0), comparator, value):
            uid = row.get("_id")
            if uid:
                users.add(uid)
    return users


async def _filter_opt_out(db, uids: Set[str]) -> Set[str]:
    if not uids:
        return uids
    async for u in db.users.find(
            {"user_id": {"$in": list(uids)},
             "retargeting_opt_out": True},
            {"user_id": 1}):
        uids.discard(u.get("user_id"))
    return uids


async def _compute_audience_members(db, audience: Dict[str, Any]
                                    ) -> Set[str]:
    per_rule: List[Set[str]] = []
    for rule in audience["rules"]:
        per_rule.append(await _users_for_rule(db, rule))
    if not per_rule:
        return set()
    users = per_rule[0]
    if audience["rule_logic"] == "AND":
        for s in per_rule[1:]:
            users &= s
    else:
        for s in per_rule[1:]:
            users |= s
    return await _filter_opt_out(db, users)


# ── Audience CRUD ────────────────────────────────────────────────
async def create_audience(db, *, advertiser_business_id: str,
                          body: Dict[str, Any]
                          ) -> Dict[str, Any]:
    name = (body.get("name") or "").strip()[:120]
    if not name:
        raise ValueError("name_required")
    rules = _validate_rules(body.get("rules") or [],
                            (body.get("rule_logic") or "AND").upper())
    now = _now()
    aud_id = _gen("rta")
    doc = {
        "_id":                       aud_id,
        "id":                        aud_id,
        "advertiser_business_id":    advertiser_business_id,
        "name":                      name,
        "description":
            (body.get("description") or "").strip()[:500] or None,
        "rules":                     rules,
        "rule_logic":                (body.get("rule_logic")
                                      or "AND").upper(),
        "estimated_size":            0,
        "last_computed_at":          None,
        "status":                    "draft",
        "created_at":                now,
        "updated_at":                now,
    }
    await db.retargeting_audiences.insert_one(doc)
    # Compute right away so the advertiser sees a real number.
    try:
        stats = await compute_audience(
            db, audience_id=aud_id,
            advertiser_business_id=advertiser_business_id)
        doc["estimated_size"]   = stats["estimated_size"]
        doc["last_computed_at"] = stats["last_computed_at"]
    except ValueError as e:
        # Bubble up validation errors (e.g. audience_too_large).
        await db.retargeting_audiences.delete_one({"id": aud_id})
        raise
    return _shape(doc)


async def update_audience(db, *, audience_id: str,
                          advertiser_business_id: str,
                          patch: Dict[str, Any]) -> Dict[str, Any]:
    a = await db.retargeting_audiences.find_one({"id": audience_id})
    if not a:
        raise ValueError("audience_not_found")
    if a["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if a["status"] != "draft":
        raise ValueError(f"audience_{a['status']}:rules_frozen")
    upd: Dict[str, Any] = {"updated_at": _now()}
    if "rules" in patch or "rule_logic" in patch:
        rules = _validate_rules(
            patch.get("rules") or a["rules"],
            (patch.get("rule_logic") or a["rule_logic"]).upper())
        upd["rules"] = rules
        upd["rule_logic"] = (patch.get("rule_logic")
                             or a["rule_logic"]).upper()
    if "name" in patch:
        upd["name"] = (patch["name"] or "").strip()[:120] or a["name"]
    if "description" in patch:
        upd["description"] = ((patch["description"] or "")
                              .strip()[:500] or None)
    await db.retargeting_audiences.update_one(
        {"id": audience_id}, {"$set": upd})
    return _shape(await db.retargeting_audiences.find_one(
        {"id": audience_id}))


async def compute_audience(db, *, audience_id: str,
                           advertiser_business_id: Optional[str] = None
                           ) -> Dict[str, Any]:
    a = await db.retargeting_audiences.find_one({"id": audience_id})
    if not a:
        raise ValueError("audience_not_found")
    if advertiser_business_id and \
            a["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    now = _now()
    users = await _compute_audience_members(db, a)
    size = len(users)
    if size > MAX_AUDIENCE_SIZE:
        raise ValueError(
            f"audience_too_large:size={size}:limit={MAX_AUDIENCE_SIZE}")
    # Nuke stale membership.
    await db.retargeting_audience_members.delete_many(
        {"audience_id": audience_id})
    # Fresh upsert.  Bulk insert for speed.
    if users:
        docs = [{
            "_id":              _gen("rtam"),
            "id":               _gen("rtam"),
            "audience_id":      audience_id,
            "user_id":          u,
            "added_at":         now,
            "last_signal_at":   now,
        } for u in list(users)[:MAX_AUDIENCE_SIZE]]
        try:
            await db.retargeting_audience_members.insert_many(
                docs, ordered=False)
        except Exception:
            pass
    await db.retargeting_audiences.update_one(
        {"id": audience_id},
        {"$set": {"estimated_size":   size,
                  "last_computed_at": now,
                  "updated_at":       now}})
    return {"audience_id":       audience_id,
            "estimated_size":    size,
            "last_computed_at":  _iso(now)}


async def activate_audience(db, *, audience_id: str,
                            advertiser_business_id: str
                            ) -> Dict[str, Any]:
    a = await db.retargeting_audiences.find_one({"id": audience_id})
    if not a:
        raise ValueError("audience_not_found")
    if a["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if a["status"] not in ("draft", "paused"):
        raise ValueError(f"audience_{a['status']}")
    # Force a fresh compute on activation.
    await compute_audience(
        db, audience_id=audience_id,
        advertiser_business_id=advertiser_business_id)
    await db.retargeting_audiences.update_one(
        {"id": audience_id},
        {"$set": {"status": "active", "updated_at": _now()}})
    return _shape(await db.retargeting_audiences.find_one(
        {"id": audience_id}))


async def archive_audience(db, *, audience_id: str,
                           advertiser_business_id: str
                           ) -> Dict[str, Any]:
    a = await db.retargeting_audiences.find_one({"id": audience_id})
    if not a:
        raise ValueError("audience_not_found")
    if a["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    await db.retargeting_audiences.update_one(
        {"id": audience_id},
        {"$set": {"status": "archived", "updated_at": _now()}})
    return _shape(await db.retargeting_audiences.find_one(
        {"id": audience_id}))


async def list_audiences(db, *,
                         advertiser_business_id: Optional[str] = None,
                         status: Optional[str] = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    rows = []
    async for a in db.retargeting_audiences.find(q).sort(
            "created_at", -1).limit(limit):
        rows.append(_shape(a))
    return rows


async def get_audience_detail(db, *, audience_id: str,
                              advertiser_business_id: Optional[str] = None
                              ) -> Dict[str, Any]:
    a = await db.retargeting_audiences.find_one({"id": audience_id})
    if not a:
        raise ValueError("audience_not_found")
    if advertiser_business_id and \
            a["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    shaped = _shape(a)
    # Sample 5 recent members with a hint at their signals (for
    # transparency — advertisers see counts, not ids).
    sample = []
    async for m in db.retargeting_audience_members.find(
            {"audience_id": audience_id}).sort("added_at", -1).limit(5):
        sample.append({
            "user_id_hint": (m.get("user_id") or "")[:6] + "***",
            "added_at":     _iso(m.get("added_at")),
        })
    shaped["sample_members"] = sample
    return shaped


# ── Campaign CRUD ────────────────────────────────────────────────
def _compute_costs(total_budget_cents: int) -> Dict[str, int]:
    budget = max(int(total_budget_cents), 100)
    fee = (budget * PLATFORM_FEE_PCT) // 100
    total = budget + fee
    return {"total_budget_cents": budget,
            "platform_fee_cents": fee,
            "grand_total_cents":  total,
            "admin_approval_required":
                total >= ADMIN_APPROVAL_THRESHOLD}


async def _verify_base_ad_ownership(db, *,
                                    advertiser_business_id: str,
                                    base_ad_type: str,
                                    base_ad_id: str) -> None:
    """Best-effort validation that base_ad_id belongs to the
    advertiser.  Different ad types live in different collections
    with different id fields."""
    if base_ad_type == "banner":
        doc = await db.banner_campaigns.find_one(
            {"banner_id": base_ad_id})
        adv_id = (doc or {}).get("advertiser_id")
    elif base_ad_type == "coupon":
        doc = await db.coupon_campaigns.find_one(
            {"id": base_ad_id})
        adv_id = (doc or {}).get("advertiser_business_id")
    elif base_ad_type == "notification":
        doc = await db.notification_campaigns.find_one(
            {"id": base_ad_id})
        adv_id = (doc or {}).get("advertiser_business_id")
    elif base_ad_type == "marketplace_slot":
        doc = await db.marketplace_featured_slots.find_one(
            {"id": base_ad_id})
        adv_id = (doc or {}).get("advertiser_business_id")
    elif base_ad_type == "sponsored_read":
        doc = await db.rj_sponsored_reads.find_one(
            {"id": base_ad_id})
        adv_id = (doc or {}).get("advertiser_business_id")
    elif base_ad_type == "takeover":
        doc = await db.takeover_hours.find_one({"id": base_ad_id})
        adv_id = (doc or {}).get("advertiser_business_id")
    elif base_ad_type == "location_boost":
        doc = await db.location_boost_campaigns.find_one(
            {"id": base_ad_id})
        adv_id = (doc or {}).get("advertiser_business_id")
    else:
        raise ValueError(f"unknown_base_ad_type:{base_ad_type}")
    if not doc:
        raise ValueError(
            f"base_ad_not_found:{base_ad_type}:{base_ad_id}")
    if adv_id and adv_id != advertiser_business_id:
        raise ValueError("base_ad_not_owned")


# ── Stripe ────────────────────────────────────────────────────────
async def _charge(*, amount_cents: int, campaign_id: str,
                  advertiser_business_id: str) -> Dict[str, Any]:
    import stripe as _stripe
    _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
    intent = _stripe.PaymentIntent.create(
        amount=int(amount_cents), currency="usd",
        payment_method_types=["card"],
        payment_method="pm_card_visa", confirm=True,
        metadata={
            "bigfm_flow":            "m6_retargeting_prepay",
            "bigfm_campaign_id":     campaign_id,
            "bigfm_advertiser_id":   advertiser_business_id,
        },
        idempotency_key=f"m6_rt_prepay_{campaign_id}")
    return {"payment_intent_id": intent.id,
            "amount_cents": int(amount_cents),
            "status": intent.status}


async def _refund(*, payment_intent_id: str,
                  refund_cents: int, campaign_id: str
                  ) -> Dict[str, Any]:
    import stripe as _stripe
    _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
    r = _stripe.Refund.create(
        payment_intent=payment_intent_id,
        amount=int(refund_cents),
        metadata={"bigfm_flow":  "m6_retargeting_refund",
                  "bigfm_campaign_id": campaign_id},
        idempotency_key=(
            f"m6_rt_refund_{campaign_id}_{secrets.token_hex(3)}"))
    return {"refund_id": r.id,
            "amount_cents": int(refund_cents),
            "status": r.status}


async def create_campaign(db, *, advertiser_business_id: str,
                          body: Dict[str, Any]) -> Dict[str, Any]:
    audience_id = (body.get("audience_id") or "").strip()
    if not audience_id:
        raise ValueError("audience_id_required")
    a = await db.retargeting_audiences.find_one({"id": audience_id})
    if not a:
        raise ValueError("audience_not_found")
    if a["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("audience_not_owned")
    if a["status"] != "active":
        raise ValueError(f"audience_{a['status']}:must_be_active")

    base_ad_type = (body.get("base_ad_type") or "").strip()
    base_ad_id   = (body.get("base_ad_id")   or "").strip()
    if base_ad_type not in BASE_AD_TYPES:
        raise ValueError(f"invalid_base_ad_type:{base_ad_type}")
    if not base_ad_id:
        raise ValueError("base_ad_id_required")
    await _verify_base_ad_ownership(
        db, advertiser_business_id=advertiser_business_id,
        base_ad_type=base_ad_type, base_ad_id=base_ad_id)

    mult = float(body.get("boost_multiplier") or 2.0)
    if mult < 1.0 or mult > 5.0:
        raise ValueError("boost_multiplier_out_of_range:1.0..5.0")
    cpi = int(body.get("cost_per_impression_cents") or 0)
    if cpi <= 0:
        raise ValueError("cost_per_impression_required_gt_0")

    plays_target = int(body.get("plays_target") or 0)
    total_budget = int(body.get("total_budget_cents") or 0)
    if total_budget < cpi:
        raise ValueError("total_budget_below_cpi")
    if plays_target <= 0:
        plays_target = max(1, total_budget // cpi)

    costs = _compute_costs(total_budget)
    now = _now()
    start = body.get("start_at") or now.isoformat()
    end   = body.get("end_at") or (
        now + timedelta(days=30)).isoformat()
    cid = _gen("rtc")
    doc = {
        "_id":                             cid,
        "id":                              cid,
        "advertiser_business_id":          advertiser_business_id,
        "audience_id":                     audience_id,
        "base_ad_type":                    base_ad_type,
        "base_ad_id":                      base_ad_id,
        "boost_multiplier":                mult,
        "cost_per_impression_cents":       cpi,
        "plays_target":                    plays_target,
        "plays_delivered":                 0,
        "total_budget_cents":              costs["total_budget_cents"],
        "platform_fee_cents":              costs["platform_fee_cents"],
        "grand_total_cents":               costs["grand_total_cents"],
        "remaining_budget_cents":          costs["total_budget_cents"],
        "admin_approval_required":         costs["admin_approval_required"],
        "stripe_payment_intent_id":        None,
        "stripe_prepayment_transaction_id": None,
        "stripe_refund_id":                None,
        "refunded_amount_cents":           0,
        "status":                          "draft",
        "start_at":                        start,
        "end_at":                          end,
        "created_at":                      now,
        "updated_at":                      now,
        "activated_at":                    None,
        "cancelled_at":                    None,
        "cancel_reason":                   None,
    }
    await db.retargeting_campaigns.insert_one(doc)
    return _shape(doc)


async def confirm_campaign_payment(db, *, campaign_id: str,
                                   advertiser_business_id: str
                                   ) -> Dict[str, Any]:
    c = await db.retargeting_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if c["status"] != "draft":
        raise ValueError(f"campaign_{c['status']}")
    charge = await _charge(
        amount_cents=int(c["grand_total_cents"]),
        campaign_id=campaign_id,
        advertiser_business_id=advertiser_business_id)
    tx_id = _gen("tx_rtc")
    now = _now()
    await db.payment_transactions_v2.insert_one({
        "_id":                     tx_id,
        "transaction_id":          tx_id,
        "stripe_payment_intent_id": charge["payment_intent_id"],
        "flow":                    "m6_retargeting_prepay",
        "event_source":            "retargeting_prepay",
        "advertiser_id":           advertiser_business_id,
        "bigfm_campaign_id":       campaign_id,
        "amount_cents":            int(c["grand_total_cents"]),
        "application_fee_cents":   int(c["platform_fee_cents"]),
        "merchant_net_cents":      0,
        "currency":                "usd",
        "status":                  "posted",
        "created_at":              now,
    })
    new_status = ("pending_admin"
                  if c.get("admin_approval_required")
                  else "active")
    upd = {
        "status":                          new_status,
        "stripe_payment_intent_id":        charge["payment_intent_id"],
        "stripe_prepayment_transaction_id": tx_id,
        "activated_at":                    now if new_status == "active"
                                                else None,
        "updated_at":                      now,
    }
    await db.retargeting_campaigns.update_one(
        {"id": campaign_id}, {"$set": upd})
    return {"campaign": _shape(
                await db.retargeting_campaigns.find_one(
                    {"id": campaign_id})),
            "charge": charge,
            "transaction_id": tx_id}


async def admin_decide_campaign(db, *, campaign_id: str,
                                admin_user_id: str, approve: bool,
                                admin_notes: Optional[str] = None
                                ) -> Dict[str, Any]:
    c = await db.retargeting_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["status"] != "pending_admin":
        raise ValueError(f"campaign_{c['status']}")
    now = _now()
    if approve:
        await db.retargeting_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"status":       "active",
                      "activated_at": now,
                      "updated_at":   now,
                      "admin_notes":  (admin_notes or "").strip() or None,
                      "decided_by_user_id": admin_user_id,
                      "decided_at":   now}})
    else:
        # Refund grand_total_cents (full).
        refund = None
        if c.get("stripe_payment_intent_id"):
            refund = await _refund(
                payment_intent_id=c["stripe_payment_intent_id"],
                refund_cents=int(c["grand_total_cents"]),
                campaign_id=campaign_id)
        await db.retargeting_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"status":                "cancelled",
                      "cancel_reason":         "admin_rejected",
                      "cancelled_at":          now,
                      "updated_at":            now,
                      "admin_notes":           (admin_notes or "")
                                                 .strip() or None,
                      "stripe_refund_id":      (refund or {}).get("refund_id"),
                      "refunded_amount_cents":
                            (refund or {}).get("amount_cents", 0),
                      "decided_by_user_id":    admin_user_id,
                      "decided_at":            now}})
    return _shape(await db.retargeting_campaigns.find_one(
        {"id": campaign_id}))


async def cancel_campaign(db, *, campaign_id: str,
                          advertiser_business_id: str,
                          reason: str = "advertiser_cancelled"
                          ) -> Dict[str, Any]:
    c = await db.retargeting_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if c["status"] not in ("draft", "active", "paused",
                           "pending_admin"):
        raise ValueError(f"campaign_{c['status']}")
    now = _now()
    # Refund unspent budget + unspent pro-rata fee.
    refund = None
    remaining_budget = int(c.get("remaining_budget_cents") or 0)
    total_budget = int(c.get("total_budget_cents") or 0)
    total_fee = int(c.get("platform_fee_cents") or 0)
    spent_ratio = ((total_budget - remaining_budget) / total_budget
                   if total_budget > 0 else 0.0)
    unspent_fee = int(total_fee * (1 - spent_ratio))
    refund_amt = remaining_budget + unspent_fee
    if refund_amt > 0 and c.get("stripe_payment_intent_id"):
        try:
            refund = await _refund(
                payment_intent_id=c["stripe_payment_intent_id"],
                refund_cents=refund_amt,
                campaign_id=campaign_id)
        except Exception as e:
            logger.warning("[m6_retargeting] refund failed: %s", e)
    await db.retargeting_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status":                "cancelled",
                  "cancel_reason":         reason,
                  "cancelled_at":          now,
                  "updated_at":            now,
                  "stripe_refund_id":      (refund or {}).get("refund_id"),
                  "refunded_amount_cents": (refund or {})
                                                .get("amount_cents", 0)}})
    return {"campaign": _shape(
                await db.retargeting_campaigns.find_one(
                    {"id": campaign_id})),
            "refund": refund}


async def list_campaigns(db, *,
                         advertiser_business_id: Optional[str] = None,
                         status: Optional[str] = None,
                         limit: int = 100
                         ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    rows = []
    async for c in db.retargeting_campaigns.find(q).sort(
            "created_at", -1).limit(limit):
        rows.append(_shape(c))
    return rows


async def get_campaign(db, *, campaign_id: str,
                       advertiser_business_id: Optional[str] = None
                       ) -> Dict[str, Any]:
    c = await db.retargeting_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if advertiser_business_id and \
            c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    return _shape(c)


# ── Selection hook (called by AD.11 banner + other auctions) ─────
async def select_candidates(db, *, base_ad_type: str,
                            user_id: Optional[str],
                            station_id: Optional[str] = None,
                            limit: int = 3
                            ) -> List[Dict[str, Any]]:
    """Returns up to `limit` matching retargeting campaigns for
    `user_id` and `base_ad_type`, sorted DESC by effective_bid_cents.

    Return shape mirrors `location_boost_service.select_candidates`
    so it can be plugged into the banner auction as a peer input:
        {campaign_id, boost_multiplier, effective_bid_cents,
         cost_per_impression_cents, audience_id, base_ad_id,
         advertiser_business_id, source: "retargeting"}
    Returns [] if user_id unknown / opted out / no membership.
    """
    if not user_id or base_ad_type not in BASE_AD_TYPES:
        return []
    # Opt-out check.
    u = await db.users.find_one(
        {"user_id": user_id, "retargeting_opt_out": True})
    if u:
        return []
    mem_aud_ids: List[str] = []
    async for m in db.retargeting_audience_members.find(
            {"user_id": user_id}, {"audience_id": 1}):
        mem_aud_ids.append(m["audience_id"])
    if not mem_aud_ids:
        return []
    # Active audiences owned by any advertiser (we only care about
    # membership) — narrow to `active` audiences only.
    active_aud_ids: List[str] = []
    async for a in db.retargeting_audiences.find(
            {"id": {"$in": mem_aud_ids},
             "status": "active"},
            {"id": 1}):
        active_aud_ids.append(a["id"])
    if not active_aud_ids:
        return []
    # Live campaigns of that base_ad_type using those audiences.
    now_iso = _now().isoformat()
    q: Dict[str, Any] = {
        "audience_id": {"$in": active_aud_ids},
        "base_ad_type": base_ad_type,
        "status":       "active",
        "$expr": {"$gte": ["$remaining_budget_cents",
                           "$cost_per_impression_cents"]},
    }
    picks = []
    async for c in db.retargeting_campaigns.find(q).limit(50):
        eff_bid = int(c["cost_per_impression_cents"]) * \
                  float(c.get("boost_multiplier") or 1.0)
        picks.append({
            "campaign_id":             c["id"],
            "advertiser_business_id":  c["advertiser_business_id"],
            "audience_id":             c["audience_id"],
            "base_ad_type":            c["base_ad_type"],
            "base_ad_id":              c["base_ad_id"],
            "boost_multiplier":        float(c["boost_multiplier"]),
            "cost_per_impression_cents":
                int(c["cost_per_impression_cents"]),
            "effective_bid_cents":     int(eff_bid),
            "source":                  "retargeting",
        })
    picks.sort(key=lambda x: x["effective_bid_cents"], reverse=True)
    return picks[:limit]


async def record_impression(db, *, campaign_id: str,
                            user_id: Optional[str],
                            station_id: Optional[str] = None
                            ) -> Dict[str, Any]:
    """Atomic decrement of budget + idempotent per (campaign, user,
    15-min bucket).  Returns {counted, remaining_budget_cents}."""
    if not user_id:
        return {"counted": False, "reason": "no_user_id"}
    now = _now()
    bucket = now.replace(minute=(now.minute // IMPRESSION_DEDUP_MIN)
                                    * IMPRESSION_DEDUP_MIN,
                          second=0, microsecond=0)
    imp_id = _gen("rtimp")
    doc = {
        "_id":            imp_id,
        "id":             imp_id,
        "campaign_id":    campaign_id,
        "user_id":        user_id,
        "station_id":     station_id,
        "dedup_bucket":   bucket,
        "served_at":      now,
    }
    try:
        await db.retargeting_impressions.insert_one(doc)
    except Exception:
        return {"counted":  False,
                "reason":   "dedup",
                "campaign_id": campaign_id}
    # Atomic budget decrement + delivered count.
    upd = await db.retargeting_campaigns.find_one_and_update(
        {"id": campaign_id,
         "status": "active",
         "$expr": {"$gte": ["$remaining_budget_cents",
                            "$cost_per_impression_cents"]}},
        {"$inc":       {"remaining_budget_cents":
                                -1,        # placeholder — see below
                        "plays_delivered": 1},
         "$set":       {"updated_at": now}},
        return_document=True)
    if not upd:
        return {"counted":  False,
                "reason":   "budget_gone",
                "campaign_id": campaign_id}
    # Real decrement: cost_per_impression, not -1.  We need a 2nd
    # update because mongo can't reference another field in $inc.
    cpi = int(upd.get("cost_per_impression_cents") or 0)
    if cpi > 1:
        await db.retargeting_campaigns.update_one(
            {"id": campaign_id},
            {"$inc": {"remaining_budget_cents": -(cpi - 1)}})
    # Snapshot remaining (fresh read).
    fresh = await db.retargeting_campaigns.find_one(
        {"id": campaign_id}, {"remaining_budget_cents": 1,
                              "cost_per_impression_cents": 1,
                              "plays_delivered": 1})
    remaining = int((fresh or {}).get("remaining_budget_cents", 0))
    # Auto-complete when budget exhausted.
    if remaining < int((fresh or {}).get("cost_per_impression_cents",
                                          cpi)):
        await db.retargeting_campaigns.update_one(
            {"id": campaign_id, "status": "active"},
            {"$set": {"status": "completed",
                      "completed_at": now,
                      "updated_at": now}})
    return {
        "counted":                    True,
        "campaign_id":                campaign_id,
        "cost_per_impression_cents":  cpi,
        "remaining_budget_cents":     remaining,
        "plays_delivered":
            int((fresh or {}).get("plays_delivered", 0)),
    }


# ── Sweeper ──────────────────────────────────────────────────────
async def sweep_stale_audiences(db, *,
                                max_age_hours: int = 24) -> Dict[str, Any]:
    """Recomputes every `active` audience whose last_computed_at is
    older than `max_age_hours` (default 24h)."""
    cutoff = _now() - timedelta(hours=max_age_hours)
    stale = []
    async for a in db.retargeting_audiences.find(
            {"status": "active",
             "$or": [{"last_computed_at": {"$lt": cutoff}},
                     {"last_computed_at": None}]}):
        stale.append(a["id"])
    refreshed = 0
    for aid in stale:
        try:
            await compute_audience(db, audience_id=aid)
            refreshed += 1
        except Exception as e:
            logger.warning(
                "[m6_retargeting] refresh %s failed: %s", aid, e)
    return {"stale_seen": len(stale), "refreshed": refreshed,
            "swept_at": _iso(_now())}


# ── Opt-out ──────────────────────────────────────────────────────
async def set_retargeting_opt_out(db, *, user_id: str,
                                  opt_out: bool) -> Dict[str, Any]:
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"retargeting_opt_out": bool(opt_out),
                  "retargeting_opt_out_updated_at": _now()}})
    # If opting out, purge existing membership rows.
    if opt_out:
        r = await db.retargeting_audience_members.delete_many(
            {"user_id": user_id})
        return {"user_id": user_id, "retargeting_opt_out": True,
                "purged_membership_rows": r.deleted_count}
    return {"user_id": user_id, "retargeting_opt_out": False}


async def get_retargeting_opt_out(db, *, user_id: str
                                  ) -> Dict[str, Any]:
    u = await db.users.find_one(
        {"user_id": user_id}, {"retargeting_opt_out": 1})
    return {"user_id": user_id,
            "retargeting_opt_out": bool((u or {}).get(
                "retargeting_opt_out"))}


__all__ = [
    "ensure_retargeting_indexes", "SIGNAL_TYPES", "BASE_AD_TYPES",
    "create_audience", "update_audience", "compute_audience",
    "activate_audience", "archive_audience", "list_audiences",
    "get_audience_detail",
    "create_campaign", "confirm_campaign_payment",
    "admin_decide_campaign", "cancel_campaign", "list_campaigns",
    "get_campaign",
    "select_candidates", "record_impression",
    "sweep_stale_audiences",
    "set_retargeting_opt_out", "get_retargeting_opt_out",
]
