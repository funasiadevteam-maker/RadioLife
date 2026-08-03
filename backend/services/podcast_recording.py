"""Phase 36c Stage 1 — Solo Audio Recording Studio service.

Stage 1 = solo audio only (no guests, no video, no screen share). The
schema + service shape is forward-compatible with stages 2-4 (guest
invites, video, screen share) but those endpoints are not implemented
in this dispatch.

Collections:
    podcast_recording_sessions    {id, creator_id, channel_id, title,
                                                            status, recording_mode, livekit_*,
                                                            mixed_audio_url, total_duration_seconds,
                                                            episode_id, started_at, ended_at,
                                                            created_at, updated_at}
    podcast_recording_participants {id, session_id, user_id, role,
                                                            joined_at, left_at,
                                                            audio_track_url, upload_status,
                                                            error_message, device_info_json,
                                                            consent_accepted, created_at}
    recording_disk_events                {id, timestamp, free_bytes_at_event,
                                                            code, session_id, route, user_id}

Disk gates (Stage 1 — disciplined-disk regime):
    - Only ONE active session at a time across the whole platform.
    - Mid-upload check every 5 MB: if free<200 MB → abort, 503 + Retry-After.
    - Transcode-and-delete-source: raw webm deleted as soon as mp3 lands.
"""
from __future__ import annotations
import asyncio
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

logger = logging.getLogger("bigfm.podcast_recording")

# Hard caps for Stage 1 — disciplined disk regime.
RECORDING_CAP_SEC                 = 600          # 10 min
UPLOAD_CAP_BYTES                  = 100 * 1024 * 1024    # 100 MB
DISK_PRESSURE_FLOOR_BYTES = 200 * 1024 * 1024    # abort if free<200MB mid-upload
DISK_CHECK_EVERY_BYTES      = 5    * 1024 * 1024    # check every 5MB streamed
CHUNK_BYTES                              = 1    * 1024 * 1024    # 1 MB stream chunk

STORAGE_ROOT = Path("/app/backend/storage/podcasts/recordings")

ACTIVE_STATES = ("recording", "processing")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _free_bytes() -> int:
    return shutil.disk_usage("/app").free


async def _record_disk_event(db, *, code: str, route: str,
                                                            session_id: Optional[str] = None,
                                                            user_id: Optional[str] = None) -> None:
    """Audit row for every disk-gate trigger. Lets us see if gates actually fire."""
    try:
        await db.recording_disk_events.insert_one({
            "id":                            _gen("rde"),
            "timestamp":                _now(),
            "free_bytes_at_event": _free_bytes(),
            "code":                         code,
            "route":                        route,
            "session_id":              session_id,
            "user_id":                    user_id,
        })
    except Exception as e:
        logger.warning("[36c] disk_event log failed (non-fatal): %s", e)


async def has_active_session(db) -> bool:
    """Stage 1 invariant: only ONE active session at a time across the platform."""
    n = await db.podcast_recording_sessions.count_documents(
        {"status": {"$in": list(ACTIVE_STATES)}})
    return n > 0


async def create_session(db, *, creator_id: str, channel_id: str,
                                              title: str, recording_mode: str = "solo",
                                              user_id: Optional[str] = None,
                                              force_mock: bool = False,
                                              video_enabled: bool = False,
                                              grid_layout: str = "auto") -> dict:
    """Stage 1 — create a session. Mints host LiveKit token via the
    livekit_client (MOCK by default). Enforces the platform-wide
    single-active-session disk gate. Stage 2 added `force_mock` (admin
    canary flag) which is persisted on the session row so subsequent
    token-mints stay on the mock path even after env vars flip live.

    Stage 3 (full-scope) adds `video_enabled` + `grid_layout`. When
    video_enabled=True the host LiveKit token grants can_publish_video,
    and the finalize path renders a 1080p grid mp4 alongside the audio
    mix."""
    if await has_active_session(db):
        await _record_disk_event(db, code="disk_constrained",
                                                          route="create_session",
                                                          user_id=user_id)
        from fastapi import HTTPException
        raise HTTPException(409, {"code": "disk_constrained",
            "message": "Another recording session is active. Try again when it finishes."})
    from services import livekit_client as lk
    sid          = _gen("prs")
    room    = f"bigfm-{sid}"
    host_token = lk.mint_room_token(room_name=room, identity=f"host-{creator_id}",
                                                                    role="host",
                                                                    permissions={"can_publish": True,
                                                                                              "can_subscribe": True,
                                                                                              "can_publish_data": True,
                                                                                              "can_publish_video": bool(video_enabled),
                                                                                              "can_publish_screen": bool(video_enabled)})
    if force_mock and not host_token.startswith("mock_lk_"):
        from services import livekit_client as _lk
        host_token = _lk.mint_room_token(room_name=room,
                                                                          identity=f"host-{creator_id}",
                                                                          role="host",
                                                                          permissions={"can_publish": True,
                                                                                                    "can_subscribe": True,
                                                                                                    "can_publish_data": True,
                                                                                                    "can_publish_video": bool(video_enabled),
                                                                                                    "can_publish_screen": bool(video_enabled)})
    room_info = lk.create_room(room_name=room, max_participants=4)
    row = {
        "id":                                     sid,
        "creator_id":                     creator_id,
        "channel_id":                     channel_id,
        "title":                                title or "Untitled Recording",
        "recording_mode":            (recording_mode if recording_mode in
                                                            ("solo", "interview", "panel") else "solo"),
        "video_enabled":                 bool(video_enabled),
        "grid_layout":                       (grid_layout if grid_layout in
                                                            ("auto", "side_by_side", "2x2",
                                                              "speaker_view") else "auto"),
        "screen_share_enabled": False,
        "status":                                "pending",
        "livekit_room_name":          room,
        "livekit_room_sid":             room_info.get("sid"),
        "livekit_url":                       __import__("services.livekit_client", fromlist=["livekit_url"]).livekit_url(),
        "force_mock":                       bool(force_mock),
        "mixed_audio_url":              None,
        "mixed_video_url":              None,
        "total_duration_seconds": 0,
        "episode_id":                       None,
        "diarization_speaker_map": {},
        "started_at":                       None,
        "ended_at":                          None,
        "created_at":                       _now(),
        "updated_at":                       _now(),
    }
    await db.podcast_recording_sessions.insert_one(row)
    # Insert the host participant row. Stage 2 — `lobby_status: "admitted"`
    # is set inline so the 4-participant cap math counts the host too.
    p = {
        "id":                            _gen("prp"),
        "session_id":             sid,
        "user_id":                    user_id,
        "role":                         "host",
        "guest_name":             None,
        "guest_email":           None,
        "display_name":         "Host",
        "joined_at":                _now(),
        "left_at":                    None,
        "admitted_at":          _now(),
        "kicked_at":                None,
        "audio_track_url":   None,
        "video_track_url":   None,
        "upload_status":      "pending",
        "consent_accepted": True,    # host implicitly consents by starting
        "device_info_json": {},
        "error_message":      None,
        "lobby_status":        "admitted",
        "ws_token":                None,
        "created_at":             _now(),
    }
    await db.podcast_recording_participants.insert_one(p)
    # Funnel event (best-effort)
    try:
        from services import podcast_guests as pg
        await pg.log_funnel(db, event="session_started", user_id=user_id,
                                                session_id=sid, channel_id=channel_id,
                                                meta={"force_mock": bool(force_mock)})
    except Exception: pass
    return {
        "session_id":             sid,
        "livekit_room_name": room,
        "livekit_token":         host_token,
        "livekit_url":             row["livekit_url"],
        "force_mock":             bool(force_mock),
        "mode":                         "mock" if (force_mock or not lk.is_live()) else "live",
    }


async def start_session(db, *, session_id: str) -> dict:
    s = await db.podcast_recording_sessions.find_one_and_update(
        {"id": session_id, "status": "pending"},
        {"$set": {"status": "recording", "started_at": _now(),
                      "updated_at": _now()}},
        return_document=True)
    if not s:
        from fastapi import HTTPException
        raise HTTPException(404, "session_not_found_or_not_pending")
    s.pop("_id", None)
    return s


async def stop_session(db, *, session_id: str,
                                          client_duration_seconds: float) -> dict:
    if client_duration_seconds and client_duration_seconds > RECORDING_CAP_SEC:
        from fastapi import HTTPException
        raise HTTPException(400, {"code": "duration_exceeded",
            "message": f"Stage 1 cap is {RECORDING_CAP_SEC}s "
                              f"(got {client_duration_seconds:.1f}s)."})
    s = await db.podcast_recording_sessions.find_one_and_update(
        {"id": session_id, "status": "recording"},
        {"$set": {"status": "processing",
                      "ended_at": _now(),
                      "total_duration_seconds": float(client_duration_seconds or 0),
                      "updated_at": _now()}},
        return_document=True)
    if not s:
        from fastapi import HTTPException
        raise HTTPException(404, "session_not_found_or_not_recording")
    s.pop("_id", None)
    return s


async def upload_track(db, *, session_id: str, role: str,
                                          upload: UploadFile,
                                          client_duration_seconds: float = 0,
                                          user_id: Optional[str] = None,
                                          participant_id: Optional[str] = None,
                                          video_upload: Optional[UploadFile] = None,
                                          screen_upload: Optional[UploadFile] = None
                                          ) -> dict:
    """Streaming multipart upload with mid-flight disk-pressure abort + dual
    duration gate (client fast-fail + server-side ffprobe authoritative).

    Stage 2: `participant_id` distinguishes which guest is uploading. When
    role='guest', participant_id is REQUIRED and the file lands at
    `{participant_id}.mp3`. role='host' still writes `host.mp3`.

    Reads `upload` in 1MB chunks, writes directly to disk, and every 5MB
    checks `shutil.disk_usage('/app').free`. If free<200MB at any check,
    aborts the upload, deletes the partial file, returns 503.

    On success: transcodes the source to mp3, then runs ffprobe to read the
    actual duration. If duration > 600s, **deletes the mp3** and returns
    400 with `code: "duration_exceeded"` (server-decoded). On accept:
    **deletes the raw source immediately** (transcode-and-delete-source),
    persists `audio_track_url`, flips `upload_status: completed`.
    """
    from fastapi import HTTPException, Response
    # Client fast-fail (defense in depth — cheap, easy to bypass; that's fine).
    if client_duration_seconds and client_duration_seconds > RECORDING_CAP_SEC:
        raise HTTPException(400, {"code": "duration_exceeded",
            "message": f"Recording exceeded the 10-minute Stage 1 cap "
                              f"(client-reported: {client_duration_seconds:.1f}s).",
            "cap_seconds": RECORDING_CAP_SEC})
    # Resolve the target participant row (Stage 2 — supports guest tracks).
    if role == "guest" and not participant_id:
        raise HTTPException(400, {"code": "participant_id_required",
            "message": "Guest uploads require participant_id."})
    part_q: dict = {"session_id": session_id, "role": role}
    if participant_id: part_q["id"] = participant_id
    part = await db.podcast_recording_participants.find_one(part_q)
    if not part:
        raise HTTPException(404, "participant_not_found")
    # Idempotency: 409 if this participant already uploaded.
    if part.get("upload_status") == "completed":
        await _record_disk_event(db, code="track_already_uploaded",
                                                          route="upload_track",
                                                          session_id=session_id, user_id=user_id)
        raise HTTPException(409, {"code": "track_already_uploaded",
            "message": "This participant has already uploaded an audio track."})

    sess_dir = STORAGE_ROOT / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    file_base = "host" if role == "host" else part["id"]
    # Sniff the filename's extension; default webm (Chromium MediaRecorder).
    src_name = upload.filename or "track.webm"
    src_ext    = Path(src_name).suffix.lower() or ".webm"
    if src_ext not in (".webm", ".mp4", ".m4a", ".ogg", ".mp3", ".wav"):
        src_ext = ".webm"
    src_path = sess_dir / f"{file_base}_raw{src_ext}"
    total = 0
    last_check_at = 0
    try:
        with open(src_path, "wb") as f:
            while True:
                chunk = await upload.read(CHUNK_BYTES)
                if not chunk: break
                total += len(chunk)
                if total > UPLOAD_CAP_BYTES:
                    f.close()
                    src_path.unlink(missing_ok=True)
                    raise HTTPException(413, {"code": "upload_too_large",
                        "message": f"Stage 1 cap is {UPLOAD_CAP_BYTES//(1024*1024)} MB."})
                # Mid-upload disk-pressure check.
                if total - last_check_at >= DISK_CHECK_EVERY_BYTES:
                    last_check_at = total
                    if _free_bytes() < DISK_PRESSURE_FLOOR_BYTES:
                        f.close()
                        src_path.unlink(missing_ok=True)
                        await _record_disk_event(db, code="disk_pressure",
                                                                          route="upload_track",
                                                                          session_id=session_id,
                                                                          user_id=user_id)
                        raise HTTPException(503,
                            {"code": "disk_pressure",
                              "message": "Disk pressure during upload, retry shortly."},
                            headers={"Retry-After": "60"})
                f.write(chunk)
    except HTTPException:
        # Re-raise (already cleaned up).
        raise
    except Exception as e:
        src_path.unlink(missing_ok=True)
        await db.podcast_recording_participants.update_one(
            {"id": part["id"]},
            {"$set": {"upload_status": "failed",
                          "error_message": f"stream_failed: {str(e)[:200]}"}})
        raise HTTPException(500, {"code": "upload_stream_failed",
                                                      "message": str(e)[:200]})

    # Transcode src → mp3. Run blocking subprocess in executor.
    mp3_path = sess_dir / f"{file_base}.mp3"
    proc = await asyncio.get_event_loop().run_in_executor(
        None, _ffmpeg_to_mp3, src_path, mp3_path)
    if proc != 0 or not mp3_path.exists() or mp3_path.stat().st_size == 0:
        await db.podcast_recording_participants.update_one(
            {"id": part["id"]},
            {"$set": {"upload_status": "failed",
                          "error_message": f"ffmpeg_rc={proc}"}})
        src_path.unlink(missing_ok=True)
        raise HTTPException(500, {"code": "transcode_failed",
                                                      "message": "FFmpeg could not transcode the uploaded audio."})

    # Transcode-and-delete-source.
    src_path.unlink(missing_ok=True)

    # Phase 36c Stage 1 bug fix — authoritative server-side duration gate.
    from services.podcasts import ffprobe_duration
    server_duration = ffprobe_duration(mp3_path) or 0.0
    if server_duration > RECORDING_CAP_SEC:
        mp3_path.unlink(missing_ok=True)
        await db.podcast_recording_participants.update_one(
            {"id": part["id"]},
            {"$set": {"upload_status":  "rejected_duration",
                          "error_message": f"server_duration={server_duration:.1f}s"}})
        await _record_disk_event(db, code="duration_exceeded",
                                                          route="upload_track",
                                                          session_id=session_id,
                                                          user_id=user_id)
        raise HTTPException(400, {"code": "duration_exceeded",
            "message": f"Recording exceeded the 10-minute Stage 1 cap "
                              f"(server-verified: {server_duration:.1f}s).",
            "cap_seconds": RECORDING_CAP_SEC,
            "server_duration_seconds": server_duration})

    audio_url = (f"/api/podcasts/recording-sessions/{session_id}"
                          f"/audio/{file_base}.mp3")
    await db.podcast_recording_participants.update_one(
        {"id": part["id"]},
        {"$set": {"upload_status":    "completed",
                      "audio_track_url": audio_url,
                      "left_at":               _now()}})

    # ── Phase 36c Stage 3 — optional per-participant video upload ──
    video_result: dict = {}
    if video_upload is not None:
        video_result = await _ingest_participant_video(
            db, session_id=session_id, sess_dir=sess_dir,
            file_base=file_base, part_id=part["id"],
            video_upload=video_upload, user_id=user_id)

    # ── Phase 36c Stage 4 — optional per-participant screen share ──
    screen_result: dict = {}
    if screen_upload is not None:
        screen_result = await _ingest_participant_screen(
            db, session_id=session_id, sess_dir=sess_dir,
            file_base=file_base, part_id=part["id"],
            screen_upload=screen_upload, user_id=user_id)

    return {"upload_status": "completed", "audio_track_url": audio_url,
              "size_bytes": mp3_path.stat().st_size,
              "server_duration_seconds": server_duration,
              "participant_id": part["id"],
              **({"video_track_url":               video_result["video_url"],
                  "video_size_bytes":               video_result["size_bytes"],
                  "video_duration_seconds": video_result["server_duration_seconds"]}
                  if video_result.get("video_url") else {}),
              **({"screen_track_url":              screen_result["screen_url"],
                  "screen_size_bytes":              screen_result["size_bytes"]}
                  if screen_result.get("screen_url") else {})}


async def _ingest_participant_screen(db, *, session_id: str, sess_dir: Path,
                                                                      file_base: str, part_id: str,
                                                                      screen_upload: "UploadFile",
                                                                      user_id: Optional[str]) -> dict:
    """Phase 36c Stage 4 — stream a webm screen capture → transcode to 1080p
    H.264 mp4 (no audio; mic is captured on the video/audio tracks). Same
    cap rules as video; persists screen_track_url + screen_upload_status."""
    from fastapi import HTTPException
    from services import podcast_video as pv
    src_name = screen_upload.filename or "screen.webm"
    src_ext    = Path(src_name).suffix.lower() or ".webm"
    if src_ext not in (".webm", ".mp4", ".mov"): src_ext = ".webm"
    src = sess_dir / f"{file_base}_screen_raw{src_ext}"
    total = 0
    try:
        with open(src, "wb") as f:
            while True:
                chunk = await screen_upload.read(CHUNK_BYTES)
                if not chunk: break
                total += len(chunk)
                if total > pv.VIDEO_UPLOAD_CAP_BYTES:
                    f.close(); src.unlink(missing_ok=True)
                    await db.podcast_recording_participants.update_one(
                        {"id": part_id},
                        {"$set": {"screen_upload_status": "rejected_disk"}})
                    raise HTTPException(413, {"code": "upload_too_large",
                        "scope": "screen",
                        "message": f"Stage 4 screen cap is "
                                          f"{pv.VIDEO_UPLOAD_CAP_BYTES//(1024*1024)} MB."})
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        src.unlink(missing_ok=True)
        raise HTTPException(500, {"code": "screen_upload_stream_failed",
                                                      "message": str(e)[:200]})
    mp4 = sess_dir / f"{file_base}_screen.mp4"
    # CRF 26 + veryfast preset; screen content compresses well at that quality.
    cmd = ["ffmpeg", "-y", "-i", str(src),
              "-c:v", "libx264", "-crf", "26", "-preset", "veryfast",
              "-vf", f"scale=-2:{pv.TARGET_H}",
              "-an", "-movflags", "+faststart", str(mp4)]
    try:
        rc = subprocess.run(cmd, capture_output=True, timeout=600).returncode
    except Exception as e:
        rc = -1; logger.warning("[36c-s4] screen ffmpeg crash: %s", e)
    src.unlink(missing_ok=True)
    if rc != 0 or not mp4.exists() or mp4.stat().st_size == 0:
        mp4.unlink(missing_ok=True)
        await db.podcast_recording_participants.update_one(
            {"id": part_id},
            {"$set": {"screen_upload_status": "failed",
                          "error_message": f"screen_ffmpeg_rc={rc}"}})
        await _record_disk_event(db, code="screen_transcode_failed",
                                                          route="upload_track:screen",
                                                          session_id=session_id, user_id=user_id)
        raise HTTPException(500, {"code": "screen_transcode_failed",
            "message": "FFmpeg could not transcode the uploaded screen capture."})
    screen_url = (f"/api/podcasts/recording-sessions/{session_id}"
                              f"/screen/{file_base}.mp4")
    await db.podcast_recording_participants.update_one(
        {"id": part_id},
        {"$set": {"screen_track_url":           screen_url,
                      "screen_track_format":      "mp4/h264",
                      "screen_upload_status":  "completed"}})
    return {"screen_url": screen_url, "size_bytes": mp4.stat().st_size}


async def _ingest_participant_video(db, *, session_id: str, sess_dir: Path,
                                                                    file_base: str, part_id: str,
                                                                    video_upload: "UploadFile",
                                                                    user_id: Optional[str]) -> dict:
    """Stage 3 (full-scope) — streaming video upload → transcode to 1080p
    H.264+AAC mp4. 500 MB per-participant cap, 60-min ffprobe duration
    gate. On any failure: cleanup, flip video_upload_status=failed, audit,
    raise. Local file is uploaded to Tigris + deleted by the
    post-finalize offloader (36c.5 path) — NOT here."""
    from fastapi import HTTPException
    from services import podcast_video as pv
    src_name = video_upload.filename or "video.webm"
    src_ext    = Path(src_name).suffix.lower() or ".webm"
    if src_ext not in (".webm", ".mp4", ".m4a", ".mov"): src_ext = ".webm"
    src_video = sess_dir / f"{file_base}_video_raw{src_ext}"
    total = 0
    try:
        with open(src_video, "wb") as f:
            while True:
                chunk = await video_upload.read(CHUNK_BYTES)
                if not chunk: break
                total += len(chunk)
                if total > pv.VIDEO_UPLOAD_CAP_BYTES:
                    f.close()
                    src_video.unlink(missing_ok=True)
                    await db.podcast_recording_participants.update_one(
                        {"id": part_id},
                        {"$set": {"video_upload_status": "rejected_disk"}})
                    raise HTTPException(413, {"code": "upload_too_large",
                        "scope": "video",
                        "message": f"Stage 3 video cap is "
                                          f"{pv.VIDEO_UPLOAD_CAP_BYTES//(1024*1024)} MB."})
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        src_video.unlink(missing_ok=True)
        raise HTTPException(500, {"code": "video_upload_stream_failed",
                                                      "message": str(e)[:200]})

    mp4_path = sess_dir / f"{file_base}_video.mp4"
    rc = await asyncio.get_event_loop().run_in_executor(
        None, pv.transcode_to_mp4, src_video, mp4_path, None, pv.TARGET_H)
    src_video.unlink(missing_ok=True)
    if rc != 0 or not mp4_path.exists() or mp4_path.stat().st_size == 0:
        mp4_path.unlink(missing_ok=True)
        await db.podcast_recording_participants.update_one(
            {"id": part_id},
            {"$set": {"video_upload_status": "failed",
                          "error_message": f"video_ffmpeg_rc={rc}"}})
        await _record_disk_event(db, code="video_transcode_failed",
                                                          route="upload_track:video",
                                                          session_id=session_id, user_id=user_id)
        raise HTTPException(500, {"code": "video_transcode_failed",
            "message": "FFmpeg could not transcode the uploaded video."})

    # Authoritative duration gate — 60 min cap for video (Stage 3 envelope).
    from services.podcasts import ffprobe_duration
    vdur = ffprobe_duration(mp4_path) or 0.0
    if vdur > pv.VIDEO_RECORDING_CAP_SEC:
        mp4_path.unlink(missing_ok=True)
        await db.podcast_recording_participants.update_one(
            {"id": part_id},
            {"$set": {"video_upload_status": "rejected_duration"}})
        await _record_disk_event(db, code="video_duration_exceeded",
                                                          route="upload_track:video",
                                                          session_id=session_id, user_id=user_id)
        raise HTTPException(400, {"code": "video_duration_exceeded",
            "cap_seconds": pv.VIDEO_RECORDING_CAP_SEC,
            "server_duration_seconds": vdur})

    video_url = (f"/api/podcasts/recording-sessions/{session_id}"
                          f"/video/{file_base}.mp4")
    await db.podcast_recording_participants.update_one(
        {"id": part_id},
        {"$set": {"video_track_url":            video_url,
                      "video_track_format":      "mp4/h264",
                      "video_upload_status":  "completed"}})
    return {"video_url": video_url, "size_bytes": mp4_path.stat().st_size,
              "server_duration_seconds": vdur}


def _ffmpeg_to_mp3(src: Path, dst: Path) -> int:
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src),
              "-codec:a", "libmp3lame", "-b:a", "128k", "-ac", "2",
              "-ar", "44100", str(dst)],
            check=False, capture_output=True, timeout=180)
        return r.returncode
    except Exception as e:
        logger.warning("[36c] ffmpeg crash: %s", e)
        return -1


async def _post_finalize_offload_to_tigris(db, *, session_id: str,
                                                                              sess_dir: Path, mixed: Path,
                                                                              audio_mp3: Path, tracks: list,
                                                                              channel_id: Optional[str],
                                                                              ep_id: str) -> dict:
    """Phase 36c.5 — Upload mixed.mp3 + audio.mp3 + per-track mp3s to
    Tigris (when STORAGE_BACKEND=tigris), HEAD-verify size, then delete
    the local copies. Empties + removes the session dir on success. On
    any upload/verify miss, KEEPS the local file and logs a
    hygiene_runs row with code=tigris_upload_size_mismatch."""
    from services import object_storage as obs
    st = obs.get_storage()
    if st.backend_name != "tigris":
        return {"skipped": True, "reason": "STORAGE_BACKEND!=tigris"}
    plan: list[tuple[Path, str, str]] = []    # (local, key, content_type)
    # Mixed audio: canonical recording-session key.
    if mixed.is_file() and mixed.stat().st_size > 0:
        plan.append((mixed, obs.key_recording_mixed_audio(session_id), "audio/mpeg"))
    # audio.mp3 is the same payload but lives under a different name —
    # we don't double-store; just delete after mixed is verified up. We
    # add it to a "delete-after-verify" list below.
    # Per-participant tracks.
    for t in tracks:
        mp3p = Path(t.get("mp3_path") or "")
        if mp3p.is_file():
            pid = t["participant_id"]; role = t.get("role") or "guest"
            # Host gets the historical host/audio.mp3 key; guests get
            # the canonical per-participant key.
            if role == "host":
                key = f"podcasts/recordings/{session_id}/host/audio.mp3"
            else:
                key = obs.key_recording_participant_audio(session_id, pid)
            plan.append((mp3p, key, "audio/mpeg"))
        # Phase 36c Stage 3 — per-participant video tracks.
        mp4p = Path(t.get("mp4_path") or "") if t.get("mp4_path") else None
        if mp4p and mp4p.is_file():
            pid = t["participant_id"]; role = t.get("role") or "guest"
            if role == "host":
                vkey = f"podcasts/recordings/{session_id}/host/video.mp4"
            else:
                vkey = obs.key_recording_participant_video(session_id, pid)
            plan.append((mp4p, vkey, "video/mp4"))
        # Phase 36c Stage 4 — per-participant screen-share tracks.
        scrp = Path(t.get("screen_path") or "") if t.get("screen_path") else None
        if scrp and scrp.is_file():
            pid = t["participant_id"]; role = t.get("role") or "guest"
            if role == "host":
                skey = f"podcasts/recordings/{session_id}/host/screen.mp4"
            else:
                skey = obs.key_recording_participant_screen(session_id, pid)
            plan.append((scrp, skey, "video/mp4"))
    # Phase 36c Stage 3 — mixed video grid (when produced by finalize).
    mixed_video = sess_dir / "video.mp4"
    if mixed_video.is_file() and mixed_video.stat().st_size > 0:
        plan.append((mixed_video, obs.key_recording_mixed_video(session_id),
                              "video/mp4"))

    uploaded: list[dict] = []
    failed: list[dict] = []
    for local_path, key, ctype in plan:
        try:
            sz_local = local_path.stat().st_size
            st.upload(local_path=str(local_path), key=key,
                          content_type=ctype)
            head = st.head(key=key)
            if not head or int(head.get("size") or 0) != sz_local:
                failed.append({"key": key, "local": str(local_path),
                                    "local_size": sz_local,
                                    "remote_size": (head or {}).get("size"),
                                    "code": "tigris_upload_size_mismatch"})
                logger.warning("[36c.5] HEAD-verify failed: %s "
                                          "local=%d remote=%s — KEEPING local",
                                          key, sz_local, head)
                continue
            uploaded.append({"key": key, "size": sz_local,
                                  "local": str(local_path)})
        except Exception as e:
            failed.append({"key": key, "local": str(local_path),
                                "code": f"tigris_upload_error:{type(e).__name__}",
                                "message": str(e)[:200]})
            logger.warning("[36c.5] Tigris upload failed for %s: %s", key, e)

    # Delete every verified-uploaded local file PLUS the duplicate
    # audio.mp3 if its mixed sibling verified up. Keep failed ones.
    deleted = 0; freed = 0
    for u in uploaded:
        p = Path(u["local"])
        try:
            if p.is_file():
                freed += p.stat().st_size
                p.unlink()
                deleted += 1
        except OSError as e:
            logger.warning("[36c.5] local unlink failed %s: %s", p, e)
    # audio.mp3 is a dup of mixed.mp3. Drop it iff mixed was uploaded ok.
    mixed_ok = any(u["key"].endswith("/mixed.mp3") for u in uploaded)
    if mixed_ok and audio_mp3.is_file():
        try:
            freed += audio_mp3.stat().st_size
            audio_mp3.unlink(); deleted += 1
        except OSError as e:
            logger.warning("[36c.5] audio.mp3 unlink failed: %s", e)

    # Try to remove the empty session dir.
    try:
        if sess_dir.is_dir():
            os.rmdir(sess_dir)
    except OSError:
        pass    # not empty (failures or guest sub-dirs) — leave it

    # Persist storage_key on the episode for future fast lookups + a
    # hygiene_runs row for the test/audit trail.
    try:
        if mixed_ok:
            await db.podcast_episodes.update_one(
                {"id": ep_id},
                {"$set": {"storage_key_audio":
                                      obs.key_recording_mixed_audio(session_id)}})
    except Exception as e:
        logger.warning("[36c.5] episode storage_key persist failed: %s", e)
    try:
        await db.hygiene_runs.insert_one({
            "run_at": _now(), "kind": "post_finalize_offload",
            "session_id": session_id, "episode_id": ep_id,
            "deleted_count": deleted, "freed_bytes": freed,
            "uploaded": [{"key": u["key"], "size": u["size"]} for u in uploaded],
            "errors": failed[:25]})
    except Exception: pass
    return {"skipped": False, "uploaded": len(uploaded),
              "failed": len(failed), "deleted_local": deleted,
              "freed_bytes": freed, "errors": failed}


async def finalize_session(db, *, session_id: str) -> dict:
    """Stage 1 (solo) → copy host.mp3 → mixed.mp3.
    Stage 2 (multi-track) → FFmpeg amix + loudnorm of all completed tracks.
    Both paths create a podcast_episodes draft + fire 36b auto-transcription.
    Phase 36c.5: after the mix is built, the per-participant + mixed +
    audio files are uploaded to Tigris (when configured), HEAD-verified,
    and the local copies are deleted. The session dir is removed once
    empty. Local files are kept on upload/verify failure."""
    from fastapi import HTTPException
    s = await db.podcast_recording_sessions.find_one({"id": session_id})
    if not s: raise HTTPException(404, "session_not_found")
    if s.get("status") not in ("processing", "recording"):
        raise HTTPException(400, {"code": "invalid_state",
            "message": f"Cannot finalize a session in '{s.get('status')}' state."})

    # Collect every completed participant track (host + admitted guests).
    from services import podcast_guests as pg
    tracks = await pg.collect_participant_tracks(db, session_id=session_id)
    if not tracks:
        raise HTTPException(400, {"code": "no_completed_track",
            "message": "No completed audio tracks to finalize."})

    sess_dir = STORAGE_ROOT / session_id
    mixed = sess_dir / "mixed.mp3"
    audio_mp3 = sess_dir / "audio.mp3"
    rc = await asyncio.get_event_loop().run_in_executor(
        None, pg.ffmpeg_amix_tracks,
        [t["mp3_path"] for t in tracks], mixed)
    if rc != 0 or not mixed.exists() or mixed.stat().st_size == 0:
        raise HTTPException(500, {"code": "mix_failed",
            "message": f"FFmpeg amix returned rc={rc}."})
    import shutil as _sh
    _sh.copyfile(mixed, audio_mp3)

    # ── Phase 36c Stage 3 — Video grid mix (when session.video_enabled) ──
    mixed_video_url: Optional[str] = None
    video_layout: Optional[str] = None
    video_dims: dict = {}
    video_tracks = [t for t in tracks if t.get("mp4_path")
                              and Path(t["mp4_path"]).is_file()]
    if s.get("video_enabled") and video_tracks:
        from services import podcast_video as pv
        # Stage 4 — when ANY participant has a screen share, force
        # screen_priority layout (overrides session.grid_layout) and pass
        # the first available screen as the featured tile.
        screen_tracks = [t for t in tracks if t.get("screen_path")
                                      and Path(t["screen_path"]).is_file()]
        has_screen = bool(screen_tracks)
        layout = pv.resolve_layout(s.get("grid_layout") or "auto",
                                                          len(video_tracks),
                                                          has_screen=has_screen)
        screen_for_grid = (Path(screen_tracks[0]["screen_path"])
                                            if has_screen else None)
        grid_video = sess_dir / "video_grid.mp4"
        final_video = sess_dir / "video.mp4"
        rc_g = await asyncio.get_event_loop().run_in_executor(
            None, pv.ffmpeg_grid_mix,
            [Path(t["mp4_path"]) for t in video_tracks],
            grid_video, layout, screen_for_grid)
        if rc_g == 0 and grid_video.is_file() and grid_video.stat().st_size > 0:
            rc_m = await asyncio.get_event_loop().run_in_executor(
                None, pv.merge_video_audio,
                grid_video, mixed, final_video)
            if rc_m == 0 and final_video.is_file() and final_video.stat().st_size > 0:
                video_layout = layout
                video_dims = pv.ffprobe_video_dimensions(final_video)
                mixed_video_url = (f"/api/podcasts/recording-sessions/"
                                                  f"{session_id}/video/mixed.mp4")
            else:
                logger.error("[36c-s4] merge_video_audio failed rc=%s — "
                                          "marking mix_failed", rc_m)
                video_layout = "mix_failed"
            grid_video.unlink(missing_ok=True)
        else:
            # ffmpeg grid mix failed on valid input → DO NOT silently ship
            # audio-only. Mark the session/episode so a re-finalize can be
            # triggered by the creator.
            logger.error("[36c-s4] ffmpeg_grid_mix failed rc=%s on valid "
                                      "inputs (video=%d screen=%s) — marking mix_failed",
                                      rc_g, len(video_tracks), bool(screen_for_grid))
            video_layout = "mix_failed"

    # Build diarization speaker map (A/B/C/D → participant_ids in join order).
    speaker_map = pg.build_diarization_speaker_map(tracks)

    # Create a draft podcast_episodes row + recording row.
    from services.podcasts import ffprobe_duration
    duration = ffprobe_duration(mixed) or float(s.get("total_duration_seconds") or 0)
    epid = _gen("pep")
    # Phase 36c Stage 4 — file_size_bytes_video for RSS length attr.
    mixed_video_size = 0
    if mixed_video_url:
        _mv = sess_dir / "video.mp4"
        if _mv.is_file(): mixed_video_size = _mv.stat().st_size
    await db.podcast_episodes.insert_one({
        "id":                            epid,
        "channel_id":             s["channel_id"],
        "guid":                         f"bigfm-ep-{epid}",
        "title":                        s["title"],
        "description":           f"Recorded in BigFM Studio on "
                                              f"{_now().strftime('%b %d, %Y')}.",
        "show_notes":             "",
        "duration_seconds": duration,
        "file_size_bytes":   mixed.stat().st_size,
        "file_size_bytes_video": mixed_video_size,
        "season":                     1, "episode_number": 1, "episode_type": "full",
        "publish_status":      "draft",
        "audio_url":               f"/api/podcasts/episodes/{epid}/audio.mp3",
        "video_url":               (f"/api/podcasts/episodes/{epid}/video.mp4"
                                              if mixed_video_url else None),
        "video_layout":         video_layout,
        "video_dimensions": video_dims or None,
        # Phase 36c Stage 4 — `video_dims` is a deprecation alias for
        # `video_dimensions`. Both ship for one release cycle so the
        # original Stage 3 dispatch brief shape stays valid for any
        # already-shipped consumers.
        "video_dims":             video_dims or None,
        "storage_path":         str(sess_dir),
        "recording_session_id": session_id,
        "diarization_speaker_map": speaker_map,
        "created_at":             _now(), "updated_at": _now(),
    })
    await db.podcast_recordings.insert_one({
        "id":                                 _gen("prec"),
        "session_id":                  session_id,
        "creator_id":                  s["creator_id"],
        "mixed_audio_url":           f"/api/podcasts/recording-sessions/{session_id}/audio/mixed.mp3",
        "mixed_video_url":           mixed_video_url,
        "raw_assets_json":           {"tracks": [{"participant_id": t["participant_id"],
                                                                    "role": t["role"],
                                                                    "mp3": str(t["mp3_path"]),
                                                                    "mp4": (str(t["mp4_path"])
                                                                                  if t.get("mp4_path") else None)}
                                                                  for t in tracks]},
        "duration_seconds":      duration,
        "processing_status":     "completed",
        "created_at":                  _now(),
    })
    await db.podcast_recording_sessions.update_one(
        {"id": session_id},
        {"$set": {"status": "completed" if video_layout != "mix_failed"
                                          else "completed_mix_failed",
                      "episode_id": epid,
                      "mixed_audio_url": f"/api/podcasts/recording-sessions/{session_id}/audio/mixed.mp3",
                      "mixed_video_url": mixed_video_url,
                      "video_layout":     video_layout,
                      "grid_layout_resolved": video_layout,
                      "diarization_speaker_map": speaker_map,
                      "updated_at": _now()}})
    # Phase 36c.5 — Upload mixed + per-track files to Tigris (when configured),
    # HEAD-verify size, then delete local copies. On any verification failure
    # the local file is kept and a hygiene event is logged.
    upload_report = await _post_finalize_offload_to_tigris(
        db, session_id=session_id, sess_dir=sess_dir, mixed=mixed,
        audio_mp3=audio_mp3, tracks=tracks, channel_id=s.get("channel_id"),
        ep_id=epid)
    # Auto-fire 36b transcription on the new draft episode. Best-effort.
    try:
        from services import podcast_transcription as tx
        await tx.kick_transcription(db, episode_id=epid)
    except Exception as e:
        logger.warning("[36c] auto-transcribe on finalize failed: %s", e)
    # Phase 36d — Magic Clips background job (asyncio.create_task, mirrors
    # the Stage 3 video pipeline). Honors per-channel `magic_clips_enabled`.
    try:
        from services import podcast_magic_clips as mc
        ch = await db.podcast_channels.find_one({"id": s.get("channel_id")})
        if mc.is_enabled_for_channel(ch):
            await db.podcast_episodes.update_one(
                {"id": epid}, {"$set": {"magic_clips_status": "pending"}})
            mc.schedule_magic_clips(db, episode_id=epid)
    except Exception as e:
        logger.warning("[36d] magic-clips schedule failed: %s", e)
    # Funnel + lobby broadcast.
    try:
        await pg.log_funnel(db, event="session_finalized",
                                                session_id=session_id,
                                                channel_id=s.get("channel_id"),
                                                meta={"episode_id": epid,
                                                          "track_count": len(tracks)})
        await pg.lobby_hub.broadcast_all(session_id,
            {"type": "session_ended", "episode_id": epid})
    except Exception: pass

    return {"session_id": session_id, "episode_id": epid,
              "mixed_audio_url": f"/api/podcasts/recording-sessions/{session_id}/audio/mixed.mp3",
              "duration_seconds": duration,
              "track_count": len(tracks),
              "diarization_speaker_map": speaker_map}


async def cancel_session(db, *, session_id: str) -> dict:
    s = await db.podcast_recording_sessions.find_one({"id": session_id})
    if not s:
        from fastapi import HTTPException
        raise HTTPException(404, "session_not_found")
    # Cleanup storage.
    sess_dir = STORAGE_ROOT / session_id
    if sess_dir.exists():
        import shutil as _sh
        _sh.rmtree(sess_dir, ignore_errors=True)
    # Cleanup LiveKit room (best-effort).
    try:
        from services import livekit_client as lk
        if s.get("livekit_room_name"):
            lk.delete_room(s["livekit_room_name"])
    except Exception as e:
        logger.warning("[36c] livekit delete_room failed (non-fatal): %s", e)
    await db.podcast_recording_sessions.update_one(
        {"id": session_id},
        {"$set": {"status": "cancelled", "updated_at": _now()}})
    return {"session_id": session_id, "status": "cancelled"}


async def get_session(db, *, session_id: str) -> Optional[dict]:
    s = await db.podcast_recording_sessions.find_one(
        {"id": session_id}, {"_id": 0})
    if not s: return None
    parts = await db.podcast_recording_participants.find(
        {"session_id": session_id}, {"_id": 0}).to_list(10)
    s["participants"] = parts
    return s


async def list_disk_events(db, *, limit: int = 50) -> list:
    return await db.recording_disk_events.find(
        {}, {"_id": 0}).sort("timestamp", -1).limit(int(limit)).to_list(int(limit))
