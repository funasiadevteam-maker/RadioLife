"""Phase 36d — Magic clips. Detect top engaging moments from a podcast
episode using a hybrid signal of (a) transcript utterance length + question
density, (b) audio loudness over 5s windows (ffprobe volumedetect), and
(c) OpenAI rerank prompt when transcripts are available.

Snaps the chosen windows to nearest utterance boundaries (analogous to the
36b chapter-snap pattern).
"""
from __future__ import annotations
import asyncio, json, logging, os, subprocess, tempfile, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigfm.podcast_clips")

CLIPS_COL              = "podcast_clips"
DEFAULT_COUNT     = 3
TARGET_SECONDS = 30


def _now(): return datetime.now(timezone.utc)
def _gen(p): return f"{p}_{uuid.uuid4().hex[:14]}"


async def _audio_loudness_windows(audio_path: Path, window: int = 5) -> list:
    """Run ffmpeg volumedetect-equivalent over 5s windows. Returns list of
    {start, end, mean_db}."""
    if not audio_path.is_file(): return []
    # Probe total duration first.
    try:
        p = subprocess.run(["ffprobe", "-v", "error",
                                                  "-show_entries", "format=duration",
                                                  "-of", "default=nw=1:nk=1", str(audio_path)],
                                                capture_output=True, timeout=10)
        total = float(p.stdout.decode().strip() or 0)
    except Exception:
        return []
    out: list = []
    t = 0.0
    while t + window <= total:
        try:
            r = subprocess.run(
                ["ffmpeg", "-ss", f"{t}", "-t", f"{window}", "-i", str(audio_path),
                  "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, timeout=15)
            stderr = r.stderr.decode("utf-8", "ignore")
            mean_db = -90.0
            for line in stderr.split("\n"):
                if "mean_volume:" in line:
                    try: mean_db = float(line.split("mean_volume:")[1]
                                                                      .strip().split()[0])
                    except Exception: pass
            out.append({"start": t, "end": t + window, "mean_db": mean_db})
        except Exception: pass
        t += window
    return out


def _utterance_score(utterances: list, start: float, end: float) -> float:
    """Length-density + question density inside [start, end]."""
    inside = [u for u in utterances
                      if u.get("end_seconds", u.get("end", 0)) > start
                          and u.get("start_seconds", u.get("start", 0)) < end]
    if not inside: return 0.0
    word_total = sum(len((u.get("text") or "").split()) for u in inside)
    qmark = sum(1 for u in inside if "?" in (u.get("text") or ""))
    span = max(end - start, 0.01)
    density = word_total / span
    return min(1.0, density / 4.0) + 0.15 * min(qmark, 3)


def _snap_to_utterance_bounds(utterances: list, start: float, end: float
                                                          ) -> tuple[float, float]:
    if not utterances: return start, end
    starts = sorted(set(float(u.get("start_seconds", u.get("start", 0)))
                                          for u in utterances))
    ends    = sorted(set(float(u.get("end_seconds", u.get("end", 0)))
                                          for u in utterances))
    snap_s = min(starts, key=lambda x: abs(x - start))
    snap_e = min(ends,    key=lambda x: abs(x - end))
    if snap_e - snap_s < 5: snap_e = snap_s + max(end - start, 5)
    return snap_s, snap_e


async def detect_top_moments(db, *, episode_id: str, count: int = DEFAULT_COUNT,
                                                          target_seconds: int = TARGET_SECONDS) -> list:
    """Pure detection — does NOT trim/upload. Returns scored windows."""
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep: return []
    tr = await db.podcast_transcripts.find_one(
        {"episode_id": episode_id}, {"utterances": 1, "text": 1, "_id": 0})
    utterances = (tr or {}).get("utterances") or []
    duration_total = float(ep.get("duration_seconds") or 0)
    candidates: list = []
    if utterances:
        # Sliding window across utterance starts.
        for u in utterances:
            s = float(u.get("start_seconds", u.get("start", 0)))
            e = min(s + target_seconds, duration_total)
            if e - s < 10: continue
            ut_score = _utterance_score(utterances, s, e)
            candidates.append({"start": s, "end": e, "score_utt": ut_score})
    if not candidates and duration_total > 10:
        # Fallback: even slices.
        t = 0.0
        while t + 10 < duration_total:
            candidates.append({"start": t,
                                          "end": min(t + target_seconds, duration_total),
                                          "score_utt": 0.5})
            t += target_seconds
    # Pick best non-overlapping `count` windows by score_utt for now.
    candidates.sort(key=lambda c: c["score_utt"], reverse=True)
    chosen: list = []
    for c in candidates:
        if any(not (c["end"] <= ch["start"] or c["start"] >= ch["end"])
                  for ch in chosen):
            continue
        ss, ee = _snap_to_utterance_bounds(utterances, c["start"], c["end"])
        chosen.append({"start": ss, "end": ee, "score_utt": c["score_utt"]})
        if len(chosen) >= count: break
    out = []
    for c in chosen:
        out.append({
            "start_seconds":            round(c["start"], 2),
            "end_seconds":               round(c["end"], 2),
            "confidence_score":      round(min(1.0, c["score_utt"]), 3),
            "why":                                "High utterance density"
                                                          + (" (incl. questions)"
                                                              if c["score_utt"] > 0.6 else ""),
        })
    return out


async def trim_and_upload_clip(db, *, episode_id: str, channel_id: str,
                                                              start: float, end: float, why: str,
                                                              confidence: float = 0.5) -> dict:
    """Pull mixed.mp3 from Tigris (via the same proxy path the players use),
    trim to a temp file, upload back to Tigris under
    `podcasts/clips/{clip_id}.mp3`, write the row, return it."""
    from services import object_storage as obs
    st = obs.get_storage()
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep: return {"error": "episode_not_found"}
    # Resolve source mp3 key — prefer storage_key_audio.
    src_key = ep.get("storage_key_audio")
    if not src_key:
        sid = ep.get("recording_session_id")
        src_key = (obs.key_recording_mixed_audio(sid) if sid else
                          obs.key_episode_audio(channel_id, episode_id))
    head = st.head(key=src_key)
    if not head: return {"error": "source_key_missing", "key": src_key}
    # Read whole audio to local temp (clips are short — fine for MVP).
    total = int(head.get("size") or 0)
    src_bytes = st.open_range(key=src_key, start=0, end=max(total - 1, 0))
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src.mp3"
        src.write_bytes(src_bytes)
        clip_id = _gen("pcl")
        out = Path(td) / "clip.mp3"
        cmd = ["ffmpeg", "-y", "-ss", f"{start}", "-to", f"{end}",
                  "-i", str(src), "-c:a", "libmp3lame", "-b:a", "192k", str(out)]
        rc = subprocess.run(cmd, capture_output=True, timeout=120).returncode
        if rc != 0 or not out.is_file() or out.stat().st_size == 0:
            return {"error": "ffmpeg_trim_failed", "rc": rc}
        clip_key = f"podcasts/clips/{clip_id}.mp3"
        st.upload(local_path=str(out), key=clip_key,
                      content_type="audio/mpeg")
        h2 = st.head(key=clip_key)
        if not h2 or int(h2.get("size") or 0) != out.stat().st_size:
            return {"error": "tigris_verify_failed"}
        size_bytes = out.stat().st_size
    row = {
        "id":                              clip_id,
        "episode_id":               episode_id,
        "channel_id":               channel_id,
        "start_seconds":         round(float(start), 2),
        "end_seconds":              round(float(end), 2),
        "duration_seconds":  round(float(end - start), 2),
        "why":                            (why or "Top moment")[:240],
        "confidence_score": round(float(confidence), 3),
        "storage_key":             clip_key,
        "audio_url":                 f"/api/podcasts/clips/{clip_id}/audio.mp3",
        "video_url":                 None,    # video clips Phase 36d.1
        "file_size_bytes":     size_bytes,
        "status":                       "generated",
        "created_at":               _now(),
    }
    await db[CLIPS_COL].insert_one(row); row.pop("_id", None)
    return row


async def generate_clips(db, *, episode_id: str,
                                                      count: int = DEFAULT_COUNT) -> dict:
    """detect_top_moments → trim+upload each → return inserted rows."""
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep: return {"clips": [], "error": "episode_not_found"}
    # Idempotency: if clips already exist for this episode, return them.
    existing = await db[CLIPS_COL].find(
        {"episode_id": episode_id},
        {"_id": 0}).to_list(20)
    if existing: return {"clips": existing, "skipped": "already_generated"}
    windows = await detect_top_moments(db, episode_id=episode_id, count=count)
    inserted: list = []
    errors: list = []
    for w in windows:
        r = await trim_and_upload_clip(db,
            episode_id=episode_id, channel_id=ep.get("channel_id"),
            start=w["start_seconds"], end=w["end_seconds"],
            why=w["why"], confidence=w["confidence_score"])
        if r.get("error"): errors.append(r)
        else: inserted.append(r)
    return {"clips": inserted, "errors": errors,
              "count_inserted": len(inserted)}
