"""Phase 18c — Smart pacing.

For each campaign with both start_date + end_date set, we compare:
    time_progress = (now - start) / (end - start)
    spend_progress = spend_usd / budget_total_usd
to decide whether the campaign is on-pace, ahead (>20% over), or behind.

`pick_weight(campaign, now) → float` returns a multiplier the ad-pick
auction applies to the campaign's bid:
    ahead   → 0.30   (throttle, do not kill)
    on_pace → 1.00
    behind  → 1.50   (boost)
    n_a     → 1.00   (no dates configured)

Takeover SKUs are exempt — the inter-song slot is exclusive in their
window, pacing must not throttle them.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

PACING_AHEAD_THRESHOLD     = 0.20
PACING_THROTTLE_FACTOR     = 0.30
PACING_BOOST_FACTOR          = 1.50


def _parse_iso(s) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def pacing_status(campaign: dict, now: Optional[datetime] = None) -> dict:
    """Return {status: 'on_pace'|'ahead'|'behind'|'n_a',
                      time_progress, spend_progress, projected_eob}."""
    now = now or datetime.now(timezone.utc)
    s = _parse_iso(campaign.get("start_date"))
    e = _parse_iso(campaign.get("end_date"))
    spend = float(campaign.get("spend_usd")          or 0.0)
    budget = float(campaign.get("budget_total_usd") or 0.0)
    if not (s and e and budget > 0):
        return {"status": "n_a", "time_progress": None,
                  "spend_progress": (spend / budget) if budget else 0.0,
                  "projected_eob": None}
    total = max((e - s).total_seconds(), 1.0)
    tp = (now - s).total_seconds() / total
    tp = max(0.0, min(1.0, tp))
    sp = spend / budget
    # Project end-of-budget date if current pace continues.
    projected = None
    if spend > 0 and tp > 0:
        rate_per_sec = spend / max((now - s).total_seconds(), 1.0)
        if rate_per_sec > 0:
            remaining = max(budget - spend, 0)
            secs_to_eob = remaining / rate_per_sec
            projected = (now.timestamp() + secs_to_eob)
    if sp > tp + PACING_AHEAD_THRESHOLD:
        status = "ahead"
    elif sp < tp - PACING_AHEAD_THRESHOLD:
        status = "behind"
    else:
        status = "on_pace"
    return {"status": status, "time_progress": round(tp, 4),
              "spend_progress": round(sp, 4),
              "projected_eob": projected}


def pick_weight(campaign: dict, now: Optional[datetime] = None) -> float:
    # Takeovers are never throttled — they own the slot inside their window.
    tc = campaign.get("takeover_config") or {}
    if tc.get("enabled"):
        return 1.0
    p = pacing_status(campaign, now)
    if p["status"] == "ahead":   return PACING_THROTTLE_FACTOR
    if p["status"] == "behind":  return PACING_BOOST_FACTOR
    return 1.0
