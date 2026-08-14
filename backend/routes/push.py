"""Push device registration — relays the native FCM/APNs token to the
Emergent managed push service (SuprSend). Tokens are NOT stored in our DB."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.push_service import register_device

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["push"])


class RegisterPushBody(BaseModel):
    user_id: str
    platform: str  # "android" | "ios"
    device_token: str


@router.post("/register-push", status_code=201)
async def register_push(body: RegisterPushBody):
    try:
        await register_device(body.user_id, body.platform, body.device_token)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:  # noqa: BLE001 — provider hiccup, don't crash the client
        logger.warning("register-push relay failed (non-blocking): %s", e)
        raise HTTPException(502, "Push provider unavailable")
    return {"status": "registered"}


__all__ = ["router"]
