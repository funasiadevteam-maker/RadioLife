"""Phase 4 — Ad decisioning engine.

Picks the best ad to insert into the next segment given user/session/context.

Priority order:
1. Direct-sold campaigns (highest priority — match targeting + frequency cap, score by bid*relevance)
2. Sponsored games — Phase 4 stub (returns None)
3. GAM backfill — Phase 4 scaffold (returns None until service account uploaded)
4. OpenRTB programmatic backfill — Phase 4 scaffold (returns None, see /api/openrtb/bid)
5. House promo — Phase 4 stub (returns None for now; Phase 5+ wires this)

Public:
- select_ad(db, user, session, segment_context) → ({decision_path, creative_doc, campaign_doc, action_cards}) | None
- log_ad_pod(db, *, pod_data) → ad_pod _id
- log_ad_impression(db, *, ...) → ad_impression _id
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("bigfm.ads.decisioning")

# Free-listener default ad load (segments between ads). Premium = 0 (no ads).
AD_LOAD_FREE_PROBABILITY = 0.65   # ~65% of free-user segments fire an ad post-roll


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Frequency cap check ----------
async def _is_capped(db, *, user_id: str, campaign: dict) -> bool:
    """True if this campaign has exceeded its frequency cap for the user."""
    cap = campaign.get("frequency_cap") or {}
    now = _now()
    pairs = [
        ("per_hour", timedelta(hours=1)),
        ("per_day", timedelta(days=1)),
        ("per_week", timedelta(days=7)),
        ("per_user_lifetime", None),
    ]
    for key, window in pairs:
        limit = cap.get(key)
        if not limit:
            continue
        q: dict = {"user_id": user_id, "campaign_id": campaign["campaign_id"]}
        if window:
            q["served_at"] = {"$gte": now - window}
        count = await db.ad_impressions.count_documents(q)
        if count >= int(limit):
            return True
    # Also block re-fires within 30 minutes regardless of cap
    recent = await db.ad_impressions.count_documents({
        "user_id": user_id, "campaign_id": campaign["campaign_id"],
        "served_at": {"$gte": now - timedelta(minutes=30)},
    })
    if recent >= 1:
        return True
    return False


# ---------- Targeting match ----------
def _targeting_score(campaign: dict, user: dict, session: dict, ctx: dict) -> float:
    """Return 0..1 relevance score, or 0 if a hard-targeting constraint fails."""
    t = campaign.get("targeting_json") or {}
    user_market = (user.get("market") or "dubai").lower()
    user_prefs = (user.get("preference_vector") or {})
    user_languages = [l.lower() for l in user_prefs.get("languages", [])]
    user_genres = [g.lower() for g in user_prefs.get("genres", [])]
    user_moods = [m.lower() for m in user_prefs.get("moods", [])]
    user_premium = bool(user.get("is_premium"))

    # Market must match (hard filter)
    cmp_markets = [m.lower() for m in (t.get("markets") or [])]
    if cmp_markets and user_market not in cmp_markets:
        return 0.0

    # Premium / free constraints
    if t.get("premium_only") and not user_premium:
        return 0.0
    if t.get("free_only") and user_premium:
        return 0.0

    # Daypart match (soft)
    cmp_dayparts = [d.lower() for d in (t.get("dayparts") or [])]
    current_daypart = (ctx.get("daypart") or "").lower()
    daypart_match = (not cmp_dayparts) or (current_daypart in cmp_dayparts)
    if not daypart_match:
        return 0.0  # we honor daypart strictly — campaigns commit to specific slots

    score = 1.0
    # Language overlap bonus
    cmp_langs = [l.lower() for l in (t.get("languages") or [])]
    if cmp_langs and user_languages:
        overlap = set(cmp_langs) & set(user_languages)
        score += 0.20 * len(overlap)

    # Genre overlap bonus
    cmp_genres = [g.lower() for g in (t.get("genres") or [])]
    if cmp_genres and user_genres:
        overlap = set(cmp_genres) & set(user_genres)
        score += 0.10 * len(overlap)

    # Mood overlap bonus
    cmp_moods = [m.lower() for m in (t.get("moods") or [])]
    if cmp_moods and user_moods:
        overlap = set(cmp_moods) & set(user_moods)
        score += 0.05 * len(overlap)

    return max(0.0, score)


# ---------- Pacing factor ----------
async def _pacing_factor(db, campaign: dict) -> float:
    """1.0 for asap; <1.0 for even/smart based on day-progress vs daily-budget burn."""
    if campaign.get("pacing") == "asap":
        return 1.0
    daily = float(campaign.get("daily_budget_cents") or 0)
    if daily <= 0:
        return 1.0
    today_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {"campaign_id": campaign["campaign_id"], "served_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "spent": {"$sum": "$attributed_revenue_cents"}}},
    ]
    rows = await db.ad_impressions.aggregate(pipeline).to_list(length=1)
    spent = float(rows[0]["spent"] if rows else 0)
    progress_of_day = ((_now() - today_start).total_seconds()) / 86400.0
    burned = spent / daily if daily else 0
    if burned >= 1.0:
        return 0.0   # daily cap hit
    # If we've burned more than time-progress, slow down; if less, speed up.
    if burned < progress_of_day:
        return 1.0   # behind pace, push
    if burned > progress_of_day + 0.10:
        return 0.4   # over-pacing, throttle
    return 0.8


# ---------- Direct-sold picker ----------
async def _pick_direct_sold(db, user: dict, session: dict, ctx: dict) -> Optional[dict]:
    """Return the highest-scoring eligible active campaign + creative."""
    user_market = (user.get("market") or "dubai").lower()
    actives = await db.campaigns.find(
        {"status": "active",
         "targeting_json.markets": user_market,
         "budget_cents": {"$gt": 0}},
    ).to_list(length=50)
    if not actives:
        return None

    scored = []
    user_id = user.get("user_id")
    for cmp in actives:
        s = _targeting_score(cmp, user, session, ctx)
        if s <= 0:
            continue
        if user_id and await _is_capped(db, user_id=user_id, campaign=cmp):
            continue
        pf = await _pacing_factor(db, cmp)
        if pf <= 0:
            continue
        bid = float(cmp.get("bid_cents_per_impression") or 100)
        score = bid * s * pf
        scored.append((score, cmp))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    # Slight randomness among top 3 to avoid deterministic ordering
    top = scored[:3]
    weights = [t[0] for t in top]
    chosen = random.choices([t[1] for t in top], weights=weights, k=1)[0]

    # Pull creative + action cards
    creative_id = (chosen.get("creative_ids") or [None])[0]
    if not creative_id:
        return None
    creative = await db.ad_creatives.find_one(
        # Phase 36c.5 hotfix — match either `id` (newer writers) or legacy
        # `creative_id`, AND match either newer `status="approved"` OR the
        # legacy pair {approval_status="approved", active=True}. Safety
        # intent preserved: pending/rejected/inactive creatives never serve.
        {"$and": [
            {"$or": [{"id": creative_id}, {"creative_id": creative_id}]},
            {"$or": [
                {"status": {"$in": ["approved", "active"]}},
                {"$and": [{"approval_status": "approved"},
                                {"active": True}]},
            ]},
        ]}
    )
    if not creative:
        return None
    actions = await db.ad_action_cards.find(
        {"campaign_id": chosen["campaign_id"], "enabled": True}
    ).sort([("display_order", 1)]).to_list(length=20)
    business = await db.businesses.find_one({"business_id": chosen.get("business_id")})
    return {
        "decision_path": "direct_sold",
        "campaign": chosen,
        "creative": creative,
        "action_cards": actions,
        "business": business,
    }


def _resolve_creative_path(cr: dict) -> str:
    """Phase 18a creatives store local `audio_path`.  Fallback to a path under
    the static dir based on `audio_url` if missing (defensive)."""
    if cr.get("audio_path"):
        return cr["audio_path"]
    url = cr.get("audio_url") or ""
    prefix = "/api/static/ad_creatives/"
    if url.startswith(prefix):
        return f"/app/backend/static/ad_creatives/{url[len(prefix):]}"
    return ""


# ---------- Public surface ----------
async def select_ad(db, *, user: dict, session: dict, segment_context: dict) -> Optional[dict]:
    """Return a dict with decision_path + campaign + creative + action_cards, or None."""
    if user.get("is_premium"):
        return None  # ad-free
    # Phase 36e Turn 1 — Channel-level subscriber ad-skip. Listeners with
    # an active sub to the channel they're listening to get an ad-free
    # session even if `is_premium` global flag is off.
    try:
        ch_id = (segment_context or {}).get("channel_id")
        u_id    = user.get("user_id")
        if ch_id and u_id:
            from services.subscriptions import user_has_active_sub_for_channel
            if await user_has_active_sub_for_channel(
                    db, user_id=u_id, channel_id=ch_id):
                return None
    except Exception as e:
        logger.debug(f"sub-skip check failed (non-fatal): {e}")
    # Free-listener ad-load probability gate
    if segment_context.get("position") == "postroll":
        if random.random() > AD_LOAD_FREE_PROBABILITY:
            return None

    # 0. Phase 9b — Route-targeted ad picker.  Fires BEFORE direct-sold
    # when the listener has an active commute and an eligible opportunity
    # is in the window (honors a 15-min cooldown).
    try:
        from services.route_ad_engine import pick_route_targeted_ad
        rt = await pick_route_targeted_ad(db, user=user,
                                                       segment_context=segment_context)
        if rt and rt.get("creative"):
            return rt
    except Exception as e:
        logger.debug(f"route_targeted picker error: {e}")

    # 0.5 Phase 18a — Direct-sold v2 (new self-serve advertiser surface).
    # Adapts pick_ad_for_user to the select_ad return shape.  Sets
    # decision_path="direct_sold_v2_phase18a" so the caller can skip the
    # legacy ad_pods/ad_impressions logging (we already wrote ad_serves).
    try:
        from services.advertisers import pick_ad_for_user as _pick_v2
        v2 = await _pick_v2(
            db, user_id=user.get("user_id") or "anon",
                  channel_slug=(segment_context or {}).get("channel_slug") or "",
                  market=(user.get("market") or
                              (segment_context or {}).get("market") or "dubai"))
        if v2 and v2.get("creative"):
            cr = v2["creative"]
            return {
                "decision_path": "direct_sold_v2_phase18a",
                "campaign":   {"campaign_id": v2["campaign"]["id"],
                                  "name": v2["campaign"].get("name"),
                                  "bid_cents_per_impression": 0},
                "creative":   {"creative_id": cr["id"],
                                  "title": cr.get("title"),
                                  "audio_path": _resolve_creative_path(cr),
                                  "audio_url": cr.get("audio_url"),
                                  "image_url": cr.get("image_url"),
                                  "click_url": cr.get("click_url"),
                                  "duration_sec": cr.get("duration_sec", 15)},
                "action_cards": [],
                "_phase18a_serve_id": v2["serve"].get("id"),
            }
    except Exception as e:
        logger.debug(f"phase18a picker error: {e}")

    # 1. Direct-sold
    d = await _pick_direct_sold(db, user, session, segment_context)
    if d:
        return d

    # 2. Sponsored games — Phase 4 stub
    # 3. GAM backfill — Phase 4 scaffold (stub)
    try:
        from services.gam_client import call_gam_for_backfill
        gam = await call_gam_for_backfill(db, user=user, session=session, ctx=segment_context)
        if gam:
            return {"decision_path": "gam_backfill", **gam}
    except Exception as e:
        logger.debug(f"GAM stub: {e}")

    # 4. OpenRTB programmatic auction
    try:
        from services.openrtb_auction import run_openrtb_auction
        rtb = await run_openrtb_auction(db, user=user, session=session, ctx=segment_context)
        if rtb:
            return rtb
    except Exception as e:
        logger.debug(f"OpenRTB auction error: {e}")

    # 5. House promo — Phase 4 stub (none)
    return None


# ---------- Logging ----------
async def log_ad_pod(db, *, session_id: str, segment_id: str, user_id: Optional[str],
                      scheduled_position: str, decision: dict) -> str:
    pod_id = str(uuid.uuid4())
    pod = {
        "_id": pod_id, "session_id": session_id, "segment_id": segment_id, "user_id": user_id,
        "scheduled_position": scheduled_position,
        "ad_creative_id": decision["creative"]["creative_id"],
        "campaign_id": decision["campaign"]["campaign_id"],
        "decision_path": decision["decision_path"],
        "bid_cents": int(decision["campaign"].get("bid_cents_per_impression") or 0),
        "served_at": _now(),
    }
    # Phase 9b — persist route-targeting metadata when applicable
    if decision.get("route_opp_id"):
        pod["route_opp_id"] = decision["route_opp_id"]
        pod["route_reason_codes"] = decision.get("route_reason_codes", [])
    await db.ad_pods.insert_one(pod)
    return pod_id


async def log_ad_impression(db, *, ad_pod_id: str, decision: dict, user_id: Optional[str],
                              session_id: str, context: dict) -> str:
    imp_id = str(uuid.uuid4())
    bid = int(decision["campaign"].get("bid_cents_per_impression") or 0)
    await db.ad_impressions.insert_one({
        "_id": imp_id, "ad_pod_id": ad_pod_id,
        "ad_creative_id": decision["creative"]["creative_id"],
        "campaign_id": decision["campaign"]["campaign_id"],
        "user_id": user_id, "session_id": session_id,
        "served_at": _now(),
        "completion_pct": 0.0, "completed_at": None, "played_for_sec": 0.0,
        "market": context.get("market"), "daypart_slug": context.get("daypart"),
        "channel_slug": context.get("channel_slug"),
        "voice_key": context.get("voice_key"),
        "context_json": context,
        "attributed_revenue_cents": bid,
    })
    # Decrement campaign budget by the bid for fast pacing-feedback (eventually consistent)
    await db.campaigns.update_one(
        {"campaign_id": decision["campaign"]["campaign_id"]},
        {"$inc": {"budget_cents": -bid, "stats.served_count": 1}},
    )
    return imp_id
