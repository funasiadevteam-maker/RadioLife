"""Phase SC.2 — Merchant status service.

Combines the admin-decision layer (`merchant_status`) with the Stripe-Connect
onboarding reality (`stripe_onboarding_status`) into a single effective enum
that the frontend + admin panel can render.

Admin layer values (`merchant_status`):
    draft                                    — wizard started, some steps incomplete
    stripe_onboarding_pending — awaiting the merchant to finish Stripe hosted flow
    verification_pending             — Stripe finished but has open requirements
    submitted                            — merchant clicked "Submit for approval"
    approved                              — admin approved (Stripe still needs to be `active`
                                                        before the merchant can transact)
    active                                    — approved AND Stripe.charges_enabled+payouts_enabled
    restricted                          — either admin flagged OR Stripe restricted
    payouts_disabled                — Stripe blocking payouts
    suspended                          — admin suspended the merchant post-approval
    rejected                              — admin rejected the application

`derive_effective_status()` is the single source of truth for the pill you
see in the admin table.  It's the merchant_status EXCEPT when Stripe reality
overrides it (e.g. approved but Stripe restricted → surface "restricted").
"""
from __future__ import annotations

from typing import Optional


MERCHANT_STATUSES = {
    "draft",
    "stripe_onboarding_pending",
    "verification_pending",
    "submitted",
    "approved",
    "active",
    "restricted",
    "payouts_disabled",
    "suspended",
    "rejected",
}

# Sub-statuses that always eclipse `approved` because they represent
# adverse Stripe reality that only the merchant / Stripe can resolve.
_STRIPE_OVERRIDES = {"restricted", "payouts_disabled", "rejected"}


def derive_effective_status(merchant: dict,
                                            stripe_status: Optional[str] = None) -> str:
    """Return the single enum value the UI should surface for this merchant.

    Priority order:
      1. admin `suspended` / `rejected` always win — they represent an
          explicit human decision that we don't want silently overridden.
      2. Stripe-adverse states (`restricted`, `payouts_disabled`, `rejected`)
          override an `approved` merchant so the admin sees the truth.
      3. `approved` + Stripe `active` → `active`.
      4. `approved` alone (Stripe not yet active) → keep `approved`.
      5. Otherwise return `merchant_status` (or `draft` when unset).
    """
    ms = (merchant.get("merchant_status") or "draft").strip()
    stripe_status = (stripe_status
        or merchant.get("stripe_onboarding_status")
        or "not_started")

    if ms in ("suspended", "rejected"):
        return ms

    if ms == "approved":
        if stripe_status in _STRIPE_OVERRIDES:
            return stripe_status
        if stripe_status == "active":
            return "active"
        return "approved"

    if ms == "submitted" and stripe_status in _STRIPE_OVERRIDES:
        return stripe_status

    return ms if ms in MERCHANT_STATUSES else "draft"


# ─── Wizard step gating ───────────────────────────────────────────
WIZARD_STEPS = [
    "welcome",              # 1 · name + category
    "profile",              # 2 · description + phone + website
    "locations",          # 3 · Google Places Autocomplete
    "logo",                    # 4 · Tigris upload
    "photos",                # 5 · up to 6 (skippable)
    "hours",                  # 6 · 7-day picker
    "terms",                  # 7 · commission terms accept
    "stripe",                # 8 · SC.1 hosted onboarding
    "review",                # 9 · submit for approval
]


def next_step(merchant: dict) -> str:
    """Return the string id of the next incomplete step for a `draft` merchant.
    Used by the wizard to resume where the merchant left off."""
    if not (merchant.get("name") and merchant.get("category_id")):
        return "welcome"
    # `description` is required; phone + website are optional to submit
    if not merchant.get("description"):
        return "profile"
    if not merchant.get("_has_primary_location"):
        # This flag is set by the loader — see routes/merchant_onboarding.py
        return "locations"
    if not merchant.get("logo_url"):
        return "logo"
    # Photos are skippable — advance if the merchant hasn't touched hours yet
    if not merchant.get("hours"):
        return "hours"
    if not merchant.get("commission_terms_accepted"):
        return "terms"
    if not merchant.get("stripe_account_id"):
        return "stripe"
    return "review"


def step_index(step_id: str) -> int:
    """1-based index for the wizard progress bar."""
    try:
        return WIZARD_STEPS.index(step_id) + 1
    except ValueError:
        return 1


def is_ready_for_submission(merchant: dict) -> tuple[bool, list[str]]:
    """Validate all required data is present before flipping to `submitted`.
    Returns (ok, missing_fields)."""
    missing: list[str] = []
    if not merchant.get("name"):
        missing.append("name")
    if not merchant.get("category_id"):
        missing.append("category_id")
    if not merchant.get("description"):
        missing.append("description")
    if not merchant.get("_has_primary_location"):
        missing.append("primary_location")
    if not merchant.get("logo_url"):
        missing.append("logo_url")
    if not merchant.get("hours"):
        missing.append("hours")
    if not merchant.get("commission_terms_accepted"):
        missing.append("commission_terms_accepted")
    if not merchant.get("stripe_account_id"):
        missing.append("stripe_account_id")
    return (len(missing) == 0, missing)


__all__ = [
    "MERCHANT_STATUSES",
    "WIZARD_STEPS",
    "derive_effective_status",
    "next_step",
    "step_index",
    "is_ready_for_submission",
]
