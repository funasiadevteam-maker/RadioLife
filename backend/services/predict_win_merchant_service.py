"""Phase PW-M.1 — Merchant Predict & Win service.

Bridges the existing Predexon-derived `predict_win_campaigns` (parent)
with the new merchant-authored child campaigns.  One parent → many
merchants; each merchant scopes their own prize inventory + winner rule
+ audience.

Reuses:
    * `predict_win_campaigns` (parent, unchanged)
    * `predict_win_entries` (customer entries, unchanged)
    * `predict_win_resolutions` (result_source, unchanged)
    * `user_wallet_items` (wallet, extended with QR + merchant_id fields)
    * `coupons`  (so merchant cashier redemption path works unchanged)
    * `merchant_rbac_service` (permission gate at the route layer)

Collections owned by this service:
    * merchant_prediction_preferences
    * merchant_prize_inventory                        (via prize_inventory_service)
    * merchant_predict_win_campaigns
    * merchant_predict_win_entries
    * merchant_predict_win_awards
    * merchant_predict_win_analytics                (via analytics_service)
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from services import merchant_prize_inventory_service as prize_svc
from services import merchant_predict_win_analytics_service as analytics_svc

log = logging.getLogger("bigfm.pw_m.service")


# ─────────────────────── Helpers ───────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _iso(v: Any) -> Optional[str]:
    d = _aware(v)
    return d.isoformat() if d else None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _strip(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return doc
    d = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at", "start_time", "lock_time",
                        "end_time", "approved_at", "awarded_at", "redeemed_at",
                        "expires_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    return d


# ─────────────────────── Constants ───────────────────────
CAMPAIGN_STATUSES = {"draft", "pending", "scheduled", "live",
                                                                        "paused", "resolved", "completed"}
APPROVAL_STATUSES = {"pending_admin", "approved", "rejected"}
WINNER_RULES = {"first_n_correct", "all_correct", "random_correct"}

ALLOWED_PATCH_FIELDS = {"campaign_title", "campaign_description",
                                                                        "promotional_message",
                                                                        "entry_rules", "placement_rules"}


# ─────────────────────── Preferences ───────────────────────
async def get_preferences(db, *, merchant_id: str) -> Dict[str, Any]:
    doc = await db.merchant_prediction_preferences.find_one(
        {"merchant_id": merchant_id})
    if not doc:
        now = _now()
        default = {
            "_id":                                    _new_id("mpp"),
            "merchant_id":                    merchant_id,
            "preferred_categories":  [],
            "preferred_sports":            [],
            "preferred_leagues":        [],
            "preferred_teams":            [],
            "default_prize_inventory_id": None,
            "max_campaigns_per_week": 5,
            "default_checkin_required": False,
            "auto_draft_enabled":     False,
            "active":                              True,
            "created_at":                      now,
            "updated_at":                      now,
        }
        await db.merchant_prediction_preferences.insert_one(default)
        return _strip(default)
    return _strip(doc)


async def patch_preferences(db, *, merchant_id: str,
                                                                updates: Dict[str, Any]) -> Dict[str, Any]:
    _ = await get_preferences(db, merchant_id=merchant_id)  # ensure exists
    allowed = {"preferred_categories", "preferred_sports",
                              "preferred_leagues", "preferred_teams",
                              "default_prize_inventory_id",
                              "max_campaigns_per_week",
                              "default_checkin_required",
                              "auto_draft_enabled", "active"}
    clean = {k: v for k, v in updates.items() if k in allowed}
    clean["updated_at"] = _now()
    await db.merchant_prediction_preferences.update_one(
        {"merchant_id": merchant_id}, {"$set": clean})
    return await get_preferences(db, merchant_id=merchant_id)


# ─────────────── Parent campaign discovery ───────────────
def _serialize_parent(pc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "campaign_id":                pc.get("campaign_id"),
        "title":                            pc.get("title"),
        "description":                pc.get("description"),
        "category":                      pc.get("category"),
        "event_type":                  pc.get("event_type"),
        "event_label":                pc.get("event_label"),
        "cover_image_url":         pc.get("cover_image_url"),
        "start_time":                  _iso(pc.get("start_time")),
        "lock_time":                    _iso(pc.get("lock_time")),
        "resolve_by":                  _iso(pc.get("resolve_by")),
        "question":                      pc.get("question") or {},
        "external_market_id": pc.get("external_market_id"),
        "data_provider_id":     pc.get("data_provider_id"),
        "merchant_eligible":     bool(pc.get("merchant_eligible")),
        "approval_status":         pc.get("approval_status"),
        "status":                          pc.get("status"),
    }


async def list_eligible_parents(db, *,
                                                                            category: Optional[str] = None,
                                                                            starting_within_hours: Optional[int] = None,
                                                                            limit: int = 50, offset: int = 0
                                                                            ) -> Tuple[List[Dict[str, Any]], int]:
    """Return parent campaigns flagged `merchant_eligible=True` that are
    approved, open (status ∈ {scheduled, live}), and still enterable."""
    now = _now()
    q: Dict[str, Any] = {
        "merchant_eligible":    True,
        "approval_status":     "approved",
        "status":                        {"$in": ["scheduled", "live"]},
        "deleted_at":              None,
    }
    if category:
        q["category"] = category
    total = await db.predict_win_campaigns.count_documents(q)
    items = []
    async for pc in db.predict_win_campaigns.find(q) \
                                                                          .sort([("lock_time", 1)]) \
                                                                          .skip(offset).limit(limit):
        lock = _aware(pc.get("lock_time"))
        if lock and lock <= now:
            continue     # already locked — merchants can't activate
        if starting_within_hours is not None:
            start = _aware(pc.get("start_time")) or lock
            if start and (start - now).total_seconds() > starting_within_hours * 3600:
                continue
        items.append(_serialize_parent(pc))
    return items, total


async def get_eligible_parent(db, *, parent_id: str) -> Optional[Dict[str, Any]]:
    pc = await db.predict_win_campaigns.find_one({"campaign_id": parent_id})
    if not pc or not pc.get("merchant_eligible"):
        return None
    return _serialize_parent(pc)


async def recommend_for_merchant(db, *, merchant_id: str, limit: int = 10
                                                                            ) -> List[Dict[str, Any]]:
    """v1 recommender — score by category-match + start-time proximity."""
    prefs = await get_preferences(db, merchant_id=merchant_id)
    parents, _ = await list_eligible_parents(db, limit=100)
    now = _now()
    pref_cats = set((prefs.get("preferred_categories") or []))

    def _score(p: Dict[str, Any]) -> float:
        s = 0.0
        if p.get("category") in pref_cats:
            s += 3.0
        # closer start = higher weight (up to +2)
        start = _aware(p.get("start_time")) or _aware(p.get("lock_time"))
        if start:
            delta_h = max(1.0, (start - now).total_seconds() / 3600)
            s += min(2.0, 48.0 / delta_h)
        return s

    ranked = sorted(parents, key=_score, reverse=True)
    return ranked[:limit]


# ─────────────── Merchant child campaign CRUD ───────────────
async def _biz_auto_publish(db, merchant_id: str) -> bool:
    biz = await db.businesses.find_one(
        {"$or": [{"business_id": merchant_id}, {"_id": merchant_id}]},
        projection={"auto_publish_predict_win": 1})
    return bool((biz or {}).get("auto_publish_predict_win"))


async def create_child_campaign(db, *, merchant_id: str, user_id: str,
                                                                                body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a merchant activation of an eligible parent Predexon campaign.

    Reserves `prize_quantity_reserved` items in the merchant's prize
    inventory.  Returns the fresh row."""
    parent_id = body.get("parent_predict_win_campaign_id")
    if not parent_id:
        raise ValueError("missing_parent_predict_win_campaign_id")
    parent = await db.predict_win_campaigns.find_one({"campaign_id": parent_id})
    if not parent:
        raise LookupError("parent_not_found")
    if not parent.get("merchant_eligible"):
        raise ValueError("parent_not_merchant_eligible")
    if parent.get("approval_status") != "approved":
        raise ValueError("parent_not_approved")
    lock = _aware(parent.get("lock_time"))
    if lock and lock <= _now():
        raise ValueError("parent_already_locked")

    prize_inventory_id = body.get("prize_inventory_id")
    qty_reserved = int(body.get("prize_quantity_reserved") or 1)
    if not prize_inventory_id:
        raise ValueError("missing_prize_inventory_id")
    # Reserve — raises on insufficient inventory.
    await prize_svc.reserve(db, prize_id=prize_inventory_id,
                                                              merchant_id=merchant_id, qty=qty_reserved)

    winner_rule = str(body.get("winner_rule") or "first_n_correct")
    if winner_rule not in WINNER_RULES:
        # release before failing hard
        await prize_svc.release(db, prize_id=prize_inventory_id, qty=qty_reserved)
        raise ValueError(f"invalid_winner_rule:{winner_rule}")

    max_winners = int(body.get("max_winners") or 1)
    campaign_id = _new_id("mpwc")
    now = _now()
    start_time = _aware(body.get("start_time")) or _aware(parent.get("start_time")) or now
    end_time   = _aware(body.get("end_time"))    or _aware(parent.get("resolve_by"))
    lock_time  = _aware(body.get("lock_time"))  or lock

    doc = {
        "_id":                                                    campaign_id,
        "campaign_id":                                    campaign_id,
        "merchant_id":                                    merchant_id,
        "location_id":                                    body.get("location_id"),
        "parent_predict_win_campaign_id":  parent_id,
        "campaign_title":                              (body.get("campaign_title")
                                                                                        or parent.get("title") or "")[:200],
        "campaign_description":                (body.get("campaign_description")
                                                                                        or "")[:1000],
        "promotional_message":                (body.get("promotional_message")
                                                                                        or "")[:280],
        "prize_inventory_id":                  prize_inventory_id,
        "prize_quantity_reserved":          qty_reserved,
        "winner_rule":                                  winner_rule,
        "max_winners":                                  max_winners,
        "entry_rules":                                  body.get("entry_rules") or {},
        "placement_rules":                          body.get("placement_rules") or {},
        "start_time":                                    start_time,
        "lock_time":                                      lock_time,
        "end_time":                                        end_time,
        "approval_status":                          None,
        "campaign_status":                          "draft",
        "approved_by":                                  None,
        "approved_at":                                  None,
        "rejected_reason":                          None,
        "created_by":                                    user_id,
        "created_at":                                    now,
        "updated_at":                                    now,
    }
    await db.merchant_predict_win_campaigns.insert_one(doc)
    await analytics_svc.record_event(
        db, merchant_campaign_id=campaign_id, event_type="detail_view",
        user_id=user_id, metadata={"kind": "child_created"})
    return _strip(doc)


async def get_merchant_campaign(db, *, campaign_id: str,
                                                                                merchant_id: Optional[str] = None
                                                                                ) -> Optional[Dict[str, Any]]:
    q: Dict[str, Any] = {"campaign_id": campaign_id}
    if merchant_id:
        q["merchant_id"] = merchant_id
    return _strip(await db.merchant_predict_win_campaigns.find_one(q))


async def list_merchant_campaigns(db, *, merchant_id: str,
                                                                                    status: Optional[str] = None,
                                                                                    limit: int = 50, offset: int = 0
                                                                                    ) -> Tuple[List[Dict[str, Any]], int]:
    q: Dict[str, Any] = {"merchant_id": merchant_id}
    if status:
        q["campaign_status"] = status
    total = await db.merchant_predict_win_campaigns.count_documents(q)
    items = []
    async for d in db.merchant_predict_win_campaigns.find(q) \
                                                                                                                  .sort("created_at", -1) \
                                                                                                                  .skip(offset).limit(limit):
        items.append(_strip(d))
    return items, total


async def patch_merchant_campaign(db, *, campaign_id: str, merchant_id: str,
                                                                                    updates: Dict[str, Any]
                                                                                    ) -> Dict[str, Any]:
    c = await db.merchant_predict_win_campaigns.find_one(
        {"campaign_id": campaign_id, "merchant_id": merchant_id})
    if not c:
        raise LookupError("campaign_not_found")
    if c["campaign_status"] not in ("draft", "pending"):
        raise ValueError("cannot_edit_after_scheduled")
    clean = {k: v for k, v in updates.items() if k in ALLOWED_PATCH_FIELDS}
    clean["updated_at"] = _now()
    await db.merchant_predict_win_campaigns.update_one(
        {"campaign_id": campaign_id, "merchant_id": merchant_id},
        {"$set": clean})
    return await get_merchant_campaign(db, campaign_id=campaign_id, merchant_id=merchant_id)


async def _transition_after_approval(db, campaign_id: str,
                                                                                              now: datetime) -> str:
    """Compute lifecycle status for an approved campaign."""
    c = await db.merchant_predict_win_campaigns.find_one({"campaign_id": campaign_id})
    start = _aware(c.get("start_time"))
    return "live" if start and start <= now else "scheduled"


async def publish_merchant_campaign(db, *, campaign_id: str, merchant_id: str
                                                                                        ) -> Dict[str, Any]:
    c = await db.merchant_predict_win_campaigns.find_one(
        {"campaign_id": campaign_id, "merchant_id": merchant_id})
    if not c:
        raise LookupError("campaign_not_found")
    if c["campaign_status"] not in ("draft",):
        raise ValueError("cannot_publish_from_status:" + c["campaign_status"])
    now = _now()
    auto = await _biz_auto_publish(db, merchant_id)
    if auto:
        next_status = await _transition_after_approval(db, campaign_id, now)
        await db.merchant_predict_win_campaigns.update_one(
            {"campaign_id": campaign_id},
            {"$set": {"approval_status": "approved",
                                  "approved_by":      "auto_publish",
                                  "approved_at":      now,
                                  "campaign_status": next_status,
                                  "updated_at":        now}})
    else:
        await db.merchant_predict_win_campaigns.update_one(
            {"campaign_id": campaign_id},
            {"$set": {"approval_status": "pending_admin",
                                  "campaign_status": "pending",
                                  "updated_at":        now}})
    await analytics_svc.record_event(
        db, merchant_campaign_id=campaign_id, event_type="detail_view",
        metadata={"kind": "published", "auto": auto})
    return await get_merchant_campaign(db, campaign_id=campaign_id)


async def pause_merchant_campaign(db, *, campaign_id: str,
                                                                                    merchant_id: Optional[str] = None,
                                                                                    by_admin: bool = False) -> Dict[str, Any]:
    q = {"campaign_id": campaign_id}
    if merchant_id and not by_admin:
        q["merchant_id"] = merchant_id
    c = await db.merchant_predict_win_campaigns.find_one(q)
    if not c:
        raise LookupError("campaign_not_found")
    if c["campaign_status"] not in ("scheduled", "live"):
        raise ValueError("cannot_pause_from_status:" + c["campaign_status"])
    await db.merchant_predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"campaign_status": "paused",
                            "updated_at":        _now()}})
    return await get_merchant_campaign(db, campaign_id=campaign_id)


async def admin_approve(db, *, campaign_id: str, admin_user_id: str
                                                    ) -> Dict[str, Any]:
    c = await db.merchant_predict_win_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise LookupError("campaign_not_found")
    if c["approval_status"] != "pending_admin":
        raise ValueError("not_pending_admin")
    now = _now()
    next_status = await _transition_after_approval(db, campaign_id, now)
    await db.merchant_predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"approval_status": "approved",
                            "approved_by":      admin_user_id,
                            "approved_at":      now,
                            "rejected_reason": None,
                            "campaign_status": next_status,
                            "updated_at":        now}})
    return await get_merchant_campaign(db, campaign_id=campaign_id)


async def admin_reject(db, *, campaign_id: str, admin_user_id: str,
                                                reason: str) -> Dict[str, Any]:
    c = await db.merchant_predict_win_campaigns.find_one({"campaign_id": campaign_id})
    if not c:
        raise LookupError("campaign_not_found")
    if c["approval_status"] != "pending_admin":
        raise ValueError("not_pending_admin")
    # Release the reservation on rejection so the merchant can retry.
    try:
        await prize_svc.release(db, prize_id=c["prize_inventory_id"],
                                                                    qty=int(c.get("prize_quantity_reserved") or 0))
    except Exception as e:
        log.warning("[admin_reject] release failed campaign=%s: %s",
                                campaign_id, e)
    await db.merchant_predict_win_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"approval_status": "rejected",
                            "rejected_reason": reason[:500] if reason else "no_reason",
                            "campaign_status": "draft",
                            "updated_at":        _now()}})
    return await get_merchant_campaign(db, campaign_id=campaign_id)


# ─────────────── Entry linking ───────────────
async def attach_entry(db, *, merchant_campaign_id: str, entry_id: str,
                                              user_id: str,
                                              venue_checkin_id: Optional[str] = None
                                              ) -> Dict[str, Any]:
    """Link an existing customer `predict_win_entries` row to a merchant
    campaign for scoping analytics + winner selection.

    The customer entry is authoritative for the pick + status; this row
    only records the merchant scoping."""
    mc = await db.merchant_predict_win_campaigns.find_one(
        {"campaign_id": merchant_campaign_id})
    if not mc:
        raise LookupError("merchant_campaign_not_found")
    if mc["campaign_status"] not in ("scheduled", "live"):
        raise ValueError("campaign_not_live")
    entry = await db.predict_win_entries.find_one({"entry_id": entry_id})
    if not entry:
        raise LookupError("entry_not_found")
    if entry.get("user_id") != user_id:
        raise ValueError("entry_user_mismatch")
    if entry.get("campaign_id") != mc["parent_predict_win_campaign_id"]:
        raise ValueError("entry_not_for_parent")

    mpwe_id = _new_id("mpwe")
    doc = {
        "_id":                                                    mpwe_id,
        "entry_id":                                        mpwe_id,
        "merchant_campaign_id":                merchant_campaign_id,
        "parent_predict_win_entry_id":  entry_id,
        "user_id":                                        user_id,
        "venue_checkin_id":                        venue_checkin_id
                                                                                    or entry.get("venue_checkin_id"),
        "eligibility_status":                  "eligible",
        "created_at":                                    _now(),
    }
    try:
        await db.merchant_predict_win_entries.insert_one(doc)
    except Exception as e:
        if "duplicate" in str(e).lower():
            raise ValueError("already_attached")
        raise
    await analytics_svc.record_event(
        db, merchant_campaign_id=merchant_campaign_id, event_type="entry",
        user_id=user_id, metadata={"entry_id": entry_id})
    return _strip(doc)


# ─────────────── Award + sweeper cascade ───────────────
def _new_qr_token() -> str:
    return f"pwm_{uuid.uuid4().hex[:20]}"


def _short_code() -> str:
    return f"PWM-{secrets.token_hex(3).upper()}"


async def _ensure_pw_merchant_offer(db, *, merchant_id: str,
                                                                                merchant_campaign: Dict[str, Any],
                                                                                prize: Dict[str, Any]) -> str:
    """Get-or-create an `offers` row that scopes cashier redemption to
    this merchant + PW campaign.  Reusing the offers/coupons stack lets
    `merchant_staff::cashier_redeem` handle the scan without changes."""
    campaign_id = merchant_campaign["campaign_id"]
    existing = await db.offers.find_one(
        {"business_id": merchant_id,
          "source_type": "predict_win_merchant",
          "source_campaign_id": campaign_id})
    if existing:
        return existing.get("offer_id") or existing.get("id") or existing.get("_id")
    offer_id = _new_id("ofr")
    now = _now()
    doc = {
        "_id":                              offer_id,
        "id":                                offer_id,
        "offer_id":                    offer_id,
        "business_id":                merchant_id,
        "venue_id":                      merchant_campaign.get("location_id"),
        "title":                            merchant_campaign.get("campaign_title")
                                                or prize.get("title") or "Predict & Win Prize",
        "description":                prize.get("description") or "",
        "offer_type":                  prize.get("prize_type") or "custom",
        "discount_percent":     0,
        "discount_value":         float(prize.get("retail_value") or 0),
        "currency":                      prize.get("currency") or "AED",
        "start_time":                  merchant_campaign.get("start_time"),
        "end_time":                      merchant_campaign.get("end_time"),
        "status":                          "active",
        "source_type":                "predict_win_merchant",
        "source_campaign_id": campaign_id,
        "source_prize_id":       prize.get("prize_id"),
        "created_at":                  now,
        "updated_at":                  now,
        "issued_count":              0,
        "market":                          "dubai",
    }
    await db.offers.insert_one(doc)
    return offer_id


async def _mint_wallet_and_coupon(db, *, user_id: str,
                                                                                merchant_id: str,
                                                                                merchant_campaign: Dict[str, Any],
                                                                                prize: Dict[str, Any],
                                                                                offer_id: str
                                                                                ) -> Tuple[str, str, datetime]:
    """Mint a `user_wallet_items` row (PW-M format with QR + merchant_id)
    and a linked `coupons` row so the existing cashier redeem endpoint
    can consume it.  Returns (wallet_item_id, coupon_id, expires_at)."""
    now = _now()
    # Expiry policy: prize.expiration_policy.hours OR 30 days default.
    exp_hours = int((prize.get("expiration_policy") or {})
                                      .get("hours", 24 * 30))
    expires_at = now + timedelta(hours=exp_hours)

    qr_token = _new_qr_token()
    short = _short_code()

    wallet_item_id = _new_id("wi")
    wi = {
        "_id":                              wallet_item_id,
        "wallet_item_id":         wallet_item_id,
        "user_id":                      user_id,
        "item_type":                  "prediction_award",
        "prize_kind":                prize.get("prize_type") or "custom",
        "title":                            prize.get("title"),
        "description":                prize.get("description"),
        "value_amount":            float(prize.get("retail_value") or 0),
        "value_currency":         prize.get("currency") or "AED",
        "image_url":                  None,
        "status":                          "in_wallet",
        "redemption_source":  "predict_win_merchant",
        "source_campaign_id": merchant_campaign["campaign_id"],
        "source_prize_id":       prize.get("prize_id"),
        # PW-M.1 additions — enable cashier scan flows.
        "merchant_id":              merchant_id,
        "qr_token":                    qr_token,
        "short_code":                short,
        "expires_at":                expires_at,
        "created_at":                now,
    }
    await db.user_wallet_items.insert_one(wi)

    coupon_id = _new_id("cpn")
    coupon = {
        "_id":                              coupon_id,
        "coupon_id":                  coupon_id,
        "short_code":                short,
        "code":                            short,       # merchant_staff._lookup_coupon reads `code`
        "offer_id":                    offer_id,
        "business_id":              merchant_id,
        "venue_id":                    merchant_campaign.get("location_id"),
        "user_id":                      user_id,
        "discount_value":         float(prize.get("retail_value") or 0),
        "status":                          "saved",     # merchant_staff cashier_scan accepts saved|claimed
        "issued_at":                  now,
        "expires_at":                expires_at,
        "source_type":                "predict_win_merchant",
        "source_wallet_item_id": wallet_item_id,
    }
    await db.coupons.insert_one(coupon)
    return wallet_item_id, coupon_id, expires_at


async def _select_winners(db, *, merchant_campaign: Dict[str, Any],
                                                          winning_option_id: str) -> List[Dict[str, Any]]:
    """Pick winners for a merchant child campaign based on its winner_rule.

    Reads `merchant_predict_win_entries` for the campaign, cross-refs
    each with `predict_win_entries` to get the picked option + submit
    time, and applies the rule."""
    mc_id = merchant_campaign["campaign_id"]
    rule = merchant_campaign.get("winner_rule") or "first_n_correct"
    max_winners = int(merchant_campaign.get("max_winners") or 1)

    # Grab all attached entries with their picks.
    correct_entries: List[Dict[str, Any]] = []
    async for me in db.merchant_predict_win_entries.find(
                                                                                                              {"merchant_campaign_id": mc_id}):
        pe = await db.predict_win_entries.find_one(
            {"entry_id": me["parent_predict_win_entry_id"]})
        if not pe:
            continue
        if pe.get("picked_option_id") != winning_option_id:
            continue
        if pe.get("status") == "void":
            continue
        correct_entries.append({
            "user_id":                        me["user_id"],
            "parent_entry_id":         me["parent_predict_win_entry_id"],
            "submitted_at":              _aware(pe.get("submitted_at")) or _now(),
        })

    if rule == "all_correct":
        return correct_entries[:max_winners] if max_winners > 0 else correct_entries
    if rule == "random_correct":
        import random
        random.shuffle(correct_entries)
        return correct_entries[:max_winners]
    # default: first_n_correct — order by submitted_at ASC.
    correct_entries.sort(key=lambda e: e["submitted_at"])
    return correct_entries[:max_winners]


async def resolve_and_award_children(db, *, parent_campaign_id: str,
                                                                                            winning_option_id: str
                                                                                            ) -> Dict[str, Any]:
    """Sweeper cascade — invoked from predict_win_sweeper after a parent
    resolves.  Idempotent: repeated calls on already-resolved children
    are no-ops."""
    now = _now()
    report = {"parent_campaign_id": parent_campaign_id,
                            "winning_option_id": winning_option_id,
                            "children_awarded": [], "children_skipped": []}
    async for mc in db.merchant_predict_win_campaigns.find(
                                                                          {"parent_predict_win_campaign_id": parent_campaign_id,
                                                                            "campaign_status": {"$in": ["live", "scheduled"]}}):
        mc_id = mc["campaign_id"]
        prize = await db.merchant_prize_inventory.find_one(
            {"prize_id": mc["prize_inventory_id"]})
        if not prize:
            report["children_skipped"].append(
                {"campaign_id": mc_id, "reason": "prize_not_found"})
            continue
        winners = await _select_winners(
            db, merchant_campaign=mc,
            winning_option_id=winning_option_id)
        # If a merchant campaign has no correct entries we still resolve
        # (release reserved inventory back).
        if not winners:
            try:
                await prize_svc.release(
                    db, prize_id=mc["prize_inventory_id"],
                    qty=int(mc.get("prize_quantity_reserved") or 0))
            except Exception:
                pass
            await db.merchant_predict_win_campaigns.update_one(
                {"campaign_id": mc_id},
                {"$set": {"campaign_status": "resolved",
                                      "resolved_at":      now,
                                      "updated_at":        now}})
            report["children_awarded"].append(
                {"campaign_id": mc_id, "n_winners": 0})
            continue

        merchant_id = mc["merchant_id"]
        offer_id = await _ensure_pw_merchant_offer(
            db, merchant_id=merchant_id,
            merchant_campaign=mc, prize=prize)

        n_awarded = 0
        for w in winners:
            wallet_item_id, coupon_id, expires_at = await _mint_wallet_and_coupon(
                db, user_id=w["user_id"], merchant_id=merchant_id,
                merchant_campaign=mc, prize=prize, offer_id=offer_id)
            award_id = _new_id("mpwa")
            await db.merchant_predict_win_awards.insert_one({
                "_id":                                                    award_id,
                "award_id":                                        award_id,
                "merchant_campaign_id":                mc_id,
                "user_id":                                        w["user_id"],
                "parent_predict_win_entry_id":  w["parent_entry_id"],
                "prize_inventory_id":                  prize["prize_id"],
                "wallet_item_id":                          wallet_item_id,
                "coupon_id":                                    coupon_id,
                "award_status":                              "awarded",
                "awarded_at":                                    now,
                "redeemed_at":                                  None,
                "expires_at":                                    expires_at,
                "notes":                                            None,
            })
            await prize_svc.award(
                db, prize_id=prize["prize_id"], qty=1)
            await analytics_svc.record_event(
                db, merchant_campaign_id=mc_id, event_type="win",
                user_id=w["user_id"],
                metadata={"award_id": award_id,
                                        "wallet_item_id": wallet_item_id,
                                        "coupon_id": coupon_id})
            n_awarded += 1

        # Release any unused reservation (max_winners > correct_entries).
        remaining = int(mc.get("prize_quantity_reserved") or 0) - n_awarded
        if remaining > 0:
            try:
                await prize_svc.release(db, prize_id=prize["prize_id"], qty=remaining)
            except Exception:
                pass

        await db.merchant_predict_win_campaigns.update_one(
            {"campaign_id": mc_id},
            {"$set": {"campaign_status": "resolved",
                                  "resolved_at":      now,
                                  "updated_at":        now}})
        report["children_awarded"].append(
            {"campaign_id": mc_id, "n_winners": n_awarded})

    return report
