"""Phase AD.11 — Banner Ad campaign service.

Advertisers create banner-ad campaigns targeting one or more of the 7
supported placement zones (see `config/ad_pricing_hints.py`).  Each
campaign has:
  - A per-zone creative image (uploaded via the routes layer).
  - A per-zone CPM (billed on impression via AD.2's split rails).
  - A total budget + optional daily cap + wallet-drain auto-pause.

The customer-facing `/api/banner/serve` endpoint runs a lightweight
priority auction (advertiser priority_score_boost DESC → per-zone CPM
DESC → random tiebreaker) and returns 1 banner per call.  Impressions
are fired on IntersectionObserver from the frontend and dedup'd per
(session, banner, zone, hour) so a scrolling user isn't billed twice
for the same slot.

Approval workflow lives in ADMOD.1 (`ad_type="banner"`).
"""
from __future__ import annotations

import logging
import random
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from config.ad_pricing_hints import (
    BANNER_ZONES, BANNER_ZONE_CPM_CENTS, BANNER_ZONE_DIMENSIONS,
)
from services.commission_service import calculate_platform_fee

logger = logging.getLogger("bigfm.ad11")


# ─── Helpers ────────────────────────────────────────────────────
def _now() -> datetime: return datetime.now(timezone.utc)
def _iso(dt) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else dt

def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ─── Indexes ────────────────────────────────────────────────────
async def ensure_ad11_indexes(db) -> None:
    try:
        await db.banner_campaigns.create_index("banner_id", unique=True)
        await db.banner_campaigns.create_index("advertiser_id")
        await db.banner_campaigns.create_index("status")
        await db.banner_campaigns.create_index([("status", 1),
                                                                                            ("start_time", 1),
                                                                                            ("end_time", 1)])
        await db.banner_campaigns.create_index("placement_zones")   # multikey
        await db.banner_impressions.create_index(
            [("banner_id", 1), ("zone", 1), ("created_at", -1)])
        await db.banner_impressions.create_index(
            [("session_id", 1), ("banner_id", 1), ("zone", 1),
              ("created_at", -1)])
        await db.banner_clicks.create_index(
            [("banner_id", 1), ("zone", 1), ("created_at", -1)])
    except Exception as e:
        logger.warning("[ad11] index setup failed: %s", e)


# ─── Validation ─────────────────────────────────────────────────
def _validate_payload(payload: Dict[str, Any]) -> None:
    if not payload.get("title") or len(payload["title"].strip()) < 3:
        raise ValueError("title_required")
    if not payload.get("target_url"):
        raise ValueError("target_url_required")
    zones = payload.get("placement_zones") or []
    if not zones:
        raise ValueError("placement_zones_required")
    for z in zones:
        if z not in BANNER_ZONES:
            raise ValueError(f"invalid_zone:{z}")
    per_cpm = payload.get("per_zone_cpm_cents") or {}
    for z, v in per_cpm.items():
        try:
            iv = int(v)
        except Exception:
            raise ValueError(f"invalid_cpm:{z}")
        if iv < 10 or iv > 100_000:
            raise ValueError(f"cpm_out_of_range:{z}")
    total_budget = int(payload.get("total_budget_cents") or 0)
    if total_budget < 100:
        raise ValueError("budget_too_low")


# ─── Draft / edit ───────────────────────────────────────────────
async def create_banner_campaign(db, *, advertiser_id: str,
                                                                          user_id: str,
                                                                          payload: Dict[str, Any]) -> Dict[str, Any]:
    _validate_payload(payload)
    now = _now()
    banner_id = _gen("bnr")
    zones = list(payload["placement_zones"])
    per_cpm = {z: int(payload.get("per_zone_cpm_cents", {}).get(
                                      z, BANNER_ZONE_CPM_CENTS.get(z, 300)))
                          for z in zones}
    doc = {
        "_id":                                banner_id,
        "banner_id":                        banner_id,
        "advertiser_id":                advertiser_id,
        "sponsoring_merchant_id":  payload.get("sponsoring_merchant_id"),
        "title":                              payload.get("title", "").strip()[:120],
        "description":                    payload.get("description", "")[:500],
        "target_url":                      payload["target_url"][:1000],
        "cta_text":                          (payload.get("cta_text") or "Learn more")[:64],
        # Placement + creative
        "placement_zones":              zones,
        "per_zone_cpm_cents":        per_cpm,
        "creative_urls":                  {},   # {zone: absolute url}
        "creative_dimensions":      {z: BANNER_ZONE_DIMENSIONS.get(z) for z in zones},
        # Budget
        "total_budget_cents":        int(payload.get("total_budget_cents") or 0),
        "spent_cents":                    0,
        "daily_cap_cents":              int(payload.get("daily_cap_cents") or 0),
        # Targeting
        "targeting":                        {
            "region":              payload.get("region"),
            "city":                  payload.get("city"),
            "language":          payload.get("language"),
            "category_tags":  payload.get("category_tags") or [],
            "min_user_tier": payload.get("min_user_tier"),
            "age_range":        payload.get("age_range"),
            "gender":              payload.get("gender"),
            "country_codes": [c.strip().upper() for c in (payload.get("country_codes") or []) if c],
        },
        # Timing
        "start_time":                      payload.get("start_time"),
        "end_time":                          payload.get("end_time"),
        # Lifecycle
        "status":                              "draft",
        "auto_paused_reason":        None,
        "auto_paused_at":              None,
        # Metrics
        "impressions_count":        0,
        "clicks_count":                  0,
        "ctr":                                  0.0,
        # Audit
        "submitted_at":                  None,
        "submitted_by":                  user_id,
        "reviewed_by":                    None,
        "reviewed_at":                    None,
        "review_reason":                None,
        "created_at":                      now,
        "updated_at":                      now,
    }
    await db.banner_campaigns.insert_one(doc)
    return _serialize(doc)


async def update_banner_campaign(db, *, banner_id: str,
                                                                          patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    doc = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not doc:
        return None
    if doc["status"] not in ("draft", "rejected", "requires_changes"):
        raise ValueError(f"cannot_edit_status:{doc['status']}")
    allowed = {"title", "description", "target_url", "cta_text",
                        "sponsoring_merchant_id", "total_budget_cents",
                        "daily_cap_cents", "start_time", "end_time"}
    set_doc: Dict[str, Any] = {"updated_at": _now()}
    for k, v in (patch or {}).items():
        if k in allowed:
            set_doc[k] = v
    if "per_zone_cpm_cents" in (patch or {}):
        merged = dict(doc.get("per_zone_cpm_cents", {}))
        for z, v in patch["per_zone_cpm_cents"].items():
            if z in doc.get("placement_zones", []):
                merged[z] = max(10, min(100_000, int(v)))
        set_doc["per_zone_cpm_cents"] = merged
    if "placement_zones" in (patch or {}):
        new_zones = [z for z in patch["placement_zones"] if z in BANNER_ZONES]
        if not new_zones:
            raise ValueError("placement_zones_required")
        set_doc["placement_zones"] = new_zones
        set_doc["creative_dimensions"] = {
            z: BANNER_ZONE_DIMENSIONS.get(z) for z in new_zones}
    if "targeting" in (patch or {}):
        merged_t = dict(doc.get("targeting") or {})
        merged_t.update({k: v for k, v in patch["targeting"].items() if v is not None})
        set_doc["targeting"] = merged_t
    await db.banner_campaigns.update_one({"banner_id": banner_id},
                                                                                              {"$set": set_doc})
    return _serialize(await db.banner_campaigns.find_one({"banner_id": banner_id}))


async def attach_creative(db, *, banner_id: str, zone: str,
                                                creative_url: str) -> Dict[str, Any]:
    if zone not in BANNER_ZONES:
        raise ValueError(f"invalid_zone:{zone}")
    doc = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not doc:
        raise ValueError("banner_not_found")
    if zone not in doc.get("placement_zones", []):
        raise ValueError("zone_not_in_placement")
    creative_urls = dict(doc.get("creative_urls") or {})
    creative_urls[zone] = creative_url
    await db.banner_campaigns.update_one(
        {"banner_id": banner_id},
        {"$set": {"creative_urls": creative_urls, "updated_at": _now()}})
    return _serialize(await db.banner_campaigns.find_one({"banner_id": banner_id}))


async def publish_banner_campaign(db, *, banner_id: str) -> Dict[str, Any]:
    doc = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not doc:
        raise ValueError("banner_not_found")
    # Must have creative for every selected zone.
    zones = doc.get("placement_zones") or []
    urls    = doc.get("creative_urls") or {}
    missing = [z for z in zones if not urls.get(z)]
    if missing:
        raise ValueError(f"creative_missing_for_zones:{','.join(missing)}")
    if not doc.get("total_budget_cents") or doc.get("total_budget_cents") < 100:
        raise ValueError("budget_too_low")
    await db.banner_campaigns.update_one(
        {"banner_id": banner_id},
        {"$set": {"status": "pending_admin",
                          "submitted_at": _now(),
                          "auto_paused_reason": None,
                          "auto_paused_at": None,
                          "updated_at": _now()}})
    return _serialize(await db.banner_campaigns.find_one({"banner_id": banner_id}))


async def list_banner_campaigns(db, *, advertiser_id: str) -> Dict[str, Any]:
    rows = await db.banner_campaigns.find(
        {"advertiser_id": advertiser_id}
    ).sort([("created_at", -1)]).to_list(500)
    items = [_serialize(r) for r in rows]
    # Roll up impressions + spend per campaign
    return {"items": items, "count": len(items)}


# ─── Auction ────────────────────────────────────────────────────
async def serve_banner(db, *, zone: str,
                                            user: Optional[Dict[str, Any]] = None,
                                            country: Optional[str] = None,
                                            language: Optional[str] = None,
                                            category_tags: Optional[List[str]] = None,
                                            session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if zone not in BANNER_ZONES:
        return None
    now = _now()

    # Phase J (M2) — location-boost prefer pass.  If the caller has a
    # located user + an active geofenced boost with base_ad_type=banner
    # matches, promote it above the standard auction winner IFF its
    # effective bid outranks the top zone CPM in the eligible set.  The
    # boost row itself is what we serve — its base_ad_id (if any) links
    # to a live banner campaign we can enrich with the creative URL.
    lb_hint: Optional[Dict[str, Any]] = None
    try:
        from services.location_boost_service import select_candidates as _lb_pick
        lb_matches = await _lb_pick(
            db, base_ad_type="banner",
            user_id=(user or {}).get("user_id"))
        if lb_matches:
            lb_hint = lb_matches[0]      # sorted DESC by effective_bid
    except Exception:
        lb_hint = None

    # Phase M (M6) — retargeting prefer pass.  Same shape as location
    # boost.  Compared against LB below; the higher effective_bid wins.
    rt_hint: Optional[Dict[str, Any]] = None
    try:
        from services.retargeting_service import select_candidates as _rt_pick
        rt_matches = await _rt_pick(
            db, base_ad_type="banner",
            user_id=(user or {}).get("user_id"))
        if rt_matches:
            rt_hint = rt_matches[0]
    except Exception:
        rt_hint = None

    q: Dict[str, Any] = {
        "status": "live",
        "placement_zones": zone,
        f"creative_urls.{zone}": {"$exists": True, "$ne": None},
    }
    # Optional country match (soft: no filter if not provided).
    if country:
        # Match banners that specify the country OR have no country filter.
        cc = country.upper()
        q["$and"] = [
            {"$or": [
                {"targeting.country_codes": {"$in": [cc]}},
                {"targeting.country_codes": {"$exists": False}},
                {"targeting.country_codes": {"$size": 0}},
            ]},
        ]
    # Fetch candidates (bounded — the auction is a small in-memory sort).
    candidates = await db.banner_campaigns.find(q).to_list(50)
    if not candidates:
        return None
    # Filter by budget remaining.
    eligible: List[Dict[str, Any]] = []
    for c in candidates:
        cpm = int((c.get("per_zone_cpm_cents") or {}).get(zone, 0))
        cost_per_impression = max(1, cpm // 1000)   # cents per single impr
        remaining = int(c.get("total_budget_cents", 0)) \
                              - int(c.get("spent_cents", 0))
        if remaining < cost_per_impression:
            continue
        # Additional soft filters (language / category).  Skip if the
        # candidate specifies a language and it doesn't match.
        tlang = (c.get("targeting") or {}).get("language")
        if tlang and language and str(tlang).lower() != str(language).lower():
            continue
        eligible.append(c)
    if not eligible:
        return None
    # Enrich with advertiser priority boost for the auction sort.
    adv_ids = list({c["advertiser_id"] for c in eligible})
    boost_by = {}
    async for a in db.advertisers_v2.find(
            {"advertiser_id": {"$in": adv_ids}},
            {"advertiser_id": 1, "priority_score_boost": 1}):
        boost_by[a["advertiser_id"]] = int(a.get("priority_score_boost") or 0)
    def _score(c):
        cpm = int((c.get("per_zone_cpm_cents") or {}).get(zone, 0))
        boost = boost_by.get(c["advertiser_id"], 0)
        return (boost, cpm, random.random())
    eligible.sort(key=_score, reverse=True)
    winner = eligible[0]

    # Phase J (M2) — apply the location-boost promotion.  If the boost's
    # effective_bid exceeds the winner's zone CPM, use the boost's
    # linked banner (base_ad_id) as the served creative.  If the boost
    # is unlinked (inline creative), skip the promotion here — inline
    # banner creatives flow via the FE candidates hook, not this path.
    # Phase M (M6) — retargeting is a peer bidder here.  We pick the
    # single higher-bidding overlay (LB vs RT) and, if its effective
    # bid beats the standard winner CPM, promote its base_ad_id.
    lb_promoted: Optional[Dict[str, Any]] = None
    rt_promoted: Optional[Dict[str, Any]] = None
    overlay_hint: Optional[Dict[str, Any]] = None
    overlay_source: Optional[str] = None
    lb_bid = int((lb_hint or {}).get("effective_bid_cents") or 0)
    rt_bid = int((rt_hint or {}).get("effective_bid_cents") or 0)
    if rt_bid >= lb_bid and rt_hint:
        overlay_hint, overlay_source = rt_hint, "retargeting"
    elif lb_hint:
        overlay_hint, overlay_source = lb_hint, "location_boost"
    if overlay_hint:
        winner_cpm_score = int((winner.get("per_zone_cpm_cents") or {}).get(zone, 0))
        boost_bid = int(overlay_hint.get("effective_bid_cents") or 0)
        if boost_bid > winner_cpm_score and overlay_hint.get("base_ad_id"):
            promoted = await db.banner_campaigns.find_one(
                {"banner_id": overlay_hint["base_ad_id"],
                  "status":            "live",
                  "placement_zones": zone,
                  f"creative_urls.{zone}": {"$exists": True, "$ne": None}})
            if promoted:
                if overlay_source == "retargeting":
                    rt_promoted = promoted
                else:
                    lb_promoted = promoted
                winner = promoted
    # Phase AD.3 bundle — log losers for the Auction Insights panel.
    # Fire-and-forget so the auction hot path isn't slowed.
    try:
        from services.auction_insights_service import (
            log_auction_result, fire_and_forget)
        winner_cpm = int((winner.get("per_zone_cpm_cents") or {}).get(zone, 0))
        losers = []
        for c in eligible[1:]:
            if c["advertiser_id"] == winner["advertiser_id"]:
                continue
            c_cpm = int((c.get("per_zone_cpm_cents") or {}).get(zone, 0))
            reason = ("priority_boost_lower"
                                if boost_by.get(c["advertiser_id"], 0)
                                    < boost_by.get(winner["advertiser_id"], 0)
                                else "higher_cpm")
            losers.append({
                "advertiser_id":  c["advertiser_id"],
                "campaign_id":      c.get("banner_id"),
                "bid_cents":          c_cpm,
                "reason":                reason,
            })
        if losers:
            fire_and_forget(log_auction_result(
                db, ad_type="banner", slot_id=zone,
                winner_advertiser_id=winner["advertiser_id"],
                winner_bid_cents=winner_cpm,
                losers=losers,
                user_context={"country": country, "language": language}))
    except Exception:
        pass
    return {
        "banner_id":    winner["banner_id"],
        "zone":              zone,
        "creative_url": (winner.get("creative_urls") or {}).get(zone),
        "target_url":  winner.get("target_url"),
        "cta_text":      winner.get("cta_text"),
        "cpm_cents":    int((winner.get("per_zone_cpm_cents") or {}).get(zone, 0)),
        "advertiser_id": winner["advertiser_id"],
        "impression_pixel_url": None,   # frontend fires POST /impression
        "served_at": now.isoformat(),
        # Phase J — surface the promoting boost so the FE fires the
        # location-boost impression endpoint in addition to the normal
        # banner impression.
        "location_boost": ({
            "campaign_id":        lb_hint["campaign_id"],
            "boost_multiplier":  lb_hint["boost_multiplier"],
            "effective_bid_cents": lb_hint["effective_bid_cents"],
        } if lb_promoted and lb_hint else None),
        # Phase M — surface the promoting retargeting campaign so the FE
        # fires the retargeting impression endpoint (atomic decrement +
        # 15-min per-user dedup).  Only present when RT out-bid LB and
        # the winner's base_ad_id had a live banner.
        "retargeting": ({
            "campaign_id":        rt_hint["campaign_id"],
            "audience_id":        rt_hint["audience_id"],
            "boost_multiplier":   rt_hint["boost_multiplier"],
            "effective_bid_cents": rt_hint["effective_bid_cents"],
        } if rt_promoted and rt_hint else None),
    }


# ─── Billing on impression ──────────────────────────────────────
async def _auto_pause(db, banner_id: str, reason: str) -> None:
    await db.banner_campaigns.update_one(
        {"banner_id": banner_id},
        {"$set": {"status": "paused",
                          "auto_paused_reason": reason,
                          "auto_paused_at": _now(),
                          "updated_at": _now()}})


async def record_impression(db, *, banner_id: str, zone: str,
                                                        user_id: Optional[str] = None,
                                                        session_id: Optional[str] = None,
                                                        commission_service_calc = None) -> Dict[str, Any]:
    """Bill advertiser wallet + record impression row + split-route.
    Dedup: same (session, banner, zone) within the last 5 minutes is a
    no-op (returns already_billed=True).
    Frequency cap (AD.11 · per user prompt): max 3 billed impressions
    per (session, zone) — regardless of banner — to prevent a single
    user repeatedly triggering billing on the same slot.  Reuses the
    AD.2 daily-cap pattern (counts prior rows in the session window)."""
    doc = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not doc:
        return {"ok": False, "reason": "banner_not_found"}
    if doc.get("status") != "live":
        return {"ok": False, "reason": f"banner_{doc.get('status')}"}
    if zone not in (doc.get("placement_zones") or []):
        return {"ok": False, "reason": "zone_not_active"}
    # Dedup
    dedup_key = session_id or user_id or "anon"
    since = _now() - timedelta(minutes=5)
    existing = await db.banner_impressions.find_one(
        {"session_id": dedup_key, "banner_id": banner_id,
          "zone": zone, "created_at": {"$gte": since}})
    if existing:
        return {"ok": True, "already_billed": True,
                      "impression_id": existing["impression_id"]}
    # AD.11 frequency cap — 3 billed impressions per (session, zone).
    SESSION_ZONE_CAP = 3
    zone_count = await db.banner_impressions.count_documents(
        {"session_id": dedup_key, "zone": zone})
    if zone_count >= SESSION_ZONE_CAP:
        return {"ok": True, "capped": True,
                      "reason": "session_zone_cap_reached",
                      "cap": SESSION_ZONE_CAP,
                      "current": zone_count}
    cpm_cents = int((doc.get("per_zone_cpm_cents") or {}).get(zone, 0))
    # Bill per single impression (CPM / 1000 cents, min 1).
    cost = max(1, cpm_cents // 1000)
    # Atomically debit advertiser wallet gated on sufficient budget.
    debit = await db.advertisers_v2.find_one_and_update(
        {"advertiser_id": doc["advertiser_id"],
          "budget_available_cents": {"$gte": cost}},
        {"$inc": {"budget_available_cents": -cost,
                          "budget_spent_cents":      cost}},
        return_document=True)
    if not debit:
        await _auto_pause(db, banner_id, "wallet_exhausted")
        return {"ok": False, "reason": "wallet_exhausted",
                      "banner_paused": True}
    # Compute split.  If a sponsoring merchant is set, apply the
    # coupon_save commission rule (30% platform / 70% merchant) — same
    # shape as AD.4.  Otherwise 100% platform revenue.
    fee_result = None
    merchant_id = doc.get("sponsoring_merchant_id")
    if merchant_id and callable(commission_service_calc):
        try:
            fee_result = await commission_service_calc(
                db, business_category="*", transaction_type="coupon_save",
                gross_cents=cost)
        except Exception as e:
            logger.warning("[ad11] fee calc failed: %s", e)
    if fee_result:
        app_fee = int(fee_result.get("platform_fee_cents") or 0)
        merch_net = int(fee_result.get("merchant_net_cents") or 0)
    else:
        app_fee = cost
        merch_net = 0
    impression_id = _gen("bimp")
    now = _now()
    await db.banner_impressions.insert_one({
        "_id":                            impression_id,
        "impression_id":            impression_id,
        "banner_id":                  banner_id,
        "zone":                            zone,
        "advertiser_id":          doc["advertiser_id"],
        "sponsoring_merchant_id": merchant_id,
        "user_id":                      user_id,
        "session_id":                dedup_key,
        "cpm_cents":                  cpm_cents,
        "cost_cents":                cost,
        "app_fee_cents":          app_fee,
        "merchant_net_cents":  merch_net,
        "created_at":                now,
    })
    # Ledger row (AD.2 shape) — plays with existing analytics.
    tx_id = _gen("tx_bnr")
    await db.payment_transactions_v2.insert_one({
        "_id":                              tx_id,
        "transaction_id":            tx_id,
        # Unique sentinel so we don't collide with the shared
        # `stripe_payment_intent_id_1` UNIQUE index on this collection
        # (AD.11 impressions aren't Stripe-backed, so we mint a
        # local sentinel keyed on the tx_id).
        "stripe_payment_intent_id": tx_id,
        "flow":                              "ad11_banner_impression",
        "event_source":                "banner_impression",
        "advertiser_id":              doc["advertiser_id"],
        "banner_id":                      banner_id,
        "zone":                              zone,
        "sponsoring_merchant_id": merchant_id,
        "customer_user_id":          user_id,
        "amount_cents":                cost,
        "application_fee_cents":  app_fee,
        "merchant_net_cents":      merch_net,
        "status":                            "posted",
        "created_at":                    now,
    })
    # Roll-up on the campaign
    await db.banner_campaigns.update_one(
        {"banner_id": banner_id},
        {"$inc": {"spent_cents": cost, "impressions_count": 1},
          "$set": {"updated_at": now}})
    # Belt-and-suspenders auto-pause when wallet dips below the next
    # impression cost.
    remaining = int(debit.get("budget_available_cents", 0))
    if remaining < cost:
        await _auto_pause(db, banner_id, "wallet_exhausted")
    total_budget = int(doc.get("total_budget_cents", 0))
    if int(doc.get("spent_cents", 0)) + cost >= total_budget:
        await _auto_pause(db, banner_id, "budget_exhausted")
    return {"ok": True, "impression_id": impression_id,
                  "cost_cents": cost, "app_fee_cents": app_fee,
                  "merchant_net_cents": merch_net}


async def record_click(db, *, banner_id: str, zone: str,
                                              user_id: Optional[str] = None,
                                              session_id: Optional[str] = None) -> Dict[str, Any]:
    doc = await db.banner_campaigns.find_one({"banner_id": banner_id})
    if not doc:
        return {"ok": False, "reason": "banner_not_found"}
    now = _now()
    click_id = _gen("bclk")
    await db.banner_clicks.insert_one({
        "_id":                    click_id,
        "click_id":            click_id,
        "banner_id":          banner_id,
        "zone":                  zone,
        "advertiser_id":  doc["advertiser_id"],
        "user_id":              user_id,
        "session_id":        session_id or user_id or "anon",
        "created_at":        now,
    })
    # Update CTR on the campaign
    impressions = int(doc.get("impressions_count", 0))
    clicks            = int(doc.get("clicks_count", 0)) + 1
    ctr = round((clicks / impressions * 100), 3) if impressions else 0.0
    await db.banner_campaigns.update_one(
        {"banner_id": banner_id},
        {"$inc": {"clicks_count": 1}, "$set": {"ctr": ctr, "updated_at": now}})
    return {"ok": True, "click_id": click_id}


# ─── Analytics ──────────────────────────────────────────────────
async def platform_analytics(db, *, days: int = 30) -> Dict[str, Any]:
    since = _now() - timedelta(days=days)
    by_zone = await db.banner_impressions.aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$zone",
                              "impressions": {"$sum": 1},
                              "spend":        {"$sum": "$cost_cents"}}},
        {"$sort": {"spend": -1}},
    ]).to_list(20)
    by_day = await db.banner_impressions.aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d",
                                                                    "date": "$created_at"}},
            "impressions": {"$sum": 1},
            "spend":        {"$sum": "$cost_cents"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(60)
    totals = await db.banner_impressions.aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": None,
                              "impressions": {"$sum": 1},
                              "spend":        {"$sum": "$cost_cents"}}},
    ]).to_list(1)
    clicks_total = await db.banner_clicks.count_documents(
        {"created_at": {"$gte": since}})
    t = totals[0] if totals else {"impressions": 0, "spend": 0}
    ctr = round((clicks_total / t["impressions"] * 100), 2) if t["impressions"] else 0
    return {
        "window_days": days,
        "totals": {"impressions": t["impressions"], "spend_cents": t["spend"],
                          "clicks": clicks_total, "ctr_pct": ctr},
        "by_zone": by_zone,
        "by_day":  by_day,
    }


async def advertiser_rollup(db, *, advertiser_id: str,
                                                            days: int = 30) -> Dict[str, Any]:
    """Per-campaign roll-ups for the advertiser dashboard."""
    since = _now() - timedelta(days=days)
    per_c = await db.banner_impressions.aggregate([
        {"$match": {"advertiser_id": advertiser_id,
                              "created_at": {"$gte": since}}},
        {"$group": {"_id": {"banner_id": "$banner_id", "zone": "$zone"},
                              "impressions": {"$sum": 1},
                              "spend":        {"$sum": "$cost_cents"}}},
    ]).to_list(500)
    return {"window_days": days, "per_campaign_zone": per_c}


__all__ = [
    "ensure_ad11_indexes",
    "create_banner_campaign", "update_banner_campaign", "attach_creative",
    "publish_banner_campaign", "list_banner_campaigns",
    "serve_banner", "record_impression", "record_click",
    "platform_analytics", "advertiser_rollup",
]
