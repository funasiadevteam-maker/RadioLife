"""Phase 18b — lightweight in-house telemetry.

Drops events into `analytics_events` (no PostHog wired yet — keeping the
hop count low for the preview env).  Front the dashboard at
`/admin/advertiser/analytics` reads aggregates from this collection.

Event shape:
    { id, name, props: {...}, ts, advertiser_id?, creative_id?, user_id? }
"""
from __future__ import annotations
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("bigfm.telemetry")


def _now():
    return datetime.now(timezone.utc)


async def emit_event(db, *, name: str, props: dict,
                                    advertiser_id: Optional[str] = None,
                                    creative_id: Optional[str] = None,
                                    user_id: Optional[str] = None) -> str:
    """Fire-and-forget event log.  Never raises; we drop on DB failure."""
    eid = f"evt_{secrets.token_hex(6)}"
    doc = {
        "id":                eid,
        "name":              name,
        "props":             props or {},
        "advertiser_id":  advertiser_id,
        "creative_id":     creative_id,
        "user_id":          user_id,
        "ts":                  _now(),
    }
    try:
        await db.analytics_events.insert_one(doc)
    except Exception as e:
        logger.warning("[telemetry] dropped %s: %s", name, e)
    return eid


async def aggregate_advertiser_kpis(db, *, days: int = 30) -> dict:
    """Cheap aggregates for the admin analytics dashboard."""
    from datetime import timedelta
    since = _now() - timedelta(days=days)

    # Auto-approve rate: count uploaded events with verdict, group by approved/other.
    cur = db.analytics_events.find(
        {"name": "advertiser_creative_uploaded", "ts": {"$gte": since}},
        {"_id": 0, "props": 1})
    docs = await cur.to_list(5000)
    approved = sum(1 for d in docs if (d["props"].get("verdict") == "approved"))
    review   = sum(1 for d in docs if (d["props"].get("verdict") == "review"))
    rejected = sum(1 for d in docs if (d["props"].get("verdict") == "rejected"))
    ai_count = sum(1 for d in docs if (d["props"].get("source") == "ai_generated"))
    manual_count = sum(1 for d in docs if (d["props"].get("source") == "manual_upload"))
    total = len(docs)

    # Issue-category breakdown.
    cat_counts: dict[str, int] = {}
    for d in docs:
        for issue in (d["props"].get("issues") or []):
            cat = issue.get("category", "unknown")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    # Avg latency by stage.
    stage_totals: dict[str, list[int]] = {}
    for d in docs:
        for k, v in (d["props"].get("stage_latency_ms") or {}).items():
            stage_totals.setdefault(k, []).append(int(v))
    avg_latency = {k: round(sum(v) / max(len(v), 1))
                          for k, v in stage_totals.items()}

    # Manual-review queue depth (live from ad_campaigns).
    queue_depth = await db.ad_campaigns.count_documents(
        {"status": "pending_review"})

    return {
        "range_days":           days,
        "total_uploads":      total,
        "auto_approve_rate":  round(approved / total, 3) if total else 0.0,
        "verdict_counts":     {"approved": approved, "review": review,
                                            "rejected": rejected},
        "source_counts":      {"ai_generated": ai_count,
                                            "manual_upload": manual_count},
        "rejection_categories": cat_counts,
        "stage_latency_ms_avg": avg_latency,
        "pending_review_queue_depth": queue_depth,
    }
