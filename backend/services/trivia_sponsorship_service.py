"""Phase H — AD.5 Trivia Sponsorship + Giveaway Redemption.

Advertisers sponsor trivia rooms (or question categories, or "any
room" fan-out) and fund a prize pool that winners can redeem.  Prize
pool supports multiple tiers (rank 1..N) or a score-threshold model.
Winners receive BigCoin points OR dollar-off vouchers — same
dual-currency pattern as Phase G's podcast completion rewards.

The runtime side (event reactor invoked from the trivia room state
machine's `done` transition) lives in
`services/trivia_sponsor_award_pipeline.py` — this file is CRUD +
Stripe + admin decisions only.

Data model:
 - trivia_sponsorships          — advertiser-created + prepaid.
 - trivia_sponsor_awards        — one row per (sponsorship, user, room).

The shipped Phase C model uses `trivia_categories.id` as the sole
targeting dimension — the spec's `question_set` target maps 1:1 to
`category` here (there is no shipped `trivia_question_sets` collection).
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.ad5.trivia_sponsorship")


ADMIN_APPROVAL_THRESHOLD_CENTS = 50_000     # $500.00 total budget
PLATFORM_FEE_PCT                              = 25          # 25% platform take
TARGET_TYPES                                    = ("question_set", "category", "any")
SELECTION_MODES                              = ("top_n", "score_threshold")
STATUS_TERMINAL                              = ("completed", "cancelled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _iso(v):
    return _aware(v).isoformat() if isinstance(v, datetime) else v


# ── Indexes ──────────────────────────────────────────
async def ensure_trivia_sponsorship_indexes(db) -> None:
    try:
        await db.trivia_sponsorships.create_index(
            "id", unique=True, name="ts_id_uniq")
        await db.trivia_sponsorships.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="ts_adv_status")
        await db.trivia_sponsorships.create_index(
            [("sponsor_target_type", 1), ("target_id", 1), ("status", 1),
              ("start_at", 1)], name="ts_target_status_start")

        await db.trivia_sponsor_awards.create_index(
            "id", unique=True, name="tsa_id_uniq")
        # Compound unique enforces idempotency — same (sponsorship, user,
        # room) can't award twice even if the pipeline is re-invoked.
        await db.trivia_sponsor_awards.create_index(
            [("sponsorship_id", 1), ("user_id", 1), ("room_code", 1)],
            unique=True, name="tsa_dedupe")
        await db.trivia_sponsor_awards.create_index(
            [("user_id", 1), ("awarded_at", -1)], name="tsa_user_time")
        await db.trivia_sponsor_awards.create_index(
            [("sponsorship_id", 1), ("awarded_at", -1)],
            name="tsa_sponsorship_time")
    except Exception as e:
        logger.warning("[ad5] index setup: %s", e)


# ── Serialisation ────────────────────────────────────
def _shape_sponsorship(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sponsorship_id":                        s.get("id"),
        "advertiser_business_id":            s.get("advertiser_business_id"),
        "sponsor_target_type":                s.get("sponsor_target_type"),
        "target_id":                                    s.get("target_id"),
        "display_name":                              s.get("display_name") or "",
        "tagline":                                      s.get("tagline") or "",
        "logo_url":                                    s.get("logo_url"),
        "prize_pool":                                s.get("prize_pool") or [],
        "winner_selection":                    s.get("winner_selection"),
        "score_threshold":                      s.get("score_threshold"),
        "start_at":                                    _iso(s.get("start_at")),
        "end_at":                                        _iso(s.get("end_at")),
        "status":                                        s.get("status"),
        "cost_cents":                                int(s.get("cost_cents") or 0),
        "platform_fee_cents":                  int(s.get("platform_fee_cents") or 0),
        "remaining_budget_cents":            int(s.get("remaining_budget_cents") or 0),
        "awarded_count":                          int(s.get("awarded_count") or 0),
        "max_total_awards":                    int(s.get("max_total_awards") or 0),
        "created_at":                                _iso(s.get("created_at")),
        "activated_at":                            _iso(s.get("activated_at")),
        "completed_at":                            _iso(s.get("completed_at")),
        "cancelled_at":                            _iso(s.get("cancelled_at")),
        "admin_approval_required":        bool(s.get("admin_approval_required")),
        "stripe_payment_intent_id":        s.get("stripe_payment_intent_id"),
        "stripe_prepayment_transaction_id": s.get(
            "stripe_prepayment_transaction_id"),
        "stripe_refund_id":                    s.get("stripe_refund_id"),
        "refunded_amount_cents":              int(s.get("refunded_amount_cents") or 0),
        "decision_note":                        s.get("decision_note"),
    }


def _shape_award(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "award_id":                            a.get("id"),
        "sponsorship_id":                a.get("sponsorship_id"),
        "room_code":                        a.get("room_code"),
        "user_id":                            a.get("user_id"),
        "user_name":                        a.get("user_name"),
        "rank":                                a.get("rank"),
        "score":                              a.get("score"),
        "points_awarded":                int(a.get("points_awarded") or 0),
        "currency":                          a.get("currency"),
        "wallet_item_id":                a.get("wallet_item_id"),
        "wallet_item_type":            a.get("wallet_item_type"),
        "redemption_status":          a.get("redemption_status") or "pending",
        "advertiser_business_id":  a.get("advertiser_business_id"),
        "advertiser_charge_cents":  int(a.get("advertiser_charge_cents") or 0),
        "awarded_at":                      _iso(a.get("awarded_at")),
        "claimed_at":                      _iso(a.get("claimed_at")),
    }


# ── Prize-pool validation + budget calc ──────────────
def _validate_prize_pool(pool: List[Dict[str, Any]]) -> None:
    if not pool or len(pool) < 1:
        raise ValueError("empty_prize_pool")
    seen_ranks = set()
    for row in pool:
        rank      = int(row.get("rank") or 0)
        reward    = int(row.get("points_reward") or 0)
        quantity  = int(row.get("quantity") or 1)
        currency  = (row.get("currency") or "bc").lower()
        if rank < 1 or rank > 100:
            raise ValueError("invalid_prize_rank")
        if rank in seen_ranks:
            raise ValueError("duplicate_prize_rank")
        seen_ranks.add(rank)
        if reward <= 0:
            raise ValueError("invalid_prize_reward")
        if quantity < 1 or quantity > 1000:
            raise ValueError("invalid_prize_quantity")
        if currency not in ("bc", "usd"):
            raise ValueError("invalid_prize_currency")


def _compute_costs(pool: List[Dict[str, Any]]) -> Dict[str, int]:
    """Sum of prize costs + platform fee.  BigCoin rewards are treated
    as 1 point = 1 cent for budgeting purposes (an internal accounting
    ratio so the platform is compensated for its BigCoin issuance).
    USD rewards use `points_reward` directly as cents."""
    prize_cost = 0
    max_awards = 0
    for row in pool:
        reward    = int(row.get("points_reward") or 0)
        quantity  = int(row.get("quantity") or 1)
        # Cents-equivalent for budgeting.  BigCoin: 1 point = 1¢.  USD: reward is already cents.
        prize_cost += reward * quantity
        max_awards += quantity
    fee = int(prize_cost * PLATFORM_FEE_PCT / 100)
    return {
        "prize_cost_cents":      prize_cost,
        "platform_fee_cents":  fee,
        "total_cents":              prize_cost + fee,
        "max_total_awards":    max_awards,
    }


# ── Stripe helpers (mirrors Phase G) ──────────────
async def _charge_prepayment(*, amount_cents: int, sponsorship_id: str,
                                                          advertiser_business_id: str
                                                          ) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        intent = _stripe.PaymentIntent.create(
            amount=int(amount_cents),
            currency="usd",
            payment_method_types=["card"],
            payment_method="pm_card_visa",
            confirm=True,
            metadata={
                "bigfm_flow":                          "ad5_trivia_sponsorship_prepay",
                "bigfm_sponsorship_id":        sponsorship_id,
                "bigfm_advertiser_id":          advertiser_business_id,
            },
            idempotency_key=f"ad5_ts_prepay_{sponsorship_id}")
        return {"payment_intent_id": intent.id,
                        "charge_id":                getattr(intent, "latest_charge", None) or "",
                        "amount_cents":        int(amount_cents),
                        "status":                  intent.status}
    except Exception as e:
        logger.exception("[ad5] stripe prepay failed")
        raise ValueError(f"stripe_error:{e}")


async def _refund_remaining(*, payment_intent_id: str,
                                                        refund_cents: int, sponsorship_id: str
                                                        ) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        refund = _stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=int(refund_cents),
            metadata={"bigfm_flow": "ad5_ts_refund",
                                "bigfm_sponsorship_id": sponsorship_id},
            idempotency_key=f"ad5_ts_refund_{sponsorship_id}")
        return {"refund_id": refund.id, "amount_cents": int(refund_cents),
                        "status": refund.status}
    except Exception as e:
        logger.exception("[ad5] stripe refund failed")
        raise ValueError(f"stripe_error:{e}")


# ── Sponsorship CRUD ──────────────────────────────
async def create_sponsorship(db, *,
                                                            advertiser_business_id: str,
                                                            body: Dict[str, Any],
                                                            user_id: str) -> Dict[str, Any]:
    sponsor_target_type = (body.get("sponsor_target_type") or "").strip()
    if sponsor_target_type not in TARGET_TYPES:
        raise ValueError("invalid_target_type")
    target_id = body.get("target_id") or None
    if sponsor_target_type in ("question_set", "category") and not target_id:
        raise ValueError("target_id_required")

    pool = body.get("prize_pool") or []
    _validate_prize_pool(pool)

    winner_selection = (body.get("winner_selection") or "top_n")
    if winner_selection not in SELECTION_MODES:
        raise ValueError("invalid_selection_mode")
    score_threshold = body.get("score_threshold")
    if winner_selection == "score_threshold" and \
            (score_threshold is None or int(score_threshold) < 0):
        raise ValueError("score_threshold_required")

    start = _aware(body.get("start_at"))
    end   = _aware(body.get("end_at"))
    if not (start and end) or end <= start:
        raise ValueError("invalid_time_window")

    if not (body.get("display_name") or "").strip():
        raise ValueError("display_name_required")

    if sponsor_target_type in ("category", "question_set") and target_id:
        cat = await db.trivia_categories.find_one({"id": target_id})
        if not cat:
            raise ValueError("category_not_found")

    costs = _compute_costs(pool)
    sponsorship_id = _gen("ts")
    now = _now()
    doc = {
        "_id":                                            sponsorship_id,
        "id":                                              sponsorship_id,
        "advertiser_business_id":            advertiser_business_id,
        "sponsor_target_type":                sponsor_target_type,
        "target_id":                                    target_id,
        "display_name":                              (body.get("display_name") or "")[:80],
        "tagline":                                      (body.get("tagline") or "")[:120],
        "logo_url":                                    body.get("logo_url"),
        "prize_pool":                                pool,
        "winner_selection":                    winner_selection,
        "score_threshold":                      (int(score_threshold)
                                                                            if winner_selection == "score_threshold"
                                                                            else None),
        "start_at":                                    start,
        "end_at":                                        end,
        "status":                                        "draft",
        "cost_cents":                                costs["total_cents"],
        "prize_cost_cents":                    costs["prize_cost_cents"],
        "platform_fee_cents":                  costs["platform_fee_cents"],
        "remaining_budget_cents":            costs["prize_cost_cents"],
        "max_total_awards":                    costs["max_total_awards"],
        "awarded_count":                          0,
        "created_at":                                now,
        "created_by_user_id":                  user_id,
        "admin_approval_required":        costs["total_cents"] >= ADMIN_APPROVAL_THRESHOLD_CENTS,
    }
    await db.trivia_sponsorships.insert_one(doc)
    return _shape_sponsorship(doc)


async def confirm_payment(db, *, sponsorship_id: str,
                                                    advertiser_business_id: str) -> Dict[str, Any]:
    s = await db.trivia_sponsorships.find_one({"id": sponsorship_id})
    if not s:
        raise ValueError("sponsorship_not_found")
    if s["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if s["status"] != "draft":
        raise ValueError(f"sponsorship_{s['status']}")

    charge = await _charge_prepayment(
        amount_cents=int(s["cost_cents"]),
        sponsorship_id=sponsorship_id,
        advertiser_business_id=advertiser_business_id)

    tx_id = _gen("tx_ts")
    await db.payment_transactions_v2.insert_one({
        "_id":                                        tx_id,
        "transaction_id":                    tx_id,
        "stripe_payment_intent_id":  charge["payment_intent_id"],
        "flow":                                      "ad5_trivia_sponsorship_prepay",
        "event_source":                        "trivia_sponsorship_prepay",
        "advertiser_id":                      advertiser_business_id,
        "bigfm_sponsorship_id":            sponsorship_id,
        "amount_cents":                        int(s["cost_cents"]),
        "application_fee_cents":        int(s["platform_fee_cents"]),
        "merchant_net_cents":              0,
        "currency":                                "usd",
        "status":                                    "posted",
        "created_at":                            _now(),
    })

    new_status = ("pending_admin"
                                if s.get("admin_approval_required")
                                else "active")
    now = _now()
    upd: Dict[str, Any] = {
        "status":                                          new_status,
        "stripe_payment_intent_id":          charge["payment_intent_id"],
        "stripe_prepayment_transaction_id": tx_id,
        "paid_at":                                        now,
    }
    if new_status == "active":
        upd["activated_at"] = now
    await db.trivia_sponsorships.update_one(
        {"id": sponsorship_id}, {"$set": upd})
    row = await db.trivia_sponsorships.find_one({"id": sponsorship_id})
    return {"sponsorship": _shape_sponsorship(row),
                    "charge": charge,
                    "transaction_id": tx_id}


async def list_sponsorships(db, *,
                                                        advertiser_business_id: Optional[str] = None,
                                                        status: Optional[str] = None,
                                                        limit: int = 100
                                                        ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    out = []
    async for s in db.trivia_sponsorships.find(q)\
                                                        .sort("created_at", -1).limit(limit):
        out.append(_shape_sponsorship(s))
    return out


async def get_sponsorship(db, *, sponsorship_id: str,
                                                  advertiser_business_id: Optional[str] = None,
                                                  is_admin: bool = False
                                                  ) -> Optional[Dict[str, Any]]:
    s = await db.trivia_sponsorships.find_one({"id": sponsorship_id})
    if not s:
        return None
    if (not is_admin) and advertiser_business_id \
            and s["advertiser_business_id"] != advertiser_business_id:
        return {"forbidden": True}
    total_awards = await db.trivia_sponsor_awards.count_documents(
        {"sponsorship_id": sponsorship_id})
    claimed = await db.trivia_sponsor_awards.count_documents(
        {"sponsorship_id": sponsorship_id, "redemption_status": "claimed"})
    return {
        "sponsorship":  _shape_sponsorship(s),
        "stats": {
            "total_awards":        total_awards,
            "claimed":                  claimed,
            "redemption_rate":  (round(claimed / total_awards, 4)
                                                    if total_awards > 0 else 0.0),
        },
    }


async def cancel_sponsorship(db, *, sponsorship_id: str,
                                                          advertiser_business_id: str,
                                                          reason: Optional[str] = None
                                                          ) -> Dict[str, Any]:
    s = await db.trivia_sponsorships.find_one({"id": sponsorship_id})
    if not s:
        raise ValueError("sponsorship_not_found")
    if s["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if s["status"] in STATUS_TERMINAL:
        raise ValueError(f"sponsorship_{s['status']}")

    refund: Optional[Dict[str, Any]] = None
    remaining = int(s.get("remaining_budget_cents") or 0)
    # Refund covers unspent prize budget + proportional platform fee.
    fee_pct                    = PLATFORM_FEE_PCT / 100
    unspent_fee_cents  = int(remaining * fee_pct)
    refund_cents          = remaining + unspent_fee_cents
    if s.get("stripe_payment_intent_id") and refund_cents > 0:
        refund = await _refund_remaining(
            payment_intent_id=s["stripe_payment_intent_id"],
            refund_cents=refund_cents, sponsorship_id=sponsorship_id)

    now = _now()
    upd = {
        "status":              "cancelled",
        "cancelled_at":  now,
        "cancel_reason": reason,
    }
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
        upd["remaining_budget_cents"]      = 0
    await db.trivia_sponsorships.update_one(
        {"id": sponsorship_id}, {"$set": upd})
    return {"sponsorship": _shape_sponsorship(
                          await db.trivia_sponsorships.find_one({"id": sponsorship_id})),
                    "refund": refund}


# ── Admin approval ──────────────────────────────────
async def admin_approve(db, *, sponsorship_id: str,
                                              admin_user_id: str,
                                              decision_note: Optional[str] = None
                                              ) -> Dict[str, Any]:
    s = await db.trivia_sponsorships.find_one({"id": sponsorship_id})
    if not s:
        raise ValueError("sponsorship_not_found")
    if s["status"] != "pending_admin":
        raise ValueError(f"sponsorship_{s['status']}")
    now = _now()
    await db.trivia_sponsorships.update_one(
        {"id": sponsorship_id},
        {"$set": {"status": "active", "activated_at": now,
                          "decision_note": decision_note,
                          "decided_by_user_id": admin_user_id,
                          "decided_at": now}})
    return _shape_sponsorship(
        await db.trivia_sponsorships.find_one({"id": sponsorship_id}))


async def admin_reject(db, *, sponsorship_id: str,
                                            admin_user_id: str,
                                            decision_note: Optional[str] = None
                                            ) -> Dict[str, Any]:
    s = await db.trivia_sponsorships.find_one({"id": sponsorship_id})
    if not s:
        raise ValueError("sponsorship_not_found")
    if s["status"] != "pending_admin":
        raise ValueError(f"sponsorship_{s['status']}")
    # Full refund since sponsorship never went live.
    refund: Optional[Dict[str, Any]] = None
    if s.get("stripe_payment_intent_id") and int(s.get("cost_cents") or 0) > 0:
        refund = await _refund_remaining(
            payment_intent_id=s["stripe_payment_intent_id"],
            refund_cents=int(s["cost_cents"]), sponsorship_id=sponsorship_id)
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
    await db.trivia_sponsorships.update_one(
        {"id": sponsorship_id}, {"$set": upd})
    return {"sponsorship": _shape_sponsorship(
                          await db.trivia_sponsorships.find_one({"id": sponsorship_id})),
                    "refund": refund}


# ── Room-binding validator (called from trivia_room_routes create) ──
async def resolve_and_validate_sponsorship(db, *,
                                                                                          sponsorship_id: str,
                                                                                          category_id: str
                                                                                          ) -> Optional[Dict[str, Any]]:
    """Called from `POST /api/trivia/rooms` when the request body
    includes `sponsorship_id`.  Returns the sponsorship metadata (only
    the fields safe to embed in the room state), or raises ValueError
    if the sponsorship isn't valid for this room.  Does NOT decrement
    budget — awards are drawn from the budget in the pipeline at
    `done` time."""
    if not sponsorship_id:
        return None
    s = await db.trivia_sponsorships.find_one({"id": sponsorship_id})
    if not s:
        raise ValueError("sponsorship_not_found")
    if s.get("status") != "active":
        raise ValueError(f"sponsorship_{s.get('status')}")
    now = _now()
    if _aware(s.get("start_at")) > now:
        raise ValueError("sponsorship_not_yet_started")
    if _aware(s.get("end_at")) <= now:
        raise ValueError("sponsorship_ended")
    ttype = s.get("sponsor_target_type")
    if ttype in ("category", "question_set"):
        if s.get("target_id") != category_id:
            raise ValueError("sponsorship_category_mismatch")
    # "any" — no additional check.
    return {
        "sponsorship_id": s["id"],
        "advertiser_business_id": s["advertiser_business_id"],
        "display_name":  s.get("display_name") or "",
        "tagline":            s.get("tagline") or "",
        "logo_url":          s.get("logo_url"),
        "prize_pool_public": [
            {"rank": p.get("rank"),
              "points_reward": int(p.get("points_reward") or 0),
              "currency": p.get("currency") or "bc",
              "quantity": int(p.get("quantity") or 1)}
            for p in (s.get("prize_pool") or [])
        ],
    }


# ── Award listings ──────────────────────────────────
async def list_awards_for_sponsorship(db, *, sponsorship_id: str,
                                                                                    limit: int = 200
                                                                                    ) -> List[Dict[str, Any]]:
    out = []
    async for a in db.trivia_sponsor_awards.find({"sponsorship_id": sponsorship_id})\
                                                                                          .sort("awarded_at", -1).limit(limit):
        out.append(_shape_award(a))
    return out


async def list_awards_for_user(db, *, user_id: str,
                                                              limit: int = 50
                                                              ) -> List[Dict[str, Any]]:
    out = []
    async for a in db.trivia_sponsor_awards.find({"user_id": user_id})\
                                                                                          .sort("awarded_at", -1).limit(limit):
        out.append(_shape_award(a))
    return out


async def mark_award_claimed(db, *, award_id: str,
                                                          user_id: str) -> Dict[str, Any]:
    """Listener endpoint: user acknowledges the prize in-wallet."""
    a = await db.trivia_sponsor_awards.find_one({"id": award_id})
    if not a:
        raise ValueError("award_not_found")
    if a["user_id"] != user_id:
        raise ValueError("not_award_owner")
    if a.get("redemption_status") == "claimed":
        return _shape_award(a)
    await db.trivia_sponsor_awards.update_one(
        {"id": award_id},
        {"$set": {"redemption_status": "claimed", "claimed_at": _now()}})
    return _shape_award(
        await db.trivia_sponsor_awards.find_one({"id": award_id}))


__all__ = [
    "ensure_trivia_sponsorship_indexes",
    "create_sponsorship", "confirm_payment",
    "list_sponsorships", "get_sponsorship", "cancel_sponsorship",
    "admin_approve", "admin_reject",
    "resolve_and_validate_sponsorship",
    "list_awards_for_sponsorship", "list_awards_for_user",
    "mark_award_claimed",
    "_shape_sponsorship", "_shape_award",
    "PLATFORM_FEE_PCT",  "ADMIN_APPROVAL_THRESHOLD_CENTS",
]
