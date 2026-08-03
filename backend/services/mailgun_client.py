"""Mailgun client — Phase 42-E2.5 (LIVE invite-a-friend).

Single abstraction: all Mailgun calls route through `send_email()`.

Reliability:
    • 3-attempt exponential backoff on 429 + 5xx.
    • Hourly-cached domain verification preflight (primary MAILGUN_DOMAIN
        with MAILGUN_DOMAIN_FALLBACK as a secondary if the primary isn't
        verified yet — useful while DNS for the `mg.` subdomain is still
        propagating).
    • Daily send counter (in-memory, resets at UTC midnight) for the
        `/api/admin/mail/health` surface.
    • API key is NEVER logged; recipients are masked to `abc***@example.com`.

Kill switch:
    When `MAILGUN_API_KEY` is unset OR `EMAIL_PROVIDER != "mailgun"`,
    `is_live()` returns False.  Individual flows (e.g. invite-a-friend)
    additionally gate on their own env flag like `INVITE_EMAIL_LIVE=1`.
"""
from __future__ import annotations
import logging
import os
import threading
import time
from datetime import datetime, timezone, date
from typing import Optional

import requests

logger = logging.getLogger("bigfm.mailgun")


# ── Module-level state (in-memory; resets on backend reload) ────────
_state_lock = threading.Lock()
_state: dict = {
    # domain → {ok: bool, checked_at: float, raw: dict}
    "verify_cache":      {},
    "daily_count":        0,
    "daily_count_date": date.today().isoformat(),
    "last_send_at":      None,
    "last_send_status": None,
    "last_message_id": None,
    "last_to_masked":  None,
    "last_error":          None,
}

_RETRY_MAX            = 3
_BACKOFF_BASE_SEC = 1.0
_VERIFY_TTL_SEC    = 3600  # 1 hour
_TIMEOUT_SEC         = 15


def is_live() -> bool:
    return bool(os.environ.get("MAILGUN_API_KEY")) \
              and os.environ.get("EMAIL_PROVIDER", "").lower() == "mailgun"


def _cfg() -> dict:
    return {
        "key":          os.environ.get("MAILGUN_API_KEY", ""),
        "domain":      os.environ.get("MAILGUN_DOMAIN", ""),
        "fallback":  os.environ.get("MAILGUN_DOMAIN_FALLBACK", ""),
        "api_base":  os.environ.get("MAILGUN_API_BASE",
                                                            "https://api.mailgun.net/v3"),
        "from":        os.environ.get("MAILGUN_FROM",
            f"BigFM <noreply@{os.environ.get('MAILGUN_DOMAIN', 'bigfantv.com')}>"),
    }


def _mask(addr: str) -> str:
    if not addr or "@" not in addr:
        return (addr or "")[:8]
    local, _, domain = addr.partition("@")
    return f"{local[:3]}***@{domain}"


def _today_key() -> str:
    return date.today().isoformat()


def _bump_counter() -> None:
    with _state_lock:
        today = _today_key()
        if _state["daily_count_date"] != today:
            _state["daily_count_date"] = today
            _state["daily_count"]        = 0
        _state["daily_count"] += 1


def _verify_domain(api_base: str, key: str, domain: str) -> dict:
    """Hit Mailgun's `/v3/domains/<domain>` and return verification info.
    Cached for `_VERIFY_TTL_SEC` per domain."""
    now = time.monotonic()
    with _state_lock:
        hit = _state["verify_cache"].get(domain)
    if hit and (now - hit["checked_at"]) < _VERIFY_TTL_SEC:
        return hit

    out: dict = {"checked_at": now, "ok": False, "state": "unknown"}
    try:
        url = f"{api_base}/domains/{domain}"
        r   = requests.get(url, auth=("api", key), timeout=_TIMEOUT_SEC)
        if r.status_code == 200:
            body = r.json()
            dom = body.get("domain") or {}
            out["state"] = dom.get("state") or "unknown"
            out["ok"]      = (out["state"] == "active")
            out["raw"]    = {"state": out["state"], "type": dom.get("type")}
        elif r.status_code == 404:
            out["state"]    = "not_found"
            out["http"]      = 404
        else:
            out["state"]    = "error"
            out["http"]      = r.status_code
    except Exception as e:
        out["state"]      = "error"
        out["exception"] = type(e).__name__
    with _state_lock:
        _state["verify_cache"][domain] = out
    return out


def _pick_domain(cfg: dict) -> tuple[Optional[str], dict]:
    """Return (best_domain_or_None, verification_info).  Primary
    domain first, fallback if primary isn't verified."""
    primary = cfg["domain"]
    fb        = cfg["fallback"]
    p_info  = _verify_domain(cfg["api_base"], cfg["key"], primary) if primary else {}
    if p_info.get("ok"):
        return primary, p_info
    if fb:
        f_info = _verify_domain(cfg["api_base"], cfg["key"], fb)
        if f_info.get("ok"):
            return fb, f_info
        return None, {"primary": p_info, "fallback": f_info}
    return None, p_info


def send_email(to, subject: str, html: str, *,
                              text: Optional[str] = None,
                              from_name: str = "BigFM",
                              tags: Optional[list] = None,
                              template_vars: Optional[dict] = None) -> dict:
    """Send a single transactional email via Mailgun's HTTP API.

    On 5xx/429 we retry with exponential backoff.  On any final failure
    we return `{ok: False, ...}` rather than raising — callers should
    record the email_status on the row but never fail the user UX.
    """
    cfg = _cfg()
    if not cfg["key"]:
        return {"ok": False, "error": "mailgun_no_api_key",
                      "message_id": None}
    domain, info = _pick_domain(cfg)
    if not domain:
        return {"ok": False, "error": f"mailgun_domain_not_verified:{info}",
                      "message_id": None}

    url = f"{cfg['api_base']}/{domain}/messages"
    # Override "from" address to use the resolved (verified) domain so
    # we don't try to send through an unverified primary.
    sender = cfg["from"].replace(cfg["domain"], domain) \
                          if cfg["domain"] and cfg["domain"] in cfg["from"] \
                          else f'{from_name} <noreply@{domain}>'

    recipients = to if isinstance(to, list) else [to]
    data = {"from": sender, "to": recipients, "subject": subject, "html": html}
    if text:
        data["text"] = text
    if tags:
        data["o:tag"] = tags
    if template_vars:
        import json as _json
        data["v:vars"] = _json.dumps(template_vars)

    masked_to = ", ".join(_mask(r) for r in recipients)
    t0 = time.monotonic()
    last_err: Optional[str] = None
    for attempt in range(_RETRY_MAX):
        try:
            r = requests.post(url, auth=("api", cfg["key"]),
                                          data=data, timeout=_TIMEOUT_SEC)
            latency_ms = int((time.monotonic() - t0) * 1000)
            if r.status_code < 300:
                body = r.json()
                msg_id = body.get("id")
                logger.info("[mailgun] sent to=%s subject=%r msg_id=%s "
                                      "domain=%s latency_ms=%d",
                                      masked_to, subject, msg_id, domain, latency_ms)
                _bump_counter()
                with _state_lock:
                    _state["last_send_at"]    = datetime.now(timezone.utc).isoformat()
                    _state["last_send_status"] = "sent"
                    _state["last_message_id"]  = msg_id
                    _state["last_to_masked"]  = masked_to
                    _state["last_error"]            = None
                return {"ok": True, "message_id": msg_id,
                              "to": recipients, "domain": domain,
                              "latency_ms": latency_ms, "error": None}
            # Retry on 429/5xx, fail-fast on 4xx (auth / bad recipient).
            retriable = (r.status_code == 429
                                      or 500 <= r.status_code < 600)
            last_err = f"http_{r.status_code}:{r.text[:160]}"
            logger.warning("[mailgun] send failed attempt=%d/%d "
                                          "status=%d to=%s subject=%r body=%s",
                                          attempt + 1, _RETRY_MAX, r.status_code,
                                          masked_to, subject, r.text[:200])
            if not retriable:
                break
        except Exception as e:
            last_err = f"{type(e).__name__}:{e}"
            logger.warning("[mailgun] send exception attempt=%d/%d to=%s "
                                          "err=%s", attempt + 1, _RETRY_MAX,
                                          masked_to, last_err)
        if attempt < _RETRY_MAX - 1:
            time.sleep(_BACKOFF_BASE_SEC * (2 ** attempt))

    with _state_lock:
        _state["last_send_at"]    = datetime.now(timezone.utc).isoformat()
        _state["last_send_status"] = "failed"
        _state["last_message_id"]  = None
        _state["last_to_masked"]  = masked_to
        _state["last_error"]            = last_err
    return {"ok": False, "error": last_err, "message_id": None,
                  "to": recipients, "domain": domain}


def health_snapshot() -> dict:
    """Snapshot for the admin /api/admin/mail/health endpoint.

    NEVER returns the API key.  Returns verification status,
    daily counters, and last-send breadcrumbs."""
    cfg     = _cfg()
    domain, info = _pick_domain(cfg) if cfg["key"] else (None, {})
    with _state_lock:
        snap = {
            "provider":              "mailgun",
            "is_live":              is_live(),
            "configured_domain": cfg["domain"] or None,
            "fallback_domain":  cfg["fallback"] or None,
            "active_domain":      domain,
            "verification":      info,
            "daily_count":        _state["daily_count"],
            "daily_count_date": _state["daily_count_date"],
            "last_send_at":      _state["last_send_at"],
            "last_send_status": _state["last_send_status"],
            "last_message_id": _state["last_message_id"],
            "last_to_masked":  _state["last_to_masked"],
            "last_error":          _state["last_error"],
            "invite_email_live": os.environ.get(
                "INVITE_EMAIL_LIVE", "").lower() in ("1", "true", "yes"),
        }
    return snap
