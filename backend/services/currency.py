"""Currency detection — header-only + offline IP→country lookup.

Order of precedence:
1. `?currency=` query param (manual override; validated against SUPPORTED_CURRENCIES)
2. `CF-IPCountry` / `X-Country` header (when the ingress forwards it — Cloudflare prod)
3. First IP in `X-Forwarded-For` → offline GeoIP lookup (geoip2fast, bundled DB)
4. Default → USD

Country → currency map per Phase 3 spec:
   AE → AED · IN → INR · US/CA/AU/GB → USD · else USD.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from fastapi import Request

logger = logging.getLogger("bigfm.currency")

SUPPORTED_CURRENCIES = ("USD", "AED", "INR")

COUNTRY_TO_CURRENCY = {
    "AE": "AED",
    "IN": "INR",
    "US": "USD",
    "CA": "USD",
    "AU": "USD",
    "GB": "USD",
    "UK": "USD",
}

# Lazy-init the GeoIP DB once per process — first lookup loads the bundled
# country-only mmdb (~6MB) and keeps it in memory. We swallow init errors
# defensively so the billing endpoint never blows up if the package becomes
# unavailable; we just fall back to USD in that case.
_geoip = None
_geoip_init_failed = False


def _get_geoip():
    global _geoip, _geoip_init_failed
    if _geoip is not None or _geoip_init_failed:
        return _geoip
    try:
        from geoip2fast import GeoIP2Fast
        _geoip = GeoIP2Fast(verbose=False)
        logger.info("GeoIP2Fast loaded (offline country lookup)")
    except Exception as e:
        _geoip_init_failed = True
        logger.warning(f"GeoIP2Fast unavailable, IP→country lookup disabled: {e}")
    return _geoip


def _client_ip(request: Request) -> Optional[str]:
    """Pull the original client IP from the X-Forwarded-For chain. The
    ingress prepends the chain so the FIRST entry is the upstream client."""
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    if request.client and request.client.host:
        return request.client.host
    return None


def _country_from_ip(ip: str) -> Optional[str]:
    geo = _get_geoip()
    if not geo:
        return None
    try:
        r = geo.lookup(ip)
        cc = (getattr(r, "country_code", "") or "").upper().strip()
        # geoip2fast returns "--" for unknown/private IPs
        if cc and cc != "--" and len(cc) == 2:
            return cc
    except Exception as e:
        logger.debug(f"GeoIP lookup failed for {ip}: {e}")
    return None


def _cf_country_header(request: Request) -> Optional[str]:
    """Return the country code from CF-IPCountry / X-Country if present and valid."""
    headers = request.headers
    val = (
        headers.get("cf-ipcountry")
        or headers.get("CF-IPCountry")
        or headers.get("x-country")
        or headers.get("X-Country")
        or ""
    ).upper().strip()
    if val and val != "XX" and len(val) == 2:
        return val
    return None


def detect_currency(request: Request, override: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Return (currency_code, country_hint_or_None).

    Raises ValueError if `override` is provided but not in SUPPORTED_CURRENCIES.
    """
    if override:
        cur = override.upper().strip()
        if cur not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"unsupported currency '{override}'. Allowed: {', '.join(SUPPORTED_CURRENCIES)}"
            )
        return cur, None

    # 1) Explicit country header (Cloudflare prod)
    country = _cf_country_header(request)

    # 2) Fallback to GeoIP lookup of the client IP from X-Forwarded-For
    if not country:
        ip = _client_ip(request)
        if ip:
            cc = _country_from_ip(ip)
            if cc:
                country = cc

    if country and country in COUNTRY_TO_CURRENCY:
        return COUNTRY_TO_CURRENCY[country], country
    return "USD", country or None


# Public re-exports for the /_whoami debug endpoint
client_ip = _client_ip
country_from_ip = _country_from_ip
cf_country_header = _cf_country_header
