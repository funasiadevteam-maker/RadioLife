"""Phase 41 Session 2.A — Station feed: posts + comments + reactions.

Listener-facing social engagement on a community station's `/r/{slug}`
page. Owner-only posts, public comments + reactions, soft-delete,
flagged-count moderation hook (full mod queue lands in Phase 19 B).

Reaction set per Phase 41 S2 spec (locked):
    like · love · fire · laugh · wow

Privacy ladder honored from Session 1:
    public      → posts visible to all
    unlisted   → posts visible only via direct slug link (same as the
                       station page itself)
    private      → posts hidden from non-owners

This module is NEW and uses the dedicated `station_posts`,
`station_comments`, `station_reactions` collections. The earlier
`social_posts.*` implementation (`routes/social_posts.py`) is left in
place untouched for backwards compatibility but is NOT consumed here.
"""
from __future__ import annotations
import asyncio
import io
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from auth import current_user, current_user_optional
from routes.community_stations import _visible_to as _station_visible_to


def _bust_analytics(slug: str) -> None:
    """Phase 41 S5/S6 — bust the in-process analytics cache so the
    Analytics + Earnings dashboards see this mutation right away."""
    try:
        from routes.station_analytics import bust_analytics_cache
        bust_analytics_cache(slug)
    except Exception:
        pass


# Phase 41 S2.C.1 — fire-and-forget notification triggers.
from routes.notifications import (
    trigger_for_comment   as _notify_for_comment,
    trigger_for_reaction  as _notify_for_reaction,
)

router = APIRouter(prefix="/api/stations", tags=["station-feed"])
log = logging.getLogger("bigfm.station_feed")

# --- constants per spec ---------------------------------------------------
VALID_REACTIONS = {"like", "love", "fire", "laugh", "wow"}
RATE_LIMITS: dict[str, int] = {
    "post":     10,   # per hour per user
    "comment":  60,
    "reaction": 300,
}
POST_BODY_MAX     = 2000
COMMENT_BODY_MAX  = 500
IMAGE_MAX_BYTES   = 5 * 1024 * 1024  # 5 MB
IMAGE_MIME_OK     = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
IMAGE_EXT_FROM_MIME = {
    "image/jpeg": "jpg",
    "image/jpg":  "jpg",
    "image/png":  "png",
    "image/webp": "webp",
}
FLAG_HIDE_THRESHOLD = 3   # hide from feed once >= 3 flags
POST_PAGE_SIZE_MAX     = 50
COMMENT_PAGE_SIZE_MAX  = 100


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str: return _now().isoformat()


# --- index ensuring -------------------------------------------------------
async def ensure_station_feed_indexes(db) -> None:
    try:
        await db.station_posts.create_index(
            [("station_slug", 1), ("created_at", -1)],
            name="posts_slug_recent")
        await db.station_posts.create_index(
            "post_id", unique=True, name="posts_id_unique")
        await db.station_comments.create_index(
            [("post_id", 1), ("created_at", 1)], name="comments_post_chrono")
        await db.station_comments.create_index(
            "comment_id", unique=True, name="comments_id_unique")
        await db.station_reactions.create_index(
            [("target_type", 1), ("target_id", 1), ("user_id", 1)],
            unique=True, name="reactions_one_per_user")
        await db.station_reactions.create_index(
            [("target_type", 1), ("target_id", 1)],
            name="reactions_by_target")
        # rate-limit bucket: one row per (user, action, hour)
        await db.station_feed_rate_limits.create_index(
            [("user_id", 1), ("action", 1), ("hour_bucket", 1)],
            unique=True, name="ratelimit_bucket")
        # TTL — auto-clean rate-limit rows after 25h (we only ever look
        # at the current hour bucket).
        await db.station_feed_rate_limits.create_index(
            "created_at", expireAfterSeconds=90000,
            name="ratelimit_ttl")
    except Exception as e:
        log.warning("[station_feed] index ensure: %s", e)


# --- helpers --------------------------------------------------------------
def _zero_counts() -> dict:
    return {r: 0 for r in VALID_REACTIONS}


def _strip(d: dict) -> dict:
    d.pop("_id", None)
    return d


async def _resolve_station(db, slug: str, user: Optional[dict],
                            *, via_direct_link: bool = True) -> dict:
    """Resolve a station by slug + apply Session 1 privacy ladder.
    Raises 404 with `not_found` if not visible to caller. Strips the
    raw `_id` ObjectId so callers never accidentally serialize it
    (defense-in-depth — every consumer in this module only reads
    fields by key, but lint enforces the contract anyway)."""
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "not_found"})
    if not _station_visible_to(s, user, via_direct_link=via_direct_link):
        raise HTTPException(404, {"code": "not_found"})
    s.pop("_id", None)
    return s


def _is_owner(station: dict, user: Optional[dict]) -> bool:
    return bool(user and station.get("owner_user_id") == user.get("user_id"))


def _is_admin(user: Optional[dict]) -> bool:
    return bool(user and (user.get("role") == "admin" or user.get("is_admin")))


async def _check_rate_limit(db, user_id: str, action: str) -> None:
    """Atomic hourly bucket. Raises 429 with retry_after_sec on cap."""
    cap = RATE_LIMITS.get(action, 60)
    hour_bucket = int(time.time() // 3600)
    key = {"user_id": user_id, "action": action, "hour_bucket": hour_bucket}
    r = await db.station_feed_rate_limits.find_one_and_update(
        key,
        {"$inc": {"count": 1},
         "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True, return_document=True)
    count = (r or {}).get("count", 0) or 1
    if count > cap:
        retry_after = 3600 - (int(time.time()) % 3600)
        raise HTTPException(429, {"code": "rate_limited",
                                   "action": action,
                                   "limit": cap,
                                   "retry_after_sec": retry_after})


def _signed_image_url(storage_key: Optional[str]) -> Optional[str]:
    if not storage_key:
        return None
    try:
        from services.object_storage import get_storage
        return get_storage().get_signed_url(key=storage_key, expires_in=3600)
    except Exception as e:
        log.warning("[station_feed] signed url failed key=%s: %s",
                    storage_key, e)
        return None


def _serialize_post(p: dict, *, viewer_id: Optional[str] = None,
                     viewer_reaction: Optional[str] = None,
                     is_admin: bool = False, is_owner: bool = False) -> dict:
    """Shape a post doc for the wire. Soft-deleted posts get scrubbed
    body+image unless viewer is admin or post owner."""
    out = _strip({**p})
    out["image_url"] = _signed_image_url(out.pop("image_storage_key", None))
    out.setdefault("reaction_counts", _zero_counts())
    # Fill any missing reaction keys so the client never has to check.
    out["reaction_counts"] = {**_zero_counts(), **out["reaction_counts"]}
    out["my_reaction"] = viewer_reaction
    out["is_mine"] = bool(viewer_id and out.get("author_id") == viewer_id)
    if out.get("deleted_at"):
        if not (is_admin or is_owner):
            out["body"] = "[deleted]"
            out["image_url"] = None
    return out


def _serialize_comment(c: dict, *, viewer_id: Optional[str] = None,
                        is_admin: bool = False,
                        is_post_owner: bool = False) -> dict:
    out = _strip({**c})
    out.setdefault("reaction_counts", _zero_counts())
    out["reaction_counts"] = {**_zero_counts(), **out["reaction_counts"]}
    out["is_mine"] = bool(viewer_id and out.get("author_id") == viewer_id)
    if out.get("deleted_at"):
        if not (is_admin or is_post_owner or out["is_mine"]):
            out["body"] = "[deleted]"
    return out


async def _viewer_reactions(db, user_id: Optional[str],
                             *, target_type: str,
                             target_ids: list) -> dict:
    """Returns {target_id: reaction_type} for the given viewer + targets."""
    if not user_id or not target_ids:
        return {}
    out: dict = {}
    cur = db.station_reactions.find(
        {"user_id": user_id, "target_type": target_type,
         "target_id": {"$in": target_ids}},
        {"target_id": 1, "reaction_type": 1, "_id": 0})
    async for r in cur:
        out[r["target_id"]] = r["reaction_type"]
    return out


# --- posts ----------------------------------------------------------------
@router.post("/{slug}/posts")
async def create_post(slug: str, request: Request,
                       body: Optional[str] = Form(None),
                       image: Optional[UploadFile] = File(None),
                       user: dict = Depends(current_user)):
    """Owner-only text/image post creation. Accepts multipart so the same
    endpoint covers JSON + image upload paths.

    Errors:
      401 auth_required
      403 not_owner          (caller is not station owner)
      404 not_found          (slug invalid / private+not-owner)
      400 validation_error  (body empty when no image; body too long; bad mime)
      413 image_too_large
      429 rate_limited
    """
    db = request.app.state.db
    await _check_rate_limit(db, user["user_id"], "post")
    station = await _resolve_station(db, slug, user)
    if not _is_owner(station, user):
        raise HTTPException(403, {"code": "not_owner",
                                   "message": "Only the station owner can post."})

    text = (body or "").strip()
    has_image = image is not None and getattr(image, "filename", "")
    if not text and not has_image:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "Post body or image required."})
    if len(text) > POST_BODY_MAX:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": f"Body must be ≤ {POST_BODY_MAX} chars."})

    post_id = "spost_" + uuid.uuid4().hex[:14]
    image_storage_key: Optional[str] = None

    if has_image:
        raw = await image.read()
        if len(raw) > IMAGE_MAX_BYTES:
            raise HTTPException(413, {"code": "image_too_large",
                                       "max_bytes": IMAGE_MAX_BYTES})
        mime = (image.content_type or "").lower()
        if mime not in IMAGE_MIME_OK:
            raise HTTPException(400, {"code": "validation_error",
                                       "message": "Image must be JPEG/PNG/WebP.",
                                       "received_mime": mime})
        ext = IMAGE_EXT_FROM_MIME[mime]
        image_storage_key = (f"station_post_images/{station['station_id']}/"
                              f"{post_id}.{ext}")
        try:
            from services.object_storage import get_storage
            storage = get_storage()
            tmp_path = f"/tmp/{post_id}.{ext}"
            with open(tmp_path, "wb") as f:
                f.write(raw)
            storage.upload(local_path=tmp_path, key=image_storage_key,
                            content_type=mime)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        except HTTPException:
            raise
        except Exception as e:
            log.error("[station_feed] image upload failed: %s", e)
            raise HTTPException(500, {"code": "image_upload_failed"})

    doc = {
        "_id":               post_id,
        "post_id":           post_id,
        "station_id":        station["station_id"],
        "station_slug":      station["slug"],
        "author_id":         user["user_id"],
        "author_name":       user.get("name") or user.get("email", "").split("@")[0],
        "body":              text,
        "image_storage_key": image_storage_key,
        "created_at":        _now_iso(),
        "deleted_at":        None,
        "reaction_counts":   _zero_counts(),
        "comment_count":     0,
        "flagged_count":     0,
    }
    await db.station_posts.insert_one(doc)
    _bust_analytics(slug)
    return {"ok": True, "post_id": post_id,
            "post": _serialize_post({**doc}, viewer_id=user["user_id"],
                                     is_owner=True)}


@router.get("/{slug}/posts")
async def list_posts(slug: str, request: Request,
                      limit: int = 20, before: Optional[str] = None,
                      user: Optional[dict] = Depends(current_user_optional)):
    """Paginated feed, newest first. Honors station privacy. Hides
    soft-deleted + flagged-count >= threshold from non-owner/non-admin
    viewers (owner/admin still see them, owner with "view deleted" toggle).
    """
    db = request.app.state.db
    station = await _resolve_station(db, slug, user)
    is_owner = _is_owner(station, user)
    is_admin_ = _is_admin(user)
    cap = max(1, min(limit, POST_PAGE_SIZE_MAX))

    q: dict = {"station_slug": slug}
    if before:
        q["created_at"] = {"$lt": before}
    if not (is_owner or is_admin_):
        q["deleted_at"] = None
        q["flagged_count"] = {"$lt": FLAG_HIDE_THRESHOLD}

    rows = []
    async for p in db.station_posts.find(q).sort("created_at", -1).limit(cap):
        rows.append(p)

    viewer_id = (user or {}).get("user_id")
    my_reactions = await _viewer_reactions(
        db, viewer_id, target_type="post",
        target_ids=[r["post_id"] for r in rows])
    items = [_serialize_post(p, viewer_id=viewer_id,
                              viewer_reaction=my_reactions.get(p["post_id"]),
                              is_admin=is_admin_, is_owner=is_owner)
             for p in rows]
    return {"items": items,
            "count": len(items),
            "next_before": items[-1]["created_at"] if items else None,
            "is_owner": is_owner}


@router.get("/{slug}/posts/{post_id}")
async def get_post(slug: str, post_id: str, request: Request,
                    user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    station = await _resolve_station(db, slug, user)
    is_owner = _is_owner(station, user)
    is_admin_ = _is_admin(user)
    p = await db.station_posts.find_one(
        {"post_id": post_id, "station_slug": slug})
    if not p:
        raise HTTPException(404, {"code": "not_found"})
    if p.get("deleted_at") and not (is_owner or is_admin_):
        raise HTTPException(404, {"code": "not_found"})

    viewer_id = (user or {}).get("user_id")
    my_reaction = (await _viewer_reactions(
        db, viewer_id, target_type="post", target_ids=[post_id])).get(post_id)
    # First 10 comments
    raw_comments = []
    async for c in db.station_comments.find(
            {"post_id": post_id}).sort("created_at", 1).limit(10):
        raw_comments.append(c)
    cmt_reactions = await _viewer_reactions(
        db, viewer_id, target_type="comment",
        target_ids=[c["comment_id"] for c in raw_comments])
    comments = []
    for c in raw_comments:
        c_out = _serialize_comment(c, viewer_id=viewer_id,
                                     is_admin=is_admin_,
                                     is_post_owner=(p["author_id"] == viewer_id))
        c_out["my_reaction"] = cmt_reactions.get(c["comment_id"])
        comments.append(c_out)
    return {"post": _serialize_post(p, viewer_id=viewer_id,
                                      viewer_reaction=my_reaction,
                                      is_admin=is_admin_, is_owner=is_owner),
            "comments": comments,
            "comments_count": p.get("comment_count", 0)}


@router.delete("/{slug}/posts/{post_id}")
async def delete_post(slug: str, post_id: str, request: Request,
                       user: dict = Depends(current_user)):
    """Soft-delete. Owner of post OR station owner OR admin can delete."""
    db = request.app.state.db
    station = await _resolve_station(db, slug, user)
    p = await db.station_posts.find_one(
        {"post_id": post_id, "station_slug": slug})
    if not p or p.get("deleted_at"):
        raise HTTPException(404, {"code": "not_found"})
    is_author = p["author_id"] == user["user_id"]
    if not (is_author or _is_owner(station, user) or _is_admin(user)):
        raise HTTPException(403, {"code": "permission_denied"})
    await db.station_posts.update_one(
        {"post_id": post_id},
        {"$set": {"deleted_at": _now_iso(),
                  "deleted_by": user["user_id"]}})
    return {"ok": True, "post_id": post_id}


# --- comments -------------------------------------------------------------
@router.post("/{slug}/posts/{post_id}/comments")
async def add_comment(slug: str, post_id: str, request: Request, body: dict,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_rate_limit(db, user["user_id"], "comment")
    await _resolve_station(db, slug, user)  # privacy gate
    p = await db.station_posts.find_one(
        {"post_id": post_id, "station_slug": slug})
    if not p or p.get("deleted_at"):
        raise HTTPException(404, {"code": "not_found"})
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "Comment body required."})
    if len(text) > COMMENT_BODY_MAX:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": f"Body must be ≤ {COMMENT_BODY_MAX} chars."})

    cid = "scmt_" + uuid.uuid4().hex[:14]
    doc = {
        "_id":             cid,
        "comment_id":      cid,
        "post_id":         post_id,
        "station_slug":    slug,
        "author_id":       user["user_id"],
        "author_name":     user.get("name") or user.get("email", "").split("@")[0],
        "body":            text,
        "created_at":      _now_iso(),
        "deleted_at":      None,
        "reaction_counts": _zero_counts(),
    }
    await db.station_comments.insert_one(doc)
    # Atomic increment of parent's comment_count
    await db.station_posts.update_one(
        {"post_id": post_id}, {"$inc": {"comment_count": 1}})
    # Phase 41 S2.C.1 — fire-and-forget notification (skips owner-self).
    try:
        station = await db.community_radio_stations.find_one({"slug": slug})
        if station:
            await _notify_for_comment(db, station, p, doc, user)
    except Exception as e:
        log.warning("[station_feed] notif trigger (comment) failed: %s", e)
    # Phase 41M.B — fire-and-forget comment_champion badge grant.
    try:
        station = station or await db.community_radio_stations.find_one(
            {"slug": slug})
        if station:
            from services.station_badge_engine import grant_safe
            asyncio.create_task(grant_safe(
                db, user_id=user["user_id"],
                station_id=station.get("station_id") or str(station.get("_id") or ""),
                station_slug=slug,
                only_types={"comment_champion"}))
    except Exception as e:
        log.warning("[station_feed] badge hook (comment) failed: %s", e)
    return {"ok": True, "comment_id": cid,
            "comment": _serialize_comment({**doc}, viewer_id=user["user_id"])}


@router.get("/{slug}/posts/{post_id}/comments")
async def list_comments(slug: str, post_id: str, request: Request,
                          limit: int = 50, before: Optional[str] = None,
                          user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    await _resolve_station(db, slug, user)
    cap = max(1, min(limit, COMMENT_PAGE_SIZE_MAX))
    q: dict = {"post_id": post_id}
    if before:
        q["created_at"] = {"$lt": before}
    rows = []
    async for c in db.station_comments.find(q).sort("created_at", 1).limit(cap):
        rows.append(c)
    viewer_id = (user or {}).get("user_id")
    cmt_reactions = await _viewer_reactions(
        db, viewer_id, target_type="comment",
        target_ids=[c["comment_id"] for c in rows])
    # Need to know whether viewer is post author for soft-delete masking
    p = await db.station_posts.find_one({"post_id": post_id},
                                         {"author_id": 1})
    is_post_owner = bool(p and viewer_id and p["author_id"] == viewer_id)
    is_admin_ = _is_admin(user)
    items = []
    for c in rows:
        co = _serialize_comment(c, viewer_id=viewer_id,
                                 is_admin=is_admin_,
                                 is_post_owner=is_post_owner)
        co["my_reaction"] = cmt_reactions.get(c["comment_id"])
        items.append(co)
    return {"items": items, "count": len(items),
            "next_before": items[-1]["created_at"] if items else None}


@router.delete("/{slug}/posts/{post_id}/comments/{comment_id}")
async def delete_comment(slug: str, post_id: str, comment_id: str,
                           request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    station = await _resolve_station(db, slug, user)
    c = await db.station_comments.find_one(
        {"comment_id": comment_id, "post_id": post_id})
    if not c or c.get("deleted_at"):
        raise HTTPException(404, {"code": "not_found"})
    is_author = c["author_id"] == user["user_id"]
    if not (is_author or _is_owner(station, user) or _is_admin(user)):
        raise HTTPException(403, {"code": "permission_denied"})
    await db.station_comments.update_one(
        {"comment_id": comment_id},
        {"$set": {"deleted_at": _now_iso(),
                  "deleted_by": user["user_id"]}})
    # Atomic decrement of parent comment count (don't go below 0)
    await db.station_posts.update_one(
        {"post_id": post_id, "comment_count": {"$gt": 0}},
        {"$inc": {"comment_count": -1}})
    return {"ok": True, "comment_id": comment_id}


# --- reactions ------------------------------------------------------------
@router.post("/{slug}/reactions")
async def react(slug: str, request: Request, body: dict,
                 user: dict = Depends(current_user)):
    """Toggle/upgrade a reaction. Body:
       {target_type: "post"|"comment", target_id, reaction_type}

    Same reaction twice → toggles off (returns my_reaction=null).
    Different reaction → in-place upgrade (atomic dec old, inc new).
    """
    db = request.app.state.db
    await _check_rate_limit(db, user["user_id"], "reaction")
    await _resolve_station(db, slug, user)
    tt = body.get("target_type")
    tid = body.get("target_id")
    rt = (body.get("reaction_type") or "").lower()
    if tt not in ("post", "comment"):
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "target_type must be post|comment."})
    if not tid:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "target_id required."})
    if rt not in VALID_REACTIONS:
        raise HTTPException(400, {"code": "validation_error",
                                   "message": "reaction_type must be one of "
                                               f"{sorted(VALID_REACTIONS)}.",
                                   "received": rt})

    # Find the target collection.
    target_col = (db.station_posts if tt == "post"
                  else db.station_comments)
    id_field = "post_id" if tt == "post" else "comment_id"
    target = await target_col.find_one({id_field: tid,
                                          "station_slug": slug})
    if not target or target.get("deleted_at"):
        raise HTTPException(404, {"code": "not_found"})

    existing = await db.station_reactions.find_one({
        "target_type": tt, "target_id": tid, "user_id": user["user_id"]})

    if existing and existing["reaction_type"] == rt:
        # Toggle off
        await db.station_reactions.delete_one({"_id": existing["_id"]})
        await target_col.update_one(
            {id_field: tid},
            {"$inc": {f"reaction_counts.{rt}": -1}})
        new_state: Optional[str] = None
    elif existing:
        # Upgrade: dec old, inc new in one atomic pair
        old = existing["reaction_type"]
        await db.station_reactions.update_one(
            {"_id": existing["_id"]},
            {"$set": {"reaction_type": rt, "updated_at": _now_iso()}})
        await target_col.update_one(
            {id_field: tid},
            {"$inc": {f"reaction_counts.{old}": -1,
                      f"reaction_counts.{rt}":  1}})
        new_state = rt
    else:
        # New row
        await db.station_reactions.insert_one({
            "_id": "rxn_" + uuid.uuid4().hex[:14],
            "target_type": tt, "target_id": tid,
            "user_id":     user["user_id"],
            "reaction_type": rt,
            "created_at":  _now_iso()})
        await target_col.update_one(
            {id_field: tid},
            {"$inc": {f"reaction_counts.{rt}": 1}})
        new_state = rt

    # Refresh counts from the source-of-truth doc
    fresh = await target_col.find_one({id_field: tid},
                                        {"reaction_counts": 1, "_id": 0})
    counts = {**_zero_counts(), **(fresh.get("reaction_counts") or {})}
    # Clamp negative values (defensive — shouldn't happen)
    counts = {k: max(0, v) for k, v in counts.items()}
    # Phase 41 S2.C.1 — milestone notification on POST reactions only.
    # Comment reactions don't trigger separate notifications (we only
    # notify on the comment landing). Fire-and-forget — never blocks
    # the response. (Restored after a regression that silently dropped
    # this call between S2.C.1 spec and verification.)
    if tt == "post":
        try:
            station = await db.community_radio_stations.find_one(
                {"slug": slug})
            if station:
                # `target` is the pre-$inc post doc but `_notify_for_reaction`
                # re-reads `reaction_counts` from the source-of-truth doc,
                # so passing the stale target is intentional and safe.
                await _notify_for_reaction(db, station, target, user)
        except Exception as e:
            log.warning("[station_feed] notif trigger (reaction) failed: %s", e)
        # Phase 41M.B — fire-and-forget top_reactor badge grant on
        # post reactions. Comment reactions don't count (would double
        # up since comments live inside the same station).
        try:
            station = station or await db.community_radio_stations.find_one(
                {"slug": slug})
            if station:
                from services.station_badge_engine import grant_safe
                asyncio.create_task(grant_safe(
                    db, user_id=user["user_id"],
                    station_id=station.get("station_id") or str(station.get("_id") or ""),
                    station_slug=slug,
                    only_types={"top_reactor"}))
        except Exception as e:
            log.warning("[station_feed] badge hook (reaction) failed: %s", e)
    return {"ok": True, "my_reaction": new_state, "counts": counts,
            "target_type": tt, "target_id": tid}


# --- moderation hook ------------------------------------------------------
@router.post("/{slug}/posts/{post_id}/flag")
async def flag_post(slug: str, post_id: str, request: Request,
                     user: dict = Depends(current_user)):
    """Soft-flag a post. flagged_count >= FLAG_HIDE_THRESHOLD hides the
    post from non-owner/non-admin viewers. Full Phase 19 B will replace
    this with a queueing flow + auto-ban heuristics."""
    db = request.app.state.db
    await _resolve_station(db, slug, user)
    p = await db.station_posts.find_one(
        {"post_id": post_id, "station_slug": slug})
    if not p:
        raise HTTPException(404, {"code": "not_found"})
    # Idempotent per user via a small flag-audit collection.
    r = await db.station_post_flags.update_one(
        {"post_id": post_id, "user_id": user["user_id"]},
        {"$setOnInsert": {"flagged_at": _now_iso()}}, upsert=True)
    if r.upserted_id:
        await db.station_posts.update_one(
            {"post_id": post_id}, {"$inc": {"flagged_count": 1}})
    fresh = await db.station_posts.find_one({"post_id": post_id},
                                              {"flagged_count": 1, "_id": 0})
    return {"ok": True, "flagged_count": fresh.get("flagged_count", 0)}
