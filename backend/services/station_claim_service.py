"""Phase 42-C — Station claim service.

Owns:
    • Homepage domain extraction (TLD+1, strip www).
    • Email-domain → station-homepage match check (exact or subdomain).
    • Mailgun-mocked email logger (writes to `mocked_emails` collection so
        the tester can read the verification token without a real provider).
    • State-transition helper `auto_verify_or_queue_admin`.

Mailgun is currently MOCKED — we deliberately do NOT call the live API.
When Mailgun env vars are populated, swap the `_log_mock_email` call for
`mailgun_client.send_email()` and remove the `mocked_emails` insert.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

log = logging.getLogger("bigfm.station_claim")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# ──────────────────── domain extraction ────────────────────
def derive_homepage_domain(station: Dict[str, Any]) -> Optional[str]:
    """Return the registered (TLD+1) domain for `station.homepage`, or
    None if the station has no usable homepage URL.

    Examples:
        https://www.bbc.co.uk/radio       → "bbc.co.uk"
        http://radio.example.com:8080  → "example.com"
        not-a-url                                                → None
    """
    homepage = (station or {}).get("homepage") or ""
    homepage = homepage.strip()
    if not homepage:
        return None
    # Add scheme so urlparse can split host correctly.
    if "://" not in homepage:
        homepage = "http://" + homepage
    try:
        parsed = urlparse(homepage)
    except Exception:
        return None
    host = (parsed.hostname or "").lower().strip()
    if not host:
        return None
    # Strip leading "www."
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    # Known multi-part public suffixes — keep last 3 labels.
    parts = host.split(".")
    MULTI_SUFFIXES = {
        "co.uk", "co.in", "co.jp", "co.nz", "co.za",
        "com.au", "com.br", "com.mx", "ac.uk", "org.uk",
        "gov.in", "ac.in",
    }
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_SUFFIXES:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


_EMAIL_RE = re.compile(r"^[^\s@]+@([^\s@]+\.[^\s@]+)$")


def email_domain_matches_homepage(contact_email: str,
                                                                              station: Dict[str, Any]) -> bool:
    """True when the email's domain exactly matches OR is a subdomain
    of the station's derived homepage domain.

    Examples (homepage=bbc.co.uk):
        "press@bbc.co.uk"      → True (exact)
        "dj@radio.bbc.co.uk" → True (subdomain)
        "fan@gmail.com"          → False
    """
    if not contact_email:
        return False
    m = _EMAIL_RE.match(contact_email.strip().lower())
    if not m:
        return False
    email_host = m.group(1)
    home_domain = derive_homepage_domain(station)
    if not home_domain:
        return False
    home_domain = home_domain.lower()
    return email_host == home_domain or email_host.endswith("." + home_domain)


# ──────────────────── mocked email ────────────────────
async def _log_mock_email(db, *, to: str, subject: str, html: str,
                                                          tags: Optional[list] = None,
                                                          claim_id: Optional[str] = None,
                                                          verification_token: Optional[str] = None,
                                                          ) -> Dict[str, Any]:
    """Insert into `mocked_emails`.    Tester reads tokens from here."""
    doc_id = _new_id("memail")
    now = _now()
    doc = {
        "_id": doc_id, "id": doc_id,
        "provider": "mocked",
        "to": to,
        "subject": subject,
        "html": html,
        "tags": tags or [],
        "claim_id": claim_id,
        "verification_token": verification_token,
        "created_at": now,
    }
    await db.mocked_emails.insert_one(doc)
    log.info("[mocked_email] id=%s claim=%s to=%s subject=%s",
                  doc_id, claim_id, to, subject)
    return {"provider": "mocked", "message_id": doc_id,
                  "to": to, "status": "logged"}


def _build_verification_link(verification_token: str) -> str:
    base = (
        # Prefer explicit app-host env; fall back to the platform's
        # configured public URL.  Both are safe — the verify endpoint is
        # platform-rooted and idempotent.
        __import__("os").environ.get("BIGFM_PUBLIC_BASE_URL")
        or __import__("os").environ.get("REACT_APP_BACKEND_URL")
        or "https://app.bigfantv.com"
    )
    return f"{base.rstrip('/')}/claim/verify/{verification_token}"


async def send_verification_email(db, *, claim: Dict[str, Any]) -> Dict[str, Any]:
    """Compose + log a verification email for a claim in email_domain
    verification mode."""
    link = _build_verification_link(claim["verification_token"])
    station_name = claim.get("station_name_snapshot") or claim.get("station_id")
    subject = f"Verify your ownership of {station_name} on RadioLife"
    html = f"""
        <p>Hi {claim.get('contact_role', 'there')},</p>
        <p>You're receiving this because someone (hopefully you) submitted a
        claim of ownership for the station <strong>{station_name}</strong> on
        RadioLife.</p>
        <p>Confirm your ownership by clicking this link:</p>
        <p><a href="{link}">{link}</a></p>
        <p>This link is for {claim.get('contact_email')}.  If you did not
        request this claim, you can safely ignore this email.</p>
        <p>— The RadioLife team</p>
    """.strip()
    return await _log_mock_email(
        db, to=claim["contact_email"], subject=subject, html=html,
        tags=["station_claim", "verification"],
        claim_id=claim["id"],
        verification_token=claim["verification_token"])


# ──────────────────── state transition ────────────────────
async def auto_verify_or_queue_admin(db, *,
                                                                              claim: Dict[str, Any],
                                                                              station: Dict[str, Any],
                                                                              ) -> Dict[str, Any]:
    """Decide the next state for a freshly-submitted claim.

    Returns the patched claim dict (with updated fields applied).  Caller
    is responsible for persisting via update_one.
    """
    now = _now()
    matches = email_domain_matches_homepage(claim["contact_email"], station)
    patch: Dict[str, Any] = {"verification_attempted_at": now,
                                                              "updated_at": now}
    if matches:
        patch["verification_method"] = "email_domain"
        patch["verification_status"] = "email_sent"
        patch["claim_status"] = "verifying"
        patch["admin_review_status"] = "not_required"
        # Send mocked email AFTER computing patch (uses the token).
        claim_for_email = {**claim, **patch}
        await send_verification_email(db, claim=claim_for_email)
    else:
        patch["verification_method"] = "manual_admin"
        patch["verification_status"] = "pending"
        patch["claim_status"] = "submitted"
        patch["admin_review_status"] = "pending"
    return patch


# ──────────────────── promotion to owner ────────────────────
async def promote_claim_to_owner(db, *, claim: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the side-effects of an approved claim:
        • Create/touch `station_owner_profiles` row.
        • Update `imported_radio_stations` to claim_status="claimed",
            link the claim + profile, flip claim_badge_visible.
    Idempotent.    Returns `{profile_id, station_id, claim_id}`.
    """
    user_id = claim["claimed_by_user_id"]
    now = _now()
    # Upsert station_owner_profiles by user_id.
    profile = await db.station_owner_profiles.find_one({"user_id": user_id})
    if profile:
        await db.station_owner_profiles.update_one(
            {"user_id": user_id},
            {"$set": {"organization_name": claim.get("organization_name"),
                              "contact_email": claim.get("contact_email"),
                              "updated_at": now},
              "$inc": {"claimed_station_count": 1}})
        profile_id = profile["id"]
    else:
        profile_id = _new_id("sop")
        await db.station_owner_profiles.insert_one({
            "_id": profile_id, "id": profile_id,
            "user_id": user_id,
            "organization_name": claim.get("organization_name"),
            "website": None,
            "contact_email": claim.get("contact_email"),
            "payout_status": "not_setup",
            "tax_status": "not_setup",
            "claimed_station_count": 1,
            "created_at": now, "updated_at": now,
        })
    # Link station.
    await db.imported_radio_stations.update_one(
        {"id": claim["station_id"]},
        {"$set": {
            "claim_status": "claimed",
            "claim_id": claim["id"],
            "owner_profile_id": profile_id,
            "claim_badge_visible": True,
            "claimed_at": now,
        }})
    return {"profile_id": profile_id,
                  "station_id": claim["station_id"],
                  "claim_id": claim["id"]}


# ──────────────────── indexes ────────────────────
async def ensure_indexes(db) -> None:
    await db.radio_station_claims.create_index([("id", 1)], unique=True)
    await db.radio_station_claims.create_index(
        [("claim_status", 1), ("created_at", -1)])
    await db.radio_station_claims.create_index(
        [("station_id", 1), ("claim_status", 1)])
    await db.radio_station_claims.create_index([("claimed_by_user_id", 1)])
    await db.radio_station_claims.create_index(
        [("verification_token", 1)], unique=True, sparse=True)
    await db.station_owner_profiles.create_index([("id", 1)], unique=True)
    await db.station_owner_profiles.create_index(
        [("user_id", 1)], unique=True)
    # mocked_emails — TTL 7 days so test debris auto-cleans.
    await db.mocked_emails.create_index([("id", 1)], unique=True)
    try:
        await db.mocked_emails.create_index(
            "created_at", expireAfterSeconds=7 * 86400,
            name="ttl_created_at_7d")
    except Exception:
        pass
