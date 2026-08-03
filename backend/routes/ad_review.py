"""Phase ADMOD.1 — /api/ad-review/* HTTP routes.

All endpoints require `ad_manager` OR `admin` role.  Advertiser-side
transparency (review status badges, blocked banner) uses different
routes on the advertiser dashboards.

Also exposes the AD.4 pricing-hints endpoint at `/api/ad-pricing-hints`
(publicly readable — no PII, purely advisory).
"""
from __future__ import annotations

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from auth import current_user
from services.ad_manager_rbac_service import require_ad_manager
from services import ad_creative_review_service as _svc
from config.ad_pricing_hints import hints_payload

router = APIRouter(tags=["admod1-ad-review"])
logger = logging.getLogger("bigfm.ad_review.routes")


# ─── Body models ─────────────────────────────────────────────────
class ApproveBody(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)


class RejectBody(BaseModel):
    reason:  str = Field(..., min_length=1, max_length=500)
    notes:  Optional[str] = Field(default=None, max_length=500)


class RequireChangesBody(BaseModel):
    notes: str = Field(..., min_length=1, max_length=500)


class BulkBody(BaseModel):
    review_ids: List[str] = Field(..., min_length=1, max_length=100)
    notes:            Optional[str] = Field(default=None, max_length=500)


class BulkRejectBody(BulkBody):
    reason: str = Field(..., min_length=1, max_length=500)


class BlockBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# ─── Queue ───────────────────────────────────────────────────────
@router.get("/api/ad-review/queue",
                        description="Ad Manager queue — filter by status/type/advertiser/flagged.")
async def get_queue(request: Request,
                                        status: Optional[str] = Query("pending"),
                                        ad_type: Optional[str] = None,
                                        advertiser_id: Optional[str] = None,
                                        flagged_only: bool = False,
                                        sort: str = Query("priority",
                                                                              pattern="^(priority|newest|oldest)$"),
                                        limit: int = Query(50, ge=1, le=200),
                                        _user: dict = Depends(require_ad_manager)):
    return await _svc.list_queue(
        request.app.state.db,
        status=status, ad_type=ad_type, advertiser_id=advertiser_id,
        flagged_only=flagged_only, sort=sort, limit=limit)


@router.get("/api/ad-review/queue/{review_id}",
                        description="Detail view + AI moderation summary + past advertiser rejects.")
async def get_detail(review_id: str, request: Request,
                                          _user: dict = Depends(require_ad_manager)):
    doc = await _svc.get_review_detail(request.app.state.db, review_id=review_id)
    if not doc:
        raise HTTPException(404, {"code": "review_not_found"})
    return doc


@router.post("/api/ad-review/queue/{review_id}/approve")
async def approve(review_id: str, body: ApproveBody, request: Request,
                                    user: dict = Depends(require_ad_manager)):
    doc = await _svc.approve_review(
        request.app.state.db, review_id=review_id,
        reviewer_user_id=user.get("user_id"), notes=body.notes)
    if not doc:
        raise HTTPException(404, {"code": "review_not_found"})
    return doc


@router.post("/api/ad-review/queue/{review_id}/reject")
async def reject(review_id: str, body: RejectBody, request: Request,
                                user: dict = Depends(require_ad_manager)):
    doc = await _svc.reject_review(
        request.app.state.db, review_id=review_id,
        reviewer_user_id=user.get("user_id"),
        reason=body.reason, notes=body.notes)
    if not doc:
        raise HTTPException(404, {"code": "review_not_found"})
    return doc


@router.post("/api/ad-review/queue/{review_id}/require-changes")
async def send_back(review_id: str, body: RequireChangesBody,
                                            request: Request,
                                            user: dict = Depends(require_ad_manager)):
    doc = await _svc.require_changes(
        request.app.state.db, review_id=review_id,
        reviewer_user_id=user.get("user_id"), notes=body.notes)
    if not doc:
        raise HTTPException(404, {"code": "review_not_found"})
    return doc


@router.post("/api/ad-review/queue/bulk-approve")
async def bulk_approve(body: BulkBody, request: Request,
                                              user: dict = Depends(require_ad_manager)):
    return await _svc.bulk_approve(
        request.app.state.db, review_ids=body.review_ids,
        reviewer_user_id=user.get("user_id"), notes=body.notes)


@router.post("/api/ad-review/queue/bulk-reject")
async def bulk_reject(body: BulkRejectBody, request: Request,
                                            user: dict = Depends(require_ad_manager)):
    return await _svc.bulk_reject(
        request.app.state.db, review_ids=body.review_ids,
        reviewer_user_id=user.get("user_id"),
        reason=body.reason, notes=body.notes)


# ─── Analytics ──────────────────────────────────────────────────
@router.get("/api/ad-review/analytics",
                        description="Pass/reject rate, per-day counts, avg time-to-review, top rejected advertisers.")
async def analytics(request: Request,
                                        days: int = Query(14, ge=1, le=90),
                                        _user: dict = Depends(require_ad_manager)):
    return await _svc.analytics_summary(request.app.state.db, days=days)


# ─── Phase PREROLL.EXT — Top Spenders + VIP priority bump ───────
@router.get("/api/ad-review/analytics/top-spenders",
                        description="Top advertisers by spend across all/filtered ad types.")
async def top_spenders(request: Request,
                                              ad_type: Optional[str] = None,
                                              window_days: int = Query(30, ge=1, le=180),
                                              limit: int = Query(10, ge=1, le=100),
                                              _user: dict = Depends(require_ad_manager)):
    return await _svc.top_spenders(
        request.app.state.db, ad_type=ad_type,
        window_days=window_days, limit=limit)


class PriorityAdjustBody(BaseModel):
    delta: int = Field(..., ge=-10, le=10,
                                          description="Signed delta.  +5 for VIP boost, -5 to restrict.")


@router.post("/api/ad-review/advertisers/{advertiser_id}/priority-adjust")
async def priority_adjust(advertiser_id: str,
                                                        body: PriorityAdjustBody,
                                                        request: Request,
                                                        user: dict = Depends(require_ad_manager)):
    doc = await _svc.adjust_priority_score_boost(
        request.app.state.db, advertiser_id=advertiser_id,
        actor_user_id=user.get("user_id"), delta=body.delta)
    if not doc:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    return doc


# ─── Advertiser block/unblock ───────────────────────────────────
@router.get("/api/ad-review/blocked-advertisers")
async def get_blocked(request: Request,
                                            limit: int = Query(100, ge=1, le=500),
                                            _user: dict = Depends(require_ad_manager)):
    return await _svc.list_blocked_advertisers(request.app.state.db, limit=limit)


@router.post("/api/ad-review/advertisers/{advertiser_id}/block")
async def block(advertiser_id: str, body: BlockBody, request: Request,
                            user: dict = Depends(require_ad_manager)):
    doc = await _svc.block_advertiser(
        request.app.state.db, advertiser_id=advertiser_id,
        actor_user_id=user.get("user_id"), reason=body.reason)
    if not doc:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    return doc


@router.post("/api/ad-review/advertisers/{advertiser_id}/unblock")
async def unblock(advertiser_id: str, request: Request,
                                    user: dict = Depends(require_ad_manager)):
    doc = await _svc.unblock_advertiser(
        request.app.state.db, advertiser_id=advertiser_id,
        actor_user_id=user.get("user_id"))
    if not doc:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    return doc


# ─── Audit log ──────────────────────────────────────────────────
@router.get("/api/ad-review/audit-log")
async def get_audit(request: Request,
                                        review_id: Optional[str] = None,
                                        actor_user_id: Optional[str] = None,
                                        limit: int = Query(100, ge=1, le=500),
                                        _user: dict = Depends(require_ad_manager)):
    return await _svc.list_audit_log(
        request.app.state.db, review_id=review_id,
        actor_user_id=actor_user_id, limit=limit)


# ─── Phase ADMIN.NAV.2 (bundled with AD.11) — nav badge counts ───
@router.get("/api/admin/nav-counts",
                        description="Lightweight badge counts for the admin sidebar.  "
                                                    "Polled from AdminSidebar every 60s.")
async def admin_nav_counts(request: Request,
                                                          user: dict = Depends(current_user)):
    if not user or user.get("role") not in ("admin", "ad_manager"):
        raise HTTPException(403, {"code": "admin_or_ad_manager_required"})
    db = request.app.state.db
    # Best-effort counters — each wrapped so a missing collection can't
    # break the whole endpoint.
    async def _count(coll_name, q):
        try:
            return await db[coll_name].count_documents(q)
        except Exception:
            return 0
    ad_review_pending = await _count("ad_creative_reviews",
                                                                                {"review_status": "pending"})
    # Banner-specific slice (subset of ad_review_pending)
    banner_reviews_pending = await _count("ad_creative_reviews",
        {"review_status": "pending", "ad_type": "banner"})
    merchant_applications_pending = await _count("merchant_applications",
        {"status": {"$in": ["pending", "pending_review"]}})
    refunds_pending = await _count("payment_transactions_v2",
        {"status": "refund_pending"})
    station_claims_pending = await _count("station_claims",
        {"status": {"$in": ["pending", "pending_review", "pending_admin"]}})
    podcast_apps_pending = await _count("podcast_applications",
        {"status": {"$in": ["pending", "pending_review", "pending_admin"]}})
    return {
        "ad_review_pending":                          ad_review_pending,
        "banner_reviews_pending":                banner_reviews_pending,
        "merchant_applications_pending":  merchant_applications_pending,
        "refunds_pending":                            refunds_pending,
        "station_claims_pending":                station_claims_pending,
        "podcast_apps_pending":                    podcast_apps_pending,
    }


# ─── Advertiser-side helpers (any authed user reads own advertiser data) ─
@router.get("/api/advertiser/{advertiser_id}/review-badges",
                        description=("Returns latest review status per campaign for the advertiser's "
                                                        "campaigns.  Used by advertiser dashboards to show badges."))
async def advertiser_review_badges(advertiser_id: str,
                                                                                request: Request,
                                                                                ad_type: str = Query("coupon_campaign")):
    db = request.app.state.db
    if ad_type == "coupon_campaign":
        rows = await db.coupon_campaigns.find(
            {"advertiser_id": advertiser_id},
            {"campaign_id": 1, "_id": 0}).to_list(500)
    elif ad_type == "advertiser_campaign":
        rows = await db.ad_campaigns_v2.find(
            {"advertiser_id": advertiser_id},
            {"campaign_id": 1, "_id": 0}).to_list(500)
    else:
        rows = []
    ids = [r.get("campaign_id") for r in rows if r.get("campaign_id")]
    badges = await _svc.list_reviews_by_target(db, ad_type=ad_type, target_ids=ids)
    return {"badges": badges, "count": len(badges)}


# ─── AD.4 pricing hints (public, advisory) ──────────────────────
@router.get("/api/ad-pricing-hints",
                        description="Recommended CPS by category.  Used by AD.4 wizard tooltip.")
async def pricing_hints():
    return hints_payload()


__all__ = ["router"]
