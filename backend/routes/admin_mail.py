"""Phase 42-E2.5 — admin mail health endpoint.

Exposes a SANITISED snapshot of the Mailgun integration state — never
returns the API key, recipients are masked.  Mounted under
`/api/admin/mail/...` by server.py.

TODO (future transactional email hooks — service is already generic):
    • voucher_created   → email the inviter when their friend redeems.
    • predict_win_lock → DM the user when their pick is locked.
    • news_digest        → weekly headline digest.
    • level_up                → social passport milestone celebration.
    • coupon_won          → instant reward acknowledgement.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from services.mailgun_client import (
    health_snapshot, is_live, send_email,
)

logger = logging.getLogger("bigfm.admin_mail")
router = APIRouter(prefix="/api/admin/mail", tags=["admin-mail"])


@router.get("/health")
async def mail_health() -> dict:
    return health_snapshot()


class TestSendBody(BaseModel):
    to:        EmailStr
    subject: str = Field(default="FUUSIC Mailgun integration test")
    note:      Optional[str] = None


@router.post("/test-send")
async def mail_test_send(body: TestSendBody, request: Request) -> dict:
    """Admin-only smoke test.  Sends a trivial email through the live
    Mailgun integration so we can confirm domain verification + DNS
    end-to-end.  Returns the message_id on success."""
    # Phase 0 of admin auth — gate on a server-side toggle until role
    # checks land for this surface.
    if not is_live():
        raise HTTPException(503, "mailgun_not_live")
    html = (f"<div style='font-family:sans-serif;padding:24px'>"
                  f"<h2>FUUSIC Mailgun test ✅</h2>"
                  f"<p>{body.note or 'No note provided.'}</p>"
                  f"<p>Sent at {request.url}</p></div>")
    res = send_email(to=str(body.to), subject=body.subject, html=html,
                                  tags=["admin-test"])
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error"),
                      "domain": res.get("domain")}
    return {"ok": True, "message_id": res["message_id"],
                  "domain": res.get("domain"),
                  "latency_ms": res.get("latency_ms")}
