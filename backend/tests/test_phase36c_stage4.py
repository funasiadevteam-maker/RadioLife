"""Phase 36c Stage 4 — Screen share + connection quality + Stage 3 polish."""
from __future__ import annotations
import asyncio, json, os, shutil, subprocess, sys, uuid
from pathlib import Path

import pytest

sys.path.insert(0, "/app/backend")

try:
    from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
except Exception: pass

from services import object_storage as obs                    # noqa: E402
from services import podcast_video as pv                          # noqa: E402

TIGRIS_LIVE = (os.environ.get("STORAGE_BACKEND") or "").lower() == "tigris"
pytestmark = pytest.mark.skipif(
    not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris (Stage 4 needs Tigris)")


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _make_av(local: Path, *, sec: float = 1.5, color: str = "red"):
    subprocess.run(
        ["ffmpeg", "-y",
          "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=15:d={sec}",
          "-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}",
          "-c:v", "libvpx", "-b:v", "200k",
          "-c:a", "libvorbis", "-shortest", str(local)],
        check=True, capture_output=True, timeout=30)
    return local.stat().st_size


def _make_screen(local: Path, *, sec: float = 1.5):
    """Solid grey 1920x1080 fake-screen capture."""
    subprocess.run(
        ["ffmpeg", "-y",
          "-f", "lavfi",
          "-i", f"color=c=gray:s=1920x1080:r=10:d={sec}",
          "-c:v", "libvpx", "-b:v", "500k",
          "-an", str(local)],
        check=True, capture_output=True, timeout=30)
    return local.stat().st_size


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


def _seed_session_av_plus_screen(db, *, n: int = 2, host_screen: bool = True
                                                                  ) -> tuple[str, list[str]]:
    """Plant a session with N participants, ALL with mp3+mp4, and (optionally)
    the host with a screen share track on disk. Returns (sid, [pid…])."""
    from services import podcast_recording as pr
    sid = f"prs_s4_{uuid.uuid4().hex[:8]}"
    ch_id = f"ch_s4_{uuid.uuid4().hex[:6]}"
    sess_dir = pr.STORAGE_ROOT / sid
    sess_dir.mkdir(parents=True, exist_ok=True)
    pids: list[str] = []
    colors = ["red", "blue", "green", "yellow"]
    for i in range(n):
        role = "host" if i == 0 else "guest"
        pid = f"prp_s4_{uuid.uuid4().hex[:8]}"; pids.append(pid)
        base = "host" if role == "host" else pid
        webm = sess_dir / f"{base}_raw.webm"
        _make_av(webm, sec=1.0, color=colors[i % len(colors)])
        mp4 = sess_dir / f"{base}_video.mp4"
        rc = pv.transcode_to_mp4(webm, mp4, target_height=1080)
        webm.unlink(missing_ok=True)
        assert rc == 0
        mp3 = sess_dir / f"{base}.mp3"
        subprocess.run(["ffmpeg", "-y", "-i", str(mp4), "-vn",
                                      "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)],
                                    check=True, capture_output=True, timeout=30)
        # Plant a screen capture for host (or first guest if host_screen=False).
        plant_screen = (role == "host" and host_screen)
        if plant_screen:
            screen_webm = sess_dir / f"{base}_screen_raw.webm"
            _make_screen(screen_webm, sec=1.0)
            screen_mp4 = sess_dir / f"{base}_screen.mp4"
            subprocess.run(["ffmpeg", "-y", "-i", str(screen_webm),
                                          "-c:v", "libx264", "-crf", "26", "-preset", "veryfast",
                                          "-vf", "scale=-2:1080", "-an",
                                          "-movflags", "+faststart", str(screen_mp4)],
                                        check=True, capture_output=True, timeout=60)
            screen_webm.unlink()
        run(db.podcast_recording_participants.insert_one({
            "id": pid, "session_id": sid, "user_id": f"u_{role}",
            "role": role, "display_name": role.title(),
            "joined_at": pr._now(), "admitted_at": pr._now(),
            "upload_status": "completed",
            "audio_track_url": f"/local/{sid}/{base}.mp3",
            "video_upload_status": "completed",
            "video_track_url": f"/local/{sid}/{base}_video.mp4",
            **({"screen_upload_status": "completed",
                  "screen_track_url": f"/local/{sid}/{base}_screen.mp4"}
                if plant_screen else {}),
            "created_at": pr._now()}))
    run(db.podcast_recording_sessions.insert_one({
        "id": sid, "creator_id": "u_host", "channel_id": ch_id,
        "title": "Stage 4 av+screen",
        "video_enabled": True, "screen_share_enabled": True,
        "grid_layout": "auto", "status": "processing",
        "started_at": pr._now(), "total_duration_seconds": 1.0,
        "created_at": pr._now(), "updated_at": pr._now()}))
    return sid, pids


def _cleanup(db, sid: str):
    from services import podcast_recording as pr
    s = obs.TigrisStorage()
    for k_suffix in ("mixed.mp3", "mixed.mp4", "audio.mp3"):
        try: s.delete(key=f"podcasts/recordings/{sid}/{k_suffix}")
        except Exception: pass
    parts = run(db.podcast_recording_participants.find(
        {"session_id": sid}, {"id": 1, "role": 1, "_id": 0}).to_list(10))
    for p in parts:
        for kf in [
                f"podcasts/recordings/{sid}/host/audio.mp3",
                f"podcasts/recordings/{sid}/host/video.mp4",
                f"podcasts/recordings/{sid}/host/screen.mp4",
                obs.key_recording_participant_audio(sid, p["id"]),
                obs.key_recording_participant_video(sid, p["id"]),
                obs.key_recording_participant_screen(sid, p["id"])]:
            try: s.delete(key=kf)
            except Exception: pass
    run(db.podcast_recording_sessions.delete_one({"id": sid}))
    run(db.podcast_recording_participants.delete_many({"session_id": sid}))
    run(db.podcast_episodes.delete_many({"recording_session_id": sid}))
    run(db.podcast_recordings.delete_many({"session_id": sid}))
    sess_dir = pr.STORAGE_ROOT / sid
    if sess_dir.exists(): shutil.rmtree(sess_dir, ignore_errors=True)


# ─── 1. Object-storage key builder for screen.mp4 exists ────────
def test_36c_s4_01_screen_key_builder_canonical():
    assert obs.key_recording_participant_screen("sid", "pid") == (
        "podcasts/recordings/sid/pid/screen.mp4")


# ─── 2. resolve_layout forces screen_priority when screen present ──
def test_36c_s4_02_resolve_layout_screen_priority_overrides():
    # Even when user picked 2x2 with 4 participants, screen wins.
    assert pv.resolve_layout("2x2", 4, has_screen=True) == "screen_priority"
    assert pv.resolve_layout("auto", 1, has_screen=True) == "screen_priority"
    # And without screen, Stage 3 contract holds.
    assert pv.resolve_layout("2x2", 4, has_screen=False) == "2x2"


# ─── 3. Finalize with screen share renders screen_priority + Tigris ──
def test_36c_s4_03_finalize_with_screen_uses_screen_priority(tmp_path):
    from services import podcast_recording as pr
    db = _db()
    sid, pids = _seed_session_av_plus_screen(db, n=2, host_screen=True)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        assert ep["video_url"] is not None
        assert ep["video_layout"] == "screen_priority"
        dims = ep["video_dimensions"]
        # screen_priority canvas is still 1920x1080.
        assert dims["width"] == 1920
        assert dims["height"] == 1080
        # Tigris: BOTH mixed.mp4 AND host/screen.mp4 must exist.
        s = obs.TigrisStorage()
        assert s.head(key=obs.key_recording_mixed_video(sid)) is not None
        h_scr = s.head(key=f"podcasts/recordings/{sid}/host/screen.mp4")
        assert h_scr is not None and int(h_scr.get("size") or 0) > 1000
    finally:
        _cleanup(db, sid)


# ─── 4. video_dims alias matches video_dimensions on episode row ──
def test_36c_s4_04_episode_video_dims_alias_present_and_equal():
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_av_plus_screen(db, n=2, host_screen=False)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        assert "video_dimensions" in ep
        assert "video_dims" in ep            # Stage 4 alias
        assert ep["video_dims"] == ep["video_dimensions"]
    finally:
        _cleanup(db, sid)


# ─── 5. RSS alternateEnclosure length matches real bytes ─────────
def test_36c_s4_05_rss_alt_enclosure_length_is_real_bytes():
    """When file_size_bytes_video is set on the episode, RSS must emit
    that exact value as the `length=` attribute (no more zero)."""
    from services import podcast_rss as rss
    db = _db()
    ch_id = f"ch_s4_rss_{uuid.uuid4().hex[:6]}"
    ep_id = f"pep_s4_rss_{uuid.uuid4().hex[:6]}"
    from datetime import datetime, timezone
    try:
        run(db.podcast_channels.insert_one({
            "id": ch_id, "creator_id": "u_rss", "show_title": "S4 RSS",
            "show_description": "rss test", "author_name": "RSS",
            "show_artwork_url": "https://example.com/x.png",
            "category_primary": "Technology", "language": "en-us",
            "explicit": False, "compliance_state": "approved",
            "rss_enabled": True}))
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": ch_id,
            "guid": f"bigfm-ep-{ep_id}",
            "title": "S4 RSS ep", "description": "rss s4",
            "audio_url": f"/api/podcasts/episodes/{ep_id}/audio.mp3",
            "video_url": f"/api/podcasts/episodes/{ep_id}/video.mp4",
            "file_size_bytes": 50_000,
            "file_size_bytes_video": 12_345_678,    # the exact value we'll match
            "duration_seconds": 1.5,
            "publish_status": "published", "publish_state": "published",
            "season": 1, "episode_number": 1, "episode_type": "full",
            "created_at": datetime.now(timezone.utc),
            "published_at": datetime.now(timezone.utc)}))
        xml = run(rss.get_or_build_xml(db, channel_id=ch_id))
        assert 'length="12345678"' in xml, (
            f"Expected length=\"12345678\" in RSS — got:\n"
            f"{[l for l in xml.split(chr(10)) if 'alternateEnclosure' in l]}")
    finally:
        run(db.podcast_episodes.delete_one({"id": ep_id}))
        run(db.podcast_channels.delete_one({"id": ch_id}))


# ─── 6. Connection quality endpoint accepts + persists + caps at 200 ─
def test_36c_s4_06_connection_quality_logs_and_caps():
    import requests
    from services import podcast_recording as pr
    db = _db()
    base = os.environ.get("PUBLIC_BACKEND_URL")
    if not base: pytest.skip("PUBLIC_BACKEND_URL not set")
    sid = f"prs_s4_cq_{uuid.uuid4().hex[:8]}"
    pid = f"prp_s4_cq_{uuid.uuid4().hex[:8]}"
    ws = uuid.uuid4().hex
    try:
        run(db.podcast_recording_sessions.insert_one({
            "id": sid, "status": "recording", "creator_id": "u",
            "channel_id": "ch", "title": "cq"}))
        run(db.podcast_recording_participants.insert_one({
            "id": pid, "session_id": sid, "role": "host",
            "ws_token": ws, "user_id": "u",
            "display_name": "Host",
            "created_at": pr._now()}))
        url = (f"{base}/api/podcasts/recording-sessions/{sid}"
                  f"/participants/{pid}/connection-quality")
        # Post 205 samples; only the last 200 should be retained.
        for i in range(205):
            r = requests.post(url, json={
                "ws_token": ws,
                "score": 0.5 + (i % 10) / 100.0,
                "rtt_ms": 30 + i,
                "jitter_ms": 5,
                "packet_loss_pct": 0.1},
                                              timeout=10)
            assert r.status_code == 200, r.text
        p = run(db.podcast_recording_participants.find_one(
            {"id": pid}, {"connection_quality_log": 1,
                                  "last_connection_quality": 1, "_id": 0}))
        log = p.get("connection_quality_log") or []
        assert len(log) == 200, f"log should be capped at 200, got {len(log)}"
        # FIFO drop: the first 5 entries (rtt 30..34) are gone.
        rtts = [e.get("rtt_ms") for e in log]
        assert 30 not in rtts and 34 not in rtts
        assert max(rtts) == 30 + 204    # last sample retained
        assert p["last_connection_quality"]["rtt_ms"] == 30 + 204
    finally:
        run(db.podcast_recording_participants.delete_one({"id": pid}))
        run(db.podcast_recording_sessions.delete_one({"id": sid}))


# ─── 7. Connection quality aggregator endpoint shape ─────────────
def test_36c_s4_07_connection_quality_aggregator_shape():
    import requests
    from services import podcast_recording as pr
    base = os.environ.get("PUBLIC_BACKEND_URL")
    if not base: pytest.skip("PUBLIC_BACKEND_URL not set")
    db = _db()
    sid = f"prs_s4_cqa_{uuid.uuid4().hex[:8]}"
    pid = f"prp_s4_cqa_{uuid.uuid4().hex[:8]}"
    try:
        run(db.podcast_recording_sessions.insert_one({
            "id": sid, "status": "recording", "creator_id": "u_admin",
            "channel_id": "ch", "title": "cq"}))
        run(db.podcast_recording_participants.insert_one({
            "id": pid, "session_id": sid, "role": "host",
            "user_id": "u_admin", "display_name": "Host",
            "connection_quality_log": [
                {"score": 0.8, "rtt_ms": 40, "jitter_ms": 5,
                  "packet_loss_pct": 0.1, "ts": "2026-06-04T00:00:00Z"},
                {"score": 0.6, "rtt_ms": 60, "jitter_ms": 8,
                  "packet_loss_pct": 0.2, "ts": "2026-06-04T00:00:05Z"}],
            "last_connection_quality": {"score": 0.6, "rtt_ms": 60,
                                                                "jitter_ms": 8,
                                                                "packet_loss_pct": 0.2,
                                                                "ts": "2026-06-04T00:00:05Z"},
            "created_at": pr._now()}))
        # Admin login.
        r = requests.post(f"{base}/api/auth/login",
                                              json={"email": "admin@bigfm.dubai",
                                                          "password": "AdminPass123!"},
                                              timeout=10)
        tok = r.json()["session_token"]
        rr = requests.get(
            f"{base}/api/podcasts/recording-sessions/{sid}/connection-quality",
            headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        assert rr.status_code == 200, rr.text
        body = rr.json()
        assert body["session_id"] == sid
        assert len(body["participants"]) == 1
        row = body["participants"][0]
        assert row["participant_id"] == pid
        assert row["samples"] == 2
        assert row["avg_score"] == 0.7
        assert row["last"]["rtt_ms"] == 60
    finally:
        run(db.podcast_recording_participants.delete_one({"id": pid}))
        run(db.podcast_recording_sessions.delete_one({"id": sid}))


# ─── 8. LiveKit token grants can_publish_screen when video_enabled ──
def test_36c_s4_08_livekit_token_grants_publish_screen(monkeypatch):
    """The host token mint must include can_publish_screen=True when
    session.video_enabled. We inspect the perms passed to the mock."""
    from services import podcast_recording as pr
    from services import livekit_client as lk
    db = _db()
    ch_id = f"ch_s4_tok_{uuid.uuid4().hex[:6]}"
    run(db.podcast_recording_sessions.delete_many({"status":
        {"$in": ["pending", "recording", "processing"]}}))
    captured: dict = {}
    real_mint = lk.mint_room_token
    def _spy(*args, **kw):
        captured.update(kw)
        return real_mint(*args, **kw)
    monkeypatch.setattr(lk, "mint_room_token", _spy)
    sess = None
    try:
        sess = run(pr.create_session(db, creator_id="u_tok",
                                                              channel_id=ch_id, title="tok",
                                                              video_enabled=True))
        perms = captured.get("permissions") or {}
        assert perms.get("can_publish_video") is True
        assert perms.get("can_publish_screen") is True
        # When video_enabled=False, screen perm must be False too.
        captured.clear()
        run(db.podcast_recording_sessions.delete_one({"id": sess["session_id"]}))
        sess = run(pr.create_session(db, creator_id="u_tok",
                                                              channel_id=ch_id, title="tok2",
                                                              video_enabled=False))
        perms = captured.get("permissions") or {}
        assert perms.get("can_publish_screen") is False
    finally:
        if sess: run(db.podcast_recording_sessions.delete_one(
                                            {"id": sess["session_id"]}))


# ─── 9. Screen tracks land in Tigris + local cleanup respected ───
def test_36c_s4_09_screen_track_offloaded_and_local_cleaned():
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_av_plus_screen(db, n=2, host_screen=True)
    try:
        run(pr.finalize_session(db, session_id=sid))
        sess_dir = pr.STORAGE_ROOT / sid
        leftover = (list(sess_dir.rglob("*")) if sess_dir.exists() else [])
        assert [p for p in leftover if p.is_file()] == []
        # Screen key must exist on Tigris.
        s = obs.TigrisStorage()
        h = s.head(key=f"podcasts/recordings/{sid}/host/screen.mp4")
        assert h is not None and int(h.get("size") or 0) > 1000
    finally:
        _cleanup(db, sid)


# ─── 10. Screen-priority finalize works with 1 participant + 1 screen ──
def test_36c_s4_10_finalize_1participant_with_screen_no_hstack_inputs_1():
    """Regression for the tester-found blocker: when ONLY the host participant
    is in the bottom strip, the screen-priority filter graph previously
    wrapped them in hstack=inputs=1 which ffmpeg rejects. After the fix,
    finalize must produce a real video with layout=screen_priority and a
    nonzero file_size_bytes_video."""
    from services import podcast_recording as pr
    db = _db()
    sid, _ = _seed_session_av_plus_screen(db, n=1, host_screen=True)
    try:
        out = run(pr.finalize_session(db, session_id=sid))
        ep = run(db.podcast_episodes.find_one(
            {"id": out["episode_id"]}, {"_id": 0}))
        assert ep["video_url"] is not None, (
            f"video_url should be set; got ep={ep}")
        assert ep["video_layout"] == "screen_priority"
        assert int(ep.get("file_size_bytes_video") or 0) > 0, (
            f"file_size_bytes_video must be > 0; got {ep.get('file_size_bytes_video')}")
        dims = ep["video_dimensions"]
        assert dims["width"] == 1920 and dims["height"] == 1080
        # Session also exposes grid_layout_resolved for tester ergonomics.
        sess = run(db.podcast_recording_sessions.find_one(
            {"id": sid}, {"_id": 0}))
        assert sess.get("grid_layout_resolved") == "screen_priority"
        # And Tigris has the mixed mp4.
        s = obs.TigrisStorage()
        h = s.head(key=obs.key_recording_mixed_video(sid))
        assert h is not None and int(h.get("size") or 0) > 1000
    finally:
        _cleanup(db, sid)
