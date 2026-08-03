"""Phase B — Podcast episode progress tracking.

Owns:
  * `podcast_progress` collection — per (user, episode) resume position +
      completion state.
  * `podcast_completed` trigger emitter — fires exactly once when the user
      crosses the 90% completion threshold on an episode.
  * play_count increment on the podcast_episodes doc — first ping per
      (user, episode) counts once.

Idempotency contract:
  * Progress upsert keyed on (user_id, episode_id) — unique index.
  * `completion_dispatched_at` marker guards the `podcast_completed`
      trigger — dispatched once even if the client keeps pinging past 90%.
  * `first_started_at` set on insert, never overwritten.
  * play_count increments only when the row is FIRST inserted for that
      (user, episode) — subsequent updates don't double-count.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("bigfm.podcast_progress")

COMPLETION_THRESHOLD = 0.90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


async def ensure_podcast_progress_indexes(db) -> None:
    try:
        await db.podcast_progress.create_index(
            [("user_id", 1), ("episode_id", 1)], unique=True,
            name="pp_user_ep_uniq")
        await db.podcast_progress.create_index(
            [("user_id", 1), ("last_played_at", -1)],
            name="pp_user_recent")
        await db.podcast_progress.create_index("podcast_id")
        await db.podcast_progress.create_index("completion_dispatched_at",
                                                                                          sparse=True)
    except Exception as e:
        logger.warning("[pp] index setup: %s", e)


async def get_progress(db, *, user_id: str, episode_id: str
                                              ) -> Optional[Dict[str, Any]]:
    row = await db.podcast_progress.find_one(
        {"user_id": user_id, "episode_id": episode_id})
    if not row:
        return None
    row.pop("_id", None)
    for k in ("first_started_at", "last_played_at",
                      "completion_dispatched_at", "completed_at"):
        v = row.get(k)
        if isinstance(v, datetime):
            row[k] = v.isoformat()
    return row


async def record_progress(db, *, user_id: str, episode_id: str,
                                                    position_seconds: float,
                                                    duration_seconds: Optional[float] = None
                                                    ) -> Dict[str, Any]:
    """Idempotent progress upsert.  Returns the persisted row.

    Fires `podcast_completed` trigger exactly once per (user, episode)
    when the user first crosses 90% completion.  Silent-on-error trigger
    dispatch — never blocks the progress write.
    """
    if position_seconds is None or position_seconds < 0:
        raise ValueError("invalid_position")
    # Resolve the episode + parent channel — needed for the payload and
    # to reject unknown episode ids fast.
    ep = await db.podcast_episodes.find_one(
        {"id": episode_id},
        {"id": 1, "channel_id": 1, "duration_seconds": 1,
          "title": 1, "publish_status": 1})
    if not ep:
        raise ValueError("episode_not_found")
    # Use the SERVER's known duration when the client didn't supply one.
    dur = duration_seconds if (duration_seconds and duration_seconds > 0) \
                else float(ep.get("duration_seconds") or 0)
    now = _now()
    completed_now = bool(dur and (position_seconds / dur >= COMPLETION_THRESHOLD))
    # Snapshot pre-existing row so we can detect the "first time crossed"
    # transition and set setOnInsert vs setOn every-write fields correctly.
    prior = await db.podcast_progress.find_one(
        {"user_id": user_id, "episode_id": episode_id})
    is_new = prior is None
    was_completed = bool(prior and prior.get("completed"))
    already_dispatched = bool(prior and prior.get("completion_dispatched_at"))

    set_on_insert = {
        "_id":                          _gen("ppg"),
        "user_id":                    user_id,
        "episode_id":              episode_id,
        "podcast_id":              ep.get("channel_id"),
        "first_started_at":  now,
    }
    set_fields: Dict[str, Any] = {
        "position_seconds":  float(position_seconds),
        "duration_seconds": float(dur) if dur else None,
        "last_played_at":    now,
    }
    if completed_now:
        set_fields["completed"]      = True
        if not was_completed:
            set_fields["completed_at"] = now

    await db.podcast_progress.update_one(
        {"user_id": user_id, "episode_id": episode_id},
        {"$setOnInsert": set_on_insert,
          "$set": set_fields},
        upsert=True)

    # First-ping-per-user bump: increment play_count on the episode only
    # when THIS row was newly inserted.
    if is_new:
        try:
            await db.podcast_episodes.update_one(
                {"id": episode_id},
                {"$inc": {"play_count": 1}})
        except Exception as e:
            logger.warning("[pp] play_count inc failed: %s", e)

    # Dispatch `podcast_completed` exactly once per (user, episode) when
    # transitioning across the 90% line.
    dispatched = False
    if completed_now and not already_dispatched:
        # Race-guard: only stamp+dispatch if no other worker already did.
        _res = await db.podcast_progress.find_one_and_update(
            {"user_id": user_id, "episode_id": episode_id,
              "completion_dispatched_at": {"$exists": False}},
            {"$set": {"completion_dispatched_at": now}})
        if _res is not None:
            dispatched = True
            try:
                await db.podcast_episodes.update_one(
                    {"id": episode_id},
                    {"$inc": {"completed_count": 1}})
            except Exception as e:
                logger.warning("[pp] completed_count inc failed: %s", e)
            try:
                from services.notification_trigger_dispatcher import dispatch_event
                await dispatch_event(
                    db, event_name="podcast_completed",
                    user_id=user_id,
                    payload={"episode_id":            episode_id,
                                      "podcast_id":            ep.get("channel_id"),
                                      "title":                      ep.get("title"),
                                      "duration_seconds": float(dur) if dur else None})
            except Exception as e:
                logger.warning("[pp] dispatch failed: %s", e)
            # Phase G — AD.9 Podcast Completion Points award pipeline.
            # Runs INLINE so we can return the resulting awards on the
            # same response for the completion toast.
            try:
                from services.podcast_completion_award_pipeline import (
                    on_podcast_completed as _pc_award)
                _award_result = await _pc_award(
                    db, user_id=user_id, episode_id=episode_id,
                    podcast_id=ep.get("channel_id"),
                    episode_title=ep.get("title"))
            except Exception as e:
                logger.warning("[pp] AD.9 award pipeline failed: %s", e)
                _award_result = {"awards": [], "count": 0}

    row = await db.podcast_progress.find_one(
        {"user_id": user_id, "episode_id": episode_id})
    row.pop("_id", None)
    for k in ("first_started_at", "last_played_at",
                      "completion_dispatched_at", "completed_at"):
        v = row.get(k)
        if isinstance(v, datetime):
            row[k] = v.isoformat()
    row["completion_pct"] = (
        round(min(1.0, position_seconds / dur), 4) if dur else 0.0)
    row["threshold_pct"] = COMPLETION_THRESHOLD
    row["dispatched_now"] = dispatched
    # Phase G — surface awards granted THIS completion so the client
    # can render the "🎉 +N points" completion toast.
    try:
        row["ad9_awards"] = _award_result.get("awards") if dispatched else []
        row["ad9_award_count"] = int(_award_result.get("count") or 0) if dispatched else 0
    except NameError:
        row["ad9_awards"] = []
        row["ad9_award_count"] = 0
    return row


async def continue_listening(db, *, user_id: str, limit: int = 20
                                                        ) -> Dict[str, Any]:
    """Recent-first list of episodes the user has started but NOT completed.
    Per Phase B contract: `completed != true` AND `position_seconds > 0`
    (a fresh row with position 0 does not count as "in progress" yet).
    """
    q = {"user_id": user_id,
          "completed": {"$ne": True},
          "position_seconds": {"$gt": 0}}
    rows = []
    async for r in db.podcast_progress.find(q).sort(
                                  "last_played_at", -1).limit(limit):
        ep = await db.podcast_episodes.find_one(
            {"id": r["episode_id"]},
            {"_id": 0, "id": 1, "channel_id": 1, "title": 1,
              "cover_image_url": 1, "duration_seconds": 1, "published_at": 1})
        ch = None
        if ep:
            ch = await db.podcast_channels.find_one(
                {"id": ep.get("channel_id")},
                {"_id": 0, "id": 1, "title": 1, "slug": 1,
                  "cover_image_url": 1})
        rows.append({
            "episode_id":              r["episode_id"],
            "podcast_id":              r.get("podcast_id"),
            "position_seconds":  float(r.get("position_seconds") or 0),
            "duration_seconds": float(r.get("duration_seconds") or 0),
            "last_played_at":    (r["last_played_at"].isoformat()
                                                    if isinstance(r.get("last_played_at"),
                                                                                datetime)
                                                    else r.get("last_played_at")),
            "episode":                  ep,
            "podcast":                  ch,
        })
    return {"items": rows, "count": len(rows)}


async def episode_analytics(db, *, episode_id: str) -> Dict[str, Any]:
    """Creator-only summary — total plays, completions, avg completion %."""
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep:
        raise ValueError("episode_not_found")
    plays          = int(ep.get("play_count") or 0)
    completions = int(ep.get("completed_count") or 0)
    # Compute mean completion % from progress rows.
    pipe = [
        {"$match": {"episode_id": episode_id,
                              "duration_seconds": {"$gt": 0}}},
        {"$project": {"pct": {"$divide": [
            {"$min": ["$position_seconds", "$duration_seconds"]},
            "$duration_seconds"]}}},
        {"$group": {"_id": None,
                              "avg_pct": {"$avg": "$pct"},
                              "n": {"$sum": 1}}},
    ]
    avg_pct = 0.0
    n_progress = 0
    async for d in db.podcast_progress.aggregate(pipe):
        avg_pct = float(d.get("avg_pct") or 0.0)
        n_progress = int(d.get("n") or 0)
    return {
        "episode_id":                episode_id,
        "plays":                        plays,
        "completions":            completions,
        "unique_listeners":    n_progress,
        "avg_completion_pct": round(avg_pct * 100, 1),
        "completion_rate_pct": round(
            (completions / plays * 100) if plays else 0.0, 1),
    }


async def list_user_subscriptions(db, *, user_id: str,
                                                                  limit: int = 200) -> Dict[str, Any]:
    """User's followed podcast channels — hydrated with channel metadata.
    Alias for AD.9's future consumer + the Phase B listener UI."""
    ids: list[str] = []
    async for r in db.podcast_followers.find(
                {"user_id": user_id}).sort("followed_at", -1).limit(limit):
        ch_id = r.get("channel_id")
        if ch_id:
            ids.append(ch_id)
    if not ids:
        return {"items": [], "count": 0}
    channels = []
    async for c in db.podcast_channels.find({"id": {"$in": ids}}):
        c.pop("_id", None)
        channels.append(c)
    # Preserve follow order (newest first).
    by_id = {c["id"]: c for c in channels}
    ordered = [by_id[i] for i in ids if i in by_id]
    return {"items": ordered, "count": len(ordered)}


async def unfollow_channel(db, *, user_id: str, channel_id: str
                                                    ) -> Dict[str, Any]:
    r = await db.podcast_followers.delete_one(
        {"user_id": user_id, "channel_id": channel_id})
    if r.deleted_count:
        # Best-effort follower_count decrement — floor at 0.
        await db.podcast_channels.update_one(
            {"id": channel_id, "follower_count": {"$gt": 0}},
            {"$inc": {"follower_count": -1}})
    return {"ok": True, "removed": bool(r.deleted_count)}


__all__ = [
    "ensure_podcast_progress_indexes",
    "record_progress",
    "get_progress",
    "continue_listening",
    "episode_analytics",
    "list_user_subscriptions",
    "unfollow_channel",
    "COMPLETION_THRESHOLD",
]
