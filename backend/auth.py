"""FUUSIC Phase 1 — Auth + Sessions module.

Cookie-based sessions shared between Google OAuth (via Emergent Auth) and
email/password registration. Exposes:

- POST /api/auth/register         — email+password signup
- POST /api/auth/login            — email+password login
- POST /api/auth/logout           — clear session
- GET  /api/auth/me               — current user (401 if unauth'd)
- POST /api/auth/google/session   — exchange Emergent session_id for our cookie
- GET  /api/users/me              — alias of /api/auth/me
- GET  /api/users/preferences     — get my preference vector
- POST /api/users/preferences     — save/update my preference vector (also marks onboarded)
- POST /api/users/onboarding/reset — set onboarding_complete=False (redo wizard)

Dependencies:
- current_user(request) — resolves user via cookie, raises 401 if missing.
- current_user_optional(request) — same but returns None.
- require_admin(user)   — allow only role=admin users; 403 otherwise.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger("bigfm.auth")
log = logger    # alias so the new password-reset code can `log.warning(...)`

SESSION_COOKIE = "bigfm_session"
SESSION_TTL = timedelta(days=7)
EMERGENT_SESSION_DATA_URL = (
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
)

# ─── Own Google OAuth 2.0 (developer's own Client ID/Secret) ──────
# Replaces the Emergent-managed Google Sign-In so the Google consent
# screen shows the app's own name/branding. Server-side auth-code flow:
#   GET /api/auth/google/login    → 302 to Google's consent screen
#   GET /api/auth/google/callback → exchange code, issue our session
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT
# URLS, THIS BREAKS THE AUTH — the redirect_uri is derived at runtime
# from the request host so it always matches the serving origin.
# NOTE: read creds lazily (server.py imports this module BEFORE load_dotenv
# runs, so a module-level os.environ.get would come back empty).
def _google_creds() -> tuple[str, str]:
    return (os.environ.get("GOOGLE_CLIENT_ID", ""),
                  os.environ.get("GOOGLE_CLIENT_SECRET", ""))
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


# ---------- pydantic ----------
class PreferenceVector(BaseModel):
    languages: List[str] = []
    genres: List[str] = []
    eras: List[str] = []
    moods: List[str] = []
    activities: List[str] = []
    favorite_artists: List[str] = []
    city: str = "Dubai"
    home_area: Optional[str] = None
    host_personality: str = "auto"  # voice_key from registry, or "auto"
    explicit_ok: bool = False
    # Phase 3.7 — Multi-market support
    market: str = "dubai"           # "dubai" | "dfw"


class UserOut(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    auth_provider: str
    role: str = "user"
    onboarding_complete: bool = False
    preference_vector: PreferenceVector = Field(default_factory=PreferenceVector)
    created_at: datetime
    last_login_at: Optional[datetime] = None
    # Phase 3 — premium tier surface for the frontend
    is_premium: bool = False
    premium_tier: Optional[str] = None
    reward_multiplier: float = 1.0
    subscription_status: Optional[str] = None
    subscription_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    # Phase 3.7 — Multi-market support (FUUSIC default, FUUSIC DFW opt-in)
    market: str = "dubai"
    # Phase 8a — Advertiser surface
    is_advertiser: bool = False
    # Phase Π.5 — Employee testing surface (drives FeedbackWidget visibility).
    is_employee: bool = False
    is_admin: bool = False
    # Phase 11 (mobile) — opaque session token returned for non-browser
    # clients.  Mobile stores in expo-secure-store and sends as
    # `Authorization: Bearer <token>` on subsequent `/api/*` calls.  Web
    # ignores this and continues to use the `bigfm_session` cookie.
    session_token: Optional[str] = None
    session_expires_at: Optional[datetime] = None


class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionReq(BaseModel):
    session_id: str


# 2026-07-31 — password-reset flow (Phase AUTH.PWR).
class ForgotPasswordReq(BaseModel):
    email: EmailStr


class ResetPasswordReq(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------- crypto ----------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- helpers ----------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_session_token() -> str:
    return f"bsess_{uuid.uuid4().hex}{uuid.uuid4().hex}"


def _set_session_cookie(response: Response, token: str) -> None:
    max_age = int(SESSION_TTL.total_seconds())
    # Primary Emergent-style cookie name (Phase 42-C + earlier).
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=max_age,
        path="/",
    )
    # Phase AUTH.1 — also set the playbook-canonical name `session_token`
    # so Playwright / QA scripts that follow the Emergent testing playbook
    # can inject a cookie without knowing our historical cookie name.
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=max_age,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    # Match attributes on delete to ensure the browser removes it.
    for key in (SESSION_COOKIE, "session_token"):
        response.delete_cookie(
            key=key,
            path="/",
            secure=True,
            samesite="none",
        )


def _kick_warm_start(request: Request, user: dict) -> None:
    """Fire-and-forget: schedule a background warm-start segment prebuild on
    login / register / google_session / onboarding completion. Silent on
    failure — radio_start cold path remains the safety net."""
    fn = getattr(request.app.state, "schedule_prebuild_warm_start", None)
    if not fn:
        logger.warning(f"[prewarm-kick] no scheduler on app.state for user={user.get('user_id')}")
        return
    try:
        fn(user)
        logger.info(f"[prewarm-kick] scheduled for user={user.get('user_id')}")
    except Exception as e:
        logger.warning(f"[prewarm-kick] failed user={user.get('user_id')}: {e}")


def _serialize_user(doc: dict) -> UserOut:
    created_at = doc.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if created_at is None:
        created_at = _now()
    last_login = doc.get("last_login_at")
    if isinstance(last_login, str):
        last_login = datetime.fromisoformat(last_login)
    pv = doc.get("preference_vector") or {}
    sub = doc.get("subscription") or {}
    sub_end = sub.get("current_period_end")
    if isinstance(sub_end, str):
        try: sub_end = datetime.fromisoformat(sub_end)
        except Exception: sub_end = None
    return UserOut(
        user_id=doc["user_id"],
        email=doc["email"],
        name=doc.get("name") or doc["email"],
        picture=doc.get("picture"),
        auth_provider=doc.get("auth_provider", "email"),
        role=doc.get("role", "user"),
        onboarding_complete=bool(doc.get("onboarding_complete", False)),
        preference_vector=PreferenceVector(**pv),
        created_at=created_at,
        last_login_at=last_login,
        is_premium=bool(doc.get("is_premium", False)),
        premium_tier=doc.get("premium_tier"),
        is_advertiser=bool(doc.get("is_advertiser", False)) or doc.get("role") == "advertiser",
        # Phase Π.5 — drives FeedbackWidget visibility in the frontend.
        is_employee=bool(doc.get("is_employee", False)),
        is_admin=(doc.get("role") == "admin"
                                or bool(doc.get("is_admin", False))
                                or "admin" in (doc.get("roles") or [])),
        reward_multiplier=float(doc.get("reward_multiplier", 1.0)),
        subscription_status=sub.get("status"),
        subscription_period_end=sub_end,
        cancel_at_period_end=bool(sub.get("cancel_at_period_end", False)),
        market=str(doc.get("market") or "dubai"),
    )


# ---------- index setup ----------
async def ensure_auth_indexes(db) -> None:
    """Create unique/TTL indexes idempotently."""
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.sessions.create_index("token", unique=True)
    # MongoDB auto-expires documents when their expires_at < now (TTL on field).
    try:
        await db.sessions.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        # If an incompatible index already exists (different TTL), leave it.
        pass
    # Phase AUTH.1 — canonical `user_sessions` collection indexes.
    try:
        await db.user_sessions.create_index("session_token", unique=True,
                                                                                                          name="user_sessions_token_unique")
    except Exception:
        pass
    try:
        await db.user_sessions.create_index("user_id",
                                                                                                          name="user_sessions_user_id")
    except Exception:
        pass
    try:
        await db.user_sessions.create_index(
            "expires_at", expireAfterSeconds=0,
            name="user_sessions_ttl")
    except Exception:
        pass
    # Own Google OAuth — short-lived state store (CSRF + redirect_uri pin).
    try:
        await db.oauth_states.create_index("state", unique=True,
                                                                                name="oauth_states_state_unique")
    except Exception:
        pass
    try:
        await db.oauth_states.create_index(
            "expires_at", expireAfterSeconds=0, name="oauth_states_ttl")
    except Exception:
        pass


# ---------- session resolution ----------
async def _resolve_user_from_request(request: Request) -> Optional[dict]:
    # Phase AUTH.1 — accept EITHER cookie name (historical `bigfm_session`
    # OR playbook-canonical `session_token`) so tests + external tooling
    # that only knows the playbook name still authenticate.
    token = (request.cookies.get(SESSION_COOKIE)
                        or request.cookies.get("session_token"))
    if not token:
        # Bearer fallback (useful for curl / automation)
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr.split(" ", 1)[1].strip()
    if not token:
        return None
    db = request.app.state.db
    # Primary collection (historical hot path).  Fall through to the
    # Phase AUTH.1 `user_sessions` collection when a session was created
    # via the playbook path or seeded directly by the test playbook.
    sess = await db.sessions.find_one({"token": token}, {"_id": 0})
    if not sess:
        sess = await db.user_sessions.find_one(
            {"session_token": token}, {"_id": 0})
        if sess:
            # Normalize field name so downstream code stays uniform.
            sess.setdefault("token", sess.get("session_token"))
    if not sess:
        return None
    exp = sess.get("expires_at")
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < _now():
        await db.sessions.delete_one({"token": token})
        await db.user_sessions.delete_one({"session_token": token})
        return None
    # Track last_used_at for the playbook collection (best-effort).
    try:
        await db.user_sessions.update_one(
            {"session_token": token},
            {"$set": {"last_used_at": _now()}})
    except Exception:
        pass
    return await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})


async def current_user(request: Request) -> dict:
    user = await _resolve_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Phase 12c — account suspension check
    susp = user.get("suspended_until")
    if susp:
        if isinstance(susp, str):
            try:
                susp = datetime.fromisoformat(susp.replace("Z", "+00:00"))
            except Exception:
                susp = None
        if susp and susp.tzinfo is None:
            susp = susp.replace(tzinfo=timezone.utc)
        if susp and susp > _now():
            raise HTTPException(
                status_code=403,
                detail={"code": "account_suspended",
                          "until": susp.isoformat(),
                          "reason": user.get("suspended_reason")
                                        or "policy_violation"})
    return user


async def current_user_optional(request: Request) -> Optional[dict]:
    return await _resolve_user_from_request(request)


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ---------- session creation ----------
async def _create_session(db, user_id: str, request: Optional[Request]) -> tuple[str, datetime]:
    """Insert a fresh row in `sessions` and return (token, expires_at).
    Tuple return — `expires_at` is surfaced in login responses so mobile
    clients can pre-empt expiry without a second roundtrip.
    """
    token = _new_session_token()
    expires_at = _now() + SESSION_TTL
    ip = ""
    ua = ""
    if request is not None:
        ip = request.client.host if request.client else ""
        ua = (request.headers.get("user-agent") or "")[:300]
    await db.sessions.insert_one({
        "user_id": user_id,
        "token": token,
        "created_at": _now(),
        "expires_at": expires_at,
        "ip": ip,
        "user_agent": ua,
    })
    # Phase AUTH.1 — mirror to `user_sessions` so tooling / test playbooks
    # that follow the Emergent testing doc verbatim can seed + read the
    # session through the canonical collection name.  Idempotent — unique
    # index on `session_token` catches double-inserts.
    try:
        await db.user_sessions.insert_one({
            "user_id":            user_id,
            "session_token":  token,
            "created_at":      _now(),
            "expires_at":      expires_at,
            "last_used_at":  _now(),
            "provider":          "email_password",   # overridden by callers when known
            "ip":                      ip,
            "user_agent":      ua,
        })
    except Exception:
        pass
    return token, expires_at


def _attach_session_to_response(out, token: str, expires_at: datetime):
    """Stamp session_token + session_expires_at on a serialized UserOut."""
    if isinstance(out, UserOut):
        out.session_token = token
        out.session_expires_at = expires_at
    return out


# ---------- routers ----------
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])


@auth_router.post("/register", response_model=UserOut)
async def register(req: RegisterReq, request: Request, response: Response):
    db = request.app.state.db
    if not re.search(r"\d", req.password) or not re.search(r"[A-Za-z]", req.password):
        raise HTTPException(400, "Password must contain at least one letter and one digit")
    email = req.email.lower().strip()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(409, "Email already registered")
    user_id = f"user_{uuid.uuid4().hex[:16]}"
    now = _now()
    doc = {
        "user_id": user_id,
        "email": email,
        "name": req.name.strip(),
        "picture": None,
        "auth_provider": "email",
        "password_hash": hash_password(req.password),
        "role": "user",
        "onboarding_complete": False,
        "preference_vector": PreferenceVector().model_dump(),
        "created_at": now,
        "last_login_at": now,
    }
    await db.users.insert_one(doc)
    # Phase 10a — Social Passport: claim any pending referral attribution
    # cookie now so the funnel ticks `signed_up`.  Failure is non-fatal.
    try:
        from services.referrals_v2 import claim_attribution, fingerprint
        ck = request.cookies.get("bigfm_ref") or ""
        rc = ck.split("|", 1)[0] if "|" in ck else (ck or None)
        ua = request.headers.get("user-agent", "")
        ip = request.client.host if request.client else ""
        await claim_attribution(
            db, ref_code=rc, user_id=user_id,
            device_fingerprint=fingerprint(ua, ip))
    except Exception:
        pass
    token, expires_at = await _create_session(db, user_id, request)
    _set_session_cookie(response, token)
    _kick_warm_start(request, doc)
    return _attach_session_to_response(_serialize_user(doc), token, expires_at)


@auth_router.post("/login", response_model=UserOut)
async def login(req: LoginReq, request: Request, response: Response):
    db = request.app.state.db
    email = req.email.lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(401, "Invalid credentials")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    # Phase 19a Part 5 — block inactive / suspended accounts at login
    status = user.get("status") or "active"
    if status != "active":
        raise HTTPException(403,
            {"status": f"account_{status}",
              "message": f"Account is {status}. Contact support."})
    token, expires_at = await _create_session(db, user["user_id"], request)
    _set_session_cookie(response, token)
    now = _now()
    # Phase A Item 3 — first_login trigger dispatch.  Snapshot the
    # pre-login timestamp so we only fire on the FIRST successful login.
    _was_first_login = user.get("last_login_at") is None
    await db.users.update_one(
        {"user_id": user["user_id"]}, {"$set": {"last_login_at": now}},
    )
    user["last_login_at"] = now
    if _was_first_login:
        try:
            import asyncio as _aio
            from services.notification_trigger_dispatcher import dispatch_event
            _aio.create_task(dispatch_event(
                db, event_name="first_login",
                user_id=user["user_id"],
                payload={"provider": "email"}))
        except Exception:
            pass
    _kick_warm_start(request, user)
    return _attach_session_to_response(_serialize_user(user), token, expires_at)


@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    db = request.app.state.db
    # Phase 11 (mobile) — logout must also revoke a Bearer-supplied
    # token, not just the cookie one.  Both paths delete the row from
    # `sessions` so the gate fails on the next call.
    token = (request.cookies.get(SESSION_COOKIE)
                        or request.cookies.get("session_token"))
    if not token:
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr.split(" ", 1)[1].strip()
    if token:
        await db.sessions.delete_one({"token": token})
        await db.user_sessions.delete_one({"session_token": token})
    _clear_session_cookie(response)
    return {"ok": True}


# ─── Password-reset flow (Phase AUTH.PWR, 2026-07-31) ────────────
# `POST /api/auth/forgot-password` — anti-enumeration: ALWAYS returns
#     the same generic success message whether the email exists or not.
# `POST /api/auth/reset-password` — consumes a token from the
#     `password_reset_tokens` collection.  Tokens are single-use, expire
#     after 1 h (TTL index), and are stored plain (they're already 43
#     bytes of urandom, and are compared exact-match server-side).
#
# Email delivery: the current send_email() surface hasn't been wired to
# a real provider (SendGrid/Resend) yet.  Until it is, the reset URL is
# LOGGED to the server console at INFO level so ops can hand it to the
# user or an integration harness can scrape it.  This is deliberately
# NOT hidden — mocked delivery must be visible.
_FRONTEND_URL_ENV = "FRONTEND_URL"


def _frontend_base_url(request: Optional[Request] = None) -> str:
    """Best-effort base URL for building the reset link.

    Priority:
        1. `FRONTEND_URL` env (canonical override for prod).
        2. `REACT_APP_BACKEND_URL` env stripped of trailing `/`.
        3. Request `Origin` header (browser-issued XHR).
        4. Request `Referer` header (form POST fallback).
        5. Request scheme + host (final backstop).
    """
    val = os.environ.get(_FRONTEND_URL_ENV) or ""
    if val:
        return val.rstrip("/")
    val = os.environ.get("REACT_APP_BACKEND_URL") or ""
    if val:
        return val.rstrip("/")
    if request is not None:
        origin = request.headers.get("origin") or ""
        if origin:
            return origin.rstrip("/")
        referer = request.headers.get("referer") or ""
        if referer:
            # Strip the path portion — keep scheme + host + optional port.
            from urllib.parse import urlparse
            u = urlparse(referer)
            if u.scheme and u.netloc:
                return f"{u.scheme}://{u.netloc}"
        # Backstop: reconstruct from the request itself.
        scheme = request.url.scheme
        host = request.headers.get("host") or request.url.netloc
        if scheme and host:
            return f"{scheme}://{host}"
    return ""


def _password_ok(pw: str) -> bool:
    """Same rules as the register path: 8+ chars, ≥ 1 letter, ≥ 1 digit."""
    if not pw or len(pw) < 8:
        return False
    has_letter = any(c.isalpha() for c in pw)
    has_digit  = any(c.isdigit() for c in pw)
    return has_letter and has_digit


async def _ensure_reset_indexes(db) -> None:
    """Idempotent: unique token + TTL on expires_at."""
    try:
        await db.password_reset_tokens.create_index(
            "token", unique=True, name="uniq_token")
    except Exception:
        pass
    try:
        await db.password_reset_tokens.create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_expires_at")
    except Exception:
        pass


@auth_router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordReq, request: Request):
    db = request.app.state.db
    await _ensure_reset_indexes(db)
    email = req.email.lower().strip()
    user = await db.users.find_one({"email": email},
                                                                      {"user_id": 1, "email": 1})
    generic = {"ok": True,
                          "message": "If that email exists, we've sent a reset link."}
    if not user:
        return generic

    token = secrets.token_urlsafe(32)     # 43-char urlsafe base64
    now = _now()
    doc = {
        "token":         token,
        "user_id":     user["user_id"],
        "email":         email,
        "created_at": now,
        "expires_at": now + timedelta(hours=1),
        "used":            False,
    }
    await db.password_reset_tokens.insert_one(doc)

    reset_url = f"{_frontend_base_url(request)}/reset-password?token={token}"
    # Email delivery: prefer the pre-wired Mailgun surface
    # (`services.mailgun_client.send_email`) when it's live.  If Mailgun
    # isn't configured (`is_live()` returns False) OR the send fails,
    # fall back to visible-log delivery so ops can hand the URL out
    # manually.  This is deliberately NOT hidden — mocked delivery must
    # be surfaced.
    #
    # TODO: once the DNS on `mg.bigfantv.com` is fully verified in
    # prod, remove the log-fallback branch and treat any send failure
    # as a 500.  Until then, the log is the source of truth.
    send_ok = False
    send_error = None
    try:
        from services.mailgun_client import send_email, is_live as _mg_live
        if _mg_live():
            subject = "Reset your FUUSIC password"
            html = (
                f'<div style="font-family:system-ui,sans-serif;'
                f'line-height:1.5;color:#0f172a">'
                f'<h2 style="color:#0f172a;margin:0 0 8px">'
                f'Reset your FUUSIC password</h2>'
                f'<p>You requested a password reset.  Click the button below '
                f'to choose a new one.  This link expires in <b>1 hour</b> '
                f'and can be used only once.</p>'
                f'<p><a href="{reset_url}" style="display:inline-block;'
                f'background:#d946ef;color:#ffffff;padding:12px 22px;'
                f'border-radius:9999px;text-decoration:none;font-weight:700">'
                f'Set new password</a></p>'
                f'<p style="color:#64748b;font-size:12px;margin-top:16px">'
                f'Or paste this URL into your browser:<br>'
                f'<span style="word-break:break-all">{reset_url}</span></p>'
                f'<p style="color:#94a3b8;font-size:11px;margin-top:12px">'
                f'If you didn\'t request this, you can safely ignore this '
                f'email — your password won\'t be changed.</p></div>'
            )
            text = (
                f"Reset your FUUSIC password:\n{reset_url}\n\n"
                f"This link expires in 1 hour and can be used once.\n"
                f"If you didn't request this, ignore this email."
            )
            resp = send_email(email, subject, html, text=text,
                                                          tags=["password_reset"])
            send_ok = bool(resp.get("ok"))
            send_error = resp.get("error")
    except Exception as _e:
        send_error = f"exception:{type(_e).__name__}:{_e}"
    if not send_ok:
        log.warning(
            "[AUTH.PWR] MOCKED password-reset email (mailgun_ok=%s err=%s) "
            "— deliver this URL to %s manually: %s",
            send_ok, send_error, email, reset_url)
    else:
        log.info("[AUTH.PWR] password-reset email dispatched via mailgun "
                          "to=%s...", email[:3])
    # Also stash the reset_url on the token doc so an admin ops view
    # can surface it in-app if the log stream is unreachable.
    await db.password_reset_tokens.update_one(
        {"token": token}, {"$set": {"reset_url_debug": reset_url,
                                                                  "email_sent": send_ok,
                                                                  "email_error": send_error}})
    return generic


@auth_router.post("/reset-password")
async def reset_password(req: ResetPasswordReq, request: Request):
    db = request.app.state.db
    await _ensure_reset_indexes(db)
    tok = await db.password_reset_tokens.find_one(
        {"token": req.token, "used": False})
    if not tok:
        raise HTTPException(400, "invalid or expired token")
    # Mongo returns naive datetimes; coerce to UTC for a valid compare
    # with `_now()` which is always tz-aware.
    exp = tok.get("expires_at")
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < _now():
        raise HTTPException(400, "invalid or expired token")
    if not _password_ok(req.new_password):
        raise HTTPException(
            400,
            "Password must be at least 8 characters and contain a "
            "letter and a digit.")

    new_hash = hash_password(req.new_password)
    await db.users.update_one(
        {"user_id": tok["user_id"]},
        {"$set": {"password_hash": new_hash, "password_updated_at": _now()}})
    await db.password_reset_tokens.update_one(
        {"token": req.token},
        {"$set": {"used": True, "used_at": _now()}})
    # Invalidate every existing session for safety.
    try:
        await db.sessions.delete_many({"user_id": tok["user_id"]})
        await db.user_sessions.delete_many({"user_id": tok["user_id"]})
    except Exception:
        pass
    return {"ok": True, "message": "Password updated. You can log in now."}


@auth_router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)):
    return _serialize_user(user)


def _base_from_request(request: Request) -> str:
    """Serving origin as the browser sees it (scheme+host), from the
    proxy's forwarded headers — the server-side equivalent of
    window.location.origin. Never hardcoded."""
    proto = (request.headers.get("x-forwarded-proto")
                      or request.url.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host")
                    or request.headers.get("host")
                    or request.url.netloc).split(",")[0].strip()
    return f"{proto}://{host}"


async def _upsert_google_user(db, request: Request, *, email: str,
                                                            name: Optional[str],
                                                            picture: Optional[str]) -> dict:
    """Create or update a user from a verified Google identity, growing the
    `auth_providers` set and firing the first_login trigger. Shared by the
    Emergent-session path and our own OAuth callback."""
    email = (email or "").lower().strip()
    now = _now()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    google_fields = {
        "google_email":         email,
        "google_name":            name,
        "google_picture":     picture,
        "google_linked_at": now,
    }
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:16]}"
        doc = {
            "user_id": user_id, "email": email,
            "name": name or email.split("@")[0],
            "picture": picture,
            "auth_provider": "google", "auth_providers": ["google"],
            **google_fields, "role": "user",
            "onboarding_complete": False,
            "preference_vector": PreferenceVector().model_dump(),
            "created_at": now, "last_login_at": now,
        }
        await db.users.insert_one(doc)
        user = doc
        try:
            import asyncio as _aio
            from services.notification_trigger_dispatcher import dispatch_event
            _aio.create_task(dispatch_event(
                db, event_name="first_login", user_id=user_id,
                payload={"provider": "google"}))
        except Exception:
            pass
    else:
        _was_first_login = user.get("last_login_at") is None
        update: Dict[str, Any] = {"last_login_at": now, **google_fields}
        if name:      update["name"] = name
        if picture: update["picture"] = picture
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": update, "$addToSet": {"auth_providers": "google"}})
        user.update(update)
        user["auth_providers"] = list(
            set((user.get("auth_providers") or []) + ["google"]))
        if _was_first_login:
            try:
                import asyncio as _aio
                from services.notification_trigger_dispatcher import dispatch_event
                _aio.create_task(dispatch_event(
                    db, event_name="first_login", user_id=user["user_id"],
                    payload={"provider": "google"}))
            except Exception:
                pass
    return user


@auth_router.post("/google/session", response_model=UserOut)
@auth_router.post("/google/exchange", response_model=UserOut)
async def google_session(req: GoogleSessionReq, request: Request, response: Response):
    if not req.session_id:
        raise HTTPException(400, "session_id required")
    headers = {"X-Session-ID": req.session_id}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(EMERGENT_SESSION_DATA_URL, headers=headers)
    except Exception as e:
        raise HTTPException(502, f"Emergent auth network error: {e}")
    if r.status_code != 200:
        raise HTTPException(401, f"Emergent session-data {r.status_code}: {r.text[:200]}")
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    email = (data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(401, "Emergent did not return an email")
    db = request.app.state.db
    user = await db.users.find_one({"email": email}, {"_id": 0})
    now = _now()
    # Phase AUTH.1 — snapshot the Google-provided identity fields for
    # audit + UI use.  `auth_providers` is a *set-like* array; we use
    # $addToSet on the update path to keep it idempotent.
    google_fields = {
        "google_email":         email,
        "google_name":            data.get("name"),
        "google_picture":     data.get("picture"),
        "google_linked_at": now,
    }
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:16]}"
        doc = {
            "user_id": user_id,
            "email": email,
            "name": data.get("name") or email.split("@")[0],
            "picture": data.get("picture"),
            "auth_provider": "google",
            "auth_providers": ["google"],
            **google_fields,
            "role": "user",
            "onboarding_complete": False,
            "preference_vector": PreferenceVector().model_dump(),
            "created_at": now,
            "last_login_at": now,
        }
        await db.users.insert_one(doc)
        user = doc
        # Phase A Item 3 — first_login trigger (Google-side, newly created).
        try:
            import asyncio as _aio
            from services.notification_trigger_dispatcher import dispatch_event
            _aio.create_task(dispatch_event(
                db, event_name="first_login",
                user_id=user_id,
                payload={"provider": "google"}))
        except Exception:
            pass
    else:
        _was_first_login = user.get("last_login_at") is None
        update: Dict[str, Any] = {"last_login_at": now, **google_fields}
        if data.get("name"):
            update["name"] = data["name"]
        if data.get("picture"):
            update["picture"] = data["picture"]
        # Preserve original auth_provider string; grow the array set.
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": update,
              "$addToSet": {"auth_providers": "google"}})
        # Audit — log when Google is linked to an existing non-google row.
        if (user.get("auth_provider") and user.get("auth_provider") != "google"
                and "google" not in (user.get("auth_providers") or [])):
            try:
                await db.auth_audit_log.insert_one({
                    "user_id":      user["user_id"],
                    "event":          "google_linked_to_existing_email",
                    "email":          email,
                    "existing_auth_provider": user.get("auth_provider"),
                    "at":                  now,
                })
            except Exception:
                pass
        user.update(update)
        user["auth_providers"] = list(
            set((user.get("auth_providers") or []) + ["google"]))
        # Phase A Item 3 — first_login trigger (Google-side, existing row
        # with no prior login — e.g. seeded via admin script).
        if _was_first_login:
            try:
                import asyncio as _aio
                from services.notification_trigger_dispatcher import dispatch_event
                _aio.create_task(dispatch_event(
                    db, event_name="first_login",
                    user_id=user["user_id"],
                    payload={"provider": "google"}))
            except Exception:
                pass
    token, expires_at = await _create_session(db, user["user_id"], request)
    # Tag the just-inserted session row with the google provider so the
    # analytics + audit trail can attribute logins.
    try:
        await db.user_sessions.update_one(
            {"session_token": token},
            {"$set": {"provider": "google"}})
    except Exception:
        pass
    _set_session_cookie(response, token)
    _kick_warm_start(request, user)
    return _attach_session_to_response(_serialize_user(user), token, expires_at)


# ─── Own Google OAuth 2.0 — server-side auth-code flow ────────────
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT
# URLS, THIS BREAKS THE AUTH.
@auth_router.get("/google/login")
async def google_login(request: Request, return_to: str = "/",
                                              platform: str = "web",
                                              app_redirect: Optional[str] = None):
    """Kick off Google sign-in with OUR own OAuth client. 302s the browser
    to Google's consent screen (which now shows the app's own name)."""
    client_id, client_secret = _google_creds()
    if not client_id or not client_secret:
        raise HTTPException(500, "Google OAuth is not configured")
    from urllib.parse import urlencode
    db = request.app.state.db
    redirect_uri = f"{_base_from_request(request)}/api/auth/google/callback"
    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "state": state, "return_to": return_to or "/",
        "platform": platform or "web", "app_redirect": app_redirect,
        "redirect_uri": redirect_uri,
        "created_at": _now(), "expires_at": _now() + timedelta(minutes=10)})
    params = {
        "client_id":                    client_id,
        "redirect_uri":              redirect_uri,
        "response_type":            "code",
        "scope":                          "openid email profile",
        "state":                          state,
        "access_type":              "online",
        "prompt":                        "select_account",
        "include_granted_scopes": "true",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}",
                                                    status_code=302)


@auth_router.get("/google/callback")
async def google_callback(request: Request, code: Optional[str] = None,
                                                    state: Optional[str] = None,
                                                    error: Optional[str] = None):
    """Google redirects here with ?code&state. Exchange the code for the
    user's identity, upsert the user, and issue OUR session — then bounce
    into the app (cookie on web, deep-link token on mobile)."""
    db = request.app.state.db
    base = _base_from_request(request)
    st = await db.oauth_states.find_one({"state": state}) if state else None
    if st:
        await db.oauth_states.delete_one({"state": state})

    def _fail(reason: str):
        return RedirectResponse(f"{base}/login?authError={reason}",
                                                        status_code=302)

    if error or not code or not st:
        return _fail("google")
    redirect_uri = st.get("redirect_uri") or f"{base}/api/auth/google/callback"
    client_id, client_secret = _google_creds()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code, "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"})
            if tok.status_code != 200:
                logger.warning("[google-oauth] token exchange %s: %s",
                                              tok.status_code, tok.text[:200])
                return _fail("google")
            access_token = (tok.json() or {}).get("access_token")
            if not access_token:
                return _fail("google")
            ui = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"})
            if ui.status_code != 200:
                return _fail("google")
    except Exception as e:
        logger.warning("[google-oauth] network error: %s", e)
        return _fail("google")

    data = ui.json() or {}
    email = (data.get("email") or "").lower().strip()
    if not email:
        return _fail("google")
    user = await _upsert_google_user(
        db, request, email=email, name=data.get("name"),
        picture=data.get("picture"))
    token, expires_at = await _create_session(db, user["user_id"], request)
    try:
        await db.user_sessions.update_one(
            {"session_token": token}, {"$set": {"provider": "google"}})
    except Exception:
        pass
    _kick_warm_start(request, user)

    # Mobile — hand the opaque session token to the app via its deep link.
    if (st.get("platform") == "mobile") and st.get("app_redirect"):
        sep = "&" if "?" in st["app_redirect"] else "?"
        return RedirectResponse(f'{st["app_redirect"]}{sep}token={token}',
                                                        status_code=302)
    # Web — set the HttpOnly session cookie and bounce into the app.
    return_to = st.get("return_to") or "/"
    if not user.get("onboarding_complete"):
        return_to = "/onboarding"
    redir = RedirectResponse(f"{base}{return_to}", status_code=302)
    _set_session_cookie(redir, token)
    return redir


# ---------- Phase 14 prep — one-click demo login ------------------------
# Idempotent: same `demo@bigfm.dubai` row is reused on every call. We keep
# a tiny in-process token bucket keyed by client IP (30 req / 60s / IP).
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_NAME  = "Demo Listener"
_DEMO_LOGIN_BUCKET: Dict[str, List[float]] = {}
_DEMO_LOGIN_PER_MIN = 30


def _demo_rate_check(ip: str) -> bool:
    """Returns True if the IP is under quota. Cleans entries older than 60s
    on each call so memory stays bounded."""
    import time as _t
    now = _t.time()
    bucket = _DEMO_LOGIN_BUCKET.setdefault(ip or "_unknown", [])
    # Drop entries older than 60s.
    while bucket and (now - bucket[0]) > 60.0:
        bucket.pop(0)
    if len(bucket) >= _DEMO_LOGIN_PER_MIN:
        return False
    bucket.append(now)
    return True


async def _ensure_demo_user(db) -> dict:
    """Idempotent upsert. The password hash is randomized at creation so
    nobody can log in via the email/password route with this account."""
    user = await db.users.find_one({"email": DEMO_EMAIL}, {"_id": 0})
    if user:
        return user
    user_id = f"user_demo_{uuid.uuid4().hex[:10]}"
    now = _now()
    doc = {
        "user_id": user_id,
        "email": DEMO_EMAIL,
        "name": DEMO_NAME,
        "picture": None,
        "auth_provider": "demo",
        # Random unrecoverable hash — demo account can only be entered
        # via /api/auth/demo, never via /login.
        "password_hash": hash_password(secrets.token_urlsafe(48)),
        "role": "user",
        "onboarding_complete": True,
        "preference_vector": PreferenceVector(
            languages=["english", "hindi"],
            genres=["bollywood", "pop", "hip-hop"],
            eras=["2010s", "2020s"],
            moods=["energetic", "happy"],
            activities=["commute", "workout"],
            favorite_artists=[],
            city="Dubai",
            host_personality="auto",
            explicit_ok=False,
            market="dubai",
        ).model_dump(),
        "is_demo": True,
        "market": "dubai",            # Phase 18b: top-level market (resolved by geo.py)
        "created_at": now,
        "last_login_at": now,
    }
    await db.users.insert_one(doc)
    return doc


@auth_router.post("/demo", response_model=UserOut)
async def demo_login(request: Request, response: Response):
    """One-click demo login. Open endpoint, rate-limited 30/min/IP."""
    ip = request.client.host if request.client else "_unknown"
    if not _demo_rate_check(ip):
        raise HTTPException(429, "Demo login rate limit (30/min). "
                                              "Please try again in a moment.")
    db = request.app.state.db
    user = await _ensure_demo_user(db)
    # The demo should reflect the listener's *actual* city/market resolved
    # from geo/IP, not a hardcoded Dubai.  Fall back to the home market only
    # when geo yields nothing useful.
    resolved_city = None
    resolved_market = None
    try:
        from services import geo as _geo
        r = await _geo.resolve_for_user(request, user, db)
        rc = (r.get("city") or "").strip()
        rm = (r.get("market") or "").strip().lower()
        if rc and rc.lower() not in ("global", "unknown"):
            resolved_city = rc
        if rm and rm not in ("global", "unknown"):
            resolved_market = rm
    except Exception:
        pass
    set_fields: dict = {"last_login_at": _now(), "name": DEMO_NAME}
    if resolved_city or resolved_market:
        if resolved_city:
            set_fields["city"] = resolved_city
            set_fields["preference_vector.city"] = resolved_city
        if resolved_market:
            set_fields["market"] = resolved_market
            set_fields["last_resolved_market"] = resolved_market
            set_fields["preference_vector.market"] = resolved_market
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": set_fields, "$unset": {"preferred_market": ""}})
    else:
        # No geo signal — clear stale overrides so the demo lands on its
        # home market via the standard resolver.
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": set_fields,
              "$unset": {"preferred_market": "", "last_resolved_market": ""}})
    user = await db.users.find_one({"user_id": user["user_id"]})
    token, expires_at = await _create_session(db, user["user_id"], request)
    _set_session_cookie(response, token)
    _kick_warm_start(request, user)
    return _attach_session_to_response(_serialize_user(user), token,
                                                          expires_at)


@auth_router.post("/_demo_reset_rate_limit", include_in_schema=False)
async def _demo_reset_rate_limit():
    """Test-only helper: clears the in-process demo rate bucket."""
    _DEMO_LOGIN_BUCKET.clear()
    return {"ok": True}
@users_router.get("/me", response_model=UserOut)
async def users_me(user: dict = Depends(current_user)):
    return _serialize_user(user)


@users_router.get("/preferences", response_model=PreferenceVector)
async def users_get_prefs(user: dict = Depends(current_user)):
    pv = user.get("preference_vector") or {}
    return PreferenceVector(**pv)


@users_router.post("/preferences", response_model=UserOut)
async def users_save_prefs(
    prefs: PreferenceVector,
    request: Request,
    user: dict = Depends(current_user),
):
    if len(prefs.languages) < 1:
        raise HTTPException(400, "Pick at least 1 language")
    if len(prefs.genres) < 2:
        raise HTTPException(400, "Pick at least 2 genres")
    if len(prefs.eras) < 1:
        raise HTTPException(400, "Pick at least 1 era")
    if len(prefs.moods) < 2:
        raise HTTPException(400, "Pick at least 2 moods")
    if len(prefs.activities) < 1:
        raise HTTPException(400, "Pick at least 1 activity (when do you listen?)")
    # Phase 3.7 — host_personality validates against the live voice registry
    try:
        from services.voice_config import VOICE_REGISTRY as _VR
        _allowed = set(_VR.keys()) | {"auto"}
    except Exception:
        _allowed = {"auto", "veer_dubai", "monika_dubai", "dj_dubai"}
    if prefs.host_personality not in _allowed:
        raise HTTPException(400, "host_personality invalid")
    if prefs.market not in ("dubai", "dfw"):
        raise HTTPException(400, "market must be 'dubai' or 'dfw'")
    db = request.app.state.db
    # Phase B — derive home_city from market on onboarding save unless
    # the user already set it explicitly via PATCH /api/users/me/home_city.
    # Mirrors useGeoStore.DISPLAY_NAMES so the labels stay in lockstep.
    _MARKET_TO_HOME_CITY = {"dubai": "Dubai", "dfw": "Dallas"}
    update_doc: dict = {
        "preference_vector": prefs.model_dump(),
        "market":              prefs.market,
        "onboarding_complete": True,
    }
    existing = await db.users.find_one({"user_id": user["user_id"]},
                                                                {"home_city": 1})
    if not (existing or {}).get("home_city"):
        update_doc["home_city"] = _MARKET_TO_HOME_CITY.get(prefs.market)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": update_doc},
    )
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    # Phase 5 — award onboarding 50 BC (idempotent) + complete any pending referral
    try:
        from services.bigcoin import maybe_award_onboarding
        from routes.bigcoin import complete_referral_after_onboarding
        await maybe_award_onboarding(db, user["user_id"])
        await complete_referral_after_onboarding(db, user["user_id"])
    except Exception:
        pass
    # Phase 5.1 — kick a warm-start prebuild now that we know the user's prefs
    _kick_warm_start(request, fresh)
    return _serialize_user(fresh)


@users_router.post("/onboarding/reset", response_model=UserOut)
async def users_reset_onboarding(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.users.update_one(
        {"user_id": user["user_id"]}, {"$set": {"onboarding_complete": False}},
    )
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return _serialize_user(fresh)



# ─── Phase 11.5 — mobile push-token registration ────────────────────────
class PushTokenIn(BaseModel):
    expo_push_token: str = Field(..., min_length=1, max_length=512)
    platform: Optional[str] = None   # "ios" | "android" | "web"
    device_id: Optional[str] = None
    # Phase 13e — distinguish Expo proxy tokens from raw APNs hex tokens.
    device_type: Optional[str] = Field(default=None,
                                                            pattern="^(expo|apns_native)$")
    apns_environment: Optional[str] = Field(default=None,
                                                                  pattern="^(sandbox|production)$")


class PushTokenDeleteIn(BaseModel):
    expo_push_token: str = Field(..., min_length=1, max_length=512)


_ALLOWED_PUSH_PLATFORMS = {"ios", "android", "web"}


@users_router.post("/push_token")
async def register_push_token(body: PushTokenIn, request: Request,
                                            user: dict = Depends(current_user)):
    """Register a push token for the current user.  Idempotent — upserts
    on `(user_id, expo_push_token)`.  One user can have many tokens
    (multi-device).

    Phase 13e — accepts both Expo proxy tokens (default; `device_type=expo`)
    and raw APNs hex tokens (`device_type=apns_native` + optional
    `apns_environment=sandbox|production`)."""
    db = request.app.state.db
    plat = (body.platform or "").lower().strip() or None
    if plat is not None and plat not in _ALLOWED_PUSH_PLATFORMS:
        raise HTTPException(
            400, f"invalid platform '{body.platform}'. "
                  f"Allowed: {sorted(_ALLOWED_PUSH_PLATFORMS)}")
    device_type = body.device_type or "expo"
    apns_env = body.apns_environment or (
        "sandbox" if device_type == "apns_native" else None)
    now = _now()
    key = {"user_id": user["user_id"],
              "expo_push_token": body.expo_push_token}
    existing = await db.user_push_tokens.find_one(key)
    if existing:
        await db.user_push_tokens.update_one(
            key,
            {"$set": {"platform": plat or existing.get("platform"),
                        "device_id": body.device_id or existing.get("device_id"),
                        "device_type": device_type,
                        "apns_environment": apns_env,
                        "updated_at": now,
                        "active": True}})
        return {"status": "ok", "registered": False,
                  "token_id": existing.get("token_id")
                                or existing.get("_id"),
                  "device_type": device_type}
    token_id = f"pt_{uuid.uuid4().hex[:14]}"
    await db.user_push_tokens.insert_one({
        "_id": token_id,
        "token_id": token_id,
        "user_id": user["user_id"],
        "expo_push_token": body.expo_push_token,
        "platform": plat,
        "device_id": body.device_id,
        "device_type": device_type,
        "apns_environment": apns_env,
        "active": True,
        "created_at": now,
        "updated_at": now,
    })
    return {"status": "ok", "registered": True, "token_id": token_id,
              "device_type": device_type}


@users_router.delete("/push_token")
async def deregister_push_token(body: PushTokenDeleteIn, request: Request,
                                                  user: dict = Depends(current_user)):
    """Soft-delete: marks the row `active=False`.  Idempotent — a call
    against a non-existent token still returns 200 ok with modified=0."""
    db = request.app.state.db
    res = await db.user_push_tokens.update_many(
        {"user_id": user["user_id"],
          "expo_push_token": body.expo_push_token},
        {"$set": {"active": False, "deactivated_at": _now(),
                    "updated_at": _now()}})
    return {"status": "ok", "modified": res.modified_count,
              "deactivated": res.modified_count > 0}
