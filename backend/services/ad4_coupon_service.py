"""Phase AD.4 — Coupon Pay-Per-Save.

Advertiser-owned coupon campaigns.  When a customer taps *Save* in the
app, we:
    1. Mint a coupon into `coupons` (existing SC.x/MER.2 collection) with
        both `advertiser_id` (AD.6 scope) AND `business_id` (MER.2 scope) so
        BOTH the merchant cashier AND advertiser staff can redeem.
    2. Push a `user_wallet_items` row so the /wallet UI picks it up.
    3. Bill the advertiser $CPS via the same split-routed
        `payment_transactions_v2` ledger AD.2 uses (event_source=coupon_save).
    4. Enforce (user_id, campaign_id) uniqueness → same user can only save
        once (returns already_saved on retry, no re-bill).
    5. Enforce inventory cap → atomic $inc + auto-pause when cap reached.
    6. Enforce wallet drain → auto-pause when advertiser wallet ≤ CPS.

Design notes
────────────
* Virtual ledger only — same shape as AD.2.  Real Stripe.Transfer happens
    in a follow-up payout sweeper (out of scope).
* Every `coupon_save` writes ONE row.  Unique-sparse index on
    `payment_transactions_v2.ad4_save_event_id` = f"save_{user}_{campaign}"
    guarantees at-most-once billing per user per campaign.
* Sponsoring merchant is REQUIRED at publish-time — non-negotiable per
    the spec ("cannot publish without it").
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services.commission_service import calculate_platform_fee

logger = logging.getLogger("bigfm.ad4")


COMMISSION_TXN_TYPE = "coupon_save"
DEFAULT_MERCHANT_SHARE_PCT = 70  # platform_commission_percent = 30
STATUSES = ("draft", "pending_admin", "approved", "live",
                        "paused", "rejected", "completed")
EVENT_SOURCE = "coupon_save"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else dt


def _aware(dt) -> Optional[datetime]:
    if dt is None or not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _gen(prefix: str, n: int = 12) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:n]}"


# ═════════════════════════════════════════════════════════════════
# Indexes
# ═════════════════════════════════════════════════════════════════
async def ensure_ad4_indexes(db) -> None:
    try:
        await db.coupon_campaigns.create_index("campaign_id", unique=True)
        await db.coupon_campaigns.create_index([("advertiser_id", 1),
                                                                                                            ("status", 1),
                                                                                                            ("created_at", -1)])
        await db.coupon_campaigns.create_index([("status", 1), ("end_time", 1)])
        await db.coupon_campaigns.create_index([("sponsoring_merchant_id", 1),
                                                                                                            ("status", 1)], sparse=True)
        # Idempotency guard — one save per (user, campaign).
        await db.payment_transactions_v2.create_index(
            "ad4_save_event_id", unique=True, sparse=True,
            name="idx_ad4_save_event_id")
    except Exception as e:
        logger.warning("[ad4] index setup: %s", e)


# ═════════════════════════════════════════════════════════════════
# CRUD — advertiser side
# ═════════════════════════════════════════════════════════════════
def _sanitize_targeting(t) -> Dict[str, Any]:
    """Accept a subset of AD.1 targeting JSON — cities, tags, hours."""
    if not isinstance(t, dict):
        return {}
    out: Dict[str, Any] = {}
    if isinstance(t.get("cities"), list):
        out["cities"] = [str(c)[:40] for c in t["cities"][:20]]
    if isinstance(t.get("country_codes"), list):
        out["country_codes"] = [str(c).upper()[:2] for c in t["country_codes"][:20]]
    if isinstance(t.get("category_tags"), list):
        out["category_tags"] = [str(c).lower()[:32] for c in t["category_tags"][:20]]
    if isinstance(t.get("hours"), list):
        out["hours"] = [int(h) for h in t["hours"] if isinstance(h, (int, str))
                                      and str(h).isdigit() and 0 <= int(h) <= 23]
    return out


async def create_coupon_campaign(db, *, advertiser_id: str,
                                                                                    payload: Dict[str, Any]) -> Dict[str, Any]:
    now = _now()
    campaign_id = _gen("cc")
    # Phase N (M7) — pricing model.  Backward-compat: absent →
    # "cps" behaves exactly like AD.4 pre-M7.
    pricing_model = (payload.get("pricing_model") or "cps").lower()
    if pricing_model not in ("cps", "cpa", "hybrid"):
        raise ValueError(f"invalid_pricing_model:{pricing_model}")
    budget_type = (payload.get("budget_type") or "prepaid").lower()
    if budget_type != "prepaid":
        # MVP: metered = out of scope, reject.
        raise ValueError(f"invalid_budget_type:{budget_type}")
    cpa_cents = int(payload.get("cost_per_action_cents") or 0)
    cps_cents = int(payload.get("cost_per_save_cents") or 0)
    if pricing_model in ("cpa", "hybrid") and cpa_cents <= 0:
        raise ValueError("cost_per_action_cents_required")
    if pricing_model in ("cps", "hybrid") and cps_cents <= 0:
        raise ValueError("cost_per_save_cents_required")

    doc = {
        "_id":                                      campaign_id,
        "campaign_id":                      campaign_id,
        "advertiser_id":                  advertiser_id,
        "sponsoring_merchant_id":  payload.get("sponsoring_merchant_id"),
        "title":                                  (payload.get("title") or "")[:120],
        "description":                      (payload.get("description") or "")[:500],
        "terms":                                  (payload.get("terms") or "")[:500],
        "retail_value_cents":            int(payload.get("retail_value_cents") or 0),
        "value_currency":                  (payload.get("value_currency") or "USD").upper(),
        # Phase N (M7) — new pricing fields.
        "pricing_model":                    pricing_model,
        "budget_type":                      budget_type,
        "cost_per_save_cents":          cps_cents,
        "cost_per_action_cents":      cpa_cents,
        "total_inventory":                int(payload.get("total_inventory") or 0),
        "saves_count":                        0,
        "targeting":                          _sanitize_targeting(payload.get("targeting")),
        "category_tags":                    list(payload.get("category_tags") or []),
        "logo_url":                            payload.get("logo_url"),
        "hero_image_url":                  payload.get("hero_image_url"),
        "start_time":                        _aware(payload.get("start_time")) or now,
        "end_time":                            _aware(payload.get("end_time"))
                                                            or (now + timedelta(days=30)),
        "status":                                "draft",
        "created_at":                        now,
        "updated_at":                        now,
        # Auto-pause hooks (populated on drain/exhaustion).
        "auto_paused_reason":            None,
        "auto_paused_at":                  None,
    }
    await db.coupon_campaigns.insert_one(doc)
    return _serialize(doc)


async def patch_coupon_campaign(db, *, campaign_id: str,
                                                                                payload: Dict[str, Any]) -> Dict[str, Any]:
    existing = await db.coupon_campaigns.find_one({"campaign_id": campaign_id})
    if not existing:
        return None
    if existing["status"] not in ("draft", "rejected"):
        raise ValueError(f"cannot_edit_status_{existing['status']}")
    updates: Dict[str, Any] = {"updated_at": _now()}
    for k in ("title", "description", "terms", "sponsoring_merchant_id",
                        "logo_url", "hero_image_url", "value_currency"):
        if k in payload and payload[k] is not None:
            updates[k] = payload[k]
    for k in ("retail_value_cents", "cost_per_save_cents",
              "cost_per_action_cents", "total_inventory"):
        if k in payload and payload[k] is not None:
            updates[k] = int(payload[k])
    if "category_tags" in payload:
        updates["category_tags"] = list(payload["category_tags"] or [])
    if "targeting" in payload:
        updates["targeting"] = _sanitize_targeting(payload["targeting"])
    if "start_time" in payload:
        updates["start_time"] = _aware(payload["start_time"])
    if "end_time" in payload:
        updates["end_time"] = _aware(payload["end_time"])
    await db.coupon_campaigns.update_one({"campaign_id": campaign_id},
                                                                                                {"$set": updates})
    return _serialize(await db.coupon_campaigns.find_one({"campaign_id": campaign_id}))


async def publish_coupon_campaign(db, *, campaign_id: str) -> Dict[str, Any]:
    c = await db.coupon_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        return None
    if c["status"] not in ("draft", "rejected"):
        raise ValueError(f"cannot_publish_status_{c['status']}")
    # Publish preconditions.
    missing: List[str] = []
    if not c.get("sponsoring_merchant_id"):
        missing.append("sponsoring_merchant_id")
    if not (c.get("title") or "").strip():
        missing.append("title")
    # Phase N (M7) — pricing-model-aware requirements.
    pm = (c.get("pricing_model") or "cps").lower()
    if pm in ("cps", "hybrid"):
        if int(c.get("cost_per_save_cents") or 0) <= 0:
            missing.append("cost_per_save_cents")
    if pm in ("cpa", "hybrid"):
        if int(c.get("cost_per_action_cents") or 0) <= 0:
            missing.append("cost_per_action_cents")
    if int(c.get("total_inventory") or 0) <= 0:
        missing.append("total_inventory")
    if missing:
        raise ValueError(f"missing_required:{','.join(missing)}")
    await db.coupon_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status":            "pending_admin",
                          "submitted_at":  _now(),
                          "updated_at":    _now()}})
    return _serialize(await db.coupon_campaigns.find_one({"campaign_id": campaign_id}))


async def admin_review_coupon_campaign(db, *, campaign_id: str, action: str,
                                                                                                          admin_user_id: str,
                                                                                                          reason: Optional[str] = None) -> Dict[str, Any]:
    c = await db.coupon_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        return None
    if action == "approve":
        if c["status"] not in ("pending_admin", "paused"):
            raise ValueError(f"cannot_approve_status_{c['status']}")
        target = "live"
    elif action == "reject":
        if c["status"] != "pending_admin":
            raise ValueError(f"cannot_reject_status_{c['status']}")
        target = "rejected"
    elif action == "pause":
        if c["status"] != "live":
            raise ValueError(f"cannot_pause_status_{c['status']}")
        target = "paused"
    else:
        raise ValueError(f"unknown_action_{action}")
    await db.coupon_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status":                    target,
                          "reviewed_by":          admin_user_id,
                          "reviewed_at":          _now(),
                          "review_reason":      (reason or "")[:200],
                          "updated_at":            _now()}})
    return _serialize(await db.coupon_campaigns.find_one({"campaign_id": campaign_id}))


async def list_advertiser_coupon_campaigns(
        db, *, advertiser_id: str, status: Optional[str] = None,
        limit: int = 50) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"advertiser_id": advertiser_id}
    if status:
        q["status"] = status
    rows = await db.coupon_campaigns.find(q).sort(
        [("created_at", -1)]).to_list(min(int(limit or 50), 200))
    return [_serialize(r) for r in rows]


async def list_admin_pending(db, *, limit: int = 100) -> List[Dict[str, Any]]:
    rows = await db.coupon_campaigns.find(
        {"status": "pending_admin"}).sort(
        [("submitted_at", 1)]).to_list(min(int(limit or 100), 500))
    return [_serialize(r) for r in rows]


# ═════════════════════════════════════════════════════════════════
# Customer-facing listing
# ═════════════════════════════════════════════════════════════════
async def list_live_coupon_campaigns(
        db, *, market: Optional[str] = None,
        city: Optional[str] = None,
        category_tag: Optional[str] = None,
        limit: int = 40) -> List[Dict[str, Any]]:
    """Filter live + inventory-available + within time window."""
    now = _now()
    q: Dict[str, Any] = {
        "status":                "live",
        "start_time":      {"$lte": now},
        "end_time":          {"$gte": now},
        "$expr":              {"$lt": ["$saves_count", "$total_inventory"]},
    }
    if market:
        # Country-code targeting is inclusive: rows with no country_codes
        # target list are shown to everyone.
        q["$or"] = [
            {"targeting.country_codes": {"$in": [market.upper()]}},
            {"targeting.country_codes": {"$exists": False}},
            {"targeting.country_codes": {"$size": 0}},
        ]
    if city:
        q_city = [{"targeting.cities": {"$in": [city]}},
                            {"targeting.cities": {"$exists": False}},
                            {"targeting.cities": {"$size": 0}}]
        if "$or" in q:
            q.setdefault("$and", []).append({"$or": q.pop("$or")})
            q["$and"].append({"$or": q_city})
        else:
            q["$or"] = q_city
    if category_tag:
        q["category_tags"] = category_tag.lower()

    rows = await db.coupon_campaigns.find(q).sort(
        [("created_at", -1)]).to_list(min(int(limit or 40), 200))
    # Enrich with sponsoring merchant name/logo.
    merch_ids = list({r.get("sponsoring_merchant_id") for r in rows
                                            if r.get("sponsoring_merchant_id")})
    merchants: Dict[str, Dict[str, Any]] = {}
    if merch_ids:
        async for b in db.businesses.find(
                {"$or": [{"business_id": {"$in": merch_ids}},
                                {"_id": {"$in": merch_ids}}]},
                {"business_id": 1, "_id": 1, "name": 1,
                  "logo_url": 1, "city": 1}):
            merchants[b.get("business_id") or b.get("_id")] = b
    out = []
    for r in rows:
        s = _serialize(r)
        biz = merchants.get(r.get("sponsoring_merchant_id"))
        s["sponsoring_merchant"] = ({
            "id":  biz.get("business_id") or biz.get("_id"),
            "name":      biz.get("name"),
            "logo_url": biz.get("logo_url"),
            "city":      biz.get("city"),
        } if biz else None)
        s["inventory_remaining"] = max(0, int(r.get("total_inventory", 0)
                                                                                    ) - int(r.get("saves_count", 0)))
        out.append(s)
    return out


# ═════════════════════════════════════════════════════════════════
# CORE: customer save → mint coupon + wallet_item + bill split
# ═════════════════════════════════════════════════════════════════
async def save_coupon_campaign(db, *, campaign_id: str,
                                                                        user_id: str) -> Dict[str, Any]:
    """The all-in-one save action.  Idempotent + atomic.

    Return shape:
        {ok, already_saved?, coupon_id, wallet_item_id, transaction_id?,
          gross_cents?, merchant_cents?, platform_cents?, campaign_paused?,
          reason?}
    """
    campaign = await db.coupon_campaigns.find_one({"campaign_id": campaign_id})
    if not campaign:
        return {"ok": False, "reason": "campaign_not_found"}
    # Precedence: intrinsic conditions (inventory / expiry / not-started)
    # take priority over paused-status so callers get a stable
    # HTTP 410/425 instead of 409 when a race auto-pauses first.
    now_pre = _now()
    if int(campaign.get("saves_count", 0)) >= int(campaign.get("total_inventory", 0)):
        await _auto_pause(db, campaign_id, "inventory_exhausted")
        return {"ok": False, "reason": "inventory_exhausted",
                      "campaign_paused": True}
    start_pre = _aware(campaign.get("start_time"))
    end_pre   = _aware(campaign.get("end_time"))
    if start_pre and start_pre > now_pre:
        return {"ok": False, "reason": "not_started"}
    if end_pre and end_pre < now_pre:
        return {"ok": False, "reason": "expired"}
    if campaign.get("status") != "live":
        # Preserve auto-pause context so clients can distinguish
        # inventory-vs-wallet-vs-manual pause states.
        reason = campaign.get("auto_paused_reason")
        if reason in ("inventory_exhausted", "wallet_exhausted"):
            return {"ok": False, "reason": reason,
                          "campaign_paused": True}
        return {"ok": False, "reason": f"campaign_{campaign.get('status')}"}
    now = now_pre

    # ─ Idempotency: has this user already saved? ───────────
    save_event_id = f"save_{user_id}_{campaign_id}"
    dup_tx = await db.payment_transactions_v2.find_one(
        {"ad4_save_event_id": save_event_id},
        {"transaction_id": 1, "coupon_id": 1, "wallet_item_id": 1, "_id": 0})
    if dup_tx:
        return {"ok": True, "already_saved": True,
                      "coupon_id":            dup_tx.get("coupon_id"),
                      "wallet_item_id":  dup_tx.get("wallet_item_id"),
                      "transaction_id": dup_tx.get("transaction_id")}

    # ─ Compute split via commission_service ─────────────────
    # Phase N (M7) — for pricing_model="cpa", NO charge happens on
    # save; the advertiser pays only at redemption via the CPA
    # pipeline.  For "cps" and "hybrid", the save-side charge is
    # exactly the original AD.4 behavior.
    pricing_model = (campaign.get("pricing_model") or "cps").lower()
    save_charge_active = pricing_model in ("cps", "hybrid")
    cps_cents = int(campaign.get("cost_per_save_cents") or 0) \
                if save_charge_active else 0
    merchant_id = campaign.get("sponsoring_merchant_id")
    biz = None
    if merchant_id:
        biz = await db.businesses.find_one(
            {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]},
            {"stripe_connect_account_id": 1, "name": 1})
    biz = biz or {}
    fee_view = await calculate_platform_fee(
        db, merchant_id=merchant_id,
        category="*",
        transaction_type=COMMISSION_TXN_TYPE,
        amount_cents=cps_cents,
        market=None, campaign_type="coupon_save",
        write_audit=False)
    platform_cents = max(0, min(int(fee_view.get("commission_cents") or 0),
                                                                  cps_cents))
    merchant_cents = cps_cents - platform_cents

    # ─ Atomic wallet + inventory guards ──────────────────────
    # For CPA-only, cps_cents==0 → wallet check trivially passes.
    ad = await db.advertisers_v2.find_one_and_update(
        {"advertiser_id": campaign.get("advertiser_id"),
          "budget_available_cents": {"$gte": cps_cents}},
        {"$inc": {"budget_available_cents": -cps_cents,
                          "budget_spent_cents":         cps_cents},
          "$set": {"updated_at": now}},
        return_document=True)
    if not ad:
        await _auto_pause(db, campaign_id, "wallet_exhausted")
        return {"ok": False, "reason": "wallet_exhausted",
                      "campaign_paused": True}
    wallet_balance_after = int(ad.get("budget_available_cents") or 0)

    # Atomic inventory increment — guarded by `$expr` inventory check.
    inv_upd = await db.coupon_campaigns.update_one(
        {"campaign_id": campaign_id,
          "$expr": {"$lt": ["$saves_count", "$total_inventory"]}},
        {"$inc": {"saves_count": 1}, "$set": {"updated_at": now}})
    if inv_upd.modified_count == 0:
        # Someone else grabbed the last one between our check and $inc.
        # Roll back the wallet, don't mint anything, and auto-pause.
        await db.advertisers_v2.update_one(
            {"advertiser_id": campaign.get("advertiser_id")},
            {"$inc": {"budget_available_cents": cps_cents,
                              "budget_spent_cents":         -cps_cents}})
        await _auto_pause(db, campaign_id, "inventory_exhausted")
        return {"ok": False, "reason": "inventory_exhausted",
                      "campaign_paused": True}

    # ─ Mint coupon (existing coupons schema) ────────────────
    coupon_id = "cpn_" + secrets.token_hex(7)
    short_code = f"ADV-{secrets.token_hex(3).upper()}"
    coupon_doc = {
        "_id":                                    coupon_id,
        "coupon_id":                          coupon_id,
        "code":                                  short_code,
        "short_code":                        short_code,
        "advertiser_id":                    campaign.get("advertiser_id"),
        "business_id":                      merchant_id,     # merchant cashier scope
        "ad_coupon_campaign_id":      campaign_id,
        "coupon_type":                      "coupon",
        "status":                                "saved",
        "user_id":                              user_id,
        "discount_value":                (int(campaign.get("retail_value_cents") or 0) / 100.0),
        "value_currency":                campaign.get("value_currency") or "USD",
        "title":                                  campaign.get("title"),
        "description":                      campaign.get("description"),
        "terms":                                  campaign.get("terms"),
        "issued_at":                          now,
        "expires_at":                        campaign.get("end_time"),
        "source_type":                      "ad4_coupon_save",
    }
    await db.coupons.insert_one(coupon_doc)

    # ─ Wallet item (customer-visible) ────────────────────────
    wallet_item_id = "wi_" + secrets.token_hex(7)
    qr_token = secrets.token_urlsafe(24)
    wallet_doc = {
        "_id":                                    wallet_item_id,
        "wallet_item_id":                wallet_item_id,
        "user_id":                              user_id,
        "kind":                                  "coupon",
        "advertiser_id":                    campaign.get("advertiser_id"),
        "merchant_id":                      merchant_id,
        "ad_coupon_campaign_id":      campaign_id,
        "coupon_id":                          coupon_id,
        "short_code":                        short_code,
        "qr_token":                            qr_token,
        "title":                                  campaign.get("title"),
        "description":                      campaign.get("description"),
        "terms":                                  campaign.get("terms"),
        "logo_url":                            campaign.get("logo_url"),
        "hero_image_url":                campaign.get("hero_image_url"),
        "retail_value_cents":          int(campaign.get("retail_value_cents") or 0),
        "value_currency":                campaign.get("value_currency") or "USD",
        "issued_at":                          now,
        "expires_at":                        campaign.get("end_time"),
        "status":                                "saved",
        "source_type":                      "ad4_coupon_save",
    }
    await db.user_wallet_items.insert_one(wallet_doc)
    # Back-link the coupon to the wallet item (so cashier scan resolves QR).
    await db.coupons.update_one(
        {"coupon_id": coupon_id},
        {"$set": {"source_wallet_item_id": wallet_item_id}})

    # ─ Persist split-routed ledger row ───────────────────────
    txn_id = _gen("tx_ad4")
    doc = {
        "_id":                                    txn_id,
        "transaction_id":                txn_id,
        "flow":                                  "ad4_coupon_save_split",
        "event_source":                    EVENT_SOURCE,
        "ad4_save_event_id":            save_event_id,
        "coupon_campaign_id":          campaign_id,
        "advertiser_id":                    campaign.get("advertiser_id"),
        "merchant_id":                      merchant_id,
        "customer_user_id":              user_id,
        "coupon_id":                          coupon_id,
        "wallet_item_id":                wallet_item_id,
        "amount_cents":                    cps_cents,
        "subtotal_cents":                cps_cents,
        "currency":                            "USD",
        "application_fee_cents":    platform_cents,
        "merchant_net_cents":          merchant_cents,
        "computed_percent":            fee_view.get("computed_percent"),
        "commission_rule_id":          fee_view.get("rule_id"),
        "commission_source":            fee_view.get("source"),
        # MER.3 pattern to bypass legacy unique-not-sparse index.
        "stripe_payment_intent_id": f"ad4_{txn_id}",
        "stripe_charge_id":              None,
        "stripe_connected_account_id":
            biz.get("stripe_connect_account_id"),
        "status":                                "succeeded",
        "wallet_balance_after_cents": wallet_balance_after,
        "created_at":                        now,
        "succeeded_at":                    now,
    }
    try:
        await db.payment_transactions_v2.insert_one(doc)
    except Exception as e:
        logger.exception("[ad4] ledger insert failed — rolling back")
        # Rollback: uncredit merchant/decrement saves + refund wallet.
        # Delete coupon + wallet_item so the state stays clean.
        await db.advertisers_v2.update_one(
            {"advertiser_id": campaign.get("advertiser_id")},
            {"$inc": {"budget_available_cents": cps_cents,
                              "budget_spent_cents":         -cps_cents}})
        await db.coupon_campaigns.update_one(
            {"campaign_id": campaign_id},
            {"$inc": {"saves_count": -1}})
        await db.coupons.delete_one({"coupon_id": coupon_id})
        await db.user_wallet_items.delete_one({"wallet_item_id": wallet_item_id})
        return {"ok": False, "reason": "ledger_insert_failed",
                      "detail": str(e)[:120]}

    # ─ Post-write auto-pause checks ──────────────────────────
    fresh = await db.coupon_campaigns.find_one({"campaign_id": campaign_id})
    campaign_paused = False
    if fresh:
        saves = int(fresh.get("saves_count") or 0)
        inv   = int(fresh.get("total_inventory") or 0)
        if inv > 0 and saves >= inv:
            await _auto_pause(db, campaign_id, "inventory_exhausted")
            campaign_paused = True
    if wallet_balance_after < cps_cents:
        # Not enough left in the wallet for even one more save →
        # pause the campaign so subsequent taps fail fast.
        await _auto_pause(db, campaign_id, "wallet_exhausted")
        campaign_paused = True

    return {
        "ok":                                      True,
        "coupon_id":                          coupon_id,
        "short_code":                        short_code,
        "wallet_item_id":                wallet_item_id,
        "qr_token":                            qr_token,
        "transaction_id":                txn_id,
        "gross_cents":                      cps_cents,
        "merchant_cents":                merchant_cents,
        "platform_cents":                platform_cents,
        "wallet_balance_cents_after": wallet_balance_after,
        "campaign_paused":              campaign_paused,
    }


async def _auto_pause(db, campaign_id: str, reason: str) -> None:
    await db.coupon_campaigns.update_one(
        {"campaign_id": campaign_id, "status": {"$in": ["live"]}},
        {"$set": {"status":                        "paused",
                          "auto_paused_reason": reason,
                          "auto_paused_at":        _now(),
                          "updated_at":                _now()}})
    logger.info("[ad4] auto-paused campaign=%s reason=%s",
                            campaign_id, reason)


# ═════════════════════════════════════════════════════════════════
# Read APIs — advertiser + merchant transactions
# ═════════════════════════════════════════════════════════════════
async def list_advertiser_coupon_transactions(
        db, *, advertiser_id: str, limit: int = 100) -> Dict[str, Any]:
    q = {"advertiser_id": advertiser_id,
              "flow":                    "ad4_coupon_save_split"}
    per_campaign = await db.payment_transactions_v2.aggregate([
        {"$match": q},
        {"$group": {
            "_id": "$coupon_campaign_id",
            "saves":                        {"$sum": 1},
            "gross_cents":            {"$sum": "$amount_cents"},
            "merchant_cents":      {"$sum": "$merchant_net_cents"},
            "platform_cents":      {"$sum": "$application_fee_cents"},
            "last_save_at":          {"$max": "$created_at"},
        }},
        {"$sort": {"last_save_at": -1}},
    ]).to_list(200)

    enriched = []
    for r in per_campaign:
        cc = await db.coupon_campaigns.find_one({"campaign_id": r["_id"]},
                                                                                                                {"title": 1, "status": 1, "total_inventory": 1,
                                                                                                                  "saves_count": 1,
                                                                                                                  "sponsoring_merchant_id": 1,
                                                                                                                  "auto_paused_reason": 1})
        biz = None
        if (cc or {}).get("sponsoring_merchant_id"):
            biz = await db.businesses.find_one(
                {"$or": [{"business_id": cc["sponsoring_merchant_id"]},
                                {"_id": cc["sponsoring_merchant_id"]}]},
                {"name": 1})
        enriched.append({
            "campaign_id":                r["_id"],
            "title":                            (cc or {}).get("title"),
            "status":                          (cc or {}).get("status"),
            "auto_paused_reason": (cc or {}).get("auto_paused_reason"),
            "sponsoring_merchant_name": (biz or {}).get("name"),
            "total_inventory":      int((cc or {}).get("total_inventory") or 0),
            "saves_used":                (cc or {}).get("saves_count", r["saves"]),
            "saves":                          r["saves"],
            "gross_cents":                r["gross_cents"],
            "merchant_cents":          r["merchant_cents"],
            "platform_cents":          r["platform_cents"],
            "last_save_at":            _iso(r["last_save_at"]),
        })

    recent = await db.payment_transactions_v2.find(q).sort(
        [("created_at", -1)]).to_list(min(int(limit or 100), 500))
    serialized = []
    for d in recent:
        row = {k: v for k, v in d.items() if k != "_id"}
        for k, v in list(row.items()):
            if isinstance(v, datetime):
                row[k] = v.isoformat()
        serialized.append(row)

    total_gross = sum(r["gross_cents"] for r in per_campaign)
    total_merchant = sum(r["merchant_cents"] for r in per_campaign)
    total_platform = sum(r["platform_cents"] for r in per_campaign)
    return {
        "advertiser_id":      advertiser_id,
        "per_campaign":      enriched,
        "recent_events":      serialized,
        "totals": {"saves": sum(r["saves"] for r in per_campaign),
                              "gross_cents":    total_gross,
                              "merchant_cents": total_merchant,
                              "platform_cents": total_platform},
    }


async def list_merchant_coupon_revenue(
        db, *, merchant_id: str, limit: int = 100) -> Dict[str, Any]:
    q = {"merchant_id": merchant_id,
              "flow":              "ad4_coupon_save_split"}
    per_campaign = await db.payment_transactions_v2.aggregate([
        {"$match": q},
        {"$group": {
            "_id": "$coupon_campaign_id",
            "saves":                    {"$sum": 1},
            "gross_cents":        {"$sum": "$amount_cents"},
            "merchant_cents":  {"$sum": "$merchant_net_cents"},
            "platform_cents":  {"$sum": "$application_fee_cents"},
            "last_save_at":      {"$max": "$created_at"},
        }},
        {"$sort": {"merchant_cents": -1}},
    ]).to_list(200)

    enriched = []
    for r in per_campaign:
        cc = await db.coupon_campaigns.find_one({"campaign_id": r["_id"]},
                                                                                                                {"title": 1, "advertiser_id": 1})
        adv = None
        if (cc or {}).get("advertiser_id"):
            adv = await db.advertisers_v2.find_one(
                {"advertiser_id": cc["advertiser_id"]},
                {"name": 1, "logo_url": 1})
        enriched.append({
            "campaign_id":              r["_id"],
            "title":                          (cc or {}).get("title"),
            "advertiser_id":          (cc or {}).get("advertiser_id"),
            "advertiser_name":      (adv or {}).get("name"),
            "advertiser_logo_url": (adv or {}).get("logo_url"),
            "saves":                        r["saves"],
            "gross_cents":              r["gross_cents"],
            "merchant_cents":        r["merchant_cents"],
            "platform_cents":        r["platform_cents"],
            "last_save_at":          _iso(r["last_save_at"]),
        })

    since = _now() - timedelta(days=30)
    rolling = await db.payment_transactions_v2.aggregate([
        {"$match": {**q, "created_at": {"$gte": since}}},
        {"$group": {"_id": None,
                                "saves":                    {"$sum": 1},
                                "merchant_cents":    {"$sum": "$merchant_net_cents"}}},
    ]).to_list(1)
    r30 = rolling[0] if rolling else {"saves": 0, "merchant_cents": 0}

    return {
        "merchant_id":  merchant_id,
        "per_campaign":  enriched,
        "totals": {"saves":                sum(r["saves"] for r in per_campaign),
                              "gross_cents":    sum(r["gross_cents"] for r in per_campaign),
                              "merchant_cents": sum(r["merchant_cents"] for r in per_campaign),
                              "platform_cents": sum(r["platform_cents"] for r in per_campaign)},
        "rolling_30d": {"saves": r30.get("saves", 0),
                                          "merchant_cents": r30.get("merchant_cents", 0)},
    }


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    # Convenience derived fields.
    inv   = int(out.get("total_inventory") or 0)
    saves = int(out.get("saves_count") or 0)
    out["inventory_remaining"] = max(0, inv - saves)
    return out


__all__ = [
    "ensure_ad4_indexes",
    "create_coupon_campaign", "patch_coupon_campaign",
    "publish_coupon_campaign", "admin_review_coupon_campaign",
    "list_advertiser_coupon_campaigns", "list_admin_pending",
    "list_live_coupon_campaigns", "save_coupon_campaign",
    "list_advertiser_coupon_transactions", "list_merchant_coupon_revenue",
    "STATUSES", "EVENT_SOURCE", "COMMISSION_TXN_TYPE",
    "DEFAULT_MERCHANT_SHARE_PCT",
]
