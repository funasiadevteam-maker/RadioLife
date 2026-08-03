"""Phase 39 Session 3 — Premium / trial gating helper.

Single source of truth for "is this user allowed to use premium features?"
Used by persona-settings, radio-engine premium gates, skip limits, etc.

Trial lifecycle:
  • A user starts a trial → users.trial_started_at = now, trial_ends_at = now+7d,
      subscription_status = "trial"
  • While trial_ends_at > now → counted as premium-or-trial
  • Past trial_ends_at → eventually flipped to "free" by either the on-read
      `flip_expired_trial(user)` call OR the daily sweep cron

Anti-abuse: at most one trial per `TRIAL_REPEAT_DAYS` (365) days.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("bigfm.premium_gate")

TRIAL_DURATION_DAYS = 7
TRIAL_REPEAT_DAYS    = 365


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(s) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_premium_or_trial(user: dict) -> bool:
    """Pure predicate — does NOT mutate the user row.  Honors the legacy
    `is_premium` boolean AND `subscription.status in (active|trialing)`
    AND the Phase 39 `subscription_status == 'trial' + trial_ends_at > now`
    path.  If trial_ends_at has passed, this returns False — but the row
    isn't actually flipped to 'free' until `flip_expired_trial` runs."""
    if not user:
        return False
    if user.get("is_premium"):
        return True
    sub = user.get("subscription") or {}
    if sub.get("status") in ("active", "trialing"):
        return True
    if user.get("subscription_status") == "premium":
        return True
    if user.get("subscription_status") == "trial":
        ends = _parse_dt(user.get("trial_ends_at"))
        if ends and ends > _now():
            return True
    return False


def trial_remaining_seconds(user: dict) -> int:
    """How many seconds remain on this user's trial.  Returns 0 if no
    active trial.  Used for the UI countdown badge."""
    if not user or user.get("subscription_status") != "trial":
        return 0
    ends = _parse_dt(user.get("trial_ends_at"))
    if not ends:
        return 0
    delta = (ends - _now()).total_seconds()
    return max(0, int(delta))


async def flip_expired_trial(db, user_id: str) -> bool:
    """Idempotent — atomic conditional update.  Flips subscription_status
    from 'trial' → 'free' iff trial_ends_at is in the past.  Returns True
    if the flip happened, False otherwise."""
    now_iso = _now().isoformat()
    r = await db.users.update_one(
        {"user_id":  user_id,
          "subscription_status":  "trial",
          "trial_ends_at":          {"$lte": now_iso}},
        {"$set": {"subscription_status":  "free",
                          "trial_ended_at":          now_iso}})
    return bool(getattr(r, "modified_count", 0))


async def sweep_expired_trials(db) -> int:
    """Daily cron entry-point.  Returns the number of rows flipped."""
    now_iso = _now().isoformat()
    r = await db.users.update_many(
        {"subscription_status":  "trial",
          "trial_ends_at":          {"$lte": now_iso}},
        {"$set": {"subscription_status":  "free",
                          "trial_ended_at":          now_iso,
                          "trial_swept_at":          now_iso}})
    n = getattr(r, "modified_count", 0)
    if n:
        log.info("[premium_gate] sweep_expired_trials flipped %d rows", n)
    return n


async def can_start_trial(db, user: dict) -> tuple[bool, Optional[str]]:
    """Returns (allowed, reason_if_blocked)."""
    if not user:
        return False, "no_user"
    if user.get("is_premium") or \
          (user.get("subscription") or {}).get("status") in ("active", "trialing") or \
          user.get("subscription_status") == "premium":
        return False, "already_premium"
    if user.get("subscription_status") == "trial":
        return False, "trial_already_active"
    last_start = _parse_dt(user.get("trial_started_at"))
    if last_start:
        cutoff = _now() - timedelta(days=TRIAL_REPEAT_DAYS)
        if last_start > cutoff:
            return False, "trial_within_repeat_window"
    return True, None


async def start_trial(db, user_id: str) -> dict:
    """Atomic.  Caller must have already checked `can_start_trial`."""
    now = _now()
    now_iso = now.isoformat()
    ends_iso = (now + timedelta(days=TRIAL_DURATION_DAYS)).isoformat()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"subscription_status":  "trial",
                          "trial_started_at":      now_iso,
                          "trial_ends_at":          ends_iso}})
    return {"subscription_status": "trial",
                  "trial_started_at":      now_iso,
                  "trial_ends_at":          ends_iso}


def apply_settings_to_prompt(prompt: str, settings: Optional[dict]) -> str:
    """Append slider directives to the persona prompt.  Midpoint (5) is
    no-op so we don't bloat tokens unnecessarily."""
    if not settings:
        return prompt
    directives: list[str] = []
    h = int(settings.get("humor",  5) or 5)
    e = int(settings.get("energy", 5) or 5)
    s = int(settings.get("slang",  5) or 5)
    if h >= 8: directives.append("Be noticeably funnier than baseline. Light wordplay welcome.")
    elif h <= 2: directives.append("Be drier and more straight-laced — minimal humor.")
    if e >= 8: directives.append("Maximum energy — punchy, urgent, alive.")
    elif e <= 2: directives.append("Low-key delivery — calm, slow, intimate.")
    if s >= 8: directives.append("Use plenty of colloquial / street-level language and code-switching.")
    elif s <= 2: directives.append("Stick to clean, formal phrasing.")
    if not directives:
        return prompt
    return prompt + "\n\nStyle directives:\n- " + "\n- ".join(directives)
