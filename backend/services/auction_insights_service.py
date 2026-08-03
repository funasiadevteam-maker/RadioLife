"""Phase AD.3 bundle — Auction Transparency service.

Logs LOSER entries when the AD.11 / AD.3 / AD.4 auctions pick a
winner.  Advertisers open the /advertiser/dashboard/auction-insights
page and see the last 24h of lost slots + reason + how to bid higher.

Fire-and-forget: `log_auction_result` is called AFTER the hot path
returns to the client; it must never block or raise into the auction.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.auction_insights")


LOSS_REASONS = (
    "higher_cpm",                    # competitor's CPE/CPM/CPD was higher
    "targeting_mismatch",    # user didn't match this advertiser's targeting
    "wallet_exhausted",        # this advertiser's budget was drained
    "priority_boost_lower",# competitor's priority_score_boost was higher
    "disqualified_creative", # creative not approved / other issue
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


# ─── Indexes ────────────────────────────────────────────────────
async def ensure_auction_indexes(db) -> None:
    try:
        await db.auction_events.create_index("event_id", unique=True)
        await db.auction_events.create_index([
            ("advertiser_id", 1), ("created_at", -1)])
        await db.auction_events.create_index("ad_type")
        # TTL — auto-expire 30 days.
        await db.auction_events.create_index(
            "created_at", expireAfterSeconds=30 * 24 * 3600)
    except Exception as e:
        logger.warning("[auction] index setup: %s", e)


# ─── Logging ────────────────────────────────────────────────────
async def log_auction_result(db, *,
                                                              ad_type: str,
                                                              slot_id: str,
                                                              winner_advertiser_id: Optional[str],
                                                              winner_bid_cents: int,
                                                              losers: List[Dict[str, Any]],
                                                              user_context: Optional[Dict[str, Any]] = None
                                                              ) -> None:
    """`losers` is a list of {advertiser_id, campaign_id, bid_cents,
    reason}.  Silent on failure — must never break the auction."""
    now = _now()
    docs = []
    for l in losers or []:
        docs.append({
            "_id":                                          _gen("aev"),
            "event_id":                                _gen("aev"),
            "ad_type":                                  ad_type,
            "slot_id":                                  slot_id,
            "advertiser_id":                        l.get("advertiser_id"),
            "campaign_id":                          l.get("campaign_id"),
            "reason":                                    l.get("reason") or "higher_cpm",
            "bid_cents":                              int(l.get("bid_cents") or 0),
            "winner_advertiser_id":          winner_advertiser_id,
            "winner_bid_cents":                  int(winner_bid_cents or 0),
            "user_context":                        user_context or {},
            "created_at":                            now,
        })
    if not docs:
        return
    try:
        await db.auction_events.insert_many(docs, ordered=False)
    except Exception as e:
        logger.warning("[auction] insert_many failed: %s", e)


def fire_and_forget(coro):
    """Kick off `coro` on the current loop without awaiting it.  Used
    at hot-path boundaries."""
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running loop — silently drop (edge case in scripts).
        pass


# ─── Query ──────────────────────────────────────────────────────
async def advertiser_insights(db, *, advertiser_id: str,
                                                                  hours: int = 24,
                                                                  limit: int = 100
                                                                  ) -> Dict[str, Any]:
    since = _now() - timedelta(hours=hours)
    rows = []
    async for e in db.auction_events.find(
                {"advertiser_id": advertiser_id,
                  "created_at": {"$gte": since}}
                ).sort("created_at", -1).limit(limit):
        rows.append({
            "event_id":                              e.get("event_id"),
            "ad_type":                                e.get("ad_type"),
            "slot_id":                                e.get("slot_id"),
            "campaign_id":                        e.get("campaign_id"),
            "reason":                                  e.get("reason"),
            "bid_cents":                            int(e.get("bid_cents") or 0),
            "winner_bid_cents":                int(e.get("winner_bid_cents") or 0),
            "shortfall_cents":                max(0,
                                                                                  int(e.get("winner_bid_cents") or 0)
                                                                                    - int(e.get("bid_cents") or 0)),
            "created_at":                          (e.get("created_at").isoformat()
                                                                        if isinstance(e.get("created_at"), datetime)
                                                                        else e.get("created_at")),
        })
    # Group by reason for summary.
    by_reason: Dict[str, int] = {}
    for r in rows:
        by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1
    return {
        "items":                    rows,
        "count":                    len(rows),
        "by_reason":            by_reason,
        "window_hours":      hours,
    }


# ─── One-click boost ────────────────────────────────────────────
async def boost_campaign_bid(db, *,
                                                              ad_type: str,
                                                              campaign_id: str,
                                                              new_bid_cents: int,
                                                              advertiser_id: str,
                                                              require_reapproval_pct: int = 20
                                                              ) -> Dict[str, Any]:
    """Bump the CPE/CPM/CPD on a live campaign.  If the change is
    > require_reapproval_pct percent, the campaign is put back into
    'pending_admin' for ADMOD.1 re-review."""
    if ad_type == "banner":
        # CPM lives inside per_zone_cpm_cents — for boost, we scale
        # ALL zones by the same factor.
        camp = await db.banner_campaigns.find_one(
            {"banner_id": campaign_id, "advertiser_id": advertiser_id})
        if not camp:
            raise ValueError("campaign_not_found")
        current = int((camp.get("per_zone_cpm_cents") or {}).values() and max(camp["per_zone_cpm_cents"].values()) or 0)
        if current == 0:
            raise ValueError("no_current_bid")
        factor = new_bid_cents / current if current > 0 else 1
        new_zones = {z: int(v * factor) for z, v in
                                    (camp.get("per_zone_cpm_cents") or {}).items()}
        change_pct = int(abs(new_bid_cents - current) * 100 / current)
        needs_review = change_pct > require_reapproval_pct
        sets = {"per_zone_cpm_cents": new_zones,
                        "updated_at": _now()}
        if needs_review:
            sets["status"] = "pending_admin"
        await db.banner_campaigns.update_one(
            {"banner_id": campaign_id}, {"$set": sets})
        return {"ok": True, "ad_type": "banner", "campaign_id": campaign_id,
                      "old_bid_cents": current, "new_bid_cents": new_bid_cents,
                      "change_pct": change_pct,
                      "requires_reapproval": needs_review}
    elif ad_type in ("advertiser_pw_sponsorship", "pw_sponsorship"):
        camp = await db.predict_win_sponsorships.find_one(
            {"sponsorship_id": campaign_id, "advertiser_id": advertiser_id})
        if not camp:
            raise ValueError("campaign_not_found")
        field = "cpe_cents" if camp.get("pricing_model") == "per_entry" \
                                else "cpi_cents"
        current = int(camp.get(field) or 0)
        if current == 0:
            raise ValueError("no_current_bid")
        change_pct = int(abs(new_bid_cents - current) * 100 / current)
        needs_review = change_pct > require_reapproval_pct
        sets = {field: int(new_bid_cents), "updated_at": _now()}
        if needs_review:
            sets["status"] = "pending_admin"
        await db.predict_win_sponsorships.update_one(
            {"sponsorship_id": campaign_id}, {"$set": sets})
        return {"ok": True, "ad_type": ad_type,
                      "campaign_id": campaign_id,
                      "field": field, "old_bid_cents": current,
                      "new_bid_cents": new_bid_cents,
                      "change_pct": change_pct,
                      "requires_reapproval": needs_review}
    elif ad_type == "notification":
        camp = await db.notification_campaigns.find_one(
            {"notification_campaign_id": campaign_id,
              "advertiser_id": advertiser_id})
        if not camp:
            raise ValueError("campaign_not_found")
        current = int(camp.get("cost_per_delivery_cents") or 0)
        if current == 0:
            raise ValueError("no_current_bid")
        change_pct = int(abs(new_bid_cents - current) * 100 / current)
        needs_review = change_pct > require_reapproval_pct
        sets = {"cost_per_delivery_cents": int(new_bid_cents),
                        "updated_at": _now()}
        if needs_review:
            sets["status"] = "pending_admin"
        await db.notification_campaigns.update_one(
            {"notification_campaign_id": campaign_id}, {"$set": sets})
        return {"ok": True, "ad_type": "notification",
                      "campaign_id": campaign_id,
                      "old_bid_cents": current, "new_bid_cents": new_bid_cents,
                      "change_pct": change_pct,
                      "requires_reapproval": needs_review}
    raise ValueError(f"unsupported_ad_type:{ad_type}")


__all__ = [
    "ensure_auction_indexes",
    "log_auction_result",
    "fire_and_forget",
    "advertiser_insights",
    "boost_campaign_bid",
    "LOSS_REASONS",
]
