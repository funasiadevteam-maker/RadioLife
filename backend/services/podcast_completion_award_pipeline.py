"""Phase G — AD.9 Podcast Completion Points · Award pipeline.

Triggered by `podcast_completed` events from
`podcast_progress_service.record_progress()`.  Fans out to every
matching `active` campaign, applies caps, awards points/vouchers,
and fires the `podcast_completion_awarded` notification.

Idempotent per `(campaign_id, user_id, episode_id)` via the unique
compound index on `podcast_completion_awards`.  Called INLINE from
`podcast_progress_service.py` so the frontend response can carry the
resulting award list (for a completion toast).

Contract:
    await on_podcast_completed(db, user_id=..., episode_id=...,
                                                          podcast_id=..., episode_title=...)
    → {"awards": [{...}, ...], "count": N}
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.ad9.pipeline")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _iso(v):
    return _aware(v).isoformat() if isinstance(v, datetime) else v


async def _matching_campaigns(db, *, podcast_id: Optional[str],
                                                              episode_id: Optional[str]
                                                              ) -> List[Dict[str, Any]]:
    """Every active campaign whose targeting matches (podcast_id and
    episode_id are both nullable filters on the campaign row)."""
    now = _now()
    q: Dict[str, Any] = {"status": "active",
                                              "start_at": {"$lte": now},
                                              "end_at":    {"$gt":    now}}
    # Podcast filter: campaigns with null podcast_id apply to ANY podcast;
    # others must match exactly.
    q_podcast_any = {"$or": [{"podcast_id": None}]}
    if podcast_id:
        q_podcast_any["$or"].append({"podcast_id": podcast_id})
    q_episode_any = {"$or": [{"episode_id": None}]}
    if episode_id:
        q_episode_any["$or"].append({"episode_id": episode_id})
    q["$and"] = [q_podcast_any, q_episode_any]
    return [c async for c in db.podcast_completion_campaigns.find(q)]


async def _already_awarded_for_user(db, *, campaign_id: str,
                                                                                user_id: str,
                                                                                episode_id: str) -> bool:
    return bool(await db.podcast_completion_awards.find_one(
        {"campaign_id": campaign_id, "user_id": user_id,
          "episode_id": episode_id}))


async def _user_completion_count(db, *, campaign_id: str,
                                                                          user_id: str) -> int:
    return await db.podcast_completion_awards.count_documents(
        {"campaign_id": campaign_id, "user_id": user_id})


async def _award_bigcoin(db, *, user_id: str, campaign_id: str,
                                              episode_id: str, points: int) -> Dict[str, Any]:
    """Credit BigCoin via the unified points ledger."""
    from services.points_service import PointsService
    result = await PointsService(db).award(
        user_id=user_id,
        source="podcast_completion_reward",
        source_id=episode_id,
        delta=int(points),
        idempotency_key=f"pcc_{campaign_id}_{user_id}_{episode_id}",
        metadata={"campaign_id": campaign_id,
                            "episode_id": episode_id,
                            "note": "AD.9 podcast completion reward"},
        enforce_caps=False)
    return {"ok": result.ok,
                    "wallet_item_id": result.entry_id,
                    "wallet_item_type": "points_ledger",
                    "balance_after": result.balance_after,
                    "reason": result.reason}


async def _award_voucher(db, *, user_id: str, campaign_id: str,
                                              episode_id: str,
                                              amount_cents: int,
                                              advertiser_business_id: str,
                                              sponsor_message: str
                                              ) -> Dict[str, Any]:
    """Mint a dollar-off coupon in the existing `coupons` collection so
    it flows through wallet_v2 aggregator."""
    now = _now()
    coupon_id = _gen("cpn_pcc")
    code = secrets.token_urlsafe(8).upper().replace("_", "").replace("-", "")[:10]
    # Reuse the standard `coupons` shape.  offer_id references a
    # phantom offer we mint inline for the campaign — advertiser can
    # scope later by business_id.  Keep it simple: create a lightweight
    # `offers` row tied to advertiser.
    offer_id = f"ofr_pcc_{campaign_id[:12]}"
    existing_offer = await db.offers.find_one({"offer_id": offer_id})
    if not existing_offer:
        try:
            await db.offers.insert_one({
                "_id":                        offer_id,
                "offer_id":              offer_id,
                "business_id":        advertiser_business_id,
                "title":                    sponsor_message[:100] or "Podcast completion voucher",
                "discount_percent":  0,
                "offer_type":          "dollar_off",
                "amount_cents":      int(amount_cents),
                "campaign_source": "ad9_podcast_completion",
                "created_at":          now,
            })
        except Exception:
            pass    # duplicate on race — safe.
    doc = {
        "_id":                    coupon_id,
        "coupon_id":        coupon_id,
        "code":                  code,
        "user_id":            user_id,
        "offer_id":          offer_id,
        "status":              "saved",
        "amount_cents":  int(amount_cents),
        "source":              "ad9_podcast_completion",
        "campaign_id":    campaign_id,
        "episode_id":      episode_id,
        "created_at":      now,
    }
    await db.coupons.insert_one(doc)
    return {"ok": True,
                    "wallet_item_id": coupon_id,
                    "wallet_item_type": "coupon",
                    "coupon_code": code}


async def _try_award_campaign(db, *,
                                                                  campaign: Dict[str, Any],
                                                                  user_id: str,
                                                                  episode_id: str,
                                                                  podcast_id: Optional[str]
                                                                  ) -> Optional[Dict[str, Any]]:
    campaign_id = campaign["id"]
    # Guards.
    if int(campaign.get("remaining_budget_cents") or 0) < \
            int(campaign.get("cost_per_completion_cents") or 0):
        return None
    max_per_user = int(campaign.get("max_completions_per_user") or 1)
    if max_per_user > 0:
        already = await _user_completion_count(
            db, campaign_id=campaign_id, user_id=user_id)
        if already >= max_per_user:
            return None
    max_total = int(campaign.get("max_total_completions") or 0)
    if max_total > 0 and int(campaign.get("awarded_count") or 0) >= max_total:
        return None
    if await _already_awarded_for_user(
                db, campaign_id=campaign_id, user_id=user_id,
                episode_id=episode_id):
        return None

    # Reserve the budget atomically — decrement remaining_budget_cents
    # and bump awarded_count in a single find_one_and_update guarded
    # against underflow / cap.
    cost = int(campaign.get("cost_per_completion_cents") or 0)
    reserved = await db.podcast_completion_campaigns.find_one_and_update(
        {"id": campaign_id,
          "status": "active",
          "remaining_budget_cents": {"$gte": cost},
          "$expr": {"$lt": ["$awarded_count", "$max_total_completions"]}},
        {"$inc": {"remaining_budget_cents": -cost,
                          "awarded_count": 1},
          "$set": {"last_award_at": _now()}},
        return_document=True)
    if not reserved:
        # Lost the race / budget exhausted.  Try flip to completed.
        try:
            await db.podcast_completion_campaigns.update_one(
                {"id": campaign_id, "status": "active",
                  "$expr": {"$gte": ["$awarded_count", "$max_total_completions"]}},
                {"$set": {"status": "completed", "completed_at": _now()}})
        except Exception:
            pass
        return None

    # Do the actual grant (points or voucher).
    currency = campaign.get("currency") or "usd"
    points = int(campaign.get("points_reward") or 0)
    sponsor_message = campaign.get("sponsor_message") or ""
    advertiser_business_id = campaign["advertiser_business_id"]
    try:
        if currency == "bc":
            grant = await _award_bigcoin(
                db, user_id=user_id, campaign_id=campaign_id,
                episode_id=episode_id, points=points)
        else:
            grant = await _award_voucher(
                db, user_id=user_id, campaign_id=campaign_id,
                episode_id=episode_id,
                amount_cents=points,        # `points_reward` doubles as cents for `usd`
                advertiser_business_id=advertiser_business_id,
                sponsor_message=sponsor_message)
    except Exception as e:
        logger.exception("[ad9] grant failed for %s: %s", campaign_id, e)
        # Roll back the reservation.
        await db.podcast_completion_campaigns.update_one(
            {"id": campaign_id},
            {"$inc": {"remaining_budget_cents": cost, "awarded_count": -1}})
        return None

    award_id = _gen("pca")
    award_doc = {
        "_id":                                          award_id,
        "id":                                            award_id,
        "campaign_id":                            campaign_id,
        "user_id":                                    user_id,
        "podcast_id":                              podcast_id,
        "episode_id":                              episode_id,
        "points_awarded":                        points,
        "currency":                                  currency,
        "advertiser_charge_cents":        cost,
        "wallet_item_id":                        grant.get("wallet_item_id"),
        "wallet_item_type":                    grant.get("wallet_item_type"),
        "sponsor_message":                    sponsor_message,
        "advertiser_business_id":        advertiser_business_id,
        "awarded_at":                              _now(),
    }
    try:
        await db.podcast_completion_awards.insert_one(award_doc)
    except Exception as e:
        # Duplicate — race condition, another worker already awarded.
        if "duplicate" in str(e).lower() or "E11000" in str(e):
            # Roll back reservation.
            await db.podcast_completion_campaigns.update_one(
                {"id": campaign_id},
                {"$inc": {"remaining_budget_cents": cost,
                                  "awarded_count": -1}})
            return None
        raise

    # If budget hit floor OR total cap reached, flip campaign to completed.
    refreshed = await db.podcast_completion_campaigns.find_one(
        {"id": campaign_id},
        {"remaining_budget_cents": 1, "awarded_count": 1,
          "max_total_completions": 1, "cost_per_completion_cents": 1,
          "status": 1})
    if refreshed and refreshed.get("status") == "active":
        rem  = int(refreshed.get("remaining_budget_cents") or 0)
        crem = int(refreshed.get("cost_per_completion_cents") or 0)
        aw    = int(refreshed.get("awarded_count") or 0)
        cap  = int(refreshed.get("max_total_completions") or 0)
        if rem < crem or (cap > 0 and aw >= cap):
            await db.podcast_completion_campaigns.update_one(
                {"id": campaign_id, "status": "active"},
                {"$set": {"status": "completed", "completed_at": _now()}})

    # Fire notification (never break upstream on failure).
    try:
        from services.notification_trigger_dispatcher import dispatch_event
        await dispatch_event(
            db, event_name="podcast_completion_awarded",
            user_id=user_id,
            payload={"campaign_id":                    campaign_id,
                              "award_id":                        award_id,
                              "podcast_id":                    podcast_id,
                              "episode_id":                    episode_id,
                              "points_awarded":              points,
                              "currency":                        currency,
                              "sponsor_message":            sponsor_message,
                              "advertiser_business_id":  advertiser_business_id})
    except Exception:
        pass

    return {
        "award_id":                              award_id,
        "campaign_id":                        campaign_id,
        "user_id":                                user_id,
        "episode_id":                          episode_id,
        "points_awarded":                    points,
        "currency":                              currency,
        "wallet_item_id":                    grant.get("wallet_item_id"),
        "wallet_item_type":                grant.get("wallet_item_type"),
        "sponsor_message":                sponsor_message,
        "advertiser_business_id":    advertiser_business_id,
        "awarded_at":                          _iso(award_doc["awarded_at"]),
    }


async def on_podcast_completed(db, *,
                                                              user_id: str,
                                                              episode_id: str,
                                                              podcast_id: Optional[str] = None,
                                                              episode_title: Optional[str] = None
                                                              ) -> Dict[str, Any]:
    """Entrypoint called from `podcast_progress_service` immediately
    after `dispatch_event('podcast_completed', ...)`.  Returns the
    list of awards granted for THIS completion so the response payload
    can carry them (for the completion toast on the client)."""
    if not user_id or not episode_id:
        return {"awards": [], "count": 0}
    try:
        campaigns = await _matching_campaigns(
            db, podcast_id=podcast_id, episode_id=episode_id)
    except Exception as e:
        logger.warning("[ad9] campaign lookup failed: %s", e)
        return {"awards": [], "count": 0}
    awards: List[Dict[str, Any]] = []
    for c in campaigns:
        try:
            r = await _try_award_campaign(
                db, campaign=c, user_id=user_id,
                episode_id=episode_id, podcast_id=podcast_id)
            if r:
                awards.append(r)
        except Exception as e:
            logger.warning("[ad9] award failed for %s: %s", c.get("id"), e)
    return {"awards": awards, "count": len(awards)}


__all__ = ["on_podcast_completed"]
