"""Phase 36d Turn 1 — Magic Clips pipeline.

Pipeline (called asynchronously via asyncio.create_task from finalize_session):

  1. Pull AssemblyAI transcription with sentiment_analysis=true +
     auto_chapters=true. We call AAI directly (lightweight wrapper)
     rather than going through services/assemblyai_client.submit_transcription
     because we need the extras flags that the default client doesn't pass.
  2. Run ffmpeg ebur128 on the mixed audio, parse momentary loudness from
     stderr in ~5s windows.
  3. Align sentiment segments to loudness windows; score = 0.6 *
     |sentiment_score| + 0.4 * normalized_loudness.
  4. Take top-N non-overlapping windows (N = channel.magic_clips_per_episode
     or 5). Snap boundaries to AAI word-timestamp gaps > 250 ms; clamp
     30-60 s.
  5. Render each clip with ffmpeg -ss/-t -c copy. Upload to Tigris under
     `magic_clips/{episode_id}/{clip_id}.{ext}`.
  6. AI-title + summary via OpenAI gpt-4o-mini (1 call per clip).
  7. Persist `podcast_magic_clips` rows, update
     `podcast_episodes.magic_clips_status: completed|failed`.

Public API:
    is_enabled_for_channel(channel) -> bool
    schedule_magic_clips(db, *, episode_id) -> asyncio.Task
    _magic_clips_job(db, *, episode_id) -> dict (entry point — awaitable)
    _run_pipeline(...) — pure-ish core, easy to test in isolation
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("bigfm.magic_clips")
_AAI_KEY = (os.environ.get("ASSEMBLYAI_API_KEY") or "").strip()
_OPENAI_KEY = (os.environ.get("OPENAI_API_KEY")
                              or os.environ.get("EMERGENT_LLM_KEY") or "").strip()


# ── channel-config helpers ─────────────────────────────────────────
DEFAULT_PER_EPISODE = 5
PER_EPISODE_MIN = 1
PER_EPISODE_MAX = 15


def is_enabled_for_channel(channel: dict | None) -> bool:
    if not channel:
        return False
    return channel.get("magic_clips_enabled", True) is not False


def clips_per_episode(channel: dict | None) -> int:
    if not channel:
        return DEFAULT_PER_EPISODE
    n = channel.get("magic_clips_per_episode")
    try:
        n = int(n) if n is not None else DEFAULT_PER_EPISODE
    except Exception:
        n = DEFAULT_PER_EPISODE
    return max(PER_EPISODE_MIN, min(PER_EPISODE_MAX, n))


# ── AAI ──────────────────────────────────────────────────────────
async def _aai_transcribe(audio_url: str, *, timeout_s: int = 600) -> dict:
    """Submit + poll an AAI transcript with sentiment_analysis +
    auto_chapters enabled. Returns the completed transcript dict.
    Raises RuntimeError on AAI error / timeout. Caller is responsible
    for catching and recording the failure."""
    if not _AAI_KEY:
        raise RuntimeError("ASSEMBLYAI_API_KEY missing")
    headers = {"authorization": _AAI_KEY}
    async with httpx.AsyncClient(timeout=60) as cli:
        sub = await cli.post("https://api.assemblyai.com/v2/transcript",
                                              headers=headers,
                                              json={"audio_url": audio_url,
                                                          "sentiment_analysis": True,
                                                          "auto_chapters": True,
                                                          "punctuate": True})
        sub.raise_for_status()
        tid = sub.json()["id"]
        t0 = time.time()
        while True:
            await asyncio.sleep(5)
            r = await cli.get(f"https://api.assemblyai.com/v2/transcript/{tid}",
                                          headers=headers)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "completed":
                return data
            if data.get("status") == "error":
                raise RuntimeError(f"AAI error: {data.get('error')}")
            if time.time() - t0 > timeout_s:
                raise RuntimeError("AAI transcription timed out")


# ── ffmpeg ebur128 momentary loudness ──────────────────────────────
_EBUR_LINE = re.compile(
    r"t:\s*([0-9.]+)\s+TARGET:\s*-23\s+LUFS\s+M:\s*(-?[0-9.]+|-inf)")


def ebur128_windows(audio_path: str, window_s: float = 5.0) -> list[dict]:
    """Run `ffmpeg -i <audio> -af ebur128 -f null -` and parse momentary
    loudness samples from stderr, then bucket into `window_s` windows.
    Returns list of {"start_sec", "end_sec", "lufs_m"} sorted by
    start_sec. lufs_m == -120 is the synthetic floor for "-inf" lines."""
    p = subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", audio_path,
          "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, timeout=600)
    samples = []
    for line in p.stderr.splitlines():
        m = _EBUR_LINE.search(line)
        if not m:
            continue
        t = float(m.group(1))
        v = m.group(2)
        lufs = -120.0 if v == "-inf" else float(v)
        samples.append((t, lufs))
    if not samples:
        return []
    duration = samples[-1][0]
    n_windows = max(1, int(duration // window_s) + 1)
    windows = []
    si = 0
    for i in range(n_windows):
        a = i * window_s
        b = a + window_s
        chunk = []
        while si < len(samples) and samples[si][0] < b:
            if samples[si][0] >= a:
                chunk.append(samples[si][1])
            si += 1
        if not chunk:
            continue
        avg = sum(chunk) / len(chunk)
        windows.append({"start_sec": a, "end_sec": b, "lufs_m": avg})
    return windows


# ── scoring + boundary snap ────────────────────────────────────────
def score_candidates(sentiment_results: list[dict],
                                      lufs_windows: list[dict]) -> list[dict]:
    """For each loudness window, find overlapping sentiment segments
    and assemble a candidate dict with `score`. Score = 0.6 *
    |sentiment_score| + 0.4 * normalized_loudness."""
    if not lufs_windows:
        return []
    lufs_vals = [w["lufs_m"] for w in lufs_windows
                            if w["lufs_m"] > -120]
    if not lufs_vals:
        return []
    lo, hi = min(lufs_vals), max(lufs_vals)
    rng = (hi - lo) or 1.0

    def _sent_for(start_ms: float, end_ms: float) -> float:
        scores = []
        for s in (sentiment_results or []):
            s0 = float(s.get("start", 0))
            s1 = float(s.get("end", 0))
            if s1 < start_ms or s0 > end_ms:
                continue
            polarity = (1.0 if s.get("sentiment") == "POSITIVE"
                                  else -1.0 if s.get("sentiment") == "NEGATIVE"
                                  else 0.3)
            conf = float(s.get("confidence", 0.5) or 0.5)
            scores.append(polarity * conf)
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    candidates = []
    for w in lufs_windows:
        l_norm = (w["lufs_m"] - lo) / rng if w["lufs_m"] > -120 else 0.0
        sentiment = _sent_for(w["start_sec"] * 1000, w["end_sec"] * 1000)
        score = 0.6 * abs(sentiment) + 0.4 * l_norm
        candidates.append({"start_sec": w["start_sec"],
                                          "end_sec": w["end_sec"],
                                          "lufs_norm": l_norm,
                                          "sentiment": sentiment,
                                          "score": round(score, 4)})
    return candidates


def pick_top_non_overlapping(candidates: list[dict], n: int) -> list[dict]:
    out: list[dict] = []
    for c in sorted(candidates, key=lambda x: x["score"], reverse=True):
        ok = all(c["end_sec"] <= o["start_sec"] or
                        c["start_sec"] >= o["end_sec"] for o in out)
        if ok:
            out.append(c)
        if len(out) >= n:
            break
    return out


def snap_to_silence(words: list[dict] | None, start_sec: float, end_sec: float,
                                  min_len: float = 30.0, max_len: float = 60.0) -> tuple[float, float]:
    """Snap clip boundaries to AAI word-timestamp gaps > 250 ms.
    If no usable snap is found, return a 45-s window centered on the peak."""
    center = (start_sec + end_sec) / 2
    if not words:
        a = max(0.0, center - 22.5); b = a + 45.0
        return a, b
    gaps = []
    prev_end = None
    for w in words:
        s = float(w.get("start", 0)) / 1000.0
        e = float(w.get("end", 0)) / 1000.0
        if prev_end is not None and (s - prev_end) > 0.25:
            gaps.append((prev_end + s) / 2)
        prev_end = e
    # candidate boundaries near the desired range
    target_start_lo = center - max_len / 2
    target_start_hi = center - min_len / 2
    target_end_lo   = center + min_len / 2
    target_end_hi   = center + max_len / 2
    start_candidates = [g for g in gaps
                                            if target_start_lo <= g <= target_start_hi]
    end_candidates   = [g for g in gaps
                                            if target_end_lo <= g <= target_end_hi]
    if start_candidates and end_candidates:
        a = max(start_candidates)
        b = min(end_candidates)
        if min_len <= (b - a) <= max_len:
            return max(0.0, a), b
    a = max(0.0, center - 22.5); b = a + 45.0
    return a, b


# ── ffmpeg cut + Tigris upload ────────────────────────────────────
def cut_clip(src: str, dst: str, start_sec: float, dur_sec: float) -> int:
    """Cut a clip via stream-copy for speed. Returns 0 on success."""
    p = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
          "-ss", f"{start_sec:.3f}", "-i", src,
          "-t", f"{dur_sec:.3f}", "-c", "copy", "-avoid_negative_ts",
          "make_zero", dst],
        capture_output=True, timeout=120)
    return p.returncode


async def _ai_title_and_summary(transcript_chunk: str) -> tuple[str, str]:
    """Single OpenAI call returning a 10-word title + 1-sentence summary.
    Falls back to a heuristic if the call fails so the pipeline never
    blocks on AI."""
    if not _OPENAI_KEY or not transcript_chunk.strip():
        return _heuristic_title(transcript_chunk), ""
    try:
        from openai import OpenAI
        cli = OpenAI(api_key=_OPENAI_KEY)
        rsp = cli.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system",
                              "content": "Return JSON {\"title\":..., \"summary\":...}. "
                                                "title <= 10 words, no emojis. "
                                                "summary one sentence under 25 words."},
                            {"role": "user",
                              "content": f"Highlight excerpt:\n\n{transcript_chunk[:1500]}"}],
            response_format={"type": "json_object"},
            max_tokens=200, timeout=30)
        import json as _json
        data = _json.loads(rsp.choices[0].message.content)
        title = (data.get("title") or "").strip()[:120]
        summary = (data.get("summary") or "").strip()[:280]
        return (title or _heuristic_title(transcript_chunk)), summary
    except Exception as e:
        logger.warning("[magic_clips] OpenAI title failed (heuristic): %s", e)
        return _heuristic_title(transcript_chunk), ""


def _heuristic_title(transcript_chunk: str) -> str:
    txt = re.sub(r"\s+", " ", transcript_chunk or "").strip()
    return (txt[:60] + "…") if len(txt) > 60 else (txt or "Highlight")


# ── orchestration ─────────────────────────────────────────────────
async def _persist_clip(db, *, episode: dict, channel_id: str,
                                          window: dict, transcript_chunk: str,
                                          local_path: str, ext: str) -> dict:
    clip_id = "mc_" + uuid.uuid4().hex[:14]
    title, summary = await _ai_title_and_summary(transcript_chunk)
    file_size = 0
    try:
        file_size = Path(local_path).stat().st_size
    except Exception:
        pass
    storage_key = f"magic_clips/{episode['id']}/{clip_id}.{ext}"
    try:
        from services import object_storage as obs
        st = obs.get_storage()
        if st.backend_name == "tigris":
            st.upload(local_path=local_path, key=storage_key,
                              content_type=("video/mp4" if ext == "mp4"
                                                            else "audio/mpeg"))
    except Exception as e:
        logger.warning("[magic_clips] tigris upload failed (kept local): %s", e)
    doc = {"id":                       clip_id,
              "episode_id":           episode["id"],
              "channel_id":           channel_id,
              "status":                   "draft",
              "start_sec":             float(window.get("start_sec_snapped", window["start_sec"])),
              "end_sec":               float(window.get("end_sec_snapped",   window["end_sec"])),
              "score":                   float(window.get("score", 0.0)),
              "sentiment":             float(window.get("sentiment", 0.0)),
              "lufs_norm":             float(window.get("lufs_norm", 0.0)),
              "title":                     title,
              "summary":               summary,
              "storage_key":         storage_key,
              "local_path":           local_path,
              "file_size_bytes":   file_size,
              "ext":                       ext,
              "created_at":           datetime.now(timezone.utc),
              "published_at":     None}
    await db.podcast_magic_clips.insert_one(doc)
    doc.pop("_id", None)
    return doc


def _episode_audio_path(episode: dict) -> str | None:
    """Locate the mixed audio file for an episode. Prefer the
    `storage_path` / session-dir mixed.mp3; fallback to other hints."""
    sp = episode.get("storage_path")
    if sp:
        cand = Path(sp) / "mixed.mp3"
        if cand.is_file():
            return str(cand)
    for k in ("master_audio_path", "audio_path", "final_audio_path"):
        v = episode.get(k)
        if v and Path(v).is_file():
            return v
    return None


def _episode_video_path(episode: dict) -> str | None:
    sp = episode.get("storage_path")
    if sp:
        cand = Path(sp) / "video.mp4"
        if cand.is_file():
            return str(cand)
    return None


async def _run_pipeline(db, *, episode_id: str,
                                              aai_data_override: dict | None = None) -> dict:
    """Pure-ish core, easy to call from tests with a synthetic AAI payload."""
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep:
        raise RuntimeError(f"episode not found: {episode_id}")
    channel = await db.podcast_channels.find_one({"id": ep.get("channel_id")})
    if not is_enabled_for_channel(channel):
        return {"skipped": True, "reason": "magic_clips disabled for channel"}
    n = clips_per_episode(channel)
    src_audio = _episode_audio_path(ep)
    src_video = _episode_video_path(ep)
    if not src_audio:
        raise RuntimeError("episode audio file not on local disk for clip-cut")

    if aai_data_override is not None:
        aai = aai_data_override
    else:
        # Prefer an external HTTPS URL if one exists; otherwise we can't
        # send the local file to AAI without uploading it first.
        audio_url = ep.get("audio_url_external")
        if not audio_url:
            from services import object_storage as obs
            st = obs.get_storage()
            ak = ep.get("audio_storage_key")
            if ak and st.backend_name == "tigris":
                audio_url = st.get_signed_url(key=ak, expires_in=3600)
        if not audio_url:
            raise RuntimeError("no AAI-reachable audio_url for this episode")
        aai = await _aai_transcribe(audio_url)

    sentiment = aai.get("sentiment_analysis_results") or []
    words = aai.get("words") or []
    lufs = ebur128_windows(src_audio)
    candidates = score_candidates(sentiment, lufs)
    if not candidates:
        return {"skipped": True, "reason": "no_loudness_data"}
    top = pick_top_non_overlapping(candidates, n)

    out_dir = Path(src_audio).parent / "magic_clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    persisted = []
    accepted_ranges: list[tuple[float, float]] = []
    for win in top:
        a, b = snap_to_silence(words, win["start_sec"], win["end_sec"])
        # snap can expand a 5s window to 30-60s, so two originally-adjacent
        # candidates can collide once snapped. Re-dedupe here.
        if any(not (b <= ra or a >= rb) for ra, rb in accepted_ranges):
            continue
        dur = b - a
        ext = "mp4" if src_video else "mp3"
        src = src_video if src_video else src_audio
        dst = out_dir / f"clip_{int(a)}_{int(b)}.{ext}"
        rc = cut_clip(src, str(dst), a, dur)
        if rc != 0 or not dst.is_file() or dst.stat().st_size == 0:
            continue
        # Transcript chunk for naming = AAI words that fall inside [a,b].
        chunk = " ".join(w.get("text", "") for w in words
                                          if a * 1000 <= float(w.get("start", 0)) <= b * 1000)
        chunk = chunk or _summary_from_window(aai, a, b)
        win_doc = {**win, "start_sec_snapped": a, "end_sec_snapped": b}
        clip = await _persist_clip(db, episode=ep, channel_id=ep["channel_id"],
                                                              window=win_doc, transcript_chunk=chunk,
                                                              local_path=str(dst), ext=ext)
        persisted.append(clip)
        accepted_ranges.append((a, b))
    return {"episode_id": episode_id, "candidates": len(candidates),
                  "produced": len(persisted), "skipped": False}


def _summary_from_window(aai: dict, a: float, b: float) -> str:
    text = (aai.get("text") or "")[:2000]
    return text


async def _magic_clips_job(db, *, episode_id: str) -> dict:
    """Top-level entry called via asyncio.create_task. Records status
    transitions on the episode doc so the frontend can poll."""
    await db.podcast_episodes.update_one(
        {"id": episode_id},
        {"$set": {"magic_clips_status": "running",
                      "magic_clips_started_at": datetime.now(timezone.utc),
                      "magic_clips_error": None}})
    try:
        res = await _run_pipeline(db, episode_id=episode_id)
        await db.podcast_episodes.update_one(
            {"id": episode_id},
            {"$set": {"magic_clips_status": "completed",
                          "magic_clips_count": res.get("produced", 0),
                          "magic_clips_finished_at": datetime.now(timezone.utc)}})
        return res
    except Exception as e:
        logger.warning("[magic_clips] job failed ep=%s: %s", episode_id, e)
        await db.podcast_episodes.update_one(
            {"id": episode_id},
            {"$set": {"magic_clips_status": "failed",
                          "magic_clips_error": str(e)[:240],
                          "magic_clips_finished_at": datetime.now(timezone.utc)}})
        return {"failed": True, "error": str(e)}


def schedule_magic_clips(db, *, episode_id: str) -> asyncio.Task | None:
    """Fire-and-forget scheduler invoked from finalize_session.
    Returns the task for testability (or None if no running loop)."""
    try:
        return asyncio.create_task(_magic_clips_job(db, episode_id=episode_id))
    except RuntimeError:
        # No running loop (e.g. in a sync test) — caller can `asyncio.run`.
        return None


# ── ensure indexes (called from server startup or on first hit) ──
async def ensure_indexes(db):
    coll = db.podcast_magic_clips
    await coll.create_index([("episode_id", 1), ("status", 1)])
    await coll.create_index([("channel_id", 1), ("created_at", -1)])
    await coll.create_index([("status", 1), ("published_at", -1)])
    await coll.create_index([("id", 1)], unique=True)
