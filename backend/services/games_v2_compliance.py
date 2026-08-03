"""Phase 8c — Strict compliance validation + geo gating + age gating.

Builds on the 8a `validate_compliance` helper (which only checked presence
of three fields) with sweepstakes-aware rules:
  - terms_text: always required
  - odds_disclosure: required iff any prize is sweepstakes-like
  - no_purchase_necessary_text: required iff any prize is cash-equivalent
  - age_restriction: required iff any prize is age-gated
  - geo_restrictions_json: enforced at start_session
  - age_restriction: enforced at start_session
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


SWEEPSTAKES_PRIZE_TYPES = {"gift_card", "ticket_entry", "free_item",
                                  "experience"}
CASH_EQUIVALENT_PRIZE_TYPES = {"gift_card", "premium_credit_days",
                                       "ticket_entry"}
AGE_GATED_PRIZE_TYPES: set[str] = set()       # placeholder for future
                                                  # alcohol / 18+ prize types


def validate_compliance_strict(compliance: dict,
                                       prizes: list[dict]) -> None:
    """Raises ValueError with a single clear message naming the missing
    field; UI surfaces it directly."""
    missing: list[str] = []
    if not (compliance.get("terms_text") or "").strip():
        missing.append("terms_text")
    needs_odds = any(int(p.get("probability_weight") or 0) > 0
                          and p.get("prize_type") in SWEEPSTAKES_PRIZE_TYPES
                          for p in prizes)
    if needs_odds and not (compliance.get("odds_disclosure") or "").strip():
        missing.append("odds_disclosure")
    needs_npn = any(p.get("prize_type") in CASH_EQUIVALENT_PRIZE_TYPES
                          for p in prizes)
    if needs_npn and not (compliance.get("no_purchase_necessary_text") or "").strip():
        missing.append("no_purchase_necessary_text")
    needs_age = any(p.get("prize_type") in AGE_GATED_PRIZE_TYPES
                          for p in prizes)
    if needs_age and not str(compliance.get("age_restriction") or "").strip():
        missing.append("age_restriction")
    if missing:
        raise ValueError(
            "compliance_missing:" + ",".join(missing))


def _country_from_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    try:
        from geoip2fast import GeoIP2Fast
        g = GeoIP2Fast()
        r = g.lookup(ip)
        c = (r.country_code or "").upper()
        return c if c and c != "--" else None
    except Exception:
        return None


def check_geo_eligibility(compliance: dict, ip: Optional[str]) -> None:
    """Raises ValueError(geo_not_eligible) if the IP's country is not in
    the allowed_countries list (when set).

    Behavior matrix:
      - allowed empty OR contains '*' → no enforcement
      - country resolved + in list  → pass
      - country resolved + NOT in list → raise geo_not_eligible
      - country NOT resolved (private IP, opaque proxy) → log a WARN
        and fail-open (degraded mode).  In production, the proxy
        middleware should provide a real public IP; an unresolved IP
        indicates either dev/test or a misconfigured deployment.
    """
    import logging as _logging
    geo = (compliance or {}).get("geo_restrictions_json") or {}
    allowed = geo.get("allowed_countries") or []
    if not allowed or "*" in allowed:
        return
    country = _country_from_ip(ip)
    if country:
        if country.upper() not in {c.upper() for c in allowed}:
            raise ValueError("geo_not_eligible")
        return
    _logging.getLogger("bigfm.compliance").warning(
        "geo_gate_degraded: ip=%s could not be resolved to a country; "
        "passing through. Verify the X-Forwarded-For chain.", ip)


def check_age_eligibility(compliance: dict,
                                listener_age: Optional[int],
                                age_confirmed: bool) -> None:
    """Raises ValueError(age_not_confirmed | age_below_minimum) when the
    campaign requires an age gate that's missing or under-age."""
    min_age_raw = (compliance or {}).get("age_restriction")
    try:
        min_age = int(min_age_raw) if min_age_raw else 0
    except (TypeError, ValueError):
        min_age = 0
    if min_age <= 0:
        return
    if not age_confirmed:
        raise ValueError("age_not_confirmed")
    if listener_age is not None and listener_age < min_age:
        raise ValueError("age_below_minimum")
