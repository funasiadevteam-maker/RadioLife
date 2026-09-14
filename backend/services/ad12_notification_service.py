"""Phase AD.12a — In-app notification ads.

Advertisers create notification campaigns targeting users with specific
regions/languages/tiers.  Delivery is scoped to the in-app inbox in
this sub-phase; browser push (Progressier) is deferred to AD.12b — the
data model already accepts `channel="push"` or `"both"` and the service
silently downgrades to `in_app` when the Progressier stub isn't wired.

Billing model
-------------
- Cost-per-DELIVERY (CPD) — advertiser is billed once per (user_id,
  notification_campaign_id) idempotency key.  A user seeing the same
  notification row multiple times (bell dropdown → full page →
  re-render) fires only one billed event.
- Split routing follows AD.2 pipeline: platform fee + optional
  sponsoring-merchant net (if a merchant is attached).
- Wallet-drain auto-pauses the campaign (matching AD.11 pattern).

Approval workflow: ADMOD.1 with `ad_type="notification"`.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.ad12")


NOTIFICATION_CHANNELS = ("in_app", "push", "both")
NOTIFICATION_STATUSES = ("draft", "pending_admin", "approved", "scheduled",
                                                "live", "paused", "completed", "rejected",
                                                "requires_changes")
DELIVERY_SCHEDULES = ("immediate", "scheduled", "trigger_based")


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
async def ensure_ad12_indexes(db) -> None:
    try:
        await db.notification_campaigns.create_index(
            "notification_campaign_id", unique=True)
        await db.notification_campaigns.create_index("advertiser_id")
        await db.notification_campaigns.create_index("status")
        await db.notification_campaigns.create_index([
            ("status", 1), ("start_time", 1)])
        await db.notification_campaigns.create_index("channel")
        await db.notification_campaigns.create_index("trigger_type")
        # Deliveries
        await db.notification_deliveries.create_index(
            "delivery_id", unique=True)
        # Idempotency — one delivery row per (user, campaign).
        await db.notification_deliveries.create_index(
            [("user_id", 1), ("notification_campaign_id", 1)], unique=True)
        await db.notification_deliveries.create_index([
            ("user_id", 1), ("dismissed_at", 1), ("delivered_at", -1)])
        await db.notification_deliveries.create_index(
            "notification_campaign_id")
    except Exception as e:
        logger.warning("[ad12] index setup failed: %s", e)


# ─── Validation ─────────────────────────────────────────────────
def _validate_payload(payload: Dict[str, Any]) -> None:
    if not payload.get("title") or len(payload["title"].strip()) < 3:
        raise ValueError("title_required")
    if not payload.get("body") or len(payload["body"].strip()) < 5:
        raise ValueError("body_required")
    if not payload.get("target_url"):
        raise ValueError("target_url_required")
    channel = payload.get("channel", "in_app")
    if channel not in NOTIFICATION_CHANNELS:
        raise ValueError(f"invalid_channel:{channel}")
    schedule = payload.get("delivery_schedule", "immediate")
    if schedule not in DELIVERY_SCHEDULES:
        raise ValueError(f"invalid_delivery_schedule:{schedule}")
    if int(payload.get("budget_cents") or 0) < 100:
        raise ValueError("budget_too_small")
    cpd = int(payload.get("cost_per_delivery_cents") or 0)
    if cpd < 1 or cpd > 100000:
        raise ValueError("invalid_cost_per_delivery")


# ─── CRUD ───────────────────────────────────────────────────────
async def create_notification_campaign(db, *, advertiser_id: str,
                                                                                        user_id: str,
                                                                                        payload: Dict[str, Any]
                                                                                        ) -> Dict[str, Any]:
    _validate_payload(payload)
    now = _now()
    nid = _gen("ntf")
    targeting = payload.get("targeting") or {}
    doc = {
        "_id":                                                nid,
        "notification_campaign_id":            nid,
        "advertiser_id":                            advertiser_id,
        "sponsoring_merchant_id":              payload.get("sponsoring_merchant_id"),
        "title":                                          payload["title"].strip(),
        "body":                                            payload["body"].strip(),
        "cta_text":                                    (payload.get("cta_text") or "Learn more")[:64],
        "target_url":                                payload["target_url"].strip(),
        "icon_url":                                    None,
        "image_url":                                  None,
        "channel":                                      payload.get("channel", "in_app"),
        "delivery_schedule":                  payload.get("delivery_schedule", "immediate"),
        "scheduled_at":                            payload.get("scheduled_at"),
        "trigger_type":                            payload.get("trigger_type"),
        "targeting": {
            "region":                                    targeting.get("region"),
            "city":                                        targeting.get("city"),
            "country_codes":                      targeting.get("country_codes") or [],
            "language":                              targeting.get("language"),
            "category_tags":                      targeting.get("category_tags") or [],
            "min_user_tier":                      targeting.get("min_user_tier"),
            "exclude_recent_notified_within_hours":
                                                                int(targeting.get(
                                                                    "exclude_recent_notified_within_hours") or 24),
        },
        "budget_cents":                            int(payload["budget_cents"]),
        "spent_cents":                              0,
        "cost_per_delivery_cents":          int(payload["cost_per_delivery_cents"]),
        "max_deliveries":                          int(payload.get("max_deliveries") or 0) or None,
        "delivered_count":                        0,
        "opened_count":                            0,
        "clicked_count":                          0,
        "dismissed_count":                        0,
        "status":                                        "draft",
        "auto_paused_reason":                  None,
        "auto_paused_at":                          None,
        "created_by":                                user_id,
        "start_time":                                payload.get("start_time"),
        "end_time":                                    payload.get("end_time"),
        "created_at":                                now,
        "updated_at":                                now,
    }
    await db.notification_campaigns.insert_one(doc)
    return _serialize(doc)


async def update_notification_campaign(db, *, notification_campaign_id: str,
                                                                                        patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    doc = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    if not doc:
        return None
    if doc["status"] not in ("draft", "rejected", "requires_changes"):
        raise ValueError(f"cannot_edit_status:{doc['status']}")
    allow = {
        "title", "body", "cta_text", "target_url",
        "sponsoring_merchant_id", "budget_cents",
        "cost_per_delivery_cents", "max_deliveries",
        "channel", "delivery_schedule", "scheduled_at",
        "trigger_type", "targeting",
        "start_time", "end_time",
    }
    sets = {k: v for k, v in patch.items() if k in allow and v is not None}
    if not sets:
        return _serialize(doc)
    sets["updated_at"] = _now()
    await db.notification_campaigns.update_one(
        {"notification_campaign_id": notification_campaign_id},
        {"$set": sets})
    fresh = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    return _serialize(fresh)


async def attach_creative(db, *, notification_campaign_id: str,
                                              slot: str, url: str) -> Dict[str, Any]:
    if slot not in ("icon_url", "image_url"):
        raise ValueError(f"invalid_slot:{slot}")
    r = await db.notification_campaigns.update_one(
        {"notification_campaign_id": notification_campaign_id},
        {"$set": {slot: url, "updated_at": _now()}})
    if r.matched_count == 0:
        raise ValueError("notification_campaign_not_found")
    doc = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    return _serialize(doc)


async def publish_notification_campaign(db, *, notification_campaign_id: str
                                                                                          ) -> Dict[str, Any]:
    doc = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    if not doc:
        raise ValueError("notification_campaign_not_found")
    if not doc.get("icon_url"):
        raise ValueError("icon_required")
    # AD.12a final decision — push is deferred permanently.  Reject
    # publish for `push` or `both` channels; only `in_app` is allowed.
    # The enum value stays in the data model so AD.12b can bolt on
    # without a migration if we ever revisit.
    if doc.get("channel") in ("push", "both"):
        raise ValueError("push_channel_not_enabled")
    await db.notification_campaigns.update_one(
        {"notification_campaign_id": notification_campaign_id},
        {"$set": {"status":              "pending_admin",
                          "updated_at":      _now()}})
    fresh = await db.notification_campaigns.find_one(
        {"notification_campaign_id": notification_campaign_id})
    return _serialize(fresh)


async def list_advertiser_campaigns(db, *, advertiser_id: str
                                                                                ) -> Dict[str, Any]:
    rows = []
    async for c in db.notification_campaigns.find(
            {"advertiser_id": advertiser_id}).sort("created_at", -1):
        rows.append(_serialize(c))
    return {"items": rows, "count": len(rows)}


# ─── Delivery + Billing ─────────────────────────────────────────
async def _matches_targeting(user: Optional[dict], camp: dict) -> bool:
    """Best-effort targeting.  Missing user fields = pass (advertiser
    picked a target but we don't know the user's attribute → don't
    hard-block; better a slightly wider audience than an empty one for
    small POC-scale campaigns)."""
    if not user:
        # Anonymous inbox = eligible for open-audience campaigns.
        t = camp.get("targeting") or {}
        return not any([t.get("min_user_tier"),
                                        t.get("country_codes"),
                                        t.get("city")])
    t = camp.get("targeting") or {}
    ccs = t.get("country_codes") or []
    user_cc = str(user.get("country") or user.get("country_code")
                                    or "").upper()
    if ccs and user_cc and user_cc not in {c.upper() for c in ccs}:
        return False
    lang = t.get("language")
    user_lang = str(user.get("language") or "").lower()
    if lang and user_lang and user_lang != lang.lower():
        return False
    tier = t.get("min_user_tier")
    if tier and _tier_rank(user.get("tier")) < _tier_rank(tier):
        return False
    city = t.get("city")
    user_city = str(user.get("city") or "").lower()
    if city and user_city and user_city != city.lower():
        return False
    return True


_TIER_RANK = {"free": 0, "listener": 0, "silver": 1, "gold": 2,
                              "platinum": 3, "vip": 4}
def _tier_rank(tier: Optional[str]) -> int:
    return _TIER_RANK.get(str(tier or "").lower(), 0)


async def _auto_pause(db, notification_campaign_id: str, reason: str
                                          ) -> None:
    await db.notification_campaigns.update_one(
        {"notification_campaign_id": notification_campaign_id},
        {"$set": {"status":                          "paused",
                          "auto_paused_reason":  reason,
                          "auto_paused_at":        _now(),
                          "updated_at":                _now()}})


async def build_inbox(db, *, user: Optional[dict],
                                            limit: int = 20,
                                            unread_only: bool = False,
                                            commission_service_calc=None
                                            ) -> Dict[str, Any]:
    """Return a merged inbox: existing station_notifications + AD.12
    notification_deliveries.  Also mints the delivery row + billing on
    first eligible view for AD.12 rows the user hasn't seen yet."""
    user_id = (user or {}).get("user_id")
    items: List[Dict[str, Any]] = []
    # 1) Station notifications (legacy owner-scoped feed).  Only for
    #    logged-in users.
    if user_id:
        q: Dict[str, Any] = {"owner_user_id": user_id}
        if unread_only:
            q["read_at"] = None
        async for n in db.station_notifications.find(q).sort(
                        "created_at", -1).limit(limit):
            items.append({
                "id":                    n.get("_id") or n.get("id"),
                "kind":                "system",
                "type":                n.get("type"),
                "title":              _system_title(n),
                "body":                _system_body(n),
                "cta_text":        "View",
                "target_url":    _system_deeplink(n),
                "icon_url":        None,
                "image_url":      None,
                "is_sponsored": False,
                "delivered_at": n.get("created_at"),
                "opened_at":      n.get("read_at"),
                "dismissed_at": None,
                "created_at":    n.get("created_at"),
            })
    # 2) AD.12 notification deliveries (existing) — user's inbox.
    if user_id:
        q2: Dict[str, Any] = {"user_id":  user_id,
                                                    "dismissed_at": None}
        async for d in db.notification_deliveries.find(q2).sort(
                            "delivered_at", -1).limit(limit):
            items.append({
                "id":                    d.get("delivery_id"),
                "kind":                "sponsored",
                "type":                "ad_notification",
                "title":              d.get("title"),
                "body":                d.get("body"),
                "cta_text":        d.get("cta_text"),
                "target_url":    d.get("target_url"),
                "icon_url":        d.get("icon_url"),
                "image_url":      d.get("image_url"),
                "is_sponsored": True,
                "delivered_at": d.get("delivered_at"),
                "opened_at":      d.get("opened_at"),
                "dismissed_at": d.get("dismissed_at"),
                "created_at":    d.get("delivered_at"),
                "advertiser_id": d.get("advertiser_id"),
                "notification_campaign_id":
                                                d.get("notification_campaign_id"),
            })
    # 3) Auction: mint new deliveries for eligible LIVE campaigns the
    #    user hasn't received yet (idempotent via unique index).
    if user_id:
        newly_delivered = await _deliver_pending(
            db, user=user,
            commission_service_calc=commission_service_calc)
        # Prepend so they surface at the top of the inbox.
        for d in reversed(newly_delivered):
            items.insert(0, d)
    # Sort merged
    def _key(x):
        return (0 if x.get("opened_at") is None else 1,
                        -_epoch(x.get("delivered_at") or x.get("created_at")))
    items.sort(key=_key)
    items = items[:limit]
    return {"items": items, "count": len(items)}


def _epoch(dt) -> int:
    if not dt:
        return 0
    if isinstance(dt, datetime):
        return int(dt.timestamp())
    try:
        return int(datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
                              .timestamp())
    except Exception:
        return 0


def _system_title(n: dict) -> str:
    if n.get("type") == "new_comment":
        return f'{(n.get("payload") or {}).get("commenter_handle") or "Someone"} commented'
    if n.get("type") == "post_reaction_milestone":
        m = (n.get("payload") or {}).get("milestone")
        return f"Your post hit {m} reactions"
    if n.get("type") == "coupon_restock":
        t = (n.get("payload") or {}).get("campaign_title") or "Coupons"
        return f"“{t}” just restocked 🎟️"
    return "New activity"


def _system_body(n: dict) -> str:
    p = n.get("payload") or {}
    if n.get("type") == "new_comment":
        return (p.get("comment_excerpt") or "")[:120]
    if n.get("type") == "post_reaction_milestone":
        return f"{p.get('total_reactions') or ''} total reactions"
    if n.get("type") == "coupon_restock":
        return "Play now before it sells out again!"
    return ""


def _system_deeplink(n: dict) -> str:
    p = n.get("payload") or {}
    if n.get("type") == "coupon_restock":
        return p.get("play_url") or (f"/play/{p.get('campaign_id')}" if p.get("campaign_id") else "/play")
    slug = n.get("station_slug")
    pid = p.get("post_id") or n.get("related_post_id")
    if pid:
        return f"/r/{slug}#post-{pid}"
    return f"/r/{slug}"


async def _deliver_pending(db, *, user: dict,
                                                    commission_service_calc=None
                                                    ) -> List[Dict[str, Any]]:
    """Find LIVE campaigns the user is eligible for and hasn't received
    yet, then mint delivery rows + fire billing.  Idempotent."""
    user_id = user["user_id"]
    minted: List[Dict[str, Any]] = []
    # Cheap prefilter — cap at 20 LIVE campaigns / call.
    lives = db.notification_campaigns.find(
        {"status": "live"}).sort("created_at", -1).limit(20)
    async for c in lives:
        if not await _matches_targeting(user, c):
            continue
        # Max deliveries guard
        max_d = c.get("max_deliveries")
        if max_d and int(c.get("delivered_count") or 0) >= int(max_d):
            continue
        # Try to mint — unique index enforces one row per (user, campaign).
        delivery_id = _gen("dlv")
        now = _now()
        try:
            await db.notification_deliveries.insert_one({
                "_id":                                          delivery_id,
                "delivery_id":                          delivery_id,
                "user_id":                                    user_id,
                "notification_campaign_id":      c["notification_campaign_id"],
                "advertiser_id":                        c["advertiser_id"],
                "sponsoring_merchant_id":          c.get("sponsoring_merchant_id"),
                "title":                                      c["title"],
                "body":                                        c["body"],
                "cta_text":                                c.get("cta_text"),
                "target_url":                            c["target_url"],
                "icon_url":                                c.get("icon_url"),
                "image_url":                              c.get("image_url"),
                "channel":                                  c.get("channel", "in_app"),
                "delivered_at":                        now,
                "opened_at":                              None,
                "clicked_at":                            None,
                "dismissed_at":                        None,
                "billed":                                    False,
            })
        except Exception:
            # DuplicateKey → already delivered → skip.
            continue
        # Fire billing (per-delivery CPD, split via AD.2 pipeline).
        billed = await _bill_delivery(
            db, delivery_id=delivery_id, campaign=c,
            user_id=user_id,
            commission_service_calc=commission_service_calc)
        # Return the client-shaped row.
        minted.append({
            "id":                            delivery_id,
            "kind":                        "sponsored",
            "type":                        "ad_notification",
            "title":                      c["title"],
            "body":                        c["body"],
            "cta_text":                c.get("cta_text"),
            "target_url":            c["target_url"],
            "icon_url":                c.get("icon_url"),
            "image_url":              c.get("image_url"),
            "is_sponsored":        True,
            "delivered_at":        now,
            "opened_at":              None,
            "dismissed_at":        None,
            "created_at":            now,
            "advertiser_id":      c["advertiser_id"],
            "notification_campaign_id":
                                                    c["notification_campaign_id"],
            "billed":                    billed,
        })
    return minted


async def _bill_delivery(db, *, delivery_id: str, campaign: dict,
                                                user_id: str,
                                                commission_service_calc=None
                                                ) -> bool:
    """Atomic wallet debit + ledger row on delivery.  Idempotent via
    delivery_id — the same delivery_id can't be billed twice."""
    cost = int(campaign.get("cost_per_delivery_cents") or 0)
    if cost <= 0:
        return False
    # Guard: is this delivery already billed?
    existing = await db.notification_deliveries.find_one(
        {"delivery_id": delivery_id, "billed": True})
    if existing:
        return True
    # Atomic wallet debit.
    debit = await db.advertisers_v2.find_one_and_update(
        {"advertiser_id":                    campaign["advertiser_id"],
          "budget_available_cents":  {"$gte": cost}},
        {"$inc": {"budget_available_cents": -cost,
                          "budget_spent_cents":      cost}},
        return_document=True)
    if not debit:
        await _auto_pause(db, campaign["notification_campaign_id"],
                                            "wallet_exhausted")
        return False
    # Split routing (matches AD.4 / AD.11 shape).
    fee_result = None
    merchant_id = campaign.get("sponsoring_merchant_id")
    if merchant_id and callable(commission_service_calc):
        try:
            fee_result = await commission_service_calc(
                db, business_category="*",
                transaction_type="coupon_save",
                gross_cents=cost)
        except Exception as e:
            logger.warning("[ad12] fee calc failed: %s", e)
    if fee_result:
        app_fee = int(fee_result.get("platform_fee_cents") or 0)
        merch_net = int(fee_result.get("merchant_net_cents") or 0)
    else:
        app_fee = cost
        merch_net = 0
    tx_id = _gen("tx_ntf")
    now = _now()
    await db.payment_transactions_v2.insert_one({
        "_id":                                      tx_id,
        "transaction_id":                    tx_id,
        # Same sentinel pattern as AD.11 to avoid the unique-index null
        # collision on stripe_payment_intent_id.
        "stripe_payment_intent_id":  tx_id,
        "flow":                                      "ad12_notification_delivery",
        "event_source":                        "notification_delivery",
        "advertiser_id":                      campaign["advertiser_id"],
        "notification_campaign_id":      campaign["notification_campaign_id"],
        "delivery_id":                          delivery_id,
        "sponsoring_merchant_id":          merchant_id,
        "customer_user_id":                  user_id,
        "amount_cents":                        cost,
        "application_fee_cents":          app_fee,
        "merchant_net_cents":              merch_net,
        "status":                                    "posted",
        "created_at":                            now,
    })
    # Mark billed on the delivery row + roll-up on the campaign.
    await db.notification_deliveries.update_one(
        {"delivery_id": delivery_id},
        {"$set": {"billed": True, "billed_at": now,
                          "cost_cents": cost,
                          "app_fee_cents": app_fee,
                          "merchant_net_cents": merch_net}})
    await db.notification_campaigns.update_one(
        {"notification_campaign_id": campaign["notification_campaign_id"]},
        {"$inc": {"spent_cents": cost, "delivered_count": 1},
          "$set": {"updated_at": now}})
    # Belt-and-suspenders auto-pause on budget exhaustion.
    remaining = int(debit.get("budget_available_cents", 0))
    if remaining < cost:
        await _auto_pause(db, campaign["notification_campaign_id"],
                                            "wallet_exhausted")
    total_budget = int(campaign.get("budget_cents", 0))
    if int(campaign.get("spent_cents", 0)) + cost >= total_budget:
        await _auto_pause(db, campaign["notification_campaign_id"],
                                            "budget_exhausted")
    return True


# ─── Per-delivery lifecycle actions ─────────────────────────────
async def mark_opened(db, *, delivery_id: str, user_id: Optional[str]
                                          ) -> Dict[str, Any]:
    q: Dict[str, Any] = {"delivery_id": delivery_id}
    if user_id:
        q["user_id"] = user_id
    doc = await db.notification_deliveries.find_one_and_update(
        q, {"$set": {"opened_at": _now()}}, return_document=True)
    if not doc:
        return {"ok": False, "reason": "not_found"}
    # Roll-up
    await db.notification_campaigns.update_one(
        {"notification_campaign_id": doc["notification_campaign_id"]},
        {"$inc": {"opened_count": 1}})
    return {"ok": True, "delivery_id": delivery_id}


async def mark_clicked(db, *, delivery_id: str, user_id: Optional[str]
                                            ) -> Dict[str, Any]:
    q: Dict[str, Any] = {"delivery_id": delivery_id}
    if user_id:
        q["user_id"] = user_id
    doc = await db.notification_deliveries.find_one_and_update(
        q, {"$set": {"clicked_at": _now(),
                                  "opened_at":  _now()}},
        return_document=True)
    if not doc:
        return {"ok": False, "reason": "not_found"}
    await db.notification_campaigns.update_one(
        {"notification_campaign_id": doc["notification_campaign_id"]},
        {"$inc": {"clicked_count": 1}})
    return {"ok": True, "delivery_id": delivery_id,
                  "target_url": doc.get("target_url")}


async def mark_dismissed(db, *, delivery_id: str, user_id: Optional[str]
                                              ) -> Dict[str, Any]:
    q: Dict[str, Any] = {"delivery_id": delivery_id}
    if user_id:
        q["user_id"] = user_id
    doc = await db.notification_deliveries.find_one_and_update(
        q, {"$set": {"dismissed_at": _now()}}, return_document=True)
    if not doc:
        return {"ok": False, "reason": "not_found"}
    await db.notification_campaigns.update_one(
        {"notification_campaign_id": doc["notification_campaign_id"]},
        {"$inc": {"dismissed_count": 1}})
    return {"ok": True, "delivery_id": delivery_id}


async def unread_count(db, *, user_id: str) -> int:
    """Count of un-opened, un-dismissed sponsored deliveries + unread
    station notifications for this user."""
    a = await db.notification_deliveries.count_documents(
        {"user_id": user_id, "opened_at": None, "dismissed_at": None})
    b = await db.station_notifications.count_documents(
        {"owner_user_id": user_id, "read_at": None})
    return int(a) + int(b)


# ─── Analytics ──────────────────────────────────────────────────
async def advertiser_notification_analytics(db, *, advertiser_id: str,
                                                                                                    days: int = 30
                                                                                                    ) -> Dict[str, Any]:
    since = _now() - timedelta(days=days)
    campaigns = []
    async for c in db.notification_campaigns.find(
                {"advertiser_id": advertiser_id,
                  "updated_at": {"$gte": since}}
            ).sort("created_at", -1):
        delivered = int(c.get("delivered_count") or 0)
        opened      = int(c.get("opened_count") or 0)
        clicked    = int(c.get("clicked_count") or 0)
        ctr = round((clicked / delivered * 100), 3) if delivered else 0.0
        campaigns.append({
            "notification_campaign_id": c["notification_campaign_id"],
            "title":                                        c["title"],
            "status":                                      c["status"],
            "channel":                                    c.get("channel"),
            "spend_cents":                            int(c.get("spent_cents") or 0),
            "budget_cents":                          int(c.get("budget_cents") or 0),
            "delivered_count":                    delivered,
            "opened_count":                          opened,
            "clicked_count":                        clicked,
            "dismissed_count":                    int(c.get("dismissed_count") or 0),
            "ctr_percent":                          ctr,
        })
    totals = {
        "spend_cents":              sum(x["spend_cents"] for x in campaigns),
        "delivered_count":    sum(x["delivered_count"] for x in campaigns),
        "opened_count":          sum(x["opened_count"] for x in campaigns),
        "clicked_count":        sum(x["clicked_count"] for x in campaigns),
    }
    if totals["delivered_count"]:
        totals["ctr_percent"] = round(
            totals["clicked_count"] / totals["delivered_count"] * 100, 3)
    else:
        totals["ctr_percent"] = 0.0
    return {"campaigns": campaigns, "totals": totals}


__all__ = [
    "ensure_ad12_indexes",
    "create_notification_campaign",
    "update_notification_campaign",
    "attach_creative",
    "publish_notification_campaign",
    "list_advertiser_campaigns",
    "build_inbox",
    "mark_opened",
    "mark_clicked",
    "mark_dismissed",
    "unread_count",
    "advertiser_notification_analytics",
    "NOTIFICATION_CHANNELS",
    "NOTIFICATION_STATUSES",
    "DELIVERY_SCHEDULES",
]
