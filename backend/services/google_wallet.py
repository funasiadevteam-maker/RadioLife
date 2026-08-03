"""Phase 9c — Google Wallet integration.

Mints JWT-signed save URLs for coupon GenericObjects using the GCP
service account already wired up in 9a (no new credential).  Falls back
to a *stub* save URL if either:

  - the Wallet API is not enabled on the GCP project
  - GOOGLE_WALLET_ISSUER_ID env var is missing
  - the service account doesn't have wallet_object.issuer scope

The mode is surfaced on /api/system/integrations so ops can spot it
instantly.

Apple Wallet (.pkpass) is a hard *stub* in 9c — the Apple Developer
cert + signing infra is deferred.

References:
  https://developers.google.com/wallet/generic
  https://developers.google.com/wallet/generic/web/jwt-format
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt
from google.oauth2 import service_account

logger = logging.getLogger("bigfm.wallet")

_WALLET_SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]
_WALLET_API_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
_SAVE_URL_PREFIX = "https://pay.google.com/gp/v/save/"
DEFAULT_CLASS_SUFFIX = "bigfm_coupon"


def _sa_path() -> Optional[str]:
    p = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    return p if p and os.path.exists(p) else None


def _load_wallet_creds() -> tuple[Optional[service_account.Credentials], Optional[str]]:
    """Same loader pattern as `maps_client._load_service_account_creds`,
    but bound to the Wallet API scope.  Returns (creds, sa_email)."""
    p = _sa_path()
    if not p:
        return None, None
    try:
        creds = service_account.Credentials.from_service_account_file(
            p, scopes=_WALLET_SCOPES)
        return creds, creds.service_account_email
    except Exception as e:
        logger.warning(f"wallet creds load failed: {e}")
        return None, None


def _sa_private_key_pem() -> Optional[str]:
    """For JWT-issuance we need the RAW pem from the SA JSON."""
    p = _sa_path()
    if not p:
        return None
    try:
        with open(p) as f:
            return json.load(f).get("private_key")
    except Exception:
        return None


def _now():
    return datetime.now(timezone.utc)


class WalletClient:
    """Singleton-ish wrapper.  Use `get_wallet_client()`."""

    name = "GoogleWalletClient"

    def __init__(self):
        self.mode = "stub"
        self.creds, self.sa_email = _load_wallet_creds()
        self.issuer_id = (os.environ.get("GOOGLE_WALLET_ISSUER_ID")
                                 or "").strip() or None
        self.api_health = "unknown"
        self.error: Optional[str] = None

    # ─── boot probe ───────────────────────────────────────────────────
    async def probe(self) -> dict:
        """One cheap call to the Wallet API.  Sets api_health + mode."""
        if not self.creds:
            self.mode = "stub"
            self.api_health = "no_sa"
            self.error = "service_account_not_loaded"
            return self._probe_dict()
        if not self.issuer_id:
            # Without an issuer ID we can mint JWTs but they won't
            # actually save (no class to attach to).  Mark as stub so
            # the listener UI doesn't trick anyone into expecting it
            # to land in Google Pay.
            self.mode = "stub"
            self.api_health = "no_issuer_configured"
            self.error = "set GOOGLE_WALLET_ISSUER_ID env var"
            return self._probe_dict()
        # Try a real API call: list classes under our issuer.
        try:
            from google.auth.transport.requests import Request as GAuthRequest
            self.creds.refresh(GAuthRequest())
        except Exception as e:
            self.mode = "stub"
            self.api_health = "token_refresh_failed"
            self.error = str(e)
            return self._probe_dict()
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(
                    f"{_WALLET_API_BASE}/genericClass",
                    headers={"Authorization":
                              f"Bearer {self.creds.token}"},
                    params={"issuerId": self.issuer_id})
            if r.status_code == 200:
                self.mode = "live"
                self.api_health = "ok"
                self.error = None
            elif r.status_code in (401, 403):
                self.mode = "stub"
                self.api_health = "forbidden"
                self.error = (r.json().get("error", {}).get("message")
                                if r.headers.get("content-type", "").startswith("application/json")
                                else r.text[:200])
            else:
                self.mode = "stub"
                self.api_health = f"http_{r.status_code}"
                self.error = r.text[:200]
        except Exception as e:
            self.mode = "stub"
            self.api_health = "error"
            self.error = str(e)
        return self._probe_dict()

    def _probe_dict(self) -> dict:
        return {
            "client": self.name,
            "mode": self.mode,
            "api_health": self.api_health,
            "auth_email": self.sa_email,
            "issuer_id": self.issuer_id,
            "error": self.error,
        }

    # ─── pass minting ─────────────────────────────────────────────────
    def mint_coupon_pass(self, *, coupon: dict, business: dict,
                                offer: dict) -> dict:
        """Returns {save_url, pass_status, jwt?, object_id?}.

        pass_status is "live" when we minted a real JWT against the
        configured issuer; "stub" when we returned a synthesised URL
        for UI testing only.
        """
        coupon_id = coupon["coupon_id"]
        # Stub fast-path
        if self.mode != "live":
            return {
                "save_url": f"{_SAVE_URL_PREFIX}stub-{coupon_id}",
                "pass_status": "stub",
                "reason": self.error or self.api_health,
            }
        pem = _sa_private_key_pem()
        if not pem:
            return {"save_url": f"{_SAVE_URL_PREFIX}stub-{coupon_id}",
                       "pass_status": "stub",
                       "reason": "private_key_unavailable"}
        class_id = f"{self.issuer_id}.{DEFAULT_CLASS_SUFFIX}"
        object_id = f"{self.issuer_id}.coupon_{coupon_id}"
        offer_title = offer.get("title", "Coupon")
        biz_name = business.get("name", "Business")
        expires_at = coupon.get("expires_at")
        if isinstance(expires_at, datetime):
            expires_iso = expires_at.astimezone(timezone.utc).isoformat()
        else:
            expires_iso = (
                expires_at or
                (_now() + timedelta(hours=1)).isoformat())
        # Build a minimal GenericObject for inline JWT mode.  This avoids
        # the need to pre-create classes/objects via REST.
        generic_object = {
            "id": object_id,
            "classId": class_id,
            "logo": {"sourceUri": {"uri": business.get("logo_url")
                                            or "https://placehold.co/96x96/png"}},
            "cardTitle": {"defaultValue": {"language": "en-US",
                                                    "value": biz_name}},
            "header": {"defaultValue": {"language": "en-US",
                                                "value": offer_title}},
            "subheader": {"defaultValue": {"language": "en-US",
                                                    "value": coupon.get(
                                                        "redemption_code",
                                                        coupon_id)}},
            "barcode": {"type": "QR_CODE",
                            "value": coupon.get("qr_token", coupon_id),
                            "alternateText": coupon.get(
                                "redemption_code", coupon_id)},
            "textModulesData": [
                {"header": "Terms",
                  "body": offer.get("terms_text", "")[:1000] or "—",
                  "id": "terms"},
                {"header": "Expires",
                  "body": expires_iso, "id": "expires"},
            ],
            "validTimeInterval": {
                "end": {"date": expires_iso}},
        }
        payload = {
            "iss": self.sa_email,
            "aud": "google",
            "typ": "savetowallet",
            "iat": int(_now().timestamp()),
            "payload": {"genericObjects": [generic_object]},
        }
        try:
            token = jwt.encode(payload, pem, algorithm="RS256")
        except Exception as e:
            logger.warning(f"wallet JWT encode failed: {e}")
            return {"save_url": f"{_SAVE_URL_PREFIX}stub-{coupon_id}",
                       "pass_status": "stub",
                       "reason": f"jwt_encode_failed:{e}"}
        return {
            "save_url": f"{_SAVE_URL_PREFIX}{token}",
            "pass_status": "live",
            "jwt": token,
            "object_id": object_id,
        }


_singleton: Optional[WalletClient] = None


def get_wallet_client() -> WalletClient:
    global _singleton
    if _singleton is None:
        _singleton = WalletClient()
    return _singleton


async def probe_wallet(app=None) -> dict:
    """Called on lifespan startup.  Sets app.state.wallet_probe."""
    cli = get_wallet_client()
    res = await cli.probe()
    if app is not None:
        app.state.wallet_probe = res
    logger.info(f"Wallet probe: mode={res['mode']} "
                   f"health={res['api_health']} "
                   f"issuer={res.get('issuer_id') or '-'}")
    return res


def mint_apple_wallet_stub(coupon: dict) -> dict:
    """Apple Wallet is stub-only in 9c — real .pkpass requires Apple
    Developer cert + signing infra (deferred)."""
    return {
        "save_url": f"https://placeholder.bigfm.dubai/apple-pass/{coupon['coupon_id']}",
        "pass_status": "stub",
        "reason": "apple_dev_cert_not_configured",
    }


__all__ = ["get_wallet_client", "probe_wallet", "mint_apple_wallet_stub",
              "WalletClient"]
