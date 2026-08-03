"""Phase 36c Stage 1 — Solo Audio Recording Studio tests (10 cases).

Covers:
  1. LiveKit MOCK token has the deterministic shape.
  2. Session create → start → stop state machine.
  3. 10-min server-side duration cap (stop with >600s rejects).
  4. 100MB upload cap (synthetic 101MB payload rejects).
  5. Idempotent upload-track (second call returns 409).
  6. NEW disk gate — concurrent session blocked with `disk_constrained` 409
      + recording_disk_events audit row written.
  7. NEW disk gate — mid-upload `disk_pressure` 503 with Retry-After.
  8. Transcode-and-delete-source: raw webm gone after upload completes.
  9. Finalize creates podcast_episodes draft and auto-fires 36b transcription.
 10. cancel_session removes storage dir and flips status to cancelled.
"""
import asyncio, os, secrets, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass
from motor.motor_asyncio import AsyncIOMotorClient

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN   = os.environ.get("DB_NAME",   "bigfm")


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed(): raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(MONGO)[DBN]


def _seed_creator_channel(db):
    uid    = f"u_36c_{secrets.token_hex(3)}"
    cid    = f"crt_36c_{secrets.token_hex(3)}"
    chid = f"ch_36c_{secrets.token_hex(3)}"
    run(db.podcast_creators.insert_one(
        {"id": cid, "user_id": uid, "display_name": "T",
          "contact_email": "t@bigfm.dubai", "market": "dubai",
          "application_status": "approved",
          "applied_at": datetime.now(timezone.utc)}))
    run(db.podcast_channels.insert_one(
        {"id": chid, "creator_id": cid, "title": "36c Test", "slug": f"36c-{secrets.token_hex(3)}",
          "category": "tech", "language": "en", "active": True,
          "approval_status": "approved",
          "created_at": datetime.now(timezone.utc)}))
    return uid, cid, chid


def _make_tiny_webm(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                                "-i", "sine=frequency=440:duration=2",
                                "-codec:a", "libopus", "-b:a", "32k", str(path)],
                              check=False, capture_output=True, timeout=30)


def _clean_active_sessions(db):
    run(db.podcast_recording_sessions.update_many(
        {"status": {"$in": ["recording", "processing", "pending"]}},
        {"$set": {"status": "cancelled"}}))


# ─── 1. LiveKit MOCK token shape ─────────────────────────
def test_36c_01_livekit_mock_token_shape():
    """Phase 36c Stage 4 A1 — mock tokens are now base64url(claims_json).
    Decode and assert the claims match the inputs."""
    import base64, json
    from services import livekit_client as lk
    assert lk.is_live() is False
    t = lk.mint_room_token(room_name="bigfm-x", identity="host-y", role="host",
                                                    permissions={"can_publish_video": True,
                                                                              "can_publish_screen": True})
    assert t.startswith("mock_lk_") and not t.startswith("mock_lk_token_")
    pad = "=" * (-len(t[len("mock_lk_"):]) % 4)
    claims = json.loads(base64.urlsafe_b64decode(t[len("mock_lk_"):] + pad))
    assert claims["room"] == "bigfm-x"
    assert claims["identity"] == "host-y"
    assert claims["role"] == "host"
    assert claims["can_publish_video"] is True
    assert claims["can_publish_screen"] is True
    r = lk.create_room(room_name="bigfm-x")
    assert r["room_name"] == "bigfm-x" and r["sid"].startswith("mock_room_sid_")
    s = lk.status()
    assert s["mode"] == "mock" and s["is_live"] is False


# ─── 2. Session create → start → stop state machine ─────
def test_36c_02_session_state_machine():
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid,
                                                          title="X", user_id="u_x"))
    sid = s["session_id"]
    row = run(db.podcast_recording_sessions.find_one({"id": sid}))
    assert row["status"] == "pending"
    run(rec.start_session(db, session_id=sid))
    assert run(db.podcast_recording_sessions.find_one({"id": sid}))["status"] == "recording"
    run(rec.stop_session(db, session_id=sid, client_duration_seconds=10.0))
    assert run(db.podcast_recording_sessions.find_one({"id": sid}))["status"] == "processing"
    _clean_active_sessions(db)


# ─── 3. 10-min duration cap ──────────────────────────────
def test_36c_03_duration_cap_enforced():
    from fastapi import HTTPException
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    run(rec.start_session(db, session_id=s["session_id"]))
    with pytest.raises(HTTPException) as ei:
        run(rec.stop_session(db, session_id=s["session_id"],
                                              client_duration_seconds=601.0))
    assert ei.value.status_code == 400
    assert ei.value.detail["code"] == "duration_exceeded"
    _clean_active_sessions(db)


# ─── 4. 100MB upload cap ──────────────────────────────
def test_36c_04_upload_size_cap():
    """101 MB synthetic stream rejected mid-flight."""
    from fastapi import HTTPException
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    run(rec.start_session(db, session_id=s["session_id"]))

    # Build a fake UploadFile that streams >100MB of zeros.
    class FakeUpload:
        filename = "track.webm"
        def __init__(self): self.served = 0; self.cap = 101 * 1024 * 1024
        async def read(self, n):
            if self.served >= self.cap: return b""
            chunk = b"\0" * min(n, self.cap - self.served)
            self.served += len(chunk); return chunk

    with pytest.raises(HTTPException) as ei:
        run(rec.upload_track(db, session_id=s["session_id"], role="host",
                                                  upload=FakeUpload(), user_id="u_x"))
    assert ei.value.status_code == 413
    assert ei.value.detail["code"] == "upload_too_large"
    _clean_active_sessions(db)


# ─── 5. Idempotent upload (409 on duplicate) ─────────────
def test_36c_05_idempotent_upload():
    from fastapi import HTTPException, UploadFile
    import io
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    sid = s["session_id"]
    run(rec.start_session(db, session_id=sid))

    src = Path(f"/tmp/36c_tiny_{sid}.webm")
    _make_tiny_webm(src)
    with open(src, "rb") as f:
        upload = UploadFile(filename="track.webm", file=io.BytesIO(f.read()))
    run(rec.upload_track(db, session_id=sid, role="host", upload=upload))
    # Second upload for same role → 409
    with open(src, "rb") as f:
        upload2 = UploadFile(filename="track.webm", file=io.BytesIO(f.read()))
    with pytest.raises(HTTPException) as ei:
        run(rec.upload_track(db, session_id=sid, role="host", upload=upload2))
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "track_already_uploaded"
    _clean_active_sessions(db)


# ─── 6. Concurrent session → disk_constrained 409 + audit row ─
def test_36c_06_concurrent_session_disk_constrained():
    from fastapi import HTTPException
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s1 = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="A"))
    run(rec.start_session(db, session_id=s1["session_id"]))
    pre_events = run(db.recording_disk_events.count_documents({"code": "disk_constrained"}))
    with pytest.raises(HTTPException) as ei:
        run(rec.create_session(db, creator_id=cid, channel_id=chid, title="B"))
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "disk_constrained"
    post_events = run(db.recording_disk_events.count_documents({"code": "disk_constrained"}))
    assert post_events == pre_events + 1, "audit row not written"
    _clean_active_sessions(db)


# ─── 7. Mid-upload disk_pressure 503 ────────────────────
def test_36c_07_disk_pressure_aborts_upload():
    from fastapi import HTTPException, UploadFile
    import io
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    sid = s["session_id"]
    run(rec.start_session(db, session_id=sid))
    # Patch _free_bytes to return <200MB.
    with patch.object(rec, "_free_bytes", return_value=100 * 1024 * 1024):
        class FakeUpload:
            filename = "track.webm"
            def __init__(self): self.served = 0
            async def read(self, n):
                if self.served >= 6 * 1024 * 1024: return b""
                self.served += n; return b"\0" * n
        pre_events = run(db.recording_disk_events.count_documents({"code": "disk_pressure"}))
        with pytest.raises(HTTPException) as ei:
            run(rec.upload_track(db, session_id=sid, role="host",
                                                      upload=FakeUpload(), user_id="u_x"))
        assert ei.value.status_code == 503
        assert ei.value.detail["code"] == "disk_pressure"
        assert ei.value.headers and ei.value.headers.get("Retry-After") == "60"
        post_events = run(db.recording_disk_events.count_documents({"code": "disk_pressure"}))
        assert post_events == pre_events + 1
    # Cleanup any partial files.
    _clean_active_sessions(db)


# ─── 8. Transcode-and-delete-source ──────────────────────
def test_36c_08_transcode_and_delete_source():
    from fastapi import UploadFile
    import io
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    sid = s["session_id"]
    run(rec.start_session(db, session_id=sid))
    src = Path(f"/tmp/36c_tiny_{sid}_b.webm")
    _make_tiny_webm(src)
    with open(src, "rb") as f:
        upload = UploadFile(filename="track.webm", file=io.BytesIO(f.read()))
    run(rec.upload_track(db, session_id=sid, role="host", upload=upload))
    sess_dir = Path(f"/app/backend/storage/podcasts/recordings/{sid}")
    raw = list(sess_dir.glob("host_raw*"))
    mp3 = sess_dir / "host.mp3"
    assert raw == [], f"raw source should be deleted; found {raw}"
    assert mp3.exists() and mp3.stat().st_size > 0
    _clean_active_sessions(db)


# ─── 9. Finalize creates draft + auto-fires 36b ─────────
def test_36c_09_finalize_creates_episode_and_fires_transcription():
    from fastapi import UploadFile
    import io
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid,
                                                          title="Finalize Test"))
    sid = s["session_id"]
    run(rec.start_session(db, session_id=sid))
    src = Path(f"/tmp/36c_tiny_{sid}_c.webm"); _make_tiny_webm(src)
    with open(src, "rb") as f:
        upload = UploadFile(filename="track.webm", file=io.BytesIO(f.read()))
    run(rec.upload_track(db, session_id=sid, role="host", upload=upload))
    run(rec.stop_session(db, session_id=sid, client_duration_seconds=2.0))
    fin = run(rec.finalize_session(db, session_id=sid))
    assert fin["episode_id"].startswith("pep_")
    ep = run(db.podcast_episodes.find_one({"id": fin["episode_id"]}))
    assert ep["publish_status"] == "draft"
    assert ep["recording_session_id"] == sid
    # 36b auto-fire: transcript row exists with status=completed (mock).
    tr = run(db.podcast_transcripts.find_one({"episode_id": fin["episode_id"]}))
    assert tr is not None and tr["status"] in ("completed", "processing")
    _clean_active_sessions(db)


# ─── 10. cancel_session cleans storage + flips status ───
def test_36c_10_cancel_cleans_storage():
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    sid = s["session_id"]
    sess_dir = Path(f"/app/backend/storage/podcasts/recordings/{sid}")
    sess_dir.mkdir(parents=True, exist_ok=True)
    (sess_dir / "stub.txt").write_text("hello")
    run(rec.cancel_session(db, session_id=sid))
    assert not sess_dir.exists(), "session dir should be removed"
    row = run(db.podcast_recording_sessions.find_one({"id": sid}))
    assert row["status"] == "cancelled"


# ─── 11. Bug fix — client_duration_seconds fast-fail on upload ─
def test_36c_11_client_duration_fast_fail_on_upload():
    """Client-reported duration > 600s rejects BEFORE any byte is streamed.
    No partial files written. No transcode. Pure short-circuit at the top."""
    from fastapi import HTTPException, UploadFile
    import io
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    sid = s["session_id"]
    run(rec.start_session(db, session_id=sid))
    src = Path(f"/tmp/36c_tiny_{sid}_fastfail.webm")
    _make_tiny_webm(src)
    with open(src, "rb") as f:
        upload = UploadFile(filename="track.webm", file=io.BytesIO(f.read()))
    with pytest.raises(HTTPException) as ei:
        run(rec.upload_track(db, session_id=sid, role="host",
                                                  upload=upload,
                                                  client_duration_seconds=750.0,
                                                  user_id="u_x"))
    assert ei.value.status_code == 400
    assert ei.value.detail["code"] == "duration_exceeded"
    assert ei.value.detail["cap_seconds"] == rec.RECORDING_CAP_SEC
    # Confirm no partial files landed on disk for this session.
    sess_dir = Path(f"/app/backend/storage/podcasts/recordings/{sid}")
    if sess_dir.exists():
        assert not list(sess_dir.glob("host_raw*")), \
              "fast-fail must not write any source bytes"
        assert not (sess_dir / "host.mp3").exists(), \
              "fast-fail must not produce an mp3"
    _clean_active_sessions(db)


# ─── 12. Bug fix — server-side ffprobe duration gate ─────
def test_36c_12_server_ffprobe_duration_rejects_and_deletes_mp3():
    """Even if the client lies (or omits client_duration_seconds), the server
    runs ffprobe on the transcoded mp3 and rejects > 600s. The mp3 must be
    deleted, the participant row flipped to rejected_duration, and an audit
    row written with code=duration_exceeded."""
    from fastapi import HTTPException, UploadFile
    import io
    from services import podcast_recording as rec
    db = _db(); _clean_active_sessions(db)
    _, cid, chid = _seed_creator_channel(db)
    s = run(rec.create_session(db, creator_id=cid, channel_id=chid, title="X"))
    sid = s["session_id"]
    run(rec.start_session(db, session_id=sid))
    src = Path(f"/tmp/36c_tiny_{sid}_srvgate.webm")
    _make_tiny_webm(src)
    pre_events = run(db.recording_disk_events.count_documents(
        {"code": "duration_exceeded"}))
    # Patch ffprobe_duration to return 700s, simulating a long upload that
    # snuck past the client fast-fail. We patch it on the services.podcasts
    # module (where it lives) so the lazy import inside upload_track picks
    # up the mock.
    with patch("services.podcasts.ffprobe_duration", return_value=700.0):
        with open(src, "rb") as f:
            upload = UploadFile(filename="track.webm",
                                              file=io.BytesIO(f.read()))
        with pytest.raises(HTTPException) as ei:
            run(rec.upload_track(db, session_id=sid, role="host",
                                                      upload=upload,
                                                      client_duration_seconds=0.0,
                                                      user_id="u_x"))
    assert ei.value.status_code == 400
    assert ei.value.detail["code"] == "duration_exceeded"
    assert ei.value.detail["server_duration_seconds"] == 700.0
    # mp3 must be gone.
    sess_dir = Path(f"/app/backend/storage/podcasts/recordings/{sid}")
    assert not (sess_dir / "host.mp3").exists(), \
              "mp3 must be deleted after server gate trips"
    # Participant flipped to rejected_duration.
    p = run(db.podcast_recording_participants.find_one(
        {"session_id": sid, "role": "host"}))
    assert p["upload_status"] == "rejected_duration"
    # Audit row added.
    post_events = run(db.recording_disk_events.count_documents(
        {"code": "duration_exceeded"}))
    assert post_events == pre_events + 1, "duration_exceeded audit row missing"
    _clean_active_sessions(db)


# ─── 13. Bug fix — path parity 308 redirect for disk-events ─
def test_36c_13_disk_events_path_parity_308_redirect():
    """The legacy admin disk-events path /api/podcasts/admin/recording-disk-events
    must respond with a 308 Permanent Redirect to the canonical
    /api/admin/podcasts/recording-disk-events. Query string preserved."""
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as cli:
        r = cli.get(
            "/api/podcasts/admin/recording-disk-events?limit=10",
            follow_redirects=False)
    assert r.status_code == 308, f"expected 308, got {r.status_code}"
    loc = r.headers.get("location") or r.headers.get("Location")
    assert loc is not None, "Location header missing on 308"
    assert loc.endswith(
        "/api/admin/podcasts/recording-disk-events?limit=10"), \
              f"redirect target wrong: {loc}"
