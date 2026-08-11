"""Transactional gift emails (buyer confirmation + recipient "you got a gift").

Routes through the existing Mailgun abstraction (`services.mailgun_client.send_email`),
which is a no-op returning {ok: False, ...} when Mailgun isn't configured — so
callers never fail the purchase UX. Meant to be scheduled via FastAPI
BackgroundTasks so the HTTP response isn't blocked by the network send.
"""
from __future__ import annotations

import logging
import os

from services.mailgun_client import send_email

log = logging.getLogger("bigfm.gift")

_BRAND = "#ea580c"


def _shell(title: str, body_html: str, cta_label: str, cta_url: str) -> str:
    return f"""\
<div style="margin:0;padding:24px;background:#0b0b0d;font-family:'Plus Jakarta Sans',Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#17171b;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,.08);">
    <div style="background:{_BRAND};padding:20px 24px;">
      <div style="color:#fff;font-size:20px;font-weight:800;letter-spacing:-.5px;">RadioLife</div>
    </div>
    <div style="padding:28px 24px;color:#e4e4e7;">
      <h1 style="margin:0 0 12px;font-size:22px;color:#f4f4f5;">{title}</h1>
      {body_html}
      <a href="{cta_url}" style="display:inline-block;margin-top:20px;background:{_BRAND};color:#fff;text-decoration:none;font-weight:800;padding:12px 22px;border-radius:999px;font-size:14px;">{cta_label}</a>
    </div>
    <div style="padding:16px 24px;color:#71717a;font-size:12px;border-top:1px solid rgba(255,255,255,.06);">
      RadioLife · Shop local, earn BigPoints.
    </div>
  </div>
</div>"""


def _base_url() -> str:
    return (os.environ.get("BIGFM_PUBLIC_BASE_URL") or "").rstrip("/")


def send_gift_emails(*, kind: str, item_name: str, sponsor_name: str | None,
                     buyer_email: str | None, buyer_name: str,
                     recipient_email: str | None, message: str | None) -> None:
    """Fire both gift emails. Safe to call from a background task (sync)."""
    sponsor = sponsor_name or "a local business"
    cta_url = f"{_base_url()}/shop/{'memberships' if kind == 'membership' else 'wallet'}"
    kind_label = {"package": "package", "membership": "membership",
                  "giftcard": "gift card"}.get(kind, "gift")

    # 1) Recipient — "you got a gift"
    if recipient_email:
        msg_block = (
            f'<div style="margin:16px 0;padding:14px 16px;background:#1e1e23;border-radius:12px;'
            f'border-left:3px solid {_BRAND};color:#d4d4d8;font-style:italic;">“{message}”</div>'
            if message else ""
        )
        body = (
            f'<p style="margin:0 0 8px;font-size:15px;line-height:1.6;">'
            f'<strong style="color:#f4f4f5;">{buyer_name}</strong> just sent you a '
            f'<strong style="color:{_BRAND};">{kind_label}</strong> at '
            f'<strong style="color:#f4f4f5;">{sponsor}</strong>:</p>'
            f'<p style="margin:0;font-size:18px;font-weight:800;color:#f4f4f5;">{item_name}</p>'
            f'{msg_block}'
            f'<p style="margin:16px 0 0;font-size:14px;color:#b4b4bb;line-height:1.6;">'
            f'Sign in to RadioLife with this email address to find it in your wallet and start using it.</p>'
        )
        res = send_email(
            to=recipient_email,
            subject=f"🎁 You've received a {kind_label}: {item_name}",
            html=_shell("You've got a gift! 🎁", body, "Open my wallet", cta_url),
            tags=["gift", f"gift-{kind}"],
        )
        log.info("[gift] recipient email kind=%s ok=%s", kind, res.get("ok"))

    # 2) Buyer — confirmation
    if buyer_email:
        who = recipient_email or "your friend"
        body = (
            f'<p style="margin:0;font-size:15px;line-height:1.6;">'
            f'Your gift is on its way to <strong style="color:#f4f4f5;">{who}</strong>.</p>'
            f'<p style="margin:12px 0 0;font-size:16px;font-weight:800;color:#f4f4f5;">{item_name}'
            f'<span style="color:#9a9aa2;font-weight:600;font-size:14px;"> · {sponsor}</span></p>'
            f'<p style="margin:16px 0 0;font-size:14px;color:#b4b4bb;line-height:1.6;">'
            f'They\'ll get an email to claim it. Thanks for spreading the love!</p>'
        )
        res = send_email(
            to=buyer_email,
            subject=f"Your {kind_label} gift to {who} is confirmed",
            html=_shell("Gift confirmed ✅", body, "View in RadioLife", cta_url),
            tags=["gift-confirm", f"gift-{kind}"],
        )
        log.info("[gift] buyer email kind=%s ok=%s", kind, res.get("ok"))


__all__ = ["send_gift_emails"]
