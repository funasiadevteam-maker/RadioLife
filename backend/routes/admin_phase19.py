"""Phase 19 Parts A + B — Channel thumbnail re-roll + Unified moderation queue."""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user

router = APIRouter(prefix="/api/admin", tags=["admin-phase19"])
log = logging.getLogger("bigfm.admin_phase19")


def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()


def _require_admin(user: dict) -> None:
    if not user or not user.get("is_admin"):
        raise HTTPException(403, {"code": "forbidden"})


@router.post("/channels/{slug}/thumbnail/reroll")
async def reroll_channel_thumbnail(slug: str, request: Request, body: dict = None,
                                     user: dict = Depends(current_user)):
    """Part A — Generate a fresh thumbnail via the existing image-gen
    pipeline (Gemini Nano Banana when wired live, else placeholder).
    Persists `channel_thumbnail_overrides[slug]` w/ new URL + audit row."""
    _require_admin(user)
    db = request.app.state.db
    # Try the existing image gen service. Falls back to a deterministic
    # placeholder so the admin UI flow stays unblocked in mock-mode envs.
    new_url = None
    try:
        from services.imaging_rules import generate_channel_thumbnail
        new_url = await generate_channel_thumbnail(
            db, slug=slug, prompt=(body or {}).get("prompt"))
    except Exception as e:
        log.warning("[reroll] image-gen unavailable: %s — placeholder", e)
        new_url = f"/api/static/channel_thumbnails/{slug}.webp?v={int(datetime.now().timestamp())}"
    await db.channel_thumbnail_overrides.update_one(
        {"slug": slug},
        {"$set": {"slug": slug, "image_url": new_url,
                  "rerolled_at": _now_iso(),
                  "rerolled_by": user["user_id"]}}, upsert=True)
    await db.channel_thumbnail_audit.insert_one({
        "slug": slug, "new_url": new_url,
        "rerolled_by": user["user_id"],
        "prompt": (body or {}).get("prompt"),
        "at": _now_iso()})
    return {"ok": True, "slug": slug, "thumbnail_url": new_url}


@router.get("/moderation/queue")
async def unified_moderation_queue(request: Request,
                                     content_type: str = "all",
                                     user: dict = Depends(current_user)):
    """Part B — Unified queue across all moderation surfaces:
       game_campaigns · podcast_applications · social_posts ·
       business_reviews.  Filter via `content_type=<single>` or `all`.
    Each item is normalized to {item_id, type, summary, created_at,
    actor_user_id, payload}."""
    _require_admin(user)
    db = request.app.state.db
    items: list[dict] = []
    ct = (content_type or "all").lower()

    if ct in ("all", "game_campaigns"):
        async for g in db.game_campaigns_v2.find(
                {"status": "pending_approval"}).limit(50):
            items.append({"item_id": str(g.get("_id") or g.get("campaign_id")),
                "type": "game_campaign",
                "summary": g.get("title") or "(untitled game)",
                "created_at": g.get("created_at"),
                "actor_user_id": g.get("advertiser_user_id"),
                "payload": {"slot": g.get("slot")}})

    if ct in ("all", "podcast_applications"):
        async for c in db.podcast_creators.find(
                {"application_status": "pending",
                 "page_type": {"$in": [None, "podcast"]}}).limit(50):
            items.append({"item_id": c.get("id"),
                "type": "podcast_application",
                "summary": c.get("display_name"),
                "created_at": (c.get("applied_at").isoformat()
                                  if hasattr(c.get("applied_at"), "isoformat")
                                  else c.get("applied_at")),
                "actor_user_id": c.get("user_id"),
                "payload": {"market": c.get("market"),
                              "bio": (c.get("bio") or "")[:160]}})

    if ct in ("all", "social_posts"):
        async for p in db.social_posts.find(
                {"status": "pending_moderation"}).limit(50):
            items.append({"item_id": p.get("post_id"),
                "type": "social_post",
                "summary": (p.get("text") or "")[:160],
                "created_at": p.get("created_at"),
                "actor_user_id": p.get("author_user_id"),
                "payload": {"page_id": p.get("page_id"),
                              "media": p.get("media_urls", [])}})

    if ct in ("all", "business_reviews"):
        async for r in db.business_reviews.find(
                {"status": "pending_moderation"}).limit(50):
            items.append({"item_id": r.get("review_id"),
                "type": "business_review",
                "summary": (r.get("text") or "")[:160],
                "created_at": r.get("created_at"),
                "actor_user_id": r.get("user_id"),
                "payload": {"business_id": r.get("business_id"),
                              "stars": r.get("stars")}})

    # newest-first
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return {"count": len(items), "items": items}


@router.post("/moderation/{content_type}/{item_id}/decide")
async def decide_moderation(content_type: str, item_id: str, request: Request,
                              body: dict,
                              user: dict = Depends(current_user)):
    _require_admin(user)
    db = request.app.state.db
    action = (body.get("action") or "").lower()
    if action not in ("approve", "reject"):
        raise HTTPException(400, {"code": "bad_action"})
    reason = (body.get("reason") or "")[:300]
    coll, key = {
        "game_campaign":       ("game_campaigns_v2",  "campaign_id"),
        "podcast_application": ("podcast_creators",   "id"),
        "social_post":         ("social_posts",       "post_id"),
        "business_review":     ("business_reviews",   "review_id"),
    }.get(content_type, (None, None))
    if not coll:
        raise HTTPException(400, {"code": "bad_content_type"})
    new_status = "approved" if action == "approve" else "rejected"
    await db[coll].update_one({key: item_id},
        {"$set": {"status" if content_type != "podcast_application"
                  else "application_status": new_status,
                  "moderated_at": _now_iso(),
                  "moderated_by": user["user_id"],
                  "moderation_reason": reason}})
    await db.social_moderation_logs.insert_one({
        "content_type": content_type, "item_id": item_id,
        "action": action, "reason": reason,
        "admin_user_id": user["user_id"], "at": _now_iso()})
    return {"ok": True, "item_id": item_id, "new_status": new_status}
