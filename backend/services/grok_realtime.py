"""xAI Grok Realtime Voice provider — server-side ephemeral token minting.

The permanent XAI_API_KEY NEVER leaves the backend. Browser / mobile clients
receive only a short-lived client secret that they pass as a WebSocket
subprotocol ("xai-client-secret.<value>") when connecting directly to xAI.

Docs: https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech
      https://docs.x.ai/developers/model-capabilities/audio/ephemeral-tokens
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("fuusic.grok")

XAI_CLIENT_SECRETS_URL = "https://api.x.ai/v1/realtime/client_secrets"
REALTIME_WS_BASE = "wss://api.x.ai/v1/realtime"


def _key() -> str:
    return (os.environ.get("XAI_API_KEY") or "").strip()


def is_configured() -> bool:
    return bool(_key())


def voice_model() -> str:
    return (os.environ.get("FUN_AI_VOICE_MODEL") or "grok-voice-latest").strip()


def voice_provider() -> str:
    return (os.environ.get("FUN_AI_VOICE_PROVIDER") or "grok").strip()


def grok_voice() -> str:
    return (os.environ.get("FUN_AI_GROK_VOICE") or "eve").strip()


def ws_url() -> str:
    return f"{REALTIME_WS_BASE}?model={voice_model()}"


async def mint_client_secret(expires_seconds: int = 300) -> dict:
    """POST to xAI to mint a short-lived client secret.

    Returns ``{"value": <secret>, "expires_at": <unix_ts>}``.
    Raises RuntimeError when the key is missing or xAI rejects the request.
    """
    key = _key()
    if not key:
        raise RuntimeError("xai_not_configured")
    secs = max(60, min(int(expires_seconds), 600))
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.post(
            XAI_CLIENT_SECRETS_URL,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"expires_after": {"seconds": secs}},
        )
    if r.is_error:
        log.warning("[grok] client_secret mint failed: %s", r.status_code)
        raise RuntimeError(f"xai_mint_failed_{r.status_code}")
    body = r.json()
    return {"value": body.get("value"), "expires_at": body.get("expires_at")}
