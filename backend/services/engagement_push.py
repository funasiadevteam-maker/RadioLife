"""Phase 18c — 5-min-before-bucket engagement push.

Web-push (VAPID) for the React app.  FCM/APNs are MOCKED — only the web-push
path is live.  Demo / test / admin accounts are excluded by default
(PUSH_ENABLE_DEMO_USERS=true to override).

Bucket flips come from the existing time-aware autoplay buckets:
  morning_commute → mid_morning → lunch_local → afternoon_drive
  → evening_chill → night_lounge → late_night → morning_commute

`tick()` runs every 60s and pushes anyone whose next flip is in [4m, 6m].
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("bigfm.push18c")

_BUCKET_ORDER = [
    (5,  "morning_commute"), (10, "mid_morning"), (12, "lunch_local"),
    (15, "afternoon_drive"), (18, "evening_chill"), (21, "night_lounge"),
    (23, "late_night"),
]
QUIET_START_H = 22
QUIET_END_H   = 7
MAX_PUSHES_PER_DAY = 3
MIN_MIN_BETWEEN     = 90

EXCLUDED_EMAILS = {"demo@bigfm.dubai", "test@bigfm.dubai", "admin@bigfm.dubai"}


def _now_utc():
    return datetime.now(timezone.utc)


def next_bucket_flip(now: Optional[datetime] = None) -> tuple[datetime, str]:
    """Return (when_utc, bucket_label) of the next bucket boundary."""
    now = now or _now_utc()
    today = now.replace(minute=0, second=0, microsecond=0)
    for h, label in _BUCKET_ORDER:
        when = today.replace(hour=h)
        if when > now:
            return when, label
    # Wrap to next-day morning commute.
    return (today + timedelta(days=1)).replace(hour=_BUCKET_ORDER[0][0]), \
              _BUCKET_ORDER[0][1]


def _in_quiet_hours(local_dt: datetime) -> bool:
    h = local_dt.hour
    if QUIET_START_H > QUIET_END_H:   # 22 → 7 wraps midnight
        return h >= QUIET_START_H or h < QUIET_END_H
    return QUIET_START_H <= h < QUIET_END_H


def _user_excluded(user: dict) -> bool:
    if os.environ.get("PUSH_ENABLE_DEMO_USERS") == "true":
        return False
    email = (user.get("email") or "").lower()
    return email in EXCLUDED_EMAILS or bool(user.get("is_demo"))


async def candidates(db, *, now: Optional[datetime] = None,
                                  lookahead_min: int = 6,
                                  lookahead_low_min: int = 4) -> list[dict]:
    """Find users whose next bucket flip lands in [now+4m, now+6m]."""
    now = now or _now_utc()
    flip_at, label = next_bucket_flip(now)
    delta_min = (flip_at - now).total_seconds() / 60.0
    if not (lookahead_low_min <= delta_min <= lookahead_min):
        return []
    cur = db.users.find({"push_enabled": True,
                                      "push_subscription": {"$exists": True}})
    out: list[dict] = []
    async for u in cur:
        if _user_excluded(u):
            continue
        # Frequency caps
        recent = await db.push_log.count_documents({
            "user_id": u.get("user_id"),
            "ts": {"$gte": now - timedelta(hours=24)}})
        if recent >= MAX_PUSHES_PER_DAY:
            continue
        last = await db.push_log.find_one({"user_id": u.get("user_id")},
                                                              sort=[("ts", -1)])
        if last and (now - last["ts"]) < timedelta(minutes=MIN_MIN_BETWEEN):
            continue
        out.append({"user": u, "next_bucket": label,
                          "flip_at": flip_at.isoformat()})
    return out


async def tick(db) -> dict:
    """One scheduler iteration.  Returns `{candidates, sent, errors}`."""
    cands = await candidates(db)
    sent, errs = 0, []
    for c in cands:
        u = c["user"]
        try:
            await _send_web_push(u, c)
            await db.push_log.insert_one({
                "id":           f"push_{u.get('user_id')}_{int(_now_utc().timestamp())}",
                "user_id": u.get("user_id"),
                "bucket":  c["next_bucket"],
                "ts":          _now_utc(),
                "delivery": "web_push",
            })
            sent += 1
        except Exception as e:
            errs.append(f"{u.get('user_id')}: {e}")
    return {"candidates": len(cands), "sent": sent, "errors": errs}


async def _send_web_push(user: dict, payload: dict) -> None:
    """Best-effort web-push.  Imports `pywebpush` lazily so unit tests on
    machines without VAPID keys don't break."""
    vapid_priv = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_pub  = os.environ.get("VAPID_PUBLIC_KEY")
    vapid_aud  = os.environ.get("VAPID_CLAIM_SUB", "mailto:ads@bigfm.dubai")
    if not (vapid_priv and vapid_pub):
        logger.warning("[push18c] VAPID keys missing — push to %s MOCKED",
                              user.get("user_id"))
        return
    try:
        from pywebpush import webpush
        webpush(subscription_info=user["push_subscription"],
                  data=str(payload), vapid_private_key=vapid_priv,
                  vapid_claims={"sub": vapid_aud})
    except Exception as e:
        logger.warning("[push18c] webpush send failed: %s", e)
        raise
