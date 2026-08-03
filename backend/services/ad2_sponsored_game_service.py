"""Phase AD.2 — Sponsored Games Revenue Split.

Extends the AD.1 sponsored-game linkage with a per-event billing
pipeline: when a user views (impression) or plays (entry) a
sponsored PG.1 game, CPM/CPC is deducted from the advertiser wallet
and a split-routed payment_transactions_v2 row is written mirroring
the SC.3 application_fee pattern (platform_share + merchant_share).

Design notes
────────────
1. **Virtual ledger, real shape.**  We do NOT hit Stripe.Transfer on
      every impression — that would cost a real API call per event and
      is fragile at ad-serving volume.  Instead we write shape-compatible
      `payment_transactions_v2` rows (`flow="ad2_sponsored_game_split"`)
      containing `application_fee_cents` (platform) + `merchant_net_cents`
      (merchant).  Aggregation & batch transfer is out-of-scope for AD.2.
2. **Idempotent by design.**  Every event carries a client-supplied
      `event_id` (UUID); a unique-sparse index on
      `payment_transactions_v2.game_event_id` guarantees at-most-once
      billing per event.
3. **Daily cap per user per game.**  Reject 4th+ event same-day.
4. **Auto-pause on wallet exhaustion.**  When the atomic $inc dips the
      advertiser wallet below the fee, we (a) roll back the deduction,
      (b) pause the ad_campaign, (c) unlink the game_campaign so the
      sponsor banner disappears client-side.
5. **Commission %.**  Resolved via commission_service with
      `transaction_type="sponsored_game"`.  Seed row (see
      scripts/seed_ad2_commission_rule.py) uses 30% platform / 70%
      merchant.  Admin can override via merchant_commission_overrides
      or via a new PATCH endpoint.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services.commission_service import calculate_platform_fee

logger = logging.getLogger("bigfm.ad2")

# Business defaults — overridable per-campaign via game_campaigns.sponsor_*.
DEFAULT_DAILY_IMPRESSION_CAP_PER_USER = 3
DEFAULT_PAUSE_WHEN_WALLET_EMPTY = True
DEFAULT_MERCHANT_SHARE_PCT = 70  # platform_commission_percent = 30

# Event source enums for payment_transactions_v2.event_source.
EVENT_GAME_IMPRESSION = "game_impression"
EVENT_GAME_ENTRY = "game_entry"

# Transaction_type key for commission_rules lookup.
COMMISSION_TXN_TYPE = "sponsored_game"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_bucket(ts: Optional[datetime] = None) -> str:
    ts = ts or _now()
    return ts.strftime("%Y-%m-%d")


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_ad2_indexes(db) -> None:
    """Idempotent AD.2 index setup — safe to call at boot.

    We piggyback on the existing `payment_transactions_v2` collection
    (adding fields, not shape).  Unique-sparse on `game_event_id`
    provides the at-most-once billing guarantee.
    """
    try:
        await db.payment_transactions_v2.create_index(
            "game_event_id", unique=True, sparse=True,
            name="idx_ad2_game_event_id")
    except Exception as e:
        logger.warning("[ad2] game_event_id index: %s", e)
    try:
        await db.payment_transactions_v2.create_index(
            [("event_source", 1), ("created_at", -1)],
            name="idx_ad2_event_source_ts")
    except Exception as e:
        logger.warning("[ad2] event_source ts index: %s", e)
    try:
        # Merchant/advertiser lookups on the split ledger.
        await db.payment_transactions_v2.create_index(
            [("advertiser_id", 1), ("event_source", 1), ("created_at", -1)],
            name="idx_ad2_adv_event_ts", sparse=True)
        await db.payment_transactions_v2.create_index(
            [("merchant_id", 1), ("event_source", 1), ("created_at", -1)],
            name="idx_ad2_mer_event_ts", sparse=True)
    except Exception as e:
        logger.warning("[ad2] adv/mer event index: %s", e)


# ─── Denormalization: AD.1 approve → game_campaigns ─────────────
async def denormalize_sponsor_to_game_campaign(
    db, *, ad_campaign_id: str) -> Dict[str, Any]:
    """Called from AD.1 `approve_campaign` right after the
    `sponsored_by_ad_campaign_id` stamp — copies CPM/CPC + defaults onto
    the target game_campaign so the impression endpoint can bill without
    a second join.
    """
    ad = await db.ad_campaigns_v2.find_one({"campaign_id": ad_campaign_id})
    if not ad or ad.get("campaign_type") != "sponsored_game":
        return {"skipped": True, "reason": "not_sponsored_game"}
    gc_id = (ad.get("creative") or {}).get("sponsored_game_campaign_id")
    if not gc_id:
        return {"skipped": True, "reason": "no_game_campaign_id"}
    updates = {
        "sponsor_advertiser_id":                        ad.get("advertiser_id"),
        "sponsor_pricing_model":                          ad.get("pricing_model") or "cpm",
        "sponsor_cpm_bid_cents":                        int(ad.get("cpm_bid_cents") or 0),
        "sponsor_cpc_bid_cents":                        int(ad.get("cpc_bid_cents") or 0),
        # New knobs are additive and use documented defaults so existing
        # rows behave predictably on the very first billing tick.
        "sponsor_daily_impression_cap_per_user":
            DEFAULT_DAILY_IMPRESSION_CAP_PER_USER,
        "sponsor_pause_when_wallet_empty":
            DEFAULT_PAUSE_WHEN_WALLET_EMPTY,
        "sponsor_paused_reason":                          None,
        "sponsor_denormalized_at":                      _now(),
    }
    await db.game_campaigns.update_one({"campaign_id": gc_id},
                                                                                {"$set": updates})
    return {"skipped": False, "game_campaign_id": gc_id, **updates}


# ─── Fee resolver (CPM or CPC) ──────────────────────────────────
def _fee_cents_for(pricing_model: str,
                                        cpm_bid_cents: int,
                                        cpc_bid_cents: int,
                                        event_type: str) -> int:
    """Compute the per-event gross fee in cents.

    - CPM impression → cpm_bid / 1000  (integer floor; sub-milli-dollar CPM
                                                                    events roll to 0 and are logged but not billed)
    - CPC entry      → cpc_bid
    - All other combos are no-op (returns 0)
    """
    if pricing_model == "cpm" and event_type == EVENT_GAME_IMPRESSION:
        return int((cpm_bid_cents or 0) // 1000)
    if pricing_model == "cpc" and event_type == EVENT_GAME_ENTRY:
        return int(cpc_bid_cents or 0)
    return 0


# ─── Cap enforcement ────────────────────────────────────────────
async def _within_daily_cap(db, *, game_campaign_id: str, user_id: str,
                                                              event_type: str, cap: int) -> bool:
    """True if the user is under the per-user-per-game per-day cap for
    the given event_type.
    """
    if cap <= 0:
        return True
    start_of_day = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    n = await db.payment_transactions_v2.count_documents({
        "event_source":            event_type,
        "game_campaign_id":  game_campaign_id,
        "customer_user_id":  user_id,
        "created_at":              {"$gte": start_of_day},
    })
    return n < cap


# ─── Core: record + split-route one game event ──────────────────
async def record_game_event(db, *, game_campaign_id: str,
                                                              user_id: str, event_type: str,
                                                              event_id: Optional[str] = None,
                                                              placement: Optional[str] = None) -> Dict[str, Any]:
    """Record one sponsored-game event and route the split.

    Return shape:
        {ok, billed, reason?, transaction_id?, gross_cents, merchant_cents,
          platform_cents, wallet_balance_cents_after, campaign_paused}

    Non-billed outcomes are legitimate (unsponsored, no-CPM combo, cap hit,
    already recorded).  Only wallet exhaustion pauses the ad_campaign.
    """
    event_id = event_id or _gen("gev")
    event_type = event_type if event_type in (EVENT_GAME_IMPRESSION,
                                                                                              EVENT_GAME_ENTRY) else EVENT_GAME_IMPRESSION

    # ─ 1. Load game_campaign ──────────────────────────────
    gc = await db.game_campaigns.find_one({"campaign_id": game_campaign_id})
    if not gc:
        return {"ok": False, "billed": False, "reason": "game_campaign_not_found"}

    ad_campaign_id = gc.get("sponsored_by_ad_campaign_id")
    if not ad_campaign_id:
        return {"ok": True, "billed": False, "reason": "not_sponsored"}

    # ─ 2. Idempotency check ───────────────────────────────
    dup = await db.payment_transactions_v2.find_one(
        {"game_event_id": event_id}, {"transaction_id": 1, "_id": 0})
    if dup:
        return {"ok": True, "billed": False, "reason": "duplicate_event",
                      "transaction_id": dup.get("transaction_id")}

    # ─ 3. Load ad_campaign + advertiser ───────────────────
    ad = await db.ad_campaigns_v2.find_one({"campaign_id": ad_campaign_id})
    if not ad:
        return {"ok": True, "billed": False, "reason": "ad_campaign_missing"}
    if ad.get("status") not in ("active",):
        return {"ok": True, "billed": False, "reason": f"ad_campaign_{ad.get('status')}"}

    pricing_model = (gc.get("sponsor_pricing_model")
                                        or ad.get("pricing_model") or "cpm")
    cpm = int(gc.get("sponsor_cpm_bid_cents")
                          or ad.get("cpm_bid_cents") or 0)
    cpc = int(gc.get("sponsor_cpc_bid_cents")
                          or ad.get("cpc_bid_cents") or 0)
    gross_cents = _fee_cents_for(pricing_model, cpm, cpc, event_type)
    if gross_cents <= 0:
        return {"ok": True, "billed": False,
                      "reason": "no_billable_combo",
                      "pricing_model": pricing_model, "event_type": event_type}

    # ─ 4. Enforce daily cap ───────────────────────────────
    cap = int(gc.get("sponsor_daily_impression_cap_per_user")
                        or DEFAULT_DAILY_IMPRESSION_CAP_PER_USER)
    if not await _within_daily_cap(db, game_campaign_id=game_campaign_id,
                                                                            user_id=user_id, event_type=event_type,
                                                                            cap=cap):
        return {"ok": True, "billed": False, "reason": "daily_cap_reached",
                      "cap": cap}

    # ─ 5. Compute split via commission_service ────────────
    merchant_id = gc.get("merchant_id")
    biz = None
    if merchant_id:
        biz = await db.businesses.find_one(
            {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]},
            {"category": 1, "market": 1, "stripe_connect_account_id": 1,
              "name": 1})
    biz = biz or {}
    # Sponsored-game split is not category-specific — resolve against the
    # `*/sponsored_game/*` rule seeded at boot.  Passing the merchant's
    # actual category would silently fall through to the generic 10 %
    # `*/*` fallback because the resolver's Step 3/4 requires an EXACT
    # category match.  We still pass `merchant_id` so a per-merchant
    # override in `merchant_commission_overrides` wins (Step 1/2).
    fee_view = await calculate_platform_fee(
        db, merchant_id=merchant_id,
        category="*",
        transaction_type=COMMISSION_TXN_TYPE,
        amount_cents=gross_cents,
        market=None, campaign_type="sponsored_game",
        write_audit=False)
    platform_cents = int(fee_view.get("commission_cents") or 0)
    # Guardrail — never let commission exceed gross.
    platform_cents = max(0, min(platform_cents, gross_cents))
    merchant_cents = gross_cents - platform_cents

    # ─ 6. Atomic wallet deduction ─────────────────────────
    advertiser_id = ad.get("advertiser_id")
    adv_upd = await db.advertisers_v2.find_one_and_update(
        {"advertiser_id": advertiser_id,
          "budget_available_cents": {"$gte": gross_cents}},
        {"$inc": {"budget_available_cents": -gross_cents,
                          "budget_spent_cents":         gross_cents},
          "$set": {"updated_at": _now()}},
        return_document=True)
    if not adv_upd:
        # Wallet couldn't cover the event — auto-pause the ad_campaign
        # and unlink the game_campaign so branding falls off.
        await _pause_for_wallet_exhaustion(
            db, ad_campaign_id=ad_campaign_id,
            game_campaign_id=game_campaign_id)
        return {"ok": True, "billed": False,
                      "reason": "wallet_exhausted", "campaign_paused": True}

    wallet_balance_after = int(adv_upd.get("budget_available_cents") or 0)

    # ─ 7. Persist the split row (shape-compatible w/ SC.5) ──
    txn_id = _gen("tx_ad2")
    now = _now()
    doc = {
        "_id":                                    txn_id,
        "transaction_id":                txn_id,
        "flow":                                  "ad2_sponsored_game_split",
        "event_source":                    event_type,
        "game_event_id":                  event_id,   # unique-sparse dedup
        "game_campaign_id":            game_campaign_id,
        "ad_campaign_id":                ad_campaign_id,
        "advertiser_id":                  advertiser_id,
        "merchant_id":                      merchant_id,
        "customer_user_id":            user_id,
        "placement":                          placement or event_type,
        "pricing_model":                  pricing_model,
        "cpm_bid_cents":                    cpm,
        "cpc_bid_cents":                    cpc,
        # Money movement (mirrors SC.5 keys).
        "amount_cents":                    gross_cents,
        "subtotal_cents":                gross_cents,
        "currency":                            "USD",
        "application_fee_cents":  platform_cents,
        "merchant_net_cents":        merchant_cents,
        "computed_percent":            fee_view.get("computed_percent"),
        "commission_rule_id":        fee_view.get("rule_id"),
        "commission_override_id":  fee_view.get("override_id"),
        "commission_source":            fee_view.get("source"),
        # Bookkeeping stubs — nothing hits Stripe; real transfer occurs
        # via a periodic reconciliation sweep (out of scope for AD.2).
        # NOTE: the `stripe_payment_intent_id_1` index on payment_transactions_v2
        # is `unique: True` but NOT sparse (pre-existing from SC.5).  Two
        # AD.2 rows with `None` would collide, so we synthesize a namespaced
        # placeholder mirroring the MER.3 zero-charge pattern.
        "stripe_payment_intent_id": f"ad2_{txn_id}",
        "stripe_charge_id":              None,
        "stripe_connected_account_id":
            biz.get("stripe_connect_account_id"),
        "status":                              "succeeded",
        "wallet_balance_after_cents": wallet_balance_after,
        "created_at":                      now,
        "succeeded_at":                  now,
    }
    try:
        await db.payment_transactions_v2.insert_one(doc)
    except Exception as e:
        # Roll back the wallet deduction on any insert failure so we
        # never bill an advertiser without a ledger row.  Idempotency
        # on `game_event_id` already prevents double-billing when the
        # same event is retried after a rollback.
        logger.exception("[ad2] insert failed — rolling back wallet")
        await db.advertisers_v2.update_one(
            {"advertiser_id": advertiser_id},
            {"$inc": {"budget_available_cents":     gross_cents,
                              "budget_spent_cents":            -gross_cents},
              "$set": {"updated_at": _now()}})
        return {"ok": False, "billed": False,
                      "reason": "ledger_insert_failed",
                      "detail": str(e)[:120]}

    # ─ 8. Bump ad_campaign spent + impression counters ───
    inc_fields: Dict[str, int] = {"budget_spent_cents": gross_cents}
    if event_type == EVENT_GAME_IMPRESSION:
        inc_fields["impressions_count"] = 1
    else:
        inc_fields["clicks_count"] = 1
    await db.ad_campaigns_v2.update_one(
        {"campaign_id": ad_campaign_id},
        {"$inc": inc_fields, "$set": {"updated_at": now}})

    # ─ 9. Auto-pause if wallet hit floor exactly ─────────
    campaign_paused = False
    if (wallet_balance_after <= 0 and
                gc.get("sponsor_pause_when_wallet_empty",
                              DEFAULT_PAUSE_WHEN_WALLET_EMPTY)):
        await _pause_for_wallet_exhaustion(
            db, ad_campaign_id=ad_campaign_id,
            game_campaign_id=game_campaign_id)
        campaign_paused = True

    return {
        "ok":                                          True,
        "billed":                                    True,
        "transaction_id":                    txn_id,
        "gross_cents":                          gross_cents,
        "merchant_cents":                    merchant_cents,
        "platform_cents":                    platform_cents,
        "wallet_balance_cents_after": wallet_balance_after,
        "campaign_paused":                  campaign_paused,
    }


async def _pause_for_wallet_exhaustion(db, *, ad_campaign_id: str,
                                                                                        game_campaign_id: str) -> None:
    now = _now()
    await db.ad_campaigns_v2.update_one(
        {"campaign_id": ad_campaign_id, "status": {"$in": ["active"]}},
        {"$set": {"status":                                "paused",
                          "paused_at":                          now,
                          "auto_paused_reason":        "wallet_exhausted",
                          "updated_at":                        now}})
    await db.game_campaigns.update_one(
        {"campaign_id": game_campaign_id},
        {"$set": {"sponsored_by_ad_campaign_id": None,
                          "sponsor_paused_reason":            "wallet_exhausted",
                          "sponsor_paused_at":                    now,
                          "updated_at":                                    now}})
    logger.info("[ad2] auto-paused ad_campaign=%s game_campaign=%s "
                            "reason=wallet_exhausted", ad_campaign_id, game_campaign_id)


# ─── Read APIs (aggregations for advertiser + merchant views) ──
async def list_advertiser_game_transactions(db, *, advertiser_id: str,
                                                                                                      limit: int = 100) -> Dict[str, Any]:
    """Return per-event spend history for an advertiser + rolling totals.
    Only reads rows this service wrote (`flow="ad2_sponsored_game_split"`).
    """
    q = {"advertiser_id": advertiser_id,
              "flow":                    "ad2_sponsored_game_split"}
    docs = await db.payment_transactions_v2.find(q).sort(
        [("created_at", -1)]).to_list(min(int(limit or 100), 500))

    # Aggregate roll-ups per game_campaign for dashboard summary cards.
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$game_campaign_id",
            "events":                            {"$sum": 1},
            "impressions":                {"$sum": {"$cond": [
                {"$eq": ["$event_source", EVENT_GAME_IMPRESSION]}, 1, 0]}},
            "entries":                        {"$sum": {"$cond": [
                {"$eq": ["$event_source", EVENT_GAME_ENTRY]},        1, 0]}},
            "gross_cents":                {"$sum": "$amount_cents"},
            "merchant_cents":          {"$sum": "$merchant_net_cents"},
            "platform_cents":          {"$sum": "$application_fee_cents"},
            "last_event_at":            {"$max": "$created_at"},
        }},
        {"$sort": {"last_event_at": -1}},
    ]
    per_campaign = await db.payment_transactions_v2.aggregate(
        pipeline).to_list(200)
    # Enrich each row with game_campaign name.
    enriched: List[Dict[str, Any]] = []
    for r in per_campaign:
        gc = await db.game_campaigns.find_one(
            {"campaign_id": r["_id"]},
            {"name": 1, "merchant_id": 1, "status": 1, "sponsor_paused_reason": 1})
        merchant_name = None
        if gc and gc.get("merchant_id"):
            biz = await db.businesses.find_one(
                {"$or": [{"business_id": gc["merchant_id"]},
                                {"_id": gc["merchant_id"]}]},
                {"name": 1})
            merchant_name = (biz or {}).get("name")
        enriched.append({
            "game_campaign_id":    r["_id"],
            "game_campaign_name":  (gc or {}).get("name"),
            "merchant_id":              (gc or {}).get("merchant_id"),
            "merchant_name":          merchant_name,
            "status":                          (gc or {}).get("status"),
            "sponsor_paused_reason": (gc or {}).get("sponsor_paused_reason"),
            "events":                          r["events"],
            "impressions":              r["impressions"],
            "entries":                      r["entries"],
            "gross_cents":              r["gross_cents"],
            "merchant_cents":          r["merchant_cents"],
            "platform_cents":          r["platform_cents"],
            "last_event_at":            r["last_event_at"].isoformat()
                                                          if isinstance(r["last_event_at"], datetime) else None,
        })

    # Serialize the raw row list.
    serialized = []
    for d in docs:
        row = {k: v for k, v in d.items() if k not in ("_id",)}
        for k, v in list(row.items()):
            if isinstance(v, datetime):
                row[k] = v.isoformat()
        serialized.append(row)

    total_gross = sum(r["gross_cents"] for r in per_campaign)
    total_merchant = sum(r["merchant_cents"] for r in per_campaign)
    total_platform = sum(r["platform_cents"] for r in per_campaign)
    return {
        "advertiser_id":  advertiser_id,
        "per_campaign":  enriched,
        "recent_events":  serialized,
        "totals": {
            "events":                sum(r["events"] for r in per_campaign),
            "impressions":  sum(r["impressions"] for r in per_campaign),
            "entries":          sum(r["entries"]      for r in per_campaign),
            "gross_cents":  total_gross,
            "merchant_cents": total_merchant,
            "platform_cents": total_platform,
        },
    }


async def list_merchant_game_revenue(db, *, merchant_id: str,
                                                                                    limit: int = 100) -> Dict[str, Any]:
    """Return inbound game-sponsorship revenue for a merchant."""
    q = {"merchant_id": merchant_id,
              "flow":              "ad2_sponsored_game_split"}
    docs = await db.payment_transactions_v2.find(q).sort(
        [("created_at", -1)]).to_list(min(int(limit or 100), 500))

    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$game_campaign_id",
            "events":                        {"$sum": 1},
            "gross_cents":            {"$sum": "$amount_cents"},
            "merchant_cents":      {"$sum": "$merchant_net_cents"},
            "platform_cents":      {"$sum": "$application_fee_cents"},
            "last_event_at":        {"$max": "$created_at"},
        }},
        {"$sort": {"merchant_cents": -1}},
    ]
    per_campaign = await db.payment_transactions_v2.aggregate(
        pipeline).to_list(200)

    enriched: List[Dict[str, Any]] = []
    for r in per_campaign:
        gc = await db.game_campaigns.find_one(
            {"campaign_id": r["_id"]},
            {"name": 1, "sponsor_advertiser_id": 1})
        adv = None
        if gc and gc.get("sponsor_advertiser_id"):
            adv = await db.advertisers_v2.find_one(
                {"advertiser_id": gc["sponsor_advertiser_id"]},
                {"name": 1, "logo_url": 1})
        enriched.append({
            "game_campaign_id":            r["_id"],
            "game_campaign_name":        (gc or {}).get("name"),
            "advertiser_id":                  (gc or {}).get("sponsor_advertiser_id"),
            "advertiser_name":              (adv or {}).get("name"),
            "advertiser_logo_url":      (adv or {}).get("logo_url"),
            "events":                                r["events"],
            "gross_cents":                      r["gross_cents"],
            "merchant_cents":                r["merchant_cents"],
            "platform_cents":                r["platform_cents"],
            "last_event_at":                    r["last_event_at"].isoformat()
                                                                    if isinstance(r["last_event_at"], datetime) else None,
        })

    serialized = []
    for d in docs:
        row = {k: v for k, v in d.items() if k not in ("_id",)}
        for k, v in list(row.items()):
            if isinstance(v, datetime):
                row[k] = v.isoformat()
        serialized.append(row)

    # Rolling 30-day window headline number for the widget.
    since = _now() - timedelta(days=30)
    rolling = await db.payment_transactions_v2.aggregate([
        {"$match": {**q, "created_at": {"$gte": since}}},
        {"$group": {"_id": None,
                                "events":                {"$sum": 1},
                                "merchant_cents":  {"$sum": "$merchant_net_cents"}}},
    ]).to_list(1)
    r30 = rolling[0] if rolling else {"events": 0, "merchant_cents": 0}

    return {
        "merchant_id":  merchant_id,
        "per_campaign":  enriched,
        "recent_events":  serialized,
        "totals": {
            "events":                sum(r["events"] for r in per_campaign),
            "gross_cents":  sum(r["gross_cents"] for r in per_campaign),
            "merchant_cents": sum(r["merchant_cents"] for r in per_campaign),
            "platform_cents": sum(r["platform_cents"] for r in per_campaign),
        },
        "rolling_30d": {
            "events":                r30.get("events", 0),
            "merchant_cents": r30.get("merchant_cents", 0),
        },
    }


__all__ = [
    "ensure_ad2_indexes",
    "denormalize_sponsor_to_game_campaign",
    "record_game_event",
    "list_advertiser_game_transactions",
    "list_merchant_game_revenue",
    "EVENT_GAME_IMPRESSION",
    "EVENT_GAME_ENTRY",
    "COMMISSION_TXN_TYPE",
    "DEFAULT_MERCHANT_SHARE_PCT",
]
