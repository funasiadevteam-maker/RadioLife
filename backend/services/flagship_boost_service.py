"""Phase F — Monetization M4: Boosted Flagship Slots.

Advertisers bid to temporarily boost their brand into a flagship
station's slot (primary/secondary/tertiary) in a specific region for a
bounded time window.  Admin creates the auction slot, advertisers bid,
admin approves the winner (with a Stripe charge), and the winning
`activation` row drives what the listener runtime shows.

Reuses:
 - AD.8 (`auction_insights_service`) — LOSS logging + rank/shortfall
    exposure with rounded-nearest-10% competitor privacy.
 - AD.11-style `payment_transactions_v2` accounting rows (advertiser
    pays the platform directly; no external merchant recipient, so we
    omit `transfer_data.destination` and record
    `application_fee_cents = bid × 20%` as reporting-only metadata).
 - Notification dispatcher recipes.

Collections:
 - flagship_boost_slots        — admin-created auction slots.
 - flagship_boost_bids          — advertiser submissions.
 - flagship_boost_activations — settled winners driving the UI.

Endpoints live in routes/flagship_boosts.py.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services import auction_insights_service as _ai
from services.notification_trigger_dispatcher import dispatch_event

logger = logging.getLogger("bigfm.flagship_boost")


# ── Constants ──────────────────────────────────────────────────
FLAGSHIP_BOOST_FEE_PCT = 20  # 20% platform take (recorded on tx row)
STATION_SLOTS      = ("primary", "secondary", "tertiary")
STATUS_SLOT_ACTIVE = ("open",)
STATUS_BID_ACTIVE   = ("pending", "winning")

_now_fn = lambda: datetime.now(timezone.utc)


def _now() -> datetime:
    return _now_fn()


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


# ── Indexes ────────────────────────────────────────────────────
async def ensure_flagship_boost_indexes(db) -> None:
    try:
        await db.flagship_boost_slots.create_index("id", unique=True,
                                                                                      name="fbs_id_uniq")
        await db.flagship_boost_slots.create_index(
            [("region_code", 1), ("station_slot", 1), ("status", 1)],
            name="fbs_region_slot_status")
        await db.flagship_boost_slots.create_index(
            [("status", 1), ("created_at", -1)], name="fbs_status_created")

        await db.flagship_boost_bids.create_index("id", unique=True,
                                                                                    name="fbb_id_uniq")
        await db.flagship_boost_bids.create_index(
            [("slot_id", 1), ("status", 1)], name="fbb_slot_status")
        await db.flagship_boost_bids.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="fbb_adv_status")
        # Enforce: one active (pending|winning) bid per (slot, advertiser).
        # Partial-filter unique index — Mongo supports this since 3.2.
        await db.flagship_boost_bids.create_index(
            [("slot_id", 1), ("advertiser_business_id", 1)],
            partialFilterExpression={"status": {"$in": ["pending", "winning"]}},
            unique=True, name="fbb_adv_active_uniq")

        await db.flagship_boost_activations.create_index("id", unique=True,
                                                                                                        name="fba_id_uniq")
        await db.flagship_boost_activations.create_index(
            [("region_code", 1), ("active_until", 1)], name="fba_region_until")
        await db.flagship_boost_activations.create_index(
            [("station_id", 1), ("status", 1)], name="fba_station_status")
        await db.flagship_boost_activations.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="fba_adv_status")

        # Impression telemetry — dedupe per (user, activation, bucket).
        await db.flagship_boost_impressions.create_index(
            [("activation_id", 1), ("user_id", 1), ("bucket_key", 1)],
            unique=True, name="fbi_dedupe")
    except Exception as e:
        logger.warning("[flagship_boost] index setup: %s", e)


# ── Serialisation helpers ──────────────────────────────────────
def _shape_slot(sp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "slot_id":                          sp.get("id"),
        "region_code":                  sp.get("region_code"),
        "station_slot":                sp.get("station_slot"),
        "start_at":                        _iso(sp.get("start_at")),
        "end_at":                            _iso(sp.get("end_at")),
        "floor_price_cents":        int(sp.get("floor_price_cents") or 0),
        "currency":                        (sp.get("currency") or "usd").lower(),
        "status":                            sp.get("status"),
        "created_at":                    _iso(sp.get("created_at")),
        "notes":                            sp.get("notes"),
    }


def _shape_bid_public(b: Dict[str, Any],
                                            include_advertiser: bool = False) -> Dict[str, Any]:
    """Bid shape safe to return to the owning advertiser.  Never
    exposes competitor advertiser_business_id unless include_advertiser
    (admin view)."""
    out = {
        "bid_id":                              b.get("id"),
        "slot_id":                            b.get("slot_id"),
        "bid_amount_cents":            int(b.get("bid_amount_cents") or 0),
        "currency":                          (b.get("currency") or "usd").lower(),
        "creative":                          b.get("creative") or {},
        "status":                              b.get("status"),
        "submitted_at":                  _iso(b.get("submitted_at")),
        "decided_at":                      _iso(b.get("decided_at")),
        "decision_note":                b.get("decision_note"),
        "payment_transaction_id":  b.get("payment_transaction_id"),
    }
    if include_advertiser:
        out["advertiser_business_id"] = b.get("advertiser_business_id")
        out["decided_by_user_id"]      = b.get("decided_by_user_id")
    return out


def _shape_activation(a: Dict[str, Any],
                                              impression_count: int = 0
                                              ) -> Dict[str, Any]:
    return {
        "activation_id":                          a.get("id"),
        "slot_id":                                    a.get("slot_id"),
        "winning_bid_id":                        a.get("winning_bid_id"),
        "region_code":                            a.get("region_code"),
        "station_id":                              a.get("station_id"),
        "station_slot":                          a.get("station_slot"),
        "advertiser_business_id":        a.get("advertiser_business_id"),
        "active_from":                            _iso(a.get("active_from")),
        "active_until":                          _iso(a.get("active_until")),
        "status":                                      a.get("status"),
        "stripe_charge_id":                    a.get("stripe_charge_id"),
        "stripe_payment_intent_id":  a.get("stripe_payment_intent_id"),
        "application_fee_cents":            int(a.get("application_fee_cents") or 0),
        "amount_cents":                          int(a.get("amount_cents") or 0),
        "currency":                                  (a.get("currency") or "usd").lower(),
        "creative":                                  a.get("creative") or {},
        "created_at":                              _iso(a.get("created_at")),
        "impression_count":                    int(impression_count),
    }


def _round_up_10pct(cents: int) -> int:
    """Round a cent amount UP to the nearest 10% bucket, preserving
    competitor privacy.  E.g. 1234 → 1400, 500 → 500, 8000 → 8000."""
    if cents <= 0:
        return 0
    if cents < 100:
        return int((cents + 9) // 10 * 10)
    # 10% of the ORDER OF MAGNITUDE (nearest power of 10 divided by 10)
    magnitude = 10 ** max(0, len(str(cents)) - 2)
    bucket = magnitude * 10  # e.g. 1234 → magnitude=100 → bucket=1000? no
    # Simpler: round up to nearest 10% of the value itself.
    # We want 1234 -> 1400 (round up to next multiple of 10% of 1000-ish).
    # Use: bucket = 10^(floor(log10(x)))   e.g. 1234 → 1000 → step=100
    step = magnitude
    return int((cents + step - 1) // step * step)


# ── Slot admin operations ─────────────────────────────────────
async def create_slot(db, *,
                                            region_code: str,
                                            station_slot: str,
                                            start_at: datetime,
                                            end_at: datetime,
                                            floor_price_cents: int,
                                            currency: str = "usd",
                                            notes: Optional[str] = None,
                                            admin_user_id: str
                                            ) -> Dict[str, Any]:
    if station_slot not in STATION_SLOTS:
        raise ValueError("invalid_station_slot")
    if floor_price_cents < 1:
        raise ValueError("floor_price_too_low")
    start_at = _aware(start_at); end_at = _aware(end_at)
    if not (start_at and end_at) or end_at <= start_at:
        raise ValueError("invalid_time_window")
    now = _now()
    slot_id = _gen("fbslot")
    doc = {
        "_id":                              slot_id,
        "id":                                slot_id,
        "region_code":                (region_code or "").strip().lower(),
        "station_slot":              station_slot,
        "start_at":                      start_at,
        "end_at":                          end_at,
        "floor_price_cents":      int(floor_price_cents),
        "currency":                      (currency or "usd").lower(),
        "status":                          "open",
        "created_at":                  now,
        "created_by_user_id":  admin_user_id,
        "notes":                          notes,
    }
    await db.flagship_boost_slots.insert_one(doc)
    return _shape_slot(doc)


async def list_slots(db, *,
                                          region_code: Optional[str] = None,
                                          status: Optional[str] = None,
                                          limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if region_code:
        q["region_code"] = region_code.strip().lower()
    if status:
        q["status"] = status
    out: List[Dict[str, Any]] = []
    async for sp in db.flagship_boost_slots.find(q)\
                                        .sort("created_at", -1).limit(limit):
        s = _shape_slot(sp)
        s["bid_count"] = await db.flagship_boost_bids.count_documents(
            {"slot_id": sp["id"]})
        top = await db.flagship_boost_bids.find_one(
            {"slot_id": sp["id"],
              "status": {"$in": ["pending", "winning", "approved"]}},
            sort=[("bid_amount_cents", -1)])
        s["top_bid_cents"] = int(top.get("bid_amount_cents")) if top else 0
        out.append(s)
    return out


async def get_slot(db, *, slot_id: str,
                                      viewer_admin: bool = False) -> Optional[Dict[str, Any]]:
    sp = await db.flagship_boost_slots.find_one({"id": slot_id})
    if not sp:
        return None
    bids = []
    async for b in db.flagship_boost_bids.find({"slot_id": slot_id})\
                                                                                .sort("bid_amount_cents", -1):
        bids.append(_shape_bid_public(b, include_advertiser=viewer_admin))
    return {"slot": _shape_slot(sp), "bids": bids,
                    "bid_count": len(bids)}


async def edit_slot(db, *, slot_id: str, patch: Dict[str, Any],
                                        admin_user_id: str) -> Dict[str, Any]:
    sp = await db.flagship_boost_slots.find_one({"id": slot_id})
    if not sp:
        raise ValueError("slot_not_found")
    # Refuse edits if any bid has already been decided.
    n_decided = await db.flagship_boost_bids.count_documents(
        {"slot_id": slot_id,
          "status": {"$in": ["approved", "rejected", "outbid"]}})
    if n_decided > 0:
        raise ValueError("slot_has_decisions")
    allowed = {"start_at", "end_at", "floor_price_cents", "notes",
                        "region_code", "station_slot", "currency"}
    upd = {}
    for k, v in patch.items():
        if k not in allowed:
            continue
        if k in ("start_at", "end_at") and isinstance(v, datetime):
            upd[k] = _aware(v)
        elif k == "region_code":
            upd[k] = (v or "").strip().lower()
        elif k == "currency":
            upd[k] = (v or "usd").lower()
        elif k == "station_slot":
            if v not in STATION_SLOTS:
                raise ValueError("invalid_station_slot")
            upd[k] = v
        elif k == "floor_price_cents":
            upd[k] = int(v)
        else:
            upd[k] = v
    if not upd:
        return _shape_slot(sp)
    upd["updated_at"] = _now()
    upd["updated_by_user_id"] = admin_user_id
    await db.flagship_boost_slots.update_one(
        {"id": slot_id}, {"$set": upd})
    sp = await db.flagship_boost_slots.find_one({"id": slot_id})
    return _shape_slot(sp)


async def close_slot(db, *, slot_id: str,
                                          admin_user_id: str) -> Dict[str, Any]:
    sp = await db.flagship_boost_slots.find_one({"id": slot_id})
    if not sp:
        raise ValueError("slot_not_found")
    if sp["status"] not in ("open",):
        raise ValueError(f"slot_{sp['status']}")
    await db.flagship_boost_slots.update_one(
        {"id": slot_id},
        {"$set": {"status": "closed", "closed_at": _now(),
                          "closed_by_user_id": admin_user_id}})
    return _shape_slot(
        await db.flagship_boost_slots.find_one({"id": slot_id}))


# ── Advertiser bid operations ────────────────────────────────
async def submit_bid(db, *,
                                          slot_id: str,
                                          advertiser_business_id: str,
                                          bid_amount_cents: int,
                                          creative: Dict[str, Any],
                                          user_id: str) -> Dict[str, Any]:
    sp = await db.flagship_boost_slots.find_one({"id": slot_id})
    if not sp:
        raise ValueError("slot_not_found")
    if sp["status"] != "open":
        raise ValueError(f"slot_{sp['status']}")
    if bid_amount_cents < int(sp.get("floor_price_cents") or 0):
        raise ValueError("bid_below_floor")
    # Creative sanity check.
    st_id = (creative or {}).get("station_id_to_promote")
    if not st_id:
        raise ValueError("missing_station_id_to_promote")
    if not (creative or {}).get("display_headline"):
        raise ValueError("missing_display_headline")

    # Duplicate-active-bid protection (unique index also enforces this).
    dup = await db.flagship_boost_bids.find_one(
        {"slot_id": slot_id,
          "advertiser_business_id": advertiser_business_id,
          "status": {"$in": ["pending", "winning"]}})
    if dup:
        raise ValueError("duplicate_active_bid")

    bid_id = _gen("fbbid")
    now = _now()
    doc = {
        "_id":                                          bid_id,
        "id":                                            bid_id,
        "slot_id":                                    slot_id,
        "advertiser_business_id":        advertiser_business_id,
        "bid_amount_cents":                    int(bid_amount_cents),
        "currency":                                  (sp.get("currency") or "usd").lower(),
        "creative":                                  {
            "station_id_to_promote":  st_id,
            "display_headline":            (creative.get("display_headline") or "")[:120],
            "subtext":                                (creative.get("subtext") or "")[:200],
            "badge_color":                        (creative.get("badge_color") or "orange"),
        },
        "status":                                      "pending",
        "submitted_at":                          now,
        "submitted_by_user_id":            user_id,
    }
    await db.flagship_boost_bids.insert_one(doc)
    # Fire confirmation notification.
    try:
        await dispatch_event(
            db, event_name="flagship_boost_bid_submitted",
            user_id=user_id,
            payload={"bid_id": bid_id, "slot_id": slot_id,
                              "advertiser_business_id": advertiser_business_id,
                              "bid_amount_cents": bid_amount_cents,
                              "region_code": sp["region_code"],
                              "station_slot": sp["station_slot"]})
    except Exception:
        pass
    return _shape_bid_public(doc, include_advertiser=True)


async def list_my_bids(db, *,
                                            advertiser_business_id: str,
                                            status: Optional[str] = None,
                                            limit: int = 100
                                            ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"advertiser_business_id": advertiser_business_id}
    if status:
        q["status"] = status
    items = []
    async for b in db.flagship_boost_bids.find(q)\
                                                                              .sort("submitted_at", -1).limit(limit):
        items.append(_shape_bid_public(b, include_advertiser=True))
    return items


async def withdraw_bid(db, *,
                                              bid_id: str,
                                              advertiser_business_id: str
                                              ) -> Dict[str, Any]:
    b = await db.flagship_boost_bids.find_one({"id": bid_id})
    if not b:
        raise ValueError("bid_not_found")
    if b["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_bid_owner")
    if b["status"] != "pending":
        raise ValueError(f"bid_{b['status']}")
    await db.flagship_boost_bids.update_one(
        {"id": bid_id}, {"$set": {"status": "cancelled",
                                                            "decided_at": _now()}})
    return _shape_bid_public(
        await db.flagship_boost_bids.find_one({"id": bid_id}),
        include_advertiser=True)


# ── Auction transparency (per-bid) ─────────────────────────────
async def bid_transparency(db, *,
                                                      bid_id: str,
                                                      advertiser_business_id: str
                                                      ) -> Dict[str, Any]:
    """Rank + next-higher-rounded exposure for an advertiser's own bid.
    Never reveals competitor advertiser names or exact amounts."""
    b = await db.flagship_boost_bids.find_one({"id": bid_id})
    if not b:
        raise ValueError("bid_not_found")
    if b["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_bid_owner")
    slot_id = b["slot_id"]
    sp = await db.flagship_boost_slots.find_one({"id": slot_id})
    all_bids = await db.flagship_boost_bids.find({"slot_id": slot_id})\
                                                                            .sort("bid_amount_cents", -1).to_list(None)
    n_competing = sum(1 for x in all_bids
                                        if x["advertiser_business_id"] != advertiser_business_id)
    rank = 1
    for x in all_bids:
        if x["id"] == bid_id:
            break
        if x["bid_amount_cents"] > b["bid_amount_cents"]:
            rank += 1
    # Next-higher bid (round up to nearest 10% bucket).
    next_higher_raw = 0
    for x in all_bids:
        if x["bid_amount_cents"] > b["bid_amount_cents"]:
            next_higher_raw = x["bid_amount_cents"]
            break
    return {
        "bid_id":                              bid_id,
        "floor_price_cents":            int(sp.get("floor_price_cents") or 0),
        "your_bid_cents":                  int(b["bid_amount_cents"]),
        "competing_bid_count":        n_competing,
        "rank":                                  rank,
        "next_higher_bid_bucket": _round_up_10pct(next_higher_raw)
                                                                if next_higher_raw > 0 else 0,
        "status":                              b["status"],
    }


# ── Admin decisions ────────────────────────────────────────────
async def _charge_stripe_for_bid(db, *, bid: Dict[str, Any]
                                                                ) -> Dict[str, Any]:
    """Stripe PaymentIntent for the winning bid.  Advertiser pays the
    platform (RadioLife) directly — no `transfer_data.destination`. The
    20% platform-fee number is recorded as accounting metadata only."""
    amount = int(bid["bid_amount_cents"])
    currency = (bid.get("currency") or "usd").lower()
    app_fee = int(amount * FLAGSHIP_BOOST_FEE_PCT / 100)
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        intent = _stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            payment_method_types=["card"],
            payment_method="pm_card_visa",
            confirm=True,
            metadata={
                "bigfm_flow":                            "m4_flagship_boost",
                "bigfm_bid_id":                        bid["id"],
                "bigfm_slot_id":                      bid["slot_id"],
                "bigfm_advertiser_id":            bid["advertiser_business_id"],
                "bigfm_boost_fee_pct":            str(FLAGSHIP_BOOST_FEE_PCT),
                "bigfm_application_fee_cents": str(app_fee),
            },
            idempotency_key=f"fbb_charge_{bid['id']}")
        return {"payment_intent_id": intent.id,
                        "charge_id":                (getattr(intent, "latest_charge", None) or ""),
                        "amount_cents":        amount,
                        "application_fee_cents":  app_fee,
                        "currency":              currency,
                        "status":                  intent.status}
    except Exception as e:
        logger.exception("[flagship_boost] stripe charge failed")
        raise ValueError(f"stripe_error:{e}")


async def approve_bid(db, *,
                                            bid_id: str,
                                            admin_user_id: str,
                                            decision_note: Optional[str] = None,
                                            force: bool = False
                                            ) -> Dict[str, Any]:
    b = await db.flagship_boost_bids.find_one({"id": bid_id})
    if not b:
        raise ValueError("bid_not_found")
    if b["status"] not in ("pending", "winning"):
        raise ValueError(f"bid_{b['status']}")
    slot_id = b["slot_id"]
    sp = await db.flagship_boost_slots.find_one({"id": slot_id})
    if not sp:
        raise ValueError("slot_not_found")
    if sp["status"] not in ("open", "closed"):
        raise ValueError(f"slot_{sp['status']}")

    # Guard: if a higher-priced pending bid exists, require explicit
    # override via `force`.
    higher = await db.flagship_boost_bids.find_one(
        {"slot_id": slot_id, "status": {"$in": ["pending", "winning"]},
          "id": {"$ne": bid_id},
          "bid_amount_cents": {"$gt": int(b["bid_amount_cents"])}})
    if higher and not force:
        raise ValueError("higher_pending_bid_exists")

    # 1) Charge Stripe.
    charge = await _charge_stripe_for_bid(db, bid=b)

    now = _now()

    # 2) Write payment_transactions_v2 row (AD.11-style accounting).
    tx_id = _gen("tx_fbb")
    await db.payment_transactions_v2.insert_one({
        "_id":                                        tx_id,
        "transaction_id":                    tx_id,
        "stripe_payment_intent_id":  charge["payment_intent_id"] or tx_id,
        "flow":                                      "m4_flagship_boost",
        "event_source":                        "flagship_boost_approval",
        "advertiser_id":                      b["advertiser_business_id"],
        "bigfm_bid_id":                      bid_id,
        "bigfm_slot_id":                      slot_id,
        "amount_cents":                        charge["amount_cents"],
        "application_fee_cents":        charge["application_fee_cents"],
        "merchant_net_cents":              0,   # no external merchant
        "currency":                                charge["currency"],
        "status":                                    "posted",
        "created_at":                            now,
    })

    # 3) Flip this bid to approved, other active bids to outbid.
    await db.flagship_boost_bids.update_one(
        {"id": bid_id},
        {"$set": {"status": "approved", "decided_at": now,
                          "decided_by_user_id": admin_user_id,
                          "decision_note": decision_note,
                          "payment_transaction_id": tx_id,
                          "stripe_payment_intent_id": charge["payment_intent_id"]}})

    outbid_ids: List[str] = []
    async for x in db.flagship_boost_bids.find(
                {"slot_id": slot_id, "id": {"$ne": bid_id},
                  "status": {"$in": ["pending", "winning"]}}):
        outbid_ids.append(x["id"])
    if outbid_ids:
        await db.flagship_boost_bids.update_many(
            {"id": {"$in": outbid_ids}},
            {"$set": {"status": "outbid", "decided_at": now}})
    # Auction transparency — log each loser to auction_events with a
    # rounded-nearest-10% winner bid so the AD.8 UI can render.
    try:
        losers = []
        for x_id in outbid_ids:
            x = await db.flagship_boost_bids.find_one({"id": x_id})
            if not x:
                continue
            losers.append({"advertiser_id": x["advertiser_business_id"],
                                          "campaign_id": x["id"],
                                          "bid_cents":    int(x["bid_amount_cents"]),
                                          "reason": "higher_cpm"})
        if losers:
            _ai.fire_and_forget(_ai.log_auction_result(
                db, ad_type="m4_flagship_boost",
                slot_id=slot_id,
                winner_advertiser_id=b["advertiser_business_id"],
                winner_bid_cents=int(b["bid_amount_cents"]),
                losers=losers,
                user_context={"region_code": sp["region_code"],
                                          "station_slot": sp["station_slot"]}))
    except Exception:
        pass

    # 4) Settle the slot.
    await db.flagship_boost_slots.update_one(
        {"id": slot_id},
        {"$set": {"status": "settled", "settled_at": now,
                          "settled_bid_id": bid_id}})

    # 5) Create the activation row (live if window covers now).
    start = _aware(sp["start_at"]); end = _aware(sp["end_at"])
    activation_status = "live" if start <= now < end else \
                                            ("scheduled" if start > now else "completed")
    act_id = _gen("fbact")
    act_doc = {
        "_id":                                              act_id,
        "id":                                                act_id,
        "slot_id":                                        slot_id,
        "winning_bid_id":                            bid_id,
        "region_code":                                sp["region_code"],
        "station_slot":                              sp["station_slot"],
        "station_id":                                b["creative"]["station_id_to_promote"],
        "advertiser_business_id":            b["advertiser_business_id"],
        "active_from":                                start,
        "active_until":                              end,
        "status":                                          activation_status,
        "stripe_charge_id":                        charge.get("charge_id"),
        "stripe_payment_intent_id":      charge["payment_intent_id"],
        "amount_cents":                              charge["amount_cents"],
        "application_fee_cents":              charge["application_fee_cents"],
        "currency":                                      charge["currency"],
        "creative":                                      b["creative"],
        "payment_transaction_id":            tx_id,
        "created_at":                                  now,
    }
    await db.flagship_boost_activations.insert_one(act_doc)

    # 6) Fire notifications — winner + losers.
    try:
        # Winner — dispatch to submitter user_id (best guess).
        winner_uid = b.get("submitted_by_user_id")
        await dispatch_event(
            db, event_name="flagship_boost_bid_won",
            user_id=winner_uid,
            payload={
                "bid_id":                                    bid_id,
                "slot_id":                                  slot_id,
                "activation_id":                        act_id,
                "advertiser_business_id":        b["advertiser_business_id"],
                "region_code":                            sp["region_code"],
                "station_slot":                          sp["station_slot"],
                "station_id":                              b["creative"]["station_id_to_promote"],
                "bid_amount_cents":                    int(b["bid_amount_cents"]),
                "application_fee_cents":            int(charge["application_fee_cents"]),
                "active_from":                            _iso(start),
                "active_until":                          _iso(end)})
        for x_id in outbid_ids:
            x = await db.flagship_boost_bids.find_one({"id": x_id})
            if not x:
                continue
            await dispatch_event(
                db, event_name="flagship_boost_bid_lost",
                user_id=x.get("submitted_by_user_id"),
                payload={
                    "bid_id":                              x["id"],
                    "slot_id":                            slot_id,
                    "advertiser_business_id":  x["advertiser_business_id"],
                    "region_code":                      sp["region_code"],
                    "station_slot":                    sp["station_slot"],
                    "your_bid_cents":                int(x["bid_amount_cents"]),
                    "winning_bid_bucket":        _round_up_10pct(int(b["bid_amount_cents"])),
                    "reason":                              "outbid"})
    except Exception:
        pass

    return {"ok": True,
                    "bid": _shape_bid_public(
                        await db.flagship_boost_bids.find_one({"id": bid_id}),
                        include_advertiser=True),
                    "activation": _shape_activation(act_doc),
                    "charge": charge,
                    "outbid_count": len(outbid_ids),
                    "transaction_id": tx_id}


async def reject_bid(db, *, bid_id: str,
                                          admin_user_id: str,
                                          decision_note: Optional[str] = None
                                          ) -> Dict[str, Any]:
    b = await db.flagship_boost_bids.find_one({"id": bid_id})
    if not b:
        raise ValueError("bid_not_found")
    if b["status"] not in ("pending", "winning"):
        raise ValueError(f"bid_{b['status']}")
    now = _now()
    await db.flagship_boost_bids.update_one(
        {"id": bid_id},
        {"$set": {"status": "rejected", "decided_at": now,
                          "decided_by_user_id": admin_user_id,
                          "decision_note": decision_note}})
    # Fire "lost" notification.
    try:
        await dispatch_event(
            db, event_name="flagship_boost_bid_lost",
            user_id=b.get("submitted_by_user_id"),
            payload={"bid_id": bid_id, "slot_id": b["slot_id"],
                              "advertiser_business_id": b["advertiser_business_id"],
                              "reason": "rejected",
                              "decision_note": decision_note,
                              "your_bid_cents": int(b["bid_amount_cents"])})
    except Exception:
        pass
    return _shape_bid_public(
        await db.flagship_boost_bids.find_one({"id": bid_id}),
        include_advertiser=True)


# ── Advertiser view: available slots ─────────────────────────
async def get_available_slots(db, *,
                                                                advertiser_business_id: Optional[str] = None,
                                                                region_code: Optional[str] = None,
                                                                limit: int = 100
                                                                ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"status": "open"}
    if region_code:
        q["region_code"] = region_code.strip().lower()
    out = []
    async for sp in db.flagship_boost_slots.find(q)\
                                                                                      .sort("end_at", 1).limit(limit):
        s = _shape_slot(sp)
        n_bids = await db.flagship_boost_bids.count_documents(
            {"slot_id": sp["id"], "status": {"$in": ["pending", "winning"]}})
        s["active_bid_count"] = n_bids
        # Include "my rank" hint if advertiser given.
        if advertiser_business_id:
            mine = await db.flagship_boost_bids.find_one(
                {"slot_id": sp["id"],
                  "advertiser_business_id": advertiser_business_id,
                  "status": {"$in": ["pending", "winning"]}})
            s["my_active_bid_id"] = mine["id"] if mine else None
            s["my_active_bid_cents"] = int(mine["bid_amount_cents"]) if mine else None
        out.append(s)
    return out


# ── Activations ────────────────────────────────────────────────
async def list_activations(db, *,
                                                        advertiser_business_id: str,
                                                        status: Optional[str] = None,
                                                        limit: int = 100
                                                        ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"advertiser_business_id": advertiser_business_id}
    if status:
        q["status"] = status
    out = []
    async for a in db.flagship_boost_activations.find(q)\
                                                                                              .sort("active_from", -1).limit(limit):
        ic = await db.flagship_boost_impressions.count_documents(
            {"activation_id": a["id"]})
        out.append(_shape_activation(a, impression_count=ic))
    return out


async def get_live_boosts_for_region(db, *, region_code: str
                                                                              ) -> List[Dict[str, Any]]:
    """Public runtime endpoint — returns live activations for a
    region.  Trimmed to only the fields the listener UI needs, no
    Stripe internals / advertiser IDs by default."""
    now = _now()
    q = {"region_code": (region_code or "").strip().lower(),
            "status": "live",
            "active_from": {"$lte": now},
            "active_until": {"$gt": now}}
    out = []
    async for a in db.flagship_boost_activations.find(q):
        out.append({
            "activation_id":      a["id"],
            "station_id":            a["station_id"],
            "station_slot":        a.get("station_slot"),
            "region_code":        a["region_code"],
            "active_until":        _iso(a["active_until"]),
            "creative":              {
                "display_headline":  (a.get("creative") or {}).get("display_headline"),
                "subtext":                    (a.get("creative") or {}).get("subtext"),
                "badge_color":            (a.get("creative") or {}).get("badge_color") or "orange",
            },
        })
    return out


# ── Impression telemetry ───────────────────────────────────
async def record_impression(db, *,
                                                        activation_id: str,
                                                        user_id: Optional[str],
                                                        bucket_minutes: int = 60
                                                        ) -> Dict[str, Any]:
    a = await db.flagship_boost_activations.find_one({"id": activation_id})
    if not a:
        raise ValueError("activation_not_found")
    if a.get("status") != "live":
        return {"ok": False, "reason": "not_live"}
    now = _now()
    # Bucket key: floor(minutes) / bucket_minutes.
    bucket_stamp = now.replace(second=0, microsecond=0)
    bucket_minutes_int = bucket_stamp.hour * 60 + bucket_stamp.minute
    bucket_key = f"{bucket_stamp.date().isoformat()}-{bucket_minutes_int // bucket_minutes:04d}"
    doc = {
        "_id":                          _gen("fbi"),
        "activation_id":      activation_id,
        "user_id":                    user_id or "anon",
        "bucket_key":              bucket_key,
        "created_at":              now,
    }
    try:
        await db.flagship_boost_impressions.insert_one(doc)
        return {"ok": True, "bucket_key": bucket_key}
    except Exception as e:
        # Duplicate-key on the unique index — that's the dedupe path,
        # not an error.
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            return {"ok": True, "deduped": True, "bucket_key": bucket_key}
        logger.warning("[flagship_boost] impression insert: %s", e)
        return {"ok": False, "error": str(e)}


# ── Sweeper ────────────────────────────────────────────────
async def sweep_activations(db) -> Dict[str, Any]:
    """Flips activation status: scheduled→live when active_from<=now,
    live→completed when active_until<=now."""
    now = _now()
    r1 = await db.flagship_boost_activations.update_many(
        {"status": "scheduled", "active_from": {"$lte": now},
          "active_until": {"$gt": now}},
        {"$set": {"status": "live", "went_live_at": now}})
    r2 = await db.flagship_boost_activations.update_many(
        {"status": "live", "active_until": {"$lte": now}},
        {"$set": {"status": "completed", "completed_at": now}})
    return {"activated": r1.modified_count,
                    "completed": r2.modified_count,
                    "swept_at": _iso(now)}


__all__ = [
    "ensure_flagship_boost_indexes",
    "create_slot", "list_slots", "get_slot", "edit_slot", "close_slot",
    "submit_bid", "list_my_bids", "withdraw_bid", "bid_transparency",
    "approve_bid", "reject_bid",
    "get_available_slots", "list_activations",
    "get_live_boosts_for_region", "record_impression",
    "sweep_activations",
    "FLAGSHIP_BOOST_FEE_PCT", "STATION_SLOTS",
]
