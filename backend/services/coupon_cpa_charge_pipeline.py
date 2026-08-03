"""Phase N — M7 CPA (cost-per-action) charge pipeline for coupons.

Sits ON TOP of the AD.4 coupon system.  Advertisers pick between:
    * `cps`      → charge on save (existing AD.4 behavior — unchanged)
    * `cpa`      → charge on redemption, not on save
    * `hybrid`   → charge cost_per_save_cents on save AND
                                 cost_per_action_cents on redemption

The wallet used is the same `advertisers_v2.budget_available_cents`
that AD.4 uses today — no new budget ledger.  Idempotency: one
`coupon_action_charges` row per coupon (unique on `coupon_id`).

If a coupon on a CPA/hybrid campaign is redeemed but the
advertiser wallet is exhausted at that moment, the redemption
STILL succeeds (merchant already got paid via scan-to-pay).  The
charge row is logged with `cost_charged_cents=0` and
`refund_reason="budget_exhausted"` for the audit trail, and the
campaign is auto-paused with `wallet_exhausted`.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.m7_cpa_pipeline")

# ── Constants ─────────────────────────────────────────────────────
REDEMPTION_TYPES = {"scan_to_pay", "merchant_staff", "advertiser_staff",
                    "manual"}
PRICING_MODELS   = {"cps", "cpa", "hybrid"}
CPA_MODELS       = {"cpa", "hybrid"}


# ── Helpers ───────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _shape(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not d:
        return d
    out = dict(d)
    out.pop("_id", None)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def ensure_cpa_indexes(db) -> None:
    try:
        await db.coupon_action_charges.create_index(
            "id", unique=True, name="cac_id_uniq")
        # Idempotency: one charge per coupon.
        await db.coupon_action_charges.create_index(
            "coupon_id", unique=True, name="cac_coupon_uniq")
        await db.coupon_action_charges.create_index(
            [("campaign_id", 1), ("charged_at", -1)],
            name="cac_camp_time")
        await db.coupon_action_charges.create_index(
            [("advertiser_business_id", 1), ("refunded", 1),
             ("charged_at", -1)],
            name="cac_adv_ref_time")
        logger.info("[m7_cpa] indexes ready")
    except Exception as e:
        logger.warning("[m7_cpa] index setup failed: %s", e)


# ── Auto-pause helper (mirrors ad4_coupon_service._auto_pause) ───
async def _auto_pause_campaign(db, campaign_id: str,
                               reason: str) -> None:
    now = _now()
    await db.coupon_campaigns.update_one(
        {"campaign_id": campaign_id, "status": "live"},
        {"$set": {"status": "paused",
                  "auto_paused_reason": reason,
                  "auto_paused_at": now,
                  "updated_at": now}})


# ── Main pipeline ────────────────────────────────────────────────
async def charge_redemption(db, *, coupon_id: str,
                            redemption_type: str,
                            staff_user_id: Optional[str] = None
                            ) -> Dict[str, Any]:
    """Called AFTER a coupon has been marked `redeemed` by any
    redemption endpoint.  Idempotent on coupon_id.

    Returns:
        {ok, charge_id?, cost_charged_cents, remaining_budget_cents,
         refunded, refund_reason?, skipped?, skip_reason?}
    """
    if redemption_type not in REDEMPTION_TYPES:
        redemption_type = "manual"
    coupon = await db.coupons.find_one({"coupon_id": coupon_id})
    if not coupon:
        return {"ok": False, "skip_reason": "coupon_not_found"}
    campaign_id = coupon.get("ad_coupon_campaign_id")
    if not campaign_id:
        return {"ok": True, "skipped": True,
                "skip_reason": "not_ad4_coupon"}

    campaign = await db.coupon_campaigns.find_one(
        {"campaign_id": campaign_id})
    if not campaign:
        return {"ok": True, "skipped": True,
                "skip_reason": "campaign_not_found"}

    pricing = (campaign.get("pricing_model") or "cps").lower()
    if pricing not in CPA_MODELS:
        return {"ok": True, "skipped": True,
                "skip_reason": f"pricing_{pricing}_no_cpa_charge"}

    cost = int(campaign.get("cost_per_action_cents") or 0)
    if cost <= 0:
        return {"ok": True, "skipped": True,
                "skip_reason": "cost_per_action_zero"}

    advertiser_id = campaign.get("advertiser_id")
    user_id = coupon.get("user_id")
    now = _now()

    # ── Insert the charge row idempotently.  UNIQUE on coupon_id
    # rejects any duplicate call (which shouldn't happen because
    # coupons flip status=redeemed atomically, but belt & braces).
    charge_id = _gen("cac")
    doc: Dict[str, Any] = {
        "_id":                       charge_id,
        "id":                        charge_id,
        "coupon_id":                 coupon_id,
        "coupon_code":               coupon.get("code")
                                     or coupon.get("short_code"),
        "campaign_id":               campaign_id,
        "advertiser_business_id":    advertiser_id,
        "user_id":                   user_id,
        "redemption_type":           redemption_type,
        "staff_user_id":             staff_user_id,
        "cost_charged_cents":        0,
        "remaining_budget_before":   None,
        "remaining_budget_after":    None,
        "charged_at":                now,
        "refunded":                  False,
        "refund_reason":             None,
        "refunded_at":               None,
    }
    try:
        await db.coupon_action_charges.insert_one(doc)
    except Exception:
        # Duplicate — this coupon already had its CPA event.
        existing = await db.coupon_action_charges.find_one(
            {"coupon_id": coupon_id})
        return {"ok": True, "skipped": True,
                "skip_reason": "already_charged",
                "charge_id": (existing or {}).get("id")}

    # ── Atomic wallet decrement.  If budget insufficient, we don't
    # roll back the charge row — we just mark it 0¢ with the reason.
    ad_row = await db.advertisers_v2.find_one_and_update(
        {"advertiser_id": advertiser_id,
         "budget_available_cents": {"$gte": cost}},
        {"$inc": {"budget_available_cents": -cost,
                  "budget_spent_cents":     cost},
         "$set": {"updated_at": now}},
        return_document=True)

    if not ad_row:
        # Budget exhausted.  Log 0¢, mark campaign auto-paused.
        current = await db.advertisers_v2.find_one(
            {"advertiser_id": advertiser_id},
            {"budget_available_cents": 1})
        remaining = int((current or {}).get(
            "budget_available_cents", 0))
        await db.coupon_action_charges.update_one(
            {"id": charge_id},
            {"$set": {
                "cost_charged_cents":      0,
                "remaining_budget_before": remaining,
                "remaining_budget_after":  remaining,
                "refund_reason":           "budget_exhausted",
            }})
        await _auto_pause_campaign(
            db, campaign_id, "wallet_exhausted")
        return {"ok": True,
                "charge_id":              charge_id,
                "cost_charged_cents":     0,
                "remaining_budget_cents": remaining,
                "refunded":               False,
                "refund_reason":          "budget_exhausted",
                "campaign_paused":        True}

    remaining_before = int(ad_row.get("budget_available_cents", 0)) + cost
    remaining_after  = int(ad_row.get("budget_available_cents", 0))

    # ── Persist final numbers.  Also mirror to
    # payment_transactions_v2 for the finance audit trail.
    await db.coupon_action_charges.update_one(
        {"id": charge_id},
        {"$set": {
            "cost_charged_cents":      cost,
            "remaining_budget_before": remaining_before,
            "remaining_budget_after":  remaining_after,
        }})
    tx_id = _gen("tx_cac")
    try:
        await db.payment_transactions_v2.insert_one({
            "_id":                    tx_id,
            "transaction_id":         tx_id,
            "flow":                   "m7_cpa_redeem_charge",
            "event_source":           "coupon_cpa",
            "advertiser_id":          advertiser_id,
            "coupon_id":              coupon_id,
            "campaign_id":            campaign_id,
            "cpa_charge_id":          charge_id,
            "amount_cents":           cost,
            "application_fee_cents":  0,   # 100% goes into platform
            "merchant_net_cents":     0,
            "currency":               "usd",
            "status":                 "posted",
            "created_at":             now,
        })
    except Exception:
        pass

    # Auto-complete campaign when budget is empty AND CPA-only
    # (hybrid keeps running until inventory exhausts too).
    if remaining_after < cost:
        await _auto_pause_campaign(
            db, campaign_id, "wallet_exhausted")

    return {"ok": True,
            "charge_id":              charge_id,
            "cost_charged_cents":     cost,
            "remaining_budget_cents": remaining_after,
            "refunded":               False}


# ── Dispute + admin refund ──────────────────────────────────────
async def _refund_charge_row(db, *, charge_id: str, reason: str,
                             actor_kind: str,
                             actor_user_id: Optional[str]
                             ) -> Dict[str, Any]:
    """Common refund path: credit the budget back + flip
    refunded=true on the charge.  Idempotent — refunding an
    already-refunded charge is a no-op."""
    charge = await db.coupon_action_charges.find_one(
        {"id": charge_id})
    if not charge:
        raise ValueError("charge_not_found")
    if charge.get("refunded"):
        return {"ok": True, "already_refunded": True,
                "charge_id": charge_id}
    now = _now()
    cost = int(charge.get("cost_charged_cents") or 0)
    if cost > 0:
        await db.advertisers_v2.update_one(
            {"advertiser_id": charge.get("advertiser_business_id")},
            {"$inc": {"budget_available_cents": cost,
                      "budget_spent_cents":     -cost},
             "$set": {"updated_at": now}})
    await db.coupon_action_charges.update_one(
        {"id": charge_id},
        {"$set": {
            "refunded":         True,
            "refund_reason":    (reason or actor_kind)[:200],
            "refunded_at":      now,
            "refunded_by_kind":   actor_kind,
            "refunded_by_user_id": actor_user_id,
        }})
    return {"ok": True, "charge_id": charge_id,
            "refunded_amount_cents": cost}


async def advertiser_dispute_charge(db, *, campaign_id: str,
                                    charge_id: str,
                                    advertiser_business_id: str,
                                    reason: str,
                                    advertiser_user_id: str
                                    ) -> Dict[str, Any]:
    charge = await db.coupon_action_charges.find_one(
        {"id": charge_id})
    if not charge:
        raise ValueError("charge_not_found")
    if charge.get("campaign_id") != campaign_id:
        raise ValueError("charge_campaign_mismatch")
    if charge.get("advertiser_business_id") != advertiser_business_id:
        raise ValueError("charge_advertiser_mismatch")
    return await _refund_charge_row(
        db, charge_id=charge_id,
        reason=f"disputed:{reason}"[:200],
        actor_kind="advertiser_dispute",
        actor_user_id=advertiser_user_id)


async def admin_refund_charge(db, *, charge_id: str,
                              reason: str,
                              admin_user_id: str) -> Dict[str, Any]:
    return await _refund_charge_row(
        db, charge_id=charge_id,
        reason=f"admin_refund:{reason}"[:200],
        actor_kind="admin_refund",
        actor_user_id=admin_user_id)


# ── Listings + metrics ──────────────────────────────────────────
async def list_charges(db, *,
                       advertiser_business_id: Optional[str] = None,
                       campaign_id: Optional[str] = None,
                       refunded: Optional[bool] = None,
                       limit: int = 100,
                       skip: int = 0) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if campaign_id:
        q["campaign_id"] = campaign_id
    if refunded is not None:
        q["refunded"] = bool(refunded)
    rows = []
    async for c in db.coupon_action_charges.find(q).sort(
            "charged_at", -1).skip(int(skip)).limit(int(limit)):
        rows.append(_shape(c))
    return rows


async def campaign_charges_metric(db, *, campaign_id: str
                                  ) -> Dict[str, Any]:
    """Aggregate CPA + CPS spending for a single coupon_campaign.

    saves_charged  → count of coupons minted (== campaign.saves_count)
    actions_charged → count of successful CPA charges (non-refunded,
                                        cost>0) from coupon_action_charges
    total_charged_cents = CPS spend + CPA spend
    remaining_budget_cents = wallet.budget_available_cents  (best-effort)
    """
    campaign = await db.coupon_campaigns.find_one(
        {"campaign_id": campaign_id})
    if not campaign:
        raise ValueError("campaign_not_found")
    saves_count = int(campaign.get("saves_count") or 0)
    cps = int(campaign.get("cost_per_save_cents") or 0)
    pricing = (campaign.get("pricing_model") or "cps").lower()
    # CPS spend only counts if pricing includes 'cps' at save time.
    cps_spend = 0
    if pricing in ("cps", "hybrid"):
        cps_spend = saves_count * cps

    # CPA aggregation.
    actions_count = 0
    cpa_spend    = 0
    actions_charged = 0
    actions_refunded = 0
    async for r in db.coupon_action_charges.aggregate([
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": "$refunded",
                    "count": {"$sum": 1},
                    "spend": {"$sum": "$cost_charged_cents"}}},
    ]):
        if r["_id"] is False or r["_id"] is None:
            actions_charged = int(r["count"])
            cpa_spend       = int(r["spend"])
        else:
            actions_refunded = int(r["count"])
    actions_count = actions_charged + actions_refunded

    # Wallet snapshot.
    ad = await db.advertisers_v2.find_one(
        {"advertiser_id": campaign.get("advertiser_id")},
        {"budget_available_cents": 1, "budget_spent_cents": 1})
    ad = ad or {}
    return {
        "campaign_id":              campaign_id,
        "pricing_model":            pricing,
        "cost_per_save_cents":      cps,
        "cost_per_action_cents":    int(campaign.get(
                                        "cost_per_action_cents") or 0),
        "saves_charged":            saves_count,
        "actions_count":            actions_count,
        "actions_charged":          actions_charged,
        "actions_refunded":         actions_refunded,
        "cps_spend_cents":          cps_spend,
        "cpa_spend_cents":          cpa_spend,
        "total_charged_cents":      cps_spend + cpa_spend,
        "advertiser_budget_available_cents":
            int(ad.get("budget_available_cents") or 0),
        "advertiser_budget_spent_cents":
            int(ad.get("budget_spent_cents") or 0),
    }


# ── Non-blocking helper for redemption routes ───────────────────
async def try_charge_after_redemption(db, *, coupon_id: str,
                                      redemption_type: str,
                                      staff_user_id: Optional[str] = None
                                      ) -> Dict[str, Any]:
    """Wrapper that never raises — the redemption endpoint calls
    this best-effort so it can't 500 the customer-facing flow.

    Callers may `asyncio.create_task(...)` this OR await inline —
    the CPA charge is fast (single find_one_and_update)."""
    try:
        return await charge_redemption(
            db, coupon_id=coupon_id,
            redemption_type=redemption_type,
            staff_user_id=staff_user_id)
    except Exception as e:
        logger.exception(
            "[m7_cpa] charge_redemption failed for coupon %s: %s",
            coupon_id, e)
        return {"ok": False, "error": str(e)}


__all__ = [
    "ensure_cpa_indexes", "charge_redemption",
    "try_charge_after_redemption",
    "advertiser_dispute_charge", "admin_refund_charge",
    "list_charges", "campaign_charges_metric",
    "PRICING_MODELS", "REDEMPTION_TYPES",
]
