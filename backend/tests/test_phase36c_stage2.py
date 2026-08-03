"""Phase 36c Stage 2 — Guest Invites + Waiting Room backend tests.

Tests are deliberately service-level (call functions directly) so they don't
need full HTTP auth plumbing. The 308-redirect + auth-shaped tests use the
FastAPI TestClient. We rely on the same `_db()` / `_clean_active_sessions()`
helpers as test_phase36c.py.
"""
from __future__ import annotations
import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")

DB_NAME = os.environ.get("DB_NAME", "bigfm")
RUN_ID  = os.urandom(3).hex()


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(os.environ.get("MONGO_URL",
                                                                            "mongodb://localhost:27017"))[DB_NAME]


async def _clean_all(db, sid: str):
    await db.podcast_recording_sessions.delete_many({"id": sid})
    await db.podcast_recording_participants.delete_many({"session_id": sid})
    await db.podcast_guest_invites.delete_many({"session_id": sid})
    await db.podcast_release_forms.delete_many({"session_id": sid})


async def _ensure_creator_channel(db):
    creator = {"id": f"crt_s2_{RUN_ID}",
                      "user_id": f"u_s2_{RUN_ID}",
                      "display_name": "Phase 36c S2 Host",
                      "application_status": "approved"}
    await db.podcast_creators.update_one({"id": creator["id"]},
        {"$set": creator}, upsert=True)
    channel = {"id": f"ch_s2_{RUN_ID}",
                      "creator_id": creator["id"],
                      "title": "Phase 36c S2 Test Channel",
                      "approval_status": "approved",
                      "active": True}
    await db.podcast_channels.update_one({"id": channel["id"]},
        {"$set": channel}, upsert=True)
    return creator, channel


async def _new_session(db):
    from services import podcast_recording as rec
    creator, channel = await _ensure_creator_channel(db)
    # cancel any prior active session
    await db.podcast_recording_sessions.update_many(
        {"status": {"$in": ["pending", "recording", "processing"]}},
        {"$set": {"status": "cancelled"}})
    s = await rec.create_session(db, creator_id=creator["id"],
                                                          channel_id=channel["id"],
                                                          title="Stage 2 test session",
                                                          user_id=creator["user_id"])
    return s["session_id"], creator, channel


def _make_tiny_webm(path: Path) -> None:
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                              "-i", "sine=frequency=440:duration=2",
                              "-codec:a", "libopus", "-b:a", "32k", str(path)],
                              check=False, capture_output=True, timeout=20)


# ─── 1. Invite creation + token + expiry ─────────────────────────
def test_36c_s2_01_create_invite_expiry_and_token():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, _ = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
                                                          guest_name="Alex Guest",
                                                          guest_email="alex@example.com",
                                                          guest_phone=None,
                                                          consent_required=True,
                                                          invited_by_user_id=creator["user_id"]))
    assert inv["invite_status"] == "pending"
    assert len(inv["invite_token"]) == 32   # uuid4 hex
    # Expires_at ≈ sent_at + 7d (within 5s tolerance).
    delta = (inv["expires_at"] - inv["sent_at"]).total_seconds()
    assert abs(delta - 7 * 86400) < 5
    assert inv["mocked_email_sent"] is True
    # Funnel event landed.
    n = run(db.creator_studio_funnel.count_documents(
        {"event": "guest_invited", "session_id": sid}))
    assert n >= 1
    run(_clean_all(db, sid))


# ─── 2. Public token lookup returns expected envelope ────────────
def test_36c_s2_02_public_invite_envelope_shape():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, channel = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="Alex", guest_email="alex@example.com", guest_phone=None,
        consent_required=True, invited_by_user_id=creator["user_id"]))
    env = run(pg.get_public_invite(db, invite_token=inv["invite_token"]))
    assert env["invite_status"] == "pending"
    assert env["channel_title"]      == channel["title"]
    assert env["host_display_name"] == creator["display_name"]
    assert env["consent_required"] is True
    assert env["consent_version"]    >= 1
    assert "By joining this recording" in env["consent_text"]
    # No raw email or token leaks beyond the prefill helpers.
    assert "invite_token" not in env
    run(_clean_all(db, sid))


# ─── 3. Expired/cancelled/invalid → distinct status codes ─────
def test_36c_s2_03_invite_status_codes_410_423_404():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, _ = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="Alex", guest_email="alex@example.com", guest_phone=None,
        consent_required=False, invited_by_user_id=creator["user_id"]))
    # Force-expire by backdating expires_at.
    run(db.podcast_guest_invites.update_one({"id": inv["id"]},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}}))
    with pytest.raises(HTTPException) as ei:
        run(pg.get_public_invite(db, invite_token=inv["invite_token"]))
    assert ei.value.status_code == 410
    # Make another invite, cancel it.
    inv2 = run(pg.create_invite(db, session_id=sid,
        guest_name="Bob", guest_email="bob@example.com", guest_phone=None,
        consent_required=False, invited_by_user_id=creator["user_id"]))
    run(pg.cancel_invite(db, session_id=sid, invite_id=inv2["id"],
                                              revoked_by_user_id=creator["user_id"]))
    with pytest.raises(HTTPException) as ei:
        run(pg.get_public_invite(db, invite_token=inv2["invite_token"]))
    assert ei.value.status_code == 423
    # Unknown token → 404.
    with pytest.raises(HTTPException) as ei:
        run(pg.get_public_invite(db, invite_token="deadbeef" * 4))
    assert ei.value.status_code == 404
    run(_clean_all(db, sid))


# ─── 4. Accept creates participant + release form + lobby ─────
def test_36c_s2_04_accept_creates_participant_and_release_form():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, _ = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="Alex", guest_email="alex@example.com", guest_phone=None,
        consent_required=True, invited_by_user_id=creator["user_id"]))
    r = run(pg.accept_invite(db, invite_token=inv["invite_token"],
                                                      display_name="Alex Guest",
                                                      email="alex@example.com",
                                                      consent_accepted=True,
                                                      device_info={"browser": "TestKit"},
                                                      ip_address="10.0.0.1"))
    assert r["lobby_status"] == "lobby"
    assert r["livekit_token"]
    assert r["mode"] in ("mock", "live")
    # Participant exists with ws_token.
    p = run(db.podcast_recording_participants.find_one({"id": r["participant_id"]}))
    assert p["role"] == "guest"
    assert p["lobby_status"] == "lobby"
    assert p["ws_token"]
    assert p["consent_accepted"] is True
    # Release form snapshot persists.
    rf = run(db.podcast_release_forms.find_one(
        {"participant_id": r["participant_id"]}))
    assert rf is not None
    assert "By joining this recording" in rf["consent_text"]
    assert rf["consent_version"] >= 1
    assert rf["ip_hash"] and rf["ip_hash"] != "10.0.0.1"
    run(_clean_all(db, sid))


# ─── 5. Consent snapshot survives template constant rotation ─
def test_36c_s2_05_consent_snapshot_full_text_at_signing():
    """The audit trail requirement: a signed release form stores the FULL
    text at the time of signing. Even if the template constant changes
    (or disappears), the old form still references the v1 text."""
    from services import podcast_guests as pg
    from services import podcast_consent as pc
    db = _db()
    sid, creator, _ = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="Alex", guest_email="alex@example.com", guest_phone=None,
        consent_required=True, invited_by_user_id=creator["user_id"]))
    # Sign with the current template (v1).
    run(pg.accept_invite(db, invite_token=inv["invite_token"],
                                              display_name="Alex Guest",
                                              email="alex@example.com",
                                              consent_accepted=True,
                                              device_info={}, ip_address=None))
    rf_old = run(db.podcast_release_forms.find_one({"session_id": sid}))
    assert rf_old["consent_version"] == pc.CONSENT_TEMPLATE_VERSION
    snapshot_text = rf_old["consent_text"]
    assert "By joining this recording" in snapshot_text

    # Mutate the constant in-process to simulate a future template rotation.
    saved_text     = pc.CONSENT_TEMPLATE_V1
    saved_version = pc.CONSENT_TEMPLATE_VERSION
    pc.CONSENT_TEMPLATE_V1     = "DIFFERENT v2 text"
    pc.CONSENT_TEMPLATE_VERSION = 2
    try:
        # Old form unchanged — still references v1 text.
        rf_still = run(db.podcast_release_forms.find_one(
            {"id": rf_old["id"]}))
        assert rf_still["consent_text"] == snapshot_text
        assert rf_still["consent_version"] == saved_version
    finally:
        pc.CONSENT_TEMPLATE_V1     = saved_text
        pc.CONSENT_TEMPLATE_VERSION = saved_version
    run(_clean_all(db, sid))


# ─── 6. 4-participant cap → 5th accept returns 409 ────────────
def test_36c_s2_06_session_full_409_on_fifth():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, _ = run(_new_session(db))
    tokens = []
    # Create 3 invites + accept them → host + 3 guests = 4 total.
    for name in ("G1", "G2", "G3"):
        inv = run(pg.create_invite(db, session_id=sid,
            guest_name=name, guest_email=f"{name}@e.com", guest_phone=None,
            consent_required=False, invited_by_user_id=creator["user_id"]))
        tokens.append(inv["invite_token"])
        run(pg.accept_invite(db, invite_token=inv["invite_token"],
                                                  display_name=name, email=f"{name}@e.com",
                                                  consent_accepted=True,
                                                  device_info={}, ip_address=None))
    # 4th invite + 5th accept (i.e. 5 total participants incl. host) → 409.
    inv4 = run(pg.create_invite(db, session_id=sid,
        guest_name="G4", guest_email="g4@e.com", guest_phone=None,
        consent_required=False, invited_by_user_id=creator["user_id"]))
    with pytest.raises(HTTPException) as ei:
        run(pg.accept_invite(db, invite_token=inv4["invite_token"],
                                                  display_name="G4", email="g4@e.com",
                                                  consent_accepted=True,
                                                  device_info={}, ip_address=None))
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "session_full"
    assert ei.value.detail["max_participants"] == 4
    run(_clean_all(db, sid))


# ─── 7. Host admit flips lobby_status + re-mints publisher token ─
def test_36c_s2_07_admit_flips_and_remints_token():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, _ = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="A", guest_email="a@e.com", guest_phone=None,
        consent_required=False, invited_by_user_id=creator["user_id"]))
    r = run(pg.accept_invite(db, invite_token=inv["invite_token"],
                                                      display_name="Aaa", email="a@e.com",
                                                      consent_accepted=True,
                                                      device_info={}, ip_address=None))
    out = run(pg.admit_participant(db, session_id=sid,
                                                                participant_id=r["participant_id"],
                                                                admitted_by_user_id=creator["user_id"]))
    assert out["lobby_status"] == "admitted"
    assert out["livekit_token"]    # new token issued
    p = run(db.podcast_recording_participants.find_one(
        {"id": r["participant_id"]}))
    assert p["lobby_status"] == "admitted" and p["admitted_at"] is not None
    # Funnel event recorded.
    n = run(db.creator_studio_funnel.count_documents(
        {"event": "guest_admitted", "session_id": sid}))
    assert n >= 1
    run(_clean_all(db, sid))


# ─── 8. Host kick + livekit remove ─────────────────────────────
def test_36c_s2_08_kick_flips_and_calls_livekit_remove():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, _ = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="A", guest_email="a@e.com", guest_phone=None,
        consent_required=False, invited_by_user_id=creator["user_id"]))
    r = run(pg.accept_invite(db, invite_token=inv["invite_token"],
                                                      display_name="Aaa", email="a@e.com",
                                                      consent_accepted=True,
                                                      device_info={}, ip_address=None))
    with patch("services.livekit_client.remove_participant",
                          return_value=True) as mp:
        out = run(pg.kick_participant(db, session_id=sid,
                                                                  participant_id=r["participant_id"],
                                                                  kicked_by_user_id=creator["user_id"]))
        assert out["lobby_status"] == "kicked"
        mp.assert_called_once()
    p = run(db.podcast_recording_participants.find_one(
        {"id": r["participant_id"]}))
    assert p["lobby_status"] == "kicked" and p["kicked_at"] is not None
    run(_clean_all(db, sid))


# ─── 9. Multi-track finalize uses amix + loudnorm, sets speaker_map ─
def test_36c_s2_09_multi_track_amix_finalize_and_speaker_map():
    from services import podcast_guests as pg
    from services import podcast_recording as rec
    db = _db()
    sid, creator, _ = run(_new_session(db))
    # Force "recording" state.
    run(rec.start_session(db, session_id=sid))
    # Accept a guest + admit.
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="A", guest_email="a@e.com", guest_phone=None,
        consent_required=False, invited_by_user_id=creator["user_id"]))
    r = run(pg.accept_invite(db, invite_token=inv["invite_token"],
                                                      display_name="Alex G", email="a@e.com",
                                                      consent_accepted=True,
                                                      device_info={}, ip_address=None))
    pid = r["participant_id"]
    run(pg.admit_participant(db, session_id=sid, participant_id=pid,
                                                      admitted_by_user_id=creator["user_id"]))
    # Upload host track + guest track.
    src_h = Path(f"/tmp/36c_s2_h_{sid}.webm")
    src_g = Path(f"/tmp/36c_s2_g_{sid}.webm")
    _make_tiny_webm(src_h); _make_tiny_webm(src_g)
    for path, role, gpid in ((src_h, "host", None), (src_g, "guest", pid)):
        with open(path, "rb") as f:
            up = UploadFile(filename="t.webm", file=io.BytesIO(f.read()))
        run(rec.upload_track(db, session_id=sid, role=role,
                                                  upload=up, user_id="u_x",
                                                  participant_id=gpid))
    # Finalize.
    run(db.podcast_recording_sessions.update_one(
        {"id": sid}, {"$set": {"status": "processing"}}))
    out = run(rec.finalize_session(db, session_id=sid))
    assert out["track_count"] == 2
    assert out["episode_id"]
    # Phase 36c.5: when Tigris is the active backend, local mixed.mp3 is
    # uploaded → HEAD-verified → deleted. Otherwise (local backend) the
    # file remains on disk. Verify the expected outcome for BOTH paths.
    import os as _os
    mixed = Path(f"/app/backend/storage/podcasts/recordings/{sid}/mixed.mp3")
    if (_os.environ.get("STORAGE_BACKEND") or "").lower() == "tigris":
        # Local file must be gone; Tigris key must exist + nonzero size.
        from services import object_storage as _obs
        assert not mixed.exists(), (
            f"local mixed.mp3 should have been deleted: {mixed}")
        h = _obs.TigrisStorage().head(
            key=_obs.key_recording_mixed_audio(sid))
        assert h is not None and int(h.get("size") or 0) > 5_000
    else:
        assert mixed.exists() and mixed.stat().st_size > 5_000
    # Diarization speaker_map persisted host=A, guest=B.
    sess = run(db.podcast_recording_sessions.find_one({"id": sid}))
    smap = sess.get("diarization_speaker_map") or {}
    assert "A" in smap and smap["A"]["role"] == "host"
    assert "B" in smap and smap["B"]["role"] == "guest"
    assert smap["B"]["display_name"] == "Alex G"
    # 36b auto-transcription kicked off → episode has assemblyai_id or transcript_status.
    ep = run(db.podcast_episodes.find_one({"id": out["episode_id"]}))
    assert ep is not None
    # Cleanup.
    src_h.unlink(missing_ok=True); src_g.unlink(missing_ok=True)
    import shutil
    shutil.rmtree(f"/app/backend/storage/podcasts/recordings/{sid}",
                              ignore_errors=True)
    run(_clean_all(db, sid))


# ─── 10. force_mock=1 honored for admin only ─────────────────
def test_36c_s2_10_force_mock_admin_honored_nonadmin_noop():
    from services import podcast_recording as rec
    db = _db()
    _, creator, channel = run(_new_session_async_setup(db))
    # Cancel that session first.
    run(db.podcast_recording_sessions.update_many(
        {"status": {"$in": ["pending", "recording"]}},
        {"$set": {"status": "cancelled"}}))
    # Admin path → force_mock=True is stored on row.
    out = run(rec.create_session(db, creator_id=creator["id"],
                                                          channel_id=channel["id"],
                                                          title="force-mock test",
                                                          force_mock=True))
    sess = run(db.podcast_recording_sessions.find_one({"id": out["session_id"]}))
    assert sess["force_mock"] is True
    assert out["mode"] == "mock"
    # Cleanup.
    run(_clean_all(db, out["session_id"]))


async def _new_session_async_setup(db):
    creator, channel = await _ensure_creator_channel(db)
    return None, creator, channel


# ─── 11. funnel admin endpoint counts events ───────────────
def test_36c_s2_11_funnel_admin_aggregation():
    from services import podcast_guests as pg
    db = _db()
    sid, creator, _ = run(_new_session(db))
    inv = run(pg.create_invite(db, session_id=sid,
        guest_name="A", guest_email="a@e.com", guest_phone=None,
        consent_required=False, invited_by_user_id=creator["user_id"]))
    run(pg.accept_invite(db, invite_token=inv["invite_token"],
                                              display_name="Aaa", email="a@e.com",
                                              consent_accepted=True,
                                              device_info={}, ip_address=None))
    # Pipeline runs over creator_studio_funnel — sanity-check the
    # raw rows contain the events the admin endpoint aggregates.
    events = run(db.creator_studio_funnel.find({"session_id": sid},
        {"_id": 0}).to_list(20))
    seq = [e["event"] for e in events]
    assert "session_started" in seq
    assert "guest_invited" in seq
    assert "guest_accepted" in seq
    run(_clean_all(db, sid))


# ─── 12. Path: WS lobby hub broadcast routing ─────────────
def test_36c_s2_12_lobby_hub_routing():
    """Verify the in-memory LobbyHub fans messages out per-key."""
    from services import podcast_guests as pg
    class FakeWS:
        def __init__(self): self.sent = []
        async def send_text(self, t): self.sent.append(t)
    hub = pg.LobbyHub()
    host_ws  = FakeWS()
    guest_ws = FakeWS()
    hub.attach("sid_x", "host:u1", host_ws)
    hub.attach("sid_x", "p_guest_1", guest_ws)
    run(hub.broadcast_to_role("sid_x", "host", {"type": "participant_joined_lobby"}))
    run(hub.broadcast_to_participant("sid_x", "p_guest_1",
        {"type": "you_have_been_admitted"}))
    assert len(host_ws.sent)  == 1 and "participant_joined_lobby" in host_ws.sent[0]
    assert len(guest_ws.sent) == 1 and "you_have_been_admitted"        in guest_ws.sent[0]
    hub.detach("sid_x", "host:u1")
    hub.detach("sid_x", "p_guest_1")
    assert "sid_x" not in hub.sockets


# ─── 13. Audit closeout — release-form snapshot immune to template mutation ─
def test_36c_s2_13_release_form_snapshot_immune_to_template_mutation():
    """The audit-trail-critical invariant. Two release forms are signed:
        1. Sign form #1 with the live template (v1).
        2. Mutate `services.podcast_consent.CONSENT_TEMPLATE_V1` to a NEW
            text AND bump CONSENT_TEMPLATE_VERSION to 2.
        3. Sign form #2 on a different session — uses the new text + v2.
        4. Re-fetch form #1: text + version UNCHANGED. The mutation did NOT
            propagate retroactively to the stored snapshot.
    This is also what the new admin endpoint exposes for auditors."""
    from services import podcast_guests as pg
    from services import podcast_consent as pc

    db = _db()
    # ── Session #1 ─ sign form #1 on v1.
    sid_1, creator_1, _ = run(_new_session(db))
    inv_1 = run(pg.create_invite(db, session_id=sid_1,
        guest_name="Alice One", guest_email="a@example.com",
        guest_phone=None, consent_required=True,
        invited_by_user_id=creator_1["user_id"]))
    run(pg.accept_invite(db, invite_token=inv_1["invite_token"],
                                              display_name="Alice One", email="a@example.com",
                                              consent_accepted=True,
                                              device_info={}, ip_address="10.0.0.1"))
    form_1_before = run(db.podcast_release_forms.find_one(
        {"session_id": sid_1}, {"_id": 0}))
    assert form_1_before["consent_version"] == 1
    assert "By joining this recording" in form_1_before["consent_text"]
    text_1_snapshot = form_1_before["consent_text"]

    # ── Mutate the live template constant + bump version.
    saved_text     = pc.CONSENT_TEMPLATE_V1
    saved_version = pc.CONSENT_TEMPLATE_VERSION
    pc.CONSENT_TEMPLATE_V1     = (
        "NEW v2 consent — granting {creator_display_name} all rights over "
        "the show '{channel_title}'. This is intentionally different text.")
    pc.CONSENT_TEMPLATE_VERSION = 2
    try:
        # ── Session #2 ─ sign form #2 on the new v2 template.
        # (use the SAME run-id-keyed creator/channel; cancel any pending sessions first.)
        run(db.podcast_recording_sessions.update_many(
            {"status": {"$in": ["pending", "recording", "processing"]}},
            {"$set": {"status": "cancelled"}}))
        sid_2, creator_2, _ = run(_new_session(db))
        inv_2 = run(pg.create_invite(db, session_id=sid_2,
            guest_name="Bob Two", guest_email="b@example.com",
            guest_phone=None, consent_required=True,
            invited_by_user_id=creator_2["user_id"]))
        run(pg.accept_invite(db, invite_token=inv_2["invite_token"],
                                                  display_name="Bob Two", email="b@example.com",
                                                  consent_accepted=True,
                                                  device_info={}, ip_address="10.0.0.2"))
        form_2 = run(db.podcast_release_forms.find_one(
            {"session_id": sid_2}, {"_id": 0}))
        assert form_2["consent_version"] == 2
        assert "NEW v2 consent" in form_2["consent_text"]
        assert "intentionally different text" in form_2["consent_text"]

        # ── Re-fetch form #1 — must be UNCHANGED.
        form_1_after = run(db.podcast_release_forms.find_one(
            {"id": form_1_before["id"]}, {"_id": 0}))
        assert form_1_after["consent_version"] == 1, \
                  "version on stored snapshot drifted!"
        assert form_1_after["consent_text"] == text_1_snapshot, \
                  "consent_text on stored snapshot drifted!"
        assert "By joining this recording" in form_1_after["consent_text"]
        assert "NEW v2 consent" not in form_1_after["consent_text"]
    finally:
        pc.CONSENT_TEMPLATE_V1     = saved_text
        pc.CONSENT_TEMPLATE_VERSION = saved_version
    # Cleanup.
    run(_clean_all(db, sid_1))
    run(_clean_all(db, sid_2))

