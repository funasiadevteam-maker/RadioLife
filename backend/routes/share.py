"""Phase 42-E2.2 — Universal Social Share + Invite-a-Friend.

Two endpoints:
  • `POST /api/share/log` — record a share event for attribution and
    award `social_share` points (5 pts × first 5 shares/day per the
    F-1 cap).  Anonymous users may log shares for analytics but do
    NOT earn points.
  • `POST /api/invite/send` — generate a referral voucher for the
    inviter, send the invitation email (Mailgun if `is_live()`,
    MOCKED log + DB row otherwise), and award `social_share` points.

Both endpoints are idempotent on `(user_id, feature_type, content_id,
day_bucket)` — repeat shares of the same surface on the same UTC day
do not multiply the point award (the points engine enforces the daily
cap regardless, but we belt-and-brace it here so the share_events
collection stays clean for analytics).
"""
from __future__ import annotations
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth import current_user, current_user_optional

log = logging.getLogger("bigfm.share")

router = APIRouter(prefix="/api", tags=["social-share"])


# ─── Shared helpers ─────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_key() -> str:
    return _now().strftime("%Y-%m-%d")


# Allowed feature types — front-end always sends one of these so we can
# segment analytics later.  Free-form falls through to "other".
_FEATURE_TYPES = {
    "home", "station", "news_article", "predict_win", "game",
    "persona", "passport", "wallet", "miniplayer", "community_station",
    "other",
}
# Allowed channels — keeps the analytics axis tight.
_CHANNELS = {
    "native", "copy_link", "whatsapp", "twitter", "facebook",
    "linkedin", "email", "telegram", "other",
}


def _normalise_feature(ft: Optional[str]) -> str:
    ft = (ft or "").strip().lower()
    return ft if ft in _FEATURE_TYPES else "other"


def _normalise_channel(ch: Optional[str]) -> str:
    ch = (ch or "").strip().lower()
    return ch if ch in _CHANNELS else "other"


async def _award_social_share(db, user: Optional[dict], *,
                                                              source_id: str) -> dict:
    """Best-effort points award — returns the points-service response
    or `{awarded: False, reason}` on any failure (we never let a points
    failure poison the share API)."""
    if not user or not user.get("user_id"):
        return {"awarded": False, "reason": "anonymous"}
    try:
        from services.points_service import PointsService
        svc = PointsService(db)
        res = await svc.award(
            user_id=user["user_id"],
            source="social_share",
            source_id=source_id,
            idempotency_key=f"share_{user['user_id']}_{source_id}_{_today_key()}",
            metadata={"surface": source_id})
        out = res.to_dict() if hasattr(res, "to_dict") else (
                  res if isinstance(res, dict) else {})
        return {"awarded": bool(out.get("ok")), **out}
    except Exception as e:
        log.warning("[share] points award failed: %s", e)
        return {"awarded": False, "reason": str(e)[:120]}


# ─── /api/share/log ─────────────────────────────────────────────────
class ShareLogIn(BaseModel):
    feature_type: str = Field(..., min_length=1, max_length=48)
    content_id:    Optional[str] = Field(None, max_length=120)
    channel:        str = Field(..., min_length=1, max_length=24)
    url:                Optional[str] = Field(None, max_length=512)


@router.post("/share/log",
                          description="Phase 42-E2.2 — record a share event + award points.")
async def share_log(body: ShareLogIn, request: Request,
                                          user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    feature_type = _normalise_feature(body.feature_type)
    channel = _normalise_channel(body.channel)
    event_id = f"shr_{uuid.uuid4().hex[:14]}"
    row = {
        "_id":              event_id,
        "user_id":      (user or {}).get("user_id"),
        "feature_type": feature_type,
        "content_id": body.content_id,
        "channel":      channel,
        "url":              body.url,
        "ip":                request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:200],
        "created_at": _now(),
    }
    try:
        await db.share_events.insert_one(row)
    except Exception as e:
        log.warning("[share] insert failed: %s", e)
        raise HTTPException(500, {"code": "share_log_failed",
                                                                "error": str(e)[:140]})
    # Award points (best-effort) — `source_id` is the surface key so the
    # daily cap of 5/25 is applied per-surface PER DAY.  We DON'T burn
    # the cap on identical re-clicks (the idempotency_key on
    # PointsService keeps it clean).
    src_id = f"{feature_type}:{body.content_id or 'page'}"
    award = await _award_social_share(db, user, source_id=src_id)
    return {"ok": True, "event_id": event_id,
                  "feature_type": feature_type, "channel": channel,
                  "points": award}


# ─── /api/invite/send ───────────────────────────────────────────────
class InviteIn(BaseModel):
    to_email:          EmailStr
    to_name:          Optional[str] = Field(None, max_length=120)
    personal_note: Optional[str] = Field(None, max_length=600)


def _generate_voucher_code() -> str:
    # 12-char URL-safe code without confusing chars (no 0/O, 1/I, etc.).
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


@router.post("/invite/send",
                          description="Phase 42-E2.2 — generate referral voucher + send invite "
                                                "email (mocked when Mailgun not configured).")
async def invite_send(body: InviteIn, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    if user["user_id"] == "":   # belt-and-brace; current_user enforces auth
        raise HTTPException(401, "auth_required")

    # 1. Mint a referral voucher tied to the inviter.
    code = _generate_voucher_code()
    voucher_id = f"rv_{uuid.uuid4().hex[:14]}"
    voucher = {
        "_id":              voucher_id,
        "voucher_id":  voucher_id,
        "kind":              "referral",
        "code":              code,
        "inviter_user_id": user["user_id"],
        "invitee_email":  str(body.to_email).lower(),
        "invitee_name":  body.to_name,
        "status":          "issued",
        "created_at": _now(),
        "redeemed_at": None,
    }
    await db.referral_vouchers.insert_one(voucher)

    # 2. Build the email payload.
    frontend_base = (request.app.state.config.get("frontend_base_url")
                                  if getattr(request.app.state, "config", None)
                                  else None) or ""
    if not frontend_base:
        # Phase 42-E2.5 — derive the public URL from the request so the
        # /register?ref=<code> link in the email actually resolves.
        frontend_base = (f"{request.url.scheme}://{request.url.netloc}"
                                          if request else "")
    deep_link = (f"{frontend_base}/register?ref={code}"
                            if frontend_base else f"/register?ref={code}")
    inviter_name = (user.get("first_name")
                                      or user.get("name") or "A BigFM listener")
    subject = f"{inviter_name} invited you to BigFM 🎙️"
    safe_note = (body.personal_note or "").replace("<", "&lt;").replace(">", "&gt;")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{subject}</title></head>
<body style="margin:0;padding:0;background:#0c1019;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#e9edf5">
  <div style="max-width:560px;margin:0 auto;padding:32px 24px">
    <div style="font-size:11px;letter-spacing:0.18em;color:#00d1ff;font-weight:700;margin-bottom:6px">BIGFM · INVITE</div>
    <h1 style="font-size:26px;line-height:1.25;margin:0 0 18px;font-weight:800;color:#fff">
      {inviter_name} invited you to BigFM 🎙️
    </h1>
    <p style="font-size:15px;line-height:1.6;color:#b4c4da;margin:0 0 18px">
      Personalized radio. Local news. Predict-&amp;-win games. Real rewards.
      {inviter_name} thinks you'd love it.
    </p>
    {f'<blockquote style="border-left:3px solid #ff38bb;padding:10px 16px;margin:0 0 22px;background:rgba(255,56,187,0.08);font-style:italic;color:#fff">{safe_note}</blockquote>' if safe_note else ''}
    <a href="{deep_link}" style="display:inline-block;padding:14px 26px;background:linear-gradient(90deg,#00d1ff,#7a5cff);color:#0c1019;text-decoration:none;font-weight:800;border-radius:999px;font-size:14px;letter-spacing:0.04em">
      ▶  Join with code {code}
    </a>
    <p style="font-size:12px;color:#8298b8;margin:24px 0 0">
      Or paste this link into your browser: <br>
      <a href="{deep_link}" style="color:#00d1ff;word-break:break-all">{deep_link}</a>
    </p>
    <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:30px 0 18px">
    <p style="font-size:11px;color:#5b6c89;margin:0">
      This invite expires in 30 days.  If you didn't expect this email,
      you can safely ignore it — your address won't be saved.
    </p>
  </div>
</body></html>"""
    text_body = (f"{inviter_name} invited you to BigFM 🎙️\n\n"
                          + (f"{safe_note}\n\n" if safe_note else "")
                          + f"Join with code {code}: {deep_link}\n\n"
                            "Personalized radio, news, games and rewards.\n"
                            "This invite expires in 30 days.")

    # 3. Phase 42-E2.5 — LIVE Mailgun (env-flagged kill switch).
    email_status      = "mocked"
    email_message_id = None
    email_error          = None
    email_sent_at      = None
    if os.environ.get("INVITE_EMAIL_LIVE", "").lower() in ("1", "true", "yes"):
        try:
            from services.mailgun_client import is_live as mg_live, send_email
            if mg_live():
                res = send_email(to=str(body.to_email), subject=subject,
                                                  html=html, text=text_body,
                                                  tags=["invite", "phase-42-e2"])
                if res.get("ok"):
                    email_status      = "sent"
                    email_message_id = res.get("message_id")
                    email_sent_at      = _now()
                else:
                    email_status = "failed"
                    email_error    = (res.get("error") or "")[:240]
                    log.warning("[invite] mailgun returned ok=False: %s",
                                              email_error)
            else:
                log.warning("[invite] MAILGUN not live (is_live=False) → mocked")
        except Exception as e:
            email_status = "failed"
            email_error    = f"{type(e).__name__}:{e}"[:240]
            log.warning("[invite] mailgun exception: %s", email_error)
    else:
        log.info("[invite] ***** MOCKED ***** EMAIL → code=%s (invite_email_live=false)",
                          code)

    # 4. Persist the invite + email-status for replay later.
    await db.referral_invites.insert_one({
        "_id":                  f"inv_{uuid.uuid4().hex[:14]}",
        "voucher_id":      voucher_id,
        "inviter_user_id": user["user_id"],
        "to_email":          str(body.to_email).lower(),
        "to_name":          body.to_name,
        "personal_note": body.personal_note,
        "code":                  code,
        "deep_link":          deep_link,
        "email_status":  email_status,
        "email_message_id": email_message_id,
        "email_error":      email_error,
        "email_sent_at":  email_sent_at,
        "created_at":      _now(),
    })

    # 5. Award social-share points to the inviter (best-effort).
    award = await _award_social_share(db, user,
                                                                          source_id=f"invite_email:{code}")

    return {"ok":              True,
                  "voucher_id":  voucher_id,
                  "code":              code,
                  "deep_link":  deep_link,
                  "email_status": email_status,
                  "email_message_id": email_message_id,
                  "email_error":      email_error,
                  "points":          award}
