"""Phase ADMOD.1 — Recommended CPS hints by merchant category.

Advertiser-side polish for the AD.4 wizard: shows a per-category
suggested cost-per-save so new advertisers can size CPS with
confidence.  Values are suggestions only — the wizard never auto-fills.

Admin can tune values later without a code change by editing this file
(pod restart picks it up) or by pointing to a Mongo collection.
"""
from __future__ import annotations

from typing import Dict


# Per-category recommended CPS in CENTS (mirrors the user brief).
CATEGORY_HINTS_CENTS: Dict[str, int] = {
    "food":                                      10,   # Food & Beverage
    "beverage":                                10,
    "restaurant":                            10,
    "cafe":                                        10,
    "coffee":                                    10,
    "retail":                                    25,
    "entertainment":                      50,
    "nightlife":                              50,
    "club":                                        50,
    "bar":                                          50,
    "health":                                    30,
    "fitness":                                  30,
    "gym":                                        30,
    "services":                                20,   # Salon, spa, etc.
    "salon":                                    20,
    "spa":                                        20,
    "auto":                                        35,
    "home_services":                      35,
    "home":                                        35,
}

DEFAULT_CPS_CENTS = 15

# Human-readable groupings for the tooltip's "Learn more" popover.
CATEGORY_GROUPS = [
    {"label": "Food & Beverage",              "tags": ["food", "beverage", "restaurant", "cafe", "coffee"], "cents": 10},
    {"label": "Retail",                                "tags": ["retail"],                                                                                "cents": 25},
    {"label": "Entertainment / Nightlife",  "tags": ["entertainment", "nightlife", "club", "bar"],        "cents": 50},
    {"label": "Health & Fitness",                "tags": ["health", "fitness", "gym"],                                              "cents": 30},
    {"label": "Services",                              "tags": ["services", "salon", "spa"],                                          "cents": 20},
    {"label": "Auto / Home Services",          "tags": ["auto", "home_services", "home"],                                "cents": 35},
    {"label": "Default (unspecified)",          "tags": [],                                                                                        "cents": DEFAULT_CPS_CENTS},
]


# Phase AD.11 — per-zone banner CPM (cents per 1000 impressions).
# CPM = "cost per mille" = cents per 1000 impressions.  Advertisers see
# these values pre-filled in the banner wizard's step 4 and can override.
BANNER_ZONE_CPM_CENTS = {
    "landing_hero":      800,   # $8 CPM — premium above-the-fold
    "station_detail":  500,   # $5 CPM — engaged station listeners
    "games":                    400,   # $4 CPM — gaming session eyeballs
    "browse_row":          300,   # $3 CPM — high volume, lower intent
    "wallet":                  250,   # $2.50 CPM — post-purchase context
    "now_playing":        200,   # $2 CPM — persistent low-attention slot
    "bottom_bar":          150,   # $1.50 CPM — thin persistent rail
}

# Per-zone creative dimensions (px).  The upload endpoint validates
# against these so advertisers can't ship mis-sized assets.
BANNER_ZONE_DIMENSIONS = {
    "landing_hero":      {"width": 1200, "height": 400},
    "station_detail":  {"width":  970, "height": 250},
    "games":                    {"width":  970, "height": 250},
    "browse_row":          {"width":  728, "height": 200},
    "wallet":                  {"width":  728, "height":  90},
    "now_playing":        {"width":  320, "height": 180},
    "bottom_bar":          {"width":  728, "height":  90},
}

BANNER_ZONES = list(BANNER_ZONE_CPM_CENTS.keys())


# Phase AD.12 — Recommended cost-per-delivery (CPD) for notification
# ads.  Cents per single delivery — advertisers see this as an inline
# tooltip on the wizard's step 4 (Budget + CPD).  Values are
# suggestions only; the wizard never auto-fills — the advertiser must
# choose intentionally (mirrors AD.4 CPS hint pattern).
NOTIFICATION_CPD_BY_CATEGORY_CENTS = {
    "food":                                      8,
    "beverage":                                8,
    "restaurant":                            8,
    "cafe":                                        8,
    "coffee":                                    8,
    "retail":                                    12,
    "entertainment":                      15,
    "nightlife":                              15,
    "club":                                        15,
    "bar":                                          15,
    "health":                                    10,
    "fitness":                                  10,
    "gym":                                        10,
    "services":                                10,
    "salon":                                    10,
    "spa":                                        10,
    "auto":                                        10,
    "home_services":                      10,
    "home":                                        10,
}
NOTIFICATION_DEFAULT_CPD_CENTS = 10

# Same shape as CATEGORY_GROUPS above so the wizard tooltip can render
# a "Learn more" popover with the same UX.
NOTIFICATION_CPD_GROUPS = [
    {"label": "Food & Beverage",              "tags": ["food", "beverage", "restaurant", "cafe", "coffee"], "cents":  8},
    {"label": "Retail",                                "tags": ["retail"],                                                                                "cents": 12},
    {"label": "Entertainment / Nightlife",  "tags": ["entertainment", "nightlife", "club", "bar"],        "cents": 15},
    {"label": "Health & Fitness",                "tags": ["health", "fitness", "gym"],                                              "cents": 10},
    {"label": "Services",                              "tags": ["services", "salon", "spa"],                                          "cents": 10},
    {"label": "Auto / Home Services",          "tags": ["auto", "home_services", "home"],                                "cents": 10},
    {"label": "Default (unspecified)",          "tags": [],                                                                                        "cents": NOTIFICATION_DEFAULT_CPD_CENTS},
]


def suggest_notification_cpd_cents(category_tags) -> int:
    """Return the recommended CPD for a list of tags.  First match wins."""
    if not category_tags:
        return NOTIFICATION_DEFAULT_CPD_CENTS
    if isinstance(category_tags, str):
        category_tags = [category_tags]
    for tag in category_tags:
        if not isinstance(tag, str):
            continue
        c = NOTIFICATION_CPD_BY_CATEGORY_CENTS.get(tag.strip().lower())
        if c:
            return c
    return NOTIFICATION_DEFAULT_CPD_CENTS


# Phase AD.3 — Advertiser Predict & Win Sponsorship recommended pricing.
# Cost-per-Entry (CPE) is the primary model.  CPI is Cost-per-Correct-
# Impression (fires when the user sees a correct-answer surface).
PW_SPONSORSHIP_CPE_CENTS = {
    "default":                          20,       # $0.20
    "high_volume":                  35,       # Super Bowl-tier events
    "niche":                              10,       # low-volume markets
}
PW_SPONSORSHIP_CPI_CENTS = {
    "default":                          5,        # $0.05
    "high_volume":                  10,
    "niche":                              3,
}
PW_SPONSORSHIP_DEFAULT_CPE = 20
PW_SPONSORSHIP_DEFAULT_CPI = 5

PW_SPONSORSHIP_TIERS = [
    {"tier": "default",          "label": "Standard event",
      "cpe": PW_SPONSORSHIP_CPE_CENTS["default"],
      "cpi": PW_SPONSORSHIP_CPI_CENTS["default"]},
    {"tier": "high_volume",  "label": "High-volume event (e.g. Super Bowl)",
      "cpe": PW_SPONSORSHIP_CPE_CENTS["high_volume"],
      "cpi": PW_SPONSORSHIP_CPI_CENTS["high_volume"]},
    {"tier": "niche",              "label": "Niche / low-volume market",
      "cpe": PW_SPONSORSHIP_CPE_CENTS["niche"],
      "cpi": PW_SPONSORSHIP_CPI_CENTS["niche"]},
]


def suggest_cps_cents(category_tags) -> int:
    """Return the recommended CPS for a list of tags.  First match wins,
    otherwise the default kicks in.  Case-insensitive."""
    if not category_tags:
        return DEFAULT_CPS_CENTS
    if isinstance(category_tags, str):
        category_tags = [category_tags]
    for tag in category_tags:
        if not isinstance(tag, str):
            continue
        c = CATEGORY_HINTS_CENTS.get(tag.strip().lower())
        if c:
            return c
    return DEFAULT_CPS_CENTS


def hints_payload() -> Dict[str, object]:
    """Public shape for the frontend."""
    return {
        "default_cents": DEFAULT_CPS_CENTS,
        "categories":      CATEGORY_HINTS_CENTS,
        "groups":            CATEGORY_GROUPS,
        # Phase AD.11 — banner-specific pricing published on the same
        # public endpoint so the wizard's step 4 can pre-fill CPMs.
        "banner_zone_cpm_cents":      BANNER_ZONE_CPM_CENTS,
        "banner_zone_dimensions":  BANNER_ZONE_DIMENSIONS,
        "banner_zones":                        BANNER_ZONES,
        # Phase AD.12 — notification-ad recommended CPD by category
        # (mirrors AD.4 CPS shape).  Wizard shows these as inline
        # tooltips — no auto-fill.
        "notification_cpd_by_category_cents": NOTIFICATION_CPD_BY_CATEGORY_CENTS,
        "notification_default_cpd_cents":            NOTIFICATION_DEFAULT_CPD_CENTS,
        "notification_cpd_groups":                          NOTIFICATION_CPD_GROUPS,
        # Phase AD.3 — Predict & Win sponsorship pricing.
        "pw_sponsorship_default_cpe_cents":  PW_SPONSORSHIP_DEFAULT_CPE,
        "pw_sponsorship_default_cpi_cents":  PW_SPONSORSHIP_DEFAULT_CPI,
        "pw_sponsorship_tiers":                              PW_SPONSORSHIP_TIERS,
    }


__all__ = ["suggest_cps_cents", "suggest_notification_cpd_cents",
                    "hints_payload",
                    "CATEGORY_HINTS_CENTS", "CATEGORY_GROUPS", "DEFAULT_CPS_CENTS",
                    "BANNER_ZONE_CPM_CENTS", "BANNER_ZONE_DIMENSIONS", "BANNER_ZONES",
                    "NOTIFICATION_CPD_BY_CATEGORY_CENTS",
                    "NOTIFICATION_DEFAULT_CPD_CENTS",
                    "NOTIFICATION_CPD_GROUPS",
                    "PW_SPONSORSHIP_DEFAULT_CPE", "PW_SPONSORSHIP_DEFAULT_CPI",
                    "PW_SPONSORSHIP_TIERS",
                    "PW_SPONSORSHIP_CPE_CENTS", "PW_SPONSORSHIP_CPI_CENTS"]
