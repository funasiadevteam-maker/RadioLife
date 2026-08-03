"""Phase 4 — Admin ads endpoints + revenue meter + GAM integration.

Mounted at /api/admin/ads (admin role required everywhere).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from bson import ObjectId

admin_ads_router = APIRouter(prefix="/api/admin/ads", tags=["admin-ads"])


async def _require_admin(request: Request):
    from auth import current_user
    u = await current_user(request)
    if u.get("role") != "admin":
        raise HTTPException(403, "admin only")
    return u


def _ser(d):
    if not d: return d
    d = dict(d)
    if "_id" in d:
        d["id"] = str(d["_id"]); d.pop("_id", None)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"): d[k] = v.isoformat()
    return d


# ---------- Advertiser queue ----------
@admin_ads_router.get("/advertisers/queue")
async def advertiser_queue(request: Request, _a = Depends(_require_admin),
                            status: Optional[str] = Query(None)):
    db = request.app.state.db
    q = {}
    if status:
        q["approval_status"] = status
    docs = await db.advertisers.find(q).sort([("created_at", -1)]).to_list(length=200)
    return {"items": [_ser(d) for d in docs], "total": len(docs)}


@admin_ads_router.post("/advertisers/{advertiser_id}/approve")
async def approve_advertiser(advertiser_id: str, request: Request, _a = Depends(_require_admin)):
    db = request.app.state.db
    res = await db.advertisers.update_one(
        {"advertiser_id": advertiser_id},
        {"$set": {"approval_status": "approved", "approved_at": datetime.now(timezone.utc)}},
    )
    if res.matched_count != 1: raise HTTPException(404, "advertiser not found")
    # Flip user's role to 'advertiser' (but keep their existing role too via a flag)
    adv = await db.advertisers.find_one({"advertiser_id": advertiser_id})
    if adv and adv.get("user_id"):
        await db.users.update_one({"user_id": adv["user_id"]}, {"$set": {"is_advertiser": True}})
    return {"ok": True}


@admin_ads_router.post("/advertisers/{advertiser_id}/reject")
async def reject_advertiser(advertiser_id: str, request: Request, _a = Depends(_require_admin),
                             reason: str = Query("")):
    db = request.app.state.db
    res = await db.advertisers.update_one(
        {"advertiser_id": advertiser_id},
        {"$set": {"approval_status": "rejected", "rejection_reason": reason,
                   "rejected_at": datetime.now(timezone.utc)}},
    )
    if res.matched_count != 1: raise HTTPException(404, "advertiser not found")
    return {"ok": True}


# ---------- Campaign queue ----------
@admin_ads_router.get("/campaigns/queue")
async def campaign_queue(request: Request, _a = Depends(_require_admin),
                          status: Optional[str] = Query(None)):
    db = request.app.state.db
    q = {}
    if status: q["status"] = status
    docs = await db.campaigns.find(q).sort([("created_at", -1)]).to_list(length=200)
    out = []
    for d in docs:
        adv = await db.advertisers.find_one({"advertiser_id": d.get("advertiser_id")}, {"name": 1})
        biz = await db.businesses.find_one({"business_id": d.get("business_id")}, {"name": 1})
        d2 = _ser(d)
        d2["advertiser_name"] = adv["name"] if adv else None
        d2["business_name"] = biz["name"] if biz else None
        out.append(d2)
    return {"items": out, "total": len(out)}


@admin_ads_router.post("/campaigns/{campaign_id}/approve")
async def approve_campaign(campaign_id: str, request: Request, _a = Depends(_require_admin)):
    db = request.app.state.db
    res = await db.campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "active", "approved_by": _a.get("user_id"),
                   "approved_at": datetime.now(timezone.utc)}},
    )
    if res.matched_count != 1: raise HTTPException(404, "campaign not found")
    return {"ok": True}


@admin_ads_router.post("/campaigns/{campaign_id}/reject")
async def reject_campaign(campaign_id: str, request: Request, _a = Depends(_require_admin),
                           reason: str = Query("")):
    db = request.app.state.db
    res = await db.campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "rejected", "rejection_reason": reason}},
    )
    if res.matched_count != 1: raise HTTPException(404, "campaign not found")
    return {"ok": True}


@admin_ads_router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, request: Request, _a = Depends(_require_admin)):
    db = request.app.state.db
    res = await db.campaigns.update_one({"campaign_id": campaign_id}, {"$set": {"status": "paused"}})
    if res.matched_count != 1: raise HTTPException(404, "campaign not found")
    return {"ok": True}


# ---------- Revenue meter ----------
@admin_ads_router.get("/revenue/live")
async def revenue_live(request: Request, _a = Depends(_require_admin),
                        minutes: int = Query(60, ge=1, le=10080)):
    db = request.app.state.db
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    # Impressions in window
    pipeline_total = [
        {"$match": {"served_at": {"$gte": since}}},
        {"$group": {"_id": None,
                     "impressions": {"$sum": 1},
                     "revenue_cents": {"$sum": "$attributed_revenue_cents"}}},
    ]
    total_row = await db.ad_impressions.aggregate(pipeline_total).to_list(length=1)
    total = total_row[0] if total_row else {"impressions": 0, "revenue_cents": 0}

    pipeline_market = [
        {"$match": {"served_at": {"$gte": since}}},
        {"$group": {"_id": "$market",
                     "impressions": {"$sum": 1},
                     "revenue_cents": {"$sum": "$attributed_revenue_cents"}}},
    ]
    by_market = await db.ad_impressions.aggregate(pipeline_market).to_list(length=10)

    pipeline_channel = [
        {"$match": {"served_at": {"$gte": since}}},
        {"$group": {"_id": "$channel_slug",
                     "impressions": {"$sum": 1},
                     "revenue_cents": {"$sum": "$attributed_revenue_cents"}}},
        {"$sort": {"impressions": -1}}, {"$limit": 10},
    ]
    by_channel = await db.ad_impressions.aggregate(pipeline_channel).to_list(length=10)

    pipeline_campaign = [
        {"$match": {"served_at": {"$gte": since}}},
        {"$group": {"_id": "$campaign_id",
                     "impressions": {"$sum": 1},
                     "revenue_cents": {"$sum": "$attributed_revenue_cents"}}},
        {"$sort": {"revenue_cents": -1}}, {"$limit": 10},
    ]
    by_campaign = await db.ad_impressions.aggregate(pipeline_campaign).to_list(length=10)
    # Hydrate campaign names
    campaign_ids = [c["_id"] for c in by_campaign if c["_id"]]
    cmps = await db.campaigns.find({"campaign_id": {"$in": campaign_ids}}, {"campaign_id": 1, "name": 1}).to_list(length=20)
    cmp_name = {c["campaign_id"]: c.get("name") for c in cmps}
    for c in by_campaign:
        c["campaign_name"] = cmp_name.get(c["_id"]) or c["_id"]

    # Imaging revenue (from station_flow_logs.value_cents)
    pipeline_imaging = [
        {"$match": {"played_at": {"$gte": since}, "value_cents": {"$gt": 0}}},
        {"$group": {"_id": "$item_type",
                     "count": {"$sum": 1}, "revenue_cents": {"$sum": "$value_cents"}}},
    ]
    imaging_rev = await db.station_flow_logs.aggregate(pipeline_imaging).to_list(length=20)

    # Premium user count + listener hours (heuristic)
    premium_active = await db.users.count_documents({"is_premium": True})
    free_active = await db.users.count_documents({"is_premium": {"$ne": True}})

    return {
        "minutes": minutes,
        "total_impressions": total["impressions"],
        "total_revenue_cents": total["revenue_cents"],
        "total_revenue_usd": round(total["revenue_cents"] / 100.0, 2),
        "imaging_revenue_cents": sum(r["revenue_cents"] for r in imaging_rev),
        "by_market":   [{"market": r["_id"], "impressions": r["impressions"], "revenue_cents": r["revenue_cents"]} for r in by_market],
        "by_channel":  [{"channel": r["_id"], "impressions": r["impressions"], "revenue_cents": r["revenue_cents"]} for r in by_channel],
        "by_campaign": [{"campaign_id": r["_id"], "campaign_name": r["campaign_name"], "impressions": r["impressions"], "revenue_cents": r["revenue_cents"]} for r in by_campaign],
        "imaging_by_type": [{"item_type": r["_id"], "count": r["count"], "revenue_cents": r["revenue_cents"]} for r in imaging_rev],
        "premium_users": premium_active,
        "free_users": free_active,
    }


# ---------- GAM scaffold ----------
@admin_ads_router.get("/integrations/gam")
async def gam_get(request: Request, _a = Depends(_require_admin)):
    from services.gam_client import get_settings
    db = request.app.state.db
    cfg = await get_settings(db)
    cfg = _ser(cfg)
    # Don't expose the encrypted blob, just whether it's set
    cfg["service_account_configured"] = bool(cfg.get("service_account_json_encrypted"))
    cfg.pop("service_account_json_encrypted", None)
    return cfg


@admin_ads_router.post("/integrations/gam")
async def gam_save(request: Request, _a = Depends(_require_admin), payload: dict = None):
    from services.gam_client import save_settings
    if not payload or "service_account_json" not in payload:
        raise HTTPException(400, "service_account_json required")
    db = request.app.state.db
    cfg = await save_settings(db,
                                service_account_json=payload["service_account_json"],
                                ad_unit_id=payload.get("ad_unit_id"))
    return {"ok": True, "ad_unit_id": cfg.get("ad_unit_id"),
            "network_code": cfg.get("network_code")}


@admin_ads_router.post("/integrations/gam/test")
async def gam_test(request: Request, _a = Depends(_require_admin)):
    from services.gam_client import test_connection
    return await test_connection(request.app.state.db)



# ─── Phase 18d.1 — Programmatic Auction Log (read-only audit panel) ────
#
# Returns the last N ad picks merged across two log streams:
#   - `ad_impressions` for direct/sponsored/house picks (timestamp =
#     `served_at`, clear price = `attributed_revenue_cents`, bid price
#     joined from `ad_pods.bid_cents`, source derived from
#     `ad_pods.decision_path`).
#   - `openrtb_auctions` for programmatic wins (timestamp = `ran_at`,
#     clear price = `clearing_price_cents`, bid price = `winner_price_cents`,
#     source hardcoded "openrtb").
#
# Read-time JOINs to `ad_creatives` / `campaigns` / `advertisers` add the
# human-readable title / advertiser_name / campaign_name. No write-side
# logging changes — this endpoint is purely a read aggregator.

import hashlib as _hashlib

_DECISION_PATH_TO_SOURCE = {
    "direct_sold":         "direct",
    "route_targeted":     "sponsored",
    "private_marketplace": "private_marketplace",
    "house":                  "house",
    "gam":                     "gam",
}


def _session_hash(session_id: str | None) -> str | None:
    if not session_id:
        return None
    return _hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]


async def _name_lookups(db, creative_ids: set, campaign_ids: set) -> tuple[dict, dict, dict]:
    """One-shot lookups for human-readable names. Returns
    (creatives_by_id, campaigns_by_id, advertisers_by_id)."""
    creatives = {}
    if creative_ids:
        async for c in db.ad_creatives.find(
                {"$or": [{"id": {"$in": list(creative_ids)}},
                              {"creative_id": {"$in": list(creative_ids)}}]},
                {"id": 1, "creative_id": 1, "title": 1, "advertiser_id": 1, "_id": 0}):
            cid = c.get("id") or c.get("creative_id")
            if cid:
                creatives[cid] = c
    campaigns = {}
    if campaign_ids:
        async for c in db.campaigns.find(
                {"campaign_id": {"$in": list(campaign_ids)}},
                {"campaign_id": 1, "name": 1, "title": 1,
                  "advertiser_id": 1, "_id": 0}):
            campaigns[c["campaign_id"]] = c
    advertiser_ids = {c.get("advertiser_id") for c in campaigns.values()
                                  if c.get("advertiser_id")}
    advertiser_ids |= {c.get("advertiser_id") for c in creatives.values()
                                      if c.get("advertiser_id")}
    advertisers = {}
    if advertiser_ids:
        async for a in db.advertisers.find(
                {"advertiser_id": {"$in": list(advertiser_ids)}},
                {"advertiser_id": 1, "company_name": 1, "name": 1, "_id": 0}):
            advertisers[a["advertiser_id"]] = a
    return creatives, campaigns, advertisers


@admin_ads_router.get("/auction-log/recent")
async def auction_log_recent(request: Request, _a = Depends(_require_admin),
                                                  limit: int = Query(20, ge=1, le=100),
                                                  window_seconds: int = Query(86400, ge=60, le=604800)):
    """Last N ad picks merged across `ad_impressions` + `openrtb_auctions`,
    newest first. Read-only; no write-side schema changes."""
    db = request.app.state.db
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

    # Pull a generous pool from each stream, merge, sort, truncate.
    pool = max(limit * 2, 50)
    impressions = [i async for i in db.ad_impressions.find(
        {"served_at": {"$gte": cutoff}},
        ).sort("served_at", -1).limit(pool)]
    auctions = [a async for a in db.openrtb_auctions.find(
        {"ran_at": {"$gte": cutoff}},
        ).sort("ran_at", -1).limit(pool)]

    # Collect all ids we'll need to enrich.
    cre_ids = {i.get("ad_creative_id") for i in impressions if i.get("ad_creative_id")}
    cmp_ids = {i.get("campaign_id") for i in impressions if i.get("campaign_id")}
    pod_ids  = {i.get("ad_pod_id") for i in impressions if i.get("ad_pod_id")}
    pods = {}
    if pod_ids:
        async for p in db.ad_pods.find(
                {"_id": {"$in": list(pod_ids)}},
                {"_id": 1, "decision_path": 1, "bid_cents": 1}):
            pods[p["_id"]] = p
    creatives, campaigns, advertisers = await _name_lookups(db, cre_ids, cmp_ids)

    items: list[dict] = []
    for imp in impressions:
        pod  = pods.get(imp.get("ad_pod_id")) or {}
        cre  = creatives.get(imp.get("ad_creative_id")) or {}
        cmp_ = campaigns.get(imp.get("campaign_id")) or {}
        adv_id = cmp_.get("advertiser_id") or cre.get("advertiser_id")
        adv   = advertisers.get(adv_id) or {}
        source = _DECISION_PATH_TO_SOURCE.get(pod.get("decision_path") or "",
                                                                          "direct")
        row = {"auction_id":       imp.get("ad_pod_id") or str(imp.get("_id", "")),
                  "timestamp":       imp.get("served_at"),
                  "slot_id":              imp.get("ad_pod_id"),
                  "channel_id":     imp.get("channel_slug"),
                  "source":               source,
                  "creative_id":     imp.get("ad_creative_id"),
                  "creative_title": cre.get("title"),
                  "advertiser_id": adv_id,
                  "advertiser_name": adv.get("company_name") or adv.get("name"),
                  "campaign_id":     imp.get("campaign_id"),
                  "campaign_name": cmp_.get("name") or cmp_.get("title"),
                  "clear_price_cents": int(imp.get("attributed_revenue_cents")
                                                              or 0),
                  "bid_price_cents":     int(pod.get("bid_cents") or 0)
                                                          if pod.get("bid_cents") is not None
                                                          else None,
                  "city":                     imp.get("market"),
                  "user_session_hash": _session_hash(imp.get("session_id"))}
        # Drop None values per spec: omit rather than fake.
        items.append({k: v for k, v in row.items() if v not in (None, "")})

    for au in auctions:
        partner = au.get("winner_partner") or "unknown"
        reason = (f"winning bid @ {au.get('winner_price_cents', 0)}¢ via {partner}"
                          if au.get("winner_price_cents") is not None else None)
        row = {"auction_id":   au.get("bidrequest_id") or str(au.get("_id", "")),
                  "timestamp":   au.get("ran_at"),
                  "source":           "openrtb",
                  "clear_price_cents": int(au.get("clearing_price_cents") or 0),
                  "bid_price_cents":     int(au.get("winner_price_cents")
                                                          or au.get("clearing_price_cents") or 0),
                  "reason":           reason,
                  "user_session_hash": _session_hash(au.get("session_id"))}
        items.append({k: v for k, v in row.items() if v not in (None, "")})

    # Newest first; treat naive datetimes as UTC for safety.
    def _key(it):
        t = it.get("timestamp")
        if hasattr(t, "tzinfo") and t.tzinfo is None:
            return t.replace(tzinfo=timezone.utc)
        return t
    items.sort(key=_key, reverse=True)
    items = items[:limit]
    # Serialize timestamps last.
    for it in items:
        if hasattr(it.get("timestamp"), "isoformat"):
            it["timestamp"] = it["timestamp"].isoformat()

    total = (await db.ad_impressions.count_documents({"served_at": {"$gte": cutoff}})
                  + await db.openrtb_auctions.count_documents({"ran_at": {"$gte": cutoff}}))
    return {"items": items, "total_in_window": total,
                  "window_seconds": window_seconds}

