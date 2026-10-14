"""Resolve a merchant's display/settlement currency from its location.

Businesses don't carry an explicit `currency` field yet, but they do carry a
`country` / `city` / `market`.  We map that to an ISO-4217 code, defaulting to
AED (the app's Dubai home market).  A business MAY override via an explicit
`currency` field.
"""
from typing import Optional

DEFAULT_CURRENCY = "aed"  # Dubai home market

COUNTRY_CURRENCY = {
    "united arab emirates": "aed", "uae": "aed", "ae": "aed",
    "united states": "usd", "usa": "usd", "us": "usd",
    "united kingdom": "gbp", "uk": "gbp", "gb": "gbp",
    "india": "inr", "in": "inr",
    "saudi arabia": "sar", "sa": "sar", "ksa": "sar",
    "qatar": "qar", "qa": "qar",
    "kuwait": "kwd", "kw": "kwd",
    "bahrain": "bhd", "bh": "bhd",
    "oman": "omr", "om": "omr",
    "egypt": "egp", "eg": "egp",
}

_AED_CITIES = {"dubai", "abu dhabi", "sharjah", "ajman", "al ain", "ras al khaimah", "fujairah"}


def currency_for_business(biz: Optional[dict]) -> str:
    """Lower-cased ISO currency code for a business doc. Never raises."""
    if not biz:
        return DEFAULT_CURRENCY
    explicit = biz.get("currency")
    if explicit:
        return str(explicit).strip().lower()
    for key in ("country", "country_code", "market"):
        v = biz.get(key)
        if v and str(v).strip().lower() in COUNTRY_CURRENCY:
            return COUNTRY_CURRENCY[str(v).strip().lower()]
    city = str(biz.get("city") or biz.get("market") or "").strip().lower()
    if city in _AED_CITIES:
        return "aed"
    return DEFAULT_CURRENCY
