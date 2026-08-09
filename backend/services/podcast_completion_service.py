"""Phase G — AD.9 Podcast Completion Points.

Advertisers create campaigns that award BigCoin points or dollar-off
vouchers to listeners who finish (≥90%) a podcast episode.  A campaign
optionally targets a specific podcast or episode; leave both null for
a global "any podcast completion" campaign.

Flow:
1. Advertiser POSTs a draft campaign + expected budget
    (cost_per_completion × max_total_completions).
2. Server creates a Stripe test-mode PaymentIntent for the total
    budget (advertiser pays RadioLife directly — no external merchant).
3. Advertiser POSTs `.../confirm-payment` after Stripe confirmation.
4. If budget ≥ $500, campaign flips to `pending_admin`; else it
    flips directly to `active`.
5. Every `podcast_completed` event runs
    `podcast_completion_award_pipeline.on_podcast_completed()` which:
      - finds matching active campaigns,
      - honors per-user + global caps,
      - decrements `remaining_budget_cents`,
      - awards via `PointsService` (bigcoin) OR mints a coupon (usd),
      - dispatches `podcast_completion_awarded` notification.
6. Cancel refunds remaining budget via Stripe.

The event pipeline lives in `podcast_completion_award_pipeline.py` for
separation of concerns (this file is CRUD; that file is the reactor).
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.ad9.podcast_completion")


# ── Constants ─────────────────────────────────────────────
ADMIN_APPROVAL_THRESHOLD_CENTS = 50_000    # $500.00 total budget.
STATUS_ACTIVE = ("active", "paused")
STATUS_TERMINAL = ("completed", "cancelled")
DEFAULT_CURRENCY = "usd"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _iso(v):
    if isinstance(v, datetime):
        return _aware(v).isoformat()
    return v


# ── Indexes ───────────────────────────────────────────────
async def ensure_podcast_completion_indexes(db) -> None:
    try:
        await db.podcast_completion_campaigns.create_index(
            "id", unique=True, name="pcc_id_uniq")
        await db.podcast_completion_campaigns.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="pcc_adv_status")
        await db.podcast_completion_campaigns.create_index(
            [("podcast_id", 1), ("status", 1), ("start_at", 1)],
            name="pcc_podcast_status_start")
        await db.podcast_completion_campaigns.create_index(
            [("episode_id", 1), ("status", 1)], name="pcc_episode_status",
            sparse=True)

        await db.podcast_completion_awards.create_index(
            "id", unique=True, name="pca_id_uniq")
        await db.podcast_completion_awards.create_index(
            [("campaign_id", 1), ("user_id", 1), ("episode_id", 1)],
            unique=True, name="pca_dedupe")
        await db.podcast_completion_awards.create_index(
            [("user_id", 1), ("awarded_at", -1)], name="pca_user_time")
        await db.podcast_completion_awards.create_index(
            [("campaign_id", 1), ("awarded_at", -1)],
            name="pca_campaign_time")
    except Exception as e:
        logger.warning("[ad9] index setup: %s", e)


# ── Serialisation ─────────────────────────────────────
def _shape_campaign(c: Dict[str, Any],
                                          include_stripe: bool = True) -> Dict[str, Any]:
    out = {
        "campaign_id":                            c.get("id"),
        "advertiser_business_id":        c.get("advertiser_business_id"),
        "podcast_id":                              c.get("podcast_id"),
        "episode_id":                              c.get("episode_id"),
        "points_reward":                        int(c.get("points_reward") or 0),
        "currency":                                  (c.get("currency") or DEFAULT_CURRENCY),
        "sponsor_message":                    c.get("sponsor_message") or "",
        "max_completions_per_user":  int(c.get("max_completions_per_user") or 1),
        "max_total_completions":          int(c.get("max_total_completions") or 0),
        "start_at":                                  _iso(c.get("start_at")),
        "end_at":                                      _iso(c.get("end_at")),
        "status":                                      c.get("status"),
        "cost_per_completion_cents":  int(c.get("cost_per_completion_cents") or 0),
        "total_budget_cents":                int(c.get("total_budget_cents") or 0),
        "remaining_budget_cents":        int(c.get("remaining_budget_cents") or 0),
        "awarded_count":                        int(c.get("awarded_count") or 0),
        "created_at":                              _iso(c.get("created_at")),
        "activated_at":                          _iso(c.get("activated_at")),
        "completed_at":                          _iso(c.get("completed_at")),
        "cancelled_at":                          _iso(c.get("cancelled_at")),
        "admin_approval_required":      bool(c.get("admin_approval_required")),
    }
    if include_stripe:
        out["stripe_payment_intent_id"] = c.get("stripe_payment_intent_id")
        out["stripe_prepayment_transaction_id"] = c.get(
            "stripe_prepayment_transaction_id")
        out["stripe_refund_id"] = c.get("stripe_refund_id")
        out["decision_note"] = c.get("decision_note")
    return out


def _shape_award(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "award_id":                          a.get("id"),
        "campaign_id":                    a.get("campaign_id"),
        "user_id":                            a.get("user_id"),
        "podcast_id":                      a.get("podcast_id"),
        "episode_id":                      a.get("episode_id"),
        "points_awarded":                int(a.get("points_awarded") or 0),
        "currency":                          a.get("currency"),
        "advertiser_charge_cents":  int(a.get("advertiser_charge_cents") or 0),
        "wallet_item_id":                a.get("wallet_item_id"),
        "wallet_item_type":            a.get("wallet_item_type"),
        "sponsor_message":              a.get("sponsor_message"),
        "advertiser_business_id":  a.get("advertiser_business_id"),
        "awarded_at":                      _iso(a.get("awarded_at")),
    }


# ── Stripe helpers ───────────────────────────────────
async def _charge_prepayment(*, amount_cents: int, currency: str,
                                                          campaign_id: str,
                                                          advertiser_business_id: str
                                                          ) -> Dict[str, Any]:
    """Create + confirm a Stripe test-mode PaymentIntent for the total
    budget.  Advertiser pays RadioLife directly (no `transfer_data`).

    Note: `currency` refers to the REWARD currency on the campaign
    ("bc" for BigCoin or "usd" for dollar-off vouchers).  The Stripe
    charge itself is always in USD — advertisers pay the platform in
    real money regardless of what the listener receives."""
    stripe_currency = "usd"    # advertiser always pays USD to the platform
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        intent = _stripe.PaymentIntent.create(
            amount=int(amount_cents),
            currency=stripe_currency,
            payment_method_types=["card"],
            payment_method="pm_card_visa",
            confirm=True,
            metadata={
                "bigfm_flow":                            "ad9_pc_prepay",
                "bigfm_campaign_id":              campaign_id,
                "bigfm_advertiser_id":            advertiser_business_id,
                "bigfm_reward_currency":      currency,
            },
            idempotency_key=f"ad9_pc_prepay_{campaign_id}")
        return {"payment_intent_id": intent.id,
                        "charge_id":                getattr(intent, "latest_charge", None) or "",
                        "amount_cents":        int(amount_cents),
                        "status":                  intent.status}
    except Exception as e:
        logger.exception("[ad9] stripe prepay failed")
        raise ValueError(f"stripe_error:{e}")


async def _refund_remaining(*, payment_intent_id: str,
                                                        refund_cents: int, campaign_id: str
                                                        ) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        refund = _stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=int(refund_cents),
            metadata={"bigfm_flow": "ad9_pc_refund",
                                "bigfm_campaign_id": campaign_id},
            idempotency_key=f"ad9_pc_refund_{campaign_id}")
        return {"refund_id": refund.id, "amount_cents": int(refund_cents),
                        "status": refund.status}
    except Exception as e:
        logger.exception("[ad9] stripe refund failed")
        raise ValueError(f"stripe_error:{e}")


# ── Campaign CRUD ────────────────────────────────────
async def create_campaign(db, *,
                                                    advertiser_business_id: str,
                                                    body: Dict[str, Any],
                                                    user_id: str) -> Dict[str, Any]:
    points = int(body.get("points_reward") or 0)
    if points <= 0:
        raise ValueError("points_reward_required")
    max_total = int(body.get("max_total_completions") or 0)
    if max_total <= 0:
        raise ValueError("max_total_completions_required")
    cost = int(body.get("cost_per_completion_cents") or 0)
    if cost <= 0:
        raise ValueError("cost_per_completion_cents_required")
    start = _aware(body.get("start_at"))
    end   = _aware(body.get("end_at"))
    if not (start and end) or end <= start:
        raise ValueError("invalid_time_window")
    if int(body.get("max_completions_per_user") or 1) < 1:
        raise ValueError("invalid_max_per_user")

    total_budget = cost * max_total
    campaign_id = _gen("pcc")
    now = _now()
    currency = (body.get("currency") or DEFAULT_CURRENCY).lower()
    if currency not in ("bc", "usd"):
        raise ValueError("invalid_currency")

    doc = {
        "_id":                                        campaign_id,
        "id":                                          campaign_id,
        "advertiser_business_id":        advertiser_business_id,
        "podcast_id":                              (body.get("podcast_id") or None),
        "episode_id":                              (body.get("episode_id") or None),
        "points_reward":                        points,
        "currency":                                  currency,
        "sponsor_message":                    (body.get("sponsor_message") or "")[:200],
        "max_completions_per_user":  int(body.get("max_completions_per_user") or 1),
        "max_total_completions":          max_total,
        "start_at":                                  start,
        "end_at":                                      end,
        "status":                                      "draft",
        "cost_per_completion_cents":  cost,
        "total_budget_cents":                total_budget,
        "remaining_budget_cents":        total_budget,
        "awarded_count":                        0,
        "created_at":                              now,
        "created_by_user_id":                user_id,
        "admin_approval_required":      total_budget >= ADMIN_APPROVAL_THRESHOLD_CENTS,
    }
    await db.podcast_completion_campaigns.insert_one(doc)
    return _shape_campaign(doc)


async def confirm_payment(db, *,
                                                    campaign_id: str,
                                                    advertiser_business_id: str
                                                    ) -> Dict[str, Any]:
    """Charge Stripe for the total budget, then flip to `active` (or
    `pending_admin` if over threshold)."""
    c = await db.podcast_completion_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if c["status"] != "draft":
        raise ValueError(f"campaign_{c['status']}")

    charge = await _charge_prepayment(
        amount_cents=int(c["total_budget_cents"]),
        currency=c.get("currency") or DEFAULT_CURRENCY,
        campaign_id=campaign_id,
        advertiser_business_id=advertiser_business_id)

    tx_id = _gen("tx_pcc")
    await db.payment_transactions_v2.insert_one({
        "_id":                                        tx_id,
        "transaction_id":                    tx_id,
        "stripe_payment_intent_id":  charge["payment_intent_id"],
        "flow":                                      "ad9_pc_prepay",
        "event_source":                        "podcast_completion_prepay",
        "advertiser_id":                      advertiser_business_id,
        "bigfm_campaign_id":                campaign_id,
        "amount_cents":                        int(c["total_budget_cents"]),
        "application_fee_cents":        0,
        "merchant_net_cents":              0,
        "currency":                                c.get("currency") or DEFAULT_CURRENCY,
        "status":                                    "posted",
        "created_at":                            _now(),
    })

    new_status = ("pending_admin"
                                  if c.get("admin_approval_required")
                                  else "active")
    now = _now()
    upd: Dict[str, Any] = {
        "status":                                        new_status,
        "stripe_payment_intent_id":        charge["payment_intent_id"],
        "stripe_prepayment_transaction_id": tx_id,
        "paid_at":                                    now,
    }
    if new_status == "active":
        upd["activated_at"] = now
    await db.podcast_completion_campaigns.update_one(
        {"id": campaign_id}, {"$set": upd})

    row = await db.podcast_completion_campaigns.find_one({"id": campaign_id})
    return {"campaign": _shape_campaign(row),
                    "charge": charge,
                    "transaction_id": tx_id}


async def list_campaigns(db, *,
                                                advertiser_business_id: Optional[str] = None,
                                                status: Optional[str] = None,
                                                limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    out: List[Dict[str, Any]] = []
    async for c in db.podcast_completion_campaigns.find(q)\
                                                        .sort("created_at", -1).limit(limit):
        out.append(_shape_campaign(c))
    return out


async def get_campaign(db, *, campaign_id: str,
                                              advertiser_business_id: Optional[str] = None,
                                              is_admin: bool = False
                                              ) -> Optional[Dict[str, Any]]:
    c = await db.podcast_completion_campaigns.find_one({"id": campaign_id})
    if not c:
        return None
    if (not is_admin) and advertiser_business_id \
            and c["advertiser_business_id"] != advertiser_business_id:
        return {"forbidden": True}
    # Top episodes stats (last 30 days).
    top_episodes: List[Dict[str, Any]] = []
    pipe = [
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": "$episode_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    async for r in db.podcast_completion_awards.aggregate(pipe):
        top_episodes.append({"episode_id": r["_id"],
                                                  "award_count": int(r["count"])})
    return {"campaign": _shape_campaign(c),
                    "top_episodes": top_episodes}


async def patch_campaign(db, *,
                                                campaign_id: str,
                                                advertiser_business_id: str,
                                                patch: Dict[str, Any]) -> Dict[str, Any]:
    c = await db.podcast_completion_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    # Only status transitions allowed after activation.
    new_status = patch.get("status")
    if new_status:
        if new_status not in ("active", "paused"):
            raise ValueError("invalid_status_transition")
        if c["status"] not in ("active", "paused"):
            raise ValueError(f"campaign_{c['status']}")
        await db.podcast_completion_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"status": new_status, "updated_at": _now()}})
    # Sponsor message can be edited any time before terminal.
    if "sponsor_message" in patch:
        if c["status"] in STATUS_TERMINAL:
            raise ValueError(f"campaign_{c['status']}")
        await db.podcast_completion_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"sponsor_message": (patch.get("sponsor_message") or "")[:200],
                              "updated_at": _now()}})
    return _shape_campaign(
        await db.podcast_completion_campaigns.find_one({"id": campaign_id}))


async def cancel_campaign(db, *,
                                                    campaign_id: str,
                                                    advertiser_business_id: str,
                                                    reason: Optional[str] = None
                                                    ) -> Dict[str, Any]:
    c = await db.podcast_completion_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if c["status"] in STATUS_TERMINAL:
        raise ValueError(f"campaign_{c['status']}")

    refund: Optional[Dict[str, Any]] = None
    remaining = int(c.get("remaining_budget_cents") or 0)
    if c.get("stripe_payment_intent_id") and remaining > 0:
        refund = await _refund_remaining(
            payment_intent_id=c["stripe_payment_intent_id"],
            refund_cents=remaining, campaign_id=campaign_id)

    now = _now()
    upd = {
        "status":              "cancelled",
        "cancelled_at":  now,
        "cancel_reason": reason,
    }
    if refund:
        upd["stripe_refund_id"]                          = refund["refund_id"]
        upd["refunded_amount_cents"]              = refund["amount_cents"]
        upd["remaining_budget_cents"]              = 0
    await db.podcast_completion_campaigns.update_one(
        {"id": campaign_id}, {"$set": upd})

    return {"campaign": _shape_campaign(
                          await db.podcast_completion_campaigns.find_one({"id": campaign_id})),
                    "refund": refund}


# ── Admin approval ───────────────────────────────────
async def admin_approve(db, *, campaign_id: str,
                                              admin_user_id: str,
                                              decision_note: Optional[str] = None
                                              ) -> Dict[str, Any]:
    c = await db.podcast_completion_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["status"] != "pending_admin":
        raise ValueError(f"campaign_{c['status']}")
    now = _now()
    await db.podcast_completion_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": "active", "activated_at": now,
                          "decision_note": decision_note,
                          "decided_by_user_id": admin_user_id,
                          "decided_at": now}})
    return _shape_campaign(
        await db.podcast_completion_campaigns.find_one({"id": campaign_id}))


async def admin_reject(db, *, campaign_id: str,
                                            admin_user_id: str,
                                            decision_note: Optional[str] = None
                                            ) -> Dict[str, Any]:
    c = await db.podcast_completion_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["status"] != "pending_admin":
        raise ValueError(f"campaign_{c['status']}")
    # Full refund since campaign never went live.
    refund: Optional[Dict[str, Any]] = None
    remaining = int(c.get("remaining_budget_cents") or 0)
    if c.get("stripe_payment_intent_id") and remaining > 0:
        refund = await _refund_remaining(
            payment_intent_id=c["stripe_payment_intent_id"],
            refund_cents=remaining, campaign_id=campaign_id)
    now = _now()
    upd = {
        "status":                    "cancelled",
        "cancelled_at":        now,
        "cancel_reason":      "admin_rejected",
        "decision_note":      decision_note,
        "decided_by_user_id": admin_user_id,
        "decided_at":            now,
    }
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
        upd["remaining_budget_cents"]      = 0
    await db.podcast_completion_campaigns.update_one(
        {"id": campaign_id}, {"$set": upd})
    return {"campaign": _shape_campaign(
                          await db.podcast_completion_campaigns.find_one({"id": campaign_id})),
                    "refund": refund}


# ── Award listing ────────────────────────────────────
async def list_awards_for_campaign(db, *, campaign_id: str,
                                                                          limit: int = 100
                                                                          ) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    async for a in db.podcast_completion_awards.find({"campaign_id": campaign_id})\
                                                                                        .sort("awarded_at", -1).limit(limit):
        out.append(_shape_award(a))
    return out


async def list_awards_for_user(db, *, user_id: str,
                                                              limit: int = 50
                                                              ) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    async for a in db.podcast_completion_awards.find({"user_id": user_id})\
                                                                                        .sort("awarded_at", -1).limit(limit):
        out.append(_shape_award(a))
    return out


__all__ = [
    "ensure_podcast_completion_indexes",
    "create_campaign", "confirm_payment", "list_campaigns", "get_campaign",
    "patch_campaign", "cancel_campaign",
    "admin_approve", "admin_reject",
    "list_awards_for_campaign", "list_awards_for_user",
    "ADMIN_APPROVAL_THRESHOLD_CENTS",
    "_shape_campaign", "_shape_award",
]
