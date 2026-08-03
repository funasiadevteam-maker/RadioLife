"""Phase 36c POC — LiveKit integration shape.

MOCKED-by-default, env-gated live. All three env vars
(`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_URL`) must be set
for `is_live()` to return True. When any is missing, every call returns
a deterministic mock so the studio flow is testable end-to-end without
the LiveKit cloud or self-hosted server.

POC consumes only `mint_room_token` + `create_room`. The full 36c MVP
(multi-participant rooms, screen share, server-side recording egress)
will extend this client without rewriting the surface.

Live path uses the official `livekit-api` Python SDK. The SDK is NOT
imported at module load — it's a lazy import inside `_live_*` so that
mock-mode deploys (the default) don't need the dependency installed.
"""
from __future__ import annotations
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.livekit")

_MOCK_URL = "mock://livekit"


def is_live(*, force_mock: bool = False) -> bool:
    """When force_mock=True, returns False unconditionally — useful as an
    A/B canary during the eventual live cutover (Phase 36c Stage 2 added)."""
    if force_mock:
        return False
    return all(
        (os.environ.get(k) or "").strip()
        for k in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL"))


def livekit_url() -> str:
    if is_live():
        return os.environ["LIVEKIT_URL"]
    return _MOCK_URL


def status() -> dict:
    return {
        "is_live":                  is_live(),
        "api_key_present":     bool((os.environ.get("LIVEKIT_API_KEY") or "").strip()),
        "api_secret_present": bool((os.environ.get("LIVEKIT_API_SECRET") or "").strip()),
        "url_present":             bool((os.environ.get("LIVEKIT_URL") or "").strip()),
        "last_check_at":         datetime.now(timezone.utc).isoformat(),
        "mode":                          "live" if is_live() else "mock",
    }


def mint_room_token(*, room_name: str, identity: str,
                                          role: str = "host",
                                          permissions: Optional[dict] = None,
                                          ttl_seconds: int = 3600) -> str:
    """Returns a JWT string. MOCK format (Phase 36c Stage 4 A1): the suffix is
    base64url-encoded JSON claims so tests can assert on permissions without
    hitting the live LiveKit SDK.
        format: `mock_lk_<b64url(claims_json)>`
        claims: {room, identity, role,
                          can_publish_audio, can_publish_video, can_publish_screen,
                          exp}
    Legacy clients that treated the token as opaque keep working.
    """
    role = "host" if role not in ("host", "guest") else role
    perms = permissions or {}
    if not is_live():
        import base64, json
        from datetime import timedelta
        claims = {
            "room": room_name, "identity": identity, "role": role,
            "can_publish_audio":    bool(perms.get("can_publish", True)),
            "can_publish_video":    bool(perms.get("can_publish_video", False)),
            "can_publish_screen": bool(perms.get("can_publish_screen", False)),
            "exp": (datetime.now(timezone.utc) +
                          timedelta(seconds=ttl_seconds)).isoformat(),
        }
        b = base64.urlsafe_b64encode(
            json.dumps(claims, separators=(",", ":")).encode()).decode().rstrip("=")
        return f"mock_lk_{b}"
    # Live path — lazy SDK import.
    from datetime import timedelta
    from livekit import api    # type: ignore
    grant = api.VideoGrants(
        room_join=True, room=room_name,
        can_publish=perms.get("can_publish", True),
        can_subscribe=perms.get("can_subscribe", True),
        can_publish_data=perms.get("can_publish_data", True))
    tok = (api.AccessToken(os.environ["LIVEKIT_API_KEY"],
                                              os.environ["LIVEKIT_API_SECRET"])
                  .with_identity(identity)
                  .with_name(identity)
                  .with_grants(grant)
                  .with_ttl(timedelta(seconds=ttl_seconds)))
    return tok.to_jwt()


def create_room(*, room_name: str, max_participants: int = 10) -> dict:
    """Live: hit LiveKit room service. Mock: stub a deterministic sid."""
    if not is_live():
        return {
            "room_name":             room_name,
            "sid":                          f"mock_room_sid_{uuid.uuid4().hex[:12]}",
            "created_at":             datetime.now(timezone.utc).isoformat(),
            "max_participants": max_participants,
            "mode":                       "mock",
        }
    from livekit import api  # type: ignore
    svc = api.RoomService(os.environ["LIVEKIT_URL"],
                                              os.environ["LIVEKIT_API_KEY"],
                                              os.environ["LIVEKIT_API_SECRET"])
    r = svc.create_room(api.CreateRoomRequest(
        name=room_name, empty_timeout=300,
        max_participants=max_participants))
    return {
        "room_name":             room_name,
        "sid":                          r.sid,
        "created_at":             datetime.now(timezone.utc).isoformat(),
        "max_participants": max_participants,
        "mode":                       "live",
    }


def delete_room(room_name: str) -> None:
    """Best-effort. Mock is a no-op; live tries DELETE but swallows errors."""
    if not is_live():
        return
    try:
        from livekit import api  # type: ignore
        svc = api.RoomService(os.environ["LIVEKIT_URL"],
                                                  os.environ["LIVEKIT_API_KEY"],
                                                  os.environ["LIVEKIT_API_SECRET"])
        svc.delete_room(api.DeleteRoomRequest(room=room_name))
    except Exception as e:
        logger.warning("[livekit] delete_room failed (non-fatal): %s", e)


def remove_participant(*, room_name: str, identity: str) -> bool:
    """Phase 36c Stage 2 — used when host kicks a guest or cancels an
    accepted invite. Mock returns True; live attempts LiveKit RoomService."""
    if not is_live():
        logger.info("[livekit MOCK] remove_participant room=%s identity=%s",
                              room_name, identity)
        return True
    try:
        from livekit import api  # type: ignore
        svc = api.RoomService(os.environ["LIVEKIT_URL"],
                                                  os.environ["LIVEKIT_API_KEY"],
                                                  os.environ["LIVEKIT_API_SECRET"])
        svc.remove_participant(api.RoomParticipantIdentity(
            room=room_name, identity=identity))
        return True
    except Exception as e:
        logger.warning("[livekit] remove_participant failed: %s", e)
        return False
