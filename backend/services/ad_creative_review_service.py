"""Phase ADMOD.1 — Unified creative-review queue.

ONE queue for every advertiser creative asset in the platform:
- advertiser_campaign  (AD.1)
- coupon_campaign      (AD.4)
- banner               (AD.11 — reserved)
- notification         (AD.12 — reserved)
- preroll_audio        (FLAGADMIN.1)
- sponsored_game       (PG.1 sponsorships)
- sponsored_predict_win (idle placeholder)
- sponsored_trivia     (idle placeholder)

Collection: `ad_creative_reviews`.
Audit trail: `ad_review_audit`.

Approval / rejection / require-changes flip the underlying target's
status (ad_campaigns_v2.status / coupon_campaigns.status / ...) so the
existing customer-side gating (list_live_coupon_campaigns, etc.)
continues to work unchanged.

Auto-moderation on submission is optional — see
`ad_moderation_service.moderate_creative_text`.  Skipped gracefully
when the Emergent LLM key is missing or the API errors.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services.ad_moderation_service import moderate_creative_text

logger = logging.getLogger("bigfm.ad_review")


# ─── Types ──────────────────────────────────────────────────────
AD_TYPES = (
    "advertiser_campaign",
    "coupon_campaign",
    "banner",
    "notification",
    "preroll_audio",
    "sponsored_game",
    "sponsored_predict_win",              # PW-M merchant-branded activations
    "advertiser_pw_sponsorship",  # Phase AD.3 — brand overlay on any PW parent
    "sponsored_trivia",
)

REVIEW_STATUSES = ("pending", "approved", "rejected", "requires_changes")

# Which underlying collection + status field to flip for each ad_type.
# The service reflects target status back to keep customer surfaces gated.
TARGET_TABLE = {
    "advertiser_campaign":          ("ad_campaigns_v2", "campaign_id", "status"),
    "coupon_campaign":                ("coupon_campaigns", "campaign_id", "status"),
    "sponsored_game":                ("ad_campaigns_v2", "campaign_id", "status"),
    "preroll_audio":                  ("preroll_ads",         "id",                    "status"),
    "sponsored_predict_win":  ("merchant_predict_win_campaigns", "campaign_id", "approval_status"),
    # Phase AD.3 — advertiser BRAND overlay on any PW parent (distinct
    # from PW-M merchant-branded activations).
    "advertiser_pw_sponsorship": ("predict_win_sponsorships", "sponsorship_id", "status"),
    # Phase AD.11 — banner-campaign approval flow.
    "banner":                              ("banner_campaigns", "banner_id", "status"),
    # Phase AD.12a — notification-ad approval flow.
    "notification":                    ("notification_campaigns", "notification_campaign_id", "status"),
    # Idle placeholders wired but with no target table yet.
    "sponsored_trivia":              (None, None, None),
}

# Mapping from review action → underlying-target status value.
TARGET_STATUS_ON_APPROVE = {
    "advertiser_campaign":          "active",
    "coupon_campaign":                "live",
    "sponsored_game":                "active",
    "preroll_audio":                  "active",
    "sponsored_predict_win":  "approved",
    "advertiser_pw_sponsorship": "live",
    "banner":                              "live",
    "notification":                    "live",
}
TARGET_STATUS_ON_REJECT = {
    "advertiser_campaign":          "rejected",
    "coupon_campaign":                "rejected",
    "sponsored_game":                "rejected",
    "preroll_audio":                  "rejected",
    "sponsored_predict_win":  "rejected",
    "advertiser_pw_sponsorship": "rejected",
    "banner":                              "rejected",
    "notification":                    "rejected",
}
# When the reviewer sends a row back for edits, we want the advertiser to
# regain edit access — flip target status back to "draft" (per phase).
TARGET_STATUS_ON_REQUIRE_CHANGES = {
    "advertiser_campaign":          "draft",
    "coupon_campaign":                "draft",
    "sponsored_game":                "draft",
    "preroll_audio":                  "draft",
    "sponsored_predict_win":  "draft",
    "advertiser_pw_sponsorship": "draft",
    "banner":                              "draft",
    "notification":                    "draft",
}


# ─── Small helpers ──────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else dt


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _priority_score(*, ad_type: str, moderation: Dict[str, Any]) -> int:
    """Higher = review first.  AI-flagged rows bubble up (60+).  Coupon
    campaigns are relatively cheap so they sit under advertiser
    campaigns (which have larger budgets)."""
    base = {
        "advertiser_campaign":          50,
        "sponsored_game":                50,
        "coupon_campaign":                40,
        "preroll_audio":                  60,   # audio has higher moderation risk
        "banner":                              45,
        "notification":                    55,
        "sponsored_predict_win":  55,
        "sponsored_trivia":              55,
    }.get(ad_type, 40)
    if (moderation or {}).get("action_taken") == "flagged":
        base += 30
    return base


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ─── Indexes ────────────────────────────────────────────────────
async def ensure_ad_review_indexes(db) -> None:
    try:
        await db.ad_creative_reviews.create_index("review_id", unique=True)
        await db.ad_creative_reviews.create_index(
            [("review_status", 1),
              ("priority_score", -1),
              ("submitted_at", 1)],
            name="idx_review_queue_sort")
        await db.ad_creative_reviews.create_index(
            [("advertiser_id", 1), ("review_status", 1)])
        # One active review row per target (ad_type + target_id).
        await db.ad_creative_reviews.create_index(
            [("ad_type", 1), ("target_id", 1), ("review_status", 1)])
        await db.ad_creative_reviews.create_index("submitted_at")
        await db.ad_review_audit.create_index([("review_id", 1),
                                                                                              ("created_at", -1)])
        await db.ad_review_audit.create_index("actor_user_id")
    except Exception as e:
        logger.warning("[ad-review] index setup failed: %s", e)


# ─── Audit ──────────────────────────────────────────────────────
async def _audit(db, *, review_id: str, actor_user_id: str,
                          action: str, before_status: Optional[str],
                          after_status: Optional[str],
                          notes: Optional[str] = None,
                          reason: Optional[str] = None) -> None:
    try:
        aid = _gen("aud")
        await db.ad_review_audit.insert_one({
            "_id":                          aid,
            "audit_id":                  aid,
            "review_id":                review_id,
            "actor_user_id":        actor_user_id,
            "action":                      action,
            "before_status":        before_status,
            "after_status":          after_status,
            "notes":                      (notes or "")[:500],
            "reason":                      (reason or "")[:500],
            "created_at":              _now(),
        })
    except Exception as e:
        logger.warning("[ad-review] audit write failed: %s", e)


# ─── Snapshot builders (per ad_type) ────────────────────────────
async def _build_snapshot(db, ad_type: str, target_id: str) -> Dict[str, Any]:
    """Freeze a small preview of the creative at submission time so
    reviewers see what they're moderating even if the advertiser
    edits after submission."""
    snap: Dict[str, Any] = {"ad_type": ad_type, "target_id": target_id}
    try:
        if ad_type == "advertiser_campaign":
            c = await db.ad_campaigns_v2.find_one({"campaign_id": target_id})
            if c:
                snap.update({
                    "name":                    c.get("name"),
                    "campaign_type":  c.get("campaign_type"),
                    "creative":            c.get("creative") or {},
                    "budget_cents":    c.get("budget_total_cents"),
                    "cpm_cents":            c.get("cpm_cents"),
                    "advertiser_id":  c.get("advertiser_id"),
                })
        elif ad_type == "coupon_campaign":
            c = await db.coupon_campaigns.find_one({"campaign_id": target_id})
            if c:
                snap.update({
                    "title":                          c.get("title"),
                    "description":              c.get("description"),
                    "terms":                          c.get("terms"),
                    "cost_per_save_cents":  c.get("cost_per_save_cents"),
                    "total_inventory":      c.get("total_inventory"),
                    "retail_value_cents":  c.get("retail_value_cents"),
                    "value_currency":        c.get("value_currency"),
                    "logo_url":                    c.get("logo_url"),
                    "hero_image_url":        c.get("hero_image_url"),
                    "advertiser_id":            c.get("advertiser_id"),
                    "sponsoring_merchant_id": c.get("sponsoring_merchant_id"),
                })
        elif ad_type == "preroll_audio":
            c = await db.preroll_ads.find_one({"id": target_id}) \
                          or await db.preroll_ads.find_one({"_id": target_id})
            if c:
                snap.update({
                    "headline":              c.get("headline"),
                    "audio_url":            c.get("audio_url"),
                    "companion_headline": c.get("companion_headline"),
                    "companion_cta":      c.get("companion_cta"),
                    "advertiser_id":    c.get("advertiser_id"),
                })
        elif ad_type == "sponsored_predict_win":
            c = await db.merchant_predict_win_campaigns.find_one(
                {"campaign_id": target_id})
            if c:
                snap.update({
                    "title":                    c.get("title"),
                    "description":        c.get("description"),
                    "advertiser_id":  c.get("advertiser_id"),
                    "merchant_id":        c.get("merchant_id"),
                })
        elif ad_type == "banner":
            # Phase AD.11 — banner-campaign snapshot for the reviewer.
            c = await db.banner_campaigns.find_one({"banner_id": target_id})
            if c:
                snap.update({
                    "title":                              c.get("title"),
                    "description":                  c.get("description"),
                    "cta_text":                        c.get("cta_text"),
                    "target_url":                    c.get("target_url"),
                    "placement_zones":            c.get("placement_zones"),
                    "creative_urls":                c.get("creative_urls"),
                    "per_zone_cpm_cents":      c.get("per_zone_cpm_cents"),
                    "total_budget_cents":      c.get("total_budget_cents"),
                    "advertiser_id":                c.get("advertiser_id"),
                    "sponsoring_merchant_id":  c.get("sponsoring_merchant_id"),
                })
        elif ad_type == "notification":
            # Phase AD.12a — notification-ad snapshot for the reviewer.
            c = await db.notification_campaigns.find_one(
                {"notification_campaign_id": target_id})
            if c:
                snap.update({
                    "title":                                    c.get("title"),
                    "body":                                      c.get("body"),
                    "cta_text":                              c.get("cta_text"),
                    "target_url":                          c.get("target_url"),
                    "icon_url":                              c.get("icon_url"),
                    "image_url":                            c.get("image_url"),
                    "channel":                                c.get("channel"),
                    "delivery_schedule":              c.get("delivery_schedule"),
                    "trigger_type":                      c.get("trigger_type"),
                    "cost_per_delivery_cents":  c.get("cost_per_delivery_cents"),
                    "budget_cents":                      c.get("budget_cents"),
                    "targeting":                            c.get("targeting"),
                    "advertiser_id":                    c.get("advertiser_id"),
                    "sponsoring_merchant_id":    c.get("sponsoring_merchant_id"),
                })
        elif ad_type == "advertiser_pw_sponsorship":
            # Phase AD.3 — PW sponsorship snapshot for the reviewer.
            sp = await db.predict_win_sponsorships.find_one(
                {"sponsorship_id": target_id})
            if sp:
                snap.update({
                    "brand_name":                        sp.get("brand_name"),
                    "tagline":                            sp.get("tagline"),
                    "brand_asset_url":              sp.get("brand_asset_url"),
                    "pricing_model":                sp.get("pricing_model"),
                    "cpe_cents":                        sp.get("cpe_cents"),
                    "cpi_cents":                        sp.get("cpi_cents"),
                    "budget_cents":                  sp.get("budget_cents"),
                    "parent_campaign_id":        sp.get("parent_campaign_id"),
                    "parent_snapshot":              sp.get("parent_snapshot"),
                    "targeting":                        sp.get("targeting_json"),
                    "advertiser_id":                sp.get("advertiser_id"),
                })
    except Exception as e:
        logger.warning("[ad-review] snapshot build failed (%s): %s",
                                      ad_type, e)
    return snap


def _snapshot_text_parts(snap: Dict[str, Any]) -> List[Optional[str]]:
    """Which fields feed OpenAI moderation for this snapshot?"""
    parts: List[Optional[str]] = []
    # Common
    parts.append(snap.get("title"))
    parts.append(snap.get("name"))
    parts.append(snap.get("description"))
    parts.append(snap.get("body"))
    parts.append(snap.get("terms"))
    parts.append(snap.get("headline"))
    parts.append(snap.get("companion_headline"))
    parts.append(snap.get("companion_cta"))
    parts.append(snap.get("cta_text"))
    creative = snap.get("creative") or {}
    if isinstance(creative, dict):
        parts.append(creative.get("headline"))
        parts.append(creative.get("body"))
        parts.append(creative.get("call_to_action"))
    return parts


# ─── Core CRUD ──────────────────────────────────────────────────
async def create_review(db, *, ad_type: str, target_id: str,
                                              advertiser_id: str, submitted_by: str,
                                              run_moderation: bool = True) -> Dict[str, Any]:
    """Create (or refresh) a pending review row for a creative.

    Idempotent on (ad_type, target_id) — if an active row exists we
    move it back to `pending` with a fresh moderation pass.
    """
    if ad_type not in AD_TYPES:
        raise ValueError(f"invalid_ad_type:{ad_type}")

    now = _now()
    snap = await _build_snapshot(db, ad_type, target_id)
    moderation = None
    if run_moderation:
        try:
            moderation = await moderate_creative_text(
                _snapshot_text_parts(snap))
        except Exception as e:  # ultra-defensive
            logger.warning("[ad-review] moderation failed: %s", e)
            moderation = None

    # Phase PREROLL.EXT — VIP boost lifts pending priority so bad actors
    # sit at the bottom and VIP advertisers jump the queue.
    boost = 0
    try:
        adv = await db.advertisers_v2.find_one(
            {"advertiser_id": advertiser_id},
            {"priority_score_boost": 1})
        boost = int((adv or {}).get("priority_score_boost") or 0)
    except Exception:
        pass
    priority = _priority_score(ad_type=ad_type,
                                                          moderation=moderation or {}) + boost

    existing = await db.ad_creative_reviews.find_one(
        {"ad_type": ad_type, "target_id": target_id,
          "review_status": {"$in": ["pending", "requires_changes",
                                                        "approved", "rejected"]}})
    if existing:
        review_id = existing["review_id"]
        await db.ad_creative_reviews.update_one(
            {"review_id": review_id},
            {"$set": {
                "review_status":              "pending",
                "submitted_at":                  now,
                "submitted_by":                  submitted_by,
                "priority_score":              priority,
                "auto_moderation_result":  moderation,
                "creative_snapshot":          snap,
                "updated_at":                    now,
                # Clear reviewer-side fields so requeue looks fresh.
                "reviewer_user_id":            None,
                "reviewed_at":                    None,
                "review_notes":                  None,
                "reject_reason":                None,
            }})
        await _audit(db, review_id=review_id, actor_user_id=submitted_by,
                              action="resubmit",
                              before_status=existing.get("review_status"),
                              after_status="pending")
    else:
        review_id = _gen("acr")
        await db.ad_creative_reviews.insert_one({
            "_id":                                review_id,
            "review_id":                      review_id,
            "ad_type":                          ad_type,
            "target_id":                      target_id,
            "advertiser_id":              advertiser_id,
            "submitted_at":                now,
            "submitted_by":                submitted_by,
            "review_status":              "pending",
            "reviewer_user_id":          None,
            "reviewed_at":                  None,
            "review_notes":                None,
            "reject_reason":              None,
            "auto_moderation_result":  moderation,
            "priority_score":              priority,
            "creative_snapshot":          snap,
            "created_at":                    now,
            "updated_at":                    now,
        })
        await _audit(db, review_id=review_id, actor_user_id=submitted_by,
                              action="submit", before_status=None,
                              after_status="pending")
    doc = await db.ad_creative_reviews.find_one({"review_id": review_id})
    return _serialize(doc)


async def _flip_target_status(db, *, ad_type: str, target_id: str,
                                                                new_status: str) -> None:
    tbl, key, field = TARGET_TABLE.get(ad_type, (None, None, None))
    if not tbl:
        return
    try:
        coll = getattr(db, tbl)
        # id primary key varies across tables — support both `key` and `_id`.
        r = await coll.update_one({key: target_id},
                                                                    {"$set": {field: new_status,
                                                                                                "updated_at": _now()}})
        if r.matched_count == 0:
            await coll.update_one({"_id": target_id},
                                                        {"$set": {field: new_status,
                                                                            "updated_at": _now()}})
    except Exception as e:
        logger.warning("[ad-review] target flip failed (%s → %s): %s",
                                      ad_type, new_status, e)


async def approve_review(db, *, review_id: str,
                                                    reviewer_user_id: str,
                                                    notes: Optional[str] = None) -> Optional[dict]:
    doc = await db.ad_creative_reviews.find_one({"review_id": review_id})
    if not doc:
        return None
    if doc["review_status"] == "approved":
        return _serialize(doc)
    now = _now()
    await db.ad_creative_reviews.update_one(
        {"review_id": review_id},
        {"$set": {"review_status":        "approved",
                          "reviewer_user_id":  reviewer_user_id,
                          "reviewed_at":          now,
                          "review_notes":        (notes or "")[:500],
                          "reject_reason":        None,
                          "updated_at":            now}})
    target_status = TARGET_STATUS_ON_APPROVE.get(doc["ad_type"])
    if target_status:
        await _flip_target_status(db, ad_type=doc["ad_type"],
                                                              target_id=doc["target_id"],
                                                              new_status=target_status)
    await _audit(db, review_id=review_id, actor_user_id=reviewer_user_id,
                          action="approve",
                          before_status=doc["review_status"],
                          after_status="approved", notes=notes)
    return _serialize(await db.ad_creative_reviews.find_one(
        {"review_id": review_id}))


async def reject_review(db, *, review_id: str, reviewer_user_id: str,
                                                  reason: str,
                                                  notes: Optional[str] = None) -> Optional[dict]:
    doc = await db.ad_creative_reviews.find_one({"review_id": review_id})
    if not doc:
        return None
    now = _now()
    await db.ad_creative_reviews.update_one(
        {"review_id": review_id},
        {"$set": {"review_status":        "rejected",
                          "reviewer_user_id":  reviewer_user_id,
                          "reviewed_at":          now,
                          "reject_reason":        (reason or "")[:500],
                          "review_notes":        (notes or "")[:500],
                          "updated_at":            now}})
    target_status = TARGET_STATUS_ON_REJECT.get(doc["ad_type"])
    if target_status:
        await _flip_target_status(db, ad_type=doc["ad_type"],
                                                              target_id=doc["target_id"],
                                                              new_status=target_status)
    await _audit(db, review_id=review_id, actor_user_id=reviewer_user_id,
                          action="reject",
                          before_status=doc["review_status"],
                          after_status="rejected", notes=notes, reason=reason)
    return _serialize(await db.ad_creative_reviews.find_one(
        {"review_id": review_id}))


async def require_changes(db, *, review_id: str, reviewer_user_id: str,
                                                    notes: str) -> Optional[dict]:
    doc = await db.ad_creative_reviews.find_one({"review_id": review_id})
    if not doc:
        return None
    now = _now()
    await db.ad_creative_reviews.update_one(
        {"review_id": review_id},
        {"$set": {"review_status":        "requires_changes",
                          "reviewer_user_id":  reviewer_user_id,
                          "reviewed_at":          now,
                          "review_notes":        (notes or "")[:500],
                          "reject_reason":        None,
                          "updated_at":            now}})
    target_status = TARGET_STATUS_ON_REQUIRE_CHANGES.get(doc["ad_type"])
    if target_status:
        await _flip_target_status(db, ad_type=doc["ad_type"],
                                                              target_id=doc["target_id"],
                                                              new_status=target_status)
    await _audit(db, review_id=review_id, actor_user_id=reviewer_user_id,
                          action="require_changes",
                          before_status=doc["review_status"],
                          after_status="requires_changes", notes=notes)
    return _serialize(await db.ad_creative_reviews.find_one(
        {"review_id": review_id}))


async def bulk_approve(db, *, review_ids: List[str], reviewer_user_id: str,
                                              notes: Optional[str] = None) -> Dict[str, Any]:
    approved: List[str] = []
    errors: Dict[str, str] = {}
    for rid in review_ids[:100]:   # cap batch
        try:
            doc = await approve_review(db, review_id=rid,
                                                                      reviewer_user_id=reviewer_user_id,
                                                                      notes=notes)
            if doc:
                approved.append(rid)
            else:
                errors[rid] = "not_found"
        except Exception as e:  # noqa: BLE001
            errors[rid] = str(e)[:100]
    return {"approved": approved, "errors": errors,
                  "approved_count": len(approved)}


async def bulk_reject(db, *, review_ids: List[str], reviewer_user_id: str,
                                          reason: str,
                                          notes: Optional[str] = None) -> Dict[str, Any]:
    rejected: List[str] = []
    errors: Dict[str, str] = {}
    for rid in review_ids[:100]:
        try:
            doc = await reject_review(db, review_id=rid,
                                                                    reviewer_user_id=reviewer_user_id,
                                                                    reason=reason, notes=notes)
            if doc:
                rejected.append(rid)
            else:
                errors[rid] = "not_found"
        except Exception as e:
            errors[rid] = str(e)[:100]
    return {"rejected": rejected, "errors": errors,
                  "rejected_count": len(rejected)}


# ─── Listings + analytics ───────────────────────────────────────
async def list_queue(db, *, status: Optional[str] = "pending",
                                          ad_type: Optional[str] = None,
                                          advertiser_id: Optional[str] = None,
                                          flagged_only: bool = False,
                                          sort: str = "priority",
                                          limit: int = 50) -> Dict[str, Any]:
    q: Dict[str, Any] = {}
    if status and status != "all":
        q["review_status"] = status
    if ad_type:
        q["ad_type"] = ad_type
    if advertiser_id:
        q["advertiser_id"] = advertiser_id
    if flagged_only:
        q["auto_moderation_result.action_taken"] = "flagged"
    if sort == "newest":
        srt = [("submitted_at", -1)]
    elif sort == "oldest":
        srt = [("submitted_at", 1)]
    else:  # priority
        srt = [("priority_score", -1), ("submitted_at", 1)]

    rows = await db.ad_creative_reviews.find(q).sort(srt).to_list(
        min(int(limit or 50), 200))
    items = [_serialize(r) for r in rows]
    # Enrich with advertiser name/logo for the queue UI.
    ids = list({r.get("advertiser_id") for r in items if r.get("advertiser_id")})
    adv_map: Dict[str, Dict[str, Any]] = {}
    if ids:
        async for a in db.advertisers_v2.find(
                {"advertiser_id": {"$in": ids}},
                {"advertiser_id": 1, "name": 1, "logo_url": 1, "status": 1}):
            adv_map[a.get("advertiser_id")] = {
                "name":          a.get("name"),
                "logo_url":  a.get("logo_url"),
                "status":      a.get("status"),
            }
    for it in items:
        it["advertiser"] = adv_map.get(it.get("advertiser_id"))
    return {"items": items, "count": len(items)}


async def get_review_detail(db, *, review_id: str) -> Optional[Dict[str, Any]]:
    doc = await db.ad_creative_reviews.find_one({"review_id": review_id})
    if not doc:
        return None
    view = _serialize(doc)
    if view.get("advertiser_id"):
        adv = await db.advertisers_v2.find_one(
            {"advertiser_id": view["advertiser_id"]},
            {"advertiser_id": 1, "name": 1, "logo_url": 1, "status": 1,
              "owner_user_id": 1})
        view["advertiser"] = _serialize(adv)
        # Past-reject count — useful reviewer signal.
        past_rej = await db.ad_creative_reviews.count_documents(
            {"advertiser_id": view["advertiser_id"],
              "review_status": "rejected"})
        view["advertiser_past_reject_count"] = past_rej
    return view


async def analytics_summary(db, *, days: int = 14) -> Dict[str, Any]:
    since = _now() - timedelta(days=days)
    # Buckets by status
    by_status = await db.ad_creative_reviews.aggregate([
        {"$group": {"_id": "$review_status", "count": {"$sum": 1}}}
    ]).to_list(20)
    # Rolling window: submissions + reviews in the last N days
    by_day = await db.ad_creative_reviews.aggregate([
        {"$match": {"submitted_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d",
                                                                    "date": "$submitted_at"}},
            "submitted": {"$sum": 1},
            "approved":  {"$sum": {"$cond": [
                {"$eq": ["$review_status", "approved"]}, 1, 0]}},
            "rejected":  {"$sum": {"$cond": [
                {"$eq": ["$review_status", "rejected"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(60)
    # Average time-to-review on reviewed rows in the window
    ttr = await db.ad_creative_reviews.aggregate([
        {"$match": {"reviewed_at": {"$gte": since,
                                                                        "$ne": None}}},
        {"$project": {"secs": {"$divide": [
            {"$subtract": ["$reviewed_at", "$submitted_at"]}, 1000]}}},
        {"$group": {"_id": None, "avg_secs": {"$avg": "$secs"},
                                "count": {"$sum": 1}}},
    ]).to_list(1)
    ttr_row = ttr[0] if ttr else {"avg_secs": 0, "count": 0}
    # Top rejected advertisers
    top_rejected = await db.ad_creative_reviews.aggregate([
        {"$match": {"review_status": "rejected"}},
        {"$group": {"_id": "$advertiser_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]).to_list(10)
    # Enrich advertiser names
    ids = [r["_id"] for r in top_rejected if r.get("_id")]
    adv_names: Dict[str, str] = {}
    if ids:
        async for a in db.advertisers_v2.find(
                {"advertiser_id": {"$in": ids}}, {"advertiser_id": 1, "name": 1}):
            adv_names[a.get("advertiser_id")] = a.get("name")
    top_rejected_view = [{"advertiser_id": r["_id"],
                                                "advertiser_name": adv_names.get(r["_id"], "—"),
                                                "reject_count":      r["count"]}
                                              for r in top_rejected]
    totals = {r["_id"]: r["count"] for r in by_status}
    total_reviewed = totals.get("approved", 0) + totals.get("rejected", 0)
    approval_rate = (round(totals.get("approved", 0) / total_reviewed * 100, 2)
                                        if total_reviewed else 0)
    return {
        "window_days":        days,
        "by_status":            totals,
        "by_day":                  by_day,
        "top_rejected":      top_rejected_view,
        "avg_secs_to_review": round(float(ttr_row.get("avg_secs") or 0), 1),
        "reviewed_in_window": ttr_row.get("count", 0),
        "approval_rate_pct":  approval_rate,
    }


async def list_blocked_advertisers(db, *, limit: int = 100) -> Dict[str, Any]:
    rows = await db.advertisers_v2.find(
        {"status": "blocked"},
        {"advertiser_id": 1, "name": 1, "logo_url": 1,
          "status": 1, "blocked_at": 1, "blocked_by": 1, "blocked_reason": 1,
          "owner_user_id": 1}
    ).sort([("blocked_at", -1)]).to_list(min(int(limit or 100), 200))
    return {"items": [_serialize(r) for r in rows],
                  "count": len(rows)}


async def block_advertiser(db, *, advertiser_id: str,
                                                    actor_user_id: str,
                                                    reason: str) -> Optional[Dict[str, Any]]:
    now = _now()
    r = await db.advertisers_v2.find_one_and_update(
        {"advertiser_id": advertiser_id},
        {"$set": {"status":                  "blocked",
                          "blocked_at":            now,
                          "blocked_by":            actor_user_id,
                          "blocked_reason":  (reason or "")[:500],
                          "updated_at":            now}},
        return_document=True)
    if not r:
        return None
    await _audit(db, review_id=f"advertiser:{advertiser_id}",
                          actor_user_id=actor_user_id,
                          action="advertiser_block",
                          before_status=None, after_status="blocked",
                          notes=reason, reason=reason)
    return _serialize(r)


async def unblock_advertiser(db, *, advertiser_id: str,
                                                        actor_user_id: str) -> Optional[Dict[str, Any]]:
    now = _now()
    r = await db.advertisers_v2.find_one_and_update(
        {"advertiser_id": advertiser_id},
        {"$set": {"status":                  "active",
                          "unblocked_at":        now,
                          "unblocked_by":        actor_user_id,
                          "updated_at":            now},
          "$unset": {"blocked_at": "", "blocked_by": "",
                              "blocked_reason": ""}},
        return_document=True)
    if not r:
        return None
    await _audit(db, review_id=f"advertiser:{advertiser_id}",
                          actor_user_id=actor_user_id,
                          action="advertiser_unblock",
                          before_status="blocked", after_status="active")
    return _serialize(r)


async def is_advertiser_blocked(db, advertiser_id: str) -> bool:
    r = await db.advertisers_v2.find_one(
        {"advertiser_id": advertiser_id}, {"status": 1})
    return (r or {}).get("status") == "blocked"


async def list_audit_log(db, *, limit: int = 100,
                                              review_id: Optional[str] = None,
                                              actor_user_id: Optional[str] = None) -> Dict[str, Any]:
    q: Dict[str, Any] = {}
    if review_id:
        q["review_id"] = review_id
    if actor_user_id:
        q["actor_user_id"] = actor_user_id
    rows = await db.ad_review_audit.find(q).sort(
        [("created_at", -1)]).to_list(min(int(limit or 100), 500))
    return {"items": [_serialize(r) for r in rows], "count": len(rows)}


# ─── Phase PREROLL.EXT — Top Spenders + priority bump ───────────
# Ad-type → (collection, spend_field_expr).  Spend is expressed in cents
# on the underlying transaction/campaign rows.  For AD.4 saves we lean
# on payment_transactions_v2, for AD.1/preroll we aggregate ad_serve_events,
# for sponsored games we sum sponsored_prizes; unknowns just return 0.
async def top_spenders(db, *, ad_type: Optional[str] = None,
                                          window_days: int = 30,
                                          limit: int = 10) -> Dict[str, Any]:
    """Return top advertisers by spend across ALL supported ad types.

    Filter by ad_type if provided (uses the same enum as
    ad_creative_reviews.ad_type).  Aggregates from multiple sources —
    payment_transactions_v2 for AD.4 coupon saves + AD.2 game splits,
    ad_serve_events for AD.1 campaign impressions, ad_creative_reviews
    for review stats (reject rate + avg TTR).
    """
    since = _now() - timedelta(days=max(1, int(window_days or 30)))
    spend_by_adv: Dict[str, int] = {}

    async def _accumulate(adv_id, cents):
        if not adv_id or not cents:
            return
        spend_by_adv[adv_id] = spend_by_adv.get(adv_id, 0) + int(cents or 0)

    # payment_transactions_v2 — coupon_save + sponsored game splits, etc.
    ptx_q: Dict[str, Any] = {"created_at": {"$gte": since}}
    if ad_type == "coupon_campaign":
        ptx_q["flow"] = "ad4_coupon_save_split"
    elif ad_type == "sponsored_game":
        ptx_q["flow"] = "ad2_game_split"
    elif ad_type is None or ad_type == "":
        pass  # any flow
    async for tx in db.payment_transactions_v2.find(ptx_q,
              {"advertiser_id": 1, "amount_cents": 1, "flow": 1}):
        adv = tx.get("advertiser_id")
        if not adv:
            continue
        # Restrict flow-scoped rows already filtered above.
        await _accumulate(adv, tx.get("amount_cents"))

    # ad_serve_events — AD.1 CPM billing (best-effort; if the collection
    # doesn't exist yet the query just returns nothing).
    if ad_type in (None, "", "advertiser_campaign"):
        try:
            async for e in db.ad_serve_events.find(
                    {"created_at": {"$gte": since}},
                    {"advertiser_id": 1, "billed_cents": 1}):
                await _accumulate(e.get("advertiser_id"), e.get("billed_cents"))
        except Exception:
            pass

    # Enrich with review stats + advertiser name + priority boost.
    ids = list(spend_by_adv.keys())
    adv_rows: Dict[str, Dict[str, Any]] = {}
    if ids:
        async for a in db.advertisers_v2.find(
                {"advertiser_id": {"$in": ids}},
                {"advertiser_id": 1, "name": 1, "status": 1, "logo_url": 1,
                  "priority_score_boost": 1}):
            adv_rows[a.get("advertiser_id")] = a
    # Reject stats per advertiser
    rej_stats = await db.ad_creative_reviews.aggregate([
        {"$match": {"advertiser_id": {"$in": ids}}} if ids else {"$match": {}},
        {"$group": {
            "_id": "$advertiser_id",
            "total_reviewed": {"$sum": {"$cond": [
                {"$in": ["$review_status", ["approved", "rejected"]]}, 1, 0]}},
            "rejects": {"$sum": {"$cond": [
                {"$eq": ["$review_status", "rejected"]}, 1, 0]}},
            "ttr_secs_avg": {"$avg": {"$cond": [
                {"$and": [{"$ne": ["$reviewed_at", None]},
                                  {"$ne": ["$submitted_at", None]}]},
                {"$divide": [{"$subtract": ["$reviewed_at", "$submitted_at"]},
                                          1000]},
                None]}},
        }},
    ]).to_list(500)
    rej_by_adv = {r["_id"]: r for r in rej_stats}

    rows: List[Dict[str, Any]] = []
    for adv_id, spend in spend_by_adv.items():
        arow = adv_rows.get(adv_id, {})
        rstat = rej_by_adv.get(adv_id, {})
        total_reviewed = int(rstat.get("total_reviewed") or 0)
        rejects            = int(rstat.get("rejects") or 0)
        reject_rate    = round(rejects / total_reviewed * 100, 1) \
                                        if total_reviewed else 0.0
        avg_ttr            = int(rstat.get("ttr_secs_avg") or 0)
        rows.append({
            "advertiser_id":          adv_id,
            "advertiser_name":      arow.get("name") or adv_id,
            "advertiser_status":  arow.get("status") or "active",
            "logo_url":                    arow.get("logo_url"),
            "spend_cents":              int(spend),
            "reject_rate_pct":      reject_rate,
            "avg_ttr_secs":          avg_ttr,
            "priority_score_boost": int(arow.get("priority_score_boost") or 0),
        })
    rows.sort(key=lambda r: r["spend_cents"], reverse=True)
    return {"items": rows[:max(1, int(limit or 10))],
                  "count": min(len(rows), int(limit or 10)),
                  "window_days": window_days, "ad_type": ad_type or "all"}


async def adjust_priority_score_boost(db, *, advertiser_id: str,
                                                                                        actor_user_id: str,
                                                                                        delta: int) -> Optional[Dict[str, Any]]:
    """VIP treatment / restriction.  Bumps or restricts an advertiser's
    priority score boost — applied additively on every future review row
    via `_priority_score`.  Clamped to [-30, +30] so it can't dominate
    the base score."""
    if delta == 0:
        return None
    now = _now()
    r = await db.advertisers_v2.find_one(
        {"advertiser_id": advertiser_id},
        {"priority_score_boost": 1, "name": 1})
    if not r:
        return None
    current = int(r.get("priority_score_boost") or 0)
    new_val = max(-30, min(30, current + int(delta)))
    await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id},
        {"$set": {"priority_score_boost": new_val,
                          "priority_boost_updated_at": now,
                          "priority_boost_updated_by": actor_user_id,
                          "updated_at": now}})
    await _audit(db, review_id=f"advertiser:{advertiser_id}",
                          actor_user_id=actor_user_id,
                          action="priority_boost" if delta > 0 else "priority_restrict",
                          before_status=str(current),
                          after_status=str(new_val),
                          notes=f"delta={delta}")
    # Also re-score any currently PENDING review rows so the bump
    # takes effect immediately without waiting for a resubmit.
    async for existing in db.ad_creative_reviews.find(
            {"advertiser_id": advertiser_id, "review_status": "pending"},
            {"review_id": 1, "ad_type": 1, "auto_moderation_result": 1}):
        base = _priority_score(ad_type=existing.get("ad_type"),
                                                          moderation=existing.get("auto_moderation_result") or {})
        await db.ad_creative_reviews.update_one(
            {"review_id": existing["review_id"]},
            {"$set": {"priority_score": base + new_val,
                              "updated_at": now}})
    return {"advertiser_id": advertiser_id,
                  "advertiser_name": r.get("name"),
                  "priority_score_boost": new_val,
                  "previous_boost": current,
                  "delta": delta}


async def list_reviews_by_target(db, *, ad_type: str,
                                                                    target_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Used by advertiser dashboards to show review-status badges."""
    if not target_ids:
        return {}
    rows = await db.ad_creative_reviews.find(
        {"ad_type": ad_type, "target_id": {"$in": target_ids}}
    ).sort([("submitted_at", -1)]).to_list(500)
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        tid = r.get("target_id")
        # Keep only the latest per target
        if tid not in out:
            out[tid] = _serialize(r)
    return out


__all__ = [
    "ensure_ad_review_indexes",
    "create_review",
    "approve_review", "reject_review", "require_changes",
    "bulk_approve", "bulk_reject",
    "list_queue", "get_review_detail",
    "analytics_summary",
    "list_blocked_advertisers", "block_advertiser", "unblock_advertiser",
    "is_advertiser_blocked", "list_audit_log", "list_reviews_by_target",
    "AD_TYPES", "REVIEW_STATUSES",
]
