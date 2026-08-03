"""Phase 12d — Unified integration health tracker.

Central registry for the 4 third-party integrations we promote in 12d:
  - `maps`     (Google Maps Platform: Routes / Places / Weather / Geocoding)
  - `wallet`   (Apple PassKit + Google Wallet)
  - `gam`      (Google Ad Manager SOAP)
  - `sendgrid` (Email delivery for retention)

Each integration carries a single Mongo doc in `integration_health`:
    {
      _id: "<integration>",
      integration: "<integration>",
      mode: "live" | "mock" | "degraded",
      last_check_at: datetime,
      last_error: str | None,
      success_count_1h: int,
      failure_count_1h: int,
      window_start: datetime,
      detail: dict,        # integration-specific (per-sub-API status, etc.)
    }

Promotion / demotion rule (used by the 5-min health loop in server.py):
  - If creds present AND >=3 calls in the last hour AND success rate > 80%
    → `mode=live`
  - If creds present AND last call failed AND failure rate >= 50%
    → `mode=degraded`
  - If creds missing → `mode=mock`

`record_call(db, integration, success, ...)` is hot-path-friendly:
  rolls the 1h window automatically and never raises (best-effort).
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.integrations")

INTEGRATIONS = ("maps", "wallet", "gam", "sendgrid",
                       "apple_apns", "apple_siwa",
                       # Phase 15d additions:
                       "geo", "news")
WINDOW_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_integration_indexes(db) -> None:
    await db.integration_health.create_index("integration", unique=True)


# ─── creds detection ────────────────────────────────────────────────────
def _maps_creds_present() -> bool:
    p = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    return bool((p and os.path.exists(p))
                  or os.environ.get("GOOGLE_MAPS_API_KEY"))


def _apple_pass_creds_present() -> bool:
    keys = ("APPLE_PASS_TYPE_ID", "APPLE_TEAM_ID",
              "APPLE_PASS_CERT_PATH", "APPLE_PASS_KEY_PATH",
              "APPLE_WWDR_CERT_PATH")
    return all(os.environ.get(k) for k in keys)


def _google_wallet_creds_present() -> bool:
    return bool(os.environ.get("GOOGLE_WALLET_ISSUER_ID")
                  and (os.environ.get("GOOGLE_WALLET_SERVICE_ACCOUNT_PATH")
                          or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")))


def _wallet_creds_present() -> bool:
    return _apple_pass_creds_present() or _google_wallet_creds_present()


def _gam_creds_present() -> bool:
    return bool(os.environ.get("GAM_NETWORK_ID"))


def _sendgrid_creds_present() -> bool:
    return bool(os.environ.get("SENDGRID_API_KEY"))


def _apple_apns_creds_present() -> bool:
    keys = ("APPLE_TEAM_ID", "APPLE_KEY_ID",
              "APPLE_KEY_PATH", "APPLE_BUNDLE_ID")
    return all(os.environ.get(k) for k in keys) and (
        os.path.exists(os.environ.get("APPLE_KEY_PATH") or ""))


def _apple_siwa_creds_present() -> bool:
    keys = ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_KEY_PATH",
              "APPLE_SIWA_SERVICE_ID", "APPLE_SIWA_REDIRECT_URI")
    return all(os.environ.get(k) for k in keys) and (
        os.path.exists(os.environ.get("APPLE_KEY_PATH") or ""))


def creds_present(integration: str) -> bool:
    return {
        "maps": _maps_creds_present,
        "wallet": _wallet_creds_present,
        "gam": _gam_creds_present,
        "sendgrid": _sendgrid_creds_present,
        "apple_apns": _apple_apns_creds_present,
        "apple_siwa": _apple_siwa_creds_present,
        # Phase 15d
        "geo":  lambda: (os.environ.get("BIGFM_GEO_PROVIDER") or "mock").lower() != "mock",
        "news": lambda: (os.environ.get("BIGFM_NEWS_PROVIDER") or "mock").lower() != "mock"
                              and bool(os.environ.get("NEWSAPI_API_KEY")),
    }.get(integration, lambda: False)()


# ─── human steps to promote each integration ───────────────────────────
HUMAN_STEPS = {
    "maps": [
        "Enable the 4 APIs in GCP console: Routes, Places, Weather, Geocoding",
        "Console URL: https://console.cloud.google.com/apis/library?project=i-academy-143517",
        "Grant the existing service account roles/serviceusage.serviceUsageConsumer",
        "Expected billing: ~$5-10 per 1k Routes calls, free tier 28k/month",
        "Re-run probe: POST /api/admin/integrations/maps/probe",
    ],
    "wallet": [
        "Apple PassKit: in Apple Developer portal, generate a Pass Type ID, "
        "download the .pem cert + private key, plus the WWDR intermediate.",
        "Place the 3 PEM files under /app/backend/secrets/apple/ and set "
        "APPLE_PASS_TYPE_ID, APPLE_TEAM_ID, APPLE_PASS_CERT_PATH, "
        "APPLE_PASS_KEY_PATH, APPLE_WWDR_CERT_PATH.",
        "Google Wallet: in GCP, grant the existing service account the "
        "'Wallet Object Issuer' role on your issuer ID, set "
        "GOOGLE_WALLET_ISSUER_ID env, optionally "
        "GOOGLE_WALLET_SERVICE_ACCOUNT_PATH (defaults to "
        "GOOGLE_APPLICATION_CREDENTIALS).",
        "Restart backend — health loop will flip mode → live within 5 min.",
    ],
    "gam": [
        "Set GAM_NETWORK_ID env to your Ad Manager network code.",
        "Traffic at least one DELIVERING audio line item targeting this app "
        "(otherwise GAM stays in `degraded` mode with no_matching_line_item).",
        "Confirm the existing GCP service account has the Ad Manager "
        "'Trafficker' or 'Read-only' role.",
        "Run probe: POST /api/admin/integrations/gam/probe (admin only).",
    ],
    "sendgrid": [
        "Create a SendGrid API key in https://app.sendgrid.com/settings/api_keys "
        "with 'Mail Send' scope.",
        "Set SENDGRID_API_KEY env + restart backend.",
        "Set SENDGRID_PLAN_TIER env to free|essentials|pro|premier so the "
        "quota enforcer can apply the right send caps.",
        "Verify quota: GET /api/admin/integrations/sendgrid/quota (admin only).",
    ],
    "apple_apns": [
        "Apple ES256 key already stored at /app/secrets/apple/AuthKey_G6PN4Z7U9Q.p8 "
        "(key_id=G6PN4Z7U9Q, chmod 600).",
        "Set env vars in backend/.env: APPLE_TEAM_ID=<your Team ID>, "
        "APPLE_KEY_ID=G6PN4Z7U9Q, "
        "APPLE_KEY_PATH=/app/secrets/apple/AuthKey_G6PN4Z7U9Q.p8, "
        "APPLE_BUNDLE_ID=<your app bundle id>.",
        "Restart backend. Real APNs send wiring lands in Phase 13e — the "
        "switcher already detects the key and will flip apple_apns to live "
        "automatically when 13e ships.",
    ],
    "apple_siwa": [
        "Same .p8 key as APNs is reused for Sign in with Apple.",
        "Create a Services ID at https://developer.apple.com/account/resources/identifiers/list/serviceId "
        "and enable Sign in with Apple on it.",
        "Set env vars: APPLE_TEAM_ID, APPLE_KEY_ID=G6PN4Z7U9Q, "
        "APPLE_KEY_PATH=/app/secrets/apple/AuthKey_G6PN4Z7U9Q.p8, "
        "APPLE_SIWA_SERVICE_ID=<your services id>, "
        "APPLE_SIWA_REDIRECT_URI=<https URL configured in Services ID>.",
        "Restart backend. Real OAuth flow lands in Phase 13e — switcher "
        "plumbing is ready now.",
    ],
    # Phase 15d — geo + news.
    "geo": [
        "Default mode is MOCK (returns Dubai). To go live, choose ONE provider:",
        "OPTION A — MaxMind GeoLite2 City (free, recommended for production):",
        "  • Sign up at https://www.maxmind.com/en/geolite2/signup",
        "  • Download `GeoLite2-City.mmdb`, place at /app/backend/data/geolite2-city.mmdb",
        "  • Set MAXMIND_DB_PATH and BIGFM_GEO_PROVIDER=maxmind. Restart.",
        "OPTION B — ipapi.co (free tier, 1k/day, zero setup):",
        "  • Set BIGFM_GEO_PROVIDER=ipapi.co. Restart.",
        "Verify: curl GET /api/geo/me — `source` flips from `mock` to `ip`.",
    ],
    "news": [
        "Default mode is MOCK (returns 3 hard-coded headlines per market).",
        "To enable live local headlines via NewsAPI:",
        "  • Get an API key at https://newsapi.org/register (free tier 100/day).",
        "  • Set NEWSAPI_API_KEY=<your key> and BIGFM_NEWS_PROVIDER=newsapi.",
        "  • Restart backend.",
        "Verify: curl GET /api/news/local — `source` flips from `mock` to `live`.",
        "Cache TTL is 30 min per market; cap=5 headlines.",
    ],
}


# ─── core API ───────────────────────────────────────────────────────────
async def get_health(db, integration: str) -> dict:
    doc = await db.integration_health.find_one(
        {"integration": integration})
    if not doc:
        # Auto-init
        doc = await _seed_doc(db, integration)
    # Compute mode if missing or stale
    mode = await _compute_mode(integration, doc)
    if mode != doc.get("mode"):
        await db.integration_health.update_one(
            {"integration": integration},
            {"$set": {"mode": mode, "last_check_at": _now()}})
        doc["mode"] = mode
    return doc


async def get_all_health(db) -> dict:
    out = {}
    for i in INTEGRATIONS:
        h = await get_health(db, i)
        h.pop("_id", None)
        h["creds_present"] = creds_present(i)
        h["human_steps"] = HUMAN_STEPS.get(i, [])
        out[i] = h
    return out


async def record_call(db, integration: str, *, success: bool,
                                error: str | None = None,
                                detail: Optional[dict] = None) -> None:
    """Best-effort: never raises."""
    try:
        now = _now()
        doc = await db.integration_health.find_one(
            {"integration": integration})
        if not doc:
            doc = await _seed_doc(db, integration)
        # Roll 1h window if expired
        ws = doc.get("window_start")
        if (ws is None) or (now - _aware(ws)) > timedelta(
                seconds=WINDOW_SECONDS):
            await db.integration_health.update_one(
                {"integration": integration},
                {"$set": {"window_start": now,
                            "success_count_1h": 0,
                            "failure_count_1h": 0}})
        upd: dict = {"last_check_at": now}
        if error:
            upd["last_error"] = str(error)[:300]
        if detail:
            upd["detail"] = detail
        inc_field = ("success_count_1h" if success
                          else "failure_count_1h")
        await db.integration_health.update_one(
            {"integration": integration},
            {"$set": upd, "$inc": {inc_field: 1}})
    except Exception as e:
        logger.debug(f"record_call({integration}) noop: {e}")


async def recompute_mode(db, integration: str) -> str:
    """Force-recompute mode based on current counters. Returns the new
    mode and persists it."""
    doc = await db.integration_health.find_one(
        {"integration": integration}) or {}
    mode = await _compute_mode(integration, doc)
    await db.integration_health.update_one(
        {"integration": integration},
        {"$set": {"mode": mode, "last_check_at": _now()}},
        upsert=True)
    return mode


# ─── helpers ───────────────────────────────────────────────────────────
async def _seed_doc(db, integration: str) -> dict:
    now = _now()
    initial_mode = "live" if creds_present(integration) else "mock"
    doc = {
        "_id": integration, "integration": integration,
        "mode": initial_mode,
        "last_check_at": now,
        "last_error": None,
        "success_count_1h": 0,
        "failure_count_1h": 0,
        "window_start": now,
        "detail": {},
    }
    await db.integration_health.update_one(
        {"_id": integration}, {"$setOnInsert": doc}, upsert=True)
    return doc


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _compute_mode(integration: str, doc: dict) -> str:
    if not creds_present(integration):
        return "mock"
    s = int(doc.get("success_count_1h") or 0)
    f = int(doc.get("failure_count_1h") or 0)
    total = s + f
    if total < 3:
        # Not enough signal — keep the current mode if it's `live`,
        # otherwise treat as `live` because creds are present (optimistic).
        return doc.get("mode") if doc.get("mode") in (
            "live", "degraded") else "live"
    rate = s / total if total else 0
    if rate > 0.8:
        return "live"
    if rate < 0.5:
        return "degraded"
    return doc.get("mode") or "degraded"


# ─── HIGHLIGHTED MOCK helper (used on hot paths) ───────────────────────
def log_mock(integration: str, context: str) -> None:
    logger.warning(
        "***** HIGHLIGHTED MOCK ***** integration=%s context=%s "
        "(creds_present=%s)",
        integration, context, creds_present(integration))


def boot_log_modes() -> None:
    """Emit one HIGHLIGHTED MOCK log line per integration currently in
    mock mode, plus a single summary."""
    rows = []
    for i in INTEGRATIONS:
        present = creds_present(i)
        mode = "live(initial)" if present else "mock"
        rows.append(f"{i}={mode}")
        if not present:
            logger.warning(
                "***** HIGHLIGHTED MOCK ***** integration=%s "
                "creds missing → mock at boot", i)
    logger.info(f"Phase 12d integration modes (boot): {', '.join(rows)}")
