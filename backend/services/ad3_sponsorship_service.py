"""Phase AD.3 — Advertiser Predict & Win Sponsorship.

Distinct from PW-M (merchant-branded activations) — AD.3 attaches an
advertiser BRAND on top of an existing Predict & Win parent campaign
without changing prize / entry / resolution rules.  Advertisers pick a
pricing model (per_entry or per_correct_impression), commit a budget,
and get their brand shown throughout the customer flow (list, detail,
entry confirmation, win screen).

Multiple sponsorships allowed per parent.  When a user views the
campaign, a single sponsorship wins the auction (priority_boost DESC,
CPE/CPI DESC, random tiebreaker) — same pattern as AD.11 banners.

Data lives in a dedicated `predict_win_sponsorships` collection to
avoid Mongo array-element update pain.  Wallet debits + ledger rows
follow the AD.2 rails via `payment_transactions_v2` shape (stripe
sentinel = tx_id to sidestep the shared null-index collision).

Approval flow: ADMOD.1 with `ad_type="sponsored_predict_win"`.
"""
from __future__ import annotations

import logging
import random
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.ad3")


PRICING_MODELS = ("per_entry", "per_correct_impression")
EVENT_TYPES        = ("entry", "correct_impression", "win_screen_view")

# Recommended defaults (in cents).
DEFAULT_CPE_CENTS = 20
DEFAULT_CPI_CENTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ─── Indexes ────────────────────────────────────────────────────
async def ensure_ad3_indexes(db) -> None:
    try:
        await db.predict_win_sponsorships.create_index(
            "sponsorship_id", unique=True)
        await db.predict_win_sponsorships.create_index("advertiser_id")
        await db.predict_win_sponsorships.create_index("parent_campaign_id")
        await db.predict_win_sponsorships.create_index([
            ("parent_campaign_id", 1), ("status", 1)])
        await db.predict_win_sponsorships.create_index("status")
        await db.predict_win_sponsorship_events.create_index(
            "event_id", unique=True)
        # Idempotency — one billed event per (user, sponsorship, type).
        await db.predict_win_sponsorship_events.create_index(
            [("user_id", 1), ("sponsorship_id", 1), ("event_type", 1)],
            unique=True)
        await db.predict_win_sponsorship_events.create_index(
            "sponsorship_id")
    except Exception as e:
        logger.warning("[ad3] index setup: %s", e)


# ─── Validation ─────────────────────────────────────────────────
def _validate(payload: Dict[str, Any]) -> None:
    if not payload.get("parent_campaign_id"):
        raise ValueError("parent_campaign_id_required")
    if not payload.get("brand_name"):
        raise ValueError("brand_name_required")
    pm = payload.get("pricing_model")
    if pm not in PRICING_MODELS:
        raise ValueError(f"invalid_pricing_model:{pm}")
    if pm == "per_entry":
        if int(payload.get("cpe_cents") or 0) < 1:
            raise ValueError("cpe_cents_required")
    else:
        if int(payload.get("cpi_cents") or 0) < 1:
            raise ValueError("cpi_cents_required")
    if int(payload.get("budget_cents") or 0) < 100:
        raise ValueError("budget_too_small")


# ─── CRUD ───────────────────────────────────────────────────────
async def create_sponsorship(db, *, advertiser_id: str,
                                                              submitted_by: str,
                                                              payload: Dict[str, Any]
                                                              ) -> Dict[str, Any]:
    _validate(payload)
    parent_id = payload["parent_campaign_id"]
    parent = await db.predict_win_campaigns.find_one(
        {"campaign_id": parent_id})
    if not parent:
        raise ValueError("parent_campaign_not_found")
    if parent.get("deleted_at") or parent.get("status") in (
            "resolved", "cancelled"):
        raise ValueError("parent_campaign_closed")
    now = _now()
    sid = _gen("pws")
    doc = {
        "_id":                                    sid,
        "sponsorship_id":                sid,
        "advertiser_id":                advertiser_id,
        "parent_campaign_id":      parent_id,
        "parent_snapshot": {
            "title":          parent.get("title"),
            "sport":          parent.get("event_label"),
            "starts_at":  parent.get("start_time"),
            "lock_time":  parent.get("lock_time"),
        },
        "brand_name":                    payload["brand_name"].strip()[:80],
        "brand_asset_url":          payload.get("brand_asset_url"),
        "tagline":                        (payload.get("tagline") or "")[:140],
        "pricing_model":              payload["pricing_model"],
        "cpe_cents":                      int(payload.get("cpe_cents") or 0),
        "cpi_cents":                      int(payload.get("cpi_cents") or 0),
        "budget_cents":                int(payload["budget_cents"]),
        "spent_cents":                  0,
        "daily_cap_cents":          int(payload.get("daily_cap_cents") or 0),
        "targeting_json":            payload.get("targeting_json") or {},
        "start_time":                    payload.get("start_time") or now,
        "end_time":                        payload.get("end_time"),
        "status":                          "draft",
        "approval_status":          "not_submitted",
        "impressions_count":      0,
        "entries_count":              0,
        "correct_impressions_count": 0,
        "win_views_count":          0,
        "auto_paused_reason":      None,
        "auto_paused_at":            None,
        "created_by":                    submitted_by,
        "created_at":                    now,
        "updated_at":                    now,
    }
    await db.predict_win_sponsorships.insert_one(doc)
    return _serialize(doc)


async def update_sponsorship(db, *, sponsorship_id: str,
                                                              patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    doc = await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id})
    if not doc:
        return None
    if doc["status"] not in ("draft", "rejected", "requires_changes"):
        raise ValueError(f"cannot_edit_status:{doc['status']}")
    allow = {"brand_name", "brand_asset_url", "tagline",
                      "pricing_model", "cpe_cents", "cpi_cents",
                      "budget_cents", "daily_cap_cents",
                      "targeting_json", "start_time", "end_time"}
    sets = {k: v for k, v in patch.items() if k in allow and v is not None}
    if not sets:
        return _serialize(doc)
    sets["updated_at"] = _now()
    await db.predict_win_sponsorships.update_one(
        {"sponsorship_id": sponsorship_id}, {"$set": sets})
    return _serialize(await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id}))


async def publish_sponsorship(db, *, sponsorship_id: str
                                                              ) -> Dict[str, Any]:
    doc = await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id})
    if not doc:
        raise ValueError("sponsorship_not_found")
    if not doc.get("brand_asset_url"):
        raise ValueError("brand_asset_required")
    await db.predict_win_sponsorships.update_one(
        {"sponsorship_id": sponsorship_id},
        {"$set": {"status":              "pending_admin",
                          "approval_status":  "pending",
                          "updated_at":        _now()}})
    return _serialize(await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id}))


async def list_advertiser_sponsorships(db, *, advertiser_id: str
                                                                                          ) -> Dict[str, Any]:
    rows = []
    async for r in db.predict_win_sponsorships.find(
                {"advertiser_id": advertiser_id}).sort("created_at", -1):
        rows.append(_serialize(r))
    return {"items": rows, "count": len(rows)}


async def available_parent_campaigns(db, *, limit: int = 50
                                                                                    ) -> Dict[str, Any]:
    """PDX.1 parents (or admin-manual) that are still open for sponsoring —
    i.e. not resolved/cancelled and not past their lock_time."""
    now = _now()
    q = {"approval_status": "approved",
              "deleted_at": None,
              "status": {"$in": ["open", "live", "locked", "scheduled"]}}
    rows = []
    async for r in db.predict_win_campaigns.find(q).sort(
                        "start_time", -1).limit(limit):
        # Count active sponsors + entries so far for the "expected volume" UX.
        s_count = await db.predict_win_sponsorships.count_documents(
            {"parent_campaign_id": r["campaign_id"], "status": "live"})
        entries = await db.predict_win_entries.count_documents(
            {"campaign_id": r["campaign_id"]})
        rows.append({
            "parent_campaign_id":  r["campaign_id"],
            "title":                        r.get("title"),
            "event_label":              r.get("event_label"),
            "event_type":                r.get("event_type"),
            "city":                          r.get("city"),
            "start_time":                r.get("start_time"),
            "lock_time":                r.get("lock_time"),
            "status":                      r.get("status"),
            "cover_image_url":      r.get("cover_image_url"),
            "active_sponsors":      s_count,
            "entries_so_far":        entries,
        })
    return {"items": rows, "count": len(rows)}


# ─── Auction — pick 1 sponsor for the current view ────────────
async def _matches_targeting(user: Optional[dict], sp: dict) -> bool:
    t = sp.get("targeting_json") or {}
    if not user:
        return not any([t.get("country_codes"), t.get("city")])
    ccs = t.get("country_codes") or []
    user_cc = str(user.get("country") or user.get("country_code")
                                    or "").upper()
    if ccs and user_cc and user_cc not in {c.upper() for c in ccs}:
        return False
    return True


async def active_sponsorship_for_parent(db, *, parent_campaign_id: str,
                                                                                        user: Optional[dict]
                                                                                        ) -> Optional[Dict[str, Any]]:
    """Pick 1 live sponsorship for this parent (auction).  Returns None
    when no eligible sponsor is found."""
    candidates = []
    async for sp in db.predict_win_sponsorships.find({
                "parent_campaign_id": parent_campaign_id,
                "status": "live"}):
        # Wallet must cover at least one impression.
        billing = int(sp.get("cpe_cents") or 0) if sp["pricing_model"] == "per_entry" \
                                        else int(sp.get("cpi_cents") or 0)
        remaining = int(sp.get("budget_cents") or 0) - int(sp.get("spent_cents") or 0)
        if billing > 0 and remaining < billing:
            continue
        # Daily cap
        if sp.get("daily_cap_cents"):
            since = _now() - timedelta(days=1)
            spent_today = 0
            cur = db.predict_win_sponsorship_events.aggregate([
                {"$match": {"sponsorship_id": sp["sponsorship_id"],
                                        "created_at": {"$gte": since}}},
                {"$group": {"_id": None, "s": {"$sum": "$billed_cents"}}}])
            async for row in cur:
                spent_today = int(row.get("s") or 0)
            if spent_today >= int(sp["daily_cap_cents"]):
                continue
        if not await _matches_targeting(user, sp):
            continue
        # Load advertiser priority boost.
        adv = await db.advertisers_v2.find_one(
            {"advertiser_id": sp["advertiser_id"]},
            {"priority_score_boost": 1, "status": 1})
        if not adv or adv.get("status") != "active":
            continue
        boost = int(adv.get("priority_score_boost") or 0)
        candidates.append((sp, billing, boost))
    if not candidates:
        return None
    # Sort: priority_boost DESC, billing DESC, random tiebreaker.
    candidates.sort(key=lambda t: (t[2], t[1], random.random()),
                                      reverse=True)
    sp, winner_bid, winner_boost = candidates[0]
    # Phase AD.3 bundle — log losers for Auction Insights.
    try:
        from services.auction_insights_service import (
            log_auction_result, fire_and_forget)
        losers = []
        for l_sp, l_bid, l_boost in candidates[1:]:
            if l_sp["advertiser_id"] == sp["advertiser_id"]:
                continue
            reason = ("priority_boost_lower"
                                if l_boost < winner_boost else "higher_cpm")
            losers.append({
                "advertiser_id":  l_sp["advertiser_id"],
                "campaign_id":      l_sp["sponsorship_id"],
                "bid_cents":          l_bid,
                "reason":                reason,
            })
        if losers:
            fire_and_forget(log_auction_result(
                db, ad_type="advertiser_pw_sponsorship",
                slot_id=parent_campaign_id,
                winner_advertiser_id=sp["advertiser_id"],
                winner_bid_cents=winner_bid,
                losers=losers,
                user_context={"parent": parent_campaign_id}))
    except Exception:
        pass
    return {
        "sponsorship_id":      sp["sponsorship_id"],
        "advertiser_id":      sp["advertiser_id"],
        "brand_name":            sp["brand_name"],
        "brand_asset_url":  sp.get("brand_asset_url"),
        "tagline":                sp.get("tagline"),
        "pricing_model":      sp["pricing_model"],
    }


# ─── Impression → billing ──────────────────────────────────────
async def record_event(db, *, sponsorship_id: str,
                                                event_type: str,
                                                parent_campaign_id: str,
                                                user_id: Optional[str]
                                                ) -> Dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"invalid_event_type:{event_type}")
    sp = await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id})
    if not sp:
        return {"ok": False, "reason": "sponsorship_not_found"}
    if sp.get("status") != "live":
        return {"ok": False, "reason": f"sponsorship_{sp.get('status')}"}
    # Only bill events matching the pricing model.  Non-billing events
    # still fire an idempotent row (for analytics) but with 0 billed.
    pm = sp.get("pricing_model")
    billed = 0
    if pm == "per_entry" and event_type == "entry":
        billed = int(sp.get("cpe_cents") or 0)
    elif pm == "per_correct_impression" \
              and event_type == "correct_impression":
        billed = int(sp.get("cpi_cents") or 0)

    now = _now()
    dedup_key = user_id or "anon"
    # Idempotent per (user, sponsorship, event_type).
    existing = await db.predict_win_sponsorship_events.find_one(
        {"user_id": dedup_key, "sponsorship_id": sponsorship_id,
          "event_type": event_type})
    if existing:
        return {"ok": True, "already_billed": True,
                      "event_id": existing["event_id"],
                      "billed_cents": int(existing.get("billed_cents") or 0)}

    # Debit wallet atomically when billed > 0.
    if billed > 0:
        debit = await db.advertisers_v2.find_one_and_update(
            {"advertiser_id": sp["advertiser_id"],
              "budget_available_cents": {"$gte": billed}},
            {"$inc": {"budget_available_cents": -billed,
                              "budget_spent_cents":      billed}},
            return_document=True)
        if not debit:
            await _auto_pause(db, sponsorship_id, "wallet_exhausted")
            return {"ok": False, "reason": "wallet_exhausted"}

    event_id = _gen("pwse")
    try:
        await db.predict_win_sponsorship_events.insert_one({
            "_id":                              event_id,
            "event_id":                    event_id,
            "sponsorship_id":        sponsorship_id,
            "parent_campaign_id":  parent_campaign_id,
            "user_id":                      dedup_key,
            "event_type":                event_type,
            "billed_cents":              billed,
            "created_at":                now,
        })
    except Exception:
        # DuplicateKey — race.  Return the existing row.
        existing = await db.predict_win_sponsorship_events.find_one(
            {"user_id": dedup_key, "sponsorship_id": sponsorship_id,
              "event_type": event_type})
        if billed > 0:
            # Undo the debit we just did (race lost).
            await db.advertisers_v2.update_one(
                {"advertiser_id": sp["advertiser_id"]},
                {"$inc": {"budget_available_cents": billed,
                                  "budget_spent_cents":      -billed}})
        return {"ok": True, "already_billed": True,
                      "event_id": (existing or {}).get("event_id"),
                      "billed_cents": int((existing or {}).get("billed_cents") or 0)}

    # Write AD.2 ledger row.
    if billed > 0:
        tx_id = _gen("tx_pws")
        await db.payment_transactions_v2.insert_one({
            "_id":                                            tx_id,
            "transaction_id":                        tx_id,
            "stripe_payment_intent_id":  tx_id,
            "flow":                                          "ad3_predict_win_sponsorship",
            "event_source":                            f"pws_{event_type}",
            "advertiser_id":                        sp["advertiser_id"],
            "sponsorship_id":                        sponsorship_id,
            "parent_campaign_id":              parent_campaign_id,
            "customer_user_id":                    user_id,
            "amount_cents":                            billed,
            "application_fee_cents":          billed,
            "merchant_net_cents":              0,
            "status":                                      "posted",
            "created_at":                              now,
        })
    # Roll-ups on the sponsorship row.
    inc = {"impressions_count": 1, "spent_cents": billed}
    if event_type == "entry":
        inc["entries_count"] = 1
    elif event_type == "correct_impression":
        inc["correct_impressions_count"] = 1
    elif event_type == "win_screen_view":
        inc["win_views_count"] = 1
    await db.predict_win_sponsorships.update_one(
        {"sponsorship_id": sponsorship_id},
        {"$inc": inc, "$set": {"updated_at": now}})
    # Belt-and-suspenders auto-pause on budget exhaustion.
    remaining = int(sp.get("budget_cents", 0)) - int(sp.get("spent_cents", 0)) - billed
    tick = int(sp.get("cpe_cents") or 0) or int(sp.get("cpi_cents") or 0) or 1
    if remaining < tick:
        await _auto_pause(db, sponsorship_id, "budget_exhausted")

    return {"ok": True, "event_id": event_id, "billed_cents": billed}


async def _auto_pause(db, sponsorship_id: str, reason: str) -> None:
    await db.predict_win_sponsorships.update_one(
        {"sponsorship_id": sponsorship_id},
        {"$set": {"status":                          "paused",
                          "auto_paused_reason":  reason,
                          "auto_paused_at":        _now(),
                          "updated_at":                _now()}})


# ─── Admin controls ─────────────────────────────────────────────
async def admin_set_status(db, *, sponsorship_id: str,
                                                    new_status: str) -> Dict[str, Any]:
    if new_status not in ("live", "paused", "rejected"):
        raise ValueError(f"invalid_status:{new_status}")
    r = await db.predict_win_sponsorships.update_one(
        {"sponsorship_id": sponsorship_id},
        {"$set": {"status":              new_status,
                          "approval_status":  "approved" if new_status == "live" else new_status,
                          "updated_at":        _now()}})
    if r.matched_count == 0:
        raise ValueError("sponsorship_not_found")
    return _serialize(await db.predict_win_sponsorships.find_one(
        {"sponsorship_id": sponsorship_id}))


# ─── Analytics ──────────────────────────────────────────────────
async def advertiser_analytics(db, *, advertiser_id: str
                                                                ) -> Dict[str, Any]:
    rows = []
    async for sp in db.predict_win_sponsorships.find(
                {"advertiser_id": advertiser_id}).sort("created_at", -1):
        rows.append({
            "sponsorship_id":                sp["sponsorship_id"],
            "parent_campaign_id":        sp["parent_campaign_id"],
            "parent_title":                    (sp.get("parent_snapshot") or {}).get("title"),
            "brand_name":                        sp["brand_name"],
            "status":                                sp["status"],
            "pricing_model":                  sp["pricing_model"],
            "budget_cents":                    int(sp.get("budget_cents") or 0),
            "spent_cents":                      int(sp.get("spent_cents") or 0),
            "entries_count":                  int(sp.get("entries_count") or 0),
            "correct_impressions_count": int(sp.get("correct_impressions_count") or 0),
            "win_views_count":              int(sp.get("win_views_count") or 0),
        })
    totals = {
        "spend_cents":      sum(r["spent_cents"] for r in rows),
        "entries":            sum(r["entries_count"] for r in rows),
        "correct_impr":  sum(r["correct_impressions_count"] for r in rows),
        "win_views":      sum(r["win_views_count"] for r in rows),
    }
    return {"items": rows, "totals": totals}


__all__ = [
    "ensure_ad3_indexes",
    "create_sponsorship",
    "update_sponsorship",
    "publish_sponsorship",
    "list_advertiser_sponsorships",
    "available_parent_campaigns",
    "active_sponsorship_for_parent",
    "record_event",
    "admin_set_status",
    "advertiser_analytics",
    "PRICING_MODELS", "EVENT_TYPES",
    "DEFAULT_CPE_CENTS", "DEFAULT_CPI_CENTS",
]
