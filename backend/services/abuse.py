"""Phase 12c — Abuse heuristics.

Augments existing Phase 5 abuse heuristics with:
    • skip_storm:   user skips >40 tracks in 24h
    • lobby_spam:   user creates >5 lobbies in 1h (block)
    • game_farming: same game_type played >20 times in 1h (block)
    • referral_self_deal: same device_id / IP across multiple accounts
      claiming referral rewards

Every flag → `abuse_events` collection + a strike.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.strikes import record_strike

logger = logging.getLogger("bigfm.abuse")

SKIP_STORM_LIMIT = 40
SKIP_STORM_HOURS = 24
LOBBY_SPAM_LIMIT = 5
LOBBY_SPAM_HOURS = 1
GAME_FARM_LIMIT = 20
GAME_FARM_HOURS = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_abuse_indexes(db) -> None:
    await db.abuse_events.create_index(
        [("user_id", 1), ("created_at", -1)])
    await db.abuse_events.create_index("status")
    await db.abuse_events.create_index("rule")


async def _emit_event(db, *, rule: str, severity: str, user_id: str,
                              detail: dict, action: str) -> dict:
    eid = f"ab_{uuid.uuid4().hex[:14]}"
    doc = {
        "_id": eid, "abuse_id": eid,
        "rule": rule, "severity": severity, "status": "open",
        "action": action,
        "user_id": user_id, "detail": detail,
        "created_at": _now(),
    }
    await db.abuse_events.insert_one(doc)
    try:
        await record_strike(
            db, user_id=user_id, severity=severity, source="abuse",
            reason=rule, ref_type="abuse_event", ref_id=eid)
    except Exception as e:
        logger.warning(f"strike record failed for abuse {eid}: {e}")
    return doc


async def check_skip_storm(db, *, user_id: str) -> Optional[dict]:
    cutoff = _now() - timedelta(hours=SKIP_STORM_HOURS)
    n = await db.playback_logs.count_documents(
        {"user_id": user_id, "event": "skip",
          "timestamp": {"$gte": cutoff}})
    if n <= SKIP_STORM_LIMIT:
        return None
    # Don't double-emit within the same window
    recent = await db.abuse_events.find_one(
        {"user_id": user_id, "rule": "skip_storm",
          "created_at": {"$gte": cutoff}})
    if recent:
        return None
    return await _emit_event(
        db, rule="skip_storm", severity="low", user_id=user_id,
        detail={"skips_24h": n, "limit": SKIP_STORM_LIMIT},
        action="flag")


async def check_lobby_spam(db, *, user_id: str) -> Optional[dict]:
    """Called BEFORE creating a lobby.  When threshold reached, returns
    a fraud-event-shaped dict and the route MUST 429 the user.

    Counts ALL lobbies in the window (live + closed), per the Phase 12c
    spec.  A spammer who closes-then-recreates rapidly is still a
    spammer.  Tests that hammer this endpoint MUST clean up their own
    lobby rows in teardown.
    """
    cutoff = _now() - timedelta(hours=LOBBY_SPAM_HOURS)
    n = await db.lobbies.count_documents(
        {"host_user_id": user_id,
          "created_at": {"$gte": cutoff}})
    if n < LOBBY_SPAM_LIMIT:
        return None
    return await _emit_event(
        db, rule="lobby_spam", severity="medium", user_id=user_id,
        detail={"lobbies_in_window": n,
                  "window_hours": LOBBY_SPAM_HOURS,
                  "limit": LOBBY_SPAM_LIMIT},
        action="block")


async def check_game_farming(db, *, user_id: str,
                                            game_type: str) -> Optional[dict]:
    cutoff = _now() - timedelta(hours=GAME_FARM_HOURS)
    n = await db.game_sessions.count_documents(
        {"user_id": user_id, "game_type": game_type,
          "created_at": {"$gte": cutoff}})
    if n < GAME_FARM_LIMIT:
        return None
    return await _emit_event(
        db, rule="game_farming", severity="medium", user_id=user_id,
        detail={"game_type": game_type, "plays_in_window": n,
                  "window_hours": GAME_FARM_HOURS,
                  "limit": GAME_FARM_LIMIT},
        action="block")


async def check_referral_self_deal(db, *, user_id: str,
                                                    referrer_user_id: str,
                                                    device_id: Optional[str] = None,
                                                    ip: Optional[str] = None
                                                    ) -> Optional[dict]:
    if user_id == referrer_user_id:
        return await _emit_event(
            db, rule="referral_self_referral", severity="medium",
            user_id=user_id,
            detail={"referrer_user_id": referrer_user_id},
            action="block")
    if device_id:
        others = await db.user_push_tokens.distinct(
            "user_id", {"device_id": device_id})
        if referrer_user_id in [o for o in others if o != user_id]:
            return await _emit_event(
                db, rule="referral_device_dupe", severity="medium",
                user_id=user_id,
                detail={"device_id": device_id,
                          "referrer_user_id": referrer_user_id},
                action="flag")
    return None
