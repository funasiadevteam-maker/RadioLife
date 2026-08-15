"""Combo scheduling ("happy hour") — shared by the pricing engine and the
public combos endpoint so enforcement and display stay in sync."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def combo_active_now(combo: Dict[str, Any]) -> bool:
    """A combo with no schedule is always active. With a schedule, it's active
    only inside the window (store-local tz), and on the selected weekdays."""
    sched = combo.get("schedule") or {}
    if not sched.get("enabled"):
        return True
    try:
        tz = ZoneInfo(sched.get("tz") or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    days = sched.get("days")
    if days and now.weekday() not in days:  # 0=Mon .. 6=Sun
        return False
    start, end = sched.get("start"), sched.get("end")
    if not (start and end):
        return True
    try:
        cur, s, e = now.hour * 60 + now.minute, _mins(start), _mins(end)
    except Exception:
        return True
    return (s <= cur <= e) if s <= e else (cur >= s or cur <= e)


__all__ = ["combo_active_now"]
