"""Phase 41 Session 2 — Social posts + reactions + comments + notifications.

All writes go through `services/moderation.py::moderate`. Flagged posts
land in the unified moderation queue (Phase 19 B) as `social_posts`.
"""
from __future__ import annotations
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user
from services.moderation import moderate

router = APIRouter(prefix="/api/social", tags=["social-posts"])
log = logging.getLogger("bigfm.social")

VALID_REACTIONS = {"like", "love", "wow", "fire", "celebrate"}
MENTION_RE = re.compile(r"@([a-z0-9_]{3,32})", re.IGNORECASE)


def _now() -> str: return datetime.now(timezone.utc).isoformat()


async def ensure_social_indexes(db) -> None:
    try:
        await db.social_posts.create_index([("page_id", 1), ("created_at", -1)])
        await db.social_posts.create_index([("author_user_id", 1), ("created_at", -1)])
        await db.social_post_reactions.create_index(
            [("post_id", 1), ("user_id", 1)], unique=True,
            name="reaction_one_per_user")
        await db.social_post_comments.create_index([("post_id", 1), ("created_at", 1)])
        await db.social_notifications.create_index(
            [("user_id", 1), ("read", 1), ("created_at", -1)],
            name="notif_user_unread")
        await db.station_followers.create_index(
            [("user_id", 1), ("station_id", 1)], unique=True,
            name="follow_one_per_user")
    except Exception as e:
        log.warning("[social] index ensure: %s", e)


async def _resolve_page(db, page_id: str) -> Optional[dict]:
    """A page_id may map to either a community_radio_station or a
    podcast_creator. Returns whichever resolves first along with a
    `_kind` discriminator."""
    s = await db.community_radio_stations.find_one({"station_id": page_id})
    if s:
        return {**s, "_kind": "station", "_owner_id": s["owner_user_id"]}
    c = await db.podcast_creators.find_one({"id": page_id})
    if c:
        return {**c, "_kind": "creator", "_owner_id": c["user_id"]}
    return None


async def _notify(db, *, user_id: str, notif_type: str,
                   source_user_id: Optional[str] = None,
                   source_post_id: Optional[str] = None,
                   message: str = "") -> None:
    """Emit a notification.  Respects users.notification_prefs.<notif_type>
    opt-out (default = enabled)."""
    if not user_id or user_id == source_user_id:
        return  # don't notify self
    u = await db.users.find_one({"user_id": user_id},
                                 {"notification_prefs": 1})
    prefs = (u or {}).get("notification_prefs") or {}
    if prefs.get(notif_type) is False:
        return
    await db.social_notifications.insert_one({
        "_id":            "notif_" + uuid.uuid4().hex[:14],
        "user_id":        user_id,
        "notif_type":     notif_type,
        "source_user_id": source_user_id,
        "source_post_id": source_post_id,
        "message":        message[:240],
        "read":           False,
        "created_at":     _now()})


async def _scan_for_mentions(db, *, text: str, source_user_id: str,
                              post_id: Optional[str]) -> None:
    for m in MENTION_RE.finditer(text or ""):
        handle = m.group(1).lower()
        target = await db.users.find_one(
            {"$or": [{"username": handle}, {"handle": handle}]},
            {"user_id": 1})
        if target and target.get("user_id"):
            await _notify(db, user_id=target["user_id"],
                          notif_type="mention",
                          source_user_id=source_user_id,
                          source_post_id=post_id,
                          message=f"You were mentioned in a post.")


# ─── posts ────────────────────────────────────────────────────────────

@router.post("/pages/{page_id}/posts")
async def create_post(page_id: str, request: Request, body: dict,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    # Phase 41 S2 — rate limit. Raises 429 with retry_after_sec on cap.
    await _check_rate_limit(db, user["user_id"], "post")
    page = await _resolve_page(db, page_id)
    if not page:
        raise HTTPException(404, {"code": "page_not_found"})

    # Authorization: owner or page allows public posting (default no).
    is_owner = page["_owner_id"] == user["user_id"]
    if not is_owner and not page.get("allow_public_posting"):
        raise HTTPException(403, {"code": "not_authorized"})

    text = (body.get("text") or "")[:2000]
    media_urls = (body.get("media_urls") or [])[:8]
    post_type = body.get("post_type") or ("photo" if media_urls else "text")

    # Moderation
    verdict = await moderate(db, text=text, user_id=user["user_id"],
                              ref_type="social_post", ref_id=None)
    auto_approve = (verdict["verdict"] == "allow")
    has_photo = bool(media_urls)
    approval_status = ("approved" if auto_approve and not has_photo
                       else "pending_moderation")
    status_status = approval_status  # mirror for moderation queue

    post_id = "post_" + uuid.uuid4().hex[:14]
    doc = {
        "_id":             post_id,
        "post_id":         post_id,
        "page_id":         page_id,
        "author_user_id":  user["user_id"],
        "business_id":     page.get("business_id"),
        "post_type":       post_type,
        "text":            text,
        "media_urls":      media_urls,
        "mood":            body.get("mood"),
        "linked_station_id":   body.get("linked_station_id"),
        "linked_offer_id":     body.get("linked_offer_id"),
        "linked_game_id":      body.get("linked_game_id"),
        "linked_event_id":     body.get("linked_event_id"),
        "linked_wallet_item_id": body.get("linked_wallet_item_id"),
        "visibility":      body.get("visibility") or "public",
        "approval_status": approval_status,
        "status":          status_status,
        "reaction_counts": {},
        "comment_count":   0,
        "share_count":     0,
        "moderation_verdict": verdict["verdict"],
        "moderation_categories": verdict.get("categories") or [],
        "created_at":      _now()}
    await db.social_posts.insert_one(doc)
    # Mentions
    await _scan_for_mentions(db, text=text, source_user_id=user["user_id"],
                              post_id=post_id)
    return {"ok": True, "post_id": post_id,
            "approved": approval_status == "approved",
            "approval_status": approval_status,
            "moderation_verdict": verdict["verdict"]}


@router.get("/pages/{page_id}/posts")
async def list_page_posts(page_id: str, request: Request,
                            limit: int = 20, before: Optional[str] = None,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    page = await _resolve_page(db, page_id)
    if not page:
        raise HTTPException(404, {"code": "page_not_found"})
    # Phase 41 S2 — privacy gate. For station-kind pages, hide posts
    # from non-owners on private/unpublished stations. Unlisted is OK
    # because reaching this endpoint implies knowledge of the page_id
    # (direct-link semantics).
    if page.get("_kind") == "station":
        if not _station_visible_to(page, user.get("user_id"),
                                       via_direct_link=True):
            raise HTTPException(404, {"code": "page_not_found"})
    is_owner = page["_owner_id"] == user["user_id"]
    q: dict = {"page_id": page_id, "deleted_at": {"$exists": False}}
    if not is_owner:
        q["approval_status"] = "approved"
    if before:
        q["created_at"] = {"$lt": before}
    out = []
    cur = db.social_posts.find(q).sort("created_at", -1).limit(min(limit, 50))
    async for p in cur:
        p.pop("_id", None)
        out.append(p)
    return {"count": len(out), "items": out,
            "next_before": out[-1]["created_at"] if out else None}


@router.get("/feed")
async def social_feed(request: Request, limit: int = 20,
                       before: Optional[str] = None,
                       user: dict = Depends(current_user)):
    """Home feed — posts from pages this user follows. Newest first."""
    db = request.app.state.db
    # Followed station ids
    followed = [f["station_id"] async for f in db.station_followers.find(
        {"user_id": user["user_id"]}, {"station_id": 1})]
    if not followed:
        return {"count": 0, "items": [], "next_before": None}
    q: dict = {"page_id": {"$in": followed},
                "approval_status": "approved"}
    if before:
        q["created_at"] = {"$lt": before}
    out = []
    cur = db.social_posts.find(q).sort("created_at", -1).limit(min(limit, 50))
    async for p in cur:
        p.pop("_id", None)
        out.append(p)
    return {"count": len(out), "items": out,
            "next_before": out[-1]["created_at"] if out else None}


# ─── reactions ────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/react")
async def toggle_reaction(post_id: str, request: Request, body: dict,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_rate_limit(db, user["user_id"], "reaction")
    rt = (body.get("reaction_type") or "").lower()
    if rt not in VALID_REACTIONS:
        raise HTTPException(400, {"code": "bad_reaction",
                                  "allowed": sorted(VALID_REACTIONS)})
    p = await db.social_posts.find_one({"post_id": post_id})
    if not p:
        raise HTTPException(404, {"code": "not_found"})

    existing = await db.social_post_reactions.find_one(
        {"post_id": post_id, "user_id": user["user_id"]})
    if existing and existing["reaction_type"] == rt:
        # Toggle off
        await db.social_post_reactions.delete_one({"_id": existing["_id"]})
        new_state = None
    else:
        await db.social_post_reactions.update_one(
            {"post_id": post_id, "user_id": user["user_id"]},
            {"$set": {"reaction_type": rt, "created_at": _now()}},
            upsert=True)
        new_state = rt
        # Notify post author (once per reaction, not toggle-off)
        if p["author_user_id"] != user["user_id"]:
            await _notify(db, user_id=p["author_user_id"],
                          notif_type="post_reaction",
                          source_user_id=user["user_id"],
                          source_post_id=post_id,
                          message=f"Someone reacted with {rt} to your post.")

    # Recount
    counts: dict = {}
    cur = db.social_post_reactions.aggregate([
        {"$match": {"post_id": post_id}},
        {"$group": {"_id": "$reaction_type", "n": {"$sum": 1}}}])
    async for c in cur:
        counts[c["_id"]] = c["n"]
    await db.social_posts.update_one(
        {"post_id": post_id}, {"$set": {"reaction_counts": counts}})
    return {"ok": True, "my_reaction": new_state, "counts": counts}


# ─── comments ─────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/comments")
async def add_comment(post_id: str, request: Request, body: dict,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_rate_limit(db, user["user_id"], "comment")
    p = await db.social_posts.find_one({"post_id": post_id})
    if not p:
        raise HTTPException(404, {"code": "not_found"})
    text = (body.get("comment_text") or "")[:1000]
    if not text.strip():
        raise HTTPException(400, {"code": "empty_comment"})
    verdict = await moderate(db, text=text, user_id=user["user_id"],
                              ref_type="social_comment")
    auto_approve = verdict["verdict"] == "allow"
    cid = "cmt_" + uuid.uuid4().hex[:14]
    doc = {
        "_id":               cid,
        "comment_id":        cid,
        "post_id":           post_id,
        "user_id":           user["user_id"],
        "comment_text":      text,
        "parent_comment_id": body.get("parent_comment_id"),
        "approval_status":   "approved" if auto_approve else "pending_moderation",
        "status":            "approved" if auto_approve else "pending_moderation",
        "created_at":        _now()}
    await db.social_post_comments.insert_one(doc)
    if auto_approve:
        await db.social_posts.update_one(
            {"post_id": post_id}, {"$inc": {"comment_count": 1}})
        # Notify post author
        await _notify(db, user_id=p["author_user_id"],
                      notif_type="post_comment",
                      source_user_id=user["user_id"],
                      source_post_id=post_id,
                      message=f"New comment on your post: {text[:80]}")
        # Mentions inside comments
        await _scan_for_mentions(db, text=text,
                                  source_user_id=user["user_id"],
                                  post_id=post_id)
    return {"ok": True, "comment_id": cid,
            "approved": auto_approve}


@router.get("/posts/{post_id}/comments")
async def list_comments(post_id: str, request: Request, limit: int = 50,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    out = []
    cur = db.social_post_comments.find(
        {"post_id": post_id, "approval_status": "approved"}
    ).sort("created_at", 1).limit(min(limit, 200))
    async for c in cur:
        c.pop("_id", None)
        out.append(c)
    return {"count": len(out), "items": out}


# Phase 41 S2 — soft-delete endpoints. Posts/comments stay in DB
# (so admin/owner can audit) but disappear from the public feed.

@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await db.social_posts.find_one({"post_id": post_id})
    if not p or p.get("deleted_at"):
        raise HTTPException(404, {"code": "not_found"})
    is_author = p["author_user_id"] == user["user_id"]
    is_admin = bool(user.get("is_admin"))
    is_page_owner = False
    page = await _resolve_page(db, p["page_id"])
    if page and page.get("_owner_id") == user["user_id"]:
        is_page_owner = True
    if not (is_author or is_admin or is_page_owner):
        raise HTTPException(403, {"code": "permission_denied"})
    await db.social_posts.update_one(
        {"post_id": post_id},
        {"$set": {"deleted_at": _now(), "deleted_by": user["user_id"]}})
    return {"ok": True, "post_id": post_id}


@router.delete("/posts/{post_id}/comments/{comment_id}")
async def delete_comment(post_id: str, comment_id: str, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.social_post_comments.find_one({"comment_id": comment_id})
    if not c or c.get("deleted_at"):
        raise HTTPException(404, {"code": "not_found"})
    is_author = c["user_id"] == user["user_id"]
    is_admin = bool(user.get("is_admin"))
    is_page_owner = False
    p = await db.social_posts.find_one({"post_id": post_id})
    if p:
        page = await _resolve_page(db, p["page_id"])
        if page and page.get("_owner_id") == user["user_id"]:
            is_page_owner = True
    if not (is_author or is_admin or is_page_owner):
        raise HTTPException(403, {"code": "permission_denied"})
    await db.social_post_comments.update_one(
        {"comment_id": comment_id},
        {"$set": {"deleted_at": _now(), "deleted_by": user["user_id"]}})
    await db.social_posts.update_one(
        {"post_id": post_id, "comment_count": {"$gt": 0}},
        {"$inc": {"comment_count": -1}})
    return {"ok": True, "comment_id": comment_id}


@router.post("/posts/{post_id}/share")
async def share_post(post_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await db.social_posts.find_one({"post_id": post_id})
    if not p:
        raise HTTPException(404, {"code": "not_found"})
    await db.social_posts.update_one(
        {"post_id": post_id}, {"$inc": {"share_count": 1}})
    if p["author_user_id"] != user["user_id"]:
        await _notify(db, user_id=p["author_user_id"],
                      notif_type="post_share",
                      source_user_id=user["user_id"],
                      source_post_id=post_id,
                      message="Someone shared your post.")
    return {"ok": True}


# ─── notifications ────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(request: Request, unread: bool = False,
                              limit: int = 20,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    q: dict = {"user_id": user["user_id"]}
    if unread: q["read"] = False
    out = []
    cur = db.social_notifications.find(q).sort("created_at", -1).limit(
        min(limit, 50))
    async for n in cur:
        n["notification_id"] = n.pop("_id")
        out.append(n)
    n_unread = await db.social_notifications.count_documents(
        {"user_id": user["user_id"], "read": False})
    return {"count": len(out), "unread_total": n_unread, "items": out}


@router.post("/notifications/mark_read")
async def mark_notifications_read(request: Request, body: dict,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    ids = body.get("notification_ids") or []
    if not ids:
        # Mark all read
        r = await db.social_notifications.update_many(
            {"user_id": user["user_id"], "read": False},
            {"$set": {"read": True, "read_at": _now()}})
        return {"ok": True, "marked": r.modified_count}
    r = await db.social_notifications.update_many(
        {"user_id": user["user_id"], "_id": {"$in": ids}},
        {"$set": {"read": True, "read_at": _now()}})
    return {"ok": True, "marked": r.modified_count}
