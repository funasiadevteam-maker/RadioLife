"""FUUSIC Phase 13e — Sign in with Apple routes (web + mobile)."""
from __future__ import annotations
import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel, Field

from services import apple_siwa
from services.apple_siwa import SIWANotConfigured
from services.integration_health import record_call

logger = logging.getLogger("bigfm.auth.apple")

auth_apple_router = APIRouter(prefix="/api/auth/apple", tags=["auth-apple"])

STATE_TTL_MIN = 10
SESSION_COOKIE_NAME = "bigfm_session"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _issue_session(db, user: dict) -> Dict[str, Any]:
    """Mint a session_token row using the same shape as the email-login
    path (auth.py.login). We keep the contract narrow: bearer-style token
    + expires_at + user_id. Frontend uses the same /api/auth/me to
    read user info post-login."""
    token = f"sess_{secrets.token_urlsafe(32)}"
    ttl_hours = 24 * 30
    expires_at = _now() + timedelta(hours=ttl_hours)
    await db.sessions.insert_one({
        "user_id": user["user_id"],
        "token": token,
        "created_at": _now(),
        "expires_at": expires_at,
        "ip": "", "user_agent": "siwa",
        "auth_provider": "apple",
    })
    return {"session_token": token,
              "expires_at": expires_at.isoformat(),
              "user_id": user["user_id"]}


# ─── Web flow ───────────────────────────────────────────────────────────
@auth_apple_router.get("/login")
async def apple_login_redirect(request: Request):
    """Kick off the Apple OAuth dance. Returns 302 to Apple."""
    db = request.app.state.db
    try:
        c = apple_siwa.creds()
    except SIWANotConfigured as e:
        await record_call(db, "apple_siwa", success=False,
                                  error=str(e))
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:40px;"
            f"background:#0a0a0f;color:#fff'>"
            f"<h2>Sign in with Apple — not configured</h2>"
            f"<p>This FUUSIC instance hasn't been provisioned with Apple "
            f"credentials yet. Admins: set APPLE_SIWA_SERVICE_ID and "
            f"APPLE_SIWA_REDIRECT_URI in backend/.env.</p>"
            f"<p style='color:#888'>{e}</p>"
            f"<a href='/login' style='color:#7BD3F7'>← back to sign in</a>"
            f"</body></html>", status_code=503)
    state = secrets.token_urlsafe(16)
    await db.apple_oauth_states.insert_one({
        "_id": state, "state": state,
        "created_at": _now(),
        "expires_at": _now() + timedelta(minutes=STATE_TTL_MIN)})
    params = {
        "client_id": c["service_id"],
        "redirect_uri": c["redirect_uri"],
        "response_type": "code id_token",
        "response_mode": "form_post",
        "scope": "name email",
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(
        f"https://appleid.apple.com/auth/authorize?{qs}", status_code=302)


@auth_apple_router.post("/callback")
async def apple_callback(request: Request,
                                    code: Optional[str] = Form(None),
                                    id_token: Optional[str] = Form(None),
                                    state: Optional[str] = Form(None),
                                    user: Optional[str] = Form(None)):
    """Apple form-POSTs back here. user= is a JSON {name:{firstName,lastName},email}
    sent ONLY on the very first authorization."""
    db = request.app.state.db
    try:
        apple_siwa.creds()
    except SIWANotConfigured as e:
        return HTMLResponse(
            f"<h3>Apple sign-in not configured</h3><p>{e}</p>",
            status_code=503)
    if not state:
        raise HTTPException(400, "missing_state")
    state_doc = await db.apple_oauth_states.find_one({"_id": state})
    if not state_doc:
        raise HTTPException(400, "invalid_or_expired_state")
    await db.apple_oauth_states.delete_one({"_id": state})
    if not id_token:
        # Exchange code → id_token if Apple only returned code.
        if not code:
            raise HTTPException(400, "missing_code_and_id_token")
        try:
            exch = await apple_siwa.exchange_code(code)
            id_token = exch.get("id_token")
        except Exception as e:
            await record_call(db, "apple_siwa", success=False,
                                      error=str(e))
            raise HTTPException(502, f"apple_exchange_failed:{e}")
    try:
        claims = await apple_siwa.verify_identity_token(db, id_token)
    except Exception as e:
        await record_call(db, "apple_siwa", success=False, error=str(e))
        raise HTTPException(401, f"identity_token_invalid:{e}")
    # First-authorization profile payload.
    profile_name: Dict[str, str] = {}
    if user:
        try:
            import json
            blob = json.loads(user)
            profile_name = blob.get("name") or {}
        except Exception:
            pass
    user_doc = await apple_siwa.apple_user_from_claims(
        db, claims, profile_name=profile_name)
    sess = await _issue_session(db, user_doc)
    await record_call(db, "apple_siwa", success=True,
                              detail={"flow": "web_callback"})
    # Redirect into the SPA so the React app can pick up the token.
    redir = (f"/auth/apple/return?session_token={sess['session_token']}"
                f"&user_id={sess['user_id']}")
    resp = RedirectResponse(redir, status_code=302)
    resp.set_cookie(SESSION_COOKIE_NAME, sess["session_token"],
                          max_age=60 * 60 * 24 * 30,
                          httponly=True, samesite="lax", path="/")
    return resp


# ─── Mobile (expo-apple-authentication) ──────────────────────────────────
class MobileSIWAIn(BaseModel):
    identity_token: str = Field(..., min_length=10)
    nonce: Optional[str] = None
    profile_name: Optional[Dict[str, str]] = None   # firstName/lastName


@auth_apple_router.post("/mobile")
async def apple_mobile_signin(body: MobileSIWAIn, request: Request):
    """Mobile path: client got identity_token from
    expo-apple-authentication. Verify + link/create + return session
    JSON (mobile reads body, not Set-Cookie)."""
    db = request.app.state.db
    try:
        apple_siwa.creds()
    except SIWANotConfigured as e:
        raise HTTPException(503, f"apple_siwa_not_configured:{e}")
    try:
        claims = await apple_siwa.verify_identity_token(
            db, body.identity_token)
    except Exception as e:
        await record_call(db, "apple_siwa", success=False, error=str(e))
        raise HTTPException(401, f"identity_token_invalid:{e}")
    user_doc = await apple_siwa.apple_user_from_claims(
        db, claims, profile_name=body.profile_name)
    sess = await _issue_session(db, user_doc)
    await record_call(db, "apple_siwa", success=True,
                              detail={"flow": "mobile"})
    return {
        "session_token": sess["session_token"],
        "expires_at": sess["expires_at"],
        "user_id": sess["user_id"],
        "is_new_user": (user_doc.get("auth_provider") == "apple"
                                and not user_doc.get("onboarded")),
    }
