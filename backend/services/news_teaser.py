"""Phase 40 Session 2 — Cross-channel news teaser picker.

Returns a 1-sentence headline teaser for a listener when:
  • user has explicit `interests` set (no inference)
  • a fresh article (<2h old) matches any interest
  • last_news_teaser_at older than 1 hour (frequency cap)

No clock times allowed in the teaser text — caller assembles via
persona script; this picker only returns the raw headline + bucket
(`breaking_just_now` / `in_the_last_hour` / `this_morning`).
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("bigfm.news_teaser")

TEASER_COOLDOWN_HOURS = 1
FRESH_WINDOW_HOURS    = 2


def _now() -> datetime: return datetime.now(timezone.utc)


def _bucket_for(pub_dt: datetime) -> str:
    age_min = (_now() - pub_dt).total_seconds() / 60.0
    if age_min < 15:  return "breaking_just_now"
    if age_min < 60:  return "in_the_last_hour"
    return "this_morning"


async def pick_news_teaser_for_user(db, user_id: str) -> Optional[dict]:
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return None
    interests = user.get("interests") or []
    if not interests:
        return None
    # Frequency cap
    last_at = user.get("last_news_teaser_at")
    if last_at:
        try:
            dt = datetime.fromisoformat(last_at) if isinstance(last_at, str) else last_at
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            if _now() - dt < timedelta(hours=TEASER_COOLDOWN_HOURS):
                return None
        except Exception:
            pass

    # Match any interest (categories array overlap)
    cutoff = (_now() - timedelta(hours=FRESH_WINDOW_HOURS))
    cur = db.news_articles.find({
        "categories":      {"$in": [str(i).lower() for i in interests]},
        "summary_script": {"$nin": [None, ""]},
    }).sort("pubDate", -1).limit(20)

    chosen: Optional[dict] = None
    async for r in cur:
        pub = r.get("pubDate")
        try:
            pub_dt = datetime.strptime(pub, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) \
                     if isinstance(pub, str) and len(pub) >= 19 else None
        except Exception:
            pub_dt = None
        if not pub_dt or pub_dt < cutoff:
            continue
        chosen = r
        break

    if not chosen:
        return None

    # Stamp the cooldown — best-effort.
    try:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_news_teaser_at": _now().isoformat()}})
    except Exception as e:
        log.warning("[teaser] cooldown stamp failed: %s", e)

    bucket = _bucket_for(pub_dt) if pub_dt else "this_morning"
    return {
        "news_id":     chosen.get("news_id"),
        "title":       chosen.get("title"),
        "source_name": chosen.get("source_name") or chosen.get("source_id"),
        "categories":  chosen.get("categories") or [],
        "freshness_bucket": bucket,  # never an actual clock time
        "deep_link":   f"/news/{chosen.get('news_id')}",
    }
