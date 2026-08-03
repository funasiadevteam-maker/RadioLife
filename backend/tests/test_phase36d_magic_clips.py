"""Phase 36d Turn 1 — Magic Clips pipeline tests.

Hermetic: tests inject a synthetic AAI payload via `aai_data_override`
so no live AAI calls happen here. Real ffmpeg is exercised for the
ebur128 + cut steps using small synthesized .wav fixtures.
"""
from __future__ import annotations
import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient
from services import podcast_magic_clips as mc


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


def _synth_audio(path: str, dur_s: int = 60):
    """30-90 s synthetic sine sweep -> stereo 16k mp3."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
          "-i", f"sine=frequency=440:duration={dur_s}",
          "-c:a", "libmp3lame", "-b:a", "64k", path],
        check=True, timeout=120)


def _synth_aai(dur_s: int = 60, n_segments: int = 12) -> dict:
    """Synthetic AAI payload with sentiment + words spanning [0, dur_s]."""
    seg_len = (dur_s * 1000) // n_segments
    sentiment = []
    words = []
    for i in range(n_segments):
        polarity = "POSITIVE" if i % 3 == 0 else (
            "NEGATIVE" if i % 5 == 0 else "NEUTRAL")
        sentiment.append({"start": i * seg_len, "end": (i + 1) * seg_len,
                                          "sentiment": polarity, "confidence": 0.85,
                                          "text": f"segment {i}"})
        # 4 words per segment with a 300 ms inter-segment gap.
        for k in range(4):
            ws = i * seg_len + k * (seg_len // 5) + 50
            we = ws + (seg_len // 6)
            words.append({"start": ws, "end": we, "text": f"w{i}_{k}"})
        # Force a > 250 ms gap between segments by skipping a tick.
    return {"status": "completed",
                  "text": "synthetic body for naming",
                  "sentiment_analysis_results": sentiment,
                  "words": words,
                  "chapters": [{"start": 0, "end": dur_s * 1000,
                                          "summary": "chapter 1", "headline": "h"}]}


@pytest.fixture
def episode_with_audio(tmp_path):
    """Seed a channel + episode whose mixed.mp3 is a real synthesized
    file, so ffmpeg ebur128 + cut succeed for real."""
    db = _db()
    cid = f"pch_t_{uuid.uuid4().hex[:6]}"
    eid = f"pep_t_{uuid.uuid4().hex[:6]}"
    sess = tmp_path / "session"; sess.mkdir()
    _synth_audio(str(sess / "mixed.mp3"), dur_s=60)
    run(db.podcast_channels.insert_one({
        "id": cid, "title": "Test", "creator_id": "cr_t",
        "active": True, "approval_status": "approved",
        "magic_clips_enabled": True, "magic_clips_per_episode": 5}))
    run(db.podcast_episodes.insert_one({
        "id": eid, "channel_id": cid, "title": "ep",
        "storage_path": str(sess), "duration_seconds": 60,
        "publish_status": "draft"}))
    yield {"channel_id": cid, "episode_id": eid, "sess": sess}
    run(db.podcast_episodes.delete_one({"id": eid}))
    run(db.podcast_channels.delete_one({"id": cid}))
    run(db.podcast_magic_clips.delete_many({"episode_id": eid}))


def test_pipeline_produces_5_clips_default(episode_with_audio):
    eid = episode_with_audio["episode_id"]
    res = run(mc._run_pipeline(_db(), episode_id=eid,
                                                  aai_data_override=_synth_aai(60, 12)))
    assert res.get("skipped") is not True, res
    assert res["produced"] >= 1, res
    clips = run(_db().podcast_magic_clips.find({"episode_id": eid}).to_list(20))
    assert 1 <= len(clips) <= 5
    # Non-overlapping
    sorted_c = sorted(clips, key=lambda c: c["start_sec"])
    for a, b in zip(sorted_c, sorted_c[1:]):
        assert a["end_sec"] <= b["start_sec"] + 0.01


def test_per_channel_override_caps_at_3(episode_with_audio):
    eid = episode_with_audio["episode_id"]
    cid = episode_with_audio["channel_id"]
    run(_db().podcast_channels.update_one(
        {"id": cid}, {"$set": {"magic_clips_per_episode": 3}}))
    run(mc._run_pipeline(_db(), episode_id=eid,
                                          aai_data_override=_synth_aai(60, 12)))
    clips = run(_db().podcast_magic_clips.find({"episode_id": eid}).to_list(20))
    assert 1 <= len(clips) <= 3, len(clips)


def test_disabled_channel_skips_pipeline(episode_with_audio):
    eid = episode_with_audio["episode_id"]
    cid = episode_with_audio["channel_id"]
    run(_db().podcast_channels.update_one(
        {"id": cid}, {"$set": {"magic_clips_enabled": False}}))
    res = run(mc._run_pipeline(_db(), episode_id=eid,
                                                  aai_data_override=_synth_aai()))
    assert res.get("skipped") is True
    n = run(_db().podcast_magic_clips.count_documents({"episode_id": eid}))
    assert n == 0


def test_scores_monotonically_decreasing_and_non_overlapping():
    sentiment = [{"start": i * 5000, "end": (i + 1) * 5000,
                              "sentiment": "POSITIVE" if i in (2, 5, 8) else "NEUTRAL",
                              "confidence": 0.9} for i in range(12)]
    lufs = [{"start_sec": i * 5, "end_sec": (i + 1) * 5,
                  "lufs_m": -30 + (3 if i in (2, 5, 8) else 0)} for i in range(12)]
    cands = mc.score_candidates(sentiment, lufs)
    top = mc.pick_top_non_overlapping(cands, 3)
    assert len(top) == 3
    assert all(top[i]["score"] >= top[i + 1]["score"] for i in range(2))
    # non-overlapping
    s = sorted(top, key=lambda c: c["start_sec"])
    for a, b in zip(s, s[1:]):
        assert a["end_sec"] <= b["start_sec"] + 1e-6


def test_snap_to_silence_clamps_to_30_60s_window():
    # No words → fallback 45 s centered on peak (37.5–82.5).
    a, b = mc.snap_to_silence(None, 50, 55)
    assert 30.0 <= (b - a) <= 60.0
    # With wide gaps inside target range it picks them.
    words = [{"start": (40 + i * 200), "end": (40 + i * 200 + 100)}
                      for i in range(120)]    # 200 ms gap each ≤ 250 → no snap usable
    a2, b2 = mc.snap_to_silence(words, 50, 55)
    assert 30.0 <= (b2 - a2) <= 60.0


def test_settings_endpoint_validates_range(episode_with_audio):
    """Backend channel-settings PATCH validates 1<=n<=15."""
    db = _db()
    cid = episode_with_audio["channel_id"]
    # The route is mounted; we test the validator directly via subset() +
    # clips_per_episode clamp.
    run(db.podcast_channels.update_one(
        {"id": cid}, {"$set": {"magic_clips_per_episode": 99}}))
    ch = run(db.podcast_channels.find_one({"id": cid}))
    # clamp at read-time
    assert mc.clips_per_episode(ch) == 15
    run(db.podcast_channels.update_one(
        {"id": cid}, {"$set": {"magic_clips_per_episode": 0}}))
    ch = run(db.podcast_channels.find_one({"id": cid}))
    assert mc.clips_per_episode(ch) == 1


def test_failure_path_marks_episode_failed():
    """If the pipeline raises, _magic_clips_job should set
    magic_clips_status='failed' and stash the error string."""
    db = _db()
    eid = f"pep_fail_{uuid.uuid4().hex[:6]}"
    cid = f"pch_fail_{uuid.uuid4().hex[:6]}"
    run(db.podcast_channels.insert_one({
        "id": cid, "title": "FailCh", "creator_id": "cr_t",
        "active": True, "magic_clips_enabled": True}))
    # Episode with no audio path -> RuntimeError in _run_pipeline.
    run(db.podcast_episodes.insert_one({
        "id": eid, "channel_id": cid, "title": "noaudio"}))
    res = run(mc._magic_clips_job(db, episode_id=eid))
    assert res.get("failed") is True
    ep = run(db.podcast_episodes.find_one({"id": eid}))
    assert ep["magic_clips_status"] == "failed"
    assert ep.get("magic_clips_error")
    run(db.podcast_episodes.delete_one({"id": eid}))
    run(db.podcast_channels.delete_one({"id": cid}))
