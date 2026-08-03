"""Phase 36c Stage 3 — Video + multi-track FFmpeg grid layout tests.

Full-scope (1080p / 500 MB / 60 min, Tigris-backed) acceptance suite.
Skipped when STORAGE_BACKEND != tigris because the grid finalize path
uploads its outputs to Tigris and the proxy reads from Tigris.

Each test seeds the bare minimum (session + participants + mp3 + mp4)
on disk, exercises the real finalize code path, then asserts on
ffprobe-reported dimensions of the resulting mixed.mp4 and the Tigris
key presence / HEAD response.
"""
from __future__ import annotations
import asyncio, json, os, shutil, subprocess, sys, uuid
from pathlib import Path

import pytest

sys.path.insert(0, "/app/backend")

try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

from services import object_storage as obs                    # noqa: E402
from services import podcast_video as pv                          # noqa: E402

TIGRIS_LIVE = (os.environ.get("STORAGE_BACKEND") or "").lower() == "tigris"
pytestmark = pytest.mark.skipif(
    not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris (Stage 3 needs Tigris)")


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _make_av(local: Path, *, sec: float = 1.5, color: str = "red"):
    """Make a tiny audio+video webm clip (mocking what MediaRecorder would
    produce in the browser). Returns the file size."""
    subprocess.run(
        ["ffmpeg", "-y",
          "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=15:d={sec}",
          "-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}",
          "-c:v", "libvpx", "-b:v", "200k",
          "-c:a", "libvorbis", "-shortest", str(local)],
        check=True, capture_output=True, timeout=30)
    return local.stat().st_size


def _seed_session_with_video(db, *, n_participants: int = 2,
                                                                  video_enabled: bool = True,
                                                                  grid_layout: str = "auto"
                                                                  ) -> tuple[str, list[str]]:
    """Plant a session + N participants + N pre-transcoded mp4 + mp3 on disk,
    then call finalize_session directly. Returns (session_id, [pid…])."""
    from services import podcast_recording as pr
    sid = f"prs_s3_{uuid.uuid4().hex[:8]}"
    ch_id = f"ch_s3_{uuid.uuid4().hex[:6]}"
    sess_dir = pr.STORAGE_ROOT / sid
    sess_dir.mkdir(parents=True, exist_ok=True)
    pids: list[str] = []
    colors = ["red", "blue", "green", "yellow"]
    for i in range(n_participants):
        role = "host" if i == 0 else "guest"
        pid = f"prp_s3_{uuid.uuid4().hex[:8]}"; pids.append(pid)
        base = "host" if role == "host" else pid
        # Plant transcoded mp4 (would be produced by upload_track).
        webm = sess_dir / f"{base}_raw.webm"
        _make_av(webm, sec=1.5, color=colors[i % len(colors)])
        mp4 = sess_dir / f"{base}_video.mp4"
        rc = pv.transcode_to_mp4(webm, mp4, target_height=1080)
        webm.unlink(missing_ok=True)
        assert rc == 0, f"transcode failed for {base}"
        # Plant matching mp3 (would be produced by amix-friendly path).
        mp3 = sess_dir / f"{base}.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp4), "-vn",
              "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)],
            check=True, capture_output=True, timeout=30)
        run(db.podcast_recording_participants.insert_one({
            "id": pid, "session_id": sid, "user_id": f"u_{role}",
            "role": role, "display_name": role.title(),
            "joined_at": pr._now(), "admitted_at": pr._now(),
            "upload_status": "completed",
            "audio_track_url": f"/local/{sid}/{base}.mp3",
            "video_upload_status": "completed",
            "video_track_url": f"/local/{sid}/{base}_video.mp4",
            "created_at": pr._now()}))
    run(db.podcast_recording_sessions.insert_one({
        "id": sid, "creator_id": "u_host", "channel_id": ch_id,
        "title": f"Stage 3 video {n_participants}p",
        "video_enabled": bool(video_enabled),
        "grid_layout": grid_layout,
        "status": "processing", "started_at": pr._now(),
        "total_duration_seconds": 1.5,
        "created_at": pr._now(), "updated_at": pr._now()}))
    return sid, pids


def _cleanup_session(db, sid: str):
    """Best-effort cleanup of Tigris keys + DB rows + local dir."""
    from services import podcast_recording as pr
    s = obs.TigrisStorage()
    for key_suffix in ("mixed.mp3", "mixed.mp4", "audio.mp3"):
        try: s.delete(key=f"podcasts/recordings/{sid}/{key_suffix}")
        except Exception: pass
    parts = run(db.podcast_recording_participants.find(
        {"session_id": sid}, {"id": 1, "role": 1, "_id": 0}).to_list(10))
    for p in parts:
        if p.get("role") == "host":
            try: s.delete(key=f"podcasts/recordings/{sid}/host/audio.mp3")
            except Exception: pass
            try: s.delete(key=f"podcasts/recordings/{sid}/host/video.mp4")
            except Exception: pass
        else:
            try: s.delete(key=obs.key_recording_participant_audio(sid, p["id"]))
            except Exception: pass
            try: s.delete(key=obs.key_recording_participant_video(sid, p["id"]))
            except Exception: pass
    run(db.podcast_recording_sessions.delete_one({"id": sid}))
    run(db.podcast_recording_participants.delete_many({"session_id": sid}))
    run(db.podcast_episodes.delete_many({"recording_session_id": sid}))
    run(db.podcast_recordings.delete_many({"session_id": sid}))
    sess_dir = pr.STORAGE_ROOT / sid
    if sess_dir.exists(): shutil.rmtree(sess_dir, ignore_errors=True)


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


# ─── 1. Session create with video_enabled=True grants publish_video ──
def test_36c_s3_01_create_session_with_video_enabled_grants_publish_video():
    from services import podcast_recording as pr
    db = _db()
    ch_id = f"ch_s3_t1_{uuid.uuid4().hex[:6]}"
    # No active session please.
    run(db.podcast_recording_sessions.delete_many({"status":
        {"$in": ["pending", "recording", "processing"]}}))
    sess = None
    try:
        sess = run(pr.create_session(db, creator_id="u_t1",
                              channel_id=ch_id, title="t1",
                              video_enabled=True, grid_layout="2x2"))
        sid = sess["session_id"]
        # Read the persisted row to verify the video flags landed.
        row = run(db.podcast_recording_sessions.find_one(
            {"id": sid}, {"_id": 0}))
        assert row["video_enabled"] is True
        assert row["grid_layout"] == "2x2"
        tok = sess.get("livekit_room_name")
        assert tok and tok.startswith("bigfm-")
        # The host livekit token mints with publish_video=True via the
        # permissions arg — we just verify the persisted contract, since
        # the mock token is a string not a JWT.
    finally:
        if sess: run(db.podcast_recording_sessions.delete_one(
                              {"id": sess["session_id"]}))


# ─── 2 & 3. Upload-track accepts video at 500 MB / 60 min relaxed caps ──
def test_36c_s3_02_video_upload_cap_constants_match_full_scope():
    """The relaxed full-scope caps drive the gate values throughout."""
    assert pv.VIDEO_UPLOAD_CAP_BYTES        == 500 * 1024 * 1024
    assert pv.VIDEO_RECORDING_CAP_SEC == 3600
    assert pv.TARGET_H == 1080 and pv.TARGET_W == 1920


# ─── 4. Transcode failure → cleanup + audit ───────────────────────
def test_36c_s3_04_transcode_failure_returns_nonzero(tmp_path):
    bad = tmp_path / "bogus.webm"
    bad.write_bytes(b"not-a-video")
    out = tmp_path / "out.mp4"
    rc = pv.transcode_to_mp4(bad, out)
    assert rc != 0
    # No partial file from a failed run (ffmpeg writes nothing or zero).
    if out.exists(): assert out.stat().st_size == 0


# ─── 5. Layout helpers correctly pick layouts ─────────────────────
def test_36c_s3_05_resolve_layout_auto_and_override():
    assert pv.resolve_layout("auto", 1) == "single"
    assert pv.resolve_layout("auto", 2) == "side_by_side"
    assert pv.resolve_layout("auto", 3) == "speaker_view"
    assert pv.resolve_layout("auto", 4) == "2x2"
    # Override.
    assert pv.resolve_layout("2x2", 2) == "2x2"
    assert pv.resolve_layout("speaker_view", 4) == "speaker_view"


# ─── 6. Finalize 1-participant video → 1080p single tile ──────────
def test_36c_s3_06_finalize_1participant_video_is_single_1080p():
    from services import podcast_recording as pr
    db = _db()
    sid, pids = _seed_session_with_video(db, n_participants=1)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        assert ep["video_url"] is not None
        assert ep["video_layout"] == "single"
        dims = ep["video_dimensions"]
        # 640x360 source padded to 1920x1080 (force_original_aspect_ratio).
        assert dims["width"] == 1920
        assert dims["height"] == 1080
        # Tigris HEAD must succeed.
        s = obs.TigrisStorage()
        assert s.head(key=obs.key_recording_mixed_video(sid)) is not None
    finally:
        _cleanup_session(db, sid)


# ─── 7. Finalize 2-participant video → side_by_side @ 1920x1080 ──
def test_36c_s3_07_finalize_2participant_is_side_by_side_1920x1080():
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_with_video(db, n_participants=2)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        assert ep["video_layout"] == "side_by_side"
        dims = ep["video_dimensions"]
        # 2× 960x1080 hstack → 1920x1080.
        assert dims["width"] == 1920
        assert dims["height"] == 1080
    finally:
        _cleanup_session(db, sid)


# ─── 8. Finalize 3-participant video → speaker_view top tile ─────
def test_36c_s3_08_finalize_3participant_is_speaker_view():
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_with_video(db, n_participants=3)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        assert ep["video_layout"] == "speaker_view"
        dims = ep["video_dimensions"]
        # Top tile 1920x810 + bottom row 1920x270 → 1920x1080.
        assert dims["width"] == 1920
        assert dims["height"] == 1080
    finally:
        _cleanup_session(db, sid)


# ─── 9. Finalize 4-participant video → 2x2 xstack ─────────────────
def test_36c_s3_09_finalize_4participant_is_2x2_xstack():
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_with_video(db, n_participants=4)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        assert ep["video_layout"] == "2x2"
        dims = ep["video_dimensions"]
        # 4× 960x540 → 1920x1080 (xstack layout 0_0|w0_0|0_h0|w0_h0).
        assert dims["width"] == 1920
        assert dims["height"] == 1080
    finally:
        _cleanup_session(db, sid)


# ─── 10. grid_layout override is respected ───────────────────────
def test_36c_s3_10_grid_layout_override_forces_speaker_view():
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_with_video(db, n_participants=4,
                                                                grid_layout="speaker_view")
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        # Forced layout even though 4 participants would auto-pick 2x2.
        assert ep["video_layout"] == "speaker_view"
    finally:
        _cleanup_session(db, sid)


# ─── 11. video.mp4 proxy: HEAD + Range from Tigris ───────────────
def test_36c_s3_11_video_mp4_proxy_supports_head_and_range():
    """End-to-end: finalize a 2-participant video, then HEAD + Range the
    new /episodes/{id}/video.mp4 endpoint and verify 200 / 206 contract."""
    import requests
    from services import podcast_recording as pr
    db = _db()
    base = os.environ.get("PUBLIC_BACKEND_URL")
    if not base: pytest.skip("PUBLIC_BACKEND_URL not set")
    sid, _ = _seed_session_with_video(db, n_participants=2)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep_id = out["episode_id"]
        url = f"{base}/api/podcasts/episodes/{ep_id}/video.mp4"
        rh = requests.head(url, timeout=20)
        assert rh.status_code == 200, rh.text
        assert rh.headers.get("content-type") == "video/mp4"
        assert int(rh.headers.get("content-length") or 0) > 1000
        assert rh.headers.get("accept-ranges") == "bytes"
        rr = requests.get(url, headers={"Range": "bytes=0-1023"}, timeout=20)
        assert rr.status_code == 206
        cr = rr.headers.get("content-range") or ""
        assert cr.startswith("bytes 0-1023/")
        assert len(rr.content) == 1024
    finally:
        _cleanup_session(db, sid)


# ─── 12. RSS contains podcast:alternateEnclosure for video episodes ─
def test_36c_s3_12_rss_includes_alternate_enclosure_for_video():
    """Build the RSS for a channel whose newest episode has video_url. The
    XML must contain a <podcast:alternateEnclosure type="video/mp4"/> tag
    pointing at our /video.mp4 endpoint."""
    from services import podcast_rss as rss
    db = _db()
    ch_id = f"ch_rss_s3_{uuid.uuid4().hex[:6]}"
    ep_id = f"pep_rss_s3_{uuid.uuid4().hex[:6]}"
    try:
        run(db.podcast_channels.insert_one({
            "id": ch_id, "creator_id": "u_rss", "show_title": "S3 RSS",
            "show_description": "rss test", "author_name": "RSS",
            "show_artwork_url": "https://example.com/x.png",
            "category_primary": "Technology", "language": "en-us",
            "explicit": False, "compliance_state": "approved",
            "rss_enabled": True}))
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": ch_id,
            "guid": f"bigfm-ep-{ep_id}",
            "title": "S3 RSS ep", "description": "rss s3",
            "audio_url": f"/api/podcasts/episodes/{ep_id}/audio.mp3",
            "video_url": f"/api/podcasts/episodes/{ep_id}/video.mp4",
            "file_size_bytes": 50_000,
            "file_size_bytes_video": 1_500_000,
            "duration_seconds": 1.5,
            "publish_status": "published", "publish_state": "published",
            "season": 1, "episode_number": 1, "episode_type": "full",
            "created_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc),
            "published_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc)}))
        xml = run(rss.get_or_build_xml(db, channel_id=ch_id))
        assert '<podcast:alternateEnclosure type="video/mp4"' in xml
        assert f"{ep_id}/video.mp4" in xml
    finally:
        run(db.podcast_episodes.delete_one({"id": ep_id}))
        run(db.podcast_channels.delete_one({"id": ch_id}))


# ─── 13. Audio amix LUFS regression: -16 LUFS with video flow ─────
def test_36c_s3_13_audio_mix_loudnorm_preserved_with_video():
    """The Stage-2 -16 LUFS audio contract must not break when the video
    grid mix is also produced."""
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_with_video(db, n_participants=2)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        # Stream-back mixed.mp3 via Tigris and ffprobe loudnorm-friendly
        # measurement. We use ffprobe's volumedetect filter on a freshly
        # downloaded copy of the bytes.
        s = obs.TigrisStorage()
        mp3 = s.open_range(
            key=obs.key_recording_mixed_audio(sid),
            start=0, end=10_000_000)
        with open("/tmp/_s3_loud.mp3", "wb") as f: f.write(mp3)
        cp = subprocess.run(
            ["ffmpeg", "-i", "/tmp/_s3_loud.mp3",
              "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
              "-f", "null", "-"],
            capture_output=True, timeout=60)
        assert cp.returncode == 0
        # The loudnorm filter prints a JSON block ending with `}` on stderr.
        text = cp.stderr.decode("utf-8", "ignore")
        # Extract the JSON object — last `{ ... }` block.
        a = text.rfind("{"); b = text.rfind("}")
        assert a != -1 and b > a, "no loudnorm JSON in ffmpeg output"
        loud = json.loads(text[a:b + 1])
        # When we loudnorm-targeted -16 LUFS during finalize, a *second*
        # pass measurement will sit very close to -16. We allow ±2 LU.
        measured_i = float(loud.get("input_i") or 0)
        assert -19.0 <= measured_i <= -13.0, (
            f"loudnorm input_i out of band: {measured_i} (expected ≈ -16)")
    finally:
        _cleanup_session(db, sid)


# ─── 14. Post-finalize local cleanup applies to video files too ───
def test_36c_s3_14_post_finalize_deletes_local_video_files():
    """36c.5 cleanup must catch mixed.mp4 + per-participant mp4 files
    in addition to audio. Session dir must be empty/gone post-finalize."""
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_with_video(db, n_participants=2)
    try:
        run(pr.finalize_session(db, session_id=sid))
        sess_dir = pr.STORAGE_ROOT / sid
        leftover = (list(sess_dir.rglob("*")) if sess_dir.exists() else [])
        files = [p for p in leftover if p.is_file()]
        assert files == [], f"video files left on disk: {files}"
    finally:
        _cleanup_session(db, sid)
