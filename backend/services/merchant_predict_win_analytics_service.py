"""Phase PW-M.1 — Merchant Predict & Win event analytics.

Collection: `merchant_predict_win_analytics`

Event types:
    impression, detail_view, qr_scan, entry, checkin, win,
    redemption, wallet_save, profile_visit, direction_request
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("bigfm.pw_m.analytics")

ALLOWED_EVENT_TYPES = {
    "impression", "detail_view", "qr_scan", "entry", "checkin",
    "win", "redemption", "wallet_save", "profile_visit",
    "direction_request",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def record_event(db, *, merchant_campaign_id: str,
                                                    event_type: str,
                                                    user_id: Optional[str] = None,
                                                    metadata: Optional[Dict[str, Any]] = None
                                                    ) -> Dict[str, Any]:
    if event_type not in ALLOWED_EVENT_TYPES:
        # Silently drop rather than raise — event ingestion is best-effort.
        log.warning("[analytics] drop unknown event_type=%s campaign=%s",
                                event_type, merchant_campaign_id)
        return {"ok": False, "reason": "unknown_event_type"}
    doc = {
        "_id":                                f"mpwan_{uuid.uuid4().hex[:16]}",
        "event_id":                      f"mpwan_{uuid.uuid4().hex[:16]}",
        "merchant_campaign_id": merchant_campaign_id,
        "event_type":                  event_type,
        "user_id":                        user_id,
        "metadata":                      metadata or {},
        "created_at":                  _now(),
    }
    doc["event_id"] = doc["_id"]
    await db.merchant_predict_win_analytics.insert_one(doc)
    return {"ok": True, "event_id": doc["event_id"]}


async def aggregate_campaign(db, *, merchant_campaign_id: str
                                                            ) -> Dict[str, Any]:
    """Return {event_type: count} for a single merchant campaign."""
    pipeline = [
        {"$match": {"merchant_campaign_id": merchant_campaign_id}},
        {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
    ]
    counts = {t: 0 for t in ALLOWED_EVENT_TYPES}
    async for row in db.merchant_predict_win_analytics.aggregate(pipeline):
        counts[row["_id"]] = row["n"]

    # A couple of derived rollups for the UI cards.
    counts["unique_users_estimate"] = await db.merchant_predict_win_analytics \
        .aggregate([{"$match": {"merchant_campaign_id": merchant_campaign_id,
                                                        "user_id": {"$ne": None}}},
                              {"$group": {"_id": "$user_id"}},
                              {"$count": "n"}]) \
        .to_list(length=1)
    counts["unique_users_estimate"] = (counts["unique_users_estimate"][0]["n"]
                                                                                if counts["unique_users_estimate"] else 0)
    return counts
