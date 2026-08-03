"""Phase 12c — Strike accumulation engine.

A "strike" is any moderation / fraud / abuse flag with severity:
    low | medium | high

Thresholds (configurable later via safety_settings):
    3 medium in 30d  → mute (chat/UGC disabled for 24h)
    1 high           → suspend 7d
    3 high           → suspend 30d

Each strike upserts into:
    users.strikes_summary = {
        low, medium, high, total,
        last_strike_at, mute_until?, suspend_until?
    }
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("bigfm.strikes")

SEVERITY_WEIGHTS = {"low": 0, "medium": 1, "high": 3}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_strike_indexes(db) -> None:
    await db.strike_events.create_index(
        [("user_id", 1), ("created_at", -1)])
    await db.strike_events.create_index("source")
    await db.safety_admin_audit.create_index(
        [("target_user_id", 1), ("created_at", -1)])


async def record_strike(db, *, user_id: str, severity: str, source: str,
                                    reason: str, ref_type: str | None = None,
                                    ref_id: str | None = None) -> dict:
    """Record a strike and update users.strikes_summary.  Returns the
    fresh summary including any mute/suspend escalations triggered."""
    if severity not in ("low", "medium", "high"):
        raise ValueError(f"severity must be low|medium|high, got {severity}")
    now = _now()
    strike_id = f"strk_{uuid.uuid4().hex[:14]}"
    await db.strike_events.insert_one({
        "_id": strike_id, "strike_id": strike_id,
        "user_id": user_id, "severity": severity, "source": source,
        "reason": reason, "ref_type": ref_type, "ref_id": ref_id,
        "created_at": now,
    })

    user = await db.users.find_one(
        {"user_id": user_id}, {"strikes_summary": 1, "_id": 1}) or {}
    summary = user.get("strikes_summary") or {
        "low": 0, "medium": 0, "high": 0, "total": 0}
    summary[severity] = int(summary.get(severity, 0)) + 1
    summary["total"] = int(summary.get("total", 0)) + 1
    summary["last_strike_at"] = now

    # Rolling 30-day counts for escalation
    cutoff = now - timedelta(days=30)
    medium_30d = await db.strike_events.count_documents(
        {"user_id": user_id, "severity": "medium",
          "created_at": {"$gte": cutoff}})
    high_30d = await db.strike_events.count_documents(
        {"user_id": user_id, "severity": "high",
          "created_at": {"$gte": cutoff}})
    summary["medium_30d"] = medium_30d
    summary["high_30d"] = high_30d

    escalation = None
    user_set: dict = {"strikes_summary": summary}
    # 3 medium in 30d → mute 24h
    if medium_30d >= 3:
        mute_until = now + timedelta(hours=24)
        summary["mute_until"] = mute_until
        user_set["mute_until"] = mute_until
        escalation = "mute_24h"
    # 1 high → suspend 7d
    if high_30d >= 1:
        days = 30 if high_30d >= 3 else 7
        suspended_until = now + timedelta(days=days)
        summary["suspend_until"] = suspended_until
        user_set["suspended_until"] = suspended_until
        user_set["suspended_reason"] = f"auto_strike_high_{high_30d}"
        escalation = f"suspend_{days}d"
    await db.users.update_one({"user_id": user_id}, {"$set": user_set})
    if escalation:
        # Terminate active sessions on suspend
        if escalation.startswith("suspend"):
            await db.sessions.delete_many({"user_id": user_id})
        logger.info(f"strike escalation user={user_id} → {escalation}")
    return {"strike_id": strike_id, "severity": severity,
              "summary": summary, "escalation": escalation}
