"""Phase 39 Session 7 — Aggregate-only Advertiser Dashboard + Geo-Anchored Pre-Rolls.

All endpoints REQUIRE the segment-size floor (>=20 users) via the S4
`is_advertiser_safe_aggregation` guard.  Listener identity NEVER leaves
the server boundary.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user
from routes.privacy import is_advertiser_safe_aggregation, MIN_SEGMENT_SIZE

router = APIRouter(prefix="/api/advertiser", tags=["advertiser-aggregate"])
log = logging.getLogger("bigfm.advertiser.aggregate")


def _now() -> datetime: return datetime.now(timezone.utc)


async def _audit(db, *, advertiser_user_id: str, action: str,
                 params: dict, segment_size: Optional[int],
                 outcome: str) -> None:
    try:
        await db.AdvertiserAggregateAuditLogs.insert_one({
            "_id":                       uuid.uuid4().hex,
            "advertiser_user_id":    advertiser_user_id,
            "action":              action,
            "params":            params,
            "segment_size":  segment_size,
            "outcome":          outcome,
            "timestamp":        _now().isoformat(),
        })
    except Exception as e:
        log.warning("[adv-agg] audit insert failed: %s", e)


@router.get("/audience/aggregate")
async def audience_aggregate(request: Request,
                             category: Optional[str] = Query(None),
                             time_bucket: Optional[str] = Query(None),
                             day_of_week: Optional[int] = Query(None, ge=0, le=6),
                             market: Optional[str] = Query(None),
                             user: dict = Depends(current_user)):
    """Returns aggregate counts (NEVER per-user). Refuses segments < 20."""
    db = request.app.state.db
    params = {"category": category, "time_bucket": time_bucket,
              "day_of_week": day_of_week, "market": market}

    # Build $match: only count consenting users via UserBusinessVisits (consent>=3 enforced at ingestion).
    match: dict = {}
    if category:
        match["category"] = category
    if time_bucket:
        match["time_bucket"] = time_bucket
    if day_of_week is not None:
        match["day_of_week"] = day_of_week  # noqa: future use

    # Distinct user count
    user_ids = await db.UserBusinessVisits.distinct("user_id", match)
    segment_size = len(user_ids)

    if not is_advertiser_safe_aggregation(segment_size):
        await _audit(db, advertiser_user_id=user["user_id"],
                     action="audience_aggregate", params=params,
                     segment_size=segment_size, outcome="refused_too_small")
        raise HTTPException(422, {
            "code": "segment_too_small",
            "min_required": MIN_SEGMENT_SIZE,
            "message": (f"Segment must contain >= {MIN_SEGMENT_SIZE} users "
                        f"to prevent re-identification. Broaden filters.")})

    # Aggregate: top categories + typical time_buckets across matching visits.
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"cat": "$category", "bucket": "$time_bucket"},
                    "n": {"$sum": 1}}},
    ]
    agg = [r async for r in db.UserBusinessVisits.aggregate(pipeline)]
    cat_counts: dict[str, int] = {}
    bucket_counts: dict[str, int] = {}
    for row in agg:
        cat_counts[row["_id"]["cat"]] = cat_counts.get(row["_id"]["cat"], 0) + row["n"]
        bk = row["_id"]["bucket"]
        if bk:
            bucket_counts[bk] = bucket_counts.get(bk, 0) + row["n"]

    top_categories = sorted(cat_counts.items(), key=lambda x: -x[1])[:5]
    typical_buckets = sorted(bucket_counts.items(), key=lambda x: -x[1])[:4]

    result = {
        "segment_size":  segment_size,
        "top_categories": [{"category": c, "visit_count": n}
                          for c, n in top_categories],
        "typical_time_buckets": [{"bucket": b, "visit_count": n}
                                 for b, n in typical_buckets],
        "coverage_markets":   [],   # Phase 39M corridor work
        "query":              params,
    }
    await _audit(db, advertiser_user_id=user["user_id"],
                 action="audience_aggregate", params=params,
                 segment_size=segment_size, outcome="ok")
    return result


class GeoAnchoredCampaignIn(BaseModel):
    name:                    str = Field(..., min_length=1, max_length=120)
    target_category:    str = Field(..., min_length=1)
    target_time_bucket: str = Field(..., pattern="^(morning|lunch|evening|night)$")
    creative_audio_url: str
    budget_aed:          float = Field(default=0, ge=0)


@router.post("/campaigns/geo_anchored")
async def create_geo_anchored_campaign(body: GeoAnchoredCampaignIn,
                                       request: Request,
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    # Pre-check segment size before letting the advertiser commit budget.
    user_ids = await db.UserBusinessVisits.distinct(
        "user_id",
        {"category": body.target_category,
         "time_bucket": body.target_time_bucket})
    segment_size = len(user_ids)
    if not is_advertiser_safe_aggregation(segment_size):
        await _audit(db, advertiser_user_id=user["user_id"],
                     action="campaign_create_blocked",
                     params=body.model_dump(),
                     segment_size=segment_size,
                     outcome="refused_too_small")
        raise HTTPException(422, {
            "code": "segment_too_small",
            "min_required": MIN_SEGMENT_SIZE,
            "estimated_segment": segment_size,
            "message": "Target segment too small for privacy-safe matching."})

    cid = "geo_" + uuid.uuid4().hex[:12]
    doc = {
        "_id":                            cid,
        "campaign_id":               cid,
        "owner_user_id":          user["user_id"],
        "name":                       body.name,
        "target_category":      body.target_category,
        "target_time_bucket": body.target_time_bucket,
        "creative_audio_url": body.creative_audio_url,
        "budget_aed":               body.budget_aed,
        "status":                       "active",
        "estimated_segment_size": segment_size,
        "delivered_impressions": 0,
        "completed_impressions": 0,
        "created_at":                _now(),
    }
    await db.GeoAnchoredCampaigns.insert_one(doc)
    await _audit(db, advertiser_user_id=user["user_id"],
                 action="campaign_created",
                 params={"campaign_id": cid,
                         "target_category": body.target_category,
                         "target_time_bucket": body.target_time_bucket},
                 segment_size=segment_size, outcome="ok")
    return {"ok": True, "campaign_id": cid,
            "estimated_segment_size": segment_size}


@router.get("/campaigns/geo_anchored")
async def list_geo_anchored_campaigns(request: Request,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    async for r in db.GeoAnchoredCampaigns.find(
        {"owner_user_id": user["user_id"]}
    ).sort("created_at", -1):
        r.pop("_id", None)
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return {"count": len(out), "campaigns": out}


async def select_geo_anchored_ad_for_user(db, user_id: str) -> Optional[dict]:
    """Server-side matching.  Returns a campaign dict when a listener with
    consent>=3 has a UserRoutePattern matching an active campaign's
    target_category + target_time_bucket — else None.

    Increments delivered_impressions atomically on selection."""
    u = await db.users.find_one({"user_id": user_id}, {"location_consent_level": 1})
    if not u or int(u.get("location_consent_level", 0)) < 3:
        return None
    patterns = []
    async for p in db.UserRoutePatterns.find({"user_id": user_id}):
        patterns.append(p)
    if not patterns:
        return None
    # Build user's (category, bucket) signal set from patterns' destinations.
    user_signals: set[tuple[str, str]] = set()
    for p in patterns:
        dest = await db.UserFrequentPlaces.find_one(
            {"user_id": user_id,
             "place_id": p.get("destination_place_id")})
        if dest and dest.get("category"):
            user_signals.add((dest["category"],
                              p.get("dominant_time_bucket") or "morning"))
    if not user_signals:
        return None
    for cat, bucket in user_signals:
        camp = await db.GeoAnchoredCampaigns.find_one_and_update(
            {"target_category": cat,
             "target_time_bucket": bucket,
             "status": "active"},
            {"$inc": {"delivered_impressions": 1}},
            sort=[("delivered_impressions", 1)],   # spread across campaigns
            return_document=True)
        if camp:
            camp.pop("_id", None)
            if isinstance(camp.get("created_at"), datetime):
                camp["created_at"] = camp["created_at"].isoformat()
            return camp
    return None


async def ensure_advertiser_aggregate_indexes(db) -> None:
    try:
        await db.GeoAnchoredCampaigns.create_index(
            [("owner_user_id", 1), ("created_at", -1)],
            name="geo_camp_owner_time")
        await db.GeoAnchoredCampaigns.create_index(
            [("target_category", 1), ("target_time_bucket", 1),
             ("status", 1)],
            name="geo_camp_targeting")
        await db.AdvertiserAggregateAuditLogs.create_index(
            [("advertiser_user_id", 1), ("timestamp", -1)],
            name="adv_agg_audit_user_time")
        log.info("[adv-agg] indexes ensured")
    except Exception as e:
        log.warning("[adv-agg] ensure indexes failed: %s", e)
