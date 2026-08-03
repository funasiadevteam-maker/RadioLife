"""Phase 12d — Unified wallet pass signing.

Two builders:
  - `build_apple_pass(coupon, business, offer)`
  - `build_google_wallet_pass(coupon, business, offer)`

Both return `{mode, save_url_or_token, reason, ...}`. `mode` is one of
`"live"` (real signed output) or `"mock"` (stub URL + HIGHLIGHTED MOCK
log + reason).

Apple PassKit (real path):
  Requires env: APPLE_PASS_TYPE_ID, APPLE_TEAM_ID, APPLE_PASS_CERT_PATH,
  APPLE_PASS_KEY_PATH, APPLE_WWDR_CERT_PATH. Builds a .pkpass ZIP with
  pass.json, manifest.json (sha1 of each file), and signature (PKCS#7
  signed manifest). Returns the raw bytes via `pkpass_bytes`.

Google Wallet (real path):
  Delegates to the existing `services/google_wallet.WalletClient`
  (`get_wallet_client().mint_coupon_pass(...)`) when issuer creds are
  configured. That path mints a JWT-signed save URL.

Both paths call `integration_health.record_call` on success/failure so
the 12d switcher promotes/demotes correctly.
"""
from __future__ import annotations
import hashlib
import io
import json
import logging
import os
import uuid
import zipfile
from typing import Optional

logger = logging.getLogger("bigfm.wallet_passes")

# ─── Apple PassKit ────────────────────────────────────────────────────
APPLE_ENV_KEYS = (
    "APPLE_PASS_TYPE_ID", "APPLE_TEAM_ID",
    "APPLE_PASS_CERT_PATH", "APPLE_PASS_KEY_PATH",
    "APPLE_WWDR_CERT_PATH",
)


def _apple_env_complete() -> bool:
    return all(os.environ.get(k) for k in APPLE_ENV_KEYS)


def _apple_stub(coupon: dict, reason: str) -> dict:
    logger.warning(
        "***** HIGHLIGHTED MOCK ***** apple_pass coupon=%s reason=%s",
        coupon.get("coupon_id"), reason)
    return {
        "mode": "mock",
        "save_url": (f"https://placeholder.bigfm.dubai/apple-pass/"
                          f"{coupon.get('coupon_id')}"),
        "pass_status": "stub",
        "reason": reason,
    }


def _build_pass_json(*, coupon: dict, business: dict, offer: dict) -> dict:
    """Minimal valid Apple Pass JSON (`coupon` type)."""
    return {
        "formatVersion": 1,
        "passTypeIdentifier": os.environ["APPLE_PASS_TYPE_ID"],
        "teamIdentifier": os.environ["APPLE_TEAM_ID"],
        "serialNumber": coupon.get("coupon_id") or uuid.uuid4().hex,
        "organizationName": (business or {}).get(
            "display_name", "BigFM"),
        "description": (offer or {}).get(
            "title", "BigFM Coupon"),
        "coupon": {
            "primaryFields": [{
                "key": "offer",
                "label": "OFFER",
                "value": (offer or {}).get("title", "")}],
            "auxiliaryFields": [{
                "key": "merchant",
                "label": "MERCHANT",
                "value": (business or {}).get("display_name", "")}],
            "backFields": [{
                "key": "code",
                "label": "CODE",
                "value": coupon.get("qr_token", "")}],
        },
        "barcode": {
            "format": "PKBarcodeFormatQR",
            "message": coupon.get("qr_token", ""),
            "messageEncoding": "iso-8859-1"},
    }


def _sign_apple_manifest(manifest_bytes: bytes) -> bytes:
    """PKCS#7 detached signature over the manifest.

    Uses the `cryptography` lib already in the venv. Loads the WWDR
    intermediate as an extra cert so verifiers trust the chain.
    """
    from cryptography.hazmat.primitives.serialization import (
        load_pem_private_key)
    from cryptography.hazmat.primitives.serialization.pkcs7 import (
        PKCS7SignatureBuilder, PKCS7Options)
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    cert_path = os.environ["APPLE_PASS_CERT_PATH"]
    key_path = os.environ["APPLE_PASS_KEY_PATH"]
    wwdr_path = os.environ["APPLE_WWDR_CERT_PATH"]

    with open(cert_path, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    with open(key_path, "rb") as f:
        key = load_pem_private_key(f.read(), password=None)
    with open(wwdr_path, "rb") as f:
        wwdr = x509.load_pem_x509_certificate(f.read())

    builder = (PKCS7SignatureBuilder()
                  .set_data(manifest_bytes)
                  .add_signer(cert, key, hashes.SHA256())
                  .add_certificate(wwdr))
    sig = builder.sign(
        encoding=__import__("cryptography").hazmat.primitives.serialization
        .Encoding.DER,
        options=[PKCS7Options.DetachedSignature, PKCS7Options.Binary])
    return sig


def _build_pkpass_bytes(*, coupon: dict, business: dict,
                                  offer: dict) -> bytes:
    pass_json = _build_pass_json(
        coupon=coupon, business=business, offer=offer)
    pass_bytes = json.dumps(pass_json,
                                       separators=(",", ":")).encode()

    files = {"pass.json": pass_bytes}
    # manifest.json: sha1 of every file in the bundle
    manifest = {name: hashlib.sha1(data).hexdigest()
                    for name, data in files.items()}
    manifest_bytes = json.dumps(manifest,
                                            separators=(",", ":")).encode()
    files["manifest.json"] = manifest_bytes

    signature = _sign_apple_manifest(manifest_bytes)
    files["signature"] = signature

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


async def build_apple_pass(db, *, coupon: dict, business: dict,
                                      offer: dict) -> dict:
    """Returns either real .pkpass bytes (mode=live) or a stub save URL
    (mode=mock). Records the health call either way."""
    from services import integration_health as ih

    if not _apple_env_complete():
        missing = [k for k in APPLE_ENV_KEYS if not os.environ.get(k)]
        out = _apple_stub(coupon, f"missing_env:{','.join(missing)}")
        await ih.record_call(db, "wallet", success=False,
                                     error=out["reason"],
                                     detail={"apple": "mock",
                                                "missing": missing})
        return out
    try:
        pkpass = _build_pkpass_bytes(
            coupon=coupon, business=business, offer=offer)
        await ih.record_call(db, "wallet", success=True,
                                     detail={"apple": "live"})
        return {"mode": "live",
                  "pkpass_bytes": pkpass,
                  "size_bytes": len(pkpass),
                  "pass_status": "signed",
                  "reason": None}
    except Exception as e:
        logger.warning(f"apple pass sign failed: {e}")
        await ih.record_call(db, "wallet", success=False,
                                     error=str(e),
                                     detail={"apple": "error"})
        return _apple_stub(coupon, f"sign_error:{str(e)[:120]}")


# ─── Google Wallet ────────────────────────────────────────────────────
def _google_wallet_creds_present() -> bool:
    return bool(os.environ.get("GOOGLE_WALLET_ISSUER_ID")
                  and (os.environ.get(
                        "GOOGLE_WALLET_SERVICE_ACCOUNT_PATH")
                        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")))


async def build_google_wallet_pass(db, *, coupon: dict, business: dict,
                                                  offer: dict) -> dict:
    from services import integration_health as ih
    if not _google_wallet_creds_present():
        logger.warning(
            "***** HIGHLIGHTED MOCK ***** google_wallet_pass coupon=%s "
            "reason=missing_env", coupon.get("coupon_id"))
        await ih.record_call(db, "wallet", success=False,
                                     error="google_wallet_missing_env",
                                     detail={"google": "mock"})
        return {
            "mode": "mock",
            "save_url": (f"https://pay.google.com/gp/v/save/"
                              f"stub-{coupon.get('coupon_id')}"),
            "pass_status": "stub",
            "reason": "google_wallet_missing_env",
        }
    try:
        from services.google_wallet import get_wallet_client
        cli = get_wallet_client()
        res = cli.mint_coupon_pass(
            coupon=coupon, business=business, offer=offer)
        # WalletClient may itself fall back to stub mode if its probe
        # detected the API isn't enabled — distinguish that.
        if (res.get("pass_status") or "").startswith("stub"):
            await ih.record_call(db, "wallet", success=False,
                                         error=res.get("reason"),
                                         detail={"google": "stub_fallback"})
            return {"mode": "mock", **res}
        await ih.record_call(db, "wallet", success=True,
                                     detail={"google": "live"})
        return {"mode": "live", "save_url": res["save_url"],
                  "jwt": res.get("jwt"),
                  "pass_status": res.get("pass_status", "signed"),
                  "reason": None}
    except Exception as e:
        logger.warning(f"google wallet mint failed: {e}")
        await ih.record_call(db, "wallet", success=False,
                                     error=str(e),
                                     detail={"google": "error"})
        return {"mode": "mock", "save_url": "",
                  "pass_status": "stub",
                  "reason": f"mint_error:{str(e)[:120]}"}
