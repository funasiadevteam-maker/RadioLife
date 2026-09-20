"""Phase 18a — Advertiser dashboard backend service layer.

Collections:
  advertisers, advertiser_staff, ad_campaigns, ad_creatives, ad_serves

Direct-sold serving hook: `pick_ad_for_user(...)` is the entry-point the
queue builder calls when reserving the inter-song ad slot.  18a uses a
simple 1-per-10-min hard cap; 18c will replace with smart pacing.
"""
from __future__ import annotations
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

logger = logging.getLogger("bigfm.advertiser")

CPM_DEFAULT_USD     = 5.0    # bid per 1 000 impressions until pacing arrives
FREQUENCY_CAP_MIN  = 10
AUTO_APPROVE_BUDGET_USD = 100.0


def _now(): return datetime.now(timezone.utc)
def _gen(prefix: str) -> str: return f"{prefix}_{secrets.token_hex(6)}"


# ─── Membership ─────────────────────────────────────────────────────
async def get_membership(db, *, advertiser_id: str, user_id: str) -> Optional[dict]:
    return await db.advertiser_staff.find_one(
        {"advertiser_id": advertiser_id, "user_id": user_id})


async def assert_membership(db, *, advertiser_id: str, user_id: str,
                                          min_role: str = "analyst") -> dict:
    """Raises PermissionError unless user has role >= min_role."""
    rank = {"analyst": 1, "manager": 2, "owner": 3}
    m = await get_membership(db, advertiser_id=advertiser_id, user_id=user_id)
    if not m:
        raise PermissionError("not-a-staff-member")
    if rank.get(m.get("role"), 0) < rank.get(min_role, 1):
        raise PermissionError(f"role-too-low (need {min_role}+)")
    return m


# ─── Onboarding ─────────────────────────────────────────────────────
async def onboard_advertiser(db, *, owner_user_id: str, name: str,
                                              contact_email: str, contact_phone: Optional[str],
                                              market: str,
                                              plan_tier: str = "self_serve") -> dict:
    aid = _gen("adv")
    stripe_customer_id = await _create_stripe_customer(name=name, email=contact_email)
    doc = {
        "id":                              aid,
        "name":                          name,
        "contact_email":              contact_email,
        "contact_phone":             contact_phone,
        "billing_user_id":            owner_user_id,
        "stripe_customer_id":      stripe_customer_id,
        "account_balance_usd":  0.0,
        "plan_tier":                    plan_tier,
        "market":                        market,
        "status":                         "active",
        "created_at":                  _now(),
    }
    await db.advertisers.insert_one(doc)
    doc.pop("_id", None)
    await db.advertiser_staff.insert_one({
        "id":               _gen("astaff"),
        "advertiser_id": aid,
        "user_id":      owner_user_id,
        "role":            "owner",
        "created_at":  _now(),
    })
    return doc


async def _create_stripe_customer(*, name: str, email: str) -> Optional[str]:
    """Best-effort Stripe customer creation; returns None on failure so we
    don't block onboarding when running offline or with a misconfigured key."""
    try:
        import stripe
        stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                                  or os.environ.get("STRIPE_API_KEY"))
        if not stripe.api_key:
            return None
        c = stripe.Customer.create(name=name, email=email,
                                                    metadata={"source": "bigfm-advertiser-18a"})
        return c.id
    except Exception as e:
        logger.warning("[advertiser] stripe customer skip: %s", e)
        return None


# ─── Top-up Checkout ─────────────────────────────────────────────────
async def create_topup_checkout(db, *, advertiser_id: str,
                                                        amount_usd: float,
                                                        success_url: str,
                                                        cancel_url:   str) -> dict:
    if amount_usd <= 0:
        raise ValueError("amount must be > 0")
    adv = await db.advertisers.find_one({"id": advertiser_id})
    if not adv:
        raise LookupError("advertiser not found")
    stripe_key = (os.environ.get("STRIPE_SECRET_KEY")
                          or os.environ.get("STRIPE_API_KEY"))
    if not stripe_key:
        # No Stripe key configured → preview-only mock fallback that credits
        # the advertiser wallet immediately so the dashboard demo still works.
        logger.warning("[advertiser] topup: STRIPE key missing — mocking top-up")
        await db.advertisers.update_one(
            {"id": advertiser_id},
            {"$inc": {"account_balance_usd": float(amount_usd)}})
        return {"url": f"{success_url}?mocked_topup={amount_usd}",
                  "session_id": f"cs_mock_{secrets.token_hex(6)}",
                  "mocked": True}
    # Live (test-mode) Stripe Checkout — surface real Checkout URL.
    import stripe
    stripe.api_key = stripe_key
    # Avoid sending a stale/foreign customer ID (e.g. seeded "cus_test_demo_karak")
    # which Stripe will reject as "No such customer".
    cust_id = adv.get("stripe_customer_id")
    if cust_id and not str(cust_id).startswith("cus_"):
        cust_id = None
    if cust_id and "demo" in str(cust_id).lower():
        cust_id = None
    cs = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        **({"customer": cust_id} if cust_id else
              {"customer_email": adv.get("contact_email")}),
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": int(amount_usd * 100),
                "product_data": {"name": f"FUUSIC ad spend top-up ${amount_usd:.2f}"},
            },
            "quantity": 1,
        }],
        metadata={"advertiser_id": advertiser_id,
                      "topup_amount_usd": str(amount_usd)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return {"url": cs.url, "session_id": cs.id, "mocked": False}


# ─── Campaigns ───────────────────────────────────────────────────────
def _validate_campaign(body: dict) -> None:
    if (body.get("budget_total_usd") or 0) <= 0:
        raise ValueError("budget_total_usd must be > 0")
    s = body.get("start_date"); e = body.get("end_date")
    if s and e and e <= s:
        raise ValueError("end_date must be > start_date")
    # Phase 18b — takeover validation.
    tc = body.get("takeover_config") or {}
    if tc.get("enabled"):
        if (body.get("budget_total_usd") or 0) < 1000:
            raise ValueError("Channel takeover requires budget_total_usd >= $1000")
        if not tc.get("channel_slug"):
            raise ValueError("takeover_config.channel_slug required")
        ws, we = tc.get("window_start"), tc.get("window_end")
        if not (ws and we):
            raise ValueError("takeover_config.window_start and window_end required")
        try:
            from datetime import datetime as _dt
            wsd = _dt.fromisoformat(ws.replace("Z", "+00:00"))
            wed = _dt.fromisoformat(we.replace("Z", "+00:00"))
        except Exception:
            raise ValueError("takeover window timestamps must be ISO format")
        if (wed - wsd).total_seconds() > 2 * 3600 + 60:
            raise ValueError("takeover window can't exceed 2 hours")
        if (wed - wsd).total_seconds() <= 0:
            raise ValueError("takeover window_end must be > window_start")
        if tc.get("windows_per_day") and tc["windows_per_day"] > 3:
            raise ValueError("max 3 takeover windows per day")


async def create_campaign(db, *, advertiser_id: str, body: dict) -> dict:
    _validate_campaign(body)
    cid = _gen("camp")
    doc = {
        "id":                  cid,
        "advertiser_id":  advertiser_id,
        "name":              body.get("name") or "Untitled campaign",
        "objective":        body.get("objective") or "awareness",
        "budget_total_usd": float(body.get("budget_total_usd") or 0),
        "budget_daily_usd": (float(body["budget_daily_usd"])
                                          if body.get("budget_daily_usd") else None),
        "spend_usd":      0.0,
        "start_date":       body.get("start_date"),
        "end_date":         body.get("end_date"),
        "targeting":         body.get("targeting") or {},
        "creative_ids":   list(body.get("creative_ids") or []),
        "takeover_config": body.get("takeover_config") or None,
        # Phase 18d — per-campaign attribution window cap (hours).
        # Used by the funnel reader to ignore stale serve_ids.
        "attribution_window_hours": int(body.get("attribution_window_hours") or 24),
        "status":             "draft",
        "created_at":      _now(),
        "updated_at":     _now(),
    }
    await db.ad_campaigns.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def submit_campaign(db, *, advertiser_id: str, campaign_id: str) -> dict:
    camp = await db.ad_campaigns.find_one({"id": campaign_id,
                                                                          "advertiser_id": advertiser_id})
    if not camp:
        raise LookupError("campaign not found")
    if not camp.get("creative_ids"):
        raise ValueError("campaign needs at least one creative attached")
    creatives = await db.ad_creatives.find(
        {"id": {"$in": camp["creative_ids"]}}).to_list(20)
    # Block submit if any attached creative was rejected by safety.
    if any(c.get("status") == "rejected" for c in creatives):
        raise PermissionError({"code": "creative_rejected",
                                          "message": "One or more creatives were rejected by safety review. "
                                                            "Edit or replace before submitting."})
    all_approved = all(
        (c.get("brand_safety_check") or {}).get("verdict") == "approved"
        for c in creatives)
    new_status = "pending_review"
    note = "Submitted for admin review."
    # Phase 18b — takeovers ALWAYS need admin approval (inventory exclusivity).
    is_takeover = bool((camp.get("takeover_config") or {}).get("enabled"))
    if is_takeover:
        new_status = "pending_review"
        note = "Channel takeover — admin approval required regardless of safety."
    elif (camp["budget_total_usd"] <= AUTO_APPROVE_BUDGET_USD) and all_approved:
        new_status = "active"
        note = "Auto-approved: budget ≤ $100 and all creatives passed safety."
    await db.ad_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status":      new_status,
                    "submitted_at": _now(),
                    "updated_at":  _now()}})
    return {"status": new_status, "note": note}


async def set_status(db, *, advertiser_id: str, campaign_id: str,
                              status: str) -> dict:
    await db.ad_campaigns.update_one(
        {"id": campaign_id, "advertiser_id": advertiser_id},
        {"$set": {"status": status, "updated_at": _now()}})
    return {"ok": True, "status": status}


async def admin_approve(db, *, campaign_id: str, admin_user_id: str) -> dict:
    await db.ad_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status":               "active",
                    "approved_at":          _now(),
                    "approved_by_user_id": admin_user_id,
                    "updated_at":            _now()}})
    return {"ok": True, "status": "active"}


async def admin_reject(db, *, campaign_id: str, admin_user_id: str,
                                  reason: str) -> dict:
    await db.ad_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status":               "rejected",
                    "rejected_reason":     reason,
                    "approved_by_user_id": admin_user_id,
                    "updated_at":            _now()}})
    return {"ok": True, "status": "rejected"}


# ─── Direct-sold serving hook ───────────────────────────────────────
async def pick_ad_for_user(db, *, user_id: str, channel_slug: str,
                                          market: str,
                                          now: Optional[datetime] = None) -> Optional[dict]:
    """Returns the ad to play (creative + campaign) or None.

    Hard cap: 1 ad per 10 min per user (Phase 18a). Caller is responsible
    for wiring this between songs in the existing queue builder.
    """
    now = now or _now()
    # 1️⃣  Frequency cap — Phase 18c multi-dimension.
    from services.freq_caps import check_caps, record_serve_event
    # 1.5️⃣  Phase 18b — exclusive takeover precedence.
    #        If any active campaign owns this channel in `now`, only that one
    #        can serve.  Non-exclusive takeovers still compete in the auction.
    takeover_camp = await _find_exclusive_takeover(db, channel_slug=channel_slug,
                                                                              market=market, now=now)
    if takeover_camp:
        return await _serve_campaign(db, camp=takeover_camp, user_id=user_id,
                                                    channel_slug=channel_slug, market=market,
                                                    now=now, was_takeover=True)
    # 2️⃣  Eligible campaigns.
    pipe_q = {
        "status": "active",
        "_is_pacing_fixture": {"$ne": True},   # exclude Phase 18c demo fixtures
        "$or":     [{"start_date": None},
                       {"start_date": {"$lte": now.isoformat()}}],
    }
    camps = await db.ad_campaigns.find(pipe_q).to_list(100)
    eligible = []
    for c in camps:
        # Targeting: market filter (falls back to advertiser.market when unset).
        t = c.get("targeting") or {}
        adv_pre = await db.advertisers.find_one({"id": c["advertiser_id"]},
                                                                          {"market": 1, "_id": 0})
        effective_market = t.get("market") or (adv_pre or {}).get("market")
        if effective_market and effective_market != market:
            continue
        if t.get("channel_slugs"):
            if channel_slug not in t["channel_slugs"]:
                continue
        if t.get("time_of_day"):
            hr = now.hour
            tod = _hour_bucket_name(hr)
            if tod not in t["time_of_day"]:
                continue
        # Advertiser balance check (use CPM/1000 as a per-impression cost).
        adv = await db.advertisers.find_one({"id": c["advertiser_id"]})
        if not adv:    continue
        cost = CPM_DEFAULT_USD / 1000.0
        if adv.get("account_balance_usd", 0.0) < cost:
            continue
        eligible.append((c, adv, cost))

    # Phase 18d — Programmatic waterfall fallback.  Used both when nothing
    # is eligible AND when everyone direct-sold is freq-capped below.
    async def _programmatic_fallback(reason: str):
        try:
            from services import gam_adapter
            env = await gam_adapter.request_ad(
                channel_slug=channel_slug, user_id=user_id, market=market)
            if env:
                source = env.get("source") or "gam_mock"
                return {"serve":   {"id": _gen("serve_gam"),
                                              "user_id": user_id, "channel_slug": channel_slug,
                                              "market": market, "served_at": now,
                                              "source": source,
                                              "advertiser_id": None,
                                              "campaign_id":   None,
                                              "cost_usd":         env.get("revenue_usd"),
                                              "was_takeover": False,
                                              "_freq_cap_reason": reason},
                           "campaign": {"id": None, "name": "GAM backfill",
                                                "was_takeover": False,
                                                "advertiser_id": None,
                                                "source": source},
                           "creative":  {"id": env.get("creative_id"),
                                                "audio_url": env.get("audio_url"),
                                                "vast_xml":   env.get("vast_xml")}}
        except Exception as e:
            logger.warning("[adv] GAM waterfall fallthrough: %s", e)
        try:
            from services import openrtb_adapter
            ortb = await openrtb_adapter.request_ad(
                user_id=user_id, channel_slug=channel_slug, market=market)
            if ortb:
                source = ortb.get("source") or "openrtb_mock"
                return {"serve":   {"id": _gen("serve_ortb"),
                                              "user_id": user_id, "channel_slug": channel_slug,
                                              "market": market, "served_at": now,
                                              "source": source,
                                              "advertiser_id": None,
                                              "campaign_id":   None,
                                              "cost_usd":         ortb.get("revenue_usd"),
                                              "was_takeover": False,
                                              "_freq_cap_reason": reason},
                           "campaign": {"id": None, "name": "OpenRTB backfill",
                                                "was_takeover": False,
                                                "advertiser_id": None,
                                                "source": source},
                           "creative":  {"id": ortb.get("creative_id"),
                                                "audio_url": ortb.get("creative_url"),
                                                "vast_xml":   ortb.get("vast_xml")}}
        except Exception as e:
            logger.warning("[adv] OpenRTB waterfall fallthrough: %s", e)
        return None

    if not eligible:
        return await _programmatic_fallback("no_direct_sold")
    # Phase 18c — apply pacing weight to the bid before sorting.
    from services.pacing import pick_weight
    def _score(item):
        c, _adv, _cost = item
        return float(c["budget_total_usd"]) * pick_weight(c, now)
    eligible.sort(key=lambda x: -_score(x))
    # Phase 18c — apply combined freq cap (skip cap-blocked campaigns and
    # short-circuit the auction on the first eligible+uncapped one).
    last_reason = None
    for camp, adv, cost in eligible:
        cap = await check_caps(db, user_id=user_id, campaign=camp,
                                              channel_slug=channel_slug, now=now)
        if cap["blocked"]:
            last_reason = cap["reason"]
            continue
        return await _serve_campaign(db, camp=camp, user_id=user_id,
                                                      channel_slug=channel_slug, market=market,
                                                      now=now, was_takeover=False,
                                                      _adv=adv, _cost=cost,
                                                      _freq_cap_reason=None)
    # Phase 18d — programmatic waterfall fallback when no direct-sold
    # campaign was eligible/uncapped. Helper is defined above.
    return await _programmatic_fallback(last_reason)


async def _find_exclusive_takeover(db, *, channel_slug: str, market: str,
                                                                now) -> Optional[dict]:
    """Return the campaign that owns this channel right now (exclusive
    takeover), or None.  An exclusive takeover blocks all other ads on the
    channel during its window."""
    iso_now = now.isoformat()
    cur = db.ad_campaigns.find({
        "status": "active",
        "takeover_config.enabled":     True,
        "takeover_config.exclusive":  True,
        "takeover_config.channel_slug": channel_slug,
    })
    async for c in cur:
        tc = c.get("takeover_config") or {}
        ws, we = tc.get("window_start"), tc.get("window_end")
        if ws and we and ws <= iso_now <= we:
            # Market check: honor targeting.market, else fall back to
            # advertiser.market (same semantics as the CPM auction).
            t = c.get("targeting") or {}
            effective = t.get("market")
            if not effective:
                adv = await db.advertisers.find_one(
                    {"id": c["advertiser_id"]}, {"market": 1, "_id": 0})
                effective = (adv or {}).get("market")
            if effective and effective != market:
                continue
            return c
    return None


async def _serve_campaign(db, *, camp: dict, user_id: str, channel_slug: str,
                                          market: str, now,
                                          was_takeover: bool = False,
                                          _adv: Optional[dict] = None,
                                          _cost: Optional[float] = None,
                                          _freq_cap_reason: Optional[str] = None) -> Optional[dict]:
    """Pick a creative, log the ad_serve, and deduct balance.  Returns the
    serve payload or None when no playable creative is available."""
    if _adv is None:
        _adv = await db.advertisers.find_one({"id": camp["advertiser_id"]})
        if not _adv:
            return None
    cost = float(_cost if _cost is not None else CPM_DEFAULT_USD / 1000.0)
    if _adv.get("account_balance_usd", 0.0) < cost and not was_takeover:
        return None
    if not camp.get("creative_ids"):
        return None
    creative = await db.ad_creatives.find_one(
        {"id":  {"$in": camp["creative_ids"]}})
    if not creative:
        return None
    served = {
        "id":                  _gen("serve"),
        "campaign_id":   camp["id"],
        "creative_id":     creative["id"],
        "advertiser_id": _adv["id"],
        "user_id":          user_id,
        "channel_slug":  channel_slug,
        "market":             market,
        "served_at":      now,
        "completed":     False,
        "click_through": False,
        "coupon_saved": False,
        "redeemed":      False,
        "cost_usd":       cost,
        "was_takeover": was_takeover,
    }
    await db.ad_serves.insert_one(served)
    served.pop("_id", None)
    # Phase 18c — mirror into ad_serve_events for freq-cap counting.
    try:
        from services.freq_caps import record_serve_event
        await record_serve_event(db, serve_doc=served)
    except Exception as e:
        logger.warning("[adv] record_serve_event failed: %s", e)
    await db.advertisers.update_one(
        {"id": _adv["id"]},
        {"$inc": {"account_balance_usd": -cost}})
    await db.ad_campaigns.update_one(
        {"id": camp["id"]},
        {"$inc": {"spend_usd": cost}})
    return {"serve": served,
              "campaign": {"id": camp["id"], "name": camp.get("name"),
                                "was_takeover": was_takeover},
              "creative": {k: creative.get(k) for k in
                              ["id", "title", "audio_url", "image_url",
                                "click_url", "duration_sec", "transcript"]}}



def _hour_bucket_name(h: int) -> str:
    if 6  <= h < 10: return "morning"
    if 10 <= h < 12: return "late_morning"
    if 12 <= h < 14: return "lunch"
    if 14 <= h < 17: return "afternoon"
    if 17 <= h < 20: return "evening"
    return "night"
