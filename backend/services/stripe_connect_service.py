"""Phase SC.1 — Stripe Connect Standard-account service.

Thin async wrapper around the (synchronous) `stripe` Python SDK.  Handles
connected-account creation, hosted onboarding via Account Links, status
retrieval, dashboard-login links.

Design notes
------------
* Uses `STRIPE_SECRET_KEY` from env (never exposed to the frontend).
* Independent from the pre-existing Checkout integration (`services/
  advertisers.py`, `services/stripe_client.py`) — no shared state,
  no monkey-patched globals.
* Every call runs in a thread-pool via `asyncio.to_thread` so the
  FastAPI event loop stays responsive.
* Errors bubble up as `stripe.error.StripeError` — callers wrap in
  HTTPException.  No swallowing.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import stripe  # already installed by the Checkout integration

logger = logging.getLogger("bigfm.stripe_connect")


def _configure() -> None:
    """Set api_key from env on every call — safe against monkey-patching
    by other stripe callers in the codebase."""
    key = (os.environ.get("STRIPE_SECRET_KEY")
              or os.environ.get("STRIPE_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not set")
    stripe.api_key = key


async def create_transfer(*, amount_cents: int, destination_account_id: str,
                          source_transaction: Optional[str] = None,
                          transfer_group: Optional[str] = None,
                          metadata: Optional[dict] = None,
                          idempotency_key: Optional[str] = None) -> dict:
    """Separate-charges-and-transfers payout leg. Moves `amount_cents` from the
    platform balance to a connected account. `source_transaction` (the original
    platform charge id) lets a DEFERRED transfer draw from that specific charge
    so it never fails for insufficient available balance. Idempotent."""
    _configure()

    def _sync():
        kwargs: dict[str, Any] = {"amount": int(amount_cents), "currency": "usd",
                                  "destination": destination_account_id}
        if source_transaction:
            kwargs["source_transaction"] = source_transaction
        if transfer_group:
            kwargs["transfer_group"] = transfer_group
        if metadata:
            kwargs["metadata"] = metadata
        opts = {"idempotency_key": idempotency_key} if idempotency_key else {}
        return stripe.Transfer.create(**kwargs, **opts)

    tr = await asyncio.to_thread(_sync)
    return {"transfer_id": tr.id, "amount": tr.amount, "destination": tr.destination}


async def reverse_transfer(*, transfer_id: str, amount_cents: Optional[int] = None,
                           idempotency_key: Optional[str] = None) -> dict:
    """Reverse a prior transfer (e.g. redemption voided/refunded)."""
    _configure()

    def _sync():
        kwargs: dict[str, Any] = {}
        if amount_cents is not None:
            kwargs["amount"] = int(amount_cents)
        opts = {"idempotency_key": idempotency_key} if idempotency_key else {}
        return stripe.Transfer.create_reversal(transfer_id, **kwargs, **opts)

    rev = await asyncio.to_thread(_sync)
    return {"reversal_id": rev.id, "amount": rev.amount}


# ─── Status derivation ─────────────────────────────────────────────
VALID_STATUSES = {
    "not_started", "onboarding_in_progress", "onboarding_incomplete",
    "verification_pending", "active", "restricted",
    "payouts_disabled", "rejected",
}


def derive_onboarding_status(*, charges_enabled: bool, payouts_enabled: bool,
                                              details_submitted: bool,
                                              requirements_currently_due: list,
                                              requirements_past_due: list,
                                              requirements_disabled_reason: Optional[str],
                                              current_status: str = "not_started") -> str:
    """Fold Stripe account fields into a single onboarding-status enum.

    Precedence order matches the SC.1 brief:
      restricted > rejected > payouts_disabled > active >
      verification_pending > onboarding_incomplete > current_status
    """
    if requirements_disabled_reason:
        # Stripe restricts accounts when compliance issues surface.
        if "rejected" in requirements_disabled_reason:
            return "rejected"
        return "restricted"
    if details_submitted and charges_enabled and payouts_enabled:
        return "active"
    if details_submitted and charges_enabled and not payouts_enabled:
        return "payouts_disabled"
    if details_submitted and (requirements_currently_due or requirements_past_due):
        return "verification_pending"
    if not details_submitted:
        # Merchant hasn't finished the hosted-onboarding flow yet.
        # Preserve "onboarding_in_progress" if that's what we already
        # have; otherwise mark as incomplete.
        if current_status == "onboarding_in_progress":
            return "onboarding_in_progress"
        return "onboarding_incomplete"
    return current_status


# ─── Service methods ───────────────────────────────────────────────
async def create_connected_account(*, merchant_id: str, email: str,
                                                          country: str = "US") -> dict:
    """Create a new Stripe Connect Standard account for a merchant.
    Returns { stripe_account_id, created }.
    """
    _configure()

    def _sync():
        return stripe.Account.create(
            type="standard",
            email=email,
            country=country,
            metadata={"merchant_id": merchant_id, "source": "bigfm_sc1"},
        )

    acct = await asyncio.to_thread(_sync)
    logger.info(f"[connect] created acct={acct.id} for merchant_id={merchant_id}")
    return {"stripe_account_id": acct.id, "created": acct.created}


async def create_onboarding_link(*, stripe_account_id: str,
                                                  return_url: str, refresh_url: str) -> str:
    """Generate a hosted onboarding URL (Account Link).  URLs are single-
    use — the merchant must complete or start-over within a few minutes."""
    _configure()

    def _sync():
        return stripe.AccountLink.create(
            account=stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )

    link = await asyncio.to_thread(_sync)
    return link.url


async def retrieve_account_status(stripe_account_id: str) -> dict:
    """Fetch the live account status from Stripe and normalise the shape."""
    _configure()

    def _sync():
        return stripe.Account.retrieve(stripe_account_id)

    acct = await asyncio.to_thread(_sync)
    reqs = getattr(acct, "requirements", None) or {}
    caps = getattr(acct, "capabilities", None) or {}
    return {
        "stripe_account_id": acct.id,
        "charges_enabled": bool(getattr(acct, "charges_enabled", False)),
        "payouts_enabled": bool(getattr(acct, "payouts_enabled", False)),
        "details_submitted": bool(getattr(acct, "details_submitted", False)),
        "requirements_currently_due": list(getattr(reqs, "currently_due", None)
                                                    or reqs.get("currently_due", []) or []),
        "requirements_past_due": list(getattr(reqs, "past_due", None)
                                                or reqs.get("past_due", []) or []),
        "requirements_disabled_reason": (getattr(reqs, "disabled_reason", None)
                                                        or reqs.get("disabled_reason")),
        "capabilities": dict(caps) if hasattr(caps, "keys") else (caps or {}),
        "country": getattr(acct, "country", None),
        "default_currency": getattr(acct, "default_currency", None),
        "email": getattr(acct, "email", None),
        "type": getattr(acct, "type", None),
    }


async def refresh_account_status(*, stripe_account_id: str,
                                                  merchant_id: str, db,
                                                  filter_by: str = "business_id") -> dict:
    """Refresh live status AND persist to the merchant document.
    Returns the full status object (as retrieve_account_status shape) plus
    the derived `stripe_onboarding_status` enum.

    `filter_by` selects the field used to locate the merchant document —
    defaults to `business_id`; callers can pass `"_id"` for rows that
    lack a `business_id`.
    """
    from datetime import datetime, timezone
    live = await retrieve_account_status(stripe_account_id)
    biz = await db.businesses.find_one(
        {filter_by: merchant_id}, {"stripe_onboarding_status": 1})
    current_status = (biz or {}).get("stripe_onboarding_status") or "not_started"
    onboarding_status = derive_onboarding_status(
        charges_enabled=live["charges_enabled"],
        payouts_enabled=live["payouts_enabled"],
        details_submitted=live["details_submitted"],
        requirements_currently_due=live["requirements_currently_due"],
        requirements_past_due=live["requirements_past_due"],
        requirements_disabled_reason=live["requirements_disabled_reason"],
        current_status=current_status,
    )
    now = datetime.now(timezone.utc)
    await db.businesses.update_one(
        {filter_by: merchant_id},
        {"$set": {
            "stripe_account_id": stripe_account_id,
            "stripe_charges_enabled": live["charges_enabled"],
            "stripe_payouts_enabled": live["payouts_enabled"],
            "stripe_details_submitted": live["details_submitted"],
            "stripe_requirements_currently_due": live["requirements_currently_due"],
            "stripe_requirements_past_due": live["requirements_past_due"],
            "stripe_requirements_disabled_reason": live["requirements_disabled_reason"],
            "stripe_capabilities": live["capabilities"],
            "stripe_onboarding_status": onboarding_status,
            "stripe_status_synced_at": now,
        }})
    return {**live, "stripe_onboarding_status": onboarding_status,
              "stripe_status_synced_at": now.isoformat()}


async def instant_payout_precheck(*, stripe_account_id: str,
                                  currency: str = "usd") -> dict:
    """Instant-payout eligibility + instant_available balance for a connected
    account. Never raises for expected states — returns ok=False + reason.
    Draws nothing; read-only."""
    _configure()
    cur = (currency or "usd").lower()

    def _sync():
        acct = stripe.Account.retrieve(stripe_account_id)
        if not bool(getattr(acct, "payouts_enabled", False)):
            return {"ok": False, "reason": "payouts_disabled"}
        bal = stripe.Balance.retrieve(stripe_account=stripe_account_id)
        avail = [x for x in (bal.get("available") or []) if x.get("currency") == cur]
        available = int(avail[0]["amount"]) if avail else 0
        inst = [x for x in (bal.get("instant_available") or []) if x.get("currency") == cur]
        instant_available = int(inst[0]["amount"]) if inst else 0
        ext = stripe.Account.list_external_accounts(stripe_account_id, limit=100)
        eligible = [x for x in (ext.get("data") or [])
                    if "instant" in (x.get("available_payout_methods") or [])]
        if not eligible:
            return {"ok": False, "reason": "no_instant_eligible_external_account",
                    "available": available, "instant_available": instant_available}
        if instant_available <= 0:
            return {"ok": False, "reason": "insufficient_instant_balance",
                    "available": available, "instant_available": instant_available}
        return {"ok": True, "available": available,
                "instant_available": instant_available, "destination": eligible[0]["id"]}

    return await asyncio.to_thread(_sync)


async def create_instant_payout(*, stripe_account_id: str, amount_cents: int,
                                currency: str = "usd",
                                idempotency_key: str) -> dict:
    """INSTANT payout from the connected account's OWN balance to its default
    external account (Stripe-Account header). Fees already taken upstream — this
    does not re-deduct. Raises stripe.StripeError (caller maps to a fallback)."""
    _configure()

    def _sync():
        return stripe.Payout.create(
            amount=int(amount_cents), currency=(currency or "usd").lower(),
            method="instant", stripe_account=stripe_account_id,
            idempotency_key=idempotency_key)

    p = await asyncio.to_thread(_sync)
    return {"payout_id": p.id, "status": p.status, "amount": p.amount,
            "currency": p.currency, "arrival_date": getattr(p, "arrival_date", None)}


async def create_login_link(stripe_account_id: str) -> str:
    """Return a URL the merchant can use to access their Stripe Express-lite
    dashboard (payouts, transaction history)."""
    _configure()

    def _sync():
        return stripe.Account.create_login_link(stripe_account_id)

    link = await asyncio.to_thread(_sync)
    return link.url


# ─── Startup migration ─────────────────────────────────────────────
SC1_DEFAULT_FIELDS: dict[str, Any] = {
    "stripe_account_id": None,
    "stripe_charges_enabled": False,
    "stripe_payouts_enabled": False,
    "stripe_details_submitted": False,
    "stripe_requirements_currently_due": [],
    "stripe_requirements_past_due": [],
    "stripe_requirements_disabled_reason": None,
    "stripe_capabilities": None,
    "stripe_onboarding_status": "not_started",
    "stripe_status_synced_at": None,
}


async def run_sc1_migration(db) -> int:
    """Additive migration — sets default Connect fields on any businesses
    doc that doesn't already have `stripe_onboarding_status`.  Idempotent.
    Returns the number of docs updated."""
    result = await db.businesses.update_many(
        {"stripe_onboarding_status": {"$exists": False}},
        {"$set": SC1_DEFAULT_FIELDS})
    if result.modified_count:
        logger.info(
            f"SC.1 migration: added Stripe Connect fields to "
            f"{result.modified_count} existing merchants")
    return result.modified_count


__all__ = [
    "create_connected_account",
    "create_onboarding_link",
    "retrieve_account_status",
    "refresh_account_status",
    "create_login_link",
    "instant_payout_precheck",
    "create_instant_payout",
    "derive_onboarding_status",
    "run_sc1_migration",
    "SC1_DEFAULT_FIELDS",
    "VALID_STATUSES",
]
