"""Phase 3.8 v2 — Imaging insertion orchestrator.

Decides which imaging assets to insert into the next live segment for a given
user/session/channel, picks files, writes `station_flow_logs`, and updates
session state. The audio_pipeline + server.py wire the actual file paths into
ffmpeg (pre-roll concat + music_bed_path under RJ).

Public surface:
- select_imaging_for_segment(db, ...) → dict with pre_roll_paths + music_bed_path
- log_imaging_inserts(db, segment_id, user_id, session_id, selection)
- prepend_imaging_to_segment(pre_roll_paths, segment_path, out_path) → seconds
- _SESSION_STATE_PROJECTION constant for select queries
"""
from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from audio_pipeline import concat_with_gaps
from services.imaging_rules import (
    _pick_one, _recent_played_ids, pick_music_bed,
    station_slug_for_market,
)

logger = logging.getLogger("bigfm.imaging_insertion")

# --- Cadence constants (env-overridable for test/dev) ---
STATION_ID_MIN_SEC = int(os.environ.get("IMAGING_STATION_ID_MIN_SEC", 15 * 60))   # 15 minutes
STATION_ID_MAX_SEC = int(os.environ.get("IMAGING_STATION_ID_MAX_SEC", 20 * 60))   # 20 minutes
SWEEPER_PROBABILITY = float(os.environ.get("IMAGING_SWEEPER_PROB", 0.5))
FIRST_SEGMENT_BRAND_PROB = float(os.environ.get("IMAGING_FIRST_BRAND_PROB", 1.0))  # default 100% for visibility
TOH_WINDOW_AFTER_HH_SEC = 90   # fire TOH up to 90s past the hour

_SESSION_STATE_PROJECTION = {
    "last_station_id_at": 1,
    "last_top_of_hour_hour": 1,
    "last_daypart_slug": 1,
    "next_segment_sponsor_id": 1,
    "user_id": 1,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dubai_now() -> datetime:
    from datetime import timedelta
    return _now() + timedelta(hours=4)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """MongoDB returns naive UTC datetimes — make them aware so we can subtract."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------- Rule predicates ----------
def _should_play_station_id(last_at: Optional[datetime]) -> bool:
    last_at = _as_aware(last_at)
    if last_at is None:
        # First segment for this session: hi-confidence brand drop so users hear
        # the station identity immediately. Dev/test can override with env var.
        return random.random() < FIRST_SEGMENT_BRAND_PROB
    elapsed = (_now() - last_at).total_seconds()
    if elapsed < STATION_ID_MIN_SEC:
        return False
    if elapsed >= STATION_ID_MAX_SEC:
        return True
    # ramp from 0 → 1 between min and max
    p = (elapsed - STATION_ID_MIN_SEC) / (STATION_ID_MAX_SEC - STATION_ID_MIN_SEC)
    return random.random() < p


def _should_play_top_of_hour(last_hh: Optional[int]) -> bool:
    """Fire TOH once per Dubai-hour, within 90s of the top of the hour."""
    now_dxb = _dubai_now()
    # Outside the 0-90s window after HH:00 → skip
    if now_dxb.minute >= 2:
        return False
    if last_hh is not None and int(last_hh) == int(now_dxb.hour):
        return False
    return True


def _should_play_daypart_opener(prev_daypart: Optional[str], current_daypart: str) -> bool:
    if not prev_daypart:
        return False  # first segment of a session — no transition yet
    return prev_daypart != current_daypart


# ---------- Selection ----------
async def select_imaging_for_segment(
    db,
    *,
    user_id: Optional[str],
    session_id: Optional[str],
    market: str,
    daypart: str,
    energy: str,
    is_premium: bool = False,
    channel_slug: Optional[str] = None,
) -> dict:
    """Decide which imaging to insert into the next segment.

    Returns a dict containing:
      - pre_roll_paths: list[Path]  (concat in this order before the segment)
      - pre_roll_assets: list[dict]  (parallel to pre_roll_paths, for logging)
      - music_bed_path: Path | None
      - music_bed_asset: dict | None
      - sponsor_bumper_asset: dict | None
      - transition_types: list[str] (parallel to pre_roll_paths)
      - station_slug: str (the imaging station_slug used)
    """
    station_slug = station_slug_for_market(market)
    out = {
        "pre_roll_paths": [],
        "pre_roll_assets": [],
        "transition_types": [],
        "music_bed_path": None,
        "music_bed_asset": None,
        "sponsor_bumper_asset": None,
        "station_slug": station_slug,
        "fired_top_of_hour": False,
        "fired_daypart_opener": False,
        "fired_station_id": False,
        "fired_sweeper": False,
        "fired_sponsor": False,
    }

    # --- session state ---
    last_station_id_at = None
    last_toh_hour = None
    last_daypart = None
    sponsor_id = None
    if session_id:
        sess = await db.radio_sessions.find_one({"_id": session_id}, _SESSION_STATE_PROJECTION)
        if sess:
            last_station_id_at = sess.get("last_station_id_at")
            last_toh_hour = sess.get("last_top_of_hour_hour")
            last_daypart = sess.get("last_daypart_slug")
            sponsor_id = sess.get("next_segment_sponsor_id")

    # --- 1) Top-of-hour (highest priority) ---
    toh_asset = None
    if _should_play_top_of_hour(last_toh_hour):
        toh_asset = await _pick_one(db, station_slug=station_slug,
                                     asset_type="top_of_hour", user_id=user_id)
        if toh_asset:
            out["pre_roll_paths"].append(Path(toh_asset["file_path"]))
            out["pre_roll_assets"].append(toh_asset)
            out["transition_types"].append("preroll.top_of_hour")
            out["fired_top_of_hour"] = True

    # --- 2) Daypart opener (if daypart just changed) ---
    if _should_play_daypart_opener(last_daypart, daypart):
        do_asset = await _pick_one(db, station_slug=station_slug,
                                    asset_type="daypart_opener",
                                    user_id=user_id, extra={"daypart": daypart})
        if do_asset:
            out["pre_roll_paths"].append(Path(do_asset["file_path"]))
            out["pre_roll_assets"].append(do_asset)
            out["transition_types"].append("preroll.daypart_opener")
            out["fired_daypart_opener"] = True

    # --- 3) Station ID (15-20 min cadence, OR premium variant for premium users on premium channels) ---
    if not out["fired_top_of_hour"] and _should_play_station_id(last_station_id_at):
        sid_type = "brand_id_short"
        # Premium users on the VIP lounge get the premium_id stinger sometimes (50%)
        if is_premium and channel_slug == "vip_lounge" and random.random() < 0.5:
            sid_type = "premium_id"
        sid_asset = await _pick_one(db, station_slug=station_slug,
                                     asset_type=sid_type, user_id=user_id)
        if sid_asset:
            out["pre_roll_paths"].append(Path(sid_asset["file_path"]))
            out["pre_roll_assets"].append(sid_asset)
            out["transition_types"].append(f"preroll.{sid_type}")
            out["fired_station_id"] = True

    # --- 4) Sponsor bumper (only if session.next_segment_sponsor_id is set) ---
    if sponsor_id:
        sb_asset = await _pick_one(db, station_slug=station_slug,
                                    asset_type="sponsor_bumper", user_id=user_id)
        if sb_asset:
            out["pre_roll_paths"].append(Path(sb_asset["file_path"]))
            out["pre_roll_assets"].append(sb_asset)
            out["transition_types"].append("preroll.sponsor_bumper")
            out["sponsor_bumper_asset"] = sb_asset
            out["fired_sponsor"] = True

    # --- 5) Sweeper between imaging and the song (50/50, only if we DID prepend imaging) ---
    if out["pre_roll_paths"] and random.random() < SWEEPER_PROBABILITY:
        sw_asset = await _pick_one(db, station_slug=station_slug,
                                    asset_type="sweeper_short", user_id=user_id)
        if sw_asset:
            out["pre_roll_paths"].append(Path(sw_asset["file_path"]))
            out["pre_roll_assets"].append(sw_asset)
            out["transition_types"].append("preroll.sweeper")
            out["fired_sweeper"] = True

    # --- 6) Music bed under RJ (always pick if available) ---
    bed_asset = await pick_music_bed(db, station_slug=station_slug, energy=energy)
    if bed_asset and bed_asset.get("file_path") and Path(bed_asset["file_path"]).exists():
        out["music_bed_path"] = Path(bed_asset["file_path"])
        out["music_bed_asset"] = bed_asset

    return out


# ---------- Session state update ----------
async def commit_imaging_state(db, *, session_id: str, selection: dict, daypart: str) -> None:
    """Persist 'last_*' fields back to the session doc so the next segment's
    rule predicates see the right state."""
    if not session_id:
        return
    update = {"last_daypart_slug": daypart}
    if selection.get("fired_station_id") or selection.get("fired_top_of_hour"):
        update["last_station_id_at"] = _now()
    if selection.get("fired_top_of_hour"):
        update["last_top_of_hour_hour"] = _dubai_now().hour
    if selection.get("fired_sponsor"):
        # Clear the one-shot sponsor flag now that we've fired it
        update["next_segment_sponsor_id"] = None
    try:
        await db.radio_sessions.update_one({"_id": session_id}, {"$set": update})
    except Exception as e:
        logger.warning(f"commit_imaging_state error: {e}")


# ---------- Flow logging ----------
async def log_imaging_inserts(
    db, *, segment_id: str, user_id: Optional[str], session_id: Optional[str],
    selection: dict,
) -> int:
    """Write one row to station_flow_logs per inserted asset (pre-roll + bed).
    Returns count of rows inserted. value_cents pre-priced per item_type
    (Phase 4 revenue meter)."""
    # Phase 4 — Imaging slot value rate card.
    IMAGING_VALUE_CENTS = {
        "imaging.brand_id_short":  0,
        "imaging.brand_id_long":   0,
        "imaging.sweeper_short":   0,
        "imaging.daypart_opener":  0,
        "imaging.top_of_hour":     0,
        "imaging.music_bed":       0,
        "imaging.sponsor_bumper":  50,   # $0.50 per impression (paired with sponsor read)
        "imaging.premium_id":      0,
        "imaging.legal_id":        0,
    }
    rows = []
    now = _now()
    for asset, t_type in zip(selection.get("pre_roll_assets", []),
                              selection.get("transition_types", [])):
        item_type = f"imaging.{asset.get('asset_type')}"
        rows.append({
            "user_id": user_id,
            "session_id": session_id,
            "segment_id": segment_id,
            "station_slug": asset.get("station_slug"),
            "asset_id": str(asset.get("_id")),
            "asset_type": asset.get("asset_type"),
            "asset_slug": asset.get("slug"),
            "item_type": item_type,
            "transition_type": t_type,
            "loudness_lufs": asset.get("loudness_lufs"),
            "duration_sec": float(asset.get("duration_sec") or 0.0),
            "value_cents": IMAGING_VALUE_CENTS.get(item_type, 0),
            "played_at": now,
        })
    bed = selection.get("music_bed_asset")
    if bed:
        rows.append({
            "user_id": user_id, "session_id": session_id, "segment_id": segment_id,
            "station_slug": bed.get("station_slug"),
            "asset_id": str(bed.get("_id")),
            "asset_type": "music_bed",
            "asset_slug": bed.get("slug"),
            "item_type": "imaging.music_bed",
            "transition_type": "underlay.rj",
            "loudness_lufs": bed.get("loudness_lufs"),
            "duration_sec": float(bed.get("duration_sec") or 0.0),
            "value_cents": 0,
            "played_at": now,
        })
    if not rows:
        return 0
    try:
        await db.station_flow_logs.insert_many(rows)
    except Exception as e:
        logger.warning(f"log_imaging_inserts error: {e}")
        return 0
    return len(rows)


# ---------- Pre-roll concat ----------
def prepend_imaging_to_segment(
    pre_roll_paths: List[Path],
    segment_path: Path,
    out_path: Path,
) -> float:
    """Concatenate the pre-roll assets in order, then append the (already-built)
    segment file. Tight 80ms gap to avoid harsh edits but keep momentum.
    Returns the new total duration_sec.
    Caller passes the SAME path as segment_path and out_path safely (uses tmp).
    """
    if not pre_roll_paths:
        return 0.0  # caller falls back to original segment unchanged
    parts: List[Path] = [Path(p) for p in pre_roll_paths if Path(p).exists()]
    if not parts:
        return 0.0
    parts.append(Path(segment_path))
    out_path = Path(out_path)
    if out_path.resolve() == Path(segment_path).resolve():
        tmp = out_path.with_suffix(".preroll.tmp.mp3")
        meta = concat_with_gaps(parts, tmp, gap_ms=80)
        tmp.replace(out_path)
    else:
        meta = concat_with_gaps(parts, out_path, gap_ms=80)
    return float(meta.get("duration_sec") or 0.0)
