"""Phase 36c Stage 2 — Guest invites, lobby, WS hub, multi-track mix.

Collections:
  podcast_guest_invites {
    id, session_id, guest_name, guest_email, guest_phone?, invite_token (uuid4),
    invite_status: pending|accepted|expired|cancelled|kicked,
    consent_required, sent_at, accepted_at?, expires_at (sent_at + 7d),
    revoked_at?, revoked_by?, accepted_participant_id?, mocked_email_sent
  }
  podcast_release_forms {
    id, session_id, participant_id, consent_text (FULL snapshot),
    consent_version, signed_at, ip_hash, status: signed|revoked
  }
  creator_studio_funnel {
    id, user_id?, event, timestamp, session_id?, channel_id?, meta?
  }

Participant row (extends Stage 1):
  + lobby_status: lobby | admitted | kicked | left
  + admitted_at, kicked_at, ws_token (uuid4 — guest WS auth)
  + display_name (guest-supplied; for host use creator display_name)
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, WebSocket

logger = logging.getLogger("bigfm.podcast_guests")

INVITE_TTL_DAYS              = 7
MAX_PARTICIPANTS_STAGE2 = 4    # 1 host + up to 3 guests
STORAGE_ROOT = Path("/app/backend/storage/podcasts/recordings")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _ip_hash(ip: Optional[str]) -> str:
    return hashlib.sha256((ip or "0.0.0.0").encode("utf-8")).hexdigest()[:32]


# ──────────────────────────────────────────────────────────────────
#  Creator-Studio Funnel  (append-only analytics)
# ──────────────────────────────────────────────────────────────────
FUNNEL_EVENTS = {
    "picker_shown", "picker_apply_cta_clicked",
    "picker_create_channel_cta_clicked",
    "session_started", "guest_invited", "guest_accepted",
    "guest_admitted", "guest_kicked",
    "session_finalized", "session_cancelled",
}


async def log_funnel(db, *, event: str, user_id: Optional[str] = None,
                                      session_id: Optional[str] = None,
                                      channel_id: Optional[str] = None,
                                      meta: Optional[dict] = None) -> None:
    if event not in FUNNEL_EVENTS:
        return
    try:
        await db.creator_studio_funnel.insert_one({
            "id":                  _gen("csf"),
            "user_id":         user_id,
            "event":             event,
            "session_id":   session_id,
            "channel_id":   channel_id,
            "meta":               meta or {},
            "timestamp": _now(),
        })
    except Exception as e:
        logger.warning("[36c-s2] funnel write failed (non-fatal): %s", e)


# ──────────────────────────────────────────────────────────────────
#  Invites
# ──────────────────────────────────────────────────────────────────
async def create_invite(db, *, session_id: str, guest_name: str,
                                          guest_email: str, guest_phone: Optional[str],
                                          consent_required: bool,
                                          invited_by_user_id: str) -> dict:
    sess = await db.podcast_recording_sessions.find_one({"id": session_id})
    if not sess: raise HTTPException(404, "session_not_found")
    if sess.get("status") not in ("pending", "recording"):
        raise HTTPException(400, {"code": "invalid_session_state",
            "message": f"Cannot invite guests when session is '{sess.get('status')}'."})
    now = _now()
    expires = now + timedelta(days=INVITE_TTL_DAYS)
    token = uuid.uuid4().hex
    doc = {
        "id":                              _gen("pgi"),
        "session_id":               session_id,
        "guest_name":              (guest_name or "").strip()[:80],
        "guest_email":             (guest_email or "").strip()[:120],
        "guest_phone":             (guest_phone or "").strip()[:32] or None,
        "invite_token":            token,
        "invite_status":          "pending",
        "consent_required":   bool(consent_required),
        "sent_at":                      now,
        "accepted_at":             None,
        "expires_at":                expires,
        "revoked_at":                None,
        "revoked_by":                None,
        "accepted_participant_id": None,
        "mocked_email_sent":  True,  # SendGrid MOCKED
        "invited_by_user_id": invited_by_user_id,
    }
    await db.podcast_guest_invites.insert_one(doc)
    logger.info("[36c-s2 MOCK] SendGrid invite email NOT sent: token=%s to=%s",
                          token, doc["guest_email"])
    await log_funnel(db, event="guest_invited", user_id=invited_by_user_id,
                                      session_id=session_id,
                                      channel_id=sess.get("channel_id"))
    return doc


async def list_invites(db, *, session_id: str) -> list:
    rows = await db.podcast_guest_invites.find(
        {"session_id": session_id}, {"_id": 0}).sort("sent_at", -1).to_list(50)
    return rows


async def cancel_invite(db, *, session_id: str, invite_id: str,
                                          revoked_by_user_id: str) -> dict:
    inv = await db.podcast_guest_invites.find_one(
        {"id": invite_id, "session_id": session_id})
    if not inv: raise HTTPException(404, "invite_not_found")
    await db.podcast_guest_invites.update_one(
        {"id": invite_id},
        {"$set": {"invite_status": "cancelled",
                      "revoked_at":      _now(),
                      "revoked_by":      revoked_by_user_id}})
    # If accepted, kick from LiveKit + flip participant lobby_status.
    pid = inv.get("accepted_participant_id")
    if pid:
        await db.podcast_recording_participants.update_one(
            {"id": pid},
            {"$set": {"lobby_status": "kicked",
                          "kicked_at":      _now()}})
        sess = await db.podcast_recording_sessions.find_one(
            {"id": session_id}, {"livekit_room_name": 1, "force_mock": 1})
        from services import livekit_client as lk
        lk.remove_participant(room_name=sess.get("livekit_room_name") or "",
                                                identity=pid)
        # Broadcast to that guest's WS.
        await lobby_hub.broadcast_to_participant(
            session_id, pid, {"type": "you_have_been_kicked"})
    inv = await db.podcast_guest_invites.find_one({"id": invite_id}, {"_id": 0})
    return inv


def _public_invite_envelope(invite: dict, sess: dict, channel: dict,
                                                    creator: dict) -> dict:
    from services import podcast_consent as pc
    cv = pc.render(creator_display_name=creator.get("display_name") or "",
                              channel_title=channel.get("title") or "")
    return {
        "invite_status":               invite.get("invite_status"),
        "channel_title":               channel.get("title"),
        "recording_title":          sess.get("title"),
        "host_display_name":      creator.get("display_name"),
        "consent_required":        bool(invite.get("consent_required")),
        "consent_version":          cv["consent_version"],
        "consent_text":                cv["consent_text"],
        "expires_at":                      invite.get("expires_at"),
        "guest_email_prefilled": invite.get("guest_email") or "",
        "guest_name_prefilled":  invite.get("guest_name") or "",
        "can_join":                          invite.get("invite_status") in ("pending", "accepted"),
    }


async def get_public_invite(db, *, invite_token: str) -> dict:
    inv = await db.podcast_guest_invites.find_one(
        {"invite_token": invite_token})
    if not inv: raise HTTPException(404, "invite_not_found")
    exp = inv.get("expires_at")
    if exp and exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
    if inv.get("invite_status") == "cancelled":
        raise HTTPException(423, {"code": "invite_cancelled",
            "message": "This invite was cancelled by the host."})
    if exp and exp < _now() and inv.get("invite_status") == "pending":
        await db.podcast_guest_invites.update_one(
            {"id": inv["id"]}, {"$set": {"invite_status": "expired"}})
        raise HTTPException(410, {"code": "invite_expired",
            "message": "This invite has expired. Ask the host for a new one."})
    if inv.get("invite_status") == "expired":
        raise HTTPException(410, {"code": "invite_expired",
            "message": "This invite has expired. Ask the host for a new one."})
    sess = await db.podcast_recording_sessions.find_one(
        {"id": inv["session_id"]})
    if not sess: raise HTTPException(404, "session_not_found")
    channel = await db.podcast_channels.find_one(
        {"id": sess.get("channel_id")}) or {}
    creator = await db.podcast_creators.find_one(
        {"id": sess.get("creator_id")}) or {}
    return _public_invite_envelope(inv, sess, channel, creator)


async def accept_invite(db, *, invite_token: str, display_name: str,
                                          email: str, consent_accepted: bool,
                                          device_info: dict,
                                          ip_address: Optional[str]) -> dict:
    inv = await db.podcast_guest_invites.find_one(
        {"invite_token": invite_token})
    if not inv: raise HTTPException(404, "invite_not_found")
    if inv.get("invite_status") == "cancelled":
        raise HTTPException(423, {"code": "invite_cancelled",
            "message": "This invite has been cancelled."})
    exp = inv.get("expires_at")
    if exp and exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < _now():
        raise HTTPException(410, {"code": "invite_expired"})
    if inv.get("consent_required") and not consent_accepted:
        raise HTTPException(400, {"code": "consent_required"})
    dn = (display_name or "").strip()
    if len(dn) < 2 or len(dn) > 40:
        raise HTTPException(400, {"code": "display_name_invalid",
            "message": "Display name must be 2-40 characters."})
    sid = inv["session_id"]
    # Stage 2 hard cap: 4 total participants.
    active_count = await db.podcast_recording_participants.count_documents(
        {"session_id": sid,
          "lobby_status": {"$in": ["lobby", "admitted"]}})
    # The host participant is created at session-create time and may not have
    # a lobby_status field yet (Stage 1); count it as an active participant.
    host_count = await db.podcast_recording_participants.count_documents(
        {"session_id": sid, "role": "host",
          "lobby_status": {"$exists": False}})
    if active_count + host_count >= MAX_PARTICIPANTS_STAGE2:
        raise HTTPException(409, {"code": "session_full",
            "max_participants": MAX_PARTICIPANTS_STAGE2,
            "message": f"This recording already has {MAX_PARTICIPANTS_STAGE2} "
                              f"participants. Ask the host to remove someone."})
    # Idempotency: if this invite is already accepted, return the prior
    # participant_id + token (lets a guest resume after a tab close).
    if inv.get("invite_status") == "accepted" and inv.get("accepted_participant_id"):
        p = await db.podcast_recording_participants.find_one(
            {"id": inv["accepted_participant_id"]}, {"_id": 0})
        if p:
            sess = await db.podcast_recording_sessions.find_one({"id": sid})
            return _accept_envelope(p, sess)

    pid = _gen("prp")
    ws_token = uuid.uuid4().hex
    sess = await db.podcast_recording_sessions.find_one({"id": sid})
    if not sess: raise HTTPException(404, "session_not_found")
    from services import livekit_client as lk
    force_mock = bool(sess.get("force_mock"))
    room = sess.get("livekit_room_name") or f"bigfm-{sid}"
    lk_token = lk.mint_room_token(
        room_name=room, identity=pid, role="guest",
        permissions={"can_publish": False, "can_subscribe": True,
                                "can_publish_data": True})
    # If force_mock was set on the session, override the mint to mock shape.
    if force_mock and not lk_token.startswith("mock_lk_"):
        lk_token = lk.mint_room_token(
            room_name=room, identity=pid, role="guest",
            permissions={"can_publish": False, "can_subscribe": True,
                                  "can_publish_data": True})

    p = {
        "id":                            pid,
        "session_id":             sid,
        "user_id":                    None,    # public guest, no user account
        "role":                         "guest",
        "guest_name":             None,
        "guest_email":           email or inv.get("guest_email") or "",
        "display_name":         dn,
        "joined_at":               _now(),
        "left_at":                    None,
        "admitted_at":          None,
        "kicked_at":               None,
        "audio_track_url":   None,
        "video_track_url":   None,
        "upload_status":      "pending",
        "consent_accepted": bool(consent_accepted),
        "consent_accepted_at": _now() if consent_accepted else None,
        "device_info_json": device_info or {},
        "error_message":      None,
        "lobby_status":        "lobby",
        "ws_token":                ws_token,
        "created_at":             _now(),
    }
    await db.podcast_recording_participants.insert_one(p)
    # Release form — snapshot the FULL consent text at signing.
    from services import podcast_consent as pc
    channel = await db.podcast_channels.find_one(
        {"id": sess.get("channel_id")}) or {}
    creator = await db.podcast_creators.find_one(
        {"id": sess.get("creator_id")}) or {}
    cv = pc.render(creator_display_name=creator.get("display_name") or "",
                              channel_title=channel.get("title") or "")
    if consent_accepted:
        await db.podcast_release_forms.insert_one({
            "id":                          _gen("prf"),
            "session_id":           sid,
            "participant_id":  pid,
            "consent_text":        cv["consent_text"],
            "consent_version": cv["consent_version"],
            "signed_at":              _now(),
            "ip_hash":                  _ip_hash(ip_address),
            "status":                    "signed",
        })
    await db.podcast_guest_invites.update_one(
        {"id": inv["id"]},
        {"$set": {"invite_status": "accepted",
                      "accepted_at": _now(),
                      "accepted_participant_id": pid}})
    await log_funnel(db, event="guest_accepted",
                                      session_id=sid,
                                      channel_id=sess.get("channel_id"),
                                      meta={"participant_id": pid})
    # Broadcast to the host's WS.
    await lobby_hub.broadcast_to_role(sid, "host", {
        "type":             "participant_joined_lobby",
        "participant": {"id": pid, "display_name": dn,
                              "joined_at": p["joined_at"].isoformat()},
    })
    return _accept_envelope(p, sess)


def _accept_envelope(p: dict, sess: dict) -> dict:
    from services import livekit_client as lk
    room = sess.get("livekit_room_name") or ""
    return {
        "participant_id":      p["id"],
        "ws_token":                p.get("ws_token"),
        "lobby_status":        p.get("lobby_status"),
        "livekit_room_name": room,
        "livekit_token":         lk.mint_room_token(
            room_name=room, identity=p["id"], role="guest",
            permissions={"can_publish": p.get("lobby_status") == "admitted",
                                    "can_subscribe": True}),
        "livekit_url":             sess.get("livekit_url") or lk.livekit_url(),
        "mode":                         "live" if lk.is_live() else "mock",
        "display_name":         p.get("display_name"),
    }


async def get_invite_state(db, *, invite_token: str) -> dict:
    inv = await db.podcast_guest_invites.find_one({"invite_token": invite_token})
    if not inv: raise HTTPException(404, "invite_not_found")
    pid = inv.get("accepted_participant_id")
    if not pid:
        return {"lobby_status": "not_accepted",
                  "invite_status": inv.get("invite_status")}
    p = await db.podcast_recording_participants.find_one({"id": pid})
    if not p: return {"lobby_status": "unknown"}
    sess = await db.podcast_recording_sessions.find_one({"id": inv["session_id"]})
    return {"lobby_status":      p.get("lobby_status"),
              "session_status": sess.get("status") if sess else "unknown",
              "invite_status":  inv.get("invite_status")}


# ──────────────────────────────────────────────────────────────────
#  Host admit / kick
# ──────────────────────────────────────────────────────────────────
async def admit_participant(db, *, session_id: str, participant_id: str,
                                                  admitted_by_user_id: str) -> dict:
    p = await db.podcast_recording_participants.find_one(
        {"id": participant_id, "session_id": session_id})
    if not p: raise HTTPException(404, "participant_not_found")
    if p.get("lobby_status") not in ("lobby", "admitted"):
        raise HTTPException(400, {"code": "invalid_lobby_state",
            "message": f"Cannot admit a participant in '{p.get('lobby_status')}' state."})
    now = _now()
    await db.podcast_recording_participants.update_one(
        {"id": participant_id},
        {"$set": {"lobby_status": "admitted",
                      "admitted_at": now}})
    sess = await db.podcast_recording_sessions.find_one({"id": session_id})
    await log_funnel(db, event="guest_admitted",
                                      user_id=admitted_by_user_id,
                                      session_id=session_id,
                                      channel_id=sess.get("channel_id") if sess else None,
                                      meta={"participant_id": participant_id})
    # Re-mint LiveKit token with can_publish=True and notify the guest's WS.
    from services import livekit_client as lk
    room = sess.get("livekit_room_name") or "" if sess else ""
    new_token = lk.mint_room_token(
        room_name=room, identity=participant_id, role="guest",
        permissions={"can_publish": True, "can_subscribe": True})
    await lobby_hub.broadcast_to_participant(session_id, participant_id, {
        "type":           "you_have_been_admitted",
        "livekit_token": new_token,
        "admitted_at": now.isoformat(),
    })
    return {"participant_id": participant_id, "lobby_status": "admitted",
              "livekit_token": new_token}


async def kick_participant(db, *, session_id: str, participant_id: str,
                                                kicked_by_user_id: str) -> dict:
    p = await db.podcast_recording_participants.find_one(
        {"id": participant_id, "session_id": session_id})
    if not p: raise HTTPException(404, "participant_not_found")
    if p.get("role") == "host":
        raise HTTPException(400, {"code": "cannot_kick_host"})
    await db.podcast_recording_participants.update_one(
        {"id": participant_id},
        {"$set": {"lobby_status": "kicked", "kicked_at": _now()}})
    sess = await db.podcast_recording_sessions.find_one({"id": session_id})
    from services import livekit_client as lk
    lk.remove_participant(room_name=(sess.get("livekit_room_name") or ""),
                                            identity=participant_id)
    await log_funnel(db, event="guest_kicked",
                                      user_id=kicked_by_user_id,
                                      session_id=session_id,
                                      channel_id=sess.get("channel_id") if sess else None,
                                      meta={"participant_id": participant_id})
    await lobby_hub.broadcast_to_participant(session_id, participant_id,
        {"type": "you_have_been_kicked"})
    return {"participant_id": participant_id, "lobby_status": "kicked"}


# ──────────────────────────────────────────────────────────────────
#  WebSocket Lobby Hub  (in-process; mirrors trivia_rooms pattern)
# ──────────────────────────────────────────────────────────────────
class LobbyHub:
    """In-memory pub/sub for podcast studio sessions.

    sockets[session_id] = {participant_id_or_'host:<uid>': WebSocket}
    For host(s) we key with 'host:<user_id>' so we can fan out to all
    hosts (currently only one) without colliding with participant_ids.
    """
    def __init__(self) -> None:
        self.sockets: dict = {}

    def _bucket(self, sid: str) -> dict:
        return self.sockets.setdefault(sid, {})

    def attach(self, sid: str, key: str, ws: WebSocket) -> None:
        self._bucket(sid)[key] = ws

    def detach(self, sid: str, key: str) -> None:
        b = self._bucket(sid)
        b.pop(key, None)
        if not b: self.sockets.pop(sid, None)

    async def _send(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_text(json.dumps(payload, default=str))
        except Exception as e:
            logger.warning("[36c-s2 ws] send failed: %s", e)

    async def broadcast_to_participant(self, sid: str, pid: str,
                                                                payload: dict) -> None:
        ws = self._bucket(sid).get(pid)
        if ws: await self._send(ws, payload)

    async def broadcast_to_role(self, sid: str, role: str,
                                                          payload: dict) -> None:
        prefix = f"{role}:" if role == "host" else ""
        for k, ws in list(self._bucket(sid).items()):
            if role == "host" and k.startswith("host:"):
                await self._send(ws, payload)
            elif role == "guest" and not k.startswith("host:"):
                await self._send(ws, payload)

    async def broadcast_all(self, sid: str, payload: dict) -> None:
        for ws in list(self._bucket(sid).values()):
            await self._send(ws, payload)


lobby_hub = LobbyHub()


# ──────────────────────────────────────────────────────────────────
#  Multi-track mixing  (FFmpeg amix + loudnorm)
# ──────────────────────────────────────────────────────────────────
def ffmpeg_amix_tracks(track_paths: list, out_path: Path) -> int:
    """Mix N mp3 tracks with `amix` + `loudnorm I=-16:TP=-1.5:LRA=11`.
    Returns ffmpeg returncode (0 = success)."""
    if not track_paths:
        return -1
    n = len(track_paths)
    if n == 1:
        # Single track: just loudnorm-pass, no amix needed.
        cmd = ["ffmpeg", "-y", "-i", str(track_paths[0]),
                  "-filter_complex",
                  "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]",
                  "-map", "[a]", "-ac", "2", "-ar", "44100",
                  "-codec:a", "libmp3lame", "-b:a", "128k", str(out_path)]
    else:
        inputs: list = []
        for p in track_paths:
            inputs += ["-i", str(p)]
        chain = "".join(f"[{i}:a]" for i in range(n))
        fc = (f"{chain}amix=inputs={n}:duration=longest:normalize=0[mix];"
                  f"[mix]loudnorm=I=-16:TP=-1.5:LRA=11[a]")
        cmd = ["ffmpeg", "-y", *inputs,
                  "-filter_complex", fc, "-map", "[a]",
                  "-ac", "2", "-ar", "44100",
                  "-codec:a", "libmp3lame", "-b:a", "128k", str(out_path)]
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, timeout=300)
        if r.returncode != 0:
            logger.warning("[36c-s2] ffmpeg amix failed rc=%s stderr=%s",
                                          r.returncode, r.stderr.decode("utf-8", "ignore")[:500])
        return r.returncode
    except Exception as e:
        logger.warning("[36c-s2] ffmpeg amix crash: %s", e)
        return -1


async def collect_participant_tracks(db, *, session_id: str
                                                                  ) -> list:
    """Return ordered list of (participant_id, role, display_name, mp3_path)
    for all completed uploads. Ordered by joined_at then admitted_at."""
    parts = await db.podcast_recording_participants.find(
        {"session_id": session_id, "upload_status": "completed"},
        {"_id": 0}).to_list(10)
    parts.sort(key=lambda p: (p.get("joined_at") or _now(),
                                                p.get("admitted_at") or _now()))
    out = []
    sess_dir = STORAGE_ROOT / session_id
    for p in parts:
        role = p.get("role", "guest")
        fname = "host.mp3" if role == "host" else f"{p['id']}.mp3"
        mp3 = sess_dir / fname
        if mp3.exists() and mp3.stat().st_size > 0:
            # Phase 36c Stage 3 — surface optional mp4 sibling.
            vfname = "host_video.mp4" if role == "host" else f"{p['id']}_video.mp4"
            mp4 = sess_dir / vfname
            has_video = (p.get("video_upload_status") == "completed"
                                  and mp4.exists() and mp4.stat().st_size > 0)
            # Phase 36c Stage 4 — surface optional screen-share sibling.
            sfname = "host_screen.mp4" if role == "host" else f"{p['id']}_screen.mp4"
            screen = sess_dir / sfname
            has_screen = (p.get("screen_upload_status") == "completed"
                                    and screen.exists() and screen.stat().st_size > 0)
            out.append({
                "participant_id": p["id"],
                "role": role,
                "display_name": p.get("display_name") or "Host",
                "mp3_path": mp3,
                "mp4_path": (mp4 if has_video else None),
                "screen_path": (screen if has_screen else None),
                "has_video": bool(has_video),
                "has_screen": bool(has_screen),
            })
    return out


def build_diarization_speaker_map(tracks: list) -> dict:
    """Map AssemblyAI speaker labels A/B/C/D to participant_ids in
    join-order. Host = A by convention."""
    out = {}
    labels = "ABCDEFGH"
    for i, t in enumerate(tracks):
        if i >= len(labels): break
        out[labels[i]] = {
            "participant_id": t["participant_id"],
            "display_name":   t["display_name"],
            "role":                t["role"],
        }
    return out
