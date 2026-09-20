"""FUUSIC Phase 2 — Share-this-break.

Slices the RJ portion of a segment, appends the FUUSIC station-ID stinger, and
saves a public, shareable MP3 at /app/backend/storage/shares/<share_id>.mp3.
The frontend hosts a public landing page at /r/<share_id> with OG meta tags
for WhatsApp/Instagram/Twitter rich previews.

API surface (mounted from server.py):
- POST /api/share/break    (auth) — generate a share from a segment_id
- GET  /api/share/{share_id}/audio  (public) — Range-served MP3
- GET  /api/share/{share_id}/meta   (public) — landing-page metadata for the
                                                React route /r/{share_id}
"""
from __future__ import annotations

import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from audio_pipeline import ffprobe_duration

logger = logging.getLogger("bigfm.share")

DAILY_SHARE_LIMIT = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def slice_break_with_stinger(
    segment_path: str | Path,
    rj_start_sec: float,
    rj_dur_sec: float,
    stinger_path: Optional[str | Path],
    out_path: str | Path,
    pre_pad: float = 1.0,
    post_pad: float = 1.0,
    fade_ms: int = 500,
) -> dict:
    """Slice [rj_start - pre_pad, rj_start + rj_dur + post_pad] from `segment_path`,
    fade in/out, then concat with the stinger (also faded). Output is mono-ready
    192k MP3 stereo for max compatibility.
    """
    start = max(0.0, rj_start_sec - pre_pad)
    duration = rj_dur_sec + pre_pad + post_pad
    fade_s = max(0.05, fade_ms / 1000.0)
    fade_out_start = max(0.0, duration - fade_s)

    inputs = ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(segment_path)]
    n_inputs = 1
    if stinger_path:
        inputs += ["-i", str(stinger_path)]
        n_inputs = 2

    if n_inputs == 2:
        filter_complex = (
            f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"afade=t=in:st=0:d={fade_s:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d={fade_s:.3f}[a0];"
            f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"afade=t=in:st=0:d=0.10,afade=t=out:st=1.2:d=0.30[a1];"
            f"[a0][a1]concat=n=2:v=0:a=1[out]"
        )
    else:
        filter_complex = (
            f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"afade=t=in:st=0:d={fade_s:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d={fade_s:.3f}[out]"
        )
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-ar", "44100", "-ac", "2",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg slice failed (rc={proc.returncode}): {proc.stderr[-2000:]}")
    return {"duration_sec": ffprobe_duration(out_path)}


async def create_share(
    db,
    *,
    user_id: str,
    segment_id: str,
    shares_dir: Path,
    stinger_path: Optional[Path],
) -> dict:
    seg = await db.segments.find_one({"_id": segment_id})
    if not seg:
        raise HTTPException(404, "segment not found")
    rj_start = float(seg.get("rj_start_sec") or 0.0)
    seg_dur = float(seg.get("duration_sec") or 0.0)
    rj_dur = max(2.0, seg_dur - rj_start)
    if rj_dur < 2.0:
        raise HTTPException(400, "segment has no shareable RJ section")

    share_id = uuid.uuid4().hex[:14]
    out_path = shares_dir / f"{share_id}.mp3"
    meta = slice_break_with_stinger(
        seg["file_path"], rj_start, rj_dur,
        str(stinger_path) if stinger_path and stinger_path.exists() else None,
        out_path,
    )

    host_names = [h.get("name") for h in (seg.get("rj_hosts") or [])
                  if h.get("name")] or [seg.get("rj_voice_key", "RJ")]
    channel_slug = seg.get("channel_slug")
    channel_name = None
    if channel_slug:
        ch = await db.channels.find_one({"_id": channel_slug})
        if ch: channel_name = ch.get("name")

    doc = {
        "_id": share_id,
        "share_id": share_id,
        "user_id": user_id,
        "segment_id": segment_id,
        "track_id": seg.get("track_id"),
        "track_title": seg.get("track_title"),
        "track_artist": seg.get("track_artist"),
        "rj_format": seg.get("rj_format"),
        "host_names": host_names,
        "channel_slug": channel_slug,
        "channel_name": channel_name,
        "mp3_filename": out_path.name,
        "duration_sec": meta["duration_sec"],
        "created_at": _now(),
        "view_count": 0,
    }
    await db.shares.insert_one(doc)
    return doc


async def increment_view(db, share_id: str) -> None:
    await db.shares.update_one({"_id": share_id}, {"$inc": {"view_count": 1}})


async def get_share(db, share_id: str) -> Optional[dict]:
    return await db.shares.find_one({"_id": share_id})
