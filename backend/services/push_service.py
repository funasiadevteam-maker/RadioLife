"""Emergent-managed push notifications (SuprSend relay).

The backend is the ONLY caller of the Emergent push relay. Device tokens are
resolved internally by SuprSend from the user_id — we NEVER store tokens in
our DB. `EMERGENT_PUSH_KEY` is injected by the deployment pipeline; locally it
is the literal "placeholder" (relay returns 401, which we swallow at the edge).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PUSH_BASE_URL = "https://integrations.emergentagent.com"
PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")

_client = httpx.AsyncClient(
    base_url=PUSH_BASE_URL,
    headers={"X-Push-Key": PUSH_KEY},
    timeout=10.0,
)


async def register_device(user_id: str, platform: str, device_token: str) -> None:
    """Relay a device registration to the Emergent push service."""
    resp = await _client.post(
        "/api/v1/push/users/register",
        json={"user_id": user_id, "platform": platform, "device_token": device_token},
    )
    if resp.status_code == 401:
        raise RuntimeError("EMERGENT_PUSH_KEY missing or invalid")
    resp.raise_for_status()


async def send_push(recipients: list[str], data: dict,
                    idempotency_key: Optional[str] = None) -> None:
    """Send a push to a list of user IDs. Caller MUST wrap in try/except —
    push failure should never block the primary operation."""
    if not recipients:
        return
    if len(recipients) > 100:
        raise ValueError("max 100 recipients per /trigger call; chunk before sending")
    if "title" not in data or "message" not in data:
        raise ValueError("data must include title and message")
    payload: dict = {"recipients": recipients, "data": data}
    if idempotency_key:
        payload["$idempotency_key"] = idempotency_key
    resp = await _client.post("/api/v1/push/trigger", json=payload)
    if resp.status_code == 401:
        raise RuntimeError("EMERGENT_PUSH_KEY missing or invalid")
    resp.raise_for_status()


__all__ = ["register_device", "send_push"]
